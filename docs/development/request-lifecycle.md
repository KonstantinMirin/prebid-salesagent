# Request Lifecycle

How a request travels from the wire to business logic — and what has already
happened to it by the time your `_impl` function runs.

Read this before adding anything to the request path: a header to read, a field
to normalise, an auth rule, a tenant-scoped check. Each of those has exactly one
layer that owns it (see [Where does my change go?](#where-does-my-change-go) at
the end). The principles this layering serves — why logic lives only in
`_impl`, and why construction and serialization happen only at the boundary —
are in [architecture-principles.md](architecture-principles.md).

## One process, four front doors

Everything is served by a single FastAPI application, built in `src/app.py`.
nginx sits in front (port 8000 locally) and proxies to it; there is no
per-protocol process. The app exposes four kinds of entry point:

| Path | Protocol | How it is wired |
|------|----------|-----------------|
| `/api/v1/*` | REST | FastAPI routes from `src/routes/api_v1.py` (`app.include_router`) |
| `/mcp` | MCP | FastMCP sub-application (`mcp.http_app()`), mounted with `app.mount("/mcp", mcp_app)` |
| `/a2a` + `/.well-known/agent-card.json` | A2A (JSON-RPC) | a2a-sdk route factories, appended **directly** to the FastAPI app's route table — not mounted as a sub-app, so the app's middleware and `scope["state"]` are visible to A2A handlers |
| `/admin` and `/` (catch-all) | Admin UI | The Flask admin app (`src.admin.app.create_app`), wrapped in `WSGIMiddleware` and mounted into FastAPI |

Two details are worth attention:

- **The admin UI is a Flask app living inside the FastAPI app.** It is mounted
  at startup (in the lifespan hook, via `_install_admin_mounts()`) rather than
  at import time, so that the root catch-all mount is guaranteed to be the
  *last* route — every FastAPI route, including ones added later, must match
  before Flask swallows the path. Admin authentication (Google OAuth sessions)
  is Flask's own and is not part of the AdCP request path this document traces.
- **Landing pages** for `GET /` and `GET /landing` are inserted at position 0
  of the route table so they win over the root Flask mount. They resolve the
  tenant from the `Host` header and render a tenant landing page.

Health routes (`src/routes/health.py`) are included alongside the REST router.

## The ASGI middleware stack — and its real order

`src/app.py` registers HTTP middleware on the root app. **Starlette's
`add_middleware` makes the last-registered middleware the outermost one, so the
registration order in the file reads backwards from the execution order.** This
is a live trap: adding a middleware "after" another in the source puts it
*before* that one on the wire.

The actual traversal, outermost first, for every HTTP request:

1. **`CORSMiddleware`** — adds CORS headers to all responses
   (origins from `ALLOWED_ORIGINS`).
2. **`RestCompatMiddleware`** (`src/routes/rest_compat_middleware.py`) —
   REST-only backwards-compatibility body normalisation; a no-op for anything
   that is not a JSON `POST` to `/api/v1/*`. Details
   [below](#the-backwards-compatibility-edge).
3. **`UnifiedAuthMiddleware`** (`src/core/auth_middleware.py`) — extracts the
   auth token and stashes it, with the request headers, in
   `scope["state"]["auth_context"]` as an immutable `AuthContext`
   (`src/core/auth_context.py`). It is a pure ASGI class (not
   `BaseHTTPMiddleware`), which keeps it free of ContextVar-propagation
   pitfalls. It does **no** database work and resolves **no** identity — it
   only parses headers, so every request pays for a string scan, not a DB
   round-trip.
4. **A2A messageId compatibility middleware** (`a2a_messageid_compatibility_middleware`
   in `src/app.py`) — rewrites numeric `messageId` / JSON-RPC `id` values to
   strings on `POST /a2a` bodies; a no-op for every other path.
5. **The router** — REST routes, the `/mcp` mount, the A2A routes, health,
   landing, and finally the Flask admin mounts.

Token extraction in `UnifiedAuthMiddleware` checks `x-adcp-auth` first (the
AdCP convention) and falls back to `Authorization: Bearer` (case-insensitive
per RFC 7235). The resulting `AuthContext` backs `request.state.auth_context`
for FastAPI routes and is what the A2A context builder reads.

## Identity: `resolve_identity`

All three transports converge on one function before business logic runs:

```
resolve_identity(headers, auth_token=None, protocol="mcp"|"a2a"|"rest",
                 require_valid_token=True, testing_context=None) -> ResolvedIdentity
```

(`src/core/resolved_identity.py`.) It is the single entry point for identity
resolution, called once per request at each transport boundary. It does three
things, in order:

**1. Tenant detection** (`_detect_tenant`) — four strategies, first match wins:

1. `Host` header → virtual-host lookup, then subdomain extraction
   (`<subdomain>.<domain>` → tenant by subdomain; `localhost`, `www`, `admin`
   and the service's own name are excluded).
2. `x-adcp-tenant` header (set by nginx for path-based routing) → subdomain
   lookup, then direct tenant-id lookup.
3. `Apx-Incoming-Host` header (Approximated.app virtual hosts) → virtual-host
   lookup.
4. Localhost fallback → the `default` tenant.

**2. Token extraction** — same priority as the middleware (`x-adcp-auth`, then
`Authorization: Bearer`), used only when the transport did not hand the token
in already.

**3. Principal resolution** — `get_principal_from_token`
(`src/core/auth_utils.py`) looks the token up in the database. With a detected
tenant the lookup is scoped to that tenant; without one it searches globally
and *discovers* the tenant from the token. An invalid token raises
`AdCPAuthenticationError` when `require_valid_token=True`; with
`require_valid_token=False` an invalid or missing token degrades to an
unauthenticated identity instead — this is what discovery endpoints
(`get_products`, `list_creative_formats`, …) and best-effort observability use.

The result is a frozen `ResolvedIdentity`: `principal_id`, `tenant_id`,
`tenant` (a `TenantContext`), `auth_token`, `protocol`, `testing_context`
(AdCP testing hooks, parsed from headers), and `account_id` (populated by
`enrich_identity_with_account` when the request body carries an
`AccountReference`). Business logic receives this object and nothing
transport-shaped — that is the whole point.

`resolve_identity_from_context` (`src/core/transport_helpers.py`) is not a
second resolver; it is the bridge that adapts transport-specific context types
to the same call: given a FastMCP `Context` it pulls the HTTP headers and
testing context out and delegates to `resolve_identity`; given a `ToolContext`
(the A2A path's carrier, which already holds resolved identity fields) it
builds the `ResolvedIdentity` directly with a lazy tenant that defers the DB
load until a field beyond `tenant_id` is touched.

## The path per transport

### REST

```
wire → CORS → RestCompat → UnifiedAuth → route → Depends(require_auth) → handler → _impl
```

1. `RestCompatMiddleware` stashes the body bytes **as sent** on
   `request.state.raw_wire_payload` (the idempotency payload-hash input), then
   normalises deprecated field names so Pydantic parses current-version names.
2. `UnifiedAuthMiddleware` sets `request.state.auth_context`.
3. The route's dependency resolves identity (`src/core/auth_context.py`):
   `RequireAuth` / `require_auth` raises `AdCPAuthRequiredError` (a 401
   envelope) when the token is missing or invalid; `ResolveAuth` /
   `resolve_auth` is the auth-optional variant for discovery endpoints and
   yields `None` instead of raising. Both call `resolve_identity(...,
   protocol="rest")` and set the tenant ContextVar (`set_current_tenant`) at
   the boundary.
4. The route handler in `src/routes/api_v1.py` coerces wire dicts into SDK
   types and calls the shared `_impl`/`_raw` function with the identity.
5. Errors surface through the app-level exception handlers in `src/app.py`:
   `AdCPError` (and normalised `ValueError` / `PermissionError` /
   `RequestValidationError` / `ToolError`) become the two-layer AdCP error
   envelope with the exception's HTTP status. Every handler funnels through
   `record_boundary_error`, so logging, the activity feed, and the audit log
   behave identically across transports.

### MCP

```
wire → (root-app middleware) → /mcp mount → FastMCP → MCPAuthMiddleware
     → RequestCompatMiddleware → tool wrapper → _impl
```

The root-app middleware runs first (the mount is inside the stack), but the
MCP path does its own work with **FastMCP middleware**, registered in
`src/core/main.py`. Note the ordering semantics differ from Starlette:
`mcp.add_middleware` runs middlewares **in registration order** — first added
runs first.

1. **`MCPAuthMiddleware`** (`src/core/mcp_auth_middleware.py`) runs on every
   tool call. It resolves identity once (via `resolve_identity_from_context`)
   and stores it on FastMCP context state, along with the raw wire arguments
   (captured *before* any normalisation — the idempotency payload-hash input)
   and the `x-context-id` header. Tools listed in `AUTH_OPTIONAL_TOOLS`
   (the discovery tools) resolve with `require_valid_token=False`; every other
   tool requires a valid token.
2. **`RequestCompatMiddleware`** (`src/core/mcp_compat_middleware.py`)
   normalises the tool arguments — [below](#the-backwards-compatibility-edge).
3. The tool wrapper (registered via `mcp.tool(...)` in `src/core/main.py`,
   wrapped in `with_error_logging`) reads the pre-resolved identity —
   `identity = await ctx.get_state("identity")` — and calls `_impl`. Tool
   wrappers do not call `resolve_identity` themselves.
4. Errors: `with_error_logging` (`src/core/tool_error_logging.py`) translates
   typed `AdCPError`s into an `AdCPToolError` carrying the same two-layer
   envelope, marked `isError: true` on the MCP wire.

MCP needs its own auth layer rather than sharing `UnifiedAuthMiddleware`
because the unit of work is different: the ASGI middleware sees one HTTP
request, but MCP multiplexes tool calls over a session, and auth-optionality
is a *per-tool* property (`AUTH_OPTIONAL_TOOLS`) that only the FastMCP layer
can see. The ASGI layer still runs and extracts the token; the FastMCP layer
is where identity is resolved and attached to the tool-call context.

### A2A

```
wire → CORS → RestCompat(no-op) → UnifiedAuth → messageId compat → /a2a route
     → AdCPCallContextBuilder → AdCPRequestHandler → _resolve_a2a_identity
     → skill handler → raw function / _impl
```

1. The A2A JSON-RPC routes are plain routes on the FastAPI app, built by the
   a2a-sdk route factories with `AdCPCallContextBuilder`
   (`src/a2a_server/context_builder.py`) as the context builder. The builder
   copies `request.state.auth_context` (set by `UnifiedAuthMiddleware`) into
   the SDK's `ServerCallContext.state` — this is the bridge between the ASGI
   world and the SDK's handler world, and it is why the routes must live on
   the app itself rather than in a sub-app: `scope["state"]` has to propagate.
2. `AdCPRequestHandler` (`src/a2a_server/adcp_a2a_server.py`) handles
   `message/send`. It resolves identity **once** per request via
   `_resolve_a2a_identity`, which reads the token and headers from the
   `AuthContext`, extracts the testing context, calls
   `resolve_identity(..., protocol="a2a")`, sets the tenant ContextVar, and
   translates auth failures into A2A errors. Unauthenticated requests are
   allowed through (with `require_valid_token=False`) only when every
   requested skill is in the `DISCOVERY_SKILLS` set. No downstream handler calls `resolve_identity` again.
3. Explicit skill invocations dispatch through `_handle_explicit_skill` to a
   per-skill handler, which calls the shared raw function / `_impl` with the
   pre-resolved identity (some build a `ToolContext` from it via
   `_make_tool_context` — no database calls, identity is already resolved).
4. Errors: `AdCPError` from business logic becomes a **failed Task** whose
   artifact carries the two-layer envelope; JSON-RPC errors (`A2AError`) are
   reserved for transport-protocol failures such as unknown methods.

The agent card at `/.well-known/agent-card.json` is served by a dynamic route
that rewrites the advertised A2A URL per tenant from the `Host` /
`Apx-Incoming-Host` headers (trusting `X-Forwarded-Proto` for the scheme).

## The backwards-compatibility edge

Two middlewares translate older wire dialects into the current request shape.
Both exist **at the edge** for the same reason: our Pydantic request models
parse strictly (and in production ignore unknown fields), so by the time a
model exists, an unrecognised or renamed field is already gone — the only
place a translation can see the buyer's original spelling is before parsing.
Putting it anywhere else would either lose the data or force every `_impl` to
speak every historical dialect. Both delegate the actual field mapping to the
shared normaliser in `src/core/request_compat.py`, so REST and MCP accept the
same dialects by construction.

**`RestCompatMiddleware`** (`src/routes/rest_compat_middleware.py`): for JSON
`POST`s to the `/api/v1/` endpoints it knows (`/products`, `/media-buys`,
`/creatives/sync`), it stashes the raw body bytes for idempotency hashing,
runs `normalize_request_params` for the corresponding tool, and swaps the
request body for the normalised JSON so FastAPI's model parsing sees
current-version field names. Malformed JSON is passed through untouched for
FastAPI to reject with the proper envelope.

**`RequestCompatMiddleware`** (`src/core/mcp_compat_middleware.py`), the MCP
counterpart, is a three-stage pipeline on every tool call:

1. Translate deprecated field names (`normalize_request_params`).
2. In **production only**, strip fields that are not in the tool's JSON
   Schema — callers on newer schema versions are not rejected. In dev/CI,
   unknown fields flow through to fail loudly, which is how a missing field
   in our own schema gets noticed.
3. If FastMCP's TypeAdapter still rejects the arguments: in production, retry
   once after deep-stripping schema-unknown *nested* fields; if it still
   fails (or in dev), translate the validation failure into the AdCP
   validation envelope and record it via `record_boundary_error`.

The raw, untranslated payload is always captured *before* these rewrites
(`request.state.raw_wire_payload` on REST, the `raw_wire_payload` context
state on MCP), because AdCP defines idempotency payload-equivalence over the
request **as the buyer sent it** — a seller-side compat-table change must not
flip an honest retry into a conflict.

## Where the path ends: the `_impl` handoff

Everything above exists to produce two things: a validated, current-shape
request object and a `ResolvedIdentity`. At that point the transport's job is
done and Critical Pattern #5 ([CLAUDE.md](../../CLAUDE.md), and
[patterns-reference.md](patterns-reference.md)) takes over:

- The wrapper calls the shared `_impl` function with the request and the
  `ResolvedIdentity` — never a `Context`, `ToolContext`, or raw headers.
- `_impl` is transport-agnostic: zero imports from fastmcp/a2a/starlette/
  fastapi, raises typed `AdCPError` subclasses, returns model objects.
- The boundary translates the result and any `AdCPError` back into the
  transport's wire shape (REST envelope + HTTP status, MCP `isError` tool
  error, A2A failed Task) — symmetrically, via the shared envelope builders
  and `record_boundary_error`.

Structural guards enforce this seam
([structural-guards.md](structural-guards.md)):
`test_transport_agnostic_impl.py`, `test_impl_resolved_identity.py`,
`test_no_toolerror_in_impl.py`, `test_architecture_boundary_completeness.py`.

## Where does my change go?

| You want to… | It belongs in | Not in |
|---|---|---|
| Read a new HTTP header for all transports | `resolve_identity` / `_detect_tenant` (identity-related), or the relevant boundary helper — headers reach every boundary | `_impl` (never sees headers) |
| Accept a renamed/deprecated request field | The shared normaliser, `src/core/request_compat.py` — both compat middlewares pick it up | Route handlers, tool wrappers, `_impl` |
| Add an auth rule (who may call at all) | REST: `require_auth`/`resolve_auth` deps; MCP: `MCPAuthMiddleware` / `AUTH_OPTIONAL_TOOLS`; A2A: `_resolve_a2a_identity` | Scattered checks inside `_impl` |
| Add an authorization rule (what this principal may do) | `_impl`, using `ResolvedIdentity` (helpers in `src/core/auth.py`: `require_identity`, `require_tenant`) | Middleware (too early — no business context) |
| Add a tenant-resolution strategy | `_detect_tenant` in `src/core/resolved_identity.py` | Per-transport code |
| Add a field to what business logic knows about the caller | `ResolvedIdentity` + populate it in `resolve_identity` | Passing extra transport args into `_impl` |
| Change how an error looks on the wire | The boundary translators: `src/app.py` exception handlers (REST), `src/core/tool_error_logging.py` (MCP), the A2A dispatcher | `_impl` (raises typed `AdCPError`, nothing else) |
| Add a REST endpoint for an existing tool | `src/routes/api_v1.py`, calling the existing `_raw`/`_impl` | New business logic in the route |
| Log/audit a boundary event | `record_boundary_error` (errors) or the boundary itself | `_impl` |
| Touch request/response bodies globally | An ASGI middleware in `src/app.py` — mind the last-registered-is-outermost order | Route handlers |

One legacy note: `src/core/mcp_context_wrapper.py` (and
`src/core/mcp_server_enhanced.py`, its only consumer) are legacy and not wired
into the live MCP path — new work follows the `MCPAuthMiddleware` +
`ctx.get_state("identity")` flow above.

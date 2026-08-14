# SB-2a: transport-generic AdCP test client — design

beads: `salesagent-xxa1` (design, this doc). Implementation is
`salesagent-geru` (SB-2b), not this task. Epic: `salesagent-xg5w`.

## 1. The problem, grounded in the actual code

The harness (`tests/harness/`) has 33 env classes (`ls tests/harness/*.py`
minus `_base.py`/`_mixins.py`/`_realize.py`/`dispatchers.py`/`transport.py`)
carrying 64 dispatch methods total (`call_a2a` + `call_mcp` +
`build_rest_body` + `parse_rest_response` + `call_impl`/`call_rest`,
grep-counted across `tests/harness/*.py`). Every one of those methods does
the same three things in a different vocabulary:

1. **ADDRESS** — pick the tool name (MCP), skill name (A2A), or route
   (REST) to call.
2. **WRAP** — turn the kwargs / `req=` object into that transport's
   envelope (FastMCP `call_tool(name, arguments)`, an A2A `Message` with a
   `{"skill":..., "parameters":...}` data Part, an HTTP JSON body).
3. **UNWRAP** — turn the transport's response envelope back into the AdCP
   response payload (`ToolResult.structured_content`, an A2A artifact
   DataPart with `message`/`success` stripped, an HTTP JSON body).

`MediaBuyDualEnv` (`tests/harness/media_buy_dual.py`) is the reductio. Read
in full for this design — key facts from it:

- `_is_update_request(kwargs)` (line 34) guesses "is this a create or an
  update?" from **the Python type of the `req` kwarg**
  (`isinstance(req, UpdateMediaBuyRequest)`) — tool identity is inferred
  from call-site shape, not addressed directly.
- `_active_update` (line 152) is instance state whose lifetime spans two
  separate dispatcher calls — `_run_rest_request` (line 103) sets it,
  `parse_rest_response` (line 146) is the only thing that resets it. The
  class's own comment (lines 104-109) documents a **past bug**: a
  `finally`-based reset flipped the flag back before `parse_rest_response`
  ran, silently misrouting the update response through the create parser
  and yielding `None`. `build_rest_body` (line 115-129) has to duplicate
  the flag-setting because the E2E dispatcher (`RestE2EDispatcher`) never
  calls `_run_rest_request` at all — it reads `REST_ENDPOINT`/`REST_METHOD`
  as plain attributes and calls `build_rest_body` directly (comment at
  line 116-119). Two different call graphs need the same mutable flag set
  correctly, by hand, in two places.
- `REST_ENDPOINT` and `REST_METHOD` (lines 131-144) are `@property`, not
  class attrs, purely so they can consult `_active_update` — i.e. the
  "address" of the REST call is not knowable until dispatch-time
  side-effecting state has been threaded through.
- Six wrapper methods (`_call_update_impl`, `_call_update_a2a`,
  `_call_update_mcp`, `_build_update_rest_body`, `_run_update_rest_request`,
  `_parse_update_rest_response`) exist purely to re-derive, per transport,
  what `create_media_buy`'s sibling methods on `MediaBuyCreateEnv` already
  derive for the create path — same shape of work, second tool.

This is not a one-off — it is what every env in `tests/harness/` looks
like at smaller scale (`MediaBuyCreateEnv.call_a2a`/`call_mcp`/
`build_rest_body`/`parse_rest_response`, `tests/harness/media_buy_create.py`
lines 372-434, do the same three things for exactly one tool).

## 2. What is actually invariant vs. what varies

Read `tests/harness/dispatchers.py` and `tests/harness/_base.py`
(`_run_a2a_handler`, `_run_mcp_client`, `_run_rest_request`) end to end.
The **real** per-transport variability is small and is not "one tool at a
time" — it is one function per transport, total:

| Transport | ADDRESS (tool → address) | WRAP (payload → wire request) | UNWRAP (wire response → payload) |
|---|---|---|---|
| MCP | tool name string, must equal a name in `mcp.list_tools()` | `dict` of kwargs — this **is** the FastMCP `call_tool` arguments dict, no transformation | `ToolResult.structured_content` (already a flat dict) |
| A2A | skill id string, must equal an `AgentSkill.id` in `create_agent_card()` | `{"skill": name, "parameters": payload}` packed into a protobuf `Struct` inside a `Message` `Part.data` (`create_a2a_message_with_skill`, `tests/utils/a2a_helpers.py:67`) | artifact `Part.data` parsed via `json_format.MessageToJson` (`extract_data_from_artifact`, same file, line 39), then strip the two protocol keys `message`/`success` that `_serialize_for_a2a` adds (`adcp_a2a_server.py:1445-1457`) |
| REST | `(method, path_template)` pair, must equal a route registered on `router` in `src/routes/api_v1.py`, keyed by `route.endpoint.__name__ == tool_name` for all but one handler (see correction below) | JSON body = `payload` minus whichever payload keys the path template consumes as path params (e.g. `media_buy_id` for `PUT /media-buys/{id}`) | `response.json()` — already the flat response dict; every `api_v1.py` handler does `return response.model_dump(mode="json")` |

Confirmed by direct inspection, not assumed:

```python
>>> from fastapi import FastAPI, APIRouter
>>> # ... build app with api_v1's router ...
>>> for route in app.routes:
...     if route.path.startswith("/api/v1"):
...         print(route.path, route.methods, route.endpoint.__name__)
/api/v1/media-buys {'POST'} create_media_buy
/api/v1/media-buys/{media_buy_id} {'PUT'} update_media_buy
```

`route.endpoint.__name__` is literally the tool name, for every route in
`api_v1.py` EXCEPT ONE — every handler function is named after the tool it
wraps (`create_media_buy`, `update_media_buy`, `get_media_buy_delivery`,
`sync_creatives`, `list_creatives`, `update_performance_index`,
`list_accounts`, `sync_accounts`, `get_products`, `list_creative_formats`,
`list_authorized_properties`) — but `get_capabilities` is the REST handler
name for the `get_adcp_capabilities` AdCP tool, not a tool name in its own
right (a naming drift the original design missed, fixed by
salesagent-vuz9t.9: `tests/harness/address_table.py`'s `REST_TOOL_ALIASES`
resolves this one known mismatch explicitly, and any NEW unresolved
divergence now raises `UnresolvedRestHandlerName` at table-build time
instead of silently registering under the wrong name). Same story for MCP:
`_register_tool(fn)` in `src/core/main.py:339-348` calls
`mcp.tool(**kwargs)(with_error_logging(fn))` where `fn.__name__` becomes
the registered tool name, so `mcp.list_tools()` (async, returns
`Sequence[Tool]` with `.name`) enumerates exactly the address table MCP
dispatch needs, straight from the object the server itself uses to route
calls — no parallel hand-maintained list. Same for A2A:
`create_agent_card()` (`src/a2a_server/adcp_a2a_server.py:2227`) returns
`AgentCard(skills=[AgentSkill(id=..., name=...), ...])`, and each `id`
matches a key in the `skill_handlers` dict inside
`_handle_explicit_skill` (line 1517) that the production server itself
dispatches on. The agent card is served to real buyers over the wire, so
reading it is reading the same source production uses to advertise itself
— not a second copy that can drift.

**Important asymmetry to flag for the implementer:** A2A's `skill_handlers`
dict has more entries than either MCP's tool set or REST's route set
(`create_creative`, `assign_creative`, `approve_creative`,
`get_media_buy_status`, `optimize_media_buy` exist only on A2A). The
address-derivation code must treat "tool has no address on transport X" as
an expected, per-tool-per-transport possibility, not an error — `client.call`
should raise a clear `NoAddressForTransport` (or similar) rather than KeyError
when a scenario asks for a tool/transport combination that doesn't exist in
production. That is itself useful conformance information (it tells you a
scenario is scoped to fewer transports than the default 3), not a bug to
paper over.

## 3. Client API

```python
# tests/harness/client.py (new file, SB-2b builds it)

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from tests.harness.transport import Transport, TransportResult


class NoAddressForTransport(LookupError):
    """Tool has no registered address on the requested transport (expected — not every
    tool exists on every transport, e.g. A2A-only skills like approve_creative)."""


@dataclass(frozen=True)
class ToolAddress:
    """One transport's resolved address for one tool. Frozen/hashable — safe to cache."""
    transport: Transport
    # MCP: tool name. A2A: skill id. REST: (method, path_template).
    name: str
    path_template: str | None = None   # REST only
    method: str | None = None          # REST only


class AdCPTestClient:
    """One client, all transports, in-process and e2e — see §5 for why one client
    covers both. Constructed per-env (it needs the env's identity + factory-bound
    session + e2e_config, exactly what BaseTestEnv already carries), NOT a global
    singleton — the address map it derives is process-wide and cached at module
    scope (see AddressTable below), but auth/session/e2e state is per-scenario.
    """

    def __init__(self, env: "BaseTestEnv") -> None:
        self._env = env

    def call(
        self,
        tool: str,
        payload: dict[str, Any],
        transport: Transport,
        *,
        identity: Any = None,   # sentinel-default: falls back to env.identity_for(transport)
    ) -> TransportResult:
        """Address → wrap → deliver → unwrap → TransportResult.

        Returns the SAME TransportResult shape dispatchers.py already returns
        (payload / envelope / error / wire_response / wire_error_envelope /
        synthesized_error_envelope) — every existing Then-step helper
        (`result.assert_wire_error`, `assert_envelope_shape`) keeps working
        unmodified whether `result` came from `env.call_via` or `client.call`.
        """
        address = ADDRESS_TABLE.resolve(tool, transport)  # raises NoAddressForTransport
        wrapped = WRAP[transport](address, payload)
        raw = DELIVER[transport](self._env, address, wrapped, identity)
        return UNWRAP[transport](raw)
```

Concrete call shapes an implementer/step-author would write:

```python
# In-process MCP dispatch of create_media_buy:
result = client.call("create_media_buy", {"packages": [...], "idempotency_key": "..."}, Transport.MCP)

# e2e REST dispatch of update_media_buy (media_buy_id is a payload key that the
# REST WRAP function knows — from the address's path_template — to peel into the URL):
result = client.call("update_media_buy", {"media_buy_id": "mb_1", "paused": True}, Transport.E2E_REST)
```

`payload` is always **the AdCP request payload as a flat dict** — the same
shape `req.model_dump(mode="json", exclude_none=True)` already produces
across every env's `build_rest_body`/`_flatten_request`. This is the
ticket's "request payload (AdCP request schema) → transport envelope →
response envelope → response payload" contract made literal: `payload` in,
`TransportResult.payload`-bearing-a-parsed-response out, and the three
WRAP/ADDRESS/UNWRAP functions are the only per-transport code.

## 4. Address-mapping derivation (not hand-maintained)

The sketch below is the ORIGINAL SB-2b proposal; `_index_rest` in the real
file has since grown `REST_TOOL_ALIASES`/`REST_ABSENT_TOOLS`/
`UnresolvedRestHandlerName` (salesagent-vuz9t.9) because `tool_name =
route.endpoint.__name__` — unmodified — silently mis-registered
`get_capabilities` and degraded four genuinely-REST-absent tools into an
indistinguishable "not found." Read `tests/harness/address_table.py`
directly for the current behavior; this block is kept as the historical
proposal, not the implementation.

```python
# tests/harness/address_table.py (new file, SB-2b builds it)

class AddressTable:
    """Built once per process from the THREE live registration objects — never
    a hand-maintained dict. Rebuilding it costs nothing (no I/O); doing it lazily
    at first use avoids import-order issues with src.core.main / src.app.
    """

    def __init__(self) -> None:
        self._by_tool_transport: dict[tuple[str, Transport], ToolAddress] = {}
        self._built = False

    def _build(self) -> None:
        self._index_mcp()
        self._index_a2a()
        self._index_rest()
        self._built = True

    def _index_mcp(self) -> None:
        import asyncio
        from src.core.main import mcp
        for tool in asyncio.run(mcp.list_tools()):
            for t in (Transport.MCP, Transport.E2E_MCP):
                self._by_tool_transport[(tool.name, t)] = ToolAddress(t, name=tool.name)

    def _index_a2a(self) -> None:
        from src.a2a_server.adcp_a2a_server import create_agent_card
        for skill in create_agent_card().skills:
            for t in (Transport.A2A, Transport.E2E_A2A):
                self._by_tool_transport[(skill.id, t)] = ToolAddress(t, name=skill.id)

    def _index_rest(self) -> None:
        from src.app import app
        for route in app.routes:
            if not getattr(route, "path", "").startswith("/api/v1"):
                continue
            tool_name = route.endpoint.__name__
            method = next(iter(route.methods - {"HEAD"})).lower()
            for t in (Transport.REST, Transport.E2E_REST):
                self._by_tool_transport[(tool_name, t)] = ToolAddress(
                    t, name=tool_name, path_template=route.path, method=method
                )

    def resolve(self, tool: str, transport: Transport) -> ToolAddress:
        if not self._built:
            self._build()
        key = (tool, transport)
        if key not in self._by_tool_transport:
            raise NoAddressForTransport(f"{tool!r} has no registered address on {transport}")
        return self._by_tool_transport[key]


ADDRESS_TABLE = AddressTable()  # module-level singleton, lazily built
```

Every source read here is something production *already calls to route
real traffic or advertise itself to real buyers* — `mcp.list_tools()` is
what a real MCP client sees, `create_agent_card()` is what a real A2A
buyer's discovery request receives, `app.routes` is FastAPI's own
dispatch table. There is no fourth, hand-maintained list of TOOLS to keep
in sync; a tool added to any of the three registration sites becomes
callable through the client automatically, and a tool the implementer
*forgot* to register on a transport shows up as `NoAddressForTransport`
instead of silently existing in a stale test-only map. (Correction,
salesagent-vuz9t.9: a REST handler's Python function name is not always
the tool name — see `REST_TOOL_ALIASES` above — so a SMALL, reviewed,
shrink-only alias map is unavoidable for that one axis; it is not a
hand-maintained TOOL list, but it is hand-maintained naming metadata, and
an unresolved divergence fails table construction loudly rather than
degrading into a silent miss.)

`path_template` handling for REST WRAP: extract `{name}` groups from the
template with a regex (`re.findall(r"\{(\w+)\}", path_template)`); any
payload key matching a captured group name is popped from the JSON body
and substituted into the URL. This generalizes what
`MediaBuyDualEnv._run_update_rest_request` currently hand-codes
(`endpoint = f"/api/v1/media-buys/{media_buy_id}"`, `body.pop("media_buy_id")`
implicitly via `req.model_dump()` never including it) into one rule that
covers every current and future path-parameterized route without a
per-tool branch.

## 5. Why one client serves both in-process and e2e

Per the ticket: in-process and e2e differ **only in delivery** — same
ADDRESS, same WRAP, same UNWRAP; only the "how do bytes actually reach the
server" step (call a Python function in-process vs. send real HTTP over
the network) differs. Concretely:

| Transport | in-process DELIVER | e2e DELIVER |
|---|---|---|
| MCP | `fastmcp.Client(mcp)` in-memory transport (`_run_mcp_client`, `_base.py:754`) | same `Client`, but constructed against a real network URL instead of the in-memory `mcp` app object — not yet implemented (`McpE2EDispatcher` placeholder, `dispatchers.py:335`) |
| A2A | `AdCPRequestHandler().on_message_send(...)` called directly (`_run_a2a_handler`, `_base.py:601`) | same message, POSTed as JSON-RPC over real HTTP to the live A2A endpoint — not yet implemented (`A2AE2EDispatcher` placeholder, `dispatchers.py:344`) |
| REST | `starlette.testclient.TestClient(app)` — in-process ASGI call, no sockets | `httpx.Client(base_url=env.e2e_config.base_url)` — real sockets through nginx to the Docker stack (`RestE2EDispatcher`, `dispatchers.py:231`, already implemented) |

So `DELIVER[transport]` is a small dict of functions keyed by `Transport`,
each taking `(env, address, wrapped_request, identity)` and returning the
transport's raw response object (`ToolResult`, `Task`, `httpx.Response`).
WRAP and UNWRAP are **transport-family** functions (one for MCP covering
both `Transport.MCP` and `Transport.E2E_MCP`; one for A2A covering both
A2A variants; one for REST covering both REST variants) — they do not
know or care whether delivery is in-process or over the wire, because the
wire format is identical either way (a FastMCP tool call looks the same
whether the transport underneath is in-memory or HTTP; an HTTP JSON body
is an HTTP JSON body whether TestClient or httpx sent it). This is exactly
why `RestE2EDispatcher` today already reuses `env.build_rest_body` /
`env.REST_ENDPOINT` / `env.parse_rest_response` from the in-process env
(`dispatchers.py:238-241`, explicit comment) — the client design promotes
that reuse from "one class happens to share methods with its parent" to
"WRAP/UNWRAP are the literal same function object for both variants,
looked up once by transport **family**." Implementing `McpE2EDispatcher`
and `A2AE2EDispatcher` for real becomes: write the `DELIVER` function for
that transport (open a real socket, or a real `Client` against a URL) —
WRAP and UNWRAP need zero new code, because they were never in-process-
specific to begin with once factored out of the 33 envs.

## 6. Migration story — additive, per-UC, only when already editing it

**Envs keep**: `EXTERNAL_PATCHES`/`ASYNC_PATCHES`/`_configure_mocks`
(mocking), all `setup_*`/`seed_*` factory-seeding methods, `identity_for`/
`switch_principal`/`switch_tenant`, `get_session`/`query`/`get_one` (DB
read-back), `realize_e2e` (`tests/harness/_realize.py`), `clock`. That is
the 34 "seeding methods" the ticket refers to — none of it is
transport-shaped, all of it stays exactly as-is.

**Envs lose** (once a UC migrates): `call_a2a`, `call_mcp`,
`build_rest_body`, `parse_rest_response`, `_run_*_request`/`_flatten_*`
helpers, `REST_ENDPOINT`/`REST_METHOD` overrides — i.e. everything
`MediaBuyDualEnv` adds beyond `MediaBuyCreateEnv.call_impl`, and everything
`MediaBuyCreateEnv` adds beyond `IntegrationEnv`.

**Where migration happens, concretely**: the seam is
`tests/bdd/steps/generic/_dispatch.py:dispatch_request` — today it calls
`env.call_via(transport, **kwargs)`. A migrated UC's step file calls
`client.call(tool, payload, transport)` instead, still inside the same
`with env:` block, still using the env for every Given step. `env.call_via`
and the 33 envs' dispatch methods keep existing for every UC that hasn't
migrated — nothing is deleted from `_base.py`/`dispatchers.py` on day one.

**Before** (`tests/bdd/steps/domain/uc002_create_media_buy.py`, current):

```python
def _dispatch_full_create(ctx: dict) -> None:
    req = CreateMediaBuyRequest(**ctx.get("request_kwargs", {}))
    from tests.bdd.steps.generic._dispatch import dispatch_request
    dispatch_request(ctx, req=req)   # → env.call_via(transport, req=req)
                                      #   → env.call_a2a/call_mcp/build_rest_body
                                      #     + parse_rest_response, all hand-written
                                      #     on MediaBuyCreateEnv
```

**After** (same file, once someone is already touching UC-002 for another
reason):

```python
def _dispatch_full_create(ctx: dict) -> None:
    req = CreateMediaBuyRequest(**ctx.get("request_kwargs", {}))
    payload = req.model_dump(mode="json", exclude_none=True)
    client = ctx["client"]  # constructed once per scenario alongside env, see below
    result = client.call("create_media_buy", payload, ctx["transport"])
    ctx["result"] = result
    if result.is_error:
        ctx["error"] = result.error
        ctx["wire_error_envelope"] = result.wire_error_envelope
    else:
        ctx["response"] = result.payload
        ctx["wire_response"] = result.wire_response
```

Everything below `_dispatch_full_create` in that file — every `given_*`
step that seeds tenant/product/account state via `env`, every `then_*`
step reading `ctx["result"]`/`ctx["wire_error_envelope"]` — is untouched.
The conftest fixture that builds `ctx["env"]` additionally builds
`ctx["client"] = AdCPTestClient(env)` (one extra line per UC's conftest
wiring); `MediaBuyCreateEnv` itself sheds `call_a2a`/`call_mcp`/
`build_rest_body`/`parse_rest_response` only once every step file that
constructed a `CreateMediaBuyRequest` and called `dispatch_request` has
been converted — until then the env keeps both paths (its own dispatch
methods AND being a valid `AdCPTestClient` constructor argument)
side by side, so a partially-migrated UC file is never broken.

**Non-goals** (ticket, restated explicitly so SB-2b does not scope-creep):
this design does **not** rewrite the 2,684 existing scenarios or the 1,450
existing step definitions — they stay exactly as they are, dispatching
via `env.call_via` through the 33 envs, for as long as nobody is already
editing them for an unrelated reason. `client.call` is a second, additive
path, not a replacement mandate.

## 7. Open questions / risks for SB-2b's implementer

- **`ext=` / non-schema kwargs.** A few current step files pass ad-hoc
  kwargs that are neither `req=` fields nor identity (e.g.
  `raw_wire_payload=` on `create_media_buy_raw`, used for idempotency
  hash verification — `api_v1.py:339`). `client.call`'s `payload` dict
  needs a documented escape hatch (or these stay on the env-based path
  until the escape hatch is designed) — don't silently drop them.
- **A2A push-notification injection.** `_handle_explicit_skill` special-
  cases `push_notification_config` for exactly two skills
  (`adcp_a2a_server.py:1491`) by mutating `parameters` before dispatch.
  That is production behavior a test client must reproduce in A2A's WRAP
  function (not invent independently) — cite this exact line when
  building it, don't re-derive from the AdCP spec alone.
- **REST body ≠ raw request model 1:1.** `api_v1.py`'s per-route Pydantic
  `Body` classes (`CreateMediaBuyBody`, `UpdateMediaBuyBody`, ...) are
  hand-declared and drift from the AdCP request schema on purpose in
  places (e.g. `paused` is declared on `CreateMediaBuyBody` but explicitly
  **not forwarded** to the raw wrapper — comment at `api_v1.py:90-92`,
  `#1619`). REST's WRAP function sends `payload` as JSON and lets FastAPI/
  Pydantic validate against the real `Body` class — it must not assume
  the wire body accepts every field the AdCP schema does. A payload key
  the REST body model rejects should surface as a real 422, not a client-
  side KeyError — verify this against a scenario that exercises exactly
  this drift (`paused` is a ready-made one).
  Cross-reference: no other transport-behavior claims required a spec
  citation for this design task itself (it is harness plumbing, not
  protocol behavior) — but SB-2b's actual WRAP implementations, wherever
  they encode a per-transport quirk like this one, should cite the
  production line that quirk mirrors, the same way this section does.
- **`_last_wire_response`/`_last_a2a_task` side channels.** `BaseTestEnv`
  stashes extra state on itself (`_last_wire_response`,
  `_last_a2a_task`) that a few Then-steps read directly
  (`env.last_a2a_task`, `tests/CLAUDE.md` "submitted contract"). If
  `client.call` bypasses `env.call_via`, it must populate these same env
  attributes (or the client needs its own equivalent surfaced via
  `TransportResult`) — otherwise a migrated UC silently loses the
  Task-level submitted-contract assertions that currently work.
- **Two placeholder E2E dispatchers.** `McpE2EDispatcher` and
  `A2AE2EDispatcher` (`dispatchers.py:335-350`) raise
  `NotImplementedError` today. This design's DELIVER-function split
  makes implementing them tractable (§5), but SB-2b should decide
  whether landing that real implementation is in scope for SB-2b itself
  or a follow-up — the client design does not require it to land first.
- **Address caching invalidation.** `ADDRESS_TABLE` is built once (lazy,
  module-level). Nothing today reloads `mcp`/`app`/`create_agent_card()`
  mid-test-run, so this should be safe, but confirm no existing test
  monkey-patches tool registration at runtime before relying on the cache
  across a whole `pytest` session.

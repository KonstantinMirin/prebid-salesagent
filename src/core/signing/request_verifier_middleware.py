"""The ONE inbound RFC 9421 verifier — a pure-ASGI middleware over MCP, A2A and REST.

#1291 B1 (salesagent-z6nr.12).

Core invariant
--------------
Exactly one middleware, registered inside :class:`~src.core.auth_middleware.UnifiedAuthMiddleware`
and scoped by an allowlist of the three AdCP surfaces, decides every inbound signature
outcome — and it decides it by *choosing whether to call* the SDK's unconditional
``verify_request_signature`` and whether to swallow its exception. It never
reimplements a checklist step, never reorders one, and never reads a posture from
anywhere but the single per-request :class:`~src.core.signing.posture.RequestSigningPosture`
that D1 will also serialize to the wire.

``src/app.py`` is a single composition root — the MCP app is a Mount, the A2A routes
are appended to ``app.routes``, and the REST router is included — so one middleware
here really does cover all three transports. Three per-transport hooks would be the
duplication class CLAUDE.md's DRY invariant exists to prevent, and they would drift the
moment one transport's error mapping changed.

Why pure ASGI and not ``BaseHTTPMiddleware``
--------------------------------------------
``BaseHTTPMiddleware`` has the ContextVar propagation bug (Starlette #1729) and, more
importantly here, it sits on the RESPONSE path: it wraps the downstream app in a task
and pumps its response through a queue, which is what breaks MCP's streamable-HTTP and
SSE responses. This class touches the request and then gets out of the way — on the
pass-through and the warn paths it does not observe the response at all.

Placement (R-H2 — the half that actually breaks verification)
--------------------------------------------------------------
Execution order is CORS -> UnifiedAuth -> **verifier** -> RestCompat -> a2a messageId
-> router, and both halves are load-bearing:

* INSIDE ``UnifiedAuthMiddleware``, because the spec's composition rule decides the
  ``required_for`` rejection on whether the caller's bearer resolves to a principal we
  accept;
* OUTSIDE ``RestCompatMiddleware`` and the a2a messageId middleware, because BOTH
  REWRITE THE REQUEST BODY. ``RestCompatMiddleware`` sets ``request._body`` to
  normalized JSON for POST ``/api/v1/{products,media-buys,creatives/sync}``, and
  Starlette's ``_CachedRequest.wrapped_receive`` hands those bytes verbatim downstream —
  so a verifier placed inside it would hash bytes the signer never signed, and the
  collision lands on ``/api/v1/media-buys`` = ``create_media_buy``, the spend-committing
  operation the spec pushes toward ``covers_content_digest: "required"``.

``tests/unit/test_architecture_request_signature_middleware.py`` pins the order
structurally; ``tests/integration/test_request_signature_middleware.py`` grades the
body-bytes property behaviorally.

Per-request sequence
--------------------
1. Non-HTTP scope, non-AdCP path, or the kill switch off -> pass through untouched.
   The allowlist (not a denylist) is what permanently exempts A3's trust-root
   documents: a verifier in front of ``/.well-known/jwks.json`` is a bootstrap
   deadlock, because that document is how a counterparty obtains the key it would need
   in order to sign. ``tests/unit/test_architecture_request_signature_middleware.py``
   ties the allowlist to ``app.routes`` so a NEW AdCP surface cannot ship silently
   unverified (R-M4).
2. Thread hop #1: resolve the tenant -> its posture -> the bucket for this operation,
   and (only when the decision needs it) the bearer -> ``Principal`` -> ``agent_url``.
   The bucket is resolved BEFORE any body is buffered (R-H3): under the ``none`` bucket
   two junk headers would otherwise buy a buffer, a DB round trip and an Ed25519 verify
   whose result is then discarded.
3. Signature headers absent -> the composition rule (below). Present -> buffer the body
   with a replay ``receive``.
4. Async: the counterparty's :class:`~adcp.signing.agent_resolver.AgentResolution` from
   the process cache, resolved on a cold entry. The WHOLE resolution is cached — jwks +
   jwks_uri + key_origins — because ``expected_key_origins`` must be handed to every
   verify or the spec's step-7 key-origin check silently no-ops with a warning (R-M2).
5. Thread hop #2: the Postgres replay store and the synchronous
   ``verify_request_signature`` over ONE session checkout, per A4's wiring contract
   (``src/core/signing/replay_store.py``). Called directly with method/url/headers/body
   rather than through ``verify_starlette_request`` (R-M3), because the wrapper derives
   the URL from the scope and would discard the explicit ``X-Forwarded-Proto``
   derivation.

Three-way header pre-check
--------------------------
Both headers absent, exactly one present, and both present are three different
outcomes, and only the third is a question the SDK can be asked: its
``_precheck_presence`` raises ``request_signature_required`` on the absent branch
UNCONDITIONALLY, which is the strict reading the spec normatively rejects. So:

* both absent -> the composition rule (``security.mdx`` @ v3.1.1 :1268-1271). An
  UNAUTHENTICATED request to a ``required_for`` operation is rejected; an unsigned but
  otherwise authenticated one MUST NOT be rejected for the missing signature. :1289
  names the failure the strict reading produces — "a seller enabling ``required_for``
  for operational monitoring would inadvertently 401 every bearer-authed buyer" — and
  salesagent is bearer-authenticated on every AdCP request, so the strict reading would
  reject essentially all production traffic the moment D1 populates ``required_for``.
* exactly one present -> hand it to the SDK, which raises
  ``request_signature_header_malformed``. A malformed signature blocks the bearer
  fallback regardless of the bucket (:1226, :1271): a present-but-broken signature
  signals signer intent and must not downgrade silently.
* both present -> the checklist runs.

Rejections are a TRANSPORT-layer 401 carrying
``WWW-Authenticate: Signature error="<code>"`` (realm intentionally omitted), built by
the SDK's ``unauthorized_response_headers``. They sit at the ASGI boundary, outside the
``AdCPError`` -> wire-envelope cascade, and are SENT rather than raised: FastAPI's
exception handlers are inner, so a raise here becomes a 500 in ``ServerErrorMiddleware``.
Every code is spec-defined; this module invents none.

Spec grounding: AdCP 3.1.1 via ``adcp==6.6.0``;
``v3.1.1:dist/docs/.../L1/security.mdx`` and
``v3.1.1:dist/compliance/3.1.1/universal/signed-requests.yaml`` (12 positive / 28
negative vectors, graded on 2xx / 401 + the ``WWW-Authenticate`` code byte-for-byte).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, cast

from adcp.signing.agent_resolver import AgentResolution, AgentResolverError, BrandAgentType, async_resolve_agent
from adcp.signing.errors import REQUEST_SIGNATURE_REQUIRED, SignatureVerificationError
from adcp.signing.jwks import StaticJwksResolver
from adcp.signing.middleware import unauthorized_response_headers
from adcp.signing.verifier import VerifiedSigner, VerifierCapability, VerifyOptions, verify_request_signature
from starlette.responses import Response

from src.core.auth_context import AUTH_CONTEXT_STATE_KEY
from src.core.config import SigningConfig, get_config
from src.core.database.database_session import get_db_session
from src.core.database.repositories.principal import PrincipalRepository
from src.core.database.repositories.replay_nonce import ReplayNonceRepository
from src.core.http_utils import headers_from_asgi_scope
from src.core.metrics import record_request_unsigned, record_signature_failed, record_signature_verified

# ``_detect_tenant`` is the Host/x-adcp-tenant resolution ladder every transport
# boundary already uses, and it is the right call here precisely because it never
# reads the token: it cannot 401 for an auth reason. ``resolve_identity`` would —
# it validates the credential and raises, which at this layer would turn an auth
# failure into a signature rejection.
from src.core.resolved_identity import _detect_tenant, _extract_auth_token
from src.core.signing.operations import OperationResolver, UnresolvedOperationResolver
from src.core.signing.posture import (
    PostureBucket,
    RequestSigningPosture,
    posture_for_tenant,
    request_signing_is_declarable,
)
from src.core.signing.replay_store import PostgresReplayStore

logger = logging.getLogger(__name__)

Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

#: The AdCP protocol surfaces, and ONLY those. Everything else — admin, health, debug,
#: the landing page, the A2A agent card and every A3 trust-root document — passes
#: through untouched by construction rather than by remembering to exempt it.
#: Prefix + segment boundary, so ``/api/v1x`` cannot sneak in.
#:
#: Note ``/a2a/`` (trailing slash) only 307-redirects to ``/a2a``; it matches the
#: allowlist and is verified before being bounced, which is harmless.
ADCP_SURFACE_PREFIXES: tuple[str, ...] = ("/mcp", "/a2a", "/api/v1")

#: Process-level ``{agent_url: AgentResolution}``. The WHOLE resolution is kept, not
#: just the JWKS: ``expected_key_origins`` comes from it and is mandatory on every
#: verify for brand-json-sourced keys (R-M2). Entries expire by
#: ``SigningConfig.agent_resolution_ttl_seconds`` against ``AgentResolution.fetched_at``.
AGENT_RESOLUTION_CACHE: dict[str, AgentResolution] = {}

#: ``{agent_url: last failure time}``. Without it, every signed request from a
#: counterparty with a broken brand.json starts a fresh 3-hop outbound walk.
_RESOLUTION_FAILURES: dict[str, float] = {}

#: The purpose key under the counterparty's ``identity.key_origins`` map.
_SIGNING_PURPOSE = "request_signing"


class _BrandJsonJwksResolver(StaticJwksResolver):
    """A resolver that tells the verifier its keys came from the brand.json walk.

    The SDK engages the spec's step-7 key-origin consistency check ONLY for resolvers
    advertising ``jwks_source = "brand_json"`` and exposing the resolved ``jwks_uri``;
    a plain :class:`~adcp.signing.jwks.StaticJwksResolver` is treated as a
    publisher-pinned tuple and skips the check with nothing but a warning. Declaring
    the conformance is documented adopter API (``adcp.signing.BrandSourcedJwksResolver``).
    """

    jwks_source = "brand_json"

    def __init__(self, jwks: dict[str, Any], *, jwks_uri: str) -> None:
        super().__init__(jwks)
        self.jwks_uri = jwks_uri


@dataclass(frozen=True)
class _RequestContext:
    """What thread hop #1 resolved: the seller's posture and the caller's identity."""

    posture: RequestSigningPosture
    bucket: PostureBucket
    tenant_id: str | None
    principal_id: str | None
    agent_url: str | None

    @property
    def authenticated(self) -> bool:
        """Whether the bearer resolved to a principal this deployment accepts.

        This is the third term of the spec's three-way AND at :1224 — "…AND the caller
        presents no other credential the verifier accepts" — and the only thing that
        separates the 401 branch from the pass-through branch on an unsigned request.
        """
        return self.principal_id is not None


@dataclass(frozen=True)
class _BufferedBody:
    """A fully-read request body plus a ``receive`` that replays it downstream."""

    body: bytes
    receive: Receive
    complete: bool
    over_cap: bool


class RequestSignatureMiddleware:
    """Verify inbound RFC 9421 signatures on the AdCP surfaces. See the module docstring."""

    def __init__(self, app: Any, *, operation_resolver: OperationResolver | None = None) -> None:
        self.app = app
        # B1 ships the seam, not a partial map: the default names no operation, so
        # ``"" in required_for`` is False for every real declaration and B1 alone can
        # never fail closed on an operation it guessed wrong. B2 swaps this.
        self._operations: OperationResolver = operation_resolver or UnresolvedOperationResolver()

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        config = get_config().signing
        if scope["type"] != "http" or not config.verifier_enabled or not _is_adcp_surface(scope):
            await self.app(scope, receive, send)
            return

        headers = headers_from_asgi_scope(scope)
        operation, protocol_method = self._operations.resolve(scope, headers)
        signed = "signature" in headers or "signature-input" in headers

        # The hop is unconditional even though the resolver often does no I/O at all
        # (see below): whether it blocks depends on the posture it reads, and the event
        # loop must not be the thing that finds out it guessed wrong.
        context = await asyncio.to_thread(
            _resolve_request_context,
            headers=headers,
            token=_bearer_token(scope, headers),
            operation=operation,
            protocol_method=protocol_method,
            signed=signed,
        )

        if not signed:
            await self._handle_unsigned(context, operation, scope, receive, send)
            return

        # R-H3: the bucket is known before a single body byte is read.
        if context.bucket == "none":
            record_request_unsigned(operation, "ignored")
            await self.app(scope, receive, send)
            return

        await self._handle_signed(context, operation, headers, config, scope, receive, send)

    # -- branches ----------------------------------------------------------

    async def _handle_unsigned(
        self,
        context: _RequestContext,
        operation: str,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
    ) -> None:
        """No signature headers: the composition rule (security.mdx :1268-1269).

        The SDK cannot decide this — ``_precheck_presence`` raises on the absent branch
        whatever the bucket says — so the rejection is built here from the SDK's own
        error type and code constant. No body is read on this path.
        """
        if context.bucket == "required" and not context.authenticated:
            record_signature_failed(operation, REQUEST_SIGNATURE_REQUIRED)
            await _reject(
                SignatureVerificationError(
                    REQUEST_SIGNATURE_REQUIRED,
                    step=0,
                    message=(
                        f"operation {operation!r} requires a signature and the caller presented "
                        "no other credential this agent accepts"
                    ),
                ),
                scope,
                receive,
                send,
            )
            return

        record_request_unsigned(operation, "absent")
        await self.app(scope, receive, send)

    async def _handle_signed(
        self,
        context: _RequestContext,
        operation: str,
        headers: Mapping[str, str],
        config: SigningConfig,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
    ) -> None:
        """At least one signature header present: run the checklist and grade it."""
        buffered = await _buffer_body(receive, config.max_signed_body_bytes)
        if buffered.over_cap:
            logger.warning("Signed request body exceeded %d bytes; rejecting", config.max_signed_body_bytes)
            await Response(status_code=413)(scope, buffered.receive, send)
            return
        if not buffered.complete:
            # The client disconnected mid-body. There is nothing to verify and nothing
            # to answer; hand the disconnect downstream and let the app unwind.
            await self.app(scope, buffered.receive, send)
            return

        resolution = await _resolution_for(context.agent_url, config)

        try:
            signer = await asyncio.to_thread(
                _run_verifier,
                method=scope.get("method", "GET"),
                url=_verify_url(scope, headers),
                headers=headers,
                body=buffered.body,
                capability=context.posture.to_verifier_capability(),
                operation=operation,
                bucket=context.bucket,
                resolution=resolution,
                config=config,
            )
        except SignatureVerificationError as exc:
            await self._handle_rejection(exc, context, operation, scope, buffered.receive, send)
            return

        record_signature_verified(operation, signer.key_id)
        await self.app(scope, buffered.receive, send)

    async def _handle_rejection(
        self,
        exc: SignatureVerificationError,
        context: _RequestContext,
        operation: str,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
    ) -> None:
        """Reject — unless the operation is in ``warn_for``, which logs and continues.

        Warn mode is OURS: ``VerifierCapability`` carries 4 of ``request_signing``'s 8
        properties and 2 of its 6 operation buckets, so handing ``warn_for`` to the SDK
        would silently drop it. It is implemented the only way it can be — call the
        verifier, catch, emit the metric, continue — and it is observable on the WIRE
        (200 where ``supported_for`` answers 401), not merely in a counter.
        """
        record_signature_failed(operation, exc.code)
        if context.bucket == "warn":
            logger.warning(
                "Request signature failed in warn mode (not rejecting): code=%s step=%s "
                "operation=%r principal=%r tenant=%r",
                exc.code,
                exc.step,
                operation,
                context.principal_id,
                context.tenant_id,
            )
            await self.app(scope, receive, send)
            return
        await _reject(exc, scope, receive, send)


# ---------------------------------------------------------------------------
# Path scoping
# ---------------------------------------------------------------------------


def _is_adcp_surface(scope: Mapping[str, Any]) -> bool:
    """Whether this request targets one of the three AdCP protocol surfaces."""
    path = scope.get("path", "")
    root_path = scope.get("root_path") or ""
    if root_path and path.startswith(root_path):
        path = path[len(root_path) :] or "/"
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in ADCP_SURFACE_PREFIXES)


# ---------------------------------------------------------------------------
# Phase 1 — posture and caller identity (one thread hop)
# ---------------------------------------------------------------------------


def _bearer_token(scope: Mapping[str, Any], headers: Mapping[str, str]) -> str | None:
    """The caller's token, from the auth context ``UnifiedAuthMiddleware`` already set.

    Falls back to extracting it from the headers with the same shared rule, so that a
    verifier accidentally moved OUTSIDE the auth middleware degrades to doing the work
    twice rather than to treating every caller as unauthenticated — which would 401
    real traffic under ``required_for``.
    """
    auth_context = (scope.get("state") or {}).get(AUTH_CONTEXT_STATE_KEY)
    if auth_context is not None:
        return auth_context.auth_token
    return _extract_auth_token(dict(headers))[0]


def _resolve_request_context(
    *,
    headers: Mapping[str, str],
    token: str | None,
    operation: str,
    protocol_method: str | None,
    signed: bool,
) -> _RequestContext:
    """Resolve the seller's posture and, when the decision needs it, the caller.

    Runs in one thread hop because both lookups are synchronous DB work — and does
    NEITHER unless the answer can change an outcome. That is R-H3's rule applied to the
    whole middleware rather than just to the buffering step: B1 shipped alone must cost
    production nothing, and "one extra uncached tenant round trip on every AdCP request"
    is not nothing.

    * the tenant is read only while a posture is DECLARABLE
      (:func:`~src.core.signing.posture.request_signing_is_declarable`) — until D1 backs
      the block, every tenant's posture is the unsupported default and the read could
      not change it;
    * the principal is read only when its answer matters: on a signed request that will
      actually be verified (its ``agent_url`` is the key-resolution input), or on an
      unsigned request to a ``required_for`` operation (the composition rule's
      credential test).
    """
    tenant_id, tenant = _detect_tenant(dict(headers)) if request_signing_is_declarable() else (None, None)
    posture = posture_for_tenant(tenant)
    bucket = posture.bucket_for(operation, protocol_method)

    needs_principal = (signed and bucket != "none") or (not signed and bucket == "required")
    if not needs_principal or not token:
        return _RequestContext(posture=posture, bucket=bucket, tenant_id=tenant_id, principal_id=None, agent_url=None)

    if tenant_id is None:
        # Deferred above, but the credential test must stay tenant-scoped: a token is
        # unique deployment-wide, yet a principal of tenant A must not authenticate
        # against tenant B's virtual host.
        tenant_id = _detect_tenant(dict(headers))[0]

    with get_db_session() as session:
        principal = PrincipalRepository(session).get_by_token(token, tenant_id)
        principal_id = principal.principal_id if principal else None
        agent_url = principal.agent_url if principal else None

    if signed and principal is not None and not agent_url:
        # Plan step 3: no onboarding record of this counterparty's agent URL means no
        # brand.json to walk and therefore no key. The checklist still runs — a
        # malformed signature must still be rejected (:1226) — and reaches
        # ``request_signature_key_unknown`` on its merits at step 7.
        logger.warning(
            "Principal %r (tenant %r) signed a request but has no agent_url on record; "
            "no signing key can be resolved for it",
            principal_id,
            tenant_id,
        )

    return _RequestContext(
        posture=posture, bucket=bucket, tenant_id=tenant_id, principal_id=principal_id, agent_url=agent_url
    )


# ---------------------------------------------------------------------------
# Body buffering
# ---------------------------------------------------------------------------


async def _buffer_body(receive: Receive, max_bytes: int) -> _BufferedBody:
    """Read the whole body, and return a ``receive`` that replays it exactly once.

    The downstream app builds its own ``Request`` from the same scope, so the receive
    channel this middleware drains is the SAME one the app will read — the SDK
    wrapper's docstring claim that Starlette caches the body for downstream handlers is
    wrong; that cache lives on the middleware's own ``Request`` instance.

    Delegation after the replay matters: ``http.disconnect`` must still reach the app,
    which a one-shot closure returning a fixed message would swallow.
    """
    chunks: list[bytes] = []
    size = 0
    pending: list[MutableMapping[str, Any]] = []
    complete = False
    over_cap = False
    more_body = True

    while more_body:
        message = await receive()
        if message["type"] == "http.disconnect":
            pending.append(message)
            break
        chunk = bytes(message.get("body", b""))
        size += len(chunk)
        if size > max_bytes:
            over_cap = True
            break
        chunks.append(chunk)
        more_body = bool(message.get("more_body", False))
    else:
        complete = True

    body = b"".join(chunks)
    if complete:
        pending.append({"type": "http.request", "body": body, "more_body": False})

    async def replay() -> MutableMapping[str, Any]:
        if pending:
            return pending.pop(0)
        return await receive()

    return _BufferedBody(body=body, receive=replay, complete=complete, over_cap=over_cap)


# ---------------------------------------------------------------------------
# Phase 2 — the counterparty's key material
# ---------------------------------------------------------------------------


async def _resolution_for(agent_url: str | None, config: SigningConfig) -> AgentResolution | None:
    """The counterparty's cached :class:`AgentResolution`, resolving on a cold entry.

    ``agent_url -> capabilities -> identity.brand_json_url -> brand.json agents[] ->
    jwks_uri -> JWKS`` is a three-hop outbound walk, so it is done once per counterparty
    per TTL and never per request. Awaited HERE, before the synchronous verify hop:
    the walk is async, the checklist is not.

    A failure is not a rejection — it returns whatever is cached (possibly nothing) and
    lets the checklist decide. Mapping a resolver failure straight to a 401 would make
    an unreachable counterparty outrank a malformed signature, which is the wrong error
    and the wrong step.

    The SSRF pin stays at the SDK default: the walk follows a URL that ultimately came
    from a counterparty document, and ``allow_private_destinations`` is a test argument
    (``tests/unit/test_architecture_no_private_destinations.py`` fails the build on any
    src/ call site that passes it).
    """
    if not agent_url:
        return None

    now = time.time()
    cached = AGENT_RESOLUTION_CACHE.get(agent_url)
    if cached is not None and now - cached.fetched_at <= config.agent_resolution_ttl_seconds:
        return cached
    if now - _RESOLUTION_FAILURES.get(agent_url, 0.0) < config.agent_resolution_refetch_cooldown_seconds:
        return cached

    try:
        resolution = await async_resolve_agent(
            agent_url,
            # The agents that sign requests TO a sales agent are the buy side, so the
            # brand.json entry to match is the counterparty's buying agent.
            agent_type=cast(BrandAgentType, config.counterparty_agent_type),
        )
    except AgentResolverError as exc:
        _RESOLUTION_FAILURES[agent_url] = now
        logger.warning("Could not resolve signing keys for counterparty %r (%s): %s", agent_url, exc.code, exc)
        return cached

    AGENT_RESOLUTION_CACHE[agent_url] = resolution
    _RESOLUTION_FAILURES.pop(agent_url, None)
    return resolution


def _jwks_resolver(resolution: AgentResolution | None) -> StaticJwksResolver:
    """The resolver handed to the checklist.

    With a resolution: a brand-json-marked resolver, which is what engages the step-7
    key-origin check. Without one: a plain empty resolver, so the checklist answers
    ``request_signature_key_unknown`` at step 7 on its own. Marking THAT one
    ``brand_json`` would instead make the SDK warn about a missing
    ``expected_key_origins`` map that by definition cannot exist.
    """
    if resolution is None:
        return StaticJwksResolver({})
    return _BrandJsonJwksResolver(resolution.jwks, jwks_uri=resolution.jwks_uri)


# ---------------------------------------------------------------------------
# Phase 3 — the checklist (one thread hop)
# ---------------------------------------------------------------------------


def _run_verifier(
    *,
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes,
    capability: VerifierCapability,
    operation: str,
    bucket: PostureBucket,
    resolution: AgentResolution | None,
    config: SigningConfig,
) -> VerifiedSigner:
    """Run the SDK checklist over one database session.

    One hop, one session: the replay store's ``at_capacity`` / ``seen`` / ``remember``
    are synchronous and the verifier calls them inline, so a single checkout serves all
    three (A4's wiring contract, ``src/core/signing/replay_store.py``). The SDK's own
    call order is what keeps the two spec ordering invariants — capacity before crypto
    verify, replay claim after it — and this function preserves them by not reordering
    anything.

    All four key-origin fields are passed (R-M2): ``expected_key_origins``,
    ``agent_url``, ``signing_purpose`` and ``posture``. Omitting the first turns a
    mandatory check into a ``UserWarning``.

    Revocation stays unwired: no revocation list is published yet (#1291 A5), and the
    SDK correctly skips the check when both hooks are absent rather than failing open
    on a list it never fetched.
    """
    with get_db_session() as session:
        options = VerifyOptions(
            now=time.time(),
            capability=capability,
            operation=operation,
            jwks_resolver=_jwks_resolver(resolution),
            replay_store=PostgresReplayStore(ReplayNonceRepository(session), config),
            max_skew_seconds=config.max_skew_seconds,
            max_window_seconds=config.max_window_seconds,
            agent_url=resolution.agent_url if resolution is not None else None,
            expected_key_origins=resolution.key_origins if resolution is not None else None,
            signing_purpose=_SIGNING_PURPOSE,
            posture=bucket,
        )
        return verify_request_signature(method=method, url=url, headers=headers, body=body, options=options)


def _verify_url(scope: Mapping[str, Any], headers: Mapping[str, str]) -> str:
    """The URL the signature covers, as the CLIENT addressed it.

    Authority comes from the ``Host`` header as received and the scheme from the first
    hop of ``X-Forwarded-Proto`` — the client-facing scheme our own edge proxy
    terminated. Never from proxy ROUTING state (``Apx-Incoming-Host`` and friends),
    which security.mdx step 10 forbids deriving identity from: the signer signed the URL
    it dialed, and a rewritten one would fail ``@target-uri`` on every legitimate
    request behind TLS termination.
    """
    forwarded = headers.get("x-forwarded-proto", "")
    scheme = forwarded.split(",")[0].strip().lower() if forwarded else ""
    if scheme not in ("http", "https"):
        scheme = scope.get("scheme", "http")

    authority = headers.get("host")
    if not authority:
        server = scope.get("server") or ("", None)
        authority = f"{server[0]}:{server[1]}" if server[1] else str(server[0])

    query = scope.get("query_string", b"").decode("latin-1")
    return f"{scheme}://{authority}{scope.get('path', '')}" + (f"?{query}" if query else "")


async def _reject(
    exc: SignatureVerificationError,
    scope: dict[str, Any],
    receive: Receive,
    send: Send,
) -> None:
    """Send the spec's 401 directly.

    SENT, never raised: FastAPI's exception handlers are inner to this middleware, so a
    raise would reach ``ServerErrorMiddleware`` and become a 500 — turning a graded
    rejection into an outage-shaped response. The header comes from the SDK
    (``WWW-Authenticate: Signature error="<code>"``, realm intentionally omitted) so the
    byte-for-byte grading surface has one source.
    """
    logger.info("Rejecting request signature: code=%s step=%s (%s)", exc.code, exc.step, exc)
    await Response(status_code=401, headers=unauthorized_response_headers(exc))(scope, receive, send)

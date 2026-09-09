"""The one path from a validated request to a response.

Every transport enters here. MCP, A2A and REST differ in how a request ARRIVES and how a
response is written back; between those two points there is one sequence, and this is it:
resolve the account the request names, honour the idempotency key it carries, run the
implementation.

## Why these two things live here and not in an implementation

Both are properties of the REQUEST rather than of the work. ``account`` names whose
inventory the caller is acting on; ``idempotency_key`` says "if you have already done this,
do not do it again". Neither is a step in creating a media buy or syncing a creative, and an
implementation that performs them has to be TOLD it is being called by a buyer -- which is
how the previous arrangement went wrong in three ways at once:

* ``request_hash`` was computed by each transport and threaded down. The generated MCP
  registration calls the implementation directly, so it stopped computing one, and replay
  silently disabled itself on that transport. A value every caller must remember to supply
  is a value some caller will forget.
* the hash was taken over raw wire bytes when a transport threaded them and over the model
  otherwise, making "the same request" a per-transport answer.
* an in-process call -- ``create_media_buy`` uploading its inline creatives through
  ``_sync_creatives_impl`` -- inherited the outer request's key and had to be kept out of
  the cache by withholding the hash. Nothing internal passes through here, so that whole
  category is gone rather than guarded.

## The idempotency rule, entire

Save a non-error response that carried a key. On a later request with the same key: same
payload replays it verbatim, different payload is IDEMPOTENCY_CONFLICT.

The digest is ``canonical_request_hash`` over the VALIDATED request -- ``req.model_dump``,
after the DTO has parsed it. Equivalence is therefore over the request as this seller
understands it: two spellings of one instant are one payload, and a field the pinned schema
does not define is dropped by ``extra="ignore"`` before hashing, so it cannot distinguish two
requests either. That is deliberate. What the seller deliberately discards cannot be part of
what it compares, and the alternative -- canonicalising the received bytes before validation
-- needs a capture point per transport, which is the arrangement whose failure this seam
exists to fix. On top of that the spec's closed exclusion list is stripped
(``idempotency_key``, ``context``, ``governance_context``, and
``push_notification_config.authentication.credentials``), so a key never hashes itself and a
rotated webhook credential does not turn a retry into a conflict.

Errors are never saved, and that is now a property of control flow rather than a check: every
implementation RAISES on failure, and a raise never reaches the save. ``create_media_buy`` was
the one exception -- it returned a result carrying ``status="failed"`` for an adapter rejection,
which is why this module used to inspect the returned status before caching. It raises like
everything else now, so a returned result IS a success and there is nothing left to inspect.

Idempotency is scoped to (agent, account, key) per the spec, with no tool dimension.
"""

from __future__ import annotations

import inspect
import logging
import typing
from collections.abc import Callable
from typing import Any, Literal

from src.core.auth_context import AuthContext
from src.core.idempotency_canonical import canonical_request_hash
from src.core.idempotency_replay import cache_success, lookup_cached_replay, maybe_evict_expired
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas._base import AdcpResponse, BuyerRequest
from src.core.version_negotiation import SERVED_ADCP_VERSION, negotiate_adcp_version

logger = logging.getLogger(__name__)


def _response_model_for(impl: Callable[..., Any]) -> type[AdcpResponse] | None:
    """The model an implementation returns, read off its annotation.

    Derived rather than declared: a registry row says which DTO a tool ACCEPTS, and the
    implementation's own signature already says what it returns. Storing the response type
    a second time would be a second declaration that can disagree with the function.

    Narrowed to ``AdcpResponse``, which is what an AdCP response IS -- every pinned response
    schema composes the version and protocol envelopes at its root, and that base carries both.
    The narrowing is what lets this module ASSIGN ``adcp_version`` and ``replayed`` and CALL
    ``revive`` without probing for them; ``_register_tool`` refuses at import any tool whose
    response does not descend from it, so the annotation cannot quietly become a lie.

    ``None`` when the callable has no readable annotations, rather than a raise: the only
    consequence is that a cached envelope cannot be revived, so the request executes fresh --
    the same degradation a stale envelope already gets. Raising here would turn a callable
    ``get_type_hints`` cannot read into a failed request.
    """
    try:
        hints = typing.get_type_hints(impl)
    except Exception:
        return None
    annotation = hints.get("return")
    if isinstance(annotation, type) and issubclass(annotation, AdcpResponse):
        return annotation
    return None


def _deserializer_for(impl: Callable[..., Any]) -> Callable[[dict[str, Any]], Any | None]:
    """Turn a stored envelope back into a typed response, or None if it no longer validates.

    ``AdcpResponse.revive`` resolves the stored body to its type -- for a tool whose schema is
    a ``oneOf``, to the BRANCH the buyer originally received.

    None means "treat as a miss": a stored envelope that stopped validating -- because the
    response model changed between the deploy that wrote it and the one replaying it, inside
    the TTL window -- must fall through to fresh execution rather than fail a request.

    The spec's ``replayed`` marker is set here, which is the only place that can: the marker
    says "you are seeing a stored answer", so it is a property of the REPLAY and never of the
    stored body -- AdCP L1/security rule 4 puts it on the outgoing envelope for exactly that
    reason, and the cached body stays clean so repeated replays of one key each carry it once.

    A plain assignment, with no check that the field exists: every response model inherits
    ``AdcpResponse``, which ``_register_tool`` refuses to register a tool without.
    """
    model = _response_model_for(impl)

    def deserialize(envelope: dict[str, Any]) -> Any | None:
        if model is None:
            return None
        try:
            result = model.revive(envelope["response"])
        except Exception:
            logger.warning("Cached %s envelope failed validation — treating as a miss", model.__name__, exc_info=True)
            return None
        result.replayed = True
        return result

    return deserialize


async def _run(impl: Callable[..., Any], /, **kwargs: Any) -> Any:
    """Call an implementation, awaiting it only if it is a coroutine function.

    Six of the fourteen are plain ``def``.
    """
    result = impl(**kwargs)
    return await result if inspect.isawaitable(result) else result


def _keyed_scope(req: BuyerRequest, identity: ResolvedIdentity | None) -> tuple[str, str, str | None, str] | None:
    """``(tenant_id, principal_id, account_id, idempotency_key)`` when this request is cacheable.

    None whenever any part is absent: a request whose schema declares no key, one carrying
    none, or an identity that resolved no tenant or principal, has no (agent, account, key)
    scope to be cached under. A DTO that declares no ``idempotency_key`` cannot carry one --
    every request model is the pinned schema and nothing else.
    """
    key = req.get_idempotency_key()
    if not key or identity is None:
        return None
    if identity.tenant_id is None or identity.principal_id is None:
        return None
    return identity.tenant_id, identity.principal_id, identity.account_id, key


async def invoke_tool(
    tool_name: str,
    req: BuyerRequest,
    credential: AuthContext,
    protocol: Literal["mcp", "a2a", "rest"],
) -> AdcpResponse:
    """Run the registry's tool named ``tool_name``, for the caller holding *credential*.

    The form every transport calls. A transport names the TOOL and hands over the request it
    validated plus the credential the request arrived with; which function runs, and whether
    that credential must verify, are the registry's answers -- not the caller's.

    IT TAKES A CREDENTIAL, NOT AN IDENTITY, AND THAT IS THE POINT. It used to accept an
    already-resolved ``ResolvedIdentity``, so each transport resolved its own and read
    ``ToolSpec.auth`` itself to decide how strictly. Four sites did that and they disagreed
    twice -- A2A refusing a credential on a public task that MCP and REST served, and REST's
    discovery dependency hardcoding ``require_valid_token=False`` where the others passed the
    tool's declaration. A transport cannot disagree about a decision it no longer makes, and
    with no identity parameter there is nowhere to put one.

    ``protocol`` stays a per-transport argument: it labels the resulting identity, it does not
    decide anything, so passing it reintroduces no per-transport branch.
    """
    from starlette.concurrency import run_in_threadpool

    from src.core.resolved_identity import resolve_identity
    from src.core.testing_hooks import AdCPTestContext
    from src.core.tools.registry import TOOLS

    spec = TOOLS[tool_name]

    # In a worker thread because ``resolve_identity`` is SYNC and hits the database twice
    # (tenant detection, then the principal lookup). psycopg2 has no async path, so awaiting
    # it directly would block the event loop for both round-trips -- which is what MCP and
    # A2A did, while REST alone got the offload for free from FastAPI's sync-dependency
    # handling. One await here gives all three the offload.
    # The testing context rides the same headers, so it is resolved here too. Omitting it
    # was a silent functional regression when resolution moved: thirteen readers under
    # src/core/tools branch on ``identity.testing_context`` for dry-run and delivery
    # simulation, and MCP and A2A used to carry it in from their own context objects. A
    # boundary that resolves the caller must resolve the WHOLE caller, or every transport
    # loses what the transports used to supply individually.
    testing_context = AdCPTestContext.from_headers(dict(credential.headers))

    identity = await run_in_threadpool(
        resolve_identity,
        headers=dict(credential.headers),
        auth_token=credential.auth_token,
        require_valid_token=spec.requires_credential(),
        protocol=protocol,
        testing_context=testing_context,
    )

    # Recording lives HERE because this is the only place holding all three things a record
    # needs: the tool name, the resolved identity, and the exception. Each transport used to
    # record for itself, and two of them RE-RESOLVED an identity purely to obtain the tenant
    # and principal to scope it with -- REST from headers in its exception handler, MCP via
    # tool_error_logging. That is the same defect as the auth decision, in the observability
    # dimension: a value the caller already has, derived again somewhere else.
    try:
        return await invoke(tool_name, spec.impl, req, identity)
    except Exception as exc:
        from src.core.tool_error_logging import record_boundary_error

        record_boundary_error(
            protocol,
            tool_name,
            exc,
            tenant_id=identity.tenant_id,
            principal_id=identity.principal_id,
        )
        raise

    # No ``set_current_tenant`` anywhere on this path, deliberately. The tenant travels on
    # ``identity.tenant`` as a LazyTenantContext: it holds ``tenant_id`` immediately and
    # loads the row on first access to any other field, once, cached. Pushing it into a
    # ContextVar would flatten it to a mutable dict -- ``set_current_tenant`` does
    # ``dict(tenant_data)``, which ITERATES the lazy context and forces exactly the query the
    # laziness exists to defer. ``require_tenant(identity)`` is the explicit path.


async def invoke(
    tool_name: str,
    impl: Callable[..., Any],
    req: BuyerRequest,
    identity: ResolvedIdentity | None = None,
) -> AdcpResponse:
    """Run ``tool_name`` for a request that arrived over a transport.

    An implementation is called with the request and the caller, and nothing else. There is
    no per-transport channel here, so no transport can hand an implementation a value the
    others cannot.

    The response comes back stamped with the release this build served. That is an envelope
    field like any other -- every response model declares ``adcp_version``, inherited from the
    SDK's ``AdcpVersionEnvelope`` -- and it is set HERE for the same reason the account and the
    idempotency key are read here: it is a property of the seller and the call, not of the
    work, so an implementation neither knows it nor should have to. AdCP 3.1.1
    ``compliance/universal/version-negotiation.yaml`` grades it at the envelope root with
    ``envelope_field_present`` and ``envelope_field_pattern`` (advisory at 3.1, MUST at 4.0).

    The INBOUND half of that negotiation runs here too, and FIRST. A version pin is a property
    of the request in exactly the sense the account and the key are, so it belongs at the one
    chokepoint rather than inside a tool -- and inside a tool is where it used to live, on
    ``get_adcp_capabilities`` alone, which is the only tool a buyer pinning an unsupported
    release could not reach normally. ``compliance/universal/error-compliance.yaml`` grades it
    on ``get_products``. Running before the account is enriched and before the request is
    hashed is deliberate: a rejected pin should not resolve an account, touch the replay cache,
    or be answered from it. It raises, so it leaves without passing through ``_served``.
    """
    negotiate_adcp_version(req.get_adcp_version(), req.get_adcp_major_version())
    return _served(await _invoke(tool_name, impl, req, identity))


def _served(response: AdcpResponse) -> AdcpResponse:
    """Stamp the release this build served onto one response envelope.

    THE one assignment. Both of ``invoke``'s answers pass through it -- a fresh run and a
    replayed one -- so a replay echoes the release that is serving it, which is what the
    buyer's connection is actually speaking.
    """
    response.adcp_version = SERVED_ADCP_VERSION
    return response


async def _invoke(
    tool_name: str,
    impl: Callable[..., Any],
    req: BuyerRequest,
    identity: ResolvedIdentity | None = None,
) -> AdcpResponse:
    """``invoke`` without the envelope stamp: resolve the account, honour the key, run it."""
    account = req.get_account()
    if account is not None and identity is not None:
        from src.core.transport_helpers import enrich_identity_with_account

        identity = enrich_identity_with_account(identity, account)

    scope = _keyed_scope(req, identity)
    if scope is None:
        return await _run(impl, req=req, identity=identity)

    tenant_id, principal_id, account_id, key = scope
    request_hash = canonical_request_hash(req)

    replay = lookup_cached_replay(
        tenant_id=tenant_id,
        principal_id=principal_id,
        account_id=account_id,
        idempotency_key=key,
        request_hash=request_hash,
        deserialize=_deserializer_for(impl),
    )
    if replay is not None:
        return replay

    result = await _run(impl, req=req, identity=identity)
    cache_success(
        tenant_id=tenant_id,
        principal_id=principal_id,
        account_id=account_id,
        tool_name=tool_name,
        idempotency_key=key,
        response_model=result,
        # The result's OWN protocol status, not a constant. A create awaiting human approval
        # is ``submitted``, and storing it as completed would make the replay reconstruct the
        # wrong response variant -- the buyer would see a success where the original answer
        # was a pending task. A response with no status is not a task envelope; it succeeded
        # by having returned at all.
        protocol_status=result.status or "completed",
        payload_hash=request_hash,
    )
    maybe_evict_expired(tenant_id)
    return result

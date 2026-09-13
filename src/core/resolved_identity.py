"""Unified identity type for transport-agnostic business logic.

ResolvedIdentity is created at each transport boundary (MCP, A2A, REST) and
passed to _impl functions instead of transport-specific Context types.

This eliminates isinstance checks and auth extraction inside business logic.
"""

import logging
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.core.schemas import Principal
from src.core.tenant_context import TenantContext
from src.core.testing_hooks import AdCPTestContext

logger = logging.getLogger(__name__)


class TransportProtocol(StrEnum):
    """The transports a buyer can arrive on. THE declaration of what a transport is.

    A ``StrEnum``, so a call site cannot spell a transport as a bare string, and so a stored
    ``protocol`` column, an audit row and a wire payload all read the same value.
    ``tests/harness/transport.py``'s ``Transport`` takes its three core values from here; it adds
    the ``E2E_*`` members, which are test dispatch paths and not protocols a buyer can speak.

    It is a LABEL, never a decision. Nothing in ``src/`` branches on it, and it has exactly ONE
    consumer: scoping an observability record, so an operator reading the activity feed can see
    which surface a request arrived on. A response shape that varied by transport would be the
    thing this whole seam exists to prevent, so if a reader for this field is ever proposed,
    that is the question to ask first.
    """

    MCP = "mcp"
    A2A = "a2a"
    REST = "rest"


class ResolvedIdentity(BaseModel):
    """Transport-agnostic identity resolved at the boundary.

    Created by resolve_identity() before any _impl function is called.
    Immutable after creation — identity should not change during request processing.
    """

    # ``extra="forbid"`` so a caller still passing ``principal_id=`` or ``tenant_id=`` fails at
    # construction instead of silently building an anonymous identity: both are derived.
    model_config = ConfigDict(frozen=True, extra="forbid")

    # The principal the credential resolved to, built once from the row the lookup
    # selected. None for the anonymous caller of a public tool.
    principal: Principal | None = None
    # The tenant the request names, its row loaded by the resolver. ONE type, never a
    # dict: the annotation used to be ``Any``, commented "TenantContext | dict | None
    # (transitional)", and that union is how dict-shaped tenant handling spread.
    tenant: TenantContext | None = None
    protocol: TransportProtocol = TransportProtocol.MCP
    testing_context: AdCPTestContext | None = None
    account_id: str | None = None  # Resolved account ID (from AccountReference at transport boundary)
    # Tenant-level billing policy (BR-RULE-059) and account approval mode (BR-RULE-060)
    # are NOT fields on ResolvedIdentity — they live on identity.tenant (TenantContext).

    @property
    def principal_id(self) -> str | None:
        return self.principal.principal_id if self.principal is not None else None

    @property
    def tenant_id(self) -> str | None:
        return self.tenant.tenant_id if self.tenant is not None else None


from src.core.http_utils import get_header_case_insensitive as _get_header_case_insensitive


def _extract_auth_token(headers: Mapping[str, str]) -> str | None:
    """The Bearer value in ``Authorization``, or None when nothing was presented.

    ``Authorization: Bearer`` only. The ``x-adcp-auth`` alias is gone: pinned 3.1.1
    L2/authentication.mdx:71 says the credential MUST be carried in ``Authorization`` and
    that sellers MUST NOT require non-canonical aliases, and :153 says the alias is not
    recognized on the A2A surface at all. Accepting it was explicitly optional, so
    declining to is the compliant end state.

    A caller sending only the alias therefore presents nothing, which is the right reading:
    a protected tool answers AUTH_MISSING (nothing was presented to reject), never
    AUTH_INVALID.
    """
    authorization = _get_header_case_insensitive(headers, "Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _detect_tenant(headers: Mapping[str, str]) -> str | None:
    """The tenant_id this request names, by four header strategies. NO row is loaded.

    Identification only. The token check is scoped by tenant_id, so which tenant cannot be
    deferred; the row is loaded once by ``TenantContext.load`` after the tenant is known.

    Every strategy used to call a ``get_tenant_by_*`` helper ending in
    ``serialize_tenant_to_dict``, so identification loaded the entire row -- which
    ``resolve_identity`` then discarded, re-querying it on first field access. One indexed
    column per strategy instead.

    Strategy order, unchanged:
    1. Host header -> virtual host, then subdomain
    2. x-adcp-tenant header -> subdomain, then the literal id
    3. Apx-Incoming-Host -> virtual host
    4. localhost -> the "default" tenant
    """
    from src.core.config_loader import tenant_id_for

    host = _get_header_case_insensitive(headers, "host") or ""

    tenant_id = tenant_id_for(virtual_host=host)
    if not tenant_id and "." in host:
        subdomain = host.split(".")[0]
        if subdomain not in ["localhost", "adcp-sales-agent", "www", "admin"]:
            tenant_id = tenant_id_for(subdomain=subdomain)

    if not tenant_id:
        hint = _get_header_case_insensitive(headers, "x-adcp-tenant")
        if hint:
            # The hint is a subdomain when one matches, and otherwise taken as the id
            # itself -- unverified, exactly as before. An id that names no tenant fails
            # later, at the principal lookup that is scoped by it.
            tenant_id = tenant_id_for(subdomain=hint) or hint

    if not tenant_id:
        apx_host = _get_header_case_insensitive(headers, "apx-incoming-host")
        if apx_host:
            tenant_id = tenant_id_for(virtual_host=apx_host)

    if not tenant_id and host.split(":")[0] in ["localhost", "127.0.0.1", "localhost.localdomain"]:
        tenant_id = tenant_id_for(subdomain="default")

    return tenant_id


def _resolve_identity(
    headers: Mapping[str, str],
    *,
    require_valid_token: bool,
    protocol: TransportProtocol,
) -> ResolvedIdentity:
    """Resolve identity from request headers. PRIVATE to the boundary.

    The leading underscore is the design, not a style choice. This is the ONE identity
    resolution in the tree and ``src/core/tools/_boundary.invoke_tool`` is its only caller;
    a transport that wanted to resolve its own has no public name to reach for. Four of them
    used to, and they disagreed twice -- A2A refusing a credential on a public task that MCP
    and REST served, and REST's discovery dependency hardcoding require_valid_token=False.
    ``ruff-boundary.toml`` bans importing it outside the boundary, so the privacy is enforced
    at lint time rather than by convention.

    It reads the headers ONCE and does everything identity-shaped: the Bearer value, the
    tenant, the principal, and the testing context. No parameter accepts a pre-parsed token
    or a pre-built testing context, so a second reader of the headers has nothing to feed
    into this one.

    Args:
        headers: The request headers, as the transport's framework exposes them.
        require_valid_token: The TOOL's declaration (``ToolSpec.requires_credential()``).
            If True, a missing or rejected credential raises. If False, a rejected
            credential is treated like a missing one (discovery).
        protocol: Which transport is calling; a label for the observability record.

    Returns:
        ResolvedIdentity with all fields resolved

    Raises:
        AdCPAuthRequiredError: No credential was presented and require_valid_token=True
            (AUTH_MISSING).
        AdCPAuthenticationError: A credential was presented and did not resolve, and
            require_valid_token=True (AUTH_INVALID).

    POSTCONDITION, relied on by every caller: when ``require_valid_token`` is True this
    either returns an identity with a resolved ``principal_id`` or raises. Callers do not
    need their own "no token" or "no principal" guards, and the ones that had them have
    been removed -- they were three transports answering one question three ways.

    Both errors are typed only. Rendering them as HTTP -- 401 and a ``WWW-Authenticate``
    challenge -- is the transport's job, in its own framework's terms.
    """
    # Import here to avoid circular dependency (auth_utils imports from database)
    from src.core.auth_utils import get_principal_from_token

    # Step 1: the Bearer value, parsed here and nowhere else.
    auth_token = _extract_auth_token(headers)

    # Step 2: NO credential presented, on a surface that requires one.
    #
    # AUTH_MISSING, not AUTH_INVALID: the v3.1.1 enum keys the split on whether a credential
    # was PRESENTED. Nothing was. A credential that is presented and fails to resolve is
    # AUTH_INVALID, raised in step 4.
    #
    # Before tenant detection, which is three DB lookups an anonymous caller has not earned.
    # Both transports that had this check ran it in this order for that reason; it is here
    # so that all of them get it, MCP included -- MCP had none, carried a principal-less
    # identity into the tool, and _impl code grew its own AdCPAuthRequiredError raises to
    # compensate.
    #
    # ``require_valid_token`` is the TOOL's declaration (``ToolSpec.auth``) travelling down
    # from the boundary, never a transport's own opinion. A discovery tool passes False and
    # still resolves anonymously.
    #
    # This function raises TYPED errors and knows nothing about HTTP. Turning AUTH_MISSING
    # into a 401 with a challenge is each transport's own job, done with its framework's
    # mechanism -- see the REST exception handler, the A2A route wrapper and the MCP
    # pre-dispatch gate. An earlier attempt had this function reach forward to the ASGI
    # response instead; it could not work, because MCP sends its response status before the
    # tool is ever dispatched.
    if require_valid_token and not auth_token:
        from src.core.exceptions import AdCPAuthRequiredError

        raise AdCPAuthRequiredError()

    # Step 3: the seller this request addresses, identified from the host and loaded. The
    # tenant comes first because a principal is a row in a tenant: a credential is only
    # ever verified inside the tenant the request reached, never looked up across tenants.
    tenant_id = _detect_tenant(headers)
    tenant: TenantContext | None = TenantContext.load(tenant_id) if tenant_id else None

    # Step 4: the token to its principal, inside that tenant. No tenant, no lookup.
    principal: Principal | None = None
    if auth_token and tenant is not None:
        principal = get_principal_from_token(auth_token, tenant.tenant_id)
    if require_valid_token and principal is None:
        # Presented, and not a principal of the tenant addressed: AUTH_INVALID. A public
        # tool treats a rejected credential as absent and proceeds anonymously.
        from src.core.exceptions import AdCPAuthenticationError

        raise AdCPAuthenticationError()

    # Step 5: the testing context rides the same headers. Thirteen readers under
    # src/core/tools branch on ``identity.testing_context`` for dry-run and delivery
    # simulation, so the one place that resolves the caller resolves the WHOLE caller.
    testing_context = AdCPTestContext.from_headers(dict(headers))

    return ResolvedIdentity(
        principal=principal,
        tenant=tenant,
        protocol=protocol,
        testing_context=testing_context,
    )

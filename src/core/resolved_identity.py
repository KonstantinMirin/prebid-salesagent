"""Unified identity type for transport-agnostic business logic.

ResolvedIdentity is created at each transport boundary (MCP, A2A, REST) and
passed to _impl functions instead of transport-specific Context types.

This eliminates isinstance checks and auth extraction inside business logic.
"""

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.core.tenant_context import LazyTenantContext
from src.core.testing_hooks import AdCPTestContext

logger = logging.getLogger(__name__)

#: The transports this seller speaks, as a closed set.
#:
#: Written ONCE. It was spelled out three times -- the field below, the resolver's parameter,
#: and ``invoke_tool``'s -- which is three edits to add a transport and three chances for one
#: of them to drift into a bare ``str``. A closed set stated in one place is the whole reason
#: this is a ``Literal`` rather than a string: mypy rejects a typo at the call site.
#:
#: It is a LABEL, never a decision. Nothing in ``src/`` branches on it, and it has exactly ONE
#: consumer: scoping an observability record, so an operator reading the activity feed can see
#: which surface a request arrived on.
#:
#: It had a second consumer until this was measured. ``_workflow.py`` stored it on a creative-
#: approval workflow step "for webhook payload creation", and nothing ever read it back. The
#: premise was wrong as well as dead: that path fires ``creative.status_changed``, an
#: account-level notification whose shape is fixed and whose subscribers are the registered
#: ``notification_configs[]`` -- the originating call's transport does not enter into it. A
#: response shape that varied by transport would be the thing this whole seam exists to
#: prevent, so if a reader for this field is ever proposed, that is the question to ask first.

TransportProtocol = Literal["mcp", "a2a", "rest"]


class ResolvedIdentity(BaseModel):
    """Transport-agnostic identity resolved at the boundary.

    Created by resolve_identity() before any _impl function is called.
    Immutable after creation — identity should not change during request processing.
    """

    # LazyTenantContext is a plain slotted class, not a pydantic model, so it needs an
    # explicit pass. Keeping the field TYPED is the point -- it was ``Any`` with a comment
    # reading "TenantContext | dict[str, Any] | None (transitional)", which is how a dict
    # ended up flowing where a context was meant.
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    principal_id: str | None = None
    tenant_id: str | None = None
    # ONE tenant type, not a union. Production builds it at the boundary (id now, row on
    # first field access, cached). A caller that already holds the row -- a test factory with
    # no database, or code that just read it -- hands over the SAME type via
    # ``LazyTenantContext.already(row)``, which resolves immediately and never queries.
    # Laziness is about when the row loads, not about which type flows.
    #
    # What the annotation excludes is both the dict and the hydrated ``TenantContext``. It
    # used to be ``Any``, commented "TenantContext | dict[str, Any] | None (transitional)",
    # and that union is how dict-shaped tenant handling spread through production.
    tenant: LazyTenantContext | None = None
    auth_token: str | None = None
    protocol: TransportProtocol = "mcp"
    testing_context: AdCPTestContext | None = None
    account_id: str | None = None  # Resolved account ID (from AccountReference at transport boundary)
    # Tenant-level billing policy (BR-RULE-059) and account approval mode (BR-RULE-060)
    # are NOT fields on ResolvedIdentity — they live on identity.tenant (TenantContext).

    @property
    def is_authenticated(self) -> bool:
        """Check if this identity has a resolved principal."""
        return self.principal_id is not None and self.principal_id != ""


from src.core.http_utils import get_header_case_insensitive as _get_header_case_insensitive


def _extract_auth_token(headers: dict) -> tuple[str | None, str | None]:
    """Extract auth token from headers.

    ``Authorization: Bearer`` only. The ``x-adcp-auth`` alias is gone: pinned 3.1.1
    L2/authentication.mdx:71 says the credential MUST be carried in ``Authorization`` and
    that sellers MUST NOT require non-canonical aliases, and :153 says the alias is not
    recognized on the A2A surface at all. Accepting it was explicitly optional, so
    declining to is the compliant end state.

    A caller sending only the alias therefore presents nothing, which is the right reading:
    a protected tool answers AUTH_MISSING (nothing was presented to reject), never
    AUTH_INVALID.

    Returns:
        (token, source) tuple — source is "Authorization: Bearer" or None
    """
    authorization = _get_header_case_insensitive(headers, "Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        potential_token = authorization[7:].strip()
        if potential_token:
            return potential_token, "Authorization: Bearer"

    return None, None


def _detect_tenant(headers: dict) -> str | None:
    """The tenant_id this request names, by four header strategies. NO row is loaded.

    Identification only. The token check is scoped by tenant_id, so which tenant cannot be
    deferred; the tenant's FIELDS can be, and ``LazyTenantContext`` defers them.

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
    headers: dict,
    auth_token: str | None = None,
    protocol: TransportProtocol = "mcp",
    require_valid_token: bool = True,
    testing_context: AdCPTestContext | None = None,
) -> ResolvedIdentity:
    """Resolve identity from request headers. PRIVATE to the boundary.

    The leading underscore is the design, not a style choice. This is the ONE identity
    resolution in the tree and ``src/core/tools/_boundary.invoke_tool`` is its only caller;
    a transport that wanted to resolve its own has no public name to reach for. Four of them
    used to, and they disagreed twice -- A2A refusing a credential on a public task that MCP
    and REST served, and REST's discovery dependency hardcoding require_valid_token=False.
    ``ruff-boundary.toml`` bans importing it outside the boundary, so the privacy is enforced
    at lint time rather than by convention.

    Args:
        headers: HTTP request headers dict
        auth_token: Pre-extracted auth token (if already parsed by transport).
                   If None, will extract from headers.
        protocol: Which transport is calling ("mcp", "a2a", "rest")
        require_valid_token: If True, raises AdCPAuthenticationError for invalid tokens.
                           If False, treats invalid tokens like missing (for discovery).
        testing_context: Pre-extracted testing context, if available.

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

    # Step 1: Extract auth token if not pre-provided
    if auth_token is None:
        auth_token, _ = _extract_auth_token(headers)

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

    # Step 3: Detect tenant from headers
    tenant_id = _detect_tenant(headers)

    # Step 4: Validate token → principal_id (and discover tenant from token if needed)
    principal_id = None
    if auth_token:
        principal_id, token_tenant = get_principal_from_token(auth_token, tenant_id)

        if principal_id is None:
            if require_valid_token:
                from src.core.exceptions import AdCPAuthenticationError

                raise AdCPAuthenticationError()
            # For discovery endpoints, continue without auth
        elif not tenant_id and token_tenant:
            # Tenant discovered from the token lookup when no header identified one. Only
            # its ID is taken: the row it carries is hydration, and hydration is the lazy
            # context's job.
            tenant_id = token_tenant.get("tenant_id") or tenant_id

    # The identity always carries the tenant_id; the tenant's FIELDS load lazily, once.
    #
    # Identification cannot be deferred -- step 4 above scopes the token check by tenant_id,
    # so we must know WHICH tenant before we can verify a credential. Hydration can: a
    # LazyTenantContext holds the id immediately and loads the row on first access to any
    # other field, caching the result. This used to build a fully-hydrated TenantContext from
    # whatever dict detection happened to return, so every request paid for the whole row
    # whether or not anything read a field off it, and LazyTenantContext was dead weight
    # everywhere except the ToolContext path.
    tenant_model: LazyTenantContext | None = LazyTenantContext(tenant_id) if tenant_id else None

    return ResolvedIdentity(
        principal_id=principal_id,
        tenant_id=tenant_id,
        tenant=tenant_model,
        auth_token=auth_token,
        protocol=protocol,
        testing_context=testing_context,
    )

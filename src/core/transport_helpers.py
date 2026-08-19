"""Transport boundary helpers for creating ResolvedIdentity from transport-specific types.

These functions bridge transport-specific types (FastMCP Context, ToolContext,
A2A headers) to the transport-agnostic ResolvedIdentity used by _impl functions.

Each transport boundary calls one of these helpers before invoking _impl.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from adcp.types import AccountReference

from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_headers

from src.core.resolved_identity import ResolvedIdentity, resolve_identity
from src.core.tenant_context import LazyTenantContext
from src.core.tool_context import ToolContext

logger = logging.getLogger(__name__)


def _make_lazy_tenant(tenant_id: str) -> LazyTenantContext:
    """Create a lazy-loading tenant context for the given tenant_id.

    The DB query is deferred until a non-tenant_id field is first accessed.
    This avoids hitting the database for requests that only need tenant_id
    (the common case) or that fail auth before reaching tenant-dependent logic.
    """
    return LazyTenantContext(tenant_id)


def resolve_identity_from_context(
    ctx: Context | ToolContext | None,
    require_valid_token: bool = True,
    protocol: Literal["mcp", "a2a", "rest"] = "mcp",
) -> ResolvedIdentity | None:
    """Create ResolvedIdentity from a FastMCP Context or ToolContext.

    This is the primary bridge for MCP tool wrappers and A2A raw functions.

    Args:
        ctx: FastMCP Context or ToolContext (or None for unauthenticated)
        require_valid_token: Whether to raise on invalid tokens
        protocol: Transport protocol ("mcp", "a2a", "rest")

    Returns:
        ResolvedIdentity, or None if ctx is None and no headers available
    """
    # Handle ToolContext directly (already has resolved identity info)
    if isinstance(ctx, ToolContext):
        # Create lazy tenant — DB query deferred until a field beyond
        # tenant_id is accessed. Most _impl paths only need tenant_id
        # for DB queries, so the full load often never happens.
        tenant = _make_lazy_tenant(ctx.tenant_id)
        return ResolvedIdentity(
            principal_id=ctx.principal_id,
            tenant_id=ctx.tenant_id,
            tenant=tenant,
            protocol=protocol,
            testing_context=ctx.testing_context,
        )

    # Handle FastMCP Context — extract headers and resolve
    headers = None
    try:
        headers = get_http_headers(include_all=True)
    except Exception:
        logger.debug("get_http_headers() unavailable, trying fallback", exc_info=True)

    # Fallback to context.meta if available
    if not headers and ctx is not None:
        if hasattr(ctx, "meta") and ctx.meta and "headers" in ctx.meta:
            headers = ctx.meta["headers"]
        elif hasattr(ctx, "headers"):
            headers = ctx.headers

    if not headers:
        if ctx is None:
            return None
        # No headers available — return minimal identity
        return ResolvedIdentity(protocol=protocol)

    # Extract testing context from headers if present
    testing_context = None
    try:
        from src.core.testing_hooks import TestContext

        if ctx is not None:
            testing_context = TestContext.from_context(ctx)
    except Exception:
        logger.debug("Could not extract testing context", exc_info=True)

    return resolve_identity(
        headers=headers,
        require_valid_token=require_valid_token,
        protocol=protocol,
        testing_context=testing_context,
    )


def enrich_identity_with_account(
    identity: ResolvedIdentity | None,
    account_ref: AccountReference | None = None,
) -> ResolvedIdentity | None:
    """Enrich a ResolvedIdentity with a resolved account_id.

    Called at the transport boundary after resolve_identity(), when the request
    payload contains an AccountReference. Opens an AccountUoW, resolves the
    reference to a validated account_id, and returns an enriched identity.

    If account_ref is None or identity is None, returns identity unchanged.

    Args:
        identity: Base ResolvedIdentity from resolve_identity().
        account_ref: AccountReference from the request body (optional).

    Returns:
        ResolvedIdentity with account_id populated, or original identity if no account.
    """
    if identity is None or account_ref is None:
        return identity

    # Require an authenticated principal BEFORE resolving the account (#1417).
    # Account resolution runs at the transport boundary ahead of the _impl auth gate;
    # without this guard an unauthenticated caller (tenant resolved, principal_id=None)
    # reaches natural-key resolution, which skips the access-scope join and discloses the
    # tenant-wide match count via ACCOUNT_AMBIGUOUS. require_principal_id raises
    # AUTH_REQUIRED first, uniformly across every transport that funnels through here.
    from src.core.auth import require_principal_id

    require_principal_id(identity)

    if identity.tenant_id is None:
        return identity

    from src.core.database.repositories.uow import AccountUoW
    from src.core.helpers.account_helpers import resolve_account

    with AccountUoW(identity.tenant_id) as uow:
        assert uow.accounts is not None
        account_id = resolve_account(account_ref, identity, uow.accounts)

    return identity.model_copy(update={"account_id": account_id})


@overload
def honor_account_reference(identity: ResolvedIdentity, account_ref: AccountReference | None) -> ResolvedIdentity: ...


@overload
def honor_account_reference(identity: None, account_ref: AccountReference | None) -> None: ...


def honor_account_reference(
    identity: ResolvedIdentity | None,
    account_ref: AccountReference | None,
) -> ResolvedIdentity | None:
    """Honor the `account` a buyer sent on a tool request.

    The ONE way a tool honors `account`, so a second tool joining the contract
    cannot get a subtly different version of it (CLAUDE.md's DRY invariant —
    a duplicate here would be a defect, not a style preference).

    Callers pass ``req.account`` rather than ``req`` deliberately. It keeps the
    field read visible in the TOOL's own source, which is what
    ``tests/harness/spec_field_consumption.py`` reads to decide the field was
    disposed; hiding it behind a whole-request parameter would make an honored
    field look undisposed and push the tool back onto the undisposed ledger.

    The overloads carry the narrowing a caller needs: this returns None ONLY
    when the identity it was handed is None, so a tool that has already run
    ``require_identity`` keeps a non-optional identity across the call instead of
    having every later attribute access widened back to ``| None``.

    The ``isinstance`` check is the real guard, not a None check: a unit test
    that mocks the request has a MagicMock for EVERY attribute, so ``req.account``
    is non-None and resolution would run — demanding an authenticated principal
    the test deliberately omitted (get_products is a discovery endpoint that
    legitimately serves anonymous callers). Checking the reference's own type
    admits exactly the real thing and skips both None and a test's stand-in.
    """
    from adcp.types import AccountReference as _AccountReference

    if not isinstance(account_ref, _AccountReference):
        return identity
    # `or identity` narrows the helper's `| None` return: it returns None only
    # when the identity it was GIVEN is None.
    return enrich_identity_with_account(identity, account_ref) or identity

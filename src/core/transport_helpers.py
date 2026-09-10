"""Transport boundary helpers for creating ResolvedIdentity from transport-specific types.

These functions bridge transport-specific types (FastMCP Context, ToolContext,
A2A headers) to the transport-agnostic ResolvedIdentity used by _impl functions.

Each transport boundary calls one of these helpers before invoking _impl.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adcp.types import AccountReference


from src.core.resolved_identity import ResolvedIdentity
from src.core.tenant_context import LazyTenantContext

logger = logging.getLogger(__name__)


def _make_lazy_tenant(tenant_id: str) -> LazyTenantContext:
    """Create a lazy-loading tenant context for the given tenant_id.

    The DB query is deferred until a non-tenant_id field is first accessed.
    This avoids hitting the database for requests that only need tenant_id
    (the common case) or that fail auth before reaching tenant-dependent logic.
    """
    return LazyTenantContext(tenant_id)


# (Deleted) resolve_identity_from_context was the MCP/A2A bridge: it turned a FastMCP
# Context or ToolContext into a ResolvedIdentity. Both transports hand the boundary a
# credential now and the boundary resolves, so there is nothing left to bridge. It was the
# last resolution site outside src/core/tools/_boundary.py.


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

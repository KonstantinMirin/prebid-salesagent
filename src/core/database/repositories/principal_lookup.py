"""Principal lookups for cross-cutting concerns outside the tenant-scoped
Account/Principal repositories (e.g. activity-feed logging).

``read_principal_name`` is a module-level, session-owning read -- like
``adapter_config.read_adapter_config`` -- rather than a class, because it is one query
with no CRUD to group it with. ``PrincipalLookupRepository`` is the cross-tenant
counterpart of ``tenant_lookup.TenantLookupRepository``: it answers a question about
a row whose tenant the caller does not yet know.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database.models import Principal


class PrincipalLookupRepository:
    """Read access to principals by a unique key, across all tenants.

    Not the credential path. The resolver looks a token up INSIDE the tenant the request
    addressed (``src/core/auth_utils.get_principal_from_token``); this exists for the
    testing-only debug endpoint that reports which tenant a known token belongs to.

    Args:
        session: SQLAlchemy session (caller manages lifecycle).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_token_hash(self, token_hash: str) -> Principal | None:
        """The principal holding ``token_hash``, whichever tenant it is in."""
        return self._session.scalars(select(Principal).filter_by(token_hash=token_hash)).first()


def read_principal_name(tenant_id: str, principal_id: str) -> str | None:
    """The persisted display name for a principal, or ``None`` if not found.

    The ONE session-owning read for this lookup.
    ``src/core/helpers/activity_helpers.log_tool_activity`` (a cross-cutting
    concern called from every ``_impl``) previously opened its own
    ``get_db_session()`` -- the same D2 disease ``adapter_helpers.py`` had
    (#1721 M2). Returns the plain string, not the ORM row, so
    there is nothing to detach.
    """
    from src.core.database.database_session import get_db_session

    with get_db_session() as session:
        principal = session.scalars(select(Principal).filter_by(principal_id=principal_id, tenant_id=tenant_id)).first()
        return principal.name if principal else None

"""Tenant-scoped access to ``principals`` rows for the operator's admin views.

The credential path never comes here: a request's principal is loaded once by the
resolver (``src/core/auth_utils``) and travels on ``ResolvedIdentity.principal``, and
``.ast-grep/rules/principal-rows-are-loaded-only-by-the-resolver.yml`` makes a
``select(Principal)`` anywhere else unconstructible. The admin UI is the other reader:
it manages principals as rows (list, edit, delete), and those queries live here.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database.models import Principal


class PrincipalRepository:
    """Read access to one tenant's principals.

    Args:
        session: SQLAlchemy session (caller manages lifecycle).
        tenant_id: Every query is scoped to this tenant.
    """

    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def get(self, principal_id: str) -> Principal | None:
        """The principal with ``principal_id`` in this tenant, or ``None``."""
        return self._session.scalars(
            select(Principal).filter_by(tenant_id=self._tenant_id, principal_id=principal_id)
        ).first()

    def list_all(self) -> list[Principal]:
        """Every principal in this tenant, ordered by display name."""
        return list(
            self._session.scalars(select(Principal).filter_by(tenant_id=self._tenant_id).order_by(Principal.name)).all()
        )

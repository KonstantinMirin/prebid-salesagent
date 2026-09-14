"""Principal lookups for cross-cutting concerns outside the tenant-scoped
``PrincipalRepository`` (activity-feed logging, the bulk setup checklist).

Module-level reads -- like ``adapter_config.read_adapter_config`` -- rather than a
class, because each is one query with no CRUD to group it with.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.database.models import Principal


def find_principal_by_token_hash(session: Session, token_hash: str) -> Principal | None:
    """The principal holding ``token_hash``, whichever tenant it is in, or ``None``.

    Not the credential path: a request's token is resolved INSIDE the tenant the request
    addressed (``PrincipalRepository.find_by_token_hash``). This is seed maintenance --
    ``scripts/setup/init_database_ci.py`` asks whether its documented token already exists
    anywhere, because ``token_hash`` is unique across tenants and a stale row in another
    tenant has to be moved, not duplicated.
    """
    return session.scalars(select(Principal).filter_by(token_hash=token_hash)).first()


def count_principals_by_tenant(session: Session, tenant_ids: Iterable[str]) -> dict[str, int]:
    """How many principals each of *tenant_ids* holds, keyed by tenant_id.

    Cross-tenant by design: the bulk setup checklist grades many tenants in one query.
    A tenant with no principals is absent from the result. Takes the caller's session
    because it runs beside the sibling per-tenant counts in the same transaction.
    """
    stmt = (
        select(Principal.tenant_id, func.count())
        .where(Principal.tenant_id.in_(list(tenant_ids)))
        .group_by(Principal.tenant_id)
    )
    return dict(session.execute(stmt).tuples().all())


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

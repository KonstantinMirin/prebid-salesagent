"""The token-to-principal lookup: the resolver's database primitive."""

import logging

from sqlalchemy import select

from src.core.database.database_session import execute_with_retry
from src.core.database.models import Principal as ModelPrincipal
from src.core.schemas import Principal

logger = logging.getLogger(__name__)


def get_principal_from_token(token: str, tenant_id: str) -> Principal | None:
    """The principal *token* authenticates inside *tenant_id*, or ``None``.

    A buyer credential is a ``Principal`` row and nothing else, and a principal is a row in
    exactly one tenant: the lookup is always scoped to the tenant the request addressed, so
    a token minted for one tenant never acts on another. The row is built into its model
    inside the session; the resolver keeps what was loaded.
    """

    def _lookup_principal(session):
        stmt = select(ModelPrincipal).filter_by(access_token=token, tenant_id=tenant_id)
        principal = session.scalars(stmt).first()
        return Principal.from_row(principal) if principal else None

    return execute_with_retry(_lookup_principal)

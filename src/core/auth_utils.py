"""The principal lookups: the resolver's database primitives.

Two readers, one per way a principal is identified. A request identifies its principal
by the token it presents (``get_principal_from_token``); server-initiated work identifies
the owner of a stored row by id (``get_principal_by_id``). Both are scoped to a tenant,
because a principal is a row in exactly one tenant, and both hand back the model built
inside the session so the resolver keeps what was loaded.
"""

import logging

from sqlalchemy import select

from src.core.credentials import hash_token
from src.core.database.database_session import execute_with_retry
from src.core.database.models import Principal as ModelPrincipal
from src.core.schemas import Principal

logger = logging.getLogger(__name__)


def get_principal_from_token(token: str, tenant_id: str) -> Principal | None:
    """The principal *token* authenticates inside *tenant_id*, or ``None``.

    A buyer credential is a ``Principal`` row and nothing else, and the lookup is always
    scoped to the tenant the request addressed, so a token minted for one tenant never
    acts on another. The row stores ``sha256(token)``, so the presented value is hashed
    here and compared by equality on the hash; the plaintext is never written anywhere.
    """

    token_hash = hash_token(token)

    def _lookup_principal(session):
        stmt = select(ModelPrincipal).filter_by(token_hash=token_hash, tenant_id=tenant_id)
        principal = session.scalars(stmt).first()
        return Principal.from_row(principal) if principal else None

    return execute_with_retry(_lookup_principal)


def get_principal_by_id(tenant_id: str, principal_id: str) -> Principal | None:
    """The principal *principal_id* names inside *tenant_id*, or ``None``.

    For resolution from stored ids (``resolved_identity.identity_of``): the owner of a
    media buy or creative a server-initiated job acts on.
    """

    def _lookup_principal(session):
        stmt = select(ModelPrincipal).filter_by(principal_id=principal_id, tenant_id=tenant_id)
        principal = session.scalars(stmt).first()
        return Principal.from_row(principal) if principal else None

    return execute_with_retry(_lookup_principal)

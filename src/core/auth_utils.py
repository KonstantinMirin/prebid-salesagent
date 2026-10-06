"""The principal lookups: the resolver's database primitives.

A request identifies its principal by the token it presents (``get_principal_from_token``),
by the agent a verified signature names (``get_principal_by_agent_url``), or, for a signed
request with no bearer, by the keyid its onboarding record pins
(``get_principal_by_signing_keyid``); server-initiated work identifies the owner of a stored
row by id (``get_principal_by_id``). All are scoped to a tenant, because a principal is a row
in exactly one tenant, and all hand back the model built inside the session so the resolver
keeps what was loaded.
"""

import logging
from collections.abc import Callable
from typing import Any

from src.core.credentials import hash_token
from src.core.database.database_session import execute_with_retry
from src.core.database.repositories.principal import PrincipalRepository
from src.core.schemas import Principal

logger = logging.getLogger(__name__)


def _load_principal(tenant_id: str, find: Callable[[PrincipalRepository], Any]) -> Principal | None:
    """The principal *find* selects from *tenant_id*'s repository, built inside the session."""

    def _lookup_principal(session):
        row = find(PrincipalRepository(session, tenant_id))
        return Principal.from_row(row) if row else None

    return execute_with_retry(_lookup_principal)


def get_principal_from_token(token: str, tenant_id: str) -> Principal | None:
    """The principal *token* authenticates inside *tenant_id*, or ``None``.

    A buyer credential is a ``Principal`` row and nothing else, and the lookup is always
    scoped to the tenant the request addressed, so a token minted for one tenant never
    acts on another. The row stores ``sha256(token)``, so the presented value is hashed
    here and compared by equality on the hash; the plaintext is never written anywhere.
    """
    token_hash = hash_token(token)
    return _load_principal(tenant_id, lambda principals: principals.find_by_token_hash(token_hash))


def get_principal_by_agent_url(agent_url: str, tenant_id: str) -> Principal | None:
    """The principal onboarded at *agent_url* inside *tenant_id*, or ``None``.

    The third way a request identifies its principal, and the newest: a valid RFC 9421
    signature. Verification establishes exactly one fact — "the request was issued by the
    agent whose ``jwks_uri`` contains the ``keyid``" (security.mdx @ v3.1.1 § Agent
    identity) — and names that agent by the ``agents[]`` entry whose ``jwks_uri`` resolved
    the key. So a verified signature IS a credential, and this is how it resolves to a
    principal when the caller presented no bearer at all.

    Scoped to the tenant like the other two, and unique within it
    (``uq_principals_tenant_agent_url``), so the answer is one row rather than whichever
    sorted first.
    """
    return _load_principal(tenant_id, lambda principals: principals.find_by_agent_url(agent_url))


def get_principal_by_signing_keyid(keyid: str, tenant_id: str) -> Principal | None:
    """The principal of *tenant_id* whose onboarding record pins *keyid*, or ``None``.

    The key-resolution input for a signed request that presents no bearer: its keyid is
    the only handle it offers. ``None`` when no principal, or more than one, pins it
    (``PrincipalRepository.find_by_signing_keyid``).
    """
    return _load_principal(tenant_id, lambda principals: principals.find_by_signing_keyid(keyid))


def get_principal_by_id(tenant_id: str, principal_id: str) -> Principal | None:
    """The principal *principal_id* names inside *tenant_id*, or ``None``.

    For resolution from stored ids (``resolved_identity.identity_of``): the owner of a
    media buy or creative a server-initiated job acts on.
    """
    return _load_principal(tenant_id, lambda principals: principals.get(principal_id))

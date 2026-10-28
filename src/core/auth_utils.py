"""The principal lookups: the resolver's database primitives.

Three readers, one per way a principal is identified. A request identifies its principal
by the credential it presents — the bearer it sent (``get_principal_from_token``) or the
RFC 9421 signature it signed with (``get_principal_by_agent_url``); server-initiated work
identifies the owner of a stored row by id (``get_principal_by_id``). All three are scoped
to a tenant, because a principal is a row in exactly one tenant, and all three hand back
the model built inside the session so the resolver keeps what was loaded.
"""

import logging

from src.core.credentials import hash_token
from src.core.database.database_session import execute_with_retry
from src.core.database.repositories.oauth_client import OAuthClientRepository
from src.core.database.repositories.principal import PrincipalRepository
from src.core.database.repositories.tenant import TenantRepository
from src.core.oauth_service import (
    OAuthTokenValidationError,
    get_mcp_oauth_audience,
    get_mcp_oauth_issuer,
    validate_mcp_access_token,
)
from src.core.schemas import Principal

logger = logging.getLogger(__name__)


def get_principal_from_token(token: str, tenant_id: str) -> Principal | None:
    """The principal *token* authenticates inside *tenant_id*, or ``None``.

    TWO kinds of bearer resolve here, because the ``Authorization`` header carries exactly
    one value and the seller accepts either form of it:

    1. A first-party MCP OAuth access token — a JWT this deployment minted and signs,
       whose claims name the tenant, the principal and the OAuth client it was issued to.
    2. A seller-minted buyer token (``tok_``) — an opaque value whose ``sha256`` the
       ``principals`` row stores.

    The OAuth form is tried first and the opaque form is the fallback, which is the order
    the two were added in. Order cannot change WHICH principal answers: a JWT never hashes
    to a stored token and an opaque token never validates as a JWT, so at most one of the
    two ever resolves. What it does decide is that an OAuth-shaped bearer is judged by the
    OAuth checks (``_oauth_principal``) rather than silently degrading to a hash miss.

    Whichever form it took, the answer is a ``Principal`` row and nothing else, and the
    lookup is always scoped to the tenant the request addressed, so a credential minted
    for one tenant never acts on another. The opaque form is compared by equality on
    ``sha256(token)``; the plaintext is never written anywhere.

    ``None`` means the bearer resolved to nobody. The resolver reads that as
    ``bearer_rejected`` and raises AUTH_INVALID (``_resolve_identity`` step 4), so a bearer
    that is neither a valid OAuth token nor a known buyer token is terminal — a request
    signature cannot launder it.
    """

    token_hash = hash_token(token)

    def _lookup_principal(session):
        oauth_principal = _oauth_principal(session, token, tenant_id)
        if oauth_principal is not None:
            return oauth_principal

        row = PrincipalRepository(session, tenant_id).find_by_token_hash(token_hash)
        return Principal.from_row(row) if row else None

    return execute_with_retry(_lookup_principal)


def _oauth_principal(session, token: str, tenant_id: str) -> Principal | None:
    """The principal a first-party MCP OAuth access token names in *tenant_id*, or ``None``.

    Four things must hold, and ``None`` is returned rather than raised for each, so that a
    bearer that is not an OAuth token at all falls through to the opaque-token lookup and a
    bearer that IS one but fails any check is refused by the caller's single AUTH_INVALID.

    1. The JWT verifies: signature, ``iss``, ``aud``, ``exp`` and the required claim set,
       all of them ``validate_mcp_access_token``'s job.
    2. The token's ``tenant_id`` claim IS the tenant the request addressed. A token minted
       for one seller presented to another resolves to nobody, the same rule the opaque
       form gets from its tenant-scoped query.
    3. The OAuth client the token was issued to is still registered and active for that
       same principal. This is the revocation point: deactivating a client stops every
       token already issued under it, which a self-contained JWT would otherwise outlive
       until ``exp``.
    4. The tenant row is active, and the principal named by the claims is still a row of
       it. The claims are a self-assertion about who the holder is; the row is the fact.
    """
    try:
        claims = validate_mcp_access_token(
            token,
            issuer=get_mcp_oauth_issuer(),
            audience=get_mcp_oauth_audience(),
        )
    except (OAuthTokenValidationError, RuntimeError) as exc:
        # RuntimeError too: no signing secret configured means no OAuth token can be
        # verified, which is "this bearer does not resolve", not an error for the buyer.
        logger.debug("OAuth access token validation failed: %s", exc)
        return None

    if claims.tenant_id != tenant_id:
        logger.warning(
            "An OAuth access token minted for tenant %r was presented to tenant %r, so it resolves to nobody",
            claims.tenant_id,
            tenant_id,
        )
        return None

    oauth_client = OAuthClientRepository(session).get_active(
        tenant_id=tenant_id,
        client_id=claims.client_id,
        principal_id=claims.principal_id,
    )
    if oauth_client is None:
        return None

    if TenantRepository(session).get_active(tenant_id) is None:
        return None

    row = PrincipalRepository(session, tenant_id).get(claims.principal_id)
    return Principal.from_row(row) if row else None


def get_principal_by_agent_url(agent_url: str, tenant_id: str) -> Principal | None:
    """The principal onboarded at *agent_url* inside *tenant_id*, or ``None``.

    The other way a request identifies its principal, and the newest: a valid RFC 9421
    signature. Verification establishes exactly one fact — "the request was issued by the
    agent whose ``jwks_uri`` contains the ``keyid``" (security.mdx @ v3.1.1 § Agent
    identity) — and names that agent by the ``agents[]`` entry whose ``jwks_uri`` resolved
    the key. So a verified signature IS a credential, and this is how it resolves to a
    principal when the caller presented no bearer at all — neither an OAuth access token
    nor an opaque buyer token, since both are answered above and both are terminal.

    Scoped to the tenant like the bearer lookups, and unique within it
    (``uq_principals_tenant_agent_url``), so the answer is one row rather than whichever
    sorted first.
    """

    def _lookup_principal(session):
        row = PrincipalRepository(session, tenant_id).find_by_agent_url(agent_url)
        return Principal.from_row(row) if row else None

    return execute_with_retry(_lookup_principal)


def get_principal_by_id(tenant_id: str, principal_id: str) -> Principal | None:
    """The principal *principal_id* names inside *tenant_id*, or ``None``.

    For resolution from stored ids (``resolved_identity.identity_of``): the owner of a
    media buy or creative a server-initiated job acts on.
    """

    def _lookup_principal(session):
        row = PrincipalRepository(session, tenant_id).get(principal_id)
        return Principal.from_row(row) if row else None

    return execute_with_retry(_lookup_principal)

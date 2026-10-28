"""``get_principal_from_token``: which bearer resolves to which principal, and which to nobody.

The merged module accepts TWO bearer forms and answers both with a ``Principal`` or ``None``
(``src/core/auth_utils.py``). Both are graded here against real objects: a first-party MCP
OAuth access token minted by ``issue_mcp_access_token`` and verified by the real
``validate_mcp_access_token``, and an opaque ``tok_`` buyer token matched on
``sha256(token)``. Nothing about the credential is faked — the JWT is really signed and really
verified, the OAuth client row is created by ``OAuthClientRepository`` and the principal row by
``PrincipalFactory`` — so a rejection here is the rejection production performs.

What is absent is the engine, because a unit test has no database: ``get_db_session`` hands
back an in-memory session that answers the repositories' ``select(Model).filter_by(...)``
from rows held in a list, applying every criterion. The repositories, the OAuth checks and
``Principal.from_row`` all run for real on top of it, and a tenant-scoped query really is
scoped.

Raising is NOT this module's job: ``None`` means "this bearer resolved to nobody", and
``src/core/resolved_identity.py`` turns that into AUTH_INVALID.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.sql.elements import BindParameter, False_, True_

from src.core.auth_utils import get_principal_from_token
from src.core.database.repositories.oauth_client import OAuthClientRepository
from src.core.oauth_service import generate_oauth_client_credentials, issue_mcp_access_token
from src.core.schemas import Principal
from tests.factories import PrincipalFactory, TenantFactory
from tests.factories.principal import plaintext_token_for

_SIGNING_KEY = "unit-test-mcp-oauth-signing-secret-32-bytes"
_ISSUER = "https://seller.example.com"
_AUDIENCE = "https://seller.example.com/mcp"

_TENANT_ID = "tenant_oauth"
_PRINCIPAL_ID = "principal_oauth"
_OTHER_TENANT_ID = "tenant_other"

#: The principal the seeded row names, which is what both bearer forms must resolve to.
_EXPECTED_PRINCIPAL = Principal(
    principal_id=_PRINCIPAL_ID,
    name="Acme Buying Desk",
    platform_mappings={"mock": {"advertiser_id": "adv_oauth"}},
    agent_url="https://buyer.example.com",
)


class _RowsResult:
    """What ``Session.scalars`` returns, for the one method the repositories call."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class _InMemorySession:
    """A session that answers ``select(Model).filter_by(...)`` from rows held in memory.

    Every ``filter_by`` criterion is applied, so ``PrincipalRepository``'s tenant scoping and
    ``OAuthClientRepository.get_active``'s ``is_active=True`` are really in force rather than
    assumed. ``add`` is here because the OAuth client row is created through its repository.
    """

    def __init__(self, *rows: Any) -> None:
        self._rows = list(rows)

    def __enter__(self) -> _InMemorySession:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def commit(self) -> None:
        """``execute_with_retry`` commits the read it just ran; the rows are the fixture."""

    def add(self, row: Any) -> None:
        self._rows.append(row)

    def scalars(self, stmt: Any) -> _RowsResult:
        entity = stmt.column_descriptions[0]["entity"]
        criteria = _criteria(stmt)
        return _RowsResult(
            [
                row
                for row in self._rows
                if isinstance(row, entity) and all(getattr(row, column) == value for column, value in criteria.items())
            ]
        )


def _criteria(stmt: Any) -> dict[str, Any]:
    """The ``{column: value}`` pairs a repository's ``filter_by`` chain put on *stmt*."""
    whereclause = stmt.whereclause
    clauses = getattr(whereclause, "clauses", (whereclause,))
    return {clause.left.key: _compared_value(clause.right) for clause in clauses}


def _compared_value(node: Any) -> Any:
    if isinstance(node, BindParameter):
        return node.value
    if isinstance(node, True_):
        return True
    if isinstance(node, False_):
        return False
    raise AssertionError(f"unsupported filter_by comparison: {node!r}")


@dataclass(frozen=True)
class _Seller:
    """One tenant with one principal and one registered OAuth client, plus their session."""

    tenant: Any
    principal: Any
    oauth_client: Any
    session: _InMemorySession


def _access_token(
    *,
    client_id: str,
    tenant_id: str = _TENANT_ID,
    principal_id: str = _PRINCIPAL_ID,
    issuer: str = _ISSUER,
    audience: str = _AUDIENCE,
    now: datetime | None = None,
    lifetime_seconds: int = 3600,
    signing_key: str = _SIGNING_KEY,
) -> str:
    """A real first-party MCP OAuth access token, signed exactly as production mints one."""
    return issue_mcp_access_token(
        tenant_id=tenant_id,
        principal_id=principal_id,
        client_id=client_id,
        issuer=issuer,
        audience=audience,
        now=now or datetime.now(UTC),
        lifetime_seconds=lifetime_seconds,
        signing_key=signing_key,
    )


@pytest.fixture
def seller(monkeypatch: pytest.MonkeyPatch) -> _Seller:
    tenant = TenantFactory.build(tenant_id=_TENANT_ID, is_active=True)
    principal = PrincipalFactory.build(
        tenant=tenant,
        principal_id=_PRINCIPAL_ID,
        name=_EXPECTED_PRINCIPAL.name,
        platform_mappings=_EXPECTED_PRINCIPAL.platform_mappings,
        agent_url=_EXPECTED_PRINCIPAL.agent_url,
    )
    session = _InMemorySession(tenant, principal)
    oauth_client = OAuthClientRepository(session).create_for_principal(
        tenant_id=_TENANT_ID,
        principal_id=_PRINCIPAL_ID,
        credentials=generate_oauth_client_credentials(),
    )

    # The deployment facts the OAuth verification reads: the signing secret, and the issuer
    # and audience a token must name. Set as environment so ``get_mcp_oauth_issuer`` and
    # ``get_mcp_oauth_audience`` answer them the way they do in production.
    monkeypatch.setenv("MCP_OAUTH_JWT_SECRET", _SIGNING_KEY)
    monkeypatch.setenv("MCP_OAUTH_ISSUER", _ISSUER)
    monkeypatch.setenv("MCP_OAUTH_AUDIENCE", _AUDIENCE)
    # The only absent part: the engine. ``execute_with_retry`` still opens, commits and
    # retries around the real repositories.
    monkeypatch.setattr("src.core.database.database_session.get_db_session", lambda: session)

    return _Seller(tenant=tenant, principal=principal, oauth_client=oauth_client, session=session)


def test_valid_oauth_access_token_resolves_to_the_principal_its_claims_name(seller: _Seller) -> None:
    token = _access_token(client_id=seller.oauth_client.client_id)

    assert get_principal_from_token(token, _TENANT_ID) == _EXPECTED_PRINCIPAL


def test_oauth_access_token_signed_with_another_key_resolves_to_nobody(seller: _Seller) -> None:
    token = _access_token(
        client_id=seller.oauth_client.client_id,
        signing_key="a-different-secret-that-this-deployment-never-signed-with",
    )

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_oauth_access_token_from_another_issuer_resolves_to_nobody(seller: _Seller) -> None:
    token = _access_token(client_id=seller.oauth_client.client_id, issuer="https://attacker.example.com")

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_oauth_access_token_for_another_audience_resolves_to_nobody(seller: _Seller) -> None:
    token = _access_token(client_id=seller.oauth_client.client_id, audience="https://seller.example.com/admin")

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_expired_oauth_access_token_resolves_to_nobody(seller: _Seller) -> None:
    """Expired by an hour, which is well past ``validate_mcp_access_token``'s 30s leeway."""
    token = _access_token(
        client_id=seller.oauth_client.client_id,
        now=datetime.now(UTC) - timedelta(hours=2),
        lifetime_seconds=3600,
    )

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_oauth_access_token_minted_for_another_tenant_resolves_to_nobody(seller: _Seller) -> None:
    """The mandatory tenant-claim match: a token naming one seller, presented to another."""
    token = _access_token(client_id=seller.oauth_client.client_id, tenant_id=_OTHER_TENANT_ID)

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_revoking_the_oauth_client_stops_a_token_already_issued_under_it(seller: _Seller) -> None:
    """The revocation point: deactivating the client outlives nothing, not even ``exp``."""
    token = _access_token(client_id=seller.oauth_client.client_id)
    assert get_principal_from_token(token, _TENANT_ID) == _EXPECTED_PRINCIPAL

    seller.oauth_client.is_active = False

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_oauth_access_token_naming_an_unregistered_client_resolves_to_nobody(seller: _Seller) -> None:
    token = _access_token(client_id="mcp_client_never_registered")

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_oauth_access_token_resolves_to_nobody_once_the_tenant_is_deactivated(seller: _Seller) -> None:
    token = _access_token(client_id=seller.oauth_client.client_id)
    assert get_principal_from_token(token, _TENANT_ID) == _EXPECTED_PRINCIPAL

    seller.tenant.is_active = False

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_oauth_access_token_whose_principal_is_not_a_row_resolves_to_nobody(seller: _Seller) -> None:
    """The claims are a self-assertion about who the holder is; the row is the fact."""
    vanished_principal_id = "principal_vanished"
    oauth_client = OAuthClientRepository(seller.session).create_for_principal(
        tenant_id=_TENANT_ID,
        principal_id=vanished_principal_id,
        credentials=generate_oauth_client_credentials(),
    )
    token = _access_token(client_id=oauth_client.client_id, principal_id=vanished_principal_id)

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_oauth_access_token_resolves_to_nobody_when_no_signing_secret_is_configured(
    seller: _Seller, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No secret configured means no OAuth token can be verified, which is not an error."""
    token = _access_token(client_id=seller.oauth_client.client_id)
    monkeypatch.delenv("MCP_OAUTH_JWT_SECRET")

    assert get_principal_from_token(token, _TENANT_ID) is None


def test_opaque_buyer_token_resolves_by_token_hash(seller: _Seller) -> None:
    """The fallback form: an opaque ``tok_`` value whose ``sha256`` the row stores."""
    assert get_principal_from_token(plaintext_token_for(_PRINCIPAL_ID), _TENANT_ID) == _EXPECTED_PRINCIPAL


def test_opaque_buyer_token_does_not_resolve_inside_another_tenant(seller: _Seller) -> None:
    assert get_principal_from_token(plaintext_token_for(_PRINCIPAL_ID), _OTHER_TENANT_ID) is None


def test_bearer_that_is_neither_form_resolves_to_nobody(seller: _Seller) -> None:
    assert get_principal_from_token("tok_this_token_was_never_issued", _TENANT_ID) is None

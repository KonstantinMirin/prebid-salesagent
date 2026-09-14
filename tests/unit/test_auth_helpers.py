"""Unit tests for shared API key auth helper.

Tests the extracted auth helper that both tenant_management_api.py
and sync_api.py delegate to.

"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import AdCPAuthenticationError
from tests.factories import PrincipalFactory


class TestRequirePrincipalId:
    """The require_principal_id entry guard (gh-1307).

    Single source of truth for the "identity has no principal_id" guard that
    every _impl runs at entry. Returns the validated principal_id or raises
    AdCPAuthenticationError with one canonical message.
    """

    def test_returns_principal_id_when_present(self):
        from src.core.auth import require_principal_id

        identity = PrincipalFactory.make_identity(principal_id="p1", tenant_id="t1")

        assert require_principal_id(identity) == "p1"

    def test_raises_canonical_error_when_principal_id_is_none(self):
        from src.core.auth import require_principal_id

        identity = PrincipalFactory.make_identity(principal_id=None, tenant_id="t1")

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            require_principal_id(identity)

    def test_raises_canonical_error_when_principal_id_is_empty(self):
        from src.core.auth import require_principal_id

        identity = PrincipalFactory.make_identity(principal_id="", tenant_id="t1")

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            require_principal_id(identity)

    def test_preserves_context_kwarg_onto_the_exception(self):
        from src.core.auth import require_principal_id

        sentinel_context = {"request_id": "req-123"}
        identity = PrincipalFactory.make_identity(principal_id=None, tenant_id="t1")

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            require_principal_id(identity, context=sentinel_context)

        assert exc_info.value.context == sentinel_context


class TestRequireTenant:
    """The require_tenant entry guard (gh-1307).

    Single source of truth for the "no tenant context available" guard — the
    most-repeated _impl prologue. Returns identity.tenant or raises
    AdCPAuthenticationError with one canonical, actionable message.
    """

    def test_returns_tenant_when_present(self):
        from src.core.auth import require_tenant

        identity = PrincipalFactory.make_identity(principal_id="p1", tenant_id="t1")

        assert require_tenant(identity) == identity.tenant

    def test_raises_canonical_error_when_tenant_is_none(self):
        from src.core.auth import require_tenant

        identity = PrincipalFactory.make_identity(principal_id=None, tenant_id="t1", tenant=None)

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            require_tenant(identity)

    def test_preserves_context_kwarg_onto_the_exception(self):
        from src.core.auth import require_tenant

        sentinel_context = {"request_id": "req-456"}
        identity = PrincipalFactory.make_identity(principal_id=None, tenant_id="t1", tenant=None)

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            require_tenant(identity, context=sentinel_context)

        assert exc_info.value.context == sentinel_context


class _FakeConfigStore:
    """Stands in for TenantManagementConfigRepository over a dict.

    The repository's own interface, so what these tests grade is what auth_helpers
    hands the store and what it asks back — not a mock's call log. Keyed the way the
    real rows are keyed, via the shared ``prefix_config_key``, so a change to that
    derivation breaks here too.
    """

    rows: dict[str, str] = {}

    def __init__(self, session=None):
        pass

    def api_key_digest(self, config_key):
        return self.rows.get(config_key)

    def api_key_prefix(self, config_key):
        from src.core.database.repositories.tenant_management_config import prefix_config_key

        return self.rows.get(prefix_config_key(config_key))

    def store_api_key(self, config_key, *, digest, prefix, description):
        from src.core.database.repositories.tenant_management_config import prefix_config_key

        self.rows[config_key] = digest
        self.rows[prefix_config_key(config_key)] = prefix


@pytest.fixture
def fake_config_store():
    """auth_helpers wired to an in-memory store, with its session context neutralized."""
    _FakeConfigStore.rows = {}
    with (
        patch("src.admin.auth_helpers.TenantManagementConfigRepository", _FakeConfigStore),
        patch("src.admin.auth_helpers.get_db_session") as mock_db,
    ):
        # A session whose only job is to be commit-able; the store above is the state.
        mock_db.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_db.return_value.__exit__ = MagicMock(return_value=False)
        yield _FakeConfigStore.rows


class TestStoredApiKeyIsHashed:
    """The operator API key is minted once, stored as sha256, and matched by hash.

    Same treatment as a principal token (salesagent-3cs7o.7): the row used to hold the
    plaintext and hand it back on every call, so anyone who could read the table — or
    call the initializer — held a working credential.
    """

    def test_mint_stores_sha256_and_prefix_and_returns_the_plaintext_once(self, fake_config_store):
        import hashlib

        from src.admin.auth_helpers import mint_stored_api_key

        key = mint_stored_api_key("test_config_key", "a description")

        assert key.startswith("sk_")
        assert fake_config_store["test_config_key"] == hashlib.sha256(key.encode("utf-8")).hexdigest()
        assert fake_config_store["test_config_key_prefix"] == key[:12]
        # The plaintext exists in the return value and NOWHERE in the store. The prefix
        # row is a 12-character head, which is not the key and cannot be presented as one.
        assert key not in fake_config_store.values()

    def test_matching_hashes_the_presented_key_rather_than_comparing_a_stored_plaintext(self, fake_config_store):
        from src.admin.auth_helpers import api_key_matches, mint_stored_api_key

        key = mint_stored_api_key("test_config_key", "a description")

        assert api_key_matches(key, None, "test_config_key") is True
        assert api_key_matches("sk_not-the-key", None, "test_config_key") is False
        # The stored digest itself is not a credential: presenting it does not authenticate.
        assert api_key_matches(fake_config_store["test_config_key"], None, "test_config_key") is False

    def test_rotation_invalidates_the_previous_key(self, fake_config_store):
        from src.admin.auth_helpers import api_key_matches, mint_stored_api_key

        first = mint_stored_api_key("test_config_key", "a description")
        second = mint_stored_api_key("test_config_key", "a description")

        assert first != second
        assert api_key_matches(first, None, "test_config_key") is False
        assert api_key_matches(second, None, "test_config_key") is True

    def test_the_settings_value_wins_and_is_compared_as_the_plaintext_it_is(self, fake_config_store):
        from src.admin.auth_helpers import api_key_matches, mint_stored_api_key

        stored = mint_stored_api_key("test_config_key", "a description")

        # An operator-supplied deployment secret is a plaintext this process was handed,
        # not a row this application minted, so it is compared directly — and it wins.
        assert api_key_matches("env-key", "env-key", "test_config_key") is True
        assert api_key_matches(stored, "env-key", "test_config_key") is False

    def test_configured_check_answers_existence_without_recovering_a_key(self, fake_config_store):
        from src.admin.auth_helpers import api_key_is_configured, api_key_prefix, mint_stored_api_key

        assert api_key_is_configured(None, "test_config_key") is False
        assert api_key_prefix("test_config_key") is None

        key = mint_stored_api_key("test_config_key", "a description")

        assert api_key_is_configured(None, "test_config_key") is True
        assert api_key_prefix("test_config_key") == key[:12]


class TestRequireApiKeyAuth:
    """Test the decorator factory."""

    def test_missing_header_returns_401(self):
        """Request without the auth header returns 401."""
        from src.admin.auth_helpers import require_api_key_auth

        decorator = require_api_key_auth(env_var="TEST_KEY", config_key="test_key", header="X-Test-Key")

        @decorator
        def protected_view():
            return {"data": "secret"}, 200

        from flask import Flask

        app = Flask(__name__)
        app.add_url_rule("/test", view_func=protected_view)
        with app.test_client() as client:
            resp = client.get("/test")
            assert resp.status_code == 401

    def test_unconfigured_key_returns_503(self):
        """When no key is configured anywhere, returns 503."""
        from src.admin.auth_helpers import require_api_key_auth

        decorator = require_api_key_auth(env_var="UNCONFIGURED_KEY_XYZ", config_key="nonexistent", header="X-Test-Key")

        @decorator
        def protected_view():
            return {"data": "secret"}, 200

        from flask import Flask

        app = Flask(__name__)
        app.add_url_rule("/test", view_func=protected_view)

        with patch("src.admin.auth_helpers.get_db_session") as mock_db:
            mock_session = MagicMock()
            mock_session.scalars.return_value.first.return_value = None
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            with app.test_client() as client:
                resp = client.get("/test", headers={"X-Test-Key": "any-key"})
                assert resp.status_code == 503

    def test_valid_key_passes_through(self):
        """Correct key allows request through."""
        from src.admin.auth_helpers import require_api_key_auth

        decorator = require_api_key_auth(env_var="TEST_VALID_KEY", config_key="test_key", header="X-Test-Key")

        @decorator
        def protected_view():
            return {"data": "secret"}, 200

        from flask import Flask

        app = Flask(__name__)
        app.add_url_rule("/test", view_func=protected_view)

        with patch.dict("os.environ", {"TEST_VALID_KEY": "correct-key"}):
            with app.test_client() as client:
                resp = client.get("/test", headers={"X-Test-Key": "correct-key"})
                assert resp.status_code == 200

    def test_wrong_key_returns_401(self):
        """Incorrect key returns 401."""
        from src.admin.auth_helpers import require_api_key_auth

        decorator = require_api_key_auth(env_var="TEST_WRONG_KEY", config_key="test_key", header="X-Test-Key")

        @decorator
        def protected_view():
            return {"data": "secret"}, 200

        from flask import Flask

        app = Flask(__name__)
        app.add_url_rule("/test", view_func=protected_view)

        with patch.dict("os.environ", {"TEST_WRONG_KEY": "correct-key"}):
            with app.test_client() as client:
                resp = client.get("/test", headers={"X-Test-Key": "wrong-key"})
                assert resp.status_code == 401

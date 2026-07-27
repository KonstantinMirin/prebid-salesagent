"""E2E tests: Admin account management BDD scenarios against Docker stack.

Runs the same 10 admin BDD scenarios from BR-ADMIN-ACCOUNTS.feature
using requests.Session against the full Docker stack (instead of Flask
test_client used by the integration BDD suite).

Requires: ADCP_SALES_PORT set (Docker stack running).
The docker_services_e2e fixture from tests/e2e/conftest.py handles
Docker lifecycle, or the stack can be pre-started via make test-stack-up.

The test creates accounts directly in the e2e database via psycopg2,
authenticates via /test/auth, and validates HTML responses and JSON APIs
through real HTTP requests against nginx -> FastAPI -> admin blueprint.
"""

from __future__ import annotations

import os

import pytest
import requests

from tests.e2e.conftest import e2e_host


@pytest.fixture()
def admin_e2e_env(docker_services_e2e):
    """Provide AdminAccountEnv in e2e mode against Docker stack.

    Sets ADCP_SALES_PORT from the Docker services fixture so the harness
    auto-detects e2e mode.
    """
    ports = docker_services_e2e
    admin_port = ports["admin_port"]

    # Ensure the env var is set for AdminAccountEnv auto-detection
    old_port = os.environ.get("ADCP_SALES_PORT")
    os.environ["ADCP_SALES_PORT"] = str(admin_port)

    # Also set DATABASE_URL to point at the e2e Postgres (the SERVER's /adcp DB).
    # In-network the runner exports E2E_DATABASE_URL (postgres:5432/adcp, no host
    # port); on the host path build localhost:<published-port>.
    old_db = os.environ.get("DATABASE_URL")
    pg_port = ports["postgres_port"]
    db_host = os.environ.get("ADCP_TEST_DB_HOST", "localhost")
    db_port = os.environ.get("ADCP_TEST_DB_PORT", str(pg_port))
    os.environ["DATABASE_URL"] = os.environ.get("E2E_DATABASE_URL") or (
        f"postgresql://adcp_user:secure_password_change_me@{db_host}:{db_port}/adcp"
    )

    from tests.harness.admin_accounts import AdminAccountEnv

    with AdminAccountEnv(mode="e2e") as env:
        yield env

    # Restore env vars
    if old_port is not None:
        os.environ["ADCP_SALES_PORT"] = old_port
    else:
        os.environ.pop("ADCP_SALES_PORT", None)
    if old_db is not None:
        os.environ["DATABASE_URL"] = old_db
    else:
        os.environ.pop("DATABASE_URL", None)


class TestAdminAccountsE2E:
    """E2E tests for admin account management against Docker stack.

    These test the same scenarios as BR-ADMIN-ACCOUNTS.feature but through
    real HTTP requests instead of Flask test_client.
    """

    def test_health_check(self, docker_services_e2e):
        """Verify the Docker stack is healthy before running admin tests."""
        port = docker_services_e2e["admin_port"]
        resp = requests.get(f"http://{e2e_host()}:{port}/health", timeout=5)
        assert resp.status_code == 200

    def test_list_accounts_page(self, admin_e2e_env):
        """T-ADMIN-ACCT-001: List accounts returns 200 with Accounts heading."""
        env = admin_e2e_env
        env.authenticate()
        response = env.get_list_page()
        assert response.status_code == 200
        html = response.data.decode()
        assert "Accounts" in html

    def test_create_account_page(self, admin_e2e_env):
        """T-ADMIN-ACCT-002: Create account page returns 200."""
        env = admin_e2e_env
        env.authenticate()
        response = env.get_create_page()
        assert response.status_code == 200
        html = response.data.decode()
        assert "Create New Account" in html

    def test_create_account_submit(self, admin_e2e_env):
        """T-ADMIN-ACCT-002: Create account form submission redirects to list."""
        env = admin_e2e_env
        env.authenticate()
        response = env.post_create(
            {
                "name": "E2E Test Corp",
                "brand_domain": "e2e-test.com",
                "operator": "test-operator",
                "billing": "operator",
                "payment_terms": "net_30",
            }
        )
        # Successful create returns redirect (302/303) or 200 if followed
        assert response.status_code in (200, 302, 303), f"Expected success/redirect, got {response.status_code}"

    def test_account_detail_page(self, admin_e2e_env):
        """T-ADMIN-ACCT-003: Account detail page shows status badge."""
        env = admin_e2e_env
        env.authenticate()
        account_id = env.create_account(name="E2E Detail Corp", status="active")
        response = env.get_detail_page(account_id)
        assert response.status_code == 200
        html = response.data.decode()
        assert "E2E Detail Corp" in html
        assert "status-active" in html

    def test_edit_account_page(self, admin_e2e_env):
        """T-ADMIN-ACCT-004: Edit account page shows edit form."""
        env = admin_e2e_env
        env.authenticate()
        account_id = env.create_account(name="E2E Edit Corp", status="active")
        response = env.get_edit_page(account_id)
        assert response.status_code == 200
        html = response.data.decode()
        assert "Edit" in html

    def test_edit_page_does_not_offer_natural_key_components(self, admin_e2e_env):
        """T-ADMIN-ACCT-011: natural-key controls are not editable (real stack).

        The in-process BDD scenario grades this against the Flask test client;
        this is the same claim served by the real templates over real HTTP, which
        is where a template that failed to render (or rendered from a stale
        image) would show up.

        `operator` and `sandbox` are natural-key components
        (AccountRepository.get_by_natural_key). Editing either RE-KEYS the
        account, so the buyer's next sync_accounts call carrying the original key
        provisions a DUPLICATE instead of matching (salesagent-8sfr). The
        repository refuses both; this asserts the operator is not invited to
        attempt a change that would then be silently discarded.
        """
        import re

        env = admin_e2e_env
        env.authenticate()
        account_id = env.create_account(name="E2E NaturalKey Corp", status="active")
        response = env.get_edit_page(account_id)
        assert response.status_code == 200
        html = response.data.decode()

        for field in ("sandbox", "operator"):
            match = re.search(rf'<input[^>]*\bname="{field}"[^>]*>', html)
            assert match, f'No <input name="{field}"> on the edit page'
            tag = match.group(0)
            assert "disabled" in tag or "readonly" in tag, (
                f'The "{field}" control is editable on the live edit page: {tag}'
            )

    def test_status_change_json(self, admin_e2e_env):
        """T-ADMIN-ACCT-005: Status change via JSON API returns success."""
        env = admin_e2e_env
        env.authenticate()
        account_id = env.create_account(name="E2E Status Corp", status="active")
        response = env.post_status_change(account_id, "suspended")
        data = response.get_json()
        assert data["success"] is True
        assert data["status"] == "suspended"

    def test_invalid_status_transition(self, admin_e2e_env):
        """T-ADMIN-ACCT-006: Invalid status transition returns 400."""
        env = admin_e2e_env
        env.authenticate()
        account_id = env.create_account(name="E2E Invalid Corp", status="active")
        response = env.post_status_change(account_id, "rejected")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_filter_by_status(self, admin_e2e_env):
        """T-ADMIN-ACCT-007: Status filter narrows account list."""
        env = admin_e2e_env
        env.authenticate()
        env.create_account(name="E2E Active", status="active")
        env.create_account(name="E2E Closed", status="closed")
        response = env.get_list_page(status_filter="active")
        assert response.status_code == 200
        html = response.data.decode()
        assert "E2E Active" in html
        assert "E2E Closed" not in html

    def test_unauthenticated_access(self, admin_e2e_env):
        """T-ADMIN-ACCT-009: Unauthenticated access gets redirected."""
        env = admin_e2e_env
        env.clear_auth()
        response = env.get_list_page()
        assert response.status_code in (302, 303, 401)

    def test_terminal_status_no_buttons(self, admin_e2e_env):
        """T-ADMIN-ACCT-010: Terminal status shows no action buttons."""
        env = admin_e2e_env
        env.authenticate()
        account_id = env.create_account(name="E2E Closed Corp", status="closed")
        response = env.get_detail_page(account_id)
        assert response.status_code == 200
        html = response.data.decode()
        assert 'onclick="changeStatus(' not in html

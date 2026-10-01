"""``GET /tls/ask``: the reverse proxy's on-demand TLS gate, against real tenant rows.

Caddy calls the endpoint with ``?domain=<host>`` before it requests a certificate and
issues only on a 2xx. These cases drive the real ASGI app over PostgreSQL, so the active
filter and the two unique-key lookups are the ones production runs.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from tests.factories import TenantFactory
from tests.helpers.settings_injection import inject_runtime

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

APEX = "agent.example.com"


@pytest.fixture
def client(factory_session, monkeypatch):
    from src.app import app

    inject_runtime(monkeypatch, sales_agent_domain=APEX, admin_domain=None)
    TenantFactory(tenant_id="t_acme", subdomain="acme", virtual_host="ads.publisher.example")
    TenantFactory(tenant_id="t_gone", subdomain="gone", virtual_host="old.publisher.example", is_active=False)
    return TestClient(app)


@pytest.mark.parametrize(
    "host", [APEX, f"admin.{APEX}", f"acme.{APEX}", "ads.publisher.example", f"ACME.{APEX}.", "Ads.Publisher.Example"]
)
def test_served_host_is_allowed(client, host):
    response = client.get("/tls/ask", params={"domain": host})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        f"gone.{APEX}",
        "old.publisher.example",
        f"nobody.{APEX}",
        f"x.acme.{APEX}",
        f"acme.{APEX}.evil.example",
        "random.example.org",
        f"*.{APEX}",
        "ads.publisher.example:443",
        "",
    ],
)
def test_unserved_host_is_refused(client, host):
    response = client.get("/tls/ask", params={"domain": host})
    assert response.status_code == 403


def test_missing_domain_parameter_is_refused(client):
    assert client.get("/tls/ask").status_code == 403

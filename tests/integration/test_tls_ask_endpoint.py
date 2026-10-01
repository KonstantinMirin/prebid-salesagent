"""``GET /tls/ask``: the reverse proxy's on-demand TLS gate, against real tenant rows.

Caddy calls the endpoint with ``?domain=<host>`` before it requests a certificate and
issues only on a 2xx. These cases drive the real ASGI app over PostgreSQL, so the active
filter and the ``virtual_host`` lookup are the ones production runs.

A tenant is served at the host it declares as its ``virtual_host`` and nowhere else, so a
tenant's ``subdomain`` under ``SALES_AGENT_DOMAIN`` is NOT a served host unless the tenant
declares it.
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
    TenantFactory(tenant_id="t_beta", subdomain="beta", virtual_host=f"beta.{APEX}")
    TenantFactory(tenant_id="t_port", subdomain="port", virtual_host="alt.publisher.example:8443")
    TenantFactory(tenant_id="t_gone", subdomain="gone", virtual_host="old.publisher.example", is_active=False)
    return TestClient(app)


@pytest.mark.parametrize(
    "host",
    [
        APEX,
        f"admin.{APEX}",
        "ads.publisher.example",
        "Ads.Publisher.Example",
        "ads.publisher.example.",
        f"beta.{APEX}",
        "alt.publisher.example",
    ],
)
def test_served_host_is_allowed(client, host):
    response = client.get("/tls/ask", params={"domain": host})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        f"acme.{APEX}",
        "old.publisher.example",
        f"gone.{APEX}",
        f"nobody.{APEX}",
        f"x.beta.{APEX}",
        f"beta.{APEX}.evil.example",
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

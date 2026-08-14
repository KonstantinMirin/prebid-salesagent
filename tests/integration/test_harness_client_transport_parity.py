"""Transport parity for AdCPTestClient, against a real database.

Lives in tests/integration/ rather than beside the rest of the client's tests in
tests/harness/test_client.py because these two need PostgreSQL: they drive REST
dispatch through get_rest_client() and seed real rows via the ORM factories.

tox's `unit` env collects `tests/unit/ tests/harness/` with DATABASE_URL unset --
"no database, no server", as its own description says -- so a db-requiring test
under tests/harness/ fails at fixture setup with a connection refusal, and no
other env collects that directory to catch it. Keeping the split by directory,
the way the rest of the suite does, is what makes the marker unnecessary.
"""

from __future__ import annotations

import pytest

from tests.harness._base import BareIntegrationEnv
from tests.harness.client import AdCPTestClient
from tests.harness.transport import Transport


@pytest.mark.integration
@pytest.mark.requires_db
class TestClientTransportParity:
    """The client's core promise: the SAME call() drives MCP/A2A/REST identically
    (CLAUDE.md Pattern #7 "Transport parity") — using tests.harness.product.ProductEnv
    (the IntegrationEnv/real-DB variant) so REST dispatch (which needs
    get_rest_client()) is available alongside MCP/A2A."""

    def test_get_products_identical_across_all_three_transports(self, integration_db):
        from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
        from tests.harness.product import ProductEnv

        with ProductEnv(tenant_id="client-parity", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="client-parity", subdomain="client-parity")
            PrincipalFactory(tenant=tenant, principal_id="p1")
            product = ProductFactory(tenant=tenant, product_id="prod_parity")
            PricingOptionFactory(product=product)

            client = AdCPTestClient(env)

            mcp_result = client.call("get_products", {"brief": "video ads"}, Transport.MCP)
            a2a_result = client.call("get_products", {"brief": "video ads"}, Transport.A2A)
            rest_result = client.call("get_products", {"brief": "video ads"}, Transport.REST)

        assert mcp_result.is_success, mcp_result.error
        assert a2a_result.is_success, a2a_result.error
        assert rest_result.is_success, rest_result.error

        # payload is the pinned GetProductsResponse model on every transport —
        # attribute access, not subscripting (salesagent-vuz9t.8.3).
        mcp_ids = {p.product_id for p in mcp_result.payload.products}
        a2a_ids = {p.product_id for p in a2a_result.payload.products}
        rest_ids = {p.product_id for p in rest_result.payload.products}

        assert mcp_ids == {"prod_parity"}
        assert mcp_ids == a2a_ids == rest_ids

    def test_rest_unauthenticated_dispatch_surfaces_auth_required(self, integration_db):
        with BareIntegrationEnv(tenant_id="client-parity-noauth", principal_id="p1") as env:
            client = AdCPTestClient(env)
            result = client.call("list_accounts", {}, Transport.REST, identity=None)

        assert result.is_error
        result.assert_wire_error("AUTH_REQUIRED")

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
class TestClientCrossTransportConsistency:
    """AdCPTestClient's own promise: the SAME call() drives MCP/A2A/REST identically
    (CLAUDE.md Pattern #7 "Transport parity") — using tests.harness.product.ProductEnv
    (the IntegrationEnv/real-DB variant) so REST dispatch (which needs
    get_rest_client()) is available alongside MCP/A2A.

    Renamed from "TestClientTransportParity" (salesagent-vuz9t.10, Finding 6):
    these tests compare AdCPTestClient against ITSELF across three transports —
    real, valuable coverage, but NOT the env.call_via() vs
    AdCPTestClient(env).call() equivalence the old name implied. That
    comparison — the actual migration precondition — is
    TestEnvVsClientEquivalence below.
    """

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


@pytest.mark.integration
@pytest.mark.requires_db
class TestEnvVsClientEquivalence:
    """The migration precondition (salesagent-vuz9t.10, Finding 6): prove
    ``env.call_via(T, ...)`` and ``AdCPTestClient(env).call(..., T)`` dispatch
    the same production code, on the SAME env, and produce an IDENTICAL
    wire-visible contract — for a success case AND an error case, per
    in-process transport family (MCP/A2A/REST). Until every one of these
    holds, migrating the 33 existing envs onto the client (tracked as the
    roadmap follow-up, out of scope here) is unsafe: a silent divergence
    between the two entry points is exactly the class of regression that
    migration must not introduce.

    The error direction dispatches a REAL unauthenticated request (not a
    mock) through each transport's error mapper — ``_mcp_error_to_result`` /
    ``_a2a_error_to_result`` / ``_rest_error_to_result`` in
    ``tests/harness/client.py`` — so it is deletion-sensitive: removing
    ``wire_error_envelope=`` from ``_mcp_error_to_result`` makes
    ``test_mcp_success_and_error_equivalence`` fail with "no
    wire_error_envelope was captured" (verified by hand during this change).
    """

    @staticmethod
    def _assert_success_equivalent(via, client_result) -> None:
        assert via.is_success, via.error
        assert client_result.is_success, client_result.error
        assert via.envelope.get("transport") == client_result.envelope.get("transport")
        assert via.wire_response == client_result.wire_response

    @staticmethod
    def _assert_error_equivalent(via, client_result, code: str) -> None:
        assert via.is_error, "env.call_via unexpectedly succeeded"
        assert client_result.is_error, "AdCPTestClient.call unexpectedly succeeded"
        via.assert_wire_error(code)
        client_result.assert_wire_error(code)
        assert via.wire_error_envelope == client_result.wire_error_envelope

    def test_mcp_success_and_error_equivalence(self, integration_db):
        from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
        from tests.harness.account_list import AccountListEnv
        from tests.harness.product import ProductEnv

        with ProductEnv(tenant_id="ev-mcp-s", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="ev-mcp-s", subdomain="ev-mcp-s")
            PrincipalFactory(tenant=tenant, principal_id="p1")
            product = ProductFactory(tenant=tenant, product_id="prod_ev_mcp")
            PricingOptionFactory(product=product)

            via = env.call_via(Transport.MCP, brief="video ads")
            client_result = AdCPTestClient(env).call("get_products", {"brief": "video ads"}, Transport.MCP)

        self._assert_success_equivalent(via, client_result)

        with AccountListEnv(tenant_id="ev-mcp-e", principal_id="p1") as env:
            via = env.call_via(Transport.MCP, identity=None)
            client_result = AdCPTestClient(env).call("list_accounts", {}, Transport.MCP, identity=None)

        self._assert_error_equivalent(via, client_result, "AUTH_REQUIRED")

    def test_a2a_success_and_error_equivalence(self, integration_db):
        from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
        from tests.harness.account_list import AccountListEnv
        from tests.harness.product import ProductEnv

        with ProductEnv(tenant_id="ev-a2a-s", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="ev-a2a-s", subdomain="ev-a2a-s")
            PrincipalFactory(tenant=tenant, principal_id="p1")
            product = ProductFactory(tenant=tenant, product_id="prod_ev_a2a")
            PricingOptionFactory(product=product)

            via = env.call_via(Transport.A2A, brief="video ads")
            client_result = AdCPTestClient(env).call("get_products", {"brief": "video ads"}, Transport.A2A)

        self._assert_success_equivalent(via, client_result)

        with AccountListEnv(tenant_id="ev-a2a-e", principal_id="p1") as env:
            via = env.call_via(Transport.A2A, identity=None)
            client_result = AdCPTestClient(env).call("list_accounts", {}, Transport.A2A, identity=None)

        self._assert_error_equivalent(via, client_result, "AUTH_REQUIRED")

    def test_rest_success_and_error_equivalence(self, integration_db):
        from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
        from tests.harness.account_list import AccountListEnv
        from tests.harness.product import ProductEnv

        with ProductEnv(tenant_id="ev-rest-s", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="ev-rest-s", subdomain="ev-rest-s")
            PrincipalFactory(tenant=tenant, principal_id="p1")
            product = ProductFactory(tenant=tenant, product_id="prod_ev_rest")
            PricingOptionFactory(product=product)

            via = env.call_via(Transport.REST, brief="video ads")
            client_result = AdCPTestClient(env).call("get_products", {"brief": "video ads"}, Transport.REST)

        self._assert_success_equivalent(via, client_result)

        with AccountListEnv(tenant_id="ev-rest-e", principal_id="p1") as env:
            via = env.call_via(Transport.REST, identity=None)
            client_result = AdCPTestClient(env).call("list_accounts", {}, Transport.REST, identity=None)

        self._assert_error_equivalent(via, client_result, "AUTH_REQUIRED")

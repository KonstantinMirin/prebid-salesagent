"""ProductEnv — integration test environment for _get_products_impl.

Two envs live here: ``ProductEnv`` (everything external mocked) and
``RealResolverProductEnv`` (identical, minus the ``resolve_property_list``
patch) for the tests that must reach the real property-list resolver and the
real egress seam.

Patches: PolicyCheckService, generate_variants_for_brief,
         get_factory (ranking), resolve_property_list.
Real: ProductUoW, get_principal_object, convert_product_model_to_schema,
      DynamicPricingService, adapter metadata, audit logger, get_db_session.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    async def test_something(self, integration_db):
        with ProductEnv() as env:
            tenant = TenantFactory(tenant_id="t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="p1")
            ProductFactory(tenant=tenant)
            PricingOptionFactory(product__tenant=tenant)

            response = await env.call_impl(brief="video ads")
            assert len(response.products) >= 1

Available mocks via env.mock:
    "policy_service"       -- PolicyCheckService class mock
    "dynamic_variants"     -- generate_variants_for_brief AsyncMock
    "ranking_factory"      -- get_factory mock (AI ranking)
    "resolve_property_list" -- resolve_property_list AsyncMock

Transport support:
    call_impl(**kw)          -- direct _get_products_impl (sync wrapper around async)
    call_a2a(**kw)           -- get_products_raw A2A wrapper
    call_mcp(**kw)           -- get_products via the registered MCP client
    build_rest_body(**kw)    -- POST /api/v1/products body
    parse_rest_response(d)   -- JSON -> GetProductsResponse
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from src.core.schemas import GetProductsResponse
from tests.harness._base import IntegrationEnv
from tests.harness._mixins import ProductMixin
from tests.harness.egress import EgressHatchMixin


class ProductEnv(ProductMixin, IntegrationEnv):
    """Integration test environment for _get_products_impl.

    Only mocks external services (policy, dynamic variants,
    AI ranking, property list resolution). Everything else is real:
    - Real ProductUoW -> real DB queries
    - Real get_principal_object -> real DB queries
    - Real convert_product_model_to_schema -> real conversion
    - Real DynamicPricingService -> real DB queries (FormatPerformanceMetrics)
    - Real audit logging

    Fluent API (from ProductMixin):
        set_policy_approved()            -- policy check returns approved
        set_policy_blocked(reason)       -- policy check returns blocked
        set_dynamic_variants(variants)   -- configure dynamic variant generation
        set_property_list(ids)           -- configure property list resolver
        set_ranking_disabled()           -- disable AI ranking
        call_impl(brief, **kw)           -- call _get_products_impl
    """

    EXTERNAL_PATCHES = {
        "policy_service": "src.core.tools.products.PolicyCheckService",
        "dynamic_variants": "src.services.dynamic_products.generate_variants_for_brief",
        "ranking_factory": "src.services.ai.factory.get_factory",
        "resolve_property_list": "src.core.property_list_resolver.resolve_property_list",
    }

    ASYNC_PATCHES = {"dynamic_variants", "resolve_property_list"}

    REST_ENDPOINT = "/api/v1/products"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def _configure_mocks(self) -> None:
        self._configure_product_mocks()

    def call_impl(self, **kwargs: Any) -> Any:  # type: ignore[override]
        """Call _get_products_impl — async-aware sync bridge.

        ProductMixin.call_impl is async. This bridge detects the calling context:
        - Async (``await env.call_impl(...)``): returns the coroutine for awaiting
        - Sync (BDD steps, ImplDispatcher): uses ``asyncio.run()``
        """
        coro = super().call_impl(**kwargs)
        try:
            asyncio.get_running_loop()
            # Already in async context (e.g., @pytest.mark.asyncio test)
            # Return the coroutine so ``await`` works
            return coro
        except RuntimeError:
            # No running loop — safe to block with asyncio.run
            return asyncio.run(coro)

    def call_a2a(self, **kwargs: Any) -> GetProductsResponse:
        """Call get_products via real AdCPRequestHandler — full A2A pipeline."""
        return self._run_a2a_handler("get_products", GetProductsResponse, **kwargs)

    def call_mcp(self, **kwargs: Any) -> GetProductsResponse:
        """Call get_products via Client(mcp) — full pipeline dispatch."""
        return self._run_mcp_client("get_products", GetProductsResponse, **kwargs)

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Convert kwargs to GetProductsBody shape for REST POST.

        The field list is read off ``GetProductsBody`` itself rather than repeated
        here. A hardcoded copy silently dropped ``property_list`` when the route
        gained it (salesagent-sxl4), so a REST case could send the field, have it
        discarded by the harness, and pass — grading nothing.
        """
        from src.routes.api_v1 import GetProductsBody

        _BODY_FIELDS = tuple(GetProductsBody.model_fields)
        return {k: kwargs[k] for k in _BODY_FIELDS if k in kwargs and kwargs[k] is not None}

    def parse_rest_response(self, data: dict[str, Any]) -> GetProductsResponse:
        """Parse REST JSON response into GetProductsResponse."""
        return GetProductsResponse(**data)


class RealResolverProductEnv(EgressHatchMixin, ProductEnv):
    """``ProductEnv`` with the property-list resolver left UNPATCHED.

    ``ProductEnv`` mocks ``resolve_property_list`` so ordinary product tests
    never reach the network. This variant drops exactly that one patch and
    changes nothing else, so ``get_products`` runs the real resolver and the
    real egress seam — which is the point: the refusal under test has to be
    produced by production code, or the wire envelope proves nothing.

    TRAP: because the mock is gone, ``self.mock["resolve_property_list"]`` does
    not exist after ``__enter__`` — the stand-in below is deleted as soon as
    ``ProductMixin``'s happy-path wiring has finished with it. Any Given step
    calling ``ProductMixin.set_property_list()`` on this env will ``KeyError``.
    A scenario that needs a SUCCESSFUL property-list fetch wants plain
    ``ProductEnv`` (mocked resolver) or a real local origin, not this class.
    """

    EXTERNAL_PATCHES = {
        name: target for name, target in ProductEnv.EXTERNAL_PATCHES.items() if name != "resolve_property_list"
    }
    ASYNC_PATCHES = ProductEnv.ASYNC_PATCHES - {"resolve_property_list"}

    def _configure_mocks(self) -> None:
        # ProductMixin's happy-path wiring pokes ``self.mock["resolve_property_list"]``.
        # A throwaway stand-in keeps that one line harmless without forking the
        # rest of the wiring, which this env does want.
        self.mock["resolve_property_list"] = MagicMock()
        try:
            super()._configure_mocks()
        finally:
            del self.mock["resolve_property_list"]

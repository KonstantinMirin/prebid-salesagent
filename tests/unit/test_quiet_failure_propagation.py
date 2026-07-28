"""Enrichment service fail-open with exception narrowing.

Product decision (GitHub #1093): Optional enrichment services degrade
gracefully on expected service failures but propagate programming errors
(TypeError, AttributeError) immediately.

    Covers: BR-RULE-079-01

beads: salesagent-o3x6
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.resolved_identity import ResolvedIdentity


def _make_identity(tenant_id="test-tenant"):
    return ResolvedIdentity(
        principal_id="user-1",
        tenant_id=tenant_id,
        tenant={
            "tenant_id": tenant_id,
            "name": "Test",
            "subdomain": "test",
            "ad_server": {"adapter": "mock"},
            "advertising_policy": None,
        },
        protocol="mcp",
    )


def _make_request(brief="test brief"):
    from src.core.schema_helpers import create_get_products_request

    return create_get_products_request(brief=brief)


def _mock_uow_with_products(products):
    mock_uow = MagicMock()
    mock_uow.__enter__ = MagicMock(return_value=mock_uow)
    mock_uow.__exit__ = MagicMock(return_value=False)
    mock_uow.products.list_all.return_value = products
    return mock_uow


def _base_patches(mock_uow, convert_fn=None):
    """Patches for a minimal _get_products_impl call (no enrichment)."""
    if convert_fn is None:
        convert_fn = lambda p, **kw: p  # noqa: E731
    return [
        patch("src.core.database.repositories.uow.ProductUoW", return_value=mock_uow),
        patch("src.core.tools.products.find_principal", return_value=None),
        patch("src.core.tools.products.convert_product_model_to_schema", side_effect=convert_fn),
    ]


class TestDynamicVariantsExceptionPropagation:
    """Dynamic variant generation fail-open.

    Covers: UC-001-MAIN-41
    """

    @pytest.mark.asyncio
    async def test_type_error_propagates(self):
        """TypeError (bug) propagates, not swallowed.

        Covers: UC-001-MAIN-41
        """
        from tests.helpers.adcp_factories import create_test_product

        product = create_test_product(product_id="p1")
        mock_uow = _mock_uow_with_products([product])

        patches = _base_patches(mock_uow) + [
            patch(
                "src.services.dynamic_products.generate_variants_for_brief",
                new_callable=AsyncMock,
                side_effect=TypeError("NoneType has no attribute 'product_id'"),
            ),
            patch(
                "src.services.dynamic_pricing_service.DynamicPricingService",
                **{
                    "return_value.enrich_products_with_pricing.side_effect": lambda products, **kw: products,
                },
            ),
        ]

        import contextlib

        from src.core.tools.products import _get_products_impl

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(TypeError, match="NoneType"):
                await _get_products_impl(_make_request(), _make_identity())

    @pytest.mark.asyncio
    async def test_runtime_error_is_graceful(self, caplog):
        """RuntimeError (service failure) degrades gracefully AND is logged.

        Covers: UC-001-MAIN-41

        The obligation has two Then clauses on this path: "static products are returned without
        dynamic variants" AND "a warning is logged". Only the first was graded, and it is satisfied
        by the no-failure path too — a variant generator that simply returns nothing also yields
        exactly one static product. Neutralizing the tripwire left this test green, so
        UC-001-MAIN-41 counted as covered while nothing distinguished the two worlds. The WARNING
        record (src/core/tools/products.py:436) is the clause that does.
        """
        from tests.helpers.adcp_factories import create_test_product

        product = create_test_product(product_id="p1")
        mock_uow = _mock_uow_with_products([product])

        variant_generator = AsyncMock(side_effect=RuntimeError("Connection refused"))
        patches = _base_patches(mock_uow) + [
            patch(
                "src.services.dynamic_products.generate_variants_for_brief",
                variant_generator,
            ),
            patch(
                "src.services.dynamic_pricing_service.DynamicPricingService",
                **{
                    "return_value.enrich_products_with_pricing.side_effect": lambda products, **kw: products,
                },
            ),
        ]

        import contextlib

        from src.core.tools.products import _get_products_impl

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(caplog.at_level(logging.WARNING, logger="src.core.tools.products"))
            result = await _get_products_impl(_make_request(), _make_identity())

        # Clause 1: static products are returned without dynamic variants.
        assert len(result.products) == 1

        # The failing collaborator was actually reached — otherwise the clauses below grade nothing.
        variant_generator.assert_awaited_once()

        # Clause 2: a warning is logged. This is the assertion the no-failure path cannot satisfy.
        assert any(
            "Connection refused" in record.message and record.levelno == logging.WARNING for record in caplog.records
        ), (
            "Dynamic variant generation failed silently — UC-001-MAIN-41 requires the failure to be "
            "logged, otherwise a signals-agent outage is indistinguishable from a brief that simply "
            f"produced no variants. Records: {[(r.levelname, r.message) for r in caplog.records]}"
        )


class TestDynamicPricingExceptionPropagation:
    """Dynamic pricing fail-open.

    Covers: UC-001-MAIN-42
    """

    @pytest.mark.asyncio
    async def test_type_error_propagates(self):
        """TypeError (bug) propagates, not swallowed.

        Covers: UC-001-MAIN-42
        """
        from tests.helpers.adcp_factories import create_test_product

        product = create_test_product(product_id="p1")
        mock_uow = _mock_uow_with_products([product])

        mock_pricing_cls = MagicMock()
        mock_pricing_cls.return_value.enrich_products_with_pricing.side_effect = TypeError(
            "'NoneType' object is not subscriptable"
        )

        patches = [
            patch("src.core.database.repositories.uow.ProductUoW", return_value=mock_uow),
            patch("src.core.tools.products.find_principal", return_value=None),
            patch("src.core.tools.products.convert_product_model_to_schema", side_effect=lambda p, **kw: p),
            patch(
                "src.services.dynamic_products.generate_variants_for_brief",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.services.dynamic_pricing_service.DynamicPricingService", mock_pricing_cls),
        ]

        import contextlib

        from src.core.tools.products import _get_products_impl

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(TypeError, match="not subscriptable"):
                await _get_products_impl(_make_request(), _make_identity())

    @pytest.mark.asyncio
    async def test_runtime_error_is_graceful(self):
        """RuntimeError (service failure) degrades gracefully — products returned without pricing enrichment.

        Covers: UC-001-MAIN-42
        GH #1078 H4 — symmetric test for the degradation path.
        """
        from tests.helpers.adcp_factories import create_test_product

        product = create_test_product(product_id="p1")
        mock_uow = _mock_uow_with_products([product])

        mock_pricing_cls = MagicMock()
        mock_pricing_cls.return_value.enrich_products_with_pricing.side_effect = RuntimeError("Connection refused")

        patches = [
            patch("src.core.database.repositories.uow.ProductUoW", return_value=mock_uow),
            patch("src.core.tools.products.find_principal", return_value=None),
            patch("src.core.tools.products.convert_product_model_to_schema", side_effect=lambda p, **kw: p),
            patch(
                "src.services.dynamic_products.generate_variants_for_brief",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.services.dynamic_pricing_service.DynamicPricingService", mock_pricing_cls),
        ]

        import contextlib

        from src.core.tools.products import _get_products_impl

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = await _get_products_impl(_make_request(), _make_identity())
            # Should still return the static product despite pricing failure
            assert len(result.products) == 1


class TestAIRankingExceptionPropagation:
    """AI ranking fail-open (obligation already existed).

    Covers: UC-001-MAIN-32
    """

    @pytest.mark.asyncio
    async def test_type_error_propagates(self):
        """TypeError (bug) propagates even though service failures degrade.

        Covers: UC-001-MAIN-32
        """
        from tests.helpers.adcp_factories import create_test_product

        product = create_test_product(product_id="p1")
        mock_uow = _mock_uow_with_products([product])

        # Need tenant with product_ranking_prompt to trigger AI ranking path
        identity = ResolvedIdentity(
            principal_id="user-1",
            tenant_id="test-tenant",
            tenant={
                "tenant_id": "test-tenant",
                "name": "Test",
                "subdomain": "test",
                "ad_server": {"adapter": "mock"},
                "advertising_policy": None,
                "product_ranking_prompt": "Rank by relevance",
            },
            protocol="mcp",
        )

        mock_factory = MagicMock()
        mock_factory.is_ai_enabled.return_value = True
        mock_factory.create_model.return_value = MagicMock()

        patches = _base_patches(mock_uow) + [
            patch(
                "src.services.dynamic_products.generate_variants_for_brief",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.services.dynamic_pricing_service.DynamicPricingService"),
            patch("src.services.ai.factory.get_factory", return_value=mock_factory),
            patch(
                "src.services.ai.agents.ranking_agent.create_ranking_agent",
                return_value=MagicMock(),
            ),
            patch(
                "src.services.ai.agents.ranking_agent.rank_products_async",
                new_callable=AsyncMock,
                side_effect=TypeError("unexpected keyword argument 'products'"),
            ),
        ]

        import contextlib

        from src.core.tools.products import _get_products_impl

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(TypeError, match="unexpected keyword"):
                await _get_products_impl(_make_request(brief="video ads"), identity)


class TestAdapterAnnotationExceptionPropagation:
    """Adapter annotation fail-open.

    Covers: UC-001-MAIN-43
    """

    @pytest.mark.asyncio
    async def test_type_error_propagates(self):
        """TypeError (bug) propagates, not swallowed.

        Covers: UC-001-MAIN-43
        """
        from tests.helpers.adcp_factories import create_test_product

        product = create_test_product(product_id="p1")
        mock_uow = _mock_uow_with_products([product])

        # Need a principal to trigger adapter annotation path
        mock_principal = MagicMock()
        mock_principal.principal_id = "user-1"

        patches = [
            patch("src.core.database.repositories.uow.ProductUoW", return_value=mock_uow),
            patch("src.core.tools.products.find_principal", return_value=mock_principal),
            patch("src.core.tools.products.convert_product_model_to_schema", side_effect=lambda p, **kw: p),
            patch(
                "src.services.dynamic_products.generate_variants_for_brief",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.services.dynamic_pricing_service.DynamicPricingService"),
            patch(
                "src.core.helpers.adapter_helpers.get_adapter",
                side_effect=TypeError("'NoneType' object has no attribute 'get'"),
            ),
        ]

        import contextlib

        from src.core.tools.products import _get_products_impl

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(TypeError, match="NoneType"):
                await _get_products_impl(_make_request(), _make_identity())

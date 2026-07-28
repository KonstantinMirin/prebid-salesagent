"""Integration tests for dynamic pricing enrichment (un-mocked).

Verifies that DynamicPricingService runs against real DB in ProductEnv,
enriching products with price_guidance from FormatPerformanceMetrics data.

When no metrics exist, products pass through unchanged (graceful no-op).
When metrics exist, CPM pricing options get floor_price and price_guidance.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.factories import (
    FormatPerformanceMetricsFactory,
    PricingOptionFactory,
    PrincipalFactory,
    ProductFactory,
    TenantFactory,
)
from tests.harness.product import ProductEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class TestDynamicPricingUnmocked:
    """Verify DynamicPricingService runs for real in integration tests."""

    @pytest.mark.asyncio
    async def test_no_metrics_products_unchanged(self, integration_db):
        """Products pass through unchanged when no FormatPerformanceMetrics exist."""
        with ProductEnv(tenant_id="pricing-noop", principal_id="pricing-principal") as env:
            tenant = TenantFactory(tenant_id="pricing-noop", subdomain="pricing-noop")
            PrincipalFactory(tenant=tenant, principal_id="pricing-principal")
            p = ProductFactory(tenant=tenant, product_id="no_metrics_product", name="No Metrics")
            PricingOptionFactory(product=p, pricing_model="cpm", rate=Decimal("10.0"), is_fixed=True)

            response = await env.call_impl(brief="test ads")

            assert len(response.products) == 1
            product = response.products[0]
            # Original fixed pricing should be intact
            assert len(product.pricing_options) >= 1
            cpm_option = product.pricing_options[0].root
            assert cpm_option.fixed_price == 10.0

    @pytest.mark.asyncio
    async def test_with_metrics_pricing_enriched(self, integration_db):
        """Products get price_guidance updated when FormatPerformanceMetrics exist.

        The dynamic pricing service updates the CPM option's floor_price to the
        median_cpm from metrics (5.50) and adds p75 to price_guidance (8.25).
        If the service is mocked (pass-through), floor_price stays at original (5.0).
        """
        with ProductEnv(tenant_id="pricing-enrich", principal_id="pricing-enrich-p") as env:
            tenant = TenantFactory(tenant_id="pricing-enrich", subdomain="pricing-enrich")
            PrincipalFactory(tenant=tenant, principal_id="pricing-enrich-p")

            # Product with display_300x250 format — original floor is 5.0
            p = ProductFactory(
                tenant=tenant,
                product_id="enriched_product",
                name="Enriched Product",
            )
            PricingOptionFactory(
                product=p,
                pricing_model="cpm",
                rate=Decimal("10.0"),
                is_fixed=False,
                price_guidance={"floor": 5.0, "p25": 4.0, "p50": 6.0, "p75": 8.0, "p90": 11.0},
            )

            # Create matching metrics for 300x250 with DIFFERENT values than original
            FormatPerformanceMetricsFactory(
                tenant=tenant,
                creative_size="300x250",
                median_cpm=Decimal("5.50"),  # Different from original floor (5.0)
                p75_cpm=Decimal("8.25"),  # Different from original p75 (8.0)
                p90_cpm=Decimal("12.00"),
            )

            response = await env.call_impl(brief="display ads")

            assert len(response.products) == 1
            product = response.products[0]

            # Find the CPM option
            cpm_options = [po.root for po in product.pricing_options if po.root.pricing_model.upper() == "CPM"]
            assert len(cpm_options) >= 1

            cpm = cpm_options[0]
            # The service sets floor_price = median_cpm (5.50)
            # If still mocked (pass-through), floor_price would be 5.0 (from original price_guidance.floor)
            assert getattr(cpm, "floor_price", None) == 5.50, (
                f"Expected floor_price=5.50 (median_cpm from metrics), got {getattr(cpm, 'floor_price', None)}. "
                "If floor_price is 5.0, DynamicPricingService is still mocked (pass-through)."
            )

    @pytest.mark.asyncio
    async def test_metrics_no_match_graceful(self, integration_db):
        """Products with formats that don't match any metrics pass through unchanged."""
        with ProductEnv(tenant_id="pricing-nomatch", principal_id="pricing-nomatch-p") as env:
            tenant = TenantFactory(tenant_id="pricing-nomatch", subdomain="pricing-nomatch")
            PrincipalFactory(tenant=tenant, principal_id="pricing-nomatch-p")

            p = ProductFactory(tenant=tenant, product_id="nomatch_product", name="No Match")
            PricingOptionFactory(product=p, pricing_model="cpm", rate=Decimal("10.0"), is_fixed=True)

            # Create metrics for a DIFFERENT size than the product uses
            FormatPerformanceMetricsFactory(
                tenant=tenant,
                creative_size="970x250",  # product uses 300x250
            )

            response = await env.call_impl(brief="test ads")

            assert len(response.products) == 1
            # Product should still be returned, just without enrichment
            product = response.products[0]
            assert len(product.pricing_options) >= 1

    @pytest.mark.asyncio
    async def test_parameterized_format_id_matches_metrics(self, integration_db):
        """A FormatId carrying typed width/height matches metrics even when its id encodes no size.

        The size of a FormatId comes from ``format_id_creative_size`` (#1600): typed
        ``width``/``height`` first, the id-encoded ``WxH`` token only as a fallback. Before
        that consolidation, dynamic pricing string-parsed the id and NOTHING else, so a
        parameterized FormatId (AdCP 2.5) with ``width=300, height=250`` and the catalog id
        ``display_image`` fell through to ``_default_pricing()`` — while gam_inventory_service,
        deriving the same size from the same FormatId, saw 300x250. Same input, two answers.
        """
        with ProductEnv(tenant_id="pricing-typed", principal_id="pricing-typed-p") as env:
            tenant = TenantFactory(tenant_id="pricing-typed", subdomain="pricing-typed")
            PrincipalFactory(tenant=tenant, principal_id="pricing-typed-p")

            p = ProductFactory(
                tenant=tenant,
                product_id="typed_dims_product",
                name="Typed Dims Product",
                # No "300x250" token anywhere in the id — the size is carried by the
                # parameterized width/height fields alone.
                format_ids=[
                    {
                        "agent_url": "https://creative.adcontextprotocol.org",
                        "id": "display_image",
                        "width": 300,
                        "height": 250,
                    }
                ],
            )
            PricingOptionFactory(
                product=p,
                pricing_model="cpm",
                rate=Decimal("10.0"),
                is_fixed=False,
                price_guidance={"floor": 5.0, "p25": 4.0, "p50": 6.0, "p75": 8.0, "p90": 11.0},
            )

            FormatPerformanceMetricsFactory(
                tenant=tenant,
                creative_size="300x250",
                median_cpm=Decimal("5.50"),
                p75_cpm=Decimal("8.25"),
                p90_cpm=Decimal("12.00"),
            )

            response = await env.call_impl(brief="display ads")

            assert len(response.products) == 1
            cpm_options = [
                po.root for po in response.products[0].pricing_options if po.root.pricing_model.upper() == "CPM"
            ]
            assert len(cpm_options) >= 1
            assert getattr(cpm_options[0], "floor_price", None) == 5.50, (
                "Expected floor_price=5.50 (median_cpm for 300x250). The product's FormatId "
                "carries typed width=300/height=250; deriving its size from the id string alone "
                "misses that and falls back to default pricing."
            )

    @pytest.mark.asyncio
    async def test_non_numeric_id_token_is_not_treated_as_a_size(self, integration_db):
        """An id token that merely contains an 'x' must not be priced as a size.

        ``parse_size_token`` requires BOTH sides of the ``x`` to be numeric (#1600). The
        pre-consolidation dynamic-pricing parser accepted any token containing an ``x``, so
        ``display_boxad`` produced the pseudo-size ``"boxad"``.

        The discriminator is a metric row keyed on that very pseudo-size: the OLD parser
        matches it and prices the product from those metrics, while the correct parser
        derives no sizes at all and returns ``_default_pricing()`` before the metric query
        ever runs. So the two behaviours differ in the PRICE, which is what this asserts.

        Deliberately not asserted via the "no recognizable creative sizes" log line. That
        was the original form of this test and it passed alone but failed in the full suite
        with zero captured records — an earlier test on the same xdist worker leaves ``src.*``
        loggers disabled, so a log-only assertion is silently vacuous exactly when the suite
        runs for real.
        """
        with ProductEnv(tenant_id="pricing-token", principal_id="pricing-token-p") as env:
            tenant = TenantFactory(tenant_id="pricing-token", subdomain="pricing-token")
            PrincipalFactory(tenant=tenant, principal_id="pricing-token-p")

            p = ProductFactory(
                tenant=tenant,
                product_id="boxad_product",
                name="Boxad Product",
                format_ids=[{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_boxad"}],
            )
            PricingOptionFactory(
                product=p,
                pricing_model="cpm",
                rate=Decimal("10.0"),
                is_fixed=False,
                price_guidance={"floor": 5.0, "p25": 4.0, "p50": 6.0, "p75": 8.0, "p90": 11.0},
            )

            # Keyed on the PSEUDO-size the broken parser produced. Only a parser that
            # accepts "boxad" as a size can reach these numbers.
            FormatPerformanceMetricsFactory(
                tenant=tenant,
                creative_size="boxad",
                median_cpm=Decimal("7.77"),
                p75_cpm=Decimal("9.99"),
                p90_cpm=Decimal("13.13"),
            )

            response = await env.call_impl(brief="display ads")

            assert len(response.products) == 1
            cpm_options = [
                po.root for po in response.products[0].pricing_options if po.root.pricing_model.upper() == "CPM"
            ]
            assert len(cpm_options) >= 1
            floor_price = getattr(cpm_options[0], "floor_price", None)
            assert floor_price != 7.77, (
                "'boxad' was treated as a creative size: the product was priced from the "
                "pseudo-size metric row (floor_price=7.77 == median_cpm). Both sides of the "
                "'x' must be numeric."
            )

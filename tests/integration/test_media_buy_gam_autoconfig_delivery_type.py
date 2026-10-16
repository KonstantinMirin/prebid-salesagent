"""Regression (PR1399 R3): GAM auto-config must normalize a guaranteed product's
delivery_type to its enum *value*, not str(Enum).

src/core/tools/media_buy_create.py auto-generates a default GAM
implementation_config when a product is missing one. It derives the
``delivery_type`` string and passes it to
``GAMProductConfigService.generate_default_config``, which branches on
``delivery_type == "guaranteed"``. ``Product.delivery_type`` is a plain
``DeliveryType`` enum, so ``str(delivery_type)`` yields
``"DeliveryType.guaranteed"`` -- the equality fails and a GUARANTEED product
silently gets the NON_GUARANTEED (PRICE_PRIORITY) config. The fix routes the
value through ``enum_value()``.

This drives the real ``_create_media_buy_impl`` GAM auto-config path and calls
through to the real config generator; only the captured arguments/output are
asserted.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.adapters.google_ad_manager import GoogleAdManager
from src.core.schemas import CreateMediaBuyRequest
from src.services.gam_product_config_service import GAMProductConfigService
from tests.factories import PricingOptionFactory, ProductFactory
from tests.factories.core import PropertyTagFactory
from tests.harness.media_buy_create import MediaBuyCreateEnv

_TENANT_ID = "gam-autocfg-tenant"
_PRINCIPAL_ID = "gam-autocfg-principal"

#: The canonical creative agent a stored legacy reference is namespaced to. Spelled here
#: rather than imported from ``format_resolver`` so the fixture states the row's own shape
#: instead of deriving it from the code under test.
_CREATIVE_AGENT = "https://creative.adcontextprotocol.org"


def _future(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _make_request(product_id: str) -> CreateMediaBuyRequest:
    return CreateMediaBuyRequest(
        account={"account_id": "acct_test"},
        brand={"domain": "testbrand.com"},
        start_time=_future(1),
        end_time=_future(8),
        packages=[{"product_id": product_id, "budget": 5000.0, "pricing_option_id": "cpm_usd_fixed"}],
        idempotency_key=f"gam-autoconfig-{product_id}",
    )


@pytest.mark.requires_db
class TestGAMAutoConfigDeliveryTypeNormalization:
    def test_guaranteed_product_autoconfig_receives_normalized_delivery_type(self, integration_db):
        """A guaranteed product missing implementation_config must auto-generate a
        GUARANTEED (STANDARD line item) GAM config, not the non_guaranteed default."""
        real_generate = GAMProductConfigService.generate_default_config
        captured: dict = {}

        # ``format_options`` is accepted because the production call now passes the
        # product's canonical arm, and NOT asserted here: this product is legacy-only
        # (``ProductFactory`` defaults the canonical arm to None), so the value would be
        # None whether the call site passes it or the spy defaults it -- an assertion that
        # cannot tell those apart. The call site is graded by
        # ``test_canonical_autoconfig_seeds_the_declared_size`` below, with a product that
        # declares one.
        def _spy(delivery_type, formats=None, *, format_options=None):
            config = real_generate(delivery_type, formats=formats, format_options=format_options)
            captured["delivery_type"] = delivery_type
            captured["config"] = config
            return config

        # No ``human_review_required=`` kwarg: it only ever seeded an in-memory tenant
        # override, and this env's ``call_impl`` dispatches at ``invoke_tool``, so the REAL
        # resolver loads the tenant from its row. The kwarg agreed with the row
        # (``TenantFactory.human_review_required = False``) purely by accident, so it
        # decided nothing; the row is the one source.
        with MediaBuyCreateEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            tenant, _principal = env.setup_default_data()
            PropertyTagFactory(tenant=tenant, tag_id="all_inventory", name="All Inventory")
            product = ProductFactory(
                tenant=tenant,
                product_id="prod_guar",
                delivery_type="guaranteed",
                implementation_config=None,  # force the auto-config branch
                property_tags=["all_inventory"],
            )
            PricingOptionFactory(product=product, pricing_model="cpm", currency="USD", is_fixed=True)

            # Enter the GAM auto-config branch (guarded by adapter class name).
            env.mock["adapter"].return_value.__class__ = GoogleAdManager

            with patch.object(GAMProductConfigService, "generate_default_config", side_effect=_spy):
                env.call_impl(req=_make_request("prod_guar"))

        assert captured, "GAM auto-config branch did not run -- generate_default_config was never called"
        # The bug passes str(DeliveryType.guaranteed) == 'DeliveryType.guaranteed'.
        assert captured["delivery_type"] == "guaranteed"
        # ... which makes generate_default_config fall through to non_guaranteed.
        assert captured["config"]["line_item_type"] == "STANDARD"

    def test_canonical_autoconfig_seeds_the_declared_size(self, integration_db):
        """The auto-config path hands the product's CANONICAL arm to the seeder.

        The fourth call site of ``generate_default_config`` and the only one outside the
        admin. Before this, it passed ``formats`` alone, so a canonically-authored product
        was auto-configured with the 300x250 fallback contradicting its own declaration --
        and that value is the one GAM traffics, because ``gam/managers/orders.py`` falls
        back to ``impl_config["creative_placeholders"]`` for a package naming no
        ``format_ids``, which is exactly this product.

        970x250 and not 300x250: the fallback is 300x250, so an assertion expecting it
        would pass whether the canonical arm is read or ignored.

        The spy CALLS THROUGH to the real generator, so ``captured["config"]`` is the
        genuine seeded document and not a mock's answer. That pass-through is what makes
        this grade the plumbing: if the call site stopped passing ``format_options``, the
        spy would receive None, the real generator would fall back, and 300x250 would fail
        this assertion.
        """
        real_generate = GAMProductConfigService.generate_default_config
        captured: dict = {}

        def _spy(delivery_type, formats=None, *, format_options=None):
            config = real_generate(delivery_type, formats=formats, format_options=format_options)
            captured["config"] = config
            return config

        with MediaBuyCreateEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            tenant, _principal = env.setup_default_data()
            PropertyTagFactory(tenant=tenant, tag_id="all_inventory", name="All Inventory")
            product = ProductFactory(
                tenant=tenant,
                product_id="prod_canonical",
                delivery_type="guaranteed",
                implementation_config=None,  # force the auto-config branch
                # Canonically authored: the canonical arm on AND the legacy arm off, which
                # is what makes ``formats`` empty and the canonical arm the only input.
                format_options=[{"format_kind": "image", "params": {"width": 970, "height": 250}}],
                format_ids=None,
                property_tags=["all_inventory"],
            )
            PricingOptionFactory(product=product, pricing_model="cpm", currency="USD", is_fixed=True)

            env.mock["adapter"].return_value.__class__ = GoogleAdManager

            with patch.object(GAMProductConfigService, "generate_default_config", side_effect=_spy):
                env.call_impl(req=_make_request("prod_canonical"))

        assert captured, "GAM auto-config branch did not run -- generate_default_config was never called"
        assert captured["config"]["creative_placeholders"] == [
            {"width": 970, "height": 250, "expected_creative_count": 1, "is_native": False}
        ]

    def test_legacy_only_autoconfig_seeds_the_size_the_arm_encodes(self, integration_db):
        """The DEPRECATED arm still reaches the seeder on the buyer's path.

        Replaces the grader stage 5 deletes --
        ``tests/admin/...::test_a_legacy_only_product_is_seeded_from_the_entry_it_stores`` --
        which POSTed a legacy-only product to the admin create handler. A4 refuses that by
        design ("Do not author a new product from format_ids alone"), so that test asserted
        behaviour the pin forbids and is deleted rather than re-grounded. The OBLIGATION is
        still live here: A4 deliberately preserves ``format_ids`` on existing and ingested
        rows, so a legacy product bought on a GAM tenant with no ``implementation_config``
        reaches this seeding call with a populated legacy arm.

        WHY THE FIXTURE ID ENCODES ITS SIZE. ``create_media_buy`` passes BARE ID STRINGS --
        ``formats_list = [fmt.id for fmt in schema_product.format_ids]`` -- so a stored
        entry's own ``width``/``height`` never reach the seeder on this path
        (salesagent-rlirf, P1, not fixed here and not mine). ``display_728x90_image``
        carries its dimensions IN THE ID, which ``upgrade_legacy_format_id`` projects, so
        this scenario grades the plumbing rather than going red on that separate gap.

        NOTHING HERE ASSERTS THE BROKEN SHAPE'S CURRENT BEHAVIOUR. A row claiming the
        entry-carrying shape yields no placeholder would pin a defect; that assertion
        belongs to rlirf's regression test, after rlirf is fixed, and it will assert
        success.

        728x90, never 300x250: the seeder's fallback is 300x250, so an assertion expecting
        it would pass whether the legacy arm is read or ignored.

        WHY THIS ASSERTS THE SEEDED VALUE AND NOT SUCCESS ON THE WIRE. Measured:
        ``_creative_placeholders`` cannot return an empty list -- it answers the 300x250
        fallback when no declaration yields a slot -- so ``validate_config``'s
        ``if not placeholders`` refusal is unreachable from a freshly seeded config and
        BOTH arms of the probe below succeed. ``Product.implementation_config`` is also
        ``Field(exclude=True)``, so the seeded placeholder is on no transport's wire by
        construction. The value is the only thing that differs, so the value is what is
        asserted.
        """
        real_generate = GAMProductConfigService.generate_default_config
        captured: dict = {}

        def _spy(delivery_type, formats=None, *, format_options=None):
            config = real_generate(delivery_type, formats=formats, format_options=format_options)
            captured["config"] = config
            return config

        with MediaBuyCreateEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            tenant, _principal = env.setup_default_data()
            PropertyTagFactory(tenant=tenant, tag_id="all_inventory", name="All Inventory")
            product = ProductFactory(
                tenant=tenant,
                product_id="prod_legacy",
                delivery_type="guaranteed",
                implementation_config=None,  # force the auto-config branch
                # The mirror of the canonical control above: the legacy arm ON and the
                # canonical arm OFF, so the deprecated arm is the seeder's only input.
                format_ids=[{"agent_url": _CREATIVE_AGENT, "id": "display_728x90_image"}],
                format_options=None,
                property_tags=["all_inventory"],
            )
            PricingOptionFactory(product=product, pricing_model="cpm", currency="USD", is_fixed=True)

            env.mock["adapter"].return_value.__class__ = GoogleAdManager

            with patch.object(GAMProductConfigService, "generate_default_config", side_effect=_spy):
                env.call_impl(req=_make_request("prod_legacy"))

        assert captured, "GAM auto-config branch did not run -- generate_default_config was never called"
        assert captured["config"]["creative_placeholders"] == [
            {"width": 728, "height": 90, "expected_creative_count": 1, "is_native": False}
        ]

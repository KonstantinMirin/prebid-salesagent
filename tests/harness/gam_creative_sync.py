"""GamCreativeSyncEnv — sync_creatives against a seller whose ad server is GAM.

``CreativeSyncEnv`` with one more external system stood in: the GAM SOAP client.
Everything between the sync and GAM is production — the assignment stage, the
post-commit push (``push_creative_to_existing_buy``), ``get_adapter`` choosing
``GoogleAdManager`` off the tenant's ``AdapterConfig``, the GAM creatives manager
building the creative and its line item associations. Only ``GAMClientManager`` is
replaced (``tests/helpers/gam_client``), and what production sends through it is
what the scenarios grade: the ``createCreatives`` payload and the
``createLineItemCreativeAssociations`` payload.

E2E: the live server's tenant talks to whatever GAM network it is configured for,
and nothing on that surface accepts a stand-in SOAP client, so the setup declares
itself unrealizable there (``E2EUnsupportedSetup``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from tests.harness._realize import e2e_unsupported, realize_e2e
from tests.harness.creative_sync import CreativeSyncEnv
from tests.helpers.gam_client import gam_line_item, stub_gam_client_manager
from tests.helpers.reference_creative_agent import reference_format, reference_preview


class GamCreativeSyncEnv(CreativeSyncEnv):
    """sync_creatives on a GAM seller, with GAM faked at its SOAP client."""

    EXTERNAL_PATCHES = {
        **CreativeSyncEnv.EXTERNAL_PATCHES,
        "gam_client": "src.adapters.google_ad_manager.GAMClientManager",
    }

    #: The buyer's GAM advertiser (principal platform mapping) and the order the
    #: seeded buy was trafficked as. Any ids GAM could have minted.
    GAM_ADVERTISER_ID = "5550001"
    GAM_ORDER_ID = "4220455642"
    #: What the stand-in GAM answers createCreatives with (stub_gam_client_manager's default).
    GAM_CREATED_CREATIVE_ID = "gam_creative_1"

    def _configure_mocks(self) -> None:
        super()._configure_mocks()
        self.mock["gam_client"].return_value = stub_gam_client_manager()

    @realize_e2e(
        e2e_unsupported(
            "the live server's GAM adapter talks to the GAM network its tenant is configured for; "
            "nothing on that surface accepts a stand-in SOAP client, so what it sends cannot be read back"
        )
    )
    def setup_gam_live_package(self, *, package_id: str, line_item_id: str, format_id: dict[str, str]) -> Any:
        """A GAM seller with a live buy whose package traffics as GAM line item *line_item_id*.

        The package carries what a GAM create_media_buy persists for it:
        ``platform_order_id`` (the order) and ``platform_line_item_id`` (this package's
        line item, from ``AdapterCreateResult.platform_line_item_ids``). The line item
        accepts the creative size of *format_id*'s primary render, read off the
        reference catalog, so the size check is the one production makes.
        """
        from tests.factories import AdapterConfigFactory, MediaBuyFactory, MediaPackageFactory, ProductFactory

        tenant, principal = self.setup_default_data()
        principal.platform_mappings = {"google_ad_manager": {"advertiser_id": self.GAM_ADVERTISER_ID}}
        AdapterConfigFactory(
            tenant=tenant,
            adapter_type="google_ad_manager",
            gam_network_code="123456",
            gam_trafficker_id="7770001",
            # The adapter refuses a config with no credential at construction; nothing
            # authenticates, because the client it would authenticate is the stand-in.
            gam_refresh_token="test_refresh_token",
        )
        product = ProductFactory(tenant=tenant, format_ids=[format_id])
        media_buy = MediaBuyFactory(tenant=tenant, principal=principal, status="active")
        package = MediaPackageFactory(
            media_buy=media_buy,
            package_id=package_id,
            package_config={
                "package_id": package_id,
                "product_id": product.product_id,
                "platform_order_id": self.GAM_ORDER_ID,
                "platform_line_item_id": line_item_id,
            },
        )
        self._commit_factory_data()

        width, height = reference_format(format_id["id"]).get_primary_dimensions()
        # Named nothing like the product: line items are matched by id, never by name.
        line_item = gam_line_item("Q4 Brand Push - Homepage", item_id=line_item_id, sizes=((width, height),))
        self.mock["gam_client"].return_value = stub_gam_client_manager(line_items=[line_item])
        return package

    def serve_reference_format(self, format_id: str) -> dict[str, str]:
        """Have the creative agent serve *format_id* as the reference catalog defines it.

        The agent previews the creative at the format's primary render size, which is
        where sync_creatives takes a creative's dimensions from.
        """
        fmt = reference_format(format_id)
        self.set_run_async_result([fmt])
        registry = self.mock["registry"].return_value
        registry.get_format = AsyncMock(return_value=fmt)
        registry.preview_creative = AsyncMock(return_value=reference_preview(format_id))
        return {"agent_url": str(fmt.format_id.agent_url), "id": format_id}

    def gam_created_creatives(self) -> list[dict[str, Any]]:
        """Every creative production sent GAM's CreativeService.createCreatives, in order."""
        service = self.mock["gam_client"].return_value.get_service("CreativeService")
        return [creative for call in service.createCreatives.call_args_list for creative in call.args[0]]

    def gam_line_item_associations(self) -> list[dict[str, Any]]:
        """Every association production sent createLineItemCreativeAssociations, in order."""
        service = self.mock["gam_client"].return_value.get_service("LineItemCreativeAssociationService")
        return [
            association
            for call in service.createLineItemCreativeAssociations.call_args_list
            for association in call.args[0]
        ]

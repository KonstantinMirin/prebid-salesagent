"""A Google Ad Manager seller, composable into any env whose tool reaches its adapter through ``get_adapter``.

``GamSellerMixin.sell_through_gam`` makes the env's tenant a GAM seller: from then on the
tool's adapter is production's ``GoogleAdManager``, built from the seeded rows, and the only
stand-in under it is Google's SOAP client (``stub_gam_client``). Every env whose scenarios
need a GAM seller mixes this in, so the capability, its e2e declaration and its readers live
here once.

A host env composes it in three places:

* its bases: ``class SomeEnv(GamSellerMixin, ..., IntegrationEnv)``;
* its ``EXTERNAL_PATCHES``: ``{..., **GAM_CLIENT_PATCH}``, next to an ``"adapter"`` patch on
  the ``get_adapter`` its tool calls;
* its ``_configure_mocks``: ``self._configure_gam_client()``.

The client patch is inert for a tenant on the Mock adapter, which never constructs an
``AdManagerClient``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from tests.harness._realize import e2e_unsupported, realize_e2e
from tests.helpers.gam_client import GAM_CREATE_METHODS, GAM_SENT_METHODS, stub_gam_client

if TYPE_CHECKING:
    from unittest.mock import MagicMock

GAM_CLIENT_PATCH: dict[str, str] = {
    # Google's SOAP client, named where GAMClientManager constructs it. ``ad_manager`` there
    # is googleads' module, so the patch replaces the class on that module, and every
    # ``ad_manager.AdManagerClient(...)`` in src/ (each looks it up at call time) gets the
    # stand-in. Inert until ``sell_through_gam`` makes the tenant a GAM seller: a tenant on
    # the Mock adapter never constructs one.
    "gam_client": "src.adapters.gam.client.ad_manager.AdManagerClient",
}


class GamSellerMixin:
    """Mixes a Google Ad Manager seller into an env: the setup, and readers of what GAM received.

    Host env must be an ``IntegrationEnv`` that spreads ``GAM_CLIENT_PATCH`` into its
    ``EXTERNAL_PATCHES``, patches ``"adapter"`` on a ``get_adapter(identity)``, and calls
    ``_configure_gam_client`` from its ``_configure_mocks``.
    """

    if TYPE_CHECKING:
        # Declared, not implemented: this mixin is only ever composed with IntegrationEnv,
        # which owns the patches, the seed and the session (the same statement
        # EgressHatchMixin makes for ``_guard``).
        mock: dict[str, MagicMock]

        def setup_default_data(self, **tenant_kwargs: Any) -> tuple[Any, Any]: ...

        def _commit_factory_data(self) -> None: ...

    def _configure_gam_client(self) -> None:
        """Every ``AdManagerClient(...)`` built during the scenario is the same stand-in client.

        The adapter's, a health check's, the approval and sync services': one scenario has
        one GAM network.
        """
        self.mock["gam_client"].return_value = stub_gam_client()

    @realize_e2e(
        e2e_unsupported(
            "the live server has no stand-in Google Ad Manager network: a GAM tenant there would "
            "call Google, so its tenants run the Mock adapter"
        )
    )
    def sell_through_gam(
        self, *, trafficker_id: str, advertiser_id: str, ad_unit_id: str, products: Iterable[Any]
    ) -> None:
        """Make this env's tenant a Google Ad Manager seller selling *products* on one ad unit.

        Writes the rows a seller has after GAM onboarding in the Admin UI, and nothing else:
        the onboarding rows (``onboard_gam``), the buyer's principal mapped to its GAM
        advertiser, the synced ad unit (the setup checklist requires one, and the adapter
        resolves product mappings against it), and each product as the add-product form saves
        it. From then on the tool's adapter is production's: ``get_adapter`` builds
        ``GoogleAdManager`` from those rows, and the only stand-in under it is Google's SOAP
        client (``stub_gam_client``). Read what the seller sent GAM with ``gam_objects_sent``
        and what GAM created with ``gam_objects_created``.

        Ceiling: once this runs, a Given that configures the ``MagicMock`` adapter
        (``self.mock["adapter"].return_value``, the adapter error and rejection injections)
        does nothing, because the patch delegates to production. A GAM scenario states GAM's
        answers through the stand-in client, and does not combine with those Givens.
        """
        from src.core.helpers.adapter_helpers import get_adapter
        from tests.factories import GAMInventoryFactory
        from tests.utils.tenant_setup import onboard_gam

        tenant, principal = self.setup_default_data()
        onboard_gam(tenant, trafficker_id=trafficker_id)
        principal.platform_mappings = {
            **(principal.platform_mappings or {}),
            "google_ad_manager": {"advertiser_id": advertiser_id},
        }
        GAMInventoryFactory(tenant=tenant, inventory_id=ad_unit_id)
        for product in products:
            self._sell_product_through_gam(product, ad_unit_id)
        self._commit_factory_data()
        self.mock["adapter"].side_effect = get_adapter

    def _sell_product_through_gam(self, product: Any, ad_unit_id: str) -> None:
        """Save *product* the way the Admin UI's add-product form saves a GAM product with one ad unit.

        * Its format is ``display_300x250_image`` from the reference catalog. The adapter
          resolves each line item's creative size through ``format_resolver.get_format``,
          which ``_get_format_spec_sync``'s stand-in does not cover, and the creative registry
          serves the checked-in reference catalog only while the testing flag's
          ``reference_formats_only`` holds (#2255). When that property goes, this env has to
          serve the format through the creative registry instead.
        * Its ``implementation_config`` is ``GAMProductConfigService.generate_default_config``
          for its delivery type and formats, the generator the form calls, plus the ad unit
          the seller picks. The generator supplies ``include_descendants: True``, the form's
          checked default.
        * Its primary inventory mapping names the same ad unit, which the form writes for the
          first picked ad unit. The adapter reads these rows before ``implementation_config``,
          so the scenario runs the path every real GAM seller runs. Because the form writes
          the same ad unit to both places, a mapping read that silently finds nothing falls
          back to the same ids and stays green; one that raises turns the scenario red.

        The form derives ``delivery_type`` from the first pricing option's ``is_fixed``. The
        env's default product (``non_guaranteed`` with a fixed CPM option) is a pairing the
        form cannot save; a scenario grading line item type or goal makes the two agree. A
        scenario that needs another product setting adds a keyword here rather than a second
        product writer.
        """
        from src.services.gam_product_config_service import GAMProductConfigService
        from tests.factories import ProductInventoryMappingFactory
        from tests.factories.product import REFERENCE_FORMAT_ID, reference_format_ids

        product.format_ids = reference_format_ids(REFERENCE_FORMAT_ID)
        product.implementation_config = {
            **GAMProductConfigService.generate_default_config(
                product.delivery_type, [fmt["id"] for fmt in product.format_ids]
            ),
            "targeted_ad_unit_ids": [ad_unit_id],
        }
        ProductInventoryMappingFactory(product=product, inventory_id=ad_unit_id, is_primary=True)

    def gam_objects_sent(self, service: str, method: str) -> list[Any]:
        """Every object the seller sent the stand-in GAM network through ``service.method``, in order.

        As production built them. Only for the methods in ``GAM_SENT_METHODS``, each of which
        takes an array of objects; this concatenates the arrays of every call. Any other
        ``(service, method)``, a misspelled one included, raises ``ValueError``, so a Then
        expecting nothing sent cannot pass by reading a method production never calls. For
        what GAM made of a create, with the ids it assigned, read ``gam_objects_created``.
        """
        if (service, method) not in GAM_SENT_METHODS:
            raise ValueError(f"{service}.{method} is not a GAM method the seller sends objects through")
        calls = getattr(self.mock["gam_client"].return_value.GetService(service), method).call_args_list
        return [obj for call in calls for obj in call.args[0]]

    def gam_objects_created(self, service: str, method: str) -> list[Any]:
        """What the stand-in GAM network created through ``service.method``, as it answered.

        Each sent object with the id the network assigned it, in order
        (``stub_gam_client``'s ``created_objects``). Only for the methods in
        ``GAM_CREATE_METHODS``, the ones the stand-in answers; any other ``(service, method)``
        raises ``ValueError``, since the network never records it as created.
        """
        if (service, method) not in GAM_CREATE_METHODS:
            raise ValueError(f"{service}.{method} is not a GAM create the stand-in network answers")
        return list(self.mock["gam_client"].return_value.created_objects.get((service, method), []))

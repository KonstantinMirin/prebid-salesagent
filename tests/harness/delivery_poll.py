"""DeliveryPollEnv — integration test environment for _get_media_buy_delivery_impl.

Patches: get_adapter ONLY (external ad server).
Real: MediaBuyUoW, _get_pricing_options (all hit real DB).

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with DeliveryPollEnv() as env:
            tenant = TenantFactory(tenant_id="t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="p1")
            buy = MediaBuyFactory(tenant=tenant, principal=principal)
            env.set_adapter_response(buy.media_buy_id, impressions=5000)

            response = env.call_impl(media_buy_ids=[buy.media_buy_id])
            assert response.aggregated_totals.impressions == 5000.0

Available mocks via env.mock:
    "adapter"    -- get_adapter mock (only external mock)
"""

from __future__ import annotations

from typing import Any, cast

from src.core.schemas import (
    AdapterGetMediaBuyDeliveryResponse,
    GetMediaBuyDeliveryRequest,
    GetMediaBuyDeliveryResponse,
)
from tests.harness._base import IntegrationEnv
from tests.harness._mixins import DeliveryPollMixin
from tests.harness._realize import e2e_unsupported, realize_e2e
from tests.harness.gam import GAM_CLIENT_PATCH, GAM_REPORT_DOWNLOAD_PATCH, seed_gam_seller
from tests.harness.transport import DeliverResult


class DeliveryDispatchMixin:
    """get_media_buy_delivery dispatch across A2A/MCP/REST.

    Owned here, beside the env whose primary verb it is, so an env that serves the tool
    as a SECOND verb (``MediaBuyCreateListEnv``, which reads back the buy it created)
    dispatches it through the same code. Named ``_deliver_delivery_*`` /
    ``_build_delivery_rest_body`` for the reason ``MediaBuyListDispatchMixin`` gives:
    a composite routes to these explicitly, so neither verb's dispatch can shadow the
    other's by MRO accident.
    """

    #: The route get_media_buy_delivery answers on (src/routes/api_v1.py).
    DELIVERY_REST_ENDPOINT = "/api/v1/media-buys/delivery"

    #: The request fields the REST body accepts.
    _DELIVERY_BODY_FIELDS = (
        "media_buy_ids",
        "status_filter",
        "start_date",
        "end_date",
        "reporting_dimensions",
        "attribution_window",
        "include_package_daily_breakdown",
        "account",
    )

    @staticmethod
    def is_delivery_request(kwargs: dict[str, Any]) -> bool:
        """Whether this dispatch is get_media_buy_delivery: the request TYPE decides."""
        return isinstance(kwargs.get("req"), GetMediaBuyDeliveryRequest)

    def _call_delivery_impl(self, **kwargs: Any) -> GetMediaBuyDeliveryResponse:
        """Call _get_media_buy_delivery_impl with a built ``req=`` request and a real DB."""
        from src.core.tools.media_buy_delivery import _get_media_buy_delivery_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        return _get_media_buy_delivery_impl(kwargs["req"], identity)

    def _deliver_delivery_mcp(self, **kwargs: Any) -> DeliverResult:
        """Dispatch get_media_buy_delivery via the real FastMCP Client pipeline."""
        return self._run_mcp_client("get_media_buy_delivery", GetMediaBuyDeliveryResponse, **kwargs)

    def _deliver_delivery_a2a(self, **kwargs: Any) -> DeliverResult:
        """Dispatch get_media_buy_delivery via the real A2A handler pipeline."""
        return self._run_a2a_handler("get_media_buy_delivery", GetMediaBuyDeliveryResponse, **kwargs)

    def _build_delivery_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """The ``GetMediaBuyDeliveryBody`` for flat kwargs or a built ``req=`` request."""
        req = kwargs.get("req")
        if req is not None:
            kwargs = req.model_dump(mode="json", exclude_unset=True)
        return {k: kwargs[k] for k in self._DELIVERY_BODY_FIELDS if kwargs.get(k) is not None}

    @staticmethod
    def _parse_delivery_rest_response(data: dict[str, Any]) -> GetMediaBuyDeliveryResponse:
        """A get_media_buy_delivery REST body, revived like the base revives its own."""
        return cast("GetMediaBuyDeliveryResponse", GetMediaBuyDeliveryResponse.revive(data))


class DeliveryPollEnv(DeliveryDispatchMixin, DeliveryPollMixin, IntegrationEnv):
    """Integration test environment for _get_media_buy_delivery_impl.

    Only mocks the adapter (external ad server). Everything else is real:
    - Real MediaBuyUoW -> real DB queries
    - The principal comes off the identity; nothing looks one up
    - Real _get_pricing_options -> real DB queries

    Fluent API (from DeliveryPollMixin):
        set_adapter_response(...)  -- configure adapter return for a media_buy_id
        set_adapter_error(exc)     -- make the adapter raise an exception
        call_impl(...)             -- call _get_media_buy_delivery_impl with real DB
    """

    RESPONSE_MODEL = GetMediaBuyDeliveryResponse

    # FIXME(#2012): JUSTIFIED OVERRIDE — deliberately does NOT declare
    # MCP_TOOL/A2A_SKILL, so it does not take the base's client-core delegation.
    # The core's UNWRAP parses into the PINNED GetMediaBuyDeliveryResponse, whose
    # by_package items REQUIRE pricing_model, rate and currency
    # (get-media-buy-delivery-response.json); production emits none of the three,
    # so every response fails that parse and 214 UC-004 scenarios go red. Parsing
    # here with the LOCAL model keeps the env working while the gap stays
    # attributable — a production schema defect, not a dispatch defect, and
    # deliberately not hidden by loosening the core. Delete both overrides and
    # their `_KNOWN_DELIVER_OVERRIDES` entries when #2012 lands.
    def deliver_mcp(self, **kwargs: Any) -> DeliverResult:
        """Dispatch get_media_buy_delivery via the real FastMCP Client pipeline."""
        return self._deliver_delivery_mcp(**kwargs)

    def deliver_a2a(self, **kwargs: Any) -> DeliverResult:
        """Dispatch get_media_buy_delivery via the real A2A handler pipeline."""
        return self._deliver_delivery_a2a(**kwargs)

    EXTERNAL_PATCHES = {
        "adapter": "src.core.tools.media_buy_delivery.get_adapter",
    }
    REST_ENDPOINT = DeliveryDispatchMixin.DELIVERY_REST_ENDPOINT

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._adapter_responses: dict[str, AdapterGetMediaBuyDeliveryResponse] = {}

    def _configure_mocks(self) -> None:
        self._configure_adapter_mock()

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Convert kwargs to GetMediaBuyDeliveryBody shape for REST POST."""
        return self._build_delivery_rest_body(**kwargs)

    # parse_rest_response: the base's, which revives RESPONSE_MODEL.


class GAMDeliveryPollEnv(DeliveryPollEnv):
    """``DeliveryPollEnv`` with the REAL Google Ad Manager adapter reading a GAM report.

    ``DeliveryPollEnv`` replaces the adapter's answer, so it cannot grade how the seller
    reads what GAM reports. This variant keeps the adapter -- report job, freshness
    handling, aggregation -- and stands in for the two things GAM owns: its SOAP client,
    which runs the report job (``serve_gam_report``), and the HTTP download of the
    finished report's CSV (``gam_report_download``). The report has no rows unless
    a scenario says otherwise.

    The tenant is made a GAM seller by ``sell_through_gam``.
    """

    EXTERNAL_PATCHES = {**GAM_CLIENT_PATCH, **GAM_REPORT_DOWNLOAD_PATCH}

    def _configure_mocks(self) -> None:
        from tests.helpers.gam_client import gam_report_download, serve_gam_report, stub_gam_client_manager

        client_manager = stub_gam_client_manager()
        serve_gam_report(client_manager)
        self.mock["gam_client"].return_value = client_manager
        self.mock["gam_report_download"].return_value = gam_report_download()

    @realize_e2e(e2e_unsupported("the live stack has no stand-in GAM network to report from"))
    def sell_through_gam(self) -> None:
        """Make the env's tenant a GAM seller and its principal a GAM advertiser."""
        tenant, principal = self.setup_default_data()
        seed_gam_seller(self, tenant, principal)

    @realize_e2e(e2e_unsupported("the live stack has no Google Ad Manager report job to fail"))
    def fail_gam_report(self) -> None:
        """GAM fails the report job -- a real report failure, not an empty report."""
        from tests.helpers.gam_client import serve_gam_report

        serve_gam_report(self.mock["gam_client"].return_value, status="FAILED")

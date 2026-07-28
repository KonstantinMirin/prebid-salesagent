"""Adapter-side coverage for AdCP 3.1.1 create-in-paused-state (GH #1619).

The wire behaviour (transport forwarding, persistence, status precedence) is
graded by the BDD features local-uc002-create-paused.feature and
local-uc019-paused-status-precedence.feature, which run against the harness's
adapter double. This module exercises the REAL MockAdServer, because the half of
the obligation the wire cannot show is that the ad server actually books a
suppressed buy: reporting media_buy_status "paused" while the server delivers
would be a lie the buyer only discovers on their invoice.

Spec: v3.1.1 create-media-buy-request.json properties.paused — "Create the media
buy in a paused delivery state." Conformance storyboard: ungraded (no scenario
under dist/compliance/3.1.1/.../scenarios exercises create-time paused).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.adapters.mock_ad_server import MockAdServer
from src.core.schemas import CreateMediaBuyRequest, MediaPackage, Principal
from src.core.schemas.delivery import ReportingPeriod

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_START = datetime.now(UTC) - timedelta(days=5)
_END = datetime.now(UTC) + timedelta(days=25)


def _adapter(tenant_id: str = "tenant_paused", **config) -> MockAdServer:
    principal = Principal(principal_id="p_paused", name="Paused Principal", platform_mappings={})
    return MockAdServer(config=config, principal=principal, tenant_id=tenant_id)


def _request(*, paused: bool | None) -> CreateMediaBuyRequest:
    return CreateMediaBuyRequest(
        brand={"domain": "testbrand.com"},
        idempotency_key=f"paused-adapter-{paused}-key-000000",
        packages=[
            {
                "product_id": "prod_paused",
                "budget": 5000.0,
                "pricing_option_id": "cpm_usd_fixed",
            }
        ],
        start_time=_START.isoformat(),
        end_time=_END.isoformat(),
        paused=paused,
    )


def _packages() -> list[MediaPackage]:
    return [
        MediaPackage(
            package_id="pkg_paused_001",
            name="Paused Package",
            delivery_type="guaranteed",
            cpm=10.0,
            impressions=500_000,
            format_ids=[],
            product_id="prod_paused",
            budget=5000.0,
        )
    ]


def _create(adapter: MockAdServer, *, paused: bool | None):
    return adapter.create_media_buy(_request(paused=paused), _packages(), _START, _END)


class TestPausedBuyIsBookedPaused:
    def test_paused_request_books_paused_packages(self, integration_db):
        """A paused request comes back with paused packages (the seller's booked state)."""
        response = _create(_adapter(), paused=True)

        assert [pkg.paused for pkg in response.packages] == [True]

    def test_unpaused_request_books_unpaused_packages(self, integration_db):
        """Counterfactual: without the flag the same buy books unpaused."""
        response = _create(_adapter(), paused=False)

        assert [pkg.paused for pkg in response.packages] == [False]


class TestPausedBuyDoesNotDeliver:
    def test_paused_buy_reports_zero_delivery(self, integration_db):
        """A buy booked paused mid-flight reports no impressions and no spend."""
        adapter = _adapter()
        response = _create(adapter, paused=True)
        today = datetime.now(UTC)

        delivery = adapter.get_media_buy_delivery(
            response.media_buy_id,
            ReportingPeriod(start=_START, end=today),
            today,
        )

        assert delivery.totals.impressions == 0
        assert delivery.totals.spend == 0.0

    def test_unpaused_buy_reports_delivery(self, integration_db):
        """Counterfactual: the same mid-flight buy delivers when it is not paused.

        Without this row, a bug that zeroed ALL delivery would pass the paused
        assertion above.
        """
        adapter = _adapter()
        response = _create(adapter, paused=False)
        today = datetime.now(UTC)

        delivery = adapter.get_media_buy_delivery(
            response.media_buy_id,
            ReportingPeriod(start=_START, end=today),
            today,
        )

        assert delivery.totals.impressions > 0
        assert delivery.totals.spend > 0.0

    def test_paused_buy_does_not_start_the_delivery_simulator(self, integration_db):
        """The simulator is never started for a paused buy, even when enabled."""
        adapter = _adapter(delivery_simulation={"enabled": True})

        with patch("src.services.delivery_simulator.delivery_simulator") as simulator:
            _create(adapter, paused=True)

        simulator.start_simulation.assert_not_called()

    def test_unpaused_buy_starts_the_delivery_simulator(self, integration_db):
        """Counterfactual: the simulator still starts for an unpaused buy."""
        adapter = _adapter(delivery_simulation={"enabled": True})

        with patch("src.services.delivery_simulator.delivery_simulator") as simulator:
            _create(adapter, paused=False)

        assert simulator.start_simulation.call_count == 1

"""Steps for local-gam-geo-targeting.feature.

The tenant sells through the REAL Google Ad Manager adapter
(``MediaBuyCreateEnv.sell_through_gam``), and the scenarios grade what it sends to GAM's
SOAP API, which an in-process stand-in records. The pinned authority is stated in the
feature file's header; this module is only the wiring.
"""

from __future__ import annotations

import json

from pytest_bdd import given, parsers, then

from tests.bdd.steps.domain.local_gam_line_item_flight import _only_line_item
from tests.bdd.steps.generic.given_media_buy import _set_targeting_overlay


@given(parsers.parse("the package targeting_overlay for the create is {overlay}"))
def given_create_package_overlay(ctx: dict, overlay: str) -> None:
    """Put the overlay, a JSON object, on the request's one package."""
    _set_targeting_overlay(ctx, overlay=json.loads(overlay))


@then(parsers.parse("the line item sent to Google Ad Manager carries geoTargeting {geo_targeting}"))
def then_line_item_geo_targeting(ctx: dict, geo_targeting: str) -> None:
    """The one line item GAM received targets exactly these locations."""
    sent = _only_line_item(ctx)["targeting"].get("geoTargeting")
    assert sent == json.loads(geo_targeting), f"GAM line item geoTargeting: {sent!r}"


@then(
    parsers.parse('the refusal is UNSUPPORTED_FEATURE naming capability "{capability}" and rejected value {rejected}')
)
def then_refusal_names_geo_code(ctx: dict, capability: str, rejected: str) -> None:
    """The wire refusal names the overlay field and the code(s), a JSON value, GAM cannot book."""
    ctx["result"].assert_wire_error(
        "UNSUPPORTED_FEATURE",
        recovery="correctable",
        require_suggestion=True,
        details={"capability": capability, "rejected_value": json.loads(rejected)},
    )


@then(parsers.parse("the refusal is INVALID_REQUEST on targeting_overlay with geo_disjoint {geo_disjoint}"))
def then_refusal_geo_disjoint(ctx: dict, geo_disjoint: str) -> None:
    """A finer inclusion wholly outside the listed countries leaves nowhere to deliver."""
    ctx["result"].assert_wire_error(
        "INVALID_REQUEST",
        recovery="correctable",
        require_suggestion=True,
        field="targeting_overlay",
        details={"geo_disjoint": json.loads(geo_disjoint)},
    )


@then("no order was created in Google Ad Manager")
def then_no_gam_order(ctx: dict) -> None:
    """The refusal came before the adapter's first write to GAM."""
    orders = ctx["env"].gam_objects_sent("OrderService", "createOrders")
    assert orders == [], f"Expected no GAM order before the refusal, GAM received {orders}"

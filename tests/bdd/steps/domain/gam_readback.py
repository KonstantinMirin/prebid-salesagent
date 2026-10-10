"""Steps for local-gam-buy-readback.feature.

The seller is made a GAM seller by ``MediaBuyCreateEnv.sell_through_gam`` (the
Background's step lives in ``local_gam_line_item_flight``), and the buy is created
through the REAL adapter against the GAM stand-in. ``MediaBuyCreateListEnv`` then serves
the two reads a buyer makes of that buy: get_media_buys (dispatched by the UC-019 When,
whose Then grades the status) and get_media_buy_delivery (dispatched here). Every
expected value is the scenario's own: the package ids are the ones the create response
returned, the rates are the products' prices, the spend is what GAM reported.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pytest_bdd import given, parsers, then, when

from src.core.schemas import GetMediaBuyDeliveryRequest
from tests.bdd.steps._outcome_helpers import wire_dict, wire_field
from tests.bdd.steps.domain.gam_adapter import dispatch_gam_create
from tests.bdd.steps.domain.gam_trafficking import html_creative
from tests.bdd.steps.generic._dispatch import dispatch_request

#: The creative agent whose reference catalog defines the formats the GAM products sell.
_REFERENCE_AGENT_URL = "https://creative.adcontextprotocol.org"


# ── Given ─────────────────────────────────────────────────────────────────


@given(
    parsers.parse(
        'a GAM product "{product_id}" selling "{format_id}" at a fixed {cpm} USD CPM '
        'under pricing option "{pricing_option_id}"'
    )
)
def given_gam_product_selling_format(
    ctx: dict, product_id: str, format_id: str, cpm: str, pricing_option_id: str
) -> None:
    option = ctx["env"].add_gam_product(
        product_id,
        delivery_type="non_guaranteed",
        cpm=cpm,
        implementation_config={},
        pricing_option_id=pricing_option_id,
        format_id=format_id,
    )
    ctx.setdefault("gam_pricing_options", {})[product_id] = option.pricing_option_id
    ctx.setdefault("gam_formats", {})[product_id] = {"agent_url": _REFERENCE_AGENT_URL, "id": format_id}


@given(
    parsers.parse(
        'the Buyer Agent created a media buy starting now with packages "{packages}", each with an inline HTML creative'
    )
)
def given_created_buy_with_inline_creatives(ctx: dict, packages: str) -> None:
    """Create the buy through the real GAM adapter and capture what the response returned.

    The package ids are read off the create response, keyed by the product each package
    echoes: they are the seller's identifiers, and nothing the request carried could
    rebuild them.
    """
    dispatch_gam_create(
        ctx,
        packages,
        start_time="asap",
        end_time=(datetime.now(UTC) + timedelta(days=14)).isoformat(),
        package_extras=lambda product_id: {
            "creatives": [html_creative(f"html-{product_id}", ctx["gam_formats"][product_id])]
        },
    )
    assert ctx.get("error") is None, f"create_media_buy failed: {ctx.get('error')!r}"
    ctx["created_media_buy_id"] = wire_field(ctx, "media_buy_id")
    ctx["created_media_buy_status"] = wire_field(ctx, "media_buy_status")
    ctx["created_package_ids"] = {pkg["product_id"]: pkg["package_id"] for pkg in wire_field(ctx, "packages")}


@given(
    parsers.parse(
        'Google Ad Manager reports {first_impressions:d} impressions and {first_spend} USD for line item "{first}" '
        'and {second_impressions:d} impressions and {second_spend} USD for line item "{second}"'
    )
)
def given_gam_reports_line_item_delivery(
    ctx: dict,
    first_impressions: int,
    first_spend: str,
    first: str,
    second_impressions: int,
    second_spend: str,
    second: str,
) -> None:
    ctx["env"].gam_reports_delivery(
        {first: (first_impressions, first_spend), second: (second_impressions, second_spend)}
    )


# ── When ──────────────────────────────────────────────────────────────────


@when("the Buyer Agent requests delivery for that media buy")
def when_request_delivery_for_created_buy(ctx: dict) -> None:
    dispatch_request(ctx, req=GetMediaBuyDeliveryRequest(media_buy_ids=[ctx["created_media_buy_id"]]))


# ── Then ──────────────────────────────────────────────────────────────────


def _delivered_packages(ctx: dict) -> list[dict[str, Any]]:
    """The by_package entries of the created buy's delivery, as the buyer received them."""
    media_buy_id = ctx["created_media_buy_id"]
    deliveries = [d for d in wire_dict(ctx).get("media_buy_deliveries", []) if d.get("media_buy_id") == media_buy_id]
    assert len(deliveries) == 1, f"expected one delivery for {media_buy_id!r}, got {deliveries!r}"
    return deliveries[0]["by_package"]


@then(parsers.parse('the create response reported media_buy_status "{status}"'))
def then_create_response_status(ctx: dict, status: str) -> None:
    assert ctx["created_media_buy_status"] == status, (
        f"create_media_buy returned media_buy_status {ctx['created_media_buy_status']!r}, expected {status!r}"
    )


@then("the delivery reports exactly the packages the create response returned")
def then_delivery_reports_created_packages(ctx: dict) -> None:
    reported = sorted(pkg["package_id"] for pkg in _delivered_packages(ctx))
    created = sorted(ctx["created_package_ids"].values())
    assert reported == created, f"delivery reported packages {reported}, the create response returned {created}"


@then(
    parsers.parse(
        'the delivery for the "{product_id}" package is {impressions:d} impressions and {spend} USD '
        "at a {pricing_model} rate of {rate} {currency}"
    )
)
def then_package_delivery(
    ctx: dict, product_id: str, impressions: int, spend: str, pricing_model: str, rate: str, currency: str
) -> None:
    package_id = ctx["created_package_ids"][product_id]
    matching = [pkg for pkg in _delivered_packages(ctx) if pkg["package_id"] == package_id]
    assert len(matching) == 1, f"expected one delivery entry for package {package_id!r}, got {matching!r}"
    (package,) = matching
    reported = tuple(package.get(key) for key in ("impressions", "spend", "pricing_model", "rate", "currency"))
    expected = (float(impressions), float(spend), pricing_model, float(rate), currency)
    assert reported == expected, f"package {package_id!r} ({product_id}) delivered {reported}, expected {expected}"

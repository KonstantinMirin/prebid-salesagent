"""Steps for the local Google Ad Manager features: what a GAM seller sends GAM, and what it reports.

local-gam-seller.feature: the Given makes the env's tenant a GAM seller
(``GamSellerMixin.sell_through_gam``): from then on the tool's adapter is production's
``GoogleAdManager``, built from the seeded rows, and the only stand-in under it is Google's
SOAP client. The Thens read two things: the buyer's wire response, and the stand-in GAM
network's record of what the seller sent it and what it created. Their expectations are the
scenario's literals, or links the stand-in itself established (the id it gave the order), so
nothing is compared with what the harness seeded.

local-gam-delivery-report.feature: the Givens make the tenant a GAM seller whose network
reports for the buyer's advertiser (``DeliveryPollEnv.report_through_gam``); the UC-004 steps
send the request and read the buyer's wire response.

A GAM scenario states GAM's answers through the stand-in client. It does not combine with
the Givens that configure the ``MagicMock`` adapter, which do nothing once the seller
sells through GAM.
"""

from __future__ import annotations

from typing import Any

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps._outcome_helpers import assert_by_package_exactly, capture_created_media_buy, wire_field
from tests.bdd.steps.generic._dispatch import dispatch_request
from tests.helpers.gam_client import gam_delivery_row


@given(
    parsers.parse(
        'the seller sells through Google Ad Manager as trafficker "{trafficker_id}" on ad unit '
        '"{ad_unit_id}", and the buyer is its advertiser "{advertiser_id}"'
    )
)
def given_seller_sells_through_gam(ctx: dict, trafficker_id: str, ad_unit_id: str, advertiser_id: str) -> None:
    """Onboard the env's tenant to GAM and sell every product the scenario built on one ad unit.

    The products the product Given built, or the route's seeded product when the scenario
    built none.
    """
    ctx["env"].sell_through_gam(
        trafficker_id=trafficker_id,
        advertiser_id=advertiser_id,
        ad_unit_id=ad_unit_id,
        products=list(ctx.get("products", {}).values()) or [ctx["default_product"]],
    )


@given(parsers.parse("the seller's {delivery_type} product has pricing options:"))
def given_product_pricing_options(ctx: dict, delivery_type: str, datatable: list[list[str]]) -> None:
    """Build the seller's products, each with the pricing options its rows state.

    Columns: ``product`` (a label naming the product; rows sharing a label are one
    product's options, and a table without the column builds one product),
    ``pricing_option_id``, ``pricing_model``, ``fixed_price`` and ``floor_price`` (one of the
    two; ``fixed_price`` makes the option fixed). The products are recorded under their
    labels in ``ctx["products"]``; the first product and its first option become
    ``ctx["default_product"]`` / ``ctx["default_pricing_option"]``, the keys the route's seed
    sets. It does not sell them: the seller Given sells every product built here.
    """
    from decimal import Decimal

    from tests.factories import PricingOptionFactory, ProductFactory

    header, *rows = datatable
    products = ctx.setdefault("products", {})
    options = []
    for row in rows:
        cells = dict(zip(header, (cell.strip() for cell in row), strict=True))
        label = cells.get("product", delivery_type)
        if label not in products:
            products[label] = ProductFactory(
                tenant=ctx["tenant"],
                product_id=label,
                delivery_type=delivery_type,
                property_tags=["all_inventory"],
            )
        fixed = bool(cells.get("fixed_price"))
        option = PricingOptionFactory(
            product=products[label],
            pricing_option_id=cells["pricing_option_id"],
            pricing_model=cells["pricing_model"],
            currency="USD",
            is_fixed=fixed,
            rate=Decimal(cells["fixed_price"]) if fixed else None,
            price_guidance=None if fixed else {"floor": float(cells["floor_price"])},
        )
        options.append(option)
    ctx["default_product"] = next(iter(products.values()))
    ctx["default_pricing_option"] = options[0]


@given(parsers.parse("the buyer's packages, over a {days:d}-day flight, are:"))
def given_buyer_packages(ctx: dict, days: int, datatable: list[list[str]]) -> None:
    """The request's packages, one per row, over a flight of *days* days starting tomorrow.

    Columns: ``product`` (a label from the product Given; without the column, every package
    is on ``ctx["default_product"]``), ``pricing_option_id``, ``budget`` and ``bid_price``
    (empty for a fixed price).
    """
    from tests.bdd.steps.generic.given_media_buy import _ensure_request_defaults, _future
    from tests.factories.request import PackageRequestFactory

    kwargs = _ensure_request_defaults(ctx)
    kwargs["start_time"] = _future(1).isoformat()
    kwargs["end_time"] = _future(1 + days).isoformat()
    header, *rows = datatable
    packages = []
    for row in rows:
        cells = dict(zip(header, (cell.strip() for cell in row), strict=True))
        product = ctx["products"][cells["product"]] if "product" in cells else ctx["default_product"]
        package: dict[str, Any] = {
            "product_id": product.product_id,
            "pricing_option_id": cells["pricing_option_id"],
            "budget": float(cells["budget"]),
        }
        if cells.get("bid_price"):
            package["bid_price"] = float(cells["bid_price"])
        packages.append(PackageRequestFactory.payload(**package))
    kwargs["packages"] = packages


@given("the buyer already has another active media buy with this seller")
def given_buyer_has_another_active_buy(ctx: dict) -> None:
    """One more buy of this principal, active and mid-flight, with one package.

    It makes a delivery request's filter observable: a request naming no buy reads every
    active buy of the principal, which reports this one and not a buy the scenario just
    created. The Then compares the reported buys with the created one alone, so this buy
    needs no name.
    """
    from tests.factories import MediaBuyFactory

    MediaBuyFactory(tenant=ctx["tenant"], principal=ctx["principal"], status="active")


def _line_item_for(ctx: dict, product_label: str) -> Any:
    """The line item GAM created for the package on *product_label*, matched by its own price.

    Not by position: among the line items the stand-in network created, the one whose
    ``costPerUnit`` is the product's fixed rate. Exactly one line item per package, and
    exactly one match.
    """
    line_items = ctx["env"].gam_objects_created("LineItemService", "createLineItems")
    packages = ctx["request_kwargs"]["packages"]
    assert len(line_items) == len(packages), (
        f"expected GAM to create one line item per package ({len(packages)}); it created {len(line_items)}"
    )
    rate = ctx["products"][product_label].pricing_options[0].rate
    micros = round(float(rate) * 1_000_000)
    matching = [item for item in line_items if int(item["costPerUnit"]["microAmount"]) == micros]
    assert len(matching) == 1, (
        f"expected exactly one line item priced {rate} for the {product_label!r} package; "
        f"line items cost {[item['costPerUnit']['microAmount'] for item in line_items]}"
    )
    return matching[0]


@given(
    parsers.re(
        r"Google Ad Manager reports (?P<impressions>\d+) impressions and (?P<spend>[\d.]+) spend for the "
        r"\"(?P<reported>[^\"]+)\" package's line item, and "
        r"(?:(?P<other_impressions>\d+) impressions and (?P<other_spend>[\d.]+) spend|nothing) for the "
        r"\"(?P<other>[^\"]+)\" package's line item"
    )
)
def given_gam_reports_line_items(
    ctx: dict,
    impressions: str,
    spend: str,
    reported: str,
    other_impressions: str | None,
    other_spend: str | None,
    other: str,
) -> None:
    """GAM's finished report holds a row for each package's line item it states figures for.

    "nothing" is no row for that line item. Each row names the line item and order the
    stand-in network created, and the order's advertiser.
    """
    orders = {str(order["id"]): order for order in ctx["env"].gam_objects_created("OrderService", "createOrders")}
    stated = [(reported, impressions, spend)]
    if other_impressions is not None and other_spend is not None:
        stated.append((other, other_impressions, other_spend))
    rows = []
    for label, label_impressions, label_spend in stated:
        line_item = _line_item_for(ctx, label)
        order = orders[str(line_item["orderId"])]
        rows.append(
            gam_delivery_row(
                advertiser_id=str(order["advertiserId"]),
                order_id=str(order["id"]),
                line_item_id=str(line_item["id"]),
                impressions=int(label_impressions),
                spend=float(label_spend),
            )
        )
    ctx["env"].serve_gam_report_rows(rows)


@when("the Buyer Agent requests delivery for the media buy it just created")
def when_request_delivery_for_created_buy(ctx: dict) -> None:
    """Capture the buy and packages create_media_buy returned, and request that buy's delivery.

    The ids are read off the create response's wire. The request is a built
    ``GetMediaBuyDeliveryRequest``, so every transport sends the same request.
    """
    from src.core.schemas import GetMediaBuyDeliveryRequest

    media_buy_id = capture_created_media_buy(ctx)
    ctx["created_package_ids"] = {
        package["product_id"]: package["package_id"] for package in wire_field(ctx, "packages")
    }
    dispatch_request(ctx, req=GetMediaBuyDeliveryRequest(media_buy_ids=[media_buy_id]))


@then(
    "the delivery report covers only the media buy it just created, "
    "with exactly these packages under the ids create_media_buy returned:"
)
def then_delivery_covers_created_buy_packages(ctx: dict, datatable: list[list[str]]) -> None:
    """The report is the created buy alone, and its packages are the created ones with these figures.

    Each row's ``package`` is a product label; it names the package create_media_buy
    returned for that product.
    """
    deliveries = wire_field(ctx, "media_buy_deliveries")
    reported = [delivery.get("media_buy_id") for delivery in deliveries]
    assert reported == [ctx["created_media_buy_id"]], (
        f"expected a report of exactly the created buy {ctx['created_media_buy_id']!r}; it reported {reported}"
    )
    header, *rows = datatable
    expected = {}
    for row in rows:
        cells = dict(zip(header, (cell.strip() for cell in row), strict=True))
        product_id = ctx["products"][cells.pop("package")].product_id
        expected[ctx["created_package_ids"][product_id]] = cells
    assert_by_package_exactly(deliveries[0], expected)


@given(
    parsers.parse(
        "the seller reports delivery from Google Ad Manager, which has reported {impressions:d} impressions "
        'and {spend:g} spend so far for the buyer\'s advertiser "{advertiser_id}"'
    )
)
def given_gam_reported_so_far(ctx: dict, impressions: int, spend: float, advertiser_id: str) -> None:
    """GAM's report for the buyer's advertiser holds the figures it has so far."""
    ctx["env"].report_through_gam(advertiser_id=advertiser_id, impressions=impressions, spend=spend)


@given(
    parsers.parse(
        "the seller reports delivery from Google Ad Manager, which has reported nothing yet "
        'for the buyer\'s advertiser "{advertiser_id}"'
    )
)
def given_gam_reported_nothing(ctx: dict, advertiser_id: str) -> None:
    """GAM's report for the buyer's advertiser finishes with no rows."""
    ctx["env"].report_through_gam(advertiser_id=advertiser_id)


@given(
    parsers.parse(
        "the seller reports delivery from Google Ad Manager, which fails the report job "
        'for the buyer\'s advertiser "{advertiser_id}"'
    )
)
def given_gam_fails_report_job(ctx: dict, advertiser_id: str) -> None:
    """GAM's report job for the buyer's advertiser ends FAILED."""
    ctx["env"].report_through_gam(advertiser_id=advertiser_id, job_status="FAILED")


def _orders_created(ctx: dict) -> list[Any]:
    """The orders the stand-in GAM network created, each carrying the id it assigned."""
    return ctx["env"].gam_objects_created("OrderService", "createOrders")


@then(
    parsers.parse(
        "the buyer holds a media buy booked in Google Ad Manager as one order, "
        'for advertiser "{advertiser_id}", trafficked by "{trafficker_id}"'
    )
)
def then_one_order_for_advertiser(ctx: dict, advertiser_id: str, trafficker_id: str) -> None:
    """The buyer received a media_buy_id, and GAM created exactly one order for its advertiser."""
    wire_field(ctx, "media_buy_id")
    orders = [(str(order["advertiserId"]), str(order["traffickerId"])) for order in _orders_created(ctx)]
    assert orders == [(advertiser_id, trafficker_id)], (
        f"expected GAM to create one order for advertiser {advertiser_id} trafficked by {trafficker_id}; "
        f"it created {orders}"
    )


@then(
    parsers.parse(
        'Google Ad Manager received one line item, in that order, targeting ad unit "{ad_unit_id}" with its descendants'
    )
)
def then_one_line_item_on_ad_unit(ctx: dict, ad_unit_id: str) -> None:
    """The seller sent one line item, under the order GAM created, targeting the product's ad unit."""
    orders = _orders_created(ctx)
    assert len(orders) == 1, f"expected GAM to create exactly one order; it created {len(orders)}"
    line_items = [
        (str(item["orderId"]), item["targeting"]["inventoryTargeting"]["targetedAdUnits"])
        for item in ctx["env"].gam_objects_sent("LineItemService", "createLineItems")
    ]
    expected = [(str(orders[0]["id"]), [{"adUnitId": ad_unit_id, "includeDescendants": True}])]
    assert line_items == expected, f"expected GAM to receive line items {expected}; it received {line_items}"

"""Steps for the local-gam-*.feature files: what a Google Ad Manager seller sends GAM.

The Given makes the env's tenant a GAM seller (``GamSellerMixin.sell_through_gam``). The
Thens read two things: the buyer's wire response, and the stand-in GAM network's record of
what the seller sent it and what it created. Their expectations are the scenario's
literals, or links the stand-in itself established (the id it gave the order), so nothing
is compared with what the harness seeded.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps._outcome_helpers import wire_field
from tests.bdd.steps.generic._table import rows as table_rows


@given(
    parsers.re(
        r'the seller sells through Google Ad Manager as trafficker "(?P<trafficker_id>[^"]+)" on ad unit '
        r'"(?P<ad_unit_id>[^"]+)", and the buyer is its advertiser "(?P<advertiser_id>[^"]+)"'
        r'(?:, on a network (?:in time zone "(?P<network_time_zone>[^"]+)"'
        r'|that refuses to name its time zone with "(?P<network_fault>[^"]+)"))?'
        r"(?:, with product settings '(?P<product_settings>[^']*)')?"
    )
)
def given_seller_sells_through_gam(
    ctx: dict,
    trafficker_id: str,
    ad_unit_id: str,
    advertiser_id: str,
    network_time_zone: str | None,
    network_fault: str | None,
    product_settings: str | None,
) -> None:
    """Onboard the env's tenant to GAM and sell every product the scenario built on one ad unit.

    The products are the scenario's default product and any further products a Given built
    beside it (``ctx["extra_products"]``). The optional network clause states the GAM
    network's own time zone, or the ``ApiError`` reason with which the network refuses to
    name it; without it the stand-in network keeps its default zone. The optional
    product-settings clause is a JSON object of ``implementation_config`` keys the seller
    wrote over the generated GAM configuration of each product it sells. A scenario that
    needs another seller fact adds a clause to this sentence rather than a second seller
    Given.
    """
    ctx["env"].sell_through_gam(
        trafficker_id=trafficker_id,
        advertiser_id=advertiser_id,
        ad_unit_id=ad_unit_id,
        products=[ctx["default_product"], *(product for product, _ in ctx.get("extra_products") or [])],
        network_time_zone=network_time_zone,
        network_fault=network_fault,
        implementation_config=json.loads(product_settings) if product_settings is not None else None,
    )


@given(parsers.re(r"the seller's (?P<delivery>guaranteed|non-guaranteed) products? (?:has|have) pricing options:"))
def given_seller_products_with_pricing_options(ctx: dict, delivery: str, datatable: Any) -> None:
    """Build the scenario's products, one per ``product_id`` in the table, with the listed pricing options.

    Columns: ``product_id | pricing_option_id | pricing_model | fixed_price | floor_price``.
    A row with a ``fixed_price`` is a fixed option at that rate; a row without one is an
    auction option with that ``floor_price``. Rows keep their order within each product, so
    a product's first row is its first pricing option.

    The first product becomes the scenario's default product and its first option the
    default pricing option, the two keys the route's seed sets; every further product is
    added to ``ctx["extra_products"]``, which the seller Given sells beside the default
    product. This step does not make the tenant a GAM seller: the seller Given that follows
    it does.
    """
    env = ctx["env"]
    options_by_product: dict[str, list[dict[str, Any]]] = {}
    for row in table_rows(datatable):
        fixed_price = row["fixed_price"].strip()
        options_by_product.setdefault(row["product_id"], []).append(
            {
                "pricing_option_id": row["pricing_option_id"],
                "pricing_model": row["pricing_model"],
                "is_fixed": bool(fixed_price),
                "rate": Decimal(fixed_price) if fixed_price else None,
                "price_guidance": None if fixed_price else {"floor": float(row["floor_price"])},
            }
        )
    built = [
        env.setup_product_chain(
            ctx["tenant"],
            product_id=product_id,
            delivery_type=delivery.replace("-", "_"),
            pricing_options=options,
        )
        for product_id, options in options_by_product.items()
    ]
    env._commit_factory_data()
    (ctx["default_product"], ctx["default_pricing_option"]), *extra = built
    ctx["extra_products"] = extra


@given(parsers.parse("the buyer's packages, over a {days:d}-day flight, are:"))
def given_buyer_packages_over_flight(ctx: dict, days: int, datatable: Any) -> None:
    """Replace the request's packages with the table's, over a flight exactly ``days`` long.

    Columns: ``product_id | pricing_option_id | budget | bid_price``; an empty ``bid_price``
    sends none. Each package is the DTO-bound ``PackageRequestFactory`` shape.
    """
    from tests.bdd.steps.generic.given_media_buy import _ensure_request_defaults, _set_flight_days
    from tests.factories.request import PackageRequestFactory

    kwargs = _ensure_request_defaults(ctx)
    _set_flight_days(kwargs, days)
    kwargs["packages"] = [
        PackageRequestFactory.payload(
            product_id=row["product_id"],
            pricing_option_id=row["pricing_option_id"],
            budget=float(row["budget"]),
            **({"bid_price": float(row["bid_price"])} if row["bid_price"].strip() else {}),
        )
        for row in table_rows(datatable)
    ]


@given("a media buy awaits the seller's approval with one package on the product, stored without its pricing_info")
def given_pending_buy_without_pricing_info(ctx: dict) -> None:
    """Persist a 14-day buy awaiting approval whose one package row has its budget and no ``pricing_info``.

    The row a pending writer stored before it kept the terms of the selected option: the
    request names the product's first option, and nothing on the row says which option the
    package bought.
    """
    from tests.factories import MediaBuyFactory, MediaPackageFactory

    product = ctx["default_product"]
    package = {
        "product_id": product.product_id,
        "budget": 420.0,
        "pricing_option_id": ctx["default_pricing_option"].pricing_option_id,
    }
    start = datetime.now(UTC) + timedelta(days=1)
    end = start + timedelta(days=14)
    media_buy = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        budget=Decimal("420"),
        start_date=start.date(),
        end_date=end.date(),
        start_time=start,
        end_time=end,
        raw_request={
            "brand": {"domain": "testbrand.com"},
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "packages": [package],
        },
    )
    MediaPackageFactory(media_buy=media_buy, package_id="pkg_a", budget=Decimal("420"), package_config=package)
    ctx["env"]._commit_factory_data()


@when("the seller approves the media buy")
def when_seller_approves_media_buy(ctx: dict) -> None:
    """The seller approves the one buy awaiting approval, as every Admin UI approval route does."""
    ctx["approval_result"] = ctx["env"].approve_pending_media_buy()


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


#: The keys of a GAM line item or order that carry its flight.
_FLIGHT_KEYS = ("startDateTimeType", "startDateTime", "endDateTime")


def _flights(ctx: dict, service: str, method: str) -> list[dict[str, Any]]:
    """For each object the stand-in GAM network created through ``service.method``, its flight keys that are present."""
    return [
        {key: created[key] for key in _FLIGHT_KEYS if key in created}
        for created in ctx["env"].gam_objects_created(service, method)
    ]


def _gam_datetime(literal: str, time_zone: str) -> dict[str, Any]:
    """The GAM ``DateTime`` for a ``YYYY-MM-DD HH:MM:SS`` wall clock read in ``time_zone``."""
    wall_clock = datetime.strptime(literal, "%Y-%m-%d %H:%M:%S")
    return {
        "date": {"year": wall_clock.year, "month": wall_clock.month, "day": wall_clock.day},
        "hour": wall_clock.hour,
        "minute": wall_clock.minute,
        "second": wall_clock.second,
        "timeZoneId": time_zone,
    }


@then(
    parsers.re(
        r'Google Ad Manager received one line item, starting (?:at "(?P<start>[^"]+)"|immediately) '
        r'and ending at "(?P<end>[^"]+)" in time zone "(?P<zone>[^"]+)"'
    )
)
def then_one_line_item_flight(ctx: dict, start: str | None, end: str, zone: str) -> None:
    """GAM created exactly one line item, whose flight is the scenario's wall clocks in the stated zone.

    A stated start is an explicit ``startDateTime``; "immediately" is
    ``startDateTimeType: IMMEDIATELY`` with no ``startDateTime``. Exact equality, so a second
    line item, a start sent in both forms, or a wrong zone label fails it.
    """
    expected_start: dict[str, Any] = (
        {"startDateTime": _gam_datetime(start, zone)} if start is not None else {"startDateTimeType": "IMMEDIATELY"}
    )
    expected = [{**expected_start, "endDateTime": _gam_datetime(end, zone)}]
    flights = _flights(ctx, "LineItemService", "createLineItems")
    assert flights == expected, f"expected GAM to create one line item with flight {expected}; it created {flights}"


@then("Google Ad Manager received one order, carrying no flight dates of its own")
def then_one_order_without_flight(ctx: dict) -> None:
    """GAM created exactly one order, and the seller sent it none of the flight keys GAM derives from its line items."""
    flights = _flights(ctx, "OrderService", "createOrders")
    assert flights == [{}], f"expected GAM to create one order carrying no flight dates; it created {flights}"


#: The line item columns the booking Then compares, each read off the line item the seller sent.
_LINE_ITEM_READERS = {
    "lineItemType": lambda item: item["lineItemType"],
    "priority": lambda item: item["priority"],
    "costType": lambda item: item["costType"],
    "costPerUnitMicros": lambda item: item["costPerUnit"]["microAmount"],
    "goalType": lambda item: item["primaryGoal"]["goalType"],
    "unitType": lambda item: item["primaryGoal"]["unitType"],
    "units": lambda item: item["primaryGoal"]["units"],
}

#: The columns whose cells are integers in GAM's line item.
_INTEGER_COLUMNS = frozenset({"priority", "costPerUnitMicros", "units"})


@then("Google Ad Manager received these line items, in package order:")
def then_line_items_in_package_order(ctx: dict, datatable: Any) -> None:
    """The seller sent GAM exactly these line items, one per package in the request's order.

    Columns: ``lineItemType | priority | costType | costPerUnitMicros | goalType | unitType |
    units``; ``costPerUnitMicros`` is the ``microAmount`` of the line item's ``costPerUnit``,
    the price GAM bills each unit (or, for CPD, each day) at. The whole list is compared, so
    a missing, extra or reordered line item fails it. An integer column is compared with its
    type, so a float goal (GAM's ``Goal.units`` is a long) fails it.
    """
    expected = [
        {column: (int, int(cell)) if column in _INTEGER_COLUMNS else cell for column, cell in row.items()}
        for row in table_rows(datatable)
    ]
    sent = [
        {
            column: (type(value), value) if column in _INTEGER_COLUMNS else value
            for column, value in ((column, read(item)) for column, read in _LINE_ITEM_READERS.items())
        }
        for item in ctx["env"].gam_objects_sent("LineItemService", "createLineItems")
    ]
    assert sent == expected, (
        f"expected GAM to receive line items {expected}; it received {sent} (approval: {ctx.get('approval_result')})"
    )


@then("the seller's approval books the media buy")
def then_approval_books_media_buy(ctx: dict) -> None:
    """The approval ran the adapter to the end, and no buy of the tenant awaits approval any longer."""
    result = ctx["approval_result"]
    assert result.ok, f"expected the seller's approval to book the media buy; it returned {result}"
    pending = ctx["env"].media_buys_awaiting_approval()
    assert pending == [], f"expected no media buy to await approval; {len(pending)} still do"


@then("the seller's approval fails on the package's missing pricing_info, and the media buy still awaits approval")
def then_approval_fails_on_missing_pricing_info(ctx: dict) -> None:
    """The approval failed naming the missing ``pricing_info``, and left the buy awaiting approval."""
    from src.core.tools.media_buy_create import ApprovalOutcome

    result = ctx["approval_result"]
    assert result.outcome is ApprovalOutcome.FAILED and "missing pricing_info" in (result.error_msg or ""), (
        f"expected the approval to fail on the package's missing pricing_info; it returned {result}"
    )
    pending = ctx["env"].media_buys_awaiting_approval()
    assert len(pending) == 1, f"expected the media buy to still await approval; {len(pending)} buys do"


@then("Google Ad Manager received no order and no line item")
def then_no_order_and_no_line_item(ctx: dict) -> None:
    """The seller sent GAM no order and no line item: the refusal left nothing behind in GAM."""
    sent = {
        method: ctx["env"].gam_objects_sent(service, method)
        for service, method in (("OrderService", "createOrders"), ("LineItemService", "createLineItems"))
    }
    assert sent == {"createOrders": [], "createLineItems": []}, f"expected GAM to receive nothing; it received {sent}"

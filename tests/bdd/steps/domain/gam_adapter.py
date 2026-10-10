"""Steps for the GAM-seller features (local-gam-*.feature).

Each feature header states its authority. This module is the wiring for
local-gam-line-item-booking.feature: the seller is made a GAM seller by
``MediaBuyCreateEnv.sell_through_gam`` (the Background's step lives in
``local_gam_line_item_flight``), the Givens add its products, the When dispatches a
create_media_buy built from the request factory through ``dispatch_request``, and the
Thens read the line items the REAL adapter sent to the GAM stand-in.
local-gam-delivery-report.feature reuses the UC-004 delivery steps and adds only the
report failure below.

WHAT MAKES THESE NON-VACUOUS. Every expected number is the scenario's own arithmetic --
a package's budget at its own product's CPM -- and two packages of the same budget at
different CPMs must book different goals, which no buy-level computation can produce.
Each Then picks the line item out by the product it was booked for (the line item name
is the product id under the default naming template), so a goal booked on the wrong
package fails rather than matching by position.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps._outcome_helpers import wire_field
from tests.bdd.steps.generic._dispatch import dispatch_request
from tests.factories.request import OMIT, CreateMediaBuyRequestFactory, PackageRequestFactory

if TYPE_CHECKING:
    from tests.harness.media_buy_create import MediaBuyCreateEnv


def _env(ctx: dict) -> MediaBuyCreateEnv:
    return ctx["env"]


def _line_item_for(ctx: dict, product_id: str) -> dict[str, Any]:
    booked = _env(ctx).gam_line_items_sent()
    matching = [item for item in booked if item["name"] == product_id]
    assert len(matching) == 1, (
        f"expected exactly one GAM line item booked for {product_id!r}, got {[item['name'] for item in booked]}"
    )
    return matching[0]


# ── Given ─────────────────────────────────────────────────────────────────


@given(
    parsers.parse(
        'a {delivery_type} GAM product "{product_id}" at a fixed {cpm} USD CPM, '
        "configured with priority {priority:d} and a {goal_type} goal"
    )
)
def given_gam_product(ctx: dict, delivery_type: str, product_id: str, cpm: str, priority: int, goal_type: str) -> None:
    option = _env(ctx).add_gam_product(
        product_id,
        delivery_type=delivery_type,
        cpm=cpm,
        implementation_config={"priority": priority, "primary_goal_type": goal_type},
    )
    ctx.setdefault("gam_pricing_options", {})[product_id] = option.pricing_option_id


# ── When ──────────────────────────────────────────────────────────────────


def dispatch_gam_create(
    ctx: dict,
    packages: str,
    *,
    start_time: str,
    end_time: str,
    package_extras: Callable[[str], dict[str, Any]] = lambda _product_id: {},
) -> None:
    """Dispatch a create_media_buy whose packages are ``"product:budget, ..."`` at each GAM
    product's own pricing option, with *package_extras* (by product id) on each package."""
    package_payloads = []
    for spec in packages.split(","):
        product_id, budget = spec.strip().split(":")
        package_payloads.append(
            PackageRequestFactory.payload(
                product_id=product_id,
                budget=float(budget),
                pricing_option_id=ctx["gam_pricing_options"][product_id],
                **package_extras(product_id),
            )
        )
    dispatch_request(
        ctx,
        **CreateMediaBuyRequestFactory.payload(
            # The env names the account it seeded for this seller.
            account=OMIT,
            start_time=start_time,
            end_time=end_time,
            packages=package_payloads,
        ),
    )


@when(parsers.parse('the Buyer Agent creates a {days:d}-day media buy with packages "{packages}"'))
def when_create_gam_media_buy(ctx: dict, days: int, packages: str) -> None:
    start = (datetime.now(UTC) + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    dispatch_gam_create(
        ctx, packages, start_time=start.isoformat(), end_time=(start + timedelta(days=days)).isoformat()
    )


# ── Then ──────────────────────────────────────────────────────────────────


@then("the buyer receives the GAM order as its media buy")
def then_media_buy_is_gam_order(ctx: dict) -> None:
    assert wire_field(ctx, "media_buy_id") == _env(ctx).gam_order_id()


@then(
    parsers.parse('the GAM line item for "{product_id}" books a {goal_type} goal of {units:d} {unit_type}'),
)
def then_line_item_goal(ctx: dict, product_id: str, goal_type: str, units: int, unit_type: str) -> None:
    goal = _line_item_for(ctx, product_id)["primaryGoal"]
    assert (goal["goalType"], goal["unitType"], goal["units"]) == (goal_type, unit_type, units), (
        f"line item for {product_id!r} booked {goal}"
    )


@then(parsers.parse('the GAM line item for "{product_id}" is a {line_item_type} line item at priority {priority:d}'))
def then_line_item_priority(ctx: dict, product_id: str, line_item_type: str, priority: int) -> None:
    item = _line_item_for(ctx, product_id)
    assert (item["lineItemType"], item["priority"]) == (line_item_type, priority), (
        f"line item for {product_id!r} booked as {item['lineItemType']} at priority {item['priority']}"
    )


@given("the tenant reports delivery from Google Ad Manager")
def given_tenant_reports_from_gam(ctx: dict) -> None:
    ctx["env"].sell_through_gam()


@given("Google Ad Manager fails the delivery report")
def given_gam_report_fails(ctx: dict) -> None:
    ctx["env"].fail_gam_report()

"""Steps for what a Google Ad Manager seller sends GAM.

Serves local-gam-seller.feature (create_media_buy on ``MediaBuyCreateEnv``) and
local-uc006-gam-assignment-trafficking.feature (sync_creatives and the seller's creative
approval on ``CreativeSyncEnv``). The seller Given makes the env's tenant a GAM seller
(``GamSellerMixin.sell_through_gam``). The Thens read two things: the buyer's wire response,
and the stand-in GAM network's record of what the seller sent it and what it created. Their
expectations are the scenario's literals, or links the stand-in itself established (the ids
it gave the order and the creative), so nothing is compared with what the harness seeded.
"""

from __future__ import annotations

from typing import Any

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps._outcome_helpers import wire_field
from tests.bdd.steps.domain.uc006_sync_creatives import when_sync_creative_with_assignments
from tests.bdd.steps.generic._account_resolution import ensure_tenant_principal


@given(
    parsers.parse(
        'the seller sells through Google Ad Manager as trafficker "{trafficker_id}" on ad unit '
        '"{ad_unit_id}", and the buyer is its advertiser "{advertiser_id}"'
    )
)
def given_seller_sells_through_gam(ctx: dict, trafficker_id: str, ad_unit_id: str, advertiser_id: str) -> None:
    """Onboard the env's tenant to GAM and sell the scenario's product on one ad unit.

    An env that seeds no product (``CreativeSyncEnv``) gets one here, with the default
    pricing option, so its booked buys are on a product the seller sells.
    """
    if "default_product" not in ctx:
        from tests.factories import PricingOptionFactory, ProductFactory

        ensure_tenant_principal(ctx, ctx["env"])
        ctx["default_product"] = ProductFactory(tenant=ctx["tenant"])
        PricingOptionFactory(product=ctx["default_product"])
    ctx["env"].sell_through_gam(
        trafficker_id=trafficker_id,
        advertiser_id=advertiser_id,
        ad_unit_id=ad_unit_id,
        products=[ctx["default_product"]],
    )


@given(
    parsers.parse(
        'the package references the buyer\'s approved 300x250 image creative "{ready_id}" showing "{ready_url}" '
        'and its creative "{held_id}" showing "{held_url}" that awaits the seller\'s review'
    )
)
def given_package_references_ready_and_held_creatives(
    ctx: dict, ready_id: str, ready_url: str, held_id: str, held_url: str
) -> None:
    """Two library creatives in the format the GAM product sells, both named in the package's creative_ids."""
    from tests.bdd.steps.generic.given_media_buy import _add_creative_ids_to_package
    from tests.factories.creative import CreativeFactory

    for creative_id, url, status in ((ready_id, ready_url, "approved"), (held_id, held_url, "pending_review")):
        CreativeFactory(
            creative_id=creative_id,
            tenant=ctx["tenant"],
            principal=ctx["principal"],
            format="display_300x250_image",
            status=status,
            data={"assets": {"banner_image": {"url": url, "width": 300, "height": 250}}},
        )
    ctx["env"]._commit_factory_data()
    _add_creative_ids_to_package(ctx, [ready_id, held_id])


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


# ═══════════════════════════════════════════════════════════════════════
# sync_creatives onto buys already booked in GAM
# (local-uc006-gam-assignment-trafficking.feature, on CreativeSyncEnv)
# ═══════════════════════════════════════════════════════════════════════


@given("the creative agent serves the reference creative formats")
def given_creative_agent_serves_reference_formats(ctx: dict) -> None:
    """The creative agent answers a lookup of a reference-catalog format with that format."""
    ctx["env"].serve_reference_formats()


@given(
    parsers.re(
        r'the buyer holds a buy booked in Google Ad Manager as order "(?P<order_id>\d+)"'
        r'(?: in status "(?P<status>[^"]+)")? whose package "(?P<package>[^"]+)" is line item '
        r'"(?P<line_item>\d+)" accepting (?P<width>\d+)x(?P<height>\d+)$'
    )
)
def given_buyer_holds_booked_buy(
    ctx: dict, order_id: str, status: str | None, package: str, line_item: str, width: str, height: str
) -> None:
    """A buy of the buyer's, booked in GAM: its one package is the stated line item."""
    ctx["env"].book_in_gam(
        package_id=package,
        line_item_id=line_item,
        size=(int(width), int(height)),
        order_id=order_id,
        product=ctx["default_product"],
        status=status or "pending_creatives",
    )


def _image_creative(creative_id: str, url: str) -> dict[str, Any]:
    """A 300x250 image creative as the buyer sends it, in the reference format the GAM product sells."""
    from src.core.format_cache import DEFAULT_AGENT_URL
    from tests.factories.creative_asset import build_assets, image_spec
    from tests.factories.request import CreativeAssetRequestFactory

    return CreativeAssetRequestFactory.payload(
        creative_id=creative_id,
        name=f"Creative {creative_id}",
        format_id={"agent_url": DEFAULT_AGENT_URL, "id": "display_300x250_image"},
        assets=build_assets(image_spec("banner_image", url=url)),
    )


@given(
    parsers.re(
        r'the buyer (?P<tense>syncs|synced) a 300x250 image creative "(?P<creative_id>[^"]+)" showing '
        r'"(?P<url>[^"]+)" assigned to package "(?P<package>[^"]+)"'
        r"(?: with weight (?P<weight>\d+))?(?P<dry_run> as a dry run)?$"
    )
)
def given_buyer_syncs_image_creative(
    ctx: dict, tense: str, creative_id: str, url: str, package: str, weight: str | None, dry_run: str | None
) -> None:
    """The buyer's sync of one image creative assigned to one package: sent now ("synced"), or by the When.

    A sync sent now goes through the scenario's transport like the When's, and must have
    succeeded, so a later step grades what the seller did with it rather than a refusal.
    """
    ctx["creatives"] = [_image_creative(creative_id, url)]
    ctx["assignments"] = {creative_id: [package]}
    if weight is not None:
        ctx["assignment_terms"] = {(creative_id, package): {"weight": int(weight)}}
    if dry_run:
        ctx["dry_run"] = True
    if tense == "synced":
        when_sync_creative_with_assignments(ctx)
        assert ctx.get("error") is None, f"the buyer's earlier sync of {creative_id!r} failed: {ctx.get('error')!r}"
        ctx.pop("creatives", None)
        ctx.pop("assignments", None)
        ctx.pop("assignment_terms", None)
        ctx.pop("dry_run", None)


_REFERENCES_LIBRARY_CREATIVE = (
    'references library creative "{creative_id}", without resending it, assigned to package "{package}"'
)


@when(parsers.parse("the Buyer Agent " + _REFERENCES_LIBRARY_CREATIVE))
def when_buyer_references_library_creative(ctx: dict, creative_id: str, package: str) -> None:
    """Sync an assignment of a library creative without resending its content.

    ``creatives`` is required (sync-creatives-request.json, minItems 1), so it carries one
    other creative, assigned nowhere.
    """
    ctx["creatives"] = [_image_creative(f"{creative_id}-unassigned", "https://example.com/unassigned.png")]
    ctx["assignments"] = {creative_id: [package]}
    when_sync_creative_with_assignments(ctx)


@when(parsers.parse('the seller approves creative "{creative_id}"'))
def when_seller_approves_creative(ctx: dict, creative_id: str) -> None:
    """The seller approves the creative in the Admin UI's review queue."""
    ctx["env"].approve_creative_as_seller(creative_id)


def _creatives_created(ctx: dict) -> list[Any]:
    """The creatives the stand-in GAM network created, each carrying the id it assigned."""
    return ctx["env"].gam_objects_created("CreativeService", "createCreatives")


@then(
    parsers.re(
        r"Google Ad Manager created (?:one image creative|image creatives) for advertiser "
        r'"(?P<advertiser_id>\d+)" showing "(?P<urls>[^"]+)"$'
    )
)
def then_gam_created_image_creatives(ctx: dict, advertiser_id: str, urls: str) -> None:
    """GAM holds exactly these creatives from this scenario, in order: images for the advertiser, showing the URLs."""
    created = [(c["xsi_type"], str(c["advertiserId"]), c.get("imageUrl")) for c in _creatives_created(ctx)]
    expected = [("ImageRedirectCreative", advertiser_id, url.strip()) for url in urls.split(",")]
    assert created == expected, f"expected GAM to create {expected}; it created {created}"


@then("Google Ad Manager created no creative")
def then_gam_created_no_creative(ctx: dict) -> None:
    """Nothing reached GAM's CreativeService."""
    created = _creatives_created(ctx)
    assert created == [], f"expected GAM to create no creative; it created {created}"


def _licas_created(ctx: dict) -> list[Any]:
    """The line item creative associations the stand-in GAM network created, in order."""
    return ctx["env"].gam_objects_created("LineItemCreativeAssociationService", "createLineItemCreativeAssociations")


def _associations(ctx: dict) -> list[tuple[str, str]]:
    """(creative id, line item id) of each line item creative association GAM created, in order."""
    return [(str(a["creativeId"]), str(a["lineItemId"])) for a in _licas_created(ctx)]


@then(parsers.re(r'Google Ad Manager associated that creative with line items "(?P<line_items>[^"]+)"$'))
def then_gam_associated_with_line_items(ctx: dict, line_items: str) -> None:
    """GAM holds the one creative it created on exactly these line items, each once, in this order."""
    created = _creatives_created(ctx)
    assert len(created) == 1, f"'that creative' names one creative; GAM created {len(created)}"
    expected = [(str(created[0]["id"]), line_item.strip()) for line_item in line_items.split(",")]
    assert _associations(ctx) == expected, f"expected GAM to hold {expected}; it holds {_associations(ctx)}"


@then(parsers.parse('Google Ad Manager associated that creative with line item "{line_item}" at weight {weight:d}'))
def then_gam_associated_at_weight(ctx: dict, line_item: str, weight: int) -> None:
    """The association carries the assignment's weight as GAM's manual rotation weight."""
    reported = [(str(a["lineItemId"]), a.get("manualCreativeRotationWeight")) for a in _licas_created(ctx)]
    assert reported == [(line_item, weight)], f"expected one association at weight {weight}; GAM holds {reported}"


@then(parsers.parse('Google Ad Manager set line item "{line_item}" to manual creative rotation'))
def then_gam_line_item_manual_rotation(ctx: dict, line_item: str) -> None:
    """The seller updated the line item to MANUAL rotation, which GAM needs to honour weights."""
    updated = ctx["env"].gam_objects_sent("LineItemService", "updateLineItems")
    reported = [(str(item["id"]), item["creativeRotationType"]) for item in updated]
    assert reported == [(line_item, "MANUAL")], f"expected line item {line_item} set to MANUAL; GAM got {reported}"


@then("Google Ad Manager associated each creative it created with the line item it created")
def then_gam_associated_each_creative_with_created_line_item(ctx: dict) -> None:
    """Each creative GAM created is on the one line item GAM created, once, in creation order."""
    line_items = ctx["env"].gam_objects_created("LineItemService", "createLineItems")
    assert len(line_items) == 1, f"'the line item it created' names one line item; GAM created {len(line_items)}"
    expected = [(str(c["id"]), str(line_items[0]["id"])) for c in _creatives_created(ctx)]
    assert _associations(ctx) == expected, f"expected GAM to hold {expected}; it holds {_associations(ctx)}"


@then("Google Ad Manager was asked to approve the order it created, on booking and on the creative's approval")
def then_gam_approved_created_order_twice(ctx: dict) -> None:
    """Both approvals the seller sent GAM name the one order GAM created."""
    (order,) = _orders_created(ctx)
    order_actions = ctx["env"].mock["gam_client"].return_value.GetService("OrderService").performOrderAction
    approvals = [
        str(bound["value"]["value"])
        for action, statement in (call.args for call in order_actions.call_args_list)
        if action["xsi_type"].startswith("Approve")
        for bound in statement["values"]
        if bound["key"] == "orderId"
    ]
    assert approvals == [str(order["id"])] * 2, f"expected two approvals of order {order['id']}; GAM got {approvals}"

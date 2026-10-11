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

from tests.bdd.steps._outcome_helpers import wire_entry, wire_field
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
    from tests.factories.creative_asset import image_spec

    return _creative(creative_id, "display_300x250_image", image_spec("banner_image", url=url))


def _creative(creative_id: str, format_id: str, asset: Any) -> dict[str, Any]:
    """A creative as the buyer sends it: one asset, in reference-catalog format *format_id*."""
    from src.core.format_cache import DEFAULT_AGENT_URL
    from tests.factories.creative_asset import build_assets
    from tests.factories.request import CreativeAssetRequestFactory

    return CreativeAssetRequestFactory.payload(
        creative_id=creative_id,
        name=f"Creative {creative_id}",
        format_id={"agent_url": DEFAULT_AGENT_URL, "id": format_id},
        assets=build_assets(asset),
    )


@given(parsers.parse('the seller\'s product also sells the reference format "{format_id}"'))
def given_product_also_sells_format(ctx: dict, format_id: str) -> None:
    """The GAM product sells one more reference-catalog format, so a creative in it may be assigned."""
    from src.core.format_cache import DEFAULT_AGENT_URL

    product = ctx["default_product"]
    product.format_ids = [*product.format_ids, {"agent_url": DEFAULT_AGENT_URL, "id": format_id}]
    ctx["env"]._commit_factory_data()


@given(
    parsers.parse(
        'the creative agent previews a creative in the format "{format_id}" at "{preview_url}" as {width:d}x{height:d}'
    )
)
def given_creative_agent_previews(ctx: dict, format_id: str, preview_url: str, width: int, height: int) -> None:
    """The creative agent lists the format and answers preview_creative with one render: a link, and its size."""
    ctx["env"].preview_creatives_at(preview_url, format_id=format_id, width=width, height=height)


@given(
    parsers.parse(
        'the buyer syncs a 300x250 HTML creative "{creative_id}" with markup "{markup}" assigned to package "{package}"'
    )
)
def given_buyer_syncs_html_creative(ctx: dict, creative_id: str, markup: str, package: str) -> None:
    """The When's sync sends one creative in the reference HTML format, assigned to the package.

    Its one asset is HTML markup (core/assets/html-asset.json: ``asset_type: "html"``, the
    markup in ``content``).
    """
    from tests.factories.creative_asset import asset_spec

    ctx["creatives"] = [
        _creative(creative_id, "display_300x250_html", asset_spec("html_creative", "html", content=markup))
    ]
    ctx["assignments"] = {creative_id: [package]}


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


@then(parsers.parse('creative "{creative_id}" is assigned to package "{package}"'))
def then_creative_assigned_to_package(ctx: dict, creative_id: str, package: str) -> None:
    """The sync's entry for the creative lists exactly that package in ``assigned_to``."""
    entry = wire_entry(ctx, "creatives", creative_id=creative_id)
    assert entry.get("assigned_to") == [package], (
        f"expected creative {creative_id!r} assigned to [{package!r}]; the entry is {entry!r}"
    )


@then(parsers.parse('creative "{creative_id}" reports package "{package}" in assignment_errors and not in assigned_to'))
def then_creative_package_in_assignment_errors(ctx: dict, creative_id: str, package: str) -> None:
    """sync-creatives-response.json: ``assigned_to`` lists only the packages the creative was assigned to."""
    entry = wire_entry(ctx, "creatives", creative_id=creative_id)
    assert package in (entry.get("assignment_errors") or {}) and package not in (entry.get("assigned_to") or []), (
        f"expected package {package!r} in assignment_errors and not in assigned_to; the entry is {entry!r}"
    )


def _creatives_created(ctx: dict) -> list[Any]:
    """The creatives the stand-in GAM network created, each carrying the id it assigned."""
    return ctx["env"].gam_objects_created("CreativeService", "createCreatives")


def _assert_creatives_created(ctx: dict, expected: list[tuple[str, str, str | None, str | None]]) -> None:
    """GAM created exactly *expected*: (type, advertiser id, image URL, snippet) of each creative, in order."""
    created = [
        (c["xsi_type"], str(c["advertiserId"]), c.get("imageUrl"), c.get("snippet")) for c in _creatives_created(ctx)
    ]
    assert created == expected, f"expected GAM to create {expected}; it created {created}"


@then(parsers.parse('Google Ad Manager created one image creative for advertiser "{advertiser_id}" showing "{url}"'))
def then_gam_created_one_image_creative(ctx: dict, advertiser_id: str, url: str) -> None:
    """GAM holds exactly one creative from this scenario: an image for the advertiser, showing the URL."""
    _assert_creatives_created(ctx, [("ImageRedirectCreative", advertiser_id, url, None)])


@then(
    parsers.parse(
        'Google Ad Manager created one third-party creative for advertiser "{advertiser_id}" whose snippet is '
        '"{snippet}" and which names no image URL'
    )
)
def then_gam_created_one_third_party_creative(ctx: dict, advertiser_id: str, snippet: str) -> None:
    """GAM holds exactly one creative from this scenario: the markup itself, not a picture of a page."""
    _assert_creatives_created(ctx, [("ThirdPartyCreative", advertiser_id, None, snippet)])


@then("Google Ad Manager created no creative")
def then_gam_created_no_creative(ctx: dict) -> None:
    """Nothing reached GAM's CreativeService."""
    created = _creatives_created(ctx)
    assert created == [], f"expected GAM to create no creative; it created {created}"


def _associations(ctx: dict) -> list[tuple[str, str]]:
    """(creative id, line item id) of each line item creative association GAM created, in order."""
    created = ctx["env"].gam_objects_created("LineItemCreativeAssociationService", "createLineItemCreativeAssociations")
    return [(str(a["creativeId"]), str(a["lineItemId"])) for a in created]


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
    created = ctx["env"].gam_objects_created("LineItemCreativeAssociationService", "createLineItemCreativeAssociations")
    reported = [(str(a["lineItemId"]), a.get("manualCreativeRotationWeight")) for a in created]
    assert reported == [(line_item, weight)], f"expected one association at weight {weight}; GAM holds {reported}"


@then(parsers.parse('Google Ad Manager set line item "{line_item}" to manual creative rotation'))
def then_gam_line_item_manual_rotation(ctx: dict, line_item: str) -> None:
    """The seller updated the line item to MANUAL rotation, which GAM needs to honour weights."""
    updated = ctx["env"].gam_objects_sent("LineItemService", "updateLineItems")
    reported = [(str(item["id"]), item["creativeRotationType"]) for item in updated]
    assert reported == [(line_item, "MANUAL")], f"expected line item {line_item} set to MANUAL; GAM got {reported}"


@then("Google Ad Manager received no order")
def then_gam_received_no_order(ctx: dict) -> None:
    """The seller sent GAM no order over the whole scenario."""
    orders = ctx["env"].gam_objects_sent("OrderService", "createOrders")
    assert orders == [], f"expected GAM to receive no order; it received {orders}"

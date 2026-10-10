"""Steps for the local GAM creative-trafficking feature.

The Givens seed through ``GamCreativeSyncEnv``; the Thens read what production sent
GAM's SOAP client, which the env records. The sync itself is dispatched by the UC-006
When ("the Buyer Agent syncs the creatives") and its assignment outcome is read by the
UC-006 Then, so this module adds only what is specific to GAM.
"""

from __future__ import annotations

from pytest_bdd import given, parsers, then

#: The creative's markup. Self-contained (no external script), so GAM's snippet checks
#: (src/adapters/gam/utils/validation.py) have nothing to refuse.
_HTML = '<div style="width:300px;height:250px;background:#0a5">Autumn sale</div>'


def html_creative(creative_id: str, format_id: dict[str, str]) -> dict:
    """An HTML creative in *format_id*: core/assets/html-asset.json (asset_type + content)."""
    return {
        "creative_id": creative_id,
        "name": "Autumn sale 300x250",
        "format_id": format_id,
        "assets": {"html_creative": {"asset_type": "html", "content": _HTML}},
    }


@given(
    parsers.parse(
        'a GAM seller whose live package "{package_id}" is trafficked as GAM line item "{line_item_id}" '
        'for format "{format_id}"'
    )
)
def given_gam_live_package(ctx: dict, package_id: str, line_item_id: str, format_id: str) -> None:
    env = ctx["env"]
    fmt = env.serve_reference_format(format_id)
    ctx["package"] = env.setup_gam_live_package(package_id=package_id, line_item_id=line_item_id, format_id=fmt)
    ctx["gam_format_id"] = fmt


@given(parsers.parse('an HTML creative "{creative_id}" assigned to package "{package_id}"'))
def given_html_creative_assigned(ctx: dict, creative_id: str, package_id: str) -> None:
    """An HTML creative in the seeded package's format."""
    ctx.setdefault("creatives", []).append(html_creative(creative_id, ctx["gam_format_id"]))
    ctx.setdefault("assignments", {}).setdefault(creative_id, []).append(package_id)


@then(
    parsers.parse(
        "GAM was sent one ThirdPartyCreative of size {width:d}x{height:d} for the buyer's GAM advertiser "
        "whose snippet is the creative's HTML"
    )
)
def then_gam_third_party_creative(ctx: dict, width: int, height: int) -> None:
    env = ctx["env"]
    (creative,) = env.gam_created_creatives()
    assert creative["xsi_type"] == "ThirdPartyCreative", f"GAM was sent a {creative['xsi_type']}: {creative!r}"
    assert creative["snippet"] == _HTML, f"snippet {creative['snippet']!r}, expected the creative's HTML"
    assert creative["size"] == {"width": width, "height": height}, f"size {creative['size']!r}"
    assert creative["advertiserId"] == env.GAM_ADVERTISER_ID, f"advertiserId {creative['advertiserId']!r}"


@then(parsers.parse('GAM was sent one association of the created creative with line item "{line_item_id}"'))
def then_gam_line_item_association(ctx: dict, line_item_id: str) -> None:
    env = ctx["env"]
    assert env.gam_line_item_associations() == [
        {"creativeId": env.GAM_CREATED_CREATIVE_ID, "lineItemId": line_item_id}
    ], f"GAM was sent associations {env.gam_line_item_associations()!r}"

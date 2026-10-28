"""UC-002 create_media_buy steps: v3.1 targeting, inline creatives, package terms, IO acceptance.

Every Given here shapes ``ctx["request_kwargs"]`` through the shared builders in
``tests/bdd/steps/generic/given_media_buy.py`` and seeds nothing a transport cannot reach;
dispatch is the shared create When, and every Then reads the dispatched wire.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from adcp.types import ErrorCode
from adcp.types.domains.enums.available_metric import AvailableMetric
from pytest_bdd import given, parsers, then

from src.core.product_conversion import default_reporting_capabilities
from tests.bdd.steps._outcome_helpers import wire_entry
from tests.bdd.steps.generic.given_media_buy import (
    _add_inline_creatives,
    _ensure_request_defaults,
    _set_catalogs,
    _set_targeting_overlay,
)
from tests.factories.creative_asset import AssetSpec, image_spec, text_spec
from tests.factories.malformed import malformed
from tests.helpers.egress_hatches import UNDIALLED_PUBLIC_HTTPS_ORIGIN

#: A complete overlay cap: core/frequency-cap.json's ``dependencies`` make max_impressions,
#: per and window travel together, so none of the three can be left out.
_OVERLAY_FREQUENCY_CAP: dict[str, Any] = {
    "max_impressions": 3,
    "per": "devices",
    "window": {"interval": 24, "unit": "hours"},
}


# ═══════════════════════════════════════════════════════════════════════
# Targeting overlay
# ═══════════════════════════════════════════════════════════════════════


@given("the package targeting_overlay carries a frequency_cap with no scope field")
def given_overlay_frequency_cap(ctx: dict) -> None:
    """An overlay cap carrying only core/frequency-cap.json's own properties."""
    _set_targeting_overlay(ctx, {"frequency_cap": dict(_OVERLAY_FREQUENCY_CAP)})


@given("the package targeting_overlay carries a frequency_cap with a scope property")
def given_overlay_frequency_cap_with_scope(ctx: dict) -> None:
    """The same cap plus ``scope``, a key core/frequency-cap.json does not declare."""
    _set_targeting_overlay(ctx, {"frequency_cap": {**_OVERLAY_FREQUENCY_CAP, "scope": "package"}})


def _collection_list(list_id: str) -> dict[str, str]:
    """A core/collection-list-ref.json reference. The origin is one no test dials."""
    return {"agent_url": f"{UNDIALLED_PUBLIC_HTTPS_ORIGIN}/collection-lists", "list_id": list_id}


_COLLECTION_LIST_OVERLAYS: dict[str, dict[str, Any]] = {
    "collection_list with valid agent_url and list_id": {"collection_list": _collection_list("cl-include")},
    "collection_list_exclude with valid agent_url and list_id": {
        "collection_list_exclude": _collection_list("cl-exclude"),
    },
    "both collection_list and collection_list_exclude set": {
        "collection_list": _collection_list("cl-include"),
        "collection_list_exclude": _collection_list("cl-exclude"),
    },
}


@given(parsers.parse('a create_media_buy request with package targeting matching "{boundary_point}"'))
def given_collection_list_targeting(ctx: dict, boundary_point: str) -> None:
    """Package targeting for the collection-list boundary rows (BR-RULE-014)."""
    if boundary_point not in _COLLECTION_LIST_OVERLAYS:
        raise ValueError(f"Unknown collection-list boundary point: {boundary_point!r}")
    _set_targeting_overlay(ctx, _COLLECTION_LIST_OVERLAYS[boundary_point])


#: The narrowing field each scenario sentence names on a core/targeting.json store_catchments item.
_STORE_CATCHMENT_NARROWING = {"catchment": "catchment_ids", "store": "store_ids"}


@given(
    parsers.parse(
        'the targeting includes a store_catchments entry for catalog "{catalog_id}" narrowed to {narrowing} "{value}"'
    )
)
def given_store_catchments_entry(ctx: dict, catalog_id: str, narrowing: str, value: str) -> None:
    """A store_catchments item in the pin's shape: a synced store catalog, narrowed by one field."""
    _set_targeting_overlay(
        ctx,
        {"store_catchments": [{"catalog_id": catalog_id, _STORE_CATCHMENT_NARROWING[narrowing]: [value]}]},
    )


@given("the targeting includes a geo_proximity entry providing BOTH radius and geometry")
def given_geo_proximity_two_methods(ctx: dict) -> None:
    """A geo_proximity item satisfying two arms of its oneOf at once (radius AND geometry)."""
    _set_targeting_overlay(
        ctx,
        {
            "geo_proximity": [
                {
                    "lat": 40.7128,
                    "lng": -74.0060,
                    "radius": {"value": 5, "unit": "km"},
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                }
            ],
        },
    )


# ═══════════════════════════════════════════════════════════════════════
# Inline creatives
# ═══════════════════════════════════════════════════════════════════════


def _drop_asset_type(asset: dict[str, Any]) -> None:
    del asset["asset_type"]


def _unknown_asset_type(asset: dict[str, Any]) -> None:
    asset["asset_type"] = "hologram"


#: boundary point -> (how the slot value is broken, how the creative is marked)
# Each entry breaks the typed asset in place and marks the creative it sits in. The
# malformed(...) calls keep their kind and reason literal at the call site, which is what
# makes each declaration auditable.
_ASSET_DISCRIMINATOR_BREAKS: dict[str, tuple[Callable[[dict], None], Callable[[dict], Any]]] = {
    "asset slot value with missing asset_type discriminator": (
        _drop_asset_type,
        lambda creative: malformed(
            "absent_key",
            "the asset slot value omits asset_type, the discriminator core/creative-asset.json's asset "
            "union selects an asset schema by, so the pin refuses it at the boundary as INVALID_REQUEST",
            creative,
            obligation=ErrorCode.INVALID_REQUEST,
        ),
    ),
    "asset slot value with unknown asset_type value": (
        _unknown_asset_type,
        lambda creative: malformed(
            "semantic",
            "asset_type names no member of the asset union, so no arm can be selected and the pin "
            "refuses it at the boundary as INVALID_REQUEST",
            creative,
            obligation=ErrorCode.INVALID_REQUEST,
        ),
    ),
}


@given(parsers.parse('a create_media_buy request with an inline creative matching "{boundary_point}"'))
def given_inline_creative_discriminator(ctx: dict, boundary_point: str) -> None:
    """One inline creative whose single asset carries a broken ``asset_type`` (BR-RULE-015)."""
    if boundary_point not in _ASSET_DISCRIMINATOR_BREAKS:
        raise ValueError(f"Unknown creative asset boundary point: {boundary_point!r}")
    breaks, mark = _ASSET_DISCRIMINATOR_BREAKS[boundary_point]
    _add_inline_creatives(ctx, count=1)
    pkg = ctx["request_kwargs"]["packages"][0]
    (creative,) = pkg["creatives"]
    typed = [asset for asset in creative["assets"].values() if isinstance(asset, dict) and "asset_type" in asset]
    assert len(typed) == 1, f"expected exactly one typed asset to break, got {list(creative['assets'])}"
    breaks(typed[0])
    pkg["creatives"] = [mark(creative)]


# ═══════════════════════════════════════════════════════════════════════
# Package terms: committed_metrics, measurement_terms, catalogs
# ═══════════════════════════════════════════════════════════════════════


@given("the request package includes committed_metrics with standard metric_id not in the product's available_metrics")
def given_committed_metric_outside_product(ctx: dict) -> None:
    """Seed the product's available_metrics, then propose a standard metric outside them."""
    advertised = [AvailableMetric.impressions, AvailableMetric.spend, AvailableMetric.clicks]
    proposed = AvailableMetric.foot_traffic
    assert proposed not in advertised
    ctx["default_product"].reporting_capabilities = default_reporting_capabilities().model_copy(
        update={"available_metrics": advertised}
    )
    ctx["env"]._commit_factory_data()
    kwargs = _ensure_request_defaults(ctx)
    kwargs["packages"][0]["committed_metrics"] = [{"scope": "standard", "metric_id": proposed.value}]


@then("the error should reference the offending committed_metrics entry")
def then_error_references_committed_metric(ctx: dict) -> None:
    """package-request.json: "reference the offending entry"; the one entry sent is [0]."""
    ctx["result"].assert_wire_error("TERMS_REJECTED", field="packages[0].committed_metrics[0]")


@given("the buyer attaches measurement_terms that the seller will not accept")
def given_unworkable_measurement_terms(ctx: dict) -> None:
    """The storyboard's aggressive proposal: a zero variance tolerance on a c28 window."""
    kwargs = _ensure_request_defaults(ctx)
    kwargs["packages"][0]["measurement_terms"] = {
        "billing_measurement": {
            "vendor": {"domain": "summit-measurement.example"},
            "measurement_window": "c28",
            "max_variance_percent": 0,
        },
        "makegood_policy": {"available_remedies": ["credit"]},
    }


@then("the error details should identify which measurement_terms are unworkable")
def then_error_identifies_measurement_terms(ctx: dict) -> None:
    """TERMS_REJECTED "SHOULD identify which specific term was rejected": a locator inside the terms."""
    result = ctx["result"]
    result.assert_wire_error("TERMS_REJECTED")
    located = (result.wire_error_object() or {}).get("field") or ""
    assert located.startswith("packages[0].measurement_terms."), (
        f"expected the rejection to locate a term under packages[0].measurement_terms, got field={located!r}"
    )


@given("a package targets a catalog whose items are brand offerings")
def given_offering_catalog(ctx: dict) -> None:
    """An inline offering-type catalog on the package; the next Given supplies its item."""
    _set_catalogs(ctx, [{"type": "offering", "items": []}])


def _asset_group(spec: AssetSpec) -> dict[str, Any]:
    """core/offering-asset-group.json holding one self-tagged item built from *spec*."""
    return {"asset_group_id": spec.role, "asset_type": spec.asset_type, "items": [spec.payload()[spec.role]]}


@given(
    parsers.parse(
        'the referenced offering "{offering_id}" has structured asset groups including "{text_group}" and "{image_group}"'
    )
)
def given_offering_with_asset_groups(ctx: dict, offering_id: str, text_group: str, image_group: str) -> None:
    """One core/offering.json item with a text asset group and an image asset group."""
    (catalog,) = ctx["request_kwargs"]["packages"][0]["catalogs"]
    catalog["items"] = [
        {
            "offering_id": offering_id,
            "name": "Summer Sale",
            "landing_url": "https://testbrand.com/summer-sale",
            "assets": [
                _asset_group(text_spec(text_group, content="Summer sale: 30% off")),
                _asset_group(
                    image_spec(image_group, url="https://testbrand.com/summer-landscape.png", width=1200, height=628)
                ),
            ],
        }
    ]


@then(
    parsers.parse(
        'the response package should echo the offering catalog carrying "{offering_id}" '
        'with asset groups "{text_group}" and "{image_group}"'
    )
)
def then_package_echoes_offering_catalog(ctx: dict, offering_id: str, text_group: str, image_group: str) -> None:
    """core/package.json catalogs: "Echoed from the create_media_buy request"."""
    package = wire_entry(ctx, "packages", index=0)
    offering_catalogs = [c for c in package.get("catalogs") or [] if c.get("type") == "offering"]
    assert len(offering_catalogs) == 1, f"expected one offering catalog echoed, got {package.get('catalogs')!r}"
    items = {item.get("offering_id"): item for item in offering_catalogs[0].get("items") or []}
    assert offering_id in items, f"offering {offering_id!r} not echoed; items={list(items)}"
    groups = [group.get("asset_group_id") for group in items[offering_id].get("assets") or []]
    assert groups == [text_group, image_group], f"expected asset groups {[text_group, image_group]}, got {groups}"


# ═══════════════════════════════════════════════════════════════════════
# io_acceptance shape (create-media-buy-request.json io_acceptance.required)
# ═══════════════════════════════════════════════════════════════════════

_IO_ACCEPTANCE: dict[str, str] = {
    "io_id": "prop-abc-2026.io.v1",
    "accepted_at": "2026-04-01T12:00:00Z",
    "signatory": "buyer-agent-12345",
}


@given(
    parsers.parse('a create_media_buy request with proposal_id "{proposal_id}" and an io_acceptance missing "{member}"')
)
def given_proposal_request_io_acceptance_missing(ctx: dict, proposal_id: str, member: str) -> None:
    """Committed-proposal execution (proposal_id + total_budget, no packages) whose io_acceptance lacks *member*."""
    assert member in _IO_ACCEPTANCE, f"{member!r} is not a required io_acceptance member"
    kwargs = _ensure_request_defaults(ctx)
    kwargs.pop("packages", None)
    kwargs["proposal_id"] = proposal_id
    kwargs["total_budget"] = {"amount": 5000.0, "currency": "USD"}
    kwargs["io_acceptance"] = {name: value for name, value in _IO_ACCEPTANCE.items() if name != member}


@then(parsers.parse('the error should reference the missing "{member}" member'))
def then_error_references_missing_io_member(ctx: dict, member: str) -> None:
    """The wire rejection locates the absent io_acceptance member."""
    ctx["result"].assert_wire_error("INVALID_REQUEST", field=f"io_acceptance.{member}")


# ═══════════════════════════════════════════════════════════════════════
# pending_creatives lifecycle (pending_creatives_to_start storyboard)
# ═══════════════════════════════════════════════════════════════════════


@given("the buyer sends create_media_buy without inline creatives")
def given_create_without_creatives(ctx: dict) -> None:
    """The default request, which carries neither inline creatives nor creative assignments."""
    kwargs = _ensure_request_defaults(ctx)
    for package in kwargs["packages"]:
        assert not ({"creatives", "creative_ids", "creative_assignments"} & package.keys()), (
            f"the default package already carries creatives: {sorted(package)}"
        )

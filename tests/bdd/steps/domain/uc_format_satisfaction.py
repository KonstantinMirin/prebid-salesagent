"""Steps for BR-UC-FORMAT-SATISFACTION: a format claim against a canonical declaration.

Setup stores a REAL dual-arm ``products`` row through ``ProductFactory`` -- the same factory
every other product fixture uses -- and the refusal is read off the WIRE through
``assert_wire_error``, which is the sanctioned error surface.

THREE TOOLS, because the satisfaction function has gates on three paths and the bead grades
all three. ``create_media_buy`` reuses the shared When from ``uc002_create_media_buy``;
``update_media_buy`` and ``sync_creatives`` get their own Whens here, which dispatch through
the same parametrized transport. The two in-feature envs differ and are routed by tag:
``@format_satisfaction`` takes ``MediaBuyDualEnv`` (create AND update dispatch off one
seeded chain) and ``@format_satisfaction_sync`` takes ``CreativeSyncEnv``.

TWO TABLES, and both of them are DATA rather than behaviour: one maps a declaration name to
the ``format_options`` document the seller stores, the other maps a selector name to the
package members the buyer sends. They are stored documents and request members -- the
faithful shapes -- not a registry of objects a factory should be building:
``core/product-format-declaration.json`` generates a sixteen-branch discriminated union over
``format_kind``, so the column holds a document and the model picks its branch on readback.
Naming each row lets the feature's Examples say which rule it is exercising instead of
carrying JSON a reader has to decode.
"""

from __future__ import annotations

import uuid
from typing import Any

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps._outcome_helpers import wire_absent, wire_entry, wire_field
from tests.factories import PricingOptionFactory, ProductFactory
from tests.factories.creative import DEFAULT_CREATIVE_AGENT_URL
from tests.factories.mint import mint

#: The legacy arm every product here also carries, matching ``MediaBuyCreateEnv``'s own
#: seeded default so the deprecated selector route and the rest of the create flow behave
#: exactly as they do for every other create scenario. The canonical arm is what varies.
_LEGACY_ARM: list[dict[str, str]] = [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}]

#: The option id the product publishes, and the id a publisher-scoped declaration publishes
#: under its own domain. Named once so a selector row and its declaration cannot drift.
_PRODUCT_OPTION_ID = "satisfaction_image_mrec"
_PUBLISHER_DOMAIN = "shorts.streamhaus.example"

#: What the seller STORES, per declaration name. Each is a
#: ``core/product-format-declaration.json`` document.
_DECLARATIONS: dict[str, list[dict[str, Any]]] = {
    # The conformance fixture's own shape: an image kind fixed at 300x250, publishing a
    # product-local option id and asserting the legacy id it projects to.
    "fixed_300x250": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "v1_format_ref": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
            "params": {"width": 300, "height": 250, "max_file_size_kb": 200},
        }
    ],
    # A RANGE constraint, which formats.mdx grades by containment rather than overlap.
    "duration_range": [
        {
            "format_kind": "video_hosted",
            "format_option_id": "satisfaction_video_range",
            "params": {"duration_ms_range": [5000, 60000]},
        }
    ],
    # A REQUIRED SLOT, which formats.mdx grades on both the group and the asset type.
    "required_slots": [
        {
            "format_kind": "video_hosted",
            "format_option_id": "satisfaction_video_slots",
            "params": {"slots": [{"asset_group_id": "video_main", "asset_type": "video", "required": True}]},
        }
    ],
    # A PUBLISHER-SCOPED option. The domain's presence is the pin's scope discriminator, so
    # this option and a product-local one sharing the id are different options.
    "publisher_300": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "publisher_domain": _PUBLISHER_DOMAIN,
            "params": {"width": 300, "height": 250},
        }
    ],
}

#: What the buyer SENDS on its package, per selector name. The members are
#: ``media-buy/package-request.json``'s three format selectors.
_SELECTORS: dict[str, dict[str, Any]] = {
    # --- selectors that satisfy ---
    "exact_300x250": {"format_kind": "image", "params": {"width": 300, "height": 250}},
    "product_option_ref": {"format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}]},
    # The legacy arm ALONE, which is what the storyboard's step 10
    # (create_media_buy_with_legacy_mrec_format) sends: format_ids and no format_kind, no
    # params. This row used to carry ``"format_kind": "image"`` as well, which the old
    # merged-claim design needed and which is NOT a shape any storyboard step sends -- and
    # once routes became independent the row correctly started failing, because a bare
    # ``image`` kind beside it is its own under-specified route (step 16). The fixture was
    # the defect, not the refusal: `bare_kind_beside_option_ref` below now grades that
    # two-route shape deliberately, and this one grades step 10 as written.
    "legacy_display_300x250": {"format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}]},
    "contained_range": {"format_kind": "video_hosted", "params": {"duration_ms_range": [10000, 30000]}},
    "covering_slots": {
        "format_kind": "video_hosted",
        "params": {"slots": [{"asset_group_id": "video_main", "asset_type": "video"}]},
    },
    "matching_publisher_claim": {
        "format_option_refs": [
            {"scope": "publisher", "publisher_domain": _PUBLISHER_DOMAIN, "format_option_id": _PRODUCT_OPTION_ID}
        ]
    },
    # Step 11: two co-present routes that BOTH resolve, to the same declaration. The
    # declaration asserts this exact legacy id in its v1_format_ref, so the legacy route is
    # a lookup rather than a guess.
    "option_plus_projectable_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
    # Step 12: a complete DIRECT canonical selector beside the legacy one, same declaration.
    "direct_plus_legacy": {
        "format_kind": "image",
        "params": {"width": 300, "height": 250},
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
    # --- selectors that do not ---
    # The storyboard's reject_bare_image_selector_for_fixed_mrec: the right kind, no params.
    "bare_image_kind": {"format_kind": "image"},
    # formats.mdx's fifth rule as an input: the same kind, different dimensions.
    "mismatched_728x90": {"format_kind": "image", "params": {"width": 728, "height": 90}},
    # A kind in the pinned vocabulary that THIS product does not publish -- the closed set.
    "unpublished_video_kind": {"format_kind": "video_hosted", "params": {"width": 300, "height": 250}},
    "unpublished_option_ref": {"format_option_refs": [{"scope": "product", "format_option_id": "no_such_option"}]},
    "overlapping_range": {"format_kind": "video_hosted", "params": {"duration_ms_range": [1000, 30000]}},
    "slot_missing": {
        "format_kind": "video_hosted",
        "params": {"slots": [{"asset_group_id": "caption", "asset_type": "text"}]},
    },
    # The same option id under a DIFFERENT publisher domain: the second half of the
    # exact-publisher-claim rule.
    "wrong_publisher_domain": {
        "format_option_refs": [
            {"scope": "publisher", "publisher_domain": "other.example", "format_option_id": _PRODUCT_OPTION_ID}
        ]
    },
    # Step 15, the ORDERING obligation: the option ref RESOLVES and the legacy id does not.
    # The refusal must be UNSUPPORTED_FEATURE naming format_ids -- not an acceptance on the
    # option route, and not CONFLICTING_SELECTORS.
    "option_plus_unprojectable_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "unmapped_legacy_selector_6648"}],
    },
    # Step 17: fixed-size image dimensions are ATOMIC, so width without height is
    # SCHEMA-invalid and belongs in the other error bucket -- INVALID_REQUEST, not
    # UNSUPPORTED_FEATURE. Measured: the pinned PackageRequest refuses it itself
    # ("violates a constraint its schema states outside its properties,
    # media-buy/package-request.json, root conjunct 3, over format_kind, height, params"),
    # so the refusal comes from the request boundary and never reaches the satisfaction
    # function at all. That is the right owner and the scenario below pins it, because the
    # alternative -- satisfaction answering UNSUPPORTED_FEATURE for a schema violation --
    # is exactly the bucket confusion the step exists to prevent.
    "width_without_height": {"format_kind": "image", "params": {"width": 300}},
    # "Canonical precedence MUST NOT hide the conflict" (step 13) as an input this stage can
    # grade: a resolving option ref beside an UNDER-SPECIFIED kind route. The kind route is
    # still resolved and still refused, so precedence is not a short circuit.
    "bare_kind_beside_option_ref": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_kind": "image",
    },
}


# ── Given steps ─────────────────────────────────────────────────────


@given("a tenant is configured for media buy creation")
def given_tenant_for_create(ctx: dict) -> None:
    """Assert the route already seeded a tenant and buyer, rather than seeding a second one.

    Both routes this feature uses seed before any Given runs -- the media-buy one seeds the
    whole create chain, the sync one a tenant and principal -- so the Background's job is to
    say the precondition exists and check it, not to establish it. A Background that seeded
    would create a SECOND tenant and leave the request pointing at whichever ran last, and
    ``setup_default_data`` re-creating a missing principal is how a later Given comes to
    undo an earlier one.

    The tenant is what BOTH routes have in common and so is what this asserts; the product
    is deliberately not checked, because the sync scenarios declare their own.
    """
    assert ctx.get("tenant") is not None, (
        "a format-satisfaction route must seed a tenant and principal before the Background runs; "
        "check the ENV_ROUTES rows claiming @format_satisfaction / @format_satisfaction_sync"
    )


@given(parsers.parse('the seller declares a canonical format option "{declaration}"'))
def given_declaration(ctx: dict, declaration: str) -> None:
    """Store a DUAL-ARM product -- the named canonical declarations plus the legacy arm.

    Dual-arm on purpose, and the feature's comment says why: a canonical-only product's
    legacy selector route is stage 4's to resolve, so seeding one would make these
    scenarios fail on an unwired route instead of on the satisfaction rule each names.

    The product becomes ``ctx["default_product"]``, which is what the shared create-request
    builder points the package at -- so the buyer's request names THIS product without this
    module duplicating the request literal.
    """
    from tests.bdd.steps.generic.given_media_buy import _ensure_request_defaults

    options = _DECLARATIONS[declaration]
    product = ProductFactory(
        tenant=ctx["tenant"],
        product_id=f"satisfaction_{declaration}",
        delivery_type="non_guaranteed",
        format_ids=list(_LEGACY_ARM),
        format_options=options,
        property_tags=["all_inventory"],
    )
    ctx["default_pricing_option"] = PricingOptionFactory(
        product=product, pricing_model="cpm", currency="USD", is_fixed=True
    )
    ctx["default_product"] = product
    # Built AFTER the product exists so the package names it; the builder reads
    # ctx["default_product"] and is guarded against re-running.
    ctx.pop("request_kwargs", None)
    _ensure_request_defaults(ctx)


@given(parsers.parse('the buyer assigns a creative identified by canonical kind "{kind}"'))
def given_canonical_creative(ctx: dict, kind: str) -> None:
    """Seed a creative carrying a CANONICAL identity and assign it to the package.

    ``canonical_kind`` rather than ``format``, which is the whole point: a creative seeded
    this way asserts NO legacy reference, so the four gates' deprecated comparison has
    nothing to compare and the canonical closed-set step is the only thing that can refuse
    it. The factory derives the stored columns through the same production mapping the sync
    path uses, so this row and a synced row cannot differ in shape.

    The asset is keyed ``banner_image`` -- a member of production's own
    ``MEDIA_ASSET_FALLBACK_IDS`` -- and that choice is forced by a real gap, not a fixture
    preference. The create path's pre-adapter gate reads a reference creative's URL and
    dimensions through ``extract_media_url_and_dimensions``, which finds the media asset
    EITHER by asking the legacy format spec for its ``asset_id`` OR from that allowlist. A
    canonical creative asserts no legacy reference, so no spec resolves and the allowlist is
    the only path left: the factory's default key (``banner``) is not in it, and the gate
    answered "missing required URL field in assets" for every canonical creative whatever
    its assets said. Measured here, filed as salesagent-ol033.16 against stage 6, whose job
    is reading a canonical manifest's assets off the declaration's SLOTS rather than off a
    deprecated format file.
    """
    from tests.factories.creative import CreativeFactory
    from tests.factories.creative_asset import build_assets, image_spec

    creative = CreativeFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        canonical_kind=kind,
        approved=True,
        data={"assets": build_assets(image_spec("banner_image"))},
    )
    ctx["env"]._commit_factory_data()
    ctx["request_kwargs"]["packages"][0]["creative_ids"] = [creative.creative_id]


def _seed_canonical_creative(ctx: dict, *, kind: str | None = None, format_id: str | None = None) -> Any:
    """One approved creative carrying the named identity arm, committed. Returns the row.

    The asset key is ``banner_image``, a member of production's own
    ``MEDIA_ASSET_FALLBACK_IDS``, and that is forced rather than chosen -- see
    salesagent-ol033.16 and the Given above it.
    """
    from tests.factories.creative import CreativeFactory
    from tests.factories.creative_asset import build_assets, image_spec

    arm: dict[str, Any] = {"canonical_kind": kind} if kind is not None else {"format": format_id}
    creative = CreativeFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        approved=True,
        data={"assets": build_assets(image_spec("banner_image"))},
        **arm,
    )
    ctx["env"]._commit_factory_data()
    return creative


# ── UPDATE path ─────────────────────────────────────────────────────


@given("the buyer already holds a media buy for that product")
def given_existing_media_buy(ctx: dict) -> None:
    """Seed a committed media buy with one package naming the canonical product.

    The package's ``package_config.product_id`` is what the update gate resolves the product
    from, so the buy has to name THIS product rather than the env's default one -- the gate
    would otherwise grade the selector against a product the scenario never declared.
    """
    from datetime import UTC, datetime, timedelta

    from tests.factories import MediaBuyFactory, MediaPackageFactory

    media_buy = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        status="pending_approval",
        currency="USD",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(days=30),
    )
    package = MediaPackageFactory(
        media_buy=media_buy,
        package_config={"product_id": ctx["default_product"].product_id, "budget": 5000.0},
    )
    ctx["env"]._commit_factory_data()
    ctx["existing_media_buy"] = media_buy
    ctx["existing_package"] = package


@given(parsers.parse('a creative identified by canonical kind "{kind}" exists'))
def given_creative_exists(ctx: dict, kind: str) -> None:
    """Seed the creative the update will assign, without assigning it yet."""
    ctx["creative_to_assign"] = _seed_canonical_creative(ctx, kind=kind)


@when("the Buyer Agent assigns that creative through update_media_buy")
def when_update_assigns_creative(ctx: dict) -> None:
    """Dispatch a real update_media_buy carrying the creative on its package.

    A RAW flat body: ``media_buy_id`` is what ``MediaBuyDualEnv._is_update_request`` routes
    on, and dispatching the flat kwargs sends them through the real route and production
    Pydantic rather than constructing the request in the test process -- the same reason the
    create side dispatches raw.
    """
    from tests.bdd.steps.generic._dispatch import dispatch_request

    dispatch_request(
        ctx,
        media_buy_id=ctx["existing_media_buy"].media_buy_id,
        account={"account_id": ctx["env"].setup_default_account().account_id},
        idempotency_key=mint(f"satisfaction-update-{uuid.uuid4().hex}"),
        packages=[
            {
                "package_id": ctx["existing_package"].package_id,
                "creative_ids": [ctx["creative_to_assign"].creative_id],
            }
        ],
    )


# ── ASSIGNMENT path (sync_creatives) ────────────────────────────────


@given("a packaged product declaring a canonical image option fixed at 300x250")
def given_sync_canonical_product(ctx: dict) -> None:
    """Seed tenant + principal + a DUAL-ARM product + a media buy and package to assign to.

    Its own seeding rather than the create chain's: ``CreativeSyncEnv`` is a different env
    with a different default seed, and the assignment gate resolves the product from
    ``package_config.product_id``, so the package has to name the product this scenario
    declared.
    """
    _seed_sync_chain(ctx, format_options=_DECLARATIONS["fixed_300x250"], format_ids=list(_LEGACY_ARM))


@given("a packaged product declaring only the deprecated format_ids")
def given_sync_legacy_product(ctx: dict) -> None:
    """The LEGACY-arm control for the lenient asymmetry: no ``format_options`` at all.

    Which lane the satisfaction function takes is decided by what the PRODUCT declares, so
    this is the one knob that moves the sibling scenario from the canonical lane to the
    deprecated one -- same tool, same mode, same condition.
    """
    _seed_sync_chain(ctx, format_options=None, format_ids=list(_LEGACY_ARM))


def _seed_sync_chain(
    ctx: dict, *, format_options: list[dict[str, Any]] | None, format_ids: list[dict[str, str]]
) -> None:
    """The product, media buy and package a sync_creatives assignment needs.

    The tenant and principal are the ROUTE's (``_seed_default_tenant_and_principal``), not
    re-seeded here: ``setup_default_data`` re-creates a missing principal, and calling it
    twice is how a Given comes to undo what the route already established.
    """
    from tests.factories import MediaBuyFactory, MediaPackageFactory

    tenant, principal = ctx["tenant"], ctx["principal"]
    product = ProductFactory(
        tenant=tenant,
        product_id="satisfaction_sync_product",
        delivery_type="non_guaranteed",
        format_ids=format_ids,
        format_options=format_options,
        property_tags=["all_inventory"],
    )
    PricingOptionFactory(product=product, pricing_model="cpm", currency="USD", is_fixed=True)
    media_buy = MediaBuyFactory(tenant=tenant, principal=principal)
    package = MediaPackageFactory(media_buy=media_buy, package_config={"product_id": product.product_id})
    ctx["env"]._commit_factory_data()
    ctx["default_product"] = product
    ctx["existing_package"] = package


#: The creative the sync scenarios send. One id, because the assignment is about this one
#: creative and the result is read off ``creatives[0]``.
_SYNC_CREATIVE_ID = "satisfaction_sync_creative"


@given(parsers.parse('the buyer syncs a creative identified by canonical kind "{kind}"'))
def given_sync_canonical_creative(ctx: dict, kind: str) -> None:
    """The creative payload the sync will carry, identified by its CANONICAL kind.

    A PAYLOAD rather than a pre-seeded row, because ``SyncCreativesRequest.creatives`` is
    required with ``min_length=1`` -- a buyer cannot assign without syncing, so sync-and-
    assign in one call IS the real flow and seeding a row then sending an empty list is a
    shape the pin refuses (measured: ``List should have at least 1 item``).

    ``format_id=OMIT`` is what makes it canonical: ``core/creative-asset.json`` is a oneOf
    on the identifier, so the legacy arm has to be ABSENT rather than null -- the pin
    reports absent and null identically, and the factory's ``OMIT`` is the only way a call
    site can say which it meant.
    """
    from tests.factories.request import OMIT, CreativeAssetRequestFactory

    ctx["creatives"] = [
        CreativeAssetRequestFactory.payload(creative_id=_SYNC_CREATIVE_ID, format_id=OMIT, format_kind=kind)
    ]


@given(parsers.parse('the buyer syncs a creative identified by format_id "{format_id}"'))
def given_sync_legacy_creative(ctx: dict, format_id: str) -> None:
    """The same payload identified by its DEPRECATED reference, for the legacy lane's row.

    The ONE difference from its canonical sibling is which identifier arm the creative
    carries, which is what decides the lane -- so the lenient asymmetry's two rows differ in
    the creative's arm and the product's arm and nothing else.
    """
    from tests.factories.request import CreativeAssetRequestFactory

    ctx["creatives"] = [
        CreativeAssetRequestFactory.payload(
            creative_id=_SYNC_CREATIVE_ID,
            format_id={"id": format_id, "agent_url": DEFAULT_CREATIVE_AGENT_URL},
        )
    ]


@given("the buyer asks for lenient validation")
def given_lenient(ctx: dict) -> None:
    """``validation_mode: "lenient"`` -- "skip what this product will not take"."""
    ctx["validation_mode"] = "lenient"


@when("the Buyer Agent assigns it to that package")
def when_sync_assigns(ctx: dict) -> None:
    """Dispatch a real sync_creatives that syncs the creative AND assigns it to the package."""
    from tests.bdd.steps.generic._dispatch import dispatch_request

    kwargs: dict[str, Any] = {
        "account": {"account_id": ctx["env"].setup_default_account().account_id},
        "creatives": ctx["creatives"],
        "assignments": [{"creative_id": _SYNC_CREATIVE_ID, "package_id": ctx["existing_package"].package_id}],
    }
    if "validation_mode" in ctx:
        kwargs["validation_mode"] = ctx["validation_mode"]
    dispatch_request(ctx, **kwargs)


@given(parsers.parse('the buyer\'s package selects "{selector}"'))
def given_selector(ctx: dict, selector: str) -> None:
    """Put the named format selector on the request's single package.

    MERGED onto the package the shared builder already assembled rather than replacing it:
    the package carries a product_id, a pricing_option_id and a budget that every other
    create scenario also sends, and a selector scenario is not about any of those.
    """
    packages = ctx["request_kwargs"]["packages"]
    assert len(packages) == 1, f"expected exactly one package to put a selector on, got {len(packages)}"
    packages[0].update(_SELECTORS[selector])


# ── Then steps ──────────────────────────────────────────────────────


@then("the buyer receives the media buy")
def then_media_buy_allocated(ctx: dict) -> None:
    """Assert the buy exists ON THE WIRE and the response carries no error.

    BOTH halves. ``media_buy_id`` alone is satisfied by a response that allocated the buy
    and then reported a problem alongside it, and an absent ``errors`` key alone is
    satisfied by any non-answer -- so a gate that refused the selector could pass either
    one of them on its own. Read off the serialized body rather than the typed result: the
    typed payload has already coerced every field to its declared type, and what the
    scenario claims is what the buyer received.
    """
    allocated = wire_entry(ctx, "packages", index=0)
    assert allocated.get("product_id") == ctx["default_product"].product_id, (
        f"the allocated package names {allocated.get('product_id')!r}, not the product the selector was graded against"
    )
    media_buy_id = wire_field(ctx, "media_buy_id")
    assert isinstance(media_buy_id, str) and media_buy_id, (
        f"expected a non-empty media_buy_id on the wire, got {media_buy_id!r}"
    )
    wire_absent(ctx, "errors")


@then(parsers.parse('the buyer is refused UNSUPPORTED_FEATURE naming the "{arm}" selector'))
def then_refused_unsupported_feature(ctx: dict, arm: str) -> None:
    """Assert the wire envelope: the code, its pinned recovery, and the field.

    ``assert_wire_error`` defaults ``recovery`` to the PINNED enum's classification for the
    code, so the recovery is graded without this scenario restating it -- UNSUPPORTED_FEATURE
    is ``correctable`` there ("check get_adcp_capabilities and remove unsupported fields"),
    which is the right lever for a buyer who can name a different format.

    The field is pinned because the two canonical selector arms are DIFFERENT fields and a
    refusal naming the wrong one sends the buyer to edit a selector they did not write. The
    buyer-facing message is deliberately not asserted: it is a function of the code through
    CODE_TABLE, so asserting both compares the table to itself.

    The feature's Examples name the ARM and the pointer is composed here, rather than the
    Examples carrying ``packages[0].format_kind`` whole. The square brackets are why: an
    Examples value lands in the pytest nodeid, and the BDD artifact readers take the FIRST
    bracketed token of a nodeid as the transport -- so a bracket inside a parametrize value
    silently misattributes every one of these scenarios to a transport named
    ``0].format_kind`` (salesagent-8qela.159 is that corruption measured on another suite).
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE", field=f"packages[0].{arm}")


@then("the update is accepted")
def then_update_accepted(ctx: dict) -> None:
    """Assert the update answered on the wire and carries no error.

    Paired halves, same reasoning as the create accept: ``media_buy_id`` alone is satisfied
    by a response that answered and then reported a problem, and an absent ``errors`` key
    alone is satisfied by a non-answer.
    """
    media_buy_id = wire_field(ctx, "media_buy_id")
    assert media_buy_id == ctx["existing_media_buy"].media_buy_id, (
        f"the update answered about {media_buy_id!r}, not the buy the scenario holds"
    )
    wire_absent(ctx, "errors")


@then(parsers.parse('the buyer is refused UNSUPPORTED_FEATURE naming the "{array}" array'))
def then_refused_naming_array(ctx: dict, array: str) -> None:
    """The UPDATE path's refusal, whose pointer names which creative array the buyer sent.

    ``packages[0].<array>`` composed here rather than written in the Examples, for the
    bracket reason the sibling Then records: a bracket inside a parametrize value lands in
    the nodeid and the BDD artifact readers take the first bracketed token as the transport.
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE", field=f"packages[0].{array}")


@then("the assignment is recorded with no assignment error")
def then_assignment_recorded(ctx: dict) -> None:
    """Assert the sync answered AND the creative's assignment carries no error for the package.

    BOTH halves, and the second is the load-bearing one: lenient mode answers SUCCESS while
    recording per-package failures in ``assignment_errors``, so a scenario asserting only
    that the sync succeeded would pass on a refusal that was merely recorded instead of
    raised. Read off the typed result because ``assignment_errors`` is a per-creative map
    the wire carries inside ``creatives[]``.
    """
    creative_results = ctx["result"].payload.creatives
    assert creative_results, "sync_creatives answered with no creative results"
    errors = creative_results[0].assignment_errors or {}
    assert not errors, f"expected no assignment error, got {errors!r}"


@then("the sync succeeds and records an assignment error for that package")
def then_assignment_error_recorded(ctx: dict) -> None:
    """Assert lenient mode SOFTENED the deprecated-arm refusal: success plus a recorded error.

    The control for the canonical row above. Three things together, because any two of them
    are satisfied by the wrong behaviour: the call succeeded (not refused), the error map
    names THIS package, and the recorded reason names both format identities -- the refused
    one and what the product accepts. The reason is graded on those VALUES and not on its
    wording, the same correction made to the sibling integration test.
    """
    result = ctx["result"]
    assert result.is_success, f"lenient mode should have answered success, got {result.error!r}"
    creative_results = result.payload.creatives
    assert creative_results, "sync_creatives answered with no creative results"
    package_id = ctx["existing_package"].package_id
    errors = creative_results[0].assignment_errors or {}
    assert package_id in errors, f"no assignment error recorded for {package_id!r}: {errors!r}"
    recorded = errors[package_id]
    assert "video_640x480" in recorded, f"the record does not name the refused format: {recorded}"
    assert "display_300x250" in recorded, f"the record does not name what the product accepts: {recorded}"


@then("the buyer is refused INVALID_REQUEST")
def then_refused_invalid_request(ctx: dict) -> None:
    """Assert the SCHEMA bucket, which is the point: a malformed selector is not an
    unsupported one.

    No ``field`` asserted, and that is this refusal's own shape rather than an omission: the
    pin's conjunct is stated at the PackageRequest ROOT (over ``format_kind``, ``height``
    and ``params`` jointly), so there is no single member to point at -- pinning one would
    assert a pointer the pinned model has no basis to emit. The CODE is the obligation the
    storyboard step states, and the code is what this grades.
    """
    ctx["result"].assert_wire_error("INVALID_REQUEST")


@then("the buyer is refused UNSUPPORTED_FEATURE")
def then_refused_unsupported_feature_bare(ctx: dict) -> None:
    """The ASSIGNMENT path's refusal: the code and its pinned recovery, no field.

    No ``field`` here, deliberately and not as an omission. The assignment gate refuses a
    STORED creative's identity, and ``core/error.json``'s ``field`` names a request field --
    which creative is in ``details.creative_id`` and which package in ``details.package_id``,
    both of which the raise site supplies. Asserting a pointer this path does not own would
    pin a value production has no reason to carry.
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE")


@then("the buyer is refused UNSUPPORTED_FEATURE naming the packages field")
def then_refused_naming_packages(ctx: dict) -> None:
    """The creative-side refusal, which names ``packages`` rather than one selector arm.

    A creative is not a selector: the buyer sent ``creative_ids``, and WHICH creative is in
    ``details.creative_id`` rather than in the pointer, because the pointer names a request
    FIELD and the request field here is the packages array. The same pointer the sibling
    creative refusals on this path already use (``PACKAGES_FIELD``).
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE", field="packages")

"""Steps for BR-UC-GET-PRODUCTS-format-options: stored canonical declarations on the wire.

Setup stores REAL ``products.format_options`` documents through ``ProductFactory`` — the
same factory every other product fixture uses — and dispatch reuses the shared
``the buyer requests products`` When from ``uc_get_products_inventory``. Assertions read
``wire_entry``, the serialized body, because the typed payload has already coerced every
field to its declared type and so cannot show a declaration that was lost on the way out.

The column holds a document rather than a model, and that is the faithful shape:
``core/product-format-declaration.json`` generates a sixteen-branch discriminated union over
``format_kind``, which the DTO declares by inheritance. Storing a document and letting the
model pick its branch on readback is what these scenarios exercise.
"""

from __future__ import annotations

import json
from typing import Any

from pytest_bdd import given, parsers, then

from tests.bdd.steps._outcome_helpers import wire_advisory_errors, wire_entry
from tests.factories import PricingOptionFactory, ProductFactory
from tests.factories.core import seed_property_tag_selection
from tests.factories.creative import DEFAULT_CREATIVE_AGENT_URL
from tests.factories.inventory_profile import InventoryProfileFactory
from tests.helpers.admin_product_form import minimal_product_create_form

#: The params a stored "image" declaration carries. Concrete values, so an announcement that
#: substituted defaults for what the seller stored is visible rather than plausible.
_STORED_IMAGE_PARAMS: dict[str, Any] = {"width": 300, "height": 250}


def _store_product(
    ctx: dict,
    format_options: list[dict[str, Any]] | None,
    *,
    with_legacy_arm: bool = True,
    legacy_ids: list[str] | None = None,
) -> None:
    """Persist one product carrying *format_options*, with a pricing option so it announces.

    The pricing option is NOT incidental scaffolding. A product with none cannot be
    converted at all -- the conversion refuses it, and get_products answers INTERNAL_ERROR --
    so without one the refusal scenarios below would pass on the missing pricing option
    rather than on the malformed declaration they name, and the success scenarios would fail
    for a reason they say nothing about. Measured: that is exactly what happened before this
    line existed.

    ``with_legacy_arm=False`` stores a CANONICAL-ONLY product -- ``format_ids`` NULL, which
    migration 08cd415b3d91 made representable.

    ``legacy_ids`` names the ids the stored legacy column carries, for the scenarios whose
    subject is that column naming something the declarations do not assert. It defaults to
    the factory's arm, which is what every other scenario here wants; each caller takes the
    ids from its scenario's own text.
    """
    overrides: dict[str, Any] = {"format_options": format_options}
    if not with_legacy_arm:
        overrides["format_ids"] = None
    elif legacy_ids is not None:
        overrides["format_ids"] = [_ref(legacy_id) for legacy_id in legacy_ids]
    product = ProductFactory(tenant=ctx["tenant"], **overrides)
    PricingOptionFactory(product=product)
    ctx["product"] = product


def _ids(listed: str) -> list[str]:
    """The comma-separated format ids a scenario names, in order."""
    return [format_id.strip() for format_id in listed.split(",") if format_id.strip()]


def _ref(format_id: str) -> dict[str, str]:
    """A v1 format reference in the canonical creative agent's namespace."""
    return {"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": format_id}


def _image_declaration(*asserted_ids: str) -> dict[str, Any]:
    """An "image" declaration with the stored params, asserting *asserted_ids* as v1 refs."""
    declaration: dict[str, Any] = {"format_kind": "image", "params": dict(_STORED_IMAGE_PARAMS)}
    if asserted_ids:
        declaration["v1_format_ref"] = [_ref(format_id) for format_id in asserted_ids]
    return declaration


def _sized_image_option(option_id: str, width: int, height: int, *asserted_ids: str) -> dict[str, Any]:
    """A product-local "image" declaration with its own option id and size."""
    declaration: dict[str, Any] = {
        "format_kind": "image",
        "format_option_id": option_id,
        "params": {"width": width, "height": height},
    }
    if asserted_ids:
        declaration["v1_format_ref"] = [_ref(format_id) for format_id in asserted_ids]
    return declaration


#: The declarations of the several-options scenario. Three product-local options, each with
#: its own ``format_option_id`` and size, so no two are interchangeable on the wire. Two
#: assert a v1 reference and the third asserts none, so the derived ``format_ids`` must take
#: refs from more than one declaration and must skip the one that asserts nothing.
_SEVERAL_DECLARATIONS: tuple[dict[str, Any], ...] = (
    _sized_image_option("mrec", 300, 250, "display_300x250_image"),
    _sized_image_option("leaderboard", 728, 90, "display_728x90_image"),
    _sized_image_option("skyscraper", 160, 600),
)


def _lost_params(stored: dict[str, Any], announced: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """The stored params that came back changed or absent, as ``{name: (stored, announced)}``.

    A SUBSET check, because the model fills a canonical shape's own defaults (slots,
    asset_source, ...) in alongside what the seller stored. What is graded is that the
    seller's values survived, not that nothing was added.
    """
    return {name: (value, announced.get(name)) for name, value in stored.items() if announced.get(name) != value}


def _announced_product(ctx: dict) -> dict[str, Any]:
    """The one product exactly as the buyer received it."""
    return wire_entry(ctx, "products", index=0)


def _the_announced_option(ctx: dict) -> dict[str, Any]:
    """The single announced declaration, refusing to pick one when there are several."""
    product = _announced_product(ctx)
    options = product.get("format_options")
    assert options, f"product carries no format_options on the wire: {sorted(product)}"
    assert len(options) == 1, f"expected exactly one format option, got {len(options)}: {options!r}"
    return options[0]


# ── Given steps ─────────────────────────────────────────────────────


@given(
    parsers.parse(
        'the seller stores a canonical format option for "{format_kind}" with a v1_format_ref to "{legacy_id}"'
    )
)
def given_declaration_with_v1_ref(ctx: dict, format_kind: str, legacy_id: str) -> None:
    """Store one declaration that asserts its own legacy projection.

    The seller ASSERTS the v1 reference rather than the seller deriving it: the projection
    runs v1 -> v2 only, so there is no legal way to compute this from the canonical kind.
    """
    _store_product(
        ctx,
        [{**_image_declaration(legacy_id), "format_kind": format_kind}],
    )


@given(
    parsers.parse(
        'the seller stores a canonically-authored product for "{format_kind}" asserting a '
        'v1_format_ref to "{legacy_id}"'
    )
)
def given_canonical_only_product_with_ref(ctx: dict, format_kind: str, legacy_id: str) -> None:
    """Store a product whose ONLY authored arm is canonical, and which asserts a v1 link.

    With no stored legacy column, any ``format_ids`` the buyer receives can only have been
    derived from the declaration.
    """
    _store_product(
        ctx,
        [{**_image_declaration(legacy_id), "format_kind": format_kind}],
        with_legacy_arm=False,
    )


@given(
    parsers.parse(
        "the seller stores a canonically-authored product linked to an inventory profile whose "
        'format_ids names "{profile_id}", asserting a v1_format_ref to "{asserted_id}"'
    )
)
def given_profile_linked_canonical_product(ctx: dict, profile_id: str, asserted_id: str) -> None:
    """A canonically-authored product linked to a profile that carries only a legacy catalog.

    The two ids differ by construction and both come from the scenario, so a seller that
    served the profile's arm beside the product's declarations cannot pass by agreement.

    ``inventory_profile_id`` is the profile's INTEGER primary key, not its string business key
    ``profile_id`` -- ``products.inventory_profile_id`` FKs ``inventory_profiles.id``.
    """
    profile = InventoryProfileFactory(tenant=ctx["tenant"], format_ids=[_ref(profile_id)])
    product = ProductFactory(
        tenant=ctx["tenant"],
        inventory_profile_id=profile.id,
        format_ids=None,
        format_options=[_image_declaration(asserted_id)],
    )
    PricingOptionFactory(product=product)
    ctx["product"] = product


@given(
    parsers.parse(
        "the seller stores a product linked to an inventory profile whose canonical declaration "
        'asserts a v1_format_ref to "{asserted_id}"'
    )
)
def given_product_linked_to_canonical_profile(ctx: dict, asserted_id: str) -> None:
    """A profile that carries canonical declarations, linked to a product with its own arms.

    The PRODUCT keeps the factory's legacy column and gets a declaration of its own, both
    naming the factory's 300x250 format, and the PROFILE carries no legacy arm. Every value
    the buyer could be announced from the product therefore differs from the profile's
    asserted ref, which comes from the scenario.
    """
    profile = InventoryProfileFactory(
        tenant=ctx["tenant"], format_ids=None, format_options=[_image_declaration(asserted_id)]
    )
    product = ProductFactory(
        tenant=ctx["tenant"],
        inventory_profile_id=profile.id,
        format_options=[_image_declaration("display_300x250_image")],
    )
    PricingOptionFactory(product=product)
    ctx["product"] = product


@given("the seller stores a dual-authored product whose declaration is a custom format with no format_shape")
def given_custom_declaration_without_format_shape(ctx: dict) -> None:
    """Store the declaration that took a tenant's whole catalogue down (salesagent-1d5z4).

    Legal where it matters and illegal where it used to be read: the pinned
    ``ProductFormatDeclaration`` union the DTO declares accepts
    ``{format_kind: "custom", params: {...}}``, and ``adcp.types.canonical_creative.Format``
    refuses it ("custom formats require format_shape").

    DUAL-authored, by keeping the factory's legacy column, so the read path has a stored
    arm it must not fall back to. Spelled as its own Given with no parameters, because every
    part of it is the subject.
    """
    _store_product(ctx, [{"format_kind": "custom", "params": dict(_STORED_IMAGE_PARAMS)}])


@given(
    parsers.parse(
        'the seller stores a dual-authored product whose format_ids names "{authored_ids}" and '
        "whose declaration asserts no v1_format_ref"
    )
)
def given_dual_authored_product_asserting_no_ref(ctx: dict, authored_ids: str) -> None:
    """A stored legacy column beside a declaration that asserts no v1 projection."""
    _store_product(ctx, [_image_declaration()], legacy_ids=_ids(authored_ids))


@given(
    parsers.parse(
        'the seller stores a dual-authored product whose format_ids names "{authored_ids}" and '
        'whose declaration asserts "{asserted_id}"'
    )
)
def given_dual_authored_product(ctx: dict, authored_ids: str, asserted_id: str) -> None:
    """A stored legacy column beside a declaration asserting a ref the column may not match.

    Both sides come from the scenario, so the fixture cannot drift into agreement by
    inheriting a factory default on one side. The declaration's params are the same
    300x250 every other scenario here stores.
    """
    _store_product(ctx, [_image_declaration(asserted_id)], legacy_ids=_ids(authored_ids))


@given(parsers.parse('the seller stores a canonically-authored product for "{format_kind}" with no format_ids'))
def given_canonical_only_product(ctx: dict, format_kind: str) -> None:
    """Store a product whose ONLY format declaration is canonical.

    The mirror of ``given_product_without_declarations`` below, and the shape the 3.2 spec
    tells new products to author: core/product.json's root anyOf has a "Canonical-format
    product" branch, and ``format_ids`` is "Deprecated in AdCP 3.2; removed in AdCP 4.0"
    and absent from the schema's root ``required``. Until migration 08cd415b3d91 the
    column's NOT NULL made this unrepresentable.
    """
    _store_product(
        ctx,
        [{"format_kind": format_kind, "params": dict(_STORED_IMAGE_PARAMS)}],
        with_legacy_arm=False,
    )


@given("the seller stores a canonically-authored product declaring three format options")
def given_canonical_product_with_several_options(ctx: dict) -> None:
    """Store a canonical-only product whose contract is three declarations, not one."""
    _store_product(ctx, [dict(declaration) for declaration in _SEVERAL_DECLARATIONS], with_legacy_arm=False)


@given(
    parsers.parse(
        'the operator creates a product through the admin product form declaring a canonical "{format_kind}" '
        "format option"
    )
)
def given_operator_authored_product(ctx: dict, format_kind: str) -> None:
    """The seller's own authoring path writes the product, not a factory.

    Every other Given here stores the row through ``ProductFactory``, so none of them can
    say where the seller's authoring puts a product's creative contract. This one posts
    the admin create form on the env's own transport (in process, or to the live server
    over e2e_rest), which is the path an operator uses. The form carries only what the
    operator chooses: a name, a price, a property tag, and the canonical declaration.

    The property tag and the authorized property carrying it are factory rows because they
    are the form's precondition, not its subject: the handler refuses a tag no authorized
    property of that publisher carries. The status is asserted here, because the handler
    answers a refused form by re-rendering it with 200, and a scenario whose product was
    never created would then read an empty catalogue in its Then.
    """
    tenant = ctx["tenant"]
    form = minimal_product_create_form(
        seed_property_tag_selection(tenant, ctx["env"]),
        product_id="operator_authored",
        format_options=json.dumps([{"format_kind": format_kind, "params": dict(_STORED_IMAGE_PARAMS)}]),
    )
    response = ctx["env"].admin_request(tenant.tenant_id, "post", "products/add", data=form)
    assert response.status_code == 302, (
        f"the admin product form did not create the product (status {response.status_code}); "
        "a refused form re-renders with 200"
    )


@given("the seller stores a product with no canonical format options")
def given_product_without_declarations(ctx: dict) -> None:
    """Store a product carrying only the deprecated half, which the pin's anyOf permits."""
    _store_product(ctx, None)


@given("the seller stores a product declaring neither format arm")
def given_product_with_no_format_arm(ctx: dict) -> None:
    """Store the one state core/product.json's root anyOf forbids: both halves absent.

    The CONJUNCTION of the two Givens either side of it, each of which stores a product the
    pin permits. It is reachable rather than hypothetical: both columns are nullable after
    migration 08cd415b3d91 and neither CHECK constraint rejects NULL, while the admin
    refuses to AUTHOR the shape (``_refuse_a_product_with_no_format_arm``), so this grades
    the READ path against a row that arrived some other way -- which is the case
    ``src/core/tools/products.py`` calls "data corruption or migration issue".
    """
    _store_product(ctx, None, with_legacy_arm=False)


@given(parsers.parse("the seller stores a canonical format option with no {missing_member}"))
def given_declaration_missing_required_member(ctx: dict, missing_member: str) -> None:
    """Store a declaration missing a member ``required`` names, which no DB constraint covers.

    Built by REMOVING the member from a complete declaration rather than by assembling a
    partial one, so the fixture cannot drift into omitting something the scenario did not
    ask about and passing for the wrong reason.
    """
    complete: dict[str, Any] = {"format_kind": "image", "params": dict(_STORED_IMAGE_PARAMS)}
    assert missing_member in complete, (
        f"the scenario names a member a complete declaration does not carry: {missing_member!r}; "
        f"carries {sorted(complete)}"
    )
    del complete[missing_member]
    _store_product(ctx, [complete])


# ── Then steps ──────────────────────────────────────────────────────


@then(parsers.parse('the announced format option declares format_kind "{format_kind}" and params the seller stored'))
def then_declaration_announced(ctx: dict, format_kind: str) -> None:
    """The two members the pin marks required arrive, carrying what the seller stored."""
    option = _the_announced_option(ctx)
    assert option.get("format_kind") == format_kind, (
        f"expected format_kind {format_kind!r} on the wire, got {option.get('format_kind')!r}"
    )
    params = option.get("params")
    assert params is not None, f"the announced declaration carries no params: {sorted(option)}"
    lost = _lost_params(_STORED_IMAGE_PARAMS, params)
    assert not lost, f"params the seller stored came back changed or absent (expected, got): {lost}"


@then("the announced format options are exactly the three declarations the seller stored")
def then_every_stored_declaration_announced(ctx: dict) -> None:
    """Every stored declaration arrives, by its option id, carrying what the seller stored.

    Keyed on ``format_option_id`` rather than on position: core/product.json gives
    ``format_options`` no order, and the id is what a buyer names in
    ``format_option_refs`` and ``packages[].format_option_refs``, so an option that arrived
    without it could not be selected. The count is asserted first, so a dropped option and
    an extra one both fail before the per-option comparison.
    """
    options = _announced_product(ctx).get("format_options")
    assert options, "the product announced no format_options at all"
    assert len(options) == len(_SEVERAL_DECLARATIONS), (
        f"expected {len(_SEVERAL_DECLARATIONS)} announced format options, got {len(options)}: {options!r}"
    )
    announced = {option.get("format_option_id"): option for option in options}
    expected = {declaration["format_option_id"]: declaration for declaration in _SEVERAL_DECLARATIONS}
    assert set(announced) == set(expected), (
        f"the announced format_option_ids are {sorted(map(str, announced))}, expected {sorted(expected)}"
    )
    for option_id, declaration in expected.items():
        option = announced[option_id]
        assert option.get("format_kind") == declaration["format_kind"], (
            f"option {option_id!r} announced format_kind {option.get('format_kind')!r}, "
            f"stored {declaration['format_kind']!r}"
        )
        lost = _lost_params(declaration["params"], option.get("params") or {})
        assert not lost, f"option {option_id!r} lost stored params (expected, got): {lost}"
        assert option.get("v1_format_ref") == declaration.get("v1_format_ref"), (
            f"option {option_id!r} announced v1_format_ref {option.get('v1_format_ref')!r}, "
            f"stored {declaration.get('v1_format_ref')!r}"
        )


@then(parsers.parse('the announced format option carries v1_format_ref naming "{legacy_id}"'))
def then_v1_format_ref_announced(ctx: dict, legacy_id: str) -> None:
    """The asserted legacy projection reaches the buyer, whole.

    Graded as the full reference rather than the id alone: a v1 format_id is an OBJECT
    (core/format-id.json requires agent_url and id), and a projection carrying only the id
    names a format in nobody's namespace.
    """
    option = _the_announced_option(ctx)
    refs = option.get("v1_format_ref")
    assert refs, (
        "the announced declaration carries no v1_format_ref, so a legacy peer would have "
        f"nothing to look up: {sorted(option)}"
    )
    assert refs == [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": legacy_id}], (
        f"the announced v1_format_ref is not the reference the seller asserted: {refs!r}"
    )


@then("the announced product carries no format_options key at all")
def then_no_format_options_key(ctx: dict) -> None:
    """Absent, not null: "declared and empty" is a different claim from "not declared"."""
    product = _announced_product(ctx)
    assert "format_options" not in product, (
        "a product declaring no canonical format options announced the key anyway, as "
        f"{product.get('format_options')!r}"
    )


@then("the announced product carries no format_ids key at all")
def then_no_format_ids_key(ctx: dict) -> None:
    """Absent, not empty -- and the distinction is the whole obligation.

    ``core/product.json``'s deprecated anyOf branch requires only the KEY, so
    ``format_ids: []`` would satisfy that branch by presence while declaring no format at
    all. An absent key is the only shape that says "this product has no legacy arm".
    """
    product = _announced_product(ctx)
    assert "format_ids" not in product, (
        "a canonically-authored product announced the deprecated key anyway, as "
        f"{product.get('format_ids')!r}; an empty array satisfies the deprecated anyOf "
        "branch by presence while declaring nothing"
    )


@then(parsers.parse('the announced product\'s format_ids name exactly "{format_ids}"'))
def then_format_ids_exactly(ctx: dict, format_ids: str) -> None:
    """The legacy arm on the wire, entry by entry, in order.

    Compared as whole references rather than ids: a v1 format_id is an OBJECT
    (core/format-id.json requires agent_url and id), and an arm that kept the ids but lost
    the namespace would name formats in nobody's catalog. Exact, so an extra entry (a stored
    column served beside the derived refs) fails as surely as a missing one.
    """
    product = _announced_product(ctx)
    announced = product.get("format_ids")
    expected = [_ref(format_id) for format_id in _ids(format_ids)]
    assert announced == expected, f"the announced format_ids are not exactly {expected!r}: {announced!r}"


@then("the response carries no format-declaration advisory")
def then_no_format_advisory(ctx: dict) -> None:
    """Nothing on the advisory channel about this product's format declarations.

    A canonical product's legacy arm is derived from its declarations, so the two arms
    cannot disagree on the reference and no ``FORMAT_DECLARATION_DIVERGENT`` is owed. An
    advisory here would report a disagreement the buyer was never shown.

    Scoped to the format-declaration codes rather than asserting an empty ``errors[]``: the
    array is get_products' task-level channel and another obligation is free to use it, so
    a blanket emptiness assertion would couple this scenario to every future advisory.
    """
    advised = [error for error in wire_advisory_errors(ctx) if str(error.get("code", "")).startswith("FORMAT_")]
    assert not advised, f"the response advises about format declarations it derived itself: {advised!r}"

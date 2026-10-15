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

from typing import Any

from pytest_bdd import given, parsers, then

from tests.bdd.steps._outcome_helpers import wire_advisory_errors, wire_entry
from tests.factories import PricingOptionFactory, ProductFactory
from tests.factories.creative import DEFAULT_CREATIVE_AGENT_URL

#: The params a stored "image" declaration carries. Concrete values, so an announcement that
#: substituted defaults for what the seller stored is visible rather than plausible.
_STORED_IMAGE_PARAMS: dict[str, Any] = {"width": 300, "height": 250}


def _store_product(
    ctx: dict,
    format_options: list[dict[str, Any]] | None,
    *,
    with_legacy_arm: bool = True,
    legacy_id: str | None = None,
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

    ``legacy_id`` names the id the legacy arm carries, for the one scenario whose whole
    subject is the two arms naming DIFFERENT formats. It defaults to the factory's arm,
    which is what every other scenario here wants. It used to not exist, on the ground that
    "the only two shapes any scenario here wants are both arms and canonical only"; the
    divergence scenario is a third, and it NAMES the value in its own text, so the risk that
    comment guarded against -- a caller passing some legacy value no scenario names -- is
    not the shape it takes.
    """
    overrides: dict[str, Any] = {"format_options": format_options}
    if not with_legacy_arm:
        overrides["format_ids"] = None
    elif legacy_id is not None:
        overrides["format_ids"] = [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": legacy_id}]
    product = ProductFactory(tenant=ctx["tenant"], **overrides)
    PricingOptionFactory(product=product)
    ctx["product"] = product


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
        [
            {
                "format_kind": format_kind,
                "params": dict(_STORED_IMAGE_PARAMS),
                "v1_format_ref": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": legacy_id}],
            }
        ],
    )


@given(
    parsers.parse(
        'the seller stores a canonically-authored product for "{format_kind}" asserting a '
        'v1_format_ref to "{legacy_id}"'
    )
)
def given_canonical_only_product_with_ref(ctx: dict, format_kind: str, legacy_id: str) -> None:
    """Store a product whose ONLY authored arm is canonical, and which asserts a v1 link.

    The shape a PROJECTING seller would dual-emit, which is why it is worth storing under a
    seller that declines to: it is the only fixture where announcing a legacy arm would be
    permitted (core/product.json's "sellers MAY additionally project"), so it is the only
    one whose empty arm distinguishes a decision from an accident. Its two siblings are the
    canonical-only product that asserts nothing (where there is nothing to project in the
    first place) and the dual-authored product (which has an authored arm already), so this
    is spelled as its own Given rather than as a parameter on either.
    """
    _store_product(
        ctx,
        [
            {
                "format_kind": format_kind,
                "params": dict(_STORED_IMAGE_PARAMS),
                "v1_format_ref": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": legacy_id}],
            }
        ],
        with_legacy_arm=False,
    )


@given("the seller stores a dual-authored product whose declaration is a custom format with no format_shape")
def given_declaration_the_divergence_check_cannot_read(ctx: dict) -> None:
    """Store the declaration that took a tenant's whole catalogue down (salesagent-1d5z4).

    Legal where it matters and illegal where it used to be read: the pinned
    ``ProductFormatDeclaration`` union the DTO declares accepts
    ``{format_kind: "custom", params: {...}}``, and ``adcp.types.canonical_creative.Format``
    refuses it ("custom formats require format_shape"). The divergence check validated into
    the latter, so the conversion raised and ``get_products`` answered INTERNAL_ERROR for
    every product of the tenant.

    DUAL-authored, by keeping the factory's legacy arm. That is the whole point of this
    fixture over the sibling that caught the outage: a canonical-only product never reaches
    the comparison, because "no authored arm" short-circuits above it.

    Spelled as its own Given with no parameters, because every part of it is the subject --
    the kind, the missing member, and the presence of the other arm. A parameterized version
    would let a caller store a shape that grades something this scenario does not name.
    """
    _store_product(ctx, [{"format_kind": "custom", "params": dict(_STORED_IMAGE_PARAMS)}])


@given(
    parsers.parse(
        'the seller stores a dual-authored product whose format_ids names "{authored_id}" and '
        'whose declaration asserts "{asserted_id}"'
    )
)
def given_divergent_dual_authored_product(ctx: dict, authored_id: str, asserted_id: str) -> None:
    """Store the producer bug: both arms authored, and each naming a different v1 format.

    Both ids come from the scenario, so the fixture cannot drift into agreement by
    inheriting a factory default on one side -- which is exactly how the sibling scenario
    above came to be divergent without saying so. The declaration's params are the same
    300x250 every other scenario here stores: the divergence under test is the REFERENCE,
    and the pin's other axis (params failing to narrow the referenced v1 format) is not
    detectable without fetching that format.
    """
    _store_product(
        ctx,
        [
            {
                "format_kind": "image",
                "params": dict(_STORED_IMAGE_PARAMS),
                "v1_format_ref": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": asserted_id}],
            }
        ],
        legacy_id=authored_id,
    )


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


@given("the seller stores a product with no canonical format options")
def given_product_without_declarations(ctx: dict) -> None:
    """Store a product carrying only the deprecated half, which the pin's anyOf permits."""
    _store_product(ctx, None)


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
    # A SUBSET check, because the model fills a canonical shape's own defaults (slots,
    # asset_source, ...) in alongside what the seller stored. What is graded is that the
    # seller's values survived, not that nothing was added.
    lost = {
        name: (value, params.get(name)) for name, value in _STORED_IMAGE_PARAMS.items() if params.get(name) != value
    }
    assert not lost, f"params the seller stored came back changed or absent (expected, got): {lost}"


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


@then("the announced product still carries its format_ids")
def then_format_ids_still_announced(ctx: dict) -> None:
    """The deprecated half is what satisfies the pin's anyOf for this product."""
    product = _announced_product(ctx)
    format_ids = product.get("format_ids")
    assert format_ids, (
        "the product announced neither half of its format declaration, so it describes no "
        f"format at all: {sorted(product)}"
    )


@then("the response carries no format-declaration advisory")
def then_no_format_advisory(ctx: dict) -> None:
    """Nothing on the advisory channel about this product's format declarations.

    The negative half of the divergence instrument. Without it an implementation that
    advised on EVERY product carrying both arms would satisfy the divergent scenario, and
    the advisory would be noise rather than a finding.

    Scoped to the format-declaration codes rather than asserting an empty ``errors[]``: the
    array is get_products' task-level channel and another obligation is free to use it, so
    a blanket emptiness assertion would couple this scenario to every future advisory.
    """
    advised = [error for error in wire_advisory_errors(ctx) if str(error.get("code", "")).startswith("FORMAT_")]
    assert not advised, f"the response advises about format declarations when the two arms agree: {advised!r}"


@then(
    parsers.parse('the response carries one FORMAT_DECLARATION_DIVERGENT advisory from the producer naming "{field}"')
)
def then_divergence_advised(ctx: dict, field: str) -> None:
    """The advisory, on a SUCCESS, attributed to the producer, pointing at the product.

    Three obligations in one assertion because the pin states them together for this code:
    ``errors[]`` is the single mandated surface ("Logger-only is insufficient"),
    ``error.field`` MUST point at the offending product, and the storyboard's
    ``get_seeded_divergent_product`` grades ``errors[0].source == "producer"`` -- the seller
    self-detected on emit, so attributing it to an SDK would name the wrong party.

    ``recovery`` is asserted too, and it is NOT authored anywhere: it is derived from the
    pinned ``enumMetadata``, which puts this code at ``correctable``. Reading it back is
    what shows the advisory went through the code table rather than being hand-assembled.

    Exactly one entry, because the pin's multi-hop rule deduplicates by ``(code, field)``
    and a product announced once cannot honestly be advised about twice.
    """
    advised = [error for error in wire_advisory_errors(ctx) if error.get("code") == "FORMAT_DECLARATION_DIVERGENT"]
    assert len(advised) == 1, (
        f"expected exactly one FORMAT_DECLARATION_DIVERGENT advisory, got {len(advised)}: {wire_advisory_errors(ctx)!r}"
    )
    advisory = advised[0]
    assert advisory.get("source") == "producer", (
        f"the advisory is not attributed to the producer that emitted it: {advisory.get('source')!r}"
    )
    assert advisory.get("field") == field, (
        f"the advisory does not point at the offending product: {advisory.get('field')!r}"
    )
    assert advisory.get("recovery") == "correctable", (
        f"the advisory's recovery is not the pinned enumMetadata's: {advisory.get('recovery')!r}"
    )
    ctx["format_divergence_advisory"] = advisory


@then(parsers.parse('the advisory details name the authored "{authored_id}" and the asserted "{asserted_id}"'))
def then_divergence_details(ctx: dict, authored_id: str, asserted_id: str) -> None:
    """The four keys the pin asks of this code's ``details``, carrying BOTH disagreeing arms.

    Graded because an advisory that said only "this product diverges" would leave the
    operator to go and diff the two arms themselves, which is what
    ``error.details`` SHOULD carry ``{product_id, format_ids, format_options_summary,
    divergence_reason}`` exists to prevent ("so buyer SDKs can flag the producer for
    follow-up").

    Each id is asserted to be in the arm that NAMES it and not in the other. A details
    block that reported the same arm twice would carry both ids and pass a membership check
    that did not say which side each came from -- and reporting the asserted ref as though
    the product had authored it is the specific confusion this advisory exists to clear up.
    """
    advisory = ctx["format_divergence_advisory"]
    details = advisory.get("details")
    assert isinstance(details, dict), f"the advisory carries no details object: {details!r}"
    assert details.get("product_id") == ctx["product"].product_id, (
        f"the details name a different product than the one stored: {details.get('product_id')!r}"
    )
    assert details.get("divergence_reason") == "v1_format_ref_absent_from_format_ids", (
        f"the details do not classify the divergence: {details.get('divergence_reason')!r}"
    )

    authored_arm = details.get("format_ids")
    assert authored_arm == [f"{DEFAULT_CREATIVE_AGENT_URL}/{authored_id}"], (
        f"the details do not report the legacy arm the product authored: {authored_arm!r}"
    )

    summary = details.get("format_options_summary")
    assert summary == [{"format_kind": "image", "v1_format_ref": [f"{DEFAULT_CREATIVE_AGENT_URL}/{asserted_id}"]}], (
        f"the details do not report what the canonical arm asserts: {summary!r}"
    )

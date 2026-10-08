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

from tests.bdd.steps._outcome_helpers import wire_entry
from tests.factories import PricingOptionFactory, ProductFactory
from tests.factories.creative import DEFAULT_CREATIVE_AGENT_URL

#: The params a stored "image" declaration carries. Concrete values, so an announcement that
#: substituted defaults for what the seller stored is visible rather than plausible.
_STORED_IMAGE_PARAMS: dict[str, Any] = {"width": 300, "height": 250}


def _store_product(ctx: dict, format_options: list[dict[str, Any]] | None) -> None:
    """Persist one product carrying *format_options*, with a pricing option so it announces.

    The pricing option is NOT incidental scaffolding. A product with none cannot be
    converted at all -- the conversion refuses it, and get_products answers INTERNAL_ERROR --
    so without one the refusal scenarios below would pass on the missing pricing option
    rather than on the malformed declaration they name, and the success scenarios would fail
    for a reason they say nothing about. Measured: that is exactly what happened before this
    line existed.
    """
    product = ProductFactory(tenant=ctx["tenant"], format_options=format_options)
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


@then("the announced product still carries its format_ids")
def then_format_ids_still_announced(ctx: dict) -> None:
    """The deprecated half is what satisfies the pin's anyOf for this product."""
    product = _announced_product(ctx)
    format_ids = product.get("format_ids")
    assert format_ids, (
        "the product announced neither half of its format declaration, so it describes no "
        f"format at all: {sorted(product)}"
    )

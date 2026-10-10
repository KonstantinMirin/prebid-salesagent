"""Steps for BR-UC-GET-PRODUCTS-canonical-format-filters: which products the canonical
format filters select.

Built exactly like ``uc_get_products_format_id_filter``, its legacy-arm sibling: setup
stores REAL ``products`` rows through ``ProductFactory`` -- including one the filter must
NOT select -- dispatch goes through the shared wire dispatcher, and the outcome reads
``wire_field`` rather than the typed payload, because the typed payload has already
coerced every field to its declared type.

Each scenario's catalogue holds a counter-example, so the expected set is never derived
from the seeded data. A filter test whose every product the filter selects passes with
the filter deleted.
"""

from __future__ import annotations

from typing import Any

from pytest_bdd import given, then, when

from tests.bdd.steps._outcome_helpers import wire_field
from tests.bdd.steps.generic._dispatch import dispatch_request
from tests.factories import PricingOptionFactory, ProductFactory

#: The kind the filter names, and the kind it must not select. Both are members of the
#: pinned sixteen-kind vocabulary, so neither product is dropped for declaring something
#: unparseable rather than for the filter's decision.
_NAMED_KIND = "image"
_OTHER_KIND = "video_hosted"

#: The one member of that vocabulary that names a format OUTSIDE the IAB standard set,
#: which is what ``standard_formats_only`` has to exclude. Written from the member list
#: rather than invented: there is no ``video`` member, so a set like {"image", "video"}
#: would raise rather than filter.
_CUSTOM_KIND = "custom"

#: Params for a declaration. Concrete, so a product dropped for an unparseable declaration
#: is distinguishable from one the filter excluded.
_PARAMS: dict[str, Any] = {"width": 300, "height": 250}


def _canonical_product_declaring(tenant: Any, format_kind: str) -> Any:
    """Persist one CANONICAL-ONLY product declaring *format_kind*, and return it.

    ``format_ids=None`` so the product carries no legacy arm at all -- which is the shape
    migration 08cd415b3d91 made representable, and the shape that makes these scenarios
    grade the canonical filters rather than the legacy one. A dual-authored product would
    let the legacy ``format_ids`` filter answer the same question and the scenario could
    not tell which arm decided.

    The pricing option is NOT incidental scaffolding, for the same measured reason its two
    siblings carry one: a product with none cannot be converted at all, so without it the
    scenario would grade the missing pricing option rather than the filter.

    Takes the TENANT and returns the row rather than taking ``ctx`` and a key to store
    under. A ``ctx``-first helper that subscripts ``ctx`` with one of its own parameters is
    the shape ``test_architecture_bdd_ctx_keys`` tracks BY FUNCTION NAME across every step
    module, so writing one here would change how that guard reads same-named helpers
    elsewhere -- which it has already done once, to this feature's siblings.
    """
    product = ProductFactory(
        tenant=tenant,
        format_ids=None,
        format_options=[{"format_kind": format_kind, "params": dict(_PARAMS)}],
    )
    PricingOptionFactory(product=product)
    return product


# ── Given steps ─────────────────────────────────────────────────────


@given("the seller stores two canonical products declaring different format kinds")
def given_two_canonical_products_with_different_kinds(ctx: dict) -> None:
    """Store the product the filter names and the counter-example it must not select."""
    assert _NAMED_KIND != _OTHER_KIND, (
        "the two products declare one kind, so no filter can tell them apart and this scenario grades nothing"
    )
    tenant = ctx["tenant"]
    ctx["named_product"] = _canonical_product_declaring(tenant, _NAMED_KIND)
    ctx["other_product"] = _canonical_product_declaring(tenant, _OTHER_KIND)


@given("the seller stores two canonical products, one declaring a custom format kind")
def given_two_canonical_products_one_custom(ctx: dict) -> None:
    """Store a standard-kind product and the custom-kind counter-example."""
    tenant = ctx["tenant"]
    ctx["named_product"] = _canonical_product_declaring(tenant, _NAMED_KIND)
    ctx["other_product"] = _canonical_product_declaring(tenant, _CUSTOM_KIND)


# ── When steps ──────────────────────────────────────────────────────


@when("the buyer requests products filtering format_kinds by the first product's kind only")
def when_request_products_filtered_by_format_kind(ctx: dict) -> None:
    """Dispatch get_products naming ONE canonical kind.

    The filter's items are canonical-format-kind values, so the request carries the kind
    itself rather than a reference object -- unlike the legacy ``format_ids`` filter, whose
    items are ``core/format-id.json`` references.
    """
    dispatch_request(ctx, brief="format_kinds filter test", filters={"format_kinds": [_NAMED_KIND]})


@when("the buyer requests products with standard_formats_only")
def when_request_products_standard_only(ctx: dict) -> None:
    """Dispatch get_products asking for IAB standard formats only."""
    dispatch_request(ctx, brief="standard_formats_only filter test", filters={"standard_formats_only": True})


# ── Then steps ──────────────────────────────────────────────────────


def _announced_product_ids(ctx: dict) -> set[str]:
    """The product_ids the buyer received, off the wire."""
    products: list[dict[str, Any]] = wire_field(ctx, "products")
    return {product["product_id"] for product in products}


def _assert_exactly_the_named_product(ctx: dict, *, filter_name: str) -> None:
    """An EXACT set, which is what separates a working filter from its two failure modes.

    Containment in either direction passes for one of them: ``>=`` passes on an IGNORED
    filter that returned both products, and ``<=`` passes on a filter that matched nothing
    and returned neither.
    """
    announced = _announced_product_ids(ctx)
    expected = {ctx["named_product"].product_id}
    assert announced == expected, (
        f"the {filter_name} filter did not select exactly the product it named: "
        f"expected {sorted(expected)}, got {sorted(announced)}"
    )


def _assert_counter_example_excluded(ctx: dict, *, what: str) -> None:
    """Named as its own outcome because it is the false positive the filter exists to stop."""
    announced = _announced_product_ids(ctx)
    excluded = ctx["other_product"].product_id
    assert excluded not in announced, (
        f"the buyer received the product declaring {what}, which it asked to exclude: {sorted(announced)}"
    )


@then("the announced products are exactly the product declaring the named kind")
def then_only_named_kind_product_announced(ctx: dict) -> None:
    _assert_exactly_the_named_product(ctx, filter_name="format_kinds")


@then("the announced products do not include the product declaring the other kind")
def then_other_kind_product_excluded(ctx: dict) -> None:
    _assert_counter_example_excluded(ctx, what=f"the other kind ({_OTHER_KIND})")


@then("the announced products are exactly the product declaring the standard kind")
def then_only_standard_product_announced(ctx: dict) -> None:
    _assert_exactly_the_named_product(ctx, filter_name="standard_formats_only")


@then("the announced products do not include the product declaring the custom kind")
def then_custom_kind_product_excluded(ctx: dict) -> None:
    _assert_counter_example_excluded(ctx, what=f"a custom format kind ({_CUSTOM_KIND})")

"""Steps for BR-UC-GET-PRODUCTS-publisher-domain: which publishers a product names (#1845).

Setup stores REAL ``AuthorizedProperty`` and ``Product`` rows through their factories, and
dispatch goes through the shared ``dispatch_request`` (via the inventory-profile module's
``When the buyer requests products``), so the same rows are read on every transport.

Assertions read the serialized wire body: ``publisher_properties`` is compared whole, so a
selector naming any other domain -- the seller's own agent host included -- fails it.
"""

from __future__ import annotations

import json

from pytest_bdd import given, parsers, then

from tests.bdd.steps._outcome_helpers import wire_entry, wire_field
from tests.factories import AuthorizedPropertyFactory, PricingOptionFactory, ProductFactory


def _split(cell: str) -> list[str]:
    """A comma-separated list from a step argument."""
    return [item.strip() for item in cell.split(",") if item.strip()]


def _offer(ctx: dict, product_id: str, property_tags: list[str]) -> None:
    """Store a priced product selecting its properties by the legacy ``property_tags`` column."""
    product = ProductFactory(tenant=ctx["tenant"], product_id=product_id, property_tags=property_tags)
    PricingOptionFactory(product=product)


# ── Given steps ─────────────────────────────────────────────────────


@given(parsers.parse('the seller is authorized for property "{property_id}" of publisher "{domain}" tagged "{tag}"'))
def given_authorized_property(ctx: dict, property_id: str, domain: str, tag: str) -> None:
    AuthorizedPropertyFactory(tenant=ctx["tenant"], property_id=property_id, publisher_domain=domain, tags=[tag])


@given(parsers.parse('the seller offers product "{product_id}" selecting property tags "{tags}"'))
def given_product_by_tags(ctx: dict, product_id: str, tags: str) -> None:
    _offer(ctx, product_id, property_tags=_split(tags))


@given(parsers.parse('the seller offers product "{product_id}" selecting no properties'))
def given_product_selecting_nothing(ctx: dict, product_id: str) -> None:
    # An empty tag list is how the admin form stores "nothing selected".
    _offer(ctx, product_id, property_tags=[])


# ── Then steps ──────────────────────────────────────────────────────


@then(parsers.parse('product "{product_id}" announces publisher_properties {expected}'))
def then_product_announces(ctx: dict, product_id: str, expected: str) -> None:
    announced = wire_entry(ctx, "products", product_id=product_id)["publisher_properties"]
    assert announced == json.loads(expected), f"product {product_id!r} announced {announced!r}"


@then(parsers.parse('the buyer receives exactly the products "{product_ids}"'))
def then_exact_products(ctx: dict, product_ids: str) -> None:
    received = sorted(product["product_id"] for product in wire_field(ctx, "products"))
    assert received == sorted(_split(product_ids)), f"received products {received!r}"

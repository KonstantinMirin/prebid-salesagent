"""get_products' wire response validates against the pinned get-products-response schema.

Regression for the ``Product.model_dump`` null-leak (#1868): nested optional fields that
are unset — ``format_ids[].width/height/duration_ms``, ``delivery_measurement.notes/
vendors``, ``pricing_options[].floor_price``, ``publisher_properties[].publisher_domains``
— were serialized as explicit nulls. The pinned AdCP schema types those properties and
none of them accepts null, so the emitted response was schema-invalid. The fix is the
``strip_none_deep`` pass in ``src/core/schemas/product.py``'s ``Product.model_dump``.

Assert on ``result.wire_response``, NEVER on ``result.payload``, for MCP/REST/A2A.
``GetProductsResponse.products`` is typed ``list[LibraryProduct]``, so the response the
harness re-parses off those three wires holds LIBRARY ``Product`` instances whose
``model_dump`` is the library's, not our override — asserting on ``.payload`` there would
silently stop exercising the fix. ``wire_response`` is the literal serialized body
captured from each transport (REST HTTP JSON body, MCP structured_content, A2A artifact
DataPart) and is the only correct source on a wire transport.

Validation targets the FULL enveloped response schema
(``media-buy/get-products-response.json``), whose ``products.items`` ``$ref``s
``core/product.json`` — a strict superset of validating each product on its own. All
three transports serialize through ``response.model_dump(mode="json")``
(``src/core/tools/products.py``, ``src/routes/api_v1.py``, ``_serialize_for_a2a``), so
each one genuinely grades ``Product.model_dump``; get_products has none of the
``to_jsonable_python`` structured_content bypass that afflicts sync_creatives.
"""

from __future__ import annotations

import pytest

from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
from tests.harness.assertions import assert_wire_omits_unset
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport
from tests.helpers import pinned_schema

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_RESPONSE_SCHEMA = "media-buy/get-products-response.json"


@pytest.fixture
def wire_schema_product_env(integration_db):
    """ProductEnv with one plain product whose nested optional fields are unset.

    The factory defaults omit exactly the fields the null-leak regressed on: format_ids
    entries carry only agent_url/id (no width/height/duration_ms), delivery_measurement
    carries only provider (no notes/vendors), and PricingOptionFactory sets a fixed rate
    with no floor_price. A product with those sub-fields populated would not exercise
    strip_none_deep at all.
    """
    with ProductEnv(tenant_id="wire-schema-test", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="wire-schema-test")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        product = ProductFactory(
            tenant=tenant,
            product_id="wire_schema_product",
            name="Wire Schema Product",
            description="Product whose nested optional fields are unset",
            delivery_type="guaranteed",
        )
        PricingOptionFactory(product=product, pricing_model="cpm", rate="15.00", is_fixed=True, currency="USD")
        env.set_policy_approved()
        env.set_ranking_disabled()
        yield env


@pytest.mark.parametrize("transport", [Transport.MCP, Transport.REST, Transport.A2A])
def test_get_products_wire_response_is_schema_valid(wire_schema_product_env, transport):
    """The literal wire body from each transport is schema-valid — no leaked nulls."""
    result = wire_schema_product_env.call_via(transport, brief="display ads")
    products = (result.wire_response or {}).get("products")
    assert isinstance(products, list) and products, (
        f"{transport}: expected a non-empty 'products' list in the response, got {products!r}"
    )

    assert_wire_omits_unset(result, schema=_RESPONSE_SCHEMA, absent_paths=[], transport=transport)


def test_get_products_impl_payload_is_schema_valid(wire_schema_product_env):
    """IMPL has no wire: this grades ``Product.model_dump`` directly, not a boundary.

    Kept because the null-leak lives in ``Product.model_dump`` itself, so a direct dump is
    the tightest failure signal. It is NOT a substitute for the three wire transports
    above and must never be the reason any of them is dropped.
    """
    result = wire_schema_product_env.call_via(Transport.IMPL, brief="display ads")
    assert result.is_success, f"IMPL get_products failed: {result.error}"

    response = result.payload.model_dump(mode="json")
    products = response.get("products")
    assert isinstance(products, list) and products, (
        f"IMPL: expected a non-empty 'products' list in the response, got {products!r}"
    )
    pinned_schema.validate_against_pinned_schema(_RESPONSE_SCHEMA, response)

"""An operator authors a product's CANONICAL format declarations through the product form.

Grades work item A4 (salesagent-ol033.2.1): before this, ``format_options`` had zero
references under ``src/admin/`` and ``templates/``, so the shape AdCP 3.2 tells new
products to author was storable, servable, and unauthorable.

WHY THIS IS AN ADMIN TEST AND NOT A BDD SCENARIO. The authoring surface is a Flask form.
The epic grades new behaviour through the four BDD transports, and none of them can reach
this: the registry declares fourteen tools and every one is buyer-facing -- there is no
``create_product`` or ``update_product``, because a product is seller-configured. The BDD
harness seeds products through ``ProductFactory``, which writes the row directly and never
posts the form. So the POST is reachable only by a Flask client, and this module is the
grader for it.

What a BDD scenario DOES grade, and what this module therefore does not re-grade, is
SERVING the result: ``@T-UC-GET-PRODUCTS-format-options-canonical-only`` already asserts on
the wire, across a2a/mcp/rest/e2e_rest, that a canonical-only product is returned with its
declarations intact and no ``format_ids`` key. The row shape this module asserts is the row
shape that scenario seeds, and the link between them is MEASURED rather than asserted: each
authoring test runs the authored row through ``convert_product_model_to_schema`` -- the
production function whose raise is the tenant-wide discovery outage.

No mocks. The creative-agent registry is only consulted for a non-empty ``formats``
submission, and canonical authoring submits none, so these scenarios reach the real handler
with no boundary stubbed.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from src.core.database.models import Product
from src.core.product_conversion import convert_product_model_to_schema
from tests.factories import AuthorizedPropertyFactory, ProductFactory, PropertyTagFactory, TenantFactory
from tests.helpers.admin_session import admin_auth_session, admin_test_app

pytestmark = [pytest.mark.admin, pytest.mark.requires_db]

#: A declaration the PIN defines: ``core/product-format-declaration.json`` requires
#: ``format_kind`` + ``params``, and ``image`` is one of the sixteen branches of the
#: discriminated union the product DTO declares by inheritance.
IMAGE_DECLARATION = {"format_kind": "image", "params": {"width": 300, "height": 250}}

LEGACY_FORMAT_ID = {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}


@pytest.fixture
def seller(factory_session):
    """A tenant an operator can create a product for, built by factories only.

    Returns ``(tenant, property_tag_selection)`` -- the second being the
    ``"<publisher_domain>:<tag>"`` string the form's property picker submits. The tenant
    comes back as the ROW, not its id: ``ProductFactory`` resolves ``tenant_id`` from its
    ``tenant`` SubFactory, so a test that names only the id gets a second tenant built
    underneath it and the product attached to that one instead.
    """
    tenant = TenantFactory(ad_server="mock")
    PropertyTagFactory(tenant=tenant, tag_id="all_inventory", name="All Inventory")
    authorized_property = AuthorizedPropertyFactory(tenant=tenant, tags=["all_inventory"])
    factory_session.commit()
    return tenant, f"{authorized_property.publisher_domain}:all_inventory"


@pytest.fixture
def operator(seller):
    """A Flask client carrying an authenticated admin session for ``seller``."""
    tenant, _ = seller
    tenant_id = tenant.tenant_id
    app = admin_test_app()
    with app.test_client() as client:
        admin_auth_session(client, tenant_id)
        yield client


def _create_form(property_tag_selection: str, **overrides: object) -> dict[str, object]:
    """The product-create form, filled in to the minimum the handler requires."""
    form: dict[str, object] = {
        "name": "Canonically Authored Product",
        "description": "Authored through the operator form",
        "formats": "[]",
        "pricing_model_0": "cpm_fixed",
        "currency_0": "USD",
        "rate_0": "10.00",
        "property_mode": "tags",
        "selected_property_tags": property_tag_selection,
        "delivery_measurement_provider": "publisher",
    }
    form.update(overrides)
    return form


def _edit_form(**overrides: object) -> dict[str, object]:
    """The product-edit form, filled in to the minimum the handler requires.

    The pricing block is NOT optional here: ``edit_product`` refuses a product with no
    pricing option, and a payload that omits it is refused before the format arms are
    read at all -- which would make a refusal test pass for the wrong reason.

    ``delivery_measurement_provider`` is not optional either, for a blunter reason: the
    route writes ``delivery_measurement`` unconditionally from the field, and the column
    is NOT NULL, so a payload omitting it raises IntegrityError (salesagent-igxy9).
    """
    form: dict[str, object] = {
        "name": "Edited Product",
        "pricing_model_0": "cpm_fixed",
        "currency_0": "USD",
        "rate_0": "10.00",
        "delivery_measurement_provider": "publisher",
    }
    form.update(overrides)
    return form


def _stored(session, tenant_id: str, product_id: str) -> Product | None:
    """The row as the database now holds it, not as this session last saw it."""
    session.expire_all()
    return session.scalars(select(Product).filter_by(tenant_id=tenant_id, product_id=product_id)).first()


#: The adapters that select a DIFFERENT product template, and the template each picks.
#: Three templates render a product form -- add_product.html (non-GAM add),
#: edit_product.html (non-GAM edit) and add_product_gam.html (GAM add AND GAM edit) -- so
#: these two adapters are the whole population, not a sample. An editor missing from one
#: of them is an authoring field that never appears for those sellers, and every POST test
#: in this module would still pass.
TEMPLATE_SELECTING_ADAPTERS = ["mock", "google_ad_manager"]


@pytest.mark.parametrize("ad_server", TEMPLATE_SELECTING_ADAPTERS)
def test_the_create_form_carries_the_canonical_editor(factory_session, ad_server):
    tenant = TenantFactory(ad_server=ad_server)
    factory_session.commit()
    app = admin_test_app()
    with app.test_client() as client:
        admin_auth_session(client, tenant.tenant_id)
        response = client.get(f"/tenant/{tenant.tenant_id}/products/add")

    assert response.status_code == 200, response.data[:2000]
    assert b'name="format_options"' in response.data


@pytest.mark.parametrize("ad_server", TEMPLATE_SELECTING_ADAPTERS)
def test_the_edit_form_shows_the_declaration_the_product_carries(factory_session, ad_server):
    """Pre-filled from the row: an editor that opens empty silently clears the arm."""
    tenant = TenantFactory(ad_server=ad_server)
    ProductFactory(tenant=tenant, product_id="canonical_product", format_ids=None, format_options=[IMAGE_DECLARATION])
    factory_session.commit()
    app = admin_test_app()
    with app.test_client() as client:
        admin_auth_session(client, tenant.tenant_id)
        response = client.get(f"/tenant/{tenant.tenant_id}/products/canonical_product/edit")

    assert response.status_code == 200, response.data[:2000]
    assert b'name="format_options"' in response.data
    # The stored document, not just the field: the editor is the only place the
    # declaration can be read, and an unfilled one loses it on the next save.
    assert b'"format_kind": "image"' in response.data or b'"format_kind":"image"' in response.data


def test_the_operator_form_authors_a_canonical_only_product(operator, seller, factory_session):
    """format_options authored, format_ids absent -- and the row is servable."""
    tenant, tag_selection = seller
    tenant_id = tenant.tenant_id

    response = operator.post(
        f"/tenant/{tenant_id}/products/add",
        data=_create_form(tag_selection, product_id="canonical_only", format_options=json.dumps([IMAGE_DECLARATION])),
    )

    assert response.status_code in (301, 302), response.data[:2000]
    row = _stored(factory_session, tenant_id, "canonical_only")
    assert row is not None, "the operator form stored no product"

    # POSITIVE: the declaration is there, and it is the one authored.
    assert row.format_options == [IMAGE_DECLARATION]
    # ABSENCE, paired with it: the deprecated arm is NULL, not an empty array. An empty
    # array satisfies the deprecated anyOf branch by its KEY while declaring no format.
    assert row.format_ids is None

    # SERVABLE: the production conversion whose raise takes the whole tenant's discovery
    # down accepts this row, and carries the kind that was authored.
    served = convert_product_model_to_schema(row, adapter_type="mock")
    assert [declaration.format_kind for declaration in served.format_options] == ["image"]


def test_a_product_declaring_neither_arm_is_refused_at_authoring_time(operator, seller, factory_session):
    """core/product.json's root anyOf, enforced where the operator can still fix it."""
    tenant, tag_selection = seller
    tenant_id = tenant.tenant_id

    response = operator.post(
        f"/tenant/{tenant_id}/products/add",
        data=_create_form(tag_selection, product_id="no_format_arm", format_options=""),
    )

    assert response.status_code == 200, "a refusal re-renders the form rather than redirecting"
    assert b"at least one creative format" in response.data
    assert _stored(factory_session, tenant_id, "no_format_arm") is None


def test_an_unparseable_declaration_is_refused(operator, seller, factory_session):
    tenant, tag_selection = seller
    tenant_id = tenant.tenant_id

    response = operator.post(
        f"/tenant/{tenant_id}/products/add",
        data=_create_form(tag_selection, product_id="bad_json", format_options="[{format_kind: image}]"),
    )

    assert response.status_code == 200
    assert b"not valid JSON" in response.data
    assert _stored(factory_session, tenant_id, "bad_json") is None


def test_a_format_kind_the_pin_does_not_define_is_refused(operator, seller, factory_session):
    """The refusal that keeps one mis-authored product from ending tenant-wide discovery.

    Stored, this document passes every column CHECK and then fails in
    ``convert_product_model_to_schema``, which ``get_products`` runs in a loop that
    re-raises -- so the whole catalog answers INTERNAL_ERROR.
    """
    tenant, tag_selection = seller
    tenant_id = tenant.tenant_id

    response = operator.post(
        f"/tenant/{tenant_id}/products/add",
        data=_create_form(
            tag_selection,
            product_id="unknown_kind",
            format_options=json.dumps([{"format_kind": "interpretive_dance", "params": {}}]),
        ),
    )

    assert response.status_code == 200
    assert b"not a valid canonical format declaration" in response.data
    assert _stored(factory_session, tenant_id, "unknown_kind") is None


def test_the_edit_form_authors_the_canonical_arm_on_a_legacy_product(operator, seller, factory_session):
    """A product already selling on format_ids gains format_options without losing it.

    Both arms is the third legal shape under the anyOf, and the pin's instruction for a
    seller that still has legacy buyers: "sellers MAY additionally project those
    declarations to format_ids".
    """
    tenant, _ = seller
    tenant_id = tenant.tenant_id
    ProductFactory(tenant=tenant, product_id="legacy_product", format_ids=[LEGACY_FORMAT_ID])
    factory_session.commit()

    response = operator.post(
        f"/tenant/{tenant_id}/products/legacy_product/edit",
        data=_edit_form(name="Legacy Product", format_options=json.dumps([IMAGE_DECLARATION])),
        follow_redirects=True,
    )

    assert response.status_code == 200, response.data[:2000]
    row = _stored(factory_session, tenant_id, "legacy_product")
    assert row.format_options == [IMAGE_DECLARATION]
    assert row.format_ids == [LEGACY_FORMAT_ID], "an edit that submits one arm leaves the other alone"
    # Both arms is a legal shape, so the conversion must still serve it.
    served = convert_product_model_to_schema(row, adapter_type="mock")
    assert [declaration.format_kind for declaration in served.format_options] == ["image"]


def test_the_edit_form_refuses_clearing_the_last_declared_arm(operator, seller, factory_session):
    """Blanking the editor on a canonical-only product would leave it declaring nothing."""
    tenant, _ = seller
    tenant_id = tenant.tenant_id
    ProductFactory(
        tenant=tenant,
        product_id="canonical_product",
        format_ids=None,
        format_options=[IMAGE_DECLARATION],
    )
    factory_session.commit()

    response = operator.post(
        f"/tenant/{tenant_id}/products/canonical_product/edit",
        data=_edit_form(name="Canonical Product", format_options=""),
        follow_redirects=True,
    )

    # The MESSAGE, not just the redirect: edit_product redirects back to the form for
    # every refusal it has, so a status-only assertion would pass on any of them.
    assert b"at least one creative format" in response.data
    row = _stored(factory_session, tenant_id, "canonical_product")
    assert row.format_options == [IMAGE_DECLARATION], "the refused edit left the declaration in place"
    assert row.format_ids is None

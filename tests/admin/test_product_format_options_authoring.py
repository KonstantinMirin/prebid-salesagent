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

from src.core.database.models import Product, Tenant
from src.core.product_conversion import convert_product_model_to_schema
from tests.factories import (
    AuthorizedPropertyFactory,
    InventoryProfileFactory,
    ProductFactory,
    PropertyTagFactory,
    TenantFactory,
)
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


def test_a_product_linked_to_a_canonical_profile_authors_no_declarations_of_its_own(operator, seller, factory_session):
    """A linked profile supplies the contract (``Product.format_contract``), so the form
    does not make the operator author declarations the profile then overrides."""
    tenant, tag_selection = seller
    tenant_id = tenant.tenant_id
    profile = InventoryProfileFactory(tenant=tenant, format_ids=None, format_options=[IMAGE_DECLARATION])
    factory_session.commit()

    response = operator.post(
        f"/tenant/{tenant_id}/products/add",
        data=_create_form(
            tag_selection, product_id="profile_linked", format_options="", inventory_profile_id=str(profile.id)
        ),
    )

    assert response.status_code in (301, 302), response.data[:2000]
    row = _stored(factory_session, tenant_id, "profile_linked")
    assert row is not None, "the operator form refused a product whose profile declares its formats"
    assert row.format_options is None
    assert row.format_ids is None
    served = convert_product_model_to_schema(row, adapter_type="mock")
    assert [declaration.format_kind for declaration in served.format_options] == ["image"]


def test_a_legacy_only_profile_does_not_stand_in_for_canonical_declarations(operator, seller, factory_session):
    """A new product's contract is canonical: a profile with only ``format_ids`` does not
    satisfy the create check ("Do not author a new product from format_ids alone")."""
    tenant, tag_selection = seller
    tenant_id = tenant.tenant_id
    profile = InventoryProfileFactory(tenant=tenant, format_ids=[LEGACY_FORMAT_ID], format_options=None)
    factory_session.commit()

    response = operator.post(
        f"/tenant/{tenant_id}/products/add",
        data=_create_form(
            tag_selection, product_id="legacy_profile_linked", format_options="", inventory_profile_id=str(profile.id)
        ),
    )

    assert response.status_code == 200, "a refusal re-renders the form rather than redirecting"
    assert b"at least one creative format" in response.data
    assert _stored(factory_session, tenant_id, "legacy_profile_linked") is None


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
    """A legacy product that gains canonical declarations retires its stored format_ids.

    canonical-formats.mdx, Producer rules: "Compatibility format_ids MUST be derived from
    them rather than maintained as a second authored catalog." So once the operator authors
    declarations, the stored column is cleared and the format_ids the product serves is
    derived from the declaration's ``v1_format_ref``.
    """
    tenant, _ = seller
    tenant_id = tenant.tenant_id
    ProductFactory(tenant=tenant, product_id="legacy_product", format_ids=[LEGACY_FORMAT_ID])
    factory_session.commit()
    declaration = {**IMAGE_DECLARATION, "v1_format_ref": [LEGACY_FORMAT_ID]}

    response = operator.post(
        f"/tenant/{tenant_id}/products/legacy_product/edit",
        data=_edit_form(name="Legacy Product", format_options=json.dumps([declaration])),
        follow_redirects=True,
    )

    assert response.status_code == 200, response.data[:2000]
    row = _stored(factory_session, tenant_id, "legacy_product")
    assert row.format_options == [declaration]
    assert row.format_ids is None, f"the stored legacy column survived beside the declarations: {row.format_ids!r}"

    # Served through the production conversion: the legacy arm a 3.x buyer receives is the
    # declaration's asserted ref, as the pinned FormatReferenceStructuredObject.
    served = convert_product_model_to_schema(row, adapter_type="mock")
    assert [declaration.format_kind for declaration in served.format_options] == ["image"]
    assert [reference.id for reference in served.format_ids] == ["display_300x250_image"]
    assert type(served.format_ids[0]) is not dict


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


# ── A4 completion (salesagent-ol033.6): format_ids is no longer AUTHORED here ────────
#
# The tests above grade that the canonical arm CAN be authored (work item A4-minimal,
# salesagent-ol033.2.1). These grade that the legacy arm can no longer be, which is the
# other half: the pin deprecates format_ids in 3.2, removes it in 4.0 and says "Do not
# author a new product from format_ids alone", and this epic's charter keeps format_id an
# INPUT only -- acceptance and recording.
#
# Not authored is NOT dropped. The column persists and a product that already carries a
# legacy arm keeps it, which is what the second and third tests here grade.


def test_the_create_form_stores_no_legacy_arm_even_when_one_is_submitted(operator, seller, factory_session):
    """A submitted ``formats`` payload is IGNORED rather than stored.

    Submitting one is the discriminating input. A test that posted an empty ``formats``
    would pass identically before and after the authoring was removed, because the old
    handler also stored nothing for an empty picker -- so it would grade nothing. This
    posts a well-formed legacy reference, the shape the old picker produced, and requires
    the row to come back with no legacy arm at all.
    """
    tenant, tag_selection = seller
    tenant_id = tenant.tenant_id

    response = operator.post(
        f"/tenant/{tenant_id}/products/add",
        data=_create_form(
            tag_selection,
            product_id="legacy_submitted",
            formats=json.dumps(
                [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}]
            ),
            format_options=json.dumps([IMAGE_DECLARATION]),
        ),
    )

    assert response.status_code in (301, 302), response.data[:2000]
    row = _stored(factory_session, tenant_id, "legacy_submitted")
    assert row is not None, "the operator form stored no product"
    # NULL, not [] -- an empty array satisfies the deprecated anyOf branch by its key.
    assert row.format_ids is None, f"a submitted legacy arm was authored anyway: {row.format_ids!r}"
    # Paired POSITIVE, so this cannot pass by the whole POST having been refused.
    assert row.format_options == [IMAGE_DECLARATION]


def test_editing_a_legacy_product_leaves_its_stored_arm_untouched(operator, seller, factory_session):
    """An edit is not how an existing legacy product loses its only format declaration.

    The hazard this guards is specific and was live: the edit handler used to write
    ``product.format_ids = validated_formats or None`` from the picker's hidden input,
    which the form always submitted. Remove the picker and leave that write, and every
    edit of a legacy product silently NULLs the one arm it has -- then the conversion
    refuses the row and get_products answers INTERNAL_ERROR for the whole tenant.

    The edit changes the NAME only, so nothing in the payload mentions formats at all.
    """
    tenant, _ = seller
    tenant_id = tenant.tenant_id
    stored_arm = [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}]
    ProductFactory(
        tenant=tenant,
        product_id="legacy_product",
        format_ids=stored_arm,
        format_options=None,
    )
    factory_session.commit()

    response = operator.post(
        f"/tenant/{tenant_id}/products/legacy_product/edit",
        data=_edit_form(name="Renamed Legacy Product"),
        follow_redirects=True,
    )

    assert response.status_code == 200, response.data[:2000]
    row = _stored(factory_session, tenant_id, "legacy_product")
    assert row.format_ids == stored_arm, f"the edit changed the stored legacy arm: {row.format_ids!r}"
    assert row.name == "Renamed Legacy Product", "the edit did not take effect, so the arm survived vacuously"


# ── RFC S3 (salesagent-ol033.20.3): options in this seller's own publisher namespace ───
#
# adagents.json#/properties/formats: products selling this publisher's inventory SHOULD
# reference its declarations "via inline format_options whose format_option_id matches an
# entry here". The seller serves that file at its own host, so a declaration naming
# ``publisher_domain == tenant.primary_domain`` must name an option its catalog publishes.
# Whether the catalog is PUBLISHED is graded on the four transports by
# tests/bdd/features/local-publisher-format-catalog.feature; these grade the authoring
# refusals, which only a Flask client reaches.

#: One reusable publisher option, as the catalog stores it and the served formats[] carries it.
CATALOG_OPTION = {"format_kind": "image", "format_option_id": "homepage_mrec", "params": {"width": 300, "height": 250}}


def _stored_catalog(session, tenant_id: str) -> list | None:
    """The tenant's catalog as the database now holds it."""
    session.expire_all()
    return session.get(Tenant, tenant_id).publisher_format_options


@pytest.mark.parametrize(
    ("catalog", "accepted"),
    [([CATALOG_OPTION], True), (None, False)],
    ids=["catalog_declares_it", "catalog_does_not"],
)
def test_an_own_publisher_option_must_be_one_the_catalog_publishes(
    operator, seller, factory_session, catalog, accepted
):
    """The same declaration, stored or refused by what the seller's own catalog declares."""
    tenant, tag_selection = seller
    tenant.publisher_format_options = catalog
    factory_session.commit()
    reference = {**CATALOG_OPTION, "publisher_domain": tenant.primary_domain}

    response = operator.post(
        f"/tenant/{tenant.tenant_id}/products/add",
        data=_create_form(tag_selection, product_id="own_option", format_options=json.dumps([reference])),
    )

    row = _stored(factory_session, tenant.tenant_id, "own_option")
    if accepted:
        assert response.status_code in (301, 302), response.data[:2000]
        assert row is not None and row.format_options == [reference]
    else:
        assert response.status_code == 200, "a refusal re-renders the form rather than redirecting"
        assert b"publisher format catalog does not declare" in response.data
        assert row is None


def test_another_publishers_option_is_not_resolved_against_this_sellers_catalog(operator, seller, factory_session):
    """Only the seller's own namespace is checked: another publisher's file is the buyer's to resolve.

    core/placement.json format_options: "buyers MUST also resolve" a publisher reference.
    The tenant has NO catalog, so the same option under its own domain would be refused
    (the parametrized test above); under a foreign domain it is stored.
    """
    tenant, tag_selection = seller
    reference = {**CATALOG_OPTION, "publisher_domain": "another-publisher.example"}

    response = operator.post(
        f"/tenant/{tenant.tenant_id}/products/add",
        data=_create_form(tag_selection, product_id="foreign_option", format_options=json.dumps([reference])),
    )

    assert response.status_code in (301, 302), response.data[:2000]
    row = _stored(factory_session, tenant.tenant_id, "foreign_option")
    assert row is not None and row.format_options == [reference]


def test_the_operator_saves_the_publisher_format_catalog(operator, seller, factory_session):
    tenant, _ = seller

    response = operator.post(
        f"/tenant/{tenant.tenant_id}/authorized-properties/format-catalog",
        data={"publisher_format_options": json.dumps([CATALOG_OPTION])},
        follow_redirects=True,
    )

    assert response.status_code == 200, response.data[:2000]
    assert b"Publisher format catalog saved" in response.data
    assert _stored_catalog(factory_session, tenant.tenant_id) == [CATALOG_OPTION]


def test_a_catalog_option_without_an_id_is_refused(operator, seller, factory_session):
    """An entry no {publisher_domain, format_option_id} can name is not a reusable option."""
    tenant, _ = seller
    unnamed = {key: value for key, value in CATALOG_OPTION.items() if key != "format_option_id"}

    response = operator.post(
        f"/tenant/{tenant.tenant_id}/authorized-properties/format-catalog",
        data={"publisher_format_options": json.dumps([unnamed])},
        follow_redirects=True,
    )

    assert b"needs a format_option_id" in response.data
    assert _stored_catalog(factory_session, tenant.tenant_id) is None


def test_withdrawing_an_option_a_product_names_is_refused(operator, seller, factory_session):
    """A stored product never announces an own-namespace option its publisher file stopped declaring."""
    tenant, _ = seller
    tenant.publisher_format_options = [CATALOG_OPTION]
    ProductFactory(
        tenant=tenant,
        product_id="names_the_option",
        format_ids=None,
        format_options=[{**CATALOG_OPTION, "publisher_domain": tenant.primary_domain}],
    )
    factory_session.commit()

    response = operator.post(
        f"/tenant/{tenant.tenant_id}/authorized-properties/format-catalog",
        data={"publisher_format_options": ""},
        follow_redirects=True,
    )

    assert b"products still reference it" in response.data
    assert _stored_catalog(factory_session, tenant.tenant_id) == [CATALOG_OPTION]


@pytest.mark.parametrize(
    ("catalog", "accepted"),
    [([CATALOG_OPTION], True), (None, False)],
    ids=["catalog_declares_it", "catalog_withdrew_it"],
)
@pytest.mark.parametrize("route", ["create", "edit"])
def test_linking_a_profile_whose_own_option_the_catalog_withdrew_is_refused(
    operator, seller, factory_session, route, catalog, accepted
):
    """A linked profile announces its declarations on the product's behalf, so the link is checked.

    The profile was authored while the catalog declared the option; the catalog then withdrew
    it, which nothing refused because no product was linked. Linking a product now would serve
    an own-namespace option the seller's adagents.json formats[] no longer declares. The
    product's own arm is product-local, so only the profile's arm can decide the outcome.
    """
    tenant, tag_selection = seller
    tenant.publisher_format_options = catalog
    profile = InventoryProfileFactory(
        tenant=tenant,
        format_ids=None,
        format_options=[{**CATALOG_OPTION, "publisher_domain": tenant.primary_domain}],
    )
    if route == "edit":
        ProductFactory(tenant=tenant, product_id="links_profile", format_ids=None, format_options=[IMAGE_DECLARATION])
    factory_session.commit()

    if route == "create":
        response = operator.post(
            f"/tenant/{tenant.tenant_id}/products/add",
            data=_create_form(
                tag_selection,
                product_id="links_profile",
                format_options=json.dumps([IMAGE_DECLARATION]),
                inventory_profile_id=str(profile.id),
            ),
            follow_redirects=True,
        )
    else:
        response = operator.post(
            f"/tenant/{tenant.tenant_id}/products/links_profile/edit",
            data=_edit_form(inventory_profile_id=str(profile.id)),
            follow_redirects=True,
        )

    row = _stored(factory_session, tenant.tenant_id, "links_profile")
    if accepted:
        assert row is not None and row.inventory_profile_id == profile.id, response.data[:2000]
    else:
        assert b"publisher format catalog does not declare" in response.data
        assert row is None if route == "create" else row.inventory_profile_id is None

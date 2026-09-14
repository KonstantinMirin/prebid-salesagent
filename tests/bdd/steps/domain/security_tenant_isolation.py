"""Steps for BR-SECURITY-002: a credential reaches exactly one tenant's data.

Why this module exists
----------------------
Identity and tenant resolution happen in ONE place -- ``_resolve_identity``, called only
from ``src/core/tools/_boundary.invoke_tool``. Nothing graded what that one place decides.
Every existing scenario seeds a single tenant, so a repository that forgot its ``tenant_id``
filter would return the right rows anyway: there were no wrong rows to return.

The rule this module is built on: **the wrong answer has to be available in the database.**
Every scenario here seeds TWO tenants, each with a product only it owns, and then asserts on
both what came back AND what did not. An assertion that only checks "I got my product" passes
under a total isolation failure, because the caller's own product is in the contaminated
result too.

What each scenario can independently catch
------------------------------------------
* Tenant SCOPING -- a query that returns another tenant's rows to a correctly authenticated
  buyer. Caught by asserting the other tenant's product is absent.
* Credential BINDING -- a token minted for tenant A accepted against tenant B.
  ``get_principal_from_token(token, tenant_id)`` filters on BOTH columns
  (``src/core/auth_utils.py``), so A's token against B resolves no principal and the request
  is refused. Caught by addressing B while presenting A's credential.

These fail for different reasons and neither substitutes for the other.

How a scenario addresses a tenant
---------------------------------
The credential a dispatch presents IS a token/tenant pair: ``credential_headers`` builds
``Authorization: Bearer`` from the token and ``x-adcp-tenant`` from the tenant id, so
handing ``dispatch_request`` A's token with B's tenant id puts exactly that mismatch on
the wire, and production resolves it for real: header -> ``_detect_tenant`` ->
tenant-scoped principal lookup. Nothing is stubbed, and the same request goes out on every
transport the scenario is parametrized over.
"""

from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.generic._dispatch import dispatch_request
from tests.helpers.credentials import credential_headers

#: The two tenants and the product each one alone owns. Ids are literals rather than
#: factory sequences because the Then steps name them: a scenario that asserts "none of
#: tenant B's products" has to be able to say which product that is.
TENANT_A = "tenant_iso_a"
TENANT_B = "tenant_iso_b"
PRINCIPAL_A = "buyer_iso_a"
PRINCIPAL_B = "buyer_iso_b"
PRODUCT_A = "prod_only_in_a"
PRODUCT_B = "prod_only_in_b"


def _seed_tenant(ctx: dict, tenant_id: str, principal_id: str, product_id: str):
    """Seed one tenant with its own principal and one product only it owns."""
    from src.core.database.models import Principal, Product, Tenant
    from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
    from tests.factories.core import get_or_create

    env = ctx["env"]
    tenant = get_or_create(
        env, Tenant, {"tenant_id": tenant_id}, lambda: TenantFactory(tenant_id=tenant_id, ad_server="mock")
    )
    principal = get_or_create(
        env,
        Principal,
        {"principal_id": principal_id, "tenant_id": tenant_id},
        lambda: PrincipalFactory(tenant=tenant, principal_id=principal_id),
    )

    def _product_with_pricing() -> Product:
        # A product with no PricingOption cannot be converted to the AdCP schema at all --
        # get_products raises INTERNAL_ERROR before it ever returns a list -- so without this
        # the scenario would fail for a seeding reason and never reach the isolation question.
        product = ProductFactory(tenant=tenant, product_id=product_id)
        PricingOptionFactory(product=product)
        return product

    get_or_create(env, Product, {"product_id": product_id, "tenant_id": tenant_id}, _product_with_pricing)
    return tenant, principal


# ── Given ───────────────────────────────────────────────────────────


@given("two tenants each own a product the other does not")
def given_two_tenants(ctx: dict) -> None:
    """Seed both tenants BEFORE any request, so a leak has something to leak."""
    _, principal_a = _seed_tenant(ctx, TENANT_A, PRINCIPAL_A, PRODUCT_A)
    _, principal_b = _seed_tenant(ctx, TENANT_B, PRINCIPAL_B, PRODUCT_B)
    ctx["env"]._commit_factory_data()
    # The tokens the factories minted. Read from the rows rather than assumed, so the
    # credential presented is the one the database will be asked about.
    ctx["token_a"] = principal_a.access_token
    ctx["token_b"] = principal_b.access_token


# ── When ────────────────────────────────────────────────────────────


@when(parsers.parse('the buyer requests products with tenant "{tenant}" credentials'))
def when_request_products_as(ctx: dict, tenant: str) -> None:
    """Present a tenant's own credential, addressed to that same tenant."""
    token = ctx["token_a"] if tenant == "A" else ctx["token_b"]
    tenant_id = TENANT_A if tenant == "A" else TENANT_B
    dispatch_request(ctx, credential=credential_headers(token=token, tenant=tenant_id), brief="video ads")


@when(parsers.parse('the buyer presents tenant "{holder}" credentials addressed to tenant "{target}"'))
def when_request_products_cross_tenant(ctx: dict, holder: str, target: str) -> None:
    """Present one tenant's credential while addressing the other."""
    token = ctx["token_a"] if holder == "A" else ctx["token_b"]
    tenant_id = TENANT_A if target == "A" else TENANT_B
    dispatch_request(ctx, credential=credential_headers(token=token, tenant=tenant_id), brief="video ads")


# ── Then ────────────────────────────────────────────────────────────


def _returned_product_ids(ctx: dict) -> list[str]:
    result = ctx["result"]
    assert result.is_success, f"expected a successful response, got {result.error or result.envelope}"
    products = result.payload.products
    assert products is not None, "response carried no products field at all"
    return [p.product_id for p in products]


@then(parsers.parse('the response contains tenant "{tenant}" products'))
def then_contains_own_products(ctx: dict, tenant: str) -> None:
    expected = PRODUCT_A if tenant == "A" else PRODUCT_B
    returned = _returned_product_ids(ctx)
    assert expected in returned, f"tenant {tenant}'s own product {expected!r} is missing; got {returned}"


@then("the request is refused and no products are returned")
def then_refused_with_no_products(ctx: dict) -> None:
    """The credential did not act on the tenant it was pointed at.

    Deliberately does NOT pin an error code. The code is a separate obligation and, on a
    public tool, currently a confused one: ``get_products`` is ``auth="optional"``, so a
    rejected credential is downgraded to anonymous before the tool runs, and the tenant's
    ``brand_manifest_policy="require_auth"`` then raises AUTH_MISSING -- telling a buyer who
    DID present a credential that none was presented. Filed separately; asserting it here
    would freeze a diagnosis this scenario has no opinion about.

    What this scenario does have an opinion about is the security property, and it is
    unambiguous: the request must not be SERVED. Both halves are checked, because a leak
    could arrive as either tenant's data.
    """
    result = ctx["result"]
    assert not result.is_success, (
        f"a credential minted for one tenant was SERVED against another; payload={result.payload}"
    )
    for product_id in (PRODUCT_A, PRODUCT_B):
        assert product_id not in str(result.wire_response or result.envelope or ""), (
            f"{product_id!r} appears in the response to a cross-tenant credential"
        )


@then(parsers.parse('the response contains no tenant "{tenant}" products'))
def then_contains_no_foreign_products(ctx: dict, tenant: str) -> None:
    """The half that actually grades isolation.

    Its counterpart ("contains tenant A's products") passes under a TOTAL isolation failure,
    because a result carrying every tenant's products carries the caller's own too. Only
    absence distinguishes a scoped query from an unscoped one.
    """
    forbidden = PRODUCT_A if tenant == "A" else PRODUCT_B
    returned = _returned_product_ids(ctx)
    assert forbidden not in returned, (
        f"tenant {tenant}'s product {forbidden!r} leaked into another tenant's response; got {returned}"
    )

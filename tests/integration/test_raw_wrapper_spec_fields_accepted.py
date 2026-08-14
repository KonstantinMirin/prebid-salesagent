"""A `_raw()` wrapper called directly must accept every field its pinned
request schema defines (GH #1193, salesagent-g6m2.10).

Sibling of tests/integration/test_spec_request_fields_accepted.py — that one
drives the MCP transport end-to-end; this one drives the raw function call
directly, the real call the A2A/REST layers make into src/core/tools/. The
structural guard, tests/unit/test_architecture_raw_wrapper_spec_fields.py,
proves the SHAPE (every field is in the signature) for all 6 fixed
functions offline; this proves an actual call with a previously-rejected
field genuinely executes rather than merely binding.

Before the fix, `get_products_raw(ext=...)` raised a plain Python TypeError
at argument-binding time — reproducible with no DB and no transport, since
Python validates keyword arguments before a coroutine is even constructed.
"""

from __future__ import annotations

import pytest

from src.core.schemas import GetProductsResponse
from src.core.tools.products import get_products_raw
from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.fixture
def product_env(integration_db):
    with ProductEnv(tenant_id="raw-spec-fields", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="raw-spec-fields")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        product = ProductFactory(tenant=tenant, delivery_type="guaranteed")
        PricingOptionFactory(product=product, pricing_model="cpm", rate="15.00", is_fixed=True, currency="USD")
        env.set_policy_approved()
        env.set_ranking_disabled()
        yield env


async def test_get_products_raw_accepts_ext_on_a_real_call(product_env):
    """A direct call with ext=... must actually execute, not just bind.

    This is the exact reproduction from salesagent-g6m2.10: before the fix,
    this call raised TypeError before the coroutine was even created.
    """
    identity = product_env.identity_for(Transport.A2A)

    response = await get_products_raw(
        brief="Display inventory on outdoor lifestyle content.",
        ext={"custom_field": "value"},
        identity=identity,
    )

    assert isinstance(response, GetProductsResponse)


async def test_get_products_raw_accepts_account_on_a_real_call(product_env):
    """A second previously-missing field, to prove this isn't ext-specific."""
    identity = product_env.identity_for(Transport.A2A)

    response = await get_products_raw(
        brief="Display inventory on outdoor lifestyle content.",
        account={"brand": {"domain": "acmeoutdoor.example"}, "operator": "pinnacle-agency.example"},
        identity=identity,
    )

    assert isinstance(response, GetProductsResponse)


async def test_get_products_raw_still_rejects_truly_unknown_arguments(product_env):
    """Accepting the SPEC'd fields must not become accepting anything.

    Mirrors test_unknown_arguments_are_still_rejected in the MCP-side sibling —
    the fix must not be a **kwargs catch-all that defeats its own purpose.
    """
    identity = product_env.identity_for(Transport.A2A)

    with pytest.raises(TypeError, match="definitely_not_a_real_adcp_field"):
        await get_products_raw(
            brief="Display inventory on outdoor lifestyle content.",
            definitely_not_a_real_adcp_field="x",
            identity=identity,
        )

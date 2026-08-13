"""MCP tools must accept the request fields 3.1.1 defines (GH #1193).

Sibling of ``test_version_envelope_accepted.py`` and deliberately separate: that
one covers the ONE envelope composed into every schema, fixable at the
registration chokepoint. This one covers the fields each tool's OWN request
schema defines and our signature omits — per-tool protocol surface, and a
different fix.

The two produce the identical error string, which is why they are easy to
conflate:

    VALIDATION_ERROR: Unexpected keyword argument

FastMCP builds each tool's input schema from its Python signature and validates
with pydantic before our code runs, so ANY field the spec defines but the
signature omits is rejected outright — not ignored, not defaulted.

Measured against the pinned bundle (`tests/storyboard/runner/adcp-3.1.1/schemas`):

    get_products           18 schema fields,  5 in signature, 13 missing
    sync_accounts           7 schema fields,  4 in signature,  3 missing
    sync_creatives         11 schema fields,  9 in signature,  2 missing
    get_adcp_capabilities   3 schema fields,  1 in signature,  2 missing

These reach the conformance runner as 12 ledgered checks. They only became
visible once the version envelope was accepted (GH #1512) and the
storyboards got past their first step — all 12 were NOT-COLLECTED before that.

The request below is the storyboard's own `sample_request`, verbatim:
``repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/invalid_transitions.yaml``
step ``get_products_brief``.
"""

from __future__ import annotations

import pytest

from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Verbatim from the pinned storyboard step, minus nothing.
STORYBOARD_SAMPLE_REQUEST = {
    "buying_mode": "brief",
    "brief": "Display inventory on outdoor lifestyle content. Q3 flight.",
    "filters": {"is_fixed_price": True},
    "account": {
        "brand": {"domain": "acmeoutdoor.example"},
        "operator": "pinnacle-agency.example",
    },
}


@pytest.fixture
def product_env(integration_db):
    with ProductEnv(tenant_id="spec-fields", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="spec-fields")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        # A product must carry at least one pricing option to serialize at all —
        # without it get_products fails with SERVICE_UNAVAILABLE, which would
        # make every case here fail for a reason that has nothing to do with
        # request-field acceptance.
        product = ProductFactory(tenant=tenant, delivery_type="guaranteed")
        PricingOptionFactory(product=product, pricing_model="cpm", rate="15.00", is_fixed=True, currency="USD")
        env.set_policy_approved()
        env.set_ranking_disabled()
        yield env


def test_get_products_accepts_the_storyboard_sample_request(product_env):
    """The reproduction, at the exact shape the conformance runner sends.

    A seller that rejects a spec-defined optional field is non-conformant even
    if it cannot act on the field: the schema defines it, so the buyer is
    entitled to send it.
    """
    result = product_env.call_via(Transport.MCP, **STORYBOARD_SAMPLE_REQUEST)

    assert result.is_success, (
        f"get_products rejected fields its own 3.1.1 request schema defines: "
        f"{result.wire_error_envelope or result.error}"
    )


# get_products enforces its own rule that at least one of brief/brand/filters is
# present, so a field cannot be tested in true isolation — an empty-but-for-one
# request fails on that rule and tells you nothing about field acceptance. Each
# case therefore adds ONE field to a minimally valid request, keeping the field
# under test the only variable.
MINIMAL_VALID_REQUEST = {"brief": STORYBOARD_SAMPLE_REQUEST["brief"]}
ADDED_FIELDS = sorted(set(STORYBOARD_SAMPLE_REQUEST) - set(MINIMAL_VALID_REQUEST))


@pytest.mark.parametrize("field", ADDED_FIELDS)
def test_each_sample_request_field_is_accepted_alongside_a_valid_request(product_env, field):
    """Which field is rejected, one at a time.

    The aggregate test above says "something in here is rejected"; this says
    which, so a partial fix cannot look like a whole one.
    """
    result = product_env.call_via(
        Transport.MCP,
        **MINIMAL_VALID_REQUEST,
        **{field: STORYBOARD_SAMPLE_REQUEST[field]},
    )

    assert result.is_success, f"get_products rejected `{field}`: {result.wire_error_envelope or result.error}"


def test_a_request_missing_brief_brand_and_filters_is_still_rejected(product_env):
    """The rule that made true isolation impossible is itself worth pinning.

    Accepting more spec fields must not accidentally make an under-specified
    request valid — `account` alone is not a product query.
    """
    result = product_env.call_via(Transport.MCP, account=STORYBOARD_SAMPLE_REQUEST["account"])

    assert result.is_error, "a request with none of brief/brand/filters must still be rejected"


def test_unknown_arguments_are_still_rejected(product_env):
    """Accepting the SPEC'd fields must not become accepting anything.

    `universal/schema-validation.yaml` grades unknown-field handling, so the fix
    cannot be a `**kwargs` catch-all.
    """
    result = product_env.call_via(Transport.MCP, definitely_not_a_real_adcp_field="x")

    assert result.is_error, "an undeclared, non-spec argument must still be rejected"

"""A buyer's version pin is negotiated for every tool, not just for capabilities.

``negotiate_adcp_version`` had one call site, inside ``_get_adcp_capabilities_impl``.
Every other tool ignored the pin, so a buyer asserting a major this build cannot serve
was answered normally -- and ``get_products`` is the tool the pinned storyboard grades
this on (``compliance/universal/error-compliance.yaml``, scenario
``version_negotiation``).

The negotiation now runs at the boundary, ahead of account enrichment and the replay
cache, so these tests drive the WIRE on every in-process transport rather than calling
``_impl``: the whole defect was one entry point disagreeing with the others, and an
``_impl``-level assertion cannot see that.

Vectors are taken from the storyboard steps verbatim -- ``adcp_major_version: 99`` and
``adcp_version: "99.0"``, both chosen by the spec as the maximum LEGAL values (the pin
types the major ``Ge(1), Le(99)``), so a rejection here is negotiation and never schema
validation.
"""

from __future__ import annotations

import pytest

#: The release and major this build serves, read from the same constants production
#: negotiates against. A literal here would pass while the seller spoke something else.
from src.core.version_negotiation import SUPPORTED_ADCP_MAJORS, SUPPORTED_ADCP_VERSIONS
from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_WIRE_TRANSPORTS = [Transport.MCP, Transport.A2A, Transport.REST]


@pytest.fixture
def env(integration_db):
    """A tenant with one sellable product, so the ACCEPT cases have something to return."""
    with ProductEnv(tenant_id="version-negotiation", principal_id="version-principal") as env:
        tenant = TenantFactory(tenant_id="version-negotiation", subdomain="version-negotiation")
        PrincipalFactory(tenant=tenant, principal_id="version-principal")
        product = ProductFactory(tenant=tenant, product_id="prod_versioned")
        PricingOptionFactory(product=product)
        yield env


@pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_unsupported_major_pin_is_refused_by_a_tool_that_is_not_capabilities(env, transport):
    """Storyboard ``error_compliance::unsupported_major_version``, on the wire."""
    result = env.call_via(transport, brief="Version negotiation probe", adcp_major_version=99)

    assert result.is_error, (
        f"[{transport.value}] a major this build cannot serve must be refused; "
        f"got {getattr(result, 'wire_response', None) or result.payload!r}"
    )
    # correctable, not fatal: enums/error-code.json puts VERSION_UNSUPPORTED there in every
    # published bundle through 3.2.0-rc.1, and the storyboard's own graded validations never
    # check recovery -- only its narrative `expected:` prose says fatal.
    result.assert_wire_error("VERSION_UNSUPPORTED", recovery="correctable")


@pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_unsupported_release_pin_is_refused(env, transport):
    """Storyboard ``error_compliance::unsupported_release_version``, on the wire.

    The release-precision sibling. A seller that validated only the integer major would
    pass the step above and still refuse nothing a 3.1 buyer actually sends, since 3.1
    promotes ``adcp_version`` to the primary wire field.
    """
    result = env.call_via(transport, brief="Version negotiation probe", adcp_version="99.0")

    assert result.is_error, (
        f"[{transport.value}] a release this build cannot serve must be refused; "
        f"got {getattr(result, 'wire_response', None) or result.payload!r}"
    )
    result.assert_wire_error("VERSION_UNSUPPORTED", recovery="correctable")


@pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_a_supported_major_pin_is_served_normally(env, transport):
    """Storyboard ``error_compliance::supported_major_version``, on the wire.

    The guard against over-rejecting. Negotiation refuses a MISMATCHED pin; declaring a
    supported one explicitly is an ordinary request.
    """
    result = env.call_via(transport, brief="Display advertising", adcp_major_version=SUPPORTED_ADCP_MAJORS[0])

    assert not result.is_error, (
        f"[{transport.value}] pinning a supported major must be served, not refused: {result.wire_error_envelope}"
    )
    # The seeded product, not merely a non-None list: an empty result would satisfy
    # "did not refuse" while proving the request never reached the tool.
    assert [p.product_id for p in result.payload.products] == ["prod_versioned"], result.payload.products


@pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_each_pin_is_judged_independently(env, transport):
    """A supported major does not excuse an unsupported release.

    The two pins were read as ALTERNATIVES: the major check returned before the release
    was judged, so this exact request -- a release this build cannot serve, alongside a
    major it can -- was accepted and answered with products. Each pin the buyer SENDS is
    a constraint.
    """
    result = env.call_via(
        transport,
        brief="Version negotiation probe",
        adcp_version="99.0",
        adcp_major_version=SUPPORTED_ADCP_MAJORS[0],
    )

    assert result.is_error, (
        f"[{transport.value}] a supported major must not excuse an unsupported release; "
        f"got {getattr(result, 'wire_response', None) or result.payload!r}"
    )
    result.assert_wire_error("VERSION_UNSUPPORTED", recovery="correctable")


def test_the_refusal_names_the_majors_a_buyer_rejected_on_a_major_can_retry_with(env):
    """``supported_majors`` is declared on the details and was never populated.

    A buyer refused for ``adcp_major_version: 99`` was told only which RELEASES exist,
    which is not the field they sent. One transport is enough here: the details are built
    once, in ``negotiate_adcp_version``, and the transports only serialize them.
    """
    result = env.call_via(Transport.REST, brief="Version negotiation probe", adcp_major_version=99)

    details = result.wire_error_details("VERSION_UNSUPPORTED") or {}
    assert details.get("supported_versions") == SUPPORTED_ADCP_VERSIONS, details
    assert details.get("supported_majors") == SUPPORTED_ADCP_MAJORS, details
    # The pin the buyer sent, echoed back, so the answer is self-describing.
    assert details.get("adcp_major_version") == 99, details

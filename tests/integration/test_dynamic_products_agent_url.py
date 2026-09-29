"""What ``get_products`` hands the dynamic-variant generator as "our agent URL".

A signals agent records its deployments against a ``destination.agent_url``, which AdCP
3.1.1 declares ``"format": "uri"`` (``_schemas/3.1.1/core/destination.json``), and
``extract_activation_key`` picks our deployment by comparing that string to what we pass in.
So the value has to be the URL the agent card publishes — ``canonical_agent_url`` — and not
the bare ``virtual_host``, which carries no scheme and may carry a port.

A host can never equal a URI, so passing one made the match silently unreachable: every
signal fell through to the "first live deployment" fallback, which answers with the
activation key of whichever DSP the signals agent happened to list first. This grades the
value at the seam, and the tenant is stored with a port so a partial fix (adding a scheme
only) still fails.
"""

import pytest

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness import ProductEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

ORIGIN = "dyn-signals.example.com:8443"


@pytest.mark.requires_db
def test_the_variant_generator_is_handed_the_url_the_card_publishes(integration_db):
    with ProductEnv(tenant_id="dyn-t", principal_id="dyn-p", virtual_host=ORIGIN) as env:
        tenant = TenantFactory(tenant_id="dyn-t", virtual_host=ORIGIN)
        PrincipalFactory(tenant=tenant, principal_id="dyn-p")
        env.call_impl(brief="video inventory")

        # The literal, not ``canonical_agent_url(...)`` recomputed here: an expectation
        # derived from the same function it is grading cannot falsify.
        env.mock["dynamic_variants"].assert_called_once_with("dyn-t", "video inventory", f"https://{ORIGIN}")

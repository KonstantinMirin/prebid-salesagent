"""list_authorized_properties' wire response omits unset optional fields.

Regression for #1710 (PR #1868 review, salesagent-w02n.2): one of the 4
zero-BDD-coverage sites named in the PR review, with no live-dispatch wire
grading at all previously.

No pinned schema validates this response: ListAuthorizedPropertiesResponse
(src/core/schemas/_base.py) is a v2.4-shape response (publisher_domains:
list[str] + optional primary_channels/primary_countries/portfolio_description/
advertising_policies/last_updated/errors) -- there is no
list-authorized-properties-response.json in the pinned 3.1 tree (2.5 had one,
for a different response shape). Field-absence assertions carry the omission
obligation instead (schema=None).

Dispatched across all 3 wire transports the tool exposes (MCP/A2A/REST) --
CapabilitiesEnv-style, no Transport.IMPL exemption needed here either.
"""

from __future__ import annotations

import pytest

from tests.factories import PrincipalFactory, PublisherPartnerFactory, TenantFactory
from tests.harness.assertions import assert_wire_omits_unset
from tests.harness.authorized_properties import AuthorizedPropertiesEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_UNSET_FIELDS = [
    "primary_channels",
    "primary_countries",
    "portfolio_description",
    "advertising_policies",
    "last_updated",
    "errors",
]


@pytest.fixture
def authorized_properties_env(integration_db):
    with AuthorizedPropertiesEnv(tenant_id="wire-shape-properties", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="wire-shape-properties")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        # A verified publisher with no advertising_policy configured -- exercises
        # the "has publishers" branch (properties.py:141-155) where every optional
        # field besides publisher_domains stays unset.
        PublisherPartnerFactory(tenant=tenant, publisher_domain="example.com")
        yield env


@pytest.mark.parametrize("transport", [Transport.MCP, Transport.A2A, Transport.REST])
def test_authorized_properties_wire_omits_unset_optional_fields(authorized_properties_env, transport):
    """Every optional field left unset by the "has publishers, no policy" path is absent, never null."""
    result = authorized_properties_env.call_via(transport)
    assert_wire_omits_unset(
        result,
        schema=None,
        absent_paths=_UNSET_FIELDS,
        transport=transport,
    )

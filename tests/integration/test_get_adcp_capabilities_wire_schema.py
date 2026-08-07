"""get_adcp_capabilities' wire response omits unset optional fields and validates
against the pinned protocol/get-adcp-capabilities-response.json schema.

Regression for #1710 (PR #1868 review): capabilities.py's
media_buy field is built via ``MediaBuy(portfolio=..., features=..., execution=...)``
(src/core/tools/capabilities.py:250-254), leaving ``supported_pricing_models``
(and the sibling ``buying_modes``/``reporting_delivery_methods`` declarations)
unset -- the exact field #1710 cited as leaking as wire ``null`` on MCP via the
``ToolResult(structured_content=<raw model>)`` bypass (fixed in w02n.1's
mcp_result() helper). This file was previously the only one of the 4 zero-BDD-
coverage sites named in the PR review with no live-dispatch wire grading at all.

Dispatched across all 3 wire transports (MCP/A2A/REST) — this tool has no
Transport.IMPL-only exemption; REST is a GET with no body, unlike the
POST-based discovery routes.
"""

from __future__ import annotations

import pytest

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.assertions import assert_wire_omits_unset
from tests.harness.capabilities import CapabilitiesEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_RESPONSE_SCHEMA = "protocol/get-adcp-capabilities-response.json"


@pytest.fixture
def capabilities_env(integration_db):
    with CapabilitiesEnv(tenant_id="wire-schema-capabilities", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="wire-schema-capabilities")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        yield env


@pytest.mark.parametrize("transport", [Transport.MCP, Transport.A2A, Transport.REST])
def test_capabilities_wire_omits_supported_pricing_models(capabilities_env, transport):
    """media_buy.supported_pricing_models is unset -- must be absent, never null."""
    result = capabilities_env.call_via(transport)
    assert_wire_omits_unset(
        result,
        schema=_RESPONSE_SCHEMA,
        absent_paths=["media_buy.supported_pricing_models"],
        transport=transport,
    )

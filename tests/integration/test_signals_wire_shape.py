"""get_signals / activate_signal responses omit unset optional fields.

Regression for #1710 (PR #1868 review, salesagent-w02n.2). IMPORTANT FINDING:
get_signals and activate_signal are NOT registered as MCP tools
(src/core/main.py's _register_tool() calls have no entry for either), A2A
intentionally excludes signals (src/a2a_server/adcp_a2a_server.py:89,
"signals should come from dedicated signals agents", documented at
tests/integration/test_tool_registration.py:8), and no REST route exists.
Both functions are therefore unreachable on EVERY transport in production
today -- there is no live wire for a buyer to ever observe, and no
"live-dispatch" coverage is possible for this site (unlike the other 3
zero-BDD-coverage sites, which DO have a real wire). See salesagent-w02n.2
notes and the follow-up beads issue for whether this dead code should be
removed or wired to a transport.

These tests grade the typed model_dump() directly (same rationale as
test_get_products_wire_schema.py's IMPL-only test) as defense-in-depth at the
model layer -- catches the null-leak class if these tools are ever wired to a
transport, but is NOT wire-transport coverage.

get_signals: production never sets signal_ref on the mock signals it returns
(only the deprecated signal_id) -- signal_ref must be absent.

activate_signal: errors is always explicitly None on success, context is
unset when not passed in the request -- both must be absent.
"""

from __future__ import annotations

import pytest

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.signals import ActivateSignalEnv, GetSignalsEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.fixture
def get_signals_env(integration_db):
    with GetSignalsEnv(tenant_id="wire-shape-signals", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="wire-shape-signals")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        yield env


@pytest.fixture
def activate_signal_env(integration_db):
    with ActivateSignalEnv(tenant_id="wire-shape-activate-signal", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="wire-shape-activate-signal")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        yield env


def test_get_signals_impl_payload_omits_signal_ref(get_signals_env):
    result = get_signals_env.call_via(Transport.IMPL)
    assert result.is_success, f"get_signals failed: {result.error}"

    wire = result.payload.model_dump(mode="json")
    assert len(wire["signals"]) > 0, "expected non-empty signals list"
    assert "signal_ref" not in wire["signals"][0], (
        f"expected signals[0].signal_ref absent, got {wire['signals'][0].get('signal_ref')!r}"
    )


def test_activate_signal_impl_payload_omits_unset_fields(activate_signal_env):
    result = activate_signal_env.call_via(Transport.IMPL, signal_agent_segment_id="auto_intenders_q1_2025")
    assert result.is_success, f"activate_signal failed: {result.error}"

    wire = result.payload.model_dump(mode="json")
    for field in ("errors", "context"):
        assert field not in wire, f"expected '{field}' absent, got {wire.get(field)!r}"

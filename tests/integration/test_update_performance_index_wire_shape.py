"""update_performance_index's wire response omits unset optional fields.

Regression for #1710 (PR #1868 review, salesagent-w02n.2): one of the 4
zero-BDD-coverage sites named in the PR review, with no live-dispatch wire
grading at all previously.

No pinned schema validates this response: update_performance_index is not in
SKILL_TO_ADCP_TASK (tests/helpers/skill_to_adcp_task.py) and has no
corresponding task in the pinned AdCP 3.1 schema tree. The pinned
media-buy/provide-performance-feedback-response.json is a DIFFERENT task
(oneOf success[required]/errors[required] discriminated union) -- validating
against it would always fail on structural grounds unrelated to null-omission,
so this file intentionally does not attempt schema validation (schema=None).
This is a separate, pre-existing spec-grounding gap, out of scope here.

Dispatched across all 3 wire transports the tool exposes (MCP/A2A/REST); auth
is required (no anonymous access, unlike the discovery-skill sites).
"""

from __future__ import annotations

import pytest

from tests.factories import MediaBuyFactory, PrincipalFactory, TenantFactory
from tests.harness.assertions import assert_wire_omits_unset
from tests.harness.performance import PerformanceEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.fixture
def performance_env(integration_db):
    with PerformanceEnv(tenant_id="wire-shape-performance", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="wire-shape-performance")
        principal = PrincipalFactory(tenant=tenant, principal_id="test_principal")
        media_buy = MediaBuyFactory(tenant=tenant, principal=principal, media_buy_id="mb_perf_wire_shape")
        yield env, media_buy


@pytest.mark.parametrize("transport", [Transport.MCP, Transport.A2A, Transport.REST])
def test_update_performance_index_wire_omits_unset_context(performance_env, transport):
    """context is unset on this call -- must be absent from the wire, never null."""
    env, media_buy = performance_env
    result = env.call_via(
        transport,
        media_buy_id=media_buy.media_buy_id,
        performance_data=[{"product_id": "prod_1", "performance_index": 1.0}],
    )
    assert_wire_omits_unset(
        result,
        schema=None,
        absent_paths=["context"],
        transport=transport,
    )

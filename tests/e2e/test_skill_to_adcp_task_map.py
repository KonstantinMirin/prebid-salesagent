"""Pins the invariants a single shared skill->AdCP-task map must satisfy.

(PR #1838 review R1-10 measurement, ChrisHuie): two
independent copies of the skill-name -> AdCP-task-name map exist —
``A2AAdCPValidator.SKILL_TO_SCHEMA_MAP`` in
tests/integration/test_a2a_skill_invocation.py and the local ``skill_to_schema``
dict inside ``A2AAdCPComplianceClient.validate_skill_response`` in
tests/e2e/test_a2a_adcp_compliance.py. They diverge (e.g. ``approve_creative``
resolves to ``"approve-creative"`` in one and ``None`` in the other), and
neither is validated against the pinned index, so an entry can claim a schema
exists when it does not — the validation call for that skill then silently
grades nothing.

These tests exercise both maps' real behavior (not source text) and will keep
passing once both files are migrated to import one shared, index-validated
map.
"""

from __future__ import annotations

import pytest

from tests.e2e.adcp_schema_validator import AdCPSchemaValidator
from tests.e2e.test_a2a_adcp_compliance import A2AAdCPComplianceClient
from tests.helpers.skill_to_adcp_task import SKILL_TO_ADCP_TASK
from tests.integration.test_a2a_skill_invocation import A2AAdCPValidator


def test_map_a_is_the_shared_map_not_a_second_copy():
    """A2AAdCPValidator must import the shared map, not hand-maintain its own equal-by-coincidence copy."""
    assert A2AAdCPValidator.SKILL_TO_SCHEMA_MAP is SKILL_TO_ADCP_TASK


async def _map_b_resolution(skill_name: str) -> str | None:
    """What tests/e2e/test_a2a_adcp_compliance.py's map resolves *skill_name* to."""
    client = A2AAdCPComplianceClient(a2a_url="http://test.invalid", auth_token="test")
    result = await client.validate_skill_response(skill_name, {})
    return result["schema_tested"]


def _map_a_resolution(skill_name: str) -> str | None:
    """What tests/integration/test_a2a_skill_invocation.py's map resolves *skill_name* to."""
    return A2AAdCPValidator.SKILL_TO_SCHEMA_MAP.get(skill_name)


@pytest.mark.asyncio
async def test_skill_to_task_maps_agree_on_every_shared_skill():
    """The two independent maps must not diverge on a skill both of them cover."""
    shared_skills = set(A2AAdCPValidator.SKILL_TO_SCHEMA_MAP) & {
        "get_products",
        "create_media_buy",
        "add_creative_assets",
        "approve_creative",
        "get_media_buy_status",
        "optimize_media_buy",
    }
    divergent = []
    for skill in sorted(shared_skills):
        map_a = _map_a_resolution(skill)
        map_b = await _map_b_resolution(skill)
        if map_a != map_b:
            divergent.append(f"{skill}: map_a={map_a!r} map_b={map_b!r}")

    assert not divergent, f"skill->task maps disagree: {divergent}"


@pytest.mark.asyncio
async def test_skill_to_task_map_non_none_entries_resolve_in_pinned_index():
    """Every non-None mapped task name must actually resolve against the pinned index.

    A map entry that claims a schema exists but doesn't resolve is worse than
    a missing entry: it makes validate_response silently raise/skip instead of
    the caller ever knowing no contract was checked.
    """
    async with AdCPSchemaValidator() as validator:
        unresolved = []
        for skill, task_name in A2AAdCPValidator.SKILL_TO_SCHEMA_MAP.items():
            if task_name is None:
                continue
            if await validator._find_schema_ref_for_task(task_name, "response") is None:
                unresolved.append(f"map_a.{skill} -> {task_name!r}")

        for skill in ("get_products", "create_media_buy", "add_creative_assets"):
            task_name = await _map_b_resolution(skill)
            if task_name is None:
                continue
            if await validator._find_schema_ref_for_task(task_name, "response") is None:
                unresolved.append(f"map_b.{skill} -> {task_name!r}")

        assert not unresolved, f"mapped task names that don't resolve in the pinned index: {unresolved}"

#!/usr/bin/env python3
"""
E2E tests for A2A protocol compliance with AdCP schemas.

These tests validate that our A2A server correctly accepts and processes
requests according to the official AdCP specification, catching issues like:
- Incorrect parameter names (e.g., 'updates' vs 'packages')
- Missing required fields
- Schema mismatches between A2A layer and core implementation

CRITICAL: These tests use real AdCP schemas and validate the full request/response
cycle to ensure protocol compliance.

NOTE: These tests require the external AdCP schema server (adcontextprotocol.org)
to be available. If the server is unreachable (e.g., HTTP 5xx errors), tests will
be skipped rather than failing, since external service availability is outside
our control.
"""

import pytest

from tests.helpers.adcp_schema_validator import AdCPSchemaValidator
from tests.helpers.skill_to_adcp_task import SKILL_TO_ADCP_TASK


class TestA2AProtocolCompliance:
    """Test A2A protocol compliance with official AdCP schemas."""

    @pytest.mark.asyncio
    async def test_update_media_buy_request_schema_structure(self):
        """
        Test that update_media_buy schema uses 'packages' field.

        This test validates:
        1. Schema uses 'packages' field (not 'updates')
        2. Schema structure matches AdCP v2.0+ spec

        Regression test for: A2A server expecting 'updates' instead of 'packages'
        """
        async with AdCPSchemaValidator() as validator:
            # Load official AdCP schema
            schema = await validator.get_schema("media-buy/update-media-buy-request.json")

            # Verify schema uses 'packages' field (not 'updates')
            assert "packages" in schema["properties"], "AdCP schema should define 'packages' field"
            assert "updates" not in schema["properties"], "AdCP schema should NOT have legacy 'updates' field"

            # Verify media_buy_id is required (spec uses required array, not oneOf)
            assert "media_buy_id" in schema.get("properties", {}), "Schema should define media_buy_id"
            assert "media_buy_id" in schema.get("required", []), "media_buy_id should be required"

    # test_update_media_buy_schema_validates_correctly removed:
    # Validated a hardcoded request dict against adcontextprotocol.org/schemas/latest/...
    # Did not exercise any sales agent behavior — purely fixture vs. upstream spec drift.
    # Real schema conformance is covered by tests/unit/test_adcp_contract.py against
    # the pinned adcp library version. See PR #1186 notes.

    # Skills mapped to None in SKILL_TO_ADCP_TASK (no task in the pinned
    # index yet) that we still actively watch for a newly-added schema.
    # Shrink-only: when the spec adds a schema for one of these, remove it
    # here — do not add new entries (add the skill to SKILL_TO_ADCP_TASK
    # with its real task name instead).
    _KNOWN_MISSING_SCHEMA_SKILLS = frozenset(skill for skill, task in SKILL_TO_ADCP_TASK.items() if task is None)

    @pytest.mark.asyncio
    async def test_all_adcp_skills_have_schemas(self):
        """
        Verify that all AdCP-compliant skills have corresponding schemas.

        This prevents regressions where we add new skills but forget to:
        1. Add them to the schema validation map
        2. Create tests for them
        3. Validate their request/response formats

        Skills and their canonical task names both come from
        SKILL_TO_ADCP_TASK (tests/helpers/skill_to_adcp_task.py) — the single
        shared source, not a locally hand-typed skill set combined with a
        skill.replace("_", "-") derivation (R3-28, salesagent-1zq3.28: that
        third derivation had already diverged from the shared map on 6
        entries). Uses AdCPSchemaValidator._find_schema_ref_for_task
        (searches every index section) rather than a hardcoded 'media-buy/'
        path, so a skill whose schema lives outside media-buy (e.g.
        sync_creatives, under creative/) is correctly found instead of
        silently treated as missing.
        """
        async with AdCPSchemaValidator() as validator:
            missing_schemas = []
            newly_resolved = []

            for skill, mapped_task_name in SKILL_TO_ADCP_TASK.items():
                task_name = mapped_task_name or skill.replace("_", "-")
                schema_ref = await validator._find_schema_ref_for_task(task_name, "request")

                if skill in self._KNOWN_MISSING_SCHEMA_SKILLS:
                    if schema_ref is not None:
                        newly_resolved.append(skill)
                    continue

                if schema_ref is None:
                    missing_schemas.append(skill)
                else:
                    schema = await validator.get_schema(schema_ref)
                    assert schema is not None, f"Schema resolved but failed to load for {skill}"

            assert not missing_schemas, (
                f"AdCP skill(s) have no request schema anywhere in the pinned index: {missing_schemas}"
            )
            assert not newly_resolved, (
                f"Skill(s) in _KNOWN_MISSING_SCHEMA_SKILLS now HAVE a schema — shrink the allowlist: {newly_resolved}"
            )

    @pytest.mark.asyncio
    async def test_get_media_buy_delivery_request_schema(self):
        """
        Test that get_media_buy_delivery uses correct parameter names.

        Validates the request accepts AdCP-compliant field names.
        """
        async with AdCPSchemaValidator() as validator:
            schema = await validator.get_schema("media-buy/get-media-buy-delivery-request.json")

            # Verify expected fields from AdCP spec
            assert "media_buy_ids" in schema["properties"], "Should accept media_buy_ids (plural) per AdCP spec"
            assert "status_filter" in schema["properties"], "Should accept status_filter for filtering by status"

            # Validate a minimal valid request
            valid_request = {"media_buy_ids": ["mb_1", "mb_2"]}

            try:
                await validator.validate_request(task_name="get-media-buy-delivery", request_data=valid_request)
                validation_passed = True
            except Exception as e:
                validation_passed = False
                error_msg = str(e)

            assert validation_passed, f"Valid request should pass: {error_msg if not validation_passed else ''}"

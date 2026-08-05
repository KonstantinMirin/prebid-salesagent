"""MCP wire shape for sync_creatives: changes/warnings must be arrays, never null.

Regression for PR #1567 round-2 blocker 3 (adcp bump — adcp 5.7->6.6 bump, round-2 review
blocker 3). adcp 6.6 re-added ``changes``/``warnings`` to the library
SyncCreativeResult parent with ``None`` defaults, and the bump switched our
subclass from local declarations (which emitted ``[]`` under 5.7) to
inheritance. On A2A/REST the custom ``model_dump()`` override strips the empty
values, but the MCP transport serializes ``structured_content`` via pydantic's
``to_jsonable_python``, which BYPASSES ``model_dump`` overrides — so the MCP
wire emits ``"changes": null`` / ``"warnings": null``.

Spec grounding (pinned 3.1.1, the installed adcp SDK's
creative/sync-creatives-response.json, read via tests.helpers.pinned_schema): the
per-creative ``changes`` and ``warnings`` properties are typed ``array`` —
``null`` is not a valid value; the field must be a list or absent.

This file is also the MCP-wire jsonschema oracle the round-2 review flagged as
missing: existing sync_creatives tests validate the typed model/payload, not
the actual MCP wire bytes. ``result.wire_response`` here IS the real
``ToolResult.structured_content`` captured by the harness MCP client.
"""

from __future__ import annotations

import pytest

from tests.factories.creative_asset import CreativeAssetFactory
from tests.harness import CreativeSyncEnv, Transport
from tests.harness.assertions import assert_wire_omits_unset

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def _sync_one_creative_via_mcp():
    with CreativeSyncEnv() as env:
        env.setup_default_data()
        creative = CreativeAssetFactory(
            creative_id="c_mcp_wire_shape",
            name="MCP Wire Shape Creative",
        )
        result = env.call_via(Transport.MCP, creatives=[creative])
    assert result.is_success, f"Expected success but got error: {result.error}"
    assert result.wire_response is not None, "MCP dispatch must stash the real structured_content wire"
    return result


def test_mcp_wire_changes_and_warnings_are_never_null(integration_db):
    """Per-creative changes/warnings/errors on the MCP wire are lists or absent, never null.

    All three fields were redeclared with default_factory=list in creative.py for the
    same structured_content null risk (PR #1567 round-3: the oracle must cover errors
    too — reverting only the errors redeclaration kept this test green before).
    Mutation check: revert any of the three redeclarations to inherit the parent's
    None default -> this test goes red on that field.
    """
    wire = _sync_one_creative_via_mcp().wire_response
    creatives = wire.get("creatives")
    assert isinstance(creatives, list) and creatives, f"MCP wire must carry the creatives array, got {creatives!r}"
    for i, item in enumerate(creatives):
        for field in ("changes", "warnings", "errors"):
            if field in item:
                assert isinstance(item[field], list), (
                    f"creatives[{i}].{field} must be an array on the MCP wire (spec 3.1.1 "
                    f"sync-creatives-response.json types it array), got {item[field]!r}"
                )


def test_mcp_wire_validates_against_pinned_response_schema(integration_db):
    """The MCP structured_content validates against the pinned 3.1.1 response schema.

    Validates the REAL wire bytes with no null-stripping. Fixed (GH #1710):
    ``sync_creatives`` MCP wrapper used to hand the raw pydantic
    ``SyncCreativesResponse`` to ``ToolResult(structured_content=...)``, which FastMCP
    serializes via ``pydantic_core.to_jsonable_python`` — bypassing both
    ``model_dump()`` overrides (Pattern #4 nested serialization) and
    ``AdCPBaseModel``'s ``exclude_none=True`` default, so spec-optional fields left
    unset (e.g. per-creative ``status``, ``adcp_version``) serialized as invalid
    ``null`` instead of being omitted. The wrapper now passes
    ``response.model_dump(mode="json")`` (a plain dict) so the same exclude-none/
    nested-serialization behavior A2A/REST already had applies on MCP too.
    """
    result = _sync_one_creative_via_mcp()
    assert_wire_omits_unset(result, schema="sync-creatives-response.json", absent_paths=[], transport=Transport.MCP)

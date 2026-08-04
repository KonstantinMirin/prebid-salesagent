"""Unit tests for the creative agent's MCP tool-result parser.

The fallback classes that used to live here (``TestStructuredContentFallbackTrigger``,
``TestSchemaValidationFailureTriggersFallback``) tested a mechanism that no
longer exists: the adcp SDK's own strict Pydantic parsing of
``list_creative_formats`` responses, which sometimes rejected a TextContent-only
reply and triggered a fallback to the raw-MCP path. salesagent-4n88 removed the
SDK client (``ADCPMultiAgentClient``) from the OPERATOR agent path entirely —
routing it through the guarded MCP seam instead — so there is no SDK-side
strict parser left to reject anything, and therefore nothing left to trigger a
fallback FROM. ``_parse_mcp_tool_result``'s own tolerant, per-format validation
(covered below) is now the ONLY ingestion path, for both the operator method
and the counterparty raw-MCP method.

Fixes: salesagent-c6i
"""

import pytest

from src.core.creative_agent_registry import CreativeAgentRegistry
from src.core.exceptions import AdCPAdapterError


@pytest.fixture
def registry():
    return CreativeAgentRegistry()


SAMPLE_FORMATS_JSON = '{"formats": [{"format_id": {"agent_url": "https://creative.example.com", "id": "display_image"}, "name": "Display Image", "type": "display"}]}'


class TestParseMcpToolResult:
    """Test the MCP tool result parser."""

    def test_parses_text_content(self, registry):
        """Content with text type → parsed formats."""
        import logging

        result = {"content": [{"type": "text", "text": SAMPLE_FORMATS_JSON}]}
        formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert len(formats) == 1
        assert formats[0].name == "Display Image"

    def test_no_text_content_raises(self, registry):
        """Content with no text items → raises AdCPAdapterError.

        Fix for salesagent-kwws: silent return [] masked failures as 'no formats'.
        """
        import logging

        result = {"content": [{"type": "image", "data": "..."}]}
        with pytest.raises(AdCPAdapterError, match="No text content"):
            registry._parse_mcp_tool_result(result, logging.getLogger())

    def test_empty_content_raises(self, registry):
        """Empty content list → raises AdCPAdapterError.

        Fix for salesagent-kwws: silent return [] masked failures as 'no formats'.
        """
        import logging

        result = {"content": []}
        with pytest.raises(AdCPAdapterError, match="No text content"):
            registry._parse_mcp_tool_result(result, logging.getLogger())


def _mcp_text_result(payload: dict) -> dict:
    """Wrap a list_creative_formats payload as an MCP tools/call TextContent result."""
    import json

    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


# Two fully-known formats the pinned adcp library understands completely.
_KNOWN_FORMAT_A = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"},
    "name": "Medium Rectangle",
    "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
}
_KNOWN_FORMAT_B = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_728x90_image"},
    "name": "Leaderboard",
    "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
}
# AdCP-additive asset_type the canonical reference agent serves but the pinned
# (and latest) adcp closed Literal union does NOT model. This is the exact
# production defect class from salesagent-w8yn.
_ADDITIVE_FORMAT = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "tracking_pixel"},
    "name": "Tracking Pixel",
    "assets": [{"item_type": "individual", "asset_id": "pixel", "asset_type": "pixel_tracker", "required": True}],
}


class TestTolerantPerFormatIngestion:
    """Hermetic regression for salesagent-w8yn (Postel / asymmetric strictness).

    One unknown AdCP-additive asset_type must NOT nuke the whole
    list_creative_formats response. Fully-understood formats are returned;
    formats whose ONLY problem is an unrecognized additive asset_type are
    passed through (the unknown additive asset_type is tolerated) with ONE
    aggregated WARNING; genuinely malformed formats still fail LOUD.
    """

    def test_unknown_additive_asset_type_passes_through(self, registry, caplog):
        """Mixed batch: 2 known + 1 additive(pixel_tracker) → all 3 returned.

        SDK 5.7 accepts unknown asset_types as UnknownFormatAsset instead of
        rejecting them. This is better Postel's law behavior — unknown types
        are preserved, not dropped.
        """
        import logging

        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, _ADDITIVE_FORMAT, _KNOWN_FORMAT_B]})

        with caplog.at_level(logging.WARNING):
            formats = registry._parse_mcp_tool_result(result, logging.getLogger())

        ids = sorted(f.format_id.id for f in formats)
        assert ids == [
            "display_300x250_image",
            "display_728x90_image",
            "tracking_pixel",
        ], "All formats including additive-asset_type should pass through"

    def test_all_known_formats_pass_through_unchanged(self, registry):
        """No additive types → all formats returned, zero warnings (no behavior change)."""
        import logging

        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, _KNOWN_FORMAT_B]})
        formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert sorted(f.format_id.id for f in formats) == ["display_300x250_image", "display_728x90_image"]

    def test_genuinely_malformed_format_still_fails_loud(self, registry):
        """A real schema bug (not an additive enum) must NOT be masked — fail loud."""
        import logging

        malformed = {
            "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "broken"},
            "name": 12345,  # wrong type — a genuine contract violation, not additive growth
            "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
        }
        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, malformed]})
        with pytest.raises(Exception, match="(?i)valid"):
            registry._parse_mcp_tool_result(result, logging.getLogger())

    def test_additive_type_with_structurally_broken_asset_fails_loud(self, registry):
        """Unknown asset_type AND a structurally broken asset → not purely additive → fail loud."""
        import logging

        broken_additive = {
            "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "broken_pixel"},
            "name": "Broken Pixel",
            # asset_type unknown AND asset_id/required missing — substituting a known
            # asset_type would STILL fail, so this is not benign additive growth.
            "assets": [{"item_type": "individual", "asset_type": "pixel_tracker"}],
        }
        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, broken_additive]})
        with pytest.raises(Exception, match="(?i)valid"):
            registry._parse_mcp_tool_result(result, logging.getLogger())

    def test_all_formats_additive_passes_through(self, registry, caplog):
        """SDK 5.7 accepts additive-only batch via UnknownFormatAsset — returns the format."""
        import logging

        result = _mcp_text_result({"formats": [_ADDITIVE_FORMAT]})
        with caplog.at_level(logging.WARNING):
            formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert len(formats) == 1
        assert formats[0].format_id.id == "tracking_pixel"

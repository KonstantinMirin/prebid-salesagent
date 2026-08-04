"""Regression tests for salesagent-kwws: silent return [] masks agent failures.

A creative-agent fetch failure must surface as an error in
``FormatFetchResult.errors``, never as a silently empty format list — that
distinction is what lets ``products.py`` tell "agent up, genuinely 0 formats"
apart from "agent unreachable" and trigger graceful degradation accordingly.

``TestFetchFormatsAnomalousStatusesMustRaise`` (anomalous ``status`` values on
a mocked adcp SDK response) was retired by salesagent-4n88: the OPERATOR agent
path no longer goes through ``adcp.ADCPMultiAgentClient`` at all — there is no
SDK-shaped ``status`` field to be anomalous. The invariant this file guards —
a malformed/unparseable MCP response must raise, not silently validate into
"no formats" — is now enforced by ``_parse_mcp_tool_result`` (covered in
``test_creative_agent_fallback.py::TestParseMcpToolResult``), the one parser
both the operator and counterparty fetch paths share.

Bug: prebid/salesagent#1136
Beads: salesagent-kwws
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.creative_agent_registry import CreativeAgentRegistry


@pytest.fixture
def registry():
    return CreativeAgentRegistry()


class TestListAllFormatsErrorPropagation:
    """End-to-end: a failed agent fetch must produce an error in FormatFetchResult.

    This is the critical integration point — when the operator fetch raises,
    list_all_formats_with_errors must record it as an error so that
    products.py can trigger graceful degradation.
    """

    @pytest.mark.asyncio
    async def test_operator_fetch_failure_produces_error(self, registry, monkeypatch):
        """When the guarded MCP seam fails, the failure lands in FormatFetchResult.errors.

        Not the seam's business (asend/create_mcp_client's own retry/backoff is
        graded elsewhere): what's graded here is that list_all_formats_with_errors
        turns a raised exception into a recorded error rather than an empty
        format list — a failed fetch must never look like "agent up, no formats".
        """
        monkeypatch.delenv("ADCP_TESTING", raising=False)

        from src.core.creative_agent_registry import CreativeAgent

        agent = CreativeAgent(agent_url="https://creative.example.com", name="test-agent")
        monkeypatch.setattr(registry, "_get_tenant_agents", lambda tenant_id=None: [agent])

        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
        client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("src.core.creative_agent_registry.create_mcp_client", return_value=client_cm):
            result = await registry.list_all_formats_with_errors(tenant_id="test")

        assert len(result.errors) > 0, (
            "FormatFetchResult.errors must be non-empty when the operator fetch fails. "
            "Silent return [] masks the failure as 'agent up, no formats'."
        )
        assert len(result.formats) == 0

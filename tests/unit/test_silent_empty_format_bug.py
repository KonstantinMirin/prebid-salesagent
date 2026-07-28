"""Regression tests for salesagent-kwws: silent return [] masks agent failures.

_fetch_formats_from_agent and _fetch_formats_raw_mcp have paths that silently
return [] without raising. list_all_formats_with_errors then records no error,
producing FormatFetchResult(formats=[], errors=[]) — which products.py treats
as "agent up, genuinely 0 formats" and rejects all submitted format IDs.

These tests demonstrate the bug: each silent-[] path should raise so that
list_all_formats_with_errors captures it as an error and triggers graceful
degradation.

Bug: prebid/salesagent#1136
Beads: salesagent-kwws
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.creative_agent_registry import CreativeAgent, CreativeAgentRegistry
from src.core.exceptions import AdCPAdapterError
from src.core.security.outbound_http import OutboundDeliveryFailed


@pytest.fixture
def registry():
    return CreativeAgentRegistry()


@pytest.fixture
def agent():
    return CreativeAgent(
        agent_url="https://creative.example.com",
        name="test-agent",
        auth={"type": "token", "credentials": "test-token"},
        auth_header="x-test-auth",
    )


class TestFetchFormatsAnomalousStatusesMustRaise:
    """_fetch_formats_from_agent must raise (not return []) for anomalous statuses.

    When these paths silently return [], list_all_formats_with_errors records
    no error, and products.py rejects all format IDs.
    """

    @pytest.mark.asyncio
    async def test_completed_with_data_none_raises(self, registry, agent):
        """status=completed but data=None is anomalous — must raise, not return []."""
        mock_result = MagicMock()
        mock_result.status = "completed"
        mock_result.data = None

        mock_agent_proxy = MagicMock()
        mock_agent_proxy.list_creative_formats = AsyncMock(return_value=mock_result)
        mock_client = MagicMock()
        mock_client.agent.return_value = mock_agent_proxy

        with pytest.raises(AdCPAdapterError):
            await registry._fetch_formats_from_agent(mock_client, agent)

    @pytest.mark.asyncio
    async def test_submitted_status_raises(self, registry, agent):
        """status=submitted is not expected for list_creative_formats — must raise."""
        mock_result = MagicMock()
        mock_result.status = "submitted"
        mock_result.submitted = None

        mock_agent_proxy = MagicMock()
        mock_agent_proxy.list_creative_formats = AsyncMock(return_value=mock_result)
        mock_client = MagicMock()
        mock_client.agent.return_value = mock_agent_proxy

        with pytest.raises(AdCPAdapterError):
            await registry._fetch_formats_from_agent(mock_client, agent)

    @pytest.mark.asyncio
    async def test_unexpected_status_raises(self, registry, agent):
        """Unexpected status (e.g. 'working') must raise, not return []."""
        mock_result = MagicMock()
        mock_result.status = "working"

        mock_agent_proxy = MagicMock()
        mock_agent_proxy.list_creative_formats = AsyncMock(return_value=mock_result)
        mock_client = MagicMock()
        mock_client.agent.return_value = mock_agent_proxy

        with pytest.raises(AdCPAdapterError):
            await registry._fetch_formats_from_agent(mock_client, agent)


class TestListAllFormatsErrorPropagation:
    """End-to-end: anomalous responses must produce errors in FormatFetchResult.

    This is the critical integration point — when _fetch_formats_from_agent
    raises, list_all_formats_with_errors must record it as an error so that
    products.py can trigger graceful degradation.
    """

    @pytest.mark.asyncio
    async def test_raw_fallback_failure_produces_error(self, registry, agent, monkeypatch):
        """When raw MCP fallback returns unparseable response, error is recorded."""
        monkeypatch.delenv("ADCP_TESTING", raising=False)

        # Simulate: SDK returns FAILED with structuredContent error → raw fallback → unparseable
        mock_result = MagicMock()
        mock_result.status = "failed"
        mock_result.error = "MCP tool list_creative_formats did not return structuredContent"
        mock_result.message = None

        mock_agent_proxy = MagicMock()
        mock_agent_proxy.list_creative_formats = AsyncMock(return_value=mock_result)
        mock_client = MagicMock()
        mock_client.agent.return_value = mock_agent_proxy

        monkeypatch.setattr(registry, "_get_tenant_agents", lambda tenant_id=None: [agent])

        # The raw fallback goes through the egress seam now, so the failure is
        # injected there rather than at a transport this code no longer touches.
        # What is graded is unchanged and is not the seam's business: a failed
        # fetch must arrive in FormatFetchResult.errors rather than as an empty
        # format list, because products.py keys graceful degradation off it.
        async def _seam_fails(*args, **kwargs):
            raise OutboundDeliveryFailed(attempts=3, last_status=503)

        with (
            patch.object(registry, "_build_adcp_client", return_value=mock_client),
            patch("src.core.creative_agent_registry.asend", _seam_fails),
        ):
            result = await registry.list_all_formats_with_errors(tenant_id="test")

        assert len(result.errors) > 0, (
            "FormatFetchResult.errors must be non-empty when raw fallback fails to parse response. "
            "Silent return [] masks the failure as 'agent up, no formats'."
        )
        assert len(result.formats) == 0

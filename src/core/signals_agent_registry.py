"""Signals Agent Registry for upstream signals discovery integration.

This module provides:
1. Signals agent registry (tenant-specific agents)
2. Dynamic signals discovery via AdCP library
3. Multi-agent support for different signals providers

Architecture:
- No default agent (tenant-specific only)
- Tenant agents: Configured in signals_agents database table
- Signals resolution: Query agents via adcp library, handle responses

Schema Version: AdCP v2.2.0
- Uses signal_spec (not brief from v1)
- Uses deliver_to.platforms as array of strings ["all"] (not single string "all")
- Supports custom auth headers via auth_header parameter

Security:
- Auth credentials stored in database (tenant-specific)
- Custom auth headers supported (e.g., Authorization, x-api-key)
- Bearer token format: "Bearer {token}"
- Token format: "{token}"

Migration Note: Now uses official `adcp` library (v1.0.1) instead of custom MCP client.
- ~100 lines of custom code replaced with official library
- Custom auth headers now fully supported (was critical blocker)
- Maintains backward compatibility with existing API
"""

import logging
from dataclasses import dataclass
from typing import Any

from adcp.types import GetSignalsResponse as LibraryGetSignalsResponse
from pydantic import ValidationError

from src.core.exceptions import AdCPConfigurationError
from src.core.helpers.mcp_seam_error_mapping import raise_mapped_mcp_error
from src.core.helpers.mcp_tool_payload import extract_tool_payload
from src.core.helpers.outbound_error_mapping import raise_mapped_outbound_error
from src.core.schemas import GetSignalsRequest
from src.core.security.outbound_http import OperatorEndpoint, OutboundError
from src.core.utils.mcp_client import MCPCompatibilityError, MCPConnectionError, create_mcp_client

logger = logging.getLogger(__name__)


@dataclass
class SignalsAgent:
    """Represents a signals discovery agent that provides product enhancement via signals.

    Note: priority, max_signal_products, and fallback_to_database are configured per-product,
    not per-agent.
    """

    agent_url: str
    name: str
    enabled: bool = True
    auth: dict[str, Any] | None = None  # Optional auth config for private agents
    auth_header: str | None = None  # HTTP header name for auth (e.g., "Authorization", "x-api-key")
    forward_promoted_offering: bool = True
    timeout: int = 30


class SignalsAgentRegistry:
    """Registry of signals discovery agents with dynamic discovery.

    Usage:
        registry = SignalsAgentRegistry()

        # Get signals from all agents
        signals = await registry.get_signals(
            brief="automotive targeting",
            tenant_id="tenant_123",
            promoted_offering="Tesla Model 3"
        )
    """

    def __init__(self):
        """Initialize registry."""
        pass  # No cache needed - adcp library handles connection pooling

    def _get_tenant_agents(self, tenant_id: str) -> list[SignalsAgent]:
        """Get list of signals agents for a tenant.

        Returns:
            List of SignalsAgent instances (tenant-specific only)
        """
        agents = []

        # Load tenant-specific agents from database
        from sqlalchemy import select

        from src.core.database.database_session import get_db_session
        from src.core.database.models import SignalsAgent as SignalsAgentModel

        with get_db_session() as session:
            stmt = select(SignalsAgentModel).filter_by(tenant_id=tenant_id, enabled=True)
            db_agents = session.scalars(stmt).all()

            for db_agent in db_agents:
                # Parse auth credentials if present
                auth = None
                if db_agent.auth_type and db_agent.auth_credentials:
                    auth = {
                        "type": db_agent.auth_type,
                        "credentials": db_agent.auth_credentials,
                    }

                agents.append(
                    SignalsAgent(
                        agent_url=db_agent.agent_url,
                        name=db_agent.name,
                        enabled=db_agent.enabled,
                        auth=auth,
                        auth_header=db_agent.auth_header,
                        forward_promoted_offering=db_agent.forward_promoted_offering,
                        timeout=db_agent.timeout,
                    )
                )

        # Sort by name for consistent ordering
        agents.sort(key=lambda a: a.name)
        return [a for a in agents if a.enabled]

    async def _fetch_signals_operator(self, agent: SignalsAgent, brief: str) -> list[dict[str, Any]]:
        """Fetch signals from an OPERATOR-configured signals agent, through the guarded MCP seam.

        Routes through ``create_mcp_client`` — a real MCP handshake, IP-pinned,
        redirect-refusing — rather than ``adcp.ADCPMultiAgentClient``, whose own
        httpx stack no egress policy of ours could reach (adcp 6.6.0 exposes no
        transport injection point; upstream adcp-client-python#1004). Closes the
        gap tracked by salesagent-4n88. Signals agents are ALWAYS
        operator-configured (tenant DB rows) — there is no counterparty-supplied
        signals URL, so every call here takes this path.

        The MCP protocol path only ever returns COMPLETED or FAILED (never
        SUBMITTED — that status exists in the adcp SDK's abstraction for other
        protocols, not for a synchronous MCP tool call), so there is no webhook/
        async branch to preserve here.

        Args:
            agent: SignalsAgent to query
            brief: Search brief/query (mapped onto AdCP's ``signal_spec``)

        Returns:
            List of signal dicts from the agent
        """
        import time

        start_time = time.time()

        request = GetSignalsRequest(signal_spec=brief)
        args = request.model_dump(mode="json", exclude_none=True)

        logger.info(f"[TIMING] Calling agent {agent.name}, brief: {brief[:50]}...")
        try:
            async with create_mcp_client(
                agent_url=agent.agent_url,
                auth=agent.auth,
                auth_header=agent.auth_header,
                timeout=agent.timeout,
            ) as client:
                result = await client.call_tool("get_signals", args)
            payload = extract_tool_payload(result)
        except OutboundError as exc:
            raise_mapped_outbound_error(exc, provenance=OperatorEndpoint(f"signals agent {agent.name}"), logger=logger)
        except (MCPConnectionError, MCPCompatibilityError) as exc:
            raise_mapped_mcp_error(exc, agent_label=f"signals agent {agent.name}", logger=logger)

        if not payload:
            # An empty payload means neither structured_content nor a TextContent
            # block carried anything parseable. GetSignalsResponse.model_validate({})
            # would otherwise validate CLEANLY with signals=None — every field is
            # optional — silently producing signals=[] and masking a genuine
            # agent failure as "agent up, 0 signals" (salesagent-9eu class bug).
            raise AdCPConfigurationError(f"No parseable content in get_signals response from {agent.name}")
        try:
            parsed = LibraryGetSignalsResponse.model_validate(payload)
        except ValidationError as e:
            raise AdCPConfigurationError(f"Signals agent {agent.name} returned an invalid response") from e

        signals = parsed.signals or []
        total_duration = time.time() - start_time
        logger.info(f"[TIMING] Got {len(signals)} signals in {total_duration:.2f}s")
        return [signal if isinstance(signal, dict) else signal.model_dump(mode="json") for signal in signals]

    async def get_signals(
        self,
        brief: str,
        tenant_id: str,
        principal_id: str | None = None,
        context: dict[str, Any] | None = None,
        principal_data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Get signals from all registered agents for a tenant.

        Args:
            brief: Search brief/query
            tenant_id: Tenant identifier
            principal_id: Optional principal identifier
            context: Optional context data (may include promoted_offering)
            principal_data: Optional principal information

        Returns:
            List of all signal objects across all agents
        """
        agents = self._get_tenant_agents(tenant_id)
        all_signals: list[dict[str, Any]] = []

        logger.info(f"get_signals: Found {len(agents)} agents for tenant {tenant_id}")

        if not agents:
            return all_signals

        for agent in agents:
            logger.info(f"get_signals: Fetching from {agent.agent_url}")
            try:
                signals = await self._fetch_signals_operator(agent, brief=brief)
                logger.info(f"get_signals: Got {len(signals)} signals from {agent.agent_url}")
                all_signals.extend(signals)
            except Exception as e:
                # Log error but continue with other agents (graceful degradation)
                logger.error(f"Failed to fetch signals from {agent.agent_url}: {e}", exc_info=True)
                continue

        logger.info(f"get_signals: Returning {len(all_signals)} total signals")
        return all_signals

    async def test_connection(
        self, agent_url: str, auth: dict[str, Any] | None = None, auth_header: str | None = None
    ) -> dict[str, Any]:
        """Test connection to a signals agent.

        Args:
            agent_url: URL of the signals agent
            auth: Optional authentication configuration
            auth_header: Optional custom auth header name

        Returns:
            dict with success status and message/error
        """
        try:
            # Create test agent config
            test_agent = SignalsAgent(
                agent_url=agent_url,
                name="Test Agent",
                enabled=True,
                auth=auth,
                auth_header=auth_header,
                timeout=30,
            )

            signals = await self._fetch_signals_operator(test_agent, brief="test")

            return {
                "success": True,
                "message": "Successfully connected to signals agent",
                "signal_count": len(signals),
            }

        except AdCPConfigurationError as e:
            # Everything the operator can fix by repointing or re-crediting this
            # deployment. CONFIGURATION_ERROR now covers THREE causes that used to
            # arrive as different classes: the guarded MCP seam rejecting us
            # (HTTP 401/403/404 during the handshake), egress policy REFUSING the
            # configured endpoint before we dial it, and an endpoint that answers
            # with nothing parseable. The seam's failure surface does not
            # distinguish "bad auth" from "bad request" the way the deleted SDK
            # client's ADCPAuthenticationError/ADCPConnectionError did, so the
            # advice below names every lever rather than presuming credentials —
            # an egress refusal has nothing to do with them. ``e.message`` already
            # says which cause it was.
            logger.error(f"Connection test failed (configuration): {e.message}")
            return {
                "success": False,
                "error": (
                    f"Connection failed: {e.message.rstrip('.')}. Check the agent URL, its credentials "
                    f"and auth header, and whether this deployment's egress policy allows the address."
                ),
            }

        except Exception as e:
            logger.error(f"Connection test failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Connection failed: {str(e)}",
            }


# Global registry instance
_registry: SignalsAgentRegistry | None = None


def get_signals_agent_registry() -> SignalsAgentRegistry:
    """Get the global signals agent registry instance."""
    global _registry
    if _registry is None:
        _registry = SignalsAgentRegistry()
    return _registry

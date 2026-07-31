"""Unified MCP client utility for consistent agent communication.

This module provides a single, standardized way to create MCP clients for
communicating with external agents (creative agents, signals agents, etc.).

Key features:
- Consistent URL handling (uses user's URL; if it fails after retries, does one
  final fallback attempt by appending "/mcp" when missing)
- Standardized auth header building
- Built-in retry logic with exponential backoff
- Proper error handling and logging
- Testable in isolation

Usage:
    from src.core.utils.mcp_client import create_mcp_client

    async with create_mcp_client(
        agent_url="https://example.com/mcp",
        auth={"type": "bearer", "credentials": "token123"},
        timeout=30
    ) as client:
        result = await client.call_tool("tool_name", params)
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastmcp.client import Client
from fastmcp.client.transports import (
    StreamableHttpTransport,  # noqa: TID251 - the MCP seam; construction is factory-pinned below (GH #1589)
)

from src.core.security.outbound_http import guarded_client_factory, sleep_backoff, validate_url

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    """Raised when MCP client connection fails after all retries."""

    pass


class MCPCompatibilityError(Exception):
    """Raised when MCP SDK version compatibility issue detected."""

    pass


def _build_auth_headers(auth: dict[str, Any] | None, auth_header: str | None = None) -> dict[str, str]:
    """Build authentication headers from auth config.

    Args:
        auth: Auth configuration dict with 'type' and 'credentials' keys
        auth_header: Optional custom header name (defaults based on auth type)

    Returns:
        Dictionary of headers to include in request

    Examples:
        >>> _build_auth_headers({"type": "bearer", "credentials": "token123"})
        {"Authorization": "Bearer token123"}

        >>> _build_auth_headers({"type": "api_key", "credentials": "key123"})
        {"x-api-key": "key123"}

        >>> _build_auth_headers({"type": "bearer", "credentials": "token"}, "X-Custom-Auth")
        {"X-Custom-Auth": "Bearer token"}
    """
    headers: dict[str, str] = {}

    if not auth:
        return headers

    auth_type = auth.get("type")
    credentials = auth.get("credentials")

    if not auth_type or not credentials:
        return headers

    # Determine header name
    if auth_header:
        header_name = auth_header
    elif auth_type == "bearer":
        header_name = "Authorization"
    elif auth_type == "api_key":
        header_name = "x-api-key"
    else:
        # Generic auth type - use x-api-key as default
        header_name = "x-api-key"

    # Format header value
    if auth_type == "bearer":
        headers[header_name] = f"Bearer {credentials}"
    else:
        # For api_key and other types, use credentials as-is
        headers[header_name] = credentials

    return headers


@asynccontextmanager
async def create_mcp_client(
    agent_url: str,
    auth: dict[str, Any] | None = None,
    auth_header: str | None = None,
    timeout: int = 30,
    max_retries: int = 3,
):
    """Create MCP client with standardized connection handling.

    This is the ONLY place where MCP clients should be created. This ensures
    consistent URL handling, auth, retry logic, and error handling across
    all agent communications.

    Args:
        agent_url: URL of the MCP agent endpoint
                  Examples: "https://creative.adcontextprotocol.org/mcp"
                           "https://audience-agent.fly.dev/FastMCP/"
                  NOTE: Use the exact URL the user provided - no modifications!
        auth: Optional auth configuration dict
              Format: {"type": "bearer"|"api_key", "credentials": "token_value"}
        auth_header: Optional custom auth header name
                    (defaults: "Authorization" for bearer, "x-api-key" for api_key)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum connection retry attempts (default: 3)

    Yields:
        Connected MCP Client instance

    Raises:
        MCPConnectionError: If connection fails after all retries
        MCPCompatibilityError: If MCP SDK version incompatibility detected

    Example:
        async with create_mcp_client(
            agent_url="https://creative.adcontextprotocol.org/mcp",
            auth={"type": "bearer", "credentials": "token123"},
            timeout=30
        ) as client:
            result = await client.call_tool("list_creative_formats", {})
            formats = result.structured_content
    """
    # Strip trailing slashes only - preserve the actual path (no mutation besides trimming)
    agent_url = agent_url.rstrip("/")

    # Egress policy, once, BEFORE the candidate loop and outside every try.
    #
    # Position is load-bearing. Inside the loop this sits under a bare
    # ``except Exception``, so a refusal would be logged as a connection failure,
    # slept on, retried against the same blocked URL and then against the
    # synthesised ``/mcp`` candidate, and finally re-raised as MCPConnectionError
    # — a policy decision laundered into a transport failure. Here the refusal
    # propagates as OutboundRequestBlocked, unretried and correctly classified.
    #
    # Validating the primary also covers the ``/mcp`` fallback below: it differs
    # only by path, and the seam's policy is about scheme and address.
    validate_url(agent_url)

    # Build auth headers
    headers = _build_auth_headers(auth, auth_header)

    # Prepare connection candidates: primary URL first, then a single '/mcp' fallback (if missing)
    primary_url = agent_url
    fallback_url = None
    if not primary_url.endswith("/mcp"):
        fallback_url = f"{primary_url}/mcp"

    candidates: list[tuple[str, int]] = [(primary_url, max_retries)]
    if fallback_url:
        # Per requirement: try once again with '/mcp' after primary retries fail
        candidates.append((fallback_url, 1))

    # Retry loop(s) with exponential backoff for primary; single attempt for fallback
    last_exception = None
    attempted_urls: list[str] = []

    for current_url, attempts in candidates:
        attempted_urls.append(current_url)

        for attempt in range(attempts):
            try:
                # Create transport and client. The httpx_client_factory pins the
                # connection to current_url's validated IP and refuses redirects:
                # without it fastmcp falls back to mcp.shared._httpx_utils's
                # create_mcp_http_client, which follows redirects with no pin, so a
                # counterparty answering `302 -> http://169.254.169.254/` reaches an
                # address the :157 pre-check never saw. Pinning current_url — the URL
                # actually dialed — also means validate-and-dial cannot diverge.
                transport = StreamableHttpTransport(
                    url=current_url,
                    headers=headers,
                    httpx_client_factory=guarded_client_factory(current_url),
                )
                client = Client(transport=transport)

                # Use client's built-in context manager
                async with client:
                    # Success! Yield the connected client
                    logger.debug(f"MCP client connected to {current_url} on attempt {attempt + 1}")
                    yield client
                    return

            except Exception as e:
                last_exception = e
                error_msg = str(e)

                # Check for known compatibility issues
                if "notifications/initialized" in error_msg:
                    logger.warning(
                        f"MCP SDK compatibility issue with {current_url}: "
                        f"Server doesn't support 'notifications/initialized' notification. "
                        f"This is a known issue between FastMCP SDK versions."
                    )
                    raise MCPCompatibilityError(
                        f"MCP SDK compatibility issue with {current_url}: "
                        f"Server doesn't support notifications/initialized notification. "
                        f"The agent may need to upgrade their FastMCP version to match the client."
                    ) from e

                # Log and retry for this candidate
                logger.warning(
                    f"MCP connection attempt {attempt + 1}/{attempts} failed for {current_url}: {type(e).__name__}: {e}"
                )

                if attempt < attempts - 1:
                    # Backoff for the primary candidate only (attempts > 1). This
                    # client owns its transport for protocol reasons — a stateful
                    # MCP session over StreamableHttpTransport, which the egress
                    # seam's one-shot asend cannot carry — so it defers to the
                    # seam's BR-RULE-029 schedule instead of recomputing one
                    # (1-based attempt index; this loop counts from 0).
                    await sleep_backoff(attempt + 1)
                else:
                    # Exhausted attempts for this candidate; move to next (if any)
                    logger.error(
                        f"All {attempts} connection attempt(s) failed for {current_url}. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    break

    # If we reach here, all candidates failed — preserve legacy error format regardless of fallback
    raise MCPConnectionError(
        f"Failed to connect to MCP agent at {agent_url} after {max_retries} attempts: "
        f"{type(last_exception).__name__ if last_exception else 'UnknownError'}: {last_exception}"
    ) from last_exception

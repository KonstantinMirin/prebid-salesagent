"""Translate a guarded-MCP-seam (``create_mcp_client``) failure into this application's AdCP taxonomy.

For OPERATOR-configured creative/signals agents (salesagent-4n88): routing the
dial through ``src.core.utils.mcp_client.create_mcp_client`` closes the SSRF gap
left by ``adcp.ADCPMultiAgentClient`` (no transport injection point in adcp
6.6.0 — upstream adcp-client-python#1004), but the seam's failure surface is not
the SDK's typed ``ADCPError`` hierarchy — it is ``MCPConnectionError`` /
``MCPCompatibilityError`` (this application's own, from ``mcp_client.py``).
``create_mcp_client``'s ``yield client`` sits INSIDE its own retry loop's
``try``, so an exception the caller raises while using ``client`` — including a
tool-level ``ToolError``/``McpError`` from ``call_tool`` — is thrown back into
that generator, retried like any other connection attempt, and surfaces to the
caller only as the final ``MCPConnectionError``. There is no separate
tool-level exception type callers of this function need to catch.

``MCPConnectionError`` looked, at first read, like it discarded the HTTP status
entirely. It does not, except for one case: the MCP Streamable HTTP transport
(``mcp/client/streamable_http.py::_handle_post_request``) special-cases a plain
404 on a session POST as "no such session" — a PROTOCOL-level signal, not a
transport failure — and synthesizes an opaque ``McpError`` for it, discarding
the status on purpose. Every other non-2xx status is a normal
``httpx.HTTPStatusError`` that survives intact as ``__cause__`` (status code and
headers, including ``Retry-After``, fully readable), because
``raise ... from ...`` chaining is exactly what both ``MCPConnectionError`` and
``create_mcp_client``'s retry loop use. That is why the classification below can
still distinguish 429 / other-4xx / 5xx: it just has to look past the causing
exception the seam already used.

Only used for OPERATOR-configured agents — a counterparty-supplied ``agent_url``
never reaches this path (creative_agent_registry.py routes those through
``_fetch_formats_raw_mcp``, on the raw egress seam's own ``OutboundError``
taxonomy, unchanged by this migration).
"""

from __future__ import annotations

import logging
from typing import NoReturn

from src.core.exceptions import AdCPAdapterError, AdCPRateLimitError, AdCPServiceUnavailableError, clamp_retry_after
from src.core.security.outbound_http import find_wrapped_http_status_error, retry_after_seconds


def raise_mapped_mcp_error(exc: Exception, *, agent_label: str, logger: logging.Logger) -> NoReturn:
    """Re-raise a guarded-MCP-seam failure as the AdCP error this application's taxonomy names.

    Mirrors ``src.core.helpers.outbound_error_mapping.raise_mapped_outbound_error``'s
    classification (429 -> RATE_LIMITED with the real ``retry_after``; other 4xx
    -> terminal; 5xx or no recoverable status -> SERVICE_UNAVAILABLE/transient) so
    the two seams name failures the same way despite different transports.

    Always raises; the ``NoReturn`` annotation lets a caller delegate from one
    ``except`` arm without a trailing ``raise``.
    """
    http_error = find_wrapped_http_status_error(exc)
    if http_error is not None:
        status = http_error.response.status_code
        if status == 429:
            retry_after = retry_after_seconds(http_error.response)
            logger.warning(f"{agent_label} rate-limited (HTTP 429)")
            raise AdCPRateLimitError(
                f"{agent_label} is rate-limited.",
                retry_after=clamp_retry_after(retry_after) if retry_after is not None else None,
            ) from exc
        if 400 <= status < 500:
            logger.error(f"{agent_label} rejected the request (HTTP {status})")
            raise AdCPAdapterError(f"{agent_label} rejected the request.", recovery="terminal") from exc
        logger.error(f"{agent_label} returned HTTP {status}")
        raise AdCPServiceUnavailableError(f"{agent_label} is unavailable.") from exc

    logger.error(f"{agent_label} is unreachable: {exc}")
    raise AdCPServiceUnavailableError(f"{agent_label} is unreachable.") from exc

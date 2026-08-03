"""Shared helper for threading AdCP's version-envelope request fields.

Every AdCP request inherits ``AdcpVersionEnvelope`` (``adcp_version`` /
``adcp_major_version``) from the ``adcp`` library. MCP tool wrappers must
declare these as explicit parameters (FastMCP derives its tool schema from
the function signature), then forward them into request construction —
this helper is the one place that mapping lives, shared by every wrapper.
"""

from typing import Any


def version_envelope_kwargs(adcp_version: str | None, adcp_major_version: int | None) -> dict[str, Any]:
    """Build the kwargs dict for a Request's inherited AdcpVersionEnvelope fields."""
    return {"adcp_version": adcp_version, "adcp_major_version": adcp_major_version}

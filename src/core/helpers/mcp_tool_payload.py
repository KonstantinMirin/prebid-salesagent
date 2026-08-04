"""Read the JSON payload an MCP ``tools/call`` result carries.

fastmcp's ``CallToolResult`` may carry the response as ``structured_content``
(already-parsed JSON) or as legacy ``TextContent`` blocks in ``content`` whose
``.text`` is a JSON string. Every MCP tool call in this codebase reads a result
the same way — this is that one place (DRY), replacing what was duplicated
inline in ``preview_creative``/``build_creative`` and now also needed by the
guarded creative-format/signals fetch paths (salesagent-4n88).
"""

from __future__ import annotations

import json
from typing import Any


def extract_tool_payload(result: Any) -> dict[str, Any]:
    """Return the tool's JSON payload, or ``{}`` if neither shape is present."""
    structured = getattr(result, "structured_content", None)
    if structured:
        return structured

    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)

    return {}

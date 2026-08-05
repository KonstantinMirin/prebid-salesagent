"""Shared MCP transport-wrapper helper for building ``ToolResult`` responses."""

from __future__ import annotations

from fastmcp.tools.tool import ToolResult
from pydantic import BaseModel


def mcp_result(response: BaseModel, content: str | None = None) -> ToolResult:
    """Build a ``ToolResult`` with a spec-compliant ``structured_content``.

    ``structured_content`` must be a plain dict via ``model_dump()``: FastMCP's
    ``ToolResult`` serializes non-dict ``structured_content`` via
    ``pydantic_core.to_jsonable_python()``, which bypasses ``model_dump()``
    overrides (Pattern #4 nested serialization) and ``AdCPBaseModel``'s
    ``exclude_none=True`` default -- so protocol/spec-optional fields the model
    leaves unset would otherwise serialize as invalid wire ``null`` instead of
    being omitted.
    """
    return ToolResult(
        content=content if content is not None else str(response),
        structured_content=response.model_dump(mode="json"),
    )

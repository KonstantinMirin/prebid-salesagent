"""The live MCP registry, read as ``tool -> (request DTO, advertised parameters)``.

Importing ``src.core.main`` is what registers the tools, so this sees exactly the set a
buyer sees. Every suite that grades "one fact per registered tool" reads membership from
HERE rather than from a dict of tool names it keeps itself: a tool absent from a
hand-kept dict is graded by nothing and reads as green, which is the failure mode two
separate tables in this repo were created to prevent and one of them then reintroduced.

The DTO comes from ``request_model_for`` — the same lookup MCP registers the tool's
announced shape with — so no consumer can resolve a DIFFERENT model for a tool than the
one production actually builds.
"""

from __future__ import annotations

from functools import cache

from pydantic import BaseModel


@cache
def registered_tool_shapes() -> dict[str, tuple[type[BaseModel], frozenset[str]]]:
    """``tool -> (request DTO, ADVERTISED parameter names)`` for every tool with a DTO.

    Cached because building it imports and registers the whole MCP server; the registry
    does not change within a process.
    """
    import asyncio

    from src.core import main
    from src.core.tools._announced_shape import request_model_for

    shapes: dict[str, tuple[type[BaseModel], frozenset[str]]] = {}
    for tool in asyncio.run(main.mcp.list_tools()):
        source_fn = getattr(tool.fn, "__wrapped__", tool.fn)
        model = request_model_for(source_fn)
        if model is not None:
            shapes[tool.name] = (model, frozenset(tool.parameters.get("properties", {})))
    return shapes


def registered_request_dtos() -> dict[str, type[BaseModel]]:
    """``tool -> request DTO``, for callers that do not need the advertised set."""
    return {tool: model for tool, (model, _) in registered_tool_shapes().items()}

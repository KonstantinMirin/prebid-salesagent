"""Steps for the locally-added MCP tool-discovery feature.

WHAT MAKES THESE NON-VACUOUS. Every value asserted is read off the ``tools/list`` body the
seller POSTed back on ``/mcp/``, and the expected value is computed independently from the
registry row's request model (``TOOLS[name].dto.model_json_schema()``), never from the
listing. The self-containment step requires at least one ``$ref`` in the listing, so a
listing that inlines every reference cannot pass it on an empty population.
"""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator
from pytest_bdd import then, when
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from src.core.tools.registry import TOOLS
from tests.helpers.pinned_schema import iter_schema_refs

#: The URI each listed document is registered under, alone, so a ``$ref`` that resolves at
#: all resolves inside that document.
_LISTED_URI = "urn:mcp-tools-list:input-schema"


def _listed_tools(ctx: dict) -> dict[str, dict[str, Any]]:
    """The listed tools by name, as the buyer received them."""
    return {tool["name"]: tool for tool in ctx["mcp_tools"]}


@when("the buyer lists the seller's MCP tools")
def when_list_mcp_tools(ctx: dict) -> None:
    ctx["mcp_tools"] = ctx["env"].list_mcp_tools()


@then("every tool the registry declares is listed")
def then_every_registry_tool_is_listed(ctx: dict) -> None:
    listed = set(_listed_tools(ctx))
    declared = set(TOOLS)
    assert declared, "the registry declares no tools, so there is nothing to grade"
    assert listed == declared, (
        f"tools/list does not list exactly the registry's tools; "
        f"missing: {sorted(declared - listed)}, unexpected: {sorted(listed - declared)}"
    )


@then("each listed input schema is the tool's request model JSON Schema")
def then_listed_schema_is_request_model_schema(ctx: dict) -> None:
    differing = []
    for name, tool in sorted(_listed_tools(ctx).items()):
        declared = TOOLS[name].dto.model_json_schema()
        if tool["inputSchema"] != declared:
            differing.append(
                f"{name}: listed {len(json.dumps(tool['inputSchema']))} bytes, "
                f"request model {len(json.dumps(declared))} bytes"
            )
    assert not differing, "tools/list publishes a schema other than the request model's:\n" + "\n".join(differing)


@then("each listed input schema is a self-contained JSON Schema 2020-12 document")
def then_listed_schema_is_self_contained(ctx: dict) -> None:
    refs_seen = 0
    unresolved = []
    for name, tool in sorted(_listed_tools(ctx).items()):
        schema = tool["inputSchema"]
        Draft202012Validator.check_schema(schema)
        resolver = Registry().with_resource(_LISTED_URI, DRAFT202012.create_resource(schema)).resolver(_LISTED_URI)
        for ref in iter_schema_refs(schema):
            refs_seen += 1
            try:
                resolver.lookup(ref)
            except Unresolvable:
                unresolved.append(f"{name}: {ref}")
    assert not unresolved, "listed input schemas carry references that do not resolve within them:\n" + "\n".join(
        unresolved
    )
    assert refs_seen > 0, (
        "no listed input schema carries a $ref, so the listing inlines every definition the "
        "request models declare instead of publishing them"
    )

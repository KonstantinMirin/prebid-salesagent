"""The advertised MCP shape is DERIVED from the SDK request DTO, and stays honest.

Three properties, each of which failed at least once while this was being built:

1. The derivation actually reaches FastMCP. Setting ``__signature__`` alone looks right
   under ``inspect.signature`` and changes nothing, because FastMCP resolves types with
   ``typing.get_type_hints`` (which reads ``__annotations__``).
2. It never NARROWS. Adopting a DTO type where the tool deliberately accepts more turns a
   type annotation into a buyer-visible rejection: doing that to ``get_products.brand``
   broke 18 brand-shorthand scenarios on mcp, because FastMCP validates against the
   advertised schema.
3. A DTO field the tool does not accept is never advertised -- with no hand-maintained
   list of exclusions. Absence from the signature IS the statement.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.tools._announced_shape import (
    _NEVER_ANNOUNCED,
    _would_narrow,
    apply_dto_announced_shape,
    request_model_for,
)

_LANE_D_TOOLS = ("get_adcp_capabilities", "get_products", "list_creative_formats", "list_creatives")


def _tool(name: str):
    from src.core.tools import capabilities, creative_formats, creatives, products

    return {
        "get_adcp_capabilities": capabilities.get_adcp_capabilities,
        "get_products": products.get_products,
        "list_creative_formats": creative_formats.list_creative_formats,
        "list_creatives": creatives.list_creatives,
    }[name]


#: (tool, parameter) pairs whose advertised type is deliberately WIDER than the DTO's,
#: because the implementation accepts more and narrowing would reject real input:
#:   get_products.brand           -- brand shorthand ("acme.com", {"domain": ...})
#:   get_adcp_capabilities.protocols / .ext -- plain str / dict rather than the generated
#:                                   enum and ExtensionObject wrapper
#:   list_creatives.fields        -- accepts the enum OR its bare string value
#: SHRINK ONLY. A new entry means an advertised type drifted wider than the spec without
#: anyone deciding to; close the gap or state the reason here.
_WIDER_THAN_DTO: frozenset[tuple[str, str]] = frozenset(
    {
        ("get_products", "brand"),
        ("get_adcp_capabilities", "protocols"),
        ("get_adcp_capabilities", "ext"),
        ("list_creatives", "fields"),
    }
)


@pytest.mark.parametrize("tool_name", _LANE_D_TOOLS)
def test_every_lane_d_tool_resolves_its_request_dto(tool_name: str) -> None:
    """The tool -> DTO edge is read from the builder the wrapper calls, via bytecode."""
    assert request_model_for(_tool(tool_name)) is not None, (
        f"{tool_name} no longer resolves to a request DTO -- the announced shape silently "
        "falls back to whatever the signature happens to say"
    )


def test_derivation_reaches_the_advertised_schema() -> None:
    """Not just __signature__: FastMCP reads __annotations__, so both must move."""
    from fastmcp.tools import Tool

    from src.core.tool_error_logging import with_error_logging

    fn = _tool("get_adcp_capabilities")
    registered = with_error_logging(fn)
    assert apply_dto_announced_shape(registered, fn) is True

    advertised = Tool.from_function(registered, name="get_adcp_capabilities").parameters
    context = advertised["properties"]["context"]
    assert "$ref" in str(context), (
        "context should be advertised as the DTO's ContextObject reference; a plain object "
        "here means the derivation set __signature__ only and FastMCP never saw it"
    )


@pytest.mark.parametrize("tool_name", _LANE_D_TOOLS)
def test_advertised_types_never_narrow_what_the_tool_accepts(tool_name: str) -> None:
    """Any parameter whose advertised type is narrower than its own would reject input."""
    fn = _tool(tool_name)
    model = request_model_for(fn)
    assert model is not None
    narrowed = []
    for name, parameter in inspect.signature(fn).parameters.items():
        if name in _NEVER_ANNOUNCED:
            continue
        field = model.model_fields.get(name)
        if field is None or parameter.annotation is inspect.Parameter.empty:
            continue
        if _would_narrow(parameter.annotation, field.annotation) and (tool_name, name) not in _WIDER_THAN_DTO:
            narrowed.append(name)
    assert not narrowed, (
        f"{tool_name} accepts more than it advertises for {narrowed}, and the pair is not "
        f"recorded in _WIDER_THAN_DTO. FastMCP validates against the advertised schema, so "
        f"this rejects input the implementation would have handled."
    )


def test_wider_than_dto_ledger_has_no_stale_entries() -> None:
    """An entry that no longer widens must be deleted -- the ledger only shrinks."""
    stale = []
    for tool_name, param in sorted(_WIDER_THAN_DTO):
        fn = _tool(tool_name)
        model = request_model_for(fn)
        parameter = inspect.signature(fn).parameters.get(param)
        if parameter is None or model is None or param not in model.model_fields:
            stale.append(f"{tool_name}.{param} (parameter or DTO field is gone)")
            continue
        if not _would_narrow(parameter.annotation, model.model_fields[param].annotation):
            stale.append(f"{tool_name}.{param} (no longer wider than the DTO)")
    assert not stale, f"_WIDER_THAN_DTO entries that no longer apply: {stale}"


@pytest.mark.parametrize("tool_name", _LANE_D_TOOLS)
def test_unimplemented_dto_fields_are_never_advertised(tool_name: str) -> None:
    """The automatic half: absence from the signature is what excludes a field.

    No list of "unimplemented" fields exists to be maintained, so this asserts the
    property directly rather than against a fixture.
    """
    from fastmcp.tools import Tool

    from src.core.tool_error_logging import with_error_logging

    fn = _tool(tool_name)
    model = request_model_for(fn)
    registered = with_error_logging(fn)
    apply_dto_announced_shape(registered, fn)

    advertised = set(Tool.from_function(registered, name=tool_name).parameters.get("properties", {}))
    accepted = {n for n in inspect.signature(fn).parameters if n not in _NEVER_ANNOUNCED}
    unimplemented = set(model.model_fields) - accepted

    leaked = advertised & unimplemented
    assert not leaked, f"{tool_name} advertises {sorted(leaked)}, which it does not accept"
    assert advertised == accepted, (
        f"{tool_name} advertises {sorted(advertised ^ accepted)} differently from what it accepts"
    )

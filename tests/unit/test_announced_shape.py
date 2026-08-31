"""The advertised MCP shape is DERIVED from the SDK request DTO, and stays honest.

Three properties, each of which failed at least once while this was being built:

1. The derivation actually reaches FastMCP. Setting ``__signature__`` alone looks right
   under ``inspect.signature`` and changes nothing, because FastMCP resolves types with
   ``typing.get_type_hints`` (which reads ``__annotations__``).
2. Advertised == accepted. The advertised type is the DTO's, so where this agent accepts
   more than the library (the brand shorthand) the widening is declared ON THE MODEL. If the
   model claims less than the tool implements, FastMCP rejects valid input at the boundary
   before any tool code runs -- that regression happened twice here, 18 scenarios then 16.
3. A DTO field the tool does not accept is never advertised -- with no hand-maintained
   list of exclusions. Absence from the signature IS the statement.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.tools._announced_shape import (
    _is_injected,
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


#: Every tool whose wrapper builds a request, i.e. every tool the derivation applies to.
_DERIVED_TOOLS = (
    "get_adcp_capabilities",
    "get_products",
    "list_creative_formats",
    "list_creatives",
    "create_media_buy",
    "get_media_buy_delivery",
    "get_media_buys",
    "list_accounts",
    "sync_accounts",
    "update_media_buy",
    "update_performance_index",
)


def _resolve_tool(name: str):
    import sys

    for module in list(sys.modules.values()):
        candidate = getattr(module, name, None)
        if callable(candidate) and getattr(candidate, "__name__", None) == name:
            if request_model_for(candidate) is not None:
                return candidate
    return None


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


@pytest.mark.parametrize("tool_name", _DERIVED_TOOLS)
def test_unimplemented_dto_fields_are_never_advertised(tool_name: str) -> None:
    """The automatic half: absence from the signature is what excludes a field.

    No list of "unimplemented" fields exists to be maintained, so this asserts the
    property directly rather than against a fixture.
    """
    from fastmcp.tools import Tool

    import src.core.main  # noqa: F401  (registers the tools)
    from src.core.tool_error_logging import with_error_logging

    fn = _resolve_tool(tool_name)
    if fn is None:
        pytest.skip(f"{tool_name} does not resolve a request DTO")
    model = request_model_for(fn)
    registered = with_error_logging(fn)
    apply_dto_announced_shape(registered, fn)

    advertised = set(Tool.from_function(registered, name=tool_name).parameters.get("properties", {}))
    accepted = {n for n, p in inspect.signature(fn).parameters.items() if not _is_injected(p)}
    unimplemented = set(model.model_fields) - accepted

    leaked = advertised & unimplemented
    assert not leaked, f"{tool_name} advertises {sorted(leaked)}, which it does not accept"

    # The rule is an INTERSECTION, in both directions:
    #   a DTO field the tool does not accept  -> not advertised (not implemented)
    #   a tool parameter the DTO does not declare -> not advertised (not in the spec)
    expected = set(model.model_fields) & accepted
    assert advertised == expected, (
        f"{tool_name} advertises {sorted(advertised ^ expected)} outside "
        f"(DTO fields INTERSECT accepted parameters). Non-spec parameters must not be "
        f"advertised, and neither must DTO fields the tool cannot take."
    )


class TestLiveRegistryActuallyCarriesTheDerivation:
    """Graded against the LIVE advertised schema, not against the helpers.

    The rest of this module tests ``derived_signature`` / ``_would_narrow`` directly, which
    a mutation review showed is not enough: turning ``apply_dto_announced_shape`` into a
    no-op, reverting the scope gate, or deleting the never-narrow guard reddened NOTHING,
    because nothing here read what FastMCP actually publishes. These do.

    The oracle is a field whose advertised form genuinely DIFFERS with the derivation on
    and off -- the DTO's description reaches the wire only when it ran.
    """

    @staticmethod
    async def _advertised(tool_name: str) -> dict:
        from src.core import main

        return (await main.mcp.get_tool(tool_name)).parameters["properties"]

    @pytest.mark.asyncio
    async def test_derivation_is_live_for_a_scoped_tool(self) -> None:
        """get_adcp_capabilities.adcp_version must carry the DTO's description.

        Undecorated the wrapper says "Requested AdCP spec version"; the DTO says
        "Release-precision AdCP version ...". Only the derivation puts the DTO's text on
        the wire, so this reddens the moment the mechanism stops running.
        """
        from adcp.types import GetAdcpCapabilitiesRequest

        advertised = await self._advertised("get_adcp_capabilities")
        expected = GetAdcpCapabilitiesRequest.model_fields["adcp_version"].description
        assert expected, "the DTO field lost its description -- pick another oracle field"
        assert advertised["adcp_version"].get("description") == expected, (
            "the advertised adcp_version description is not the DTO's. The derivation is "
            "not reaching the live registry -- check apply_dto_announced_shape is called "
            "in _register_tool and that it sets __annotations__ as well as __signature__."
        )

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
    derived_signature,
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


class TestNarrowingIsGraded:
    """The `accepted` argument to select_request_fields must actually narrow.

    A mutation review found that making select_request_fields IGNORE `accepted` reddened
    nothing in the whole suite: uc018 and uc019 were byte-identical to baseline. The
    narrowing is what stops a callee being handed a DTO field it cannot take -- the
    difference between a dropped key and a TypeError 500 on a spec-conformant payload -- so
    it needs a grader that fails when it stops happening.
    """

    def test_accepted_narrows_the_selection(self) -> None:
        """Fields outside `accepted` must not be forwarded."""
        from src.core.schema_helpers import select_request_fields
        from src.core.schemas import ListCreativesRequest

        bag = {"filters": {"tags": ["q1"]}, "sort": {"direction": "asc"}, "include_assignments": True}
        wide = select_request_fields(ListCreativesRequest, bag)
        narrow = select_request_fields(ListCreativesRequest, bag, {"filters"})

        assert set(wide) == {"filters", "sort", "include_assignments"}, (
            f"unnarrowed selection should carry every DTO field present in the bag; got {sorted(wide)}"
        )
        assert set(narrow) == {"filters"}, (
            f"`accepted` must remove what the callee cannot take; got {sorted(narrow)}. If this "
            f"equals the unnarrowed set, select_request_fields is ignoring its third argument "
            f"and every converted call site is handing its callee unaccepted kwargs."
        )

    def test_a_real_call_site_would_break_without_narrowing(self) -> None:
        """The concrete case: create_get_products_request takes 5 of GetProductsRequest's 20.

        Splatting the unnarrowed selection into it raises TypeError -- which is precisely the
        500-on-a-valid-payload the `accepted` argument exists to prevent. Proven by calling
        it, not by reading the signature.
        """

        import pytest

        from src.core.schema_helpers import create_get_products_request, select_request_fields
        from src.core.schemas import GetProductsRequest

        bag = {"brief": "video", "catalog": {"id": "c1"}, "refine": True}
        unnarrowed = select_request_fields(GetProductsRequest, bag)
        assert "catalog" in unnarrowed, "fixture stale: catalog must be a DTO field for this to grade"
        with pytest.raises(TypeError):
            create_get_products_request(**unnarrowed)

        narrowed = select_request_fields(
            GetProductsRequest, bag, inspect.signature(create_get_products_request).parameters
        )
        create_get_products_request(**narrowed)  # must not raise


class TestDerivationIsAPureFunction:
    """The derivation is ``(signature, DTO) -> signature``: no I/O, no registry, no DB.

    Graded here with a FIXTURE model and a LITERAL expectation, which is the whole point.
    The tests these replace computed their expectation as ``set(model.model_fields) &
    accepted`` -- exactly what production computes -- so both sides moved together and the
    assertion was blind to the rule being wrong; it graded drift, not correctness. A mutation
    review confirmed it: disabling ``_is_injected`` left them fully green.

    Writing the expected parameters out by hand is what makes them able to fail. The fixture
    deliberately contains BOTH exclusion directions, because the rule is an intersection and
    a test that exercises only one half cannot tell an intersection from a union.
    """

    @staticmethod
    def _fixture():
        from pydantic import BaseModel, Field

        class FixtureRequest(BaseModel):
            alpha: str | None = Field(default=None, description="described by the DTO")
            beta: int | None = None
            gamma_unimplemented: bool | None = None  # DTO declares it; the tool does not take it

        from fastmcp.server.context import Context

        def fixture_tool(
            alpha: str = "",
            beta: int = 0,
            legacy_not_in_dto: str = "",
            ctx: Context | None = None,
        ):
            """A tool with one spec param the DTO lacks and one the DTO has."""

        return fixture_tool, FixtureRequest

    def test_derived_parameters_are_exactly_the_intersection(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert sorted(p for p in sig.parameters if p != "ctx") == ["alpha", "beta"], (
            "expected exactly the DTO fields the tool accepts. "
            "gamma_unimplemented is declared by the DTO but not taken by the tool; "
            "legacy_not_in_dto is taken by the tool but not declared by the DTO."
        )

    def test_a_dto_field_the_tool_cannot_take_is_not_derived(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert "gamma_unimplemented" not in sig.parameters, (
            "advertising a field the implementation does not accept offers buyers an input "
            "whose only outcome is an error"
        )

    def test_a_tool_parameter_the_dto_does_not_declare_is_not_derived(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert "legacy_not_in_dto" not in sig.parameters, (
            "a parameter outside the spec must not be advertised; absence from the DTO is "
            "what retires it, with no list of legacy names to maintain"
        )

    def test_the_injected_context_parameter_survives(self) -> None:
        """ctx is not a DTO field but must stay, or FastMCP has nothing to inject.

        Dropping it is not a cosmetic bug: it broke authentication on 79 tests in this lane
        (every call arrived without identity -> AUTH_MISSING) because the annotation arrived
        as a STRING under postponed annotations and the type test missed it.
        """
        fixture_tool, FixtureRequest = self._fixture()
        assert "ctx" in derived_signature(fixture_tool, FixtureRequest).parameters

    def test_the_dto_supplies_the_description(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert "described by the DTO" in str(sig.parameters["alpha"].annotation)


class TestAdvertisedSchemaIsPublished:
    """What FastMCP actually publishes -- a request/response concern, not a pure one.

    Separated from the derivation tests above on purpose: this needs the live registry, so it
    can only assert what a buyer would really receive. Expectations are LITERAL for one tool,
    not recomputed from the model.
    """

    @pytest.mark.asyncio
    async def test_get_adcp_capabilities_publishes_exactly_its_five_fields(self) -> None:
        from src.core import main

        advertised = set((await main.mcp.get_tool("get_adcp_capabilities")).parameters["properties"])
        assert advertised == {"protocols", "context", "adcp_version", "adcp_major_version", "ext"}, (
            f"published shape drifted: {sorted(advertised)}. This is the buyer-visible schema, "
            f"written out rather than recomputed, so it fails when the shape moves for any reason."
        )


class TestAdvertisedTypesAreAccepted:
    """Every TYPE we advertise must be one the implementation actually takes.

    The lane's rule -- advertise (DTO fields) INTERSECT (impl arguments) -- was enforced in the
    NAME dimension only. Names are not the whole shape: adopting the DTO also adopts the DTO's
    TYPES, and a type can widen while the implementation stays narrow. That direction had no
    grader, and it put a live defect in the tree.

    update_media_buy advertised ``budget: Budget | number | null`` (from the DTO) while
    ``_build_update_request`` still declared ``float | None`` and called ``float(budget)``. A
    buyer sending the documented Budget object got ``TypeError: float() argument must be a
    string or a real number, not 'Budget'`` -- an untyped 500 from the exact payload our own
    schema told them to send. This is the precise inverse of the rule: an advertised input
    whose only outcome is an error.

    Graded behaviorally -- construct the advertised type, call the real builder -- rather than
    by comparing annotations, because an annotation comparison cannot distinguish a real defect
    from a loose one (``typing.Any`` accepts everything; bare ``list`` differs from
    ``list[str]`` only on paper). Of 23 statically-suspicious sites, exactly one broke.
    """

    def test_the_budget_object_we_advertise_is_accepted(self) -> None:
        from src.core.tools.media_buy_update import Budget, _build_update_request

        req = _build_update_request(media_buy_id="mb_1", budget=Budget(total=5000, currency="EUR"))

        assert req.budget is not None
        assert float(req.budget.total) == 5000.0
        assert req.budget.currency == "EUR", (
            "the currency carried INSIDE the Budget object must survive; dropping it would "
            "silently re-denominate the buy, which is worse than the TypeError it replaced"
        )

    def test_the_bare_number_form_still_works(self) -> None:
        """The scalar form must keep reaching _impl as a bare float.

        Not redundant with the case above: _impl branches on the type, and reusing the
        existing media buy's currency (rather than forcing USD at the boundary) depends on
        the bare float arriving bare. A fix that coerced everything into a Budget would pass
        the test above and silently re-denominate every scalar update to USD.
        """
        from src.core.tools.media_buy_update import _build_update_request

        req = _build_update_request(media_buy_id="mb_1", budget=5000)

        assert isinstance(req.budget, float)
        assert req.budget == 5000.0

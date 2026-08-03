"""Meta-tests for AddressTable — the DERIVED (not hand-maintained) tool address map.

Covers two things:

1. Resolution against the REAL production registration objects (``mcp``,
   ``create_agent_card()``, ``app.routes``) for tools that already exist —
   proving the map reads live data, not a copy.
2. The core invariant from the design doc (§4): a tool registered on a
   FRESH registration object at test time — one ``AddressTable`` has never
   seen before — becomes addressable with ZERO map edits. This is the
   direct proof that nothing in this file (or in ``address_table.py``)
   needs updating when a new tool is registered in production; only
   ``AddressTable``'s constructor accepts injected registration objects (a
   testability seam), the derivation logic itself is unconditional.

No database required — building the table only reads in-memory registration
objects (``mcp.list_tools()``, ``create_agent_card()``, ``app.routes``).
"""

from __future__ import annotations

import asyncio

import pytest

from tests.harness.address_table import PATH_PARAM_RE, AddressTable, NoAddressForTransport, ToolAddress
from tests.harness.transport import Transport


class TestAddressTableAgainstLiveProduction:
    """Resolution against the real, already-registered production objects."""

    def test_resolves_get_products_on_mcp(self):
        table = AddressTable()
        address = table.resolve("get_products", Transport.MCP)
        assert address == ToolAddress(Transport.MCP, name="get_products")

    def test_resolves_get_products_on_a2a(self):
        table = AddressTable()
        address = table.resolve("get_products", Transport.A2A)
        assert address == ToolAddress(Transport.A2A, name="get_products")

    def test_resolves_get_products_on_rest_with_method_and_path(self):
        table = AddressTable()
        address = table.resolve("get_products", Transport.REST)
        assert address.method == "post"
        assert address.path_template == "/api/v1/products"

    def test_resolves_update_media_buy_rest_path_param(self):
        """update_media_buy's REST route has a {media_buy_id} path param — the
        concrete case the REST WRAP path-param peeling (tests/harness/client.py)
        generalizes from MediaBuyDualEnv's hand-coded version (design doc §4)."""
        table = AddressTable()
        address = table.resolve("update_media_buy", Transport.REST)
        assert address.method == "put"
        assert address.path_template == "/api/v1/media-buys/{media_buy_id}"
        assert address.path_params == ("media_buy_id",)

    def test_e2e_family_shares_the_same_address_as_in_process(self):
        """WRAP/UNWRAP are transport-FAMILY functions (design doc §5) — the
        address table mirrors that by registering the identical name/path/method
        under both the in-process and E2E transport keys."""
        table = AddressTable()
        mcp_addr = table.resolve("get_products", Transport.MCP)
        e2e_mcp_addr = table.resolve("get_products", Transport.E2E_MCP)
        assert mcp_addr.name == e2e_mcp_addr.name
        assert e2e_mcp_addr.transport == Transport.E2E_MCP

    def test_no_address_for_transport_on_a2a_only_skill(self):
        """approve_creative exists only on A2A (create_creative/assign_creative/
        approve_creative/get_media_buy_status/optimize_media_buy — design doc §2
        'Important asymmetry to flag for the implementer'). Confirmed against the
        live registries directly (not assumed) before writing this test."""
        table = AddressTable()
        with pytest.raises(NoAddressForTransport):
            table.resolve("approve_creative", Transport.MCP)
        with pytest.raises(NoAddressForTransport):
            table.resolve("approve_creative", Transport.REST)
        # But it DOES resolve on the transport it actually exists on:
        assert table.resolve("approve_creative", Transport.A2A).name == "approve_creative"

    def test_no_address_for_unknown_tool(self):
        table = AddressTable()
        with pytest.raises(NoAddressForTransport):
            table.resolve("this_tool_does_not_exist", Transport.MCP)

    def test_every_live_mcp_tool_resolves(self):
        """Full-coverage check against the LIVE registry, not a hardcoded subset —
        if a tool is added to src/core/main.py tomorrow, this test keeps passing
        with zero edits, because it enumerates mcp.list_tools() itself rather than
        naming tools by hand."""
        from src.core.main import mcp

        table = AddressTable()
        live_tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
        assert live_tool_names, "sanity: production MCP registry should not be empty"
        for name in live_tool_names:
            assert table.resolve(name, Transport.MCP).name == name


class TestAddressTableDerivationInvariant:
    """The core invariant (design doc §4): NEW registrations become addressable
    with no hand-maintained map edit — proven by registering a tool at test
    time on a THROWAWAY registration object an AddressTable has never seen,
    not by asserting against tools someone already wired into address_table.py.
    """

    def test_new_mcp_tool_becomes_addressable_without_a_map_edit(self):
        from fastmcp import FastMCP

        temp_app = FastMCP("throwaway-test-server")

        @temp_app.tool()
        def brand_new_tool_never_seen_before(x: int) -> int:
            return x

        table = AddressTable(mcp_app=temp_app)
        address = table.resolve("brand_new_tool_never_seen_before", Transport.MCP)
        assert address.name == "brand_new_tool_never_seen_before"
        # And the E2E sibling gets it too, for free — same derivation pass.
        assert table.resolve("brand_new_tool_never_seen_before", Transport.E2E_MCP).name == (
            "brand_new_tool_never_seen_before"
        )

    def test_new_a2a_skill_becomes_addressable_without_a_map_edit(self):
        from a2a.types import AgentCapabilities, AgentCard, AgentSkill

        def fake_agent_card() -> AgentCard:
            return AgentCard(
                name="throwaway",
                description="throwaway",
                version="0.0.0",
                capabilities=AgentCapabilities(),
                default_input_modes=["message"],
                default_output_modes=["message"],
                skills=[AgentSkill(id="brand_new_skill_never_seen_before", name="Brand New Skill", tags=[])],
            )

        table = AddressTable(agent_card_factory=fake_agent_card)
        address = table.resolve("brand_new_skill_never_seen_before", Transport.A2A)
        assert address.name == "brand_new_skill_never_seen_before"

    def test_new_rest_route_becomes_addressable_without_a_map_edit(self):
        from fastapi import FastAPI

        temp_app = FastAPI()

        @temp_app.post("/api/v1/brand-new-tool/{widget_id}")
        def brand_new_rest_tool_never_seen_before(widget_id: str) -> dict:
            return {"widget_id": widget_id}

        table = AddressTable(rest_app=temp_app)
        address = table.resolve("brand_new_rest_tool_never_seen_before", Transport.REST)
        assert address.name == "brand_new_rest_tool_never_seen_before"
        assert address.method == "post"
        assert address.path_template == "/api/v1/brand-new-tool/{widget_id}"
        assert address.path_params == ("widget_id",)

    def test_non_api_v1_routes_are_not_indexed(self):
        """The REST indexer only reads /api/v1/* — confirms it isn't blindly
        vacuuming every FastAPI route (e.g. /admin/*, /mcp/*, health checks)."""
        from fastapi import FastAPI

        temp_app = FastAPI()

        @temp_app.get("/healthz")
        def healthcheck() -> dict:
            return {"ok": True}

        table = AddressTable(rest_app=temp_app)
        with pytest.raises(NoAddressForTransport):
            table.resolve("healthcheck", Transport.REST)


class TestPathParamRegex:
    def test_extracts_single_param(self):
        assert PATH_PARAM_RE.findall("/api/v1/media-buys/{media_buy_id}") == ["media_buy_id"]

    def test_extracts_multiple_params(self):
        assert PATH_PARAM_RE.findall("/api/v1/a/{a_id}/b/{b_id}") == ["a_id", "b_id"]

    def test_no_params(self):
        assert PATH_PARAM_RE.findall("/api/v1/products") == []

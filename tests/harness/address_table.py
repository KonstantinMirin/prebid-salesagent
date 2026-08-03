"""Tool address derivation — MCP/A2A/REST addresses read from live registration.

Builds the tool -> address map from the THREE objects production itself uses to
route real traffic: ``mcp.list_tools()`` (what a real MCP client sees),
``create_agent_card()`` (what a real A2A buyer's discovery request receives),
and ``app.routes`` (FastAPI's own dispatch table). There is no fourth,
hand-maintained list — a tool registered on any of those three sites becomes
resolvable through :data:`ADDRESS_TABLE` automatically; a tool NOT registered
on a transport raises :class:`NoAddressForTransport` instead of silently
being unreachable. See ``.claude/notes/storyboard-conformance/
sb2a-transport-generic-client-design.md`` §4 for the design this implements.

Usage::

    from tests.harness.address_table import ADDRESS_TABLE
    from tests.harness.transport import Transport

    address = ADDRESS_TABLE.resolve("get_products", Transport.MCP)
    # address.name == "get_products"

    from tests.harness.address_table import NoAddressForTransport
    try:
        ADDRESS_TABLE.resolve("approve_creative", Transport.REST)
    except NoAddressForTransport:
        ...  # expected: approve_creative is an A2A-only skill
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tests.harness.transport import Transport

# {name} groups in a REST path template, e.g. "media_buy_id" from
# "/api/v1/media-buys/{media_buy_id}". Single source of truth for both the
# ADDRESS derivation (informational) and REST WRAP's path-param peeling
# (tests/harness/client.py) — see design doc §4 "path_template handling".
PATH_PARAM_RE = re.compile(r"\{(\w+)\}")


class NoAddressForTransport(LookupError):
    """Tool has no registered address on the requested transport.

    This is EXPECTED, not a bug — not every tool exists on every transport.
    A2A's ``skill_handlers`` has strictly more entries than MCP's tool set or
    REST's route set (e.g. ``approve_creative``, ``get_media_buy_status``,
    ``optimize_media_buy``, ``create_creative``, ``assign_creative`` are
    A2A-only). Callers that hit this for a real scenario should treat it as
    "this scenario is scoped to fewer transports than the default", not
    paper over it with a broader except.
    """


@dataclass(frozen=True)
class ToolAddress:
    """One transport's resolved address for one tool. Frozen/hashable — safe to cache."""

    transport: Transport
    # MCP: tool name. A2A: skill id. REST: route.endpoint.__name__ (same string
    # convention production uses — every api_v1.py handler is named after the
    # tool it wraps).
    name: str
    path_template: str | None = None  # REST only, e.g. "/api/v1/media-buys/{media_buy_id}"
    method: str | None = None  # REST only, lowercase HTTP verb, e.g. "put"

    @property
    def path_params(self) -> tuple[str, ...]:
        """Path-param names captured by ``path_template`` (REST only, else empty)."""
        if not self.path_template:
            return ()
        return tuple(PATH_PARAM_RE.findall(self.path_template))


# Transport families: WRAP/UNWRAP are shared across an in-process transport and
# its E2E sibling (see design doc §5) — ADDRESS derivation mirrors that by
# registering the same ToolAddress under both keys of a family.
_MCP_FAMILY = (Transport.MCP, Transport.E2E_MCP)
_A2A_FAMILY = (Transport.A2A, Transport.E2E_A2A)
_REST_FAMILY = (Transport.REST, Transport.E2E_REST)


class AddressTable:
    """Tool -> address map, built once per process from live registration objects.

    Not a hand-maintained dict — rebuilding costs nothing (no I/O), so it is
    built lazily on first ``resolve()`` call to avoid import-order issues with
    ``src.core.main`` / ``src.app`` (importing either pulls in the full app
    wiring, which some unit-test contexts must not trigger at module-import
    time).

    The three ``_index_*`` methods read production's own registration
    objects by default (``src.core.main.mcp``, ``create_agent_card()``,
    ``src.app.app``). Tests that need to prove the "derived, not
    hand-maintained" invariant directly — a NEW tool registered at test time
    becomes addressable with zero map edits — inject a throwaway
    ``mcp_app``/``agent_card_factory``/``rest_app`` via the constructor
    instead of mutating the real production singletons.
    """

    def __init__(
        self,
        *,
        mcp_app: Any = None,
        agent_card_factory: Callable[[], Any] | None = None,
        rest_app: Any = None,
    ) -> None:
        self._mcp_app: Any = mcp_app
        self._agent_card_factory = agent_card_factory
        self._rest_app: Any = rest_app
        self._by_tool_transport: dict[tuple[str, Transport], ToolAddress] = {}
        self._built = False

    def _build(self) -> None:
        self._index_mcp()
        self._index_a2a()
        self._index_rest()
        self._built = True

    def _index_mcp(self) -> None:
        import asyncio

        mcp_app: Any = self._mcp_app
        if mcp_app is None:
            from src.core.main import mcp as mcp_app  # noqa: PLC0414

        for tool in asyncio.run(mcp_app.list_tools()):
            for t in _MCP_FAMILY:
                self._by_tool_transport[(tool.name, t)] = ToolAddress(t, name=tool.name)

    def _index_a2a(self) -> None:
        agent_card_factory = self._agent_card_factory
        if agent_card_factory is None:
            from src.a2a_server.adcp_a2a_server import create_agent_card

            agent_card_factory = create_agent_card

        for skill in agent_card_factory().skills:
            for t in _A2A_FAMILY:
                self._by_tool_transport[(skill.id, t)] = ToolAddress(t, name=skill.id)

    def _index_rest(self) -> None:
        rest_app: Any = self._rest_app
        if rest_app is None:
            from src.app import app as rest_app  # noqa: PLC0414

        for route in rest_app.routes:
            path = getattr(route, "path", "")
            endpoint = getattr(route, "endpoint", None)
            methods = getattr(route, "methods", None)
            if not path.startswith("/api/v1") or endpoint is None or not methods:
                continue
            tool_name = endpoint.__name__
            method = next(iter(methods - {"HEAD"})).lower()
            for t in _REST_FAMILY:
                self._by_tool_transport[(tool_name, t)] = ToolAddress(
                    t, name=tool_name, path_template=path, method=method
                )

    def resolve(self, tool: str, transport: Transport) -> ToolAddress:
        """Return the live-registered address for *tool* on *transport*.

        Raises :class:`NoAddressForTransport` when *tool* has no address on
        *transport* — an expected, per-tool-per-transport possibility (see
        class docstring), not a hand-maintained-map bug.
        """
        if not self._built:
            self._build()
        key = (tool, transport)
        if key not in self._by_tool_transport:
            raise NoAddressForTransport(f"{tool!r} has no registered address on {transport!r}")
        return self._by_tool_transport[key]

    def all_tools(self, transport: Transport) -> frozenset[str]:
        """All tool names addressable on *transport* — for coverage assertions."""
        if not self._built:
            self._build()
        return frozenset(name for (name, t) in self._by_tool_transport if t == transport)


# Module-level singleton over the REAL production registration objects — the
# one every step definition / client should import. Lazily built on first use.
ADDRESS_TABLE = AddressTable()

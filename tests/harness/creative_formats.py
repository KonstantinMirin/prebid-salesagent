"""CreativeFormatsEnv — integration test environment for _list_creative_formats_impl.

Patches: the creative agent registry singleton (replaced by a fresh instance of
production's own testing-mode ``ReferenceFormatsRegistry`` per env, so each scenario has
its own format cache), and the audit logger.
Real: the registry, the tenant's ``creative_agents`` rows, the dial to a peer creative
agent over the egress seam, and the format processing logic.

A scenario that names the formats a seller serves calls ``set_registry_formats``. The
formats are served by a real peer creative agent -- the webhook-capture service, started
once per worker in process and running in the compose stack on e2e -- the tenant's one
``creative_agents`` row points at it, and the tenant does not federate the standard
creative agent. The seller then lists exactly those formats, on every transport, through
production's own path.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with CreativeFormatsEnv() as env:
            env.set_registry_formats([format_1, format_2])
            response = env.call_impl()
            assert len(response.formats) == 2

Available mocks via env.mock:
    "registry"     -- get_creative_agent_registry (lazy import in creative_formats.py)
    "audit_logger" -- get_audit_logger (module-level import in creative_formats.py)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.core.schemas import ListCreativeFormatsResponse
from tests.harness._base import IntegrationEnv
from tests.harness._realize import realize_e2e
from tests.harness.egress import EgressHatchMixin
from tests.harness.transport import DeliverResult
from tests.helpers.peer_creative_agent import new_peer_key, serve_peer_catalog
from tests.helpers.tls_material import trust_test_ca


def _serve_peer_catalog_on_the_live_stack(env: CreativeFormatsEnv, key: str, document: dict[str, Any]) -> str:
    """E2E realization of the peer agent: the compose stack's capture service serves *document*.

    The live server cannot reach a socket in the runner, so the peer it dials is the
    webhook-capture service, which already sits behind the shared TLS front and answers
    ``list_creative_formats`` over MCP for a key a test programs. Returns the URL the
    server dials, which the tenant's ``creative_agents`` row then names; the factory writes
    that row to the live server's own database, as every e2e factory row is written.
    """
    from tests.e2e import _webhook_capture

    _webhook_capture.serve_peer_catalog(key, document)
    return _webhook_capture.peer_agent_url(key)


class CreativeFormatsEnv(EgressHatchMixin, IntegrationEnv):
    """Integration test environment for _list_creative_formats_impl.

    Runs production's testing-mode registry against real ``creative_agents`` rows and a
    real peer creative agent; mocks only the audit logger.
    """

    # Dispatch declaration: the base owns call_mcp/call_a2a.
    RESPONSE_MODEL = ListCreativeFormatsResponse

    # JUSTIFIED OVERRIDE — does NOT declare MCP_TOOL/A2A_SKILL, so it does not
    # take the base's client-core delegation. AdCPTestClient's UNWRAP parses the
    # wire into spec_response_model("list_creative_formats") — the PINNED
    # ListCreativeFormatsResponse — and our real format-registry wire does not
    # satisfy it (measured: 2520 errors, e.g. formats.N.assets.M.max_count /
    # .assets required by the pinned Assets variants but absent from ours).
    # That is a list_creative_formats-vs-pinned-schema conformance gap, NOT a
    # dispatch defect, so it is recorded and graded elsewhere rather than being
    # hidden by making the core's parse swallow ValidationError.
    def deliver_mcp(self, **kwargs: Any) -> DeliverResult:
        """Dispatch list_creative_formats via the real FastMCP Client pipeline."""
        return self._run_mcp_client("list_creative_formats", ListCreativeFormatsResponse, **kwargs)

    def deliver_a2a(self, **kwargs: Any) -> DeliverResult:
        """Dispatch list_creative_formats via the real A2A handler pipeline."""
        return self._run_a2a_handler("list_creative_formats", ListCreativeFormatsResponse, **kwargs)

    EXTERNAL_PATCHES = {
        "registry": "src.core.creative_agent_registry.get_creative_agent_registry",
        "audit_logger": "src.core.tools.creative_formats.get_audit_logger",
    }
    REST_ENDPOINT = "/api/v1/creative-formats"

    #: The formats :meth:`set_registry_formats` seeded, or None when no Given named any.
    _seeded_formats: list[Any] | None = None
    #: The tenant's one peer ``creative_agents`` row, created on first use.
    _peer_agent_row: Any = None
    #: The URL that row names: where the seller dials its peer, and what it refers buyers to.
    _peer_agent_url: str | None = None
    #: Whether this env trusts the test CA and opened the private-range hatch yet.
    _peer_reachable: bool = False

    def _configure_mocks(self) -> None:
        """Install production's testing-mode registry, fresh per env, and a no-op audit logger.

        ``ReferenceFormatsRegistry`` answers the standard creative agent from the committed
        capture and dials every agent the tenant configured, exactly as the e2e server's
        registry does, so a scenario with no format Given lists the capture in both worlds.
        The patch exists only so each env gets its own instance -- and with it its own
        format cache -- rather than the process's memoized one.
        """
        from src.core.creative_agent_registry import ReferenceFormatsRegistry

        self.mock["registry"].return_value = ReferenceFormatsRegistry()
        self.mock["audit_logger"].return_value = MagicMock()

    def set_registry_formats(self, formats: list[Any]) -> None:
        """The seller's catalog is exactly *formats*, on every transport.

        Serves *formats* from the peer creative agent under a fresh key, points the
        tenant's one peer ``creative_agents`` row at it, and turns off the tenant's
        federation of the standard creative agent (``use_default_creative_agent``), so the
        seller lists these formats and nothing else. Each call mints a new key, so a
        cumulative re-sync from successive Givens is never answered from a catalog the
        registry cached for an earlier URL.

        A format the seller's own parse refuses (``PeerFormat``) is discarded and
        reported, as it would be from any real peer: the Given has to build a conforming
        format, which is the point of serving it for real.
        """
        document = {"formats": [fmt.model_dump(mode="json", exclude_none=True) for fmt in formats]}
        self.configure_peer_agent(self._serve_peer_catalog(document), use_default_creative_agent=False)
        self._seeded_formats = list(formats)

    def set_peer_format_payload(self, payload: list[dict[str, Any]]) -> None:
        """A creative agent configured on the tenant answers ``list_creative_formats`` with *payload*.

        *payload* is the agent's ``formats`` array as raw JSON, served verbatim, so an
        entry the pinned schema cannot validate reaches the seller's OWN parse. Nothing
        here is a stand-in for that parse: the agent is a real MCP endpoint over TLS, the
        tenant row is a real ``creative_agents`` row, and the registry is production's
        testing-mode ``ReferenceFormatsRegistry``. The standard creative agent stays
        federated: these scenarios locate the peer's formats by the agent_url it published.
        """
        self.configure_peer_agent(self._serve_peer_catalog({"formats": payload}))

    def _serve_peer_catalog(self, document: dict[str, Any]) -> str:
        """Serve *document* from the peer creative agent under a fresh key; return its URL."""
        return self._realize_peer_catalog(new_peer_key(), document)

    @realize_e2e(_serve_peer_catalog_on_the_live_stack)
    def _realize_peer_catalog(self, key: str, document: dict[str, Any]) -> str:
        """In process: this worker's shared peer agent, on loopback over TLS.

        The registry dials it through the egress seam, so the env trusts the shared test
        CA and opens the private-range hatch -- once, for the env's lifetime. The live
        stack's posture is already open.
        """
        if not self._peer_reachable:
            trust_test_ca(self._guard)
            self.set_egress_hatches(private=True)
            self._peer_reachable = True
        return serve_peer_catalog(key, document)

    def configure_peer_agent(self, agent_url: str, **tenant_columns: Any) -> None:
        """The tenant's one peer creative agent is *agent_url* -- one row, both worlds.

        The row is created on the first call and re-pointed after, so a scenario never
        configures two peers by re-seeding. *tenant_columns* go through ``ensure_tenant``,
        which applies them to the tenant row the test or the e2e auto-seed already created
        and seeds nothing else: this configures the seller, not a buyer.
        """
        from tests.factories import CreativeAgentFactory

        tenant = self.ensure_tenant(**tenant_columns)
        if self._peer_agent_row is None:
            self._peer_agent_row = CreativeAgentFactory(tenant=tenant, agent_url=agent_url, name="Peer Creative Agent")
        else:
            self._peer_agent_row.agent_url = agent_url
        self._commit_factory_data()
        self._peer_agent_url = agent_url

    def peer_agent_url(self) -> str:
        """The URL of the tenant's peer creative agent, as its ``creative_agents`` row names it."""
        assert self._peer_agent_url is not None, "no peer creative agent is configured on this tenant"
        return self._peer_agent_url

    def served_registry_formats(self) -> list[Any]:
        """The formats the seller's creative agents serve this scenario, on every transport.

        What :meth:`set_registry_formats` seeded -- the peer serves exactly those and the
        standard agent is not federated -- or, when no Given named any, the reference
        catalog the standard creative agent answers from.
        """
        if self._seeded_formats is not None:
            return list(self._seeded_formats)
        from src.core.format_cache import load_reference_formats

        return list(load_reference_formats())

    def call_impl(self, **kwargs: Any) -> ListCreativeFormatsResponse:
        """Call _list_creative_formats_impl.

        Accepts 'req' (ListCreativeFormatsRequest) and 'identity' kwargs.
        Defaults to self.identity if not provided.
        """
        from src.core.tools.creative_formats import _list_creative_formats_impl

        self._commit_factory_data()
        kwargs.setdefault("identity", self.identity)
        kwargs.setdefault("req", None)
        return _list_creative_formats_impl(**kwargs)

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Forward FLAT kwargs to the REST body, matching a2a/mcp.

        This env dispatches a2a and mcp BY TOOL NAME, so its callers pass flat
        kwargs (``format_ids=[...]``) rather than a ``req`` object. The inherited
        default only serializes a Pydantic ``req`` and returns ``{}`` for
        anything else — so every flat-kwarg filter was silently dropped on REST
        alone, and REST ran UNFILTERED while a2a and mcp filtered. A parametrized
        test then reported three green transports while only two graded the
        filter (found via salesagent-3dawm.16).

        ListCreativeFormatsBody (src/routes/api_v1.py) declares format_ids and
        every other filter, and the route maps them into
        ListCreativeFormatsRequest, so forwarding them makes REST filter for real.

        A Pydantic ``req`` still takes precedence, so callers that pass one keep
        the inherited behaviour.
        """
        from pydantic import BaseModel as PydanticBaseModel

        if isinstance(kwargs.get("req"), PydanticBaseModel):
            return super().build_rest_body(**kwargs)

        body: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key in ("req", "identity") or value is None:
                continue
            if isinstance(value, PydanticBaseModel):
                body[key] = value.model_dump(mode="json", exclude_none=True)
            elif isinstance(value, list):
                body[key] = [
                    v.model_dump(mode="json", exclude_none=True) if isinstance(v, PydanticBaseModel) else v
                    for v in value
                ]
            else:
                body[key] = value
        return body

    # parse_rest_response: the base's, which revives RESPONSE_MODEL.

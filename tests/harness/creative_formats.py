"""CreativeFormatsEnv — integration test environment for _list_creative_formats_impl.

Patches: creative agent registry, audit logger.
Real: format processing logic (no direct DB access in this _impl). A scenario that
calls ``set_peer_format_payload`` swaps the registry stand-in for production's own
registry, which dials a real peer endpoint.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with CreativeFormatsEnv() as env:
            env.set_registry_formats([mock_format_1, mock_format_2])
            response = env.call_impl()
            assert len(response.formats) == 2

Available mocks via env.mock:
    "registry"     -- get_creative_agent_registry (lazy import in creative_formats.py)
    "audit_logger" -- get_audit_logger (module-level import in creative_formats.py)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.core.schemas import FormatKey, ListCreativeFormatsResponse
from tests.harness._base import IntegrationEnv
from tests.harness._realize import E2EUnsupportedSetup, realize_e2e
from tests.harness.egress import EgressHatchMixin
from tests.harness.transport import DeliverResult
from tests.helpers.tls_material import start_tls_capture_service, trust_test_ca


def _format_identity_key(fmt: Any) -> FormatKey:
    """Federation identity ``(canonical agent_url, id)`` of a Format / FormatId / bare id.

    Delegates to ``src.core.format_resolver.format_identity``, which is the ONE
    place that answers "same format?" — it normalizes the three shapes a
    reference actually arrives in (model, wire dict, legacy bare string) and then
    hands the rule itself to ``src.core.schemas.format_id_identity``. The pinned
    ``core/format-id.json`` makes canonicalizing ``agent_url`` before treating two
    references as one a MUST, so a harness that compared ``.format_id.id`` alone
    (what this helper used to do) would call a third-party format that merely
    shares an id "already in the reference catalog" and silently skip the
    unrealizable-setup error the scenario needs.

    Accepts a ``Format`` (unwrapped via ``.format_id``), a bare ``FormatId``, a
    wire dict, or a plain string id — a bare id is namespaced to the canonical
    creative agent, which is the agent every entry in the reference fixture
    carries.
    """
    from src.core.format_resolver import format_identity

    return format_identity(getattr(fmt, "format_id", fmt))


def _validate_registry_formats(env: Any, formats: list[Any]) -> None:
    """E2E realization of set_registry_formats: validate against the live catalog.

    The live stack serves the full reference-format catalog by construction
    (``ADCP_TESTING`` reads the same fixture this validates against), so there
    is no per-scenario server registry to write. Instead we validate the
    scenario's intent is realizable:

    - empty list (empty-catalog scenarios) -> unrealizable: the live stack
      always serves the agent catalog.
    - requested ids ⊆ reference set -> no-op: the server already serves them.
    - requested ⊄ reference set -> unrealizable: name the missing ids and point
      at the fixture-refresh path.

    Membership is decided on the ``(canonical agent_url, id)`` federation pair
    (:func:`_format_identity_key`), never on the bare id: two agents may publish
    the same ``id``, and only the pair says whether the LIVE catalog actually
    serves the format this scenario asked for.

    The missing ones are spelled by ``format_display``, the one renderer of a
    :data:`FormatKey`'s halves. A key is a ``str`` now, not the frozen dataclass it was
    before the creative-identity collapse, so reading ``.id`` / ``.agent_url`` off one here
    raised ``AttributeError`` instead of naming them -- turning every unrealizable e2e setup
    into a failure rather than the skip the scenario asked for.
    """
    from src.core.format_cache import load_reference_formats
    from src.core.format_resolver import format_display

    if not formats:
        raise E2EUnsupportedSetup(
            "live stack always serves the agent catalog; an empty catalog cannot be realized over e2e"
        )

    reference_ids = {_format_identity_key(f) for f in load_reference_formats()}
    requested_ids = {_format_identity_key(f) for f in formats}
    missing = requested_ids - reference_ids
    if missing:
        named = sorted(format_display(identity) for identity in missing)
        raise E2EUnsupportedSetup(
            f"requested formats not in the reference catalog: {named}. "
            "Register them in the creative agent registry and refresh the fixture "
            "(`make creative-formats-refresh`)."
        )


def _serve_peer_catalog_on_the_live_stack(env: CreativeFormatsEnv, payload: list[dict[str, Any]]) -> None:
    """E2E realization of set_peer_format_payload: the compose stack's capture service is the peer.

    The live server cannot reach a socket in the runner, so the peer it dials is the
    webhook-capture service, which already sits behind the shared TLS front and answers
    ``list_creative_formats`` over MCP for a key a test programs. The tenant's
    ``creative_agents`` row names that endpoint; the factory writes it to the live
    server's own database, as every e2e factory row is written.
    """
    from tests.e2e._webhook_capture import peer_agent_url, serve_peer_catalog

    key = f"peer-{uuid4().hex}"
    serve_peer_catalog(key, {"formats": payload})
    env.configure_peer_agent(peer_agent_url(key))


class CreativeFormatsEnv(EgressHatchMixin, IntegrationEnv):
    """Integration test environment for _list_creative_formats_impl.

    Mocks creative agent registry (external service) and audit logger.
    The format processing logic runs for real.
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

    def _configure_mocks(self) -> None:
        """Set up happy-path defaults for external mocks.

        Seeds a minimal set of default formats so scenarios that don't
        explicitly call set_registry_formats() still get non-empty results.
        Scenarios needing specific formats override via set_registry_formats().
        """
        from src.core.creative_agent_registry import CreativeAgentRegistry, FormatFetchResult
        from src.core.format_cache import load_reference_formats

        default_formats = list(load_reference_formats())

        # Registry: return a mock with async list_all_formats + list_all_formats_with_errors
        mock_registry = MagicMock()
        mock_registry.list_all_formats = AsyncMock(return_value=default_formats)
        mock_registry.list_all_formats_with_errors = AsyncMock(
            return_value=FormatFetchResult(formats=default_formats, errors=[])
        )
        self.mock["registry"].return_value = mock_registry

        # ``_get_tenant_agents`` is the REAL method, bound to a real registry, so the
        # referral path (``creative_agents``, POST-S4) reads the tenant's
        # ``creative_agents`` rows exactly as the live server does. Left as a MagicMock
        # attribute it returned a MagicMock, which MagicMock makes ITERABLE AND EMPTY --
        # so production walked zero agents and answered ``creative_agents: []`` on every
        # in-process transport. That is a mock inventing an answer it does not have, and
        # it read as a production gap for long enough to be recorded as one.
        #
        # ``_get_tenant_agents`` is defined once, on the base, and neither
        # ``ReferenceFormatsRegistry`` nor anything else overrides it, so which class is
        # instantiated here cannot change the answer.
        mock_registry._get_tenant_agents = CreativeAgentRegistry()._get_tenant_agents

        # Audit logger: no-op
        mock_logger = MagicMock()
        self.mock["audit_logger"].return_value = mock_logger

    @realize_e2e(_validate_registry_formats)
    def set_registry_formats(self, formats: list[Any]) -> None:
        """Configure mock registry to return these formats from list_all_formats.

        In-process: injects ``formats`` on the registry mock. E2E: validates the
        request is realizable against the live catalog (the live stack serves the
        full reference set by construction, so there is no per-scenario registry
        to write) — see :func:`_validate_registry_formats`.
        """
        from src.core.creative_agent_registry import FormatFetchResult

        self.mock["registry"].return_value.list_all_formats = AsyncMock(return_value=formats)
        self.mock["registry"].return_value.list_all_formats_with_errors = AsyncMock(
            return_value=FormatFetchResult(formats=list(formats), errors=[])
        )

    @realize_e2e(_serve_peer_catalog_on_the_live_stack)
    def set_peer_format_payload(self, payload: list[dict[str, Any]]) -> None:
        """A creative agent configured on the tenant answers ``list_creative_formats`` with *payload*.

        *payload* is the agent's ``formats`` array as raw JSON, served verbatim, so an
        entry the pinned schema cannot validate reaches the seller's OWN parse. Nothing
        here is a stand-in for that parse: the agent is a real MCP endpoint over TLS (the
        same capture service the e2e stack runs, started in this process), the tenant row
        is a real ``creative_agents`` row, and the registry is production's testing-mode
        ``ReferenceFormatsRegistry``, which answers the default agent from the reference
        catalog and dials the tenant's configured agents.

        In process that means trusting the shared test CA and opening the private-range
        hatch, because the endpoint listens on loopback; the live stack's posture is
        already open.
        """
        from src.core.creative_agent_registry import ReferenceFormatsRegistry
        from tests.e2e.webhook_capture_service import peer_path

        trust_test_ca(self._guard)
        self.set_egress_hatches(private=True)
        peer = start_tls_capture_service(self._guard, "peer_creative_agent")
        key = f"peer-{uuid4().hex}"
        peer.store.serve_peer_catalog(key, {"formats": payload})
        self.configure_peer_agent(f"https://127.0.0.1:{peer.server_address[1]}{peer_path(key)}")
        self.mock["registry"].return_value = ReferenceFormatsRegistry()

    def configure_peer_agent(self, agent_url: str) -> None:
        """Configure *agent_url* as one of the tenant's creative agents -- one row, both worlds."""
        from tests.factories import CreativeAgentFactory

        tenant, _principal = self.setup_default_data()
        CreativeAgentFactory(tenant=tenant, agent_url=agent_url, name="Peer Creative Agent")
        self._commit_factory_data()

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

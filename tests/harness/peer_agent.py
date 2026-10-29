"""A real peer creative agent, reachable from any env whose code under test dials one.

A creative agent the tenant configured is dialled for its formats -- on the listing path
and on a single-format lookup alike -- so a test that names such an agent has to stand one
up that really answers. In process that is this worker's shared peer agent
(:mod:`tests.helpers.peer_creative_agent`), on loopback over TLS; on e2e it is the compose
stack's webhook-capture service. ``serve_peer_catalog`` is the one way an env reaches
either, so every env that needs a peer gets the same agent and the same reachability.

``seed_own_creative_agent`` is the one way an env says "the seller's catalog is exactly
these formats": serve them from the peer, point the tenant's one ``creative_agents`` row at
it, and stop federating the standard creative agent. Every env whose subject is a seeded
catalog -- listing it, or resolving a creative against it -- goes through it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from src.core.schemas import Format
from tests.harness._realize import realize_e2e
from tests.harness.egress import EgressHatchMixin
from tests.helpers.peer_creative_agent import new_peer_key, serve_peer_catalog
from tests.helpers.tls_material import trust_test_ca


def _serve_peer_catalog_on_the_live_stack(env: PeerCreativeAgentMixin, key: str, document: dict[str, Any]) -> str:
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


def _peer_url_on_the_live_stack(env: PeerCreativeAgentMixin, key: str) -> str:
    """E2E realization of :meth:`PeerCreativeAgentMixin.peer_url_for`: the URL the live server dials."""
    from tests.e2e import _webhook_capture

    return _webhook_capture.peer_agent_url(key)


class PeerCreativeAgentMixin(EgressHatchMixin):
    """Mixes the peer creative agent into an env whose code under test dials a configured creative agent.

    Host env must be an ``IntegrationEnv`` (relies on ``_guard`` to release the trusted CA
    and the hatch posture on exit, and on ``ensure_tenant`` / ``_commit_factory_data`` to
    write the tenant's ``creative_agents`` row).
    """

    if TYPE_CHECKING:
        # Declared, not implemented: this mixin is only composed with IntegrationEnv,
        # which owns the tenant row and the factory session (same convention as
        # EgressHatchMixin._guard).
        def ensure_tenant(self, **tenant_kwargs: Any) -> Any: ...
        def _commit_factory_data(self) -> None: ...

    #: Whether this env trusts the test CA and opened the private-range hatch yet.
    _peer_reachable: bool = False
    #: The tenant's one peer ``creative_agents`` row, created on first use.
    _peer_agent_row: Any = None
    #: The URL that row names: where the seller dials its peer, and what it refers buyers to.
    _peer_agent_url: str | None = None

    @realize_e2e(_serve_peer_catalog_on_the_live_stack)
    def serve_peer_catalog(self, key: str, document: dict[str, Any]) -> str:
        """Serve *document* as the peer's ``list_creative_formats`` under *key*; return the URL a seller dials.

        In process the peer is this worker's shared agent, on loopback over TLS. The seller
        dials it through the egress seam, so the env trusts the shared test CA and opens the
        private-range hatch -- once, for the env's lifetime. The live stack's posture is
        already open.
        """
        if not self._peer_reachable:
            trust_test_ca(self._guard)
            self.set_egress_hatches(private=True)
            self._peer_reachable = True
        return serve_peer_catalog(key, document)

    @realize_e2e(_peer_url_on_the_live_stack)
    def peer_url_for(self, key: str) -> str:
        """The URL a seller dials for the catalog served under *key*, before anything is served there."""
        from tests.helpers.peer_creative_agent import peer_agent_url

        return peer_agent_url(key)

    def publish_formats(self, formats: Sequence[Format], *, rehome: bool) -> str:
        """Serve *formats* from the peer under a fresh key; return the URL a seller dials.

        Each call mints a new key, so a re-seed is never answered from a catalog a registry
        cached for an earlier URL. With *rehome*, every entry's ``format_id.agent_url`` is the
        peer's own URL, as an agent states for a format it publishes: a creative that names
        one of them is then resolved by dialling this peer, because a single-format lookup
        routes by that URL and a URL naming the standard agent is answered from the
        reference capture instead. Without it, the entries are served verbatim.

        Serialized here, in the harness, because the document is what a real agent puts on
        the wire; the seller's own parse (``PeerFormat``) is what reads it back.
        """
        key = new_peer_key()
        entries = [fmt.model_dump(mode="json", exclude_none=True) for fmt in formats]
        if rehome:
            url = self.peer_url_for(key)
            for entry in entries:
                entry["format_id"]["agent_url"] = url
        return self.serve_peer_catalog(key, {"formats": entries})

    def seed_own_creative_agent(self, formats: Sequence[Format], *, rehome: bool) -> str:
        """The seller's catalog is exactly *formats*, on every transport; return the peer's URL.

        Serves *formats* from the peer (:meth:`publish_formats`), points the tenant's one
        peer ``creative_agents`` row at it, and turns off the tenant's federation of the
        standard creative agent (``use_default_creative_agent``), so the seller lists and
        resolves these formats and nothing else, through production's own registry.

        A format the seller's own parse refuses (``PeerFormat``) is discarded and reported,
        as it would be from any real peer: the caller has to build a conforming format,
        which is the point of serving it for real.
        """
        url = self.publish_formats(formats, rehome=rehome)
        self.configure_peer_agent(url, use_default_creative_agent=False)
        return url

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

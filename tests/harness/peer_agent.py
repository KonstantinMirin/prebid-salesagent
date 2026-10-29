"""A real peer creative agent, reachable from any env whose code under test dials one.

A creative agent the tenant configured is dialled for its formats -- on the listing path
and on a single-format lookup alike -- so a test that names such an agent has to stand one
up that really answers. In process that is this worker's shared peer agent
(:mod:`tests.helpers.peer_creative_agent`), on loopback over TLS; on e2e it is the compose
stack's webhook-capture service. ``serve_peer_catalog`` is the one way an env reaches
either, so every env that needs a peer gets the same agent and the same reachability.
"""

from __future__ import annotations

from typing import Any

from tests.harness._realize import realize_e2e
from tests.harness.egress import EgressHatchMixin
from tests.helpers.peer_creative_agent import serve_peer_catalog
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


class PeerCreativeAgentMixin(EgressHatchMixin):
    """Mixes ``serve_peer_catalog`` into an env whose code under test dials a configured creative agent.

    Host env must be an ``IntegrationEnv`` (relies on ``_guard`` to release the trusted CA
    and the hatch posture on exit).
    """

    #: Whether this env trusts the test CA and opened the private-range hatch yet.
    _peer_reachable: bool = False

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

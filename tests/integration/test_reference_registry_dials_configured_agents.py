"""The testing-mode registry answers from the reference capture for the operator agent only.

``ReferenceFormatsRegistry`` (every test deployment, and the e2e server) serves the
committed capture in place of the standard creative agent. A creative agent the tenant
configured is a different agent: looking one of its formats up must dial it, on the
single-format path as on the listing path. Before the rule lived in one place the
single-format path answered the capture for ANY agent_url, so a peer's format could not be
resolved and a capture id was "found" at an agent that never published it.
"""

from __future__ import annotations

import asyncio

import pytest

from src.core.creative_agent_registry import ReferenceFormatsRegistry
from src.core.format_cache import load_reference_formats
from tests.harness.creative_formats import CreativeFormatsEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_PEER_FORMAT_ID = "acme_peer_banner"
_PEER_ENTRY = {
    "format_id": {"agent_url": "https://peer-creatives.example", "id": _PEER_FORMAT_ID},
    "name": "Acme Peer Banner",
}


def test_a_configured_agents_format_is_looked_up_from_that_agent(integration_db):
    """The peer's own format resolves; a capture id at the peer's URL does not."""
    capture_id = load_reference_formats()[0].format_id.id
    with CreativeFormatsEnv() as env:
        env.set_peer_format_payload([_PEER_ENTRY])
        registry = ReferenceFormatsRegistry()
        peer_format = asyncio.run(registry.get_format(agent_url=env.peer_agent_url(), format_id=_PEER_FORMAT_ID))
        capture_format = asyncio.run(registry.get_format(agent_url=env.peer_agent_url(), format_id=capture_id))

    assert peer_format is not None, "the configured agent's format was not resolved from the agent"
    assert peer_format.name == "Acme Peer Banner"
    assert capture_format is None, (
        f"{capture_id!r} resolved at the configured agent's URL, which never published it: "
        "the reference capture answered for a non-operator agent"
    )

"""Operator-registered creative/signals agents dial through the guarded MCP seam (salesagent-4n88).

``CreativeAgentRegistry`` and ``SignalsAgentRegistry`` used to build an
``adcp.ADCPMultiAgentClient`` (``_build_adcp_client``) to query OPERATOR-configured
agents — the tenant's own ``creative_agents`` / ``signals_agents`` rows, plus the
built-in default creative agent. adcp 6.6.0 exposes no client/transport/factory
injection point on ``ADCPMultiAgentClient`` (verified: its ``__init__`` takes
only ``agents``, ``webhook_url_template``, ``webhook_secret``, ``on_activity``,
``handlers``, ``signing``, ``adcp_version``), so that dial reached none of this
application's egress policy — address validation, IP pinning, redirect refusal
— at all (upstream ask: adcp-client-python#1004, open, blocked on a maintainer
design call as of this writing).

Fixed by routing the operator dial through
``src.core.utils.mcp_client.create_mcp_client`` — the same guarded fastmcp seam
already used in this file for ``preview_creative``/``build_creative``, and
already proven redirect-refusing by ``tests/integration/test_mcp_client_egress.py``.
``_fetch_formats_operator``/``_fetch_signals_operator`` are now the only
operator-agent fetch paths; ``ADCPMultiAgentClient`` is gone from both
registries (confirmed by ``tests/unit/test_ruff_egress_bans.py``'s closed
exemption set, which no longer lists either file).

Same shape as ``tests/integration/test_mcp_client_egress.py``: an operator
agent answers ``302 -> <metadata stand-in>``, and the metadata stand-in's real
hit count over a real socket is the grade — not whether the call raised. A
pinned transport also refuses a wrong-host connect for its own reasons, so an
"assert the call failed" test would stay green even under the regression it
exists to catch (a followed redirect also ends in failure, just later). Only
the hit count on the redirect target distinguishes "refused" from "followed".
"""

from __future__ import annotations

import pytest

from src.core.creative_agent_registry import CreativeAgent, CreativeAgentRegistry
from src.core.signals_agent_registry import SignalsAgent, SignalsAgentRegistry
from tests.helpers.local_http_origin import run_local_origin
from tests.integration.property_list_helpers import allow_local_origin
from tests.integration.test_outbound_http import fast_backoff

pytestmark = [pytest.mark.integration]


class TestOperatorCreativeAgentRedirectIsRefused:
    """The guarded MCP seam refuses a redirect the OPERATOR creative-agent path is served."""

    @pytest.mark.timeout(30)
    async def test_operator_creative_agent_redirect_to_metadata_is_not_followed(self, local_origin_tls, monkeypatch):
        """An operator ``CreativeAgent`` answering ``302 -> metadata stand-in`` never reaches it.

        ``local_origin_tls`` stands in for a tenant-configured creative agent (an
        operator agent, not a buyer-supplied URL). ``_fetch_formats_operator``
        dials through ``create_mcp_client``, which pins the connection and sets
        ``follow_redirects=False`` — the redirect is never followed
        (``metadata_standin.hits == 0``), matching the fixed MCP-seam behavior
        in ``test_mcp_client_egress.py``.
        """
        allow_local_origin(monkeypatch)
        fast_backoff(monkeypatch)

        with run_local_origin() as metadata_standin:
            metadata_standin.close_without_responding()
            local_origin_tls.redirect_to(metadata_standin.base_url, status=302)

            agent = CreativeAgent(agent_url=local_origin_tls.base_url, name="operator-creative-agent")
            registry = CreativeAgentRegistry()

            with pytest.raises(Exception):  # noqa: B017 - a 302 is not a valid MCP handshake either way
                await registry._fetch_formats_operator(agent)

            assert local_origin_tls.hits >= 1, "the operator agent_url was never dialed — the test graded nothing"
            assert metadata_standin.hits == 0, (
                f"the redirect to the metadata stand-in was followed unguarded: {metadata_standin.requests}"
            )


class TestOperatorSignalsAgentRedirectIsRefused:
    """The guarded MCP seam refuses a redirect the OPERATOR signals-agent path is served."""

    @pytest.mark.timeout(30)
    async def test_operator_signals_agent_redirect_to_metadata_is_not_followed(self, local_origin_tls, monkeypatch):
        """A tenant-configured ``SignalsAgent`` answering ``302 -> metadata stand-in`` never reaches it."""
        allow_local_origin(monkeypatch)
        fast_backoff(monkeypatch)

        with run_local_origin() as metadata_standin:
            metadata_standin.close_without_responding()
            local_origin_tls.redirect_to(metadata_standin.base_url, status=302)

            agent = SignalsAgent(agent_url=local_origin_tls.base_url, name="operator-signals-agent")
            registry = SignalsAgentRegistry()

            with pytest.raises(Exception):  # noqa: B017 - a 302 is not a valid MCP handshake either way
                await registry._fetch_signals_operator(agent, brief="test brief")

            assert local_origin_tls.hits >= 1, "the operator agent_url was never dialed — the test graded nothing"
            assert metadata_standin.hits == 0, (
                f"the redirect to the metadata stand-in was followed unguarded: {metadata_standin.requests}"
            )

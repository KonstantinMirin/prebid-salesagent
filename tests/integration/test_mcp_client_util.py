"""Integration tests for unified MCP client utility.

These tests verify that our unified MCP client can connect to real MCP servers
and handle various scenarios (auth, retries, errors, etc.).
"""

import socket

import pytest


def _host_reachable(host: str, port: int = 443, timeout: float = 2.0) -> bool:
    """Check if an external host is reachable (DNS + TCP)."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except (OSError, TimeoutError):
        return False


_audience_agent_reachable = _host_reachable("audience-agent.fly.dev")
skip_no_audience_agent = pytest.mark.skipif(
    not _audience_agent_reachable,
    reason="audience-agent.fly.dev is not reachable",
)

from src.core.security.outbound_http import OutboundRequestBlocked
from src.core.utils import mcp_client as mcp_client_module
from src.core.utils.mcp_client import (
    MCPConnectionError,
    _build_auth_headers,
    create_mcp_client,
)

# A cloud-metadata address: refused by the egress seam unconditionally, escape
# hatches or not. Spelled as an MCP endpoint because that is the shape a
# tenant-registered agent URL arrives in.
METADATA_AGENT_URL = "https://169.254.169.254/mcp"


class TestBuildAuthHeaders:
    """Test auth header building logic."""

    def test_no_auth(self):
        """No auth config returns empty headers."""
        headers = _build_auth_headers(None)
        assert headers == {}

    def test_bearer_auth_default_header(self):
        """Bearer auth uses Authorization header by default."""
        auth = {"type": "bearer", "credentials": "token123"}
        headers = _build_auth_headers(auth)
        assert headers == {"Authorization": "Bearer token123"}

    def test_api_key_auth_default_header(self):
        """API key auth uses x-api-key header by default."""
        auth = {"type": "api_key", "credentials": "key123"}
        headers = _build_auth_headers(auth)
        assert headers == {"x-api-key": "key123"}

    def test_custom_auth_header(self):
        """Custom header name overrides default."""
        auth = {"type": "bearer", "credentials": "token123"}
        headers = _build_auth_headers(auth, auth_header="X-Custom-Auth")
        assert headers == {"X-Custom-Auth": "Bearer token123"}

    def test_generic_auth_type(self):
        """Unknown auth types use x-api-key with credentials as-is."""
        auth = {"type": "custom", "credentials": "secret123"}
        headers = _build_auth_headers(auth)
        assert headers == {"x-api-key": "secret123"}

    def test_missing_credentials(self):
        """Missing credentials returns empty headers."""
        auth = {"type": "bearer"}
        headers = _build_auth_headers(auth)
        assert headers == {}

    def test_missing_type(self):
        """Missing auth type returns empty headers."""
        auth = {"credentials": "token123"}
        headers = _build_auth_headers(auth)
        assert headers == {}


@pytest.mark.asyncio
class TestCreateMCPClient:
    """Test MCP client creation and connection."""

    @pytest.mark.skip_ci
    async def test_connect_to_creative_agent(self):
        """Can connect to AdCP creative agent (known good server)."""
        agent_url = "https://creative.adcontextprotocol.org/mcp"

        async with create_mcp_client(agent_url=agent_url, timeout=10) as client:
            # Should successfully connect
            assert client is not None

            # Should be able to list tools
            tools = await client.list_tools()
            assert isinstance(tools, list)
            assert len(tools) > 0

            # Should have expected tools
            tool_names = [tool.name for tool in tools]
            assert "list_creative_formats" in tool_names

    @pytest.mark.skip_ci
    @skip_no_audience_agent
    async def test_connect_to_audience_agent(self):
        """Can connect to audience/signals agent."""
        agent_url = "https://audience-agent.fly.dev"

        async with create_mcp_client(agent_url=agent_url, timeout=10) as client:
            # Should successfully connect
            assert client is not None

            # Should be able to list tools
            tools = await client.list_tools()
            assert isinstance(tools, list)
            assert len(tools) > 0

            # Should have expected tools
            tool_names = [tool.name for tool in tools]
            assert "get_signals" in tool_names

    async def test_unresolvable_host_is_refused_before_dialling(self):
        """Invalid URL raises MCPConnectionError after retries."""
        # Behaviour change (salesagent-jl08): an unresolvable host is now refused by
        # egress policy before any connection is attempted, rather than being dialled,
        # retried and reported as a connection failure. The seam cannot pin a
        # connection to an address it could not resolve, so it declines to try.
        agent_url = "https://nonexistent.example.com/mcp"

        with pytest.raises(OutboundRequestBlocked) as exc_info:
            async with create_mcp_client(agent_url=agent_url, timeout=5, max_retries=2):
                pass

        # Opaque by design: the refusal must not echo which host or address failed.
        assert "nonexistent.example.com" not in str(exc_info.value)

    async def test_respects_max_retries(self, monkeypatch):
        """Connection failures respect max_retries parameter."""
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_PRIVATE", "true")
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true")
        # A loopback port with nothing listening: resolves, fails fast, and the retry
        # budget is what is graded. It needs the hatches now only because policy refuses
        # loopback plain-http by default. NOT a live origin — create_mcp_client never
        # passes its timeout to the transport, so an origin that answers without speaking
        # MCP hangs instead of failing (a bug adjacent to this ticket, not fixed here).
        agent_url = "http://localhost:9999/mcp"

        with pytest.raises(MCPConnectionError) as exc_info:
            async with create_mcp_client(agent_url=agent_url, timeout=1, max_retries=1):
                pass

        # Should only try once
        assert "after 1 attempts" in str(exc_info.value)


@pytest.mark.asyncio
class TestURLHandling:
    """Test that URL handling respects user input."""

    @pytest.mark.skip_ci
    @skip_no_audience_agent
    async def test_respects_user_url_exactly(self):
        """Client uses the exact URL provided by user (no modifications)."""
        # Audience agent is at base URL (no path)
        agent_url = "https://audience-agent.fly.dev"

        async with create_mcp_client(agent_url=agent_url, timeout=10) as client:
            # Should use URL as-is
            tools = await client.list_tools()
            assert len(tools) > 0
            assert any(tool.name == "get_signals" for tool in tools)

    @pytest.mark.skip_ci
    async def test_strips_trailing_slashes_only(self):
        """Client strips trailing slashes but preserves path."""
        # URL with trailing slash
        agent_url = "https://creative.adcontextprotocol.org/mcp/"

        async with create_mcp_client(agent_url=agent_url, timeout=10) as client:
            # Should strip trailing slash but keep /mcp path
            tools = await client.list_tools()
            assert len(tools) > 0


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.skip_ci
    async def test_client_cleanup_on_error(self):
        """Client is properly cleaned up even if error occurs during usage."""
        agent_url = "https://creative.adcontextprotocol.org/mcp"

        # Context manager should handle cleanup gracefully
        async with create_mcp_client(agent_url=agent_url, timeout=10) as client:
            # Successfully connected, just verify we can use the client
            tools = await client.list_tools()
            assert len(tools) > 0

        # If we reach here without hanging, cleanup worked correctly
        assert True

    async def test_timeout_handling(self, monkeypatch):
        """Connection timeout is respected."""
        # Use a URL that will timeout (assuming nothing on port 9999)
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_PRIVATE", "true")
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true")
        # Unchanged target: a loopback port with nothing listening, which fails fast.
        # It needs the hatches now only because policy refuses loopback plain-http by
        # default. NOT repointed at a live origin: create_mcp_client accepts a timeout
        # and never passes it to the transport (mcp_client.py:101-107 vs the transport
        # construction), so an origin that ANSWERS but does not speak MCP hangs forever
        # rather than timing out. That bug is adjacent to this ticket and not fixed here.
        agent_url = "http://localhost:9999/mcp"

        with pytest.raises(MCPConnectionError):
            async with create_mcp_client(agent_url=agent_url, timeout=1, max_retries=1):
                pass


class _SleepRecordingAsyncio:
    """Stands in for the MCP client module's ``asyncio``, recording sleeps only.

    Replacing the name the module resolves — rather than setting
    ``asyncio.sleep`` on the real module — keeps the substitution scoped to the
    retry loop under test. The transport, anyio and the event loop keep the real
    ``asyncio.sleep``, so a hang or a deadlock observed in this test is the
    client's, not one this fixture introduced.
    """

    def __init__(self, real, slept: list[float]) -> None:
        self._real = real
        self._slept = slept

    async def sleep(self, seconds: float, *args, **kwargs) -> None:
        self._slept.append(seconds)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def recorded_retry_sleeps(monkeypatch):
    """Record every sleep the MCP client performs, without waiting any of them out.

    The sleep is the observation point, not the wall clock: a retry schedule of
    1s then 2s cannot be graded by timing a test, and waiting it out would make
    this file three seconds slower for no added signal.

    The replacement must be an ``async def`` — a plain ``MagicMock`` returns a
    non-awaitable and the client would ``TypeError`` on the await instead of
    failing on what is being graded. Same reason as ``record_sleeps`` in
    ``tests/integration/test_outbound_http.py``.
    """
    slept: list[float] = []
    monkeypatch.setattr(
        mcp_client_module,
        "asyncio",
        _SleepRecordingAsyncio(mcp_client_module.asyncio, slept),
    )
    return slept


@pytest.fixture
def egress_hatches_closed(monkeypatch):
    """Close both escape hatches explicitly, as the literal ``"false"``.

    Not optional and not a default: ``run_all_tests_host.sh`` and the e2e compose
    files export ``ADCP_OUTBOUND_ALLOW_PRIVATE`` / ``ADCP_OUTBOUND_ALLOW_INSECURE``
    for the creative-agent stack, so a test that merely assumed them unset would
    grade nothing on exactly the machines this suite runs on.
    """
    monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_PRIVATE", "false")
    monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "false")


@pytest.mark.asyncio
class TestRefusedAgentUrlIsNotDialled:
    """A refused agent URL propagates as a policy refusal, not a transport failure.

    ``create_mcp_client`` is the MCP seam's entry point, so the egress seam's
    address and scheme policy applies ONCE, at its top, before the connection
    candidates are built — outside the retry loop and outside the ``try`` whose
    arm is a bare ``except Exception``.

    Position is the whole obligation. Validating inside that loop would leave
    ``OutboundRequestBlocked`` caught, logged as "MCP connection attempt N/M
    failed", slept on, retried against the same blocked URL, retried again
    against the synthesised ``{url}/mcp`` candidate, and finally re-raised as
    ``MCPConnectionError`` — a policy refusal converted into a retried transport
    failure with the wrong class.

    Note what that means for the assertions: an origin-hit count of zero holds
    under BOTH designs, so it cannot be the grade on its own. The sleep
    assertion is what separates them.
    """

    # A correct refusal returns in microseconds — nothing is dialled. The bound
    # exists because the FAILING state is a hang, not a fast wrong answer:
    # `create_mcp_client` accepts a `timeout` and never passes it to the
    # transport, so a client that reaches the wire waits out the OS connect
    # timeout on an unroutable address, four times over. Without this the whole
    # slice dies with no report instead of failing with one.
    @pytest.mark.timeout(60)
    @pytest.mark.parametrize("destination", ["local-origin-loopback", "cloud-metadata"])
    async def test_refused_url_raises_blocked_without_dialling_or_retrying(
        self, destination, local_origin, egress_hatches_closed, recorded_retry_sleeps
    ):
        """The refusal is raised as-is, before the wire, and is never retried.

        Both destinations are refused by the seam for real reasons, not mocked
        ones: ``127.0.0.1`` is in a reserved range (and the URL is plain http),
        and ``169.254.169.254`` is the cloud-metadata address. The loopback case
        points at an origin that is genuinely listening and would answer, which
        is what makes ``hits == 0`` a statement about the client rather than
        about an address nothing could have reached anyway.
        """
        agent_url = local_origin.base_url if destination == "local-origin-loopback" else METADATA_AGENT_URL

        with pytest.raises(OutboundRequestBlocked):
            async with create_mcp_client(agent_url=agent_url, timeout=5, max_retries=3):
                pass

        assert local_origin.hits == 0, f"the client dialled a refused address: {local_origin.requests}"
        assert recorded_retry_sleeps == [], (
            f"a policy refusal was retried (slept {recorded_retry_sleeps}) — it was caught by the "
            "connection retry loop instead of being raised before it"
        )

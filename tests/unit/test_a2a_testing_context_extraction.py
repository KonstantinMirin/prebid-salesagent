"""Regression tests: test headers reach the implementation as a testing context.

Originally A2A-only, because A2A was the transport that dropped them: MCP extracted a
testing context from headers and A2A had no equivalent path, so X-Dry-Run and
X-Test-Session-ID sent to an A2A endpoint were silently ignored
(https://github.com/prebid/salesagent/pull/1066).

The extraction now happens once, in ``src/core/tools/_boundary.invoke_tool``, so there is no
per-transport path left to differ and the top class is written against the boundary and
parametrized over all three transports. That is not a weakening -- it is the same claim with
the per-transport hole closed, and it keeps grading a behaviour that has already regressed
once SINCE the collapse: the boundary briefly stopped forwarding testing_context at all,
thirteen readers took the None branch, nothing failed, and review caught it rather than a test
(fixed in 1e03f3671). A dropped testing context is silent by construction -- the field is
Optional and every reader has an else branch -- so it needs a test asserting the value ARRIVED.

The classes below it grade AdCPTestContext itself (parsing, and the UTC-awareness regression
from #1545) and are untouched by any of that.
"""

from types import MappingProxyType
from unittest.mock import patch

import pytest

from src.core.auth_context import AuthContext
from src.core.schemas import GetProductsRequest
from src.core.tools._boundary import invoke_tool
from tests.factories.principal import PrincipalFactory


def _credential(**headers: str) -> AuthContext:
    """The AuthContext UnifiedAuthMiddleware parks on ASGI scope state, built by hand."""
    base = {"authorization": "Bearer test-token", "x-adcp-tenant": "test-tenant"}
    return AuthContext(auth_token="test-token", headers=MappingProxyType({**base, **headers}))


async def _testing_context_reaching_the_resolver(credential: AuthContext, protocol: str):
    """Call the boundary and return the testing_context it handed the resolver."""
    identity = PrincipalFactory.make_identity(principal_id="test_principal", tenant_id="test-tenant", protocol=protocol)
    with patch("src.core.resolved_identity._resolve_identity", return_value=identity) as resolver:
        try:
            await invoke_tool("get_products", GetProductsRequest(brief="x"), credential, protocol)
        except Exception:
            # The IMPLEMENTATION may fail without a database. The resolver call happens
            # before it, and the resolver call is the subject.
            pass
    assert resolver.called, "invoke_tool did not resolve identity"
    return resolver.call_args.kwargs.get("testing_context")


@pytest.mark.parametrize("protocol", ["a2a", "mcp", "rest"])
class TestTestingContextReachesTheBoundary:
    """Every transport, one extraction. The parametrization IS the anti-regression."""

    async def test_dry_run_header_becomes_a_testing_context(self, protocol):
        ctx = await _testing_context_reaching_the_resolver(_credential(**{"x-dry-run": "true"}), protocol)
        assert ctx is not None, f"{protocol}: X-Dry-Run header did not reach the resolver as a testing context"
        assert ctx.dry_run is True, f"{protocol}: X-Dry-Run: true must set testing_context.dry_run=True"

    async def test_test_session_id_becomes_a_testing_context(self, protocol):
        ctx = await _testing_context_reaching_the_resolver(
            _credential(**{"x-test-session-id": "session-abc"}), protocol
        )
        assert ctx is not None, f"{protocol}: X-Test-Session-ID did not reach the resolver"
        assert ctx.test_session_id == "session-abc", (
            f"{protocol}: X-Test-Session-ID must arrive verbatim, got {ctx.test_session_id!r}"
        )

    async def test_no_test_headers_yields_no_testing_context(self, protocol):
        ctx = await _testing_context_reaching_the_resolver(_credential(), protocol)
        assert ctx is None or (ctx.dry_run is False and ctx.test_session_id is None), (
            f"{protocol}: a request carrying no test headers must not acquire a populated testing context, got {ctx!r}"
        )


class TestAdCPTestContextFromHeaders:
    """AdCPTestContext should have a from_headers classmethod for raw header dicts."""

    def test_from_headers_method_exists(self):
        """AdCPTestContext should have from_headers classmethod.

        Currently FAILS: Only from_context (takes FastMCP Context) exists.
        A2A needs from_headers (takes raw dict) for header extraction.
        """
        from src.core.testing_hooks import AdCPTestContext

        assert hasattr(AdCPTestContext, "from_headers"), (
            "AdCPTestContext needs a from_headers classmethod that extracts "
            "testing context from a raw headers dict (for A2A transport)."
        )

    def test_from_headers_extracts_dry_run(self):
        """from_headers should extract X-Dry-Run from raw headers dict."""
        from src.core.testing_hooks import AdCPTestContext

        if not hasattr(AdCPTestContext, "from_headers"):
            import pytest

            pytest.skip("from_headers not yet implemented")

        ctx = AdCPTestContext.from_headers({"x-dry-run": "true"})
        assert ctx.dry_run is True

    def test_from_headers_empty_dict_returns_none(self):
        """from_headers with empty dict should return None (no testing enabled)."""
        from src.core.testing_hooks import AdCPTestContext

        if not hasattr(AdCPTestContext, "from_headers"):
            import pytest

            pytest.skip("from_headers not yet implemented")

        ctx = AdCPTestContext.from_headers({})
        assert ctx is None, (
            "from_headers({}) should return None when no test headers present, "
            "to avoid creating a truthy AdCPTestContext that activates testing behavior."
        )


class TestMockTimeIsAlwaysAware:
    """mock_time is UTC-aware no matter how the context is constructed.

    Regression (#1545 K1 follow-up review): X-Mock-Time was minted NAIVE by
    from_headers (rstrip("Z") + fromisoformat, and local-time fromtimestamp for
    the epoch form) while campaign flight datetimes are UTC-aware, so
    NextEventCalculator.calculate_next_event_time raised
    'TypeError: can't compare offset-naive and offset-aware datetimes' and
    failed the whole get_media_buy_delivery request. The clock is now
    normalized once at the AdCPTestContext construction boundary.
    """

    def test_from_headers_iso_z_is_utc_aware(self):
        from datetime import UTC, datetime

        from src.core.testing_hooks import AdCPTestContext

        ctx = AdCPTestContext.from_headers({"x-mock-time": "2025-06-01T00:00:00Z"})
        assert ctx.mock_time == datetime(2025, 6, 1, tzinfo=UTC)
        assert ctx.mock_time.tzinfo is not None

    def test_from_headers_iso_without_offset_is_utc_aware(self):
        from datetime import UTC, datetime

        from src.core.testing_hooks import AdCPTestContext

        ctx = AdCPTestContext.from_headers({"x-mock-time": "2025-06-01T12:30:00"})
        assert ctx.mock_time == datetime(2025, 6, 1, 12, 30, tzinfo=UTC)

    def test_from_headers_epoch_is_utc_aware_and_utc_anchored(self):
        """Epoch seconds are UTC-anchored — 1748736000 is 2025-06-01T00:00:00Z.

        A naive fromtimestamp() would return *local* time; labeling that UTC
        would shift the simulated clock by the host's UTC offset.
        """
        from datetime import UTC, datetime

        from src.core.testing_hooks import AdCPTestContext

        ctx = AdCPTestContext.from_headers({"x-mock-time": "1748736000"})
        assert ctx.mock_time == datetime(2025, 6, 1, tzinfo=UTC)

    def test_direct_construction_with_naive_datetime_is_coerced_to_utc(self):
        from datetime import UTC, datetime

        from src.core.testing_hooks import AdCPTestContext

        ctx = AdCPTestContext(mock_time=datetime(2025, 6, 1))
        assert ctx.mock_time == datetime(2025, 6, 1, tzinfo=UTC)

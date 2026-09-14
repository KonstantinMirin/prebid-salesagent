"""AdCPTestContext parsing: from_headers, and the UTC-awareness regression from #1545.

This file used to also grade that the boundary hands the testing context to the
implementation on every transport. That is transport behaviour and is not graded by a unit
test any more; it is a BDD gap (see the step-1 report) until a scenario presents
``x-dry-run`` / ``x-test-session-id`` on the wire and reads the effect off the response.
"""


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

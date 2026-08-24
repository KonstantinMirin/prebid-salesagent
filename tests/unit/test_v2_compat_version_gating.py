"""Test v2 compat version gating.

V2 compat fields (is_fixed, rate, price_guidance.floor) should only be added
for pre-3.0 clients. Clients declaring adcp_version >= 3.0 should receive
clean V3 responses without backward-compat fields.
"""

from src.core.product_conversion import needs_v2_compat


class TestNeedsV2Compat:
    """Test the version gating helper."""

    def test_absent_version_assumes_the_pin(self):
        """No declared version means the PINNED version, so no v2 compat.

        This asserted the opposite -- None -> True, "for safety". That framing had
        it backwards: the unsafe outcome is emitting is_fixed / rate /
        price_guidance.floor, none of which exist in the pinned schema, to a
        caller that never asked for them. On an agent that declares itself 3.1.1,
        silence is not evidence of a legacy client, and defaulting to v2 made the
        NON-CONFORMANT shape the one you get by saying nothing.

        An unparseable version still gets compat (see below) -- that is a
        positive signal we cannot read the caller, which is a different thing
        from the caller sending nothing.
        """
        assert needs_v2_compat(None) is False

    def test_v1_needs_compat(self):
        """V1.x clients need v2 compat fields."""
        assert needs_v2_compat("1.0.0") is True

    def test_v2_needs_compat(self):
        """V2.x clients need v2 compat fields."""
        assert needs_v2_compat("2.2.0") is True
        assert needs_v2_compat("2.5.0") is True

    def test_v3_does_not_need_compat(self):
        """V3.0+ clients should NOT get v2 compat fields."""
        assert needs_v2_compat("3.0.0") is False

    def test_v3_minor_does_not_need_compat(self):
        """V3.x clients should NOT get v2 compat fields."""
        assert needs_v2_compat("3.1.0") is False
        assert needs_v2_compat("3.5.0") is False

    def test_future_v4_does_not_need_compat(self):
        """Future versions should NOT get v2 compat fields."""
        assert needs_v2_compat("4.0.0") is False

    def test_malformed_version_defaults_to_compat(self):
        """Malformed version strings should default to applying compat (safe default)."""
        assert needs_v2_compat("not-a-version") is True
        assert needs_v2_compat("") is True

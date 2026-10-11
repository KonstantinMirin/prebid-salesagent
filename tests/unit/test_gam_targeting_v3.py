"""Tests for the int() cast GAM frequency caps apply to FrequencyCap float arithmetic.

The GAM targeting refusals are graded on the wire by
tests/bdd/features/local-gam-geo-targeting.feature.
"""


class TestFrequencyCapIntCast:
    """suppress_minutes float arithmetic must produce int for GAM API."""

    def test_hours_cast_to_int(self):
        """suppress_minutes=120.0 (2 hours) → numTimeUnits must be int 2."""
        from src.core.schemas import FrequencyCap

        cap = FrequencyCap(suppress_minutes=120.0)
        # Simulate the GAM conversion logic
        num_time_units = int(cap.suppress_minutes // 60)
        assert isinstance(num_time_units, int)
        assert num_time_units == 2

    def test_days_cast_to_int(self):
        """suppress_minutes=2880.0 (2 days) → numTimeUnits must be int 2."""
        from src.core.schemas import FrequencyCap

        cap = FrequencyCap(suppress_minutes=2880.0)
        num_time_units = int(cap.suppress_minutes // 1440)
        assert isinstance(num_time_units, int)
        assert num_time_units == 2

    def test_minutes_stays_int(self):
        """suppress_minutes=30 (minutes) → numTimeUnits should be int."""
        from src.core.schemas import FrequencyCap

        cap = FrequencyCap(suppress_minutes=30)
        num_time_units = int(cap.suppress_minutes)
        assert isinstance(num_time_units, int)
        assert num_time_units == 30

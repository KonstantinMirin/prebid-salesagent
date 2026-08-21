"""Tests for city targeting rejection.

Regression tests for salesagent-hfz: ensures geo_city_any_of/geo_city_none_of
sent in targeting_overlay are caught by removed_dimensions() instead of
being silently dropped.

Updated for salesagent-17b: validation now accepts Targeting model directly.
The normalizer consumes geo_city_any_of/geo_city_none_of and sets
had_city_targeting=True — both fields produce a single violation (correct
semantics: city targeting was used, regardless of which field).
"""

from src.core.schemas import Targeting
from src.services.targeting_capabilities import (
    TARGETING_CAPABILITIES,
    get_overlay_dimensions,
    removed_dimensions,
)


class TestCityFieldsRejected:
    """geo_city_any_of and geo_city_none_of must produce violations."""

    def test_geo_city_any_of_violation(self):
        violations = removed_dimensions(Targeting(geo_city_any_of=["New York"]))
        assert violations == ["geo_city"]

    def test_geo_city_none_of_violation(self):
        violations = removed_dimensions(Targeting(geo_city_none_of=["Los Angeles"]))
        assert violations == ["geo_city"]

    def test_both_city_fields_produce_one_violation(self):
        """Both geo_city fields trigger the same had_city_targeting flag → 1 violation."""
        violations = removed_dimensions(Targeting(geo_city_any_of=["NYC"], geo_city_none_of=["LA"]))
        assert len(violations) == 1

    def test_city_reported_under_removed_not_managed_only(self):
        """The city dimension is reported as REMOVED, which is a different reason from
        managed-only, and the two must not be conflated.

        This used to assert the violation SENTENCE contained "removed" or "not supported".
        That wording is now CODE_TABLE's, not the validator's (salesagent-3dawm.9); what
        the validator owns is which dimension, and under which reason.
        """
        from src.services.targeting_capabilities import managed_only_dimensions

        overlay = Targeting(geo_city_any_of=["NYC"])
        assert removed_dimensions(overlay) == ["geo_city"]
        assert managed_only_dimensions(overlay) == []


class TestCityMixedWithValidFields:
    """Valid overlay fields alongside city fields should only flag city."""

    def test_valid_geo_plus_city_only_city_flagged(self):
        violations = removed_dimensions(Targeting(geo_countries=["US"], geo_city_any_of=["NYC"]))
        assert violations == ["geo_city"]

    def test_device_plus_city_only_city_flagged(self):
        violations = removed_dimensions(Targeting(device_type_any_of=["mobile"], geo_city_none_of=["LA"]))
        assert violations == ["geo_city"]


class TestGeoCityDimensionRemoved:
    """geo_city dimension should not appear in overlay dimensions."""

    def test_geo_city_not_in_overlay_dimensions(self):
        overlay = get_overlay_dimensions()
        assert "geo_city" not in overlay

    def test_geo_city_access_is_removed(self):
        cap = TARGETING_CAPABILITIES["geo_city"]
        assert cap.access == "removed"

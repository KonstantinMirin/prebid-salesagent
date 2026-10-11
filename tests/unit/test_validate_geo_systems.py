"""The system fields of TargetingCapabilities, which validate_geo_systems reads, stay in sync with its tuples.

What validate_geo_systems refuses is graded on the wire for the GAM adapter, which calls it,
by tests/bdd/features/local-gam-geo-targeting.feature.
"""

import dataclasses

from src.adapters.base import TargetingCapabilities

# Non-system boolean fields (geo_countries/geo_regions are top-level geo,
# not metro/postal system identifiers).
_NON_SYSTEM_FIELDS = {"geo_countries", "geo_regions"}


class TestFieldTupleSync:
    """_METRO_FIELDS and _POSTAL_FIELDS must cover all system boolean fields."""

    def test_tuples_cover_all_system_fields(self):
        """Every bool field except geo_countries/geo_regions must be in one tuple."""
        bool_fields = {f.name for f in dataclasses.fields(TargetingCapabilities) if f.type is bool or f.type == "bool"}
        system_fields = bool_fields - _NON_SYSTEM_FIELDS
        tuple_fields = set(TargetingCapabilities._METRO_FIELDS) | set(TargetingCapabilities._POSTAL_FIELDS)
        assert system_fields == tuple_fields, (
            f"Mismatch — fields not in tuples: {system_fields - tuple_fields}, "
            f"tuple entries not in dataclass: {tuple_fields - system_fields}"
        )

    def test_no_overlap_between_tuples(self):
        """Metro and postal tuples must not share entries."""
        overlap = set(TargetingCapabilities._METRO_FIELDS) & set(TargetingCapabilities._POSTAL_FIELDS)
        assert not overlap, f"Fields in both tuples: {overlap}"

    def test_tuple_entries_are_valid_field_names(self):
        """Every tuple entry must name an actual dataclass field."""
        all_field_names = {f.name for f in dataclasses.fields(TargetingCapabilities)}
        for name in TargetingCapabilities._METRO_FIELDS + TargetingCapabilities._POSTAL_FIELDS:
            assert name in all_field_names, f"'{name}' is in a tuple but not a dataclass field"

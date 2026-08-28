"""Tests for unknown targeting field rejection.

Regression tests for : ensures unknown buyer-submitted targeting
fields (typos, bogus fields) are rejected. With extra='forbid' in dev mode,
unknown fields are caught at construction time via ValidationError.
"""

import pytest

from src.core.schemas import Targeting


class TestForbidRejectsUnknownFields:
    """extra='forbid' should reject unknown fields at construction time."""

    def test_unknown_field_rejected(self):
        with pytest.raises(Exception, match="Extra inputs are not permitted"):
            Targeting(totally_bogus="hello", geo_countries=["US"])

    def test_known_field_accepted(self):
        """Known model fields must be accepted, model_extra stays None (extra='forbid')."""
        t = Targeting(geo_countries=["US"], device_type_any_of=["mobile"])
        assert t.geo_countries is not None
        assert t.model_extra is None

    def test_managed_field_accepted(self):
        """Managed-only fields are real model fields, accepted normally."""
        t = Targeting(axe_include_segment="foo", key_value_pairs={"k": "v"})
        assert t.axe_include_segment == "foo"
        assert t.model_extra is None

    def test_v2_normalized_field_accepted(self):
        """v2 field names consumed by normalizer should not cause rejection."""
        t = Targeting(geo_country_any_of=["CA"])
        assert t.geo_countries is not None
        assert t.model_extra is None

    def test_multiple_unknown_fields_rejected(self):
        with pytest.raises(Exception, match="Extra inputs are not permitted"):
            Targeting(bogus_one="a", bogus_two="b")


class TestValidateUnknownTargetingFields:
    """Unknown targeting fields are rejected by PYDANTIC, not by business logic.

    ``Targeting`` resolves ``extra`` through ``get_pydantic_extra_mode()``: ``forbid`` in
    dev/CI (rejected at construction, as the tests above assert) and ``ignore`` in
    production (silently dropped). A business-logic ``model_extra`` scan therefore could
    never fire, and was deleted in salesagent-3dawm.9.
    """

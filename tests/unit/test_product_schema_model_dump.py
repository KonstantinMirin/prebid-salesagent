"""Unit tests for Product schema model_dump branches.

Covers three untested branches in src/core/schemas/product.py:
1. publisher_properties validator — raises ValueError when empty
2. formats → format_ids rename in model_dump() — ensures correct wire format
3. Empty pricing_options=[] — response shape contract for anonymous users

These are pure Pydantic schema tests — no database or transport required.

Covers: salesagent-xsn4
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.schemas import Product
from tests.helpers.adcp_factories import (
    create_test_cpm_pricing_option,
    create_test_format_id,
    create_test_product,
    create_test_publisher_properties_by_tag,
)


class TestPublisherPropertiesValidator:
    """Product validator rejects empty publisher_properties."""

    def test_empty_list_raises_validation_error(self):
        """publisher_properties=[] raises ValidationError per AdCP spec (line 121).

        The library enforces min_length=1 on publisher_properties, which
        catches the empty list before our after-validator at line 120.
        Either way, empty publisher_properties is rejected.
        """
        with pytest.raises(ValidationError):
            create_test_product(publisher_properties=[])

    def test_none_raises_validation_error(self):
        """publisher_properties=None raises ValidationError per AdCP spec (line 120).

        The library field is non-optional with min_length=1, so None is
        rejected at the field level. Must bypass factory (it sets a default).
        """
        with pytest.raises(ValidationError):
            Product(
                product_id="test",
                name="Test",
                description="Test",
                publisher_properties=None,
                format_ids=[create_test_format_id("display_300x250")],
                delivery_type="guaranteed",
                pricing_options=[create_test_cpm_pricing_option()],
                delivery_measurement={"provider": "test", "notes": "Test"},
            )

    def test_valid_publisher_properties_accepted(self):
        """Non-empty publisher_properties passes validation."""
        product = create_test_product()
        assert len(product.publisher_properties) > 0


class TestFormatIdsRenameInModelDump:
    """model_dump() renames internal 'formats' to 'format_ids' for wire format."""

    def test_output_has_format_ids_not_formats(self):
        """model_dump() outputs 'format_ids', not 'formats' (line 203)."""
        product = create_test_product()
        data = product.model_dump()

        assert "format_ids" in data, "Wire format must use 'format_ids'"
        assert "formats" not in data, "'formats' must be renamed to 'format_ids'"

    def test_format_ids_preserves_values(self):
        """Renamed format_ids contains the correct values."""
        product = create_test_product(format_ids=["display_300x250", "video_1920x1080"])
        data = product.model_dump()

        assert "format_ids" in data
        assert len(data["format_ids"]) == 2


class TestEmptyPricingOptionsInModelDump:
    """model_dump() includes pricing_options=[] for anonymous user path.

    In production, products are constructed with valid pricing_options
    (min_length=1), then pricing_options is set to [] for anonymous users
    (see src/core/tools/products.py:852). model_dump() must preserve the
    empty list in the output to maintain the response shape contract.
    """

    def test_empty_pricing_options_included(self):
        """pricing_options=[] appears in model_dump() output (lines 222-226).

        Simulates the anonymous user path: product created with pricing,
        then pricing_options cleared before serialization.
        """
        product = create_test_product()
        # Simulate anonymous path: clear pricing after construction
        product.pricing_options = []
        data = product.model_dump()

        assert "pricing_options" in data, "Empty pricing_options must be present in output"
        assert data["pricing_options"] == []

    def test_populated_pricing_options_included(self):
        """Non-empty pricing_options also appear in output."""
        product = create_test_product()
        data = product.model_dump()

        assert "pricing_options" in data
        assert len(data["pricing_options"]) > 0


class TestCoreFieldsDoNotForceInvalidNull:
    """core_fields must never force-include a field the pinned schema types
    non-nullable (R3-8, salesagent-1zq3.8).

    Per the pinned core/product.json: format_ids is typed "array", which
    rejects null. The comment directly above core_fields already says
    format_ids "must not be force-included as null"; this pins that it
    actually behaves that way when unset, rather than only documenting it.
    """

    def test_format_ids_omitted_when_unset(self):
        """format_ids=None must not appear as an explicit null.

        Spec: core/product.json properties.format_ids is typed "array",
        which rejects null. Constructed directly (bypassing the factory,
        which always defaults format_ids) to get a Product with format_ids
        genuinely unset.
        """
        product = Product(
            product_id="test",
            name="Test",
            description="Test",
            publisher_properties=[create_test_publisher_properties_by_tag()],
            format_ids=None,
            delivery_type="guaranteed",
            pricing_options=[create_test_cpm_pricing_option()],
            reporting_capabilities={"metrics": ["impressions"]},
        )
        data = product.model_dump()

        assert "format_ids" not in data, (
            "format_ids=None must be omitted, not force-included as null "
            "(the pinned schema types it as a non-nullable array)"
        )


class TestReportingCapabilitiesAlwaysPresent:
    """reporting_capabilities is unconditionally required by the pinned
    core/product.json's top-level required array (salesagent-00pl.1) —
    unlike format_ids (only required via anyOf with format_options),
    Product.model_dump() must never omit it, even when unset on the model.
    When unset, model_dump() backfills the same minimal default
    product_conversion.py's primary path already provides, now from one
    shared source of truth instead of two.
    """

    def test_present_and_non_null_when_unset(self):
        """reporting_capabilities=None must still appear, backfilled with a default."""
        product = create_test_product(reporting_capabilities=None)
        data = product.model_dump()

        assert "reporting_capabilities" in data, (
            "reporting_capabilities is schema-required and must never be omitted, even when unset on the model"
        )
        assert data["reporting_capabilities"] is not None

    def test_preserves_explicit_value_when_set(self):
        """An explicitly-set reporting_capabilities is not overwritten by the default."""
        rc = {"available_metrics": ["impressions"], "expected_delay_minutes": 30}
        product = create_test_product(reporting_capabilities=rc)
        data = product.model_dump()

        assert data["reporting_capabilities"]["expected_delay_minutes"] == 30


class TestOptionalFieldsOmittedWhenUnset:
    """delivery_measurement and is_custom get the same omit-when-unset
    treatment as the core_fields above, but unlike format_ids and
    reporting_capabilities they are genuinely optional per the pinned
    core/product.json (not required) — so omission here is already correct
    behavior, not a bug. Pure test-coverage; no production code change.
    """

    def test_delivery_measurement_omitted_when_unset(self):
        """delivery_measurement=None must not appear as an explicit null.

        create_test_product(delivery_measurement=None) still defaults it to a
        populated dict (the factory treats None as "not provided"), so this
        constructs Product directly to get a genuinely unset field, same as
        test_format_ids_omitted_when_unset above.
        """
        product = Product(
            product_id="test",
            name="Test",
            description="Test",
            publisher_properties=[create_test_publisher_properties_by_tag()],
            format_ids=[create_test_format_id("display_300x250")],
            delivery_type="guaranteed",
            pricing_options=[create_test_cpm_pricing_option()],
            reporting_capabilities={"metrics": ["impressions"]},
            delivery_measurement=None,
        )
        data = product.model_dump()

        assert "delivery_measurement" not in data, (
            "delivery_measurement=None must be omitted from model_dump() output when unset"
        )

    def test_is_custom_omitted_when_unset(self):
        """is_custom=None must not appear as an explicit null.

        create_test_product() never sets is_custom, so it is unset by default.
        """
        product = create_test_product()
        data = product.model_dump()

        assert "is_custom" not in data, "is_custom=None must be omitted from model_dump() output when unset"

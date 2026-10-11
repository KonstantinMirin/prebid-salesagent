"""Unit tests for GAM pricing compatibility logic."""

import pytest

from src.adapters.gam.pricing_compatibility import PricingCompatibility
from src.core.exceptions import AdCPCapabilityNotSupportedError


class TestCompatibilityMatrix:
    """Test the GAM compatibility matrix accuracy."""

    def test_cpm_compatible_with_all_types(self):
        """CPM should work with all line item types."""
        for line_item_type in ["STANDARD", "SPONSORSHIP", "NETWORK", "PRICE_PRIORITY", "BULK", "HOUSE"]:
            assert PricingCompatibility.is_compatible(line_item_type, "cpm"), (
                f"CPM should be compatible with {line_item_type}"
            )

    def test_vcpm_compatible_with_standard_only(self):
        """VCPM should only work with STANDARD line items."""
        assert PricingCompatibility.is_compatible("STANDARD", "vcpm")

        # VCPM NOT compatible with other types
        for line_item_type in ["SPONSORSHIP", "NETWORK", "PRICE_PRIORITY", "BULK", "HOUSE"]:
            assert not PricingCompatibility.is_compatible(line_item_type, "vcpm"), (
                f"VCPM should NOT be compatible with {line_item_type}"
            )

    def test_cpc_compatible_types(self):
        """CPC should work with STANDARD, SPONSORSHIP, NETWORK, PRICE_PRIORITY."""
        compatible = {"STANDARD", "SPONSORSHIP", "NETWORK", "PRICE_PRIORITY"}
        incompatible = {"BULK", "HOUSE"}

        for line_item_type in compatible:
            assert PricingCompatibility.is_compatible(line_item_type, "cpc"), (
                f"CPC should be compatible with {line_item_type}"
            )

        for line_item_type in incompatible:
            assert not PricingCompatibility.is_compatible(line_item_type, "cpc"), (
                f"CPC should NOT be compatible with {line_item_type}"
            )

    def test_flat_rate_compatible_types(self):
        """FLAT_RATE (→CPD) should work with SPONSORSHIP and NETWORK only."""
        compatible = {"SPONSORSHIP", "NETWORK"}
        incompatible = {"STANDARD", "PRICE_PRIORITY", "BULK", "HOUSE"}

        for line_item_type in compatible:
            assert PricingCompatibility.is_compatible(line_item_type, "flat_rate"), (
                f"FLAT_RATE should be compatible with {line_item_type}"
            )

        for line_item_type in incompatible:
            assert not PricingCompatibility.is_compatible(line_item_type, "flat_rate"), (
                f"FLAT_RATE should NOT be compatible with {line_item_type}"
            )


class TestLineItemTypeSelection:
    """Test automatic line item type selection logic."""

    def test_flat_rate_selects_sponsorship(self):
        """FLAT_RATE pricing should select SPONSORSHIP type."""
        result = PricingCompatibility.select_line_item_type("flat_rate", is_guaranteed=False)
        assert result == "SPONSORSHIP"

    def test_vcpm_selects_standard(self):
        """VCPM pricing should select STANDARD type."""
        result = PricingCompatibility.select_line_item_type("vcpm", is_guaranteed=False)
        assert result == "STANDARD"

    def test_guaranteed_cpm_selects_standard(self):
        """Guaranteed CPM campaigns should select STANDARD type."""
        result = PricingCompatibility.select_line_item_type("cpm", is_guaranteed=True)
        assert result == "STANDARD"

    def test_non_guaranteed_cpm_selects_price_priority(self):
        """Non-guaranteed CPM campaigns should select PRICE_PRIORITY type."""
        result = PricingCompatibility.select_line_item_type("cpm", is_guaranteed=False)
        assert result == "PRICE_PRIORITY"

    def test_cpc_non_guaranteed_selects_price_priority(self):
        """Non-guaranteed CPC campaigns should select PRICE_PRIORITY type."""
        result = PricingCompatibility.select_line_item_type("cpc", is_guaranteed=False)
        assert result == "PRICE_PRIORITY"

    def test_cpc_guaranteed_selects_standard(self):
        """Guaranteed CPC campaigns should select STANDARD type."""
        result = PricingCompatibility.select_line_item_type("cpc", is_guaranteed=True)
        assert result == "STANDARD"


class TestGAMCostTypeMapping:
    """Test AdCP to GAM cost type conversion."""

    def test_supported_pricing_models(self):
        """Test conversion of supported pricing models."""
        assert PricingCompatibility.get_gam_cost_type("cpm") == "CPM"
        assert PricingCompatibility.get_gam_cost_type("vcpm") == "VCPM"
        assert PricingCompatibility.get_gam_cost_type("cpc") == "CPC"
        assert PricingCompatibility.get_gam_cost_type("flat_rate") == "CPD"

    def test_unsupported_pricing_models(self):
        """An unsupported pricing model is a buyer-correctable capability gap.

        Per the pinned spec (v3.1.1 enums/error-code.json) it must surface as
        UNSUPPORTED_FEATURE / correctable — a bare ValueError gets wrapped
        into SERVICE_UNAVAILABLE / transient ("retry the unretryable") by the
        impl's generic handler (salesagent-rdrs; se18 targeting precedent).
        """

        for unsupported in ["cpcv", "cpv", "cpp", "invalid"]:
            with pytest.raises(AdCPCapabilityNotSupportedError):
                PricingCompatibility.get_gam_cost_type(unsupported)


class TestCompatibleLineItemTypes:
    """Test getting all compatible line item types for a pricing model."""

    def test_get_compatible_types_for_cpm(self):
        """CPM should be compatible with all types."""
        compatible = PricingCompatibility.get_compatible_line_item_types("cpm")
        assert compatible == {"STANDARD", "SPONSORSHIP", "NETWORK", "PRICE_PRIORITY", "BULK", "HOUSE"}

    def test_get_compatible_types_for_vcpm(self):
        """VCPM should only be compatible with STANDARD."""
        compatible = PricingCompatibility.get_compatible_line_item_types("vcpm")
        assert compatible == {"STANDARD"}

    def test_get_compatible_types_for_cpc(self):
        """CPC should be compatible with 4 types."""
        compatible = PricingCompatibility.get_compatible_line_item_types("cpc")
        assert compatible == {"STANDARD", "SPONSORSHIP", "NETWORK", "PRICE_PRIORITY"}

    def test_get_compatible_types_for_flat_rate(self):
        """FLAT_RATE should be compatible with SPONSORSHIP and NETWORK."""
        compatible = PricingCompatibility.get_compatible_line_item_types("flat_rate")
        assert compatible == {"SPONSORSHIP", "NETWORK"}

    def test_get_compatible_types_for_unsupported_model(self):
        """Unsupported pricing models should return empty set."""
        compatible = PricingCompatibility.get_compatible_line_item_types("cpcv")
        assert compatible == set()

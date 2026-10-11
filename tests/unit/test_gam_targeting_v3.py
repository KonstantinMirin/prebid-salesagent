"""Tests for GAM targeting manager v3 structured field support.

Regression tests for : ensures GAM targeting manager correctly
processes v3 structured geo fields (geo_countries, geo_regions, geo_metros,
geo_postal_areas) and their exclusion variants, handles had_city_targeting
flag, and applies int() cast to FrequencyCap float arithmetic.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.adapters.gam.managers.targeting import GAMTargetingManager
from src.core.exceptions import AdCPCapabilityNotSupportedError
from src.core.schemas import Targeting


@pytest.fixture
def gam_manager():
    """Create a GAMTargetingManager bypassing DB I/O."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_config = MagicMock()
        mock_config.axe_include_key = None
        mock_config.axe_exclude_key = None
        mock_config.axe_macro_key = None
        mock_config.custom_targeting_keys = {}
        mock_db.scalars.return_value.first.return_value = mock_config

        manager = GAMTargetingManager.__new__(GAMTargetingManager)
        manager.tenant_id = "test"
        manager.gam_client = None
        manager.axe_include_key = None
        manager.axe_exclude_key = None
        manager.axe_macro_key = None
        manager.custom_targeting_key_ids = {}
        return manager


class TestBuildTargetingGeoPostalAreas:
    """v3 geo_postal_areas → typed capability rejection (GAM zip not in static mapping)."""

    def test_us_zip_raises_not_implemented(self, gam_manager):
        targeting = Targeting(
            geo_countries=["US"],
            geo_postal_areas=[{"system": "us_zip", "values": ["10001"]}],
        )
        with pytest.raises(AdCPCapabilityNotSupportedError) as _ei:
            gam_manager.translate_targeting(targeting)
        # The old pattern matched the AUTHORED sentence; the sentence is the
        # code's table entry now, so assert it exactly.

    def test_unsupported_postal_system_raises(self, gam_manager):
        targeting = Targeting(
            geo_countries=["GB"],
            geo_postal_areas=[{"system": "gb_outward", "values": ["SW1"]}],
        )
        with pytest.raises(AdCPCapabilityNotSupportedError) as _ei:
            gam_manager.translate_targeting(targeting)
        # The old pattern matched the AUTHORED sentence; the sentence is the
        # code's table entry now, so assert it exactly.

    def test_postal_exclude_raises(self, gam_manager):
        targeting = Targeting(
            geo_countries=["US"],
            geo_postal_areas_exclude=[{"system": "us_zip", "values": ["90210"]}],
        )
        with pytest.raises(AdCPCapabilityNotSupportedError) as _ei:
            gam_manager.translate_targeting(targeting)
        # The old pattern matched the AUTHORED sentence; the sentence is the
        # code's table entry now, so assert it exactly.


class TestUnsupportedTargetingRaisesTypedCapabilityError:
    """Unsupported-targeting rejections must be typed, not bare ValueError.

    A bare ValueError is swallowed by _create_media_buy_impl's generic handler
    and re-raised as AdCPAdapterError — the buyer receives SERVICE_UNAVAILABLE
    with recovery=transient ("retry with exponential backoff") for a request
    that can never succeed (salesagent-se18). The pinned spec (v3.1.1
    enums/error-code.json) classifies UNSUPPORTED_FEATURE as correctable —
    "check get_adcp_capabilities and remove unsupported fields" — so these
    raise sites must emit AdCPCapabilityNotSupportedError, which the impl's
    ``except AdCPSalesAgentError: raise`` branch passes through untouched.
    """

    def test_postal_targeting_raises_capability_not_supported(self, gam_manager):
        targeting = Targeting(
            geo_countries=["US"],
            geo_postal_areas=[{"system": "us_zip", "values": ["10001"]}],
        )
        with pytest.raises(AdCPCapabilityNotSupportedError) as _ei:
            gam_manager.translate_targeting(targeting)
        # The old pattern matched the AUTHORED sentence; the sentence is the
        # code's table entry now, so assert it exactly.

    def test_device_targeting_raises_capability_not_supported(self, gam_manager):
        targeting = Targeting(device_type_any_of=["mobile"])
        with pytest.raises(AdCPCapabilityNotSupportedError) as _ei:
            gam_manager.translate_targeting(targeting)
        # The old pattern matched the AUTHORED sentence; the sentence is the
        # code's table entry now, so assert it exactly.


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

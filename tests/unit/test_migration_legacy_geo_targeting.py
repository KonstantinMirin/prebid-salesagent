"""The one check on the legacy-geo data migration's pure transform.

``Targeting.normalize_legacy_geo`` used to rewrite flat v2 geo keys on every validation.
It is deleted; the rewrite now happens once, in migration f7c3a9d21b64. This grades the
transform the migration applies, without a database.
"""

import importlib.util
from pathlib import Path

_PATH = Path("alembic/versions/f7c3a9d21b64_migrate_legacy_flat_geo_targeting.py")


def _migration():
    spec = importlib.util.spec_from_file_location("migration_legacy_geo", _PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_legacy_keys_become_v3_structured_fields():
    migration = _migration()
    doc = {
        "geo_country_any_of": ["US", "CA"],
        "geo_region_any_of": ["CA", "NY", "CA-ON"],
        "geo_metro_none_of": ["501"],
        "geo_zip_any_of": ["10001"],
        "geo_city_any_of": ["Boston"],
        "device_platform": ["ios"],
    }
    assert migration.upgrade_targeting_doc(doc) == {
        "geo_countries": ["US", "CA"],
        "geo_regions": ["US-CA", "US-NY", "CA-ON"],
        "geo_metros_exclude": [{"system": "nielsen_dma", "values": ["501"]}],
        "geo_postal_areas": [{"system": "us_zip", "values": ["10001"]}],
        "device_platform": ["ios"],
    }


def test_structured_key_already_present_wins_and_legacy_key_is_dropped():
    migration = _migration()
    assert migration.upgrade_targeting_doc({"geo_country_any_of": ["US"], "geo_countries": ["GB"]}) == {
        "geo_countries": ["GB"]
    }


def test_document_without_legacy_keys_is_untouched():
    migration = _migration()
    assert migration.upgrade_targeting_doc({"geo_countries": ["US"]}) is None
    assert migration.upgrade_package_config({"targeting_overlay": {"geo_countries": ["US"]}, "budget": 1}) is None


def test_package_config_is_rewritten_under_either_document_key():
    migration = _migration()
    config = {"targeting": {"geo_zip_none_of": ["02134"]}, "budget": 1}
    assert migration.upgrade_package_config(config) == {
        "targeting": {"geo_postal_areas_exclude": [{"system": "us_zip", "values": ["02134"]}]},
        "budget": 1,
    }
    assert config == {"targeting": {"geo_zip_none_of": ["02134"]}, "budget": 1}, "the input is not mutated"

"""A seller that runs Google Ad Manager, for envs that drive the REAL GAM adapter.

An env that replaces the whole adapter cannot say what the seller sent GAM or how it read
GAM's answer. The envs that grade those keep the adapter and stand in only for GAM's SOAP
client (``tests/helpers/gam_client``), patched as ``gam_client``. This module seeds the
rows production's ``get_adapter`` builds the ``GoogleAdManager`` adapter from.
"""

from __future__ import annotations

from typing import Any

#: The ``EXTERNAL_PATCHES`` entry for GAM's SOAP client.
GAM_CLIENT_PATCH = {"gam_client": "src.adapters.google_ad_manager.GAMClientManager"}

#: The synced ad unit a GAM product books into. GAM ad unit ids are numeric, and the
#: adapter refuses any other.
GAM_AD_UNIT_ID = "23312403856"


def seed_gam_seller(env: Any, tenant: Any, principal: Any) -> None:
    """Make *tenant* a GAM seller and *principal* a GAM advertiser in it.

    Seeds the tenant's ad server, its GAM ``AdapterConfig`` and the synced ad unit (the
    setup checklist refuses a GAM tenant with no synced inventory). ``gam_refresh_token``
    only has to be present: the adapter refuses a config with no credential at
    construction, and nothing authenticates against the stand-in.
    """
    from src.core.database.models import AdapterConfig
    from tests.factories.core import AdapterConfigFactory, GAMInventoryFactory

    tenant.ad_server = "google_ad_manager"
    principal.platform_mappings = {"google_ad_manager": {"advertiser_id": "123456789"}}
    GAMInventoryFactory(tenant=tenant, inventory_id=GAM_AD_UNIT_ID)
    config = env.get_session().get(AdapterConfig, tenant.tenant_id) or AdapterConfigFactory(tenant=tenant)
    config.adapter_type = "google_ad_manager"
    config.gam_network_code = "123456"
    config.gam_trafficker_id = "654321"
    config.gam_refresh_token = "test_refresh_token"
    env._commit_factory_data()

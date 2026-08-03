"""AVAILABLE_ADAPTERS must accept every ADAPTER_REGISTRY key it's supposed to.

PR #1838 review (dedup/consistency/layering lenses): src.core.main.AVAILABLE_ADAPTERS
hand-re-enumerated ADAPTER_REGISTRY's keys instead of deriving from it, and had
already drifted — missing 'broadstreet' and 'google_ad_manager'. A tenant/deployment
configured with either was silently downgraded to 'mock' at startup
(src.core.main:216-218) even though the adapter is fully registered and importable.
"""

from src.adapters import ADAPTER_REGISTRY
from src.core.main import AVAILABLE_ADAPTERS

# creative_engine is a creative-processing base class, not a selectable ad-server
# adapter (see CLAUDE.md "Adapter Support" — registry keys vs ad-server adapters).
NON_AD_SERVER_REGISTRY_KEYS = {"creative_engine"}


def test_every_ad_server_registry_key_is_available_for_selection():
    ad_server_keys = set(ADAPTER_REGISTRY) - NON_AD_SERVER_REGISTRY_KEYS
    missing = ad_server_keys - set(AVAILABLE_ADAPTERS)
    assert not missing, (
        f"ADAPTER_REGISTRY key(s) {missing} are registered ad-server adapters but "
        f"AVAILABLE_ADAPTERS doesn't accept them — a tenant configured with one of "
        f"these would be silently downgraded to 'mock' at startup."
    )


def test_available_adapters_has_no_stale_entries():
    """Every AVAILABLE_ADAPTERS entry must actually resolve in ADAPTER_REGISTRY."""
    stale = set(AVAILABLE_ADAPTERS) - set(ADAPTER_REGISTRY)
    assert not stale, f"AVAILABLE_ADAPTERS references unregistered adapter(s): {stale}"

"""Guard: no second hand-written OIDC discovery-URL dict.

Disease (PR #1838 review, consistency lens): src/admin/blueprints/auth.py and
src/services/auth_config_service.py each hand-typed their own OIDC_PROVIDERS
dict — same domain concept (well-known OIDC discovery URL by provider name),
independently maintained, with no test catching drift. auth_config_service.py
was missing okta/auth0/keycloak entirely. Both now derive from
src.core.oidc_providers.OIDC_DISCOVERY_URLS, the single source of truth.

This guard bans a dict literal mapping >=2 known OIDC provider names to a
discovery-URL-shaped string constant (or None) anywhere outside the canonical
module.
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import (
    REPO_ROOT,
    find_dict_literals_with_matching_entries,
    format_failure,
    scan_for_ast_violations,
)

CANONICAL_FILE = "src/core/oidc_providers.py"
GUARD_FILE = "tests/unit/test_guards_no_duplicate_oidc_providers.py"

KNOWN_PROVIDER_NAMES = {"google", "microsoft", "okta", "auth0", "keycloak"}
MIN_MATCHING_ENTRIES = 2


def _is_discovery_url_shaped_value(_provider_name: str, value: ast.expr) -> bool:
    """True for a well-known-openid-configuration URL string, or None."""
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    return isinstance(value, ast.Constant) and isinstance(value.value, str) and "openid-configuration" in value.value


def find_duplicate_oidc_provider_dicts(tree: ast.Module) -> list[int]:
    return find_dict_literals_with_matching_entries(
        tree,
        key_matches=lambda name: name in KNOWN_PROVIDER_NAMES,
        value_matches=_is_discovery_url_shaped_value,
        min_matches=MIN_MATCHING_ENTRIES,
    )


def test_no_duplicate_oidc_provider_dict():
    exclude = frozenset({CANONICAL_FILE, GUARD_FILE})
    violations = scan_for_ast_violations(REPO_ROOT, exclude=exclude, finder=find_duplicate_oidc_provider_dicts)
    assert not violations, format_failure(
        summary="A hand-written dict literal re-implements the OIDC provider discovery-URL map",
        violations=violations,
        fix_hint="Import OIDC_DISCOVERY_URLS from src.core.oidc_providers instead of hand-writing a "
        "new copy of the provider -> discovery-URL mapping — two independent copies is exactly what "
        "let auth_config_service.py silently drop okta/auth0/keycloak.",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def test_detector_catches_known_bad_shape():
    bad = (
        "OIDC_PROVIDERS = {\n"
        '    "google": "https://accounts.google.com/.well-known/openid-configuration",\n'
        '    "microsoft": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",\n'
        "}\n"
    )
    assert find_duplicate_oidc_provider_dicts(ast.parse(bad))


def test_detector_ignores_alias_of_shared_constant():
    fixed = "from src.core.oidc_providers import OIDC_DISCOVERY_URLS\nOIDC_PROVIDERS = OIDC_DISCOVERY_URLS\n"
    assert find_duplicate_oidc_provider_dicts(ast.parse(fixed)) == []


def test_detector_ignores_filtered_derivation():
    """auth_config_service.py's filtered subset (dict comprehension) is not a literal."""
    fixed = (
        "from src.core.oidc_providers import OIDC_DISCOVERY_URLS\n"
        "OIDC_PROVIDERS = {name: url for name, url in OIDC_DISCOVERY_URLS.items() if url is not None}\n"
    )
    assert find_duplicate_oidc_provider_dicts(ast.parse(fixed)) == []


def test_detector_ignores_single_entry_dict():
    """A single provider entry isn't the roster-duplication disease (needs >=2)."""
    fine = 'SOME_CONFIG = {"google": "https://accounts.google.com/.well-known/openid-configuration"}\n'
    assert find_duplicate_oidc_provider_dicts(ast.parse(fine)) == []


def test_detector_ignores_unrelated_dict():
    unrelated = 'VALID_STATUSES = {"active": True, "closed": False}\n'
    assert find_duplicate_oidc_provider_dicts(ast.parse(unrelated)) == []

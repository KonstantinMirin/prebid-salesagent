"""Lock test for the e2e_rest known-failures ledger (#1418, Wave 3).

The ledger (``tests/bdd/e2e_rest_known_failures.txt``) is a shrinking work-list of
e2e_rest BDD scenarios that fail over real HTTP. Wave 3 graduated every scenario
that now passes in-network and moved every format-injection-only scenario to an
env-level ``E2EUnsupportedSetup`` declaration (surfaced as xfail by the conftest
report hook, NOT listed in the ledger). What remains are genuine production /
harness gaps, enumerated below.

This test pins that end state so the ledger cannot silently drift:

* a removed entry that creeps back (a graduation regression) fails here;
* a genuine-gap entry deleted without landing the underlying fix fails here;
* the conftest loader must still read the same file the BDD suite xfails against.

When a gap is genuinely fixed (its scenario now passes in-network) or moved to an
env declaration, remove it from BOTH the ledger file and ``EXPECTED_LEDGER`` below
in the same change.
"""

from __future__ import annotations

from pathlib import Path

# The 9 genuine-gap e2e_rest nodeids remaining (2 date-range boundary graduated
# + 2 merged-upstream account rows added on the first in-network CI run, 2026-07-09;
# the 2 date-range partition twins graduated at the origin/pr-1417 merge —
# d4af23095 removed them from its ledger on strict-xfail XPASS in-network, the
# positive evidence they were pending) (47 after Wave 3 triage; jdy1
# graduated M3 6 get_products tenant-duplicate, M1 6 uc004 REST-422 wire-shape,
# M4 4 uc004 webhook-observability entries [now tag-declared in conftest]; the
# uc004 attribution campaign-interval boundary graduated at the main merge after
# upstream re-pointed its expected cell at error "VALIDATION_ERROR"; 12 uc006
# account billing-state entries graduated at the #1417 merge — its account
# resolution wiring makes them pass, xpass confirmed innet_040726_0013; 3 uc002
# creative extension entries imported at the #1417 merge — newly wired there,
# confirmed still failing in-network post-merge, innet_040726_0013; the uc004
# roas/cpa entry retired at #1430 item 4 — its Then steps now exist and the
# scenario is tag-declared T-UC-004-aggregated-roas-and-cpa on ALL transports;
# #1430 items 1-3 graduated the 6 uc011 read-back entries [_db_scope_for repoint
# + agent auth_token fix] and 2 uc002 ext-o/ext-p entries [auto-approval seeding],
# all 8 xpassed in-network, innet_050726_2030; the uc002 ext-q upload entry
# graduated after the fail_on_upload mock-fidelity + catalog-format +
# run_async_in_sync_context format-resolution fixes, verified in-network).
# Grouped by gap in the ledger file's section comments; flat here for exact-set
# comparison.
EXPECTED_LEDGER: frozenset[str] = frozenset(
    {
        # All four date-range invalid rows graduated: boundary rows 2026-07-09
        # (#1270 tripwires fired on the first in-network CI run — live server
        # validates start>=end now), partition twins at the origin/pr-1417 merge
        # (d4af23095, strict-xfail XPASS in-network).
        # Account valid rows graduated at the #1417 merge (jr5b seeded-account
        # Given; XPASS in-network innet_140726_1516) — see ledger note.
        "tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_include_package_daily_breakdown_boundary__boundary_point[e2e_rest-string 'true' (non-boolean type)-\"true\"-invalid]",
        "tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_principal_ownership_boundary__boundary_point[e2e_rest-principal differs from owner-invalid]",
        "tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_principal_ownership_partition__partition[e2e_rest-owner_mismatch-invalid]",
        'tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_reporting_dimensions_boundary__boundary_point[e2e_rest-geo with geo_level=metro but no system (behavioral gap)-{"geo": {"geo_level": "metro"}}-invalid]',
        "tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_sampling_method_boundary__boundary_point[e2e_rest-Unknown string not in enum-systematic-invalid]",
        "tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_seller_ignores_attribution_request__returns_platform_default[e2e_rest]",
        "tests/bdd/test_uc011_manage_accounts.py::test_push_notification_for_async_status_changes__with_push_notification[e2e_rest]",
        # Added by bug-triage epic salesagent-jl20 (2026-07-16): 2 genuine e2e-only
        # gaps surfaced by un-xfailing dn2s/mkso's scenarios — see ledger file
        # section comments for full root-cause analysis of each.
        # uc010 auth-data-identity graduated at salesagent-zna9 (_resolve_auth_dep
        # now resolves tenant from headers regardless of credential presence).
        # uc003 ext-a-unknown graduated at salesagent-z9e0 (harness identity_for()
        # now nulls principal_id on a failed token->principal DB lookup, mirroring
        # production's resolve_identity() — all transports agree now).
        # UC-010 capability-degradation scenarios added 2026-07-24 (eiww batches
        # chbi/tmpd): mock-incompatible on e2e_rest — Givens inject adapter/DB
        # failure or a specific adapter targeting config not realizable over real
        # HTTP; they run + assert on a2a/mcp/rest, only e2e_rest cannot set up the
        # precondition. Mirrored in tests/bdd/e2e_rest_known_failures.txt.
        "tests/bdd/test_uc010_discover_seller_capabilities.py::test_degraded_response_is_always_schemavalid[e2e_rest]",
        "tests/bdd/test_uc010_discover_seller_capabilities.py::test_targeting_capability_configurations__partition[e2e_rest-adapter_unavailable_defaults adapter unavailable (production defaults apply)-adapter unavailable-targeting equals exactly {geo_countries: true, geo_regions: true}]",
        "tests/bdd/test_uc010_discover_seller_capabilities.py::test_degradation_path__partition[e2e_rest-adapter_fail-a tenant is resolvable but adapter is unavailable-primary_channels equals [display] and targeting equals exactly {geo_countries: true, geo_regions: true} with no reporting_delivery_methods, audience_targeting or conversion_tracking]",
        "tests/bdd/test_uc010_discover_seller_capabilities.py::test_degradation_path__partition[e2e_rest-adapter_and_db_fail-a tenant is resolvable but both adapter and DB fail-primary_channels equals [display] and publisher_domains equals the placeholder domain, adapter-dependent sections absent]",
        "tests/bdd/test_uc010_discover_seller_capabilities.py::test_degradation_path__partition[e2e_rest-db_fail-a tenant is resolvable but database query fails-publisher_domains equals the placeholder domain and primary_channels equals [display, social, ctv]]",
        "tests/bdd/test_uc010_discover_seller_capabilities.py::test_targeting_capability_configurations__partition[e2e_rest-nested_absent no nested sub-properties declared-no nested sub-properties true-geo_metros and geo_postal_areas absent from targeting]",
    }
)

_LEDGER_PATH = Path(__file__).parent.parent / "bdd" / "e2e_rest_known_failures.txt"


def _load_ledger_nodeids() -> frozenset[str]:
    """Parse the ledger the way the conftest loader does (drop comments/blanks)."""
    return frozenset(
        line.strip()
        for line in _LEDGER_PATH.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_ledger_matches_expected_genuine_gaps() -> None:
    """The ledger file contains exactly the pinned genuine-gap nodeids."""
    actual = _load_ledger_nodeids()
    crept_back = actual - EXPECTED_LEDGER
    disappeared = EXPECTED_LEDGER - actual
    assert actual == EXPECTED_LEDGER, (
        "e2e_rest ledger drifted from its pinned Wave-3 end state.\n"
        f"Entries that crept back in (un-graduate them or update EXPECTED_LEDGER): {sorted(crept_back)}\n"
        f"Entries removed without updating this test: {sorted(disappeared)}"
    )


def test_ledger_entries_are_e2e_rest_bdd_nodeids() -> None:
    """Every ledger entry is a tests/bdd e2e_rest scenario nodeid."""
    for nodeid in _load_ledger_nodeids():
        assert nodeid.startswith("tests/bdd/"), f"non-bdd ledger entry: {nodeid}"
        assert "::" in nodeid, f"ledger entry is not a nodeid: {nodeid}"
        assert "e2e_rest" in nodeid, f"ledger entry is not an e2e_rest variant: {nodeid}"


def test_conftest_loader_reads_this_ledger() -> None:
    """The BDD conftest loads the same ledger this test pins.

    Guards against the loader being deleted or pointed elsewhere while the file
    still exists — that would silently stop xfailing these known failures.
    """
    from tests.bdd.conftest import _E2E_REST_KNOWN_FAILURES

    assert _E2E_REST_KNOWN_FAILURES == EXPECTED_LEDGER

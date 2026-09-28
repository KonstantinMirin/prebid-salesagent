"""Lock test for the storyboard-conformance known-failures ledger (the storyboard-conformance job).

Mirrors ``tests/unit/test_e2e_rest_ledger_state.py`` verbatim in shape: the storyboard
CI job (the storyboard-conformance job) grades a MEASURED run of the real ``@adcp/sdk`` storyboard runner through
pytest as ordinary parametrized tests -- one per ``(protocol, track, storyboard_id,
step_id)``, the runner being executed once per protocol (mcp, a2a) against the same
agent -- reusing the exact ledger/xfail/lock-test discipline already established by
``tests/bdd/e2e_rest_known_failures.txt`` rather than inventing a second comparator
system (Core Invariant). That means a sibling ledger file
(``tests/storyboard/known_failures.txt``), a conftest loader
(``tests/storyboard/conftest.py``) that reads it to xfail(strict=False) exactly those
known-failing storyboard test ids, and this lock test pinning the ledger's exact
contents so it cannot silently drift -- the same triad as the e2e_rest precedent.

Per the Core Invariant, an entry must be seeded from a MEASURED in-network CI run,
never re-derived/inferred (the architect review's HIGH finding: the runner's host-side
numbers do not carry over to the in-network receiver topology).

The ledger holds the measured gap surface, and ``EXPECTED_LEDGER`` below pins it
entry-for-entry: adding or removing a line in one file without the other fails this module.

RE-SEEDING is a standing rule, not a one-off: whenever a run seeds or retires
entries, update the ledger file AND ``EXPECTED_LEDGER`` below in the same change.
Same discipline as the e2e_rest docstring — a removed entry that creeps back is a
graduation regression; a genuine-gap entry deleted without landing the underlying fix
is a silent gap-hiding regression.
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit import ledger
from tests.helpers.ledger import load_ledger_nodeids

# --- ledger pin ---
# Re-seeded from ONE measured in-network run, test-results/innet_180926_2349, which scored
# passed=49 failed=16 on both protocols with zero disparity. 18 mcp + 18 a2a, every failing
# check failing on both surfaces -- so an asymmetric pair appearing here is an mcp-only fix
# that left its a2a twin behind, which is the drift the per-protocol split exists to expose.
# (The runner's own ``failed`` counter reads 16 while its per-check ``failures`` array carries
# 18 records; the ledger keys on the records. Same shape as the first seeding's 23-vs-21.)
#
# WHAT MOVED, against the first seeding (innet_160926_1917, passed=30, 46 entries): 26 entries
# graduated when the account-seeding fix took the score 30 -> 49, and 16 checks that the
# resulting skip cascade had masked began executing and failing. Both halves are itemised in
# the header of tests/storyboard/known_failures.txt. Net 46 -> 36.
#
# The pass count is floored separately, in ``.storyboard-pass-floor``, because no pytest
# outcome carries it: a check degrading from PASS to SKIP deletes its own failing item, so
# this file alone cannot catch it. The floor moves with a re-seed, in the same change.
#
# Re-seed all three in the same change, always, and only from a measured run.
EXPECTED_LEDGER: frozenset[str] = frozenset(
    {
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::creative::media_buy_seller/creative_reception::list_formats]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/creative_fate_after_cancellation::list_creatives_before_cancel]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/dependency_impairment::assign_creative_to_package]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/dependency_impairment_cardinality::create_buy_two_packages]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inline_creatives_without_sync::create_buy_with_legacy_inline_creative]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inline_creatives_without_sync::get_products_canonical_format]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/invalid_transitions::second_cancel]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inventory_list_no_match::create_buy_no_match]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inventory_list_targeting::create_buy_with_lists]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/measurement_terms_rejected::create_media_buy_aggressive_terms]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/measurement_terms_rejected::create_media_buy_relaxed_terms]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::security::security_baseline::probe_api_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::creative::media_buy_seller/creative_reception::list_formats]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/creative_fate_after_cancellation::list_creatives_before_cancel]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/dependency_impairment::assign_creative_to_package]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/dependency_impairment_cardinality::create_buy_two_packages]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inline_creatives_without_sync::create_buy_with_legacy_inline_creative]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inline_creatives_without_sync::get_products_canonical_format]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/invalid_transitions::second_cancel]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inventory_list_no_match::create_buy_no_match]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inventory_list_targeting::create_buy_with_lists]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/measurement_terms_rejected::create_media_buy_aggressive_terms]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/measurement_terms_rejected::create_media_buy_relaxed_terms]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::probe_api_key]",
    }
)


_LEDGER_PATH = Path(__file__).parent.parent / "storyboard" / "known_failures.txt"


def _load_ledger_nodeids() -> frozenset[str]:
    """Parse the ledger the way the storyboard conftest loader must.

    Same format as ``tests/bdd/e2e_rest_known_failures.txt``: one test-id-equivalent
    identifier per line, ``#``-prefixed comment lines and blank lines dropped.
    """
    return load_ledger_nodeids(_LEDGER_PATH)


def test_ledger_matches_expected_genuine_gaps() -> None:
    """The storyboard ledger file contains exactly the pinned genuine-gap entries."""
    actual = _load_ledger_nodeids()
    crept_back = actual - EXPECTED_LEDGER
    disappeared = EXPECTED_LEDGER - actual
    assert actual == EXPECTED_LEDGER, (
        "storyboard-conformance ledger drifted from its pinned state.\n"
        f"Entries that crept back in (un-graduate them or update EXPECTED_LEDGER): {sorted(crept_back)}\n"
        f"Entries removed without updating this test: {sorted(disappeared)}"
    )


def test_ledger_entries_are_storyboard_conformance_test_ids() -> None:
    """Every ledger entry identifies a tests/storyboard parametrized check.

    Mirrors the e2e_rest ledger's nodeid-shape guard (test_ledger_entries_are_e2e_rest_bdd_nodeids):
    entries key on (protocol, track, storyboard_id, step_id) per the Core Invariant, carried as a
    pytest parametrize id on the storyboard-conformance test module -- not a free-text
    reason (reason/reason_kind are non-key annotations reported on failure, per plan
    step 2, never part of the ledger identity). Parsed through the shared grammar
    (scripts.audit.ledger.LedgerCheckId) rather than a hand-rolled partition split --
    a malformed entry now fails loudly (parse() returns None) instead of silently
    mis-parsing a prefix.
    """
    for entry in _load_ledger_nodeids():
        assert entry.startswith("tests/storyboard/"), f"non-storyboard ledger entry: {entry}"
        assert "::" in entry, f"ledger entry is not a test id: {entry}"
        parsed = ledger.LedgerCheckId.parse(entry)
        assert parsed is not None, f"ledger entry does not match the check-id grammar: {entry}"
        assert parsed.protocol in {"mcp", "a2a"}, f"ledger entry has no known protocol prefix: {entry}"


def test_conftest_loader_reads_this_ledger() -> None:
    """The storyboard-conformance conftest loads the same ledger this test pins.

    Asserts the loader's PATH, not only the set it produced. Two empty sets compare
    equal however the loader was wired, so a path assertion is the only form of this
    check that still bites while the ledger holds no entries -- and pointing the loader
    elsewhere is the silent breakage the ledger/lock-test triad exists to prevent.
    """
    from tests.storyboard import conftest

    assert conftest._LEDGER_PATH.resolve() == _LEDGER_PATH.resolve()
    assert _LEDGER_PATH.is_file(), f"the pinned ledger file is missing: {_LEDGER_PATH}"
    assert conftest._STORYBOARD_KNOWN_FAILURES == EXPECTED_LEDGER

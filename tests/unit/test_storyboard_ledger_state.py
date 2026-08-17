"""Lock test for the storyboard-conformance known-failures ledger (SB-4b, salesagent-syhj).

Mirrors ``tests/unit/test_e2e_rest_ledger_state.py`` verbatim in shape: the storyboard
CI job (SB-4b) grades a MEASURED run of the real ``@adcp/sdk`` storyboard runner through
pytest as ordinary parametrized tests -- one per ``(protocol, track, storyboard_id,
step_id)``, the runner being executed once per protocol (mcp, a2a) against the same
agent -- reusing the exact ledger/xfail/lock-test discipline already established by
``tests/bdd/e2e_rest_known_failures.txt`` rather than inventing a second comparator
system (Core Invariant, salesagent-syhj design). That means a sibling ledger file
(``tests/storyboard/known_failures.txt``), a conftest loader
(``tests/storyboard/conftest.py``) that reads it to xfail(strict=False) exactly those
known-failing storyboard test ids, and this lock test pinning the ledger's exact
contents so it cannot silently drift -- the same triad as the e2e_rest precedent.

Per the Core Invariant, the ledger must be seeded from a MEASURED in-network CI run,
never re-derived/inferred (the architect review's HIGH finding: SB-1d's host-side
numbers do not carry over to the in-network receiver topology). Until SB-4b lands the
runner module and its first in-network run, ``EXPECTED_LEDGER`` is pinned empty --
nothing has been measured through this pipeline yet. This test currently fails because
none of the triad exists yet (ledger file, loader, pytest module); that failure is the
TDD-red signal for SB-4b's implementation atom.

When the storyboard-conformance pytest module lands and its first in-network CI run
seeds real entries, update the ledger file AND ``EXPECTED_LEDGER`` below in the same
change (same discipline as the e2e_rest docstring: a removed entry that creeps back is
a graduation regression; a genuine-gap entry deleted without landing the underlying fix
is a silent gap-hiding regression).
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit import ledger
from tests.helpers.ledger import load_ledger_nodeids

# --- mcp half ---
# RE-SEEDED from the in-network run test-results/innet_130826_0940, taken WITH the
# version-envelope fix (GH #1512) live: 52 ledgered checks over 72 collected,
# down from 81 over 95.
#
# The docstring's note above about #1512 is now history: the capability probe is no
# longer rejected, so the runner reads our capabilities and gates on them. That
# GRADUATED all 40 signed_requests entries — the storyboard correctly SKIPS an agent
# that does not advertise request_signing.supported, exactly as its own gating clause
# says (salesagent-g6m2.3), plus 4 more, for 44 removed.
#
# 15 entries were ADDED, none of them a regression: all 15 were NOT-COLLECTED in the
# pre-fix baseline (innet_130826_0906). They are checks the run only reaches now that
# it gets past the first step. 12 fail on the SAME error string for a DIFFERENT cause
# — tool signatures missing 3.1.1 request fields the storyboards send, e.g. get_products
# lacks `account` and `buying_mode` (GH #1193). 3 are error-code mismatches.
EXPECTED_LEDGER: frozenset[str] = frozenset(
    {
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::assert_omitted_key_grace_handled]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_accept]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_reject]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::nonexistent_product]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::reversed_dates_error]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::unsupported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::unsupported_release_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::billing_gate_dispatch::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::capability_discovery::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::capability_discovery::get_capabilities_filtered]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::probe_unauth]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::stale_response_advisory::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::v3_envelope_integrity::no_legacy_status_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::version_negotiation::get_capabilities_with_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::assert_webhook_signing_key_present]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::fetch_brand_json]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_idempotent_webhook_initial]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_operation_id_echo]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_retry_scenario]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_signed_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_webhook_operation]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::creative::media_buy_seller/creative_reception::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::creative::media_buy_seller/creative_reception::sync_creatives]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/creative_fate_after_cancellation::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inline_creatives_without_sync::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inline_creatives_without_sync::get_products_canonical_format]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inline_creatives_without_sync::get_products_legacy_format]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/invalid_transitions::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/invalid_transitions::update_unknown_package]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inventory_list_no_match::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/inventory_list_targeting::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/measurement_terms_rejected::create_media_buy_aggressive_terms]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/measurement_terms_rejected::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/refine_products::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::media_buy_seller/refine_products::sync_accounts]",
        # --- a2a half ---
        # RE-SEEDED from the first real in-network run of the a2a axis (run
        # 32027922014, commit 6d16d9b1e, this branch): the agent-card dual-emit fix
        # (create_agent_card()/_create_dynamic_agent_card() now emit both a top-level
        # `url` and the 1.0 supportedInterfaces[0].url) resolved the discovery
        # rejection that previously graded ZERO a2a checks. Replaces the single
        # graded_checks_produced placeholder with the 32 checks actually measured.
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::version_negotiation::get_capabilities_with_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::webhook_emission::assert_webhook_signing_key_present]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::webhook_emission::fetch_brand_json]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::webhook_emission::trigger_idempotent_webhook_initial]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::webhook_emission::trigger_operation_id_echo]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::webhook_emission::trigger_retry_scenario]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::webhook_emission::trigger_signed_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::webhook_emission::trigger_webhook_operation]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::nonexistent_product]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::reversed_dates_error]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::unsupported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::unsupported_release_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::billing_gate_dispatch::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::security::security_baseline::probe_unauth]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/creative_fate_after_cancellation::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inline_creatives_without_sync::get_products_canonical_format]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inline_creatives_without_sync::get_products_legacy_format]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/invalid_transitions::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/invalid_transitions::update_unknown_package]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inventory_list_no_match::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inventory_list_targeting::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/measurement_terms_rejected::create_media_buy_aggressive_terms]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/measurement_terms_rejected::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/refine_products::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/refine_products::sync_accounts]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::creative::media_buy_seller/creative_reception::sync_creatives]",
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

    Guards against the loader being deleted or pointed elsewhere while the ledger file
    still exists -- that would silently stop xfailing these known-failing checks, the
    exact silent-breakage class the ledger/lock-test triad exists to prevent.
    """
    from tests.storyboard.conftest import _STORYBOARD_KNOWN_FAILURES

    assert _STORYBOARD_KNOWN_FAILURES == EXPECTED_LEDGER

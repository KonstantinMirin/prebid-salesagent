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

Per the Core Invariant, the ledger must be seeded from a MEASURED in-network CI run,
never re-derived/inferred (the architect review's HIGH finding: the runner's host-side
numbers do not carry over to the in-network receiver topology).

All three parts exist — the ledger file, its loader, and the pytest module — and the
ledger IS seeded from a real in-network run. The count below is read through the
loader rather than counted by hand, so this docstring cannot drift from the file.

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
# Two measured halves, seeded from two different in-network CI runs. Measured,
# never derived: the runner's host-side numbers do not carry over to the
# in-network receiver topology.
#
# Current total, through scripts.audit.ledger.load: 115 entries (79 mcp + 36 a2a).
#
# mcp (79) — RE-SEEDED from run 32478296091, job 96759107129, head_sha 0ec6637dd
# (2026-08-21): 96 collected, 13 failed, 1 passed, 13 skipped, 69 xfailed,
# 0 xpassed. That seed was 80 entries: the 69 previously-ledgered ones, ALL of
# which xfailed at that head (zero graduations), plus the 11 measured
# un-ledgered failures. Every one of the 11 carries `VALIDATION_ERROR:
# Unexpected keyword argument` -- #1512 (adcp_version rejected). Four of them
# (the wholesale_feed family) were not in the previous seed run's collection set
# at all: collection grew 83 -> 96, so they are newly gradable rather than newly
# broken. One has since GRADUATED --
# `mcp::core::version_negotiation::get_capabilities_with_version`: the seller now
# echoes adcp_version on the response envelope, stamped once at the one response
# seam, so the entry is deliberately absent rather than merely unmeasured. 80 - 1
# = 79.
#
# a2a (36) — the axis's FIRST measurement, ledgered by #2191. Before that change
# the A2A protocol pass graded ZERO checks (overall_status=unreachable, #1440):
# the app served the card on one path in an A2A 1.0 shape the runner's bundled
# `@a2a-js/sdk` client could not read. These 36 are first-sight gaps, not
# regressions -- 35 conformance gaps under #2192 (22 of them a2a twins of gaps
# already ledgered for mcp, which is exactly the cross-transport drift the
# two-protocol split exists to expose; 14 a2a-only), plus
# `a2a::security::security_baseline::probe_unauth` under #1859, kept on its own
# issue so a bulk graduation of #2192 can never silently carry a security gap
# with it.
#
# `a2a::_runner::agent_reachability::graded_checks_produced` -- the
# `_no_graded_checks` synthetic that recorded "this protocol graded NOTHING" --
# GRADUATED with that same change and is deliberately absent: the protocol grades
# 36 checks now. It is the mechanism to reach for again if the axis ever goes
# unreachable, since "not measured" is still not "graduated".
EXPECTED_LEDGER: frozenset[str] = frozenset(
    (
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::assert_omitted_key_grace_handled]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_accept]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_reject]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_products_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_accounts_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_creatives_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::missing_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::nonexistent_product]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::reversed_dates_error]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::supported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::unsupported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::unsupported_release_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::billing_gate_dispatch::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::capability_discovery::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::capability_discovery::get_capabilities_filtered]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::probe_unauth]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::stale_response_advisory::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::stale_response_advisory::no_stale_on_healthy_upstream]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::v3_envelope_integrity::no_legacy_status_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::assert_webhook_signing_key_present]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::fetch_brand_json]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_idempotent_webhook_initial]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_operation_id_echo]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_retry_scenario]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_signed_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_webhook_operation]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-001-no-signature-header]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-002-wrong-tag]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-003-expired-signature]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-004-window-too-long]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-005-alg-not-allowed]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-006-missing-covered-component]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-007-missing-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-008-unknown-keyid]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-009-key-ops-missing-verify]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-010-content-digest-mismatch]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-011-malformed-header]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-012-missing-expires-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-013-expires-le-created]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-014-missing-nonce-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-015-signature-invalid]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-016-replayed-nonce]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-017-key-revoked]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-018-digest-covered-when-forbidden]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-019-signature-without-signature-input]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-020-rate-abuse]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-021-duplicate-signature-input-label]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-022-multi-valued-content-type]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-023-multi-valued-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-024-unquoted-string-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-025-jwk-alg-crv-mismatch]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-027-webhook-registration-authentication-unsigned]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-028-unsigned-protocol-method-required]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-001-basic-post]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-002-post-with-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-003-es256-post]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-004-multiple-signature-labels]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-005-default-port-stripped]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-006-dot-segment-path]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-007-query-byte-preserved]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-008-percent-encoded-path]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-009-percent-encoded-unreserved-decoded]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-010-percent-encoded-slash-preserved]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-011-ipv6-authority]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-012-ipv6-authority-default-port-stripped]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::wholesale_feed_bulk_webhooks::register_bulk_change_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::wholesale_feed_product_webhooks::register_product_pricing_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::wholesale_feed_products::bootstrap_products]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::signals::wholesale_feed_signal_webhooks::register_signal_pricing_webhook]",
        # --- a2a axis, first measured by #2191 ---
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::capability_discovery::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::capability_discovery::get_capabilities_filtered]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::read_tool_idempotency::assert_omitted_key_grace_handled]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::read_tool_idempotency::get_capabilities_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_accept]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_reject]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::v3_envelope_integrity::no_legacy_status_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::core::version_negotiation::get_capabilities_with_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::creative::media_buy_seller/creative_reception::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::creative::media_buy_seller/creative_reception::sync_creatives]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::billing_gate_dispatch::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::nonexistent_product]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::reversed_dates_error]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::unsupported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::error_compliance::unsupported_release_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::error_handling::stale_response_advisory::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/creative_fate_after_cancellation::get_products_brief]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::media_buy::media_buy_seller/inline_creatives_without_sync::get_capabilities]",
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
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::security::security_baseline::probe_unauth]",
    )
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

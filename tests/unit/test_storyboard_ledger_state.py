"""Lock test for the storyboard-conformance known-failures ledger (SB-4b, salesagent-syhj).

Mirrors ``tests/unit/test_e2e_rest_ledger_state.py`` verbatim in shape: the storyboard
CI job (SB-4b) grades a MEASURED run of the real ``@adcp/sdk`` storyboard runner through
pytest as ordinary parametrized tests -- one per ``(track, storyboard_id, step_id)`` --
reusing the exact ledger/xfail/lock-test discipline already established by
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

from tests.helpers.ledger import load_ledger_nodeids

# SEEDED from the first real in-network CI run of the Storyboard Conformance job
# (run 30962437988, commit 1348eed70): 72 failed, 11 skipped, 0 passed over 83 graded
# checks. Measured, never re-derived -- the architect review's HIGH finding stands,
# and SB-1b/SB-1d's host-side numbers were NOT carried over here.
#
# Measured with this PR's two production fixes reverted, so the set describes
# origin/main's real conformance. #1512 (adcp_version rejected on MCP wrappers) and
# #1861 (auth masks DB errors) are both live in it: the runner's capability probe is
# itself rejected, which is why 0 checks pass and most storyboards never reach their
# assertions. Landing either fix should GRADUATE entries -- that is the signal.
#
# 40 of the 72 are signed_requests, which we do not advertise. The runner grades them
# anyway rather than skipping (#1291 is the implementation epic).
EXPECTED_LEDGER: frozenset[str] = frozenset(
    {
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::capability_discovery::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::capability_discovery::get_capabilities_filtered]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::assert_omitted_key_grace_handled]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::get_capabilities_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_accept]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_reject]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::get_products_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::list_accounts_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::read_tool_idempotency::list_creatives_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::v3_envelope_integrity::no_legacy_status_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::version_negotiation::get_capabilities_with_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[core::wholesale_feed_bulk_webhooks::register_bulk_change_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::billing_gate_dispatch::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::error_compliance::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::error_compliance::missing_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::error_compliance::nonexistent_product]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::error_compliance::reversed_dates_error]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::error_compliance::supported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::error_compliance::unsupported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::error_compliance::unsupported_release_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::stale_response_advisory::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[error_handling::stale_response_advisory::no_stale_on_healthy_upstream]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[media_buy::wholesale_feed_product_webhooks::register_product_pricing_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[media_buy::wholesale_feed_products::bootstrap_products]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security::security_baseline::probe_unauth]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-001-no-signature-header]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-002-wrong-tag]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-003-expired-signature]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-004-window-too-long]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-005-alg-not-allowed]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-006-missing-covered-component]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-007-missing-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-008-unknown-keyid]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-009-key-ops-missing-verify]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-010-content-digest-mismatch]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-011-malformed-header]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-012-missing-expires-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-013-expires-le-created]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-014-missing-nonce-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-015-signature-invalid]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-016-replayed-nonce]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-017-key-revoked]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-018-digest-covered-when-forbidden]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-019-signature-without-signature-input]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-020-rate-abuse]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-021-duplicate-signature-input-label]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-022-multi-valued-content-type]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-023-multi-valued-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-024-unquoted-string-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-025-jwk-alg-crv-mismatch]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-027-webhook-registration-authentication-unsigned]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::negative-028-unsigned-protocol-method-required]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-001-basic-post]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-002-post-with-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-003-es256-post]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-004-multiple-signature-labels]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-005-default-port-stripped]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-006-dot-segment-path]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-007-query-byte-preserved]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-008-percent-encoded-path]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-009-percent-encoded-unreserved-decoded]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-010-percent-encoded-slash-preserved]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-011-ipv6-authority]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[security_transport::signed_requests::positive-012-ipv6-authority-default-port-stripped]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[signals::wholesale_feed_signal_webhooks::register_signal_pricing_webhook]",
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
    entries key on (track, storyboard_id, step_id) per the Core Invariant, carried as a
    pytest parametrize id on the storyboard-conformance test module -- not a free-text
    reason (reason/reason_kind are non-key annotations reported on failure, per plan
    step 2, never part of the ledger identity).
    """
    for entry in _load_ledger_nodeids():
        assert entry.startswith("tests/storyboard/"), f"non-storyboard ledger entry: {entry}"
        assert "::" in entry, f"ledger entry is not a test id: {entry}"


def test_conftest_loader_reads_this_ledger() -> None:
    """The storyboard-conformance conftest loads the same ledger this test pins.

    Guards against the loader being deleted or pointed elsewhere while the ledger file
    still exists -- that would silently stop xfailing these known-failing checks, the
    exact silent-breakage class the ledger/lock-test triad exists to prevent.
    """
    from tests.storyboard.conftest import _STORYBOARD_KNOWN_FAILURES

    assert _STORYBOARD_KNOWN_FAILURES == EXPECTED_LEDGER

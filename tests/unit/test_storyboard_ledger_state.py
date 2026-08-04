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

# Nothing has been measured through the storyboard-conformance pytest pipeline yet
# (SB-4b is not implemented: no runner module, no ledger file, no conftest loader).
# Per the Core Invariant ("MEASURED ... never re-derived/inferred"), this must not be
# pre-populated with numbers carried over from the SB-1b/SB-1d host-side manual runs --
# those used a different receiver topology (host ports vs. in-network proxy:8000) and
# the architect review's HIGH finding is explicit that the two do not agree. Update this
# to the real seeded set together with tests/storyboard/known_failures.txt once SB-4b's
# first in-network CI run produces the summary JSON.
EXPECTED_LEDGER: frozenset[str] = frozenset()

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

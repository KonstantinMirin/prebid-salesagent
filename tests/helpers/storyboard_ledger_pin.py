"""The pinned contents of the storyboard-conformance known-failures ledger.

``tests/storyboard/known_failures.txt`` is pinned in exactly one place, and two
suites grade against that pin: ``tests/unit/test_storyboard_ledger_state.py``
(the lock test — the ledger file must equal the pin) and
``tests/integration/test_storyboard_ledger_fitness_real_session.py`` (the
fitness function — its three cases are vacuous unless the ledger it drives a
real session with is the pinned one).

The pin used to live in the unit lock test and be imported out of it, which made
a module whose job is to BE a test double as a helper library — the disease
``tests/unit/test_architecture_no_cross_test_module_imports.py`` forbids:
renaming or splitting the lock test would break an unrelated suite, and the
breakage would surface as a collection error in a file nobody touched. Same fix
shape, and same home rationale, as ``tests/unit/_run_all_tests_helpers.py``,
except that these two consumers sit in DIFFERENT suites (unit + integration), so
a suite-local ``_*_helpers.py`` would just move the cross-suite reach rather
than remove it. ``tests/helpers/**`` is the cross-suite home, alongside
``tests/helpers/ledger.py`` — the shared parser both consumers already use.

RE-SEEDING is a standing rule, not a one-off: whenever a run seeds or retires
entries, update ``tests/storyboard/known_failures.txt`` AND ``EXPECTED_LEDGER``
below in the same change. A removed entry that creeps back is a graduation
regression; a genuine-gap entry deleted without landing the underlying fix is a
silent gap-hiding regression.
"""

from __future__ import annotations

from pathlib import Path

#: Repo root, computed once from this module's path.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: The ledger file whose exact contents ``EXPECTED_LEDGER`` pins.
LEDGER_PATH = REPO_ROOT / "tests" / "storyboard" / "known_failures.txt"

# --- ledger pin ---
# The ledger is EMPTY by decision: the storyboard grades every check it collects, so
# every conformance gap reddens the job instead of xfailing quietly. The trade the
# emptiness buys and costs is written into tests/storyboard/known_failures.txt.
#
# An empty pin is not a disabled pin — it is the strictest one this file can hold. Any
# entry added to the ledger fails test_ledger_matches_expected_genuine_gaps until it is
# named here too, so re-ledgering a check is a deliberate, reviewable act rather than a
# quiet one. Seed an entry only from a MEASURED in-network run, and update both files in
# the same change.
#
# The pre-merge signing branch carried an 81-entry seed here (run 32478296091, job
# 96759107129, head_sha 0ec6637dd, @adcp/sdk 11.0.0). It is NOT carried forward and must
# not be restored by arithmetic: it was measured against the pre-#1721 transport
# architecture and an older runner pin, and this tree has neither. Recover it from git
# history if a future re-seed wants a starting point, then RE-MEASURE.
EXPECTED_LEDGER: frozenset[str] = frozenset()

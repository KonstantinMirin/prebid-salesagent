"""Guard: the committed check index agrees with the committed storyboard ledger.

Offline — reads ``docs/test-obligations/storyboard-checks.jsonl`` and
``tests/storyboard/known_failures.txt`` only. Never resolves a live
``~/projects/adcp`` clone, so unlike its sibling guards this one RUNS in CI.

The ``measured_failing_protocols`` column is a pure join of those two committed
files: no clone, no in-network run, nothing environment-dependent. So the two
can be checked against each other offline, and a ledger re-seed that lands
without an artifact refresh becomes a build failure instead of a silent drift.

Why this exists: `19116bf7e` regenerated the artifacts AND applied a ledger
`+40 / -14` in the same commit, in that order, so the published artifacts
described the PRE-change ledger — 34 of 1135 records across 12 sites disagreed
with the ledger sitting beside them, and the headline "measured FAILING" count
was wrong in `docs/`. Nothing caught it: the existing artifact-truth guard
states outright that it does not grade the measured columns
(test_architecture_storyboard_check_index_artifact_truth.py:19-22), and every
guard that would need a clone skips in CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import ledger  # noqa: E402

CHECKS_JSONL = REPO_ROOT / "docs" / "test-obligations" / "storyboard-checks.jsonl"


def test_measured_columns_match_the_ledger() -> None:
    """Every record's measured_failing_protocols == the ledger's protocols for that check."""
    failures: dict[tuple[str, str], list[str]] = {}
    for check_id in ledger.load(REPO_ROOT / ledger.LEDGER):
        failures.setdefault((check_id.storyboard_key, check_id.step_id), []).append(check_id.protocol)

    drift: list[str] = []
    for line in CHECKS_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = (record["storyboard_id"], record["step_id"])
        expected = sorted(failures.get(key, []))
        if sorted(record["measured_failing_protocols"]) != expected:
            drift.append(f"{key[0]}::{key[1]} artifact={record['measured_failing_protocols']} ledger={expected}")

    assert not drift, (
        "storyboard-checks.jsonl disagrees with the ledger it is generated from — "
        "regenerate the artifacts (scripts/audit/storyboard_check_index.py --jsonl --markdown "
        "and scripts/audit/storyboard_roadmap.py --markdown):\n  " + "\n  ".join(sorted(set(drift)))
    )

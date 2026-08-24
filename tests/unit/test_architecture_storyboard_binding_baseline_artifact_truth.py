"""Structural guard: `docs/test-obligations/storyboard-binding-baseline.md` agrees with
the feature tree it was generated from (Lane E4).

The checked-in baseline opens with "`21` scenarios tagged `@storyboard-v3.1`". The
tree carries **20** (`storyboard_spec.tagged_scenarios`), its table lists a
21st row for a scenario that no longer exists, and several rows cite a
`Feature:line` the feature has since moved past. Nothing catches any of that:
the only tests touching this artifact assert that the *check-index join* no
longer reads it (`test_architecture_storyboard_ledger.py`), which is a
different claim. A published number that nothing regenerates is exactly what
this lane's Core Invariant forbids — every artifact must be regenerable and
COMPARED in `make quality`, which is why this guard is a unit-suite structural
test rather than an integration one.

**The offline-comparable slice, named explicitly.** Full regeneration
(`scripts/audit/storyboard_binding_sweep.py --markdown`) resolves every
`@source` footer against a live `~/projects/adcp` clone at the pinned version.
CI has no clone, so a guard that regenerated the WHOLE artifact would simply
skip there — grading nothing while reporting green, the same false-green the
`requires_clone`-marked check-index tests had before
`test_architecture_storyboard_check_index_artifact_truth.py` split out its own
offline slice. This guard follows that precedent and regenerates only what the
repository alone determines:

* the header's pinned version, scenario COUNT, and declared
  specialisms/protocols — `storyboard_spec.pinned_version` /
  `declared_capabilities`, both repo-only readers;
* the table's IDENTITY column (`@T-*` scenario ids) and its `Feature:line`
  column — `storyboard_spec.tagged_scenarios`, which reads
  `tests/bdd/features/*.feature` and nothing else.

The **Bucket** and **Findings** columns are deliberately NOT regenerated here:
both are verdicts about a cited storyboard file that only exists in the clone.
They stay checkable only where the clone exists (`storyboard_binding_sweep.audit`,
run by hand or in the in-network job).

**Why no measured/liveness column may ever enter this slice** (Lane E binding
input R2): `docs/test-obligations/storyboard-checks.jsonl` carries 488 liveness
rows all reading `measured_this_run=False` — the published artifact is itself a
victim of the empty-under-xdist bug Lane E1 fixes. Once E1 lands, any such
column becomes RUN-DEPENDENT, so freezing one into a checked-in artifact and
diffing it here would make this guard non-deterministic.
`test_offline_slice_excludes_run_dependent_columns` pins that exclusion instead
of leaving it to a comment.

Offline: reads `tests/bdd/features/*.feature` and
`docs/test-obligations/storyboard-binding-baseline.md` only. Never resolves a
live `~/projects/adcp` clone.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURES_DIR = REPO_ROOT / "tests" / "bdd" / "features"
BASELINE = REPO_ROOT / "docs" / "test-obligations" / "storyboard-binding-baseline.md"

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_spec  # noqa: E402

# The fields the offline slice regenerates. Locked by
# `test_offline_slice_excludes_run_dependent_columns`.
OFFLINE_ROW_FIELDS = ("scenario", "feature", "line")

# Columns whose value depends on a particular RUN rather than on the tree.
RUN_DEPENDENT_FIELDS = ("measured", "measured_this_run", "liveness", "observations", "harness_wired", "steps_bound")

_HEADER_RE = re.compile(
    r"^`(?P<count>\d+)` scenarios tagged `(?P<tag>@[\w.\-]+)`\. "
    r"Declared specialisms: `(?P<specialisms>[^`]*)`; protocols: `(?P<protocols>[^`]*)`\.$",
    re.M,
)
_ROW_RE = re.compile(r"^\| `(?P<scenario>T-[^`]+)` \| (?P<feature>[^:|]+):(?P<line>\d+) \| ", re.M)


def _baseline_text() -> str:
    return BASELINE.read_text(encoding="utf-8")


def _published_header() -> dict[str, str]:
    match = _HEADER_RE.search(_baseline_text())
    assert match is not None, (
        "storyboard-binding-baseline.md no longer opens with the header "
        "scripts/audit/storyboard_binding_sweep.render_markdown emits; regenerate it."
    )
    return match.groupdict()


def _published_rows() -> list[dict[str, str]]:
    rows = [m.groupdict() for m in _ROW_RE.finditer(_baseline_text())]
    assert rows, "storyboard-binding-baseline.md has no parseable scenario rows"
    return rows


def _regenerated_rows() -> list[dict[str, str]]:
    """The offline slice, rebuilt from the feature tree the artifact claims to describe."""
    return [
        {"scenario": s.identifier, "feature": s.feature, "line": str(s.line)}
        for s in storyboard_spec.tagged_scenarios(FEATURES_DIR)
    ]


def test_published_scenario_count_matches_the_feature_tree() -> None:
    """The header's `N` scenarios claim is regenerated, not asserted."""
    published = int(_published_header()["count"])
    regenerated = len(_regenerated_rows())
    assert published == regenerated, (
        f"storyboard-binding-baseline.md claims {published} scenarios tagged "
        f"{storyboard_spec.TAG}; the feature tree carries {regenerated}. Regenerate it: "
        "`uv run python scripts/audit/storyboard_binding_sweep.py --markdown` "
        "(needs ~/projects/adcp for the Bucket/Findings columns)."
    )


def test_published_header_matches_the_declared_capabilities() -> None:
    """Tag, pinned version and declared specialisms/protocols come from the repo."""
    header = _published_header()
    declared = storyboard_spec.declared_capabilities(REPO_ROOT)
    version = storyboard_spec.pinned_version(REPO_ROOT)

    assert header["tag"] == storyboard_spec.TAG
    assert header["specialisms"] == ", ".join(sorted(declared["specialisms"]))
    assert header["protocols"] == ", ".join(sorted(declared["protocols"]))
    assert _baseline_text().splitlines()[0] == f"# Storyboard binding baseline — AdCP {version}"


def test_published_rows_match_the_tagged_scenarios_exactly() -> None:
    """Identity and Feature:line are regenerated row-for-row, in order.

    Order matters: `render_markdown` emits `audit()`'s bindings in
    `tagged_scenarios` order, so a row that has drifted position is as much a
    stale artifact as a row with a wrong line number.
    """
    published = _published_rows()
    regenerated = _regenerated_rows()

    published_ids = [r["scenario"] for r in published]
    regenerated_ids = [r["scenario"] for r in regenerated]
    assert published_ids == regenerated_ids, (
        "storyboard-binding-baseline.md lists scenarios the feature tree does not:\n"
        f"  only in the artifact: {sorted(set(published_ids) - set(regenerated_ids))}\n"
        f"  only in the tree:     {sorted(set(regenerated_ids) - set(published_ids))}"
    )

    drifted = [
        f"{p['scenario']}: artifact says {p['feature']}:{p['line']}, tree says {r['feature']}:{r['line']}"
        for p, r in zip(published, regenerated, strict=True)
        if (p["feature"], p["line"]) != (r["feature"], r["line"])
    ]
    assert drifted == [], "storyboard-binding-baseline.md cites stale Feature:line locations:\n  " + "\n  ".join(
        drifted
    )


def test_offline_slice_excludes_run_dependent_columns() -> None:
    """R2: no measured/liveness column may enter the offline-comparable slice.

    Post-E1 those columns are run-dependent; diffing a frozen copy of one
    against a fresh run would make this guard non-deterministic rather than
    truthful.
    """
    row_fields = set(_regenerated_rows()[0])
    assert row_fields == set(OFFLINE_ROW_FIELDS)
    assert row_fields.isdisjoint(RUN_DEPENDENT_FIELDS)


def test_guard_catches_a_drifted_line_number() -> None:
    """Meta-test: a guard that cannot fail is not a guard.

    Self-contained — corrupts a copy of the regenerated slice and compares it
    against the regenerated slice, so this stays a proof about the comparison
    itself no matter what state the checked-in artifact happens to be in.
    """
    regenerated = _regenerated_rows()
    corrupted = [dict(r) for r in regenerated]
    corrupted[0]["line"] = str(int(corrupted[0]["line"]) + 1)
    drifted = [
        a["scenario"]
        for a, b in zip(regenerated, corrupted, strict=True)
        if (a["feature"], a["line"]) != (b["feature"], b["line"])
    ]
    assert drifted == [regenerated[0]["scenario"]]


def test_guard_catches_a_row_for_a_scenario_that_no_longer_exists() -> None:
    """Meta-test: the identity comparison catches a deleted/renamed scenario's stale row."""
    regenerated = _regenerated_rows()
    published_ids = [r["scenario"] for r in regenerated] + ["T-UC-999-storyboard-deleted-scenario"]
    assert published_ids != [r["scenario"] for r in regenerated]
    assert set(published_ids) - {r["scenario"] for r in regenerated} == {"T-UC-999-storyboard-deleted-scenario"}

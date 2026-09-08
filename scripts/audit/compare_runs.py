#!/usr/bin/env python3
"""Compare two test runs test-by-test, and refuse to summarise.

Aggregate counts cannot establish that a change was safe. A suite can hold its
passed count exactly while silently swapping which tests pass, and a change that
adds tests moves every total at once so nothing can be read from the movement.
The only claim worth making is per-test: THIS nodeid had THIS outcome before and
THIS outcome now, and here is why.

The comparison is deliberately split, because the two halves support different
claims:

PRE-EXISTING nodeids (present in both runs)
    The safety claim. A change that adds test files must not perturb a single
    test that already existed. Any outcome change here is a regression until
    individually explained -- including a change to a MORE tolerant outcome, since
    pass -> xfail and pass -> skip both remove grading while looking green.

NEW nodeids (present only in the new run)
    The accounting claim. Every one must be explained by a reason the change
    intends, grouped so the reasons can be read and judged. A new test with no
    stated reason for its outcome is unaccounted for, not "fine because it is new".

EVERY VERDICT NAMES ITS DENOMINATOR, and that is the point of the reporting below
rather than a nicety. This tool used to enumerate suites from the NEW directory
alone: ``sorted(p.name for p in new.glob("*.json"))``. A suite that ran in the
baseline and died in the new run produces no report, was therefore never
enumerated, was never mentioned in the output, and ``CLEAN`` printed over its
absence. The one event a regression gate exists for -- a whole suite stopping --
was the one event it could not see. It happened:
``test-results/innet_080926_1108/`` is missing ``bdd_inprocess.json`` (8182
nodeids, SIGKILLed at 957s) and the tool named it nowhere.

So the suite set is the UNION of four sources -- each run's ``.suites`` manifest
(what ``run_all_tests.sh`` recorded that run as having executed) and each run's
reports on disk -- and a suite in that set with no report on either side is
NOT MEASURED: named, counted, and fatal. Not measured is never folded into
"compared and fine".

KNOWN NOISE, measured before trusting this tool, and now COMPUTED rather than
left to the reader. Two runs of the SAME code disagree on about 19 of 8182
bdd_inprocess nodeids, and the disagreement is always the transport parameter:
the identical scenario appears as ``[rest-<example>]`` in one run and
``[mcp-<example>]`` in the other. The docstring used to say "treat ~19 removed as
selection instability" while the code printed all 19 under "always a defect" and
exited 1 -- the tool's stated limit contradicting its own verdict. The pairing is
derivable, so it is derived: a removed nodeid whose base id (everything before
``[``) also appears among the added ones is reported as RE-PARAMETRIZED, and only
an unpaired removal is a disappearance. Measured against innet_080926_0943 vs
innet_080926_1145, that accounts for 19 of 19.

Exit status is 1 when any pre-existing test changed outcome, when any nodeid
genuinely disappeared, or when any suite went unmeasured -- so this can gate.

    python3 scripts/audit/compare_runs.py <baseline-dir> <new-dir> [suite.json ...]
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys
from typing import NamedTuple

#: Written by ``run_all_tests.sh`` next to the reports: the comma-separated list
#: of suites THAT invocation ran. Its own comment says consumers cannot infer
#: this from the reports -- report mtimes do not separate "stale" from "ran early
#: in a long serial run" -- which is exactly why this consumer must read it.
SUITES_MANIFEST = ".suites"


class SuiteComparison(NamedTuple):
    """What one suite contributed to the verdict, including its denominator."""

    suite: str
    baseline: int
    new: int
    shared: int
    changed: int
    disappeared: int
    reparametrized: int
    added: int
    regressed: bool


def outcomes(report: pathlib.Path) -> dict[str, tuple[str, str]]:
    """``nodeid -> (outcome, reason)`` for one suite's JSON report."""
    data = json.loads(report.read_text())
    result: dict[str, tuple[str, str]] = {}
    for test in data.get("tests", []):
        outcome = test.get("outcome", "?")
        reason = ""
        for phase in ("setup", "call", "teardown"):
            info = test.get(phase) or {}
            if info.get("longrepr"):
                reason = str(info["longrepr"])
                break
        result[test["nodeid"]] = (outcome, reason)
    return result


def declared_suites(run: pathlib.Path) -> set[str] | None:
    """Report filenames the run's own manifest says it executed, or ``None``.

    ``None`` means the run predates the manifest, and is different from an empty
    manifest: with no declaration the reports on disk are the only evidence of
    what ran, and this tool says so rather than inventing a denominator.
    """
    manifest = run / SUITES_MANIFEST
    if not manifest.exists():
        return None
    return {f"{name.strip()}.json" for name in manifest.read_text().split(",") if name.strip()}


def present_suites(run: pathlib.Path) -> set[str]:
    """Report filenames actually on disk for a run."""
    return {path.name for path in run.glob("*.json")}


def _base_nodeid(nodeid: str) -> str:
    """A nodeid with its ``[parametrization]`` suffix removed."""
    return nodeid.split("[", 1)[0]


def _pair_reparametrized(removed: set[str], added: set[str]) -> tuple[set[str], set[str]]:
    """Removed/added nodeids that differ only in their parametrization suffix.

    Paired per base id and by count, so a base that lost two nodeids and gained
    one leaves one genuine disappearance rather than excusing both.
    """
    removed_by_base: dict[str, list[str]] = collections.defaultdict(list)
    added_by_base: dict[str, list[str]] = collections.defaultdict(list)
    for nodeid in removed:
        removed_by_base[_base_nodeid(nodeid)].append(nodeid)
    for nodeid in added:
        added_by_base[_base_nodeid(nodeid)].append(nodeid)

    paired_removed: set[str] = set()
    paired_added: set[str] = set()
    for base, gone in removed_by_base.items():
        pairs = min(len(gone), len(added_by_base.get(base, ())))
        paired_removed.update(sorted(gone)[:pairs])
        paired_added.update(sorted(added_by_base[base])[:pairs])
    return paired_removed, paired_added


def _print_changed(changed: list[str], old: dict, now: dict) -> None:
    print(f"\n  PRE-EXISTING TESTS THAT CHANGED OUTCOME: {len(changed)}  <-- each needs an explanation")
    transitions = collections.Counter((old[n][0], now[n][0]) for n in changed)
    for (before, after), count in transitions.most_common():
        print(f"    {count:6}  {before} -> {after}")
        for nodeid in [n for n in changed if (old[n][0], now[n][0]) == (before, after)][:3]:
            print(f"            e.g. {nodeid[:100]}")
            if now[nodeid][1]:
                print(f"                 now: {now[nodeid][1].strip().splitlines()[-1][:90]}")


def _print_added(added: set[str], now: dict) -> None:
    print(f"\n  NEW TESTS: {len(added)}, by outcome and reason")
    by_reason: collections.Counter = collections.Counter()
    for nodeid in added:
        outcome, reason = now[nodeid]
        head = reason.strip().splitlines()[-1][:76] if reason.strip() else "(no reason recorded)"
        by_reason[(outcome, head)] += 1
    for (outcome, head), count in by_reason.most_common(14):
        print(f"    {count:6}  {outcome:9} {head}")
    if len(by_reason) > 14:
        print(f"    ... {len(by_reason) - 14} more distinct reasons")


def compare(baseline: pathlib.Path, new: pathlib.Path, suite: str) -> SuiteComparison:
    """Compare one suite present on both sides, and report its denominator."""
    old, now = outcomes(baseline / suite), outcomes(new / suite)
    shared = old.keys() & now.keys()
    added = now.keys() - old.keys()
    removed = old.keys() - now.keys()
    reparam_removed, reparam_added = _pair_reparametrized(set(removed), set(added))
    disappeared = sorted(removed - reparam_removed)
    genuinely_added = added - reparam_added

    changed = sorted(n for n in shared if old[n][0] != now[n][0])

    print(f"\n=== {suite} ===")
    print(
        f"  baseline {len(old):6}   new {len(now):6}   shared {len(shared):6}   "
        f"added {len(genuinely_added):6}   disappeared {len(disappeared):6}"
    )

    if changed:
        _print_changed(changed, old, now)
    else:
        print(f"\n  PRE-EXISTING TESTS: zero outcome changes over {len(shared)} shared nodeids")

    if reparam_removed:
        print(
            f"\n  RE-PARAMETRIZED: {len(reparam_removed)}  (same base nodeid, different [transport-example];"
            " selection instability, not a change)"
        )
        for nodeid in sorted(reparam_removed)[:3]:
            print(f"    {nodeid[:104]}")

    if disappeared:
        print(f"\n  DISAPPEARED (collected before, not now, no replacement): {len(disappeared)}  <-- always a defect")
        for nodeid in disappeared[:5]:
            print(f"    {nodeid[:104]}")

    if genuinely_added:
        _print_added(genuinely_added, now)

    return SuiteComparison(
        suite=suite,
        baseline=len(old),
        new=len(now),
        shared=len(shared),
        changed=len(changed),
        disappeared=len(disappeared),
        reparametrized=len(reparam_removed),
        added=len(genuinely_added),
        regressed=bool(changed or disappeared),
    )


def _why_unmeasured(suite: str, in_old: bool, in_new: bool, declared_old: bool, declared_new: bool) -> str | None:
    """Why this suite could not be compared, or ``None`` if it can be."""
    if in_old and in_new:
        return None
    manifests = [side for side, was in (("baseline", declared_old), ("new", declared_new)) if was]
    declared = f" (declared by the {' and '.join(manifests)} manifest)" if manifests else ""
    if in_old:
        return f"ran in the baseline, produced NO report in the new run{declared}"
    if in_new:
        return f"produced no report in the baseline, only in the new run{declared} — nothing to compare against"
    return f"NO report on either side{declared}"


def _resolve_suites(
    requested: list[str],
    sides: dict[str, tuple[set[str] | None, set[str]]],
) -> list[str]:
    """Every suite that must be accounted for: what was named, declared, or ran."""
    if requested:
        return sorted({name if name.endswith(".json") else f"{name}.json" for name in requested})
    accounted: set[str] = set()
    for declared, present in sides.values():
        accounted |= present | (declared or set())
    return sorted(accounted)


def _print_header(baseline: pathlib.Path, new: pathlib.Path, sides: dict, suites: list[str]) -> None:
    print("RUN COMPARISON")
    for label, path in (("baseline", baseline), ("new", new)):
        declared, present = sides[label]
        claim = (
            f"{len(declared)} suites declared ({SUITES_MANIFEST})"
            if declared is not None
            else f"no {SUITES_MANIFEST} manifest"
        )
        print(f"  {label:8} {path}")
        print(f"           {claim}, {len(present)} reports on disk")
    print(f"  suites to account for: {len(suites)}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    baseline, new = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    sides = {
        "baseline": (declared_suites(baseline), present_suites(baseline)),
        "new": (declared_suites(new), present_suites(new)),
    }
    suites = _resolve_suites(sys.argv[3:], sides)
    _print_header(baseline, new, sides, suites)

    compared: list[SuiteComparison] = []
    unmeasured: list[tuple[str, str]] = []
    for suite in suites:
        reason = _why_unmeasured(
            suite,
            in_old=suite in sides["baseline"][1],
            in_new=suite in sides["new"][1],
            declared_old=suite in (sides["baseline"][0] or set()),
            declared_new=suite in (sides["new"][0] or set()),
        )
        if reason is None:
            compared.append(compare(baseline, new, suite))
        else:
            unmeasured.append((suite, reason))

    return _report(compared, unmeasured, len(suites))


def _report(compared: list[SuiteComparison], unmeasured: list[tuple[str, str]], total: int) -> int:
    """Print the scope, then a verdict that cannot be read apart from it."""
    shared = sum(c.shared for c in compared)
    print(f"\nSCOPE: {len(compared)} of {total} suites compared, {shared} shared nodeids graded.")
    print(
        f"       baseline held {sum(c.baseline for c in compared)} nodeids in those suites, "
        f"new held {sum(c.new for c in compared)}."
    )

    if unmeasured:
        print(f"\nNOT MEASURED: {len(unmeasured)} of {total} suites — each is a hole in any verdict below.")
        for suite, reason in unmeasured:
            print(f"    {suite}: {reason}")

    regressed = [c.suite for c in compared if c.regressed]
    if regressed:
        print(f"\nREGRESSION over the {len(compared)} of {total} suites compared: {', '.join(regressed)}")
    elif unmeasured:
        print(
            f"\nNO REGRESSION in the {len(compared)} of {total} suites compared — and this says NOTHING about the other {len(unmeasured)}."
        )
    else:
        print(
            f"\nCLEAN over {len(compared)} of {total} suites, {shared} shared nodeids: no pre-existing test changed outcome."
        )

    return 1 if (regressed or unmeasured) else 0


if __name__ == "__main__":
    raise SystemExit(main())

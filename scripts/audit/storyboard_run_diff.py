#!/usr/bin/env python3
"""Diff two storyboard runs by the SET of steps each one passed.

Counts cannot answer "did this change break conformance". Two runs that pass 102 steps
each may pass different 102, and a storyboard step that PASSES produces no pytest item,
so neither the suite summary nor ``compare_runs.py`` (which diffs pytest nodeids) can see
a pass at all. The only thing left comparing conformance run-to-run was ``passed=N``, and
an equal N was read as "the same checks passed" when it meant "the same number passed".

This reads the runner's OWN record -- ``test-results/storyboard_run_<protocol>.json``,
the ``--json`` stdout published by ``tests/storyboard/test_storyboard_conformance.py`` --
and reports gained, lost and still-failing as sets of identified steps.

A step is identified by ``<track>::<scenario>::<task>``, which is what the runner nests
its results under and what ``storyboard_collected.json`` keys its check ids on.

SKIP MARKERS ARE NOT PASSES. A storyboard whose requirement is unmet contributes one
``requirement_unmet`` step that the runner records as passed -- the skip itself
succeeded. A run where that storyboard executes has no such marker, so counting it as a
pass makes a tree that skipped MORE look like it passed more. They are dropped.

Exit status: 1 if any step passed on the BASE and not on the HEAD, 0 otherwise. A
regression is a lost pass; gaining passes and gaining failures are both reported but
neither fails this script, because a run that grades more steps than its base
legitimately has more of both.

Read-only. Emits a table, or ``--json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: A storyboard the runner declined to execute still emits one step, recorded as passed.
#: Counting it would reward skipping.
_SKIP_MARKERS = ("requirement_unmet", "Storyboard skipped")

_PROTOCOLS = ("mcp", "a2a")


def _steps(record: Path) -> dict[str, bool]:
    """Every step in *record*, keyed ``track::scenario::task``, mapped to passed.

    Skip markers are excluded here rather than by the caller, so no consumer can
    accidentally count one.
    """
    data = json.loads(record.read_text())
    out: dict[str, bool] = {}
    for track in data.get("tracks") or []:
        for scenario in track.get("scenarios") or []:
            for step in scenario.get("steps") or []:
                key = f"{track.get('track')}::{scenario.get('scenario')}::{step.get('task') or step.get('step')}"
                if any(marker in key for marker in _SKIP_MARKERS):
                    continue
                out[key] = bool(step.get("passed"))
    return out


def _record_for(where: Path, protocol: str) -> Path | None:
    """The record for *protocol* under *where*, whether it is a run dir or its parent.

    Accepts the published location (``test-results/storyboard_run_<p>.json``), a pulled
    run directory (``<run>/storyboard/storyboard_run_<p>.json``), and a bare file.
    """
    if where.is_file():
        return where
    for candidate in (
        where / f"storyboard_run_{protocol}.json",
        where / "storyboard" / f"storyboard_run_{protocol}.json",
        where / "test-results" / f"storyboard_run_{protocol}.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def _compare(base: dict[str, bool], head: dict[str, bool]) -> dict[str, Any]:
    base_pass = {k for k, v in base.items() if v}
    head_pass = {k for k, v in head.items() if v}
    return {
        "base_graded": len(base),
        "head_graded": len(head),
        "base_passed": len(base_pass),
        "head_passed": len(head_pass),
        "identical": sorted(base_pass) == sorted(head_pass),
        "lost": sorted(base_pass - head_pass),
        "gained": sorted(head_pass - base_pass),
        "failing_both": sorted({k for k, v in base.items() if not v} & {k for k, v in head.items() if not v}),
        "newly_failing": sorted({k for k, v in head.items() if not v} - set(base)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", type=Path, help="run dir or record the HEAD is compared against")
    parser.add_argument("head", type=Path, help="run dir or record under test")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--protocol", choices=_PROTOCOLS, help="one protocol instead of both")
    args = parser.parse_args()

    protocols = (args.protocol,) if args.protocol else _PROTOCOLS
    report: dict[str, Any] = {}
    missing: list[str] = []
    for protocol in protocols:
        base_rec = _record_for(args.base, protocol)
        head_rec = _record_for(args.head, protocol)
        if base_rec is None or head_rec is None:
            missing.append(f"{protocol} (base={base_rec is not None} head={head_rec is not None})")
            continue
        report[protocol] = _compare(_steps(base_rec), _steps(head_rec))

    if missing:
        # Loud, never a silent partial: a protocol whose record is absent was not compared,
        # and reporting the other one as the verdict is how a half-measured run reads green.
        print(f"ERROR: no storyboard record for: {', '.join(missing)}", file=sys.stderr)
        print(
            "       Records come from the runner's --json stdout, published per protocol. A run "
            "that died before writing one cannot be compared.",
            file=sys.stderr,
        )
        if not report:
            return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for protocol, r in sorted(report.items()):
            verdict = "IDENTICAL" if r["identical"] else "DIFFERENT"
            print(f"[{protocol}] passing sets {verdict}")
            print(f"  graded: base={r['base_graded']} head={r['head_graded']}")
            print(f"  passed: base={r['base_passed']} head={r['head_passed']}")
            print(f"  lost ({len(r['lost'])}) — passed on base, not on head:")
            for step in r["lost"]:
                print(f"    - {step}")
            print(f"  gained ({len(r['gained'])}):")
            for step in r["gained"]:
                print(f"    + {step}")
            print(f"  failing on both: {len(r['failing_both'])}   newly graded and failing: {len(r['newly_failing'])}")

    return 1 if any(r["lost"] for r in report.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

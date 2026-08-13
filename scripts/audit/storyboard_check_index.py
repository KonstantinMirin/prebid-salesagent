#!/usr/bin/env python3
"""Per-CHECK index of the pinned conformance surface — the source of truth.

``storyboard-roadmap.md`` answers per STORYBOARD: is anything covering it, is
anything tracking it. That is the wrong grain for the questions this PR needs
answered — which individual graded check is covered by which BDD scenario,
which is tracked by which ticket, and which is neither — because a storyboard
with one scenario and eleven graded checks looks "covered" in that table while
ten checks go ungraded by us.

So this emits ONE RECORD PER CHECK, as JSONL, and every markdown view is a
rendering of those records rather than a separate artifact. Adding a view means
adding a renderer, never a second source that can drift from the first. Each
record carries every column any view might want; the narrow tables in
``render()`` exist because one 12-column table is unreadable, not because the
data is separate.

Record identity is ``(storyboard, step_id, check_type, ordinal)``. The step is
the addressable unit: the conformance ledger keys on ``(protocol, track,
storyboard_id, step_id)``, so the step is what a ticket or a scenario can
actually be mapped onto, and the ordinal disambiguates repeated check types
within one step.

Joins, and what each is authoritative for:

* pinned compliance tree — which checks EXIST, and their gates. The standard.
* ``tests/storyboard/known_failures.txt`` — what a real in-network run MEASURED.
* ``storyboard_coverage_map`` — which ``@storyboard-v3.1`` scenario claims the
  storyboard (scenario coverage is declared per storyboard, not per check, so
  it is carried down to every check of that storyboard and marked as such).
* ``docs/test-obligations/storyboard-issue-map.yaml`` — the curated ticket
  mapping, the one input no program can derive.

Read-only. ``--jsonl`` for the source of truth, ``--markdown`` for the report.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit import storyboard_coverage_map, storyboard_roadmap, storyboard_spec  # noqa: E402

# A check whose storyboard needs this tool can never be graded here: the tool is
# a production test-control backdoor we will not implement.
CONTROLLER = "comply_test_controller"


def _ledger_steps(repo: Path) -> dict[tuple[str, str], list[str]]:
    """(storyboard_id, step_id) -> protocols on which the ledger records a failure."""
    failures: dict[tuple[str, str], list[str]] = {}
    path = repo / storyboard_roadmap.LEDGER
    if not path.is_file():
        return failures
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = storyboard_roadmap._LEDGER_ID_RE.search(line)
        if match:
            key = (match.group(3).replace("-", "_"), match.group(4))
            failures.setdefault(key, []).append(match.group(1))
    return failures


WIREABILITY = Path("docs") / "test-obligations" / "storyboard-wireability.yaml"
BINDING_BASELINE = Path("docs") / "test-obligations" / "storyboard-binding-baseline.md"

_BINDING_ROW_RE = re.compile(r"^\| `([^`]+)` \| ([^|]+) \| \*\*([A-E])\*\* \|")


def _wireability(repo: Path) -> dict[str, dict[str, Any]]:
    """Curated (storyboard, step) -> e2e-wireability verdict.

    The one judgement in this index no program can derive: whether a step can be
    driven and observed from outside a running agent. Same status as the issue
    map — curated, reviewable, joined rather than inferred.
    """
    import yaml

    path = repo / WIREABILITY
    if not path.is_file():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("steps") or {}


def _binding_buckets(repo: Path) -> dict[str, str]:
    """Scenario id -> binding-baseline bucket (A verified … E blocked).

    A scenario in bucket B cites a storyboard it does not actually claim, so
    "covered by that scenario" is a weaker statement than it looks. Carrying the
    bucket alongside the scenario is what stops this index from repeating the
    roadmap's overclaim in finer print.
    """
    path = repo / BINDING_BASELINE
    if not path.is_file():
        return {}
    return {
        m.group(1): m.group(3)
        for line in path.read_text(encoding="utf-8").splitlines()
        if (m := _BINDING_ROW_RE.match(line.strip()))
    }


def _wire_fields(entry: dict[str, Any] | None, requires_controller: bool) -> dict[str, Any]:
    """Wireability columns for one check.

    A controller-gated step needs no assessment and gets none: it is ungradable
    by policy, so the verdict is deterministic and stating it as an assessed
    judgement would misrepresent where it came from.
    """
    if requires_controller:
        return {
            "e2e_wireable": "not_wireable",
            "e2e_axes": {},
            "e2e_requires": [],
            "e2e_blocker": "requires comply_test_controller, which will not be implemented",
            "e2e_source": "policy",
        }
    if entry is None:
        return {"e2e_wireable": "unassessed", "e2e_axes": {}, "e2e_requires": [], "e2e_blocker": "", "e2e_source": ""}
    return {
        "e2e_wireable": entry["verdict"],
        "e2e_axes": entry.get("axes") or {},
        "e2e_requires": entry.get("requires") or [],
        "e2e_blocker": entry.get("blocker", ""),
        "e2e_source": "assessed",
    }


def build(repo: Path, adcp: Path) -> dict[str, Any]:
    coverage = storyboard_coverage_map.build(repo, adcp)
    dist = storyboard_spec.dist_root(adcp, coverage["pinned_version"])
    issue_map = storyboard_roadmap._load_issue_map(repo)
    ledger = _ledger_steps(repo)
    wireability = _wireability(repo)
    buckets = _binding_buckets(repo)

    records: list[dict[str, Any]] = []
    for row in coverage["storyboards"]:
        if row["status"] != "ON-PATH":
            continue
        text = (dist / row["storyboard"]).read_text(encoding="utf-8")
        storyboard_id = storyboard_spec.storyboard_id(text) or row["stem"].replace("-", "_")
        tools = sorted(storyboard_spec.required_tools(text))
        tracking = issue_map.get(row["storyboard"]) or {}
        issues = tracking.get("issues") or []

        seen: dict[tuple[str, str], int] = {}
        for step_id, check_type, phase_id in storyboard_spec.checks_by_owner(text):
            ordinal = seen[(step_id, check_type)] = seen.get((step_id, check_type), -1) + 1
            failing = ledger.get((storyboard_id, step_id), [])
            records.append(
                {
                    # identity
                    "storyboard": row["storyboard"],
                    "storyboard_id": storyboard_id,
                    "phase_id": phase_id,
                    "step_id": step_id,
                    "check_type": check_type,
                    "ordinal": ordinal,
                    # provenance — every claim below is checkable against this
                    "citation": f"repo=adcp ref={coverage['pinned_version']} path={row['storyboard']}",
                    "tier": storyboard_spec.storyboard_tier(row["storyboard"]),
                    # gating: why a check may be unreachable rather than untested
                    "required_tools": tools,
                    "requires_controller": CONTROLLER in tools,
                    # measured, from a real in-network run
                    "measured_failing_protocols": sorted(failing),
                    "measured": "FAILING" if failing else ("ungradable" if CONTROLLER in tools else "no ledger entry"),
                    # our coverage — declared per storyboard, carried to each check
                    "scenarios": row["covered_by"],
                    "scenario_grain": "storyboard",
                    "scenario_binding_buckets": {s: buckets.get(s, "-") for s in row["covered_by"]},
                    # can a scenario for this check be wired end-to-end?
                    **_wire_fields(wireability.get(f"{row['storyboard']}::{step_id}"), CONTROLLER in tools),
                    # tracking — the one curated input
                    "issues": issues,
                    "issue_coverage": tracking.get("coverage", "untriaged"),
                    "issue_note": (tracking.get("note") or "").replace("\n", " ").strip(),
                }
            )

    gaps = [r for r in records if not r["scenarios"] and not r["issues"]]
    return {
        "pinned_version": coverage["pinned_version"],
        "totals": {
            "checks": len(records),
            "storyboards": len({r["storyboard"] for r in records}),
            "with_scenario": sum(1 for r in records if r["scenarios"]),
            "with_issue": sum(1 for r in records if r["issues"]),
            "neither": len(gaps),
            "failing": sum(1 for r in records if r["measured_failing_protocols"]),
            "ungradable": sum(1 for r in records if r["requires_controller"]),
            "wireable": sum(1 for r in records if r["e2e_wireable"] == "wireable"),
            "conditional": sum(1 for r in records if r["e2e_wireable"] == "conditional"),
            "not_wireable": sum(1 for r in records if r["e2e_wireable"] == "not_wireable"),
            "unassessed": sum(1 for r in records if r["e2e_wireable"] == "unassessed"),
        },
        "records": records,
    }


def jsonl(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The source of truth: one line per check."""
    return result["records"]


def _check_id(record: dict[str, Any]) -> str:
    suffix = f"#{record['ordinal']}" if record["ordinal"] else ""
    return f"`{record['storyboard_id']}/{record['step_id']}/{record['check_type']}{suffix}`"


def render(result: dict[str, Any]) -> str:
    """Several narrow tables, each answering ONE question about the same rows."""
    totals = result["totals"]
    records = result["records"]
    out = [
        f"# Storyboard check index — AdCP {result['pinned_version']}",
        "",
        "**One row per graded check**, not per storyboard. Generated from "
        "`storyboard-checks.jsonl`, which is the source of truth — every table below is a "
        "view of those same records, so they cannot disagree. Regenerate both with "
        "`scripts/audit/storyboard_check_index.py` (`--jsonl` / `--markdown`).",
        "",
        f"- graded checks on our conformance path: **{totals['checks']}** across "
        f"**{totals['storyboards']}** storyboards",
        f"- covered by a BDD scenario: **{totals['with_scenario']}**",
        f"- tracked by an issue: **{totals['with_issue']}**",
        f"- **neither scenario nor ticket: {totals['neither']}**",
        f"- measured FAILING: **{totals['failing']}**",
        f"- permanently ungradable (`comply_test_controller`): **{totals['ungradable']}**",
        "",
        f"E2E wireability — **{totals['wireable']}** wireable as-is, **{totals['conditional']}** "
        f"conditional on provisioning, **{totals['not_wireable']}** not wireable"
        + (f", **{totals['unassessed']}** unassessed" if totals["unassessed"] else "")
        + ".",
        "",
        "Scenario coverage is declared per STORYBOARD (`@storyboard-v3.1` tags a scenario "
        "to a storyboard, not to a check), so a scenario shown against a check means "
        '"this check\'s storyboard is claimed" — not that this check is asserted. That '
        "distinction is the whole reason for indexing at this grain.",
        "",
        "## 1. Measured status",
        "",
        "| Check | Status | Protocols failing |",
        "|---|---|---|",
    ]
    for r in records:
        if r["measured"] == "no ledger entry" and not r["requires_controller"]:
            continue
        protocols = ", ".join(f"`{p}`" for p in r["measured_failing_protocols"]) or "—"
        out.append(f"| {_check_id(r)} | {r['measured']} | {protocols} |")

    out += [
        "",
        "## 2. Tracking",
        "",
        "Checks whose storyboard carries an issue. `coverage` is the map's own assessment "
        "of how much of the storyboard that issue covers.",
        "",
        "| Check | Issue(s) | Coverage |",
        "|---|---|---|",
    ]
    for r in records:
        if not r["issues"]:
            continue
        refs = ", ".join(f"#{n}" for n in r["issues"])
        out.append(f"| {_check_id(r)} | {refs} | {r['issue_coverage']} |")

    out += [
        "",
        "## 3. Scenario coverage",
        "",
        "| Check | Scenario(s) claiming the storyboard |",
        "|---|---|",
    ]
    for r in records:
        if not r["scenarios"]:
            continue
        out.append(f"| {_check_id(r)} | {', '.join(f'`{s}`' for s in r['scenarios'])} |")

    out += [
        "",
        "## 4. End-to-end wireability",
        "",
        "Can a BDD scenario for this check be wired in the e2e environment — Given seeded by "
        "sending requests or by ordinary stack fixtures, When constructed and sent by a client, "
        "Then asserted on the wire? Curated in `storyboard-wireability.yaml`; the harness is a "
        "client, so building a signed request, sending a malformed one or firing N requests to "
        "trip a rate limit are all wireable. Controller-gated checks are `not_wireable` by "
        "policy rather than by assessment.",
        "",
        "| Check | Wireable | Needs provisioning | Blocker |",
        "|---|---|---|---|",
    ]
    for r in records:
        if r["e2e_wireable"] in ("wireable", "unassessed"):
            continue
        needs = ", ".join(f"`{x}`" for x in r["e2e_requires"]) or "—"
        blocker = (r["e2e_blocker"] or "—").replace("\n", " ").strip()
        out.append(f"| {_check_id(r)} | {r['e2e_wireable']} | {needs} | {blocker[:180]} |")

    out += [
        "",
        "## 5. Neither scenario nor ticket",
        "",
        "The list to take to triage: 3.1.1 grades these, we do not test them, and nothing in the tracker names them.",
        "",
        "| Check | Storyboard | Required tools |",
        "|---|---|---|",
    ]
    for r in records:
        if r["scenarios"] or r["issues"]:
            continue
        tools = ", ".join(f"`{t}`" for t in r["required_tools"]) or "—"
        out.append(f"| {_check_id(r)} | `{r['storyboard']}` | {tools} |")

    return "\n".join(out) + "\n"


def main() -> int:
    return storyboard_spec.run_cli(__doc__ or "", build, render, jsonl_fn=jsonl)


if __name__ == "__main__":
    sys.exit(main())

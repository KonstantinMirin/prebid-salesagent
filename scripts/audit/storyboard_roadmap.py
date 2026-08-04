#!/usr/bin/env python3
"""Per-storyboard roadmap: spec clause + scenario + implementation clue, per on-path row.

For every ON-PATH storyboard (from storyboard_coverage_map.build()), attaches:

  * the 3.1.1 citation (the storyboard's own pinned-tree path + pinned_version()),
  * required_tools and a static, YAML-derived check-type inventory,
  * real measured status where the SB-1d runner executed this storyboard
    (per-STEP passed/failed counts — never a per-check-type breakdown, which
    the runner's free-text step details cannot support soundly; see the
    "measured status" note below),
  * the comply_test_controller divergence tag for the 20 storyboards
    sb5d-comply-test-controller-divergence.md already triaged as deliberate
    (not a plain gap),
  * a best-effort GitHub-issue cross-reference, joined per-SCENARIO through
    sb5c-issue-drafts.md's "Blocked BDD scenarios" sections (present on only
    25 of 49 items) — left blank where no such section names the scenario,
    never inferred.

Explicitly NOT joined here: scenario-level reconciliation (VERDICT/action)
from storyboard_reconciliation.py. Its rows key by proposal-file slug
(``uc003-creativefate``), not by T-UC-* scenario id, and there is no existing
mapping between the two (40 proposals vs the current 21 tagged scenarios) --
inventing one would violate the Core Invariant ("never re-derived/inferred").
See docs/test-obligations/storyboard-reconciliation.md directly for that data.

Measured-status join key: the SB-1d runner's ``tested_tracks[].scenarios[].
scenario`` field is ``"<storyboard_stem>/<sub-scenario-name>"`` in the
runner's own underscore-cased spelling (e.g. ``capability_discovery/...``),
while coverage_map's stems are hyphenated for universal/ storyboards
(``capability-discovery``). Joined by normalizing both sides to underscores.
A storyboard with zero matching runner scenarios is reported ``not_yet_run``,
never silently omitted -- this script asserts a minimum join rate against the
runner's own ``storyboards_executed``/``storyboards_missing_tools`` totals so
a regression in the join logic cannot ship looking like "nothing was
measured" (salesagent-pw71, architect review finding).

Read-only. Emits JSON, or ``--markdown`` for the checked-in artifact.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit import storyboard_coverage_map, storyboard_spec  # noqa: E402

# The 20 on-path-uncovered storyboards sb5d-comply-test-controller-divergence.md
# already triaged as a deliberate, closed divergence -- not a plain conformance
# gap. DETERMINISTIC INJECTION storyboards stay dormant by design; PRIOR STATE
# ONLY storyboards are reachable via real API sequencing instead of the missing
# tool. Keyed by storyboard stem (matches storyboard_coverage_map's `stem`).
# Source: .claude/notes/storyboard-conformance/sb5d-comply-test-controller-divergence.md
# "Part 2 -- triage of the 20". Kept as an explicit, reviewable table here
# (not re-derived from the prose) per the Core Invariant.
_COMPLY_TEST_CONTROLLER_DIVERGENCE: dict[str, str] = {
    "audience_buy_flow": "DETERMINISTIC INJECTION",
    "billing_finality_delivery": "DETERMINISTIC INJECTION",
    "canonical_formats": "PRIOR STATE ONLY",
    "clicks_buy_flow": "DETERMINISTIC INJECTION",
    "completed_views_buy_flow": "DETERMINISTIC INJECTION",
    "dependency_impairment": "PRIOR STATE ONLY",
    "dependency_impairment_cardinality": "PRIOR STATE ONLY",
    "frequency_cap_enforcement": "DETERMINISTIC INJECTION",
    "get_products_async": "DETERMINISTIC INJECTION",
    "performance_buy_flow": "DETERMINISTIC INJECTION",
    "performance_buy_flow_roas": "DETERMINISTIC INJECTION",
    "pricing_currency_filter": "PRIOR STATE ONLY",
    "product_signal_targeting": "PRIOR STATE ONLY",
    "provenance_audit_observation": "DETERMINISTIC INJECTION",
    "reach_buy_flow": "DETERMINISTIC INJECTION",
    "vendor_metric_catalog_precondition": "DETERMINISTIC INJECTION",
    "vendor_metric_optimization_flow": "PRIOR STATE ONLY",
    "canonical-format-validate-input": "PRIOR STATE ONLY",
    "comply-controller-mode-gate": "DETERMINISTIC INJECTION",
    "deterministic-testing": "DETERMINISTIC INJECTION",
}

_ITEM_HEADER_RE = re.compile(r"^### ([A-Z]+-\d+)\b.*$", re.M)
_BLOCKED_SCENARIOS_HEADER_RE = re.compile(r"^## Blocked BDD scenarios\s*$", re.M)
_NEXT_HEADER_RE = re.compile(r"^#{1,3} ", re.M)
_DISPOSITION_LINE_RE = re.compile(r"^\*\*Disposition:\s*(.+?)\*\*", re.M)
_SUMMARY_ROW_RE = re.compile(r"^\|\s*([A-Z]+-\d+)\s*\|.*\|\s*(.+?)\s*\|\s*$", re.M)


def _gh_issue_cross_reference(repo: Path) -> dict[str, str]:
    """Best-effort T-UC-* scenario -> GH-issue-disposition map.

    Only scenarios literally named inside a "## Blocked BDD scenarios"
    section are joined -- present on 25 of the 49 sb5c items. Everything
    else is left unjoined (the caller renders it blank), never inferred.
    Each item is a "### <ID> -- <title>" (H3) section; its disposition is
    stated as "**Disposition: ...**" prose right after the header (falling
    back to the "0. Disposition summary" table's row when absent from the
    item body), and its blocked-scenario list sits inside a "## Blocked BDD
    scenarios" sub-header nested in the item's body (itself inside a fenced
    gh-issue-body block, which this parser does not need to respect since it
    only reads text between two header markers).
    """
    sb5c = repo / ".claude" / "notes" / "storyboard-conformance" / "sb5c-issue-drafts.md"
    if not sb5c.is_file():
        return {}
    text = sb5c.read_text(encoding="utf-8")

    summary_dispositions = dict(_SUMMARY_ROW_RE.findall(text))

    item_headers = list(_ITEM_HEADER_RE.finditer(text))
    result: dict[str, str] = {}
    for i, match in enumerate(item_headers):
        item_id = match.group(1)
        item_start = match.end()
        item_end = item_headers[i + 1].start() if i + 1 < len(item_headers) else len(text)
        item_text = text[item_start:item_end]

        disposition_match = _DISPOSITION_LINE_RE.search(item_text)
        disposition = disposition_match.group(1) if disposition_match else summary_dispositions.get(item_id, "?")

        blocked = _BLOCKED_SCENARIOS_HEADER_RE.search(item_text)
        if not blocked:
            continue
        blocked_end = _NEXT_HEADER_RE.search(item_text, blocked.end())
        blocked_text = item_text[blocked.end() : (blocked_end.start() if blocked_end else len(item_text))]
        for ident in re.findall(r"\bT-UC-[A-Za-z0-9\-]+\b", blocked_text):
            result.setdefault(ident, f"{item_id} ({disposition})")
    return result


ISSUE_MAP = Path("docs") / "test-obligations" / "storyboard-issue-map.yaml"


def _load_issue_map(repo: Path) -> dict[str, dict[str, Any]]:
    """Curated storyboard -> GitHub-issue map. The one hand-maintained input here.

    Keyed by STORYBOARD, deliberately. The older cross-reference above joins by
    SCENARIO, which structurally cannot express "this storyboard has no scenario
    but issue #N tracks the gap" -- and that is the majority case (51 of 62
    on-path storyboards have no scenario). Keying on the storyboard is what lets
    an uncovered gap carry a ticket, or be explicitly marked as carrying none.

    A `coverage: none` row with no issues is a real answer, not a hole: it means
    3.1.1 grades this, we do not test it, and nobody is tracking it.
    """
    import yaml

    path = repo / ISSUE_MAP
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded.get("storyboards") or {}


def check_issue_map_complete(repo: Path, on_path: list[str]) -> list[str]:
    """Return the on-path storyboards absent from the issue map.

    A spec bump that introduces a storyboard must not silently add an untracked
    conformance gap -- the new storyboard has to be triaged into the map, even
    if the triage outcome is `coverage: none`. Same ratchet discipline as the
    structural guards: the map may not fall behind the spec.
    """
    return sorted(set(on_path) - set(_load_issue_map(repo)))


def _render_issue_cell(entry: dict[str, Any] | None) -> str:
    """One table cell: the tracking status of a storyboard's gap."""
    if entry is None:
        return "**UNTRIAGED**"
    issues = entry.get("issues") or []
    coverage = entry.get("coverage", "none")
    if not issues:
        return "**NO TICKET**"
    refs = ", ".join(f"#{n}" for n in issues)
    return f"{refs} ({coverage})" if coverage != "full" else refs


def _load_runner_scenarios(results_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load SB-1d's real per-step results, preferring it over the older SB-1b run."""
    for name in ("sb1d-full.json", "sb1b-full.json"):
        path = results_dir / name
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            scenarios = [s for track in data.get("tested_tracks", []) for s in track.get("scenarios", [])]
            return scenarios, data
    return [], {}


def _measured_status(stem: str, runner_scenarios: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate real per-step pass/fail for one storyboard, or None if never run.

    Joined on the runner scenario field's storyboard-stem prefix, normalized
    to underscores on both sides (coverage_map stems are hyphenated for
    universal/ storyboards; the runner spells them with underscores).
    """
    normalized_stem = stem.replace("-", "_")
    matched = [s for s in runner_scenarios if s.get("scenario", "").split("/")[0] == normalized_stem]
    if not matched:
        return None

    passed = failed = failed_skip_affected = 0
    for scenario in matched:
        for step in scenario.get("steps", []):
            if step.get("passed"):
                passed += 1
            else:
                failed += 1
                if "skipped" in (step.get("details") or ""):
                    failed_skip_affected += 1
    return {
        "scenarios_matched": len(matched),
        "steps_passed": passed,
        "steps_failed": failed,
        "steps_failed_skip_affected": failed_skip_affected,
    }


def build(repo: Path, adcp: Path) -> dict[str, Any]:
    coverage = storyboard_coverage_map.build(repo, adcp)
    dist = storyboard_spec.dist_root(adcp, coverage["pinned_version"])
    runner_results_dir = repo / "tests" / "storyboard" / "runner" / "results"
    runner_scenarios, runner_summary = _load_runner_scenarios(runner_results_dir)
    gh_issues = _gh_issue_cross_reference(repo)
    issue_map = _load_issue_map(repo)

    on_path = [r for r in coverage["storyboards"] if r["status"] == "ON-PATH"]
    untriaged = check_issue_map_complete(repo, [r["storyboard"] for r in on_path])

    rows: list[dict[str, Any]] = []
    joined = 0
    for row in on_path:
        text = (dist / row["storyboard"]).read_text(encoding="utf-8")
        checks: dict[str, int] = {}
        for phase_id in storyboard_spec.phases(text):
            for check_type in storyboard_spec.checks_for_phase(text, phase_id):
                checks[check_type] = checks.get(check_type, 0) + 1

        measured = _measured_status(row["stem"], runner_scenarios)
        if measured is not None:
            joined += 1

        gh_refs = sorted({gh_issues[ident] for ident in row["covered_by"] if ident in gh_issues})
        tracking = issue_map.get(row["storyboard"])

        rows.append(
            {
                "storyboard": row["storyboard"],
                "stem": row["stem"],
                "citation": f"repo=adcp ref={coverage['pinned_version']} path={row['storyboard']}",
                "scenarios": row["covered_by"],
                "required_tools": sorted(storyboard_spec.required_tools(text)),
                "checks": dict(sorted(checks.items())),
                "measured": measured or {"status": "not_yet_run"},
                "divergence": _COMPLY_TEST_CONTROLLER_DIVERGENCE.get(row["stem"]),
                "gh_issues": gh_refs,
                "tracking": _render_issue_cell(tracking),
                "tracking_issues": (tracking or {}).get("issues") or [],
                "tracking_coverage": (tracking or {}).get("coverage", "untriaged"),
                "tracking_note": (tracking or {}).get("note", ""),
            }
        )

    # Never ship a silently-degraded join: assert against the runner's own
    # reported totals rather than an arbitrary threshold.
    runner_ran_count = len(runner_summary.get("storyboards_executed", [])) + len(
        runner_summary.get("storyboards_missing_tools", [])
    )
    if runner_ran_count and joined == 0:
        raise SystemExit(
            f"measured-status join resolved 0 of {len(on_path)} on-path rows, but the runner "
            f"reports {runner_ran_count} storyboards executed/missing-tools — the join key is "
            "broken, not the data. Fix _measured_status() before trusting this output."
        )

    if untriaged:
        raise SystemExit(
            f"{len(untriaged)} on-path storyboard(s) are absent from {ISSUE_MAP}. A storyboard the "
            "pinned spec grades us on must be triaged before this table can claim to be the "
            "conformance gap record — even if the triage outcome is `coverage: none`:\n"
            + "\n".join(f"  {s}" for s in untriaged)
        )

    return {
        "pinned_version": coverage["pinned_version"],
        "totals": {
            "on_path": len(on_path),
            "measured_join": joined,
            "runner_reported": runner_ran_count,
            "no_scenario": sum(1 for r in rows if not r["scenarios"]),
            "no_ticket": sum(1 for r in rows if not r["tracking_issues"]),
            "no_scenario_no_ticket": sum(1 for r in rows if not r["scenarios"] and not r["tracking_issues"]),
            "distinct_issues": len({i for r in rows for i in r["tracking_issues"]}),
        },
        "rows": rows,
    }


def render(result: dict[str, Any]) -> str:
    out = [
        f"# Storyboard roadmap — AdCP {result['pinned_version']}",
        "",
        "**What AdCP 3.1.1 grades this agent on, what we test, and what is tracked.**",
        "",
        "One row per on-path storyboard: the 3.1.1 clause, which BDD scenario(s) claim it, "
        "the static check-type inventory, real measured status where the SB-1d runner "
        "executed it, and whether an open GitHub issue tracks the gap. Generated — do not "
        "hand-edit; regenerate with `scripts/audit/storyboard_roadmap.py`. Every column but "
        "**Tracking** is derived from the pinned compliance tree and this repo's `.feature` "
        "files; **Tracking** comes from the curated `storyboard-issue-map.yaml`.",
        "",
        f"- on-path storyboards: **{result['totals']['on_path']}**",
        f"- **no BDD scenario: {result['totals']['no_scenario']}**",
        f"- **no tracking issue: {result['totals']['no_ticket']}**",
        f"- **neither scenario nor ticket: {result['totals']['no_scenario_no_ticket']}**",
        f"- existing issues that track part of the gap: **{result['totals']['distinct_issues']}**",
        f"- joined to real runner measurement: **{result['totals']['measured_join']}** "
        f"(runner reports {result['totals']['runner_reported']} executed/missing-tools)",
        "",
        "This table deliberately files **no new issues**. The uncovered storyboards are a "
        "conformance gap, not a work plan — decomposing them into tickets is a decision for "
        "the project's roadmap, not for the PR that measured them. `NO TICKET` is the "
        "finding, stated plainly, with the spec clause and check inventory attached so the "
        "triage conversation can start from evidence.",
        "",
        "Reading the cells:",
        "",
        "- **Scenario(s)** — `— NOT COVERED —` means no `@storyboard-v3.1` scenario claims it. "
        "A scenario being listed does *not* mean its checks all pass; compare against Checks.",
        "- **Tracking** — `#N (partial)` means the issue covers some of this storyboard's "
        "checks; the map's `note:` says what it leaves out. `NO TICKET` means nothing in the "
        "tracker covers it.",
        "- **Divergence** — `DETERMINISTIC INJECTION` marks storyboards requiring "
        "`comply_test_controller`, which will not be implemented (it is a production "
        "test-control backdoor). Those checks are permanently ungradable here by design.",
        "",
        "Scenario-level reconciliation (VERDICT/action per proposal) is a separate artifact — "
        "see `storyboard-reconciliation.md`; its rows key by proposal-file slug, not by "
        "scenario id, so it is not joined into this table.",
        "",
        "| Storyboard | Citation | Scenario(s) | Required tools | Checks | Measured | Divergence | Tracking |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in result["rows"]:
        scenarios = ", ".join(f"`{s}`" for s in r["scenarios"]) or "**— NOT COVERED —**"
        tools = ", ".join(f"`{t}`" for t in r["required_tools"]) or "—"
        checks = ", ".join(f"{k}×{v}" for k, v in r["checks"].items()) or "—"
        measured = r["measured"]
        if measured.get("status") == "not_yet_run":
            measured_cell = "not yet run"
        else:
            measured_cell = f"{measured['steps_passed']} passed / {measured['steps_failed']} failed" + (
                f" ({measured['steps_failed_skip_affected']} skip-affected)" if measured["steps_failed"] else ""
            )
        divergence = r["divergence"] or "—"
        out.append(
            f"| `{r['storyboard']}` | {r['citation']} | {scenarios} | {tools} | {checks} | "
            f"{measured_cell} | {divergence} | {r['tracking']} |"
        )

    # The gap, restated as the only two lists a reader actually acts on.
    out += [
        "",
        "## Graded, untested, untracked",
        "",
        "On our conformance path at the pin, with no BDD scenario **and** no open issue. "
        "This is the list to take to roadmap triage.",
        "",
        "| Storyboard | Checks | Why it matters |",
        "|---|---|---|",
    ]
    for r in result["rows"]:
        if r["scenarios"] or r["tracking_issues"]:
            continue
        total = sum(r["checks"].values())
        note = (r["tracking_note"] or "—").replace("\n", " ").strip()
        out.append(f"| `{r['storyboard']}` | {total} | {note} |")

    out += [
        "",
        "## Graded and untested, but already tracked",
        "",
        "No BDD scenario, but an open issue covers some or all of it — these map onto work "
        "the project has already accepted.",
        "",
        "| Storyboard | Checks | Issue(s) | What the issue does not cover |",
        "|---|---|---|---|",
    ]
    for r in result["rows"]:
        if r["scenarios"] or not r["tracking_issues"]:
            continue
        total = sum(r["checks"].values())
        refs = ", ".join(f"#{n}" for n in r["tracking_issues"])
        note = (r["tracking_note"] or "—").replace("\n", " ").strip()
        out.append(f"| `{r['storyboard']}` | {total} | {refs} | {note} |")

    return "\n".join(out) + "\n"


def main() -> int:
    return storyboard_spec.run_cli(__doc__ or "", build, render)


if __name__ == "__main__":
    sys.exit(main())

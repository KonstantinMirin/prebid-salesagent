"""Regression tests for the liveness join in storyboard_check_index.build() (salesagent-vuz9t.12.2).

storyboard_check_index derived ``covered_by`` from tag presence alone: a
``@storyboard-v3.1``-tagged scenario with zero bound step definitions counted as
"covered" forever (salesagent-vuz9t.12's finding). This file proves the fix: two
published headline numbers (``claimed-by-a-scenario`` vs ``graded-by-a-live-scenario``),
and a ``graduation_candidate`` flag on entries the BDD suite locally xfails as a known
gap that the real conformance ledger does not currently measure as failing.

The real, exhaustive proof needs the live pinned compliance tree (``build()`` reads
per-check text that the vendored offline fixture doesn't carry) — same
``requires_clone`` contract as this repo's other storyboard_check_index consumers
(``test_architecture_storyboard_wireability.py``, ``test_architecture_storyboard_ledger.py``).
Liveness itself is injected via ``scenario_liveness_join.build_index``'s
``artifact_path``/``env_routes`` parameters (monkeypatched), so this test needs neither a
real BDD run nor a real ``ENV_ROUTES`` registry entry — only the real check/storyboard
join, which is the thing under test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADCP_HOME = Path.home() / "projects" / "adcp"

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import scenario_liveness_join, storyboard_check_index, storyboard_spec  # noqa: E402

# Captured before any test monkeypatches scenario_liveness_join.load_artifact --
# tests below patch that name to a fixed-path lambda, so the lambda body must call
# the ORIGINAL function object, not the (by-then-patched) module attribute.
_real_load_artifact = scenario_liveness_join.load_artifact

DIST = storyboard_spec.dist_root(ADCP_HOME, storyboard_spec.pinned_version(REPO_ROOT))

requires_clone = pytest.mark.skipif(
    not DIST.is_dir(),
    reason=f"live pinned AdCP compliance tree not found at {DIST} (clone adcontextprotocol/adcp to ~/projects/adcp)",
)


class _Route:
    def __init__(self, xfail_reason: str | None = None) -> None:
        self.xfail_reason = xfail_reason


@requires_clone
def test_no_artifact_publishes_zero_graded_and_zero_candidates(tmp_path: Path) -> None:
    """Baseline: with no BDD run this session, nothing can be claimed graded or a
    graduation candidate -- missing measurement must render as a gap, not a guess."""
    result = storyboard_check_index.build(REPO_ROOT, ADCP_HOME)
    assert result["totals"]["with_scenario"] > 0, "fixture broken: no on-path check is claimed by any scenario"
    assert result["totals"]["with_live_scenario"] == 0
    assert result["totals"]["graduation_candidates"] == 0
    assert all(not r["graded_by_live_scenario"] for r in result["records"])
    assert all(not r["graduation_candidate"] for r in result["records"])


@requires_clone
def test_registry_wired_scenario_grades_its_claimed_checks(monkeypatch, tmp_path: Path) -> None:
    """A steps-bound scenario whose UC bucket IS a registry row grades every check
    its storyboard claims -- the actual join, not a bool the fixture hands us."""
    scenario_id = "T-UC-019-storyboard-post-create-status-poll"
    artifact = tmp_path / "liveness.json"
    artifact.write_text(
        json.dumps({"scenarios": [{"scenario_id": scenario_id, "steps_bound": True, "ledgered": False}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        scenario_liveness_join, "load_artifact", lambda _path, _fixed=artifact: _real_load_artifact(_fixed)
    )
    monkeypatch.setattr(scenario_liveness_join, "load_env_routes", lambda: {"UC-019": _Route()})

    result = storyboard_check_index.build(REPO_ROOT, ADCP_HOME)
    claiming = [r for r in result["records"] if scenario_id in r["scenarios"]]
    assert claiming, "fixture broken: no on-path check is claimed by T-UC-019-storyboard-post-create-status-poll"
    assert all(r["graded_by_live_scenario"] for r in claiming)
    assert all(r["scenario_liveness"][scenario_id]["registry_wired"] is True for r in claiming)
    assert result["totals"]["with_live_scenario"] >= len(claiming)


@requires_clone
def test_steps_bound_without_registry_row_does_not_grade(monkeypatch, tmp_path: Path) -> None:
    """steps_bound alone (the old 4-of-21 hand measurement) is not enough -- a UC
    bucket absent from ENV_ROUTES must stay ungraded even when its steps run for real."""
    scenario_id = "T-UC-006-storyboard-multi-format-sync"
    artifact = tmp_path / "liveness.json"
    artifact.write_text(
        json.dumps({"scenarios": [{"scenario_id": scenario_id, "steps_bound": True, "ledgered": False}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        scenario_liveness_join, "load_artifact", lambda _path, _fixed=artifact: _real_load_artifact(_fixed)
    )
    monkeypatch.setattr(scenario_liveness_join, "load_env_routes", lambda: {"UC-019": _Route()})  # UC-006 absent

    result = storyboard_check_index.build(REPO_ROOT, ADCP_HOME)
    claiming = [r for r in result["records"] if scenario_id in r["scenarios"]]
    assert claiming, "fixture broken: no on-path check is claimed by T-UC-006-storyboard-multi-format-sync"
    assert all(not r["graded_by_live_scenario"] for r in claiming)
    assert all(r["scenario_liveness"][scenario_id]["registry_wired"] is False for r in claiming)


@requires_clone
def test_ledgered_scenario_marks_graduation_candidate_when_not_measured_failing(monkeypatch, tmp_path: Path) -> None:
    """A scenario ledgered as a known gap, for a check the real conformance run
    does not measure FAILING, is a graduation candidate -- independent of wiring."""
    scenario_id = "T-UC-019-storyboard-post-create-status-poll"
    artifact = tmp_path / "liveness.json"
    artifact.write_text(
        json.dumps({"scenarios": [{"scenario_id": scenario_id, "steps_bound": True, "ledgered": True}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        scenario_liveness_join, "load_artifact", lambda _path, _fixed=artifact: _real_load_artifact(_fixed)
    )
    monkeypatch.setattr(scenario_liveness_join, "load_env_routes", lambda: {})  # not registry-wired at all

    result = storyboard_check_index.build(REPO_ROOT, ADCP_HOME)
    candidates = [r for r in result["records"] if scenario_id in r["scenarios"] and r["measured"] == "no ledger entry"]
    assert candidates, "fixture broken: no 'no ledger entry' check is claimed by T-UC-019-...-poll"
    assert all(r["graduation_candidate"] for r in candidates)
    # Not registry-wired -> not graded -- graduation_candidate does not require it.
    assert all(not r["graded_by_live_scenario"] for r in candidates)
    assert result["totals"]["graduation_candidates"] >= len(candidates)

    rendered = storyboard_check_index.render(result)
    assert "## 4. Graduation candidates" in rendered
    assert f"`{scenario_id}`" in rendered.split("## 4. Graduation candidates")[1].split("## 5.")[0]


@requires_clone
def test_ungradable_checks_are_never_graduation_candidates(monkeypatch, tmp_path: Path) -> None:
    """comply_test_controller-gated checks can never graduate -- excluded even when
    their claiming scenario is ledgered, because 'ungradable' != 'no ledger entry'."""
    scenario_id = "T-UC-019-storyboard-post-create-status-poll"
    artifact = tmp_path / "liveness.json"
    artifact.write_text(
        json.dumps({"scenarios": [{"scenario_id": scenario_id, "steps_bound": True, "ledgered": True}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        scenario_liveness_join, "load_artifact", lambda _path, _fixed=artifact: _real_load_artifact(_fixed)
    )
    monkeypatch.setattr(scenario_liveness_join, "load_env_routes", lambda: {})

    result = storyboard_check_index.build(REPO_ROOT, ADCP_HOME)
    ungradable = [r for r in result["records"] if scenario_id in r["scenarios"] and r["requires_controller"]]
    if not ungradable:
        pytest.skip("no controller-gated check claimed by T-UC-019-...-poll in the current pinned tree")
    assert all(not r["graduation_candidate"] for r in ungradable)

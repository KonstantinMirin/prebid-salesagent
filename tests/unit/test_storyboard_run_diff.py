"""The storyboard run diff compares passing SETS, and a lost pass is a failure.

Two properties carry the whole tool, and both have a way of going wrong silently:

* a skip marker must not count as a pass — otherwise a tree that SKIPPED more storyboards
  scores higher than one that executed them, which is how a regression reads as progress;
* a step that passed on the base and not on the head must make the tool exit non-zero,
  because that is the only thing it exists to catch.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.audit.storyboard_run_diff import _steps, main


def _record(path: Path, steps: list[tuple[str, str, str, bool]]) -> None:
    """Write a runner-shaped record holding exactly *steps* (track, scenario, task, passed)."""
    tracks: dict[str, dict] = {}
    for track, scenario, task, passed in steps:
        t = tracks.setdefault(track, {"track": track, "scenarios": []})
        sc = next((s for s in t["scenarios"] if s["scenario"] == scenario), None)
        if sc is None:
            sc = {"scenario": scenario, "steps": []}
            t["scenarios"].append(sc)
        sc["steps"].append({"task": task, "passed": passed})
    path.write_text(json.dumps({"tracks": list(tracks.values())}))


def test_skip_marker_is_not_counted_as_a_pass(tmp_path: Path) -> None:
    rec = tmp_path / "storyboard_run_mcp.json"
    _record(
        rec,
        [
            ("core", "webhook_emission/requirement_unmet", "Storyboard skipped: requires 'x'", True),
            ("core", "capability_discovery", "get_adcp_capabilities", True),
        ],
    )
    steps = _steps(rec)
    assert list(steps) == ["core::capability_discovery::get_adcp_capabilities"], (
        "a requirement_unmet marker is the runner reporting a successful SKIP, not a graded pass; "
        f"counting it rewards skipping. got {sorted(steps)}"
    )


def test_a_lost_pass_exits_nonzero(tmp_path: Path, monkeypatch, capsys) -> None:
    base, head = tmp_path / "base", tmp_path / "head"
    base.mkdir()
    head.mkdir()
    _record(base / "storyboard_run_mcp.json", [("core", "s", "kept", True), ("core", "s", "dropped", True)])
    _record(head / "storyboard_run_mcp.json", [("core", "s", "kept", True), ("core", "s", "dropped", False)])

    monkeypatch.setattr("sys.argv", ["diff", str(base), str(head), "--protocol", "mcp"])
    assert main() == 1, "a step that passed on the base and fails on the head is the regression this catches"
    assert "core::s::dropped" in capsys.readouterr().out


def test_gaining_passes_is_not_a_failure(tmp_path: Path, monkeypatch) -> None:
    """A head that grades more steps than its base has more passes AND more failures."""
    base, head = tmp_path / "base", tmp_path / "head"
    base.mkdir()
    head.mkdir()
    _record(base / "storyboard_run_mcp.json", [("core", "s", "kept", True)])
    _record(head / "storyboard_run_mcp.json", [("core", "s", "kept", True), ("core", "s", "extra", True)])

    monkeypatch.setattr("sys.argv", ["diff", str(base), str(head), "--protocol", "mcp"])
    assert main() == 0


def test_a_missing_record_is_loud(tmp_path: Path, monkeypatch, capsys) -> None:
    """A protocol with no record was NOT compared, and must not be reported as agreement."""
    base, head = tmp_path / "base", tmp_path / "head"
    base.mkdir()
    head.mkdir()
    _record(base / "storyboard_run_mcp.json", [("core", "s", "kept", True)])

    monkeypatch.setattr("sys.argv", ["diff", str(base), str(head), "--protocol", "mcp"])
    assert main() == 2
    assert "no storyboard record" in capsys.readouterr().err

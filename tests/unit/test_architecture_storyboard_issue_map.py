"""Structural guard: every on-path storyboard is triaged in the issue map.

The storyboard roadmap (`scripts/audit/storyboard_roadmap.py`) claims to be *the* record of what AdCP
grades this agent on and what tracks each gap. That claim only holds if no graded
storyboard is missing from it — and the one input a program cannot derive is whether
an existing GitHub issue covers a gap. That judgement lives in
`docs/test-obligations/storyboard-issue-map.yaml`.

Without this guard, advancing the spec pin would silently introduce untracked
conformance gaps: the new storyboard would be on-path, absent from the map, and the
roadmap would simply not mention it. The document would stay green while getting less
true — the same rot the binding sweep found in the `@storyboard-v3.1` tags.

`coverage: none` is a valid triage outcome. This guard requires a *decision*, not a
ticket. Filing issues is the project's call; saying "graded, untested, untracked" out
loud is this repo's.

Offline: reads the vendored `tests/fixtures/adcp_storyboards_pinned/index.json`, the
same snapshot `test_architecture_storyboard_binding.py` uses, refreshed by the
`_refresh.py` beside it when the pin advances. Never resolves a live `~/projects/adcp`
clone — CI has none.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX = REPO_ROOT / "tests" / "fixtures" / "adcp_storyboards_pinned" / "index.json"
ISSUE_MAP = REPO_ROOT / "docs" / "test-obligations" / "storyboard-issue-map.yaml"

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_coverage_map  # noqa: E402

VALID_COVERAGE = {"full", "partial", "none"}


def _on_path() -> set[str]:
    """On-path storyboards, classified from the vendored index.

    Delegates to `storyboard_coverage_map.on_path_from_vendored_index` so this guard
    and every other fixture-driven on-path check share the one implementation — the
    gate logic has been wrong four separate times during this sweep, and a second
    copy of the offline derivation would be a fifth. (The JSONL artifact-truth guard
    that used to be the other caller went with the committed artifact it graded.)
    """
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    return storyboard_coverage_map.on_path_from_vendored_index(REPO_ROOT, index)


def _map() -> dict[str, dict]:
    loaded = yaml.safe_load(ISSUE_MAP.read_text(encoding="utf-8")) or {}
    return loaded.get("storyboards") or {}


def test_every_on_path_storyboard_is_triaged() -> None:
    """No storyboard AdCP grades us on may be absent from the issue map."""
    untriaged = sorted(_on_path() - set(_map()))
    assert untriaged == [], (
        "On-path storyboards missing from docs/test-obligations/storyboard-issue-map.yaml. "
        "Each needs a triage decision — an issue number, or `coverage: none` stating plainly "
        "that nothing tracks it:\n" + "\n".join(f"  {s}" for s in untriaged)
    )


def test_issue_map_has_no_entries_for_unknown_storyboards() -> None:
    """Entries must name a storyboard that exists at the pin — stale rows mislead."""
    known = set(json.loads(INDEX.read_text(encoding="utf-8"))["storyboards"])
    unknown = sorted(set(_map()) - known)
    assert unknown == [], (
        "Issue-map entries naming storyboards that do not exist at the pinned version. "
        "Remove them, or fix the path:\n" + "\n".join(f"  {s}" for s in unknown)
    )


def test_issue_map_entries_are_well_formed() -> None:
    """Every entry declares a coverage verdict; a partial one says what it leaves out."""
    problems: list[str] = []
    for rel, entry in sorted(_map().items()):
        coverage = entry.get("coverage")
        if coverage not in VALID_COVERAGE:
            problems.append(f"{rel}: coverage {coverage!r} not one of {sorted(VALID_COVERAGE)}")
            continue
        issues = entry.get("issues") or []
        if not all(isinstance(n, int) for n in issues):
            problems.append(f"{rel}: issues must be integers, got {issues!r}")
        if coverage == "partial" and not entry.get("note"):
            problems.append(f"{rel}: coverage 'partial' needs a note saying what is NOT covered")
        if issues and coverage == "none":
            problems.append(f"{rel}: lists issues {issues} but claims coverage 'none' — contradictory")
    assert problems == [], "Malformed storyboard-issue-map.yaml entries:\n" + "\n".join(f"  {p}" for p in problems)


@pytest.mark.parametrize(
    "entry,expected",
    [
        ({"coverage": "sometimes"}, "not one of"),
        ({"coverage": "partial"}, "needs a note"),
        ({"coverage": "none", "issues": [1]}, "contradictory"),
        ({"coverage": "full", "issues": ["1442"]}, "must be integers"),
    ],
)
def test_wellformedness_check_catches_each_defect(monkeypatch, entry: dict, expected: str) -> None:
    """Meta-test: a guard that cannot fail is not a guard."""
    monkeypatch.setattr(f"{__name__}._map", lambda: {"universal/security.yaml": entry})
    with pytest.raises(AssertionError, match=expected):
        test_issue_map_entries_are_well_formed()

"""Structural guard: `docs/test-obligations/storyboard-checks.jsonl` agrees with the
vendored `tests/fixtures/adcp_storyboards_pinned/index.json` it was generated from.

`storyboard_check_index.py --jsonl` (the generator) needs a live `~/projects/adcp`
clone to produce the FULL record set — the per-check grain (`check_type`, `ordinal`,
`phase_id`/`step_id`) comes from raw storyboard YAML text the vendored index does not
carry. That is why the only prior artifact-truth tests for this JSONL were
`requires_clone`-marked and skipped in CI: nothing verified the checked-in file offline.

What IS fully derivable from the vendored index, offline, is the STORYBOARD-LEVEL
shape every record repeats: which storyboards are on our conformance path at all
(`storyboard_coverage_map.on_path_from_vendored_index`, the same offline classifier
the issue-map guard uses), each storyboard's tier, its `required_tools`, and the pinned
version every record's `citation` must cite. This guard regenerates exactly that slice
from the vendored index and diffs it against what is checked in — artifact truth, not a
conformance gate (it says nothing about whether a check is covered or measured, only
whether the checked-in file still agrees with the index it claims to be built from).

Catches: a checked-in JSONL hand-edited to add/misclassify a storyboard, drift a
`required_tools`/`tier` value, or carry a citation for a version the vendored index no
longer represents (a pin bump with no JSONL refresh). It does NOT regenerate or grade
`check_type`/coverage/measured columns — that needs the clone and stays out of CI.

Offline: reads `tests/fixtures/adcp_storyboards_pinned/index.json` and
`docs/test-obligations/storyboard-checks.jsonl` only. Never resolves a live
`~/projects/adcp` clone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX = REPO_ROOT / "tests" / "fixtures" / "adcp_storyboards_pinned" / "index.json"
CHECKS_JSONL = REPO_ROOT / "docs" / "test-obligations" / "storyboard-checks.jsonl"

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_check_index, storyboard_coverage_map, storyboard_spec  # noqa: E402


def _index() -> dict[str, Any]:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def _records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CHECKS_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]


def _violations(records: list[dict[str, Any]], index: dict[str, Any]) -> list[str]:
    """The storyboard-level cross-checks. Empty when the JSONL still agrees with the index."""
    storyboards: dict[str, dict[str, Any]] = index["storyboards"]
    fixture_version: str = index["adcp_spec_version"]
    # The full status map, not just the on-path set: the JSONL now indexes GATED
    # storyboards too (with `gate="GATED"`), so the offline cross-check grades
    # the gate COLUMN rather than asserting every indexed row is on-path.
    statuses = storyboard_coverage_map.statuses_from_vendored_index(REPO_ROOT, index)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["storyboard"], []).append(record)

    problems: list[str] = []
    for rel, rows in sorted(grouped.items()):
        entry = storyboards.get(rel)
        if entry is None:
            problems.append(f"{rel}: not present in the vendored index at {fixture_version}")
            continue

        expected_status = statuses.get(rel, "OFF-PATH")
        if expected_status not in storyboard_check_index.INDEXED_STATUSES:
            problems.append(
                f"{rel}: classifies {expected_status} from the vendored index + declared capabilities, "
                "so it should not be indexed at all"
            )
        else:
            gates = {r["gate"] for r in rows}
            if gates != {expected_status}:
                problems.append(
                    f"{rel}: gate {sorted(gates)} does not match {expected_status!r} derived offline "
                    "from the vendored index + declared capabilities"
                )

        expected_tier = storyboard_spec.storyboard_tier(rel)
        tiers = {r["tier"] for r in rows}
        if tiers != {expected_tier}:
            problems.append(f"{rel}: tier {sorted(tiers)} does not match {expected_tier!r} derived from the path")

        expected_tools = tuple(sorted(entry.get("required_tools", [])))
        tool_sets = {tuple(sorted(r["required_tools"])) for r in rows}
        if tool_sets != {expected_tools}:
            problems.append(
                f"{rel}: required_tools {sorted(tool_sets)} does not match the vendored index's {list(expected_tools)}"
            )

        bad_refs = sorted({r["citation"] for r in rows if f"ref={fixture_version}" not in r["citation"]})
        if bad_refs:
            problems.append(f"{rel}: citation(s) do not cite the fixture's pinned {fixture_version!r}: {bad_refs}")

    return problems


def test_checked_in_jsonl_matches_the_vendored_index() -> None:
    """`docs/test-obligations/storyboard-checks.jsonl` still agrees with the index it was built from."""
    problems = _violations(_records(), _index())
    assert problems == [], (
        "docs/test-obligations/storyboard-checks.jsonl no longer agrees with the vendored "
        "tests/fixtures/adcp_storyboards_pinned/index.json it was generated from. Either the "
        "JSONL was hand-edited, or the vendored index moved (declared capabilities, pin) without "
        "the JSONL being regenerated (`scripts/audit/storyboard_check_index.py --jsonl`, needs "
        "~/projects/adcp):\n" + "\n".join(f"  {p}" for p in problems)
    )


def test_every_checked_in_storyboard_exists_at_the_pin() -> None:
    """No record may cite a storyboard the vendored index does not know about."""
    known = set(_index()["storyboards"])
    unknown = sorted({r["storyboard"] for r in _records()} - known)
    assert unknown == [], (
        "storyboard-checks.jsonl records cite storyboards absent from the vendored index:\n"
        + "\n".join(f"  {s}" for s in unknown)
    )


def test_guard_catches_a_hand_edited_required_tools() -> None:
    """Meta-test: a guard that cannot fail is not a guard."""
    corrupted = [dict(_records()[0])]
    corrupted[0]["required_tools"] = [*corrupted[0]["required_tools"], "not_a_real_tool"]
    problems = _violations(corrupted, _index())
    assert problems, "guard did not flag a hand-edited required_tools value"
    assert "required_tools" in problems[0]


def test_guard_catches_a_hand_edited_tier() -> None:
    """Meta-test: a guard that cannot fail is not a guard."""
    corrupted = [dict(_records()[0])]
    corrupted[0]["tier"] = "specialisms" if corrupted[0]["tier"] != "specialisms" else "protocols"
    problems = _violations(corrupted, _index())
    assert problems, "guard did not flag a hand-edited tier value"
    assert "tier" in problems[0]


def test_guard_catches_a_storyboard_absent_from_the_index() -> None:
    """Meta-test: a guard that cannot fail is not a guard."""
    corrupted = [dict(_records()[0])]
    corrupted[0]["storyboard"] = "protocols/media-buy/scenarios/does-not-exist.yaml"
    problems = _violations(corrupted, _index())
    assert problems, "guard did not flag a storyboard absent from the vendored index"
    assert "not present in the vendored index" in problems[0]


def test_guard_catches_a_stale_citation_after_a_pin_bump() -> None:
    """Meta-test: bumping the pin without refreshing the JSONL must fail loudly."""
    index = _index()
    corrupted = [dict(_records()[0])]
    corrupted[0]["citation"] = corrupted[0]["citation"].replace(f"ref={index['adcp_spec_version']}", "ref=9.9.9")
    problems = _violations(corrupted, index)
    assert problems, "guard did not flag a citation naming a version the fixture no longer represents"
    assert "citation" in problems[0]

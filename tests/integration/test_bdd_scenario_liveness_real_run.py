"""Real-run proof for tests/bdd/scenario_liveness.py (salesagent-vuz9t.12.1).

The pure-logic tests live in ``tests/unit/test_architecture_bdd_scenario_liveness.py``.
This file is the grounding the parent finding demands: the liveness artifact must be
emitted from an ACTUAL BDD run, and a scenario with genuinely unbound steps must be
recorded as such — not asserted against hand-constructed dataclasses.

Shells out to two narrow, fast, real ``pytest tests/bdd`` slices (selected by the
``@storyboard-v3.1`` marker so the count of scenarios discovered matches what
``scripts/audit/storyboard_coverage_map.covered_storyboards`` claims as covered):

* UC-006's ``uc006-storyboard-routing`` scenarios — salesagent-vuz9t.12.3 landed real
  step definitions for all six (none are dormant/steps-unbound any more). Five
  genuinely xfail with a ``ledgered`` reason citing a real production gap
  (provenance validation, multi-format sync status); the sixth,
  format-id-roundtrip-on-sync, genuinely passes. Proves the artifact distinguishes
  ledgered-xfail from live-pass for scenarios that both have their steps bound —
  not just the steps-bound/unbound axis.
* UC-005's format-id-roundtrip scenarios, which pass for real on all three
  in-process transports. Proves ``steps_bound=True`` and ``harness_wired=True`` for a
  scenario that isn't dormant — a guard that only ever proves the negative case isn't
  a guard.

Needs a real Postgres reachable via ``DATABASE_URL`` (the harness these scenarios
exercise creates tenants/principals/products for real) — skipped otherwise, same as
every other ``requires_db`` test in this suite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_bdd_slice(tmp_path: Path, test_file: str, marker_expr: str) -> dict:
    artifact = tmp_path / "liveness.json"
    env = dict(os.environ)
    env["BDD_LIVENESS_ARTIFACT"] = str(artifact)
    env.setdefault("ADCP_TESTING", "true")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            test_file,
            "-m",
            marker_expr,
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert artifact.is_file(), (
        f"pytest subprocess did not write the liveness artifact to {artifact}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return json.loads(artifact.read_text(encoding="utf-8"))


def test_real_run_records_uc006_storyboard_scenarios_as_ledgered_or_live(tmp_path: Path) -> None:
    """All six UC-006 storyboard-routing scenarios have real, bound step definitions
    (salesagent-vuz9t.12.3) — none are dormant/steps-unbound. Five genuinely xfail
    with a real, ledgered production-gap reason (not StepDefinitionNotFoundError);
    the sixth, format-id-roundtrip-on-sync, genuinely passes. Proves the artifact
    tracks real state, not a frozen count, and distinguishes ledgered-xfail from
    live-pass even though both have steps_bound=True."""
    data = _run_bdd_slice(tmp_path, "tests/bdd/test_uc006_sync_creatives.py", "uc006-storyboard-routing")
    scenarios = {s["scenario_id"]: s for s in data["scenarios"]}

    # Only the six scenarios still tagged @storyboard-v3.1 show up here — the two
    # retagged @schema-v3.1 (provenance-claim-contradicted, creative-reception-
    # stateful-render) are correctly excluded, mirroring storyboard_coverage_map's
    # own tag filter (scripts/audit/storyboard_spec.TAG).
    assert set(scenarios) == {
        "T-UC-006-storyboard-provenance-required-rejection",
        "T-UC-006-storyboard-provenance-digital-source-type-missing",
        "T-UC-006-storyboard-provenance-disclosure-missing",
        "T-UC-006-storyboard-provenance-corrected-acceptance",
        "T-UC-006-storyboard-multi-format-sync",
        "T-UC-006-storyboard-format-id-roundtrip-on-sync",
    }
    live_scenario_id = "T-UC-006-storyboard-format-id-roundtrip-on-sync"
    for scenario_id, record in scenarios.items():
        # Every scenario has real steps bound now — the dormant/unbound axis is
        # fully retired for this feature.
        assert record["steps_bound"] is True, f"{scenario_id} unexpectedly reports steps_bound=False"
        assert record["unbound_steps"] == [], f"{scenario_id} unexpectedly reports unbound step text"
        if scenario_id == live_scenario_id:
            assert record["ledgered"] is False
            assert all(o["outcome"] == "passed" for o in record["observations"])
            assert all(o["reason_category"] == "live" for o in record["observations"])
        else:
            assert record["ledgered"] is True, f"{scenario_id} unexpectedly reports ledgered=False"
            assert all(o["outcome"] == "xfailed" for o in record["observations"])
            assert all(o["reason_category"] == "ledgered" for o in record["observations"])
            assert all("SPEC-PRODUCTION GAP" in o["reason"] for o in record["observations"]), (
                f"{scenario_id}'s xfail reason doesn't cite a real production gap"
            )
        # Real transports actually ran (not silently zero, not silently one).
        assert {o["transport"] for o in record["observations"]} == {"mcp", "a2a", "rest"}


def test_real_run_records_uc005_format_id_roundtrip_scenarios_as_live(tmp_path: Path) -> None:
    """A scenario that is NOT dormant reports steps_bound=True/harness_wired=True — the
    guard proves both directions, not only the failure case."""
    data = _run_bdd_slice(tmp_path, "tests/bdd/test_uc005_discover_creative_formats.py", "storyboard-v3.1")
    scenarios = {s["scenario_id"]: s for s in data["scenarios"]}

    assert set(scenarios) == {
        "T-UC-005-storyboard-baseline-format-id-object-shape",
        "T-UC-005-storyboard-format-id-roundtrip-from-products",
        "T-UC-005-storyboard-format-id-third-party-agent-out-of-scope",
    }
    for scenario_id, record in scenarios.items():
        assert record["steps_bound"] is True, f"{scenario_id} unexpectedly reports steps_bound=False"
        assert record["unbound_steps"] == []
        assert record["harness_wired"] is True
        assert record["ledgered"] is False
        assert {o["transport"] for o in record["observations"]} == {"mcp", "a2a", "rest"}
        assert all(o["outcome"] == "passed" for o in record["observations"])

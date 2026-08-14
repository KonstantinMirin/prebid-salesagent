"""Real-run proof for tests/bdd/scenario_liveness.py (salesagent-vuz9t.12.1).

The pure-logic tests live in ``tests/unit/test_architecture_bdd_scenario_liveness.py``.
This file is the grounding the parent finding demands: the liveness artifact must be
emitted from an ACTUAL BDD run, and a scenario with genuinely unbound steps must be
recorded as such — not asserted against hand-constructed dataclasses.

Shells out to two narrow, fast, real ``pytest tests/bdd`` slices (selected by the
``@storyboard-v3.1`` marker so the count of scenarios discovered matches what
``scripts/audit/storyboard_coverage_map.covered_storyboards`` claims as covered):

* UC-006's ``uc006-storyboard-routing`` scenarios — six of these have zero Then step
  definitions today (salesagent-vuz9t.12's finding; the fix is
  salesagent-vuz9t.12.3, not this task) and are known to auto-xfail via
  ``StepDefinitionNotFoundError``. Proves ``steps_bound=False`` with real unbound step
  text, not a synthetic one.
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


def test_real_run_records_uc006_storyboard_scenarios_as_dormant(tmp_path: Path) -> None:
    """The six UC-006 storyboard-routing scenarios with no Then steps are recorded
    steps_bound=False, with the actual unimplemented Gherkin step text — the exact
    defect the parent finding (salesagent-vuz9t.12) measured by hand."""
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
    for scenario_id, record in scenarios.items():
        assert record["steps_bound"] is False, f"{scenario_id} unexpectedly reports steps_bound=True"
        assert record["unbound_steps"], f"{scenario_id} reports no unbound step text"
        assert all(o["reason_category"] == "no_steps_bound" for o in record["observations"])
        assert all(o["outcome"] == "xfailed" for o in record["observations"])
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

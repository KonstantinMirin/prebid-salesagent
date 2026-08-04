"""Storyboard-conformance grading via pytest (SB-4b, salesagent-syhj).

Grades a MEASURED run of the real ``@adcp/sdk`` storyboard runner (never
re-derived/inferred) as ordinary parametrized pytest tests, one per
``(track, storyboard_id, step_id)`` — reusing the exact ledger/xfail/lock-test
discipline ``tests/bdd/e2e_rest_known_failures.txt`` already established
(``tests/storyboard/known_failures.txt`` + ``tests/storyboard/conftest.py``)
instead of a second hand-rolled comparator system (Core Invariant).

Runner-reported skips (``missing_test_controller``, ``missing_tool``,
``prerequisite_failed``, ...) become native ``pytest.skip()`` calls — they are
never ledger entries. Only a genuine check FAILURE is ledgered.

Requires a live in-network stack and the runner's npm deps + the pinned 3.1.1
compliance/schema bundle (see ``tests/storyboard/runner/`` and
``.claude/notes/storyboard-conformance/sb1b-baseline-report.md``'s Reproduce
section) — this module cannot be collected meaningfully without that
environment, matching how ``tests/bdd``'s e2e_rest transport and ``tests/e2e``
already require a live stack to collect.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

_RUNNER_DIR = Path(__file__).parent / "runner"
_ADCP_BIN = _RUNNER_DIR / "node_modules" / ".bin" / "adcp"
_SUMMARY_PATH = _RUNNER_DIR / "results" / "ci-summary.json"

# Env vars the CI job (SB-4b Implementation Plan step 6) must set. No defaults
# for the compliance/schema paths — those come from a pinned GitHub release
# asset (sb1b-baseline-report.md Reproduce step 2), never guessed at.
_AGENT_URL_ENV = "STORYBOARD_AGENT_URL"
_AUTH_TOKEN_ENV = "STORYBOARD_AUTH_TOKEN"
_COMPLIANCE_DIR_ENV = "STORYBOARD_COMPLIANCE_DIR"
_SCHEMA_ROOT_ENV = "STORYBOARD_SCHEMA_ROOT"


def _missing_env() -> list[str]:
    return [name for name in (_COMPLIANCE_DIR_ENV, _SCHEMA_ROOT_ENV) if not os.environ.get(name)]


def _run_storyboard_runner() -> dict[str, Any]:
    """Shell out to the real @adcp/sdk storyboard runner once, return its summary JSON.

    Mirrors the invocation documented in sb1b-baseline-report.md's Reproduce
    step 5, pointed at the in-network agent instead of the host-port smoke
    setup that report used.
    """
    agent_url = os.environ.get(_AGENT_URL_ENV, "http://proxy:8000/mcp/")
    auth_token = os.environ.get(_AUTH_TOKEN_ENV, "ci-test-token")
    cmd = [
        str(_ADCP_BIN),
        "storyboard",
        "run",
        agent_url,
        "--auth",
        auth_token,
        "--allow-http",
        "--compliance-version",
        "3.1.1",
        "--compliance-dir",
        os.environ[_COMPLIANCE_DIR_ENV],
        "--schema-root",
        os.environ[_SCHEMA_ROOT_ENV],
        "--timeout",
        "600",
        "--json",
        "--summary-output",
        str(_SUMMARY_PATH),
    ]
    result = subprocess.run(cmd, cwd=_RUNNER_DIR, capture_output=True, text=True, timeout=700)  # noqa: S603
    if not _SUMMARY_PATH.exists():
        pytest.fail(
            f"storyboard runner did not produce a summary (exit={result.returncode}): "
            f"stdout={result.stdout[-2000:]!r} stderr={result.stderr[-2000:]!r}"
        )
    return json.loads(_SUMMARY_PATH.read_text())


def _collect_checks() -> list[dict[str, Any]]:
    """One entry per (track, storyboard_id, step_id): a failure or a skip.

    Passed checks are not enumerated individually — the runner's summary
    reports a pass/fail/skip count, not a per-check pass record — so a
    passing check has no ledger identity to track; only failures and skips
    are gradeable per-check here.
    """
    summary = _run_storyboard_runner()
    checks: list[dict[str, Any]] = []
    for f in summary["failures"]:
        checks.append(
            {
                "track": f["track"],
                "storyboard_id": f["storyboard_id"],
                "step_id": f["step_id"],
                "status": "fail",
                "reason": f["reason"],
                "reason_kind": f["reason_kind"],
            }
        )
    # skip_causes[].affected entries are "storyboard_id/step_id" (no track —
    # a gap in the runner's own summary shape; skips aren't ledgered so the
    # missing track doesn't affect grading, only the test id's display form).
    for cause in summary.get("skip_causes", []):
        for affected in cause.get("affected", []):
            storyboard_id, _, step_id = affected.partition("/")
            checks.append(
                {
                    "track": None,
                    "storyboard_id": storyboard_id,
                    "step_id": step_id,
                    "status": "skip",
                    "reason": cause.get("detail", ""),
                    "reason_kind": cause["cause"],
                }
            )
    return checks


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "storyboard_check" not in metafunc.fixturenames:
        return
    missing = _missing_env()
    if missing:
        metafunc.parametrize(
            "storyboard_check",
            [{"status": "skip", "reason": f"missing env: {', '.join(missing)}", "reason_kind": "config"}],
            ids=["environment-not-configured"],
        )
        return
    checks = _collect_checks()
    ids = [f"{c['track']}::{c['storyboard_id']}::{c['step_id']}" for c in checks]
    metafunc.parametrize("storyboard_check", checks, ids=ids)


def test_storyboard_check(storyboard_check: dict[str, Any]) -> None:
    """One assertion per measured (track, storyboard_id, step_id) check.

    Known failures xfail(strict=False) via tests/storyboard/conftest.py's
    ledger loader (matched on this test's nodeid) — an un-ledgered failure is
    the regression signal this job exists to catch.
    """
    if storyboard_check["status"] == "skip":
        pytest.skip(f"{storyboard_check['reason_kind']}: {storyboard_check['reason']}")
    assert storyboard_check["status"] != "fail", (
        f"storyboard check failed: {storyboard_check['track']}/{storyboard_check['storyboard_id']}/"
        f"{storyboard_check['step_id']} ({storyboard_check['reason_kind']}) — {storyboard_check['reason']}"
    )

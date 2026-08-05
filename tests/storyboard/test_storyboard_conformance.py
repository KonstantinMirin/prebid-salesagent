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

_REPO_ROOT = Path(__file__).resolve().parents[2]
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

# Webhook receiver. Without one, every expect_webhook* step reports
# `requirement_unmet: webhook_receiver` and is silently ungraded.
#
# The address the SERVER must use to call back to this runner. In-network that is
# the runner container's compose alias (ADCP_WEBHOOK_HOST=tests, set on the tests
# service) — deliberately not "localhost", which the server rewrites to
# host.docker.internal. Unset on the host path, where loopback is correct.
_WEBHOOK_CALLBACK_HOST_ENV = "ADCP_WEBHOOK_HOST"
_WEBHOOK_PORT_ENV = "STORYBOARD_WEBHOOK_PORT"
_DEFAULT_WEBHOOK_PORT = "9998"


def _missing_env() -> list[str]:
    return [name for name in (_COMPLIANCE_DIR_ENV, _SCHEMA_ROOT_ENV) if not os.environ.get(name)]


def _bundle_path(env_name: str) -> str:
    """Resolve a bundle path env var to an absolute path.

    The runner is spawned with ``cwd=_RUNNER_DIR`` so it can find its own
    ``node_modules``, but these paths are naturally written relative to the REPO
    ROOT (that is where the CI job's other paths are rooted, and where a developer
    runs pytest from). Passed through verbatim they resolve against the runner
    directory instead -- ``tests/storyboard/runner/tests/storyboard/runner/...`` --
    and the runner reports the cache as missing, which reads like a broken download
    rather than a path bug.

    Absolute values are passed through untouched.
    """
    raw = Path(os.environ[env_name])
    return str(raw if raw.is_absolute() else (_REPO_ROOT / raw).resolve())


def _webhook_receiver_args() -> tuple[list[str], dict[str, str]]:
    """CLI args + extra env that let the runner host a reachable webhook receiver.

    Two topologies, and the difference is which interface the receiver must listen on:

    * **In-network** (the CI path): the server and this runner are separate
      containers. The server calls back to the runner's compose alias, so the
      receiver has to bind something other than loopback or the delivery lands on
      the container's eth0 with nothing listening. `proxy_url` mode is the SDK's
      sanctioned way to do that -- it takes the URL to advertise, and (unlike
      `loopback_mock`) permits a non-loopback bind.
    * **Host-side**: runner and published ports share a network namespace, so the
      SDK's default loopback receiver already works. Returns no args at all.

    ADCP_WEBHOOK_RECEIVER_HOST is NOT an upstream feature. The CLI has no
    `--webhook-receiver-host`, so it cannot pass `host` through to
    createWebhookReceiver() even though the library accepts it -- filed as
    adcontextprotocol/adcp-client#2448 and bridged meanwhile by
    tests/storyboard/runner/patches/@adcp+sdk+9.3.0.patch, which adds exactly the
    env var the issue proposes. Delete both when the flag ships.
    """
    callback_host = os.environ.get(_WEBHOOK_CALLBACK_HOST_ENV)
    if not callback_host:
        return [], {}

    port = os.environ.get(_WEBHOOK_PORT_ENV, _DEFAULT_WEBHOOK_PORT)
    args = [
        "--webhook-receiver",
        "proxy",
        "--webhook-receiver-port",
        port,
        "--webhook-receiver-public-url",
        f"http://{callback_host}:{port}/",
    ]
    return args, {"ADCP_WEBHOOK_RECEIVER_HOST": "0.0.0.0"}


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
        _bundle_path(_COMPLIANCE_DIR_ENV),
        "--schema-root",
        _bundle_path(_SCHEMA_ROOT_ENV),
        "--timeout",
        "600",
        "--json",
        "--summary-output",
        str(_SUMMARY_PATH),
    ]
    webhook_args, webhook_env = _webhook_receiver_args()
    cmd += webhook_args
    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=_RUNNER_DIR,
        capture_output=True,
        text=True,
        timeout=700,
        env={**os.environ, **webhook_env},
    )
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

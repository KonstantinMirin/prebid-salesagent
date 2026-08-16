"""Regression test for salesagent-8v2yu: the default in-network run must invoke
``tox -p`` (full multi-suite parallelism), not serial ``tox``.

salesagent-8v2yu's live test (run sa-ca89380e) proved the 2026-06-18 OOM
rationale in run_all_tests.sh no longer holds: PYTEST_XDIST_AUTO_NUM_WORKERS /
BDD_XDIST_N caps genuinely reach the in-network tests container, and a real
``tox -p`` run of all 7 suites completed with memory peaking at ~40.5% of the
box (well under the locked 70% fail threshold) with zero OOM-kills. Until the
runner is changed, its default (no-flag) invocation still builds a SERIAL
(no ``-p``) ``tox`` command — this test pins the correct future behavior and
must fail red today.

Runs the REAL run_all_tests.sh end to end (real arg parsing, real env/suite
resolution, real command construction) rather than grepping its source, so it
asserts on genuine behavior instead of text shape. The only thing replaced is
the `docker` binary on PATH -- a stub that records every invocation and exits
0 -- because actually standing up the full Postgres/app/proxy compose stack
(already exercised live for salesagent-8v2yu) is not needed to observe *which
command run_all_tests.sh hands to tox*, and doing so here would make this
regression test slow, non-hermetic, and dependent on a real Docker daemon.
Docker orchestration itself is the true external boundary being stubbed, not
the subject under test.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "run_all_tests.sh"
_CREATIVE_AGENT_STACK = _REPO_ROOT / "scripts" / "creative-agent-stack.sh"

_DOCKER_STUB = """#!/usr/bin/env bash
# Records every invocation of this fake `docker` (argv, space-joined) to
# $DOCKER_STUB_LOG, then reports success unconditionally so run_all_tests.sh's
# control flow proceeds exactly as it would against a real, healthy stack.
printf '%s\\n' "$*" >> "$DOCKER_STUB_LOG"
exit 0
"""


def _run_with_stubbed_docker(tmp_path: Path) -> tuple[subprocess.CompletedProcess, Path]:
    """Runs the real run_all_tests.sh default invocation with `docker` stubbed.

    Returns the completed process and the path to the log of every command the
    script attempted to hand to `docker`.
    """
    workdir = tmp_path / "workdir"
    (workdir / "scripts").mkdir(parents=True)
    shutil.copy2(_RUNNER, workdir / "run_all_tests.sh")
    shutil.copy2(_CREATIVE_AGENT_STACK, workdir / "scripts" / "creative-agent-stack.sh")

    stub_bin = tmp_path / "stub_bin"
    stub_bin.mkdir()
    docker_stub = stub_bin / "docker"
    docker_stub.write_text(_DOCKER_STUB)
    docker_stub.chmod(docker_stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    docker_log = tmp_path / "docker_calls.log"
    docker_log.touch()

    env = {
        **os.environ,
        "PATH": f"{stub_bin}:{os.environ.get('PATH', '')}",
        "DOCKER_STUB_LOG": str(docker_log),
        # The dedicated CI security-audit check already owns this scan; skip it
        # here so a missing/real uvx on the test box can't affect this test.
        "RUN_ALL_SKIP_AUDIT": "1",
    }

    proc = subprocess.run(
        ["bash", "run_all_tests.sh"],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, docker_log


def _tox_invocation_tokens(docker_log: Path) -> list[str]:
    """Extracts the argv tokens run_all_tests.sh hands to `tox` inside the
    tests container, from the recorded `docker compose ... run ... tox ...`
    call (the only stubbed `docker` invocation that names `tox`).
    """
    tox_lines = [line for line in docker_log.read_text().splitlines() if " tox " in f" {line} "]
    assert len(tox_lines) == 1, f"expected exactly one docker invocation naming tox, got: {tox_lines!r}"
    tokens = tox_lines[0].split()
    tox_index = tokens.index("tox")
    return tokens[tox_index + 1 :]


@pytest.mark.slow
def test_default_run_invokes_tox_with_parallel_flag(tmp_path):
    """run_all_tests.sh's default (no-flag) invocation must run `tox -p`
    (genuine multi-suite parallelism), matching what salesagent-8v2yu's live
    test proved safe (7 suites concurrently, ~40.5% peak box memory, no OOM) --
    not the serial (no `-p`) tox call it emits today.
    """
    proc, docker_log = _run_with_stubbed_docker(tmp_path)

    assert proc.returncode == 0, (
        f"run_all_tests.sh (stubbed docker) exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    tox_args = _tox_invocation_tokens(docker_log)

    assert "-p" in tox_args, (
        "run_all_tests.sh's default tox invocation must include -p (parallel "
        f"multi-suite execution) but did not: tox {' '.join(tox_args)}"
    )

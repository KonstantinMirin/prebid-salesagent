#!/usr/bin/env python3
"""Structural guard: registered failure-injection tests must FAIL when the failure is removed.

A test that injects a failure — ``patch(target, side_effect=SomeError(...))`` — and then asserts a
degraded-state VALUE ([], a default, one static product) usually cannot fail. The no-failure path
produces the identical value, so the assertion does not distinguish "the failure was handled" from
"the failure never happened". Three such tests (salesagent-19w8) had been green for their whole
lifetime; a whole-suite sweep found 12 of 45 tripwire sites in that state (salesagent-9278).

**This class is invisible to AST scanning.** It is not a property of the source text but of what an
assertion can distinguish, so the only sound detector is execution: remove the failure and see
whether the test notices. That is what this guard does, for a registry of sites whose sensitivity
has been established. Writing an AST guard here and calling the class covered would repeat exactly
the mistake these tickets are about — a guard that advertises coverage it cannot deliver.

Two neutralization forms are registered per site, because they are complementary and disagree in
both directions (salesagent-9278): ``side_effect=None`` leaves the collaborator returning an
ordinary MagicMock, while ``return_value=<benign>`` makes it return a specific harmless value. A
site can be sensitive to one and blind to the other, so a single-form sweep under-reports.

The registry may only GROW. Each entry is a site whose mutation-sensitivity is pinned; removing one
means giving up that protection.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MutationCase:
    """One (site, neutralization) pair that must make the registered test go red."""

    path: str
    test_pattern: str  # passed to pytest -k
    old: str  # the exact tripwire text
    new: str  # the benign replacement ("the failure never happened")
    why: str

    @property
    def label(self) -> str:
        return f"{self.path}::{self.test_pattern} [{self.new.strip().rstrip(',')}]"


# Registry — may only grow. Sites fixed under salesagent-19w8.
MUTATION_REGISTRY: list[MutationCase] = [
    MutationCase(
        path="tests/unit/test_format_resolver.py",
        test_pattern="registry_creation_fails",
        old='side_effect=RuntimeError("Registry initialization failed"),',
        new="return_value=None,",
        why="`result == []` alone is satisfied by a registry with no formats; the ERROR record is not",
    ),
    MutationCase(
        path="tests/unit/test_format_resolver.py",
        test_pattern="registry_creation_fails",
        old='side_effect=RuntimeError("Registry initialization failed"),',
        new="side_effect=None,",
        why="same site, other neutralization form: a working registry must not satisfy the test",
    ),
    MutationCase(
        path="tests/unit/test_quiet_failure_propagation.py",
        test_pattern="TestDynamicVariantsExceptionPropagation and runtime_error_is_graceful",
        old='AsyncMock(side_effect=RuntimeError("Connection refused"))',
        new="AsyncMock(return_value=[])",
        why="UC-001-MAIN-41 clause 2 ('a warning is logged') — a generator returning nothing logs none",
    ),
    MutationCase(
        path="tests/unit/test_quiet_failure_propagation.py",
        test_pattern="TestDynamicVariantsExceptionPropagation and runtime_error_is_graceful",
        old='AsyncMock(side_effect=RuntimeError("Connection refused"))',
        new="AsyncMock(return_value=None)",
        why="same site, other neutralization form",
    ),
    MutationCase(
        path="tests/unit/test_transport_tenant_resolution.py",
        test_pattern="fallback_when_db_unavailable",
        old='side_effect=RuntimeError("DB not available"),',
        new="return_value=None,",
        why="an unknown tenant reaches the SAME minimal fallback with the same defaults",
    ),
    MutationCase(
        path="tests/unit/test_transport_tenant_resolution.py",
        test_pattern="fallback_when_db_unavailable",
        old='side_effect=RuntimeError("DB not available"),',
        new="return_value=FULL_TENANT_DICT,",
        why="same site: a tenant that loads fine must not satisfy a DB-unavailable test",
    ),
]


def run_under_mutation(case: MutationCase) -> subprocess.CompletedProcess:
    """Run the registered test from a mutated COPY, leaving the working tree untouched.

    The mutant is written to a temp directory and pytest is pointed at it with ``cwd=REPO_ROOT``
    and the repo's pytest.ini, so ``src.*`` / ``tests.*`` imports and asyncio auto-mode resolve
    exactly as they do in place.

    Copying rather than editing in place is deliberate, for two independent reasons:
    - Under xdist another worker may be running the real file's other tests at the same moment;
      mutating it in place would make those fail for reasons that have nothing to do with them.
    - An in-place harness has to restore, and restoring is where this goes wrong. The first version
      of this harness restored with ``git checkout -- <file>``, which restores from the INDEX and
      silently destroyed the uncommitted fixes it was validating — a mutant then read GREEN because
      the file under it had reverted to the weak version. Never restore a mutated file from git.
    """
    path = REPO_ROOT / case.path
    original = path.read_text()
    occurrences = original.count(case.old)
    assert occurrences == 1, (
        f"{case.label}: tripwire anchor found {occurrences}x, expected exactly 1. The registered "
        f"site moved or changed — re-derive the entry, do not delete it."
    )

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="tripwire-mutant-"))
    try:
        mutant = workdir / path.name
        mutant.write_text(original.replace(case.old, case.new))
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(mutant),
                "-k",
                case.test_pattern,
                "-p",
                "no:randomly",
                "-q",
                "--no-header",
                "-c",
                str(REPO_ROOT / "pytest.ini"),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@pytest.mark.parametrize("case", MUTATION_REGISTRY, ids=lambda c: f"{pathlib.Path(c.path).stem}-{c.new.strip()}")
def test_registered_tripwire_test_fails_when_the_failure_is_removed(case: MutationCase):
    result = run_under_mutation(case)

    assert "no tests ran" not in result.stdout, (
        f"{case.label}: the -k pattern selected nothing, so this guard graded nothing. "
        f"The registered test was renamed or removed."
    )
    assert result.returncode != 0, (
        f"{case.label} still PASSES with the failure removed, so it cannot distinguish "
        f"'the failure was handled' from 'the failure never happened'.\n"
        f"Why this site is registered: {case.why}\n"
        f"Fix by asserting the observable consequence of the failure (the logged warning/error, a "
        f"fallback marker, a call count proving the failing collaborator ran) — not the degraded "
        f"value alone.\n\n{result.stdout[-1500:]}"
    )


def test_registry_only_grows():
    """The registry is a ratchet: entries are protection, and protection is not given up quietly."""
    assert len(MUTATION_REGISTRY) >= 6, (
        "MUTATION_REGISTRY shrank below its established size. Each entry pins one site's ability to "
        "fail; removing one silently restores the vacuity it was added to prevent."
    )

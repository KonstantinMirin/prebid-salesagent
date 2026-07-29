#!/usr/bin/env python3
"""Guard: every script in .pre-commit-hooks/ must actually be run by something.

A hook script that nothing invokes is worse than no script. The rule it polices reads as enforced —
CLAUDE.md called two of these mandatory — while nothing runs them, so the repo advertises a
guarantee it does not provide, and the script rots unnoticed. ``check_parameter_alignment.py`` had
decayed to the point of referencing ``src/core/tools.py`` and ``src/core/main.py``, neither of which
has existed since tools became a package; it could not have passed had anyone run it.

A script counts as WIRED when it is named by any of:
  - ``.pre-commit-config.yaml`` (a real hook at any stage)
  - ``Makefile`` (e.g. the ``quality-ci`` target)
  - a GitHub workflow
  - a test that loads and calls it (``check_import_usage.py`` is used exactly this way — the
    tree-wide pytest guard imports it by path, so it is live code and must not be deleted)

Deliberately not enforced here: that the wiring RUNS IN CI. That is a separate gap —
no workflow invokes pre-commit at all, so the pre-push hooks are graded only on a developer's
machine and only over their push range (#1600).

GitHub: #1600
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".pre-commit-hooks"

# Files searched for a reference to each hook script.
WIRING_SOURCES = [
    REPO_ROOT / ".pre-commit-config.yaml",
    REPO_ROOT / "Makefile",
]
WIRING_GLOBS = [
    (REPO_ROOT / ".github" / "workflows", "*.y*ml"),
    (REPO_ROOT / "tests", "**/*.py"),
    (REPO_ROOT / "scripts", "**/*"),
]


def _wiring_corpus() -> str:
    parts: list[str] = []
    for path in WIRING_SOURCES:
        if path.exists():
            parts.append(path.read_text())
    for root, pattern in WIRING_GLOBS:
        if not root.exists():
            continue
        for path in root.rglob(pattern):
            # Exclude this guard's own source: it names hook scripts in prose, which would make
            # every script look wired and the rule vacuous. (Observed — the sentinel below tripped
            # on the guard reading itself.)
            if path.is_file() and "__pycache__" not in path.parts and path != pathlib.Path(__file__).resolve():
                try:
                    parts.append(path.read_text())
                except (UnicodeDecodeError, OSError):
                    continue
    return "\n".join(parts)


def _hook_scripts() -> list[pathlib.Path]:
    return sorted(p for p in HOOKS_DIR.glob("*.py") if "__pycache__" not in p.parts)


def test_hooks_directory_is_discoverable():
    """If discovery finds nothing, the guard below passes while grading nothing."""
    scripts = _hook_scripts()
    assert len(scripts) >= 10, f"Only found {len(scripts)} hook scripts — discovery is broken"


def test_every_hook_script_is_wired():
    corpus = _wiring_corpus()
    unwired = [p.name for p in _hook_scripts() if p.stem not in corpus]

    assert not unwired, (
        "Hook scripts that nothing invokes — dead enforcement:\n  "
        + "\n  ".join(unwired)
        + "\n\nThe rule each polices reads as enforced while nothing runs it. Either wire the script "
        "(.pre-commit-config.yaml, or the Makefile quality-ci target if the commit-stage hook "
        "ceiling is full), fold its rule into the architecture guard that already covers the "
        "ground, or delete it."
    )


def test_wiring_detection_is_not_vacuous():
    """A name that appears nowhere must NOT be reported as wired, or the guard proves nothing."""
    sentinel = "check_" + "absent_sentinel_" + "hook"
    assert sentinel not in _wiring_corpus(), (
        "The wiring corpus matches a name that exists nowhere, so every script would read as wired."
    )

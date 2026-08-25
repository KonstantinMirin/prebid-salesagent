"""Guard: every unit test must have at least one entity marker.

Entity markers (delivery, creative, product, media_buy, tenant, auth, adapter,
inventory, schema, admin, architecture, targeting, transport, workflow, policy,
agent, infra) allow running any slice of the test suite by domain:

    pytest -m delivery          # all delivery tests
    pytest -m "creative and unit"  # creative unit tests only

Markers are auto-applied by filename patterns in tests/conftest.py. This guard
ensures no test slips through without classification. If a new test file doesn't
match any pattern, either:
1. Add a filename pattern to _ENTITY_PATTERNS in tests/conftest.py, or
2. Add an explicit @pytest.mark.<entity> decorator to the test.

The _ALLOWED_UNMARKED set is an escape hatch for tests pending classification.
It must shrink over time — adding new entries is a code smell.

This guard used to answer the question by running `pytest tests/unit/
--collect-only -m "not (...)"` in a SUBPROCESS with a 60s timeout. That timeout
was sized against a serial suite and does not survive parallelism: under
`tox -p` the box runs 16 unit + 16 integration + 16 bdd workers on 16 cores, so
a nested full-suite collection is starved. Measured on box A at 0ea350f11+:

    subprocess.TimeoutExpired: [... 'pytest','tests/unit/','--collect-only' ...]
    timed out after 60 seconds

It was also the single largest contributor to the unit suite's floor (21s on the
16-core box, 28s on the 40-core one). Both problems are the subprocess, not the
timeout — so the subprocess is gone. The auto-marking rule lives in exactly one
place (`tests.conftest.entity_markers_for_path`, which collection itself calls),
and explicit `@pytest.mark.<entity>` decorators are read from the AST. No
subprocess, no timeout, no full-suite re-collection.
"""

import ast
from pathlib import Path

import pytest

from tests.conftest import _ENTITY_MARKERS, entity_markers_for_path
from tests.unit._architecture_helpers import assert_violations_match_allowlist

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Tests pending entity classification — the list may only SHRINK.
#
# Seeded, not authored. The previous version of this guard was VACUOUS: it
# shelled out to `pytest --collect-only -q -m "not (...)"` and scanned stdout for
# lines containing "::", but at this repo's verbosity (pytest.ini's addopts
# carries -v, which -q reduces to normal) --collect-only prints a module TREE and
# not node ids -- so the parser matched 0 of 869 output lines and the guard
# passed unconditionally, on every run, since it was written. Measured: pytest
# reports "685/5740 tests collected (5055 deselected)" for the guard's own query
# while the guard reported nothing unmarked.
#
# These 613 entries are what the honest, in-process guard finds. They are
# PRE-EXISTING debt made visible, not new violations, and the sibling
# stale-entry test enforces that the list only shrinks from here.
_ALLOWED_UNMARKED_PATH = Path(__file__).with_name("unmarked-entity-baseline.txt")
_ALLOWED_UNMARKED: set[str] = {
    line.strip()
    for line in _ALLOWED_UNMARKED_PATH.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}


def _explicit_entity_marks(node: ast.AST) -> set[str]:
    """Entity names in ``@pytest.mark.<entity>`` decorators directly on *node*."""
    marks: set[str] = set()
    for decorator in getattr(node, "decorator_list", []):
        # @pytest.mark.foo  and  @pytest.mark.foo(...)
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in _ENTITY_MARKERS:
            value = target.value
            if isinstance(value, ast.Attribute) and value.attr == "mark":
                marks.add(target.attr)
    return marks


def _collect_unmarked_tests() -> list[str]:
    """Node IDs of unit tests that would carry no entity marker.

    Mirrors what collection does: a file earns markers from
    ``entity_markers_for_path`` (the same function ``pytest_collection_modifyitems``
    calls), and a test can additionally carry an explicit
    ``@pytest.mark.<entity>`` on itself or on its class.
    """
    unmarked: list[str] = []
    for path in sorted((PROJECT_ROOT / "tests" / "unit").rglob("test_*.py")):
        if entity_markers_for_path(str(path)):
            continue  # every test in this file is marked by its path alone

        rel = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                class_marks = _explicit_entity_marks(node)
                for method in node.body:
                    if isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef) and method.name.startswith("test_"):
                        if not (class_marks | _explicit_entity_marks(method)):
                            unmarked.append(f"{rel}::{node.name}::{method.name}")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_"):
                if not _explicit_entity_marks(node):
                    unmarked.append(f"{rel}::{node.name}")

    return unmarked


@pytest.mark.arch_guard
def test_all_unit_tests_have_entity_markers():
    """Every unit test must have at least one entity marker for entity-scoped runs.

    Entity markers are auto-applied by filename patterns in tests/conftest.py.
    If this test fails, it means a test file doesn't match any entity pattern.

    Fix options:
    1. Add a filename pattern to _ENTITY_PATTERNS in tests/conftest.py
    2. Add an explicit @pytest.mark.<entity> decorator to the test
    3. Rename the test file to include an entity keyword
    """
    unmarked = _collect_unmarked_tests()

    # Filter out allowed unmarked tests
    new_violations = [t for t in unmarked if t not in _ALLOWED_UNMARKED]

    if new_violations:
        msg_lines = [
            f"Found {len(new_violations)} unit test(s) without any entity marker:",
            "",
        ]
        for test_id in sorted(new_violations):
            msg_lines.append(f"  {test_id}")
        msg_lines.append("")
        msg_lines.append("Every test must have at least one entity marker from:")
        msg_lines.append(f"  {', '.join(sorted(_ENTITY_MARKERS))}")
        msg_lines.append("")
        msg_lines.append("Fix: Add a filename pattern to _ENTITY_PATTERNS in tests/conftest.py,")
        msg_lines.append("or add an explicit @pytest.mark.<entity> decorator to the test.")
        raise AssertionError("\n".join(msg_lines))


@pytest.mark.arch_guard
def test_allowed_unmarked_entries_still_unmarked():
    """Every _ALLOWED_UNMARKED entry must still be unmarked (stale entry detection).

    When a test gains an entity marker (via pattern or decorator), remove it
    from _ALLOWED_UNMARKED. This test enforces that the allowlist only shrinks.
    """
    if not _ALLOWED_UNMARKED:
        return  # Nothing to check

    unmarked = set(_collect_unmarked_tests())
    assert_violations_match_allowlist(
        unmarked & _ALLOWED_UNMARKED,
        _ALLOWED_UNMARKED,
        fix_hint="Remove fixed entries from _ALLOWED_UNMARKED.",
    )

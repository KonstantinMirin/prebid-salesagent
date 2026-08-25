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

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# A COUNT ratchet, not an allowlist. Every ratchet baseline in this repo is a
# count -- .type-ignore-baseline (63), .mypy-untyped-defs-baseline (227),
# .duplication-baseline and .ruff-complexity-baseline (3-key JSON) -- and none
# enumerates sanctioned violations. An earlier version of this guard shipped a
# 613-line list of node ids, which was a new artifact type: a count cannot be
# gamed by appending your own violation and implies nothing about any individual
# instance, while a 613-line file reads as 613 grants. CLAUDE.md also requires a
# `# FIXME(#<gh-issue>)` at each allowlisted violation's SOURCE location, which a
# central list cannot provide.
#
# The number is not an approval either. It exists because this guard was VACUOUS
# from the day it was written (see the module docstring), so 613 unmarked tests
# accumulated unseen. They live in only ~60 FILES, and entity markers are applied
# BY FILENAME PATTERN, so the fix is ~60 decisions in _ENTITY_PATTERNS -- not 613.
# When the count fails, this guard prints the offenders; it does not sanction them.
_BASELINE_FILE = PROJECT_ROOT / ".unmarked-entity-baseline"


def _baseline_count() -> int:
    return int(_BASELINE_FILE.read_text(encoding="utf-8").strip())


def _entity_from_mark_expr(node: ast.expr) -> str | None:
    """Entity name from a `pytest.mark.<entity>` / `mark.<entity>` expression."""
    target = node.func if isinstance(node, ast.Call) else node
    if not isinstance(target, ast.Attribute) or target.attr not in _ENTITY_MARKERS:
        return None
    value = target.value
    # `pytest.mark.x` (Attribute .mark) or a bare `mark.x` from `from pytest import mark`
    if (isinstance(value, ast.Attribute) and value.attr == "mark") or (
        isinstance(value, ast.Name) and value.id == "mark"
    ):
        return target.attr
    return None


def _explicit_entity_marks(node: ast.AST) -> set[str]:
    """Entity names in `@pytest.mark.<entity>` decorators directly on *node*."""
    return {
        entity
        for decorator in getattr(node, "decorator_list", [])
        if (entity := _entity_from_mark_expr(decorator)) is not None
    }


def _module_level_entity_marks(tree: ast.Module) -> set[str]:
    """Entities from a module-level `pytestmark = ...`, which marks every test in the file.

    Latent today -- the eight files that use `pytestmark` all earn markers by PATH,
    so the walk returns before reaching the AST. Handled anyway: this is an
    OVER-reporting gap, and over-reporting inflates the ratchet rather than
    anchoring it to a false floor.
    """
    marks: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        values = node.value.elts if isinstance(node.value, ast.List | ast.Tuple) else [node.value]
        marks.update(e for v in values if (e := _entity_from_mark_expr(v)) is not None)
    return marks


def _is_test_case_subclass(node: ast.ClassDef) -> bool:
    """A unittest.TestCase subclass collects `testCamelCase`, not just `test_snake`."""
    return any(
        (isinstance(b, ast.Name) and b.id.endswith("TestCase"))
        or (isinstance(b, ast.Attribute) and b.attr.endswith("TestCase"))
        for b in node.bases
    )


def _collect_from_class(node: ast.ClassDef, rel: str, prefix: str, inherited: set[str]) -> list[str]:
    """Unmarked tests in *node*, recursing into nested classes.

    pytest collects nested `Test*` classes, so a walk that only looks at
    `tree.body` would UNDER-report -- the dangerous direction, because it anchors
    the ratchet to a floor lower than reality.
    """
    marks = inherited | _explicit_entity_marks(node)
    name_prefix = f"{prefix}::{node.name}"
    method_prefix = "test" if _is_test_case_subclass(node) else "test_"
    unmarked: list[str] = []
    for child in node.body:
        if isinstance(child, ast.ClassDef) and child.name.startswith("Test"):
            unmarked.extend(_collect_from_class(child, rel, name_prefix, marks))
        elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) and child.name.startswith(method_prefix):
            if not (marks | _explicit_entity_marks(child)):
                unmarked.append(f"{rel}{name_prefix}::{child.name}")
    return unmarked


def _unmarked_in_source(source: str, rel: str = "") -> list[str]:
    """Unmarked test names in *source*, assuming its path earned no marker."""
    tree = ast.parse(source)
    module_marks = _module_level_entity_marks(tree)
    if module_marks:
        return []
    unmarked: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            unmarked.extend(_collect_from_class(node, rel, "", set()))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_"):
            if not _explicit_entity_marks(node):
                unmarked.append(f"{rel}::{node.name}")
    return unmarked


def _collect_unmarked_tests() -> list[str]:
    """Node ids of unit tests that would carry no entity marker.

    Mirrors collection: a file earns markers from `entity_markers_for_path` -- the
    same function `pytest_collection_modifyitems` calls -- and a test can carry an
    explicit `@pytest.mark.<entity>` on itself, its class, an enclosing class, or a
    module-level `pytestmark`.
    """
    unmarked: list[str] = []
    for path in sorted((PROJECT_ROOT / "tests" / "unit").rglob("test_*.py")):
        if entity_markers_for_path(str(path)):
            continue  # every test in this file is marked by its path alone
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        unmarked.extend(_unmarked_in_source(path.read_text(encoding="utf-8"), rel))
    return unmarked


@pytest.mark.arch_guard
def test_unmarked_unit_tests_do_not_increase():
    """Ratchet: the number of unit tests with no entity marker may only fall.

    Entity markers make `make test-entity ENTITY=<x>` meaningful. Every unmarked
    test is one an entity-scoped run silently skips, so this number is a live
    coverage gap, not cosmetic debt.
    """
    unmarked = sorted(_collect_unmarked_tests())
    baseline = _baseline_count()

    if len(unmarked) > baseline:
        new_ones = unmarked[baseline:] if len(unmarked) - baseline < 20 else []
        raise AssertionError(
            f"{len(unmarked)} unit tests have no entity marker, up from {baseline}.\n"
            + ("".join(f"  {t}\n" for t in new_ones) if new_ones else "")
            + "\nEvery test needs one of: "
            + ", ".join(sorted(_ENTITY_MARKERS))
            + "\nFix: add a filename pattern to _ENTITY_PATTERNS in tests/conftest.py "
            "(markers are applied by FILENAME, so one pattern usually fixes a whole file), "
            "or add an explicit @pytest.mark.<entity> to the test."
        )

    if len(unmarked) < baseline:
        raise AssertionError(
            f"Only {len(unmarked)} unit tests are unmarked now, down from {baseline} -- "
            f"lower the ratchet: echo {len(unmarked)} > .unmarked-entity-baseline"
        )


@pytest.mark.arch_guard
def test_the_scan_actually_examined_the_unit_tree():
    """Positive control: prove the scanner saw the suite before trusting a pass.

    Without this the guard is only as trustworthy as its scanner. Its predecessor
    parsed subprocess stdout for a format that repo verbosity never produced,
    matched 0 of 869 lines, and passed unconditionally for its entire life. An
    assertion over a silently-empty collection is not an assertion.

    The same hazard is repo-wide: `assert_violations_match_allowlist` is called at
    48 sites, and at 30 of them both the found set and the allowlist are empty --
    a state that passes whether or not the scanner works. A non-empty allowlist is
    its own positive control; an empty one has none.
    """
    scanned = list((PROJECT_ROOT / "tests" / "unit").rglob("test_*.py"))
    assert len(scanned) > 400, (
        f"only {len(scanned)} unit test files found under {PROJECT_ROOT / 'tests' / 'unit'} -- "
        f"the scanner is broken, and every assertion built on it is vacuous"
    )
    assert any(entity_markers_for_path(str(p)) for p in scanned), (
        "no unit test file earned an entity marker from its path -- entity_markers_for_path "
        "is broken, which would make every test look unmarked"
    )


# ---------------------------------------------------------------------------
# Detector tests — the rule is asserted, not merely observed to agree
# ---------------------------------------------------------------------------
# A zero set-difference against pytest proves the walker is right about the code
# that exists TODAY; it does not prove the rule is right. These feed synthetic
# source for each way pytest's collection diverges from a naive `tree.body` walk,
# so a future shape that this guard would mis-classify fails here instead of
# silently lowering the ratchet's floor. The UNDER-reporting cases matter most:
# they anchor the count to a floor lower than reality.

_SHAPES: dict[str, tuple[str, list[str]]] = {
    "plain unmarked function": ("def test_a(): pass", ["::test_a"]),
    "explicitly marked function": ("import pytest\n@pytest.mark.schema\ndef test_a(): pass", []),
    "alias mark form": ("from pytest import mark\n@mark.schema\ndef test_a(): pass", []),
    "mark called with args": ("import pytest\n@pytest.mark.schema()\ndef test_a(): pass", []),
    "non-entity mark does not count": ("import pytest\n@pytest.mark.slow\ndef test_a(): pass", ["::test_a"]),
    "class-marked methods inherit": (
        "import pytest\n@pytest.mark.schema\nclass TestX:\n    def test_a(self): pass",
        [],
    ),
    "unmarked class methods": ("class TestX:\n    def test_a(self): pass", ["::TestX::test_a"]),
    "NESTED class is collected": (
        "class TestOuter:\n    class TestInner:\n        def test_a(self): pass",
        ["::TestOuter::TestInner::test_a"],
    ),
    "nested class inherits outer mark": (
        "import pytest\n@pytest.mark.schema\nclass TestOuter:\n    class TestInner:\n        def test_a(self): pass",
        [],
    ),
    "module-level pytestmark covers all": (
        "import pytest\npytestmark = pytest.mark.schema\ndef test_a(): pass",
        [],
    ),
    "module-level pytestmark list": (
        "import pytest\npytestmark = [pytest.mark.slow, pytest.mark.schema]\ndef test_a(): pass",
        [],
    ),
    "TestCase collects testCamelCase": (
        "import unittest\nclass TestX(unittest.TestCase):\n    def testCamelCase(self): pass",
        ["::TestX::testCamelCase"],
    ),
    "plain class does NOT collect testCamelCase": (
        "class TestX:\n    def testCamelCase(self): pass",
        [],
    ),
    "async test function": ("async def test_a(): pass", ["::test_a"]),
    "function nested in a test body is not collected": (
        "def test_outer():\n    def test_inner(): pass\n    test_inner()",
        ["::test_outer"],
    ),
    "non-test function ignored": ("def helper(): pass", []),
}


@pytest.mark.arch_guard
@pytest.mark.parametrize("shape", sorted(_SHAPES), ids=lambda s: s.replace(" ", "-"))
def test_walker_classifies_each_collection_shape(shape: str) -> None:
    source, expected = _SHAPES[shape]
    assert _unmarked_in_source(source) == expected

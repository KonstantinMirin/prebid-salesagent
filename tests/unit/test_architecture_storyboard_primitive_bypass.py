"""Structural guard: nobody re-derives a storyboard-tree primitive (salesagent-g6m2.1).

``scripts/audit/storyboard_spec.py`` exists to be the SINGLE implementation of
every fact read out of the pinned AdCP compliance tree. Its own docstring
records why: before it, 14+ primitives had 2-4 incompatible implementations
each, six of which had silently diverged into live bugs.

salesagent-g6m2.1 was the seventh. ``storyboard_roadmap.py`` built its
published check-type inventory by summing ``checks_for_phase()`` over
``phases()`` -- an aggregate the module never offered, invented at the call
site, and wrong: ``phases()`` returns ids at every depth while a phase's
window already encloses its steps', so every nested check was counted twice.
119 of 121 storyboards shipped inflated numbers.

Two forms are banned here, both drawn from that ticket's disease scan:

1. **The aggregate.** Iterating ``phases()`` and calling ``checks_for_phase()``
   inside the loop. There is exactly one correct spelling of that aggregate --
   ``storyboard_spec.check_inventory()`` -- and it is not this one.
2. **The declared-id regex.** Re-deriving a storyboard's top-level ``id:``
   with a local regex instead of ``storyboard_spec.storyboard_id()``.

Structural, not textual: the check walks the AST, so it catches the pattern
through a bare import (``from ... import phases``), through the module
(``storyboard_spec.phases``), and through an aliased import alike. A
name-anchored regex would miss at least one of those spellings -- the
meta-tests below feed all three and require the guard to catch each.

Two files are skipped, neither of them an allowlist of violations:
``storyboard_spec.py``, where these primitives are defined, and this file,
which holds the deliberate violation fixtures the meta-tests feed the guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Where compliance-tree parsing happens at all. Widening this set is the point:
# a new consumer anywhere under these roots is scanned automatically.
SCAN_ROOTS = (REPO_ROOT / "scripts", REPO_ROOT / "tests", REPO_ROOT / "src")

# The only two files the scan skips, and neither is an allowlist of violations:
# storyboard_spec.py is where these primitives are DEFINED, and this file holds
# the deliberate violation fixtures the meta-tests feed to the guard.
PRIMITIVE_HOME = REPO_ROOT / "scripts" / "audit" / "storyboard_spec.py"
EXEMPT = {PRIMITIVE_HOME, Path(__file__).resolve()}

_PHASES = "phases"
_CHECKS_FOR_PHASE = "checks_for_phase"

# A local re-derivation of the storyboard's declared top-level `id:`. Anchored
# on the regex LITERAL rather than on any variable name, since the name is
# whatever the author felt like calling it.
_DECLARED_ID_PATTERNS = (r"^id:", r"^id\s*:")


def _called_name(node: ast.AST) -> str | None:
    """The bare function name of a call, through either ``f()`` or ``mod.f()``."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _calls_within(node: ast.AST, name: str) -> bool:
    return any(_called_name(child) == name for child in ast.walk(node))


def find_summed_phase_aggregates(tree: ast.AST) -> list[int]:
    """Line numbers of loops that iterate phases() and call checks_for_phase().

    Covers the comprehension spelling as well as the statement loop -- the
    original bug used nested ``for`` statements, but
    ``[c for p in phases(t) for c in checks_for_phase(t, p)]`` is the same
    defect written shorter, and one of the two survivors of the original scan
    was written exactly that way.
    """
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            if _called_name(node.iter) == _PHASES and any(_calls_within(stmt, _CHECKS_FOR_PHASE) for stmt in node.body):
                hits.append(node.lineno)
        elif isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp):
            iterates_phases = any(_called_name(gen.iter) == _PHASES for gen in node.generators)
            if iterates_phases and _calls_within(node, _CHECKS_FOR_PHASE):
                hits.append(node.lineno)
    return hits


def find_declared_id_regexes(tree: ast.AST) -> list[int]:
    """Line numbers of string literals re-deriving the storyboard's declared id."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(pattern in node.value for pattern in _DECLARED_ID_PATTERNS)
    ]


def _scan_files() -> list[Path]:
    return sorted(
        path
        for root in SCAN_ROOTS
        if root.is_dir()
        for path in root.rglob("*.py")
        if path.resolve() not in EXEMPT and "__pycache__" not in path.parts
    )


def test_no_consumer_sums_checks_for_phase_over_phases():
    """The salesagent-g6m2.1 double-count may not return in any consumer."""
    violations = {
        str(path.relative_to(REPO_ROOT)): lines
        for path in _scan_files()
        if (lines := find_summed_phase_aggregates(ast.parse(path.read_text(encoding="utf-8"))))
    }
    assert violations == {}, (
        "Summing checks_for_phase() over phases() double-counts every nested check "
        "(a phase's window already encloses its steps'). Call "
        "storyboard_spec.check_inventory() instead — see salesagent-g6m2.1."
    )


def test_no_consumer_re_derives_the_declared_storyboard_id():
    """The declared-id read belongs to storyboard_spec.storyboard_id()."""
    violations = {
        str(path.relative_to(REPO_ROOT)): lines
        for path in _scan_files()
        if (lines := find_declared_id_regexes(ast.parse(path.read_text(encoding="utf-8"))))
    }
    assert violations == {}, (
        "A local `^id:` regex re-derives a compliance-tree primitive. Call "
        "storyboard_spec.storyboard_id() instead — see salesagent-g6m2.1."
    )


# ── Meta-tests: the guard must actually catch what it claims to ─────────────

# The exact shape the bug shipped as, module-qualified.
_VIOLATION_MODULE_QUALIFIED = """
from scripts.audit import storyboard_spec

def build(text):
    checks = {}
    for phase_id in storyboard_spec.phases(text):
        for check_type in storyboard_spec.checks_for_phase(text, phase_id):
            checks[check_type] = checks.get(check_type, 0) + 1
    return checks
"""

# The same defect through a bare import -- no `storyboard_spec.` prefix for a
# name-anchored regex to hook onto.
_VIOLATION_BARE_IMPORT = """
from scripts.audit.storyboard_spec import checks_for_phase, phases

def build(text):
    checks = {}
    for phase_id in phases(text):
        for check_type in checks_for_phase(text, phase_id):
            checks[check_type] = checks.get(check_type, 0) + 1
    return checks
"""

# The same defect as a comprehension, on one line.
_VIOLATION_COMPREHENSION = """
from scripts.audit import storyboard_spec

def build(text):
    return [c for p in storyboard_spec.phases(text) for c in storyboard_spec.checks_for_phase(text, p)]
"""

# Correct: the aggregate primitive, plus the LEAF-ONLY per-phase read that
# test_architecture_storyboard_spec.py legitimately does over an explicit list.
_COMPLIANT = """
from scripts.audit import storyboard_spec

def build(text):
    return storyboard_spec.check_inventory(text)

def leaf_only(text):
    leaves = ["setup", "teardown"]
    return [c for p in leaves for c in storyboard_spec.checks_for_phase(text, p)]
"""


def test_guard_catches_the_aggregate_through_every_import_spelling():
    """Positive meta-test, including the would-be-missed spellings.

    A regex anchored on `storyboard_spec.phases` misses the bare-import form;
    one anchored on nested `for` statements misses the comprehension. The
    guard walks the AST specifically so neither slips.
    """
    for label, source in (
        ("module-qualified", _VIOLATION_MODULE_QUALIFIED),
        ("bare import", _VIOLATION_BARE_IMPORT),
        ("comprehension", _VIOLATION_COMPREHENSION),
    ):
        assert find_summed_phase_aggregates(ast.parse(source)), f"guard missed the {label} spelling"


def test_guard_passes_compliant_source():
    """Negative meta-test: correct code, and the legitimate leaf-only read."""
    assert find_summed_phase_aggregates(ast.parse(_COMPLIANT)) == []


_VIOLATION_DECLARED_ID = """
import re

def storyboard_id(text):
    match = re.search(r"^id:\\s*(\\S+)", text, re.M)
    return match.group(1) if match else None
"""


def test_guard_catches_a_local_declared_id_regex():
    assert find_declared_id_regexes(ast.parse(_VIOLATION_DECLARED_ID))


def test_guard_ignores_unrelated_id_strings():
    """Negative meta-test: `id:` in prose or in a non-anchored pattern is fine."""
    benign = """
LABEL = "id: the storyboard's declared identifier"
PATTERN = r"- id:\\s*(\\S+)"
"""
    assert find_declared_id_regexes(ast.parse(benign)) == []

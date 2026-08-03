"""Guard: AVAILABLE_ADAPTERS must be derived from ADAPTER_REGISTRY, never a hand-typed literal.

Disease (PR #1838 review lineage): src/core/main.py's AVAILABLE_ADAPTERS was a
hand-typed literal list re-enumerating ADAPTER_REGISTRY's keys, and had
drifted — missing 'broadstreet' and 'google_ad_manager', silently downgrading
those tenants to 'mock' at startup. The fix derives it from ADAPTER_REGISTRY
(a list comprehension); this guard bans a literal ``ast.List``/``ast.Tuple``
of string constants from being assigned to that name again — a comprehension,
generator, or other derived expression is fine, only a hand-typed literal is
banned.
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import REPO_ROOT, format_failure, scan_for_ast_violations

GUARD_FILE = "tests/unit/test_guards_available_adapters_derived.py"


def _is_string_literal_collection(node: ast.expr) -> bool:
    if not isinstance(node, ast.List | ast.Tuple):
        return False
    return all(isinstance(elt, ast.Constant) and isinstance(elt.value, str) for elt in node.elts)


def find_hardcoded_available_adapters(tree: ast.Module) -> list[int]:
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "AVAILABLE_ADAPTERS" in targets and _is_string_literal_collection(node.value):
            violations.append(node.lineno)
    return violations


def test_available_adapters_is_not_a_hardcoded_literal():
    violations = scan_for_ast_violations(
        REPO_ROOT, exclude=frozenset({GUARD_FILE}), finder=find_hardcoded_available_adapters
    )
    assert not violations, format_failure(
        summary="AVAILABLE_ADAPTERS assigned a hand-typed literal instead of deriving from ADAPTER_REGISTRY",
        violations=violations,
        fix_hint="Derive from ADAPTER_REGISTRY (e.g. a comprehension excluding non-ad-server keys "
        "like creative_engine) instead of hand-typing the list — a literal will drift.",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def test_detector_catches_known_bad_shape():
    bad = 'AVAILABLE_ADAPTERS = ["mock", "gam", "kevel"]\n'
    assert find_hardcoded_available_adapters(ast.parse(bad))


def test_detector_ignores_derived_comprehension():
    fixed = 'AVAILABLE_ADAPTERS = [k for k in ADAPTER_REGISTRY if k not in {"creative_engine"}]\n'
    assert find_hardcoded_available_adapters(ast.parse(fixed)) == []


def test_detector_ignores_unrelated_literal_list():
    unrelated = 'OTHER_LIST = ["a", "b", "c"]\n'
    assert find_hardcoded_available_adapters(ast.parse(unrelated)) == []

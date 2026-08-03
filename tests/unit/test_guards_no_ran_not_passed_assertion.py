"""Guard: an assertion must grade that a check PASSED, not merely that it RAN.

Disease (PR #1838 review lineage): a test asserts 'valid or errors or
warnings' (or the equivalent bare '.results'/'["results"]' truthy check) — a
shape that is true whenever the validation attempt completed at all, success
or failure, because the callee always appends to one of those fields on any
path. This let real production schema-compliance defects go undetected
through every CI run.

Two forms banned, both AST-based (no reliance on variable naming):

- Form A: ``assert <outcome> or <activity> [or <activity> ...]`` where
  ``<outcome>`` is a dict/attribute access keyed 'valid'/'success'/'passed'/'ok'
  and at least one ``<activity>`` operand is keyed 'errors'/'warnings'/
  'results'/'messages' — the callee's own control flow guarantees the
  activity operand is truthy whenever the check ran, so the outcome operand
  is dead weight.
- Form B: a bare ``assert <x>.results`` / ``assert <x>["results"]`` with no
  per-item outcome check — same "something ran" shape, zero-operand version.
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import REPO_ROOT, format_failure, iter_src_and_test_python_files, safe_parse

GUARD_FILE = "tests/unit/test_guards_no_ran_not_passed_assertion.py"

OUTCOME_KEYS = {"valid", "success", "passed", "ok"}
ACTIVITY_KEYS = {"errors", "warnings", "results", "messages", "warning", "error"}

# Pre-existing violation, tracked for a follow-up fix — shrink-only, never add to this.
# FIXME(#1838): tests/e2e/test_a2a_adcp_compliance.py:346 asserts only that
# compliance_report.results is non-empty, not that any tested skill's validation
# actually passed (Form B — same disease this guard bans).
ALLOWLIST = {
    "tests/e2e/test_a2a_adcp_compliance.py:346",
}


def _keyed_ref(node: ast.expr, vocab: set[str]) -> bool:
    if isinstance(node, ast.Subscript):
        s = node.slice
        if isinstance(s, ast.Constant) and isinstance(s.value, str) and s.value in vocab:
            return True
    return isinstance(node, ast.Attribute) and node.attr in vocab


def find_ran_not_passed_violations(tree: ast.Module) -> list[int]:
    """Line numbers of 'ran, not passed' assertion shapes (Form A and Form B)."""
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test

        # Form A: outcome-or-activity tautology.
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
            has_outcome = any(_keyed_ref(v, OUTCOME_KEYS) for v in test.values)
            has_activity = any(_keyed_ref(v, ACTIVITY_KEYS) for v in test.values)
            if has_outcome and has_activity:
                violations.append(node.lineno)
                continue

        # Form B: bare truthy check on a '.results'/'["results"]' collection.
        if isinstance(test, ast.Attribute) and test.attr == "results":
            violations.append(node.lineno)
        elif isinstance(test, ast.Subscript):
            s = test.slice
            if isinstance(s, ast.Constant) and s.value == "results":
                violations.append(node.lineno)
    return violations


def test_no_ran_not_passed_assertion():
    violations: list[str] = []
    for path, rel in iter_src_and_test_python_files(REPO_ROOT, exclude=frozenset({GUARD_FILE})):
        tree = safe_parse(path)
        if tree is None:
            continue
        for lineno in find_ran_not_passed_violations(tree):
            site = f"{rel}:{lineno}"
            if site not in ALLOWLIST:
                violations.append(site)
    assert not violations, format_failure(
        summary="Assertion grades that a check RAN, not that it PASSED",
        violations=violations,
        fix_hint="Assert the actual outcome (e.g. 'assert result[\"valid\"] is True') instead of "
        "'valid or errors or warnings' (always true once the check ran) or a bare "
        "'.results'/'[\"results\"]' truthy check (true even if every item failed).",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def test_detector_catches_form_a_known_bad_shape():
    bad = 'assert result["valid"] or result["errors"] or result["warnings"]\n'
    assert find_ran_not_passed_violations(ast.parse(bad))


def test_detector_catches_form_a_attribute_shape():
    bad = "assert report.success or report.errors\n"
    assert find_ran_not_passed_violations(ast.parse(bad))


def test_detector_catches_form_b_bare_results_check():
    bad = 'assert compliance_report.results, "Should have collected some test results"\n'
    assert find_ran_not_passed_violations(ast.parse(bad))


def test_detector_ignores_direct_outcome_assertion():
    fixed = 'assert result["valid"] is True, f"should be valid: {result[\'errors\']}"\nassert not result["errors"]\n'
    assert find_ran_not_passed_violations(ast.parse(fixed)) == []


def test_detector_ignores_unrelated_or_assertion():
    unrelated = "assert x or y or z\n"
    assert find_ran_not_passed_violations(ast.parse(unrelated)) == []


def test_detector_ignores_per_item_outcome_loop():
    """A loop asserting each item's own outcome is the correct fixed shape, not this disease."""
    fixed = "for item in report.results:\n    assert item['valid'] is True\n"
    assert find_ran_not_passed_violations(ast.parse(fixed)) == []

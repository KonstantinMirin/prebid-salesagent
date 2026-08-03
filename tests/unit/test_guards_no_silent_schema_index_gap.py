"""Guard: an AdCP schema-index lookup must search every section and must not warn-and-skip.

Disease (PR #1838 review R1-10): ``_find_schema_ref_for_task``
in ``tests/e2e/adcp_schema_validator.py`` hardcoded two literal section lookups
(``index.get("schemas", {}).get("media-buy", {})`` / ``...get("signals", {})``)
instead of iterating every section the pinned index carries — 8 of the pinned
3.1.1 index's 10 task-bearing sections were unreachable. On a miss,
``validate_request``/``validate_response`` printed a warning and returned
instead of raising, so the caller observed "validation passed" having graded
nothing — a quiet failure (CLAUDE.md "No Quiet Failures").

This guard bans both halves of the disease reappearing anywhere in ``src/`` or
``tests/``:

- Form A: a two-level ``X.get("schemas", ...).get("<literal-section>", ...)``
  chain — a single hardcoded section name substituted for iterating
  ``index["schemas"].values()``/``.items()``. AST-based, so quote style and
  whitespace don't evade it.
- Form B: a ``print(...)`` call whose message mentions a schema-resolution
  warning, immediately followed by a bare ``return`` in the same block — the
  warn-and-skip idiom instead of raising. The message match is
  keyword/substring based (case-insensitive "warning" + "schema" +
  "not found"/"no "), not the exact original wording, so a reworded recurrence
  is still caught (see the reworded-wording meta-test below — the
  regex-slip case a literal ``"Don't fail if schema not found"`` string
  search would miss).
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import REPO_ROOT, format_failure, scan_for_ast_violations

GUARD_FILE = "tests/unit/test_guards_no_silent_schema_index_gap.py"


def _string_literal_value(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def find_hardcoded_schema_section_lookups(tree: ast.Module) -> list[int]:
    """Line numbers of ``X.get("schemas", ...).get("<literal>", ...)`` chains."""
    violations: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"):
            continue
        if not node.args or _string_literal_value(node.args[0]) is None:
            continue
        inner = node.func.value
        if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "get"):
            continue
        if not inner.args or _string_literal_value(inner.args[0]) != "schemas":
            continue
        violations.append(node.lineno)
    return violations


def _call_text(call: ast.Call) -> str:
    """Best-effort lowercased text of a call's string/f-string arguments."""
    parts: list[str] = []
    for arg in call.args:
        for sub in ast.walk(arg):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                parts.append(sub.value)
    return " ".join(parts).lower()


def _is_schema_warning_print(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr):
        return False
    call = stmt.value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "print"):
        return False
    text = _call_text(call)
    return "warning" in text and "schema" in text and ("not found" in text or "no " in text)


def find_warn_and_skip_violations(tree: ast.Module) -> list[int]:
    """Line numbers of a schema-warning ``print`` immediately followed by a bare ``return``."""
    violations: list[int] = []
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for i, stmt in enumerate(body[:-1]):
            if _is_schema_warning_print(stmt):
                nxt = body[i + 1]
                if isinstance(nxt, ast.Return) and nxt.value is None:
                    violations.append(stmt.lineno)
    return violations


def test_no_hardcoded_schema_section_lookup():
    violations = scan_for_ast_violations(
        REPO_ROOT, exclude=frozenset({GUARD_FILE}), finder=find_hardcoded_schema_section_lookups
    )
    assert not violations, format_failure(
        summary="Hardcoded single-section lookup against an AdCP schema index (schemas[<literal>])",
        violations=violations,
        fix_hint="Iterate every section — index['schemas'].values()/.items() — instead of "
        "hardcoding a literal section name; see AdCPSchemaValidator._find_schema_ref_for_task.",
        docs_link="docs/development/structural-guards.md",
    )


def test_no_warn_and_skip_on_schema_miss():
    violations = scan_for_ast_violations(
        REPO_ROOT, exclude=frozenset({GUARD_FILE}), finder=find_warn_and_skip_violations
    )
    assert not violations, format_failure(
        summary="print()+return on a schema-resolution miss instead of raising (quiet failure)",
        violations=violations,
        fix_hint="Raise SchemaError (or the caller's own error type) instead of printing a "
        "warning and returning — a caller must not observe 'validation passed' having "
        "graded nothing.",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detectors themselves ────────────────────────────────────


def test_form_a_detector_catches_known_bad_shape():
    bad = 'media_buy_tasks = index.get("schemas", {}).get("media-buy", {})\n'
    assert find_hardcoded_schema_section_lookups(ast.parse(bad))


def test_form_a_detector_ignores_iteration_over_all_sections():
    fixed = (
        "for section in index.get('schemas', {}).values():\n    task_info = section.get('tasks', {}).get(task_name)\n"
    )
    assert find_hardcoded_schema_section_lookups(ast.parse(fixed)) == []


def test_form_a_detector_ignores_unrelated_nested_get_chain():
    unrelated = 'timeout = config.get("network", {}).get("timeout_seconds", 30)\n'
    assert find_hardcoded_schema_section_lookups(ast.parse(unrelated)) == []


def test_form_b_detector_catches_known_bad_shape():
    bad = (
        "def f(task_name):\n"
        "    if not schema_ref:\n"
        "        print(f\"Warning: No request schema found for task '{task_name}'\")\n"
        "        return\n"
    )
    assert find_warn_and_skip_violations(ast.parse(bad))


def test_form_b_detector_catches_reworded_variant():
    """Regex-slip case: a literal '"Don't fail if schema not found"' string search
    would miss this differently-cased, differently-worded recurrence of the same
    disease; the keyword-based detector still catches it."""
    reworded = (
        "def f(task_name):\n"
        "    if not schema_ref:\n"
        "        print(f'WARNING: no response schema was found for {task_name}')\n"
        "        return\n"
    )
    assert find_warn_and_skip_violations(ast.parse(reworded))


def test_form_b_detector_ignores_raise_on_miss():
    fixed = (
        "def f(task_name):\n"
        "    if not schema_ref:\n"
        "        raise SchemaError(f'No request schema found for task {task_name!r}')\n"
    )
    assert find_warn_and_skip_violations(ast.parse(fixed)) == []


def test_form_b_detector_ignores_unrelated_warning_print():
    unrelated = (
        "def f(order_id):\n"
        "    try:\n"
        "        archive(order_id)\n"
        "    except Exception as e:\n"
        "        print(f'Warning: Failed to archive order {order_id}: {e}')\n"
    )
    assert find_warn_and_skip_violations(ast.parse(unrelated)) == []

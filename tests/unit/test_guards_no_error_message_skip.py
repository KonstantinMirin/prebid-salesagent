"""Guard: don't classify a caught exception by string-matching its message, then skip.

Disease (PR #1838 review, ChrisHuie): test_all_adcp_skills_have_schemas caught
every exception from schema resolution, filtered out anything whose message
matched '404' or 'not found', then converted any survivor into pytest.skip().
Once the resolver's own error message started containing 'not found' (a
wording coincidence, unrelated to the filter's intent), every miss was
filtered and the pytest.skip() branch became unreachable dead code — the test
could no longer fail regardless of what schema was actually missing.

Bans the shape: an ``except`` block that string-matches the exception message
(``in str(e)`` / ``.lower()`` comparisons) to decide whether to record it, in
a function that also calls ``pytest.skip`` — the message-matching classifier
is exactly the fragile coupling that made the skip untestable.
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import REPO_ROOT, format_failure, scan_for_ast_violations

GUARD_FILE = "tests/unit/test_guards_no_error_message_skip.py"


def _compares_str_of_exception(node: ast.AST) -> bool:
    """True for a comparison/containment check against ``str(<exc>)`` or its ``.lower()``."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Compare):
            continue
        for operand in (sub.left, *sub.comparators):
            target = operand
            # str(e).lower() -> unwrap the .lower() call to the str(e) call
            if isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute) and target.func.attr == "lower":
                target = target.func.value
            if isinstance(target, ast.Call) and isinstance(target.func, ast.Name) and target.func.id == "str":
                if target.args and isinstance(target.args[0], ast.Name):
                    return True
    return False


def _has_message_gated_append(node: ast.ExceptHandler) -> bool:
    """True if an ``if <message comparison>: <collection>.append(...)`` appears in the handler.

    This is the specific "filter-then-collect" shape (not just any message
    comparison anywhere in the handler — e.g. a positive ``assert "x" in
    str(e)`` proving the RIGHT rejection happened is a different, legitimate
    pattern and must not trip this).
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.If) or not _compares_str_of_exception(sub.test):
            continue
        for stmt in ast.walk(sub):
            if (
                isinstance(stmt, ast.Call)
                and isinstance(stmt.func, ast.Attribute)
                and stmt.func.attr in ("append", "add")
            ):
                return True
    return False


def _calls_pytest_skip(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "skip":
            value = sub.func.value
            if isinstance(value, ast.Name) and value.id == "pytest":
                return True
    return False


def find_error_message_skip_violations(tree: ast.Module) -> list[int]:
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        has_filter_then_collect = any(
            isinstance(sub, ast.ExceptHandler) and _has_message_gated_append(sub) for sub in ast.walk(node)
        )
        if has_filter_then_collect and _calls_pytest_skip(node):
            violations.append(node.lineno)
    return violations


def test_no_error_message_skip():
    violations = scan_for_ast_violations(
        REPO_ROOT, exclude=frozenset({GUARD_FILE}), finder=find_error_message_skip_violations
    )
    assert not violations, format_failure(
        summary="A test classifies caught exceptions by message string-matching, then skips",
        violations=violations,
        fix_hint="Assert the expected outcome directly (e.g. against a pinned index with a "
        "shrink-only allowlist) instead of catching-and-classifying by exception message text — "
        "a wording change in the exception silently neuters the classifier.",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def test_detector_catches_known_bad_shape():
    bad = (
        "async def test_x():\n"
        "    missing = []\n"
        "    try:\n"
        "        await get_schema(path)\n"
        "    except Exception as e:\n"
        "        if '404' not in str(e) and 'not found' not in str(e).lower():\n"
        "            missing.append(e)\n"
        "    if missing:\n"
        "        pytest.skip('some missing')\n"
    )
    assert find_error_message_skip_violations(ast.parse(bad))


def test_detector_ignores_direct_assertion():
    fixed = (
        "async def test_x():\n"
        "    missing = []\n"
        "    ref = await validator._find_schema_ref_for_task(task, 'request')\n"
        "    if ref is None and task not in KNOWN_MISSING:\n"
        "        missing.append(task)\n"
        "    assert not missing\n"
    )
    assert find_error_message_skip_violations(ast.parse(fixed)) == []


def test_detector_ignores_message_match_without_skip():
    """Message-matching alone (e.g. for a log line) isn't the disease — only paired with skip."""
    fine = (
        "async def test_x():\n"
        "    try:\n"
        "        await get_schema(path)\n"
        "    except Exception as e:\n"
        "        if 'not found' not in str(e).lower():\n"
        "            raise\n"
    )
    assert find_error_message_skip_violations(ast.parse(fine)) == []


def test_detector_ignores_skip_without_message_match():
    """A plain skip (e.g. 'requires live server') with no message-classifying except isn't the disease."""
    fine = "def test_x():\n    pytest.skip('requires live server')\n"
    assert find_error_message_skip_violations(ast.parse(fine)) == []


def test_detector_ignores_positive_assertion_with_unrelated_skip():
    """Regression: a positive 'assert expected_text in str(e)' + an unrelated skip()
    in a different branch (e.g. 'skip if the DB doesn't enforce this constraint') is a
    different, legitimate pattern — not the filter-then-silently-drop disease."""
    fine = (
        "def test_x():\n"
        "    try:\n"
        "        insert_bad_row()\n"
        '        pytest.skip("DB doesn\'t validate this (likely SQLite)")\n'
        "    except Exception as e:\n"
        "        assert 'check_constraint' in str(e)\n"
    )
    assert find_error_message_skip_violations(ast.parse(fine)) == []

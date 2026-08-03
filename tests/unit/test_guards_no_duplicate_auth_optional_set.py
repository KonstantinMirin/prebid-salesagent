"""Guard: no second hand-written auth-optional skill/tool frozenset.

Disease (PR #1838 review, layering lens): MCP's AUTH_OPTIONAL_TOOLS and A2A's
DISCOVERY_SKILLS were two independently hand-typed frozensets declaring the
same "which skills are callable without auth" policy, and had drifted —
list_accounts was (incorrectly) marked auth-optional in both, contradicting
the graded BR-UC-011 BDD scenario and _list_accounts_impl's own enforcement.
Both now alias src.core.auth.AUTH_OPTIONAL_SKILLS, the single source of
truth.

This guard bans a frozenset LITERAL (not a Name reference to the shared
constant) from being assigned to a name matching the auth-optional-policy
vocabulary (*_SKILLS, *_TOOLS ending, or containing DISCOVERY/AUTH_OPTIONAL)
anywhere outside the canonical module.
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import REPO_ROOT, format_failure, scan_for_ast_violations

CANONICAL_FILE = "src/core/auth.py"
GUARD_FILE = "tests/unit/test_guards_no_duplicate_auth_optional_set.py"


def _name_matches_policy_vocabulary(name: str) -> bool:
    upper = name.upper()
    return upper.endswith("_SKILLS") or upper.endswith("_TOOLS") or "DISCOVERY" in upper or "AUTH_OPTIONAL" in upper


def _is_frozenset_literal(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and bool(node.args)
        and isinstance(node.args[0], ast.Set | ast.List)
    )


def find_duplicate_auth_optional_sets(tree: ast.Module) -> list[int]:
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if any(_name_matches_policy_vocabulary(t) for t in targets) and _is_frozenset_literal(node.value):
            violations.append(node.lineno)
    return violations


def test_no_duplicate_auth_optional_set():
    exclude = frozenset({CANONICAL_FILE, GUARD_FILE})
    violations = scan_for_ast_violations(REPO_ROOT, exclude=exclude, finder=find_duplicate_auth_optional_sets)
    assert not violations, format_failure(
        summary="A hand-written frozenset re-implements the auth-optional skill/tool policy",
        violations=violations,
        fix_hint="Import AUTH_OPTIONAL_SKILLS from src.core.auth instead of hand-writing a new "
        "policy frozenset — two independent copies is exactly what drifted list_accounts's auth "
        "requirement out of sync across transports.",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def test_detector_catches_known_bad_shape():
    bad = 'DISCOVERY_SKILLS = frozenset({"get_adcp_capabilities", "list_accounts", "get_products"})\n'
    assert find_duplicate_auth_optional_sets(ast.parse(bad))


def test_detector_catches_auth_optional_tools_literal():
    bad = 'AUTH_OPTIONAL_TOOLS = frozenset({"get_products", "list_creative_formats"})\n'
    assert find_duplicate_auth_optional_sets(ast.parse(bad))


def test_detector_ignores_alias_of_shared_constant():
    fixed = "from src.core.auth import AUTH_OPTIONAL_SKILLS\nDISCOVERY_SKILLS = AUTH_OPTIONAL_SKILLS\n"
    assert find_duplicate_auth_optional_sets(ast.parse(fixed)) == []


def test_detector_ignores_unrelated_frozenset():
    unrelated = 'VALID_STATUSES = frozenset({"active", "closed"})\n'
    assert find_duplicate_auth_optional_sets(ast.parse(unrelated)) == []

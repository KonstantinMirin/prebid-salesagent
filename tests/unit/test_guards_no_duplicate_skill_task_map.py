"""Guard: no second hand-written A2A skill-name -> AdCP-task-name dict literal.

Disease (PR #1838 review R1-10 measurement): two independent dict literals —
``A2AAdCPValidator.SKILL_TO_SCHEMA_MAP`` in
tests/integration/test_a2a_skill_invocation.py and a local ``skill_to_schema``
dict inside tests/e2e/test_a2a_adcp_compliance.py — implemented the same
skill-name -> AdCP-task-name mapping concept and drifted apart with no test
catching it. The fix collapsed both into one shared, index-validated map:
``tests.helpers.skill_to_adcp_task.SKILL_TO_ADCP_TASK``.

This guard fingerprints the disease by dict CONTENT, not by variable name (a
rename would evade a name-based check): a dict literal anywhere in ``src/`` or
``tests/`` — other than the canonical module itself — that maps 3 or more
known skill names to either ``None`` or their own AdCP task-name spelling
(``skill_name`` -> ``"skill-name"``) is a reintroduced hand-written copy.
Matching on key set ALONE over-fires: several legitimate dicts in this
codebase (an A2A skill dispatch table to handler callables, a task-name to
response-class map, a skill to required-fields-set map, ...) share the same
key vocabulary but map to a completely different kind of value — the value
shape is what makes this dict specifically a skill->task-name lookup.
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import (
    REPO_ROOT,
    find_dict_literals_with_matching_entries,
    format_failure,
    scan_for_ast_violations,
)

CANONICAL_FILE = "tests/helpers/skill_to_adcp_task.py"
GUARD_FILE = "tests/unit/test_guards_no_duplicate_skill_task_map.py"

# The known A2A skill-name vocabulary this map covers.
KNOWN_SKILL_NAMES = {
    "get_products",
    "create_media_buy",
    "update_media_buy",
    "get_media_buy_delivery",
    "sync_creatives",
    "list_creatives",
    "approve_creative",
    "add_creative_assets",
    "get_media_buy_status",
    "optimize_media_buy",
}
MIN_MATCHING_ENTRIES = 3


def _is_task_name_value(skill_name: str, value: ast.expr) -> bool:
    """True if *value* is ``None`` or the AdCP task-name spelling of *skill_name*."""
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    return isinstance(value, ast.Constant) and value.value == skill_name.replace("_", "-")


def find_duplicate_skill_task_maps(tree: ast.Module) -> list[int]:
    """Line numbers of dict literals matching >=3 known skill-name -> task-name entries."""
    return find_dict_literals_with_matching_entries(
        tree,
        key_matches=lambda name: name in KNOWN_SKILL_NAMES,
        value_matches=_is_task_name_value,
        min_matches=MIN_MATCHING_ENTRIES,
    )


def test_no_duplicate_skill_task_map():
    exclude = frozenset({CANONICAL_FILE, GUARD_FILE})
    violations = scan_for_ast_violations(REPO_ROOT, exclude=exclude, finder=find_duplicate_skill_task_maps)
    assert not violations, format_failure(
        summary="A hand-written dict literal re-implements the skill->AdCP-task map",
        violations=violations,
        fix_hint="Import SKILL_TO_ADCP_TASK from tests.helpers.skill_to_adcp_task instead of "
        "hand-writing a new copy of the skill-name -> AdCP-task-name mapping.",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def test_detector_catches_known_bad_shape():
    bad = (
        "SKILL_TO_SCHEMA_MAP = {\n"
        '    "get_products": "get-products",\n'
        '    "create_media_buy": "create-media-buy",\n'
        '    "sync_creatives": "sync-creatives",\n'
        "}\n"
    )
    assert find_duplicate_skill_task_maps(ast.parse(bad))


def test_detector_ignores_import_of_shared_map():
    fixed = (
        "from tests.helpers.skill_to_adcp_task import SKILL_TO_ADCP_TASK\nSKILL_TO_SCHEMA_MAP = SKILL_TO_ADCP_TASK\n"
    )
    assert find_duplicate_skill_task_maps(ast.parse(fixed)) == []


def test_detector_ignores_unrelated_dict_with_few_matching_keys():
    unrelated = 'config = {"get_products": True, "timeout": 30, "retries": 3}\n'
    assert find_duplicate_skill_task_maps(ast.parse(unrelated)) == []


def test_detector_ignores_skill_dispatch_table():
    """Key-set overlap alone is not enough — a skill->handler dispatch table (or any
    skill->non-task-name-shaped value dict) is a different domain concept."""
    dispatch_table = (
        "skill_handlers = {\n"
        '    "get_products": self._handle_get_products_skill,\n'
        '    "create_media_buy": self._handle_create_media_buy_skill,\n'
        '    "sync_creatives": self._handle_sync_creatives_skill,\n'
        "}\n"
    )
    assert find_duplicate_skill_task_maps(ast.parse(dispatch_table)) == []


def test_detector_ignores_skill_to_required_fields_map():
    required_fields = (
        "SKILL_REQUIRED_FIELDS = {\n"
        '    "create_media_buy": set(),\n'
        '    "sync_creatives": {"creatives"},\n'
        '    "get_products": {"products"},\n'
        "}\n"
    )
    assert find_duplicate_skill_task_maps(ast.parse(required_fields)) == []


def test_detector_catches_local_variable_form():
    """The original disease site was a LOCAL variable inside a method, not module-level."""
    bad = (
        "def validate_skill_response(self, skill_name, response):\n"
        "    skill_to_schema = {\n"
        '        "get_products": "get-products",\n'
        '        "create_media_buy": "create-media-buy",\n'
        '        "add_creative_assets": "add-creative-assets",\n'
        "    }\n"
        "    return skill_to_schema.get(skill_name)\n"
    )
    assert find_duplicate_skill_task_maps(ast.parse(bad))

"""Guard: wire-facing serialization shortcuts that leak nulls or drop fields.

Disease (PR #1838 review lineage): Product.model_dump() (src/core/schemas/product.py)
forced ``exclude_none=False`` at its own level (needed to keep certain
required-but-currently-None fields present) but never recursively stripped
None from nested substructures — every optional field of every nested object
(format_ids, placements, pricing_options, publisher_properties,
delivery_measurement) leaked explicit ``null``, which the pinned AdCP schema
types (rejects null for those fields). Separately, AdCPRequestHandler.
_get_products (src/a2a_server/adcp_a2a_server.py) hand-built a response dict
instead of calling the response model's own ``model_dump()`` (as its sibling
``_handle_get_products_skill`` correctly does), silently dropping
schema-required fields (cache_scope, status) the model already computes
correctly.

Two forms banned:

- Form A: a ``model_dump`` method setting ``exclude_none=False`` (directly or
  via ``kwargs["exclude_none"] = False``) without also calling
  ``strip_none_deep`` somewhere in the same function body — the escape hatch
  that makes ``exclude_none=False`` safe for nested structures.
- Form B (narrow, named): the two known get_products A2A response-building
  methods (``_get_products``, ``_handle_get_products_skill``) must each
  contain a ``.model_dump(`` call — structural parity between the sibling
  paths, so one drifting back to a hand-rolled dict is caught.
"""

from __future__ import annotations

import ast

from tests.unit._architecture_helpers import REPO_ROOT, format_failure, safe_parse

GUARD_FILE = "tests/unit/test_guards_wire_serialization_shortcuts.py"
SCHEMAS_DIR = "src/core/schemas"
A2A_SERVER_FILE = "src/a2a_server/adcp_a2a_server.py"
GET_PRODUCTS_HANDLER_NAMES = {"_get_products", "_handle_get_products_skill"}


def _sets_exclude_none_false(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        # kwargs["exclude_none"] = False
        if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Constant) and sub.value.value is False:
            for target in sub.targets:
                if isinstance(target, ast.Subscript):
                    s = target.slice
                    if isinstance(s, ast.Constant) and s.value == "exclude_none":
                        return True
        # exclude_none=False as a call keyword
        if isinstance(sub, ast.Call):
            for kw in sub.keywords:
                if kw.arg == "exclude_none" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    return True
    return False


def _calls_strip_none_deep(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
            if name == "strip_none_deep":
                return True
    return False


def find_unsafe_exclude_none_false(tree: ast.Module) -> list[int]:
    """Form A: model_dump methods forcing exclude_none=False without strip_none_deep."""
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != "model_dump":
            continue
        if _sets_exclude_none_false(node) and not _calls_strip_none_deep(node):
            violations.append(node.lineno)
    return violations


def _has_top_level_model_dump_call(node: ast.AST, *, inside_comprehension: bool = False) -> bool:
    """True if a ``.model_dump(`` call exists outside any comprehension.

    A per-item ``[p.model_dump() for p in response.products]`` dumps each
    nested item but never the response itself (so schema-required
    response-level fields like cache_scope/status are never captured) — only
    a call outside a comprehension counts as "dumped the whole response".
    """
    for child in ast.iter_child_nodes(node):
        child_in_comp = inside_comprehension or isinstance(
            child, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
        )
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "model_dump":
            if not child_in_comp:
                return True
        if _has_top_level_model_dump_call(child, inside_comprehension=child_in_comp):
            return True
    return False


def find_hand_rolled_get_products_response(tree: ast.Module) -> list[int]:
    """Form B: named get_products handlers that never dump the full response."""
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name not in GET_PRODUCTS_HANDLER_NAMES:
            continue
        if not _has_top_level_model_dump_call(node):
            violations.append(node.lineno)
    return violations


def test_no_unsafe_exclude_none_false_in_schemas():
    violations: list[str] = []
    repo = REPO_ROOT
    for path in sorted((repo / SCHEMAS_DIR).glob("*.py")):
        rel = str(path.relative_to(repo))
        if rel == GUARD_FILE:
            continue
        tree = safe_parse(path)
        if tree is None:
            continue
        for lineno in find_unsafe_exclude_none_false(tree):
            violations.append(f"{rel}:{lineno}")
    assert not violations, format_failure(
        summary="model_dump() forces exclude_none=False without recursively stripping nested nulls",
        violations=violations,
        fix_hint="Call strip_none_deep() (src/core/schemas/_base.py) on nested field values before "
        "returning — exclude_none=False at this level otherwise leaks null into every optional "
        "field of every nested object, which AdCP schemas type (reject null).",
        docs_link="docs/development/structural-guards.md",
    )


def test_get_products_handlers_reuse_model_dump():
    violations: list[str] = []
    path = REPO_ROOT / A2A_SERVER_FILE
    tree = safe_parse(path)
    if tree is not None:
        for lineno in find_hand_rolled_get_products_response(tree):
            violations.append(f"{A2A_SERVER_FILE}:{lineno}")
    assert not violations, format_failure(
        summary="A get_products A2A handler hand-builds its response instead of reusing model_dump()",
        violations=violations,
        fix_hint="Call response.model_dump(mode='json') on the full GetProductsResponse (matching "
        "the sibling handler) instead of hand-constructing a partial dict — a hand-rolled dict "
        "silently drops schema-required fields (cache_scope, status) the model already computes.",
        docs_link="docs/development/structural-guards.md",
    )


# ── Meta-tests: the detectors themselves ─────────────────────────────────────


def test_form_a_detector_catches_known_bad_shape():
    bad = (
        "class X:\n"
        "    def model_dump(self, **kwargs):\n"
        '        kwargs["exclude_none"] = False\n'
        "        data = super().model_dump(**kwargs)\n"
        "        return data\n"
    )
    assert find_unsafe_exclude_none_false(ast.parse(bad))


def test_form_a_detector_ignores_when_strip_none_deep_called():
    fixed = (
        "class X:\n"
        "    def model_dump(self, **kwargs):\n"
        '        kwargs["exclude_none"] = False\n'
        "        data = super().model_dump(**kwargs)\n"
        "        return {k: strip_none_deep(v) for k, v in data.items()}\n"
    )
    assert find_unsafe_exclude_none_false(ast.parse(fixed)) == []


def test_form_a_detector_ignores_exclude_none_true():
    fine = "class X:\n    def model_dump(self, **kwargs):\n        kwargs['exclude_none'] = True\n        return super().model_dump(**kwargs)\n"
    assert find_unsafe_exclude_none_false(ast.parse(fine)) == []


def test_form_b_detector_catches_hand_rolled_dict():
    bad = (
        "class X:\n"
        "    async def _get_products(self, query, identity):\n"
        "        response = await core_get_products_tool(brief=query, identity=identity)\n"
        "        products = [p.model_dump(mode='json') for p in response.products]\n"
        "        return {'products': products, 'message': str(response)}\n"
    )
    assert find_hand_rolled_get_products_response(ast.parse(bad))


def test_form_b_detector_ignores_full_model_dump():
    fixed = (
        "class X:\n"
        "    async def _get_products(self, query, identity):\n"
        "        response = await core_get_products_tool(brief=query, identity=identity)\n"
        "        response_data = response.model_dump(mode='json')\n"
        "        response_data['message'] = str(response)\n"
        "        return response_data\n"
    )
    assert find_hand_rolled_get_products_response(ast.parse(fixed)) == []


def test_form_b_detector_ignores_unrelated_functions():
    unrelated = "class X:\n    async def _get_media_buys(self, query, identity):\n        return {'media_buys': []}\n"
    assert find_hand_rolled_get_products_response(ast.parse(unrelated)) == []

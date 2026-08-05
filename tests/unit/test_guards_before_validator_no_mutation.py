"""Guard: pydantic ``@model_validator(mode="before")`` methods must not mutate
their input dict in place without first taking a defensive copy.

Regression guard for GH #1710-adjacent finding (A2A list_creatives format_id
serialized as a bare string instead of {agent_url, id}): pydantic-core hands a
``mode="before"`` validator its input dict BY REFERENCE -- notably, when
validating a ``list[Model]`` field on a parent model, each list item's dict is
passed to the item model's before-validator without a defensive copy. A
validator that mutates that dict in place (``values["x"] = y``, ``values.pop(...)``,
``values.update(...)``) therefore corrupts whatever dict the CALLER still holds a
reference to.

Concretely: ``src/a2a_server/adcp_a2a_server.py``'s ``_reconstruct_response_object``
reconstructs a typed response FROM the same dict about to be sent on the A2A wire
(purely to build a human-readable text part). ``Creative.validate_format_id``
mutated its input dict, silently replacing a spec-compliant ``{agent_url, id}``
nested dict with a live ``FormatId`` Python object in the CALLER's dict -- which the
wire serializer's ``json.dumps(default=str)`` fallback then silently stringified.

Rule: every ``@model_validator(mode="before")`` method that mutates its input
parameter (subscript assignment, ``.pop()``, ``.update()``, ``.setdefault()``,
``.clear()``) must first reassign that parameter to a copy
(``values = values.copy()`` / ``values = dict(values)``) before any such mutation.
A validator that never mutates its input (read-only / raises) is exempt.

Ships with ZERO violations; no allowlist (repo hard rule: allowlists never grow).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "src" / "core" / "schemas"

_MUTATING_METHODS = {"pop", "update", "setdefault", "clear", "popitem"}


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return None


def _is_before_validator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        fn = dec.func
        name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if name != "model_validator":
            continue
        for kw in dec.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and kw.value.value == "before":
                return True
    return False


def _param_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    # Skip `cls` (classmethod) — the input dict is the next positional arg.
    args = [a.arg for a in node.args.args]
    if args and args[0] == "cls":
        args = args[1:]
    return args[0] if args else None


def _is_copy_reassignment(stmt: ast.stmt, param: str) -> bool:
    """True for `<param> = <param>.copy()` or `<param> = dict(<param>)`."""
    if not isinstance(stmt, ast.Assign):
        return False
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name) or stmt.targets[0].id != param:
        return False
    value = stmt.value
    if isinstance(value, ast.Call):
        fn = value.func
        if isinstance(fn, ast.Attribute) and fn.attr == "copy" and isinstance(fn.value, ast.Name):
            return True
        if isinstance(fn, ast.Name) and fn.id == "dict":
            return True
    return False


def _mutates_param(stmt: ast.stmt, param: str) -> bool:
    for node in ast.walk(stmt):
        # values[...] = ... / values[...] += ...
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == param:
                    return True
        if isinstance(node, ast.AugAssign):
            t = node.target
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == param:
                return True
        # values.pop(...) / values.update(...) / etc.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func
            if attr.attr in _MUTATING_METHODS and isinstance(attr.value, ast.Name) and attr.value.id == param:
                return True
    return False


def find_unsafe_before_validators(src_files: dict[str, ast.AST]) -> list[str]:
    """``file:line: method_name`` for every before-validator that mutates its input
    without a preceding defensive copy."""
    offenders: list[str] = []
    for path, tree in sorted(src_files.items()):
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not _is_before_validator(node):
                continue
            param = _param_name(node)
            if not param:
                continue

            copied = False
            for stmt in node.body:
                if _is_copy_reassignment(stmt, param):
                    copied = True
                    continue
                if not copied and _mutates_param(stmt, param):
                    offenders.append(f"{path}:{node.lineno}: {node.name}")
                    break
    return offenders


def test_no_unsafe_before_validator_mutation():
    src_files = {str(p.relative_to(REPO_ROOT)): t for p in sorted(SCHEMAS_DIR.rglob("*.py")) if (t := _parse(p))}
    violations = find_unsafe_before_validators(src_files)
    assert not violations, (
        '@model_validator(mode="before") mutates its input dict without a '
        "defensive copy first -- pydantic-core hands list-item dicts to "
        "before-validators BY REFERENCE, so this can corrupt a dict the caller "
        "still holds (traced production bug: A2A list_creatives format_id). Add "
        "`values = values.copy()` before any mutation. Violations:\n  " + "\n  ".join(violations)
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def _detect(src_snippets: dict[str, str]) -> list[str]:
    return find_unsafe_before_validators({k: ast.parse(v) for k, v in src_snippets.items()})


class TestGuardDetector:
    def test_positive_subscript_assignment_without_copy(self):
        src = (
            "class M:\n"
            "    @model_validator(mode='before')\n"
            "    @classmethod\n"
            "    def v(cls, values):\n"
            "        values['x'] = 1\n"
            "        return values\n"
        )
        assert _detect({"src/t.py": src})

    def test_positive_pop_without_copy(self):
        src = (
            "class M:\n"
            "    @model_validator(mode='before')\n"
            "    @classmethod\n"
            "    def v(cls, values):\n"
            "        values.pop('x', None)\n"
            "        return values\n"
        )
        assert _detect({"src/t.py": src})

    def test_negative_copy_then_mutate(self):
        src = (
            "class M:\n"
            "    @model_validator(mode='before')\n"
            "    @classmethod\n"
            "    def v(cls, values):\n"
            "        values = values.copy()\n"
            "        values['x'] = 1\n"
            "        return values\n"
        )
        assert not _detect({"src/t.py": src})

    def test_negative_dict_copy_then_mutate(self):
        src = (
            "class M:\n"
            "    @model_validator(mode='before')\n"
            "    @classmethod\n"
            "    def v(cls, values):\n"
            "        values = dict(values)\n"
            "        values.pop('x', None)\n"
            "        return values\n"
        )
        assert not _detect({"src/t.py": src})

    def test_negative_read_only_validator(self):
        src = (
            "class M:\n"
            "    @model_validator(mode='before')\n"
            "    @classmethod\n"
            "    def v(cls, values):\n"
            "        if not values.get('x'):\n"
            "            raise ValueError('missing x')\n"
            "        return values\n"
        )
        assert not _detect({"src/t.py": src})

    def test_negative_not_a_before_validator(self):
        src = (
            "class M:\n    @model_validator(mode='after')\n    def v(self):\n        self.x = 1\n        return self\n"
        )
        assert not _detect({"src/t.py": src})

#!/usr/bin/env python3
"""Scan for RootModel values being stringified into persisted/derived strings.

The defect this finds (salesagent-myhs): ``str()`` or f-string interpolation of a
pydantic ``RootModel`` does NOT yield the wrapped scalar — it yields the model's
repr, ``root='brand_one'``. When that string is persisted (a natural key, a display
name) the stored value is permanently mangled and, for a column typed
``JSONType(model=...)``, the row stops being loadable through the ORM at all.

Method: derive the set of field names whose declared type is (or contains) a
RootModel from the installed ``adcp`` SDK plus ``src.core.schemas``, then AST-scan
``src/`` for f-string interpolations, ``str(...)`` calls and ``+`` concatenations
whose terminal attribute is one of those names. Type-directed rather than
text-directed, so it does not depend on how a call site happens to be spelled.

Usage:
    uv run python scripts/ci/scan_rootmodel_stringification.py [--json]
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import pkgutil
import sys
import typing
from pathlib import Path

import pydantic

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _is_root_model(tp: object) -> bool:
    return inspect.isclass(tp) and issubclass(tp, pydantic.RootModel) and tp is not pydantic.RootModel


def _contains_root_model(annotation: object) -> bool:
    """True if the annotation is a RootModel or wraps one (Optional/list/union)."""
    if _is_root_model(annotation):
        return True
    return any(_contains_root_model(arg) for arg in typing.get_args(annotation))


def root_model_field_names() -> set[str]:
    """Field names across the adcp SDK and our schemas whose type wraps a RootModel."""
    names: set[str] = set()
    roots = []
    import adcp

    roots.append(adcp)
    try:
        import src.core.schemas as schemas

        roots.append(schemas)
    except Exception:  # pragma: no cover - schemas import is best-effort
        pass

    modules = []
    for root in roots:
        modules.append(root)
        if hasattr(root, "__path__"):
            for info in pkgutil.walk_packages(root.__path__, root.__name__ + "."):
                try:
                    modules.append(importlib.import_module(info.name))
                except Exception:
                    continue

    for module in modules:
        for obj in vars(module).values():
            if not (inspect.isclass(obj) and issubclass(obj, pydantic.BaseModel)):
                continue
            if _is_root_model(obj):
                continue
            try:
                fields = obj.model_fields
            except Exception:
                continue
            for field_name, field in fields.items():
                if _contains_root_model(field.annotation):
                    names.add(field_name)
    return names


def _terminal_attr(node: ast.AST) -> str | None:
    """Terminal attribute name of an expression, e.g. req.brand.brand_id -> brand_id."""
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


_DIAGNOSTIC_CALLS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "print"}


def _is_diagnostic_context(stack: list[ast.AST]) -> bool:
    """True when the string is only ever shown to a human (log line, exception text).

    A mangled ``root='x'`` in a log message is cosmetic — it is never read back. The
    defect only bites when the string is PERSISTED or returned on the wire, so this
    split is what separates a real candidate from a name collision that would render
    ugly at worst.
    """
    for parent in stack:
        if isinstance(parent, ast.Call):
            func = parent.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in _DIAGNOSTIC_CALLS:
                return True
            # Exception construction: raise ValueError(f"... {x} ...")
            if isinstance(func, ast.Name) and func.id.endswith(("Error", "Exception")):
                return True
        if isinstance(parent, ast.Raise):
            return True
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, field_names: set[str]) -> None:
        self.path = path
        self.field_names = field_names
        self.hits: list[dict[str, object]] = []
        self._stack: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        self._stack.append(node)
        super().generic_visit(node)
        self._stack.pop()

    def _record(self, node: ast.AST, expr: ast.AST, form: str) -> None:
        attr = _terminal_attr(expr)
        if attr in self.field_names:
            self.hits.append(
                {
                    "file": str(self.path.relative_to(REPO_ROOT)),
                    "line": node.lineno,
                    "attr": attr,
                    "form": form,
                    "context": "diagnostic" if _is_diagnostic_context(self._stack) else "value",
                    "source": ast.unparse(node)[:120],
                }
            )

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                self._record(node, value.value, "f-string")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "str" and node.args:
            self._record(node, node.args[0], "str()")
        if isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            for arg in node.args:
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Attribute):
                        self._record(node, sub, "join()")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Add):
            for side in (node.left, node.right):
                self._record(node, side, "concat")
        elif isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant):
            for sub in ast.walk(node.right):
                if isinstance(sub, ast.Attribute):
                    self._record(node, sub, "%-format")
        self.generic_visit(node)


def scan(field_names: set[str]) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        visitor = _Visitor(path, field_names)
        visitor.visit(tree)
        hits.extend(visitor.hits)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    field_names = root_model_field_names()
    hits = scan(field_names)

    if args.json:
        json.dump({"field_names": sorted(field_names), "hits": hits}, sys.stdout, indent=2)
        print()
        return 0

    values = [h for h in hits if h["context"] == "value"]
    diagnostics = [h for h in hits if h["context"] == "diagnostic"]

    print(f"RootModel-typed field names considered: {len(field_names)}")
    print(f"Stringification sites found in src/: {len(hits)}")
    print(f"  value context (persisted / returned / derived key): {len(values)}")
    print(f"  diagnostic context (log line, exception text): {len(diagnostics)}")
    print()
    for hit in values:
        print(f"  VALUE      {hit['file']}:{hit['line']}  [{hit['form']}] .{hit['attr']}  {hit['source']}")
    for hit in diagnostics:
        print(f"  DIAGNOSTIC {hit['file']}:{hit['line']}  [{hit['form']}] .{hit['attr']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

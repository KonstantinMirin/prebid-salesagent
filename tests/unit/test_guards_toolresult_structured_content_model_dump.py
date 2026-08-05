"""Guard: MCP ``ToolResult(structured_content=...)`` must never pass a raw model.

Regression guard for GH #1710: FastMCP's ``ToolResult.__init__``
(``fastmcp/tools/base.py``) always serializes non-dict ``structured_content`` via
``pydantic_core.to_jsonable_python()`` when the value isn't already a plain dict. That
serialization path BYPASSES:

- our ``model_dump()`` overrides (Pattern #4 nested serialization -- e.g.
  ``SyncCreativesResponse.model_dump()``'s per-creative child dump), and
- ``adcp.types.base.AdCPBaseModel.model_dump()``'s ``exclude_none=True`` default,
  which A2A/REST get for free via ``response.model_dump(mode="json")``.

The result: spec-optional fields left unset (e.g. per-creative ``status``,
``adcp_version``) silently serialize as invalid wire ``null`` on MCP ONLY --
byte-different from A2A/REST for the identical response object, and invalid
against the pinned response schema (typed fields don't accept ``null``).

Fix pattern (already correct at ``src/core/tools/products.py`` before this bug was
found, and now applied at all 14 call sites): always pass
``response.model_dump(mode="json")`` -- a plain dict -- as ``structured_content``,
never the raw model.

Rule: every ``ToolResult(...)`` call in ``src/`` whose ``structured_content=``
keyword argument is a bare name/attribute (not a ``.model_dump(...)`` call, not a
dict literal, not ``None``) is a violation.

Ships with ZERO violations; no allowlist (repo hard rule: allowlists never grow).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return None


def _is_raw_model_structured_content(node: ast.expr) -> bool:
    """True if *node* looks like a raw model/value rather than a serialized dict.

    Safe (not a violation): ``None``, a dict literal (``{...}``), a
    ``.model_dump(...)`` call (however it's chained, e.g.
    ``response.model_dump(mode="json")``), or any other method call (assumed to
    already return a dict, e.g. a local helper) -- this guard specifically targets
    the bare-identifier/attribute case that a raw pydantic model takes.
    """
    if isinstance(node, ast.Constant) and node.value is None:
        return False
    if isinstance(node, ast.Dict):
        return False
    if isinstance(node, ast.Call):
        # Any call result is treated as already-serialized (e.g. .model_dump(...),
        # a local dict-building helper). Only bare names/attributes are flagged.
        return False
    if isinstance(node, ast.Name | ast.Attribute):
        return True
    return False


def find_raw_structured_content_calls(src_files: dict[str, ast.AST]) -> list[str]:
    """``file:line`` for every ``ToolResult(structured_content=<raw model>)`` call."""
    offenders: list[str] = []
    for path, tree in sorted(src_files.items()):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if name != "ToolResult":
                continue
            for kw in node.keywords:
                if kw.arg == "structured_content" and _is_raw_model_structured_content(kw.value):
                    offenders.append(f"{path}:{node.lineno}")
    return offenders


def test_no_toolresult_structured_content_raw_model():
    src_files = {str(p.relative_to(REPO_ROOT)): t for p in sorted(SRC_ROOT.rglob("*.py")) if (t := _parse(p))}
    violations = find_raw_structured_content_calls(src_files)
    assert not violations, (
        "ToolResult(structured_content=<raw model>) bypasses model_dump() overrides "
        "and AdCPBaseModel's exclude_none default (GH #1710) -- "
        'pass response.model_dump(mode="json") instead. Violations:\n  ' + "\n  ".join(violations)
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────


def _detect(src_snippets: dict[str, str]) -> list[str]:
    return find_raw_structured_content_calls({k: ast.parse(v) for k, v in src_snippets.items()})


class TestGuardDetector:
    def test_positive_bare_name(self):
        assert _detect({"src/t.py": "ToolResult(content=str(response), structured_content=response)"})

    def test_positive_bare_attribute(self):
        assert _detect({"src/t.py": "ToolResult(content=str(r.response), structured_content=r.response)"})

    def test_negative_model_dump_call(self):
        assert not _detect(
            {"src/t.py": 'ToolResult(content=str(response), structured_content=response.model_dump(mode="json"))'}
        )

    def test_negative_none(self):
        assert not _detect({"src/t.py": "ToolResult(content=str(response), structured_content=None)"})

    def test_negative_dict_literal(self):
        assert not _detect({"src/t.py": 'ToolResult(content="ok", structured_content={"a": 1})'})

    def test_negative_unrelated_call(self):
        # A differently-named call is not ToolResult and must not be flagged.
        assert not _detect({"src/t.py": "SomethingElse(content=str(response), structured_content=response)"})

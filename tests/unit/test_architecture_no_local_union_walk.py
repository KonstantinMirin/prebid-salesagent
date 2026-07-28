#!/usr/bin/env python3
"""Structural guard: test code must not re-implement the union walk locally.

A type-introspection helper that resolves unions by ``origin is typing.Union`` alone is blind to
the PEP 604 ``X | None`` spelling this codebase writes everywhere (``get_origin`` returns
``types.UnionType`` for it). Such a helper does not raise — it silently stops resolving, and every
membership check downstream ("does this accept an array?", "is this a bare scalar?") answers no
for every annotation. The guard built on it then passes without grading anything, which is worse
than having no guard, because it advertises coverage.

This is not a hypothetical failure mode. The identical defect was written **twice inside one
file** (``tests/unit/test_mcp_tool_type_alignment.py``: first in ``_scalar_leaves``, then in
``normalize_type``), and both times it was found by mutation testing rather than by review —
the second one only after it had been green for its whole lifetime. Four near-identical union
walkers existed across three files.

So the rule is not "handle both spellings" (unenforceable, and the second copy proved review does
not catch it) but "do not write the walk at all": use ``tests.helpers.type_introspection``, which
is meta-tested in one place. Callers keep their own return contracts — only the walk is shared.

Allowlist may only shrink. It currently holds exactly the shared helper and this guard's own
fixtures.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.architecture

TESTS_ROOT = pathlib.Path(__file__).resolve().parents[1]

# The ONLY module allowed to name the union internals: the shared primitive itself.
# This allowlist may only shrink. Adding an entry means re-introducing the disease.
ALLOWLIST = {
    "helpers/type_introspection.py",
}

_UNION_NAMES = {"Union", "UnionType"}


def _is_union_ref(node: ast.expr) -> bool:
    """True when the node names ``typing.Union`` / ``types.UnionType`` (dotted or bare)."""
    if isinstance(node, ast.Attribute):
        return node.attr in _UNION_NAMES
    if isinstance(node, ast.Name):
        return node.id in _UNION_NAMES
    return False


def find_local_union_walks(source: str) -> list[tuple[int, str]]:
    """Return (lineno, form) for every local union-spelling check in ``source``.

    Two forms, because a walker can be written either way and the regression looks the same:
      - ``<expr> is typing.Union`` / ``is types.UnionType`` (and ``==`` variants)
      - ``isinstance(<expr>, types.UnionType)``
    """
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.Is | ast.Eq) for op in node.ops):
            for comparator in node.comparators:
                if _is_union_ref(comparator):
                    hits.append((node.lineno, ast.unparse(node)))
                    break
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) == 2
            and _is_union_ref(node.args[1])
        ):
            hits.append((node.lineno, ast.unparse(node)))

    return hits


class TestNoLocalUnionWalk:
    def test_no_test_module_reimplements_the_union_walk(self):
        violations: list[str] = []

        for path in sorted(TESTS_ROOT.rglob("*.py")):
            rel = path.relative_to(TESTS_ROOT).as_posix()
            if rel in ALLOWLIST or rel == pathlib.Path(__file__).name or "__pycache__" in rel:
                continue
            try:
                hits = find_local_union_walks(path.read_text())
            except SyntaxError:
                continue
            violations.extend(f"tests/{rel}:{lineno}  {form}" for lineno, form in hits)

        assert not violations, (
            "Union-spelling checks written locally instead of using "
            "tests.helpers.type_introspection.union_args:\n  "
            + "\n  ".join(violations)
            + "\n\nA walker that matches only one spelling stops resolving instead of failing, "
            "and the guard built on it passes while grading nothing. Use union_args()."
        )

    def test_allowlist_entries_still_exist(self):
        """A stale allowlist entry silently widens the guard — the ratchet must stay honest."""
        missing = [entry for entry in ALLOWLIST if not (TESTS_ROOT / entry).exists()]
        assert not missing, f"Allowlisted paths no longer exist; remove them from ALLOWLIST: {missing}"


class TestDetectorMetaTests:
    """The detector must catch every spelling a real walker uses — including the ones it almost missed."""

    def test_flags_typing_union_identity_check(self):
        src = "import typing\ndef walk(h):\n    if typing.get_origin(h) is typing.Union:\n        return 1\n"
        assert [line for line, _ in find_local_union_walks(src)] == [3]

    def test_flags_bare_imported_union_name(self):
        """``from typing import Union`` drops the dotted prefix — an attribute-only match misses it."""
        src = "from typing import Union, get_origin\ndef walk(h):\n    if get_origin(h) is Union:\n        return 1\n"
        assert [line for line, _ in find_local_union_walks(src)] == [3]

    def test_flags_isinstance_uniontype_spelling(self):
        """The other real spelling: the two sibling walkers were written this way, not with `is`."""
        src = "import types\ndef walk(h):\n    if isinstance(h, types.UnionType):\n        return 1\n"
        assert [line for line, _ in find_local_union_walks(src)] == [3]

    def test_flags_dunder_origin_access(self):
        """``annotation.__origin__ is typing.Union`` bypasses get_origin — same walk, same blindness."""
        src = "import typing\ndef walk(h):\n    if getattr(h, '__origin__', None) is typing.Union:\n        return 1\n"
        assert [line for line, _ in find_local_union_walks(src)] == [3]

    def test_flags_equality_variant(self):
        """``==`` instead of ``is`` is the same check; anchoring on `is` alone would miss it."""
        src = "import typing\ndef walk(h):\n    if typing.get_origin(h) == typing.Union:\n        return 1\n"
        assert [line for line, _ in find_local_union_walks(src)] == [3]

    def test_does_not_flag_the_shared_primitive_usage(self):
        """Negative case: the sanctioned form must stay clean, or the guard is unusable."""
        src = (
            "from tests.helpers import union_args\n"
            "def walk(h):\n"
            "    if members := union_args(h):\n"
            "        return members\n"
            "    return ()\n"
        )
        assert find_local_union_walks(src) == []

    def test_does_not_flag_union_used_as_a_type_value(self):
        """Negative case: passing ``typing.Union[str, int]`` as data is not a walk."""
        src = "import typing\nfrom tests.helpers import union_args\ndef t():\n    assert union_args(typing.Union[str, int])\n"
        assert find_local_union_walks(src) == []

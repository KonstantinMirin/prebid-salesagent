"""Guard: one canonical FormatId -> (width, height) derivation (#1600).

The creative-size bug class was N local re-derivations of the same logical
operation: read the typed ``width``/``height`` if present, else scan the
id for a ``WxH`` token. Written by hand at each consumer they drifted
observably — ``gam_inventory_service`` consulted the typed dimensions and
required both sides numeric, ``dynamic_pricing_service`` consulted only the
id and accepted any token containing an ``x`` (so ``display_boxad`` yielded
the pseudo-size ``"boxad"``), and the Flask suggest route ran a bare
``int(size.split("x"))`` that raised on ``?sizes=300xfoo``. Same FormatId,
three different answers.

The fix put the whole derivation in ``src/core/helpers/creative_helpers.py``
(``format_id_creative_size`` + its ``parse_size_token`` primitive) and
migrated every consumer onto it. This guard keeps it that way: production
code must not split a ``WxH`` token or decompose a format id by hand again.

This duplication is SEMANTIC, not textual — pylint R0801 and the
``.duplication-baseline`` cannot grade it, so this AST scan is the only
durable ratchet.
"""

import ast
from pathlib import Path

import pytest

from tests.unit._architecture_helpers import iter_call_expressions

_SRC = Path(__file__).parent.parent.parent / "src"

#: Files allowed to derive a creative size locally (the definition site only).
ALLOWLIST: set[str] = {"src/core/helpers/creative_helpers.py"}

#: str methods that split a "WxH" token apart.
_TOKEN_METHODS = ("split", "rsplit", "partition", "rpartition")


def _literal_str_arg(call: ast.Call) -> str | None:
    """The first argument of a call when it is a string literal, else None."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _size_token_splits(tree: ast.AST) -> list[int]:
    """Line numbers of hand-rolled ``WxH`` token splits (``"300x250"`` -> 300, 250)."""
    lines: list[int] = []
    for method in _TOKEN_METHODS:
        for call in iter_call_expressions(tree, method):
            literal = _literal_str_arg(call)
            if literal is not None and literal.lower() == "x":
                lines.append(call.lineno)
    return sorted(lines)


def _format_id_decompositions(tree: ast.AST) -> list[int]:
    """Line numbers of ``<expr>.id.split("_")`` — local format-id decomposition."""
    lines: list[int] = []
    for call in iter_call_expressions(tree, "split"):
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Attribute) or func.value.attr != "id":
            continue
        if _literal_str_arg(call) == "_":
            lines.append(call.lineno)
    return sorted(lines)


def _violations(tree: ast.AST) -> list[int]:
    return sorted(_size_token_splits(tree) + _format_id_decompositions(tree))


class TestSingleCreativeSizeDerivation:
    @pytest.mark.arch_guard
    def test_no_local_creative_size_derivation_in_production_code(self):
        violations: list[str] = []
        for path in sorted(_SRC.rglob("*.py")):
            rel = str(path.relative_to(_SRC.parent))
            if rel in ALLOWLIST:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
                continue
            violations += [f"{rel}:{lineno}" for lineno in _violations(tree)]
        assert not violations, (
            "creative size derived locally — a FormatId's (width, height) has exactly one "
            "derivation, format_id_creative_size() in src/core/helpers/creative_helpers.py, "
            "and a bare 'WxH' token has exactly one parser, parse_size_token():\n  " + "\n  ".join(violations)
        )

    @pytest.mark.arch_guard
    def test_guard_detects_planted_token_split(self):
        """Positive meta-test: the unguarded int(split) removed from the Flask route."""
        tree = ast.parse('width, height = size.split("x")\nparsed.append(int(width))\n')
        assert _violations(tree) == [1]

    @pytest.mark.arch_guard
    def test_guard_detects_planted_partition(self):
        """Positive meta-test: the partition form removed from gam_inventory_service."""
        tree = ast.parse('width_str, _, height_str = parts[1].partition("x")\n')
        assert _violations(tree) == [1]

    @pytest.mark.arch_guard
    def test_guard_detects_planted_format_id_decomposition(self):
        """Positive meta-test: the id scan removed from dynamic_pricing_service."""
        tree = ast.parse('parts = format_id.id.split("_")\n')
        assert _violations(tree) == [1]

    @pytest.mark.arch_guard
    def test_guard_ignores_canonical_helper_calls(self):
        """Negative meta-test: the migrated form is clean."""
        tree = ast.parse(
            "from src.core.helpers.creative_helpers import format_id_creative_size, parse_size_token\n"
            "size = format_id_creative_size(fmt)\n"
            "other = parse_size_token(token)\n"
        )
        assert _violations(tree) == []

    @pytest.mark.arch_guard
    def test_guard_ignores_unrelated_splits(self):
        """Negative meta-test: non-size string splitting is none of this guard's business."""
        tree = ast.parse('parts = strategy_id.split("_")\nhost, _, port = netloc.partition(":")\n')
        assert _violations(tree) == []

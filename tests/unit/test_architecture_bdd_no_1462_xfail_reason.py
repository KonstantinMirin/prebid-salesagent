"""Guard: BDD strict-xfail markers must not attribute their failure to #1462.

#1462 reported that the ``get_media_buy_delivery`` request path dropped
``attribution_window.post_click`` before validation could run. Re-derived
against main on 2026-07-27: it never reproduced, on any transport. Every
transport builds its request through the one shared
``_build_get_media_buy_delivery_request``, which preserves ``post_click``, and
a direct in-process probe confirms ``_validate_attribution_window`` rejects
``{"interval": 2, "unit": "campaign"}`` as it should.

The reported symptom was manufactured in the BDD step layer: the generic
``with {request_params}`` step matched the specific attribution step's text and
``_parse_request_params`` harvested only ``key=value`` pairs, so the space-form
window yielded ``{}`` and the request dispatched with NO attribution_window at
all. Production then echoed ``post_click=None, model=last_touch`` — the
signature of "the field never arrived", not "post_click was stripped". #1545
narrowed that step to the ``\\w+=`` form, so the cause is dead everywhere.

So a ``reason=`` string blaming #1462 is always wrong, and not merely because
BDD skips the IMPL transport: it names a request-path defect that never existed.
Do not replace it with the step-shadowing attribution either — that cause is
also dead. Find what the failing transport actually exercises today.

Scanning approach: AST — find ``pytest.mark.xfail(...)`` calls under
``tests/bdd/`` and assert no ``reason=`` string contains "1462". (Clarifying
*comments* that mention #1462 to explain the history are fine — only the marker
reason strings are scanned.)

GH: #1462 (the disproven attribution), #1545 (the step-binding fix that made it
unreproducible)
"""

from __future__ import annotations

import ast
from pathlib import Path

_BDD_DIR = Path(__file__).resolve().parents[1] / "bdd"


def _string_parts(node: ast.AST) -> list[str]:
    """Collect every string literal in an expression subtree.

    Handles a plain ``Constant``, implicit adjacent concatenation (already one
    Constant after parse), explicit ``a + b`` concatenation (BinOp), and
    f-strings (JoinedStr) — so a reason split across several lines cannot slip
    the check.
    """
    parts: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            parts.append(child.value)
    return parts


def _is_xfail_call(node: ast.Call) -> bool:
    """True if ``node`` is a ``pytest.mark.xfail(...)`` (or bare ``xfail(...)``) call."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "xfail"
    return isinstance(func, ast.Name) and func.id == "xfail"


def _find_1462_reasons(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, reason) for every xfail reason string mentioning 1462."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_xfail_call(node)):
            continue
        for kw in node.keywords:
            if kw.arg != "reason":
                continue
            reason = "".join(_string_parts(kw.value))
            if "1462" in reason:
                hits.append((node.lineno, reason))
    return hits


def test_no_bdd_xfail_reason_attributes_to_1462() -> None:
    """No BDD strict-xfail reason may blame #1462 (a defect that never reproduced)."""
    violations: list[str] = []
    for path in sorted(_BDD_DIR.rglob("*.py")):
        for lineno, reason in _find_1462_reasons(path):
            rel = path.relative_to(_BDD_DIR.parents[1])
            violations.append(f"{rel}:{lineno}: xfail reason blames #1462 -> {reason!r}")
    assert not violations, (
        "BDD xfail markers must not attribute failures to #1462. It reported a request "
        "path that drops attribution_window.post_click; re-derived 2026-07-27, that never "
        "reproduced on any transport — all transports share "
        "_build_get_media_buy_delivery_request, which preserves it. Do not swap in the "
        "generic-step-shadowing attribution either: #1545 narrowed that step, so the cause "
        "is dead too. Identify what the failing transport actually exercises today. "
        "Violations:\n" + "\n".join(violations)
    )


# ── Meta-tests (the guard catches the disease, and tolerates the corrected form) ──


def _scan_source(src: str) -> list[tuple[int, str]]:
    tree = ast.parse(src)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_xfail_call(node):
            for kw in node.keywords:
                if kw.arg == "reason" and "1462" in "".join(_string_parts(kw.value)):
                    hits.append((node.lineno, "".join(_string_parts(kw.value))))
    return hits


def test_meta_positive_catches_1462_reason() -> None:
    """Positive: a #1462-attributed xfail reason is flagged."""
    src = 'import pytest\npytest.mark.xfail(reason="window dropped (#1462)", strict=True)\n'
    assert _scan_source(src), "guard must flag a #1462 xfail reason"


def test_meta_positive_catches_multiline_concatenated_reason() -> None:
    """Positive (would-be-missed): a reason split across implicit-concatenated parts."""
    src = (
        "import pytest\n"
        "pytest.mark.xfail(\n"
        '    reason="attribution_window: validation can\'t fire — "\n'
        '    "request path drops post_click (#1462)",\n'
        "    strict=True,\n"
        ")\n"
    )
    assert _scan_source(src), "guard must flag a #1462 reason even when concatenated across lines"


def test_meta_negative_allows_corrected_reason() -> None:
    """Negative: a reason naming a live, transport-specific cause is NOT flagged."""
    src = (
        'import pytest\npytest.mark.xfail(reason="e2e_rest: seller attribution default not implemented", strict=True)\n'
    )
    assert not _scan_source(src), "guard must tolerate a non-#1462 reason"


def test_meta_negative_ignores_1462_in_comments() -> None:
    """Negative: #1462 in a comment (not a reason string) is fine."""
    src = (
        "import pytest\n"
        "# #1462 alleged a request-path drop; it never reproduced (see module docstring)\n"
        'pytest.mark.xfail(reason="e2e_rest: seller attribution default not implemented", strict=True)\n'
    )
    assert not _scan_source(src), "guard must scan reason strings only, not comments"

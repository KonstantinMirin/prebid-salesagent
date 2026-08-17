"""Guard: an untyped/caught exception's own text must never become a
buyer-facing message verbatim (prkv.8).

Disease, two shapes, both fixed by prkv.8:

1. ``AdCPError(str(exc))`` — the bare base class (not a typed subclass)
   constructed directly from an exception's ``str()``. Typed subclasses
   (``AdCPValidationError(...)``, etc.) carry their OWN deliberately-authored,
   safe message text; only the generic untyped-exception fallback in
   ``normalize_to_adcp_error()`` legitimately needs the bare base class, and
   it must use ``type(exc).__name__``, never ``str(exc)`` — the exception's
   text has no provenance guarantee (AdCP 3.1.1 transport-errors.mdx Security
   Considerations MUST-NOT list: credentials, SQL, hostnames, stack traces,
   upstream responses).

2. ``InternalError(message=f"...{exc}...")`` (or any A2A JSON-RPC error
   constructor) — an f-string interpolating a bare caught-exception variable
   directly into the wire ``message`` field. ``_internal_error_for()``'s
   original bug: ``message=f"{operation} failed: {exc}"``. The fix reuses
   ``normalize_to_adcp_error(exc).message`` (already safe by construction)
   instead of re-deriving from ``exc`` directly.

Scope: transport-boundary modules where these constructors are actually
called (adding NEW files here means auditing them first, not silently
narrowing coverage).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCOPE = (
    REPO_ROOT / "src" / "core" / "exceptions.py",
    REPO_ROOT / "src" / "a2a_server" / "adcp_a2a_server.py",
    REPO_ROOT / "src" / "app.py",
)

# (file, lineno) pairs permitted to violate — shrink-only.
ALLOWLIST: set[tuple[str, int]] = set()

_A2A_ERROR_CTORS = {"InternalError", "InvalidParamsError", "InvalidRequestError", "TaskNotFoundError"}

#: This codebase's consistent naming for a caught exception variable (verified
#: against every ``except ... as <name>`` site feeding these constructors).
#: Narrows both checks to actual exception interpolation — ``operation``,
#: ``task_id``, and other legitimate bare-Name f-string slots (buyer-supplied
#: request data, safe to echo) are not exception variables and must not trip
#: the guard.
_EXC_VAR_NAMES = {"exc", "e", "error"}


def _contains_str_of_exc_var(node: ast.AST) -> bool:
    """Walks *node* for a ``str(<exc-var>)`` call anywhere in the subtree —
    catches both the bare ``AdCPError(str(exc))`` shape and the historical
    ``AdCPError(str(exc) or type(exc).__name__)`` shape (str() nested inside
    a BoolOp, not the argument's top-level node)."""
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "str"
            and len(sub.args) == 1
            and isinstance(sub.args[0], ast.Name)
            and sub.args[0].id in _EXC_VAR_NAMES
        ):
            return True
    return False


def _bare_adcperror_from_str(node: ast.Call) -> bool:
    """``AdCPError(str(exc), ...)`` — the bare base class built from ``str()``
    of a caught exception, anywhere in the message argument's expression."""
    if not (isinstance(node.func, ast.Name) and node.func.id == "AdCPError"):
        return False
    if node.args and _contains_str_of_exc_var(node.args[0]):
        return True
    return any(kw.arg == "message" and _contains_str_of_exc_var(kw.value) for kw in node.keywords)


def _fstring_interpolates_exc_var(value: ast.AST) -> bool:
    """An f-string (``JoinedStr``) with a ``{exc}``-shaped slot: a bare Name
    matching the exception-variable convention, not narrowed by ``.attr``/
    call/subscript. ``normalize_to_adcp_error(exc).message`` is an Attribute
    access on a DIFFERENT name (``typed``), so the safe replacement pattern
    never matches this."""
    if not isinstance(value, ast.JoinedStr):
        return False
    return any(
        isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name) and part.value.id in _EXC_VAR_NAMES
        for part in value.values
    )


def _a2a_ctor_with_raw_message(node: ast.Call) -> bool:
    if not (isinstance(node.func, ast.Name) and node.func.id in _A2A_ERROR_CTORS):
        return False
    for kw in node.keywords:
        if kw.arg == "message" and _fstring_interpolates_exc_var(kw.value):
            return True
    return False


def _scan_source_text(rel: str, text: str) -> list[tuple[str, str, int]]:
    hits: list[tuple[str, str, int]] = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        if _bare_adcperror_from_str(node):
            hits.append((rel, "AdCPError(str(...))", node.lineno))
        elif _a2a_ctor_with_raw_message(node):
            func_name = node.func.id if isinstance(node.func, ast.Name) else "?"
            hits.append((rel, f"{func_name}(message=f'...{{name}}...')", node.lineno))
    return hits


def _scan() -> list[tuple[str, str, int]]:
    hits: list[tuple[str, str, int]] = []
    for path in _SCOPE:
        rel = str(path.relative_to(REPO_ROOT))
        hits.extend(_scan_source_text(rel, path.read_text()))
    return hits


class TestNoRawExceptionMessageGuard:
    def test_scope_files_exist(self):
        """The scope list must keep pointing at real files (guard not vacuous)."""
        assert all(p.is_file() for p in _SCOPE), [p for p in _SCOPE if not p.is_file()]

    def test_no_raw_exception_text_reaches_a_buyer_facing_constructor(self):
        violations = [v for v in _scan() if (v[0], v[2]) not in ALLOWLIST]
        assert not violations, (
            "An untyped/caught exception's own text is being used directly as a "
            "buyer-facing message (prkv.8 disease). Use type(exc).__name__ for the "
            "AdCPError generic fallback, or normalize_to_adcp_error(exc).message for "
            "an A2A JSON-RPC error's message= field:\n"
            + "\n".join(f"  {f}:{line} {form}" for f, form, line in violations)
        )

    def test_allowlist_entries_still_violate(self):
        actual = {(v[0], v[2]) for v in _scan()}
        stale = ALLOWLIST - actual
        assert not stale, f"Allowlist entries no longer violating — remove them: {sorted(stale)}"


class TestGuardMetaTests:
    def test_positive_detects_bare_adcperror_from_str(self):
        src = "return AdCPError(str(exc) or type(exc).__name__)\n"
        hits = _scan_source_text("x.py", src)
        assert [h[1] for h in hits] == ["AdCPError(str(...))"]

    def test_positive_detects_a2a_ctor_raw_interpolation(self):
        src = 'return InternalError(message=f"{operation} failed: {exc}", data={})\n'
        hits = _scan_source_text("x.py", src)
        assert [h[1] for h in hits] == ["InternalError(message=f'...{name}...')"]

    def test_negative_typed_subclass_with_own_message_passes(self):
        src = "return AdCPValidationError(str(exc))\n"
        assert _scan_source_text("x.py", src) == []

    def test_negative_type_name_fallback_passes(self):
        src = "return AdCPError(type(exc).__name__)\n"
        assert _scan_source_text("x.py", src) == []

    def test_negative_a2a_ctor_reusing_normalized_message_passes(self):
        src = (
            "typed = normalize_to_adcp_error(exc)\n"
            'return InternalError(message=f"{operation} failed: {typed.message}", data={})\n'
        )
        assert _scan_source_text("x.py", src) == []

    def test_str_of_exc_var_caught_even_when_nested(self):
        """str(exc) is caught anywhere in the message argument's subtree, not
        just when it IS the argument — e.g. nested inside an f-string or a
        BoolOp (the historical ``str(exc) or type(exc).__name__`` shape)."""
        src = 'return AdCPError(f"failed: {str(exc)}")\n'
        hits = _scan_source_text("x.py", src)
        assert [h[1] for h in hits] == ["AdCPError(str(...))"]

    def test_would_be_missed_nonstandard_exception_variable_name(self):
        """Known limitation: the guard anchors on this codebase's consistent
        exception-variable naming (exc/e/error, verified against every
        ``except ... as <name>`` site feeding these constructors at guard-
        authoring time). A caught exception bound to a different name evades
        both checks. Reviewers own this residual — renaming the variable to
        dodge the guard would be a deliberate, reviewable act, not a silent
        gap in normal code evolution."""
        src = "try:\n    pass\nexcept Exception as boom:\n    x = AdCPError(str(boom))\n"
        assert _scan_source_text("x.py", src) == []

"""Guard: a broad ``except`` must not relabel arbitrary failures as a *ValidationError.

Banned shape::

    except Exception as e:              # or bare `except:` / `except BaseException:`
        raise SomeValidationError(...)  # any name ending in "ValidationError"

A ``*ValidationError`` tells the caller **"your input violates the contract."**
A broad ``except`` catches implementation bugs — ``AttributeError``,
``TypeError``, a typo in an f-string — and this shape reports every one of them
as the caller's fault. The reader then hunts a contract violation that does not
exist, which is exactly the confusion #1843 was opened to eliminate.

The fix is never "log it too". It is to name the failure types that genuinely
mean the operation could not be performed, and let everything else propagate to
whatever handles internal errors at the boundary. #1868 did this for
``tests/helpers/adcp_schema_validator.py``: it now maps a fixed
``_INSTRUMENT_FAILURES`` tuple to ``SchemaError`` and has no ``except Exception``
arm at all.

NOT violations, deliberately:

- ``except Exception: raise ValueError(...)`` — ``ValueError`` is an internal
  Python signal, not a buyer-facing contract verdict.
- ``except Exception: raise AdCPAdapterError(...)`` (and
  ``AdCPServiceUnavailableError``, ``_internal_error_for``, ...) — these types
  already mean "something outside this code broke", which is the honest reading
  of an unexpected exception. Broad catch, correct label.
- ``except (SchemaError, KeyError): raise SomeValidationError(...)`` — a NAMED
  tuple is the fix, not the disease.

Sibling guard: ``test_architecture_no_silent_except.py`` bans the *swallow*
half (``except Exception: pass``) in ``src/``. This one bans the *mislabel*
half, tree-wide.

GH #1843, #1868
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import REPO_ROOT, assert_violations_match_allowlist, safe_parse

_SCAN_DIRS = ("src", "tests", "scripts")

_BROAD_NAMES = frozenset({"Exception", "BaseException"})

# Known violations — shrink-only, never grow. Keyed by (path, enclosing function,
# raised type) rather than line number: a fix elsewhere in the file shifts lines,
# and a line-keyed allowlist then reads as "fixed" when nothing changed.
# EMPTY, and it must stay empty. Both original entries (#1888 get_products
# property-list resolution, #1889 currency-code validation) were fixed by
# deleting the handlers, not by allowlisting them. An AST sweep of src/, tests/
# and scripts/ finds no other instance of this shape anywhere in the tree, so a
# new entry here would be a NEW defect, never inherited debt.
_KNOWN_VIOLATIONS: set[tuple[str, str, str]] = set()


def _is_broad_name(node: ast.expr) -> bool:
    """True for a reference to ``Exception``/``BaseException``, bare or dotted."""
    if isinstance(node, ast.Name):
        return node.id in _BROAD_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _BROAD_NAMES
    return False


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    """True for ``except:``, ``except Exception:``, ``except BaseException:``,
    and for any tuple containing one of those.

    A tuple whose members are all named, specific types is narrow and permitted.
    """
    node = handler.type
    if node is None:
        return True
    if isinstance(node, ast.Tuple):
        # A tuple CONTAINING Exception is exactly as broad as Exception alone —
        # the named siblings are already subsumed by it. Treating tuples as
        # narrow left "except (ValueError, Exception)" as a one-token way past
        # this guard. Measured when tightened: zero new violations tree-wide.
        return any(_is_broad_name(element) for element in node.elts)
    return _is_broad_name(node)


def _relabelled_validation_types(handler: ast.ExceptHandler) -> list[str]:
    """Names ending in "ValidationError" that this handler raises."""
    raised = []
    for node in ast.walk(handler):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
            continue
        func = node.exc.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if name.endswith("ValidationError"):
            raised.append(name)
    return raised


def _scan_tree(tree: ast.Module, rel_path: str) -> list[tuple[str, str, str]]:
    """Violations in one parsed module, as (path, enclosing function, raised type)."""
    violations: list[tuple[str, str, str]] = []

    def visit(node: ast.AST, enclosing: str) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            enclosing = node.name
        if isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            for raised in _relabelled_validation_types(node):
                violations.append((rel_path, enclosing, raised))
        for child in ast.iter_child_nodes(node):
            visit(child, enclosing)

    visit(tree, "<module>")
    return violations


def _scan_repo() -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for scan_dir in _SCAN_DIRS:
        root = REPO_ROOT / scan_dir
        if not root.exists():
            continue
        for py_file in sorted(root.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            tree = safe_parse(py_file)
            if tree is not None:
                found.update(_scan_tree(tree, str(py_file.relative_to(REPO_ROOT))))
    return found


@pytest.mark.arch_guard
def test_no_broad_except_relabels_as_validation_error():
    """No new broad-except-to-*ValidationError relabels anywhere in the tree."""
    new = _scan_repo() - _KNOWN_VIOLATIONS

    assert not new, (
        f"Found {len(new)} broad except handler(s) relabelling arbitrary failures as a "
        "*ValidationError — an implementation bug would reach the caller as 'your input "
        "violates the contract'.\n\n"
        + "\n".join(f"  {path}::{func} — except Exception -> raise {raised}" for path, func, raised in sorted(new))
        + "\n\nFix: name the failure types that genuinely mean the operation could not be "
        "performed, and delete the broad arm so anything else propagates. See "
        "tests/helpers/adcp_schema_validator.py::_INSTRUMENT_FAILURES."
    )


@pytest.mark.arch_guard
def test_known_violations_not_stale():
    """Every allowlisted violation must still exist — the allowlist only shrinks."""
    assert_violations_match_allowlist(
        _scan_repo(),
        _KNOWN_VIOLATIONS,
        fix_hint="_KNOWN_VIOLATIONS is empty and stays empty — delete the handler instead.",
    )


# ---------------------------------------------------------------------------
# Meta-tests: the guard must actually detect the disease, and must not fire on
# the shapes it deliberately permits. Sources are parsed from strings so the
# samples are not themselves scanned as repo files.
# ---------------------------------------------------------------------------

_POSITIVE_SAMPLES = {
    "bare-except": "try:\n    f()\nexcept:\n    raise MyValidationError('x')\n",
    "except-Exception": "try:\n    f()\nexcept Exception as e:\n    raise MyValidationError('x') from e\n",
    "except-BaseException": "try:\n    f()\nexcept BaseException:\n    raise AdCPValidationError('x')\n",
    "dotted-Exception": "try:\n    f()\nexcept builtins.Exception:\n    raise ValidationError('x')\n",
    "dotted-raise": "try:\n    f()\nexcept Exception:\n    raise mod.SchemaValidationError('x')\n",
    "raise-nested-in-if": "try:\n    f()\nexcept Exception as e:\n    if e:\n        raise MyValidationError('x')\n",
    "inside-async-def": "async def go():\n    try:\n        await f()\n    except Exception:\n        raise ValidationError('x')\n",
}

_NEGATIVE_SAMPLES = {
    # The fix shape: a named tuple, however many members.
    "named-tuple": "try:\n    f()\nexcept (SchemaError, KeyError) as e:\n    raise MyValidationError('x') from e\n",
    "single-named-type": "try:\n    f()\nexcept SchemaError:\n    raise ValidationError('x')\n",
    # Broad catch relabelled to a type that already means "something external broke".
    "adapter-error": "try:\n    f()\nexcept Exception as e:\n    raise AdCPAdapterError('x') from e\n",
    "value-error": "try:\n    f()\nexcept Exception as e:\n    raise ValueError('x') from e\n",
    # Broad catch that does not relabel at all.
    "bare-reraise": "try:\n    f()\nexcept Exception:\n    raise\n",
    "logged": "try:\n    f()\nexcept Exception as e:\n    logger.error(e)\n",
    # A *ValidationError raised OUTSIDE any handler is ordinary validation.
    "raise-outside-handler": "def check(v):\n    if not v:\n        raise MyValidationError('x')\n",
}


@pytest.mark.parametrize("sample", sorted(_POSITIVE_SAMPLES), ids=sorted(_POSITIVE_SAMPLES))
def test_guard_detects_disease(sample):
    """Each banned shape is detected — a guard that never fires guards nothing."""
    found = _scan_tree(ast.parse(_POSITIVE_SAMPLES[sample]), "sample.py")
    assert found, f"guard missed the {sample!r} form of the disease"


@pytest.mark.parametrize("sample", sorted(_NEGATIVE_SAMPLES), ids=sorted(_NEGATIVE_SAMPLES))
def test_guard_permits_correct_shapes(sample):
    """Each permitted shape is NOT reported — a guard that fires on everything is noise."""
    found = _scan_tree(ast.parse(_NEGATIVE_SAMPLES[sample]), "sample.py")
    assert not found, f"guard wrongly flagged the {sample!r} form: {found}"

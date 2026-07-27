"""Guard: a pure tripwire patch must target a REACHABLE symbol.

A *pure tripwire* is ``patch("<D>.<sym>", side_effect=<SomeError>(...))`` — a patch
whose entire contribution is to blow up if the code under test touches ``sym``. It
pins a negative ("this must not happen"), so the surrounding assertion is usually an
absence/fallback check that the ordinary happy path also satisfies.

That makes an unreachable tripwire silently vacuous. Python binds ``from D import sym``
into the *consumer* module's globals at import time, so a call inside module ``M`` that
did ``from D import sym`` resolves through ``M.sym`` and NEVER consults a patch applied
to ``D.sym``. The tripwire cannot fire, the absence assertion passes anyway, and the
test reports green while pinning nothing.

This is not hypothetical. ``tests/integration/test_delivery_webhook_scheduler_session.py``
patched the definition site while ``src/services/delivery_webhook_scheduler.py`` binds the
name at module level; reintroducing the exact regression it existed to catch left the test
GREEN (#1600). A whole-suite sweep found it to be the only instance — hence the empty
allowlist below.

Detection is deliberately narrowed to pure tripwires. A definition-site patch is
perfectly legitimate in general (a consumer using module-attribute access — ``mod.sym()``
— or a function-local import does see it), so flagging every such patch would be ~423
false positives. Restricting to tripwires is what makes unreachability *provably* fatal
rather than merely suspicious.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.unit._architecture_helpers import assert_violations_match_allowlist

pytestmark = [pytest.mark.architecture]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
TESTS = REPO_ROOT / "tests"

# Callables that, used as a ``side_effect``, make the patch a pure tripwire.
_RAISERS = {"AssertionError", "RuntimeError", "Exception", "ValueError", "TypeError", "fail"}

# INTENTIONALLY EMPTY. The scheduler tripwire (#1600) was the suite's only unreachable
# one, and it is fixed rather than allowlisted — so this guard carries zero debt.
#
# Do not add an entry to make a new violation pass. The fix is always to repoint the
# patch at the use site; an unreachable tripwire has no legitimate form.
#
# Note what this guard does NOT cover: a tripwire can also be vacuous while being
# perfectly reachable, when the surrounding assertion is satisfied by the happy path too
# (e.g. `assert result == []` where the unpatched path also yields []). That is a
# weak-assertion defect, not a binding defect, and it is invisible to static analysis —
# only a mutation run can settle it. Three such tests are tracked separately.
_ALLOWED: dict[tuple[str, str, str], str] = {}


def _from_import_binders(src_root: pathlib.Path) -> dict[tuple[str, str], set[str]]:
    """Map (defining_module, symbol) -> {modules that bind it at MODULE level}.

    Only a module-level ``from D import sym`` shadows: it runs once at import time and
    freezes the reference in the consumer's globals, so a later patch on ``D.sym`` is
    never consulted. A *function-local* ``from D import sym`` is the opposite — it
    re-executes on every call and therefore picks the patched object up. Counting
    function-local imports as binders produces false positives on tests that are
    demonstrably fine (verified against the ``pytest.raises(match=...)`` self-verifying
    tripwires in tests/unit/test_quiet_failure_propagation.py).
    """
    binders: dict[tuple[str, str], set[str]] = {}
    for path in src_root.rglob("*.py"):
        module = str(path.relative_to(src_root.parent).with_suffix("")).replace("/", ".")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        # Module level only — do NOT ast.walk() into function bodies.
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    # An aliased import is a different shape (the local name differs),
                    # so it cannot shadow a patch on "<module>.<original name>".
                    if alias.asname is None:
                        binders.setdefault((node.module, alias.name), set()).add(module)
    return binders


def _callable_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_raiser(value: ast.AST) -> bool:
    """True when a ``side_effect=`` value makes the patch a pure tripwire."""
    if isinstance(value, ast.Call):
        return _callable_name(value.func) in _RAISERS
    return _callable_name(value) in _RAISERS


def _imported_src_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src"):
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(a.name for a in node.names if a.name.startswith("src"))
    return modules


def find_shadowed_tripwires(
    tree: ast.AST,
    binders: dict[tuple[str, str], set[str]],
) -> list[tuple[int, str, list[str]]]:
    """Return (lineno, patch_target, shadowing_modules) for each unreachable tripwire."""
    test_modules = _imported_src_modules(tree)
    found: list[tuple[int, str, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _callable_name(node.func) != "patch" or not node.args:
            continue
        target = node.args[0]
        if not (isinstance(target, ast.Constant) and isinstance(target.value, str)):
            continue
        side_effects = [kw.value for kw in node.keywords if kw.arg == "side_effect"]
        if not side_effects or not _is_raiser(side_effects[0]):
            continue
        defining_module, _, symbol = target.value.rpartition(".")
        shadowing = binders.get((defining_module, symbol), set()) & test_modules
        if shadowing:
            found.append((node.lineno, target.value, sorted(shadowing)))
    return found


def _scan_suite() -> set[tuple[str, str, str]]:
    """(test file, patch target, shadowing modules) for every unreachable tripwire."""
    binders = _from_import_binders(SRC)
    found: set[tuple[str, str, str]] = set()
    for path in TESTS.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for _lineno, target, shadowing in find_shadowed_tripwires(tree, binders):
            found.add((rel, target, ", ".join(shadowing)))
    return found


def test_no_unreachable_tripwire_patches() -> None:
    """Every pure tripwire must be able to fire against the code under test.

    Both failure modes (a new unreachable tripwire, and a stale allowlist entry whose
    violation has since been fixed) are reported by the shared helper.
    """
    assert_violations_match_allowlist(
        _scan_suite(),
        set(_ALLOWED),
        fix_hint=(
            "A tripwire patched at the DEFINITION site cannot fire when the module under "
            "test binds that symbol at module level via `from ... import` — the call "
            "resolves through the consumer's own globals. Repoint the patch at the USE "
            "site (the module under test), then confirm the tripwire can fail: reintroduce "
            "the regression it pins and watch the test go red."
        ),
    )


# --- Meta-tests: prove the detector actually detects ---------------------------------

_BINDERS = {("src.pkg.defs", "helper"): {"src.pkg.consumer"}}

_KNOWN_BAD = """
from src.pkg.consumer import run
from unittest.mock import patch

def test_x():
    with patch("src.pkg.defs.helper", side_effect=AssertionError("must not be called")):
        run()
"""

_KNOWN_GOOD_USE_SITE = """
from src.pkg.consumer import run
from unittest.mock import patch

def test_x():
    with patch("src.pkg.consumer.helper", side_effect=AssertionError("must not be called")):
        run()
"""

_KNOWN_GOOD_NOT_A_TRIPWIRE = """
from src.pkg.consumer import run
from unittest.mock import patch

def test_x():
    with patch("src.pkg.defs.helper", return_value=3):
        run()
"""

_WOULD_BE_MISSED = """
from src.pkg.consumer import run
from unittest.mock import patch

def test_x():
    # Bare exception CLASS rather than an instantiated call, and patch reached as an
    # attribute (mock.patch) rather than a bare name.
    with mock.patch("src.pkg.defs.helper", side_effect=RuntimeError):
        run()
"""


def test_meta_detects_known_bad() -> None:
    found = find_shadowed_tripwires(ast.parse(_KNOWN_BAD), _BINDERS)
    assert [(t, s) for _, t, s in found] == [("src.pkg.defs.helper", ["src.pkg.consumer"])]


@pytest.mark.parametrize(
    "source",
    [_KNOWN_GOOD_USE_SITE, _KNOWN_GOOD_NOT_A_TRIPWIRE],
    ids=["patches-use-site", "not-a-tripwire"],
)
def test_meta_ignores_known_good(source: str) -> None:
    assert find_shadowed_tripwires(ast.parse(source), _BINDERS) == []


def test_meta_catches_would_be_missed_variants() -> None:
    """Bare exception class + attribute-style ``mock.patch`` must still be caught.

    Both are natural spellings a narrower detector (one requiring an instantiated
    ``side_effect=Err(...)`` call, or a bare ``patch`` name) would silently skip —
    which would blind the guard exactly where a real tripwire lives.
    """
    found = find_shadowed_tripwires(ast.parse(_WOULD_BE_MISSED), _BINDERS)
    assert [t for _, t, _ in found] == ["src.pkg.defs.helper"]


def test_meta_aliased_import_does_not_shadow() -> None:
    """``from D import sym as other`` rebinds under a different name, so a patch on
    ``D.sym`` is still the right target and must not be reported."""
    binders = _from_import_binders(SRC)
    assert ("src.core.database.database_session", "get_db_session") in binders

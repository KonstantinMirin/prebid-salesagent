"""Structural lock on the e2e shared-adapter-state baseline (salesagent-wkjc).

The e2e suite shares ONE live database. Its ci-test tenant's adapter
test-behavior (manual approval, fault injection) is mutable global state, and
pytest-randomly reorders tests every run, so whoever mutates it last decides how
the NEXT test's ``create_media_buy`` behaves (salesagent-d1n0).

The fix inverted the ownership: ``tests/e2e/conftest.py`` owns that state through
ONE autouse fixture that resets it to the default baseline on both sides of every
live-stack test. Tests opt INTO non-default behavior and never opt back out.

That invariant is structural, and it is graded only by a full Docker e2e run under
a hostile seed — far too slow and too rare to catch a regression at review time.
This guard is the fast surrogate. It fails when:

1. the autouse owner is removed, renamed, duplicated, or stops resetting on both
   sides of its yield (a setup-only reset leaves the last leaker's state behind);
2. the reset helper stops gating on ``live_server``, which would drag Docker into
   the hermetic e2e classes that request no fixtures at all;
3. a test body re-pins the baseline itself with
   ``set_live_adapter_behavior(..., manual_approval_required=False)`` — the
   hand-rolled per-victim pinning this change deleted, coming back.

Both detectors are exercised against known-bad synthetic sources below (including
a would-be-missed variant), so a detector regression cannot silently blind the
lock — repo precedent: tests/unit/test_architecture_e2e_rest_escape_hatches.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.unit._architecture_helpers import call_name, format_failure, iter_call_expressions

_REPO_ROOT = Path(__file__).resolve().parents[2]
_E2E_DIR = _REPO_ROOT / "tests" / "e2e"
_E2E_CONFTEST = _E2E_DIR / "conftest.py"
_E2E_UTILS = _E2E_DIR / "utils.py"

# The one owner and the plain function holding its live-stack gate.
BASELINE_FIXTURE = "adapter_state_baseline"
RESET_ENTRY_POINT = "reset_adapter_baseline_if_live"
RESET_HELPER = "reset_live_adapter_behavior"
BEHAVIOR_SETTER = "set_live_adapter_behavior"


# ---------------------------------------------------------------------------
# Detector 1: the autouse baseline owner in tests/e2e/conftest.py
# ---------------------------------------------------------------------------


def _is_autouse_fixture(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when *func* is decorated ``@pytest.fixture(autouse=True)``."""
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call) or call_name(dec) != "fixture":
            continue
        for kw in dec.keywords:
            if kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def find_autouse_baseline_fixtures(tree: ast.Module) -> dict[str, tuple[int, int]]:
    """Map each autouse fixture name to its (resets-before-yield, resets-after-yield) counts.

    A "reset" is a call to :data:`RESET_ENTRY_POINT`. Counting on each side of the
    ``yield`` is the point: a fixture that only resets on setup leaves the last
    leaker's state in the shared DB for whatever runs next.
    """
    found: dict[str, tuple[int, int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _is_autouse_fixture(node):
            continue
        yield_linenos = [n.lineno for n in ast.walk(node) if isinstance(n, (ast.Yield, ast.YieldFrom))]
        pivot = min(yield_linenos) if yield_linenos else None
        before = after = 0
        for call in iter_call_expressions(node, RESET_ENTRY_POINT):
            if pivot is not None and call.lineno > pivot:
                after += 1
            else:
                before += 1
        found[node.name] = (before, after)
    return found


def find_gated_reset_helpers(tree: ast.Module) -> set[str]:
    """Names of functions that gate on ``fixturenames`` AND reach the reset helper.

    Both halves matter. Without the ``fixturenames`` gate an autouse reset would
    request ``live_server`` for every e2e test, starting Docker for the hermetic
    wire-format classes. Without the reset call the gate guards nothing.
    """
    gated: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        gates = any(isinstance(sub, ast.Attribute) and sub.attr == "fixturenames" for sub in ast.walk(node))
        resets = any(call_name(call) == RESET_HELPER for call in iter_call_expressions(node))
        if gates and resets:
            gated.add(node.name)
    return gated


def test_exactly_one_autouse_baseline_owner_resetting_both_sides() -> None:
    """tests/e2e/conftest.py has ONE autouse fixture resetting on setup AND teardown."""
    fixtures = find_autouse_baseline_fixtures(ast.parse(_E2E_CONFTEST.read_text()))
    resetting = {name: counts for name, counts in fixtures.items() if sum(counts) > 0}

    assert list(resetting) == [BASELINE_FIXTURE], format_failure(
        summary=(
            "tests/e2e/conftest.py must define exactly ONE autouse fixture that resets "
            f"the shared adapter baseline, named {BASELINE_FIXTURE!r}."
        ),
        violations=[f"autouse fixtures calling {RESET_ENTRY_POINT}(): {sorted(resetting) or 'none'}"],
        fix_hint=(
            "Shared ci-test adapter state has exactly one owner. Do not add a second "
            "autouse resetter and do not delete this one — tests opt INTO non-default "
            "behavior only (salesagent-wkjc)."
        ),
    )

    before, after = resetting[BASELINE_FIXTURE]
    assert before >= 1 and after >= 1, format_failure(
        summary=f"{BASELINE_FIXTURE} must reset on BOTH sides of its yield.",
        violations=[f"{RESET_ENTRY_POINT}() calls: {before} before yield, {after} after yield"],
        fix_hint=(
            "Setup-only reset leaves the LAST leaker's manual-approval state in the shared "
            "DB for whatever touches the ci-test tenant next; teardown-only leaves a test "
            "exposed to a crashed predecessor."
        ),
    )


def test_reset_entry_point_gates_on_live_server() -> None:
    """The reset entry point early-returns unless the test requests ``live_server``."""
    gated = find_gated_reset_helpers(ast.parse(_E2E_UTILS.read_text()))
    assert RESET_ENTRY_POINT in gated, format_failure(
        summary=(
            f"tests/e2e/utils.py::{RESET_ENTRY_POINT} must gate on request.fixturenames and call {RESET_HELPER}()."
        ),
        violations=[f"gated reset helpers found: {sorted(gated) or 'none'}"],
        fix_hint=(
            "An UNCONDITIONAL reset would make the autouse fixture request live_server for "
            "every e2e test, starting Docker for the hermetic classes (TestProtocolWebhook"
            "WireFormat, test_schema_validation_standalone.py) that request no fixtures."
        ),
    )


# ---------------------------------------------------------------------------
# Detector 2: hand-rolled baseline re-pins in e2e test bodies
# ---------------------------------------------------------------------------


def find_baseline_repins(tree: ast.Module) -> list[int]:
    """Line numbers of ``set_live_adapter_behavior(..., manual_approval_required=False)``.

    Setting the flag to False IS the baseline the autouse fixture already
    guarantees, so every such call is a redundant per-test re-pin — the disease
    returning. Opt-INS (``manual_approval_required=True``) and fault injection are
    untouched: those are legitimate non-default behavior.
    """
    lines: list[int] = []
    for call in iter_call_expressions(tree, BEHAVIOR_SETTER):
        for kw in call.keywords:
            if kw.arg == "manual_approval_required" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                lines.append(call.lineno)
    return lines


def test_no_test_body_repins_the_baseline() -> None:
    """No module under tests/e2e/ re-pins the auto-approval baseline itself."""
    violations: list[str] = []
    for path in sorted(_E2E_DIR.rglob("*.py")):
        if path == _E2E_UTILS or "__pycache__" in str(path):
            continue
        for lineno in find_baseline_repins(ast.parse(path.read_text())):
            violations.append(
                f"{path.relative_to(_REPO_ROOT)}:{lineno}: {BEHAVIOR_SETTER}(manual_approval_required=False)"
            )

    assert not violations, format_failure(
        summary="e2e tests must not re-pin the adapter auto-approval baseline themselves.",
        violations=violations,
        fix_hint=(
            f"The autouse {BASELINE_FIXTURE} fixture already resets the ci-test tenant to "
            "auto-approval before and after every live-stack test. Delete the call; keep "
            "only explicit opt-INS (manual_approval_required=True)."
        ),
    )


# ---------------------------------------------------------------------------
# Meta-tests: the LIVE detectors catch known-bad sources (#1498 discipline)
# ---------------------------------------------------------------------------

_SYNTHETIC_CONFTEST_SETUP_ONLY = """
import pytest


@pytest.fixture(autouse=True)
def adapter_state_baseline(request):
    from tests.e2e.utils import reset_adapter_baseline_if_live

    reset_adapter_baseline_if_live(request)
    yield


@pytest.fixture(autouse=True)
def a_second_owner(request):
    from tests.e2e.utils import reset_adapter_baseline_if_live

    reset_adapter_baseline_if_live(request)
    yield
    reset_adapter_baseline_if_live(request)


@pytest.fixture(autouse=True)
def unrelated_autouse_fixture():
    yield
"""


def test_detector_reports_reset_sides_and_ignores_unrelated_autouse() -> None:
    """The live fixture detector counts resets per side and skips non-resetting fixtures."""
    found = find_autouse_baseline_fixtures(ast.parse(_SYNTHETIC_CONFTEST_SETUP_ONLY))
    assert found == {
        "adapter_state_baseline": (1, 0),
        "a_second_owner": (1, 1),
        "unrelated_autouse_fixture": (0, 0),
    }


_SYNTHETIC_CONFTEST_NON_AUTOUSE = """
import pytest


@pytest.fixture
def adapter_state_baseline(request):
    from tests.e2e.utils import reset_adapter_baseline_if_live

    reset_adapter_baseline_if_live(request)
    yield
    reset_adapter_baseline_if_live(request)
"""


def test_detector_catches_owner_downgraded_to_opt_in() -> None:
    """Dropping ``autouse=True`` (back to per-victim opt-in) makes the owner disappear."""
    assert find_autouse_baseline_fixtures(ast.parse(_SYNTHETIC_CONFTEST_NON_AUTOUSE)) == {}


_SYNTHETIC_UTILS_UNGATED = """
def reset_adapter_baseline_if_live(request):
    reset_live_adapter_behavior(request.getfixturevalue("live_server"))


def gate_without_reset(request):
    if "live_server" not in request.fixturenames:
        return
    print("noop")


def reset_without_gate(request, live_server):
    reset_live_adapter_behavior(live_server)
"""


def test_detector_catches_ungated_reset_helper() -> None:
    """A reset without the fixturenames gate — and a gate without a reset — both fail the check."""
    assert find_gated_reset_helpers(ast.parse(_SYNTHETIC_UTILS_UNGATED)) == set()


_SYNTHETIC_E2E_TEST = """
from tests.e2e.utils import set_live_adapter_behavior


class TestSomething:
    def test_repins_the_baseline(self, live_server):
        set_live_adapter_behavior(live_server, manual_approval_required=False)

    def test_legitimate_opt_in(self, live_server):
        set_live_adapter_behavior(live_server, manual_approval_required=True)

    def test_legitimate_fault_injection(self, live_server):
        set_live_adapter_behavior(live_server, fail_on_create=True)

    def test_repins_with_tenant_kwarg(self, live_server):
        set_live_adapter_behavior(
            live_server, tenant_subdomain="other", manual_approval_required=False
        )
"""


def test_detector_catches_repins_and_spares_opt_ins() -> None:
    """The live re-pin detector flags only the False pins, at any kwarg position."""
    linenos = find_baseline_repins(ast.parse(_SYNTHETIC_E2E_TEST))
    assert linenos == [7, 16]

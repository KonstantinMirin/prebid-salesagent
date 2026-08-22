"""Guard: BDD wire-discipline — error handling goes through the wire, not test-side.

Three complementary checks, locking in the universal-wire-dispatch invariant after the
holdouts were migrated:

A. **No test-side error construction** (dispatch-side). A step must NOT
   fabricate the expected error via ``ctx["error"] = SomethingError(...)``. Dispatch the
   malformed/invalid request through the wire so *production* emits the error; assert it via
   ``ctx['result'].assert_wire_error(...)``. (The complementary ``env.call_impl`` bypass is
   enforced by ``test_architecture_bdd_no_direct_call_impl.py`` /
   ``test_architecture_bdd_no_partial_account_call_impl.py`` — there are currently zero
   ``call_impl`` calls in ``tests/bdd/steps/`` after the dlh8/osrl/zh85 migrations.)

B. **No reconstructed-only error assertion** (assertion-side). An error
   ``@then`` step must not assert purely on the lossy reconstructed ``ctx['error']`` via
   ``_get_error_code`` / ``_get_error_dict`` without reading the real wire envelope
   (``_wire_code`` / ``_wire_suggestion`` / ``assert_wire_error`` / ``wire_error_envelope`` /
   ``ctx['result']``). Reconstruction collapses distinct wire codes onto one exception class
   (yields ``RuntimeError`` for an unmapped code); the wire envelope is the buyer-facing
   contract.

C. **No private circuit-breaker state reached from a step** (arrange/assert-side). A step must
   not touch ``<service>._circuit_breakers``. Breaker state is process-local, so a step indexing
   that dict is unfalsifiable across any process boundary (it grades a test double, not a
   delivery). Seeding goes through the harness env's breaker accessors — the one place allowed to
   touch the private dict — and every state READ an assertion depends on goes through the
   production public API ``WebhookDeliveryService.get_circuit_breaker_state``. Allowlist is
   permanently EMPTY.

All allowlists can only SHRINK. Each entry documents the production gap that keeps it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.unit._architecture_helpers import assert_violations_match_allowlist

_STEPS_DIR = Path(__file__).resolve().parents[1] / "bdd" / "steps"
_TESTS_ROOT = _STEPS_DIR.parent.parent

_WIRE_REFERENCES = (
    "_wire_code",
    "_wire_suggestion",
    "_wire_error_object",
    "assert_wire_error",
    "wire_error_envelope",
    # The reader pair that replaced the hand-rolled `wire or synthesized`
    # fallback. A step migrated onto it still references the wire — without
    # these names it would lose the marker and trip Check B.
    "error_envelope",
    "error_envelope_or_none",
)

# -- Check A: test-side error construction ------------------------------------
# Keyed by "<relative path> <enclosing func> <ErrorClass>" (NOT line numbers — those
# shift on unrelated edits). Each remaining entry is a 33r0-reclassified production gap.
_ERROR_CONSTRUCTION_ALLOWLIST: set[str] = {
    # Production gap: _SyntheticError wraps the REAL production per-creative error
    # string — production emits unstructured per-creative errors (no machine code). Remove
    # when sync_creatives emits structured per-creative codes.
    "bdd/steps/domain/uc006_sync_creatives.py _promote_creative_errors_to_ctx _SyntheticError",
    # (Retired) The null-date phantom (uc019 _create_media_buy_with_null_dates) is gone:
    # the scenario was retired (schema-impossible + not spec-graded) and resolve_canonical_status
    # now guards the null edge, so no test-side error construction remains here.
}

# -- Check B: reconstructed-only error assertions -----------------------------
_RECONSTRUCTED_ASSERTION_ALLOWLIST: set[str] = set()

# -- Check C: private circuit-breaker state in a step -------------------------
# The private attribute a step may never reach for. Matched as an AST ``Attribute``,
# never as a source token: a token scan also hits the DOCSTRING at
# ``uc004_delivery.py`` that *describes* the process-local limitation, which would make
# the zero allowlist unachievable and the guard unshippable (gra7.3 correction C3).
_PRIVATE_BREAKER_ATTR = "_circuit_breakers"

# ZERO entries, permanently. Every site migrates onto the harness env's breaker accessors
# in the same change that lands this check, so a baseline here would be allowlist growth.
# Keys carry line numbers (unlike checks A/B) precisely BECAUSE the allowlist is empty:
# nothing is ever stored, so nothing can go stale, and the failure names the exact sites.
_PRIVATE_BREAKER_ALLOWLIST: set[str] = set()


def _iter_step_modules() -> list[tuple[str, ast.Module]]:
    out = []
    for py_file in sorted(_STEPS_DIR.rglob("*.py")):
        if py_file.name.startswith("__"):
            continue
        rel = str(py_file.relative_to(_TESTS_ROOT))
        out.append((rel, ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))))
    return out


def _enclosing_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _own_nodes(func: ast.FunctionDef | ast.AsyncFunctionDef):
    """Yield nodes in ``func``'s body but NOT inside any nested function definition.

    Prevents attributing a construction in a nested helper to BOTH the helper and
    its enclosing function (which double-counts under a naive ``ast.walk``).
    """
    stack = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue  # a nested function owns its own nodes
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _is_then(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id == "then":
            return True
    return False


def _error_class_name(call: ast.Call) -> str | None:
    """Return the constructed class name if it ends in 'Error', else None."""
    fn = call.func
    name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
    return name if name and name.endswith("Error") else None


def _func_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """All identifiers/attributes referenced in the function body."""
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


def _find_error_construction() -> set[str]:
    """Find ``ctx["error"] = <X>Error(...)`` assignments in any step function."""
    found: set[str] = set()
    for rel, tree in _iter_step_modules():
        for func in _enclosing_functions(tree):
            for node in _own_nodes(func):
                if not isinstance(node, ast.Assign):
                    continue
                # target ctx["error"]
                if not any(
                    isinstance(t, ast.Subscript)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "ctx"
                    and isinstance(t.slice, ast.Constant)
                    and t.slice.value == "error"
                    for t in node.targets
                ):
                    continue
                if isinstance(node.value, ast.Call) and (cls := _error_class_name(node.value)):
                    found.add(f"{rel} {func.name} {cls}")
    return found


def _find_reconstructed_only_assertions() -> set[str]:
    """Find error @then steps using _get_error_code/_get_error_dict without a wire reference."""
    found: set[str] = set()
    for rel, tree in _iter_step_modules():
        # then_error.py DEFINES the helpers — its wire-first steps reference _wire_code; skip
        # the helper-definition file's own _get_* definitions by requiring a @then decorator.
        for func in _enclosing_functions(tree):
            if not _is_then(func):
                continue
            names = _func_names(func)
            uses_reconstructed = bool({"_get_error_code", "_get_error_dict"} & names)
            uses_wire = bool(set(_WIRE_REFERENCES) & names) or "result" in names
            if uses_reconstructed and not uses_wire:
                found.add(f"{rel} {func.name}")
    return found


def _private_breaker_hits(tree: ast.Module) -> dict[str, list[int]]:
    """Map enclosing function name -> sorted line numbers of ``x._circuit_breakers`` access.

    ``ast.Attribute`` only. A string mentioning ``_circuit_breakers`` — a docstring
    explaining the process-local limitation, a comment, a log line — parses to a
    ``Constant``, never an ``Attribute``, and is therefore invisible here. That is the
    whole reason this check is structural rather than a token scan.
    """
    owner_of: dict[int, str] = {}
    for func in _enclosing_functions(tree):
        for node in _own_nodes(func):
            owner_of[id(node)] = func.name

    hits: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == _PRIVATE_BREAKER_ATTR:
            hits.setdefault(owner_of.get(id(node), "<module>"), []).append(node.lineno)
    return {name: sorted(lines) for name, lines in hits.items()}


def _find_private_breaker_access() -> set[str]:
    """Find every step-side read/write of a service's private ``_circuit_breakers`` dict."""
    found: set[str] = set()
    for rel, tree in _iter_step_modules():
        for func_name, lines in _private_breaker_hits(tree).items():
            found.add(f"{rel} {func_name}:{','.join(str(n) for n in lines)}")
    return found


def test_no_test_side_error_construction() -> None:
    """0wby: steps must not fabricate ctx['error']; dispatch through the wire instead."""
    assert_violations_match_allowlist(
        _find_error_construction(),
        _ERROR_CONSTRUCTION_ALLOWLIST,
        fix_hint=(
            "A BDD step constructs the expected error test-side (ctx['error'] = SomeError(...)). "
            "Dispatch the malformed/invalid request through the wire (raw flat-kwargs for schema-shape "
            "rejections) so production emits it; assert via ctx['result'].assert_wire_error(...). "
            "See zh85 / 33r0 for the pattern."
        ),
    )


def test_no_reconstructed_only_error_assertion() -> None:
    """ztl6.8: error @then steps must read the wire envelope, not only the lossy ctx['error']."""
    assert_violations_match_allowlist(
        _find_reconstructed_only_assertions(),
        _RECONSTRUCTED_ASSERTION_ALLOWLIST,
        fix_hint=(
            "An error Then-step asserts on the reconstructed ctx['error'] (_get_error_code/_get_error_dict) "
            "without reading the wire envelope. Make it wire-first: read _wire_code(ctx)/_wire_suggestion(ctx) "
            "or ctx['result'].assert_wire_error(...) and fall back to the reconstructed exception only for "
            "IMPL/no-wire. See then_error.py then_error_code / then_suggestion_contains."
        ),
    )


def test_no_private_circuit_breaker_state_in_steps() -> None:
    """gra7.3: steps must not index ``service._circuit_breakers``; go through the env accessors."""
    assert_violations_match_allowlist(
        _find_private_breaker_access(),
        _PRIVATE_BREAKER_ALLOWLIST,
        fix_hint=(
            "A BDD step reaches into a service's private _circuit_breakers dict. Breaker state is "
            "process-local, so that read is unfalsifiable across a process boundary — it grades a "
            "test double, not a delivery. SEED through the harness env's breaker accessors "
            "(tests/harness/_mixins.py circuit-breaker mixin — the only place allowed to touch the "
            "private dict); READ through the production public API "
            "WebhookDeliveryService.get_circuit_breaker_state (via the env's breaker_snapshot); and "
            "where the scenario claims deliveries happen, assert the delivery EFFECT (an attempt "
            "reached the origin), not the state enum alone. The allowlist is permanently empty."
        ),
    )


# ── Check D: no step reads the provenance-stripped ctx["response"] ────────────
#
# The dispatch seams stopped writing that key: a copy of the payload cannot tell
# a Then whether it holds a wire fact or an in-process reconstruction, which is
# how a self-grading transport stayed green. Worse, the key had THREE writers
# with three meanings — dispatch, modules calling production directly, and one
# step stashing a REQUEST under it — so a reader could not know what it had.
#
# Steps read the dispatch's own TransportResult via require_payload /
# payload_or_none. Modules that still call production directly stash under the
# explicitly-named ctx["self_dispatched_response"], which the shared accessors
# know about by name.
_CTX_RESPONSE_KEY = "response"

# Shrink-only. Every entry is a module whose When calls production DIRECTLY
# rather than dispatching, with the GitHub issue tracking its migration. When a
# module migrates its entry goes; nothing may be added.
# EMPTY, and it stays that way. Every module migrated; the two that still call
# production directly (uc011's _list_accounts_impl, FIXME(#1880)) stash under the
# explicitly-named ctx["self_dispatched_response"], which the shared accessors
# know by name — so they need no exemption from this check at all.
_CTX_RESPONSE_ALLOWLIST: set[str] = set()


def _ctx_response_hits(tree: ast.AST) -> dict[str, list[int]]:
    """Subscript AND .get access to ctx["response"], per enclosing function.

    ALL FIVE access forms condition C2 made binding — subscript, ``ctx.get``,
    ``_require*(ctx, "response")``, ``"response" in ctx`` and ``ctx.pop``.
    Covering only the first two would leave a future step able to re-open the
    retired key through the shared accessor, which is exactly the escape the
    design review named.

    Subscript and ``ctx.get`` deliberately: a subscript-only check would miss the ~218
    ``ctx.get("response")`` reads this lane migrated and would pass on an almost
    entirely unmigrated tree. A string mentioning the key in a docstring parses
    to ast.Constant and is invisible to both, which is what makes the pinned set
    achievable.
    """
    hits: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lines: list[int] = []
        for child in ast.walk(node):
            # ctx["response"]
            if (
                isinstance(child, ast.Subscript)
                and isinstance(child.value, ast.Name)
                and child.value.id == "ctx"
                and isinstance(child.slice, ast.Constant)
                and child.slice.value == _CTX_RESPONSE_KEY
            ):
                lines.append(child.lineno)
            # _require(ctx, "response") / any _require*(ctx, "response") helper —
            # the escape route pass 2 named: a future step could re-open the key
            # through the shared accessor rather than by subscript.
            elif (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id.startswith("_require")
                and len(child.args) >= 2
                and isinstance(child.args[0], ast.Name)
                and child.args[0].id == "ctx"
                and isinstance(child.args[1], ast.Constant)
                and child.args[1].value == _CTX_RESPONSE_KEY
            ):
                lines.append(child.lineno)
            # "response" in ctx — a membership test is a read of the same key
            elif (
                isinstance(child, ast.Compare)
                and isinstance(child.left, ast.Constant)
                and child.left.value == _CTX_RESPONSE_KEY
                and any(isinstance(op, ast.In) for op in child.ops)
                and any(isinstance(c, ast.Name) and c.id == "ctx" for c in child.comparators)
            ):
                lines.append(child.lineno)
            # ctx.pop("response") — a clear of a key nothing writes any more is
            # dead code that reads as live state management
            elif (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "pop"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "ctx"
                and child.args
                and isinstance(child.args[0], ast.Constant)
                and child.args[0].value == _CTX_RESPONSE_KEY
            ):
                lines.append(child.lineno)
            # ctx.get("response")
            elif (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "get"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "ctx"
                and child.args
                and isinstance(child.args[0], ast.Constant)
                and child.args[0].value == _CTX_RESPONSE_KEY
            ):
                lines.append(child.lineno)
        if lines:
            hits[node.name] = sorted(set(lines))
    return hits


def _find_ctx_response_access() -> set[str]:
    found: set[str] = set()
    steps_root = _STEPS_DIR
    for path in sorted(steps_root.rglob("*.py")):
        rel = path.relative_to(steps_root).as_posix()
        if rel == "_outcome_helpers.py":
            continue  # the accessors themselves; they are the sanctioned readers
        if _ctx_response_hits(ast.parse(path.read_text())):
            found.add(rel)
    return found


class TestNoProvenanceStrippedResponseCopy:
    def test_steps_read_the_dispatch_result_not_a_payload_copy(self):
        """No step module reads ctx["response"] in any of its five access forms."""
        assert_violations_match_allowlist(
            {(module,) for module in _find_ctx_response_access()},
            {(module,) for module in _CTX_RESPONSE_ALLOWLIST},
            fix_hint=(
                "A Then reading ctx['response'] cannot tell a wire fact from an in-process "
                "reconstruction. Read the dispatch's TransportResult instead — require_payload(ctx) "
                "when a payload is required, payload_or_none(ctx) when the step branches on which "
                "path ran. Modules whose When calls production directly stash under "
                "ctx['self_dispatched_response'], which those accessors know by name."
            ),
        )

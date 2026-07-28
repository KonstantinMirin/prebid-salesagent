"""Guard: a BDD oracle must not read a ``ctx`` key that no step ever writes.

``ctx`` is the mutable dict shared across steps in a scenario. A Then-step reads
the entities and outcomes a prior step was expected to put there. When it reads a
key **nothing writes**, one of two things is true:

* the read supplies a literal default -- the oracle silently degrades into a
  constant, which is indistinguishable from having no assertion at all; or
* it does not -- the read yields ``None`` or raises ``KeyError``, which is at
  least loud, but the branch behind it is dead.

The first form is the dangerous one, and it is invisible to every other guard:
``test_architecture_bdd_no_trivial_assertions`` and ``_no_pass_steps`` catch
truthiness and no-op bodies, not a defaulted read of state that was never set.

It has already cost real coverage. ``ctx.get("last_max_results", 50)`` re-paged a
cursor continuation at a hardcoded 50 regardless of the page size the scenario set
up; the only scenario happened to use 50, so the row was green while proving
nothing. ``ctx.get("pre_request_account_ids", set())`` sat behind a guard on two
other never-set keys, so a POST-F1 state-isolation obligation asserted *nothing* --
injecting ``assert False`` into its body passed on all three transports.

Background and the remaining work: GH #1749.

Detection notes, each of which cost a real finding when it was missing:

* ``_require(ctx, "k")`` / ``_require_response`` / ``_require_error``
  (``tests/bdd/steps/_outcome_helpers.py``) are the blessed loud-read helpers and
  MUST count as reads. A census that ignores them flags correctly-written call
  sites and passes badly-written ones -- observed directly: after a fix replaced a
  bare read with ``_require``, the naive read-count went *down*.
* "Literal default" must include ``set()``, ``dict()``, ``list()`` and empty
  ``{} [] ()``, not just ``ast.Constant``. A Constant-only matcher misses
  ``ctx.get(k, set())`` and ``ctx.get(k, {})``.
* ``when_*`` counts as an oracle context. ``last_max_results`` above lives in a
  When and silently changed what got *dispatched*, upstream of any assertion.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

_BDD_ROOT = Path(__file__).resolve().parents[1] / "bdd"

# Functions whose bodies are oracle-shaped: Then-steps, assertion helpers, and the
# When-steps that decide what gets dispatched.
_ORACLE_PREFIXES = ("then_", "assert_", "_assert", "when_")

# Loud-read helpers from tests/bdd/steps/_outcome_helpers.py. These raise a
# diagnostic AssertionError when the key is absent, which is the behaviour this
# guard wants -- so they are READS, not violations.
_REQUIRE_HELPERS = {"_require", "_require_response", "_require_error"}

# TIER 1 -- orphan key read WITH a literal default (the silent-constant form).
# MUST STAY EMPTY. This is the shape that turns an oracle into a constant, and it
# is at zero today. An entry here is not a deferral, it is a test that has stopped
# testing -- fix the read (write the key, or use `_require`) instead.
_ALLOWED_DEFAULTED_ORPHANS: set[str] = set()

# TIER 2 -- orphan key read with NO default. These yield None or raise rather than
# silently constant-ing, so they are dead branches rather than vacuous oracles.
# Shrink-only: never add. Tracked by GH #1749.
_ALLOWED_ORPHANS: frozenset[str] = frozenset(
    {
        "bad_package_id",
        "captured_logs",
        "dispatched_pipeline",
        "e2e_config",
        "existing_product",
        "expected_existing_package_id",
        "explicit_buying_mode",
        "last_order_name",
        "media_buy_id",
        "request_push_config",
        "seeded_task_count",
        "target_media_buy_id",
    }
)

# Writes whose key is not a string literal (`ctx[some_var] = ...`). An AST census
# cannot resolve these, so each is a potential false-orphan source. Pinning the
# count means adding one forces a conscious re-validation of the orphan list
# instead of letting this analysis silently degrade.
_MAX_DYNAMIC_KEY_WRITES = 4


def _is_literal_default(node: ast.expr) -> bool:
    """True for a default that stands in for absent scenario state."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
        return not getattr(node, "elts", None) and not getattr(node, "keys", None)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in {"set", "dict", "list"} and not node.args
    return False


def _ctx_key(node: ast.expr) -> str | None:
    """Return the string-literal subscript key of a `ctx[...]` node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan() -> tuple[set[str], dict[str, list[str]], list[tuple[str, str]], list[str]]:
    """Return (written keys, read key -> sites, defaulted orphan reads, dynamic writes)."""
    written: set[str] = set()
    read: dict[str, list[str]] = defaultdict(list)
    defaulted: list[tuple[str, str]] = []  # (key, "file:line")
    dynamic: list[str] = []

    for path in sorted(_BDD_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        rel = path.relative_to(_BDD_ROOT)

        for node in ast.walk(tree):
            # ctx["k"] = ...   (and the unresolvable ctx[<expr>] = ... form)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                        if target.value.id != "ctx":
                            continue
                        key = _ctx_key(target.slice)
                        if key is None:
                            dynamic.append(f"{rel}:{node.lineno}")
                        else:
                            written.add(key)

            if isinstance(node, ast.Call):
                func = node.func
                # ctx.setdefault("k", ...) writes; ctx.get("k") reads
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "ctx"
                    and node.args
                    and (key := _ctx_key(node.args[0])) is not None
                ):
                    if func.attr == "setdefault":
                        written.add(key)
                    elif func.attr == "get":
                        read[key].append(f"{rel}:{node.lineno}")
                # _require(ctx, "k") is a READ, and the blessed one
                if isinstance(func, ast.Name) and func.id in _REQUIRE_HELPERS and len(node.args) >= 2:
                    if (key := _ctx_key(node.args[1])) is not None:
                        read[key].append(f"{rel}:{node.lineno}")

            # ctx["k"] in a load position
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "ctx"
                and isinstance(node.ctx, ast.Load)
                and (key := _ctx_key(node.slice)) is not None
            ):
                read[key].append(f"{rel}:{node.lineno}")

        # Defaulted reads, but only inside oracle-shaped functions.
        for func_def in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            if not func_def.name.startswith(_ORACLE_PREFIXES):
                continue
            for node in ast.walk(func_def):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "ctx"
                    and len(node.args) == 2
                    and (key := _ctx_key(node.args[0])) is not None
                    and _is_literal_default(node.args[1])
                ):
                    defaulted.append((key, f"{rel}:{node.lineno}"))

    return written, read, defaulted, dynamic


class TestBddNoOrphanCtxReads:
    """A BDD oracle must not read scenario state no step ever wrote."""

    def test_no_defaulted_read_of_an_orphan_key(self) -> None:
        """TIER 1: a literal default over a never-written key makes the oracle a constant."""
        written, _read, defaulted, _dynamic = _scan()
        violations = sorted(
            f"{site}: ctx.get({key!r}, <literal>) -- nothing writes {key!r}"
            for key, site in defaulted
            if key not in written and key not in _ALLOWED_DEFAULTED_ORPHANS
        )
        assert not violations, (
            "BDD oracle reads a ctx key nothing writes AND supplies a literal default, so the "
            "assertion silently degrades into a constant:\n  "
            + "\n  ".join(violations)
            + "\n\nFix the read, do not allowlist it: write the key in the Given/When that "
            "establishes the precondition, and read it with `_require(ctx, key, hint=...)` so "
            "absence fails loudly. See GH #1749."
        )

    def test_no_orphan_ctx_reads(self) -> None:
        """TIER 2: reading a never-written key at all is dead code."""
        written, read, _defaulted, _dynamic = _scan()
        orphans = {key: sites for key, sites in read.items() if key not in written}
        unexpected = sorted(set(orphans) - _ALLOWED_ORPHANS)
        assert not unexpected, (
            "BDD steps read ctx keys that no step writes:\n  "
            + "\n  ".join(f"{key} (read at {', '.join(sorted(set(orphans[key]))[:3])})" for key in unexpected)
            + "\n\nEither write the key where the precondition is established, or delete the "
            "dead read. Do not add it to the allowlist. See GH #1749."
        )

    def test_orphan_allowlist_has_no_stale_entries(self) -> None:
        """A fixed orphan must leave the allowlist, so the ratchet only turns one way."""
        written, read, _defaulted, _dynamic = _scan()
        orphans = {key for key in read if key not in written}
        stale = sorted(_ALLOWED_ORPHANS - orphans)
        assert not stale, (
            "These keys are allowlisted as orphans but are no longer orphans -- remove them from "
            f"_ALLOWED_ORPHANS: {stale}"
        )

    def test_dynamic_key_writes_do_not_grow(self) -> None:
        """`ctx[<expr>] = ...` cannot be resolved, so it can mask a real orphan."""
        _written, _read, _defaulted, dynamic = _scan()
        assert len(dynamic) <= _MAX_DYNAMIC_KEY_WRITES, (
            f"Dynamic-key ctx writes grew to {len(dynamic)} (pinned at {_MAX_DYNAMIC_KEY_WRITES}):\n  "
            + "\n  ".join(sorted(dynamic))
            + "\n\nAn AST census cannot resolve `ctx[<expr>] = ...`, so every one of these is a "
            "key this guard may wrongly believe is never written. Prefer a string-literal key. If "
            "a dynamic write is genuinely needed, re-validate the orphan allowlist and raise the "
            "pin deliberately."
        )

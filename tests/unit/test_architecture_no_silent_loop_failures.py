"""Guard: per-item failures in _impl loops must be surfaced, not swallowed.

CLAUDE.md rule: "No Quiet Failures". When an ``_impl`` function iterates to
build a response and an item's processing fails, the failure must be visible
to the caller — a raised ``AdCPError``, an advisory appended to the response's
``errors[]`` list, or at minimum a recorded per-item result. A handler that
only logs (or logs and ``continue``s) makes the item silently vanish from the
response: the buyer sees a shorter list with no signal that anything failed.

Origin: PR #1545 review — ``_get_media_buy_delivery_impl`` had two sibling
handlers on the same loop path; the inner adapter handler appended a
``SERVICE_UNAVAILABLE`` advisory while the outer handler only logged and fell
through, so a failure in the status/model path dropped the buy with no signal.

Detection (AST): inside functions named ``*_impl`` under ``src/core/tools/``,
an ``except`` handler that sits directly in a ``for``/``while`` loop (not
nested inside another handler — best-effort cleanup like audit-log writes is
exempt) is a violation when it:

- contains no ``raise``, AND
- calls no ``.append(...)`` / ``.extend(...)`` / ``.add(...)``, AND
- either contains ``continue`` (item explicitly skipped) or consists solely
  of expression/``pass`` statements (log-only fall-through).

Handlers that assign a fallback value and let the iteration proceed are fine —
the item still reaches the response.

Allowlist can only SHRINK. Every entry has a FIXME(#gh-issue) at the source.
"""

import ast

import pytest

from tests.unit._architecture_helpers import (
    REPO_ROOT,
    assert_detector_catches_ast_snippets,
    assert_violations_match_allowlist,
    format_failure,
    iter_call_expressions,
    iter_module_trees,
)

SCAN_DIRS = [REPO_ROOT / "src/core/tools"]

# Pre-existing violations, keyed (repo-relative file, enclosing function).
# Each has a FIXME(#gh-issue) comment at the source. Shrink-only.
SILENT_LOOP_HANDLER_ALLOWLIST: set[tuple[str, str]] = {
    # FIXME(#1566): unparseable Broadstreet template dropped from formats silently
    ("src/core/tools/creative_formats.py", "_list_creative_formats_impl"),
    # FIXME(#1566): creative-association failure logged only, absent from response
    ("src/core/tools/media_buy_create.py", "_create_media_buy_impl"),
}

FIX_HINT = (
    "Surface the failure: append an advisory Error to the response errors[] list "
    "(see the SERVICE_UNAVAILABLE handler in _get_media_buy_delivery_impl), raise an "
    "AdCPError, or assign a fallback the response can carry. If the swallow is "
    "genuinely correct, allowlist it with a FIXME(#gh-issue) at the source."
)


def _handler_is_silent(handler: ast.ExceptHandler) -> bool:
    """True when the handler swallows the failure without surfacing it.

    KNOWN OVER-APPROXIMATION: a handler is treated as *surfacing* if it raises OR
    calls any ``.append``/``.extend``/``.add`` — regardless of the target. A
    handler that appends to an unrelated scratch buffer (``log; scratch.append(x);
    continue``) is therefore a FALSE NEGATIVE this guard will not catch: proving,
    via AST alone, that the append target is the response's ``errors[]`` list
    would require whole-function dataflow the guard deliberately avoids. So an
    empty allowlist means "no handler that both loops-and-continues AND does
    nothing list-like was found" — NOT "every dropped item is provably surfaced."
    The append-to-``errors[]`` convention is the enforceable proxy; genuine
    surfacing is still a human-review responsibility.
    """
    has_continue = False
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return False
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"append", "extend", "add"}
        ):
            return False
        if isinstance(node, ast.Continue):
            has_continue = True
    log_only = all(isinstance(stmt, ast.Expr | ast.Pass) for stmt in handler.body)
    return has_continue or log_only


def find_silent_loop_handlers(tree: ast.Module, relpath: str) -> list[tuple[str, str, int]]:
    """Return (relpath, function_name, lineno) for silent handlers in _impl loops."""
    violations: list[tuple[str, str, int]] = []

    def visit(node: ast.AST, func_name: str, in_loop: bool, in_handler: bool) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func_name = node.name
            in_loop = False  # loop/handler context does not cross function boundaries
            in_handler = False
        if isinstance(node, ast.For | ast.AsyncFor | ast.While):
            in_loop = True
        if isinstance(node, ast.ExceptHandler):
            if in_loop and not in_handler and func_name.endswith("_impl") and _handler_is_silent(node):
                violations.append((relpath, func_name, node.lineno))
            in_handler = True
        for child in ast.iter_child_nodes(node):
            visit(child, func_name, in_loop, in_handler)

    visit(tree, "<module>", False, False)
    return violations


def _scan_all() -> list[tuple[str, str, int]]:
    violations: list[tuple[str, str, int]] = []
    for tree, relpath in iter_module_trees(SCAN_DIRS):
        violations.extend(find_silent_loop_handlers(tree, relpath))
    return violations


KNOWN_BAD_SNIPPETS = {
    "log-only-fallthrough": (
        "async def _foo_impl(req):\n"
        "    for item in req.items:\n"
        "        try:\n"
        "            results.append(process(item))\n"
        "        except Exception as e:\n"
        "            logger.error(f'failed {item}: {e}')\n"
    ),
    "log-and-continue": (
        "def _bar_impl(req):\n"
        "    for item in req.items:\n"
        "        try:\n"
        "            results.append(process(item))\n"
        "        except ValueError as e:\n"
        "            logger.warning('skipping %s', item)\n"
        "            continue\n"
    ),
    "bare-pass": (
        "def _baz_impl(req):\n"
        "    while req.pending:\n"
        "        try:\n"
        "            step(req)\n"
        "        except Exception:\n"
        "            pass\n"
    ),
}

KNOWN_GOOD_SNIPPETS = {
    "appends-advisory": (
        "def _ok_impl(req):\n"
        "    for item in req.items:\n"
        "        try:\n"
        "            results.append(process(item))\n"
        "        except Exception as e:\n"
        "            errors.append(Error(code='SERVICE_UNAVAILABLE', message=str(e)))\n"
        "            continue\n"
    ),
    "reraises": (
        "def _ok2_impl(req):\n"
        "    for item in req.items:\n"
        "        try:\n"
        "            results.append(process(item))\n"
        "        except AdCPError:\n"
        "            raise\n"
    ),
    "fallback-assignment": (
        "def _ok3_impl(req):\n"
        "    for item in req.items:\n"
        "        try:\n"
        "            status = parse(item.status)\n"
        "        except ValueError:\n"
        "            status = 'pending_review'\n"
        "        results.append(build(item, status))\n"
    ),
    "cleanup-inside-handler-exempt": (
        "def _ok4_impl(req):\n"
        "    for item in req.items:\n"
        "        try:\n"
        "            results.append(process(item))\n"
        "        except Exception as e:\n"
        "            try:\n"
        "                audit(e)\n"
        "            except Exception as audit_err:\n"
        "                logger.error('audit failed: %s', audit_err)\n"
        "            errors.append(Error(code='SERVICE_UNAVAILABLE', message=str(e)))\n"
    ),
    "non-impl-function-out-of-scope": (
        "def helper(items):\n"
        "    for item in items:\n"
        "        try:\n"
        "            step(item)\n"
        "        except Exception:\n"
        "            pass\n"
    ),
}


class TestNoSilentLoopFailuresInImpl:
    """Per-item failures in _impl response loops must be surfaced."""

    @pytest.mark.arch_guard
    def test_no_new_silent_loop_handlers(self):
        """No _impl loop handler swallows a per-item failure outside the allowlist."""
        found = _scan_all()
        new = [(f, fn, line) for f, fn, line in found if (f, fn) not in SILENT_LOOP_HANDLER_ALLOWLIST]
        assert not new, format_failure(
            summary=(
                f"Found {len(new)} except handler(s) in _impl loops that swallow "
                "per-item failures without surfacing them:"
            ),
            violations=[f"{f}:{line}: in {fn}" for f, fn, line in new],
            fix_hint=FIX_HINT,
            docs_link="CLAUDE.md § No Quiet Failures",
        )

    @pytest.mark.arch_guard
    def test_allowlist_entries_still_exist(self):
        """Every allowlisted violation must still exist (stale-entry detection)."""
        found_keys = {(f, fn) for f, fn, _ in _scan_all()}
        assert_violations_match_allowlist(
            found_keys,
            SILENT_LOOP_HANDLER_ALLOWLIST,
            fix_hint=FIX_HINT,
        )

    @pytest.mark.arch_guard
    def test_detector_catches_known_bad_snippets(self):
        """Detector self-test: known-bad shapes must be flagged."""
        assert_detector_catches_ast_snippets(
            lambda tree: [line for _, _, line in find_silent_loop_handlers(tree, "<snippet>")],
            snippets=KNOWN_BAD_SNIPPETS,
        )

    @pytest.mark.arch_guard
    def test_detector_passes_known_good_snippets(self):
        """Detector self-test: surfaced/fallback/exempt shapes must NOT be flagged."""
        false_positives = []
        for label, source in KNOWN_GOOD_SNIPPETS.items():
            tree = ast.parse(source, filename=f"<known-good:{label}>")
            if find_silent_loop_handlers(tree, "<snippet>"):
                false_positives.append(label)
        assert not false_positives, "Detector flagged known-good snippet(s):\n" + "\n".join(
            f"  {s}" for s in false_positives
        )


# ══════════════════════════════════════════════════════════════════════════════
# Straight-line degradation handlers (salesagent-3xmz B6)
# ══════════════════════════════════════════════════════════════════════════════
#
# The detector above only sees handlers INSIDE a for/while loop, and it exempts
# "handlers that assign a fallback value and let iteration proceed". Both
# exclusions are right for the per-item case, and both make it structurally blind
# to the OTHER shape of the same disease: a straight-line `try/except` around a
# whole lookup that logs, falls through to a placeholder, and returns a silently
# degraded response.
#
# That is what `_get_adcp_capabilities_impl` did at five sites before B5 — the
# buyer could not tell "this seller has none" from "the lookup failed".
#
# Keyed STRUCTURALLY, not by function name: an `*_impl` that builds an advisory
# list and passes it to a response `errors=` argument has opted into surfacing
# degradations, so every straight-line handler in it must append to that list. A
# rule keyed to the literal name `_get_adcp_capabilities_impl` would die silently
# on a rename or a helper extraction — which the B5 "extract ONE helper" step
# makes likely. Keying on the advisory list means the guard follows the pattern,
# not the identifier.
#
# Deliberately NARROW: functions with no advisory list are not in scope, so
# products.py (which degrades but builds no advisory list) stays invisible here.
# Widening the detector to those is salesagent-gr4z, which would surface that
# group all at once.
#
# "Advisory list" means a CONTAINER this function holds and a handler can reach —
# see `_advisory_list_names`. `_create_media_buy_impl` derives its advisories from
# the request (`errors=property_list_unsupported_advisories(req.packages, adapter)`)
# and holds no container, so it is out of scope and no longer allowlisted. Its
# best-effort Slack / activity-feed / audit-log handlers were never this guard's
# business; the per-item row in SILENT_LOOP_HANDLER_ALLOWLIST above still covers
# the one loop-shaped swallow it does have.

_ADVISORY_FIX_HINT = (
    "This _impl builds an advisory list passed to a response errors= argument, so "
    "every straight-line except handler in it must append to that list (see "
    "_record_degradation in src/core/tools/capabilities.py). Log-and-fall-through "
    "leaves the buyer with a silently degraded response. If the handler genuinely "
    "needs no advisory, raise instead, or allowlist it with a FIXME(#gh-issue)."
)

# Straight-line handlers that log without surfacing, in _impl functions that DO
# build an advisory list. This is the NEW guard's initial baseline (the same way
# SILENT_LOOP_HANDLER_ALLOWLIST above was seeded), not allowlist growth: these
# predate the guard. Shrink-only from here.
#
# `_get_adcp_capabilities_impl` is deliberately ABSENT — salesagent-3xmz B5 fixed
# all five of its sites, and that absence is what makes this guard a pin on the
# fix rather than a description of it.
SILENT_ADVISORY_HANDLER_ALLOWLIST: set[tuple[str, str]] = {
    # FIXME(#1566): exactly TWO handlers, both response-degrading and both with a
    # FIXME at the source: creative_formats.py:297 drops the adapter's formats and
    # :487 drops the creative-agent referrals, each with nothing but a log line, so
    # the buyer reads "this seller has none" off a failed lookup. Same disease as
    # the loop-shaped row already allowlisted for this function above.
    #
    # (The other two handlers in this function — the :225 event-loop retry and the
    # :447 cursor reset — are silent fallbacks the detector now exempts, and
    # `_create_media_buy_impl` is gone from this list entirely: it has no advisory
    # container at all, so it was never in scope. See the two notes below.)
    ("src/core/tools/creative_formats.py", "_list_creative_formats_impl"),
}

_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical"})


def _advisory_list_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Local names that ARE the advisory container passed to a response ``errors=``.

    Matches the direct form (``errors=advisories``, ``errors=agent_errors if
    agent_errors else None``) and the normalized form
    (``errors=normalize_advisory_errors(advisories) or None``), since the
    normalizer is the sanctioned wrapper around the container.

    Two filters keep this to the CONTAINER rather than every name in the
    expression. Harvesting every ``ast.Name`` (the first cut of this detector)
    read ``errors=property_list_unsupported_advisories(req.packages, adapter)`` in
    ``_create_media_buy_impl`` as three advisory lists — ``req``, ``adapter`` and
    the callee. That function computes its advisories from the REQUEST and holds
    no container at all, so the guard's own fix hint ("append to that list") was
    impossible to follow there; worse, treating ``req``/``adapter`` as advisory
    names made every handler that merely passes one of them to a call score as
    "surfacing" — a false NEGATIVE. So:

    - a name must be *bound in this function* and not a parameter, and
    - a name reached only as a call argument counts only in the wrapper position
      (first positional arg of the call producing the value); a helper that
      DERIVES advisories from other inputs contributes no container.

    Strictly narrower than harvesting every name, so it can only remove functions
    from scope, never add them.
    """
    bound = {n.id for n in ast.walk(func) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    params = {a.arg for a in (*func.args.posonlyargs, *func.args.args, *func.args.kwonlyargs)}
    if func.args.vararg:
        params.add(func.args.vararg.arg)
    if func.args.kwarg:
        params.add(func.args.kwarg.arg)
    local_names = bound - params

    candidates: set[str] = set()
    for node in iter_call_expressions(func):
        for kw in node.keywords:
            if kw.arg != "errors" or kw.value is None:
                continue
            candidates.update(_container_candidates(kw.value))
    return candidates & local_names


def _container_candidates(value: ast.expr) -> set[str]:
    """Names in an ``errors=`` value that could be the advisory container itself."""
    disqualified: set[str] = set()
    for call in iter_call_expressions(value):
        # the callee is the wrapper, never the container
        disqualified.update(_names_in(call.func))
        for pos, arg in enumerate(call.args):
            if pos == 0 and isinstance(arg, ast.Name):
                continue  # normalize_advisory_errors(advisories) — the wrapper's subject
            disqualified.update(_names_in(arg))
        for kw in call.keywords:
            disqualified.update(_names_in(kw.value))
    return _names_in(value) - disqualified


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _handler_appends_to(handler: ast.ExceptHandler, names: set[str]) -> bool:
    """True when the handler surfaces via one of *names*, directly or via a helper.

    A call passing an advisory-list name as an argument counts: the B5 fix routes
    all five sites through ``_record_degradation(advisories, ...)``, and requiring
    a literal ``advisories.append`` would punish exactly the DRY extraction the
    disease scan asked for.
    """
    if any(isinstance(n, ast.Raise) for n in ast.walk(handler)):
        return True
    for node in iter_call_expressions(handler):
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"append", "extend"}
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in names
        ):
            return True
        if any(isinstance(a, ast.Name) and a.id in names for a in node.args):
            return True
    return False


def _handler_is_exempt_shape(handler: ast.ExceptHandler) -> bool:
    """True for the two non-swallowing shapes the sibling loop detector exempts.

    ``_handler_is_silent`` above flags a loop handler only when its body is
    *solely* expression/``pass`` statements, so a handler that RETURNS or that
    ASSIGNS a fallback is already exempt there. Both shapes reach this detector
    too and were false positives until now:

    - ``return <helper>``: control leaves the function — the failure is resolved
      or re-raised downstream, never absorbed into a degraded response
      (``except IntegrityError: return _resolve_idempotency_race_or_raise(...)``).
    - a SILENT fallback assignment: the handler substitutes a default and moves on
      (the ``except RuntimeError:`` event-loop retry and the ``except ValueError:
      start_index = 0`` cursor reset in ``creative_formats``).

    The fallback exemption is deliberately NARROWER than the sibling's. A
    fallback assignment is structurally indistinguishable from the placeholder
    degradation salesagent-3xmz B5 fixed in ``capabilities`` (``except: channels =
    [DEFAULT]`` leaves the buyer unable to tell "none" from "lookup failed"), so
    exempting it wholesale would un-pin that fix. A handler that LOGS is admitting
    something went wrong and must still surface it; only the silent, deliberate
    default is exempt.
    """
    if any(isinstance(n, ast.Return) for n in ast.walk(handler)):
        return True
    logs = any(
        isinstance(n.func, ast.Attribute) and n.func.attr in _LOG_METHODS for n in iter_call_expressions(handler)
    )
    assigns = any(isinstance(n, ast.Assign | ast.AnnAssign | ast.AugAssign) for n in ast.walk(handler))
    return assigns and not logs


def find_silent_advisory_handlers(tree: ast.Module, relpath: str) -> list[tuple[str, str, int]]:
    """Return (relpath, function_name, lineno) for straight-line handlers that
    fail to surface a degradation in an advisory-emitting ``*_impl``."""
    violations: list[tuple[str, str, int]] = []

    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not func.name.endswith("_impl"):
            continue
        names = _advisory_list_names(func)
        if not names:
            continue  # not an advisory-emitting _impl — out of scope (see gr4z)

        def visit(
            node: ast.AST,
            in_loop: bool,
            in_handler: bool,
            _names: set[str] = names,
            _fname: str = func.name,
        ) -> None:
            if isinstance(node, ast.For | ast.AsyncFor | ast.While):
                in_loop = True
            if isinstance(node, ast.ExceptHandler):
                # loop handlers belong to the per-item detector above; nested
                # handlers are best-effort cleanup, exempt by the same rule
                if (
                    not in_loop
                    and not in_handler
                    and not _handler_appends_to(node, _names)
                    and not _handler_is_exempt_shape(node)
                ):
                    violations.append((relpath, _fname, node.lineno))
                in_handler = True
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue  # nested function: its own scope
                visit(child, in_loop, in_handler)

        visit(func, False, False)

    return violations


def _scan_all_advisory() -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for tree, relpath in iter_module_trees(SCAN_DIRS):
        found.extend(find_silent_advisory_handlers(tree, relpath))
    return found


_ADVISORY_BAD = {
    "log_only_in_advisory_impl": (
        "def _thing_impl():\n"
        "    advisories = []\n"
        "    try:\n"
        "        x = lookup()\n"
        "    except Exception as e:\n"
        "        logger.warning(e)\n"
        "    return Response(errors=advisories or None)\n"
    ),
    # The salesagent-3xmz B5 shape: log, substitute a placeholder, hand the buyer a
    # response that cannot be told apart from "this seller genuinely has none". The
    # log line is what separates it from the exempt silent-default shape below.
    "log_and_fallback_without_advisory": (
        "def _thing_impl():\n"
        "    advisories = []\n"
        "    try:\n"
        "        channels = lookup()\n"
        "    except Exception as e:\n"
        "        logger.warning('channel lookup failed: %s', e)\n"
        "        channels = [DEFAULT]\n"
        "    return Response(errors=normalize(advisories))\n"
    ),
}

_ADVISORY_GOOD = {
    "appends_directly": (
        "def _thing_impl():\n"
        "    advisories = []\n"
        "    try:\n"
        "        x = lookup()\n"
        "    except Exception as e:\n"
        "        advisories.append(Err(code='SERVICE_UNAVAILABLE', message=str(e)))\n"
        "    return Response(errors=advisories or None)\n"
    ),
    # would-be-missed: the DRY extraction the disease scan asked for. A detector
    # requiring a literal `advisories.append` would flag this CORRECT code.
    "appends_via_helper": (
        "def _thing_impl():\n"
        "    advisories = []\n"
        "    try:\n"
        "        x = lookup()\n"
        "    except Exception as e:\n"
        "        _record_degradation(advisories, 'thing', e)\n"
        "    return Response(errors=normalize(advisories) or None)\n"
    ),
    "no_advisory_list_is_out_of_scope": (
        "def _other_impl():\n"
        "    try:\n"
        "        x = lookup()\n"
        "    except Exception as e:\n"
        "        logger.warning(e)\n"
        "    return Response()\n"
    ),
    "raises_instead": (
        "def _thing_impl():\n"
        "    advisories = []\n"
        "    try:\n"
        "        x = lookup()\n"
        "    except Exception as e:\n"
        "        raise AdCPError(str(e)) from e\n"
        "    return Response(errors=advisories or None)\n"
    ),
    # shape (a): control leaves the function — the helper resolves the race or raises
    "returns_helper_that_raises": (
        "def _thing_impl():\n"
        "    advisories = []\n"
        "    try:\n"
        "        x = persist()\n"
        "    except IntegrityError as exc:\n"
        "        return _resolve_idempotency_race_or_raise(exc, tenant_id)\n"
        "    return Response(errors=advisories or None)\n"
    ),
    # shape (b): a deliberate, SILENT default — the cursor reset / event-loop retry.
    # Add a log line and it becomes `log_and_fallback_without_advisory` above, which
    # stays BAD: that is what keeps the B5 placeholder fix pinned.
    "silent_fallback_default": (
        "def _thing_impl():\n"
        "    advisories = []\n"
        "    try:\n"
        "        start_index = int(decode(cursor))\n"
        "    except ValueError:\n"
        "        start_index = 0\n"
        "    return Response(errors=advisories or None)\n"
    ),
    # advisories DERIVED from the request, no container the handler could reach:
    # the guard's fix hint is unfollowable here, so the function is out of scope.
    "derived_advisories_have_no_container": (
        "def _thing_impl(req):\n"
        "    adapter = get_adapter(req)\n"
        "    try:\n"
        "        notify(req)\n"
        "    except Exception as e:\n"
        "        logger.warning('notify failed: %s', e)\n"
        "    return Response(errors=unsupported_advisories(req.packages, adapter))\n"
    ),
}


class TestNoSilentAdvisoryHandlersInImpl:
    """Straight-line degradations in advisory-emitting _impls must be surfaced."""

    @pytest.mark.arch_guard
    def test_no_new_silent_advisory_handlers(self):
        found = _scan_all_advisory()
        new = [(f, fn, line) for f, fn, line in found if (f, fn) not in SILENT_ADVISORY_HANDLER_ALLOWLIST]
        assert not new, format_failure(
            summary=(
                f"Found {len(new)} straight-line except handler(s) in advisory-emitting "
                "_impl functions that degrade the response without surfacing it:"
            ),
            violations=[f"{f}:{line}: in {fn}" for f, fn, line in new],
            fix_hint=_ADVISORY_FIX_HINT,
            docs_link="CLAUDE.md § No Quiet Failures",
        )

    @pytest.mark.arch_guard
    def test_advisory_allowlist_entries_still_exist(self):
        assert_violations_match_allowlist(
            {(f, fn) for f, fn, _ in _scan_all_advisory()},
            SILENT_ADVISORY_HANDLER_ALLOWLIST,
            fix_hint=_ADVISORY_FIX_HINT,
        )

    @pytest.mark.arch_guard
    def test_advisory_detector_catches_known_bad(self):
        assert_detector_catches_ast_snippets(
            lambda tree: [line for _, _, line in find_silent_advisory_handlers(tree, "<snippet>")],
            snippets=_ADVISORY_BAD,
        )

    @pytest.mark.arch_guard
    def test_advisory_detector_passes_known_good(self):
        false_positives = []
        for label, source in _ADVISORY_GOOD.items():
            tree = ast.parse(source, filename=f"<known-good:{label}>")
            if find_silent_advisory_handlers(tree, f"<known-good:{label}>"):
                false_positives.append(label)
        assert not false_positives, f"detector flagged correct shapes: {false_positives}"

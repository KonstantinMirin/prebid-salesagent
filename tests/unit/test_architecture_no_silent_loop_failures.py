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

# Straight-line silent handlers in *_impl — the widened rule (salesagent-gr4z).
# Keyed (repo-relative file, enclosing function, ORDINAL of the silent handler within that
# function). Several sites share one function, so a coarser key would let a new violation hide
# behind an existing entry; a line-number key would make every entry in a file go stale whenever
# anything above it moved. Shrink-only.
#
# Classification is by whether the handler alters the CLIENT-FACING RESPONSE:
#   BENIGN       — a side effect (Slack, activity feed, audit row). The buyer's response is
#                  identical whether it succeeded or not, so there is nothing to surface to them.
#   DEGRADES     — content is dropped from the response with no signal. These are the real
#                  violations; each names the ticket that owns the migration.
_SILENT_STRAIGHT_LINE_ALLOWLIST: set[tuple[str, str, int]] = {
    # -- BENIGN: notification / audit side effects, response unchanged ----------------------------
    ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", 0),  # Slack: manual approval
    ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", 1),  # activity feed
    ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", 2),  # audit log
    ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", 3),  # Slack: config approval
    ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", 4),  # activity feed
    ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", 5),  # Slack: success
    # -- DEGRADES the response: real violations, migration owned elsewhere -------------------------
    # salesagent-3xmz migrates these to GetAdcpCapabilitiesResponse.errors[].
    ("src/core/tools/capabilities.py", "_get_adcp_capabilities_impl", 0),  # adapter channels dropped
    ("src/core/tools/capabilities.py", "_get_adcp_capabilities_impl", 1),  # publisher domains dropped
    # salesagent-gr4z: adapter formats / agent referrals dropped from the format list.
    ("src/core/tools/creative_formats.py", "_list_creative_formats_impl", 0),
    ("src/core/tools/creative_formats.py", "_list_creative_formats_impl", 1),
    # salesagent-gr4z: GetProductsResponse HAS errors[], so these four are the strongest migration
    # candidates — dynamic variants, dynamic pricing, AI ranking and adapter-support annotations all
    # silently vanish from the response. NOT migrated here: emitting advisory errors changes the
    # response contract, and CLAUDE.md's spec-grounding gate requires citing the pinned AdCP section
    # that mandates it BEFORE the code is written. The pin does not mandate advisory errors on
    # degraded enrichment, and UC-001-MAIN-41/42 require only that a warning be LOGGED (which
    # salesagent-19w8 now grades). Migrating on the strength of "the field exists" would be exactly
    # the downstream-artifact reasoning that gate exists to prevent.
    ("src/core/tools/products.py", "_get_products_impl", 0),  # dynamic variants
    ("src/core/tools/products.py", "_get_products_impl", 1),  # dynamic pricing
    ("src/core/tools/products.py", "_get_products_impl", 2),  # AI ranking
    ("src/core/tools/products.py", "_get_products_impl", 3),  # adapter-support annotations
}

STRAIGHT_LINE_FIX_HINT = (
    "A straight-line try/except in an _impl that drops content from the response is the same "
    "'No Quiet Failures' violation as the loop form — the buyer gets a degraded response with no "
    "signal. Surface it (advisory Error on the response errors[] list, per _normalize_advisory_errors "
    "in media_buy_delivery.py) or raise. If the handler only guards a side effect that cannot change "
    "the response (Slack, activity feed, audit row), allowlist it with that reason."
)

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


def find_silent_handlers(tree: ast.Module, relpath: str, *, scope: str) -> list[tuple[str, str, int]]:
    """Return (relpath, function_name, lineno) for silent handlers in ``_impl`` functions.

    ``scope="loop"`` keeps the original rule: a handler sitting directly in a for/while loop, where
    the failure makes an ITEM vanish from a response list.

    ``scope="straight-line"`` is the widened rule. The original detector was scoped to loops (see
    the module docstring), so a plain ``try: enrich(...) except: log`` in an ``_impl`` was
    structurally invisible to it — even though it degrades the client-facing response in exactly
    the way "No Quiet Failures" forbids, and even though the four swallowed degradations in
    ``_get_adcp_capabilities_impl`` that motivated salesagent-3xmz are all of that shape. Same
    disease, different statement position (salesagent-gr4z).
    """
    violations: list[tuple[str, str, int]] = []
    want_loop = scope == "loop"
    seen_per_function: dict[str, int] = {}

    def visit(node: ast.AST, func_name: str, in_loop: bool, in_handler: bool) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func_name = node.name
            in_loop = False  # loop/handler context does not cross function boundaries
            in_handler = False
        if isinstance(node, ast.For | ast.AsyncFor | ast.While):
            in_loop = True
        if isinstance(node, ast.ExceptHandler):
            if in_loop == want_loop and not in_handler and func_name.endswith("_impl") and _handler_is_silent(node):
                # Key by ORDINAL within the function, not by line: several sites share one function,
                # so a coarser key would let a new violation hide behind an existing entry, while a
                # line-number key would make every allowlist entry in a file go stale the moment
                # anything above it moved.
                ordinal = seen_per_function.get(func_name, 0)
                seen_per_function[func_name] = ordinal + 1
                violations.append((relpath, func_name, ordinal))
            in_handler = True
        for child in ast.iter_child_nodes(node):
            visit(child, func_name, in_loop, in_handler)

    visit(tree, "<module>", False, False)
    return violations


def find_silent_loop_handlers(tree: ast.Module, relpath: str) -> list[tuple[str, str, int]]:
    """Back-compat alias for the loop-scoped rule."""
    return find_silent_handlers(tree, relpath, scope="loop")


def _scan_all(scope: str = "loop") -> list[tuple[str, str, int]]:
    violations: list[tuple[str, str, int]] = []
    for tree, relpath in iter_module_trees(SCAN_DIRS):
        violations.extend(find_silent_handlers(tree, relpath, scope=scope))
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


class TestNoSilentStraightLineFailuresInImpl:
    """Response-degrading swallows in _impl must be surfaced, wherever the handler sits.

    The loop-scoped rule below could not see these: its detector requires the handler to sit
    directly in a for/while, so a plain ``try: enrich(...) except: log`` was structurally invisible
    even though it degrades the response identically (salesagent-gr4z).
    """

    @pytest.mark.arch_guard
    def test_no_new_silent_straight_line_handlers(self):
        found = _scan_all(scope="straight-line")
        new = [row for row in found if row not in _SILENT_STRAIGHT_LINE_ALLOWLIST]
        assert not new, format_failure(
            summary=(
                f"Found {len(new)} straight-line except handler(s) in _impl functions that swallow "
                "a failure without surfacing it:"
            ),
            violations=[f"{f}:{line}: in {fn}" for f, fn, line in new],
            fix_hint=STRAIGHT_LINE_FIX_HINT,
            docs_link="CLAUDE.md § No Quiet Failures",
        )

    @pytest.mark.arch_guard
    def test_straight_line_allowlist_entries_still_exist(self):
        assert_violations_match_allowlist(
            set(_scan_all(scope="straight-line")),
            _SILENT_STRAIGHT_LINE_ALLOWLIST,
            fix_hint=STRAIGHT_LINE_FIX_HINT,
        )

    @pytest.mark.arch_guard
    def test_detector_catches_straight_line_shapes(self):
        """The shape the loop rule is blind to must be caught, and the loop shape must NOT be."""
        straight = (
            "def _foo_impl(req):\n"
            "    try:\n"
            "        products = enrich(req)\n"
            "    except Exception as e:\n"
            "        logger.warning('enrichment failed: %s', e)\n"
        )
        tree = ast.parse(straight)
        assert find_silent_handlers(tree, "<snippet>", scope="straight-line"), (
            "straight-line swallow not detected — the widened rule grades nothing"
        )
        assert not find_silent_handlers(tree, "<snippet>", scope="loop"), (
            "straight-line swallow leaked into the loop rule, which would double-report it"
        )

    @pytest.mark.arch_guard
    def test_straight_line_rule_ignores_loop_handlers(self):
        """The two rules must partition the sites, or one allowlist silently covers the other."""
        loop_only = KNOWN_BAD_SNIPPETS["log-only-fallthrough"]
        tree = ast.parse(loop_only)
        assert find_silent_handlers(tree, "<snippet>", scope="loop")
        assert not find_silent_handlers(tree, "<snippet>", scope="straight-line")

    @pytest.mark.arch_guard
    def test_straight_line_rule_respects_surfacing(self):
        """A handler that appends an advisory is compliant in the straight-line form too."""
        ok = (
            "def _ok_impl(req):\n"
            "    try:\n"
            "        products = enrich(req)\n"
            "    except Exception as e:\n"
            "        errors.append(Error(code='SERVICE_UNAVAILABLE', message=str(e)))\n"
        )
        assert not find_silent_handlers(ast.parse(ok), "<snippet>", scope="straight-line")


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

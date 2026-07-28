"""Guard: no exponential retry backoff computed outside the egress seam.

``src/core/security/outbound_http.py`` decides the retry schedule for every
outbound request: BR-RULE-029's 1s/2s/4s, each plus a ``uniform(0, 1)`` draw.
A call site that computes its own geometric delay is deciding that policy a
second time, and the two drift — which is exactly what happened before
salesagent-4fya.6: one site slept 1/2/4, another skipped the 1s step entirely
and slept 2/4, and the seam itself slept 0.1/0.2/0.4 with no jitter at all. The
BDD step that was supposed to catch it only compared successive delays as a
ratio, so every one of those schedules passed.

This is the class-level counterpart to ``test_architecture_no_raw_egress.py``.
That guard stops a call site owning the *transport*; this one stops it owning
the *schedule*. They are separate diseases: a site can route through the seam
and still wrap it in its own retry loop (``src/core/utils/mcp_client.py`` does).

What counts as a violation: a ``sleep()`` whose duration is computed
geometrically. Three forms, because real code uses all three and a detector that
only read the inline one would report almost nothing:

- inline — ``time.sleep(2**attempt)``, ``time.sleep(min(5 * 2**attempt, 30))``
- via a local — ``backoff_time = 2**attempt`` then ``time.sleep(backoff_time)``
- via a helper in the same module — ``time.sleep(_backoff_seconds(attempt))``,
  which is the seam's own form (one hop only; a guard is not a call graph)

What does NOT count, deliberately:

- A constant or config-driven sleep: ``time.sleep(poll_interval)``,
  ``asyncio.sleep(SLEEP_INTERVAL_SECONDS)``, ``time.sleep(0.5)``. Polling a
  remote that is *working*, pacing an SSE stream and ticking a scheduler are not
  retry schedules, and there are two dozen of them in ``src/``.
- Exponentiation that never reaches a sleep. The power has to flow into the
  duration, by one of the three routes above.

The allowlist is seeded at its maximum — every geometric sleep in ``src/`` at
the time salesagent-4fya.6 landed — and only shrinks. Each entry names the
ticket that removes it, so an entry that outlives its ticket is visible.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    assert_violations_match_allowlist,
    iter_call_expressions,
    parse_module,
    rel,
    repo_root,
    src_python_files,
)

# The one module allowed to compute a retry schedule.
SEAM_FILE = "src/core/security/outbound_http.py"
EXEMPT_FILES = frozenset({SEAM_FILE})

# Sleep callables, however they are spelled: time.sleep, asyncio.sleep, a bare
# imported sleep, or an awaited one. iter_call_expressions matches both the bare
# name and the attribute form.
SLEEP_NAME = "sleep"

# Pre-existing violations: (module_path, geometric_sleep_count).
# Seeded at the maximum when salesagent-4fya.6 centralised the schedule. It only
# shrinks — the named ticket for each entry is what removes it.
ALLOWLIST = {
    # Counterparty-supplied URLs — these migrate onto the seam and inherit its
    # schedule. Tickets: salesagent-4fya.11, .10, .9, salesagent-cnkq
    # (salesagent-4fya.8 migrated order_approval_service and removed its entry).
    ("src/core/webhook_delivery.py", 1),
    ("src/services/webhook_delivery_service.py", 1),
    ("src/core/creative_agent_registry.py", 2),  # the 429 Retry-After fallback and the plain retry
    ("src/services/protocol_webhook_service.py", 2),
    # Egress retry schedules that no migration ticket covered — found by the
    # salesagent-4fya.6 disease scan, filed as salesagent-zlwz and salesagent-fwid.
    ("src/core/utils/mcp_client.py", 1),
    ("src/core/oauth_retry.py", 1),
    # Geometric, but not outbound HTTP — so the seam is not where they belong,
    # and they stay listed with the reason in writing rather than exempted by a
    # path rule the next reader has to reverse-engineer.
    #
    # GAM forecasting readiness (NO_FORECAST_YET): a business-state poll.
    ("src/adapters/gam/managers/orders.py", 1),
    # GAM SOAP retries via the googleads client, which the seam does not carry.
    ("src/adapters/gam/utils/error_handler.py", 1),
    # PostgreSQL connection retry — not HTTP at all.
    ("src/core/database/database_session.py", 1),
}

FIX_HINT = (
    "Outbound retry backoff is decided once, in src/core/security/outbound_http.py "
    "(BR-RULE-029: 1s/2s/4s + jitter). Route the call through send/asend and let the "
    "seam schedule the retries instead of computing a delay here."
)


def _contains_power(node: ast.AST) -> bool:
    """True when the expression computes an exponentiation anywhere inside it.

    Walking the whole subtree — rather than matching ``BinOp(op=Pow)`` at the
    top — is what catches the forms that hide the power one layer down:
    ``base * 2**n``, ``min(5 * 2**attempt, 30)``, ``2**n + random.uniform(0, 1)``.
    """
    return any(isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Pow) for sub in ast.walk(node))


def _names_bound_to_a_power(tree: ast.AST) -> set[str]:
    """Names assigned an expression that contains an exponentiation.

    Almost no real backoff is written inline. Every one in this repo computes
    the delay first and sleeps the variable::

        backoff_time = 2**attempt
        time.sleep(backoff_time)

    A detector that only read the sleep argument would report none of them, so
    it would pass a codebase full of the disease. Binding is collected per
    module and order-insensitively: an assignment that reaches the sleep by any
    path still counts, and over-reporting here is the safe direction.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _contains_power(node.value):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign | ast.AugAssign) and node.value is not None and _contains_power(node.value):
            targets = [node.target]
        else:
            continue
        for target in targets:
            bound.update(sub.id for sub in ast.walk(target) if isinstance(sub, ast.Name))
    return bound


def _functions_returning_a_power(tree: ast.AST) -> set[str]:
    """Names of functions in this module whose body computes an exponentiation.

    One hop, deliberately. ``time.sleep(_backoff_seconds(attempt))`` — the seam's
    own form — hides the schedule behind a local helper; without this the seam
    itself would read as clean and the guard's exemption would prove nothing.
    Chasing further than one hop would need real call-graph analysis, which is
    not what a structural guard should grow into.
    """
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _contains_power(node)
    }


def find_call_site_backoff_violations(tree: ast.Module) -> list[int]:
    """Line numbers of sleeps whose duration is computed geometrically."""
    power_names = _names_bound_to_a_power(tree)
    power_functions = _functions_returning_a_power(tree)

    violations: list[int] = []
    for node in iter_call_expressions(tree, name=SLEEP_NAME):
        duration = node.args[0] if node.args else None
        if duration is None:
            continue
        referenced = {sub.id for sub in ast.walk(duration) if isinstance(sub, ast.Name)}
        called = {
            sub.func.id for sub in ast.walk(duration) if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
        }
        if _contains_power(duration) or (referenced & power_names) or (called & power_functions):
            violations.append(node.lineno)
    return violations


def _scan_src(exempt: frozenset[str] = EXEMPT_FILES) -> dict[str, int]:
    """Every module in src/ with a geometric sleep, and how many it has."""
    found: dict[str, int] = {}
    for path in src_python_files(repo_root()):
        key = rel(path)
        if key in exempt:
            continue
        count = len(find_call_site_backoff_violations(parse_module(path)))
        if count:
            found[key] = count
    return found


class TestNoCallSiteBackoff:
    """No module outside the seam computes its own exponential retry delay."""

    @pytest.mark.arch_guard
    def test_no_new_call_site_backoff(self):
        """The set of geometric sleeps in src/ matches the allowlist exactly.

        Fails on a new violation AND on a stale entry, so a migrated site must
        be removed from the list rather than left to rot.
        """
        assert_violations_match_allowlist(
            {(path, count) for path, count in _scan_src().items()},
            ALLOWLIST,
            fix_hint=FIX_HINT,
        )

    @pytest.mark.arch_guard
    def test_allowlist_only_shrinks(self):
        """The allowlist is a ratchet: its size is pinned to its seeded maximum.

        Update this number DOWNWARD when a site migrates. Raising it means a new
        call site grew its own schedule, which is the thing the guard exists to
        prevent.
        """
        assert len(ALLOWLIST) <= 9, (
            f"allowlist grew to {len(ALLOWLIST)} entries — a new call-site backoff was admitted. {FIX_HINT}"
        )


class TestGuardDetector:
    """The guard's own correctness, on synthetic sources.

    A guard that cannot fail is not a guard. None of these touch real source
    files — they feed the detector known-bad and known-good snippets directly.
    """

    @pytest.mark.arch_guard
    def test_detector_catches_known_bad(self):
        """Every geometric form is reported, including the ones that bury the power."""
        assert_detector_catches_ast_snippets(
            find_call_site_backoff_violations,
            snippets={
                "bare power": "import time\ntime.sleep(2**attempt)\n",
                "spaced power": "import time\ntime.sleep(2 ** attempt)\n",
                "base times power": "import time\ntime.sleep(base_delay * (2**attempt))\n",
                "power plus jitter": ("import random\nimport time\ntime.sleep(2**attempt + random.uniform(0, 1))\n"),
                "capped power": "import time\ntime.sleep(min(5 * (2**attempt), 30))\n",
                "async power": "import asyncio\n\n\nasync def f(n):\n    await asyncio.sleep(2**n)\n",
                "async base times power": (
                    "import asyncio\n\n\nasync def f(d, n):\n    await asyncio.sleep(d * (2**n))\n"
                ),
                "bare imported sleep": "from time import sleep\nsleep(2**attempt)\n",
                "multiplier power": "import time\ntime.sleep(base * multiplier**attempt)\n",
            },
        )

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("constant poll", "import time\ntime.sleep(0.5)\n"),
            ("named interval", "import time\ntime.sleep(poll_interval)\n"),
            (
                "module constant tick",
                "import asyncio\n\n\nasync def f():\n    await asyncio.sleep(SLEEP_INTERVAL_SECONDS)\n",
            ),
            ("division, not exponentiation", "import time\ntime.sleep(delay_ms / 1000)\n"),
            ("linear multiple", "import time\ntime.sleep(attempt * 2)\n"),
            ("header-driven wait", "import asyncio\n\n\nasync def f(r):\n    await asyncio.sleep(retry_after)\n"),
            ("power outside a sleep", "x = 2**attempt\nprint(x)\n"),
            ("seam usage", "from src.core.security.outbound_http import send\n\nr = send('https://x/', json={})\n"),
        ],
    )
    def test_detector_ignores_non_backoff(self, label, source):
        """A sleep that is not a geometric retry delay is not a violation."""
        assert find_call_site_backoff_violations(ast.parse(source)) == [], f"false positive on {label}"

    @pytest.mark.arch_guard
    def test_would_be_missed_by_a_text_scan(self):
        """The AST catches forms a ``2\\*\\*`` text grep would not.

        ``base * multiplier**attempt`` (src/core/oauth_retry.py:72) and
        ``time.sleep(pow(2, attempt))`` contain no literal ``2**``. A regex
        anchored on the common spelling would pass both; the guard reads shape.
        """
        assert find_call_site_backoff_violations(ast.parse("import time\ntime.sleep(base * multiplier**attempt)\n"))
        assert find_call_site_backoff_violations(ast.parse("import time\ntime.sleep(2 * 3 ** (attempt - 1))\n")), (
            "spacing variant missed"
        )

    @pytest.mark.arch_guard
    def test_seam_module_would_otherwise_be_flagged(self):
        """The seam is exempt by path, and is genuinely exempt — not merely clean.

        An exemption that excludes an already-clean file proves nothing. The seam
        really does compute a geometric delay; the scan skips it by path.
        """
        seam = repo_root() / SEAM_FILE
        assert find_call_site_backoff_violations(parse_module(seam)), (
            "seam no longer computes a geometric backoff — is the path stale?"
        )
        assert SEAM_FILE not in _scan_src()

    @pytest.mark.arch_guard
    def test_seam_is_the_only_exempt_path(self):
        """Exempting the seam changes exactly one file, and no other."""
        without_exemption = _scan_src(exempt=frozenset())
        difference = set(without_exemption) - set(_scan_src())
        assert difference == {SEAM_FILE}, f"unexpected exempt path(s): {sorted(difference - {SEAM_FILE})}"

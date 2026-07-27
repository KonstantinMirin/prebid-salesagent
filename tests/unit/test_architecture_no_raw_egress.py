"""Guard: No raw outbound HTTP outside the egress seam.

Every outbound HTTP request must go through ``src/core/security/outbound_http.py``.
That module is the only place address policy, TLS policy, redirect policy and
retry classification are decided; anywhere else, those decisions get re-made per
call site and one of them is always forgotten. That is exactly how SSRF kept
recurring here (#1589).

This is a structural guard, not a behavioural unit test: it scans the AST and
never exercises production code. Behaviour is graded by the seam's integration
tests and by the epic's BDD coverage.

What counts as a violation:

- Constructing or calling into ``requests`` / ``httpx`` / ``aiohttp``
  (``requests.post(...)``, ``requests.Session()``, ``httpx.Client(...)``, …)
- ``urlopen(...)``, however it is spelled
- Importing ``aiohttp`` at all — the epic drops the dependency, so there is no
  legitimate use, not even for exception types

What does NOT count, deliberately:

- Referencing an exception type without issuing a request, e.g.
  ``except requests.exceptions.Timeout:`` in ``src/core/context_manager.py``.
  Matching bare names instead of calls would flag that file, which issues
  nothing. Match on construction and call.

The allowlist is seeded at its maximum with the 17 modules in the #1589
inventory and only ever shrinks. Each entry pairs a module with its current
egress-call count, so adding a call to an already-allowlisted module fails too
rather than hiding behind the entry.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    assert_violations_match_allowlist,
    iter_call_expressions,
    parse_module,
    repo_root,
    src_python_files,
)

# The one module allowed to issue outbound HTTP.
SEAM_FILE = "src/core/security/outbound_http.py"
EXEMPT_FILES = frozenset({SEAM_FILE})

# Libraries that issue requests. A call on any of these is egress.
EGRESS_MODULES = frozenset({"requests", "httpx", "aiohttp"})

# Banned outright, imported or not: the epic drops this dependency entirely.
BANNED_IMPORTS = frozenset({"aiohttp"})

# Callable names that are egress wherever they appear.
EGRESS_FUNCTIONS = frozenset({"urlopen"})

# Pre-existing violations: (module_path, egress_call_count).
# Seeded at the maximum from the #1589 call-site inventory. It only shrinks —
# salesagent-c5b6 / cnkq / gstl empty it. Every entry has a FIXME(#1589) at the
# source location.
ALLOWLIST = {
    # Counterparty-supplied URL — the actual SSRF surface.
    ("src/core/webhook_delivery.py", 1),
    ("src/services/webhook_delivery_service.py", 1),
    ("src/services/order_approval_service.py", 1),
    ("src/core/creative_agent_registry.py", 1),
    ("src/core/property_list_resolver.py", 1),
    ("src/services/protocol_webhook_service.py", 1),
    # Operator-configured vendor endpoints.
    ("src/adapters/base_workflow.py", 1),
    ("src/adapters/gam_reporting_service.py", 1),
    ("src/adapters/kevel.py", 12),
    ("src/adapters/triton_digital.py", 14),
    ("src/adapters/xandr.py", 5),
    ("src/adapters/mock_ad_server.py", 1),
    ("src/adapters/broadstreet/client.py", 1),
    ("src/admin/blueprints/settings.py", 4),
    ("src/admin/blueprints/tenants.py", 1),
    # Operator OAuth to Google.
    ("src/admin/blueprints/auth.py", 1),
    # aiohttp import only (exception types) — the dependency itself is doomed.
    ("src/core/retry_utils.py", 1),
}

EXPECTED_VIOLATION_COUNT = len(ALLOWLIST)


def _call_is_egress(call: ast.Call) -> bool:
    """True when *call* issues an outbound request.

    Matches ``<lib>.<anything>(...)`` for the egress libraries and any callable
    named in :data:`EGRESS_FUNCTIONS`. A bare attribute reference with no call —
    an exception type in an ``except`` clause — is not matched, which is the
    whole point of keying on the Call node.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in EGRESS_FUNCTIONS
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in EGRESS_FUNCTIONS:
        return True
    root = func.value
    while isinstance(root, ast.Attribute):
        root = root.value
    return isinstance(root, ast.Name) and root.id in EGRESS_MODULES


def _import_is_banned(node: ast.AST) -> bool:
    """True when *node* imports a banned library, in either import form."""
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] in BANNED_IMPORTS for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return bool(node.module) and node.module.split(".")[0] in BANNED_IMPORTS
    return False


def find_raw_egress_violations(tree: ast.Module) -> list[int]:
    """Line numbers of raw-egress violations in *tree*.

    Shaped as a ``(tree) -> list[int]`` detector so it can be fed synthetic
    sources directly by the meta-tests.
    """
    linenos = [call.lineno for call in iter_call_expressions(tree) if _call_is_egress(call)]
    linenos.extend(node.lineno for node in ast.walk(tree) if _import_is_banned(node))
    return sorted(linenos)


def _scan_src(*, exempt: frozenset[str] = EXEMPT_FILES) -> dict[str, int]:
    """Map every offending module under src/ to its violation count.

    ``exempt`` is a parameter so a meta-test can run the same scan with nothing
    exempted and prove the exemption changes exactly one file.
    """
    repo = repo_root()
    counts: dict[str, int] = {}
    for path in src_python_files(repo):
        rel = path.relative_to(repo).as_posix()
        if rel in exempt:
            continue
        violations = find_raw_egress_violations(parse_module(path))
        if violations:
            counts[rel] = len(violations)
    return counts


class TestNoRawEgress:
    """Outbound HTTP is issued by the egress seam and nowhere else."""

    @pytest.mark.arch_guard
    def test_no_new_raw_egress(self):
        """A raw egress call in a module that had none fails immediately."""
        allowlisted = {module for module, _count in ALLOWLIST}
        new = {module: count for module, count in _scan_src().items() if module not in allowlisted}

        if new:
            lines = ["Raw outbound HTTP found outside the egress seam:", ""]
            lines.extend(f"  {module} ({count} call site(s))" for module, count in sorted(new.items()))
            lines += [
                "",
                f"Fix: route the request through {SEAM_FILE} — `send(...)` / `await asend(...)`.",
                "Do NOT add it to ALLOWLIST: the allowlist is seeded at its maximum and only shrinks.",
            ]
            raise AssertionError("\n".join(lines))

    @pytest.mark.arch_guard
    def test_allowlist_matches_reality(self):
        """Every allowlisted module still violates, with exactly the recorded count.

        Pairing the module with its count means a migration that removes only
        some of a module's call sites shows up as a stale entry rather than
        passing silently, and a new call added to an already-allowlisted module
        cannot hide behind the entry.
        """
        assert_violations_match_allowlist(
            set(_scan_src().items()),
            ALLOWLIST,
            fix_hint=(
                "Entries are (module, egress_call_count). After migrating a module, remove its "
                "entry; after migrating some of its call sites, lower the count. The allowlist "
                "never grows — see salesagent-c5b6 / cnkq / gstl, which empty it."
            ),
        )

    @pytest.mark.arch_guard
    def test_violation_count_matches(self):
        """Module count matches the #1589 inventory (catches undocumented additions)."""
        actual = len(_scan_src())
        assert actual == EXPECTED_VIOLATION_COUNT, (
            f"Expected {EXPECTED_VIOLATION_COUNT} allowlisted modules with raw egress, found {actual}. "
            "If you migrated one, remove it from ALLOWLIST. If you added one, DON'T — use the seam."
        )


class TestGuardDetector:
    """The guard's own correctness, on synthetic sources.

    A guard that cannot fail is not a guard. None of these touch real source
    files — they feed the detector known-bad and known-good snippets directly.
    """

    @pytest.mark.arch_guard
    def test_detector_catches_known_bad(self):
        """Every banned form is reported."""
        assert_detector_catches_ast_snippets(
            find_raw_egress_violations,
            snippets={
                "httpx.Client": "import httpx\nc = httpx.Client()\n",
                "httpx.AsyncClient": "import httpx\nc = httpx.AsyncClient()\n",
                "httpx module call": "import httpx\nr = httpx.post('https://x/', json={})\n",
                "requests verb": "import requests\nr = requests.post('https://x/', json={})\n",
                "requests.Session": "import requests\ns = requests.Session()\n",
                "requests.get in method": (
                    "import requests\n\n\nclass C:\n    def go(self):\n        return requests.get('https://x/')\n"
                ),
                "bare urlopen": "from urllib.request import urlopen\nr = urlopen('https://x/')\n",
                "dotted urlopen": "import urllib.request\nr = urllib.request.urlopen('https://x/')\n",
                "aiohttp import": "import aiohttp\n",
                "aiohttp from-import": "from aiohttp import ClientError\n",
                "aiohttp session": "import aiohttp\ns = aiohttp.ClientSession()\n",
            },
        )

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            (
                "requests exception type only",
                "import requests\n\ntry:\n    pass\nexcept requests.exceptions.Timeout:\n    pass\n",
            ),
            (
                "httpx exception type only",
                "import httpx\n\ntry:\n    pass\nexcept httpx.HTTPError:\n    pass\n",
            ),
            (
                "httpx type annotation only",
                "import httpx\n\n\ndef f(r: httpx.Response) -> int:\n    return r.status_code\n",
            ),
            (
                "unrelated session.get",
                "def f(session, model, pk):\n    return session.get(model, pk)\n",
            ),
            (
                "unrelated dict get",
                "def f(flask_session):\n    return flask_session.get('user', {})\n",
            ),
            (
                "seam usage",
                "from src.core.security.outbound_http import send\n\nr = send('https://x/', json={})\n",
            ),
        ],
    )
    def test_detector_ignores_non_egress(self, label, source):
        """Referencing a name without issuing a request is not a violation."""
        assert find_raw_egress_violations(ast.parse(source)) == [], f"false positive on {label}"

    @pytest.mark.arch_guard
    def test_context_manager_is_not_flagged(self):
        """The real exception-type-only module stays clean.

        ``src/core/context_manager.py`` imports requests and catches its
        exception types without ever issuing a request. It is the reason this
        guard keys on Call nodes, so it is asserted against the real file rather
        than only a synthetic stand-in.
        """
        path = repo_root() / "src" / "core" / "context_manager.py"
        assert find_raw_egress_violations(parse_module(path)) == []

    @pytest.mark.arch_guard
    def test_seam_module_would_otherwise_be_flagged(self):
        """The seam is exempt by path, and is genuinely exempt — not merely clean.

        An exemption that excludes an already-clean file proves nothing. The
        seam really does construct httpx clients; the scan skips it by path.
        """
        seam = repo_root() / SEAM_FILE
        assert find_raw_egress_violations(parse_module(seam)), "seam no longer issues egress — is the path stale?"
        assert SEAM_FILE not in _scan_src()

    @pytest.mark.arch_guard
    def test_seam_is_the_only_exempt_path(self):
        """Exempting the seam changes exactly one file, and no other.

        Run the same scan with nothing exempted: the difference against the
        real scan must be the seam alone. A second quietly-exempted module
        would show up here as an extra key.
        """
        without_exemption = _scan_src(exempt=frozenset())
        difference = set(without_exemption) - set(_scan_src())
        assert difference == {SEAM_FILE}, f"unexpected exempt path(s): {sorted(difference - {SEAM_FILE})}"

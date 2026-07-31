"""Guard: every fastmcp ``StreamableHttpTransport`` is built with the guarded client factory.

The MCP seam (``src/core/utils/mcp_client.py``) is EXEMPT from the "no SDK
construction outside the seam" scan in ``test_architecture_no_raw_egress.py``,
because constructing the transport is that seam's job. That exemption trusts the
seam to apply address policy — and for one release it did not: the transport was
built as ``StreamableHttpTransport(url=..., headers=...)`` with no
``httpx_client_factory``, so fastmcp fell back to
``mcp.shared._httpx_utils.create_mcp_http_client`` (``follow_redirects=True``,
no IP pin). A counterparty answering ``302 -> http://169.254.169.254/`` had the
redirect followed to the metadata endpoint (#1589 follow-up, salesagent-uzgw).

This guard closes the gap that exemption opened: wherever a
``StreamableHttpTransport`` is constructed under ``src/``, it MUST pass
``httpx_client_factory=guarded_client_factory(...)`` — the seam's factory that
pins the connection to the validated IP and refuses redirects. Passing no
factory (SDK default) or any OTHER factory is a violation: the whole point of
``guarded_client_factory`` is that redirect-refusal and the pin are not
negotiable, so a bespoke factory is exactly the escape this guard forbids.

Structural, not behavioural: it scans the AST and never issues a request. The
behaviour it protects is graded by
``tests/integration/test_mcp_client_egress.py``. There is no allowlist — the one
construction site is the seam's, and it is compliant; a second unguarded site
fails outright with nothing to add it to.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    iter_call_expressions,
    parse_module,
    repo_root,
    src_python_files,
)

# The transport whose default client follows redirects unpinned.
TRANSPORT_NAME = "StreamableHttpTransport"

# The one factory that makes the pin and the redirect-refusal non-negotiable.
GUARDED_FACTORY_NAME = "guarded_client_factory"


def _factory_kw_is_guarded(call: ast.Call) -> bool:
    """True when *call* passes ``httpx_client_factory=guarded_client_factory(...)``.

    Accepts both spellings of the callee — bare ``guarded_client_factory(url)``
    and dotted ``mod.guarded_client_factory(url)`` — because the value must be a
    CALL to that factory (it returns the per-URL closure fastmcp will invoke),
    never a bare reference or a different factory. Anything else — no keyword, a
    keyword whose value is ``create_mcp_http_client``, a hand-rolled lambda — is
    not guarded.
    """
    for kw in call.keywords:
        if kw.arg != "httpx_client_factory":
            continue
        value = kw.value
        if not isinstance(value, ast.Call):
            return False
        func = value.func
        if isinstance(func, ast.Name):
            return func.id == GUARDED_FACTORY_NAME
        if isinstance(func, ast.Attribute):
            return func.attr == GUARDED_FACTORY_NAME
        return False
    return False


def _call_is_transport_construction(call: ast.Call) -> bool:
    """True when *call* constructs a ``StreamableHttpTransport`` (bare or dotted).

    Keys on the Call node, never a bare Name, so an import or a type annotation
    naming the class is not matched — only actual construction is.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == TRANSPORT_NAME
    if isinstance(func, ast.Attribute):
        return func.attr == TRANSPORT_NAME
    return False


def find_unguarded_transport_violations(tree: ast.Module) -> list[int]:
    """Line numbers of ``StreamableHttpTransport(...)`` built without the guarded factory.

    Shaped as a ``(tree) -> list[int]`` detector so the meta-tests can feed it
    synthetic sources directly, matching the other architecture guards.
    """
    return sorted(
        call.lineno
        for call in iter_call_expressions(tree)
        if _call_is_transport_construction(call) and not _factory_kw_is_guarded(call)
    )


def _scan_src() -> dict[str, int]:
    """Map every module under src/ with an unguarded transport to its count."""
    repo = repo_root()
    counts: dict[str, int] = {}
    for path in src_python_files(repo):
        violations = find_unguarded_transport_violations(parse_module(path))
        if violations:
            counts[path.relative_to(repo).as_posix()] = len(violations)
    return counts


class TestEveryStreamableTransportIsGuarded:
    """No ``StreamableHttpTransport`` under src/ is built without the guarded factory."""

    @pytest.mark.arch_guard
    def test_no_unguarded_transport(self):
        """Any StreamableHttpTransport missing httpx_client_factory=guarded_client_factory(...) fails."""
        offenders = _scan_src()

        if offenders:
            lines = ["StreamableHttpTransport built without the guarded client factory:", ""]
            lines.extend(f"  {module} ({count} site(s))" for module, count in sorted(offenders.items()))
            lines += [
                "",
                "Fix: pass httpx_client_factory=guarded_client_factory(url) from "
                "src/core/security/outbound_http.py. Without it fastmcp uses "
                "create_mcp_http_client (follow_redirects=True, no IP pin) — the redirect "
                "bypass salesagent-uzgw closed. There is no allowlist.",
            ]
            raise AssertionError("\n".join(lines))

    @pytest.mark.arch_guard
    def test_the_real_seam_is_compliant_not_merely_absent(self):
        """The MCP seam really constructs a transport, and it is guarded.

        A green scan could mean "compliant" or "no transport anywhere". This
        pins the former: the seam DOES construct a StreamableHttpTransport, and
        that construction carries the guarded factory — so the scan is grading a
        real site, not an empty tree.
        """
        seam = repo_root() / "src" / "core" / "utils" / "mcp_client.py"
        tree = parse_module(seam)
        constructions = [c for c in iter_call_expressions(tree) if _call_is_transport_construction(c)]
        assert constructions, "the MCP seam no longer constructs a StreamableHttpTransport — is the path stale?"
        assert find_unguarded_transport_violations(tree) == [], (
            "the MCP seam constructs a StreamableHttpTransport without the guarded factory"
        )


class TestGuardDetector:
    """The detector's own correctness, on synthetic sources — a guard that cannot fail is not a guard."""

    @pytest.mark.arch_guard
    def test_detector_catches_known_bad(self):
        """Every unguarded construction form is reported."""
        assert_detector_catches_ast_snippets(
            find_unguarded_transport_violations,
            snippets={
                "no factory at all (the original bug)": (
                    "from fastmcp.client.transports import StreamableHttpTransport\n"
                    "t = StreamableHttpTransport(url='https://x/mcp', headers={})\n"
                ),
                "a different, non-guarded factory": (
                    "from fastmcp.client.transports import StreamableHttpTransport\n"
                    "from mcp.shared._httpx_utils import create_mcp_http_client\n"
                    "t = StreamableHttpTransport(url='https://x/mcp', httpx_client_factory=create_mcp_http_client)\n"
                ),
                "a hand-rolled lambda factory": (
                    "import httpx\n"
                    "from fastmcp.client.transports import StreamableHttpTransport\n"
                    "t = StreamableHttpTransport(url='https://x/mcp', httpx_client_factory=lambda **k: httpx.AsyncClient())\n"
                ),
                "guarded factory PASSED BY REFERENCE, not called": (
                    "from fastmcp.client.transports import StreamableHttpTransport\n"
                    "from src.core.security.outbound_http import guarded_client_factory\n"
                    "t = StreamableHttpTransport(url='https://x/mcp', httpx_client_factory=guarded_client_factory)\n"
                ),
                "dotted spelling, no factory": (
                    "import fastmcp.client.transports as tr\nt = tr.StreamableHttpTransport(url='https://x/mcp')\n"
                ),
                "construction inside a retry loop": (
                    "from fastmcp.client.transports import StreamableHttpTransport\n\n\n"
                    "def connect(urls):\n"
                    "    for u in urls:\n"
                    "        t = StreamableHttpTransport(url=u, headers={})\n"
                ),
            },
        )

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            (
                "guarded factory, bare spelling",
                "from fastmcp.client.transports import StreamableHttpTransport\n"
                "from src.core.security.outbound_http import guarded_client_factory\n"
                "t = StreamableHttpTransport(url='https://x/mcp', headers={}, "
                "httpx_client_factory=guarded_client_factory('https://x/mcp'))\n",
            ),
            (
                "guarded factory, dotted spelling",
                "from fastmcp.client.transports import StreamableHttpTransport\n"
                "from src.core.security import outbound_http\n"
                "t = StreamableHttpTransport(url=u, httpx_client_factory=outbound_http.guarded_client_factory(u))\n",
            ),
            (
                "import alone, no construction",
                "from fastmcp.client.transports import StreamableHttpTransport\n",
            ),
            (
                "type annotation only",
                "from fastmcp.client.transports import StreamableHttpTransport\n\n\n"
                "def f(t: StreamableHttpTransport) -> None:\n    return None\n",
            ),
            (
                "bare name reference, no call",
                "from fastmcp.client.transports import StreamableHttpTransport\n\nalias = StreamableHttpTransport\n",
            ),
        ],
    )
    def test_detector_ignores_guarded_and_non_constructions(self, label, source):
        """A guarded construction, or a mere reference, is not a violation."""
        assert find_unguarded_transport_violations(ast.parse(source)) == [], f"false positive on {label}"

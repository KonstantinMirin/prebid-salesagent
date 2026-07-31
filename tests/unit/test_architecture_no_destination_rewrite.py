"""Guard: no code under src/ rebuilds a URL or rewrites its destination fields.

Routing every request through the egress seam
(``src/core/security/outbound_http.py``) is not enough if code in front of the
seam may still change WHERE the request goes. A host rewrite ahead of ``asend``
means the URL the seam validates and pins is not the URL the caller supplied —
the latent SSRF shape the #1589 follow-up removed
(``_normalize_localhost_for_docker`` in ``protocol_webhook_service.py`` rewrote
``localhost`` to ``host.docker.internal`` before delivery, failing open on
parse errors).

The scan flags URL reconstruction anywhere under ``src/``: ``urlunparse(...)``
/ ``urlunsplit(...)`` calls and ``._replace(netloc=...)`` /
``._replace(scheme=...)`` (#1589). Nothing is exempt — not even the seam:
address policy there is delegated to ``adcp.signing``, which pins the resolved
IP without ever rewriting the URL, so a netloc rewrite inside the seam would be
just as wrong. The scan set is empty and there is no allowlist to grow.

Scope, stated precisely: this detector matches the stdlib REASSEMBLY spellings.
It deliberately does not try to catch every way a destination can change hands
— ``src/core/creative_agent_registry.py``'s ``_connection_agent_url`` swaps the
transport URL for the env-configured ``CREATIVE_AGENT_URL`` alias by returning
a different STRING (sanctioned, salesagent-9qe2), which no spelling scan can
distinguish from hostile code statically. That swap's bounds are graded
behaviourally instead: ``tests/unit/test_creative_agent_connection_alias.py``
asserts it applies only to the public default agent, only when the env var is
set, and that identity/cache-key URLs stay byte-identical.

Sibling guards for the other egress properties: the raw-lib and SDK-client
import bans formerly in ``test_architecture_no_raw_egress.py`` now live in
``ruff-egress.toml`` (TID251, run over ``src/`` by ``make quality-ci``), with
``tests/unit/test_ruff_egress_bans.py`` as their executable non-vacuity proof;
the seam's own construction is graded by
``tests/integration/test_mcp_client_egress.py`` over a real socket.
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

# The egress seam — scanned like everything else (see module docstring).
SEAM_FILE = "src/core/security/outbound_http.py"

# Rebuilding a URL from parts is how a destination gets rewritten in front of
# the seam. Both spellings of the stdlib reassembler are banned under src/.
URL_REBUILD_FUNCTIONS = frozenset({"urlunparse", "urlunsplit"})

# ``ParseResult._replace`` keywords that change WHERE a request goes. ``path``
# / ``query`` / ``fragment`` rewrites are content, not destination, and are
# deliberately not matched.
DESTINATION_REPLACE_KEYWORDS = frozenset({"netloc", "scheme"})


def _call_is_destination_rewrite(call: ast.Call) -> bool:
    """True when *call* rebuilds a URL or replaces its destination fields.

    Matches ``urlunparse(...)`` / ``urlunsplit(...)`` in both bare and dotted
    spellings, and ``<expr>._replace(netloc=...)`` / ``<expr>._replace(scheme=...)``.
    A ``._replace`` without a destination keyword (e.g. on a datetime or a
    NamedTuple that has nothing to do with URLs) is not matched.
    """
    func = call.func
    if isinstance(func, ast.Name) and func.id in URL_REBUILD_FUNCTIONS:
        return True
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in URL_REBUILD_FUNCTIONS:
        return True
    if func.attr == "_replace":
        return any(kw.arg in DESTINATION_REPLACE_KEYWORDS for kw in call.keywords)
    return False


def find_destination_rewrite_violations(tree: ast.Module) -> list[int]:
    """Line numbers of destination-rewrite violations in *tree*.

    Shaped as a ``(tree) -> list[int]`` detector so the meta-tests can feed it
    synthetic sources directly.
    """
    return sorted(call.lineno for call in iter_call_expressions(tree) if _call_is_destination_rewrite(call))


def _scan_src() -> dict[str, int]:
    """Map every offending module under src/ to its violation count. No exemptions."""
    repo = repo_root()
    counts: dict[str, int] = {}
    for path in src_python_files(repo):
        violations = find_destination_rewrite_violations(parse_module(path))
        if violations:
            counts[path.relative_to(repo).as_posix()] = len(violations)
    return counts


class TestNoDestinationRewrite:
    """No code under src/ rebuilds a URL or rewrites its destination fields.

    There is no allowlist and no exemption: the scan set was emptied by the
    #1589 follow-up and stays empty. Even the seam is scanned — it pins
    addresses via ``adcp.signing`` without rewriting URLs.
    """

    @pytest.mark.arch_guard
    def test_no_destination_rewrites_anywhere(self):
        """Any urlunparse/urlunsplit or _replace(netloc/scheme=...) under src/ fails."""
        offenders = _scan_src()

        if offenders:
            lines = ["URL destination rewrite found under src/:", ""]
            lines.extend(f"  {module} ({count} call site(s))" for module, count in sorted(offenders.items()))
            lines += [
                "",
                "The URL a caller supplies must reach the egress seam byte-for-byte; nothing may",
                "rebuild it or swap its netloc/scheme in front of (or inside) the seam. If a test",
                "stack needs a reachable callback host, register a reachable hostname instead",
                "(ADCP_WEBHOOK_HOST — see tests/e2e/_webhook_capture.py). There is no allowlist.",
            ]
            raise AssertionError("\n".join(lines))


class TestDestinationRewriteDetector:
    """The destination-rewrite detector's own correctness, on synthetic sources."""

    @pytest.mark.arch_guard
    def test_detector_catches_known_bad(self):
        """Every destination-rewrite form is reported."""
        assert_detector_catches_ast_snippets(
            find_destination_rewrite_violations,
            snippets={
                "bare urlunparse": (
                    "from urllib.parse import urlparse, urlunparse\n"
                    "u = urlunparse(urlparse(url)._replace(netloc='evil'))\n"
                ),
                "dotted urlunparse": "import urllib.parse\nu = urllib.parse.urlunparse(parts)\n",
                "bare urlunsplit": "from urllib.parse import urlunsplit\nu = urlunsplit(parts)\n",
                "netloc replace alone": (
                    "from urllib.parse import urlparse\np = urlparse(url)._replace(netloc='host.docker.internal')\n"
                ),
                "scheme replace alone": (
                    "from urllib.parse import urlparse\np = urlparse(url)._replace(scheme='http')\n"
                ),
                "the removed rewrite's exact shape": (
                    "from urllib.parse import urlparse, urlunparse\n\n\n"
                    "def _normalize(url):\n"
                    "    parsed = urlparse(url)\n"
                    "    return urlunparse(parsed._replace(netloc='host.docker.internal'))\n"
                ),
            },
        )

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            (
                "urlparse alone",
                "from urllib.parse import urlparse\n\nhost = urlparse(url).hostname\n",
            ),
            (
                "_replace without destination keyword",
                "from datetime import datetime\n\nd = datetime.now().replace(microsecond=0)\n",
            ),
            (
                "_replace on a non-URL namedtuple",
                "def f(point):\n    return point._replace(x=1, y=2)\n",
            ),
            (
                "_replace(path=...) is content, not destination",
                "from urllib.parse import urlparse\n\np = urlparse(url)._replace(path='/new', query='')\n",
            ),
            (
                "str.replace on a URL",
                "def f(url):\n    return url.replace('http://', 'https://')\n",
            ),
            (
                "bare name reference, no call",
                "from urllib.parse import urlunparse\n\nalias = urlunparse\n",
            ),
        ],
    )
    def test_detector_ignores_non_rewrites(self, label, source):
        """Parsing a URL or replacing non-destination fields is not a violation."""
        assert find_destination_rewrite_violations(ast.parse(source)) == [], f"false positive on {label}"

    @pytest.mark.arch_guard
    def test_seam_is_scanned_and_clean(self):
        """The seam is NOT exempt from this scan, and is clean.

        The import bans in ``ruff-egress.toml`` exempt the seam by noqa because
        issuing egress is its job. Rewriting destinations is nobody's job —
        address policy lives in ``adcp.signing``, which pins IPs without
        touching the URL — so this asserts the seam passes the scan it is
        subject to.
        """
        seam = repo_root() / SEAM_FILE
        assert find_destination_rewrite_violations(parse_module(seam)) == []

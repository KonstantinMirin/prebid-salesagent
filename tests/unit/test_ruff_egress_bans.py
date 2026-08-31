"""Executable-exemption meta-test for the egress import bans.

The egress import bans live in a SECOND ruff config (``ruff-egress.toml`` at
the repo root, run as its own ``make quality`` line:
``uv run ruff check --config ruff-egress.toml --no-respect-gitignore
src/ scripts/``). They replace the deleted
AST scans #1 (raw network libs) and #2 (SDK/MCP client constructors) of the
old ``test_architecture_no_raw_egress.py`` — see GH #1589 and CLAUDE.md
pattern #9: all outbound HTTP goes through ``src/core/security/outbound_http.py``.

This module is the ban table's non-vacuity proof, replacing the deleted
guards' meta-tests. Five cases:

(a) POSITIVE  — every banned entry fires (TID251 in ruff's OUTPUT, not just
    exit status) for every resolving spelling: direct import, aliased import,
    dotted-attribute use, and the bypass re-export paths
    (``fastmcp.client`` / ``fastmcp.client.transports.http`` /
    ``adcp.client``) that a single-path ban would let through.
(b) NEGATIVE  — a clean snippet yields no TID251 (and the config loads).
(c) NON-VACUITY per exemption — every recorded marker line is a real violation
    site, and no file carries a suppression the record does not know about.
(d) CLOSED SET — the set of files with a violation absent all suppressions
    equals the recorded constant; a new exemption fails until recorded here.
(e) DERIVED OBLIGATION — every suppressed import site's own re-export path
    (``<module>.<name>``) is itself banned, so a seam cannot leak the name it
    was sanctioned to import.

Cases (c) and (d) do NOT parse suppressions themselves. They ask ruff, via
``--ignore-noqa``, what the violation set V is absent ALL suppressions, and
compare V against the recorded constants. This is the whole point: a regex
that mirrors ruff's noqa syntax mirrors it INCOMPLETELY — ``# ruff: noqa``,
bare ``# noqa``, ``# noqa:TID251`` with no space, and ``# flake8: noqa`` all
evaded the previous form (GH #1802 round-3 finding 2a). V is spelling-blind by
construction, because ruff computes it.

``--ignore-noqa`` suppresses only *inline* suppressions; it does NOT bypass
``[lint.per-file-ignores]``, so the ANN401 negated-glob scoping in the config
still holds (verified).

The scan set is ``_SCAN_DIRS`` HERE, not the Makefile line — so reverting the
Makefile to ``src/``-only does not hide a ``scripts/`` violation from this
proof. ``--no-respect-gitignore`` is likewise load-bearing: ruff's walk honors
``.gitignore``, which hid a git-tracked ``scripts/`` file from the scan.

Every case shells out to the real ruff with the real config — the exemptions
are executable, never prose (Core Invariant of GH #1589).
"""

from __future__ import annotations

import ast
import functools
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tests.unit._architecture_helpers import repo_root

# Repo-root-relative path of the src-scoped egress ban config.
EGRESS_CONFIG = "ruff-egress.toml"

# Path a synthetic snippet is presented under (inside the scanned tree —
# tests/ is deliberately out of scope; tests import httpx/requests freely).
_SYNTHETIC_PATH = "src/core/_synthetic_egress_probe.py"

# The scan set. This constant, not the Makefile line, is the authority: a
# revert of Makefile:18 to src/-only still leaves any scripts/ violation inside
# V, so case (d) catches it. Mirrors of a gate drift; a gate that owns its own
# scope does not.
_SCAN_DIRS: tuple[str, ...] = ("src/", "scripts/")

# Path a synthetic snippet is presented under to prove the bans are not
# path-scoped: banned-api entries apply wherever the config is applied.
_SYNTHETIC_SCRIPTS_PATH = "scripts/_synthetic_egress_probe.py"

_NOQA_MARKER = "# noqa: TID251"

# The same three properties, for the second rule this config carries. ANN401
# bans `Any` in a signature across the outbound chain (GH #1802):
# `Any` is an opt-out of type checking, assignable to and
# from everything, so it is the one value the seam's own JsonValue signatures
# cannot make unrepresentable — a NEW forwarder declaring `json: Any` and
# passing it straight to send() type-checks clean under mypy.
_ANY_NOQA_MARKER = "# noqa: ANN401"


# The two adcp SDK client constructions were removed (GH #1589), so neither
# file constructs one anymore — the set SHRANK from 4 to 2, per this module's
# own non-vacuity contract (case c/d): removing a noqa without a live
# violation is required, not merely permitted. It does not grow beyond the
# two seam definitions.
#
# src/core/security/egress/policy.py was ADDED (3 -> the set now carries this
# third entry) once ``ipaddress`` joined the module bans below: the egress
# package is the one sanctioned site for address classification (GH #1589),
# so its own ``import ipaddress`` line-scoped noqa is the live violation case
# (c) proves. The set grows here by exactly this one entry, not by a fourth.
# ---------------------------------------------------------------------------
SEAM_FILES: frozenset[str] = frozenset(
    {
        "src/core/security/outbound_http.py",
        "src/core/utils/mcp_client.py",
        "src/core/security/egress/policy.py",
    }
)

# ---------------------------------------------------------------------------
# scripts/ exemptions — a SHRINK-ONLY debt list, deliberately NOT SEAM_FILES.
#
# SEAM_FILES is a floor: a seam architecture must have sanctioned importers of
# the thing it wraps, so that set never empties. These two mean the opposite:
# "recorded debt, retire me". They exist because `scripts/` used to be outside
# the scan entirely — an unbounded, unscanned implicit exemption. Scanning it
# with two recorded, line-scoped, liveness-proven rows SHRINKS the exempt
# surface; it does not grow an allowlist (GH #1802 round-3 F2).
#
#   scripts/dev/gen_test_tls.py     — `import ipaddress` builds certificate IP
#                                     SANs. Not address classification, so the
#                                     egress package is not where it belongs.
#   scripts/ops/sync_all_tenants.py — `import requests` for an ops-plane
#                                     self-call to a hardcoded loopback URL.
#                                     The seam's policy refuses loopback BY
#                                     DESIGN, so routing this through the seam
#                                     would be wrong, not safer. Retiring this
#                                     row means an in-process invocation.
#
# Entries leave one at a time, with evidence. They must not grow.
# ---------------------------------------------------------------------------
SCRIPT_EXEMPT_FILES: frozenset[str] = frozenset(
    {
        "scripts/dev/gen_test_tls.py",
        "scripts/ops/sync_all_tenants.py",
    }
)

# Module-level bans: the bare import fires, so verb enumeration is moot.
_MODULE_BANS: tuple[str, ...] = (
    "httpx",
    "requests",
    "aiohttp",
    "urllib.request",
    "ipaddress",
    # The HTTP stacks under and beside httpx/requests. httpx2 is ONE CHARACTER
    # from the banned spelling, and both httpx2 and httpcore2 are installed
    # transitively (via genai-prices) and importable (GH #1802 round-3 F1).
    "httpcore",
    "urllib3",
    "http.client",
    "httpx2",
    "httpcore2",
)

# Symbol bans: every resolving import path per symbol. The non-first entries
# are the bypass re-export spellings a single-path ban would miss
# (fastmcp.client re-exports the transports; adcp.client is the classes'
# real defining module).
_SYMBOL_BAN_PATHS: dict[str, tuple[str, ...]] = {
    "StreamableHttpTransport": (
        "fastmcp.client.transports",
        "fastmcp.client",
        "fastmcp.client.transports.http",
    ),
    "SSETransport": (
        "fastmcp.client.transports",
        "fastmcp.client",
        "fastmcp.client.transports.sse",
    ),
    "ADCPClient": ("adcp", "adcp.client"),
    "ADCPMultiAgentClient": ("adcp", "adcp.client"),
    "get_adcp_signed_headers_for_webhook": ("adcp.webhooks", "adcp"),
    # Resolve-then-check is a TOCTOU the egress package does not use (adcp.signing
    # pins the resolved IP in one step) — one path, no bypass re-export exists.
    "gethostbyname": ("socket",),
    # `Client(url)` INFERS an un-pinned StreamableHttpTransport from a bare URL
    # (verified at runtime): banning the transports without banning the
    # constructor that manufactures one leaves the hole open. The MCP seam is
    # the sanctioned importer and passes transport= only. The seam's own module
    # is the fourth path because importing FROM the seam re-exports the name.
    "Client": ("fastmcp", "fastmcp.client", "fastmcp.client.client", "src.core.utils.mcp_client"),
    # The seam re-exports: `from src.core.security.outbound_http import httpx`
    # resolves to the real module and used to pass clean (round-3 finding 2b).
    "httpx": ("src.core.security.outbound_http",),
    "ipaddress": ("src.core.security.egress.policy",),
}

# Note: the `httpx` and `ipaddress` keys above double as module names in
# `_MODULE_BANS`. That is not a duplicate — case (a) reads this dict as
# {symbol: paths}, so those two entries prove the SEAM RE-EXPORT ban fires
# (`from src.core.security.outbound_http import httpx`), while `_MODULE_BANS`
# proves the bare-module ban fires. Different bans, different spellings.


def _run_ruff_egress(source: str, stdin_filename: str) -> subprocess.CompletedProcess[str]:
    """Run ruff over *source* as *stdin_filename* with the egress ban config.

    The single helper every case goes through (DRY): same interpreter
    (``sys.executable -m ruff``), same config, same output format — so a
    passing case proves the REAL gate line would fire, not a lookalike.
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            EGRESS_CONFIG,
            "--stdin-filename",
            stdin_filename,
            "--output-format",
            "concise",
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        cwd=repo_root(),
        check=False,
    )


def _assert_rule_fires(source: str, stdin_filename: str, label: str, code: str) -> None:
    """One assertion for every rule this config carries — see _assert_tid251_fires."""
    proc = _run_ruff_egress(source, stdin_filename)
    assert code in proc.stdout, (
        f"[{label}] expected a {code} violation from ruff for:\n{source}\n"
        f"--- ruff stdout ---\n{proc.stdout}\n--- ruff stderr ---\n{proc.stderr}"
    )


def _assert_tid251_fires(source: str, stdin_filename: str, label: str) -> None:
    _assert_rule_fires(source, stdin_filename, label, "TID251")


def _module_ban_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for module in _MODULE_BANS:
        alias = "_" + module.replace(".", "_")
        cases.append((f"{module}::direct-import", f"import {module}\n"))
        cases.append((f"{module}::aliased-import", f"import {module} as {alias}\n"))
        cases.append((f"{module}::from-import", f"from {module} import get\n"))
    return cases


def _symbol_ban_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for symbol, import_paths in _SYMBOL_BAN_PATHS.items():
        for path in import_paths:
            cases.append((f"{symbol}::from-{path}", f"from {path} import {symbol}\n"))
        canonical = import_paths[0]
        cases.append((f"{symbol}::aliased-import", f"from {canonical} import {symbol} as _aliased\n"))
        cases.append(
            (
                f"{symbol}::dotted-attribute",
                f"import {canonical} as _mod\n_mod.{symbol}('https://example.com')\n",
            )
        )
    return cases


_POSITIVE_CASES: list[tuple[str, str]] = _module_ban_cases() + _symbol_ban_cases()


class TestEgressBansFire:
    """(a) Every banned entry yields TID251, in every resolving spelling."""

    @pytest.mark.parametrize(
        ("label", "snippet"),
        _POSITIVE_CASES,
        ids=[label for label, _ in _POSITIVE_CASES],
    )
    def test_banned_spelling_yields_tid251(self, label: str, snippet: str) -> None:
        _assert_tid251_fires(snippet, _SYNTHETIC_PATH, label)

    def test_bans_are_not_path_scoped_to_src(self) -> None:
        """The same snippet fires under `scripts/`, which joined the scan set.

        banned-api entries are not path-scoped, so this is one probe, not one
        per entry. It pins the half of round-3 F2 that `_SCAN_DIRS` does not:
        the config applying wherever the gate points it.
        """
        _assert_tid251_fires("import requests\n", _SYNTHETIC_SCRIPTS_PATH, "scripts-scope")


class TestCleanCodePasses:
    """(b) The seam's own public surface is not flagged — and the config loads."""

    def test_clean_snippet_yields_no_tid251(self) -> None:
        clean = "from src.core.security.outbound_http import asend\n"
        proc = _run_ruff_egress(clean, _SYNTHETIC_PATH)
        # returncode == 0 also proves the config parsed — a missing/broken
        # ruff-egress.toml must fail HERE, not pass vacuously via empty output.
        assert proc.returncode == 0, (
            f"ruff did not run cleanly (config missing/broken?):\n"
            f"--- ruff stdout ---\n{proc.stdout}\n--- ruff stderr ---\n{proc.stderr}"
        )
        assert "TID251" not in proc.stdout, f"clean snippet was flagged:\n{proc.stdout}"


# ---------------------------------------------------------------------------
# The derived violation set V.
#
# Cases (c), (d) and (e) all rest on ONE question, asked of ruff rather than
# answered by a regex: which (file, line) pairs violate *code* when EVERY
# inline suppression is ignored? A hand-written mirror of ruff's noqa syntax
# is the thing this module used to carry, and it missed four spellings
# (GH #1802 round-3 finding 2a). `--ignore-noqa` cannot miss one.
# ---------------------------------------------------------------------------


def _scanned_python_files() -> list[Path]:
    """Every .py file ruff sees under `_SCAN_DIRS` (gitignore deliberately ignored)."""
    repo = repo_root()
    files: list[Path] = []
    for scan_dir in _SCAN_DIRS:
        files.extend((repo / scan_dir.rstrip("/")).rglob("*.py"))
    return sorted(files)


@functools.cache
def _violation_sites_ignoring_noqa(code: str) -> frozenset[tuple[str, int]]:
    """Every ``(relpath, lineno)`` where *code* fires absent ALL suppressions.

    One ruff invocation per rule, over the real tree, with the real config.
    ``--no-respect-gitignore`` is required: ruff's walk honors ``.gitignore``,
    which hid the git-tracked ``scripts/ops/sync_all_tenants.py`` from the scan
    (round-3 F2). Cached — the two cases below ask the same question.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            EGRESS_CONFIG,
            "--ignore-noqa",
            "--no-respect-gitignore",
            "--output-format",
            "concise",
            *_SCAN_DIRS,
        ],
        capture_output=True,
        text=True,
        cwd=repo_root(),
        check=False,
    )
    assert proc.returncode in (0, 1), (
        f"ruff did not run (config missing/broken?): rc={proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    sites: set[tuple[str, int]] = set()
    for line in proc.stdout.splitlines():
        # concise format: path:line:col: CODE message
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        rel_path, lineno, _col, rest = parts
        if not lineno.isdigit() or rest.strip().split(" ", 1)[0] != code:
            continue
        sites.add((rel_path, int(lineno)))
    return frozenset(sites)


def _marker_lines(marker: str) -> list[tuple[str, int]]:
    """Every ``(relpath, 1-based lineno)`` under `_SCAN_DIRS` carrying *marker*.

    The canonical spelling only. Its incompleteness is now HARMLESS: an
    exemption written in any other spelling still appears in V, so the count
    equality below breaks. The marker exists to locate what the record claims,
    not to define what a suppression is.
    """
    repo = repo_root()
    sites: list[tuple[str, int]] = []
    for path in _scanned_python_files():
        rel = str(path.relative_to(repo))
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if marker in line:
                sites.append((rel, lineno))
    return sorted(sites)


# ---------------------------------------------------------------------------
# ANN401's exempt set — an allowlist that SHRINKS, unlike SEAM_FILES's floor.
#
# SEAM_FILES is a floor: a seam architecture must have sanctioned importers of
# the thing it wraps, so that set never empties. This set is the opposite — it
# records `Any` that PREDATES the ban, in three groups, none of which is a
# payload parameter on the outbound chain (pldmk.23 removed the last of those):
#
#   xandr.py                     — 11 `**kwargs: Any` response stubs that absorb
#                                  arbitrary vendor fields by setattr. No value
#                                  type exists to state; retiring them means a
#                                  typed response model, not an annotation.
#   *.py `-> Any` decode returns — OutboundResult.json() and its readers. The
#                                  honest type is JsonValue; narrowing it
#                                  cascades to every response.json()[...] reader
#                                  in the adapters, so it is its own change.
#   logging/serializer/handles   — genuinely dynamic inputs; a log sanitizer
#                                  legitimately accepts any object.
#
# Every entry is liveness-proven by case (c). Entries leave this set as
# pldmk.37's follow-ups land. It must not grow — a new file needing `Any` in a
# signature under these two directories is the very thing the ban refuses.
# ---------------------------------------------------------------------------
ANY_EXEMPT_FILES: frozenset[str] = frozenset(
    {
        "src/adapters/base_inventory.py",
        "src/adapters/broadstreet/client.py",
        "src/adapters/gam/managers/targeting.py",
        "src/adapters/gam/utils/error_handler.py",
        "src/adapters/gam/utils/formatters.py",
        "src/adapters/gam/utils/logging.py",
        "src/adapters/gam_orders_discovery.py",
        "src/adapters/xandr.py",
        "src/core/security/egress/response.py",
        "src/core/security/webhook_strict_json.py",
    }
)

# One parametrization for both rules this config carries — the DRY invariant.
# `recorded` is the file set the rule's exemptions are closed to.
_RULES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("TID251", _NOQA_MARKER, SEAM_FILES | SCRIPT_EXEMPT_FILES),
    ("ANN401", _ANY_NOQA_MARKER, ANY_EXEMPT_FILES),
)
_RULE_IDS = [code for code, _, _ in _RULES]

# The two liveness cases below compare V against the MARKERS, not against the
# recorded file set, so they take a projection rather than an unread third
# parameter. Derived from `_RULES` — one source, no second list to drift.
_RULE_MARKERS: tuple[tuple[str, str], ...] = tuple((code, marker) for code, marker, _ in _RULES)


class TestExemptionsAreExecutable:
    """(c) Every suppression is RECORDED, and every recorded marker is LIVE."""

    @pytest.mark.parametrize(("code", "marker"), _RULE_MARKERS, ids=_RULE_IDS)
    def test_no_dead_marker(self, code: str, marker: str) -> None:
        """A canonical marker on a line that does not violate is dead prose."""
        violations = _violation_sites_ignoring_noqa(code)
        dead = [site for site in _marker_lines(marker) if site not in violations]
        assert not dead, (
            f"{len(dead)} '{marker}' marker(s) sit on lines that do NOT violate {code} "
            f"with all suppressions ignored — the exemption is DEAD prose, not a live "
            f"exemption. Delete it.\n  " + "\n  ".join(f"{f}:{n}" for f, n in dead)
        )

    @pytest.mark.parametrize(("code", "marker"), _RULE_MARKERS, ids=_RULE_IDS)
    def test_no_unrecorded_suppression(self, code: str, marker: str) -> None:
        """Per file, ruff's violation count equals the canonical-marker count.

        This is what retires the noqa regex. A second suppression in a recorded
        file — written ``# ruff: noqa``, bare ``# noqa``, ``# noqa:TID251``, or
        ``# flake8: noqa``, none of which the marker matches — still lands in V
        and breaks this equality. So does a RAW, unsuppressed violation that
        someone added without a marker: the file's V-count exceeds its marker
        count either way.
        """
        violations = _violation_sites_ignoring_noqa(code)
        markers = _marker_lines(marker)
        by_file_v: dict[str, int] = {}
        for rel_path, _lineno in violations:
            by_file_v[rel_path] = by_file_v.get(rel_path, 0) + 1
        by_file_m: dict[str, int] = {}
        for rel_path, _lineno in markers:
            by_file_m[rel_path] = by_file_m.get(rel_path, 0) + 1
        mismatched = {
            rel_path: (by_file_v.get(rel_path, 0), by_file_m.get(rel_path, 0))
            for rel_path in set(by_file_v) | set(by_file_m)
            if by_file_v.get(rel_path, 0) != by_file_m.get(rel_path, 0)
        }
        assert not mismatched, (
            f"{code}: per-file violation count (suppressions ignored) must equal the "
            f"'{marker}' count. A mismatch means an UNRECORDED suppression in some other "
            f"spelling, or a raw violation with no marker at all.\n  "
            + "\n  ".join(f"{f}: {v} violation(s) vs {m} marker(s)" for f, (v, m) in sorted(mismatched.items()))
        )

    @pytest.mark.parametrize(("code", "marker", "recorded"), _RULES, ids=_RULE_IDS)
    def test_every_recorded_file_carries_a_line_scoped_marker(
        self, code: str, marker: str, recorded: frozenset[str]
    ) -> None:
        """A recorded exemption must exist as a LINE, not as an entry in a set."""
        missing = []
        for rel_path in sorted(recorded):
            path = repo_root() / rel_path
            assert path.is_file(), f"recorded {code} exemption does not exist: {rel_path}"
            if marker not in path.read_text(encoding="utf-8"):
                missing.append(rel_path)
        assert not missing, (
            f"recorded as sanctioned {code} exemptions but carrying no line-scoped "
            f"'{marker}' — the exemption must be executable, not prose: {missing}"
        )


class TestExemptSetIsClosed:
    """(d) The violating-file set is exactly the recorded constant — no silent growth."""

    @pytest.mark.parametrize(("code", "marker", "recorded"), _RULES, ids=_RULE_IDS)
    def test_violating_files_equal_recorded_constant(self, code: str, marker: str, recorded: frozenset[str]) -> None:
        """Derived from ruff, not from a marker scan — so it is spelling-blind.

        Strictly stronger than the old file-carries-a-marker form in two ways:
        an exemption written in ANY spelling shows up here, and a RAW violation
        shows up here too — so this catches a reverted Makefile gate line
        independently of the Makefile.
        """
        found = {rel_path for rel_path, _lineno in _violation_sites_ignoring_noqa(code)}
        unrecorded = found - recorded
        missing = recorded - found
        assert not unrecorded and not missing, (
            f"files violating {code} with all suppressions ignored must equal the recorded "
            f"constant.\n"
            + (f"unrecorded (record it or remove the import): {sorted(unrecorded)}\n" if unrecorded else "")
            + (f"recorded but no longer violating (delete the row): {sorted(missing)}\n" if missing else "")
        )


# ---------------------------------------------------------------------------
# (e) The derived obligation: a sanctioned importer RE-EXPORTS what it imports.
#
# banned-api matches the WRITTEN import path textually, so
# `from src.core.security.outbound_http import httpx` resolved to the real
# module and passed clean (round-3 finding 2b). Enumerating the seam paths by
# hand is the same disease as enumerating noqa spellings, so the obligation is
# DERIVED: every suppressed import site owes a ban on its own re-export path.
# A fourth seam file, or a second import in an existing one, creates its
# obligation on the day it is written.
# ---------------------------------------------------------------------------


def _banned_api_paths() -> set[str]:
    """The dotted paths in the config's banned-api table, parsed not guessed."""
    data = tomllib.loads((repo_root() / EGRESS_CONFIG).read_text(encoding="utf-8"))
    return set(data["lint"]["flake8-tidy-imports"]["banned-api"])


def _module_dotted_path(rel_path: str) -> str:
    """`src/core/utils/mcp_client.py` -> `src.core.utils.mcp_client`."""
    parts = rel_path.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _import_bindings_at(rel_path: str, lineno: int) -> set[str]:
    """Names bound by an import statement on *lineno* of *rel_path*."""
    tree = ast.parse((repo_root() / rel_path).read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for alias in node.names:
            if alias.lineno != lineno:
                continue
            bound.add(alias.asname or alias.name.split(".")[0])
    return bound


def _reexport_obligations() -> list[tuple[str, int, str]]:
    """`(rel_path, lineno, dotted_reexport_path)` for every suppressed import site.

    `scripts/` is excluded: a script is not importable as a `src.`-style module,
    so it re-exports nothing.
    """
    obligations: list[tuple[str, int, str]] = []
    for rel_path, lineno in sorted(_violation_sites_ignoring_noqa("TID251")):
        if not rel_path.startswith("src/"):
            continue
        module = _module_dotted_path(rel_path)
        for name in sorted(_import_bindings_at(rel_path, lineno)):
            obligations.append((rel_path, lineno, f"{module}.{name}"))
    return obligations


class TestSeamReexportsAreBanned:
    """(e) Every sanctioned importer's own re-export path is itself banned."""

    def test_every_seam_reexport_path_is_banned(self) -> None:
        obligations = _reexport_obligations()
        assert obligations, (
            "no suppressed TID251 import sites found under src/ — this test has gone "
            "vacuous; the derivation is reading an empty violation set"
        )
        banned = _banned_api_paths()
        unbanned = [(f, n, path) for f, n, path in obligations if path not in banned]
        assert not unbanned, (
            "a sanctioned importer RE-EXPORTS the name it was allowed to import, and that "
            "re-export path is not banned — `from <seam> import <name>` bypasses the gate "
            f"(GH #1589). Add each path to {EGRESS_CONFIG}'s banned-api table:\n  "
            + "\n  ".join(f'{f}:{n} -> "{path}"' for f, n, path in unbanned)
        )

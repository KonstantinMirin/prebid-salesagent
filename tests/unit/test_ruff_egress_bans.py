"""Executable-exemption meta-test for the src-scoped egress import bans.

The egress import bans live in a SECOND, src-scoped ruff config
(``ruff-egress.toml`` at the repo root, run as its own ``make quality`` line:
``uv run ruff check --config ruff-egress.toml src/``). They replace the deleted
AST scans #1 (raw network libs) and #2 (SDK/MCP client constructors) of the
old ``test_architecture_no_raw_egress.py`` — see GH #1589 and CLAUDE.md
pattern #9: all outbound HTTP goes through ``src/core/security/outbound_http.py``.

This module is the ban table's non-vacuity proof, replacing the deleted
guards' meta-tests. Four cases:

(a) POSITIVE  — every banned entry fires (TID251 in ruff's OUTPUT, not just
    exit status) for every resolving spelling: direct import, aliased import,
    dotted-attribute use, and the bypass re-export paths
    (``fastmcp.client`` / ``fastmcp.client.transports.http`` /
    ``adcp.client``) that a single-path ban would let through.
(b) NEGATIVE  — a clean snippet yields no TID251 (and the config loads).
(c) NON-VACUITY per exemption — each sanctioned ``# noqa: TID251`` site,
    fed through stdin under its real path with the noqa stripped, DOES
    violate: the exemption covers a live violation, never dead prose.
(d) CLOSED SET — the set of src/ files carrying ``# noqa: TID251`` equals
    the recorded constant; a new exemption fails until recorded here.

Every case shells out to the real ruff with the real config — the exemptions
are executable, never prose (Core Invariant of salesagent-rq6w / GH #1589).
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from tests.unit._architecture_helpers import repo_root, src_python_files

# Repo-root-relative path of the src-scoped egress ban config.
EGRESS_CONFIG = "ruff-egress.toml"

# Path a synthetic snippet is presented under (must be inside src/ — the
# config's scope is src-only; tests import httpx/requests freely).
_SYNTHETIC_PATH = "src/core/_synthetic_egress_probe.py"

_NOQA_MARKER = "# noqa: TID251"
_NOQA_STRIP_RE = re.compile(r"#\s*noqa:\s*TID251[^\n]*")

# ---------------------------------------------------------------------------
# (d) The two seam definitions -- not an exemption list, a floor.
#
# A seam architecture cannot have zero sanctioned importers of the thing it
# wraps: the seam itself has to import httpx, and the guarded MCP seam has to
# import StreamableHttpTransport to factory-pin it. Every entry is a
# line-scoped `noqa: TID251` comment (never a per-file-ignore) at the one
# construction/import site the seam architecture sanctions:
#   - outbound_http.py       — the seam itself imports httpx
#   - mcp_client.py          — StreamableHttpTransport, factory-pinned
# Adding a file here requires a matching live violation (case c) — the set
# and the noqa lines move together or this module fails. Both are
# liveness-proven: strip the noqa and the build fails.
#
# creative_agent_registry.py / signals_agent_registry.py were listed here
# for constructing adcp.ADCPMultiAgentClient on the un-pinned OPERATOR-agent
# path (adcp 6.6.0 exposed no transport injection point — GH #1589). Both were
# migrated onto the guarded MCP seam (src.core.utils.mcp_client.create_mcp_client)
# by salesagent-4n88, so neither file constructs an adcp SDK client anymore —
# the set SHRANK from 4 to 2, per this module's own non-vacuity contract
# (case c/d): removing a noqa without a live violation is required, not
# merely permitted. It does not grow beyond the two seam definitions.
# ---------------------------------------------------------------------------
SEAM_FILES: frozenset[str] = frozenset(
    {
        "src/core/security/outbound_http.py",
        "src/core/utils/mcp_client.py",
    }
)

# Module-level bans: the bare import fires, so verb enumeration is moot.
_MODULE_BANS: tuple[str, ...] = ("httpx", "requests", "aiohttp", "urllib.request")

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
}


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


def _assert_tid251_fires(source: str, stdin_filename: str, label: str) -> None:
    proc = _run_ruff_egress(source, stdin_filename)
    assert "TID251" in proc.stdout, (
        f"[{label}] expected a TID251 violation from ruff for:\n{source}\n"
        f"--- ruff stdout ---\n{proc.stdout}\n--- ruff stderr ---\n{proc.stderr}"
    )


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


def _files_carrying_noqa() -> set[str]:
    repo = repo_root()
    return {
        str(path.relative_to(repo))
        for path in src_python_files(repo)
        if _NOQA_MARKER in path.read_text(encoding="utf-8")
    }


class TestExemptionsAreExecutable:
    """(c) Each sanctioned noqa still covers a LIVE violation (never dead prose)."""

    @pytest.mark.parametrize("rel_path", sorted(SEAM_FILES))
    def test_stripping_the_noqa_makes_the_file_violate(self, rel_path: str) -> None:
        path = repo_root() / rel_path
        assert path.is_file(), f"recorded exemption file does not exist: {rel_path}"

        source = path.read_text(encoding="utf-8")
        assert _NOQA_MARKER in source, (
            f"{rel_path} is recorded as a sanctioned egress-ban exemption but carries "
            f"no line-scoped '{_NOQA_MARKER}' — the exemption must be executable, not prose"
        )

        stripped = _NOQA_STRIP_RE.sub("", source)
        _assert_tid251_fires(stripped, rel_path, f"strip-noqa:{rel_path}")


class TestExemptSetIsClosed:
    """(d) The exempt set is exactly the recorded constant — no silent growth."""

    def test_noqa_files_equal_recorded_constant(self) -> None:
        found = _files_carrying_noqa()
        unrecorded = found - SEAM_FILES
        missing = SEAM_FILES - found
        assert not unrecorded and not missing, (
            "src/ files carrying '# noqa: TID251' must equal SEAM_FILES.\n"
            + (f"unrecorded exemptions (record here or remove the noqa): {sorted(unrecorded)}\n" if unrecorded else "")
            + (f"recorded exemptions with no noqa in the file: {sorted(missing)}\n" if missing else "")
        )

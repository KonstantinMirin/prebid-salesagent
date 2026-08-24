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

# The same three properties, for the second rule this config carries. ANN401
# bans `Any` in a signature across the outbound chain (GH #1802 /
# salesagent-pldmk.37): `Any` is an opt-out of type checking, assignable to and
# from everything, so it is the one value the seam's own JsonValue signatures
# cannot make unrepresentable — a NEW forwarder declaring `json: Any` and
# passing it straight to send() type-checks clean under mypy.
_ANY_NOQA_MARKER = "# noqa: ANN401"
_ANY_NOQA_STRIP_RE = re.compile(r"#\s*noqa:\s*ANN401[^\n]*")

# ANN401's scope is the two directories the negated glob in ruff-egress.toml
# names, so a synthetic probe must live inside one of them — presenting it
# under src/core/ (TID251's probe path) would be ignored and pass vacuously.
_ANY_SYNTHETIC_PATH = "src/adapters/_synthetic_any_probe.py"

# A forwarder that re-widens the payload one hop before the seam. This is the
# exact shape pldmk.23 removed from VendorHttpClient.call.
_ANY_POSITIVE_SNIPPET = "from typing import Any\ndef call(url: str, *, json: Any = None) -> None:\n    ...\n"

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
# migrated onto the guarded MCP seam (src.core.utils.mcp_client.call_mcp_tool)
# by salesagent-4n88, so neither file constructs an adcp SDK client anymore —
# the set SHRANK from 4 to 2, per this module's own non-vacuity contract
# (case c/d): removing a noqa without a live violation is required, not
# merely permitted. It does not grow beyond the two seam definitions.
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

# Module-level bans: the bare import fires, so verb enumeration is moot.
_MODULE_BANS: tuple[str, ...] = ("httpx", "requests", "aiohttp", "urllib.request", "ipaddress")

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


def _files_carrying_marker(marker: str) -> set[str]:
    repo = repo_root()
    return {
        str(path.relative_to(repo)) for path in src_python_files(repo) if marker in path.read_text(encoding="utf-8")
    }


def _files_carrying_noqa() -> set[str]:
    return _files_carrying_marker(_NOQA_MARKER)


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
# Every entry is liveness-proven by case (c): strip its noqa and ANN401 fires.
# Entries leave this set as pldmk.37's follow-ups land. It must not grow — a new
# file needing `Any` in a signature under these two directories is the very
# thing the ban exists to refuse.
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


class TestAnyBanFires:
    """(a) A re-widening forwarder yields ANN401 — in EITHER scoped directory."""

    @pytest.mark.parametrize(
        "stdin_filename",
        [_ANY_SYNTHETIC_PATH, "src/core/security/_synthetic_any_probe.py"],
        ids=["adapters", "core-security"],
    )
    def test_any_payload_parameter_yields_ann401(self, stdin_filename: str) -> None:
        _assert_rule_fires(_ANY_POSITIVE_SNIPPET, stdin_filename, f"any-ban:{stdin_filename}", "ANN401")

    def test_ban_covers_files_that_do_not_exist_yet(self) -> None:
        """The negated glob is what makes this class-level, not a file list."""
        _assert_rule_fires(
            _ANY_POSITIVE_SNIPPET,
            "src/adapters/brand_new_vendor/client.py",
            "any-ban:new-module",
            "ANN401",
        )


class TestAnyBanScopeIsBounded:
    """(b) ANN401 is scoped to the outbound chain, NOT to all of src/."""

    def test_typed_payload_is_not_flagged(self) -> None:
        clean = (
            "from pydantic import JsonValue\ndef call(url: str, *, json: JsonValue | None = None) -> None:\n    ...\n"
        )
        proc = _run_ruff_egress(clean, _ANY_SYNTHETIC_PATH)
        assert proc.returncode == 0, f"clean snippet failed ruff:\n{proc.stdout}\n{proc.stderr}"
        assert "ANN401" not in proc.stdout, f"typed payload was flagged:\n{proc.stdout}"

    def test_outside_the_scoped_directories_is_ignored(self) -> None:
        """src/ as a whole carries ~200 pre-existing Any and is not this ban's business."""
        proc = _run_ruff_egress(_ANY_POSITIVE_SNIPPET, "src/core/schemas/_probe.py")
        assert "ANN401" not in proc.stdout, (
            f"ANN401 escaped its two-directory scope — the negated glob in ruff-egress.toml is wrong:\n{proc.stdout}"
        )


class TestAnyExemptionsAreExecutable:
    """(c) Each `# noqa: ANN401` still covers a LIVE violation (never dead prose)."""

    @pytest.mark.parametrize("rel_path", sorted(ANY_EXEMPT_FILES))
    def test_stripping_the_noqa_makes_the_file_violate(self, rel_path: str) -> None:
        path = repo_root() / rel_path
        assert path.is_file(), f"recorded ANN401 exemption does not exist: {rel_path}"

        source = path.read_text(encoding="utf-8")
        assert _ANY_NOQA_MARKER in source, (
            f"{rel_path} is recorded as a sanctioned ANN401 exemption but carries no "
            f"line-scoped '{_ANY_NOQA_MARKER}' — the exemption must be executable, not prose"
        )

        stripped = _ANY_NOQA_STRIP_RE.sub("", source)
        _assert_rule_fires(stripped, rel_path, f"strip-any-noqa:{rel_path}", "ANN401")


class TestAnyExemptSetIsClosed:
    """(d) The ANN401 exempt set is exactly the recorded constant — it only shrinks."""

    def test_noqa_files_equal_recorded_constant(self) -> None:
        found = _files_carrying_marker(_ANY_NOQA_MARKER)
        unrecorded = found - ANY_EXEMPT_FILES
        missing = ANY_EXEMPT_FILES - found
        assert not unrecorded and not missing, (
            "src/ files carrying '# noqa: ANN401' must equal ANY_EXEMPT_FILES.\n"
            + (f"unrecorded exemptions (record here or remove the noqa): {sorted(unrecorded)}\n" if unrecorded else "")
            + (f"recorded exemptions with no noqa in the file: {sorted(missing)}\n" if missing else "")
        )

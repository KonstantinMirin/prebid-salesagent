"""Shared L0 parsing layer for the pinned AdCP storyboard compliance tree.

Every ``scripts/audit/storyboard_*.py`` script and the ``make quality`` guard
(``tests/unit/test_architecture_storyboard_binding.py``) need the same
handful of structured facts out of the pinned compliance tree and our own
``.feature`` files: the pinned spec version, our declared protocols/
specialisms, a storyboard's ``required_tools``/``requires_capability``/
phases, a phase's graded check types, a tagged scenario's ``@source``
footer. Before this module each consumer re-derived these independently —
14+ primitives, 2-4 incompatible implementations each, six of which had
silently diverged into live bugs (see salesagent-pw71's codebase-scan,
``.claude/code-review/salesagent-pw71/``). This module is the single
implementation; every consumer imports it.

Deliberately import-safe: nothing here resolves a live ``~/projects/adcp``
clone at import time. ``dist_root()`` takes the clone path as an argument and
is only ever called inside a consumer's own ``build()``/``main()`` — the
``make quality`` guard runs in CI, where no clone exists, and reads the
vendored ``tests/fixtures/adcp_storyboards_pinned/index.json`` instead of
calling into this module's tree-walking functions at all.

Regex over raw text, not ``yaml.safe_load``, remains deliberate: one pinned
file (``universal/runner-output-contract.yaml``) is not valid plain YAML
(it embeds prose/code blocks), and it is already excluded by the ``track:``
predicate in :func:`storyboards` before any consumer would try to parse it
structurally.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Pinned version + declared capabilities ─────────────────────────────────

_SPEC_VERSION_RE = re.compile(r"targets \*\*AdCP spec version ([0-9][^*]*)\*\*")


def pinned_version(repo: Path) -> str:
    """Read the pinned AdCP spec version from docs/adcp-spec-version.md.

    Never hardcoded — a consumer that hardcodes the version rots the same
    way the pins it audits did.
    """
    text = (repo / "docs" / "adcp-spec-version.md").read_text(encoding="utf-8")
    match = _SPEC_VERSION_RE.search(text)
    if not match:
        raise SystemExit("cannot determine pinned version from docs/adcp-spec-version.md")
    return match.group(1).strip()


def dist_root(adcp: Path, version: str) -> Path:
    """The pinned compliance tree root for ``version`` inside a local adcp clone.

    Callers own the existence check (``is_dir()``) — this function only
    joins the path, so it stays import-safe with no adcp clone present.
    """
    return adcp / "dist" / "compliance" / version


_SPECIALISM_RE = re.compile(r"AdcpSpecialism\.(\w+)")
_PROTOCOL_RE = re.compile(r"SupportedProtocol\.(\w+)")


def declared_capabilities(repo: Path) -> dict[str, set[str]]:
    """Our declared specialisms + protocols, read from src/core/tools/capabilities.py.

    Normalized hyphenated (``sales-non-guaranteed``), matching the majority
    convention (2 of the 3 pre-migration readers) — the path segments this
    is compared against are hyphenated in the pinned tree.
    """
    text = (repo / "src" / "core" / "tools" / "capabilities.py").read_text(encoding="utf-8")
    return {
        "specialisms": {s.replace("_", "-") for s in _SPECIALISM_RE.findall(text)},
        "protocols": {p.replace("_", "-") for p in _PROTOCOL_RE.findall(text)},
    }


# ── Storyboard universe ─────────────────────────────────────────────────────

_SKIP_PREFIXES = ("domains/", "test-kits/", "test-vectors/")
_TRACK_RE = re.compile(r"^track:\s*\S", re.M)


@dataclass
class Storyboard:
    rel: str
    stem: str
    text: str


def storyboard_key(rel: str) -> str:
    """Stable identity for a storyboard file.

    ``Path.stem`` collapses every ``*/index.yaml`` onto the literal
    ``"index"``, making one citation of ``protocols/creative/index.yaml``
    look like a claim on every specialism's index. Key index files by their
    parent directory instead.
    """
    path = Path(rel)
    return path.parent.name if path.stem == "index" else path.stem


def storyboards(dist: Path) -> Iterator[Storyboard]:
    """Every real, gradable storyboard file under the pinned compliance tree.

    Skips: ``domains/`` (mirrors ``protocols/`` byte-for-byte — counted
    once), ``test-kits/``/``test-vectors/`` (not storyboards),
    ``storyboard-schema`` (the schema file, not a storyboard), and any
    ``universal/`` file lacking a top-level ``track:`` (``fictional-
    entities.yaml`` is a shared data catalog; ``runner-output-contract.yaml``
    describes runner OUTPUT shape and is not valid plain YAML). Every real
    storyboard declares ``track:``; confirmed against the SB-1b real-runner
    baseline — neither exclusion ever appears in ``storyboards_executed`` or
    ``storyboards_missing_tools``.
    """
    for yaml_file in sorted(dist.rglob("*.yaml")):
        rel = str(yaml_file.relative_to(dist))
        if rel.startswith(_SKIP_PREFIXES):
            continue
        stem = storyboard_key(rel)
        if stem == "storyboard-schema":
            continue
        text = yaml_file.read_text(encoding="utf-8")
        if rel.startswith("universal/") and not _TRACK_RE.search(text):
            continue
        yield Storyboard(rel=rel, stem=stem, text=text)


def storyboard_tier(rel_path: str) -> str:
    """Classify a storyboard path into the tier that decides how it is gated.

    Prefix match on the first path segment — NOT a substring scan (a prior
    implementation matched a tier token appearing anywhere in the path, not
    just the leading segment).
    """
    for tier in ("universal", "specialisms", "protocols", "domains", "test-kits", "test-vectors"):
        if rel_path.startswith(f"{tier}/"):
            return tier
    return "unknown"


# ── Gate fields: required_tools / requires_capability / requires_scenarios ─

_TOOLS_BLOCK_RE = re.compile(r"^required_tools:\n((?:\s+-\s+\S+\n)+)", re.M)
_CAPABILITY_RE = re.compile(r"requires_capability:\s*\n\s*path:\s*(\S+)\s*\n\s*equals:\s*(\S+)")
_REQUIRES_SCENARIOS_RE = re.compile(r"^requires_scenarios:\n((?:\s+-\s+\S+\n)+)", re.M)


def required_tools(text: str) -> set[str]:
    """The ``required_tools:`` any-of list from a storyboard's raw text, or empty."""
    block = _TOOLS_BLOCK_RE.search(text)
    if not block:
        return set()
    return {line.strip().lstrip("- ") for line in block.group(1).splitlines()}


def requires_capability(text: str) -> tuple[str, str] | None:
    """The ``requires_capability: {path, equals}`` gate, or None."""
    match = _CAPABILITY_RE.search(text)
    return (match.group(1), match.group(2)) if match else None


def requiring_indexes(dist: Path) -> dict[str, list[str]]:
    """Map each scenario id to the index.yaml files whose requires_scenarios pulls it in.

    A scenario's directory does NOT determine its gate — ``requires_scenarios``
    is composition ("scenario IDs that must pass alongside this storyboard"),
    the reachability edge, never a whitelist of what applies.
    """
    required_by: dict[str, list[str]] = {}
    for index in sorted(dist.rglob("index.yaml")):
        rel_index = str(index.relative_to(dist))
        if rel_index.startswith("domains/"):
            continue
        block = _REQUIRES_SCENARIOS_RE.search(index.read_text(encoding="utf-8"))
        if not block:
            continue
        for line in block.group(1).splitlines():
            scenario_id = line.strip().lstrip("- ").split("/")[-1]
            required_by.setdefault(scenario_id, []).append(rel_index)
    return required_by


def index_reachable(rel_index: str, declared: dict[str, set[str]]) -> bool:
    """Can we reach this index at all, given what we declare?"""
    parts = rel_index.split("/")
    tier, name = parts[0], parts[1]
    if tier == "specialisms":
        return name in declared["specialisms"]
    if tier == "protocols":
        return name in declared["protocols"]
    return True


# ── Phase / check parsing ───────────────────────────────────────────────────

_PHASE_ID_RE = re.compile(r"^\s*-\s*id:\s*(?P<id>[a-z][a-z0-9_]{3,})\s*$", re.M)
# A real "check:" line's value is a bare identifier alone on the line — either
# list-item-first ("- check: X") or a sibling key within an id-first item
# ("  check: X"). Prose that happens to end in the word "check:" has nothing
# (or a multi-word sentence) after it, not a lone token, so it never matches:
# requiring `\s*$` immediately after the captured token excludes both
# "...parity check:" (nothing captured) and "check: error_code assertions
# ensure..." (more text follows the first token before end of line).
_CHECK_LINE_RE = re.compile(r"^\s*(?:-\s*)?check:\s*(\S+)\s*$", re.M)


def phases(text: str) -> set[str]:
    """Every phase/step ``- id:`` declared in a storyboard's raw text."""
    return {m.group("id") for m in _PHASE_ID_RE.finditer(text)}


def phase_index(dist: Path) -> dict[str, list[str]]:
    """Map every phase/step id at the pinned version to the files declaring it."""
    index: dict[str, list[str]] = {}
    for sb in storyboards(dist):
        for phase_id in phases(sb.text):
            index.setdefault(phase_id, []).append(sb.rel)
    return index


def checks_for_phase(text: str, phase_id: str) -> list[str]:
    """Check types graded under one phase — ``[]`` if absent or narrative-only.

    Anchors on the phase's ``- id:`` line, then windows to the next SIBLING
    id at the same indent (not the next id at any depth — phases sit two
    spaces in and their steps six; stopping at the first six-space ``- id:``
    would truncate at the phase's first step and never reach a later
    ``validations:`` block, misreporting a graded phase as prose). Matches
    ``- check: X`` and the id-first sibling form ``check: X`` alike — the
    leading-dash-only form used pre-migration missed every id-first
    ordering (18 real checks in
    ``protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml`` alone).
    """
    anchor = re.search(rf"^(?P<indent>\s*)-\s*id:\s*{re.escape(phase_id)}\s*$", text, re.M)
    if anchor is None:
        return []
    indent = len(anchor.group("indent"))
    sibling = re.compile(rf"^\s{{0,{indent}}}-\s*id:\s*\S+\s*$", re.M)
    rest = text[anchor.end() :]
    following = sibling.search(rest)
    window = rest[: following.start()] if following else rest
    return _CHECK_LINE_RE.findall(window)


def phase_is_graded(text: str, phase_id: str) -> str | None:
    """Is ``phase_id`` present, and graded (``validations:``) or narrative (``expected:``)?

    Returns ``"graded"``, ``"prose"``, ``"absent"``, or ``None`` when
    ``phase_id`` is falsy (no phase was cited).
    """
    if not phase_id:
        return None
    if re.search(rf"^\s*-\s*id:\s*{re.escape(phase_id)}\s*$", text, re.M) is None:
        return "absent"
    return "graded" if checks_for_phase(text, phase_id) else "prose"


# ── @source footers + tagged scenarios ──────────────────────────────────────

TAG = "@storyboard-v3.1"
_TAGLINE_RE = re.compile(r"^\s*@[\w.\-]+(?:\s+@[\w.\-]+)*\s*$")
_SCENARIO_RE = re.compile(r"^\s*Scenario(?: Outline)?:\s*(?P<title>.+?)\s*$")
_IDENT_TAG_RE = re.compile(r"@(T-[A-Za-z0-9_\-]+)")
_SOURCE_LINE_RE = re.compile(r"@source\s+((?:\w+=\S+\s*)+)")
_KV_RE = re.compile(r"(\w+)=(\S+)")
_CITED_PATH_PREFIX_RE = re.compile(r"^(?:dist/compliance/[^/]+/|static/compliance/source/)")
_SELF_DECLARED_NAME_RE = re.compile(r"^\s*#\s*([a-z][a-z0-9_]{3,}):\s", re.M)


@dataclass
class TaggedScenario:
    """One scenario tagged with ``TAG``, and its trailing comment block."""

    feature: str
    line: int
    identifier: str
    tags: list[str]
    title: str
    block: str
    self_declared_names: set[str] = field(default_factory=set)


def tagged_scenarios(features_dir: Path, tag: str = TAG) -> list[TaggedScenario]:
    """Every scenario tagged ``tag``, with its title and trailing comment block.

    The block runs from the tag line to the next scenario's tag line (or 80
    lines, whichever comes first) — NOT a fixed 60-line window with no
    terminator, which bleeds the following scenario's ``@source`` citations
    into this one's block (verified: 16 of 21 tagged scenarios in
    tests/bdd/features/ were affected pre-fix).
    """
    found: list[TaggedScenario] = []
    for feature in sorted(features_dir.glob("*.feature")):
        lines = feature.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if tag not in line or not _TAGLINE_RE.match(line):
                continue
            tags = line.split()
            title, title_line = "", idx + 1
            for probe in range(idx + 1, min(idx + 4, len(lines))):
                if match := _SCENARIO_RE.match(lines[probe]):
                    title, title_line = match.group("title"), probe + 1
                    break
            ident = next((m.group(1) for t in tags if (m := _IDENT_TAG_RE.match(t))), "(unnamed)")
            block_lines: list[str] = []
            for probe in range(idx, min(idx + 80, len(lines))):
                if probe > idx and _TAGLINE_RE.match(lines[probe]):
                    break
                block_lines.append(lines[probe])
            block = "\n".join(block_lines)
            found.append(
                TaggedScenario(
                    feature=feature.name,
                    line=title_line,
                    identifier=ident,
                    tags=tags,
                    title=title,
                    block=block,
                    self_declared_names=set(_SELF_DECLARED_NAME_RE.findall(block)),
                )
            )
    return found


def parse_source_footer(block: str) -> dict[str, str] | None:
    """Parse an ``@source repo=... ref=... [commit=...] [phase=...] path=...`` footer.

    Order-agnostic over every ``key=value`` pair (a prior implementation
    required an exact ``repo ref [commit] [phase] path`` order and silently
    failed to match any footer that didn't follow it; another dropped
    ``phase`` capture entirely). ``path``'s ``#L..`` line-fragment suffix is
    stripped.
    """
    match = _SOURCE_LINE_RE.search(block)
    if match is None:
        return None
    result = dict(_KV_RE.findall(match.group(1)))
    if "path" in result:
        result["path"] = result["path"].split("#", 1)[0]
    return result


def normalize_cited_path(raw_path: str) -> str:
    """Strip the dist/compliance/<version>/ or static/compliance/source/ prefix."""
    return _CITED_PATH_PREFIX_RE.sub("", raw_path)


# ── Shared CLI entrypoint ────────────────────────────────────────────────────
# Every scripts/audit/storyboard_*.py sibling has the identical
# --repo/--adcp/--markdown argparse + "print JSON or rendered markdown" shape
# — a duplicate `main()` in each file is the same disease this module exists
# to close, one layer up (caught by the duplication guard when a 3rd copy of
# this exact function landed alongside coverage_map.py and binding_sweep.py).


def run_cli(
    description: str,
    build_fn: Callable[[Path, Path], dict[str, Any]],
    render_fn: Callable[[dict[str, Any]], str],
) -> int:
    """Standard CLI: --repo/--adcp/--markdown, build(repo, adcp), print JSON or markdown."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--adcp", type=Path, default=Path.home() / "projects" / "adcp")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    result = build_fn(args.repo.resolve(), args.adcp.resolve())
    print(render_fn(result) if args.markdown else json.dumps(result, indent=2))
    return 0


__all__ = [
    "TAG",
    "Storyboard",
    "TaggedScenario",
    "checks_for_phase",
    "declared_capabilities",
    "dist_root",
    "index_reachable",
    "normalize_cited_path",
    "parse_source_footer",
    "phase_index",
    "phase_is_graded",
    "phases",
    "pinned_version",
    "required_tools",
    "requires_capability",
    "requiring_indexes",
    "run_cli",
    "storyboard_key",
    "storyboard_tier",
    "storyboards",
    "tagged_scenarios",
]

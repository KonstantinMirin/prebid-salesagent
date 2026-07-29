#!/usr/bin/env python3
"""Audit every @storyboard-v3.1 BDD scenario against the pinned AdCP storyboards.

Answers, per scenario, the questions that decide whether its tag is honest:

  1. Does the ``@source`` footer cite a path that EXISTS at the pinned version?
  2. Does the cited phase/step exist in that file?
  3. If not, where does it actually live?
  4. Is the behaviour GRADED (under ``validations:``) or narrative (``expected:``)?
  5. Which storyboard tier owns it -- universal / protocol / domain / specialism?
  6. Do we DECLARE the specialism or protocol that gates it?

Read-only. Emits JSON on stdout; ``--markdown`` renders the checked-in baseline.

The pinned version comes from docs/adcp-spec-version.md, never hardcoded here --
a sweep that hardcodes the version rots the same way the pins it audits did.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCENARIO_TAG = "@storyboard-v3.1"
FEATURES_DIR = Path("tests/bdd/features")
CAPABILITIES = Path("src/core/tools/capabilities.py")
SPEC_VERSION_DOC = Path("docs/adcp-spec-version.md")

# @source repo=adcp ref=<ref> [phase=<phase>] path=<path>[#L..]
SOURCE_RE = re.compile(
    r"@source\s+repo=(?P<repo>\S+)\s+ref=(?P<ref>\S+)"
    r"(?:\s+commit=(?P<commit>\S+))?"
    r"(?:\s+phase=(?P<phase>\S+))?"
    r"\s+path=(?P<path>[^\s#]+)"
)
TAGLINE_RE = re.compile(r"^\s*@[\w.\-]+(?:\s+@[\w.\-]+)*\s*$")
SCENARIO_RE = re.compile(r"^\s*Scenario(?: Outline)?:\s*(?P<title>.+?)\s*$")
IDENT_TAG_RE = re.compile(r"@(T-[A-Za-z0-9_\-]+)")
# A storyboard phase/step id as it appears in the YAML and in scenario prose.
PHASE_ID_RE = re.compile(r"^\s*-\s*id:\s*(?P<id>[a-z][a-z0-9_]{3,})\s*$", re.M)


@dataclass
class Binding:
    """One @storyboard-v3.1 scenario and everything the sweep can prove about it."""

    feature: str
    line: int
    identifier: str
    tags: list[str]
    title: str
    sources: list[dict[str, str]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    bucket: str = "A"  # A ok · B wrong path · C wrong tag · D under-asserts · E prod-blocked
    comment_block: str = ""  # scenario prose; phase ids are named here, not only in `phase=`

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "line": self.line,
            "identifier": self.identifier,
            "title": self.title,
            "tags": self.tags,
            "sources": self.sources,
            "findings": self.findings,
            "bucket": self.bucket,
        }


def pinned_version(repo: Path) -> str:
    """Read the pinned AdCP spec version from the doc that owns it."""
    text = (repo / SPEC_VERSION_DOC).read_text(encoding="utf-8")
    match = re.search(r"targets \*\*AdCP spec version ([0-9][^*]*)\*\*", text)
    if not match:
        raise SystemExit(f"cannot determine pinned version from {SPEC_VERSION_DOC}")
    return match.group(1).strip()


def declared_capabilities(repo: Path) -> dict[str, set[str]]:
    """Extract declared specialisms and protocols from the capabilities emitter."""
    text = (repo / CAPABILITIES).read_text(encoding="utf-8")
    specialisms = set(re.findall(r"AdcpSpecialism\.(\w+)", text))
    protocols = set(re.findall(r"SupportedProtocol\.(\w+)", text))
    return {"specialisms": specialisms, "protocols": protocols}


def parse_features(repo: Path) -> list[Binding]:
    """Collect every @storyboard-v3.1 scenario with its tags, title and @source lines."""
    bindings: list[Binding] = []
    for feature in sorted((repo / FEATURES_DIR).glob("*.feature")):
        lines = feature.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if SCENARIO_TAG not in line or not TAGLINE_RE.match(line):
                continue
            tags = line.split()
            title, title_line = "", idx + 1
            for probe in range(idx + 1, min(idx + 4, len(lines))):
                if match := SCENARIO_RE.match(lines[probe]):
                    title, title_line = match.group("title"), probe + 1
                    break
            ident = next((m for t in tags if (m := IDENT_TAG_RE.match(t))), None)
            binding = Binding(
                feature=feature.name,
                line=title_line,
                identifier=ident.group(1) if ident else "(none)",
                tags=tags,
                title=title,
            )
            # @source lines and the explanatory prose live in the block after the
            # scenario body, up to the next scenario's tag line.
            block: list[str] = []
            for probe in range(idx, min(idx + 80, len(lines))):
                if probe > idx and TAGLINE_RE.match(lines[probe]):
                    break  # next scenario's tag line
                block.append(lines[probe])
                if match := SOURCE_RE.search(lines[probe]):
                    binding.sources.append({k: v or "" for k, v in match.groupdict().items()})
            binding.comment_block = "\n".join(block)
            bindings.append(binding)
    return bindings


def storyboard_tier(rel_path: str) -> str:
    """Classify a storyboard path into the tier that decides how it is gated."""
    for tier in ("universal", "specialisms", "protocols", "domains", "test-kits", "test-vectors"):
        if f"/{tier}/" in f"/{rel_path}":
            return tier
    return "unknown"


def phase_is_graded(text: str, phase: str) -> str | None:
    """Is `phase` present, and does it sit under validations: or only expected: prose?

    Returns "graded", "prose", "absent", or None when no phase was cited.
    """
    if not phase:
        return None
    anchor = re.search(rf"^(?P<indent>\s*)-\s*id:\s*{re.escape(phase)}\s*$", text, re.M)
    if anchor is None:
        return "absent"

    # Window runs to the next sibling id at the SAME indent, not to the next
    # deeper one. Phases sit two spaces in and their steps six; truncating at
    # the first six-space `- id:` stopped at the phase's first step and never
    # reached `validations:`, reporting graded phases as prose.
    indent = len(anchor.group("indent"))
    sibling = re.compile(rf"^\s{{0,{indent}}}-\s*id:\s*\S+\s*$", re.M)
    rest = text[anchor.end() :]
    following = sibling.search(rest)
    window = rest[: following.start()] if following else rest
    return "graded" if re.search(r"^\s*-\s*check:", window, re.M) else "prose"


def phase_index(dist: Path) -> dict[str, list[str]]:
    """Map every storyboard phase/step id at the pinned version to the files declaring it.

    Scenario footers frequently omit ``phase=`` and name the phase in prose instead,
    so the audit has to recognise phase ids on sight rather than trusting the key.
    """
    index: dict[str, list[str]] = {}
    for yaml_file in sorted(dist.rglob("*.yaml")):
        rel = str(yaml_file.relative_to(dist))
        for match in PHASE_ID_RE.finditer(yaml_file.read_text(encoding="utf-8")):
            index.setdefault(match.group("id"), []).append(rel)
    return index


def audit(repo: Path, adcp: Path) -> dict[str, Any]:
    version = pinned_version(repo)
    dist = adcp / "dist" / "compliance" / version
    if not dist.is_dir():
        raise SystemExit(f"pinned compliance tree missing: {dist}")

    declared = declared_capabilities(repo)
    bindings = parse_features(repo)
    phases = phase_index(dist)

    for binding in bindings:
        # Phases the scenario names in prose, whether or not it set `phase=`.
        #
        # Match only an explicit phase REFERENCE ("<id> phase:", "phase=<id>",
        # "step <id>"), never a bare token: most phase ids are also tool names
        # (`create_media_buy`, `get_products`, `list_creatives`) that appear in
        # ordinary prose, and treating those as bindings manufactures findings.
        named = sorted(
            p
            for p in phases
            if re.search(
                rf"(?:\b{re.escape(p)}\s+(?:phase|step)\b|\bphase[=:]\s*{re.escape(p)}\b"
                rf"|\bstep\s+{re.escape(p)}\b)",
                binding.comment_block,
            )
        )
        cited_files = {
            re.sub(r"^(dist/compliance/[^/]+/|static/compliance/source/)", "", s["path"])
            for s in binding.sources
            if "schemas" not in s["path"]
        }
        # Scenarios name their own storyboard in a summary line ("# <name>: <claim>")
        # immediately above the @source footer. When that self-declared name does not
        # match the cited file, the footer points somewhere the scenario never claimed.
        declared_names = set(re.findall(r"^\s*#\s*([a-z][a-z0-9_]{3,}):\s", binding.comment_block, re.M))
        cited_stems = {Path(p).stem for p in cited_files}
        if declared_names and cited_stems and not (declared_names & cited_stems):
            # Only a finding when the declared name is a real storyboard/phase id.
            real = {n for n in declared_names if n in phases or any(Path(f).stem == n for f in phases.get(n, []))}
            real |= {
                n
                for n in declared_names
                if any((dist / f).exists() for f in [f"protocols/media-buy/scenarios/{n}.yaml"])
            }
            if real:
                binding.findings.append(
                    f"self-declared storyboard {sorted(real)} does not match cited file {sorted(cited_stems)} "
                    "— footer points at a storyboard this scenario never claims"
                )
                binding.bucket = "B"

        for phase in named:
            owners = phases[phase]
            if cited_files and not (cited_files & set(owners)):
                binding.findings.append(
                    f"names phase {phase!r} but cites {sorted(cited_files)} — that phase lives in {owners}"
                )
                binding.bucket = "B"

        if not binding.sources:
            binding.findings.append("NO @source footer — binding is unverifiable")
            binding.bucket = "C"
            continue

        for source in binding.sources:
            raw_path, ref, phase = source["path"], source["ref"], source["phase"]

            if version not in ref:
                binding.findings.append(f"stale ref {ref!r} — pinned version is {version}")
                binding.bucket = max(binding.bucket, "B")

            # Normalize: footers cite either dist/compliance/<v>/... or static/... source paths.
            rel = re.sub(r"^dist/compliance/[^/]+/", "", raw_path)
            rel = re.sub(r"^static/compliance/source/", "", rel)
            is_schema = "schemas" in raw_path
            if is_schema:
                source["verdict"] = "schema-path (not a storyboard)"
                continue

            target = dist / rel
            source["resolved"] = str(target.relative_to(adcp)) if target.exists() else ""
            if not target.exists():
                binding.findings.append(f"cited path does not exist at {version}: {rel}")
                binding.bucket = "B"
                continue

            text = target.read_text(encoding="utf-8")
            tier = storyboard_tier(rel)
            source["tier"] = tier
            grading = phase_is_graded(text, phase)
            if grading:
                source["grading"] = grading
                if grading == "absent":
                    binding.findings.append(f"phase {phase!r} not in cited file at {version}")
                    binding.bucket = "B"
                elif grading == "prose":
                    binding.findings.append(f"phase {phase!r} is narrative (expected:) not graded (validations:)")
                    binding.bucket = "C"

            if tier == "specialisms":
                name = rel.split("/")[1].replace("-", "_")
                if name not in declared["specialisms"]:
                    binding.findings.append(f"gated by specialism {name!r} which we do NOT declare — tag is wrong")
                    binding.bucket = "C"

    buckets: dict[str, int] = {}
    for binding in bindings:
        buckets[binding.bucket] = buckets.get(binding.bucket, 0) + 1

    return {
        "pinned_version": version,
        "declared": {k: sorted(v) for k, v in declared.items()},
        "scenario_count": len(bindings),
        "buckets": buckets,
        "bindings": [b.to_dict() for b in bindings],
    }


def render_markdown(result: dict[str, Any]) -> str:
    version = result["pinned_version"]
    out = [
        f"# Storyboard binding baseline — AdCP {version}",
        "",
        f"`{result['scenario_count']}` scenarios tagged `{SCENARIO_TAG}`. "
        f"Declared specialisms: `{', '.join(result['declared']['specialisms']) or 'none'}`; "
        f"protocols: `{', '.join(result['declared']['protocols']) or 'none'}`.",
        "",
        "Buckets — **A** binding verified · **B** wrong/stale `@source` · "
        "**C** tag unjustified (ungraded or undeclared gate) · "
        "**D** graded but under-asserted · **E** graded, blocked on production.",
        "",
        "| Scenario | Feature:line | Bucket | Findings |",
        "|---|---|---|---|",
    ]
    for b in result["bindings"]:
        findings = "<br>".join(b["findings"]) or "—"
        out.append(f"| `{b['identifier']}` | {b['feature']}:{b['line']} | **{b['bucket']}** | {findings} |")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--adcp", type=Path, default=Path.home() / "projects" / "adcp")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    result = audit(args.repo.resolve(), args.adcp.resolve())
    print(render_markdown(result) if args.markdown else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

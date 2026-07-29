#!/usr/bin/env python3
"""Reverse map: which pinned AdCP storyboards are on OUR conformance path, and are they covered?

The binding sweep asks "does this scenario's @source resolve?". This asks the
question that actually decides compliance: **for every storyboard the pinned spec
would grade us on, do we have a BDD scenario?**

A storyboard is on our path when it is either

  * ``universal/``            — always applies, no gate; or
  * named in ``requires_scenarios`` of a protocol we declare; or
  * a protocol/domain index for a protocol we declare,

AND it is not excluded by a gate we fail:

  * ``requires_capability:``  — a capability we do not advertise
  * ``specialisms/``          — a specialism we do not declare

Uncovered on-path storyboards are conformance gaps with no test. Covered
off-path scenarios are tests claiming a grading that does not apply to us.

Read-only. Emits JSON, or ``--markdown`` for the checked-in artifact.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

FEATURES_DIR = Path("tests/bdd/features")
CAPABILITIES = Path("src/core/tools/capabilities.py")
SPEC_VERSION_DOC = Path("docs/adcp-spec-version.md")
SCENARIO_TAG = "@storyboard-v3.1"


def pinned_version(repo: Path) -> str:
    text = (repo / SPEC_VERSION_DOC).read_text(encoding="utf-8")
    match = re.search(r"targets \*\*AdCP spec version ([0-9][^*]*)\*\*", text)
    if not match:
        raise SystemExit(f"cannot determine pinned version from {SPEC_VERSION_DOC}")
    return match.group(1).strip()


def declared(repo: Path) -> dict[str, set[str]]:
    text = (repo / CAPABILITIES).read_text(encoding="utf-8")
    return {
        "specialisms": {s.replace("_", "-") for s in re.findall(r"AdcpSpecialism\.(\w+)", text)},
        "protocols": {p.replace("_", "-") for p in re.findall(r"SupportedProtocol\.(\w+)", text)},
    }


def required_scenarios(dist: Path, protocols: set[str]) -> set[str]:
    """Scenario ids the declared protocols pull onto the base conformance path."""
    required: set[str] = set()
    for protocol in protocols:
        index = dist / "protocols" / protocol / "index.yaml"
        if not index.exists():
            continue
        block = re.search(r"^requires_scenarios:\n((?:\s+-\s+\S+\n)+)", index.read_text("utf-8"), re.M)
        if block:
            required |= {line.strip().lstrip("- ").split("/")[-1] for line in block.group(1).splitlines()}
    return required


def classify(rel: str, text: str, decl: dict[str, set[str]], required: set[str]) -> tuple[str, str]:
    """Return (status, reason) for one storyboard file."""
    stem = Path(rel).stem
    if rel.startswith("universal/"):
        return "ON-PATH", "universal — applies to every agent"
    if rel.startswith("specialisms/"):
        name = rel.split("/")[1]
        if name not in decl["specialisms"]:
            return "OFF-PATH", f"specialism {name!r} not declared"
        return "ON-PATH", f"specialism {name!r} declared"
    if rel.startswith(("protocols/", "domains/")):
        protocol = rel.split("/")[1]
        if protocol not in decl["protocols"]:
            return "OFF-PATH", f"protocol {protocol!r} not declared"
        if capability := re.search(r"requires_capability:\s*\n\s*path:\s*(\S+)\s*\n\s*equals:\s*(\S+)", text):
            return "GATED", f"requires_capability {capability.group(1)} == {capability.group(2)}"
        if stem == "index":
            return "ON-PATH", f"protocol {protocol!r} index"
        if stem in required:
            return "ON-PATH", f"in {protocol!r} requires_scenarios"
        return "OFF-PATH", f"not in {protocol!r} requires_scenarios"
    return "UNKNOWN", "unclassified tier"


def storyboard_key(rel: str) -> str:
    """Stable identity for a storyboard file.

    ``Path.stem`` collapses every ``*/index.yaml`` onto the literal "index",
    which makes one citation of ``protocols/creative/index.yaml`` look like a
    claim on every specialism's index. Key index files by their parent instead.
    """
    path = Path(rel)
    return path.parent.name if path.stem == "index" else path.stem


def covered_storyboards(repo: Path) -> dict[str, list[str]]:
    """Storyboard stems our @storyboard-v3.1 scenarios claim, by scenario identifier."""
    claims: dict[str, list[str]] = {}
    for feature in sorted((repo / FEATURES_DIR).glob("*.feature")):
        lines = feature.read_text("utf-8").splitlines()
        for idx, line in enumerate(lines):
            if SCENARIO_TAG not in line:
                continue
            ident = next((t for t in line.split() if t.startswith("@T-")), "@?").lstrip("@")
            block = "\n".join(lines[idx : idx + 60])
            # Prefer the scenario's self-declared storyboard name over its (often wrong) @source.
            for name in re.findall(r"^\s*#\s*([a-z][a-z0-9_]{3,}):\s", block, re.M):
                claims.setdefault(name, []).append(ident)
            for path in re.findall(r"path=(\S+)", block):
                if "schemas" not in path:
                    claims.setdefault(storyboard_key(path), []).append(ident)
    return claims


def build(repo: Path, adcp: Path) -> dict[str, Any]:
    version = pinned_version(repo)
    dist = adcp / "dist" / "compliance" / version
    if not dist.is_dir():
        raise SystemExit(f"missing pinned compliance tree: {dist}")

    decl = declared(repo)
    required = required_scenarios(dist, decl["protocols"])
    claims = covered_storyboards(repo)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for yaml_file in sorted(dist.rglob("*.yaml")):
        rel = str(yaml_file.relative_to(dist))
        # protocols/ and domains/ mirror each other byte-for-byte; count each storyboard once.
        if rel.startswith("domains/"):
            continue
        stem = storyboard_key(rel)
        if rel.startswith(("test-kits/", "test-vectors/")) or stem == "storyboard-schema":
            continue
        status, reason = classify(rel, yaml_file.read_text("utf-8"), decl, required)
        key = f"{rel}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "storyboard": rel,
                "stem": stem,
                "status": status,
                "reason": reason,
                "covered_by": sorted(set(claims.get(stem, []))),
            }
        )

    on_path = [r for r in rows if r["status"] == "ON-PATH"]
    return {
        "pinned_version": version,
        "declared": {k: sorted(v) for k, v in decl.items()},
        "requires_scenarios": sorted(required),
        "totals": {
            "storyboards": len(rows),
            "on_path": len(on_path),
            "on_path_uncovered": len([r for r in on_path if not r["covered_by"]]),
            "off_path_but_claimed": len(
                [r for r in rows if r["status"] in {"OFF-PATH", "GATED"} and r["covered_by"]]
            ),
        },
        "storyboards": rows,
    }


def render(result: dict[str, Any]) -> str:
    out = [
        f"# Storyboard coverage map — AdCP {result['pinned_version']}",
        "",
        f"Declared protocols: `{', '.join(result['declared']['protocols'])}` · "
        f"specialisms: `{', '.join(result['declared']['specialisms'])}`",
        "",
        f"- storyboards examined: **{result['totals']['storyboards']}**",
        f"- on our conformance path: **{result['totals']['on_path']}**",
        f"- **on-path with NO scenario: {result['totals']['on_path_uncovered']}**",
        f"- off-path/gated but claimed by a scenario: **{result['totals']['off_path_but_claimed']}**",
        "",
        "## On our conformance path",
        "",
        "| Storyboard | Why on path | Covered by |",
        "|---|---|---|",
    ]
    for r in result["storyboards"]:
        if r["status"] != "ON-PATH":
            continue
        covered = ", ".join(f"`{c}`" for c in r["covered_by"]) or "**— NOT COVERED —**"
        out.append(f"| `{r['storyboard']}` | {r['reason']} | {covered} |")
    out += ["", "## Off path or gated, but a scenario claims them", "", "| Storyboard | Why off path | Claimed by |", "|---|---|---|"]
    for r in result["storyboards"]:
        if r["status"] == "ON-PATH" or not r["covered_by"]:
            continue
        out.append(f"| `{r['storyboard']}` | {r['reason']} | {', '.join(f'`{c}`' for c in r['covered_by'])} |")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--adcp", type=Path, default=Path.home() / "projects" / "adcp")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    result = build(args.repo.resolve(), args.adcp.resolve())
    print(render(result) if args.markdown else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

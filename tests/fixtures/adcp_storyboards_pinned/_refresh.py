#!/usr/bin/env python3
"""Refresh the pinned AdCP storyboard index used by test_architecture_storyboard_binding.

Source of truth: adcontextprotocol/adcp, the compliance tree for the spec version
this repo pins in ``docs/adcp-spec-version.md`` (``dist/compliance/<version>/``).

Why an index rather than the storyboards themselves: the guard only needs to answer
three questions offline — does a cited storyboard path exist at the pin, does a named
phase live in that file, and what gates that storyboard. Vendoring the full YAML tree
(hundreds of files, most of them narrative prose) to answer three structural questions
would be noise. The index is a few KB and diffs legibly when the pin advances.

This deliberately mirrors the ``adcp_schemas_pinned`` fixture next door, with one
difference worth knowing: that fixture is frozen at commit 04f59d2d5 as an intentional
reference point for "AdCP 3.1 semantics", which is now OLDER than the 3.1.1 the repo
actually pins. This index tracks ``docs/adcp-spec-version.md`` instead, so the two can
disagree — and when they do, that disagreement is the finding.

To refresh (a deliberate, reviewed change — normally only when the pin advances):
    uv run python tests/fixtures/adcp_storyboards_pinned/_refresh.py

Reads from a local clone at ~/projects/adcp.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ADCP = Path.home() / "projects" / "adcp"
OUT = Path(__file__).parent / "index.json"

PHASE_RE = re.compile(r"^\s*-\s*id:\s*(?P<id>[a-z][a-z0-9_]{3,})\s*$", re.M)
CAPABILITY_RE = re.compile(r"requires_capability:\s*\n\s*path:\s*(\S+)\s*\n\s*equals:\s*(\S+)")
TOOLS_RE = re.compile(r"^required_tools:\n((?:\s+-\s+\S+\n)+)", re.M)


def pinned_version() -> str:
    doc = (REPO_ROOT / "docs" / "adcp-spec-version.md").read_text(encoding="utf-8")
    match = re.search(r"targets \*\*AdCP spec version ([0-9][^*]*)\*\*", doc)
    if not match:
        raise SystemExit("cannot determine pinned version from docs/adcp-spec-version.md")
    return match.group(1).strip()


def build() -> dict[str, object]:
    version = pinned_version()
    dist = ADCP / "dist" / "compliance" / version
    if not dist.is_dir():
        raise SystemExit(f"pinned compliance tree not found: {dist}\nIs ~/projects/adcp cloned and current?")

    storyboards: dict[str, dict[str, object]] = {}
    for yaml_file in sorted(dist.rglob("*.yaml")):
        rel = str(yaml_file.relative_to(dist))
        # protocols/ and domains/ mirror byte-for-byte; index the protocols/ view only.
        if rel.startswith(("domains/", "test-kits/", "test-vectors/")):
            continue
        text = yaml_file.read_text(encoding="utf-8")
        entry: dict[str, object] = {"phases": sorted({m.group("id") for m in PHASE_RE.finditer(text)})}
        if capability := CAPABILITY_RE.search(text):
            entry["requires_capability"] = {"path": capability.group(1), "equals": capability.group(2)}
        if tools := TOOLS_RE.search(text):
            entry["required_tools"] = sorted(line.strip().lstrip("- ") for line in tools.group(1).splitlines())
        if rel.startswith("specialisms/"):
            entry["specialism"] = rel.split("/")[1]
        elif rel.startswith("protocols/"):
            entry["protocol"] = rel.split("/")[1]
        elif rel.startswith("universal/"):
            entry["universal"] = True
        storyboards[rel] = entry

    return {
        "adcp_spec_version": version,
        "source": f"adcontextprotocol/adcp dist/compliance/{version}",
        "storyboard_count": len(storyboards),
        "storyboards": storyboards,
    }


if __name__ == "__main__":
    index = build()
    OUT.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(REPO_ROOT)} — {index['storyboard_count']} storyboards at {index['adcp_spec_version']}"
    )

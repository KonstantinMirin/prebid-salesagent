"""Fact-extractor for the salesagent-g6m2.4 re-grounding audit.

For every obligation section in docs/test-obligations/{constraints,business-rules}.md,
resolve the schema subject it names against the PINNED 3.1.1 bundle and report the
facts a verdict needs: does the named schema still exist, what is its
additionalProperties policy, and which of the fields the obligation names are
actually present.

Deterministic and re-runnable — the verdicts are written from these facts, not
from memory of what 3.6 used to say.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path("/Users/konst/projects/salesagent-sbsweep")
BUNDLE = REPO / "tests/storyboard/runner/adcp-3.1.1/schemas"
DOCS = REPO / "docs/test-obligations"

SECTION_RE = re.compile(r"^### (?P<subject>[^:]+): (?P<title>.+)$", re.M)
OBLIGATION_RE = re.compile(r"^\*\*Obligation ID\*\* (?P<id>\S+)", re.M)
LAYER_RE = re.compile(r"^\*\*Layer\*\* (?P<layer>\w+)", re.M)
VERDICT_RE = re.compile(r"^\*\*Affected by 3\.6:\*\* (?P<verdict>.*)$", re.M)
FIELD_RE = re.compile(r"`([a-z][a-z0-9_]{2,})`")


def _schema_index() -> dict[str, list[Path]]:
    """Every schema in the bundle, indexed by stem."""
    index: dict[str, list[Path]] = {}
    for path in BUNDLE.rglob("*.json"):
        index.setdefault(path.stem, []).append(path)
    return index


def _resolve(subject: str, index: dict[str, list[Path]]) -> list[Path]:
    """Candidate schema files for an obligation's `### <subject>:` name."""
    stem = subject.strip().replace("_", "-").lower()
    for candidate in (stem, stem.rstrip("s"), f"{stem}s"):
        if candidate in index:
            return index[candidate]
    return []


def _facts(paths: list[Path], named_fields: set[str]) -> dict[str, object]:
    if not paths:
        return {"exists": False}
    schema = json.loads(paths[0].read_text(encoding="utf-8"))
    props = set(schema.get("properties", {}))
    return {
        "exists": True,
        "path": str(paths[0].relative_to(BUNDLE)),
        "additionalProperties": schema.get("additionalProperties"),
        "required": sorted(schema.get("required", [])),
        "present_fields": sorted(named_fields & props),
        "absent_fields": sorted(named_fields - props) if props else sorted(named_fields),
        "n_properties": len(props),
    }


def audit(doc: Path, index: dict[str, list[Path]]) -> list[dict[str, object]]:
    text = doc.read_text(encoding="utf-8")
    matches = list(SECTION_RE.finditer(text))
    rows: list[dict[str, object]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        obligation = OBLIGATION_RE.search(body)
        layer = LAYER_RE.search(body)
        verdict = VERDICT_RE.search(body)
        subject = match.group("subject")
        named = set(FIELD_RE.findall(body))
        paths = _resolve(subject, index)
        rows.append(
            {
                "doc": doc.name,
                "subject": subject,
                "obligation_id": obligation.group("id") if obligation else None,
                "layer": layer.group("layer") if layer else None,
                "old_verdict": verdict.group("verdict").strip() if verdict else None,
                **_facts(paths, named),
            }
        )
    return rows


def main() -> int:
    index = _schema_index()
    rows: list[dict[str, object]] = []
    for name in ("constraints.md", "business-rules.md"):
        rows += audit(DOCS / name, index)

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/verdict_facts.json")
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    resolved = sum(1 for r in rows if r.get("exists"))
    print(f"sections: {len(rows)}  schema-resolved: {resolved}  unresolved: {len(rows) - resolved}")
    print(f"with an 'Affected by 3.6' verdict: {sum(1 for r in rows if r['old_verdict'])}")
    print("\nunresolved subjects (need a hand decision):")
    for r in rows:
        if not r.get("exists"):
            print(f"  {r['doc']:20} {r['subject']:45} {r['obligation_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

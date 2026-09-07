#!/usr/bin/env python3
"""Locate every hand-built creative and pricing-option literal in the test tree.

The step-defect counts have had a committed classifier since they were first
quoted (``build_bdd_decisions.py``); the seeding counts did not, and a review
caught the asymmetry: the 191/110/84 figures lived only inside a 547 KB HTML of
agent reports, so the first engineer to act on them would have started with
archaeology instead of a command.

This is that command. It re-derives the counts, prints the file list a migration
shards on, and states its own definition — because a differently-drawn definition
produces materially different numbers, which is exactly what the review found when
it re-counted by hand.

DEFINITION, stated so it can be argued with rather than guessed at:

    A CREATIVE LITERAL is a dict display whose keys include at least two of
    creative_id / name / format_id / format / format_kind / assets / snippet /
    url / media_url. Two keys, not one, because ``{"format_id": x}`` on its own is
    a reference, not a creative.

    It is HAND-BUILT when it is not an argument to a factory call — no enclosing
    ``*Factory(...)``, ``.build(...)``, ``.create(...)`` or ``.payload(...)``.
    Those go through an owner; the hand-built ones go through nothing, which is
    what makes them the migration target.

    It is STRUCTURALLY INVALID when it omits ``assets``, which the pinned model
    marks required on both ``oneOf`` branches — so the payload cannot validate,
    and today it passes only because nothing reads it.

    ``--scope`` decides whether ``tests/integration`` and ``tests/unit`` count.
    The reviewer's re-count differed from the report's largely on this axis, so it
    is a flag rather than a silent choice.

    python3 scripts/audit/creative_literal_sites.py [--scope bdd|tests] [--json]
"""

from __future__ import annotations

import argparse
import ast
import collections
import glob
import json
import pathlib
import sys

CREATIVE_KEYS = {
    "creative_id",
    "name",
    "format_id",
    "format",
    "format_kind",
    "assets",
    "snippet",
    "url",
    "media_url",
}
PRICING_KEYS = {"pricing_option_id", "pricing_model", "rate", "currency", "fixed_price", "floor_price"}
FACTORY_CALLS = ("Factory", "build", "create", "payload")

SCOPES = {
    "bdd": ["tests/bdd/**/*.py", "tests/harness/**/*.py"],
    "tests": ["tests/**/*.py"],
}


def factory_spans(tree: ast.AST) -> list[tuple[int, int]]:
    """Line ranges covered by a call that goes through an owner."""
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        label = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
        owner = getattr(getattr(f, "value", None), "id", "")
        if any(k in label for k in FACTORY_CALLS) or "Factory" in owner:
            spans.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
    return spans


def scan(paths: list[str]):
    creatives, pricing = [], []
    for pattern in paths:
        for path in sorted(glob.glob(pattern, recursive=True)):
            if "__pycache__" in path:
                continue
            text = pathlib.Path(path).read_text()
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            spans = factory_spans(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                inside = any(lo <= node.lineno <= hi for lo, hi in spans)
                if len(keys & CREATIVE_KEYS) >= 2:
                    creatives.append(
                        {
                            "file": path,
                            "line": node.lineno,
                            "hand_built": not inside,
                            "omits_assets": "assets" not in keys,
                            "pre_311": bool(
                                keys & {"snippet", "snippet_type", "template_variables", "duration", "variants"}
                            ),
                        }
                    )
                elif len(keys & PRICING_KEYS) >= 2:
                    pricing.append({"file": path, "line": node.lineno, "hand_built": not inside})
    return creatives, pricing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=sorted(SCOPES), default="tests")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    creatives, pricing = scan(SCOPES[args.scope])
    hand = [c for c in creatives if c["hand_built"]]
    invalid = [c for c in hand if c["omits_assets"]]
    stale = [c for c in creatives if c["pre_311"]]

    if args.json:
        json.dump({"creatives": creatives, "pricing": pricing}, sys.stdout, indent=1)
        return 0

    print(f"scope={args.scope}\n")
    print(f"  creative literals            {len(creatives):5}   in {len({c['file'] for c in creatives})} files")
    print(f"    hand-built (no owner)      {len(hand):5}   <- the migration target")
    print(f"    ...of those, omit assets   {len(invalid):5}   <- structurally invalid, green today")
    print(f"    carrying pre-3.1.1 fields  {len(stale):5}")
    print(f"  pricing-option literals      {len(pricing):5}   hand-built {sum(1 for p in pricing if p['hand_built'])}")

    print("\n  hand-built creative sites by file (the shard list):")
    for f, n in collections.Counter(c["file"] for c in hand).most_common():
        print(f"    {n:4}  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

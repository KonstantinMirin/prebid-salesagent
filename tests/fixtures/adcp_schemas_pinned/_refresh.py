#!/usr/bin/env python3
"""Refresh the pinned AdCP error-code enum vendored here.

Source of truth: adcontextprotocol/adcp @ commit
    04f59d2d56d3d77033162c310e99a1188e4eb419  (tag v3.1-04f59d2d5, 2026-05-13)

This commit is an INTENTIONAL, frozen reference point, DELIBERATELY independent
of the installed adcp SDK's own pin (see docs/adcp-spec-version.md "Pinned
schema sources"). It exists ONLY for enums/error-code.json's ``enumMetadata``
``suggestion`` text, read by
tests/unit/test_architecture_error_suggestion_enum_conformance.py. The
installed SDK's error-code enum has grown independently (92+ codes vs. this
fixture's 66) and its ``suggestion`` wording diverges from this fixture's on
4 codes (CREDENTIAL_IN_ARGS, MEDIA_BUY_NOT_FOUND, PACKAGE_NOT_FOUND,
REQUOTE_REQUIRED, verified at migration time) — moving that reader onto the
SDK tree requires first reconciling that divergence (tracked as its own
epic; see docs/adcp-spec-version.md), not a mechanical resolver swap.

Every OTHER pinned-schema consumer — structural request/response shape,
``$ref`` resolution, AND the ``recovery`` half of this same enumMetadata
block (verified byte-identical across all 66 shared codes, so
tests/harness/transport.py and
tests/unit/test_architecture_error_recovery_enum_conformance.py both migrated)
— reads through tests/helpers/pinned_schema.py, which resolves from the
installed SDK's own tree. scripts/verify_feature_error_codes.py also
migrated (it only reads the ``enum`` code list, not enumMetadata content).
This fixture directory no longer vendors any schema-shape files, only this
one enum, kept only for its suggestion-text divergence.

To refresh (e.g. to advance the pinned commit — a deliberate, reviewed change
that must also re-check the recovery/suggestion divergence against the SDK):
    uv run python tests/fixtures/adcp_schemas_pinned/_refresh.py

It reads from a local clone at ~/projects/adcp if present (faster), else GitHub raw.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path

PINNED_SHA = "04f59d2d56d3d77033162c310e99a1188e4eb419"
REPO = "adcontextprotocol/adcp"
SRC_PREFIX = "static/schemas/source"  # repo path that backs the `/schemas/...` namespace
LOCAL_CLONE = Path.home() / "projects" / "adcp"
FIXTURE_DIR = Path(__file__).parent

# The sole surviving root: error-code enumMetadata (see module docstring for why
# this is a deliberately independent pin, not part of the general schema-shape closure).
ROOTS = [
    "/schemas/enums/error-code.json",
]


def _read_local(rel: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(LOCAL_CLONE), "show", f"{PINNED_SHA}:{SRC_PREFIX}{rel}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else None


def _read_github(rel: str) -> str:
    url = f"https://raw.githubusercontent.com/{REPO}/{PINNED_SHA}/{SRC_PREFIX}{rel}"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (pinned host)
        return resp.read().decode()


def fetch(ref: str) -> str:
    rel = ref[len("/schemas") :]  # "/schemas/core/x.json" -> "/core/x.json"
    return _read_local(rel) or _read_github(rel)


def main() -> None:
    seen: set[str] = set()
    stack = list(ROOTS)
    written = 0
    while stack:
        ref = stack.pop().split("#")[0]
        if not ref.startswith("/schemas/") or ref in seen:
            continue
        seen.add(ref)
        body = fetch(ref)
        out = FIXTURE_DIR / ref[len("/schemas/") :]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(json.loads(body), indent=2) + "\n")
        written += 1
        stack.extend(re.findall(r'"\$ref"\s*:\s*"([^"]+)"', body))
    print(f"vendored {written} schema files from {REPO}@{PINNED_SHA[:9]} into {FIXTURE_DIR}")


if __name__ == "__main__":
    main()

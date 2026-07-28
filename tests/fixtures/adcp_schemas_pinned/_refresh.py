#!/usr/bin/env python3
"""Refresh the pinned AdCP JSON-schema fixtures used by test_pydantic_schema_alignment.

Source of truth: adcontextprotocol/adcp @ commit
    04f59d2d56d3d77033162c310e99a1188e4eb419  (tag v3.1-04f59d2d5, 2026-05-13)

This commit is an INTENTIONAL, frozen reference point for AdCP 3.1 semantics. The
upstream adcp repo ships constantly and `/schemas/latest` drifts; we deliberately do
NOT track it. The commit is immutable on GitHub, so the schemas are vendored here
(committed) — the alignment test reads them offline and never fetches `/schemas/latest`.

Layout: schema `$id`/`$ref` namespace is `/schemas/<rest>`; each is written to
`<this dir>/<rest>` (so `/schemas/core/account-ref.json` -> `core/account-ref.json`).

Only the transitive `$ref` closure of the request schemas the test maps is vendored.

To refresh (e.g. to advance the pinned commit — a deliberate, reviewed change):
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

# Second, explicitly-versioned root set (#1291 A3, salesagent-z6nr.9 step 7).
#
# The trust-root documents A3 publishes are graded against v3.1.1, NOT against
# PINNED_SHA: `adagents.json` and `brand.json` differ between the two revisions,
# and `core/authorized-agent-base.json` — where `signing_keys[]` actually lives —
# does not exist at PINNED_SHA at all. Vendoring them from the old pin would grade
# the producer against a schema that predates the shape it must emit.
#
# The pin is NOT moved: that would churn every vendored file under this directory
# and re-open `test_pydantic_schema_alignment`. Two coexisting root sets instead.
#
# The `$id` namespace at this revision carries the version (`/schemas/3.1.1/...`),
# so these land under `3.1.1/` by the same layout rule and the `referencing`
# registry built by `tests/helpers/pinned_schema.py` resolves the VERSIONED URIs
# without a special case. `core/agent-signing-key.json` is byte-identical to the
# PINNED_SHA copy except for that `$id` — the changed namespace is exactly why
# the versioned URI has to be the registry key.
V311_REV = "v3.1.1"
V311_SRC_PREFIX = "dist/schemas"  # backs the `/schemas/...` namespace at this revision
V311_ROOTS = [
    "/schemas/3.1.1/brand.json",
    "/schemas/3.1.1/adagents.json",
    "/schemas/3.1.1/core/agent-signing-key.json",
]

# Request schemas the alignment test maps to Pydantic models, plus response schemas
# whose contract individual tests assert against (the BFS roots).
ROOTS = [
    "/schemas/media-buy/get-products-request.json",
    "/schemas/media-buy/update-media-buy-request.json",
    "/schemas/media-buy/get-media-buy-delivery-request.json",
    "/schemas/creative/sync-creatives-request.json",
    "/schemas/creative/list-creatives-request.json",
    # Response schemas grounding specific contract tests:
    "/schemas/media-buy/create-media-buy-response.json",  # test_adcp_contract F4 (valid_actions/context)
    "/schemas/account/sync-accounts-response.json",  # test_sync_response_account_contract F5 (required fields)
    "/schemas/creative/sync-creatives-response.json",  # PR1399 R3-F2 (creatives required)
    # PR1399 Plan-B: machine-complete RESPONSE_ALIGNMENTS over every implemented response model.
    "/schemas/media-buy/get-products-response.json",
    "/schemas/media-buy/update-media-buy-response.json",
    "/schemas/media-buy/get-media-buy-delivery-response.json",
    "/schemas/creative/get-creative-delivery-response.json",
    "/schemas/creative/list-creatives-response.json",
    "/schemas/creative/list-creative-formats-response.json",
    "/schemas/account/list-accounts-response.json",
    "/schemas/signals/get-signals-response.json",
    "/schemas/signals/activate-signal-response.json",
    # Standalone enum vendored for the BDD error-code guard (verify_feature_error_codes.py).
    # Not in any request/response $ref closure, so it must be listed explicitly to stay pinned.
    "/schemas/enums/error-code.json",
]


def _read_local(rev: str, src_prefix: str, rel: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(LOCAL_CLONE), "show", f"{rev}:{src_prefix}{rel}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else None


def _read_github(rev: str, src_prefix: str, rel: str) -> str:
    url = f"https://raw.githubusercontent.com/{REPO}/{rev}/{src_prefix}{rel}"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (pinned host)
        return resp.read().decode()


def fetch(ref: str, *, rev: str = PINNED_SHA, src_prefix: str = SRC_PREFIX) -> str:
    rel = ref[len("/schemas") :]  # "/schemas/core/x.json" -> "/core/x.json"
    return _read_local(rev, src_prefix, rel) or _read_github(rev, src_prefix, rel)


def vendor(roots: list[str], *, rev: str, src_prefix: str) -> int:
    """Walk the transitive ``$ref`` closure of *roots* at *rev* and write it out.

    One BFS for every root set — the layout rule (``$id`` namespace path minus
    the ``/schemas/`` prefix) is identical at both revisions, so a second copy
    parameterised by revision would be pure duplication.
    """
    seen: set[str] = set()
    stack = list(roots)
    written = 0
    while stack:
        ref = stack.pop().split("#")[0]
        if not ref.startswith("/schemas/") or ref in seen:
            continue
        seen.add(ref)
        body = fetch(ref, rev=rev, src_prefix=src_prefix)
        out = FIXTURE_DIR / ref[len("/schemas/") :]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(json.loads(body), indent=2) + "\n")
        written += 1
        stack.extend(re.findall(r'"\$ref"\s*:\s*"([^"]+)"', body))
    print(f"vendored {written} schema files from {REPO}@{rev[:9]} into {FIXTURE_DIR}")
    return written


def main() -> None:
    vendor(ROOTS, rev=PINNED_SHA, src_prefix=SRC_PREFIX)
    vendor(V311_ROOTS, rev=V311_REV, src_prefix=V311_SRC_PREFIX)


if __name__ == "__main__":
    main()

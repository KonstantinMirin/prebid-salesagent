#!/usr/bin/env python3
"""Refresh the pinned AdCP JSON-schema fixtures used by test_pydantic_schema_alignment.

Also vendors the request-signing CONFORMANCE VECTORS (#1291 B3, salesagent-z6nr.14)
into ``tests/fixtures/adcp_conformance_vectors/`` — see :func:`vendor_signing_vectors`.
Deliberately the SAME mechanism (local clone -> GitHub raw, committed snapshot, offline
reads) rather than a submodule or a fetch step; ``tests/`` runs offline by construction.

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

import hashlib
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

# ---------------------------------------------------------------------------
# Request-signing conformance vectors (#1291 B3, salesagent-z6nr.14)
# ---------------------------------------------------------------------------
#
# These are NOT schemas — they are the graded conformance data for the RFC 9421
# request-signing profile: 12 positive + 28 negative request vectors, the runner
# keypairs, and 31 URL-canonicalization cases. They live in their own fixture
# tree because they are loaded by a different loader and pinned by a different
# guard, but they are vendored by THIS script so there is one refresh command.
VECTORS_REV = "v3.1.1"
VECTORS_SPEC_VERSION = "3.1.1"
VECTORS_SRC = "dist/compliance/3.1.1/test-vectors/request-signing"
VECTORS_DIR = Path(__file__).parent.parent / "adcp_conformance_vectors" / "3.1.1" / "request-signing"


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


def _list_local(rev: str, path: str) -> list[str] | None:
    r = subprocess.run(
        ["git", "-C", str(LOCAL_CLONE), "ls-tree", "-r", "--name-only", rev, "--", path],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    return [line for line in r.stdout.splitlines() if line.strip()]


def _read_local_path(rev: str, path: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(LOCAL_CLONE), "show", f"{rev}:{path}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else None


def _read_github_path(rev: str, path: str) -> str:
    url = f"https://raw.githubusercontent.com/{REPO}/{rev}/{path}"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (pinned host)
        return resp.read().decode()


def vendor_signing_vectors() -> int:
    """Vendor the request-signing conformance vectors + a sha256 MANIFEST.

    The vector tree is upstream-owned and byte-pinned: the drift guard
    (``tests/unit/test_adcp_conformance_vectors_pin.py``) re-hashes every file
    against ``MANIFEST.json`` and ties ``spec_version`` to
    ``adcp.get_adcp_spec_version()``, so a local edit to a vector — or an
    ``adcp`` pin bump without a re-vendor — is a loud failure.

    Files are written BYTE-VERBATIM (no JSON re-indent): the vectors grade
    byte-level canonicalization, so reformatting them would be editing the
    evidence.
    """
    # GitHub raw cannot list a directory. With no local clone we re-fetch exactly
    # the file set the committed MANIFEST already records — enough to re-verify a
    # snapshot offline-first, while a NEW upstream file needs a clone. The drift
    # guard's explicit counts (12 positive / 28 negative / 31 canonicalization)
    # are what stop that from silently shrinking the graded set.
    paths = _list_local(VECTORS_REV, VECTORS_SRC)
    if paths is None:
        prior = VECTORS_DIR / "MANIFEST.json"
        if not prior.exists():
            raise SystemExit(
                f"No local adcp clone at {LOCAL_CLONE} and no committed "
                f"{prior} to enumerate from — clone adcontextprotocol/adcp first."
            )
        paths = [f"{VECTORS_SRC}/{rel}" for rel in json.loads(prior.read_text())["files"]]
    manifest: dict[str, str] = {}
    for path in sorted(paths):
        rel = path[len(VECTORS_SRC) + 1 :]
        body = _read_local_path(VECTORS_REV, path) or _read_github_path(VECTORS_REV, path)
        out = VECTORS_DIR / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body)
        manifest[rel] = hashlib.sha256(body.encode()).hexdigest()
    (VECTORS_DIR / "MANIFEST.json").write_text(
        json.dumps(
            {
                "spec_version": VECTORS_SPEC_VERSION,
                "source_tag": VECTORS_REV,
                "source_path": VECTORS_SRC,
                "files": manifest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"vendored {len(manifest)} conformance-vector files from {REPO}@{VECTORS_REV} into {VECTORS_DIR}")
    return len(manifest)


def main() -> None:
    vendor(ROOTS, rev=PINNED_SHA, src_prefix=SRC_PREFIX)
    vendor(V311_ROOTS, rev=V311_REV, src_prefix=V311_SRC_PREFIX)
    vendor_signing_vectors()


if __name__ == "__main__":
    main()

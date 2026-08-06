#!/usr/bin/env python3
"""Refresh the pinned AdCP legacy webhook-HMAC test vectors used by test_webhook_hmac_vectors.

Source of truth: adcontextprotocol/adcp @ tag v3.1.1
    (commit 467fd93d77112baf9e094e18980119edcd3a4d07)

This is the repo's PINNED AdCP spec version (docs/adcp-spec-version.md). The
upstream adcp repo ships constantly; we deliberately do NOT track its default
branch. The vectors are NOT bundled in the installed `adcp` PyPI package (verified:
absent from adcp==6.6.0's site-packages tree) -- they only exist in the spec
SOURCE repo, so they are vendored here (committed) and the test reads them
offline, mirroring tests/fixtures/adcp_schemas_pinned/_refresh.py's pattern for
the same reason (CI/other machines don't have ~/projects/adcp checked out).

Source path: static/test-vectors/webhook-hmac-sha256.json

To refresh (e.g. to advance the pinned tag -- a deliberate, reviewed change,
done in lockstep with docs/adcp-spec-version.md):
    uv run python tests/fixtures/adcp_webhook_vectors_pinned/_refresh.py

It reads from a local clone at ~/projects/adcp if present (faster), else GitHub raw.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

PINNED_SHA = "467fd93d77112baf9e094e18980119edcd3a4d07"  # tag v3.1.1
REPO = "adcontextprotocol/adcp"
SRC_PATH = "static/test-vectors/webhook-hmac-sha256.json"
LOCAL_CLONE = Path.home() / "projects" / "adcp"
FIXTURE_DIR = Path(__file__).parent
OUT_FILE = FIXTURE_DIR / "webhook-hmac-sha256.json"


def _read_local() -> str | None:
    r = subprocess.run(
        ["git", "-C", str(LOCAL_CLONE), "show", f"{PINNED_SHA}:{SRC_PATH}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else None


def _read_github() -> str:
    url = f"https://raw.githubusercontent.com/{REPO}/{PINNED_SHA}/{SRC_PATH}"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (pinned host)
        return resp.read().decode()


def main() -> None:
    body = _read_local() or _read_github()
    OUT_FILE.write_text(json.dumps(json.loads(body), indent=2) + "\n")
    print(f"vendored {SRC_PATH} from {REPO}@{PINNED_SHA[:9]} into {OUT_FILE}")


if __name__ == "__main__":
    main()

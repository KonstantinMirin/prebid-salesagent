"""Shared parser for line-based known-failures ledger files.

One nodeid-equivalent identifier per line, ``#``-prefixed comments and blank
lines dropped. Used by every ledger loader + its lock test (e.g.
``tests/bdd/e2e_rest_known_failures.txt`` and
``tests/storyboard/known_failures.txt``) so the parse logic has exactly one
implementation instead of being copy-pasted per ledger.
"""

from __future__ import annotations

from pathlib import Path


def load_ledger_nodeids(path: Path) -> frozenset[str]:
    """Parse a line-based known-failures ledger file into a frozenset of ids."""
    return frozenset(
        line.strip() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
    )

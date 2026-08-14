"""Single owner for the conformance-ledger check-id grammar and curated YAML loaders.

Before this module, the ledger check-id grammar (``test_storyboard_check[protocol::
track::storyboard::step]``) had two parsers: ``storyboard_roadmap._ledgered_failures``
owned the regex, and ``storyboard_check_index._ledger_steps`` reached into that
module's underscore-private ``_LEDGER_ID_RE`` as a sibling view — the exact pattern
this repo's structural guards ban for ``storyboard_spec`` primitives, just not yet
enforced here. The two curated YAML loaders (the issue map, the wireability map) had
the same shape: one lived behind ``storyboard_roadmap._load_issue_map`` and was
reached into privately by ``storyboard_check_index``; the other was local to
``storyboard_check_index`` alone. This module is the one owner for all of it.

``LedgerCheckId`` is a LOSSLESS identity record: ``parse(line).format()`` reconstructs
the bracket content exactly, with no normalization baked in. The ledger spells
hyphenated ``universal/`` storyboard stems with underscores (per the runner's own
emission), while ``storyboard_coverage_map``'s stems stay hyphenated — joining raw
silently matched nothing before that was understood. Normalizing inside ``parse()``
would make identity lossy (a hyphenated segment could never round-trip), so the
hyphen-to-underscore join spelling lives on the derived ``storyboard_key`` property
instead; callers that join against ``storyboard_coverage_map`` use ``storyboard_key``,
never ``storyboard_id``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ledger ids are `protocol::track::storyboard::step` (the protocol segment arrived
# with A2A grading). Storyboard is the THIRD segment; a three-group pattern silently
# read the track as the storyboard and joined nothing -- caught by callers' zero-join
# guards rather than by rendering every row green.
_LEDGER_ID_RE = re.compile(r"test_storyboard_check\[([^:]+)::([^:]*)::([^:]+)::(.+)\]\s*$")


@dataclass(frozen=True)
class LedgerCheckId:
    """One ``(protocol, track, storyboard_id, step_id)`` conformance-ledger key.

    ``storyboard_id`` is the RAW segment as parsed — identity, must round-trip.
    ``storyboard_key`` is the derived, normalized join spelling.
    """

    protocol: str
    track: str
    storyboard_id: str
    step_id: str

    @classmethod
    def parse(cls, line: str) -> LedgerCheckId | None:
        """Parse one ledger line (or any line containing the bracket grammar).

        Uses ``.search()``, not ``.match()`` — real ledger lines carry a full
        nodeid prefix (``tests/storyboard/test_storyboard_conformance.py::``)
        before the bracket expression this grammar owns. Returns ``None`` on a
        non-matching line (comment, prose, or a grammar-drifted short form)
        rather than raising — callers that must fail loudly on a malformed
        entry do so themselves (see ``load()`` below, and
        ``test_storyboard_ledger_state.py``'s own assertion).
        """
        match = _LEDGER_ID_RE.search(line.strip())
        if not match:
            return None
        return cls(
            protocol=match.group(1),
            track=match.group(2),
            storyboard_id=match.group(3),
            step_id=match.group(4),
        )

    def format(self) -> str:
        """The bracket-content spelling: what ``parse()`` consumed, byte for byte.

        Not a full nodeid — the module path and function name
        (``test_storyboard_check[...]``) are pytest's concern (the producer at
        ``tests/storyboard/test_storyboard_conformance.py``'s
        ``pytest_generate_tests``), not the grammar's.
        """
        return f"{self.protocol}::{self.track}::{self.storyboard_id}::{self.step_id}"

    @property
    def storyboard_key(self) -> str:
        """The derived, normalized join spelling every consumer groups on.

        Hyphen -> underscore: the ledger carries the runner's underscore
        spelling (``webhook_emission``) while ``storyboard_coverage_map``
        stems are hyphenated for ``universal/`` (``webhook-emission``).
        """
        return self.storyboard_id.replace("-", "_")


LEDGER = Path("tests") / "storyboard" / "known_failures.txt"


def load(path: Path) -> list[LedgerCheckId]:
    """Parse every line of a ledger file into ``LedgerCheckId``.

    Blank lines and ``#``-prefixed comments are skipped; a line that does not
    match the grammar is silently skipped too (same behavior as the two
    call sites this replaces — a malformed line is a ledger authoring bug,
    not this loader's failure to surface).
    """
    if not path.is_file():
        return []
    ids: list[LedgerCheckId] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parsed = LedgerCheckId.parse(stripped)
        if parsed is not None:
            ids.append(parsed)
    return ids


ISSUE_MAP = Path("docs") / "test-obligations" / "storyboard-issue-map.yaml"


def load_issue_map(repo: Path) -> dict[str, dict[str, Any]]:
    """Curated storyboard -> GitHub-issue map. The one hand-maintained input here.

    Keyed by STORYBOARD, deliberately. A scenario-keyed cross-reference cannot
    express "this storyboard has no scenario but issue #N tracks the gap" --
    the majority case among on-path storyboards. Keying on the storyboard is
    what lets an uncovered gap carry a ticket, or be explicitly marked as
    carrying none.

    A `coverage: none` row with no issues is a real answer, not a hole: it
    means the pinned spec grades this, we do not test it, and nobody is
    tracking it.
    """
    import yaml

    path = repo / ISSUE_MAP
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded.get("storyboards") or {}


WIREABILITY = Path("docs") / "test-obligations" / "storyboard-wireability.yaml"


def load_wireability(repo: Path) -> dict[str, dict[str, Any]]:
    """Curated (storyboard, step) -> e2e-wireability verdict.

    The one judgement in the check index no program can derive: whether a
    step can be driven and observed from outside a running agent. Same
    status as the issue map -- curated, reviewable, joined rather than
    inferred.
    """
    import yaml

    path = repo / WIREABILITY
    if not path.is_file():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("steps") or {}


def load_wireability_untriaged(repo: Path) -> set[str]:
    """``(storyboard, step)`` keys explicitly deferred rather than assessed.

    A step can legitimately have no verdict yet -- someone has to look at it
    -- but that is a stated decision, not a silent absence. This is the
    curated escape hatch ``test_architecture_storyboard_wireability.py``
    checks against: a graded step missing from ``load_wireability()`` fails
    the guard UNLESS its key also appears here.
    """
    import yaml

    path = repo / WIREABILITY
    if not path.is_file():
        return set()
    return set((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("untriaged") or [])

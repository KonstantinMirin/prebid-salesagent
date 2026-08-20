"""Guard: MediaBuyRepository is the only writer of ``revision`` and ``confirmed_at``.

Both fields are repository-managed by construction. ``revision`` is the buyer's
optimistic-concurrency token, so it must be bumped by exactly one code path that
cannot be forgotten; ``confirmed_at`` is the seller-commitment instant and is
write-once. Any assignment to either field outside
``src/core/database/repositories/`` re-opens the hole that PR #1941's review
found: a by-construction contract re-implemented as a compensating call that a
future writer forgets to make.

**This guard is a forward-lock, not a first-run red.** It is GREEN at the commit
that introduces it — measured: the only assignments to these two attributes
anywhere in ``src/`` are the two inside
``src/core/database/repositories/media_buy.py``. Its grade is therefore the
MUTATION, not the first run: move either of those writes (or any new stamp/bump
the lane adds) outside ``repositories/`` and this test must go red. The
``test_detector_*`` cases below are the standing non-vacuity proof that the
detector can actually see such a write.

Deliberately NOT guarded: ``.status``. Too many unrelated entities own a status
column, so a ``.status`` scan would be noise rather than a seam.

Precedent: ``tests/unit/test_architecture_no_raw_media_package_select.py``.

GH #1941 (the media-buy write seam)
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    format_failure,
    parse_module,
    repo_root,
    src_python_files,
)

# The repository package is the ONLY place allowed to write these fields.
REPOSITORY_DIR = "src/core/database/repositories/"

# Fields whose value is owned by MediaBuyRepository, by construction.
GUARDED_FIELDS = frozenset({"revision", "confirmed_at"})

_KNOWN_BAD_SNIPPETS = {
    "plain_assign_revision": "def f(media_buy):\n    media_buy.revision = 2",
    "plain_assign_confirmed_at": "def f(mb, now):\n    mb.confirmed_at = now",
    "self_attr_assign": "def f(self, now):\n    self.media_buy.confirmed_at = now",
    "aug_assign": "def f(media_buy):\n    media_buy.revision += 1",
    "annotated_assign": "def f(media_buy):\n    media_buy.revision: int = 7",
    "tuple_target": "def f(mb, now):\n    mb.confirmed_at, other = now, None",
    "setattr_literal": 'def f(mb, now):\n    setattr(mb, "confirmed_at", now)',
    "constructor_keyword": "def f(now):\n    return MediaBuy(confirmed_at=now, revision=99)",
    "constructor_keyword_qualified": "def f(now):\n    return models.MediaBuy(revision=7)",
}

# The ORM row whose columns the repository owns. Construction is a write: a row
# built with ``confirmed_at`` already set never passed ``_stamp_confirmation_if_needed``,
# which is the state the seam exists to prevent.
ORM_MODEL_NAME = "MediaBuy"


def _attribute_targets(node: ast.AST) -> list[ast.Attribute]:
    """Every ``ast.Attribute`` written by an assignment-like *node*."""
    if isinstance(node, ast.Assign):
        targets: list[ast.expr] = list(node.targets)
    elif isinstance(node, ast.AugAssign | ast.AnnAssign):
        targets = [node.target]
    else:
        return []

    found: list[ast.Attribute] = []
    for target in targets:
        # Unpacking (``a.revision, b = ...``) writes each element.
        elements = target.elts if isinstance(target, ast.Tuple | ast.List) else [target]
        found.extend(el for el in elements if isinstance(el, ast.Attribute))
    return found


def _called_name(func: ast.expr) -> str | None:
    """The bare name a call targets: ``MediaBuy`` for both ``MediaBuy`` and ``models.MediaBuy``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_orm_construction_with_guarded_field(node: ast.AST) -> bool:
    """True for ``MediaBuy(confirmed_at=...)`` / ``MediaBuy(revision=...)``, however qualified.

    Both conditions are load-bearing. The name alone is not enough: ``MediaBuy`` also
    names an adcp capabilities DTO (``src/core/tools/capabilities.py``) and a schema stub
    (``src/adapters/xandr.py``), neither of which is the row. The guarded KEYWORD is what
    identifies the ORM model — no other ``MediaBuy`` declares either field, so passing one
    to them raises ``TypeError`` rather than writing anything.
    """
    if not isinstance(node, ast.Call) or _called_name(node.func) != ORM_MODEL_NAME:
        return False
    return any(kw.arg in GUARDED_FIELDS for kw in node.keywords)


def find_media_buy_write_seam_violations(tree: ast.Module) -> list[int]:
    """Return line numbers of writes to a guarded field in *tree*.

    Catches attribute assignment (plain, augmented, annotated, and unpacked), the
    ``setattr(obj, "<field>", ...)`` string-literal escape hatch, and construction of the
    ORM row with a guarded field as a constructor keyword. The last shape is a write the
    guard originally missed: assignment and ``setattr`` model mutation of an existing row,
    but a row can be born with ``confirmed_at`` already set, having never passed
    ``_stamp_confirmation_if_needed``.
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        lines.extend(attr.lineno for attr in _attribute_targets(node) if attr.attr in GUARDED_FIELDS)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in GUARDED_FIELDS
        ):
            lines.append(node.lineno)
        if _is_orm_construction_with_guarded_field(node):
            lines.append(node.lineno)
    return sorted(lines)


def _scan_src(*, inside_repositories: bool) -> list[str]:
    """Return ``"<rel-path>:<line>"`` for every guarded-field write in (or outside) the seam."""
    repo = repo_root()
    hits: list[str] = []
    for path in src_python_files(repo):
        rel = str(path.relative_to(repo))
        if rel.startswith(REPOSITORY_DIR) is not inside_repositories:
            continue
        hits.extend(f"{rel}:{lineno}" for lineno in find_media_buy_write_seam_violations(parse_module(path)))
    return sorted(hits)


@pytest.mark.arch_guard
def test_no_media_buy_write_seam_bypass() -> None:
    """Nothing outside the repository package writes ``revision`` or ``confirmed_at``.

    Zero allowlist entries, by design: a site that cannot be routed through
    MediaBuyRepository is an escalation, not an allowlist entry.
    """
    violations = _scan_src(inside_repositories=False)
    assert not violations, format_failure(
        summary=f"{sorted(GUARDED_FIELDS)} are MediaBuyRepository-owned — nothing outside it may write them",
        violations=violations,
        fix_hint=(
            "Route the write through MediaBuyRepository: update_status / update_fields stamp "
            "confirmed_at and bump revision for you, and the package writers bump the parent. "
            "Do NOT add an allowlist entry — this guard ships with none."
        ),
        docs_link="docs/development/structural-guards.md",
    )


@pytest.mark.arch_guard
def test_detector_catches_known_bad_snippets() -> None:
    """Non-vacuity: the detector sees each shape a bypass could take."""
    assert_detector_catches_ast_snippets(find_media_buy_write_seam_violations, snippets=_KNOWN_BAD_SNIPPETS)


@pytest.mark.arch_guard
def test_detector_finds_the_real_repository_writes() -> None:
    """Non-vacuity against production: the seam itself must trip the detector.

    A scan that silently visits nothing (wrong root, wrong prefix, a detector that
    only matches synthetic snippets) would pass ``test_no_media_buy_write_seam_bypass``
    vacuously. The repository's own two writes are the fixed point that proves the
    scan reaches real ``src/`` code.
    """
    seam_writes = _scan_src(inside_repositories=True)
    assert seam_writes, "Detector found no guarded-field write inside " + REPOSITORY_DIR

    repo = repo_root()
    written_fields = {
        attr.attr
        for path in src_python_files(repo)
        if str(path.relative_to(repo)).startswith(REPOSITORY_DIR)
        for node in ast.walk(parse_module(path))
        for attr in _attribute_targets(node)
        if attr.attr in GUARDED_FIELDS
    }
    assert written_fields == GUARDED_FIELDS, (
        f"Expected the repository package to write every guarded field {sorted(GUARDED_FIELDS)}, "
        f"but the detector only saw {sorted(written_fields)}. Either a write moved out of the "
        f"seam (that is the regression this guard exists for) or the detector stopped matching it."
    )

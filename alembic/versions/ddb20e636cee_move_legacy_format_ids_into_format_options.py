"""move legacy-only format contracts into format_options

A DATA MIGRATION, by the owner's ruling for this work: data in old rows is moved by a
migration, never accommodated by read-time compatibility code.

canonical-formats-migration.mdx § Seller migration, step 1 (v3.2.7): "Move each product's
creative contract into format_options[]." ``core/product.json`` makes it normative: "New 3.2
products MUST carry format_options" and, on ``format_ids``, "Deprecated in AdCP 3.2; removed
in AdCP 4.0." Every authoring path in this seller now writes the canonical arm, but rows
authored before that still carry their whole contract in ``format_ids``. A product linked to
an inventory profile takes its contract from the profile (``Product.format_contract``), so
profiles are moved too.

THE PROJECTION IS THE PINNED SDK'S, not a table typed here.
``adcp.canonical_formats.project_legacy_format_id`` walks the registry's normative order and
fails closed ("Legacy -> canonical projection follows the registry's normative order and
fails closed", RFC 002 L2). Each declaration it returns carries the SDK's stable
``format_option_id`` for the legacy tuple (``migrated_<hash>``), and this migration adds the
one fact the SDK cannot know: ``v1_format_ref`` naming the exact format_id the row carried.
That is the seller asserting the named format it authored, so the derived legacy projection
(``CanonicalFormats.format_ids``) serves a 3.x buyer the same ``format_ids`` it was served
before. Nothing is synthesized from a kind: the ref is the stored value, verbatim.

ALL OR NOTHING PER ROW. A row moves only when EVERY one of its format_ids projects. Moving a
subset would shrink the row's contract, because once a canonical arm exists the stored
legacy column is no longer read. A row with any unprojectable id (a custom creative agent's
format, an id the registry does not map) keeps its legacy arm, which the 3.x anyOf still
admits, and is named in the migration's output so an operator can author its declarations.

The stored ``format_ids`` of a moved row is cleared, as the admin edit form clears it when
an operator authors the canonical arm: a column kept beside the declarations would be the
"second authored catalog" canonical-formats.mdx's producer rules forbid.

``downgrade`` is the exact inverse for the rows this revision moved, recognised by their
SDK-minted ``migrated_`` option ids: it puts each declaration's ``v1_format_ref`` back into
``format_ids`` and clears ``format_options``. No backup table and no copy of the old value is
kept; the ref the upgrade writes is the served legacy projection, not a restore point.

Revision ID: ddb20e636cee
Revises: 5c1e7a9d3b42
Create Date: 2026-10-29 18:00:00.000000

"""

import json
import logging
from collections.abc import Iterable, Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ddb20e636cee"
down_revision: str | Sequence[str] | None = "5c1e7a9d3b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

#: The two tables whose rows carry a format contract, and the columns that key a row.
_TABLES: dict[str, tuple[str, ...]] = {
    "products": ("tenant_id", "product_id"),
    "inventory_profiles": ("id",),
}

#: The prefix ``adcp.canonical_formats.migrated_format_option_id`` gives every option id it
#: mints from a legacy tuple. Only this revision writes such ids into a stored row.
_MIGRATED_PREFIX = "migrated_"


def plan_canonical_moves(
    rows: Iterable[tuple[Any, Any]],
) -> tuple[list[tuple[Any, list[dict[str, Any]]]], list[Any]]:
    """``(rows to move with their declarations, keys of rows that cannot move)``.

    Each input row is ``(key, format_ids)`` for a row with no canonical arm. A row with no
    legacy arm either is not a move and is left out of both lists.

    Separate from the SQL so the part that can be wrong -- which declaration each format_id
    becomes, and which rows are left alone -- is testable without a database
    (``tests/unit/test_move_legacy_format_ids_migration_plan.py``). The SDK is imported
    inside: alembic imports every revision to build its graph, and that must not depend on
    the SDK being importable.
    """
    from adcp.canonical_formats import project_legacy_format_id

    moves: list[tuple[Any, list[dict[str, Any]]]] = []
    unmovable: list[Any] = []
    for key, format_ids in rows:
        if not format_ids:
            continue
        declarations: list[dict[str, Any]] = []
        for index, format_id in enumerate(format_ids):
            projected = project_legacy_format_id(format_id, product_id=str(key), field=f"format_ids[{index}]")
            if projected.declaration is None:
                break
            declaration = projected.declaration.model_dump(mode="json", exclude_none=True)
            declaration["v1_format_ref"] = [format_id]
            declarations.append(declaration)
        else:
            moves.append((key, declarations))
            continue
        unmovable.append(key)
    return moves, unmovable


def plan_legacy_restores(rows: Iterable[tuple[Any, Any]]) -> list[tuple[Any, list[Any]]]:
    """``(key, format_ids)`` for each row whose declarations this revision wrote.

    Each input row is ``(key, format_options)``. A row qualifies only when every declaration
    carries a ``migrated_`` option id and exactly one ``v1_format_ref``, which is the shape
    :func:`plan_canonical_moves` writes; anything an operator authored is left alone.
    """
    restores: list[tuple[Any, list[Any]]] = []
    for key, declarations in rows:
        if not declarations:
            continue
        if all(
            str(declaration.get("format_option_id", "")).startswith(_MIGRATED_PREFIX)
            and len(declaration.get("v1_format_ref") or []) == 1
            for declaration in declarations
        ):
            restores.append((key, [declaration["v1_format_ref"][0] for declaration in declarations]))
    return restores


def _where(key_columns: tuple[str, ...]) -> str:
    return " AND ".join(f"{column} = :{column}" for column in key_columns)


def _key_params(key_columns: tuple[str, ...], key: Any) -> dict[str, Any]:
    return dict(zip(key_columns, key, strict=True))


def upgrade() -> None:
    """Move each legacy-only row's contract into ``format_options`` where it projects."""
    bind = op.get_bind()
    for table, key_columns in _TABLES.items():
        rows = bind.execute(
            sa.text(f"SELECT {', '.join(key_columns)}, format_ids FROM {table} WHERE format_options IS NULL")
        ).fetchall()
        moves, unmovable = plan_canonical_moves((tuple(row[:-1]), row[-1]) for row in rows)
        for key, declarations in moves:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET format_options = CAST(:format_options AS jsonb), format_ids = NULL "
                    f"WHERE {_where(key_columns)}"
                ),
                {"format_options": json.dumps(declarations), **_key_params(key_columns, key)},
            )
        if unmovable:
            logger.warning(
                "%s: %d row(s) keep their legacy format_ids because at least one id has no canonical "
                "projection; author their format_options by hand: %s",
                table,
                len(unmovable),
                ", ".join("/".join(str(part) for part in key) for key in unmovable),
            )


def downgrade() -> None:
    """Put back the legacy arm of every row this revision moved."""
    bind = op.get_bind()
    for table, key_columns in _TABLES.items():
        rows = bind.execute(
            sa.text(f"SELECT {', '.join(key_columns)}, format_options FROM {table} WHERE format_ids IS NULL")
        ).fetchall()
        for key, format_ids in plan_legacy_restores((tuple(row[:-1]), row[-1]) for row in rows):
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET format_ids = CAST(:format_ids AS jsonb), format_options = NULL "
                    f"WHERE {_where(key_columns)}"
                ),
                {"format_ids": json.dumps(format_ids), **_key_params(key_columns, key)},
            )

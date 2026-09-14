"""migrate legacy flat geo targeting keys in media_packages.package_config

Revision ID: f7c3a9d21b64
Revises: e4b7c2a91f05
Create Date: 2026-09-14 10:00:00.000000

"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7c3a9d21b64"
down_revision: str | Sequence[str] | None = "e4b7c2a91f05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKUP_TABLE = "media_packages_legacy_geo_backup"

#: The keys ``package_config`` may hold the targeting document under.
_DOC_KEYS = ("targeting_overlay", "targeting")

#: Legacy flat key -> (v3 structured key, transform). This is the mapping
#: ``Targeting.normalize_legacy_geo`` applied on every validation before it was deleted:
#: a stored document that does not fit its model is migrated once, not rewritten on read.
_LEGACY_GEO_FIELDS: list[tuple[str, str, Any]] = [
    ("geo_country_any_of", "geo_countries", None),
    ("geo_country_none_of", "geo_countries_exclude", None),
    ("geo_region_any_of", "geo_regions", lambda v: [r if "-" in r else f"US-{r}" for r in v]),
    ("geo_region_none_of", "geo_regions_exclude", lambda v: [r if "-" in r else f"US-{r}" for r in v]),
    ("geo_metro_any_of", "geo_metros", lambda v: [{"system": "nielsen_dma", "values": v}]),
    ("geo_metro_none_of", "geo_metros_exclude", lambda v: [{"system": "nielsen_dma", "values": v}]),
    ("geo_zip_any_of", "geo_postal_areas", lambda v: [{"system": "us_zip", "values": v}]),
    ("geo_zip_none_of", "geo_postal_areas_exclude", lambda v: [{"system": "us_zip", "values": v}]),
]

#: Removed in v3 with no structured successor: dropped.
_CITY_KEYS = ("geo_city_any_of", "geo_city_none_of")

LEGACY_KEYS = frozenset(k for k, _, _ in _LEGACY_GEO_FIELDS) | frozenset(_CITY_KEYS)


def upgrade_targeting_doc(doc: dict[str, Any]) -> dict[str, Any] | None:
    """The v3 form of one stored targeting document, or ``None`` if it carries no legacy key.

    Pure, so the rule can be checked without a database. A legacy key is removed; its
    value moves to the structured key only when that key is absent, so a document that
    already carries both keeps the structured one.
    """
    if not any(key in doc for key in LEGACY_KEYS):
        return None
    out = dict(doc)
    for legacy_key, v3_key, transform in _LEGACY_GEO_FIELDS:
        if legacy_key not in out:
            continue
        value = out.pop(legacy_key)
        if value and v3_key not in out:
            out[v3_key] = transform(value) if transform else value
    for key in _CITY_KEYS:
        out.pop(key, None)
    return out


def upgrade_package_config(package_config: dict[str, Any]) -> dict[str, Any] | None:
    """The package_config with every targeting document migrated, or ``None`` if untouched."""
    out: dict[str, Any] | None = None
    for doc_key in _DOC_KEYS:
        doc = package_config.get(doc_key)
        if not isinstance(doc, dict):
            continue
        migrated = upgrade_targeting_doc(doc)
        if migrated is not None:
            out = out if out is not None else dict(package_config)
            out[doc_key] = migrated
    return out


def upgrade() -> None:
    """Rewrite legacy flat geo keys into the v3 structured fields, once, in the stored rows.

    Every touched row is first copied to ``media_packages_legacy_geo_backup`` so the
    downgrade restores the exact prior document rather than guessing an inverse mapping.
    Rows without a legacy key are not read into the backup and are not written.
    """
    connection = op.get_bind()
    op.create_table(
        BACKUP_TABLE,
        sa.Column("media_buy_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("package_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("package_config", sa.Text(), nullable=False),
    )
    rows = connection.execute(
        sa.text(
            # ``->`` rather than the ``?`` key-exists operator: ``?`` collides with the
            # DBAPI placeholder syntax under psycopg2 (see 319e6b366151).
            "SELECT media_buy_id, package_id, package_config FROM media_packages "
            "WHERE (package_config::jsonb)->'targeting_overlay' IS NOT NULL "
            "OR (package_config::jsonb)->'targeting' IS NOT NULL"
        )
    ).fetchall()
    for media_buy_id, package_id, package_config in rows:
        config = package_config if isinstance(package_config, dict) else json.loads(package_config)
        migrated = upgrade_package_config(config)
        if migrated is None:
            continue
        connection.execute(
            sa.text(
                f"INSERT INTO {BACKUP_TABLE} (media_buy_id, package_id, package_config) "
                "VALUES (:media_buy_id, :package_id, :package_config)"
            ),
            {"media_buy_id": media_buy_id, "package_id": package_id, "package_config": json.dumps(config)},
        )
        connection.execute(
            sa.text(
                "UPDATE media_packages SET package_config = CAST(:package_config AS jsonb) "
                "WHERE media_buy_id = :media_buy_id AND package_id = :package_id"
            ),
            {"media_buy_id": media_buy_id, "package_id": package_id, "package_config": json.dumps(migrated)},
        )


def downgrade() -> None:
    """Restore every migrated row from the backup table, then drop the backup."""
    op.execute(
        f"UPDATE media_packages AS mp SET package_config = CAST(b.package_config AS jsonb) "
        f"FROM {BACKUP_TABLE} AS b WHERE mp.media_buy_id = b.media_buy_id AND mp.package_id = b.package_id"
    )
    op.drop_table(BACKUP_TABLE)

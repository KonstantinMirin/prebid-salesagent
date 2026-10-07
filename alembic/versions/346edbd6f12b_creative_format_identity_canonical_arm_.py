"""creative format identity: canonical arm alongside the legacy pair

AdCP 3.2 identifies a creative by EITHER the deprecated ``format_id`` (agent_url + id) OR
the canonical ``format_kind`` plus an optional ``format_option_ref``, mutually exclusive,
exactly one. This table could only store the first: ``agent_url`` and ``format`` were both
NOT NULL, so a canonical creative had nowhere to go.

Four structural changes, no data touched:

* ``format_kind`` and ``format_option_ref`` added, both nullable — the canonical arm.
* ``agent_url`` and ``format`` relaxed to nullable — they ARE the deprecated arm, and a
  creative that carries the canonical one supplies neither.

The exclusivity is not expressed as a CHECK constraint. It is a protocol rule the request
and state models both enforce as a ``oneOf`` on the way in, and the one reader that turns a
row back into a creative asks ``creative_format_identity`` which arm is present. A fifth
place to state the same rule is a fifth place for it to drift.

``format_option_ref`` is JSON because the thing it stores is an object, not a scalar:
``core/format-option-ref.json`` is itself a oneOf over publisher scope
(``publisher_domain`` + ``format_option_id``) and product scope (``format_option_id``).

Revision ID: 346edbd6f12b
Revises: 7f31c0ab94d2
Create Date: 2026-10-07 11:54:16.822830

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.core.database.json_type import JSONType

# revision identifiers, used by Alembic.
revision: str = "346edbd6f12b"
down_revision: str | Sequence[str] | None = "7f31c0ab94d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the canonical arm; relax the legacy arm to nullable."""
    op.add_column("creatives", sa.Column("format_kind", sa.String(100), nullable=True))
    op.add_column("creatives", sa.Column("format_option_ref", JSONType(), nullable=True))
    op.alter_column("creatives", "agent_url", existing_type=sa.String(500), nullable=True)
    op.alter_column("creatives", "format", existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    """Drop the canonical arm; restore the legacy arm as NOT NULL."""
    op.alter_column("creatives", "format", existing_type=sa.String(100), nullable=False)
    op.alter_column("creatives", "agent_url", existing_type=sa.String(500), nullable=False)
    op.drop_column("creatives", "format_option_ref")
    op.drop_column("creatives", "format_kind")

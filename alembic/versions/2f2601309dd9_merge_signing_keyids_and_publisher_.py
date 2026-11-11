"""merge signing keyids and publisher adagents heads

Revision ID: 2f2601309dd9
Revises: b8d3e5f1a207, e2af0c242a7f
Create Date: 2026-11-11 15:29:13.696414

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2f2601309dd9"
down_revision: str | Sequence[str] | None = ("b8d3e5f1a207", "e2af0c242a7f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

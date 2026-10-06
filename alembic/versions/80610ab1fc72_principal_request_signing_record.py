"""principal request_signing record

Adds ``principals.request_signing``: the counterparty's request-signing keys, pinned at
onboarding, with its per-counterparty replay tuning (src/core/signing/onboarding.py). A record
requires an ``agent_url``, because that URL is the ``agents[]`` entry its keyids resolve to.

Revision ID: 80610ab1fc72
Revises: 7f31c0ab94d2
Create Date: 2026-10-06 11:39:47.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "80610ab1fc72"
down_revision: str | Sequence[str] | None = "7f31c0ab94d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("principals", sa.Column("request_signing", postgresql.JSONB(), nullable=True))
    op.create_check_constraint(
        "ck_principals_request_signing_agent_url",
        "principals",
        "request_signing IS NULL OR agent_url IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_principals_request_signing_agent_url", "principals", type_="check")
    op.drop_column("principals", "request_signing")

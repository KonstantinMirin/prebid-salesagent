"""virtual_host is mandatory

Revision ID: 7f31c0ab94d2
Revises: 390461e816ea
Create Date: 2026-09-28 09:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f31c0ab94d2"
down_revision: str | Sequence[str] | None = "390461e816ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make ``tenants.virtual_host`` NOT NULL.

    A tenant declares the host it is served at, always: a request names a tenant by ``Host``
    against this column or by the ``x-adcp-tenant`` literal id (#2191), so a row holding NULL
    is unreachable by ``Host`` at all.

    This REFUSES rather than backfills. A migration cannot know where a deployment answers,
    and any host it could invent is a name nothing serves, published on that tenant's agent
    card as its own (#1845). The operator can know, so the refusal names each offending row
    and carries the statement that fixes it. Rows are not deleted either: losing a
    publisher's tenant is worse than running one UPDATE.

    A refusal changes no data in either direction, so this stays inside the structure-only
    rule: ``upgrade`` adds the constraint, ``downgrade`` removes it, and neither moves a
    value.
    """
    offenders = [
        row[0]
        for row in op.get_bind().execute(sa.text("SELECT tenant_id FROM tenants WHERE virtual_host IS NULL")).fetchall()
    ]
    if offenders:
        named = ", ".join(repr(tenant_id) for tenant_id in offenders)
        statements = "\n".join(
            f"  UPDATE tenants SET virtual_host = '<the host this tenant is served at>' "
            f"WHERE tenant_id = '{tenant_id}';"
            for tenant_id in offenders
        )
        raise RuntimeError(
            f"{len(offenders)} tenant(s) declare no virtual_host: {named}.\n"
            "virtual_host is the address a tenant is served at and the only way a request "
            "can name it, so this revision makes it mandatory. It will not guess a value: a "
            "host derived from a subdomain is a name nothing serves, published on the agent "
            "card as the tenant's own (#1845). Set each one to the host that deployment "
            "really answers at, then re-run the migration:\n"
            f"{statements}"
        )

    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    """Let ``tenants.virtual_host`` be NULL again."""
    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=True)

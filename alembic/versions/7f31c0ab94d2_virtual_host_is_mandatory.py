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
down_revision: str | Sequence[str] | None = "e7a2c40b91d5"
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

    # A host differing only in case is the SAME host, so the stored form has to be the folded
    # one: the ORM validator folds on write, `ix_tenants_virtual_host` covers the raw column,
    # and every lookup is one exact match against it. A legacy row holding `Host.com` would be
    # unreachable under that match while still occupying the name. Refused, not folded, for
    # the same reason as above — and because folding two rows that differ only in case would
    # trip the unique index mid-migration. The operator's UPDATE hits that index instead,
    # where the collision is theirs to resolve.
    unfolded = [
        row[0]
        for row in op.get_bind()
        .execute(sa.text("SELECT tenant_id FROM tenants WHERE virtual_host <> lower(virtual_host)"))
        .fetchall()
    ]
    if unfolded:
        named = ", ".join(repr(tenant_id) for tenant_id in unfolded)
        statements = "\n".join(
            f"  UPDATE tenants SET virtual_host = lower(virtual_host) WHERE tenant_id = '{tenant_id}';"
            for tenant_id in unfolded
        )
        raise RuntimeError(
            f"{len(unfolded)} tenant(s) store a virtual_host that is not case-folded: {named}.\n"
            "A host differing only in case is the same host, so this column stores the folded "
            "form and every lookup matches it exactly. Fold each row, then re-run the "
            "migration. If two rows fold to the same host, the unique index refuses the second "
            "one: those two tenants claim one address, and which of them keeps it is a "
            "decision only the operator can make:\n"
            f"{statements}"
        )

    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    """Let ``tenants.virtual_host`` be NULL again."""
    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=True)

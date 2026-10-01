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
    # The key routing resolves by is the host's NAME, port aside: the same tenant answers at
    # `host` and at `host:8443` (@T-TENANTID-host-with-port). The unique index covered the RAW
    # column, so `host` and `host:8443` were two admissible rows that BOTH matched
    # `Host: host`, and `.first()` chose between them with no ORDER BY. Indexing the
    # expression the lookup compares makes that pair unrepresentable.
    #
    # Refused rather than resolved, like the NULLs above: which of two tenants claiming one
    # name keeps it is not a decision a migration can make.
    collisions = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT lower(split_part(virtual_host, ':', 1)) AS name, string_agg(tenant_id, ', ') AS tenants "
                "FROM tenants GROUP BY 1 HAVING count(*) > 1"
            )
        )
        .fetchall()
    )
    if collisions:
        named = "\n".join(f"  {row.name!r} is claimed by: {row.tenants}" for row in collisions)
        raise RuntimeError(
            f"{len(collisions)} host name(s) are claimed by more than one tenant:\n{named}\n"
            "A port says how a deployment is reached, not which seller it is, so "
            "'host' and 'host:8443' are ONE address and only one tenant can hold it. This "
            "revision makes that a unique index. Decide which tenant keeps each name and "
            "change or deactivate the others, then re-run the migration. Case is part of it: "
            "'Host.com' and 'host.com' are the same name."
        )

    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=False)
    op.drop_index("ix_tenants_virtual_host", table_name="tenants")
    op.create_index(
        "ux_tenants_virtual_host_name",
        "tenants",
        [sa.text("lower(split_part(virtual_host, ':', 1))")],
        unique=True,
    )


def downgrade() -> None:
    """Let ``tenants.virtual_host`` be NULL again, keyed on the raw column."""
    op.drop_index("ux_tenants_virtual_host_name", table_name="tenants")
    op.create_index("ix_tenants_virtual_host", "tenants", ["virtual_host"], unique=True)
    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=True)

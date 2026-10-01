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


def _hostname_of(host: str | None) -> str:
    """*host* without its port, by stdlib.

    Inlined rather than imported from ``src.core.http_utils``: a revision has to keep
    behaving the way it did when it ran, and an application helper is free to change.
    ``urlsplit`` is the parser either way -- this takes a URL apart with no string surgery,
    which is the whole reason the derived name is a column and not an index expression.
    """
    from urllib.parse import urlsplit

    folded = (host or "").strip().lower()
    return urlsplit(f"//{folded}").hostname or folded


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

    It also adds ``virtual_host_name`` -- the host without its port -- and keys uniqueness on
    it. Populating a new NOT NULL column is initialising the structure being added, not
    preserving data across the change: ``downgrade`` drops the column outright rather than
    putting anything back, and nothing here rewrites ``virtual_host`` itself.

    Case needs no separate refusal: ``_hostname_of`` folds, so a legacy row holding
    ``Host.com`` derives ``host.com`` and routes correctly without its raw value being
    touched. DNS is case-insensitive (RFC 7230 §5.4), so the card publishing the stored
    spelling is still dialled.
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

    # The key routing resolves by is the host's NAME, port aside: the same tenant answers at
    # `host` and at `host:8443` (@T-TENANTID-host-with-port). It is stored in its own column
    # so that only stdlib ever parses the URL -- an index expression would have to take the
    # host apart in SQL, which is incorrect for a bracketed IPv6 literal.
    op.add_column("tenants", sa.Column("virtual_host_name", sa.Text(), nullable=True))

    rows = op.get_bind().execute(sa.text("SELECT tenant_id, virtual_host FROM tenants")).fetchall()
    derived = {row.tenant_id: _hostname_of(row.virtual_host) for row in rows}

    # Refused rather than resolved, like the NULLs above: which of two tenants claiming one
    # name keeps it is not a decision a migration can make.
    claimed: dict[str, list[str]] = {}
    for tenant_id, name in derived.items():
        claimed.setdefault(name, []).append(tenant_id)
    collisions = {name: ids for name, ids in claimed.items() if len(ids) > 1}
    if collisions:
        named = "\n".join(f"  {name!r} is claimed by: {', '.join(ids)}" for name, ids in sorted(collisions.items()))
        raise RuntimeError(
            f"{len(collisions)} host name(s) are claimed by more than one tenant:\n{named}\n"
            "A port says how a deployment is reached, not which seller it is, so "
            "'host' and 'host:8443' are ONE address and only one tenant can hold it. This "
            "revision makes that a unique index. Decide which tenant keeps each name and "
            "change or deactivate the others, then re-run the migration. Case is part of it: "
            "'Host.com' and 'host.com' are the same name."
        )

    for tenant_id, name in derived.items():
        op.get_bind().execute(
            sa.text("UPDATE tenants SET virtual_host_name = :name WHERE tenant_id = :tenant_id"),
            {"name": name, "tenant_id": tenant_id},
        )

    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=False)
    op.alter_column("tenants", "virtual_host_name", existing_type=sa.Text(), nullable=False)
    op.drop_index("ix_tenants_virtual_host", table_name="tenants")
    op.create_index("ux_tenants_virtual_host_name", "tenants", ["virtual_host_name"], unique=True)


def downgrade() -> None:
    """Let ``tenants.virtual_host`` be NULL again, keyed on the raw column."""
    op.drop_index("ux_tenants_virtual_host_name", table_name="tenants")
    op.create_index("ix_tenants_virtual_host", "tenants", ["virtual_host"], unique=True)
    op.drop_column("tenants", "virtual_host_name")
    op.alter_column("tenants", "virtual_host", existing_type=sa.Text(), nullable=True)

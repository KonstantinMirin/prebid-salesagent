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

    A tenant declares the host it is served at, always. Since the routing change in
    PR #2191 there are exactly two ways to name a tenant — ``Host`` against this column and
    the ``x-adcp-tenant`` literal id — so a row holding NULL is unreachable by ``Host`` at
    all, and the readers papered over it by inventing a host: the agent card published
    ``http://localhost:8080`` as such a tenant's PUBLIC A2A endpoint.

    This REFUSES rather than backfills, and that is the deliberate choice. The only
    expressions available to a backfill are ``<subdomain>.<SALES_AGENT_DOMAIN>`` and
    ``<subdomain>.example.com``, and inventing a host from one of those is exactly what took
    A2A conformance from 30 passing checks to 0 (#1845) — a name nothing on the network
    served, published on a card, followed by every client that trusted it. A migration
    cannot know where a deployment answers; the operator can, so the refusal names each
    offending row and carries the statement that fixes it. Rows are not deleted either:
    losing a publisher's tenant is worse than running one UPDATE.

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

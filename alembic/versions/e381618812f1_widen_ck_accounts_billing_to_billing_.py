"""widen ck_accounts_billing to billing-party enum

``ck_accounts_billing`` (born in 51d4f9009db4) allowed only
``('operator', 'agent')`` while the AdCP 3.1.1 billing-party enum is
``["operator", "agent", "advertiser"]`` — a spec-valid
``billing="advertiser"`` create failed the CHECK (#1521, #1592).
Widen the constraint to the full enum. The literals below are a frozen
snapshot by design; the ORM constraint derives from the SDK
``BillingParty`` enum via ``src.core.billing_policy.BILLING_PARTY_VALUES``,
guarded by ``tests/unit/test_billing_party_parity.py``.

The downgrade REFUSES rather than destroys. ``billing='advertiser'`` cannot
satisfy the two-value constraint, and the only automatic way to narrow the
CHECK is to erase those values — which is not a downgrade, it is data loss
wearing one's clothes: ``billing IS NULL`` means "the buyer never declared a
billing party" and is accepted everywhere a declared value would be gated
(``_check_billing_supported`` never rejects an omitted billing), so the
erasure would be invisible on the wire and would never self-heal — the
settings-update arm of ``sync_accounts`` INHERITS the stored value when the
entry omits ``billing``. So the downgrade surveys the affected accounts,
reports them, and stops, matching the sibling natural-key migration
(``b2e94f7c1a03``, owner decision 2026-07-27).

Revision ID: e381618812f1
Revises: 823974a5553e
Create Date: 2026-07-14 22:45:17.675465

"""

from collections.abc import Sequence

from alembic import op
from src.core.database.migration_guards import abort_if_rows

# revision identifiers, used by Alembic.
revision: str = "e381618812f1"
down_revision: str | Sequence[str] | None = "823974a5553e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_accounts_billing"

#: The accounts the narrow two-value constraint cannot admit.
_ADVERTISER_SURVEY_SQL = """
    SELECT tenant_id, account_id, name
      FROM accounts
     WHERE billing = 'advertiser'
     ORDER BY tenant_id, account_id
"""


def upgrade() -> None:
    """Recreate ck_accounts_billing with the full 3.1.1 billing-party enum."""
    op.drop_constraint(_CONSTRAINT, "accounts", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "accounts",
        "billing IS NULL OR billing IN ('operator', 'agent', 'advertiser')",
    )


def downgrade() -> None:
    """Recreate the two-value constraint, or refuse if any row needs the third.

    The survey runs BEFORE the constraint is touched, so an aborted downgrade
    leaves the widened CHECK in place and every row untouched.
    """
    abort_if_rows(
        op.get_bind(),
        _ADVERTISER_SURVEY_SQL,
        describe=lambda row: f"  tenant={row.tenant_id!r} account={row.account_id!r} name={row.name!r}",
        # Plain string, not an f-string: ``{count}`` is filled by the guard, and an
        # f-string would have to escape it as ``{{count}}`` to survive.
        headline=(
            "Cannot narrow ck_accounts_billing to ('operator', 'agent'): {count} account(s) carry billing='advertiser'."
        ),
        remedy=(
            "'advertiser' is a spec-valid billing party (AdCP 3.1.1) that the buyer declared, and the "
            "narrow constraint has no room for it. This migration will not clear those values for you: "
            "a NULL billing reads as 'never declared', is accepted by every gate that would have "
            "checked a declared value, and is inherited by the next settings-update sync — so the loss "
            "would be silent and permanent. Re-declare each account above as 'operator' or 'agent', or "
            "close it, then re-run this downgrade."
        ),
    )

    op.drop_constraint(_CONSTRAINT, "accounts", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "accounts",
        "billing IS NULL OR billing IN ('operator', 'agent')",
    )

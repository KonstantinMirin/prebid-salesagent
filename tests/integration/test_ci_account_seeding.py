"""Grade init_db's CI account seeding against a real database.

The E2E request builders reference this account by id, and `account` is in
/required on sync-creatives, create-media-buy and update-media-buy. Without the
seeded row every E2E call to those tools is refused with INVALID_REQUEST before
reaching the behavior under test, which is how this gap stayed invisible: the
E2E suite failed for a reason that looked like a production bug.
"""

import pytest
from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Account, AgentAccountAccess


@pytest.mark.requires_db
def test_ci_account_and_grant_are_seeded(integration_db, monkeypatch):
    from src.core.database.database import init_db

    # The fixture already migrated; init_db would re-run them and hit DuplicateTable.
    monkeypatch.setenv("SKIP_MIGRATIONS", "true")
    # The account lives in the demo block, beside the CI principal it belongs to.
    monkeypatch.setenv("CREATE_DEMO_TENANT", "true")

    init_db()

    with get_db_session() as s:
        acct = s.scalars(select(Account).filter_by(tenant_id="default", account_id="ci-test-account")).first()
        assert acct is not None, "init_db must seed the CI account the E2E builders reference"
        assert acct.status == "active", f"a non-active status blocks resolution, got {acct.status!r}"

        # Resolution is gated on the GRANT, not the account row alone -- without it
        # _require_account_access raises AUTHORIZATION_ERROR. The grant's FKs are
        # composite and carry no ORM relationship, so its INSERT ordering is explicit
        # in init_db; this assertion is what catches that ordering regressing.
        grant = s.scalars(
            select(AgentAccountAccess).filter_by(
                tenant_id="default", principal_id="ci-test-principal", account_id="ci-test-account"
            )
        ).first()
        assert grant is not None, "the principal must be granted access to the seeded account"

"""The ``creatives.format_kind`` NOT NULL constraint, against a MIGRATED database.

Revision ``b4f1a9c27d53`` makes the column NOT NULL and migrates existing rows by
projection. Three mechanisms keep a kindless creative out of the table -- the creation gate
that refuses an unprojectable reference, the request models' arm exclusivity, and this
constraint -- and until now none of the three was graded at the level of "what happens if it
regresses". The type-level and creation-edge halves are
``tests/unit/test_format_identity_kind_is_mandatory.py``; this is the column.

IT HAS TO BE ``migration_db`` AND CANNOT BE ``integration_db``. The latter builds its schema
with ``Base.metadata.create_all``, which constructs tables from the ORM models and therefore
reflects whatever ``models.py`` currently declares -- so it would pass whether or not the
MIGRATION creates the constraint, and a revision that forgot the ``ALTER COLUMN`` would read
green. ``migration_db`` runs alembic, which is the only place a migration-created constraint
exists at all (the same reason ``a7c31e0f45b2``'s validator function is invisible to the
integration suite).

So this grades the REVISION, not the model: the assertions below would fail if ``upgrade()``
stopped altering the column even while ``models.py`` kept saying ``nullable=False``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.migration_helpers import reset_to_revision

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_REVISION = "b4f1a9c27d53"
_PREVIOUS = "a7c31e0f45b2"

_TENANT = "mig_kind_tenant"
_PRINCIPAL = "mig_kind_principal"


@pytest.fixture
def at_revision(migration_db):
    """The database AT the NOT NULL revision, with one empty tenant and a principal."""
    engine, db_url = reset_to_revision(
        migration_db,
        revision=_REVISION,
        tenant_id=_TENANT,
        tenant_name="Migration Kind",
        subdomain="mig-kind",
    )
    with engine.begin() as conn:
        # creatives is keyed (creative_id, tenant_id, principal_id), so a row needs a
        # principal to reference.
        conn.execute(
            text(
                "INSERT INTO principals (tenant_id, principal_id, name, access_token, platform_mappings) "
                "VALUES (:t, :p, 'Migration Kind', :tok, '{}') ON CONFLICT DO NOTHING"
            ),
            {"t": _TENANT, "p": _PRINCIPAL, "tok": f"tok-{uuid.uuid4().hex[:8]}"},
        )
    return engine, db_url


def _insert(conn, *, kind: str | None) -> None:
    """One creative row, with ``format_kind`` as given. Raw SQL on purpose.

    The ORM would refuse a ``None`` before the database saw it -- which is the model's job
    and is graded elsewhere. What this file asks is whether the COLUMN refuses it, so the
    insert has to reach the column without passing through the model that also forbids it.
    """
    conn.execute(
        text(
            "INSERT INTO creatives (creative_id, tenant_id, principal_id, name, format_kind, data, status) "
            "VALUES (:cid, :t, :p, 'c', :kind, '{}', 'approved')"
        ),
        {"cid": f"cr-{uuid.uuid4().hex[:8]}", "t": _TENANT, "p": _PRINCIPAL, "kind": kind},
    )


class TestTheColumnRefusesAKindlessCreative:
    def test_a_null_format_kind_is_rejected_by_the_database(self, at_revision) -> None:
        """The constraint, observed where it actually lives.

        This is the assertion that would have caught a revision whose ``upgrade()`` projected
        the rows and then forgot to alter the column: every other check in this change reads
        ``models.py``, which says ``nullable=False`` regardless.
        """
        engine, _ = at_revision

        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert(conn, kind=None)

    def test_a_kind_bearing_creative_is_admitted(self, at_revision) -> None:
        """The control. Without it the row above passes on a database that refuses every
        insert -- a broken fixture, a missing principal, a wrong column list -- and the
        constraint would not have been what was graded.
        """
        engine, _ = at_revision

        with engine.begin() as conn:
            _insert(conn, kind="image")
            stored = (
                conn.execute(text("SELECT format_kind FROM creatives WHERE tenant_id = :t"), {"t": _TENANT})
                .scalars()
                .all()
            )

        assert stored == ["image"]


class TestTheConstraintIsWhatTheMigrationAdded:
    def test_the_previous_revision_still_admits_a_null(self, migration_db) -> None:
        """The two-point measurement: NULL is admitted BEFORE and refused AFTER.

        Without this, ``test_a_null_format_kind_is_rejected_by_the_database`` is satisfied by
        a column that was always NOT NULL, and the revision would be credited with a
        constraint it did not create. Pinned at ``_PREVIOUS`` rather than assumed, so the
        pair reads as one differential.
        """
        engine, _ = reset_to_revision(
            migration_db,
            revision=_PREVIOUS,
            tenant_id=_TENANT,
            tenant_name="Migration Kind",
            subdomain="mig-kind",
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO principals (tenant_id, principal_id, name, access_token, platform_mappings) "
                    "VALUES (:t, :p, 'Migration Kind', :tok, '{}') ON CONFLICT DO NOTHING"
                ),
                {"t": _TENANT, "p": _PRINCIPAL, "tok": f"tok-{uuid.uuid4().hex[:8]}"},
            )
            _insert(conn, kind=None)

            admitted = conn.execute(
                text("SELECT count(*) FROM creatives WHERE tenant_id = :t AND format_kind IS NULL"),
                {"t": _TENANT},
            ).scalar_one()

        assert admitted == 1

"""What ``validate_format_ids`` ACCEPTS, asked of a real migrated database.

The pin declares six properties on ``core/format-id.json`` -- ``agent_url``, ``id``,
``width``, ``height``, ``duration_ms``, ``pixel_ratio`` -- with only the first two
required. The function allowed five, so the database refused a product carrying a property
the spec defines and marks optional, and two ``e2e_rest`` rows were red on land because of
it (salesagent-knd96).

**This asks the database, not the migration source.** An earlier attempt regexed the
``allowed_keys`` literal out of one revision file and compared it to the pin. That checked
nothing: it never connected to a database, so the deployed function could be any revision
and the test passed anyway, and it was keyed on one filename, so the NEXT migration to
touch the function would leave it green against a dead revision. A guard on a spelling is
not a guard on a behaviour.

``migration_db`` rather than ``integration_db`` is the whole point. ``tests/conftest_db.py``
builds the integration schema with ``Base.metadata.create_all``, so this function does not
exist there at all -- which is why no suite but ``e2e_rest`` could see the defect
(salesagent-3cs7o.42).

Each case takes a FRESH CONNECTION. The first refusal aborts the transaction, so a shared
one reports ``InFailedSqlTransaction`` for every case after it -- which looked like four
more findings on the first hand-probe and was an artefact of the harness.
"""

from __future__ import annotations

import json
from pathlib import Path

import adcp
import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_REVISION = "a7c31e0f45b2"
_PREVIOUS = "08cd415b3d91"

_AGENT = "https://creative.adcontextprotocol.org"


def _validates(engine, document: list[dict]) -> bool:
    """Whether the live function accepts *document*, on a connection of its own."""
    with engine.connect() as connection:
        try:
            connection.execute(
                text("SELECT validate_format_ids(CAST(:payload AS jsonb))"),
                {"payload": json.dumps(document)},
            )
        except Exception:
            return False
    return True


def _pinned_properties() -> set[str]:
    """The properties ``core/format-id.json`` declares, read off the installed SDK."""
    bundle = str(adcp.get_adcp_spec_version()).rsplit(".", 1)[0]
    document = Path(adcp.__file__).parent / "_schemas" / bundle / "core" / "format-id.json"
    assert document.is_file(), f"the pinned bundle carries no {document}"
    return set(json.loads(document.read_text())["properties"])


@pytest.fixture(scope="module")
def migrated(migration_db):
    """The database at this revision, which is where the function is defined."""
    from tests.integration.migration_helpers import run_alembic_upgrade

    engine, db_url = migration_db
    run_alembic_upgrade(db_url, _REVISION)
    return engine, db_url


def test_a_reference_carrying_pixel_ratio_is_accepted(migrated) -> None:
    """The defect: the database refused a property the pin declares."""
    engine, _ = migrated
    assert _validates(
        engine, [{"agent_url": _AGENT, "id": "display_static", "width": 300, "height": 250, "pixel_ratio": 2}]
    )


def test_every_property_the_pin_declares_is_accepted_one_at_a_time(migrated) -> None:
    """Derived from the pin, so a seventh property fails here rather than in production.

    One at a time, because a document carrying all six passes as soon as the allowlist is a
    superset and would not say WHICH member is missing.
    """
    engine, _ = migrated
    pinned = _pinned_properties()
    assert len(pinned) >= 3, f"read only {sorted(pinned)} from the pinned format-id.json"

    #: a value each optional property accepts; the two required ones are always present
    values = {"width": 300, "height": 250, "duration_ms": 15000, "pixel_ratio": 2}
    optional = pinned - {"agent_url", "id"}
    assert optional, "the pin declares no optional properties, which contradicts its own schema"

    refused = [
        name
        for name in sorted(optional)
        if not _validates(engine, [{"agent_url": _AGENT, "id": "display_static", name: values.get(name, 1)}])
    ]
    assert not refused, (
        f"the database REFUSES properties core/format-id.json declares: {refused}. "
        "Add a migration widening validate_format_ids' allowed_keys (salesagent-knd96)."
    )


@pytest.mark.parametrize(
    "document, why",
    [
        ([{"agent_url": _AGENT, "id": "x", "bogus_prop": 1}], "an undeclared property"),
        ([{"agent_url": _AGENT, "id": "x", "pixel_ratio": "large"}], "a non-numeric pixel_ratio"),
        ([{"agent_url": _AGENT, "id": "x", "pixel_ratio": 0}], "a non-positive pixel_ratio"),
        ([{"agent_url": _AGENT, "pixel_ratio": 2}], "a reference with no id"),
        ([{"id": "x", "pixel_ratio": 2}], "a reference with no agent_url"),
    ],
)
def test_the_function_still_refuses_what_it_refused_before(migrated, document, why) -> None:
    """Widening an allowlist to anything removes the check rather than correcting it."""
    engine, _ = migrated
    assert not _validates(engine, document), f"{why} was accepted"


def test_the_previous_revision_refuses_pixel_ratio(migrated) -> None:
    """The red half: downgrade and the defect comes back, so this grades the migration.

    Without this the suite cannot tell "the migration fixed it" from "the property was
    always allowed". Restored to the revision under test afterwards, because the module's
    database is shared.
    """
    from tests.integration.migration_helpers import run_alembic_downgrade, run_alembic_upgrade

    engine, db_url = migrated
    document = [{"agent_url": _AGENT, "id": "display_static", "pixel_ratio": 2}]
    try:
        run_alembic_downgrade(db_url, _PREVIOUS)
        assert not _validates(engine, document), (
            "the previous revision accepts pixel_ratio, so this migration grades nothing"
        )
    finally:
        run_alembic_upgrade(db_url, _REVISION)
    assert _validates(engine, document), "failed to restore the revision under test"

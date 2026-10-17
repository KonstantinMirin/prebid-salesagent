"""What migration b4f1a9c27d53 decides for each ``format_kind IS NULL`` row.

The migration makes ``creatives.format_kind`` ``NOT NULL`` and migrates existing rows BY
PROJECTION rather than by deleting them -- the user's ruling: "Don't delete -- migrate using
the projection. Those that can't be migrated would be migration errors and the seller would
take care of them on the data level."

So the decision per row is the part that can be WRONG: which rows get a kind, WHICH kind each
gets, and which ones abort the whole migration. A wrong answer there silently writes a
fabricated identity onto a buyer's stored creative, and every layer inside this seller keys
on that value. ``plan_projection`` is separated from the DDL for exactly this reason, and
these grade it with no database: the ``ALTER COLUMN`` either runs or does not, and the schema
round-trip is graded against a MIGRATED database (``migration_db``), which is the only place
a migration-created constraint exists -- ``integration_db`` builds its schema with
``Base.metadata.create_all`` and cannot see one.

THE PROJECTION AVAILABLE TO A MIGRATION IS THE REGISTRY ONLY. ``canonical_kind_for`` resolves
the agent's own declaration first, then the registry -- the glob against the id, and, failing
that, against the id the registry's parameterized upgrade normalizes it to. Only the first
step needs a fetched format spec, which a migration cannot obtain because it must not dial the
creative agent. That asymmetry is the subject of half these tests: an id the registry resolves
migrates, and an id that needs the declaration aborts even though the sync path resolves it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

AGENT = "https://creative.adcontextprotocol.org"


def _load_migration() -> Any:
    """Import the revision module by path -- it is not an importable package member."""
    path = (
        Path(__file__).resolve().parents[2] / "alembic" / "versions" / "b4f1a9c27d53_creatives_format_kind_not_null.py"
    )
    spec = importlib.util.spec_from_file_location("migration_b4f1a9c27d53", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plan_projection() -> Any:
    return _load_migration().plan_projection


def _row(creative_id: str, legacy_id: str | None, *, tenant: str = "tenant_a") -> tuple[Any, Any, Any]:
    """One ``SELECT creative_id, tenant_id, legacy_format_id`` row as the driver returns it."""
    return (creative_id, tenant, {"agent_url": AGENT, "id": legacy_id} if legacy_id is not None else None)


class TestRowsThatProject:
    @pytest.mark.parametrize(
        ("legacy_id", "expected_kind"),
        [("display_300x250", "image"), ("video_640x480", "video_hosted")],
    )
    def test_a_glob_resolvable_reference_migrates_to_its_kind(
        self, plan_projection: Any, legacy_id: str, expected_kind: str
    ) -> None:
        """The kind is DERIVED from the stored reference, not defaulted to anything.

        Both ids resolve through ``registries/v1-canonical-mapping.json``'s globs, which is
        the only route a migration has. The expected kind is spelled out rather than compared
        against another call to the same function -- comparing a derivation to itself would
        pass on any derivation, including one that returns a constant.
        """
        projected, unprojectable = plan_projection([_row("cr-1", legacy_id)])

        assert (projected, unprojectable) == ([("cr-1", "tenant_a", expected_kind)], [])

    def test_the_tenant_travels_with_the_row(self, plan_projection: Any) -> None:
        """creatives is keyed (creative_id, tenant_id, principal_id).

        A plan that dropped the tenant would make the UPDATE match one creative_id across
        every tenant that happens to share it, writing one tenant's projected kind onto
        another's creative.
        """
        projected, _ = plan_projection(
            [
                _row("cr-same", "display_300x250", tenant="tenant_a"),
                _row("cr-same", "display_300x250", tenant="tenant_b"),
            ]
        )

        assert [(cid, tid) for cid, tid, _kind in projected] == [("cr-same", "tenant_a"), ("cr-same", "tenant_b")]


class TestRowsThatAbort:
    def test_a_reference_needing_the_agents_declaration_cannot_be_migrated(self, plan_projection: Any) -> None:
        """``video_standard_30s`` is served and resolvable AT SYNC, and not here.

        This is the asymmetry an operator reading the abort needs to understand: the row is
        not corrupt, it just cannot be projected by a process with no catalog. Listing it is
        what lets them re-sync it instead of deleting it.

        The id is one ``database.py`` SEEDS into the demo tenant's ``auto_approve_format_ids``,
        so the abort it demonstrates is one a real operator can actually be handed -- the
        registry carries no ``video_standard_30s`` mapping and the only route left is the
        agent's own ``canonical`` declaration, which needs the catalog.

        It used to be ``display_300x250_image``, on the premise that the sync path resolved it.
        It did not: that id reached the same refusal, in 101 of the 376 nodeids regressed on
        land (salesagent-iz7dm), because the registry covers it through ``display_image``'s
        parameterized upgrade and the projection matched the glob against the raw slug only.
        It now projects to ``image`` HERE as well, which is why it cannot stand for this case.
        """
        projected, unprojectable = plan_projection([_row("cr-needs-spec", "video_standard_30s")])

        assert (projected, unprojectable) == ([], ["cr-needs-spec"])

    def test_a_row_with_no_reference_at_all_aborts_too(self, plan_projection: Any) -> None:
        """No kind and no ``legacy_format_id``: there is nothing to project FROM.

        Collected into the same list rather than ignored. Skipping it would leave the row NULL
        and the ``ALTER COLUMN`` would then fail on it with a database error naming a
        constraint instead of a creative.
        """
        projected, unprojectable = plan_projection([_row("cr-no-ref", None)])

        assert (projected, unprojectable) == ([], ["cr-no-ref"])

    def test_one_unprojectable_row_does_not_discard_the_projectable_ones(self, plan_projection: Any) -> None:
        """Both lists come back whole, which is what makes the abort ALL-OR-NOTHING upstream.

        ``upgrade`` raises before issuing any UPDATE, so a mixed batch changes nothing at all.
        If this returned only the failures, a later reader could not tell whether the
        projectable rows had already been written.
        """
        projected, unprojectable = plan_projection(
            [_row("cr-ok", "display_300x250"), _row("cr-bad", "audio_standard"), _row("cr-ok-2", "video_640x480")]
        )

        assert [cid for cid, _t, _k in projected] == ["cr-ok", "cr-ok-2"]
        assert unprojectable == ["cr-bad"]


def test_no_rows_is_not_an_abort(plan_projection: Any) -> None:
    """The expected case on a database with no legacy creatives: nothing to do, no error."""
    assert plan_projection([]) == ([], [])

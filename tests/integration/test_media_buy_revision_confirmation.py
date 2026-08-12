"""Integration test: the repository maintains revision and confirmed_at.

These two fields are only meaningful as PERSISTED state, so they are graded here
against a real Postgres rather than in a unit test: the revision bump is a SQL-side
``coalesce(revision, 0) + 1`` precisely so the database serializes concurrent
mutations, and a mocked session would assert the Python call, not the behaviour that
matters.

Semantics adopted verbatim from PR #1544 (GH #1928 requires reconciling with it
rather than deciding independently):
  - revision is a monotonic optimistic-concurrency token, bumped on EVERY successful
    mutation, repository-managed and immutable to callers.
  - confirmed_at is the seller-commitment instant, written ONCE and stable across all
    later transitions.
"""

import pytest
from sqlalchemy.orm import Session as SASession

from src.core.database.database_session import get_engine
from src.core.database.repositories.media_buy import MediaBuyRepository

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.fixture
def repo_env(integration_db):
    """A pending_approval media buy plus a repository scoped to its tenant."""
    from tests.factories import ALL_FACTORIES, MediaBuyFactory

    session = SASession(bind=get_engine())
    try:
        for factory in ALL_FACTORIES:
            factory._meta.sqlalchemy_session = session
        media_buy = MediaBuyFactory(status="pending_approval")
        repo = MediaBuyRepository(session, media_buy.tenant_id)
        yield repo, media_buy
    finally:
        session.close()
        for factory in ALL_FACTORIES:
            factory._meta.sqlalchemy_session = None


def _revision(repo: MediaBuyRepository, media_buy_id: str) -> int:
    """Re-read the persisted counter (the attribute holds a SQL expression post-bump)."""
    return repo.get_by_id(media_buy_id).revision


class TestRevisionCounter:
    def test_new_media_buy_starts_at_revision_one(self, repo_env):
        repo, media_buy = repo_env
        assert _revision(repo, media_buy.media_buy_id) == 1

    def test_back_to_back_updates_yield_strictly_increasing_revisions(self, repo_env):
        """Two updates in the same clock tick must still produce 2 then 3.

        This is the scenario that rules out deriving revision from timestamps, and
        the one PR #1544's own integration test pins.
        """
        repo, media_buy = repo_env

        repo.update_fields(media_buy.media_buy_id, budget=20000)
        first = _revision(repo, media_buy.media_buy_id)
        repo.update_fields(media_buy.media_buy_id, budget=30000)
        second = _revision(repo, media_buy.media_buy_id)

        assert (first, second) == (2, 3)

    def test_status_transition_bumps_revision(self, repo_env):
        """Seller-side transitions move the token too, not just buyer updates."""
        repo, media_buy = repo_env

        repo.update_status(media_buy.media_buy_id, "active")

        assert _revision(repo, media_buy.media_buy_id) == 2

    def test_package_level_write_can_bump_via_public_entry_point(self, repo_env):
        """Package writes persist outside update_*, so they need bump_revision."""
        repo, media_buy = repo_env

        repo.bump_revision(media_buy.media_buy_id)

        assert _revision(repo, media_buy.media_buy_id) == 2

    def test_revision_is_immutable_to_callers(self, repo_env):
        """It is repository-managed: a caller writing it would break monotonicity."""
        repo, media_buy = repo_env

        with pytest.raises(ValueError, match="immutable field"):
            repo.update_fields(media_buy.media_buy_id, revision=99)

        assert _revision(repo, media_buy.media_buy_id) == 1


class TestConfirmedAtStamp:
    def test_unconfirmed_status_leaves_confirmed_at_null(self, repo_env):
        """pending_approval is not a seller commitment, so nothing is stamped."""
        repo, media_buy = repo_env

        repo.update_fields(media_buy.media_buy_id, budget=20000)

        assert repo.get_by_id(media_buy.media_buy_id).confirmed_at is None

    def test_reaching_a_committed_status_stamps_confirmed_at(self, repo_env):
        repo, media_buy = repo_env

        repo.update_status(media_buy.media_buy_id, "active")

        assert repo.get_by_id(media_buy.media_buy_id).confirmed_at is not None

    def test_confirmed_at_is_written_once_and_survives_later_transitions(self, repo_env):
        """The commitment instant must not track the most recent transition."""
        repo, media_buy = repo_env

        repo.update_status(media_buy.media_buy_id, "active")
        stamped = repo.get_by_id(media_buy.media_buy_id).confirmed_at

        repo.update_status(media_buy.media_buy_id, "completed")

        assert repo.get_by_id(media_buy.media_buy_id).confirmed_at == stamped

    def test_rejected_never_stamps(self, repo_env):
        """A rejected buy was never committed to, so it has no commitment instant."""
        repo, media_buy = repo_env

        repo.update_status(media_buy.media_buy_id, "rejected")

        assert repo.get_by_id(media_buy.media_buy_id).confirmed_at is None

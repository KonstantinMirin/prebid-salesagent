"""Integration test: the background order-approval job, end to end against the DB.

Replaces a mocked-session unit test (``test_start_approval_creates_sync_job``) that
asserted the SyncJob's fields off ``session.add.call_args`` — a MagicMock, never a
persisted row — and, because it never let the worker body run under control, leaked a
live daemon thread past the end of the test. That thread later reached the real
``get_db_session()``, found no adapter config, and fired ``_send_approval_webhook`` ->
``httpx.Client`` from inside whatever test happened to be running by then, breaking
``test_approval_webhook_rejects_metadata_url_without_post``'s ``assert_not_called()``
under an unlucky pytest-randomly seed (salesagent-egyz).

Here the whole path runs for real: the row is INSERTed by production code, the worker
thread reads the tenant's adapter config through AdapterConfigRepository, and the
failure is marked and committed — then the test joins the thread before returning, so
nothing escapes into a sibling test.
"""

import time
from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from src.core.database.database_session import get_engine
from src.core.database.models import SyncJob
from src.services.order_approval_service import (
    get_approval_status,
    is_approval_running,
    start_order_approval_background,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# The worker's first real step is the adapter-config lookup; with no GAM config it
# marks the job failed immediately, so it settles well inside this budget. Generous
# enough not to flake on a loaded CI box, short enough to fail fast if the thread
# never terminates (the leak this test exists to prevent).
_SETTLE_TIMEOUT_SECONDS = 30.0


@dataclass
class _ApprovalEnv:
    tenant_id: str
    session: SASession


@pytest.fixture
def approval_env(integration_db):
    """A committed tenant carrying no AdapterConfig row, plus the session that wrote it.

    Committed, not just flushed: the approval worker runs on its own connection and
    would not see an open transaction's writes. The session is handed to the test so
    it can read the persisted row back without opening a raw ``get_db_session()``
    (CLAUDE.md Pattern #8 / the repository-pattern guard) — SyncJob has no repository
    of its own to go through.
    """
    from tests.factories import ALL_FACTORIES, TenantFactory

    session = SASession(bind=get_engine())
    try:
        for factory in ALL_FACTORIES:
            factory._meta.sqlalchemy_session = session
        tenant = TenantFactory(tenant_id="approval_tenant")
        yield _ApprovalEnv(tenant_id=tenant.tenant_id, session=session)
    finally:
        session.close()
        for factory in ALL_FACTORIES:
            factory._meta.sqlalchemy_session = None


def _wait_until_settled(approval_id: str) -> dict:
    """Block until the worker leaves 'running', reading through production's own
    status API, and return its final report."""
    deadline = time.monotonic() + _SETTLE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = get_approval_status(approval_id)
        assert status is not None, f"production never persisted a SyncJob for {approval_id}"
        if status["status"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError(f"approval {approval_id} still 'running' after {_SETTLE_TIMEOUT_SECONDS}s")


def test_start_approval_persists_job_then_worker_marks_it_failed_without_gam_config(approval_env):
    """The job is persisted with its tracking payload, and the worker terminates it.

    One test covers both halves deliberately: the row's creation is only meaningful if
    the worker that owns it can be observed reaching a terminal state, and the join at
    the end is what keeps the thread from outliving the test.
    """
    approval_id = start_order_approval_background(
        order_id="12345",
        media_buy_id="mb_123",
        tenant_id=approval_env.tenant_id,
        principal_id="principal_1",
        # No webhook_url: this test grades persistence and thread lifecycle, and a URL
        # here would make the worker attempt a real outbound POST.
        webhook_url=None,
    )

    assert approval_id.startswith("approval_12345_")

    status = _wait_until_settled(approval_id)

    # Terminal state, reached through the real AdapterConfigRepository lookup.
    assert status["status"] == "failed"
    assert status["error_message"] == "GAM not configured for tenant"
    assert status["completed_at"] is not None

    # Tracking payload production wrote at INSERT time; the worker never rewrites it.
    assert status["progress"]["order_id"] == "12345"
    assert status["progress"]["media_buy_id"] == "mb_123"
    assert status["progress"]["webhook_url"] is None

    # Columns the status API does not expose, read off the persisted row. rollback()
    # first: this session opened its snapshot before the worker committed.
    approval_env.session.rollback()
    job = approval_env.session.scalars(select(SyncJob).where(SyncJob.sync_id == approval_id)).one()
    assert job.tenant_id == approval_env.tenant_id
    assert job.sync_type == "order_approval"
    assert job.adapter_type == "google_ad_manager"
    assert job.triggered_by == "order_creation"
    assert job.triggered_by_id == "mb_123"

    assert not is_approval_running(approval_id), "worker thread outlived the test — it must not leak"

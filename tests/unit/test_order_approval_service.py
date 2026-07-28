"""Unit tests for order approval service."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.order_approval_service import (
    get_active_approvals,
    get_approval_status,
    is_approval_running,
    start_order_approval_background,
)


@pytest.fixture(autouse=True)
def cleanup_approval_registry():
    """Clean up global approval registry before each test."""
    # Import here to avoid issues with module loading
    import src.services.order_approval_service as service

    # Clear the registry before the test (ThreadRegistry API)
    for key in list(service._active_approvals.list_active()):
        service._active_approvals.remove(key)

    yield

    # Note: Don't clear after test - threads may still be running and need to clean up themselves


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch("src.services.order_approval_service.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = None  # No existing approval
        mock_db.scalars.return_value.all.return_value = []
        yield mock_db


@pytest.fixture
def mock_gam_client():
    """Mock GAM client and managers."""
    with (
        patch("src.services.order_approval_service.GAMClientManager") as mock_client_mgr,
        patch("src.services.order_approval_service.GAMOrdersManager") as mock_orders_mgr,
        patch("src.services.order_approval_service.AdapterConfig") as mock_config,
    ):
        # Mock adapter config
        mock_adapter_config = MagicMock()
        mock_adapter_config.gam_network_code = "12345"

        # Mock orders manager
        mock_orders_instance = MagicMock()
        mock_orders_instance.approve_order.return_value = True
        mock_orders_mgr.return_value = mock_orders_instance

        yield {
            "client_manager": mock_client_mgr,
            "orders_manager": mock_orders_mgr,
            "orders_instance": mock_orders_instance,
            "adapter_config": mock_adapter_config,
        }


def test_start_approval_creates_sync_job(mock_db_session):
    """Test that starting approval creates a SyncJob record."""
    from src.core.database.models import SyncJob

    approval_id = start_order_approval_background(
        order_id="12345",
        media_buy_id="mb_123",
        tenant_id="tenant_1",
        principal_id="principal_1",
        webhook_url="https://example.com/webhook",
    )

    # Verify sync job was created
    assert approval_id.startswith("approval_12345_")
    mock_db_session.add.assert_called_once()

    # Check the sync job was created with correct fields
    sync_job_call = mock_db_session.add.call_args[0][0]
    assert isinstance(sync_job_call, SyncJob)
    assert sync_job_call.sync_type == "order_approval"
    assert sync_job_call.status == "running"
    assert sync_job_call.tenant_id == "tenant_1"
    assert sync_job_call.progress["order_id"] == "12345"
    assert sync_job_call.progress["media_buy_id"] == "mb_123"
    assert sync_job_call.progress["webhook_url"] == "https://example.com/webhook"


def test_start_approval_rejects_duplicate(mock_db_session):
    """Test that starting approval for same order fails."""
    from src.core.database.models import SyncJob

    # Mock existing approval for this order
    existing_approval = SyncJob(
        sync_id="approval_12345_existing",
        tenant_id="tenant_1",
        adapter_type="google_ad_manager",
        sync_type="order_approval",
        status="running",
        started_at=datetime.now(UTC),
        triggered_by="order_creation",
        triggered_by_id="mb_123",
        progress={"order_id": "12345"},
    )
    mock_db_session.scalars.return_value.all.return_value = [existing_approval]

    with pytest.raises(ValueError, match="Approval already running for order 12345"):
        start_order_approval_background(
            order_id="12345",
            media_buy_id="mb_123",
            tenant_id="tenant_1",
            principal_id="principal_1",
        )


def test_approval_thread_tracks_in_registry(mock_db_session):
    """Test that approval thread is tracked in global registry.

    Uses a blocking mock so the worker stays alive while the test
    inspects the registry — the dead-thread reaper added in the
    production memory-leak fix drops dead-thread entries on read, so
    a no-op mock that exits immediately would race the reaper.
    """
    import threading

    keep_alive = threading.Event()
    with patch(
        "src.services.order_approval_service._run_approval_thread",
        side_effect=lambda *args, **kwargs: keep_alive.wait(timeout=2.0),
    ):
        approval_id = start_order_approval_background(
            order_id="12345",
            media_buy_id="mb_123",
            tenant_id="tenant_1",
            principal_id="principal_1",
        )
        try:
            active_approvals = get_active_approvals()
            assert approval_id in active_approvals, f"Expected {approval_id} in {active_approvals}"
            assert is_approval_running(approval_id)
        finally:
            keep_alive.set()


def test_get_approval_status(mock_db_session):
    """Test getting approval status."""
    from src.core.database.models import SyncJob

    # Mock existing approval
    approval = SyncJob(
        sync_id="approval_12345_test",
        tenant_id="tenant_1",
        adapter_type="google_ad_manager",
        sync_type="order_approval",
        status="running",
        started_at=datetime.now(UTC),
        triggered_by="order_creation",
        triggered_by_id="mb_123",
        progress={"order_id": "12345", "attempts": 3},
    )
    mock_db_session.scalars.return_value.first.return_value = approval

    status = get_approval_status("approval_12345_test")

    assert status is not None
    assert status["approval_id"] == "approval_12345_test"
    assert status["status"] == "running"
    assert status["progress"]["order_id"] == "12345"
    assert status["progress"]["attempts"] == 3


def test_get_approval_status_not_found(mock_db_session):
    """Test getting approval status for non-existent approval."""
    mock_db_session.scalars.return_value.first.return_value = None

    status = get_approval_status("nonexistent")
    assert status is None

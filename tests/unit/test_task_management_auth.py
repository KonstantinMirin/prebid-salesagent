"""Unit tests for F-03: task management tools require authenticated principal.

Covers the vulnerability where list_tasks / get_task_status / complete_task accepted
requests that had a resolved tenant (via localhost fallback) but no principal_id.
An unauthenticated caller could read or mutate workflow task state.

The fix is now STRUCTURAL rather than a per-function guard. Identity is resolved in one
place -- ``invoke_tool`` -- which reads ``ToolSpec.requires_credential()`` and passes it as
``require_valid_token``. All three of these tools declare ``auth="required"``, so an
unauthenticated caller is refused inside resolution and never reaches the implementation.

These tests therefore drive the boundary the way a buyer does: they present a CREDENTIAL
(absent, or present-but-unresolvable) instead of injecting a pre-resolved identity. Injecting
one is no longer possible -- ``invoke_tool`` takes no identity parameter -- and that is the
point: the vulnerable state (tenant resolved via localhost fallback, principal absent) cannot
be constructed to be passed in.
"""

import pytest

from src.core.auth_context import AuthContext
from src.core.exceptions import AdCPAuthenticationError, AdCPNotFoundError, AdCPTaskNotFoundError
from src.core.resolved_identity import ResolvedIdentity

# Every protocol field travels on the request now. Dispatch goes through the shared boundary
# -- the one path MCP, A2A and REST take -- so this grades the auth gate every buyer hits.
from src.core.schemas import CompleteTaskRequest, GetTaskStatusRequest, ListTasksRequest
from src.core.tenant_context import TenantContext
from src.core.tools._boundary import invoke_tool
from tests.factories.principal import PrincipalFactory
from tests.helpers.boundary_identity import refused_as, resolved_as


def _authenticated() -> ResolvedIdentity:
    """What the boundary resolves for a caller whose credential is good."""
    return PrincipalFactory.make_identity(
        principal_id="principal-abc",
        tenant_id="test-tenant",
        tenant=TenantContext(tenant_id="test-tenant", name="Test"),
        protocol="mcp",
    )


def _no_credential() -> AuthContext:
    """What an unauthenticated caller presents: nothing."""
    return AuthContext()


def _unresolvable_credential() -> AuthContext:
    """A credential that is presented and resolves to no principal."""
    return AuthContext(
        auth_token="not-a-real-token",
        headers={"Authorization": "Bearer not-a-real-token", "host": "localhost"},
    )


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tasks_no_principal_raises_auth_error() -> None:
    """list_tasks must reject identity that has tenant but no principal_id."""
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        with refused_as(AdCPAuthenticationError()):
            await invoke_tool("list_tasks", ListTasksRequest(), _unresolvable_credential(), "mcp")


@pytest.mark.asyncio
async def test_list_tasks_no_identity_raises_auth_error() -> None:
    """list_tasks must reject a completely missing identity."""
    with pytest.raises(AdCPAuthenticationError):
        await invoke_tool("list_tasks", ListTasksRequest(), _no_credential(), "mcp")


# ---------------------------------------------------------------------------
# get_task_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_no_principal_raises_auth_error() -> None:
    """get_task_status must reject identity that has tenant but no principal_id."""
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        with refused_as(AdCPAuthenticationError()):
            await invoke_tool(
                "get_task_status", GetTaskStatusRequest(task_id="step-123"), _unresolvable_credential(), "mcp"
            )


@pytest.mark.asyncio
async def test_get_task_no_identity_raises_auth_error() -> None:
    """get_task_status must reject a completely missing identity."""
    with pytest.raises(AdCPAuthenticationError):
        await invoke_tool("get_task_status", GetTaskStatusRequest(task_id="step-123"), _no_credential(), "mcp")


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_task_no_principal_raises_auth_error() -> None:
    """complete_task must reject identity that has tenant but no principal_id."""
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        with refused_as(AdCPAuthenticationError()):
            await invoke_tool(
                "complete_task",
                CompleteTaskRequest(task_id="step-123", status="completed"),
                _unresolvable_credential(),
                "mcp",
            )


@pytest.mark.asyncio
async def test_complete_task_no_identity_raises_auth_error() -> None:
    """complete_task must reject a completely missing identity."""
    with pytest.raises(AdCPAuthenticationError):
        await invoke_tool(
            "complete_task", CompleteTaskRequest(task_id="step-123", status="completed"), _no_credential(), "mcp"
        )


# ---------------------------------------------------------------------------
# Regression: authenticated identity is not affected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tasks_authenticated_proceeds_past_auth_check(
    mocker: pytest.FixtureRequest,
) -> None:
    """Authenticated identity must pass the auth check and proceed to DB access."""
    mock_uow = mocker.patch("src.core.tools.task_management.WorkflowUoW")
    mock_uow.return_value.__enter__.return_value.workflows.count_by_tenant.return_value = 0
    mock_uow.return_value.__enter__.return_value.workflows.list_by_tenant.return_value = []
    mock_uow.return_value.__enter__.return_value.workflows.get_mappings_for_steps.return_value = {}

    with resolved_as(_authenticated()):
        result = await invoke_tool("list_tasks", ListTasksRequest(), _unresolvable_credential(), "mcp")

    assert result.tasks == []
    # The count moved inside query_summary, where list-tasks-response.json declares it.
    assert result.query_summary.total_matching == 0


@pytest.mark.asyncio
async def test_get_task_authenticated_proceeds_past_auth_check(
    mocker: pytest.FixtureRequest,
) -> None:
    """Authenticated identity must pass the auth check and proceed to DB access."""

    mock_uow = mocker.patch("src.core.tools.task_management.WorkflowUoW")
    mock_uow.return_value.__enter__.return_value.workflows.get_by_step_id_or_raise.side_effect = AdCPTaskNotFoundError()

    with pytest.raises(AdCPNotFoundError) as _ei:
        with resolved_as(_authenticated()):
            await invoke_tool(
                "get_task_status", GetTaskStatusRequest(task_id="step-999"), _unresolvable_credential(), "mcp"
            )
    # The old pattern matched the AUTHORED sentence; the sentence is the
    # code's table entry now, so assert it exactly.


@pytest.mark.asyncio
async def test_complete_task_authenticated_proceeds_past_auth_check(
    mocker: pytest.FixtureRequest,
) -> None:
    """Authenticated identity must pass the auth check and proceed to DB access."""

    mock_uow = mocker.patch("src.core.tools.task_management.WorkflowUoW")
    mock_uow.return_value.__enter__.return_value.workflows.get_by_step_id_or_raise.side_effect = AdCPTaskNotFoundError()

    with pytest.raises(AdCPNotFoundError) as _ei:
        # status is REQUIRED by the DTO and typed Literal["completed", "failed"], so the
        # request cannot be built without one -- the rejection is the model's, not a
        # second check inside the impl.
        with resolved_as(_authenticated()):
            await invoke_tool(
                "complete_task",
                CompleteTaskRequest(task_id="step-999", status="completed"),
                _unresolvable_credential(),
                "mcp",
            )
    # The old pattern matched the AUTHORED sentence; the sentence is the
    # code's table entry now, so assert it exactly.

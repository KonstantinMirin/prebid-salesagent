"""Task management MCP tools (list_tasks, get_task, complete_task).

Human-in-the-loop task queue for workflow steps that require approval
or manual completion. These tools let AI agents query and complete
pending workflow tasks.

This module follows the MCP/A2A shared implementation pattern from CLAUDE.md.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from adcp.types import ContextObject
from adcp.types.generated_poc.protocol.list_tasks_request import ListTasksRequest as LibraryListTasksRequest
from fastmcp.server.context import Context

from src.core.audit_logger import get_audit_logger
from src.core.auth import require_identity, require_principal_id, require_tenant
from src.core.database.repositories.uow import WorkflowUoW
from src.core.exceptions import (
    AdCPConflictError,
    AdCPValidationError,
)
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas.task_management import (
    ListTasksQuerySummary,
    ListTasksResponse,
    ResponsePagination,
    WorkflowTask,
    WorkflowTaskObject,
    WorkflowTaskSummary,
)
from src.core.spec_request_carrier import refuse_unsupported_fields

logger = logging.getLogger(__name__)


def _isoformat(value: Any) -> str | None:
    """ISO 8601 for a timestamp column, tolerant of a driver handing back a string.

    One helper for every timestamp this module reports — the same three-branch
    expression was written out at each of the four sites it is used.
    """
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


# Body-semantic fields `list_tasks` ACCEPTS on the wire (its pinned 3.1.1 request
# schema defines them) and this seller cannot act on. It filters with the flat
# status / object_type / object_id / limit / offset parameters it declares; the
# spec's structured filters, sort and cursor pagination are a different query
# surface. Refused rather than dropped: a buyer that sorted by age and got
# creation order, or asked for page 2 and got page 1, cannot tell.
_UNSUPPORTED_LIST_TASKS_FIELDS = {
    "account": "filtering by account reference is not implemented; results are scoped to the authenticated agent",
    "filters": "the structured filters object is not implemented; use status / object_type / object_id",
    "include_history": "task change history is not implemented",
    "pagination": "cursor pagination is not implemented; use limit / offset",
    "sort": "sorting is not implemented; tasks are returned newest first",
}


async def list_tasks(
    status: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    context: ContextObject | None = None,
    ctx: Context | None = None,
    identity: ResolvedIdentity | None = None,
    # Seam carrier: the wire request as this tool's pinned model. Present on
    # EVERY seam member under the same name — uniform or it is not a seam —
    # and filtered out of the published schema by the decorator.
    _spec_request: LibraryListTasksRequest | None = None,
) -> ListTasksResponse:
    """List workflow tasks with filtering options.

    Args:
        status: Filter by task status ("pending", "in_progress", "completed", "failed", "requires_approval")
        object_type: Filter by object type ("media_buy", "creative", "product")
        object_id: Filter by specific object ID
        limit: Maximum number of tasks to return (default: 20)
        offset: Number of tasks to skip (default: 0)
        context: Application-level context object (optional). Per AdCP 3.1.1's
            normative echo contract (docs/building/by-layer/L2/context-sessions.mdx),
            this is opaque -- never parsed or acted on -- but MUST be echoed
            byte-for-byte in the response when the caller supplies it.
        ctx: MCP context (automatically provided)
        identity: Pre-resolved identity (preferred over ctx)

    Returns:
        ListTasksResponse — the pinned response model, which owns serialization
        (query_summary, pagination and the context echo included).
    """
    if identity is None and ctx is not None:
        identity = await ctx.get_state("identity")

    identity = require_identity(identity, context=context)
    tenant = require_tenant(identity, context=context)
    require_principal_id(identity, context=context)  # F-03: an authenticated (non-anonymous) principal is required

    # `list_tasks` has no internal request model of its own — the seam's carrier IS
    # its request — so the disposition is taken on `_spec_request` directly.
    if _spec_request is not None:
        refuse_unsupported_fields(_spec_request, tool="list_tasks", unsupported=_UNSUPPORTED_LIST_TASKS_FIELDS)

    with WorkflowUoW(tenant["tenant_id"]) as uow:
        assert uow.workflows is not None

        total = uow.workflows.count_by_tenant(
            status=status,
            object_type=object_type,
            object_id=object_id,
        )

        tasks = uow.workflows.list_by_tenant(
            status=status,
            object_type=object_type,
            object_id=object_id,
            offset=offset,
            limit=limit,
        )

        step_ids = [task.step_id for task in tasks]
        all_mappings = uow.workflows.get_mappings_for_steps(step_ids)

        formatted_tasks = []
        for task in tasks:
            mappings = all_mappings.get(task.step_id, [])

            summary = None
            if isinstance(task.request_data, dict):
                nested_request = task.request_data.get("request") or {}
                summary = WorkflowTaskSummary(
                    operation=task.request_data.get("operation"),
                    media_buy_id=task.request_data.get("media_buy_id"),
                    po_number=nested_request.get("po_number") if isinstance(nested_request, dict) else None,
                )

            formatted_tasks.append(
                WorkflowTask(
                    task_id=task.step_id,
                    status=task.status,
                    type=task.step_type,
                    tool_name=task.tool_name,
                    owner=task.owner,
                    created_at=_isoformat(task.created_at),
                    updated_at=None,
                    context_id=task.context_id,
                    associated_objects=[
                        WorkflowTaskObject(type=m.object_type, id=m.object_id, action=m.action) for m in mappings
                    ],
                    summary=summary,
                    # Failure detail belongs to failed steps only — on any other
                    # status it is stale text from an earlier attempt.
                    error_message=task.error_message if task.status == "failed" else None,
                )
            )

        has_more = offset + limit < total if total is not None else False
        # The declared response model owns serialization from here: `query_summary`
        # and `pagination` are REQUIRED by the pinned schema (AdCP 3.1.1
        # protocol/list-tasks-response.json, required: query_summary, tasks,
        # pagination) and inherited, so they can no longer be forgotten the way
        # they were while this returned a hand-assembled dict. `query_summary`
        # is graded by compliance/3.1.1 pagination-integrity.yaml: `total_matching`
        # is the unpaged total and `returned` is THIS page's slice size.
        #
        # `context` is assigned as the MODEL, never `context.model_dump()`: the
        # echo is the model's serialization job, and hand-dumping it in the tool
        # body is what made the echo a per-tool detail instead of a contract.
        return ListTasksResponse(
            tasks=formatted_tasks,
            query_summary=ListTasksQuerySummary(total_matching=total, returned=len(formatted_tasks)),
            pagination=ResponsePagination(has_more=has_more, total_count=total),
            total=total,
            offset=offset,
            limit=limit,
            has_more=has_more,
            context=context,
        )


async def get_task(
    task_id: str, ctx: Context | None = None, identity: ResolvedIdentity | None = None
) -> dict[str, Any]:
    """Get detailed information about a specific task.

    Args:
        task_id: The unique task/workflow step ID
        ctx: MCP context (automatically provided)
        identity: Pre-resolved identity (preferred over ctx)

    Returns:
        Dict containing complete task details
    """
    if identity is None and ctx is not None:
        identity = await ctx.get_state("identity")

    identity = require_identity(identity)
    tenant = require_tenant(identity)
    require_principal_id(identity)  # F-03: an authenticated (non-anonymous) principal is required

    with WorkflowUoW(tenant["tenant_id"]) as uow:
        assert uow.workflows is not None

        task = uow.workflows.get_by_step_id_or_raise(task_id)

        mappings = uow.workflows.get_mappings_for_step(task_id)

        task_detail = {
            "task_id": task.step_id,
            "context_id": task.context_id,
            "status": task.status,
            "type": task.step_type,
            "tool_name": task.tool_name,
            "owner": task.owner,
            "created_at": _isoformat(task.created_at),
            "updated_at": None,
            "request_data": task.request_data,
            "response_data": task.response_data,
            "error_message": task.error_message,
            "associated_objects": [
                {
                    "type": m.object_type,
                    "id": m.object_id,
                    "action": m.action,
                    "created_at": _isoformat(m.created_at),
                }
                for m in mappings
            ],
        }

        return task_detail


async def complete_task(
    task_id: str,
    status: str = "completed",
    response_data: dict[str, Any] | None = None,
    error_message: str | None = None,
    ctx: Context | None = None,
    identity: ResolvedIdentity | None = None,
) -> dict[str, Any]:
    """Complete a pending task (simulates human approval or async completion).

    Args:
        task_id: The unique task/workflow step ID
        status: New status ("completed" or "failed")
        response_data: Optional response data for completed tasks
        error_message: Error message if status is "failed"
        ctx: MCP context (automatically provided)
        identity: Pre-resolved identity (preferred over ctx)

    Returns:
        Dict containing task completion status
    """
    if identity is None and ctx is not None:
        identity = await ctx.get_state("identity")

    identity = require_identity(identity)
    tenant = require_tenant(identity)
    principal_id = require_principal_id(identity)  # F-03: an authenticated principal is required

    if status not in ["completed", "failed"]:
        raise AdCPValidationError(
            f"Invalid status '{status}'. Must be 'completed' or 'failed'",
            field="status",
        )

    with WorkflowUoW(tenant["tenant_id"]) as uow:
        assert uow.workflows is not None

        task = uow.workflows.get_by_step_id_or_raise(task_id)

        if task.status not in ["pending", "in_progress", "requires_approval"]:
            raise AdCPConflictError(f"Task {task_id} is already {task.status} and cannot be completed")

        completed_time = datetime.now(UTC)

        if status == "completed":
            uow.workflows.update_status(
                task_id,
                status=status,
                completed_at=completed_time,
                response_data=response_data or {"manually_completed": True, "completed_by": principal_id},
            )
        else:
            uow.workflows.update_status(
                task_id,
                status=status,
                completed_at=completed_time,
                error_message=error_message or "Task marked as failed manually",
                response_data=response_data,
            )

        audit_logger = get_audit_logger("task_management", tenant["tenant_id"])
        audit_logger.log_operation(
            operation="complete_task",
            principal_name="Manual Completion",
            principal_id=principal_id or "unknown",
            adapter_id="system",
            success=True,
            details={
                "task_id": task_id,
                "new_status": status,
                "original_status": "pending",
                "task_type": task.step_type,
            },
        )

        return {
            "task_id": task_id,
            "status": status,
            "message": f"Task {task_id} marked as {status}",
            "completed_at": completed_time.isoformat(),
            "completed_by": principal_id,
        }

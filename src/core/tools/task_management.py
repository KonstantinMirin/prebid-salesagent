"""Task management MCP tools (list_tasks, get_task, complete_task).

Human-in-the-loop task queue for workflow steps that require approval
or manual completion. These tools let AI agents query and complete
pending workflow tasks.

This module follows the MCP/A2A shared implementation pattern from CLAUDE.md.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ExtensionObject, PaginationRequest
from adcp.types import ListTasksRequest as LibraryListTasksRequest
from adcp.types.generated_poc.protocol.list_tasks_request import Filters as ListTasksFilters
from adcp.types.generated_poc.protocol.list_tasks_request import Sort as ListTasksSort
from fastmcp.server.context import Context

from src.core.audit_logger import get_audit_logger
from src.core.auth import require_identity, require_principal_id, require_tenant
from src.core.database.repositories.uow import WorkflowUoW
from src.core.errors.details import ConflictDetails, ValidationDetails
from src.core.exceptions import (
    AdCPConflictError,
    AdCPValidationError,
)
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas import CompleteTaskRequestLocal, ContextObject, GetTaskRequest, enum_value

logger = logging.getLogger(__name__)


#: Spec TaskStatus -> the workflow-step status this repo actually stores.
#:
#: The two vocabularies are genuinely different, which is the substance of the rebase and
#: not a naming detail: list-tasks-request.json filters on TaskStatus
#: (submitted/working/input-required/completed/canceled/failed/rejected/auth-required)
#: while WorkflowStep.status is pending/in_progress/requires_approval/completed/failed.
#: A buyer now sends the SPEC value and this is where it becomes ours.
#:
#: canceled, rejected and auth-required have no workflow-step equivalent today. They map to
#: None, which the filter treats as "no such task", rather than being silently dropped --
#: dropping the filter would return EVERY task for a status the buyer meant to narrow by.
_SPEC_STATUS_TO_WORKFLOW_STATUS: dict[str, str | None] = {
    "submitted": "pending",
    "working": "in_progress",
    "input-required": "requires_approval",
    "completed": "completed",
    "failed": "failed",
    "canceled": None,
    "rejected": None,
    "auth-required": None,
}


def _build_list_tasks_request(
    filters: ListTasksFilters | None = None,
    sort: ListTasksSort | None = None,
    pagination: PaginationRequest | None = None,
    include_history: bool | None = None,
    account: LibraryAccountReference | None = None,
    context: ContextObject | None = None,
) -> LibraryListTasksRequest:
    """Build a ListTasksRequest from individual wire params.

    The one seam every transport constructs this request through, matching the other
    tools. Its existence is what lets ``_register_tool(list_tasks)`` resolve the DTO
    from the builder instead of being handed one via the ``dto=`` escape hatch.
    """
    fields = {
        "filters": filters,
        "sort": sort,
        "pagination": pagination,
        "include_history": include_history,
        "account": account,
        "context": context,
    }
    # A None argument means the buyer did not send that field, so it is omitted and the
    # model's own default applies rather than being overwritten with an explicit None.
    return LibraryListTasksRequest(**{k: v for k, v in fields.items() if v is not None})


async def list_tasks(
    filters: ListTasksFilters | None = None,
    sort: ListTasksSort | None = None,
    pagination: PaginationRequest | None = None,
    include_history: bool | None = None,
    account: LibraryAccountReference | None = None,
    context: ContextObject | None = None,
    ctx: Context | None = None,
    identity: ResolvedIdentity | None = None,
) -> dict[str, Any]:
    """List workflow tasks (AdCP 3.1.1 list-tasks-request.json).

    REBASED onto the SDK vocabulary. This tool used to take object_id, object_type,
    status, limit and offset -- a pre-3.1.1 flat shape whose intersection with
    ListTasksRequest was ``{context}`` alone, so it could only register through
    ``_register_tool``'s ``dto=`` escape hatch, and it was the last tool doing so.

    ``object_type`` and ``object_id`` are GONE from the wire surface: they are our
    internal workflow-object concepts and list-tasks-request.json declares no equivalent
    (its Filters carry protocol, status, task_type, dates, task_ids, context_contains,
    has_webhook). The repository still supports them for internal callers; they are simply
    not something a buyer can ask for any more, per the rule that pre-3.x payloads do not
    belong at tool-definition level.

    Args:
        filters: Task filters per the spec (status/statuses, task_type, dates, ...)
        sort: Sort field and direction
        pagination: Cursor pagination (max_results, cursor)
        include_history: Include task history
        account: Account reference
        context: Application-level context per AdCP spec
        ctx: MCP context (automatically provided)
        identity: Pre-resolved identity (preferred over ctx)

    Returns:
        Dict containing tasks list and pagination info
    """
    if identity is None and ctx is not None:
        identity = await ctx.get_state("identity")

    req = _build_list_tasks_request(
        filters=filters,
        sort=sort,
        pagination=pagination,
        include_history=include_history,
        account=account,
        context=context,
    )

    # Map the spec shape onto the repository's own vocabulary. `statuses` is the plural
    # arm; a single `status` is the singular one, and the repository takes one string.
    status: str | None = None
    filtered_by_status = False
    if req.filters is not None:
        spec_status = req.filters.status
        if spec_status is None and req.filters.statuses:
            spec_status = req.filters.statuses[0]
        if spec_status is not None:
            filtered_by_status = True
            status = _SPEC_STATUS_TO_WORKFLOW_STATUS.get(enum_value(spec_status))
    if filtered_by_status and status is None:
        # A spec status this seller has no workflow equivalent for. Answering with an
        # unfiltered listing would be worse than answering with none: the buyer asked to
        # narrow and would get everything.
        return {"tasks": [], "total": 0, "limit": 0, "offset": 0}
    object_type = None
    object_id = None
    limit = req.pagination.max_results if req.pagination and req.pagination.max_results else 20
    offset = 0

    # context is forwarded so a refusal ECHOES the buyer's context object, as it does on
    # every other tool -- available here now that this tool builds a request.
    identity = require_identity(identity, context=req.context)
    tenant = require_tenant(identity, context=req.context)
    principal_id = require_principal_id(identity, context=req.context)  # F-03: authenticated principal required

    with WorkflowUoW(tenant["tenant_id"]) as uow:
        assert uow.workflows is not None

        # SCOPED TO THE CALLER'S PRINCIPAL. This listed the whole TENANT, so every buyer
        # saw every other buyer's tasks -- a wider version of the same defect get_task had
        # (salesagent-prkv.88). The pin grades it: get_products_async.yaml step
        # `list_products_task_wrong_account` lists the same task_id under a different
        # account and requires total_matching 0, "Sellers MUST scope task reconciliation to
        # the authenticated account + principal pair".
        #
        # Count and page are narrowed TOGETHER on purpose -- a tenant-wide count beside a
        # principal-scoped page discloses how many tasks the others hold.
        total = uow.workflows.count_by_tenant(
            status=status,
            object_type=object_type,
            object_id=object_id,
            principal_id=principal_id,
        )

        tasks = uow.workflows.list_by_tenant(
            status=status,
            object_type=object_type,
            object_id=object_id,
            offset=offset,
            limit=limit,
            principal_id=principal_id,
        )

        step_ids = [task.step_id for task in tasks]
        all_mappings = uow.workflows.get_mappings_for_steps(step_ids)

        formatted_tasks = []
        for task in tasks:
            mappings = all_mappings.get(task.step_id, [])

            formatted_task = {
                "task_id": task.step_id,
                "status": task.status,
                "type": task.step_type,
                "tool_name": task.tool_name,
                "owner": task.owner,
                "created_at": (
                    task.created_at.isoformat() if hasattr(task.created_at, "isoformat") else str(task.created_at)
                ),
                "updated_at": None,
                "context_id": task.context_id,
                "associated_objects": [
                    {"type": m.object_type, "id": m.object_id, "action": m.action} for m in mappings
                ],
            }

            if task.status == "failed" and task.error_message:
                formatted_task["error_message"] = task.error_message

            if task.request_data:
                if isinstance(task.request_data, dict):
                    formatted_task["summary"] = {  # type: ignore[assignment]
                        "operation": task.request_data.get("operation"),
                        "media_buy_id": task.request_data.get("media_buy_id"),
                        "po_number": (
                            task.request_data.get("request", {}).get("po_number")
                            if task.request_data.get("request")
                            else None
                        ),
                    }

            formatted_tasks.append(formatted_task)

        return {
            "tasks": formatted_tasks,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total if total is not None else False,
        }


def build_get_task_request(
    task_id: str,
    context: Any = None,
    account: LibraryAccountReference | None = None,
    include_history: bool = False,
    include_result: bool = False,
    ext: ExtensionObject | None = None,
) -> GetTaskRequest:
    """Build the request get_task accepts.

    The DTO is local because the pinned SDK ships no GetTaskRequest, but the TOOL is not
    local: protocol/get-task-status-request.json defines it, and GetTaskRequest declares
    that ref. This docstring used to say get_task "appears in neither the pinned 3.1 schema
    tree nor ADCP_TOOL_DEFINITIONS" -- half right, and the wrong half is why four of its
    six spec fields went missing (salesagent-prkv.85). The spec names the task
    get-task-status while the tool is get_task, which is the only reason the schema path
    cannot be derived from the SDK module name the way the other twelve are.

    What the builder buys is that the tool follows the same wrapper -> builder -> DTO ->
    impl template as every other tool, which is what lets _register_tool resolve its model
    without the explicit `dto=` escape hatch (salesagent-prkv.29).
    """
    return GetTaskRequest(
        task_id=task_id,
        context=context,
        account=account,
        include_history=include_history,
        include_result=include_result,
        ext=ext,
    )


def build_complete_task_request(
    task_id: str,
    status: str | None = None,
    response_data: Any = None,
    error_message: str | None = None,
    context: Any = None,
) -> CompleteTaskRequestLocal:
    """Build the request complete_task accepts. Local tool; see build_get_task_request."""
    return CompleteTaskRequestLocal(
        task_id=task_id,
        status=status,
        response_data=response_data,
        error_message=error_message,
        context=context,
    )


async def get_task(
    task_id: str,
    context: Context | None = None,
    identity: ResolvedIdentity | None = None,
    account: LibraryAccountReference | None = None,
    include_history: bool = False,
    include_result: bool = False,
    ext: ExtensionObject | None = None,
) -> dict[str, Any]:
    """Get detailed information about a specific task.

    Args:
        task_id: The unique task/workflow step ID
        context: MCP context (automatically provided)
        identity: Pre-resolved identity (preferred over context)
        account: Account scope for the lookup (see the request DTO)
        include_history: Return this task's request/response exchanges
        include_result: Return the terminal payload when the task is completed
        ext: Extension slot (core/ext.json)

    Returns:
        Dict containing complete task details
    """
    if identity is None and context is not None:
        identity = await context.get_state("identity")

    req = build_get_task_request(
        task_id=task_id,
        context=context if not isinstance(context, Context) else None,
        account=account,
        include_history=include_history,
        include_result=include_result,
        ext=ext,
    )

    identity = require_identity(identity)
    tenant = require_tenant(identity)
    principal_id = require_principal_id(identity)  # F-03: an authenticated (non-anonymous) principal is required

    with WorkflowUoW(tenant["tenant_id"]) as uow:
        assert uow.workflows is not None

        # SCOPED TO THE CALLER'S PRINCIPAL, which is what req.account's obligation amounts
        # to here: "Sellers MUST return REFERENCE_NOT_FOUND for a task_id that exists only
        # under a different account or principal" (get-task-status-request.json @ 3.1.1).
        # The lookup was tenant-scoped only, so any authenticated principal could read
        # another's task by id -- request_data and response_data included. The raised error
        # is identical to the absent case, so it does not reveal that the task exists.
        task = uow.workflows.get_by_step_id_or_raise(req.task_id, principal_id=principal_id)

        mappings = uow.workflows.get_mappings_for_step(task_id)

        task_detail = {
            "task_id": task.step_id,
            "context_id": task.context_id,
            "status": task.status,
            "type": task.step_type,
            "tool_name": task.tool_name,
            "owner": task.owner,
            "created_at": (
                task.created_at.isoformat() if hasattr(task.created_at, "isoformat") else str(task.created_at)
            ),
            "updated_at": None,
            "request_data": task.request_data,
            "error_message": task.error_message,
            "associated_objects": [
                {
                    "type": m.object_type,
                    "id": m.object_id,
                    "action": m.action,
                    "created_at": (
                        m.created_at.isoformat() if hasattr(m.created_at, "isoformat") else str(m.created_at)
                    ),
                }
                for m in mappings
            ],
        }

        # The terminal payload is CONDITIONAL. get-task-status-request.json defaults
        # include_result to false "for lightweight status-only polls", and the response
        # schema says result is "Present when status is 'completed' and include_result was
        # true in the request; absent otherwise". This used to ship the payload on every
        # response under the non-spec name ``response_data``, so a status poll carried the
        # whole result and the flag had nothing left to switch.
        #
        # Withheld on an unfinished task rather than refused: the buyer is polling precisely
        # because they do not know yet, and the payload is not owed until completed. A
        # failed task's detail rides error_message, per "For failed tasks, read the existing
        # error field instead" (task-lifecycle.mdx).
        if req.include_result and task.status == "completed":
            task_detail["result"] = task.response_data

        # UNGRADED by any storyboard in the 3.1.1 tree, so this is the response schema's
        # item shape and nothing invented on top of it: {timestamp, type, data}, all three
        # required. Implemented rather than refused because the material is real -- a step
        # records the request that opened it and the response that closed it, with the
        # instants each happened at. An exchange that has not happened is OMITTED; padding
        # the array with a null-timestamped entry would describe one that never occurred.
        if req.include_history:
            task_detail["history"] = _task_history(task)

        return task_detail


def _task_history(task: Any) -> list[dict[str, Any]]:
    """The task's exchanges, in the shape get-task-status-response.json gives history items.

    Two at most today, because a workflow step records one request and one response. The
    list form is the spec's, not a guess at a future shape: if a step ever accumulates more
    exchanges they append here without any caller changing.
    """

    def _stamp(value: Any) -> str | None:
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    exchanges = (
        ("request", _stamp(task.created_at), task.request_data),
        ("response", _stamp(getattr(task, "completed_at", None)), task.response_data),
    )
    return [
        {"timestamp": timestamp, "type": kind, "data": data}
        for kind, timestamp, data in exchanges
        if timestamp is not None and data is not None
    ]


async def complete_task(
    task_id: str,
    status: str = "completed",
    response_data: dict[str, Any] | None = None,
    error_message: str | None = None,
    context: Context | None = None,
    identity: ResolvedIdentity | None = None,
) -> dict[str, Any]:
    """Complete a pending task (simulates human approval or async completion).

    Args:
        task_id: The unique task/workflow step ID
        status: New status ("completed" or "failed")
        response_data: Optional response data for completed tasks
        error_message: Error message if status is "failed"
        context: MCP context (automatically provided)
        identity: Pre-resolved identity (preferred over context)

    Returns:
        Dict containing task completion status
    """
    if identity is None and context is not None:
        identity = await context.get_state("identity")

    req = build_complete_task_request(
        task_id=task_id,
        status=status,
        response_data=response_data,
        error_message=error_message,
        context=context if not isinstance(context, Context) else None,
    )

    identity = require_identity(identity)
    tenant = require_tenant(identity)
    principal_id = require_principal_id(identity)  # F-03: an authenticated principal is required

    if status not in ["completed", "failed"]:
        raise AdCPValidationError(
            details=ValidationDetails(rejected_value=str(status)),
            field="status",
        )

    with WorkflowUoW(tenant["tenant_id"]) as uow:
        assert uow.workflows is not None

        # SCOPED, like the read. The same unscoped lookup made this a cross-principal
        # WRITE: principal A could complete principal B's task (salesagent-prkv.88).
        task = uow.workflows.get_by_step_id_or_raise(task_id, principal_id=principal_id)

        if task.status not in ["pending", "in_progress", "requires_approval"]:
            # `resource_id` is conflict.json's own name; `task_id` was a local synonym.
            # FIXME(#2099): `status` is not in the pinned shape -- the pin models a
            # conflict as expected_version vs current_version, not a status string.
            raise AdCPConflictError(details=ConflictDetails(resource_id=task_id, status=task.status))

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

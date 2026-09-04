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
from adcp.types.generated_poc.core.async_response_data import AdcpAsyncResponseData
from adcp.types.generated_poc.core.pagination_response import PaginationResponse
from adcp.types.generated_poc.protocol.get_task_status_response import HistoryItem
from adcp.types.generated_poc.protocol.list_tasks_request import Filters as ListTasksFilters
from adcp.types.generated_poc.protocol.list_tasks_request import Sort as ListTasksSort
from adcp.types.generated_poc.protocol.list_tasks_response import QuerySummary
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
from src.core.schemas import (
    CompleteTaskRequestLocal,
    ContextObject,
    GetTaskRequest,
    GetTaskResponse,
    ListTasksResponse,
    TaskSummary,
    enum_value,
)
from src.core.tools._request_defaults import omit_unset

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


#: The AdCP task a workflow step SERVICES, keyed by ``WorkflowStep.tool_name``.
#:
#: GROUNDED, not chosen. ``task_type`` is the buyer's TASK NAME, not our unit of work:
#:   * building/by-layer/L0/mcp-guide.mdx:459 @ 3.1.0 -- "`task_type` -- Task name (e.g.,
#:     `create_media_buy`, `sync_creatives`) for routing to per-task handlers";
#:   * protocol/calling-an-agent.mdx:95-99 -- the normative tasks/get response carries
#:     `task_type: "create_media_buy"` beside `protocol: "media-buy"`;
#:   * dist/compliance/3.1.1/domains/media-buy/scenarios/get_products_async.yaml GRADES it
#:     twice -- `tasks[0].task_type == "get_products"` ("Task type identifies get_products")
#:     on list_products_task, and `task_type == "get_products"` + `protocol == "media-buy"`
#:     on get_products_task_status_completed -- and FILTERS on `filters.task_type`, so an
#:     internal label would break the input side too, not merely misreport.
#:
#: This is why the fix was never the rename it was filed as. The response emitted
#: ``"type": step.step_type`` -- "tool_call", "approval", "media_buy_creation" -- and NONE of
#: our step_type values is a member of enums/task-type.json. Renaming the key would have
#: shipped `"task_type": "tool_call"`: still non-conformant, and now falsely claiming to BE
#: the spec field.
_TASK_TYPE_BY_TOOL: dict[str, str] = {
    "create_media_buy": "create_media_buy",
    "update_media_buy": "update_media_buy",
    "sync_creatives": "sync_creatives",
}

#: ``task_type -> AdCP protocol/domain``. DERIVED FROM THE PIN, not chosen: every member of
#: enums/task-type.json carries an ``enumDescriptions`` entry that opens with its domain
#: ("Media-buy domain: Sync creative assets ..."), and
#: ``test_task_domain_map_matches_the_pinned_enum_descriptions`` grades this map against that
#: block, the same way the recovery oracle grades CODE_TABLE against error-code.json's
#: enumMetadata. Written out here rather than parsed at run time because production has no
#: pinned-schema reader and must not grow one (no import-time filesystem I/O).
#:
#: Note sync_creatives is MEDIA-BUY domain, not creative -- which is exactly why this is
#: graded against the pin instead of inferred from the name.
_DOMAIN_BY_TASK_TYPE: dict[str, str] = {
    "create_media_buy": "media-buy",
    "update_media_buy": "media-buy",
    "sync_creatives": "media-buy",
}

#: The inverse of :data:`_SPEC_STATUS_TO_WORKFLOW_STATUS`. A response must speak the SPEC
#: vocabulary (TaskStatus) just as the filter accepts it.
_WORKFLOW_STATUS_TO_SPEC_STATUS: dict[str, str] = {
    "pending": "submitted",
    "in_progress": "working",
    "requires_approval": "input-required",
    "completed": "completed",
    "failed": "failed",
}


def _spec_task_type(step: Any) -> str:
    """The pinned ``task_type`` for *step*, or raise.

    FAILS LOUDLY on a step this seller cannot classify, and that is the point rather than an
    oversight. ``task_type`` is REQUIRED on both response shapes, so there is no "omit it";
    the two alternatives are both worse:

      * FABRICATE. src/core/webhook_validator.py already does this on the webhook path --
        ``validate_webhook_task_type`` substitutes "update_media_buy" for any label that is
        not a TaskType member, so a GAM order approval leaves this seller as an
        update_media_buy task the buyer does not have. That was chosen to keep a PAYLOAD
        parseable; the same trick on a task read corrupts the ANSWER a buyer acts on. Filed
        separately; deliberately not reused here.
      * OMIT the row, the way media_buy_list's ``_persisted_revision`` drops a media buy
        whose required revision is unpublishable. Defensible for a list, but get_task is a
        single-task read where omission means answering "no such task" about one that exists.

    So an unmappable step raises, visibly and attributably, naming the step and its
    tool_name. Adapter and approval steps (activate_gam_order, creative_approval, ...) have
    no member of enums/task-type.json, which is real: the pin's task IS the buyer's
    operation, and those steps are our implementation of one rather than tasks in their own
    right. The narrowing that would remove the whole residue -- exposing only steps that
    service a buyer operation -- is filed as its own bead and deliberately not folded in.
    """
    tool_name = getattr(step, "tool_name", None)
    task_type = _TASK_TYPE_BY_TOOL.get(tool_name or "")
    if task_type is None:
        raise AdCPValidationError(
            details=ValidationDetails(
                field="task_type",
                rejected_value=repr(tool_name),
                accepted_values=sorted(_TASK_TYPE_BY_TOOL),
            ),
            internal_detail=(
                f"workflow step {getattr(step, 'step_id', '?')!r} has tool_name {tool_name!r}, which is "
                f"not an AdCP task this seller can name. enums/task-type.json requires one, and "
                f"neither fabricating nor omitting it is honest -- see _spec_task_type."
            ),
        )
    return task_type


def _spec_task_status(step: Any) -> str:
    """The pinned ``status`` for *step*. Unknown workflow statuses map to the enum's own
    ``unknown`` member rather than raising: TaskStatus DEFINES that member for exactly this,
    and a status we cannot name is not a reason to refuse the whole read."""
    return _WORKFLOW_STATUS_TO_SPEC_STATUS.get(getattr(step, "status", "") or "", "unknown")


def _task_timestamps(step: Any) -> tuple[Any, Any, Any]:
    """``(created_at, updated_at, completed_at)`` for a step.

    ``updated_at`` is REQUIRED and non-nullable on both shapes and the response used to emit
    ``None``, which is schema-invalid. WorkflowStep has no updated_at column, so the last
    instant we actually recorded is used: ``completed_at`` when the step finished, else
    ``created_at``. Named here rather than inlined twice so the approximation is stated once
    and both responses share it.
    """
    created_at = step.created_at
    completed_at = getattr(step, "completed_at", None)
    return created_at, completed_at or created_at, completed_at


def _request_summary(request_data: Any) -> dict[str, Any] | None:
    """The non-spec ``summary`` highlights, or None. Extracted so the item build reads as one
    expression instead of three conditional mutations of a dict."""
    if not isinstance(request_data, dict) or not request_data:
        return None
    nested = request_data.get("request") or {}
    return {
        "operation": request_data.get("operation"),
        "media_buy_id": request_data.get("media_buy_id"),
        "po_number": nested.get("po_number") if isinstance(nested, dict) else None,
    }


def _list_tasks_response(tasks: list[TaskSummary], *, total: int | None, limit: int, offset: int) -> ListTasksResponse:
    """Wrap a page in the pinned envelope.

    The three envelope fields the response used to omit entirely, in one place so both exits
    (the no-such-status short circuit and the normal page) build the same shape:
      * ``query_summary`` -- total_matching/returned, which the storyboard grades directly
        (get_products_async.yaml, list_products_task: total_matching 1, returned 1);
      * ``pagination`` -- has_more is the pinned-required member; total_count carries what
        the old ``total`` did;
      * ``status`` -- composed onto every response by core/protocol-envelope.json. A
        synchronous read is "completed".
    ``offset``/``limit``/``has_more`` used to be top-level non-spec fields; they live inside
    pagination now, where the pin puts them.
    """
    return ListTasksResponse(
        status="completed",
        tasks=tasks,
        query_summary=QuerySummary(total_matching=total, returned=len(tasks)),
        pagination=PaginationResponse(
            has_more=(offset + limit < total) if total is not None else False,
            total_count=total,
        ),
    )


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
) -> ListTasksResponse:
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
        return _list_tasks_response([], total=0, limit=0, offset=0)
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

            task_type = _spec_task_type(task)
            created_at, updated_at, completed_at = _task_timestamps(task)

            formatted_tasks.append(
                TaskSummary(
                    task_id=task.step_id,
                    task_type=task_type,
                    domain=_DOMAIN_BY_TASK_TYPE[task_type],
                    status=_spec_task_status(task),
                    created_at=created_at,
                    updated_at=updated_at,
                    completed_at=completed_at,
                    context_id=task.context_id,
                    tool_name=task.tool_name,
                    owner=task.owner,
                    associated_objects=[
                        {"type": m.object_type, "id": m.object_id, "action": m.action} for m in mappings
                    ],
                    error_message=(task.error_message if task.status == "failed" else None),
                    summary=_request_summary(task.request_data),
                )
            )

        return _list_tasks_response(formatted_tasks, total=total, limit=limit, offset=offset)


def build_get_task_request(
    task_id: str,
    context: Any = None,
    account: LibraryAccountReference | None = None,
    # ``= None`` states NOTHING. GetTaskRequest declares False for both, and restating it
    # here made one fact two declarations; omit_unset below lets the model's own value
    # apply for a field the buyer did not send.
    include_history: bool | None = None,
    include_result: bool | None = None,
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
        **omit_unset(
            context=context,
            account=account,
            include_history=include_history,
            include_result=include_result,
            ext=ext,
        ),
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
    # ``= None`` states NOTHING: the advertised default comes from the DTO field
    # (derived_signature), and an omitted value reaches the builder as None, which
    # omit_unset drops so the model's own default applies.
    include_history: bool | None = None,
    include_result: bool | None = None,
    ext: ExtensionObject | None = None,
) -> GetTaskResponse:
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

        task_type = _spec_task_type(task)
        created_at, updated_at, completed_at = _task_timestamps(task)

        # ``protocol`` and ``domain`` are ONE axis under two names -- get-task-status-response
        # spells it protocol (AdcpProtocol, 7 members), list-tasks-response tasks[] spells it
        # domain (Domain, 3) -- so both read the same map rather than each deriving its own.
        task_detail = GetTaskResponse(
            task_id=task.step_id,
            task_type=task_type,
            protocol=_DOMAIN_BY_TASK_TYPE[task_type],
            status=_spec_task_status(task),
            created_at=created_at,
            updated_at=updated_at,
            completed_at=completed_at,
            context_id=task.context_id,
            tool_name=task.tool_name,
            owner=task.owner,
            request_data=task.request_data,
            error_message=task.error_message,
            associated_objects=[
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
        )

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
            # VALIDATED, not cast. The pin types ``result`` as core/async-response-data.json --
            # a union of the concrete AdCP task results -- while ``response_data`` is whatever
            # this seller stored. model_validate raises on a payload that is not one of them
            # rather than shipping an arbitrary dict under a spec field name, which is the same
            # fail-loudly posture _spec_task_type takes.
            task_detail.result = AdcpAsyncResponseData.model_validate(task.response_data)

        # UNGRADED by any storyboard in the 3.1.1 tree, so this is the response schema's
        # item shape and nothing invented on top of it: {timestamp, type, data}, all three
        # required. Implemented rather than refused because the material is real -- a step
        # records the request that opened it and the response that closed it, with the
        # instants each happened at. An exchange that has not happened is OMITTED; padding
        # the array with a null-timestamped entry would describe one that never occurred.
        if req.include_history:
            task_detail.history = [HistoryItem(**entry) for entry in _task_history(task)]

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

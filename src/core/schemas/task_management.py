"""Task-queue schemas — the declared response model for `list_tasks`.

`list_tasks` used to return an untyped `dict[str, Any]` assembled field by field
in the tool body, including a hand-written `context.model_dump(mode="json")`. An
untyped return is why the pinned-required `query_summary` / `pagination` could go
missing for a whole release without anything noticing: there was no model to be
invalid. Serialization belongs to the model (Critical Pattern #4), not to the
tool body.

Divergence, stated rather than hidden: AdCP 3.1.1
`protocol/list-tasks-response.json` types each `tasks[]` item with REQUIRED
`task_type` (enum of AdCP task names), `domain` and `updated_at`. This seller's
queue is `workflow_steps`, which also holds steps that are not AdCP tasks at all
(publisher approvals, adapter calls such as `create_gam_order`) and has no
`updated_at` column — there is no honest value to put in those fields for such a
row, and fabricating one is worse than the shape below. `tasks[]` items are
therefore the seller's own work-queue shape, which is EXACTLY what this tool has
always emitted on the wire; typing it changes no bytes. The item-level divergence
is pre-existing and tracked separately from this model.
"""

from __future__ import annotations

from adcp.types.generated_poc.core.pagination_response import PaginationResponse as ResponsePagination
from adcp.types.generated_poc.protocol.list_tasks_response import ListTasksResponse as LibraryListTasksResponse
from adcp.types.generated_poc.protocol.list_tasks_response import QuerySummary as ListTasksQuerySummary
from pydantic import Field

from src.core.schemas._base import NestedModelSerializerMixin, SalesAgentBaseModel

__all__ = [
    "ListTasksQuerySummary",
    "ListTasksResponse",
    "ResponsePagination",
    "WorkflowTask",
    "WorkflowTaskObject",
    "WorkflowTaskSummary",
]


class WorkflowTaskSummary(SalesAgentBaseModel):
    """The buyer-facing digest of a queued step's original request."""

    operation: str | None = Field(default=None, description="The operation the queued step performs")
    media_buy_id: str | None = Field(default=None, description="Media buy the step acts on, when it acts on one")
    po_number: str | None = Field(default=None, description="Purchase order number carried by the original request")


class WorkflowTaskObject(SalesAgentBaseModel):
    """One object a queued step is associated with (media buy, creative, ...)."""

    type: str | None = Field(default=None, description="Object type, e.g. media_buy or creative")
    id: str | None = Field(default=None, description="Object identifier")
    action: str | None = Field(default=None, description="What the step does to the object")


class WorkflowTask(SalesAgentBaseModel):
    """One entry of this seller's work queue, as `list_tasks` reports it."""

    task_id: str = Field(..., description="Workflow step identifier")
    status: str = Field(..., description="Step status: pending, in_progress, completed, failed, requires_approval")
    type: str = Field(..., description="Step type, e.g. tool_call or approval")
    tool_name: str | None = Field(default=None, description="AdCP tool the step runs, when it runs one")
    owner: str | None = Field(default=None, description="Who must act: principal, publisher, or system")
    created_at: str | None = Field(default=None, description="ISO 8601 creation timestamp")
    updated_at: str | None = Field(default=None, description="ISO 8601 timestamp of the last recorded change")
    context_id: str | None = Field(default=None, description="Context this step belongs to")
    associated_objects: list[WorkflowTaskObject] = Field(
        default_factory=list, description="Objects this step is associated with"
    )
    summary: WorkflowTaskSummary | None = Field(default=None, description="Digest of the step's original request")
    error_message: str | None = Field(default=None, description="Failure detail, present only on failed steps")


class ListTasksResponse(NestedModelSerializerMixin, LibraryListTasksResponse):
    """Extends the pinned list_tasks response with this seller's task shape.

    Inherited from the library, and therefore enforced rather than remembered:
    `query_summary`, `pagination` and `context` — the three the untyped dict kept
    losing. `query_summary.returned` is THIS page's slice size and
    `query_summary.total_matching` the unpaged total; AdCP 3.1.1
    `compliance/.../pagination-integrity.yaml` grades both.

    `tasks` is redeclared for Critical Pattern #4 (nested local subtype), the same
    override `ListCreativesResponse.creatives` carries — see this module's header
    for why the item type is local rather than the pinned `Task`.
    """

    tasks: list[WorkflowTask] = Field(..., description="Queued tasks matching the query")  # type: ignore[assignment]

    # The flat pagination fields this tool has emitted since before the pinned
    # response schema had `pagination`. Kept (and now typed) because buyers and
    # the admin UI read them; they carry the same numbers `pagination` does.
    total: int | None = Field(default=None, description="Total tasks matching the filters, across all pages")
    offset: int | None = Field(default=None, description="Offset this page started at")
    limit: int | None = Field(default=None, description="Maximum tasks requested for this page")
    has_more: bool | None = Field(default=None, description="Whether more tasks follow this page")

    def __str__(self) -> str:
        """Human-readable summary for the protocol envelope."""
        returned = self.query_summary.returned if self.query_summary else len(self.tasks)
        total = self.query_summary.total_matching if self.query_summary else None
        if total is None or returned == total:
            return f"Found {returned} task{'s' if returned != 1 else ''}."
        return f"Showing {returned} of {total} tasks."

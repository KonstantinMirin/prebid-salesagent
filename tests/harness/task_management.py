"""TaskManagementEnv -- integration test environment for list_tasks.

list_tasks is an MCP-only surface: no A2A raw wrapper (the A2A task
polling handlers ``on_get_task``/``on_list_tasks`` are a separate, native
A2A task-lifecycle concept, not a caller of this module) and no REST route.
``call_a2a``/``call_rest`` are intentionally left unimplemented (base class
default raises ``NotImplementedError``).

Requires: integration_db fixture.
"""

from __future__ import annotations

from typing import Any

from tests.harness._base import IntegrationEnv
from tests.harness.transport import DeliverResult


class TaskManagementEnv(IntegrationEnv):
    """Integration test environment for list_tasks.

    No patches -- list_tasks reads real WorkflowStep rows via WorkflowUoW.
    """

    # Dispatch declaration: the base owns call_mcp/call_a2a. list_tasks is
    # MCP-only (no A2A skill, no REST route).
    MCP_TOOL = "list_tasks"
    RESPONSE_MODEL = dict

    EXTERNAL_PATCHES: dict[str, str] = {}

    def _configure_mocks(self) -> None:
        """No mocks needed -- real WorkflowUoW."""

    # FIXME(#2201): production's list_tasks wire omits query_summary and
    # pagination, both required by the pinned ListTasksResponse. Remove this
    # override -- and its _KNOWN_DELIVER_OVERRIDES row -- when #2201 lands.
    def deliver_mcp(self, **kwargs: Any) -> DeliverResult:
        """Dispatch WITHOUT the client core's pinned parse-back.

        The core's UNWRAP parses the wire into ``spec_response_model("list_tasks")``
        (``tests/harness/client.py``, ``_parse_pinned_response`` inside
        ``_unwrap_tool_success``) and production's body is
        ``{tasks, total, offset, limit, has_more}`` -- no ``query_summary``, no
        ``pagination``, both of which the pinned model requires. So joining the core
        turns a live conformance gap into a dispatch error: the ``ValidationError``
        escapes ``_dispatch_core`` (whose try/except covers DELIVER only), is folded
        into an error ``TransportResult`` by ``McpDispatcher``, and ``wire_response``
        comes back ``None``. ``RESPONSE_MODEL``/``response_parser`` cannot rescue it --
        they are consulted further down ``_deliver_via_client``, on a line the
        exception never reaches.

        ``_run_mcp_client`` is the SAME delivery the core's DELIVER step performs
        (``client._deliver_mcp`` calls it with ``response_cls=dict``); this skips only
        the parse-back. The override exists to keep the gap attributable rather than
        hidden by loosening the core.

        THIS DOCSTRING REPLACES ONE THAT SAID THE OPPOSITE. It claimed "production's
        list_tasks emits the pinned-required query_summary + pagination, so the core's
        pinned parse succeeds" -- false when written. It is why this override and its
        allowlist row were deleted, and why the deletion was recorded as a shrink.
        """
        return self._run_mcp_client(self.MCP_TOOL, dict, **kwargs)

    def call_impl(self, **kwargs: Any) -> dict[str, Any]:
        """Call list_tasks directly with real DB (no transport dispatch)."""
        import asyncio

        from src.core.tools.task_management import list_tasks

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        return asyncio.run(list_tasks(identity=identity, **kwargs))

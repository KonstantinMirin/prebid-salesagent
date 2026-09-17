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


class TaskManagementEnv(IntegrationEnv):
    """Integration test environment for list_tasks.

    No patches -- list_tasks reads real WorkflowStep rows via WorkflowUoW.
    """

    # Dispatch declaration: the base owns call_mcp/call_a2a and this env DELEGATES to the
    # client core. It kept a deliver_mcp override under FIXME(#2201) because production's
    # list_tasks wire omitted the pinned-required query_summary and pagination, so the
    # core's parse-back raised. #2201 landed; the response extends the pinned
    # ListTasksResponse now, the parse succeeds, and the override and its
    # _KNOWN_DELIVER_OVERRIDES row are both gone. list_tasks is MCP-only (no A2A skill,
    # no REST route).
    MCP_TOOL = "list_tasks"
    RESPONSE_MODEL = dict

    EXTERNAL_PATCHES: dict[str, str] = {}

    def _configure_mocks(self) -> None:
        """No mocks needed -- real WorkflowUoW."""

    def call_impl(self, **kwargs: Any) -> dict[str, Any]:
        """Call list_tasks directly with real DB (no transport dispatch)."""
        import asyncio

        # ``_list_tasks_impl``, not ``list_tasks``: #1721 split every tool into a
        # transport-agnostic ``_<tool>_impl(req, identity)`` and left no bare ``list_tasks``
        # in the module. The old name raised AttributeError at CALL time, not import time,
        # because the import is function-local -- the same shape as the AdCPError import in
        # tests/harness/_base.py. Request-shaped, like every sibling harness call_impl.
        from src.core.schemas import ListTasksRequest
        from src.core.tools.task_management import _list_tasks_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        req = kwargs.pop("req", None) or ListTasksRequest(**kwargs)
        return asyncio.run(_list_tasks_impl(req=req, identity=identity))

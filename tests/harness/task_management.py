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

    EXTERNAL_PATCHES: dict[str, str] = {}

    def _configure_mocks(self) -> None:
        """No mocks needed -- real WorkflowUoW."""

    def call_impl(self, **kwargs: Any) -> dict[str, Any]:
        """Call list_tasks directly with real DB (no transport dispatch)."""
        import asyncio

        from src.core.tools.task_management import list_tasks

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        return asyncio.run(list_tasks(identity=identity, **kwargs))

    def call_mcp(self, **kwargs: Any) -> Any:
        """Call list_tasks via Client(mcp) -- full pipeline dispatch, including
        the ``accepts_spec_request_fields`` widening at the registration
        chokepoint (main.py:346-351). This is the only dispatch path that
        reproduces the field-silently-stripped defect this env was added to
        regression-test.
        """
        return self._run_mcp_client("list_tasks", dict, **kwargs)

"""Context echo through the MCP wire for get_adcp_capabilities and list_tasks
(salesagent-vuz9t.14).

Core Invariant: a field an agent publishes as ACCEPTED on the wire must
never silently disappear before it can satisfy the ONE obligation the spec
attaches to it. For ``context`` specifically that obligation is AdCP
3.1.1's normative echo contract (dist/docs/3.1.1/building/by-layer/L2/
context-sessions.mdx, "Application Context (context)" rules 1-6): the
agent MUST echo the caller's ``context`` object byte-for-byte in the
response, and MUST NOT parse or act on its contents.

Before this fix, ``accepts_spec_request_fields`` (main.py:346-351)
silently added ``context`` to the published MCP schema for
``get_adcp_capabilities`` and ``list_tasks`` (the only 2 of the 16
registered tools where ``context`` was not already a first-class
parameter) and then stripped it before the tool body ran -- so a caller
that supplied ``context`` on the wire got a 200 with the field silently
dropped, never echoed. Accepting the field and never honoring the ONE
thing the spec requires of it is a conformance lie the widening
introduced, not pre-existing debt it revealed (every other tool that
accepts ``context`` -- get_media_buys, create_media_buy, etc. -- already
echoes it; see tests/harness/media_buy_list.py-style wiring).

These tests dispatch through the REAL MCP pipeline
(``tests.harness._base.IntegrationEnv._run_mcp_client`` -> ``Client(mcp)``
-> ``main.mcp``), which is the only path that exercises
``accepts_spec_request_fields`` and therefore the only path that can prove
this regression fixed. A test that called the ``_impl`` functions directly
would not reproduce the original bug at all.
"""

import pytest
from adcp.types import ContextObject

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class TestGetAdcpCapabilitiesContextEcho:
    """get_adcp_capabilities MUST echo a caller-supplied context byte-for-byte."""

    def test_context_echoed_through_mcp_wire(self, integration_db):
        from tests.factories import PrincipalFactory, TenantFactory
        from tests.harness.capabilities import CapabilitiesEnv

        with CapabilitiesEnv(tenant_id="ctx-echo-caps", principal_id="ctx_principal") as env:
            tenant = TenantFactory(tenant_id="ctx-echo-caps")
            PrincipalFactory(tenant=tenant, principal_id="ctx_principal")

            response = env.call_mcp(context={"trace_id": "trace_caps_1", "channel": "unit-test"})

        assert response.context is not None, (
            "get_adcp_capabilities dropped the caller's context object -- AdCP 3.1.1's "
            "normative echo contract requires it be echoed byte-for-byte in the response."
        )
        assert response.context.model_dump(exclude_none=True) == {
            "trace_id": "trace_caps_1",
            "channel": "unit-test",
        }

    def test_context_echoed_through_a2a_wire(self, integration_db):
        """A2A parity: _handle_get_adcp_capabilities_skill must forward and
        echo context too, not just the MCP wrapper (the review round that
        graded this ticket caught this call site not forwarding
        parameters.get('context') at all before this fix)."""
        from tests.factories import PrincipalFactory, TenantFactory
        from tests.harness.capabilities import CapabilitiesEnv

        with CapabilitiesEnv(tenant_id="ctx-echo-caps-a2a", principal_id="ctx_principal_a2a") as env:
            tenant = TenantFactory(tenant_id="ctx-echo-caps-a2a")
            PrincipalFactory(tenant=tenant, principal_id="ctx_principal_a2a")

            response = env.call_a2a(context={"trace_id": "trace_caps_a2a_1"})

        assert response.context is not None, (
            "A2A get_adcp_capabilities dropped the caller's context object."
        )
        assert response.context.model_dump(exclude_none=True) == {"trace_id": "trace_caps_a2a_1"}

    def test_no_context_supplied_means_none_in_response(self, integration_db):
        """Rule 4, 'No synthesis': absent request context must stay absent, never fabricated."""
        from tests.factories import PrincipalFactory, TenantFactory
        from tests.harness.capabilities import CapabilitiesEnv

        with CapabilitiesEnv(tenant_id="ctx-echo-caps-none", principal_id="ctx_principal_none") as env:
            tenant = TenantFactory(tenant_id="ctx-echo-caps-none")
            PrincipalFactory(tenant=tenant, principal_id="ctx_principal_none")

            response = env.call_mcp()

        assert response.context is None


class TestListTasksContextEcho:
    """list_tasks MUST echo a caller-supplied context byte-for-byte."""

    def test_context_echoed_through_mcp_wire(self, integration_db):
        from tests.factories import PrincipalFactory, TenantFactory
        from tests.harness.task_management import TaskManagementEnv

        with TaskManagementEnv(tenant_id="ctx-echo-tasks", principal_id="ctx_task_principal") as env:
            tenant = TenantFactory(tenant_id="ctx-echo-tasks")
            PrincipalFactory(tenant=tenant, principal_id="ctx_task_principal")

            result = env.call_mcp(context={"trace_id": "trace_tasks_1"})

        assert result["context"] is not None, (
            "list_tasks dropped the caller's context object -- AdCP 3.1.1's normative "
            "echo contract requires it be echoed byte-for-byte in the response."
        )
        assert result["context"] == {"trace_id": "trace_tasks_1"}

    def test_no_context_supplied_means_none_in_response(self, integration_db):
        from tests.factories import PrincipalFactory, TenantFactory
        from tests.harness.task_management import TaskManagementEnv

        with TaskManagementEnv(tenant_id="ctx-echo-tasks-none", principal_id="ctx_task_principal_none") as env:
            tenant = TenantFactory(tenant_id="ctx-echo-tasks-none")
            PrincipalFactory(tenant=tenant, principal_id="ctx_task_principal_none")

            result = env.call_mcp()

        assert result["context"] is None

    def test_context_object_direct_call_is_never_parsed_or_acted_on(self, integration_db):
        """Rule 6, 'No action': list_tasks must not branch on context's contents.

        Calls the impl directly (not through MCP) with a context payload shaped
        like a filter, and asserts it has zero effect on the returned task set --
        pinning that ``context`` stays opaque even though it superficially looks
        like it could be misread as a filter.
        """
        from tests.factories import PrincipalFactory, TenantFactory
        from tests.harness.task_management import TaskManagementEnv

        with TaskManagementEnv(tenant_id="ctx-echo-tasks-opaque", principal_id="ctx_task_opaque") as env:
            tenant = TenantFactory(tenant_id="ctx-echo-tasks-opaque")
            PrincipalFactory(tenant=tenant, principal_id="ctx_task_opaque")

            baseline = env.call_impl()
            with_lookalike_context = env.call_impl(context=ContextObject.model_validate({"status": "completed"}))

        assert with_lookalike_context["tasks"] == baseline["tasks"]
        assert with_lookalike_context["total"] == baseline["total"]

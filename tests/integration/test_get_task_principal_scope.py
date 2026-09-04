"""get_task does not serve one principal's task to another, inside one tenant.

protocol/get-task-status-request.json @ AdCP 3.1.1 attaches the obligation to ``account``:
"Sellers MUST return REFERENCE_NOT_FOUND for a task_id that exists only under a different
account or principal." The graded step is
dist/compliance/3.1.1/domains/media-buy/scenarios/get_products_async.yaml ::
``get_products_task_status_wrong_account`` — poll the same task_id from a different account,
expect error_code REFERENCE_NOT_FOUND, with the expected text "Sellers MUST NOT reveal
whether the task exists under another account or principal."

Before salesagent-prkv.85 the lookup filtered ``DBContext.tenant_id`` and nothing else, so
any authenticated principal could read any other principal's task in the same tenant —
``request_data`` and ``response_data`` included. Nothing covered it.

INTEGRATION, against real Postgres, deliberately: the defect and the fix both live in a
query's WHERE clause. A mocked repository would return whatever the test told it to and
would have passed just as happily before the fix as after (CLAUDE.md: repository changes
are graded against real Postgres, not a mock echo chamber).
"""

import pytest

from src.core.exceptions import AdCPTaskNotFoundError
from tests.factories import PrincipalFactory, TenantFactory
from tests.harness._base import BareIntegrationEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

TENANT_ID = "task_scope_tenant"
OWNER_ID = "principal_owner"
INTRUDER_ID = "principal_intruder"


def _seed_task(env) -> str:
    """Commit one tenant, two principals, and a task owned by the FIRST of them.

    The context and the step are written through PRODUCTION's own creators —
    ``build_context`` and ``WorkflowRepository.create_step`` — rather than constructed
    inline. That is the repository-pattern rule, and here it also buys the thing the test
    depends on: ``create_step`` takes the Context INSTANCE and refuses a cross-tenant write,
    so the ownership this test asserts on is established the same way production establishes
    it, not asserted into existence by the fixture.
    """
    from src.core.database.repositories.workflow import WorkflowRepository, build_context

    tenant = TenantFactory(tenant_id=TENANT_ID)
    PrincipalFactory(tenant=tenant, principal_id=OWNER_ID)
    PrincipalFactory(tenant=tenant, principal_id=INTRUDER_ID)

    session = env.get_session()
    context = build_context(session, tenant_id=TENANT_ID, principal_id=OWNER_ID)
    step = WorkflowRepository(session, TENANT_ID).create_step(
        context=context,
        step_type="tool_call",
        owner="principal",
        status="completed",
        tool_name="create_media_buy",
        request_data={"secret_brief": "the other buyer's brief"},
        response_data={"media_buy_id": "mb_not_yours"},
    )
    session.commit()
    return step.step_id


async def _get_task(task_id: str, principal_id: str, **kwargs):
    from src.core.main import mcp

    tool = await mcp.get_tool("get_task")
    identity = PrincipalFactory.make_identity(
        principal_id=principal_id,
        tenant_id=TENANT_ID,
        tenant={"tenant_id": TENANT_ID, "name": "Task Scope Tenant"},
        protocol="mcp",
    )
    return await tool.fn(task_id=task_id, identity=identity, **kwargs)


class TestGetTaskIsScopedToItsPrincipal:
    """The account obligation, graded on the wire the tool actually answers over."""

    @pytest.mark.asyncio
    async def test_another_principal_is_refused(self, integration_db):
        """A second principal in the SAME tenant gets REFERENCE_NOT_FOUND, not the task."""
        with BareIntegrationEnv(tenant_id=TENANT_ID) as env:
            task_id = _seed_task(env)

        with pytest.raises(AdCPTaskNotFoundError) as exc_info:
            await _get_task(task_id, principal_id=INTRUDER_ID, include_result=True)

        # The published code, and the same one an absent task raises — so the refusal
        # does not disclose that the task exists under someone else.
        assert exc_info.value.error_code == "REFERENCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_a_task_that_does_not_exist_is_refused_identically(self, integration_db):
        """The control. Without it the assertion above cannot show the refusal is opaque.

        Two different codes for "not yours" and "not there" would leak existence just as
        surely as returning the task, so the point is that these two are the SAME.
        """
        with BareIntegrationEnv(tenant_id=TENANT_ID) as env:
            _seed_task(env)

        with pytest.raises(AdCPTaskNotFoundError) as exc_info:
            await _get_task("step_no_such_task", principal_id=INTRUDER_ID)

        assert exc_info.value.error_code == "REFERENCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_the_owner_still_gets_their_own_task(self, integration_db):
        """The other half: scoping must not have locked the owner out of their own task.

        Asserted on the result payload, not merely on task_id, because a fix that returned
        the row but dropped its contents would pass a bare identity check.
        """
        with BareIntegrationEnv(tenant_id=TENANT_ID) as env:
            task_id = _seed_task(env)

        detail = await _get_task(task_id, principal_id=OWNER_ID, include_result=True)

        assert detail["task_id"] == task_id
        assert detail["result"] == {"media_buy_id": "mb_not_yours"}

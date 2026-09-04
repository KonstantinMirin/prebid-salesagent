"""One principal's task is not readable, listable or completable by another, inside a tenant.

salesagent-prkv.88. protocol/get-task-status-request.json @ AdCP 3.1.1 attaches the
obligation to ``account``: "Sellers MUST return REFERENCE_NOT_FOUND for a task_id that
exists only under a different account or principal." Two storyboard steps in
dist/compliance/3.1.1/domains/media-buy/scenarios/get_products_async.yaml grade it:

  * ``get_products_task_status_wrong_account`` — poll the same task_id from a different
    account, expect error_code REFERENCE_NOT_FOUND, "Sellers MUST NOT reveal whether the
    task exists under another account or principal."
  * ``list_products_task_wrong_account`` — list the same task_id from a different account,
    expect total_matching 0, "Sellers MUST scope task reconciliation to the authenticated
    account + principal pair."

WorkflowRepository.get_by_step_id and list_by_tenant/count_by_tenant filtered
``DBContext.tenant_id`` and nothing else, so inside one tenant every authenticated
principal could read, list and COMPLETE every other principal's tasks. Nothing covered it,
and the tenant-isolation guard was green while naming the leaking method as exemplary.

ON THE WIRE, not on an exception class. tests/CLAUDE.md: the harness no longer reconstructs
AdCPSalesAgentError from a wire response, and a test asserting on a rebuilt object grades
the reconstruction rather than the buyer-facing envelope. A refusal that is correct in
Python and wrong on the wire is exactly the failure this obligation is about. Asserted
through ``result.assert_wire_error`` rather than the bare envelope primitive, which adds
the CODE_TABLE emittability check and fails loudly when no envelope was captured at all --
the way a "passing" error test can grade nothing.

INTEGRATION, against real Postgres: the defect and the fix are both a WHERE clause. A
mocked repository returns whatever the test told it to and would pass identically before
and after.
"""

from typing import Any

import pytest

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.task_management import TaskManagementEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

TENANT_ID = "task_scope_tenant"
OWNER_ID = "principal_owner"
INTRUDER_ID = "principal_intruder"


class _GetTaskEnv(TaskManagementEnv):
    """TaskManagementEnv aimed at get_task rather than list_tasks.

    Subclassed HERE rather than added to tests/harness: the base already dispatches any
    registered MCP tool by name, so this needs the name and nothing else.
    """

    MCP_TOOL = "get_task"


class _CompleteTaskEnv(TaskManagementEnv):
    """The write half. Same reasoning as :class:`_GetTaskEnv`."""

    MCP_TOOL = "complete_task"


def _seed(env, principal_id: str) -> str:
    """Seed a tenant, both principals, and one task owned by OWNER_ID. Returns its step id.

    Written through PRODUCTION's creators — ``build_context`` and
    ``WorkflowRepository.create_step`` — not constructed inline: the repository-pattern
    guard forbids new inline session writes, and using the real path means the ownership
    this test asserts on is established the way production establishes it.
    """
    from src.core.database.repositories.workflow import WorkflowRepository, build_context

    tenant = TenantFactory(tenant_id=TENANT_ID)
    PrincipalFactory(tenant=tenant, principal_id=OWNER_ID)
    PrincipalFactory(tenant=tenant, principal_id=INTRUDER_ID)

    session = env.get_session()
    context = build_context(session, tenant_id=TENANT_ID, principal_id=principal_id)
    step = WorkflowRepository(session, TENANT_ID).create_step(
        context=context,
        step_type="tool_call",
        owner="principal",
        status="requires_approval",
        tool_name="create_media_buy",
        request_data={"secret_brief": "the other buyer's brief"},
    )
    session.commit()
    return step.step_id


def _blind_echoed_ids(envelope: Any) -> Any:
    """The envelope with every echoed ``step_id`` replaced by a constant.

    ``details.step_id`` is the id the CALLER sent, so of course it differs between two
    lookups of different ids — it is the one field that legitimately cannot match and is
    not a disclosure, because the buyer already knows what they asked for. Everything else
    must be identical. Blinding it here rather than comparing field-by-field is what keeps
    the comparison total: a field added to this envelope later is compared automatically
    instead of being silently omitted from a hand-written list.
    """
    if isinstance(envelope, dict):
        return {k: ("<echoed>" if k == "step_id" else _blind_echoed_ids(v)) for k, v in envelope.items()}
    if isinstance(envelope, list):
        return [_blind_echoed_ids(item) for item in envelope]
    return envelope


def _assert_two_distinct_principals(env) -> None:
    """Prove the two principals authenticate as DIFFERENT callers before asserting a refusal.

    The precondition the previous version of this file silently lacked. A cross-principal
    test that authenticates as one principal twice cannot fail, and passes loudest on a
    build that leaks. So the tokens are compared here: they come from two separate Principal
    rows and the production chain resolves each to its own identity.
    """
    owner_token = _become(env, OWNER_ID)
    intruder_token = _become(env, INTRUDER_ID)
    assert owner_token != intruder_token, (
        "both principals presented the SAME credential, so every call below authenticates "
        "as one caller and the cross-principal assertions cannot fail"
    )


def _become(env, principal_id: str) -> str:
    """Re-authenticate the env AS *principal_id*, and return the token it will present.

    ``env.switch_principal`` is the public accessor for this: it clears the identity cache
    so the next access re-runs the auth-token lookup against the committed principal rows.

    THIS REPLACES A HELPER THAT DID NOT WORK AND COULD NOT FAIL. It was
    ``env.identity.model_copy(update={"principal_id": ...})`` — which changes the field the
    dispatcher never reads. ``_run_mcp_client`` pops ``identity`` and uses it ONLY to build
    credential headers (``_credential_headers`` reads ``auth_token`` and nothing else), then
    the production chain resolves header -> token -> DB -> ResolvedIdentity. Copying a
    different principal_id onto the OWNER's token meant every call authenticated as the
    owner: the "intruder" never existed, and the whole suite would have passed against a
    leaking build.
    """
    env.switch_principal(principal_id)
    token = env.identity.auth_token
    assert token, (
        f"{principal_id} resolved no auth_token, so the dispatch would fall back to a "
        "mocked identity instead of the real header -> token -> DB chain"
    )
    return token


class TestTaskIsScopedToItsPrincipal:
    """Read, list and complete, each graded on the envelope the buyer actually receives."""

    def test_reading_another_principals_task_is_refused(self, integration_db):
        """REFERENCE_NOT_FOUND on the wire, which is the code the storyboard demands."""
        with _GetTaskEnv(tenant_id=TENANT_ID, principal_id=OWNER_ID) as env:
            task_id = _seed(env, OWNER_ID)
            _assert_two_distinct_principals(env)
            _become(env, INTRUDER_ID)
            result = env.call_via(Transport.MCP, task_id=task_id)

        assert result.is_error
        result.assert_wire_error("REFERENCE_NOT_FOUND")

    def test_the_two_refusals_are_indistinguishable(self, integration_db):
        """ "Not yours" and "not there" must be the SAME envelope, field for field.

        This is the control, and the reason the test above means anything. The obligation
        is not merely that a cross-principal lookup fails — it is that the buyer cannot
        tell a task they may not see from one that does not exist. "Sellers MUST NOT reveal
        whether the task exists under another account or principal."

        Compared as WHOLE ENVELOPES, not as two error codes. A code-only assertion passes
        even when the refusals differ in message, suggestion, or a details dict that names
        the owning principal — and a leak in any of those is exactly the disclosure this
        forbids. The only field allowed to differ is the step_id the caller sent back to
        itself, which is blinded above with the reason stated.
        """
        with _GetTaskEnv(tenant_id=TENANT_ID, principal_id=OWNER_ID) as env:
            task_id = _seed(env, OWNER_ID)
            _become(env, INTRUDER_ID)
            not_yours = env.call_via(Transport.MCP, task_id=task_id)
            not_there = env.call_via(Transport.MCP, task_id="step_no_such_task")

        assert not_yours.is_error
        assert not_there.is_error
        not_there.assert_wire_error("REFERENCE_NOT_FOUND")

        assert _blind_echoed_ids(not_yours.wire_error_envelope) == _blind_echoed_ids(not_there.wire_error_envelope), (
            "the refusal for a task owned by another principal differs from the refusal for "
            "a task that does not exist — the difference is what tells a buyer the task is real"
        )

    def test_completing_another_principals_task_is_refused(self, integration_db):
        """The WRITE half. The same unscoped lookup let A complete B's task."""
        with _CompleteTaskEnv(tenant_id=TENANT_ID, principal_id=OWNER_ID) as env:
            task_id = _seed(env, OWNER_ID)
            _become(env, INTRUDER_ID)
            result = env.call_via(Transport.MCP, task_id=task_id, status="completed")

        assert result.is_error
        result.assert_wire_error("REFERENCE_NOT_FOUND")

    def test_listing_does_not_show_another_principals_task(self, integration_db):
        """list_tasks was the widest of the three: it listed the whole tenant.

        Graded on both the page and the COUNT. A page scoped to the caller beside a
        tenant-wide total still discloses how many tasks the others hold — the same leak
        by arithmetic.
        """
        with TaskManagementEnv(tenant_id=TENANT_ID, principal_id=OWNER_ID) as env:
            _seed(env, OWNER_ID)
            _become(env, INTRUDER_ID)
            payload = env.call_via(Transport.MCP).payload

        assert payload["tasks"] == []
        assert payload["total"] == 0

    def test_the_owner_still_reads_and_lists_their_own(self, integration_db):
        """The other half: scoping must not have locked the owner out.

        Both surfaces in one test because the risk they share is one over-broad filter.
        Asserted on the request payload, not merely on task_id, because a fix that returned
        the row stripped of its contents would satisfy an id check.
        """
        with _GetTaskEnv(tenant_id=TENANT_ID, principal_id=OWNER_ID) as env:
            task_id = _seed(env, OWNER_ID)
            detail = env.call_via(Transport.MCP, task_id=task_id).payload

        assert detail["task_id"] == task_id
        assert detail["request_data"] == {"secret_brief": "the other buyer's brief"}

        with TaskManagementEnv(tenant_id=TENANT_ID, principal_id=OWNER_ID) as env:
            _seed(env, OWNER_ID)
            payload = env.call_via(Transport.MCP).payload

        assert [task["task_id"] for task in payload["tasks"]] == [task_id]
        assert payload["total"] == 1

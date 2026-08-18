"""Envs that carry a registration from INGEST to DELIVERY, over a real origin.

Epic D lane C2 (salesagent-fo99.2) turns the persistence and stash boundaries
into value-takers. Every one of those boundaries is INVISIBLE from either end
in isolation: a repository test proves what a row holds, and a sender test
proves what a sender does with a row, but neither can see a registration whose
credential half was dropped SOMEWHERE BETWEEN the two. The only observation
that spans the gap is the one the buyer makes — did the POST that finally
arrived carry a signature it can verify.

So both envs here are the same shape: a real local origin, the real production
path from the buyer's registration call through to the send, and the origin's
captured request as the sole authority. Nothing about the intermediate
representation is asserted; the graders would survive the raw dict, the wire
dump and the value alike, which is what makes them a regression guard for a
refactor whose whole point is to change that representation.

``LocalOriginMixin`` supplies the origin (real TLS, private-range hatch open
for its lifetime); the domain envs supply production. Neither is re-derived.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from tests.harness._mixins import LocalOriginMixin
from tests.harness.media_buy_dual import MediaBuyDualEnv
from tests.harness.product import ProductEnv

if TYPE_CHECKING:
    from collections.abc import Iterator


def _drop_registered_auth(stashed: Any) -> Any:
    """Return *stashed* with its credential half removed, whatever shape it is.

    Deliberately shape-agnostic. The mutation this powers is the reverse-TDD
    control for the A2A grader: it must express "the auth fields did not
    survive into the stash" against the RAW PROTOBUF stashed today and against
    the ``ValidatedWebhookRegistration`` stashed after lane C2, or the control
    would silently stop mutating anything the day the representation changes —
    and a control that mutates nothing reports a vacuous grader as a real one.
    """
    from src.core.security.webhook_egress import webhook_auth_for
    from src.core.webhooks.registration import ValidatedWebhookRegistration

    if isinstance(stashed, ValidatedWebhookRegistration):
        return ValidatedWebhookRegistration(
            url=stashed.url,
            authentication_type=None,
            authentication_token=None,
            auth=webhook_auth_for(None, None),  # type: ignore[arg-type]
        )
    stripped = type(stashed)()
    stripped.CopyFrom(stashed)
    stripped.ClearField("authentication")
    return stripped


class _AuthDroppingStash(dict):
    """A ``_task_push_configs`` that loses the credential half on the way in."""

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, _drop_registered_auth(value))


class A2APushRegistrationEnv(LocalOriginMixin, ProductEnv):
    """``message/send`` registers the webhook in the PROTOCOL envelope.

    ``on_message_send`` reads ``params.configuration.task_push_notification_config``
    before any skill routing, stashes it under the task id, and
    ``_send_protocol_webhook`` reads that stash back when the task reaches a
    terminal state. The skill the registration rides on (``get_products``) is
    incidental — it exists only to give the task something to complete.
    """

    def call_a2a_with_push_config(self, push_config: dict[str, Any], **kwargs: Any) -> Any:
        """Dispatch ``message/send`` carrying a protocol-level push registration.

        ``push_config`` is the A2A protobuf shape (SINGULAR ``scheme``), not the
        AdCP tool shape — see ``_a2a_send_message_configuration``.
        """
        return self.call_a2a(a2a_push_notification_config=push_config, **kwargs)

    @contextmanager
    def stash_drops_the_credential_half(self) -> Iterator[None]:
        """Make the task stash lose the auth fields — the reverse-TDD mutation.

        Patches ``__init__`` rather than an instance because the handler is
        constructed inside ``_run_a2a_handler``; the stash is replaced right
        after production installs it, so everything up to and including the
        ingest gate runs untouched and only what SURVIVES the stash differs.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        original_init = AdCPRequestHandler.__init__

        def _init_with_dropping_stash(handler: Any, *args: Any, **kwargs: Any) -> None:
            original_init(handler, *args, **kwargs)
            handler._task_push_configs = _AuthDroppingStash(handler._task_push_configs)

        with patch.object(AdCPRequestHandler, "__init__", _init_with_dropping_stash):
            yield


class MediaBuyPushRegistrationEnv(LocalOriginMixin, MediaBuyDualEnv):
    """``create_media_buy`` / ``update_media_buy`` register; the WORKFLOW STEP delivers.

    Both tools stash the registration on the workflow step they create, and
    ``ContextManager._send_push_notifications`` reads that stash back when the
    step's status changes. Production's own ``update_workflow_step`` calls are
    mocked out by the media-buy envs (so a create does not fire a webhook
    mid-test), which is why the status change is driven here, explicitly,
    through the REAL context manager — the same entry point the admin approval
    flow and the adapter completion path both use.
    """

    def register_delivery_target(self) -> Any:
        """Store ONE active ``PushNotificationConfig`` row pointing at the origin.

        ``_send_push_notifications`` sends once per active row per mapping, so
        the row count is the delivery count — one row keeps
        ``delivery_attempts == 1`` a statement about signing rather than about
        fan-out. What the row HOLDS is not what gets delivered to: the config
        the sender receives is rebuilt from the workflow step's stash. The row
        stands in for the earlier ``create_media_buy`` that registered it, which
        is the only way a real buyer's ``update_media_buy`` webhook is ever
        delivered — update never upserts one itself.
        """
        from tests.factories import PushNotificationConfigFactory

        tenant, principal = self.setup_default_data()
        return PushNotificationConfigFactory(
            tenant=tenant,
            principal=principal,
            url=self.webhook_url,
            is_active=True,
        )

    def push_step(self, tool_name: str) -> Any:
        """The workflow step ``tool_name`` created, read fresh from the database.

        ``expire_all`` first: production wrote the row through its own session,
        so the env-bound session would otherwise answer from its identity map.
        """
        from src.core.database.models import WorkflowStep

        self.get_session().expire_all()
        steps = [step for step in self.get_workflow_steps() if step.tool_name == tool_name]
        assert len(steps) == 1, (
            f"expected exactly one {tool_name} workflow step to grade, found {len(steps)} — "
            f"a second step would make the delivery count ambiguous"
        )
        step: WorkflowStep = steps[0]
        return step

    def stashed_push_config(self, step: Any) -> dict[str, Any]:
        """What the tool actually stashed under ``push_notification_config``."""
        stashed = (step.request_data or {}).get("push_notification_config")
        assert isinstance(stashed, dict), (
            f"the workflow step stashed {stashed!r} under push_notification_config — "
            f"there is nothing for the delivery path to read back"
        )
        return stashed

    def drop_stashed_credential_half(self, step: Any) -> None:
        """Remove the auth block from the stash — the reverse-TDD mutation.

        Keyed on the ``authentication`` block that every producer of this key
        writes today (``model_dump(mode="json")`` of the library
        ``PushNotificationConfig``), so the mutation means the same thing before
        and after lane C2 changes who writes it. Asserts the block was there:
        a mutation that removed nothing would make the control vacuous.
        """
        stashed = self.stashed_push_config(step)
        assert "authentication" in stashed, (
            "nothing to drop — the stash already carries no authentication block, so this control would grade nothing"
        )
        request_data = dict(step.request_data)
        request_data["push_notification_config"] = {
            key: value for key, value in stashed.items() if key != "authentication"
        }
        step.request_data = request_data
        self.get_session().add(step)
        self.get_session().commit()

    def poison_stashed_registration(self, step: Any) -> None:
        """Rewrite the stash into a shape the INGEST GATE refuses.

        HMAC-SHA256 with the credential half removed — the one document the
        registration gate rejects outright, so ``from_stash`` raises
        ``AdCPValidationError`` at delivery time. Distinct from
        :meth:`drop_stashed_credential_half`, which produces a stash the gate
        ACCEPTS (as unauthenticated) and therefore delivers unsigned: that one
        grades signing, this one grades what happens when rehydration REFUSES.
        """
        stashed = self.stashed_push_config(step)
        request_data = dict(step.request_data)
        request_data["push_notification_config"] = {
            "url": stashed["url"],
            "authentication": {"schemes": ["HMAC-SHA256"]},
        }
        step.request_data = request_data
        self.get_session().add(step)
        self.get_session().commit()

    def persisted_config_rows(self) -> list[Any]:
        """Every push-notification row this env's tenant currently holds."""
        from sqlalchemy import select

        from src.core.database.models import PushNotificationConfig

        self.get_session().expire_all()
        return list(self.get_session().scalars(select(PushNotificationConfig)).all())

    def step_status(self, step: Any) -> str:
        """The step's status, read fresh — production wrote it in another session."""
        self.get_session().expire_all()
        self.get_session().refresh(step)
        return step.status

    def complete_step(self, step: Any) -> None:
        """Drive the step to ``completed`` through the REAL context manager.

        This is the call that fires ``_send_push_notifications``. It runs with
        no event loop running, so production takes its ``asyncio.run`` branch
        and the delivery has finished by the time this returns — the assertions
        need no polling.
        """
        from src.core.context_manager import get_context_manager

        self._commit_factory_data()
        get_context_manager().update_workflow_step(step_id=step.step_id, status="completed")

"""SSRF gate for protocol push / reporting webhook URLs.

Pins that ProtocolWebhookService refuses unsafe URLs before any outbound POST,
mirrors application-level WebhookURLValidator usage in webhook_delivery, and
covers registration wiring: create_media_buy, sync_creatives, A2A message/send,
and A2A set_push_notification_config handler.

Wire-level VALIDATION_ERROR / recovery=correctable + suggestion for
create_media_buy and sync_creatives is graded by transport-blind BDD scenarios
(BR-UC-002-ext-webhook-ssrf, BR-UC-006-ext-webhook-ssrf). A2A-native push-config
endpoints translate the same registration gate to InvalidParamsError with the
AdCP VALIDATION_ERROR envelope in ``data`` — pinned below.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
from a2a.types import (
    InvalidParamsError,
    Message,
    Part,
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
    TaskPushNotificationConfig,
)
from adcp.types import ReportingWebhook

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler, _reject_unsafe_a2a_webhook_url
from src.core.database.models import PushNotificationConfig
from src.core.exceptions import AdCPValidationError
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas import CreateMediaBuyRequest
from src.core.security import outbound_http
from src.core.testing_hooks import AdCPTestContext
from src.core.tools.creatives._sync import _sync_creatives_impl
from src.core.tools.media_buy_create import _create_media_buy_impl
from src.core.webhook_validator import WEBHOOK_SSRF_SUGGESTION_DEV, reject_unsafe_webhook_registration_url
from src.services.protocol_webhook_service import ProtocolWebhookService
from tests.factories.principal import PrincipalFactory
from tests.helpers import assert_envelope_shape
from tests.helpers.adcp_factories import create_test_media_buy_request_dict, valid_reporting_webhook
from tests.helpers.egress_hatches import egress_hatch_env
from tests.helpers.local_http_origin import run_local_origin

_METADATA_URL = "http://169.254.169.254/latest/meta-data/"

# What a delivery carries when the case is only about the destination. Written
# once because all four send-path cases below pass the same pair and none of
# them is about the payload: ``task_type`` deliberately stays outside the
# delivery-report pair so no case touches the database.
_PAYLOAD = {"task_id": "t1", "status": "completed"}
_METADATA = {"task_type": "create_media_buy", "tenant_id": "t1"}


class _RecordingTransport(httpx.AsyncBaseTransport):
    """Delegating transport that logs the URL of every hop httpx dispatches."""

    def __init__(self, inner: httpx.AsyncBaseTransport, dispatched: list[str]) -> None:
        self._inner = inner
        self._dispatched = dispatched

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._dispatched.append(str(request.url))
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


@contextlib.contextmanager
def _egress_hatches(*, private: bool, insecure: bool) -> Iterator[None]:
    """Pin BOTH outbound escape hatches for the block.

    A refusal case that leaves them ambient is graded by whichever gate the
    surrounding shell happened to arm — ``run_all_tests_host.sh`` exports both
    as true — so a test meaning "production posture" would silently grade
    nothing. Same pair, same spelling, as ``LocalOriginMixin`` and the seam's
    own suite.
    """
    with patch.dict(os.environ, egress_hatch_env(private=private, insecure=insecure)):
        yield


@contextlib.contextmanager
def _dispatched_hops() -> Iterator[list[str]]:
    """Record every HTTP hop the egress seam actually puts on the wire.

    WRAPS the real ``build_async_ip_pinned_transport`` rather than replacing it:
    the SDK still resolves, validates and pins the destination, so nothing here
    can turn a refusal into a pass. A URL the seam refuses never reaches the
    builder at all, which is why an empty list is direct evidence that nothing
    left the process — and every redirect hop httpx follows is dispatched
    through the same client transport, so a followed redirect shows up as a
    second entry naming where it went.
    """
    dispatched: list[str] = []
    real_builder = outbound_http.build_async_ip_pinned_transport

    def build(url: str, **kwargs: object) -> httpx.AsyncBaseTransport:
        return _RecordingTransport(real_builder(url, **kwargs), dispatched)

    with patch.object(outbound_http, "build_async_ip_pinned_transport", build):
        yield dispatched


def _config(url: str) -> PushNotificationConfig:
    return PushNotificationConfig(
        id="pnc-ssrf-test",
        tenant_id="t1",
        principal_id="p1",
        url=url,
        authentication_type=None,
        authentication_token=None,
        is_active=True,
    )


def _reporting_webhook(url: str) -> ReportingWebhook:
    return ReportingWebhook.model_validate(valid_reporting_webhook(url))


def _identity() -> ResolvedIdentity:
    return PrincipalFactory.make_identity(
        principal_id="principal_1",
        tenant_id="test_tenant",
        auth_token="test-token",
        protocol="mcp",
        tenant={"tenant_id": "test_tenant", "human_review_required": False, "auto_create_media_buys": True},
        testing_context=AdCPTestContext(dry_run=False, test_session_id="test-session"),
    )


def _minimal_create_request(**overrides):
    data = create_test_media_buy_request_dict(
        product_ids=["prod_1"],
        total_budget=5000.0,
        pricing_option_id="cpm_usd_fixed",
        idempotency_key="unit-ssrf-create-key-0001",
        **overrides,
    )
    return CreateMediaBuyRequest(**data)


@pytest.mark.asyncio
async def test_send_notification_rejects_metadata_url_without_post() -> None:
    """A cloud-metadata destination fails closed, with nothing put on the wire.

    Graded with BOTH escape hatches OPEN, which is what makes the case about the
    metadata blocklist and nothing else: with the hatches shut, a plain ``http://``
    link-local URL is already refused by the seam's TLS rule and a green mark
    would say nothing about the address. ``adcp.signing`` refuses
    ``169.254.169.254`` unconditionally, hatches or not — the property
    ``tests/integration/test_outbound_http.py::test_cloud_metadata_stays_refused_with_both_flags_on``
    grades directly.
    """
    service = ProtocolWebhookService()

    with _egress_hatches(private=True, insecure=True), _dispatched_hops() as hops:
        sent = await service.send_notification(_config(_METADATA_URL), payload=_PAYLOAD, metadata=_METADATA)

    assert sent is False
    assert hops == [], f"a request was dispatched towards a cloud-metadata address: {hops}"


@pytest.mark.asyncio
async def test_send_notification_rejects_localhost_without_post() -> None:
    """Under production posture a loopback destination is refused, unreached.

    The endpoint is a REAL origin that is genuinely listening on ``localhost``,
    so "no POST" is read off the server's own hit count rather than off a mock:
    zero hits is a fact about a socket nobody connected to. Opening the hatches
    is the whole difference between this and
    :func:`test_send_notification_posts_when_url_is_public`, which reaches the
    same kind of origin and counts one hit.
    """
    service = ProtocolWebhookService()

    with run_local_origin(listen_host="localhost") as origin:
        origin.respond_with(200)

        with _egress_hatches(private=False, insecure=False), _dispatched_hops() as hops:
            sent = await service.send_notification(
                _config(f"{origin.base_url}/webhook"), payload=_PAYLOAD, metadata=_METADATA
            )

        assert sent is False
        assert origin.hits == 0, f"the loopback endpoint was reached anyway: {origin.requests}"
        assert hops == [], f"a request was dispatched towards a reserved address: {hops}"


@pytest.mark.asyncio
async def test_send_notification_posts_when_url_is_public() -> None:
    """A destination the seam permits is really POSTed to — body and headers included.

    Asserted against the bytes the origin received rather than against the
    arguments a transport mock was handed: the latter reads back the object the
    caller passed and proves nothing crossed a socket. The escape hatches stand
    in for "public" here because the only origin a unit test can really run
    listens on loopback over plain HTTP; what the case grades is that a
    destination the gate ALLOWS is dialled and served.
    """
    service = ProtocolWebhookService()

    with run_local_origin() as origin:
        origin.respond_with(200)

        with _egress_hatches(private=True, insecure=True):
            sent = await service.send_notification(
                _config(f"{origin.base_url}/webhook"), payload=_PAYLOAD, metadata=_METADATA
            )

        assert sent is True
        assert origin.hits == 1, f"the endpoint served {origin.hits} requests for one notification"
        request = origin.last_request
        assert request.method == "POST"
        assert request.path == "/webhook"
        assert request.json() == _PAYLOAD
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["User-Agent"] == "AdCP-Sales-Agent/1.0"


@pytest.mark.asyncio
async def test_send_notification_does_not_follow_redirect_to_metadata() -> None:
    """A 302 towards link-local metadata is returned, never chased.

    The dispatch log is the proof, not the return value: were the redirect
    followed, the pinned transport would refuse the wrong-host connect and the
    call would STILL come back ``False``, so ``sent is False`` alone cannot tell
    a refused redirect from a followed one. Every hop httpx follows is dispatched
    through the client's transport, so a chased 302 appears as a second entry
    naming ``169.254.169.254``.

    The hit count carries the other half: a 302 is terminal to the seam, so the
    buyer's endpoint is asked exactly once.
    """
    service = ProtocolWebhookService()

    with run_local_origin() as origin:
        origin.redirect_to(_METADATA_URL, status=302)
        webhook_url = f"{origin.base_url}/webhook"

        with _egress_hatches(private=True, insecure=True), _dispatched_hops() as hops:
            sent = await service.send_notification(_config(webhook_url), payload=_PAYLOAD, metadata=_METADATA)

        assert sent is False
        assert origin.hits == 1, f"the 302 was retried: {origin.paths}"
        assert hops == [webhook_url], f"the redirect was followed: {hops}"


def test_reject_unsafe_webhook_registration_url_raises_validation_error() -> None:
    with pytest.raises(AdCPValidationError) as exc_info:
        reject_unsafe_webhook_registration_url(
            "http://metadata.google.internal/computeMetadata/v1/",
            field="reporting_webhook.url",
        )
    assert exc_info.value.field == "reporting_webhook.url"
    assert "Invalid reporting_webhook.url" in exc_info.value.message
    assert exc_info.value.suggestion == WEBHOOK_SSRF_SUGGESTION_DEV
    assert exc_info.value.recovery == "correctable"


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_reject_unsafe_webhook_registration_url_noop_on_blank(blank: str | None) -> None:
    """Blank / missing URL is not a rejection — callers extract-then-call unconditionally."""
    reject_unsafe_webhook_registration_url(blank, field="push_notification_config.url")


def test_sanitize_webhook_url_for_log_strips_credentials_query_and_fragment() -> None:
    from src.core.webhook_validator import (
        UNPARSEABLE_WEBHOOK_URL_FOR_LOG,
        sanitize_webhook_url_for_log,
        webhook_url_for_log,
    )

    dirty = "https://user:pass@buyer.example.com:8443/hook?token=abc#frag"
    assert sanitize_webhook_url_for_log(dirty) == "https://buyer.example.com/hook"
    assert webhook_url_for_log(dirty) == "https://buyer.example.com/hook"
    assert sanitize_webhook_url_for_log(None) is None
    assert sanitize_webhook_url_for_log("not-a-url") is None
    assert webhook_url_for_log(None) == UNPARSEABLE_WEBHOOK_URL_FOR_LOG
    assert webhook_url_for_log("not-a-url") == UNPARSEABLE_WEBHOOK_URL_FOR_LOG


def test_reject_unsafe_webhook_registration_url_allows_public() -> None:
    # Registration skips DNS — fixture hostnames must not NXDOMAIN-fail.
    reject_unsafe_webhook_registration_url("https://buyer.example.com/hook", field="push_notification_config.url")


def test_reject_unsafe_webhook_registration_url_allows_unresolvable_public_hostname() -> None:
    """Registration gate must not require DNS (BDD fixture hosts)."""
    reject_unsafe_webhook_registration_url(
        "https://nonexistent-buyer-ssrf-fixture.invalid/hook",
        field="reporting_webhook.url",
    )


def test_push_notification_config_repo_upsert_rejects_ssrf_url() -> None:
    """Repository upsert is a second registration gate (A2A set_push_notification_config)."""
    from src.core.database.repositories.push_notification_config import PushNotificationConfigRepository

    repo = PushNotificationConfigRepository(MagicMock(), "t1")
    with pytest.raises(ValueError, match="Invalid webhook URL"):
        repo.upsert(
            config_id="pnc_bad",
            principal_id="p1",
            url=_METADATA_URL,
            authentication_type=None,
            authentication_token=None,
            validation_token=None,
        )


@pytest.mark.asyncio
async def test_create_media_buy_rejects_reporting_webhook_anyurl() -> None:
    """Registration gate must run for real ReportingWebhook.url (AnyUrl, not str)."""
    req = _minimal_create_request(reporting_webhook=_reporting_webhook(_METADATA_URL))
    with pytest.raises(AdCPValidationError) as exc_info:
        await _create_media_buy_impl(req, identity=_identity())
    assert exc_info.value.field == "reporting_webhook.url"
    assert "Invalid reporting_webhook.url" in exc_info.value.message


@pytest.mark.asyncio
async def test_create_media_buy_rejects_push_config_before_workflow() -> None:
    """PNC SSRF must run before workflow metadata write (wiring + ordering)."""
    req = _minimal_create_request()
    mock_ctx = MagicMock()
    with (
        patch("src.core.tools.media_buy_create.get_context_manager", return_value=mock_ctx),
        pytest.raises(AdCPValidationError) as exc_info,
    ):
        await _create_media_buy_impl(
            req,
            push_notification_config={"url": _METADATA_URL},
            identity=_identity(),
        )
    assert exc_info.value.field == "push_notification_config.url"
    mock_ctx.create_workflow_step.assert_not_called()
    mock_ctx.create_context.assert_not_called()


def test_sync_creatives_rejects_unsafe_push_config_url() -> None:
    """sync_creatives must reject metadata URL at registration before DB work."""
    with pytest.raises(AdCPValidationError) as exc_info:
        _sync_creatives_impl(
            creatives=[],
            push_notification_config={"url": _METADATA_URL},
            identity=_identity(),
        )
    assert exc_info.value.field == "push_notification_config.url"


def test_reject_unsafe_a2a_webhook_url_rejects_metadata() -> None:
    """A2A registration helper maps SSRF to InvalidParamsError + AdCP envelope in data."""
    with pytest.raises(InvalidParamsError, match="Invalid push_notification_config.url") as exc_info:
        _reject_unsafe_a2a_webhook_url(_METADATA_URL)
    assert_envelope_shape(exc_info.value.data, "VALIDATION_ERROR", recovery="correctable")
    assert exc_info.value.data["errors"][0].get("suggestion")


@pytest.mark.asyncio
async def test_a2a_message_send_rejects_unsafe_push_config_url() -> None:
    """message/send must reject metadata URL before stash."""
    handler = AdCPRequestHandler()
    text_part = Part()
    text_part.text = "list products"
    message = Message(message_id="m-ssrf", role=Role.ROLE_USER, parts=[text_part])
    push = TaskPushNotificationConfig(url=_METADATA_URL)
    params = SendMessageRequest(
        message=message,
        configuration=SendMessageConfiguration(task_push_notification_config=push),
    )

    with pytest.raises(InvalidParamsError, match="Invalid push_notification_config.url") as exc_info:
        await handler.on_message_send(params, context=MagicMock())

    assert_envelope_shape(exc_info.value.data, "VALIDATION_ERROR", recovery="correctable")
    assert handler._task_push_configs == {}


@pytest.mark.asyncio
async def test_a2a_set_push_handler_rejects_metadata_url() -> None:
    """Handler on_create_task_push_notification_config must reject before upsert."""
    handler = AdCPRequestHandler()
    identity = _identity()
    tool_context = MagicMock()
    tool_context.tenant_id = identity.tenant_id
    tool_context.principal_id = identity.principal_id
    params = TaskPushNotificationConfig(url=_METADATA_URL, task_id="task-1", id="pnc-1")

    with (
        patch.object(handler, "_get_auth_token", return_value="tok"),
        patch.object(handler, "_resolve_a2a_identity", return_value=identity),
        patch.object(handler, "_make_tool_context", return_value=tool_context),
        patch("src.a2a_server.adcp_a2a_server.PushNotificationConfigUoW") as mock_uow,
        pytest.raises(InvalidParamsError, match="Invalid push_notification_config.url") as exc_info,
    ):
        await handler.on_create_task_push_notification_config(params, context=MagicMock())

    assert_envelope_shape(exc_info.value.data, "VALIDATION_ERROR", recovery="correctable")
    mock_uow.assert_not_called()

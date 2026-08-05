"""
Protocol-level webhook delivery service for A2A/MCP push notifications.

This service handles protocol-level push notifications (operation status updates)
as distinct from application-level webhooks (scheduled reporting delivery).

Protocol-level webhooks are configured via:
- A2A: MessageSendConfiguration.pushNotificationConfig
- MCP: (future) protocol wrapper extension

Application-level webhooks are configured via:
- AdCP: CreateMediaBuyRequest.reporting_webhook
"""

import json
import logging
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from a2a.types import Task, TaskStatusUpdateEvent
from adcp import extract_webhook_result_data, sign_legacy_webhook
from adcp.types import McpWebhookPayload
from google.protobuf.json_format import MessageToDict

from src.core.audit_logger import get_audit_logger
from src.core.database.database_session import get_db_session
from src.core.database.models import PushNotificationConfig
from src.core.database.repositories.delivery import DeliveryRepository
from src.core.security.outbound_http import (
    OutboundDeliveryFailed,
    OutboundRequestBlocked,
    asend,
    terminal_client_error_status,
)
from src.core.webhook_validator import webhook_url_for_log

logger = logging.getLogger(__name__)


# FIXME(gh-#1299): behaviour-identical backport of adcp 5.4.0
# ``adcp.to_wire_dict`` + ``_normalize_a2a_task_state_to_v03`` (adcp #602).
# salesagent is pinned to adcp 4.3.0, which predates that public seam.
# Delete this block and call ``adcp.to_wire_dict()`` directly once salesagent
# bumps adcp to the version that ships it.
def _normalize_message_role(message: dict[str, Any]) -> None:
    """Rewrite a2a-sdk 1.0 ``ROLE_*`` to the A2A 0.3 lowercase wire form."""
    role = message.get("role")
    if isinstance(role, str) and role.startswith("ROLE_"):
        message["role"] = role[len("ROLE_") :].lower()


def _normalize_a2a_task_state_to_v03(payload: dict[str, Any]) -> None:
    """Rewrite a2a-sdk 1.0 ``TASK_STATE_*`` / ``ROLE_*`` enums to A2A 0.3
    lowercase wire strings in-place. Buyer receivers parse the 0.3 shape
    (``"state": "completed"``); the 1.0 protobuf JSON emitter produces
    ``"state": "TASK_STATE_COMPLETED"`` by default.
    """
    status = payload.get("status")
    if isinstance(status, dict):
        state = status.get("state")
        if isinstance(state, str) and state.startswith("TASK_STATE_"):
            # Spec uses hyphens for multi-word states (e.g. "auth-required").
            status["state"] = state[len("TASK_STATE_") :].lower().replace("_", "-")
        message = status.get("message")
        if isinstance(message, dict):
            _normalize_message_role(message)
    history = payload.get("history")
    if isinstance(history, list):
        for entry in history:
            if isinstance(entry, dict):
                _normalize_message_role(entry)
    if "role" in payload:
        _normalize_message_role(payload)


def _to_wire_dict(payload: Any) -> dict[str, Any]:
    """Serialize any AdCP webhook payload to a JSON-ready dict.

    Behaviour-identical backport of adcp 5.4.0 ``adcp.to_wire_dict``:

    * a2a ``Task`` / ``TaskStatusUpdateEvent`` (protobuf, a2a-sdk 1.0+) ->
      ``MessageToDict(preserving_proto_field_name=False)`` so JSON keys are
      the A2A wire camelCase (``id``, ``contextId``, ``taskId``), then enum
      values normalized from the 1.0 form (``TASK_STATE_COMPLETED``,
      ``ROLE_AGENT``) to the 0.3-spec lowercase form (``completed``,
      ``agent``).
    * Any Pydantic model (``McpWebhookPayload`` ...) ->
      ``model_dump(mode="json", exclude_none=True)``.
    * ``Mapping`` -> coerced to ``dict`` (legacy hand-built passthrough).
    """
    if isinstance(payload, (Task, TaskStatusUpdateEvent)):
        data: dict[str, Any] = MessageToDict(payload, preserving_proto_field_name=False)
        _normalize_a2a_task_state_to_v03(data)
        return data
    if hasattr(payload, "model_dump"):
        return cast(dict[str, Any], payload.model_dump(mode="json", exclude_none=True))
    if isinstance(payload, Mapping):
        return dict(payload)
    raise TypeError(
        f"Unsupported webhook payload type {type(payload).__name__}: expected "
        "a2a Task / TaskStatusUpdateEvent (protobuf), an AdCP Pydantic model "
        "(e.g. McpWebhookPayload), or a Mapping[str, Any]."
    )


class ProtocolWebhookService:
    """
    Service for sending protocol-level push notifications to clients.

    Supports authentication schemes:
    - HMAC-SHA256: Signs payload with shared secret
    - Bearer: Sends credentials as Bearer token
    - None: No authentication
    """

    def _record_delivery_failure(
        self,
        *,
        log_id: str,
        url: str,
        task_id: Any,
        task_type: Any,
        tenant_id: Any,
        principal_id: Any,
        media_buy_id: Any,
        sequence_number: int,
        notification_type: Any,
        attempts: int,
        http_status_code: int | None,
        error: str,
        payload_size_bytes: int,
        start_time: float,
        audit_logger: Any,
    ) -> bool:
        """Book one failed delivery: the log row, the audit entry, and ``False``.

        Shared by all three failure arms — a refusal, a delivery failure and an
        unexpected error differ only in what they know (attempts, status, wording),
        not in what they must record. Repeating the row-and-audit block per arm is
        how one of them ends up silently not recording, which for a refusal would
        mean a misconfigured destination leaving no trace at all.
        """
        response_time_ms = int((time.time() - start_time) * 1000)

        if task_type in ("delivery_report", "media_buy_delivery") and media_buy_id and tenant_id and principal_id:
            self._write_delivery_log(
                log_id=log_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                webhook_url=url,
                task_type=task_type,
                status="failed",
                sequence_number=sequence_number,
                notification_type=notification_type,
                attempt_count=attempts,
                http_status_code=http_status_code,
                payload_size_bytes=payload_size_bytes,
                response_time_ms=response_time_ms,
                error_message=error,
                completed_at=datetime.now(UTC),
            )

        if audit_logger:
            audit_logger.log_warning(f"{task_type} webhook failed for task {task_id}: {error}")

        return False

    async def send_notification(
        self,
        push_notification_config: PushNotificationConfig,
        payload: Task | TaskStatusUpdateEvent | McpWebhookPayload,
        metadata: dict[str, Any],
    ) -> bool:
        """
        Send a protocol-level push notification to the configured webhook.

        Args:
            push_notification_config: Push notification configuration from protocol layer
            payload: For A2A it can be Task or TaskStatusUpdateEvent types for MCP it wil be McpWebhookPayload.
                Use create_a2a_webhook_payload or create_mcp_webhook_payload from adcp's official python client to get the payload for particular task and status
            metadata: Contains app specific metadata's such as task_type, tenant_id, principal_id

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not push_notification_config or not push_notification_config.url:
            # TODO: @yusuf - Double check logging actually works for Task, TaskStatusUpdateEvent and McpWebhookPayload types
            logger.debug(
                f"No webhook URL configured in the push notification. Here's payload: {payload}, skipping notification"
            )
            return False

        # The buyer's URL is delivered verbatim: the egress seam (asend) is the only
        # place allowed to decide anything about the destination. Test stacks that
        # need a reachable callback register a reachable hostname instead — the e2e
        # stack runs a long-lived webhook-capture service behind the shared TLS front
        # (see tests/e2e/webhook_capture_service.py).
        #
        # No separate send-time SSRF gate here (#1697 added one in front of the old
        # requests.Session POST): the seam's pre-connection check IS that gate and
        # strictly more — same HTTPS requirement and same reserved/private-address
        # refusal over a real DNS resolution, but it then PINS the connection to the
        # address it validated, so the resolve-then-connect rebinding window a
        # separate validator leaves open does not exist. Re-validating here would be
        # a second copy of address policy, which is what deleting the hand-rolled
        # validator (src/core/security/url_validator.py) was for.
        url = push_notification_config.url

        # Prepare headers
        headers = {"Content-Type": "application/json", "User-Agent": "AdCP-Sales-Agent/1.0"}

        # Log sanitized config (exclude sensitive authentication_token)
        safe_config = {
            "url": push_notification_config.url if hasattr(push_notification_config, "url") else None,
            "authentication_type": (
                push_notification_config.authentication_type
                if hasattr(push_notification_config, "authentication_type")
                else None
            ),
            # DO NOT log authentication_token - security risk
        }
        logger.info(f"push_notification_config (sanitized): {safe_config}")

        # Serialize payload to dict at the delivery boundary (for HMAC signing
        # and JSON send). Single seam: a2a protobuf -> camelCase + A2A 0.3
        # lowercase enum values; Pydantic -> model_dump; Mapping -> dict.
        payload_dict: dict[str, Any] = _to_wire_dict(payload)

        # Apply authentication based on schemes
        body_bytes: bytes | None = None
        if (
            push_notification_config.authentication_type == "HMAC-SHA256"
            and push_notification_config.authentication_token
        ):
            # Sign the EXACT bytes that go on the wire. The signature is computed
            # over compact JSON; letting the HTTP client re-serialize the dict
            # produces different bytes (spaced separators under requests, escaped
            # non-ASCII under others) and the receiver's verification fails — a
            # security header that silently stops meaning anything. The SDK returns
            # the signed bytes for exactly this reason, so we transmit those.
            signed_headers, body_bytes = sign_legacy_webhook(
                push_notification_config.authentication_token,
                payload_dict,
                timestamp=str(int(time.time())),
                headers=headers,
            )
            headers = {**headers, **signed_headers}

        elif push_notification_config.authentication_type == "Bearer" and push_notification_config.authentication_token:
            # Use Bearer token authentication
            headers["Authorization"] = f"Bearer {push_notification_config.authentication_token}"

        # Send notification with retry logic and logging
        return await self._send_with_retry_and_logging(
            url=url, payload=payload_dict, headers=headers, metadata=metadata, body_bytes=body_bytes
        )

    @staticmethod
    def _write_delivery_log(
        *,
        log_id: str,
        tenant_id: str,
        principal_id: str,
        media_buy_id: str,
        webhook_url: str,
        task_type: str,
        status: str,
        sequence_number: int = 1,
        notification_type: str | None = None,
        attempt_count: int = 1,
        http_status_code: int | None = None,
        error_message: str | None = None,
        payload_size_bytes: int | None = None,
        response_time_ms: int | None = None,
        completed_at: datetime | None = None,
        next_retry_at: datetime | None = None,
    ) -> None:
        """Write a webhook delivery log entry via the DeliveryRepository."""
        try:
            with get_db_session() as session:
                repo = DeliveryRepository(session, tenant_id)
                repo.create_log(
                    log_id=log_id,
                    principal_id=principal_id,
                    media_buy_id=media_buy_id,
                    webhook_url=webhook_url,
                    task_type=task_type,
                    status=status,
                    sequence_number=sequence_number,
                    notification_type=notification_type,
                    attempt_count=attempt_count,
                    http_status_code=http_status_code,
                    error_message=error_message,
                    payload_size_bytes=payload_size_bytes,
                    response_time_ms=response_time_ms,
                    completed_at=completed_at,
                    next_retry_at=next_retry_at,
                )
                session.commit()
        except Exception as e:
            logger.error(f"Failed to write webhook delivery log: {e}")

    async def _send_with_retry_and_logging(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict,
        metadata: dict[str, Any],
        max_attempts: int = 3,
        body_bytes: bytes | None = None,
    ) -> bool:
        """Deliver one webhook through the egress seam, with logging and audit trail.

        ``body_bytes`` are the exact bytes an HMAC signature was computed over, when
        the destination is signed. They go on the wire unchanged — re-serializing the
        dict here would break the signature the receiver checks.
        """
        # The bytes that actually go on the wire, so payload_size_bytes measures what
        # was sent rather than a second serialization of the same dict.
        wire_body = body_bytes if body_bytes is not None else json.dumps(payload).encode("utf-8")
        payload_size_bytes = len(wire_body)

        task_type = metadata["task_type"] if "task_type" in metadata else None
        tenant_id = metadata["tenant_id"] if "tenant_id" in metadata else None
        principal_id = metadata["principal_id"] if "principal_id" in metadata else None
        media_buy_id = metadata["media_buy_id"] if "media_buy_id" in metadata else None

        # TODO: Fix type annotation discrepancy in adcp library - extract_webhook_result_data
        # returns dict at runtime but is typed as AdcpAsyncResponseData | None
        result = cast(dict[str, Any] | None, extract_webhook_result_data(payload))
        # After serialization, payload is always a dict - extract task_id accordingly.
        # A2A Task uses 'id'; A2A TaskStatusUpdateEvent uses camelCase 'taskId' (proto
        # json_name wire contract); MCP uses snake_case 'task_id'.
        task_id = payload.get("id") or payload.get("taskId") or payload.get("task_id") or ""

        # If we are delivering media buy delivery report
        notification_type_from_result = result.get("notification_type") if result is not None else None
        sequence_number_from_result = result.get("sequence_number") if result is not None else None
        notification_type = notification_type_from_result
        sequence_number = sequence_number_from_result if isinstance(sequence_number_from_result, int) else 1

        # Create webhook delivery log entry
        log_id = str(uuid4())
        start_time = time.time()

        # Log to audit system (start)
        audit_logger = None
        if tenant_id:
            audit_logger = get_audit_logger("webhook", tenant_id)
            audit_logger.log_info(f"Sending {task_type} webhook for task {task_id} (sequence #{sequence_number})")

        # One call through the egress seam. It owns address and TLS policy, the
        # refusal to follow redirects, the retry schedule and which statuses are
        # worth another attempt — and it builds a transport pinned to THIS
        # destination, which is why no client or session may outlive the call.
        #
        # The seam's redirect refusal is what #1697 reached for with
        # ``allow_redirects=False``: httpx defaults to ``follow_redirects=False``
        # and the seam never overrides it, so a 302 toward metadata or a private
        # address cannot carry us past the validated destination.
        #
        # No ``field=``: the URL is read back out of a stored PushNotificationConfig,
        # not off a request document a buyer just sent — the buyer-actionable
        # refusal already happened at ingest (src/core/webhook_validator.py, reject_unsafe_webhook_registration_url).
        #
        # The URL is logged sanitized (scheme://host/path): a buyer's webhook URL
        # may carry credentials in userinfo or a token in the query string, and a
        # log line is the one place they would sit in cleartext (#1697).
        logger.info("Sending webhook for task %s to %s", task_id, webhook_url_for_log(url))
        try:
            result_out = await asend(
                url,
                content=wire_body,
                headers=headers,
                timeout=10.0,
                max_attempts=max_attempts,
            )
        except OutboundRequestBlocked:
            # Refused before a connection was opened: attempts=0 is the honest count.
            # It still writes a row and an audit entry — a misconfigured destination
            # that leaves no trace is indistinguishable from one nobody configured.
            logger.error(f"Webhook for task {task_id} was refused by egress policy")
            return self._record_delivery_failure(
                log_id=log_id,
                url=url,
                task_id=task_id,
                task_type=task_type,
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                sequence_number=sequence_number,
                notification_type=notification_type,
                attempts=0,
                http_status_code=None,
                error="refused by egress policy",
                payload_size_bytes=payload_size_bytes,
                start_time=start_time,
                audit_logger=audit_logger,
            )
        except OutboundDeliveryFailed as exc:
            terminal_status = terminal_client_error_status(exc)
            if terminal_status is not None:
                error = f"client error {terminal_status}, not retried"
            elif exc.last_status is not None:
                error = f"failed after {exc.attempts} attempts (last status {exc.last_status})"
            else:
                error = f"failed after {exc.attempts} attempts (no response received)"
            logger.error(f"Webhook for task {task_id} {error}")
            return self._record_delivery_failure(
                log_id=log_id,
                url=url,
                task_id=task_id,
                task_type=task_type,
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                sequence_number=sequence_number,
                notification_type=notification_type,
                attempts=exc.attempts,
                http_status_code=exc.last_status,
                error=error,
                payload_size_bytes=payload_size_bytes,
                start_time=start_time,
                audit_logger=audit_logger,
            )
        except Exception as e:
            # Deliberately kept. A lone ``except OutboundError`` would let anything
            # else escape a function contracted ``-> bool``, and the delivery
            # scheduler re-raises what it catches. The pinned transport's own
            # wrong-host guard raises a bare RuntimeError, which belongs here.
            logger.error(f"Unexpected error sending webhook for task {task_id}: {e}", exc_info=True)
            return self._record_delivery_failure(
                log_id=log_id,
                url=url,
                task_id=task_id,
                task_type=task_type,
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                sequence_number=sequence_number,
                notification_type=notification_type,
                attempts=0,
                http_status_code=None,
                error=str(e),
                payload_size_bytes=payload_size_bytes,
                start_time=start_time,
                audit_logger=audit_logger,
            )

        response_time_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Successfully sent webhook for task {task_id} (status: {result_out.status_code})")

        if task_type in ("delivery_report", "media_buy_delivery") and media_buy_id and tenant_id and principal_id:
            self._write_delivery_log(
                log_id=log_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                webhook_url=url,
                task_type=task_type,
                status="success",
                sequence_number=sequence_number,
                notification_type=notification_type,
                attempt_count=result_out.attempts,
                http_status_code=result_out.status_code,
                payload_size_bytes=payload_size_bytes,
                response_time_ms=response_time_ms,
                completed_at=datetime.now(UTC),
            )

        if audit_logger:
            audit_logger.log_success(
                f"{task_type} webhook delivered successfully (sequence #{sequence_number}, "
                f"{response_time_ms}ms, {payload_size_bytes} bytes)"
            )

        return True


# Global service instance
_webhook_service: ProtocolWebhookService | None = None


def get_protocol_webhook_service() -> ProtocolWebhookService:
    """Get or create global webhook service instance.

    The service owns no connection state, so there is nothing to close and no
    shutdown callback to register. Each delivery builds a transport pinned to its
    own destination and discards it: a pooled client shared across destinations
    would resolve once and then serve a hostname it was never validated for,
    which is the whole reason the pin exists.
    """
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = ProtocolWebhookService()
    return _webhook_service


def get_webhook_service_or_none() -> ProtocolWebhookService | None:
    """Return the current singleton instance, or None if never constructed.

    Distinct from :func:`get_protocol_webhook_service`: this does NOT trigger
    construction. Use it from shutdown hooks where you only want to close an
    *existing* instance, not create one just to inspect it.

    Resolving the singleton through this function call is location-independent:
    it reads the live module global at call time, so callers may import it at
    module top-level without the lazy-import tripwire that a direct
    ``from ... import _webhook_service`` would introduce (a hoisted private
    import binds the initial ``None`` forever).
    """
    return _webhook_service

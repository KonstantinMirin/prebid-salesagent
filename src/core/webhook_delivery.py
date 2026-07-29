"""Webhook delivery service with exponential backoff retry logic.

This module provides reliable webhook delivery with:
- Exponential backoff retry strategy (1s, 2s, 4s)
- Database tracking of delivery attempts
- Retry on 5xx errors, no retry on 4xx client errors
- SSRF protection, redirect refusal and the retry schedule: all the egress seam's
- HMAC signing support via WebhookAuthenticator
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.core.database.database_session import get_db_session
from src.core.security.outbound_http import (
    OutboundDeliveryFailed,
    OutboundRequestBlocked,
    send,
    terminal_client_error_status,
)
from src.core.webhook_authenticator import WebhookAuthenticator

logger = logging.getLogger(__name__)


@dataclass
class WebhookDelivery:
    """Configuration for webhook delivery with retry logic.

    Attributes:
        webhook_url: Target URL for webhook POST request
        payload: JSON payload to send
        headers: HTTP headers (will be modified with signature if secret provided)
        max_retries: Maximum number of retry attempts (default: 3)
        timeout: Request timeout in seconds (default: 10)
        signing_secret: Optional secret for HMAC signing
        event_type: Event type for database tracking (e.g., "creative.status_changed")
        tenant_id: Tenant ID for database tracking
        object_id: Object ID related to webhook (e.g., creative_id)
    """

    webhook_url: str
    payload: dict[str, Any]
    headers: dict[str, str]
    max_retries: int = 3
    timeout: int = 10
    signing_secret: str | None = None
    event_type: str | None = None
    tenant_id: str | None = None
    object_id: str | None = None


def deliver_webhook_with_retry(delivery: WebhookDelivery) -> tuple[bool, dict[str, Any]]:
    """Deliver webhook with exponential backoff retry and database tracking.

    Retry strategy:
    - Attempt 1: Immediate
    - Attempt 2: After 1 second (2^0)
    - Attempt 3: After 2 seconds (2^1)
    - Attempt 4: After 4 seconds (2^2)

    Retry conditions:
    - 5xx errors: Retry (server-side issues)
    - 4xx errors: Do NOT retry (client errors, invalid request)
    - Network errors: Retry (timeouts, connection failures)

    Args:
        delivery: WebhookDelivery configuration object

    Returns:
        Tuple of (success: bool, result: dict) where result contains:
        - delivery_id: Unique ID for this delivery attempt
        - status: "delivered" or "failed"
        - attempts: Number of attempts made
        - response_code: HTTP status code (if received)
        - error: Error message (if failed)
    """
    from src.core.metrics import webhook_delivery_attempts, webhook_delivery_duration, webhook_delivery_total

    # Reject delivery for paused media buys
    if delivery.payload.get("status") == "paused":
        logger.info("[Webhook Delivery] Rejected: media buy is paused")
        return False, {
            "status": "rejected",
            "error": "Media buy is paused",
            "attempts": 0,
        }

    # Generate delivery ID for tracking
    delivery_id = f"whd_{uuid.uuid4().hex[:12]}"

    # Add HMAC signature if secret provided
    headers = delivery.headers.copy()
    if delivery.signing_secret:
        signature_headers = WebhookAuthenticator.sign_payload(delivery.payload, delivery.signing_secret)
        headers.update(signature_headers)

    # Track delivery attempts
    attempts = 0
    last_error = None
    response_code = None
    start_time = time.time()

    # Create initial database record if tracking is enabled
    if delivery.tenant_id and delivery.event_type:
        _create_delivery_record(
            delivery_id=delivery_id,
            tenant_id=delivery.tenant_id,
            webhook_url=delivery.webhook_url,
            payload=delivery.payload,
            event_type=delivery.event_type,
            object_id=delivery.object_id,
        )

    # One call through the egress seam. It owns address and TLS policy, the
    # refusal to follow redirects, the retry schedule (BR-RULE-029) and which
    # statuses are worth another attempt. The redirect part is why this module is
    # the epic's centre: requests.Session.request defaults allow_redirects=True,
    # so this site used to validate a URL and then chase a 302 to wherever the
    # counterparty pointed.
    #
    # No ``field=``: the URL is read back out of a stored PushNotificationConfig,
    # not off the request document a buyer just sent. Refusing it at ingest, where
    # a response still exists to carry the error, is salesagent-w97e.
    try:
        result = send(
            delivery.webhook_url,
            json=delivery.payload,
            headers=headers,
            timeout=float(delivery.timeout),
            max_attempts=delivery.max_retries,
        )
    except OutboundRequestBlocked as exc:
        # Refused before a connection was opened. attempts=0 is the honest count:
        # nothing was sent. NOTE this bucket now also catches an UNRESOLVABLE host,
        # which previously exhausted retries and booked max_retries_exceeded.
        logger.error(f"[Webhook Delivery] REFUSED: {delivery_id} to {delivery.webhook_url}")
        return _record_failure(
            delivery,
            delivery_id,
            metric_status="validation_failed",
            attempts=0,
            response_code=None,
            error=f"Invalid webhook URL: {exc}",
            start_time=start_time,
            observe_histograms=False,
        )
    except OutboundDeliveryFailed as exc:
        terminal_status = terminal_client_error_status(exc)
        if terminal_status is not None:
            # A 4xx the seam refused to retry. 401/403 additionally block the
            # endpoint until its credentials are reconfigured.
            error = f"Client error {terminal_status}"
            logger.warning(f"[Webhook Delivery] Client error, will NOT retry: {error}")
            if terminal_status in (401, 403) and delivery.tenant_id:
                _set_auth_blocked(delivery.tenant_id, delivery.webhook_url)
            return _record_failure(
                delivery,
                delivery_id,
                metric_status="client_error",
                attempts=exc.attempts,
                response_code=terminal_status,
                error=error,
                start_time=start_time,
                observe_histograms=False,
            )

        total_duration = time.time() - start_time
        logger.error(
            f"[Webhook Delivery] FAILED: {delivery_id} failed after {exc.attempts} attempts in {total_duration:.2f}s"
        )
        return _record_failure(
            delivery,
            delivery_id,
            metric_status="max_retries_exceeded",
            attempts=exc.attempts,
            response_code=exc.last_status,
            # The seam does not distinguish a timeout from a dropped connection —
            # deliberately, so a refusal cannot become a side channel. What is still
            # true and useful to an operator is whether the endpoint ever answered:
            # last_status is None exactly when nothing came back.
            error=(
                f"Delivery failed after {exc.attempts} attempts"
                + ("" if exc.last_status is not None else " (no response received)")
            ),
            start_time=start_time,
            observe_histograms=True,
        )

    total_duration = time.time() - start_time
    logger.info(
        f"[Webhook Delivery] SUCCESS: {delivery_id} delivered in {total_duration:.2f}s after {result.attempts} attempts"
    )

    if delivery.tenant_id and delivery.event_type:
        _update_delivery_record(
            delivery_id=delivery_id,
            tenant_id=delivery.tenant_id,
            status="delivered",
            attempts=result.attempts,
            response_code=result.status_code,
            delivered_at=datetime.now(UTC),
        )
        webhook_delivery_total.labels(
            tenant_id=delivery.tenant_id, event_type=delivery.event_type, status="success"
        ).inc()
        webhook_delivery_duration.labels(event_type=delivery.event_type).observe(total_duration)
        webhook_delivery_attempts.labels(event_type=delivery.event_type).observe(result.attempts)

    return True, {
        "delivery_id": delivery_id,
        "status": "delivered",
        "attempts": result.attempts,
        "response_code": result.status_code,
        "duration": total_duration,
    }


def _record_failure(
    delivery: WebhookDelivery,
    delivery_id: str,
    *,
    metric_status: str,
    attempts: int,
    response_code: int | None,
    error: str,
    start_time: float,
    observe_histograms: bool,
) -> tuple[bool, dict[str, Any]]:
    """Record one failed delivery: the DB row, the counter, and the caller's dict.

    The three failure arms differ only in which metric status they book, what they
    know about attempts and status, and whether the duration/attempt histograms are
    observed — so they share this rather than repeating the record-and-count block
    three times with substituted variables.

    ``observe_histograms`` preserves today's asymmetry deliberately: only an
    exhausted retry budget observes them, because only it represents a full
    delivery lifetime. A refusal never reached the network and a terminal 4xx
    stopped on the first answer; folding either into the latency histogram would
    change what that metric means.

    Every arm returns the same key set — delivery_id, status, attempts,
    response_code, error — so the shape does not vary by failure mode. ``duration``
    is added only where it exists today (the exhausted-retries arm), which is the
    one arm whose callers could have been reading it.
    """
    from src.core.metrics import webhook_delivery_attempts, webhook_delivery_duration, webhook_delivery_total

    total_duration = time.time() - start_time

    if delivery.tenant_id and delivery.event_type:
        _update_delivery_record(
            delivery_id=delivery_id,
            tenant_id=delivery.tenant_id,
            status="failed",
            attempts=attempts,
            response_code=response_code,
            last_error=error,
        )
        webhook_delivery_total.labels(
            tenant_id=delivery.tenant_id, event_type=delivery.event_type, status=metric_status
        ).inc()
        if observe_histograms:
            webhook_delivery_duration.labels(event_type=delivery.event_type).observe(total_duration)
            webhook_delivery_attempts.labels(event_type=delivery.event_type).observe(attempts)

    result: dict[str, Any] = {
        "delivery_id": delivery_id,
        "status": "failed",
        "attempts": attempts,
        "response_code": response_code,
        "error": error,
    }
    if observe_histograms:
        result["duration"] = total_duration
    return False, result


def _create_delivery_record(
    delivery_id: str,
    tenant_id: str,
    webhook_url: str,
    payload: dict[str, Any],
    event_type: str,
    object_id: str | None = None,
) -> None:
    """Create initial webhook delivery record in database.

    Args:
        delivery_id: Unique delivery identifier
        tenant_id: Tenant ID
        webhook_url: Target webhook URL
        payload: JSON payload being sent
        event_type: Type of event (e.g., "creative.status_changed")
        object_id: Optional object ID related to webhook
    """
    try:
        from src.core.database.repositories.delivery import DeliveryRepository

        with get_db_session() as session:
            repo = DeliveryRepository(session, tenant_id)
            repo.create_record(
                delivery_id=delivery_id,
                webhook_url=webhook_url,
                payload=payload,
                event_type=event_type,
                object_id=object_id,
                created_at=datetime.now(UTC),
            )
            session.commit()
            logger.debug(f"[Webhook Delivery] Created delivery record: {delivery_id}")
    except Exception as e:
        # Don't fail delivery if we can't create tracking record
        logger.error(f"[Webhook Delivery] Failed to create delivery record: {e}", exc_info=True)


def _update_delivery_record(
    delivery_id: str,
    tenant_id: str,
    status: str,
    attempts: int,
    response_code: int | None = None,
    last_error: str | None = None,
    delivered_at: datetime | None = None,
) -> None:
    """Update webhook delivery record in database.

    Args:
        delivery_id: Delivery identifier
        tenant_id: Tenant ID for repository scoping
        status: Delivery status ("delivered" or "failed")
        attempts: Number of delivery attempts made
        response_code: HTTP response code (if received)
        last_error: Error message (if failed)
        delivered_at: Timestamp of successful delivery
    """
    try:
        from src.core.database.repositories.delivery import DeliveryRepository

        with get_db_session() as session:
            repo = DeliveryRepository(session, tenant_id)
            result = repo.update_record(
                delivery_id,
                status=status,
                attempts=attempts,
                response_code=response_code,
                last_error=last_error,
                last_attempt_at=datetime.now(UTC),
                delivered_at=delivered_at,
            )
            if result is not None:
                session.commit()
                logger.debug(f"[Webhook Delivery] Updated delivery record: {delivery_id} status={status}")
            else:
                logger.warning(f"[Webhook Delivery] Delivery record not found: {delivery_id}")

    except Exception as e:
        # Don't fail delivery if we can't update tracking record
        logger.error(f"[Webhook Delivery] Failed to update delivery record: {e}", exc_info=True)


def _set_auth_blocked(tenant_id: str, webhook_url: str) -> None:
    """Set auth_blocked_at on PushNotificationConfig for 401/403 auth failures.

    Blocks further delivery attempts until credentials are reconfigured.
    """
    try:
        from sqlalchemy import update

        from src.core.database.models import PushNotificationConfig

        with get_db_session() as session:
            stmt = (
                update(PushNotificationConfig)
                .where(
                    PushNotificationConfig.tenant_id == tenant_id,
                    PushNotificationConfig.url == webhook_url,
                    PushNotificationConfig.auth_blocked_at.is_(None),
                )
                .values(auth_blocked_at=datetime.now(UTC))
            )
            session.execute(stmt)
            session.commit()
            logger.warning(f"[Webhook Delivery] Auth failure blocked endpoint {webhook_url} for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"[Webhook Delivery] Failed to set auth block: {e}", exc_info=True)

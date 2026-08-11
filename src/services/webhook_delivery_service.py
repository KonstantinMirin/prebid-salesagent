"""Enhanced webhook delivery service for AdCP with security and reliability features.

This service implements the AdCP webhook specification from PR #86:
- HMAC-SHA256 signature generation with X-ADCP-Signature header
- Circuit breaker pattern (CLOSED/OPEN/HALF_OPEN states) for fault tolerance
- Exponential backoff with jitter for retry logic
- Replay attack prevention with 5-minute timestamp window
- Bounded queues (1000 webhooks per endpoint)
- Support for is_adjusted flag for late-arriving data
- Per-endpoint isolation to prevent cascading failures
"""

import atexit
import logging
import os
import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from adcp import get_adcp_spec_version

from src.core.security.outbound_http import OutboundError, OutboundRequestBlocked, terminal_client_error_status
from src.core.security.webhook_egress import (
    BasicCredentials,
    BearerToken,
    HmacSecretMissing,
    SignWithSecret,
    deliver_signed_webhook,
    webhook_auth_for,
)
from src.core.webhook_validator import webhook_url_for_log

logger = logging.getLogger(__name__)


# How long a single delivery attempt may take. Read at CALL time, not import, so a
# test can shorten it without patching a transport — which is what lets the timeout
# path be graded against an origin that really stalls, rather than against a mocked
# clock. Production's value is unchanged.
_DELIVERY_TIMEOUT_ENV = "ADCP_WEBHOOK_DELIVERY_TIMEOUT_SECONDS"
_DEFAULT_DELIVERY_TIMEOUT_SECONDS = 10.0


def _delivery_timeout_seconds() -> float:
    """Seconds a single webhook delivery attempt may take before it is abandoned."""
    raw = os.environ.get(_DELIVERY_TIMEOUT_ENV)
    if not raw:
        return _DEFAULT_DELIVERY_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not a number — using %ss", _DELIVERY_TIMEOUT_ENV, raw, _DEFAULT_DELIVERY_TIMEOUT_SECONDS
        )
        return _DEFAULT_DELIVERY_TIMEOUT_SECONDS
    if value <= 0:
        logger.warning(
            "%s=%r is not positive — using %ss", _DELIVERY_TIMEOUT_ENV, raw, _DEFAULT_DELIVERY_TIMEOUT_SECONDS
        )
        return _DEFAULT_DELIVERY_TIMEOUT_SECONDS
    return value


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Per-endpoint circuit breaker for fault isolation."""

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening circuit
            success_threshold: Consecutive successes in HALF_OPEN to close circuit
            timeout_seconds: Time to wait before moving to HALF_OPEN
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: datetime | None = None
        self._lock = threading.Lock()

    def can_attempt(self) -> bool:
        """Check if request can be attempted.

        Returns:
            True if request should be attempted, False if circuit is OPEN
        """
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if timeout has elapsed
                if (
                    self.last_failure_time
                    and (datetime.now(UTC) - self.last_failure_time).total_seconds() >= self.timeout_seconds
                ):
                    # Move to HALF_OPEN to test recovery
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info("Circuit breaker moved to HALF_OPEN (testing recovery)")
                    return True
                return False

            # HALF_OPEN state
            return True

    def record_success(self):
        """Record successful request."""
        with self._lock:
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    logger.info(f"Circuit breaker CLOSED after {self.success_count} successes")
            elif self.state == CircuitState.OPEN:
                # Shouldn't happen but handle gracefully
                self.state = CircuitState.CLOSED
                logger.info("Circuit breaker CLOSED (recovery)")

    def record_failure(self):
        """Record failed request."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now(UTC)

            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")
            elif self.state == CircuitState.HALF_OPEN:
                # Failed during recovery test - go back to OPEN
                self.state = CircuitState.OPEN
                self.failure_count = 0
                logger.warning("Circuit breaker reopened (recovery test failed)")


class WebhookQueue:
    """Bounded queue for webhook delivery per endpoint."""

    def __init__(self, max_size: int = 1000):
        """Initialize webhook queue.

        Args:
            max_size: Maximum number of webhooks in queue
        """
        self.max_size = max_size
        self.queue: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._dropped_count = 0

    def enqueue(self, webhook_data: dict[str, Any]) -> bool:
        """Add webhook to queue.

        Args:
            webhook_data: Webhook payload and metadata

        Returns:
            True if enqueued, False if queue is full
        """
        with self._lock:
            if len(self.queue) >= self.max_size:
                self._dropped_count += 1
                logger.warning(
                    f"Webhook queue full ({self.max_size}), dropping webhook (total dropped: {self._dropped_count})"
                )
                return False

            self.queue.append(webhook_data)
            return True

    def dequeue(self) -> dict[str, Any] | None:
        """Remove and return oldest webhook from queue.

        Returns:
            Webhook data or None if queue is empty
        """
        with self._lock:
            if self.queue:
                return self.queue.popleft()
            return None


class WebhookDeliveryService:
    """Webhook delivery service with enhanced security and reliability features.

    Implements AdCP webhook specification from PR #86 with HMAC-SHA256 signatures,
    circuit breakers, exponential backoff, and replay attack prevention.
    """

    def __init__(self) -> None:
        """Initialize enhanced webhook delivery service."""
        self._sequence_numbers: dict[str, int] = {}  # Track sequence per media buy
        self._lock = threading.Lock()  # Protect shared state
        self._circuit_breakers: dict[str, CircuitBreaker] = {}  # Per-endpoint circuit breakers
        self._queues: dict[str, WebhookQueue] = {}  # Per-endpoint bounded queues

        # Register graceful shutdown
        atexit.register(self._shutdown)

        logger.info("✅ WebhookDeliveryService initialized")

    def send_delivery_webhook(
        self,
        media_buy_id: str,
        tenant_id: str,
        principal_id: str,
        reporting_period_start: datetime,
        reporting_period_end: datetime,
        impressions: int,
        spend: float,
        currency: str = "USD",
        status: str = "active",
        clicks: int | None = None,
        ctr: float | None = None,
        by_package: list[dict[str, Any]] | None = None,
        is_final: bool = False,
        is_adjusted: bool = False,
        next_expected_interval_seconds: float | None = None,
    ) -> bool:
        """Send AdCP V2.3 compliant delivery webhook with enhanced security.

        Args:
            media_buy_id: Media buy identifier
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            reporting_period_start: Start of reporting period
            reporting_period_end: End of reporting period
            impressions: Impressions delivered
            spend: Spend amount
            currency: Currency code (default: USD)
            status: Media buy status
            clicks: Optional click count
            ctr: Optional CTR
            by_package: Optional package-level breakdown
            is_final: Whether this is the final webhook
            is_adjusted: Whether this replaces previous data (late arrivals)
            next_expected_interval_seconds: Seconds until next webhook

        Returns:
            True if webhook sent successfully, False otherwise
        """
        try:
            # Thread-safe sequence number increment
            with self._lock:
                self._sequence_numbers[media_buy_id] = self._sequence_numbers.get(media_buy_id, 0) + 1
                sequence_number = self._sequence_numbers[media_buy_id]

            # Determine notification type per new spec
            if is_final:
                notification_type = "final"
            elif is_adjusted:
                notification_type = "adjusted"  # New in spec
            else:
                notification_type = "scheduled"

            # Calculate next_expected_at if not final
            next_expected_at = None
            if not is_final and next_expected_interval_seconds:
                next_expected_at = (datetime.now(UTC) + timedelta(seconds=next_expected_interval_seconds)).isoformat()

            # Build AdCP compliant payload with new fields
            delivery_payload = {
                "adcp_version": get_adcp_spec_version(),
                "notification_type": notification_type,
                "is_adjusted": is_adjusted,  # New field for late data
                "sequence_number": sequence_number,
                "reporting_period": {
                    "start": reporting_period_start.isoformat(),
                    "end": reporting_period_end.isoformat(),
                },
                "currency": currency,
                "media_buy_deliveries": [
                    {
                        "media_buy_id": media_buy_id,
                        "status": status,
                        "totals": {
                            "impressions": impressions,
                            "spend": round(spend, 2),
                        },
                        "by_package": by_package or [],
                    }
                ],
            }

            # Add optional fields
            if next_expected_at:
                delivery_payload["next_expected_at"] = next_expected_at

            # Add optional metrics to totals dict
            # We know structure is valid as we just created it above
            media_buy_delivery = delivery_payload["media_buy_deliveries"][0]  # type: ignore[index]
            totals: dict[str, Any] = media_buy_delivery["totals"]
            if clicks is not None:
                totals["clicks"] = clicks
            if ctr is not None:
                totals["ctr"] = ctr

            logger.info(
                f"📤 Delivery webhook #{sequence_number} for {media_buy_id}: "
                f"{impressions:,} imps, ${spend:,.2f} "
                f"[{notification_type}{'|adjusted' if is_adjusted else ''}]"
            )

            # Send webhook with enhanced security and reliability
            success = self._send_webhook_enhanced(
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                delivery_payload=delivery_payload,
            )

            return success

        except Exception as e:
            logger.error(
                f"❌ Failed to send delivery webhook for {media_buy_id}: {e}",
                exc_info=True,
            )
            return False

    def _send_webhook_enhanced(
        self,
        tenant_id: str,
        principal_id: str,
        media_buy_id: str,
        delivery_payload: dict[str, Any],
    ) -> bool:
        """Send webhook with enhanced security and reliability features.

        Args:
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            media_buy_id: Media buy identifier
            delivery_payload: AdCP delivery payload

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get webhook configurations
            from sqlalchemy import select

            from src.core.database.database_session import get_db_session
            from src.core.database.models import PushNotificationConfig

            with get_db_session() as db:
                stmt = select(PushNotificationConfig).filter_by(
                    tenant_id=tenant_id, principal_id=principal_id, is_active=True
                )
                configs = db.scalars(stmt).all()

                if not configs:
                    logger.debug(f"⚠️ No webhooks configured for {tenant_id}/{principal_id}")
                    return False

                # Send to all configured webhooks
                sent_count = 0
                for config in configs:
                    safe_url = webhook_url_for_log(config.url)
                    # Skip auth-blocked endpoints (UC-004-EXT-G-07)
                    if isinstance(getattr(config, "auth_blocked_at", None), datetime):
                        logger.warning(
                            "⚠️ Auth blocked for %s, skipping until credentials reconfigured",
                            safe_url,
                        )
                        continue

                    endpoint_key = f"{tenant_id}:{config.url}"

                    # Get or create circuit breaker for this endpoint
                    if endpoint_key not in self._circuit_breakers:
                        self._circuit_breakers[endpoint_key] = CircuitBreaker()

                    # Get or create queue for this endpoint
                    if endpoint_key not in self._queues:
                        self._queues[endpoint_key] = WebhookQueue(max_size=1000)

                    circuit_breaker = self._circuit_breakers[endpoint_key]
                    queue = self._queues[endpoint_key]

                    # Check circuit breaker
                    if not circuit_breaker.can_attempt():
                        logger.warning(
                            "⚠️ Circuit breaker OPEN for %s, skipping webhook delivery",
                            safe_url,
                        )
                        continue

                    # No send-time address gate here: #1697 put one in front of the
                    # raw POST this path used to do, and the egress seam that POST
                    # became now owns exactly that policy — it resolves, validates
                    # and PINS the connection to the validated IP inside the same
                    # call, so there is no window between the verdict and the
                    # socket. Re-checking here would only re-resolve, which is the
                    # rebinding gap the pin closes, and #1697's refusal-records-a-
                    # failure bookkeeping survives in _deliver_with_backoff: a
                    # refused URL raises OutboundRequestBlocked, which reaches
                    # record_failure() through the OutboundError handler.
                    # (Registration-time validation, which must NOT resolve DNS,
                    # still lives in src/core/webhook_validator.py.)

                    # Add to queue (bounded)
                    webhook_data = {
                        "config": config,
                        "payload": delivery_payload,
                        "timestamp": datetime.now(UTC),
                    }

                    if not queue.enqueue(webhook_data):
                        logger.warning("⚠️ Queue full for %s, webhook dropped", safe_url)
                        continue

                    # Deliver from queue with enhanced features
                    if self._deliver_with_backoff(endpoint_key, circuit_breaker, queue):
                        sent_count += 1

                if sent_count > 0:
                    logger.debug(f"✅ Delivery webhook sent to {sent_count} endpoint(s)")
                    return True
                else:
                    logger.warning("⚠️ Failed to deliver webhook to any endpoint")
                    return False

        except Exception as e:
            logger.error(f"❌ Error in webhook delivery: {e}", exc_info=True)
            return False

    def _deliver_with_backoff(
        self,
        endpoint_key: str,
        circuit_breaker: CircuitBreaker,
        queue: WebhookQueue,
    ) -> bool:
        """Deliver webhook with exponential backoff and jitter.

        Args:
            endpoint_key: Unique endpoint identifier
            circuit_breaker: Circuit breaker for this endpoint
            queue: Webhook queue for this endpoint

        Returns:
            True if delivered successfully, False otherwise
        """
        webhook_data = queue.dequeue()
        if not webhook_data:
            return False

        config = webhook_data["config"]
        payload = webhook_data["payload"]
        safe_url = webhook_url_for_log(config.url)

        # Signing (X-ADCP-Signature / X-ADCP-Timestamp) is owned entirely by
        # deliver_signed_webhook below -- it serializes, signs and stamps the
        # timestamp as one decision, so this function never holds a signature
        # and a body serialization as two independent things to keep in sync.
        #
        # The auth DECISION above that transport is owned entirely by
        # webhook_auth_for (salesagent-47n9.24, GH #1894). This sender used to make
        # it inline and made it wrong four ways at once: it read webhook_secret (a
        # column with zero writers in src/, so the signing branch was unreachable
        # for any row a buyer can create), signed on a truthy secret rather than on
        # the scheme, silently downgraded a weak secret to an UNSIGNED delivery, and
        # compared "bearer" against an enum every writer stores as "Bearer". One
        # resolver call replaces all four, and the closed WebhookAuth set is what
        # makes "what if it is none of these" un-writable.
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AdCP-Sales-Agent/2.3 (Enhanced Webhooks)",
        }

        auth = webhook_auth_for(config.authentication_type, config.authentication_token)

        if isinstance(auth, HmacSecretMissing):
            # FAIL-CLOSED, and deliberately log-and-return rather than raise -- the
            # same shape and the same reasoning as order_approval_service's backstop
            # (src/services/order_approval_service.py). The buyer asked for a
            # signature this sender cannot produce; an unsigned POST to an endpoint
            # that will reject it is strictly worse than no POST at all, because it
            # is an unauthenticated request to a third party that no receiver can
            # attribute to us.
            #
            # The refusal a buyer can ACT on already happened at ingest
            # (media_buy_create and the A2A push-config handler both reject an
            # HMAC-SHA256 registration carrying no credentials). By the time control
            # reaches here the poller is on its own thread with no request in
            # flight, so there is no caller left to receive a raise.
            #
            # This does NOT cite "No Quiet Failures": that rule's worked example
            # bans exactly this shape, and the honest reason it is an exception is
            # written above. It records a circuit-breaker failure for the same
            # reason a refused URL does -- a destination we cannot deliver to must
            # not look healthy to the breaker.
            logger.error(
                "Webhook to %s is configured for HMAC-SHA256 but has no credentials "
                "stored -- refusing to send unsigned",
                safe_url,
            )
            circuit_breaker.record_failure()
            return False

        signing_secret = auth.secret if isinstance(auth, SignWithSecret) else None

        # No secret-strength gate. It used to live here and never once fired: it
        # tested webhook_secret, the column with no writers. Re-pointing it at
        # authentication_token would take every buyer whose credential is under 32
        # characters from "delivered" to "not delivered at all", and would make this
        # the only one of three senders that refuses a short secret -- the same
        # divergence, re-created one line lower. A length minimum is a REGISTRATION
        # policy: it belongs beside the credential-presence gate at ingest, where
        # the buyer can still act on it, and AdCP 3.1.1 mandates no minimum.
        if isinstance(auth, BearerToken):
            headers["Authorization"] = f"Bearer {auth.token}"
        elif isinstance(auth, BasicCredentials):
            headers["Authorization"] = f"Basic {auth.token}"

        # One call: the seam owns attempts, the BR-RULE-029 schedule (plus any
        # Retry-After the endpoint asks for), address and TLS policy, and which
        # statuses are worth trying again. No ``field=`` — this URL is read back
        # out of storage, not off a request document.
        #
        # The seam's redirect refusal is what #1697 reached for with
        # ``follow_redirects=False``: httpx defaults to that and the seam never
        # overrides it, so a 302 toward a private address or a metadata endpoint
        # cannot carry this delivery past the validated destination.
        #
        # Every log below names ``safe_url`` (scheme://host/path), never
        # ``config.url``: a buyer's webhook URL may carry credentials in userinfo
        # or a token in the query string, and these lines land in operator logs.
        try:
            result = deliver_signed_webhook(
                config.url,
                payload,
                secret=signing_secret,
                headers=headers,
                timeout=_delivery_timeout_seconds(),
                max_attempts=3,
            )
        except OutboundError as exc:
            # The BASE class on purpose. A refused URL and a dead one both have to
            # reach record_failure(), or a misconfigured destination stays
            # invisible to the breaker while a merely unreachable one opens it.
            terminal_status = terminal_client_error_status(exc)
            if terminal_status is not None:
                # Named at WARNING from THIS logger: the seam logs nothing on a
                # non-retryable 4xx and its records do not propagate here, so this
                # line is the only operator-visible trace of a rejected delivery.
                logger.warning(
                    "Webhook delivery to %s returned client error %s, will not retry",
                    safe_url,
                    terminal_status,
                )
            elif isinstance(exc, OutboundRequestBlocked):
                # Refused before a connection was opened -- attempts/last_status are
                # both None (nothing was attempted), so "failed after None attempts"
                # would misreport a refusal as a delivery that was tried and failed.
                logger.warning("Webhook delivery to %s was refused by egress policy", safe_url)
            else:
                # Name the status and the attempt count. The seam's own message is a
                # fixed constant by design, so interpolating only the exception tells
                # an operator nothing about WHY — a rate limit, a 5xx and a dead
                # socket would read identically.
                cause = f"status {exc.last_status}" if exc.last_status is not None else "no response"
                logger.warning(
                    "Webhook delivery to %s failed after %s attempts (%s)",
                    safe_url,
                    exc.attempts,
                    cause,
                )
            circuit_breaker.record_failure()
            return False
        except Exception as e:
            logger.error("Unexpected error delivering to %s: %s", safe_url, e, exc_info=True)
            circuit_breaker.record_failure()
            return False

        logger.debug(
            "Webhook delivered to %s (status: %s)",
            safe_url,
            result.status_code,
        )
        circuit_breaker.record_success()
        return True

    def reset_sequence(self, media_buy_id: str):
        """Reset sequence number for a media buy.

        Args:
            media_buy_id: Media buy identifier
        """
        with self._lock:
            if media_buy_id in self._sequence_numbers:
                del self._sequence_numbers[media_buy_id]

    def has_open_circuit_breaker(self, tenant_id: str) -> bool:
        """Check if any circuit breaker is OPEN for endpoints belonging to a tenant."""
        for key, cb in self._circuit_breakers.items():
            if key.startswith(f"{tenant_id}:") and cb.state == CircuitState.OPEN:
                return True
        return False

    def get_circuit_breaker_state(self, endpoint_url: str) -> tuple[CircuitState, int]:
        """Get circuit breaker state for an endpoint.

        Args:
            endpoint_url: Webhook endpoint URL

        Returns:
            Tuple of (state, failure_count)
        """
        for key in self._circuit_breakers.keys():
            if endpoint_url in key:
                circuit_breaker = self._circuit_breakers[key]
                return (circuit_breaker.state, circuit_breaker.failure_count)
        return (CircuitState.CLOSED, 0)

    def _shutdown(self):
        """Graceful shutdown handler."""
        try:
            with self._lock:
                # Clean up internal state without logging
                # (logging stream may be closed during interpreter shutdown)
                pass
        except (ValueError, OSError):
            # Logging stream may be closed during interpreter shutdown
            pass


# Global singleton instance
webhook_delivery_service = WebhookDeliveryService()

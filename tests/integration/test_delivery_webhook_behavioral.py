"""Integration behavioral tests for UC-004 webhook delivery (deliver_webhook_with_retry).

Delivery runs against a REAL local HTTP origin (``WebhookEnv``): the endpoint
answers with the status a test programmed, and the assertions read what actually
arrived — how many requests, with which headers, carrying which bytes. Only
``time.sleep`` is mocked, so the retry schedule stays observable without waiting
for it; nothing about the outbound transport is patched, which is what keeps
these tests indifferent to whether delivery is implemented with ``requests`` or
with the egress seam. DB operations for delivery record tracking are real.

Each test targets exactly one obligation ID and follows the 6 hard rules.
"""

from __future__ import annotations

import pytest

# A stall the caller's own clock gives up on. Both numbers are as small as a
# real socket allows: the timeout is what production is told to enforce, and the
# stall must outlast it by enough that a loaded CI box cannot answer in time.
_TIMEOUT_SECONDS = 1
_STALL_SECONDS = 1.5

# The cloud-metadata address: production's URL policy refuses it outright, which
# is what makes "no request left the process" provable rather than configured.
_METADATA_URL = "http://169.254.169.254/latest/meta-data/"

# ---------------------------------------------------------------------------
# UC-004-ALT-WEBHOOK-PUSH-REPORTING-01
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookDeliveryHappyPath:
    """Scheduled webhook delivery happy path — POST with signed payload.

    Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-01
    """

    def test_webhook_sends_signed_payload(self, integration_db):
        """Webhook delivery sends POST to configured URL with HMAC-signed payload.

        Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-01
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(200)

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={
                    "media_buy_id": "mb_001",
                    "impressions": 5000,
                    "spend": 250.0,
                    "notification_type": "scheduled",
                },
                signing_secret="test-secret-key",
                max_retries=1,
            )

            assert success is True
            assert result["status"] == "delivered"

            # Verify POST was called with correct URL
            # Verify the request reached the configured endpoint
            assert env.delivery_attempts == 1
            assert env.last_delivery.path == "/webhook"

            # Verify HMAC signature headers were added
            sent_headers = env.last_delivery.headers
            assert "X-Webhook-Signature" in sent_headers
            assert "X-Webhook-Timestamp" in sent_headers

            # Verify payload was sent
            sent_payload = env.last_delivery.json()
            assert sent_payload["media_buy_id"] == "mb_001"
            assert sent_payload["notification_type"] == "scheduled"


# ---------------------------------------------------------------------------
# UC-004-ALT-WEBHOOK-PUSH-REPORTING-07
# ---------------------------------------------------------------------------


class TestWebhookHmacSha256Signing:
    """Webhook payload signed with HMAC-SHA256.

    Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-07
    """

    def test_sign_payload_produces_hmac_headers(self):
        """WebhookAuthenticator.sign_payload produces HMAC-SHA256 signature headers.

        Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-07
        """
        from src.core.webhook_authenticator import WebhookAuthenticator

        payload = {"media_buy_id": "mb_001", "impressions": 5000}
        secret = "test-signing-secret"

        headers = WebhookAuthenticator.sign_payload(payload, secret)

        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")
        assert len(headers["X-Webhook-Signature"]) > len("sha256=")
        assert "X-Webhook-Timestamp" in headers
        assert headers["X-Webhook-Timestamp"].isdigit()


# ---------------------------------------------------------------------------
# UC-004-ALT-WEBHOOK-PUSH-REPORTING-08
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookBearerTokenAuth:
    """Webhook delivery with Bearer token authentication.

    Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-08
    """

    def test_bearer_token_sent_in_authorization_header(self, integration_db):
        """Bearer token is forwarded in Authorization header when set by caller.

        Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-08
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(200)

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001"},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer test-bearer-token-xyz",
                },
                max_retries=1,
            )

            assert success is True
            assert result["status"] == "delivered"

            sent_headers = env.last_delivery.headers
            assert sent_headers["Authorization"] == "Bearer test-bearer-token-xyz"


# ---------------------------------------------------------------------------
# UC-004-ALT-WEBHOOK-PUSH-REPORTING-11
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookOnlyActiveMediaBuys:
    """Only active media buys trigger webhook delivery.

    Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-11
    """

    def test_paused_media_buy_webhook_rejected(self, integration_db):
        """Webhook delivery should be rejected for paused media buys.

        Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-11
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(200)

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_paused", "status": "paused"},
                max_retries=1,
            )

            assert success is False, "Webhook should not be delivered for paused media buy"


# ---------------------------------------------------------------------------
# UC-004-ALT-WEBHOOK-PUSH-REPORTING-12
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookEndpoint2xxAcknowledgment:
    """Endpoint acknowledges with 2xx — successful delivery recorded.

    Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-12
    """

    def test_2xx_response_records_successful_delivery(self, integration_db):
        """200 OK from buyer endpoint records delivery as successful.

        Covers: UC-004-ALT-WEBHOOK-PUSH-REPORTING-12
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(200)

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001", "impressions": 5000},
                max_retries=1,
            )

            assert success is True
            assert result["status"] == "delivered"
            assert result["response_code"] == 200
            assert result["attempts"] == 1


# ---------------------------------------------------------------------------
# UC-004-EXT-G-01
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhook503RetryBackoff:
    """Tests that a 503 webhook endpoint triggers retries with exponential backoff.

    Covers: UC-004-EXT-G-01
    """

    def test_503_triggers_retries_with_exponential_backoff(self, integration_db):
        """When a webhook returns 503, the system retries with exponential backoff.

        Covers: UC-004-EXT-G-01
        """
        from unittest.mock import call

        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(503, "Service Unavailable")

            success, result = env.call_deliver(max_retries=4, timeout=10)

            assert success is False
            assert result["status"] == "failed"
            assert result["attempts"] == 4
            assert result["response_code"] == 503
            assert env.delivery_attempts == 4
            assert env.mock["sleep"].call_count == 3
            env.mock["sleep"].assert_has_calls([call(1), call(2), call(4)])

    def test_503_no_backoff_after_final_attempt(self, integration_db):
        """No sleep occurs after the last attempt — only between attempts.

        Covers: UC-004-EXT-G-01
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(503, "Service Unavailable")

            env.call_deliver(max_retries=4)

            assert env.mock["sleep"].call_count == 3
            assert env.delivery_attempts == 4

    def test_503_then_success_stops_retrying(self, integration_db):
        """If a retry succeeds, no further retries or backoff occur.

        Covers: UC-004-EXT-G-01
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_sequence([(503, "Service Unavailable"), (200, "OK")])

            success, result = env.call_deliver(max_retries=4)

            assert success is True
            assert result["status"] == "delivered"
            assert result["attempts"] == 2
            assert env.delivery_attempts == 2
            assert env.mock["sleep"].call_count == 1
            env.mock["sleep"].assert_called_once_with(1)

    @pytest.mark.xfail(
        reason="deliver_webhook_with_retry adds no randomization to its backoff. "
        "BR-RULE-029 specifies '1s, 2s, 4s + jitter'; the magnitudes are right and "
        "the jitter is missing. Graduates when the module moves onto the jittered "
        "egress seam (salesagent-4fya.6 + salesagent-4fya.11).",
        strict=True,
    )
    def test_backoff_includes_jitter(self, integration_db):
        """Backoff delays should include jitter to prevent thundering herd.

        Covers: UC-004-EXT-G-01
        """
        from tests.harness import WebhookEnv
        from tests.helpers.backoff_assertions import assert_backoff_schedule

        with WebhookEnv() as env:
            env.set_http_status(503, "Service Unavailable")

            env.call_deliver(max_retries=4)

            sleep_values = [float(c.args[0]) for c in env.mock["sleep"].call_args_list]

            # jitter=None: WebhookEnv patches no randomness source, so a jittered
            # delay would show up as a value inside the window rather than on the base.
            assert_backoff_schedule(sleep_values, jitter=None)


# ---------------------------------------------------------------------------
# UC-004-EXT-G-02
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookRetrySucceedsOnSecondAttempt:
    """Webhook endpoint fails first, succeeds on retry -> delivery recorded.

    Covers: UC-004-EXT-G-02
    """

    def test_transient_failure_then_success_records_delivered(self, integration_db):
        """Given a webhook that 503s then 200s, the delivery result is 'delivered'.

        Covers: UC-004-EXT-G-02
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_sequence([(503, "Service Unavailable"), (200, "OK")])

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001", "event": "delivery.update"},
                max_retries=3,
                timeout=10,
                event_type="delivery.update",
                tenant_id="test_tenant",
                object_id="mb_001",
            )

            assert success is True
            assert result["status"] == "delivered"
            assert result["attempts"] == 2
            assert result["response_code"] == 200
            assert env.mock["sleep"].call_count == 1


# ---------------------------------------------------------------------------
# UC-004-EXT-G-05
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhook401ForbiddenNoRetry:
    """Tests that 401 authentication errors are not retried.

    Covers: UC-004-EXT-G-05
    """

    def test_401_response_is_not_retried_and_marked_failed(self, integration_db):
        """A 401 Forbidden response must cause immediate failure with no retries.

        Covers: UC-004-EXT-G-05
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(401, "Unauthorized - invalid credentials")

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001", "event": "delivery.update"},
                max_retries=3,
                timeout=10,
                event_type="delivery.update",
                tenant_id="test_tenant",
                object_id="mb_001",
            )

            assert success is False
            assert result["status"] == "failed"
            assert result["response_code"] == 401
            assert env.delivery_attempts == 1
            assert result["attempts"] == 1
            assert "401" in result["error"]

    def test_401_vs_500_retry_behavior_contrast(self, integration_db):
        """Verify 401 does NOT retry while 500 DOES retry.

        Covers: UC-004-EXT-G-05
        """
        from tests.harness import WebhookEnv

        # --- 401 case: should stop immediately ---
        with WebhookEnv() as env:
            env.set_http_status(401, "Unauthorized")
            success_401, result_401 = env.call_deliver(max_retries=3)

            assert success_401 is False
            assert result_401["attempts"] == 1
            assert env.delivery_attempts == 1

        # --- 500 case: should retry all attempts ---
        with WebhookEnv() as env:
            env.set_http_status(500, "Internal Server Error")
            success_500, result_500 = env.call_deliver(max_retries=3)

            assert success_500 is False
            assert result_500["attempts"] == 3
            assert env.delivery_attempts == 3


# ---------------------------------------------------------------------------
# UC-004-EXT-G-06
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestEXT_G_06_HmacAuthRejection:
    """HMAC auth rejection: 401/403 logs rejection, no retry, marks failed.

    Covers: UC-004-EXT-G-06
    """

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_rejection_no_retry_marks_failed(self, integration_db, status_code):
        """401/403 from endpoint => single attempt, no retry, status=failed.

        Covers: UC-004-EXT-G-06
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(status_code, "HMAC signature mismatch")

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001", "impressions": 5000},
                signing_secret="super-secret-key-for-hmac-signing",
                max_retries=3,
                event_type="delivery.report",
                tenant_id="test_tenant",
                object_id="mb_001",
            )

            assert success is False
            assert result["status"] == "failed"
            assert result["response_code"] == status_code
            assert result["attempts"] == 1
            assert env.delivery_attempts == 1
            assert f"Client error {status_code}" in result["error"]

    def test_hmac_headers_sent_before_rejection(self, integration_db):
        """When signing_secret is provided, HMAC signature headers are added.

        Covers: UC-004-EXT-G-06
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(401, "Invalid signature")

            env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001", "event": "delivery.report"},
                signing_secret="my-webhook-secret-key",
                event_type="delivery.report",
                tenant_id="test_tenant",
                object_id="mb_001",
            )

            sent_headers = env.last_delivery.headers
            assert "X-Webhook-Signature" in sent_headers
            assert sent_headers["X-Webhook-Signature"].startswith("sha256=")
            assert "X-Webhook-Timestamp" in sent_headers

    def test_auth_rejection_vs_server_error_retry_behavior(self, integration_db):
        """Contrast: 401 does NOT retry, but 500 DOES retry.

        Covers: UC-004-EXT-G-06
        """
        from tests.harness import WebhookEnv

        # 401 case
        with WebhookEnv() as env:
            env.set_http_status(401, "Unauthorized")
            success_401, result_401 = env.call_deliver(max_retries=3, event_type="delivery.report", tenant_id="t1")
            assert success_401 is False
            assert result_401["attempts"] == 1
            assert env.delivery_attempts == 1

        # 500 case
        with WebhookEnv() as env:
            env.set_http_status(500, "Internal Server Error")
            success_500, result_500 = env.call_deliver(max_retries=3, event_type="delivery.report", tenant_id="t1")
            assert success_500 is False
            assert result_500["attempts"] == 3
            assert env.delivery_attempts == 3


# ---------------------------------------------------------------------------
# UC-004-EXT-G-08 (SSRF validation — webhook failure does not reach buyer)
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookSSRFValidation:
    """Invalid/internal webhook URLs are rejected before any HTTP request is made.

    The URLs below are refused by production's own address policy — nothing here
    configures the refusal, so what is graded is the policy and not the test's
    opinion of it. ``169.254.169.254`` really is the cloud-metadata address.

    Covers: UC-004-EXT-G-08
    """

    def test_internal_url_rejected_with_validation_error(self, integration_db):
        """Delivery to an internal/link-local URL (e.g., AWS metadata) is rejected immediately.

        Covers: UC-004-EXT-G-08 (src/core/webhook_delivery.py lines 93-99)
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            success, result = env.call_deliver(
                webhook_url=_METADATA_URL,
                payload={"media_buy_id": "mb_001"},
                max_retries=3,
                event_type="delivery.update",
                tenant_id="test_tenant",
                object_id="mb_001",
            )

            assert success is False
            assert result["status"] == "failed"
            assert "Invalid webhook URL" in result["error"]
            assert result["attempts"] == 0
            # SSRF prevented: no HTTP request was made
            assert env.delivery_attempts == 0

    def test_ssrf_validation_records_failure_metrics(self, integration_db):
        """When URL validation fails with tenant/event context, metrics are recorded.

        Covers: UC-004-EXT-G-08 (src/core/webhook_delivery.py lines 95-98)
        """
        from unittest.mock import patch

        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            with patch("src.core.metrics.webhook_delivery_total") as mock_metric:
                success, result = env.call_deliver(
                    webhook_url=_METADATA_URL,
                    payload={"media_buy_id": "mb_001"},
                    tenant_id="test_tenant",
                    event_type="delivery.update",
                )

                assert success is False
                mock_metric.labels.assert_called_once_with(
                    tenant_id="test_tenant",
                    event_type="delivery.update",
                    status="validation_failed",
                )
                mock_metric.labels.return_value.inc.assert_called_once()

    def test_ssrf_validation_skips_metrics_without_tenant(self, integration_db):
        """When no tenant_id/event_type is provided, metrics are not recorded.

        Covers: UC-004-EXT-G-08 (src/core/webhook_delivery.py line 95 -- falsy branch)
        """
        from unittest.mock import patch

        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            with patch("src.core.metrics.webhook_delivery_total") as mock_metric:
                success, result = env.call_deliver(
                    webhook_url=_METADATA_URL,
                    payload={"media_buy_id": "mb_001"},
                    tenant_id=None,
                    event_type=None,
                )

                assert success is False
                assert result["attempts"] == 0
                mock_metric.labels.assert_not_called()


# ---------------------------------------------------------------------------
# UC-004-EXT-G-01 / UC-004-EXT-G-03 (retry backoff + retry exhaustion)
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookRetryBackoff:
    """Server errors and network exceptions trigger retries with exponential backoff.

    Covers: UC-004-EXT-G-01, UC-004-EXT-G-03
    """

    def test_5xx_retry_with_eventual_success(self, integration_db):
        """503 -> 503 -> 200: delivery succeeds after retries.

        Covers: UC-004-EXT-G-01
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_sequence(
                [
                    (503, "Service Unavailable"),
                    (503, "Service Unavailable"),
                    (200, "OK"),
                ]
            )

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001"},
                max_retries=4,
                event_type="delivery.update",
                tenant_id="test_tenant",
            )

            assert success is True
            assert result["status"] == "delivered"
            assert result["attempts"] == 3
            assert result["response_code"] == 200
            assert env.delivery_attempts == 3
            # Backoff sleeps: 2^0=1, 2^1=2 (before attempts 2 and 3)
            assert env.mock["sleep"].call_count == 2

    def test_5xx_retry_exhaustion(self, integration_db):
        """Always-500 with max_retries=3: delivery fails after all attempts exhausted.

        Covers: UC-004-EXT-G-03
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.set_http_status(500, "Internal Server Error")

            success, result = env.call_deliver(
                webhook_url=env.webhook_url,
                payload={"media_buy_id": "mb_001"},
                max_retries=3,
                event_type="delivery.update",
                tenant_id="test_tenant",
            )

            assert success is False
            assert result["status"] == "failed"
            assert result["attempts"] == 3
            assert result["response_code"] == 500
            assert env.delivery_attempts == 3

    def test_timeout_triggers_retry(self, integration_db):
        """An endpoint slower than the timeout triggers retry with backoff.

        The origin really stalls past the caller's own timeout, so the Timeout
        the retry loop catches is raised by the HTTP client itself — nothing here
        chooses which exception that is.

        Covers: UC-004-EXT-G-01 (src/core/webhook_delivery.py lines 222-225)
        """
        from tests.harness import WebhookEnv
        from tests.helpers.local_http_origin import responds

        with WebhookEnv() as env:
            # Stall past the 1s timeout twice, then answer promptly.
            env.set_http_sequence(
                [
                    responds(200, delay_seconds=_STALL_SECONDS),
                    responds(200, delay_seconds=_STALL_SECONDS),
                    responds(200, body=b"OK"),
                ]
            )

            success, result = env.call_deliver(
                max_retries=4,
                timeout=_TIMEOUT_SECONDS,
                event_type="delivery.update",
                tenant_id="test_tenant",
            )

            assert success is True
            assert result["attempts"] == 3
            assert env.delivery_attempts == 3

    def test_connection_error_triggers_retry(self, integration_db):
        """An endpoint that drops the connection triggers retry with backoff.

        Covers: UC-004-EXT-G-01 (src/core/webhook_delivery.py lines 227-230)
        """
        from tests.harness import WebhookEnv
        from tests.helpers.local_http_origin import hangs_up

        with WebhookEnv() as env:
            env.set_http_sequence([hangs_up(), (200, "OK")])

            success, result = env.call_deliver(
                max_retries=3,
                event_type="delivery.update",
                tenant_id="test_tenant",
            )

            assert success is True
            assert result["attempts"] == 2
            assert env.delivery_attempts == 2

    def test_malformed_response_body_triggers_retry(self, integration_db):
        """An endpoint whose body violates its own framing triggers retry with backoff.

        This is the third distinct network failure mode, and the one the generic
        ``RequestException`` branch exists for: the headers parse, so it is not a
        connection failure, and nothing timed out — the body simply does not
        decode. Clients report it as its own exception class
        (``ChunkedEncodingError``), which a retry policy handling only
        connection failures and timeouts would let escape.

        Covers: UC-004-EXT-G-01 (src/core/webhook_delivery.py lines 232-235)
        """
        from tests.harness import WebhookEnv
        from tests.helpers.local_http_origin import sends_malformed_body

        with WebhookEnv() as env:
            env.set_http_sequence([sends_malformed_body(), (200, "OK")])

            success, result = env.call_deliver(
                max_retries=3,
                event_type="delivery.update",
                tenant_id="test_tenant",
            )

            assert success is True
            assert result["attempts"] == 2
            assert env.delivery_attempts == 2

    def test_all_retries_timeout_reports_failure(self, integration_db):
        """When all retry attempts timeout, delivery is marked failed with attempt count.

        Covers: UC-004-EXT-G-03 (src/core/webhook_delivery.py lines 222-225, 243-274)
        """
        from tests.harness import WebhookEnv

        with WebhookEnv() as env:
            env.origin.delay(_STALL_SECONDS)

            success, result = env.call_deliver(
                max_retries=3,
                timeout=_TIMEOUT_SECONDS,
                event_type="delivery.update",
                tenant_id="test_tenant",
            )

            assert success is False
            assert result["status"] == "failed"
            assert result["attempts"] == 3
            assert "timeout" in result["error"].lower()
            assert env.delivery_attempts == 3

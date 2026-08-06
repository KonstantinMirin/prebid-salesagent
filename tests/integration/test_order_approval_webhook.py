"""The approval webhook, against a real origin and the real outbound transport.

Replaces ``test_webhook_notification_sent_on_success`` and
``test_webhook_retries_on_failure`` in ``tests/unit/test_order_approval_service.py``.
Both of those substituted ``httpx.Client`` and then read the call back off the
mock, which describes the transport ``_send_approval_webhook`` happens to use
rather than what it delivers: ``call_args[1]["json"]`` is the object the caller
passed, not the bytes that crossed the socket, and a mock's ``call_count`` is
the number of times a stand-in was invoked, not the number of requests a server
actually served.

Everything here is graded off ``OrderApprovalWebhookEnv``'s local origin, so the
assertions mean the same thing before and after the egress-seam migration —
which is the point: the transport symbol changes, the delivered bytes must not.

What is deliberately NOT graded here: the retry *spacing*. BR-RULE-029's
1s/2s/4s-plus-jitter schedule is graded once, in
``tests/integration/test_outbound_http.py`` through
``tests/helpers/backoff_assertions.py``. Re-asserting a delay per call site is
exactly the duplication the seam exists to delete.

One case is RED before the migration, on purpose:
``TestTerminalStatusIsNotRetried`` requires a 404 to cost exactly one request.
Today's hand-rolled loop retries every non-2xx, so it costs three. The seam
classifies retryable as ``{429, 500, 502, 503, 504}`` and treats everything else
— every other 4xx, every 3xx — as terminal, so adopting it is what turns that
case green. That behaviour change is named in the PR, not smuggled.
"""

from __future__ import annotations

import pytest

from tests.factories import PushNotificationConfigFactory
from tests.harness.order_approval_webhook import OrderApprovalWebhookEnv
from tests.helpers import assert_signature_verifies_over_wire_body

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# The attempt budget ``_send_approval_webhook`` gives one webhook: three tries
# total, not three retries after the first. Written once here because three
# cases below assert against it and they must not drift apart.
MAX_ATTEMPTS = 3


def _bearer_config(env: OrderApprovalWebhookEnv, token: str = "test_token") -> None:
    """Store a bearer-auth ``PushNotificationConfig`` for the env's own endpoint.

    Production looks the row up by ``(tenant_id, principal_id, url, is_active)``,
    so the URL has to be the origin that is really listening — a row pointing
    anywhere else is invisible to the code under test and would make an
    "Authorization header" assertion grade nothing.
    """
    tenant, principal = env.setup_default_data()
    PushNotificationConfigFactory(
        tenant=tenant,
        principal=principal,
        url=env.webhook_url,
        authentication_type="bearer",
        authentication_token=token,
        is_active=True,
    )


class TestDeliveredPayload:
    """What the buyer's endpoint actually receives when an approval completes."""

    def test_payload_carries_the_approval_result(self, integration_db):
        """Event, media buy, status and the GAM polling outcome cross the socket.

        ``order_id`` and ``attempts`` are the two fields that only exist when the
        GAM poll produced them, so they are the ones a payload-build regression
        would drop silently — the webhook is the ONLY outward signal that an
        approval finished, and nothing downstream re-derives them.
        """
        with OrderApprovalWebhookEnv() as env:
            env.setup_default_data()
            env.set_http_status(200)

            env.call_send_approval_webhook(
                media_buy_id="mb_123",
                status="approved",
                message="Order approved successfully",
                order_id="12345",
                attempts=3,
            )

            assert env.delivery_attempts == 1
            request = env.last_delivery
            assert request.method == "POST"
            assert request.path == "/webhook"

            payload = request.json()
            assert payload["event"] == "order_approval_update"
            assert payload["media_buy_id"] == "mb_123"
            assert payload["status"] == "approved"
            assert payload["order_id"] == "12345"
            assert payload["attempts"] == 3


class TestStoredCredential:
    """The ``Authorization`` header is derived from the stored PushNotificationConfig.

    Both directions are graded: a stored bearer token must reach the wire, and
    the absence of a row must produce no ``Authorization`` header at all. The
    second half is where a stored-credential regression would hide — the deleted
    unit test covered it only incidentally, by running with no row.
    """

    def test_bearer_token_from_the_stored_config_reaches_the_wire(self, integration_db):
        """A bearer row becomes ``Authorization: Bearer <token>`` on the request."""
        with OrderApprovalWebhookEnv() as env:
            _bearer_config(env, token="test_token")
            env.set_http_status(200)

            env.call_send_approval_webhook(status="approved")

            assert env.delivery_attempts == 1
            assert env.last_delivery.headers["Authorization"] == "Bearer test_token"

    def test_no_stored_config_sends_no_authorization_header(self, integration_db):
        """With no active row the request still goes out — unauthenticated.

        Not "no request": production deliberately delivers without auth rather
        than refusing, so the assertion is on the header's absence on a request
        that provably arrived.
        """
        with OrderApprovalWebhookEnv() as env:
            env.setup_default_data()
            env.set_http_status(200)

            env.call_send_approval_webhook(status="approved")

            assert env.delivery_attempts == 1
            assert "Authorization" not in env.last_delivery.headers


class TestHmacSigning:
    """A ``HMAC-SHA256``-configured row must sign the webhook it sends.

    salesagent-47n9.15: ``_approval_webhook_headers`` has bearer/basic/token
    branches but no HMAC-SHA256 branch at all, and ``_post_approval_webhook``
    hardcodes ``secret=None`` on every call -- so a config that ASKS for
    HMAC-SHA256 signing gets silent unsigned delivery instead, with no error.
    RED until the send path reads ``PushNotificationConfig.webhook_secret``
    for this scheme and threads it into ``deliver_signed_webhook``.
    """

    def test_hmac_sha256_config_signs_the_wire_body(self, integration_db):
        """A stored HMAC-SHA256 row produces a verifiable signature over the
        exact bytes that crossed the socket -- not a re-serialization of the
        payload dict, per the wire-byte pattern salesagent-47n9.2 established.
        """
        secret = "s" * 32  # Meets the 32-char minimum every HMAC secret in this suite uses.

        with OrderApprovalWebhookEnv() as env:
            tenant, principal = env.setup_default_data()
            PushNotificationConfigFactory(
                tenant=tenant,
                principal=principal,
                url=env.webhook_url,
                authentication_type="HMAC-SHA256",
                webhook_secret=secret,
                is_active=True,
            )
            env.set_http_status(200)

            env.call_send_approval_webhook(status="approved")

            assert env.delivery_attempts == 1
            assert_signature_verifies_over_wire_body(env.last_delivery, secret)


class TestRetryClassification:
    """Which failures are worth trying again, counted on a server that really ran.

    ``origin.hits`` is the only honest grade for a retry policy: "it was retried
    twice" and "it was not retried at all" are both claims about how many
    requests reached a destination, and only a destination can count them.
    """

    def test_a_transient_status_is_retried_until_it_succeeds(self, integration_db):
        """``503, 503, 200`` costs three requests and ends delivered.

        503 rather than the deleted unit test's 500 — both are in the seam's
        retryable set, so the obligation is identical and 503 says "transient"
        without also implying the origin crashed.
        """
        with OrderApprovalWebhookEnv() as env:
            env.setup_default_data()
            env.set_http_sequence([(503, "unavailable"), (503, "unavailable"), (200, "ok")])

            env.call_send_approval_webhook(status="approved")

            assert env.delivery_attempts == MAX_ATTEMPTS

    def test_a_terminal_status_is_not_retried(self, integration_db):
        """A 404 costs exactly ONE request.

        The endpoint said the resource does not exist; posting the same body to
        the same URL twice more cannot change that answer, and doing so triples
        the load a misconfigured buyer endpoint takes from us. Retryable is
        ``{429, 500, 502, 503, 504}`` and 404 is not in it.

        RED until ``_send_approval_webhook`` adopts the egress seam: the
        hand-rolled loop it has today retries every non-2xx, so this currently
        counts three.
        """
        with OrderApprovalWebhookEnv() as env:
            env.setup_default_data()
            env.set_http_status(404, "not found")

            env.call_send_approval_webhook(status="approved")

            assert env.delivery_attempts == 1


class TestExhaustedDeliveryIsSilent:
    """A webhook that cannot be delivered must not escape into the caller."""

    def test_a_dropped_connection_exhausts_the_budget_and_raises_nothing(self, integration_db):
        """Every attempt is answered with a closed socket; the call still returns.

        ``_send_approval_webhook`` runs on the approval daemon thread, reached
        only from ``_mark_approval_complete`` / ``_mark_approval_failed``, and
        both ignore its return value. An exception escaping it would kill that
        thread after the approval had already completed — so "delivery failed"
        has to stay a log line. Reaching the assertion below at all is that
        obligation; the assertion itself pins that the failure was genuinely
        exhausted rather than abandoned after one try.

        A dropped connection rather than a failing status, so this grades the
        transport-exception path — the one the deleted unit tests never reached.
        """
        with OrderApprovalWebhookEnv() as env:
            env.setup_default_data()
            env.set_http_error()

            env.call_send_approval_webhook(status="failed", message="GAM order rejected")

            assert env.delivery_attempts == MAX_ATTEMPTS

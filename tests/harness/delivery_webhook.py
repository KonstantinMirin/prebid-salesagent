"""WebhookEnv — integration test environment for deliver_webhook_with_retry.

Real: a local HTTP origin that actually serves the delivery attempts, and
      ``get_db_session`` for delivery record tracking.
Mocked: ``time.sleep`` (so backoff is observable without waiting for it), and
      the loopback allowance described below.

Nothing about the outbound transport is patched. That is the point: the same
tests grade ``requests.post`` today and ``src.core.security.outbound_http.send``
after the migration, because both must put the same bytes on the same socket.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with WebhookEnv() as env:
            env.set_http_status(200)
            success, result = env.call_deliver(payload={"event": "delivery.update"})
            assert success is True
            assert env.delivery_attempts == 1

Available mocks via env.mock:
    "sleep"       -- time.sleep mock (the retry schedule, not a transport)
    "url_policy"  -- loopback allowance for the test origin (see below)
"""

from __future__ import annotations

from src.core.webhook_validator import WebhookURLValidator
from tests.harness._base import IntegrationEnv
from tests.harness._mixins import WebhookMixin


def _allow_the_local_test_origin(url: str) -> tuple[bool, str]:
    """Run production's REAL URL policy, with loopback allowed.

    ``check_url_ssrf`` refuses loopback, and the test origin can only listen on
    loopback — so something has to say "this one address is fine". Production
    already owns that statement (``validate_for_testing(allow_localhost=True)``),
    so the harness delegates to it rather than stubbing the answer: every other
    URL is still judged by the real validator, which is what lets a test prove a
    cloud-metadata address is genuinely refused instead of asserting against a
    refusal the test itself configured.

    It is the in-repo twin of ``ADCP_OUTBOUND_ALLOW_PRIVATE=true`` (which
    ``LocalOriginMixin`` also sets); when delivery moves onto the egress seam the
    env flag is the only one left and this patch is deleted outright.
    """
    return WebhookURLValidator.validate_for_testing(url, allow_localhost=True)


class WebhookEnv(WebhookMixin, IntegrationEnv):
    """Integration test environment for deliver_webhook_with_retry.

    Delivery goes over real HTTP to a real local origin; DB operations for
    delivery tracking go through the real database.

    Fluent API (from WebhookMixin / LocalOriginMixin):
        webhook_url                       -- the running origin's URL
        set_http_status(code, text)       -- answer every attempt with one status
        set_http_sequence(responses)      -- answer attempts in order, last repeats
        set_http_error()                  -- drop the connection without answering
        call_deliver(...)                 -- call deliver_webhook_with_retry
        delivery_attempts / last_delivery -- what the endpoint actually received
    """

    MODULE = "src.core.webhook_delivery"

    EXTERNAL_PATCHES = {
        "sleep": "src.core.webhook_delivery.time.sleep",
        "url_policy": "src.core.webhook_delivery.WebhookURLValidator.validate_webhook_url",
    }

    def _configure_mocks(self) -> None:
        self.mock["url_policy"].side_effect = _allow_the_local_test_origin

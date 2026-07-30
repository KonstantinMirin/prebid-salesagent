"""Meta-tests for CircuitBreakerEnv (unit variant) — verifies the harness contract.

These tests ensure the unit harness itself works correctly. They run in ``make quality``
but have no ``Covers:`` tags — they test infrastructure, not obligations.
"""

from __future__ import annotations

from src.services.webhook_delivery_service import CircuitState, WebhookDeliveryService
from tests.harness.delivery_circuit_breaker_unit import CircuitBreakerEnv


class TestCircuitBreakerEnvContract:
    """Contract tests for CircuitBreakerEnv (unit variant)."""

    def test_service_instantiation(self):
        """get_service returns a WebhookDeliveryService instance."""
        with CircuitBreakerEnv() as env:
            service = env.get_service()
            assert isinstance(service, WebhookDeliveryService)

    def test_breaker_state_transitions(self):
        """get_breaker returns a CircuitBreaker that transitions correctly."""
        with CircuitBreakerEnv() as env:
            breaker = env.get_breaker(failure_threshold=3)

            assert breaker.state == CircuitState.CLOSED
            assert breaker.can_attempt() is True

            for _ in range(3):
                breaker.record_failure()

            assert breaker.state == CircuitState.OPEN
            assert breaker.can_attempt() is False

    def test_configured_endpoint_receives_the_delivery(self):
        """The service delivers to the real local origin the config points at."""
        from datetime import UTC, datetime

        with CircuitBreakerEnv() as env:
            env.set_http_response(200)
            config = env.make_webhook_config()
            env.set_db_webhooks([config])

            service = env.get_service()
            assert isinstance(service, WebhookDeliveryService)

            delivered = service.send_delivery_webhook(
                media_buy_id="mb_001",
                tenant_id=env._tenant_id,
                principal_id=env._principal_id,
                reporting_period_start=datetime(2025, 1, 1, tzinfo=UTC),
                reporting_period_end=datetime(2025, 1, 31, tzinfo=UTC),
                impressions=1000,
                spend=50.0,
            )

            assert delivered is True
            assert env.delivery_attempts == 1
            assert env.last_delivery.json()["media_buy_deliveries"][0]["media_buy_id"] == "mb_001"

    def test_mock_access(self):
        """env.mock[name] provides access to all patch targets — timing only, no transport.

        ``ssrf`` is the send-time SSRF gate (#1697) — a *decision* production consults
        before anything leaves, not a transport mock; delivery itself still goes to the
        real local origin.
        """
        with CircuitBreakerEnv() as env:
            assert set(env.mock) == {"sleep", "random", "db", "logger", "ssrf"}

    def test_make_webhook_config(self):
        """make_webhook_config creates a mock with expected attributes."""
        with CircuitBreakerEnv() as env:
            config = env.make_webhook_config(
                auth_type="bearer",
                auth_token="tok123",
                secret="s3cret",
            )
            assert config.url == env.webhook_url
            assert config.authentication_type == "bearer"
            assert config.authentication_token == "tok123"
            assert config.webhook_secret == "s3cret"

    def test_get_breaker_accepts_kwargs(self):
        """get_breaker passes keyword args to CircuitBreaker constructor."""
        with CircuitBreakerEnv() as env:
            breaker = env.get_breaker(
                failure_threshold=10,
                success_threshold=5,
                timeout_seconds=120,
            )
            assert breaker.failure_threshold == 10
            assert breaker.success_threshold == 5
            assert breaker.timeout_seconds == 120

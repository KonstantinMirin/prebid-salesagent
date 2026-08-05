"""Webhook signature verification reference for AdCP webhook receivers.

Delegates entirely to ``adcp.webhook_receiver.verify_webhook_hmac`` (the
installed ``adcp==6.6.0`` SDK), which verifies the HMAC over the RAW body
bytes as received — never a re-serialization of a parsed payload. Per AdCP
3.1.1 (``dist/docs/3.1.1/building/by-layer/L3/webhooks.mdx:404-418``):
"Verifiers MUST use the raw HTTP body bytes as received on the wire,
captured before any JSON parse or re-serialize." A verifier that
re-serializes a parsed dict (this module's own prior implementation)
recreates, on the receive side, the exact signed-bytes-vs-wire-bytes
divergence salesagent-47n9.1 fixes on the send side — and masks it, because
a re-serializing verifier and a re-serializing signer can agree with each
other while both disagree with the real wire.
"""

import time
from collections.abc import Mapping

from adcp.signing.webhook_hmac import (
    LegacyWebhookHmacError,
    LegacyWebhookHmacOptions,
    verify_webhook_hmac,
)


class WebhookVerificationError(Exception):
    """Raised when webhook verification fails."""

    pass


class WebhookVerifier:
    """Verifies AdCP webhook signatures and timestamps over the raw received body."""

    def __init__(self, webhook_secret: str, replay_window_seconds: int = 300):
        """Initialize webhook verifier.

        Args:
            webhook_secret: Shared secret for HMAC verification (min 32 chars)
            replay_window_seconds: Maximum age of webhook in seconds (default: 300 = 5 minutes)
        """
        if len(webhook_secret) < 32:
            raise ValueError("Webhook secret must be at least 32 characters for security")

        self.webhook_secret = webhook_secret
        self.replay_window_seconds = replay_window_seconds

    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """Verify a webhook's ``X-AdCP-Signature``/``X-AdCP-Timestamp`` over ``body``.

        Args:
            body: The RAW HTTP request body bytes, exactly as received on the
                wire — never a re-serialization of a parsed payload.
            headers: HTTP request headers (case-insensitive; any Mapping).

        Returns:
            True if webhook is valid

        Raises:
            WebhookVerificationError: If verification fails
        """
        try:
            verify_webhook_hmac(
                headers=headers,
                body=body,
                options=LegacyWebhookHmacOptions(
                    secret=self.webhook_secret.encode("utf-8"),
                    sender_identity="webhook_verifier",
                    now=time.time(),
                    window_seconds=self.replay_window_seconds,
                ),
            )
        except LegacyWebhookHmacError as exc:
            raise WebhookVerificationError(str(exc)) from exc
        return True


def verify_adcp_webhook(
    webhook_secret: str,
    body: bytes,
    request_headers: Mapping[str, str],
    replay_window_seconds: int = 300,
) -> bool:
    """Convenience function to verify an AdCP webhook in one call.

    Args:
        webhook_secret: Shared secret for HMAC verification
        body: The RAW HTTP request body bytes, exactly as received on the
            wire — read them BEFORE any JSON parse, e.g. ``request.get_data()``
            in Flask or ``await request.body()`` in Starlette, never
            ``request.json()`` (which discards the exact bytes a signature
            was computed over).
        request_headers: HTTP request headers
        replay_window_seconds: Maximum age of webhook (default: 300s = 5 min)

    Returns:
        True if webhook is valid

    Raises:
        WebhookVerificationError: If verification fails

    Example:
        try:
            verify_adcp_webhook(
                webhook_secret=os.environ["WEBHOOK_SECRET"],
                body=request.get_data(),
                request_headers=dict(request.headers)
            )
            # Process webhook -- parse request.get_data() again for the payload,
            # now that the signature over those exact bytes has been verified.
        except WebhookVerificationError as e:
            # Reject webhook
            return {"error": str(e)}, 401
    """
    verifier = WebhookVerifier(webhook_secret, replay_window_seconds)
    return verifier.verify_webhook(body, request_headers)

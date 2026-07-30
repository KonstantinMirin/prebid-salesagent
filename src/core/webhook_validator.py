"""Webhook URL validation to prevent SSRF attacks.

This module provides security validation for webhook URLs to prevent
Server-Side Request Forgery (SSRF) attacks where malicious users could
trick the server into making requests to internal services.

Relationship to ``src/core/security/outbound_http.py``: that module is the seam
every outbound *request* goes through, and it delegates address policy and
resolve-once IP pinning to the adcp SDK. It cannot serve the two gates below,
because both of its pre-connection entry points (``send``/``asend`` and
``validate_url``) go through ``adcp.signing.resolve_and_validate_host``, which
ALWAYS resolves DNS. Registration is deliberately a no-DNS verdict — an
unresolvable but public hostname must be accepted at registration and re-checked
with DNS at send time — so the two-gate split here
(``validate_webhook_url_registration`` vs ``validate_outbound_webhook_url``) is
load-bearing and stays until the seam grows a no-DNS mode. New outbound *sends*
should still route through the seam rather than growing another copy of address
policy here.

The one thing the two gates here MUST NOT decide for themselves is the scheme.
That decision belongs to the seam (``_require_tls``), and this module reads the
seam's own flag to make it — see :meth:`WebhookURLValidator._require_https`. An
ingest gate that admitted a scheme the seam refuses would accept a buyer's
webhook URL with a success envelope and then never deliver to it, which is the
one failure mode the buyer cannot see or correct.

``validate_webhook_task_type`` below is an unrelated concern (SDK payload enum
coercion) that happens to live in this file.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from adcp.types import ContextObject, TaskType

from src.core.config import is_production
from src.core.exceptions import AdCPValidationError

# The scheme decision is the SEAM's, not ours: importing its env-var name and
# its truthiness helper (rather than restating either) is what makes ingest and
# send unable to drift. Private names on purpose — this module is the seam's
# ingest-side twin, not a third party reaching into it. There is no import
# cycle: outbound_http imports only httpx, adcp.signing and src.core.exceptions.
from src.core.security.outbound_http import _ALLOW_INSECURE_ENV, _env_flag
from src.core.security.url_validator import check_url_ssrf

# Fallback used when an action label is not a member of the SDK's closed
# TaskType enum. create_mcp_webhook_payload() restricts task_type to that
# enum and would otherwise reject the payload as schema-invalid.
WEBHOOK_TASK_TYPE_FALLBACK = "update_media_buy"

WEBHOOK_SSRF_SUGGESTION = (
    "Provide a public https webhook URL that does not target private, loopback, "
    "link-local, CGNAT, multicast, or cloud-metadata hosts."
)
WEBHOOK_SSRF_SUGGESTION_DEV = (
    "Provide a public http(s) webhook URL that does not target private, loopback, "
    "link-local, CGNAT, multicast, or cloud-metadata hosts."
)

# Log fallback when sanitize_webhook_url_for_log cannot parse scheme/host —
# never fall back to the raw buyer URL (credentials / query).
UNPARSEABLE_WEBHOOK_URL_FOR_LOG = "<unparseable-url>"


def _adcp_testing() -> bool:
    """True when ADCP_TESTING allows localhost/HTTP for capture servers."""
    return os.environ.get("ADCP_TESTING") == "true"


def _strict_mode() -> bool:
    """Production SSRF posture: no testing localhost bypass.

    Kept for the buyer-facing suggestion wording only. It no longer decides the
    scheme — that moved onto the seam's hatch
    (:meth:`WebhookURLValidator._require_https`) — so the dev wording can
    currently say "http(s)" in a non-production process whose hatch is closed
    and therefore rejects http. Reconciling the wording means also updating
    ``tests/unit/test_protocol_webhook_ssrf.py``, which pins
    ``WEBHOOK_SSRF_SUGGESTION_DEV`` for that case.
    """
    return is_production() and not _adcp_testing()


def validate_webhook_task_type(task_type: str, fallback: str = WEBHOOK_TASK_TYPE_FALLBACK) -> str:
    """Coerce a task_type to a value accepted by the SDK webhook payload builder.

    ``create_mcp_webhook_payload()`` validates ``task_type`` against the closed
    :class:`adcp.types.TaskType` enum. Action labels sourced from untrusted data
    (e.g. ``workflow_steps.tool_name``) may not be enum members, which would make
    the payload schema-invalid. This helper returns ``task_type`` unchanged when
    it is a valid enum value, otherwise returns ``fallback``.

    This validates ONLY the value destined for the SDK/webhook payload. Callers
    must keep the original action label for internal metadata (audit log,
    delivery-webhook guards, ``WebhookDeliveryLog.task_type``) — see
    salesagent-yi3s.

    Args:
        task_type: The candidate action label.
        fallback: The value to return when ``task_type`` is not a TaskType member.

    Returns:
        ``task_type`` if it is a valid TaskType, otherwise ``fallback``.
    """
    try:
        TaskType(task_type)
    except ValueError:
        return fallback
    return task_type


def webhook_ssrf_suggestion() -> str:
    """Buyer-facing suggestion for registration/outbound SSRF rejections."""
    if _strict_mode():
        return WEBHOOK_SSRF_SUGGESTION
    return WEBHOOK_SSRF_SUGGESTION_DEV


def sanitize_webhook_url_for_log(url: str | None) -> str | None:
    """Return ``scheme://host/path`` for logs — never credentials or query."""
    if not url:
        return None
    parsed = urlparse(str(url))
    if parsed.scheme and parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname}{parsed.path or ''}"
    return None


def webhook_url_for_log(url: str | None) -> str:
    """Total log helper: sanitized URL or the unparseable placeholder (never raw)."""
    return sanitize_webhook_url_for_log(url) or UNPARSEABLE_WEBHOOK_URL_FOR_LOG


def reject_unsafe_webhook_registration_url(
    url: str | None,
    *,
    field: str,
    context: ContextObject | dict[str, Any] | None = None,
) -> None:
    """Raise AdCPValidationError when ``url`` fails the registration SSRF gate.

    Blank / whitespace-only / ``None`` URLs are a no-op (not a rejection) so
    callers can extract-then-call unconditionally.
    """
    if url is None or not str(url).strip():
        return
    is_valid, error_msg = WebhookURLValidator.validate_webhook_url_registration(str(url))
    if not is_valid:
        raise AdCPValidationError(
            f"Invalid {field}: {error_msg}",
            field=field,
            suggestion=webhook_ssrf_suggestion(),
            recovery="correctable",
            context=context,
        )


def reject_unsafe_outbound_webhook_url(
    url: str,
    *,
    log: logging.Logger,
    kind: str,
) -> tuple[bool, str]:
    """Send-time SSRF gate with standardized error logging.

    Returns ``(rejected, error_msg)``. On rejection, logs once with a shared
    message shape so protocol and application delivery paths cannot drift.
    Callers that maintain a circuit breaker should record failure locally.
    """
    is_valid, error_msg = WebhookURLValidator.validate_outbound_webhook_url(url)
    if is_valid:
        return False, ""
    log.error(
        "%s webhook URL failed SSRF validation (url=%s): %s",
        kind,
        webhook_url_for_log(url),
        error_msg,
    )
    return True, error_msg


class WebhookURLValidator:
    """Validates webhook URLs to prevent SSRF attacks."""

    @staticmethod
    def _maybe_allow_localhost(is_valid: bool, error: str, *, allow_localhost: bool) -> tuple[bool, str]:
        """Override localhost/loopback SSRF failures when testing allows them."""
        if not is_valid and allow_localhost:
            if "localhost" in error.lower() or "127.0.0" in error or "loopback" in error.lower():
                return True, ""
        return is_valid, error

    @staticmethod
    def _require_https() -> bool:
        """HTTPS is required unless the outbound INSECURE hatch is open.

        Keyed on exactly the condition the send seam uses
        (``src/core/security/outbound_http.py`` ``_require_tls``: https, or the
        ``ADCP_OUTBOUND_ALLOW_INSECURE`` hatch), so the two gates cannot drift.
        They used to: ingest required https only in production, so every
        non-production and ADCP_TESTING process ACCEPTED a buyer's ``http://``
        webhook URL at registration and the seam then refused it at every send —
        a silent, permanent non-delivery the buyer was never told about, at the
        one moment they could still fix the URL.

        This is the SCHEME decision only. The localhost/loopback allowance under
        ``ADCP_TESTING`` is a separate concern and still keys off
        :func:`_adcp_testing` (see ``_maybe_allow_localhost``): a capture server
        on loopback still needs the hatch open to be reachable over plain http,
        exactly as the seam requires.

        Must stay in sync with ``outbound_http._require_tls``.
        """
        return not _env_flag(_ALLOW_INSECURE_ENV)

    @classmethod
    def validate_webhook_url(cls, url: str) -> tuple[bool, str]:
        """
        Validate webhook URL for SSRF protection.

        Args:
            url: The webhook URL to validate

        Returns:
            (is_valid, error_message) - is_valid is True if safe, error_message explains failures
        """
        return check_url_ssrf(url, require_https=cls._require_https())

    @classmethod
    def validate_webhook_url_registration(cls, url: str) -> tuple[bool, str]:
        """Registration-time SSRF gate (no DNS required).

        Blocks known-bad hostnames and literal private IPs. Unresolvable
        public hostnames are allowed here; send-time re-checks with DNS
        (``validate_outbound_webhook_url``). When ``ADCP_TESTING=true``,
        localhost/loopback are allowed for capture servers. HTTPS is required
        unless the seam's insecure hatch is open (:meth:`_require_https`).
        """
        allow_localhost = _adcp_testing()
        is_valid, error = check_url_ssrf(
            url,
            resolve_dns=False,
            require_https=cls._require_https(),
        )
        return cls._maybe_allow_localhost(is_valid, error, allow_localhost=allow_localhost)

    @classmethod
    def validate_outbound_webhook_url(cls, url: str) -> tuple[bool, str]:
        """Send-time SSRF gate (full DNS), with localhost allowance under ADCP_TESTING."""
        if _adcp_testing():
            return cls.validate_for_testing(url, allow_localhost=True)
        return cls.validate_webhook_url(url)

    @classmethod
    def validate_for_testing(cls, url: str, allow_localhost: bool = False) -> tuple[bool, str]:
        """
        Validate webhook URL with optional localhost allowance for testing.

        This is useful for development/testing scenarios where webhooks need to
        point to localhost services. Production should use validate_webhook_url().

        Args:
            url: The webhook URL to validate
            allow_localhost: If True, allows localhost and 127.0.0.1

        Returns:
            (is_valid, error_message)
        """
        # Testing path always allows HTTP (capture servers, local harnesses).
        is_valid, error = check_url_ssrf(url, require_https=False)
        return cls._maybe_allow_localhost(is_valid, error, allow_localhost=allow_localhost)

"""Webhook URL validation to prevent SSRF attacks.

This module provides security validation for webhook URLs to prevent
Server-Side Request Forgery (SSRF) attacks where malicious users could
trick the server into making requests to internal services.

Relationship to ``src/core/security/outbound_http.py``: that module is the seam
every outbound *request* goes through, and it owns SEND-time policy outright —
address, TLS, redirect and retry, delegated to the adcp SDK. This module keeps
exactly ONE gate, and only because the seam cannot yet express it: registration.

Both of the seam's pre-connection entry points (``send``/``asend`` and
``validate_url``) go through ``adcp.signing.resolve_and_validate_host``, which
ALWAYS resolves DNS. Registration is deliberately a no-DNS verdict — an
unresolvable but public hostname must be ACCEPTED at registration and re-checked
with DNS when the callback is actually dialled — so
``validate_webhook_url_registration`` stays until the seam grows a no-DNS mode
(gh-#1589), at which point it and ``src/core/security/url_validator.py`` go too.

There is no send-side gate here any more. There used to be
(``validate_outbound_webhook_url`` and friends); it had no production callers and
survived only as a patch target that made test controls look live while
intercepting nothing, so it was deleted. Any new outbound send goes through the
seam — never a second copy of address policy here.

The one thing this gate MUST NOT decide for itself is the scheme. That decision
belongs to the seam (``_require_tls``), which requires https unconditionally
(salesagent-e6h0 deleted its escape hatch) — see
:meth:`WebhookURLValidator._require_https`, which does the same. An ingest gate
that admitted a scheme the seam refuses would accept a buyer's webhook URL with
a success envelope and then never deliver to it, which is the one failure mode
the buyer cannot see or correct.

``validate_webhook_task_type`` below is an unrelated concern (SDK payload enum
coercion) that happens to live in this file.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Any
from urllib.parse import urlparse

from adcp.types import ContextObject, TaskType

from src.core.exceptions import AdCPValidationError

# ``_scheme_error`` is imported (not restated): ``_maybe_allow_localhost`` must
# recognise a scheme refusal without re-implementing the scheme rule, or the
# two copies can drift.
from src.core.security.url_validator import _scheme_error, check_url_ssrf

# Fallback used when an action label is not a member of the SDK's closed
# TaskType enum. create_mcp_webhook_payload() restricts task_type to that
# enum and would otherwise reject the payload as schema-invalid.
WEBHOOK_TASK_TYPE_FALLBACK = "update_media_buy"

WEBHOOK_SSRF_SUGGESTION = (
    "Provide a public https webhook URL that does not target private, loopback, "
    "link-local, CGNAT, multicast, or cloud-metadata hosts."
)

# Log fallback when sanitize_webhook_url_for_log cannot parse scheme/host —
# never fall back to the raw buyer URL (credentials / query).
UNPARSEABLE_WEBHOOK_URL_FOR_LOG = "<unparseable-url>"


def _adcp_testing() -> bool:
    """True when ADCP_TESTING allows localhost/HTTP for capture servers."""
    return os.environ.get("ADCP_TESTING") == "true"


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
    """Buyer-facing suggestion for registration/outbound SSRF rejections.

    Always the strict https wording (salesagent-e6h0): there is no posture
    left in which a plain-http webhook URL is ever admissible, so there is no
    second wording to select between. It used to key on
    :meth:`WebhookURLValidator._require_https`, which selected between this and
    a now-deleted "http(s)" wording depending on the (now also deleted)
    outbound scheme hatch.
    """
    return WEBHOOK_SSRF_SUGGESTION


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


class WebhookURLValidator:
    """Validates webhook URLs to prevent SSRF attacks."""

    @staticmethod
    def _maybe_allow_localhost(url: str, is_valid: bool, error: str, *, allow_localhost: bool) -> tuple[bool, str]:
        """Override a loopback-ADDRESS refusal when ADCP_TESTING allows it.

        Re-derives loopback-ness structurally from *url* rather than sniffing
        the refusal message: the address-cause message is now one fixed
        non-disclosing string for every blocked range
        (``url_validator._RESTRICTED_RANGE_MESSAGE``), so it no longer carries
        "which range matched" for a substring check to key on.

        Must NOT rescue a SCHEME refusal — ``_scheme_error`` is checked first
        and unconditionally blocks the rescue when it fires, which is what
        ``test_adcp_testing_localhost_allowance_does_not_reopen_plain_http``
        pins: a loopback capture server must be reached over a REAL https URL
        now (salesagent-e6h0 deleted the scheme hatch entirely — there is no
        posture in which plain http is ever rescued).
        """
        if is_valid or not allow_localhost:
            return is_valid, error
        parsed = urlparse(url)
        if _scheme_error(parsed, require_https=WebhookURLValidator._require_https()):
            return is_valid, error
        hostname = parsed.hostname
        if hostname is None:
            return is_valid, error
        if hostname.lower() == "localhost":
            return True, ""
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return is_valid, error
        return (True, "") if is_loopback else (is_valid, error)

    @staticmethod
    def _require_https() -> bool:
        """HTTPS is required, unconditionally — no escape hatch (salesagent-e6h0).

        Kept as a method (not inlined at the 3 call sites — this one,
        ``_maybe_allow_localhost``, and ``webhook_ssrf_suggestion``) so a
        future second ingest gate has one place to ask, matching the send
        seam's own unconditional rule
        (``src/core/security/outbound_http.py`` ``_require_tls``). Ingest used
        to require https only in production, so every non-production and
        ADCP_TESTING process ACCEPTED a buyer's ``http://`` webhook URL at
        registration and the seam then refused it at every send — a silent,
        permanent non-delivery the buyer was never told about, at the one
        moment they could still fix the URL.

        This is the SCHEME decision only. The localhost/loopback allowance
        under ``ADCP_TESTING`` is a separate concern and still keys off
        :func:`_adcp_testing` (see ``_maybe_allow_localhost``): a capture
        server on loopback must be reached over a real https URL now, exactly
        as the seam requires.

        Must stay in sync with ``outbound_http._require_tls``.
        """
        return True

    @classmethod
    def validate_webhook_url_registration(cls, url: str) -> tuple[bool, str]:
        """Registration-time SSRF gate (no DNS required).

        Blocks known-bad hostnames and literal private IPs. Unresolvable
        public hostnames are allowed here; the SEAM re-checks with DNS when the
        callback is dialled (``src.core.security.outbound_http.send``). When
        ``ADCP_TESTING=true``, localhost/loopback are allowed for capture
        servers — graded on both arms in
        ``tests/unit/test_webhook_security.py::TestLocalhostAllowanceUnderTestingMode``.
        HTTPS is required unless the seam's insecure hatch is open
        (:meth:`_require_https`).
        """
        allow_localhost = _adcp_testing()
        is_valid, error = check_url_ssrf(
            url,
            resolve_dns=False,
            require_https=cls._require_https(),
        )
        return cls._maybe_allow_localhost(url, is_valid, error, allow_localhost=allow_localhost)

"""The one place a webhook payload becomes signed bytes and those bytes go out.

Core Invariant (salesagent-47n9.1): a webhook sender must never hold a signer
and a body serializer as two independent decisions. One function serializes
the body once, optionally signs those exact bytes, and transmits those exact
bytes via ``content=`` through :mod:`src.core.security.outbound_http`. No
webhook sender may reach ``json=`` on the egress seam.

Spec grounding: pinned AdCP 3.1.1,
``dist/docs/3.1.0/building/by-layer/L3/webhooks.mdx:404-418`` — the legacy
HMAC-SHA256 fallback signs ``{unix_timestamp}.{raw_body_bytes}`` and requires
``X-ADCP-Signature: sha256=<hex digest>`` / ``X-ADCP-Timestamp: <unix
seconds>`` on compact-separator JSON. ``adcp.sign_legacy_webhook`` (the
installed ``adcp==6.6.0`` SDK) implements exactly this and is a cross-check
confirming the spec reading, not the authority.

Placed beside :mod:`outbound_http` rather than in ``src/services/``: this is
egress policy (what bytes represent a payload, and how those bytes are
authenticated), not business logic.

Signer-side duplicate-object-key MUST (salesagent-47n9.19; pinned AdCP 3.1.1,
``dist/docs/3.1.0/building/by-layer/L1/security.mdx`` §Duplicate object keys):
signers MUST reject duplicate-key input before signing. ``prepare_signed_request``
takes ``payload: dict[str, Any]`` — a Python ``dict`` cannot represent a
duplicate key, so this MUST is satisfied *by construction*: there is no
production path in this codebase that feeds this function parsed-from-text
JSON (every payload source is already a dict — ``_to_wire_dict`` and
JSONB-sourced rows). Do NOT add a ``bytes``/``str``-accepting overload "for
convenience" — it would have no caller today, and it would reopen exactly the
gap this paragraph closes. ``tests/unit/test_architecture_no_webhook_egress_text_payload.py``
guards this as a build failure, not just a paragraph: if a future PR needs a
text-accepting entry point, it MUST route the text through
:func:`src.core.security.webhook_strict_json.loads_rejecting_duplicate_keys`
first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from adcp import sign_legacy_webhook

from src.core.security.outbound_http import OutboundResult, asend, send


@dataclass(frozen=True, slots=True)
class SignWithSecret:
    """Sign the body with ``secret`` (AdCP ``HMAC-SHA256``)."""

    secret: str


@dataclass(frozen=True, slots=True)
class BearerToken:
    """Send ``Authorization: Bearer <token>``. Header credential, no signature."""

    token: str


@dataclass(frozen=True, slots=True)
class BasicCredentials:
    """Send ``Authorization: Basic <token>``.

    Not an AdCP scheme. Preserved because ``order_approval_service`` honours it
    today and the A2A push-config endpoint stores a free-form protobuf string,
    so a stored ``basic`` row is one a real buyer can have created. Dropping it
    while unifying would silently stop sending a header those buyers rely on.
    """

    token: str


@dataclass(frozen=True, slots=True)
class Unauthenticated:
    """Deliver plain. The buyer selected no scheme, so there is nothing to apply."""


@dataclass(frozen=True, slots=True)
class HmacSecretMissing:
    """``HMAC-SHA256`` was requested but no credential is stored.

    Deliberately NOT :class:`Unauthenticated`: that one means "send it plain",
    this one means "the buyer asked for a signature this sender cannot produce".
    Collapsing the two into a single ``None`` is what let a sender deliver
    unsigned to a receiver that will reject it, with no error anywhere.
    """


WebhookAuth = SignWithSecret | BearerToken | BasicCredentials | Unauthenticated | HmacSecretMissing

_HMAC_SCHEME = "hmac-sha256"
_BEARER_SCHEME = "bearer"
_BASIC_SCHEME = "basic"


def webhook_auth_for(scheme: str | None, credentials: str | None) -> WebhookAuth:
    """Turn a stored ``(authentication_type, authentication_token)`` pair into ONE decision.

    Three senders used to answer this question inline and gave three different
    answers — differing in both the FIELD they read and the VALUE spelling they
    compared — so a buyer's HMAC row signed on one path, silently delivered
    unsigned on another, and never matched at all on a third.

    Takes PRIMITIVES, not a ``PushNotificationConfig``: this package holds no
    edge into ``src.core.database.models`` and must not grow one, and three call
    sites build detached/transient configs that a model-shaped resolver would
    serve only by accident.

    Comparison is CASE-INSENSITIVE. The A2A ``setTaskPushNotificationConfig``
    handler stores ``params.authentication.scheme`` verbatim from a free-form
    protobuf string — no enum guards that path — so lowercase rows exist in
    production. Comparing exactly against the pinned enum
    (``AuthenticationScheme = ["Bearer", "HMAC-SHA256"]``) would stop
    authenticating rows that are authenticated today: a regression, not a
    tightening.

    An unrecognised scheme resolves to :class:`Unauthenticated`, matching what
    every sender does with it today. It must not widen into
    :class:`HmacSecretMissing`, which means specifically "HMAC was asked for".
    """
    normalized = (scheme or "").strip().lower()
    if not normalized:
        return Unauthenticated()
    if normalized == _HMAC_SCHEME:
        return SignWithSecret(credentials) if credentials else HmacSecretMissing()
    if normalized == _BEARER_SCHEME:
        return BearerToken(credentials) if credentials else Unauthenticated()
    if normalized == _BASIC_SCHEME:
        return BasicCredentials(credentials) if credentials else Unauthenticated()
    return Unauthenticated()


def _canonical_body(payload: dict[str, Any]) -> bytes:
    """The ONE serialization every webhook payload goes through.

    Compact separators, insertion order — the canonical on-wire form pinned
    by adcontextprotocol/adcp#2478, and the same formula
    ``adcp.sign_legacy_webhook`` uses internally when it signs. Both the
    signed and unsigned branches of :func:`_prepare_signed_request` route
    through this single function so they cannot independently drift, the way
    the disease this module replaces did.
    """
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def prepare_signed_request(
    payload: dict[str, Any],
    secret: str | None,
    headers: dict[str, str],
    *,
    timestamp: str | int | None = None,
) -> tuple[dict[str, str], bytes]:
    """Serialize once; sign those exact bytes when a secret is given.

    Returns ``(headers, body_bytes)`` where ``body_bytes`` is what must be
    transmitted via ``content=`` — never re-derived, never re-serialized.
    When ``secret`` is provided, delegates entirely to
    ``adcp.sign_legacy_webhook``, whose returned ``body_bytes`` are asserted
    (in tests) to equal :func:`_canonical_body`'s own output for the same
    payload, so a future SDK revision that drifted from this formula would be
    caught immediately rather than silently diverging.

    Public (not module-private): callers that must know ``len(body_bytes)``
    or otherwise inspect the prepared request BEFORE sending it — logging the
    payload size ahead of a delivery that might fail before a response comes
    back — call this directly and pass the result to :func:`send`/:func:`asend`
    themselves, rather than through :func:`deliver_signed_webhook`. Call this
    at most ONCE per delivery: ``sign_legacy_webhook`` stamps the current time
    when no explicit ``timestamp`` is given, so calling it twice for the "same"
    delivery signs two different timestamps and only one bytes value may
    reach the wire. ``timestamp`` exists to make callers (notably conformance
    tests grading against fixed vectors) deterministic — real delivery callers
    leave it ``None``.
    """
    merged_headers = dict(headers)
    merged_headers.setdefault("Content-Type", "application/json")

    if secret:
        signed_headers, body_bytes = sign_legacy_webhook(secret, payload, timestamp=timestamp, headers=merged_headers)
        return signed_headers, body_bytes

    return merged_headers, _canonical_body(payload)


def deliver_signed_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    secret: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> OutboundResult:
    """Serialize, optionally sign, and send one webhook through the egress seam.

    ``OutboundRequestBlocked``/``OutboundDeliveryFailed`` propagate — each
    caller keeps its own catch/retry-record/circuit-breaker bookkeeping, which
    differs per sender and is out of this function's remit.
    """
    signed_headers, body_bytes = prepare_signed_request(payload, secret, headers or {})
    return send(url, content=body_bytes, headers=signed_headers, timeout=timeout, max_attempts=max_attempts)


async def adeliver_signed_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    secret: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> OutboundResult:
    """Async twin of :func:`deliver_signed_webhook` — identical policy."""
    signed_headers, body_bytes = prepare_signed_request(payload, secret, headers or {})
    return await asend(url, content=body_bytes, headers=signed_headers, timeout=timeout, max_attempts=max_attempts)

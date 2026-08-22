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
import logging
from dataclasses import dataclass
from typing import Any, Literal, cast

from adcp import extract_webhook_result_data, sign_legacy_webhook
from adcp.types import AuthenticationScheme
from adcp.types.generated_poc.core.push_notification_config import (
    Authentication as LibraryAuthentication,
)
from pydantic import ValidationError

from src.core.security.outbound_http import (
    OutboundDeliveryFailed,
    OutboundError,
    OutboundRequestBlocked,
    OutboundResult,
    asend,
    send,
    terminal_client_error_status,
)

logger = logging.getLogger(__name__)


RefusalReason = Literal[
    "no_credentials",
    "credentials_too_short",
    "scheme_not_in_spec",
    "multi_scheme",
    "no_scheme",
]


@dataclass(frozen=True, slots=True)
class WebhookDeliveryOutcome:
    """What became of one webhook delivery attempt. The seam's only return value.

    Senders used to conclude in ``bool`` — or in an exception they each caught
    differently — so "refused", "failed after retries" and "the receiver said no"
    all arrived as the same nothing, and each sender re-derived its own failure
    literals from whatever it happened to catch. This type carries the conclusion
    to whoever needs it instead.

    ``detail`` is PRE-SANITIZED at construction: never a URL, never a credential.
    ``payload_size_bytes`` is carried because it maps 1:1 onto
    ``WebhookDeliveryLog.payload_size_bytes`` and is the reason the protocol
    sender used to reach past the seam for ``len(body_bytes)`` — which is why the
    async twin had no caller.
    """

    kind: Literal["delivered", "refused_destination", "refused_auth", "client_error", "exhausted"]
    attempts: int
    http_status: int | None = None
    detail: str | None = None
    payload_size_bytes: int | None = None
    reason: RefusalReason | None = None
    scheme: str | None = None

    @classmethod
    def unexpected(cls, exception_type: str) -> WebhookDeliveryOutcome:
        """A non-transport failure, named by its EXCEPTION TYPE and nothing else.

        The two senders that conclude on a generic exception used to build this
        outcome inline with ``detail=str(e)``. That let a foreign exception's
        text ride into ``detail`` -- and ``detail`` is not an in-memory
        convenience: it is written verbatim to
        ``webhook_delivery_log.error_message`` and emitted as an audit warning.
        ``IpPinnedTransport``'s RuntimeError names the pinned host and the host
        it refused to connect to, so ``str(e)`` disclosed a destination into
        durable storage.

        The type name is diagnostic and carries nothing the buyer supplied. The
        exception's own message stays in the log line beside the call, where an
        operator can read it, and never enters the outcome.

        This does NOT make ``detail=str(e)`` unwritable -- this is a public
        frozen dataclass and a caller can still construct one by hand. It makes
        the sanitized form the named and convenient one. A future third
        out-of-module site could reconstruct the defect, and would be invisible
        to the seam-scoped outcome tests; that residual is accepted knowingly.
        """
        return cls(kind="exhausted", attempts=0, detail=f"delivery failed with an unexpected {exception_type}")


@dataclass(frozen=True, slots=True)
class WebhookTaskContext:
    """A delivery's task identity, constructed once and consumed identically
    by all three failure arms and the success path in
    ``_send_with_retry_and_logging``.

    Absorbs the metadata/payload pluck block that used to run inline at the
    top of ``_send_with_retry_and_logging`` — repeating that pluck (or,
    worse, re-threading its results as twelve independent kwargs at three
    call sites) is how one of them ends up silently dropped at one site.

    Lives HERE, beside :class:`WebhookDeliveryOutcome`, rather than in
    ``src/services/``: these are the two values
    ``DeliveryRepository.record_outcome`` consumes — WHO the delivery was for
    and WHAT became of it — and a repository importing a dataclass out of a
    service module would invert the layering. Nothing about task identity is
    sender-specific, which is the point: both senders build one of these.
    """

    task_id: str
    task_type: str | None
    tenant_id: str | None
    principal_id: str | None
    media_buy_id: str | None
    sequence_number: int
    notification_type: str | None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any], payload: dict[str, Any]) -> WebhookTaskContext:
        task_type = metadata["task_type"] if "task_type" in metadata else None
        tenant_id = metadata["tenant_id"] if "tenant_id" in metadata else None
        principal_id = metadata["principal_id"] if "principal_id" in metadata else None
        media_buy_id = metadata["media_buy_id"] if "media_buy_id" in metadata else None

        # TODO: Fix type annotation discrepancy in adcp library - extract_webhook_result_data
        # returns dict at runtime but is typed as AdcpAsyncResponseData | None
        result = cast(dict[str, Any] | None, extract_webhook_result_data(payload))
        # After serialization, payload is always a dict - extract task_id accordingly.
        # A2A Task uses 'id'; A2A TaskStatusUpdateEvent uses camelCase 'taskId' (proto
        # json_name wire contract); MCP uses snake_case 'task_id'.
        task_id = payload.get("id") or payload.get("taskId") or payload.get("task_id") or ""

        # If we are delivering media buy delivery report
        notification_type_from_result = result.get("notification_type") if result is not None else None
        sequence_number_from_result = result.get("sequence_number") if result is not None else None
        notification_type = notification_type_from_result
        sequence_number = sequence_number_from_result if isinstance(sequence_number_from_result, int) else 1

        return cls(
            task_id=task_id,
            task_type=task_type,
            tenant_id=tenant_id,
            principal_id=principal_id,
            media_buy_id=media_buy_id,
            sequence_number=sequence_number,
            notification_type=notification_type,
        )

    @property
    def records_delivery_log(self) -> bool:
        """Whether this delivery is eligible for a ``webhook_delivery_log`` row.

        Spells the gating condition that used to appear twice (once per
        failure/success branch) exactly once.
        """
        return (
            self.task_type in ("delivery_report", "media_buy_delivery")
            and bool(self.media_buy_id)
            and bool(self.tenant_id)
            and bool(self.principal_id)
        )


def _authentication_or_refusal(
    scheme: str | None,
    credentials: str | None,
) -> LibraryAuthentication | WebhookDeliveryOutcome | None:
    """Validate the stored pair, or return the refusal it earns. The ONE decision.

    Returns ``None`` for "no authentication block was registered" — deliver plain,
    which is what the pinned schema's "absence selects 9421" means for a seller
    that has not implemented the 9421 profile yet.

    Constructing the pinned ``Authentication`` (imported here as
    ``LibraryAuthentication``, an alias -- there is no subclass) IS the
    validation: ``credentials`` is required with ``minLength: 32`` and ``schemes``
    has ``maxItems: 1``, and the enum is the pin's own, unwidened. A scheme
    outside it is REFUSED rather than folded, and casing is not folded either --
    ``"bearer"`` refuses exactly as ``"Digest"`` does. So there is no
    supported-set to keep in step with the spec and no per-sender branching: a
    caller either gets a validated block or an outcome.

    The blank-scheme pair is TWO different documents and must not be conflated:
    no scheme and no credential means there was no ``authentication`` block at
    all (the spec's own selector for the RFC 9421 baseline, so deliver plain),
    while no scheme WITH a credential means a block existed whose ``schemes``
    array was empty — which the pinned type refuses, and which
    ``ValidatedWebhookRegistration.from_stash`` (which can see the array) already
    refuses. Answering those the same way would give one stored row two answers
    depending on which caller saw it.
    """
    if not (scheme or "").strip():
        if (credentials or "").strip():
            # Reported as scheme=None, not as the blank string: a whitespace-only
            # value is the ABSENCE of a scheme, and echoing "   " back at an
            # operator tells them nothing they can search a row by.
            return _refusal(None, "no_scheme")
        return _NO_AUTHENTICATION

    try:
        return LibraryAuthentication(schemes=[scheme], credentials=credentials)
    except ValidationError as exc:
        reason = _reason(exc)
        return _refusal(scheme, reason)


def _reason(
    exc: ValidationError,
) -> RefusalReason:
    """Map the pinned type's own complaint onto the closed reason set.

    Derived from the ``ValidationError`` rather than re-checked by hand, so the
    reasons cannot drift from what the schema actually enforces.
    """
    for error in exc.errors():
        location = error.get("loc") or ()
        kind = error.get("type", "")
        if "credentials" in location:
            # Explicit on the error type, never an else-catch: a key that is ABSENT
            # reports "missing" while a key present with a null reports
            # "string_type", and both mean the same thing to a buyer — no credential
            # was supplied. Only an actual short string is credentials_too_short.
            # An else-catch here silently relabels the first two, and this
            # discriminator is graded against the buyer-visible refusal envelope.
            if kind == "string_too_short":
                return "credentials_too_short"
            return "no_credentials"
        if "schemes" in location:
            return "multi_scheme" if kind == "too_long" else "scheme_not_in_spec"
    return "scheme_not_in_spec"


_REFUSAL_DETAIL: dict[RefusalReason, str] = {
    "no_credentials": "the registration names an authentication scheme but stores no credential",
    "credentials_too_short": "the stored credential is shorter than the 32 characters the spec requires",
    "scheme_not_in_spec": "the stored authentication scheme is not one this seller supports",
    "multi_scheme": "the registration names more than one authentication scheme",
    "no_scheme": "an authentication block was stored with no scheme",
}


def _refusal(scheme: str | None, reason: RefusalReason) -> WebhookDeliveryOutcome:
    """A refusal outcome. Nothing is dialled, so ``attempts`` is zero by construction.

    The sentence is looked up here rather than passed in. Handed in, a caller
    could — and one did — spell a literal that duplicated the table's own entry,
    so an edit to the table reached nothing and ``"no_scheme"`` sat in it unread.
    With no parameter to pass, the table is the only way to say it.
    """
    detail = _REFUSAL_DETAIL[reason]
    # The log names BOTH the human sentence and the machine-readable reason. The
    # reason is what an operator greps for to enumerate every affected registration;
    # the sentence is what tells them what to do about it. With no outcome record on
    # the rehydration seat and no migration for these rows, this line is the only
    # surface the decision has.
    logger.error(
        "Refusing to deliver webhook [%s]: %s (scheme=%r). The registration must be corrected by its owner.",
        reason,
        detail,
        scheme,
    )
    return WebhookDeliveryOutcome(
        kind="refused_auth",
        attempts=0,
        http_status=None,
        detail=detail,
        reason=reason,
        scheme=scheme,
    )


# Sentinel for "no authentication block was registered": deliver plain, which is
# what the pinned schema's "absence selects 9421" means for a seller that has not
# implemented the 9421 profile yet.
_NO_AUTHENTICATION: LibraryAuthentication | None = None


def _canonical_body(payload: dict[str, Any]) -> bytes:
    """The ONE serialization every webhook payload goes through.

    Compact separators, insertion order — the canonical on-wire form pinned
    by adcontextprotocol/adcp#2478, and the same formula
    ``adcp.sign_legacy_webhook`` uses internally when it signs. Both the
    signed and unsigned branches of :func:`prepare_signed_request` route
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
    themselves. Call this
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


# ── The seam: one decision, one outcome ───────────────────────────────────────


def _headers_for(
    auth: LibraryAuthentication | None, headers: dict[str, str] | None
) -> tuple[dict[str, str], str | None]:
    """Turn a validated block into (headers, signing secret). Matched ONCE.

    Shared by both twins deliberately: if each destructured the decision itself,
    "decided here and nowhere else" would be false on the day this shipped.
    """
    prepared = dict(headers or {})
    if auth is None:
        return prepared, None

    scheme = auth.schemes[0]
    credential = auth.credentials
    match scheme:
        case AuthenticationScheme.HMAC_SHA256:
            return prepared, credential
        case AuthenticationScheme.Bearer:
            prepared["Authorization"] = f"Bearer {credential}"
            return prepared, None
    # Adding a member to AuthenticationScheme without a branch here lands on this line
    # rather than delivering the webhook with the new scheme silently ignored.
    raise AssertionError(f"unhandled scheme: {scheme!r} — add a branch in _headers_for")


def _outcome_for_outbound_error(exc: OutboundError, *, payload_size_bytes: int | None) -> WebhookDeliveryOutcome:
    """Classify a seam failure. The ONE place the taxonomy is read.

    Every sender used to re-derive these literals from whichever exception it
    happened to catch, which is how three senders reported the same failure three
    ways.
    """
    attempts = exc.attempts or 0
    status = exc.http_status
    if isinstance(exc, OutboundRequestBlocked):
        return WebhookDeliveryOutcome(
            kind="refused_destination",
            attempts=0,
            http_status=None,
            detail="the destination was refused before any connection was made",
            payload_size_bytes=payload_size_bytes,
        )
    if terminal_client_error_status(exc) is not None:
        return WebhookDeliveryOutcome(
            kind="client_error",
            attempts=attempts,
            http_status=status,
            detail=f"the receiver answered {status} and will not be retried",
            payload_size_bytes=payload_size_bytes,
        )
    return WebhookDeliveryOutcome(
        kind="exhausted",
        attempts=attempts,
        http_status=status,
        detail="delivery did not succeed within the attempt budget",
        payload_size_bytes=payload_size_bytes,
    )


def _delivered(result: OutboundResult, *, payload_size_bytes: int) -> WebhookDeliveryOutcome:
    return WebhookDeliveryOutcome(
        kind="delivered",
        attempts=result.attempts,
        http_status=result.http_status,
        detail=None,
        payload_size_bytes=payload_size_bytes,
    )


def deliver_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    scheme: str | None = None,
    credentials: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> WebhookDeliveryOutcome:
    """Deliver one webhook and say what became of it.

    Takes the stored PRIMITIVES rather than a validated block on purpose: senders
    read ``authentication_type`` / ``authentication_token`` off a row, and handing
    them a type to construct would hand each of them a ``ValidationError`` to
    interpret — three senders deciding again what an invalid registration means,
    which is the divergence this seam exists to end. Primitives in, outcome out.
    """
    decided = _authentication_or_refusal(scheme, credentials)
    if isinstance(decided, WebhookDeliveryOutcome):
        return decided

    auth_headers, secret = _headers_for(decided, headers)

    # ONE serialization per delivery. The bytes that are measured, the bytes that
    # are signed and the bytes that go on the wire are the same object, because
    # there is only one. This used to run twice -- once here purely for len(),
    # once again inside the delivery helper -- and two runs of a serializer are
    # two things that can disagree, which is the whole reason the signed and
    # transmitted bodies had to be asserted equal in tests rather than being
    # equal by construction.
    request_headers, body_bytes = prepare_signed_request(payload, secret, auth_headers)
    try:
        result = send(url, content=body_bytes, headers=request_headers, timeout=timeout, max_attempts=max_attempts)
    except (OutboundRequestBlocked, OutboundDeliveryFailed) as exc:
        return _outcome_for_outbound_error(exc, payload_size_bytes=len(body_bytes))
    return _delivered(result, payload_size_bytes=len(body_bytes))


async def adeliver_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    scheme: str | None = None,
    credentials: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> WebhookDeliveryOutcome:
    """Async twin of :func:`deliver_webhook` — identical policy, shared helpers."""
    decided = _authentication_or_refusal(scheme, credentials)
    if isinstance(decided, WebhookDeliveryOutcome):
        return decided

    auth_headers, secret = _headers_for(decided, headers)

    # One serialization, exactly as in the sync twin above.
    request_headers, body_bytes = prepare_signed_request(payload, secret, auth_headers)
    try:
        result = await asend(
            url, content=body_bytes, headers=request_headers, timeout=timeout, max_attempts=max_attempts
        )
    except (OutboundRequestBlocked, OutboundDeliveryFailed) as exc:
        return _outcome_for_outbound_error(exc, payload_size_bytes=len(body_bytes))
    return _delivered(result, payload_size_bytes=len(body_bytes))

"""Prometheus metrics for monitoring AI review and webhook operations.

Label cardinality is deliberately bounded to keep memory flat for a
long-running multi-tenant process:

- **Histograms** never label by ``tenant_id``. Each series allocates a full
  bucket array, so a per-tenant label makes memory grow linearly with the
  tenant count. Latency views stay aggregated; per-tenant *volume* is still
  available on the cheaper Counters.
- **``error_type``** is collapsed to a fixed enum via :func:`categorize_error`
  instead of ``type(e).__name__`` (otherwise unbounded as code evolves, and
  attacker-influenceable).
- **``policy_triggered``** is validated against :data:`POLICY_TRIGGERED_ALLOWLIST`
  via :func:`sanitize_policy_triggered`; unknown values collapse to ``"other"``.
- **``code``** (request-signature outcomes) is validated against the SDK's own
  request-family taxonomy via :func:`sanitize_signature_code`; anything else —
  including anything an attacker could induce — collapses to ``"other"``.
- **``keyid``** is the signer's real key id ONLY after the verifier resolved it
  (checklist step 7), i.e. only for a key we already recognize. Before that it is
  attacker-supplied, so it is recorded as ``"unresolved"``.

Call sites must record AI-review metrics through :func:`record_ai_review` and
:func:`record_ai_review_error`, and request-signature outcomes through
:func:`record_signature_verified` / :func:`record_signature_failed` /
:func:`record_request_unsigned`, so the bounding logic lives in exactly one place.
"""

from adcp.signing.errors import REQUEST_TO_WEBHOOK_CODE
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest

from src.core.exceptions import (
    AdCPRateLimitError,
    AdCPServiceUnavailableError,
    AdCPValidationError,
)

# ---------------------------------------------------------------------------
# Bounded label vocabularies
# ---------------------------------------------------------------------------

#: Fixed enum for the ``error_type`` label. Keep <= 5 values.
ERROR_TYPE_VALUES = ("validation", "timeout", "model_error", "other")

#: Closed set of ``policy_triggered`` values emitted by the AI review flow.
#: Anything outside this set (e.g. an AI-generated free-form reason) collapses
#: to ``"other"`` to prevent unbounded series growth.
POLICY_TRIGGERED_ALLOWLIST = frozenset(
    {
        "sensitive_category",
        "auto_approve",
        "low_confidence_approval",
        "auto_reject",
        "uncertain_rejection",
        "uncertain",
        "other",
    }
)


def categorize_error(error: BaseException) -> str:
    """Collapse an arbitrary exception into a bounded ``error_type`` enum.

    The mapping is intentionally coarse — its only job is to keep Prometheus
    series count constant regardless of how many exception classes exist.
    """
    # Timeouts first: a TimeoutError may also subclass OSError, and project
    # AdCP errors that mean "service unavailable" are timeout-ish operationally.
    if isinstance(error, TimeoutError | AdCPServiceUnavailableError | AdCPRateLimitError):
        return "timeout"
    if isinstance(error, ValueError | TypeError | KeyError | AdCPValidationError):
        return "validation"
    # AI/model layer surfaces failures as RuntimeError or connection errors.
    if isinstance(error, RuntimeError | ConnectionError):
        return "model_error"
    return "other"


def sanitize_policy_triggered(value: str | None) -> str:
    """Return ``value`` if it is in the allowlist, else ``"other"``."""
    if value in POLICY_TRIGGERED_ALLOWLIST:
        return value
    return "other"


#: The 27 request-family signature rejection codes, taken from the SDK's own
#: request->webhook translation table rather than re-listed here. The spec grades
#: these byte-for-byte, so a hand-maintained copy would be a second source that can
#: drift from the one the verifier actually raises.
SIGNATURE_ERROR_CODES = frozenset(REQUEST_TO_WEBHOOK_CODE)

#: ``keyid`` before the verifier resolved one (checklist step 7). Every rejection
#: carries this: ``SignatureVerificationError`` does not expose the keyid, and a
#: pre-resolution keyid is attacker-supplied and therefore unbounded.
UNRESOLVED_KEYID = "unresolved"

#: Why a request was not verified. Two values, both closed.
UNSIGNED_REASONS = frozenset({"absent", "ignored"})


def sanitize_signature_code(code: str | None) -> str:
    """Return ``code`` if it is a spec request-signature code, else ``"other"``."""
    return code if code in SIGNATURE_ERROR_CODES else "other"


# ---------------------------------------------------------------------------
# AI Review Metrics
# ---------------------------------------------------------------------------
ai_review_total = Counter(
    "ai_review_total",
    "Total AI reviews performed",
    ["tenant_id", "decision", "policy_triggered"],
)

ai_review_duration = Histogram(
    "ai_review_duration_seconds",
    "AI review latency in seconds (aggregated across tenants)",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

ai_review_errors = Counter(
    "ai_review_errors_total",
    "AI review errors by bounded error type",
    ["tenant_id", "error_type"],
)

ai_review_confidence = Histogram(
    "ai_review_confidence",
    "AI review confidence scores (0-1, aggregated across tenants)",
    ["decision"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ---------------------------------------------------------------------------
# Webhook Metrics
# ---------------------------------------------------------------------------
webhook_delivery_total = Counter(
    "webhook_delivery_total",
    "Total webhook deliveries",
    ["tenant_id", "event_type", "status"],
)

webhook_delivery_duration = Histogram(
    "webhook_delivery_duration_seconds",
    "Webhook delivery latency in seconds (aggregated across tenants)",
    ["event_type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

webhook_delivery_attempts = Histogram(
    "webhook_delivery_attempts",
    "Number of delivery attempts before success (aggregated across tenants)",
    ["event_type"],
    buckets=[1, 2, 3, 4, 5],
)

# ---------------------------------------------------------------------------
# Active monitoring gauges
# ---------------------------------------------------------------------------
# Gauges are keyed by tenant_id but are self-bounding: they track *currently
# active* work, so series stay proportional to live concurrency, not history.
active_ai_reviews = Gauge(
    "active_ai_reviews",
    "Currently running AI reviews",
    ["tenant_id"],
)

webhook_queue_size = Gauge(
    "webhook_queue_size",
    "Number of webhooks pending delivery",
    ["tenant_id"],
)

# ---------------------------------------------------------------------------
# RFC 9421 inbound request-signature outcomes (#1291 B1)
# ---------------------------------------------------------------------------
# The middleware is the ONLY layer that sees the verifier's outcome before it is
# swallowed (``warn_for``) or turned into a transport 401, so these three counters
# are the whole evidence base for the shadow-mode promotion ladder
# (supported_for -> warn_for -> required_for). No ``tenant_id`` label: the posture
# is per-tenant but the series count must not grow with the tenant list.
request_signature_verified_total = Counter(
    "adcp_request_signature_verified_total",
    "Inbound RFC 9421 request signatures that passed the verifier checklist",
    ["operation", "keyid"],
)

request_signature_failed_total = Counter(
    "adcp_request_signature_failed_total",
    "Inbound RFC 9421 request signatures rejected by the verifier checklist",
    ["operation", "keyid", "code"],
)

request_unsigned_total = Counter(
    "adcp_request_unsigned_total",
    "Inbound AdCP requests the verifier did not grade (no signature, or posture ignores it)",
    ["operation", "reason"],
)


# ---------------------------------------------------------------------------
# Recording helpers — single source of truth for label bounding
# ---------------------------------------------------------------------------
def record_ai_review(tenant_id: str, decision: str, policy_triggered: str | None) -> None:
    """Increment :data:`ai_review_total` with a bounded ``policy_triggered``."""
    ai_review_total.labels(
        tenant_id=tenant_id,
        decision=decision,
        policy_triggered=sanitize_policy_triggered(policy_triggered),
    ).inc()


def record_ai_review_error(tenant_id: str, error: BaseException) -> None:
    """Increment :data:`ai_review_errors` with a bounded ``error_type``."""
    ai_review_errors.labels(tenant_id=tenant_id, error_type=categorize_error(error)).inc()


def record_signature_verified(operation: str, keyid: str) -> None:
    """Increment :data:`request_signature_verified_total` for a verified signer.

    ``keyid`` is safe to record verbatim here and ONLY here: the verifier resolved it
    against the counterparty's JWKS at checklist step 7, so the value is drawn from a
    key set we already know.
    """
    request_signature_verified_total.labels(operation=operation, keyid=keyid).inc()


def record_signature_failed(operation: str, code: str | None) -> None:
    """Increment :data:`request_signature_failed_total` with a bounded ``code``."""
    request_signature_failed_total.labels(
        operation=operation,
        keyid=UNRESOLVED_KEYID,
        code=sanitize_signature_code(code),
    ).inc()


def record_request_unsigned(operation: str, reason: str) -> None:
    """Increment :data:`request_unsigned_total`.

    ``reason="absent"`` — the request carried no signature headers.
    ``reason="ignored"`` — headers were present but the tenant's posture puts this
    operation in the ``none`` bucket, so nothing was verified (and, per R-H3, nothing
    was buffered or hashed either).
    """
    request_unsigned_total.labels(
        operation=operation,
        reason=reason if reason in UNSIGNED_REASONS else "other",
    ).inc()


def get_metrics_text() -> str:
    """Return current metrics in Prometheus text format."""
    return generate_latest(REGISTRY).decode("utf-8")

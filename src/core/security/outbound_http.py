"""The single seam every outbound HTTP request in this application goes through.

**This application implements no SSRF protection, ever.** Not private-IP
classification, not a cloud-metadata blocklist, not resolve-then-check, not
redirect re-validation. Every one of those belongs to a maintained library:

* ``adcp.signing`` owns address validation, cloud-metadata blocking, and
  resolve-once + IP pinning (DNS-rebinding defence), via
  :func:`adcp.signing.build_ip_pinned_transport`.
* ``httpx`` owns the response state machine — status, redirects, 1xx,
  decompression, TLS, pooling.
* This module owns only what neither decides for us: requiring TLS, capping the
  response body, and what counts as retryable.

SSRF recurred in this codebase because policy lived at call sites, so each new
outbound call shipped without it. Centralising *our own* copy of that policy
would only move the recurrence. Deleting our copy entirely and routing every
call through one seam backed by a maintained library is what makes the
recurrence structurally impossible.

Spec grounding: AdCP 3.1.1, ``building/by-layer/L1/security.mdx``, "Webhook URL
validation (SSRF)". Before any outbound fetch to a counterparty-controlled URL a
fetcher MUST (1) reject non-HTTPS in production, (2) reject reserved ranges,
(3) pin the connection to the validated IP, (4) refuse to follow redirects,
(5) cap response size and timeouts, and (6) not echo fetch errors back to the
agent that supplied the URL. Points 2 and 3 are the SDK's; point 4 comes free
from httpx's ``follow_redirects=False`` default, which is why no line in this
module sets it; 1, 5 and 6 are implemented here.

The public surface is a *send function*, deliberately not a client factory. A
factory would leave the four existing retry/backoff/classification copies in
place and add a fifth thing to get wrong per call site.

There is one more entry point, :func:`validate_url`, for URLs that are STORED
rather than sent — a webhook URL accepted at ingest and fetched later. It runs
the identical pre-connection policy and connects to nothing, so those call sites
have no reason to grow a second copy of address policy either.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx
from adcp.signing import (
    SSRFValidationError,
    build_async_ip_pinned_transport,
    build_ip_pinned_transport,
    resolve_and_validate_host,
)

from src.core.exceptions import AdCPInvalidRequestError, AdCPServiceUnavailableError

logger = logging.getLogger(__name__)

# Escape hatches. Both default OFF — a guarded posture is the default, and an
# operator has to say so out loud to leave it.
_ALLOW_PRIVATE_ENV = "ADCP_OUTBOUND_ALLOW_PRIVATE"
_ALLOW_INSECURE_ENV = "ADCP_OUTBOUND_ALLOW_INSECURE"

# Response bodies are accumulated, so an unbounded counterparty response is a
# memory-exhaustion vector. httpx applies no default limit (spec point 5).
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024

# Retry backoff, as a module constant so tests stay honest without patching
# ``time.sleep``: attempt N waits _BACKOFF_BASE_SECONDS * 2**N.
_BACKOFF_BASE_SECONDS = 0.1

# Statuses worth trying again. Everything else — including every 4xx and every
# 3xx — is terminal: retrying a rejected or redirected request only doubles the
# damage.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

# httpx signals these as exceptions, never as a status, so a status-only
# classifier would let them escape the seam and force every migrated call site
# to keep its own ``except httpx...`` — the duplication this module deletes.
_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
)

# Spec point 6: one fixed message for every refusal, whatever the real cause.
# The SDK's own text says "resolved IP <IP> is in a reserved range" versus
# "cannot resolve host '<host>'" — echoing either back hands the party that
# supplied the URL both the resolved address and whether the name exists, which
# is an internal host and port scanner. These messages never interpolate
# anything.
_BLOCKED_MESSAGE = "Outbound request to the supplied URL was refused by egress policy."
_DELIVERY_FAILED_MESSAGE = "Outbound request to the supplied URL could not be delivered."


class OutboundError(Exception):
    """Marker base for every failure this seam raises — NEVER raised directly.

    It exists so a call site that only logs can write one ``except``. It is
    deliberately *not* an ``AdCPError``: raising it directly would degrade to a
    bare INTERNAL_ERROR at a transport boundary and would be invisible to the
    error-taxonomy guards that walk ``AdCPError.iter_concrete_subclasses()``.
    Raise one of the two concrete subclasses instead.

    It defines no ``__init__`` on purpose — one would shadow ``AdCPError``'s
    through the MRO of those subclasses.
    """


class OutboundRequestBlocked(OutboundError, AdCPInvalidRequestError):
    """The URL was refused before any connection was attempted.

    Scheme or address policy said no. Terminal — never retried, because nothing
    about the destination will change on a second look.
    """


class OutboundDeliveryFailed(OutboundError, AdCPServiceUnavailableError):
    """The destination was reachable but the request was not delivered.

    ``attempts`` is how many times it was tried; ``last_status`` is the last
    HTTP status observed, or ``None`` when the failure was a transport
    exception and there was never a response to read a status from.
    """

    # Only these two fields ride to the buyer. `details` is buyer-visible —
    # build_two_layer_error_envelope passes it straight into the adcp_error
    # payload — so nothing derived from the origin's response or from the httpx
    # error string may be added here (spec point 6).
    _DETAIL_KEYS: ClassVar[tuple[str, str]] = ("attempts", "last_status")

    def __init__(self, *, attempts: int, last_status: int | None) -> None:
        super().__init__(
            _DELIVERY_FAILED_MESSAGE,
            details={"attempts": attempts, "last_status": last_status},
        )
        self.attempts = attempts
        self.last_status = last_status


@dataclass(frozen=True)
class OutboundResult:
    """A delivered response, plus what it cost to get it."""

    response: httpx.Response
    attempts: int
    duration_seconds: float
    _body: bytes

    @property
    def status_code(self) -> int:
        return self.response.status_code

    def json(self) -> Any:
        """Decode the body as JSON.

        Raises ``json.JSONDecodeError`` on a non-JSON body. That is deliberately
        *outside* the ``except OutboundError`` contract: a body that does not
        parse is the call site's business, not a transport failure.
        """
        return json.loads(self._body)


def _env_flag(name: str) -> bool:
    """Read a boolean env flag the way the rest of the repo does.

    Read at CALL time, never at import: tests flip these with
    ``monkeypatch.setenv`` and an import-time read would freeze the first value.
    """
    return os.environ.get(name, "").lower() == "true"


def _require_tls(url: str) -> None:
    """Reject anything but https:// unless the insecure hatch is open.

    The one address-adjacent rule the seam owns: the SDK validator deliberately
    permits plain http, because it is a transport validator, not a transport
    policy.
    """
    if url.lower().startswith("https://"):
        return
    if _env_flag(_ALLOW_INSECURE_ENV):
        return
    logger.warning("Outbound request refused: scheme is not https")
    raise OutboundRequestBlocked(_BLOCKED_MESSAGE)


def _blocked(exc: SSRFValidationError) -> OutboundRequestBlocked:
    """Translate an SDK refusal into an opaque typed refusal.

    The SDK detail is logged and never returned: ``str(exc)`` names the resolved
    IP and distinguishes "unresolvable" from "reserved".
    """
    logger.warning("Outbound request refused by address policy: %s", exc)
    return OutboundRequestBlocked(_BLOCKED_MESSAGE)


def _prepare[Validated](url: str, validator: Callable[..., Validated]) -> Validated:
    """Run every pre-connection egress decision, once, and hand back what the caller asked for.

    Scheme policy, the escape-hatch read, the SDK's address validation and the
    translation of its refusal are ONE decision, not three implementations of
    one. ``Validated`` — what the caller gets out of the validated URL: a sync
    transport, an async transport, or the resolved triple a validate-only caller
    discards — is the ONLY thing that varies between the three, and each of
    those is a call into ``adcp.signing`` that runs the identical
    resolve-and-validate step (``build_ip_pinned_transport`` is literally
    ``resolve_and_validate_host`` plus a transport constructor). That is what
    makes "validate-only refuses exactly what send refuses" a property of the
    code rather than a claim a test has to keep re-proving.

    Raises :class:`OutboundRequestBlocked` — never lets ``SSRFValidationError``
    out, because its message names the resolved IP (spec point 6).
    """
    _require_tls(url)
    try:
        return validator(url, allow_private=_env_flag(_ALLOW_PRIVATE_ENV))
    except SSRFValidationError as exc:
        raise _blocked(exc) from exc


def _should_retry_status(status: int) -> bool:
    return status in _RETRYABLE_STATUSES


def _backoff_seconds(attempt: int) -> float:
    """Seconds to wait before the attempt after ``attempt`` (1-based)."""
    return _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))


def _build_request(
    client: httpx.Client | httpx.AsyncClient,
    *,
    method: str,
    url: str,
    json_body: Any,
    params: Any,
    headers: Any,
    content: Any,
) -> httpx.Request:
    return client.build_request(
        method.upper(),
        url,
        json=json_body,
        params=params,
        headers=headers,
        content=content,
    )


def _over_cap(size: int) -> bool:
    return size > _MAX_RESPONSE_BYTES


def _attach_body(response: httpx.Response, body: bytes) -> None:
    """Make the streamed body readable through the response object itself.

    The body has to be streamed so the size cap can be enforced while
    accumulating, but a streamed response whose stream is exhausted raises
    ``ResponseNotRead`` from ``.content`` / ``.text``. Every call site migrating
    onto this seam logs one of those, so handing back a response that cannot be
    read would be a trap. Assigning ``_content`` is how httpx itself records a
    read body (``Response.read``); after this, ``.content``, ``.text`` and
    ``.json()`` all behave as on a non-streamed response.
    """
    response._content = body


def _result(response: httpx.Response, body: bytes, attempt: int, started: float) -> OutboundResult:
    _attach_body(response, body)
    return OutboundResult(
        response=response,
        attempts=attempt,
        duration_seconds=time.monotonic() - started,
        _body=body,
    )


def _fail(attempts: int, last_status: int | None) -> OutboundDeliveryFailed:
    return OutboundDeliveryFailed(attempts=attempts, last_status=last_status)


def validate_url(url: str) -> None:
    """Apply the seam's egress policy to a URL WITHOUT sending anything.

    For URLs that are *stored* rather than sent: a webhook or brand-manifest URL
    supplied at ingest time is persisted now and fetched later, possibly by a
    background worker, so the refusal a buyer can act on has to happen at ingest
    — long before there is a request to attach it to. A send-only seam cannot
    serve those call sites, and the alternative they reach for otherwise is a
    second, hand-written copy of address policy, which is the recurrence this
    module exists to make impossible.

    It refuses EXACTLY what :func:`send` and :func:`asend` refuse, because all
    three go through :func:`_prepare` and differ only in what they ask the SDK
    to return; here that is the resolved ``(hostname, ip, port)``, which is
    discarded. No transport is built, no socket is opened, no DNS answer is
    reused: validation at ingest is a policy verdict, and a *later* fetch must
    resolve again through its own :func:`send` call, because a resolution
    cached across that gap is precisely the DNS-rebinding window the SDK's
    resolve-once-then-pin closes within a single request.

    Returns nothing and raises :class:`OutboundRequestBlocked` on refusal, with
    the same opaque message :func:`send` uses — a validator that handed back the
    resolved address would leak it to whatever logs or stores the result (spec
    point 6).
    """
    _prepare(url, resolve_and_validate_host)


def send(
    url: str,
    *,
    method: str = "POST",
    json: Any = None,
    params: Any = None,
    headers: Any = None,
    content: Any = None,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> OutboundResult:
    """Send one outbound HTTP request through the seam.

    ``max_attempts`` counts TOTAL attempts, not retries after the first, so
    ``max_attempts=1`` is how a non-idempotent or vendor call opts out of retry.
    ``duration_seconds`` on the result is total wall time across all attempts.

    Raises :class:`OutboundRequestBlocked` if the scheme or the address is
    refused (before any connection is attempted), or
    :class:`OutboundDeliveryFailed` if the destination was reached but the
    request was not delivered. Both are ``OutboundError`` subclasses, so a call
    site that only logs can catch that one type.
    """
    transport = _prepare(url, build_ip_pinned_transport)

    started = time.monotonic()
    last_status: int | None = None

    # One transport per call, never cached: the pin is per-destination and fails
    # closed when reused for another host.
    with httpx.Client(transport=transport, timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            request = _build_request(
                client,
                method=method,
                url=url,
                json_body=json,
                params=params,
                headers=headers,
                content=content,
            )
            try:
                response = client.send(request, stream=True)
                try:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if _over_cap(len(body)):
                            # Terminal: a body too large now will be too large
                            # on a retry too.
                            logger.warning("Outbound response exceeded the size cap; aborting read")
                            raise _fail(attempt, response.status_code)
                finally:
                    response.close()
            except _RETRYABLE_EXCEPTIONS as exc:
                logger.warning("Outbound attempt %d failed at the transport level: %s", attempt, exc)
                last_status = None
            else:
                last_status = response.status_code
                if not _should_retry_status(last_status):
                    if response.is_success:
                        return _result(response, bytes(body), attempt, started)
                    raise _fail(attempt, last_status)

            if attempt < max_attempts:
                time.sleep(_backoff_seconds(attempt))

    raise _fail(max_attempts, last_status)


async def asend(
    url: str,
    *,
    method: str = "POST",
    json: Any = None,
    params: Any = None,
    headers: Any = None,
    content: Any = None,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> OutboundResult:
    """Async twin of :func:`send` — same policy, same failure modes.

    See :func:`send` for the contract. The two differ only in
    ``Client``/``AsyncClient`` and ``time.sleep``/``asyncio.sleep``; every
    policy decision is a shared helper so neither path can drift from the other.
    """
    transport = _prepare(url, build_async_ip_pinned_transport)

    started = time.monotonic()
    last_status: int | None = None

    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            request = _build_request(
                client,
                method=method,
                url=url,
                json_body=json,
                params=params,
                headers=headers,
                content=content,
            )
            try:
                response = await client.send(request, stream=True)
                try:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if _over_cap(len(body)):
                            logger.warning("Outbound response exceeded the size cap; aborting read")
                            raise _fail(attempt, response.status_code)
                finally:
                    await response.aclose()
            except _RETRYABLE_EXCEPTIONS as exc:
                logger.warning("Outbound attempt %d failed at the transport level: %s", attempt, exc)
                last_status = None
            else:
                last_status = response.status_code
                if not _should_retry_status(last_status):
                    if response.is_success:
                        return _result(response, bytes(body), attempt, started)
                    raise _fail(attempt, last_status)

            if attempt < max_attempts:
                await asyncio.sleep(_backoff_seconds(attempt))

    raise _fail(max_attempts, last_status)

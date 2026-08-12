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

**Sanctioned dialers outside this seam.** A handful of outbound calls
deliberately do not go through ``send``/``asend``, and each is recorded here
so the next reader can tell a sanctioned dialer from an unnoticed bypass
without archaeology through a PR description:

* ``adcp.adagents.fetch_adagents`` (called from
  ``src/admin/blueprints/publisher_partners.py``,
  ``src/services/property_discovery_service.py``,
  ``src/services/property_verification_service.py`` — all dialing a
  tenant-admin-configured ``publisher_domain``). Its ``_owned_pinned_client``
  builds an ``AsyncIpPinnedTransport`` on the validated IP with
  ``trust_env=False`` and mints a FRESH pinned client per redirect hop — this
  is *stronger* than injecting this seam's client would be: our client
  resolves once and pins, which would collapse into a TOCTOU pre-check across
  ``fetch_adagents``' own multi-host redirect chain rather than re-pinning at
  each hop. Injecting our client here would weaken, not tighten, the address
  policy.
* authlib (OIDC/OAuth discovery and token exchange, ``requests``-backed): not
  TID251-expressible, because the URL arrives inside a kwarg the ban cannot
  see. Ingest-time validation of ``discovery_url``/``logout_url`` is the
  defence (``src/admin/blueprints/oidc.py``); the second-order
  ``token_endpoint``/``jwks_uri`` read out of the discovery document is
  tracked separately (prebid/salesagent#1872).
* Fixed-destination SDKs — ``googleads``, ``google.auth``,
  ``google.cloud.iam``, ``pydantic_ai`` providers. No attacker- or
  tenant-controlled URL ever reaches these; their destinations are vendor
  constants dialled under operator credentials. Banning them would be noqa
  ceremony with no threat behind it.

**RFC 9421 signers do NOT need their own client** (salesagent-47n9.22). A signer
whose signature cannot be replayed — RFC 9421 covers a ``nonce`` a conformant
receiver must reject twice — used to have a reason to open its own
``httpx.AsyncClient``: this seam owns retry, so a signature computed once above
the loop ships unchanged on attempts 2 and 3. That reason is gone. ``send``/
``asend`` take a :class:`SignAttempt` callback invoked once PER ATTEMPT, inside
the retry loop. Injection, not detection — the caller never receives a client it
could point somewhere else, exactly like :func:`guarded_client_factory`.

Two properties of that hook are load-bearing, and neither is evident from the
parameter name:

* It is invoked AFTER ``client.build_request``, so the signer is handed
  ``request.content`` — the exact bytes httpx will transmit — and the
  post-params ``request.url``. That is what removes the re-serialization hazard
  (#1441 / salesagent-47n9.1) in which a signer signed one serialization of a
  payload while httpx independently produced another. For a ``sign=`` caller
  BOTH ``json=`` and ``content=`` are therefore sound. (The ``json=`` ban in
  ``tests/unit/test_architecture_no_signed_webhook_json_send.py`` is about
  sign-ONCE callers holding an ``X-*-Signature`` key; it does not match RFC
  9421's header names, and on this path those names are minted inside
  ``adcp``'s ``SignedHeaders.as_dict()`` and never appear in ``src/`` at all.
  Do not cite it as a reason to prefer one body form here.)
* What is NOT free is ``Content-Type``. httpx sets it on the ``json=`` path and
  not on ``content=``, while ``adcp``'s ``JwkSignerStrategy`` covers
  ``content-type`` unconditionally — so a ``sign=`` caller using ``content=``
  must pass ``headers={"Content-Type": "application/json"}`` or it signs a
  header that never ships and no receiver can rebuild the base. Content-Type is
  decided at the payload layer, which is why this seam does not inject it; see
  :func:`~src.core.security.webhook_egress.prepare_signed_request`, which
  ``setdefault``\\ s it for the legacy path.

Cost of matching the SDK's shape, recorded once so it does not have to be
rediscovered: at the injection point the seam holds the request's FULL headers,
but ``WebhookAuthStrategy.build_auth_headers`` accepts only method/url/body. The
signer therefore cannot see headers it may be covering, which is precisely why
the Content-Type obligation above lands on the caller. Reusing the SDK protocol
verbatim is still right — it is what lets ``sign=strategy.build_auth_headers``
work with no adapter — but the trade is real, and widening the callback later
means diverging from the SDK.

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

Retries wait BR-RULE-029's 1s/2s/4s plus jitter. An origin's ``Retry-After`` can
LENGTHEN that wait, never shorten it, and only up to a bounded amount — a header
is a request, not an instruction, and an unbounded one would let any counterparty
pin a worker. The value the buyer sees rides out in ``AdCPError``'s own top-level
``retry_after`` slot (clamped to the spec's [1, 3600]), not in ``details``. ``ADCP_OUTBOUND_BACKOFF_BASE_SECONDS``
shortens the base for test speed and nothing else — it cannot change the shape or
remove the jitter, it is deliberately not passed through ``tox.ini`` or either
compose file, and it must never be set in a deployment.

``send`` and ``asend`` take an optional ``field``: the request-payload path the
URL arrived on, carried onto a refusal so the buyer learns which input to fix.
It is a PASSTHROUGH, not a fourth decision — the seam sees a URL string, never a
request document, so it cannot compute the path, and the path's namespace differs
per call site. Callers pass it only for a URL that came from the caller's own
request; an operator-configured endpoint has no such path.

There is one more entry point, :func:`validate_url`, for URLs that are STORED
rather than sent — a webhook URL accepted at ingest and fetched later. It runs
the identical pre-connection policy and connects to nothing, so those call sites
have no reason to grow a second copy of address policy either. It takes the same
optional ``field``: admin ingest handlers build no AdCP envelope and omit it,
while protocol ``_impl`` ingest sites (create/update/sync accepting a buyer's
webhook URL) pass the request path so the refusal names the input to fix.

The last entry point is :func:`sleep_backoff`, for the one retry loop that
lives outside this module by design: the MCP seam owns a stateful session
transport ``send``/``asend`` cannot carry, but it reads THIS schedule instead
of recomputing one. It awaits the wait itself and returns nothing, so no call
site ever holds a number it could quietly scale.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

import httpx  # noqa: TID251 - the seam itself; the one sanctioned httpx importer (GH #1589)
from adcp.signing import (
    SSRFValidationError,
    build_async_ip_pinned_transport,
    build_ip_pinned_transport,
    resolve_and_validate_host,
)

from src.core.exceptions import AdCPBlockedUrlError, AdCPServiceUnavailableError, clamp_retry_after

logger = logging.getLogger(__name__)

# Escape hatch. Defaults OFF — a guarded posture is the default, and an
# operator has to say so out loud to leave it. The scheme requirement
# (https-only) has NO escape hatch (salesagent-e6h0): the outbound origins
# that used to need one are all TLS-fronted now (salesagent-40qh).
_ALLOW_PRIVATE_ENV = "ADCP_OUTBOUND_ALLOW_PRIVATE"


class SignAttempt(Protocol):
    """Signs ONE attempt: ``(method, url, body) -> headers to merge``.

    The seam owns retry, so a signature computed once above the loop would be
    replayed on every attempt. That is fine for a legacy HMAC (it covers body +
    timestamp, and replay inside the window verifies) and WRONG for RFC 9421,
    whose ``nonce`` a conformant receiver must reject on replay. Passing a
    callback instead of a client is what lets a signing caller keep the seam's
    pinned transport: the caller never gets something it can point elsewhere.

    KEYWORD-ONLY, structurally identical to
    ``adcp.webhook_auth.WebhookAuthStrategy.build_auth_headers``. That is not a
    style choice — it is the whole point of the parameter. A signing caller
    passes ``sign=strategy.build_auth_headers`` with no adapter; restated
    positionally, every caller would have to hand-write a shim, which is exactly
    the friction that made callers open their own client instead.
    """

    def __call__(self, *, method: str, url: str, body: bytes) -> Mapping[str, str]: ...


#: Headers a signer may not set, because they describe the FRAMING of the body
#: rather than authenticating it.
#:
#: Measured, not theorised (httpx 0.28.1 against a real origin): a signer
#: returning ``Transfer-Encoding: chunked`` alongside the ``Content-Length``
#: httpx already computed makes the origin read the chunk-size line as part of
#: the body — it received ``b'15\r\n{"event": "delive'`` where ``b'{"event":
#: "delivery"}'`` was signed, and answered 200. That is the CL.TE
#: request-smuggling shape, arrived at through a signer rather than an attacker,
#: and it breaks this seam's core promise that the bytes signed are the bytes
#: transmitted.
#:
#: Dropped rather than refused: a signer returning these is confused, not
#: hostile, and the correct request is the one httpx already framed. Refusing
#: would turn a harmless over-broad signer into a delivery outage.
_SIGNER_RESERVED_HEADERS = frozenset({"content-length", "transfer-encoding", "host"})

# Response bodies are accumulated, so an unbounded counterparty response is a
# memory-exhaustion vector. httpx applies no default limit (spec point 5).
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024

# Retry backoff. BR-RULE-029 INV-3: a retried delivery waits 1s, 2s, 4s, each
# plus jitter, so a fleet of clients retrying the same failed endpoint does not
# thunder back in lockstep. That is production's schedule, and it is decided here
# rather than at any call site.
_BACKOFF_BASE_SECONDS = 1.0

# Test-speed override for the base only — the shape (x2 per attempt) and the
# jitter are not negotiable. Deliberately absent from tox.ini pass_env and from
# both compose files: no deployed or CI environment has any business shortening
# production backoff.
_BACKOFF_BASE_ENV = "ADCP_OUTBOUND_BACKOFF_BASE_SECONDS"

# The most of a counterparty's Retry-After this seam will actually wait. The
# header is a request, not an instruction: honouring an unbounded value lets any
# origin pin a worker for an hour with one response header. Retry-After can only
# ever LENGTHEN a wait beyond BR-RULE-029 — never shorten it — and only this far.
_MAX_HONOURED_RETRY_AFTER_SECONDS = 60.0

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
    through the MRO of those subclasses. Class attributes are safe: they do
    not touch ``__init__``, and declaring them here — rather than leaving
    ``last_status``/``attempts`` as fields only ``OutboundDeliveryFailed``
    happens to set — is what makes ``exc.last_status`` a typed read on
    ``OutboundError`` instead of a ``getattr(exc, "last_status", None)`` at
    every call site that only has the base type. ``OutboundRequestBlocked``
    never overrides either, so both read as ``None`` on a refusal — which is
    the honest value: nothing was attempted, so there is no status or count.
    """

    last_status: int | None = None
    attempts: int | None = None


class OutboundRequestBlocked(OutboundError, AdCPBlockedUrlError):
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

    # Narrower than the base's ``int | None``: a delivery that reaches this
    # class was tried at least once (``__init__`` requires ``attempts: int``,
    # no default), so callers that have already caught this concrete type
    # read a plain ``int``, not ``int | None``. ``last_status`` stays inherited
    # — it is genuinely optional even here (a transport exception vs a
    # response).
    attempts: int

    # Only these two fields ride to the buyer. `details` is buyer-visible —
    # build_two_layer_error_envelope passes it straight into the adcp_error
    # payload — so nothing derived from the origin's response or from the httpx
    # error string may be added here (spec point 6).
    _DETAIL_KEYS: ClassVar[tuple[str, str]] = ("attempts", "last_status")

    def __init__(self, *, attempts: int, last_status: int | None, retry_after: int | None = None) -> None:
        super().__init__(
            _DELIVERY_FAILED_MESSAGE,
            details={"attempts": attempts, "last_status": last_status},
            retry_after=retry_after,
        )
        self.attempts = attempts
        self.last_status = last_status
        self.retry_after = retry_after


def terminal_client_error_status(exc: OutboundError) -> int | None:
    """The 4xx this seam refused to retry, or ``None``.

    "Client error, will not retry" has to be true by construction rather than by
    each call site remembering which statuses are retryable. A plain
    ``400 <= status < 500`` test looks right and is not: 429 is a 4xx this seam
    DOES retry, so that spelling reports a rate-limited endpoint — retried to
    exhaustion — as a terminal client error, and any log or classification built
    on it states the opposite of what happened.

    It lives here rather than beside the taxonomy mapper because the answer is a
    property of :data:`_RETRYABLE_STATUSES`, i.e. of this module's own retry
    policy, not of any caller's error vocabulary. Callers reading it from here
    also cannot drift from the set as it changes.

    Returns ``None`` for a refusal (no status to be terminal about) and for a
    transport failure (``last_status is None`` — the input a bare comparison
    raises ``TypeError`` on).
    """
    if not isinstance(exc, OutboundDeliveryFailed):
        return None
    status = exc.last_status
    if status is None or not (400 <= status < 500) or status in _RETRYABLE_STATUSES:
        return None
    return status


def find_wrapped_http_status_error(exc: BaseException) -> httpx.HTTPStatusError | None:
    """Walk *exc*'s cause/context chain (and any ``ExceptionGroup`` members) for a wrapped ``httpx.HTTPStatusError``.

    For a transport that does NOT go through ``send``/``asend`` — the guarded
    MCP seam (``src.core.utils.mcp_client.create_mcp_client``) hands a
    ``guarded_client_factory``-built client to fastmcp/mcp, whose own
    session/retry logic wraps failures in its own exception types, but chains
    through the real ``httpx.HTTPStatusError`` via ``raise ... from ...``. This
    lets a caller of that seam recover the same status-code-aware
    classification (429/4xx/5xx) this module's own retry loop uses, without
    importing ``httpx`` itself — this module is the one sanctioned importer
    (GH #1589).
    """
    seen: set[int] = set()
    return _find_wrapped_http_status_error(exc, seen)


def _find_wrapped_http_status_error(exc: BaseException, seen: set[int]) -> httpx.HTTPStatusError | None:
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.HTTPStatusError):
            return current
        sub_exceptions = getattr(current, "exceptions", None)
        if sub_exceptions is not None:
            for sub in sub_exceptions:
                found = _find_wrapped_http_status_error(sub, seen)
                if found is not None:
                    return found
        current = current.__cause__ or current.__context__
    return None


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


def _env_float(name: str, default: float) -> float:
    """Read a positive float env knob, falling back loudly.

    Read at CALL time for the same reason as :func:`_env_flag`.

    The value must be STRICTLY positive. Zero is rejected rather than honoured
    because "no base delay, jitter only" is not a schedule this module offers,
    and silently substituting the 1s production default for it would surprise in
    exactly the direction this seam exists to close. Every rejection is logged at
    WARNING naming the variable — an operator who cannot see which knob was
    ignored cannot fix it.
    """
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number — using %ss", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%r is not strictly positive — using %ss", name, raw, default)
        return default
    return value


def _require_tls(url: str, field: str | None = None) -> None:
    """Reject anything but https:// — unconditionally, no escape hatch (salesagent-e6h0).

    The one address-adjacent rule the seam owns: the SDK validator deliberately
    permits plain http, because it is a transport validator, not a transport
    policy.
    """
    if url.lower().startswith("https://"):
        return
    logger.warning("Outbound request refused: scheme is not https")
    raise OutboundRequestBlocked(_BLOCKED_MESSAGE, field=field)


def _blocked(exc: SSRFValidationError, field: str | None) -> OutboundRequestBlocked:
    """Translate an SDK refusal into an opaque typed refusal.

    The SDK detail is logged and never returned: ``str(exc)`` names the resolved
    IP and distinguishes "unresolvable" from "reserved".
    """
    logger.warning("Outbound request refused by address policy: %s", exc)
    return OutboundRequestBlocked(_BLOCKED_MESSAGE, field=field)


def _checked_field(field: str | None, url: str) -> str | None:
    """Refuse a ``field`` that would leak the URL, instead of trusting the caller.

    ``field`` is buyer-visible, and the whole point of the opaque refusal message
    is that a refusal discloses nothing about our network (spec point 6). A call
    site that passed the URL — or anything containing it or a scheme — would
    route around that in a field the message never touches. Documentation cannot
    stop that; this can.

    The containment check runs in the leak direction only (``url in field``,
    never ``field in url``): call sites pass fixed path constants, and the URL is
    buyer-controlled, so a buyer who embeds a constant like
    ``push_notification_config.url`` inside their own URL must get the normal
    policy verdict on that URL — not a ValueError manufactured from our guard.

    Refusing loudly rather than silently dropping the value: a call site that
    means to name a field and instead names a URL has a bug, and swallowing it
    would ship the bug with a quietly fieldless envelope.
    """
    if field is None:
        return None
    if "://" in field or url in field:
        raise ValueError(
            f"field must be a JSONPath-lite path into the request payload, not a URL or one containing it: {field!r}"
        )
    return field


def _prepare[Validated](url: str, validator: Callable[..., Validated], field: str | None = None) -> Validated:
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
    out, because its message names the resolved IP (spec point 6). ``field``, when
    the caller supplied one, rides that refusal onto both envelope layers so the
    buyer learns which input to fix; both refusal causes carry it identically, so
    it cannot become a scheme-versus-address discriminator.
    """
    field = _checked_field(field, url)
    _require_tls(url, field)
    try:
        return validator(url, allow_private=_env_flag(_ALLOW_PRIVATE_ENV))
    except SSRFValidationError as exc:
        raise _blocked(exc, field) from exc


def _should_retry_status(status: int) -> bool:
    return status in _RETRYABLE_STATUSES


def _backoff_seconds(attempt: int) -> float:
    """Seconds to wait before the attempt after ``attempt`` (1-based).

    BR-RULE-029 INV-3, in the one place both ``send`` and ``asend`` reach: the
    base doubles per attempt (1s, 2s, 4s) and each wait carries its own
    ``uniform(0, 1)`` draw. Because the schedule is computed here and nowhere
    else, no call site can migrate onto this seam and quietly keep a different
    one. Deliberately private: the one sanctioned external consumer gets
    :func:`sleep_backoff`, which performs the wait itself so no call site ever
    holds a number it could scale or replace.
    """
    base = _env_float(_BACKOFF_BASE_ENV, _BACKOFF_BASE_SECONDS)
    return base * (2 ** (attempt - 1)) + random.uniform(0, 1)


async def sleep_backoff(attempt: int) -> None:
    """Await BR-RULE-029's wait before the attempt after ``attempt`` (1-based).

    For the MCP seam (``src/core/utils/mcp_client.py``), which owns its own
    transport for protocol reasons — a stateful MCP session that ``asend``'s
    one-shot request/response cannot carry — but must not own a second copy of
    the retry schedule. Sleeping HERE rather than returning the number is the
    guard: the no-call-site-backoff detector follows same-module names only, so
    a public ``backoff_seconds()`` would let ``sleep(backoff_seconds(1))`` or a
    scaled variant drift invisibly; an awaitable that hands nothing back leaves
    a call site nothing to get wrong but the attempt index.
    """
    await asyncio.sleep(_backoff_seconds(attempt))


def retry_after_seconds(response: httpx.Response) -> float | None:
    """The origin's Retry-After in seconds, or ``None`` if it did not usably say.

    Delta-seconds only. RFC 9110 also permits an HTTP-date, but honouring one
    means trusting a counterparty's clock against ours; it is logged and treated
    as absent, which costs only the BR-RULE-029 wait we would have taken anyway.

    Deliberately UNCLAMPED. The raw value decides the WAIT (bounded separately by
    :data:`_MAX_HONOURED_RETRY_AFTER_SECONDS`); the value that rides out to the
    buyer is clamped to the spec's [1, 3600] at the point of emission. Fusing the
    two would floor every wait at one second, so an origin could not answer
    ``Retry-After: 0`` — and a test suite could not avoid sleeping for real.

    Public (not module-private): reused by
    ``src.core.helpers.mcp_seam_error_mapping`` to parse the same header off
    the ``httpx.HTTPStatusError`` a guarded MCP-seam dial surfaces, so the
    429/Retry-After parsing rule has one home regardless of which transport
    the seam used underneath.
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        logger.debug("Ignoring non-delta-seconds Retry-After: %r", raw)
        return None


def _wait_seconds(attempt: int, retry_after: float | None) -> float:
    """How long to wait before the attempt after ``attempt``.

    BR-RULE-029 is a FLOOR: this returns the geometric wait, raised to the
    origin's Retry-After when that asks for longer, and the ceiling clamps the
    RETRY-AFTER CONTRIBUTION only.

    The order matters and the obvious spelling is wrong. ``min(max(backoff,
    retry_after), CEILING)`` applies the ceiling to the whole wait, so any time
    the geometric wait exceeds the ceiling the seam would sleep LESS than the
    rule — silently, in the one module that owns that rule, and reachable through
    the public ``max_attempts`` parameter (the schedule is 1, 2, 4, 8, 16, 32,
    64s, so it crosses a 60s ceiling at seven attempts).
    """
    honoured = min(retry_after or 0.0, _MAX_HONOURED_RETRY_AFTER_SECONDS)
    return max(_backoff_seconds(attempt), honoured)


def _build_request(
    client: httpx.Client | httpx.AsyncClient,
    *,
    method: str,
    url: str,
    json_body: Any,
    params: Any,
    headers: Any,
    content: Any,
    sign: SignAttempt | None = None,
) -> httpx.Request:
    request = client.build_request(
        method.upper(),
        url,
        json=json_body,
        params=params,
        headers=headers,
        content=content,
    )
    if sign is not None:
        # ``request.content`` is what httpx will transmit, and ``request.url`` is
        # post-params — so the signer signs the exact bytes and the exact target
        # URI that go on the wire. Same invariant as the webhook egress helper:
        # signed bytes and wire bytes are one object, not two that agree.
        signed = sign(method=request.method, url=str(request.url), body=request.content)
        for name, value in signed.items():
            if name.lower() in _SIGNER_RESERVED_HEADERS:
                # See _SIGNER_RESERVED_HEADERS: letting a signer re-frame the body
                # would let it desync the bytes it just signed from the bytes the
                # receiver reads.
                logger.warning("Signer returned reserved header %r; dropped (body framing is httpx's)", name)
                continue
            request.headers[name] = value
    return request


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


def _fail(attempts: int, last_status: int | None, retry_after: float | None = None) -> OutboundDeliveryFailed:
    return OutboundDeliveryFailed(
        attempts=attempts,
        last_status=last_status,
        retry_after=clamp_retry_after(retry_after) if retry_after is not None else None,
    )


def validate_url(url: str, *, field: str | None = None) -> None:
    """Apply the seam's egress policy to a URL WITHOUT sending anything.

    For URLs that are *stored* rather than sent: a webhook or brand-manifest URL
    supplied at ingest time is persisted now and fetched later, possibly by a
    background worker, so the refusal a buyer can act on has to happen at ingest
    — long before there is a request to attach it to. A send-only seam cannot
    serve those call sites, and the alternative they reach for otherwise is a
    second, hand-written copy of address policy, which is the recurrence this
    module exists to make impossible.

    ``field`` is the same passthrough :func:`send` and :func:`asend` take — the
    request-payload path the URL arrived on, carried onto the refusal so the
    buyer learns which input to fix. Admin ingest handlers build no AdCP
    envelope and omit it; protocol ``_impl`` ingest sites pass their request
    path constant.

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
    _prepare(url, resolve_and_validate_host, field)


def guarded_async_client(
    url: str,
    *,
    headers: Any = None,
    timeout: Any = None,
    auth: Any = None,
    **client_kwargs: Any,
) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` pinned to ``url``'s validated IP, redirects refused.

    For the one library seam whose stateful client this module's one-shot
    :func:`asend` cannot carry — fastmcp's ``StreamableHttpTransport``, which
    owns a long-lived MCP session — this hands over a client that makes the SAME
    pre-connection decision :func:`asend` makes: ``adcp.signing`` resolves ``url``
    once and pins every connect to that IP (spec points 2-3), and
    ``follow_redirects=False`` refuses the 30x a counterparty uses to reach an
    address the pin never saw (point 4). ``trust_env=False`` so an ambient
    ``HTTP(S)_PROXY`` cannot route around the pin.

    It is a client BUILDER, not a send loop, precisely because the caller owns
    the request/response lifecycle the send functions own for their own callers;
    everything up to the socket is still decided here, once, through
    :func:`_prepare`. Raises :class:`OutboundRequestBlocked` before returning if
    the scheme or address is refused — the identical verdict :func:`validate_url`
    and :func:`asend` reach, because all three go through :func:`_prepare`.
    """
    transport = _prepare(url, build_async_ip_pinned_transport)
    kwargs: dict[str, Any] = {**client_kwargs}
    if headers is not None:
        kwargs["headers"] = headers
    if timeout is not None:
        kwargs["timeout"] = timeout
    if auth is not None:
        kwargs["auth"] = auth
    # The pin, the redirect refusal and the proxy bypass are the reason this
    # function exists, so they are applied LAST and are not negotiable — a caller
    # cannot pass them away. fastmcp does exactly that: it invokes the factory
    # with a hard-coded ``follow_redirects=True`` (mcp/client/streamable_http.py),
    # which would otherwise land in ``client_kwargs`` and re-open the bypass.
    kwargs.update(transport=transport, follow_redirects=False, trust_env=False)
    return httpx.AsyncClient(**kwargs)


def guarded_client_factory(url: str) -> Callable[..., httpx.AsyncClient]:
    """A ``(headers, timeout, auth) -> AsyncClient`` factory pinned to ``url``.

    The shape fastmcp's ``StreamableHttpTransport(httpx_client_factory=...)`` and
    the MCP SDK's ``create_mcp_http_client`` share. The default factory the SDK
    falls back to when none is supplied builds ``follow_redirects=True`` with no
    pin — the live redirect bypass this closes. Pinning ``url`` here, the SAME
    ``url`` the transport is constructed to dial, puts the pin on the dialed host
    by construction: there is no validate-one/dial-another gap to reopen.
    """

    def factory(headers: Any = None, timeout: Any = None, auth: Any = None, **extra: Any) -> httpx.AsyncClient:
        return guarded_async_client(url, headers=headers, timeout=timeout, auth=auth, **extra)

    return factory


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
    field: str | None = None,
    sign: SignAttempt | None = None,
) -> OutboundResult:
    """Send one outbound HTTP request through the seam.

    ``max_attempts`` counts TOTAL attempts, not retries after the first, so
    ``max_attempts=1`` is how a non-idempotent or vendor call opts out of retry.
    ``duration_seconds`` on the result is total wall time across all attempts.

    ``field`` names the request-payload path this URL arrived on, in AdCP
    JSONPath-lite (e.g. ``"property_list.agent_url"``), and rides a refusal onto
    both envelope layers so the buyer knows what to fix. Pass it ONLY when the
    URL came from the caller's request document: an operator-configured endpoint
    has no such path, and neither does a URL read back out of storage. See the
    module docstring — this is carried, not decided.

    ``sign`` is a :class:`SignAttempt` callback invoked once PER ATTEMPT, with
    the exact method, target URI and body bytes of that attempt, returning the
    headers to merge. It exists so a signing caller does not have to bring its
    own client — and therefore does not have to leave this seam's pinned
    transport — to satisfy a scheme whose signature cannot be replayed across
    retries (RFC 9421's ``nonce``). A caller signing a legacy HMAC needs none of
    this: that signature is replay-valid inside its window, so passing
    ``headers=`` once is correct and remains so.

    Two obligations on a ``sign`` caller, both spelled out in the module
    docstring: pass an explicit ``Content-Type`` if you use ``content=`` (httpx
    sets none there, and RFC 9421 signers cover it), and do not return framing
    headers — ``Content-Length``, ``Transfer-Encoding`` and ``Host`` are dropped
    with a warning, because a signer that re-frames the body can desync the
    bytes it just signed from the bytes the receiver reads.

    Raises :class:`OutboundRequestBlocked` if the scheme or the address is
    refused (before any connection is attempted), or
    :class:`OutboundDeliveryFailed` if the destination was reached but the
    request was not delivered. Both are ``OutboundError`` subclasses, so a call
    site that only logs can catch that one type.
    """
    transport = _prepare(url, build_ip_pinned_transport, field)

    started = time.monotonic()
    last_status: int | None = None
    last_retry_after: float | None = None

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
                sign=sign,
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
                last_retry_after = None
            else:
                last_status = response.status_code
                last_retry_after = retry_after_seconds(response)
                if not _should_retry_status(last_status):
                    if response.is_success:
                        return _result(response, bytes(body), attempt, started)
                    raise _fail(attempt, last_status, last_retry_after)

            if attempt < max_attempts:
                time.sleep(_wait_seconds(attempt, last_retry_after))

    raise _fail(max_attempts, last_status, last_retry_after)


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
    field: str | None = None,
    sign: SignAttempt | None = None,
) -> OutboundResult:
    """Async twin of :func:`send` — same policy, same failure modes.

    See :func:`send` for the contract, ``field`` included. The two differ only in
    ``Client``/``AsyncClient`` and ``time.sleep``/``asyncio.sleep``; every
    policy decision is a shared helper so neither path can drift from the other.
    """
    transport = _prepare(url, build_async_ip_pinned_transport, field)

    started = time.monotonic()
    last_status: int | None = None
    last_retry_after: float | None = None

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
                sign=sign,
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
                last_retry_after = None
            else:
                last_status = response.status_code
                last_retry_after = retry_after_seconds(response)
                if not _should_retry_status(last_status):
                    if response.is_success:
                        return _result(response, bytes(body), attempt, started)
                    raise _fail(attempt, last_status, last_retry_after)

            if attempt < max_attempts:
                await asyncio.sleep(_wait_seconds(attempt, last_retry_after))

    raise _fail(max_attempts, last_status, last_retry_after)

"""The single seam every outbound HTTP request in this application goes through.

**This application implements no SSRF protection, ever.** Not private-IP
classification, not a cloud-metadata blocklist, not resolve-then-check, not
redirect re-validation. Every one of those belongs to a maintained library:

* ``adcp.signing`` owns address validation, cloud-metadata blocking, and
  resolve-once + IP pinning (DNS-rebinding defence), via
  :func:`adcp.signing.resolve_and_validate_host`.
* ``httpx`` owns the response state machine — status, redirects, 1xx,
  decompression, TLS, pooling.
* ``src.core.security.egress.policy.EgressPolicy`` owns the one address/scheme
  decision neither of those makes for us — see :meth:`EgressPolicy.
  resolve_for_dial`, which every pre-connection check in this module goes
  through (imported here, not restated).
* ``src.core.security.egress.attempts.Attempts`` owns the retry SCHEDULE and
  the retry/success/terminal decision — this module drives one instance per
  call, it does not decide the policy itself.
* This module owns capping the response body and the I/O verbs (sync vs
  async client, chunked read, sleep) that differ between ``send`` and
  ``asend``.

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

``send`` and ``asend`` take an optional ``provenance: UrlProvenance`` —
:class:`CounterpartyUrl` (its ``field``, when it has one, is the request-payload
path the URL arrived on, carried onto a refusal so the buyer learns which input
to fix) or :class:`OperatorEndpoint` (a role, never a field or an address). It is
a PASSTHROUGH, not a fourth decision — the seam sees a URL string, never a
request document, so it cannot compute the path, and the path's namespace differs
per call site. Callers construct ``CounterpartyUrl`` only for a URL that came
from the caller's own request; an operator-configured endpoint has no such path.

There is one more entry point, :func:`validate_url`, for URLs that are STORED
rather than sent — a webhook URL accepted at ingest and fetched later. It runs
the identical pre-connection policy and connects to nothing, so those call sites
have no reason to grow a second copy of address policy either. It takes the same
optional ``provenance``: admin ingest handlers build no AdCP envelope and omit
it, while protocol ``_impl`` ingest sites (create/update/sync accepting a
buyer's webhook URL) construct a ``CounterpartyUrl`` naming the request path so
the refusal names the input to fix.

The last entry point is :func:`sleep_backoff`, for the one retry loop that
lives outside this module by design: the MCP seam (``call_mcp_tool``) owns a
stateful session transport ``send``/``asend`` cannot carry, but it drives the
SAME :class:`~src.core.security.egress.attempts.Attempts` instance and hands
it here for the wait rather than computing one. It awaits the wait itself and
returns nothing, so no call site ever holds a number it could quietly scale.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeGuard

import httpx  # noqa: TID251 - the seam itself; the one sanctioned httpx importer (GH #1589)
from adcp.signing import AsyncIpPinnedTransport, IpPinnedTransport

from src.core.security.egress.attempts import (
    _MAX_HONOURED_RETRY_AFTER_SECONDS,  # noqa: F401 - re-exported; test-facing facade, no remaining src consumer
    _RETRYABLE_STATUSES,  # noqa: F401 - re-exported; read as a seam attribute by tests
    Attempts,
    OutboundDeliveryFailed,  # noqa: F401 - re-exported; caught by name throughout the tree
)
from src.core.security.egress.policy import (
    EgressPolicy,
    OutboundError,
    OutboundRequestBlocked,  # noqa: F401 - re-exported; ~30 call sites import it from this module
)

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

# The retry SCHEDULE (_backoff_seconds, _wait_seconds, _RETRYABLE_STATUSES,
# _MAX_HONOURED_RETRY_AFTER_SECONDS), the retry/success/terminal decision, and
# OutboundDeliveryFailed itself now live in src.core.security.egress.attempts
# — imported above and re-exported so this seam's ~30 existing
# ``except OutboundError`` / ``except OutboundDeliveryFailed`` catchers, and
# the tests that read _RETRYABLE_STATUSES / _MAX_HONOURED_RETRY_AFTER_SECONDS
# off this module, see no change.


@dataclass(frozen=True, slots=True)
class CounterpartyUrl:
    """A URL that arrived on the counterparty's own request document.

    ``field`` is a JSONPath-lite locator into that document (e.g.
    ``"property_list.agent_url"``) when one exists, or honestly ``None`` when
    it does not (e.g. a stored creative's ``agent_url``, re-dialled later with
    no live request document to point into). ``None`` is never spelled as a
    fabricated path — possession of this type IS the "this is a counterparty
    URL" fact; the field is optional detail on top of it, not the fact itself.
    """

    field: str | None = None


@dataclass(frozen=True, slots=True)
class OperatorEndpoint:
    """An operator-configured endpoint — a registered agent, a vendor host.

    ``name`` identifies the ROLE this deployment stands behind (e.g. "the
    creative agent", "Kevel"), never an address: a refusal naming an endpoint
    the buyer did not choose would disclose network topology (AdCP 3.1.1,
    security.mdx point 6), so the constructor refuses anything that looks like
    one rather than relying on every call site to remember not to pass one.
    """

    name: str

    def __post_init__(self) -> None:
        if "://" in self.name:
            raise ValueError(f"OperatorEndpoint.name must identify a role, not a URL: {self.name!r}")


# Whose URL was refused, as a type: a counterparty-supplied URL (may name the
# request-document field it arrived on) or an operator-configured endpoint
# (may name a role, never a field or an address). Required wherever the seam
# reports outward — there is no "no opinion" default, because "no opinion" is
# exactly the provenance-by-omission this union replaces.
UrlProvenance = CounterpartyUrl | OperatorEndpoint


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
    MCP seam (``src.core.utils.mcp_client.call_mcp_tool``) hands a
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


def wire_field(provenance: UrlProvenance | None) -> str | None:
    """The buyer-visible field *provenance* contributes to a refusal, if any.

    Only :class:`CounterpartyUrl` contributes one (its ``field``, which may
    itself be ``None``); :class:`OperatorEndpoint` and bare ``None`` provenance
    always contribute none, because there is no request-document path to point a
    buyer at. Public — and the ONE place this derivation lives — because more
    than the seam itself needs it: a call site that raises its own
    ``AdCPValidationError`` at the locator a seam refusal would have carried
    (e.g. ``creative_agent_registry``) reads it from here rather than re-deriving
    whose-URL-is-this with a second ``isinstance`` check.
    """
    if isinstance(provenance, CounterpartyUrl):
        return provenance.field
    return None


def is_counterparty(provenance: UrlProvenance | None) -> TypeGuard[CounterpartyUrl]:
    """Whether *provenance* names a URL the counterparty (buyer) supplied.

    The counterpart to :func:`wire_field`, for call sites that need the
    CounterpartyUrl-vs-everything-else predicate itself rather than the field it
    carries — e.g. deciding whether a URL is eligible for a testing
    short-circuit that must never apply to a buyer-controlled destination. Kept
    here, the ONE place either derivation lives, so no caller re-implements the
    union's meaning with its own ``isinstance``. A ``TypeGuard`` so a caller that
    branches on it gets ``CounterpartyUrl`` narrowing for free, the same as an
    inline ``isinstance`` would.
    """
    return isinstance(provenance, CounterpartyUrl)


def _checked_field(provenance: UrlProvenance | None, url: str) -> str | None:
    """Derive the buyer-visible field from *provenance*, refusing one that would leak the URL.

    The derived field is buyer-visible, and the whole point of the opaque
    refusal message is that a refusal discloses nothing about our network (spec
    point 6). A call site that passed the URL — or anything containing it or a
    scheme — would route around that in a field the message never touches.
    Documentation cannot stop that; this can.

    The containment check runs in the leak direction only (``url in field``,
    never ``field in url``): call sites pass fixed path constants, and the URL is
    buyer-controlled, so a buyer who embeds a constant like
    ``push_notification_config.url`` inside their own URL must get the normal
    policy verdict on that URL — not a ValueError manufactured from our guard.

    Refusing loudly rather than silently dropping the value: a call site that
    means to name a field and instead names a URL has a bug, and swallowing it
    would ship the bug with a quietly fieldless envelope.
    """
    field = wire_field(provenance)
    if field is None:
        return None
    if "://" in field or url in field:
        raise ValueError(
            f"field must be a JSONPath-lite path into the request payload, not a URL or one containing it: {field!r}"
        )
    return field


def _sync_transport(url: str, *, field: str | None, allow_private: bool) -> IpPinnedTransport:
    """The sync pinned transport for *url*, after EgressPolicy.resolve_for_dial's verdict.

    A thin builder, not a policy decision: :meth:`EgressPolicy.resolve_for_dial`
    owns the scheme check, the single resolution and the address-policy verdict
    (including OutboundRequestBlocked's raise); this function only turns the
    resolved triple into the transport the caller asked for.
    """
    hostname, resolved_ip, _port = EgressPolicy.resolve_for_dial(url, field=field, allow_private=allow_private)
    return IpPinnedTransport(hostname=hostname, resolved_ip=resolved_ip, verify=True)


def _async_transport(url: str, *, field: str | None, allow_private: bool) -> AsyncIpPinnedTransport:
    """The async twin of :func:`_sync_transport` — see its docstring."""
    hostname, resolved_ip, _port = EgressPolicy.resolve_for_dial(url, field=field, allow_private=allow_private)
    return AsyncIpPinnedTransport(hostname=hostname, resolved_ip=resolved_ip, verify=True)


async def sleep_backoff(attempts: Attempts) -> None:
    """Await the wait BR-RULE-029 owes before *attempts*' next attempt.

    For the MCP seam (``src/core/utils/mcp_client.py``), which owns its own
    transport for protocol reasons — a stateful MCP session that ``asend``'s
    one-shot request/response cannot carry — but must not own a second copy of
    the retry schedule. Sleeping HERE rather than returning the number is the
    guard: the no-call-site-backoff detector follows same-module names (and,
    since salesagent-tbrk.2, same-module ``.wait_seconds()``-shaped attribute
    calls) only, so a public wait-returning function callable from outside
    this exempt module would let a scaled variant drift invisibly. Taking the
    WHOLE :class:`~src.core.security.egress.attempts.Attempts` instance rather
    than a bare attempt index means a call site cannot separately compute or
    hold a wait duration at all — it can only hand back the SAME instance it
    is already driving via ``next_attempt()``, so there is nothing left for it
    to get wrong.

    ``attempts.wait_seconds()`` reads the schedule from
    :mod:`src.core.security.egress.attempts`, which owns it — this facade
    still performs the wait itself, so the guarantee above is unchanged.
    """
    await asyncio.sleep(attempts.wait_seconds())


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


def validate_url(url: str, *, provenance: UrlProvenance | None = None) -> None:
    """Apply the seam's egress policy to a URL WITHOUT sending anything.

    For URLs that are *stored* rather than sent: a webhook or brand-manifest URL
    supplied at ingest time is persisted now and fetched later, possibly by a
    background worker, so the refusal a buyer can act on has to happen at ingest
    — long before there is a request to attach it to. A send-only seam cannot
    serve those call sites, and the alternative they reach for otherwise is a
    second, hand-written copy of address policy, which is the recurrence this
    module exists to make impossible.

    ``provenance`` is the same passthrough :func:`send` and :func:`asend` take —
    whose URL this is, carried onto a refusal so a :class:`CounterpartyUrl`'s
    field (when it has one) tells the buyer which input to fix, while an
    :class:`OperatorEndpoint` or ``None`` contributes nothing. Admin ingest
    handlers build no AdCP envelope and omit it; protocol ``_impl`` ingest sites
    construct a ``CounterpartyUrl`` naming their request path.

    It refuses EXACTLY what :func:`send` and :func:`asend` refuse, because all
    three go through :meth:`EgressPolicy.resolve_for_dial` and differ only in
    what they do with the resolved ``(hostname, ip, port)``; here it is
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
    field = _checked_field(provenance, url)
    EgressPolicy.resolve_for_dial(url, field=field, allow_private=_env_flag(_ALLOW_PRIVATE_ENV))


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
    :meth:`EgressPolicy.resolve_for_dial`. Raises :class:`OutboundRequestBlocked`
    before returning if the scheme or address is refused — the identical
    verdict :func:`validate_url` and :func:`asend` reach, because all three go
    through the same policy method.
    """
    transport = _async_transport(url, field=None, allow_private=_env_flag(_ALLOW_PRIVATE_ENV))
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
    provenance: UrlProvenance | None = None,
    sign: SignAttempt | None = None,
) -> OutboundResult:
    """Send one outbound HTTP request through the seam.

    ``max_attempts`` counts TOTAL attempts, not retries after the first, so
    ``max_attempts=1`` is how a non-idempotent or vendor call opts out of retry.
    ``duration_seconds`` on the result is total wall time across all attempts.

    ``provenance`` states whose URL this is. A :class:`CounterpartyUrl` may carry
    a request-payload path in AdCP JSONPath-lite (e.g.
    ``"property_list.agent_url"``), which rides a refusal onto both envelope
    layers so the buyer knows what to fix; construct one WITHOUT a field when the
    URL came from the caller's request document but there is no canonical path to
    name it by (never fabricate one). An :class:`OperatorEndpoint` or ``None``
    contributes no field. See the module docstring — this is carried, not
    decided.

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
    field = _checked_field(provenance, url)
    transport = _sync_transport(url, field=field, allow_private=_env_flag(_ALLOW_PRIVATE_ENV))

    started = time.monotonic()
    attempts = Attempts(max_attempts)

    # One transport per call, never cached: the pin is per-destination and fails
    # closed when reused for another host.
    with httpx.Client(transport=transport, timeout=timeout) as client:
        for attempt in attempts.next_attempt():
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
                            logger.warning("Outbound response exceeded the size cap; aborting read")
                            attempts.record_oversized_response(response.status_code)
                            raise attempts.failure()
                finally:
                    response.close()
            except _RETRYABLE_EXCEPTIONS as exc:
                logger.warning("Outbound attempt %d failed at the transport level: %s", attempt, exc)
                attempts.record_transport_failure(exc)
            else:
                outcome = attempts.record_response(response.status_code, retry_after_seconds(response))
                if outcome is Attempts.Outcome.SUCCESS:
                    return _result(response, bytes(body), attempt, started)
                if outcome is Attempts.Outcome.TERMINAL:
                    raise attempts.failure()

            if attempt < max_attempts:
                time.sleep(attempts.wait_seconds())

    raise attempts.failure()


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
    provenance: UrlProvenance | None = None,
    sign: SignAttempt | None = None,
) -> OutboundResult:
    """Async twin of :func:`send` — same policy, same failure modes.

    See :func:`send` for the contract, ``provenance`` included. The two differ
    only in ``Client``/``AsyncClient`` and ``time.sleep``/``asyncio.sleep``;
    every policy decision is a shared helper, driven by one Attempts
    instance, so neither path can drift from the other.
    """
    field = _checked_field(provenance, url)
    transport = _async_transport(url, field=field, allow_private=_env_flag(_ALLOW_PRIVATE_ENV))

    started = time.monotonic()
    attempts = Attempts(max_attempts)

    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        for attempt in attempts.next_attempt():
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
                            attempts.record_oversized_response(response.status_code)
                            raise attempts.failure()
                finally:
                    await response.aclose()
            except _RETRYABLE_EXCEPTIONS as exc:
                logger.warning("Outbound attempt %d failed at the transport level: %s", attempt, exc)
                attempts.record_transport_failure(exc)
            else:
                outcome = attempts.record_response(response.status_code, retry_after_seconds(response))
                if outcome is Attempts.Outcome.SUCCESS:
                    return _result(response, bytes(body), attempt, started)
                if outcome is Attempts.Outcome.TERMINAL:
                    raise attempts.failure()

            if attempt < max_attempts:
                await asyncio.sleep(attempts.wait_seconds())

    raise attempts.failure()

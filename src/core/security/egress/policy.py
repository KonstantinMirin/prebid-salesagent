"""The address/scheme policy shared by both egress verdicts.

Two verdicts exist because the seam is asked two different questions at two
different times: :func:`EgressPolicy.check_registration` is the DNS-free
verdict a webhook (or other stored) URL earns at *registration*, before there
is any request to attach a refusal to; :func:`EgressPolicy.resolve_for_dial`
is the DNS-full, IP-pinning verdict a URL earns the moment something is
actually about to dial it. Both read the SAME address predicate
(:func:`_blocked_address`) and the SAME hostname blocklist and scheme rule —
one shared value, not two independently-maintained copies, which is the
disease this module exists to make structurally impossible (salesagent-tbrk.1,
salesagent-634hc).

AdCP 3.1.1, ``building/by-layer/L1/security.mdx``: a fetcher MUST (1) reject
non-HTTPS in production, (2) reject reserved ranges — including RFC 6598
CGNAT — (6) never echo the refusal cause back to the party that supplied the
URL. :func:`resolve_for_dial` stays opaque about *why* a dial-time refusal
happened, because the resolved address is exactly what point 6 forbids
disclosing; :func:`check_registration` MAY name the class of range, because
the caller already supplied that literal information in the URL itself —
telling them "this hostname is blocked" discloses nothing they did not
already know.
"""

from __future__ import annotations

import ipaddress  # noqa: TID251 - the egress package's own address classification; the one sanctioned site (GH #1589)
import logging
from typing import NamedTuple
from urllib.parse import ParseResult, urlparse

from adcp.signing import SSRFValidationError, resolve_and_validate_host

from src.core.exceptions import AdCPBlockedUrlError, AdCPError

logger = logging.getLogger(__name__)

# The base RFC1918/loopback/link-local/multicast/reserved/unspecified ranges
# are NOT restated here — adcp.signing.resolve_and_validate_host's own flag
# check already covers them (is_private/is_loopback/is_link_local/
# is_multicast/is_reserved/is_unspecified), and _blocked_address below reuses
# exactly that same flag set rather than inventing a superset. What resolve_
# and_validate_host does NOT cover is these six ranges — CGNAT plus the five
# adcontextprotocol/adcp-client-python#974 additions — verified directly
# against the installed adcp SDK: every one of these evaluates False on every
# flag the SDK checks.
_SUPPLEMENT_NETWORKS = frozenset(
    {
        ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (RFC 6598)
        # FIXME(adcontextprotocol/adcp-client-python#974): drop this whole
        # frozenset (except the CGNAT entry above) once we adopt a release
        # that carries these ranges upstream.
        ipaddress.ip_network("192.88.99.0/24"),  # 6to4 relay anycast (RFC 7526)
        ipaddress.ip_network("192.31.196.0/24"),  # AS112-v4 (RFC 7535)
        ipaddress.ip_network("192.52.193.0/24"),  # AMT (RFC 7450)
        ipaddress.ip_network("192.175.48.0/24"),  # AS112 direct (RFC 7534)
        ipaddress.ip_network("2001:20::/28"),  # ORCHIDv2 (RFC 7343)
    }
)

# Blocked hostnames (cloud metadata services, localhost aliases, Docker-internal
# hostnames) — moved verbatim from the deleted url_validator.py.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "169.254.169.254",
        "metadata",
        "instance-data",
        "host.docker.internal",
        "gateway.docker.internal",
        "docker.host.internal",
    }
)

# One fixed, non-disclosing reason for every REGISTRATION address-cause
# refusal — no CIDR, no resolved address (spec point 6). Distinct from
# _BLOCKED_MESSAGE (dial-time): registration already holds the literal URL
# the caller supplied, so naming the class of range discloses nothing new;
# dial-time would be disclosing a RESOLVED address the caller never had.
_RESTRICTED_RANGE_MESSAGE = "URL resolves to a restricted range."

# Spec point 6: one fixed message for every DIAL-time refusal, whatever the
# real cause. The SDK's own text says "resolved IP <IP> is in a reserved
# range" versus "cannot resolve host '<host>'" — echoing either back hands
# the party that supplied the URL both the resolved address and whether the
# name exists, which is an internal host and port scanner. This message never
# interpolates anything.
_BLOCKED_MESSAGE = "Outbound request to the supplied URL was refused by egress policy."


class PinnedHost(NamedTuple):
    """The resolved identity a pinned transport is built from.

    A bare tuple return made ``ip, hostname = ...`` type-check inside the
    function that decides what gets dialled, because hostname and IP are both
    ``str``. Naming the fields is only half the fix — a NamedTuple still unpacks
    positionally — so the two transport builders read it by ATTRIBUTE.

    Carries only what a caller consumes. The SDK's ``resolve_and_validate_host``
    also returns the port, but no reader of this type has ever used it and
    ``IpPinnedTransport`` takes no port, so it is dropped at the construction
    site below rather than projected here for nobody.
    """

    hostname: str
    resolved_ip: str


class OutboundError(Exception):
    """Marker base for every failure the outbound egress seam raises — NEVER
    raised directly.

    It exists so a call site that only logs can write one ``except``. It is
    deliberately *not* an ``AdCPError``: raising it directly would degrade to
    a bare INTERNAL_ERROR at a transport boundary and would be invisible to
    the error-taxonomy guards that walk ``AdCPError.iter_concrete_subclasses()``.
    Raise :class:`OutboundRequestBlocked` (defined here) or
    ``OutboundDeliveryFailed`` (``src/core/security/egress/attempts.py`` — a
    delivery outcome tied to the retry schedule, not an address-policy
    verdict, so it lives beside :class:`~src.core.security.egress.attempts.
    Attempts`) instead.

    Lives here (not in ``outbound_http.py``) because :func:`resolve_for_dial`
    must raise :class:`OutboundRequestBlocked` directly, and ``outbound_http``
    re-exports both names unchanged so none of this seam's ~30 existing
    catchers (``except OutboundError`` / ``except OutboundRequestBlocked``)
    notice the move.

    It defines no ``__init__`` on purpose — one would shadow ``AdCPError``'s
    through the MRO of ``OutboundRequestBlocked``. Class attributes are safe:
    they do not touch ``__init__``, and declaring them here is what makes
    ``exc.http_status`` a typed read on ``OutboundError`` instead of a
    ``getattr(exc, "http_status", None)`` at every call site that only has
    the base type. ``OutboundRequestBlocked`` never overrides either, so both
    read as ``None`` on a refusal — the honest value: nothing was attempted,
    so there is no status or count.
    """

    http_status: int | None = None
    attempts: int | None = None


class OutboundRequestBlocked(OutboundError, AdCPBlockedUrlError):
    """The URL was refused before any connection was attempted.

    Scheme or address policy said no. Terminal — never retried, because
    nothing about the destination will change on a second look.
    """


def _blocked_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """One address predicate, applied identically by both verdicts.

    The flag half — ``is_private``/``is_loopback``/``is_link_local``/
    ``is_multicast``/``is_reserved``/``is_unspecified`` — mirrors
    ``adcp.signing.resolve_and_validate_host``'s own rejection set exactly,
    not a superset invented here. That equivalence is what makes
    "registration-verdict == dial-verdict" true by construction: on the dial
    path this half is redundant with the SDK's own check (harmless); on the
    registration path — DNS-free, so it never reaches the SDK — it is the
    only thing that still refuses a literal ``10.0.0.1`` or ``127.0.0.1``.
    """
    return (
        any(ip in network for network in _SUPPLEMENT_NETWORKS)
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _scheme_error(parsed: ParseResult) -> str | None:
    """HTTPS is required, unconditionally — no escape hatch (salesagent-e6h0).

    One spelling for the rule that used to live three times:
    ``outbound_http._require_tls``, ``url_validator._scheme_error`` (with a
    now-dead ``require_https=False`` branch — the seam has required https
    unconditionally since salesagent-e6h0 deleted its own hatch, and
    registration has required it unconditionally since the same change), and
    ``webhook_validator.WebhookURLValidator._require_https`` (a bare
    ``return True``).
    """
    if parsed.scheme != "https":
        return f"URL must use HTTPS scheme, got '{parsed.scheme}'"
    return None


def _is_rescuable_loopback(url: str) -> bool:
    """True when *url* names ``localhost`` or a literal loopback IP.

    The ``ADCP_TESTING`` localhost/loopback allowance
    :func:`EgressPolicy.check_registration` applies via its
    ``allow_loopback`` parameter — a narrow POST-CHECK rescue over the
    hostname and literal-IP refusal branches, never a flag threaded into
    :func:`_blocked_address` itself (that would also rescue every supplement
    range and every base RFC1918 address at registration, not just loopback).

    Must NOT rescue a scheme refusal: checked first, unconditionally, in
    :func:`EgressPolicy.check_registration` — salesagent-e6h0 deleted the
    scheme hatch entirely, so a plain ``http://`` URL is never rescued
    regardless of ``ADCP_TESTING``.
    """
    parsed = urlparse(url)
    if _scheme_error(parsed):
        return False
    hostname = parsed.hostname
    if hostname is None:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _registration_error(url: str) -> str | None:
    """The registration-time refusal reason for *url*, or ``None`` if accepted.

    DNS-free: an unresolvable-but-public hostname is accepted here and
    re-checked with DNS when :func:`resolve_for_dial` actually dials it —
    see the module docstring's point-6 rationale for why registration may
    name the class of range while dial-time cannot.
    """
    parsed = urlparse(url)
    scheme_err = _scheme_error(parsed)
    if scheme_err:
        return scheme_err

    hostname = parsed.hostname
    if not hostname:
        return "URL must have a valid hostname"

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return f"URL hostname '{hostname}' is blocked (internal/private)"

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Not a literal IP -- a hostname that resolves (or fails to) is a
        # dial-time question, not a registration-time one.
        return None

    if _blocked_address(literal_ip):
        return _RESTRICTED_RANGE_MESSAGE
    return None


class EgressPolicy:
    """The two egress verdicts, sharing one address predicate.

    Neither method is stateful — both are plain functions spelled as
    staticmethods so callers read ``EgressPolicy.check_registration(...)`` /
    ``EgressPolicy.resolve_for_dial(...)`` as the two verdicts of one policy
    object, matching the plan's own framing, without construction ceremony
    neither verdict needs.
    """

    @staticmethod
    def check_registration(url: str, *, allow_loopback: bool = False) -> None:
        """DNS-free registration-time verdict.

        Absorbs ``WebhookURLValidator.validate_webhook_url_registration``'s
        SSRF-computation logic (that class survives as a thin ``(bool, str)``
        wrapper over this method — see ``webhook_validator.py``) plus
        ``url_validator.check_url_ssrf``'s ``resolve_dns=False`` path (the
        ``resolve_dns=True`` branch was dead code — one production caller,
        always ``resolve_dns=False`` — and is dropped, not ported).

        ``allow_loopback`` is the ``ADCP_TESTING`` localhost/loopback
        allowance, threaded in as an explicit parameter rather than read from
        the environment here — the caller (``webhook_validator._adcp_testing``)
        owns that read, this method only owns what to do with the answer.

        Raises :class:`~src.core.exceptions.AdCPBlockedUrlError` on refusal.
        """
        try:
            error = _registration_error(url)
        except AdCPError:
            raise
        except ValueError as exc:
            # ValueError, not Exception, and a FIXED sentence rather than the
            # exception's text. urlsplit raises ValueError for a malformed URL
            # ("Invalid IPv6 URL" for "https://[oops/hook"), and interpolating
            # that put stdlib phrasing this module did not author into a
            # buyer-facing refusal. Anything that is NOT a ValueError is not a
            # malformed URL and has no business being reported as one -- it now
            # escapes loudly instead of being relabelled.
            raise AdCPBlockedUrlError("URL could not be parsed") from exc
        if error is None:
            return
        if allow_loopback and _is_rescuable_loopback(url):
            return
        raise AdCPBlockedUrlError(error)

    @staticmethod
    def resolve_for_dial(url: str, *, field: str | None = None, allow_private: bool = False) -> PinnedHost:
        """Dial-time verdict: DNS-full, single resolution, refusal-checked.

        Runs the scheme check, then ONE ``resolve_and_validate_host`` call —
        the single resolution :class:`adcp.signing.IpPinnedTransport` pins
        subsequent connects to, closing the DNS-rebinding TOCTOU a second
        resolution would reopen — then checks the resolved IP against the
        shared :func:`_blocked_address` predicate. That last check is what
        closes salesagent-634hc: the SDK call alone does not know about the
        six supplement ranges.

        Returns a :class:`PinnedHost` so a caller building a pinned transport
        does not resolve a second time, and reads the two same-typed strings by
        name rather than by position; :func:`validate_url` (which sends nothing)
        discards it.

        Raises :class:`OutboundRequestBlocked` — never lets
        ``SSRFValidationError`` out, because its message names the resolved
        IP (spec point 6). Opaque :data:`_BLOCKED_MESSAGE` regardless of
        cause, unlike :meth:`check_registration`, which may name the class of
        range because the caller already supplied that literal information.
        """
        if _scheme_error(urlparse(url)) is not None:
            logger.warning("Outbound request refused: scheme is not https")
            raise OutboundRequestBlocked(_BLOCKED_MESSAGE, field=field)

        try:
            hostname, ip, _port = resolve_and_validate_host(url, allow_private=allow_private)
        except SSRFValidationError as exc:
            logger.warning("Outbound request refused by address policy: %s", exc)
            raise OutboundRequestBlocked(_BLOCKED_MESSAGE, field=field) from exc

        if not allow_private and _blocked_address(ipaddress.ip_address(ip)):
            logger.warning("Outbound request refused by address policy: matched the supplement range set")
            raise OutboundRequestBlocked(_BLOCKED_MESSAGE, field=field)

        return PinnedHost(hostname=hostname, resolved_ip=ip)

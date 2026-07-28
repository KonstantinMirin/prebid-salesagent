"""The URL-canonicalization seam: the SDK's algorithm plus the spec's rejection set.

#1291 B3 (``salesagent-z6nr.14``). This module is DELIBERATELY THIN. It delegates
every canonical form to :mod:`adcp.signing.canonical` and adds exactly one thing the
SDK does not do: it REFUSES the authority shapes the spec enumerates as malformed,
with the spec's own error code.

Why it must stay thin
---------------------
Two canonicalizers in one verify path is the precise divergence this whole feature
exists to prevent — a signer and a verifier that each compute ``@target-uri`` their
own way agree only by luck, and the disagreement is silent until a production interop
bug surfaces. So this module NEVER re-derives ``@target-uri`` or ``@authority``: it
gates, then hands the string to the SDK verbatim. If a canonical form here is wrong,
the fix belongs upstream (SDK divergence #6, filed), not in a local re-implementation.

What the gate covers, and where each rule is grounded
-----------------------------------------------------
``adcontextprotocol/adcp@v3.1.1:dist/docs/3.1.0/reference/url-canonicalization.mdx``
is the authoritative algorithm — security.mdx §"@target-uri canonicalization" defers
to it explicitly. Two of its eight steps carry MUST-reject rules that
``adcp==6.6.0`` does not implement:

* **step 2** — "A host containing raw non-ASCII bytes that has not been
  ToASCII-normalized by the producer MUST be rejected by the comparer — receivers do
  not silently re-normalize", and "IPv6 zone identifiers (RFC 6874) MUST be
  rejected ... MUST reject any URL containing ``%25`` inside ``[...]``".
* **step 3** — "The following authority shapes are malformed and MUST be rejected —
  producers MUST NOT emit them, comparers MUST reject them": userinfo but no host,
  no host at all (``https:///p``, ``https://:443/p``), a bracketed host missing its
  closing bracket, and a bare IPv6 address outside brackets.

The error code
--------------
``request_target_uri_malformed`` — the string ``canonicalization.json``'s six
``reject: true`` cases grade byte-for-byte, and the one the same page names ("Malformed
authorities are rejected with ``request_target_uri_malformed`` on the signing path").
It is ABSENT from ``adcp==6.6.0`` (SDK divergence #7), which is why it is defined here,
per divergence #2's own instruction that we emit such codes from our own layer.

**It is NOT the same code as the wire-header rejection.** Request vector
``negative/026`` (non-ASCII ``Host`` on a signed request) legitimately expects
``request_signature_header_malformed`` — a verifier-checklist step-1 rejection. The two
are kept apart on purpose. What they SHARE is the predicate, not the code:
:func:`malformed_authority_reason` is the single source of the rule, called from here
with the canonicalization code and from
:func:`~src.core.signing.request_verifier_middleware._strict_header_precheck` with the
checklist code. One rule, two graded artifacts.

Note also that the vector README's worked example is STALE on this point — it shows the
reject cases expecting ``request_signature_header_malformed``. The shipped DATA wins;
do not "correct" the code from the prose.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from adcp.signing.canonical import canonicalize_authority as _sdk_canonicalize_authority
from adcp.signing.canonical import canonicalize_target_uri as _sdk_canonicalize_target_uri
from adcp.signing.errors import SignatureVerificationError

#: SDK divergence #7 — graded by shipped conformance data, undefined by ``adcp==6.6.0``.
REQUEST_TARGET_URI_MALFORMED = "request_target_uri_malformed"


def malformed_authority_reason(authority: str) -> str | None:
    """Why *authority* is malformed per url-canonicalization.mdx steps 2-3, or ``None``.

    A REASON rather than a bool, so every caller's rejection message names the rule that
    fired instead of restating "malformed". *authority* is the raw netloc as received —
    from a URL's ``netloc`` here, from the as-received ``Host`` header at the verifier
    boundary; the rule is identical on both and must not be written twice.
    """
    host = authority.rsplit("@", 1)[-1]  # step 3: strip userinfo before judging the host
    if not host:
        return "the authority carries no host (empty, or userinfo/port with nothing before it)"
    if host.startswith("["):
        return _bracketed_host_reason(host)
    if host.count(":") > 1:
        return "an IPv6 address outside brackets is ambiguous with a port and is malformed"
    name = host.split(":", 1)[0]
    if not name:
        return "the authority carries a port but no host"
    if not name.isascii():
        # Step 2. The A-label MAPPING is the producer's job; a comparer that
        # re-normalized would pick one of several legitimate UTS-46 outcomes and
        # disagree with whoever signed.
        return "the host carries raw non-ASCII bytes and was not ToASCII-normalized by the producer"
    return None


def _bracketed_host_reason(host: str) -> str | None:
    """Step 2's two IPv6-literal rejections."""
    end = host.find("]")
    if end < 0:
        return "a bracketed IPv6 host missing its closing bracket is malformed"
    if "%" in host[1:end]:
        return "an IPv6 zone identifier (RFC 6874) is node-local and MUST be rejected in signed URLs"
    return None


def reject_malformed_target(url: str) -> None:
    """Raise unless *url*'s authority is one the spec permits a comparer to accept.

    The whole of this module's added behavior. Everything else delegates.
    """
    try:
        authority = urlsplit(url).netloc
    except ValueError as exc:
        # ``urlsplit`` already refuses SOME shapes (an unterminated IPv6 literal) — but
        # with a bare ``ValueError``, which carries none of the graded code. Normalizing
        # it here is why the conformance case cannot pass on the wrong exception.
        raise _malformed(url, f"the authority is unparseable as a URI ({exc})") from exc
    reason = malformed_authority_reason(authority)
    if reason is not None:
        raise _malformed(url, reason)


def canonical_target_uri(url: str) -> str:
    """The ``@target-uri`` derived component — gated, then the SDK's, verbatim."""
    reject_malformed_target(url)
    return _sdk_canonicalize_target_uri(url)


def canonical_authority(url: str) -> str:
    """The ``@authority`` derived component — gated, then the SDK's, verbatim."""
    reject_malformed_target(url)
    return _sdk_canonicalize_authority(url)


def _malformed(url: str, reason: str) -> SignatureVerificationError:
    """The one typed rejection this module raises.

    ``step`` is deliberately left unset: these are canonicalization-ALGORITHM steps
    (url-canonicalization.mdx 1-8), not verifier-CHECKLIST steps (security.mdx 1-15),
    and putting an algorithm step number in a field the checklist owns would be read as
    the wrong one. The graded artifact is the code.
    """
    return SignatureVerificationError(REQUEST_TARGET_URI_MALFORMED, message=f"{reason}: {url!r}")

"""The RFC 9421 transport error taxonomy, as codes this seller can put on the wire.

AdCP 3.1.1 ``security.mdx`` § Transport error taxonomy:

    Stable codes returned in ``WWW-Authenticate: Signature error="<code>"`` on 401, and
    surfaced by SDK verifiers as typed errors.

and § ``WWW-Authenticate`` format:

    Verifiers MUST emit ``WWW-Authenticate: Signature error="<code>"`` with no ``realm``
    parameter and no other parameters.

WHY THEY ARE IN ``CODE_TABLE`` AT ALL
-------------------------------------
Before #1721 the verifier was an ASGI middleware that SENT its own bodyless 401 with the
challenge attached, so the code never had to be an AdCP error code. On #1721's boundary a
refusal is an identity failure raised inside ``_resolve_identity``: ``invoke_tool`` catches
it, ``failure_response`` renders it, and ``AuthChallengeResponder`` — the ONE renderer —
lifts it to 401 and writes the challenge from the code it reads off the FINISHED body. So
the specific code has to survive into the envelope, because the renderer has nothing else
to read. A generic ``AUTH_INVALID`` would pass our tests and fail conformance:
``dist/compliance/3.1.1/universal/signed-requests.yaml`` grades the challenge string
byte-for-byte.

That is legal, and the spec says so directly: ``core/error.json`` types ``error.code`` as a
wire string rather than a closed enum, the published codes are documentary, senders MAY
emit codes outside that set, and receivers MUST decode an unknown one by reading
``error.recovery``. ``recovery`` is the part that must stay inside its three values, and
:data:`SIGNATURE_CODE_TABLE` is where that is decided.

DERIVED FROM THE SDK'S OWN TAXONOMY, NOT RE-LISTED
---------------------------------------------------
The 28 members come from ``adcp.signing.errors.REQUEST_TO_WEBHOOK_CODE`` (27 of them), which is the
table the SDK's verifier raises from. A transcribed copy would be a second source for a
string the spec grades byte-for-byte, and it would drift the first time the SDK's
taxonomy grew — silently, as an unclassified code reaching ``CodeEntry`` construction.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from adcp.signing.errors import REQUEST_TO_WEBHOOK_CODE

from src.core.errors._entry import CodeEntry, Recovery
from src.core.signing.canonical import REQUEST_TARGET_URI_MALFORMED, WEBHOOK_TARGET_URI_MALFORMED

#: The SDK's retag table plus the ONE row it omits at ``adcp==6.6.0``.
#:
#: ``REQUEST_TO_WEBHOOK_CODE`` maps each request-profile code to its webhook-profile twin,
#: and it is missing ``request_target_uri_malformed`` -> ``webhook_target_uri_malformed``
#: (upstream fix: adcp-client-python PR #987 / fbab8f44). Merged here rather than
#: transcribed, so the other 27 rows still come from the SDK and the local addition
#: disappears by itself when the pin advances past the fix.
_TAXONOMY: Final = {**REQUEST_TO_WEBHOOK_CODE, REQUEST_TARGET_URI_MALFORMED: WEBHOOK_TARGET_URI_MALFORMED}

__all__ = ["SIGNATURE_CODE_TABLE", "SignatureErrorCode", "challenge_for"]

if TYPE_CHECKING:
    # The MEMBERS are generated, so no static checker can know their names -- and this enum
    # is a member of the ``ErrorCodeT`` union, which has to be usable as an annotation in
    # sixty places. A functional-API call assigned at module level is a VARIABLE to mypy, and
    # a variable is not valid as a type; suppressing that would be a silencing comment the
    # repo's ratchet counts, rightly, as a claim nobody checks.
    #
    # So: a member-less declaration for the checker, the generated one at runtime. Nothing in
    # the tree names a member by attribute, which is what makes the erasure free -- production
    # resolves a code through ``CODE_BY_VALUE[wire_string]``, because what it holds IS a wire
    # string (off a ``SignatureVerificationError``, or off a finished response body), and the
    # 28 attribute names would only ever be a second spelling of those strings.
    class SignatureErrorCode(StrEnum): ...

else:
    #: Every request-family signature code. The member NAME is the upper-cased code and the
    #: VALUE is the wire string, which is the one that matters: it is what reaches
    #: ``error.code`` and the ``WWW-Authenticate`` challenge.
    SignatureErrorCode = StrEnum("SignatureErrorCode", {code.upper(): code for code in sorted(_TAXONOMY)})


#: Codes the BUYER can act on by changing the request and sending it again. Read as
#: suffixes off the taxonomy rather than listed as whole codes, so a new sibling the SDK
#: adds (``request_signature_components_incomplete`` joining
#: ``request_signature_covered_components_invalid``) lands in the right class on arrival.
_CORRECTABLE_MARKERS: Final = ("_required", "_malformed", "_incomplete", "_invalid_components", "_not_allowed")

#: Codes whose cause is somebody else's availability, so the SAME request may succeed
#: later. Everything the discovery walk could not reach, plus a revocation list that has
#: aged out.
_TRANSIENT_MARKERS: Final = ("_unreachable", "_unavailable", "_stale")


def _recovery_for(code: str) -> Recovery:
    """How a buyer should react to *code*.

    Three classes, and the default is the strict one. A signature that was PRESENTED and
    refused on its cryptographic merits — invalid, replayed, expired, key unknown, key
    origin mismatched — arrives identically on every retry, so it is terminal: security.mdx
    § Retry semantics states exactly this ("the signature bytes and request context arrive
    identically on every retry, so every retry fails identically"), and a buyer that
    auto-retried a terminal refusal would turn one misconfiguration into a loop.

    ``request_signature_required`` is the one that is genuinely correctable, and it is the
    reason the classes are read off markers rather than defaulted wholesale: it is what a
    buyer gets for not signing at all, and "sign the request and send it again" is a
    complete instruction.
    """
    if any(marker in code for marker in _TRANSIENT_MARKERS):
        return Recovery.TRANSIENT
    if any(code.endswith(marker) for marker in _CORRECTABLE_MARKERS):
        return Recovery.CORRECTABLE
    return Recovery.TERMINAL


#: What a buyer is TOLD, per recovery class. One sentence each rather than 28, because the
#: distinguishing information is the CODE — which is on the wire, twice (``error.code`` and
#: the challenge) — and because a buyer-facing message must not narrate which checklist step
#: refused: AdCP 3.1.1 ``transport-errors.mdx`` § Security Considerations forbids putting
#: internal detail in a client-facing field, and "your nonce was already claimed" is a
#: verifier-internal fact an unauthenticated caller should not be able to probe for.
_TEXT: Final[dict[Recovery, tuple[str, str]]] = {
    Recovery.CORRECTABLE: (
        "The request signature was missing or malformed",
        "Sign the request per RFC 9421 as this agent's request_signing capability describes, and send it again",
    ),
    Recovery.TRANSIENT: (
        "This agent could not reach the documents that establish the signer's keys",
        "Retry with backoff; if it persists, check that your brand.json and JWKS are reachable",
    ),
    Recovery.TERMINAL: (
        "The request signature was rejected",
        "Do not retry unchanged; check the named code, then rotate or re-register the signing key",
    ),
}

#: Every signature code, mapped to what a buyer gets with it. Merged into ``CODE_TABLE``.
#:
#: ``status`` is 401 for all of them, from the taxonomy's own first sentence ("returned in
#: ``WWW-Authenticate: Signature error="<code>"`` on 401"). It has to agree with what
#: ``AuthChallengeResponder`` writes, and it does, because both are that one number.
SIGNATURE_CODE_TABLE: Final = MappingProxyType(
    {
        member: CodeEntry(
            recovery=_recovery_for(member.value),
            suggestion=_TEXT[_recovery_for(member.value)][1],
            message=_TEXT[_recovery_for(member.value)][0],
            status=401,
        )
        for member in SignatureErrorCode
    }
)


def challenge_for(code: str) -> str:
    """The ``WWW-Authenticate`` value for a signature refusal.

    THE one expression of the string the compliance vectors grade byte-for-byte. It is the
    SDK's ``unauthorized_response_headers`` reduced to its f-string, because the renderer
    that needs it holds a CODE read off a finished response body and not the exception the
    SDK's helper takes. ``tests/unit/test_signature_challenge_string.py`` pins this against
    that helper for all 28 codes, so the SDK stays the cross-check.

    No ``realm`` and no other parameters, per the pin.
    """
    return f'Signature error="{code}"'

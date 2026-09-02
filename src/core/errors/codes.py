"""The one table every buyer-facing error resolves against.

An error code is a label. This module maps each label to the four things a
buyer needs with it: how to recover, what to do about it, what happened, and
the HTTP status the failure is signalled with. Nothing else in the codebase
decides those four per raise site.

The 92 codes AdCP publishes are LOADED from the pinned schema bundle inside the
installed ``adcp`` wheel -- ``enums/error-code.json``, whose ``enumMetadata``
block the spec marks normative ("SDKs MUST consume this block instead of parsing
'Recovery: X' from enumDescriptions prose"). A loaded table cannot drift from the
file it came from, so it needs no guard checking that it hasn't. A transcribed
one would.

``recovery`` and ``suggestion`` come from that file and nowhere else. A message
comes from the first of three sources that has one: authored below, then the
SDK's ``STANDARD_ERROR_CODES``, then the file's own ``enumDescriptions`` prose.
The middle source is the one thing here not read from the pin, and it is
deliberate rather than tidy: the SDK carries a message for 37 published codes and
those 37 are what this seller sends today, so dropping it would rewrite 37 live
buyer-facing strings. The cost is that an ``adcp`` bump can change those 37
without the pinned schema changing. Everywhere else in this codebase the SDK is
treated as a cross-check rather than the authority: the pinned enumMetadata says
"SDKs MUST consume this block ... the recovery classification embedded in that prose
is normative and MUST match the value here", and where the shipped SDK values
disagreed with the pin it was the SDK that was drifting. So if the two ever disagree
about a message, the file wins and the SDK entry is the bug.

The platform codes in :class:`AppErrorCode` are this seller's own. The spec's
vocabulary is open by design -- ``core/error.json`` (AdCP 3.1.1): ``error.code``
is a wire-typed string rather than a closed enum, the published codes are
documentary, senders MAY emit codes outside that set, and receivers MUST decode
unknown ones by reading ``error.recovery``. So a code outside the 92 is legal,
and ``recovery`` is the part that must stay inside its three values.

Loading happens at import, because deferring it buys nothing. It is one bounded
read of one file shipped inside a package the process has already imported, and
the path is package-relative -- derived from ``importlib.resources``, not the
working directory -- so importability does not depend on where the process was
started or which uid started it. Making it lazy would add a cache, a module
``__getattr__`` and a ``TYPE_CHECKING`` declaration to move that read a few
microseconds later.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from types import MappingProxyType
from typing import Final

from adcp import get_adcp_spec_version
from adcp.server.helpers import STANDARD_ERROR_CODES
from adcp.types import ErrorCode
from adcp.validation.version import resolve_bundle_key

__all__ = [
    "CODE_TABLE",
    "AppErrorCode",
    "CodeEntry",
    "ErrorCodeT",
    "Recovery",
]


class Recovery(StrEnum):
    """What a buyer can do about an error.

    Closed at three values by the wire schema, and the one field a receiver is
    required to read when it meets a code it does not know.
    """

    CORRECTABLE = "correctable"
    TRANSIENT = "transient"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class CodeEntry:
    """Everything a code resolves to. Frozen: the table is a fact, not state.

    Refuses an empty ``suggestion`` or ``message`` at construction: every error
    on the wire derives both from its table entry, so an empty string here would
    put a blank buyer-facing field on every raise of that code. Checking it at
    the one place entries are built — pinned-schema load and platform authorship
    alike — means no test or raise site ever needs to re-check non-emptiness.

    ``status`` is the HTTP status the failure is signalled with. It belongs to
    the CODE, not to whichever exception class happened to raise it: the pinned
    schema states the transport-level failure marker per code — ``HTTP 5xx`` for
    CONFIGURATION_ERROR and GOVERNANCE_UNAVAILABLE, ``HTTP 4xx`` for
    GOVERNANCE_DENIED and CREDENTIAL_IN_ARGS (``enums/error-code.json``,
    ``enumDescriptions``, AdCP 3.1.1) — so a class that emitted a code with a
    status from a different band would contradict the pin. The band is the
    spec's; the exact number inside it is this seller's.
    """

    recovery: Recovery
    suggestion: str
    message: str
    status: int

    def __post_init__(self) -> None:
        if not self.suggestion or not self.message:
            raise ValueError(
                f"CodeEntry requires non-empty suggestion and message, got "
                f"suggestion={self.suggestion!r}, message={self.message!r}"
            )
        if not 100 <= self.status <= 599:
            raise ValueError(f"CodeEntry.status must be an HTTP status code, got {self.status!r}")


class AppErrorCode(StrEnum):
    """Codes this platform emits that AdCP's published set does not define.

    Legal on the wire: the spec's code vocabulary is open (see the module
    docstring). Each one names a failure this seller can distinguish and a buyer
    can act on differently -- collapsing them onto a published code would throw
    that distinction away, which is the opposite of what an open vocabulary is
    for.

    No member may name a vendor. A buyer integrates with this seller, not with
    whatever ad server sits behind it, and a code is part of the contract: once
    ``GAM_UPDATE_FAILED`` is on the wire, swapping ad servers is a breaking
    change to every buyer parsing it. The two ad-server codes are therefore
    named for the operation that failed, not the system that failed it.

    Each member carries its own :class:`CodeEntry`, so declaring a code and
    declaring what it means are one act -- a member with no entry is a
    ``TypeError`` at class creation, not a lookup that fails later on an
    error path.

    Recovery follows the same rule the spec applies to its own codes --
    correctable when the buyer can change the request and retry, transient when
    the same request may succeed later, terminal when neither is true. Messages
    reach buyer agents, so they say what happened in the buyer's terms and never
    name an internal component.
    """

    entry: CodeEntry

    def __new__(cls, value: str, entry: CodeEntry) -> AppErrorCode:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.entry = entry
        return obj

    ACTIVATION_WORKFLOW_FAILED = (
        "ACTIVATION_WORKFLOW_FAILED",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Check the media buy's status before retrying; it may activate without further action",
            message="The media buy was created but could not be activated",
            status=502,
        ),
    )
    AD_SERVER_CREATE_FAILED = (
        "AD_SERVER_CREATE_FAILED",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; if it persists, the seller's operator must intervene",
            message="The media buy could not be created on the ad server",
            status=502,
        ),
    )
    AD_SERVER_UPDATE_FAILED = (
        "AD_SERVER_UPDATE_FAILED",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; the media buy is unchanged",
            message="The media buy could not be updated on the ad server",
            status=502,
        ),
    )
    AGENT_UNREACHABLE = (
        "AGENT_UNREACHABLE",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry to pick up the missing formats; the formats that were returned are complete and usable",
            message="A configured creative agent is unreachable; its formats were not included",
            status=502,
        ),
    )
    INTERNAL_ERROR = (
        "INTERNAL_ERROR",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; if it persists, report it to the seller's operator",
            message="The request could not be completed",
            status=500,
        ),
    )
    MEDIA_BUY_REJECTED = (
        "MEDIA_BUY_REJECTED",
        CodeEntry(
            recovery=Recovery.TERMINAL,
            suggestion="Do not retry this buy; contact the seller about the decision",
            message="The media buy was declined",
            status=422,
        ),
    )
    PARTIAL_FAILURE = (
        "PARTIAL_FAILURE",
        CodeEntry(
            recovery=Recovery.CORRECTABLE,
            suggestion="Read the per-item errors and resend only the items that failed",
            message="Some items in the request succeeded and others failed",
            status=502,
        ),
    )
    WORKFLOW_CREATION_FAILED = (
        "WORKFLOW_CREATION_FAILED",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; the request itself was accepted",
            message="The request was accepted but its approval workflow could not be started",
            status=502,
        ),
    )


#: Any code this seller can emit: AdCP's published set plus this platform's own.
#: A union rather than a subclass because a Python enum with members cannot be
#: extended -- ``class AppErrorCode(ErrorCode)`` is a TypeError at class
#: creation, not a design choice.
ErrorCodeT = ErrorCode | AppErrorCode


# ---------------------------------------------------------------------------
# The published 92: loaded, never transcribed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PublishedCode:
    """One published code as the pinned schema describes it.

    Its three fields come from two sibling blocks of the same file --
    ``enumMetadata`` carries recovery and suggestion, ``enumDescriptions`` the
    prose -- so they are joined here, at the read, rather than carried around as
    parallel dicts keyed by the same 92 codes.
    """

    recovery: Recovery
    suggestion: str
    description: str


#: Trailing "Recovery: correctable (...)" clause in an ``enumDescriptions``
#: entry. It restates ``enumMetadata.recovery`` as prose for human readers, so
#: it is redundant with :attr:`CodeEntry.recovery` and belongs nowhere near a
#: buyer-facing message.
_RECOVERY_CLAUSE: Final = re.compile(r"\s*Recovery:.*\Z", re.DOTALL)


def _load_published_codes() -> Mapping[str, _PublishedCode]:
    """Read every published code out of the pinned schema bundle.

    Reached through public API only -- ``get_adcp_spec_version`` and
    ``resolve_bundle_key`` rather than the SDK's private schema-root resolver --
    because this runs at application import and a private symbol that moves
    between SDK releases would take the application down with it.
    """
    bundle_key = resolve_bundle_key(get_adcp_spec_version())
    schema = files("adcp") / "_schemas" / bundle_key / "enums" / "error-code.json"
    document = json.loads(schema.read_text(encoding="utf-8"))
    metadata = document["enumMetadata"]
    descriptions = document["enumDescriptions"]

    published: dict[str, _PublishedCode] = {}
    for code in document["enum"]:
        if code not in metadata or code not in descriptions:
            raise RuntimeError(
                f"The pinned AdCP schema lists {code} in its enum but describes it in neither "
                f"enumMetadata nor enumDescriptions. The installed adcp wheel is inconsistent."
            )
        published[code] = _PublishedCode(
            recovery=Recovery(metadata[code]["recovery"]),
            suggestion=metadata[code]["suggestion"],
            description=descriptions[code],
        )
    return MappingProxyType(published)


def _message_from_prose(description: str) -> str:
    """Turn one ``enumDescriptions`` entry into a single-line message.

    Drops the trailing recovery clause and collapses whitespace; keeps
    everything else. Deliberately NOT a first-sentence rule: the prose is full
    of abbreviations ("e.g.", "i.e."), and splitting on them silently truncates
    a message mid-clause. Long and whole beats short and cut in half.
    """
    return " ".join(_RECOVERY_CLAUSE.sub("", description).split())


# ---------------------------------------------------------------------------
# First-party entries
# ---------------------------------------------------------------------------


#: Message overrides for published codes. Only the message: recovery and
#: suggestion for these come from the pinned schema, which is authoritative for
#: them.
#:
#: These seven are the published codes that resolve to no buyer-shippable text on
#: their own. The SDK's ``STANDARD_ERROR_CODES`` carries no message for any of
#: them, and the pinned schema's prose for them is normative implementer text
#: rather than a sentence for a buyer: the shortest of the seven is 195
#: characters and the longest, ``PERMISSION_DENIED``'s, is over 2000, all of it
#: MUST/SHOULD referencing other codes and error-details JSON paths. So they are authored here, and each one deletes itself the moment
#: the pin ships a message for it.
#:
#: There were eight until ``CREATIVE_NOT_FOUND`` was removed: the pinned prose
#: resolves it to one clean sentence unaided, which is strictly better than a
#: hand-written override that can drift from the file it duplicates.
_AUTHORED_SPEC_MESSAGES: Final[Mapping[ErrorCode, str]] = MappingProxyType(
    {
        ErrorCode.AUTH_INVALID: "Credentials were presented but rejected",
        ErrorCode.AUTH_MISSING: "No credentials were presented",
        ErrorCode.BILLING_NOT_SUPPORTED: "Billing model is not supported by this seller",
        ErrorCode.CONFIGURATION_ERROR: "Configuration error",
        ErrorCode.PERMISSION_DENIED: "Not authorized for this action",
        ErrorCode.UNSUPPORTED_PROVISIONING: "Settings-update entry matched no existing account",
        ErrorCode.VERSION_UNSUPPORTED: "Requested AdCP version is not supported",
    }
)


#: HTTP status for a published code this seller does not classify below. 500 is
#: what an unclassified code has always resolved to — it was the base exception's
#: own class default — so nothing that reaches this line changes shape. It is a
#: floor, not a judgement: none of this seller's raise sites can emit a code that
#: lands here, because every code a typed class declares is in the table below.
_UNCLASSIFIED_STATUS: Final = 500


#: The HTTP status each published code is signalled with.
#:
#: Keyed by CODE, which is the whole point. These 31 numbers were, until
#: salesagent-pssfi, 26 ``_default_status_code`` declarations spread over the
#: exception classes in ``src/core/exceptions.py`` — where a class was free to
#: redeclare its ``_code`` and keep a status inherited from a parent that meant
#: something else. ``SimulationError`` did exactly that: INVALID_REQUEST with
#: ``AdCPNotFoundError``'s 404, so a buyer's malformed simulation request was
#: answered 404, and the derived plain-``ToolError`` table resolved
#: INVALID_REQUEST to 400 or 404 depending on whether ``src.core.strategy`` had
#: been imported yet. Keyed by code, that state cannot be written down.
#:
#: The pinned schema fixes the BAND per code (see :class:`CodeEntry`); the exact
#: number is this seller's, and the choices are conventional HTTP: 4xx where the
#: buyer can change the request, 5xx where it cannot.
_HTTP_STATUS: Final[Mapping[ErrorCode, int]] = MappingProxyType(
    {
        # 400 — the request is malformed or unsupported as written.
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.VERSION_UNSUPPORTED: 400,
        # 401 / 402 / 403 — who is asking, and whether they may.
        ErrorCode.AUTH_INVALID: 401,
        ErrorCode.AUTH_MISSING: 401,
        ErrorCode.ACCOUNT_PAYMENT_REQUIRED: 402,
        ErrorCode.ACCOUNT_SUSPENDED: 403,
        ErrorCode.PERMISSION_DENIED: 403,
        ErrorCode.POLICY_VIOLATION: 403,
        # 404 — a named thing does not exist, or is not the caller's to see.
        ErrorCode.ACCOUNT_NOT_FOUND: 404,
        ErrorCode.CREATIVE_NOT_FOUND: 404,
        ErrorCode.MEDIA_BUY_NOT_FOUND: 404,
        ErrorCode.PACKAGE_NOT_FOUND: 404,
        ErrorCode.PRODUCT_NOT_FOUND: 404,
        ErrorCode.REFERENCE_NOT_FOUND: 404,
        ErrorCode.SESSION_NOT_FOUND: 404,
        # 409 — the request collides with state that already exists.
        ErrorCode.ACCOUNT_AMBIGUOUS: 409,
        ErrorCode.CONFLICT: 409,
        ErrorCode.IDEMPOTENCY_CONFLICT: 409,
        ErrorCode.IDEMPOTENCY_EXPIRED: 409,
        # 410 — the resource's own status forbids the operation.
        ErrorCode.INVALID_STATE: 410,
        # 422 — well-formed, understood, and refused on its merits.
        ErrorCode.ACCOUNT_SETUP_REQUIRED: 422,
        ErrorCode.BUDGET_EXCEEDED: 422,
        ErrorCode.BUDGET_EXHAUSTED: 422,
        ErrorCode.BUDGET_TOO_LOW: 422,
        ErrorCode.CREATIVE_REJECTED: 422,
        ErrorCode.PRODUCT_UNAVAILABLE: 422,
        ErrorCode.UNSUPPORTED_FEATURE: 422,
        # 429 — correct, but too often.
        ErrorCode.RATE_LIMITED: 429,
        # 5xx — the buyer cannot fix it. CONFIGURATION_ERROR and
        # SERVICE_UNAVAILABLE are the two the pin bands explicitly, both 5xx.
        ErrorCode.CONFIGURATION_ERROR: 500,
        # SERVICE_UNAVAILABLE is what the buyer is TOLD, so 503 is what the buyer
        # is answered — including for the adapter and MCP-client failures that
        # used to declare 502 while emitting this code. A 502 answer to a
        # "service unavailable" code told the buyer two different things about
        # one failure; the codes for an ad-server call that actually failed are
        # AD_SERVER_CREATE_FAILED / AD_SERVER_UPDATE_FAILED, which are 502 above.
        ErrorCode.SERVICE_UNAVAILABLE: 503,
    }
)


def _build_code_table() -> dict[ErrorCodeT, CodeEntry]:
    """Assemble the published codes and this platform's own into one table.

    A message comes from the first source that has one: authored here, then the
    SDK's ``STANDARD_ERROR_CODES``, then the pinned schema's own prose. Every
    code resolves to text, so no code can reach a buyer with an empty message.
    A status comes from ``_HTTP_STATUS`` or, for the published codes this seller
    never raises, from ``_UNCLASSIFIED_STATUS``.
    """
    published = _load_published_codes()
    table: dict[ErrorCodeT, CodeEntry] = {}

    # An authored override exists ONLY while neither downstream source ships a
    # buyer-usable message for its code ("each one deletes itself the moment the
    # pin ships a message for it" -- the block comment above). Enforced here, at
    # the one place the sources meet, rather than promised in prose: an adcp
    # bump that adds an SDK message for an overridden code fails the import,
    # forcing the override's deletion instead of leaving a silent divergence
    # between the override and the message the SDK now carries.
    stale_overrides = sorted(
        code.value for code in _AUTHORED_SPEC_MESSAGES if STANDARD_ERROR_CODES.get(code.value, {}).get("message")
    )
    if stale_overrides:
        raise RuntimeError(
            f"_AUTHORED_SPEC_MESSAGES overrides {stale_overrides}, but the installed adcp SDK now "
            "ships a message for them. Delete the stale override(s) -- or, if the SDK's sentence is "
            "wrong for buyers, record why the override stays."
        )

    for code in ErrorCode:
        spec = published[code.value]
        table[code] = CodeEntry(
            recovery=spec.recovery,
            suggestion=spec.suggestion,
            message=(
                _AUTHORED_SPEC_MESSAGES.get(code)
                or STANDARD_ERROR_CODES.get(code.value, {}).get("message")
                or _message_from_prose(spec.description)
            ),
            status=_HTTP_STATUS.get(code, _UNCLASSIFIED_STATUS),
        )

    # Each member carries its own entry, so there is nothing to reconcile: a code
    # without one cannot be declared.
    table.update({member: member.entry for member in AppErrorCode})

    return table


#: Every code this seller can emit, mapped to what a buyer gets with it.
CODE_TABLE: Final[Mapping[ErrorCodeT, CodeEntry]] = MappingProxyType(_build_code_table())

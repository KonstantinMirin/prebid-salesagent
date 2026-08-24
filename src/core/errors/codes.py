"""The one table every buyer-facing error resolves against.

An error code is a label. This module maps each label to the three things a
buyer needs with it: how to recover, what to do about it, and what happened.
Nothing else in the codebase decides those three per raise site.

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
    """

    recovery: Recovery
    suggestion: str
    message: str

    def __post_init__(self) -> None:
        if not self.suggestion or not self.message:
            raise ValueError(
                f"CodeEntry requires non-empty suggestion and message, got "
                f"suggestion={self.suggestion!r}, message={self.message!r}"
            )


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
        ),
    )
    AD_SERVER_CREATE_FAILED = (
        "AD_SERVER_CREATE_FAILED",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; if it persists, the seller's operator must intervene",
            message="The media buy could not be created on the ad server",
        ),
    )
    AD_SERVER_UPDATE_FAILED = (
        "AD_SERVER_UPDATE_FAILED",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; the media buy is unchanged",
            message="The media buy could not be updated on the ad server",
        ),
    )
    AGENT_UNREACHABLE = (
        "AGENT_UNREACHABLE",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry to pick up the missing formats; the formats that were returned are complete and usable",
            message="A configured creative agent is unreachable; its formats were not included",
        ),
    )
    INTERNAL_ERROR = (
        "INTERNAL_ERROR",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; if it persists, report it to the seller's operator",
            message="The request could not be completed",
        ),
    )
    MEDIA_BUY_REJECTED = (
        "MEDIA_BUY_REJECTED",
        CodeEntry(
            recovery=Recovery.TERMINAL,
            suggestion="Do not retry this buy; contact the seller about the decision",
            message="The media buy was declined",
        ),
    )
    PARTIAL_FAILURE = (
        "PARTIAL_FAILURE",
        CodeEntry(
            recovery=Recovery.CORRECTABLE,
            suggestion="Read the per-item errors and resend only the items that failed",
            message="Some items in the request succeeded and others failed",
        ),
    )
    WORKFLOW_CREATION_FAILED = (
        "WORKFLOW_CREATION_FAILED",
        CodeEntry(
            recovery=Recovery.TRANSIENT,
            suggestion="Retry with backoff; the request itself was accepted",
            message="The request was accepted but its approval workflow could not be started",
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


def _build_code_table() -> dict[ErrorCodeT, CodeEntry]:
    """Assemble the published codes and this platform's own into one table.

    A message comes from the first source that has one: authored here, then the
    SDK's ``STANDARD_ERROR_CODES``, then the pinned schema's own prose. Every
    code resolves to text, so no code can reach a buyer with an empty message.
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
        )

    # Each member carries its own entry, so there is nothing to reconcile: a code
    # without one cannot be declared.
    table.update({member: member.entry for member in AppErrorCode})

    return table


#: Every code this seller can emit, mapped to what a buyer gets with it.
CODE_TABLE: Final[Mapping[ErrorCodeT, CodeEntry]] = MappingProxyType(_build_code_table())

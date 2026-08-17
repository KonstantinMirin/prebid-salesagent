"""The typed notion of WHERE a URL comes from, as a construction-time value.

Separate from ``UrlProvenance`` (``CounterpartyUrl | OperatorEndpoint``,
``outbound_http.py``, Epic B) on purpose: ``UrlProvenance`` answers "who to
blame in a refusal message" at THE MOMENT a dial fails, using a buyer-facing
role label that never carries the URL itself. ``Destination`` answers "where
did this constant/config value come from in source" at THE MOMENT a call site
builds its own URL, and DOES carry it. A call site MAY use both — one to type
its own constant, one (optionally) as ``send()``'s ``provenance=`` for
refusal messaging — but neither replaces the other; this type does not touch
``UrlProvenance``, ``send()``/``asend()``'s signature, or any existing
``provenance=`` call site.

Threaded through exactly two sites today (salesagent-tbrk.6):
``APPROXIMATED_BASE_URL``, ``GOOGLE_TOKEN_URL``. ``OperatorConfigured`` and
``CounterpartySupplied`` are defined for the concept's completeness — no call
site constructs them yet.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VendorConstant:
    """A URL that is a literal in source — never environment- or DB-sourced.

    The seam-side answer to "which URLs must never be silently redirectable":
    an env read in front of one is exactly the shape triage F11 found
    (``APPROXIMATED_BASE_URL``), and this type — plus the destination-rewrite
    guard's env-sourced-destination detector — is what makes a repeat
    instance loud instead of a harmless-looking one-liner.
    """

    url: str


@dataclass(frozen=True, slots=True)
class OperatorConfigured:
    """A URL read from tenant DB/config — a registered agent endpoint, a
    vendor host the deployment (not the buyer) chose."""

    url: str


@dataclass(frozen=True, slots=True)
class CounterpartySupplied:
    """A URL that arrived on the counterparty's own request document.

    ``field`` is ALWAYS present here (unlike ``UrlProvenance``'s
    ``CounterpartyUrl.field``, which is optional) — this type is constructed
    at the moment a URL ENTERS the system from a request document, where the
    field path is always known; ``CounterpartyUrl.field`` becomes optional
    only later, at refusal time, potentially after the URL has been
    persisted and re-dialled without the original request context.
    """

    url: str
    field: str


Destination = VendorConstant | OperatorConfigured | CounterpartySupplied

"""Grading for HMAC-SHA256 webhook signatures, over the RAW bytes received.

Recomputing over the origin's captured ``.body`` (rather than a fresh
serialization of the payload dict) is the whole point: a recompute from the
dict uses whatever serialization formula the caller happens to pick, which
can silently agree with a sender that signed one serialization and
transmitted another — the exact defect salesagent-47n9.1 fixed. Several test
files need to grade that same signed-bytes-equal-wire-bytes property, so it
lives here once instead of six near-identical copies drifting apart.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

# The two header names AdCP 3.1.1 pins for the legacy HMAC-SHA256 fallback
# (``dist/docs/3.1.0/building/by-layer/L3/webhooks.mdx:404-418``). Named
# constants rather than inline defaults because tests that grade the ABSENCE of
# a signature need the same name this module verifies against: a second string
# literal spelled somewhere else would keep passing after a header rename, which
# is precisely the regression an absence assertion exists to catch.
SIGNATURE_HEADER = "X-AdCP-Signature"
TIMESTAMP_HEADER = "X-AdCP-Timestamp"


def assert_signature_verifies_over_wire_body(
    request: Any,
    secret: str,
    *,
    signature_header: str = SIGNATURE_HEADER,
    timestamp_header: str = TIMESTAMP_HEADER,
) -> None:
    """Assert ``request``'s HMAC signature verifies against ``request.body``.

    Args:
        request: an ``OriginRequest`` (or equivalent) exposing ``.headers``
            (case-insensitive) and ``.body`` (the raw bytes the origin
            actually received).
        secret: the shared HMAC secret the sender signed with.
        signature_header: the header carrying ``sha256=<hex>``.
        timestamp_header: the header carrying the unix-seconds timestamp the
            signed message is ``f"{timestamp}."`` prefixed with.

    Raises:
        AssertionError: if the header is missing the ``sha256=`` prefix, or
            if the signature does not verify against ``request.body`` — the
            message that means for a real buyer: the signature was computed
            over bytes other than the ones that crossed the socket.
    """
    sent_signature = request.headers[signature_header]
    timestamp = request.headers[timestamp_header]
    assert sent_signature.startswith("sha256="), sent_signature

    expected = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode() + request.body,
        hashlib.sha256,
    ).hexdigest()

    assert sent_signature == f"sha256={expected}", (
        f"the buyer's endpoint could not verify this webhook: {signature_header} was "
        f"computed over bytes other than the {len(request.body)} that crossed the "
        f"socket ({request.body[:120]!r}...)"
    )

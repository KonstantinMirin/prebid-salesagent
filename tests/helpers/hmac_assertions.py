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


def assert_signature_verifies_over_wire_body(
    request: Any,
    secret: str,
    *,
    signature_header: str = "X-AdCP-Signature",
    timestamp_header: str = "X-AdCP-Timestamp",
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

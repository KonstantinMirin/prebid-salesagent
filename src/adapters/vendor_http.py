"""Construction proves an adapter can dial its vendor.

``AdServerAdapter`` used to declare ``base_url: str`` / ``headers: dict[str, str]``
as bare annotations — a promise to mypy that ``self._api(...)`` could type-check
on every subclass, kept only by the two (Kevel, Triton) that happened to assign
both. GAM, mock, and Broadstreet never did, so the same call site type-checked
and then raised ``AttributeError`` at runtime; Kevel/Triton assigned ``headers``
only in their credentialed branch, so a dry-run adapter type-checked a call it
could never actually make.

``VendorHttpClient`` replaces the promise with a fact: an adapter holds one only
when its construction already proved ``base_url`` and ``headers`` exist
together. :func:`require_vendor` is the one place "no client" becomes a typed
error, so no adapter writes its own copy of that guard.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.core.exceptions import AdCPConfigurationError
from src.core.security.outbound_http import OutboundResult, send


@dataclass(frozen=True, slots=True)
class VendorHttpClient:
    """A vendor API endpoint, dialled through the egress seam.

    ``base_url`` and ``headers`` (credentials included) are set together at
    construction and never after — the same invariant :class:`OperatorEndpoint`
    enforces for a label, applied here to a vendor's dial coordinates.
    """

    base_url: str
    headers: Mapping[str, str]

    def call(self, method: str, path: str, *, json: Any = None, params: Any = None) -> OutboundResult:
        """One vendor call through the egress seam. Returns the OutboundResult.

        Deliberately does NOT parse and does NOT map errors — callers whose
        vendor response never carries a body would otherwise trip
        ``OutboundResult.json()``'s ``json.JSONDecodeError``, which the seam
        places outside its ``OutboundError`` contract; and call sites vary in
        error policy (raise, degrade to a failed status, degrade to unknown),
        so mapping here would flatten them.

        ``max_attempts=1``: a single request, not a retry policy this method
        decides — vendor mutations (campaign/flight/creative creation) are not
        idempotent, so silently turning one failed create into three is exactly
        what routing through here must not do. ``dict(self.headers)`` copies
        the frozen mapping so a caller's mutation of the returned dict cannot
        reach back into this client's own headers.
        """
        return send(
            f"{self.base_url}{path}",
            method=method,
            headers=dict(self.headers),
            json=json,
            params=params,
            timeout=30.0,
            max_attempts=1,
        )


def require_vendor(client: VendorHttpClient | None, *, vendor: str) -> VendorHttpClient:
    """Return *client*, or raise a typed, vendor-named configuration error.

    The one place "no client" becomes an ``AdCPConfigurationError`` — every
    adapter with a ``VendorHttpClient | None`` calls this instead of writing
    its own ``if self._vendor is None: raise ...``, so the message and the
    exception class cannot drift per adapter.
    """
    if client is None:
        raise AdCPConfigurationError(f"{vendor} credentials are not configured; cannot dial the vendor API.")
    return client

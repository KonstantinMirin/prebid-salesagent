"""Transport request -> AdCP operation name: the seam, deliberately empty in B1.

#1291 B1 (salesagent-z6nr.12), plan step 2.

The posture buckets are keyed by AdCP operation name (``create_media_buy``) and, in a
separate namespace, by JSON-RPC protocol method (``tasks/cancel``). Deriving either
from an inbound MCP / A2A / REST request is a whole ticket of its own — B2
(``salesagent-z6nr.13``) — and it owns the fail-closed rule for an operation it cannot
name.

B1 therefore ships the seam and the identity element, not half a map.
:class:`UnresolvedOperationResolver` returns ``("", None)``: ``"" in required_for`` is
False for every real declaration, so B1 alone can never emit
``request_signature_required`` and can never fail closed on an operation it guessed
wrong. A partial hand-written map would do the opposite — it would be right for the
operations someone remembered and silently wrong for the rest.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OperationResolver(Protocol):
    """Names the AdCP operation (and JSON-RPC method) an inbound request invokes."""

    def resolve(self, scope: Mapping[str, Any], headers: Mapping[str, str]) -> tuple[str, str | None]:
        """Return ``(operation, protocol_method)``.

        ``operation`` is an AdCP tool name or ``""`` when unknown; ``protocol_method``
        is a wire JSON-RPC method name or ``None`` when the request is not a protocol
        method call. The two are separate namespaces in the schema and must not be
        conflated.
        """
        ...


class UnresolvedOperationResolver:
    """The identity element: every request is an unnamed operation.

    Swapped out by B2. Keeping it as a class (rather than a lambda default) is what
    makes the swap a constructor argument instead of an edit inside the middleware.
    """

    def resolve(self, scope: Mapping[str, Any], headers: Mapping[str, str]) -> tuple[str, str | None]:
        return "", None

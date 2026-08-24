"""The delivery-domain values a webhook conclusion is written from.

Lives above the SSRF seam, not inside it. ``src/core/security/webhook_egress``
owns bytes and destinations -- signing a body, choosing an address, refusing
one. WHO a delivery was for and WHAT became of it are domain facts that the
persistence layer and both senders read, and parking them in the security
package forced ``src/core/database/repositories/delivery.py`` to import out of
``src.core.security`` -- persistence depending on the security package
(salesagent-pldmk.7, review pattern #4 / AR-01).

``WebhookTaskContext``'s own docstring named the bind it was written under: "a
repository importing a dataclass out of a service module would invert the
layering." Both horns were real while the only two homes on offer were the
security package and ``src/services/``. This module is the third: a domain home
that neither side inverts to reach.

Deliberately holds no persistence encoding. ``_OUTCOME_STATUS`` -- the
``kind -> webhook_delivery_log.status`` mapping -- stays in the repository,
because its VALUES ("success", "refused", "failed") are column vocabulary. A
domain module naming DB column values would trade the inversion this move
deletes for one pointing the other way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from adcp.webhooks import extract_webhook_result_data

RefusalReason = Literal[
    "no_credentials",
    "credentials_too_short",
    "scheme_not_in_spec",
    "multi_scheme",
    "no_scheme",
]


@dataclass(frozen=True, slots=True)
class WebhookDeliveryOutcome:
    """What became of one webhook delivery attempt. The seam's only return value.

    Senders used to conclude in ``bool`` — or in an exception they each caught
    differently — so "refused", "failed after retries" and "the receiver said no"
    all arrived as the same nothing, and each sender re-derived its own failure
    literals from whatever it happened to catch. This type carries the conclusion
    to whoever needs it instead.

    ``detail`` is PRE-SANITIZED at construction: never a URL, never a credential.
    ``payload_size_bytes`` is carried because it maps 1:1 onto
    ``WebhookDeliveryLog.payload_size_bytes`` and is the reason the protocol
    sender used to reach past the seam for ``len(body_bytes)`` — which is why the
    async twin had no caller.
    """

    kind: Literal["delivered", "refused_destination", "refused_auth", "client_error", "exhausted"]
    attempts: int
    http_status: int | None = None
    detail: str | None = None
    payload_size_bytes: int | None = None
    reason: RefusalReason | None = None
    scheme: str | None = None

    @classmethod
    def unexpected(cls, exception_type: str) -> WebhookDeliveryOutcome:
        """A non-transport failure, named by its EXCEPTION TYPE and nothing else.

        The two senders that conclude on a generic exception used to build this
        outcome inline with ``detail=str(e)``. That let a foreign exception's
        text ride into ``detail`` -- and ``detail`` is not an in-memory
        convenience: it is written verbatim to
        ``webhook_delivery_log.error_message`` and emitted as an audit warning.
        ``IpPinnedTransport``'s RuntimeError names the pinned host and the host
        it refused to connect to, so ``str(e)`` disclosed a destination into
        durable storage.

        The type name is diagnostic and carries nothing the buyer supplied. The
        exception's own message stays in the log line beside the call, where an
        operator can read it, and never enters the outcome.

        This does NOT make ``detail=str(e)`` unwritable -- this is a public
        frozen dataclass and a caller can still construct one by hand. It makes
        the sanitized form the named and convenient one. A future third
        out-of-module site could reconstruct the defect, and would be invisible
        to the seam-scoped outcome tests; that residual is accepted knowingly.
        """
        return cls(kind="exhausted", attempts=0, detail=f"delivery failed with an unexpected {exception_type}")


@dataclass(frozen=True, slots=True)
class WebhookTaskContext:
    """A delivery's task identity, constructed once and consumed identically
    by all three failure arms and the success path in
    ``_send_with_retry_and_logging``.

    Absorbs the metadata/payload pluck block that used to run inline at the
    top of ``_send_with_retry_and_logging`` — repeating that pluck (or,
    worse, re-threading its results as twelve independent kwargs at three
    call sites) is how one of them ends up silently dropped at one site.

    Lives HERE, beside :class:`WebhookDeliveryOutcome`, rather than in
    ``src/services/``: these are the two values
    ``DeliveryRepository.record_outcome`` consumes — WHO the delivery was for
    and WHAT became of it — and a repository importing a dataclass out of a
    service module would invert the layering. Nothing about task identity is
    sender-specific, which is the point: both senders build one of these.
    """

    task_id: str
    task_type: str | None
    tenant_id: str | None
    principal_id: str | None
    media_buy_id: str | None
    sequence_number: int
    notification_type: str | None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any], payload: dict[str, Any]) -> WebhookTaskContext:
        task_type = metadata["task_type"] if "task_type" in metadata else None
        tenant_id = metadata["tenant_id"] if "tenant_id" in metadata else None
        principal_id = metadata["principal_id"] if "principal_id" in metadata else None
        media_buy_id = metadata["media_buy_id"] if "media_buy_id" in metadata else None

        # TODO: Fix type annotation discrepancy in adcp library - extract_webhook_result_data
        # returns dict at runtime but is typed as AdcpAsyncResponseData | None
        result = cast(dict[str, Any] | None, extract_webhook_result_data(payload))
        # After serialization, payload is always a dict - extract task_id accordingly.
        # A2A Task uses 'id'; A2A TaskStatusUpdateEvent uses camelCase 'taskId' (proto
        # json_name wire contract); MCP uses snake_case 'task_id'.
        task_id = payload.get("id") or payload.get("taskId") or payload.get("task_id") or ""

        # If we are delivering media buy delivery report
        notification_type_from_result = result.get("notification_type") if result is not None else None
        sequence_number_from_result = result.get("sequence_number") if result is not None else None
        notification_type = notification_type_from_result
        sequence_number = sequence_number_from_result if isinstance(sequence_number_from_result, int) else 1

        return cls(
            task_id=task_id,
            task_type=task_type,
            tenant_id=tenant_id,
            principal_id=principal_id,
            media_buy_id=media_buy_id,
            sequence_number=sequence_number,
            notification_type=notification_type,
        )

    @property
    def records_delivery_log(self) -> bool:
        """Whether this delivery is eligible for a ``webhook_delivery_log`` row.

        Spells the gating condition that used to appear twice (once per
        failure/success branch) exactly once.
        """
        return (
            self.task_type in ("delivery_report", "media_buy_delivery")
            and bool(self.media_buy_id)
            and bool(self.tenant_id)
            and bool(self.principal_id)
        )

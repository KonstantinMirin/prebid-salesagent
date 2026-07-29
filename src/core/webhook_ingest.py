"""Ingest-time egress verdicts for buyer-supplied webhook URLs.

A webhook URL accepted on the protocol surface is STORED now and fetched later,
often by a background worker — by then there is no request left to attach a
refusal to, so the refusal the buyer can act on has to happen here, at ingest
(AdCP 3.1.1 L1 security, "Webhook URL validation (SSRF)" points 1/2/6).

This module owns NO policy. The verdict is the seam's
(:func:`src.core.security.outbound_http.validate_url`); the coercion is
:func:`src.core.schema_helpers.to_push_notification_config` /
:func:`~src.core.schema_helpers.to_reporting_webhook`. What lives here is the
one thing neither of those can know: the JSONPath-lite request path the URL
arrived on, declared once per field below so every ``_impl`` that accepts the
field names it identically and a sixth tool cannot forget the verdict.

The field-path constants cite the pinned spec (AdCP 3.1.1): both
``create-media-buy-request.json`` and ``update-media-buy-request.json`` declare
``push_notification_config`` ($ref core/push-notification-config.json,
required ["url"]) and ``reporting_webhook`` at the TOP level of the request —
never per-package — and ``creative/sync-creatives-request.json`` carries the
same top-level ``push_notification_config``. Verified against the v3.1.1 tag.
"""

from __future__ import annotations

from typing import Any

from adcp.types import PushNotificationConfig, ReportingWebhook

from src.core.schema_helpers import to_push_notification_config, to_reporting_webhook
from src.core.security.outbound_http import validate_url

PUSH_NOTIFICATION_CONFIG_URL_FIELD = "push_notification_config.url"
REPORTING_WEBHOOK_URL_FIELD = "reporting_webhook.url"


def validated_push_notification_config(
    config: dict[str, Any] | PushNotificationConfig | None,
    *,
    field: str = PUSH_NOTIFICATION_CONFIG_URL_FIELD,
) -> PushNotificationConfig | None:
    """Coerce a wire push-notification config and refuse a URL the seam would never dial.

    Returns the typed model (or ``None`` for an absent config). Raises
    ``OutboundRequestBlocked`` — already ``INVALID_REQUEST`` / correctable —
    with ``error.field`` naming the buyer's input; callers let it propagate
    unwrapped so the path survives to both envelope layers (the
    ``property_list_resolver`` precedent).
    """
    model = to_push_notification_config(config)
    if model is not None and model.url:
        validate_url(str(model.url), field=field)
    return model


def validated_reporting_webhook(
    webhook: dict[str, Any] | ReportingWebhook | None,
    *,
    field: str = REPORTING_WEBHOOK_URL_FIELD,
) -> ReportingWebhook | None:
    """Coerce a wire reporting webhook and refuse a URL the seam would never dial.

    Same contract as :func:`validated_push_notification_config`; the reporting
    webhook is fetched by the nightly delivery scheduler, the clearest case of
    "no request left to refuse into" that makes ingest the only useful gate.
    """
    model = to_reporting_webhook(webhook)
    if model is not None and model.url:
        validate_url(str(model.url), field=field)
    return model

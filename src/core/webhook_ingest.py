"""Ingest-time egress verdicts for buyer-supplied webhook URLs.

A webhook URL accepted on the protocol surface is STORED now and fetched later,
often by a background worker — by then there is no request left to attach a
refusal to, so the refusal the buyer can act on has to happen here, at ingest
(AdCP 3.1.1 L1 security, "Webhook URL validation (SSRF)" points 1/2/6).

This module owns NO policy. The verdict is the seam's
(:func:`src.core.security.outbound_http.validate_url`). What lives here is the
one thing the seam cannot know: the JSONPath-lite request path the URL arrived
on, declared once per field below so every ``_impl`` that accepts the field
names it identically and a sixth tool cannot forget the verdict.

The helpers read ONLY the ``url`` — deliberately no model coercion of the rest
of the config. Running the whole config through the adcp
``PushNotificationConfig`` model would apply ``Authentication.credentials``
MinLen(32) to a protocol-layer parameter, so a short webhook credential would
divert the entire create away from the manual-approval gate — the exact
regression gh-#1299 settled against (see the A2A create skill's comment in
``src/a2a_server/adcp_a2a_server.py``: the config is a transport-layer
parameter, never folded into request-body validation). The URL is the SSRF
surface; the URL is what gets the verdict.

The field-path constants cite the pinned spec (AdCP 3.1.1): both
``create-media-buy-request.json`` and ``update-media-buy-request.json`` declare
``push_notification_config`` ($ref core/push-notification-config.json,
required ["url"]) and ``reporting_webhook`` at the TOP level of the request —
never per-package — and ``creative/sync-creatives-request.json`` carries the
same top-level ``push_notification_config``. Verified against the v3.1.1 tag.
"""

from __future__ import annotations

from typing import Any

from src.core.security.outbound_http import validate_url

PUSH_NOTIFICATION_CONFIG_URL_FIELD = "push_notification_config.url"
REPORTING_WEBHOOK_URL_FIELD = "reporting_webhook.url"


def _validated_webhook_url(value: Any, field: str) -> str | None:
    """The seam's verdict on the ``url`` of a dict-or-model webhook config.

    Returns the URL string (or ``None`` for an absent config/url). Raises
    ``OutboundRequestBlocked`` — already ``INVALID_REQUEST`` / correctable —
    with ``error.field`` naming the buyer's input; callers let it propagate
    unwrapped so the path survives to both envelope layers (the
    ``property_list_resolver`` precedent).
    """
    if value is None:
        return None
    url = value.get("url") if isinstance(value, dict) else getattr(value, "url", None)
    if not url:
        return None
    url_str = str(url)
    validate_url(url_str, field=field)
    return url_str


def validated_push_notification_config(config: Any, *, field: str = PUSH_NOTIFICATION_CONFIG_URL_FIELD) -> str | None:
    """Refuse a ``push_notification_config.url`` the seam would never dial.

    Accepts the dict or model shape the transport delivered and returns the
    validated URL string (``None`` when absent). URL-only on purpose — see the
    module docstring for why the rest of the config is not model-validated
    here (gh-#1299).
    """
    return _validated_webhook_url(config, field)


def validated_reporting_webhook(webhook: Any, *, field: str = REPORTING_WEBHOOK_URL_FIELD) -> str | None:
    """Refuse a ``reporting_webhook.url`` the seam would never dial.

    Same contract as :func:`validated_push_notification_config`; the reporting
    webhook is fetched by the nightly delivery scheduler, the clearest case of
    "no request left to refuse into" that makes ingest the only useful gate.
    """
    return _validated_webhook_url(webhook, field)

"""Translate the egress seam's two failure classes into this application's taxonomy.

``src/core/security/outbound_http.py`` deliberately raises exactly two errors:
``OutboundRequestBlocked`` (refused before connecting) and
``OutboundDeliveryFailed`` (reached the network, did not deliver). That is its
whole public failure surface, and it stays that way — the seam must not learn
which AdCP code a given caller wants a 429 to become, because the answer depends
on whose URL it is and what the caller is doing with it.

The translation still has to live in ONE place, or every migrating call site
re-derives it and they drift — which is the duplication the epic deletes. So it
lives here: a leaf module importing only the seam and the exception taxonomy.

NOT in ``src/core/helpers/adapter_helpers.py`` beside its sibling
``raise_mapped_adcp_error``, despite the shape being the same. That module
imports the ad-server adapters at module level, and the adapters are precisely
the call sites that will use this mapper as the epic's remaining migrations land
— importing it back would be a cycle.

Spec grounding for the classification (AdCP 3.1.1,
``dist/schemas/3.1.1/enums/error-code.json`` enumMetadata):

* ``CONFIGURATION_ERROR`` — recovery ``terminal``, "surface to a human at the
  seller — the buyer cannot resolve a seller-side deployment misconfiguration and
  MUST NOT auto-retry". That is exactly a refused OPERATOR-registered endpoint.
* ``RATE_LIMITED`` — recovery ``transient``, "retry after the retry_after
  interval".
* ``SERVICE_UNAVAILABLE`` — recovery ``transient``.
"""

from __future__ import annotations

import logging
from typing import NoReturn

from src.core.security.outbound_http import (
    OutboundDeliveryFailed,
    OutboundError,
    OutboundRequestBlocked,
    terminal_client_error_status,
)


def raise_mapped_outbound_error(exc: OutboundError, *, agent_label: str, logger: logging.Logger) -> NoReturn:
    """Re-raise a seam failure as the AdCP error its call site's URL warrants.

    For a call site whose URL is OPERATOR configuration — a registered agent
    endpoint, a vendor host — not something the buyer supplied.

    A refusal becomes ``CONFIGURATION_ERROR``/terminal rather than
    ``INVALID_REQUEST``/correctable: the buyer did not choose this address and
    cannot fix it, so telling them to correct their request would be false. (The
    opposite case — a buyer-supplied URL — keeps the seam's own
    ``INVALID_REQUEST`` and names the offending field instead.)

    A 429 becomes ``RATE_LIMITED`` carrying the origin's ``retry_after``, which
    the seam has already bounded and clamped to the spec's [1, 3600].

    Any other 4xx is terminal: a rejected request will be rejected again.

    Everything else — a 5xx, or a transport failure with no status at all — is
    re-raised UNCHANGED, because ``OutboundDeliveryFailed`` already IS an
    ``AdCPServiceUnavailableError`` (SERVICE_UNAVAILABLE / transient). Rewrapping
    it would restate the seam's own classification in a second place, which is
    what this module exists to prevent.

    Always raises; the ``NoReturn`` annotation lets a caller delegate from a
    single ``except OutboundError`` arm without a trailing ``raise``.
    """
    from src.core.exceptions import AdCPAdapterError, AdCPConfigurationError, AdCPRateLimitError

    if isinstance(exc, OutboundRequestBlocked):
        logger.error(f"Egress policy refused the configured endpoint for {agent_label}")
        raise AdCPConfigurationError(
            f"The configured endpoint for {agent_label} is not reachable under this deployment's egress policy."
        ) from exc

    if isinstance(exc, OutboundDeliveryFailed) and exc.last_status == 429:
        logger.warning(f"{agent_label} rate-limited after {exc.attempts} attempts")
        raise AdCPRateLimitError(f"{agent_label} is rate-limited.", retry_after=exc.retry_after) from exc

    terminal_status = terminal_client_error_status(exc)
    if terminal_status is not None:
        logger.error(f"{agent_label} rejected the request (HTTP {terminal_status})")
        raise AdCPAdapterError(f"{agent_label} rejected the request.", recovery="terminal") from exc

    raise exc

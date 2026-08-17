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

NOT in ``src/core/helpers/adapter_helpers.py``. That module imports the
ad-server adapters at module level, and the adapters are precisely the call
sites that will use this mapper as the epic's remaining migrations land —
importing it back would be a cycle. (Its former sibling ``raise_mapped_adcp_error``,
for the adcp SDK's own exception hierarchy, was deleted by salesagent-4n88 once
both callers moved off ``ADCPMultiAgentClient`` onto the guarded MCP seam — see
``src.core.helpers.mcp_seam_error_mapping``, the analogous mapper for THAT
seam's failure surface.)

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
    CounterpartyUrl,
    OutboundDeliveryFailed,
    OutboundError,
    OutboundRequestBlocked,
    UrlProvenance,
    terminal_client_error_status,
)


def raise_mapped_outbound_error(exc: OutboundError, *, provenance: UrlProvenance, logger: logging.Logger) -> NoReturn:
    """Re-raise a seam failure as the AdCP error *provenance* warrants.

    ``provenance`` is required — there is no "no opinion" default, because
    provenance-by-omission (an optional field a caller either passes or doesn't)
    is exactly what let a call site fabricate a locator or hand-branch on
    ``None`` instead of stating whose URL it dialled.

    A :class:`CounterpartyUrl` — the buyer supplied this URL — is re-raised
    UNCHANGED: ``OutboundRequestBlocked`` already IS an ``AdCPBlockedUrlError``
    (``VALIDATION_ERROR`` / correctable, naming the offending field when it has
    one) and ``OutboundDeliveryFailed`` already IS an
    ``AdCPServiceUnavailableError`` (``SERVICE_UNAVAILABLE`` / transient) — the
    seam's own classification is already correct for a URL the buyer chose and
    can fix, and rewrapping it would restate that classification in a second
    place, which is what this module exists to prevent.

    An :class:`OperatorEndpoint` — a registered agent endpoint, a vendor host,
    not something the buyer supplied — gets the classification below, naming
    ``provenance.name`` (a role, never an address):

    A refusal becomes ``CONFIGURATION_ERROR``/terminal rather than
    ``VALIDATION_ERROR``/correctable: the buyer did not choose this address and
    cannot fix it, so telling them to correct their request would be false.

    A 429 becomes ``RATE_LIMITED`` carrying the origin's ``retry_after``, which
    the seam has already bounded and clamped to the spec's [1, 3600].

    Any other 4xx is terminal: a rejected request will be rejected again.

    Everything else — a 5xx, or a transport failure with no status at all — is
    re-raised UNCHANGED for the same reason as the ``CounterpartyUrl`` arm:
    ``OutboundDeliveryFailed`` already IS the right AdCP class.

    Always raises; the ``NoReturn`` annotation lets a caller delegate from a
    single ``except OutboundError`` arm without a trailing ``raise``.
    """
    from src.core.exceptions import AdCPConfigurationError, AdCPRateLimitError

    if isinstance(provenance, CounterpartyUrl):
        raise exc

    agent_label = provenance.name

    if isinstance(exc, OutboundRequestBlocked):
        logger.error("Egress policy refused the configured endpoint for %s", agent_label)
        raise AdCPConfigurationError(
            f"The configured endpoint for {agent_label} is not reachable under this deployment's egress policy."
        ) from exc

    if isinstance(exc, OutboundDeliveryFailed) and exc.last_status == 429:
        logger.warning("%s rate-limited after %s attempts", agent_label, exc.attempts)
        raise AdCPRateLimitError(f"{agent_label} is rate-limited.", retry_after=exc.retry_after) from exc

    terminal_status = terminal_client_error_status(exc)
    if terminal_status is not None:
        logger.error("%s rejected the request (HTTP %s)", agent_label, terminal_status)
        raise AdCPConfigurationError(f"{agent_label} rejected the request.") from exc

    raise exc

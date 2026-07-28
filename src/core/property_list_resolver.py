"""Property list resolver with caching.

Fetches buyer property lists from external agent services and caches
the results using the cache_valid_until TTL from the response.
"""

import logging
from datetime import UTC, datetime, timedelta

from adcp.types import GetPropertyListResponse, PropertyListReference

from src.core.security.outbound_http import asend

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
_DEFAULT_TIMEOUT = 10.0

# Default cache TTL when cache_valid_until is not provided (seconds)
_DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes

# Cache: (agent_url, list_id) -> (identifier_values, expires_at)
_cache: dict[tuple[str, str], tuple[list[str], datetime]] = {}


async def resolve_property_list(ref: PropertyListReference) -> list[str]:
    """Resolve a property list reference to a list of property identifier strings.

    Fetches the property list from the agent service identified by ref.agent_url,
    caches the result using cache_valid_until from the response, and returns
    the identifier value strings.

    Args:
        ref: PropertyListReference containing agent_url, list_id, and optional auth_token.

    Returns:
        List of property identifier value strings.

    Raises:
        OutboundRequestBlocked: The buyer-supplied ``agent_url`` was refused by
            egress policy (non-HTTPS scheme, or an address the SDK validator
            rejects). INVALID_REQUEST / correctable: the buyer supplied the URL,
            so the buyer is the only party who can fix it.
        OutboundDeliveryFailed: The agent service was reachable but did not
            answer — SERVICE_UNAVAILABLE / transient.
    """
    agent_url_str = str(ref.agent_url)

    cache_key = (agent_url_str, ref.list_id)

    # Check cache
    if cache_key in _cache:
        identifiers, expires_at = _cache[cache_key]
        if datetime.now(UTC) < expires_at:
            logger.debug("Cache hit for property list %s/%s", ref.agent_url, ref.list_id)
            return identifiers
        else:
            del _cache[cache_key]

    # Build request
    url = agent_url_str.rstrip("/") + "/lists/" + ref.list_id
    headers: dict[str, str] = {}
    if ref.auth_token:
        headers["Authorization"] = f"Bearer {ref.auth_token}"

    # Fetch. Scheme policy, address validation, IP pinning, redirect refusal,
    # the response-size cap and retry classification are all the seam's — a
    # refusal or a delivery failure arrives here already typed as an AdCPError
    # with the right wire code, so there is nothing left to catch and rewrap.
    result = await asend(url, method="GET", headers=headers, timeout=_DEFAULT_TIMEOUT)

    # Parse response
    parsed = GetPropertyListResponse.model_validate(result.json())

    # Extract identifier values
    identifier_values = [ident.value for ident in parsed.identifiers] if parsed.identifiers else []

    # Cache with TTL
    if parsed.cache_valid_until is not None:
        expires_at = parsed.cache_valid_until
    else:
        expires_at = datetime.now(UTC) + timedelta(seconds=_DEFAULT_CACHE_TTL_SECONDS)

    _cache[cache_key] = (identifier_values, expires_at)

    logger.debug(
        "Resolved property list %s/%s: %d identifiers (cached until %s)",
        ref.agent_url,
        ref.list_id,
        len(identifier_values),
        expires_at.isoformat(),
    )

    return identifier_values


def clear_cache() -> None:
    """Clear the property list cache."""
    _cache.clear()

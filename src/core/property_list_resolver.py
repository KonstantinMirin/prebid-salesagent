"""Property list resolver with caching.

Fetches buyer property lists from external agent services and caches
the results using the cache_valid_until TTL from the response.
"""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from adcp.types import GetPropertyListResponse, PropertyListReference

from src.core.errors.details import AdapterFailureDetails
from src.core.exceptions import AdCPAdapterError, AdCPUrlNotAllowedError
from src.core.security.url_validator import check_url_ssrf

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
_DEFAULT_TIMEOUT = 10.0

# Default cache TTL when cache_valid_until is not provided (seconds)
_DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes

# Cache: (agent_url, list_id) -> (identifier_values, expires_at)
_cache: dict[tuple[str, str], tuple[list[str], datetime]] = {}


def _validate_agent_url(agent_url: str) -> None:
    """Validate agent_url to prevent SSRF attacks.

    Buyer-supplied agent_url must be HTTPS and must not target private/internal
    networks or cloud metadata services.

    Raises:
        AdCPAdapterError: If the URL is not allowed.
    """
    is_safe, error = check_url_ssrf(agent_url, require_https=True)
    if not is_safe:
        # The rejection reason is deliberately NOT echoed: ``check_url_ssrf``
        # returns text like "URL resolves to private/internal IP address: <ip>"
        # — the DNS-resolution result for the buyer's hostname, seen from the
        # seller's network. Emitting it turns this endpoint into a buyer-driven
        # DNS/network oracle and violates AdCP 3.1.1 transport-errors.mdx
        # § Security Considerations ("MUST NOT include: internal service names,
        # hostnames, or IP addresses"). Its catch-all arms also return
        # f"Invalid URL: {e}", i.e. third-party text. The static suggestion
        # covers the closed set of causes (scheme / hostname / blocked host /
        # private range / unresolvable); the reason goes to the log only.
        raise AdCPUrlNotAllowedError(
            field="property_list.agent_url",
            internal_detail=error,
        )


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
        AdCPAdapterError: On HTTP errors, timeouts, connection failures, or SSRF violations.
    """
    agent_url_str = str(ref.agent_url)

    # Validate URL before any network I/O
    _validate_agent_url(agent_url_str)

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

    # Fetch
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    # ``url`` is derived from the buyer's own ``ref.agent_url`` — echoing it
    # back discloses nothing the buyer did not send. The third-party exception
    # text does not go on the wire (transport-errors.mdx § Security
    # Considerations); it goes to ``internal_detail``, which
    # ``adcp_error_for()`` logs server-side. None of these three arms
    # logged anything before, so the slot is also their only operator coverage.
    except httpx.HTTPStatusError as exc:
        raise AdCPAdapterError(
            details=AdapterFailureDetails(url=url),
            internal_detail=exc,
        ) from exc
    except httpx.TimeoutException as exc:
        raise AdCPAdapterError(details=AdapterFailureDetails(url=url), internal_detail=exc) from exc
    except httpx.RequestError as exc:
        raise AdCPAdapterError(details=AdapterFailureDetails(url=url), internal_detail=exc) from exc

    # Parse response
    parsed = GetPropertyListResponse.model_validate(response.json())

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

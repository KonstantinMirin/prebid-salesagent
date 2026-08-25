"""Format resolution with product overrides and dynamic creative agent discovery.

Provides layered format lookup:
1. Product-level overrides (from product.implementation_config.format_overrides)
2. Dynamic format discovery from creative agents (via CreativeAgentRegistry)

Note: Tenant custom formats (creative_formats table) were removed in favor of
creative agent-based format discovery per AdCP v2.4.
"""

import json
import logging
from collections.abc import Iterable

from adcp.types import FormatId as LibraryFormatId

from src.core.database.database_session import get_db_session
from src.core.errors.details import EntityRefDetails
from src.core.exceptions import AdCPError, AdCPFormatNotFoundError, AdCPNotFoundError
from src.core.schemas import Format, format_id_identity
from src.core.validation_helpers import run_async_in_sync_context

logger = logging.getLogger(__name__)


def fetch_format_spec(agent_url: str, format_id: str) -> Format | None:
    """Fetch one format spec from the creative-agent registry (sync bridge).

    THE single fetch path for format specs (salesagent-mpo1) — create_media_buy,
    sync_creatives validation, and get_format all route through here so typed
    transient errors behave identically on every tool:

    - Typed ``AdCPError`` from the registry (429 -> AdCPRateLimitError,
      5xx/timeout/connect -> AdCPServiceUnavailableError) PROPAGATES: it carries
      its own recovery semantics, and swallowing it into ``None`` degrades a
      transient agent failure to a terminal "unknown format" rejection.
    - ``None`` means the agent genuinely doesn't expose the format (unknown-
      format semantics — the caller decides how to reject or fall back).
    - Untyped exceptions are logged and become ``None``: the registry types all
      its network errors, so an untyped one here is a programming surprise, not
      a transport signal.
    """
    from src.core.creative_agent_registry import get_creative_agent_registry

    registry = get_creative_agent_registry()
    try:
        return run_async_in_sync_context(registry.get_format(agent_url, format_id))
    except AdCPError:
        raise
    except Exception as e:
        logger.warning(f"Could not fetch format {format_id} from {agent_url}: {e}")
        return None


def find_format(formats: Iterable[Format], format_id: LibraryFormatId) -> Format | None:
    """The format in *formats* that *format_id* names, or None.

    ONE definition of "is this the format the buyer asked for", so no caller can
    reintroduce a class-sensitive ``==`` against a registry listing. ``FormatId``
    exists twice -- the library type the AdCP schemas declare and our subclass --
    and pydantic v2 equality is class-sensitive, so comparing the models matched
    NOTHING whenever the two sides were built by different code paths
    (the A2A boundary built one, MCP and REST the other; #1388).

    Identity is ``format_id_identity``'s ``(canonical agent_url, id)``, the pair the
    graded contract matches on (``core/format-id.json`` requires ``[agent_url, id]``;
    the list_formats storyboard step uses ``match_keys: [agent_url, id]``) and the
    same pair ``list_creative_formats`` filters with. Notably that means a
    PARAMETERIZED reference resolves to the template it parameterizes -- which is
    the point of a template format, and what lets a 300x250 request find the
    ``display`` format's spec.
    """
    wanted = format_id_identity(format_id)
    return next((fmt for fmt in formats if format_id_identity(fmt.format_id) == wanted), None)


def get_format(
    format_id: str, agent_url: str | None = None, tenant_id: str | None = None, product_id: str | None = None
) -> Format:
    """Resolve format with priority: product override → creative agent discovery.

    Args:
        format_id: Format identifier (e.g., "display_300x250_image")
        agent_url: Optional creative agent URL (defaults to AdCP standard agent)
        tenant_id: Optional tenant ID for agent lookup
        product_id: Optional product ID for product-level overrides

    Returns:
        Format object with all configuration

    Raises:
        AdCPFormatNotFoundError: If format_id not found in any source
    """
    # Check product override first
    if product_id and tenant_id:
        override = _get_product_format_override(tenant_id, product_id, format_id, agent_url=agent_url)
        if override:
            return override

    # Get from creative agent registry
    from src.core.creative_agent_registry import get_creative_agent_registry

    registry = get_creative_agent_registry()

    # If agent_url provided, get format directly from that agent
    # Coerce to str: FormatId.agent_url is Pydantic AnyUrl (not a str subclass)
    if agent_url:
        fmt = fetch_format_spec(str(agent_url), format_id)
        if fmt:
            return fmt
    else:
        # Search all agents for this format
        all_formats = run_async_in_sync_context(registry.list_all_formats(tenant_id=tenant_id))
        # `fmt.format_id.id == format_id`, the same component comparison
        # CreativeAgentRegistry.get_format uses, because this parameter is a bare
        # `str`. Comparing it against the FormatId MODEL -- as this line did -- is
        # False for every format, so the branch resolved nothing at all (#1388).
        # An id with no agent_url to namespace it is inherently ambiguous across
        # agents; first in listing order wins, which is what "search all agents"
        # has always meant here.
        for fmt in all_formats:
            if fmt.format_id.id == format_id:
                return fmt

    # Not found anywhere. The identifiers travel as structured detail rather than
    # interpolated prose: the buyer needs to know WHICH format_id was rejected, and
    # ``details`` is where a machine can read it.
    raise AdCPFormatNotFoundError(
        field="format_id",
        # The conditional spreads this replaces kept absent identifiers out of the
        # block; ``to_wire()`` drops unset fields, so a plain None says the same
        # thing without three dict literals.
        details=EntityRefDetails(format_id=format_id, agent_url=agent_url, tenant_id=tenant_id),
    )


def _get_product_format_override(
    tenant_id: str, product_id: str, format_id: str, agent_url: str | None = None
) -> Format | None:
    """Get product-level format override from product.implementation_config.

    Product can override any format's platform_config. Example:
    {
        "format_overrides": {
            "display_300x250": {
                "platform_config": {
                    "gam": {
                        "creative_placeholder": {
                            "width": 1,
                            "height": 1,
                            "creative_template_id": 12345678
                        }
                    }
                }
            }
        }
    }

    Args:
        tenant_id: Tenant identifier
        product_id: Product identifier
        format_id: Format to look up
        agent_url: Optional creative agent URL (needed to fetch base format)

    Returns:
        Format with overridden config, or None if no override exists
    """
    from sqlalchemy import text

    with get_db_session() as session:
        result = session.execute(
            text(
                "SELECT implementation_config FROM products WHERE tenant_id = :tenant_id AND product_id = :product_id"
            ),
            {"tenant_id": tenant_id, "product_id": product_id},
        )
        row = result.fetchone()
        if not row or not row[0]:
            return None

        # Parse implementation_config JSON
        impl_config = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        format_overrides = impl_config.get("format_overrides", {})

        if format_id not in format_overrides:
            return None

        # Get base format from creative agent registry (WITHOUT product_id to avoid recursion)
        from src.core.creative_agent_registry import get_creative_agent_registry

        registry = get_creative_agent_registry()

        try:
            # format_id is a string key in format_overrides dict
            # Pass agent_url to find the base format from the correct creative agent
            base_format = get_format(format_id, agent_url=agent_url, tenant_id=tenant_id, product_id=None)
        except (AdCPNotFoundError, Exception):
            # Base format not found - cannot apply override
            return None

        # Apply override to base format
        override_config = format_overrides[format_id]

        # Merge platform_config override
        if "platform_config" in override_config:
            # Access platform_config directly from the model, not via model_dump(),
            # because platform_config has exclude=True and model_dump() drops it.
            base_platform_config = base_format.platform_config or {}
            override_platform_config = override_config["platform_config"]

            # Deep merge platform configs (override takes precedence)
            merged_platform_config = {**base_platform_config}
            for platform, config in override_platform_config.items():
                if platform in merged_platform_config:
                    # Merge platform-specific configs
                    merged_platform_config[platform] = {
                        **merged_platform_config[platform],
                        **config,
                    }
                else:
                    merged_platform_config[platform] = config

            return base_format.model_copy(update={"platform_config": merged_platform_config})

        return base_format


def list_available_formats(
    tenant_id: str | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
    is_responsive: bool | None = None,
    asset_types: list[str] | None = None,
    name_search: str | None = None,
) -> list[Format]:
    """List all formats available to a tenant from all registered creative agents.

    Args:
        tenant_id: Optional tenant ID to include tenant-specific agents
        max_width: Maximum width in pixels (inclusive)
        max_height: Maximum height in pixels (inclusive)
        min_width: Minimum width in pixels (inclusive)
        min_height: Minimum height in pixels (inclusive)
        is_responsive: Filter for responsive formats
        asset_types: Filter by asset types
        name_search: Search by name

    Returns:
        List of all available Format objects from all registered agents
    """
    import logging

    logger = logging.getLogger(__name__)

    from src.core.creative_agent_registry import get_creative_agent_registry

    logger.info(f"[list_available_formats] Starting format fetch for tenant_id={tenant_id}")

    try:
        registry = get_creative_agent_registry()
    except Exception as e:
        logger.error(f"[list_available_formats] Failed to get creative agent registry: {e}", exc_info=True)
        return []

    # Get formats from all agents (default + tenant-specific)
    try:
        formats = run_async_in_sync_context(
            registry.list_all_formats(
                tenant_id=tenant_id,
                max_width=max_width,
                max_height=max_height,
                min_width=min_width,
                min_height=min_height,
                is_responsive=is_responsive,
                asset_types=asset_types,
                name_search=name_search,
            )
        )
    except Exception as e:
        logger.error(f"[list_available_formats] Error fetching formats: {e}", exc_info=True)
        return []

    logger.info(f"[list_available_formats] Successfully fetched {len(formats)} formats")
    return formats

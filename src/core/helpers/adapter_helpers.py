"""Adapter instance creation and configuration helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NoReturn, Protocol

if TYPE_CHECKING:
    from adcp import AgentConfig
    from adcp.exceptions import ADCPError

    from src.adapters import AdServerAdapter


class _HasAgentFields(Protocol):
    """Structural type for objects with agent config fields (CreativeAgent, SignalsAgent)."""

    name: str
    agent_url: str
    auth: dict[str, Any] | None
    auth_header: str | None
    timeout: int


def build_agent_config(agent: _HasAgentFields) -> AgentConfig:
    """Build an adcp AgentConfig from any object with standard agent fields.

    Shared by CreativeAgentRegistry and SignalsAgentRegistry to avoid
    duplicating the auth-extraction and config-building logic.
    """
    from adcp import AgentConfig as _AgentConfig
    from adcp import Protocol as AdcpProtocol

    auth_type = "token"
    auth_token = None
    if agent.auth:
        auth_type = agent.auth.get("type", "token")
        auth_token = agent.auth.get("credentials")

    return _AgentConfig(
        id=agent.name,
        agent_uri=str(agent.agent_url),
        protocol=AdcpProtocol.MCP,
        auth_token=auth_token,
        auth_type=auth_type,
        auth_header=agent.auth_header or "x-adcp-auth",
        timeout=float(agent.timeout),
    )


def raise_mapped_adcp_error(exc: ADCPError, *, agent_label: str, logger: logging.Logger) -> NoReturn:
    """Translate an adcp SDK exception into the internal typed AdCPError taxonomy.

    Shared by CreativeAgentRegistry and SignalsAgentRegistry so the SDK-to-internal
    error mapping — and its recovery classification — has a single home: an
    authentication failure surfaces as terminal (the caller must fix credentials),
    a timeout or connection failure surfaces as a transient service outage (a retry
    may succeed), and any other AdCP error maps to a generic adapter failure.

    Always raises; the ``NoReturn`` annotation lets callers delegate from a single
    ``except ADCPError`` arm without a trailing ``raise``.
    """
    from adcp.exceptions import ADCPAuthenticationError, ADCPConnectionError, ADCPTimeoutError

    from src.core.exceptions import AdCPAdapterError, AdCPAuthenticationError, AdCPServiceUnavailableError

    if isinstance(exc, ADCPAuthenticationError):
        logger.error(f"Authentication failed for {agent_label}: {exc.message}")
        raise AdCPAuthenticationError(f"Authentication failed: {exc.message}") from exc
    if isinstance(exc, ADCPTimeoutError):
        logger.error(f"Request timed out for {agent_label}: {exc.message}")
        raise AdCPServiceUnavailableError(f"Request timed out: {exc.message}") from exc
    if isinstance(exc, ADCPConnectionError):
        logger.error(f"Connection failed for {agent_label}: {exc.message}")
        raise AdCPServiceUnavailableError(f"Connection failed: {exc.message}") from exc
    logger.error(f"AdCP error for {agent_label}: {exc.message}")
    raise AdCPAdapterError(str(exc.message)) from exc


from src.adapters.google_ad_manager import GoogleAdManager
from src.adapters.kevel import Kevel
from src.adapters.mock_ad_server import MockAdServer as MockAdServerAdapter
from src.adapters.triton_digital import TritonDigital
from src.core.database.database_session import get_db_session
from src.core.schemas import Principal


def _resolve_tenant_id_and_fallback_adapter(tenant: Any) -> tuple[str, str]:
    """Extract tenant_id and the tenant.ad_server fallback adapter type.

    Supports both the ORM model (Tenant) and the dict shape (identity.tenant).
    This is the pre-AdapterConfig fallback only — callers needing the
    authoritative adapter type must go through ``resolve_tenant_adapter_type``.
    """
    if isinstance(tenant, dict):
        return tenant["tenant_id"], tenant.get("ad_server") or "mock"
    # ORM model (Tenant) — use attribute access
    return tenant.tenant_id, tenant.ad_server or "mock"


def resolve_tenant_adapter_type(tenant: Any = None) -> str:
    """Resolve the authoritative ad-server adapter type for a tenant.

    Single source of truth for adapter-TYPE resolution: ``AdapterConfig.adapter_type``
    (via ``AdapterConfigRepository``) wins when a row exists, falling back to
    ``tenant.ad_server``/``tenant["ad_server"]`` otherwise. ``get_adapter()`` and the
    principal-free ``get_adapter_class_for_tenant()`` read path both route through
    this function so the two can never diverge (salesagent-dn2s: divergent
    tenant-adapter-type resolution copies would only half-close INV-4).

    Args:
        tenant: Tenant context (dict or ORM model). Falls back to ContextVar if not provided.
    """
    logger = logging.getLogger(__name__)

    if tenant is None:
        # Fallback for callers that haven't been updated yet (e.g., async approval handlers)
        from src.core.config_loader import get_current_tenant

        tenant = get_current_tenant()

    tenant_id, selected_adapter = _resolve_tenant_id_and_fallback_adapter(tenant)
    logger.info(f"[ADAPTER_SELECT] Initial selected_adapter from tenant.ad_server: {selected_adapter}")

    from src.core.database.repositories.adapter_config import AdapterConfigRepository

    with get_db_session() as session:
        repo = AdapterConfigRepository(session, tenant_id)
        config_row = repo.find_by_tenant()
        if config_row and config_row.adapter_type:
            selected_adapter = config_row.adapter_type
            logger.info(f"[ADAPTER_SELECT] Using AdapterConfig.adapter_type: {selected_adapter}")

    return selected_adapter or "mock"


def get_adapter_class_for_tenant(tenant: Any = None) -> type[AdServerAdapter]:
    """Resolve the ad-server adapter CLASS for a tenant, without a Principal.

    For read-only capability/discovery paths (e.g. get_adcp_capabilities) that
    only need adapter-level CLASS attributes (default_channels,
    get_targeting_capabilities) and must work identically for anonymous and
    authenticated callers per AdCP INV-4 (capabilities describe the seller,
    not the caller). Deliberately bypasses ``Adapter.__init__`` — Kevel and
    TritonDigital unconditionally require a principal-bound config in
    ``__init__`` and would crash for a synthetic/tenant-only Principal.

    Args:
        tenant: Tenant context (dict or ORM model). Falls back to ContextVar if not provided.
    """
    from src.adapters import get_adapter_class

    adapter_type = resolve_tenant_adapter_type(tenant)
    return get_adapter_class(adapter_type)


def get_adapter(
    principal: Principal, dry_run: bool = False, testing_context: Any = None, tenant: Any = None
) -> MockAdServerAdapter | GoogleAdManager | Kevel | TritonDigital:
    """Get the appropriate adapter instance for the selected adapter type.

    Args:
        principal: The authenticated principal
        dry_run: Whether to run in dry-run mode
        testing_context: Optional test context for simulations
        tenant: Tenant context (from identity.tenant). Falls back to ContextVar if not provided.
    """
    import logging

    logger = logging.getLogger(__name__)

    if tenant is None:
        # Fallback for callers that haven't been updated yet (e.g., async approval handlers)
        from src.core.config_loader import get_current_tenant

        tenant = get_current_tenant()

    selected_adapter = resolve_tenant_adapter_type(tenant)
    tenant_id, _ = _resolve_tenant_id_and_fallback_adapter(tenant)

    # Get adapter config via repository
    from src.core.database.repositories.adapter_config import AdapterConfigRepository

    targeting_config: dict[str, Any] | None = None
    naming_templates: tuple[str | None, str | None] | None = None

    with get_db_session() as session:
        repo = AdapterConfigRepository(session, tenant_id)
        config_row = repo.find_by_tenant()

        adapter_config: dict[str, Any] = {"enabled": True}
        if config_row:
            adapter_type = config_row.adapter_type
            logger.info(f"[ADAPTER_SELECT] adapter_type from AdapterConfig: {adapter_type}")
            if adapter_type == "mock":
                adapter_config["dry_run"] = config_row.mock_dry_run or False
                # Default to True (require approval) for safety
                adapter_config["manual_approval_required"] = (
                    config_row.mock_manual_approval_required
                    if config_row.mock_manual_approval_required is not None
                    else True
                )
            elif adapter_type == "google_ad_manager":
                adapter_config = repo.get_gam_config(config_row)
                targeting_config = repo.get_gam_targeting_config(config_row)
                naming_templates = repo.get_gam_naming_templates(config_row)

                # Get advertiser_id from principal's platform_mappings (per-principal, not tenant-level)
                # Support both old format (nested under "google_ad_manager") and new format (root "gam_advertiser_id")
                advertiser_id: str | None = None
                if principal.platform_mappings:
                    # Try nested format first
                    gam_mappings = principal.platform_mappings.get("google_ad_manager", {})
                    advertiser_id = gam_mappings.get("advertiser_id")
                    logger.info(
                        f"[ADAPTER_CONFIG] principal_id={principal.principal_id}, platform_mappings={principal.platform_mappings}, gam_mappings={gam_mappings}, advertiser_id={advertiser_id}"
                    )

                    # Fall back to root-level format if nested not found
                    if not advertiser_id:
                        advertiser_id = principal.platform_mappings.get("gam_advertiser_id")
                        logger.info(f"[ADAPTER_CONFIG] Fell back to root-level gam_advertiser_id: {advertiser_id}")

                    adapter_config["company_id"] = advertiser_id
                    logger.info(f"[ADAPTER_CONFIG] Set adapter_config['company_id']={advertiser_id}")
                else:
                    adapter_config["company_id"] = None
                    logger.info("[ADAPTER_CONFIG] principal.platform_mappings is None/empty, set company_id=None")
            elif adapter_type == "kevel":
                adapter_config["network_id"] = config_row.kevel_network_id or ""
                adapter_config["api_key"] = config_row.kevel_api_key or ""
                # Default to True (require approval) for safety
                adapter_config["manual_approval_required"] = (
                    config_row.kevel_manual_approval_required
                    if config_row.kevel_manual_approval_required is not None
                    else True
                )
            elif adapter_type == "triton":
                adapter_config["station_id"] = config_row.triton_station_id or ""
                adapter_config["api_key"] = config_row.triton_api_key or ""

    if not selected_adapter:
        # Default to mock if no adapter specified
        selected_adapter = "mock"
        if not adapter_config:
            adapter_config = {"enabled": True}

    # Create the appropriate adapter instance with tenant_id and testing context
    logger.info(f"[ADAPTER_SELECT] FINAL selected_adapter: {selected_adapter}")
    if selected_adapter == "mock":
        logger.info("[ADAPTER_SELECT] Instantiating MockAdServerAdapter")
        return MockAdServerAdapter(
            adapter_config, principal, dry_run, tenant_id=tenant_id, strategy_context=testing_context
        )
    elif selected_adapter == "google_ad_manager":
        # network_code is required for GoogleAdManager
        network_code = adapter_config.get("network_code")
        if not network_code or not isinstance(network_code, str):
            raise ValueError("network_code is required for GoogleAdManager adapter")

        logger.info("[ADAPTER_SELECT] Instantiating GoogleAdManager")
        logger.info(
            f"[ADAPTER_SELECT] GAM params: network_code={adapter_config.get('network_code')}, advertiser_id={adapter_config.get('company_id')}, trafficker_id={adapter_config.get('trafficker_id')}, dry_run={dry_run}"
        )
        return GoogleAdManager(
            adapter_config,
            principal,
            network_code=network_code,
            advertiser_id=adapter_config.get("company_id"),
            trafficker_id=adapter_config.get("trafficker_id"),
            dry_run=dry_run,
            tenant_id=tenant_id,
            targeting_config=targeting_config,
            naming_templates=naming_templates,
        )
    elif selected_adapter == "kevel":
        return Kevel(adapter_config, principal, dry_run, tenant_id=tenant_id)
    elif selected_adapter in ["triton", "triton_digital"]:
        return TritonDigital(adapter_config, principal, dry_run, tenant_id=tenant_id)
    else:
        # Default to mock for unsupported adapters
        return MockAdServerAdapter(
            adapter_config, principal, dry_run, tenant_id=tenant_id, strategy_context=testing_context
        )

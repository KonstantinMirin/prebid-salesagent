"""CapabilitiesEnv — integration test environment for _get_adcp_capabilities_impl.

Patches: adapter factory + audit logger ONLY.
Real: get_db_session, TenantConfigUoW (publisher partners), get_principal_object,
the full response builder (all hit real DB).

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with CapabilitiesEnv() as env:
            tenant, principal = env.setup_default_data()
            response = env.call_impl()
            assert response.supported_protocols

Available mocks via env.mock:
    "adapter"      -- get_adapter (module-level import in capabilities.py)
    "audit_logger" -- log_tool_activity (module-level import in capabilities.py)

beads: salesagent-4sn7 (#1592 / #1210)
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from adcp.types import GetAdcpCapabilitiesRequest, GetAdcpCapabilitiesResponse

from src.adapters.base import TargetingCapabilities
from tests.harness._base import IntegrationEnv

#: Default channels seeded on the adapter mock — matches the feature fixture
#: comment ("fixture seeds channels 'display, social, ctv' on the adapter").
DEFAULT_ADAPTER_CHANNELS = ["display", "social", "ctv"]


def _full_targeting_capabilities() -> TargetingCapabilities:
    """A TargetingCapabilities with every dimension enabled."""
    from dataclasses import fields

    return TargetingCapabilities(**{f.name: True for f in fields(TargetingCapabilities)})


class CapabilitiesEnv(IntegrationEnv):
    """Integration test environment for get_adcp_capabilities.

    Only mocks the adapter factory and the audit logger. Everything else is
    real: real DB, real TenantConfigUoW (publisher partners), real transport
    wrappers. Capabilities is a pure read — no adapter I/O beyond attribute
    access on the mock.

    Transport routing:
    - call_impl(): direct _get_adcp_capabilities_impl (sync)
    - call_a2a(): real AdCPRequestHandler pipeline
    - call_mcp(): real FastMCP in-memory Client (wire_response is real wire)
    - REST: /api/v1/capabilities is a GET route with no body — _run_rest_request
      is overridden to GET (the base implementation POSTs)
    """

    EXTERNAL_PATCHES = {
        "adapter": "src.core.tools.capabilities.get_adapter",
        "audit_logger": "src.core.tools.capabilities.log_tool_activity",
    }

    REST_ENDPOINT = "/api/v1/capabilities"
    # RestE2EDispatcher honors this hook (dispatchers.py) — the live route is GET.
    REST_METHOD = "get"

    def _configure_mocks(self) -> None:
        """Happy-path adapter: default channels + full targeting capabilities."""
        adapter = MagicMock()
        adapter.default_channels = list(DEFAULT_ADAPTER_CHANNELS)
        adapter.get_targeting_capabilities.return_value = _full_targeting_capabilities()
        self.mock["adapter"].return_value = adapter
        self._adapter_mock = adapter

    # -- Given-step helpers ---------------------------------------------------

    def set_adapter_channels(self, channels: list[str]) -> None:
        """Configure the channel names the adapter reports."""
        self._adapter_mock.default_channels = list(channels)

    def set_targeting_capabilities(self, **dims: bool) -> None:
        """Configure adapter targeting capabilities from keyword flags.

        Unnamed dimensions default to False (TargetingCapabilities defaults).
        """
        self._adapter_mock.get_targeting_capabilities.return_value = TargetingCapabilities(**dims)

    def make_adapter_unavailable(self) -> None:
        """Adapter factory raises — production degrades to default channels."""
        self.mock["adapter"].side_effect = Exception("adapter unavailable (harness)")

    def break_tenant_config_db(self) -> None:
        """Make the publisher-partner DB read fail — production degrades to placeholder.

        Patches TenantConfigUoW at the capabilities module seam. Tracked on
        ctx-independent env teardown via the standard patcher list.
        """
        patcher = patch(
            "src.core.tools.capabilities.TenantConfigUoW",
            side_effect=Exception("tenant config DB failure (harness)"),
        )
        self.mock["tenant_config_uow"] = patcher.start()
        self._patchers.append(patcher)

    def invalid_token_identity(self) -> Any:
        """An identity carrying a token that matches no Principal row.

        Per-transport behavior is production's: A2A rejects a presented-but-
        invalid credential; MCP/REST treat it as absent (auth-optional tool).
        """
        from tests.factories.principal import PrincipalFactory

        return PrincipalFactory.make_identity(
            principal_id=None,
            tenant_id=self._tenant_id,
            auth_token="invalid-token-harness",
            **self._tenant_overrides,
        )

    def anonymous_identity(self) -> Any:
        """Tenant-resolvable identity with NO credential and NO principal.

        Models the production no-auth discovery call where the tenant still
        resolves (Host header / subdomain) — distinct from identity=None,
        which is the no-tenant case.
        """
        from tests.factories.principal import PrincipalFactory

        return PrincipalFactory.make_identity(
            principal_id=None,
            tenant_id=self._tenant_id,
            auth_token=None,
            **self._tenant_overrides,
        )

    # -- Transport verbs ------------------------------------------------------

    @staticmethod
    def _build_request(**kwargs: Any) -> GetAdcpCapabilitiesRequest:
        """Build the typed request from flat When-step kwargs."""
        return GetAdcpCapabilitiesRequest(**kwargs)

    def call_impl(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Call _get_adcp_capabilities_impl directly (sync — no wrapper needed)."""
        from src.core.tools.capabilities import _get_adcp_capabilities_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        req = self._build_request(**kwargs) if kwargs else None
        return _get_adcp_capabilities_impl(req, identity)

    def call_a2a(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Call get_adcp_capabilities via real AdCPRequestHandler — full A2A pipeline."""
        return self._run_a2a_handler("get_adcp_capabilities", GetAdcpCapabilitiesResponse, **kwargs)

    def call_mcp(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Call get_adcp_capabilities via Client(mcp) — full pipeline dispatch."""
        return self._run_mcp_client("get_adcp_capabilities", GetAdcpCapabilitiesResponse, **kwargs)

    def _run_rest_request(self, endpoint: str, **kwargs: Any) -> Any:
        """REST dispatch override: the capabilities route is GET with no body.

        Mirrors the base implementation's auth handling via the shared
        ``_configure_rest_auth`` helper, then GETs. Request params (protocols /
        context / adcp_version) cannot ride this route today — passing any
        raises so the gap surfaces as xfail evidence instead of a silent drop
        (No Quiet Failures; the param-carrying REST shape is S2 production work).
        """
        identity = self._pop_rest_identity(kwargs)
        if kwargs:
            raise NotImplementedError(
                f"REST /api/v1/capabilities is a parameterless GET — cannot express {sorted(kwargs)} (#1592 S2)"
            )
        self._commit_factory_data()
        client = self.get_rest_client()
        self._configure_rest_auth(identity)
        return client.get(endpoint)

    def parse_rest_response(self, data: dict[str, Any]) -> GetAdcpCapabilitiesResponse:
        """Parse REST JSON into GetAdcpCapabilitiesResponse."""
        return GetAdcpCapabilitiesResponse(**data)

    # -- Async variants for @pytest.mark.asyncio tests ------------------------

    async def call_a2a_async(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Async wrapper for tests already inside an event loop."""
        return await asyncio.to_thread(self.call_a2a, **kwargs)

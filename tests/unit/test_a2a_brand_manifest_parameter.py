#!/usr/bin/env python3
"""
Test A2A get_products brand parameter handling (adcp 3.6.0).

Unit tests to verify that the A2A server correctly uses brand (not brand_manifest)
when calling the core get_products tool.

After the identity-at-transport-boundary refactor, handlers
receive a pre-resolved identity parameter.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from src.core.schema_helpers import to_brand_reference
from tests.factories.principal import PrincipalFactory

logger = logging.getLogger(__name__)

_MOCK_IDENTITY = PrincipalFactory.make_identity(
    principal_id="test_principal", tenant_id="test_tenant", tenant={"tenant_id": "test_tenant"}, protocol="a2a"
)


@pytest.mark.asyncio
async def test_handle_get_products_skill_passes_brand():
    """Test that _handle_get_products_skill passes brand parameter to core tool."""
    handler = AdCPRequestHandler()

    with patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        parameters = {
            "brand": {"domain": "nike.com"},
            "brief": "Athletic footwear",
        }

        await handler._handle_get_products_skill(parameters, _MOCK_IDENTITY)

        mock_core_tool.assert_called_once()
        # The handler builds through the shared builder and hands the wrapper ONE request,
        # so the buyer's fields are graded where they now travel: on the request.
        req = mock_core_tool.call_args.kwargs["req"]

        assert to_brand_reference({"domain": "nike.com"}) == req.brand
        assert req.brief == "Athletic footwear"
        assert not hasattr(req, "brand_manifest"), "brand_manifest must not reach the request"


@pytest.mark.asyncio
async def test_handle_get_products_skill_extracts_all_parameters():
    """Test that _handle_get_products_skill extracts spec parameters and ignores non-spec ones.

    Non-spec parameters (min_exposures, strategy_id, adcp_version) MUST NOT be forwarded
    to the core tool — they are not in the AdCP GetProductsRequest schema. adcp_version is
    used at the transport boundary for version compat, not forwarded to the wrapper.
    """
    handler = AdCPRequestHandler()

    with patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        parameters = {
            "brand": {"domain": "nike.com"},
            "brief": "Athletic footwear",
            "filters": {"delivery_type": "guaranteed"},
            "min_exposures": 10000,
            "adcp_version": "3.6.0",
            "strategy_id": "test_strategy_123",
        }

        await handler._handle_get_products_skill(parameters, _MOCK_IDENTITY)

        mock_core_tool.assert_called_once()
        req = mock_core_tool.call_args.kwargs["req"]

        assert to_brand_reference({"domain": "nike.com"}) == req.brand
        assert req.brief == "Athletic footwear"
        assert req.filters is not None and req.filters.delivery_type is not None
        # Off-spec and transport-envelope names must not reach the request. The builder is
        # the only door now, so a name it does not take cannot arrive by another route.
        for off_spec in ("min_exposures", "strategy_id", "brand_manifest"):
            assert not hasattr(req, off_spec), f"{off_spec} is not in the AdCP spec — must not be forwarded"


@pytest.mark.asyncio
async def test_handle_get_products_skill_forwards_property_list():
    """Test that _handle_get_products_skill forwards property_list to core tool.

    Regression test for : A2A handler was silently dropping
    property_list while MCP and get_products_raw both forwarded it correctly.
    """
    handler = AdCPRequestHandler()

    with patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        parameters = {
            "brief": "Video ads",
            # list_id is REQUIRED on PropertyListReference (agent_url and list_id both
            # are, per the pinned type). This payload used to omit it and still pass,
            # because the handler forwarded the raw dict unvalidated; the shared builder
            # validates it, so a fixture that could never come off the wire now fails.
            "property_list": {"agent_url": "https://buyer.example.com/properties", "list_id": "pl-001"},
        }

        await handler._handle_get_products_skill(parameters, _MOCK_IDENTITY)

        mock_core_tool.assert_called_once()
        req = mock_core_tool.call_args.kwargs["req"]

        assert req.property_list is not None, "property_list should reach the request"
        assert str(req.property_list.agent_url).rstrip("/") == "https://buyer.example.com/properties"
        assert req.property_list.list_id == "pl-001"


@pytest.mark.asyncio
async def test_handle_get_products_skill_brand_manifest_not_converted():
    """Test that brand_manifest is NOT silently converted — brand_manifest is ignored."""
    handler = AdCPRequestHandler()

    with patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        # brand_manifest with brief — brief satisfies the "brief OR brand" requirement
        parameters = {
            "brand_manifest": {"name": "Nike Athletic Footwear"},
            "brief": "Display ads",
        }

        await handler._handle_get_products_skill(parameters, _MOCK_IDENTITY)

        mock_core_tool.assert_called_once()
        req = mock_core_tool.call_args.kwargs["req"]

        # brand_manifest is ignored, so the request carries no brand at all. The obligation
        # graded here is that brand_manifest is never CONVERTED into a brand -- stated on
        # the request itself, without also pinning how the field was forwarded.
        assert req.brand is None
        assert req.brief == "Display ads"
        assert not hasattr(req, "brand_manifest")


@pytest.mark.asyncio
async def test_handle_get_products_skill_no_brief_no_brand_raises():
    """Test that AdCPValidationError from _impl propagates through the handler."""
    handler = AdCPRequestHandler()

    with patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool:
        from src.core.exceptions import AdCPValidationError

        mock_core_tool.side_effect = AdCPValidationError()

        # AdCPSalesAgentError propagates via 'except AdCPSalesAgentError: raise' to outer handler
        with pytest.raises(AdCPValidationError):
            await handler._handle_get_products_skill({}, _MOCK_IDENTITY)

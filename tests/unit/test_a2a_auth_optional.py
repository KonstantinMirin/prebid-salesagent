#!/usr/bin/env python3
"""
Unit tests for A2A auth-optional discovery endpoints.

Tests that discovery endpoints (list_creative_formats, list_authorized_properties, get_products)
properly handle both authenticated and unauthenticated requests according to AdCP spec.

After the identity-at-transport-boundary refactor , handlers receive
a pre-resolved identity parameter rather than resolving auth internally.
"""

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from src.core.auth_context import AuthContext
from src.core.schemas import GetProductsResponse, ListCreativeFormatsResponse
from tests.factories.principal import PrincipalFactory
from tests.helpers.boundary_identity import resolved_as
from tests.helpers.capture_wrapper_req import stub_impl


class TestAuthOptionalSkills:
    """Test auth-optional skill handling in A2A server.

    The with-auth / without-auth pairs below express the difference through the RESOLVER,
    because that is where it now lives. They used to express it by handing _dispatch_skill a
    different identity -- a parameter dispatch ignored, so the two halves of each pair ran
    the identical code path and the pair graded nothing.
    """

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = AdCPRequestHandler()
        self.mock_identity = PrincipalFactory.make_identity(
            principal_id="test_principal", tenant_id="default", tenant={"tenant_id": "default"}, protocol="a2a"
        )
        self.anon_identity = PrincipalFactory.make_identity(
            principal_id=None, tenant_id="default", tenant={"tenant_id": "default"}, protocol="a2a"
        )

    @pytest.mark.asyncio
    async def test_list_creative_formats_without_auth(self):
        """list_creative_formats should work with anonymous identity (no principal)."""
        with stub_impl("list_creative_formats") as mock_tool, resolved_as(self.anon_identity):
            mock_tool.return_value = ListCreativeFormatsResponse(formats=[])

            result = await self.handler._dispatch_skill("list_creative_formats", {}, AuthContext())

            assert result is not None
            assert "formats" in result
            mock_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_creative_formats_with_auth(self):
        """list_creative_formats should work with authenticated identity."""
        with stub_impl("list_creative_formats") as mock_tool, resolved_as(self.mock_identity):
            mock_tool.return_value = ListCreativeFormatsResponse(formats=[])

            result = await self.handler._dispatch_skill("list_creative_formats", {}, AuthContext())

            assert result is not None
            mock_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_products_without_auth(self):
        """get_products should work with anonymous identity."""
        with stub_impl("get_products") as mock_tool, resolved_as(self.anon_identity):
            mock_tool.return_value = GetProductsResponse(products=[])

            result = await self.handler._dispatch_skill("get_products", {"brief": "test campaign"}, AuthContext())

            assert result is not None
            mock_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_products_with_auth(self):
        """get_products should work with authenticated identity."""
        with stub_impl("get_products") as mock_tool, resolved_as(self.mock_identity):
            mock_tool.return_value = GetProductsResponse(products=[])

            result = await self.handler._dispatch_skill("get_products", {"brief": "test campaign"}, AuthContext())

            assert result is not None
            mock_tool.assert_called_once()

    # (Deleted) test_create_media_buy_requires_auth / test_update_media_buy_requires_auth.
    #
    # Both passed a deliberately INCOMPLETE parameter bag ({"product_ids": [...]},
    # {"media_buy_id": ...}) and asserted an auth refusal. That only held while auth ran
    # before validation. Validation runs first now -- deliberately: there is no reason to
    # authenticate a request pydantic already knows is malformed -- so the same bag raises
    # AdCPInvalidRequestError, which is the correct answer to a malformed request.
    #
    # The obligation they were reaching for (an auth-required skill refuses an
    # unauthenticated caller) is graded on the wire by BDD across mcp/a2a/rest -- AUTH_MISSING
    # appears in 18 feature files -- rather than by one transport's unit test built on a
    # payload that never reaches the auth check.

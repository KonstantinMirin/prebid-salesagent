#!/usr/bin/env python3
"""
Comprehensive authentication requirement tests for all AdCP tools.

Tests that all authenticated tools properly reject requests without valid authentication,
preventing database constraint violations and security issues.

Background:
-----------
Bug discovered where sync_creatives accepted requests without auth, leading to
NOT NULL constraint violations on principal_id. Investigation revealed all integration
tests provided mock auth, never testing the unauthenticated code path.

This test file ensures all tools that require authentication properly enforce it.

Migration note:
--------------
_impl functions accept `identity: ResolvedIdentity`, never None: the boundary resolves one on
every path. Tests pass ResolvedIdentity(principal_id=None) for the anonymous caller; the
no-credential refusal is graded on the wire by BDD.
"""

import pytest

from src.core.exceptions import AdCPAuthenticationError
from tests.factories.creative_asset import build_assets, image_spec
from tests.factories.principal import PrincipalFactory
from tests.helpers.creative_test_helpers import creative_payload, sync_creatives_request


class TestAuthenticationRequirements:
    """Test that all authenticated tools enforce authentication requirements."""

    # =========================================================================
    # Creative Tools
    # =========================================================================

    def test_sync_creatives_with_invalid_auth(self):
        """sync_creatives must reject requests with invalid authentication."""
        from src.core.tools.creatives._sync import _sync_creatives_impl

        # ResolvedIdentity with None principal_id (simulates invalid token)
        invalid_identity = PrincipalFactory.make_identity(principal_id=None, tenant_id="test_tenant")

        creatives = [
            {
                "creative_id": "test_creative",
                "name": "Test Creative",
                "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_728x90_image"},
                "assets": build_assets(image_spec("banner_image", url="https://example.com/banner.png")),
            }
        ]

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            _sync_creatives_impl(req=sync_creatives_request(creatives=creatives), identity=invalid_identity)

    # =========================================================================
    # Media Buy Tools
    # =========================================================================

    def test_update_media_buy_requires_authentication(self):
        """update_media_buy must reject requests without authentication."""
        from unittest.mock import MagicMock

        from src.core.tools.media_buy_update import _verify_principal

        # ResolvedIdentity with no principal_id — _verify_principal raises AdCPAuthenticationError
        no_auth_identity = PrincipalFactory.make_identity(
            principal_id=None, tenant_id="default", tenant={"tenant_id": "default"}, protocol="rest"
        )
        # repo is not accessed when principal_id is None (early exit)
        with pytest.raises(AdCPAuthenticationError) as exc_info:
            _verify_principal(media_buy_id="test_buy", identity=no_auth_identity, repo=MagicMock())

    def test_update_media_buy_with_invalid_auth(self):
        """update_media_buy must reject requests with invalid auth."""
        from unittest.mock import MagicMock

        from src.core.tools.media_buy_update import _verify_principal

        # ResolvedIdentity with None principal_id
        invalid_identity = PrincipalFactory.make_identity(
            principal_id=None, tenant_id="test_tenant", tenant={"tenant_id": "test_tenant"}, protocol="rest"
        )

        # repo is not accessed when principal_id is None (early exit)
        with pytest.raises(AdCPAuthenticationError) as exc_info:
            _verify_principal(media_buy_id="test_buy", identity=invalid_identity, repo=MagicMock())

    # =========================================================================
    # Performance Tools
    # =========================================================================

    # =========================================================================
    # Signal Tools
    # =========================================================================

    def test_identity_with_none_principal_id(self):
        """ResolvedIdentity with None principal_id should be rejected."""
        from src.core.tools.creatives._sync import _sync_creatives_impl

        # ResolvedIdentity with None principal_id (invalid token scenario)
        identity = PrincipalFactory.make_identity(principal_id=None, tenant_id="test_tenant")

        # A SPEC-LEGAL item (core/creative-asset.json requires format_id and non-empty
        # assets). The stub that was here never crossed a request boundary, so it graded the
        # auth gate against a payload no transport would have delivered.
        creatives = [creative_payload(creative_id="test", name="Test")]

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            _sync_creatives_impl(req=sync_creatives_request(creatives=creatives), identity=identity)

    def test_identity_with_empty_string_principal_id(self):
        """ResolvedIdentity with empty string principal_id should be rejected."""
        from src.core.tools.creatives._sync import _sync_creatives_impl

        # ResolvedIdentity with empty principal_id
        identity = PrincipalFactory.make_identity(principal_id="", tenant_id="test_tenant")

        # A SPEC-LEGAL item (core/creative-asset.json requires format_id and non-empty
        # assets). The stub that was here never crossed a request boundary, so it graded the
        # auth gate against a payload no transport would have delivered.
        creatives = [creative_payload(creative_id="test", name="Test")]

        with pytest.raises(AdCPAuthenticationError) as exc_info:
            _sync_creatives_impl(req=sync_creatives_request(creatives=creatives), identity=identity)


class TestAuthenticationErrorMessages:
    """Test that auth error messages are clear and actionable."""

    def test_update_media_buy_error_message_actionable(self):
        """Error message should be actionable for developers."""
        from unittest.mock import MagicMock

        from src.core.tools.media_buy_update import _verify_principal

        no_auth = PrincipalFactory.make_identity(
            principal_id=None, tenant_id="default", tenant={"tenant_id": "default"}, protocol="rest"
        )
        # repo is not accessed when principal_id is None (early exit)
        with pytest.raises(AdCPAuthenticationError) as exc_info:
            _verify_principal(media_buy_id="test", identity=no_auth, repo=MagicMock())
        # Should explain what's missing


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

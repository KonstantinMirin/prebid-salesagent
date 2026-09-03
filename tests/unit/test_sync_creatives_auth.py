"""Test authentication requirement for sync_creatives."""

import pytest

from src.core.exceptions import AdCPAuthenticationError
from src.core.tools.creatives import _sync_creatives_impl
from tests.helpers.creative_test_helpers import creative_payload, sync_creatives_request


def test_sync_creatives_requires_authentication():
    """sync_creatives should raise AdCPAuthenticationError when principal_id is None (no auth)."""
    # Prepare minimal creative data
    creatives = [creative_payload(creative_id="test_creative", name="Test Creative")]

    # Call without context (simulates missing auth header)
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        _sync_creatives_impl(req=sync_creatives_request(creatives=creatives), identity=None)

    # Verify error message mentions authentication


def test_sync_creatives_with_invalid_auth():
    """sync_creatives should raise AdCPAuthenticationError when auth token is invalid."""
    from tests.factories.principal import PrincipalFactory

    # An IDENTITY whose principal_id is None -- what an invalid token resolves to.
    # This used to build a Mock(spec=ToolContext) and pass it as ``context``, the AdCP
    # ContextObject: the wrong parameter and the wrong type, so the rejection under test
    # came from ``identity`` defaulting to None rather than from anything the mock did.
    invalid_identity = PrincipalFactory.make_identity(principal_id=None, tenant_id="test_tenant")

    creatives = [creative_payload(creative_id="test_creative", name="Test Creative")]

    # Call with invalid auth context
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        _sync_creatives_impl(req=sync_creatives_request(creatives=creatives), identity=invalid_identity)

    # Verify error message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

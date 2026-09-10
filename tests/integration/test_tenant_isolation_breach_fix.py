"""Integration tests for tenant isolation breach fix.

These tests verify tenant isolation works correctly with a real database.
"""

import pytest


@pytest.mark.requires_db
def test_no_fallback_to_first_tenant(integration_db):
    """Test that we never fall back to the first active tenant (the original bug)."""
    from src.core.config_loader import current_tenant, get_current_tenant
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Tenant

    # Create multiple tenants
    with get_db_session() as session:
        tenant1 = Tenant(
            tenant_id="tenant_first",
            name="First Tenant",
            subdomain="first",
            is_active=True,
        )
        tenant2 = Tenant(
            tenant_id="tenant_second",
            name="Second Tenant",
            subdomain="second",
            is_active=True,
        )
        session.add_all([tenant1, tenant2])
        session.commit()

    # Clear tenant context
    current_tenant.set(None)

    # Try to get tenant without setting context
    # Should raise RuntimeError, not return tenant_first
    with pytest.raises(RuntimeError) as exc_info:
        get_current_tenant()


# (Retired) test_tenant_isolation_with_valid_subdomain and test_cross_tenant_token_rejected
# drove get_principal_from_context, the pre-boundary resolver, and presented the removed
# x-adcp-auth alias. Their claim -- a credential minted for one tenant must not act on
# another -- is graded on the wire across a2a, mcp and rest by
# tests/bdd/features/BR-SECURITY-002-tenant-isolation.feature, with BOTH tenants' data
# present so a leak has something to leak. Calling one internal function could never have
# caught a transport that skipped it.

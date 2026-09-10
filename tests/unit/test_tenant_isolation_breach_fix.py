"""Unit tests for tenant isolation breach fix.

These tests verify the security fixes work without requiring a database:

1. get_current_tenant() now raises RuntimeError instead of falling back to default tenant
2. get_principal_from_context() now raises ToolError if tenant cannot be determined from headers
3. Global token lookup is prevented when tenant detection fails

Bug Report:
- User called wonderstruck endpoint with valid token
- Got back products from test-agent tenant
- Root cause: Tenant detection failed, fell back to global token lookup, which found test-agent principal

Security Fixes:
1. Removed dangerous fallback in get_current_tenant() that returned first active tenant
2. Added tenant detection requirement - reject requests if tenant can't be determined
3. Fail loudly with clear error messages instead of silently using wrong tenant
"""

import pytest


def test_get_current_tenant_fails_without_context():
    """Test that get_current_tenant() raises error instead of falling back."""
    from src.core.config_loader import current_tenant, get_current_tenant

    # Clear any existing tenant context
    current_tenant.set(None)

    # Should raise RuntimeError, not return a default tenant
    with pytest.raises(RuntimeError) as exc_info:
        get_current_tenant()


# (Retired) The tests here that drove get_principal_from_context went with it. That
# function was the pre-boundary resolver, deleted for having zero production callers.
# What they GRADED -- a credential minted for one tenant must not act on another, and a
# buyer must not see another tenant's rows -- is graded on the wire now, across all three
# transports, by tests/bdd/features/BR-SECURITY-002-tenant-isolation.feature. That is a
# stronger grader than these were: they called one internal function directly, so they
# could not have caught a transport that skipped it.

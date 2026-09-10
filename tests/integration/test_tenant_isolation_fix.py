"""Tenant resolution branches that only the resolver can show, driven through the resolver.

These tests used to call ``src.core.auth.get_principal_from_context`` and present an
``x-adcp-auth`` header. Both are gone: that function was the pre-boundary resolver, deleted
for having zero production callers, and the alias was removed from the credential seam (pinned
3.1.1 L2/authentication.mdx says the credential MUST travel in ``Authorization``). A test that
drives a deleted function with a rejected header grades nothing, however green it reads.

What they CLAIMED is still true and still worth grading, so the claims move to
``_resolve_identity`` -- the one resolver, reached the way production reaches it, with the
credential in the header production actually reads.

Two branches live here and nowhere else. The cross-tenant claims this module also carried are
NOT here: they are graded on the wire, across all three transports, by
tests/bdd/features/BR-SECURITY-002-tenant-isolation.feature, which is strictly stronger than
calling one function directly -- a transport that skipped the resolver entirely would satisfy
a direct call and fail the wire.
"""

import pytest

from src.core.resolved_identity import _resolve_identity
from tests.factories import PrincipalFactory, TenantFactory
from tests.harness._base import BareIntegrationEnv
from tests.helpers.credentials import credential_headers

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def test_a_token_alone_discovers_its_own_tenant(integration_db):
    """No header names a tenant, so the TOKEN does — the global-lookup branch.

    ``get_principal_from_token`` searches globally when ``_detect_tenant`` matched nothing,
    and adopts the tenant the principal belongs to. That is the one path where the tenant is
    learned AFTER the credential check rather than before it, which is why the resolver builds
    the lazy context at the end rather than the start.
    """
    with BareIntegrationEnv(tenant_id="tenant_global") as env:
        tenant = TenantFactory(tenant_id="tenant_global", subdomain="global", ad_server="mock")
        PrincipalFactory(
            tenant=tenant,
            principal_id="principal_global",
            access_token="global_principal_token",
        )
        env.get_session()  # commit factory data so the resolver's own session sees it

        # No Host, no x-adcp-tenant: nothing in the request names a seller.
        identity = _resolve_identity(headers=credential_headers(token="global_principal_token"), protocol="mcp")

    assert identity.principal_id == "principal_global"
    assert identity.tenant_id == "tenant_global", (
        "a token that belongs to exactly one tenant must resolve that tenant when no header names one"
    )
    assert identity.tenant is not None and identity.tenant.tenant_id == "tenant_global"


def test_an_admin_token_resolves_the_tenant_its_subdomain_names(integration_db):
    """The admin-token branch: a tenant's own admin credential, scoped by the addressed tenant.

    Distinct from the principal branch above -- the token matches ``Tenant.admin_token`` rather
    than any ``Principal.access_token``, and the principal it yields is synthesised as
    ``{tenant_id}_admin``. It is still tenant-SCOPED: the lookup compares the admin token only
    against the tenant the request addressed.
    """
    with BareIntegrationEnv(tenant_id="tenant_admin_test") as env:
        TenantFactory(
            tenant_id="tenant_admin_test",
            subdomain="admin-test",
            ad_server="mock",
            admin_token="admin_test_admin_token",
        )
        env.get_session()

        identity = _resolve_identity(
            headers=credential_headers(token="admin_test_admin_token", tenant="admin-test"),
            protocol="mcp",
        )

    assert identity.tenant_id == "tenant_admin_test", "the addressed subdomain must survive an admin-token login"
    assert identity.principal_id == "tenant_admin_test_admin"

"""One seam for tests that must reach past identity resolution.

Identity is resolved in exactly one place -- ``src/core/tools/_boundary.invoke_tool``, via
``src.core.resolved_identity.resolve_identity``. Tests whose subject is something ELSE (the
exception-handler stack, a tool's own logic) previously reached past it with FastAPI's
``app.dependency_overrides[_resolve_auth_dep]``. That dependency is gone: the route has no
identity dependency to override, because the route no longer resolves.

So there is one patch point, and this is it. Patching the resolver is also more honest than
the override was -- the override could express an identity the wire never carried, and did:
it treated ANY non-None identity as an already-resolved valid token, so REST answered
AUTH_MISSING to a caller who HAD presented a credential while every other transport answered
AUTH_INVALID (GH #1886).

Tests whose subject IS the credential decision must not use this. They belong on the wire,
where BDD grades them across every transport.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from src.core.resolved_identity import ResolvedIdentity


@contextmanager
def resolved_as(identity: ResolvedIdentity | None = None) -> Iterator[ResolvedIdentity]:
    """Make the boundary resolve to *identity* instead of touching the database.

    Defaults to an anonymous identity with a tenant, which is what a discovery route sees.
    """
    if identity is None:
        from src.core.tenant_context import TenantContext

        identity = ResolvedIdentity(
            principal_id=None,
            tenant_id="test_tenant",
            tenant=TenantContext(tenant_id="test_tenant"),
            protocol="rest",
        )
    with patch("src.core.resolved_identity.resolve_identity", return_value=identity):
        yield identity

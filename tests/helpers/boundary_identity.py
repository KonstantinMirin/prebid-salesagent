"""One seam for tests that must reach past identity resolution.

Identity is resolved in exactly one place -- ``src/core/tools/_boundary.invoke_tool``, via
``src.core.resolved_identity._resolve_identity``. Tests whose subject is something ELSE (the
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
from tests.factories.principal import PrincipalFactory

#: The one patch target. Spelled once, here, and nowhere else in tests/.
#:
#: ``ruff-boundary.toml`` bans IMPORTING ``_resolve_identity`` outside the boundary, which a
#: ``mock.patch`` string sails straight past -- a patch names a module path, it does not import
#: it. So the ban cannot police this, and the sixteen REST tests that each spelled
#: ``"src.core.resolved_identity.resolve_identity"`` in a decorator are exactly how the seam's
#: location ends up recorded in sixteen places and renamed in one.
_RESOLVER = "src.core.resolved_identity._resolve_identity"


def resolves_to(identity: ResolvedIdentity):
    """``resolved_as`` as a DECORATOR, for tests that take the mock as an argument.

    ``mock.patch`` objects are both, so this is the same substitution wearing the shape a
    ``@patch(...)``-decorated test already has. It exists so migrating those tests is a change
    of name, not a rewrite of every test body into a ``with`` block -- a rewrite is where
    assertions get dropped by accident.
    """
    return patch(_RESOLVER, return_value=identity)


@contextmanager
def resolved_as(identity: ResolvedIdentity | None = None) -> Iterator[ResolvedIdentity]:
    """Make the boundary resolve to *identity* instead of touching the database.

    Defaults to an anonymous identity with a tenant, which is what a discovery route sees.
    """
    if identity is None:
        from src.core.tenant_context import TenantContext

        identity = PrincipalFactory.make_identity(
            principal_id=None,
            tenant_id="test_tenant",
            tenant=TenantContext(tenant_id="test_tenant"),
            protocol="rest",
        )
    with patch("src.core.resolved_identity._resolve_identity", return_value=identity):
        yield identity


@contextmanager
def refused_as(error: Exception) -> Iterator[Exception]:
    """Make the boundary REFUSE, raising *error* instead of touching the database.

    The counterpart to ``resolved_as``. Resolution both resolves and refuses -- a protected
    tool's refusal happens INSIDE it, which is what makes the postcondition ("returns a
    resolved principal or raises") worth relying on. A test that grades what happens on a
    refusal therefore has to make the resolver raise, not return something unusable.

    Before the collapse a test could inject an identity carrying a tenant and no principal
    and watch a downstream guard reject it. That state is now unconstructable: the tools
    declare auth="required", so resolution refuses first and nothing partial reaches them.
    """
    with patch("src.core.resolved_identity._resolve_identity", side_effect=error):
        yield error

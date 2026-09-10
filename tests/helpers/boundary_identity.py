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
from typing import Any
from unittest.mock import patch

from src.core.resolved_identity import ResolvedIdentity
from tests.factories.principal import PrincipalFactory
from tests.harness.transport import NO_IDENTITY_OVERRIDE

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
def resolved_as(identity: Any = NO_IDENTITY_OVERRIDE) -> Iterator[ResolvedIdentity]:
    """Make the boundary resolve to *identity* instead of touching the database.

    ``None`` and "no argument" are DIFFERENT, and conflating them is a defect this function
    shipped with. It defaulted on ``identity is None``, so a caller saying "resolve to no
    identity" got the default instead: an anonymous identity carrying ``tenant_id`` of
    ``test_tenant``. BR-UC-010's "no tenant can be resolved from the request context"
    scenarios dispatch with exactly that None, so they were handed a tenant, sailed past
    ``get_adcp_capabilities``'s ``if not tenant: return minimal`` guard, and failed further in
    -- grading the opposite of what they say. A sentence in a feature file and the state the
    request actually carried have to be the same thing.

    ``NO_IDENTITY_OVERRIDE`` is the repo's existing sentinel for this exact distinction
    (tests/harness/transport.py, "scoped to the identity-argument omission disease"), reused
    rather than re-invented.

    * omitted or ``None`` -> an anonymous caller WITH a tenant. That is what a dispatch means
      by ``identity=None``: NO CREDENTIAL, not "no seller". A buyer who presents nothing still
      connected to a host, and the host is what names the tenant -- the request payload cannot
      (``get-adcp-capabilities-request.json`` has no field identifying a seller), so the
      connection is the only channel there is.
    * an identity -> that identity, verbatim. A scenario whose subject is a request naming NO
      tenant passes one explicitly, principal and tenant both None, rather than borrowing
      ``None`` from the credential-less case. Those are different states and each sentence in
      a feature file must produce its own; sharing one is how a scenario comes to grade the
      opposite of what it says.
    """
    if identity is NO_IDENTITY_OVERRIDE or identity is None:
        from src.core.tenant_context import TenantContext

        # A CONTROLLED tenant carrying only its id, deliberately, because this default serves
        # every scenario that does not name an identity. Making it lazy so it loads the real
        # row was tried and reverted: it fixed BR-UC-010's auth-invariance scenario and broke
        # thirty others, which set tenant policy explicitly and were then overridden by
        # whatever the database happened to hold.
        #
        # The residue is real but narrow. An unauthenticated leg gets this minimal tenant
        # while its authenticated twin gets the row, so a tenant-scoped field like
        # creative_approval_mode differs by auth state IN THE FIXTURE -- never in production,
        # where the host names the same tenant either way. The fix belongs in that scenario's
        # own setup (its unauthenticated leg wants the env's identity minus credentials), not
        # in a default shared by everything.
        identity = PrincipalFactory.make_identity(
            principal_id=None,
            tenant_id="test_tenant",
            tenant=TenantContext(tenant_id="test_tenant"),
            protocol="rest",
        )
    with patch(_RESOLVER, return_value=identity):
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

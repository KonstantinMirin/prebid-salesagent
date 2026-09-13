"""Factory_boy factory for Principal model."""

from __future__ import annotations

from typing import Any

import factory
from factory import LazyAttribute, Sequence, SubFactory

from src.core.credentials import hash_token, token_prefix
from src.core.database.models import Principal
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas import Principal as SchemaPrincipal
from src.core.tenant_context import TenantContext
from tests.factories.core import TenantFactory

_UNSET = object()


def plaintext_token_for(principal_id: str) -> str:
    """The token a test presents for the factory principal *principal_id*.

    Production stores ``sha256(token)`` and never the token, so a test cannot read a
    credential back out of the row it created. The factory derives the plaintext from the
    principal id instead, and the harness derives the same one when it builds the
    ``Authorization`` header, which is what lets the real resolver run in every test.
    """
    return f"tok_test_{principal_id}"


class PrincipalFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Principal
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.tenant_id)
    principal_id = Sequence(lambda n: f"principal_{n:04d}")
    name = LazyAttribute(lambda o: f"Test Advertiser {o.principal_id}")
    # The row stores only the hash. The plaintext a test PRESENTS is derived from the
    # principal id by ``plaintext_token_for`` -- the harness computes the same value, so a
    # credential never has to be read back out of a table that no longer holds it.
    token_hash = LazyAttribute(lambda o: hash_token(plaintext_token_for(o.principal_id)))
    token_prefix = LazyAttribute(lambda o: token_prefix(plaintext_token_for(o.principal_id)))
    platform_mappings = factory.LazyFunction(lambda: {"mock": {"advertiser_id": "test_adv"}})

    @classmethod
    def make_identity(
        cls,
        principal_id: str | None = "test_principal",
        tenant_id: str = "test_tenant",
        protocol: str = "mcp",
        tenant: TenantContext | None | Any = _UNSET,
        account_id: str | None = None,
        **tenant_overrides: object,
    ) -> ResolvedIdentity:
        """Build a ResolvedIdentity without DB persistence.

        Auto-derives tenant dict via TenantFactory.make_tenant().
        A principal always has a tenant: ``tenant=None`` is accepted only for the anonymous
        caller (``principal_id=None``), and ``ResolvedIdentity`` refuses the other pairing.
        Pass **tenant_overrides for domain fields (approval_mode, etc).

        ``account_id`` is DECLARED, not left to **tenant_overrides. It is a
        ``ResolvedIdentity`` field, not a tenant one, so the catch-all swallowed it into the
        tenant dict and the identity came back with account_id=None -- silently, which cost
        an afternoon: the idempotency cache is scoped by (principal, account, key), so a
        test that thought it had set the account was probing a different scope. It is what
        ``enrich_identity_with_account`` resolves onto the identity in production.

        ``tenant`` accepts whatever a test has to hand -- a dict or a ``TenantContext`` --
        and normalizes it. THIS IS THE ONE NORMALIZER. ``ResolvedIdentity.tenant`` is
        typed ``TenantContext | None``, a single type rather than a union, so a dict fails
        validation at construction. Tests are not asked to know that: they pass data and
        this converts it, which is why inline ``ResolvedIdentity(...)`` outside this factory
        fails ``.ast-grep/rules/resolved-identity-constructed-only-by-its-owners.yml``. An inline site
        carries its own copy of the conversion below, and 98 copies is how the previous
        shape broke -- the union widened to fit them instead of them narrowing to fit it.
        """
        resolved_tenant: TenantContext | None = (
            TenantFactory.make_tenant(tenant_id=tenant_id, **tenant_overrides) if tenant is _UNSET else tenant
        )
        if principal_id and resolved_tenant is None:
            raise TypeError("a principal always belongs to a tenant; tenant=None is only for the anonymous caller")
        # The principal the resolver would have loaded for this caller: the factory's own
        # shape (name and the mock platform mapping), so what a tool reads off
        # ``identity.principal`` is what a row would have given it.
        principal = (
            SchemaPrincipal(
                principal_id=principal_id,
                name=f"Test Advertiser {principal_id}",
                platform_mappings={"mock": {"advertiser_id": "test_adv"}},
            )
            if principal_id
            else None
        )
        return ResolvedIdentity(
            principal=principal,
            tenant=resolved_tenant,
            protocol=protocol,
            account_id=account_id,
        )

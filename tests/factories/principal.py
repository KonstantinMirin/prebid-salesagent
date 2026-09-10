"""Factory_boy factory for Principal model."""

from __future__ import annotations

from typing import Any

import factory
from factory import LazyAttribute, Sequence, SubFactory

from src.core.database.models import Principal
from src.core.resolved_identity import ResolvedIdentity
from src.core.testing_hooks import AdCPTestContext
from tests.factories.core import TenantFactory

_UNSET = object()


class PrincipalFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Principal
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.tenant_id)
    principal_id = Sequence(lambda n: f"principal_{n:04d}")
    name = LazyAttribute(lambda o: f"Test Advertiser {o.principal_id}")
    access_token = Sequence(lambda n: f"token_{n:08d}")
    platform_mappings = factory.LazyFunction(lambda: {"mock": {"advertiser_id": "test_adv"}})

    @classmethod
    def make_identity(
        cls,
        principal_id: str | None = "test_principal",
        tenant_id: str = "test_tenant",
        protocol: str = "mcp",
        dry_run: bool = False,
        auth_token: str | None = None,
        tenant: Any = _UNSET,
        testing_context: AdCPTestContext | None | Any = _UNSET,
        account_id: str | None = None,
        **tenant_overrides: object,
    ) -> ResolvedIdentity:
        """Build a ResolvedIdentity without DB persistence.

        Auto-derives tenant dict via TenantFactory.make_tenant().
        Pass explicit tenant=None for auth-error tests.
        Pass **tenant_overrides for domain fields (approval_mode, etc).

        ``account_id`` is DECLARED, not left to **tenant_overrides. It is a
        ``ResolvedIdentity`` field, not a tenant one, so the catch-all swallowed it into the
        tenant dict and the identity came back with account_id=None -- silently, which cost
        an afternoon: the idempotency cache is scoped by (principal, account, key), so a
        test that thought it had set the account was probing a different scope. It is what
        ``enrich_identity_with_account`` resolves onto the identity in production.
        Pass testing_context to override the default (e.g. set
        test_session_id for harness routing).

        ``tenant`` accepts whatever a test has to hand -- a dict, a ``TenantContext``, a
        ``LazyTenantContext``, or None -- and normalizes it. THIS IS THE ONE NORMALIZER.
        ``ResolvedIdentity.tenant`` is typed ``LazyTenantContext | None``, a single type
        rather than a union, so a dict and a hydrated ``TenantContext`` both fail
        validation at construction. Tests are not asked to know that: they pass data and
        this converts it, which is why inline ``ResolvedIdentity(...)`` in a test is capped
        by ``tests/unit/test_architecture_resolved_identity_inline_cap.py``. An inline site
        carries its own copy of the conversion below, and 98 copies is how the previous
        shape broke -- the union widened to fit them instead of them narrowing to fit it.
        """
        resolved_tenant = (
            TenantFactory.make_tenant(tenant_id=tenant_id, **tenant_overrides) if tenant is _UNSET else tenant
        )
        if resolved_tenant is not None:
            from src.core.tenant_context import LazyTenantContext, TenantContext

            if isinstance(resolved_tenant, dict):
                resolved_tenant = TenantContext.from_dict(resolved_tenant)
            if isinstance(resolved_tenant, TenantContext):
                # ``already`` wraps a row the caller already holds, so nothing queries.
                resolved_tenant = LazyTenantContext.already(resolved_tenant)
        # An explicit ``testing_context=None`` MEANS none, and is not the same as omitting
        # the argument. The sentinel keeps them apart: without it, a caller converted from
        # an inline ``ResolvedIdentity(..., testing_context=None)`` silently acquired the
        # default context below, and a test reading ``if identity.testing_context`` would
        # take the other branch.
        if testing_context is _UNSET:
            testing_context = AdCPTestContext(
                dry_run=dry_run,
                mock_time=None,
                jump_to_event=None,
                test_session_id=None,
            )
        return ResolvedIdentity(
            principal_id=principal_id,
            tenant_id=tenant_id,
            tenant=resolved_tenant,
            auth_token=auth_token,
            protocol=protocol,
            testing_context=testing_context,
            account_id=account_id,
        )

"""The rows the create_media_buy setup-checklist gate grades.

``_create_media_buy_impl`` calls ``validate_setup_complete(tenant_id)`` unconditionally,
and a tenant is "set up" only when every CRITICAL task in
``SetupChecklistService._check_critical_tasks`` is complete. The gate used to be skipped
for a caller that set the testing context's ``dry_run`` -- every create_media_buy test set
it -- and that channel is gone (a1b79d22d), so a tenant such a test drives now needs the
real rows.

A fixture normally seeds the tasks a media buy visibly needs: the ad server, the currency,
a product, a principal. The two here are the ones nothing else in a test wants, so they
are the two every create_media_buy fixture was missing:

* an ``AuthorizedProperty`` -- the "Authorized Properties" task counts rows for the
  tenant; and
* a ``TenantAuthConfig`` with SSO on -- single-tenant deployments make
  ``sso_configuration`` critical (``_is_multi_tenant_mode()``), and the integration suite
  runs single-tenant.

The third half of "SSO configured" is ``auth_setup_mode=False``, which is a column on the
TENANT and so stays with whoever creates it: pass it to ``TenantFactory`` /
``create_tenant_with_timestamps``.
"""

from __future__ import annotations

from typing import Any

from tests.utils.database_helpers import bind_factories_to_session


def seed_setup_checklist_rows(session: Any, tenant: Any) -> None:
    """Give *tenant* the two setup-checklist rows a create_media_buy test needs.

    *tenant* is the persisted ``Tenant``, passed rather than looked up: the factories
    declare ``tenant`` as a SubFactory, so omitting it would seed a SECOND tenant instead
    of attaching to this one. The caller must flush the tenant first.
    """
    from tests.factories import AuthorizedPropertyFactory, TenantAuthConfigFactory

    with bind_factories_to_session(session):
        AuthorizedPropertyFactory(tenant=tenant)
        TenantAuthConfigFactory(tenant=tenant, oidc_enabled=True)

"""The operator's publisher-authorization actions, and the publishers' files they read.

Three admin actions read a publisher's adagents.json to decide whether it authorizes THIS
agent: syncing publisher partners, verifying pending authorized properties, and opening a
partner's properties. :class:`PublisherAuthorizationEnv` drives each through its admin
route on a Flask test client, with the real tenant row, URL derivation, SDK resolution and
database writes. The one thing replaced is the publisher's origin, by
:class:`PublisherAdagentsMixin`.

In process only. The live server dials a publisher through adcp's ``fetch_adagents``,
whose pinned dialer refuses every private address and takes no override, and every
origin the compose stack serves is private -- so on the live stack no scenario can choose
what a publisher's file says. ``local-publisher-authorization.feature`` states the same.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from adcp.exceptions import AdagentsNotFoundError

from src.core.config import get_settings
from src.core.database.models import AuthorizedProperty, PublisherPartner
from tests.harness._base import IntegrationEnv
from tests.helpers.admin_session import admin_auth_session

#: Every module that binds ``fetch_adagents`` for this seller's own authorization check.
#: Patched together, so whichever action a scenario drives reads the same publisher.
_FETCH_ADAGENTS_SITES = (
    "src.admin.blueprints.publisher_partners.fetch_adagents",
    "src.services.property_verification_service.fetch_adagents",
    "src.services.property_discovery_service.fetch_adagents",
)


class PublisherAdagentsMixin:
    """Serves each publisher's adagents.json from a document the scenario wrote.

    The publisher's origin is a system this seller does not own, so it is the one seam.
    A domain no scenario gave a document answers as a missing file does
    (``AdagentsNotFoundError``), never as an empty authorization.

    Host env must be a ``BaseTestEnv`` (relies on ``_guard`` so both release paths stop
    the patchers).
    """

    if TYPE_CHECKING:
        # Declared, not implemented: composed only with BaseTestEnv, which owns the
        # cleanup registry (the same declaration EgressHatchMixin makes).
        def _guard(self, label: str, cleanup: Callable[[], None]) -> None: ...

    _adagents_documents: dict[str, dict[str, Any]]

    def adagents_document(self, domain: str) -> dict[str, Any]:
        """The document *domain* serves, created empty and served from the first call on."""
        if not hasattr(self, "_adagents_documents"):
            self._adagents_documents = {}
            for site in _FETCH_ADAGENTS_SITES:
                patcher = patch(site, side_effect=self._serve_adagents)
                patcher.start()
                self._guard(f"adagents:{site}", patcher.stop)
        return self._adagents_documents.setdefault(domain, {"authorized_agents": [], "properties": []})

    async def _serve_adagents(self, publisher_domain: str, **_options: Any) -> dict[str, Any]:
        document = self._adagents_documents.get(publisher_domain)
        if document is None:
            raise AdagentsNotFoundError(publisher_domain)
        return document


class PublisherAuthorizationEnv(PublisherAdagentsMixin, IntegrationEnv):
    """Drive the three admin actions that read a publisher's file, and read what they wrote."""

    _admin_app: Any = None

    # ── deployment and tenant state ───────────────────────────────────────

    def deploy_in_production(self) -> None:
        """Run as a production deployment for this env's lifetime.

        Anywhere else partner sync verifies every partner without reading its file
        (``Settings.publisher_auto_verify_allowed``), so the check under test only runs
        in production. The settings field is patched where every reader reads it.
        """
        patcher = patch.object(get_settings().runtime, "production", True)
        patcher.start()
        self._guard("production", patcher.stop)

    def run_ad_server(self, adapter_type: str) -> None:
        """Give the tenant an adapter configuration of *adapter_type*."""
        from tests.factories import AdapterConfigFactory

        AdapterConfigFactory(tenant=self._tenant(), adapter_type=adapter_type)

    def pending_property(self, *, property_id: str, publisher_domain: str) -> None:
        """An authorized website property of *publisher_domain*, waiting for verification."""
        from tests.factories import AuthorizedPropertyFactory

        AuthorizedPropertyFactory(
            tenant=self._tenant(),
            property_id=property_id,
            publisher_domain=publisher_domain,
            verification_status="pending",
        )

    # ── the operator's actions ────────────────────────────────────────────

    def sync_publisher_partners(self) -> Any:
        return self._admin_request("post", "publisher-partners/sync")

    def verify_pending_properties(self) -> Any:
        return self._admin_request("post", "authorized-properties/verify-all")

    def open_partner_properties(self, publisher_domain: str) -> Any:
        partner = self.partner(publisher_domain)
        return self._admin_request("get", f"publisher-partners/{partner.id}/properties")

    # ── read-backs ────────────────────────────────────────────────────────

    def partner(self, publisher_domain: str) -> PublisherPartner:
        (partner,) = self._fresh(PublisherPartner, publisher_domain=publisher_domain)
        return partner

    def properties_from(self, publisher_domain: str) -> list[AuthorizedProperty]:
        return self._fresh(AuthorizedProperty, publisher_domain=publisher_domain)

    def authorized_property(self, property_id: str) -> AuthorizedProperty:
        (prop,) = self._fresh(AuthorizedProperty, property_id=property_id)
        return prop

    # ── internals ─────────────────────────────────────────────────────────

    def _tenant(self) -> Any:
        tenant, _principal = self.setup_default_data()
        return tenant

    def _fresh(self, model: type, **filters: Any) -> list:
        """Rows the admin request committed in its own session, not this session's cache."""
        self.get_session().expire_all()
        return self.query(model, tenant_id=self._tenant_id, **filters)

    def _admin_request(self, method: str, path: str) -> Any:
        """One authenticated request to the tenant's admin route at *path*.

        The app is composed from the settings object this env already holds, so the
        deployment a Given set is the one the app is composed and served under; left to
        itself ``create_app`` loads a fresh object and drops it. Over https, because a
        production app marks its session cookie Secure.
        """
        from src.admin.app import create_app

        self._commit_factory_data()
        if self._admin_app is None:
            self._admin_app = create_app(settings=get_settings())
            self._admin_app.config["TESTING"] = True
            self._admin_app.config["WTF_CSRF_ENABLED"] = False
        with self._admin_app.test_client() as client:
            admin_auth_session(client, self._tenant_id)
            return getattr(client, method)(f"/tenant/{self._tenant_id}/{path}", base_url="https://localhost")

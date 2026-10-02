"""Integration tests for the inventory profiles admin blueprint.

Tests profile list, create, edit, and delete via Flask test client.
Requires PostgreSQL (integration_db fixture).
"""

import json

import pytest
from sqlalchemy import delete, select

from src.admin.app import create_app
from src.admin.blueprints import inventory_profiles as inventory_profiles_module
from src.core.database.database_session import get_db_session
from src.core.database.models import InventoryProfile, Tenant
from tests.factories import AuthorizedPropertyFactory, InventoryProfileFactory, TenantFactory
from tests.helpers import concurrent_commit_in_write_window, operator_answer
from tests.utils.database_helpers import create_tenant_with_timestamps

app = create_app()

pytestmark = [pytest.mark.admin, pytest.mark.requires_db]

_TENANT_ID = "inv_prof_test_tenant"


@pytest.fixture
def client():
    """Flask test client with test configuration."""
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SESSION_COOKIE_PATH"] = "/"
    with app.test_client() as client:
        yield client


@pytest.fixture
def test_tenant(integration_db):
    """Create a test tenant for inventory profile tests."""
    with get_db_session() as session:
        try:
            session.execute(delete(InventoryProfile).where(InventoryProfile.tenant_id == _TENANT_ID))
            session.execute(delete(Tenant).where(Tenant.tenant_id == _TENANT_ID))
            session.commit()
        except Exception:
            session.rollback()

        tenant = create_tenant_with_timestamps(
            tenant_id=_TENANT_ID,
            name="Inventory Profile Test Tenant",
            subdomain="inv-prof-test",
            # The host this tenant is served at; mandatory on every tenant.
            virtual_host="inv-prof-test.real-configured-domain.test",
            ad_server="mock",
            is_active=True,
        )
        session.add(tenant)
        session.commit()

    return _TENANT_ID


def _auth_session(client, tenant_id):
    """Set up authenticated session for test client."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["user"] = {"email": "test@example.com", "is_super_admin": True}
        sess["email"] = "test@example.com"
        sess["tenant_id"] = tenant_id
        sess["test_user"] = "test@example.com"
        sess["test_user_role"] = "super_admin"
        sess["test_user_name"] = "Test User"
        sess["test_tenant_id"] = tenant_id


def _create_sample_profile(tenant_id: str, name: str = "Sample Profile", profile_id: str = "sample_profile") -> int:
    """Create a sample inventory profile in the database. Returns the PK id."""
    from datetime import UTC, datetime

    with get_db_session() as session:
        profile = InventoryProfile(
            tenant_id=tenant_id,
            profile_id=profile_id,
            name=name,
            description="A sample profile for testing",
            inventory_config={"ad_units": [], "placements": [], "include_descendants": False},
            format_ids=[{"agent_url": "https://formats.example.com", "id": "display_300x250_image"}],
            publisher_properties=[
                {
                    "publisher_domain": f"{tenant_id}.example.com",
                    "property_tags": ["all_inventory"],
                    "selection_type": "by_tag",
                }
            ],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(profile)
        session.commit()
        return profile.id


class TestInventoryProfileList:
    """Test the inventory profiles list page."""

    def test_list_returns_200(self, client, test_tenant):
        """GET /tenant/<tid>/inventory-profiles/ returns 200."""
        _auth_session(client, test_tenant)
        response = client.get(f"/tenant/{test_tenant}/inventory-profiles/")
        assert response.status_code == 200

    def test_list_shows_profile_names(self, client, test_tenant):
        """JSON API list endpoint includes names of existing profiles.

        The /tenant/<tid>/inventory-profiles/ HTML page is client-side rendered
        via JavaScript that fetches /api/list, so profile names never appear in
        the server-rendered HTML. This test verifies the JSON API contract that
        backs the page, not the rendered markup.
        """
        _auth_session(client, test_tenant)
        _create_sample_profile(test_tenant, name="Visible Profile", profile_id="visible_profile")

        response = client.get(f"/tenant/{test_tenant}/inventory-profiles/api/list")
        assert response.status_code == 200
        payload = response.get_json()
        names = [p["name"] for p in payload["profiles"]]
        assert "Visible Profile" in names


class TestInventoryProfileCreate:
    """Test inventory profile creation."""

    def test_create_form_returns_200(self, client, test_tenant):
        """GET /tenant/<tid>/inventory-profiles/add returns 200."""
        _auth_session(client, test_tenant)
        response = client.get(f"/tenant/{test_tenant}/inventory-profiles/add")
        assert response.status_code == 200

    def test_create_profile_with_tags_saves_to_db(self, client, test_tenant, factory_session):
        """POST with valid tag-based config creates a profile."""
        # The tag names the publishers of the tenant's authorized properties (#1845).
        AuthorizedPropertyFactory(tenant=factory_session.get(Tenant, test_tenant))
        _auth_session(client, test_tenant)
        response = client.post(
            f"/tenant/{test_tenant}/inventory-profiles/add",
            data={
                "name": "New Tag Profile",
                "profile_id": "new_tag_profile",
                "description": "Created via test",
                "targeted_ad_unit_ids": "[]",
                "targeted_placement_ids": "[]",
                "formats": json.dumps([{"agent_url": "https://formats.example.com", "id": "display_300x250_image"}]),
                "property_mode": "tags",
                "property_tags": "all_inventory",
            },
            follow_redirects=False,
        )
        # Redirect indicates success (profile saved)
        assert response.status_code in (302, 303)

        with get_db_session() as session:
            profile = session.scalars(
                select(InventoryProfile).where(
                    InventoryProfile.tenant_id == test_tenant,
                    InventoryProfile.profile_id == "new_tag_profile",
                )
            ).first()
        assert profile is not None
        assert profile.name == "New Tag Profile"

    def test_create_profile_missing_name_redirects_without_creation(self, client, test_tenant):
        """POST without a name redirects back without creating a profile."""
        _auth_session(client, test_tenant)
        response = client.post(
            f"/tenant/{test_tenant}/inventory-profiles/add",
            data={
                "formats": json.dumps([{"id": "display_300x250_image"}]),
                "property_mode": "tags",
                "property_tags": "all_inventory",
            },
            follow_redirects=False,
        )
        assert response.status_code in (302, 303)

        with get_db_session() as session:
            count = len(
                list(session.scalars(select(InventoryProfile).where(InventoryProfile.tenant_id == test_tenant)).all())
            )
        assert count == 0

    def test_create_profile_missing_formats_redirects_without_creation(self, client, test_tenant):
        """POST without formats redirects back without creating a profile."""
        _auth_session(client, test_tenant)
        response = client.post(
            f"/tenant/{test_tenant}/inventory-profiles/add",
            data={
                "name": "No Formats Profile",
                "formats": "[]",
                "property_mode": "tags",
                "property_tags": "all_inventory",
            },
            follow_redirects=False,
        )
        assert response.status_code in (302, 303)

        with get_db_session() as session:
            prop = session.scalars(
                select(InventoryProfile).where(
                    InventoryProfile.tenant_id == test_tenant,
                    InventoryProfile.name == "No Formats Profile",
                )
            ).first()
        assert prop is None


class TestInventoryProfileDelete:
    """Test inventory profile deletion."""

    def test_delete_profile_removes_from_db(self, client, test_tenant):
        """POST delete removes the profile from the database."""
        _auth_session(client, test_tenant)
        profile_pk = _create_sample_profile(test_tenant, name="Delete Me Profile", profile_id="delete_me_profile")

        response = client.post(
            f"/tenant/{test_tenant}/inventory-profiles/{profile_pk}/delete",
            follow_redirects=False,
        )
        assert response.status_code in (302, 303)

        with get_db_session() as session:
            profile = session.get(InventoryProfile, profile_pk)
        assert profile is None

    def test_delete_nonexistent_profile_returns_404(self, client, test_tenant):
        """DELETE for a nonexistent profile returns 404."""
        _auth_session(client, test_tenant)
        response = client.delete(
            f"/tenant/{test_tenant}/inventory-profiles/999999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestAddInventoryProfileDuplicateId:
    """POST /tenant/<id>/inventory-profiles/add — duplicate profile_id.

    ``uq_inventory_profile`` is the authority, and the loser of the race must be answered
    like any refusal rather than with raw psycopg2 text in the flash, so the grading
    compares the whole answer — status, redirect target and flash — against the winner's.
    The loser runs first so its pre-check is genuinely clean.
    """

    PROFILE_ID = "contested_profile"

    def _form(self):
        return {
            "name": "Contested Profile",
            "profile_id": self.PROFILE_ID,
            "targeted_ad_unit_ids": "[]",
            "targeted_placement_ids": "[]",
            "formats": json.dumps([{"agent_url": "https://formats.example.com", "id": "display_300x250_image"}]),
            "property_mode": "tags",
            "property_tags": "all_inventory",
        }

    def test_winner_and_loser_get_the_same_answer(self, client, factory_session):
        # An authorized property is required to reach the write window at all: the
        # "tags" selection names the publishers whose properties carry the tag, and the
        # add route refuses a selection naming none BEFORE it ever gets to the
        # uq_inventory_profile write this test grades.
        tenant = TenantFactory(virtual_host="contested-profile.real-configured-domain.test")
        AuthorizedPropertyFactory(tenant=tenant)
        _auth_session(client, tenant.tenant_id)

        def post_add():
            return client.post(
                f"/tenant/{tenant.tenant_id}/inventory-profiles/add",
                data=self._form(),
                follow_redirects=False,
            )

        def commit_conflicting_row():
            InventoryProfileFactory(tenant=tenant, profile_id=self.PROFILE_ID)

        with concurrent_commit_in_write_window(inventory_profiles_module, commit_conflicting_row):
            loser = operator_answer(client, post_add())

        winner = operator_answer(client, post_add())

        assert winner == (
            302,
            f"/tenant/{tenant.tenant_id}/inventory-profiles/add",
            [("error", f"Inventory profile with ID '{self.PROFILE_ID}' already exists")],
        )
        assert loser == winner


class TestProfileSelectorsNamePublishers:
    """A profile's ``tags`` and ``property_ids`` modes name each property's own publisher.

    AdCP 3.1.1 ``core/product.json`` admits only the singular ``publisher_domain`` form on a
    product, and ``core/publisher-property-selector.json`` makes property IDs
    publisher-scoped, so selections spanning publishers are one selector per publisher. The
    domain is the authorized property's ``publisher_domain`` -- never the host the seller's
    agent answers on, which is no publisher's (#1845).
    """

    @staticmethod
    def _seller(virtual_host: str):
        tenant = TenantFactory(virtual_host=virtual_host)
        AuthorizedPropertyFactory(
            tenant=tenant, property_id="news_home", publisher_domain="news.example", tags=["premium"]
        )
        AuthorizedPropertyFactory(
            tenant=tenant, property_id="sports_home", publisher_domain="sports.example", tags=["premium"]
        )
        AuthorizedPropertyFactory(
            tenant=tenant, property_id="weather_home", publisher_domain="weather.example", tags=["standard"]
        )
        return tenant

    @staticmethod
    def _form(profile_id: str, **selection):
        return {
            "name": f"Profile {profile_id}",
            "profile_id": profile_id,
            "targeted_ad_unit_ids": "[]",
            "targeted_placement_ids": "[]",
            "formats": json.dumps([{"agent_url": "https://formats.example.com", "id": "display_300x250_image"}]),
            **selection,
        }

    @staticmethod
    def _stored(session, tenant_id: str, profile_id: str):
        session.expire_all()
        return session.scalars(
            select(InventoryProfile).where(
                InventoryProfile.tenant_id == tenant_id, InventoryProfile.profile_id == profile_id
            )
        ).first()

    def test_tags_mode_names_each_publisher_carrying_the_tag(self, client, factory_session):
        tenant = self._seller("seller-tags.example.test")
        _auth_session(client, tenant.tenant_id)

        client.post(
            f"/tenant/{tenant.tenant_id}/inventory-profiles/add",
            data=self._form("by_tag_profile", property_mode="tags", property_tags="premium"),
        )

        profile = self._stored(factory_session, tenant.tenant_id, "by_tag_profile")
        assert profile is not None
        assert profile.publisher_properties == [
            {"publisher_domain": "news.example", "property_tags": ["premium"], "selection_type": "by_tag"},
            {"publisher_domain": "sports.example", "property_tags": ["premium"], "selection_type": "by_tag"},
        ]

    def test_property_ids_mode_groups_ids_under_their_publishers(self, client, factory_session):
        tenant = self._seller("seller-ids.example.test")
        _auth_session(client, tenant.tenant_id)

        client.post(
            f"/tenant/{tenant.tenant_id}/inventory-profiles/add",
            data={
                **self._form("by_id_profile", property_mode="property_ids"),
                "selected_property_ids": ["news_home", "weather_home"],
            },
        )

        profile = self._stored(factory_session, tenant.tenant_id, "by_id_profile")
        assert profile is not None
        assert profile.publisher_properties == [
            {"publisher_domain": "news.example", "property_ids": ["news_home"], "selection_type": "by_id"},
            {"publisher_domain": "weather.example", "property_ids": ["weather_home"], "selection_type": "by_id"},
        ]

    def test_edit_regroups_by_publisher(self, client, factory_session):
        tenant = self._seller("seller-edit.example.test")
        profile = InventoryProfileFactory(tenant=tenant, profile_id="edited_profile")
        _auth_session(client, tenant.tenant_id)

        client.post(
            f"/tenant/{tenant.tenant_id}/inventory-profiles/{profile.id}/edit",
            data={
                **self._form("edited_profile", property_mode="property_ids"),
                "selected_property_ids": ["sports_home", "news_home"],
            },
        )

        stored = self._stored(factory_session, tenant.tenant_id, "edited_profile")
        assert stored.publisher_properties == [
            {"publisher_domain": "news.example", "property_ids": ["news_home"], "selection_type": "by_id"},
            {"publisher_domain": "sports.example", "property_ids": ["sports_home"], "selection_type": "by_id"},
        ]

    def test_a_tag_no_authorized_property_carries_is_refused(self, client, factory_session):
        tenant = self._seller("seller-orphan.example.test")
        _auth_session(client, tenant.tenant_id)

        answer = operator_answer(
            client,
            client.post(
                f"/tenant/{tenant.tenant_id}/inventory-profiles/add",
                data=self._form("orphan_profile", property_mode="tags", property_tags="podcast"),
            ),
        )

        assert answer == (
            302,
            f"/tenant/{tenant.tenant_id}/inventory-profiles/add",
            [("error", "No authorized property carries the tags: podcast")],
        )
        assert self._stored(factory_session, tenant.tenant_id, "orphan_profile") is None

    def test_the_form_offers_no_agent_host_default(self, client, factory_session):
        tenant = self._seller("seller-form.example.test")
        profile = InventoryProfileFactory(tenant=tenant, profile_id="form_profile")
        _auth_session(client, tenant.tenant_id)

        add_page = client.get(f"/tenant/{tenant.tenant_id}/inventory-profiles/add")
        edit_page = client.get(f"/tenant/{tenant.tenant_id}/inventory-profiles/{profile.id}/edit")

        assert add_page.status_code == edit_page.status_code == 200
        assert "seller-form.example.test" not in add_page.get_data(as_text=True)
        assert "seller-form.example.test" not in edit_page.get_data(as_text=True)

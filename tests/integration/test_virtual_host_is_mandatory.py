"""A tenant always declares the host it is served at, and every publisher reads that one.

``virtual_host`` is the only statement of where a tenant answers. A tenant holding none is
not merely unpublishable: since the routing change in PR #2191 there are exactly two ways
to name a tenant — ``Host`` against ``tenants.virtual_host``, and the ``x-adcp-tenant``
literal id — so a host-less tenant is UNREACHABLE by ``Host`` at all. The defect this
module grades is that every creation path produced exactly such a tenant, and the readers
then papered over it by INVENTING a host: ``canonical_agent_url`` fell through to
``http://localhost:{port}`` and published it as the tenant's public A2A endpoint, while the
adagents.json verifier invented a different one on the same row. Inventing a host is what
took A2A conformance from 30 passing checks to 0 (#1845) — a name nothing on the network
served, followed by every client that trusted the card.

So the rule is the column's, not each reader's: a tenant cannot exist without a host, and
no code derives one. These tests drive the outer surfaces that rule has to hold at — the
admin form that writes the row and the card route that publishes it.

Two facts about the shared fixtures are recorded here because they decide whether these
tests grade anything at all:

* ``authenticated_admin_session`` puts a DICT in ``session["user"]``, while production
  stores a string email (``src/admin/blueprints/auth.py``, ``oidc.py``). ``create_tenant``
  appends that value to ``authorized_emails``, so under the fixture shape the route writes
  a dict into a list-of-strings column and every later read of the row fails pydantic
  validation. These tests set the production shape; grading the route against the fixture
  shape would grade a route no deployment runs.
* ``create_tenant`` is ``@require_auth(admin_only=True)``, so the session email must be the
  one the fixture seeds as ``super_admin_emails``.
"""

import pytest
from starlette.testclient import TestClient

#: A host under the test TLD the storyboard seed established. Nothing routes to it on a
#: test box; it exists so a stored origin can be compared against what a reader publishes.
ORIGIN = "mandatory-vhost.adcp.test"
ADMIN_EMAIL = "test@example.com"


def _stored_host(tenant_id: str) -> str | None:
    """The host the row actually holds, read the one way a tenant is loaded by id.

    ``TenantContext.load`` rather than a session of our own: it is the sanctioned read
    (CLAUDE.md Pattern #8 bans ``get_db_session()`` in a test body), and it is the same
    projection every production reader sees, so this grades what the card would publish.
    """
    from src.core.tenant_context import TenantContext

    loaded = TenantContext.load(tenant_id)
    return loaded.virtual_host if loaded else None


def _tenant_exists(tenant_id: str) -> bool:
    from src.core.tenant_context import TenantContext

    return TenantContext.load(tenant_id) is not None


def _as_production_admin(client) -> None:
    """Give the session the shape production writes — a string email, not a dict."""
    with client.session_transaction() as sess:
        sess["user"] = ADMIN_EMAIL


@pytest.mark.requires_db
def test_a_ui_created_tenants_card_publishes_its_stored_origin(authenticated_admin_session, integration_db):
    """THE ACCEPTANCE: drive a UI-created tenant's card and assert it publishes the stored origin.

    The two halves have to be graded together. The form writing the host and the card
    reading it are the only pair that can tell "the operator's host is published" from
    "some host is published" — which is how ``http://localhost:8080`` came to be a
    UI-created tenant's advertised public endpoint.
    """
    from src.app import app

    _as_production_admin(authenticated_admin_session)

    response = authenticated_admin_session.post(
        "/create_tenant",
        data={"name": "Mandatory Vhost", "subdomain": "mandatory_vhost", "virtual_host": ORIGIN},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302), response.data[:500]

    stored = _stored_host("tenant_mandatory_vhost")
    assert stored == ORIGIN, f"the admin form did not store the host the operator submitted, it stored {stored!r}"

    card = TestClient(app).get("/.well-known/agent-card.json", headers={"Host": ORIGIN})
    assert card.status_code == 200, card.text
    urls = [interface["url"] for interface in card.json()["supportedInterfaces"]]
    assert urls == [f"https://{ORIGIN}/a2a"], f"the card published {urls}, not the origin the operator stored"


@pytest.mark.requires_db
def test_the_admin_form_refuses_to_create_a_tenant_with_no_host(authenticated_admin_session, integration_db):
    """A submission naming no host creates no tenant.

    Asks whether the TENANT exists rather than whether its host is None, deliberately: once
    the column refuses NULL those two questions collapse, and a host-is-None assertion could
    not tell "refused" from "created host-less" while the defect was present.
    """
    _as_production_admin(authenticated_admin_session)

    authenticated_admin_session.post(
        "/create_tenant",
        data={"name": "No Host", "subdomain": "no_host"},
        follow_redirects=False,
    )

    assert not _tenant_exists("tenant_no_host"), "a tenant was created despite naming no host"


@pytest.mark.requires_db
def test_the_column_itself_refuses_a_tenant_with_no_host(integration_db):
    """The rule lives on the column, so a creation path added later cannot miss it.

    Every creation path writes through the ORM validator, which is why refusing there — and
    not in each of the eight paths — is what makes a host-less tenant unrepresentable.
    """
    from src.core.database.models import Tenant

    with pytest.raises(ValueError):
        Tenant(tenant_id="host_less", name="Host Less", subdomain="host_less", virtual_host=None)

    with pytest.raises(ValueError):
        Tenant(tenant_id="host_blank", name="Host Blank", subdomain="host_blank", virtual_host="   ")


@pytest.mark.requires_db
def test_every_publisher_of_this_tenants_agent_url_names_the_same_origin(monkeypatch, integration_db):
    """The adagents.json verifier and the card name ONE origin for one tenant.

    A counterparty fetches adagents.json and byte-matches the agent URL it finds there
    against the one the card published. Two derivations of "where is this tenant" are two
    chances to disagree, and there is no diagnostic when they do — the check simply fails.

    ``ADCP_AGENT_URL`` is set on the settings OBJECT rather than the environment: production
    reads a field off settings built once, so an env write lands only before the first read.
    A deployment-wide override must not outrank the tenant's own stored host, because that
    is how every tenant collapses onto one URL.
    """
    from src.admin.blueprints.authorized_properties import _construct_agent_url
    from src.core.agent_identity import canonical_agent_url
    from src.core.config import get_settings
    from tests.factories import TenantFactory
    from tests.harness import ProductEnv

    monkeypatch.setattr(get_settings().runtime, "adcp_agent_url", "https://some-other-deployment.example.org")

    with ProductEnv(tenant_id="pub-origin-t", principal_id="pub-origin-p") as env:
        tenant = TenantFactory(tenant_id="pub-origin-t", virtual_host=ORIGIN)
        env._commit_factory_data()

        from src.core.tenant_context import TenantContext

        published = canonical_agent_url(TenantContext(tenant_id=tenant.tenant_id, virtual_host=tenant.virtual_host))
        verified = _construct_agent_url("pub-origin-t", None)

        assert verified == published, (
            f"the adagents.json verifier derived {verified!r} while the card publishes {published!r}"
        )
        assert published == f"https://{ORIGIN}", f"the published origin is not the stored host: {published!r}"


@pytest.mark.requires_db
def test_a_seller_with_no_publisher_partners_names_its_own_domain(integration_db):
    """With no partners, the seller's portfolio names the domain it is actually served at.

    Asserts EQUALITY with the tenant's own hostname, not a ``.example.com`` suffix. The BDD
    scenarios that touch this placeholder assert only the suffix, and ``TenantFactory``
    mints ``vhost-NNNN.example.com`` — so they pass both with the fabricated
    ``{subdomain}.example.com`` and with the fix, and nothing else in the suite can tell the
    two apart.
    """
    from src.core.http_utils import hostname_of
    from src.core.resolved_identity import public_identity_for
    from src.services.seller_capabilities import describe_seller
    from tests.factories import PrincipalFactory, TenantFactory
    from tests.harness import ProductEnv

    with ProductEnv(tenant_id="placeholder-t", principal_id="placeholder-p") as env:
        tenant = TenantFactory(tenant_id="placeholder-t", subdomain="placeholdert", virtual_host=ORIGIN)
        PrincipalFactory(tenant=tenant, principal_id="placeholder-p")
        env._commit_factory_data()

        seller = describe_seller(public_identity_for({"host": ORIGIN}))
        assert seller.media_buy is not None, "the seller declared no media_buy block, so nothing names a domain"
        domains = [str(domain.root) for domain in seller.media_buy.portfolio.publisher_domains]

        assert domains == [hostname_of(ORIGIN)], f"the portfolio named {domains}, not the seller's own domain"

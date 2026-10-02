"""A publisher's adagents.json that names this agent's MCP or A2A endpoint authorizes it.

The pinned spec (AdCP 3.1.1) calls ``authorized_agents[].url`` the "Agent's API endpoint
URL" (``docs/governance/property/adagents.mdx``), its seller-setup example authorizes
``https://ads.streamhaus.example/mcp`` (``docs/brand-protocol/seller-setup.mdx``), and
``docs/reference/url-canonicalization.mdx`` keeps the path in the comparison. Each of the
three places this seller reads a publisher's file for its own authorization -- the
publisher-partner properties view, property verification and property discovery -- must
read an endpoint entry as naming the tenant, and an entry for another agent as not.

``fetch_adagents`` is the one thing replaced: it is the network edge. The tenant row, the
URL derivation, the SDK's resolution and the database writes are all real.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src.admin.app import create_app
from src.admin.blueprints.publisher_partners import get_publisher_properties
from src.core.database.models import AuthorizedProperty
from src.services.property_discovery_service import PropertyDiscoveryService
from src.services.property_verification_service import PropertyVerificationService
from tests.factories import AuthorizedPropertyFactory, PublisherPartnerFactory, TenantFactory
from tests.harness._base import IntegrationEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

PUBLISHER = "endpoint-publisher.example.com"

#: Entry spellings that name the tenant's agent. ``{origin}`` is the tenant's
#: ``agent_url``; ``{ORIGIN}`` is the same origin upper-cased, which canonicalization folds.
NAMING_THE_AGENT = ["{origin}", "{origin}/mcp", "{origin}/mcp/", "{origin}/a2a", "{ORIGIN}/mcp/"]


def _spell(template: str, origin: str) -> str:
    return template.format(origin=origin, ORIGIN=origin.upper())


def _adagents(entry_url: str) -> dict:
    return {
        "authorized_agents": [
            {
                "url": entry_url,
                "authorized_for": "Display inventory",
                "authorization_type": "property_ids",
                "property_ids": ["front_page"],
            }
        ],
        "properties": [
            {
                "property_id": "front_page",
                "property_type": "website",
                "name": "Front page",
                "identifiers": [{"type": "domain", "value": PUBLISHER}],
            }
        ],
    }


@pytest.fixture
def env(integration_db):
    with IntegrationEnv() as env:
        yield env


@pytest.fixture
def tenant(env):
    return TenantFactory(virtual_host="sales.endpoint-seller.example.com")


def _partner_properties(tenant, entry_url: str) -> dict:
    partner = PublisherPartnerFactory(tenant=tenant, publisher_domain=PUBLISHER)
    with (
        create_app().test_request_context(),
        patch(
            "src.admin.blueprints.publisher_partners.fetch_adagents",
            new_callable=AsyncMock,
            return_value=_adagents(entry_url),
        ),
    ):
        result = get_publisher_properties(tenant.tenant_id, partner.id)
    # The refusal answers ``(response, 200)``; the success answers the bare response.
    response = result[0] if isinstance(result, tuple) else result
    return response.get_json()


@pytest.mark.parametrize("template", NAMING_THE_AGENT)
def test_partner_properties_accept_an_entry_naming_the_agent(tenant, template):
    body = _partner_properties(tenant, _spell(template, tenant.agent_url))

    assert body["is_authorized"] is True
    assert body["property_ids"] == ["front_page"]


def test_partner_properties_refuse_an_entry_naming_another_agent(tenant):
    body = _partner_properties(tenant, "https://other-seller.example.com/mcp")

    assert body["is_authorized"] is False


def _verify(env, tenant, entry_url: str) -> tuple[bool, str | None, str]:
    prop = AuthorizedPropertyFactory(
        tenant=tenant,
        publisher_domain=PUBLISHER,
        property_type="website",
        identifiers=[{"type": "domain", "value": PUBLISHER}],
        verification_status="pending",
    )
    adagents = {
        "authorized_agents": [
            {
                "url": entry_url,
                "authorized_for": "Display inventory",
                "authorization_type": "inline_properties",
                "properties": [
                    {
                        "property_type": "website",
                        "name": "Front page",
                        "identifiers": [{"type": "domain", "value": PUBLISHER}],
                    }
                ],
            }
        ]
    }
    with patch(
        "src.services.property_verification_service.fetch_adagents", new_callable=AsyncMock, return_value=adagents
    ):
        verified, error = PropertyVerificationService().verify_property(
            tenant.tenant_id, prop.property_id, tenant.agent_url
        )

    session = env.get_session()
    session.rollback()
    row = session.scalars(
        select(AuthorizedProperty).filter_by(tenant_id=tenant.tenant_id, property_id=prop.property_id)
    ).one()
    return verified, error, row.verification_status


@pytest.mark.parametrize("template", NAMING_THE_AGENT)
def test_verification_accepts_an_entry_naming_the_agent(env, tenant, template):
    verified, error, status = _verify(env, tenant, _spell(template, tenant.agent_url))

    assert (verified, error, status) == (True, None, "verified")


def test_verification_refuses_an_entry_naming_another_agent(env, tenant):
    verified, _error, status = _verify(env, tenant, "https://other-seller.example.com/mcp")

    assert (verified, status) == (False, "failed")


async def _discover(env, tenant, entry_url: str) -> list[str]:
    with patch(
        "src.services.property_discovery_service.fetch_adagents",
        new_callable=AsyncMock,
        return_value=_adagents(entry_url),
    ):
        await PropertyDiscoveryService().sync_properties_from_adagents(
            tenant.tenant_id, [PUBLISHER], agent_url=tenant.agent_url
        )

    session = env.get_session()
    session.rollback()
    return list(session.scalars(select(AuthorizedProperty.name).filter_by(tenant_id=tenant.tenant_id)))


@pytest.mark.asyncio
@pytest.mark.parametrize("template", NAMING_THE_AGENT)
async def test_discovery_syncs_the_properties_of_an_entry_naming_the_agent(env, tenant, template):
    assert await _discover(env, tenant, _spell(template, tenant.agent_url)) == ["Front page"]


@pytest.mark.asyncio
async def test_discovery_syncs_nothing_from_an_entry_naming_another_agent(env, tenant):
    assert await _discover(env, tenant, "https://other-seller.example.com/mcp") == []

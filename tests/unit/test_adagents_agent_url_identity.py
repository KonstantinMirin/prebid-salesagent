"""Which ``authorized_agents[].url`` values in a publisher's adagents.json name this agent.

The pinned spec (AdCP 3.1.1) describes the entry ``url`` as the "Agent's API endpoint URL"
(``docs/governance/property/adagents.mdx``), and its own seller-setup example authorizes
``https://ads.streamhaus.example/mcp`` (``docs/brand-protocol/seller-setup.mdx``). URL
canonicalization (``docs/reference/url-canonicalization.mdx``) preserves the path, so the
origin and the origin plus ``/mcp`` are different identifiers. A publisher that writes our
MCP or A2A endpoint must still be read as authorizing us; one that names another agent
must not.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from adcp.adagents import get_properties_by_agent, verify_agent_authorization

from src.core.agent_identity import adagents_scoped_to_agent, canonical_agent_url, identifies_agent

TENANT = SimpleNamespace(virtual_host="sales.example.com")
AGENT_URL = canonical_agent_url(TENANT)


@pytest.mark.parametrize(
    "entry_url",
    [
        "https://sales.example.com",
        "https://sales.example.com/",
        "https://sales.example.com/mcp",
        "https://sales.example.com/mcp/",
        "https://sales.example.com/a2a",
        "https://sales.example.com/a2a/",
        # Steps 1, 2 and 4: scheme and host fold to lower case, the default port drops.
        "HTTPS://Sales.Example.COM/mcp",
        "https://sales.example.com:443/a2a",
        # Step 8: a fragment never takes part in the comparison.
        "https://sales.example.com/mcp#section",
    ],
)
def test_an_entry_naming_the_origin_or_an_endpoint_identifies_the_agent(entry_url):
    assert identifies_agent(entry_url, AGENT_URL)


@pytest.mark.parametrize(
    "entry_url",
    [
        "https://other.example.com/mcp",
        "https://evil.sales.example.com",
        "https://sales.example.com.evil.example/mcp",
        # Step 1: the scheme is preserved, so http and https never match.
        "http://sales.example.com/mcp",
        # Step 4: a non-default port is a different authority.
        "https://sales.example.com:8443/mcp",
        # A path this agent does not serve.
        "https://sales.example.com/api",
        "https://sales.example.com/mcp/extra",
        "https://sales.example.com/.well-known/adcp/sales",
        # Step 7: the query is part of the identifier.
        "https://sales.example.com/mcp?x=1",
        # Step 3: an authority with no host is rejected, not canonicalized.
        "https:///mcp",
        "",
        None,
        42,
    ],
)
def test_an_entry_naming_anything_else_does_not(entry_url):
    assert not identifies_agent(entry_url, AGENT_URL)


def test_the_agent_url_side_is_canonicalized_too():
    assert identifies_agent("https://sales.example.com/mcp", "HTTPS://SALES.EXAMPLE.COM/")


def _document(*entries):
    return {
        "authorized_agents": list(entries),
        "properties": [
            {
                "property_id": pid,
                "property_type": "website",
                "name": pid,
                "identifiers": [{"type": "domain", "value": f"{pid}.example"}],
            }
            for pid in ("news", "sport", "other")
        ],
    }


def _entry(url, *property_ids):
    return {
        "url": url,
        "authorized_for": "test",
        "authorization_type": "property_ids",
        "property_ids": list(property_ids),
    }


def test_scoping_lets_the_sdk_authorize_an_endpoint_entry():
    document = _document(_entry("https://sales.example.com/mcp", "news"))

    scoped = adagents_scoped_to_agent(document, AGENT_URL)

    assert verify_agent_authorization(scoped, AGENT_URL)
    assert [p["property_id"] for p in get_properties_by_agent(scoped, AGENT_URL)] == ["news"]


def test_scoping_unions_every_entry_that_names_the_agent_and_drops_the_rest():
    document = _document(
        _entry("https://sales.example.com", "news"),
        _entry("https://sales.example.com/a2a", "sport"),
        _entry("https://other.example.com", "other"),
    )

    scoped = adagents_scoped_to_agent(document, AGENT_URL)

    assert sorted(p["property_id"] for p in get_properties_by_agent(scoped, AGENT_URL)) == ["news", "sport"]
    assert scoped["properties"] == document["properties"]


def test_scoping_a_document_that_names_another_agent_authorizes_nothing():
    scoped = adagents_scoped_to_agent(_document(_entry("https://other.example.com/mcp", "news")), AGENT_URL)

    assert not verify_agent_authorization(scoped, AGENT_URL)
    assert get_properties_by_agent(scoped, AGENT_URL) == []


def test_scoping_leaves_a_malformed_document_for_the_sdk_to_refuse():
    document = {"authorized_agents": "not a list"}

    assert adagents_scoped_to_agent(document, AGENT_URL) is document

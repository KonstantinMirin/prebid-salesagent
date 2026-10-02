"""Steps for the locally-added adagents.json publication feature.

WHAT MAKES THESE NON-VACUOUS. Every value asserted is read off the FETCHED document. The
seeded state always includes a property on ANOTHER publisher's domain, so a lookup that
dropped the domain filter would claim it, and the own-host property is pending, so a
lookup that filtered on verification would serve nothing. The host-on-a-port scenario
stores the port in ``virtual_host``, so a lookup by ``virtual_host`` instead of its
hostname finds no property and answers 404.

The authorized-property Given is the UC-010 one
(``uc010_capabilities.given_authorized_property``), which also seeds a property on the
tenant's own host.
"""

from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.helpers.adcp_pin import EXPECTED_SPEC_VERSION
from tests.helpers.pinned_schema import validate_against_pinned_schema

ADAGENTS_PATH = "/.well-known/adagents.json"


@given(parsers.parse("the tenant is served on port {port:d} of its host"))
def given_tenant_served_on_port(ctx: dict, port: int) -> None:
    """Store the origin with a port, the way an operator declares a non-default one.

    ``configure_tenant_field`` writes the ``tenants`` row, so its ``virtual_host``
    validator re-derives the stored hostname, and the live server reads the same row.
    """
    ctx["env"].configure_tenant_field("virtual_host", f"{ctx['tenant'].virtual_host_name}:{port}")


@when("the buyer fetches adagents.json naming the seller by Host")
def when_fetch_adagents_by_host(ctx: dict) -> None:
    ctx["adagents_response"] = ctx["env"].fetch_agent_card(path=ADAGENTS_PATH, host=ctx["tenant"].virtual_host)


def _adagents_document(ctx: dict) -> dict:
    """The parsed document, or a loud failure naming what came back instead."""
    response = ctx["adagents_response"]
    assert response.status_code == 200, (
        f"GET {ADAGENTS_PATH} returned {response.status_code}, so there is no document to read: {response.text[:300]!r}"
    )
    return dict(response.json())


@then("no adagents.json is published")
def then_no_adagents(ctx: dict) -> None:
    response = ctx["adagents_response"]
    assert response.status_code == 404, (
        f"a host that owns no property must publish no adagents.json; got {response.status_code} "
        f"{response.text[:300]!r}. With neither sales authorization nor catalog content the pinned "
        f"schema rejects the file, and a missing file is what tells a buyer 'not authorized here'"
    )
    assert "authorized_agents" not in response.text, f"the 404 carried an adagents body: {response.text[:300]!r}"


@then("the adagents.json validates against the pinned schema")
def then_adagents_schema_valid(ctx: dict) -> None:
    validate_against_pinned_schema(f"{EXPECTED_SPEC_VERSION}/adagents.json", _adagents_document(ctx))


@then("the adagents.json claims only the property on the tenant's own host")
def then_adagents_claims_own_host_only(ctx: dict) -> None:
    own_host = ctx["tenant"].virtual_host_name
    claimed = [
        prop["publisher_domain"]
        for entry in _adagents_document(ctx)["authorized_agents"]
        for prop in entry.get("properties") or []
    ]
    assert claimed == [own_host], (
        f"the document served at {own_host!r} claimed {claimed}. It speaks for the one property on that "
        f"host and no other: a property on another publisher's domain is authorized by that "
        f"publisher's own adagents.json"
    )

"""E2E: a counterparty resolves our signing keys from our published trust root.

TDD RED for #1291 A3 (salesagent-z6nr.9), step 9 as amended by R-H2.

This walks the SDK's own three-hop discovery (``adcp.signing.async_resolve_agent``)
against the live Docker stack, and is the only test in the A3 suite that grades
the documents as a real counterparty consumes them rather than as we build them.

Two deliberate seams, each with its reason:

1. **Hop 1 is seeded** (``_capabilities_client_factory``). Two independent reasons,
   and either alone would be sufficient:

   * *SDK divergence #4.* ``_fetch_capabilities`` does a raw ``GET <agent_url>``
     and requires a JSON object body, while security.mdx:1142 says the opposite
     verbatim — "invoke ``get_adcp_capabilities`` via the agent's declared
     transport (MCP ``tools/call`` or A2A skill invocation), **not** a raw HTTP
     ``GET``". Our ``/mcp`` answers GET with a redirect to an SSE stream and
     ``/a2a`` is JSON-RPC POST, so an unseeded hop 1 fails no matter what A3
     publishes.
   * *``identity`` is still gated.* ``capability_declarations._UNBACKED_BLOCKS``
     lists ``identity`` and ``validate_backing`` rejects it by name, so a REAL
     capabilities response carries no ``identity`` and hop 2 would raise
     ``brand_json_url_missing`` before brand.json is ever fetched. Un-gating it is
     D1's scope (salesagent-z6nr.20), DOWNSTREAM of A3.

   So the seeded body's ``identity`` is built from **A3's own** helpers, and the
   test asserts the values the resolver ends up using are those helpers' output.
   That assertion is what makes D1's later reuse of this module GRADED rather than
   hoped for: when D1 emits ``identity`` for real, it must emit these strings.

2. **Hops 2 and 3 are live.** No ``_brand_jwks_client_factory`` is passed —
   brand.json and the JWKS are fetched from the running stack over real HTTP,
   because those two hops are the ones A3 owns.

``allow_private_destinations=True`` is a TEST argument only: it relaxes the SDK's
SSRF pin so an ``http://localhost:<port>`` stack is reachable. Nothing in A3's
production path reads it (the real gate belongs to B1, salesagent-z6nr.12, where
the verifier actually runs).
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import delete

from tests.e2e.utils import live_db_env

_SLUG = "trustroot_e2e"
_TENANT_ID = "tr_e2e"


def _netloc(url: str) -> str:
    return httpx.URL(url).netloc.decode()


def _origin(url: str) -> str:
    parsed = httpx.URL(url)
    return f"{parsed.scheme}://{parsed.netloc.decode()}"


def _seeded_capabilities_factory(body: dict):
    """A ``_capabilities_client_factory`` that serves *body* for hop 1.

    ``async_resolve_agent`` calls ``factory(agent_url)`` and uses the result as an
    async context manager, so an ``httpx.AsyncClient`` over a ``MockTransport`` is
    a drop-in — no monkeypatching of the SDK.
    """

    def factory(_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))

    return factory


def _drop_tenant(live_server: dict) -> None:
    """Remove this test's tenant and its children from the shared e2e database.

    Children go first, explicitly: the ORM ``backref`` relationships carry no
    delete cascade, so an ORM ``session.delete(tenant)`` tries to NULL a child's
    ``tenant_id`` — which is half of its composite primary key. The FK's
    ``ON DELETE CASCADE`` only applies to a database-level delete.
    """
    from src.core.database.models import AuthorizedProperty, SigningKey, Tenant

    with live_db_env(live_server) as env:
        session = env.get_session()
        for model in (SigningKey, AuthorizedProperty, Tenant):
            session.execute(delete(model).where(model.tenant_id == _TENANT_ID))
        session.commit()


@pytest.fixture
def trust_root_tenant(live_server):
    """A tenant whose canonical agent URL IS the live stack, plus one signing key.

    ``virtual_host`` is set to the stack's own host:port so that
    ``canonical_agent_url`` resolves to somewhere the resolver can actually reach —
    otherwise hops 2 and 3 would be pointed at a domain that does not exist and the
    test would grade nothing. The row is removed afterwards: ``virtual_host`` is
    host-routing state shared by the whole e2e session.
    """
    from tests.factories import AuthorizedPropertyFactory, SigningKeyFactory, TenantFactory

    _drop_tenant(live_server)
    host = _netloc(live_server["mcp"])
    with live_db_env(live_server) as env:
        tenant = TenantFactory(
            tenant_id=_TENANT_ID,
            subdomain=f"seller-{_SLUG}".replace("_", "-"),
            virtual_host=host,
        )
        key = SigningKeyFactory(tenant=tenant, kid=f"adcp-{_SLUG}-key")
        AuthorizedPropertyFactory(tenant=tenant, publisher_domain=host, tags=["premium_news"])
        env._commit_factory_data()
        yield tenant, key

    _drop_tenant(live_server)


@pytest.mark.asyncio
async def test_counterparty_resolves_our_jwks_through_our_published_brand_json(
    docker_services_e2e, live_server, trust_root_tenant
):
    """The full chain: agent URL -> capabilities identity -> brand.json -> JWKS.

    Asserts, in the order a verifier would hit them:

    * the URL we PUBLISH is the URL we are REACHABLE at;
    * every hop the SDK walked succeeded (no ``trace`` entry with status "error");
    * the brand.json entry the resolver matched is the one whose ``url``
      byte-equals the agent card's A2A interface URL — security.mdx step 5, with
      no canonicalization;
    * the ``jwks_uri`` the LIVE document advertised equals ``jwks_uri(tenant)``,
      and its origin equals the ``key_origins`` value we seeded from
      ``jwks_origin(tenant)`` — the consistency check B1's verifier performs, and
      the reason D1 must import this origin rather than re-literal it;
    * the key that comes back is the key we stored.
    """
    from adcp.signing import async_resolve_agent
    from src.core.agent_identity import brand_json_url, canonical_agent_url, jwks_origin, jwks_uri

    from src.core.validation import normalize_agent_url

    tenant, key = trust_root_tenant
    base_url = live_server["mcp"]

    # 1. The URL we publish must be the URL we are reachable at. If this fails, the
    #    scheme derivation in domain_config does not handle the host the stack is
    #    actually served on (e.g. an in-network service name rather than localhost),
    #    and every document below would advertise an unreachable origin.
    assert canonical_agent_url(tenant) == base_url, (
        f"canonical_agent_url must equal the live stack base URL; published "
        f"{canonical_agent_url(tenant)!r}, reachable at {base_url!r}"
    )

    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        card = (await client.get("/.well-known/agent-card.json")).json()
        brand = (await client.get("/.well-known/brand.json")).json()
        adagents = (await client.get("/.well-known/adagents.json")).json()

    agent_url = card["supportedInterfaces"][0]["url"]
    matching = [entry for entry in brand["agents"] if entry["url"] == agent_url]
    assert len(matching) == 1, (
        "brand.json must contain exactly one agents[] entry whose url BYTE-EQUALS the agent card's "
        f"A2A interface URL {agent_url!r} — that is the match security.mdx step 5 performs, with no "
        f"canonicalization; got {[entry['url'] for entry in brand['agents']]}"
    )
    entry_id = matching[0]["id"]

    # 2. Hop 1 seeded from A3's OWN helpers (identity is D1's to emit for real).
    seeded_identity = {
        "brand_json_url": brand_json_url(tenant),
        "key_origins": {"request_signing": jwks_origin(tenant)},
    }
    capabilities_body = {"adcp_version": "3.1.1", "identity": seeded_identity}

    resolution = await async_resolve_agent(
        agent_url,
        agent_type="sales",
        agent_id=entry_id,
        allow_private_destinations=True,
        _capabilities_client_factory=_seeded_capabilities_factory(capabilities_body),
    )

    failed = [hop for hop in resolution.trace if hop.status == "error"]
    assert failed == [], f"every discovery hop must succeed; failed hops: {failed}"

    assert resolution.brand_json_url == brand_json_url(tenant), (
        "the brand.json URL the resolver walked must be the one A3's helper emits — this is the "
        f"string D1 will publish as identity.brand_json_url; got {resolution.brand_json_url!r}"
    )
    assert resolution.agent_entry["url"] == agent_url, (
        f"the matched entry's url must byte-equal the agent URL the call was made to; got "
        f"{resolution.agent_entry['url']!r} vs {agent_url!r}"
    )

    # 3. The jwks_uri comes from the SERVED document, not from the seed — so this is
    #    the assertion that proves the published document and the local helper agree.
    assert resolution.jwks_uri == jwks_uri(tenant), (
        f"the live brand.json advertised {resolution.jwks_uri!r}; A3's helper says "
        f"{jwks_uri(tenant)!r}. These are the same string or key discovery is a coin flip."
    )
    assert _origin(resolution.jwks_uri) == seeded_identity["key_origins"]["request_signing"], (
        "the declared request_signing key origin must equal the origin the JWKS actually resolved "
        f"at — otherwise a verifier raises request_signature_key_origin_mismatch; declared "
        f"{seeded_identity['key_origins']['request_signing']!r}, resolved {_origin(resolution.jwks_uri)!r}"
    )

    assert {jwk["kid"] for jwk in resolution.jwks["keys"]} == {key.kid}, (
        f"the resolved JWKS must carry exactly this tenant's stored key; got "
        f"{sorted(jwk['kid'] for jwk in resolution.jwks['keys'])}, stored {key.kid!r}"
    )

    # 4. adagents' url obeys the OTHER comparison rule: canonicalize both sides
    #    (core/authorized-agent-base.json), never byte-equality. A canonical-by-
    #    construction producer satisfies both rules at once, which is the point.
    adagents_urls = {entry["url"] for entry in adagents["authorized_agents"]}
    assert adagents_urls, "the seeded authorized-property record must yield an authorized_agents entry"
    assert all(normalize_agent_url(url) == normalize_agent_url(agent_url) for url in adagents_urls), (
        "every adagents authorized_agents[].url must canonicalize to the same agent as the brand.json "
        f"entry; got {sorted(adagents_urls)} vs {agent_url!r}"
    )

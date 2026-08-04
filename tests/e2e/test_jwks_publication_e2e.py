"""E2E-0: an origin we ADVERTISE as a key origin serves a key we actually HAVE.

salesagent-mp53.7 (#1291) — the PUBLICATION half of the RFC 9421 instrument, and
deliberately only that half.

**PROVES.** An external process, starting from the tenant's SERVED
``get_adcp_capabilities`` document and holding no ``src`` import on its fetching
path, can locate and fetch a well-formed public key over a real TLS handshake
verified against the stack's CA — and that key's ``kid`` is the ``kid`` a
PRODUCTION provisioning path (the admin route, driven over real HTTP) minted
INSIDE the live stack.

**DOES NOT PROVE.** That this agent can SIGN, or that any signature verifies.
That is salesagent-mp53.3. Keeping the two apart is what makes a later signing
failure attributable to the signer rather than to key discovery.

Why it exists: production shipped ``/.well-known/jwks.json`` serving
``{"keys": []}`` for every tenant while the inbound verifier was mounted and live
(salesagent-7x8t). Nothing caught it because nothing fetched it from outside.

The two mutations this test is built to fail under, both verified by hand:
delete the JWKS route (the last assertions lose their document), and delete the
``key_origins=`` emission in ``emitted_identity`` (the fetcher can no longer
locate the JWKS, and the origin-consistency assertion has nothing to compare).

Why the chain is walked here rather than through ``adcp.signing.async_resolve_agent``:
the SDK's THIRD hop is ``async_default_jwks_fetcher``, which builds its own
``httpx.AsyncClient`` with ``trust_env=False`` and takes no client-factory seam
(``_brand_jwks_client_factory`` reaches hop 2 only). Against a leaf signed by the
private e2e CA that hop can only ever raise ``jwks_fetch_failed`` — a RIG failure
whose one obvious "fix" is ``verify=False``, which would destroy the only property
this module has. So every hop here is fetched over ONE client pinned to the test
CA, and the SDK still supplies the piece that matters: ``check_key_origin_consistency``
is the verifier's mandatory step-7 check, called on the served documents rather than
re-implemented. The plaintext sibling in ``test_trust_root_e2e`` keeps grading the
SDK resolver end to end, where no private CA is in the way.
"""

from __future__ import annotations

import contextlib
from typing import Any

import httpx
import pytest

from tests.e2e._signing_e2e import (
    ca_verified_ssl_context,
    netloc,
    provision_signing_key_via_admin,
    provisioned_trust_root_tenant,
    tls_base_url,
)

_SLUG = "jwkspub_e2e"
_TENANT_ID = "jwkspub_e2e"

#: Where an external process starts. The JWKS URL is never written down here —
#: it is read out of the documents this one leads to.
_CAPABILITIES_PATH = "/api/v1/capabilities"

#: The one operation the tenant declares a ``request_signing`` posture for.
#: ``supported_for``, never ``required_for``: ``/api/v1`` is an AdCP surface for
#: the inbound verifier, so a required bucket could refuse the anonymous fetch
#: this whole test is built on.
_DECLARED_OPERATION = "get_products"

#: What the admin route is asked to mint, and the JWK members that follow from it
#: (``adcp.signing.generate_signing_keypair``).
_ALG = "ed25519"
_EXPECTED_JWK_ALG = "EdDSA"


def _signing_declarations(tenant: Any) -> dict[str, Any]:
    """The capability declaration that makes an ``identity`` block owed.

    ``identity`` is emitted only when ``requires_trust_root`` fires, which a
    NON-EMPTY ``request_signing`` bucket does. ``brand_json_url`` is DERIVED from
    the tenant rather than literalled because the capabilities read path
    cross-checks the declared pointer against the one it actually serves
    (``validate_signing_platform_backing``) and refuses a mismatch.
    """
    from src.core.agent_identity import brand_json_url

    return {
        # ``supported`` is a required member of the block; the non-empty bucket
        # beside it is what actually fires the trigger.
        "request_signing": {"supported": True, "supported_for": [_DECLARED_OPERATION]},
        "identity": {"brand_json_url": brand_json_url(tenant)},
    }


@pytest.fixture
def keyless_declaring_tenant(live_server):
    """A tenant that DECLARES a signing posture and owns NO key, at a caller-supplied netloc.

    A factory rather than a plain fixture so the assertions about *where* the TLS
    listener is happen in the test body and fail as failures, not as fixture-setup
    errors. ``mint_key=False`` is the point of this module's first phase: the key
    must arrive later, through a production transport, or the test grades its own
    fixture.
    """
    stack = contextlib.ExitStack()

    def provision(host: str):
        return stack.enter_context(
            provisioned_trust_root_tenant(
                live_server,
                tenant_id=_TENANT_ID,
                slug=_SLUG,
                host=host,
                mint_key=False,
                declarations_from_tenant=_signing_declarations,
            )
        )

    with stack:
        yield provision


async def _fetch_capabilities(client: httpx.AsyncClient) -> dict[str, Any]:
    """The served capabilities document, fetched anonymously over the CA-verified client.

    Anonymous on purpose: discovery responses describe the SELLER, not the caller
    (AdCP INV-4), and the tenant is resolved from the Host header — which is what
    lets a counterparty holding no credential reach this document at all.
    """
    response = await client.get(_CAPABILITIES_PATH)
    assert response.status_code == 200, (
        f"the capabilities document must be served anonymously over TLS at {_CAPABILITIES_PATH!r}; "
        f"got HTTP {response.status_code}. Body: {response.text[:300]!r}"
    )
    return response.json()


@pytest.mark.asyncio
async def test_advertised_key_origin_serves_a_key_the_tenant_actually_has(
    docker_services_e2e, live_server, keyless_declaring_tenant
):
    """One tenant, two phases against the same live server: MISS, then PUBLICATION.

    One tenant rather than two because a second would need a second dotted TLS
    name, which the stack does not alias — and because a before/after of the SAME
    server is a stronger instrument than two servers' worth of coincidence.
    """
    from adcp.signing import check_key_origin_consistency
    from adcp.signing.errors import SignatureVerificationError

    base_url = tls_base_url(live_server)
    verify = ca_verified_ssl_context()

    # The netloc INCLUDES the port: get_tenant_by_virtual_host matches the Host
    # header as an exact string, and httpx sends the port unless it is the
    # scheme default.
    tenant, key = keyless_declaring_tenant(netloc(base_url))
    assert key is None, "this tenant's key must arrive through a production path, not through the fixture"
    declared_identity = tenant.capability_declarations["identity"]

    # ── Phase A — MISS. No key exists yet. ────────────────────────────────────
    async with httpx.AsyncClient(base_url=base_url, verify=verify, timeout=15.0) as client:
        before = await _fetch_capabilities(client)

    # The POSITIVE half first. "key_origins is absent" is equally satisfied by the
    # identity block being absent ENTIRELY — which is what happens when the seeded
    # declaration failed to take, so requires_trust_root never fires. A green there
    # would grade nothing, which is the exact failure this ticket exists to remove.
    identity_before = before.get("identity")
    assert identity_before is not None, (
        "a tenant declaring a non-empty request_signing bucket on an https origin fires the pinned "
        "identity.brand_json_url required_when trigger, so the served document MUST carry an identity "
        f"block; it carries none. Top-level keys: {sorted(before)}"
    )
    assert identity_before.get("brand_json_url") == declared_identity["brand_json_url"], (
        f"the served identity.brand_json_url must be the trust root this tenant declared and the server "
        f"derives; served {identity_before.get('brand_json_url')!r}, declared "
        f"{declared_identity['brand_json_url']!r}"
    )
    supported_for = (before.get("request_signing") or {}).get("supported_for") or []
    assert _DECLARED_OPERATION in supported_for, (
        f"the served request_signing posture must still name {_DECLARED_OPERATION!r} in supported_for — "
        "that non-empty bucket is what makes the withheld key_origins below a deliberate omission rather "
        f"than an absent posture; served supported_for={supported_for!r}"
    )

    # The MISS itself. This is the distinction the ticket demands the document
    # make: "this tenant has no key" (posture declared, origin withheld) vs "this
    # seller does not publish keys" (no identity at all). A served
    # key_origins.request_signing here is an advertisement for a JWKS that can only
    # answer {"keys": []} — precisely the shape production shipped.
    assert (identity_before.get("key_origins") or {}).get("request_signing") is None, (
        "a tenant with NO provisioned key must not advertise identity.key_origins.request_signing: the "
        'JWKS at that origin can only serve {"keys": []}, and a counterparty that fetches it learns '
        "nothing it can verify against. Served key_origins: "
        f"{identity_before.get('key_origins')!r}"
    )

    # ── Phase B — PUBLICATION. Provision through a production transport. ──────
    # The admin route runs INSIDE the server container, so the row is encrypted
    # under the CONTAINER's KEK — a key the server can actually open later. A
    # runner-minted key would still publish (a JWKS projects the public half only),
    # which is exactly why it would be a green that means nothing.
    provisioned_kid = provision_signing_key_via_admin(base_url, tenant_id=_TENANT_ID, alg=_ALG)

    async with httpx.AsyncClient(base_url=base_url, verify=verify, timeout=15.0) as client:
        after = await _fetch_capabilities(client)

        identity_after = after.get("identity") or {}
        advertised_origin = (identity_after.get("key_origins") or {}).get("request_signing")
        assert advertised_origin, (
            "once the tenant owns a publishable key, the served document must advertise "
            f"identity.key_origins.request_signing — otherwise no counterparty can locate our keys at "
            f"all. Served identity: {identity_after!r}"
        )

        # Hop 2's entry point comes from the SERVED document, never from a helper.
        brand_response = await client.get(identity_after["brand_json_url"])
        assert brand_response.status_code == 200, (
            f"the trust root the served document points at must resolve over TLS at "
            f"{identity_after['brand_json_url']!r}; got HTTP {brand_response.status_code}"
        )
        brand = brand_response.json()

        # Step 5 of the discovery algorithm: the agents[] entry whose url
        # BYTE-EQUALS the endpoint the counterparty invoked, with no
        # canonicalization. Both sides are served documents.
        card = (await client.get("/.well-known/agent-card.json")).json()
        agent_url = card["supportedInterfaces"][0]["url"]
        matching = [entry for entry in brand["agents"] if entry.get("type") == "sales" and entry["url"] == agent_url]
        assert len(matching) == 1, (
            "the served brand.json must carry exactly one sales agents[] entry whose url byte-equals the "
            f"agent card's interface URL {agent_url!r} — that is the match the discovery algorithm "
            f"performs; served {[entry['url'] for entry in brand['agents']]}"
        )
        resolved_jwks_uri = matching[0]["jwks_uri"]

        # Step 7, run by the SDK's own verifier helper rather than re-implemented:
        # the resolved jwks_uri's host must match the declared origin after IDNA
        # canonicalization. Its absence is what raises
        # request_signature_key_origin_mismatch / _missing in a real verifier, so
        # this is the assertion that makes "delete the key_origins emission -> red"
        # bite.
        try:
            check_key_origin_consistency(
                jwks_uri=resolved_jwks_uri,
                key_origins=identity_after.get("key_origins"),
                purpose="request_signing",
            )
        except SignatureVerificationError as exc:
            pytest.fail(
                "the JWKS the served trust root resolves to must satisfy the verifier's key-origin "
                f"consistency check against the served identity.key_origins; declared "
                f"{advertised_origin!r}, resolved {resolved_jwks_uri!r} — {exc}"
            )

        jwks_response = await client.get(resolved_jwks_uri)
        assert jwks_response.status_code == 200, (
            f"the advertised JWKS must resolve over TLS at {resolved_jwks_uri!r}; got HTTP {jwks_response.status_code}"
        )
        jwks = jwks_response.json()

    # The published document, graded member by member. {"keys": []} fails the first
    # of these by construction, not by hope — and "delete the JWKS route -> red"
    # bites here.
    keys = jwks.get("keys") or []
    assert len(keys) == 1, (
        f"the JWKS at the advertised origin must carry exactly the one key this tenant was provisioned "
        f"with; it carries {len(keys)}. An empty key set here is the defect this test exists to catch: "
        f"an advertised origin serving nothing verifiable. Document: {jwks!r}"
    )
    published = keys[0]
    assert published.get("kid") == provisioned_kid, (
        f"the published kid must be the kid the ADMIN ROUTE reported provisioning ({provisioned_kid!r}); "
        f"published {published.get('kid')!r}. A mismatch means the document is serving some other "
        "tenant's key, or a key this deployment did not mint"
    )
    assert published.get("alg") == _EXPECTED_JWK_ALG, (
        f"a key provisioned as {_ALG!r} publishes alg {_EXPECTED_JWK_ALG!r}; got {published.get('alg')!r}"
    )
    assert published.get("kty") and published.get("crv") and published.get("x"), (
        "the published JWK must be well formed — kty, crv and x all present and non-empty, or a "
        f"counterparty has no key material to verify with; got {published!r}"
    )

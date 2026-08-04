"""E2E-3: a webhook THIS SERVER signed verifies against the JWKS THIS SERVER publishes.

salesagent-mp53.3 (#1291) — the SIGNING half of the RFC 9421 instrument, and the leg
``test_jwks_publication_e2e`` (E2E-0, salesagent-mp53.7) deliberately does not cover.

**PROVES.** A real outbound delivery — fired by driving ``create_media_buy`` over A2A
against the live stack, delivered asynchronously by the production webhook sender to a
real HTTP receiver on a real socket — carries an RFC 9421 signature that verifies, and
the public key that verifies it was obtained from nothing but TLS fetches of the
server's OWN published documents (capabilities → ``identity.brand_json_url`` →
``brand.json`` → ``jwks_uri`` → JWKS). The JWKS URL is never written down here. The
signature's ``tag`` is the ``webhook_signing.profile`` the server ADVERTISES on that
same capabilities document — advertised and emitted graded against each other, not
against a literal — and ``content-digest`` is a covered component, so the signature is
over the bytes the receiver read rather than over a header set that ignores them.

**DOES NOT PROVE.** That the published document is well formed, or that its ``kid`` is
the one a production provisioning path minted — that is E2E-0, and keeping the two
apart is what makes a failure here attributable to the SIGNER rather than to key
discovery. Nor that any INBOUND verifier accepts a counterparty's signature (B1).

**"No ``src`` import" — the narrowing, stated so a later grader reads it as deliberate.**
The blanket form ("no ``src`` import in the verifying process") is unsatisfiable: an e2e
runner imports ``src`` for the factories and ``live_db_env``, and the sibling module's
``_signing_declarations`` imports ``src.core.agent_identity`` ON PURPOSE, to DERIVE
``brand_json_url`` rather than literal it. The property that is real, and that this
module holds, is narrower: **no ``src`` import on the VERIFY path**.
:func:`tests.helpers.signing.verify_as_conformant_receiver` reaches only into
``adcp.signing`` — the decision is made by SDK code over wire bytes and a fetched JWKS,
with no production import participating in it.

The two mutations this module is built to fail under, both verified by hand:

* delete the RFC 9421 arm in ``webhook_sender_factory._rfc9421_sender`` → red at the
  "Signature / Signature-Input / Content-Digest are present" assertion;
* delete the JWKS route → red at the discovery hop, because the verifier has no key
  material. If removing the JWKS route leaves this green, the verifier is not fetching
  from the server and this module grades nothing.

Why the tenant has to be the TLS-hosted one rather than the seeded ``ci-test``: the
signing arm is gated on ``origin_is_publishable`` (``src/core/signing/posture.py``),
which is derived from ``tenant.virtual_host``. On a single-label host the posture is
``supported=False`` and every delivery goes out UNSIGNED — which is exactly why the
existing ``test_delivery_webhooks_e2e`` / ``test_a2a_webhook_payload_types`` captures
carry no signature and why assertions could not simply be added to them.
"""

from __future__ import annotations

import copy
from time import sleep
from typing import Any

import httpx
import pytest

from tests.e2e._signing_e2e import (
    ca_verified_ssl_context,
    declaring_tenant_provisioner,
    fetch_capabilities,
    netloc,
    provision_signing_key_via_admin,
    tls_base_url,
)
from tests.e2e._webhook_capture import WebhookCaptureHandler, run_webhook_capture_server
from tests.e2e.adcp_request_builder import build_a2a_message_send, build_adcp_media_buy_request, get_test_date_range
from tests.helpers.signing import verify_as_conformant_receiver
from tests.helpers.webhook_wire import CapturedWebhook, signature_input_label

#: Distinct from ``jwkspub_e2e`` (E2E-0), ``tr_e2e_tls`` (the trust-root module) and
#: ``dn4i_e2e`` (the KEK-mismatch module). All four claim the same TLS ``virtual_host``,
#: which ``get_tenant_by_virtual_host`` matches as an exact string, so only one may hold
#: it at a time — tox runs e2e serially and the seam drops the row at BOTH ends, which
#: makes that an ordering constraint rather than a concurrency one.
_SLUG = "whsig_e2e"
_TENANT_ID = "whsig_e2e"

#: Handed IN to the tenant seam so the yield stays a 2-tuple. A literal rather than the
#: factory's ``Sequence`` because the value has to be known here to authenticate with.
_BUYER_TOKEN = "whsig-e2e-buyer-token"

#: The operation the tenant declares a ``request_signing`` posture for. ``supported_for``
#: rather than ``required_for``: a required bucket could refuse the anonymous capabilities
#: fetch the whole discovery chain starts from.
_DECLARED_OPERATION = "get_products"

_ALG = "ed25519"

#: Long enough for the sender's retry ladder, short enough that a missing delivery is a
#: failure rather than a hang.
_DELIVERY_TIMEOUT_SECONDS = 45.0
_POLL_INTERVAL_SECONDS = 0.5


class _SignedWebhookCapture(WebhookCaptureHandler):
    """This module's own receiver, with its own capture lists.

    Both lists are declared here rather than inherited: they are CLASS attributes on the
    shared handler, so a subclass that declares neither would append into — and read —
    every other e2e suite's captures.
    """

    received_webhooks: list = []
    received_raw: list = []


def _signing_declarations(tenant: Any) -> dict[str, Any]:
    """The capability declaration that makes an ``identity`` block owed.

    ``identity`` is emitted only when ``requires_trust_root`` fires, which a non-empty
    ``request_signing`` bucket does. ``brand_json_url`` is DERIVED from the tenant rather
    than literalled because the capabilities read path cross-checks the declared pointer
    against the one it serves (``validate_signing_platform_backing``) and refuses a
    mismatch. This import is on the SETUP path, never the verify path.
    """
    from src.core.agent_identity import brand_json_url

    return {
        "request_signing": {"supported": True, "supported_for": [_DECLARED_OPERATION]},
        "identity": {"brand_json_url": brand_json_url(tenant)},
    }


@pytest.fixture
def signing_capable_tenant(live_server):
    """A tenant that DECLARES a signing posture, owns NO key, and CAN be bought from.

    ``mint_key=False`` (fixed inside :func:`declaring_tenant_provisioner`) is the point of
    phase A: the key must arrive later through a production transport, or the module
    grades its own fixture. ``buyer_access_token`` is what makes this tenant, unlike the
    sibling ``keyless_declaring_tenant`` fixture in ``test_jwks_publication_e2e``, one this
    module can actually drive a real ``create_media_buy`` against.
    """
    with declaring_tenant_provisioner(
        live_server,
        tenant_id=_TENANT_ID,
        slug=_SLUG,
        declarations_from_tenant=_signing_declarations,
        buyer_access_token=_BUYER_TOKEN,
    ) as provision:
        yield provision


async def _fire_one_delivery(client: httpx.AsyncClient, receiver: dict) -> None:
    """Drive a real ``create_media_buy`` over A2A so production posts a webhook back.

    The ``push_notification_config`` carries NO ``authentication`` block, and that
    omission is what selects the RFC 9421 arm: ``legacy_auth_mode``
    (``webhook_sender_factory.py``) returns ``None`` only for an ABSENT block, and any
    ``{schemes, credentials}`` there would route the delivery down the legacy Bearer arm
    instead — a green that would grade the wrong sender.
    """
    product_id, pricing_option_id = await _discover_product_and_pricing(client)
    start_time, end_time = get_test_date_range(days_from_now=1, duration_days=30)
    message = build_a2a_message_send(
        skill="create_media_buy",
        parameters=build_adcp_media_buy_request(
            product_ids=[product_id],
            total_budget=5000.0,
            start_time=start_time,
            end_time=end_time,
            brand={"domain": "testbrand.com"},
            pricing_option_id=pricing_option_id,
            context={"e2e": "webhook_signature"},
        ),
        push_notification_config={"url": receiver["url"]},
    )
    result = await _post_a2a(client, message, leg="create_media_buy")
    assert "error" not in result, f"the A2A create_media_buy returned an error: {result['error']!r}"


async def _discover_product_and_pricing(client: httpx.AsyncClient) -> tuple[str, str]:
    """The product to buy, read off the wire rather than from the row we seeded.

    ``pricing_option_id`` is DERIVED by production from the pricing row's model/currency/
    fixedness, so reading it back from ``get_products`` is what keeps the create request
    valid without this module restating that derivation rule.
    """
    message = build_a2a_message_send(skill="get_products", parameters={"brand": {"domain": "testbrand.com"}})
    result = await _post_a2a(client, message, leg="get_products")
    products = (_a2a_data_part(result) or {}).get("products") or []
    assert products, (
        "the seeded tenant must expose at least one product with a pricing option, or there is nothing "
        f"to buy and no delivery to sign. A2A response: {str(result)[:600]!r}"
    )
    pricing_options = products[0].get("pricing_options") or []
    assert pricing_options, f"product {products[0].get('product_id')!r} exposes no pricing_options: {products[0]!r}"
    return products[0]["product_id"], pricing_options[0]["pricing_option_id"]


async def _post_a2a(client: httpx.AsyncClient, message: dict[str, Any], *, leg: str) -> dict[str, Any]:
    """POST one A2A JSON-RPC envelope, naming the leg in every failure mode.

    A bare ``httpx.ReadTimeout`` out of a two-request flow says nothing about WHICH
    request hung, which is the difference between a slow discovery hop and a delivery
    that never started.
    """
    try:
        response = await client.post("/a2a", json=message, headers=_buyer_headers())
    except httpx.TimeoutException as exc:
        raise AssertionError(f"the A2A {leg} request timed out against the live stack: {exc!r}") from exc
    assert response.status_code == 200, (
        f"the A2A {leg} request must succeed; got HTTP {response.status_code}: {response.text[:600]!r}"
    )
    return response.json()


def _a2a_data_part(a2a_response: dict[str, Any]) -> dict[str, Any] | None:
    """The AdCP payload out of an A2A JSON-RPC result's first data part."""
    for artifact in (a2a_response.get("result") or {}).get("artifacts") or []:
        for part in artifact.get("parts") or []:
            if part.get("kind") == "data" and "data" in part:
                return part["data"]
    return None


def _buyer_headers() -> dict[str, str]:
    """No ``x-adcp-tenant``: the tenant resolves from the Host header the client sends.

    That is the same exact-string ``virtual_host`` match the signing posture is derived
    from, so routing by header here would let the request reach one tenant while the
    posture was computed for another.
    """
    return {"Authorization": f"Bearer {_BUYER_TOKEN}", "Content-Type": "application/json"}


def _await_deliveries(receiver: dict) -> list[CapturedWebhook]:
    """Poll until the asynchronous delivery lands, then reconstruct what the socket saw.

    Polling rather than sleeping a fixed interval because delivery runs behind a retry
    ladder. The reconstruction goes through ONE :class:`CapturedWebhook` per delivery:
    ``received_raw`` flattens ``http.server``'s case-INsensitive header mapping into a
    plain dict, and httpx makes no guarantee about the case of the ``Host`` key it puts
    on the wire, so a raw-dict lookup can ``KeyError`` on a correct request.

    The ``@target-uri`` is rebuilt from that ``Host`` plus the path — never from the URL
    we registered. ``protocol_webhook_service._normalize_localhost_for_docker`` rewrites
    the URL BEFORE signing and the SDK signs the post-hook effective URL, so the
    registered URL is not the signed one, and passing it would surface as
    ``request_signature_invalid`` — which reads like a crypto bug.
    """
    elapsed = 0.0
    while elapsed < _DELIVERY_TIMEOUT_SECONDS and not receiver["received_raw"]:
        sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS

    deliveries = []
    for path, raw_headers, body in list(receiver["received_raw"]):
        headers = httpx.Headers(raw_headers)
        host = headers.get("host")
        assert host, (
            f"the captured delivery carries no Host header, so its @target-uri cannot be rebuilt: {dict(headers)!r}"
        )
        deliveries.append(CapturedWebhook(url=f"http://{host}{path}", headers=headers, content=body))
    return deliveries


def _delivery_summary(captured: CapturedWebhook) -> dict[str, Any]:
    """Just enough of one delivery to say WHICH webhook it was, for a failure message.

    An unsigned delivery among signed ones is only actionable if the report names the
    notification it belongs to; the full body would bury that in a screenful of task JSON.
    """
    try:
        payload = captured.payload
    except ValueError:
        return {"signed": "signature" in captured.headers, "body": captured.content[:120]}
    status = payload.get("status")
    return {
        "signed": "signature" in captured.headers,
        "state": status.get("state") if isinstance(status, dict) else status,
        "keys": sorted(payload)[:8],
    }


def _jwks_with_swapped_key_material(jwks: dict[str, Any], kid: str) -> dict[str, Any]:
    """The published JWKS with the SAME ``kid`` carrying a DIFFERENT public key.

    Same kid on purpose. A negative control that used a different kid would fail at key
    LOOKUP (``request_signature_key_unknown``) and never reach the crypto step, so it
    would grade the resolver rather than the signature. Substituting real key material
    from a freshly generated pair — rather than mangling the ``x`` bytes — keeps the
    point on the curve, so the only thing that can fail is the signature check itself.
    """
    from adcp.signing import generate_signing_keypair

    _pem, other_jwk = generate_signing_keypair(alg=_ALG, kid=kid)
    swapped = copy.deepcopy(jwks)
    swapped["keys"][0]["x"] = other_jwk["x"]
    return swapped


@pytest.mark.asyncio
async def test_an_outbound_webhook_is_signed_and_verifies_against_the_published_jwks(
    docker_services_e2e, live_server, signing_capable_tenant
):
    """One tenant, two phases against the same live server: MISS, then PUBLICATION.

    A before/after of the SAME server rather than two tenants: only one tenant can hold
    the TLS ``virtual_host`` at a time, and a before/after is the stronger instrument
    anyway — it rules out "this deployment never signs anything" as an explanation of
    phase A and "this deployment signs everything" as an explanation of phase B.
    """
    base_url = tls_base_url(live_server)
    verify = ca_verified_ssl_context()

    # The netloc INCLUDES the port: get_tenant_by_virtual_host matches the Host header as
    # an exact string, and httpx sends the port unless it is the scheme default.
    tenant, key = signing_capable_tenant(netloc(base_url))
    assert key is None, "this tenant's key must arrive through a production path, not through the fixture"
    declared_identity = tenant.capability_declarations["identity"]

    # ── Phase A — MISS. The tenant has no key, so it must not sign. ────────────
    async with httpx.AsyncClient(base_url=base_url, verify=verify, timeout=60.0) as client:
        before = await fetch_capabilities(client)
        assert (before.get("webhook_signing") or {}).get("supported") is False, (
            "a tenant holding NO signing key must advertise webhook_signing.supported == false — "
            '"receivers MUST NOT expect a Signature header" is the only honest claim it can make. '
            f"Served webhook_signing: {before.get('webhook_signing')!r}"
        )

        with run_webhook_capture_server(_SignedWebhookCapture, _SignedWebhookCapture.received_webhooks) as receiver:
            miss_callback_url = receiver["url"]
            await _fire_one_delivery(client, receiver)
            unsigned = _await_deliveries(receiver)

    # Two assertions, never one. "No webhook arrived" and "an unsigned webhook arrived"
    # are different defects, and collapsing them is how a delivery path that silently
    # stopped firing reads as a signing result.
    assert unsigned, (
        f"no webhook reached the receiver at {miss_callback_url!r} within {_DELIVERY_TIMEOUT_SECONDS}s — "
        "with none there is nothing to grade, and the phase-B assertions below would be vacuous for a "
        "reason that has nothing to do with signing"
    )
    assert "signature" not in unsigned[0].headers, (
        "a tenant with no provisioned key must deliver the webhook UNSIGNED: a Signature header here "
        "is one no counterparty can verify against anything we publish. Headers: "
        f"{sorted(unsigned[0].headers.keys())}"
    )

    # ── Phase B — PUBLICATION. Provision through a production transport. ───────
    # The admin route runs INSIDE the server container, so the row is encrypted under the
    # CONTAINER's KEK — a key the server can actually open when it comes to sign. A
    # runner-minted key would still publish (a JWKS projects the public half only), and
    # would then fail to sign for a reason this module could not distinguish from a bug.
    provisioned_kid = provision_signing_key_via_admin(base_url, tenant_id=_TENANT_ID, alg=_ALG)

    async with httpx.AsyncClient(base_url=base_url, verify=verify, timeout=60.0) as client:
        after = await fetch_capabilities(client)
        advertised_profile = (after.get("webhook_signing") or {}).get("profile")
        assert (after.get("webhook_signing") or {}).get("supported") is True, (
            "once the tenant owns a publishable key on an https origin it MUST advertise "
            f"webhook_signing.supported == true; served {after.get('webhook_signing')!r}"
        )
        assert advertised_profile, (
            "a supported webhook_signing block must name the profile it emits, or the tag assertion "
            f"below has nothing to grade the wire against; served {after.get('webhook_signing')!r}"
        )

        jwks, published_kid = await _walk_discovery_to_jwks(client, after, declared_identity)

        with run_webhook_capture_server(_SignedWebhookCapture, _SignedWebhookCapture.received_webhooks) as receiver:
            signed_callback_url = receiver["url"]
            await _fire_one_delivery(client, receiver)
            signed = _await_deliveries(receiver)

    # (a) it arrived at all.
    assert signed, (
        f"no webhook reached the receiver at {signed_callback_url!r} within {_DELIVERY_TIMEOUT_SECONDS}s "
        "after the key was provisioned — a missing delivery is a delivery defect, not a signing result"
    )
    delivery = signed[0]

    # (b) the three headers a receiver needs, all present. Every delivery is checked, not
    # just the graded one: a second, unsigned delivery is exactly the regression a
    # first-only check would miss.
    for index, captured in enumerate(signed):
        missing = [h for h in ("signature", "signature-input", "content-digest") if h not in captured.headers]
        assert not missing, (
            f"outbound delivery {index} of {len(signed)} is missing {missing} — a receiver cannot verify it. "
            "This is the assertion that goes red when the RFC 9421 arm in "
            "webhook_sender_factory._rfc9421_sender is removed. Headers: "
            f"{sorted(captured.headers.keys())}. Bodies, in delivery order: {[_delivery_summary(c) for c in signed]}"
        )

    parsed = signature_input_label(delivery)

    # (c) the tag we EMIT is the profile we ADVERTISE. Both sides come from this run —
    # one off the served capabilities, one off the wire — so a literal cannot make it pass.
    assert parsed.params.get("tag") == advertised_profile, (
        "the emitted Signature-Input tag must equal the webhook_signing.profile the served capabilities "
        "advertise: the pin fixes the profile's meaning as the value receivers statically validate the "
        f"on-wire tag against. Advertised {advertised_profile!r}, emitted {parsed.params.get('tag')!r}"
    )

    # (d) the signature covers the digest of the body, so it is a signature over the BYTES
    # the receiver read — not over a header set that would survive a swapped payload.
    assert "content-digest" in parsed.components, (
        "content-digest must be a COVERED component of the signature; sign_webhook pins "
        "cover_content_digest=True, so an emission without it means the bytes are unprotected. Covered "
        f"components: {list(parsed.components)}"
    )

    # (e) the signature verifies — against a key this process obtained from nothing but
    # TLS fetches of the server's own documents.
    verified = verify_as_conformant_receiver(delivery, jwks)
    assert verified.key_id == provisioned_kid, (
        f"the signature must verify under the kid the admin route reported provisioning "
        f"({provisioned_kid!r}); it verified under {verified.key_id!r}"
    )
    assert verified.key_id == published_kid, (
        f"the verifying key must be the one PUBLISHED at the advertised origin ({published_kid!r}); "
        f"the signature verified under {verified.key_id!r} — a key we sign with but do not publish is "
        "a key no counterparty can use"
    )

    # The negative control. Same kid, different key material: the failure must be at the
    # crypto step, which is what proves the positive result above was crypto and not a
    # verifier that accepts anything it can look up.
    from adcp.signing.errors import SignatureVerificationError

    with pytest.raises(SignatureVerificationError) as rejected:
        verify_as_conformant_receiver(delivery, _jwks_with_swapped_key_material(jwks, published_kid))
    assert rejected.value.code == "request_signature_invalid", (
        "swapping the key material under the SAME kid must be rejected at the SIGNATURE check; got code "
        f"{rejected.value.code!r} at step {rejected.value.step!r}. A key_unknown here would mean the "
        "control never reached the crypto step and graded the resolver instead"
    )


async def _walk_discovery_to_jwks(
    client: httpx.AsyncClient, capabilities: dict[str, Any], declared_identity: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    """The buyer's discovery chain, walked from the SERVED documents only.

    capabilities → ``identity.brand_json_url`` → ``brand.json`` → the ``agents[]`` entry
    whose url BYTE-EQUALS the agent card's interface url → ``jwks_uri`` → JWKS. Every hop
    reads its next address out of the previous document; the JWKS URL is never written
    down. Step 7 of the discovery algorithm runs through the SDK's own
    ``check_key_origin_consistency`` rather than being re-implemented — it is the check a
    real verifier performs, and its absence is what "delete the key_origins emission →
    red" bites on.
    """
    from adcp.signing import check_key_origin_consistency
    from adcp.signing.errors import SignatureVerificationError

    identity = capabilities.get("identity") or {}
    assert identity.get("brand_json_url") == declared_identity["brand_json_url"], (
        f"the served identity.brand_json_url must be the trust root this tenant declared and the server "
        f"derives; served {identity.get('brand_json_url')!r}, declared {declared_identity['brand_json_url']!r}"
    )
    advertised_origin = (identity.get("key_origins") or {}).get("request_signing")
    assert advertised_origin, (
        "once the tenant owns a publishable key, the served document must advertise "
        f"identity.key_origins.request_signing, or no counterparty can locate our keys. Served: {identity!r}"
    )

    brand_response = await client.get(identity["brand_json_url"])
    assert brand_response.status_code == 200, (
        f"the trust root the served document points at must resolve over TLS at "
        f"{identity['brand_json_url']!r}; got HTTP {brand_response.status_code}"
    )
    brand = brand_response.json()

    card = (await client.get("/.well-known/agent-card.json")).json()
    agent_url = card["supportedInterfaces"][0]["url"]
    matching = [entry for entry in brand["agents"] if entry.get("type") == "sales" and entry["url"] == agent_url]
    assert len(matching) == 1, (
        "the served brand.json must carry exactly one sales agents[] entry whose url byte-equals the agent "
        f"card's interface URL {agent_url!r} — that is the match the discovery algorithm performs; served "
        f"{[entry['url'] for entry in brand['agents']]}"
    )
    resolved_jwks_uri = matching[0]["jwks_uri"]

    try:
        check_key_origin_consistency(
            jwks_uri=resolved_jwks_uri, key_origins=identity.get("key_origins"), purpose="request_signing"
        )
    except SignatureVerificationError as exc:
        pytest.fail(
            "the JWKS the served trust root resolves to must satisfy the verifier's key-origin consistency "
            f"check against the served identity.key_origins; declared {advertised_origin!r}, resolved "
            f"{resolved_jwks_uri!r} — {exc}"
        )

    jwks_response = await client.get(resolved_jwks_uri)
    assert jwks_response.status_code == 200, (
        f"the advertised JWKS must resolve over TLS at {resolved_jwks_uri!r}; got HTTP {jwks_response.status_code}"
    )
    jwks = jwks_response.json()
    keys = jwks.get("keys") or []
    assert len(keys) == 1, (
        f"the JWKS at the advertised origin must carry exactly the one key this tenant was provisioned with; "
        f"it carries {len(keys)}. An empty key set is the shape production shipped (salesagent-7x8t) and the "
        f"verifier below would have nothing to resolve. Document: {jwks!r}"
    )
    return jwks, keys[0]["kid"]

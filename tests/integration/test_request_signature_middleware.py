"""Integration tests pinning salesagent-z6nr.12 (#1291 B1) — the ONE inbound
RFC 9421 request-signature verifier middleware.

These are TDD-red: ``src.core.signing.request_verifier_middleware`` does not
exist yet, so this module fails at collection. That is legitimate red — what
matters is that each test below encodes the exact behavior the REFINED plan
(``bd show salesagent-z6nr.12`` → "## Refinement (atom salesagent-3u4e.21,
post-review)") creates. The refinement AMENDS the original Implementation Plan
and wins wherever the two differ.

What is graded here, and why each one exists
--------------------------------------------

**R-H1 — the composition rule (production-breaking if wrong).**
``required_for`` governs the signature requirement *relative to the caller's
credential path*, not absolutely. Pinned spec (AdCP 3.1.1 →
``dist/docs/3.1.0-rc.15/building/by-layer/L1/security.mdx`` in
``github.com/adcontextprotocol/adcp`` @ tag ``v3.1.1``):

  :1268  an **unauthenticated** request to a ``required_for`` operation MUST be
         rejected with ``request_signature_required``;
  :1269  an **unsigned but otherwise authenticated** request (valid bearer, no
         ``Signature-Input``) MUST NOT be rejected for the missing signature;
  :1271  a **malformed signature** blocks that fallback regardless;
  :1224  states it as a three-way AND ("…AND the caller presents no other
         credential the verifier accepts");
  :1289  names this exact failure — "a seller enabling ``required_for`` for
         operational monitoring would inadvertently 401 every bearer-authed
         buyer".

Salesagent is bearer-authenticated on every AdCP request, so the naive reading
401s essentially all production traffic the moment D1 populates
``required_for``. Compliance negative vector 001 does NOT catch this: its
request carries only ``Content-Type``, i.e. it is unauthenticated, and is
therefore consistent with BOTH readings. All three branches are pinned below.

**R-H2 / R-M5(b) — the verifier must sit OUTSIDE the body rewriter.**
``RestCompatMiddleware`` (``src/routes/rest_compat_middleware.py:67``) is a
``BaseHTTPMiddleware`` that, for POST ``/api/v1/{products,media-buys,
creatives/sync}``, sets ``request._body = normalized_bytes``; Starlette's
``_CachedRequest.wrapped_receive`` then hands those NORMALIZED bytes to
everything downstream. At the originally-planned placement the verifier would
verify bytes the signer never signed, and the collision lands on
``/api/v1/media-buys`` = ``create_media_buy``, the spend-committing operation
the spec pushes toward ``covers_content_digest: "required"``.
:class:`TestVerifierSitsOutsideBodyRewriter` grades exactly that and nothing
else: it FAILS at the original placement (digest computed over normalized
bytes) and PASSES at the corrected one (CORS → UnifiedAuth → verifier →
RestCompat → a2a → router).

**R-H3 — the ``none`` bucket costs nothing.** Two junk signature headers under
``supported: false`` must not buffer the body, must not run crypto. Asserted
observably (the SDK verifier is never invoked; the downstream handler still
receives the full body), not by reading the middleware source.

**R-L / three-way pre-check.** Both headers absent → composition rule; exactly
one present → ``_precheck_presence`` raises (``adcp/signing/verifier.py:389``);
both present → verify.

**Shadow-mode ladder.** ``supported_for`` / ``warn_for`` / ``required_for``
differ on the WIRE (200 vs 401), not merely in a counter — status AND counter
are asserted. (The refinement retires the research note's "invisible failure
mode" framing for warn precisely because the difference IS on the wire.)

Why these tests are not vacuous
-------------------------------

The seam is the tenant DECLARATION, never the middleware's decision function:
:func:`_declared_posture` substitutes what ``posture_for_tenant`` reads and
lets the REAL ``RequestSigningPosture.bucket_for`` precedence
(``required_for > warn_for > supported_for``) run. B1 shipped alone is INERT in
production — ``request_signing`` is still in ``_UNBACKED_BLOCKS``
(``src/core/schemas/capability_declarations.py:61``), so no tenant can declare
a posture through ``from_tenant`` yet. That is intended, and it is why D1
(``salesagent-z6nr.20``) carries the obligation to re-run this same ladder
through the real ``from_tenant`` path once the block is backed.

B1 shipped with ``UnresolvedOperationResolver``, which returned ``("", None)``
by design (plan step 2 — no partial hand-written map in B1), so the operation
these declarations bucketed was the empty string. B2
(``salesagent-z6nr.13``) swapped in the registry-derived resolver, and
:data:`B1_OPERATIONS` now carries the real AdCP operation names this ladder
invokes — which is what makes every assertion below non-vacuous.

Covers: salesagent-z6nr.12 (Core Invariant + Refinement R-H1, R-H2, R-H3,
R-L, and the shadow-mode ladder).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from adcp.signing import (
    REQUEST_SIGNATURE_HEADER_MALFORMED,
    REQUEST_SIGNATURE_REQUIRED,
    generate_signing_keypair,
    load_private_key_pem,
    sign_request,
)
from adcp.signing.agent_resolver import AgentResolution
from adcp.signing.errors import REQUEST_SIGNATURE_DIGEST_MISMATCH
from prometheus_client import REGISTRY

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness._base import BareIntegrationEnv

# --------------------------------------------------------------------------
# Contract the implement atom (salesagent-3u4e.15) must satisfy
# --------------------------------------------------------------------------
# These names are the red test's half of the TDD contract. The refined plan
# names the module and the class; the two module-level attributes below are
# the seams this file needs and are called out here so the implementer wires
# them deliberately rather than by accident:
#
#   src.core.signing.request_verifier_middleware
#     .RequestSignatureMiddleware      pure-ASGI class (plan step 4)
#     .ADCP_SURFACE_PREFIXES           the path allowlist (plan step 4b, R-M4)
#     .posture_for_tenant              imported from src.core.signing.posture
#                                      into the middleware namespace, so the
#                                      declaration is substitutable (see below)
#     .verify_request_signature        imported from adcp.signing — R-M3 says
#                                      call the SYNC entry point directly, not
#                                      through a Starlette Request duck type
#     .AGENT_RESOLUTION_CACHE          process-level {agent_url: AgentResolution}
#                                      registry (R-M2: cache the resolution
#                                      WHOLE — jwks + jwks_uri + key_origins —
#                                      so all four VerifyOptions fields can be
#                                      passed and the key-origin check does not
#                                      ship silently OFF)

#: The AdCP operations this file's ladder actually invokes, now that B2
#: (salesagent-z6nr.13) has replaced ``UnresolvedOperationResolver`` with the
#: registry-derived one and every request below is NAMED.
#:
#: Two names rather than the single ``""`` B1 shipped, because the ladder runs on two
#: routes: ``/api/v1/capabilities`` (both verbs) is ``get_adcp_capabilities`` and POST
#: ``/api/v1/media-buys`` is ``create_media_buy``. Each test still exercises exactly
#: one of them, and :func:`_bucketed` puts BOTH in the bucket under test, so every
#: assertion below grades the same thing it graded in B1 — against real operation names
#: instead of the empty string, which is what makes the whole ladder non-vacuous.
B1_OPERATIONS = ("get_adcp_capabilities", "create_media_buy")

_AGENT_URL = "https://buyer.example.com/a2a"
_KEY_ORIGIN = "https://buyer.example.com"
_JWKS_URI = "https://buyer.example.com/.well-known/jwks.json"
_KID = "buyer-request-signing-1"

_TENANT_ID = "sig_tenant"
_PRINCIPAL_ID = "sig_principal"

#: An AdCP surface path with no request body — the cheapest place to grade the
#: header-presence branches. Auth-optional, so any 401 seen on it came from the
#: verifier and not from the route's own auth dependency.
_BODYLESS_ADCP_PATH = "/api/v1/capabilities"

#: The body-rewriter collision site (R-H2). ``account_id`` is a DEPRECATED
#: field name: ``normalize_request_params`` translates ``account_id`` →
#: ``account`` (``src/core/request_compat.py``), which sets
#: ``translations_applied`` and makes ``RestCompatMiddleware`` rewrite the body.
_REWRITTEN_ADCP_PATH = "/api/v1/media-buys"


# --------------------------------------------------------------------------
# Declaration seam
# --------------------------------------------------------------------------


@contextmanager
def _declared_posture(**declaration: Any) -> Iterator[None]:
    """Substitute the tenant's ``request_signing`` DECLARATION, not the decision.

    Takes the schema's own property names (``supported``,
    ``covers_content_digest``, ``required_for``, ``warn_for``,
    ``supported_for``, ``protocol_methods_*``) and builds a real
    :class:`RequestSigningPosture` from them, so the production
    ``bucket_for`` precedence runs for real. Only the READER
    (``posture_for_tenant``) is replaced — ``request_signing`` is still in
    ``_UNBACKED_BLOCKS``, so there is no DB path that can carry a declaration
    in B1.

    ``request_signing_is_declarable`` is substituted TRUE alongside it (B2
    refinement R-H1). B1 gates only the tenant DB read on declarability and
    calls ``posture_for_tenant`` unconditionally, so B1 never needed this. B2
    gates the body BUFFER + operation RESOLVE on the same flag — which is
    False in production today — so without this line every B2 declaration
    would be graded against an operation the resolver was never asked to
    name, and the whole ladder below would pass vacuously. Declaring a posture
    and not making it declarable is not a state any tenant can be in.
    """
    from src.core.signing import request_verifier_middleware as mw
    from src.core.signing.posture import RequestSigningPosture

    posture = RequestSigningPosture(**declaration)
    with (
        patch.object(mw, "posture_for_tenant", lambda _tenant: posture),
        patch.object(mw, "request_signing_is_declarable", lambda: True),
    ):
        yield


def _unsupported() -> dict[str, Any]:
    """The default posture: the ``none`` bucket for every operation."""
    return {"supported": False}


def _bucketed(bucket: str) -> dict[str, Any]:
    """A declaration putting :data:`B1_OPERATIONS` in exactly one bucket.

    ``required_for`` entries must also appear in ``supported_for``
    (``get-adcp-capabilities-response.json`` x-adcp-validation: "an operation
    can't be required without being supported"), so the required declaration
    lists both — which is also what makes the precedence rule
    ``required_for > warn_for > supported_for`` load-bearing rather than
    decorative.
    """
    declaration: dict[str, Any] = {"supported": True, "supported_for": list(B1_OPERATIONS)}
    if bucket == "required":
        declaration["required_for"] = list(B1_OPERATIONS)
    elif bucket == "warn":
        declaration["warn_for"] = list(B1_OPERATIONS)
    elif bucket != "supported":
        raise ValueError(f"unknown bucket {bucket!r}")
    return declaration


# --------------------------------------------------------------------------
# Counterparty key material
# --------------------------------------------------------------------------


@contextmanager
def _counterparty_key(jwks: dict[str, Any]) -> Iterator[None]:
    """Seed the whole :class:`AgentResolution` for :data:`_AGENT_URL` (R-M2).

    The middleware keys its resolver registry on the counterparty's
    ``agent_url`` (read from the Principal row — security.mdx :1212/:1216
    forbid taking it from a header, a body field or any self-assertion), and
    R-M2 requires the cached object to carry ``jwks`` AND ``jwks_uri`` AND
    ``key_origins`` so ``expected_key_origins`` can be passed to
    ``VerifyOptions``. Seeding the resolution here is what lets these tests run
    the REAL verifier without a live counterparty — nothing about the outcome
    is faked.
    """
    from src.core.signing import request_verifier_middleware as mw

    resolution = AgentResolution(
        agent_url=_AGENT_URL,
        brand_json_url="https://buyer.example.com/.well-known/brand.json",
        agent_entry={"type": "sales", "url": _AGENT_URL, "jwks_uri": _JWKS_URI},
        jwks_uri=_JWKS_URI,
        jwks=jwks,
        fetched_at=time.time(),
        key_origins={"request_signing": _KEY_ORIGIN},
    )
    mw.AGENT_RESOLUTION_CACHE[_AGENT_URL] = resolution
    try:
        yield
    finally:
        mw.AGENT_RESOLUTION_CACHE.pop(_AGENT_URL, None)


@pytest.fixture(scope="module")
def counterparty_keypair() -> tuple[Any, dict[str, Any]]:
    """A real Ed25519 request-signing keypair: (private_key, public JWKS)."""
    pem, public_jwk = generate_signing_keypair(alg="ed25519", kid=_KID, purpose="request-signing")
    return load_private_key_pem(pem), {"keys": [public_jwk]}


# --------------------------------------------------------------------------
# Request construction
# --------------------------------------------------------------------------

#: Both headers present, neither parseable — the malformed-signature shape.
_MALFORMED_SIGNATURE_HEADERS = {
    "Signature-Input": "sig1=this-is-not-an-rfc8941-inner-list",
    "Signature": "sig1=:AAAA:",
}


def _seed(env: BareIntegrationEnv, *, agent_url: str | None = _AGENT_URL) -> str:
    """Create the tenant + a Principal carrying ``agent_url``; return its token.

    ``Principal.agent_url`` is plan step 3 (nullable ``String(500)``, Alembic
    migration chained on head ``04c04fef9503``) — the onboarding record is the
    only legitimate source for the counterparty's agent URL.
    """
    tenant = TenantFactory(tenant_id=_TENANT_ID)
    principal = PrincipalFactory(
        tenant=tenant,
        principal_id=_PRINCIPAL_ID,
        agent_url=agent_url,
    )
    return principal.access_token


def _headers(token: str | None, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Wire headers: tenant hint + optional bearer + whatever the test adds."""
    headers = {"x-adcp-tenant": _TENANT_ID}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


def _sign(
    private_key: Any,
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
) -> dict[str, str]:
    """Sign *body* over the WIRE bytes, covering ``content-digest``."""
    signed = sign_request(
        method=method,
        url=url,
        headers=headers,
        body=body,
        private_key=private_key,
        key_id=_KID,
        alg="ed25519",
        cover_content_digest=True,
    )
    return signed.as_dict()


# --------------------------------------------------------------------------
# Observation helpers
# --------------------------------------------------------------------------


def _rejection_code(response: Any) -> str | None:
    """The verifier's error code off the wire, or None if it did not reject.

    The 401 carries ``WWW-Authenticate: Signature error="<code>"`` — the
    SDK's ``unauthorized_response_headers`` (``adcp/signing/middleware.py:22``)
    and the only wire signal that distinguishes a verifier rejection from a
    route-level 401.
    """
    if response.status_code != 401:
        return None
    challenge = response.headers.get("WWW-Authenticate", "")
    if not challenge.startswith("Signature "):
        return None
    _, _, remainder = challenge.partition('error="')
    return remainder.rstrip('"') or None


@contextmanager
def _verifier_spy() -> Iterator[list[dict[str, Any]]]:
    """Record every ``verify_request_signature`` call, delegating to the real one.

    Pure observation: the SDK verifier still runs and still decides. Recording
    the kwargs is what lets :class:`TestVerifierSitsOutsideBodyRewriter` prove
    WHICH bytes were verified, and what lets :class:`TestNoneBucketCostsNothing`
    prove no crypto ran at all.
    """
    from src.core.signing import request_verifier_middleware as mw

    calls: list[dict[str, Any]] = []
    real = mw.verify_request_signature

    def _recording(**kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return real(**kwargs)

    with patch.object(mw, "verify_request_signature", _recording):
        yield calls


def _counter_samples(sample_name: str) -> dict[tuple[tuple[str, str], ...], float]:
    """All Prometheus samples named *sample_name*, keyed by their label set."""
    out: dict[tuple[tuple[str, str], ...], float] = {}
    for family in REGISTRY.collect():
        for sample in family.samples:
            if sample.name == sample_name:
                out[tuple(sorted(sample.labels.items()))] = sample.value
    return out


def _counter_total(sample_name: str) -> float:
    return sum(_counter_samples(sample_name).values())


def _samples_with(sample_name: str, **labels: str) -> dict[tuple[tuple[str, str], ...], float]:
    """Samples of *sample_name* whose labels are a superset of *labels*."""
    wanted = labels.items()
    return {key: value for key, value in _counter_samples(sample_name).items() if wanted <= dict(key).items()}


#: Metric names from plan step 6. ``code`` collapses to ``"other"`` outside the
#: 27 spec strings; ``keyid`` is the real value only after step-7 resolution.
_FAILED_METRIC = "adcp_request_signature_failed_total"
_VERIFIED_METRIC = "adcp_request_signature_verified_total"


# --------------------------------------------------------------------------
# R-H1 — the composition rule
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestCompositionWithFallbackAuthenticators:
    """``required_for`` rejects the UNAUTHENTICATED branch only (security.mdx :1268-1271)."""

    def test_unsigned_but_bearer_authenticated_is_not_rejected(self, integration_db):
        """security.mdx :1269 — an unsigned request carrying a valid bearer that
        resolves to an accepted Principal MUST NOT be rejected for the missing
        signature, even when the operation is in ``required_for``.

        This is the branch that would 401 essentially all salesagent production
        traffic under the strict reading (:1289), and the branch compliance
        negative vector 001 cannot grade because its request is unauthenticated.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_bucketed("required")):
                response = client.get(_BODYLESS_ADCP_PATH, headers=_headers(token))

            assert _rejection_code(response) is None, (
                "an unsigned but bearer-authenticated request to a required_for "
                "operation must NOT be rejected for the missing signature "
                f"(security.mdx :1269); the verifier rejected with {_rejection_code(response)!r}"
            )
            assert response.status_code == 200, (
                f"expected the request to pass through to the route, got {response.status_code}: {response.text}"
            )

    def test_unsigned_and_unauthenticated_is_rejected(self, integration_db):
        """security.mdx :1268 + :1264 — a bearer token the verifier does not
        accept is NOT a valid credential, so the caller is unauthenticated and
        a ``required_for`` operation MUST reject with
        ``request_signature_required``.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_bucketed("required")):
                response = client.get(
                    _BODYLESS_ADCP_PATH,
                    headers=_headers("not-a-token-any-principal-holds"),
                )

            assert response.status_code == 401, (
                "an unsigned request presenting no credential the verifier accepts must be "
                f"rejected on a required_for operation (security.mdx :1268), got {response.status_code}"
            )
            assert _rejection_code(response) == REQUEST_SIGNATURE_REQUIRED, (
                "the rejection must carry the spec error code on "
                f'WWW-Authenticate: Signature error="{REQUEST_SIGNATURE_REQUIRED}"; '
                f"got {response.headers.get('WWW-Authenticate')!r}"
            )

    def test_malformed_signature_blocks_bearer_fallback(self, integration_db):
        """security.mdx :1271 + :1226 — a present-but-malformed signature signals
        signer intent and MUST NOT downgrade silently to bearer. A valid bearer
        does not rescue it.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_bucketed("required")):
                response = client.get(
                    _BODYLESS_ADCP_PATH,
                    headers=_headers(token, _MALFORMED_SIGNATURE_HEADERS),
                )

            assert response.status_code == 401, (
                "a malformed signature blocks the bearer fallback regardless "
                f"(security.mdx :1271), got {response.status_code}: {response.text}"
            )
            assert _rejection_code(response) == REQUEST_SIGNATURE_HEADER_MALFORMED, (
                f"expected {REQUEST_SIGNATURE_HEADER_MALFORMED!r} on the wire, "
                f"got {response.headers.get('WWW-Authenticate')!r}"
            )


# --------------------------------------------------------------------------
# Three-way pre-check (R-L)
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestHeaderPresencePrecheck:
    """Both absent → composition rule; exactly one → malformed; both → verify."""

    @pytest.mark.parametrize(
        "present",
        ["Signature-Input", "Signature"],
        ids=["only-signature-input", "only-signature"],
    )
    def test_exactly_one_signature_header_is_malformed(self, integration_db, present):
        """``_precheck_presence`` raises on BOTH one-sided branches
        (``adcp/signing/verifier.py:389``): "Signature and Signature-Input must
        both be present". A valid bearer does not rescue a half-present
        signature — same malformed rule as :1271.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_bucketed("supported")):
                response = client.get(
                    _BODYLESS_ADCP_PATH,
                    headers=_headers(token, {present: _MALFORMED_SIGNATURE_HEADERS[present]}),
                )

            assert _rejection_code(response) == REQUEST_SIGNATURE_HEADER_MALFORMED, (
                f"a request carrying only {present!r} must be rejected with "
                f"{REQUEST_SIGNATURE_HEADER_MALFORMED!r}; got status {response.status_code}, "
                f"WWW-Authenticate={response.headers.get('WWW-Authenticate')!r}"
            )

    def test_both_headers_present_enters_the_checklist(self, integration_db):
        """Both present → the SDK verifier runs, on a ``supported_for`` operation."""
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_bucketed("supported")), _verifier_spy() as calls:
                client.get(
                    _BODYLESS_ADCP_PATH,
                    headers=_headers(token, _MALFORMED_SIGNATURE_HEADERS),
                )

            assert len(calls) == 1, (
                "a request carrying BOTH signature headers on a supported_for operation "
                f"must enter the SDK verifier checklist exactly once; it was called {len(calls)} times"
            )


# --------------------------------------------------------------------------
# R-H3 — the `none` bucket costs nothing
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestNoneBucketCostsNothing:
    """Posture is resolved BEFORE buffering; ``none`` passes through untouched."""

    def test_junk_signature_headers_under_unsupported_posture_run_no_crypto(self, integration_db):
        """R-H3 — two junk headers under ``supported: false`` must not buffer the
        body and must not run crypto: otherwise attaching two headers is an
        unauthenticated CPU+DB amplifier whose result is then DISCARDED, because
        the matrix says ``none`` → 200.

        Asserted observably (the SDK verifier is never invoked, and the
        downstream handler still receives the complete body from an undrained
        receive channel), not by reading the middleware source.
        """
        body = {"context": {"request_id": "none-bucket-passthrough"}}
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_unsupported()), _verifier_spy() as calls:
                response = client.post(
                    _BODYLESS_ADCP_PATH,
                    json=body,
                    headers=_headers(token, _MALFORMED_SIGNATURE_HEADERS),
                )

            assert calls == [], (
                "the none bucket must not run crypto — verify_request_signature was "
                f"invoked {len(calls)} time(s) for a request the matrix passes through"
            )
            assert response.status_code == 200, (
                f"the none bucket must pass through untouched, got {response.status_code}: {response.text}"
            )
            assert response.json()["context"] == body["context"], (
                "the downstream handler must still receive the complete request body — "
                "a receive channel drained by the verifier would truncate it; got "
                f"{response.json().get('context')!r}"
            )

    def test_the_same_request_under_a_supported_posture_does_run_crypto(self, integration_db):
        """The contrast that makes the cheapness claim non-vacuous: byte-identical
        request, one declaration change, and now the checklist runs and rejects.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_bucketed("supported")), _verifier_spy() as calls:
                response = client.post(
                    _BODYLESS_ADCP_PATH,
                    json={"context": {"request_id": "supported-bucket"}},
                    headers=_headers(token, _MALFORMED_SIGNATURE_HEADERS),
                )

            assert len(calls) == 1, (
                "under supported_for the SDK verifier must run for the same request the "
                f"none bucket skips; it ran {len(calls)} time(s)"
            )
            assert _rejection_code(response) == REQUEST_SIGNATURE_HEADER_MALFORMED, (
                f"expected {REQUEST_SIGNATURE_HEADER_MALFORMED!r} on the wire, "
                f"got status {response.status_code}, WWW-Authenticate="
                f"{response.headers.get('WWW-Authenticate')!r}"
            )


# --------------------------------------------------------------------------
# Shadow-mode ladder
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestShadowModeLadder:
    """``supported_for`` / ``warn_for`` / ``required_for`` differ on the WIRE.

    ``VerifierCapability`` (``adcp/signing/verifier.py:88``) carries only 4 of
    ``request_signing``'s 8 properties and only 2 of its 6 operation buckets, so
    ``warn_for`` is SILENTLY DROPPED if it is passed to the SDK and expected to
    do something. Warn must therefore be implemented by us: call the verifier,
    catch ``SignatureVerificationError``, emit the metric and CONTINUE. Each
    test below asserts BOTH the status and the counter, so the test fails if
    warn degrades to plain ``supported_for`` (status) and fails if the metric is
    dropped (counter).

    The signature used is WELL-FORMED and cryptographically real — signed with
    the counterparty's actual key, then the body is mutated in flight, so the
    verifier reaches ``request_signature_digest_mismatch`` on its merits rather
    than short-circuiting at the header parse.
    """

    @staticmethod
    def _tampered_signed_request(private_key: Any, token: str) -> tuple[dict[str, str], bytes]:
        """Headers signed over one body, plus the DIFFERENT body actually sent."""
        signed_body = json.dumps({"context": {"request_id": "as-signed"}}).encode()
        sent_body = json.dumps({"context": {"request_id": "as-sent-DIFFERENT"}}).encode()
        base = _headers(token, {"Content-Type": "application/json"})
        signature_headers = _sign(
            private_key,
            method="POST",
            url=f"http://testserver{_BODYLESS_ADCP_PATH}",
            headers=base,
            body=signed_body,
        )
        return {**base, **signature_headers}, sent_body

    @pytest.mark.parametrize(
        ("bucket", "expected_status"),
        [("supported", 401), ("warn", 200), ("required", 401)],
    )
    def test_invalid_signature_outcome_differs_per_bucket(
        self, integration_db, counterparty_keypair, bucket, expected_status
    ):
        """A signed-but-invalid request: ``warn_for`` logs and continues (200),
        ``supported_for`` and ``required_for`` reject (401). Every bucket
        increments ``adcp_request_signature_failed_total`` with the spec code.
        """
        private_key, jwks = counterparty_keypair
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()
            headers, sent_body = self._tampered_signed_request(private_key, token)

            before = _counter_total(_FAILED_METRIC)
            with _declared_posture(**_bucketed(bucket)), _counterparty_key(jwks):
                response = client.post(_BODYLESS_ADCP_PATH, content=sent_body, headers=headers)
            after = _counter_total(_FAILED_METRIC)

            assert response.status_code == expected_status, (
                f"bucket {bucket!r} must answer {expected_status} on the wire for a "
                f"signed-but-invalid request, got {response.status_code}: {response.text}"
            )
            assert after == before + 1, (
                f"bucket {bucket!r} must increment {_FAILED_METRIC} exactly once "
                f"(it is the promotion evidence the shadow-mode ladder runs on); "
                f"went {before} -> {after}"
            )
            assert _samples_with(_FAILED_METRIC, code=REQUEST_SIGNATURE_DIGEST_MISMATCH), (
                f"the failure must be labelled with the spec code "
                f"{REQUEST_SIGNATURE_DIGEST_MISMATCH!r}; samples were "
                f"{sorted(_counter_samples(_FAILED_METRIC))}"
            )

    def test_warn_does_not_degrade_to_supported(self, integration_db, counterparty_keypair):
        """The two-bucket contrast stated as one assertion: byte-identical
        request, ``warn_for`` vs ``supported_for``, different wire answers. If
        warn degrades to supported both are 401 and this fails.
        """
        private_key, jwks = counterparty_keypair
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()
            headers, sent_body = self._tampered_signed_request(private_key, token)

            with _counterparty_key(jwks):
                with _declared_posture(**_bucketed("warn")):
                    warn_response = client.post(_BODYLESS_ADCP_PATH, content=sent_body, headers=headers)
                with _declared_posture(**_bucketed("supported")):
                    supported_response = client.post(_BODYLESS_ADCP_PATH, content=sent_body, headers=headers)

            assert (warn_response.status_code, supported_response.status_code) == (200, 401), (
                "warn_for and supported_for must differ on the WIRE for the same "
                f"signed-but-invalid request; got warn={warn_response.status_code}, "
                f"supported={supported_response.status_code}"
            )


# --------------------------------------------------------------------------
# R-H2 / R-M5(b) — the verifier sits outside the body rewriter
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestVerifierSitsOutsideBodyRewriter:
    """The verifier must see the WIRE bytes, not ``RestCompatMiddleware``'s rewrite.

    This class grades the middleware ORDER and nothing else. Execution must be
    CORS → UnifiedAuth → verifier → RestCompat → a2a → router (R-H2): the
    verifier stays outside BOTH body rewriters while ``auth_context`` is still
    populated before it. At the ORIGINAL placement (verifier inside RestCompat)
    ``request._body`` has already been replaced with the normalized JSON and
    the signature over ``content-digest`` fails with
    ``request_signature_digest_mismatch`` — on ``create_media_buy``, the
    spend-committing operation.
    """

    @staticmethod
    def _signed_deprecated_field_request(private_key: Any, token: str) -> tuple[dict[str, str], bytes]:
        """A POST whose body uses the DEPRECATED ``account_id`` field name.

        ``normalize_request_params`` translates ``account_id`` → ``account``
        (``src/core/request_compat.py``), so ``translations_applied`` is
        non-empty and ``RestCompatMiddleware`` rewrites the body — which is
        precisely the condition that makes wire bytes and downstream bytes
        differ.
        """
        wire_body = json.dumps(
            {
                "account_id": "acct-deprecated-name",
                "packages": [],
                "start_time": "2026-08-01T00:00:00Z",
                "end_time": "2026-08-31T00:00:00Z",
            }
        ).encode()
        base = _headers(token, {"Content-Type": "application/json"})
        signature_headers = _sign(
            private_key,
            method="POST",
            url=f"http://testserver{_REWRITTEN_ADCP_PATH}",
            headers=base,
            body=wire_body,
        )
        return {**base, **signature_headers}, wire_body

    def test_signature_over_wire_bytes_verifies_on_a_body_rewritten_route(self, integration_db, counterparty_keypair):
        """R-M5(b) — the whole point of the ordering change, graded directly.

        Three assertions, each with its own diagnosis:
        1. the verifier was handed the WIRE bytes (they still carry the
           deprecated field name);
        2. it did not reject — the real SDK checklist ran over those bytes and
           the ``content-digest`` matched;
        3. the URL it verified against is the as-received one.
        """
        private_key, jwks = counterparty_keypair
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()
            headers, wire_body = self._signed_deprecated_field_request(private_key, token)

            with (
                _declared_posture(**_bucketed("supported")),
                _counterparty_key(jwks),
                _verifier_spy() as calls,
            ):
                response = client.post(_REWRITTEN_ADCP_PATH, content=wire_body, headers=headers)

            assert len(calls) == 1, (
                "the signed POST must reach the SDK verifier exactly once; it was called "
                f"{len(calls)} time(s). Zero calls means the middleware aborted before "
                "verify (check AGENT_RESOLUTION_CACHE seeding, R-M2)"
            )
            assert calls[0]["body"] == wire_body, (
                "the verifier must be handed the WIRE bytes. It received "
                f"{calls[0]['body']!r} instead of {wire_body!r} — that is "
                "RestCompatMiddleware's normalized rewrite, i.e. the verifier is "
                "registered INSIDE the body rewriter (R-H2)"
            )
            assert _rejection_code(response) != REQUEST_SIGNATURE_DIGEST_MISMATCH, (
                "the signature covers content-digest over the wire bytes and must "
                "verify; a digest mismatch means the verifier hashed bytes the signer "
                "never signed (R-H2)"
            )
            assert _rejection_code(response) is None, (
                f"the verifier must not reject this request; it answered {response.status_code} "
                f"with WWW-Authenticate={response.headers.get('WWW-Authenticate')!r}"
            )
            assert calls[0]["url"] == f"http://testserver{_REWRITTEN_ADCP_PATH}", (
                "the verify URL must be derived from the as-received Host "
                f"(security.mdx step 10), got {calls[0]['url']!r}"
            )

    def test_verified_signature_increments_the_verified_counter(self, integration_db, counterparty_keypair):
        """Plan step 6 — B1 is the only layer that sees the outcome before it is
        swallowed or turned into a 401, so the success side of the ladder's
        promotion evidence is emitted here too.
        """
        private_key, jwks = counterparty_keypair
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()
            headers, wire_body = self._signed_deprecated_field_request(private_key, token)

            before = _counter_total(_VERIFIED_METRIC)
            with _declared_posture(**_bucketed("supported")), _counterparty_key(jwks):
                client.post(_REWRITTEN_ADCP_PATH, content=wire_body, headers=headers)
            after = _counter_total(_VERIFIED_METRIC)

            assert after == before + 1, (
                f"a successfully verified signature must increment {_VERIFIED_METRIC} "
                f"exactly once; went {before} -> {after}"
            )

    def test_rest_compat_still_normalizes_the_deprecated_field(self, integration_db):
        """Companion guard on the re-registration: moving RestCompatMiddleware
        must not disable it. The deprecated ``account_id`` must still be
        translated before the route's Pydantic body model sees it, so no error
        the route emits names ``account_id``.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            token = _seed(env)
            client = env.get_rest_client()

            with _declared_posture(**_unsupported()):
                response = client.post(
                    _REWRITTEN_ADCP_PATH,
                    json={
                        "account_id": "acct-deprecated-name",
                        "packages": [],
                        "start_time": "2026-08-01T00:00:00Z",
                        "end_time": "2026-08-31T00:00:00Z",
                    },
                    headers=_headers(token),
                )

            assert "account_id" not in response.text, (
                "RestCompatMiddleware must still translate account_id -> account before "
                f"the route model validates; the response still names it: {response.text[:400]}"
            )

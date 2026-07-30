"""Shared helpers for the signing test modules (#1291).

Two groups:

* **A2 key provisioning** (``salesagent-z6nr.8``) — build the tenant-scoped
  repository off the harness session, provision a key through production, and
  resolve a provider through production.
* **The B1 verifier seams** (``salesagent-z6nr.14`` step 2, review finding LOW-1)
  — the DECLARATION substitute, the counterparty-key seed, the verifier spy, the
  wire rejection-code reader and the Prometheus counter readers. These were
  defined inside ``tests/integration/test_request_signature_middleware.py`` and
  imported ACROSS test modules by two siblings (and now a third, the B3
  conformance run) — the duplication class the DRY invariant and
  ``check_code_duplication.py`` exist to stop. One definition, here.

Deliberately thin: these forward to production entry points and add nothing.
Anything that decides or asserts belongs in the test, not here.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

# An RFC 9421 signature base: the canonicalized component list joined by LF with
# ``"@signature-params"`` last. A SigningProvider signs this as a RAW MESSAGE —
# never as a pre-hashed digest — so passing it verbatim is what the profile means.
SIGNATURE_BASE = (
    b'"@method": POST\n'
    b'"@target-uri": https://seller.example/mcp/\n'
    b'"@signature-params": ("@method" "@target-uri");created=1767225600;'
    b'keyid="adcp-key";alg="ed25519"'
)

REQUEST_SIGNING = "request-signing"

# ---------------------------------------------------------------------------
# The counterparty, the tenant and the surfaces the signing suites share
# (promoted from tests/integration/test_request_signature_middleware.py —
# salesagent-z6nr.14 step 2)
# ---------------------------------------------------------------------------
#
# These were module constants of the B1 middleware suite that the B4 operations,
# A5 revocation and B3 conformance suites then imported ACROSS test modules (or
# re-declared verbatim). Both shapes are the same defect: a name whose home is a
# ``test_*.py`` module has no importable home at all. One definition, here.

#: The counterparty as the Principal row carries it. ``agent_url`` is the ONLY
#: legitimate source for a counterparty's identity (security.mdx forbids taking
#: it from a header, a body field or any other self-assertion), and the
#: middleware keys :data:`AGENT_RESOLUTION_CACHE` on exactly this value.
COUNTERPARTY_AGENT_URL = "https://buyer.example.com/a2a"

#: The origin the counterparty's ``brand.json`` is served from — what
#: ``expected_key_origins`` is checked against at verifier step 7.
COUNTERPARTY_KEY_ORIGIN = "https://buyer.example.com"

#: Where that brand.json points for request-signing keys.
COUNTERPARTY_JWKS_URI = "https://buyer.example.com/.well-known/jwks.json"

#: The ``keyid`` the counterparty signs under.
COUNTERPARTY_KID = "buyer-request-signing-1"

#: The seller tenant and the buyer's principal within it. Shared so the three
#: in-process suites address the same rows and one ``seed_principal`` serves all.
SIGNING_TENANT_ID = "sig_tenant"
SIGNING_PRINCIPAL_ID = "sig_principal"

#: The seller's own host, DOTTED so ``canonical_agent_url`` derives ``https://`` for it.
#:
#: Load-bearing since #1291 D1: a stored ``request_signing`` declaration with any
#: non-empty bucket fires the pinned ``identity.brand_json_url`` ``required_when``, and
#: the pin fixes that pointer to ``^https://``. ``_get_protocol_for_domain``
#: deliberately derives ``http`` for localhost and single-label hosts, so on the default
#: integration host every declaration :func:`declared_posture` writes would be REFUSED —
#: and the suites would grade the refusal path while reading like they graded the
#: declared one. Requests still reach this tenant by the ``x-adcp-tenant`` header
#: (:func:`request_headers`), so the host is identity, not routing.
SIGNING_AGENT_HOST = "seller-signing.example.com"

#: An AdCP surface path with no request body — the cheapest place to grade the
#: header-presence branches. Auth-optional, so any 401 seen on it came from the
#: verifier and not from the route's own auth dependency.
BODYLESS_ADCP_PATH = "/api/v1/capabilities"

#: The body-rewriter collision site (R-H2). ``account_id`` is a DEPRECATED field
#: name: ``normalize_request_params`` translates ``account_id`` → ``account``
#: (``src/core/request_compat.py``), which sets ``translations_applied`` and makes
#: ``RestCompatMiddleware`` rewrite the body.
REWRITTEN_ADCP_PATH = "/api/v1/media-buys"

#: Metric names from B1 plan step 6. ``code`` collapses to ``"other"`` outside the
#: 27 spec strings; ``keyid`` is the real value only after step-7 resolution.
VERIFIED_METRIC = "adcp_request_signature_verified_total"
FAILED_METRIC = "adcp_request_signature_failed_total"

#: The AdCP operations the B1 shadow-mode ladder invokes, and which the A5
#: revocation suite declares alongside it so both bucket the same two names.
#:
#: Two names rather than one, because the ladder runs on two routes:
#: ``/api/v1/capabilities`` (both verbs) is ``get_adcp_capabilities`` and POST
#: ``/api/v1/media-buys`` is ``create_media_buy``. Each test exercises exactly one
#: of them and :func:`bucketed_declaration` puts BOTH in the bucket under test, so
#: every assertion grades the same thing against real operation names rather than
#: the empty string the pre-B2 resolver returned.
LADDER_OPERATIONS = ("get_adcp_capabilities", "create_media_buy")


def signing_key_repo(env: Any, tenant_id: str) -> Any:
    """Commit pending factory data and build a tenant-scoped SigningKeyRepository."""
    from src.core.database.repositories.signing_key import SigningKeyRepository

    return SigningKeyRepository(env.get_session(), tenant_id)


def provision_key(
    repo: Any,
    tenant_id: str,
    kid: str,
    *,
    alg: str = "ed25519",
    purpose: str = REQUEST_SIGNING,
) -> Any:
    """Mint a keypair through production and return the persisted SigningKey row.

    Returns the ROW, not the whole ``ProvisionedKey``: a ``db:`` mint hands back no
    PEM (the ciphertext is on the row), which is the only shape this helper is used
    for.
    """
    from src.core.signing.keys import provision_signing_key

    return provision_signing_key(
        repo,
        tenant_id=tenant_id,
        alg=alg,
        kid=kid,
        purpose=purpose,
    ).row


@contextmanager
def deployment_kek(monkeypatch: Any, name: str = "SALESAGENT_TEST_SIGNING_KEK") -> Iterator[None]:
    """Configure the one deployment-wide KEK for the duration of a test.

    ``db:`` minting REFUSES without it — there is no plaintext fallback — so every
    suite that provisions a key through production needs this. ``key_passphrase``
    is resolved from the environment on every use (deliberately uncached), but the
    ``AppConfig`` carrying ``key_passphrase_env`` is a process global, so the
    cached config is dropped too.
    """
    monkeypatch.setenv("ADCP_SIGNING_KEY_PASSPHRASE_ENV", name)
    monkeypatch.setenv(name, "correct-horse-battery-staple")
    monkeypatch.setattr("src.core.config._config", None, raising=False)
    yield


def get_trust_root_document(client: Any, path: str, tenant: Any) -> dict[str, Any]:
    """GET a trust-root document for *tenant*'s host, failing loudly on non-200.

    One home for the Host-scoped fetch so a missing route reports itself as a
    missing route rather than as a ``KeyError`` or a schema violation three
    assertions later — and so the A3 publication suite and the A-provisioning
    suite cannot drift into two fetches. It lives here rather than in either
    module because a module whose job is to BE a test must not also be a helper
    library (``tests/unit/test_architecture_no_cross_test_module_imports.py``).
    """
    response = client.get(path, headers={"Host": tenant.virtual_host})
    assert response.status_code == 200, (
        f"GET {path} with Host {tenant.virtual_host!r} must return 200; got "
        f"{response.status_code} {response.text[:200]!r}"
    )
    return response.json()


def published_kids(entries: list[dict[str, Any]]) -> set[str]:
    """The ``kid`` set of a published JWK/signing-key list."""
    return {entry["kid"] for entry in entries}


def resolve_provider(
    repo: Any,
    tenant_id: str,
    *,
    now: datetime,
    kid: str | None = None,
    purpose: str = REQUEST_SIGNING,
) -> Any:
    """Resolve a SigningProvider through production (row -> ref -> PEM -> tripwire)."""
    from src.core.signing.provider import resolve_signing_provider

    return resolve_signing_provider(repo, tenant_id=tenant_id, purpose=purpose, now=now, kid=kid)


# ---------------------------------------------------------------------------
# B1 verifier seams (promoted from tests/integration/test_request_signature_middleware.py)
# ---------------------------------------------------------------------------


@contextmanager
def declared_posture(*, tenant_id: str = SIGNING_TENANT_ID, **declaration: Any) -> Iterator[None]:
    """Store *declaration* as *tenant_id*'s REAL ``request_signing`` declaration.

    Takes the schema's own property names (``supported``,
    ``covers_content_digest``, ``required_for``, ``warn_for``, ``supported_for``,
    ``protocol_methods_*``) and writes them onto ``tenants.capability_declarations``
    through the repository, exactly as an operator would. Production then does all
    the rest for real: ``CapabilityDeclarations.from_tenant`` parses and
    relation-checks the document, ``posture_for_tenant`` reads it,
    ``bucket_for`` applies precedence, and ``to_verifier_capability`` projects it.

    #1291 D1 is what made this possible: ``request_signing`` left
    ``_UNBACKED_BLOCKS``, so ``request_signing_is_declarable()`` is True on its own
    and there is a DB path for the declaration to travel. Until then this helper
    substituted BOTH ``posture_for_tenant`` and that predicate, and B3's green
    therefore said only "GIVEN a posture, the checklist behaves" — nothing about
    where the posture came from, which is B3 design step 12's obligation 1 and is
    what this rewrite discharges. There is no ``patch`` left in it.

    ``identity.brand_json_url`` is written alongside the posture and is DERIVED from
    ``src.core.agent_identity``, never a literal: any non-empty bucket fires the
    pinned ``required_when`` trigger, and the capabilities read path additionally
    cross-checks a declared pointer against the served one. That is why
    :func:`seed_principal` gives the tenant a DOTTED ``virtual_host`` — on
    ``localhost`` the derived pointer is ``http://`` and the pin's ``^https://``
    would (correctly) refuse the whole declaration.

    Restores the previous stored value on exit, so a suite that declares different
    postures across tests does not inherit the last one.
    """
    previous = _declare(tenant_id, declaration)
    try:
        yield
    finally:
        _restore_declarations(tenant_id, previous)


def _declare(tenant_id: str, declaration: dict[str, Any]) -> dict[str, Any] | None:
    """Write the posture + derived identity onto the tenant; return what was there."""
    from src.core.agent_identity import brand_json_url
    from src.core.database.repositories.uow import TenantConfigUoW

    with TenantConfigUoW(tenant_id) as uow:
        assert uow.tenant_config is not None
        tenant = uow.tenant_config.get_tenant()
        assert tenant is not None, (
            f"declared_posture needs tenant {tenant_id!r} to exist before a declaration can be stored "
            "on it — seed it (seed_principal / TenantFactory) first"
        )
        previous = tenant.capability_declarations
        tenant.capability_declarations = {
            "request_signing": declaration,
            "identity": {"brand_json_url": brand_json_url(tenant)},
        }
        return previous


def _restore_declarations(tenant_id: str, previous: dict[str, Any] | None) -> None:
    """Put the tenant's declaration document back the way the test found it."""
    from src.core.database.repositories.uow import TenantConfigUoW

    with TenantConfigUoW(tenant_id) as uow:
        assert uow.tenant_config is not None
        tenant = uow.tenant_config.get_tenant()
        if tenant is not None:
            tenant.capability_declarations = previous


@contextmanager
def counterparty_key(
    jwks: dict[str, Any],
    *,
    agent_url: str = COUNTERPARTY_AGENT_URL,
    jwks_uri: str = COUNTERPARTY_JWKS_URI,
    key_origin: str = COUNTERPARTY_KEY_ORIGIN,
) -> Iterator[None]:
    """Seed the whole ``AgentResolution`` for *agent_url* into the middleware cache.

    The three keyword arguments default to the shared counterparty
    (:data:`COUNTERPARTY_AGENT_URL` and friends) that every signing suite signs
    as; pass them only when a test needs a SECOND counterparty, which is the
    thing the defaults make visible at the call site.

    The middleware keys its resolver registry on the counterparty's ``agent_url``
    (read from the Principal row — security.mdx forbids taking it from a header, a
    body field or any self-assertion), and the cached object must carry ``jwks``
    AND ``jwks_uri`` AND ``key_origins`` so ``expected_key_origins`` reaches
    ``VerifyOptions`` and the step-7 key-origin check stays ON. Seeding the
    resolution is what lets these tests run the REAL verifier against real keys
    without a live counterparty — nothing about the outcome is faked.
    """
    from adcp.signing.agent_resolver import AgentResolution

    from src.core.signing import request_verifier_middleware as mw

    resolution = AgentResolution(
        agent_url=agent_url,
        brand_json_url=f"{key_origin}/.well-known/brand.json",
        agent_entry={"type": "sales", "url": agent_url, "jwks_uri": jwks_uri},
        jwks_uri=jwks_uri,
        jwks=jwks,
        fetched_at=time.time(),
        key_origins={"request_signing": key_origin},
    )
    mw.AGENT_RESOLUTION_CACHE[agent_url] = resolution
    try:
        yield
    finally:
        mw.AGENT_RESOLUTION_CACHE.pop(agent_url, None)


#: Reserved key under which :func:`verifier_spy` records what the real verifier
#: RETURNED. Not a kwarg name — chosen so it cannot collide with one.
VERIFIER_RESULT = "__verifier_result__"


@contextmanager
def verifier_spy() -> Iterator[list[dict[str, Any]]]:
    """Record every ``verify_request_signature`` call, delegating to the real one.

    Pure observation: the SDK verifier still runs and still decides. Recording the
    kwargs is what proves WHICH bytes were verified — and what makes a positive
    conformance vector non-vacuous, since "non-4xx" is equally true of a middleware
    that skipped the path entirely.

    The patched attribute is called inside a worker thread (``asyncio.to_thread``);
    ``list.append`` is atomic under the GIL, so the recording list is safe as-is.
    """
    from src.core.signing import request_verifier_middleware as mw

    calls: list[dict[str, Any]] = []
    real = mw.verify_request_signature

    def _recording(**kwargs: Any) -> Any:
        record = dict(kwargs)
        calls.append(record)
        result = real(**kwargs)
        # The RESULT under a reserved key, so a caller can assert the returned
        # ``VerifiedSigner.key_id`` — the only positive-path observable that
        # distinguishes "the verifier accepted this signature" from "the middleware
        # never looked". Absent when the verifier raised, which is itself the signal.
        record[VERIFIER_RESULT] = result
        return result

    with patch.object(mw, "verify_request_signature", _recording):
        yield calls


def rejection_code(response: Any) -> str | None:
    """The verifier's error code OFF THE WIRE, or None if it did not reject.

    The 401 carries ``WWW-Authenticate: Signature error="<code>"`` — the SDK's
    ``unauthorized_response_headers`` and the only wire signal that distinguishes a
    verifier rejection from a route-level 401. Asserting ``status_code == 401``
    alone is satisfied by auth middleware rejecting first, which is why every
    negative case reads this instead.

    Accepts anything with ``.status_code`` and ``.headers`` — an httpx response or
    a :class:`tests.helpers.asgi_wire.WireResponse`.
    """
    if response.status_code != 401:
        return None
    challenge = response.headers.get("WWW-Authenticate") or response.headers.get("www-authenticate") or ""
    if not challenge.startswith("Signature "):
        return None
    _, _, remainder = challenge.partition('error="')
    return remainder.rstrip('"') or None


def counter_samples(sample_name: str) -> dict[tuple[tuple[str, str], ...], float]:
    """All Prometheus samples named *sample_name*, keyed by their label set."""
    from prometheus_client import REGISTRY

    out: dict[tuple[tuple[str, str], ...], float] = {}
    for family in REGISTRY.collect():
        for sample in family.samples:
            if sample.name == sample_name:
                out[tuple(sorted(sample.labels.items()))] = sample.value
    return out


def counter_total(sample_name: str) -> float:
    return sum(counter_samples(sample_name).values())


def samples_with(sample_name: str, **labels: str) -> dict[tuple[tuple[str, str], ...], float]:
    """Samples of *sample_name* whose labels are a superset of *labels*."""
    wanted = labels.items()
    return {key: value for key, value in counter_samples(sample_name).items() if wanted <= dict(key).items()}


# ---------------------------------------------------------------------------
# Declaration and request construction (promoted alongside the constants above)
# ---------------------------------------------------------------------------


def bucketed_declaration(bucket: str, *operations: str) -> dict[str, Any]:
    """A ``request_signing`` declaration putting *operations* in exactly one bucket.

    ``required_for`` entries must also appear in ``supported_for``
    (``get-adcp-capabilities-response.json`` x-adcp-validation: "an operation
    can't be required without being supported"), so the required declaration lists
    both — which is also what makes the precedence rule
    ``required_for > warn_for > supported_for`` load-bearing rather than
    decorative.

    Naming the operations EXPLICITLY (rather than leaving a bucket unnarrowed) is
    what puts every other operation in the ``none`` bucket, and so what keeps the
    controls in the suites that use this meaningful.
    """
    declaration: dict[str, Any] = {"supported": True, "supported_for": list(operations)}
    if bucket == "required":
        declaration["required_for"] = list(operations)
    elif bucket == "warn":
        declaration["warn_for"] = list(operations)
    elif bucket != "supported":
        raise ValueError(f"unknown bucket {bucket!r}")
    return declaration


def keypair_for(kid: str) -> tuple[Any, dict[str, Any]]:
    """Fresh Ed25519 request-signing material for *kid*: (private_key, public JWKS)."""
    from adcp.signing import generate_signing_keypair, load_private_key_pem

    pem, public_jwk = generate_signing_keypair(alg="ed25519", kid=kid, purpose=REQUEST_SIGNING)
    return load_private_key_pem(pem), {"keys": [public_jwk]}


def seed_principal(env: Any, *, agent_url: str | None = COUNTERPARTY_AGENT_URL) -> str:
    """Create the shared tenant + a Principal carrying *agent_url*; return its token.

    ``Principal.agent_url`` (nullable ``String(500)``) is the onboarding record,
    and the only legitimate source for the counterparty's agent URL. Pass
    ``agent_url=None`` to grade what the verifier does when onboarding never
    recorded one.

    *env* is the live :class:`~tests.harness._base.BareIntegrationEnv`: it is not
    read here, but the factories below write through the session that entering the
    env bound to them, so taking it as an argument is what pins the ordering.
    """
    from tests.factories import PrincipalFactory, TenantFactory

    tenant = TenantFactory(tenant_id=SIGNING_TENANT_ID, virtual_host=SIGNING_AGENT_HOST)
    principal = PrincipalFactory(
        tenant=tenant,
        principal_id=SIGNING_PRINCIPAL_ID,
        agent_url=agent_url,
    )
    return principal.access_token


def request_headers(token: str | None, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Wire headers: tenant hint + optional bearer + whatever the test adds."""
    headers = {"x-adcp-tenant": SIGNING_TENANT_ID}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


def sign_wire_request(
    private_key: Any,
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    key_id: str = COUNTERPARTY_KID,
) -> dict[str, str]:
    """Sign *body* over the WIRE bytes, covering ``content-digest``."""
    from adcp.signing import sign_request

    signed = sign_request(
        method=method,
        url=url,
        headers=headers,
        body=body,
        private_key=private_key,
        key_id=key_id,
        alg="ed25519",
        cover_content_digest=True,
    )
    return signed.as_dict()


def just_after_provisioning() -> datetime:
    """An instant safely inside the activity window of a key provisioned just now.

    ``provision_signing_key`` stamps ``not_before`` from the wall clock, so a
    fixed literal instant would sit outside the window and make window-sensitive
    resolution fail for reasons that have nothing to do with the behavior tested.
    """
    return datetime.now(UTC) + timedelta(minutes=1)

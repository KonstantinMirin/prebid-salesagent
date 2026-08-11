"""Shared seams for the #1291 signing e2e suite (salesagent-mp53).

Every module in the suite needs the same four things, and each of them has
exactly ONE home:

* **TLS origin and CA bundle** — NOT here. ``tests/e2e/conftest.py`` already owns
  the env-var reading (:func:`~tests.e2e.conftest.e2e_tls_base_url`,
  :func:`~tests.e2e.conftest.e2e_ca_bundle`); :func:`tls_base_url` and
  :func:`ca_bundle` below only add the loud assertions the signing suite needs
  on top of them. A signing test that cannot find the TLS listener or the CA
  must FAIL, never skip — a skipped https test and a passing http one are the
  same green.
* **The tenant seam** — :func:`provisioned_trust_root_tenant`, which owns the
  ``virtual_host`` routing state the whole e2e session shares.
* **The hop-1 seed** — :func:`seeded_capabilities_factory`, needed because the
  SDK's capabilities hop raw-GETs the agent URL (SDK divergence #4, see
  ``test_trust_root_e2e``).
* **Production-path key provisioning** — :func:`provision_signing_key_via_admin`,
  which drives the real admin route over real HTTP so the row is minted under
  the SERVER CONTAINER's KEK rather than the test runner's.
* **The keyless-declaring-tenant fixture factory** — :func:`declaring_tenant_provisioner`
  — and **the anonymous capabilities fetch** — :func:`fetch_capabilities` — both needed
  by every module whose phase A proves a tenant that DECLARES a signing posture but owns
  no key yet (``mint_key=False``): the key must arrive later through a production
  transport, or the module grades its own fixture.
"""

from __future__ import annotations

import contextlib
import os
import re
import ssl
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import delete

from tests.e2e.conftest import e2e_ca_bundle, e2e_tls_base_url
from tests.e2e.utils import live_db_env

#: The super-admin the e2e stack seeds, and the endpoint that logs it in.
#: ``/test/auth`` needs ``ADCP_AUTH_TEST_MODE`` (docker-compose.e2e.yml) AND the
#: target tenant's ``auth_setup_mode``, AND a ``tenant_id`` form field — posting
#: without one aborts 404, not 401, so a missing field must not be misdiagnosed
#: as a routing problem. No ``CSRFProtect`` is registered anywhere in
#: ``src/admin``, so a raw POST is accepted.
E2E_ADMIN_EMAIL = "test_super_admin@example.com"
E2E_ADMIN_PASSWORD = "test123"

#: Flask admin is mounted at BOTH ``/admin`` and ``/`` (src/app.py). Auth and the
#: create POST are pinned to ONE prefix so the session cookie and the ``url_for``
#: redirect stay on a single script root.
_ADMIN_PREFIX = "/admin"

#: What the create route FLASHES on success (src/admin/blueprints/signing_keys.py).
#: The flash carries ``provisioned.row.kid`` from the provisioning call itself, so
#: it is what the ROUTE reported; the list table's ``kid`` is a subsequent DB
#: re-read wearing the route's clothes.
_SUCCESS_FLASH = re.compile(r"Signing key ([A-Za-z0-9._:-]+) provisioned and published\.")

#: What the revoke route FLASHES on success (src/admin/blueprints/signing_keys.py
#: :137-139) — the kid the row's OWN revoke() call reported, not a re-read.
_REVOKE_SUCCESS_FLASH = re.compile(r"Signing key ([A-Za-z0-9._:-]+) revoked\.")


def netloc(url: str) -> str:
    return httpx.URL(url).netloc.decode()


def origin(url: str) -> str:
    parsed = httpx.URL(url)
    return f"{parsed.scheme}://{parsed.netloc.decode()}"


def tls_base_url(live_server: dict) -> str:
    """The origin the stack serves TLS on, as the stack itself reports it.

    Its absence must read as a failure, never as a skip.
    """
    url = live_server.get("tls") or e2e_tls_base_url(None)
    assert url, (
        "the e2e stack publishes no TLS listener: neither live_server['tls'] nor E2E_TLS_BASE_URL is set. "
        "The tls-proxy sidecar must serve TLS at a dotted host alongside the existing plaintext port, or "
        "the discovery chain can only ever be graded over http"
    )
    assert url.startswith("https://"), f"the TLS base URL must be an https origin; got {url!r}"
    return url.rstrip("/")


def ca_bundle() -> str:
    """ABSOLUTE path to the CA that signed the test stack's leaf certificate.

    A private CA is not "publicly trusted" — but the counterparty here is our own
    client, which trusts this CA explicitly. Trusting the stack unconditionally
    instead (``verify=False``) would make every TLS leg prove nothing.
    """
    path = e2e_ca_bundle()
    assert os.path.isabs(path), (
        f"the CA bundle path must be absolute — pytest does not always run from the repo root; got {path!r}"
    )
    assert Path(path).is_file(), (
        f"the CA bundle points at no file: {path!r}. Run scripts/dev/ensure-test-tls.sh, or set E2E_CA_BUNDLE"
    )
    return path


def ca_verified_ssl_context() -> ssl.SSLContext:
    """An SSL context trusting the test stack's CA and nothing else extra."""
    return ssl.create_default_context(cafile=ca_bundle())


def seeded_capabilities_factory(body: dict):
    """A ``_capabilities_client_factory`` that serves *body* for hop 1.

    ``async_resolve_agent`` calls ``factory(agent_url)`` and uses the result as an
    async context manager, so an ``httpx.AsyncClient`` over a ``MockTransport`` is
    a drop-in — no monkeypatching of the SDK.
    """

    def factory(_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))

    return factory


def drop_tenant(live_server: dict, tenant_id: str) -> None:
    """Remove a test tenant and EVERY row that hangs off it, from the shared e2e database.

    Children go first, explicitly: the ORM ``backref`` relationships carry no
    delete cascade, so an ORM ``session.delete(tenant)`` tries to NULL a child's
    ``tenant_id`` — which is half of its composite primary key. The FK's
    ``ON DELETE CASCADE`` only applies to a database-level delete.

    And the deployed schema does not have the cascade the models claim. ``AuditLog``
    was already in this list for that reason; the same gap covers three more tables:
    ``initial_schema.py`` created ``principals``, ``products``, ``media_buys`` and
    ``audit_logs`` with a plain ``tenant_id`` FK, and no later migration ever added
    ``ON DELETE CASCADE`` — while ``models.py`` declares it on all four today. That
    model/migration drift is a real, pre-existing bug (out of scope to fix here), and
    reading the model metadata instead of the migrations is what would make this
    teardown silently incomplete. ``adapter_config``, ``property_tags``,
    ``pricing_options`` and ``contexts`` DO carry a real cascade in their creating
    migrations; they are deleted anyway, because an explicit delete of an
    already-cascaded row is a harmless no-op and depending on which half of a known
    drift is true is not.

    ``ObjectWorkflowMapping`` and ``WorkflowStep`` have no ``tenant_id`` at all, so
    they are reached through ``contexts``.

    A failure here must SURFACE. A tenant row that survives teardown keeps its
    ``virtual_host`` — session-global routing state that ``get_tenant_by_virtual_host``
    matches as an exact string — so a swallowed ``IntegrityError`` would turn one
    module's incomplete list into every later module's tenant resolving to the wrong
    row.
    """
    from sqlalchemy import select

    from src.core.database.models import (
        AdapterConfig,
        AuditLog,
        AuthorizedProperty,
        Context,
        Creative,
        CreativeAssignment,
        MediaBuy,
        MediaPackage,
        ObjectWorkflowMapping,
        Principal,
        Product,
        PropertyTag,
        PushNotificationConfig,
        SigningKey,
        Tenant,
        WebhookDeliveryLog,
        WorkflowStep,
    )

    with live_db_env(live_server) as env:
        session = env.get_session()
        context_ids = select(Context.context_id).where(Context.tenant_id == tenant_id)
        step_ids = select(WorkflowStep.step_id).where(WorkflowStep.context_id.in_(context_ids))
        session.execute(delete(ObjectWorkflowMapping).where(ObjectWorkflowMapping.step_id.in_(step_ids)))
        session.execute(delete(WorkflowStep).where(WorkflowStep.context_id.in_(context_ids)))
        # ``media_packages`` has no tenant_id and its FK to media_buys carries no cascade,
        # so a created media buy is unreachable from the tenant-scoped deletes below.
        media_buy_ids = select(MediaBuy.media_buy_id).where(MediaBuy.tenant_id == tenant_id)
        session.execute(delete(MediaPackage).where(MediaPackage.media_buy_id.in_(media_buy_ids)))
        # ``PricingOption`` is deliberately NOT deleted directly: the
        # ``prevent_empty_pricing_options`` trigger REFUSES to remove a product's last
        # pricing option while that product still exists, and explicitly allows the same
        # row to go via the product's cascade. The composite FK's ``ON DELETE CASCADE``
        # (migration c3b75d304773) is real, so deleting ``Product`` takes it.
        for model in (
            Context,
            CreativeAssignment,
            WebhookDeliveryLog,
            Creative,
            PushNotificationConfig,
            MediaBuy,
            Product,
            Principal,
            PropertyTag,
            AdapterConfig,
            SigningKey,
            AuthorizedProperty,
            AuditLog,
            Tenant,
        ):
            session.execute(delete(model).where(model.tenant_id == tenant_id))
        session.commit()


def _seed_buying_surface(env: Any, tenant: Any, *, access_token: str) -> None:
    """Everything a live ``create_media_buy`` needs on *tenant*, and nothing more.

    Seeded through the seam's OWN ``live_db_env`` session, which is why *env* is a
    parameter rather than something opened here: the factory binding is global state and
    :func:`~tests.e2e.utils.live_db_env` refuses to nest, so a caller cannot reach for
    ``set_live_adapter_behavior`` while the seam's context is still open.

    Deliberately NOT a ``CurrencyLimit``: ``TenantFactory`` already auto-creates the
    USD one through its ``currency_usd`` ``RelatedFactory``, and a second insert would
    collide rather than help.

    ``PropertyTagFactory``'s ``tag_id`` is a ``Sequence`` (``tag_0001``), while
    ``ProductFactory.property_tags`` defaults to ``["all_inventory"]`` — so the id is
    passed explicitly or the product's tag reference dangles.

    The access token is handed IN as a caller-supplied literal rather than read back
    out of the created row: the seam's ``yield`` stays a 2-tuple, so the three call
    sites that pass nothing are untouched by the existence of this seed.
    """
    from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, PropertyTagFactory
    from tests.factories.core import set_adapter_test_behavior

    PrincipalFactory(tenant=tenant, access_token=access_token)
    PropertyTagFactory(tenant=tenant, tag_id="all_inventory")
    # ``publisher_properties`` is spelled out rather than left to the model's fallback.
    # The fallback derives ``publisher_domain`` from ``tenant.virtual_host``, which on
    # this seam carries the stack's PORT — and the AdCP ``Product`` schema types that
    # field as a bare hostname, so the derived value fails validation and every read of
    # the product 500s before anything about signing is reached.
    publisher_domain = (tenant.virtual_host or "").split(":")[0]
    # ``property_tags`` is cleared in the same breath: ``ck_product_authorization`` is an
    # XOR across properties / property_ids / property_tags, so the factory's default tag
    # list and an explicit ``properties`` cannot both stand.
    product = ProductFactory(
        tenant=tenant,
        property_tags=None,
        properties=[
            {"publisher_domain": publisher_domain, "property_tags": ["all_inventory"], "selection_type": "by_tag"}
        ],
    )
    PricingOptionFactory(product=product)
    # Creates the mock AdapterConfig row and pins approval in one call — e2e shares one
    # database and pytest-randomly reorders, so leftover approval state is not something
    # a delivery-dependent module can trust.
    set_adapter_test_behavior(env, tenant.tenant_id, manual_approval_required=False)


@contextlib.contextmanager
def provisioned_trust_root_tenant(
    live_server: dict,
    *,
    tenant_id: str,
    slug: str,
    host: str,
    mint_key: bool = True,
    declarations_from_tenant: Callable[[Any], dict[str, Any]] | None = None,
    buyer_access_token: str | None = None,
    counterparty_principals: Mapping[str, str] | None = None,
) -> Iterator[tuple]:
    """The tenant seam, shared by every signing e2e module.

    ``virtual_host`` is set to the stack's own host:port so that
    ``canonical_agent_url`` resolves to somewhere a resolver can actually reach —
    otherwise the hops below would be pointed at a domain that does not exist and
    the test would grade nothing. That is not hypothetical: 635 of 638
    ``TenantFactory`` sites leave ``virtual_host`` NULL, which makes the server
    derive ``<subdomain>.sales-agent.example.com`` — already dotted, so already
    https, at a host that serves no JWKS. A test written against one of those
    passes vacuously.

    ``get_tenant_by_virtual_host`` (``src/core/config_loader.py``) is an EXACT
    string match against the Host header, so *host* must carry the port whenever
    the client will send one.

    *mint_key* is False for a tenant whose key must be provisioned through a
    PRODUCTION path instead (see :func:`provision_signing_key_via_admin`) — a
    runner-minted key grades the fixture, and is encrypted under the runner's KEK
    rather than the server container's.

    *declarations_from_tenant* receives the just-built tenant so a declaration can
    carry ``identity.brand_json_url`` DERIVED from it (``src.core.agent_identity``)
    rather than a literal, which is what ``validate_signing_platform_backing``
    cross-checks.

    *buyer_access_token* is opt-in and default-off. Passing one additionally seeds the
    principal / adapter config / property tag / product / pricing option a live
    ``create_media_buy`` needs (:func:`_seed_buying_surface`), authenticated by that
    exact literal — which is how a caller that must DRIVE this tenant gets a usable
    token without the yield growing a third element. Callers that pass nothing get
    byte-for-byte the tenant they got before.

    *counterparty_principals* maps ``access_token -> agent_url`` and seeds one Principal
    per entry. ``Principal.agent_url`` is the ONLY legitimate source for an inbound
    counterparty's identity (security.mdx forbids taking it from a header or a body
    field) and it is the sole input to the verifier's key-resolution walk
    (``_resolve_request_context`` -> ``_resolution_for``), so a module grading the
    INBOUND signed path needs a principal that carries one — which
    :func:`_seed_buying_surface` deliberately does not create (``PrincipalFactory``
    leaves the nullable column NULL). Two entries rather than one is the ordinary case
    there: a counterparty whose brand.json lists it and one whose does not resolve to
    two DIFFERENT ``agent_url`` values, and ``AGENT_RESOLUTION_CACHE`` is keyed on
    exactly that, so they cannot collide.

    Note that the session below stays bound for the whole ``yield``: a caller cannot
    open a second ``live_db_env`` from its test body, so anything that must be seeded
    belongs in the seed above rather than in the test.

    The row is removed at both ends: ``virtual_host`` is host-routing state
    shared by the whole e2e session.
    """
    from tests.factories import AuthorizedPropertyFactory, PrincipalFactory, SigningKeyFactory, TenantFactory

    drop_tenant(live_server, tenant_id)
    try:
        with live_db_env(live_server) as env:
            tenant = TenantFactory(
                tenant_id=tenant_id,
                subdomain=f"seller-{slug}".replace("_", "-"),
                virtual_host=host,
            )
            key = SigningKeyFactory(tenant=tenant, kid=f"adcp-{slug}-key") if mint_key else None
            AuthorizedPropertyFactory(tenant=tenant, publisher_domain=host, tags=["premium_news"])
            if buyer_access_token is not None:
                _seed_buying_surface(env, tenant, access_token=buyer_access_token)
            for access_token, agent_url in (counterparty_principals or {}).items():
                PrincipalFactory(tenant=tenant, access_token=access_token, agent_url=agent_url)
            if declarations_from_tenant is not None:
                tenant.capability_declarations = declarations_from_tenant(tenant)
            env._commit_factory_data()
            yield tenant, key
    finally:
        drop_tenant(live_server, tenant_id)


@contextlib.contextmanager
def declaring_tenant_provisioner(
    live_server: dict,
    *,
    tenant_id: str,
    slug: str,
    declarations_from_tenant: Callable[[Any], dict[str, Any]],
    buyer_access_token: str | None = None,
) -> Iterator[Callable[[str], tuple]]:
    """A per-host ``provision(host)`` factory for a keyless, signing-DECLARING tenant.

    Shared by every phase-A fixture in this suite: the tenant must advertise a signing
    posture (via *declarations_from_tenant*) while owning no key (``mint_key=False`` is
    fixed here, not a parameter — a module whose phase A mints its own key grades its own
    fixture rather than a production provisioning path). Wrapped in an ``ExitStack`` so
    the assertions about *where* the TLS listener is happen in the caller's test body and
    fail as failures, not as fixture-setup errors — ``provision(host)`` is called there,
    not here.

    *buyer_access_token* forwards to :func:`provisioned_trust_root_tenant` for modules
    that must DRIVE the tenant (e.g. a real ``create_media_buy``); modules that only
    fetch discovery documents leave it unset.
    """
    stack = contextlib.ExitStack()

    def provision(host: str) -> tuple:
        return stack.enter_context(
            provisioned_trust_root_tenant(
                live_server,
                tenant_id=tenant_id,
                slug=slug,
                host=host,
                mint_key=False,
                declarations_from_tenant=declarations_from_tenant,
                buyer_access_token=buyer_access_token,
            )
        )

    with stack:
        yield provision


async def fetch_capabilities(client: httpx.AsyncClient, path: str = "/api/v1/capabilities") -> dict[str, Any]:
    """The served capabilities document, fetched anonymously over the CA-verified client.

    Anonymous on purpose: discovery responses describe the SELLER, not the caller
    (AdCP INV-4), and the tenant is resolved from the Host header — which is what lets a
    counterparty holding no credential reach this document at all.
    """
    response = await client.get(path)
    assert response.status_code == 200, (
        f"the capabilities document must be served anonymously over TLS at {path!r}; "
        f"got HTTP {response.status_code}. Body: {response.text[:300]!r}"
    )
    return response.json()


def _admin_post_expecting_flash(
    base_url: str,
    *,
    tenant_id: str,
    path: str,
    data: dict[str, str],
    pattern: re.Pattern[str],
    not_found_hint: str = "",
) -> str:
    """Authenticate, POST one admin form, and return the flash's captured group.

    The shared shape behind every signing-key admin-route driver in this module
    (#1291 mp53.6, architect review MEDIUM-6): authenticate as the e2e
    super-admin, POST *path* with *data* and follow the redirect (Flask renders
    the flash on the destination page), assert 200, then extract *pattern*'s
    first captured group. Extracting only the auth block and leaving the
    POST/assert/extract steps duplicated per driver would be the same defect
    one layer down, so this is the unit that gets shared.
    """
    import requests

    with requests.Session() as session:
        session.verify = ca_bundle()
        auth = session.post(
            f"{base_url}{_ADMIN_PREFIX}/test/auth",
            data={"email": E2E_ADMIN_EMAIL, "password": E2E_ADMIN_PASSWORD, "tenant_id": tenant_id},
            allow_redirects=False,
            timeout=30,
        )
        assert auth.status_code in (200, 302), (
            f"admin test auth must succeed before {path!r} can be driven through the admin route; POST "
            f"{_ADMIN_PREFIX}/test/auth returned HTTP {auth.status_code}. A 404 here means "
            f"ADCP_AUTH_TEST_MODE is off, the tenant's auth_setup_mode is off, or the tenant_id form "
            f"field never arrived — it is not a routing problem. Body: {auth.text[:300]!r}"
        )

        response = session.post(
            f"{base_url}{path}",
            data=data,
            allow_redirects=True,
            timeout=30,
        )
        assert response.status_code == 200, (
            f"the admin route {path!r} must succeed; got HTTP {response.status_code} for tenant "
            f"{tenant_id!r}. Body: {response.text[:300]!r}"
        )

    match = pattern.search(response.text)
    assert match is not None, (
        f"the admin route {path!r} must report its outcome in a success flash matching "
        f"{pattern.pattern!r}; the rendered page carries no such message for tenant {tenant_id!r}. "
        f"{not_found_hint}Page: {response.text[:600]!r}"
    )
    return match.group(1)


def provision_signing_key_via_admin(base_url: str, *, tenant_id: str, alg: str = "ed25519") -> str:
    """Mint one signing key through the PRODUCTION admin route, over real HTTP.

    Returns the ``kid`` **the route reported**, read out of its success flash.

    Why this route rather than ``SigningKeyFactory`` or the harness's
    ``_provision_signing_key``: both of those mint inside the TEST RUNNER, under
    the runner's KEK, while the server holds a different one. Publication would
    still pass (a JWKS projects the PUBLIC half only), which is precisely why it
    would be a green that means nothing. Driving the admin route mints the row
    inside the server container, so the key is one the server can actually open
    later.
    """
    return _admin_post_expecting_flash(
        base_url,
        tenant_id=tenant_id,
        path=f"{_ADMIN_PREFIX}/tenant/{tenant_id}/signing-keys/create",
        data={"alg": alg, "ref_scheme": "db"},
        pattern=_SUCCESS_FLASH,
        not_found_hint=(
            "If a 'Could not provision a signing key' flash is present instead, the container's signing "
            "KEK (ADCP_SIGNING_DEV_KEK) is missing. "
        ),
    )


def revoke_signing_key_via_admin(base_url: str, *, tenant_id: str, kid: str) -> str:
    """Revoke one signing key through the PRODUCTION admin route, over real HTTP.

    Returns the ``kid`` **the route reported revoking**, read out of its
    success flash (the row's own ``revoke()`` call, not a subsequent re-read) —
    the same shape as :func:`provision_signing_key_via_admin`, through the
    shared :func:`_admin_post_expecting_flash`.
    """
    return _admin_post_expecting_flash(
        base_url,
        tenant_id=tenant_id,
        path=f"{_ADMIN_PREFIX}/tenant/{tenant_id}/signing-keys/{kid}/revoke",
        data={},
        pattern=_REVOKE_SUCCESS_FLASH,
        not_found_hint=f"If a 'No signing key {kid} for this tenant.' flash is present instead, {kid!r} was never provisioned for this tenant, or was already revoked under a different kid. ",
    )


def signing_declarations(operation: str) -> Callable[[Any], dict[str, Any]]:
    """A ``declarations_from_tenant`` callback declaring *operation* as ``supported_for``.

    Generalizes ``test_jwks_publication_e2e.py``'s former module-private
    ``_signing_declarations`` (#1291 mp53.6) into a reusable factory: every
    signing e2e module that needs "declare a request_signing posture, own no
    key yet" wants the SAME shape with a different operation name.
    ``brand_json_url`` is DERIVED from the tenant rather than literalled
    because the capabilities read path cross-checks the declared pointer
    against the one it actually serves (``validate_signing_platform_backing``)
    and refuses a mismatch.
    """

    def _declarations(tenant: Any) -> dict[str, Any]:
        from src.core.agent_identity import brand_json_url

        return {
            # ``supported`` is a required member of the block; the non-empty
            # bucket beside it is what actually fires ``requires_trust_root``.
            "request_signing": {"supported": True, "supported_for": [operation]},
            "identity": {"brand_json_url": brand_json_url(tenant)},
        }

    return _declarations


def keyless_declaring_tenant_fixture(*, tenant_id: str, slug: str, operation: str) -> Callable[..., Iterator[tuple]]:
    """Build a ``keyless_declaring_tenant`` pytest fixture for *tenant_id*/*slug*.

    Every signing e2e module wants the SAME wrapper around
    :func:`declaring_tenant_provisioner` + :func:`signing_declarations` — "a
    tenant that DECLARES a signing posture and owns NO key, at a
    caller-supplied netloc" — varying only the tenant/slug/operation
    (#1291 mp53.6, pylint R0801). Assign the return value directly to a
    module-level ``keyless_declaring_tenant`` name; pytest fixture-collects it
    the same as a ``@pytest.fixture``-decorated function::

        keyless_declaring_tenant = keyless_declaring_tenant_fixture(
            tenant_id=_TENANT_ID, slug=_SLUG, operation=_DECLARED_OPERATION
        )
    """

    @pytest.fixture
    def _keyless_declaring_tenant(live_server: dict) -> Iterator[Callable[[str], tuple]]:
        with declaring_tenant_provisioner(
            live_server,
            tenant_id=tenant_id,
            slug=slug,
            declarations_from_tenant=signing_declarations(operation),
        ) as provision:
            yield provision

    return _keyless_declaring_tenant

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
"""

from __future__ import annotations

import contextlib
import os
import re
import ssl
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
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
    """Remove a test tenant and its children from the shared e2e database.

    Children go first, explicitly: the ORM ``backref`` relationships carry no
    delete cascade, so an ORM ``session.delete(tenant)`` tries to NULL a child's
    ``tenant_id`` — which is half of its composite primary key. The FK's
    ``ON DELETE CASCADE`` only applies to a database-level delete.

    ``AuditLog`` is in the list because driving a PRODUCTION admin route writes
    one (``@log_admin_action``), and its FK has no cascade — without this the
    tenant row survives teardown and the NEXT run inherits its routing state.
    """
    from src.core.database.models import AuditLog, AuthorizedProperty, SigningKey, Tenant

    with live_db_env(live_server) as env:
        session = env.get_session()
        for model in (SigningKey, AuthorizedProperty, AuditLog, Tenant):
            session.execute(delete(model).where(model.tenant_id == tenant_id))
        session.commit()


@contextlib.contextmanager
def provisioned_trust_root_tenant(
    live_server: dict,
    *,
    tenant_id: str,
    slug: str,
    host: str,
    mint_key: bool = True,
    declarations_from_tenant: Callable[[Any], dict[str, Any]] | None = None,
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

    The row is removed at both ends: ``virtual_host`` is host-routing state
    shared by the whole e2e session.
    """
    from tests.factories import AuthorizedPropertyFactory, SigningKeyFactory, TenantFactory

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
            if declarations_from_tenant is not None:
                tenant.capability_declarations = declarations_from_tenant(tenant)
            env._commit_factory_data()
            yield tenant, key
    finally:
        drop_tenant(live_server, tenant_id)


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
            f"admin test auth must succeed before the signing key can be provisioned through the admin "
            f"route; POST {_ADMIN_PREFIX}/test/auth returned HTTP {auth.status_code}. A 404 here means "
            f"ADCP_AUTH_TEST_MODE is off, the tenant's auth_setup_mode is off, or the tenant_id form "
            f"field never arrived — it is not a routing problem. Body: {auth.text[:300]!r}"
        )

        created = session.post(
            f"{base_url}{_ADMIN_PREFIX}/tenant/{tenant_id}/signing-keys/create",
            data={"alg": alg, "ref_scheme": "db"},
            allow_redirects=True,
            timeout=30,
        )
        assert created.status_code == 200, (
            f"the admin signing-key create route must succeed; got HTTP {created.status_code} for tenant "
            f"{tenant_id!r}. Body: {created.text[:300]!r}"
        )

    match = _SUCCESS_FLASH.search(created.text)
    assert match is not None, (
        "the admin create route must report the kid it provisioned in its success flash; the rendered "
        f"page carries no 'Signing key <kid> provisioned and published.' message for tenant {tenant_id!r}. "
        "If a 'Could not provision a signing key' flash is present instead, the container's signing KEK "
        f"(ADCP_SIGNING_DEV_KEK) is missing. Page: {created.text[:600]!r}"
    )
    return match.group(1)

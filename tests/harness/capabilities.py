"""CapabilitiesEnv — integration test environment for _get_adcp_capabilities_impl.

Patches: adapter CLASS resolver + audit logger ONLY.
Real: get_db_session, TenantConfigUoW (publisher partners), the full response
builder (all hit real DB).

Production reads adapter default_channels/get_targeting_capabilities off a
tenant-resolved adapter CLASS (get_adapter_class_for_tenant,
src/core/helpers/adapter_helpers.py) — principal-free, identical for
anonymous and authenticated callers per INV-4 (salesagent-dn2s). The mock
below stands in for that class: production code only reads class-level
attributes/staticmethods off it, so a MagicMock works interchangeably.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with CapabilitiesEnv() as env:
            tenant, principal = env.setup_default_data()
            response = env.call_impl()
            assert response.supported_protocols

Available mocks via env.mock:
    "adapter"      -- get_adapter (module-level import in capabilities.py)
    "audit_logger" -- log_tool_activity (module-level import in capabilities.py)

beads: salesagent-4sn7 (#1592 / #1210)
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from adcp.types import GetAdcpCapabilitiesRequest, GetAdcpCapabilitiesResponse

from src.adapters.base import TargetingCapabilities
from tests.harness._base import IntegrationEnv
from tests.harness._realize import e2e_unsupported, realize_e2e

#: Default channels seeded on the adapter mock — matches the feature fixture
#: comment ("fixture seeds channels 'display, social, ctv' on the adapter").
DEFAULT_ADAPTER_CHANNELS = ["display", "social", "ctv"]

#: The tenant's own host for every signing scenario, DOTTED on purpose — see
#: :meth:`CapabilitiesEnv.declare_signing`. A single-label host derives ``http://``,
#: which no conformant ``identity.brand_json_url`` can be built from.
SIGNING_AGENT_HOST = "seller-capabilities.example.com"

#: docker-compose.e2e.yml's adcp-server service, whose environment names the ONE
#: KEK the LIVE SERVER CONTAINER holds. e2e_rest scenarios resolve a provisioned
#: key through THAT container, not through this test process, so the runner's KEK
#: must match it exactly -- a hardcoded literal that drifts from compose is
#: precisely the KEK mismatch salesagent-dn4i's fix now correctly detects and
#: refuses to sign with (previously masked by the bug that fix closed).
_COMPOSE_SERVICE = "adcp-server"

#: Default pricing models seeded on the adapter mock -- mirrors the REAL
#: MockAdServerAdapter.get_supported_pricing_models() set (mock_ad_server.py),
#: so the harness's MagicMock stand-in doesn't silently degrade to an empty
#: iterator (MagicMock() auto-implements __iter__ -> iter([]) unless a
#: return_value is set) for the one BDD scenario family (T-UC-010-pricing)
#: that actually exercises this method.
DEFAULT_ADAPTER_PRICING_MODELS = {"cpm", "vcpm", "cpcv", "cpp", "cpc", "cpv", "flat_rate"}


def _full_targeting_capabilities() -> TargetingCapabilities:
    """A TargetingCapabilities with every dimension enabled."""
    from dataclasses import fields

    return TargetingCapabilities(**{f.name: True for f in fields(TargetingCapabilities)})


class CapabilitiesEnv(IntegrationEnv):
    """Integration test environment for get_adcp_capabilities.

    Only mocks the adapter factory and the audit logger. Everything else is
    real: real DB, real TenantConfigUoW (publisher partners), real transport
    wrappers. Capabilities is a pure read — no adapter I/O beyond attribute
    access on the mock.

    Transport routing:
    - call_impl(): direct _get_adcp_capabilities_impl (sync)
    - call_a2a(): real AdCPRequestHandler pipeline
    - call_mcp(): real FastMCP in-memory Client (wire_response is real wire)
    - REST: /api/v1/capabilities is a GET route with no body — _run_rest_request
      is overridden to GET (the base implementation POSTs)
    """

    EXTERNAL_PATCHES = {
        "adapter": "src.core.tools.capabilities.get_adapter_class_for_tenant",
        "audit_logger": "src.core.tools.capabilities.log_tool_activity",
    }

    REST_ENDPOINT = "/api/v1/capabilities"
    # RestE2EDispatcher honors this hook (dispatchers.py) — the live route is GET.
    REST_METHOD = "get"

    def _configure_mocks(self) -> None:
        """Happy-path adapter: default channels + full targeting capabilities."""
        adapter = MagicMock()
        adapter.default_channels = list(DEFAULT_ADAPTER_CHANNELS)
        adapter.get_targeting_capabilities.return_value = _full_targeting_capabilities()
        adapter.get_supported_pricing_models.return_value = set(DEFAULT_ADAPTER_PRICING_MODELS)
        self.mock["adapter"].return_value = adapter
        self._adapter_mock = adapter
        self._capability_declarations: dict[str, Any] = {}

    # -- Given-step helpers ---------------------------------------------------

    def declare_capabilities(self, **blocks: Any) -> None:
        """Persist the tenant's capability declaration blocks (salesagent-3xmz).

        Each keyword is one declaration block keyed exactly as it appears in the
        capability-declaration store (``trusted_match``, ``creative_specs``,
        ``measurement``, ...); repeated calls MERGE, so a scenario may build the
        declaration across several Given steps.

        No ``@realize_e2e``: this is a real tenant-config DB write, not a
        monkeypatch. ``configure_tenant_field`` (tests/harness/_base.py) updates
        both the in-memory tenant overrides (mock identity path) and the DB
        ``tenants`` row, which the real MCP/A2A/e2e auth chain reads back via
        ``config_loader.get_tenant_by_id`` — the same shape as the undecorated
        ``set_billing_policy`` / ``set_approval_mode`` precedents
        (tests/harness/account_sync.py). Because it needs no test-only injection
        seam it declares no ``E2EUnsupportedSetup``, so the e2e escape-hatch pin
        (``EXPECTED_UNSUPPORTED_DECLARATIONS``) does not grow.
        """
        self._capability_declarations.update(blocks)
        self.configure_tenant_field("capability_declarations", dict(self._capability_declarations))

    def declare_signing(
        self,
        *,
        request_signing: dict[str, Any] | None = None,
        keyed_alg: str | None = None,
        host: str = SIGNING_AGENT_HOST,
    ) -> None:
        """Put this tenant in a state where a signing posture is real (#1291 D1).

        ONE helper for every signing Given, because all of them need the same three
        things and each one is load-bearing:

        1. **A DOTTED ``virtual_host``.** ``canonical_agent_url`` derives the scheme from
           the host, and ``_get_protocol_for_domain`` deliberately answers ``http`` for
           localhost and single-label hosts — neither can present a publicly-trusted
           certificate. The pin fixes ``identity.brand_json_url`` to ``^https://``, so on
           the default integration host every declaration below would be REFUSED and the
           scenario would grade the refusal path while reading like it graded the declared
           one. This is the mechanism on the in-process transports, which have no host of
           their own at all.
        2. **A provisioned key, when the row needs a KEYED tenant.** ``webhook_signing``
           is DERIVED platform state since D1 — ``_DERIVED_BLOCKS`` refuses a declaration
           of it — so "the tenant declares webhook_signing supported=true with
           algorithms=[X]" is realized by MINTING a key of algorithm X through production
           (``provision_signing_key``), never by writing a declaration. The deployment KEK
           is configured first because a ``db:`` mint refuses without it; both env writes
           go through the env's own patcher list, so they are undone at teardown.
        3. **A DERIVED ``identity.brand_json_url``** whenever the posture names an
           operation. A non-empty bucket fires the pinned ``required_when``, and the
           capabilities read path cross-checks a declared pointer against the one it
           actually serves — so the value has to come from
           ``src.core.agent_identity.brand_json_url``, never a literal.

        Not decorated with ``@realize_e2e``: every step is a real write (the ``tenants``
        row, the ``signing_keys`` row) that a live server reads back through its own
        session, so no test-only injection seam is needed and the e2e escape-hatch pin
        does not grow. The KEK env vars are process-local, so an out-of-process e2e server
        needs its own (``docker-compose.yml`` sets one).
        """
        from src.core.agent_identity import brand_json_url
        from src.core.database.models import Tenant
        from src.core.signing.posture import request_signing_buckets_declared

        self.configure_tenant_field("virtual_host", host)
        if keyed_alg is not None:
            self._provision_signing_key(keyed_alg)
        if request_signing is None:
            return

        from src.core.signing.posture import RequestSigningPosture

        blocks: dict[str, Any] = {"request_signing": request_signing}
        # The pointer is declared ONLY where the posture obliges one, so a row that
        # declares `supported` and nothing else keeps grading the conservative default
        # (which fires no required_when trigger) rather than a trust-root-bearing posture.
        if request_signing_buckets_declared(RequestSigningPosture(**request_signing)):
            tenant = self.get_one(Tenant, tenant_id=self._tenant_id)
            assert tenant is not None, "the tenants row must exist before its identity URLs are derived"
            blocks["identity"] = {"brand_json_url": brand_json_url(tenant)}
        self.declare_capabilities(**blocks)

    def _provision_signing_key(self, alg: str) -> None:
        """Mint one ACTIVE signing key of *alg* through production, under the
        SAME KEK docker-compose.e2e.yml gives the live server container.

        ``provision_signing_key`` stamps ``not_before`` from the wall clock, so the key is
        active by the time the When step calls ``get_adcp_capabilities``. Key PRESENCE is
        then derived by production's ``signing_key_backed`` — this method never asserts a
        posture, it only creates the platform state one is derived from.

        The KEK is read straight out of compose (salesagent-dn4i) rather than a
        hardcoded literal: in-process transports (mcp/a2a/rest) resolve the key in
        THIS process, but e2e_rest resolves it in the LIVE SERVER CONTAINER, which
        only ever holds compose's value. A runner-only literal that drifted from it
        would mint a key the container can never open -- exactly the mismatch
        salesagent-dn4i's production fix now correctly detects and refuses to sign
        with, instead of the previous bug silently masking it.
        """
        import os
        from pathlib import Path
        from unittest.mock import patch

        import yaml

        from src.core.database.repositories.signing_key import SigningKeyRepository
        from src.core.signing.keys import provision_signing_key

        compose_path = Path(__file__).resolve().parents[2] / "docker-compose.e2e.yml"
        service_env = yaml.safe_load(compose_path.read_text())["services"][_COMPOSE_SERVICE]["environment"]
        kek_pointer = service_env["ADCP_SIGNING_KEY_PASSPHRASE_ENV"]
        kek_value = service_env[kek_pointer]

        for patcher in (
            patch.dict(os.environ, {"ADCP_SIGNING_KEY_PASSPHRASE_ENV": kek_pointer, kek_pointer: kek_value}),
            # The AppConfig carrying `key_passphrase_env` is a process global and is
            # already cached by the time a Given runs; the passphrase itself is re-read
            # from the environment on every use.
            patch("src.core.config._config", None),
        ):
            patcher.start()
            self._patchers.append(patcher)

        self._commit_factory_data()
        provision_signing_key(
            SigningKeyRepository(self.get_session(), self._tenant_id),
            tenant_id=self._tenant_id,
            alg=alg,
            kid=f"{self._tenant_id}-{alg}-1",
        )

    @realize_e2e(
        e2e_unsupported(
            "no production test_behavior channel for overriding reported default_channels "
            "(only 'unavailable' and 'targeting_capabilities' are wired to AdapterConfig "
            "test_behavior — salesagent-689e)"
        )
    )
    def set_adapter_channels(self, channels: list[str]) -> None:
        """Configure the channel names the adapter reports."""
        self._adapter_mock.default_channels = list(channels)

    def _realize_targeting_capabilities(self, **dims: bool) -> None:
        """E2E realization: persist targeting_capabilities into test_behavior."""
        from tests.factories.core import set_adapter_test_behavior

        set_adapter_test_behavior(self, self._tenant_id, targeting_capabilities=dims)

    @realize_e2e(_realize_targeting_capabilities)
    def set_targeting_capabilities(self, **dims: bool) -> None:
        """Configure adapter targeting capabilities from keyword flags.

        Unnamed dimensions default to False (TargetingCapabilities defaults).
        In-process: overrides the adapter mock directly. E2E: persists the
        override into AdapterConfig.config_json['test_behavior'], read by
        get_targeting_capabilities_override (src/core/helpers/adapter_helpers.py).
        """
        self._adapter_mock.get_targeting_capabilities.return_value = TargetingCapabilities(**dims)

    def _realize_adapter_unavailable(self) -> None:
        """E2E realization: persist the 'unavailable' fault-injection flag."""
        from tests.factories.core import set_adapter_test_behavior

        set_adapter_test_behavior(self, self._tenant_id, unavailable=True)

    @realize_e2e(_realize_adapter_unavailable)
    def make_adapter_unavailable(self) -> None:
        """Adapter factory raises — production degrades to default channels.

        In-process: the adapter-class mock raises directly. E2E: persists
        test_behavior['unavailable']=True, read by get_adapter_class_for_tenant
        (src/core/helpers/adapter_helpers.py), which raises for mock-adapter
        tenants only.
        """
        self.mock["adapter"].side_effect = Exception("adapter unavailable (harness)")

    @realize_e2e(
        e2e_unsupported(
            "no production tenant-config surface for the seller's advertised adcp version set "
            "(SUPPORTED_ADCP_VERSIONS/MAJORS are process-wide constants, salesagent-rldj) — a "
            "module-constant monkeypatch cannot cross a real HTTP process boundary"
        )
    )
    def set_supported_versions(self, versions: list[str]) -> None:
        """Override the seller's advertised adcp_version/adcp_major_version release set.

        In-process only: monkeypatches src.core.version_negotiation's derived
        module constants, reached by every in-process transport (a2a/mcp/rest
        within the BDD harness) via their per-call lazy re-import.
        """
        majors = sorted({int(v.split(".")[0]) for v in versions})
        version_patcher = patch("src.core.version_negotiation.SUPPORTED_ADCP_VERSIONS", list(versions))
        major_patcher = patch("src.core.version_negotiation.SUPPORTED_ADCP_MAJORS", majors)
        self.mock["supported_versions"] = version_patcher.start()
        self.mock["supported_majors"] = major_patcher.start()
        self._patchers.append(version_patcher)
        self._patchers.append(major_patcher)

    @realize_e2e(
        e2e_unsupported(
            "no production tenant-config surface for the seller's advertised build_version "
            "(src.core.version.get_version() is a process-wide package-metadata read, "
            "salesagent-rldj) — cannot be injected over real HTTP"
        )
    )
    def set_build_version(self, build_version: str) -> None:
        """Override the advisory build_version surfaced on a VERSION_UNSUPPORTED error."""
        patcher = patch("src.core.version.get_version", return_value=build_version)
        self.mock["build_version"] = patcher.start()
        self._patchers.append(patcher)

    @realize_e2e(
        e2e_unsupported(
            "no production tenant-config surface for the adcp.idempotency posture "
            "(get_idempotency_posture() is a process-wide provider, salesagent-rldj) — a "
            "module-function monkeypatch cannot cross a real HTTP process boundary"
        )
    )
    def set_idempotency_posture(
        self,
        *,
        supported: bool,
        replay_ttl_seconds: int | None = None,
        in_flight_max_seconds: int | None = None,
        account_id_is_opaque: bool = False,
    ) -> None:
        """Override the seller's declared adcp.idempotency posture.

        In-process only: monkeypatches get_idempotency_posture() at its module
        seam (src.core.tools.capabilities._build_adcp_block re-imports it per
        call). The overridden posture still flows through the REAL
        IdempotencyPosture.check_bounds()/to_sdk_union() production code --
        only the input posture is test-controlled, not the validation/shaping.
        """
        from src.core.database.repositories.idempotency_attempt import IdempotencyPosture

        posture = IdempotencyPosture(
            supported=supported,
            replay_ttl_seconds=replay_ttl_seconds,
            in_flight_max_seconds=in_flight_max_seconds,
            account_id_is_opaque=account_id_is_opaque,
        )
        patcher = patch(
            "src.core.database.repositories.idempotency_attempt.get_idempotency_posture",
            return_value=posture,
        )
        self.mock["idempotency_posture"] = patcher.start()
        self._patchers.append(patcher)

    @realize_e2e(
        e2e_unsupported("no production DB fault hook; TenantConfigUoW read failure cannot be injected over real HTTP")
    )
    def break_tenant_config_db(self) -> None:
        """Make the capabilities DB reads fail — production degrades to placeholder.

        Patches CapabilitiesUoW at the capabilities module seam, so BOTH reads it owns
        fail: the publisher partners (placeholder domain) and, since #1291 D1, the
        signing-key backing (keyless posture, no identity block). Tracked on
        ctx-independent env teardown via the standard patcher list. In-process
        only — no server-side DB-fault-injection surface exists (e2e branch
        declares E2EUnsupportedSetup).
        """
        patcher = patch(
            "src.core.tools.capabilities.CapabilitiesUoW",
            side_effect=Exception("tenant config DB failure (harness)"),
        )
        self.mock["tenant_config_uow"] = patcher.start()
        self._patchers.append(patcher)

    # invalid_token_identity() / anonymous_identity() live on BaseTestEnv
    # (tests/harness/_base.py) — every Env subclass inherits them.

    # -- Transport verbs ------------------------------------------------------

    @staticmethod
    def _build_request(**kwargs: Any) -> GetAdcpCapabilitiesRequest:
        """Build the typed request from flat When-step kwargs."""
        return GetAdcpCapabilitiesRequest(**kwargs)

    def call_impl(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Call _get_adcp_capabilities_impl directly (sync — no wrapper needed)."""
        from src.core.tools.capabilities import _get_adcp_capabilities_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        req = self._build_request(**kwargs) if kwargs else None
        return _get_adcp_capabilities_impl(req, identity)

    def call_a2a(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Call get_adcp_capabilities via real AdCPRequestHandler — full A2A pipeline."""
        return self._run_a2a_handler("get_adcp_capabilities", GetAdcpCapabilitiesResponse, **kwargs)

    def call_mcp(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Call get_adcp_capabilities via Client(mcp) — full pipeline dispatch."""
        return self._run_mcp_client("get_adcp_capabilities", GetAdcpCapabilitiesResponse, **kwargs)

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Flat kwargs (protocols/context/adcp_version/adcp_major_version) map
        1:1 onto GetCapabilitiesBody's top-level fields — no req object, no
        per-field extraction needed.
        """
        return kwargs

    def _run_rest_request(self, endpoint: str, **kwargs: Any) -> Any:
        """REST dispatch: POST /api/v1/capabilities with a JSON body when
        request params are present (protocols/context/adcp_version), else GET
        the parameterless happy-path route — both are real production routes
        (salesagent-5yik, owner decision 2026-07-24: POST, matching the
        codebase's RPC-over-REST convention).
        """
        identity = self._pop_rest_identity(kwargs)
        self._commit_factory_data()
        client = self.get_rest_client()
        self._configure_rest_auth(identity)
        if not kwargs:
            return client.get(endpoint)
        body = self.build_rest_body(**kwargs)
        return client.post(endpoint, json=body)

    def parse_rest_response(self, data: dict[str, Any]) -> GetAdcpCapabilitiesResponse:
        """Parse REST JSON into GetAdcpCapabilitiesResponse."""
        return GetAdcpCapabilitiesResponse(**data)

    # -- Async variants for @pytest.mark.asyncio tests ------------------------

    async def call_a2a_async(self, **kwargs: Any) -> GetAdcpCapabilitiesResponse:
        """Async wrapper for tests already inside an event loop."""
        return await asyncio.to_thread(self.call_a2a, **kwargs)

"""The environment, read once, as typed state.

This module is the ONE reader of the process environment. It is read when the application
is composed (``load_settings``), into a :class:`Settings` object whose fields and derived
properties are what the rest of the tree depends on. No module reads ``os.environ`` after
import, and no request-time code asks what environment it is in: it reads a named fact off
the settings, or it is handed the component the composition root selected for that fact.

Two shapes of fact live here:

- **Values**: a port, a domain, a key, a limit. Plain fields.
- **Allowances and selections**: whether loopback webhook targets are accepted, whether the
  debug routes exist, whether the creative registry serves the checked-in reference formats.
  These are named properties derived from the fields, so a call site reads the allowance it
  needs rather than the raw flag that implies it. ``ADCP_TESTING`` implies six different
  allowances; each has its own name, and the composition root uses them to pick components.

``load_settings`` rebuilds the object (a test that changes the environment calls it);
``get_settings`` returns the current one, building it on first use so a script that never
composed an app still gets a consistent view. Nothing builds it at import: a module that
needs one runtime fact while its classes are being defined (the request DTOs' extra mode)
reads :class:`RuntimeSettings` alone, so a bad credential fails where the app is composed,
not when a schema is imported.

An empty value is an unset value. CI and the compose files hand a process ``ADCP_TESTING=""``
or ``DB_PORT=""`` (``${VAR:-}``), and the helpers this module replaced read those as the
default; ``env_ignore_empty`` keeps that reading.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

from adcp.signing.agent_resolver import BrandAgentType
from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore", env_ignore_empty=True)


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


class RuntimeSettings(BaseSettings):
    """Where and how this process runs."""

    model_config = _ENV

    environment: str = "development"
    production: bool = False
    fly_app_name: str | None = None
    adcp_sales_port: int = 8080
    adcp_sales_host: str = "0.0.0.0"
    skip_nginx: bool = False
    skip_cron: bool = False
    allowed_origins: str = "http://localhost:8000"
    admin_ui_url: str = "http://localhost:8001"
    sales_agent_domain: str | None = None
    admin_domain: str | None = None
    super_admin_domain: str | None = None
    support_email: str = "support@example.com"
    adcp_agent_url: str | None = None
    adcp_multi_tenant: bool = False
    adcp_log_dir: Path = Path("logs")
    adcp_run_background_schedulers: bool = True
    flask_secret_key: str = Field(default_factory=lambda: secrets.token_hex(32))
    flask_debug: bool = False
    admin_server_type: str = "waitress"

    @property
    def is_production(self) -> bool:
        """One answer for the three spellings a deployment used to set.

        ``PRODUCTION=true``, ``ENVIRONMENT=production`` and a Fly.io app name all meant
        "this is production" to some site and not to others; security-sensitive checks
        drifted on the difference. Any of the three is production.
        """
        return self.production or self.environment.lower() == "production" or bool(self.fly_app_name)

    @property
    def is_single_tenant(self) -> bool:
        return not self.adcp_multi_tenant

    @property
    def allowed_origin_list(self) -> list[str]:
        return _csv(self.allowed_origins)

    @property
    def admin_domain_or_derived(self) -> str | None:
        if self.admin_domain:
            return self.admin_domain
        return f"admin.{self.sales_agent_domain}" if self.sales_agent_domain else None

    def sales_agent_url(self, protocol: str = "https") -> str | None:
        return f"{protocol}://{self.sales_agent_domain}" if self.sales_agent_domain else None

    @property
    def local_base_url(self) -> str:
        """The URL this process answers on when no domain is configured."""
        return f"http://localhost:{self.adcp_sales_port}"

    @property
    def session_cookie_domain(self) -> str | None:
        return f".{self.sales_agent_domain}" if self.sales_agent_domain else None

    # --- production-derived selections; runtime facts only, so a module that needs one
    # while its classes are being defined can read this group without composing the rest.

    @property
    def structured_logging(self) -> bool:
        return self.is_production

    @property
    def verbose_auth_log(self) -> bool:
        return not self.is_production

    @property
    def pydantic_extra_mode(self) -> Literal["ignore", "forbid"]:
        """Production ignores undeclared request fields (a newer buyer is served); everywhere
        else they are a hard rejection (an unimplemented spec field is loud)."""
        return "ignore" if self.is_production else "forbid"


class TestingSettings(BaseSettings):
    """Facts that exist only for test and demo deployments.

    ``adcp_testing`` is never read by business code directly: the allowances it implies
    are named on :class:`Settings` and selected at composition.
    """

    model_config = _ENV

    adcp_testing: bool = False
    adcp_auth_test_mode: bool = False
    test_super_admin_email: str = "test_super_admin@example.com"
    test_super_admin_password: str = "test123"
    test_tenant_admin_email: str = "test_tenant_admin@example.com"
    test_tenant_admin_password: str = "test123"
    test_tenant_user_email: str = "test_tenant_user@example.com"
    test_tenant_user_password: str = "test123"
    create_demo_tenant: bool = False
    create_sample_data: bool = False
    skip_migrations: bool = False


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection and pool."""

    model_config = _ENV

    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "adcp"
    db_user: str = "adcp"
    db_password: str = ""
    db_sslmode: str = "prefer"
    use_pgbouncer: bool = False
    database_query_timeout: int = 30
    database_connect_timeout: int = 10
    database_pool_timeout: int = 30
    db_pool_size: int = 10
    db_max_overflow: int = 20


class AuthSettings(BaseSettings):
    """Operator authentication and the seller's own credentials to third parties."""

    model_config = _ENV

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    google_credentials_file: str | None = None
    oauth_provider: str = "google"
    oauth_discovery_url: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_scopes: str = "openid email profile"
    super_admin_emails: str = ""
    super_admin_domains: str = ""
    tenant_management_emails: str | None = None
    tenant_management_domains: str | None = None
    tenant_management_api_key: str | None = None
    sync_api_key: str | None = None
    encryption_key: str | None = None
    gam_oauth_client_id: str = ""
    gam_oauth_client_secret: str = ""
    gcp_project_id: str | None = None
    google_application_credentials: str | None = None
    google_application_credentials_json: str | None = None

    @field_validator("gam_oauth_client_id")
    @classmethod
    def _gam_client_id_shape(cls, v: str) -> str:
        if v and not v.endswith(".apps.googleusercontent.com"):
            raise ValueError("GAM_OAUTH_CLIENT_ID must end with '.apps.googleusercontent.com'")
        return v

    @field_validator("gam_oauth_client_secret")
    @classmethod
    def _gam_client_secret_shape(cls, v: str) -> str:
        if v and not v.startswith("GOCSPX-"):
            raise ValueError("GAM_OAUTH_CLIENT_SECRET must start with 'GOCSPX-'")
        return v

    @property
    def super_admin_email_list(self) -> list[str]:
        return [e.lower() for e in _csv(self.super_admin_emails)]

    @property
    def super_admin_domain_list(self) -> list[str]:
        return [d.lower() for d in _csv(self.super_admin_domains)]

    @property
    def gam_oauth_configured(self) -> bool:
        return bool(self.gam_oauth_client_id and self.gam_oauth_client_secret)

    @property
    def tenant_management_email_list_source(self) -> str:
        """The operator list the database seed stores: the tenant-management spelling wins."""
        return self.tenant_management_emails or self.super_admin_emails

    @property
    def tenant_management_domain_list_source(self) -> str:
        return self.tenant_management_domains or self.super_admin_domains


class IntegrationSettings(BaseSettings):
    """Other services this seller talks to."""

    model_config = _ENV

    creative_agent_url: str | None = None
    approximated_api_key: str | None = None
    approximated_backend_url: str = "adcp-sales-agent.fly.dev"
    approximated_proxy_ip: str = "37.16.24.200"
    pydantic_ai_provider: str = "gemini"
    pydantic_ai_model: str = "gemini-2.0-flash"
    logfire_token: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    aws_access_key_id: str | None = None

    def provider_api_key(self, provider: str) -> str | None:
        """The API key for an AI *provider* name as ``services.ai`` spells it."""
        keys = {
            "google": self.gemini_api_key,
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "groq": self.groq_api_key,
            "bedrock": self.aws_access_key_id,
        }
        return keys.get(provider)


class LimitSettings(BaseSettings):
    """Operator-tunable ceilings and intervals."""

    model_config = _ENV

    idempotency_max_active_attempts_per_scope: int = 1000
    idempotency_insert_rate_window_seconds: int = 10
    idempotency_max_inserts_per_window: int = 300
    delivery_webhook_interval: int = 3600
    media_buy_status_check_interval: int = 60
    adcp_outbound_allow_private: bool = False
    adcp_outbound_backoff_base_seconds: float = Field(default=1.0, gt=0)
    adcp_webhook_delivery_timeout_seconds: float = Field(default=10.0, gt=0)
    adcp_webhook_breaker_failure_threshold: int = Field(default=5, gt=0)
    adcp_webhook_breaker_success_threshold: int = Field(default=2, gt=0)
    adcp_webhook_breaker_timeout_seconds: int = Field(default=60, gt=0)


# Characters that make an override key a PATTERN rather than one counterparty's keyid.
_KEYID_PATTERN_CHARS = "*?%[]"

#: AdCP 3.1.1 ``security.mdx`` §per-keyid cap, and the signed-requests test kit's
#: ``production_min_per_keyid_cap_requests``.
_PRODUCTION_MIN_PER_KEYID_CAP = 1_000_000


class CounterpartyRegistryEntry(TypedDict):
    """One configured counterparty's key material, as the request path consumes it.

    The four keys are exactly what
    :func:`src.core.signing.verifier.build_registry_resolution` reads. Declaring them here
    makes the settings boundary refuse a malformed entry, so the request path cannot meet
    one: a missing key raises ``missing`` and a misspelled one raises both ``missing`` for
    the key it failed to spell and ``extra_forbidden`` naming the misspelling.
    """

    agent_url: str
    jwks_uri: str
    key_origin: str
    jwks: dict[str, Any]


def _validate_explicit_keyid(key: str, field_name: str) -> None:
    """Refuse an empty or pattern-shaped key on a per-keyid config map.

    Shared by every per-keyid map on :class:`SigningSettings` (override maps AND the
    counterparty registry) so "explicit keyids only" is one rule, not one reimplementation
    per field — a pattern key on ANY of them would lower a protection globally, which is
    refused everywhere identically.
    """
    if not key.strip():
        raise ValueError(f"{field_name}: a key must be an explicit keyid, not empty")
    if any(char in key for char in _KEYID_PATTERN_CHARS):
        raise ValueError(
            f"{field_name}: key {key!r} looks like a pattern. Keys name explicit keyids only — "
            "a pattern would lower the protection globally, which is refused."
        )


class SigningSettings(BaseSettings):
    """Deployment-level posture for inbound RFC 9421 request verification (#1291 B1-B4).

    Everything about verification that is a property of the DEPLOYMENT rather than of a
    tenant. Verifier POSTURE is per-tenant and lives in the tenant's declaration
    (:class:`src.core.signing.posture.RequestSigningPosture`), never here — the knobs below
    are transport limits, a kill switch, and two conformance-grading relaxations that a
    production signal forbids outright.
    """

    model_config = SettingsConfigDict(env_prefix="ADCP_SIGNING_", case_sensitive=False, extra="ignore")

    # -- the kill switch ---------------------------------------------------
    verifier_enabled: bool = Field(
        default=True,
        description=(
            "Kill switch for inbound RFC 9421 verification. False makes every request resolve "
            "identity from the bearer alone, so a rollback is a flag flip and not a deploy"
        ),
    )

    # -- transport limits --------------------------------------------------
    max_skew_seconds: int = Field(default=60, gt=0)
    max_window_seconds: int = Field(default=300, gt=0)
    max_signed_body_bytes: int = Field(
        default=10 * 1024 * 1024,
        gt=0,
        description=(
            "Cap on the request body the capture middleware buffers. Bounds the memory a "
            "pre-auth caller can make one worker hold; an over-cap SIGNED request is refused"
        ),
    )

    # -- counterparty discovery -------------------------------------------
    agent_resolution_ttl_seconds: float = Field(default=3600.0, gt=0)
    agent_resolution_refetch_cooldown_seconds: float = Field(default=30.0, gt=0)
    counterparty_agent_type: BrandAgentType = Field(
        default="buying",
        description=(
            "brand.json agents[] type used to resolve a signing counterparty's JWKS. The agents "
            "that sign requests TO a sales agent are the buy side. Typed as the SDK's Literal so "
            "an env override naming a type the resolver cannot resolve is refused HERE rather "
            "than 401-ing every signed counterparty with nothing naming the cause"
        ),
    )

    # -- replay store ------------------------------------------------------
    per_keyid_cap: int = Field(default=_PRODUCTION_MIN_PER_KEYID_CAP)
    per_keyid_cap_overrides: dict[str, int] = Field(default_factory=dict)
    replay_ttl_overrides: dict[str, float] = Field(default_factory=dict)
    replay_claim_ttl_seconds: float = Field(default=60.0, gt=0)

    # -- revocation, checklist step 9 --------------------------------------
    revoked_keyids: str = Field(
        default="",
        description=(
            "Comma-separated counterparty keyids this deployment treats as revoked, regardless "
            "of any published list. Monotone in the fail-closed direction — it can only ADD "
            "rejections — which is what makes it a posture and not a backdoor"
        ),
    )
    require_revocation_list: bool = Field(default=False)
    revocation_grace_multiplier: float = Field(
        default=4.0,
        gt=0,
        description="security.mdx :1333 requires 4x; the SDK default is 2.0, so it is passed explicitly",
    )
    revocation_issuer_origin: str | None = Field(default=None)

    # -- conformance-grading key trust ------------------------------------
    counterparty_registry: dict[str, CounterpartyRegistryEntry] = Field(
        default_factory=dict,
        description=(
            "Per-keyid registered counterparty entries, consulted as a FALLBACK when a signed "
            "request resolves no principal to walk from (the signed_requests_runner sends no "
            "bearer at all). NEVER consulted when a principal-derived walk exists but FAILS. "
            "Refused entirely under a production signal"
        ),
    )

    # There is deliberately NO ``allow_private_destinations`` knob: a configurable SSRF pin
    # is a pin an operator can remove, and key discovery follows a counterparty-supplied URL.

    @property
    def revoked_keyid_list(self) -> list[str]:
        """Locally-seeded revoked keyids as a list.

        A comma-joined ``str`` rather than ``list[str]``: pydantic-settings treats sequence
        fields as complex types and JSON-parses the env value, so
        ``ADCP_SIGNING_REVOKED_KEYIDS=test-revoked-2026`` would raise at startup.
        """
        return [keyid.strip() for keyid in self.revoked_keyids.split(",") if keyid.strip()]

    @field_validator("per_keyid_cap")
    @classmethod
    def validate_per_keyid_cap(cls, v: int) -> int:
        """Refuse a GLOBAL cap below the spec floor.

        The test kit's ``grading_target_per_keyid_cap_requests: 100`` is permitted for the
        test-kit COUNTERPARTY only, which is what ``per_keyid_cap_overrides`` is for.
        """
        if v < _PRODUCTION_MIN_PER_KEYID_CAP:
            raise ValueError(
                f"ADCP_SIGNING_PER_KEYID_CAP={v} is below the spec floor of "
                f"{_PRODUCTION_MIN_PER_KEYID_CAP} live entries per keyid. Lower the cap for a "
                "single test counterparty with ADCP_SIGNING_PER_KEYID_CAP_OVERRIDES, never globally."
            )
        return v

    @field_validator("per_keyid_cap_overrides", "replay_ttl_overrides")
    @classmethod
    def validate_overrides_name_explicit_keyids(cls, v: dict[str, float], info: ValidationInfo) -> dict[str, float]:
        """Both override maps name explicit keyids — never a pattern.

        Each map lowers a spec-mandated protection (the cap, and the replay row's lifetime)
        for one counterparty. A wildcard or prefix key would re-introduce a global lowering
        by the back door, for a value nobody reads as global.
        """
        for key, value in v.items():
            _validate_explicit_keyid(key, info.field_name or "")
            if value <= 0:
                raise ValueError(f"{info.field_name}: override for keyid {key!r} must be positive, got {value}")
        return v

    @field_validator("counterparty_registry")
    @classmethod
    def validate_counterparty_registry_keys(
        cls, v: dict[str, CounterpartyRegistryEntry], info: ValidationInfo
    ) -> dict[str, CounterpartyRegistryEntry]:
        """Registry entries are keyed by explicit keyid too — same rule as the override maps.

        Only the KEY shape is checked: :class:`CounterpartyRegistryEntry` is the annotation,
        so pydantic refuses a malformed VALUE while building the field, before this runs.
        """
        for key in v:
            _validate_explicit_keyid(key, info.field_name or "")
        return v

    @model_validator(mode="after")
    def validate_test_kit_relaxations_forbidden_in_production(self) -> SigningSettings:
        """Refuse any non-empty conformance relaxation under a production signal.

        A ``@model_validator`` fires on EVERY construction, so every process that can reach
        :func:`get_settings` is covered — unlike :func:`validate_configuration`, which the
        ASGI lifespan never calls, so a deployment pointing uvicorn at ``src.app:app``
        directly would boot the registry with that guard never executing.

        The signal is the UNION of every production marker an entrypoint in this codebase
        checks, not a reuse of :func:`is_production`: the blast radius a relaxation opens —
        a keyid alone becoming sufficient to be trusted as a counterparty — warrants the
        most paranoid reading.
        """
        signal = next(
            (name for name in ("ENVIRONMENT", "PRODUCTION", "FLY_APP_NAME") if _production_signal(name)),
            None,
        )
        if signal is None:
            return self
        for field_name in ("counterparty_registry", "per_keyid_cap_overrides", "replay_ttl_overrides"):
            if getattr(self, field_name):
                raise ValueError(
                    f"{field_name} is a conformance-grading relaxation and must not be set "
                    f"when {signal} signals a production deployment"
                )
        return self


def _production_signal(name: str) -> bool:
    """Whether env var *name* is set to something that marks a production deployment.

    ``ENVIRONMENT`` counts only for the literal ``production``; the other two count for any
    non-empty value, matching ``scripts/run_server.py``'s looser reading of ``FLY_APP_NAME``.
    """
    value = os.getenv(name, "").strip()
    if name == "ENVIRONMENT":
        return value.lower() == "production"
    return bool(value)


class ToolingSettings(BaseSettings):
    """Knobs the repo's own scripts and audits read; nothing the application serves depends
    on them, so they are not part of :class:`Settings`. A script reads them where it starts."""

    model_config = _ENV

    adcp_home: Path | None = None
    adcp_req_path: Path = Path.home() / "projects" / "adcp-req"
    bdd_liveness_artifact: Path | None = None
    storyboard_ledger_path: Path | None = None
    allow_live_creative_agent: bool = False


@dataclass(frozen=True)
class Settings:
    """Everything the environment says, as one object.

    A plain composite, deliberately not a ``BaseSettings``: the groups read the environment,
    and this object only holds them. As a ``BaseSettings`` its six field names were themselves
    environment variables, so a shell with ``TESTING=1`` or ``DATABASE=x`` could not start
    the process.
    """

    runtime: RuntimeSettings
    testing: TestingSettings
    database: DatabaseSettings
    auth: AuthSettings
    integrations: IntegrationSettings
    limits: LimitSettings
    signing: SigningSettings

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            runtime=RuntimeSettings(),
            testing=TestingSettings(),
            database=DatabaseSettings(),
            auth=AuthSettings(),
            integrations=IntegrationSettings(),
            limits=LimitSettings(),
            signing=SigningSettings(),
        )

    # --- the allowances ADCP_TESTING implies, each under its own name ---------------

    @property
    def debug_routes_enabled(self) -> bool:
        """The `/debug/*` and `/_internal/*` routes exist at all."""
        return self.testing.adcp_testing

    @property
    def reference_formats_only(self) -> bool:
        """The creative registry serves the checked-in reference formats, never a network."""
        return self.testing.adcp_testing

    @property
    def loopback_webhooks_allowed(self) -> bool:
        """A buyer webhook may target localhost over plain HTTP (a capture server)."""
        return self.testing.adcp_testing

    @property
    def mock_delivery_seed_enabled(self) -> bool:
        """The mock ad server reads seeded delivery rows; the table has no production writer."""
        return self.testing.adcp_testing

    @property
    def mock_adapter_counts_as_configured(self) -> bool:
        """The setup checklist treats the mock adapter as a configured ad server."""
        return self.testing.adcp_testing

    @property
    def relaxed_brand_validation(self) -> bool:
        """get_products accepts simple test values where it would demand a real brand."""
        return self.testing.adcp_testing

    @property
    def unit_tests_may_not_open_a_database(self) -> bool:
        """Under test with no DATABASE_URL, opening an engine is a test bug, not a fallback."""
        return self.testing.adcp_testing and not self.database.database_url

    # --- production-derived selections ------------------------------------------------

    @property
    def publisher_auto_verify_allowed(self) -> bool:
        """A publisher partner is verified without an adagents.json check: a local server
        is in nobody's file. Anywhere that is not production."""
        return not self.runtime.is_production

    @property
    def structured_logging(self) -> bool:
        return self.runtime.structured_logging

    @property
    def verbose_auth_log(self) -> bool:
        return self.runtime.verbose_auth_log

    @property
    def pydantic_extra_mode(self) -> Literal["ignore", "forbid"]:
        return self.runtime.pydantic_extra_mode


_settings: Settings | None = None


def load_settings() -> Settings:
    """Read the environment and make the result the current settings.

    Called by each composition root when it starts, and by a test after it changes the
    environment. Validation failures raise here, at startup, not at the first request.
    """
    global _settings
    _settings = Settings.from_environment()
    return _settings


def get_settings() -> Settings:
    """The current settings, built on first use."""
    global _settings
    if _settings is None:
        _settings = Settings.from_environment()
    return _settings


def validate_configuration() -> None:
    """Load the settings at startup and report what is configured."""
    try:
        settings = load_settings()
    except Exception as e:
        raise RuntimeError(f"Configuration validation failed: {e}") from e

    print("✅ Configuration validation passed")
    print(f"   GAM OAuth: {'✅ Configured' if settings.auth.gam_oauth_configured else '❌ Not configured'}")
    print(f"   Database: {'✅ Configured' if settings.database.database_url else '❌ Not configured'}")
    print(
        f"   Gemini API: {'✅ Configured' if settings.integrations.gemini_api_key else '⚪ Not configured (tenants use own keys)'}"
    )
    print(
        f"   Super Admin: {'✅ Configured' if settings.auth.super_admin_emails else '⚪ Not configured (use per-tenant OIDC)'}"
    )


def is_production() -> bool:
    return get_settings().runtime.is_production


def get_pydantic_extra_mode() -> Literal["ignore", "forbid"]:
    """The request DTOs' extra mode, read while the schema modules define their classes.

    Reads :class:`RuntimeSettings` alone and never builds :class:`Settings`: importing a
    schema must not be where a bad credential fails.
    """
    return RuntimeSettings().pydantic_extra_mode

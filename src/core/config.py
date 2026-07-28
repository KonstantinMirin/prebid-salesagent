"""Configuration management for Prebid Sales Agent.

Provides Pydantic-based configuration classes for type-safe, validated configuration
management using environment variables.
"""

import os
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# AdCP 3.1.1 `security.mdx` §per-keyid cap, restated by the signed-requests test-kit
# as `production_min_per_keyid_cap_requests: 1000000`.
_PRODUCTION_MIN_PER_KEYID_CAP = 1_000_000

# Characters that make an override key a PATTERN rather than one counterparty's keyid.
_KEYID_PATTERN_CHARS = "*?%[]"


class GAMOAuthConfig(BaseSettings):
    """Google Ad Manager OAuth configuration."""

    client_id: str = Field(default="", description="GAM OAuth Client ID from Google Cloud Console")
    client_secret: str = Field(default="", description="GAM OAuth Client Secret from Google Cloud Console")

    model_config = SettingsConfigDict(env_prefix="GAM_OAUTH_", case_sensitive=False)

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, v):
        """Validate GAM OAuth Client ID format (only if provided)."""
        if not v:
            return v  # Allow empty - validation happens when GAM adapter is used
        if not v.endswith(".apps.googleusercontent.com"):
            raise ValueError("GAM OAuth Client ID must end with '.apps.googleusercontent.com'")
        return v

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret(cls, v):
        """Validate GAM OAuth Client Secret format (only if provided)."""
        if not v:
            return v  # Allow empty - validation happens when GAM adapter is used
        if not v.startswith("GOCSPX-"):
            raise ValueError("GAM OAuth Client Secret must start with 'GOCSPX-'")
        return v


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    url: str | None = Field(default=None, description="Database connection URL")
    type: str = Field(default="postgresql", description="Database type")

    model_config = SettingsConfigDict(env_prefix="DATABASE_", case_sensitive=False)


class ServerConfig(BaseSettings):
    """Server configuration."""

    adcp_sales_port: int = Field(default=8080, description="MCP server port")
    admin_ui_port: int = Field(default=8001, description="Admin UI port")
    a2a_port: int = Field(default=8091, description="A2A server port")

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class GoogleOAuthConfig(BaseSettings):
    """Google OAuth configuration for admin UI."""

    client_id: str | None = Field(default=None, description="Google OAuth Client ID")
    client_secret: str | None = Field(default=None, description="Google OAuth Client Secret")
    credentials_file: str | None = Field(default=None, description="Path to Google OAuth credentials file")

    model_config = SettingsConfigDict(env_prefix="GOOGLE_", case_sensitive=False)


class SuperAdminConfig(BaseSettings):
    """Super admin configuration."""

    emails: str = Field(default="", description="Comma-separated list of super admin emails")
    domains: str | None = Field(default=None, description="Comma-separated list of super admin domains")

    model_config = SettingsConfigDict(env_prefix="SUPER_ADMIN_", case_sensitive=False)

    @property
    def email_list(self) -> list[str]:
        """Get super admin emails as a list."""
        return [email.strip() for email in self.emails.split(",") if email.strip()]

    @property
    def domain_list(self) -> list[str]:
        """Get super admin domains as a list."""
        if not self.domains:
            return []
        return [domain.strip() for domain in self.domains.split(",") if domain.strip()]


class SigningConfig(BaseSettings):
    """Agent-level posture for OUR OWN RFC 9421 signing key material (#1291 A2).

    Not to be confused with ``adcp.signing.SigningConfig``, which is the SDK's
    auto-signing bundle — alias at any import site that touches both.

    The split this class encodes: the STORE KIND is agent-level (one process, one
    key store), while each key's LOCATION is per-tenant and lives on the
    ``signing_keys`` row's ``private_key_ref``. Each tenant is a distinct seller
    identity with its own brand domain and therefore its own key material, so a
    single agent-level key location is unimplementable.
    """

    provider: Literal["in_memory", "kms"] = Field(
        default="in_memory", description="SigningProvider implementation: in_memory (default) or kms"
    )
    allowed_key_ref_schemes: str = Field(
        default="env,file",
        description="Comma-separated private_key_ref schemes this deployment will resolve (env, file)",
    )
    key_passphrase_env: str | None = Field(
        default=None,
        description="Name of the env var holding the PEM passphrase (the passphrase itself is never a config value)",
    )

    # -- Replay store (#1291 A4) -------------------------------------------
    # These are agent-level because the replay store is a property of the shared
    # deployment, not of a tenant: one nonce is accepted at most once across every
    # worker, whichever tenant's virtual host it arrived at.
    per_keyid_cap: int = Field(
        default=1_000_000,
        description="Live replay entries per keyid before request_signature_rate_abuse (spec floor: 1,000,000)",
    )
    per_keyid_cap_overrides: dict[str, int] = Field(
        default_factory=dict,
        description="Per-counterparty cap override, keyed by explicit keyid (test-kit counterparties -> 100)",
    )
    replay_ttl_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Per-counterparty clamp (seconds) on replay row lifetime, keyed by explicit keyid",
    )
    replay_claim_ttl_seconds: float = Field(
        default=60.0,
        description="Lifetime written by the atomic claim before remember() raises it to the signature's own TTL",
    )

    model_config = SettingsConfigDict(env_prefix="ADCP_SIGNING_", case_sensitive=False)

    @property
    def key_ref_scheme_list(self) -> list[str]:
        """Allowed ``private_key_ref`` schemes as a list.

        A comma-joined ``str`` rather than a ``tuple[str, ...]`` deliberately:
        pydantic-settings treats sequence fields as complex types and JSON-parses
        the env value, so ``ADCP_SIGNING_ALLOWED_KEY_REF_SCHEMES=env,file`` would
        raise at startup and only ``["env","file"]`` would work. This is the gate
        that lets a deployment forbid ``file:`` in production — the one field
        least worth making awkward to set. Same shape as ``SuperAdminConfig``.
        """
        return [scheme.strip() for scheme in self.allowed_key_ref_schemes.split(",") if scheme.strip()]

    @property
    def key_passphrase(self) -> bytes | None:
        """Resolve the configured PEM passphrase, or None.

        Resolved from the environment on every call rather than held as a field:
        CPython cannot zero a ``bytes``, so the SDK's guidance is to source the
        passphrase per use rather than pin a literal in process memory for the
        life of the config object.
        """
        if not self.key_passphrase_env:
            return None
        value = os.getenv(self.key_passphrase_env)
        return value.encode() if value else None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Reject ``kms`` until a KMS provider exists.

        Fires when ``AppConfig()`` is constructed, which ``validate_configuration()``
        does at startup — so selecting an unimplemented provider kills the process
        then, not at the first signature (note §11).
        """
        if v == "kms":
            raise ValueError(
                "ADCP_SIGNING_PROVIDER='kms' is not implemented — no KMS SigningProvider exists yet. Use 'in_memory'."
            )
        return v

    @field_validator("per_keyid_cap")
    @classmethod
    def validate_per_keyid_cap(cls, v: int) -> int:
        """Refuse a GLOBAL cap below the spec floor.

        AdCP 3.1.1 ``security.mdx`` §per-keyid cap and the test-kit's
        ``production_min_per_keyid_cap_requests: 1000000`` put the production floor
        at 1,000,000 live entries per keyid. The test-kit's
        ``grading_target_per_keyid_cap_requests: 100`` is permitted for the test-kit
        COUNTERPARTY only, which is what ``per_keyid_cap_overrides`` is for. Refusing
        the global lowering here is the mechanical form of "never a global lowering":
        a misconfiguration kills the process at startup instead of quietly turning
        every busy signer into ``request_signature_rate_abuse``.
        """
        if v < _PRODUCTION_MIN_PER_KEYID_CAP:
            raise ValueError(
                f"ADCP_SIGNING_PER_KEYID_CAP={v} is below the spec floor of "
                f"{_PRODUCTION_MIN_PER_KEYID_CAP} live entries per keyid. Lower the cap for a single "
                "test counterparty with ADCP_SIGNING_PER_KEYID_CAP_OVERRIDES, never globally."
            )
        return v

    @field_validator("per_keyid_cap_overrides", "replay_ttl_overrides")
    @classmethod
    def validate_overrides_name_explicit_keyids(cls, v: dict[str, float], info: ValidationInfo) -> dict[str, float]:
        """Both override maps name explicit keyids — never a pattern.

        Each map lowers a spec-mandated protection (the cap, and the replay row's
        lifetime) for one counterparty. A wildcard or prefix key would re-introduce
        the global lowering the validator above refuses, by the back door and for a
        value nobody reads as global. Same rule, same reason, so one validator serves
        both fields.
        """
        for key, value in v.items():
            if not key.strip():
                raise ValueError(f"{info.field_name}: an override key must be an explicit keyid, not empty")
            if any(char in key for char in _KEYID_PATTERN_CHARS):
                raise ValueError(
                    f"{info.field_name}: override key {key!r} looks like a pattern. Overrides name explicit "
                    "keyids only — a pattern would lower the protection globally, which is refused."
                )
            if value <= 0:
                raise ValueError(f"{info.field_name}: override for keyid {key!r} must be positive, got {value}")
        return v

    @field_validator("replay_claim_ttl_seconds")
    @classmethod
    def validate_replay_claim_ttl(cls, v: float) -> float:
        """A non-positive claim TTL would write an already-dead row — i.e. no replay protection at all."""
        if v <= 0:
            raise ValueError(f"ADCP_SIGNING_REPLAY_CLAIM_TTL_SECONDS must be positive, got {v}")
        return v


class AppConfig(BaseSettings):
    """Main application configuration."""

    gemini_api_key: str | None = Field(
        default=None, description="Platform-level Gemini API key (optional - tenants can configure their own)"
    )
    flask_secret_key: str = Field(default="dev-secret-key-change-in-production", description="Flask secret key")
    debug: bool = Field(default=False, description="Enable debug mode")
    environment: str = Field(default="development", description="Environment: production, staging, or development")

    # Configuration objects
    # BaseSettings subclasses read from environment; mypy doesn't understand this pattern
    gam_oauth: GAMOAuthConfig = Field(default_factory=GAMOAuthConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    google_oauth: GoogleOAuthConfig = Field(default_factory=GoogleOAuthConfig)
    superadmin: SuperAdminConfig = Field(default_factory=SuperAdminConfig)
    signing: SigningConfig = Field(default_factory=SigningConfig)

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


# Global configuration instance
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def validate_configuration() -> None:
    """Validate all configuration at startup.

    Raises:
        ValueError: If required configuration is missing or invalid
        RuntimeError: If configuration validation fails
    """
    try:
        config = get_config()

        # Validate GAM OAuth configuration
        if config.gam_oauth:
            # Configuration validation happens automatically via Pydantic
            pass

        # Note: GEMINI_API_KEY is optional - tenants configure their own AI keys
        # Note: SUPER_ADMIN_EMAILS is optional - per-tenant OIDC with Setup Mode is the default auth flow

        # Signing: an unimplemented provider must kill the process HERE, not at
        # the first signature. The field_validator on SigningConfig already
        # raises; this names the provider explicitly rather than surfacing a raw
        # Pydantic trace.
        if config.signing.provider not in ("in_memory",):
            raise ValueError(
                f"ADCP_SIGNING_PROVIDER={config.signing.provider!r} is not implemented — "
                "the only available SigningProvider is 'in_memory'."
            )

        print("✅ Configuration validation passed")
        print(f"   GAM OAuth: {'✅ Configured' if config.gam_oauth.client_id else '❌ Not configured'}")
        print(f"   Database: {'✅ Configured' if config.database.url else '❌ Not configured'}")
        print(
            f"   Gemini API: {'✅ Configured' if config.gemini_api_key else '⚪ Not configured (tenants use own keys)'}"
        )
        print(
            f"   Super Admin: {'✅ Configured' if config.superadmin.emails else '⚪ Not configured (use per-tenant OIDC)'}"
        )

    except Exception as e:
        raise RuntimeError(f"Configuration validation failed: {str(e)}") from e


def get_gam_oauth_config() -> GAMOAuthConfig:
    """Get GAM OAuth configuration."""
    return get_config().gam_oauth


def is_production() -> bool:
    """Check if running in production environment.

    Returns:
        bool: True if ENVIRONMENT=production, False otherwise
    """
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


def get_pydantic_extra_mode() -> Literal["ignore", "forbid"]:
    """Get Pydantic extra field handling mode based on environment.

    Production: "ignore" - Accept extra fields for forward compatibility
    Non-production: "forbid" - Reject extra fields to catch bugs early
    """
    return "ignore" if is_production() else "forbid"

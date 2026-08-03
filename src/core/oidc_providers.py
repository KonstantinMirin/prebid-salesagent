"""Well-known OIDC discovery URLs — single source of truth.

Shared by the single-tenant, env-based OAuth flow (src.admin.blueprints.auth)
and the per-tenant, DB-backed OIDC config service
(src.services.auth_config_service), which previously hand-duplicated this
data and had drifted (auth_config_service.py was missing okta/auth0/keycloak
entirely, with no test catching it).
"""

# A provider mapped to None has no fixed discovery URL — it requires a
# tenant-specific parameter (subdomain, realm, server) to construct one.
OIDC_DISCOVERY_URLS: dict[str, str | None] = {
    "google": "https://accounts.google.com/.well-known/openid-configuration",
    "microsoft": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
    "okta": None,  # Requires tenant: https://{tenant}.okta.com/.well-known/openid-configuration
    "auth0": None,  # Requires tenant: https://{tenant}.auth0.com/.well-known/openid-configuration
    "keycloak": None,  # Requires server/realm: https://{server}/realms/{realm}/.well-known/openid-configuration
}

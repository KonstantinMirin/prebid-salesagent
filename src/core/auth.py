"""Authentication functions for Prebid Sales Agent.

This module provides authentication and principal resolution functions used
by both MCP and A2A protocols.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adcp.types import ContextObject

    from src.core.resolved_identity import ResolvedIdentity
    from src.core.tenant_context import LazyTenantContext
from sqlalchemy import select

from src.core.config_loader import (
    get_current_tenant,
)
from src.core.database.database_session import get_db_session
from src.core.database.models import Principal as ModelPrincipal
from src.core.errors.details import EntityRefDetails

# Buyer-facing correction hints, split per the v3.1.1 AUTH_MISSING/AUTH_INVALID
# error-code split (dist/schemas/3.1.1/enums/error-code.json, #2092).
# Canonical hints owned by exceptions.py (class-level default suggestions on
# AdCPAuthRequiredError / AdCPAuthenticationError); re-exported here for
# existing importers.
from src.core.http_utils import get_header_case_insensitive as _get_header_case_insensitive
from src.core.schemas import Principal

logger = logging.getLogger(__name__)

# Enable verbose auth logging only in development
_VERBOSE_AUTH_LOG = not (os.environ.get("FLY_APP_NAME") or os.environ.get("PRODUCTION"))


def get_push_notification_config_from_headers(headers: dict[str, str] | None) -> dict[str, Any] | None:
    """
    Extract protocol-level push notification config from MCP HTTP headers.

    MCP clients can provide push notification config via custom headers:
    - X-Push-Notification-Url: Webhook URL
    - X-Push-Notification-Auth-Scheme: Authentication scheme (HMAC-SHA256, Bearer, None)
    - X-Push-Notification-Credentials: Shared secret or Bearer token

    Returns:
        Push notification config dict matching A2A structure, or None if not provided
    """
    if not headers:
        return None

    url = _get_header_case_insensitive(headers, "x-push-notification-url")
    if not url:
        return None

    auth_scheme = _get_header_case_insensitive(headers, "x-push-notification-auth-scheme") or "None"
    credentials = _get_header_case_insensitive(headers, "x-push-notification-credentials")

    return {
        "url": url,
        "authentication": {"schemes": [auth_scheme], "credentials": credentials} if auth_scheme != "None" else None,
    }


# (Deleted) get_principal_from_context resolved a principal AND detected a tenant from a
# FastMCP Context -- its own x-adcp-tenant handling, parallel to _detect_tenant. It is the
# ancestor of src/core/resolved_identity._resolve_identity, which replaced it when identity
# resolution collapsed to one site. It had ZERO production callers and survived only
# because seven test modules called it directly; test_no_duplicate_auth_functions.py said
# so outright, keeping it "in auth.py for test compat". A second resolver kept alive by its
# own tests is still a second resolver.
#
# Its docstring carried the tell: "the caller MUST call set_current_tenant(tenant_context)
# in their own context" because ContextVar writes do not cross the sync/async boundary --
# an obligation on every caller, which is what the boundary exists to remove.


def get_principal_adapter_mapping(principal_id: str, tenant_id: str | None = None) -> dict[str, Any]:
    """Get the platform mappings for a principal."""
    if tenant_id is None:
        tenant = get_current_tenant()
        tenant_id = tenant["tenant_id"]
    with get_db_session() as session:
        stmt = select(ModelPrincipal).filter_by(principal_id=principal_id, tenant_id=tenant_id)
        principal = session.scalars(stmt).first()
        return principal.platform_mappings if principal else {}


def get_principal_object(principal_id: str, tenant_id: str | None = None) -> Principal | None:
    """Get a Principal object for the given principal_id."""
    if tenant_id is None:
        tenant = get_current_tenant()
        tenant_id = tenant["tenant_id"]
    with get_db_session() as session:
        stmt = select(ModelPrincipal).filter_by(principal_id=principal_id, tenant_id=tenant_id)
        principal = session.scalars(stmt).first()

        if principal:
            return Principal(
                principal_id=principal.principal_id,
                name=principal.name,
                platform_mappings=principal.platform_mappings,
            )
    return None


def resolve_principal_or_raise(
    principal_id: str,
    *,
    tenant_id: str | None = None,
    context: "ContextObject | dict[str, Any] | None" = None,
) -> Principal:
    """Resolve the Principal for ``principal_id`` or raise ``AdCPAuthenticationError``.

    Collapses the identical "look up the principal, fail authentication if it
    does not exist" guard shared by the create, update, and delivery media-buy
    tools into one definition. ``context`` is echoed into the error envelope so
    buyer agents can correlate the failure to their request.
    """
    from src.core.exceptions import AdCPAuthenticationError

    principal = get_principal_object(principal_id, tenant_id=tenant_id)
    if principal is None:
        raise AdCPAuthenticationError(details=EntityRefDetails(principal_id=principal_id), context=context)
    return principal


def require_principal_id(
    identity: "ResolvedIdentity",
    *,
    context: "ContextObject | dict[str, Any] | None" = None,
) -> str:
    """Return ``identity.principal_id`` or raise ``AdCPAuthRequiredError``.

    Single source of truth for the "no principal_id in identity" guard that
    every ``_impl`` runs at entry. Use this instead of open-coding the check
    across tool modules. ``context`` is echoed into the error envelope so
    buyer agents can correlate the failure to their request.
    """
    from src.core.exceptions import AdCPAuthRequiredError

    principal_id = identity.principal_id
    if not principal_id:
        # No principal_id was resolved at all (absent credential, not a
        # presented-but-rejected one) -> AUTH_MISSING per v3.1.1
        # error-code.json. Was previously the base AdCPAuthenticationError
        # (AUTH_INVALID-shaped) with mixed absent/invalid wording ("Provide a
        # valid x-adcp-auth token" reads as invalid-framing) — de-conflicted
        # per #2092 consistency-lens finding, while keeping the
        # "Principal ID not found in identity" substring existing tests match on.
        raise AdCPAuthRequiredError(
            context=context,
        )
    return principal_id


def require_tenant(
    identity: "ResolvedIdentity",
    *,
    context: "ContextObject | dict[str, Any] | None" = None,
) -> "LazyTenantContext":
    """Return ``identity.tenant`` or raise ``AdCPAuthenticationError``.

    Single source of truth for the "no tenant context available" guard — the
    most-repeated ``_impl`` prologue. Use this instead of open-coding the check
    across tool modules. The canonical message carries the actionable
    diagnostic (token + host headers) so buyer agents can self-correct.

    It returns a LazyTenantContext, and said ``dict[str, Any]`` for a long time while
    returning whatever ``identity.tenant`` held. An annotation that disagrees with the
    value is worse than none: it tells every reader, and every type checker, that
    subscripting is safe and attribute access is not, which is how dict-shaped handling
    spread from here. The context supports both, and the annotation now says what it is.
    """
    from src.core.exceptions import AdCPAuthenticationError, AdCPAuthRequiredError

    tenant = identity.tenant
    if not tenant:
        # AUTH_MISSING/AUTH_INVALID split (#2092), completed for the
        # tenant-resolution axis (salesagent-otc5). The signal is whether a
        # credential was PRESENTED, i.e. ``identity.auth_token`` — not merely
        # whether an identity object exists: resolve_identity() always builds
        # a ResolvedIdentity for discovery endpoints even with no token, and
        # for a presented-but-invalid token (require_valid_token=False) it
        # sets auth_token but leaves principal_id unresolved. No token at all
        # -> AUTH_MISSING (correctable); a token was presented but tenant
        # still didn't resolve -> AUTH_INVALID (terminal). The TENANT_REQUIRED
        # gap (salesagent-40kk) — full tenant-axis semantics beyond this
        # credential-presence split — remains tracked separately.
        if not identity.auth_token:
            raise AdCPAuthRequiredError(
                context=context,
            )
        raise AdCPAuthenticationError(
            context=context,
        )
    return tenant


def get_adapter_principal_id(principal_id: str, adapter: str, tenant_id: str | None = None) -> str | None:
    """Get the adapter-specific ID for a principal."""
    mappings = get_principal_adapter_mapping(principal_id, tenant_id=tenant_id)

    # Map adapter names to their specific fields
    adapter_field_map = {
        "gam": "gam_advertiser_id",
        "kevel": "kevel_advertiser_id",
        "triton": "triton_advertiser_id",
        "mock": "mock_advertiser_id",
    }

    field_name = adapter_field_map.get(adapter)
    if field_name:
        return str(mappings.get(field_name, "")) if mappings.get(field_name) else None
    return None

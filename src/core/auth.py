"""Authentication functions for Prebid Sales Agent.

This module provides authentication and principal resolution functions used
by both MCP and A2A protocols.
"""

import logging
from typing import TYPE_CHECKING, Any

from src.core.config import get_settings

if TYPE_CHECKING:
    from src.core.resolved_identity import ResolvedIdentity
    from src.core.tenant_context import TenantContext


# Buyer-facing correction hints, split per the v3.1.1 AUTH_MISSING/AUTH_INVALID
# error-code split (dist/schemas/3.1.1/enums/error-code.json, #2092).
# Canonical hints owned by exceptions.py (class-level default suggestions on
# AdCPAuthRequiredError / AdCPAuthenticationError); re-exported here for
# existing importers.
from src.core.http_utils import get_header_case_insensitive as _get_header_case_insensitive
from src.core.schemas import Principal

logger = logging.getLogger(__name__)

# Verbose auth logging is a development affordance
_VERBOSE_AUTH_LOG = get_settings().verbose_auth_log


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


def require_principal(identity: "ResolvedIdentity") -> Principal:
    """The principal the resolver loaded for this caller, or ``AdCPAuthRequiredError``.

    A tool acts only as the resolved principal, so this is the one principal a tool ever
    holds; nothing downstream loads one by id. The anonymous caller of a public tool has
    none, which on a tool that needs one is AUTH_MISSING. The refusal carries no request
    context: the boundary echoes the buyer's context onto the failure it builds.
    """
    from src.core.exceptions import AdCPAuthRequiredError

    if identity.principal is None:
        raise AdCPAuthRequiredError()
    return identity.principal


def require_tenant(identity: "ResolvedIdentity") -> "TenantContext":
    """Return ``identity.tenant`` or raise ``AdCPAuthenticationError``.

    Single source of truth for the "no tenant context available" guard — the
    most-repeated ``_impl`` prologue. Use this instead of open-coding the check
    across tool modules. The canonical message carries the actionable
    diagnostic (token + host headers) so buyer agents can self-correct.

    It returns a TenantContext, and said ``dict[str, Any]`` for a long time while
    returning whatever ``identity.tenant`` held. An annotation that disagrees with the
    value is worse than none: it tells every reader, and every type checker, that
    subscripting is safe and attribute access is not, which is how dict-shaped handling
    spread from here. The context supports both, and the annotation now says what it is.
    """
    from src.core.exceptions import AdCPInternalError

    tenant = identity.tenant
    if tenant is None:
        # Not an auth outcome. A protected tool is reached only with a resolved principal,
        # and a principal is a row in a tenant, so this is the resolver's invariant broken.
        # A public tool reads ``identity.tenant`` itself and answers without a seller.
        raise AdCPInternalError()
    return tenant

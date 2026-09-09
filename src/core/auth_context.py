"""Shared AuthContext populated by UnifiedAuthMiddleware, consumed by handlers.

UnifiedAuthMiddleware extracts auth_token and headers BEFORE the handler runs.
Available via:
- request.state.auth_context (FastAPI routes, via scope["state"])
- get_auth_context FastAPI Depends (route signatures)
- ServerCallContext.state["auth_context"] (A2A, via AdCPCallContextBuilder)

Identity resolution (principal, tenant) happens at handler level via
resolve_identity() — this is intentional to avoid DB calls on every request.
"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Annotated, Any

from fastapi import Depends, Request

# Shared state key for auth context in scope["state"] and ServerCallContext.state.
# All producers/consumers must use this constant instead of a string literal.
AUTH_CONTEXT_STATE_KEY = "auth_context"


@dataclass(frozen=True)
class AuthContext:
    """Immutable per-request auth token + headers carrier.

    Populated by UnifiedAuthMiddleware (extracts token from headers).
    Identity resolution (principal_id, tenant_id) happens downstream
    via resolve_identity() at the handler level.
    """

    auth_token: str | None = None
    headers: MappingProxyType[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        # Wrap mutable dicts passed to __init__ so headers is always immutable.
        if isinstance(self.headers, dict):
            object.__setattr__(self, "headers", MappingProxyType(self.headers))

    @classmethod
    def unauthenticated(cls, *, headers: "dict[str, str] | None" = None) -> "AuthContext":
        """Factory for unauthenticated request context."""
        return cls(headers=MappingProxyType(headers or {}))


def _get_auth_context(request: Request) -> AuthContext:
    """FastAPI dependency that reads AuthContext from request.state.

    The middleware must have already populated request.state.auth_context.
    If middleware hasn't run (e.g., websocket or internal route), returns unauthenticated.
    """
    return getattr(request.state, AUTH_CONTEXT_STATE_KEY, AuthContext.unauthenticated())


# Annotated type aliases for route signatures (modern FastAPI pattern):
#   def my_route(auth_ctx: GetAuthContext):
GetAuthContext = Annotated[AuthContext, Depends(_get_auth_context)]

# Backward-compatible Depends instance (for dependency chaining):
get_auth_context: Any = Depends(_get_auth_context)


# ---------------------------------------------------------------------------
# Identity resolution dependencies (REST routes)
# ---------------------------------------------------------------------------


def _resolve_auth_dep(auth_ctx: AuthContext = get_auth_context) -> "ResolvedIdentity | None":
    """FastAPI dependency: resolve identity (auth-optional, for discovery endpoints).

    Always resolves tenant context from headers (Host / x-adcp-tenant /
    Apx-Incoming-Host), regardless of whether a credential was presented or
    resolved to a principal — matching resolve_identity_from_context()'s
    MCP/A2A contract (transport_helpers.py). Discovery responses describe the
    SELLER, not the caller (AdCP INV-4, v3.1.1), so an ANONYMOUS caller must
    still receive the same tenant-scoped data an authenticated caller would
    (salesagent-zna9). Anonymous, not "sent a token that does not work":
    ``must_validate_credential`` draws that line, so a rejected credential is
    refused AUTH_INVALID here exactly as it already was on MCP and A2A.
    Never raises for a caller who presented NOTHING — identity.principal_id
    being None is how downstream code distinguishes "no credentials" from a
    resolved principal (require_principal_id, brand_manifest_policy checks).
    """
    from src.core.auth_middleware import must_validate_credential
    from src.core.resolved_identity import resolve_identity

    identity = resolve_identity(
        headers=dict(auth_ctx.headers),
        auth_token=auth_ctx.auth_token,
        require_valid_token=must_validate_credential(False, auth_ctx.headers),
        protocol="rest",
    )

    # Set tenant ContextVar at the REST transport boundary
    if identity.tenant:
        from src.core.config_loader import set_current_tenant

        set_current_tenant(identity.tenant)

    return identity


def _require_auth_dep(auth_ctx: AuthContext = get_auth_context) -> "ResolvedIdentity":
    """FastAPI dependency: resolve identity (auth-required, raises 401 if missing).

    Returns ResolvedIdentity on success. Raises AdCPAuthRequiredError if
    no token is present or the token is invalid. The error carries the shared
    AUTH_MISSING suggestion so the REST 401 envelope tells the buyer how to
    recover (parity with require_identity on the _impl path; AdCP POST-F3).
    """
    from src.core.resolved_identity import resolve_identity

    # No presence guard here. resolve_identity raises AdCPAuthRequiredError (AUTH_MISSING)
    # for an absent credential and AdCPAuthenticationError (AUTH_INVALID) for one that is
    # presented and does not resolve, keyed on presence exactly as the v3.1.1 enum is.
    # REST, A2A and MCP each used to answer that question themselves and did not agree; the
    # app's exception handler turns whichever is raised into 401 + WWW-Authenticate.
    identity = resolve_identity(
        headers=dict(auth_ctx.headers),
        auth_token=auth_ctx.auth_token,
        require_valid_token=True,
        protocol="rest",
    )

    # The `not identity.principal_id` backstop that stood here is gone with the guard it
    # backstopped. Its reasoning was right and is preserved where the decision now lives:
    # the spec keys AUTH_MISSING and AUTH_INVALID on whether a credential was PRESENTED, so
    # the two answer different questions and must not be shaped alike. resolve_identity
    # makes both calls on that same signal, and its postcondition — with
    # require_valid_token set it returns a resolved principal or raises — is what makes a
    # backstop here unreachable rather than merely unlikely.

    # Set tenant ContextVar at the REST transport boundary
    if identity.tenant:
        from src.core.config_loader import set_current_tenant

        set_current_tenant(identity.tenant)

    return identity


# Annotated type aliases for route signatures (modern FastAPI pattern):
#   def my_route(identity: ResolveAuth):
#   def my_route(identity: RequireAuth):
# Import at module level for Annotated (cannot be deferred — Annotated
# needs the real type at alias definition time).
from src.core.resolved_identity import ResolvedIdentity  # noqa: E402

#: Where the exception handler looks for the identity this request resolved.
RESOLVED_IDENTITY_STATE_KEY = "resolved_identity"


def _publishing(dep: Any) -> Any:
    """Wrap an identity dependency so the resolved identity reaches the error boundary.

    ``@app.exception_handler`` receives only ``(request, exc)``, so REST's handler used to
    RE-RESOLVE identity from headers just to scope an audit record — a second full lookup,
    principal DB retry included, on a credential that had usually just been rejected. Every
    failed REST auth cost two resolutions where MCP and A2A cost one.

    The identity is published here instead, in the one place that has both the request and
    the resolved identity. Not in the route handler: ``test_no_route_takes_a_raw_request``
    forbids a route touching ``Request`` at all, and rightly — a handler holding the request
    is a handler that can start resolving auth by hand again. A dependency is the layer whose
    job this already is.

    When the wrapped dependency RAISES there is nothing to publish and this never runs, so
    the record is unscoped — the same "unknown" A2A reports on the same path. The boundary
    reports what it resolved and never goes looking for more.
    """

    # Bound before the def, not inline in the parameter list: B008 bans a call in an
    # argument default, and this file already reads defaults from a name for that reason
    # (``auth_ctx: AuthContext = get_auth_context``).
    wrapped: Any = Depends(dep)

    def _publishing_dep(request: Request, identity: Any = wrapped) -> Any:
        setattr(request.state, RESOLVED_IDENTITY_STATE_KEY, identity)
        return identity

    return _publishing_dep


ResolveAuth = Annotated[ResolvedIdentity | None, Depends(_publishing(_resolve_auth_dep))]
RequireAuth = Annotated[ResolvedIdentity, Depends(_publishing(_require_auth_dep))]

# Backward-compatible Depends instances (for dependency chaining):
resolve_auth: Any = Depends(_publishing(_resolve_auth_dep))
require_auth: Any = Depends(_publishing(_require_auth_dep))

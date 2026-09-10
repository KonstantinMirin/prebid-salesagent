"""Shared AuthContext populated by UnifiedAuthMiddleware, consumed by handlers.

UnifiedAuthMiddleware extracts auth_token and headers BEFORE the handler runs.
Available via:
- request.state.auth_context (FastAPI routes, via scope["state"])
- get_auth_context FastAPI Depends (route signatures)
- ServerCallContext.state["auth_context"] (A2A, via AdCPCallContextBuilder)

Identity resolution (principal, tenant) happens at handler level via
resolve_identity() — this is intentional to avoid DB calls on every request.

NEITHER dependency sets the tenant ContextVar, and the removal is deliberate twice over.

It never worked. FastAPI runs a SYNC dependency in an anyio worker thread, the worker gets
a COPY of the context, and a ContextVar written there is discarded on return — measured,
the write lands on "AnyIO worker thread" while the tool's read on "MainThread" raises. MCP
and A2A set the same ContextVar from async handlers on the event loop, where it sticks, so
REST alone was silently anonymous and nobody noticed.

It is deleted rather than repaired because the ambient channel is the wrong carrier. The
tenant already travels explicitly on ``identity.tenant`` — a typed, immutable context that
defers its DB row until a field beyond ``tenant_id`` is read, then caches it once. A
parallel copy of that same value, flattened into a mutable dict and pushed into task-local
state, is a second source of truth for data the callee was already handed, and it is why
this bug was invisible: nothing links such a write to its read. ``require_tenant(identity)``
inside each _impl is the explicit path, and is what has been doing the real work all along.
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


# (Deleted) _resolve_auth_dep / _require_auth_dep / resolve_auth / require_auth / _publishing.
#
# REST resolved identity in a dependency, choosing between two of them by reading
# ToolSpec.auth at the route builder. That was one of the four places the decision lived,
# and the one that hardcoded require_valid_token=False -- so REST alone served a rejected
# credential on a public tool. The boundary resolves now, from the AuthContext the route
# hands it, and a route that cannot resolve cannot disagree.
#
# _publishing went with them: it existed so the REST error path could read the resolved
# identity off request.state, which the boundary now holds directly.

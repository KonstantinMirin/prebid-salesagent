"""Context extraction helpers for MCP tools."""

import logging

from src.core.resolved_identity import ResolvedIdentity
from src.core.tenant_context import LazyTenantContext

logger = logging.getLogger(__name__)


def ensure_tenant_context(identity: ResolvedIdentity | None = None) -> LazyTenantContext:
    """The tenant this identity names, or a typed auth refusal.

    ONE step, where there were four. It used to: read the tenant ContextVar; resolve it from
    a string via the DB if that is what it found; compare the dict it got against the
    identity's tenant_id; and reload from the DB on a mismatch, re-pushing each result back
    into the ContextVar. Every one of those steps existed to REPAIR ambient state -- to cope
    with the ContextVar holding nothing, or a string, or a different tenant than the caller.

    There is no ambient state to repair. ``identity.tenant`` is a LazyTenantContext carrying
    the tenant_id, built at the boundary on every path, hydrating its row at most once on
    first field access. The value the caller was handed IS the answer.

    The refusal keeps its split: nothing presented -> AUTH_MISSING (correctable), something
    presented that did not resolve -> AUTH_INVALID (terminal).
    """
    from src.core.exceptions import AdCPAuthenticationError, AdCPAuthRequiredError

    if identity is not None and identity.tenant is not None:
        return identity.tenant

    if not identity or not identity.auth_token:
        raise AdCPAuthRequiredError()
    raise AdCPAuthenticationError()

"""Where a tenant's agent is reachable — derived from stored state, once.

One function answers it, and everything that publishes or byte-matches an agent URL
reads that one answer. The point is not tidiness: a tenant that answered on several
hosts, or whose scheme was taken from a request header, would publish several
identities, and a counterparty comparing the URL it invoked against the one we
published would fail with no diagnostic.

So the scheme and host come from the tenant row, never from ``Host``,
``Apx-Incoming-Host`` or ``X-Forwarded-Proto``. The ladder over those headers that
used to sit in ``src/app.py`` is gone: it published whatever host the caller asked
for, behind nothing but a syntax check.

Scope. This module is the DERIVATION and nothing else. The agent card reads it
through :mod:`src.services.seller_capabilities`, which is also what
``get_adcp_capabilities`` renders from, so the card and the tool cannot name
different URLs for one seller. The trust-root documents that also build on this
origin — brand.json, adagents.json, the JWKS, and the entry ids addressing them —
belong to the RFC 9421 signing work (#1291) and live on its branch together with the
signing-key repository and migration they need. They are not re-declared here with
no caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import get_settings
from src.core.domain_config import _get_protocol_for_domain, get_sales_agent_domain

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.core.tenant_context import TenantContext

# The paths a counterparty actually reaches this agent at, keyed by transport.
# Values are what the running app resolves to AFTER any redirect it issues —
# ``/mcp`` 307s to ``/mcp/``, ``/a2a`` does not redirect. This table is what stops
# the URL we publish drifting from the mount the app actually serves.
AGENT_ENDPOINT_PATHS: dict[str, str] = {"mcp": "/mcp/", "a2a": "/a2a"}


def _agent_host(tenant: TenantContext) -> str | None:
    """The host this tenant is reachable at, or None when nothing is configured.

    ``virtual_host`` is the tenant's own host (it may carry a port). Otherwise
    the subdomain under the deployment's sales-agent domain. Both are stored
    state, never request state.
    """
    if tenant.virtual_host:
        return tenant.virtual_host
    sales_agent_domain = get_sales_agent_domain()
    if sales_agent_domain and tenant.subdomain:
        return f"{tenant.subdomain}.{sales_agent_domain}"
    return None


def canonical_agent_url(tenant: TenantContext) -> str:
    """The tenant's canonical ORIGIN — scheme + host, no path, no trailing slash.

    An anchor rather than an endpoint: every URL this agent publishes for *tenant* is
    this string plus a path from :data:`AGENT_ENDPOINT_PATHS`.

    Takes the typed read projection the resolver hands on, not the ORM row. This is a
    read, it touches two columns (``virtual_host``, ``subdomain``), and
    ``TenantContext`` carries both — so nothing here opens a session, and a caller
    holding a tenant already has everything it needs.
    """
    host = _agent_host(tenant)
    if host:
        return f"{_get_protocol_for_domain(host)}://{host}"

    # Deployment-level base: single-tenant installs with no per-tenant host. Ranked
    # BELOW the tenant's own host deliberately — a deployment-wide literal that
    # overrode a per-tenant identity would collapse every tenant onto one URL, which
    # is the defect this module exists to remove.
    runtime = get_settings().runtime
    if runtime.adcp_agent_url:
        return runtime.adcp_agent_url.rstrip("/")

    # Development default — the port the sales agent serves on locally.
    return runtime.local_base_url

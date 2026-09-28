"""Where a tenant's agent is reachable — derived from stored state, once.

One function answers it, and everything that publishes or byte-matches an agent URL
reads that one answer. The point is not tidiness: a tenant that answered on several
hosts, or whose scheme was taken from a request header, would publish several
identities, and a counterparty comparing the URL it invoked against the one we
published would fail with no diagnostic.

So the scheme and host come from the tenant row, never from a request header —
not ``Host``, not ``X-Forwarded-Proto``. The ladder over those that used to sit in
``src/app.py`` is gone: it published whatever host the caller asked for, behind
nothing but a syntax check.

Nor is there a ladder UNDER the row any more. A tenant always declares a host —
``Tenant.virtual_host`` refuses a blank and the column refuses NULL — so there is
nothing for a default to answer, and :func:`canonical_agent_url` cannot return a name
the tenant does not live at. The one place a host is still derived is
:func:`deployment_virtual_host`, which runs at CREATION for the tenant a deployment
bootstraps for itself and STORES its answer; see its own note for why that is the
opposite of #1845 rather than a repeat of it.

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

from typing import Protocol
from urllib.parse import urlsplit

from src.core.config import get_settings
from src.core.domain_config import _get_protocol_for_domain

# The paths a counterparty actually reaches this agent at, keyed by transport.
# Values are what the running app resolves to AFTER any redirect it issues —
# ``/mcp`` 307s to ``/mcp/``, ``/a2a`` does not redirect. This table is what stops
# the URL we publish drifting from the mount the app actually serves.
AGENT_ENDPOINT_PATHS: dict[str, str] = {"mcp": "/mcp/", "a2a": "/a2a"}


class DeclaresHost(Protocol):
    """Anything that carries the one column this module reads.

    A tenant reaches this function in two shapes — the ORM row an admin view holds and
    the ``TenantContext`` projection the resolver hands a tool — and both already carry
    the host. Naming the ATTRIBUTE rather than either class is what lets every caller
    pass the row it is already holding instead of re-loading the other shape, which is
    why the four sites that used to derive their own URL can now call this one.
    """

    @property
    def virtual_host(self) -> str: ...


def canonical_agent_url(tenant: DeclaresHost) -> str:
    """The tenant's canonical ORIGIN — scheme + host, no path, no trailing slash.

    An anchor rather than an endpoint: every URL this agent publishes for *tenant* is
    this string plus a path from :data:`AGENT_ENDPOINT_PATHS`.

    ONE source, and no ladder under it: ``virtual_host``, the origin the tenant says it is
    served at (it may carry a port, because the card publishes this string and a client
    connects to what the card says). Stored state, never request state, and never derived.

    Two rungs used to stand below it, and both published a name the tenant did not live
    at. ``f"{subdomain}.{SALES_AGENT_DOMAIN}"`` put ``ci-test.sales-agent.example.com`` on
    the CI tenant's card — nothing on the network served it, and the A2A runner followed it
    and failed every check (#1845). ``local_base_url`` then put ``http://localhost:8080``
    on every admin-created tenant's card as its PUBLIC A2A endpoint. A second derivation of
    "where is this tenant" is a second chance to be wrong about it, and the tenant already
    answers the question — so the column is mandatory (``Tenant.virtual_host`` refuses a
    blank) and this reads it verbatim. This is a read of one column: nothing here opens a
    session.
    """
    return f"{_get_protocol_for_domain(tenant.virtual_host)}://{tenant.virtual_host}"


def deployment_virtual_host() -> str | None:
    """The host a DEPLOYMENT declares itself served at, or None when it declares none.

    For the ONE tenant a deployment bootstraps for itself. Every other tenant is created by
    somebody who knows where it answers and states it; this exists because nobody is present
    at ``init_db`` time to state anything, and the column is mandatory.

    The ladder here is the same one deleted from :func:`canonical_agent_url`, and the
    difference is the whole point: this runs ONCE, at creation, and its answer is STORED in
    a column an operator can see and correct. #1845 re-derived a host at PUBLISH time, for
    tenants that never lived at it, on every request — so no operator ever saw the value
    that was going out.

    Returns None in production declaring neither ``ADCP_AGENT_URL`` nor
    ``SALES_AGENT_DOMAIN``: such an install serves nothing by ``Host`` today, and storing
    ``localhost`` would give it a row that LOOKS configured and still serves nothing. A
    wrong stored host is worse than an absent tenant — it is #1845 one step earlier. The
    bootstraps skip creating the default tenant and log why.
    """
    runtime = get_settings().runtime
    if runtime.adcp_agent_url:
        # The netloc, not the URL: this is a HOST column, and the scheme is re-derived
        # from the host by _get_protocol_for_domain on the way back out.
        return urlsplit(runtime.adcp_agent_url).netloc or None
    if runtime.sales_agent_domain:
        return runtime.sales_agent_domain
    if not runtime.is_production:
        return f"localhost:{runtime.adcp_sales_port}"
    return None

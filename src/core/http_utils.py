"""The host and header facts of an HTTP request, read in one place.

ONE HOST INPUT. ``requested_host`` is the ``Host``, and there is no second spelling of
it. There was: ``Apx-Incoming-Host``, read by a ladder copied into eleven modules, each
spelling the header name itself and each handling case its own way. Those copies did not
agree — ``domain_routing`` let the vendor header win over ``Host`` while
``_detect_tenant`` let ``Host`` win over the vendor header — so one request could resolve
to two different tenants depending on which resolver asked.

The header is now EDGE CONFIG, not application logic. The Approximated proxy serves a
publisher's own domain and forwards to this backend, so the ``Host`` it sends names the
backend identically for every publisher and the publisher's domain arrives in the vendor
header; ``config/nginx/nginx-multi-tenant.conf`` folds it back into ``Host`` and drops it
before anything here runs. Deleting the app-side reader is what makes that fold the only
mechanism rather than one of two, and a deployment serving custom domains needs an edge
that performs it.

**Do not add a reader back.** A helper whose job is to know the vendor header exists
reintroduces the third input the edge just removed. The absence is graded on all four
transports by ``@T-TENANTID-vendor-header-ignored``
(``tests/bdd/features/local-tenant-identification-routes.feature``), which presents the
header over an unserved ``Host`` and requires the refusal.

This module holds no state, imports nothing from the application, and is therefore
importable from the boundary resolver, the admin blueprints, the routes and the routing
module alike.
"""

from collections.abc import Iterable
from typing import Any, Protocol
from urllib.parse import urlsplit


class HeaderSource(Protocol):
    """Anything that can list its headers.

    A plain ``dict``, Flask/werkzeug's ``Headers`` and Starlette's ``Headers`` are all
    passed to these functions, and only the first is a ``Mapping`` — werkzeug's is a
    multi-dict that does not register as one. Listing the pairs is all any function here
    needs, so that is what the parameter asks for.
    """

    def items(self) -> Iterable[tuple[str, Any]]: ...


def get_header_case_insensitive(headers: HeaderSource, header_name: str) -> str | None:
    """Get a header value with case-insensitive lookup.

    HTTP headers are case-insensitive per RFC 7230, but Python dicts are
    case-sensitive. This helper performs case-insensitive header lookup.

    Args:
        headers: Dictionary of headers
        header_name: Header name to look up (compared case-insensitively)

    Returns:
        Header value if found, None otherwise
    """
    if not headers:
        return None

    header_name_lower = header_name.lower()
    for key, value in headers.items():
        if key.lower() == header_name_lower:
            return value
    return None


def requested_host(headers: HeaderSource) -> str | None:
    """The host this request is for: the ``Host``, and nothing else.

    Callers ask for the FACT, not for a header name, which is why this exists at all as a
    one-line function — every reader phrasing it as its own header read is how eleven
    copies came to disagree. What a proxy in front of this app did to produce that ``Host``
    is the edge's business and has no spelling here.
    """
    return get_header_case_insensitive(headers, "Host")


def hostname_of(host: str) -> str:
    """*host* without its port.

    A ``Host`` header carries a port whenever the origin is not on the scheme's default
    (``storyboard.adcp.test:8443``), and both proxies forward it intact. ``virtual_host``
    stores the ORIGIN a tenant is served at, port included, because that is the string the
    agent card has to publish -- a card advertising ``https://storyboard.adcp.test/a2a``
    for an agent listening on 8443 sends every A2A client to a closed port, which is
    exactly what took the A2A conformance axis from 27 passing checks to zero.

    So the port is dropped where a HOSTNAME is what the reader needs, and nowhere else.
    Two readers need one: the tenant routing lookups in ``TenantLookupRepository``, which
    compare host to host so a request naming either form resolves; and
    ``Tenant.primary_domain``, which feeds ``publisher_properties[].publisher_domain`` --
    a field AdCP constrains to ``^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[...])*$``, admitting no
    colon. Feeding the port into that pattern failed every product of such a tenant and
    answered INTERNAL_ERROR for the whole catalogue, which is the defect that first named
    these two jobs.

    Projecting a stored origin onto a hostname is not the defensive re-validation the
    architecture forbids: the column's contents are trusted exactly as stored, and what
    happens here is that one reader wants a different part of the same fact.
    """
    return urlsplit(f"//{host}").hostname or host

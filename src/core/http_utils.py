"""The host and header facts of an HTTP request, read in one place.

Which host a request names was read by a ladder — ``Apx-Incoming-Host`` or its lowercase
spelling, falling back to ``Host`` — copied into eleven modules, each spelling the header
name itself and each handling case its own way. A caller that reads a header name nobody
else reads is a second answer to "which host is this", and the two disagree: the ladder in
``_detect_tenant`` read ``Host`` where ``admin/app.py`` read only the proxy header, and a
request arriving on one but not the other resolved differently depending on which module
saw it first.

So the header NAMES live here and nowhere else, and a caller asks for the fact it wants.
This module holds no state, imports nothing from the application, and is therefore
importable from the boundary resolver, the admin blueprints, the routes and the routing
module alike.
"""

from collections.abc import Iterable
from typing import Any, Protocol
from urllib.parse import urlsplit

#: The Approximated proxy forwards the host the CLIENT asked for under this name; the
#: ``Host`` it sends is the backend's own. Spelled once, here.
APPROXIMATED_HOST_HEADER = "Apx-Incoming-Host"


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


def proxied_host(headers: HeaderSource) -> str | None:
    """The host the client asked for, as the Approximated proxy forwards it.

    ``None`` when the request did not come through that proxy, which is what a caller
    distinguishing "proxied" from "direct" branches on.
    """
    return get_header_case_insensitive(headers, APPROXIMATED_HOST_HEADER)


def requested_host(headers: HeaderSource) -> str | None:
    """The host this request was addressed to: the proxy's spelling, else ``Host``.

    The proxy header wins because when it is present the ``Host`` is the backend's
    internal name, which names no tenant and belongs to no deployment's routing.
    """
    return proxied_host(headers) or get_header_case_insensitive(headers, "Host")


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

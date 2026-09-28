"""The host and header facts of an HTTP request, read in one place.

The host a request names is its ``Host``. ``requested_host`` is that, and it is the only
host input this application has — a caller asks for the FACT rather than naming a header,
which is what keeps one answer to "which host is this request for" across the boundary
resolver, the admin blueprints, the routes and the routing module.

Whatever a proxy in front of this app does to produce that ``Host`` is the edge's business
and has no spelling here.

This module holds no state and imports nothing from the application, so every one of those
callers can import it.
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
    one-line function — a reader phrasing it as its own header read is a copy that can
    disagree with this one. What a proxy in front of this app did to produce that ``Host``
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

    The answer is LOWERCASE -- ``urlsplit(...).hostname`` folds case -- and both callers
    depend on that: ``_same_host`` compares this against a case-folded ``virtual_host``
    column, and ``publisher_domain``'s pinned pattern (``^[a-z0-9]...``) admits no
    uppercase at all. Only this side folding is what took every tenant-routing reader dark
    for a host STORED with uppercase (PR #2191), so the column is folded too.
    ``tests/unit/test_request_host_headers.py`` pins the fold rather than leaving it
    inherited.
    """
    return urlsplit(f"//{host}").hostname or host

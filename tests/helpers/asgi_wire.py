"""A raw-ASGI driver: send a request whose bytes NO client library may normalise.

#1291 B3 (``salesagent-z6nr.14``), design step 5.

WHY THIS EXISTS — do NOT "simplify" it to ``TestClient``/``httpx``. Measured against
a scope-recording app, an httpx-based driver VOIDS eight conformance vectors:

===========================  ==================================================
vector                       what httpx/TestClient does to it
===========================  ==================================================
positive/005 default port    strips ``:443`` from Host before the app sees it
positive/006 dot segment     collapses ``/./`` in the URL
positive/008 pct-encoded     (path decoded to ``☃``; ``raw_path`` kept)
positive/010 ``%2F``         ``path`` becomes a REAL ``/`` — wrong @target-uri
positive/011 IPv6            ``ValueError: invalid literal for int()`` — cannot send
positive/012 IPv6 + :443     same — cannot send
negative/026 non-ASCII host  punycodes ``bücher.`` before send — vector voided
===========================  ==================================================

Five of those are the canonicalization pathologies the vectors exist to grade, so a
client-library driver would report green having graded a normalised request.

THE HARNESS RULE, or ``positive/010`` passes vacuously: this driver sets
``path = unquote(raw_path)``, exactly as uvicorn does. Setting ``path`` to the raw
string instead would hide the production defect that vector 010 is the pin for —
``_verify_url`` builds ``@target-uri`` from ``scope["path"]``, which is percent-DECODED.

This IS the wire for this feature: the verifier's 401 is sent at the ASGI boundary
(``_reject`` -> ``Response(...)(scope, receive, send)``), not through the AdCP envelope
cascade — so ``assert_envelope_shape`` does NOT apply to it. The wire assertion is the
``WWW-Authenticate: Signature error="<code>"`` header, read with
:func:`tests.helpers.signing.rejection_code`.

Header encoding follows ``src.core.http_utils.headers_from_asgi_scope``'s rule
(latin-1), so driver and middleware agree by construction rather than by coincidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass
class WireResponse:
    """What came back off the ASGI boundary. No client library touched it."""

    status_code: int
    #: Preserves REPEATED header lines — a dict would last-win, which is the very
    #: collapse ``negative/022``/``023`` are about.
    raw_headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""

    @property
    def headers(self) -> dict[str, str]:
        """Case-insensitive single-value view, for the checks that want one."""
        return {name.lower(): value for name, value in self.raw_headers}

    def get(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def get_all(self, name: str) -> list[str]:
        return [value for header, value in self.raw_headers if header.lower() == name.lower()]


def build_scope(
    method: str,
    url: str,
    headers: list[tuple[str, str]],
    *,
    app: Any = None,
    root_path: str = "",
) -> dict[str, Any]:
    """Build the ASGI scope a real server would build for *url*, byte-exactly.

    ``headers`` is a LIST of pairs, not a dict: the strict pre-parse gate that
    ``negative/021``/``022``/``023`` grade must be able to see a genuinely REPEATED
    header line, and ``headers_from_asgi_scope`` collapses those (last-wins, not
    joined). A dict here would make those vectors ungradeable in their threat form.
    """
    parts = urlsplit(url)
    scheme = parts.scheme or "http"
    host = parts.hostname or ""
    # ``urlsplit`` strips the brackets off an IPv6 hostname; the ASGI ``server``
    # tuple carries the bare address, while ``Host:`` keeps the bracketed form.
    port = parts.port or _DEFAULT_PORTS.get(scheme, 80)

    raw_path = parts.path.encode("latin-1") or b"/"
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": scheme,
        "path": unquote(raw_path.decode("latin-1")),  # uvicorn's rule, deliberately
        "raw_path": raw_path,
        "root_path": root_path,
        "query_string": parts.query.encode("latin-1"),
        "headers": [(name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in headers],
        "client": ("127.0.0.1", 50000),
        "server": (host, port),
        "state": {},
        "app": app,
    }


async def send_asgi(app: Any, scope: dict[str, Any], body: bytes = b"") -> WireResponse:
    """Drive *app* once with *scope* and collect the response off the boundary."""
    scope.setdefault("app", app)
    received = {"done": False}

    async def receive() -> dict[str, Any]:
        if received["done"]:
            return {"type": "http.disconnect"}
        received["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    response = WireResponse(status_code=0)

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            response.status_code = message["status"]
            response.raw_headers = [
                (name.decode("latin-1"), value.decode("latin-1")) for name, value in message.get("headers", [])
            ]
        elif message["type"] == "http.response.body":
            response.body += message.get("body", b"")

    await app(scope, receive, send)
    return response


def send_wire_request(
    app: Any,
    portal: Any,
    *,
    method: str,
    url: str,
    headers: list[tuple[str, str]],
    body: bytes = b"",
) -> WireResponse:
    """Send one hand-built request through *app* on the lifespan portal's loop.

    The portal is ``TestClient.portal`` from an ENTERED ``TestClient(app)`` context:
    ``src.app.app`` is built with ``lifespan=combine_lifespans(app_lifespan,
    mcp_app.lifespan)`` (``src/app.py:121-125``), so startup must have run, and the
    coroutine must run on the loop startup ran on.
    """
    scope = build_scope(method, url, headers, app=app)
    return portal.call(lambda: send_asgi(app, scope, body))

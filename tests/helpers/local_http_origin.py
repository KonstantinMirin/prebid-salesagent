"""Suite-neutral local HTTP origin: one stdlib server core, two consumers.

Two test suites need a throwaway HTTP server on an ephemeral port:

* ``tests/e2e/_webhook_capture.py`` captures the webhooks the sales agent posts
  back. It binds ``0.0.0.0`` and advertises a *different* callback host, because
  the server runs in a container and must reach the receiver by network alias.
* ``tests/integration/`` drives the outbound egress seam against a real origin
  and needs to program the response (status, redirect, delay, chunked body,
  a per-attempt response sequence, or no response at all) and count exact hits.

Both are the same bootstrap — bind a free port, serve on a daemon thread, hand
back a URL, tear the socket down — so the bootstrap lives here once and the
listen host and the callback host are *parameters*, not forks. No new
dependency: stdlib ``http.server`` only.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, ClassVar

# Default body for a programmable origin that a test never configures.
_DEFAULT_BODY = b'{"ok": true}'


@contextlib.contextmanager
def serve_in_thread(
    handler_class: type[BaseHTTPRequestHandler],
    *,
    listen_host: str = "127.0.0.1",
    server_attrs: dict[str, Any] | None = None,
) -> Iterator[ThreadingHTTPServer]:
    """Serve ``handler_class`` on an ephemeral port of ``listen_host``, in a daemon thread.

    Binds port 0 and reads the kernel-assigned port back off
    ``server.server_address`` rather than probing for a free port and rebinding
    it — the probe-close-rebind form races another xdist worker between the
    close and the rebind.

    ``server_attrs`` are set on the server instance *before* the serving thread
    starts, so a handler may read per-server state (e.g. the programmable
    origin) on its very first request without a data race.
    """
    server = ThreadingHTTPServer((listen_host, 0), handler_class)
    for name, value in (server_attrs or {}).items():
        setattr(server, name, value)

    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@dataclass(frozen=True)
class OriginRequest:
    """One request the origin actually received."""

    method: str
    path: str


@dataclass
class LocalOrigin:
    """Control surface and request log of a running local origin.

    A test programs the next response through one of the ``respond_*`` methods
    and then asserts on :attr:`hits` — the exact number of times the origin was
    reached. Exact hit counts are the whole point: "the redirect was not
    followed" and "a 404 was not retried" are only provable by counting.
    """

    host: str = "127.0.0.1"
    port: int = 0
    requests: list[OriginRequest] = field(default_factory=list)

    # Programmable response state. ``mode`` selects which branch the handler takes.
    mode: str = "fixed"
    status: int = 200
    body: bytes = _DEFAULT_BODY
    content_type: str = "application/json"
    location: str = ""
    delay_seconds: float = 0.0
    total_bytes: int = 0
    chunk_size: int = 64 * 1024
    sequence: list[tuple[int, bytes]] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        """``http://host:port`` — no trailing slash, no scheme choice (plain HTTP only)."""
        return f"http://{self.host}:{self.port}"

    @property
    def hits(self) -> int:
        """Number of requests the origin actually received."""
        return len(self.requests)

    @property
    def paths(self) -> list[str]:
        return [req.path for req in self.requests]

    def respond_with(
        self,
        status: int = 200,
        *,
        body: bytes = _DEFAULT_BODY,
        content_type: str = "application/json",
    ) -> None:
        """Answer every subsequent request with a fixed status and body."""
        self.mode = "fixed"
        self.status = status
        self.body = body
        self.content_type = content_type

    def respond_in_sequence(
        self,
        responses: Sequence[tuple[int, bytes]],
        *,
        content_type: str = "application/json",
    ) -> None:
        """Answer each subsequent request with the next ``(status, body)``; the last entry repeats.

        This is what a real origin needs in order to express *recovery*: ``503,
        503, 200`` is a transient failure that clears on the third attempt, and
        only a queue can say that — a fixed status can say "always fails" or
        "always succeeds" and nothing in between.

        The last entry repeating rather than the queue running dry means a test
        never has to know how many attempts the caller will actually make. It
        programs the recovery point and then asserts on :attr:`hits`, which is
        the number that grades the retry policy.
        """
        if not responses:
            raise ValueError("respond_in_sequence needs at least one response")
        self.mode = "sequence"
        self.sequence = list(responses)
        self.content_type = content_type

    def take_from_sequence(self) -> tuple[int, bytes]:
        """Consume the next programmed response; the final entry repeats forever.

        Consuming the queue rather than indexing it by hit count keeps "the last
        entry repeats" as a single expression and keeps :meth:`reset` honest —
        there is no separate counter that a reset could forget to clear.
        """
        if len(self.sequence) > 1:
            return self.sequence.pop(0)
        return self.sequence[0]

    def close_without_responding(self) -> None:
        """Accept the request, record the hit, then close the connection with no response.

        The hit is recorded first, so the request provably arrived; nothing is
        written after it, so the client sees the socket close before a status
        line and raises a *genuine* transport error of its own making. That is
        the one behaviour a real origin could not express before, and the reason
        ``WebhookMixin.set_http_error`` has to fake it by assigning an exception
        to a mock's ``side_effect`` — a mock can only restate which exception the
        test already chose, never prove the client raises it.
        """
        self.mode = "error"

    def redirect_to(self, location: str, *, status: int = 302) -> None:
        """Answer with a redirect to ``location`` (an arbitrary URL, including a blocked one)."""
        self.mode = "redirect"
        self.status = status
        self.location = location

    def respond_chunked(self, total_bytes: int, *, chunk_size: int = 64 * 1024, status: int = 200) -> None:
        """Answer with ``Transfer-Encoding: chunked`` and ``total_bytes`` of body.

        Chunked rather than a large ``Content-Length``: a body whose size is not
        declared up front is what forces a reader to accumulate and abort, so
        this is the mode that grades a response-size cap honestly.
        """
        self.mode = "chunked"
        self.status = status
        self.total_bytes = total_bytes
        self.chunk_size = chunk_size

    def delay(self, seconds: float) -> None:
        """Stall ``seconds`` before answering, after logging the hit.

        The hit is recorded *before* the stall, so a caller that times out still
        shows up in :attr:`hits` — which is how a per-attempt timeout is graded.
        """
        self.delay_seconds = seconds

    def record(self, method: str, path: str) -> None:
        self.requests.append(OriginRequest(method=method, path=path))

    def reset(self) -> None:
        self.requests.clear()
        self.mode = "fixed"
        self.status = 200
        self.body = _DEFAULT_BODY
        self.content_type = "application/json"
        self.location = ""
        self.delay_seconds = 0.0
        self.total_bytes = 0
        self.sequence.clear()


class ProgrammableOriginHandler(BaseHTTPRequestHandler):
    """Serve whatever ``self.server.origin`` is currently programmed to serve."""

    # HTTP/1.1 is required for Transfer-Encoding: chunked. Every response also
    # carries ``Connection: close`` so each request gets its own connection —
    # that keeps hit counting unambiguous and avoids keep-alive interactions
    # with a client that aborts mid-body.
    protocol_version = "HTTP/1.1"

    def _serve(self) -> None:
        origin: LocalOrigin = self.server.origin  # type: ignore[attr-defined]

        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length:
            self.rfile.read(content_length)

        origin.record(self.command, self.path)

        if origin.delay_seconds:
            time.sleep(origin.delay_seconds)

        try:
            self._SENDERS[origin.mode](self, origin)
        except (BrokenPipeError, ConnectionResetError):
            # The caller aborted — a timeout or a size cap tripping is exactly
            # the behaviour under test, so this is expected, not a failure.
            pass

    def _send_redirect(self, origin: LocalOrigin) -> None:
        self.send_response(origin.status)
        self.send_header("Location", origin.location)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def _send_body(self, status: int, body: bytes, content_type: str) -> None:
        """Write one complete, length-declared response — the shape both fixed and sequence need."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_fixed(self, origin: LocalOrigin) -> None:
        self._send_body(origin.status, origin.body, origin.content_type)

    def _send_sequence(self, origin: LocalOrigin) -> None:
        status, body = origin.take_from_sequence()
        self._send_body(status, body, origin.content_type)

    def _send_nothing(self, origin: LocalOrigin) -> None:
        """Write no bytes at all and close the connection.

        ``close_connection`` ends ``BaseHTTPRequestHandler``'s keep-alive loop,
        after which ``socketserver`` closes the socket. The client has already
        sent a complete request and gets a close instead of a status line, which
        is a real protocol violation on the wire — so the transport error it
        raises is its own, not one a test handed it.
        """
        self.close_connection = True

    def _send_chunked(self, origin: LocalOrigin) -> None:
        self.send_response(origin.status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()

        remaining = origin.total_bytes
        filler = b"x" * origin.chunk_size
        while remaining > 0:
            chunk = filler[: min(origin.chunk_size, remaining)]
            self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
            remaining -= len(chunk)
        self.wfile.write(b"0\r\n\r\n")

    # Mode -> sender. A table rather than an if/elif ladder: adding a mode is
    # one entry, and an unrecognised mode is a KeyError raised at the origin
    # rather than a silent fall-through to "fixed" that would quietly grade the
    # wrong behaviour.
    _SENDERS: ClassVar[dict[str, Callable[[Any, LocalOrigin], None]]] = {
        "fixed": _send_fixed,
        "redirect": _send_redirect,
        "chunked": _send_chunked,
        "sequence": _send_sequence,
        "error": _send_nothing,
    }

    do_GET = _serve
    do_POST = _serve
    do_PUT = _serve
    do_DELETE = _serve

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        """Suppress HTTP server logs during tests."""


@contextlib.contextmanager
def run_local_origin(*, listen_host: str = "127.0.0.1") -> Iterator[LocalOrigin]:
    """Run a programmable local origin and yield its control surface.

    In-process callers only, so the listen host is loopback by default: nothing
    outside this machine should be able to reach a test origin.
    """
    origin = LocalOrigin(host=listen_host)
    with serve_in_thread(
        ProgrammableOriginHandler,
        listen_host=listen_host,
        server_attrs={"origin": origin},
    ) as server:
        origin.port = server.server_address[1]
        yield origin

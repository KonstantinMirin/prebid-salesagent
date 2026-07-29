"""Shared webhook-capture HTTP receiver for e2e tests.

Several e2e suites stand up a throwaway HTTP server to capture the webhooks the
sales agent posts back (delivery reports, A2A status notifications, reference
async notifications). They all need the same bootstrap: bind a free port, serve
on a daemon thread, hand back the callback URL, and tear the socket down
cleanly afterwards. This is the single implementation of that — kept here
instead of copy-pasted per test (PR #1420 / #1423).
"""

import contextlib
import json
import os
import socket
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread


class WebhookCaptureHandler(BaseHTTPRequestHandler):
    """Default capture handler: append each POSTed JSON body to ``received_webhooks``.

    Subclass it and give the subclass its own ``received_webhooks`` list so
    captures don't bleed across suites (``do_POST`` reads ``self.received_webhooks``,
    which resolves to the subclass attribute). Handlers that store more than the
    raw payload (e.g. the a2a status-notification classifier) override
    :meth:`record` — the HTTP framing is never copied.
    """

    received_webhooks: list = []

    #: Every request as the socket delivered it: ``(url, headers, body_bytes)``.
    #: Class-level like ``received_webhooks``, and for the same reason — a subclass
    #: that declares its own list keeps its captures to itself.
    #:
    #: #1291 C1 (``salesagent-z6nr.18``): RFC 9421 verification needs the exact
    #: bytes AND the ``Signature`` / ``Signature-Input`` / ``Content-Digest``
    #: headers, both of which :meth:`record` discards by design (it maps to a
    #: parsed payload). Recording them here rather than adding a parallel receiver
    #: keeps every e2e suite on one server.
    received_raw: list = []

    def record(self, payload):
        """Map an inbound JSON payload to the entry appended to ``received_webhooks``.

        Subclass hook. A raised exception is answered with a 500 and is visible
        to the test via the sender's delivery failure — never swallowed here.
        """
        return payload

    def record_raw(self, url: str, headers, body: bytes) -> None:
        """Append the untouched request to ``received_raw``.

        Runs BEFORE :meth:`record`, so a handler whose ``record`` rejects a
        payload still leaves the raw request available to explain why.
        """
        self.received_raw.append((url, dict(headers.items()), body))

    def do_POST(self):
        """Handle POST requests (webhook notifications)."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            self.record_raw(self.path, self.headers, body)
            self.received_webhooks.append(self.record(json.loads(body.decode("utf-8"))))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "received"}')
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        """Suppress HTTP server logs during tests."""
        pass


@contextlib.contextmanager
def run_webhook_capture_server(
    handler_class: type[BaseHTTPRequestHandler],
    received: list,
    host: str | None = None,
) -> Iterator[dict]:
    """Run a daemon HTTP receiver on a free port and yield its webhook handle.

    ``handler_class`` records inbound POST bodies into ``received`` (a list it
    mutates in place). ``host`` controls the callback hostname: the default
    honors ``ADCP_WEBHOOK_HOST`` so the server reaches this receiver both on the
    host ('localhost', which the server rewrites to host.docker.internal) and
    in-network (the runner's alias 'tests', left un-rewritten). Pass an explicit
    host (e.g. '127.0.0.1') when the receiver is only reachable on loopback.

    Yields ``{"url", "server", "received", "received_raw"}``. Both lists are
    cleared on entry and exit so each test sees only its own captures;
    ``received_raw`` carries ``(path, headers, body_bytes)`` for assertions that
    need the wire rather than the parsed payload (signature verification).
    """
    received.clear()
    raw: list = getattr(handler_class, "received_raw", WebhookCaptureHandler.received_raw)
    raw.clear()

    # Bind 0.0.0.0 (all interfaces), not 127.0.0.1: the in-network runner reaches
    # this receiver by its compose network alias, so a loopback-only bind would be
    # unreachable from the server container. The callback host (below) is what
    # narrows reachability for loopback-only callers, not the listen address.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("0.0.0.0", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = HTTPServer(("0.0.0.0", port), handler_class)
    Thread(target=server.serve_forever, daemon=True).start()

    webhook_host = host if host is not None else os.getenv("ADCP_WEBHOOK_HOST", "localhost")
    try:
        yield {
            "url": f"http://{webhook_host}:{port}/webhook",
            "server": server,
            "received": received,
            "received_raw": raw,
        }
    finally:
        server.shutdown()
        server.server_close()
        received.clear()
        raw.clear()

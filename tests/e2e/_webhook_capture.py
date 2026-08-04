"""Shared webhook-capture HTTP receiver for e2e tests.

Several e2e suites stand up a throwaway HTTP server to capture the webhooks the
sales agent posts back (delivery reports, A2A status notifications, reference
async notifications). They all need the same bootstrap: bind a free port, serve
on a daemon thread, hand back the callback URL, and tear the socket down
cleanly afterwards. This is the single implementation of that — kept here
instead of copy-pasted per test (PR #1420 / #1423).

The bootstrap itself now lives in the suite-neutral
``tests.helpers.local_http_origin``, shared with the integration suite's
programmable local origin. What stays here is genuinely e2e-specific: the
capture semantics, and the ``0.0.0.0`` listen host with a separate callback
host, which a containerised server needs to reach this receiver.
"""

import contextlib
import json
import os
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler

from tests.helpers.local_http_origin import serve_in_thread
from tests.helpers.test_tls_material import load_gen_test_tls, server_ssl_context


class WebhookCaptureHandler(BaseHTTPRequestHandler):
    """Default capture handler: append each POSTed JSON body to ``received_webhooks``.

    Subclass it and give the subclass its own ``received_webhooks`` list so
    captures don't bleed across suites (``do_POST`` reads ``self.received_webhooks``,
    which resolves to the subclass attribute). Handlers that store more than the
    raw payload (e.g. the a2a status-notification classifier) override
    :meth:`record` — the HTTP framing is never copied.
    """

    received_webhooks: list = []

    def record(self, payload):
        """Map an inbound JSON payload to the entry appended to ``received_webhooks``.

        Subclass hook. A raised exception is answered with a 500 and is visible
        to the test via the sender's delivery failure — never swallowed here.
        """
        return payload

    def do_POST(self):
        """Handle POST requests (webhook notifications)."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
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


def _tls_context_for(webhook_host: str):
    """A server-side TLS context for ``webhook_host``, or ``None`` if it can't verify.

    Only a dotted ``*.adcp.test`` name is covered by the generated CA's wildcard
    SAN (``scripts/dev/gen_test_tls.py``) — the default ``host.docker.internal``
    host-run case is not, and gets no cert, so it keeps serving plain http exactly
    as before. The in-network runner registers its callback host as
    ``tests.adcp.test`` (docker-compose.e2e.yml), which is what turns this on:
    the SAME generated leaf every other TLS front in this stack reuses, wrapped
    around this receiver's own ephemeral socket in-process — no separate nginx
    sidecar, because the port is only known once this server has already bound it
    (salesagent-40qh).
    """
    if not webhook_host.endswith(".adcp.test"):
        return None
    gen_test_tls = load_gen_test_tls()
    gen_test_tls.ensure_test_tls()
    return server_ssl_context(gen_test_tls)


@contextlib.contextmanager
def run_webhook_capture_server(
    handler_class: type[BaseHTTPRequestHandler],
    received: list,
    host: str | None = None,
) -> Iterator[dict]:
    """Run a daemon HTTP receiver on a free port and yield its webhook handle.

    ``handler_class`` records inbound POST bodies into ``received`` (a list it
    mutates in place). ``host`` controls the callback hostname: the default
    honors ``ADCP_WEBHOOK_HOST``, falling back to 'host.docker.internal' so a
    dockerized server can reach a host-run receiver regardless of which launcher
    started the stack (test-stack.sh, the CI e2e job's conftest, or manual). The
    in-network runner overrides it to its compose alias 'tests.adcp.test'
    (docker-compose.e2e.yml). The server never rewrites the URL — it delivers
    the registered hostname verbatim. Pass an explicit host (e.g. '127.0.0.1')
    when the receiver is only reachable on loopback.

    Serves https (real TLS, verification ON) when ``webhook_host`` is a dotted
    ``*.adcp.test`` name the generated CA actually covers; plain http otherwise,
    unchanged from before (salesagent-40qh).

    Yields ``{"url", "server", "received"}``. ``received`` is cleared on entry
    and exit so each test sees only its own captures.
    """
    received.clear()

    webhook_host = host if host is not None else os.getenv("ADCP_WEBHOOK_HOST", "host.docker.internal")
    ssl_context = _tls_context_for(webhook_host)
    scheme = "https" if ssl_context is not None else "http"

    # Listen on 0.0.0.0 (all interfaces), not 127.0.0.1: the in-network runner
    # reaches this receiver by its compose network alias, so a loopback-only
    # bind would be unreachable from the server container. The callback host
    # (below) is what narrows reachability for loopback-only callers, not the
    # listen address.
    with serve_in_thread(handler_class, listen_host="0.0.0.0", ssl_context=ssl_context) as server:
        port = server.server_address[1]
        try:
            yield {
                "url": f"{scheme}://{webhook_host}:{port}/webhook",
                "server": server,
                "received": received,
            }
        finally:
            received.clear()

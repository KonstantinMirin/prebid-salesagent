"""The in-process peer creative agent: one per worker process, one catalog per key.

The e2e stack hosts exactly one peer creative agent, the ``webhook-capture`` service,
and a scenario programs it under a key of its own (``POST /control/peer/<key>``). This
is the same service started once in THIS process, over TLS on loopback, so an
in-process scenario's peer and the live server's peer are one implementation addressed
the same way. Each xdist worker is its own process and so gets its own port and store;
keys are minted per call, so two scenarios never read each other's catalog.

Started lazily on first use and shut down at interpreter exit: a server per scenario
would add a TLS listener and a thread per scenario for no isolation the key does not
already give.
"""

from __future__ import annotations

import atexit
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from http.server import ThreadingHTTPServer

_server: ThreadingHTTPServer | None = None


def _shared_peer_agent() -> ThreadingHTTPServer:
    """This process's peer agent, started on first call."""
    global _server
    if _server is None:
        from tests.helpers.tls_material import start_tls_capture_service

        server = start_tls_capture_service()

        def close() -> None:
            server.shutdown()
            server.server_close()

        atexit.register(close)
        _server = server
    return _server


def new_peer_key() -> str:
    """A fresh key: the URL a catalog is served under changes with every catalog."""
    return f"peer-{uuid4().hex}"


def peer_agent_url(key: str) -> str:
    """The agent URL a seller dials for the catalog served under *key*."""
    from tests.e2e.webhook_capture_service import peer_path

    return f"https://127.0.0.1:{_shared_peer_agent().server_address[1]}{peer_path(key)}"


def serve_peer_catalog(key: str, document: dict) -> str:
    """Serve *document* as ``list_creative_formats`` under *key*; return the agent URL a seller dials."""
    _shared_peer_agent().store.serve_peer_catalog(key, document)
    return peer_agent_url(key)

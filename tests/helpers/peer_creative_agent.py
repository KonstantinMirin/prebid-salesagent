"""The in-process peer creative agent: one per worker process, one set of tool answers per key.

The e2e stack hosts exactly one peer creative agent, the ``webhook-capture`` service,
and a scenario programs it under a key of its own (``POST /control/peer/<key>/<tool>``).
This is the same service started once in THIS process, over TLS on loopback, so an
in-process scenario's peer and the live server's peer are one implementation addressed
the same way. Each xdist worker is its own process and so gets its own port and store;
keys are minted per call, so two scenarios never read each other's answers.

Started lazily on first use and shut down at interpreter exit: a server per scenario
would add a TLS listener and a thread per scenario for no isolation the key does not
already give.

The documents a peer serves are built here too, because the service itself is
stdlib-only (it runs on a bare image in the compose stack) and cannot import the SDK
that states their pinned shape.
"""

from __future__ import annotations

import atexit
from typing import TYPE_CHECKING, Any
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
    """The agent URL a seller dials for the peer served under *key*."""
    from tests.e2e.webhook_capture_service import peer_path

    return f"https://127.0.0.1:{_shared_peer_agent().server_address[1]}{peer_path(key)}"


def serve_peer_tool(key: str, tool: str, document: dict) -> str:
    """Serve *document* as the answer to *tool* under *key*; return the agent URL a seller dials."""
    _shared_peer_agent().store.serve_peer_tool(key, tool, document)
    return peer_agent_url(key)


def rehomed_reference_format(format_id: str, agent_url: str) -> dict[str, Any]:
    """The reference capture's *format_id*, published by the agent at *agent_url* as its own.

    The capture's entry, unchanged except for ``format_id.agent_url``: an agent states its
    own URL there for a format it publishes, and a seller dials whatever URL a format's
    identity names. Raises ``ValueError`` for an id the capture does not carry.
    """
    from src.core.format_cache import load_reference_formats

    (fmt,) = [f for f in load_reference_formats() if f.format_id.id == format_id]
    entry = fmt.model_dump(mode="json", exclude_none=True)
    entry["format_id"]["agent_url"] = agent_url
    return entry


def single_preview_document(key: str) -> dict[str, Any]:
    """A ``preview_creative`` answer for the peer under *key*: one variant, one URL render.

    The single-request arm of creative/preview-creative-response.json (AdCP 3.2.7), built
    through the SDK's model of that arm so the document has the pinned shape, the
    protocol envelope's ``status`` included. It names no dimensions, so a seller back-fills
    no width or height from it: one document answers every preview under the key, and a
    size that fitted one format would misstate another.
    """
    from adcp.types import LegacyPreviewCreativeSingleResponse as PreviewCreativeSingleResponse

    return PreviewCreativeSingleResponse.model_validate(
        {
            "response_type": "single",
            "previews": [
                {
                    "preview_id": f"{key}-preview",
                    "renders": [
                        {
                            "render_id": f"{key}-render",
                            "output_format": "url",
                            "preview_url": f"https://preview.example.com/{key}.html",
                            "role": "primary",
                        }
                    ],
                    "input": {"name": "Default"},
                }
            ],
        }
    ).model_dump(mode="json", exclude_none=True)

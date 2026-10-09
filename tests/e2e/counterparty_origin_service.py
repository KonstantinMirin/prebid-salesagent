"""Static counterparty identity origin for the e2e signing suite (salesagent-mp53.8).

The live server's INBOUND verifier resolves an unknown counterparty by WALKING
its published trust root — ``adcp.signing.agent_resolver.async_resolve_agent``:

    POST <agent_url>                    -> MCP ``initialize`` then ``tools/call``
                                           ``get_adcp_capabilities``, whose
                                           ``identity.brand_json_url`` names ...
    GET <brand_json_url>                -> brand.json, whose ``agents[]`` entry
                                           for that url carries ``jwks_uri`` ...
    GET <jwks_uri>                      -> the JWKS the signature is verified against

This service is the other end of that walk. Hop 1 is a PROTOCOL call, not a
document fetch: ``_fetch_capabilities`` (``adcp/signing/agent_resolver.py``:264)
hands its SSRF-pinned client to ``fetch_protocol_capabilities``
(``adcp/signing/_resolver_protocol.py``:290), which for the default
``protocol="mcp"`` opens ``streamablehttp_client``, runs
``ClientSession.initialize()`` and then calls the ``get_adcp_capabilities`` tool.
That is ``security.mdx``:1142 verbatim — "invoke ``get_adcp_capabilities`` via the
agent's declared transport ... **not** a raw HTTP ``GET``" — so the raw-GET hop 1
this fixture was first written against is gone, and with it the SDK divergence
that used to be the reason to work around it. ``do_POST`` below is that hop;
``do_GET`` keeps serving the same document, because the suite's own read-back
reads it that way (``tests/harness/signing_capability.py``).

It is still a SEPARATE origin from the seller, because a counterparty is by
definition not the party under test: the suite has to control these documents one
bit at a time, which is what the agent pair and the slots below are for.

It is a SIBLING of ``tests/e2e/webhook_capture_service.py``, not a mode inside it.
What would be shared is ~30 lines of ``BaseHTTPRequestHandler`` — not the
duplication class worth collapsing — while the coupling would be real: that
service's other mode records raw bytes for the signing suite and its ``do_POST``
semantics must not bleed into an identity origin.

TWO agents on ONE origin, differing ONLY in which brand.json their capabilities
document points at:

* ``/agent/listed``   -> ``/.well-known/brand.json``          (lists it   -> Tier 3 PASSES)
* ``/agent/unlisted`` -> ``/.well-known/brand-unlisted.json`` (omits it   -> Tier 3 REFUSES)

That pair is what makes "resolvable via the PUBLISHED TRUST ROOT" a wire fact
rather than an inference: without the unlisted sibling, a regression that skipped
Tier 3 or routed to the config registry would produce a byte-identical 2xx AND an
identical metric increment. ``AGENT_RESOLUTION_CACHE`` is keyed on agent_url, so
the two cannot collide in the server's cache.

The JWKS is INSTALLED at runtime over ``PUT /_control/jwks`` rather than baked in,
so keys are minted fresh per run by ``keypair_for()`` and no private material is
committed. That control plane is fixture setup — scenery, like a seeded tenant
row — not a seam in anything under test.

Stdlib-only, and deliberately so: it runs on a bare ``python:3.12-slim`` compose
service with no project dependencies. Importing anything under ``tests.helpers``
would run that package's ``__init__``, which transitively pulls in ``factory-boy``.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from collections.abc import Iterator

from tests.e2e._stdlib_json_http import JsonRequestHandler, compose_project_name, serve_forever_in_thread

#: The public origin the SERVER walks. Read from the environment so the compose
#: service, the nginx SNI map and this module cannot drift apart silently: every
#: absolute URL this origin publishes about ITSELF must be the name the server
#: dials, not the container-internal address it happens to bind.
PUBLIC_ORIGIN = os.environ.get("COUNTERPARTY_PUBLIC_ORIGIN", "https://counterparty.adcp-e2e.dev:8443")

LISTED_AGENT_PATH = "/agent/listed"
UNLISTED_AGENT_PATH = "/agent/unlisted"
BRAND_JSON_PATH = "/.well-known/brand.json"
BRAND_UNLISTED_PATH = "/.well-known/brand-unlisted.json"
JWKS_PATH = "/.well-known/jwks.json"
JWKS_CONTROL_PATH = "/_control/jwks"
HEALTH_PATH = "/health"

#: SLOTS — the same listed-agent shape, once per caller instead of once per origin.
#:
#: The two agents above are FIXED documents shared by every consumer, which is
#: right for the accepted/unlisted PAIR (their whole point is that they differ in
#: one bit) and wrong for anyone who needs a key of their own. The server caches a
#: resolved ``AgentResolution`` — JWKS included — per ``agent_url`` for
#: ``SigningSettings.agent_resolution_ttl_seconds`` (an hour by default), in
#: ``src/core/signing/verifier.py``'s ``_resolution_for``, so a SECOND consumer of
#: ``/agent/listed`` does not merely race the first: whichever walks first pins the
#: keyset, and every key published afterwards at that url is invisible to the
#: verifier for the rest of the TTL. A slot gives each caller its own agent url,
#: hence its own cache entry, hence no interference — across xdist workers, across
#: suites, and with the fixed pair above.
#:
#: A slot is an AGENT, never a KEY LOCATION. The server reads a counterparty's keys
#: from ``<agent origin>/.well-known/jwks.json`` and nowhere else
#: (``docs/design/request-signing-subset.md``), and a well-known path is one per
#: ORIGIN — so every slot's brand.json points at that one document and the keysets
#: installed at each slot are served there together, selected by ``kid`` exactly as
#: the SDK selects within any JWKS. What the slot still isolates is what it was for:
#: the agent url, and therefore the cache entry.
SLOT_AGENT_PREFIX = "/agent/slot/"
SLOT_BRAND_PREFIX = "/.well-known/brand-slot/"
SLOT_CONTROL_PREFIX = "/_control/jwks/"

#: The tool hop 1 invokes — ``security.mdx``:1142, and the name
#: ``fetch_protocol_capabilities`` sends verbatim.
CAPABILITIES_TOOL = "get_adcp_capabilities"

#: What the handshake answers with. ``ClientSession.initialize`` offers
#: ``LATEST_HANDSHAKE_VERSION`` and REFUSES a counter-offer outside
#: ``HANDSHAKE_PROTOCOL_VERSIONS`` with a ``RuntimeError``
#: (``mcp/client/session.py``:657, :666), so the answer has to be one of those four
#: revisions; this is the newest, which is what the installed ``mcp`` 2.3.0 offers
#: (``mcp_types/version.py``). The modern ``2026-07-28`` era is reached by
#: ``server/discover`` instead and is never offered here. A LITERAL and not an
#: import, because this module is stdlib-only (see the module docstring) — the
#: constraint that also rules out building these envelopes with ``mcp_types``.
MCP_PROTOCOL_VERSION = "2025-11-25"

#: The header the transport reads a session id out of
#: (``mcp/client/streamable_http.py``:55, :167).
MCP_SESSION_ID_HEADER = "mcp-session-id"

#: One fixed id for the process. This origin keeps no per-session state — every
#: request carries the agent path that decides its answer — so the id exists only
#: because the transport looks for one, and handing out a distinct id per handshake
#: would be bookkeeping nothing reads.
MCP_SESSION_ID = "counterparty-origin"

#: JSON-RPC 2.0 §5.1 codes, for a body or a method this origin will not serve.
_JSONRPC_PARSE_ERROR = -32700
_JSONRPC_INVALID_REQUEST = -32600
_JSONRPC_METHOD_NOT_FOUND = -32601


def slot_agent_url(slot: str) -> str:
    """The absolute ``agent_url`` a caller records on its Principal row."""
    return f"{PUBLIC_ORIGIN}{SLOT_AGENT_PREFIX}{slot}"


def slot_control_path(slot: str) -> str:
    """Where a caller PUTs the keyset this origin serves for *slot*."""
    return f"{SLOT_CONTROL_PREFIX}{slot}"


class _JwksStore:
    """The keysets this origin publishes, installed at runtime and read concurrently.

    Keyed by SLOT for BOOKKEEPING — ``has(slot)`` is how an agent document answers 404
    for a slot nobody installed — while :meth:`published` is the single document every
    walk fetches: the union of every installed keyset, because this origin serves one
    JWKS at one well-known path and callers are told apart by ``kid``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jwks: dict[str, dict] = {"": {"keys": []}}

    def install(self, jwks: dict, slot: str = "") -> None:
        with self._lock:
            self._jwks[slot] = jwks

    def has(self, slot: str) -> bool:
        with self._lock:
            return slot in self._jwks

    def published(self) -> dict:
        """Every installed key, in one keyset.

        A caller's key is visible to any walk that happens after it installed, which is
        the same guarantee the per-slot documents gave: the server's cache pins whatever
        this answers at the moment that agent url is first walked.
        """
        with self._lock:
            return {"keys": [key for jwks in self._jwks.values() for key in jwks.get("keys", [])]}


def _capabilities(brand_json_url: str) -> dict:
    """The capabilities document for one agent.

    ``identity.brand_json_url`` is what hop 1 exists to deliver
    (``_extract_brand_json_url``). Key discovery goes through brand.json — never
    through an ``adagents.json``, which is a different mechanism the resolver
    does not consult here.

    ``identity.key_origins`` is published because a conformant counterparty may, and
    keeping it here is what makes the server's indifference to it observable: it reads
    keys from ``<agent origin>/.well-known/jwks.json`` and consults no map
    (``docs/design/request-signing-subset.md``). A run that started depending on this
    field again would keep passing here and fail against a counterparty that omits it,
    which is the regression the presence of an IGNORED value catches.
    """
    return {
        "adcp_version": "3.1.1",
        "identity": {
            "brand_json_url": brand_json_url,
            "key_origins": {"request_signing": PUBLIC_ORIGIN},
        },
    }


def _agent_brand_json_url(path: str) -> str | None:
    """The brand.json the agent at *path* points at, or ``None`` if *path* is no agent.

    The ONE copy of the agent -> brand.json routing, because hop 1 now reaches these
    documents by two spellings: the MCP ``tools/call`` the SDK's resolver makes, and
    the plain ``GET`` the suite's own read-back does
    (``tests/harness/signing_capability.py``). Which agent was addressed is the only
    thing either spelling needs from the request.
    """
    if path == LISTED_AGENT_PATH:
        return f"{PUBLIC_ORIGIN}{BRAND_JSON_PATH}"
    if path == UNLISTED_AGENT_PATH:
        return f"{PUBLIC_ORIGIN}{BRAND_UNLISTED_PATH}"
    if path.startswith(SLOT_AGENT_PREFIX):
        return f"{PUBLIC_ORIGIN}{SLOT_BRAND_PREFIX}{path[len(SLOT_AGENT_PREFIX) :]}.json"
    return None


def _brand_json(listed_agent_url: str | None) -> dict:
    """A brand.json listing zero or one agent.

    ``jwks_uri`` on the agent entry is what hop 3 fetches, and it is the well-known
    path at this origin for every agent here — the server reads keys from nowhere
    else. When *listed_agent_url* is ``None`` the document is well-formed and simply
    does not list the caller — which is the point of the unlisted sibling: the refusal
    must come from the AUTHORIZATION decision, not from a malformed or missing
    document (those would fail earlier, in a different hop, and prove something
    else).
    """
    agents = []
    if listed_agent_url is not None:
        agents.append({"url": listed_agent_url, "jwks_uri": f"{PUBLIC_ORIGIN}{JWKS_PATH}", "type": "buying"})
    return {"agents": agents}


class _CounterpartyHandler(JsonRequestHandler):
    """Answer hop 1 over MCP, hops 2 and 3 as plain GETs, plus the JWKS control plane."""

    #: Carried by exactly one response — the ``initialize`` result. Held on the handler
    #: rather than passed to ``_write_json`` because that writer owns the framing every
    #: JSON origin here shares and takes no extra headers; teaching the shared module
    #: about an MCP header for one response of one handler is the wrong trade.
    _session_id: str | None = None

    def end_headers(self) -> None:
        """Add the MCP session header, which ``_write_json``'s framing does not know about."""
        if self._session_id is not None:
            self.send_header(MCP_SESSION_ID_HEADER, self._session_id)
            self._session_id = None
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        store: _JwksStore = self.server.jwks_store  # type: ignore[attr-defined]
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        brand_json_url = _agent_brand_json_url(path)

        if brand_json_url is not None:
            if self._wants_event_stream():
                # The streamable-HTTP client opens a SECOND, server->client SSE stream
                # with a GET at this same url, once a handshake hands it a session id
                # (``mcp/client/streamable_http.py``:639 ``start_get_stream`` ->
                # :224 ``handle_get_stream``). Nothing here pushes server-initiated
                # messages, so that stream is declined — and 405 is the one status
                # ``DiscoveryTransport`` passes through on a GET instead of turning into
                # ``capabilities_unreachable`` (``_resolver_protocol.py``:120), which is
                # the SDK saying this is the expected answer from a server without one.
                #
                # Keyed on ``Accept`` and NOT on the method, because the same GET at the
                # same url is how ``tests/harness/signing_capability.py`` reads this
                # document back, and that read must keep getting its 200.
                self._write_json(405, {"error": "this origin pushes no server-initiated MCP messages"})
            elif path.startswith(SLOT_AGENT_PREFIX):
                self._slot_document(store, path[len(SLOT_AGENT_PREFIX) :], _capabilities(brand_json_url))
            else:
                self._write_json(200, _capabilities(brand_json_url))
        elif path == HEALTH_PATH:
            self._write_json(200, {"compose_project_name": self.server.compose_project_name})  # type: ignore[attr-defined]
        elif path == BRAND_JSON_PATH:
            self._write_json(200, _brand_json(f"{PUBLIC_ORIGIN}{LISTED_AGENT_PATH}"))
        elif path == BRAND_UNLISTED_PATH:
            self._write_json(200, _brand_json(None))
        elif path == JWKS_PATH:
            self._write_json(200, store.published())
        elif path.startswith(SLOT_BRAND_PREFIX) and path.endswith(".json"):
            slot = path[len(SLOT_BRAND_PREFIX) : -len(".json")]
            self._slot_document(store, slot, _brand_json(slot_agent_url(slot)))
        else:
            self._write_json(404, {"error": f"no counterparty document at {self.path!r}"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        """Hop 1, as the MCP streamable-HTTP transport performs it.

        adcp 9 moved this hop onto the protocol transport (see the module docstring),
        so where there was one ``GET`` there are now three POSTs at the agent url:
        ``initialize``, the ``notifications/initialized`` that follows it, and
        ``tools/call`` for ``get_adcp_capabilities``. Only the envelope is new — the
        document inside it is the same ``_capabilities(...)`` dict ``do_GET`` serves,
        selected by the same path routing.
        """
        store: _JwksStore = self.server.jwks_store  # type: ignore[attr-defined]
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        brand_json_url = _agent_brand_json_url(path)

        if brand_json_url is None:
            self._write_json(404, {"error": f"no agent to invoke at {self.path!r}"})
            return
        if path.startswith(SLOT_AGENT_PREFIX) and self._refuse_unknown_slot(store, path[len(SLOT_AGENT_PREFIX) :]):
            return

        try:
            message = json.loads(self._read_raw_body() or b"null")
        except json.JSONDecodeError as exc:
            self._write_jsonrpc_error(None, _JSONRPC_PARSE_ERROR, f"request body is not valid JSON: {exc}")
            return
        if not isinstance(message, dict):
            self._write_jsonrpc_error(None, _JSONRPC_INVALID_REQUEST, "request body is not a JSON-RPC object")
            return

        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params")
        tool = params.get("name") if isinstance(params, dict) else None

        if method == "initialize":
            self._session_id = MCP_SESSION_ID
            self._write_jsonrpc_result(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "counterparty-origin", "version": "1.0"},
                },
            )
        elif method == "notifications/initialized":
            self._write_accepted()
        elif method == "tools/call" and tool == CAPABILITIES_TOOL:
            document = _capabilities(brand_json_url)
            # BOTH renderings of the one dict, which is what an MCP server with an output
            # schema emits: ``_extract_strict_mcp_capabilities``
            # (``adcp/signing/_resolver_protocol.py``:59) reads ``structuredContent`` and
            # falls back to parsing a text part, so serving both leaves neither path
            # depending on a shape this fixture happens not to send.
            self._write_jsonrpc_result(
                request_id,
                {"content": [{"type": "text", "text": json.dumps(document)}], "structuredContent": document},
            )
        else:
            self._write_jsonrpc_error(
                request_id,
                _JSONRPC_METHOD_NOT_FOUND,
                f"this origin serves the {CAPABILITIES_TOOL!r} tool and nothing else; got method {method!r}",
            )

    def _wants_event_stream(self) -> bool:
        """Whether the request is asking for an SSE stream rather than a document."""
        return "text/event-stream" in (self.headers.get("Accept") or "")

    def _write_jsonrpc_result(self, request_id: object, result: dict) -> None:
        """A JSON-RPC 2.0 success envelope around *result*."""
        self._write_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})

    def _write_jsonrpc_error(self, request_id: object, code: int, message: str) -> None:
        """A JSON-RPC 2.0 error envelope — at HTTP 200, deliberately.

        ``DiscoveryTransport`` turns any 4xx or 5xx on a POST into
        ``capabilities_unreachable`` before the body is read at all
        (``adcp/signing/_resolver_protocol.py``:120). An HTTP status here would
        therefore report this origin as DOWN, when what happened is that it declined a
        method — a distinction the signing suite spends most of its failure messages
        trying to keep.
        """
        self._write_json(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def _write_accepted(self) -> None:
        """202 with no body, which is how a JSON-RPC notification is answered.

        Bodiless, so ``_write_json`` cannot express it: the transport returns the moment
        it reads the status and never looks at a body
        (``mcp/client/streamable_http.py``:377).
        """
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def _refuse_unknown_slot(self, store: _JwksStore, slot: str) -> bool:
        """Answer 404 and return ``True`` when nothing is installed for *slot*.

        The 404 is where the per-slot JWKS used to answer it, and it is why the check is
        worth keeping: an unknown slot answering a well-formed document would let the walk
        SUCCEED and the signature then fail as an unresolvable keyid — blaming the verifier
        for a caller that never installed anything. Refusing at hop 1 (and hop 2) names the
        slot instead. Both of hop 1's spellings refuse, which is what this being shared by
        ``do_GET`` and ``do_POST`` is for.
        """
        if store.has(slot):
            return False
        self._write_json(404, {"error": f"no keyset installed for slot {slot!r}"})
        return True

    def _slot_document(self, store: _JwksStore, slot: str, document: dict) -> None:
        """Answer one of a slot's two documents, or 404 if nothing is installed for it."""
        if not self._refuse_unknown_slot(store, slot):
            self._write_json(200, document)

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler name
        path = self.path.split("?", 1)[0].rstrip("/")
        slot = ""
        if path.startswith(SLOT_CONTROL_PREFIX):
            slot = path[len(SLOT_CONTROL_PREFIX) :]
        elif path != JWKS_CONTROL_PATH:
            self._write_json(404, {"error": f"no control endpoint at {self.path!r}"})
            return
        raw = self._read_raw_body()
        try:
            jwks = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            # Answering 400 rather than a quiet 200: a test that installed a
            # malformed keyset and got a 200 would fail three assertions later as
            # an unresolvable key, naming the verifier for a fixture's mistake.
            self._write_json(400, {"error": f"JWKS body is not valid JSON: {exc}"})
            return
        store: _JwksStore = self.server.jwks_store  # type: ignore[attr-defined]
        store.install(jwks, slot)
        self._write_json(200, {"installed": len(jwks.get("keys", [])), "slot": slot})


@contextlib.contextmanager
def run_counterparty_origin(*, host: str = "0.0.0.0", port: int = 8080) -> Iterator[str]:
    """Run the counterparty origin, yielding its base URL (``http://host:port``).

    Plaintext by design: TLS is terminated by the shared ``tls-proxy`` front,
    which routes ``counterparty.adcp-e2e.dev`` here by SNI. The origin never holds a
    certificate — one terminator, one leaf, one place to keep in step.
    """
    server = serve_forever_in_thread(
        _CounterpartyHandler,
        host=host,
        port=port,
        server_attrs={"jwks_store": _JwksStore(), "compose_project_name": compose_project_name()},
    )
    try:
        yield f"http://{host}:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    """Entry point for ``python -m tests.e2e.counterparty_origin_service``."""
    port = int(os.environ.get("PORT", "8080"))
    with run_counterparty_origin(host="0.0.0.0", port=port):
        threading.Event().wait()


if __name__ == "__main__":
    main()

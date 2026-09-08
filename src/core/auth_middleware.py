"""Pure ASGI middleware for unified authentication token extraction.

Replaces the fragile 3-middleware chain (auth_context_middleware +
a2a_auth_middleware + ordering dependency) with a single middleware that:
- Extracts token from Authorization: Bearer or x-adcp-auth headers
- Writes to scope["state"] (backs request.state)

This is a pure ASGI class, NOT BaseHTTPMiddleware, avoiding ContextVar
propagation bugs (Starlette issue #1729).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.auth_context import AUTH_CONTEXT_STATE_KEY, AuthContext

logger = logging.getLogger(__name__)

#: The challenge a 401 carries, per code.
#:
#: RFC 6750 §3: a bearer challenge names the scheme and, when a credential WAS presented and
#: rejected, the ``invalid_token`` error code. Both credentials this seller accepts are
#: bearer shaped -- ``Authorization: Bearer`` and the AdCP-conventional ``x-adcp-auth`` -- so
#: ``Bearer`` is the scheme to name. No ``realm``: AdCP defines none for this, and RFC 7235
#: permits a challenge carrying the scheme alone.
#:
#: NOT the ``WWW-Authenticate: Signature error="..."`` family from L1/security.mdx's
#: "Transport error taxonomy" -- that is REQUEST SIGNING, a different mechanism with its own
#: codes. AUTH_MISSING and AUTH_INVALID are ordinary published codes from
#: ``enums/error-code.json`` and travel in the AdCP envelope as usual; what this adds is the
#: HTTP handshake beside it, which is what the storyboard's security_baseline grades.
_CHALLENGE_BY_CODE: Final[dict[str, str]] = {
    "AUTH_MISSING": "Bearer",
    "AUTH_INVALID": 'Bearer error="invalid_token"',
}


def challenge_for_code(code: str | None) -> str | None:
    """The ``WWW-Authenticate`` value for *code*, or None if it is not an auth refusal.

    One owner for "which codes are answered with a 401 challenge", so the three transports
    render the same refusal the same way. Each still emits it through its OWN framework's
    mechanism -- a FastAPI exception handler, the A2A route wrapper, the MCP pre-dispatch
    gate -- because that is the part that legitimately differs; only the decision is shared.
    """
    return _CHALLENGE_BY_CODE.get(code or "")


def credential_present(headers: Mapping[str, str]) -> bool:
    """Whether the caller presented ANY credential this seller accepts.

    Presence only, never validity: validating means a database lookup, and the point of
    asking this at the HTTP layer is to answer an anonymous caller without doing any. The
    same two headers ``UnifiedAuthMiddleware`` extracts, in the same precedence.
    """
    if (headers.get("x-adcp-auth") or "").strip():
        return True
    authorization = (headers.get("authorization") or "").strip()
    return authorization.lower().startswith("bearer ") and bool(authorization[7:].strip())


def _tool_named_by(body: bytes) -> str | None:
    """The tool a JSON-RPC ``tools/call`` body names, or None for anything else.

    Deliberately total: a body that is not JSON, not a ``tools/call``, or missing the name
    yields None and the request proceeds untouched. This gate exists to REFUSE a specific
    thing; anything it cannot positively identify is not its business.
    """
    try:
        message = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(message, dict) or message.get("method") != "tools/call":
        return None
    params = message.get("params")
    name = params.get("name") if isinstance(params, dict) else None
    return name if isinstance(name, str) else None


class McpCredentialGate:
    """Refuse an anonymous call to an auth-required MCP tool, BEFORE dispatch.

    MCP frames a tool failure as a JSON-RPC error inside an HTTP 200, and for an application
    code that is correct. A missing credential is not one: the caller has no identity and
    needs the 401 handshake to discover how to authenticate. The storyboard's
    security_baseline grades exactly that.

    It has to happen BEFORE dispatch, and that is not a preference. For a POST carrying a
    JSON-RPC request, FastMCP's streamable-HTTP transport opens an SSE response and sends
    ``http.response.start`` -- status 200, ``text/event-stream`` -- before handing the
    message to the session (``mcp/server/streamable_http.py``). By the time any tool-level
    code runs, the status is already on the wire. Nothing downstream can change it, and a
    middleware that tried to rewrite it later would silently do nothing.

    So this is the shape the MCP SDK itself uses for auth
    (``mcp.server.auth.middleware.bearer_auth.RequireAuthMiddleware``, and FastMCP's
    equivalent): decide, send your own response, and do not call the app. What this adds is
    that the decision is PER TOOL, because three of ours are ``auth="optional"`` and a
    server-wide gate would wrongly refuse them. The tool name is only knowable from the
    request body, so the body is buffered and replayed -- the standard ASGI way to read a
    request without consuming it.

    PRESENCE ONLY, never validity. Validating means a database lookup, and an anonymous
    caller should not be able to cause one. A credential that IS presented passes through
    here and is judged downstream by ``resolve_identity``, which answers AUTH_INVALID in the
    ordinary envelope. That asymmetry is deliberate and is the one thing this design does
    not give MCP: an invalid token over MCP still returns 200. Fixing that means validating
    pre-dispatch, which contradicts "accuracy belongs downstream" -- flagged rather than
    decided here.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if credential_present(headers):
            # Something was presented. Whether it is any good is not this layer's question.
            await self.app(scope, receive, send)
            return

        buffered: list[Message] = []
        body = b""
        while True:
            message = await receive()
            buffered.append(message)
            if message.get("type") != "http.request":
                break
            body += message.get("body", b"") or b""
            if not message.get("more_body", False):
                break

        tool_name = _tool_named_by(body)
        if tool_name is not None and _tool_requires_credential(tool_name):
            await _send_challenge(send)
            return

        pending = iter(buffered)

        async def replay() -> Message:
            """Hand back the buffered messages, then defer to the real receive."""
            buffered_message = next(pending, None)
            return buffered_message if buffered_message is not None else await receive()

        await self.app(scope, replay, send)


def _tool_requires_credential(tool_name: str) -> bool:
    """Whether the registry says this tool needs a caller.

    ``ToolSpec.auth`` is the authority and the only one -- the same field the MCP tool
    middleware, the A2A skill dispatch and the REST dependency all read. An unknown name is
    NOT treated as requiring auth: it is not this gate's job to answer "no such tool", and
    refusing it here would turn a clear tool error into a confusing 401.
    """
    from src.core.tools.registry import TOOLS

    spec = TOOLS.get(tool_name)
    return spec is not None and spec.auth == "required"


async def _send_challenge(send: Send) -> None:
    """Answer 401 with the AdCP envelope in the body and the challenge in the header.

    The body is the same two-layer envelope every other transport returns for AUTH_MISSING,
    built from the same exception, so a buyer parsing the payload sees no difference between
    transports -- only the HTTP framing differs, which is the part that legitimately does.
    """
    from src.core.exceptions import AdCPAuthRequiredError, build_two_layer_error_envelope

    payload = json.dumps(build_two_layer_error_envelope(AdCPAuthRequiredError())).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                (b"www-authenticate", _CHALLENGE_BY_CODE["AUTH_MISSING"].encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class UnifiedAuthMiddleware:
    """Pure ASGI middleware that extracts auth token and populates AuthContext.

    Sets AuthContext in scope["state"]["auth_context"], which backs
    request.state for FastAPI routes and is read by AdCPCallContextBuilder
    for A2A.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract headers from ASGI scope
        headers: dict[str, str] = {}
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
            headers[name] = value

        # Token extraction: x-adcp-auth takes priority (AdCP convention),
        # then Authorization: Bearer (case-insensitive per RFC 7235 §2.1).
        token: str | None = None
        x_adcp = headers.get("x-adcp-auth", "").strip()
        if x_adcp:
            token = x_adcp
        else:
            auth_header = headers.get("authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                potential = auth_header[7:].strip()
                token = potential or None

        auth_ctx = AuthContext(auth_token=token, headers=MappingProxyType(headers))

        scope.setdefault("state", {})
        scope["state"][AUTH_CONTEXT_STATE_KEY] = auth_ctx

        await self.app(scope, receive, send)

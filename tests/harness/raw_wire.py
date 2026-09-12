"""Raw-wire dispatch: send a document the client cannot shape, and capture what came back.

``AdCPTestClient`` resolves a KNOWN tool name and serializes a keyword BAG. A refusal that
happens before any tool runs -- a body that is not a JSON object, bytes that are not JSON,
a name the registry does not know, an A2A message naming no skill or two -- is exactly what
that client cannot send, because the shape being refused is the shape it builds. This is
the one seam that sends such a document as written. The identity, the REST client, the A2A
handler and the MCP client are the harness's own; only the document is raw.

What comes back is read the way the client reads it. An AdCP body goes through the one
envelope normalizer and lands in ``wire_error_envelope``. A refusal the transport's own
protocol made, with no AdCP body behind it, is ``envelope["status"] ==
DERIVED_STATUS_TRANSPORT_FAULT`` plus that protocol's own verdict beside it: the HTTP
status for REST, the JSON-RPC code for A2A (from the SDK's own class-to-code table in
process, off the body on the wire), the ToolError text for MCP.

MCP has no raw form for a body that is not an object: the MCP protocol types ``arguments``
as an object and the client refuses to send anything else, so the seller never sees that
shape. Such a document raises here as harness wiring, the way ``NoAddressForTransport``
does, rather than becoming a result a scenario could mistake for the seller's answer.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from tests.harness.transport import (
    DERIVED_STATUS_TRANSPORT_FAULT,
    NO_IDENTITY_OVERRIDE,
    Transport,
    TransportResult,
    derive_error_status,
)
from tests.helpers.credentials import identity_credential_headers

#: The A2A JSON-RPC route and the version header it requires, the same two the harness's
#: wire dispatcher sends (``tests/harness/client.py::_deliver_e2e_a2a``).
_A2A_RPC_PATH = "/a2a"
_A2A_VERSION_HEADER = {"A2A-Version": "1.0"}


@dataclass(frozen=True)
class RawDocument:
    """One document to send as written.

    ``tool`` is the name to address -- it need not exist. ``body`` is the REST body (bytes
    are sent verbatim, anything else is JSON-encoded) and the A2A skill ``input``.
    ``a2a_parts``, when given, are the DataPart contents of the A2A message and replace the
    one part ``tool``/``body`` would build, so a message can name no skill or two.
    """

    tool: str
    body: Any = None
    a2a_parts: tuple[dict[str, Any], ...] | None = None


def dispatch_raw(
    env: Any, transport: Transport, document: RawDocument, identity: Any = NO_IDENTITY_OVERRIDE
) -> TransportResult:
    """Send *document* over *transport* and return what the buyer received."""
    try:
        sender = _SENDERS[transport]
    except KeyError:
        raise NotImplementedError(f"raw-wire dispatch has no sender for {transport!r}") from None
    return sender(env, document, identity)


# ── REST ─────────────────────────────────────────────────────────────


def _rest_address(tool: str) -> tuple[str, str]:
    """The registered verb and path for *tool*, or a POST at the name for one the registry lacks."""
    from tests.harness.address_table import ADDRESS_TABLE, NoAddressForTransport

    try:
        address = ADDRESS_TABLE.resolve(tool, Transport.REST)
    except NoAddressForTransport:
        return "post", f"/api/v1/{tool}"
    return address.method or "post", address.path_template or f"/api/v1/{tool}"


def _rest_content(body: Any) -> bytes:
    return body if isinstance(body, bytes) else json.dumps(body).encode()


def _no_payload(_body: dict[str, Any]) -> None:
    """A raw document names no response model to parse a success into."""
    return None


def _rest(env: Any, document: RawDocument, identity: Any) -> TransportResult:
    from tests.harness.client import unwrap_rest_response

    kwargs: dict[str, Any] = {} if identity is NO_IDENTITY_OVERRIDE else {"identity": identity}
    client, resolved = env._prepare_rest_request(kwargs)
    method, path = _rest_address(document.tool)
    headers = {"content-type": "application/json", **env._rest_request_headers(resolved)}
    response = client.request(method, path, content=_rest_content(document.body), headers=headers)
    return unwrap_rest_response(env, response, Transport.REST, parse_response=_no_payload)


def _e2e_rest(env: Any, document: RawDocument, identity: Any) -> TransportResult:
    import httpx

    from tests.harness.client import unwrap_rest_response

    if not env.e2e_config:
        raise RuntimeError("E2E dispatch requires env.e2e_config (pass e2e_config= to env)")
    resolved = env.identity_for(Transport.E2E_REST) if identity is NO_IDENTITY_OVERRIDE else identity
    method, path = _rest_address(document.tool)
    headers = {"content-type": "application/json", **identity_credential_headers(resolved)}
    with httpx.Client(base_url=env.e2e_config.base_url, timeout=30) as client:
        response = client.request(method, path, content=_rest_content(document.body), headers=headers)
    return unwrap_rest_response(env, response, Transport.E2E_REST, parse_response=_no_payload)


# ── A2A ──────────────────────────────────────────────────────────────


def _a2a_message(document: RawDocument) -> Any:
    from a2a.types import Message, Part, Role

    from tests.utils.a2a_helpers import _dict_to_value

    parts = document.a2a_parts
    if parts is None:
        parts = ({"skill": document.tool, "input": {} if document.body is None else document.body},)
    message = Message(message_id=str(uuid4()), role=Role.ROLE_USER)
    for part in parts:
        message.parts.append(Part(data=_dict_to_value(part)))
    return message


def _protocol_refusal(transport: Transport, exc: Exception, **verdict: Any) -> TransportResult:
    """The transport's own refusal: no AdCP body, the protocol's verdict beside the status."""
    return TransportResult(
        has_wire=False,
        error=exc,
        envelope={"transport": transport.value, "status": DERIVED_STATUS_TRANSPORT_FAULT, **verdict},
        wire_error_envelope=None,
    )


def _a2a_task_result(transport: Transport, failed: bool, bodies: list[dict[str, Any]]) -> TransportResult:
    from tests.harness._base import WireError, _wire_envelope

    on_wire = transport is Transport.E2E_A2A
    if failed:
        wire = _wire_envelope(bodies[0]) if bodies else None
        return TransportResult(
            has_wire=False,
            error=WireError(wire) if wire is not None else RuntimeError("A2A task failed with no artifact"),
            envelope={"transport": transport.value, "status": derive_error_status(wire)},
            wire_error_envelope=wire,
        )
    return TransportResult(
        has_wire=on_wire,
        envelope={"transport": transport.value, "status": "completed"},
        wire_response=bodies[0] if bodies else None,
    )


def _a2a(env: Any, document: RawDocument, identity: Any) -> TransportResult:
    from a2a.server.routes.common import ServerCallContext
    from a2a.types import SendMessageRequest, TaskState
    from a2a.utils.errors import JSON_RPC_ERROR_CODE_MAP, A2AError

    from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
    from src.core.auth_context import AUTH_CONTEXT_STATE_KEY, AuthContext
    from tests.utils.a2a_helpers import extract_data_from_artifact

    env._commit_factory_data()
    resolved = env.identity_for(Transport.A2A) if identity is NO_IDENTITY_OVERRIDE else identity
    if env.use_real_db and resolved is not None and resolved.tenant_id:
        env._ensure_tenant_for_audit(resolved.tenant_id)
    token = resolved.auth_token if resolved is not None else None
    if token:
        credential = AuthContext(auth_token=token, headers=identity_credential_headers(resolved, tenant="tenant_id"))
        context = ServerCallContext(state={AUTH_CONTEXT_STATE_KEY: credential})
    else:
        context = ServerCallContext()

    request = SendMessageRequest(message=_a2a_message(document))
    try:
        if resolved is not None and not token:
            # A token-less identity is injected through the resolver seam, as the harness's
            # own A2A leg does; ``identity=None`` means no credential and runs the real chain.
            from tests.helpers.boundary_identity import resolved_as

            with resolved_as(resolved):
                task = asyncio.run(AdCPRequestHandler().on_message_send(request, context))
        else:
            task = asyncio.run(AdCPRequestHandler().on_message_send(request, context))
    except A2AError as exc:
        # The code the JSON-RPC layer would write for this class, read from the SDK's own
        # table rather than restated here.
        return _protocol_refusal(Transport.A2A, exc, jsonrpc_error_code=JSON_RPC_ERROR_CODE_MAP[type(exc)])
    failed = task.status.state == TaskState.TASK_STATE_FAILED
    return _a2a_task_result(Transport.A2A, failed, [extract_data_from_artifact(a) for a in task.artifacts])


def _e2e_a2a(env: Any, document: RawDocument, identity: Any) -> TransportResult:
    import httpx
    from a2a.types.a2a_pb2 import SendMessageRequest
    from google.protobuf import json_format

    from tests.harness._base import _wire_envelope

    if not env.e2e_config:
        raise RuntimeError("E2E dispatch requires env.e2e_config (pass e2e_config= to env)")
    resolved = env.identity_for(Transport.E2E_A2A) if identity is NO_IDENTITY_OVERRIDE else identity
    rpc_body = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "SendMessage",
        "params": json_format.MessageToDict(SendMessageRequest(message=_a2a_message(document))),
    }
    headers = {"Content-Type": "application/json", **_A2A_VERSION_HEADER, **identity_credential_headers(resolved)}
    with httpx.Client(base_url=env.e2e_config.base_url, timeout=30) as client:
        response = client.post(_A2A_RPC_PATH, json=rpc_body, headers=headers)
    rpc = response.json()
    if "error" in rpc:
        error = rpc["error"]
        wire = _wire_envelope(error.get("data")) if isinstance(error.get("data"), dict) else None
        if wire is not None:
            return _a2a_task_result(Transport.E2E_A2A, True, [wire])
        return _protocol_refusal(
            Transport.E2E_A2A, RuntimeError(error.get("message", "")), jsonrpc_error_code=error.get("code")
        )
    result = rpc.get("result") or {}
    task = result.get("task") or result
    failed = (task.get("status") or {}).get("state") == "TASK_STATE_FAILED"
    bodies = [
        part["data"] for artifact in task.get("artifacts", []) for part in artifact.get("parts", []) if "data" in part
    ]
    return _a2a_task_result(Transport.E2E_A2A, failed, bodies)


# ── MCP ──────────────────────────────────────────────────────────────


def _mcp(env: Any, document: RawDocument, identity: Any) -> TransportResult:
    from unittest.mock import patch

    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    from src.core.main import mcp
    from tests.harness._base import WireError, _mcp_wire_envelope

    env._commit_factory_data()
    resolved = env.identity_for(Transport.MCP) if identity is NO_IDENTITY_OVERRIDE else identity
    headers = identity_credential_headers(resolved, tenant="tenant_id")
    arguments = {} if document.body is None else document.body

    async def _call() -> Any:
        with patch("fastmcp.server.dependencies.get_http_headers", return_value=headers):
            async with Client(mcp) as client:
                return await client.call_tool(document.tool, arguments)

    try:
        result = asyncio.run(_call())
    except ToolError as exc:
        wire = _mcp_wire_envelope(exc)
        if wire is not None:
            return TransportResult(
                has_wire=False,
                error=WireError(wire),
                envelope={"transport": Transport.MCP.value, "status": derive_error_status(wire)},
                wire_error_envelope=wire,
            )
        return _protocol_refusal(Transport.MCP, exc, mcp_tool_error=str(exc))
    return TransportResult(
        has_wire=False,
        envelope={"transport": Transport.MCP.value, "status": "completed"},
        wire_response=result.structured_content,
    )


_SENDERS = {
    Transport.REST: _rest,
    Transport.E2E_REST: _e2e_rest,
    Transport.A2A: _a2a,
    Transport.E2E_A2A: _e2e_a2a,
    Transport.MCP: _mcp,
}

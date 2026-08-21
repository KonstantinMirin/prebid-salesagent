"""Transport request -> AdCP operation name: ONE registry, derived from the transports.

#1291 B2 (``salesagent-z6nr.13``), plan steps 1, 3 and 5 as amended by the refinement.

Core invariant
--------------
Every inbound AdCP request is NAMED before a posture decides anything about it —
named in exactly one of the two disjoint namespaces the schema defines (an AdCP
operation with no ``/``, or a JSON-RPC protocol method with one), from ONE registry
derived from the transport registries that already exist, so that no request can
reach the posture as "unnamed, therefore not required".

The two namespaces are mutually exclusive, and that is MANDATORY
--------------------------------------------------------------
:meth:`~src.core.signing.posture.RequestSigningPosture.bucket_for` grades ONLY the
``protocol_methods_*`` trio whenever ``protocol_method`` is not None and IGNORES
``operation``. So an MCP ``tools/call`` resolved into BOTH namespaces — both are true
of the wire — would silently disable ``required_for`` across the entire MCP surface
while looking more informative. Every branch below therefore returns exactly one of
the two, never both.

The consequence to know about: an A2A ``message/send`` WITH an explicit skill returns
``(skill, None)``, so a ``protocol_methods_*`` entry naming ``message/send`` never
fires on explicit-skill calls. Acceptable — the spec's protocol-method table
contemplates only the ``tasks/*`` lifecycle — but D1 (``salesagent-z6nr.20``) should
warn on such a declaration.

Where the name comes from, per surface
--------------------------------------
=========================  =========================================  ======================
Surface                    Field that names it                        Result
=========================  =========================================  ======================
``/api/v1/...``            the route table (method AND path)          ``(operation, None)``
``/mcp`` ``tools/call``    ``params.name``                            ``(name, None)``
``/mcp`` other method      the JSON-RPC ``method``                    ``("", method)``
``/a2a`` ``message/send``  ``params.message.parts[].data.skill``      ``(skill, None)``
``/a2a`` no explicit skill the JSON-RPC ``method``                    ``("", method)``
``/mcp`` or ``/a2a``, no   nothing — a transport session frame        ``("", None)``
body
=========================  =========================================  ======================

REST and A2A carry no ``tools/call``, and security.mdx :1053 read literally ("a
``required_for`` membership MUST NOT be satisfied by a body whose JSON-RPC ``method``
is anything other than ``tools/call``") would therefore bar both — contradicting the
same section's own "this is how cross-transport verifiers agree on what 'signed for
create_media_buy' means", and contradicting compliance vectors 001 and 027, which are
plain ``required_for``-shaped POSTs with no JSON-RPC envelope at all. The sentence
governs which FIELD names the operation when the body IS a JSON-RPC envelope: never
the envelope ``method``. ``params.name`` and ``data.skill`` are such fields.

Fail closed on the unnameable, not on the merely unnamed
--------------------------------------------------------
``resolvable=False`` is reserved for a request on an AdCP surface that carries a body
naming nothing: a non-JSON body, no ``method`` key, a ``tools/call`` with no
``params.name``, or an ``/api/v1`` path matching no route. The middleware promotes
those to the strictest bucket the posture declares. What is NOT unresolvable:

* a JSON-RPC method that names no operation (``initialize``, ``tools/list``) — it is
  named in the protocol namespace, and having no ``/`` it can never legally appear in
  a ``protocol_methods_*`` list, so it lands in supported/none by construction rather
  than by special case. That is what keeps plan step 5 from 401-ing every MCP
  handshake;
* a BODILESS ``/mcp`` or ``/a2a`` request (R-M3) — the streamable-HTTP session frames.
  Tested BEFORE the unresolvable rule, because "no body" trivially satisfies "not
  JSON" and every SSE stream open would otherwise 401 under any ``required_for``.

Classification lives in the guard, not here
-------------------------------------------
MCP tool names and A2A skill ids are IDENTITY with AdCP operation names for our
registrations, so this module emits them verbatim; whether a given name is a real AdCP
operation (``create_media_buy``) or one of ours that is not (``get_task``,
``approve_creative``) is asserted by ``tests/unit/test_architecture_signing_operations.py``
against ``ADCP_TOOL_DEFINITIONS``. Blanking a non-AdCP name here would recreate the
silent-``("", None)`` failure this module exists to remove; a non-AdCP name simply
cannot match a bucket, because the schema forbids one appearing in a declaration.

Spec grounding: AdCP 3.1.1 via ``adcp==6.6.0``;
``v3.1.1:docs/building/by-layer/L1/security.mdx`` :1045-1059 (the two namespaces and
the cross-namespace prohibition), :1375 and :1462-1465 (the webhook-registration
escalation), and compliance vectors 001 / 027 / 028.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol, runtime_checkable

from src.core.http_utils import path_from_asgi_scope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedOperation:
    """What one inbound request is NAMED, plus the two decisions naming it produces.

    ``operation`` and ``protocol_method`` are mutually exclusive (see the module
    docstring): a protocol method is graded against a different trio of buckets and
    takes precedence, so filling both hides the other.
    """

    #: The AdCP operation name, or ``""`` when this request is a protocol method or a
    #: session frame. Never contains ``/``.
    operation: str
    #: The JSON-RPC wire method, or ``None`` when the request names an operation.
    protocol_method: str | None
    #: security.mdx :1462-1465 — the payload registers webhook credentials, so a
    #: signature is mandatory whatever bucket the operation falls in.
    signature_forced: bool = False
    #: False only for a request on an AdCP surface whose body names nothing at all.
    resolvable: bool = True


#: The identity element: an unnamed, nameable request. ``"" in required_for`` is False
#: for every real declaration, so it can never fail closed on a guessed operation.
UNNAMED_OPERATION = ResolvedOperation(operation="", protocol_method=None)


@runtime_checkable
class OperationResolver(Protocol):
    """Names the AdCP operation (and JSON-RPC method) an inbound request invokes."""

    def resolve(self, scope: Mapping[str, Any], headers: Mapping[str, str], body: bytes) -> ResolvedOperation:
        """Return the :class:`ResolvedOperation` for this request.

        ``body`` is the fully-buffered request body: on two of the three transports
        the operation name lives IN the body, and the payload escalation lives there
        on all three. Pure — no I/O, so callers may run it on the event loop.
        """
        ...


class UnresolvedOperationResolver:
    """The inert default: every request is an unnamed operation.

    Kept as the identity element the middleware can be constructed with in a test
    that wants naming out of the picture; production gets
    :class:`RegistryOperationResolver`.
    """

    def resolve(self, scope: Mapping[str, Any], headers: Mapping[str, str], body: bytes) -> ResolvedOperation:
        return UNNAMED_OPERATION


# ---------------------------------------------------------------------------
# The REST leg: derived from the route table, never hand-listed
# ---------------------------------------------------------------------------

#: The only two ``/api/v1`` endpoint functions whose name is not the operation they
#: serve (``src/routes/api_v1.py:252,259`` — one GET and one POST binding of the same
#: AdCP operation). Any further divergence is a rename, and
#: ``tests/unit/test_architecture_signing_operations.py`` fails the build on it rather
#: than letting it resolve to a name no declaration can carry.
_REST_ENDPOINT_ALIASES: dict[str, str] = {
    "get_capabilities": "get_adcp_capabilities",
    "post_capabilities": "get_adcp_capabilities",
}


@lru_cache(maxsize=1)
def _rest_registry() -> tuple[tuple[frozenset[str], re.Pattern[str], str], ...]:
    """``(methods, path regex, operation)`` for every ``/api/v1`` route.

    Derived from ``api_v1.router.routes``, so a new route is named the moment it is
    registered and a renamed one fails the guard instead of silently resolving to
    nothing. The route's OWN ``path_regex`` does the matching — re-implementing path
    templating here is how the two would drift.

    Imported inside the function: this module is imported by the ASGI middleware,
    which ``src/app.py`` registers while the router is still being assembled.
    """
    from src.routes.api_v1 import router

    entries: list[tuple[frozenset[str], re.Pattern[str], str]] = []
    for route in router.routes:
        endpoint = getattr(route, "endpoint", None)
        path_regex = getattr(route, "path_regex", None)
        if endpoint is None or path_regex is None:
            continue
        operation = _REST_ENDPOINT_ALIASES.get(endpoint.__name__, endpoint.__name__)
        entries.append((frozenset(getattr(route, "methods", None) or ()), path_regex, operation))
    return tuple(entries)


def operation_for_rest_route(method: str, path: str) -> str:
    """The AdCP operation a ``/api/v1`` (method, path) pair invokes, or ``""``.

    Public because ``src/routes/rest_compat_middleware.py`` derives its own 3-entry
    gate's VALUES from it (R-M2) — one table, two readers.
    """
    for methods, path_regex, operation in _rest_registry():
        if path_regex.match(path) and (not methods or method in methods):
            return operation
    return ""


# ---------------------------------------------------------------------------
# The JSON-RPC leg: MCP and A2A
# ---------------------------------------------------------------------------

#: The MCP envelope that CARRIES an operation rather than being one.
_TOOL_CALL = "tools/call"

#: The A2A envelopes that carry an explicit skill. ``message/stream`` is the streaming
#: sibling of ``message/send`` and uses the identical part shape.
_MESSAGE_METHODS = frozenset({"message/send", "message/stream"})


def _json_object(body: bytes) -> dict[str, Any] | None:
    """Parse *body* as a JSON object, leniently — for NAMING only.

    Duplicate keys, wrong types and every other malformation are the checklist's to
    reject (security.mdx step 14, ``request_body_malformed``, owned by the SDK). A
    resolver that rejected here would answer the wrong code at the wrong step.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _authenticated_configs(configs: Any) -> bool:
    """Whether any notification config in *configs* carries an ``authentication`` block."""
    candidates = configs if isinstance(configs, list) else [configs]
    return any(isinstance(config, dict) and config.get("authentication") is not None for config in candidates)


def _forces_signature(payload: Any) -> bool:
    """security.mdx :1462-1465 — does this payload register webhook credentials?

    "Sellers that support request signing MUST require the inbound request to be
    9421-signed … when ``authentication`` is present on
    ``push_notification_config.authentication`` or any
    ``accounts[].notification_configs[].authentication``", restated at :1375 as a
    trigger "regardless of ``required_for`` membership".

    BOTH triggers, not just the first: only ``push_notification_config`` has a
    compliance vector, so a resolver handling it alone passes all 40 vectors and is
    still wrong.
    """
    if not isinstance(payload, dict):
        return False
    if _authenticated_configs(payload.get("push_notification_config")):
        return True
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        return False
    return any(
        isinstance(account, dict) and _authenticated_configs(account.get("notification_configs"))
        for account in accounts
    )


def _data_parts(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The ``data`` payloads of an A2A message's data parts.

    Envelope shape: ``params.message.parts[{kind: "data", data: {skill, input}}]``
    (``src/a2a_server/adcp_a2a_server.py:566-583``).
    """
    message = params.get("message")
    if not isinstance(message, dict):
        return []
    parts = message.get("parts")
    if not isinstance(parts, list):
        return []
    return [part["data"] for part in parts if isinstance(part, dict) and isinstance(part.get("data"), dict)]


def _explicit_skill(params: Mapping[str, Any]) -> str:
    """The skill id an A2A ``message/send`` names explicitly, or ``""``.

    Empty for the natural-language invocation path (``adcp_a2a_server.py:607``), which
    is a real production shape and is named as its protocol method instead.
    """
    for data in _data_parts(params):
        skill = data.get("skill")
        if isinstance(skill, str) and skill:
            return skill
    return ""


def _jsonrpc_payload_forces_signature(method: str, params: Mapping[str, Any]) -> bool:
    """Run the escalation test over wherever this transport puts the request payload."""
    if method == _TOOL_CALL:
        return _forces_signature(params.get("arguments"))
    if method in _MESSAGE_METHODS:
        return any(
            _forces_signature(data.get("input")) or _forces_signature(data.get("parameters"))
            for data in _data_parts(params)
        )
    return False


def _resolve_jsonrpc(body: bytes) -> ResolvedOperation:
    """Name an ``/mcp`` or ``/a2a`` request off its JSON-RPC envelope."""
    if not body.strip():
        # R-M3: streamable-HTTP session frames (GET/DELETE ``/mcp``) carry no body.
        # A non-operation BY CONSTRUCTION, decided ahead of the unresolvable test —
        # "no body" trivially satisfies "not JSON", and promoting it would 401 every
        # SSE stream open under any posture declaring required_for.
        return UNNAMED_OPERATION

    envelope = _json_object(body)
    if envelope is None:
        return ResolvedOperation(operation="", protocol_method=None, resolvable=False)

    method = envelope.get("method")
    if not isinstance(method, str) or not method:
        return ResolvedOperation(operation="", protocol_method=None, resolvable=False)

    raw_params = envelope.get("params")
    params: Mapping[str, Any] = raw_params if isinstance(raw_params, dict) else {}
    forced = _jsonrpc_payload_forces_signature(method, params)

    if method == _TOOL_CALL:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return ResolvedOperation(operation="", protocol_method=None, signature_forced=forced, resolvable=False)
        # The tool name is the OPERATION and ``tools/call`` is deliberately dropped:
        # returning it as the protocol method would route the grading to
        # protocol_methods_* and disable required_for on the whole MCP surface.
        return ResolvedOperation(operation=name, protocol_method=None, signature_forced=forced)

    if method in _MESSAGE_METHODS:
        skill = _explicit_skill(params)
        if skill:
            return ResolvedOperation(operation=skill, protocol_method=None, signature_forced=forced)

    return ResolvedOperation(operation="", protocol_method=method, signature_forced=forced)


class RegistryOperationResolver:
    """The production resolver: the REST route table plus the two JSON-RPC envelopes.

    Stateless and pure. The route registry it reads is derived once and cached; every
    other transport's name is identity off the wire, so there is nothing else to
    maintain and nothing that can drift without failing
    ``tests/unit/test_architecture_signing_operations.py``.
    """

    def resolve(self, scope: Mapping[str, Any], headers: Mapping[str, str], body: bytes) -> ResolvedOperation:
        path = path_from_asgi_scope(scope)

        if _on_surface(path, "/mcp") or _on_surface(path, "/a2a"):
            return _resolve_jsonrpc(body)

        if _on_surface(path, "/api/v1"):
            operation = operation_for_rest_route(str(scope.get("method", "GET")).upper(), path)
            forced = _forces_signature(_json_object(body))
            if not operation:
                logger.warning(
                    "No /api/v1 route names %s %s; the request cannot be named and will be "
                    "graded against the strictest bucket this tenant declares",
                    scope.get("method"),
                    path,
                )
                return ResolvedOperation(operation="", protocol_method=None, signature_forced=forced, resolvable=False)
            return ResolvedOperation(operation=operation, protocol_method=None, signature_forced=forced)

        # Not an AdCP surface. The middleware never asks about these (its allowlist
        # runs first), so this is the answer for a direct caller, not a bypass.
        return UNNAMED_OPERATION


def _on_surface(path: str, prefix: str) -> bool:
    """Prefix match on a segment boundary, so ``/api/v1x`` cannot sneak in."""
    return path == prefix or path.startswith(f"{prefix}/")


# ---------------------------------------------------------------------------
# The VOCABULARY: every value ``ResolvedOperation.operation`` can carry
# ---------------------------------------------------------------------------
#
# ``operation`` is a Prometheus LABEL on all three request-signature counters
# (``src/core/metrics.py``), and on two of the three transports its value comes
# VERBATIM out of the request body — ``params.name`` for an MCP ``tools/call``,
# ``data.skill`` for an A2A ``message/send``. The verifier runs ABOVE
# authentication, so recording it raw would let an anonymous
# ``POST /mcp {"method":"tools/call","params":{"name":"<anything>"}}`` mint one new
# time series per request, forever, in a long-running multi-tenant process. The
# label is therefore bounded against the closed set below exactly the way ``code``
# is bounded against the SDK's error taxonomy: anything outside it collapses to
# ``"other"``, so cardinality is a function of the vocabulary and not of the caller.
#
# DERIVED, never hand-listed. A hand-written copy would be a second source of truth
# for the same surface, and it fails the way second copies always fail: silently, on
# the day a tool is added, by demoting that tool's real traffic into the bucket that
# exists to alarm on attacker-supplied names.
# ``tests/unit/test_architecture_signing_operations.py`` drives every registered MCP
# tool, every ``/api/v1`` route and every A2A skill through the sanitizer and fails
# the build if one of them does not survive verbatim.


@lru_cache(maxsize=1)
def sdk_operation_names() -> frozenset[str]:
    """The AdCP operation names the pinned SDK defines.

    A CROSS-CHECK leg, never the authority (module docstring): the SDK list can
    diverge from the spec and is missing two operations we genuinely implement. It
    is in the union so that an operation the SDK knows about is a bounded label the
    moment we start serving it, ahead of any of our own registries naming it.
    """
    from adcp.server.mcp_tools import ADCP_TOOL_DEFINITIONS

    return frozenset(definition["name"] for definition in ADCP_TOOL_DEFINITIONS)


@lru_cache(maxsize=1)
def resolved_operation_names() -> frozenset[str]:
    """Every value :attr:`ResolvedOperation.operation` can carry, derived.

    The union of the four registries this resolver names requests from — the SDK's
    definitions, the ``_register_tool`` list in ``src/core/main.py``, the
    ``/api/v1`` route table and the A2A skill dispatch table — plus
    :data:`UNNAMED_OPERATION`'s ``""``, which the table in the module docstring
    gives a request named in the PROTOCOL namespace or carrying no body at all.
    ``""`` is ONE series and is deliberately kept distinct: folding it into
    ``"other"`` would bury every MCP handshake in the bucket whose whole job is to
    make an attacker-supplied name visible.

    The imports are inside the function for the reason ``_rest_registry`` gives:
    this module is imported by the ASGI middleware, which ``src/app.py`` registers
    while the transports are still being assembled. Cached — all four registries are
    fixed once the process has finished importing, and the first call is at request
    time.
    """
    from src.a2a_server.adcp_a2a_server import SKILL_HANDLERS
    from src.core.main import MCP_TOOL_NAMES

    return (
        frozenset({UNNAMED_OPERATION.operation})
        | sdk_operation_names()
        | frozenset(MCP_TOOL_NAMES)
        | frozenset(SKILL_HANDLERS)
        | frozenset(operation for _methods, _regex, operation in _rest_registry())
    )

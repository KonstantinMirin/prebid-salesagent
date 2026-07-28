"""Structural guards for salesagent-z6nr.13 (#1291 B2) — the transport →
AdCP operation map, and the two shapes that keep it honest.

B2's deliverable is a MAP, and a map's failure mode is silent. ``bucket_for("",
None)`` grades as ``none`` (``src/core/signing/posture.py:95-104``), so a
surface the resolver cannot name does not error — it QUIETLY BECOMES
UNVERIFIED. That is the same inverted failure mode B1's surface allowlist had
one layer up, and it has the same fix: derive the classification from the
production registries and fail ``make quality`` when something new is
unclassified.

There are four transport-local name registries in this tree and none of them
is the AdCP operation list:

* MCP — the 16 ``_register_tool(fn)`` calls in ``src/core/main.py``, where the
  wire tool name is ``fn.__name__``;
* REST — the 13 routes on ``src.routes.api_v1.router``, where the operation is
  the endpoint function's name and the METHOD discriminates two of them
  (``POST /media-buys`` = ``create_media_buy``, ``PUT /media-buys/{id}`` =
  ``update_media_buy``);
* A2A — ``SKILL_HANDLERS`` plus the AgentCard's ``AgentSkill`` ids, two
  hand-maintained lists that must agree or a rename leaks;
* ``rest_compat_middleware._PATH_TO_TOOL``, a fourth, partial REST path → tool
  map that must not drift from the route table (R-M2; the full merge is
  salesagent-i12h).

``adcp.server.mcp_tools.ADCP_TOOL_DEFINITIONS`` (63 names, already imported at
``src/core/main.py:349``) is the CROSS-CHECK, never the authority — it is
missing two operations we genuinely implement, and per the source hierarchy an
SDK list can diverge from the spec.

What each guard catches
-----------------------

1. A new MCP tool / REST route / A2A skill that the resolver cannot name →
   silently unverified, no runtime symptom. Fails here instead.
2. A name the resolver emits that is neither a known AdCP operation nor
   explicitly classified as non-AdCP → a non-AdCP string leaking into a
   ``required_for`` comparison, which the schema forbids.
3. An MCP ``tools/call`` resolved into BOTH namespaces → ``bucket_for`` gives
   the protocol method precedence and ignores the operation, silently
   disabling ``required_for`` across the whole MCP surface (R-L).
4. An A2A skill rename → the AgentCard and the dispatch table disagree.
5. ``_PATH_TO_TOOL`` drifting from the route table (R-M2).
6. The unsigned arms of the middleware being handed the RAW receive channel
   after the reorder drained it (R-H2). Encoded as "they cannot reach the raw
   channel at all", because a 401 that ignores its receive argument is not
   observable at the wire — the pass-through arm IS, and is graded in
   ``tests/integration/test_request_signature_operations.py``.

Contract the implement atom (salesagent-srpm.15) must satisfy
-------------------------------------------------------------
These names are this file's half of the TDD contract, and they are exactly the
ones the refinement names:

  src.core.signing.operations
    .ResolvedOperation          frozen dataclass — operation, protocol_method,
                                signature_forced, resolvable (plan step 3)
    .RegistryOperationResolver  the production resolver, derived from the four
                                registries above; the default the middleware
                                and ``src/app.py`` get
    .OperationResolver.resolve(scope, headers, body: bytes) -> ResolvedOperation
                                the widened Protocol (R-M1) — the name lives in
                                the BODY on two of three transports

  src.a2a_server.adcp_a2a_server
    .SKILL_HANDLERS             the dispatch table hoisted to module scope
                                (R-M4) — a dict local to ``_handle_explicit_skill``
                                cannot be reconciled with the AgentCard by any test

Covers: salesagent-z6nr.13 (Refinement R-H2, R-M2, R-M4, R-L + the disease scan).
"""

from __future__ import annotations

import ast
import re
from typing import Any

import pytest

from tests.unit._architecture_helpers import REPO_ROOT, parse_module

# --------------------------------------------------------------------------
# Classification allowlists — SHRINK-ONLY, and each entry states its reason
# --------------------------------------------------------------------------

#: Real AdCP operations the pinned SDK's ``ADCP_TOOL_DEFINITIONS`` does not
#: list. They are ours to name and the SDK is only a cross-check, so they are
#: allowlisted rather than renamed. This list may only SHRINK — an SDK bump
#: that adds them removes them from here.
_SDK_MISSING_ADCP_OPERATIONS: dict[str, str] = {
    "list_authorized_properties": "AdCP operation; absent from ADCP_TOOL_DEFINITIONS at adcp==6.6.0",
    "update_performance_index": "AdCP operation; absent from ADCP_TOOL_DEFINITIONS at adcp==6.6.0",
}

#: Surfaces we expose that are NOT AdCP operations. Naming them in a
#: ``required_for`` list would put a non-AdCP string in an AdCP namespace, which
#: the schema forbids — so they are classified here instead of silently
#: resolving to nothing.
_NON_ADCP_OPERATIONS: dict[str, str] = {
    "get_task": "local task-inspection tool; the SDK's lifecycle operation is get_task_status",
    "complete_task": "local task-completion tool, no AdCP counterpart",
    "approve_creative": "A2A-only creative-approval skill, no AdCP counterpart",
    "create_creative": "A2A-only skill superseded by sync_creatives",
    "assign_creative": "A2A-only skill superseded by sync_creatives",
    "get_media_buy_status": "A2A-only convenience skill; AdCP reads status via get_media_buys",
    "optimize_media_buy": "A2A-only optimization skill, no AdCP counterpart",
}

#: The two REST endpoint functions whose names are not the operation they serve
#: (``src/routes/api_v1.py:252,259``). Both are ``get_adcp_capabilities``.
_REST_ENDPOINT_ALIASES: dict[str, str] = {
    "get_capabilities": "get_adcp_capabilities",
    "post_capabilities": "get_adcp_capabilities",
}

#: A DECLARABLE JSON-RPC protocol method: exactly one ``/``, which is what keeps
#: the two namespaces disjoint as bare strings (security.mdx :1045-1059). Note
#: the wire also carries slash-free methods (``initialize``, ``ping``); those
#: are legal to RESOLVE and impossible to DECLARE, which is what keeps MCP
#: session traffic out of every bucket without a special case.
_PROTOCOL_METHOD_PATTERN = re.compile(r"^[a-z][a-z0-9_]*/[a-z][a-z0-9_]*$")


# --------------------------------------------------------------------------
# The production registries, read from production
# --------------------------------------------------------------------------


def _sdk_operation_names() -> set[str]:
    from adcp.server.mcp_tools import ADCP_TOOL_DEFINITIONS

    return {definition["name"] for definition in ADCP_TOOL_DEFINITIONS}


def _registered_mcp_tools() -> list[str]:
    """Every ``_register_tool(fn)`` call in ``src/core/main.py``.

    Read from the source rather than from ``mcp``'s private tool manager: the
    registration list IS the surface, and an AST read cannot be fooled by
    import-time ordering.
    """
    tree = parse_module(REPO_ROOT / "src" / "core" / "main.py")
    names = [
        call.args[0].id
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_register_tool"
        and call.args
        and isinstance(call.args[0], ast.Name)
    ]
    assert names, "no _register_tool(...) calls found in src/core/main.py — this guard has gone dead"
    return names


def _rest_routes() -> list[tuple[str, str, str]]:
    """``(method, concrete path, expected operation)`` for every /api/v1 route.

    ``route.path`` already carries the router's ``/api/v1`` prefix, and path
    templates are made concrete so the resolver has to match them the way the
    route itself does rather than by string equality.
    """
    from src.routes.api_v1 import router

    routes: list[tuple[str, str, str]] = []
    for route in router.routes:
        endpoint = route.endpoint.__name__
        operation = _REST_ENDPOINT_ALIASES.get(endpoint, endpoint)
        concrete = re.sub(r"\{[^}]+\}", "probe_id", route.path)
        for method in sorted(route.methods or set()):
            if method in ("HEAD", "OPTIONS"):
                continue
            routes.append((method, concrete, operation))
    assert routes, "no /api/v1 routes found — this guard has gone dead"
    return routes


def _a2a_skill_ids() -> list[str]:
    """The A2A skill ids, from the dispatch table once it is importable.

    Falls back to the AgentCard's advertised ids while ``SKILL_HANDLERS`` is
    still a local inside ``_handle_explicit_skill`` (R-M4). The fallback keeps
    the parametrized guards below alive and meaningful before the hoist lands;
    the hoist itself is asserted on its own by
    :meth:`TestA2ASkillListsAgree.test_the_dispatch_table_is_importable_at_module_scope`,
    so nothing here can silently accept the un-hoisted state.
    """
    try:
        from src.a2a_server.adcp_a2a_server import SKILL_HANDLERS
    except ImportError:
        return _agent_card_skill_ids()
    return sorted(SKILL_HANDLERS)


def _agent_card_skill_ids() -> list[str]:
    from src.a2a_server.adcp_a2a_server import create_agent_card

    return sorted(skill.id for skill in create_agent_card().skills)


# --------------------------------------------------------------------------
# Driving the resolver
# --------------------------------------------------------------------------


def _resolve(method: str, path: str, body: bytes = b"") -> Any:
    from src.core.signing.operations import RegistryOperationResolver

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "query_string": b"",
        "headers": [],
    }
    return RegistryOperationResolver().resolve(scope, {}, body)


def _jsonrpc(method: str, params: dict[str, Any]) -> bytes:
    import json

    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()


def _mcp_tool_call(tool: str) -> bytes:
    return _jsonrpc("tools/call", {"name": tool, "arguments": {}})


def _a2a_explicit_skill(skill: str) -> bytes:
    return _jsonrpc(
        "message/send",
        {
            "message": {
                "messageId": "guard-probe",
                "role": "user",
                "parts": [{"kind": "data", "data": {"skill": skill, "input": {}}}],
            }
        },
    )


def _pair(resolved: Any) -> tuple[str, str | None]:
    return (resolved.operation, resolved.protocol_method)


#: JSON-RPC methods that are NOT operation-carrying envelopes. Each names the
#: protocol method and no operation, which is what keeps an MCP handshake out
#: of the fail-closed branch without a special case: ``initialize`` has no
#: ``/``, so it can never legally appear in a ``protocol_methods_*`` list.
_NON_OPERATION_JSONRPC_METHODS = ("tasks/cancel", "tasks/get", "tasks/resubscribe", "initialize", "tools/list")


# --------------------------------------------------------------------------
# The map cannot leave a surface unnamed, and never names one twice
# --------------------------------------------------------------------------


class TestEveryAdcpSurfaceIsNamed:
    """The disease scan's load-bearing half: no surface may resolve to nothing.

    ``("", None)`` is graded as the ``none`` bucket, i.e. UNVERIFIED, with no
    runtime symptom whatsoever. Converting that into a build failure is the
    only signal that will ever exist.

    Each test below drives EVERY entry of one production registry and reports
    every mismatch at once, so a rename shows up as a named diff rather than as
    one failure out of sixteen identical ones.
    """

    def test_every_registered_mcp_tool_resolves_to_its_own_name(self):
        """The MCP wire tool name IS the operation name for our registrations
        (``src/core/main.py:351-378``), so this is identity — and identity is
        exactly what a future rename breaks silently.

        The ``protocol_method is None`` half is R-L: ``bucket_for``
        (``posture.py:97-103``) grades ONLY the ``protocol_methods_*`` trio
        whenever a protocol method is present and IGNORES the operation, so
        returning ``(tool, "tools/call")`` — both, because both are true of the
        wire — would silently disable ``required_for`` across the entire MCP
        surface while looking more informative.
        """
        mismatched = {
            tool: _pair(_resolve("POST", "/mcp", _mcp_tool_call(tool)))
            for tool in _registered_mcp_tools()
            if _pair(_resolve("POST", "/mcp", _mcp_tool_call(tool))) != (tool, None)
        }

        assert mismatched == {}, (
            f"MCP tools whose tools/call does not resolve to (tool_name, None): {mismatched}. "
            "An unnamed tool grades as the none bucket — silently unverified; a tool ALSO named "
            "as the protocol method 'tools/call' routes the grading to protocol_methods_* and "
            "disables required_for on the whole MCP surface."
        )

    def test_every_rest_route_resolves_to_its_operation(self):
        """Derived from ``api_v1.router.routes``: a new route lands here
        unclassified. The METHOD is part of the key — ``/media-buys`` is two
        different operations by verb (``api_v1.py:332,375``) — and REST carries
        no JSON-RPC envelope, so the protocol method is always None.
        """
        mismatched = {
            f"{method} {path}": _pair(_resolve(method, path))
            for method, path, operation in _rest_routes()
            if _pair(_resolve(method, path)) != (operation, None)
        }

        assert mismatched == {}, (
            f"REST routes not resolving to their endpoint's AdCP operation: {mismatched}. "
            "Expected one entry per route from the route table; a path-only map cannot "
            "distinguish POST /media-buys (create_media_buy) from PUT /media-buys/{id} "
            "(update_media_buy)."
        )

    def test_every_a2a_skill_resolves_to_its_own_name(self):
        """A2A skill ids are identity with AdCP operation names, and the name
        comes from ``parts[].data.skill`` — a third field, distinct from both
        the JSON-RPC ``method`` and MCP's ``params.name``.

        Read literally, security.mdx :1053 ("a ``required_for`` membership MUST
        NOT be satisfied by a body whose JSON-RPC method is anything other than
        ``tools/call``") would bar A2A entirely — and REST too, which has no
        JSON-RPC envelope at all, though vectors 001 and 027 are plain
        ``required_for``-shaped POSTs. The sentence governs which FIELD names
        the operation when the body IS a JSON-RPC envelope: never the envelope
        ``method``. ``data.skill`` is such a field.
        """
        mismatched = {
            skill: _pair(_resolve("POST", "/a2a", _a2a_explicit_skill(skill)))
            for skill in _a2a_skill_ids()
            if _pair(_resolve("POST", "/a2a", _a2a_explicit_skill(skill))) != (skill, None)
        }

        assert mismatched == {}, (
            f"A2A skills whose explicit-skill message/send does not resolve to (skill, None): "
            f"{mismatched}. A skill named as the protocol method 'message/send' instead would "
            "put every A2A call in the protocol namespace, where no AdCP operation can be required."
        )

    def test_a_jsonrpc_method_that_names_no_operation_is_still_named(self):
        """The fail-closed rule must not turn MCP handshakes into 401s.

        ``initialize`` and ``tools/list`` name no AdCP operation, but they are
        not UNNAMED: they are protocol methods, graded against
        ``protocol_methods_*``. ``initialize`` has no ``/``, so it can never
        legally appear in one — benign by construction rather than by special
        case, which is what keeps plan step 5's fail-closed rule from 401-ing
        every MCP session.
        """
        mismatched = {
            method: _pair(_resolve("POST", "/mcp", _jsonrpc(method, {})))
            for method in _NON_OPERATION_JSONRPC_METHODS
            if _pair(_resolve("POST", "/mcp", _jsonrpc(method, {}))) != ("", method)
        }

        assert mismatched == {}, (
            f"JSON-RPC methods not named in the protocol namespace alone: {mismatched}. "
            "Each must resolve to ('', method) — naming an operation as well would let it "
            "satisfy required_for, and naming nothing at all would make it unresolvable and "
            "promote every MCP handshake to the strictest declared bucket."
        )


# --------------------------------------------------------------------------
# The two namespaces stay disjoint as bare strings
# --------------------------------------------------------------------------


class TestNamespacesStayDisjoint:
    """AdCP operation names carry no ``/``; protocol methods carry exactly one.

    That shape IS the separation (security.mdx :1045-1059) — the two buckets
    are plain string lists in the same declaration, so nothing but the shape
    keeps ``tasks/cancel`` out of ``required_for``. Asserted on RESOLVER
    OUTPUT, not only on declarations.
    """

    def test_no_emitted_operation_name_contains_a_slash(self):
        emitted = {
            surface: resolved.operation
            for surface, resolved in (
                *((f"mcp:{tool}", _resolve("POST", "/mcp", _mcp_tool_call(tool))) for tool in _registered_mcp_tools()),
                *((f"a2a:{skill}", _resolve("POST", "/a2a", _a2a_explicit_skill(skill))) for skill in _a2a_skill_ids()),
                *((f"{method} {path}", _resolve(method, path)) for method, path, _op in _rest_routes()),
            )
        }
        with_slash = {surface: operation for surface, operation in emitted.items() if "/" in operation}

        assert with_slash == {}, (
            f"emitted AdCP operation names containing '/': {with_slash}. That is the JSON-RPC "
            "protocol-method shape; the two namespaces are matched as bare strings and must not "
            "be able to collide."
        )

    def test_an_emitted_protocol_method_can_never_be_read_as_an_operation(self):
        """The mirror of the test above, and the reason a slash-free protocol
        method is safe rather than a special case.

        A namespaced method (``tasks/cancel``) must be well-formed, because
        that is the only form a ``protocol_methods_*`` declaration can name. A
        slash-free one (``initialize``, ``ping``) is a legal wire method and is
        deliberately UN-declarable — which is exactly what keeps MCP session
        methods out of every bucket. What must never happen either way is a
        protocol method that collides with a real operation name, because the
        two are compared as bare strings.
        """
        emitted = {
            method: _resolve("POST", "/mcp", _jsonrpc(method, {})).protocol_method
            for method in _NON_OPERATION_JSONRPC_METHODS
        }
        malformed = {
            method: value
            for method, value in emitted.items()
            if value and "/" in value and not _PROTOCOL_METHOD_PATTERN.fullmatch(value)
        }
        operations = set(_registered_mcp_tools()) | {op for _m, _p, op in _rest_routes()} | set(_a2a_skill_ids())
        colliding = sorted(value for value in emitted.values() if value in operations)

        assert malformed == {}, (
            f"namespaced protocol methods not matching {_PROTOCOL_METHOD_PATTERN.pattern}: "
            f"{malformed}. Only this shape can appear in a protocol_methods_* declaration."
        )
        assert colliding == [], (
            f"protocol methods that are also AdCP operation names: {colliding}. The two "
            "namespaces are matched as bare strings, so a collision makes one declaration "
            "silently grade the other's traffic."
        )


# --------------------------------------------------------------------------
# Every emitted name is classified
# --------------------------------------------------------------------------


class TestEveryEmittedNameIsClassified:
    """A name the resolver can emit is either a known AdCP operation or is
    explicitly listed as non-AdCP. An unclassified new tool fails the build
    rather than leaking a non-AdCP string into an AdCP namespace.
    """

    def test_no_unclassified_operation_name_can_be_emitted(self):
        emitted = set(_registered_mcp_tools())
        emitted.update(operation for _method, _path, operation in _rest_routes())
        emitted.update(_a2a_skill_ids())

        known = _sdk_operation_names() | set(_SDK_MISSING_ADCP_OPERATIONS) | set(_NON_ADCP_OPERATIONS)
        unclassified = sorted(emitted - known)

        assert unclassified == [], (
            f"operation names the resolver can emit that are neither in the SDK's "
            f"ADCP_TOOL_DEFINITIONS nor classified in this file: {unclassified}. If one is a "
            "real AdCP operation the pinned SDK lacks, add it to _SDK_MISSING_ADCP_OPERATIONS "
            "with the SDK version; if it is not an AdCP operation, add it to "
            "_NON_ADCP_OPERATIONS with the reason. Never leave it unclassified — a non-AdCP "
            "name in a required_for comparison is what the schema forbids."
        )

    def test_the_allowlists_carry_no_dead_entries(self):
        """Shrink-only means the entries must still describe something real."""
        reachable = set(_registered_mcp_tools()) | {op for _m, _p, op in _rest_routes()} | set(_a2a_skill_ids())
        dead = sorted((set(_SDK_MISSING_ADCP_OPERATIONS) | set(_NON_ADCP_OPERATIONS)) - reachable)

        assert dead == [], (
            f"allowlist entries matching no registered MCP tool, REST route or A2A skill: {dead}. "
            "A stale entry hides the fact that the surface moved. (Until the R-M4 hoist lands, "
            "the A2A leg falls back to the 16 AgentCard ids, so the two handler-only skills "
            "create_creative and assign_creative read as dead here — that resolves with the hoist, "
            "not by deleting them.)"
        )

    def test_the_sdk_missing_allowlist_only_holds_names_the_sdk_really_lacks(self):
        """The moment an SDK bump adds them, this list must shrink."""
        redundant = sorted(set(_SDK_MISSING_ADCP_OPERATIONS) & _sdk_operation_names())

        assert redundant == [], (
            f"_SDK_MISSING_ADCP_OPERATIONS entries the pinned SDK now defines: {redundant}. "
            "Remove them — the allowlist may only shrink."
        )


# --------------------------------------------------------------------------
# A2A's two hand-maintained lists (R-M4)
# --------------------------------------------------------------------------


class TestA2ASkillListsAgree:
    """``SKILL_HANDLERS`` and the AgentCard are the two places A2A names a
    skill. If they can drift, a rename leaks into the operation map — which is
    the failure the acceptance bullet "an A2A skill rename never leaks into
    required_for" names.
    """

    def test_the_dispatch_table_is_importable_at_module_scope(self):
        """R-M4 — it is a LOCAL dict inside ``_handle_explicit_skill`` today
        (``src/a2a_server/adcp_a2a_server.py:1498-1525``), so nothing can
        reconcile it with anything. The hoist is a production step.
        """
        from src.a2a_server.adcp_a2a_server import SKILL_HANDLERS

        assert len(SKILL_HANDLERS) >= 16, (
            "SKILL_HANDLERS must be the module-scope A2A dispatch table (18 skills at the time "
            f"of writing); it has {len(SKILL_HANDLERS)} entries"
        )

    def test_every_advertised_skill_has_a_handler(self):
        """An AgentCard skill with no handler is a lie told to every buyer that
        reads the card, and it is also a name the operation map would emit for
        a request that can only fail.
        """
        undispatchable = sorted(set(_agent_card_skill_ids()) - set(_a2a_skill_ids()))

        assert undispatchable == [], (
            f"AgentCard advertises skills with no entry in SKILL_HANDLERS: {undispatchable}. "
            "Either the skill was renamed in one list only, or the card advertises a skill "
            "that cannot be invoked."
        )


# --------------------------------------------------------------------------
# The fourth REST table must not drift (R-M2)
# --------------------------------------------------------------------------


class TestRestCompatTableAgreesWithTheRouteTable:
    """``_PATH_TO_TOOL`` (``src/routes/rest_compat_middleware.py:22-26``) is a
    3-entry POST-only subset of the route table maintained by hand.

    R-M2 keeps the gate (widening it would start normalizing deprecated fields
    on 10 routes that do not get it today — a REST behavior change graded by
    nothing; the full merge is salesagent-i12h) but forbids the DRIFT: each key
    must name the same operation the registry does for that route.
    """

    def test_every_entry_names_the_same_operation_as_the_route_table(self):
        from src.routes.rest_compat_middleware import _PATH_TO_TOOL

        drifted = {}
        for suffix, tool_name in _PATH_TO_TOOL.items():
            resolved = _resolve("POST", f"/api/v1{suffix}")
            if resolved.operation != tool_name:
                drifted[suffix] = (tool_name, resolved.operation)

        assert drifted == {}, (
            f"_PATH_TO_TOOL entries disagreeing with the derived route registry "
            f"{ {suffix: {'rest_compat': pair[0], 'registry': pair[1]} for suffix, pair in drifted.items()} }. "
            "One table, two readers — a drifted entry normalizes the wrong tool's deprecated "
            "fields."
        )


# --------------------------------------------------------------------------
# R-H2 — the unsigned arms cannot reach the raw receive channel
# --------------------------------------------------------------------------

#: The middleware branches that run AFTER the reorder has drained the request
#: body. Each must take the buffered body, so that the only ``receive`` it can
#: forward downstream is the replaying one.
_POST_BUFFER_BRANCHES = ("_handle_unsigned", "_handle_signed")


class TestBufferedReceiveReachesEveryArm:
    """After the reorder every arm runs downstream of a drained receive channel.

    The pass-through arm is graded behaviorally (the handler must still get
    every byte —
    ``tests/integration/test_request_signature_operations.py::TestUnsignedBodyReachesTheHandlerIntact``
    and B1's ``TestNoneBucketCostsNothing``). The 401 arm is NOT observable at
    the wire, because Starlette's ``Response.__call__`` never reads its receive
    argument — so it is pinned by construction instead: a branch that cannot be
    handed the raw channel cannot forward it.
    """

    @staticmethod
    def _method_args(name: str) -> list[str]:
        tree = parse_module(REPO_ROOT / "src" / "core" / "signing" / "request_verifier_middleware.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
                arguments = node.args
                return [arg.arg for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)]
        raise AssertionError(
            f"RequestSignatureMiddleware.{name} no longer exists — this guard has gone dead. If the "
            "branch was renamed or inlined, re-point _POST_BUFFER_BRANCHES at whatever now runs "
            "downstream of the buffer."
        )

    @pytest.mark.parametrize("branch", _POST_BUFFER_BRANCHES)
    def test_the_branch_takes_the_buffered_body_not_a_raw_receive(self, branch):
        """R-H2's omitted half, made unrepresentable rather than remembered."""
        args = self._method_args(branch)

        assert "receive" not in args, (
            f"{branch} still takes a raw `receive`. After the reorder the body has already been "
            "drained, so forwarding that channel hands the downstream app (or the 401's Response) "
            "an exhausted receive — the unsigned request's body is gone. Take the _BufferedBody "
            "and forward `buffered.receive`."
        )
        assert "buffered" in args, (
            f"{branch} must take the already-buffered body (the reorder buffers once, before the "
            f"signed/unsigned split); its parameters are {args}"
        )

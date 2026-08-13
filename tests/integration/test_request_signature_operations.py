"""Integration tests pinning salesagent-z6nr.13 (#1291 B2) — every inbound AdCP
request is NAMED before the posture grades anything about it.

These are TDD-red against HEAD: ``UnresolvedOperationResolver`` names nothing
(``("", None)``), so every declaration below buckets the empty string and the
middleware takes its pass-through arm. What each test encodes is the behavior
the REFINED plan creates (``bd show salesagent-z6nr.13`` → "## Refinement
(atom salesagent-srpm.21, post-review)"), which AMENDS the original
Implementation Plan and wins wherever the two differ.

Nothing in this file names a resolver symbol. The whole contract is graded at
the wire — status plus the ``WWW-Authenticate: Signature error="<code>"`` byte
the SDK writes — so the implement atom is free to shape
``src/core/signing/operations.py`` as the refinement describes without any of
these tests moving. The one exception is deliberate and lives in
``tests/unit/test_architecture_signing_operations.py``: the registry guard has
to call the resolver directly, because "no AdCP surface silently resolves to
nothing" is a property of the MAP, not of any one request.

What is graded here, and why each one exists
--------------------------------------------

**The name per transport (plan step 3, acceptance "same logical call ⇒ same
operation").** MCP ``tools/call`` → ``params.name``; A2A ``message/send`` →
``params.message.parts[].data.skill``; REST → the route table, which needs the
METHOD as well as the path (``POST /media-buys`` = ``create_media_buy`` while
``PUT /media-buys/{id}`` = ``update_media_buy``). Compliance vector 001 is the
REST shape of this.

**The namespace split (spec :1045-1059, vector 028).** An AdCP operation name
(no ``/``) and a JSON-RPC protocol method (one ``/``) are DISJOINT namespaces
matched against different envelope fields. ``tasks/cancel`` arriving as the
JSON-RPC ``method`` is graded against ``protocol_methods_required_for``; the
same string arriving as a ``tools/call`` ``params.name`` must NOT satisfy it.
The reverse direction is R-L and is the sharpest failure available here:
``RequestSigningPosture.bucket_for`` (``src/core/signing/posture.py:97-103``)
IGNORES ``operation`` whenever ``protocol_method`` is not None, so a resolver
that returned both for an MCP ``tools/call`` would silently disable
``required_for`` across the entire MCP surface — a 200 where the spec demands
a 401, invisible on a green suite.
:meth:`TestProtocolMethodNamespace.test_an_mcp_tool_call_is_named_in_the_adcp_namespace`
is what fails in that case.

**Session frames are not unresolvable (R-M3).** Step 5 promotes an
unresolvable request to the strictest declared bucket. A bodiless ``/mcp`` GET
(the streamable-HTTP stream open) satisfies "non-JSON body" by construction,
so without an explicit rule AHEAD of the unresolvable test every SSE stream
open 401s the moment a posture declares ``required_for`` — the exact outage
step 5 claims to prevent. Graded against its sibling: an unparseable POST body
on the same surface DOES fail closed, so neither test can pass vacuously.

**The webhook escalation (spec :1462-1465, vector 027) is exempt from the
composition rule.** B1's unsigned branch rejects only
``bucket == "required" AND not authenticated``. The webhook rule exists
BECAUSE the registering request is normally bearer-authed and an on-path
mutator can inject or strip the ``authentication`` block, so "valid bearer ⇒
don't reject" defeats it entirely. Vector 027 cannot discriminate — its
``test-bearer-token`` resolves to no principal, so it 401s under either
reading — which is why the AUTHENTICATED case is graded here and not left to
B3. Both triggers are graded: ``push_notification_config.authentication`` (the
one with a vector) and ``accounts[].notification_configs[].authentication``
(the one without).

**The unsigned body survives the reorder (R-H2, R-M5).** B2 moves
``_buffer_body`` ahead of the signed/unsigned split, so for the first time an
UNSIGNED request has its body drained by this middleware and replayed. Two
things must stay true and neither did before: the handler receives every byte,
and ``max_signed_body_bytes`` — a cap whose over-cap branch is lossy and whose
only caller today 413s immediately — must neither reject nor truncate unsigned
traffic. Graded on a plain route and on the body-rewriter route, under and
over the cap.

Why these tests are not vacuous
-------------------------------

Every rejection case has a control that must NOT be rejected under the same
declaration — a different operation, the other namespace, the same body minus
the ``authentication`` block, the same request under ``supported: false``. A
resolver that blanket-promoted everything to ``required`` would pass the first
half of this file and fail the second.

The seam is ``declared_posture`` (``tests/helpers/signing.py``), reused rather
than reimplemented: it substitutes the tenant DECLARATION and
lets production's ``bucket_for`` precedence run for real, and (R-H1) it
substitutes ``request_signing_is_declarable`` to True so the resolver is
actually asked to name anything at all.

Covers: salesagent-z6nr.13 (Core Invariant + Refinement R-H1, R-H2, R-M3,
R-M5, R-L).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any
from unittest.mock import patch

import pytest
from adcp.signing import REQUEST_SIGNATURE_REQUIRED

from tests.harness._base import BareIntegrationEnv

# The seams, the shared tenant/surface constants and the shared request builders
# all come from their single home (salesagent-z6nr.14 step 2). What stays below is
# only what this suite alone uses — the per-transport paths and envelopes.
from tests.helpers.signing import (
    BODYLESS_ADCP_PATH,
    REWRITTEN_ADCP_PATH,
    SIGNING_PRINCIPAL_ID,
    SIGNING_TENANT_ID,
    bucketed_declaration,
    counter_total,
    request_headers,
    seed_principal,
)
from tests.helpers.signing import (
    declared_posture as _declared_posture,
)
from tests.helpers.signing import (
    rejection_code as _rejection_code,
)

#: Module-wide, and load-bearing rather than defensive: the reorder's failure
#: mode is a DEADLOCK, not a short body. A replay that yields nothing — the raw
#: ``receive`` forwarded after the buffer drained it, or an over-cap branch that
#: dropped its chunks — leaves the handler awaiting a body that will never
#: arrive while Starlette's test transport awaits a response that will never be
#: sent. Both faults were injected into a reference implementation, and the
#: first one hangs whichever pass-through test runs first, in ANY class here —
#: which is why this is a module mark and not a class one. ``method="thread"``
#: is what makes it terminate: the default signal timeout fires and then the
#: portal's own teardown deadlocks on the same coroutine, so the run hangs
#: anyway. A correct implementation never reaches this.
pytestmark = pytest.mark.timeout(60, method="thread")

#: The MCP and A2A surfaces, as the compliance vectors address them. Both are
#: inside ``ADCP_SURFACE_PREFIXES``, so the verifier decides before either
#: transport's own routing does — which is why these tests do not need the MCP
#: session manager (it only starts under the app lifespan) to be running.
_MCP_PATH = "/mcp"
_A2A_PATH = "/a2a"

#: REST paths whose operation names differ from each other by METHOD alone —
#: the pair that makes "derive from the route table" load-bearing rather than
#: decorative (``src/routes/api_v1.py:332,375``).
_CREATE_MEDIA_BUY_PATH = "/api/v1/media-buys"
_UPDATE_MEDIA_BUY_PATH = "/api/v1/media-buys/mb_signature_probe"

#: The second escalation trigger's surface (``accounts[].notification_configs``).
_SYNC_ACCOUNTS_PATH = "/api/v1/accounts/sync"

#: A webhook registration carrying credentials — the thing security.mdx :1465
#: says a seller supporting request signing MUST NOT accept unsigned.
_WEBHOOK_AUTHENTICATION = {"scheme": "Bearer", "credentials": "webhook-secret-token"}


# --------------------------------------------------------------------------
# Declarations
# --------------------------------------------------------------------------


def _requires_protocol_methods(*methods: str) -> dict[str, Any]:
    """A posture requiring signatures for JSON-RPC *methods* and nothing else.

    The AdCP-operation buckets are declared EMPTY (not absent): a null
    ``supported_for`` means "verify wherever signatures appear"
    (``posture.py:58-74``), and an empty list is what pins the cross-namespace
    prohibition — anything landing in the AdCP namespace must come out
    ``none``.
    """
    return {
        "supported": True,
        "supported_for": [],
        "required_for": [],
        "protocol_methods_supported_for": list(methods),
        "protocol_methods_required_for": list(methods),
    }


def _supported_only() -> dict[str, Any]:
    """``supported: true`` with no operation narrowing — vector 027's shape.

    ``required_for`` is EXPLICITLY empty, so any rejection this posture
    produces came from the payload escalation and not from bucket membership.
    """
    return {"supported": True, "required_for": []}


# --------------------------------------------------------------------------
# Request construction
# --------------------------------------------------------------------------


def _client(env: BareIntegrationEnv) -> Any:
    """A TestClient that reports a downstream crash as a response, not a raise.

    The MCP mount needs the app lifespan to have started its session manager,
    which no in-process TestClient here does. That is irrelevant to what these
    tests grade — the verifier decides before the mount is ever reached — but
    it means an MCP request the verifier PASSES must be observable as "no
    rejection" rather than as an exception. ``raise_server_exceptions=False``
    (the same device ``tests/unit/test_a2a_transport_contract.py:129`` uses)
    is what makes the pass-through arm assertable at all.
    """
    from starlette.testclient import TestClient

    from src.app import app

    env.get_rest_client()  # installs the route-level auth dependency overrides
    return TestClient(app, raise_server_exceptions=False)


def _jsonrpc(method: str, params: dict[str, Any]) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()


def _mcp_tool_call(tool_name: str) -> bytes:
    """An MCP ``tools/call`` envelope — the operation is ``params.name``."""
    return _jsonrpc("tools/call", {"name": tool_name, "arguments": {}})


def _a2a_explicit_skill(skill: str) -> bytes:
    """An A2A ``message/send`` naming a skill explicitly.

    The envelope shape is ``params.message.parts[{kind: "data", data: {skill,
    input}}]`` (``src/a2a_server/adcp_a2a_server.py:566-583``) — a third field,
    distinct from both the JSON-RPC ``method`` and MCP's ``params.name``.
    """
    return _jsonrpc(
        "message/send",
        {
            "message": {
                "messageId": "msg-signature-probe",
                "role": "user",
                "parts": [{"kind": "data", "data": {"skill": skill, "input": {}}}],
            }
        },
    )


def _json_headers(token: str | None) -> dict[str, str]:
    return request_headers(token, {"Content-Type": "application/json"})


# --------------------------------------------------------------------------
# Observation helpers
# --------------------------------------------------------------------------


def _assert_rejected(response: Any, why: str) -> None:
    """The verifier answered the spec's 401 with ``request_signature_required``."""
    assert _rejection_code(response) == REQUEST_SIGNATURE_REQUIRED, (
        f"{why}\nExpected 401 + WWW-Authenticate: Signature "
        f'error="{REQUEST_SIGNATURE_REQUIRED}"; got status {response.status_code} with '
        f"WWW-Authenticate={response.headers.get('WWW-Authenticate')!r}"
    )


@contextmanager
def _assert_verifier_looked() -> Iterator[None]:
    """The middleware ACTUALLY RAN and reached a verdict for an unsigned request.

    Wraps the request. Absence-of-rejection alone is worthless as an acceptance
    signal — it is byte-identical to a middleware that never looked, which is true
    whenever the verifier is disabled, the operation is in the ``none`` bucket, or
    the posture is ``warn`` (salesagent-z6nr.40). So the control cases assert a
    POSITIVE observable instead: production increments
    ``adcp_request_unsigned_total`` from ``record_request_unsigned`` on exactly the
    path that decides an unsigned request may proceed. A middleware that returned
    early emits nothing, and the delta is zero.

    Reads the counter through ``counter_total`` (tests/helpers/signing.py) rather
    than hand-rolling a before/after pair — that idiom was open-coded at eight
    sites across three modules, and a ninth would make it worse.
    """
    before = counter_total("adcp_request_unsigned_total")
    yield
    after = counter_total("adcp_request_unsigned_total")
    assert after > before, (
        "the verifier never recorded a verdict for this request: "
        f"adcp_request_unsigned_total did not move ({before} -> {after}). A 2xx with no rejection is "
        "equally true of a middleware that returned early — disabled verifier, 'none' bucket, or 'warn' "
        "posture — so this control proves nothing without the counter."
    )


def _assert_not_rejected(response: Any, why: str) -> None:
    """The verifier did not reject — whatever the transport answered afterwards.

    Deliberately blind to the downstream status: these are the CONTROL cases,
    and what they grade is that the signature verifier let the request past.

    Pair this with :func:`_assert_verifier_looked` around the request itself. On
    its own it only rules out a rejection; it cannot distinguish "the verifier
    considered this and allowed it" from "the verifier never ran".
    """
    assert _rejection_code(response) is None, (
        f"{why}\nThe verifier rejected it: status {response.status_code}, "
        f"WWW-Authenticate={response.headers.get('WWW-Authenticate')!r}"
    )


@contextmanager
def _body_cap(max_bytes: int) -> Iterator[None]:
    """Shrink ``max_signed_body_bytes`` for the duration of one request.

    The production default is 10 MiB (``src/core/config.py:171``); shrinking it
    is what makes the over-cap path testable in milliseconds instead of by
    posting ten megabytes. The whole config object is copied, so nothing else
    the middleware reads changes.
    """
    from src.core.signing import request_verifier_middleware as mw

    config = mw.get_config()
    capped = config.model_copy(
        update={"signing": config.signing.model_copy(update={"max_signed_body_bytes": max_bytes})}
    )
    with patch.object(mw, "get_config", lambda: capped):
        yield


@contextmanager
def _rest_compat_spy() -> Iterator[list[dict[str, Any]]]:
    """Record the body ``RestCompatMiddleware`` parsed, delegating to the real one.

    ``normalize_request_params`` is handed ``json.loads(await request.body())``
    from INSIDE the verifier (``src/routes/rest_compat_middleware.py:57-61``),
    i.e. off the replaying ``receive`` the verifier installed. So the recorded
    dict is direct evidence of what a downstream body reader actually got —
    which is the exposure the reorder creates and the reason R-M5 asks for the
    rewriter route specifically.
    """
    from src.routes import rest_compat_middleware as rcm

    seen: list[dict[str, Any]] = []
    real = rcm.normalize_request_params

    def _recording(tool_name: str, params: dict[str, Any]) -> Any:
        seen.append(dict(params))
        return real(tool_name, params)

    with patch.object(rcm, "normalize_request_params", _recording):
        yield seen


# --------------------------------------------------------------------------
# The name, per transport
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestOperationNamePerTransport:
    """The same logical call carries the same AdCP operation name on every surface.

    One declaration — ``required_for: ["create_media_buy"]`` — and three
    unsigned, unauthenticated requests that mean the same thing. All three must
    reject with ``request_signature_required`` (security.mdx :1268, compliance
    vector 001), which is only possible if MCP's ``params.name``, A2A's
    ``data.skill`` and the REST route table all resolve to the one name.
    """

    def test_a_rest_route_is_named_by_method_and_path(self, integration_db):
        """Vector 001's shape on our wire: ``POST /api/v1/media-buys`` =
        ``create_media_buy`` (``src/routes/api_v1.py:332``).

        The vector's own URL (``/adcp/create_media_buy``) is illustrative — the
        pinned spec defines no such REST binding and that path is outside
        ``ADCP_SURFACE_PREFIXES`` — so the operation must come from the route
        table, which is the whole point of deriving it rather than parsing the
        path for a name.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**bucketed_declaration("required", "create_media_buy")):
                response = client.post(
                    _CREATE_MEDIA_BUY_PATH,
                    content=json.dumps({"packages": [], "start_time": "2026-08-01T00:00:00Z"}).encode(),
                    headers=_json_headers(None),
                )

            _assert_rejected(
                response,
                "POST /api/v1/media-buys is create_media_buy, which this posture puts in "
                "required_for; the caller presented no credential this agent accepts",
            )

    def test_an_mcp_tool_call_is_named_by_params_name(self, integration_db):
        """MCP's wire tool name IS the AdCP operation name for our registrations
        (``src/core/main.py:351-378`` — ``fn.__name__``).
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**bucketed_declaration("required", "create_media_buy")):
                response = client.post(
                    _MCP_PATH,
                    content=_mcp_tool_call("create_media_buy"),
                    headers=_json_headers(None),
                )

            _assert_rejected(
                response,
                "an MCP tools/call naming create_media_buy invokes the same required_for "
                "operation as the REST route above",
            )

    def test_an_a2a_explicit_skill_is_named_by_data_skill(self, integration_db):
        """A2A skill ids are identity with AdCP operation names, and the name
        comes from ``parts[].data.skill`` — never from the JSON-RPC ``method``,
        which is ``message/send`` for every skill.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**bucketed_declaration("required", "create_media_buy")):
                response = client.post(
                    _A2A_PATH,
                    content=_a2a_explicit_skill("create_media_buy"),
                    headers=_json_headers(None),
                )

            _assert_rejected(
                response,
                "an A2A message/send whose data.skill is create_media_buy invokes the same "
                "required_for operation as the MCP and REST calls above",
            )

    def test_the_same_path_with_a_different_method_is_a_different_operation(self, integration_db):
        """The control that makes the three above non-vacuous, and the sharpest
        one available: ``PUT /api/v1/media-buys/{id}`` is ``update_media_buy``
        (``api_v1.py:375``), which this posture does NOT require.

        A resolver that keyed on the path alone — or that promoted anything it
        could not name — answers 401 here.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with (
                _declared_posture(**bucketed_declaration("required", "create_media_buy")),
                _assert_verifier_looked(),
            ):
                response = client.put(
                    _UPDATE_MEDIA_BUY_PATH,
                    content=json.dumps({"packages": []}).encode(),
                    headers=_json_headers(None),
                )

            _assert_not_rejected(
                response,
                "PUT /api/v1/media-buys/{id} is update_media_buy, which is not in required_for; "
                "only POST on that path is create_media_buy",
            )

    def test_an_unrequired_mcp_tool_is_not_promoted(self, integration_db):
        """The MCP-side control: a different tool name on the same envelope."""
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**bucketed_declaration("required", "create_media_buy")):
                response = client.post(
                    _MCP_PATH,
                    content=_mcp_tool_call("get_products"),
                    headers=_json_headers(None),
                )

            _assert_not_rejected(
                response,
                "get_products is not in required_for; naming the operation must discriminate "
                "between tools, not merely detect that a tools/call happened",
            )


# --------------------------------------------------------------------------
# The two namespaces
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestProtocolMethodNamespace:
    """AdCP operations and JSON-RPC protocol methods are matched against
    DISJOINT envelope fields (security.mdx :1053).

    The declaration used throughout is ``protocol_methods_required_for:
    ["tasks/cancel"]`` with both AdCP buckets explicitly EMPTY, so each test
    answers exactly one question: did this request land in the protocol
    namespace or the AdCP one?
    """

    def test_a_jsonrpc_method_is_named_in_the_protocol_namespace(self, integration_db):
        """Compliance vector 028's shape: the name comes off the envelope
        ``method``, so ``tasks/cancel`` is graded against
        ``protocol_methods_required_for`` and rejects unsigned.

        NOTE for the implement atom — this is red for TWO reasons at HEAD, and
        the resolver is only the first. ``RequestSigningPosture`` cannot match
        ANY protocol method today: ``_names`` (``src/core/signing/posture.py:46-55``)
        runs ``enum_value`` over the declared items, and the
        ``protocol_methods_*`` items are pydantic ``RootModel[str]`` wrappers,
        not enums — so ``enum_value`` falls through to ``str(v)`` and the
        frozenset contains ``"root='tasks/cancel'"``. Supplying the right name
        is necessary and not sufficient.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**_requires_protocol_methods("tasks/cancel")):
                response = client.post(
                    _MCP_PATH,
                    content=_jsonrpc("tasks/cancel", {"taskId": "task-signature-probe"}),
                    headers=_json_headers(None),
                )

            _assert_rejected(
                response,
                "a JSON-RPC body whose method is tasks/cancel is a protocol-method call and "
                "this posture requires a signature for it (security.mdx :1053, vector 028)",
            )

    def test_a_tool_call_never_satisfies_a_protocol_method_bucket(self, integration_db):
        """The cross-namespace prohibition, stated as its own request: the
        string ``tasks/cancel`` arriving as ``params.name`` is an AdCP
        operation name, and "a ``protocol_methods_required_for`` membership
        MUST NOT be satisfied by a body whose JSON-RPC method is ``tools/call``"
        (:1053).

        With both AdCP buckets empty it therefore falls in ``none`` and passes.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**_requires_protocol_methods("tasks/cancel")):
                response = client.post(
                    _MCP_PATH,
                    content=_mcp_tool_call("tasks/cancel"),
                    headers=_json_headers(None),
                )

            _assert_not_rejected(
                response,
                "params.name is matched against the AdCP-operation buckets, never against "
                "protocol_methods_required_for — the two are disjoint namespaces",
            )

    def test_an_mcp_tool_call_is_named_in_the_adcp_namespace(self, integration_db):
        """R-L, the failure that a green suite would otherwise hide.

        ``bucket_for`` (``posture.py:97-103``) grades ONLY the
        ``protocol_methods_*`` trio whenever ``protocol_method`` is not None
        and ignores ``operation`` entirely. So a resolver returning
        ``("create_media_buy", "tools/call")`` — both, because both are true of
        the wire — disables ``required_for`` across the WHOLE MCP surface while
        looking more informative. Here that resolver answers 200 and this test
        fails; the mutually-exclusive one answers 401.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            declaration = bucketed_declaration("required", "create_media_buy")
            declaration["protocol_methods_supported_for"] = ["tools/call"]

            with _declared_posture(**declaration):
                response = client.post(
                    _MCP_PATH,
                    content=_mcp_tool_call("create_media_buy"),
                    headers=_json_headers(None),
                )

            _assert_rejected(
                response,
                "an MCP tools/call must carry its operation in the AdCP namespace and NO "
                "protocol method; returning tools/call as the protocol method routes the "
                "grading to protocol_methods_* and silently disables required_for on MCP",
            )


# --------------------------------------------------------------------------
# Session frames vs genuinely unresolvable requests (R-M3, plan step 5)
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestSessionFramesAreNotUnresolvable:
    """A transport session frame is a non-operation by construction; an
    unnameable AdCP request fails closed. Both under the SAME declaration, so
    neither can pass by accident.
    """

    def test_a_bodiless_mcp_get_is_a_session_frame(self, integration_db):
        """R-M3 — the streamable-HTTP stream open carries no body at all.

        "Non-JSON body ⇒ unresolvable ⇒ promote to the strictest declared
        bucket" would 401 every SSE stream open the moment a posture declares
        ``required_for``, which is the outage plan step 5 exists to avoid. The
        rule that prevents it has to sit AHEAD of the unresolvable test.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**bucketed_declaration("required", "create_media_buy")):
                response = client.get(_MCP_PATH, headers=request_headers(None))

            _assert_not_rejected(
                response,
                "GET /mcp is a streamable-HTTP session frame with no body — a non-operation, "
                "never an unresolvable AdCP request",
            )

    def test_an_unparseable_body_on_an_adcp_surface_fails_closed(self, integration_db):
        """Plan step 5 — the anti-bypass, and what makes the sibling above
        non-vacuous: a POST that carries a body which names nothing is
        genuinely unresolvable and is promoted to the strictest bucket the
        posture declares.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            seed_principal(env)
            client = _client(env)

            with _declared_posture(**bucketed_declaration("required", "create_media_buy")):
                response = client.post(
                    _MCP_PATH,
                    content=b"<<< this is not JSON and names no operation >>>",
                    headers=_json_headers(None),
                )

            _assert_rejected(
                response,
                "a body that names no operation on an AdCP surface must fail closed to the "
                "strictest declared bucket, not resolve to nothing and grade as unverified",
            )


# --------------------------------------------------------------------------
# The webhook-registration escalation (spec :1462-1465, vector 027)
# --------------------------------------------------------------------------


@pytest.mark.requires_db
class TestWebhookAuthenticationForcesASignature:
    """Credentials in the payload force a signature REGARDLESS of the bucket
    and REGARDLESS of the bearer.

    ":1465 — Sellers that support request signing MUST require the inbound
    request to be 9421-signed … when ``authentication`` is present on
    ``push_notification_config.authentication`` or any
    ``accounts[].notification_configs[].authentication``", restated at :1375 as
    a trigger "regardless of ``required_for`` membership". Every posture below
    declares ``required_for: []``, so a rejection can only have come from the
    payload.
    """

    @staticmethod
    def _webhook_body(*, with_authentication: bool) -> bytes:
        config: dict[str, Any] = {"url": "https://buyer.example.com/adcp-webhook"}
        if with_authentication:
            config["authentication"] = dict(_WEBHOOK_AUTHENTICATION)
        return json.dumps({"push_notification_config": config}).encode()

    @staticmethod
    def _account_webhook_body() -> bytes:
        """The SECOND escalation trigger, factored out because two tests now send it."""
        return json.dumps(
            {
                "accounts": [
                    {
                        "account_id": "acct-signature-probe",
                        "notification_configs": [
                            {
                                "url": "https://buyer.example.com/account-webhook",
                                "authentication": dict(_WEBHOOK_AUTHENTICATION),
                            }
                        ],
                    }
                ]
            }
        ).encode()

    def test_push_notification_authentication_rejects_an_authenticated_caller(self, integration_db):
        """The case vector 027 structurally CANNOT grade, and therefore the
        case B3 green will never prove.

        027's ``test-bearer-token`` resolves to no principal, so it 401s under
        both readings of the composition rule. Here the bearer is a REAL
        principal of this tenant, and the request must still be rejected: the
        rule exists precisely because the registering caller is normally
        bearer-authed and an on-path mutator can inject or strip the
        ``authentication`` block, so exempting authenticated callers would
        defeat the entire rule.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            token = seed_principal(env)
            client = _client(env)

            with _declared_posture(**_supported_only()):
                response = client.put(
                    _UPDATE_MEDIA_BUY_PATH,
                    content=self._webhook_body(with_authentication=True),
                    headers=_json_headers(token),
                )

            _assert_rejected(
                response,
                "push_notification_config.authentication is present, so security.mdx :1465 "
                "requires the request to be signed — a valid bearer does NOT satisfy it "
                "(the composition rule is scoped to required_for operations, and this "
                "posture declares required_for: [])",
            )

    def test_account_notification_config_authentication_also_rejects(self, integration_db):
        """The second trigger named at :1465 — the one with NO compliance
        vector, which is exactly why it needs its own test: a resolver
        handling only ``push_notification_config`` passes all 40 vectors and
        is still wrong.
        """
        body = self._account_webhook_body()

        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            token = seed_principal(env)
            client = _client(env)

            with _declared_posture(**_supported_only()):
                response = client.post(_SYNC_ACCOUNTS_PATH, content=body, headers=_json_headers(token))

            _assert_rejected(
                response,
                "accounts[].notification_configs[].authentication is the second escalation "
                "trigger at security.mdx :1465 and carries the same MUST",
            )

    def test_the_same_registration_without_credentials_is_not_escalated(self, integration_db):
        """The control: byte-identical apart from the ``authentication`` block.

        Without it there are no credentials to steal, the escalation must not
        fire, and an unsigned bearer-authed webhook registration is ordinary
        traffic.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            token = seed_principal(env)
            client = _client(env)

            with _declared_posture(**_supported_only()):
                response = client.put(
                    _UPDATE_MEDIA_BUY_PATH,
                    content=self._webhook_body(with_authentication=False),
                    headers=_json_headers(token),
                )

            _assert_not_rejected(
                response,
                "a push_notification_config with no authentication block carries no "
                "credentials; escalating it would 401 ordinary webhook registrations",
            )

    def test_the_escalation_fires_for_a_tenant_that_DECLARED_NOTHING(self, integration_db):
        """The newly-reachable case, and the only one with no declaration at all.

        Every other test in this class establishes an explicit posture through
        ``_declared_posture``. That leaves the case #1291 D1 created unguarded: a tenant
        that declares NOTHING now resolves to the AGENT-LEVEL posture
        (``posture_for_tenant`` -> ``agent_level_posture``, ``supported`` =
        ``SigningConfig.verifier_enabled``, every bucket empty), which puts every operation
        in the ``supported`` bucket rather than ``none`` — so :1465's escalation binds this
        deployment for ordinary traffic, not only for tenants who opted into a posture.

        That is not a hypothetical: it is exactly what turned a green UC-011 scenario red
        the moment D1 landed, and the escalation branch had no test that would have
        predicted it. security.mdx @ v3.1.1's "Downgrade and injection resistance" block
        binds "sellers that support request signing", and D1 is what made this deployment
        one; the unsigned-seller fallback there is explicitly "a 3.0 migration note, not an
        exemption".

        No ``_declared_posture`` context by design — substituting one would recreate the
        gap this test exists to close.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            token = seed_principal(env)
            client = _client(env)

            response = client.post(
                _SYNC_ACCOUNTS_PATH, content=self._account_webhook_body(), headers=_json_headers(token)
            )

            _assert_rejected(
                response,
                "a tenant that declared no posture at all still SUPPORTS request signing "
                "after #1291 D1 (the agent-level default is supported=verifier_enabled), so "
                "accounts[].notification_configs[].authentication must force a signature "
                "here exactly as it does under an explicitly declared posture",
            )

    def test_the_escalation_does_not_fire_under_an_unsupported_posture(self, integration_db):
        """:1465 binds "sellers that SUPPORT request signing". Under
        ``supported: false`` signatures are ignored entirely (the ``none``
        bucket, ``posture.py:95-96``), and an agent that does not verify
        signatures cannot demand one.
        """
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            token = seed_principal(env)
            client = _client(env)

            with _declared_posture(supported=False):
                response = client.put(
                    _UPDATE_MEDIA_BUY_PATH,
                    content=self._webhook_body(with_authentication=True),
                    headers=_json_headers(token),
                )

            _assert_not_rejected(
                response,
                "security.mdx :1465 binds sellers that SUPPORT request signing; under "
                "supported: false the middleware ignores signatures entirely",
            )


# --------------------------------------------------------------------------
# R-H2 / R-M5 — the unsigned body survives the reorder
# --------------------------------------------------------------------------

#: Small enough to make the over-cap path a millisecond test rather than a
#: ten-megabyte one, large enough that the padding below exceeds it.
_TEST_BODY_CAP = 4096

#: Padding that must arrive at the handler byte-for-byte. Long enough to push
#: any body it appears in past :data:`_TEST_BODY_CAP`.
_PADDING = "P" * (_TEST_BODY_CAP * 2)


@pytest.mark.requires_db
class TestUnsignedBodyReachesTheHandlerIntact:
    """The reorder buffers EVERY request, not just signed ones — so for the
    first time an unsigned body is drained by this middleware and replayed.

    R-M5: the downstream handler must receive identical bytes, on a plain route
    and on the body-rewriter route where ``RestCompatMiddleware`` reads the
    body through the replay.

    R-H2: ``max_signed_body_bytes`` now bounds unsigned traffic too, and
    ``_buffer_body``'s over-cap branch DISCARDS the chunks it already read and
    returns an empty ``pending`` — harmless only because its one caller
    (``_handle_signed``) 413s immediately. On the unsigned path that same
    branch is either a 413 this middleware has never issued on unsigned
    traffic, or a handler receiving a destroyed body. Neither is acceptable, so
    both routes below are graded under AND over the cap.

    Neither fault produces a SHORT body — both deadlock, which is what the
    module-level timeout above exists to terminate.
    """

    @pytest.mark.parametrize("cap", [None, _TEST_BODY_CAP], ids=["under-cap", "over-cap"])
    def test_a_plain_route_receives_every_byte(self, integration_db, cap):
        """``POST /api/v1/capabilities`` echoes ``context`` verbatim, so the
        request_id below is a byte-for-byte receipt of what the handler got.

        A truncating over-cap path answers 422 (or echoes a short id); a
        rejecting one answers 413. Only a lossless replay answers 200 with the
        whole string.
        """
        body = {"context": {"request_id": _PADDING}}
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            token = seed_principal(env)
            client = _client(env)

            with _declared_posture(**_supported_only()), _body_cap(cap) if cap else nullcontext():
                response = client.post(BODYLESS_ADCP_PATH, json=body, headers=request_headers(token))

            assert response.status_code == 200, (
                "an UNSIGNED request must never be answered by the signature verifier's "
                f"413 — the body cap bounds what the verifier buffers before HASHING, and "
                f"nothing is hashed here. Got {response.status_code}: {response.text[:300]}"
            )
            assert response.json()["context"]["request_id"] == _PADDING, (
                "the handler must receive every byte of an unsigned body the verifier "
                "buffered and replayed; the echoed request_id came back "
                f"{len(response.json()['context'].get('request_id', ''))} bytes long instead "
                f"of {len(_PADDING)}"
            )

    @pytest.mark.parametrize("cap", [None, _TEST_BODY_CAP], ids=["under-cap", "over-cap"])
    def test_the_body_rewriter_route_receives_every_byte(self, integration_db, cap):
        """R-M5 names this route specifically: ``RestCompatMiddleware`` runs
        INSIDE the verifier and reads the body off the replaying ``receive``
        (``rest_compat_middleware.py:57``), so it is the one downstream reader
        whose input can be observed directly.

        ``test_rest_compat_still_normalizes_the_deprecated_field``
        (``test_request_signature_middleware.py:810``) is the same route's
        companion gate for the translation itself; this one grades the BYTES.
        """
        body = {
            "account_id": "acct-deprecated-name",
            "packages": [],
            "start_time": "2026-08-01T00:00:00Z",
            "buyer_ref": _PADDING,
        }
        with BareIntegrationEnv(tenant_id=SIGNING_TENANT_ID, principal_id=SIGNING_PRINCIPAL_ID) as env:
            token = seed_principal(env)
            client = _client(env)

            with (
                _declared_posture(**_supported_only()),
                _body_cap(cap) if cap else nullcontext(),
                _rest_compat_spy() as parsed,
            ):
                response = client.post(REWRITTEN_ADCP_PATH, json=body, headers=request_headers(token))

            assert response.status_code != 413, (
                "an UNSIGNED request must never be answered with the signed-body 413; "
                f"got {response.status_code}: {response.text[:300]}"
            )
            assert len(parsed) == 1, (
                "RestCompatMiddleware must still parse this route's body downstream of the "
                f"verifier; it parsed {len(parsed)} bodies. Zero means the replayed receive "
                "yielded nothing and the deprecated-field translation silently stopped running"
            )
            assert parsed[0] == body, (
                "the downstream body reader must receive the request EXACTLY as sent; it got "
                f"{ {key: (value[:40] + '…' if isinstance(value, str) and len(value) > 40 else value) for key, value in parsed[0].items()} }"
            )

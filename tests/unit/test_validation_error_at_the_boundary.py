"""A pydantic ``ValidationError`` raised at DTO construction is the SAME error on every transport.

This replaces two deleted structural guards, and it grades the property they were
written to protect instead of the mechanism they happened to scan for.

Both guards -- ``test_architecture_request_construction_boundary.py`` and
``test_guards_rest_request_boundary.py`` -- failed a typed ``*Request(...)``
constructed outside a ``with adcp_validation_boundary(...)`` block, on the stated
premise that "a raw Pydantic ValidationError then leaks past the transport boundary
untranslated -- the buyer loses the real error code/recovery/suggestion". That premise
is false, and this module is the measurement that says so: all three transports route
an escaping ``ValidationError`` through the one ``adcp_error_for`` mapping (MCP via
``_translate_to_tool_error``, A2A via its skill dispatcher, REST via
``@app.exception_handler(ValueError)`` -- a pydantic ``ValidationError`` IS a
``ValueError`` subclass, and ``adcp_error_for`` tests ``ValidationError`` FIRST so the
buyer gets ``field`` and ``issues`` rather than a bare VALIDATION_ERROR).

So the 48 wrapper blocks were deleted, and the guards with them. A scan for the
wrapper cannot survive the wrapper. What has to survive is the WIRE PROPERTY, which
is what the three tests below assert -- on the actual envelope each transport emits,
never on a reconstruction (tests/CLAUDE.md, Error Verification Policy).

Why the deleted guards could not have caught a real regression here anyway: the
architecture one exempts builder bodies by design, and every transport now constructs
through a builder, so it went on passing with all 48 blocks removed. Its green graded
nothing.

The tool is ``get_adcp_capabilities`` because it is auth-optional on all three
transports, so the comparison needs no database and no principal -- the only thing
under test is the boundary. The builder is replaced by a stand-in that raises a REAL
``ValidationError`` from the REAL DTO: a stand-in rather than a bad payload because
the three transports reject a malformed payload at three different LAYERS (FastAPI's
body model on REST, FastMCP's argument schema on MCP, the DTO itself on A2A), and
what is under test is the one layer they share.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest
from adcp.types import GetAdcpCapabilitiesRequest as LibraryGetAdcpCapabilitiesRequest
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from src.core.exceptions import AdCPSalesAgentError, build_two_layer_error_envelope
from tests.helpers import assert_envelope_shape

#: The one field path the DTO rejection is about, in the JSONPath-lite form
#: core/error.json specifies. Every transport must name it identically.
EXPECTED_FIELD = "protocols[0]"


def _real_validation_error() -> ValidationError:
    """A genuine pydantic ``ValidationError`` from the request DTO itself.

    Built by rejecting an out-of-enum protocol rather than by constructing a
    ``ValidationError`` directly: a hand-made one carries whatever ``loc`` and
    ``type`` the test chose, so the ``field`` and ``issues`` derivations would be
    graded against the test's own input instead of against pydantic's.
    """
    with pytest.raises(ValidationError) as excinfo:
        LibraryGetAdcpCapabilitiesRequest(protocols=["not-a-real-protocol"])
    return excinfo.value


def _builder_that_raises(exc: ValidationError):
    """Stand-in for ``build_get_adcp_capabilities_request`` that fails at construction.

    A real function with the real return annotation, NOT a ``Mock``. The tool -> DTO
    edge is resolved by reading this object's return annotation
    (``_announced_shape.request_model_for``), so a Mock makes the request seam
    unresolvable and the transports fail with a RuntimeError about the seam -- a
    different failure, measured instead of the one under test.
    """

    def _builder(**kwargs):
        raise exc

    _builder.__name__ = "build_get_adcp_capabilities_request"
    _builder.__annotations__ = {"return": LibraryGetAdcpCapabilitiesRequest}
    return _builder


def _assert_is_the_expected_rejection(envelope: dict) -> None:
    """The whole obligation, in one place, so the three transports are graded identically."""
    assert_envelope_shape(envelope, "INVALID_REQUEST", recovery="correctable")
    assert envelope["adcp_error"]["field"] == EXPECTED_FIELD
    # ``issues`` is the half a bare VALIDATION_ERROR would have dropped, so it is
    # asserted rather than merely present: the pointer is what tells the buyer WHICH
    # array element the enum rejection is about.
    assert envelope["adcp_error"]["issues"] == [
        {
            "pointer": "/protocols/0",
            "message": "This field must be one of the accepted values.",
            "keyword": "enum",
            "keyword_value": "'media_buy', 'signals', 'governance', 'sponsored_intelligence' or 'creative'",
        }
    ]


def _rest_envelope() -> tuple[int, dict]:
    from starlette.testclient import TestClient

    import src.core.tools.capabilities as capabilities_module
    from src.app import app
    from src.core.auth_context import _resolve_auth_dep

    # The route's identity dependency reads a tenant out of Postgres and the handler
    # stack under test never looks at it; overriding the dependency is FastAPI's own
    # seam for that, so no part of identity resolution has to be faked.
    app.dependency_overrides[_resolve_auth_dep] = lambda: None
    try:
        with patch.object(
            capabilities_module,
            "build_get_adcp_capabilities_request",
            _builder_that_raises(_real_validation_error()),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/v1/capabilities", json={"protocols": ["mcp"]})
    finally:
        app.dependency_overrides.pop(_resolve_auth_dep, None)
    return response.status_code, response.json()


def _mcp_envelope() -> tuple[int, dict]:
    import src.core.tools.capabilities as capabilities_module
    from src.core import main
    from src.core.tool_error_logging import with_error_logging

    registered = with_error_logging(main.get_adcp_capabilities)
    with patch.object(
        capabilities_module,
        "build_get_adcp_capabilities_request",
        _builder_that_raises(_real_validation_error()),
    ):
        with pytest.raises(ToolError) as excinfo:
            asyncio.run(registered(protocols=["mcp"]))
    error = excinfo.value
    # ``str(error)`` IS the MCP wire text: FastMCP serializes a raised ToolError as
    # ``CallToolResult(content=[TextContent(text=str(error))])``, so parsing it grades
    # the bytes the buyer parses rather than the ``envelope`` attribute beside them.
    return error.status_code, json.loads(str(error))


def _a2a_envelope() -> tuple[int, dict]:
    import src.core.tools.capabilities as capabilities_module
    from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

    # The dispatcher is the unit under test and touches no instance state on this
    # path, so it is exercised without running the handler's constructor (which wires
    # a full A2A application).
    handler = AdCPRequestHandler.__new__(AdCPRequestHandler)
    with patch.object(
        capabilities_module,
        "build_get_adcp_capabilities_request",
        _builder_that_raises(_real_validation_error()),
    ):
        with pytest.raises(AdCPSalesAgentError) as excinfo:
            asyncio.run(handler._handle_explicit_skill("get_adcp_capabilities", {"protocols": ["mcp"]}, None))
    typed = excinfo.value
    return typed.status_code, build_two_layer_error_envelope(typed)


class TestValidationErrorNeedsNoWrapper:
    """Each transport, alone. A regression on one fails only its own test."""

    def test_rest_answers_invalid_request_with_field_and_issues(self):
        status, envelope = _rest_envelope()

        assert status == 400
        _assert_is_the_expected_rejection(envelope)

    def test_mcp_answers_invalid_request_with_field_and_issues(self):
        status, envelope = _mcp_envelope()

        assert status == 400
        _assert_is_the_expected_rejection(envelope)

    def test_a2a_answers_invalid_request_with_field_and_issues(self):
        status, envelope = _a2a_envelope()

        assert status == 400
        _assert_is_the_expected_rejection(envelope)


def test_the_three_transports_emit_the_same_envelope():
    """Byte-identical, not merely each-conforming.

    The three tests above would all pass if one transport dropped ``suggestion`` and
    the others kept it, or if they spelled the same rejection with different messages
    -- each would still satisfy its own assertions. Cross-transport divergence is the
    defect this file exists for, so it is asserted directly: one request, one answer,
    whichever door the buyer came through.
    """
    rest_status, rest = _rest_envelope()
    mcp_status, mcp = _mcp_envelope()
    a2a_status, a2a = _a2a_envelope()

    assert rest == mcp == a2a
    assert rest_status == mcp_status == a2a_status == 400

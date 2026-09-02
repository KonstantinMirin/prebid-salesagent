"""Error-boundary behavior that has no other grader in this suite.

This module is deliberately narrow. Everything it once asserted about a code's
``message`` / ``recovery`` / ``suggestion`` is gone: all three are read-only
properties over ``CODE_TABLE`` (``src/core/errors/codes.py``), so pinning them
per exception class copies the pinned table into a second place instead of
grading production. What remains is the behavior that lives in *code* rather
than in the table, and that nothing else in the suite exercises:

- ``handle_tool_error`` — the body of ``@app.exception_handler(ToolError)``
  wired at ``src/app.py``. A typed ``AdCPToolError`` forwards its envelope and
  its ``status_code``; a plain ``ToolError`` is rebuilt from a synthetic error
  whose HTTP status comes from ``_ERROR_CODE_TO_STATUS`` and whose code falls
  back to ``INTERNAL_ERROR`` when the wire string is unrecognized.
- ``AdCPSalesAgentError.status_code`` — a read-only function of the wire code,
  read from ``CODE_TABLE``. What is graded is that one code cannot be answered
  with two statuses, and that the answer does not move with the import set.
- ``extract_error_info`` on its NON-typed branches — the plain-``ToolError``
  argument shapes, the ``is_error_code`` heuristic that chooses between them,
  and the non-``ToolError`` fallthrough.
- ``_coerce_recovery`` — membership validation of a wire ``recovery`` string.
- ``adcp_error_for``'s type mapping (``ValueError`` → VALIDATION_ERROR / 400,
  ``PermissionError`` → PERMISSION_DENIED / 403) at each of the three
  boundaries that call it.
- ``_translate_to_tool_error``'s plain-``ToolError`` passthrough, which must
  stay ahead of the pre-converted ``typed`` short-circuit.
- The HTTP ``status_code`` roundtrip through REST. ``CODE_TABLE`` now carries
  the status, so the value itself is a table read — what is NOT a table read is
  whether it survives the handler stack and lands on the response, which is what
  driving each exception through REST grades.
"""

from __future__ import annotations

import copy
import inspect
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from src.core.errors.codes import CODE_TABLE, Recovery
from src.core.exceptions import (
    AdCPAdapterError,
    AdCPConflictError,
    AdCPGoneError,
    AdCPMediaBuyNotFoundError,
    AdCPRateLimitError,
    AdCPSalesAgentError,
    AdCPServiceUnavailableError,
    AdCPValidationError,
    build_two_layer_error_envelope,
)
from src.core.tool_error_logging import (
    AdCPToolError,
    _coerce_recovery,
    _translate_to_tool_error,
    extract_error_info,
    handle_tool_error,
    with_error_logging,
)
from tests.helpers import assert_envelope_shape


def _capabilities_response(side_effect: Exception):
    """Drive ``GET /api/v1/capabilities`` with ``side_effect`` raised inside the tool.

    The single patch site for every REST case below. The route is the thinnest
    endpoint in the app — one call, one ``model_dump`` — so what it grades is the
    exception-handler stack registered in ``src/app.py``, not the capabilities tool.
    """
    from starlette.testclient import TestClient

    from src.app import app
    from src.core.auth_context import _resolve_auth_dep

    # The route's identity dependency reads the tenant out of Postgres, and the
    # handler stack under test never looks at it. Overriding the dependency is
    # FastAPI's own seam for that, so no part of identity resolution has to be
    # faked to reach the exception handlers.
    app.dependency_overrides[_resolve_auth_dep] = lambda: None
    try:
        with patch("src.core.tools.capabilities.get_adcp_capabilities_raw", side_effect=side_effect):
            client = TestClient(app, raise_server_exceptions=False)
            return client.get("/api/v1/capabilities")
    finally:
        app.dependency_overrides.pop(_resolve_auth_dep, None)


# ---------------------------------------------------------------------------
# handle_tool_error — the body of @app.exception_handler(ToolError)
# ---------------------------------------------------------------------------


class TestHandleToolError:
    """``handle_tool_error`` is the whole ToolError REST boundary.

    ``src/app.py`` registers ``@app.exception_handler(ToolError)`` and delegates
    to this function, so every branch here is live on the wire: an MCP-wrapped
    tool invoked from a REST route raises ``AdCPToolError`` and lands in the
    typed branch, while legacy code that raises ``ToolError`` directly lands in
    the reconstruction branch.
    """

    def test_adcp_tool_error_forwards_envelope_and_status(self):
        """The typed branch forwards the carried envelope and the source status verbatim."""
        source = AdCPMediaBuyNotFoundError()
        envelope = build_two_layer_error_envelope(source)

        response = handle_tool_error(AdCPToolError(envelope, status_code=source.status_code))

        assert response.status_code == source.status_code == 404
        assert json.loads(response.body) == envelope

    def test_adcp_tool_error_envelope_is_not_aliased_into_the_response(self):
        """The defensive ``dict()`` copy leaves the exception's own envelope untouched.

        The envelope dict is owned by the ``AdCPToolError`` instance, which the
        audit log and activity feed may still be holding. Handing it to the
        serializer by reference makes the response and the exception the same
        object; this pins that they are not.
        """
        source = AdCPAdapterError()
        tool_error = AdCPToolError(build_two_layer_error_envelope(source), status_code=source.status_code)
        before = copy.deepcopy(tool_error.envelope)

        response = handle_tool_error(tool_error)

        assert tool_error.envelope == before
        assert json.loads(response.body) == before

    def test_plain_tool_error_with_known_code_uses_the_status_map(self):
        """``ToolError("VALIDATION_ERROR", ...)`` resolves 400 through ``_ERROR_CODE_TO_STATUS``.

        Legacy paths construct ``ToolError`` directly and carry no typed source
        that owns ``status_code``, so the map is the only thing standing between
        a 4xx condition and a 500 response.
        """
        response = handle_tool_error(ToolError("VALIDATION_ERROR", "missing required field"))

        assert response.status_code == 400
        assert_envelope_shape(json.loads(response.body), "VALIDATION_ERROR", recovery="correctable")

    def test_plain_tool_error_with_unknown_code_becomes_internal_error_500(self):
        """An unrecognized wire code resolves to INTERNAL_ERROR at 500 — a named fallback.

        The code is not passed through: an unvalidated string from a legacy
        raise site would reach the buyer as an error code the pinned table
        cannot classify.
        """
        response = handle_tool_error(ToolError("WEIRD_LEGACY_CODE", "what is this"))

        assert response.status_code == 500
        assert_envelope_shape(json.loads(response.body), "INTERNAL_ERROR", recovery="transient")

    def test_single_arg_tool_error_becomes_internal_error_500(self):
        """``ToolError("unstructured failure")`` carries no code at all, so it is a 500."""
        response = handle_tool_error(ToolError("unstructured failure"))

        assert response.status_code == 500
        assert_envelope_shape(json.loads(response.body), "INTERNAL_ERROR", recovery="transient")


class TestStatusIsAFunctionOfTheWireCode:
    """One wire code, one HTTP status — with nowhere left to say otherwise.

    ``status_code`` used to be a per-class ``_default_status_code`` slot, and the
    plain-``ToolError`` boundary reconstructed a code → status table by walking
    ``AdCPSalesAgentError.__subclasses__()`` and letting the highest status win.
    Both halves were wrong in the same way. A subclass could redeclare its
    ``_code`` and keep a status that belonged to its parent's code —
    ``SimulationError`` emitted INVALID_REQUEST carrying ``AdCPNotFoundError``'s
    404 — and because ``__subclasses__()`` only sees classes already imported,
    the table answered INVALID_REQUEST 400 or 404 depending on which modules the
    process had imported first (salesagent-pssfi).

    The status is now read from ``CODE_TABLE`` by code. These tests grade the
    two properties that fix bought: no code has two statuses, and no status
    depends on the import set.
    """

    def test_no_subclass_can_shadow_the_derived_status(self):
        """Every class in the hierarchy resolves ``status_code`` to the ONE property.

        The check is structural — ``getattr_static`` on the live class set, so a
        subclass added later is graded the moment it exists — rather than
        instantiating each class and comparing numbers: several classes take
        required constructor arguments (``SetupIncompleteError``), and a
        value-comparison test would be reporting on whichever of them a given
        worker's import set happened to have loaded. What must stay impossible is
        not a wrong number but a second place to put one, which is exactly what
        the old ``_default_status_code`` slot was: writable, inheritable, and
        free to belong to a different code than the class's own.
        """
        derived = AdCPSalesAgentError.__dict__["status_code"]
        walked = list(AdCPSalesAgentError.iter_concrete_subclasses())

        # Non-vacuity: an empty walk would satisfy every assertion below.
        assert walked, "no concrete AdCPSalesAgentError subclass was walked — the check is vacuous"

        shadowed = [
            f"  {cls.__name__} defines its own status_code ({inspect.getattr_static(cls, 'status_code')!r})"
            for cls in walked
            if inspect.getattr_static(cls, "status_code", derived) is not derived
        ]
        assert not shadowed, (
            "these classes override the code-derived HTTP status, so one wire code can again be "
            "answered two ways:\n" + "\n".join(shadowed)
        )

    def test_the_derived_status_is_the_table_entry(self):
        """The property reads ``CODE_TABLE``, so a class's code decides its status.

        Paired with the shadowing check above: that one says there is exactly one
        place the status can come from, this one says what that place is. Uses
        the base class with a named code, which is the only construction that
        can vary the code independently of the class.
        """
        error = AdCPSalesAgentError(error_code=AdCPAdapterError._code)

        assert error.status_code == CODE_TABLE[AdCPAdapterError._code].status == 503

    def test_two_classes_sharing_a_code_are_answered_identically(self):
        """SERVICE_UNAVAILABLE is emitted by four classes and answered one way.

        A real collision, not a constructed one: ``AdCPAdapterError`` declared
        502 and ``AdCPServiceUnavailableError`` 503 while both put
        SERVICE_UNAVAILABLE on the wire, so one failure told the buyer two
        different things. The buyer reads the code, so the code decides: 503.
        """
        assert AdCPAdapterError._code == AdCPServiceUnavailableError._code

        assert AdCPAdapterError().status_code == AdCPServiceUnavailableError().status_code == 503

    def test_simulation_error_is_answered_as_the_bad_request_it_is(self):
        """``SimulationError`` emits INVALID_REQUEST, so it is a 400 — not its parent's 404.

        Graded through REST rather than off the attribute: the 404 the buyer
        used to get came out of the response, and that is where it has to stop.
        """
        from src.core.strategy import SimulationError

        response = _capabilities_response(SimulationError())

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "INVALID_REQUEST", recovery="correctable")

    def test_status_does_not_move_with_the_import_set(self):
        """The same code resolves to the same status under a narrow and a wide import.

        This is the literal regression, so it is graded on the literal path: a
        plain ``ToolError("INVALID_REQUEST")`` through ``handle_tool_error``,
        which is what a legacy raise site puts in front of a buyer. It has to run
        out-of-process twice — the defect was that the answer depended on which
        modules had been imported, and a test sharing this session's interpreter
        has already imported everything. The wide leg imports
        ``src.core.strategy`` first, whose ``SimulationError`` used to raise the
        derived table's INVALID_REQUEST entry from 400 to 404; the narrow leg
        does not. They used to disagree.
        """
        resolve = (
            "from fastmcp.exceptions import ToolError;"
            "from src.core.tool_error_logging import handle_tool_error;"
            "print(handle_tool_error(ToolError('INVALID_REQUEST', 'bad')).status_code)"
        )
        legs = ("", "import src.core.strategy;")

        answers = [
            subprocess.run(
                [sys.executable, "-c", leg + resolve],
                capture_output=True,
                text=True,
                check=True,
                cwd=Path(__file__).resolve().parents[2],
            ).stdout.strip()
            for leg in legs
        ]

        assert answers == ["400", "400"], f"INVALID_REQUEST resolved differently per import set: {answers}"

    def test_a_caller_cannot_name_a_status_that_contradicts_the_code(self):
        """There is no ``status_code=`` parameter, so no raise site can override it.

        The old constructor took one, which is how a boundary could hand a code
        one status while the class that owned the code declared another.
        """
        with pytest.raises(TypeError):
            AdCPValidationError(status_code=500)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# extract_error_info — the branches that do NOT read a typed exception
# ---------------------------------------------------------------------------


class TestExtractErrorInfoUntypedBranches:
    """``extract_error_info`` parses plain ``ToolError`` argument shapes.

    The typed branches read ``AdCPToolError.envelope`` / ``AdCPSalesAgentError``
    attributes and are graded wherever those errors cross a boundary. These
    branches exist only for code that raises ``ToolError`` directly, and the
    heuristic that routes between them is graded nowhere else.
    """

    def test_three_arg_tool_error_reads_recovery_from_the_third_arg(self):
        """``ToolError(code, message, recovery)`` yields all three."""
        code, message, recovery = extract_error_info(ToolError("SERVICE_UNAVAILABLE", "GAM down", "transient"))

        assert (code, message, recovery) == ("SERVICE_UNAVAILABLE", "GAM down", Recovery.TRANSIENT)

    def test_two_arg_tool_error_has_no_recovery(self):
        """``ToolError(code, message)`` yields ``None`` recovery — nothing to invent it from."""
        code, message, recovery = extract_error_info(ToolError("VALIDATION_ERROR", "bad field"))

        assert (code, message, recovery) == ("VALIDATION_ERROR", "bad field", None)

    def test_first_arg_that_is_not_code_shaped_falls_to_the_single_arg_branch(self):
        """The ``is_error_code`` heuristic rejects a first arg with spaces or lowercase.

        Without it, a two-arg ``ToolError`` whose first argument is prose would
        put that prose on the wire as an error code.
        """
        error = ToolError("not a code at all", "second arg")

        code, message, recovery = extract_error_info(error)

        assert code == "TOOL_ERROR"
        assert message == str(error)
        assert recovery is None

    def test_single_arg_tool_error_reports_tool_error(self):
        """``ToolError("message")`` has no code, so the placeholder TOOL_ERROR stands in."""
        code, message, recovery = extract_error_info(ToolError("something failed"))

        assert (code, message, recovery) == ("TOOL_ERROR", "something failed", None)

    def test_non_tool_error_reports_its_type_name(self):
        """An arbitrary exception reports its class name and ``str()``, with no recovery."""
        code, message, recovery = extract_error_info(RuntimeError("unexpected"))

        assert (code, message, recovery) == ("RuntimeError", "unexpected", None)


class TestCoerceRecovery:
    """``_coerce_recovery`` is the membership check on an untrusted recovery string.

    ``extract_error_info`` advertises ``Recovery | None``, but both the envelope
    branch and the legacy ToolError branch read a value typed ``str | None`` on
    the wire. The enum is the validator; anything outside it becomes ``None``
    rather than silently escaping the type contract.
    """

    def test_known_wire_string_becomes_the_enum_member(self):
        assert _coerce_recovery("transient") is Recovery.TRANSIENT

    def test_unknown_wire_string_becomes_none(self):
        assert _coerce_recovery("mostly_harmless") is None

    def test_non_string_becomes_none(self):
        assert _coerce_recovery(object()) is None

    def test_unknown_recovery_arg_reaches_none_through_extract_error_info(self):
        """The legacy ToolError path cannot smuggle an off-vocabulary recovery through."""
        code, _message, recovery = extract_error_info(ToolError("VALIDATION_ERROR", "bad", "mostly_harmless"))

        assert code == "VALIDATION_ERROR"
        assert recovery is None


# ---------------------------------------------------------------------------
# _translate_to_tool_error — passthrough ordering at the MCP boundary
# ---------------------------------------------------------------------------


class TestTranslateToToolErrorPassthrough:
    """A ``ToolError`` reaching the MCP translator is already in wire shape.

    The passthrough is keyed on the RAW error and must stay ahead of the
    ``typed`` short-circuit: a caller that pre-converted still hands over the
    original exception, and re-wrapping it would bury an envelope inside an
    envelope.
    """

    def test_plain_tool_error_is_reraised_unchanged(self):
        error = ToolError("EXISTING_CODE", "existing message")

        with pytest.raises(ToolError) as exc_info:
            _translate_to_tool_error(error)

        assert exc_info.value is error

    def test_passthrough_wins_over_a_supplied_typed_conversion(self):
        """Passing ``typed=`` does not divert a ToolError into the wrapping branch."""
        error = ToolError("EXISTING_CODE", "existing message")

        with pytest.raises(ToolError) as exc_info:
            _translate_to_tool_error(error, typed=AdCPValidationError())

        assert exc_info.value is error

    def test_adcp_tool_error_is_reraised_unchanged(self):
        """``AdCPToolError`` is a ``ToolError``, so it passes through rather than double-wrapping."""
        error = AdCPToolError(build_two_layer_error_envelope(AdCPValidationError()), status_code=400)

        with pytest.raises(AdCPToolError) as exc_info:
            _translate_to_tool_error(error)

        assert exc_info.value is error


# ---------------------------------------------------------------------------
# adcp_error_for's type mapping, at every boundary that calls it
# ---------------------------------------------------------------------------


class TestAdcpErrorForAtEveryBoundary:
    """``ValueError`` and ``PermissionError`` get the same wire shape on all three transports.

    ``adcp_error_for`` is the single source of truth for the mapping, but each
    boundary reaches it by its own route — MCP through
    ``_translate_to_tool_error``, REST through the registered exception
    handlers, A2A through ``_build_error_envelope`` — so a boundary that stops
    calling it fails here and only here.
    """

    def test_mcp_boundary_maps_value_error_to_validation_error(self):
        def failing_tool():
            raise ValueError("invalid input shape")

        with pytest.raises(ToolError) as exc_info:
            with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, "VALIDATION_ERROR", check_mcp_tool_error=True, recovery="correctable")
        assert exc_info.value.status_code == 400

    def test_mcp_boundary_maps_permission_error_to_permission_denied(self):
        def failing_tool():
            raise PermissionError("access denied")

        with pytest.raises(ToolError) as exc_info:
            with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, "PERMISSION_DENIED", check_mcp_tool_error=True, recovery="correctable")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_async_mcp_boundary_maps_value_error_to_validation_error(self):
        """The async wrapper shares ``_handle_tool_exception``, so it must land identically."""

        async def failing_tool():
            raise ValueError("invalid input shape")

        with pytest.raises(ToolError) as exc_info:
            await with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, "VALIDATION_ERROR", check_mcp_tool_error=True, recovery="correctable")
        assert exc_info.value.status_code == 400

    def test_rest_boundary_maps_value_error_to_400(self):
        """Without the REST ``ValueError`` handler this is a bare 500, unlike MCP and A2A."""
        response = _capabilities_response(ValueError("invalid input shape"))

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "VALIDATION_ERROR", recovery="correctable")

    def test_rest_boundary_maps_permission_error_to_403(self):
        response = _capabilities_response(PermissionError("access denied"))

        assert response.status_code == 403
        assert_envelope_shape(response.json(), "PERMISSION_DENIED", recovery="correctable")

    def test_a2a_boundary_maps_value_error_to_validation_error(self):
        """``_build_failed_skill_result`` is the A2A dispatcher's only failure carrier."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        result = AdCPRequestHandler._build_failed_skill_result("get_products", ValueError("invalid input shape"))

        assert result["success"] is False
        assert result["skill"] == "get_products"
        assert_envelope_shape(result["error_envelope"], "VALIDATION_ERROR", recovery="correctable")

    def test_a2a_boundary_maps_permission_error_to_permission_denied(self):
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        result = AdCPRequestHandler._build_failed_skill_result("get_products", PermissionError("access denied"))

        assert result["success"] is False
        assert_envelope_shape(result["error_envelope"], "PERMISSION_DENIED", recovery="correctable")


# ---------------------------------------------------------------------------
# HTTP status is the one graded value CODE_TABLE does not own
# ---------------------------------------------------------------------------


class TestRestStatusCodeRoundtrip:
    """Each typed class's ``status_code`` must survive the REST boundary.

    ``CODE_TABLE`` now owns the status alongside ``message``, ``recovery`` and
    ``suggestion``, so the expected numbers below are not an independent
    declaration of what each class means — that is graded by
    :class:`TestStatusIsAFunctionOfTheWireCode`. What these rows grade is the
    delivery: the status is a read-only property with no instance state behind
    it, and only driving the exception through the handler stack proves the
    property is what the response is built from.
    """

    @pytest.mark.parametrize(
        ("exc_cls", "expected_status"),
        [
            (AdCPConflictError, 409),
            (AdCPGoneError, 410),
            (AdCPServiceUnavailableError, 503),
            (AdCPRateLimitError, 429),
            # 503, not the 502 this class used to declare: it emits
            # SERVICE_UNAVAILABLE, and the code owns the status.
            (AdCPAdapterError, 503),
        ],
        ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
    )
    def test_status_code_reaches_the_response(self, exc_cls: type[AdCPSalesAgentError], expected_status: int):
        """A new typed subclass is one parametrize row, not one method."""
        response = _capabilities_response(exc_cls())

        assert response.status_code == expected_status
        # Read back through the class rather than a transcribed literal: what is
        # graded is that THIS exception produced the response, not what the
        # pinned table says its code means.
        assert response.json()["errors"][0]["code"] == str(exc_cls._code)

    def test_budget_exhausted_reaches_422(self):
        """422 is carried by several classes; ``AdCPBudgetExhaustedError`` is the
        one whose recovery is ``terminal``, so it also pins that a terminal
        classification does not get downgraded on the way out.
        """
        from src.core.exceptions import AdCPBudgetExhaustedError

        response = _capabilities_response(AdCPBudgetExhaustedError())

        assert response.status_code == 422
        assert_envelope_shape(response.json(), "BUDGET_EXHAUSTED", recovery="terminal")

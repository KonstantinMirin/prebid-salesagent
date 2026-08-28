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
- ``_build_error_code_to_status`` — the derived wire-code → HTTP-status table:
  the "highest status wins" rule for a code two classes declare, and the
  ``INVALID_REQUEST → 400`` seed.
- ``extract_error_info`` on its NON-typed branches — the plain-``ToolError``
  argument shapes, the ``is_error_code`` heuristic that chooses between them,
  and the non-``ToolError`` fallthrough.
- ``_coerce_recovery`` — membership validation of a wire ``recovery`` string.
- ``adcp_error_for``'s type mapping (``ValueError`` → VALIDATION_ERROR / 400,
  ``PermissionError`` → PERMISSION_DENIED / 403) at each of the three
  boundaries that call it.
- ``_translate_to_tool_error``'s plain-``ToolError`` passthrough, which must
  stay ahead of the pre-converted ``typed`` short-circuit.
- The per-class HTTP ``status_code`` roundtrip through REST. ``status_code`` is
  the one graded wire-adjacent value that is NOT a function of the error code —
  ``CODE_TABLE`` does not carry it — so no table-derivation argument covers it.
"""

from __future__ import annotations

import copy
import json
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from src.core.errors.codes import Recovery
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
    _build_error_code_to_status,
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


class TestErrorCodeToStatusTable:
    """``_build_error_code_to_status`` derives the plain-ToolError status map.

    The map used to be hand-maintained and drifted from the class declarations
    it was supposed to mirror. Deriving it removes the drift but introduces a
    question the class declarations alone cannot answer: what happens when two
    classes declare the same wire code with different statuses.
    """

    def test_shared_wire_code_resolves_to_the_highest_declared_status(self):
        """SERVICE_UNAVAILABLE is declared twice — the more restrictive status wins.

        A real collision, not a constructed one: ``AdCPAdapterError`` is a 502
        and ``AdCPServiceUnavailableError`` a 503, and both emit
        SERVICE_UNAVAILABLE. A plain-ToolError fallback carries no context to
        disambiguate them, so the rule is "highest wins".
        """
        assert AdCPAdapterError._code == AdCPServiceUnavailableError._code
        assert AdCPAdapterError._default_status_code == 502
        assert AdCPServiceUnavailableError._default_status_code == 503

        table = _build_error_code_to_status()

        assert table[str(AdCPAdapterError._code)] == 503

    def test_invalid_request_is_seeded_as_a_client_error(self):
        """INVALID_REQUEST — AdCP's generic bad-request code — always has a 4xx entry.

        The seed is what stops a plain ``ToolError("INVALID_REQUEST", ...)`` from
        falling through to the unknown-code 500 and reporting the buyer's own
        malformed request as a server fault.

        The assertion is a 4xx band rather than the literal 400 the seed writes,
        because the seed does not survive the subclass walk: ``SimulationError``
        (``src/core/strategy.py``) declares INVALID_REQUEST while inheriting
        ``AdCPNotFoundError``'s 404, so "highest status wins" raises the entry to
        404 — and only once ``src.core.strategy`` has been imported, which makes
        the resolved value depend on the import set. Pinning 400 here would grade
        that accident rather than the seed. See the report accompanying this file.
        """
        status = _build_error_code_to_status()["INVALID_REQUEST"]

        assert 400 <= status < 500, f"INVALID_REQUEST resolved to {status}, not a client-error status"

    def test_every_concrete_subclass_that_declares_a_code_reaches_the_table(self):
        """Drift guard: the table is DERIVED from the class declarations, not hand-kept.

        The hand-maintained version of this table drifted — it said
        ``AUTH_REQUIRED -> 401`` while the class emitting that code carried 403,
        so a plain-ToolError raise from authorization code surfaced as 401. A
        derivation that silently skips a class puts that drift straight back, so
        every concrete subclass declaring ``_code`` must be present, at a status
        no LOWER than the one it declares: the "highest status wins" merge may
        only raise an entry, never lower it.

        The merge is also why the table is not a pure function of the classes it
        walks. ``SimulationError`` (``src/core/strategy.py``) declares
        INVALID_REQUEST while inheriting ``AdCPNotFoundError``'s 404, so the
        seeded 400 resolves to 404 — but only once ``src.core.strategy`` has been
        imported, which makes the value depend on the import set. This guard is
        where a class joining, leaving, or re-coding that walk becomes visible.
        """
        table = _build_error_code_to_status()
        declared = [cls for cls in AdCPSalesAgentError.iter_concrete_subclasses() if getattr(cls, "_code", None)]

        # Non-vacuity: an empty walk would satisfy every assertion below.
        assert declared, "no concrete AdCPSalesAgentError subclass declares a code — the walk is vacuous"

        drift = [
            f"  {cls.__name__}: _code={str(cls._code)!r} declares {cls._default_status_code}, "
            f"table says {table.get(cls._code)!r}"
            for cls in declared
            if table.get(cls._code, 0) < cls._default_status_code
        ]
        assert not drift, (
            "concrete AdCPSalesAgentError subclasses are missing from — or understated in — the derived "
            "status table, so the plain-ToolError fallback would mis-classify their HTTP status:\n" + "\n".join(drift)
        )

    def test_each_call_returns_a_fresh_table(self):
        """The derivation is a function, not a constant wearing a function's name.

        Re-walking ``__subclasses__()`` per call is what lets a subclass defined
        in a module imported later reach the table at all. Returning a shared
        dict by reference would also let one caller's mutation reach every other
        caller of a table that decides HTTP status.
        """
        first = _build_error_code_to_status()
        second = _build_error_code_to_status()

        assert first == second
        assert first is not second

        first["INVALID_REQUEST"] = 599
        assert _build_error_code_to_status()["INVALID_REQUEST"] != 599


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

    ``message``, ``recovery`` and ``suggestion`` are all functions of the error
    code, resolved from ``CODE_TABLE`` at read time, so asserting them per class
    only re-reads the pinned table. ``status_code`` is not in that table — it is
    a per-class transport choice — so the only thing that proves it reaches the
    wire is driving the exception through the handler stack and reading the
    response.
    """

    @pytest.mark.parametrize(
        ("exc_cls", "expected_status"),
        [
            (AdCPConflictError, 409),
            (AdCPGoneError, 410),
            (AdCPServiceUnavailableError, 503),
            (AdCPRateLimitError, 429),
            (AdCPAdapterError, 502),
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

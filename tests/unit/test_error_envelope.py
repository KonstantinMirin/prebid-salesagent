"""Error-response behavior that has no other grader in this suite.

A failure is an ``AdcpErrorResponse`` (``src/core/schemas/_base.py``), built once by
``AdcpErrorResponse.of`` and serialized by ``to_wire``. Most of what that produces is graded
where it matters most -- on the wire, by BDD, through
``tests/helpers/envelope_assertions.py::assert_envelope_shape`` across mcp / a2a / rest /
e2e_rest. Everything that helper already grades is deliberately absent here rather than
restated: two-layer presence, code equality across the layers, message and recovery on both
layers, ``field``, ``details``, ``issues`` and ``suggestion``.

Anything asserting an authored ``message``, ``recovery`` or ``suggestion`` is absent too:
all three are read-only properties over ``CODE_TABLE`` (``src/core/errors/codes.py``, built
at import from the pinned adcp SDK's enums), so pinning them per raise site would copy the
pinned table into a second place instead of grading production.

What remains is behavior nothing else reaches:

- A ``context`` the buyer sent that cannot be modelled as a ``ContextObject`` is dropped
  from the rejection, never raised over. The echo itself, on every outcome and transport,
  is graded by ``tests/bdd/features/local-context-echo-every-outcome.feature``.
- Byte-identical bodies across REST and A2A. BDD grades each transport against the same
  expected code and recovery, but never asserts the two transports emit the same bytes, so
  a field appearing on one boundary only would pass every scenario.
- The HTTP status REST answers, read off the response as ``http_status``.
- The per-class HTTP ``status_code`` for the four typed subclasses below.
  ``tests/unit/test_adcp_exceptions.py::TestPerClassHttpStatus`` pins a disjoint set of
  classes -- the two lists must not overlap.
"""

from __future__ import annotations

import asyncio
import json
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import (
    AdCPBudgetTooLowError,
    AdCPCapabilityNotSupportedError,
    AdCPMediaBuyNotFoundError,
    AdCPPackageNotFoundError,
    AdCPSalesAgentError,
    AdCPValidationError,
)

_TOOL = "get_adcp_capabilities"


def _capabilities_response(side_effect: Exception):
    """Drive ``POST /api/v1/capabilities`` with ``side_effect`` raised inside the tool.

    The route is the thinnest endpoint in the app -- one call, one serialization -- so what
    it grades is the REST route's own failure path, not the capabilities tool.
    """
    from starlette.testclient import TestClient

    from src.app import app
    from tests.helpers.boundary_identity import resolved_as
    from tests.helpers.capture_wrapper_req import registry_impl

    # The boundary resolves identity from the database, and the path under test never looks
    # at it. One resolver means one patch point.
    with resolved_as(), registry_impl(_TOOL, AsyncMock(side_effect=side_effect)):
        client = TestClient(app, raise_server_exceptions=False)
        return client.post("/api/v1/capabilities", json={})


def _a2a_skill_body(side_effect: Exception) -> dict:
    """The DataPart body A2A's dispatcher hands the Task for the same failure."""
    from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
    from src.core.auth_context import AuthContext
    from tests.helpers.boundary_identity import resolved_as
    from tests.helpers.capture_wrapper_req import registry_impl

    with resolved_as(), registry_impl(_TOOL, AsyncMock(side_effect=side_effect)):
        credential = AuthContext(headers=MappingProxyType({}))
        return asyncio.run(AdCPRequestHandler()._dispatch_skill(_TOOL, {}, credential))


class TestRestStatusIsTheCodesStatus:
    """The HTTP status REST answers is the failing code's own, read from ``CODE_TABLE``.

    Graded on the WIRE -- a real route, a real exception raised inside the tool, the status
    read off the response -- rather than by calling the property by name, so restructuring
    how REST decides does not force an edit here. The expected value is read from
    ``CODE_TABLE`` rather than written as a literal, because the table is the single
    declaration of a code's status: what is graded is that the value SURVIVES to the
    response, not what the table says it is.
    """

    @pytest.mark.parametrize(
        "exc_cls",
        [AdCPMediaBuyNotFoundError, AdCPValidationError, AdCPBudgetTooLowError, AdCPCapabilityNotSupportedError],
    )
    def test_status_survives_to_the_response(self, exc_cls: type[AdCPSalesAgentError]) -> None:
        from src.core.errors.codes import CODE_TABLE

        exc = exc_cls()
        response = _capabilities_response(exc)

        assert response.status_code == CODE_TABLE[exc.error_code].status, (
            f"{exc_cls.__name__} ({exc.error_code}) reached the buyer as HTTP {response.status_code}, "
            f"but CODE_TABLE declares {CODE_TABLE[exc.error_code].status}"
        )
        assert response.json()["adcp_error"]["code"] == exc.error_code


class TestUnmodellableContextIsDropped:
    """A ``context`` that is not an object is dropped from the rejection, never raised over.

    ``validated_request`` reads the echo off the raw payload for a schema rejection. A value
    the DTO refuses AND ``ContextObject`` cannot model has nothing to echo, so the rejection
    goes out without the key and without a second failure shadowing the first.
    """

    def test_rejection_carries_no_context_key(self) -> None:
        from starlette.testclient import TestClient

        from src.app import app
        from tests.helpers.boundary_identity import resolved_as

        with resolved_as():
            response = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/capabilities", json={"context": "not-an-object"}
            )

        assert response.status_code == 400
        body = response.json()
        assert body["adcp_error"]["code"] == "INVALID_REQUEST"
        assert "context" not in body


class TestWireBytesIdenticalAcrossTransports:
    """REST and A2A emit the SAME BYTES for the same failure.

    Both transports serialize the response the boundary built and add only their own
    marker. BDD grades each transport against the same expected code and recovery, but
    never compares the two transports to each other, so one boundary growing an extra field,
    or dropping one, passes every scenario. This drives the real REST route and the real A2A
    skill dispatcher for one failing tool, then compares ``json.dumps(..., sort_keys=True)``
    of both bodies.
    """

    @pytest.mark.parametrize(
        "exc",
        [
            AdCPValidationError(field="budget"),
            AdCPMediaBuyNotFoundError(),
        ],
        ids=lambda exc: type(exc).__name__,
    )
    def test_body_matches_across_transports(self, exc: AdCPSalesAgentError):
        rest_bytes = json.dumps(_capabilities_response(exc).json(), sort_keys=True)
        a2a_bytes = json.dumps(_a2a_skill_body(exc), sort_keys=True)

        assert rest_bytes == a2a_bytes, (
            f"REST and A2A bodies drifted apart for {type(exc).__name__}:\n  REST: {rest_bytes}\n  A2A : {a2a_bytes}"
        )


class TestTypedSubclassHttpStatus:
    """The four typed subclasses whose HTTP status nothing else pins.

    ``status_code`` is a function of the class's code through ``CODE_TABLE``, and REST
    answers it through ``AdcpErrorResponse.http_status``. The codes these classes carry are
    graded by BDD; only the status is unowned.

    The class list is disjoint from
    ``tests/unit/test_adcp_exceptions.py::TestPerClassHttpStatus`` on purpose -- a class
    belongs to exactly one of the two tables.
    """

    @pytest.mark.parametrize(
        ("exc_cls", "expected_status"),
        [
            (AdCPMediaBuyNotFoundError, 404),
            (AdCPPackageNotFoundError, 404),
            (AdCPBudgetTooLowError, 422),
            (AdCPCapabilityNotSupportedError, 422),
        ],
        ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
    )
    def test_class_declares_its_status(self, exc_cls: type[AdCPSalesAgentError], expected_status: int):
        assert exc_cls().status_code == expected_status

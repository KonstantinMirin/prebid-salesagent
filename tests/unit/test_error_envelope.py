"""Envelope-builder behavior that has no other grader in this suite.

``build_two_layer_error_envelope`` is the single serializer every transport
boundary calls (``src/app.py``'s handler stack, the A2A dispatcher's failed-skill
artifact, ``ContextManager.audit_workflow_step_failure``), so most of its output
is graded where it matters most — on the wire, by BDD, through
``tests/helpers/envelope_assertions.py::assert_envelope_shape`` across mcp / a2a
/ rest / e2e_rest. Everything that helper already grades is deliberately absent
here rather than restated: two-layer presence, code equality across the layers,
message and recovery on both layers, ``field``, ``details``, ``issues`` and
``suggestion``.

Gone with the symbols they exercised: the wire-translation suite
(``ERROR_CODE_MAPPING``, ``translate_error_code``) — codes now reach the buyer
verbatim because the AdCP vocabulary is open — and the three-serializer
consistency and REST/A2A reconstruction suites (``to_dict``, ``to_adcp_error``,
``parse_rest_error``, ``_envelope_to_adcp_error``), all deleted from src/ and
from the harness. Anything asserting an authored ``message``, ``recovery`` or
``suggestion`` is gone too: all three are read-only properties over
``CODE_TABLE`` (``src/core/errors/codes.py``, built at import from the pinned
adcp SDK's enums), so pinning them per raise site would copy the pinned table
into a second place instead of grading production.

What remains is the builder behavior nothing else reaches:

- ``_serialize_context``'s three branches. The function has exactly one caller
  (this builder) and no other test; its fail-open branch is the reason the
  boundary translator cannot shadow the buyer's original error.
- The ``context`` echo AT THE BUILDER, including the omit-when-absent rule.
  ``tests/unit/test_adcp_exceptions.py::TestErrorEnvelopeContextEcho`` grades
  the same echo one layer up — that the FastAPI handler doesn't lose the key on
  the way out — and names this file as the builder-level grader.
- Byte-identical envelopes across REST and A2A. BDD grades each transport
  against the same expected code and recovery, but never asserts the two
  transports emit the same bytes, so a field appearing on one boundary only
  would pass every scenario.
- The per-class HTTP ``status_code`` for the four typed subclasses below.
  ``CODE_TABLE`` does not carry status, so no table-derivation argument covers
  it; the classes' CODES are graded by BDD, only the status is orphaned.
  ``tests/unit/test_adcp_exceptions.py::TestPerClassHttpStatus`` pins a
  disjoint set of classes — the two lists must not overlap.
"""

from __future__ import annotations

import json
import logging

import pytest

from src.core.exceptions import (
    AdCPBudgetTooLowError,
    AdCPCapabilityNotSupportedError,
    AdCPMediaBuyNotFoundError,
    AdCPPackageNotFoundError,
    AdCPSalesAgentError,
    AdCPValidationError,
    build_two_layer_error_envelope,
)

# The REST driver is IMPORTED, not re-declared: ``GET /api/v1/capabilities`` is
# the thinnest route in the app and one helper already drives it with the tool
# patched and the identity dependency overridden. A second copy here would be
# the same logical operation with the variables renamed.
from tests.unit.test_error_boundary_translation import _capabilities_response


class TestContextEcho:
    """``exc.context`` is echoed on the ERROR envelope, and omitted when absent.

    Normative since AdCP spec 3.0.0 (``error-handling.mdx``): buyer agents
    correlate a failure back to the request that produced it through this key.
    Graded here on the builder — ``tests/unit/test_adcp_exceptions.py``
    grades that the FastAPI handler carries the key through to the response
    body, which is the distinct obligation.
    """

    def test_context_object_is_echoed_with_exclude_none(self):
        """A ``ContextObject`` is dumped with ``exclude_none=True``.

        ``_serialize_context`` calls ``model_dump(mode="json", exclude_none=True)``
        so the envelope carries only populated fields, matching the spec's
        emit-only-populated-fields norm. An unset optional must not reach the
        wire as ``null``.
        """
        from adcp.types import ContextObject

        exc = AdCPMediaBuyNotFoundError(context=ContextObject(correlation_id="abc-123"))

        envelope = build_two_layer_error_envelope(exc)

        assert envelope["context"]["correlation_id"] == "abc-123"
        assert all(value is not None for value in envelope["context"].values())

    def test_context_omitted_when_none(self):
        """No context on the exception means no ``context`` key at all — not ``null``."""
        envelope = build_two_layer_error_envelope(AdCPMediaBuyNotFoundError())

        assert "context" not in envelope

    def test_dict_context_is_shallow_copied(self):
        """Mutating the source dict after the build must not mutate the envelope.

        ``_serialize_context`` copies a dict context rather than aliasing it, so
        an exception held across more than one serialization cannot leak a
        mutation from one envelope into another.
        """
        source_context = {"correlation_id": "orig"}
        exc = AdCPMediaBuyNotFoundError(context=source_context)

        envelope = build_two_layer_error_envelope(exc)
        source_context["correlation_id"] = "mutated"
        source_context["new_key"] = "added"

        assert envelope["context"] == {"correlation_id": "orig"}


class TestMalformedContextFailsOpen:
    """A context that is neither a dict nor a ``BaseModel`` is logged and dropped.

    The builder runs INSIDE exception handlers. Raising here — the ``TypeError``
    a strict serializer would emit — would shadow the buyer's original error and
    leave the boundary translator with no envelope to send at all. So the
    malformed value drops to ``None`` and the rest of the envelope is emitted
    intact; the diagnostic goes to the server log, which is the only place it
    can go without inventing buyer-facing text.
    """

    def test_non_model_context_is_dropped_not_raised(self, caplog: pytest.LogCaptureFixture):
        exc = AdCPValidationError(context=object())

        with caplog.at_level(logging.WARNING, logger="src.core.exceptions"):
            envelope = build_two_layer_error_envelope(exc)  # must not raise

        assert "context" not in envelope, "malformed context must be dropped, not serialized"
        # The rest of the envelope survives — dropping the context must not cost
        # the buyer the error itself.
        assert envelope["adcp_error"]["code"] == "VALIDATION_ERROR"
        assert envelope["errors"][0]["code"] == "VALIDATION_ERROR"
        assert "dropping context" in caplog.text, "the drop must leave a server-side breadcrumb"


class TestWireBytesIdenticalAcrossTransports:
    """REST and A2A emit the SAME BYTES for the same exception.

    Both boundaries claim to delegate to one builder. BDD grades each transport
    against the same expected code and recovery, but never compares the two
    transports to each other, so one boundary growing an extra field, or
    dropping one, passes every scenario. This drives the real REST handler stack
    (``TestClient`` -> ``adcp_error_handler``) and the real A2A failed-skill
    builder used by the dispatcher, then compares
    ``json.dumps(..., sort_keys=True)`` of both envelopes.
    """

    @staticmethod
    def _rest_envelope_bytes(exc: AdCPSalesAgentError) -> str:
        """The wire body a REST buyer receives, serialized with sorted keys."""
        return json.dumps(_capabilities_response(exc).json(), sort_keys=True)

    @staticmethod
    def _a2a_envelope_bytes(exc: AdCPSalesAgentError) -> str:
        """The envelope the A2A artifact DataPart carries, serialized the same way."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        result = AdCPRequestHandler._build_failed_skill_result("test_skill", exc)
        return json.dumps(result["error_envelope"], sort_keys=True)

    @pytest.mark.parametrize(
        "exc",
        [
            AdCPValidationError(field="budget"),
            AdCPMediaBuyNotFoundError(),
        ],
        ids=lambda exc: type(exc).__name__,
    )
    def test_envelope_matches_across_transports(self, exc: AdCPSalesAgentError):
        rest_bytes = self._rest_envelope_bytes(exc)
        a2a_bytes = self._a2a_envelope_bytes(exc)

        assert rest_bytes == a2a_bytes, (
            f"REST and A2A envelopes drifted apart for {type(exc).__name__}:\n  REST: {rest_bytes}\n  A2A : {a2a_bytes}"
        )


class TestTypedSubclassHttpStatus:
    """The four typed subclasses whose HTTP status nothing else pins.

    Status is not a function of the error code — ``CODE_TABLE`` classifies
    message, recovery and suggestion and stops there — so the declaration is
    real behavior with a real reader: ``src/app.py``'s handler stack turns
    ``exc.status_code`` into the response status. The codes these classes carry
    are graded by BDD; only the status is unowned.

    The class list is disjoint from
    ``tests/unit/test_adcp_exceptions.py::TestPerClassHttpStatus`` on purpose —
    a class belongs to exactly one of the two tables.
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

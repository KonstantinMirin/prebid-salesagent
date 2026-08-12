"""Generic Then steps that grade a response against the pinned AdCP schema.

``the response should be schema-valid against <file>`` lived at module scope in
tests/bdd/test_uc018_list_creatives.py, so only UC-018 could use it — which is why
the UC-019 scenario asserting the same thing went dormant. It overrides no generic
text, so unlike the eight deliberately module-scoped UC-019 steps there is nothing
to keep it local.

Prefers the REAL WIRE. When a dispatcher stashed ``ctx["wire_response"]`` (REST's
HTTP body, MCP's structured_content, A2A's artifact DataPart) that is the document
a buyer actually receives, and validating it catches transport-framing regressions
that a re-serialized typed payload cannot. IMPL has no wire by definition, so it
falls back to the production serializer.
"""

from __future__ import annotations

from typing import Any

from pytest_bdd import parsers, then

from tests.bdd.steps._outcome_helpers import _require_response
from tests.helpers.pinned_schema import validate_against_pinned_schema


def serialized_response(ctx: dict) -> dict[str, Any]:
    """The response document to grade: the real wire when there is one.

    ``exclude_none`` on the fallback matches the buyer-visible wire and the AdCP
    contract, which types optional fields only when present — a literal ``null`` is
    not a valid array/object/boolean there.
    """
    wire = ctx.get("wire_response")
    if wire is not None:
        return wire
    return _require_response(ctx).model_dump(mode="json", exclude_none=True)


@then(parsers.parse("the response should be schema-valid against {schema_file}"))
def then_response_schema_valid(ctx: dict, schema_file: str) -> None:
    """Assert the response validates against the pinned AdCP schema."""
    validate_against_pinned_schema(schema_file, serialized_response(ctx))


@then("the response envelope carries status completed")
def then_envelope_status_completed(ctx: dict) -> None:
    """Assert the protocol envelope's spec-required ``status`` is on the response.

    Scoped to the envelope rather than full-document validity on purpose: this is
    the obligation GH #1900 owns, and it is gradeable on any response whose schema
    composes core/protocol-envelope.json, independently of whether that response's
    domain body is complete.
    """
    document = serialized_response(ctx)
    assert "status" in document, (
        f"AdCP 3.1.1 core/protocol-envelope.json marks 'status' REQUIRED on every task "
        f"response envelope, but the response carries only {sorted(document)}"
    )
    assert document["status"] == "completed", (
        f"a synchronously-completed task must report status 'completed', got {document['status']!r}"
    )

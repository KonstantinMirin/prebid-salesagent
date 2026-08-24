"""Unified AdCP two-layer error envelope assertion.

Single helper for the wire shape every transport boundary must emit::

    {
        "adcp_error": {"code": "...", "message": "...", "recovery": "..."},
        "errors":     [{"code": "...", "message": "...", "recovery": "..."}],
        "context":    {...},   # optional
    }

Replaces the per-boundary helpers (``_assert_two_layer_envelope``,
``_assert_mcp_envelope``, ``_assert_a2a_envelope``, ``_assert_rest_envelope``)
that all verified the same shape with diverging signatures. A spec change to
the envelope now requires updating exactly one helper.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def locate_envelope_error(target: Any) -> dict[str, Any] | None:
    """The payload-layer error object (``errors[0]``) — the protocol position.

    THE one locator: every sanctioned read of an error region (the ``field`` /
    ``details`` kwargs below, and the harness readers on ``TransportResult``)
    resolves through it, so "where does the spec put this?" is answered in
    exactly one place. ``errors[0]`` rather than the envelope-level
    ``adcp_error`` mirror because error.json defines the per-error fields
    (``field``, ``details``, ``suggestion``) on the payload-layer object.

    Tolerant by design — returns ``None`` when there is no envelope at all —
    because the tolerant step-layer readers built on it must keep their
    ``| None`` contract. Strictness belongs to the callers that assert.
    """
    if target is None:
        return None
    body = target.envelope if hasattr(target, "envelope") else target
    if not isinstance(body, dict):
        return None
    errors = body.get("errors")
    if not errors:
        return None
    first = errors[0]
    return first if isinstance(first, dict) else None


def assert_no_raw_validation_leak(message: str) -> None:
    """Assert a buyer-facing validation message omits raw Pydantic internals."""
    assert "input_value" not in message, f"raw Pydantic input leaked into validation message: {message!r}"
    assert "errors.pydantic.dev" not in message, f"Pydantic documentation URL leaked into message: {message!r}"


def _assert_marker_absent(rendered_region: Any, marker: str, *, region_label: str) -> None:
    """Core of the wire-safety marker scan: ``marker`` must not appear in a region.

    Shared by the two carriers the spec treats as equal — the two-layer ERROR
    envelope and a SUCCESS payload's ``errors[]`` (error-compliance.yaml's
    ``validate_error_shape`` grades a typed error code "via either adcp_error
    (envelope) or errors[] (payload)"). One scan body, two entry points, so a
    third carrier never becomes a third copy.
    """
    rendered = str(rendered_region)
    assert marker not in rendered, f"marker {marker!r} leaked into {region_label}: {rendered!r}"


def assert_no_marker_in_envelope(envelope: Mapping[str, Any] | None, marker: str) -> None:
    """Assert ``marker`` is absent from the FULL wire error envelope.

    Sibling to :func:`assert_no_raw_validation_leak`, for the wire-safety
    obligation: unlike a positive match scoped to ``errors[0].message``,
    this scans
    ``str(envelope)`` so a leak buried anywhere in the envelope
    (``adcp_error.message``, ``errors[0].details``, ``suggestion``, ``context``)
    fails the check — mirroring the exemplar
    ``tests/integration/test_prkv8_untyped_exception_wire_leak.py::_assert_no_leak``,
    which scans the WHOLE envelope rather than a single field.
    """
    assert envelope is not None, f"no wire envelope captured to check for marker {marker!r}"
    _assert_marker_absent(envelope, marker, region_label="wire error envelope")


def assert_no_marker_in_payload_errors(wire_response: Mapping[str, Any] | None, marker: str) -> None:
    """Assert ``marker`` is absent from a SUCCESS payload's ``errors[]``.

    The success-path counterpart to :func:`assert_no_marker_in_envelope`. A tool
    that degrades gracefully (``list_creative_formats`` with one unreachable
    agent) returns HTTP success with per-agent failures reported in
    ``errors[]`` — so ``result.is_error`` is False and ``wire_error_envelope``
    is ``None``, which makes the envelope helpers either fail on their
    ``not None`` guard or pass vacuously. That carrier is still buyer-facing:
    AdCP 3.1.1 ``transport-errors.mdx`` § Security Considerations opens with
    "Every field is client-facing", and the storyboard gives the two carriers
    equal status.

    Asserts ``errors[]`` is present and NON-EMPTY first, so the scan cannot
    pass vacuously against a response that carried no errors at all.
    """
    assert wire_response is not None, f"no wire response captured to check for marker {marker!r}"
    errors = wire_response.get("errors")
    assert errors, f"expected a non-empty payload-level errors[] to scan for {marker!r}, got {wire_response!r}"
    _assert_marker_absent(errors, marker, region_label="payload errors[]")


def assert_envelope_shape(
    target: Any,
    code: str,
    *,
    recovery: str,
    field: str | None = None,
    details: Mapping[str, Any] | None = None,
    retry_after: int | None = None,
    check_mcp_tool_error: bool = False,
) -> None:
    """Assert the AdCP spec two-layer error envelope shape.

    Args:
        target: The envelope under test. Accepts either:
                - a ``dict`` (REST JSON body, A2A ``error.data``, raw envelope),
                - an ``AdCPToolError`` (MCP boundary) — its ``.envelope`` attr
                  is read transparently.
        code: Expected wire error code; must match BOTH ``adcp_error.code``
                and ``errors[0].code``. Two-layer invariant: both layers
                always agree.
        recovery: Required. Both ``adcp_error.recovery`` and
                ``errors[0].recovery`` must equal this hint. Pinning recovery
                is mandatory: it is the buyer-facing retry semantics
                (``correctable`` / ``transient`` / ``terminal``) and a silent
                drift between a typed exception's recovery and the wire is
                exactly the regression this helper exists to catch.
        field: If provided, ``errors[0].field`` must equal it exactly — the
                error.json ``field`` pointer naming WHICH request field was
                rejected. Asserted at the protocol top level only: a copy buried
                in the free-form ``details`` dict is not at the protocol position
                and does not satisfy the contract (same burial rule as
                ``extract_wire_suggestion``). This lives here, on the one envelope
                primitive, rather than as a second free-function error surface —
                a parallel error-assertion mechanism is exactly what step
                definitions must not have to choose between.
        details: If provided, each key must be present in ``errors[0].details``
                with an equal value — a SUBSET check, never dict equality:
                ``details`` is an OPEN object in core/error.json (the error
                object declares ``additionalProperties: true``), so production
                may carry diagnostic keys no oracle names. Asserted at the
                protocol position ``errors[0].details`` only — a block that
                lives on the envelope-level mirror alone, or a value nested one
                level deeper, does not satisfy it (the same burial rule as
                ``field``). Lives here for the same reason ``field`` does: one
                sanctioned error surface, so a step never has to choose a
                mechanism. Non-binary oracles (non-empty, regex-per-entry,
                membership) use ``TransportResult.wire_error_details`` instead,
                which asserts the code before handing the block over.
        check_mcp_tool_error: If ``True``, additionally assert that ``target``
                is an ``AdCPToolError`` instance before reading its envelope.
                MCP-boundary call sites use this to pin the exception type as
                well as the wire shape — a plain ``ToolError`` would still
                expose ``.envelope`` via duck-typing but would not be the
                typed MCP-boundary exception the test claims to inspect.
    """
    if check_mcp_tool_error:
        from src.core.tool_error_logging import AdCPToolError

        assert isinstance(target, AdCPToolError), f"expected AdCPToolError, got {type(target).__name__}"

    body = target.envelope if hasattr(target, "envelope") else target

    assert isinstance(body, dict), f"envelope target must resolve to dict, got {type(body).__name__}"
    assert "adcp_error" in body, f"missing envelope-level adcp_error: {body}"
    assert "errors" in body, f"missing payload-level errors[]: {body}"
    assert body["errors"], "errors[] must contain at least one entry"

    # Through the locator, not a second body["errors"][0] of its own: this function is
    # where "the payload-layer error object lives at errors[0]" is decided, so reading
    # it any other way here would be the primitive contradicting itself.
    error = locate_envelope_error(body)
    assert error is not None, f"errors[0] is not an error object: {body}"

    assert body["adcp_error"]["code"] == code, f"adcp_error.code={body['adcp_error']['code']!r}, expected {code!r}"
    assert error["code"] == code, f"errors[0].code={error['code']!r}, expected {code!r}"

    assert body["adcp_error"].get("recovery") == recovery, (
        f"adcp_error.recovery={body['adcp_error'].get('recovery')!r}, expected {recovery!r}"
    )
    assert error.get("recovery") == recovery, f"errors[0].recovery={error.get('recovery')!r}, expected {recovery!r}"

    if field is not None:
        actual_field = error.get("field")
        assert actual_field == field, f"errors[0].field={actual_field!r}, expected {field!r}"

    if retry_after is not None:
        # Mirrors `recovery` in being checked on BOTH layers. Until this existed
        # there was no way to grade retry_after through the sanctioned surface, so
        # the one test that needs it hand-indexed the envelope
        # (`wire_error_envelope["adcp_error"].get("retry_after")`) -- an off-path
        # read that existed because the helper could not express the fact, not
        # because the author reached past it.
        assert body["adcp_error"].get("retry_after") == retry_after, (
            f"adcp_error.retry_after={body['adcp_error'].get('retry_after')!r}, expected {retry_after!r}"
        )
        assert error.get("retry_after") == retry_after, (
            f"errors[0].retry_after={error.get('retry_after')!r}, expected {retry_after!r}"
        )

    if details is not None:
        actual_details = error.get("details")
        assert isinstance(actual_details, dict), (
            f"errors[0].details={actual_details!r} is not an object at the protocol position; "
            f"expected it to carry {dict(details)!r}"
        )
        for key, expected in details.items():
            assert key in actual_details, f"errors[0].details is missing {key!r}: {actual_details!r}"
            assert actual_details[key] == expected, (
                f"errors[0].details[{key!r}]={actual_details[key]!r}, expected {expected!r}"
            )

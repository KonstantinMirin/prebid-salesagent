"""Outcome-based assertion helpers for E2E transport compatibility.

These helpers verify outcomes through the harness (which uses repositories
and the correctly-bound DB session), making assertions work across all
transports including E2E.

No raw session access. No db_session(ctx). The harness owns the session,
the repository owns the query, the helper owns the assertion.
"""

from __future__ import annotations

from typing import Any


class _WireMissing:
    """Type of :data:`WIRE_MISSING` — exists only to give it a readable repr."""

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return "<absent from wire>"


#: Sentinel distinguishing "the path is not on the wire at all" from "the path is
#: present and carries a JSON null". The two are different contract violations and
#: must never collapse: an unset optional object is ABSENT on a conformant wire, so
#: a serialized ``null`` is a schema-invalid serialization, not an absence.
WIRE_MISSING = _WireMissing()


def _wire_body(ctx: dict) -> dict:
    """The serialized success-path wire body, behind the loud guard.

    Every BDD transport (REST/A2A/MCP and the e2e variants) exposes the real
    success-path wire dict via ``ctx["wire_response"]``. There is no other kind:
    a missing wire is always a defect in the env, so this raises rather than
    falling back.

    It used to serialize the typed payload through ``model_dump`` when the
    transport was an explicit no-wire IMPL. That fallback turned a wire assertion
    into a serializer round-trip, and the pseudo-transport it served is deleted —
    so the branch, and the "is the transport unset or deliberately no-wire?"
    question it forced on every caller, are gone with it (GH #1744 was the
    narrower fix for the same hazard).

    When the dispatch stashed a ``TransportResult`` it delegates to that object's
    :meth:`require_wire`, so the step definitions and the integration tests share
    one guard rather than two copies free to drift.

    Sole guard implementation for :func:`wire_field`, :func:`wire_dict` and
    :func:`wire_absent` — three copies of it would be exactly the duplication the
    canonical-helper rule exists to prevent.

    A success-path helper reached on a scenario that actually ERRORED says so, and
    names the error. Without this the transport guard below would fire first and
    report "env does not stash success-path wire" — blaming the harness for what is
    really a failed request, which is the single most misleading diagnostic these
    helpers can emit.
    """
    result = ctx.get("result")
    if result is not None:
        # The guarded read lives on TransportResult, which is the object that HOLDS
        # the wire (origin/main). One implementation, so a step definition cannot
        # drift from an integration test asserting the same thing; it distinguishes
        # the same two failures this helper does — an error result never had a
        # success body, and a success result with no stashed body means the dispatch
        # bypassed the real pipeline.
        return result.require_wire()
    wire = ctx.get("wire_response")
    error = ctx.get("error")
    if wire is None and error is not None and ctx.get("response") is None:
        raise AssertionError(f"expected a success response, got error: {error!r}")
    transport = ctx.get("transport")
    if wire is None:
        # No serializer fallback any more. It existed for an explicit IMPL
        # pseudo-transport (no wire), which is deleted: every BDD scenario now
        # runs on a real wire, so a missing wire is a defect in the env, never a
        # legitimate no-wire case to serialize around.
        raise AssertionError(
            f"{transport}: wire_response missing — the env does not stash success-path "
            "wire. Every BDD transport is a real wire; there is no no-wire fallback."
        )
    return wire


def _dig(doc: Any, path: str) -> Any:
    """Walk a dotted path through nested JSON objects, or :data:`WIRE_MISSING`.

    The shared resolver behind :func:`wire_lookup` (whole-body reads) and
    :func:`_locate_entry` (per-entry matches) — one dotted-path convention across
    every wire helper, defined once.
    """
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return WIRE_MISSING
        cur = cur[part]
    return cur


def wire_lookup(ctx: dict, path: str) -> Any:
    """Resolve a dotted path on the success-path wire, or :data:`WIRE_MISSING` if absent.

    ``"a"`` reads a top-level key; ``"a.b.c"`` walks nested objects. A hop through a
    non-dict (e.g. a list or a scalar) counts as an absence rather than raising.

    This is the shared resolver behind :func:`wire_field` / :func:`wire_dict` /
    :func:`wire_absent`, exposed for the genuinely TRI-STATE oracle — one whose
    contract is "absent, or present with this value" (an outline column grading
    ``absent or false``; a conditional Then that only grades a block when the seller
    emits it). It ASSERTS NOTHING, so it is a primitive, not a competing assertion
    surface: whenever the oracle is binary, reach for wire_field/wire_absent instead,
    and never rebuild a private dotted-path resolver on top of this one.
    """
    return _dig(_wire_body(ctx), path)


def wire_field(ctx: dict, field: str) -> Any:
    """Return a success-response field, by dotted path, as the buyer sees it on the wire.

    ``field`` is a dotted path (``"media_buy.features.sandbox"``), of which a bare
    top-level key is the one-segment case.

    DUAL assert — the path must be both present AND non-null:

    - **absent** fails, naming the top-level keys actually on the wire;
    - **present but JSON null** fails too. These are optional object/array fields
      whose schemas do not admit ``null``, so a null on the wire is a serialization
      defect, not a populated section (observed on MCP ``structured_content``, which
      serializes unset ``None`` fields; #1592). Downgrading this to a presence-only
      check would silently reintroduce the vacuous-pass class this helper exists to
      catch — see :func:`wire_absent` for the symmetric rule.
    """
    value = wire_lookup(ctx, field)
    assert value is not WIRE_MISSING, f"{field!r} absent from wire response (top-level keys: {sorted(_wire_body(ctx))})"
    assert value is not None, f"{field!r} is JSON null on the wire — schema-invalid serialization of an unset field"
    return value


def wire_dict(ctx: dict, path: str | None = None) -> dict:
    """Return the success-path wire body — the whole envelope, or the object at *path*.

    The dict analogue of :func:`wire_field` — use when an oracle must test key
    PRESENCE/ABSENCE (e.g. an optional field) rather than read one known field.
    With ``path``, resolves the same dotted path :func:`wire_field` does (same
    absent/null dual assert) and additionally pins that the resolved value IS a
    JSON object, so a caller that goes on to index it cannot fail with a confusing
    ``TypeError`` on a scalar. Shares the same loud guard on a non-stashing env.
    """
    doc = _wire_body(ctx)
    if path is None:
        return doc
    value = wire_field(ctx, path)
    assert isinstance(value, dict), f"{path!r} is not a JSON object on the wire: {value!r}"
    return value


def _locate_entry(ctx: dict, collection: str, index: int | None, match: dict[str, Any]) -> dict:
    """The one locator for a per-entry read inside a SUCCESS envelope.

    Sole implementation behind :func:`wire_entry` and :func:`wire_entry_errors` —
    two copies of the "find the row, or say what rows there were" logic is exactly
    the duplication the canonical-helper rule exists to prevent.

    Strict on every miss, and the failure NAMES THE ENTRIES ACTUALLY PRESENT: a
    bare "no match" sends the reader to the harness, while showing what the wire
    did carry makes an off-by-one identifier or an unexpected partial-failure row
    obvious from the output alone.
    """
    entries = wire_field(ctx, collection)
    assert isinstance(entries, list), f"{collection!r} is not a JSON array on the wire: {entries!r}"

    def _present() -> list:
        return [{k: e.get(k) for k in ("account_id", "buyer_ref", "creative_id", "action") if k in e} for e in entries]

    if index is not None:
        assert 0 <= index < len(entries), (
            f"{collection}[{index}] is out of range — the wire carried {len(entries)} entr(y/ies): {_present()}"
        )
        entry = entries[index]
    else:
        assert match, f"wire_entry({collection!r}) needs either index= or a field to match on"
        matched = [e for e in entries if isinstance(e, dict) and all(_dig(e, k) == v for k, v in match.items())]
        assert matched, f"no {collection} entry matching {match!r}; the wire carried: {_present()}"
        assert len(matched) == 1, f"{match!r} matched {len(matched)} {collection} entries, expected exactly one"
        entry = matched[0]
    assert isinstance(entry, dict), f"{collection} entry is not a JSON object on the wire: {entry!r}"
    return entry


def wire_entry(ctx: dict, collection: str, *, index: int | None = None, **match: Any) -> dict:
    """One entry of a per-entry SUCCESS response, located on the wire.

    A partial-success response (e.g. sync-accounts-response oneOf/0) carries its
    per-entry outcomes at ``accounts[]`` — INSIDE a success envelope — so
    ``assert_wire_error`` / ``wire_error_envelope``, which grade the error-envelope
    shape, structurally cannot serve them. Without this primitive the only way to
    reach an entry is a typed-payload read or a hand-rolled index, which is how the
    typed ``ctx["last_account"]`` stash grew 28 readers.

    Locate by ``**match`` on the entry's own wire fields — flat
    (``account_id="acct_1"``) or dotted for a nested one
    (``**{"brand.domain": "nike.com"}``, the same dotted convention
    :func:`wire_lookup` uses) — or, for a genuinely single-entry response, by ``index=0`` — in which case pin
    the count (``len(wire_field(ctx, "accounts")) == 1``) so index 0 is asserted
    rather than assumed. Built on :func:`wire_field`, so it inherits the loud guard.
    """
    return _locate_entry(ctx, collection, index, match)


def wire_entry_errors(ctx: dict, collection: str, *, index: int | None = None, **match: Any) -> list:
    """The per-entry ``errors[]`` array of one entry, located on the wire.

    Per-entry errors are the partial-failure channel: a rejected row inside an
    otherwise successful response. Defaults to ``[]`` — an entry that succeeded
    carries no errors, and that absence is a legitimate outcome to assert on, not
    a missing-wire defect.

    RESTRICTED: the buyer-facing ``message`` is stripped from every entry before it is
    returned. This is the one GUARD-SANCTIONED per-entry reader (it is blessed in the wire
    discipline guard's ``_PRIMITIVE_FUNCTIONS``), so handing back the sentence would make it
    the single blessed door through which a step could assert prose — the exact class this
    reader is sanctioned to replace. The sentence is a function of the entry's CODE through
    CODE_TABLE, so nothing is lost: assert ``code``, ``recovery``, ``field`` or ``details``.
    """
    entry = _locate_entry(ctx, collection, index, match)
    errors = entry.get("errors") or []
    assert isinstance(errors, list), f"{collection} entry errors is not a JSON array on the wire: {errors!r}"
    return [
        {k: v for k, v in error.items() if k != "message"} if isinstance(error, dict) else error for error in errors
    ]


def wire_absent(ctx: dict, path: str) -> None:
    """Assert the dotted *path* is not present on the success-path wire at all.

    The strict complement of :func:`wire_field`: only the missing key counts as
    absent. A path that resolves to a JSON ``null`` is PRESENT and therefore FAILS
    here — an unset optional section must not appear on the wire at all, and a
    serialized ``null`` is the schema-invalid emission this asserts against.
    """
    value = wire_lookup(ctx, path)
    assert value is WIRE_MISSING, f"{path!r} unexpectedly present on the wire: {value!r}"


def _require(ctx: dict, key: str, *, hint: str | None = None) -> object:
    """Return ``ctx[key]``, failing with a diagnostic if it is absent.

    Then steps read entities and outcomes a prior step was expected to put in
    ``ctx``. Reading ``ctx[key]`` by subscript raises a bare ``KeyError`` when
    that step did not populate it — giving no hint why. This helper raises an
    ``AssertionError`` that names the missing key, includes an optional hint,
    and surfaces any recorded error instead.

    ``env`` is intentionally not routed through this helper: the harness
    guarantees it and the ``no-silent-env`` guard requires ``ctx["env"]``.
    """
    val = ctx.get(key)
    detail = f" {hint}" if hint else ""
    assert val is not None, f"Expected ctx[{key!r}] in ctx but none found.{detail} Recorded error: {ctx.get('error')!r}"
    return val


def _require_response(ctx: dict) -> object:
    """Return ctx["response"], failing with a diagnostic if it is absent.

    Then steps assert on the response produced by a prior When step. Reading
    ``ctx["response"]`` by subscript raises a bare ``KeyError`` when the
    operation errored (only ``ctx["error"]`` was set) — giving no hint why.
    This helper raises an ``AssertionError`` that names the missing response
    and surfaces any recorded error instead.
    """
    return _require(ctx, "response", hint="The operation may have errored instead of returning.")


def _require_error(ctx: dict) -> object:
    """Return ctx["error"], failing with a diagnostic if no error was recorded.

    Then steps on an error path read ``ctx["error"]``. By subscript that raises
    a bare ``KeyError`` when the operation actually succeeded — giving no hint
    that the expected error never happened. This helper raises an
    ``AssertionError`` that says an error was expected and surfaces the response
    produced instead.
    """
    error = ctx.get("error")
    assert error is not None, (
        "Expected an error to be recorded in ctx but none found — the operation "
        f"may have succeeded. Response: {ctx.get('response')!r}"
    )
    return error


def _get_response_field(resp: object, field: str) -> object:
    """Extract a field from a response, handling wrapper types."""
    if hasattr(resp, field):
        return getattr(resp, field)
    inner = getattr(resp, "response", None)
    if inner is not None and hasattr(inner, field):
        return getattr(inner, field)
    if isinstance(resp, dict):
        return resp.get(field)
    return None


def is_e2e(ctx: dict) -> bool:
    """Check if the current transport is E2E (Docker-based)."""
    transport = ctx.get("transport")
    return transport is not None and hasattr(transport, "value") and str(transport.value).startswith("e2e_")


def assert_media_buy_created(ctx: dict, media_buy_id: str | None = None) -> object:
    """Verify media buy exists in DB through the harness.

    Returns the MediaBuy ORM instance for further assertions.
    """
    env = ctx["env"]

    if media_buy_id is None:
        resp = ctx.get("response")
        if resp is not None:
            media_buy_id = _get_response_field(resp, "media_buy_id")

    assert media_buy_id is not None, "No media_buy_id available to verify creation"

    mb = env.get_media_buy(media_buy_id)
    return mb


def assert_adapter_executed(ctx: dict) -> object:
    """Verify adapter ran by checking DB state through the harness.

    A media buy that reaches a non-draft status proves the adapter was invoked.
    """
    mb = assert_media_buy_created(ctx)
    executed_statuses = ("active", "completed", "pending_approval", "pending_start", "submitted")
    assert mb.status in executed_statuses, (
        f"Media buy status '{mb.status}' does not confirm adapter execution. Expected one of {executed_statuses}."
    )
    return mb


def assert_audit_logged(ctx: dict, *, operation_substring: str = "create_media_buy") -> None:
    """Verify audit logging occurred — transport-aware.

    In-process: asserts on mock audit logger calls (fast, precise).
    E2E: queries audit_logs through the harness.
    """
    if is_e2e(ctx):
        env = ctx["env"]
        logs = env.get_audit_logs(operation_substring)
        assert logs, f"Expected audit_logs entry containing '{operation_substring}' for tenant {env._tenant_id}"
    else:
        _assert_audit_logged_mock(ctx, operation_substring)


def _assert_audit_logged_mock(ctx: dict, operation_substring: str) -> None:
    """Assert audit logger mock was called with the operation (in-process mode)."""
    env = ctx["env"]
    mock_audit = env.mock["audit"].return_value
    assert mock_audit.log_operation.called, (
        f"Expected audit_logger.log_operation to be called with '{operation_substring}', but it was never called"
    )
    operations = [
        call.kwargs.get("operation") or (call.args[0] if call.args else None)
        for call in mock_audit.log_operation.call_args_list
    ]
    matching = [op for op in operations if op and operation_substring in op]
    assert matching, (
        f"Expected at least one log_operation call containing '{operation_substring}', got operations: {operations}"
    )


def assert_audit_approval_logged(ctx: dict) -> None:
    """Verify approval decision was logged — transport-aware."""
    if is_e2e(ctx):
        env = ctx["env"]
        logs = env.get_audit_logs()
        found = any("pending_approval" in (log.operation or "") for log in logs) or any(
            "create_media_buy" in (log.operation or "") and log.success is True for log in logs
        )
        assert found, (
            f"Expected audit entry for approval decision, found: {[(log.operation, log.success) for log in logs]}"
        )
    else:
        _assert_audit_approval_mock(ctx)


def _assert_audit_approval_mock(ctx: dict) -> None:
    """Assert approval-specific audit log call exists (in-process mode)."""
    env = ctx["env"]
    mock_audit = env.mock["audit"].return_value
    assert mock_audit.log_operation.called, (
        "Expected audit_logger.log_operation to be called for approval decision logging"
    )
    for call in mock_audit.log_operation.call_args_list:
        op = call.kwargs.get("operation") or (call.args[0] if call.args else None)
        if op == "create_media_buy_pending_approval":
            return
        if op == "create_media_buy":
            success = call.kwargs.get("success")
            details = call.kwargs.get("details") or {}
            if success is True and "media_buy_id" in details:
                return
    raise AssertionError(
        f"Expected audit log entry with approval-specific content, "
        f"got calls: {[c.kwargs for c in mock_audit.log_operation.call_args_list]}"
    )


def assert_audit_adapter_logged(ctx: dict) -> None:
    """Verify adapter execution was logged — transport-aware.

    If the media buy went to pending_approval, the adapter was not called —
    that's correct behavior (no adapter audit log expected).
    """
    if is_e2e(ctx):
        env = ctx["env"]
        logs = env.get_audit_logs()
        for log in logs:
            op = log.operation or ""
            if "create_media_buy" in op and log.success is True and log.details is not None:
                return
            if "pending_approval" in op:
                return
        raise AssertionError(
            f"Expected audit entry for adapter execution or pending_approval, "
            f"found: {[(log.operation, log.success) for log in logs]}"
        )
    else:
        _assert_audit_adapter_mock(ctx)


def _assert_audit_adapter_mock(ctx: dict) -> None:
    """Assert adapter execution audit log call exists (in-process mode)."""
    env = ctx["env"]
    mock_audit = env.mock["audit"].return_value
    assert mock_audit.log_operation.called, (
        "Expected audit_logger.log_operation to be called for adapter execution logging"
    )
    for call in mock_audit.log_operation.call_args_list:
        op = call.kwargs.get("operation") or (call.args[0] if call.args else None)
        success = call.kwargs.get("success")
        details = call.kwargs.get("details")
        if op == "create_media_buy" and success is True and details is not None:
            return
    raise AssertionError(
        f"Expected audit log entry for adapter execution "
        f"(operation='create_media_buy', success=True, with details), "
        f"got: {[c.kwargs for c in mock_audit.log_operation.call_args_list]}"
    )

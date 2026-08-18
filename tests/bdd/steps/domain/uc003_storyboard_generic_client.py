"""BDD step definitions for UC-003 storyboard scenarios wired onto AdCPTestClient.

SB-4a demonstrator (salesagent-35to): dispatches through the transport-generic
``AdCPTestClient`` (``tests/harness/client.py``) via ``dispatch_via_client``
instead of ``MediaBuyDualEnv``/``dispatch_request``. Additive only — see
``tests/bdd/conftest.py``'s ``_UC003_STORYBOARD_GENERIC_CLIENT`` branch.

beads: salesagent-35to
"""

from __future__ import annotations

from uuid import uuid4

from pytest_bdd import given, then, when

from tests.bdd.steps._outcome_helpers import wire_error_dict
from tests.bdd.steps.generic._dispatch import dispatch_via_client
from tests.bdd.steps.generic.then_error import then_error_recovery


@given("the buyer fabricates a media_buy_id that does not exist in the seller catalog")
def given_fabricated_nonexistent_media_buy_id(ctx: dict) -> None:
    """Stash a guaranteed-nonexistent media_buy_id — nothing to seed against."""
    ctx["fabricated_media_buy_id"] = f"mb_does_not_exist_{uuid4()}"


@when("the Buyer Agent sends update_media_buy with the unknown media_buy_id and paused true")
def when_update_media_buy_with_unknown_id(ctx: dict) -> None:
    """Dispatch update_media_buy for the fabricated id through AdCPTestClient.

    Generates and stashes a correlation_id under the generic ctx["correlation_id"]
    key (not scenario-specific) so the dormant sibling scenario
    T-UC-003-storyboard-package-not-found, which reuses the correlation_id-echo
    Then step below, can graduate later without a rewrite.
    """
    correlation_id = str(uuid4())
    ctx["correlation_id"] = correlation_id
    payload = {
        "media_buy_id": ctx["fabricated_media_buy_id"],
        "paused": True,
        "context": {"correlation_id": correlation_id},
    }
    dispatch_via_client(ctx, "update_media_buy", payload)


@when("the Buyer Agent sends update_media_buy with canceled true on the already-canceled buy")
def when_update_media_buy_recancel(ctx: dict) -> None:
    """Dispatch the second cancel of an already-canceled buy, on the wire.

    Sends the buyer's literal payload — ``canceled: true`` included — through
    ``AdCPTestClient`` so the request-field normalization seam is what decides
    whether ``canceled`` is honored or refused (Lane A, salesagent-qbac1.1).
    Deliberately NOT ``dispatch_request`` on ``MediaBuyDualEnv``: that env's
    ``_flatten_update_request`` pops ``canceled``/``cancellation_reason``
    (``_WRAPPER_UNSUPPORTED_FIELDS``) before the wire, so the scenario would
    grade the harness's own accommodation of the bug instead of the seller.

    Stashes the correlation_id under the generic ``ctx["correlation_id"]`` key,
    the same contract the sibling storyboard When step uses, so the shared
    correlation-echo Then step below works unmodified.
    """
    correlation_id = str(uuid4())
    ctx["correlation_id"] = correlation_id
    media_buy = ctx["existing_media_buy"]
    assert media_buy is not None, (
        "No existing_media_buy in ctx — the re-cancel scenario needs the Background's "
        "seeded buy, mutated to canceled status by the Given step"
    )
    payload = {
        "media_buy_id": media_buy.media_buy_id,
        "canceled": True,
        "context": {"correlation_id": correlation_id},
    }
    dispatch_via_client(ctx, "update_media_buy", payload)


@then("the error recovery hint should indicate correctable")
def then_error_recovery_hint_correctable(ctx: dict) -> None:
    """Delegate to then_error_recovery's existing wire-first logic — DRY, no duplication."""
    then_error_recovery(ctx, "correctable")


@then("the response should echo the context.correlation_id unchanged")
def then_response_echoes_correlation_id_unchanged(ctx: dict) -> None:
    """Assert the wire envelope's top-level context.correlation_id matches the When step's stash.

    Reads the generic ctx["correlation_id"] key (see the When step above), not
    a scenario-specific one, so this step is reusable by any sibling scenario
    that generates and stashes a correlation_id the same way.
    """
    envelope = wire_error_dict(ctx)
    expected = ctx.get("correlation_id")
    assert expected is not None, "No correlation_id stashed on ctx — the When step must generate and stash one"
    actual = (envelope.get("context") or {}).get("correlation_id")
    assert actual == expected, f"Expected context.correlation_id={expected!r} echoed unchanged, got {actual!r}"


@then("the response should NOT be a 500 or non-AdCP error shape")
def then_response_not_500_or_non_adcp_shape(ctx: dict) -> None:
    """Assert the two-layer AdCP envelope shape via the single shape authority, and non-500 where a status exists.

    ``result.assert_wire_error`` is the harness's single shape authority for
    verifying an error on the wire (see its docstring) — delegating to it here
    (rather than re-implementing its checks inline) means a spec change to the
    envelope shape only needs updating in one place. This step has no expected
    code of its own (it is reused across scenarios with different codes), so
    it reads the code the envelope itself reports and asserts against THAT —
    which still exercises the real checks ``assert_wire_error`` performs: the
    two-layer invariant (``adcp_error.code == errors[0].code``), that the code
    is canonical (pinned ``error-code.json``), and that recovery matches the
    pinned classification.

    The "not a 500 or non-AdCP shape" half is graded by the DERIVED status
    (Lane C, change-set C4). It used to be gated on ``status_code``, which only
    REST populates — so on MCP and A2A, two of the three transports this
    scenario claims to cover, that half of the sentence was a silent no-op. The
    fix is NOT to synthesize an HTTP status for them: inventing a number and
    then asserting it is != 500 would be a loud tautology. Instead each
    transport reports whether the seller produced a structured AdCP envelope
    (``adcp_error``) or died as a fault (``transport_fault``), read from its own
    evidence — REST's HTTP body, A2A's failed-Task artifact, MCP's ToolError.
    The REST status_code check is kept where it genuinely exists.
    """
    result = ctx.get("result")
    envelope = wire_error_dict(ctx)
    code = (envelope.get("adcp_error") or {}).get("code")
    assert code, f"Expected a non-empty adcp_error.code in the wire envelope, got {envelope}"
    result.assert_wire_error(code)

    transport_envelope = getattr(result, "envelope", None) or {}
    status = transport_envelope.get("status")
    assert status != "transport_fault", (
        "Expected a structured AdCP error envelope, but the transport reported a fault "
        f"(status={status!r}, envelope={transport_envelope!r}) — this is the 'not a 500 or "
        "non-AdCP error shape' obligation failing."
    )

    status_code = transport_envelope.get("status_code")
    if status_code is not None:
        assert status_code != 500, f"Expected a non-500 status, got {status_code}"

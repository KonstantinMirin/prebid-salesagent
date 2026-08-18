"""RED grader for Lane C (salesagent-qbac1.3): UC-006 storyboard Thens must grade the WIRE.

Core Invariant under grade (lane plan, verbatim): *every storyboard ``Then``
asserts a transport-observable signal, on every transport, through the guarded
accessors (``wire_dict``/``wire_field``/``assert_wire_error``); setup goes
through the env's per-transport primitive, never a direct ``_impl`` call.*

**Why this module exists rather than the liveness artifact.** Lane C's §5
declares two graders: the per-scenario ledgered/live partition pinned in
``tests/integration/test_bdd_scenario_liveness_real_run.py:99-125`` — which
solution-review pass 3 (P4) assigns to **Lane D**, and which Lane C **must not
modify** — and the REVERSION TEST, which pass-3 finding (d) requires to be *an
EXECUTED step in the grader, not a prose procedure*. This module is that
executed grader, plus the per-item mutations for C3 and C4 that the partition
artifact cannot see (the artifact records pass/xfail; it cannot tell a Then that
read the wire from one that re-serialized an in-memory object and got lucky).

**Why the Thens are driven directly instead of through pytest-bdd.** Finding (d):
the reversion "must run against a scenario P1 marks EXPECTED-LIVE, because an
xfail-ledgered scenario would SWALLOW the loud failure". Driving the step
functions against a ctx built from the LIVE scenario's own Given/When
(``T-UC-006-storyboard-format-id-roundtrip-on-sync``) satisfies that and, in
addition, puts the assertions out of reach of *any* ledger route — the conftest
tag sets and ``tests/bdd/e2e_rest_known_failures.txt`` both key on scenario
identity, and no scenario is being collected here. Same reasoning as
``tests/unit/test_bdd_uc006_storyboard_dispatch_fault_is_not_xfail.py``, which
drives the same module's Thens against an injected fault.

**Measured pre-Lane-C state** (this box, ``CreativeSyncEnv``, storyboard payload):

    transport   TransportResult.wire_response
    mcp         {'dry_run', 'creatives', 'status'}   real wire
    rest        {'dry_run', 'creatives', 'status'}   real wire
    a2a         None                                 <- the gap C1 closes

``CreativeSyncEnv``'s A2A leg calls ``sync_creatives_raw`` directly (its own
docstring says why), so it never routes through ``_run_a2a_handler`` and never
stashes a wire. ``then_response_envelope_schema_valid`` therefore falls back to
``resp.model_dump(mode="json")`` — a re-serialization of the in-process object,
which cannot catch an A2A framing regression because no A2A framing was
exercised.

**CB1 compatibility.** Every mutation below leaves ``ctx["response"]``
POPULATED, so a C2 implementation that keeps ``_response_or_xfail(ctx, ...)``
ahead of the wire read — which pass-3 CB1 makes BINDING — passes these graders
unchanged. Nothing here requires or rewards deleting that guard; deleting it is
Lane D's step, one commit later.

**Out of scope, deliberately.** C6 (the phantom-transport assertion) is graded by
the transport-set assertion already living in the Lane-D-owned liveness block;
this module does not restate it and does not touch that file. C5 (context echo
compared against the captured wire) is a test-side assertion-source obligation on
``CapabilitiesEnv``, graded structurally by
``tests/unit/test_architecture_context_echo_wire_grading.py`` — a behavioral
byte-for-byte echo test would redden for a PRODUCTION normalization defect
(measured: ``context={"trace_id": "t1", "channel": None}`` comes back
``{"trace_id": "t1"}`` on the mcp and a2a wire alike), which Lane C does not own.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any

import pytest

from tests.bdd.steps.domain import uc006_storyboard_creative_sync as steps
from tests.bdd.steps.generic._dispatch import _populate_ctx_from_result
from tests.harness.transport import Transport, TransportResult

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

#: The three in-process wire transports the storyboard slice parametrizes over.
#: IMPL is deliberately absent — it has no wire by definition (tests/CLAUDE.md
#: "TransportResult.wire_response"), so it cannot grade this invariant.
WIRE_TRANSPORTS = (Transport.MCP, Transport.A2A, Transport.REST)

#: The scenario whose Given/When builds every ctx below. P1 (solution review
#: pass 2) marks this the one EXPECTED-LIVE member of the UC-006 storyboard
#: partition; the other five are ledgered against named production defects and
#: would swallow a loud failure (finding (d)).
LIVE_SCENARIO_TAG = "T-UC-006-storyboard-format-id-roundtrip-on-sync"


class _NeverSerialized:
    """Stand-in for ``ctx["response"]`` whose re-serialization is a loud failure.

    ``_response_or_xfail`` only checks that ``ctx["response"]`` is not None, so
    this object satisfies the CB1-mandated guard while making any *use* of the
    in-memory object as an assertion SOURCE observable: ``model_dump`` records
    the call and returns a payload that is not schema-valid, so a Then that
    still re-serializes both trips the recorder and fails validation.
    """

    def __init__(self) -> None:
        self.model_dump_calls: list[dict[str, Any]] = []

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        self.model_dump_calls.append(kwargs)
        return {"not": "a sync-creatives response envelope"}


def _live_scenario_ctx(env: Any, transport: Transport) -> dict[str, Any]:
    """Run the LIVE storyboard scenario's own Given + When and return its ctx.

    Uses the production step functions verbatim — no re-derived payload — so a
    change to the scenario's setup moves this grader with it instead of leaving
    it grading a stale payload.
    """
    ctx: dict[str, Any] = {"env": env, "transport": transport}
    steps.given_captured_format_id_from_get_products_for_sync(ctx)
    steps.when_sync_creative_with_captured_format_id(ctx)
    assert ctx.get("error") is None, (
        f"{transport.value}: the LIVE storyboard scenario's When dispatch errored — "
        f"this grader cannot measure wire discipline against a failed dispatch: {ctx['error']!r}"
    )
    assert ctx.get("response") is not None, f"{transport.value}: dispatch produced neither response nor error"
    return ctx


def _sync_env(name: str) -> Any:
    from tests.harness.creative_sync import CreativeSyncEnv

    return CreativeSyncEnv(tenant_id=name, principal_id="wire_grader_principal")


# ═══════════════════════════════════════════════════════════════════════
# C1 — the A2A leg must capture a real success-path wire
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("transport", WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_storyboard_dispatch_captures_a_real_success_path_wire(integration_db, transport: Transport) -> None:
    """Every wire transport must stash ``TransportResult.wire_response`` for sync_creatives.

    This is C1's grader. ``wire_response`` is populated on A2A *only* when the env
    routes through ``_run_a2a_handler`` (tests/CLAUDE.md, "Authenticity per
    transport") — the raw-wrapper bypass produces ``None``, which is exactly the
    condition ``wire_dict``/``wire_field`` raise on. Asserting the top-level
    envelope keys rather than mere non-None keeps a future empty-dict stash from
    satisfying this.
    """
    with _sync_env(f"wire-c1-{transport.value}") as env:
        ctx = _live_scenario_ctx(env, transport)
        wire = ctx.get("wire_response")

    assert isinstance(wire, dict), (
        f"{transport.value}: no success-path wire captured for sync_creatives "
        f"(ctx['wire_response']={wire!r}). The storyboard Then steps cannot assert a "
        "transport-observable signal on a transport that stashes no wire."
    )
    assert "creatives" in wire, (
        f"{transport.value}: captured wire has no top-level 'creatives' key — "
        f"got keys {sorted(wire)}; this is not a sync-creatives response envelope."
    )


# ═══════════════════════════════════════════════════════════════════════
# C2 — the envelope-schema Then reads the wire, never the in-memory object
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("transport", WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_envelope_schema_then_validates_the_wire_not_the_in_memory_object(integration_db, transport: Transport) -> None:
    """``then_response_envelope_schema_valid`` must validate ``wire_dict(ctx)``.

    The mutation: keep the real captured wire, but replace ``ctx["response"]``
    with an object whose ``model_dump`` is a tripwire returning a payload that is
    NOT schema-valid. A Then that reads the wire passes and never calls it; the
    ``model_dump`` fallback both trips the recorder and fails validation.

    ``ctx["response"]`` stays non-None on purpose so a CB1-compliant
    implementation (``_response_or_xfail`` retained ahead of the wire read) is
    graded identically to one without it — this grader pins the assertion SOURCE,
    not the guard order.
    """
    with _sync_env(f"wire-c2-{transport.value}") as env:
        ctx = _live_scenario_ctx(env, transport)
        tripwire = _NeverSerialized()
        ctx["response"] = tripwire

        steps.then_response_envelope_schema_valid(ctx)

    assert tripwire.model_dump_calls == [], (
        f"{transport.value}: then_response_envelope_schema_valid re-serialized the in-memory "
        f"response (model_dump called with {tripwire.model_dump_calls}) instead of validating the "
        "captured wire. A schema check against a re-serialization of the in-process object cannot "
        "catch a transport-framing regression — it exercises the serializer twice."
    )


def test_reverting_the_a2a_wire_capture_makes_the_envelope_schema_then_fail_loudly(integration_db) -> None:
    """THE REVERSION TEST (lane §5): un-stash the A2A wire; the Then must fail LOUDLY.

    Executed, not prose (pass-3 finding (d)). The reversion is applied at the
    single observable the A2A wire capture produces — ``_run_a2a_handler``'s
    ``env._last_wire_response`` stash — rather than by name-patching the env's A2A
    primitive, because Lane B renames that primitive in the commit immediately
    before this lane. Clearing the stash reproduces exactly the pre-C1 observable
    that the ``sync_creatives_raw`` bypass produces: a real typed response, and no
    wire (measured above: ``wire_response=None`` on a2a today, a real dict on
    mcp/rest).

    Run on the EXPECTED-LIVE scenario (finding (d)) and driven directly, so no
    ledger tag can absorb the failure.

    Direction: with no wire, ``wire_dict``'s guard (``_outcome_helpers.py:53-56``)
    must raise. Silence here means the ``model_dump`` fallback is still in place
    and the A2A leg's wire capture is decorative — the precise failure mode C2
    exists to remove.
    """
    with _sync_env("wire-c2-revert-a2a") as env:
        ctx = _live_scenario_ctx(env, Transport.A2A)
        # THE REVERSION: the A2A leg stashed no success-path wire.
        ctx["wire_response"] = None
        assert ctx.get("response") is not None, "reversion must leave the typed response intact"

        with pytest.raises(AssertionError) as excinfo:
            steps.then_response_envelope_schema_valid(ctx)

    assert "wire_response missing" in str(excinfo.value), (
        f"the envelope-schema Then failed, but not through the guarded accessor's missing-wire guard: {excinfo.value!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# C3 — the format_id roundtrip reads the creative back ON THE WIRE
# ═══════════════════════════════════════════════════════════════════════


def _spy_on_client_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every tool name dispatched through ``AdCPTestClient.call``.

    ``AdCPTestClient.call`` is the seam pass-3 CB3 binds C3 to — either via a
    ctx-seeded client (mirroring ``tests/bdd/conftest.py:3123``) or via
    ``AdCPTestClient(ctx["env"])`` built at the step. Both route through this one
    method, so spying here does not presume which of the two C3 picks.
    """
    from tests.harness.client import AdCPTestClient

    seen: list[str] = []
    original = AdCPTestClient.call

    def _spy(self: Any, tool: str, payload: dict[str, Any], transport: Transport, **kwargs: Any) -> TransportResult:
        seen.append(tool)
        return original(self, tool, payload, transport, **kwargs)

    monkeypatch.setattr(AdCPTestClient, "call", _spy)
    return seen


@pytest.mark.parametrize("transport", WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_format_id_roundtrip_then_reads_the_creative_back_over_the_wire(
    integration_db, monkeypatch: pytest.MonkeyPatch, transport: Transport
) -> None:
    """``then_format_id_roundtrips_verbatim`` must read the persisted creative on the wire.

    C3: the ``CreativeRepository`` read stays only as a redundant in-process check;
    the PRIMARY assertion is a ``list_creatives`` dispatch plus a wire read.
    ``CreativeSyncEnv`` exposes no ``list_creatives`` primitive (its MCP_TOOL /
    REST_ENDPOINT are sync-only), but ``AdCPTestClient.call`` resolves any tool off
    the address table on the SAME env — measured working on all three transports
    against this env (pass-2 finding (c) names it; CB3 makes the wiring explicit).
    """
    seen = _spy_on_client_calls(monkeypatch)

    with _sync_env(f"wire-c3-{transport.value}") as env:
        ctx = _live_scenario_ctx(env, transport)
        steps.then_format_id_roundtrips_verbatim(ctx)

    assert "list_creatives" in seen, (
        f"{transport.value}: the format_id-roundtrip Then never dispatched list_creatives "
        f"(tools dispatched through AdCPTestClient: {seen}). It graded only the DB row, so it "
        "cannot detect a seller that persists the format_id correctly and then serializes it "
        "wrong on the wire — the exact roundtrip the storyboard step grades."
    )


@pytest.mark.parametrize("transport", WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_format_id_roundtrip_then_fails_when_the_wire_contradicts_the_captured_id(
    integration_db, monkeypatch: pytest.MonkeyPatch, transport: Transport
) -> None:
    """A wire that disagrees with the captured format_id must FAIL the Then.

    The complement of the spy test: proves the wire read is the PRIMARY assertion
    and not a decorative extra call. The DB row is left correct and only the
    ``list_creatives`` wire is corrupted (every occurrence of the captured format
    id replaced), so a Then that still grades the repository read passes green on
    a wire that contradicts it.
    """
    from tests.harness.client import AdCPTestClient

    original = AdCPTestClient.call

    def _lying_call(self: Any, tool: str, payload: dict[str, Any], tr: Transport, **kwargs: Any) -> TransportResult:
        result = original(self, tool, payload, tr, **kwargs)
        if tool != "list_creatives" or result.wire_response is None:
            return result
        corrupted = json.loads(
            json.dumps(copy.deepcopy(result.wire_response)).replace(captured_id, "format_id_from_another_seller")
        )
        return replace(result, wire_response=corrupted)

    with _sync_env(f"wire-c3-lie-{transport.value}") as env:
        ctx = _live_scenario_ctx(env, transport)
        captured_id = ctx["captured_format_id"]["id"]
        monkeypatch.setattr(AdCPTestClient, "call", _lying_call)

        with pytest.raises(AssertionError):
            steps.then_format_id_roundtrips_verbatim(ctx)


# ═══════════════════════════════════════════════════════════════════════
# C4 — a DERIVED status enum on the error envelope, never a fabricated code
# ═══════════════════════════════════════════════════════════════════════

#: The two members of C4's derived enum. Deliberately NOT an integer
#: ``status_code``: synthesizing an HTTP status for MCP/A2A would turn today's
#: silent no-op into a loud tautology — the harness asserting != 500 against a
#: number the harness itself invented (pass-1 finding 4).
DERIVED_STATUS_VALUES = ("adcp_error", "transport_fault")


def _adcp_error_result(env: Any, transport: Transport) -> TransportResult:
    """Dispatch an unauthenticated sync_creatives — a structured AdCP rejection, not a fault."""
    return env.call_via(
        transport,
        identity=None,
        creatives=[
            {
                "creative_id": "creative-c4-001",
                "name": "C4 Grader Creative",
                "format_id": {"id": "display_300x250", "agent_url": env.DEFAULT_AGENT_URL},
            }
        ],
    )


@pytest.mark.parametrize("transport", WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_error_envelope_carries_a_derived_status_on_every_transport(integration_db, transport: Transport) -> None:
    """``TransportResult.envelope['status']`` must be derived on mcp/a2a/rest alike.

    Measured today: ``envelope`` is ``{}`` on mcp, ``{'transport': 'a2a'}`` on a2a,
    and carries a real ``status_code`` only on rest — which is why
    ``then_response_not_500_or_non_adcp_shape``'s status check is a silent no-op on
    two of the three transports the storyboard scenario claims to cover.

    The authentic per-transport sources are named by the design: REST's real HTTP
    status, A2A's Task state (``_base.py``'s ``_last_a2a_task``), and MCP's
    ``CallToolResult.is_error`` via ``raise_on_error=False``. A structured AdCP
    rejection must read ``adcp_error`` on all three.
    """
    with _sync_env(f"wire-c4-{transport.value}") as env:
        env.setup_default_data()
        result = _adcp_error_result(env, transport)

    assert result.is_error, f"{transport.value}: expected an AdCP rejection, got {result.payload!r}"
    status = result.envelope.get("status")
    assert status in DERIVED_STATUS_VALUES, (
        f"{transport.value}: TransportResult.envelope carries no derived status "
        f"(envelope={result.envelope!r}). Without it, 'the response should NOT be a 500 or "
        "non-AdCP error shape' grades nothing on this transport."
    )
    assert status == "adcp_error", (
        f"{transport.value}: a structured AdCP rejection must derive status='adcp_error', got {status!r}"
    )


@pytest.mark.parametrize("transport", WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_not_500_then_fails_when_the_derived_status_reports_a_transport_fault(
    integration_db, transport: Transport
) -> None:
    """``then_response_not_500_or_non_adcp_shape`` must FAIL on ``status='transport_fault'``.

    The step's own docstring claims "a real check on every transport, not a
    conditional no-op", but its status branch is gated on a ``status_code`` only
    REST populates. This mutation states the obligation the Then's sentence
    actually makes — *the seller returned a transport fault instead of a structured
    AdCP envelope* — and requires the step to enforce it wherever the derived
    status exists.

    The error envelope itself is left untouched and valid, so the ONLY thing that
    can redden this is the step reading the derived status.
    """
    from tests.bdd.steps.domain import uc003_storyboard_generic_client as uc003_steps

    with _sync_env(f"wire-c4-fault-{transport.value}") as env:
        env.setup_default_data()
        result = _adcp_error_result(env, transport)
        assert result.is_error, f"{transport.value}: expected an AdCP rejection, got {result.payload!r}"

        faulted = replace(result, envelope={**result.envelope, "status": "transport_fault"})
        ctx: dict[str, Any] = {"env": env, "transport": transport}
        _populate_ctx_from_result(ctx, faulted)

        with pytest.raises(AssertionError):
            uc003_steps.then_response_not_500_or_non_adcp_shape(ctx)

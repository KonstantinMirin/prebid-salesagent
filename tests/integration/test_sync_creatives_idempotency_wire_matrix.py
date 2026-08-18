"""Wire matrix for sync_creatives idempotency: replay / conflict / fresh key per transport.

The obligation, from the PINNED spec (AdCP 3.1.1) rather than the SDK:

    ~/projects/adcp @ v3.1.1 — dist/compliance/3.1.1/universal/idempotency.yaml
    "Every mutating request in AdCP carries an idempotency_key so buyers can safely
     retry after network errors without double-booking."
      1. First call with a fresh key is processed normally.
      2. Replay with the same key and an equivalent payload returns the cached
         response WITHOUT re-executing resource mutations.
      3. Same key + a materially different payload -> IDEMPOTENCY_CONFLICT.
      4. A different key is a NEW request even if the payload is identical.
      5. Error responses do NOT cache.
    "Sellers that do not support create_media_buy SHOULD still pass idempotency
     compliance on whichever mutating task they do implement."

``pinned_request_schema_fields("sync_creatives")`` reports ``idempotency_key`` as
present AND REQUIRED, so this is a schema-required field on a mutating task — not
an optional nicety.

GRADED-BY status, stated rather than assumed (CLAUDE.md spec-grounding gate): the
universal idempotency storyboard exercises ``create_media_buy`` / ``get_media_buys``
/ ``get_adcp_capabilities`` only — there is NO ``task: sync_creatives`` step at
3.1.1. sync_creatives appears with ``idempotency_key`` in the domain scenarios only
as sample-request payload, never as an idempotency assertion. The obligation is
mandated but **UNGRADED** by any conformance step, which is exactly why this
module exists: without it, "sync_creatives is idempotent" is believed, not tested.

Sibling: ``tests/integration/test_idempotency_wire_matrix.py`` grades the identical
contract for ``create_media_buy``. This module deliberately mirrors its structure —
the two tools must satisfy ONE contract through ONE implementation, and a reader
comparing the files should see the same obligations in the same order.

Transports: the three WIRE transports. ``Transport.IMPL`` is excluded on purpose —
``_sync_creatives_impl`` has no idempotency parameter at all, so an IMPL leg would
grade a function signature (the implementer's design choice) rather than the
buyer-observable behavior. The acceptance seam already delivers ``idempotency_key``
to every wire transport (``@accepts_spec_request_fields`` on ``sync_creatives_raw``
and on the MCP registration), so these three legs grade HONORING, not acceptance.

Behavior 5 (errors are never cached) is NOT covered here, and the reason is
structural rather than an omission: sync_creatives has partial-success semantics —
a per-creative failure still returns the success variant — and the only
whole-operation errors reachable at this layer (auth / request validation) reject
before any handler mutation, so a "did the error cache?" probe cannot distinguish a
correct implementation from one that never got far enough to cache. The spec itself
defers the end-to-end version of this phase "pending a generic force-error
controller verb" (adcontextprotocol/adcp#2760). Behaviors 6 (in-flight) and the
expired-window arm are likewise out of scope for this atom.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from src.core.database.models import Creative as DBCreative
from tests.harness import CreativeSyncEnv, Transport
from tests.helpers import assert_envelope_shape

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Only transports that carry a real wire. See the module docstring for why IMPL
# is not in this list.
WIRE_TRANSPORTS = [Transport.A2A, Transport.MCP, Transport.REST]

# wire_response is stashed only by dispatchers that route through the real
# transport plumbing. CreativeSyncEnv.call_a2a calls sync_creatives_raw directly
# (its own docstring records why: the real A2A skill handler cannot build a
# CreativeAsset from the wire dict yet), so A2A stashes no wire body. Asserting
# the spec's top-level marker there would assert on a harness reconstruction, so
# the marker arm grades the two transports whose wire is genuinely real.
REAL_WIRE_TRANSPORTS = [Transport.MCP, Transport.REST]


def _key(kind: str) -> str:
    """A fresh idempotency key per test — never share keys across runs."""
    return f"sync-creatives-{kind}-{uuid.uuid4().hex}"


def _action_of(result: Any, index: int = 0) -> str:
    """The per-creative CreativeAction as a plain string."""
    action = result.payload.creatives[index].action
    return str(getattr(action, "value", action))


def _workflow_step_count(env: CreativeSyncEnv) -> int:
    """Number of approval workflow steps the tenant has accumulated.

    This is the concrete "resource mutation" the spec's behavior 2 forbids a
    replay from repeating: each executed sync_creatives under the default
    require-human approval mode mints a workflow step. A replay that re-executes
    mints a second one for a single buyer intent.
    """
    return len(env.get_workflow_steps())


@pytest.mark.parametrize("transport", WIRE_TRANSPORTS, ids=lambda t: t.value)
class TestSyncCreativesIdempotencyWireMatrix:
    """Replay, conflict, and fresh-key behavior observed through each real transport."""

    def test_identical_retry_does_not_re_execute(self, integration_db, transport):
        """Spec behavior 2: an identical retry returns the cached response and
        re-executes NO resource mutation.

        The three assertions are the three observable faces of one obligation:
        the response is the ORIGINAL one (action stays ``created``, and the whole
        per-creative result is byte-for-byte what the first call returned), and
        the seller's state moved exactly once (no second approval workflow step).

        The middle assertion compares the ENTIRE ``creatives`` list as serialized
        to the wire, rather than a single hand-picked field: "verbatim" is a claim
        about every buyer-visible field, and pinning one of them lets a replay that
        silently re-derives the rest pass.
        Note it cannot be spelled ``changes is None`` -- ``SyncCreativeResult``
        pins ``changes`` to ``list[str]`` with ``default_factory=list`` on purpose
        (spec 3.1.1 ``sync-creatives-response.json`` types it ``array``; a None
        default serializes to the spec-invalid ``null`` on MCP -- see the comment
        on that field). An empty list, not None, is the spec-valid "nothing was
        re-written" value here.
        """
        from tests.factories.creative_asset import CreativeAssetFactory

        key = _key("replay")

        with CreativeSyncEnv() as env:
            env.setup_default_data()
            creative = CreativeAssetFactory(creative_id="c_idem_replay", name="Replay Creative")

            first = env.call_via(transport, creatives=[creative], idempotency_key=key)
            assert first.is_success, f"fresh sync failed on {transport.value}: {first.error}"
            steps_after_first = _workflow_step_count(env)

            second = env.call_via(transport, creatives=[creative], idempotency_key=key)
            assert second.is_success, f"replay failed on {transport.value}: {second.error}"
            steps_after_second = _workflow_step_count(env)

        # The replay is the ORIGINAL response, not a fresh upsert result.
        assert _action_of(first) == "created", f"first sync should create on {transport.value}"
        assert _action_of(second) == "created", (
            f"replay on {transport.value} must return the cached 'created' result verbatim, "
            f"got '{_action_of(second)}' — the retry re-executed the upsert"
        )
        # Compare the BUYER-VISIBLE serialization, not the in-memory models:
        # SyncCreativeResult carries exclude=True internal fields (internal_status,
        # review_feedback) that never cross the wire. The original call returns a
        # live model with those populated, while a replay is parsed back from the
        # serialized cache and cannot have them — comparing model objects would
        # therefore fail on a difference the buyer can never observe, which is not
        # what "verbatim" means here.
        first_wire = [c.model_dump(mode="json") for c in first.payload.creatives]
        second_wire = [c.model_dump(mode="json") for c in second.payload.creatives]
        assert second_wire == first_wire, (
            f"a verbatim replay on {transport.value} must reproduce the original "
            f"per-creative result exactly; got {second_wire!r} vs the original "
            f"{first_wire!r} — the retry re-derived the response instead of "
            f"replaying the cached one"
        )
        assert not second.payload.creatives[0].changes, (
            f"a verbatim replay on {transport.value} records no field changes; got "
            f"{second.payload.creatives[0].changes} — the retry re-wrote the creative"
        )

        # And the seller's state moved exactly once for one buyer intent.
        assert steps_after_second == steps_after_first, (
            f"replay on {transport.value} minted a second approval workflow step "
            f"({steps_after_first} -> {steps_after_second}) — the mutation re-executed"
        )

    def test_same_key_different_payload_conflicts(self, integration_db, transport):
        """Spec behavior 3: the same key with a materially different payload is
        IDEMPOTENCY_CONFLICT (recovery ``correctable`` per the pinned enum)."""
        from tests.factories.creative_asset import CreativeAssetFactory

        key = _key("conflict")

        with CreativeSyncEnv() as env:
            env.setup_default_data()
            original = CreativeAssetFactory(creative_id="c_idem_conflict", name="Original Name")

            first = env.call_via(transport, creatives=[original], idempotency_key=key)
            assert first.is_success, f"fresh sync failed on {transport.value}: {first.error}"

            divergent = CreativeAssetFactory(creative_id="c_idem_conflict", name="Materially Different Name")
            second = env.call_via(transport, creatives=[divergent], idempotency_key=key)

        assert second.is_error, (
            f"a reused key carrying a different payload must reject on {transport.value}, "
            "but the seller accepted it and re-executed the write"
        )
        assert second.wire_error_envelope is not None, (
            f"conflict must carry the two-layer wire envelope on {transport.value}"
        )
        assert_envelope_shape(second.wire_error_envelope, "IDEMPOTENCY_CONFLICT", recovery="correctable")

    def test_fresh_key_is_a_new_request(self, integration_db, transport):
        """Spec behavior 4: a DIFFERENT key is a new request even when the payload
        is identical — the key is what makes a retry safe, not payload equivalence.

        This arm is a control: it must stay green both before and after the fix, so
        a future implementation cannot satisfy the replay arm by caching too widely.
        """
        from tests.factories.creative_asset import CreativeAssetFactory

        with CreativeSyncEnv() as env:
            env.setup_default_data()
            creative = CreativeAssetFactory(creative_id="c_idem_fresh", name="Fresh Key Creative")

            first = env.call_via(transport, creatives=[creative], idempotency_key=_key("fresh-a"))
            assert first.is_success, f"fresh sync failed on {transport.value}: {first.error}"
            steps_after_first = _workflow_step_count(env)

            second = env.call_via(transport, creatives=[creative], idempotency_key=_key("fresh-b"))
            assert second.is_success, f"second fresh-key sync failed on {transport.value}: {second.error}"
            steps_after_second = _workflow_step_count(env)

        # A new key re-executes: the upsert runs again and updates the existing row.
        assert _action_of(second) == "updated", (
            f"a fresh key on {transport.value} must execute a new request, got '{_action_of(second)}'"
        )
        assert steps_after_second > steps_after_first, (
            f"a fresh key on {transport.value} must execute (and mint its own workflow step)"
        )


@pytest.mark.parametrize("transport", REAL_WIRE_TRANSPORTS, ids=lambda t: t.value)
def test_replay_carries_the_top_level_replayed_marker(integration_db, transport):
    """The replay must be labelled as one on the wire.

    ``replayed`` is a PROTOCOL-ENVELOPE field at 3.1.1 (core/protocol-envelope.json):
    "Set to true when this response was returned from the idempotency cache rather
    than from a fresh execution ... From 3.1 onward, `replayed` MAY appear on
    responses to any request that resolved via the idempotency cache." Buyers use it
    for billing reconciliation and exactly-once routing, so a replay that is not
    labelled is only half-conformant even when it does not re-execute.

    Asserted on ``wire_response`` — the real serialized body — not on the typed
    payload, so a marker that never reaches the wire cannot pass.
    """
    from tests.factories.creative_asset import CreativeAssetFactory

    key = _key("marker")

    with CreativeSyncEnv() as env:
        env.setup_default_data()
        creative = CreativeAssetFactory(creative_id="c_idem_marker", name="Marker Creative")

        first = env.call_via(transport, creatives=[creative], idempotency_key=key)
        assert first.is_success, f"fresh sync failed on {transport.value}: {first.error}"
        second = env.call_via(transport, creatives=[creative], idempotency_key=key)
        assert second.is_success, f"replay failed on {transport.value}: {second.error}"

    assert first.wire_response is not None, f"{transport.value} must stash a real wire body"
    assert second.wire_response is not None, f"{transport.value} must stash a real wire body"
    # Omitted-or-false on a fresh execution, true on the replay (the spec allows
    # either omission or an explicit false for a fresh call).
    assert first.wire_response.get("replayed", False) is False, (
        f"a fresh sync on {transport.value} must not be marked replayed"
    )
    assert second.wire_response.get("replayed") is True, (
        f"the replay on {transport.value} must carry top-level replayed=true, "
        f"got {second.wire_response.get('replayed')!r}"
    )


def test_stored_creative_is_written_once_across_a_retry(integration_db):
    """The library holds exactly one creative, unmodified, after an identical retry.

    Complements the per-transport arms with the persistence-side view of behavior 2:
    the buyer's single intent produced a single write. Graded on REST (a real HTTP
    wire) because the assertion is about stored state, which is transport-invariant.
    """
    from tests.factories.creative_asset import CreativeAssetFactory

    key = _key("persist")

    with CreativeSyncEnv() as env:
        env.setup_default_data()
        creative = CreativeAssetFactory(creative_id="c_idem_persist", name="Persist Creative")

        first = env.call_via(Transport.REST, creatives=[creative], idempotency_key=key)
        assert first.is_success, f"fresh sync failed: {first.error}"
        stored_after_first = env.get_one(DBCreative, creative_id="c_idem_persist")
        updated_at_after_first = stored_after_first.updated_at

        second = env.call_via(Transport.REST, creatives=[creative], idempotency_key=key)
        assert second.is_success, f"replay failed: {second.error}"

        rows = env.query(DBCreative, creative_id="c_idem_persist")
        stored_after_second = env.get_one(DBCreative, creative_id="c_idem_persist")
        updated_at_after_second = stored_after_second.updated_at

    assert len(rows) == 1, f"expected exactly one stored creative after a retry, got {len(rows)}"
    assert updated_at_after_second == updated_at_after_first, (
        "the replay re-wrote the stored creative: updated_at moved from "
        f"{updated_at_after_first} to {updated_at_after_second}"
    )

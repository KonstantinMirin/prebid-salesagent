"""MCP tools must accept the request fields 3.1.1 defines (GH #1193).

Sibling of ``test_version_envelope_accepted.py`` and deliberately separate: that
one covers the ONE envelope composed into every schema, fixable at the
registration chokepoint. This one covers the fields each tool's OWN request
schema defines and our signature omits — per-tool protocol surface, and a
different fix.

The two produce the identical error string, which is why they are easy to
conflate:

    VALIDATION_ERROR: Unexpected keyword argument

FastMCP builds each tool's input schema from its Python signature and validates
with pydantic before our code runs, so ANY field the spec defines but the
signature omits is rejected outright — not ignored, not defaulted.

Measured against the pinned bundle (`tests/storyboard/runner/adcp-3.1.1/schemas`):

    get_products           18 schema fields,  5 in signature, 13 missing
    sync_accounts           7 schema fields,  4 in signature,  3 missing
    sync_creatives         11 schema fields,  9 in signature,  2 missing
    get_adcp_capabilities   3 schema fields,  1 in signature,  2 missing

These reach the conformance runner as 12 ledgered checks. They only became
visible once the version envelope was accepted (GH #1512) and the
storyboards got past their first step — all 12 were NOT-COLLECTED before that.

The request below is the storyboard's own `sample_request`, verbatim:
``repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/invalid_transitions.yaml``
step ``get_products_brief``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.core.version_compat import accepts_spec_request_fields, spec_request_model
from tests.harness.spec_field_consumption import UNDISPOSED_LEDGER, spec_tool_names, undisposed_fields
from tests.harness.transport import Transport
from tests.helpers import assert_envelope_shape
from tests.helpers.sample_account import SAMPLE_ACCOUNT, spec_field_product_env

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Verbatim from the pinned storyboard step, minus nothing.
STORYBOARD_SAMPLE_REQUEST = {
    "buying_mode": "brief",
    "brief": "Display inventory on outdoor lifestyle content. Q3 flight.",
    "filters": {"is_fixed_price": True},
    "account": SAMPLE_ACCOUNT,
}


@pytest.fixture
def product_env(integration_db):
    """The seeded world both spec-field graders need (see the helper for why)."""
    with spec_field_product_env("spec-fields") as env:
        yield env


def test_get_products_accepts_the_storyboard_sample_request(product_env):
    """The reproduction, at the exact shape the conformance runner sends.

    A seller that rejects a spec-defined optional field is non-conformant even
    if it cannot act on the field: the schema defines it, so the buyer is
    entitled to send it.
    """
    result = product_env.call_via(Transport.MCP, **STORYBOARD_SAMPLE_REQUEST)

    assert result.is_success, (
        f"get_products rejected fields its own 3.1.1 request schema defines: "
        f"{result.wire_error_envelope or result.error}"
    )


# get_products enforces its own rule that at least one of brief/brand/filters is
# present, so a field cannot be tested in true isolation — an empty-but-for-one
# request fails on that rule and tells you nothing about field acceptance. Each
# case therefore adds ONE field to a minimally valid request, keeping the field
# under test the only variable.
MINIMAL_VALID_REQUEST = {"brief": STORYBOARD_SAMPLE_REQUEST["brief"]}
ADDED_FIELDS = sorted(set(STORYBOARD_SAMPLE_REQUEST) - set(MINIMAL_VALID_REQUEST))


@pytest.mark.parametrize("field", ADDED_FIELDS)
def test_each_sample_request_field_is_accepted_alongside_a_valid_request(product_env, field):
    """Which field is rejected, one at a time.

    The aggregate test above says "something in here is rejected"; this says
    which, so a partial fix cannot look like a whole one.
    """
    result = product_env.call_via(
        Transport.MCP,
        **MINIMAL_VALID_REQUEST,
        **{field: STORYBOARD_SAMPLE_REQUEST[field]},
    )

    assert result.is_success, f"get_products rejected `{field}`: {result.wire_error_envelope or result.error}"


def test_a_request_missing_brief_brand_and_filters_is_still_rejected(product_env):
    """The rule that made true isolation impossible is itself worth pinning.

    Accepting more spec fields must not accidentally make an under-specified
    request valid — `account` alone is not a product query.
    """
    result = product_env.call_via(Transport.MCP, account=STORYBOARD_SAMPLE_REQUEST["account"])

    assert result.is_error, "a request with none of brief/brand/filters must still be rejected"


def test_unknown_arguments_are_still_rejected(product_env):
    """Accepting the SPEC'd fields must not become accepting anything.

    `universal/schema-validation.yaml` grades unknown-field handling, so the fix
    cannot be a `**kwargs` catch-all.
    """
    result = product_env.call_via(Transport.MCP, definitely_not_a_real_adcp_field="x")

    assert result.is_error, "an undeclared, non-spec argument must still be rejected"


# ══════════════════════════════════════════════════════════════════════════
# ACCEPTED is not HONORED — the request-normalization seam (Lane A,
# salesagent-qbac1.1; plan .claude/notes/pr1858-round2-remediation.md §5)
#
# The tests above pin that a spec field is not REJECTED. That is only half
# the contract, and the weaker half: `accepts_spec_request_fields` currently
# publishes every field the pinned request schema defines and then `_strip()`s
# it out of the kwargs before the tool body runs (version_compat.py:309-310),
# so `update_media_buy(canceled=true)` is advertised, accepted, and silently
# dropped. The Core Invariant is that a body-semantic field is always HONORED
# or REFUSED, never silently dropped — "the seller returns success while the
# buy keeps spending" is exactly the failure `is_success`-only assertions miss.
#
# HONORED is defined as HAS-A-DISPOSITION, not as ACTED-ON: a field the seam
# threads into the pinned request model and that `_impl` then refuses with an
# explicit AdCPError is disposed of, and legitimately stays in the published
# schema. What may not exist is a published body-semantic field the tool body
# never sees at all.
# ══════════════════════════════════════════════════════════════════════════

# The accept-and-ignore class, the read/write idempotency split, the published
# input schema and the declared-parameter set all live in
# `tests/harness/spec_field_consumption.py` — one implementation, shared with the
# unit guard `test_architecture_spec_field_disposition.py`. Two copies of "what
# counts as honored" is how the first version of this grader drifted into
# counting carrier DELIVERY as honoring.


def _seam_delivered_request_model(tool_name: str, payload: dict[str, Any]) -> Any:
    """The pinned request model instance the seam hands the tool body, or None.

    Probes `accepts_spec_request_fields` itself rather than one decorated
    tool, because the hand-off is by CONSTRUCTION: the decorator builds the
    pinned request model and passes it, uniformly, to every tool it wraps
    (change-set v3 §S3). Asserting nothing about the carrier's NAME keeps this
    grader independent of how the seam is implemented — it only demands that
    an instance of `spec_request_model(tool_name)` reaches the body carrying
    what the caller sent.

    A `**kwargs` probe therefore sees whatever the wrapper forwards. Today it
    sees nothing: `_strip()` (version_compat.py:309-310) removes every
    decorator-added name and no model is passed in its place.
    """
    model = spec_request_model(tool_name)
    assert model is not None, f"{tool_name} has no pinned request model — it is not a 3.1.1 spec task"

    seen: dict[str, Any] = {}

    async def probe(**kwargs: Any) -> None:
        seen.update(kwargs)

    probe.__name__ = tool_name
    probe.__annotations__ = {}
    asyncio.run(accepts_spec_request_fields(probe)(**payload))

    delivered = [value for value in seen.values() if isinstance(value, model)]
    assert len(delivered) <= 1, (
        f"{tool_name}: the seam delivered {len(delivered)} pinned request models, expected at most 1"
    )
    return delivered[0] if delivered else None


def _carries(actual: Any, expected: Any) -> bool:
    """Every leaf the buyer sent survived into the delivered model, exactly.

    Recurses into nested objects instead of comparing whole dicts, because the
    pinned models legitimately add their own defaults when they parse a wire
    dict (``account`` becomes an ``Account`` with optional siblings). Exact
    equality is still demanded of every value the buyer actually sent — this
    tolerates model-added defaults, not a changed or missing value.
    """
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(_carries(actual.get(key), sub) for key, sub in expected.items())
    return actual == expected


# One realistic wire payload per lane-named tool. Each is a complete request
# for its schema (the pinned schemas mark account/idempotency_key/media_buy_id
# required on update_media_buy), so the seam has everything it needs to build
# the model — a partial payload would fail model construction for a reason
# that has nothing to do with the disposition rule under test.
SEAM_PAYLOADS: dict[str, dict[str, Any]] = {
    "update_media_buy": {
        "media_buy_id": "mb_seam_probe",
        "account": {"brand": {"domain": "acmeoutdoor.example"}, "operator": "pinnacle-agency.example"},
        "idempotency_key": "idem-seam-probe-update",
        "canceled": True,
        "cancellation_reason": "Campaign pulled by the brand.",
    },
    "sync_creatives": {
        "creatives": [],
        "account": {"brand": {"domain": "acmeoutdoor.example"}, "operator": "pinnacle-agency.example"},
        "idempotency_key": "idem-seam-probe-sync",
    },
    "get_products": {
        "brief": "Display inventory on outdoor lifestyle content. Q3 flight.",
        "buying_mode": "brief",
        "account": {"brand": {"domain": "acmeoutdoor.example"}, "operator": "pinnacle-agency.example"},
    },
}


@pytest.mark.parametrize("tool_name", spec_tool_names())
def test_published_schema_minus_honored_is_empty_for_body_semantic_fields(tool_name):
    """Plan §5's grader: published MCP schema MINUS honored == empty (body-semantic).

    Every field a tool advertises must be one of three things: accept-and-ignore
    (the spec-prose envelope class), declared on the tool's own signature (so it
    reaches the body by construction), or DISPOSED by the tool's code — read off
    the request it acts on, or refused with an explicit `AdCPError`. A field in
    none of those is published to buyers and silently dropped.

    HONORED is measured from what the tool's code actually CONSUMES, never from
    what the seam DELIVERS. The first version of this assertion computed
    `honored = declared | type(delivered).model_fields`, so merely handing a tool
    the pinned model marked every field of that model honored — it degenerated to
    "published minus CARRIED", which is empty by construction, and passed
    vacuously for the fourteen tools that never read the carrier at all.

    This also still pins reviewer note 2: the seam's model carrier must be kept
    OUT of the published MCP schema, or the carrier itself surfaces here as an
    unhonored body-semantic field.
    """
    undisposed = undisposed_fields(tool_name)
    ledgered = sorted(UNDISPOSED_LEDGER.get(tool_name, frozenset()))

    assert undisposed == ledgered, (
        f"{tool_name} advertises {len(undisposed)} body-semantic field(s) with no disposition: "
        f"{undisposed}. They are accepted on the wire and never reach any line of the tool's code, "
        f"so the buyer is told they were applied. Each owes a disposition: honored (read off the "
        f"request the tool acts on), or refused with an explicit AdCPError."
    )


@pytest.mark.parametrize("tool_name", sorted(SEAM_PAYLOADS))
def test_the_seam_delivers_the_pinned_request_model_to_the_tool_body(tool_name):
    """The hand-off channel exists and carries the buyer's values.

    Names the failure the test above reports as a set difference: there is no
    channel at all today, so no value the buyer sent can be honored no matter
    which field is inspected.
    """
    payload = SEAM_PAYLOADS[tool_name]
    delivered = _seam_delivered_request_model(tool_name, payload)

    assert delivered is not None, (
        f"{tool_name}: the seam delivered no pinned request model to the tool body. "
        f"Every field of {sorted(payload)} was accepted on the wire and dropped before the body."
    )
    dumped = delivered.model_dump(mode="json", exclude_none=True)
    for field, value in payload.items():
        assert _carries(dumped.get(field), value), (
            f"{tool_name}: the seam delivered a request model whose {field!r} is "
            f"{dumped.get(field)!r}, not the {value!r} the buyer sent"
        )


# ── Honor side: `canceled: true` on a LIVE buy must actually cancel it ────
#
# Without this, the whole invariant is satisfiable by REFUSING everywhere:
# T-UC-003-storyboard-not-cancellable-on-recancel reddens under the current
# strip only because a `canceled`-less request has no updatable fields
# (BR-RULE-022 -> INVALID_REQUEST), and a seller that rejected every cancel
# would green it. This is the assertion that makes "honored" mean honored.


def test_canceled_true_on_a_live_buy_actually_cancels_it(live_media_buy_env):
    """`canceled: true` must change the buy's state, not just return success.

    The honor arm of the two-way disposition rule. A seller that accepts the
    field and leaves the buy spending is the live regression this lane names;
    a seller that refuses every cancel passes the re-cancel scenario but fails
    here.

    Dispatches through ``AdCPTestClient`` (which sends the buyer's literal
    payload) rather than ``env.call_via`` — see the ``live_media_buy_env``
    fixture's note on ``_WRAPPER_UNSUPPORTED_FIELDS``.
    """
    from src.core.database.models import MediaBuy
    from tests.harness.client import AdCPTestClient

    env, media_buy = live_media_buy_env

    result = AdCPTestClient(env).call(
        "update_media_buy",
        {
            "media_buy_id": media_buy.media_buy_id,
            "canceled": True,
            "cancellation_reason": "Campaign pulled by the brand.",
        },
        Transport.MCP,
    )

    # NOT result.is_success: `update_media_buy` has no pinned response model, so
    # AdCPTestClient leaves payload=None on a SUCCESSFUL dispatch and is_success
    # is False by its documented contract ("a caller that needs the flat wire
    # dict for one of them reads result.wire_response directly"). Grading the
    # absence of an error and the presence of real wire is the same obligation
    # without depending on a parse the client cannot perform for this tool.
    assert result.error is None and result.wire_error_envelope is None, (
        f"update_media_buy(canceled=true) on an active buy failed: {result.wire_error_envelope or result.error}"
    )
    assert isinstance(result.wire_response, dict), (
        f"expected a real update_media_buy wire body, got {result.wire_response!r}"
    )
    persisted = env.get_one(MediaBuy, media_buy_id=media_buy.media_buy_id)
    assert persisted.status == "canceled", (
        f"The seller reported success but the buy is still {persisted.status!r} — "
        "accepted-and-dropped on the money path."
    )


# ── Refuse side: a REFUSED field must say so on the wire ──────────────────
#
# The refuse arm's behavioral grader, and the counterpart to the honor arm
# above. Until this existed the disposition rule was graded ONLY statically:
# `test_every_published_body_semantic_field_has_a_disposition` reads the tool's
# source and confirms a field is named somewhere, which says nothing about what
# a buyer who sends it actually receives. A refusal that raised the wrong code,
# or that a transport swallowed into a 500, would have been invisible.


@pytest.mark.parametrize("transport", [Transport.MCP, Transport.A2A, Transport.REST])
def test_a_refused_field_returns_unsupported_feature_on_the_wire(product_env, transport):
    """`get_products` REFUSES `time_budget`, and the buyer is told so in AdCP terms.

    Asserted on the wire envelope, not a reconstructed exception (tests/CLAUDE.md
    "Error Verification Policy"): reconstruction is lossy, and the point here is
    precisely what crosses the transport boundary. Run on MCP/A2A/REST because
    only those observe real wire bytes — IMPL has none.

    Contract: AdCP 3.1.1 UNSUPPORTED_FEATURE ("Requested feature not supported by
    this seller"), recovery `correctable` — the buyer removes the field and
    retries, which is why it must not surface as terminal or as a 500.
    """
    result = product_env.call_via(
        transport,
        brief="Display inventory on outdoor lifestyle content.",
        # A schema-VALID Duration ({interval, unit}), not a bare int: an invalid
        # value is rejected as VALIDATION_ERROR at the request boundary before
        # the refusal can fire, which would grade schema validation instead of
        # the disposition.
        time_budget={"interval": 30, "unit": "seconds"},
    )

    assert result.is_error, (
        f"get_products accepted `time_budget` on {transport.value} instead of refusing it. "
        "Its _UNSUPPORTED_GET_PRODUCTS_FIELDS map declares the field unimplemented, so accepting "
        "it silently is the accept-and-drop defect the disposition rule exists to prevent."
    )
    assert_envelope_shape(
        result.wire_error_envelope,
        "UNSUPPORTED_FEATURE",
        recovery="correctable",
        message_substr="time_budget",
    )

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
import inspect
from typing import Any

import pytest

from src.core.version_compat import accepts_spec_request_fields, spec_request_model
from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Verbatim from the pinned storyboard step, minus nothing.
STORYBOARD_SAMPLE_REQUEST = {
    "buying_mode": "brief",
    "brief": "Display inventory on outdoor lifestyle content. Q3 flight.",
    "filters": {"is_fixed_price": True},
    "account": {
        "brand": {"domain": "acmeoutdoor.example"},
        "operator": "pinnacle-agency.example",
    },
}


@pytest.fixture
def product_env(integration_db):
    with ProductEnv(tenant_id="spec-fields", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="spec-fields")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        # A product must carry at least one pricing option to serialize at all —
        # without it get_products fails with SERVICE_UNAVAILABLE, which would
        # make every case here fail for a reason that has nothing to do with
        # request-field acceptance.
        product = ProductFactory(tenant=tenant, delivery_type="guaranteed")
        PricingOptionFactory(product=product, pricing_model="cpm", rate="15.00", is_fixed=True, currency="USD")
        env.set_policy_approved()
        env.set_ranking_disabled()
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

# Plan step 1's accept-and-ignore class: the version/protocol envelope, which
# a seller MUST tolerate without acting on (AdCP 3.1.1
# building/by-layer/L1/security.mdx, "Server-side tool wrapper conformance";
# mirrored by src.core.version_compat.SPEC_ENVELOPE_FIELDS). Everything else a
# request schema defines carries body semantics and owes a disposition.
ENVELOPE_FIELDS = frozenset(
    {
        "adcp_version",
        "adcp_major_version",
        "context",
        "context_id",
        "governance_context",
    }
)

# `idempotency_key` is envelope-class on READS (nothing to de-duplicate) and
# body-semantic on WRITES (dropping it silently re-executes a retried write —
# the second live regression this lane exists to fix). Read-vs-write is taken
# from the SDK's own `readOnlyHint`, never a hand-maintained list.
IDEMPOTENCY_KEY = "idempotency_key"


def _is_read_tool(tool_name: str) -> bool:
    from src.core.main import ADCP_TOOL_DEFINITIONS

    for definition in ADCP_TOOL_DEFINITIONS:
        if definition["name"] == tool_name:
            return bool((definition.get("annotations") or {}).get("readOnlyHint"))
    raise AssertionError(f"{tool_name} has no SDK tool definition — cannot classify it as a read or a write")


def _envelope_fields_for(tool_name: str) -> frozenset[str]:
    """The accept-and-ignore class for one tool, read/write split applied."""
    if _is_read_tool(tool_name):
        return ENVELOPE_FIELDS | {IDEMPOTENCY_KEY}
    return ENVELOPE_FIELDS


def _published_input_fields(tool_name: str) -> frozenset[str]:
    """The properties a tool actually ADVERTISES over MCP.

    The registered tool's published input schema — what a buyer sees from
    `tools/list` and what FastMCP validates against — not
    `inspect.signature(main.<tool>)`, which is the UNDECORATED function
    (acceptance is applied at registration, src/core/main.py:_register_tool).
    Same derivation as tests/unit/test_architecture_spec_request_fields.py.
    """
    from src.core.main import mcp

    tool = asyncio.run(mcp.get_tool(tool_name))
    assert tool is not None, f"{tool_name} is no longer registered with the MCP server"
    return frozenset(tool.parameters.get("properties", {}))


def _declared_params(tool_name: str) -> frozenset[str]:
    """Parameters the tool's own function signature declares.

    These reach the tool body by construction, so they are honored whatever
    the seam does.
    """
    import src.core.main as main_module

    undecorated = getattr(main_module, tool_name)
    return frozenset(inspect.signature(undecorated).parameters)


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


@pytest.mark.parametrize("tool_name", sorted(SEAM_PAYLOADS))
def test_published_schema_minus_honored_is_empty_for_body_semantic_fields(tool_name):
    """Plan §5's grader: published MCP schema MINUS honored == empty (body-semantic).

    Every field a tool advertises must be one of three things: envelope-class
    (accept-and-ignore, plan step 1), declared on the tool's own signature (so
    it reaches the body by construction), or delivered to the body by the seam
    inside the pinned request model. A field in none of those is published to
    buyers and silently dropped — accept-and-drop, the thing the Core Invariant
    forbids. The remaining escape, refusing the field outright, removes it from
    `accepted_names` and therefore from the published schema, so it never
    reaches this subtraction at all.

    Note this also pins reviewer note 2: the seam's model carrier must be kept
    OUT of the published MCP schema (`version_compat.py` builds
    `decorated.__signature__` from the original parameters plus its additions),
    or the carrier itself shows up here as an unhonored body-semantic field.
    """
    published = _published_input_fields(tool_name)
    delivered = _seam_delivered_request_model(tool_name, SEAM_PAYLOADS[tool_name])
    honored = _declared_params(tool_name) | (
        frozenset(type(delivered).model_fields) if delivered is not None else frozenset()
    )

    unhonored = sorted(published - _envelope_fields_for(tool_name) - honored)

    assert unhonored == [], (
        f"{tool_name} advertises {len(unhonored)} body-semantic field(s) that never reach the tool "
        f"body: {unhonored}. They are accepted on the wire and stripped before the body "
        f"(version_compat.py _strip), so the buyer is told they were applied. Each owes a "
        f"disposition: threaded into the pinned request model (honored, or refused there with an "
        f"explicit AdCPError), or removed from accepted_names so the transport refuses it loudly."
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

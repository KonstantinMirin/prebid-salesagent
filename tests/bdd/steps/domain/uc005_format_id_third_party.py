"""UC-005 storyboard: third-party format_id (foreign agent_url) is an observation, not a failure.

Scenario ``T-UC-005-storyboard-format-id-third-party-agent-out-of-scope``
(@third-party-agent): when a product advertises a ``format_id`` whose ``agent_url``
points at a creative agent OTHER than this seller, the seller cannot verify it
locally. Per the ``list_formats`` storyboard step such a reference is OUT OF
SCOPE — ``scope.equals=$agent_url`` with ``on_out_of_scope: warn`` — so the seller
MUST NOT fabricate a local format entry to cover it, and an empty result is an
observation, never a graded failure.

Wired to real production across a2a/mcp/rest (auto-parametrized; UC-005 →
CreativeFormatsEnv). Falsifiability comes from the COLLISION setup: the seller's own
catalog holds a format whose ``id`` matches the third-party reference but under the
SELLER's ``agent_url``. A filter comparing ``id`` alone would return that local
format as if it satisfied the third-party reference; the v3.1 ``(agent_url, id)``
federation filter (``format_id_identity``) returns nothing, which is the correct
observation. Both the production filter fix and the REST harness fix
(``build_rest_body`` now transmits ``format_ids``) are required for this to hold on
all three transports.

The scenario's expected outcome is otherwise entirely NEGATIVE, so it carries a
POSITIVE CONTROL (third Given): the same call on the same transport with the
SELLER's ``(agent_url, id)`` must resolve to exactly that pair. Without it the
scenario passes on an empty ``formats[]`` for any reason at all — unreachable
creative agent, catalog drift, a 200 carrying an errors array — and cannot tell
"correctly returned nothing" from "returns nothing". Local scenario edit; mirror
upstream (#1600, follows #1585). Assertions read the serialized wire
(``_serialized_formats`` + ``wire_format_id_identity``), matching the two sibling
UC-005 format_id scenarios.

@source repo=adcp ref=v3.1.0-beta.3
  path=static/compliance/source/protocols/media-buy/index.yaml
  (step list_formats, refs_resolve: match_keys [agent_url, id], scope.equals $agent_url, on_out_of_scope: warn)
"""

from __future__ import annotations

from pytest_bdd import given, then, when

from src.core.schemas import FormatId, ListCreativeFormatsRequest, format_id_identity
from tests.bdd.steps._outcome_helpers import _require_response
from tests.bdd.steps.domain.uc005_format_id_shape import _assert_formats_non_empty, _serialized_formats
from tests.bdd.steps.generic.when_request import _call
from tests.factories import FormatFactory
from tests.helpers.format_assertions import wire_format_id_identity

# The seller's own creative agent — matches the agent_url the CreativeFormatsEnv
# mock catalog uses, so a seeded format reads as "hosted by this seller".
SELLER_AGENT_URL = "https://creative.adcontextprotocol.org"
# A DIFFERENT creative agent the seller does not proxy — the out-of-scope reference.
THIRD_PARTY_AGENT_URL = "https://third-party-creative.example.com"
# Shared id: the third-party reference and the seller's local catalog entry collide
# on id so the test can prove discrimination is on agent_url, not id.
COLLIDING_FORMAT_ID = "display_300x250_image"


@given("a product advertises a format_id whose agent_url points at a third-party creative agent")
def given_product_advertises_third_party_format_id(ctx: dict) -> None:
    """Capture the format_id a product carries, hosted by a third-party agent."""
    ctx["third_party_format_id"] = FormatId(agent_url=THIRD_PARTY_AGENT_URL, id=COLLIDING_FORMAT_ID)


@given("the seller has no local copy of that format in its own catalog")
def given_seller_has_no_local_copy(ctx: dict) -> None:
    """Seed the seller catalog with ONLY a same-id format under the seller's own agent_url.

    The seller has no copy of the *third-party* format. This same-id/own-agent_url
    collision is the falsifier: an id-only filter would wrongly surface this local
    entry for the third-party reference; the (agent_url, id) filter must not.
    """
    fid: FormatId = ctx["third_party_format_id"]
    local = FormatFactory(format_id=FormatId(agent_url=SELLER_AGENT_URL, id=fid.id))
    ctx["env"].set_registry_formats([local])


@given("list_creative_formats resolves the seller's own agent_url plus that same id to exactly that format")
def given_seller_own_format_resolves(ctx: dict) -> None:
    """POSITIVE CONTROL: prove the id collision is live on THIS transport, THIS run.

    Issues the SAME ``list_creative_formats`` call on the SAME transport with the
    SELLER's ``(agent_url, id)`` and requires it to resolve to exactly that pair.
    Without this control the scenario's outcome is entirely negative — no fabricated
    entry — and an empty ``formats[]`` satisfies it for ANY reason (creative agent
    unreachable, catalog drift, a 200 carrying an errors array). With it, the empty
    third-party result is evidence of ``(agent_url, id)`` discrimination rather than
    evidence of nothing. Local scenario edit, mirror upstream (#1600, follows #1585).

    Reads the serialized WIRE (``_serialized_formats``), like the two sibling UC-005
    format_id scenarios, and clears the control's response so a later transport error
    cannot leave stale control data for the Then steps to assert against.
    """
    seller_format_id = FormatId(agent_url=SELLER_AGENT_URL, id=COLLIDING_FORMAT_ID)
    _call(ctx, req=ListCreativeFormatsRequest(format_ids=[seller_format_id]))

    assert ctx.get("error") is None, (
        f"positive control failed: resolving the seller's OWN format {format_id_identity(seller_format_id)} "
        f"raised {ctx.get('error')!r}. The third-party empty result would prove nothing."
    )
    formats = _assert_formats_non_empty(
        ctx,
        f"positive control failed: the seller's OWN {format_id_identity(seller_format_id)} resolved to an "
        "empty formats[]. The id collision this scenario relies on does not exist for this run, so an "
        "empty third-party result is evidence of nothing (catalog drift or an unreachable creative agent).",
    )
    assert len(formats) == 1, (
        f"positive control: expected exactly the seller's own format for {format_id_identity(seller_format_id)}, "
        f"got {[f['format_id'] for f in formats]}"
    )
    assert wire_format_id_identity(formats[0]["format_id"]) == format_id_identity(seller_format_id), (
        f"positive control: formats[0].format_id is {formats[0]['format_id']!r}, expected the seller pair "
        f"{format_id_identity(seller_format_id)}"
    )

    # The control's own result must not leak into the Then steps: they assert on the
    # third-party dispatch, and a failed dispatch would otherwise read this response.
    ctx.pop("response", None)
    ctx.pop("wire_response", None)


@when("the Buyer Agent sends list_creative_formats with that third-party format_id")
def when_send_list_with_third_party_format_id(ctx: dict) -> None:
    """Dispatch list_creative_formats filtered by the third-party format_id (all transports)."""
    req = ListCreativeFormatsRequest(format_ids=[ctx["third_party_format_id"]])
    _call(ctx, req=req)


@then("the seller should NOT fabricate a local format entry to satisfy the third-party reference")
def then_no_fabricated_local_entry(ctx: dict) -> None:
    """No returned format is the third-party reference, nor a substituted local same-id format.

    Reads the serialized WIRE (``_serialized_formats``) like the two sibling UC-005
    format_id scenarios — the typed payload cannot observe a serialization regression.
    ``_require_response`` first, so a dispatch that errored surfaces its recorded error
    instead of a bare missing-wire assertion.
    """
    _require_response(ctx)
    returned = {wire_format_id_identity(entry["format_id"]) for entry in _serialized_formats(ctx)}

    third_party = format_id_identity(ctx["third_party_format_id"])
    assert third_party not in returned, (
        f"seller fabricated a third-party-attributed entry {third_party} it does not host: {returned}"
    )

    # Falsifiable core: the seller's own same-id format must NOT be substituted for
    # the foreign reference. id-only matching would surface it here.
    seller_local = (SELLER_AGENT_URL, ctx["third_party_format_id"].id)
    assert seller_local not in returned, (
        f"seller substituted its own format {seller_local} for the third-party reference "
        f"{third_party}; the federation filter must match on (agent_url, id), not id alone"
    )


@then("the verification result should be reported as an observation rather than a graded failure")
def then_reported_as_observation(ctx: dict) -> None:
    """An unresolvable foreign reference is a successful (empty) result, not an error envelope."""
    assert ctx.get("error") is None, (
        f"out-of-scope third-party reference raised an error instead of an observation: {ctx.get('error')!r}"
    )
    _require_response(ctx)
    # The foreign reference resolves to nothing locally — that empty match is the
    # observation (on_out_of_scope: warn), distinct from a graded failure/error.
    # Read on the wire, the buyer-facing surface (siblings do the same).
    third_party = format_id_identity(ctx["third_party_format_id"])
    returned = {wire_format_id_identity(entry["format_id"]) for entry in _serialized_formats(ctx)}
    assert third_party not in returned, (
        f"the foreign reference {third_party} came back as a resolved format on the wire: {sorted(returned)}"
    )

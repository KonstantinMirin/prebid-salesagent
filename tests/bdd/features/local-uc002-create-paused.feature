# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# SPEC GROUNDING — adcp v3.1.1 (the pin this capability targets),
# git show v3.1.1:dist/schemas/3.1.1/media-buy/create-media-buy-request.json,
# properties.paused = {type: boolean, default: false}:
#
#   "Create the media buy in a paused delivery state. When true, and the buy would
#    otherwise be active because creatives are assigned and the flight has started,
#    the seller returns media_buy_status "paused". Setup blockers still take
#    precedence: a buy with no creatives remains "pending_creatives", and a
#    future-dated buy remains "pending_start" until its flight can start.
#    Defaults to false."
#
# CONFORMANCE STORYBOARD: UNGRADED. No scenario under
# dist/compliance/3.1.1/protocols/media-buy/scenarios/ exercises create-time paused
# (both `paused` hits — available_actions.yaml, invalid_transitions.yaml — are
# update_media_buy). The JSON-schema description above is therefore the contract.
# GH #1619.
#
# WHAT THIS FILE GRADES (create surface): the buyer's paused intent survives the
# transport boundary on EVERY transport and is carried into the buy the seller
# books — the packages the seller reports are paused, and the buy is persisted
# with the paused delivery flag that the read surface's precedence rule consumes.
#
# The REST leg is the one that regressed: CreateMediaBuyBody declared `paused` but
# the route never forwarded it to create_media_buy_raw, so a REST buyer's
# paused:true was dropped in silence and the buy delivered (chris #1585 A1).
#
# The READ-side precedence is graded separately, in
# local-uc019-paused-status-precedence.feature (+ the generated BR-UC-019
# @T-UC-019-inv-150-6 for the in-flight partition).
#
# NOTE on the create-response status: a create request's creatives are never
# pre-approved (src/core/tools/media_buy_create.py sets creatives_approved=False
# whenever a request carries creatives), so a freshly created buy can never be
# "active" — hence never "paused" — on the create response. That is the spec's own
# precedence ("setup blockers still take precedence"), graded by the second
# scenario below, and it is why `paused` is persisted as an intent flag rather
# than as a persisted status.

Feature: UC-002 create_media_buy — create in a paused delivery state (local, AdCP 3.1.1)

  @T-UC-002-local-create-paused @schema-v3.1.1
  Scenario: create_media_buy with paused true books a paused buy
    Given a valid create_media_buy request
    And the create request sets paused true
    When the Buyer Agent sends the create_media_buy request
    Then every package in the create response reports paused true
    And the persisted media buy has is_paused true

  @T-UC-002-local-create-paused-precedence @schema-v3.1.1
  Scenario: a paused create with no creatives still reports pending_creatives
    Given a valid create_media_buy request
    And the create request sets paused true
    When the Buyer Agent sends the create_media_buy request
    Then the wire media_buy_status should be "pending_creatives"

  @T-UC-002-local-create-paused-manual @schema-v3.1.1
  Scenario: a paused create awaiting manual approval books paused packages
    Given a valid create_media_buy request
    And the create request sets paused true
    And the tenant requires manual approval
    When the Buyer Agent sends the create_media_buy request
    Then the persisted media buy has is_paused true
    And every persisted package carries paused true

  @T-UC-002-local-create-unpaused @schema-v3.1.1
  Scenario: create_media_buy without paused books an unpaused buy
    Given a valid create_media_buy request
    When the Buyer Agent sends the create_media_buy request
    Then every package in the create response reports paused false
    And the persisted media buy has is_paused false

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
# dist/compliance/3.1.1/protocols/media-buy/scenarios/ exercises create-time paused —
# the only two `paused` hits (available_actions.yaml, invalid_transitions.yaml) are
# update_media_buy. The JSON-schema description above is therefore the contract.
# GH #1619.
#
# WHAT THIS FILE GRADES: the READ-surface half of that sentence — the status
# PRECEDENCE a paused buy is reported under:
#
#     pending_creatives  >  pending_start  >  paused  >  active
#
# i.e. `paused` surfaces only when the buy would OTHERWISE be active. Before
# GH #1619 the shared resolver (src/core/tools/_media_buy_status.py) returned
# "paused" for is_paused BEFORE refining against the flight window, so a paused
# future-dated buy wrongly read "paused" instead of "pending_start".
#
# The fourth partition — in-flight + paused -> "paused" — is already graded by the
# generated BR-UC-019 scenario @T-UC-019-inv-150-6 (persisted "active",
# is_paused true, window 2026-03-01..2026-03-31, today 2026-03-15). It is NOT
# duplicated here; it is the behaviour-preservation tripwire for the reorder.
#
# The post-flight row is a DERIVED consequence of the same sentence rather than a
# literal clause of it: a completed buy is not one that "would otherwise be
# active", so paused does not override it. Recorded here so the ordering change is
# graded rather than silent.
#
# Windows are deliberately far-future / far-past instead of a patched clock, so
# every transport (including a live-server e2e_rest run, where an in-process
# datetime patch is invisible) evaluates the same partition.

Feature: UC-019 get_media_buys — paused status precedence (local, AdCP 3.1.1)

  @T-UC-019-local-paused-pending-creatives @schema-v3.1.1
  Scenario: a paused buy with no creatives still reports pending_creatives
    Given the principal "buyer-001" owns media buy "mb-001" with persisted status "pending_creatives" and is_paused true
    When the Buyer Agent sends a get_media_buys request for media_buy_ids ["mb-001"]
    Then the media buy "mb-001" should have status "pending_creatives"

  @T-UC-019-local-paused-pending-start @schema-v3.1.1
  Scenario: a paused buy whose flight has not started still reports pending_start
    Given the principal "buyer-001" owns media buy "mb-001" with persisted status "active" and is_paused true
    And media buy "mb-001" has start_date "2099-01-01" and end_date "2099-12-31"
    When the Buyer Agent sends a get_media_buys request for media_buy_ids ["mb-001"]
    Then the media buy "mb-001" should have status "pending_start"

  @T-UC-019-local-paused-completed @schema-v3.1.1
  Scenario: a paused buy whose flight has ended reports completed
    Given the principal "buyer-001" owns media buy "mb-001" with persisted status "active" and is_paused true
    And media buy "mb-001" has start_date "2020-01-01" and end_date "2020-12-31"
    When the Buyer Agent sends a get_media_buys request for media_buy_ids ["mb-001"]
    Then the media buy "mb-001" should have status "completed"

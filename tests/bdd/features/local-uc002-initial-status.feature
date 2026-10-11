# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# What it grades: the status a buy starts in when create_media_buy assigns it creatives that
# are already approved. AdCP 3.1.1 enums/media-buy-status.json: `pending_creatives` is a buy
# that "has no creatives assigned — the buyer must attach creatives via `sync_creatives`
# before the buy can serve"; `pending_start` is "ready to serve and waiting for its flight
# date to begin"; `active` is "currently running". docs/media-buy/media-buys/lifecycle.mdx
# line 146: "`create_media_buy` accepts inline `creative_assignments` or `creatives` per
# package. If you supply them at creation time and the flight date has passed, the buy
# enters `active` directly ... If the flight date is in the future, it enters
# `pending_start`". The buyer observes the status on the create response and on
# get_media_buys.
#
# The state-machine storyboard's create_buy step grades the same transition, but it requires
# media_buy.creative_approval_mode auto_approve, which this seller does not declare, and it
# assigns the creative through creative_assignments, which create does not read (#2392). These
# scenarios are the in-process grading of that obligation, on a tenant that auto-approves
# creatives, with the creative uploaded inline on the package.
#
# Not graded here: a buy whose assigned creatives are still under review keeps
# `pending_creatives` (whether it should is #2399), and a package naming an approved library
# creative by id goes through the same status decision as the inline upload.
#
# Transports: a2a, mcp, rest and e2e_rest.
#
# @source repo=adcp ref=v3.1.1 path=dist/schemas/3.1.1/enums/media-buy-status.json
# @source repo=adcp ref=v3.1.1 path=docs/media-buy/media-buys/lifecycle.mdx
# @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/domains/media-buy/state-machine.yaml pointer=/phases/setup/steps/create_buy
Feature: A media buy created with approved creatives starts in its flight state (local)

  @T-UC-002-local-initial-status-approved-creatives @extension
  Scenario Outline: A buy whose package carries an approved creative is <status>, not pending_creatives
    Given a valid create_media_buy request with:
      | field      | value              |
      | start_time | <start>            |
      | end_time   | {30 days from now} |
    And the account exists and is active
    And the tenant has approval_mode "auto-approve"
    And the product "prod-1" supports format_ids ["display_300x250_image"]
    And the request's package carries an inline image creative in its product's format
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And the wire media_buy_status should be "<status>"
    When the Buyer Agent calls get_media_buys for the media buy it just created
    Then the included entry should expose the same media_buy_id and status "<status>"

    Examples:
      | start             | status        |
      | asap              | active        |
      | {7 days from now} | pending_start |

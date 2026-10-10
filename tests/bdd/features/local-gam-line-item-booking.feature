# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# NOT a protocol obligation. AdCP 3.1.1 is silent on how a seller traffics a package in
# its ad server. What the buyer sends is the input -- each package's own `budget` and the
# `pricing_option_id` naming a fixed-price option (media-buy/package-request.json,
# pricing-options/cpm-option.json `fixed_price`) -- and the line item the seller books in
# Google Ad Manager is the output. The invariants are the ad server's own contract and
# this repo's product configuration:
#
#   GAM API v202605 ForecastService.GoalType: LIFETIME is "a goal on the number of ads
#   delivered for this line item during its entire lifetime" and applies to STANDARD,
#   BULK, PRICE_PRIORITY; DAILY is "a daily goal" and applies to SPONSORSHIP, NETWORK,
#   PRICE_PRIORITY, HOUSE. A STANDARD line item therefore books LIFETIME, whatever the
#   product's primary_goal_type says, and its units are the whole flight's.
#
#   GAM API v202605 LineItemSummary.priority: "defaults to the default priority of the
#   LineItemType", within a per-type range -- STANDARD 8 (6..10), PRICE_PRIORITY 12
#   (11..14), SPONSORSHIP 4 (2..5).
#
#   docs/adapters/gam/product-configuration.md: implementation_config.priority is the
#   product's configured priority, set in the Admin UI. A configured priority GAM accepts
#   for the line item type is the one booked; one outside the type's range books the
#   type's default.
#
# WHO OBSERVES IT. The ad server. Each Then reads the line items the seller sent to the
# Google Ad Manager stand-in (MediaBuyCreateEnv.sell_through_gam: the only replaced piece
# is GAM's SOAP client). The live e2e stack has no GAM network, so the env declares the
# seller unrealizable there.
#
# Ungraded by the conformance storyboards.

Feature: A Google Ad Manager line item carries its package's goal and its product's priority (local)

  Background:
    Given the tenant sells through Google Ad Manager on a network in time zone "America/New_York"

  @T-UC-002-ext-gam-line-item-goal @extension
  Scenario: each guaranteed fixed-CPM package books a lifetime goal its own budget buys at its own price
    Given a guaranteed GAM product "display_10" at a fixed 10.00 USD CPM, configured with priority 6 and a DAILY goal
    And a guaranteed GAM product "display_12" at a fixed 12.00 USD CPM, configured with priority 6 and a DAILY goal
    When the Buyer Agent creates a 14-day media buy with packages "display_10:500.00, display_12:500.00"
    Then the buyer receives the GAM order as its media buy
    And the GAM line item for "display_10" books a LIFETIME goal of 50000 IMPRESSIONS
    And the GAM line item for "display_12" books a LIFETIME goal of 41666 IMPRESSIONS

  @T-UC-002-ext-gam-line-item-daily-goal @extension
  Scenario: a price-priority package with a daily goal books its lifetime volume spread over the flight's days
    Given a non_guaranteed GAM product "remnant_12" at a fixed 12.00 USD CPM, configured with priority 12 and a DAILY goal
    When the Buyer Agent creates a 14-day media buy with packages "remnant_12:500.00"
    Then the buyer receives the GAM order as its media buy
    And the GAM line item for "remnant_12" books a DAILY goal of 2976 IMPRESSIONS

  @T-UC-002-ext-gam-line-item-priority @extension
  Scenario Outline: the product's configured priority is booked when GAM allows it for the line item type
    Given a <delivery> GAM product "prio" at a fixed 10.00 USD CPM, configured with priority <configured> and a <goal> goal
    When the Buyer Agent creates a 14-day media buy with packages "prio:500.00"
    Then the buyer receives the GAM order as its media buy
    And the GAM line item for "prio" is a <line_item_type> line item at priority <booked>

    Examples: configured priority inside the type's range
      | delivery       | configured | goal     | line_item_type | booked |
      | guaranteed     | 6          | DAILY    | STANDARD       | 6      |
      | guaranteed     | 10         | LIFETIME | STANDARD       | 10     |
      | non_guaranteed | 13         | NONE     | PRICE_PRIORITY | 13     |

    Examples: configured priority outside the type's range books the type's default
      | delivery       | configured | goal     | line_item_type | booked |
      | guaranteed     | 4          | DAILY    | STANDARD       | 8      |
      | non_guaranteed | 10         | NONE     | PRICE_PRIORITY | 12     |

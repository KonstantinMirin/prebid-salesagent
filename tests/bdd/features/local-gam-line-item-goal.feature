# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# What it grades: the type, priority and goal of each line item a Google Ad Manager seller
# books for a buyer's create_media_buy, on the create path and on the seller's approval.
#
# AdCP 3.1.1 create_media_buy.mdx, Package Object: every package carries its own
# `pricing_option_id` ("Pricing option ID from product's pricing_options array") and its own
# `budget` ("Budget in currency specified by pricing option"), and an auction package its
# `bid_price`. pricing-models.mdx: CPM is the "Cost per 1,000 impressions", and "Budgets are
# always denominated at the fixed_price level ... that €10,000 is the buyer's cost". So a
# per-unit package's volume is its own budget at its selected option's unit price, and a
# flat-rate package is a "Fixed cost for the entire campaign period regardless of delivery
# volume".
#
# Google Ad Manager API (LineItem.priority, Goal.goalType, Goal.units): a line item type
# accepts priorities in its own range (SPONSORSHIP 2-5, default 4; STANDARD 6-10, default 8;
# NETWORK, BULK and PRICE_PRIORITY 11-14, default 12; HOUSE 15-16, default 16). STANDARD and
# BULK take a LIFETIME goal; SPONSORSHIP, NETWORK and HOUSE take a DAILY goal whose units are a
# percentage of impressions; PRICE_PRIORITY takes LIFETIME, DAILY or NONE. A seller
# misconfiguration is refused with CONFIGURATION_ERROR (enums/error-code.json, recovery
# terminal), before anything is written to GAM.
#
# The sales-guaranteed storyboard's create_media_buy step sends two packages with different
# budgets and validates only the response schema, so these scenarios grade the booking
# in-process: the real GoogleAdManager adapter runs, and only Google's SOAP client is stood in.
#
# Transports: a2a, mcp and rest. The live server has no stand-in GAM network, so the setup
# declares itself unrealizable on e2e (GamSellerMixin.sell_through_gam).
#
# @source repo=adcp ref=v3.1.1 path=docs/media-buy/task-reference/create_media_buy.mdx
# @source repo=adcp ref=v3.1.1 path=docs/media-buy/advanced-topics/pricing-models.mdx
# @source repo=adcp ref=v3.1.1 path=static/schemas/source/enums/error-code.json
# @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/specialisms/sales-guaranteed/index.yaml pointer=/phases/create_buy
Feature: A Google Ad Manager seller books each package's own volume, type, priority and goal (local)

  @T-UC-002-local-gam-goal-per-package @extension
  Scenario: Each package's line item books that package's budget at the price of the option it selected
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's guaranteed products have pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_standard  | cpm           | 12.00       |             |
      | prod_a     | cpm_usd_premium   | cpm           | 20.00       |             |
      | prod_b     | cpm_usd_standard  | cpm           | 12.00       |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001"
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | cpm_usd_premium   | 600    |           |
      | prod_b     | cpm_usd_standard  | 420    |           |
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And Google Ad Manager received these line items, in package order:
      | lineItemType | priority | goalType | unitType    | units |
      | STANDARD     | 8        | LIFETIME | IMPRESSIONS | 30000 |
      | STANDARD     | 8        | LIFETIME | IMPRESSIONS | 35000 |

  @T-UC-002-local-gam-goal-approved @extension
  Scenario: A buy the seller approves books each package's budget at the price of the option it selected
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's guaranteed products have pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_standard  | cpm           | 12.00       |             |
      | prod_a     | cpm_usd_premium   | cpm           | 20.00       |             |
      | prod_b     | cpm_usd_standard  | cpm           | 12.00       |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001"
    And the tenant requires manual approval
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | cpm_usd_premium   | 600    |           |
      | prod_b     | cpm_usd_standard  | 420    |           |
    When the Buyer Agent sends the create_media_buy request
    Then the response status should be "submitted"
    When the seller approves the media buy
    Then Google Ad Manager received these line items, in package order:
      | lineItemType | priority | goalType | unitType    | units |
      | STANDARD     | 8        | LIFETIME | IMPRESSIONS | 30000 |
      | STANDARD     | 8        | LIFETIME | IMPRESSIONS | 35000 |

  @T-UC-002-local-gam-goal-price-priority @extension
  Scenario Outline: A price-priority line item's goal units follow the goal type the product configures
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's non-guaranteed product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_auction   | cpm           |             | 1.00        |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001", with product settings '{"primary_goal_type": "<configured>"}'
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | cpm_usd_auction   | 560    | 4.00      |
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And Google Ad Manager received these line items, in package order:
      | lineItemType   | priority | goalType   | unitType    | units   |
      | PRICE_PRIORITY | 12       | <goalType> | IMPRESSIONS | <units> |

    Examples:
      | configured | goalType | units  |
      | LIFETIME   | LIFETIME | 140000 |
      | DAILY      | DAILY    | 10000  |

  @T-UC-002-local-gam-type-priority @extension
  Scenario Outline: A CPM package books the product's configured priority, and a share-of-voice type only for flat rate
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's guaranteed product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_standard  | cpm           | 12.00       |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001", with product settings '<settings>'
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | cpm_usd_standard  | 420    |           |
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And Google Ad Manager received these line items, in package order:
      | lineItemType | priority   | goalType   | unitType    | units   |
      | <type>       | <priority> | <goalType> | IMPRESSIONS | <units> |

    Examples:
      | settings                                         | type     | priority | goalType | units |
      | {}                                               | STANDARD | 8        | LIFETIME | 35000 |
      | {"primary_goal_type": "DAILY"}                   | STANDARD | 8        | LIFETIME | 35000 |
      | {"priority": 6}                                  | STANDARD | 6        | LIFETIME | 35000 |
      | {"priority": 10}                                 | STANDARD | 10       | LIFETIME | 35000 |
      | {"line_item_type": "NETWORK"}                    | STANDARD | 8        | LIFETIME | 35000 |
      | {"line_item_type": "SPONSORSHIP", "priority": 5} | STANDARD | 8        | LIFETIME | 35000 |
      | {"line_item_type": "HOUSE"}                      | STANDARD | 8        | LIFETIME | 35000 |

  @T-UC-002-local-gam-type-flat-rate @extension
  Scenario Outline: A flat-rate package books the product's configured type when that type can sell it at a fixed price
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's guaranteed product has pricing options:
      | product_id | pricing_option_id         | pricing_model | fixed_price | floor_price |
      | prod_a     | flat_rate_usd_sponsorship | flat_rate     | 7000.00     |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001", with product settings '<settings>'
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id         | budget | bid_price |
      | prod_a     | flat_rate_usd_sponsorship | 7000   |           |
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And Google Ad Manager received these line items, in package order:
      | lineItemType | priority   | goalType | unitType    | units |
      | <type>       | <priority> | DAILY    | IMPRESSIONS | 100   |

    Examples:
      | settings                                      | type        | priority |
      | {"line_item_type": "STANDARD"}                | SPONSORSHIP | 4        |
      | {"line_item_type": "NETWORK"}                 | NETWORK     | 12       |
      | {"line_item_type": "NETWORK", "priority": 11} | NETWORK     | 11       |

  @T-UC-002-local-gam-priority-refused @extension
  Scenario Outline: A configured priority outside the booked type's range is refused before anything reaches GAM
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's guaranteed product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_standard  | cpm           | 12.00       |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001", with product settings '{"priority": <priority>}'
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | cpm_usd_standard  | 420    |           |
    When the Buyer Agent sends the create_media_buy request
    Then the error code should be "CONFIGURATION_ERROR"
    And the error recovery should be "terminal"
    And Google Ad Manager received no order

    Examples:
      | priority |
      | 12       |
      | 17       |

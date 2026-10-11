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
# percentage of impressions; PRICE_PRIORITY takes LIFETIME, DAILY or NONE. The goal is in the
# unit the package is sold in (Goal.unitType): IMPRESSIONS for CPM, VIEWABLE_IMPRESSIONS for
# vCPM. The line item is billed at the selected option's unit price (LineItem.costType and
# costPerUnit); a flat-rate price is billed per day (CPD) over the flight's days. A seller
# misconfiguration is refused with CONFIGURATION_ERROR (enums/error-code.json, recovery
# terminal) before anything is written to GAM. On the seller's approval the same refusal
# tells the seller the product, the setting and the rejected value, nothing is written to
# GAM, and the buy is not marked failed: its status stays pending_approval. Whether the
# Admin UI then offers a second approval is decided by the approval workflow step, which
# these scenarios do not drive (#2414).
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
      | lineItemType | priority | costType | costPerUnitMicros | goalType | unitType    | units |
      | STANDARD     | 8        | CPM      | 20000000          | LIFETIME | IMPRESSIONS | 30000 |
      | STANDARD     | 8        | CPM      | 12000000          | LIFETIME | IMPRESSIONS | 35000 |

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
    Then the seller's approval books the media buy
    And Google Ad Manager received these line items, in package order:
      | lineItemType | priority | costType | costPerUnitMicros | goalType | unitType    | units |
      | STANDARD     | 8        | CPM      | 20000000          | LIFETIME | IMPRESSIONS | 30000 |
      | STANDARD     | 8        | CPM      | 12000000          | LIFETIME | IMPRESSIONS | 35000 |

  @T-UC-002-local-gam-goal-price-priority @extension
  Scenario Outline: A price-priority line item's goal units follow the goal type the product configures
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's non-guaranteed product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_auction   | cpm           |             | 1.00        |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001", with product settings '{"primary_goal_type": "<configured>"}'
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget   | bid_price |
      | prod_a     | cpm_usd_auction   | <budget> | <bid>     |
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And Google Ad Manager received these line items, in package order:
      | lineItemType   | priority | costType | costPerUnitMicros | goalType   | unitType    | units   |
      | PRICE_PRIORITY | 12       | CPM      | <micros>          | <goalType> | IMPRESSIONS | <units> |

    # The line item is billed at the package's bid, not at the option's 1.00 floor.
    # 425 at 12.00 buys 35416.67 impressions: the volume is floored, so it never costs more
    # than the budget, and a DAILY goal floors the spread over 14 days (2529.76).
    Examples:
      | configured | budget | bid   | micros   | goalType | units  |
      | LIFETIME   | 560    | 4.00  | 4000000  | LIFETIME | 140000 |
      | DAILY      | 560    | 4.00  | 4000000  | DAILY    | 10000  |
      | NONE       | 425    | 12.00 | 12000000 | NONE     | 35416  |
      | DAILY      | 425    | 12.00 | 12000000 | DAILY    | 2529   |

  @T-UC-002-local-gam-type-priority @extension
  Scenario Outline: A per-unit package books the product's configured priority, and a share-of-voice type only for flat rate
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's <delivery> product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | <option>          | <model>       | 12.00       |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001", with product settings '<settings>'
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | <option>          | 420    |           |
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And Google Ad Manager received these line items, in package order:
      | lineItemType | priority   | costType   | costPerUnitMicros | goalType   | unitType   | units |
      | <type>       | <priority> | <costType> | 12000000          | <goalType> | <unitType> | 35000 |

    Examples:
      | delivery       | option            | model | settings                                         | type           | priority | costType | goalType | unitType             |
      | guaranteed     | cpm_usd_standard  | cpm   | {}                                               | STANDARD       | 8        | CPM      | LIFETIME | IMPRESSIONS          |
      | guaranteed     | cpm_usd_standard  | cpm   | {"primary_goal_type": "DAILY"}                   | STANDARD       | 8        | CPM      | LIFETIME | IMPRESSIONS          |
      | guaranteed     | cpm_usd_standard  | cpm   | {"priority": 6}                                  | STANDARD       | 6        | CPM      | LIFETIME | IMPRESSIONS          |
      | guaranteed     | cpm_usd_standard  | cpm   | {"priority": 10}                                 | STANDARD       | 10       | CPM      | LIFETIME | IMPRESSIONS          |
      | guaranteed     | cpm_usd_standard  | cpm   | {"line_item_type": "NETWORK"}                    | STANDARD       | 8        | CPM      | LIFETIME | IMPRESSIONS          |
      | guaranteed     | cpm_usd_standard  | cpm   | {"line_item_type": "SPONSORSHIP", "priority": 5} | STANDARD       | 8        | CPM      | LIFETIME | IMPRESSIONS          |
      | guaranteed     | cpm_usd_standard  | cpm   | {"line_item_type": "HOUSE"}                      | STANDARD       | 8        | CPM      | LIFETIME | IMPRESSIONS          |
      | guaranteed     | vcpm_usd_standard | vcpm  | {}                                               | STANDARD       | 8        | VCPM     | LIFETIME | VIEWABLE_IMPRESSIONS |
      | non-guaranteed | cpm_usd_standard  | cpm   | {"line_item_type": "NETWORK"}                    | PRICE_PRIORITY | 12       | CPM      | NONE     | IMPRESSIONS          |

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
      | lineItemType | priority   | costType | costPerUnitMicros | goalType | unitType    | units |
      | <type>       | <priority> | CPD      | 500000000         | DAILY    | IMPRESSIONS | 100   |

    # The 7000.00 flat price over the 14-day flight is billed at 500.00 a day.
    Examples:
      | settings                                      | type        | priority |
      | {"line_item_type": "STANDARD"}                | SPONSORSHIP | 4        |
      | {"line_item_type": "NETWORK"}                 | NETWORK     | 12       |
      | {"line_item_type": "NETWORK", "priority": 11} | NETWORK     | 11       |

  @T-UC-002-local-gam-priority-refused @extension
  Scenario Outline: A booking setting GAM does not accept is refused before anything reaches GAM
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
    Then the error code should be "CONFIGURATION_ERROR"
    And the error recovery should be "terminal"
    And the wire error details should include capability "<capability>"
    And the wire error details should include rejected_value "<rejected>"
    And Google Ad Manager received no order and no line item

    Examples:
      | settings                                                           | capability                         | rejected |
      | {"priority": 12}                                                   | line_item_priority:STANDARD        | 12       |
      | {"priority": 17}                                                   | line_item_priority:STANDARD        | 17       |
      | {"priority": "8"}                                                  | line_item_priority:STANDARD        | 8        |
      | {"line_item_type": "BOGUS"}                                        | line_item_type                     | BOGUS    |
      | {"line_item_type": "PRICE_PRIORITY", "primary_goal_type": "WEEKLY"} | line_item_goal_type:PRICE_PRIORITY | WEEKLY   |

  @T-UC-002-local-gam-priority-refused-approval @extension
  Scenario Outline: The seller's approval refuses a booking setting GAM does not accept, and the buy still awaits approval
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's guaranteed product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_standard  | cpm           | 12.00       |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001", with product settings '<settings>'
    And the tenant requires manual approval
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | cpm_usd_standard  | 420    |           |
    When the Buyer Agent sends the create_media_buy request
    Then the response status should be "submitted"
    When the seller approves the media buy
    Then the seller's approval is refused, and the media buy still awaits approval
    And the seller is told product "prod_a" is refused with "CONFIGURATION_ERROR" on setting "<capability>", rejecting "<rejected>"
    And Google Ad Manager received no order and no line item

    Examples:
      | settings                                                           | capability                         | rejected |
      | {"priority": 17}                                                   | line_item_priority:STANDARD        | 17       |
      | {"line_item_type": "BOGUS"}                                        | line_item_type                     | BOGUS    |
      | {"line_item_type": "PRICE_PRIORITY", "primary_goal_type": "WEEKLY"} | line_item_goal_type:PRICE_PRIORITY | WEEKLY   |

  @T-UC-002-local-gam-approval-unsupported-pricing @extension
  Scenario: The seller's approval refuses a package priced in a model GAM cannot bill, and the buy still awaits approval
    Given a valid create_media_buy request
    And the account exists and is active
    And the seller's non-guaranteed product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpcv_usd_fixed    | cpcv          | 0.10        |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001"
    And the tenant requires manual approval
    And the buyer's packages, over a 14-day flight, are:
      | product_id | pricing_option_id | budget | bid_price |
      | prod_a     | cpcv_usd_fixed    | 420    |           |
    When the Buyer Agent sends the create_media_buy request
    Then the response status should be "submitted"
    When the seller approves the media buy
    Then the seller's approval is refused, and the media buy still awaits approval
    And the seller is told the approval is refused with "VALIDATION_ERROR", for one package whose pricing model "cpcv" is "UNSUPPORTED_FEATURE"
    And Google Ad Manager received no order and no line item

  @T-UC-002-local-gam-approval-no-pricing-terms @extension
  Scenario: The seller's approval refuses a package stored without its pricing terms, and the buy still awaits approval
    Given the account exists and is active
    And the seller's guaranteed product has pricing options:
      | product_id | pricing_option_id | pricing_model | fixed_price | floor_price |
      | prod_a     | cpm_usd_standard  | cpm           | 12.00       |             |
    And the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001"
    And a media buy awaits the seller's approval with one package "pkg_a" on the product, stored without its pricing terms
    When the seller approves the media buy
    Then the seller's approval is refused, and the media buy still awaits approval
    And the seller is told "Package pkg_a has no stored budget or pricing_info"
    And Google Ad Manager received no order and no line item

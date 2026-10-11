# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# What it grades: the delivery get_media_buy_delivery reports for each package of a buy.
# AdCP 3.1.1 docs/media-buy/task-reference/get_media_buy_delivery.mdx line 15: when delivery
# data is not available, "the seller returns the buy in `media_buy_deliveries` with zero or
# partial metrics". media-buy/get-media-buy-delivery-response.json: `by_package[].package_id`
# is the "Seller's package identifier", and `by_package[].rate` is, for fixed-rate pricing,
# "the agreed rate"; core/delivery-metrics.json types `impressions` and `spend` as delivered
# and spent amounts. A package the ad server did not report is therefore reported at zero,
# not credited with a share of the buy; a buy's only package carries the buy's delivery,
# which is what an ad server with no per-package reporting (Kevel, Broadstreet) returns.
# pricing-options/cpc-option.json: `pricing_option_id` is unique only within its product, and
# `by_package[].rate` is "the agreed rate", so a package's clicks are priced at the rate agreed
# for that package: not at its own product's option as the seller has since repriced it, and
# not at another product's option that shares the id.
#
# Ungraded by storyboard: delivery_reporting's get_delivery step validates the response
# schema and the presence of `media_buy_deliveries`, not per-package figures.
#
# Transports: a2a, mcp, rest and e2e_rest.
#
# @source repo=adcp ref=v3.1.1 path=docs/media-buy/task-reference/get_media_buy_delivery.mdx
# @source repo=adcp ref=v3.1.1 path=dist/schemas/3.1.1/media-buy/get-media-buy-delivery-response.json
# @source repo=adcp ref=v3.1.1 path=dist/schemas/3.1.1/pricing-options/cpc-option.json pointer=/properties/pricing_option_id
Feature: get_media_buy_delivery never credits a package with a share of the buy (local)

  @T-UC-004-local-unreported-package-zero @extension
  Scenario: A package the ad server did not report is reported at zero
    Given a media buy "mb-001" owned by "buyer-001" with status "active"
    And the media buy "mb-001" has a second package "pkg_002"
    And the ad server adapter reports 1000 impressions and 10.00 spend for "pkg_001"
    When the Buyer Agent requests delivery metrics for media_buy_ids ["mb-001"]
    Then the delivery report for "mb-001" has exactly these packages:
      | package | impressions | spend |
      | pkg_001 | 1000        | 10.00 |
      | pkg_002 | 0           | 0.00  |

  @T-UC-004-local-unreported-package-sole @extension
  Scenario: A buy's only package carries the buy's delivery when the ad server reports no breakdown
    Given a media buy "mb-001" owned by "buyer-001" with status "active"
    And the ad server adapter reports 1000 impressions and 10.00 spend for "mb-001" with no package breakdown
    When the Buyer Agent requests delivery metrics for media_buy_ids ["mb-001"]
    Then the delivery report for "mb-001" has exactly these packages:
      | package | impressions | spend |
      | pkg_001 | 1000        | 10.00 |

  @T-UC-004-local-unreported-package-cpc-own-rate @extension
  Scenario: A CPC package's clicks are priced at its own agreed rate, not at the catalog's current options under its id
    Given a media buy "mb-001" owned by "buyer-001" with status "active"
    And package "pkg_cpc" uses pricing_model "cpc" with rate 0.50 and currency "USD"
    And the seller's catalog now prices package "pkg_cpc"'s pricing_option_id at cpc rate 2.00, on the package's own product and on another product
    And the ad server adapter reports 1000 impressions and 10.00 spend for "pkg_cpc"
    When the Buyer Agent requests delivery metrics for media_buy_ids ["mb-001"]
    Then the delivery report for "mb-001" has exactly these packages:
      | package | impressions | spend | pricing_model | rate | clicks |
      | pkg_cpc | 1000        | 10.00 | cpc           | 0.50 | 20     |

# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# What a buyer reads back about a buy it created through a Google Ad Manager seller: the
# buy's status, and the delivery of each of its packages.
#
# PINNED AUTHORITY (adcp==6.6.0, AdCP 3.1.1 -- docs/adcp-spec-version.md).
#   enums/media-buy-status.json: pending_creatives -- "The media buy is approved by the
#   seller and has no creatives assigned -- the buyer must attach creatives via
#   sync_creatives before the buy can serve"; active -- "Media buy is currently running".
#   docs/media-buy/media-buys/lifecycle.mdx: create_media_buy with "creatives present,
#   flight started" enters active; pending_creatives is "Approved; no creatives assigned
#   yet".
#   media-buy/package-request.json: creatives -- inline creatives uploaded and assigned to
#   the package; pricing_option_id -- "ID of the selected pricing option from the
#   product's pricing_options array", so the id is scoped to its product and two products
#   may both name theirs "cpm_usd_fixed" (PricingOption.default_option_id does exactly
#   that for every fixed USD CPM option).
#   media-buy/get-media-buy-delivery-response.json: by_package[] requires package_id
#   ("Seller's package identifier"), spend, pricing_model, rate ("For fixed-rate pricing,
#   this is the agreed rate") and currency.
#   Ungraded by the conformance storyboards: no storyboard creates through a GAM seller.
#
# WHO OBSERVES IT. The buyer, on the get_media_buys and get_media_buy_delivery responses.
# Everything between the request and GAM is production; the only stand-ins are GAM's SOAP
# client and the HTTP download of the report it produced (MediaBuyCreateEnv.sell_through_gam).
# The live e2e stack has no GAM network, so the env declares the seller unrealizable there.
#
# WHAT MAKES THESE NON-VACUOUS. The two products share their pricing option id and differ
# in price, so a rate keyed by the option id alone is wrong for one of them; GAM reports
# different delivery for the two line items, so a spend split across packages, or matched
# to the wrong package, differs from what GAM reported; and the expected package ids are
# the ones the create response returned, not ones a reader could rebuild from the request.

@gamreadback
Feature: A buyer reads back the status and per-package delivery of a buy booked through Google Ad Manager (local)

  Background:
    Given the tenant sells through Google Ad Manager on a network in time zone "America/New_York"
    And the tenant approval mode is auto-approve
    And a GAM product "leaderboard" selling "display_300x250_html" at a fixed 10.00 USD CPM under pricing option "cpm_usd_fixed"
    And a GAM product "rectangle" selling "display_300x250_html" at a fixed 12.00 USD CPM under pricing option "cpm_usd_fixed"
    And the Buyer Agent created a media buy starting now with packages "leaderboard:500.00, rectangle:500.00", each with an inline HTML creative

  @T-GAMREADBACK-status
  Scenario: a buy whose inline creatives were approved and attached is running, not waiting for creatives
    When the Buyer Agent calls get_media_buys with that media_buy_id under the same account
    Then the included entry should expose the same media_buy_id and status "active"
    And the create response reported media_buy_status "active"

  @T-GAMREADBACK-delivery-packages
  Scenario: delivery reports each created package under its own id, price and GAM-reported spend
    Given Google Ad Manager reports 20000 impressions and 200.00 USD for line item "leaderboard" and 10000 impressions and 120.00 USD for line item "rectangle"
    When the Buyer Agent requests delivery for that media buy
    Then the delivery reports exactly the packages the create response returned
    And the delivery for the "leaderboard" package is 20000 impressions and 200.00 USD at a cpm rate of 10.00 USD
    And the delivery for the "rectangle" package is 10000 impressions and 120.00 USD at a cpm rate of 12.00 USD

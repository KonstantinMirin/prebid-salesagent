# A creative a buyer syncs and assigns to a package reaches the GAM line item that
# package is trafficked as.
#
# PINNED AUTHORITY (adcp==6.6.0, AdCP 3.1.1 -- docs/adcp-spec-version.md).
#   creative/sync-creatives-request.json: assignments[] -- "Each entry maps one creative
#   to one package"; creative/sync-creatives-response.json: assigned_to is the "Package
#   IDs this creative was successfully assigned to".
#   core/assets/html-asset.json: an HTML asset is asset_type "html" plus its "content";
#   the creative IS its markup, so the ad server is handed the markup.
#   Ungraded by the conformance storyboards: no storyboard observes a seller's ad server.
#
# WHO OBSERVES IT. GAM. The seller's GAM SOAP client is the one stand-in
# (tests/harness/gam_creative_sync.py); everything between the sync and that client is
# production, and the GAM Thens read what production sent through it. The e2e transport
# declares the setup unrealizable: the live server talks to a real GAM network.
#
# LINE ITEMS BY ID. The seeded line item is named nothing like its product or package:
# the seller knows the line item it created for each package (platform_line_item_id),
# and that mapping, never a name pattern, is what the association is keyed by.

@gamtraffic
Feature: A creative assigned to a GAM package is trafficked on that package's line item

  Background:
    Given the Buyer is authenticated
    And the tenant approval mode is auto-approve

  @T-GAMTRAFFIC-html-third-party
  Scenario: An HTML creative goes to GAM as a third-party creative on its package's line item
    Given a GAM seller whose live package "pkg-gam-1" is trafficked as GAM line item "7210001" for format "display_300x250_html"
    And an HTML creative "html-cr-1" assigned to package "pkg-gam-1"
    When the Buyer Agent syncs the creatives
    Then the creatives entry for "html-cr-1" is assigned to the package
    And GAM was sent one ThirdPartyCreative of size 300x250 for the buyer's GAM advertiser whose snippet is the creative's HTML
    And GAM was sent one association of the created creative with line item "7210001"

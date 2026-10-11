# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# What it grades: a creative assigned to a package of a buy booked in Google Ad Manager
# reaches the line item that package was booked as, through sync_creatives or the seller's
# approval of the creative, once; and an assignment GAM cannot take is reported as an
# assignment error. local-gam-seller.feature grades a buy booked at create.
#
# AdCP 3.1.1:
# - creative/sync-creatives-response.json: assigned_to lists "Package IDs this creative was
#   successfully assigned to"; assignment_errors holds "Assignment errors by package ID".
# - docs/creative/task-reference/sync_creatives.mdx: "Assignments are at the request level,
#   mapping creative IDs to package IDs. Standalone creative agents that do not manage media
#   buys ignore this field" (a sales agent acts on them); dry_run previews changes "without
#   applying them".
# Ungraded by the storyboard runner.
#
# Transports: a2a, mcp and rest with the real GoogleAdManager adapter over a stand-in SOAP
# client. The live server has no stand-in GAM network, so the setup declares itself
# unrealizable on e2e (GamSellerMixin.sell_through_gam).
#
# @source repo=adcp ref=v3.1.1 path=docs/creative/task-reference/sync_creatives.mdx
# @source repo=adcp ref=v3.1.1 path=static/schemas/source/creative/sync-creatives-response.json
Feature: UC-006 a Google Ad Manager seller traffics assigned creatives onto its booked line items (local)

  Background:
    Given the seller sells through Google Ad Manager as trafficker "2000001" on ad unit "4000001", and the buyer is its advertiser "3000001"
    And the creative agent serves the reference creative formats
    And the tenant has approval_mode "auto-approve"
    And the buyer holds a buy booked in Google Ad Manager as order "6000001" whose package "pkg-banner-a" is line item "5000001" accepting 300x250

  @T-UC-006-local-gam-assignment-traffics
  Scenario: A synced creative assigned to a booked package is created in GAM and placed on its line item
    Given the buyer syncs a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-banner-a"
    When the Buyer Agent syncs the creative with assignments
    Then creative "cr-banner" is assigned to package "pkg-banner-a"
    And Google Ad Manager created one image creative for advertiser "3000001" showing "https://example.com/banner.png"
    And Google Ad Manager associated that creative with line items "5000001"

  @T-UC-006-local-gam-weighted-assignment
  Scenario: A weighted assignment puts its line item on manual rotation and carries the weight
    Given the buyer syncs a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-banner-a" with weight 40
    When the Buyer Agent syncs the creative with assignments
    Then creative "cr-banner" is assigned to package "pkg-banner-a"
    And Google Ad Manager set line item "5000001" to manual creative rotation
    And Google Ad Manager associated that creative with line item "5000001" at weight 40

  @T-UC-006-local-gam-assignment-refused
  Scenario: A package whose line item cannot take the creative's size is reported in assignment_errors
    Given the buyer holds a buy booked in Google Ad Manager as order "6000003" whose package "pkg-leader" is line item "5000003" accepting 728x90
    And the buyer syncs a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-leader"
    When the Buyer Agent syncs the creative with assignments
    Then creative "cr-banner" reports package "pkg-leader" in assignment_errors and not in assigned_to
    And Google Ad Manager created no creative

  @T-UC-006-local-gam-creative-reused
  Scenario: A creative already in GAM is placed on a second package's line item, not created again
    Given the buyer holds a buy booked in Google Ad Manager as order "6000002" whose package "pkg-banner-b" is line item "5000002" accepting 300x250
    And the buyer synced a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-banner-a"
    When the Buyer Agent references library creative "cr-banner", without resending it, assigned to package "pkg-banner-b"
    Then creative "cr-banner" is assigned to package "pkg-banner-b"
    And Google Ad Manager created one image creative for advertiser "3000001" showing "https://example.com/banner.png"
    And Google Ad Manager associated that creative with line items "5000001, 5000002"

  @T-UC-006-local-gam-dry-run-stays-local
  Scenario: A dry-run sync of an assignment sends nothing to GAM
    Given the buyer syncs a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-banner-a" as a dry run
    When the Buyer Agent syncs the creative with assignments
    Then creative "cr-banner" is assigned to package "pkg-banner-a"
    And Google Ad Manager created no creative

  @T-UC-006-local-gam-pending-creative-held
  Scenario: A creative awaiting the seller's review is assigned but not sent to GAM
    Given the tenant has approval_mode "require-human"
    And the buyer syncs a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-banner-a"
    When the Buyer Agent syncs the creative with assignments
    Then creative "cr-banner" is assigned to package "pkg-banner-a"
    And Google Ad Manager created no creative

  # The id the approval records is GAM's own: the later assignment places that creative on
  # the second line item instead of creating it again.
  @T-UC-006-local-gam-approval-on-live-buy
  Scenario: Approving a creative held back from a live buy places it on the buy's line item and records GAM's id
    Given the tenant has approval_mode "require-human"
    And the buyer holds a buy booked in Google Ad Manager as order "6000005" in status "active" whose package "pkg-live" is line item "5000005" accepting 300x250
    And the buyer synced a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-live"
    When the seller approves creative "cr-banner"
    Then Google Ad Manager created one image creative for advertiser "3000001" showing "https://example.com/banner.png"
    And Google Ad Manager associated that creative with line items "5000005"
    When the Buyer Agent references library creative "cr-banner", without resending it, assigned to package "pkg-banner-a"
    Then creative "cr-banner" is assigned to package "pkg-banner-a"
    And Google Ad Manager created one image creative for advertiser "3000001" showing "https://example.com/banner.png"
    And Google Ad Manager associated that creative with line items "5000005, 5000001"

  # The buyer re-sends the creative it already synced, with the same assignment. GAM already
  # holds the creative on that line item, so nothing is sent again.
  @T-UC-006-local-gam-resend-no-second-creative
  Scenario: Re-sending a creative GAM already holds, with the same assignment, creates nothing in GAM
    Given the buyer synced a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-banner-a"
    And the buyer syncs a 300x250 image creative "cr-banner" showing "https://example.com/banner.png" assigned to package "pkg-banner-a"
    When the Buyer Agent syncs the creative with assignments
    Then creative "cr-banner" is assigned to package "pkg-banner-a"
    And Google Ad Manager created one image creative for advertiser "3000001" showing "https://example.com/banner.png"
    And Google Ad Manager associated that creative with line items "5000001"

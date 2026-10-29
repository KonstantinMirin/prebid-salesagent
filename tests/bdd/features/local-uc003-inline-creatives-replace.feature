# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# Upstream gap: BR-UC-003's only positive inline-creatives scenario
# (@T-UC-003-alt-creatives-inline) grades the response status and affected_packages,
# which a seller that ADDS the inline bodies beside the package's previous creatives
# passes as well as one that replaces them. The pin's inline_creatives_without_sync
# storyboard grades the replacement, but it requires comply_test_controller, which this
# seller does not include. This scenario grades the replacement itself.
#
# Reconcile upstream in adcp-req (a "the inline creatives replace the package's
# creatives" Then on the alt-creatives-inline flow), then retire this file.
#
# @source repo=adcp ref=v3.2.7 path=static/schemas/source/media-buy/package-update.json pointer=/properties/creatives
# @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/media-buy-features.json pointer=/properties/inline_creative_management
# @source repo=adcp ref=v3.2.7 path=docs/creative/sales-agent-creative-capabilities.mdx section="Creative management modes"
Feature: UC-003 update_media_buy — inline creatives replace the package's creatives (local)

  @T-UC-003-local-inline-creatives-replace @creatives-inline @post-s1 @post-s2
  Scenario: inline creatives on a package update replace the creatives assigned to the package
    Given the tenant is configured for auto-approval
    And a valid update_media_buy request with:
    | field        | value       |
    | media_buy_id | mb_existing |
    And the request includes 1 package update with:
    | field      | value   |
    | package_id | pkg_001 |
    And library creative "cr_before_inline" is assigned to package "pkg_001"
    And the package update includes inline creatives with valid content
    And the package "pkg_001" exists in the media buy
    When the Buyer Agent sends the update_media_buy request
    Then the response is compliant with the update_media_buy success spec
    And the response status should be "completed"
    And the response should contain affected_packages including "pkg_001"
    And the package "pkg_001" should be assigned exactly the inline creatives the update sent
    # package-update.json /properties/creatives: "Replace this package's inline creative
    # assets". The seller declares media_buy.features.inline_creative_management true
    # (graded by @T-UC-010-local-inline-creative-management), and media-buy-features.json
    # says a seller declaring a feature "MUST honor requests using that feature". So the
    # library creative assigned before the update is no longer assigned after it, and the
    # inline body the update sent is: the record holds the replacement, not the union.

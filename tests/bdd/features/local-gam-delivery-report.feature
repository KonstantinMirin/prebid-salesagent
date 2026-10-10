# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# PINNED AUTHORITY (adcp==6.6.0, AdCP 3.1.1 -- docs/adcp-spec-version.md).
#   docs/media-buy/task-reference/get_media_buy_delivery.mdx :15 -- "If delivery data for
#   a buy is genuinely unavailable (e.g., the ad server has not yet reported a flight), the
#   seller returns the buy in `media_buy_deliveries` with zero or partial metrics; the
#   seller does not omit it".
#   media-buy/get-media-buy-delivery-response.json: `errors` carries "Task-specific errors
#   and warnings (e.g., missing delivery data, reporting platform issues)"; each
#   media_buy_deliveries[] item requires media_buy_id, status, totals and by_package.
#   The storyboard scenario BR-UC-004 @T-UC-004-empty-period grades the same obligation
#   with the adapter's answer injected; this file grades it through the REAL Google Ad
#   Manager adapter, whose own handling of an empty report is the subject.
#
# The two outcomes this separates: a report that ran and has no rows (a buy that has not
# delivered, or a network that has not reported) is zero delivery; a report GAM failed to
# produce is a reporting platform issue, reported in `errors` for that buy. Data GAM has
# not finished for the period is a third case only in webhook context, where the response
# schema gives it `reporting_delayed` and `expected_availability`; a buyer's own request is
# answered with the figures so far, which is what these scenarios send.
#
# WHO OBSERVES IT. The buyer, on the get_media_buy_delivery response. The only replaced
# pieces are GAM's SOAP client and the HTTP download of the report it produced. The live
# e2e stack has no GAM network, so the env declares the seller unrealizable there.

@gam_delivery
Feature: get_media_buy_delivery reads an empty Google Ad Manager report as zero delivery (local)

  Background:
    Given the tenant reports delivery from Google Ad Manager
    And a media buy "mb-001" owned by "buyer-001" with status "active"

  @T-UC-004-local-gam-empty-report
  Scenario: a GAM report with no rows reports the buy with zero delivery
    When the Buyer Agent requests delivery metrics for media_buy_ids ["mb-001"]
    Then the response is compliant with the get_media_buy_delivery spec
    And the response should include "mb-001" with zero impressions and zero spend
    And the response should not include an error for "mb-001"

  @T-UC-004-local-gam-failed-report
  Scenario: a GAM report job that fails is reported as an error for the buy
    Given Google Ad Manager fails the delivery report
    When the Buyer Agent requests delivery metrics for media_buy_ids ["mb-001"]
    Then the response errors include code "SERVICE_UNAVAILABLE" for media buy "mb-001"
    And the response should NOT include delivery data for "mb-001"

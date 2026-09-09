# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# BR-UC-004 grades the two SIGNED deliveries — HMAC-SHA256 (:285) and Bearer
# (:298) — and nothing grades the case where the buyer registers no
# authentication block at all. The pinned schema makes that case legal:
# core/reporting-webhook.json requires url and reporting_frequency, and
# authentication is optional, so a registration without it is conformant and
# the seller owes the buyer a delivery.
#
# The failure this exists to catch is a delivered → never-delivered change.
# Every refusal the seller learned to make (a >1 schemes array, a sub-32
# credential, a credential-less HMAC — local-egress-ssrf-refusal.feature) is
# scoped to a block that IS present; a gate that also refused an ABSENT block
# would silently stop delivering to every buyer who never asked to be signed,
# and would do it where no buyer is left to correct anything.
#
# @source repo=adcp ref=v3.1.1 path=dist/schemas/3.1.1/core/reporting-webhook.json
Feature: UC-004 delivery webhooks — a registration with no authentication still delivers, unsigned (local)

  @T-UC-004-local-unsigned-webhook-delivery @webhook @invariant
  Scenario: a webhook registered without an authentication block is delivered unsigned
    Given a media buy "mb-001" with an active reporting_webhook configured
    When the system delivers a webhook report for "mb-001"
    Then the system should POST a delivery report to the configured webhook URL
    And the request should carry no webhook authentication headers

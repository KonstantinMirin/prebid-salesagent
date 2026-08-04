# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# Spec grounding — AdCP 3.1.1, the version this repo PINS (adcp==6.6.0, see
# docs/adcp-spec-version.md). Read the pinned prose with
# `git -C <adcp-checkout> show v3.1.1:docs/building/by-layer/L1/security.mdx`
# (`dist/docs/` stops at 3.1.0 at that tag), § "Webhook URL validation (SSRF)":
#   point 1 — reject non-HTTPS URLs;
#   point 2 — reject reserved-range addresses (169.254.169.254 named outright);
#   point 6 — "Do not echo fetch errors to the agent that supplied the URL …
#             a side-channel for probing internal network topology."
# "Any URL that a buyer, seller, or governance agent provides for another party
# to fetch is an SSRF vector" — property_list.agent_url is one of those URLs.
#
# The conformance storyboard does NOT grade this. Nothing in
# dist/compliance/3.1.1/ grades a seller refusing a counterparty-supplied URL;
# the three `ssrf` hits there are guardrails the RUNNER applies to its OWN
# outbound fetches. So there is no BR-UC-* scenario to inherit — hence a local
# feature. Reconcile upstream in adcp-req (a get_products scenario carrying a
# refused property_list), then retire this file for the regenerated one.
#
# The wire grading is INVALID_REQUEST / correctable / field
# "property_list.agent_url": the refusal is a property of the URL the buyer
# sent, so it is buyer-fixable, and `field` is the only channel that can say
# WHICH input to fix without disclosing anything (the message must not).
# Grounded on docs/building/by-layer/L3/error-handling.mdx § "Request
# Validation" + § "Recovery Classification"; INVALID_REQUEST is in the pinned
# static/schemas/source/enums/error-code.json.
#
# Why THESE causes: with both escape hatches open — which is the posture of
# docker-compose.e2e.yml and of run_all_tests_host.sh — a cloud-metadata
# address and an unresolvable host are still refused (the SDK checks
# BLOCKED_METADATA_IPS and raises on getaddrinfo failure upstream of the
# allow_private gate). They are the only two refusal causes that grade the same
# production on every transport, so both envelope scenarios pin the hatches ON
# deliberately. The plaintext-http scenario needs them OFF, which the e2e stack
# cannot do — it declares that at the env, not in a nodeid ledger.
#
# NOT here, on purpose: the redirect-not-followed obligation (proved by a
# second live origin's hit count in
# tests/integration/test_delivery_webhook_behavioral.py:823 — unobservable
# across the Docker boundary) and the delivery-time push_notification_config
# refusal (tests/integration/test_delivery_webhook_behavioral.py:523 — no
# request/response cycle, so no envelope to grade). The ingest-time
# push_notification_config twin (last scenario below) grades the same
# obligation at the one moment a request still exists to refuse into —
# create_media_buy ingest, before the URL is stored for later delivery. Its
# @egress_create tag routes it to the media-buy create harness; the sibling
# ingest paths (update_media_buy, sync_creatives, reporting_webhook.url) are
# graded at tests/integration/test_webhook_url_ingest_refusal.py.
#
# The ingest verdict is NOT the seam's, and the last scenario is graded
# accordingly. `reject_unsafe_webhook_registration_url`
# (src/core/webhook_validator.py) raises AdCPValidationError — VALIDATION_ERROR
# / correctable / field / suggestion, message shaped `Invalid <field>:
# <reason>` — and it is deliberately DNS-FREE: an unresolvable-but-public
# hostname is ACCEPTED at ingest and re-checked when the callback is dialled
# (gh-#1589 / gh-#1697). So the ingest scenario carries its own wire code and
# its own causes; an unresolvable host is not one of them. The <reason> itself
# is now the SAME fixed, non-disclosing text for every address cause
# (`url_validator._RESTRICTED_RANGE_MESSAGE`) — no CIDR, no resolved address —
# matching the seam's one-message-for-every-cause posture, so every row below
# expects the identical message.
Feature: Egress refusal of a buyer-supplied URL (local, L1 SSRF)

  A URL the buyer supplies for us to fetch is an SSRF vector. When the egress
  seam refuses one, the buyer must learn that their request is fixable and
  which field to fix — and nothing whatsoever about our network.

  @T-EGRESS-SSRF-refused-url-is-a-correctable-buyer-error @egress @invariant
  Scenario Outline: a refused agent_url is a correctable buyer error naming the field
    Given a tenant is configured for product discovery
    And both outbound egress escape hatches are open
    When the buyer requests products with a property list agent at "<agent_url>"
    Then the request is rejected with INVALID_REQUEST naming field "property_list.agent_url"

    Examples:
      | agent_url                    |
      | https://169.254.169.254      |
      | https://no-such-host.invalid |

  @T-EGRESS-SSRF-refusal-discloses-nothing @egress @invariant
  Scenario Outline: the refusal discloses nothing and does not distinguish the cause
    Given a tenant is configured for product discovery
    And both outbound egress escape hatches are open
    When the buyer requests products with a property list agent at "<agent_url>"
    Then the refusal message on both envelope layers is exactly "Outbound request to the supplied URL was refused by egress policy."
    And the error envelope names neither the supplied host nor any IP address

    Examples:
      | agent_url                    |
      | https://169.254.169.254      |
      | https://no-such-host.invalid |

  # The host RESOLVES, and is public, on purpose: scheme policy runs before
  # address validation, so a host that NXDOMAINs would be refused either way and
  # this scenario could not tell a scheme refusal from an unresolvable-host one —
  # it would stay green with the scheme gate deleted. A resolvable public host
  # makes the scheme gate the only thing standing between the request and the
  # network, which is what the scenario claims to grade. Nothing is ever sent:
  # the refusal happens before DNS.
  @T-EGRESS-SSRF-plaintext-http-refused @egress
  Scenario: a plaintext http agent_url is refused
    Given a tenant is configured for product discovery
    And both outbound egress escape hatches are closed
    When the buyer requests products with a property list agent at "http://example.com"
    Then the request is rejected with INVALID_REQUEST naming field "property_list.agent_url"

  # The third buyer-supplied URL on the protocol surface, and the one with the
  # LOWEST privilege bar: creatives[].format_id.agent_url names the creative
  # agent a creative's format lives on, and sync_creatives dials it to check the
  # format exists. Any authenticated advertiser can send it (gh-#1790).
  #
  # Graded here rather than only in integration because the refusal's
  # classification — not merely its existence — is the obligation: before the
  # fix the connection WAS refused, but the registry reported it through its
  # OPERATOR arm as CONFIGURATION_ERROR / terminal, telling the buyer a seller
  # was misconfigured about a URL the buyer themselves chose, with no field.
  #
  # Hatches OPEN, and a cloud-metadata address, for the reason the header gives:
  # that is the only posture the e2e stack can realize, and metadata is refused
  # even with both hatches wide open, so this scenario grades ONE production on
  # every transport including e2e_rest.
  #
  # The field is INDEXED (creatives[0]...) per the pinned spec's JSONPath-lite
  # examples: a sync carries up to 100 creatives and the message says nothing,
  # so an unindexed path would leave the buyer unable to tell WHICH creative.
  @T-EGRESS-SSRF-sync-creatives-agent-url @egress_sync @invariant
  Scenario: a refused creative-agent agent_url is a correctable buyer error at sync ingest
    Given both outbound egress escape hatches are open
    When the buyer syncs a creative whose format agent is at "https://169.254.169.254"
    Then the creative is rejected with INVALID_REQUEST naming field "creatives[0].format_id.agent_url"

  # The ingest twin: the same obligation — a buyer-supplied URL we refuse comes
  # back as a correctable, non-disclosing error naming the field to fix —
  # graded at the one moment a request still exists to refuse into. A
  # push_notification_config.url is STORED at create_media_buy and dialled later
  # by a background worker; by then the buyer is gone, so an
  # accepted-then-undeliverable URL is a silent failure.
  #
  # Why THESE causes: the ingest gate is DNS-free, so an unresolvable host is
  # ACCEPTED here (correctly — send time re-checks it) and cannot be an example.
  # A reserved-range LITERAL needs no DNS and is refused with the hatches open
  # (the gate reads BLOCKED_NETWORKS in src/core/security/url_validator.py, not
  # the egress hatches), so it grades one production on every transport. Both
  # rows are IPv6 reserved ranges spec point 2 covers — unique-local (RFC 4193)
  # and multicast. Loopback (::1) is deliberately NOT an example here even
  # though the fix below makes its message non-disclosing too: ADCP_TESTING is
  # ambient true in this harness, and ::1 is loopback exactly like 127.0.0.1
  # (tests/unit/conftest.py's own _LOOPBACK_PREFIXES treats it identically), so
  # the registration gate's testing-mode allowance (WebhookURLValidator.
  # _maybe_allow_localhost) RESCUES it here — the request would succeed, not
  # refuse. A cloud-metadata literal and any IPv4 literal are not used here
  # only because the IPv6 set already exercises every address-cause branch
  # (named-network match and the loopback/private fallback) — not because
  # either would still leak: the message below is now identical for every
  # address cause.
  #
  # The message is now cause-blind, same as the seam scenarios above: the
  # registration gate used to report a per-cause reason (which CIDR, which
  # resolved address) — the bug fixed here — and now returns the SAME fixed,
  # non-disclosing text regardless of which reserved range matched
  # (`url_validator._RESTRICTED_RANGE_MESSAGE`). The non-disclosure Then below
  # holds that line independently of the exact-message Then above.
  @T-EGRESS-SSRF-ingest-refused-webhook-url @egress_create @invariant
  Scenario Outline: a refused push_notification_config.url is a correctable buyer error at ingest
    Given both outbound egress escape hatches are open
    When the buyer creates a media buy with push notification url "<webhook_url>"
    Then the request is rejected with VALIDATION_ERROR naming field "push_notification_config.url"
    And the refusal message on both envelope layers is exactly "<message>"
    And the error envelope names neither the supplied host nor any IP address

    Examples:
      | webhook_url            | message                                                                    |
      | https://[fc00::1]/hook | Invalid push_notification_config.url: URL resolves to a restricted range. |
      | https://[ff02::1]/hook | Invalid push_notification_config.url: URL resolves to a restricted range. |

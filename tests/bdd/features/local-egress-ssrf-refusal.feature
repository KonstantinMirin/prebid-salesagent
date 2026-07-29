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
# push_notification_config twin of the first scenario below lands with
# salesagent-w97e, which adds the validation it needs.
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

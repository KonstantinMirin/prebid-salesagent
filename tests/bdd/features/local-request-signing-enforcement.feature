# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# Upstream gap: the request-signing obligations are graded upstream ONLY by the
# 40 static conformance vectors (dist/compliance/3.1.1/test-vectors/request-signing/*),
# which are byte-level fixtures replayed against a verifier — there is no storyboard
# scenario that drives a REAL buyer request through a REAL seller deployment and grades
# whether it was refused or verified. Every one of the three obligations below was
# therefore asserted in this repo by code shape and by per-transport unit tests, which
# is precisely how the A2A credential-location bypass (SF-4) survived a review:
# the property "a signed request accepted, an unsigned one refused, IDENTICALLY on every
# transport" is a CROSS-transport property, and nothing cross-transport graded it.
#
# These three scenarios are that grading. Each differs from the others by exactly ONE
# variable, and all three run on the same operation through the same env, so a
# difference in outcome is attributable to the variable and not to the setup.
#
# Reconcile upstream in adcp-req (a "seller enforces inbound request signatures"
# storyboard), then retire this file in favor of the regenerated one.
#
# @source repo=adcp ref=v3.1.1 path=dist/docs/3.1.1/building/by-layer/L1/security.mdx pointer=L1268-L1269
# @source repo=adcp ref=v3.1.1 path=dist/docs/3.1.1/building/by-layer/L1/security.mdx pointer=L1375
# @source repo=adcp ref=v3.1.1 path=dist/docs/3.1.1/building/by-layer/L1/security.mdx pointer=L1462-L1465
# @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/test-vectors/request-signing/negative/027-webhook-registration-authentication-unsigned.json pointer=/expected_outcome
Feature: Inbound request-signature enforcement on an AdCP operation (local)

  @T-UC-006-local-signing-required-unsigned @request-signing @error-path @invariant
  Scenario: an unsigned request to a required_for operation is refused
    Given a creative with a known format_id
    And the Buyer Agent has published a signing key the seller can resolve
    And the seller requires a request signature for "sync_creatives"
    And the Buyer has no authentication credentials
    When the Buyer Agent syncs the creative
    Then the seller answers with the request-signature challenge "request_signature_required"
    # The composition rule, security.mdx @ v3.1.1 :1268-1269: a seller MUST NOT refuse an
    # unsigned request for the missing signature when the caller "presents another
    # credential the agent accepts" (:1269) — so `required_for` alone does NOT make an
    # authenticated unsigned request a 401, and the caller here presents NO credential
    # (:1268), which is the only branch that reaches the refusal.
    # The oracle is the CHALLENGE, byte-exactly, never the status: a bare 401 is equally
    # produced by the auth middleware rejecting first, by a 404 wearing a 401, and by the
    # malformed-header precheck.

  @T-UC-006-local-signing-verified @request-signing @invariant
  Scenario: a request signed by a counterparty the seller can resolve is accepted
    Given a creative with a known format_id
    And the Buyer Agent has published a signing key the seller can resolve
    And the seller requires a request signature for "sync_creatives"
    And the Buyer Agent signs the request
    When the Buyer Agent syncs the creative
    Then the seller verified exactly 1 request under the Buyer Agent's published key
    # ONE variable apart from the scenario above: the same operation, the same posture,
    # the same seller — a signature, and a credential the seller accepts.
    # "Accepted" is NOT graded as a 2xx, and cannot be: a 200 is equally true of a
    # middleware that never looked at the request, and of an operation whose posture
    # bucket collapsed to `none`. The seller's own record of WHICH key it verified —
    # matching the key this buyer published, under a kid unique to this run — is what
    # separates "verified" from "waved through".

  @T-UC-006-local-signing-webhook-credentials @request-signing @error-path @invariant @boundary
  Scenario: a registration carrying webhook authentication is refused unless signed
    Given a creative with a known format_id
    And the Buyer Agent has published a signing key the seller can resolve
    And the seller supports request signatures but requires them for no operation
    And the request registers a webhook whose authentication carries credentials
    When the Buyer Agent syncs the creative
    Then the seller answers with the request-signature challenge "request_signature_required"
    # security.mdx @ v3.1.1 :1462-1465 — "sellers that support request signing MUST require
    # the inbound request to be 9421-signed ... when `authentication` is present", restated
    # at :1375 as a trigger that fires "regardless of `required_for` membership".
    # The posture declares `supported` and requires the operation NOWHERE, which is the
    # pinned vector's own `verifier_capability` ({supported: true, required_for: []}) and is
    # LOAD-BEARING: with the operation in `required_for` the refusal could equally come from
    # the composition rule, and the scenario would stop grading the escalation at all.
    # The buyer here IS authenticated — the opposite of the first scenario — because the
    # escalation is deliberately NOT subject to the composition rule's exemption: the
    # registering request is normally bearer-authed, and an on-path mutator injecting or
    # stripping the `authentication` block is exactly what the MUST exists to stop.
    # WHERE the credential travels is the TRANSPORT's business, not this scenario's, and it
    # is not the same place on every transport: the env puts it where each transport's
    # production code READS it. That difference is the point — see the a2a result.

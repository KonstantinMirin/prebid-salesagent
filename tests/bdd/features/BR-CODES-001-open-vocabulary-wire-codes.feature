# Hand-authored feature — not compiled from adcp-req
# Cross-cutting wire obligation for salesagent-3dawm.6 (delete the code rewriters)

@codes
Feature: A declared error code reaches the buyer as declared
  As a buyer agent,
  I want the error code a seller declares to arrive on the wire unrewritten,
  with the recovery semantics that code carries,
  so that I can decode an outcome the published enum does not name.

  # AdCP 3.1.1 core/error.json: the error-code vocabulary is OPEN. `error.code` is a
  # wire-typed string, the published codes are documentary, senders MAY emit codes
  # outside that set, and receivers MUST decode an unknown code by reading
  # `error.recovery`. Collapsing a platform code onto a published one therefore
  # discards information the spec asks senders to keep — and leaves `recovery` as the
  # only decode path, which is why this scenario pins BOTH halves.
  #
  # MEDIA_BUY_REJECTED is the discriminating case: before the rewriters were deleted
  # the buyer received POLICY_VIOLATION with recovery "correctable" — retry this — for
  # a seller decision that is terminal. Both the code AND its recovery change here, so
  # a scenario that graded only the code would still pass while telling the buyer to
  # retry a rejection.
  #
  # No suggestion is asserted: AdCPMediaBuyRejectedError leaves _default_suggestion
  # unset, so the envelope omits the field. That is the 42/42 suggestion half of the
  # deferred class-attribute fold, out of scope here — an omission, not a contradiction.

  @T-CODES-001-platform-code-reaches-buyer
  Scenario: A seller rejection reaches the buyer as the code the seller declared
    Given the buyer requests a media buy the seller will reject
    When the Buyer Agent sends the create_media_buy request
    Then the response is an error carrying the seller's own code "MEDIA_BUY_REJECTED"
    And the error recovery should be "terminal"

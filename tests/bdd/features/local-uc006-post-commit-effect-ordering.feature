# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# NOT a protocol obligation, and deliberately not dressed as one. AdCP 3.1.1 is
# silent on WHEN a seller may run a background review; what it is not silent
# about is what sync_creatives reports. The sibling file
# local-uc006-dry-run-out-of-transaction-effects.feature grades the preview arm
# (an effect a rollback cannot reach must not fire at all); this file grades the
# LIVE arm of the same seam, where the failure is ordering rather than
# occurrence. Per the project's source hierarchy, where the schema is silent the
# invariant is production's own — stated here so it is graded rather than
# assumed.
#
# The invariant: an effect that leaves the sync's transaction runs only AFTER
# that transaction commits. The AI-review job is the concrete instance —
# _processing.py hands it to a background executor and it opens its own session,
# so committed rows are the only state it can ever read. Today the sync
# ``flush()``es and submits from INSIDE the still-open transaction, which is not
# a commit: on the create arm the job's session finds no row, and on the update
# arm it finds the row as it was BEFORE this sync touched it.
#
# Why the outline is create x update and not the four-cell partition its sibling
# uses: the AI-review submit is on the approval-mode branch, which does not fork
# on format kind, so generative vs agent-served-static reaches the same submit.
# What DOES fork it is whether the creative already exists — the two arms have
# separate submit sites and separate wrong answers (missing row vs stale row).
#
# @source repo=adcp ref=v3.1.1 path=dist/schemas/3.1.1/creative/sync-creatives-response.json
Feature: UC-006 sync_creatives — an effect that leaves the transaction runs only after that transaction commits (local)

  @T-UC-006-local-post-commit-ai-review-ordering @creative-approval @invariant
  Scenario Outline: the AI review job cannot observe a creative the sync has not committed
    Given the Buyer is authenticated with a valid principal_id
    And the tenant has approval_mode "ai-powered"
    And the tenant has a slack_webhook_url configured
    And a <creative_state> creative on a static format served by a creative agent
    When the Buyer Agent syncs the creative
    Then the response is the success variant carrying a creatives array
    And every creative result has action "<expected_action>"
    And the AI review submissions name exactly the synced creative
    And each AI review submission observes the creative exactly as the sync committed it
    # The last Then compares two reads of the same row: what an INDEPENDENT
    # connection could see at submit time, and what the request left committed.
    # Equality is the whole invariant — the job reads committed state and nothing
    # else, so any difference is state the job would have missed or misread.
    #
    # "the AI review submissions name exactly the synced creative" is the
    # non-vacuity control: without it, an ai-powered branch that stopped
    # submitting, a renamed executor or a wrong patch target would leave nothing
    # observed and the comparison would hold over an empty set.

    Examples:
      | partition_boundary                             | creative_state | expected_action |
      | create arm, no row exists until the commit     | new            | created         |
      | update arm, the row exists but is pre-update   | existing       | updated         |

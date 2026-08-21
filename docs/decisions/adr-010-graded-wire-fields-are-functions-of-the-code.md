# ADR-010: A graded wire field is a function of the error code, never authored at a raise site

**Status:** Accepted
**Date:** 2026-08-21
**Context:** epic `salesagent-3dawm` (derive every buyer-facing error from one code table)

## Context

AdCP 3.1.1 defines an error's buyer-facing fields as properties **of the code**.
`enums/error-code.json` carries `enumMetadata.recovery` and `enumMetadata.suggestion` per
code, and the pinned bundle is normative — its own text says SDKs MUST consume that block and
that the recovery classification embedded in the prose MUST match the value there. This repo
augments the published set with its own platform codes in `CODE_TABLE`, which supplies the
same three fields for those.

So for any code there is exactly one correct message, one correct recovery, one correct
suggestion. They are not decisions a raise site gets to make.

The codebase disagreed with that in three places at once, and each cost something measurable:

- **Message.** Raise sites interpolated caught exceptions into buyer text —
  `raise AdCPAdapterError(str(e))`, `AdCPServiceUnavailableError(f"Request timed out: {mcp_url}")`.
  Third-party exception strings and internal URLs reached the buyer-facing wire.
- **Recovery.** 14 raise sites passed a `recovery=` that contradicts the pinned classification
  for their own code — telling a buyer "terminal, do not retry" where the pin says the condition
  is transient or correctable. A buyer dispatches on this field.
- **Suggestion.** 220 of 294 construction sites passed none, so the field was simply absent from
  those envelopes; 71 authored one, and 9 codes ended up emitting two different strings depending
  on which raise site fired.

Each was policed by a guard rather than prevented: guards asserting that a class agreed with the
pin, that an advisory site remembered to call a normalizer, that recovery matched. Guards are
hand-maintained correspondences too, and they grow.

## Decision

**A graded wire field is derived from the code. A raise site cannot author one.**

Concretely:

1. `message` has **no constructor parameter** and is a read-only property resolved from
   `CODE_TABLE`. (Landed: `salesagent-3dawm.3`.)
2. `recovery` and `suggestion` follow the same rule. The `recovery=` and `suggestion=`
   parameters are to be **deleted**, not merely defaulted. A class may still override
   *visibly* via a `ClassVar`, but silence means the table owns it.
3. **A different retry semantic is a different code, therefore a different error class.**
   Overriding recovery at a call site is not the escape hatch; declaring the right code is.
4. **An advisory error** (an `errors[]` entry inside a success response) is constructible
   **only from a typed exception**, via `build_error_object(exc)`. Field-by-field `Error(...)`
   construction is not available.
5. Specifics travel as **data, not prose**: `details=` for structured, buyer-visible facts;
   `field=` for the offending field; `internal_detail=` for the caught exception, which is
   **server-log only and must never be added to a serializer**.

The test of a correct fix is that the defect becomes **unrepresentable**, not that a guard
detects it. Where a guard exists only to police a correspondence that this makes impossible,
the guard is deleted with it.

## Consequences

**Good.** One code means one thing on every lane and every transport. Whole classes of guard
disappear: three pin-conformance guards were already deleted, and
`test_architecture_advisory_normalizer_routing.py` (202 lines) plus `normalize_advisory_errors`
itself become unnecessary once (4) lands — the normalizer exists only to repair hand-built
advisories, and the guard exists only to ensure the normalizer is called.

**Cost.** Deleting a parameter is a breaking change to every raise site that used it, and each
must be re-expressed as a code choice or as `details`. The 14 contradicting recovery sites need
a per-site decision, and 4 of them look like a wrong-class problem rather than a missing code —
re-classing those changes the buyer-visible **code**, which requires spec grounding under
CLAUDE.md's Spec-Grounding Gate before any code is written.

**A testing affordance is the current blocker for recovery.** Two sites
(`mock_ad_server.py`, `helpers/adapter_helpers.py`) read `recovery` from a test-behaviour hook,
so a testing convenience is keeping a production parameter alive that lets 14 real sites
contradict the pin. The hook needs a different injection path; the production signature must not
be shaped by it.

**When to revisit.** If AdCP ever makes recovery or suggestion request-dependent rather than
code-dependent, (2) and (3) stop being true and this ADR is superseded.

## Execution

| item | bead |
|---|---|
| delete the `recovery=` parameter; resolve the 14 contradicting sites | `salesagent-3dawm.11` |
| delete the `suggestion=` parameter (61 sites) | `salesagent-3dawm.12` |
| drop `GateFailure.suggestion` (required field) | `salesagent-3dawm.13` — subsumed by `.14` |
| advisory constructible only from a typed exception; delete the normalizer and its guard | `salesagent-3dawm.14` |

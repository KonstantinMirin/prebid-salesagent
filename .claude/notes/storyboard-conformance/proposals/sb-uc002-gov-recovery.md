# Re-pin: `@T-UC-002-storyboard-governance-denied-recovery`

Scenario: `tests/bdd/features/BR-UC-002-create-media-buy.feature:2664`
Title: "Governance denied recovery -- buyer shrinks the buy to within plan limits and retries successfully"

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** The `@storyboard-v3.1` tag is unjustified and must become `@schema-v3.1`.

Two independent gates both close for us:

1. **Specialism gate.** `governance_denied_recovery` is required by exactly one index in the whole 3.1.1 compliance tree — `specialisms/governance-aware-seller/index.yaml:27`. It is *not* in `protocols/media-buy/index.yaml`'s `requires_scenarios`, and it is *not* in `specialisms/sales-non-guaranteed/index.yaml`'s `requires_scenarios` (that specialism pulls in `governance_aware_seller/governance_multi_agent_rejected`, a different scenario, but not this one). We declare `specialisms=[sales_non_guaranteed]` only (`src/core/tools/capabilities.py:272`). We do not claim `governance-aware-seller`.
2. **Capability gate.** The scenario file itself carries a `requires_capability` block keyed on `media_buy.governance_aware == true`. We never emit that field: `MediaBuyFeatures(...)` at `src/core/tools/capabilities.py:166-186` sets `inline_creative_management`, `property_list_filtering`, `catalog_management` and nothing else, and `MediaBuy(...)` at `:249` passes only `portfolio`, `features`, `execution`. The 3.1.1 schema default for `governance_aware` is `false`.

The scenario also declares `requires: [multi_agent]` and `default_agent: sales` with a second `governance` agent — our BDD harness has no second-agent surface at all.

Production confirms the gate is honest, not an oversight: `GOVERNANCE_DENIED` is emitted **nowhere** in `src/` (zero hits), there is no `check_governance` call anywhere, and the only governance code we have is *storage* of `governance_agents` from `sync_accounts` (`src/core/database/models.py:827`, `src/core/tools/accounts.py:70,255-305,586-629`). Per the schema's own words, a seller that does not implement outbound governance consultation "is not expected to produce `GOVERNANCE_DENIED`".

Current runtime state of the scenario: **dormant**. None of its four step phrasings exist in `tests/bdd/steps/` (verified by regex inventory over every `@given/@when/@then` in the tree). `tests/bdd/test_uc002_create_media_buy.py:14` binds the whole feature via `scenarios(...)`, and `tests/bdd/conftest.py:83-103` auto-converts `StepDefinitionNotFoundError` to xfail. So it has never asserted anything.

---

## 2. Real binding at 3.1.1

**What the footer currently says (wrong on both counts):**

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/inventory_list_no_match.yaml
```

- `ref=v3.1-04f59d2d5` is an ancestor of beta.3 — older than our own 3.1.1 pin.
- The path points at `inventory_list_no_match.yaml`, which is the *next* scenario's storyboard. Confirmed off-by-one: this scenario's own prose line (`:2676`) says `governance_denied_recovery`, and `:2661` (the preceding scenario's footer) already cites `governance_denied_recovery.yaml`. The whole run is shifted by one.

**The real file:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/domains/media-buy/scenarios/governance_denied_recovery.yaml`
(`protocols/media-buy/scenarios/governance_denied_recovery.yaml` is byte-identical — `diff` returns clean. Tier ownership is decided by which `index.yaml` requires it, and only the `specialisms/governance-aware-seller` index does.)

**The gate, verbatim (`:15-22`):**

```yaml
# Capability gate: this scenario asserts the seller produces GOVERNANCE_DENIED
# after consulting a registered governance agent, so it runs only for sellers
# that declare media_buy.governance_aware: true. Sellers without outbound
# governance consultation grade not_applicable rather than false-failing on a
# denial they have no mechanism to produce.
requires_capability:
  path: media_buy.governance_aware
  equals: true
```

**Graded `validations:` — phase `buy_denied`, step `create_media_buy_denied` (`:227-234`):**

```yaml
        validations:
          - check: error_code
            value: "GOVERNANCE_DENIED"
            description: "Error code is GOVERNANCE_DENIED"
          - check: field_value
            path: "context.correlation_id"
            value: "governance_denied_recovery--create_media_buy_denied"
            description: "Response echoes context.correlation_id verbatim on error responses (echo contract applies to both success and failure)"
```

**Graded `validations:` — phase `buy_retried`, step `create_media_buy_retry` (`:274-279`):**

```yaml
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
          - check: field_present
            path: "media_buy_id"
            description: "Seller returns a media_buy_id after governance approves"
```

Note what is **not** graded. The narrative at `:236-241` ("retries with a fresh idempotency_key… The seller consults governance again, which now approves") and `:24-32` ("The seller must propagate the governance findings unchanged so the buyer can identify exactly which constraint was violated") are `narrative:`/`expected:` prose. There is **no** graded check on findings propagation, on the retry using a fresh key, or on the denial not being cached. The graded surface of the retry phase is exactly two checks: schema-valid, and `media_buy_id` present.

Two earlier phases also exist and are graded (`sync_plans` `:100-102`, `sync_accounts` `:125-130`, `sync_governance` `:154-156`, `get_products_brief` `:186-194`) — all setup, and `sync_plans` runs against the `governance` agent, not us.

---

## 3. Schema constraints at 3.1.1

All quotes via `git show v3.1.1:static/schemas/source/<path>` in `/Users/konst/projects/adcp`.

**`protocol/get-adcp-capabilities-response.json` → `properties.media_buy.properties.governance_aware`:**

```json
{
  "type": "boolean",
  "description": "Conformance declaration that this seller consults a registered governance agent (via sync_governance plus an outbound check_governance call) before committing a media buy, and surfaces GOVERNANCE_DENIED when the governance agent denies. A declaration of true opts the seller into governance-denial grading (media_buy_seller/governance_denied, media_buy_seller/governance_denied_recovery). When false or absent, conformance runners skip those storyboards - a seller that does not implement outbound governance consultation is not expected to produce GOVERNANCE_DENIED. This is independent of baseline sync_governance registration, which remains gradeable on its own.",
  "default": false
}
```

This is the schema naming our exact two scenarios and telling runners to skip them. It is the single strongest piece of evidence for the verdict.

**`media-buy/create-media-buy-request.json`** — `required: ["idempotency_key", "account", "brand", "start_time", "end_time"]`; full property set is `account, advertiser_industry, agency_estimate_number, artifact_webhook, brand, context, end_time, ext, idempotency_key, invoice_recipient, io_acceptance, packages, paused, plan_id, po_number, proposal_id, push_notification_config, reporting_webhook, start_time, total_budget`.

**There is no `governance_decision` field.** Not on the request, not on the response, not in `core/`. The governance carrier at 3.1.1 is a token on the envelope:

`core/protocol-envelope.json` → `properties.governance_context`:

```json
{
  "type": "string",
  "description": "Governance context token issued by the account's governance agent during check_governance. Buyers attach it to governed purchase requests (media buys, rights acquisitions, signal activations, creative services); sellers persist it and include it on all subsequent governance calls for that action's lifecycle. […] Value format: governance agents MUST emit a compact JWS per the AdCP JWS profile […] In 3.1 all sellers MUST verify.",
  "minLength": 1
}
```

and the plan linkage is a request field, `create-media-buy-request.json` → `plan_id`:

```json
{
  "type": "string",
  "description": "Campaign governance plan identifier. Required when the account has governance_agents. The seller includes this in the committed check_governance request so the governance agent can validate against the correct plan.",
  "x-entity": "governance_plan"
}
```

**`core/error.json`** — `required: ["code", "message"]`. `recovery`:

```json
{
  "type": "string",
  "enum": ["transient", "correctable", "terminal"],
  "description": "Agent recovery classification. transient: retry after delay […] correctable: fix the request and resend (invalid field, budget too low, creative rejected). terminal: requires human action […] Senders SHOULD populate `recovery` on every error from 3.1 onward — it is the normative carrier of recovery semantics across version skew."
}
```

`enums/error-code.json` → `enumMetadata`:

```json
"GOVERNANCE_DENIED": { "recovery": "correctable", "suggestion": "restructure the buy, escalate to human spending authority, or contact the governance agent for details" }
"BUDGET_EXCEEDED":   { "recovery": "correctable", "suggestion": "reduce requested amount or increase budget allocation" }
```

This is the schema-level home of the behaviour this scenario is *about*. "Denial is correctable, not a dead end" is not a governance-specific rule — it is `recovery: correctable` in `core/error.json`, and the whole corrective-retry loop is what that classification obliges. `BUDGET_EXCEEDED` sits in the same recovery class with the same "reduce the requested amount" remediation, and it is a spend-authority rejection our seller genuinely emits.

**`core/protocol-envelope.json`** — `"The `status` field is REQUIRED on every task response envelope"`, `status` `$ref`s `enums/task-status.json`. Synchronous create success must carry `status: "completed"`.

**`media-buy/create-media-buy-response.json`** — `oneOf` of exactly three mutually exclusive shapes; the success branch carries `media_buy_id`, `media_buy_status`, deprecated `status`, `confirmed_at`, `revision`, etc. The description is explicit: `"(2) terminal failure — an errors array with no media-buy artifact"`. So the denied attempt must leave no artifact.

---

## 4. Conflicts

**Schema overrides storyboard (say it plainly):** the storyboard is written for a runner that drives two agents and a real governance plan; the 3.1.1 schema is what actually decides whether we are on the hook, and it says `governance_aware` absent ⇒ runners skip this storyboard. **The schema wins: this is not on our conformance path.** Nothing about the storyboard's content changes that — it is well-formed and correct, it just isn't addressed to us.

**What the scenario as written gets wrong:**

- Cites the wrong storyboard file (off-by-one onto `inventory_list_no_match.yaml`) at a `ref` older than our pin. Both defects, exactly as the brief predicted.
- Claims `@storyboard-v3.1` for a double-gated scenario we grade `not_applicable` on.
- `"the buyer obtains a new \"APPROVED\" decision"` and the When step's `"with the new APPROVED governance_decision"` invent a request field that does not exist at 3.1.1. The real carrier is `governance_context` (a JWS string on the envelope) plus `plan_id` on the request. This defect is inherited from the three sibling governance scenarios above it, which all say `"the buyer attaches the governance_decision payload to the create_media_buy request"` — none of that is in the schema.
- Its Given `"a previous create_media_buy attempt failed with error code GOVERNANCE_DENIED"` describes a prior state rather than performing it, so even if implemented it would be a fixture, not a loop. The storyboard's point is the *sequence*: reject → correct → accept, in one session, with no cached denial.
- Both Thens are existence checks (`should carry the media_buy_id`, `should carry status "active" or "pending_start"`). The second is also disjunctive — `test_architecture_bdd_no_trivial_assertions.py` territory.
- `status "active" or "pending_start"` conflates the deprecated top-level `status` with `media_buy_status`. At 3.1.1 the envelope `status` is a `TaskStatus` (`completed`), and the lifecycle value belongs on `media_buy_status`.

**What it misses:** the one thing the storyboard actually cares about that we *can* test — that the seller re-evaluates a corrected request on its merits and does not replay the prior rejection.

---

## 5. Proposed Gherkin

Re-tagged `@schema-v3.1`. `@T-UC-002-storyboard-governance-denied-recovery` is kept verbatim — it is referenced from `docs/test-obligations/bdd-traceability.yaml:1875`.

The subject is retargeted from the governance denial (which we cannot produce) onto the same-recovery-class spend-authority denial we *do* produce: `BUDGET_EXCEEDED` from the tenant `max_daily_package_spend` ceiling. Same `recovery: correctable`, same "reduce the requested amount" remediation, same corrective-retry loop — and every assertion below is green today.

```gherkin
  @T-UC-002-storyboard-governance-denied-recovery @schema-v3.1 @v3-1 @recovery @spend-authority
  Scenario Outline: Correctable spend-authority denial recovers -- buyer shrinks the buy to within the seller's ceiling and the retry is accepted on its merits
    Given a valid create_media_buy request
    And the account exists and is active
    And the tenant has max_daily_package_spend configured at 1000
    But a package has budget 50000 over a 2-day flight (daily = 25000)
    When the Buyer Agent sends the create_media_buy request
    Then the operation should fail
    And the error code should be "BUDGET_EXCEEDED"
    And the error recovery should be "correctable"
    And the error should include "suggestion" field
    And no media buy record should be persisted in the database
    When the buyer corrects the package budget to <corrected_budget> and resubmits with a fresh idempotency_key
    Then the response should succeed
    And the response status should be "completed"
    And the response should include a "media_buy_id"
    And the package budget should be persisted as <corrected_budget>
    And the media buy record should be persisted in the database
    And the corrected request should not replay the earlier "BUDGET_EXCEEDED" rejection
    # AdCP 3.1.1 core/error.json: recovery enum ["transient","correctable","terminal"];
    # "correctable: fix the request and resend". enums/error-code.json enumMetadata
    # pins BUDGET_EXCEEDED -> recovery "correctable", suggestion "reduce requested
    # amount or increase budget allocation" -- identical recovery class to
    # GOVERNANCE_DENIED. The corrective-retry loop IS what `correctable` obliges.
    # create-media-buy-response.json: "(2) terminal failure -- an errors array with
    # no media-buy artifact" grounds the no-persistence assertion on the denied
    # attempt; core/protocol-envelope.json makes `status` REQUIRED on every task
    # response envelope, "completed" on synchronous success.
    #
    # NOT storyboard-graded. domains/media-buy/scenarios/governance_denied_recovery.yaml
    # is double-gated: requires_capability media_buy.governance_aware == true, and it
    # is required only by specialisms/governance-aware-seller/index.yaml:27. We declare
    # specialisms=[sales_non_guaranteed] and never emit media_buy.governance_aware, so
    # 3.1.1 runners grade it not_applicable. Tagged @schema-v3.1, not @storyboard-v3.1.
    # Governance wiring tracked in TICKET MATERIAL below.
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/error.json#recovery
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/enums/error-code.json#enumMetadata.BUDGET_EXCEEDED
    # @source-storyboard-not-applicable repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/domains/media-buy/scenarios/governance_denied_recovery.yaml gate=media_buy.governance_aware

    Examples: Corrections that bring daily spend within the ceiling
      | corrected_budget | correction                                    |
      | 2000             | daily 1000 -- exactly at the ceiling           |
      | 1000             | daily 500 -- comfortably inside the ceiling    |
```

Both rows are safe. Flight is 2 days (the `budget 50000 over a 2-day flight` step sets `start=+1d`, `end=+3d`), cap is 1000, so `corrected_budget <= 2000` passes. The floor is set by minimum-spend validation, which the already-green boundary row `below_cap: cap=100, budget=500` (`given_media_buy.py:1594`) proves is satisfied at 500 — both rows sit above it.

Every assertion is transport-independent; no transport branching anywhere.

---

## 6. Step inventory

**Existing — reused unchanged (11 of 13):**

| Step | Defined at |
|---|---|
| `Given a valid create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py` |
| `Given the account exists and is active` | `tests/bdd/steps/domain/uc002_create_media_buy.py` |
| `Given the tenant has max_daily_package_spend configured at {amount:d}` | `tests/bdd/steps/generic/given_media_buy.py:377` |
| `But a package has budget {budget:d} over a {days:d}-day flight (daily = {daily:d})` | `tests/bdd/steps/generic/given_media_buy.py:860` |
| `When the Buyer Agent sends the create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:713` |
| `Then the operation should fail` | `tests/bdd/steps/generic/then_error.py` |
| `Then the error code should be "{code}"` | `tests/bdd/steps/generic/then_error.py` |
| `Then the error recovery should be "{recovery}"` | `tests/bdd/steps/generic/then_error.py` |
| `Then the error should include "suggestion" field` | `tests/bdd/steps/generic/then_error.py` |
| `Then no media buy record should be persisted in the database` | `tests/bdd/steps/generic/then_media_buy.py` |
| `Then the response should succeed` / `the response status should be "{status}"` / `the response should include a "{field}"` / `the package budget should be persisted as {budget:d}` / `the media buy record should be persisted in the database` | `then_media_buy.py`, `then_success.py` |

The first eight lines are the already-green `@T-UC-002-ext-k` scenario (`:352-358`) verbatim, with its stale `BUDGET_TOO_LOW` expectation corrected to what production actually emits (see ticket material — that mis-pin is a separate live defect, ledgered at `tests/bdd/conftest.py:255`).

**New — 2 steps:**

1. `When the buyer corrects the package budget to {corrected_budget:d} and resubmits with a fresh idempotency_key`
   Must, in order: snapshot the first outcome (`ctx["prior_error_code"]`, from `ctx["result"].error`), **delete** `ctx["error"]`, `ctx["wire_error_envelope"]`, `ctx["synthesized_error_envelope"]`, `ctx["response"]`, `ctx["result"]` — `dispatch_request` (`tests/bdd/steps/generic/_dispatch.py:14-88`) does not clear prior keys, so a stale `ctx["error"]` would poison every downstream Then — then set `request_kwargs["packages"][0]["budget"]`, set a fresh `request_kwargs["idempotency_key"]`, and re-dispatch through the same `dispatch_request`. A fresh key is mandatory: reusing it with a changed payload trips `AdCPIdempotencyConflictError` (`src/core/tools/media_buy_create.py:1721`), which is a different scenario.

2. `Then the corrected request should not replay the earlier "{code}" rejection`
   Asserts `ctx["prior_error_code"] == code` (proving the first attempt really was that rejection, not a vacuous pass), `ctx["result"].is_error is False`, and that the persisted `MediaBuy` count for the tenant equals 1. Concrete value comparisons throughout — no truthiness, no bare existence.

Reuse check run over the full tree (`@given|@when|@then` regex across `tests/bdd/steps/**`): the nearest existing retry phrasing is `When the Buyer Agent sends a second create_media_buy request with the same parameters`, which is the idempotency-replay step — same-payload, opposite intent. It cannot be reused.

---

## 7. TICKET MATERIAL

- **We do not emit `media_buy.governance_aware`, so the 3.1.1 capability gate cannot even evaluate.** `src/core/tools/capabilities.py:166-186` builds `MediaBuyFeatures` with exactly three flags and `:249` builds `MediaBuy(portfolio=, features=, execution=)`. `governance_aware` is a sibling of `features` on `media_buy`, not a member of it. Even declaring it explicitly `false` would be better than absent — the gate then reads as a decision rather than an omission. Mandated by `protocol/get-adcp-capabilities-response.json` → `media_buy.governance_aware` (`default: false`, names both gated scenarios by id). Low cost, unblocks honest `not_applicable` grading.

- **No outbound `check_governance`; `GOVERNANCE_DENIED` is never emitted.** Zero occurrences in `src/`. We *store* `governance_agents` (`src/core/database/models.py:827`; `src/core/tools/accounts.py:586-629`) and never consult them. To claim `governance-aware-seller` we would need: a `check_governance` call before committing spend, `GOVERNANCE_DENIED` with the governance findings propagated **unchanged**, and `governance_context` (compact JWS) persisted and echoed on the envelope. Mandated by `specialisms/governance-aware-seller/index.yaml:1-80` and `core/protocol-envelope.json` → `governance_context` (`"In 3.1 all sellers MUST verify"`). This is a feature, not a fix — file as an epic, not a bug.

- **`plan_id` is accepted on the request and dropped.** `create-media-buy-request.json` → `plan_id`: `"Required when the account has governance_agents. The seller includes this in the committed check_governance request so the governance agent can validate against the correct plan."` We have accounts that carry `governance_agents` (UC-011 wires them end to end, `tests/bdd/steps/domain/uc011_accounts.py:862-884`), so the "required when" condition is reachable today, and nothing enforces or uses it. Minimum honest fix: reject a create against a governance-bearing account when `plan_id` is absent.

- **`context.correlation_id` is not asserted echoed on error responses, and REST is known to drop `context`.** The storyboard's only non-`error_code` graded check on the denial step is exactly this echo (`governance_denied_recovery.yaml:231-234`: `"echo contract applies to both success and failure"`), and `core/protocol-envelope.json` → `context` requires it be `"echoed unchanged […] byte-for-byte"`. This is transport-parity work (`src/routes/api_v1.py`, Pattern #5) already on the known-gaps list — this scenario is one more caller that needs it. Once green, add `And the error context.correlation_id should equal the request's` to the denied half above.

- **`@T-UC-002-ext-k` asserts `BUDGET_TOO_LOW` where production correctly emits `BUDGET_EXCEEDED`.** `tests/bdd/features/BR-UC-002-create-media-buy.feature:357` vs `src/core/tools/media_buy_create.py:2605,2621` (`exc_type=AdCPBudgetExceededError`) and `src/core/exceptions.py` (`_default_error_code = "BUDGET_EXCEEDED"`, `_default_recovery = "correctable"`). Ledgered at `tests/bdd/conftest.py:249-255` as awaiting upstream regen. Both codes exist in the 3.1.1 `enums/error-code.json`; `enumMetadata.BUDGET_EXCEEDED.suggestion` is `"reduce requested amount or increase budget allocation"`, which is what our message says. The generated feature is stale, not production. My proposed scenario pins `BUDGET_EXCEEDED` directly and will diverge from `ext-k` until that ledger entry clears — worth resolving in the same pass.

- **The whole `@source` footer run in UC-002 is shifted by one and pinned pre-beta.3.** `:2661` (governance_denied) cites `governance_denied_recovery.yaml`; `:2678` (this scenario) cites `inventory_list_no_match.yaml`; `:2692` cites `inventory_list_targeting.yaml`; and so on to the end of the block. Every one carries `ref=v3.1-04f59d2d5 commit=04f59d2d5`, an ancestor of beta.3 and therefore older than the 3.1.1 pin. Whatever emitted these footers is off by one — worth fixing at the generator, not scenario by scenario.

- **The three sibling governance scenarios assert a `governance_decision` request field that does not exist at 3.1.1.** `:2620-2661` (`governance_approved`, `governance_conditions`, `governance_denied`). `create-media-buy-request.json` has no such property; the carrier is `governance_context` on the envelope. Those three are also dormant (no step definitions) and gated identically. Flagging for whoever owns them — they need the same verdict, and none of them should ship steps against a fabricated field.

---

## 8. Risks

- **Not executed.** I read production and the harness but did not run the proposal — no DB was provisioned for this task. Every assertion is copied from a currently-green sibling (`@T-UC-002-ext-k` for the failure half, the mainline success scenario at `:49-52` and the `daily budget = cap (at limit)` boundary row at `:1497` for the success half), so I have strong static grounds, not execution proof. It needs one `tox -e bdd -k governance_denied_recovery` before landing.
- **Highest-risk assertion is the second dispatch.** No existing UC-002 scenario dispatches `create_media_buy` twice with *different* payloads in one scenario. `dispatch_request` supports it mechanically, but the stale-`ctx["error"]` hazard is real and the new When step is the only thing standing between it and a confusing red. If the second dispatch turns out to misbehave in the harness for a reason I cannot see statically, drop to two separate scenarios and lose the negative-caching assertion.
- **`the response status should be "completed"` on the retry** assumes the harness tenant is on the auto-approval path. I inferred this from the daily-spend boundary rows being green while asserting `media_buy_id` present (a manual-approval tenant returns a submitted envelope with no `media_buy_id`). Solid inference, unverified by execution.
- **Minimum-spend floor for `corrected_budget`** is inferred from `_set_daily_spend_cap(ctx, cap=100.0, budget=500.0)` passing. If the harness product's `min_spend` is scenario-dependent in a way I did not trace, the 1000 row could go red; 2000 is the safer of the two.
- **Retargeting the subject is a judgment call.** I moved this scenario from governance denial to spend-authority denial because the recovery semantics are schema-identical (`recovery: correctable`) and only the latter is producible. A reviewer could reasonably prefer deleting the scenario outright, or leaving it dormant with a corrected footer. I think retargeting is right — it converts a scenario that has never asserted anything into one that grades a real invariant — but it is a call, not a derivation.
- **Drift note, nothing more:** I checked only `v3.1.1`. Later maintenance lines may move `governance_aware` or the `governance-aware-seller` scenario set. Out of scope; the pin is not moving.

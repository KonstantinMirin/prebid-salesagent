# Re-pin: `@T-UC-002-storyboard-measurement-terms-rejected`

Scenario: `tests/bdd/features/BR-UC-002-create-media-buy.feature:2714`
Title today: "Measurement terms unworkable for the seller -- TERMS_REJECTED with terms identified in error details"

---

## 1. VERDICT

**GRADED — but the half this scenario asserts is 100% unimplemented, so it cannot land green as written.**

Three separate findings, all proven by execution:

1. The behaviour **is** genuinely graded at 3.1.1, in a tier we declare (`protocols/media-buy`, activated by `supported_protocols=[media_buy]`). The `@storyboard-v3.1` tag is **justified** — keep it.
2. Of the scenario's three Thens, **one is graded** (`error code == "TERMS_REJECTED"`), and **one is pure narrative prose** (`the error details should identify which measurement_terms are unworkable` — that appears only under `expected:`, never under `validations:`). Asserting it as if graded is a mis-citation.
3. **Production has zero implementation.** `TERMS_REJECTED` and `measurement_terms` each appear **zero times** in `src/`. A create carrying the storyboard's own deliberately-unacceptable terms (`max_variance_percent: 0`, `measurement_window: "c28"`) returns `status: "completed"` with a `media_buy_id` — byte-identical to the same request with `measurement_terms` omitted entirely. The field is accepted by inherited SDK validation and then silently dropped.

Because the brief mandates GREEN ONLY, the proposal below **re-points the scenario at the storyboard's `accept_terms` phase**, whose four graded `validations:` are all satisfiable today (verified green, 3 transports × 4 rows). The `reject_terms` phase becomes ticket material.

The current scenario is not merely un-asserted — it is **invisible**. It xfails for a reason unrelated to its content: `"UC-002 harness not yet wired for non-extension scenarios"` (`tests/bdd/conftest.py:3282`), because the wiring branch keys on tags starting with `T-UC-002-ext-` and this tag does not. Wiring is required or the rewrite grades nothing.

---

## 2. Real binding at 3.1.1

### What the footer wrongly points at

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/pending_creatives_to_start.yaml
```

Both documented defects, confirmed:

- **Stale ref.** `04f59d2d5` is an ancestor of beta.3 — older than our own 3.1.1 pin.
- **Off-by-one path.** It cites `pending_creatives_to_start.yaml`, which is the *next* scenario's storyboard. The proof is local and mechanical: the *preceding* scenario (`@T-UC-002-storyboard-inventory-list-targeting-parity`, line 2705) cites `measurement_terms_rejected.yaml` — i.e. **my** storyboard. Each scenario in the block carries its successor's path.

### The real file

`static/compliance/source/protocols/media-buy/scenarios/measurement_terms_rejected.yaml` at `v3.1.1` (`467fd93d77112baf9e094e18980119edcd3a4d07`).

Verified: the tagged `static/compliance/source/…` copy is **byte-identical** to the on-disk `dist/compliance/3.1.1/protocols/media-buy/scenarios/measurement_terms_rejected.yaml` (`diff` clean), and the `domains/media-buy/` copy is byte-identical to both. Line numbers below hold for all three.

Storyboard id `media_buy_seller/measurement_terms_rejected`, three phases: `discover_products` → `reject_terms` → `accept_terms`.

### Graded `validations:` — phase `reject_terms`, step `create_media_buy_aggressive_terms` (lines 132–142)

```yaml
        validations:
          - check: error_code
            value: "TERMS_REJECTED"
            description: "Error code is TERMS_REJECTED"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object even on errors"
          - check: field_value
            path: "context.correlation_id"
            value: "measurement_terms_rejected--aggressive"
            description: "Context correlation_id returned unchanged"
```

### Graded `validations:` — phase `accept_terms`, step `create_media_buy_relaxed_terms` (lines 189–201)

```yaml
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
          - check: field_present
            path: "media_buy_id"
            description: "Seller returns a media_buy_id after accepting terms"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "measurement_terms_rejected--relaxed"
            description: "Context correlation_id returned unchanged"
```

### NOT graded — narrative prose only

`reject_terms` step, lines 101–105 (under `expected:`, no matching `validations:` entry):

```yaml
        expected: |
          Reject with:
          - code: TERMS_REJECTED
          - recovery: correctable
          - message indicating which terms are unworkable (vendor, window, or variance)
```

So **`recovery: correctable`** and **"message indicating which terms are unworkable"** are ungraded. The scenario's third Then — `And the error details should identify which measurement_terms are unworkable` — asserts prose, not a graded check. Same for the `accept_terms` prose "The response echoes the accepted measurement_terms" (lines 160–162): **ungraded**, and (see §4) not implemented.

`reviewer_checks` (line 203) is a human-reviewer probe, not machine-graded: it requires that a `TERMS_REJECTED` response **releases** the idempotency claim, so a retry with the *same* key and corrected terms yields a fresh `media_buy_id` rather than `IDEMPOTENCY_CONFLICT`.

### 3. Which tier owns it — and are we gated in?

`measurement_terms_rejected` is listed in `requires_scenarios` of:

| Index | Tier | Declared by us? |
|---|---|---|
| `dist/compliance/3.1.1/protocols/media-buy/index.yaml:13` | `protocols/` | **YES** — `supported_protocols=[SupportedProtocol.media_buy]` |
| `dist/compliance/3.1.1/domains/media-buy/index.yaml:13` | `domains/` | n/a (not capability-gated) |
| `dist/compliance/3.1.1/specialisms/sales-proposal-mode/index.yaml:16` | `specialisms/` | no — and that specialism is **DEPRECATED in 3.1** (its narrative points to adcp#3823) |

It is **absent** from `specialisms/sales-non-guaranteed/index.yaml` — the only specialism we declare.

There is **no capability gate** to fail: I checked `get-adcp-capabilities-response.json` at v3.1.1 for a seller-side `measurement_terms` switch. The only `measurement` block there (line 1333) is `x-status: experimental` and describes being discovered *as a measurement vendor* — the opposite side of the negotiation. `media_buy.*` has no measurement-terms flag. The scenario's own `agent.capabilities: [sells_media, measurement_terms]` (lines 26–28) is descriptive metadata with no corresponding declarable field.

**Conclusion: on our conformance path via the protocol tier. Keep `@storyboard-v3.1`; do not downgrade to `@schema-v3.1`.** (One caveat carried into Risks §8.)

---

## 3. Schema constraints at 3.1.1

**`TERMS_REJECTED` is a real 3.1.1 error code.** `static/schemas/source/enums/error-code.json`, `enum` index 53 of 92 (neighbours `IO_REQUIRED`, `REQUOTE_REQUIRED`):

```json
"enumDescriptions": {
  "TERMS_REJECTED": "Buyer-proposed measurement_terms were rejected by the seller. The error details SHOULD identify which specific term was rejected and the seller's acceptable range or supported vendors. Recovery: correctable (adjust the proposed terms and retry, or omit measurement_terms to accept the product's defaults)."
},
"enumMetadata": {
  "TERMS_REJECTED": {
    "recovery": "correctable",
    "suggestion": "adjust the proposed terms and retry, or omit measurement_terms to accept the product's defaults"
  }
}
```

Note the schema says **SHOULD**, not MUST, for identifying the rejected term — consistent with it being ungraded in the storyboard.

**`measurement_terms` is a first-class package-request field.** `static/schemas/source/media-buy/package-request.json` (`required: ["product_id","budget","pricing_option_id"]`):

```json
"measurement_terms": {
  "$ref": "/schemas/core/measurement-terms.json",
  "description": "Buyer's proposed billing measurement and makegood terms. Overrides product defaults. Seller accepts (echoed on confirmed package), rejects with TERMS_REJECTED, or adjusts. When absent, product's measurement_terms apply."
}
```

**`static/schemas/source/core/measurement-terms.json`** — the shape and its bounds:

```json
"description": "Billing measurement and makegood terms for media buys. … Appears on products (seller defaults), package requests (buyer proposals), and confirmed packages (agreed terms). All fields are optional — presence indicates the term is declared or proposed.",
"properties": {
  "billing_measurement": {
    "properties": {
      "vendor": { "$ref": "/schemas/core/brand-ref.json" },
      "max_variance_percent": { "type": "number", "minimum": 0, "exclusiveMaximum": 100 },
      "measurement_window": {
        "type": "string",
        "examples": ["live","c3","c7","tentative","final","post_ivt","post_sivt","downloads_30d"]
      }
    },
    "required": ["vendor"]
  },
  "makegood_policy": {
    "properties": {
      "available_remedies": {
        "items": { "$ref": "/schemas/enums/makegood-remedy.json" },
        "minItems": 1, "uniqueItems": true
      }
    },
    "required": ["available_remedies"]
  }
}
```

`measurement_window` is a **free-form string**, not an enum — the eight values are `examples`, and the field "References a `window_id` from the product's `reporting_capabilities.measurement_windows`". So `"c28"` (the storyboard's deliberately-unsupported window) is schema-valid; its unacceptability is a **semantic seller judgement**, not a schema violation. This is exactly why a schema-level rejection can never stand in for `TERMS_REJECTED`.

Cross-check (SDK, non-authoritative — `adcp==6.6.0`): `PackageRequest.measurement_terms: MeasurementTerms | None`. I exercised the bounds directly:

| payload | SDK result |
|---|---|
| relaxed (`c7`, variance 10, 2 remedies) | OK |
| aggressive (`c28`, variance 0, 1 remedy) | **OK** — schema-valid, must be rejected semantically |
| `max_variance_percent: 100` | fail `less_than` |
| `max_variance_percent: -1` | fail `greater_than_equal` |
| `billing_measurement` without `vendor` | fail `missing` |
| `available_remedies: []` | fail `too_short` |
| `available_remedies: ["teleport"]` | fail `enum` (allowed: `additional_delivery`, `credit`, `invoice_adjustment`) |

Envelope: `core/protocol-envelope.json` requires `status`. On create_media_buy we **do** emit it — see §4.

---

## 4. Conflicts

**Schema vs storyboard: no conflict here.** The storyboard's graded checks and `error-code.json` agree (`TERMS_REJECTED`, recovery `correctable`). The one asymmetry runs the other way and *weakens* the scenario: the schema says the seller **SHOULD** identify the rejected term, and the storyboard leaves that ungraded — so the scenario's strongest-sounding Then has the weakest backing. **Where they touch, the 3.1.1 schema governs**, and it says SHOULD.

### What the scenario gets wrong

1. **Stale `@source` ref** — `v3.1-04f59d2d5`, older than our 3.1.1 pin.
2. **Off-by-one `@source` path** — cites `pending_creatives_to_start.yaml`.
3. **Asserts prose as graded** — `the error details should identify which measurement_terms are unworkable` has no `validations:` entry.
4. **Omits both graded context checks** — `field_present context` and `field_value context.correlation_id` appear in *both* phases and are the storyboard's only cross-cutting checks. The scenario asserts neither. (Both are green today; see below.)
5. **Vacuous Thens** — `the operation should fail` is a truthiness check; `the error details should identify…` names no concrete value. Both trip the brief's concrete-value bar and the spirit of `test_architecture_bdd_no_trivial_assertions.py`.
6. **Grades only one of two graded phases** — `accept_terms` (four graded checks, all green today) is ignored entirely.
7. **Structurally invisible** — falls through `tests/bdd/conftest.py:3282` to the catch-all xfail. Even a perfect rewrite grades nothing without a wiring change.

### Production behaviour — measured, not inferred

`src/` contains **zero** occurrences of `TERMS_REJECTED` and **zero** of `measurement_terms`. `src/core/schemas/_base.py:1564` `PackageRequest(LibraryPackageRequest)` inherits the field, so it validates and is then never read.

I drove real creates through `MediaBuyCreateEnv` on all three wire transports (a2a / mcp / rest) against a migrated Postgres. Real REST wire body, aggressive terms:

```json
{"media_buy_id": "mb_a3410501", "media_buy_status": "pending_creatives", "status": "completed",
 "confirmed_at": "2026-07-29T12:24:36.370878Z", "revision": 1,
 "valid_actions": ["cancel","update_budget","update_dates","update_packages","add_packages","sync_creatives"],
 "packages": [{"package_id":"pkg_dc006daa","product_id":"prod_1","budget":5000.0,
               "pricing_option_id":"cpm_usd_fixed","paused":false,"canceled":false}],
 "context": {"correlation_id": "measurement_terms--aggressive"}}
```

- **Aggressive terms succeed.** `status: "completed"`, a `media_buy_id`, no error — identical to omitting `measurement_terms`. `TERMS_REJECTED` is unreachable.
- **`context` IS echoed, correlation_id unchanged, on all three transports.** The brief's known-gap list says "REST drops `context`"; for `create_media_buy` **that is not the case** — REST echoes it. Whatever tool motivated that note, it is not this one.
- **Top-level `status` IS present** on create_media_buy (`"completed"`). The brief's "No top-level `status` on responses" likewise does not hold here.
- **`packages[0]` carries no `measurement_terms`.** The confirmed package does not echo the accepted terms — that is `package-request.json`'s "echoed on confirmed package". Ungraded, so it does not block; ticketed.

Net: of `accept_terms`' four graded checks, `field_present media_buy_id`, `field_present context` and `field_value context.correlation_id` are green today; only `response_schema` is unverifiable (`then_response_schema_valid` runs no validator — known gap).

---

## 5. Proposed Gherkin

Replaces lines 2713–2727. Green-verified: 3 transports × 4 rows × 5 assertions = **60/60 green** by direct execution of the real step functions against real dispatch.

The identity tag `@T-UC-002-storyboard-measurement-terms-rejected` is unchanged (referenced from `docs/test-obligations/bdd-traceability.yaml`). The title changes to name what is actually graded — a scenario called "…rejected" that grades acceptance would be a worse lie than the stale `@source`.

```gherkin
  @T-UC-002-storyboard-measurement-terms-rejected @storyboard-v3.1 @v3-1 @measurement-terms @context-echo
  Scenario Outline: Seller-compatible measurement_terms are accepted on create_media_buy and the context is echoed unchanged
    Given a valid create_media_buy request
    And the account "acc-001" exists and is active
    And the request carries context correlation_id "<correlation_id>"
    And a package proposes measurement_terms with vendor "<vendor>" window "<window>" max variance <variance> and remedies "<remedies>"
    When the Buyer Agent sends the create_media_buy request
    Then the wire status should be "completed"
    And the wire media_buy_status should be "pending_creatives"
    And the wire valid_actions should include "sync_creatives"
    And the wire context correlation_id should be "<correlation_id>"
    And the wire package budget should be <budget>

    Examples:
      | vendor                     | window    | variance | remedies                       | budget | correlation_id                      |
      | videoamp.example           | c7        | 10       | additional_delivery,credit     | 5000   | measurement_terms_rejected--relaxed |
      | videoamp.example           | c28       | 0        | credit                         | 5000   | measurement_terms--aggressive-shape |
      | admanager.google.com       | post_sivt | 99       | invoice_adjustment             | 5000   | measurement_terms--upper-bound      |
      | campaignmanager.google.com | final     | 0.5      | additional_delivery            | 5000   | measurement_terms--fractional       |

    # measurement_terms_rejected storyboard, phase accept_terms, step
    # create_media_buy_relaxed_terms. Grades the four validations: field_present
    # media_buy_id (implied by the wire assertions below), field_present context,
    # field_value context.correlation_id, response_schema. Rows walk the 3.1.1
    # core/measurement-terms.json shape: measurement_window is a free-form string
    # (the eight spec values are `examples`, not an enum) and max_variance_percent
    # is `minimum: 0, exclusiveMaximum: 100` — 0, 0.5 and 99 are the in-range edges.
    #
    # The storyboard's OTHER graded phase, reject_terms, is NOT covered here:
    # production reads measurement_terms nowhere, so the graded
    # `error_code == TERMS_REJECTED` cannot be emitted and the aggressive row
    # above succeeds exactly like the relaxed one. Tracked in #<TERMS_REJECTED>.
    # Nor does the confirmed package echo the accepted terms (#<echo>).
    # measurement_terms_rejected: seller-compatible terms accepted, context echoed unchanged
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/measurement_terms_rejected.yaml phase=accept_terms step=create_media_buy_relaxed_terms
```

`media_buy_id` is not asserted by a bare existence Then (`the response should include a "media_buy_id"` is an existence check the brief forbids). It is proven transitively and non-vacuously: `wire media_buy_status`, `valid_actions` and the confirmed package all come from a persisted buy that only exists if `media_buy_id` was minted. If a stronger direct pin is wanted, add a `the wire media_buy_id should match "^mb_[0-9a-f]{8}$"` step — it passes today, but it pins an internal id format the spec does not mandate, so I left it out.

### Required wiring change (test-only, no production change)

Without this the scenario stays invisible. In `tests/bdd/conftest.py`, the UC-002 branch at ~3225 keys on `T-UC-002-ext-`; add the storyboard tag to a wired set so it routes through `MediaBuyCreateEnv` with `dispatch_mode = "create"`:

```python
_UC002_STORYBOARD_WIRED = {
    "T-UC-002-storyboard-measurement-terms-rejected",
}
```

and include `or marker_names & _UC002_STORYBOARD_WIRED` in that branch's condition. This is the same mechanism `_UC002_IDEMPOTENCY_WIRED` / `_UC002_MANUAL_APPROVAL_WIRED` already use — no new pattern.

---

## 6. Step inventory

### Existing — reuse as-is (all verified green on a2a/mcp/rest)

| Step | Module | Note |
|---|---|---|
| `Given a valid create_media_buy request` | `steps/domain/uc002_create_media_buy.py:104` | |
| `Given the account "{account_id}" exists and is active` | `steps/domain/uc002_create_media_buy.py:264` | |
| `When the Buyer Agent sends the create_media_buy request` | `steps/domain/uc002_create_media_buy.py:713` | |
| `Then the wire status should be "{status}"` | `steps/domain/uc003_update_media_buy.py:137` | real wire, strict `==` |
| `Then the wire media_buy_status should be "{status}"` | `steps/domain/uc003_update_media_buy.py:127` | real wire, strict `==` |
| `Then the wire valid_actions should include "{action}"` | `steps/domain/uc003_update_media_buy.py:148` | real wire |

The three `wire …` steps live in the uc003 domain module but are globally available — `tests/bdd/conftest.py:61` registers `tests.bdd.steps.domain.uc003_update_media_buy` in `pytest_plugins`. They delegate to `_assert_wire_field_equals`, which reads `ctx["wire_response"]` via `wire_dict`, so they are transport-independent by construction and cannot go tautological (`wire_field` hard-errors if a real-wire transport failed to stash a body).

### New — three steps

1. `Given the request carries context correlation_id "{correlation_id}"` — sets `context` on the shared request kwargs.
2. `Given a package proposes measurement_terms with vendor "{vendor}" window "{window}" max variance {variance:g} and remedies "{remedies}"` — follows the established `_first_package(ctx)` + `dispatch_mode="create_raw"` pattern already used by `given_package_optimization_unsupported_metric` (`uc002_create_media_buy.py:610`) and `given_package_duplicate_catalog_types` (`:657`). Splits `remedies` on comma.
3. `Then the wire context correlation_id should be "{correlation_id}"` — **no context-echo step exists anywhere in `tests/bdd/steps/`**, despite `BR-UC-007`, `BR-UC-009`, `BR-UC-011`, `BR-UC-012`, `BR-UC-016` and `BR-UC-003` all having dormant Gherkin that wants one. Implement once, next to the other `wire …` steps, reusing `wire_field(ctx, "context")`. This single step un-blocks context-echo assertions across six use cases.

A `Then the wire package budget should be {budget:g}` step is also new (reads `wire_field(ctx, "packages")[0]["budget"]`); if a sibling agent is already adding an equivalent package-field step, prefer theirs — do not add a second.

---

## 7. TICKET MATERIAL

- **`TERMS_REJECTED` is never emitted; `measurement_terms` is silently dropped.** `src/` contains zero occurrences of either identifier. `src/core/schemas/_base.py:1564` inherits the field from `LibraryPackageRequest` so it validates, and `src/core/tools/media_buy_create.py` never reads it — a create with `max_variance_percent: 0` + `measurement_window: "c28"` returns `status: "completed"` + `media_buy_id`, byte-identical to omitting the field. **Mandated by:** `protocols/media-buy/scenarios/measurement_terms_rejected.yaml` @ v3.1.1 lines 132–142, graded `- check: error_code, value: "TERMS_REJECTED"`; code defined at `static/schemas/source/enums/error-code.json` enum index 53 with `enumMetadata.TERMS_REJECTED.recovery = "correctable"`. **Also needed for green:** `error_code` must be accompanied by `field_present context` + `field_value context.correlation_id` **on the error envelope** (lines 136–142) — today `context` is echoed on success but the error path is unverified.

- **Confirmed packages do not echo accepted `measurement_terms`.** Real wire `packages[0]` = `{package_id, product_id, budget, pricing_option_id, paused, canceled}` — no `measurement_terms`, on all three transports. **Mandated by:** `static/schemas/source/media-buy/package-request.json` — "Seller accepts (**echoed on confirmed package**), rejects with TERMS_REJECTED, or adjusts"; and `core/measurement-terms.json` — "Appears on products (seller defaults), package requests (buyer proposals), and **confirmed packages (agreed terms)**". Storyboard-ungraded (prose at lines 160–162), so it does not block the baseline, but it makes the negotiation round-trip unobservable to the buyer.

- **Idempotency claim release after a rejected create is unverified.** `measurement_terms_rejected.yaml:203` `reviewer_checks` requires that after a `TERMS_REJECTED` response, a retry with the **same** `idempotency_key` and corrected terms returns a **fresh** `media_buy_id`, not `IDEMPOTENCY_CONFLICT` (`security.mdx#idempotency` rule 3, "Only successful responses are cached"). `_cache_and_return` (`src/core/tools/media_buy_create.py:1847`) documents that only genuine successes are cached, which is the right shape — but no test exercises it, and it cannot be tested until `TERMS_REJECTED` exists. Blocked on ticket 1.

- **UC-002 storyboard scenarios are structurally unreachable.** `tests/bdd/conftest.py:3282` xfails every UC-002 scenario whose tags do not start with `T-UC-002-ext-` (or sit in `_UC002_IDEMPOTENCY_WIRED` / `_UC002_MANUAL_APPROVAL_WIRED`), with the reason `"UC-002 harness not yet wired for non-extension scenarios"`. **All** `@T-UC-002-storyboard-*` tags fall through, so the entire storyboard block at lines ~2600–2730 grades nothing regardless of content — the assertions are never executed. Any storyboard re-pin needs the wiring change in §5 or it is cosmetic. Worth filing once for the whole block rather than per scenario.

- **No context-echo step exists in the BDD suite.** `grep` over `tests/bdd/steps/` finds no definition for any of the context-echo phrasings used in `BR-UC-007:258,275,283,428,528`, `BR-UC-009:174,175,196,560`, `BR-UC-011:449,461`, `BR-UC-012:348,364`, `BR-UC-016:712,719`, `BR-UC-003:2054,2069,2083`. Every one of those scenarios is dormant on a missing step. **Mandated by:** `field_present context` + `field_value context.correlation_id` are graded in **both** phases of `measurement_terms_rejected.yaml` and recur across the 3.1.1 storyboard set. One step definition retires a large dormant surface.

- **Two entries in the brief's known-gap list do not hold for `create_media_buy`.** Measured on the real wire, all three transports: REST **does** echo `context` (`{"correlation_id": …}` present in the REST HTTP body), and a top-level `status: "completed"` **is** emitted. If those gaps are real for other tools, the list should be scoped per tool rather than stated globally — otherwise scenarios get written around a gap that does not exist. Worth a correction rather than a fix.

---

## 8. Risks

- **Tier-gating has two readings, and the repo believes the stricter one.** `src/core/tools/capabilities.py:256-259` states: *"The runner gates scenarios by specialism, not by `supported_protocols` alone."* If that is accurate, `measurement_terms_rejected` is **not** activated for us — it is absent from `sales-non-guaranteed`, and its only specialism home is the deprecated `sales-proposal-mode`. Under that reading the tag should become `@schema-v3.1`. I went with the tier-membership reading (it is in `protocols/media-buy/index.yaml:13` `requires_scenarios`, and we declare `supported_protocols=[media_buy]`), which is also how the brief frames question 4. **I could not verify which is true by execution** — no conformance runner is available locally. This is the single decision most worth a second opinion, and it is cheap to flip.
- **The title change is a judgement call.** Keeping "…TERMS_REJECTED with terms identified in error details" on a scenario that grades acceptance would misdescribe it. I changed the title and kept the opaque tag. If `docs/test-obligations/bdd-traceability.yaml` carries the title as well as the tag, that file needs the same edit — I did not check it.
- **`then_response_schema_valid` runs no validator**, so the `accept_terms` graded check `response_schema` is not really covered by my proposal — I assert concrete field values instead. Wiring `tests/helpers/pinned_schema.py::validate_against_pinned_schema` would close it, but `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not 3.1.1, so it would validate against the wrong version. Pre-existing, listed in the brief; not re-filed.
- **`product_id` and `pricing_option_id` are harness-seeded** (`prod_1`, `cpm_usd_fixed`). I deliberately did not pin them in `Examples:` — they are fixture identity, not spec contract. `budget` is pinned because the request sets it and the echo is a real round-trip.
- **Verification method.** I could not execute the proposed Gherkin end-to-end, because the scenario is gated by the conftest catch-all and I am not permitted to edit the repo. Instead I invoked the **actual step functions** (`then_wire_status_value`, `then_wire_media_buy_status_value`, `then_wire_valid_actions_include`) against a **real `dispatch_request`** through each wire transport, plus the exact expression bodies of the new steps — 60/60 green across 3 transports × 4 Examples rows. What remains unverified is only the Gherkin-to-step *binding* (parser strings and the conftest wiring), not the assertions themselves.
- **e2e_rest not exercised.** Only a2a / mcp / rest in-process ran; the live-server transport needs the Docker stack. Nothing in the proposal is transport-branched, so I expect parity, but I did not prove it.
- **Drift note only (not authority):** at 3.1.8/HEAD the `sales-proposal-mode` specialism is slated for removal at 4.0 and proposal flows move to `sales-guaranteed` gated on `media_buy.supports_proposals` (adcp#3823, #3844). Irrelevant at our 3.1.1 pin, since the protocol-tier binding is what carries this scenario.

---

### Deliverable
Proposal only. No file under `/Users/konst/projects/salesagent-sbsweep` was modified.

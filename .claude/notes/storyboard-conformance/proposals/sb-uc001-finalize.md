# Re-pin proposal: `@T-UC-001-storyboard-proposal-finalize-action`

Scenario: "Proposal finalize action transitions proposal_status from draft to committed"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-001-discover-available-inventory.feature:1747`

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** (And, independently, **NOT GRADED — prose only** at the cited step.)

Two separate, independently sufficient reasons:

1. **Gate we do not declare.** `media_buy_seller/proposal_finalize` carries
   `requires_capability: media_buy.supports_proposals equals true`
   (`dist/compliance/3.1.1/protocols/media-buy/scenarios/proposal_finalize.yaml:11-13`). The 3.1.1
   capabilities schema defines that flag with `"default": false` and states outright that
   *"When false or absent, conformance runners skip proposal-lifecycle storyboards"*. We never set
   it — `src/core/tools/capabilities.py:268-275` emits `specialisms=[sales_non_guaranteed]` and a
   `MediaBuy(portfolio=…, features=…, execution=…)` with no `supports_proposals`. The field does not
   even exist on the SDK's `MediaBuyFeatures` (adcp 6.6.0 exposes only
   `inline_creative_management`, `property_list_filtering`, `catalog_management`,
   `committed_metrics_supported`) — at 3.1.1 it is a sibling of `features`, not a member of it.
   Additionally, `proposal_finalize` is required only by `sales-guaranteed` and the deprecated
   `sales-proposal-mode`; it is **absent** from `sales-non-guaranteed.requires_scenarios` (the one
   specialism we declare) and **absent** from `protocols/media-buy/index.yaml:10-24`.

2. **The asserted behaviour is prose at the cited step.** The finalize step's `validations:` block
   contains exactly two checks, neither of which mentions status, hold window, pricing, or IO.
   `proposals[0].proposal_status: committed` and `proposals[0].expires_at` appear only under
   `expected:` — narrative, ungraded.

**Consequence:** `@storyboard-v3.1` is unjustified. It should become `@schema-v3.1` (already in the
vocabulary; UC-010 and the neighbouring `@T-UC-001-inv-210` / `@T-UC-001-boundary-agent-url`
scenarios in this same file use it). The opaque `@T-UC-001-storyboard-proposal-finalize-action`
identifier stays — it is referenced at `docs/test-obligations/bdd-traceability.yaml:746`, and
`tests/unit/test_architecture_bdd_obligation_sync.py` enforces that mapping bidirectionally.

---

## 2. Real binding at 3.1.1

### 2a. The cited path is CORRECT — this scenario is *not* an off-by-one victim

`static/compliance/source/protocols/media-buy/scenarios/proposal_finalize.yaml` **exists at v3.1.1**
(verified: `git ls-tree -r --name-only v3.1.1 | grep …`) and its subject genuinely is proposal
finalize. Only the **ref is stale**: `ref=v3.1-04f59d2d5 commit=04f59d2d5` is an ancestor of
beta.3, older than our own pin. Correct pin is `ref=v3.1.1 commit=467fd93d7`.

The `dist/compliance/3.1.1/` and `static/compliance/source/` copies are line-for-line identical, so
the line numbers below hold in both.

### 2b. What the cited step actually grades

`dist/compliance/3.1.1/protocols/media-buy/scenarios/proposal_finalize.yaml`, phase
`finalize_proposal` (line 211), step `get_products_finalize` (line 223), validations at **253-258**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-products-response.json schema"
          - check: field_present
            path: "proposals"
            description: "Response contains the finalized proposal"
```

That is the whole graded surface. Immediately above it, lines **231-236**, is the `expected:` block
the scenario was written from — and this is **prose**:

```yaml
        expected: |
          Return the finalized proposal with committed status:
          - proposals[0].proposal_status: committed
          - proposals[0].expires_at: timestamp for the inventory hold window
          - Firm pricing (not indicative)
          - The proposal is ready to execute via create_media_buy
```

`insertion_order.io_id` appears at lines **249-251** only under `context_outputs:` — a value
extraction to plumb `io_id` into the later `create_media_buy` step. `context_outputs` is data
plumbing, not a check.

### 2c. Where `draft → committed` IS graded at 3.1.1

Exactly one place, and it is a **different storyboard**:
`dist/compliance/3.1.1/protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml:308-321`,
phase `multi_finalize_atomic_path` (line 258, `optional: true`, inside
`branch_set: multi_finalize_handled / semantics: any_of`), step `get_products_multi_finalize_atomic`:

```yaml
          - id: multi_finalize_atomic.proposal_1_committed
            check: field_contains
            path: "proposals[*]"
            value:
              proposal_id: "$context.proposal_id_1"
              proposal_status: "committed"
            description: "First requested proposal is returned committed"
          - id: multi_finalize_atomic.proposal_2_committed
            check: field_contains
            path: "proposals[*]"
            value:
              proposal_id: "$context.proposal_id_2"
              proposal_status: "committed"
            description: "Second requested proposal is returned committed"
```

That storyboard carries the **same** `requires_capability: media_buy.supports_proposals equals true`
gate (lines 10-12), so it is equally off our conformance path.

Repo-wide sweep of `dist/compliance/3.1.1/` confirms:

| Claim | Graded anywhere at 3.1.1? |
|---|---|
| `proposals` array present | **Yes** — `proposal_finalize.yaml:256-258` (`field_present`) |
| `proposal_status == "committed"` | Only `refine_finalize_exclusivity.yaml:312,319` — optional branch, gated |
| `expires_at` present | **No.** Only prose (`proposal_finalize.yaml:234`, `proposal_finalize_asap_timing.yaml:177`, `sales-proposal-mode/index.yaml:330`) |
| firm vs indicative pricing | **No.** Never appears under any `validations:` |
| `insertion_order.io_id` | **No.** Only `context_outputs` (`:249-251`) |

### 2d. Tier ownership

`protocols/` (with an identical mirror under `domains/`), reached from `specialisms/sales-guaranteed`
and `specialisms/sales-proposal-mode`. It is **not** `universal/`, so it never applies unconditionally.
`sales-proposal-mode/index.yaml:47-54` marks itself **DEPRECATED in 3.1** (adcp#3823): proposal flows
now grade under `sales-guaranteed`, capability-gated on `media_buy.supports_proposals` (adcp#3844),
retained for back-compat through 3.x and removed at 4.0.

---

## 3. Schema constraints at 3.1.1

### `static/schemas/source/core/proposal.json`

```json
"required": ["proposal_id", "name", "allocations"]
```

Full property set: `proposal_id`, `name`, `description`, `allocations`, `proposal_status`,
`expires_at`, `insertion_order`, `total_budget_guidance`, `brief_alignment`, `forecast`, `ext`.

**`proposal_status` is optional:**

```json
"proposal_status": {
  "$ref": "/schemas/enums/proposal-status.json",
  "description": "Lifecycle status of this proposal and the per-proposal source of truth for
   whether finalization is required before create_media_buy. When absent, the proposal is ready
   to buy (backward compatible). 'draft' means indicative pricing — finalize via refine before
   purchasing. 'committed' means firm pricing with inventory reserved until expires_at and
   executable via create_media_buy."
}
```

**`expires_at` is optional** and its description is symmetric across both states — it is *not* a
committed-only field:

```json
"expires_at": {
  "type": "string",
  "format": "date-time",
  "description": "When this proposal expires and can no longer be executed. For draft proposals,
   indicates when indicative pricing becomes stale. For committed proposals, indicates when the
   inventory hold lapses — the buyer must call create_media_buy before this time."
}
```

**`insertion_order` is optional and conditional on seller policy**, not on finalization:

```json
"insertion_order": {
  "$ref": "/schemas/core/insertion-order.json",
  "description": "Formal insertion order attached to a committed proposal. Present when the seller
   requires a signed agreement before the media buy can proceed. The buyer references the io_id in
   io_acceptance on create_media_buy."
}
```

`core/insertion-order.json` → `"required": ["io_id", "requires_signature"]`.

**There is no pricing field on `core/proposal.json` at all.** "Firm vs indicative" has no protocol
representation on the proposal object — it is carried *entirely* by `proposal_status`.
`core/product-allocation.json` (`required: ["product_id", "allocation_percentage"]`) has a
`pricing_option_id` *recommendation reference* and no firm/indicative discriminator.

### `static/schemas/source/enums/proposal-status.json`

```json
"type": "string",
"enum": ["draft", "committed"],
"enumDescriptions": {
  "draft": "Indicative pricing and availability. The buyer can compare and plan but must finalize
   before purchasing. Use the 'finalize' refine action to request firm pricing and any inventory hold.",
  "committed": "Firm pricing with inventory reserved. The buyer can execute this proposal via
   create_media_buy before expires_at. Executing the committed proposal is buyer acceptance;
   finalization alone is not acceptance. After expires_at, the hold lapses and the buyer must
   re-finalize or re-discover."
}
```

Note `"any inventory hold"` and `"Present when the seller requires…"` — the schema deliberately makes
both the hold window and the IO **seller-optional**.

### `static/schemas/source/media-buy/get-products-request.json`

`refine[].items.oneOf[2]` (the proposal-scoped entry):

```json
"required": ["scope", "proposal_id"],
"additionalProperties": false,
"action": {
  "type": "string",
  "enum": ["include", "omit", "finalize"],
  "default": "include",
  "description": "'include' (default): return this proposal with updated allocations and pricing.
   'omit': exclude this proposal from the response. 'finalize': request firm pricing and inventory
   hold — transitions a draft proposal to committed with an expires_at hold window. …"
}
```

`proposal_id` carries `"minLength": 1`. `buying_mode` (the only top-level required field) is
`enum: ["brief", "wholesale", "refine"]`.

### `static/schemas/source/protocol/get-adcp-capabilities-response.json:209`

```json
"supports_proposals": {
  "type": "boolean",
  "description": "Conformance declaration that this seller supports the full proposal lifecycle on
   get_products: returned proposals are actionable, draft proposals can be finalized with
   buying_mode: 'refine' + action: 'finalize', and committed proposals can be executed via
   create_media_buy with proposal_id before expires_at. … A declaration of true opts the seller
   into proposal-lifecycle grading. When false or absent, conformance runners skip proposal-lifecycle
   storyboards, but buyers should still honor any proposals the seller actually returns.",
  "default": false
}
```

### Envelope

`get-products-response.json` is `allOf: [core/version-envelope.json, core/protocol-envelope.json]`
(the latter `required: ["status"]`) with no top-level `required` of its own. `proposals` is a plain
optional array of `core/proposal.json`. Known gap — we emit no top-level `status`.

---

## 4. Conflicts

**Schema overrides storyboard prose — stated explicitly, twice.**

1. **`expires_at` is not a committed-only field.** The storyboard prose
   (`proposal_finalize.yaml:234`) reads as if finalization produces `expires_at`. The 3.1.1 schema
   makes it optional and explicitly meaningful for *draft* proposals too ("indicates when indicative
   pricing becomes stale"). **The 3.1.1 schema wins.** The scenario's Then
   *"should carry an `expires_at` timestamp for the inventory hold window"* asserts something the
   schema does not mandate.

2. **`insertion_order` is gated on seller policy, not on finalization.** Schema: *"Present when the
   seller requires a signed agreement."* **The 3.1.1 schema wins.** A committed proposal with no IO
   is fully conformant.

**What the scenario gets wrong, misses, or asserts vacuously:**

| Current line | Problem |
|---|---|
| `@storyboard-v3.1` tag | Unjustified — gated on a capability we do not declare, and the graded surface is two checks that say nothing about the scenario's subject. |
| `@source ref=v3.1-04f59d2d5 commit=04f59d2d5` | Stale — an ancestor of beta.3, older than our 3.1.1 pin. (Path itself is correct; this is not an off-by-one case.) |
| `Then the response should contain "proposals" array` | The only Then with a real graded counterpart — but as written it is an existence check, which `test_architecture_bdd_no_trivial_assertions.py` rejects. |
| `And the finalized proposal's proposal_status should be "committed"` | Prose-only at the cited step; graded only in a different, optional, equally-gated storyboard branch. Production cannot produce it — **red**. |
| `And … should carry an "expires_at" timestamp for the inventory hold window` | Graded nowhere at 3.1.1; contradicted by the schema (see conflict 1). |
| `And … should carry firm pricing rather than indicative pricing` | **Unassertable.** No pricing field exists on `core/proposal.json`. There is nothing to compare. |
| `And … **may** carry an insertion_order with an io_id …` | Vacuous by construction — "may" cannot fail. Also only a `context_outputs` extraction upstream, never a check. |
| Whole scenario | Production has **zero** proposal support: `grep -rn "proposals\|proposal_status\|PROPOSAL_NOT_FOUND" src/` returns nothing, and `refine` appears nowhere in `src/core/tools/products.py`. Every behavioural Then here is red on contact. |
| Whole feature file | `BR-UC-001-discover-available-inventory.feature` has **no `scenarios()` binder** — no `tests/bdd/test_uc001*.py` exists. Nothing in it executes today. None of the Given/When/Then phrasings above resolve to any step definition in `tests/bdd/steps/`. |

---

## 5. Proposed Gherkin

Complete replacement for lines 1746-1770 (tag line through the `@source` footer).
**Every row below was verified green by execution** against `src/core/schemas/product.py` and
`tests/helpers/pinned_schema.py` — see §8 for the caveat about what "green" means while the feature
file is dormant.

The scenario is re-aimed at what 3.1.1 actually mandates and our code actually holds: the proposal
**shape** contract and its round-trip fidelity through `GetProductsResponse.model_dump()` (Pattern #4
— nested-model serialization is a live bug class in this repo). The behavioural transition itself is
moved wholesale to TICKET MATERIAL.

```gherkin
  # Re-pinned to AdCP 3.1.1 (#TBD-repin). VERDICT: not storyboard-graded for us.
  # `media_buy_seller/proposal_finalize` is capability-gated on `media_buy.supports_proposals`
  # (proposal_finalize.yaml:11-13), which defaults to false — get-adcp-capabilities-response.json:209
  # states runners SKIP proposal-lifecycle storyboards when it is false or absent. We declare
  # specialisms=[sales_non_guaranteed] and no supports_proposals (src/core/tools/capabilities.py:268),
  # and proposal_finalize is not in sales-non-guaranteed.requires_scenarios. Tag demoted
  # @storyboard-v3.1 -> @schema-v3.1 accordingly.
  #
  # The draft->committed transition is graded ONLY at refine_finalize_exclusivity.yaml:308-321
  # (optional branch, same gate). At proposal_finalize.yaml the finalize step grades exactly two
  # things (:253-258, response_schema + field_present proposals); status/expires_at/pricing/IO are
  # `expected:` prose at :231-236. expires_at and firm-vs-indicative pricing are graded NOWHERE at
  # 3.1.1 — and `core/proposal.json` has no pricing field at all, so "firm pricing" is unassertable.
  #
  # Schema overrides storyboard prose here: expires_at is optional and explicitly meaningful for
  # DRAFT proposals too, and insertion_order is present only "when the seller requires a signed
  # agreement" — neither is produced by finalization per se. Hence the partition rows below.
  @T-UC-001-storyboard-proposal-finalize-action @schema-v3.1 @v3.1 @proposal @refine @finalize-action @partition
  Scenario Outline: Finalize round-trip preserves the 3.1.1 proposal shape - <case>
    Given a proposal-scoped refine entry with proposal_id "prop_q2_outdoor" and action "finalize"
    And a get_products response proposal "prop_q2_outdoor" with proposal_status <proposal_status>, expires_at <expires_at>, and insertion_order io_id <io_id>
    When the seller serializes the get_products request and response
    Then the serialized refine entry should be {"scope": "proposal", "proposal_id": "prop_q2_outdoor", "action": "finalize"}
    And the serialized proposal's proposal_status should be <proposal_status>
    And the serialized proposal's expires_at should be <expires_at>
    And the serialized proposal's insertion_order io_id should be <io_id>
    And the serialized proposal should be schema-valid against "proposal.json"
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/schemas/source/core/proposal.json
    #   required=[proposal_id,name,allocations]; proposal_status, expires_at, insertion_order ALL optional
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/schemas/source/enums/proposal-status.json
    #   enum=[draft,committed]; absent means "ready to buy" (pre-3.1 back-compat)
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/schemas/source/media-buy/get-products-request.json
    #   refine[].oneOf[2] scope=proposal: required=[scope,proposal_id], action enum=[include,omit,finalize] default=include

    Examples: proposal lifecycle shape partition
      | case                            | proposal_status | expires_at             | io_id       |
      | draft, no hold yet              | "draft"         | absent                 | absent      |
      | committed with hold and IO      | "committed"     | "2026-08-01T00:00:00Z" | "io_q2_001" |
      | committed with hold, no IO      | "committed"     | "2026-08-01T00:00:00Z" | absent      |
      | status absent (pre-3.1 compat)  | absent          | absent                 | absent      |
```

**Why each row earns its place** (this is the specificity the exercise is asking for):

- **row 1** — locks that `draft` survives round-trip and that the schema does *not* force a hold
  window onto a draft.
- **row 2** — the full committed shape the storyboard prose describes, as a *shape* claim rather
  than a transition claim.
- **row 3** — the row that encodes conflict 2: a committed proposal with **no** IO is conformant.
  Directly refutes the original scenario's IO expectation.
- **row 4** — encodes the schema's back-compat clause ("When absent, the proposal is ready to buy"),
  and locks that `exclude_none` serialization omits the key rather than emitting `null`.

**Deliberately excluded (would be red or vacuous):**

- Any Then about a *transition* from draft to committed — production has no proposal store.
- Any Then about firm vs indicative pricing — no field exists to compare.
- The `may carry` phrasing — replaced by an explicit `io_id` column with `absent` as a comparable value.

**Transport independence:** the scenario never dispatches through MCP/A2A/REST. It exercises the
shared production schema layer that all four transports serialize through, so the logic is identical
by construction — no transport branching, and nothing for a transport-parity gap to skew.

**Execution evidence** (all four rows, run against the worktree):

```
REQ refine dump: [{"scope": "proposal", "proposal_id": "prop_q2_outdoor", "action": "finalize"}]
row status='draft'     exp=None                   io=None        -> status='draft'     expires_at=None                   io_id=None        SCHEMA-VALID
row status='committed' exp='2026-08-01T00:00:00Z' io='io_q2_001' -> status='committed' expires_at='2026-08-01T00:00:00Z' io_id='io_q2_001' SCHEMA-VALID
row status='committed' exp='2026-08-01T00:00:00Z' io=None        -> status='committed' expires_at='2026-08-01T00:00:00Z' io_id=None        SCHEMA-VALID
row status=None        exp=None                   io=None        -> status=None        expires_at=None                   io_id=None        SCHEMA-VALID
```

Supporting probes, also green: our `GetProductsRequest` accepts `action` ∈ {include, omit, finalize},
defaults an omitted `action` to `include`, and rejects a bogus action, a missing `proposal_id`, and an
empty-string `proposal_id`. `GetProductsResponse` rejects `proposal_status: "approved"`.

---

## 6. Step inventory

**Existing steps reused: none.** `BR-UC-001-discover-available-inventory.feature` is entirely
dormant — no `tests/bdd/test_uc001*.py` binder exists (every other feature file has one, e.g.
`test_uc019_query_media_buys.py:16`), and greps for the current scenario's phrasings across
`tests/bdd/steps/` return nothing. The same is true of its neighbours
(`a collection_distribution entry uses identifier type …`, `a get_products response references a
product sold by a different seller …`) — none are implemented.

The closest existing precedent to copy from is
`tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101`,
`@then("the response should be schema-valid against list-creative-formats-response.json")`, which
wraps `tests/helpers/pinned_schema.py::validate_against_pinned_schema`. My last Then generalizes that
to a parameterized filename.

**New steps required (5):**

| Kind | Phrasing | Implementation note |
|---|---|---|
| Given | `a proposal-scoped refine entry with proposal_id "{proposal_id}" and action "{action}"` | Build `GetProductsRequest(buying_mode="refine", refine=[…])`; store on ctx. |
| Given | `a get_products response proposal "{proposal_id}" with proposal_status {status}, expires_at {expires_at}, and insertion_order io_id {io_id}` | `absent` sentinel → omit key. Build `GetProductsResponse` with one `allocations` entry (`minItems: 1`) and `requires_signature: true` when an IO is present. |
| When | `the seller serializes the get_products request and response` | `model_dump(exclude_none=True, mode="json")` on both; store both dicts. |
| Then | `the serialized refine entry should be {json}` | Exact dict equality against the parsed JSON literal. |
| Then | `the serialized proposal's {field} should be {value}` | One parameterized step covering `proposal_status`, `expires_at`, and `insertion_order io_id`; `absent` → assert the key is missing. Single step, three bindings — keeps `test_architecture_bdd_no_duplicate_steps.py` happy. |
| Then | `the serialized proposal should be schema-valid against "{filename}"` | Delegate to `validate_against_pinned_schema`. Worth hoisting into `tests/bdd/steps/generic/then_payload.py` and retrofitting `uc005_format_id_roundtrip.py:101` onto it (DRY). |

Every Then compares a concrete value or an explicit absence — none is a truthiness or existence
check, so `test_architecture_bdd_no_trivial_assertions.py` and `..._no_pass_steps.py` are satisfied.

---

## 7. TICKET MATERIAL

Each of these is file-ready as written.

- **`BR-UC-001-discover-available-inventory.feature` is dormant — no scenario in it executes.**
  Every other feature file is bound by a `scenarios()` call (`tests/bdd/test_uc019_query_media_buys.py:16`,
  `tests/bdd/test_uc005_discover_creative_formats.py:14`, …); there is no `tests/bdd/test_uc001*.py`.
  Consequently none of the ~40 UC-001 scenarios' steps exist in `tests/bdd/steps/`, and "green" for
  anything in this file is currently vacuous. This is the dormant-scenario anti-pattern at
  whole-file scale. Fix: add the binder, then implement steps use-case by use-case — bind and
  implement together, or the file silently re-enters dormancy.
  *Mandate:* `docs/test-obligations/bdd-traceability.yaml:746-751` claims traceability for scenarios
  that cannot run.

- **`get_adcp_capabilities` cannot declare `media_buy.supports_proposals`.**
  `src/core/tools/capabilities.py:248-252` builds `MediaBuy(portfolio=…, features=…, execution=…)`;
  the flag is never set. The 3.1.1 capabilities schema places `supports_proposals` as a direct child
  of `media_buy` (`static/schemas/source/protocol/get-adcp-capabilities-response.json:209`,
  `"default": false`), *not* inside `features` — and the SDK's `MediaBuyFeatures` (adcp 6.6.0) has
  only `inline_creative_management`, `property_list_filtering`, `catalog_management`,
  `committed_metrics_supported`. Decide and record: leave it false (correct today — we have no
  proposal support) or implement proposals and flip it. Either way the decision belongs in a comment
  next to the existing `catalog_management=False` / `property_list_filtering` rationale block
  (`capabilities.py:170-190`), which is the established pattern for honest capability declaration.
  *Mandate:* `get-adcp-capabilities-response.json:209`.

- **Production has no proposal lifecycle at all.**
  `grep -rn "proposals\|proposal_status\|PROPOSAL_NOT_FOUND" src/` → zero hits.
  `src/core/tools/products.py` never reads `req.refine`. The request model accepts the `refine` array
  (inherited from the library at `src/core/schemas/product.py:231`) and then silently discards it —
  a quiet failure, which `.claude/rules/patterns/code-patterns.md` § "No Quiet Failures" prohibits.
  Minimum honest behaviour: reject `buying_mode: "refine"` with a typed `AdCPError` rather than
  returning a products list that ignores the buyer's refinement. Full behaviour: implement the
  lifecycle per `protocols/media-buy/scenarios/proposal_finalize.yaml`.
  *Mandate:* `get-products-request.json` `refine` — *"The seller responds to each entry via
  refinement_applied in the response, matched by position."* We emit no `refinement_applied`.

- **Finalize-exclusivity is not enforced.**
  Verified: `GetProductsRequest.model_validate` **accepts** a `refine` array mixing
  `{scope: proposal, action: finalize}` with `{scope: request, ask: …}`. 3.1.1 requires rejection:
  *"if any entry has `action: 'finalize'`, ALL entries in the array MUST be proposal-scoped with
  `action: 'finalize'` … MUST be rejected by the seller with `INVALID_REQUEST`"*
  (`get-products-request.json`, `refine` description). Graded at
  `refine_finalize_exclusivity.yaml:204-212` (`error_code: INVALID_REQUEST` + `errors[0].field`).
  Blocked behind the proposal-support ticket above, but the *validator* is independently
  implementable today as a `model_validator` on `GetProductsRequest`.

- **`MULTI_FINALIZE_UNSUPPORTED` is not in our error catalog.**
  3.1.1 makes it the preferred rejection for sellers that cannot guarantee atomic pre-commit
  validation across a multi-finalize array, with `INVALID_REQUEST` as the pre-3.1 fallback
  (`get-products-request.json` `refine` description; graded at
  `refine_finalize_exclusivity.yaml:390-403`). Feeds the existing error-code reconciliation epic.

- **`tests/fixtures/adcp_schemas_pinned/` is vendored at 04f59d2d5, not 3.1.1.**
  Known gap. Scoped evidence for this scenario: `core/proposal.json` and
  `enums/proposal-status.json` differ from v3.1.1 in **description prose only** — `required`,
  `properties`, `enum`, and `format` are byte-identical, so the assertions proposed in §5 are
  faithful to 3.1.1. But `media-buy/get-products-request.json` differs **structurally**: v3.1.1 adds
  a top-level `allOf` conditional (*"Conditional wholesale feed version requests are only valid for
  wholesale product feed reads"* — if `if_wholesale_feed_version` or `if_pricing_version` is present
  then `buying_mode` must be `"wholesale"`) that the vendored copy lacks entirely, and the vendored
  `refine` description is missing the whole finalize-exclusivity and multi-finalize-atomicity
  contract. Any request-level schema assertion against the pinned tree is therefore weaker than
  3.1.1. Re-vendor via `tests/fixtures/adcp_schemas_pinned/_refresh.py` at v3.1.1 (`467fd93d7`).

- **`then_response_schema_valid` runs no validator** despite
  `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing. Known gap; the new Then
  in §6 should route through the real validator, and the existing no-op should be fixed rather than
  worked around.

- **Sibling scenario `@T-UC-001-storyboard-finalize-uses-refine-vocabulary` overstates the schema.**
  Not mine to rewrite, but it is wrong in a way worth filing: its Then reads *"the entry should be
  accepted as valid (ask is ignored for finalize action)"*. At 3.1.1 the `ask` description says
  *"Ignored when action is `'omit'`"* — it says nothing about `finalize`. The scenario's own comment
  block claims this "mirrors the existing INV-10 pattern for omit action", which is precisely the
  conflation. Also, "should be accepted as valid" is a bare truthiness Then. Verified green fact it
  *could* assert instead: our model accepts `{scope, proposal_id, action: finalize, ask}` and
  preserves both `action` and `ask` on round-trip.

---

## 8. Risks

- **"Green" is currently unfalsifiable for this file.** With no `scenarios()` binder, my proposed
  scenario would not run either — it cannot go red, but it also cannot go green in any meaningful
  sense. I verified all four Examples rows by executing the underlying model and validator calls
  directly (§5), which is the strongest evidence available without the binder. If the baseline PR
  adds the binder, the five new steps in §6 must land in the same PR or the file goes red at once.

- **`#TBD-repin` placeholder.** The proposed Gherkin cites `#TBD-repin`. Per the comment convention
  (GitHub issue numbers, never beads ids) this must be replaced with the real issue number filed out
  of §7 before the scenario lands. I had no issue number to use.

- **`domains/` vs `protocols/` duplication.** `proposal_finalize.yaml` is byte-identical under both
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/` and `dist/compliance/3.1.1/domains/media-buy/scenarios/`.
  I cited `protocols/` because that is where the source tree
  (`static/compliance/source/protocols/…`) lives at v3.1.1 and it matches the existing footer
  convention. If the repo standardizes on `domains/`, the path in the footer needs a mechanical swap
  — the line numbers are the same either way.

- **Round-trip fidelity vs seller behaviour.** The proposed scenario grades that our serialization
  layer preserves proposal lifecycle fields, not that our seller *produces* them. That is the only
  honest green claim available, but a reader skimming the tag could mistake it for lifecycle
  coverage. The comment block is written to preclude that reading; keep it if the scenario is edited.

- **Not verified by execution:** that the five new steps in §6 pass the BDD structural guards
  (`test_architecture_bdd_no_trivial_assertions.py`, `..._no_pass_steps.py`,
  `..._no_duplicate_steps.py`, `..._step_text_alignment.py`). I read the guards' intent and designed
  against it, but I wrote no step code — the brief scopes this to a proposal, and the guards run on
  step definitions, which do not exist yet.

- **Drift beyond our pin (noted only).** 3.1.8 and HEAD exist in the spec repo. I read nothing past
  v3.1.1 and made no use of it. The `sales-proposal-mode` deprecation notice says the storyboard is
  removed at 4.0, so this binding has a known expiry.

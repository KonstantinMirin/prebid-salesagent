# Re-pin: `@T-UC-001-storyboard-finalize-uses-refine-vocabulary`

Scenario: `tests/bdd/features/BR-UC-001-discover-available-inventory.feature:1765-1774`
Title: *Finalize action is encoded as a refine entry with action "finalize" (vocabulary lock)*
Cited `@source`: **none** — the scenario has no footer at all.

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** And, independently, **NOT GRADED — prose only**. Both hold; either alone
strips the `@storyboard-v3.1` tag.

1. **Undeclared gate (primary).** Every 3.1.1 storyboard that exercises `action: "finalize"` carries
   `requires_capability: media_buy.supports_proposals == true`, and lives under specialism
   `sales-guaranteed` (or the deprecated `sales-proposal-mode`). We declare
   `specialisms=[sales_non_guaranteed]` and never set `supports_proposals`
   (`src/core/tools/capabilities.py:249-253, 271-273` — `MediaBuy(portfolio=…, features=…, execution=…)`,
   no `supports_proposals` kwarg; schema default is `false`). A conformance runner therefore skips the
   whole proposal lifecycle for us as `capability_unsupported`. It is not on our conformance path.
   `protocols/media-buy/index.yaml:10-24` — the base media-buy `requires_scenarios` list — contains
   `media_buy_seller/refine_products` but **not** `proposal_finalize` and **not**
   `refine_finalize_exclusivity`, confirming finalize is off the universal path.

2. **Prose only (independent).** Even for a seller that *did* declare the gate, no storyboard anywhere in
   3.1.1 grades the claim this scenario makes. The claim — "a refine entry with `scope: proposal` +
   `proposal_id` + `action: finalize` is a well-formed entry" — appears only as **`sample_request`
   fixture shape**. No `validations:` entry anywhere checks it. See §2.

**Tag change:** `@storyboard-v3.1` → `@schema-v3.1`. That is the correct home: the claim is a pure
JSON-schema grammar claim, and the four sibling refine scenarios in this same file
(`:740-770`, the `BR-RULE-086` INV-1/INV-8/INV-10/INV-11 family) already carry `@schema-v3.1` and already
cite `get-products-request.json`. This scenario is the fifth member of that family and was mistagged.
Keep `@T-UC-001-storyboard-finalize-uses-refine-vocabulary` unchanged —
`docs/test-obligations/bdd-traceability.yaml:752-757` references it
(`upstream_refs: ["BR-UC-001-alt-refine", "BR-RULE-086"]` — the traceability file itself already binds this
scenario to **BR-RULE-086**, the refine-grammar rule, not to a storyboard).

---

## 2. Real binding at 3.1.1

### What the current footer points at
Nothing — there is no `@source` footer. The only pointer is a trailing prose line:

```
# proposal_finalize: vocabulary lock -- finalize is expressed via the existing refine grammar
```

The immediately-preceding scenario (`:1747-1764`, owned by another agent) cites
`path=static/compliance/source/protocols/media-buy/scenarios/proposal_finalize.yaml` with the stale
`ref=v3.1-04f59d2d5`. If the off-by-one defect described in the brief were applied here, this scenario
would inherit that same storyboard path. **It should not.** Adding a storyboard `@source` here would be
wrong twice over (undeclared gate + ungraded).

### Where `action: "finalize"` actually appears in 3.1.1 storyboards

Two files, both duplicated byte-identically across the `protocols/` and `domains/` tiers
(`diff -q` → identical), both capability-gated:

**A. `dist/compliance/3.1.1/protocols/media-buy/scenarios/proposal_finalize.yaml`**
Gate, lines 11-13:
```yaml
requires_capability:
  path: media_buy.supports_proposals
  equals: true
```
The finalize step is `finalize_proposal` / `get_products_finalize`, lines 211-258. Its `sample_request`
carries the entry (lines 238-247), but its **graded block is lines 253-258, verbatim**:
```yaml
        validations:
          - check: response_schema
            description: "Response matches get-products-response.json schema"
          - check: field_present
            path: "proposals"
            description: "Response contains the finalized proposal"
```
That is all. `proposal_status: committed`, `expires_at`, firm-vs-indicative pricing and the `insertion_order`
appear **only** under `expected:` (lines 231-236) — narrative prose, ungraded.

**B. `dist/compliance/3.1.1/protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml`**
Same gate at lines 10-13. This file *does* grade finalize behaviour — but the negative direction only:
- `mixed_finalize_rejected`, validations lines 204-212:
```yaml
        validations:
          - id: mixed_finalize.error_code
            check: error_code
            value: "INVALID_REQUEST"
            description: "Mixed finalize + non-finalize refine[] rejected with INVALID_REQUEST"
          - id: mixed_finalize.error_field_present
            check: field_present
            path: "errors[0].field"
            description: "Seller populates error.field pointing at the offending refine entry"
```
- `non_proposal_finalize_rejected`, validations lines 252-256:
```yaml
        validations:
          - id: product_finalize.error_code
            check: error_code
            value: "INVALID_REQUEST"
            description: "Product-scoped finalize entry rejected with INVALID_REQUEST"
```
- multi-finalize branch set, lines 299-340 and 390-394 (`MULTI_FINALIZE_UNSUPPORTED` / `INVALID_REQUEST`).

Note `refine_finalize_exclusivity` appears in **no** `requires_scenarios:` list anywhere in
`dist/compliance/3.1.1/` — it is an orphan scenario file, not required by any specialism or protocol index.

**Nowhere** — in either file, in either tier — is there a `validations:` entry asserting that a
proposal-scoped `action: "finalize"` entry is *accepted*. The positive vocabulary claim is ungraded.

### The real binding

The authoritative source for this scenario is the **JSON schema**, tier-independent, gate-independent:

`static/schemas/source/media-buy/get-products-request.json` @ `v3.1.1` (`467fd93d7`),
`properties.refine.items.oneOf[2]` — the proposal variant, **lines 116-149**.

---

## 3. Schema constraints at 3.1.1 — verbatim

`git show v3.1.1:static/schemas/source/media-buy/get-products-request.json`

**Lines 116-149 — the proposal-scoped refine variant (the vocabulary lock itself):**
```json
          {
            "properties": {
              "scope": {
                "type": "string",
                "const": "proposal",
                "description": "Change scoped to a specific proposal."
              },
              "proposal_id": {
                "type": "string",
                "minLength": 1,
                "description": "Proposal ID from a previous get_products response."
              },
              "action": {
                "type": "string",
                "enum": [
                  "include",
                  "omit",
                  "finalize"
                ],
                "default": "include",
                "description": "'include' (default): … 'finalize': request firm pricing and inventory hold — transitions a draft proposal to committed with an expires_at hold window. May trigger seller-side approval (HITL). The buyer should not set a time_budget for finalize requests … Optional — when omitted, the seller treats the entry as action: 'include'."
              },
              "ask": {
                "type": "string",
                "minLength": 1,
                "description": "What the buyer is asking for on this proposal (e.g., 'shift more budget toward video', 'reduce total by 10%'). Ignored when action is 'omit'."
              }
            },
            "required": [
              "scope",
              "proposal_id"
            ],
            "additionalProperties": false
          }
```

**Line 53-56 — array level:** `"refine": { "type": "array", … "minItems": 1, "items": { "type": "object",
"discriminator": { "propertyName": "scope" }, "oneOf": [ … ] } }`

**Lines 53 (description) — the finalize-exclusivity rule, verbatim excerpt:**
> "Finalize-exclusivity rule: if any entry has `action: 'finalize'`, ALL entries in the array MUST be
> proposal-scoped with `action: 'finalize'` — mixing finalize entries with `include`/`omit` entries or with
> request- / product-scoped entries MUST be rejected by the seller with `INVALID_REQUEST`."

and

> "Sellers that cannot guarantee atomic pre-commit validation MUST reject multi-finalize arrays with
> `MULTI_FINALIZE_UNSUPPORTED` (preferred …) or `INVALID_REQUEST` (acceptable fallback …)."

**Product variant, lines ~82-114:** `action` enum is `["include", "omit", "more_like_this"]`,
`additionalProperties: false` — so `finalize` on product scope is *structurally* invalid, and
`more_like_this` on proposal scope is likewise structurally invalid. That asymmetry is the lock.

**Request variant, lines ~58-80:** `required: ["scope", "ask"]`, no `action` property at all,
`additionalProperties: false`.

**`buying_mode` enum, lines 40-48:** `["brief", "wholesale", "refine"]`; and `brief` (lines 50-52):
> "Must not be provided when `buying_mode` is 'wholesale' or 'refine'."

**Capability gate — `static/schemas/source/protocol/get-adcp-capabilities-response.json:209`
(`properties.media_buy.properties.supports_proposals`):**
```json
        "supports_proposals": {
          "type": "boolean",
          "description": "Conformance declaration that this seller supports the full proposal lifecycle on get_products: returned proposals are actionable, draft proposals can be finalized with buying_mode: 'refine' + action: 'finalize' … A declaration of true opts the seller into proposal-lifecycle grading. When false or absent, conformance runners skip proposal-lifecycle storyboards …",
          "default": false
        }
```

**`static/schemas/source/enums/specialism.json:53`** confirms the routing:
> "`sales-proposal-mode`: DEPRECATED in 3.1 … The `media_buy_seller/proposal_finalize` scenario lives under
> `sales-guaranteed.requires_scenarios` and is capability-gated on `media_buy.supports_proposals`: …
> direct-buy guaranteed sellers … declare `false` and the runner skips it as `capability_unsupported`."

---

## 4. Conflicts

### 4a. Schema overrides storyboard
The storyboards treat finalize as a *lifecycle* behaviour and grade almost none of it; the schema is where
the finalize vocabulary is actually normative. **The 3.1.1 schema wins** — this scenario binds to
`get-products-request.json`, not to `proposal_finalize.yaml`. Where `proposal_finalize.yaml`'s `expected:`
prose (lines 231-236) promises `proposal_status: committed` / `expires_at` / firm pricing, the schema is
what a runner can actually check, and the storyboard chose not to check it. Prose loses.

### 4b. The scenario's central assertion is factually wrong
```gherkin
Then the entry should be accepted as valid (ask is ignored for finalize action)
```
and the supporting comment:
```
# scope=proposal, the captured proposal_id, and action=finalize; ask is ignored
# for the finalize action (mirrors the existing INV-10 pattern for omit action).
```

The 3.1.1 schema says **`ask` is ignored when action is `'omit'`** (line 141), full stop. It says nothing
about `ask` under `finalize`. The scenario generalised the `omit` rule to `finalize` — that generalisation
is not in the schema and is not in any storyboard. Per the source hierarchy: **schema silent → production
authoritative → do not assert it.** I removed the claim rather than inventing a grade for it.

Production confirms: `ask` alongside `finalize` is **accepted and retained**, not dropped —
`Refine3(scope='proposal', proposal_id='p', action=Action2.finalize, ask='shift budget')`.
So the original Then is not merely unsourced, it asserts the opposite of observable behaviour.

### 4c. Vacuous / non-comparing assertions
Both `When the system validates the refine entry` and
`Then the entry should be accepted as valid (…)` are unimplemented — **there are no step definitions
for them anywhere** (`grep -rn "refine entry" tests/ --include="*.py"` → zero hits). More broadly:

**`BR-UC-001-discover-available-inventory.feature` has no `scenarios()` binding at all.** No file under
`tests/bdd/` references it (`grep -rn "BR-UC-001-discover" tests/ | grep -v .feature` → zero hits), while
every other feature has one (`tests/bdd/test_uc002_create_media_buy.py:14`, `…test_uc018_list_creatives.py:83`,
etc.). The **entire UC-001 feature file is dormant** — nothing in it executes. That is the dominant fact
about this scenario and it applies equally to its four `BR-RULE-086` siblings.

Consequence: "GREEN ONLY" here cannot mean "I ran it". It means every row below was verified by executing
production validation directly against `src.core.schemas.GetProductsRequest` (matrix in §7 evidence).

### 4d. What the scenario misses
- A single `Scenario` proving one positive case is the weakest possible form of a *vocabulary lock*. The
  lock is the **asymmetry** between the three scope variants' `action` enums. That needs a table.
- No coverage that `finalize` is *rejected* on `product`/`request` scope — which is precisely what makes
  `finalize` "proposal vocabulary" rather than generic refine vocabulary.
- No coverage that `proposal_id` is required (`minLength: 1`) for a finalize entry.
- No coverage of the default (`action` absent → `include`), which is the boundary the finalize value sits next to.

---

## 5. Proposed Gherkin — complete replacement for lines 1765-1774

GREEN-only. Every row below was executed against production (`GetProductsRequest.model_validate`) —
results in §7. Transport-independent by construction: all four transports (MCP / A2A / REST / e2e_rest)
build the *same* `src.core.schemas.GetProductsRequest`, so the request contract is a single shared surface;
there is no transport branching in the Gherkin and none is needed in the steps.

```gherkin
  @T-UC-001-storyboard-finalize-uses-refine-vocabulary @schema-v3.1 @v3.1 @proposal @refine @finalize-action @partition
  Scenario Outline: Finalize lives in the refine grammar - scope "<scope>" with action "<action>"
    Given a get_products request with buying_mode "refine" and one refine entry with scope "<scope>", id "<entry_id>", action "<action>", and ask "<ask>"
    When the get_products request is validated against the AdCP request contract
    Then the refine entry should resolve to effective action "<effective_action>"

    # Vocabulary lock: the protocol expresses proposal finalization through the existing
    # refine grammar rather than a separate finalize endpoint. The lock IS the asymmetry
    # between the three scope variants' action enums:
    #   request  -> no `action` property at all (additionalProperties: false)
    #   product  -> include | omit | more_like_this
    #   proposal -> include | omit | finalize
    # so `finalize` is proposal vocabulary and nothing else, and `more_like_this` is
    # product vocabulary and nothing else. Both directions are graded below.
    #
    # `(absent)` = key omitted from the entry. `(empty)` = key present with "".
    # `rejected` = the request contract refuses the entry.
    #
    # Row 2 (finalize + ask) is ACCEPTED and the ask is RETAINED. AdCP 3.1.1 states
    # "Ignored when action is 'omit'" only (get-products-request.json:141); it is SILENT
    # on ask-under-finalize, so no ignore-semantics claim is asserted here. See #TBD.
    #
    # Not asserted here because production does not enforce it (see #TBD):
    # the array-level finalize-exclusivity rule and multi-finalize atomicity contract.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/schemas/source/media-buy/get-products-request.json lines=116-149 (properties.refine.items.oneOf[2], proposal variant)

    Examples: Proposal scope owns "finalize"
      | scope    | entry_id | action         | ask          | effective_action |
      | proposal | prop-1   | finalize       | (absent)     | finalize         |
      | proposal | prop-1   | finalize       | shift budget | finalize         |
      | proposal | prop-1   | include        | (absent)     | include          |
      | proposal | prop-1   | omit           | (absent)     | omit             |
      | proposal | prop-1   | (absent)       | (absent)     | include          |
      | proposal | prop-1   | more_like_this | (absent)     | rejected         |

    Examples: proposal_id is required for a finalize entry
      | scope    | entry_id | action         | ask          | effective_action |
      | proposal | (absent) | finalize       | (absent)     | rejected         |
      | proposal | (empty)  | finalize       | (absent)     | rejected         |

    Examples: No other scope accepts "finalize"
      | scope    | entry_id | action         | ask          | effective_action |
      | product  | prod-1   | finalize       | (absent)     | rejected         |
      | product  | prod-1   | more_like_this | (absent)     | more_like_this   |
      | product  | prod-1   | omit           | (absent)     | omit             |
      | request  | (absent) | finalize       | more CTV     | rejected         |
```

Design notes:
- Single `Then`, one exact string comparison per row (`effective_action`), never truthiness or existence —
  satisfies `test_architecture_bdd_no_trivial_assertions.py` and `..._no_pass_steps.py`.
- `rejected` is a first-class value in the same column as the accepted actions, so accepted and rejected
  rows are graded by the identical comparison. No sentinel branching in the step body, no dict
  intermediary (`test_architecture_bdd_no_dict_registry.py`).
- The scenario title drops the word "storyboard"; the opaque `@T-…` id is unchanged for
  `bdd-traceability.yaml:752`.
- `#TBD` placeholders are for the GitHub issues filed from §7 — substitute real `#NNNN` before landing.
  Per repo policy these must be GitHub numbers, never beads ids.

---

## 6. Step inventory

**Existing steps reused: none.** No step in `tests/bdd/steps/` matches any phrasing in this scenario or in
its four `BR-RULE-086` siblings. Searched: `grep -rn "refine entry\|validates the refine" tests/ --include="*.py"`
(zero hits) and the full `@then(` inventory in `tests/bdd/steps/generic/*.py` (`then_error.py`,
`then_payload.py`, `then_success.py`, `then_media_buy.py`) — the closest existing phrasings are
`@then("no error should be raised")` (`then_error.py:631`) and
`@then("the response should indicate a validation error")` (`then_error.py:652`), both of which are
existence/truthiness-shaped and would themselves trip the trivial-assertion guard if reused here.

**New steps required (3), all in one new module `tests/bdd/steps/domain/uc001_refine_grammar.py`:**

| # | Kind | Phrasing |
|---|------|----------|
| 1 | `@given(parsers.parse(...))` | `a get_products request with buying_mode "refine" and one refine entry with scope "{scope}", id "{entry_id}", action "{action}", and ask "{ask}"` |
| 2 | `@when` | `the get_products request is validated against the AdCP request contract` |
| 3 | `@then(parsers.parse(...))` | `the refine entry should resolve to effective action "{effective_action}"` |

**DRY — these three steps subsume the four dormant siblings.** Lines 741, 749, 758, 766 of the same feature
(`BR-RULE-086` INV-1 / INV-8 / INV-10 / INV-11) are the same operation with different parameters and today
have four distinct hand-written Given phrasings and three distinct Then phrasings, none implemented. Under
the CLAUDE.md DRY invariant they must **not** get their own step functions
(`test_architecture_bdd_no_duplicate_steps.py` bans 3+ identical bodies). Recommendation: fold all five
scenarios onto this one step family in the same PR that wires them. Concretely, siblings map as:
INV-1 → `| request | (absent) | (absent) | more video options | request-scoped |`;
INV-8 → the `proposal / more_like_this / rejected` row already present above;
INV-10 → `| product | prod-123 | omit | not relevant | omit |`;
INV-11 → `| product | prod-123 | (absent) | (absent) | include |`.
(That fold is out of scope for this baseline PR — flagged, not done.)

**Wiring blocker:** even with the steps written, nothing runs until
`scenarios("features/BR-UC-001-discover-available-inventory.feature")` exists. See §7.

---

## 7. TICKET MATERIAL

Evidence matrix — production validation results, all executed against
`src.core.schemas.GetProductsRequest.model_validate({"buying_mode": "refine", "refine": [entry]})`:

| entry | production | matches 3.1.1 schema? |
|---|---|---|
| `proposal` + `finalize` | ACCEPT, `action=finalize` | yes |
| `proposal` + `finalize` + `ask` | ACCEPT, `ask` retained | yes (schema silent on ignore) |
| `proposal` + `include` / `omit` | ACCEPT | yes |
| `proposal`, no `action` | ACCEPT, defaults `include` | yes |
| `proposal` + `more_like_this` | REJECT | yes |
| `proposal` + `finalize`, `proposal_id` absent | REJECT | yes |
| `proposal` + `finalize`, `proposal_id: ""` | REJECT | yes (`minLength: 1`) |
| `product` + `finalize` | REJECT | yes |
| `request` + `action` | REJECT | yes |
| `refine: []` | REJECT | yes (`minItems: 1`) |
| **mixed finalize + request-scoped entry** | **ACCEPT** | **NO** |
| **mixed finalize + proposal-`include` entry** | **ACCEPT** | **NO** |
| **two finalize entries (multi-finalize)** | **ACCEPT** | **NO** |
| **`brief` set with `buying_mode: "refine"`** | **ACCEPT** | **NO** |

---

- **UC-001 feature file is entirely dormant — no `scenarios()` binding.**
  `tests/bdd/features/BR-UC-001-discover-available-inventory.feature` (2000+ lines, ~40 scenarios) is
  referenced by no test module: `grep -rn "BR-UC-001-discover" tests/ | grep -v '\.feature'` returns
  nothing, while every sibling feature has one (`tests/bdd/test_uc002_create_media_buy.py:14`,
  `tests/bdd/test_uc018_list_creatives.py:83`, `tests/bdd/test_uc019_query_media_buys.py:16`, …).
  Nothing in UC-001 has ever executed. Repo convention (`tests/bdd/test_uc018_list_creatives.py:81-83`)
  notes the `scenarios()` binding is what the CI shard-splitter requires, so an unbound feature is
  invisible to CI as well as to pytest. **Fix:** add `tests/bdd/test_uc001_discover_inventory.py` with
  `scenarios("features/BR-UC-001-discover-available-inventory.feature")` — but only once step definitions
  exist for the scenarios it contains, or collection fails wholesale. This ticket gates every other UC-001
  ticket.

- **No step definitions exist for the refine-grammar scenario family.**
  Five scenarios (`…feature:741, 749, 758, 766, 1766`) use Given/When/Then phrasings with zero matching
  `@given`/`@when`/`@then` in `tests/bdd/steps/`. **Fix:** implement the three-step family in §6 as
  `tests/bdd/steps/domain/uc001_refine_grammar.py` and fold all five scenarios onto it (DRY —
  `test_architecture_bdd_no_duplicate_steps.py`). Mandated by
  `static/schemas/source/media-buy/get-products-request.json:53-149` @ v3.1.1.

- **Production does not enforce the finalize-exclusivity rule.**
  `GetProductsRequest` accepts `refine: [{scope: proposal, proposal_id: p1, action: finalize},
  {scope: request, ask: "more CTV"}]` — each entry is individually schema-valid and nothing checks the
  array-level constraint. 3.1.1 `get-products-request.json:53` (`properties.refine.description`) is
  explicit: *"if any entry has `action: 'finalize'`, ALL entries in the array MUST be proposal-scoped with
  `action: 'finalize'` — mixing finalize entries with `include`/`omit` entries or with request- /
  product-scoped entries MUST be rejected by the seller with `INVALID_REQUEST`."* Graded upstream at
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml:204-212`
  (`check: error_code`, `value: "INVALID_REQUEST"`, plus `field_present: errors[0].field`).
  **Fix:** add an array-level `model_validator` on `src/core/schemas/product.py::GetProductsRequest`
  raising `INVALID_REQUEST` with `field` naming the offending entry index. Note this is only reachable
  once we declare `media_buy.supports_proposals`; file it, sequence it behind the capability decision.

- **Production does not enforce multi-finalize atomicity or emit `MULTI_FINALIZE_UNSUPPORTED`.**
  Two proposal-scoped finalize entries in one array are accepted with no atomicity guarantee and no
  rejection. 3.1.1 `get-products-request.json:53`: *"Sellers that cannot guarantee atomic pre-commit
  validation MUST reject multi-finalize arrays with `MULTI_FINALIZE_UNSUPPORTED` (preferred …) or
  `INVALID_REQUEST`."* Graded at `refine_finalize_exclusivity.yaml:390-394`
  (`check: error_code`, `allowed_values: ["MULTI_FINALIZE_UNSUPPORTED", "INVALID_REQUEST"]`).
  The code exists in the SDK catalog (`ErrorCode.MULTI_FINALIZE_UNSUPPORTED`) and is never emitted by us
  — consistent with the known three-layer error-code drift. Same sequencing note as above.

- **`brief` is accepted alongside `buying_mode: "refine"`.**
  `GetProductsRequest.model_validate({"buying_mode": "refine", "brief": "x", "refine": [...]})` succeeds.
  3.1.1 `get-products-request.json:50-52` (`properties.brief.description`): *"Must not be provided when
  `buying_mode` is 'wholesale' or 'refine'."* Not proposal-gated — this is on the base media-buy path
  (`buying_mode: "refine"` is required for `media_buy_seller/refine_products`, which
  `protocols/media-buy/index.yaml:11` **does** require of us). **Fix:** cross-field validator on
  `GetProductsRequest`. Discovered incidentally while probing the refine grammar; unrelated to the
  proposal gate, and the highest-value item in this list because it *is* on our conformance path.

- **We do not declare `media_buy.supports_proposals`, and there is no product decision recorded either way.**
  `src/core/tools/capabilities.py:249-253` builds `MediaBuy(portfolio=…, features=…, execution=…)`;
  `supports_proposals` defaults to `false`
  (`static/schemas/source/protocol/get-adcp-capabilities-response.json:209`). There is no proposal engine
  in `src/` at all (`grep -rn "proposal" --include="*.py" src/core/` → no proposal-lifecycle code).
  Declaring `false` is currently **honest** and this is not a bug. But the repo has no note recording that
  choice, and `capabilities.py:256-265` documents the reasoning for the `sales_non_guaranteed` specialism
  declaration in detail while saying nothing about proposals. **Fix:** either add the explicit
  `supports_proposals=False` kwarg with a comment (mirroring the `catalog_management=False` rationale at
  `capabilities.py:176-183`), or open a decision ticket on whether the proposal lifecycle is in scope.
  Until it is declared true, every proposal storyboard grades `capability_unsupported` and all of the
  above finalize tickets are off our conformance path.

- **No scenario grades ask-under-finalize semantics — upstream gap, file against `adcontextprotocol/adcp`.**
  3.1.1 `get-products-request.json:141` says `ask` is *"Ignored when action is 'omit'"* and is silent on
  `finalize`. Our production retains it. A buyer sending `{action: finalize, ask: "…"}` has no defined
  answer to "was my ask applied before the commit?" — which matters, because finalize is a commit.
  Not a salesagent bug; an upstream spec ambiguity worth raising.

---

## 8. Risks

- **Nothing was verified by test execution.** UC-001 is dormant and unbindable today (no steps), so I could
  not run the scenario in any form. Greenness was established by executing production validation directly
  against `src.core.schemas.GetProductsRequest` — the same model every transport constructs — for all
  twelve proposed rows plus the negative probes. That is stronger than reading `src/`, but weaker than a
  pytest run. If the proposal is accepted, the wiring PR should re-verify the table before landing.
- **Extra-field mode is environment-dependent.** `GetProductsRequest.model_config` uses
  `get_pydantic_extra_mode()` (`src/core/schemas/product.py:236`) — `forbid` in dev/CI, `ignore` under
  `ENVIRONMENT=production` (CLAUDE.md Pattern #7). My probes ran in dev mode. I deliberately included **no**
  row that depends on `additionalProperties: false` (e.g. an unknown key on the entry) for exactly this
  reason; the twelve rows above all turn on `oneOf` discrimination, enum membership, `required`, or
  `minLength`, none of which vary with extra mode. Worth confirming during wiring.
- **Transport-independence is argued, not demonstrated.** The claim rests on all four transports building
  the same request model. I read the boundary contract in CLAUDE.md Pattern #5 rather than tracing each
  wrapper. If any transport pre-validates or reshapes `refine` before model construction, rows could
  diverge — that would itself be a Pattern #5 violation and worth its own ticket, but I did not check.
- **`refine_finalize_exclusivity.yaml` is an orphan.** It is required by no `requires_scenarios:` list in
  `dist/compliance/3.1.1/`. I treated it as informative for spec intent (it quotes the same normative
  clauses as the schema) but did not treat it as a grading authority. If the compliance runner discovers
  scenario files by directory scan rather than by index, that judgment is wrong and the two exclusivity
  tickets rise in priority.
- **`domains/` vs `protocols/` tiers are byte-identical** for these files (`diff -q` confirms). I cited the
  `protocols/` path throughout. If the two tiers are ever allowed to diverge, the citation should be
  re-checked; today the choice is arbitrary.
- **3.1.8 / HEAD drift not investigated**, per the brief. The proposal lifecycle is actively churning
  upstream (issues #3823, #3844, #4107 are all referenced from the 3.1.1 artifacts themselves), so this
  binding is more likely than average to move on the next pin bump. Noted only.

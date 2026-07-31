# Re-pin: `@T-UC-006-storyboard-provenance-disclosure-missing`

Scenario: `tests/bdd/features/BR-UC-006-sync-creatives.feature:1563`
Title: *PROVENANCE_DISCLOSURE_MISSING — provenance present but disclosure block omitted under require_disclosure_metadata*

---

## 1. VERDICT

**GRADED — and correctly bound. But zero production coverage, and the scenario is DORMANT today.**

Three separate findings, all verified:

1. **The behaviour IS storyboard-graded at 3.1.1.** There is a real `validations:` block with a
   `- check: field_value / path: creatives[0].errors[0].code / value: "PROVENANCE_DISCLOSURE_MISSING"`
   entry. This is not narrative prose. The `@storyboard-v3.1` tag is **justified** and must stay.

2. **The `@source` path is CORRECT — this scenario is NOT one of the 16 off-by-one victims.**
   The cited path `static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml`
   exists verbatim at `v3.1.1` and really does contain the disclosure phase. Only defect #1 applies:
   the `ref=v3.1-04f59d2d5 commit=04f59d2d5` pin is stale and must move forward to `v3.1.1` / `467fd93d7`.
   The footer is also missing `phase=` / `step=` anchors, which is what let the off-by-one epidemic go
   undetected elsewhere — add them.

3. **`PROVENANCE_DISCLOSURE_MISSING` is never emitted by production, and never can be today.**
   `grep -rn "PROVENANCE_" src/ --include='*.py'` → **zero hits**. `require_disclosure_metadata` →
   **zero hits in `src/`**. The only provenance gate we implement is `provenance_required`, and it
   produces a *warning string*, not `action: "failed"` with an error code.

Consequence: **no assertion in this scenario can be made green by editing Gherkin.** The scenario is
currently dormant (no matching step definitions → `StepDefinitionNotFoundError` → auto-xfail at
`tests/bdd/conftest.py:99-101`), which is why the baseline is green. My proposal below keeps it
dormant, corrects the binding, and makes the Gherkin storyboard-exact so it grades the right thing the
day the production gap closes. **This scenario contributes zero grading power right now and I am not
pretending otherwise** — see §7 for the two tickets that change that.

---

## 2. Real binding at 3.1.1

### Where it is graded

**File:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml`
**Phase:** `reject_missing_disclosure` — line **365**
**Step:** `sync_creatives_missing_disclosure` — line **376**
**Graded block:** lines **422–436**

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_value
            path: "creatives[0].action"
            value: "failed"
            description: "Per-creative action is failed for the missing-disclosure submission"
          - check: field_value
            path: "creatives[0].errors[0].code"
            value: "PROVENANCE_DISCLOSURE_MISSING"
            description: "Per-creative error code identifies the missing disclosure requirement; buyers can self-correct without negotiating"
          - check: field_value
            path: "context.correlation_id"
            value: "provenance_enforcement--reject_missing_disclosure"
            description: "Context correlation_id returned unchanged on rejection"
```

Four graded checks. Note what is **NOT** graded: the phase `expected:` prose (lines 383–388) promises
`field` pointing at the missing disclosure path and `recovery: correctable`, but **neither appears
under `validations:`**. Per the brief's rule, those are narrative — a scenario asserting them would be
asserting something the storyboard does not grade. I have kept them out of the mainline Gherkin and
recorded them as a documented divergence instead.

### What the current footer points at

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml
```

- `path=` — **correct.** Verified with `git ls-tree -r --name-only v3.1.1 static/compliance/source | grep provenance`:
  the file is present at that exact path at the 3.1.1 tag.
- `ref=v3.1-04f59d2d5 commit=04f59d2d5` — **stale.** That tag is an ancestor of the beta line, older
  than our own pin. Re-pin to `ref=v3.1.1 commit=467fd93d7` (`git rev-parse --short=9 v3.1.1^{commit}`).
- `phase=` / `step=` — **missing.** Add them. Without an anchor there is nothing to mechanically
  diff a footer against, which is exactly how 16 sibling scenarios drifted onto the *next*
  storyboard's file undetected.

### Tier ownership

`protocols/media-buy` — a **protocol**, not a specialism.

- `dist/compliance/3.1.1/index.json` lists `{"id": "media-buy", "title": "Media buy seller agent", "path": "protocols/media-buy/"}`
  under `protocols`, and an identical entry under `domains`. The two trees are **byte-identical**
  (`diff` of the two `provenance_enforcement.yaml` copies → no output); `domains/` is the 3.1.1 alias of
  `protocols/`. Citing `protocols/` matches what exists at `static/compliance/source/`, which is the
  authored tree — keep `protocols/`.
- The 21 entries under `specialisms` contain **no** provenance specialism. Provenance enforcement is
  not capability-gated.

### Do we declare the gate? — YES

`src/core/tools/capabilities.py:271` declares `supported_protocols=[SupportedProtocol.media_buy]`.
That is the tier this storyboard belongs to. **This scenario is on our conformance path**, so the
undeclared-gate escape hatch (downgrade to `@schema-v3.1`) does **not** apply. `@storyboard-v3.1` stays.

One caveat worth naming: the storyboard declares `agent.capabilities: [has_creative_library]`
(line 39-40) and `interaction_model: stateful_push` (line 38). We do not emit any `has_creative_library`
marker in `_get_adcp_capabilities_impl` — but that is an agent-descriptor field, not one of the four
conformance tiers, and the runner gates on specialism/protocol. It does not move the verdict.

---

## 3. Schema constraints at 3.1.1

### `core/creative-policy.json` — the conditional MUST

`git show v3.1.1:static/schemas/source/core/creative-policy.json`:

```json
"provenance_requirements": {
  "type": "object",
  "description": "Structured provenance requirements for creatives. Refines `provenance_required`: when `provenance_required` is true, the fields in this object specify which provenance features the seller requires. When `provenance_required` is false or absent, this object SHOULD be absent; if present, receivers MUST ignore it. Existing seller agents that do not read this object are unaffected; the wire shape does not change for them. Sellers that publish a requirement here MUST enforce it on creative submission: a `sync_creatives` request that omits a required field is rejected with the corresponding `PROVENANCE_*` error code (see error-code.json) ... Field-level requirements are seller-enforced — JSON Schema validation does not check them.",
  "properties": {
    "require_disclosure_metadata": {
      "type": "boolean",
      "description": "When true, the seller requires creatives to include a `disclosure` object in their provenance with `disclosure.required` set to a boolean value (true or false). When `disclosure.required` is true, at least one entry in `disclosure.jurisdictions` is expected. Submissions that omit `disclosure.required` are rejected with `PROVENANCE_DISCLOSURE_MISSING`."
    }
  },
  "additionalProperties": true
}
```

Three load-bearing clauses:

1. **The MUST is conditional on publication.** *"Sellers **that publish a requirement here** MUST
   enforce it."* We publish nothing — no product in `src/services/default_products.py` sets
   `provenance_requirements` (all five products carry only `co_branding`/`landing_page`/`templates_available`).
   So we are **not currently in breach** of the schema. We are simply not participating in the contract.
2. **"Field-level requirements are seller-enforced — JSON Schema validation does not check them."**
   No amount of envelope validation will surface this gap. Only a behavioural test can.
3. The precise trigger is `disclosure.required` being **absent**, not `disclosure` being absent.
   A creative carrying `disclosure: {jurisdictions: [...]}` with no `required` key is *also* a rejection.
   The current Gherkin says "lacks a disclosure block", which is narrower than the schema. Fixed below.

### `core/provenance.json` — what a compliant disclosure block looks like

`disclosure` is an **optional** property (the schema has no top-level `required` array), with
`required: boolean` and `jurisdictions: [{country, region, regulation, label_text, render_guidance}]`.
So the buyer's omission is schema-legal — the rejection is purely policy-driven, which is exactly why
it needs a seller-side check.

### `enums/error-code.json` — the code exists

92 codes at `v3.1.1`, six in the PROVENANCE family:

```
PROVENANCE_REQUIRED, PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING, PROVENANCE_DISCLOSURE_MISSING,
PROVENANCE_EMBEDDED_MISSING, PROVENANCE_VERIFIER_NOT_ACCEPTED, PROVENANCE_CLAIM_CONTRADICTED
```

**Cross-check (not authority):** `adcp==6.6.0`'s `ErrorCode` enum has exactly 92 members and the same
six PROVENANCE codes. Schema and SDK agree here — no drift to reconcile.

### `core/error.json` — the code field is an open string

```json
"code": {
  "type": "string", "minLength": 1, "maxLength": 64,
  "description": "... The error-code vocabulary is open: `error.code` is wire-typed `string` (not a closed enum), the standard codes published in `enums/error-code.json` are documentary, and senders MAY emit codes outside that set ..."
}
```

Relevant to the fix: nothing schema-level blocks us from emitting `PROVENANCE_DISCLOSURE_MISSING`
today. `SyncCreativeResult.errors[]` already takes an arbitrary code string
(`src/core/tools/creatives/_processing.py:34-56`). The gate is missing logic, not a missing type.

### `creative/sync-creatives-response.json` — the per-creative result shape

```json
"required": ["creative_id", "action"],
"allOf": [{
  "if":   { "properties": { "action": { "enum": ["failed", "deleted"] } }, "required": ["action"] },
  "then": { "not": { "required": ["status"] } }
}]
```

So a `failed` result **MUST NOT** carry `status`. `_failed_sync_result` does not set `status` — that
part is already conformant.

The response root also `$ref`s `core/protocol-envelope.json`, which `required: ["status"]` at top
level. That is the known repo-wide gap already listed in the brief; not this scenario's to fix.

---

## 4. Conflicts

**Schema vs storyboard: no conflict.** The storyboard's fixture (`provenance_requirements.require_disclosure_metadata: true`,
`accepted_verifiers[]`) validates cleanly against `core/creative-policy.json` at 3.1.1, and its graded
error code is in the 3.1.1 enum. Nothing to override.

**Storyboard `expected:` vs storyboard `validations:` — a real gap inside the storyboard.**
The phase promises `field` + `recovery: correctable` in prose (lines 386-388) but grades neither.
Per the brief's rule, prose is not graded. I do not assert them.

**What the scenario gets wrong / misses:**

| # | Problem | Evidence |
|---|---------|----------|
| 1 | Stale `@source` ref (`v3.1-04f59d2d5`), older than our own 3.1.1 pin | feature:1580 |
| 2 | `@source` has no `phase=` / `step=` anchor — unverifiable against the storyboard | feature:1580 |
| 3 | **Scenario is dormant.** `When the Buyer Agent sends sync_creatives` matches nothing; the real step is `@when("the Buyer Agent sends a sync_creatives request")` (`tests/bdd/steps/domain/uc006_sync_creatives.py:256`). Neither Given nor the Then exists at all. → `StepDefinitionNotFoundError` → auto-xfail | `tests/bdd/conftest.py:99-101` |
| 4 | Trigger condition is narrower than the schema: says "lacks a disclosure block", schema says the trigger is a missing `disclosure.required` | creative-policy.json |
| 5 | Drops the graded `context.correlation_id` echo entirely | storyboard:433-436 |
| 6 | Drops the graded `response_schema` check — but adding it back would be **vacuous**: `then_response_schema_valid` runs no validator (brief, known gaps). Left out deliberately. | — |
| 7 | Prose comment claims "`error.field` points at the missing disclosure path" — that is ungraded storyboard prose, stated as if it were contract | feature:1576-1578 |
| 8 | No `Scenario Outline` — the disclosure gate has at least two distinct trigger shapes (no `disclosure` at all; `disclosure` present but no `required`) collapsed into one vague prose line | — |

---

## 5. Proposed Gherkin

**Status of this block: DORMANT BY DESIGN.** It stays green because no step definitions match it, which
is exactly the state the file is in today — this change cannot turn the baseline red. What it buys is a
correct binding and storyboard-exact assertions, so that when ticket **T1** below lands, the scenario
grades the right four things instead of being rewritten from scratch. The `Examples:` table encodes the
two distinct schema triggers that the current one-line prose collapses.

I am flagging this explicitly rather than burying it: **I could not find a formulation of this scenario
that is both green and truthful.** See §5b for the alternative I rejected and why.

```gherkin
  @T-UC-006-storyboard-provenance-disclosure-missing @storyboard-v3.1 @v3-1 @provenance @rejection
  Scenario Outline: PROVENANCE_DISCLOSURE_MISSING -- <case> under require_disclosure_metadata
    Given the tenant has a product whose creative_policy publishes provenance_requirements.require_disclosure_metadata = true
    And the Buyer Agent submits a creative whose provenance <provenance_shape>
    When the Buyer Agent sends a sync_creatives request
    Then the creative should have action "failed"
    And the per-creative errors[0].code should be "PROVENANCE_DISCLOSURE_MISSING"
    And the per-creative result should not carry a status field
    And the response context.correlation_id should equal the request correlation_id

    Examples:
      | case                        | provenance_shape                                      |
      | disclosure block absent     | carries no disclosure object                          |
      | disclosure.required absent  | carries a disclosure object with no required flag     |

    # Storyboard phase 5 of 6 (reject_missing_disclosure): the structural-rejection
    # contract. The seller inspects the submitted manifest against the
    # provenance_requirements it published on the product -- no verifier is called.
    #
    # Both Examples rows are mandated by core/creative-policy.json at 3.1.1:
    # require_disclosure_metadata requires "a `disclosure` object in their provenance
    # with `disclosure.required` set to a boolean value", and "Submissions that omit
    # `disclosure.required` are rejected with `PROVENANCE_DISCLOSURE_MISSING`".
    # The storyboard's own sample_request only exercises the first row.
    #
    # NOT asserted, deliberately:
    #  - error.field / error.recovery: promised in the storyboard's `expected:` prose
    #    (provenance_enforcement.yaml:383-388) but absent from its `validations:` block.
    #    Ungraded prose is not contract.
    #  - response_schema: graded upstream, but then_response_schema_valid runs no
    #    validator in this repo, so the assertion would be vacuous. See #<T3>.
    #
    # The `status` absence assertion is schema-derived, not storyboard-derived:
    # sync-creatives-response.json makes `status` forbidden when action is
    # failed or deleted (allOf/if-then).
    #
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml phase=reject_missing_disclosure step=sync_creatives_missing_disclosure
```

Notes on the rewrite:

- **`When` phrasing changed** to `the Buyer Agent sends a sync_creatives request` so it binds to the
  step that actually exists (`uc006_sync_creatives.py:256`) rather than inventing a fourth spelling.
  This is a strict improvement even while dormant: it removes one of the three reasons the scenario
  can't bind.
- **Transport-independent.** Zero transport branching; UC-006 is parametrized across A2A/MCP/REST by
  `pytest_generate_tests` and this Gherkin says nothing transport-specific.
- **Every Then compares a concrete value** — `"failed"`, the literal code string, absence of a named
  field, and an equality between response and request correlation_id. No truthiness, no bare existence.
  Clears `test_architecture_bdd_no_trivial_assertions.py`.
- Identifier tag `@T-UC-006-storyboard-provenance-disclosure-missing` unchanged — it is referenced from
  `docs/test-obligations/bdd-traceability.yaml:4819`.

### 5b. The alternative I rejected

The only formulation that would *execute green* under the current harness is a characterization of
what production actually does:

```gherkin
    Then the creative should have action "created"     # <-- do not do this
    And no provenance warning should be generated
```

Both of those pass today (verified by reading `check_provenance_required` — it returns `None` the
moment `creative.provenance is not None`, regardless of what's inside it). I am not proposing it.
Writing an approving assertion over behaviour the 3.1.1 schema calls a MUST-reject would convert a
known gap into a pinned expectation, and the next person to implement enforcement would have to delete
a passing test to do it. A dormant scenario is honest about contributing nothing; a green
characterization scenario lies about contributing something.

If the team lead prefers execution over honesty here, the characterization form is one paste away — but
it needs a `# CHARACTERIZATION: production is non-conformant, see #<T1>` banner and a ticket link, and
I'd want that decision made explicitly rather than by default.

---

## 6. Step inventory

### Existing — reused as-is

| Step | Location |
|------|----------|
| `@when("the Buyer Agent sends a sync_creatives request")` | `tests/bdd/steps/domain/uc006_sync_creatives.py:256` |
| `@then('the creative should have action "failed"')` | `tests/bdd/steps/domain/uc006_sync_creatives.py:2068` |

### Existing — near-misses that must NOT be reused

| Step | Location | Why not |
|------|----------|---------|
| `@given("the tenant has a product with creative_policy.provenance_required = true")` | `uc006_sync_creatives.py:2754` | Sets only `{"provenance_required": True}`. Does not publish `provenance_requirements`, so the disclosure gate is never armed. |
| `@then("a provenance warning should be generated")` | `uc006_sync_creatives.py:2862` | Grades the *warning* path — the non-conformant behaviour. Asserting it here would pin the gap. |

### New — required, all currently missing (this is why the scenario is dormant)

| Step | Notes |
|------|-------|
| `@given("the tenant has a product whose creative_policy publishes provenance_requirements.require_disclosure_metadata = true")` | The helper `_setup_product_with_creative_policy(ctx, creative_policy={...})` (`uc006_sync_creatives.py:2817-2843`) **already accepts an arbitrary policy dict** — this step is a two-line call, no new plumbing. |
| `@given(parsers.parse("the Buyer Agent submits a creative whose provenance {provenance_shape}"))` | Parametrized by the Examples column; builds on the existing `_build_creative_payload` (`:2688`). |
| `@then("the per-creative errors[0].code should be \"{code}\"")` | No positional per-creative error-code assertion exists in the UC-006 module today. Should be written generically (it is needed identically by the two sibling scenarios `provenance-required-rejection` and `provenance-digital-source-type-missing`) — DRY, one step, three scenarios. |
| `@then("the per-creative result should not carry a status field")` | Grades the `sync-creatives-response.json` if/then constraint. Also reusable by every `action: failed` scenario in the file. |
| `@then("the response context.correlation_id should equal the request correlation_id")` | Graded in **every one of the six phases** of this storyboard. Belongs in `tests/bdd/steps/generic/then_payload.py`, not in the UC-006 module. |

**Do not write these steps as part of the baseline PR** — the moment they bind, the scenario runs and
fails. They belong with ticket **T1**.

---

## 7. TICKET MATERIAL

**T1 — `sync_creatives` never enforces `provenance_requirements`; three graded PROVENANCE_* codes are unreachable.**
Production reads exactly one provenance field. `check_provenance_required`
(`src/core/tools/creatives/_validation.py:144-173`) returns early with `None` as soon as
`creative.provenance is not None` — it never inspects `digital_source_type`, `disclosure`, or
`embedded_provenance`. `grep -rn "require_disclosure_metadata\|require_digital_source_type\|require_embedded_provenance\|accepted_verifiers" src/` → **zero hits**; `grep -rn "PROVENANCE_" src/` → **zero hits**.
`core/creative-policy.json` at v3.1.1 states: *"Sellers that publish a requirement here MUST enforce it
on creative submission: a `sync_creatives` request that omits a required field is rejected with the
corresponding `PROVENANCE_*` error code"*, and for `require_disclosure_metadata` specifically:
*"Submissions that omit `disclosure.required` are rejected with `PROVENANCE_DISCLOSURE_MISSING`."*
Graded at `dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml:422-436`
(disclosure), `:261-275` (digital_source_type), `:349-363` (off-list verifier).
**The emission plumbing already exists** — `_failed_sync_result(creative_id, msg, code=..., recovery=...)`
(`src/core/tools/creatives/_processing.py:34-59`) produces exactly the graded shape
(`action: "failed"`, `errors[0].code`, `recovery`, no `status`). The work is the gate logic at the
`check_provenance_required` call site (`src/core/tools/creatives/_sync.py:180-184`), plus turning the
result from a warning into a per-item failure. Note the schema's precise trigger is a missing
`disclosure.required` **flag**, not a missing `disclosure` object.

**T2 — provenance policy is resolved tenant-wide from an arbitrary product, not from the creative's product.**
`src/core/tools/creatives/_sync.py:184` passes `provenance_policies[0]` with the comment *"Use the first
matching policy (tenant-wide enforcement)"*, where the list comes from
`CreativeRepository.get_provenance_policies()` (`src/core/database/repositories/creative.py:263-273`).
Two defects: (a) a tenant with two products having different `provenance_requirements` enforces
whichever row the query returns first — non-deterministic across tenants; (b) the query filters on
`p.creative_policy.get("provenance_required")` alone, so a product publishing `provenance_requirements`
**without** `provenance_required: true` is invisible to enforcement entirely. The 3.1.1 schema scopes
`creative_policy` to *"a product"* (`core/creative-policy.json` title: *"Creative requirements and
restrictions for a product"*), so per-product resolution is the contract. Blocks any correct
implementation of T1.

**T3 — `then_response_schema_valid` runs no validator, so `check: response_schema` is ungradeable.**
Already known (brief §"Known production gaps"), re-cited because it is 1 of the 4 graded checks in
this phase and the reason I could not include the schema assertion. `tests/helpers/pinned_schema.py::validate_against_pinned_schema`
exists but is not called; and `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not
3.1.1, so wiring it without re-vendoring would validate against the wrong version.
Graded at `provenance_enforcement.yaml:423-424` (and in all six phases of this storyboard).

**T4 — `context.correlation_id` echo is graded in all six phases of this storyboard and asserted in none of our scenarios.**
`grep -rn "correlation_id" tests/bdd/steps/` finds no generic echo assertion. Every phase of
`provenance_enforcement.yaml` grades it (`:137-140`, `:204-207`, `:272-275`, `:360-363`, `:433-436`,
`:514-517`), as does essentially every other 3.1.1 storyboard. This is a one-step, repo-wide win that
belongs in `tests/bdd/steps/generic/then_payload.py`. Needs a production check first: confirm
`sync_creatives` echoes `context` on the per-item-failure path across all four transports (the brief
already records that REST drops `context` in `src/routes/api_v1.py` — if so, that is the fix).

**T5 — `src/core/schemas/_base.py:1404-1414` redeclares a field the library already provides (Pattern #1 violation).**
`class CreativePolicy(LibraryCreativePolicy)` adds `provenance_required`, but `adcp==6.6.0`'s
`CreativePolicy` already carries `provenance_required`, `provenance_requirements`, **and**
`accepted_verifiers` (verified: `CreativePolicy.model_fields.keys()` →
`['co_branding', 'landing_page', 'templates_available', 'provenance_required', 'provenance_requirements', 'accepted_verifiers']`).
CLAUDE.md Pattern #1: *"Only redeclare parent fields when needed for nested serialization."* There is no
nested-serialization reason here. Worse, the subclass is near-dead: its only use in `src/` is a type
annotation at `src/core/tools/creatives/_validation.py:146`; `Product.creative_policy` resolves to the
**library** type, and `src/core/product_conversion.py:450-451` passes the raw DB dict straight through.
Delete the subclass and import the library type. Side benefit: it makes visible that
`provenance_requirements` and `accepted_verifiers` already round-trip through `get_products` today,
which is what T1 needs to be testable end-to-end.

---

## 8. Risks

- **Nothing here was verified by execution.** I did not run the BDD suite — no Postgres was provisioned
  for this task and the brief scopes me to proposal-only. Every production claim comes from reading
  source: `_validation.py:144-173`, `_sync.py:139-184` + `:275-278` + `:328-331`,
  `_processing.py:34-59`, `creative.py:263-273`, `capabilities.py:271`, `product_conversion.py:450-451`.
  The dormancy claim rests on the absence of matching `@given`/`@when`/`@then` registrations in
  `tests/bdd/steps/` plus the auto-xfail hook at `conftest.py:99-101`; I did not observe the xfail in a
  test report.
- **`Scenario Outline` row 2 is schema-derived, not storyboard-derived.** The storyboard's
  `sample_request` only exercises the "no `disclosure` object" case. The second row (`disclosure`
  present, `required` absent) comes from the `require_disclosure_metadata` description in
  `core/creative-policy.json`, which is the higher authority per the brief. If the upstream runner ever
  grades only its own sample, row 2 will be ours alone — correct, but unmatched upstream.
- **`domains/` vs `protocols/` may flip.** At 3.1.1 both trees exist and are byte-identical, but only
  `protocols/` is present under `static/compliance/source/` at the tag. I cited `protocols/`. If
  upstream retires the alias in favour of `domains/`, every `@source` in this repo needs a sweep — not
  just this one.
- **Drift beyond our pin (noted, not acted on).** `v3.1.2` … `v3.1.8` exist in the spec repo. I read
  nothing past `v3.1.1`, so I cannot say whether the PROVENANCE family or the disclosure trigger
  changed after our pin.
- **The `has_creative_library` capability question is unresolved.** The storyboard declares it under
  `agent.capabilities` and we emit no such marker. I judged it non-gating (the runner gates on
  specialism/protocol, and there is no provenance specialism), but I did not find the runner's gating
  code to confirm — it lives upstream, not in this repo.
- **T4's premise needs one check I did not do:** whether `sync_creatives` echoes `context` on the
  per-item-failure path on all four transports. If REST drops it (as the brief records for other
  tools), T4 grows a production fix.

---

## Summary

1. **VERDICT: GRADED, correctly bound, zero production coverage, currently dormant.**
2. The `@source` **path is right** — this scenario escaped the 16-scenario off-by-one; only the ref is stale.
3. Re-pin `ref=v3.1-04f59d2d5 commit=04f59d2d5` → `ref=v3.1.1 commit=467fd93d7`, and add `phase=reject_missing_disclosure step=sync_creatives_missing_disclosure`.
4. Real binding: `dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml:365` (phase), `:376` (step), `:422-436` (four graded checks).
5. Tier is `protocols/media-buy`, which `capabilities.py:271` declares → on our conformance path → `@storyboard-v3.1` **stays**, no downgrade to `@schema-v3.1`.
6. `PROVENANCE_DISCLOSURE_MISSING` is in the 3.1.1 enum (92 codes) and in `adcp==6.6.0` — schema and SDK agree.
7. Production emits it **never**: `grep "PROVENANCE_" src/` → zero; `require_disclosure_metadata` → zero. We implement only `provenance_required`, and only as a warning.
8. The scenario is dormant — `When the Buyer Agent sends sync_creatives` matches no step; auto-xfail at `conftest.py:99-101` is what makes the baseline green.
9. Proposed Gherkin: `Scenario Outline` with the two schema-mandated triggers, storyboard-exact assertions, correct `@source`, bound to the real `@when` — **kept dormant on purpose**; I rejected the green-but-dishonest characterization variant and say so in §5b.
10. Five tickets, T1 (enforcement gate — plumbing already exists in `_failed_sync_result`) and T2 (per-product policy resolution) being the ones that unblock this scenario.

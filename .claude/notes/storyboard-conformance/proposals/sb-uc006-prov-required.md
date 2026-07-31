# Re-pin: `@T-UC-006-storyboard-provenance-required-rejection`

Scenario: `tests/bdd/features/BR-UC-006-sync-creatives.feature:1536-1547`
Repo under audit: `/Users/konst/projects/salesagent-sbsweep` @ `test/storyboard-binding-baseline`
Spec: `/Users/konst/projects/adcp` @ `v3.1.1` (`467fd93d77112baf9e094e18980119edcd3a4d07`)

---

## 1. VERDICT

**GRADED — and production is non-conformant. The scenario CANNOT be made green as a storyboard assertion.**

The behaviour *is* really graded at 3.1.1: `provenance_enforcement.yaml` phase `reject_no_provenance` carries a
real `validations:` block asserting `creatives[0].action == "failed"` and
`creatives[0].errors[0].code == "PROVENANCE_REQUIRED"` — not narrative prose. The tier is
`protocols/media-buy/` (a protocol we declare) and the step's `required_tools` (`get_products`,
`sync_creatives`) are both tools we advertise. So `@storyboard-v3.1` is **justified** and must stay;
this is *not* an "undeclared gate" case and it must **not** be downgraded to `@schema-v3.1`.

What is wrong is our implementation. Under `creative_policy.provenance_required = true` with provenance
absent, production **accepts the creative** (`action: "created"`) and appends an advisory *warning string*
(`src/core/tools/creatives/_validation.py:144-174` → `src/core/tools/creatives/_sync.py:181-184, 276-277,
329-330`). It never emits `action: "failed"` and never emits the code `PROVENANCE_REQUIRED` — that string
does not appear anywhere in `src/`.

Consequently the only baseline-safe change is: **re-pin the footer, document the divergence, and leave the
scenario dormant.** Writing the three missing step definitions would turn a currently-xfailing scenario RED.
Rewriting it to assert production's warning behaviour would (a) enshrine non-conformant behaviour under a
`@storyboard-v3.1` tag and (b) duplicate four scenarios that already exist in this same file (see §4.3).

Current state is CI-green by accident: all three `Then` steps (and the `Given`/`When`) have no step
definitions, so `pytest_runtest_makereport` in `tests/bdd/conftest.py:83-104` converts
`StepDefinitionNotFoundError` into a non-strict xfail. The scenario is **dormant**.

---

## 2. Real binding at 3.1.1

### What the footer says now (wrong on one axis, right on the other)

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml
```

- **`path` is CORRECT.** This scenario is *not* one of the 16 off-by-one victims. It genuinely binds to
  `provenance_enforcement.yaml`, phase 2 (`reject_no_provenance`), exactly as its prose claims.
- **`ref`/`commit` are STALE.** `04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin.
- **The footer names no phase or step**, which is how the off-by-one drift went unnoticed across the
  sibling scenarios. Add `phase=` and `step=`.

### Where it is actually graded

File (identical in source and dist — verified byte-for-byte):
- `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml`
- `git show v3.1.1:static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml`

Phase `reject_no_provenance` — **line 142**. Step `sync_creatives_no_provenance` — **line 152**.
Graded `validations:` block — **lines 188-207**, quoted verbatim:

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_value
            path: "creatives[0].action"
            value: "failed"
            description: "Per-creative action is failed for the no-provenance submission"
          # Per-creative error assertions read errors[0].code positionally.
          # The handler emits errors in the cascade order documented on
          # enforceProvenancePolicy (PROVENANCE_REQUIRED first), so [0] is
          # stable. If a future implementation accumulates errors, the same
          # cascade priority should drive the array order.
          - check: field_value
            path: "creatives[0].errors[0].code"
            value: "PROVENANCE_REQUIRED"
            description: "Per-creative error code is PROVENANCE_REQUIRED — provenance object absent on a creative under a policy that requires it"
          - check: field_value
            path: "context.correlation_id"
            value: "provenance_enforcement--reject_no_provenance"
            description: "Context correlation_id returned unchanged on rejection"
```

Four graded checks. Our scenario asserts two of them (action, errors[0].code), states the third
(`response_schema`) in a form that runs no validator, and **omits the correlation_id echo entirely**.

### Tier ownership

`protocols/media-buy/` — with an identical mirror at `domains/media-buy/scenarios/provenance_enforcement.yaml`
(`diff` = empty). Not a specialism; `dist/compliance/3.1.1/index.json` lists no specialism containing it.

We declare `supported_protocols=[media_buy]` (`src/core/tools/capabilities.py:99`), so the tier is on our
conformance path. Two caveats, both non-disqualifying:

- `provenance_enforcement` is **not** in `requires_scenarios` of `protocols/media-buy/index.yaml` (that list
  is 14 entries and does not include it), so it is a standalone scenario in the tier rather than a baseline
  gate. It still selects on `required_tools: [get_products, sync_creatives]` — both advertised by us.
- `agent.capabilities: [has_creative_library]` on the storyboard is descriptive, not a wire gate; there is
  no `has_creative_library` field in `get_adcp_capabilities`.

### Sibling attribution (the lead asked which of the three citations is right)

The off-by-one **starts one scenario later than expected**. Verified against the phase list:

| Feature scenario | Cited path | True binding | Verdict |
|---|---|---|---|
| `...-provenance-required-rejection` (mine) | `provenance_enforcement.yaml` | phase 2 `reject_no_provenance` L142 | path **correct**, ref stale |
| `...-provenance-digital-source-type-missing` | `provenance_enforcement.yaml` | phase 3 `reject_missing_digital_source_type` L209 | path **correct**, ref stale |
| `...-provenance-disclosure-missing` | `provenance_enforcement.yaml` | phase 5 `reject_missing_disclosure` L365 | path **correct**, ref stale |
| `...-provenance-corrected-acceptance` | `provenance_truth_of_claim.yaml` | phase 6 `accept_with_disclosure` of **`provenance_enforcement.yaml`** L438 | **WRONG FILE** — off-by-one |
| `...-provenance-claim-contradicted` | `protocols/creative/index.yaml` | `provenance_truth_of_claim.yaml` | **WRONG FILE** — off-by-one |

So all three `provenance_enforcement.yaml` citations are the right file; the drift begins at
`corrected-acceptance`, which took the *next* scenario's path. Owners of those two scenarios should be told.

**Coverage gap:** the feature file has **no scenario at all** for phase 4, `reject_off_list_verifier` /
`PROVENANCE_VERIFIER_NOT_ACCEPTED` (storyboard L277-363) — the phase the narrative calls
"the buyer-controlled-URL trust gap". Five of six phases are represented; the security-relevant one is missing.

---

## 3. Schema constraints at 3.1.1

### `PROVENANCE_REQUIRED` is a real, first-class code

`git show v3.1.1:static/schemas/source/enums/error-code.json` — 92 entries, including:

```
"PROVENANCE_REQUIRED",
"PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING",
"PROVENANCE_DISCLOSURE_MISSING",
"PROVENANCE_EMBEDDED_MISSING",
"PROVENANCE_VERIFIER_NOT_ACCEPTED",
"PROVENANCE_CLAIM_CONTRADICTED"
```

The enum is advisory only — `core/error.json` wire-types `code` as bare `string`
(`"The error-code vocabulary is open: error.code is wire-typed string (not a closed enum)"`), so emitting the
code is not blocked by schema validation. `core/error.json` `required: ["code", "message"]`.

### `creative_policy.provenance_required` is SPEC, not a local extension

`git show v3.1.1:static/schemas/source/core/creative-policy.json` carries `provenance_required`,
`provenance_requirements` (with `require_digital_source_type` / `require_disclosure_metadata` /
`require_embedded_provenance`) and `accepted_verifiers`. The normative sentence that mandates my scenario:

> "Sellers that publish a requirement here **MUST enforce it on creative submission**: a `sync_creatives`
> request that omits a required field is **rejected with the corresponding `PROVENANCE_*` error code**
> (see error-code.json) […] This is the structural-rejection surface […] **Field-level requirements are
> seller-enforced — JSON Schema validation does not check them.**"

That last clause is why a schema-only check can never catch this: it is a behavioural obligation on us.

On `provenance_required` itself:

> "Whether creatives must include provenance metadata. When true, the seller **requires** buyers to attach
> provenance declarations to creative submissions."

### `sync-creatives-response.json` — where the rejection lives

`git show v3.1.1:static/schemas/source/creative/sync-creatives-response.json`. The `SyncCreativesSuccess`
branch is the correct shape (a per-item failure is **not** a terminal error response):

> `"creatives": { … "Results for each creative processed. Items with action='failed' indicate per-item
> validation/processing failures, not operation-level failures." }`
> `"errors": { … "Validation or processing errors (only present when action='failed')", items: $ref core/error.json }`

Per-item `required: ["creative_id", "action"]`, and a conditional that matters here:

```json
"allOf": [{ "if": { "properties": { "action": { "enum": ["failed", "deleted"] } }, "required": ["action"] },
           "then": { "not": { "required": ["status"] } } }]
```

i.e. **`status` MUST be absent on a `failed` item**. Any implementation of this rejection must not attach a
`CreativeStatus` to the failed entry.

The response also `allOf`-refs `core/protocol-envelope.json`, whose `required: ["status"]` is the known
top-level-status gap.

---

## 4. Conflicts

### 4.1 Schema vs storyboard

**No conflict.** The storyboard's four graded checks are all consistent with the 3.1.1 schemas, and
`creative-policy.json`'s "MUST enforce … rejected with the corresponding `PROVENANCE_*` error code" is the
schema-side mandate for the same behaviour. The schema is if anything *stronger* than the storyboard: it adds
the `action: failed ⇒ no status` constraint, which the storyboard does not grade.

### 4.2 What the scenario gets wrong

1. **Stale `@source` ref** (`v3.1-04f59d2d5`, an ancestor of beta.3) and no `phase=`/`step=` anchor.
2. **Dormant, not graded.** All five steps are unimplemented, so pytest-bdd raises
   `StepDefinitionNotFoundError` and `tests/bdd/conftest.py:99-101` silently converts it to xfail. The
   scenario reads as coverage and delivers none — the dormant-scenario anti-pattern.
3. **`Then the response envelope should be schema-valid against sync-creatives-response.json` is vacuous
   even if implemented** — the sibling phrasing at `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101`
   runs no validator, while `tests/helpers/pinned_schema.py::validate_against_pinned_schema` sits unused.
4. **Missing the correlation_id echo** — one of the four graded checks, and the only one production
   plausibly satisfies (`_sync.py:463` passes `context=context` straight into `SyncCreativesResponse`).
5. **Policy scoping is wrong in the Given.** The storyboard binds the requirement to *the product the
   creative is submitted against*, discovered via `get_products`. Our `Given the tenant has a product with
   creative_policy.provenance_required = true` matches production's actual (also wrong) behaviour:
   `CreativeRepository.get_provenance_policies()` (`src/core/database/repositories/creative.py:263-273`)
   scans **every** product in the tenant and `_sync.py:184` then applies `provenance_policies[0]` to every
   creative. One product with the flag makes the whole tenant's creatives subject to a policy they were
   never submitted against.

### 4.3 Why a "rewrite it to the warning behaviour" is rejected

Production's warning behaviour is already graded **four times** in this same feature file:

- `BR-UC-006-sync-creatives.feature:97` `@T-UC-006-main-provenance-warning`
- `:687` `INV-1 — provenance absent when required triggers warning`
- `:863` `@T-UC-006-partition-provenance`, row `provenance_absent_when_required`
- `:1123` `@T-UC-006-boundary-provenance`, row `provenance absent + policy requires provenance`

Retargeting the storyboard scenario at that behaviour adds a fifth copy (DRY invariant) and puts a
`@storyboard-v3.1` tag on an assertion that contradicts the storyboard it cites.

---

## 5. Proposed Gherkin

**Recommendation: dormancy preserved, binding corrected.** The steps stay unimplemented on purpose so the
scenario remains a non-strict xfail; the comment block makes the dormancy explicit instead of accidental, so
the next reader does not mistake it for coverage. Nothing here goes red.

Two small assertion changes are still worth making now, because they cost nothing while dormant and make the
scenario correct the day the gap is closed: the graded `context.correlation_id` echo is added, and the
vacuous "schema-valid" line is replaced with the schema's actual per-item constraint
(`failed` ⇒ no `status`), expressed as a comparison rather than a validity claim.

Replace `tests/bdd/features/BR-UC-006-sync-creatives.feature:1536-1547` with:

```gherkin
  @T-UC-006-storyboard-provenance-required-rejection @storyboard-v3.1 @v3-1 @provenance @rejection
  Scenario Outline: PROVENANCE_REQUIRED -- <partition> under a policy that requires provenance
    Given the seller publishes a product whose creative_policy sets provenance_required to "true"
    And the Buyer Agent submits a creative whose manifest carries <provenance_state>
    And the request carries context.correlation_id "provenance_enforcement--reject_no_provenance"
    When the Buyer Agent sends sync_creatives
    Then the per-creative result should report action "<action>"
    And the per-creative errors[0].code should be "<error_code>"
    And the per-creative result should carry no status field
    And the response context.correlation_id should be "provenance_enforcement--reject_no_provenance"

    Examples: provenance presence under provenance_required = true
      | partition            | provenance_state             | action | error_code           |
      | no provenance object | no provenance object at all  | failed | PROVENANCE_REQUIRED  |

    # DORMANT ON PURPOSE -- do NOT write the step definitions below until the production
    # gap is closed. Implementing them turns this scenario RED, not green.
    #
    # Graded at AdCP 3.1.1, provenance_enforcement.yaml phase `reject_no_provenance`
    # (L142) step `sync_creatives_no_provenance` (L152), validations L188-207:
    #   creatives[0].action        == "failed"
    #   creatives[0].errors[0].code == "PROVENANCE_REQUIRED"
    #   context.correlation_id      == "provenance_enforcement--reject_no_provenance"
    # Mandated by core/creative-policy.json: "Sellers that publish a requirement here MUST
    # enforce it on creative submission: a sync_creatives request that omits a required field
    # is rejected with the corresponding PROVENANCE_* error code."
    #
    # PRODUCTION DOES NOT DO THIS. src/core/tools/creatives/_validation.py:144 returns an
    # advisory warning string and src/core/tools/creatives/_sync.py:329 appends it to a
    # result whose action is "created". The code PROVENANCE_REQUIRED is never emitted.
    # Tracked in #<PROVENANCE-ENFORCEMENT-ISSUE>. The warning behaviour production DOES
    # implement is already graded at :97, :687, :863 and :1123 -- do not re-assert it here.
    #
    # `the per-creative result should carry no status field` is not from the storyboard: it is
    # sync-creatives-response.json's per-item conditional
    # `if action in [failed, deleted] then not required [status]`.
    #
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml phase=reject_no_provenance step=sync_creatives_no_provenance
```

The `Scenario Outline` with a one-row `Examples:` is deliberate: phase 4
(`PROVENANCE_VERIFIER_NOT_ACCEPTED`, storyboard L277) currently has no scenario at all, and phases 3 and 5
live in separate scenarios asserting the identical four-step shape. Once the production gap is closed, the
whole `PROVENANCE_*` structural-rejection family collapses into rows of this one table. Leaving the outline
in place now means that consolidation is a table edit rather than a rewrite.

### If the lead wants live coverage instead of dormancy

There is exactly one graded check production plausibly satisfies — the `context.correlation_id` echo
(`_sync.py:463` passes `context` through unchanged). It could be split into a separate green scenario. I did
**not** propose it, for two reasons: it needs three new step definitions whose behaviour across all four
transports I could not verify by execution in a read-only worktree, and a scenario that grades only the
correlation echo, tagged to a storyboard step about provenance rejection, is misleading about what it covers.
Filed as ticket material instead.

---

## 6. Step inventory

### Existing — reusable as-is

| Step | Location |
|---|---|
| `@then('the creative should have action "created"')` | `tests/bdd/steps/domain/uc006_sync_creatives.py:2048` |
| `@then('the creative should have action "failed"')` | `tests/bdd/steps/domain/uc006_sync_creatives.py:2068` |
| `@when("the Buyer Agent sends a sync_creatives request")` | `tests/bdd/steps/domain/uc006_sync_creatives.py:256` |
| `@given("the tenant has a product with creative_policy.provenance_required = true")` | `tests/bdd/steps/domain/uc006_sync_creatives.py:2754` |
| `@given("a creative with no provenance metadata")` | `tests/bdd/steps/domain/uc006_sync_creatives.py:2722` |
| `@then("a provenance warning should be generated")` | `tests/bdd/steps/domain/uc006_sync_creatives.py:2862` |

### Existing but NOT matched by this scenario's phrasing (this is what makes it dormant)

- Scenario says `When the Buyer Agent sends sync_creatives`; the implemented step is
  `the Buyer Agent sends a sync_creatives **request**`. Near-miss, no match.
- Scenario says `Then the per-creative result should report action "failed"`; the implemented step is
  `the **creative** should have action "failed"`. Near-miss, no match.

I deliberately did **not** re-phrase the proposed Gherkin onto the existing `When`/`Then` wording. Doing so
would match the existing `When` and `Then action "failed"` steps, the scenario would stop xfailing, and it
would then fail RED on the `action` assertion. Keeping the storyboard phrasing keeps it dormant.

### New — required only when the gap is closed (do not write now)

| Step | Notes |
|---|---|
| `Given the seller publishes a product whose creative_policy sets provenance_required to "<v>"` | parametrized replacement for the two existing hardcoded true/false Givens (DRY) |
| `Given the Buyer Agent submits a creative whose manifest carries <provenance_state>` | outline-parametrized creative builder |
| `Given the request carries context.correlation_id "<id>"` | no equivalent exists in `tests/bdd/steps/`; nearest is `uc011_accounts.py:2204` `the context is identical to what was sent` |
| `When the Buyer Agent sends sync_creatives` | alias onto `uc006_sync_creatives.py:256` |
| `Then the per-creative result should report action "<action>"` | alias onto `uc006_sync_creatives.py:2068`, parametrized |
| `Then the per-creative errors[0].code should be "<code>"` | new; must read the **wire** envelope via `assert_envelope_shape`, not the reconstructed model |
| `Then the per-creative result should carry no status field` | new; schema conditional, wire-level |
| `Then the response context.correlation_id should be "<id>"` | new |

---

## 7. TICKET MATERIAL

**T1 — `provenance_required` is advisory, not enforced: `PROVENANCE_REQUIRED` is never emitted.**
`src/core/tools/creatives/_validation.py:144-174` (`check_provenance_required`) returns a warning *string*
when `creative_policy.provenance_required` is true and `creative.provenance is None`;
`src/core/tools/creatives/_sync.py:329-330` appends it to a result whose action is `created`. Grep of `src/`
for `PROVENANCE_REQUIRED` returns nothing. 3.1.1 `core/creative-policy.json` mandates: *"Sellers that publish
a requirement here MUST enforce it on creative submission: a `sync_creatives` request that omits a required
field is rejected with the corresponding `PROVENANCE_*` error code."* Graded by
`dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml:188-207`. Fix: emit
`SyncCreativeResult(action="failed", errors=[Error(code="PROVENANCE_REQUIRED", …)])` and omit `status` on the
failed item per `sync-creatives-response.json`'s `if action in [failed,deleted] then not required [status]`.

**T2 — Provenance policy is applied tenant-wide instead of per-product.**
`src/core/database/repositories/creative.py:263-273` (`get_provenance_policies`) scans *all* products in the
tenant; `src/core/tools/creatives/_sync.py:140-141, 184` then applies `provenance_policies[0]` to every
creative in the sync. A single product carrying the flag subjects every creative in the tenant to a policy it
was never submitted against, and the *first* product's policy silently wins when several differ. The 3.1.1
storyboard binds the requirement to the product discovered via `get_products`
(`provenance_enforcement.yaml:83-140`, phase `discover_requirement`), and `core/creative-policy.json` scopes
`creative_policy` to "a product".

**T3 — `provenance_requirements` / `accepted_verifiers` are unread, so four of six storyboard phases cannot
be implemented.** `adcp==6.6.0`'s `CreativePolicy` already exposes `provenance_requirements` and
`accepted_verifiers` (verified: `sorted(CreativePolicy.model_fields) == ['accepted_verifiers', 'co_branding',
'landing_page', 'provenance_required', 'provenance_requirements', 'templates_available']`), but no code under
`src/` references either name. Blocks `PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING` (storyboard L209),
`PROVENANCE_VERIFIER_NOT_ACCEPTED` (L277), `PROVENANCE_DISCLOSURE_MISSING` (L365) and the corrected-acceptance
phase (L438).

**T4 — `src/core/schemas/_base.py:1404-1415` redeclares an inherited spec field and its docstring is wrong.**
`class CreativePolicy(LibraryCreativePolicy)` redeclares `provenance_required` and documents it as *"Local
extension adds provenance_required for EU AI Act Article 50 compliance"* / *"Library provides: co_branding,
landing_page, templates_available."* Both statements are false under `adcp==6.6.0`: the library parent
provides all three provenance fields. This is a CLAUDE.md Pattern #1 (schema inheritance) violation — the
redeclaration should be deleted, which also makes `provenance_requirements` and `accepted_verifiers` visible
to callers for free.

**T5 — No scenario covers storyboard phase 4, `PROVENANCE_VERIFIER_NOT_ACCEPTED`.**
`BR-UC-006-sync-creatives.feature` has scenarios for storyboard phases 2, 3, 5 and 6 but none for phase 4
(`reject_off_list_verifier`, `provenance_enforcement.yaml:277-363`), the phase whose narrative states the
seller *"MUST cross-check the URL before any outbound call […] closing the buyer-controlled-URL trust gap"*.
This is the security-relevant phase of the family and it is entirely uncovered. Add a scenario (dormant until
T3 lands) and a traceability entry alongside the existing five in
`docs/test-obligations/bdd-traceability.yaml:4807-4835`.

**T6 — Two sibling scenarios cite the wrong storyboard file (off-by-one).**
`BR-UC-006-sync-creatives.feature:1588` (`...-provenance-corrected-acceptance`) cites
`provenance_truth_of_claim.yaml` but is phase 6 `accept_with_disclosure` of `provenance_enforcement.yaml`
(L438-517). `:1607` (`...-provenance-claim-contradicted`) cites `protocols/creative/index.yaml` but belongs to
`provenance_truth_of_claim.yaml`. Both also carry the stale `ref=v3.1-04f59d2d5`. Owners of those two
scenarios in this sweep should be told; not mine to change.

**T7 — `Then the response envelope should be schema-valid against <file>.json` runs no validator.**
The only implementation of this family is `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101`, and
`tests/helpers/pinned_schema.py::validate_against_pinned_schema` exists but is unused. The storyboard grades
`check: response_schema` on this step (`provenance_enforcement.yaml:189-190`), so a green implementation is
required for real conformance. Blocked behind the top-level `status` gap
(`core/protocol-envelope.json` `required: ["status"]`) and the `04f59d2d5`-vintage fixtures in
`tests/fixtures/adcp_schemas_pinned/` — both already on the known-gaps list.

**T8 — `context.correlation_id` echo on `sync_creatives` is graded but ungraded by us.**
`provenance_enforcement.yaml:204-207` grades the echo on the rejection path;
`src/core/tools/creatives/_sync.py:463` passes `context=context` into `SyncCreativesResponse`, so it is
plausibly already correct, but no BDD step in `tests/bdd/steps/` asserts a correlation_id echo on
`sync_creatives` across the four transports. Add one.

---

## 8. Risks

1. **Nothing here was verified by execution.** The worktree is read-only per the brief, so every "green" /
   "red" claim comes from reading `src/`, not from a test run. The specific claim I would most want executed:
   that production really returns `action: "created"` (not `updated`/`unchanged`) with a warning under
   `provenance_required=true` + provenance absent. `_sync.py:329` is inside the create branch and the four
   existing warning scenarios all pass today, so I am confident in the warning; less so in the exact action
   value on an upsert path.
2. **Whether the compliance runner would actually select `provenance_enforcement` against us is inferred,
   not observed.** It is not in `requires_scenarios` of `protocols/media-buy/index.yaml`; I read its
   `required_tools: [get_products, sync_creatives]` gate as the selector, per the `required_tools` semantics
   documented at `universal/storyboard-schema.yaml:54-58`. If the runner only executes the baseline's
   `requires_scenarios` set, this scenario would be unselected — which would weaken the verdict from
   "non-conformant" to "not currently exercised", but would not change the schema-level MUST in
   `core/creative-policy.json`, which stands on its own.
3. **`prerequisites.controller_seeding: true` and `test_kit: test-kits/acme-outdoor.yaml`** mean the real
   conformance run seeds its fixture product through the compliance controller. Our BDD harness seeds via
   `ProductFactory`. The proposed `Given` phrasing assumes the factory path; if the lead intends these
   storyboard scenarios to run against a seeded controller, the Given needs rethinking.
4. **The `@source` `commit=` convention.** I used `commit=467fd93d7`, the commit `v3.1.1` points at. If the
   sweep's convention is to record the commit that last touched the cited *file* rather than the tag commit,
   this needs adjusting — it is uniform across all scenarios either way.
5. **The dormancy recommendation is deliberately conservative** and will read as "did nothing" on a diff that
   only moves a comment. The alternative — implementing the steps — is a guaranteed red on a baseline PR.
   If the intent of this sweep is to surface the gap loudly rather than keep CI green, converting the
   scenario to a strict-xfail with an explicit reason would be a better fit than the current silent
   `StepDefinitionNotFoundError` auto-xfail; that is a policy call for the lead, not mine.
6. **I did not re-verify T6's two sibling bindings against their step-level `validations:`** — only against
   phase titles and narrative. The file-level attribution is solid; the exact phase for
   `claim-contradicted` inside `provenance_truth_of_claim.yaml` is that scenario owner's job.

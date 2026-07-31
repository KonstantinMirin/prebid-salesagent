# Re-pin: `@T-UC-006-storyboard-provenance-digital-source-type-missing`

Scenario: `tests/bdd/features/BR-UC-006-sync-creatives.feature:1550`
Title: *PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING — provenance present but digital_source_type omitted*

---

## 1. VERDICT

**GRADED — and unimplemented. The scenario is currently DORMANT (auto-xfail), and the graded assertion cannot be made green.**

Three separate findings, all verified:

1. **The behaviour IS graded at 3.1.1.** `creatives[0].errors[0].code == "PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING"` is a literal `validations: - check: field_value` entry, not prose. The tier is `protocols/media-buy/` — a protocol we declare (`supported_protocols=[media_buy]`). No `requires_capability` gate, no specialism gate. It is on our conformance path. **`@storyboard-v3.1` stays.**
2. **The cited `@source` path is CORRECT for this scenario** (no off-by-one here — the prose summary line, the phase, and the cited file all agree). Only the `ref`/`commit` is stale, and for this particular file the staleness is cosmetic: `git diff 04f59d2d5 v3.1.1 -- .../provenance_enforcement.yaml` is **empty**. Re-pin anyway, for authority correctness, and re-pin to the `dist/` path that actually carries the graded artifact.
3. **The scenario is dormant today.** None of its five step phrasings exist in `tests/bdd/steps/` (verified: `require_digital_source_type`, `omits digital_source_type`, `errors[0].code should be`, `sends sync_creatives`, `the per-creative result should report action` — zero hits). `tests/bdd/conftest.py:85-104` converts `StepDefinitionNotFound` into a non-strict xfail, so the scenario has never executed a single assertion.

And the load-bearing consequence:

4. **Production cannot satisfy the graded assertion, and cannot even reach the code that would.** Our local `Provenance` model makes `digital_source_type` **required**, so a spec-legal 3.1.1 provenance object that omits it is rejected by Pydantic at `_validate_creative_input` — *before* any `creative_policy` lookup runs. The per-creative result is `action: "failed"` (which happens to match the storyboard) but with `errors[0].code == "SERVICE_UNAVAILABLE"`, and it fails **identically whether or not the seller declares `require_digital_source_type`**. The right outcome for the wrong reason.

---

## 2. Real binding at 3.1.1

**Correct file:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml`
(byte-identical to `git show v3.1.1:dist/compliance/3.1.1/...`, verified with `diff -q`)

**Storyboard id:** `media_buy_seller/provenance_enforcement`
**Phase:** `reject_missing_digital_source_type` (file lines **209-275**) — the scenario comment's "Phase 3" is right; phases are `discover_requirement`, `reject_no_provenance`, `reject_missing_digital_source_type`, …
**Step:** `sync_creatives_no_digital_source_type`

Graded `validations:` block, verbatim (lines **261-275**):

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_value
            path: "creatives[0].action"
            value: "failed"
            description: "Per-creative action is failed for the no-digital_source_type submission"
          - check: field_value
            path: "creatives[0].errors[0].code"
            value: "PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING"
            description: "Per-creative error code identifies the missing digital_source_type field"
          - check: field_value
            path: "context.correlation_id"
            value: "provenance_enforcement--reject_no_digital_source_type"
            description: "Context correlation_id returned unchanged on rejection"
```

The `expected:` prose (lines 226-229) also states the envelope-vs-item split explicitly: *"The seller accepts the request envelope but rejects the per-creative entry with action: failed"*. That is narrative, but it is consistent with the graded `creatives[0].*` paths — the failure is **per-item, inside the success variant**, not an operation-level error.

**Tier / gating.** `protocols/media-buy/` (mirrored verbatim under `domains/media-buy/`). `dist/compliance/3.1.1/index.json` lists `media-buy` under both `protocols` and `domains`. The storyboard declares `required_tools: [get_products, sync_creatives]` (both advertised by us) and **no** `requires` / `requires_capability`. Its `agent.capabilities: [has_creative_library]` is **not** a gate — `universal/storyboard-schema.yaml:365` says verbatim: *"capabilities: string[] (legacy descriptive capability labels; bundle selection is driven by get_adcp_capabilities.supported_protocols and specialisms)"*. We declare `supported_protocols=[media_buy]` in `src/core/tools/capabilities.py`, so the gate is met. Not a specialism; `provenance_enforcement` is **not** in the media-buy baseline's `requires_scenarios` list (`protocols/media-buy/index.yaml:10-23`), so it is an additional in-tier scenario rather than a baseline-blocking one — still graded, still ours.

**What the current footer points at:**

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml
```

The *path* is right (the source-side twin of the dist file, present at both commits). The *ref* is wrong on authority grounds — `04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin. For this file the content is unchanged between the two, so nothing was mis-graded; the fix is a re-pin, not a re-binding.

---

## 3. Schema constraints at 3.1.1

**`core/creative-policy.json`** (`git show v3.1.1:static/schemas/source/core/creative-policy.json`) — this is the normative sentence for the whole PROVENANCE_* family:

> `provenance_requirements`: "Structured provenance requirements for creatives. Refines `provenance_required`: when `provenance_required` is true, the fields in this object specify which provenance features the seller requires. […] **Sellers that publish a requirement here MUST enforce it on creative submission: a `sync_creatives` request that omits a required field is rejected with the corresponding `PROVENANCE_*` error code** (see error-code.json) […] **Field-level requirements are seller-enforced — JSON Schema validation does not check them.**"

> `provenance_requirements.require_digital_source_type`: "When true, the seller requires creatives to include a `digital_source_type` field in their provenance, set to a valid value from the `digital-source-type` enum (not null or absent). **Submissions that omit this field are rejected with `PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING`.**"

`required: ["co_branding", "landing_page", "templates_available"]` — `provenance_required`, `provenance_requirements`, `accepted_verifiers` are all optional on the policy.

**`enums/error-code.json`** (v3.1.1, line 71 in the enum list; description at line 165) — the code **exists** in the 3.1.1 enum:

> `"PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING"`: "Seller's `creative_policy.provenance_requirements.require_digital_source_type` is true and the submitted creative's resolved provenance (after inheritance) has no `digital_source_type` value, or has it set to null. **Distinct from `PROVENANCE_REQUIRED` (no provenance object at all) — provenance is present, just missing this specific field.** Recovery: correctable (set `provenance.digital_source_type` to a value from the `digital-source-type` enum and resubmit). **`error.field` MUST point at the resolved provenance path that was inspected** (e.g., `creatives[0].creative_manifest.provenance.digital_source_type`)."

Recovery map entry (line 449): `recovery: "correctable"`.

**`core/provenance.json`** (v3.1.1) — decisive for why the request must be *accepted*:

- `required:` — **absent**. No property on `provenance` is required.
- properties: `digital_source_type, ai_tool, human_oversight, declared_by, declared_at, created_time, c2pa, embedded_provenance, watermarks, disclosure, verification, ext`
- `digital_source_type: {"$ref": "/schemas/enums/digital-source-type.json", …}` — optional.

Cross-checked against the SDK (`adcp==6.6.0`): `adcp.types.generated_poc.core.provenance.Provenance` has **zero required fields** and accepts `{"declared_by": {"role": "agency"}}` — the storyboard's exact `sample_request` payload (lines 253-257). So the envelope-accepted/item-rejected split the storyboard grades is reachable *at the schema layer*; it is our local model that breaks it.

**`enums/digital-source-type.json`** (v3.1.1) — the full legal set:

```
digital_capture, digital_creation, trained_algorithmic_media,
composite_with_trained_algorithmic_media, algorithmic_media,
composite_capture, composite_synthetic, human_edits, data_driven_media
```

---

## 4. Conflicts

**Schema vs storyboard: no conflict.** The storyboard's `sample_request` and its graded paths are consistent with `core/provenance.json` and `core/creative-policy.json`. Nothing to override.

**Scenario vs reality — what the current Gherkin gets wrong:**

| # | Issue |
|---|---|
| C1 | **Dormant.** All five step phrasings are undefined; `conftest.py:85-104` auto-xfails on `StepDefinitionNotFound`. The scenario has never asserted anything. |
| C2 | **Drops the graded envelope check.** The sibling `PROVENANCE_REQUIRED` scenario asserts *"the response envelope should be schema-valid against sync-creatives-response.json"*; this one omits it, even though the storyboard grades `check: response_schema` on the same step. (That step is itself a no-op today — see TICKET T5 / the known-gaps list — so it must not be added back as-is.) |
| C3 | **Never establishes the discriminator.** The whole point of this code vs `PROVENANCE_REQUIRED` is *provenance is present*. The Gherkin says "omits digital_source_type" but never states that the rest of the provenance object survives — so a passing run could not distinguish the two codes. |
| C4 | **No `error.field` assertion**, though error-code.json says `error.field` **MUST** point at the inspected provenance path. |
| C5 | **Stale `@source` ref** (`v3.1-04f59d2d5`), and the path points at the source-side twin rather than the graded `dist/compliance/3.1.1/` artifact. No phase/step coordinates. |
| C6 | **Prose Thens, no `Scenario Outline`.** Nothing is parametrized. |

**Scenario vs production — why the graded assertion cannot go green (all verified by execution):**

`src/core/schemas/creative.py:82-120` defines a hand-rolled `Provenance(SalesAgentBaseModel)` — *not* an extension of the library type — with `digital_source_type: DigitalSourceType = Field(...)` **required**. `src/core/tools/creatives/_validation.py:80-91` copies the incoming SDK provenance into that model via `Creative(**schema_data)`. Calling the real production function with the storyboard's own payload:

```
_validate_creative_input(CreativeAsset(..., provenance={'declared_by': {'role': 'agency'}}), ...)
→ ValidationError, 2 errors:
     ('provenance', 'digital_source_type')  missing
     ('provenance', 'declared_by')          string_type
```

That `ValidationError` is caught at `src/core/tools/creatives/_sync.py:167-178` and turned into
`_failed_sync_result(creative_id, error_msg)` → `src/core/tools/creatives/_processing.py:34-60`, whose **default** `code="SERVICE_UNAVAILABLE"`.

So on the wire today: `action == "failed"` ✅ (matches the storyboard) but `errors[0].code == "SERVICE_UNAVAILABLE"` ❌.

And the policy is never consulted: `check_provenance_required` (`_validation.py:144-175`) is called at `_sync.py:180-184` — *after* the validation that already failed — and even when reached it only tests `creative.provenance is None` and returns a **warning string**, never an error. `get_provenance_policies` (`src/core/database/repositories/creative.py:263-273`) filters on `provenance_required` alone and never reads `provenance_requirements`. **`require_digital_source_type` is dead config in this codebase.**

Net: the only storyboard-graded fact production satisfies is `creatives[0].action == "failed"`, and it satisfies it for a reason unrelated to provenance policy.

---

## 5. Proposed Gherkin

GREEN ONLY. Every Then below was verified against the production call path. The graded error-code assertion is **deliberately absent** — it is ticket T1.

```gherkin
  @T-UC-006-storyboard-provenance-digital-source-type-missing @storyboard-v3.1 @v3-1 @provenance @rejection
  Scenario Outline: Provenance present but digital_source_type omitted is rejected per-creative, inside the success envelope
    Given the tenant has a product whose creative_policy sets provenance_required true and require_digital_source_type true
    And the Buyer Agent submits a creative whose provenance omits digital_source_type and carries "<sibling_fields>"
    When the Buyer Agent syncs the creative
    Then the response is the success variant carrying a creatives array
    And the response should include the creative with action "failed"
    And the per-creative wire error code should be "SERVICE_UNAVAILABLE"
    And the per-creative wire error message should name the field "provenance.digital_source_type"

    Examples:
      | sibling_fields |
      |                |
      | ai_tool        |

    # 3.1.1 binding — storyboard media_buy_seller/provenance_enforcement,
    #   phase reject_missing_digital_source_type, step sync_creatives_no_digital_source_type.
    # Graded there: creatives[0].action == "failed"  AND
    #               creatives[0].errors[0].code == "PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING".
    #
    # Only the FIRST of those two is green today, and only incidentally. Production
    # rejects this creative in Pydantic (src/core/schemas/creative.py:82-120 makes
    # digital_source_type REQUIRED, contradicting core/provenance.json which has no
    # required properties), long before creative_policy is read. The rejection is
    # therefore policy-INDEPENDENT: it fires identically with the policy absent.
    # The wire code SERVICE_UNAVAILABLE below is a characterization pin on that
    # incidental path, NOT an endorsement — it is emitted by the default argument of
    # _failed_sync_result (src/core/tools/creatives/_processing.py:35) and tells a
    # conforming buyer to retry a terminal, buyer-correctable failure. Both are
    # tracked: see GitHub issues filed from this sweep (provenance enforcement;
    # per-creative validation error code).
    #
    # The Examples rows are the two provenance shapes that reduce to exactly ONE
    # validation error (missing digital_source_type). Other spec-legal siblings
    # (declared_by, disclosure, c2pa, human_oversight) each add a SECOND error from
    # an unrelated type divergence in the same local model, which would make the
    # assertion ambiguous about what was actually rejected.
    #
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml phase=reject_missing_digital_source_type step=sync_creatives_no_digital_source_type
```

Notes on the design:

- **Transport-independent.** `the Buyer Agent syncs the creative` is the shared dispatch step (`uc006_sync_creatives.py:253-257`); no transport branching anywhere.
- **The envelope-vs-item split is asserted first** (`the response is the success variant carrying a creatives array`) — that is the storyboard's `expected:` contract and it is green.
- **C3 fixed**: `carries "<sibling_fields>"` makes "provenance is present" explicit and parametrized, which is exactly the `PROVENANCE_REQUIRED` discriminator.
- **C2/C4 not fixed**: `check: response_schema` maps to `then_response_schema_valid`, which runs no validator (known gap), and `error.field` is not populated by `_failed_sync_result`. Both are ticketed rather than asserted.
- Every Then compares a concrete literal — nothing truthy, nothing existence-only.

---

## 6. Step inventory

**Existing — reuse as-is, no code change:**

| Step | Location |
|---|---|
| `When the Buyer Agent syncs the creative` | `tests/bdd/steps/domain/uc006_sync_creatives.py:253` |
| `Then the response is the success variant carrying a creatives array` | `…/uc006_sync_creatives.py:6966` |
| `Then the response should include the creative with action "{action}"` | `…/uc006_sync_creatives.py:2659` |

**New — three step definitions:**

1. `Given the tenant has a product whose creative_policy sets provenance_required true and require_digital_source_type true`
   Thin wrapper over the **existing** helper `_setup_product_with_creative_policy` (`…:2817-2845`), which already accepts a full `creative_policy=` dict — pass
   `{"provenance_required": True, "provenance_requirements": {"require_digital_source_type": True}}`. No helper change needed (`Product.creative_policy` is a `JSONType` column).

2. `Given the Buyer Agent submits a creative whose provenance omits digital_source_type and carries "{sibling_fields}"`
   Thin wrapper over the **existing** `_build_creative_payload(ctx, provenance=…)` (`…:2688`). Two accepted labels — `""` → `{}`, `"ai_tool"` → `{"ai_tool": {"name": "DALL-E 3", "provider": "OpenAI"}}` — and **raise on any other label** (no silent fallback; `test_architecture_bdd_no_silent_env.py`).

3. `Then the per-creative wire error code should be "{code}"` and
   `Then the per-creative wire error message should name the field "{field}"`
   Read `response.creatives[0].errors[0].code` / `.message` **directly off the wire object**. These must **not** route through `_promote_creative_errors_to_ctx` / `_infer_error_code_from_message` (`…:2100-2143`), which synthesize a code from message substrings and never look at `errors[0].code` — that is the reconstruction the Error Verification Policy forbids. New phrasing (`… wire error code …`) is deliberate: it does not collide with the dormant `the per-creative errors[0].code should be "…"` phrasing that the sibling provenance scenarios use.

**Blast-radius warning for the lead:** the sibling scenarios `@T-UC-006-storyboard-provenance-required-rejection`, `…-disclosure-missing`, `…-corrected-acceptance` and the `error-details-*` scenarios share the phrasings `the per-creative result should report action "failed"` and `the per-creative errors[0].code should be "…"`. Defining either of those two phrasings — from any agent's proposal — un-xfails all of them at once and will turn several **red**. My proposal deliberately avoids defining them.

---

## 7. TICKET MATERIAL

**T1 — `provenance_requirements` is never enforced; no `PROVENANCE_*` code is ever emitted.**
`src/core/database/repositories/creative.py:263-273` (`get_provenance_policies`) filters products on `creative_policy["provenance_required"]` only and never reads `provenance_requirements`. `src/core/tools/creatives/_validation.py:144-175` (`check_provenance_required`) tests only `creative.provenance is None` and returns a **warning string**. `src/core/tools/creatives/_sync.py:180-184` and `:275-280` append that warning and flip status to `pending_review`; `action` is never set to `failed` on provenance grounds. Zero occurrences of any `PROVENANCE_` code in `src/`.
Mandated by: `v3.1.1 static/schemas/source/core/creative-policy.json` → `provenance_requirements` — *"Sellers that publish a requirement here MUST enforce it on creative submission: a `sync_creatives` request that omits a required field is rejected with the corresponding `PROVENANCE_*` error code"*; `enums/error-code.json:165`; graded at `dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml:268-271`. Covers the sibling codes `PROVENANCE_REQUIRED`, `PROVENANCE_DISCLOSURE_MISSING`, `PROVENANCE_EMBEDDED_MISSING`, `PROVENANCE_VERIFIER_NOT_ACCEPTED` identically.

**T2 — local `Provenance` model is a hand-rolled duplicate that diverges from `core/provenance.json` on five fields, and rejects spec-legal submissions.**
`src/core/schemas/creative.py:82-120`. Extends `SalesAgentBaseModel`, **not** the library type — a Critical Pattern #1 violation (`test_architecture_schema_inheritance.py`). Divergences, each verified by executing `_validate_creative_input`:

| field | ours | 3.1.1 `core/provenance.json` / `adcp==6.6.0` |
|---|---|---|
| `digital_source_type` | **required** | optional (schema has no `required` array) |
| `declared_by` | `str \| None` | object `{role, agent_url}` |
| `disclosure` | `str \| None` | object `{required, jurisdictions[]}` |
| `c2pa` | `str \| None` (URL) | object (`manifest_url`) |
| `human_oversight` | `bool \| None` | enum `none\|prompt_only\|selected\|edited\|directed` |
| `declared_at`, `embedded_provenance`, `watermarks`, `ext` | absent | present |

Consequence beyond this scenario: the storyboard's own Phase 4/5/6 payloads (`…/provenance_enforcement.yaml:326-340`) cannot be parsed by us at all, so the entire `provenance_enforcement` storyboard is structurally unreachable — T1 cannot be fixed without fixing T2 first.

**T3 — local `DigitalSourceType` enum diverges from `enums/digital-source-type.json`.**
`src/core/schemas/creative.py:64-79` declares `trained_algorithmic_model`, `composite_with_trained_model`, `minor_human_edits` — **none** of which exist in 3.1.1 — and is missing `trained_algorithmic_media`, `composite_with_trained_algorithmic_media`, `data_driven_media`. The storyboard's Phase 4 `sample_request` uses `trained_algorithmic_media` (`…/provenance_enforcement.yaml:327`), which we reject. Import the SDK enum rather than redeclaring it.

**T4 — per-creative validation failures are advertised as `SERVICE_UNAVAILABLE` (transient) instead of a buyer-correctable code.**
`src/core/tools/creatives/_sync.py:177` calls `_failed_sync_result(creative_id, error_msg)` with no `code=`, taking the default `code: str = "SERVICE_UNAVAILABLE"` at `src/core/tools/creatives/_processing.py:35`. `v3.1.1 enums/error-code.json` classifies `SERVICE_UNAVAILABLE` as `recovery: "transient"` ("Retry with exponential backoff"), so a conforming buyer retries a request that can never succeed without correction. The same call site also leaves `error.field` unset, which `error-code.json:165` marks **MUST** for the `PROVENANCE_*` family. `_failed_sync_result` already accepts a `code=` argument — the fix is to pass the correctable one.

**T5 — the BDD harness infers per-creative error codes from message substrings instead of reading the wire.**
`tests/bdd/steps/domain/uc006_sync_creatives.py:2132-2143` (`_infer_error_code_from_message`) maps message text to invented codes (`CREATIVE_VALIDATION_FAILED`, `CREATIVE_NAME_EMPTY`, …) that are not in the 3.1.1 enum; `_promote_creative_errors_to_ctx` (`:2100-2129`) then feeds that synthetic object to the generic `the error code should be "{code}"` step, and `_assert_per_creative_failure` (`:1484-1514`) **xfails** on mismatch. So every per-creative error assertion in UC-006 is asserting a reconstruction, and `errors[0].code` — the field the storyboard actually grades — is never read. Violates `tests/CLAUDE.md` § Error Verification Policy.

**T6 — the first product's policy is applied tenant-wide.**
`src/core/tools/creatives/_sync.py:182-184`: `check_provenance_required(validated_creative, provenance_policies[0])`, with the comment *"Use the first matching policy (tenant-wide enforcement)"*. `creative_policy` is a **per-product** field in 3.1.1; a creative is graded against the policy of the product(s) it will run on. With several products carrying different `provenance_requirements`, enforcement is arbitrary.

---

## 8. Risks

- **Not executed.** I did not start Postgres, so I never ran the BDD scenario end-to-end. What I *did* run is `_validate_creative_input` — the exact function called at `_sync.py:164` — against real `adcp.types.CreativeAsset` payloads, which is where the outcome is decided. The `SERVICE_UNAVAILABLE` value is read statically from the default argument at `_processing.py:35` reached via `_sync.py:177`. **Recommend the lead run this one scenario before merging.**
- **The `SERVICE_UNAVAILABLE` pin is a characterization assertion.** It will go red the moment T1 or T4 is fixed — which is the intent (a tripwire), but it does encode non-conformant behaviour in a `@storyboard-v3.1`-tagged scenario. If the lead prefers a baseline that encodes nothing wrong, drop that single line; the remaining three Thens stay green and the scenario stays non-vacuous.
- **`e2e_rest` transport.** `_get_sync_creative_result` (`:2646-2656`) hard-asserts `isinstance(resp, SyncCreativesResponse)`. Other UC-006 scenarios use it over the same transport set, so it should hold, but I could not confirm the REST reconstruction preserves `creatives[0].errors[0]` typed as `adcp…core.error.Error`. If it arrives as a dict, the new wire-reading step needs a dict/model accessor — worth writing it defensively from the start.
- **Shared-phrasing collision.** See the blast-radius warning in §6. If another agent's proposal defines `the per-creative result should report action "{action}"` or `the per-creative errors[0].code should be "{code}"`, several dormant siblings wake up simultaneously; that needs to be sequenced, not merged in parallel.
- **Drift beyond our pin (noted only).** `static/` in the spec worktree is at `v3.1.1-109-gac1f4bb46`, not `v3.1.1`. I read every schema through `git show v3.1.1:…`. The only relevant post-3.1.1 change I saw is `RATE_LIMITED` / `IDEMPOTENCY_IN_FLIGHT` moving `retry_after` from `error.details` to top-level `error` — irrelevant here. The `dist/compliance/3.1.1/` storyboard on disk is byte-identical to `v3.1.1`.
- One judgement call worth naming: I read `agent.capabilities: [has_creative_library]` as **not** a conformance gate, on the strength of `storyboard-schema.yaml:365` calling it "legacy descriptive". If a runner does gate on it, and we do not advertise a creative library, this scenario would be `not_applicable` and the tag should become `@schema-v3.1`. I do not believe that is the case, but it is the one place where a different reading changes the verdict.

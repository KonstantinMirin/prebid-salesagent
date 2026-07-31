# Re-pin proposal — `@T-UC-006-storyboard-provenance-claim-contradicted`

Scenario: `tests/bdd/features/BR-UC-006-sync-creatives.feature:1591`
Title: *PROVENANCE_CLAIM_CONTRADICTED — on-list verifier refutes buyer's digital_source_type claim*

---

## 1. VERDICT

**NOT GRADED — undeclared gate (and orphan storyboard).**

Three independent reasons, any one of which is sufficient:

1. **The storyboard is an orphan at 3.1.1.** The behaviour lives in
   `media_buy_seller/provenance_truth_of_claim`, which appears in **no** `requires_scenarios:`
   list anywhere in `dist/compliance/3.1.1/`. Per `universal/storyboard-schema.yaml:64-66`,
   scenarios only execute when a storyboard requires them ("The compliance engine resolves and
   runs them alongside the main storyboard"). Neither `protocols/media-buy/index.yaml`
   (14 required scenarios) nor `specialisms/sales-non-guaranteed/index.yaml` (15 required
   scenarios) lists it. Verified by full-tree grep — the string `provenance_truth_of_claim`
   occurs only inside the two identical copies of the scenario file itself and in one narrative
   cross-reference. The same holds at 3.1.2 / 3.1.5 / 3.1.8, so this is not a 3.1.1 accident.
2. **The capability gate is undeclared.** The scenario declares
   `agent.capabilities: [has_creative_library]` (line 43), the capability that identifies the
   **creative** protocol baseline (`protocols/creative/index.yaml:26`). We declare
   `supported_protocols=[media_buy]` and `specialisms=[sales_non_guaranteed]` only
   (`src/core/tools/capabilities.py:99-100`, `:271-272`).
3. **Production cannot participate at all.** `grep -rn "PROVENANCE_" src/` returns **zero**
   hits. There is no verifier client, no `get_creative_features` caller, no
   `accepted_verifiers` reader, and `Provenance` has no `embedded_provenance` field — the
   buyer cannot even express `verify_agent` on the wire. Production's entire provenance
   surface is one advisory warning (`src/core/tools/creatives/_validation.py:144-175`).

→ `@storyboard-v3.1` is unjustified. Retag **`@schema-v3.1`** (the behaviour is still anchored
in the 3.1.1 JSON schemas — `PROVENANCE_CLAIM_CONTRADICTED` is a real enum member — it is just
not on our graded conformance path). Keep the opaque `@T-UC-006-…` id tag (referenced from
`docs/test-obligations/bdd-traceability.yaml:4831`).

**Separately: the scenario is dormant today.** `tests/bdd/conftest.py:3362-3378` routes UC-006
and `pytest.xfail("UC-006 harness not yet wired for non-account scenarios")` for every scenario
not tagged `@account`, `@creative-invariant`, or `@BR-RULE-034`. I confirmed by execution: all
36 UC-006 provenance scenarios (partition, boundary, BR-RULE-094 INV-1..5, and this one) report
`XFAIL` — including the ones that look green in the feature file. My replacement adds
`@creative-invariant` so it actually runs.

---

## 2. Real binding at 3.1.1

**Correct path (both copies byte-identical):**

- `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_truth_of_claim.yaml`
- `/Users/konst/projects/adcp/dist/compliance/3.1.1/domains/media-buy/scenarios/provenance_truth_of_claim.yaml`

`id: media_buy_seller/provenance_truth_of_claim` (line 1), phase `reject_contradicted_claim`
(line 126), step `sync_creatives_contradicted` (line 145).

**Graded `validations:` block — verbatim, lines 195-223:**

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_value
            path: "creatives[0].action"
            value: "failed"
            description: "Per-creative action is failed when verifier contradicts the claim"
          - check: field_value
            path: "creatives[0].errors[0].code"
            value: "PROVENANCE_CLAIM_CONTRADICTED"
            description: "Per-creative error code is PROVENANCE_CLAIM_CONTRADICTED"
          - check: field_present
            path: "creatives[0].errors[0].details.agent_url"
            description: "error.details carries the verifier's agent_url for audit"
          - check: field_present
            path: "creatives[0].errors[0].details.feature_id"
            description: "error.details carries the queried feature_id"
          - check: field_value
            path: "creatives[0].errors[0].details.claimed_value"
            value: "digital_capture"
            description: "error.details carries the buyer's claimed digital_source_type"
          - check: field_value
            path: "creatives[0].errors[0].details.observed_value"
            value: true
            description: "error.details carries the verifier's observed ai_generated value"
          - check: field_value
            path: "context.correlation_id"
            value: "provenance_truth_of_claim--reject_contradicted"
            description: "Context correlation_id returned unchanged on rejection"
```

So the behaviour **is** graded *inside* the scenario file — it is the scenario file itself that
nobody requires. Note also that `confidence` is named in the prose allowlist but is **not**
graded (no `check:` for `details.confidence`), and the "MUST NOT carry detail_url" half of the
contract is **prose only** (`narrative`, lines 137-142) — there is no negative `check:`.

**What the current footer points at (both defects present):**

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/creative/index.yaml
```

- `ref=v3.1-04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin → re-pin to `v3.1.1`.
- `path=…/protocols/creative/index.yaml` is wrong. `creative/index.yaml` is the creative-lifecycle
  baseline (sync display / list / preview); it contains no provenance phase at all.

**The off-by-one is proven here too, in the opposite direction.** The *preceding* scenario
(`@T-UC-006-storyboard-provenance-corrected-acceptance`, feature line 1575) carries
`path=…/provenance_truth_of_claim.yaml` — MY storyboard — while it actually belongs to
`provenance_enforcement.yaml` phase 6 `accept_with_disclosure` (line 438 of that file; the file's
six phases are `discover_requirement`, `reject_no_provenance`, `reject_missing_digital_source_type`,
`reject_off_list_verifier`, `reject_missing_disclosure`, `accept_with_disclosure`). The footers in
this block are shifted by one scenario; mine fell off the end and got the enclosing index instead.

**Tier:** `protocols/media-buy/` (mirrored under `domains/media-buy/`) — the media-buy protocol
tier, which we DO declare. It is not a `specialisms/` scenario. The disqualifier is orphan status
plus the `has_creative_library` capability, not the tier.

---

## 3. Schema constraints at 3.1.1

**(a) `PROVENANCE_CLAIM_CONTRADICTED` exists.** `static/schemas/source/enums/error-code.json`
(92 members) includes all six `PROVENANCE_*` codes. `enumDescriptions.PROVENANCE_CLAIM_CONTRADICTED`,
verbatim:

> Seller invoked a governance agent from `creative_policy.accepted_verifiers` via
> `get_creative_features` and the verifier's result contradicts the buyer's provenance claim -
> e.g., buyer claims `digital_source_type: digital_capture` but the AI-detection feature returns
> `ai_generated: true` above the seller's confidence threshold. Distinct from the
> `PROVENANCE_*_MISSING` family (structural absence) by being an active refutation.
> `error.details` SHOULD be limited to the audit-safe allowlist
> `{ agent_url, feature_id, claimed_value, observed_value, confidence }`; sellers MUST NOT
> forward arbitrary verifier extension fields, `detail_url`, or any verifier response shape that
> may carry cross-tenant or PII data. […] Recovery: correctable - buyer revises the provenance
> claim to match reality (or replaces the creative); auto-retry without correction will not pass.

Note the strength: the allowlist is **SHOULD**, the no-forwarding rule is **MUST NOT**. The
scenario's Then "the error details should NOT carry detail_url or verifier extension fields" is
the MUST NOT half and is correctly stated — it is simply ungraded by any storyboard `check:`.

**(b) The seller, not the buyer, is the verifier-of-record.**
`static/schemas/source/core/creative-policy.json` → `accepted_verifiers`:

> Governance agents the seller operates, has allowlisted, or otherwise trusts to verify
> provenance claims via `get_creative_features`. […] Sellers MUST reject `sync_creatives`
> submissions whose `verify_agent.agent_url` does not match any entry here with
> `PROVENANCE_VERIFIER_NOT_ACCEPTED`. The seller is the verifier-of-record: it is the seller,
> not the buyer, that decides which agent it will call.

`items.required: ["agent_url"]`, `agent_url` `pattern: "^https://"`, `additionalProperties: false`.
`creative_policy.properties` at 3.1.1 =
`[co_branding, landing_page, templates_available, provenance_required, provenance_requirements, accepted_verifiers]`.
`provenance_requirements` **does** exist (contra any assumption that the sibling scenarios invented it),
with `require_digital_source_type` / `require_disclosure_metadata` / `require_embedded_provenance`,
and its description names `PROVENANCE_CLAIM_CONTRADICTED` explicitly:

> a creative whose provenance claim is contradicted by an independent verification
> (`get_creative_features` against a governance agent the seller operates or has allowlisted via
> `accepted_verifiers`) is rejected with `PROVENANCE_CLAIM_CONTRADICTED`. This is the
> structural-rejection surface; the truth-of-claim surface lives in `get_creative_features`.

**(c) `digital_source_type` enum — `static/schemas/source/enums/digital-source-type.json`:**

```json
["digital_capture", "digital_creation", "trained_algorithmic_media",
 "composite_with_trained_algorithmic_media", "algorithmic_media", "composite_capture",
 "composite_synthetic", "human_edits", "data_driven_media"]
```

**(d) `embedded_provenance[].verify_agent` — `static/schemas/source/core/provenance.json`:**

> Buyer's representation that this embedding can be verified by a governance agent on the
> seller's `creative_policy.accepted_verifiers` list. The `agent_url` MUST match (canonicalized)
> one of the seller's published `accepted_verifiers[].agent_url` entries […] This is
> buyer-supplied evidence, not buyer-driven routing — the seller is the verifier-of-record.

**(e) Per-creative result shape — `static/schemas/source/creative/sync-creatives-response.json`:**
`creatives[].required: ["creative_id", "action"]`; `errors` items `$ref core/error.json`
("only present when action='failed'"); and a normative conditional:

```json
{"if": {"properties": {"action": {"enum": ["failed", "deleted"]}}, "required": ["action"]},
 "then": {"not": {"required": ["status"]}}}
```

i.e. **`status` MUST be absent when `action` is `failed`**. `enums/creative-action.json` =
`["created", "updated", "unchanged", "failed", "deleted"]`.

**(f) Error object — `static/schemas/source/core/error.json`:** `required: ["code", "message"]`;
`details` is `type: object, additionalProperties: true`; `recovery` enum
`["transient", "correctable", "terminal"]` ("Senders SHOULD populate `recovery` on every error
from 3.1 onward").

**(g) Envelope — `static/schemas/source/core/protocol-envelope.json`,** `allOf`-ed into
sync-creatives-response:

> The `status` field is REQUIRED on every task response envelope […] Agents shipping responses
> without a top-level `status` are non-conformant regardless of whether the task body schema
> would otherwise validate.

(Known gap — see brief; not re-filed.)

---

## 4. Conflicts

**Schema vs storyboard.** No direct contradiction on the graded checks. Two schema-wins notes:

- The storyboard grades `creatives[0].errors[0].details.observed_value == true` and
  `claimed_value == "digital_capture"`, but `core/error.json` types `details` as a free-form
  object with `additionalProperties: true` — it defines no `claimed_value`/`observed_value`
  properties at all. The **schema is authoritative on shape** (free-form object); the storyboard's
  key names are a storyboard-fixture convention, not a schema mandate. A conformance run would
  grade them, but a schema validator would not. Worth knowing before anyone treats those key
  names as normative.
- `confidence` appears in the error-code allowlist prose and in the scenario's Then, but there is
  **no** graded `check:` for it. The scenario over-claims relative to what is graded.

**What the current scenario gets wrong:**

1. **Stale `@source` ref** (`v3.1-04f59d2d5`, older than our 3.1.1 pin).
2. **Wrong `@source` path** (`protocols/creative/index.yaml` — a file with no provenance phase).
3. **`@storyboard-v3.1` is unjustified** — orphan scenario + undeclared `has_creative_library`.
4. **Asserts behaviour production cannot produce.** Every Then is red-by-construction: no
   `PROVENANCE_*` code is emitted anywhere in `src/`, there is no verifier call, and
   `Provenance` has no `embedded_provenance` field to carry `verify_agent`.
5. **The `When` step is not a buyer action.** "When the seller invokes the verifier against the
   creative manifest" describes seller-internal behaviour. Every other UC-006 scenario's `When`
   is a buyer request; this one cannot be dispatched through the four transports at all.
6. **Vacuous by omission.** "the error details should NOT carry detail_url or verifier extension
   fields" has no bound on "extension fields" — unimplementable as a concrete comparison.
7. **Dormant.** xfails at `tests/bdd/conftest.py:3378` before any step runs.

**What the replacement asserts instead.** The truthful, verifiable 3.1.1-anchored statement about
this seller: it is a **pass-through** on provenance — it stores the buyer's declared
`digital_source_type` unchanged, never refutes it, and never emits a per-creative error, because
it runs no verifier. That is the honest baseline; the refutation contract becomes ticket material.

---

## 5. Proposed Gherkin

Replaces feature lines **1591-1610** (tag line through the `@source` footer).
**Verified green on mcp / a2a / rest** — I ran this exact step chain via a throwaway probe module
(`21 passed`), then deleted the probe. No file in `salesagent-sbsweep` was modified.

```gherkin
  @T-UC-006-storyboard-provenance-claim-contradicted @schema-v3.1 @v3-1 @provenance @truth-of-claim @creative-invariant
  Scenario Outline: Buyer-declared digital_source_type is stored as declared -- this seller runs no verifier (<claim>)
    Given the Buyer is authenticated with a valid principal_id
    And the tenant has a product with creative_policy.provenance_required = true
    And a creative with provenance declaring digital_source_type "<claim>"
    When the Buyer Agent syncs the creative
    Then the response should include the creative with action "created"
    And the per-creative result should carry no errors
    And no provenance warning should be generated
    And the stored creative provenance digital_source_type should be "<claim>"
    And the stored creative status should be "pending_review"

    # AdCP 3.1.1 enums/digital-source-type.json publishes nine values. This table carries only
    # the six our DigitalSourceType enum accepts; the other three
    # (trained_algorithmic_media, composite_with_trained_algorithmic_media, data_driven_media)
    # are rejected with action="failed" by src/core/schemas/creative.py:64-79 -- see #<enum-drift>.
    Examples: digital_source_type claims accepted at 3.1.1 and by this seller
      | claim               |
      | digital_capture     |
      | digital_creation    |
      | algorithmic_media   |
      | composite_capture   |
      | composite_synthetic |
      | human_edits         |

    # AdCP 3.1.1 grades PROVENANCE_CLAIM_CONTRADICTED in
    # protocols/media-buy/scenarios/provenance_truth_of_claim.yaml, phase reject_contradicted_claim,
    # step sync_creatives_contradicted (validations at lines 195-223): the seller calls an on-list
    # governance agent via get_creative_features and rejects the per-creative entry when the
    # verifier refutes the buyer's claim. That scenario is an ORPHAN at 3.1.1 -- no index anywhere
    # under dist/compliance/3.1.1/ lists media_buy_seller/provenance_truth_of_claim in
    # requires_scenarios -- and it gates on agent.capabilities: [has_creative_library], which we
    # do not declare (capabilities.py declares supported_protocols=[media_buy],
    # specialisms=[sales_non_guaranteed]). Hence @schema-v3.1, not @storyboard-v3.1.
    #
    # This seller is a provenance PASS-THROUGH: no accepted_verifiers are published, no
    # get_creative_features client exists, and Provenance carries no embedded_provenance field,
    # so verify_agent cannot even reach us. The buyer's claim is stored verbatim and routed to
    # human review -- no machine refutation. Wiring the refutation contract is #<truth-of-claim>.
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_truth_of_claim.yaml phase=reject_contradicted_claim step=sync_creatives_contradicted
```

Notes for whoever applies this:

- `@creative-invariant` is what lifts the scenario out of the UC-006 dormant lane
  (`tests/bdd/conftest.py:3364`). It is an honest fit — the conftest comment describes that lane
  as "success-variant response invariants", which is exactly what this asserts. Do **not** add
  `@provenance` to the conftest allow-set: that would un-dormant ~30 other UC-006 provenance
  scenarios, several of which are red.
- Replace `#<enum-drift>` and `#<truth-of-claim>` with the GitHub issue numbers filed from §7.
- The `Examples:` table is deliberately the intersection of the 3.1.1 enum and our enum. Do not
  add the three drifted values to make a point — that would pin a bug into the baseline.

---

## 6. Step inventory

**Existing — reused unchanged (all in `tests/bdd/steps/domain/uc006_sync_creatives.py` unless noted):**

| Step | Location |
|---|---|
| `Given the Buyer is authenticated with a valid principal_id` | `tests/bdd/steps/generic/given_auth.py` |
| `Given the tenant has a product with creative_policy.provenance_required = true` | `uc006_sync_creatives.py:2754` |
| `Given a creative with provenance declaring digital_source_type "{source_type}"` | `uc006_sync_creatives.py:3684` |
| `When the Buyer Agent syncs the creative` | `uc006_sync_creatives.py:253` |
| `Then the response should include the creative with action "{action}"` | `uc006_sync_creatives.py:2659` |
| `Then no provenance warning should be generated` | `uc006_sync_creatives.py:3819` |

**New — 2 steps, both concrete-value comparisons (no truthiness, no existence checks):**

```python
@then("the per-creative result should carry no errors")
def then_per_creative_no_errors(ctx: dict) -> None:
    """Assert the first SyncCreativeResult carries an empty errors array.

    3.1.1 creative/sync-creatives-response.json types creatives[].errors as
    "only present when action='failed'" — an accepted creative must carry none.
    """
    result = _get_sync_creative_result(ctx)
    errors = result.errors or []
    assert errors == [], f"Expected no per-creative errors on an accepted creative, got {errors}"


@then(parsers.parse('the stored creative provenance digital_source_type should be "{claim}"'))
def then_stored_provenance_source_type(ctx: dict, claim: str) -> None:
    """Assert the buyer's declared claim is persisted verbatim (pass-through, no refutation)."""
    creative = _get_creative_from_db(ctx)
    provenance = (creative.data or {}).get("provenance") or {}
    assert provenance.get("digital_source_type") == claim, (
        f"Expected stored digital_source_type '{claim}', got {provenance!r}"
    )


@then(parsers.parse('the stored creative status should be "{status}"'))
def then_stored_creative_status(ctx: dict, status: str) -> None:
    """Assert the persisted creative status (require-human approval routes to pending_review)."""
    creative = _get_creative_from_db(ctx)
    assert creative.status == status, f"Expected creative status '{status}', got '{creative.status}'"
```

(Three definitions; `the stored creative status should be` is the third. I list two "new
behaviours" because the status step is a generalisation of the existing
`then("the creative should be flagged for review")` at `:3839`, which hard-codes
`pending_review` and whose docstring wrongly attributes the status to *missing* provenance.
Prefer the parameterised step here; the older one can stay for its existing callers.)

Guard compliance: each body compares a value (`== []`, `== claim`, `== status`), so
`test_architecture_bdd_no_trivial_assertions.py` and `..._no_pass_steps.py` are satisfied; no
`ctx.get("env")` / `hasattr(env, …)` so `..._no_silent_env.py` is satisfied; bodies are distinct
so `..._no_duplicate_steps.py` is satisfied.

---

## 7. TICKET MATERIAL

**T1 — `DigitalSourceType` enum has drifted from AdCP 3.1.1; three spec-valid values are rejected with `action: "failed"`.**
`src/core/schemas/creative.py:64-79` defines
`[digital_capture, digital_creation, composite_capture, composite_synthetic,
composite_with_trained_model, trained_algorithmic_model, algorithmic_media, human_edits,
minor_human_edits]`. AdCP 3.1.1 `static/schemas/source/enums/digital-source-type.json` defines
`[digital_capture, digital_creation, trained_algorithmic_media,
composite_with_trained_algorithmic_media, algorithmic_media, composite_capture,
composite_synthetic, human_edits, data_driven_media]`.
Spec-only (we reject): `trained_algorithmic_media`, `composite_with_trained_algorithmic_media`,
`data_driven_media`. Ours-only (not in the spec): `composite_with_trained_model`,
`trained_algorithmic_model`, `minor_human_edits`.
**Reproduced by execution:** a `sync_creatives` carrying
`provenance.digital_source_type = "trained_algorithmic_media"` returns per-creative
`action: "failed"` on mcp, a2a and rest. This is the single most-used AI-disclosure value in the
enum — an EU AI Act Art. 50 workflow submitting a correct claim is rejected today.
Fix: replace the hand-rolled `StrEnum` with the SDK/`$ref`-backed enum (Pattern #1 — extend the
library type, do not duplicate it).

**T2 — `Provenance` does not extend the library type and diverges structurally from `core/provenance.json`.**
`src/core/schemas/creative.py:82-120` derives from `SalesAgentBaseModel`, not from the adcp
library `Provenance` (Pattern #1 / `test_architecture_schema_inheritance.py`). Field-level
divergence against 3.1.1 `static/schemas/source/core/provenance.json`:
- `embedded_provenance` — **absent entirely**. Spec: array, `minItems: 1`, items carry
  `method`/`standard`/`provider`/`verify_agent`. This is the field the whole truth-of-claim
  contract hangs on; without it a buyer cannot present `verify_agent` to us at all.
- `human_oversight` — ours `bool | None`; spec: string enum
  `[none, prompt_only, selected, edited, directed]`.
- `declared_by` — ours `str | None`; spec: object with `required: ["role"]`,
  `role` enum `[creator, advertiser, agency, platform, tool]`.
- `disclosure` — ours `str | None`; spec: object (with `required` boolean and `jurisdictions`).
- `c2pa` — ours `str | None`; spec: object with `required: ["manifest_url"]`.
- `verification` — ours only; not in the spec.
- `watermarks`, `declared_at` — spec only.
A buyer sending a spec-shaped `provenance` object is rejected on at least four of these fields.

**T3 — `creative_policy` is stored and echoed as an opaque dict; `accepted_verifiers` and `provenance_requirements` are never published or read.**
`src/core/database/models.py:249` types `creative_policy` as an untyped `JSONType` dict;
`src/core/product_conversion.py:450-451` passes it straight through;
`src/services/default_products.py:35,57,77,100,119,151` seed only
`{co_branding, landing_page, templates_available}`. AdCP 3.1.1
`static/schemas/source/core/creative-policy.json` defines six properties including
`accepted_verifiers` (`minItems: 1`, `agent_url` `pattern: "^https://"`,
`additionalProperties: false`) and `provenance_requirements`
(`require_digital_source_type` / `require_disclosure_metadata` / `require_embedded_provenance`).
Because we never publish `accepted_verifiers`, the storyboard's phase-1 gate
(`field_present: products[0].creative_policy.accepted_verifiers[0].agent_url`,
`provenance_truth_of_claim.yaml:118-120`) fails at `get_products` before `sync_creatives` is
ever reached. Model `creative_policy` as a typed schema extending the library type.

**T4 — `provenance_required: true` produces an advisory warning, never a `PROVENANCE_REQUIRED` rejection.**
`src/core/tools/creatives/_validation.py:144-175` returns a warning **string** when
`creative.provenance is None`; `src/core/tools/creatives/_sync.py:180-184,275-278,328-329`
appends it to `warnings[]` and leaves `action` at `created`/`updated`. AdCP 3.1.1
`enums/error-code.json` `PROVENANCE_REQUIRED`: *"Seller's `creative_policy.provenance_required`
is true and the submitted creative has no `provenance` object … `error.field` MUST point at the
path where provenance was expected."* Graded at
`protocols/media-buy/scenarios/provenance_enforcement.yaml` phase `reject_no_provenance`
(line 142). Also note the policy is applied **tenant-wide**: `_sync.py:139-142` takes
`provenance_policies[0]` from *any* product with `provenance_required`, so the per-product
policy binding the spec assumes does not exist. (Sibling scenarios
`@T-UC-006-storyboard-provenance-required-rejection`, `…-digital-source-type-missing`,
`…-disclosure-missing` are all blocked on this — coordinate with those agents' writeups.)

**T5 — No `get_creative_features` client; the truth-of-claim surface does not exist.**
`grep -rn "get_creative_features\|accepted_verifiers\|verify_agent" src/` finds only
`verify_agent_authorization` (an unrelated adagents.json property-authorization helper at
`src/services/property_verification_service.py:16,107`). 3.1.1 mandates the seller be the
verifier-of-record (`core/creative-policy.json` → `accepted_verifiers`: *"The seller is the
verifier-of-record: it is the seller, not the buyer, that decides which agent it will call"*)
and defines the call contract at `static/schemas/source/creative/get-creative-features-request.json`
/ `-response.json` + `creative/creative-feature-result.json`. Implementing this is what would
make `PROVENANCE_CLAIM_CONTRADICTED` emittable, with `error.details` bounded to
`{agent_url, feature_id, claimed_value, observed_value, confidence}` and **MUST NOT** carry
`detail_url` or verifier extension fields (cross-tenant trust boundary,
`enums/error-code.json` → `PROVENANCE_CLAIM_CONTRADICTED`). Scope note: this is only worth doing
if we also intend to declare the creative protocol / `has_creative_library` — today the storyboard
is an orphan and nothing grades it.

**T6 — `then("the creative should be flagged for review")` mis-attributes its assertion.**
`tests/bdd/steps/domain/uc006_sync_creatives.py:3839-3846` asserts `creative.status ==
"pending_review"` with the docstring *"flagged for review due to missing provenance"*. The status
actually comes from `approval_mode = require-human` (`src/core/tools/creatives/_sync.py:126`) and
holds identically when provenance is **present** — I verified it passes on all six accepted
claims. The step tests the approval-mode default, not provenance enforcement. Retitle, or replace
its callers with the parameterised `the stored creative status should be "{status}"`.

**T7 — `given_creative_with_provenance_source_type` is not e2e-transport-safe and hard-codes one `creative_id`.**
`tests/bdd/steps/domain/uc006_sync_creatives.py:3684-3700` hard-codes
`format_id = "display_300x250"` + `env.DEFAULT_AGENT_URL` instead of calling `_format_payload(ctx, env)`
(`:44-66`), which is the e2e-aware helper every sibling given uses; and it hard-codes
`creative_id = "creative-provenance-source-001"`, so two rows of a `Scenario Outline` collide
if the DB scope is ever widened past per-test. Low-risk fix, prerequisite for ever running this
scenario on `e2e_rest`.

---

## 8. Risks

- **I did not verify on `e2e_rest`.** The probe parametrised `[mcp, a2a, rest]` only — that is the
  full in-process matrix for UC-006 today. See T7 for why the reused given would need a fix first.
- **`@creative-invariant` is a routing decision, not a spec decision.** It is the only existing
  tag that lifts a UC-006 scenario out of the dormant lane without touching conftest. If the team
  prefers an explicit lane, add a new tag (e.g. `@provenance-passthrough`) to the marker set at
  `tests/bdd/conftest.py:3364` — one line, no collateral, since only this scenario would carry it.
  Do not widen the set to `@provenance`.
- **"Orphan scenario" is inferred from `requires_scenarios` semantics**
  (`universal/storyboard-schema.yaml:64-66`) plus an exhaustive grep of
  `dist/compliance/3.1.1/`. I could not execute a conformance runner to confirm the runner really
  skips unreferenced scenario files. If the runner in fact enumerates every file under a declared
  tier, the verdict softens from "orphan + undeclared gate" to "undeclared gate" — the retag to
  `@schema-v3.1` still holds, because `has_creative_library` is undeclared either way.
- **`confidence` and the `detail_url` prohibition are prose-only** even inside the storyboard.
  Anyone implementing T5 should not assume a conformance run will catch a leak.
- **Drift, noted not acted on:** the same orphan status holds at 3.1.2 / 3.1.5 / 3.1.8. We remain
  pinned at 3.1.1.
- **Scratch files:** I created and deleted
  `tests/bdd/features/zz-scratch-provprobe.feature` and `tests/bdd/test_zz_scratch_provprobe.py`
  to run the greenness probe. `git status --porcelain` is clean for `tests/`; no tracked file was
  modified.

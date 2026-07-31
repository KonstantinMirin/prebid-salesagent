# Re-pin: `@T-UC-006-storyboard-provenance-corrected-acceptance`

Scenario: `tests/bdd/features/BR-UC-006-sync-creatives.feature:1575-1590`
Title today: *"Corrected resubmission with disclosure block and on-list verifier is accepted"*

---

## 1. VERDICT

**GRADED** — and the footer's cited path is wrong.

The behaviour is genuinely graded at 3.1.1: `provenance_enforcement.yaml`, phase `accept_with_disclosure`,
carries a real `validations:` block (not prose). It sits in the **`protocols/media-buy/`** tier (mirrored
byte-identically under `domains/media-buy/`), it is **not** specialism-gated, and its `required_tools`
(`get_products`, `sync_creatives`) are both advertised by us. We declare
`supported_protocols=[SupportedProtocol.media_buy]` (`src/core/tools/capabilities.py:271`), so this scenario
**is on our conformance path**. `@storyboard-v3.1` is justified and stays.

Two separate defects, both confirmed:

- **Footer defect (the off-by-one):** the footer cites `provenance_truth_of_claim.yaml`. That is the *next*
  scenario's storyboard — the file that grades `PROVENANCE_CLAIM_CONTRADICTED`, which is explicitly declared
  out of scope by `provenance_enforcement.yaml:31-35`. The scenario's own prose two lines above the footer
  already names the truth (`# provenance_enforcement Phase 6: …`). Re-pin to
  `provenance_enforcement.yaml`, `ref=v3.1.1`.
- **Substance defect (the serious one):** the scenario's titled subject — *disclosure block* + *on-list
  `verify_agent`* — **cannot pass against current production**. Both fields are rejected by our own
  `src/core/schemas/creative.py::Provenance` before any policy logic runs. Proven by execution below. The
  scenario currently survives only because it is **dormant**: none of its five step phrasings exist in
  `tests/bdd/steps/`, so `tests/bdd/conftest.py:85-101` auto-xfails it as `StepDefinitionNotFoundError`. It
  has never asserted anything.

---

## 2. Real binding at 3.1.1

**Correct file:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml`
**Phase:** `accept_with_disclosure` (line 438) → **step:** `sync_creatives_with_disclosure` (line 447)
**Graded block:** lines **507-517**
**Source path for the footer:** `static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml`
(confirmed present at `v3.1.1` = `467fd93d7`)

Graded `validations:` verbatim (lines 507-517):

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_value
            path: "creatives[0].action"
            allowed_values: ["created", "updated"]
            description: "Per-creative action is created or updated — not failed. Tighter than field_present, which would silently pass on action: failed"
          - check: field_value
            path: "context.correlation_id"
            value: "provenance_enforcement--accept_with_disclosure"
            description: "Context correlation_id returned unchanged"
```

The `expected:` prose on the same step (lines 454-457) additionally says *"a status from creative-status
(processing, pending_review, or approved)"* — **that is narrative, not graded.** No `validations:` entry
checks `creatives[0].status`. Do not assert it as a storyboard obligation (and see §4 — we could not pass it
anyway).

The submitted manifest that this phase grades (lines 481-503) carries `digital_source_type:
trained_algorithmic_media`, a full `disclosure` object with two jurisdictions, `declared_by: {role: agency}`,
and `embedded_provenance[0].verify_agent.agent_url:
https://governance.encypher.seller.example` drawn from `creative_policy.accepted_verifiers`
(fixture, lines 72-75).

**What the current footer wrongly points at:** `provenance_truth_of_claim.yaml`. Wrong scenario entirely —
it grades the verifier-invocation contract, which `provenance_enforcement.yaml:31-35` states is "a separate
scenario; this one tests only the structural surface". Also `ref=v3.1-04f59d2d5 commit=04f59d2d5`, an
ancestor of beta.3 and therefore older than our own pin.

**Tier:** `protocols/` (id `media-buy`, `index.json`). Not in the media-buy baseline's `requires_scenarios`
(`protocols/media-buy/index.yaml:9-23`) — it is a free-standing protocol-tier scenario, and nothing under
`specialisms/` references it. So there is **no capability gate to fail**: it is graded for us on the strength
of `supported_protocols=[media_buy]` alone.

---

## 3. Schema constraints at 3.1.1

All quotes read via `git show v3.1.1:<path>` in `/Users/konst/projects/adcp`.

### `static/schemas/source/creative/sync-creatives-response.json`

Success branch, per-creative item:

```json
"required": ["creative_id", "action"],
"additionalProperties": true,
"allOf": [
  { "if":  { "properties": { "action": { "enum": ["failed", "deleted"] } }, "required": ["action"] },
    "then": { "not": { "required": ["status"] } } }
]
```

`action` `$ref`s `enums/creative-action.json`:

```json
"enum": ["created", "updated", "unchanged", "failed", "deleted"]
```

Note `unchanged` is a legal wire value that the storyboard's `allowed_values: ["created","updated"]`
**excludes**. Our production cannot emit it on this path (see §4), but the Gherkin must still pin the exact
value rather than "not failed".

`status` `$ref`s `enums/creative-status.json` (`processing | pending_review | approved | suspended |
rejected | archived`) and its description is normative on omission:

> "MUST be omitted when action is failed or deleted … Omit entirely when the seller has no review lifecycle at all."

The whole response `allOf`s `core/protocol-envelope.json`, which is:

```json
"required": ["status"]
```

> "The `status` field is REQUIRED on every task response envelope… Agents shipping responses without a
> top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate."

### `static/schemas/source/core/creative-policy.json`

```json
"provenance_requirements": {
  "description": "… Sellers that publish a requirement here MUST enforce it on creative submission: a `sync_creatives` request that omits a required field is rejected with the corresponding `PROVENANCE_*` error code …",
  "properties": {
    "require_digital_source_type": { … "rejected with `PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING`" },
    "require_disclosure_metadata": { … "Submissions that omit `disclosure.required` are rejected with `PROVENANCE_DISCLOSURE_MISSING`." },
    "require_embedded_provenance": { … "rejected with `PROVENANCE_EMBEDDED_MISSING`" }
  }
}
```

```json
"accepted_verifiers": {
  "description": "… Sellers MUST reject `sync_creatives` submissions whose `verify_agent.agent_url` does not match any entry here with `PROVENANCE_VERIFIER_NOT_ACCEPTED`. …",
  "minItems": 1,
  "items": { "required": ["agent_url"], "additionalProperties": false,
             "properties": { "agent_url": { "format": "uri", "pattern": "^https://" }, "feature_id": {…}, "providers": {…} } }
}
```

### `static/schemas/source/core/provenance.json`

```json
"disclosure": {
  "type": "object",
  "properties": { "required": { "type": "boolean" },
                  "jurisdictions": { "type": "array", "minItems": 1,
                    "items": { "required": ["country", "regulation"] } } },
  "required": ["required"]
}
```

```json
"embedded_provenance": {
  "type": "array", "minItems": 1,
  "items": { "required": ["method", "provider"],
    "properties": { "verify_agent": {
      "properties": { "agent_url": { "format": "uri", "pattern": "^https://" }, "feature_id": {"type":"string"} },
      "required": ["agent_url"], "additionalProperties": false } } }
}
```

```json
"declared_by": { "type": "object",
  "properties": { "agent_url": {"format":"uri"},
                  "role": { "enum": ["creator","advertiser","agency","platform","tool"] } },
  "required": ["role"] }
```

```json
"human_oversight": { "type": "string",
  "enum": ["none","prompt_only","selected","edited","directed"] }
```

### `static/schemas/source/enums/digital-source-type.json`

```json
"enum": ["digital_capture", "digital_creation", "trained_algorithmic_media",
         "composite_with_trained_algorithmic_media", "algorithmic_media",
         "composite_capture", "composite_synthetic", "human_edits", "data_driven_media"]
```

---

## 4. Conflicts — what the scenario gets wrong, and what production cannot do

### 4a. Schema vs storyboard

No conflict on this step. The storyboard's `allowed_values: ["created","updated"]` is a legal narrowing of
the 5-value `creative-action` enum, and the fixture policy validates against `creative-policy.json`
(verified: our local `CreativePolicy` constructs it cleanly, including `provenance_requirements` and
`accepted_verifiers`, because `adcp==6.6.0`'s `CreativePolicy` already carries all three fields).

The one place to state the precedence rule explicitly: the storyboard's `expected:` prose demands a
`status` from creative-status, but the **schema** makes `status` conditionally forbidden (on
`failed`/`deleted`) and explicitly optional otherwise. **Schema wins**: `status` is not assertable here, and
the storyboard does not grade it either.

### 4b. Our production rejects the storyboard's own manifest — PROVEN

`_validate_creative_input` (`src/core/tools/creatives/_validation.py:26-88`) accepts the library
`CreativeAsset` (3.1.1-shaped, fine), dumps `provenance` to a dict, then re-validates it through our
**local, hand-rolled, non-inheriting** `src/core/schemas/creative.py::Provenance` (line 82) under
`extra="forbid"`. Feeding it the storyboard's exact phase-6 provenance object:

```
LOCAL Creative REJECTED — errors:
   ('provenance', 'digital_source_type') | enum          | Input should be 'digital_capture', 'digital_creation', 'composite_capture', …
   ('provenance', 'declared_by')         | string_type   | Input should be a valid string
   ('provenance', 'disclosure')          | string_type   | Input should be a valid string
   ('provenance', 'embedded_provenance') | extra_forbidden | Extra inputs are not permitted
```

Four independent rejections. The `except Exception` at `src/core/tools/creatives/_sync.py:356-363` converts
that to a per-creative `action: "failed"` carrying a raw pydantic message — the **exact inverse** of the
graded assertion `creatives[0].action ∈ ["created","updated"]`.

Field-by-field divergence of `src/core/schemas/creative.py::Provenance` from `core/provenance.json`:

| field | 3.1.1 schema | ours (`creative.py`) | effect |
|---|---|---|---|
| `digital_source_type` | optional, 9-value enum incl. `trained_algorithmic_media`, `composite_with_trained_algorithmic_media`, `data_driven_media` | **required**; enum has `trained_algorithmic_model`, `composite_with_trained_model`, `minor_human_edits` — three names that do not exist in the spec, and lacks `data_driven_media` | storyboard's value rejected |
| `disclosure` | object, `required: ["required"]` | `str \| None` | rejected |
| `declared_by` | object, `required: ["role"]` | `str \| None` | rejected |
| `human_oversight` | string enum (5 values) | `bool \| None` | rejected |
| `c2pa` | object `{manifest_url}` | `str \| None` | rejected |
| `verification` | array | `dict \| None` | rejected |
| `embedded_provenance`, `watermarks`, `declared_at`, `ext` | present | **absent** + `extra="forbid"` | rejected |

Executed probe of what survives **both** models:

```
minimal dst only        -> BOTH OK
dst+ai_tool             -> BOTH OK
dst+created_time        -> BOTH OK
+human_oversight edited -> LOCAL REJECT (bool_parsing)
+declared_by obj        -> LOCAL REJECT (string_type)
+disclosure obj         -> LOCAL REJECT (string_type)
+embedded_provenance    -> LOCAL REJECT (extra_forbidden)
storyboard dst value    -> LOCAL REJECT (enum)
```

So the green surface is exactly `{digital_source_type ∈ (ours ∩ spec), ai_tool, created_time}`.
**A green Gherkin cannot contain a disclosure block or a `verify_agent`.**

### 4c. What the scenario asserts vacuously today

- `Then the per-creative result should report action "created" or "updated"` — dormant; no step exists.
- `And the per-creative result should NOT report action "failed"` — a **restatement** of the line above
  (created/updated already excludes failed). Even if implemented it adds nothing, and "NOT report X" is the
  negative-existence shape the trivial-assertion guard exists to stop.
- No assertion on `creative_id`, on result cardinality, on per-creative `errors`, or on anything that would
  fail if the disclosure block were silently dropped. The scenario's title claims disclosure + verifier; the
  body checks neither.

### 4d. No enforcement exists at all

Production's entire provenance surface is `check_provenance_required`
(`src/core/tools/creatives/_validation.py:144-175`): if a product has `provenance_required` truthy and the
creative has no `provenance`, it returns a **warning string** that is appended to `result.warnings`
(`_sync.py:276-277, 329-330`) and flags the creative for review. It never fails the item, never reads
`provenance_requirements`, never reads `accepted_verifiers`, and emits no `PROVENANCE_*` code anywhere in
`src/`. The policy is also applied tenant-wide from `provenance_policies[0]` (`_sync.py:184`), not resolved
per the product the creative is destined for.

### 4e. Adjacent breakage found while sizing this

The existing fixture `@given("a creative with provenance metadata")`
(`tests/bdd/steps/domain/uc006_sync_creatives.py:2707-2717`) builds
`{"source": …, "model": …, "disclosure": "This creative was generated using AI."}`. Executed against
`adcp==6.6.0`:

```
LIBRARY REJECT: [(('provenance','disclosure'), 'model_type', 'Input should be a valid dictionary or instance of Disclosure')]
```

That payload fails at `CreativeAsset(**creative_data)` (`_sync.py:158`) → `except Exception` →
`action: "failed"`. Every scenario using this Given is therefore asserting against a *failed* sync. I did
**not** reuse it. Ticketed in §7.

---

## 5. Proposed Gherkin — GREEN ONLY

Replaces `tests/bdd/features/BR-UC-006-sync-creatives.feature:1575-1590` in full. The opaque
`@T-UC-006-…` tag is preserved byte-for-byte (`docs/test-obligations/bdd-traceability.yaml:4825` binds to
it). Title changed to match what the body actually asserts — the old title named two things the body never
checked and production cannot do.

```gherkin
  @T-UC-006-storyboard-provenance-corrected-acceptance @storyboard-v3.1 @v3-1 @provenance @acceptance
  Scenario Outline: Corrected resubmission carrying provenance is accepted under a provenance_required policy
    Given the tenant publishes a product whose creative_policy requires provenance and lists one accepted verifier
    And the creative library state for "<creative_id>" is "<prior_state>"
    And the Buyer Agent submits creative "<creative_id>" carrying provenance with digital_source_type "<digital_source_type>"
    When the Buyer Agent syncs the creative
    Then the response is the success variant carrying a creatives array
    And the response does not carry an operation-level errors array
    And the response should carry exactly 1 per-creative result
    And the per-creative result creative_id should be "<creative_id>"
    And the action should be "<action>"
    And the per-creative result should carry no errors
    And the creative should be processed without warning

    Examples: corrected submission lands as created or updated depending on prior library state
      | creative_id                   | prior_state | digital_source_type | action  |
      | acme_disclosure_probe_fresh   | absent      | digital_creation    | created |
      | acme_disclosure_probe_resync  | present     | algorithmic_media   | updated |
      | acme_disclosure_probe_capture | absent      | digital_capture     | created |
      | acme_disclosure_probe_edits   | present     | human_edits         | updated |
    # provenance_enforcement Phase 6 (accept_with_disclosure): the buyer reads the rejection codes from
    # the earlier phases, re-submits, and the per-creative action transitions to created/updated rather
    # than failed. The storyboard grades exactly one thing here — creatives[0].action ∈ [created, updated]
    # (validations, lines 507-517) — plus response_schema and the context.correlation_id echo.
    #
    # SCOPE NOTE (#TBD-provenance-model-rewrite): the storyboard's phase-6 manifest also carries a
    # disclosure block and an on-list embedded_provenance[].verify_agent. Neither is expressible here:
    # src/core/schemas/creative.py::Provenance types `disclosure` as str and has no embedded_provenance
    # field under extra="forbid", so the storyboard's own sample_request is rejected with action=failed.
    # digital_source_type values are restricted to the intersection of our local enum and 3.1.1's
    # digital-source-type enum for the same reason. The disclosure/verifier half of this phase is
    # tracked in the tickets below; adding it here would make the baseline red.
    #
    # The last Then is the anti-vacuity guard: check_provenance_required
    # (src/core/tools/creatives/_validation.py:144) appends a provenance warning whenever a creative
    # arrives with no provenance under a provenance_required policy. Asserting the warning is ABSENT is
    # what fails if the provenance object is dropped between the buyer and the seller.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/provenance_enforcement.yaml phase=accept_with_disclosure step=sync_creatives_with_disclosure
```

Greenness of each row, verified against `src/`:

- `prior_state: present` → `_update_existing_creative` reaches
  `src/core/tools/creatives/_processing.py:449` — `changes.extend(["url","click_url","width","height","duration"])`
  runs **unconditionally** ("In full upsert, consider all fields as changed"), so line 455 always yields
  `"updated"`. `"unchanged"` is unreachable on this path; the `updated` rows are deterministic.
- `prior_state: absent` → `create_result` with `action="created"`.
- Every `digital_source_type` value used is in both our local `DigitalSourceType`
  (`src/core/schemas/creative.py:64-79`) and 3.1.1's `digital-source-type.json`.
- `errors` and `warnings` default to `[]` on `SyncCreativeResult`
  (`src/core/schemas/creative.py`, redeclared with `default_factory=list`); with provenance attached
  `check_provenance_required` returns `None`, so nothing is appended, and no assignments are requested so no
  assignment warnings appear.

Deliberately **not** asserted (each would be red — see §7): the response envelope's top-level `status`; the
per-creative `status`; the `context.correlation_id` echo; `response_schema` validity;
`PROVENANCE_VERIFIER_NOT_ACCEPTED` on an off-list verifier; persistence of the disclosure block.

---

## 6. Step inventory

**Existing — reuse unchanged (all in `tests/bdd/steps/domain/uc006_sync_creatives.py`):**

| phrase | line | note |
|---|---|---|
| `When the Buyer Agent syncs the creative` | 253 | dispatches through all four transports via `dispatch_request` |
| `Then the response is the success variant carrying a creatives array` | 6966 | asserts no operation-level error + `creatives` is a list |
| `And the response does not carry an operation-level errors array` | ~6993 | success-variant discriminator |
| `And the action should be "{expected_action}"` | 6743 | exact string compare on `creatives[0].action` |
| `And the creative should be processed without warning` | ~2848 | asserts zero provenance-substring warnings |

**New — four steps:**

| phrase | kind | what it does |
|---|---|---|
| `Given the tenant publishes a product whose creative_policy requires provenance and lists one accepted verifier` | given | wraps the existing `_setup_product_with_creative_policy(ctx, creative_policy={...})` with the storyboard fixture policy: `provenance_required: true`, `provenance_requirements.{require_digital_source_type, require_disclosure_metadata}: true`, `accepted_verifiers: [{agent_url: "https://governance.encypher.seller.example", feature_id: "encypher.markers_present_v2", providers: ["Encypher"]}]`. Verified to construct cleanly through our local `CreativePolicy`. |
| `Given the creative library state for "{creative_id}" is "{prior_state}"` | given | `absent` → no-op; `present` → seed one `CreativeFactory` row stamped with `ctx["principal"].principal_id` so `creative_repo.get_by_id(creative_id, principal_id)` hits. Factory-based per CLAUDE.md §8 — no `session.add()` in the step body. |
| `Given the Buyer Agent submits creative "{creative_id}" carrying provenance with digital_source_type "{digital_source_type}"` | given | reuses `_build_creative_payload`'s format/asset plumbing but takes an explicit `creative_id` and emits `{"digital_source_type": <param>, "ai_tool": {"name": "DALL-E 3", "provider": "OpenAI"}}`. **Do not reuse the existing `a creative with provenance metadata` fixture** — §4e. |
| `Then the response should carry exactly {count:d} per-creative result` | then | `assert len(response.creatives) == count` |
| `Then the per-creative result creative_id should be "{creative_id}"` | then | `assert response.creatives[0].creative_id == creative_id` |
| `Then the per-creative result should carry no errors` | then | `assert list(response.creatives[0].errors) == []`, message includes the codes found |

(Six rows, four of them genuinely new phrasings plus two thin per-creative assertions; none duplicates an
existing body, so `test_architecture_bdd_no_duplicate_steps.py` stays clean.)

**Deleted phrasings** (dormant, never implemented, nothing else references them):
`Given a creative submission that previously failed with provenance rejection codes`;
`And the Buyer Agent resubmits with a complete disclosure block and an on-list verify_agent from the seller's accepted_verifiers`;
`When the Buyer Agent sends sync_creatives with the corrected manifest`;
`Then the per-creative result should report action "created" or "updated"`;
`And the per-creative result should NOT report action "failed"`.

Note: `When the Buyer Agent sends sync_creatives` is also undefined and is used by the three sibling
`@provenance` rejection scenarios (feature lines 1537, 1550, 1562) — owned by `sb-uc006-prov-required`,
`sb-uc006-prov-dst`, `sb-uc006-prov-disclosure`. My proposal uses the already-defined
`the Buyer Agent syncs the creative` instead of adding a second alias; the sibling agents should be told to
converge on the same `When`.

---

## 7. TICKET MATERIAL

1. **`src/core/schemas/creative.py::Provenance` is a hand-rolled model that contradicts `core/provenance.json` on seven fields.**
   It subclasses `SalesAgentBaseModel`, not the library `Provenance` — a direct Pattern #1 /
   `test_architecture_schema_inheritance.py` violation. `disclosure` is `str` where the schema says object
   with `required: ["required"]`; `declared_by` is `str` where the schema says object with
   `required: ["role"]`; `human_oversight` is `bool` where the schema says a 5-value string enum; `c2pa` is
   `str` where the schema says `{manifest_url}`; `verification` is `dict` where the schema says array;
   `embedded_provenance`, `watermarks`, `declared_at` and `ext` are absent entirely under `extra="forbid"`.
   Evidence: `src/core/schemas/creative.py:82-120`; rejection reproduced above.
   Mandate: `static/schemas/source/core/provenance.json` @ v3.1.1. Fix = extend
   `adcp.types.generated_poc.core.provenance.Provenance` and delete the local redeclarations.
   **This single ticket is what blocks the storyboard's phase-6 manifest.**

2. **Local `DigitalSourceType` enum invents three values and misses one.**
   `src/core/schemas/creative.py:64-79` declares `trained_algorithmic_model`, `composite_with_trained_model`
   and `minor_human_edits`; 3.1.1's `enums/digital-source-type.json` has `trained_algorithmic_media`,
   `composite_with_trained_algorithmic_media` and `data_driven_media`, and has no `minor_human_edits`. A
   buyer sending any spec-legal value from those three gets `action: "failed"`. Fix = import the SDK enum.

3. **`provenance_requirements` is never read; `provenance_required` is warn-only.**
   `check_provenance_required` (`src/core/tools/creatives/_validation.py:144-175`) returns a warning string
   and nothing else; `_sync.py:276-277,329-330` appends it and flags for review. No `PROVENANCE_*` code
   exists anywhere in `src/`. `core/creative-policy.json` is explicit: *"Sellers that publish a requirement
   here MUST enforce it on creative submission: a `sync_creatives` request that omits a required field is
   rejected with the corresponding `PROVENANCE_*` error code."* Graded by
   `provenance_enforcement.yaml` phases `reject_no_provenance` (188-207),
   `reject_missing_digital_source_type` (261-275), `reject_missing_disclosure` (422-436).

4. **`accepted_verifiers` is never read — the buyer-controlled-URL trust gap is open.**
   No occurrence of `accepted_verifiers` in `src/` (only in the SDK's `CreativePolicy` field list).
   `core/creative-policy.json`: *"Sellers MUST reject `sync_creatives` submissions whose
   `verify_agent.agent_url` does not match any entry here with `PROVENANCE_VERIFIER_NOT_ACCEPTED`"* and
   *"Sellers MUST NOT call this URL until the canonicalized match is confirmed"*
   (`core/provenance.json`, `verify_agent.agent_url`). Graded by `provenance_enforcement.yaml` phase
   `reject_off_list_verifier` (277-363). **There is no BDD scenario for this phase at all** in
   `BR-UC-006-sync-creatives.feature` — the other four phases have one each. Coverage gap plus production
   gap.

5. **`tenant_requires_provenance` resolves the policy tenant-wide from `provenance_policies[0]`.**
   `src/core/tools/creatives/_sync.py:140-146,184` picks the first product in the tenant that has
   `provenance_required` truthy and applies its policy to every creative in the sync, regardless of which
   product the creative targets. `creative_policy` is a per-product field
   (`core/creative-policy.json` — "Creative requirements and restrictions for **a product**"). A tenant with
   two products under different regimes gets the wrong regime applied.

6. **`SyncCreativeResult.status` is inherited but never populated, and serializes as `null` on MCP.**
   Documented in-code at `src/core/schemas/creative.py` ("we inherit but do NOT populate the spec `status`:
   it stays None… on MCP the response goes through `structured_content` → `to_jsonable_python`, which
   BYPASSES the `model_dump` override, so the inherited `status` serializes as null"). `status` `$ref`s
   `enums/creative-status.json`, which is a string enum — `null` is schema-invalid on the MCP wire. Also:
   we *do* run a review lifecycle (workflow steps, `pending_review`), so the schema's "omit entirely when the
   seller has no review lifecycle at all" carve-out does not apply to us — we should be emitting
   `pending_review`/`approved`. The code comment says the null-serialization question is "tracked
   separately"; this ticket is the *population* half.

7. **The `a creative with provenance metadata` BDD fixture builds a payload that `adcp==6.6.0` rejects.**
   `tests/bdd/steps/domain/uc006_sync_creatives.py:2707-2717` emits
   `{"source", "model", "disclosure": <string>}`. `CreativeAsset(**creative_data)` (`_sync.py:158`) raises
   `Input should be a valid dictionary or instance of Disclosure` → `except Exception` (`_sync.py:356`) →
   `action: "failed"`. Every scenario built on this Given is asserting against a failed sync. Fix the fixture
   to the `core/provenance.json` shape (blocked on ticket 1 for the disclosure half) and re-check whatever
   those scenarios were claiming.

8. **Storyboard-graded checks we cannot make, all pre-existing and already known:** no top-level envelope
   `status` (`core/protocol-envelope.json` `required: ["status"]`, and its prose: *"Agents shipping responses
   without a top-level `status` are non-conformant"*); REST drops `context`, so the graded
   `context.correlation_id` echo (`provenance_enforcement.yaml:514-517`) cannot be asserted
   transport-independently (`src/routes/api_v1.py`); `then_response_schema_valid` runs no validator despite
   `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing, so
   `check: response_schema` is ungradable locally; `tests/fixtures/adcp_schemas_pinned/` is vendored at
   `04f59d2d5`, not 3.1.1. Cited here, not re-filed.

9. **The footer defect is mechanical and repo-wide.** This scenario cited the *next* storyboard. Every
   `@source` line in `BR-UC-006-sync-creatives.feature` still reads `ref=v3.1-04f59d2d5 commit=04f59d2d5`,
   an ancestor of beta.3 and therefore older than our own 3.1.1 pin. Worth a lint: the footer's `path=` must
   name a file that exists at the pinned `ref`, and — where the scenario carries a
   `# <storyboard_id>: …` summary line — the two must name the same storyboard.

---

## 8. Risks

- **I did not execute the proposed Gherkin.** No step definitions exist for it yet (it is dormant), so there
  was nothing to run. Greenness is argued from source reads plus four executed probes of the model layer
  (`CreativeAsset`/`Creative` construction, `CreativePolicy` construction, the existing fixture's payload,
  and the intersection of the two `digital_source_type` enums). The action=`created`/`updated` claim rests on
  reading `_processing.py:449-455` and `_sync.py`, not on a run.
- **`the creative should be processed without warning` may be too coarse.** It filters warnings on the
  substring `"provenance"`. If some other code path ever appends a provenance-mentioning warning on the
  success path, the assertion flips red for the wrong reason. A tighter version would compare
  `result.warnings == []`; I kept the existing step to avoid a near-duplicate body, but the swap is cheap.
- **`prior_state: "present"` seeding assumes `CreativeFactory` stamps `tenant_id` + `principal_id` such that
  `creative_repo.get_by_id(creative_id, principal_id)` matches.** I read the repository signature but did not
  run the factory. If the lookup misses, those two rows return `created` instead of `updated` — a visible,
  easily-corrected failure, not a silent pass.
- **Title change.** I renamed the scenario because the old title named a disclosure block and an on-list
  verifier that the body never checked and production cannot accept. The `@T-UC-006-…` tag is unchanged, and
  `docs/test-obligations/bdd-traceability.yaml:4825-4829` keys on `adcp_scenario_id`, not on the title — but
  I did not grep for the title string anywhere else in the repo.
- **Four Examples rows, two of them (`digital_capture`, `human_edits`) exercise the same code path** as the
  first two and differ only in the enum value. That is deliberate — the enum-value axis is exactly where our
  local enum diverges from the spec (ticket 2), so pinning several intersection values documents the
  boundary. If reviewers consider it padding, drop to two rows without loss of coverage.
- **Drift note only, not authority:** at adcp HEAD (3.1.8+) the provenance family has grown
  `provenance_audit_observation.yaml` alongside the two 3.1.1 files. We are pinned at 3.1.1 and I treated
  only 3.1.1 as authoritative.

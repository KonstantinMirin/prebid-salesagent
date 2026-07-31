# sb-uc021-preview — re-grounding `@T-UC-021-storyboard-preview-display-from-synced-manifest`

Scenario: `tests/bdd/features/BR-UC-021-preview-creative.feature:948`
Title: "Preview a synced display creative -- returns preview_url and render_dimensions matching the format"

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** Three independent reasons, any one of which is sufficient:

1. **Wrong tier for us.** The behaviour is graded only in the **creative protocol** baseline
   (`protocols/creative/index.yaml`, mirrored byte-identically at `domains/creative/index.yaml`).
   We declare `supported_protocols=[media_buy]` only
   (`src/core/tools/capabilities.py:99` and `:271`). `creative` is a real value of the SDK's
   `SupportedProtocol` enum (`['media_buy','signals','governance','sponsored_intelligence','creative','brand','measurement']`)
   that we deliberately do not emit. Undeclared protocol ⇒ off our conformance path.

2. **Step-level tool gate unsatisfied.** The step declares `requires_tool: preview_creative`
   (`protocols/creative/index.yaml:313`). We implement **no inbound `preview_creative` tool at all** —
   no MCP wrapper, no A2A raw function, no REST route. A `grep -rn "preview_creative" src/`
   returns exactly one production symbol, and it points the other way:
   `CreativeAgentRegistry.preview_creative` (`src/core/creative_agent_registry.py:885`) is an
   **outbound MCP client call** we make *to* a third-party creative agent during `sync_creatives`.
   We are the caller of this task, never the callee. Per `universal/storyboard-schema.yaml:254-256`,
   "`requires_tool` gates individual steps at execution time" — the step is gated out, not failed.

3. **Even on its own binding, the two field assertions are ungraded prose.** The graded
   `validations:` block for `preview_display` contains no check on `preview_url` and no check on
   any dimensions field. Both appear only under `expected:` — narrative prose.

Consequence: the `@storyboard-v3.1` tag is unjustified. It should become `@schema-v3.1`.
Keep `@T-UC-021-storyboard-preview-display-from-synced-manifest` unchanged — it is referenced from
`docs/test-obligations/bdd-traceability.yaml:12076`.

**Separately and importantly: the entire BR-UC-021 feature file is DORMANT.** There is no
`tests/bdd/test_uc021*.py`, no `scenarios()` binding to `BR-UC-021-preview-creative.feature`
anywhere under `tests/`, and no step module for it (`tests/bdd/steps/domain/` has no `uc021_*.py`).
Not one scenario in this 950-line file executes today. See §7 and §8.

---

## 2. Real binding at 3.1.1

### What the footer points at

**Nothing.** This scenario has **no `@source` footer at all** — it is one of the 11 the brief flagged.
The trailing comment block names its intended storyboard in prose only:

```
    # creative_lifecycle preview_display: the buyer requests a preview of a
    # display creative that was previously synced (creative_id present).
```

So there is no stale `ref=v3.1-04f59d2d5` to correct here; there is a missing binding to *add*.
The prose name `creative_lifecycle` / `preview_display` is **correct** — no off-by-one in this one.

### The real file + line

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/creative/index.yaml`
`id: creative_lifecycle` (line 1) → phase `build_and_preview` (**line 295**) → step `preview_display` (**line 303**).

Step metadata (lines 303-313):

```yaml
      - id: preview_display
        title: "Preview the display creative"
        task: preview_creative
        schema_ref: "creative/preview-creative-request.json"
        response_schema_ref: "creative/preview-creative-response.json"
        doc_ref: "/creative/task-reference/preview_creative"
        comply_scenario: creative_flow
        requires_tool: preview_creative
        stateful: false
```

**The graded `validations:` block, verbatim (lines 345-355):**

```yaml
        validations:
          - check: response_schema
            description: "Response matches preview-creative-response.json schema"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "creative_lifecycle--preview_display"
            description: "Context correlation_id returned unchanged"
```

Three checks. **Neither `preview_url` nor any dimensions field is graded here.**

The ungraded prose the scenario was written from (lines 315-319):

```yaml
        expected: |
          Return a preview of the display creative:
          - preview_url: rendered preview the buyer can inspect
          - render_dimensions: matches the 300x250 format
          - status: preview available
```

### Tier ownership (brief question 3)

`protocols/creative/` — the **creative protocol baseline**, `has_baseline: true`, `path: "protocols/creative/"`
(`dist/compliance/3.1.1/index.json`). 3.1.1 is mid-rename: `protocols/creative/index.yaml` and
`domains/creative/index.yaml` are **byte-identical** (verified by `diff`), and `index.json` lists the
same six ids under both `protocols` and `domains`. Not universal, not a specialism.
The storyboard declares no `requires:` and no `requires_capability:` — the only gates are the
protocol tier itself and the per-step `requires_tool`.

### The one place `preview_url` IS graded at 3.1.1 — and why it still doesn't rescue us

`protocols/media-buy/scenarios/creative_reception.yaml`, phase `preview` (line 177) →
step `preview_synced` (line 186), validations at **lines 235-240**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches preview-creative-response.json schema"
          - check: field_present
            path: "previews[0].renders[0].preview_url"
            description: "Preview includes a renderable URL"
```

This is on the **media-buy protocol**, which we *do* declare — so tier-wise it would be on our path.
But note the path: `previews[0].renders[0].preview_url`, **not** a top-level field. And the step
carries the same `requires_tool: preview_creative` gate (line 197), which we do not satisfy.
It is also a *native* creative in a media-buy reception flow, not a display creative previewed from
the library, so it is not this scenario's subject. Recorded here because it is the only graded
`preview_url` at 3.1.1 and it settles the nesting question definitively.

---

## 3. Schema constraints at 3.1.1

All quotes from `git show v3.1.1:static/schemas/source/...` in `/Users/konst/projects/adcp`.

### `creative/preview-creative-response.json`

Envelope composition and discriminator:

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
  "discriminator": { "propertyName": "response_type" },
```

Single branch (`PreviewCreativeSingleResponse`) required set:

```json
      "required": [
        "response_type",
        "previews"
      ],
      "additionalProperties": true
```

`previews[]` item shape:

```json
            "required": [
              "preview_id",
              "renders",
              "input"
            ]
```

with `previews` itself `"minItems": 1`, and:

```json
              "renders": {
                "type": "array",
                "description": "Array of rendered pieces for this preview variant. ...",
                "items": { "$ref": "/schemas/creative/preview-render.json" },
                "minItems": 1
              },
```

`expires_at` is **optional** and explicitly so:

```json
        "expires_at": {
          "type": "string",
          "format": "date-time",
          "description": "ISO 8601 timestamp when preview links expire. **Optional.** Omit when preview URLs do not expire ..."
        },
```

### `creative/preview-render.json` — the decisive file

`"discriminator": { "propertyName": "output_format" }` over three `oneOf` branches:

| `output_format` | `required` |
|---|---|
| `url` | `["render_id", "output_format", "preview_url", "role"]` |
| `html` | `["render_id", "output_format", "preview_html", "role"]` |
| `both` | `["render_id", "output_format", "preview_url", "preview_html", "role"]` |

The dimensions field, identical in all three branches:

```json
        "dimensions": {
          "type": "object",
          "description": "Dimensions for this rendered piece",
          "properties": {
            "width":  { "type": "number", "minimum": 0 },
            "height": { "type": "number", "minimum": 0 }
          },
          "required": ["width", "height"]
        },
```

Two hard facts follow:

- The field is named **`dimensions`**, not `render_dimensions`. **`render_dimensions` does not exist
  anywhere in the AdCP 3.1.1 schema source.** Cross-check: it does not exist in the `adcp==6.6.0`
  SDK either (grep over the installed package returns nothing).
- `dimensions` is **not** in any branch's `required` list — it is optional on every branch.
  `width`/`height` are required *only if* `dimensions` is present.

### `core/protocol-envelope.json`

```json
  "required": [ "status" ],
```

with the description stating: *"The `status` field is REQUIRED on every task response envelope,
including synchronous metadata responses ... Agents shipping responses without a top-level `status`
are non-conformant regardless of whether the task body schema would otherwise validate."*
This is the known repo-wide gap listed in the brief; it applies to this response too via the `allOf`.

### `creative/preview-creative-request.json`

Conditional required, verbatim from `allOf`:

```json
  { "if": { "properties": { "request_type": { "const": "single" } } },
    "then": { "required": [ "creative_manifest" ] } },
  { "if": { "properties": { "request_type": { "const": "batch"  } } },
    "then": { "required": [ "requests" ] } },
  { "if": { "properties": { "request_type": { "const": "variant"} } },
    "then": { "required": [ "variant_id" ] } }
```

The scenario's When (`request_type "single"` + `creative_manifest`) is correct against this.

---

## 4. Conflicts

### Where the 3.1.1 schema overrode the storyboard

**The storyboard prose is wrong and the schema wins.** `protocols/creative/index.yaml:318` writes
`- render_dimensions: matches the 300x250 format` under `expected:`. No such field exists in
`preview-render.json`, in `preview-creative-response.json`, or in the SDK. The storyboard author
invented a field name in a narrative block that nothing grades, and our scenario copied it into an
assertion. **Per the brief's authority order, the 3.1.1 JSON schema wins: the field is `dimensions`,
nested at `previews[i].renders[j].dimensions`, and it is optional.**

Same section of prose says `- status: preview available`. `status` is a `core/protocol-envelope.json`
task-state field constrained by `enums/task-status.json` — "preview available" is not a member of
that enum. Also prose, also ungraded, also wrong.

### What the scenario gets wrong

| Line | Current text | Defect |
|---|---|---|
| 949 (title) | `returns preview_url and render_dimensions matching the format` | Names a field that does not exist at 3.1.1 |
| 953 | `Then the response should be schema-valid against preview-creative-response.json` | Vacuous as written — the repo's only implementation of this phrasing, `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-102 (then_response_schema_valid)`, runs no validator despite `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing (known gap, brief §"Known production gaps"). It would also validate against `tests/fixtures/adcp_schemas_pinned/`, vendored at `04f59d2d5`, not 3.1.1. |
| 954 | `And the response should carry a preview_url the buyer can inspect` | Wrong nesting (it is `previews[0].renders[0].preview_url`) **and** wrong unconditionality (absent entirely on the `html` branch). Also a bare existence check — rejected by `test_architecture_bdd_no_trivial_assertions.py`. |
| 955 | `And the render_dimensions on the preview should match the format_id "display_300x250"` | Field does not exist; and "match the format_id" is not a value comparison — a format_id is a `{agent_url, id}` object, not a dimension pair. Nothing to compare against. |
| tags | `@storyboard-v3.1` | Unjustified — see §1. |
| footer | *(absent)* | No `@source` line at all. |

### Vacuity

All three Thens are non-executing (feature is dormant, §1) and, of the three, two are pure
existence/"should match" prose with no concrete comparand. This scenario asserts nothing today
and would assert nearly nothing if wired as written.

### Sibling defects in the same file (not mine to fix; flagged for the lead)

- Line 49: `And each render has a render_id, output_format, role, and preview_url` — same
  branch-blindness; `preview_url` is not required on the `html` branch.
- Lines 51 and 71: `And the response includes an expires_at timestamp in ISO 8601 format` —
  `expires_at` is **optional** at 3.1.1 with an explicit "Omit when preview URLs do not expire"
  clause. Asserting its presence contradicts the pinned schema.
- Lines 52-53: `the response may include ...` — "may" Thens cannot assert and will trip
  `test_architecture_bdd_no_pass_steps.py` when wired.

---

## 5. Proposed Gherkin

Replaces `tests/bdd/features/BR-UC-021-preview-creative.feature:948-966` in full.

Retagged `@storyboard-v3.1` → `@schema-v3.1`. Opaque identifier tag preserved verbatim.
Re-expressed as a `Scenario Outline` over the `preview-render.json` discriminated union, which is
precisely what the two broken Thens were groping at. Every Then compares a concrete value.
Nothing is asserted that the 3.1.1 schema does not mandate — in particular `dimensions` is asserted
only in the row where the Given supplies it, and `expires_at` is not asserted at all.

```gherkin
  @T-UC-021-storyboard-preview-display-from-synced-manifest @schema-v3.1 @v3-1 @preview-from-library
  Scenario Outline: Preview a synced display creative -- render carries the <output_format> branch fields at previews[0].renders[0]
    Given a display creative has been synced to the library with creative_id "display_trail_pro_300x250" and format_id agent_url "https://your-platform.example.com" and id "display_300x250"
    And the creative agent returns a render with output_format "<output_format>" and dimensions 300x250
    When the Buyer Agent sends preview_creative with request_type "single" and the synced creative_manifest
    Then the response field "response_type" equals "single"
    And the response field "previews[0].renders[0].output_format" equals "<output_format>"
    And the render at "previews[0].renders[0]" carries exactly the required fields "<required_fields>"
    And the response field "previews[0].renders[0].role" equals "primary"
    And the response field "previews[0].renders[0].dimensions.width" equals 300
    And the response field "previews[0].renders[0].dimensions.height" equals 250
    And the response field "context.correlation_id" equals "creative_lifecycle--preview_display"

    Examples: preview-render.json oneOf branches (3.1.1)
      | output_format | required_fields                                       |
      | url           | render_id,output_format,preview_url,role              |
      | html          | render_id,output_format,preview_html,role             |
      | both          | render_id,output_format,preview_url,preview_html,role |

    # Binding: creative_lifecycle / build_and_preview / preview_display.
    # Tagged @schema-v3.1, NOT @storyboard-v3.1: that step is gated by
    # `requires_tool: preview_creative` and sits on the `creative` protocol, which
    # src/core/tools/capabilities.py does not declare (we emit media_buy only).
    # The step's own `validations:` grade only response_schema + context echo —
    # preview_url and dimensions appear there under `expected:` prose, ungraded.
    # Field names and required-sets above come from the 3.1.1 JSON schema, which
    # overrides the storyboard prose: the prose says "render_dimensions", a field
    # that exists in no 3.1.1 schema and no adcp SDK type. The real field is
    # `dimensions`, nested under each render, and it is OPTIONAL — asserted here
    # only because the Given supplies it. See #TBD-A.
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/creative/index.yaml phase=build_and_preview step=preview_display graded=false
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/creative/preview-render.json
```

### Honesty note on "GREEN ONLY"

This scenario is green **only because it does not execute** — BR-UC-021 has no test module, so no
scenario in the file runs. That is the pre-existing state of all ~40 scenarios in it, and this
rewrite does not change it. **If the feature were wired today, this scenario would go red**, because
there is no inbound `preview_creative` tool to call and no harness env to call it through (§7,
first two bullets). I am not proposing to wire it in this PR.

**The lead has a real alternative and should choose deliberately:** delete this scenario outright and
drop `docs/test-obligations/bdd-traceability.yaml:12076-12081`, on the grounds that a scenario for a
task we neither implement nor advertise, on a protocol we do not declare, is not coverage we owe.
I recommend the rewrite over deletion only because the surrounding 40 scenarios have exactly the same
status — deleting this one alone would be arbitrary. Deleting the whole file is a coherent option;
deleting one scenario from it is not.

---

## 6. Step inventory

**Existing in `tests/bdd/steps/` and reusable: none.** There is no `uc021_*.py` step module, and no
generic step matches any phrasing in this scenario. Verified by
`grep -rln "uc021\|UC-021\|preview_creative" tests/bdd/steps/` → only
`tests/bdd/steps/domain/uc006_sync_creatives.py`, and there `preview_creative` is an `AsyncMock` on
the *outbound* registry (`uc006_sync_creatives.py:2045`), not a step.

| Phrasing | Status | Note |
|---|---|---|
| `Given a display creative has been synced to the library with creative_id "…" and format_id agent_url "…" and id "…"` | **NEW** | Split the original's `{agent_url, "display_300x250"}` brace-literal into two named parts — the original is not a parseable `parsers.parse` shape. |
| `And the creative agent returns a render with output_format "<…>" and dimensions 300x250` | **NEW** | Needs a harness env; see §7. |
| `When the Buyer Agent sends preview_creative with request_type "single" and the synced creative_manifest` | **reused verbatim** from the current scenario (line 952) — but unimplemented, like every When in this file. |
| `Then the response field "…" equals "…"` | **NEW (generic)** | Should land in `tests/bdd/steps/generic/then_payload.py` as a dotted-path value comparator. Nothing equivalent exists — `then_payload.py` has 19 `@then`s, all format-listing specific. This is the DRY-correct place for it and would serve far more than UC-021. |
| `And the render at "…" carries exactly the required fields "…"` | **NEW** | Exact set equality against the branch's `required` list, not a subset check — this is the assertion that actually encodes the discriminated union. |

Deliberately **not** reused: `Then the response should be schema-valid against preview-creative-response.json`.
Its only sibling implementation (`uc005_format_id_roundtrip.py:101`) runs no validator, and it would
resolve against the `04f59d2d5`-vintage `tests/fixtures/adcp_schemas_pinned/`. Reusing it would import
a known-vacuous assertion. Ticketed in §7.

---

## 7. TICKET MATERIAL

- **BR-UC-021 is entirely dormant — no scenario in the file executes.**
  There is no `tests/bdd/test_uc021*.py`, no `scenarios()` binding to
  `tests/bdd/features/BR-UC-021-preview-creative.feature` anywhere under `tests/`, and no
  `tests/bdd/steps/domain/uc021_*.py`. ~40 scenarios across 966 lines assert nothing. This is the
  dormant-scenario anti-pattern at file scale. Decide explicitly: wire it, or delete the file and its
  `docs/test-obligations/bdd-traceability.yaml` rows. Mandate for wiring, if chosen:
  `protocols/creative/index.yaml:303` (`preview_display`) and
  `protocols/media-buy/scenarios/creative_reception.yaml:186` (`preview_synced`).

- **We implement no inbound `preview_creative` tool, on any transport.**
  `grep -rn "preview_creative" src/` yields only `src/core/creative_agent_registry.py:885`, an
  **outbound** MCP client call we make to a third-party creative agent from `sync_creatives`
  (`src/core/tools/creatives/_processing.py:359` and `:649`). No MCP wrapper, no A2A raw function,
  no REST route. Mandated by `protocols/media-buy/scenarios/creative_reception.yaml:186-240` —
  a step on the **media-buy protocol we do declare** — whose `requires_tool: preview_creative`
  (line 197) we fail to satisfy, forfeiting the only graded `preview_url` check at 3.1.1
  (`previews[0].renders[0].preview_url`, line 239). Scope: `_impl` + 3 transport wrappers +
  a `preview` harness env (`tests/harness/` has 20 envs, none for preview).

- **Stale comment claims `preview_creative` is not in the AdCP spec.**
  `src/core/creative_agent_registry.py:917`: *"Use custom MCP client for non-standard tools
  (preview_creative not in AdCP spec)"*. It is in the spec at 3.1.1 —
  `static/schemas/source/creative/preview-creative-request.json` and `-response.json`, with a
  `doc_ref: "/creative/task-reference/preview_creative"` on three separate storyboard steps.
  One-line comment fix; matters because it is load-bearing for "should we implement this".

- **`then_response_schema_valid` runs no validator.**
  `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-102` implements
  `Then the response should be schema-valid against list-creative-formats-response.json` and asserts
  nothing schema-related, while `tests/helpers/pinned_schema.py::validate_against_pinned_schema`
  exists unused. Any scenario adopting this phrasing inherits a vacuous Then. (Already known per the
  brief; re-stated because this scenario is a live consumer.)

- **`tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not 3.1.1.**
  Re-vendoring changes what `preview-creative-response.json` validation means here: the
  `core/protocol-envelope.json` `required: ["status"]` composition and the three-branch
  `preview-render.json` discriminator are 3.1.1 shapes. (Already known per the brief.)

- **Sibling scenarios in BR-UC-021 contradict the pinned schema.** Fix alongside any wiring effort:
  - `:51` and `:71` assert `expires_at` is present. `creative/preview-creative-response.json` at
    v3.1.1 marks it **Optional** with an explicit "Omit when preview URLs do not expire" clause.
  - `:49` asserts every render has `preview_url`. `creative/preview-render.json` requires it only on
    the `url` and `both` branches; the `html` branch requires `preview_html` and has no `preview_url`.
  - `:52-53` use `the response may include …` as Then steps — cannot assert; will trip
    `test_architecture_bdd_no_pass_steps.py`.

- **Upstream: `protocols/creative/index.yaml:318` names a field that does not exist.**
  The `expected:` prose for `preview_display` says `- render_dimensions: matches the 300x250 format`.
  No 3.1.1 schema and no `adcp==6.6.0` type defines `render_dimensions`; the real field is
  `dimensions` on `creative/preview-render.json`. Line 319's `- status: preview available` is
  likewise not a member of `enums/task-status.json`. File upstream at
  `github.com/adcontextprotocol/adcp` — our scenario was written straight off this prose, so the
  same trap is live for every other implementer.

- **No top-level `status` on our responses.** `core/protocol-envelope.json` `required: ["status"]`
  composes into `preview-creative-response.json` via `allOf`. (Already known per the brief; noted
  because it would apply to any `preview_creative` we ship.)

---

## 8. Risks

- **Nothing here was verified by execution.** The feature is dormant, so I could not run the current
  scenario, could not observe it fail, and cannot demonstrate the replacement passes. Every claim in
  §1-§4 is from reading the 3.1.1 schema source, the 3.1.1 storyboards, and `src/`. The proposed
  Gherkin is green only in the trivial sense that it does not execute — stated plainly in §5.

- **My proposed step phrasings are unimplemented.** If the lead wires BR-UC-021 in a later PR, the
  `Then the response field "…" equals "…"` comparator belongs in
  `tests/bdd/steps/generic/then_payload.py`, not in a UC-021-local module — several other features
  would want it, and a UC-021-local copy would be a DRY defect on arrival.

- **`requires_tool` skip-vs-fail semantics are documented only indirectly.**
  `universal/storyboard-schema.yaml:254-256` says it "gates individual steps at execution time" and
  contrasts it with load-time `requires:`; I found no block spelling out the runner's exact
  skip_result. I read it as "step skipped when the tool is unadvertised". If it is instead a hard
  fail, our conformance posture on `creative_reception.yaml` is worse than stated, not better — the
  verdict does not change either way.

- **`protocols/` vs `domains/` duplication.** At 3.1.1 the two trees are byte-identical for
  `creative` (verified by `diff`) and `index.json` lists the same six ids under both keys. I cited
  `protocols/` as canonical since `index.json` lists it first and the brief's phrasing implies
  `protocols/` is the forward name. If the runner actually loads from `domains/`, substitute the
  path — the line numbers are identical.

- **I did not check 3.1.8 or HEAD**, per the brief. The `render_dimensions` prose defect may already
  be fixed upstream; the ticket bullet should be checked against HEAD before filing so it is not a
  duplicate.

- **I did not verify the off-by-one hypothesis for this scenario** because it has no `@source` footer
  to be wrong. Its prose binding (`creative_lifecycle` / `preview_display`) is correct; this one is
  a missing-binding case, not a mis-binding case.

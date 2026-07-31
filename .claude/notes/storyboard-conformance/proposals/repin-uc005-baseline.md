# Re-pin: UC-005 baseline `format_id` object shape → AdCP 3.1.1

Target scenario: `tests/bdd/features/BR-UC-005-discover-creative-formats.feature:1094`
Tags: `@T-UC-005-storyboard-baseline-format-id-object-shape @storyboard-v3.1 @v3-1 @format-id-shape @baseline-conformance`

Current `@source`: `ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/schemas/source/core/format-id.json`
(04f59d2d5 is an ancestor of beta.3 — older than our own pin; being re-pinned to **3.1.1**.)

Verification note: `dist/compliance/3.1.1/protocols/creative/index.yaml` on disk is byte-identical
at these lines to `git show v3.1.1:static/compliance/source/protocols/creative/index.yaml`. Both were
read; line numbers below are the `dist/compliance/3.1.1/...` ones.

---

## 1. Storyboard checks at 3.1.1 — verbatim

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/creative/index.yaml:79-130`

```yaml
  - id: discover_formats                                                    # :79
    title: "Discover accepted formats"
    narrative: |
      Before pushing any creatives, the buyer discovers what formats your platform accepts.
      This determines which assets to prepare and what dimensions and specs to target.

    steps:
      - id: list_formats                                                    # :86
        title: "List creative formats"
        narrative: |
          The buyer calls list_creative_formats to discover what your platform accepts.
          The response defines format specs: dimensions, asset requirements, mime types,
          and any platform-specific constraints.
        task: list_creative_formats                                         # :92
        schema_ref: "creative/list-creative-formats-request.json"           # :93
        response_schema_ref: "creative/list-creative-formats-response.json" # :94
        doc_ref: "/creative/task-reference/list_creative_formats"
        comply_scenario: creative_lifecycle
        stateful: false
        expected: |                                                         # :98
          Return the first page of creative formats your platform accepts:
          - format_id with your agent_url and unique id
          - Asset requirements (dimensions, file sizes, mime types)
          - Render dimensions
          - Up to five formats on this compliance request; callers paginate for the rest when needed

        sample_request:                                                     # :105
          pagination:
            max_results: 5
          context:
            correlation_id: "creative_lifecycle--list_formats"

        validations:                                                        # :111
          - check: response_schema
            description: "Response matches list-creative-formats-response.json schema"
          - check: field_present
            path: "formats"
            description: "Response contains formats array"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "creative_lifecycle--list_formats"
            description: "Context correlation_id returned unchanged"
          - check: field_present
            path: "formats[0].format_id.agent_url"                          # :126
            description: "Format IDs include agent_url"
          - check: field_present
            path: "formats[0].format_id.id"                                 # :129
            description: "Format IDs include id — must match those in get_products"
```

**Graded set (6 checks):** `response_schema`; `field_present formats`; `field_present context`;
`field_value context.correlation_id`; `field_present formats[0].format_id.agent_url`;
`field_present formats[0].format_id.id`.

Note the storyboard grades **`formats[0]` only** — first element, presence only. It says nothing
about the other entries, nothing about value shape, and nothing about a bare string.

---

## 2. Schema constraints at 3.1.1 — verbatim

### `core/format-id.json` (`git show v3.1.1:static/schemas/source/core/format-id.json`)

```json
"title": "Format Reference (Structured Object)",
"description": "A JSON object — never a plain string — that identifies a creative format by its
declaring agent and local slug. Required properties: agent_url (URI of the agent that owns the
format) and id (slug matching [a-zA-Z0-9_-]+). ... Using a plain string here is a schema violation.",
"type": "object",
"properties": {
  "agent_url": { "type": "string", "format": "uri", ... },
  "id":        { "type": "string", "pattern": "^[a-zA-Z0-9_-]+$", ... },
  "width":     { "type": "integer", "minimum": 1 },
  "height":    { "type": "integer", "minimum": 1 },
  "duration_ms": { "type": "number", "minimum": 1 }
},
"required": ["agent_url", "id"],
"additionalProperties": true,
"dependencies": { "width": ["height"], "height": ["width"] }
```

Binding: **`format_id` may NEVER be a bare string** — `"type": "object"` plus the description's
explicit "Using a plain string here is a schema violation." Both `agent_url` and `id` are
`required`. `id` carries a value-level `pattern`; `agent_url` carries `format: uri`.
`additionalProperties: true` — so the assertion must check *presence*, not an exact key set
(`width`/`height`/`duration_ms` are legal extras; adcp 5.7.0 emits them).

### `creative/list-creative-formats-response.json` (the `response_schema_ref`)

```
properties: ['formats', 'creative_agents', 'errors', 'pagination', 'context', 'ext']
required:   ['formats']
additionalProperties: true
pagination: { "$ref": "/schemas/core/pagination-response.json" }
```

`media-buy/list-creative-formats-response.json` (what a sales agent actually serves) is the same
shape plus a `source` enum; `required` is likewise `["formats"]`.

**`pagination` is NOT required on this response at 3.1.1.** Only `formats` is.

### `core/format.json`

```
required: ['format_id', 'name']
format_id: { "$ref": "/schemas/core/format-id.json",
             "description": "This format's own identifier — a structured object {agent_url, id},
                             not a string." }
additionalProperties: true
```

So **every** element of `formats[]` has a required `format_id` that is a `format-id.json` object —
the schema's "every entry" strictness, which the storyboard's `formats[0]` grading does not express.

### `core/pagination-response.json`

```json
"properties": {
  "has_more":    { "type": "boolean", ... },
  "cursor":      { "type": "string",
                   "description": "... Only present when has_more is true." },
  "total_count": { "type": "integer", "minimum": 0, ... }
},
"required": ["has_more"],
"additionalProperties": false
```

### `core/pagination-request.json`

```json
"properties": {
  "max_results": { "type": "integer", "minimum": 1, "maximum": 100, "default": 50 },
  "cursor":      { "type": "string" }
},
"additionalProperties": false
```

The `cursor ↔ has_more` coupling ("Only present when has_more is true") is **prose in a
description**, not a JSON Schema construct — nothing machine-enforces it. `cursor` is typed
`string`, so a literal `"cursor": null` on the wire is a type violation (see Risks).

---

## 3. Pagination analysis — is "complete catalog" tenable at 3.1.1?

**No, not as an unconditional premise.**

At 3.1.1 `list_creative_formats` is definitionally a **paged** operation: the request carries
`pagination` (`max_results` default 50, max 100) and the response carries `pagination.has_more`.
The storyboard's own `expected` says "Return the **first page** … callers paginate for the rest
when needed" and the compliance request pins `max_results: 5`. A single unfiltered response is a
**page**, not a catalog. A buyer only "knows the complete catalog" after iterating cursors until
`has_more == false`.

Production matches this: `src/core/tools/creative_formats.py:428-461` defaults `max_results = 50`,
slices `formats[start:end]`, computes `has_more = end_index < total_count`, and emits a cursor only
when `has_more`.

### Is MY scenario affected?

**Materially, no — but the claim needs scoping.** The `format_id` object-shape contract is a
*per-entry* invariant from `core/format.json` + `core/format-id.json`. It holds identically on
page 1, page N, and on a complete catalog. "Every entry" in this scenario means *every entry in the
returned page*, and that is the correct and complete statement of the contract.

The rewrite makes this explicit and, in this scenario's environment, closes the gap honestly: it
adds a Then asserting `has_more == false` and `total_count == len(formats)`. In the BDD env the
mock registry seeds 11 formats (`src/core/creative_agent_registry.py:212-230`, 11 entries) against a
default page size of 50, so the returned page **is** the whole catalog — which is exactly what
makes "every entry" equal "every registered format" here, and it is now asserted rather than assumed.

### Recommendation for line 10 and the siblings (analysis only — NOT edited)

- **Line 10** (`POST-S1: Buyer knows the complete catalog of creative formats available from this
  seller`) should be re-worded to something like: *"Buyer knows the seller's format catalog, one page
  at a time — the first page plus a `pagination.has_more`/`cursor` pair sufficient to retrieve the
  rest."* As written, POST-S1 asserts a postcondition no single 3.1.1 response can satisfy.
- **Line ~29 `Then the response should include all registered formats`** and the `# POST-S1: Complete
  catalog returned` comment at line ~34 are true only because the fixture catalog (11) is smaller
  than the default page size (50). They are accidentally-passing, not contract-grounded. Either
  bound them explicitly (`has_more == false`, so this page is the catalog) or add an explicit
  seeded-catalog-larger-than-page-size scenario.
- **Missing sibling coverage entirely:** there is no scenario anywhere in this feature file for
  `pagination` (`grep` for `pagination|has_more|cursor|max_results` returns zero hits) nor for
  `context` / `correlation_id` echo. Both are **graded** by the 3.1.1 `discover_formats` step.
  Two new siblings are warranted: a *pagination page-boundary* scenario (`max_results: 5` over a
  >5 catalog → exactly 5 entries, `has_more true`, `cursor` present, follow the cursor, second page
  `has_more false`, no `cursor`) and a *context echo* scenario (`context.correlation_id` returned
  unchanged). I did not write them — flagging them as the phase's real uncovered graded checks.

---

## 4. Conflicts

**Schema over storyboard (explicit).** The storyboard grades only `formats[0].format_id.agent_url`
and `formats[0].format_id.id`, presence-only. The schema (`core/format.json` requires `format_id` on
*every* item; `core/format-id.json` is `type: object`, `required [agent_url, id]`, `id` pattern-
constrained, "plain string is a schema violation") is strictly stronger and applies to every entry.
**The 3.1.1 schema wins.** The rewritten scenario asserts the schema's strength, not the
storyboard's floor. The current scenario already made this call; the rewrite keeps it and adds the
value-level constraints the schema carries and the storyboard has no way to express.

**Where the current scenario is wrong or thin:**

1. `@source` cites `commit=04f59d2d5` — an ancestor of beta.3, older than our own pin. Stale.
2. The `@source` footer cites `core/format-id.json` while the prose comment cites the
   `creative/index.yaml discover_formats` phase. Two different authorities in one footer, neither
   versioned to 3.1.1.
3. **Misses `response_schema`** — the first graded check of the step. The scenario never asserts the
   response validates against `list-creative-formats-response.json`.
4. **Misses the `id` value constraint** — `^[a-zA-Z0-9_-]+$`. A seller emitting
   `{"agent_url": "...", "id": "display 300x250"}` (space) passes the current scenario and violates
   3.1.1.
5. **Misses the `agent_url` value constraint** — `format: uri`. A seller emitting
   `{"agent_url": "creative-agent", "id": "x"}` (relative, no scheme) passes the current scenario
   and violates 3.1.1.
6. **Misses the JSON-type constraint on the sub-fields.** `assert_wire_format_id_is_object` checks
   `"agent_url" in fid` only — `{"agent_url": 123, "id": null}` passes today.
7. **Unscoped "every entry" claim.** With pagination in the contract, "every entry" is per-page;
   the scenario never establishes what page it is looking at.
8. **Not a `Scenario Outline`.** The two required keys are asserted by two hand-rolled prose Thens
   with no per-key parametrization.

**No conflict found** between the SDK/production and the schema on this contract: production types
`format_id` as a structured `FormatId` and cannot emit a bare string by construction — which is
precisely why the assertion has to run on the **serialized wire**
(`ctx["wire_response"]`), as the existing step module already does
(`tests/bdd/steps/domain/uc005_format_id_shape.py:30-52`). That design is correct and is preserved.

---

## 5. Proposed Gherkin — complete replacement for lines 1094-1106

```gherkin
  @T-UC-005-storyboard-baseline-format-id-object-shape @storyboard-v3.1 @v3-1 @format-id-shape @baseline-conformance
  Scenario Outline: Baseline list_creative_formats response carries format_id objects with agent_url and id -- <required_key>
    Given the Buyer Agent calls list_creative_formats without filters
    When the response returns a non-empty formats array
    Then the response should be schema-valid against list-creative-formats-response.json
    And every entry's format_id should be an object carrying both agent_url and id
    And no entry's format_id should be a bare string
    And the returned page should report has_more false with total_count equal to the number of entries
    And every entry's format_id "<required_key>" should serialize as JSON type "<json_type>"
    And every entry's format_id "<required_key>" should satisfy the "<value_rule>" constraint from core/format-id.json

    # core/format-id.json (3.1.1) required: [agent_url, id]. One row per required key:
    # present (indexed by the step), correctly typed, and value-valid.
    Examples: required keys of the format_id object
      | required_key | json_type | value_rule                |
      | agent_url    | string    | absolute_uri_with_scheme  |
      | id           | string    | slug_alnum_underscore_dash|

    # discover_formats phase, 3.1.1: every format_id returned must be an object with both
    # agent_url (the creative agent's URL) and id (the format's unique identifier within that
    # agent). Sellers returning bare-string format IDs break the v3.1 federation contract.
    #
    # SCHEMA OVER STORYBOARD: the storyboard grades field_present on formats[0].format_id.agent_url
    # and .id only (index.yaml:125-130). The schema is strictly stronger and wins:
    # core/format.json requires format_id on EVERY item of formats[]; core/format-id.json is
    # "type": "object", required [agent_url, id], with "Using a plain string here is a schema
    # violation" in its description, "format": "uri" on agent_url and "^[a-zA-Z0-9_-]+$" on id.
    # This scenario asserts the schema's strength on every entry, plus the value-level constraints
    # the storyboard has no way to express.
    #
    # PAGE-SCOPED, DELIBERATELY: at 3.1.1 list_creative_formats is a paged operation
    # (core/pagination-request.json max_results default 50, max 100; the compliance request pins
    # max_results: 5 and the step's `expected` says "Return the first page ... callers paginate for
    # the rest"). "Every entry" therefore means every entry of the returned page -- which is the
    # complete statement of the per-entry contract, since it holds identically on every page.
    # The has_more/total_count Then pins that this particular page IS the whole catalog, so the
    # "every entry" claim here is not silently weaker than it reads. pagination itself is OPTIONAL
    # on list-creative-formats-response.json (required: ["formats"] only), and the
    # cursor-only-when-has_more coupling is prose in the schema description, not an enforced
    # construct -- both belong to a dedicated pagination sibling (see GitHub issue when filed),
    # not here.
    #
    # discover_formats: format_id object shape is the federation contract
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/creative/index.yaml#L79-L130
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/format-id.json
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/format.json
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/creative/list-creative-formats-response.json
```

---

## 6. Step inventory

### Reused verbatim — no new code

| Step text | Defined at |
|---|---|
| `Given the Buyer Agent calls list_creative_formats without filters` | `tests/bdd/steps/generic/when_request.py:130` |
| `When the response returns a non-empty formats array` | `tests/bdd/steps/domain/uc005_format_id_shape.py:55` |
| `Then the response should be schema-valid against list-creative-formats-response.json` | `tests/bdd/steps/domain/uc005_format_id_roundtrip.py` (`then_response_schema_valid`) |
| `Then every entry's format_id should be an object carrying both agent_url and id` | `tests/bdd/steps/domain/uc005_format_id_shape.py:62` |
| `Then no entry's format_id should be a bare string` | `tests/bdd/steps/domain/uc005_format_id_shape.py:70` |

### New — 3 step definitions, all in `tests/bdd/steps/domain/uc005_format_id_shape.py`

1. `@then(parsers.parse('every entry\'s format_id "{required_key}" should serialize as JSON type "{json_type}"'))`
   — for each entry of `_serialized_formats(ctx)`, look up `entry["format_id"][required_key]` (the
   `KeyError` on absence *is* the required-key check) and compare its runtime type against a
   `{"string": str, "object": dict, "integer": int}` **dict lookup** — not an `elif` chain.
   Concrete comparison, no truthiness.

2. `@then(parsers.parse('every entry\'s format_id "{required_key}" should satisfy the "{value_rule}" constraint from core/format-id.json'))`
   — dict of named predicates → `{"absolute_uri_with_scheme": ..., "slug_alnum_underscore_dash": ...}`.
   `absolute_uri_with_scheme`: `urlparse(v).scheme` in `{"http","https"}` **and** `.netloc` non-empty
   (pins `format: uri`; tolerant of the trailing-slash normalization noted in
   `tests/helpers/format_assertions.py`). `slug_alnum_underscore_dash`:
   `re.fullmatch(r"[a-zA-Z0-9_-]+", v)` — the schema pattern verbatim. Unknown rule name raises,
   so a typo'd Examples cell fails loudly instead of passing vacuously.

3. `@then("the returned page should report has_more false with total_count equal to the number of entries")`
   — needs the **response envelope**, not just `formats[]`. Extract a new
   `_serialized_response(ctx) -> dict` from the existing `_serialized_formats`
   (`uc005_format_id_shape.py:30-52`) and make `_serialized_formats` call it — DRY, single
   wire/IMPL branch, and the loud "wire_response missing" guard stays in one place. Assert
   `pagination["has_more"] is False` and `pagination["total_count"] == len(formats)`.

### Recommended for the predicate helpers

Put `absolute_uri_with_scheme` / `slug_alnum_underscore_dash` in
`tests/helpers/format_assertions.py` next to `assert_wire_format_id_is_object` — the
`roundtrip-from-products` and `third-party-agent` siblings will want the same value rules, and that
module is already the shared home for the federation contract.

---

## 7. Risks

1. **`pagination.cursor: null` on the REST wire is a live 3.1.1 conformance defect.**
   `src/routes/api_v1.py:211` returns `response.model_dump(mode="json")` with **no**
   `exclude_none`, so a response with `has_more == false` serializes `"cursor": null`.
   `core/pagination-response.json` types `cursor` as `"type": "string"` — `null` fails validation,
   and the schema's own description says cursor is "Only present when has_more is true." My
   proposed Thens do not trip on this (they read `has_more` and `total_count` only), but a *real*
   `response_schema` validation would. Worth its own ticket; not fixed here.

2. **The reused `Then the response should be schema-valid against list-creative-formats-response.json`
   under-delivers on its name.** Its body asserts only `isinstance(formats, list)`
   (`uc005_format_id_roundtrip.py`, `then_response_schema_valid`). It does not run a JSON Schema
   validator. Reusing it keeps DRY and matches the sibling, but the scenario line reads stronger
   than the assertion is. Upgrading it to a real `jsonschema.validate` against the pinned 3.1.1 file
   would immediately red on risk #1 above — which is the correct outcome, but it changes a sibling
   scenario's behavior and is out of my scope.

3. **`wire_response` availability.** The new pagination Then depends on `pagination` surviving to
   the wire on all of REST / MCP / A2A. REST emits the full `model_dump`; A2A stashes the DataPart
   *before* the message/success strip; MCP uses `structured_content`. All three should carry it, but
   this is unverified by execution — I did not run the suite (proposal-only). If any transport
   strips `pagination`, that is a finding, not a reason to weaken the Then.

4. **`has_more == false` is fixture-dependent.** It holds because the mock registry seeds 11 formats
   (`src/core/creative_agent_registry.py:212-230`) against a default page size of 50. A future
   change that grows the mock catalog past 50 flips `has_more` to `true` and reds this scenario. The
   failure would be loud and correct (it would mean "every entry" no longer covers the catalog), but
   it is a coupling worth knowing about.

5. **Retiring nothing, adding an Outline.** The scenario becomes 2 parametrized instances × 4
   transports = 8 test cases where it was 4. Cheap here (no DB writes beyond the env), but it does
   double this scenario's share of the bdd env runtime.

6. **`type` filter is gone from the 3.1.1 request schema.**
   `media-buy/list-creative-formats-request.json` at 3.1.1 has no `type` property, yet sibling
   scenarios at lines ~38 and ~542 still filter on `type` (production already no-ops it —
   `when_request.py:186-192` ignores the value). Not my scenario, but it means the sibling
   "Discover filtered format catalog" scenario is asserting against a field the pinned request
   schema does not define. Flagging for the lead.

7. **Two `@source` authorities in one footer.** I kept both (storyboard + schemas) because the
   scenario legitimately draws on both and the comment explains which one wins where. If the repo
   convention is one `@source` line per scenario, collapse to the schema line and keep the
   storyboard reference in prose.

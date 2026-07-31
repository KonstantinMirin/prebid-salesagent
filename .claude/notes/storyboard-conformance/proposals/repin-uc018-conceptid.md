# Re-pin: UC-018 `concept_ids` filter scenario against AdCP 3.1.1

Target: `/Users/konst/projects/salesagent/tests/bdd/features/BR-UC-018-list-creatives.feature:787-800`
Steps live in: `/Users/konst/projects/salesagent/tests/bdd/test_uc018_list_creatives.py:229-370` (module-local)
Authority: `v3.1.1` tag in `/Users/konst/projects/adcp` (commit `467fd93d7`), plus `/Users/konst/projects/adcp/dist/compliance/3.1.1/` on disk.

---

## 1. Is this actually storyboard-graded for us? — **No. The `@storyboard-v3.1` tag is wrong, twice over.**

Two independent reasons, either one sufficient:

**(a) The only 3.1.1 storyboard that mentions `concept_id` is a specialism we do not declare.**
A full walk of `dist/compliance/3.1.1/` finds exactly one non-protocol file containing the string
`concept_id`: `specialisms/creative-ad-server/index.yaml`. (`concept_name` appears in **zero**
storyboard files at 3.1.1.) The prior investigation is confirmed.

`src/core/tools/capabilities.py:98` and `:270` both declare:

```python
specialisms=[AdcpSpecialism.sales_non_guaranteed],
supported_protocols=[SupportedProtocol.media_buy],
```

We declare neither the `creative-ad-server` specialism nor the `creative` protocol. The comment at
`src/core/tools/capabilities.py:254-257` states the runner's own gating rule: *"The runner gates
scenarios by specialism, not by `supported_protocols` alone."* So `creative-ad-server` is not on our
graded conformance path at all.

**(b) Even for an agent that DOES declare `creative-ad-server`, `concept_id` is still not graded.**
The mention sits in the step's `expected:` narrative prose, not in `validations:`. The full graded
validation set for that step is three checks — `response_schema`, `field_present: context`,
`field_value: context.correlation_id`. There is no `field_present`/`field_value` on `concept_id`
anywhere in 3.1.1. The `sample_request` for that step doesn't even use the `concept_ids` filter; it
filters on `statuses: [approved]`.

**Verdict:** the `concept_ids` filter and the `concept_id` / `concept_name` response fields are
**schema-graded only** at 3.1.1. Replace `@storyboard-v3.1` with `@schema-v3.1` (already in the
feature-file tag vocabulary — used by UC-010). Keep the `@T-UC-018-storyboard-filter-by-concept-id`
identifier tag **unchanged**: it is an opaque id referenced from
`docs/test-obligations/bdd-traceability.yaml`, and renaming it means editing that file in the same
change. If you want the rename anyway, that's the one extra file.

**The one thing that IS storyboard-graded here:** `universal/pagination-integrity.yaml` — a
`track: core` **universal** storyboard (not specialism-gated) whose `required_tools` is
`list_creatives`. It grades `pagination.has_more`, `pagination.cursor`, `pagination.total_count`,
`query_summary.total_matching` and `query_summary.returned` on *every* `list_creatives` response. The
current scenario asserts none of those. That is the real grading gap, and it is the reason the
rewrite below adds them.

---

## 2. Storyboard checks at 3.1.1 — verbatim + file:line

### 2a. The specialism mention (NOT graded, prose only)

`/Users/konst/projects/adcp/dist/compliance/3.1.1/specialisms/creative-ad-server/index.yaml`

```yaml
164:        expected: |
165:          Return creatives from your library. Each creative should include:
166:          - creative_id (your platform's identifier)
167:          - format_id referencing the creative's format
168:          - name and status (approved, pending_review, rejected)
169:          - concept_id grouping related creatives across sizes
170:          - pricing_options array with pricing_option_id, model, cpm, currency —
```

and the actual graded block for that same step:

```yaml
185:        validations:
186:          - check: response_schema
187:            description: "Response matches list-creatives-response.json schema. Validates pricing_options shape when present; absence is conformant for agents that bill out of band."
188:
189:          - check: field_present
190:            path: "context"
191:            description: "Response echoes back the context object"
192:          - check: field_value
193:            path: "context.correlation_id"
194:            value: "creative_ad_server--list_creatives"
```

Header for the same file, showing the gate:

```yaml
1:id: creative_ad_server
4:protocol: creative
5:category: creative_ad_server
```

### 2b. `universal/pagination-integrity.yaml` — graded for us, and it grades `list_creatives`

`/Users/konst/projects/adcp/dist/compliance/3.1.1/universal/pagination-integrity.yaml`

```yaml
 1:id: pagination_integrity
 5:summary: "Validates the cursor↔has_more invariant by walking a paginated list_creatives response from a continuation page to a terminal page."
 6:track: core
 7:required_tools:
 8:  - list_creatives
```

```yaml
14:  Pagination is cursor-based across AdCP. Every response carrying a
15:  `pagination` block satisfies a single invariant: when `has_more` is true the
16:  `cursor` MUST be present (callers need it to fetch the next page); when
17:  `has_more` is false the `cursor` MUST be absent (a stale token on a terminal
18:  page invites callers to follow it into undefined behavior).
19:
20:  The invariant is documented in prose on
21:  `static/schemas/source/core/pagination-response.json` but JSON Schema does
22:  not gate the two fields against each other.
```

```yaml
41:  `query_summary.total_matching` is required by the response schema and
42:  asserted unconditionally; `query_summary.returned` MUST equal the size
43:  of each page's slice (2 on the continuation page, 1 on the terminal
44:  page) — drift here flags an agent whose summary numbers don't match
45:  what it actually emitted.
```

First-page (continuation) graded checks:

```yaml
174:          - check: field_value
175:            path: "pagination.has_more"
176:            value: true
178:          - check: field_present
179:            path: "pagination.cursor"
180:            description: "has_more=true requires a cursor — without one the caller cannot continue"
181:          - check: field_value
182:            path: "query_summary.total_matching"
183:            value: 3
185:          - check: field_value
186:            path: "query_summary.returned"
187:            value: 2
189:          - check: field_value_or_absent
190:            path: "pagination.total_count"
191:            allowed_values: [3]
```

Terminal-page graded checks:

```yaml
249:          - check: field_value
250:            path: "pagination.has_more"
251:            value: false
253:          - check: field_value_or_absent
254:            path: "pagination.cursor"
255:            allowed_values: [null]
256:            description: "Terminal page MUST omit cursor (null also accepted for clients that explicitly clear the field)"
257:          - check: field_value
258:            path: "query_summary.total_matching"
259:            value: 3
261:          - check: field_value
262:            path: "query_summary.returned"
263:            value: 1
265:          - check: field_value_or_absent
266:            path: "pagination.total_count"
267:            allowed_values: [3]
```

---

## 3. Schema constraints at 3.1.1 — verbatim + file

All quoted from `git show v3.1.1:dist/schemas/3.1.1/...` in `/Users/konst/projects/adcp`.

### `core/creative-filters.json` — `concept_ids` IS a valid request filter, in CORE (not specialism-gated)

```json
"concept_ids": {
  "type": "array",
  "description": "Filter by creative concept IDs. Concepts group related creatives across sizes and formats (e.g., Flashtalking concepts, Celtra campaign folders, CM360 creative groups).",
  "items": { "type": "string" },
  "minItems": 1
}
```

### `creative/list-creatives-request.json` — the `fields` projection knows `concept`

```json
"fields": {
  "type": "array",
  "description": "Specific fields to include in response (omit for all fields). The 'concept' value returns both concept_id and concept_name.",
  "minItems": 1,
  "items": { "type": "string", "enum": [ ..., "concept", "pricing_options" ] }
}
```

Worked example carried in the schema itself:

```json
{
  "description": "List creatives in a specific concept matching a format",
  "data": { "filters": { "concept_ids": ["concept_holiday_2026"], "format_ids": [...] }, "include_variables": true }
}
```

### `creative/list-creatives-response.json` — `concept_id` / `concept_name` ARE 3.1.1 creative fields

```json
"concept_id": {
  "type": "string",
  "description": "Creative concept this creative belongs to. Concepts group related creatives across sizes and formats."
},
"concept_name": {
  "type": "string",
  "description": "Human-readable concept name"
}
```

Both are **optional** — the creative object's `required` list is:

```json
"required": ["creative_id", "name", "format_id", "status", "created_date", "updated_date"]
```

So "carries concept_id" is not a schema MUST. It is a MUST *for creatives the seller returned in
response to a `concept_ids` filter* — a filter that matched implies membership, and membership is
what `concept_id` reports. That's the real obligation; state it that way.

Response-level requirements — **`pagination` is required**, confirming the prior finding:

```json
"required": ["query_summary", "pagination", "creatives"]
```

`query_summary` own requirements:

```json
"required": ["total_matching", "returned"]
```

with

```json
"total_matching": { "type": "integer", "description": "Total number of creatives matching filters (across all pages)", "minimum": 0 },
"returned":       { "type": "integer", "description": "Number of creatives returned in this response",                "minimum": 0 }
```

`filters_applied` (optional, `array` of `string`); the schema's own example demonstrates the exact
encoding production uses:

```json
"filters_applied": ["concept_ids=concept_holiday_2026", "statuses=approved"]
```

### `core/pagination-response.json` — the cursor↔has_more invariant is prose only

```json
"properties": {
  "has_more": { "type": "boolean", "description": "Whether more results are available beyond this page" },
  "cursor":   { "type": "string",  "description": "Opaque cursor to pass in the next request to fetch the next page. Only present when has_more is true." },
  "total_count": { "type": "integer", "minimum": 0, "description": "Total number of items matching the query across all pages. Optional because not all backends can efficiently compute this." }
},
"required": ["has_more"],
"additionalProperties": false
```

`"Only present when has_more is true"` is a description string. JSON Schema does not gate the two
fields against each other — exactly as `pagination-integrity.yaml:20-22` says. It has to be asserted
by a Then step or it is not asserted at all.

### Pinned-fixture drift check (good news)

`tests/fixtures/adcp_schemas_pinned/creative/list-creatives-response.json` already has
`required: ["query_summary","pagination","creatives"]`, `query_summary.required:
["total_matching","returned"]`, and both `concept_id` / `concept_name` on the creative object;
`tests/fixtures/adcp_schemas_pinned/core/pagination-response.json` is identical to 3.1.1 on every
field quoted above; `tests/fixtures/adcp_schemas_pinned/core/creative-filters.json` has
`concept_ids`. **No fixture re-pin is needed for this scenario's surface.**

---

## 4. Conflicts

**Schema over storyboard.** The 3.1.1 schema layer *defines* `concept_ids` (request filter) and
`concept_id` / `concept_name` (response fields) in **core**, not in a specialism. The storyboard layer
mentions them only in ungraded prose inside a specialism we don't declare. **Schema wins:** the
behavior is real, binding, and worth a scenario — but it is graded by schema conformance, not by a
storyboard phase. The scenario stays; the `@storyboard-v3.1` tag and the storyboard-flavored
`@source` footer go.

**Current scenario — what's wrong or missing:**

| # | Issue | Severity |
|---|---|---|
| 1 | `@storyboard-v3.1` claims storyboard grading that does not exist at 3.1.1 (§1) | wrong |
| 2 | `@source` cites `ref=v3.1-04f59d2d5` — 226 commits behind, and points at a `static/schemas/source/` path rather than the version-stamped `dist/schemas/3.1.1/` tree | stale |
| 3 | No assertion on `pagination` at all — a **schema-required** response member, and the one thing here that IS storyboard-graded (`universal/pagination-integrity.yaml`) | missing |
| 4 | No assertion on `query_summary.total_matching` / `.returned` — both schema-required, both graded universally | missing |
| 5 | No assertion on the cursor↔has_more invariant. Prose-only, so a Then step is the only place it can live | missing |
| 6 | Single hard-coded concept id. No coverage of multi-`concept_ids` union, no coverage of a filter that matches nothing (the `total_matching: 0` / `returned: 0` case) | thin |
| 7 | No assertion on `query_summary.filters_applied` echoing the applied filter — POST-S7 in this feature's own postcondition list, and the 3.1.1 response example shows the exact encoding | missing |
| 8 | Scenario is a flat `Scenario`, not a `Scenario Outline`; the concept id, the expected member count and the decoy set are all buried in step prose | style / brief |

**Not wrong, keep as-is:** the existing exact-set falsifiability anchor
(`test_uc018_list_creatives.py:354-358`, `returned_ids == set(ctx["in_concept_creative_ids"])`) and
the `_wire_creatives` loud guard (`:335-336`) that refuses to fall back to a re-serialization on a
real-wire transport. Both are good and the rewrite preserves them.

**Production gap surfaced by this exercise (do not silently absorb):**
`src/core/tools/creatives/listing.py:416-419` constructs

```python
pagination=SchemaPagination(
    has_more=has_more,
    total_count=total_count,
),
```

— it **never emits a `cursor`**, on any page, while `has_more` is computed as
`(page * limit) < total_count` (`listing.py:349`) and can be `True`. That violates the
`has_more: true ⇒ cursor present` half of `pagination-integrity.yaml:174-180`, which is
**universal** and therefore genuinely on our conformance path. The rewrite below deliberately
contains only `has_more: false` rows so the scenario lands green; the continuation half is called
out in §8 with the scenario that should own it.

---

## 5. Proposed Gherkin

Complete replacement for `BR-UC-018-list-creatives.feature:787-800`.

```gherkin
  @T-UC-018-storyboard-filter-by-concept-id @schema-v3.1 @v3-1 @list-filter @concept-id
  Scenario Outline: filters.concept_ids scopes the library to the requested concepts -- <case>
    Given the authenticated principal has creatives grouped by concept:
      | concept_id          | concept_name         | creative_count |
      | concept_summer_2026 | Summer 2026 Campaign | 2              |
      | concept_winter_2025 | Winter 2025 Campaign | 1              |
    And the authenticated principal also has 1 creative that belongs to no concept
    When the Buyer Agent sends list_creatives with filters.concept_ids [<requested_concept_ids>]
    Then the response should be schema-valid against list-creatives-response.json
    And the creatives array should contain exactly <returned> creatives
    And the returned creative_ids should equal exactly the seeded members of the requested concepts
    And every returned creative should carry a concept_id drawn from the requested concept_ids
    And every returned creative should carry the concept_name seeded for its own concept_id
    And the query_summary shows total_matching as <total_matching> and returned as <returned>
    And the query_summary filters_applied should record the requested concept_ids
    And the pagination shows has_more as false
    And the pagination carries no cursor
    And the pagination total_count equals the query_summary total_matching
    # AdCP 3.1.1 core/creative-filters.json defines `concept_ids` (array of concept-id
    # strings, minItems 1); concepts group related creatives across sizes and formats.
    # creative/list-creatives-response.json defines creatives[].concept_id and
    # creatives[].concept_name (both optional on the object, but a creative returned in
    # answer to a concept_ids filter matched BY membership, so it MUST report that
    # membership). The response `required` set is [query_summary, pagination, creatives];
    # query_summary `required` is [total_matching, returned]; core/pagination-response.json
    # `required` is [has_more] with `cursor` documented "Only present when has_more is
    # true" in PROSE ONLY -- JSON Schema does not gate the two fields against each other,
    # so the has_more/cursor pairing is asserted here or nowhere. Every row below fits on
    # one page (default max_results 50), so every row is a terminal page: has_more false,
    # cursor absent. The continuation half of the invariant (has_more true => cursor
    # present) is graded by universal/pagination-integrity.yaml and belongs to
    # @T-UC-018-edge-pagination-next -- see GH #1739 discussion; production does not emit
    # a cursor today.
    #
    # NOT storyboard-graded for this agent: the only 3.1.1 storyboard mentioning concept_id
    # is specialisms/creative-ad-server/index.yaml:169, and (a) it is ungraded `expected:`
    # prose rather than a `validations:` check, and (b) we declare
    # specialisms=[sales_non_guaranteed], not creative-ad-server. Schema-graded only --
    # hence @schema-v3.1, not @storyboard-v3.1.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 phase=ungraded-by-storyboard
    #   path=dist/schemas/3.1.1/core/creative-filters.json
    #   path=dist/schemas/3.1.1/creative/list-creatives-response.json
    #   path=dist/schemas/3.1.1/core/pagination-response.json
    #   path=dist/compliance/3.1.1/universal/pagination-integrity.yaml

    Examples: Concept filter partitions the library
      | case                                     | requested_concept_ids                          | total_matching | returned |
      | one concept spanning two formats         | "concept_summer_2026"                          | 2              | 2        |
      | a different concept with a single member | "concept_winter_2025"                          | 1              | 1        |
      | two concept ids return the union         | "concept_summer_2026", "concept_winter_2025"   | 3              | 3        |
      | an unknown concept id returns no members | "concept_does_not_exist"                       | 0              | 0        |
```

Why each row earns its place:

- **row 1** — the base case, and the only one the current scenario covers. Two members proves the
  filter is a set membership test, not a first-match.
- **row 2** — the decoy from row 1 becomes the target. Proves the filter is parameterised, not a
  hard-coded id. Kills a `return everything that has any concept_id` implementation.
- **row 3** — union semantics across a multi-element `concept_ids` array. `minItems: 1` says the
  field is an array; nothing in the schema says one element. Kills a `concept_ids[0]` implementation.
- **row 4** — the empty result. Forces `total_matching: 0` / `returned: 0` and a well-formed,
  schema-valid `pagination` block on an empty page — the case where a naive implementation returns
  `null` or drops `pagination` entirely and violates the response `required` set. Also the only row
  where "every returned creative..." passes vacuously, which is precisely why the exact-count and
  exact-id-set assertions carry it.

The unconcepted creative from the second `Given` is never in an expected set, on any row — it is a
permanent negative control for "the filter didn't just return the whole library."

Transport-independence: every step is dispatched through `_call_via` and asserted against
`ctx["wire_response"]`. No transport appears anywhere in the Gherkin or the Examples.

---

## 6. Step inventory

### Reuse verbatim — phrasing already exists in this feature file (currently dormant, asserted by no step)

| Step text | Where the phrasing already appears |
|---|---|
| `the query_summary shows total_matching as <n> and returned as <n>` | `BR-UC-018-list-creatives.feature:42` (`@T-UC-018-main`) |
| `the pagination shows has_more as false` | `BR-UC-018-list-creatives.feature:44`, `:508` |

Wiring these in `test_uc018_list_creatives.py` makes them available to every scenario bound by
`scenarios()` — but the other UC-018 scenarios xfail at the conftest `_harness_env` fixture before
any step runs, so there is no behavioural collision. It does mean those two mainline scenarios become
cheaper to wire later, which is a win.

### Reuse the shape — near-identical steps exist in a sibling module (not importable, pytest-bdd resolves per-module)

| Existing | File |
|---|---|
| `the response includes pagination metadata with has_more {has_more} and a cursor` | `tests/bdd/steps/domain/uc011_accounts.py:604` |
| `the response includes pagination metadata with has_more {has_more}` | `tests/bdd/steps/domain/uc011_accounts.py:615` |

I deliberately did **not** adopt the uc011 phrasing: it is weaker than what 3.1.1 requires (it asserts
`cursor is not None` only when `has_more` is true, and never asserts cursor **absence** on a terminal
page — the half `pagination-integrity.yaml:253-256` grades). The UC-018 feature's own
`the pagination shows has_more as false` phrasing is the better base, plus an explicit
`the pagination carries no cursor`.

### Reuse as-is — already implemented in the UC-018 module

| Step | Implementation |
|---|---|
| `the response should be schema-valid against {schema_file}` | `test_uc018_list_creatives.py:195` |
| helper `_wire_creatives(ctx)` (real wire bytes + loud guard) | `test_uc018_list_creatives.py:320` |
| helper `_seed_creative(...)` (CreativeFactory + concept blob merge) | `test_uc018_list_creatives.py:86` |
| helper `_serialized_response(ctx)` | `test_uc018_list_creatives.py:177` |

### Modify

| Step | Change |
|---|---|
| `@when ... filters.concept_ids [(?P<concept_list>.+)]` (`:296`) | **Keep unchanged.** The existing `re.findall(r'"([^"]+)"', ...)` already parses a multi-element list, so row 3 works with no edit. It already stashes `ctx["requested_concept_ids"]`, which the new `filters_applied` step consumes. |
| `@given 'the authenticated principal has creatives grouped under concept "{x}" and other creatives under different concepts'` (`:249`) | **Replace** with the datatable form below. |
| `@then 'the creatives array should only include creatives belonging to concept "{x}"'` (`:342`) | **Replace.** Splits into an exact-count step and an exact-id-set step; the current version hard-asserts non-empty, which row 4 legitimately violates. |
| `@then 'each returned creative should carry concept_id "{x}" and a concept_name'` (`:361`) | **Replace.** Single-concept-only, and asserts `concept_name` merely non-empty rather than equal to the seeded name. |

### New — 7 step definitions, all in `test_uc018_list_creatives.py`

| Step text | Assertion (concrete comparison, no truthiness) |
|---|---|
| `Given the authenticated principal has creatives grouped by concept:` + datatable | Seeds `int(row.creative_count)` creatives per row via `_seed_creative(..., concept_id=, concept_name=)`; stashes `ctx["seeded_by_concept"] = {concept_id: {"name": ..., "ids": [...]}}`. pytest-bdd ≥7 `datatable` fixture — same mechanism as `tests/bdd/steps/generic/then_payload.py:249`. |
| `Given the authenticated principal also has 1 creative that belongs to no concept` | One `_seed_creative(...)` with no concept kwargs; stashes its id as `ctx["unconcepted_creative_id"]`. |
| `Then the creatives array should contain exactly <n> creatives` | `len(_wire_creatives(ctx)) == int(n)` |
| `Then the returned creative_ids should equal exactly the seeded members of the requested concepts` | `{e["creative_id"] for e in wire} == union of seeded ids over ctx["requested_concept_ids"]` (empty set on row 4). Also asserts `ctx["unconcepted_creative_id"] not in returned`. |
| `Then every returned creative should carry a concept_id drawn from the requested concept_ids` | for each entry: `entry.get("concept_id") in set(ctx["requested_concept_ids"])`, reporting offenders. |
| `Then every returned creative should carry the concept_name seeded for its own concept_id` | for each entry: `entry["concept_name"] == ctx["seeded_by_concept"][entry["concept_id"]]["name"]` — an equality, not a non-empty check. |
| `Then the query_summary filters_applied should record the requested concept_ids` | `"concept_ids=" + ",".join(ctx["requested_concept_ids"]) in wire["query_summary"]["filters_applied"]`. Encoding matches `listing.py:363-364` and the 3.1.1 response example. |
| `Then the pagination carries no cursor` | `wire["pagination"].get("cursor") is None` **and** `wire["pagination"]["has_more"] is False` — asserts the invariant pairing, not just field absence. |
| `Then the pagination total_count equals the query_summary total_matching` | `wire["pagination"]["total_count"] == wire["query_summary"]["total_matching"]` (mirrors `field_value_or_absent` at `pagination-integrity.yaml:265-268`; production always volunteers it — `listing.py:418`). |
| `Then the query_summary shows total_matching as <n> and returned as <n>` | two integer equalities against the wire. Phrasing reused from feature line 42. |
| `Then the pagination shows has_more as false` | `wire["pagination"]["has_more"] is False`. Phrasing reused from feature lines 44 / 508. |

All eleven assert on `_wire_creatives`-style wire bytes (extend the helper to return the whole wire
document, not just `creatives`) so `query_summary` / `pagination` are checked on what the buyer
actually receives, matching the existing `#1503` discipline in this module.

Guard compliance: every Then compares two concrete values, so
`test_architecture_bdd_no_trivial_assertions.py` and `test_architecture_bdd_no_pass_steps.py` are
satisfied. The datatable Given builds ORM rows through `CreativeFactory`, not a raw dict registry, so
`test_architecture_bdd_no_dict_registry.py` is satisfied. No step body is a duplicate of another, so
`test_architecture_bdd_no_duplicate_steps.py` is satisfied.

---

## 7. e2e_rest realizability

**Correction to the brief: this scenario is not on the ledger.** `tests/bdd/e2e_rest_known_failures.txt`
contains zero lines matching `concept` and zero matching `uc018`. Every entry in that file is
`get_products_inventory_profile` / `uc004` / `uc005` / `uc006` / `uc011`. There is nothing here to
graduate off #1739.

That is the expected result, and it stays true after the rewrite. The mechanism the ledger exists for
is *in-process mock injection* (`set_registry_formats`, `set_adapter_response`, account billing-state
fixtures) — state a separate HTTP server process cannot see. This scenario's setup is
`CreativeFactory` writing rows into the shared test **database**, which the e2e_rest server reads
over the same connection string. The rewrite keeps exactly that mechanism: the new datatable Given
still routes through `_seed_creative` → `CreativeFactory`, and adds no registry or adapter mock.

One dependency to keep an eye on: `_seed_creative` layers `concept_id` / `concept_name` into the
creative's `data` JSON blob (`test_uc018_list_creatives.py:110-116`) because adcp 5.7.0 standardises
no concept **input** on `sync_creatives` (`listing.py:316-326`). That is a DB write, so it is
e2e_rest-safe. If a future change moves concept seeding to an in-process registry, this scenario
lands on the ledger — don't.

---

## 8. Risks

1. **The cursor gap is real and this rewrite does not close it.** `listing.py:416-419` never emits a
   `cursor`, while `has_more` can be `True` (`listing.py:349`). That fails
   `pagination-integrity.yaml:174-180`, which is universal and therefore genuinely graded for us. The
   rewrite is all-terminal-page so it stays green. The right home for the other half is the already
   present, currently dormant `@T-UC-018-edge-pagination-next` (feature `:514-521`), which literally
   says *"the pagination includes a cursor for the next page"*. Wiring it will go **RED**. That is the
   correct outcome — file it, don't soften it. Per repo discipline, either fix production in the same
   change or land the scenario with an explicit, cited xfail entry; do not drop the assertion.

2. **Tag rename touches `docs/test-obligations/bdd-traceability.yaml`** if you rename the
   `@T-UC-018-storyboard-*` identifier. My recommendation is to change only
   `@storyboard-v3.1` → `@schema-v3.1` and leave the identifier alone — zero extra files.
   The same "storyboard" misnomer applies to its two neighbours,
   `@T-UC-018-storyboard-list-all-creatives-after-sync` (`:759`) and
   `@T-UC-018-storyboard-filter-by-format-id-object` (`:773`) — both also carry `@storyboard-v3.1`
   and both cite `protocols/creative/index.yaml`, a *protocol* storyboard for a protocol
   (`creative`) we do not declare in `supported_protocols`. Out of scope here, but they are the same
   defect and should get the same treatment in a follow-up.

3. **The feature file header says `DO NOT EDIT` (`:1-2`).** Per
   `project_bdd_authoritative_sources`, generated `BR-*.feature` files CAN be edited locally —
   generation merges semantically and local edits are not overwritten. The diff should still be
   mirrored upstream so the generator stops emitting the wrong tag.

4. **Wiring `the query_summary shows total_matching as ... and returned as ...` and
   `the pagination shows has_more as false` makes those phrasings resolvable for other UC-018
   scenarios** that currently use them (feature lines 42, 44, 508). Those scenarios xfail at the
   conftest `_harness_env` fixture before any step executes, so nothing changes today — but if
   someone later un-dorments them, they inherit these implementations. That is desirable; just don't
   be surprised by it.

5. **Row 4 (`concept_does_not_exist`) depends on the repository treating an unmatched
   `concept_ids` filter as an empty result, not an error.** Production passes `concept_ids` straight
   through (`listing.py:181`, `:237`) with no existence check, so an empty page is what comes back.
   Worth confirming on first run — if it 404s, that is a finding, not a scenario bug.

6. **`filters_applied` is optional in the schema** but production always populates it for
   `concept_ids` (`listing.py:363-364`). The new step asserts membership, which is stricter than the
   schema. That is intentional (POST-S7 is one of this feature's declared postconditions) and it is
   the encoding the 3.1.1 response example demonstrates — but it is a production-behaviour assertion,
   not a spec MUST. Flagging so nobody later mistakes it for one.

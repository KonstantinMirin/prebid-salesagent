# Re-pin proposal — `@T-UC-018-storyboard-filter-by-format-id-object`

Scenario: `tests/bdd/features/BR-UC-018-list-creatives.feature:773-785`
Title (current): *"List creatives filtered by a format_id object returns only creatives matching that {agent_url, id}"*

---

## 1. VERDICT

**NOT GRADED — undeclared gate.**

The behaviour *is* graded at 3.1.1, but only inside the **`creative` protocol baseline**
(`protocols/creative/index.yaml`). `src/core/tools/capabilities.py:98-99` declares
`supported_protocols=[SupportedProtocol.media_buy]` and `specialisms=[AdcpSpecialism.sales_non_guaranteed]`
— **`creative` is not declared**, so `protocols/creative/` is not on our conformance path.
`dist/compliance/3.1.1/index.json` lists `creative` as a first-class protocol tier
(`{"id": "creative", "title": "Creative lifecycle", "has_baseline": true, "path": "protocols/creative/"}`),
i.e. it is opt-in per declared protocol, exactly like `media-buy`. The storyboard additionally gates on an
agent capability we never declare (`agent.capabilities: [has_creative_library]`,
`protocols/creative/index.yaml:26-28`).

**Second, independent reason the storyboard tag is unjustified:** even for an agent that *does* declare
`creative`, the graded `validations:` for the bound step **do not grade exclusion at all**. "Only creatives
matching that format are returned" appears solely under `expected:` — narrative prose. The five graded
checks are schema-validity, `creatives` presence, `context` presence, `context.correlation_id` echo, and an
*inclusion* check (`creatives[0].creative_id == synced_creative_id`). The scenario's entire premise — the
word *only* — is ungraded by the storyboard.

**Action:** `@storyboard-v3.1` → `@schema-v3.1`. The exclusion semantics survive as an obligation, but
sourced from the **JSON schema**, not the storyboard (see §3). Keep `@T-UC-018-storyboard-filter-by-format-id-object`
unchanged (referenced at `docs/test-obligations/bdd-traceability.yaml:10555`).

This matches the sibling verdict already reached for `@T-UC-018-storyboard-filter-by-concept-id` — same
class, independently reached here.

---

## 2. Real binding at 3.1.1

**This is one of the ~24 scenarios whose cited `path=` is actually CORRECT.** Only the `ref`/`commit` is
stale. `static/compliance/source/protocols/creative/index.yaml` exists at `v3.1.1` and is byte-identical to
the built `dist/compliance/3.1.1/protocols/creative/index.yaml` (verified by `diff`). No off-by-one here.

| | value |
|---|---|
| Current footer | `ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/creative/index.yaml` |
| Correct footer | `ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/creative/index.yaml phase=list_and_filter step=list_filtered` |

`v3.1.1` = commit `467fd93d77112baf9e094e18980119edcd3a4d07`.

Storyboard id `creative_lifecycle`, tier **`protocols/`** (mirrored verbatim into `domains/creative/` — the
`domains/` copy is generated; only `protocols/` exists in `static/compliance/source/` at v3.1.1).

Real location: **`protocols/creative/index.yaml:248`** (phase `list_and_filter`, line 195; step
`list_filtered`, line 248). Graded block verbatim, **lines 277-294**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches list-creatives-response.json schema"
          - check: field_present
            path: "creatives"
            description: "Response contains filtered creatives"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "creative_lifecycle--list_filtered"
            description: "Context correlation_id returned unchanged"
          - check: field_equals_context
            path: "creatives[0].creative_id"
            context_key: "synced_creative_id"
            description: "Filtered list_creatives returns the display creative synced earlier"
```

The *ungraded* prose immediately above it (lines 259-262) is where "only" lives:

```yaml
        expected: |
          Return only creatives matching the format filter:
          - creatives array filtered to display format
          - Should include display_trail_pro_300x250
```

The storyboard's own `sample_request` (lines 264-274) confirms the object shape under test:

```yaml
          filters:
            format_ids:
              - agent_url: "https://your-platform.example.com"
                id: "display_300x250"
```

---

## 3. Schema constraints at 3.1.1

Read via `git show v3.1.1:static/schemas/source/<path>` in `/Users/konst/projects/adcp`.

### `core/format-id.json` — the filter entry shape

```json
  "title": "Format Reference (Structured Object)",
  "description": "A JSON object — never a plain string — that identifies a creative format by its
   declaring agent and local slug. ... Using a plain string here is a schema violation.",
  "type": "object",
  "required": ["agent_url", "id"],
```
`id` carries `"pattern": "^[a-zA-Z0-9_-]+$"`. `agent_url` carries the comparison mandate:

```json
"Callers comparing two `format-id` values MUST canonicalize `agent_url` per the AdCP URL
 canonicalization rules before treating two formats as the same. See docs/reference/url-canonicalization."
```

### `core/creative-filters.json` — `format_ids`

```json
    "format_ids": {
      "type": "array",
      "description": "Filter by structured format IDs. Returns creatives that match any of these formats.",
      "items": { "$ref": "/schemas/core/format-id.json" },
      "minItems": 1
    },
```

**This is the authority for the exclusion behaviour.** *"Returns creatives that match any of these
formats"* is a schema-level definition of filter semantics — the schema **defines** it, so the schema wins
and production is the drifted side. (Contrast the storyboard, which grades only inclusion.) Where schema
and storyboard disagree here, **the 3.1.1 schema wins**: the correct behaviour is exclusion of
non-matching creatives; it is simply not gradeable via the storyboard and cannot land green today (§7).

### `creative/list-creatives-response.json`

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
  ...
  "required": ["query_summary", "pagination", "creatives"],
```
`creatives[]` items: `"required": ["creative_id", "name", "format_id", "status", "created_date", "updated_date"]`,
with `format_id` `$ref`-ing `core/format-id.json` (so the response's `format_id` is object-shaped, same
contract as the filter). `protocol-envelope.json` adds `required: ["status"]`.
`pagination` is **required** at 3.1.1 (it was not at the 04f59d2d5 pin the scenario currently cites).

---

## 4. Conflicts / what the scenario gets wrong

Everything below was verified by **executing production** against the worktree's agent-db
(`CreativeListEnv`, transports a2a/mcp/rest, seeded 3 creatives: `{A, display_300x250}`,
`{A, video_640x480}`, `{B, display_300x250}` where A=`https://creative.adcontextprotocol.org`,
B=`https://other-agent.example.com`).

1. **`filters.format_ids` is silently dropped — the scenario's central claim is RED.**
   `_list_creatives_impl` (`src/core/tools/creatives/listing.py:216-269`) derives `status`, `tags`,
   `created_after/before`, `name_contains`, `media_buy_ids` and `concept_ids` from `req.filters` and
   threads them into `CreativeRepository.get_by_principal`. It **never reads `req.filters.format_ids`.**
   The repository's `format=` argument is fed only by the out-of-band flat `format` string
   (`listing.py:258`). Observed on all three transports: filter `{A, display_300x250}` returned
   **all three** creatives, `query_summary.total_matching: 3`. This is the identical defect class fixed
   for `concept_ids` in #1493 — the fix left `format_ids` behind.

2. **`filters_applied` claims a filter that was not applied, and leaks a Python repr onto the wire.**
   `listing.py:386-387` appends `f"format_ids={','.join(str(f) for f in req.filters.format_ids)}"`.
   Observed wire value:
   `"format_ids=agent_url=AnyUrl('https://creative.adcontextprotocol.org/') id='display_300x250' width=None height=None duration_ms=None"`.
   Two bugs in one line: an unapplied filter is reported as applied, and `str(FormatId)` (a Pydantic repr,
   including `AnyUrl(...)` and `None`s) is emitted as buyer-facing data.

3. **Scenario title and Thens assert `only` — unsupported by production and ungraded by the storyboard.**
   The two exclusion Thens ("should only include…", "should NOT include…") cannot land green.

4. **Stale `ref`.** `v3.1-04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin.

5. **`then_response_schema_valid` validates against a schema tree vendored at 04f59d2d5**, not 3.1.1
   (`tests/fixtures/adcp_schemas_pinned/`). It *does* run a real validator here — the UC-018 module binds
   `tests/helpers/pinned_schema.py::validate_against_pinned_schema`
   (`tests/bdd/test_uc018_list_creatives.py:217-220`), so the brief's "runs no validator" note applies to
   a different definition, not this one. But it grades the wrong version: 3.1.1's `pagination`-required and
   `protocol-envelope` `status`-required constraints are not enforced by the vendored copy.

6. **Correction to a brief bullet, measured:** REST does **not** drop `pagination` on this tool. Observed
   REST wire top-level keys: `['creatives', 'pagination', 'query_summary', 'replayed', 'status']` —
   `pagination` and `status: "completed"` both present. REST drops `context` and the summary blocks only.
   MCP's `structured_content` capture is pre-JSON (it carries live `FormatId` objects and `None`-valued
   envelope slots), which is why a wire-based schema assertion passes on REST and fails on MCP — the
   existing UC-018 steps correctly assert on `model_dump(mode="json", exclude_none=True)` instead.

7. **The scenario is dormant.** `tests/bdd/conftest.py:3403-3413` wires the UC-018 harness only for
   markers `{list-after-sync, concept-id, BR-RULE-034}`; everything else `pytest.xfail`s at the fixture.
   Re-pinning the tag without adding `format-id-object` to that set leaves it dormant.

---

## 5. Proposed Gherkin — GREEN ONLY

Replaces `BR-UC-018-list-creatives.feature:773-785`. Every assertion below was executed against
production on a2a/mcp/rest before being written down.

```gherkin
  @T-UC-018-storyboard-filter-by-format-id-object @schema-v3.1 @v3-1 @list-filter @format-id-object
  Scenario: A well-formed format_id object filter is accepted and the matching creative round-trips its {agent_url, id}
    Given the buyer has synced a creative with format id "display_300x250" on agent url "https://creative.adcontextprotocol.org"
    And the buyer has synced a creative with format id "video_640x480" on agent url "https://creative.adcontextprotocol.org"
    When the Buyer Agent sends list_creatives with filters.format_ids [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"}]
    Then the response should be schema-valid against list-creatives-response.json
    And the creatives array should include the creative synced with format id "display_300x250" on agent url "https://creative.adcontextprotocol.org"
    And that creative's format_id should carry id "display_300x250" and agent_url "https://creative.adcontextprotocol.org" after URL canonicalization
    # A filters.format_ids entry is an object, never a bare string: core/format-id.json
    # requires [agent_url, id] and states plainly that "using a plain string here is a
    # schema violation". Comparison of two format-id values MUST canonicalize agent_url
    # first (same file), so the round-trip Then compares canonicalized forms — production
    # normalizes through AnyUrl and returns a trailing slash the buyer never sent.
    # Retagged @schema-v3.1 (was @storyboard-v3.1): the binding storyboard below is the
    # `creative` PROTOCOL baseline, and src/core/tools/capabilities.py declares only
    # supported_protocols=[media_buy] — protocols/creative/ is not on our conformance
    # path. Independently, the storyboard step grades exclusion nowhere: "only creatives
    # matching the format filter" is `expected:` prose, while `validations:` grades
    # response_schema + creatives present + context echo + creatives[0].creative_id
    # INCLUSION. The `only` semantics are schema-sourced (core/creative-filters.json
    # format_ids: "Returns creatives that match any of these formats") and are NOT
    # asserted here because production drops filters.format_ids entirely — see #<FILTER>.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/creative/index.yaml phase=list_and_filter step=list_filtered

  @T-UC-018-format-id-object-filter-shape @schema-v3.1 @v3-1 @list-filter @format-id-object
  Scenario Outline: A filters.format_ids entry that is not a {agent_url, id} object is rejected -- <violation>
    Given the buyer has synced a creative with format id "display_300x250" on agent url "https://creative.adcontextprotocol.org"
    When the Buyer Agent sends list_creatives with a raw filters.format_ids payload <payload>
    Then the operation should fail
    And the error code should be "VALIDATION_ERROR"
    And the error recovery should be "correctable"
    And the error should include a "suggestion" field

    Examples: Shapes core/format-id.json forbids
      | violation                          | payload                         |
      | bare string instead of an object   | ["display_300x250"]             |
      | object missing required agent_url  | [{"id": "display_300x250"}]     |
      | empty array violates minItems 1    | []                              |
    # core/format-id.json: type object, required [agent_url, id], "Using a plain string
    # here is a schema violation". core/creative-filters.json: format_ids minItems 1.
    # All three rows verified rejected on a2a/mcp/rest with code VALIDATION_ERROR,
    # recovery "correctable", non-empty suggestion. The envelope's `field` value is
    # deliberately NOT asserted: it is transport-dependent (`format_ids[0]` on a2a/rest,
    # `filters.format_ids[0]` on mcp) — see #<FIELDPATH>.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/schemas/source/core/format-id.json
```

Wiring changes the rewrite depends on (both mechanical, both in scope for the same PR):

- `tests/bdd/conftest.py:3404` — extend the wired marker set to
  `{"list-after-sync", "concept-id", "BR-RULE-034", "format-id-object"}`, otherwise both scenarios stay
  dormant behind the fixture xfail.
- `docs/test-obligations/bdd-traceability.yaml` — add next to the existing entry at line 10555:
  ```yaml
      - adcp_scenario_id: "T-UC-018-format-id-object-filter-shape"
        adcp_feature: "BR-UC-018-list-creatives.feature"
        obligation_id: null
        upstream_refs: ["BR-UC-018-main"]
        business_rules: []
        status: new
  ```
  `test_architecture_bdd_obligation_sync.py::test_bdd_scenarios_have_traceability_entries` fails without it.

---

## 6. Step inventory

**Existing — reused as-is (globally registered via `tests/bdd/conftest.py:49-72`):**

| Step | Location |
|---|---|
| `the operation should fail` | `tests/bdd/steps/generic/then_error.py:181` |
| `the error code should be "{code}"` | `then_error.py:270` (wire-first) |
| `the error recovery should be "{recovery}"` | `then_error.py:413` |
| `the error should include a "suggestion" field` | `then_error.py:426` (wire-first) |

**Existing — reused, module-scoped in `tests/bdd/test_uc018_list_creatives.py`:**

| Step | Location |
|---|---|
| `the response should be schema-valid against {schema_file}` | `test_uc018_list_creatives.py:217` |
| `the Buyer is authenticated as principal "{principal_id}"` (Background) | `test_uc018_list_creatives.py:148` |

Helpers to reuse rather than re-implement: `_seed_creative` (:86), `_get_or_create_tenant_and_principal`
(:123), `_serialized_response` (:199), `tests.bdd.steps.generic.when_request._call_via`.

**New — 4 steps, all in `test_uc018_list_creatives.py` (module scope, matching that file's stated
blast-radius policy):**

1. `Given the buyer has synced a creative with format id "{format_id}" on agent url "{agent_url}"`
   — `_seed_creative` extended with an `agent_url` kwarg (`CreativeFactory` already accepts `agent_url`);
   records `ctx["synced_by_format"][(agent_url, format_id)] = creative_id`.
2. `When the Buyer Agent sends list_creatives with filters.format_ids [<json>]`
   — parse the bracketed JSON, build through `adcp.CreativeFilters` (so minItems/shape validation runs
   client-side too), `model_dump(mode="json", exclude_none=True)`, dispatch via `_call_via(ctx, transport, filters=...)`.
   Mirrors the existing `when_list_creatives_concept_ids` (:315) exactly — same helper, same rationale.
3. `When the Buyer Agent sends list_creatives with a raw filters.format_ids payload <payload>`
   — deliberately **bypasses** `CreativeFilters` and passes the raw dict, so the rejection is produced by
   the server-side boundary (FastMCP TypeAdapter / A2A skill / REST body), not by the test.
4. `Then the creatives array should include the creative synced with format id "{format_id}" on agent url "{agent_url}"`
   + `Then that creative's format_id should carry id "{id}" and agent_url "{agent_url}" after URL canonicalization`
   — the second reads the entry recorded by (1) out of `_serialized_response(ctx)["creatives"]` and compares
   `format_id["id"]` exactly and `format_id["agent_url"]` after canonicalization (strip trailing `/`,
   lowercase scheme+host) per `core/format-id.json`.

**Deleted phrasings** (their claims are RED and move to §7): `the creatives array should only include
creatives whose format_id matches both agent_url and id`, `the creatives array should NOT include creatives
whose format_id has a different id even on the same agent_url`. Neither has a step definition today, so
nothing is orphaned.

---

## 7. TICKET MATERIAL

- **`list_creatives` silently ignores `filters.format_ids` — the filter is a no-op.**
  `src/core/tools/creatives/listing.py:216-269` builds the DB query from `req.filters` but never reads
  `req.filters.format_ids`; `CreativeRepository.get_by_principal`'s `format=` parameter
  (`src/core/database/repositories/creative.py`, `if format: stmt = stmt.where(Creative.format == format)`)
  is fed only by the out-of-band flat `format` string (`listing.py:258`). Measured on a2a/mcp/rest: a
  filter of `{agent_url: https://creative.adcontextprotocol.org, id: display_300x250}` against a library
  of 3 creatives (one matching) returned all 3, `query_summary.total_matching: 3`.
  Mandated by **3.1.1 `core/creative-filters.json`** → `format_ids`: *"Filter by structured format IDs.
  Returns creatives that match any of these formats."* Identical defect class to the `concept_ids` drop
  fixed in #1493 — `format_ids` was left behind by that fix.

- **Format matching must compare `(agent_url, id)`, not `id` alone.**
  The repository can only match `Creative.format` (the id slug); `Creative.agent_url` is stored
  (`listing.py:296` reads it back) but never participates in any filter predicate. Two creatives with the
  same `id` on different agents are indistinguishable to every filter path. Mandated by
  **3.1.1 `core/format-id.json`**: `required: ["agent_url", "id"]` plus *"Callers comparing two
  `format-id` values MUST canonicalize `agent_url` per the AdCP URL canonicalization rules before treating
  two formats as the same."* The fix needs a canonicalizing comparison (the AnyUrl round-trip already
  rewrites `https://x.example` → `https://x.example/`, so naive string equality is wrong in both
  directions).

- **`query_summary.filters_applied` reports `format_ids` as applied when it was not, and emits a Python
  repr on the wire.** `src/core/tools/creatives/listing.py:386-387`:
  `filters_applied.append(f"format_ids={','.join(str(f) for f in req.filters.format_ids)}")`. Measured wire
  value: `"format_ids=agent_url=AnyUrl('https://creative.adcontextprotocol.org/') id='display_300x250' width=None height=None duration_ms=None"`.
  **3.1.1 `creative/list-creatives-response.json`** defines `query_summary.filters_applied` as *"List of
  filters that were applied to the query"* with `items: {type: string}` — reporting an unapplied filter
  breaks the contract, and a Pydantic `__str__` is not a buyer-facing string. Fix both: report only
  filters actually pushed into the query, and format the entry from the object's fields.

- **Validation-error `field` path is transport-dependent.** Measured: a2a/rest emit
  `field: "format_ids[0]"`, mcp emits `field: "filters.format_ids[0]"` for the same malformed request;
  the a2a/rest `message` is the long "does not match the AdCP specification" narrative while mcp's is the
  bare Pydantic string. **3.1.1 `core/error.json`** types `field` as a single protocol-level pointer — one
  request shape must produce one pointer. This is why the proposed Outline asserts only
  `code`/`recovery`/`suggestion` (Pattern #5 transport parity).

- **Pinned schema fixtures are vendored at `04f59d2d5`, not 3.1.1.**
  `tests/fixtures/adcp_schemas_pinned/` — so `then_response_schema_valid`
  (`tests/bdd/test_uc018_list_creatives.py:217`) cannot enforce 3.1.1's
  `list-creatives-response.json` `required: ["query_summary", "pagination", "creatives"]` nor the
  `core/protocol-envelope.json` `required: ["status"]` that 3.1.1 adds via `allOf`. Re-vendor at
  `v3.1.1` (`467fd93d7`). Until then every `schema-valid against …` Then in the BDD suite grades a
  superseded contract.

- **UC-018 storyboard tags are unjustified across the file, not only here.** All three
  `@storyboard-v3.1` UC-018 scenarios bind `protocols/creative/index.yaml`, a protocol tier we do not
  declare (`src/core/tools/capabilities.py:98-99`, `supported_protocols=[media_buy]`). If we intend to
  claim the creative protocol, that is a capabilities change with its own conformance surface; if not,
  all three should read `@schema-v3.1`. (`list-after-sync` and `filter-by-concept-id` are owned by sibling
  agents in this sweep — flagged here only so the file ends up internally consistent.)

---

## 8. Risks

- **e2e_rest is unverified.** The three transports a2a/mcp/rest were executed; e2e_rest needs the full
  Docker stack. The wired UC-018 siblings currently xfail on e2e_rest, so the proposed scenarios should
  inherit that same treatment — but I could not confirm by execution that they xfail rather than error.
- **The rewrite is not literally executed.** I verified each assertion's underlying production behaviour
  by direct harness dispatch (temporary probe under `tests/integration/`, deleted afterwards —
  `git status` is clean, no repo file was modified). The Gherkin + step definitions themselves have not
  been run, because doing so requires the two wiring edits listed at the end of §5, which are out of my
  propose-only scope.
- **Trailing-slash canonicalization.** Production normalizes `agent_url` through Pydantic `AnyUrl`, which
  appends a trailing `/` to bare-host URLs. The proposed round-trip Then compares canonicalized forms, so
  it is green — but if a future change swaps the serializer, that step is the one that moves.
- **`the error recovery should be "correctable"`** reads the reconstructed `ctx["error"]`
  (`then_error.py:413-423`), not the wire envelope. I confirmed both agree here
  (`AdCPValidationError.recovery == "correctable"`, and every measured envelope carried
  `recovery: "correctable"`), but per `tests/CLAUDE.md` § Error Verification Policy the wire is the
  authority — that generic step is weaker than it looks and is worth hardening separately.
- **Drift note only, not authority:** at 3.1.8/HEAD the creative storyboard may have moved or gained
  graded exclusion checks. Not consulted for any decision above; we are pinned to 3.1.1.
- **`context` echo not asserted.** The storyboard grades `context.correlation_id` round-trip, and
  production does return `context=req.context` (`listing.py:450`). I did not verify that all four
  transports thread a caller-supplied `context` through, so I left it out rather than risk red. It is a
  cheap follow-up if someone confirms the plumbing.

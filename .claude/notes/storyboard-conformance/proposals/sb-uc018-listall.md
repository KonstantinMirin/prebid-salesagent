# Re-grounding `@T-UC-018-storyboard-list-all-creatives-after-sync` against AdCP 3.1.1

Scenario: `tests/bdd/features/BR-UC-018-list-creatives.feature:760`
"List creatives with no filters returns the library including recently synced creatives"
Steps: `tests/bdd/test_uc018_list_creatives.py` (inline, lines ~163–240)

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** The behaviour *is* graded at 3.1.1, but only inside the
**`creative` protocol** baseline storyboard, and we do not declare that protocol. The
`@storyboard-v3.1` tag must become **`@schema-v3.1`**.

Two things are true at once and both matter:

- The graded step exists and is real: `protocols/creative/index.yaml` → phase `list_and_filter`
  → step `list_all`, with a genuine `validations:` block (not prose). See §2.
- We do not claim it. `src/core/tools/capabilities.py:271` declares
  `supported_protocols=[SupportedProtocol.media_buy]` and `specialisms=[sales_non_guaranteed]`.
  The 3.1.1 capabilities schema makes `supported_protocols` the *literal* gate on this
  storyboard file (verbatim, `protocol/get-adcp-capabilities-response.json` at v3.1.1):

  > "AdCP protocols this agent supports. Stable values both (a) declare which tools the agent
  > implements and (b) **commit the agent to pass the baseline compliance storyboard at
  > `/compliance/{version}/protocols/{protocol}/`** (with snake_case → kebab-case path mapping,
  > e.g. `media_buy` → `/compliance/.../protocols/media-buy/`)."
  >
  > `items.enum`: `["media_buy", "signals", "governance", "sponsored_intelligence", "creative", "brand", "measurement"]`

  We commit to `/compliance/3.1.1/protocols/media-buy/`. `list_all` lives in
  `/compliance/3.1.1/protocols/creative/`. It is not on our conformance path.

The repo already knows this: `docs/test-obligations/storyboard-coverage-map.md:69` lists
`protocols/creative/index.yaml` → *"protocol 'creative' not declared"* → and names
`T-UC-018-storyboard-list-all-creatives-after-sync` among its orphans. The feature file's tag
just never caught up.

**Also note (deviation from the brief's assumption):** the `@source` **path** on this scenario is
**correct** — it is one of the ~24 that did *not* suffer the off-by-one. `static/compliance/source/protocols/creative/index.yaml`
exists at v3.1.1 and really does contain `list_all`. Only the **ref/commit is stale**
(`v3.1-04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin). Re-pin the ref, keep the path,
and add the phase/step coordinates it is currently missing.

Keep the opaque `@T-UC-018-…` tag (referenced from `docs/test-obligations/bdd-traceability.yaml:10549`).

---

## 2. Real binding at 3.1.1

**File:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/creative/index.yaml`
(byte-identical to `dist/compliance/3.1.1/domains/creative/index.yaml` — `diff` returns clean;
the generator emits the same storyboard into both trees. Source of record at the tag:
`static/compliance/source/protocols/creative/index.yaml`, same line numbers.)

**Storyboard header (lines 1–8, 23–30):**

```yaml
id: creative_lifecycle
version: "1.0.0"
title: "Creative lifecycle"
category: creative_lifecycle
track: creative
required_tools:
  - list_creative_formats
agent:
  interaction_model: stateful_push
  capabilities:
    - has_creative_library
```

**Phase / step (lines 195–214):**

```yaml
  - id: list_and_filter
    title: "List creatives with filtering"
    steps:
      - id: list_all
        title: "List all creatives in library"
        task: list_creatives
        schema_ref: "creative/list-creatives-request.json"
        response_schema_ref: "creative/list-creatives-response.json"
        comply_scenario: creative_lifecycle
        stateful: true
```

**Graded `validations:` — verbatim, lines 230–247:**

```yaml
        validations:
          - check: response_schema
            description: "Response matches list-creatives-response.json schema"
          - check: field_present
            path: "creatives"
            description: "Response contains creatives array"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "creative_lifecycle--list_all"
            description: "Context correlation_id returned unchanged"
          - check: field_equals_context
            path: "creatives[0].creative_id"
            context_key: "synced_creative_id"
            description: "list_creatives returns the creative synced earlier"
```

Five graded checks. Note what is **prose only** (`expected:`, lines 215–219) and therefore **not**
graded — the scenario's current Then steps are built almost entirely on this prose:

```
        expected: |
          Return creatives in the library:
          - creatives array containing the synced items
          - Each creative includes: creative_id, name, format_id, status
          - At least one creative from the sync phase
```

The "each creative exposes creative_id, name, format_id, status" claim the scenario asserts comes
from that ungraded prose. It is still worth asserting — but its authority is the **schema**
(`required` on `creatives[].items`), not the storyboard.

**Tier (question 3):** `protocols/` — top-level protocol `creative`
(`dist/compliance/3.1.1/index.json` → `protocols: [… {"id": "creative", "path": "protocols/creative/"} …]`).
Not universal, not a specialism. The identical `domains/creative/` copy does not change the gate.

**What the current footer points at:**

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/creative/index.yaml
```

Path right, ref wrong (04f59d2d5 predates 3.1.1; that file changed by 50+/107− lines between the two),
and no `phase=`/`step=` coordinates, so nothing pins *which* of the file's six steps is meant.

**Adjacent universal storyboard that touches this tool:**
`universal/pagination-integrity.yaml` (`track: core`, `required_tools: [list_creatives]`) grades the
cursor↔has_more invariant. Per the brief it is on our path; I flag one caveat in §8 — it also declares
`agent.capabilities: [has_creative_library]` and `requires: [controller]`, and `has_creative_library`
is defined on the capabilities response as a **sub-field of the `creative` block**, which the schema says
is *"Only present if creative is in supported_protocols."* So by the same gating rule that disqualifies
`list_all`, this universal may be gated off for us too. I did not resolve that; it changes only whether
the pagination ticket is "conformance failure" or "latent correctness bug".

---

## 3. Schema constraints at 3.1.1

`git show v3.1.1:static/schemas/source/creative/list-creatives-response.json`:

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
  ...
  "required": [ "query_summary", "pagination", "creatives" ],
  "additionalProperties": true
```

`query_summary` (required sub-fields):

```json
      "required": [ "total_matching", "returned" ]
```

`creatives[].items`:

```json
        "required": [
          "creative_id", "name", "format_id", "status", "created_date", "updated_date"
        ],
        "additionalProperties": true
```

`format_id` `$ref`s `/schemas/core/format-id.json` (object, `{agent_url, id}` — not a bare string);
`status` `$ref`s `/schemas/enums/creative-status.json`.

`git show v3.1.1:static/schemas/source/core/pagination-response.json`:

```json
  "properties": {
    "has_more": { "type": "boolean", … },
    "cursor":   { "type": "string", "description": "Opaque cursor to pass in the next request to fetch the next page. Only present when has_more is true." },
    "total_count": { "type": "integer", "minimum": 0, … }
  },
  "required": [ "has_more" ],
  "additionalProperties": false
```

`git show v3.1.1:static/schemas/source/core/protocol-envelope.json`:

```json
  "required": [ "status" ],
```

> "The `status` field is REQUIRED on every task response envelope, including synchronous metadata
> responses … Agents shipping responses without a top-level `status` are non-conformant regardless of
> whether the task body schema would otherwise validate."

**Delta 3.1.1 vs the vendored 04f59d2d5 pin** (`tests/fixtures/adcp_schemas_pinned/creative/list-creatives-response.json`):
the pinned copy already carries `required: [query_summary, pagination, creatives]` and the same
six-field `creatives[]` required list; the only material difference is the added
`protocol-envelope` ref (i.e. `status`). See §4 — we pass it anyway.

---

## 4. Conflicts, and what the scenario gets wrong

**Schema vs storyboard.** No contradiction on this step; the schema is strictly stronger.
The storyboard's prose says entries carry four fields; the **3.1.1 schema requires six**
(`created_date`, `updated_date` too). **The 3.1.1 schema wins** — the rewrite asserts six.

**Two claims in the shared brief are wrong for `list_creatives`; I verified both by execution.**
I dumped the real response on all three wired transports (read-only pytest plugin,
`pytest_bdd_after_scenario`; no repo file touched):

- *"No top-level `status` on responses"* — **false here.** `status: "completed"` is present on the
  typed response **and** on the a2a / mcp / rest wire dicts.
- *"REST drops `context` and `pagination`; MCP drops `pagination`"* — **false here.** Both wires carry
  `pagination` and `query_summary`; `src/routes/api_v1.py:459` returns the full `model_dump(mode="json")`.

I then validated the three dumps against the **real 3.1.1 schema** (full `$ref` closure extracted from
`v3.1.1`, Draft7): **0 errors on a2a, mcp and rest.** So our `list_creatives` response is 3.1.1-clean
today, including the new `protocol-envelope` `status` requirement.

**What the scenario is missing / asserting weakly:**

1. Asserts nothing about `query_summary`, though the schema *requires* it and POST-S2/POST-S7 are its
   whole point. Production emits `total_matching: 3, returned: 3, filters_applied: [], sort_applied:
   {field: created_date, direction: desc}`.
2. Asserts nothing about `pagination`, also schema-required. Production emits
   `{has_more: false, total_count: 3}`, no cursor.
3. Asserts four of the six schema-required creative fields — `created_date`/`updated_date` unchecked.
4. `then_each_creative_exposes_core_fields` is partly a **presence/non-empty** check
   (`entry[field] not in (None, "", {})`) rather than a value comparison — the class of assertion
   `test_architecture_bdd_no_trivial_assertions.py` exists to stop.
5. Never grades the storyboard's **only distinctive** checks: the `context` echo and
   `context.correlation_id` round-trip. That one is genuinely red — see §7.
6. Prose Then steps, no `Examples:` — nothing parametrized, so the default sort order
   (BR-RULE-147 INV-3, `created_date desc`) rides along unverified even though production honours it.

---

## 5. Proposed Gherkin — complete replacement (GREEN ONLY)

Every assertion below was executed against current production on **a2a, mcp and rest**
(`uv run pytest tests/bdd/test_uc018_list_creatives.py -k list_creatives_with_no_filters…`),
and the values are taken from the real dumps.

```gherkin
  @T-UC-018-storyboard-list-all-creatives-after-sync @schema-v3.1 @v3-1 @list-after-sync
  Scenario Outline: Unfiltered list_creatives returns the synced library -- <sync_order> synced creative
    Given the buyer recently synced three creatives in three different formats via sync_creatives
    When the Buyer Agent sends list_creatives with no filters for the same account
    Then the response should be schema-valid against list-creatives-response.json
    And the response envelope should carry status "completed"
    And the creatives array should include each of the synced creatives
    And each creative entry should expose creative_id, name, format_id, status, created_date and updated_date
    And the creative at position <position> should be the <sync_order> synced creative with format_id.id "<format_id>" and status "approved"
    And the query_summary should report total_matching 3, returned 3 and filters_applied []
    And the query_summary should report sort_applied field "created_date" direction "desc"
    And the pagination should report has_more false and total_count 3 with no cursor
    # 3.1.1 binding. This tool is graded ONLY inside the `creative` protocol baseline
    # storyboard, and get-adcp-capabilities-response.json (v3.1.1) makes
    # supported_protocols the gate: declaring a protocol "commit[s] the agent to pass the
    # baseline compliance storyboard at /compliance/{version}/protocols/{protocol}/".
    # src/core/tools/capabilities.py declares supported_protocols=[media_buy] only,
    # so protocols/creative/ is NOT on our conformance path -> @schema-v3.1, not
    # @storyboard-v3.1 (cf. docs/test-obligations/storyboard-coverage-map.md).
    # Assertions are therefore grounded in the 3.1.1 JSON schema, which is stricter than
    # the storyboard prose: creatives[] requires SIX fields (the prose lists four), and
    # query_summary/pagination are top-level `required`.
    # The storyboard's `context` / `context.correlation_id` echo checks are NOT asserted
    # here -- the rest harness path drops the caller `context` (see #<ctx-echo-issue>).
    # Position ordering grades BR-RULE-147 INV-3: no sort -> created_date descending.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/creative/index.yaml phase=list_and_filter step=list_all
    # @schema repo=adcp ref=v3.1.1 path=static/schemas/source/creative/list-creatives-response.json

    Examples: newest-first order, one row per synced format
      | sync_order | format_id       | position |
      | third      | audio_30s       | 1        |
      | second     | video_640x480   | 2        |
      | first      | display_300x250 | 3        |
```

Notes on the outline: the `Given` seeds display → video → audio in that order, so
`created_date desc` returns them audio → video → display. Each row therefore asserts a *different*
concrete pairing of (sync order, format, position) — the rows are not cosmetic copies. Verified from
the live dumps on all three transports (`creative_0002 audio / 0001 video / 0000 display`).

Replace `#<ctx-echo-issue>` with the issue number filed from §7, bullet 1.

---

## 6. Step inventory

**Reused unchanged** (already defined inline in `tests/bdd/test_uc018_list_creatives.py`; they must stay
in that module — pytest-bdd 8 resolves steps only from the scenario's own module/conftest/plugins, see the
module docstring):

| Step | Location |
|---|---|
| `Given the buyer recently synced three creatives in three different formats via sync_creatives` | `test_uc018_list_creatives.py:163` |
| `When the Buyer Agent sends list_creatives with no filters for the same account` | `test_uc018_list_creatives.py:181` |
| `Then the response should be schema-valid against {schema_file}` | `test_uc018_list_creatives.py:216` |
| `Then the creatives array should include each of the synced creatives` | `test_uc018_list_creatives.py:222` |

**Replaced** (old phrasing is used by this scenario only — `grep` over `tests/bdd/features/` returns
one hit, line 765 — so retiring it is safe):

- `each creative entry should expose creative_id, name, format_id, and status`
  → `each creative entry should expose creative_id, name, format_id, status, created_date and updated_date`.
  Rewrite the body to compare values, not presence: `set(entry) >= {six fields}`, `entry["format_id"].keys()`
  contains `agent_url` and `id`, `entry["status"] in CreativeStatus` (enum membership, a value comparison),
  and both dates parse as ISO-8601 (`datetime.fromisoformat`) — drop the `not in (None, "", {})` truthiness.

**New** (all four to be defined inline in the same module, all reading `_serialized_response(ctx)`):

| New step | Asserts |
|---|---|
| `the response envelope should carry status "{value}"` | `doc["status"] == value` — 3.1.1 `core/protocol-envelope.json` `required: [status]` |
| `the creative at position {position:d} should be the {sync_order} synced creative with format_id.id "{format_id}" and status "{status}"` | `doc["creatives"][position-1]["creative_id"] == ctx["synced_creative_ids"][idx]` (idx from `sync_order`), `…["format_id"]["id"] == format_id`, `…["status"] == status` |
| `the query_summary should report total_matching {total:d}, returned {returned:d} and filters_applied []` | exact equality on all three, incl. `== []` |
| `the query_summary should report sort_applied field "{field}" direction "{direction}"` | `doc["query_summary"]["sort_applied"] == {"field": field, "direction": direction}` |
| `the pagination should report has_more {has_more} and total_count {total:d} with no cursor` | `pagination["has_more"] is False`, `["total_count"] == total`, `"cursor" not in pagination` |

Do **not** try to import `tests/bdd/steps/domain/uc011_accounts.py:606,617` (`the response includes
pagination metadata with has_more …`) — importing does not register under pytest-bdd 8, and registering
those globally would alter the UC-011 suite. Same reason the module keeps its steps inline.

`_serialized_response` (`test_uc018_list_creatives.py:210`) is the right oracle to keep: it is the typed
payload through the production serializer, identical across transports, and it is what makes the e2e_rest
row work. Asserting `cursor` absence on the raw **wire** would be red on e2e_rest — see §7, bullet 2.

---

## 7. TICKET MATERIAL

1. **The rest harness path drops the caller-supplied `context`, so the storyboard's only distinctive
   grading cannot be asserted.**
   `tests/harness/creative_list.py:86–98` — `build_rest_body()` whitelists exactly
   `media_buy_id / media_buy_ids / status / format / filters` and silently discards every other kwarg,
   including `context`. Probed live: a2a and mcp echo `{"correlation_id": "creative_lifecycle--list_all"}`
   on both the typed response and the wire; rest returns `context: null` on both. Production is
   **not** at fault — `src/routes/api_v1.py:456` threads `context=to_context_object(body.context)` into
   `list_creatives_raw`, and `src/core/tools/creatives/listing.py:451` sets `context=req.context`.
   Mandated by `protocols/creative/index.yaml:237–243` (v3.1.1) — `field_present: context` and
   `field_value: context.correlation_id` — and by `core/protocol-envelope.json` (v3.1.1), whose `context`
   is "echoed unchanged in the response … MUST preserve byte-for-byte". Fix `build_rest_body` to forward
   `context` (and ideally stop whitelisting), then add the two echo assertions to this scenario.

2. **REST emits `pagination.cursor: null` on terminal pages; 3.1.1 forbids the key there.**
   `src/routes/api_v1.py:459` returns `response.model_dump(mode="json")` with no `exclude_none`, so every
   `None` optional serializes as an explicit `null` — including `pagination.cursor` on a page where
   `has_more` is false. `core/pagination-response.json` (v3.1.1) documents `cursor` as
   "Only present when has_more is true", and `universal/pagination-integrity.yaml` grades exactly this
   ("An agent that carries a stale cursor onto the terminal page fails the second-page assertion").
   Note `additionalProperties: false` on that schema makes the block strict. Same route file, same call:
   `format_summary`, `status_summary`, `sandbox`, `context`, `errors`, `ext` also go out as literal
   `null`s. Fix: `model_dump(mode="json", exclude_none=True)` on the REST route (audit sibling routes;
   `get_products` at `api_v1.py:237` and `list_creative_formats` at `:258` have the same shape).

3. **`list_creatives` never emits `pagination.cursor` at all, while `has_more` can be true.**
   `src/core/tools/creatives/listing.py:349` computes `has_more = (page * limit) < total_count` and
   `:443–446` builds `Pagination(has_more=…, total_count=…)` with no cursor — so a buyer told
   `has_more: true` has no way to fetch page 2 over a cursor. Violates the invariant graded by
   `universal/pagination-integrity.yaml` ("when `has_more` is true the `cursor` MUST be present").
   Already known per the shared brief — cited, not re-filed. (Gate caveat in §2/§8.)

4. **REST cannot express cursor pagination or sorting at all.**
   `ListCreativesBody` (`src/routes/api_v1.py:146–168`) has no `pagination` and no `sort` field — only
   the legacy `page`/`limit`/`sort_by`/`sort_order` scalars — and `list_creatives()` at `:438–458` never
   forwards a `PaginationRequest`, even though the tool signature accepts one
   (`src/core/tools/creatives/listing.py:454+`, `pagination: PaginationRequest | None`). The 3.1.1
   request schema `creative/list-creatives-request.json` carries structured `pagination`/`sort`; a REST
   buyer sending them gets them dropped (or 422'd under `extra="forbid"` in CI). Ties into #3 — without
   this, the pagination-integrity storyboard cannot be walked over REST regardless of the cursor fix.

5. **`ListCreativesBody` has no `account` field, so the storyboard's own `sample_request` is unsendable
   over REST.** `protocols/creative/index.yaml:221–229` (v3.1.1) posts
   `account: {brand: {domain}, operator, sandbox: true}` on `list_all`. Our REST body
   (`src/routes/api_v1.py:146–168`) has no `account`; under the dev/CI `extra="forbid"` mode
   (CLAUDE.md pattern #7) that request is a 422. The BDD scenario's phrase "for the same account" is
   therefore aspirational — it is principal-scoped, not account-scoped. Relevant to the
   account-management work already in flight.

6. **The pinned schema fixture tree is stale (04f59d2d5, not 3.1.1) — and refreshing it is green here.**
   `tests/fixtures/adcp_schemas_pinned/` + `tests/helpers/pinned_schema.py:6` pin
   `v3.1-04f59d2d5`, an ancestor of beta.3, i.e. *older* than the repo's own 3.1.1 pin, so
   "schema-valid against list-creatives-response.json" currently grades against a superseded contract
   (notably missing the `core/protocol-envelope.json` ref → `status` unenforced). I validated the live
   a2a/mcp/rest responses against the true v3.1.1 closure: **0 errors on all three.** For `list_creatives`
   the refresh is a no-op risk-wise and a real strengthening — do it, then re-run the whole BDD suite to
   find the tools where it is *not* free.

7. **`then_response_schema_valid` is duplicated per-module with divergent strength.**
   The UC-018 copy (`tests/bdd/test_uc018_list_creatives.py:216`) really does call
   `validate_against_pinned_schema`; the brief reports a same-named step elsewhere that validates nothing.
   Two steps with one phrasing and different rigour is the DRY defect CLAUDE.md treats as a correctness
   bug. Consolidate into one registered implementation (a shared plugin module, given the pytest-bdd 8
   resolution constraint) so no feature file can silently bind the weak one.

---

## 8. Risks

- **`has_creative_library` gating.** I could not settle whether `universal/pagination-integrity.yaml`
  applies to us. It is `track: core`, but declares `agent.capabilities: [has_creative_library]` and
  `requires: [controller]`, and `has_creative_library` is defined only inside the capabilities response's
  `creative` block, which the 3.1.1 schema says is *"Only present if creative is in supported_protocols."*
  By the same rule that de-grades `list_all`, the pagination universal may be gated off too. This changes
  the *severity* of tickets #3/#4, not their correctness.
- **The `creative` protocol is a policy decision, not a test decision.** We implement `list_creatives`,
  `sync_creatives`, `list_creative_formats` and `preview_creative`, and the response passes the 3.1.1
  schema — declaring `supported_protocols=[media_buy, creative]` would put this storyboard *back* on our
  path and flip the tag to `@storyboard-v3.1`. That is an owner call. I have proposed `@schema-v3.1`
  strictly because it matches what `capabilities.py:271` declares **today**.
- **Ordering tie-break.** The `position` column relies on `created_date desc` over three factory inserts
  ~4 ms apart (verified: distinct microsecond timestamps on all three transports). Identical timestamps
  would make row order DB-dependent. Low risk, non-zero.
- **e2e_rest not executed.** `BDD_E2E_ENABLED` was off, so I verified a2a/mcp/rest only. This scenario is
  *not* in `tests/bdd/e2e_rest_known_failures.txt`, so it must stay green in the "BDD In-Network" CI job.
  My assertions read `_serialized_response` (typed, `exclude_none`), the same oracle the existing green
  steps use, which is why I did *not* move them to the raw wire — the REST `cursor: null` of ticket #2
  would make a wire-level "no cursor" assertion red in-network. Someone should run the in-network job
  before merge.
- **Node-id churn.** Converting to a `Scenario Outline` re-parametrizes the pytest node ids. The
  scenario is absent from the e2e_rest ledger, and `docs/test-obligations/bdd-traceability.yaml:10549`
  keys off the tag (unchanged), so I expect no fallout — but `tests/unit/test_e2e_rest_ledger_state.py`
  and `scripts/ci/shard_split.py` are worth a glance after the edit.
- **Not verified by execution:** the rewritten Gherkin itself. I was scoped to propose only and made no
  edit under `salesagent-sbsweep`; the four new Then steps do not exist yet. Every *value* they assert
  came from a live dump, but the step wiring is unexercised.
- **3.1.8 / HEAD drift** was not consulted beyond confirming 3.1.1 is the authority. Noted, nothing more.

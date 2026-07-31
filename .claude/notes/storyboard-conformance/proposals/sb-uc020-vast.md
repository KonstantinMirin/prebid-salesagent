# Re-pin: `@T-UC-020-storyboard-build-vast-tag-from-synced-creative`

Scenario: `tests/bdd/features/BR-UC-020-build-creative.feature:1015-1028`
Title: "Build a VAST-compatible serving tag from a synced video creative referenced by creative_id"
Cited `@source`: **none** — no footer exists.

---

## 1. VERDICT

**NOT GRADED — undeclared gate.**

The behaviour *is* graded at 3.1.1 — but only inside the **`creative-ad-server` specialism**
(`specialisms/creative-ad-server/index.yaml`), which we do not declare, on the **`creative`
protocol**, which we also do not declare. Three independent gates all fail:

| Gate | 3.1.1 requirement | What we declare | Result |
|---|---|---|---|
| Specialism | `creative-ad-server` | `sales-non-guaranteed` only (`src/core/tools/capabilities.py:100,272`) | not on path |
| Protocol | `protocol: creative` (`specialisms/creative-ad-server/index.yaml:4`) | `media_buy` only (`capabilities.py:99,271`) | not on path |
| Required tool | `required_tools: [build_creative]` (`.../creative-ad-server/index.yaml:6-7`) | `build_creative` is **not registered** — `src/core/main.py:351-366` registers 16 tools, none of them `build_creative` | cannot execute |

And the 3.1.1 generic creative baseline says so in prose, twice, explicitly:

`dist/compliance/3.1.1/domains/creative/index.yaml:17-20` (verbatim):
```
  The individual creative storyboards (template, ad server, native, sales agent) cover
  specific interaction models and sub-modalities. This storyboard keeps the generic
  creative baseline display-safe; video tag generation is covered by the
  creative-ad-server specialism.
```
and again at `domains/creative/index.yaml:295-298` on the `build_and_preview` phase:
```
  - id: build_and_preview
    title: "Preview display creative"
    narrative: |
      The buyer previews renderings for the synced display creative. Video/VAST tag
      generation is covered by the creative-ad-server specialism, where the agent has
      explicitly claimed that sub-modality.
```
(`protocols/creative/index.yaml` is a byte-identical mirror — same lines 20 and 298.)

Cross-check that closes it: `specialisms/sales-non-guaranteed/index.yaml:12-27` enumerates
`requires_scenarios` — 15 entries, all `media_buy_seller/*` plus one
`governance_aware_seller/*`. **No `creative_ad_server/*` scenario appears.** Declaring
`sales-non-guaranteed` pulls in nothing from the creative track.

The only thing this repo does with the name `build_creative` is call it **outbound** as a
client of a third-party creative agent — `src/core/creative_agent_registry.py:950-996`,
`client.call_tool("build_creative", params)`, reached only from `sync_creatives` refinement
(`src/core/tools/creatives/_processing.py:253,565`). We are the *caller*, never the *agent
under test*. The storyboard grades the agent under test.

**Action:** `@storyboard-v3.1` → `@schema-v3.1`. Keep `@T-UC-020-storyboard-build-vast-tag-from-synced-creative`
unchanged (referenced at `docs/test-obligations/bdd-traceability.yaml:11649-11654`).

### Compounding finding — the whole feature file is dormant

`BR-UC-020-build-creative.feature` (1028 lines, ~60 scenarios) has **no `scenarios()`
binding**. There is no `tests/bdd/test_uc020*.py`; the file does not appear in any
`scenarios("features/...")` call across `tests/bdd/*.py`. It is never collected by pytest.
There are also zero step definitions for it — `tests/bdd/conftest.py:49-72` registers 22
step plugins, none for UC-020, and the Background's second step
(`And at least one creative agent is registered and reachable`) has no definition either
(only `"at least one creative agent is registered with format definitions"` exists, in
`tests/bdd/steps/generic/given_entities.py`). So *this scenario has never run, in any
transport, and neither has anything else in the file.* Its "green" status is vacuous.

---

## 2. Real binding at 3.1.1

**File:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/specialisms/creative-ad-server/index.yaml`
**Phase:** `generate_tags` — line **212**
**Step:** `build_tag` — line **226**
**Graded block:** lines **266-292**

Verbatim (`validations:` at line 266):
```yaml
        validations:
          - check: response_schema
            description: "Response matches build-creative-response.json schema"
          - check: field_present
            path: "creative_manifest.assets"
            description: "Output includes a serving tag asset"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "creative_ad_server--build_tag"
            description: "Context correlation_id returned unchanged"
          # Anti-façade: a real ad-server adapter calls its upstream tag-build /
          # creative-trafficking API. An adapter that fabricates a serving tag
          # locally without touching the ad server fails this check. Permissive
          # endpoint pattern because ad-server vendors differ widely (Google
          # Ad Manager, Kevel, Equativ, FreeWheel) — the storyboard asserts
          # "an upstream call happened" rather than naming a platform.
          - check: upstream_traffic
            description: "build_creative caused upstream traffic to the ad server carrying the creative_id"
            min_count: 1
            endpoint_pattern: "POST *"
            identifier_paths:
              - "creative_id"
```

The step's own metadata (lines 239-244):
```yaml
        task: build_creative
        schema_ref: "media-buy/build-creative-request.json"
        response_schema_ref: "media-buy/build-creative-response.json"
        doc_ref: "/creative/task-reference/build_creative"
        comply_scenario: creative_flow
        stateful: true
```

The scenario's `vast_30s` string is not incidental — it is lifted from this specialism's
fixture block, `specialisms/creative-ad-server/index.yaml:78-87`:
```yaml
fixtures:
  creatives:
    - creative_id: "campaign_hero_video"
      status: "approved"
      format_id:
        id: "vast_30s"
```
and its `sample_request` at lines 254-262. So the scenario was authored *from this
specialism* — the author just never recorded which tier it came from.

**Tier:** `specialisms/` — capability-gated. Not `universal/`, not `protocols/`, not `domains/`.

**What the missing footer would have wrongly pointed at, had it followed the pack's
off-by-one pattern:** nothing to correct here — the footer is simply absent. The scenario's
own trailing comments name `creative_lifecycle` and `build_video_tag`. Both are wrong as
bindings:
- `creative_lifecycle` is the **id of `domains/creative/index.yaml`** (line 1: `id: creative_lifecycle`)
  — the *display-safe baseline that explicitly disclaims this behaviour* (quoted above).
- `build_video_tag` **does not exist anywhere** in `dist/compliance/3.1.1/` (`grep -rn
  "build_video_tag"` → zero hits). It is an invented step id.

So the scenario's self-documentation points at the one storyboard that says "not here."

**Prose-vs-graded split for the three current Thens:**

| Current Then | Graded at 3.1.1? |
|---|---|
| "response should be schema-valid against build-creative-response.json" | **Graded** — `check: response_schema` (line 267). But under the undeclared specialism. |
| "response should carry a serving tag compatible with the VAST target_format_id" | **Prose only.** The graded check is `field_present: creative_manifest.assets` — asset *presence*, no VAST-ness, no format match. "The format_id matching the target format" appears only under `expected:` (line 248), which is narrative. |
| "response should reference the originating creative_id" | **Not graded, and unschema-able.** See §3. |

---

## 3. Schema constraints at 3.1.1

All quotes from `git show v3.1.1:static/schemas/source/<path>` in `/Users/konst/projects/adcp`.

### `media-buy/build-creative-response.json`

Six mutually exclusive branches. Discriminator = which key is present:

| # | Branch | `required` | Selected when |
|---|---|---|---|
| 0 | `BuildCreativeSuccess` | `["creative_manifest"]` | request used `target_format_id` |
| 1 | `BuildCreativeMultiSuccess` | `["creative_manifests"]` | request used `target_format_ids` |
| 2 | `BuildCreativeVariantSuccess` | `["creatives"]` | `max_creatives` / `max_variants` fan-out |
| 3 | `BuildCreativeEstimate` | `["mode","estimate"]` | `mode: "estimate"` |
| 4 | `BuildCreativeError` | `["errors"]` | terminal failure |
| 5 | `BuildCreativeSubmitted` | `["status","task_id"]` | queued build |

Schema `description`, verbatim:
> "Response payload for build_creative. Exactly one of six shapes: (1) synchronous
> single-format success — creative_manifest issued in-line (target_format_id request); …
> These six shapes are mutually exclusive — a response has exactly one."

Envelope, verbatim from the same file:
```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
```

`BuildCreativeSuccess.properties` = `creative_manifest, build_variant_id, recipe_hash,
sandbox, expires_at, preview, preview_error, pricing_option_id, vendor_cost, currency,
consumption, context, ext`. **There is no `creative_id` property.**

### `core/protocol-envelope.json` — `required: ["status"]`

```json
  "required": [ "status" ],
```
description, verbatim:
> "The `status` field is REQUIRED on every task response envelope, including synchronous
> metadata responses (e.g., `get_adcp_capabilities`) where the value is `completed`. Agents
> shipping responses without a top-level `status` are non-conformant regardless of whether
> the task body schema would otherwise validate."

Plus the negative constraint:
```json
  "not": { "anyOf": [ { "required": ["task_status"] }, { "required": ["response_status"] } ] }
```

### `core/creative-manifest.json`

```
required: ['assets']
properties: format_id, format_kind, format_option_ref, assets, brand, rights,
            industry_identifiers, provenance, ext
additionalProperties: true
```
**No `creative_id` property.** `format_id` and `format_kind` are mutually exclusive
(`oneOf` at the schema root), and `format_id` is
> "Always a structured object {agent_url, id} — never a plain string."

### `media-buy/build-creative-request.json`

`required: ["idempotency_key"]` — and *only* that. `creative_id` is optional:
> "Reference to a creative in the agent's library. The creative agent resolves this to a
> manifest from its library. Use this instead of creative_manifest when retrieving an
> existing creative for tag generation or format adaptation."

Mutual exclusion, verbatim:
```json
    {
      "$comment": "target_format_id and target_format_ids are mutually exclusive (single vs multi).",
      "not": { "required": ["target_format_id", "target_format_ids"] }
    },
```
`idempotency_key`: `minLength: 16`, `maxLength: 255`, `pattern: "^[A-Za-z0-9_.:-]{16,255}$"`.

### `enums/specialism.json`

```json
  "enum": [ …, "creative-ad-server", …, "sales-non-guaranteed", … ],
  "enumDescriptions": {
    "creative-ad-server": "Creative ad server with tag-based delivery",
    "sales-non-guaranteed": "Non-guaranteed auction-based media buys",
```
Schema `description`, verbatim — this is the normative statement that makes the gate
question decidable:
> "Specialized capability claims an agent can make. Each specialism maps to a compliance
> storyboard bundle published at /compliance/{version}/specialisms/{id}/. An agent asserts
> specialisms it supports in get_adcp_capabilities; the AAO compliance runner executes the
> matching storyboards to verify the claim."

We assert `sales-non-guaranteed`. The runner therefore executes
`specialisms/sales-non-guaranteed/` — not `specialisms/creative-ad-server/`.

---

## 4. Conflicts

**Schema overrides storyboard — one place, and it kills a Then.**

"The response should reference the originating creative_id" has **no schema anchor**.
`BuildCreativeSuccess` has no `creative_id`; `creative-manifest.json` has no `creative_id`.
The storyboard's `upstream_traffic` check (line 286-292) asserts the creative_id appears in
**outbound traffic to the ad server**, `identifier_paths: ["creative_id"]` — a network-trace
assertion, explicitly *not* a response-body assertion. The scenario read a wire-trace check
as a payload check.

`creative-manifest.json` is `additionalProperties: true`, so an agent *may* echo `creative_id`
inside the manifest without failing validation (and `domains/creative/index.yaml:324`'s
`preview_creative` sample_request does exactly that). But "MAY ride along" is not "MUST be
present," and no `validations:` entry anywhere grades it. The 3.1.1 schema wins: **drop the
assertion**.

**What else the scenario gets wrong:**

1. **Tier misattribution** (the headline). `@storyboard-v3.1` claims conformance grading we
   are not on the hook for and cannot execute.
2. **Invented step id.** `build_video_tag` does not exist in 3.1.1. Real id is `build_tag`.
3. **Wrong storyboard named.** `creative_lifecycle` is the display-safe baseline that
   disclaims video tag generation in its own narrative.
4. **Vacuous Then #2.** "should carry a serving tag compatible with the VAST
   target_format_id" — "compatible with" is unfalsifiable prose. The graded check is
   `field_present: creative_manifest.assets`. `test_architecture_bdd_no_trivial_assertions.py`
   would reject any honest implementation of this phrasing, because the only implementable
   reading is an existence check.
5. **No envelope assertion.** 3.1.1 added `core/protocol-envelope.json` with
   `required: ["status"]` to this response. The scenario never mentions `status`.
6. **No branch discriminator.** The response schema's entire contract is "exactly one of
   six shapes." A scenario that says "schema-valid" without naming the branch asserts
   almost nothing — `oneOf` is satisfied by any of the six.
7. **Missing `@source` footer.** Every other scenario in the pack has one.
8. **Never executed.** No `scenarios()` binding, no step definitions, unbound Background.

---

## 5. Proposed Gherkin

**Recommendation, stated plainly first:** this scenario grades a capability we do not claim,
on a protocol we do not declare, through a tool we do not register. My primary
recommendation is the rewrite below — retag to `@schema-v3.1`, correct the binding, and
reduce the assertions to pure 3.1.1 response-schema shape facts that carry no conformance
claim. My secondary recommendation, which I think is defensible and cleaner, is to **delete
the scenario and its `bdd-traceability.yaml` row** (see TICKET MATERIAL); I did not propose
deletion as primary only because the brief instructs that the `@T-UC-…` tag be preserved.

**Honesty note on GREEN:** these Thens have no step definitions and the feature file has no
`scenarios()` binding, so this scenario does not execute today and my proposal does not make
it execute. It is green in the CI sense (never collected) and would be `xfail` if bound
(`tests/bdd/conftest.py` auto-xfails on missing step definitions). I have deliberately not
invented steps that would call a `build_creative` tool that does not exist — that would be
the dormant-scenario anti-pattern with extra steps. Everything needed to make it real is in
TICKET MATERIAL.

```gherkin
  # Retagged @storyboard-v3.1 -> @schema-v3.1: at 3.1.1 video/VAST tag generation is
  # graded ONLY under the creative-ad-server specialism, which this agent does not
  # declare. src/core/tools/capabilities.py:271-272 declares
  # supported_protocols=[media_buy], specialisms=[sales_non_guaranteed]; the
  # creative-ad-server bundle requires protocol `creative` and required_tools
  # [build_creative], and specialisms/sales-non-guaranteed/index.yaml:12-27 lists no
  # creative_ad_server scenario. The generic creative baseline disclaims this behaviour
  # in its own narrative (domains/creative/index.yaml:17-20). What remains below is the
  # 3.1.1 build-creative-response.json SHAPE contract, which is version-pinned fact
  # independent of whether we are graded on it. See #TBD-uc020-binding.
  @T-UC-020-storyboard-build-vast-tag-from-synced-creative @schema-v3.1 @v3-1 @build-from-library @vast
  Scenario Outline: build_creative response selects exactly one of the six 3.1.1 branches
    Given a video creative has been synced to the library with creative_id "video_30s_trail_pro"
    And the request carries <request_shape>
    When the Buyer Agent sends a build_creative request
    Then the response envelope field "status" should be present
    And the response should match exactly 1 branch of build-creative-response.json
    And the selected branch should be "<branch>"
    And the branch required keys should be "<required_keys>"
    And the response should not contain the field "task_status"
    And the response should not contain the field "response_status"

    Examples: six mutually exclusive response shapes
      | request_shape                              | branch                       | required_keys        |
      | a single target_format_id with id "vast_30s" | BuildCreativeSuccess       | creative_manifest    |
      | two target_format_ids                      | BuildCreativeMultiSuccess    | creative_manifests   |
      | max_variants of 3                          | BuildCreativeVariantSuccess  | creatives            |
      | mode "estimate"                            | BuildCreativeEstimate        | mode,estimate        |
      | a build that the agent queues              | BuildCreativeSubmitted       | status,task_id       |
      | inputs the agent terminally rejects        | BuildCreativeError           | errors               |

  # @source ref=v3.1.1 commit=467fd93d7
  #   file=dist/compliance/3.1.1/specialisms/creative-ad-server/index.yaml
  #   phase=generate_tags (line 212) step=build_tag (line 226) validations=lines 266-292
  #   tier=specialisms  gate=specialism:creative-ad-server + protocol:creative
  #   status=NOT ON OUR CONFORMANCE PATH — we declare specialisms=[sales-non-guaranteed],
  #          supported_protocols=[media_buy] and register no build_creative tool.
  #   schema=static/schemas/source/media-buy/build-creative-response.json (six-branch oneOf)
  #        + static/schemas/source/core/protocol-envelope.json (required: ["status"])
  # Superseded self-documentation removed: the prior comments named storyboard
  # `creative_lifecycle` (= domains/creative/index.yaml, the display-safe baseline that
  # explicitly excludes video tag generation) and step `build_video_tag` (no such id
  # exists anywhere in dist/compliance/3.1.1/).
```

Notes on the rewrite:
- Every Then compares a concrete value (`"status"`, a branch name, an exact required-key
  set, two forbidden field names) — no truthiness, no bare existence of an unnamed thing.
- Zero transport branching. Identical across MCP / A2A / REST / e2e_rest.
- The `Examples:` table *is* the specificity: it encodes the schema's six-way `oneOf` as six
  rows, which is the actual 3.1.1 contract for this response.
- Dropped: "should reference the originating creative_id" (§4, no schema anchor) and
  "carry a serving tag compatible with the VAST target_format_id" (prose, unfalsifiable).
  `vast_30s` survives as an Examples value so the VAST framing and the specialism fixture
  origin are not lost.

---

## 6. Step inventory

**Existing steps reused: 1 of 10.**

| Step | Status | Where |
|---|---|---|
| `Given a Seller Agent is operational and accepting requests` (Background) | **exists** | `tests/bdd/steps/generic/given_entities.py` |
| `Given at least one creative agent is registered and reachable` (Background) | **MISSING** | nearest is `"at least one creative agent is registered with format definitions"` (`given_entities.py`) — different phrasing, not a match |
| `Given a video creative has been synced to the library with creative_id "…"` | **MISSING** (unchanged from current text) | — |
| `Given the request carries <request_shape>` | **new** | — |
| `When the Buyer Agent sends a build_creative request` | **MISSING** (unchanged from current text) | — |
| `Then the response envelope field "status" should be present` | **new** | closest precedent `then_media_buy.py::the response should include a "{field}"` |
| `Then the response should match exactly 1 branch of build-creative-response.json` | **new** | closest precedent `uc005_format_id_roundtrip.py:101` `@then("the response should be schema-valid against list-creative-formats-response.json")` — the only schema-valid step in the repo |
| `Then the selected branch should be "<branch>"` | **new** | — |
| `Then the branch required keys should be "<required_keys>"` | **new** | — |
| `Then the response should not contain the field "…"` | **new** | — |

Verified by `grep -rn "^@then\|^@when\|^@given" tests/bdd/steps/` — **none of the three
current Thens has a definition**, and the string `serving tag` / `VAST` / `vast_30s` /
`originating creative_id` / `build-creative-response` appears nowhere in
`tests/bdd/steps/`. This scenario has never had an implementation.

Note: `tests/harness/` has no `build_creative` environment (`ls tests/harness/` — 30 modules,
none for build/creative-build), and `grep -rn "build_creative" tests/` returns zero hits.
So there is no dispatch target for the When step either.

---

## 7. TICKET MATERIAL

- **`BR-UC-020-build-creative.feature` is never collected — ~60 scenarios, 1028 lines, zero
  executions.** No `scenarios("features/BR-UC-020-build-creative.feature")` exists in any
  `tests/bdd/test_*.py` (verified across all 24 binding modules), and `tests/bdd/conftest.py:49-72`
  registers no UC-020 step plugin. Every scenario in the file, including the four
  `@storyboard-*`/`@error-details` ones immediately above ours, is dormant. Decide per
  scenario: bind or delete. Anything kept unbound must be marked so nobody reads its
  presence as coverage. Mandated by nothing in the spec — this is the repo's own
  dormant-scenario anti-pattern (cf. #1260, #1544).

- **Retag `@storyboard-v3.1` → `@schema-v3.1` on `@T-UC-020-storyboard-build-vast-tag-from-synced-creative`.**
  `enums/specialism.json` (v3.1.1) description: "An agent asserts specialisms it supports in
  get_adcp_capabilities; the AAO compliance runner executes the matching storyboards."
  `src/core/tools/capabilities.py:271-272` asserts `sales-non-guaranteed` + `media_buy`.
  The graded step lives at `specialisms/creative-ad-server/index.yaml:226` under
  `protocol: creative` + `required_tools: [build_creative]`.
  `specialisms/sales-non-guaranteed/index.yaml:12-27` lists no creative_ad_server scenario.

- **Delete the assertion "the response should reference the originating creative_id"
  (`BR-UC-020-build-creative.feature:1021`) — it asserts something 3.1.1 does not define.**
  `media-buy/build-creative-response.json` `BuildCreativeSuccess.required == ["creative_manifest"]`
  and its property set contains no `creative_id`; `core/creative-manifest.json`
  `required == ["assets"]` and has no `creative_id` property. The storyboard's only
  creative_id check is `check: upstream_traffic … identifier_paths: ["creative_id"]`
  (`specialisms/creative-ad-server/index.yaml:286-292`) — an outbound network-trace
  assertion, not a response-payload one.

- **`build_creative` is not implemented as a server-side AdCP tool.** `src/core/main.py:351-366`
  registers 16 tools; `build_creative` is not among them. The only occurrence is the
  outbound client call at `src/core/creative_agent_registry.py:996`
  (`client.call_tool("build_creative", params)`), reached from `sync_creatives` refinement
  (`src/core/tools/creatives/_processing.py:253,565`). If the intent is to claim
  `creative-ad-server`, the tool, a `_impl`, MCP/A2A/REST wrappers, and a harness env are
  all missing. If the intent is *not* to claim it, UC-020 should say so once, at the top of
  the feature file, instead of 60 scenarios implying otherwise.

- **Stale comment: `src/core/creative_agent_registry.py:981` says "build_creative not in
  AdCP spec".** False at 3.1.1 — `static/schemas/source/media-buy/build-creative-request.json`
  and `build-creative-response.json` both exist, and `/creative/task-reference/build_creative`
  is the storyboard's `doc_ref`. The comment predates 3.1 and misleads anyone deciding
  whether to implement the tool.

- **No BDD/harness coverage for `get_adcp_capabilities`, which is the gate for every
  specialism question.** `grep -rn "get_adcp_capabilities" tests/harness/ tests/bdd/steps/`
  → only `tests/harness/test_mcp_client_dispatch.py` (a middleware smoke test). Our
  specialism/protocol declaration — the thing that decides which storyboards grade us — is
  asserted nowhere behaviourally. `protocol-envelope.json` also requires `status` on the
  capabilities response specifically ("including synchronous metadata responses (e.g.,
  `get_adcp_capabilities`) where the value is `completed`").

- **Background step `And at least one creative agent is registered and reachable`
  (`BR-UC-020-build-creative.feature:21`) has no definition.** Nearest existing phrasing is
  `at least one creative agent is registered with format definitions`
  (`tests/bdd/steps/generic/given_entities.py`). Every UC-020 scenario would xfail on the
  Background alone if the file were bound. Same defect likely in
  `BR-UC-021-preview-creative.feature` (also carries one `@storyboard-v3.1` tag, also
  unbound).

- **Known gaps this scenario would hit if implemented (already filed per brief — cited, not
  re-filed):** no top-level `status` on responses vs `core/protocol-envelope.json`
  `required: ["status"]`; `then_response_schema_valid` runs no validator despite
  `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing;
  `tests/fixtures/adcp_schemas_pinned/` vendored at `04f59d2d5` rather than 3.1.1 — which
  means the proposed "match exactly 1 branch of build-creative-response.json" step cannot be
  implemented against the pinned fixtures until they are re-vendored.

---

## 8. Risks

- **Not verified by execution.** Nothing here was run — the scenario is uncollectable
  (no `scenarios()` binding), so there was no test to execute. Every claim is from reading
  `dist/compliance/3.1.1/`, `git show v3.1.1:static/schemas/source/…`, and `src/`.
- **Schema/storyboard conflict resolution.** I resolved one in favour of the schema: the
  `creative_id`-in-response Then. The storyboard never asserts it in a response either, so
  this is a weak conflict — mostly the scenario misreading `upstream_traffic` as a payload
  check. I am confident in the outcome, less so that "conflict" is the right word for it.
- **The `@schema-v3.1` retag assumes the tag means "schema-grounded, not conformance-graded."**
  I inferred that from usage (`BR-UC-001` main/alt scenarios, `BR-UC-002-account-access.feature:12`)
  and from the brief. I found no written definition of the tag vocabulary anywhere in the
  repo — no guard, no doc, no conftest marker registration consumes either tag
  (`grep` over `.py`/`.yaml`/`.md`/`.ini`/`.toml` outside `.feature` files: zero hits). If
  the tags carry meaning somewhere I did not find, re-check.
- **Six-branch outline is untestable today** against the pinned fixtures (vendored at
  `04f59d2d5`, pre-3.1.1). If those fixtures do not carry the six-branch `oneOf`, the
  proposed Then would need the live 3.1.1 schema instead. I did not open
  `tests/fixtures/adcp_schemas_pinned/` to check which build-creative schema version it holds.
- **`BuildCreativeSubmitted` row.** Its `required` is `["status","task_id"]`, so `status`
  is both an envelope field and a branch-required field there. My outline asserts `status`
  present on every row plus `status,task_id` as that row's required keys — correct but
  slightly redundant. Left as-is because the branch's own `required` array is the fact
  being pinned.
- **Line numbers are from `dist/compliance/3.1.1/` as checked out on disk**, which I took as
  matching the published 3.1.1 bundle. I did not verify that working tree against
  `git show v3.1.1:dist/compliance/3.1.1/…`. Schema quotes *are* from `git show v3.1.1:`
  and are safe.
- **3.1.8 / HEAD drift not examined** beyond noting the version list. Per brief, out of scope.

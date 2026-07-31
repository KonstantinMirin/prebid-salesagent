# Re-pin: `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope` → AdCP 3.1.1

Target scenario: `tests/bdd/features/BR-UC-005-discover-creative-formats.feature:1078`
Current pin: `ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/creative/index.yaml`
Proposed pin: **3.1.1**, `protocols/media-buy/index.yaml` (see §1.4).

Authority used, in order: (1) AdCP 3.1.1 JSON schemas via `git show v3.1.1:static/schemas/source/...`
in `/Users/konst/projects/adcp`; (2) 3.1.1 storyboard on disk at
`/Users/konst/projects/adcp/dist/compliance/3.1.1/`. Production code and the `adcp` SDK are
cited only as cross-checks.

---

## 1. Storyboard checks at 3.1.1 — verbatim + file:line

### 1.1 The `list_formats_integrity` step — and what it actually grades

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/index.yaml:352-378`
(phase `product_discovery`):

```yaml
352:      - id: list_formats_integrity
353:        title: "Verify format_ids on products resolve to real formats"
354:        narrative: |
355:          The buyer asks the sales agent to filter `list_creative_formats` by
356:          `products[0].format_ids[0]`. The sales agent MUST return the format
357:          it advertised on its own product — whether it hosts that format
358:          directly or proxies to the creative agent named in
359:          `format_ids[0].agent_url`. An empty `formats[]` means the sales
360:          agent's product catalog references a format that does not resolve —
361:          a stale or typo'd entry that would have failed silently at
362:          `sync_creatives` after the media buy was already committed.
363:        task: list_creative_formats
364:        schema_ref: "creative/list-creative-formats-request.json"
365:        response_schema_ref: "creative/list-creative-formats-response.json"
```

Its graded validations (`:399-415`):

```yaml
399:        validations:
400:          - check: response_schema
401:            description: "Response matches list-creative-formats-response.json schema"
402:          - check: field_present
403:            path: "formats[0]"
404:            description: "Sales agent resolves the format_id — products[0].format_ids[0] exists in the catalog"
405:          - check: field_value
406:            path: "formats[0].format_id"
407:            value: "$context.product_format_id"
408:            description: "Returned format_id round-trips verbatim — the agent cannot substitute a different format in response to the filter"
409:          - check: field_present
410:            path: "context"
411:            description: "Response echoes back the context object"
412:          - check: field_value
413:            path: "context.correlation_id"
414:            value: "media_buy_seller--list_formats_integrity"
415:            description: "Context correlation_id returned unchanged"
```

**`list_formats_integrity` at 3.1.1 contains no `scope:`, no `on_out_of_scope:`, and no
`refs_resolve` check.** Every one of its five validations is unconditional. The line the
current scenario leans on — the out-of-scope/warn exemption — is not in this step.

Note `:408` verbatim: *"the agent cannot substitute a different format in response to the
filter."* That is the gradeable seller obligation this scenario is really about.

### 1.2 Where `scope.equals=$agent_url` / `on_out_of_scope: warn` actually lives at 3.1.1

A **different phase** (`creative_sync`, `:587`) and a **different step** (`list_formats`, `:604`):

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/index.yaml:650-669`:

```yaml
650:          - check: refs_resolve
651:            description: |
652:              The captured format_id returned on the first product resolves to a
653:              format in this agent's list_creative_formats. Broken references here surface as a
654:              grading failure instead of a silent mismatch that only breaks at
655:              sync_creatives time, after the buy is committed. Third-party
656:              format_ids (agent_url pointing at a different creative agent)
657:              can't be verified without calling that agent and are reported as
658:              observations rather than failures.
659:            source:
660:              from: context
661:              path: "product_format_id"
662:            target:
663:              from: current_step
664:              path: "formats[*].format_id"
665:            match_keys: [agent_url, id]
666:            scope:
667:              key: agent_url
668:              equals: $agent_url
669:            on_out_of_scope: warn
```

### 1.3 What `on_out_of_scope: warn` means — the runner, not the seller

`/Users/konst/projects/adcp/dist/compliance/3.1.1/universal/storyboard-schema.yaml:1373-1394`:

```yaml
1373: #     match_keys: [<key>, ...]      # keys compared on each ref — e.g. [agent_url, id].
1374: #                                   # A ref missing any declared key is NEVER a match
1375: #                                   # (agents that drop a key don't fuzzy-match others
1376: #                                   # that also dropped it).
1377: #     scope:                        # optional — restrict integrity to in-scope refs.
1378: #       key: <string>               # e.g. `agent_url`.
1379: #       equals: <string>            # literal value, or `$agent_url` for the
1380: #                                   # runner target URL. Keys ending in `url`
1381: #                                   # get trailing-slash / case normalization
1382: #                                   # on both sides before compare. ...
1389: #     on_out_of_scope: warn | ignore | fail
1390: #                                   # how refs outside `scope` are graded.
1391: #                                   # default `warn`: pass the check, attach
1392: #                                   # observations naming the skipped refs.
1393: #                                   # `ignore`: silent. `fail`: promote to
1394: #                                   # missing so reports name them.
```

Read `:1390` literally: *"how refs outside `scope` are **graded**."* `warn` / `ignore` / `fail`
are three settings of the **compliance runner's report generator**. The seller emits byte-identical
responses under all three. This is the crux of §3.2.

Also load-bearing for the rewrite, `:1380-1382`: scope keys ending in `url` *"get trailing-slash /
case normalization on both sides before compare."* Reference comparison is canonicalized, not literal.

### 1.4 Correct `path=` for the footer

The current footer cites `static/compliance/source/protocols/creative/index.yaml`. At 3.1.1 that
file's only `list_creative_formats` steps are `discover_formats/list_formats` (`:86`),
`list_and_filter/list_all` (`:203`) and `list_and_filter/list_filtered` (`:248`). It contains **no**
`list_formats_integrity` step, **no** `refs_resolve` check and **no** `on_out_of_scope` key. Both
mechanisms this scenario cites live only in `protocols/media-buy/index.yaml`. The current path is
wrong at 3.1.1 and was wrong at 04f59d2d5 for the same reason.

---

## 2. Schema constraints at 3.1.1 — verbatim

### 2.1 `core/format-id.json` (`git show v3.1.1:static/schemas/source/core/format-id.json`)

```json
"title": "Format Reference (Structured Object)",
"description": "A JSON object — never a plain string — that identifies a creative format by its
 declaring agent and local slug. Required properties: agent_url (URI of the agent that owns the
 format) and id (slug matching [a-zA-Z0-9_-]+). ... Using a plain string here is a schema violation."
```

```json
"agent_url": {
  "type": "string", "format": "uri",
  "description": "URL of the agent that defines this format ... Callers comparing two `format-id`
   values MUST canonicalize `agent_url` per the AdCP URL canonicalization rules before treating two
   formats as the same. See docs/reference/url-canonicalization."
},
"id": { "type": "string", "pattern": "^[a-zA-Z0-9_-]+$", ... },
"required": ["agent_url", "id"]
```

Three binding constraints:
1. `agent_url` is **part of the identity**, not decoration — a format reference is the *pair*.
2. `agent_url` is *"URL of the agent that **defines** this format"* — so the `agent_url` on a
   returned format asserts authorship. Rewriting it is a misattribution, not a formatting choice.
3. Comparison is a **MUST-canonicalize** operation. Literal string equality is non-conformant in
   both directions: a trailing-slash variant of the seller's own URL is the *same* agent, and a
   canonicalized foreign URL is still foreign.

### 2.2 `core/format.json`

```
required: ['format_id', 'name']
format_id: {"$ref": "/schemas/core/format-id.json",
            "description": "This format's own identifier — a structured object {agent_url, id},
             not a string."}
```

Every entry in `formats[]` carries its own `format_id`; `agent_url` inside it names the defining agent.

### 2.3 `creative/list-creative-formats-request.json`

```json
"format_ids": {
  "type": "array",
  "description": "Return only these specific format IDs",
  "items": { "$ref": "/schemas/core/format-id.json" },
  "minItems": 1
}
```

The filter items are full format-id objects — i.e. the filter is keyed on `(agent_url, id)`, not `id`.
A well-formed single third-party reference satisfies `minItems: 1`, so **there is no validation
error to emit**: the request is valid, it simply selects nothing.

### 2.4 `creative/list-creative-formats-response.json`

```json
"formats": {
  "type": "array",
  "description": "Full format definitions for all formats this agent supports. Each format's
   authoritative source is indicated by its agent_url field.",
  "items": { "$ref": "/schemas/core/format.json" }
},
"creative_agents": {
  "type": "array",
  "description": "Optional: Creative agents that provide additional formats. Buyers can recursively
   query these agents to discover more formats. ...",
  "items": { ... "required": ["agent_url"] }
},
"errors": { "type": "array", "description": "Task-specific errors and warnings", ... },
"required": ["formats"]
```

Two decisive points:
- *"Each format's authoritative source is indicated by its `agent_url` field."* This is the schema
  sentence that makes "MUST NOT fabricate a local format entry" a real, gradeable obligation:
  returning an entry whose `agent_url` misstates who defines it violates the response contract.
- `formats` is **required**, and nothing sets `minItems`. An **empty `formats: []` is schema-valid**.
  So "returned nothing" is a conformant success response, not an error path.

---

## 3. Conflicts

### 3.1 Storyboard-internal tension (not a schema/storyboard conflict)

`list_formats_integrity` (`:356-359`) states an unconditional MUST that explicitly *includes* the
third-party case — resolve it *"whether it hosts that format directly or **proxies to the creative
agent named in `format_ids[0].agent_url`**."* The `creative_sync/list_formats` `refs_resolve`
(`:655-658`) says third-party refs are unverifiable and downgraded to observations. These are two
different checks in two different phases, so they do not literally contradict — but they pull in
opposite directions on the same input.

**Resolution under the stated authority order:** the 3.1.1 **schemas are silent on any obligation to
proxy.** `list-creative-formats-response.json` never requires a seller to resolve foreign references;
it only constrains the *shape and attribution* of whatever is returned, and explicitly permits an
empty `formats`. Per the project's source-of-truth rule (schema silent → production authoritative),
"the seller MUST proxy to third-party creative agents" is **not** something this scenario may assert.
What it may assert is the identity/attribution contract, which the schema states in binding terms.

### 3.2 Category error in the current scenario — confirmed

```gherkin
And the verification result should be reported as an observation rather than a graded failure
```

This is a claim about the **compliance runner's grading policy** (`on_out_of_scope: warn` →
*"pass the check, attach observations naming the skipped refs"*, storyboard-schema.yaml:1391-1392).
Our seller does not implement `refs_resolve`, does not read `on_out_of_scope`, and emits an
identical response whether the setting is `warn`, `ignore` or `fail`. **No seller behavior can
falsify this Then.**

The step body (`tests/bdd/steps/domain/uc005_format_id_third_party.py:91-102`) confirms it: it
asserts `ctx["error"] is None` plus `third_party not in returned` — the latter being a verbatim
duplicate of the preceding step's first assertion (`:78-80`). So the step is one generic no-error
check plus a copy of its sibling, wearing a name about runner grading. Delete the Then; keep the
no-error property under the existing generic `no error should be returned` phrasing.

By contrast, *"the seller MUST NOT fabricate a local format entry"* **is** gradeable, and 3.1.1
grounds it twice: `format-id.json` ("URL of the agent that **defines** this format", required pair)
and `list-creative-formats-response.json` ("Each format's authoritative source is indicated by its
`agent_url` field"). The current scenario is right about this half.

### 3.3 Wrong `path=` in the footer

§1.4. `creative/index.yaml` carries neither mechanism at 3.1.1.

### 3.4 Pin is older than our own pin

`04f59d2d5` is an ancestor of `3.1.0-beta.3` (our `adcp==5.7.0` target), so the scenario was pinned
behind the repo's own pin. Re-pinned to 3.1.1 here.

### 3.5 Missing checks the current scenario does not make

- **No positive control.** Every assertion in the current scenario is a *negative* ("X not in
  returned"). A seller that returned `formats: []` for **every** request passes it unchanged. The
  scenario cannot distinguish "correctly declined a foreign reference" from "totally broken filter."
  The rewrite adds own-agent_url rows that must resolve to exactly one entry.
- **No canonicalization coverage.** `format-id.json` makes canonicalized comparison a MUST, and the
  storyboard normalizes trailing-slash/case on both sides (`:1380-1382`). Neither direction is
  tested today: a trailing-slash variant of the seller's own URL must still resolve, and a
  case/slash variant of a foreign URL must still *not*. Both are added as Examples rows.
- **No exact-cardinality assertion.** `formats` is asserted only by non-membership; nothing pins
  how many entries come back, so an over-broad filter returning the whole catalog alongside the
  right entry would pass.
- **No `creative_agents` check.** 3.1.1 gives `creative_agents` as the sanctioned way to point a
  buyer at another creative agent, and production already emits referrals
  (`src/core/tools/creative_formats.py:463-482`, `:510`). Advertising a third-party agent the seller
  does not federate with is the *delegation-shaped* form of fabrication and is currently ungraded.

### 3.6 Cross-check (non-authoritative)

Production already implements the pair filter with canonicalization —
`src/core/tools/creative_formats.py:296-307` filters on `format_id_identity`, and
`src/core/schemas/_base.py:145-188` canonicalizes via `adcp.signing.canonicalize_target_uri`.
Verified behavior: `https://creative.adcontextprotocol.org/`,
`https://Creative.AdContextProtocol.ORG` and `HTTPS://creative.adcontextprotocol.org` all
canonicalize to `https://creative.adcontextprotocol.org`. Every Examples row below is therefore
expected to pass on current production — this re-pin is a strengthening of the grading, not a
production-behavior change request.

---

## 4. Proposed Gherkin

Complete replacement for `BR-UC-005-discover-creative-formats.feature:1077-1093` (tag line through
the `@source` footer). Tag vocabulary unchanged; the `@T-UC-005-...` id is kept verbatim so ledger
and traceability references still resolve (see Risks §6.1).

```gherkin
  @T-UC-005-storyboard-format-id-third-party-agent-out-of-scope @storyboard-v3.1 @v3-1 @format-id-roundtrip @third-party-agent
  Scenario Outline: Format ID filter resolves on the canonicalized (agent_url, id) pair -- <case>
    Given the seller catalog holds format "display_300x250_image" under the seller's own agent_url "https://creative.adcontextprotocol.org"
    And the seller hosts no format under the third-party agent_url "https://third-party-creative.example.com"
    When the Buyer Agent sends list_creative_formats with format_ids [{agent_url "<requested_agent_url>", id "display_300x250_image"}]
    Then the response should be schema-valid against list-creative-formats-response.json
    And no error should be returned
    And the formats array should contain exactly <resolved_count> entries
    And the returned format_id identity set should equal "<expected_identities>"
    And the creative_agents referrals should not include agent_url "https://third-party-creative.example.com"

    Examples: the seller's own agent_url resolves under canonicalization; a third-party agent_url never does
      | case                                  | requested_agent_url                       | resolved_count | expected_identities                                          |
      | own agent_url verbatim                | https://creative.adcontextprotocol.org    | 1              | https://creative.adcontextprotocol.org,display_300x250_image |
      | own agent_url trailing slash          | https://creative.adcontextprotocol.org/   | 1              | https://creative.adcontextprotocol.org,display_300x250_image |
      | own agent_url mixed-case host         | https://Creative.AdContextProtocol.ORG    | 1              | https://creative.adcontextprotocol.org,display_300x250_image |
      | third-party agent_url verbatim        | https://third-party-creative.example.com  | 0              | (none)                                                       |
      | third-party agent_url trailing slash  | https://third-party-creative.example.com/ | 0              | (none)                                                       |
      | third-party agent_url mixed-case host | https://Third-Party-Creative.Example.COM  | 0              | (none)                                                       |
    # AdCP 3.1.1. A format reference is the PAIR (agent_url, id) -- core/format-id.json
    # requires [agent_url, id] and mandates that callers "MUST canonicalize agent_url per the
    # AdCP URL canonicalization rules before treating two formats as the same". The seller's
    # catalog holds an entry whose id COLLIDES with the third-party reference but sits under the
    # seller's own agent_url: an id-only filter surfaces it for the foreign reference, which is
    # exactly the fabricated local entry list-creative-formats-response.json forbids when it says
    # "Each format's authoritative source is indicated by its agent_url field". The own-agent_url
    # rows are the positive control -- without them a seller that always returned formats: [] would
    # pass every negative row. formats is required but has no minItems, so the empty result on the
    # foreign rows is a schema-valid success, not an error (list-creative-formats-response.json).
    #
    # NOT asserted here, deliberately: whether the compliance RUNNER grades an unresolvable
    # third-party reference as an observation or a failure. That is the runner's
    # `on_out_of_scope: warn|ignore|fail` policy (universal/storyboard-schema.yaml:1389-1394,
    # "how refs outside scope are graded"), and the seller emits an identical response under all
    # three settings -- no seller behavior can falsify it. Only the seller-side obligation
    # (do not fabricate, do not substitute) is gradeable and it is what this scenario grades.
    #
    # Also not asserted: any obligation to PROXY the third-party agent. media-buy/index.yaml:356-359
    # says the seller MUST resolve products[0].format_ids[0] "whether it hosts that format directly
    # or proxies to the creative agent named in format_ids[0].agent_url", but the 3.1.1 schemas are
    # silent on proxying, so it is out of scope for this scenario. The sibling
    # @T-UC-005-storyboard-format-id-roundtrip-from-products covers the seller-hosted resolve path.
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/media-buy/index.yaml
    #   (phase product_discovery, step list_formats_integrity: field_value formats[0].format_id
    #    == $context.product_format_id -- "the agent cannot substitute a different format in
    #    response to the filter"; phase creative_sync, step list_formats: refs_resolve
    #    match_keys [agent_url, id])
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/format-id.json
    #   (required [agent_url, id]; MUST canonicalize agent_url before treating two formats as the same)
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/creative/list-creative-formats-response.json
    #   (required [formats], no minItems; "Each format's authoritative source is indicated by its agent_url field")
```

---

## 5. Step inventory

### 5.1 Reused unchanged (no new code)

| Step | Defined at |
|---|---|
| `Then the response should be schema-valid against list-creative-formats-response.json` | `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:93` |
| `Then no error should be returned` | `tests/bdd/steps/generic/then_error.py:519` (asserts `"error" not in ctx`) |

### 5.2 New steps (5)

| Step | Note |
|---|---|
| `Given the seller catalog holds format "{format_id}" under the seller's own agent_url "{agent_url}"` | Replaces the untyped `the seller has no local copy of that format in its own catalog`. Seeds the colliding-id local format via `FormatFactory` + `env.set_registry_formats`, same as `uc005_format_id_third_party.py:52-61`, but with the URL and id as explicit step arguments instead of module constants. |
| `Given the seller hosts no format under the third-party agent_url "{agent_url}"` | Asserts the seeded registry contains zero entries canonicalizing to that host, then records it in `ctx` for the referral check. Makes the premise falsifiable instead of implicit. |
| `When the Buyer Agent sends list_creative_formats with format_ids [{agent_url "{agent_url}", id "{format_id}"}]` | Builds `ListCreativeFormatsRequest(format_ids=[FormatId(...)])` and dispatches via `_call(ctx, req=req)` — the existing transport-agnostic dispatcher used at `uc005_format_id_third_party.py:68`. Sends the `agent_url` **verbatim** (uncanonicalized) so the canonicalization rows exercise production's normalization rather than the test's. |
| `Then the formats array should contain exactly {count:d} entries` | Exact cardinality against `_serialized_formats(ctx)` (wire on REST/A2A/MCP, production serializer on IMPL). |
| `Then the returned format_id identity set should equal "{expected}"` | Parses `"agent_url,id"` pairs (`(none)` → empty set), compares to `{format_id_identity(f.format_id) for f in response.formats}` as a set equality. Single assertion covering non-fabrication, non-substitution and verbatim roundtrip in both directions. |
| `Then the creative_agents referrals should not include agent_url "{agent_url}"` | Reads `creative_agents` off the wire response, canonicalizes each `agent_url`, asserts the third party is absent. Grades the delegation-shaped form of fabrication (§3.5). |

### 5.3 Retired (delete from `uc005_format_id_third_party.py`)

| Step | Why |
|---|---|
| `Then the verification result should be reported as an observation rather than a graded failure` (`:91-102`) | Category error (§3.2). Its no-error half moves to the existing generic `no error should be returned`; its second assertion is a verbatim duplicate of `:78-80`. |
| `Then the seller should NOT fabricate a local format entry to satisfy the third-party reference` (`:71-88`) | Subsumed by the identity-set equality. **Cannot** be reused inside the Outline: its body asserts `seller_local not in returned` (`:84-88`), which is correct for the foreign rows but false by construction on the own-agent_url rows. |
| `Given a product advertises a format_id whose agent_url points at a third-party creative agent` (`:45-48`) | Replaced by the two parameterized Givens; the module-constant `FormatId` no longer varies per row. |
| `Given the seller has no local copy of that format in its own catalog` (`:51-61`) | Replaced by `Given the seller catalog holds format ... under the seller's own agent_url ...`. |
| `When the Buyer Agent sends list_creative_formats with that third-party format_id` (`:64-68`) | Replaced by the parameterized When. |

Net: `uc005_format_id_third_party.py` is rewritten, not patched. The module docstring must drop its
`on_out_of_scope: warn` framing and re-pin to 3.1.1.

---

## 6. Risks

**6.1 Tag name no longer describes the scenario.** `@T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`
keeps "out-of-scope", which is precisely the runner-grading concept §3.2 removes. Kept verbatim so
existing traceability and any ledger entry still resolve. If the team prefers accuracy over
stability, rename to `@T-UC-005-storyboard-format-id-third-party-agent-not-fabricated` — but that is
a separate, deliberate decision, and every reference to the old id must move with it.

**6.2 Row-count growth.** 1 scenario → 6 Examples rows × 4 transports = 24 test instances, up from 4.
`Scenario Outline` is heavily used in this feature file (22 existing outlines) and each row is a
`CreativeFormatsEnv` integration test, so runtime cost is real but bounded.

**6.3 `creative_agents` referral check may be vacuous on the current fixture.** Production builds
referrals from `registry._get_tenant_agents(tenant_id)` (`creative_formats.py:470`). If
`CreativeFormatsEnv` seeds no tenant creative agents, `creative_agents` is `None` and the Then
passes trivially. To keep it meaningful the Given should seed at least one *legitimate* referral so
the assertion discriminates presence-of-others from absence-of-the-third-party. If the harness has
no seam for that, drop this Then rather than ship a vacuous one — flagging it now so it is a
decision, not an oversight.

**6.4 The `(none)` sentinel.** Empty Examples cells are ambiguous in Gherkin, hence `(none)`. The new
step must treat it as the empty set and must **not** silently treat an unparseable value as empty —
otherwise a typo'd row degrades into "assert nothing".

**6.5 Canonicalization rows depend on the SDK.** Rows 2/3 and 5/6 assume
`adcp.signing.canonicalize_target_uri` lowercases scheme+host and strips the trailing slash. Verified
against the installed SDK (§3.6), and the schema mandates the behavior — but it is SDK-implemented,
so an SDK bump could move it. That is arguably a feature: these rows would then correctly fail.

**6.6 The `_serialized_formats` wire guard.** It raises when a REST/A2A/MCP transport did not stash
`wire_response` (`uc005_format_id_shape.py:45-46`). `CreativeFormatsEnv` does stash, so the new
count/identity steps can reuse it — but any future re-homing of this scenario to another env breaks
loudly rather than silently, which is the intended behavior.

**6.7 `no error should be returned` is a generic step.** It checks `"error" not in ctx`, not the wire
envelope. Per `tests/CLAUDE.md` the wire envelope is the preferred authority for error-path
assertions — but this is a *success*-path scenario, `wire_error_envelope` is `None` by definition,
and the positive content is carried by the schema-validity, cardinality and identity-set Thens. Reuse
is appropriate here; no new envelope helper is warranted.

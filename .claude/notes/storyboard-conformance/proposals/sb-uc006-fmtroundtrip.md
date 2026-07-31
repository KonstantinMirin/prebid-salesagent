# Re-pin: `@T-UC-006-storyboard-format-id-roundtrip-on-sync`

Scenario: "Sync creative with the same format_id object returned by get_products -- seller MUST accept its own format_id"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-006-sync-creatives.feature:1626`

---

## 1. VERDICT

**GRADED — but the specific MUST the scenario names is prose, not a graded check.**

Two separable facts, both true:

1. The step this scenario belongs to **is graded** at 3.1.1 and **is on our conformance path**. It is
   `protocols/media-buy/index.yaml`, phase `creative_sync`, step `sync_creatives`, and it carries a real
   `validations:` block. The storyboard's `track: media_buy` matches our declared
   `supported_protocols=[SupportedProtocol.media_buy]` (`src/core/tools/capabilities.py:99-100,271-272`).
   No specialism gate stands between us and it. So `@storyboard-v3.1` stays.

2. The sentence the scenario is built on — "the seller must accept its own format_ids without
   modification" — appears **only** in that step's `narrative:` and `expected:` prose. It is **not** a
   `- check:` entry. A seller that rejects its own format_id with `action: "failed"` passes all four
   graded checks unchanged (`failed` is a legal `creative-action` enum value, so `field_present
   creatives[0].action` still holds, and the failed shape is still schema-valid).

**Recommendation:** keep `@storyboard-v3.1` (the binding is to a genuinely graded step), and rewrite the
assertions so they land on what *is* graded (`creatives[0].action` as a concrete value) plus what
production actually guarantees. The rewritten scenario below adds a negative row precisely because the
storyboard's own grading cannot distinguish accept from reject — the discrimination has to come from us.

Opaque identifier tag `@T-UC-006-storyboard-format-id-roundtrip-on-sync` unchanged — it is referenced from
`docs/test-obligations/bdd-traceability.yaml:4843`.

---

## 2. Real binding at 3.1.1

### What the footer wrongly points at

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/creative_reception.yaml
```

Both defects present, as the brief predicted:

- **Stale ref.** `04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin.
- **Off-by-one path.** `creative_reception.yaml` is the storyboard of the **next** scenario in the file
  (`@T-UC-006-storyboard-creative-reception-stateful-render`, line 1642 — which itself has *no* `@source`
  footer at all). My scenario's own prose names its true home in the summary line:
  `# media-buy/index.yaml creative_sync (format_id roundtrip)`.

`creative_reception.yaml` does exist at 3.1.1 (`protocols/media-buy/scenarios/creative_reception.yaml`) and
does have a `push_creatives` phase — but nothing in it concerns format_id roundtrip. Wrong file.

### The real one

`static/compliance/source/protocols/media-buy/index.yaml` — phase `creative_sync` (dist line 587),
step `sync_creatives` (dist line 671), title *"Push creative assets (format_id roundtrip)"* (dist line 672).

Verified on disk at `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/index.yaml`.
Note `dist/compliance/3.1.1/` ships the same file under **both** `protocols/` and `domains/` —
`diff protocols/media-buy/index.yaml domains/media-buy/index.yaml` is empty. The **source** tree at
`v3.1.1` has only `protocols/` (`git ls-tree v3.1.1 static/compliance/source/` → protocols, specialisms,
test-kits, test-vectors, universal). So `protocols/` is the correct prefix for an `@source path=`.

**Graded `validations:` block, verbatim (dist lines 731-743):**

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_present
            path: "creatives[0].action"
            description: "Each creative has an action (created/updated)"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "media_buy_seller--sync_creatives"
            description: "Context correlation_id returned unchanged"
```

The roundtrip MUST lives here instead — **prose, ungraded** (dist lines 673-677, 695-696):

```yaml
        narrative: |
          The buyer uploads creative assets for the confirmed packages. The first
          creative uses $context.product_format_id — the exact format_id object
          returned by get_products. This is the roundtrip test: the seller must
          accept its own format_ids without modification. If the seller's validation
          rejects a format_id that it returned in products, this step fails.
...
        expected: |
          ...
          The first creative uses a format_id extracted from get_products.
          If this is rejected, your format_ids do not roundtrip correctly.
```

The mechanism is the `sample_request`: `format_id: "$context.product_format_id"` (dist line 705), the object
captured from `products[0].format_ids[0]`. The storyboard *feeds* the seller its own format_id but never
grades the outcome beyond "an action field exists".

**Tier:** `protocols/` (a track-gated protocol storyboard, `track: media_buy`), not `universal/`,
not `specialisms/`. On our path.

**Contrast — where a verbatim roundtrip IS graded at 3.1.1** (and worth citing in the rewrite comment):
the sibling `list_formats_integrity` step, dist lines 405-409:

```yaml
          - check: field_value
            path: "formats[0].format_id"
            value: "$context.product_format_id"
            description: "Returned format_id round-trips verbatim — the agent cannot substitute a different format in response to the filter"
```

That is `list_creative_formats`, i.e. UC-005's scenario — not this one. UC-005 owns the graded verbatim
roundtrip; UC-006 owns the ungraded acceptance claim.

---

## 3. Schema constraints at 3.1.1

### `core/format-id.json` (`git show v3.1.1:static/schemas/source/core/format-id.json`)

```json
  "required": [ "agent_url", "id" ],
```
```json
    "agent_url": {
      "type": "string", "format": "uri",
      "description": "... Callers comparing two `format-id` values MUST canonicalize `agent_url` per the AdCP URL canonicalization rules before treating two formats as the same. See docs/reference/url-canonicalization."
    },
    "id": { "type": "string", "pattern": "^[a-zA-Z0-9_-]+$", ... }
```

Title: *"Format Reference (Structured Object)"* — "A JSON object — never a plain string ... Using a plain
string here is a schema violation." Identity is the **pair**, compared **after canonicalization**.

### `creative/sync-creatives-response.json` (`git show v3.1.1:...`)

Three mutually exclusive branches under `oneOf`: `SyncCreativesSuccess` (`required: ["creatives"]`,
`not` `errors`/`task_id`/`status:"submitted"`), `SyncCreativesError` (`required: ["errors"]`,
`minItems: 1`, `not` `creatives`), `SyncCreativesSubmitted` (`required: ["status","task_id"]`).
Plus `allOf` → `core/version-envelope.json` **and** `core/protocol-envelope.json`.

Per-creative item:

```json
            "required": [ "creative_id", "action" ],
```
```json
            "allOf": [ { "if": { "properties": { "action": { "enum": ["failed","deleted"] } },
                                 "required": ["action"] },
                        "then": { "not": { "required": ["status"] } } } ]
```

`action` → `enums/creative-action.json`: `["created","updated","unchanged","failed","deleted"]` —
**`failed` is a legal action**, which is exactly why `field_present creatives[0].action` cannot grade
acceptance. `status` → `enums/creative-status.json`: `["processing","pending_review","approved",
"suspended","rejected","archived"]`, and is described as *"a UI hint ... NOT a spend-authorization gate"*.

**There is no `format_id` field on the per-creative result.** The sync response cannot, by schema, carry
the echoed format_id. "Roundtrips without modification" is therefore not directly observable on this
call — see Conflicts.

---

## 4. Conflicts

**Schema vs storyboard.** No contradiction here; the schema is silent where the storyboard is prose. But
the schema **overrides the scenario's second Then**: `And the seller's own format_id object should
roundtrip through sync_creatives without modification` asserts a property of a field that
`sync-creatives-response.json` does not define on `creatives[]`. That Then is unassertable at the sync
boundary as written — it is not merely vacuous, it is unbindable. It must be re-expressed against
something the wire actually carries.

**What the current scenario gets wrong:**

1. `Then the per-creative result should NOT report action "failed" due to format_id rejection` — negative
   phrasing with a causal qualifier ("due to format_id rejection") the response cannot express. The wire
   has an action value; it has no rejection-reason taxonomy tied to format_id. Also a NOT-assertion of
   this shape is the sort of thing `test_architecture_bdd_no_trivial_assertions.py` exists to stop.
2. `And the seller's own format_id object should roundtrip through sync_creatives without modification` —
   unbindable per above.
3. **No negative control.** Since production's own harness (`CreativeSyncEnv._configure_mocks`,
   `tests/harness/creative_sync.py:85`) stubs `registry.get_format` to return a truthy value for *every*
   `(agent_url, id)`, a bare "was not rejected" assertion passes in-process **no matter what format_id is
   sent**. Green and worthless. The rewrite adds a row for a format_id the seller never advertised, so the
   accepted row has content.
4. **The scenario is dormant.** None of its three step phrasings exist in `tests/bdd/steps/`
   (`grep -rn "captured a format_id\|without modification" tests/bdd/steps/` matches only the UC-005 file).
   It has never graded anything.
5. Stale + off-by-one `@source` (section 2).

**What it misses:** the one thing production *does* let you observe about "without modification" — on an
identical resubmission, `_update_existing_creative` (`src/core/tools/creatives/_processing.py:114-128`)
appends `"format"` to `changes[]` **iff** the stored `(agent_url, format, format_parameters)` differ from
what the request carries. So "`format` absent from `changes` on an identical resubmission" is a real,
wire-observable, transport-independent roundtrip detector. That is where the rewrite puts the roundtrip
claim.

**Note on canonicalization (the lead's pointer).** `core/format-id.json` mandates canonicalized `agent_url`
comparison, and production *has* the helper (`canonical_agent_url` / `format_id_identity`,
`src/core/schemas/_base.py:156-199`). But the sync path does **not** use it — see TICKET MATERIAL T1-T3.
Worse, `CreativeAgentRegistry.get_format` (`src/core/creative_agent_registry.py:863-884`) matches on
`fmt.format_id.id == format_id` and **ignores `agent_url` entirely**, and under `ADCP_TESTING=true`
(`:654-655`) returns the whole reference catalog regardless of which agent was asked. Consequence: a
Scenario Outline over six canonicalization spellings of `agent_url` **would pass on every row and prove
nothing** — it would pass because `agent_url` is never compared, not because canonicalization works.
That is the definition of a green-but-vacuous outline, so I deliberately did **not** write one. The
canonicalization obligation goes to tickets, where it can be fixed and then graded honestly.

---

## 5. Proposed Gherkin

Replacement for lines 1626-1641. GREEN ONLY — every Then below is traced to production in section 4 / the
step inventory.

```gherkin
  @T-UC-006-storyboard-format-id-roundtrip-on-sync @storyboard-v3.1 @v3-1 @format-id-roundtrip
  Scenario Outline: sync_creatives accepts the format_id the seller itself advertises -- <format_id_source>, <submission>
    Given the seller advertises a format_id {agent_url, id} on a product in its own catalog
    And the Buyer Agent submits a creative whose format_id is <format_id_source>
    And the sync is the <submission> of that creative
    When the Buyer Agent syncs the creative
    Then the action should be "<action>"
    And the per-creative result should carry exactly <error_count> error entries
    And the per-creative result should report creative_id echoing the submitted creative_id
    And the per-creative result should not list "format" among its changes
    And the response does not carry an operation-level errors array

    Examples: the seller's own format_id is accepted and stored verbatim; one it never advertised is not
      | format_id_source                                | submission             | action  | error_count |
      | the exact object the seller advertises          | first submission       | created | 0           |
      | the exact object the seller advertises          | identical resubmission | updated | 0           |
      | an id absent from the seller's own catalog      | first submission       | failed  | 1           |

    # protocols/media-buy/index.yaml phase creative_sync, step sync_creatives
    # ("Push creative assets (format_id roundtrip)"). The storyboard feeds the seller
    # $context.product_format_id -- the exact {agent_url, id} object it returned on
    # products[0].format_ids[0] -- and grades response_schema plus field_present
    # creatives[0].action. It does NOT grade acceptance: "failed" is a legal
    # creative-action value (enums/creative-action.json), so a seller that rejects its
    # own format_id still passes every check. Row 3 supplies the discrimination the
    # storyboard lacks: a format_id absent from the seller's catalog must be rejected,
    # which is what makes rows 1-2 non-vacuous.
    #
    # Row 2 is the "without modification" half. sync-creatives-response.json defines no
    # format_id on creatives[], so the echo is not observable on this call; the wire
    # signal is changes[]. _update_existing_creative appends "format" iff the stored
    # (agent_url, format, format_parameters) differ from the resubmitted object, so
    # "format" absent from changes on a byte-identical resubmission is direct evidence
    # the seller stored its own format_id verbatim.
    #
    # NOT asserted here, and why: (a) the storyboard's context / context.correlation_id
    # echo checks -- REST drops context, so they cannot pass transport-independently
    # (see #<context-echo>); (b) any agent_url canonicalization variation -- the sync
    # path resolves formats by `id` alone and never compares agent_url
    # (creative_agent_registry.py get_format), so spelling rows would pass for the wrong
    # reason (see #<pair-identity>).
    #
    # creative_sync: the seller MUST accept the format_id it advertised on its own products
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/index.yaml phase=creative_sync step=sync_creatives
```

Replace `#<context-echo>` / `#<pair-identity>` with the GitHub issue numbers filed from T1 and T6.

---

## 6. Step inventory

**Existing — reuse as-is (no new phrasing):**

| Step | Definition |
|---|---|
| `When the Buyer Agent syncs the creative` | `tests/bdd/steps/domain/uc006_sync_creatives.py:253` (`when_sync_creative`) |
| `Then the action should be "<expected_action>"` | `uc006_sync_creatives.py:6743` (`then_action_should_be` → `_get_sync_creative_result` :2646) |
| `And the response does not carry an operation-level errors array` | `uc006_sync_creatives.py:6993` (`then_no_operation_level_errors`) — asserts the `SyncCreativesSuccess` branch of the 3.1.1 `oneOf` |

**New — four steps, all in `uc006_sync_creatives.py` (same module as the helpers they need):**

1. `Given the seller advertises a format_id {agent_url, id} on a product in its own catalog`
   Seeds `ProductFactory(format_ids=[_product_format_entry(ctx, env)])` + `PricingOptionFactory` via the
   existing helpers at `uc006_sync_creatives.py:69` and stores the entry as `ctx["advertised_format_id"]`.
   Asserts the seeded product's `format_ids[0]` equals `ctx["advertised_format_id"]` so the Given is not a
   hollow precondition. Uses `_e2e_unique_id` for the product id under e2e.

2. `And the Buyer Agent submits a creative whose format_id is <format_id_source>`
   `parsers.parse`. Two values:
   - *the exact object the seller advertises* → copies `ctx["advertised_format_id"]` verbatim into the
     payload, with assets from the existing `_format_payload(ctx, env)` (`:44`) so the accepted rows use
     the exact fixture combination existing green UC-006 scenarios already use.
   - *an id absent from the seller's own catalog* → same `agent_url`, `id: "format_never_advertised"`.
     Under e2e the Docker creative agent rejects it for real. In-process, `CreativeSyncEnv` stubs
     `registry.get_format` truthy for everything (`tests/harness/creative_sync.py:85`), so this branch
     replaces that stub with an `AsyncMock(side_effect=…)` returning `None` for the unadvertised id and
     the default format object otherwise — a **harness-parity shim that reproduces what e2e gets for
     free**, not scenario rigging, and it touches only row 3.
   Creative id: `_e2e_unique_id("creative")` under e2e (per `:80`, so a prior run's row cannot turn row 1's
   `created` into `updated`), fixed id otherwise.

3. `And the sync is the <submission> of that creative`
   `first submission` → no-op. `identical resubmission` → one prior `dispatch_request(ctx, creatives=...)`
   with the byte-identical payload, over the *same* transport (so it works in-network on e2e too — no
   in-process bypass, no ledger entry). Then clears `ctx["response"]` so the When's result is the one
   asserted.

4. `Then the per-creative result should carry exactly <error_count> error entries`
   `parsers.parse("...exactly {error_count:d} error entries")`; `len(getattr(result, "errors", None) or [])
   == error_count` (REST omits empty lists, hence the `or []`).

5. `Then the per-creative result should report creative_id echoing the submitted creative_id`
   `result.creative_id == ctx["submitted_creative_id"]`. Grades `required: ["creative_id","action"]`.

6. `Then the per-creative result should not list "format" among its changes`
   `"format" not in (getattr(result, "changes", None) or [])`. Load-bearing on row 2, true by construction
   on rows 1 and 3 (`changes` is `[]` on create and on `_failed_sync_result`).

Totals: **3 existing phrasings reused, 6 new phrasings** across 6 new step functions (items 1-6 above);
items 2 and 3 are `parsers.parse` steps whose Examples columns supply two values each.

---

## 7. TICKET MATERIAL

- **T1 — sync_creatives resolves formats by `id` alone; `agent_url` is never compared.**
  `CreativeAgentRegistry.get_format` (`src/core/creative_agent_registry.py:863-884`) builds a throwaway
  `CreativeAgent(agent_url=…)`, fetches that agent's catalog, then matches `if fmt.format_id.id ==
  format_id`. `_validate_creative_input` (`src/core/tools/creatives/_validation.py:126-135`) passes the
  agent_url only as a catalog selector, and under `ADCP_TESTING=true` (`creative_agent_registry.py:654-655`)
  the catalog is returned regardless of which agent was asked. A creative referencing
  `{agent_url: "https://someone-else.example", id: "display_300x250_image"}` is therefore accepted as
  though the seller hosted it. Mandated fix: compare on `format_id_identity`
  (`src/core/schemas/_base.py:180-199`). Clause: `core/format-id.json` at v3.1.1 — `required:
  ["agent_url","id"]` and *"Callers comparing two `format-id` values MUST canonicalize `agent_url` per the
  AdCP URL canonicalization rules before treating two formats as the same"*. **DRY/asymmetry:**
  `list_creative_formats` already does it correctly (`src/core/tools/creative_formats.py:312-313`) — one
  concept, two identity rules.

- **T2 — format-spec lookup inside sync uses raw Pydantic equality, silently skipping processing on a
  canonically-equal spelling.** `src/core/tools/creatives/_processing.py:194-196` (create) and `:511-514`
  (update) do `if fmt.format_id == creative_format`. A trailing slash, uppercase host, or explicit default
  port makes the match fail; `format_obj` stays `None`, the `if format_obj and format_obj.agent_url:` guard
  at `:199` / `:517` falls through, and generative detection + preview generation are skipped **with no
  error and no warning**. Clause: same canonicalization MUST in `core/format-id.json`; also violates
  CLAUDE.md "No Quiet Failures". Fix: `format_id_identity(fmt.format_id) == format_id_identity(creative_format)`.

- **T3 — identical-modulo-canonicalization resubmission rewrites the row and reports a spurious
  `changes: ["format"]`.** `_update_existing_creative` (`src/core/tools/creatives/_processing.py:118-128`)
  compares `new_agent_url != existing_creative.agent_url` byte-wise. Same clause as T1/T2. This is the
  reason the proposed scenario can only assert the *byte-identical* resubmission row; the canonical-variant
  row becomes assertable once this is fixed.

- **T4 — a correctable format-validation failure is emitted on the wire as `SERVICE_UNAVAILABLE`.**
  `_validate_creative_input` raises `AdCPValidationError` ("Unknown format '<id>' from agent <url>",
  `_validation.py:130-135`), whose class defaults are `error_code="VALIDATION_ERROR"`,
  `recovery="correctable"` (`src/core/exceptions.py:421-426`). The catch site `src/core/tools/creatives/
  _sync.py:338-355` calls `_failed_sync_result(creative_id, error_msg)` **without forwarding the code or
  recovery**, and `_failed_sync_result` defaults to `code="SERVICE_UNAVAILABLE", recovery=None`
  (`src/core/tools/creatives/_processing.py:34-56`). The buyer is told to retry an infra outage when the
  correct signal is "fix your payload". Clause: `core/error.json` +
  `universal/error-compliance.yaml` at 3.1.1. This is why the proposed row 3 asserts only the error
  **count**, not the code — asserting `SERVICE_UNAVAILABLE` would pin the defect into the baseline.

- **T5 — `SyncCreativeResult.status` is inherited but never populated, so the sibling multi-format
  scenario is red/vacuous.** `src/core/schemas/creative.py:369-378` records the owner decision to inherit
  but not populate `status` (it stays `None`; A2A/REST omit it, MCP serializes `null`).
  `@T-UC-006-storyboard-multi-format-sync` (feature line ~1613) asserts *"every per-creative result should
  expose action and status fields"* and *"every status value should be drawn from the creative-status
  enum"*. Against 3.1.1 `sync-creatives-response.json`, `status` is optional on the success branch and
  MUST be absent when `action` is `failed`/`deleted` — so the scenario over-specifies. Owner call needed:
  populate `status`, or re-ground that scenario. Not in my scope; flagged so it is not rediscovered.

- **T6 — the storyboard's two `context` checks cannot be asserted transport-independently.**
  `field_present context` and `field_value context.correlation_id == "media_buy_seller--sync_creatives"`
  are graded (dist lines 737-743) but REST drops `context` (`src/routes/api_v1.py`, per the brief's known-
  gaps list; Pattern #5 violation). Until that is fixed, the correlation-id echo — the *only* strictly
  graded field-value check on this step — is untestable in the four-transport harness.

- **T7 — the pinned schema fixtures cannot grade `check: response_schema` at 3.1.1.**
  `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, and `then_response_schema_valid` runs
  no validator despite `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing (both from
  the brief's known-gaps list). Specifically ungradeable today: the three-branch `oneOf`, the
  `SyncCreativesSubmitted` `status`/`task_id` branch, and the `if action in [failed,deleted] then not
  status` conditional.

- **T8 — `@source` off-by-one is present on this scenario** (cited `creative_reception.yaml`, i.e. the next
  scenario's storyboard) **and its neighbour has no `@source` at all**
  (`@T-UC-006-storyboard-creative-reception-stateful-render`, feature line 1642, is the real
  `creative_reception.yaml` owner). Sweep-level, presumably already tracked.

---

## 8. Risks

- **Not executed.** I own a proposal, not an edit, and the repo is read-only to me — no `pytest` run
  backs any "GREEN" claim below. Everything is traced by reading `src/` and the harness. The three
  assertions I am most confident in are `action`, `errors` count, and `creative_id` echo (all three
  reuse or mirror existing green UC-006 steps).
- **Row 3 in-process depends on a harness shim.** `CreativeSyncEnv` stubs `registry.get_format` truthy for
  everything, so without the shim the "never advertised" row would come back `created` and the row would be
  red. The shim is small and local, but it *is* mock injection; if the lead prefers zero injection, row 3
  must move to a companion scenario and rows 1-2 lose their negative control.
- **Row 3 on e2e_rest depends on the Docker creative agent rejecting an unknown id** rather than being
  unreachable. If the agent is down, `fetch_format_spec` raises a *transient* `AdCPError` which
  `_sync.py:347-348` **re-raises** as a request-level failure — the dispatch errors instead of returning
  `action: "failed"`, and the row goes red for an infra reason. Acceptable (the same dependency exists for
  every e2e format scenario), but it is a real flake surface.
- **No precedent for a `Given` that dispatches.** Every `dispatch_request` call in
  `uc006_sync_creatives.py` today sits in a `When`. Step 3 ("identical resubmission") introduces a Given
  that dispatches. It stays on the scenario's transport (unlike UC-005's in-process capture), which is what
  keeps it off the e2e ledger — but it is a new pattern and a reviewer may want it as a second `When`
  instead.
- **The get_products provenance chain is not reproduced.** The storyboard's format_id comes from
  `$context.product_format_id`, an actual `get_products` response. UC-005 does capture that way
  (`tests/bdd/steps/domain/uc005_format_id_roundtrip.py:29-79`) — and pays for it: its roundtrip scenario
  is **on the e2e_rest known-failures ledger** (`tests/bdd/e2e_rest_known_failures.txt`, "parallel
  e2e_rest mock-injection artifacts",
  `test_format_id_roundtrip__list_creative_formats_returns_the_same_format_object_that_get_products_advertised[e2e_rest]`),
  because in-process capture is invisible to the Docker server. Since the ledger may only shrink, I
  sourced the advertised object from `_product_format_entry(ctx, env)` — the same `{agent_url, id}` the
  product is seeded with and the same one `_format_payload` puts on the creative — rather than from a live
  `get_products` call. Identical value, weaker provenance. Making it a true cross-tool chain needs a
  harness that can dispatch a *different* tool over the scenario's transport; that does not exist today
  and is worth its own ticket if the lead wants the chain graded literally.
- **Drift note only (not authority):** at HEAD/3.1.8 this step may have gained checks. We are pinned at
  3.1.1 and I graded against 3.1.1 exclusively.

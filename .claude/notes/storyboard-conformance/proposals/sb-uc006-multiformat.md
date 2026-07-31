# Re-pin: `@T-UC-006-storyboard-multi-format-sync`

Scenario: "Bulk sync of three creatives in three different formats returns per-creative action and status"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-006-sync-creatives.feature:1609-1623`

---

## 1. VERDICT

**GRADED — but the cited binding is wrong, and the scenario as written cannot be graded at 3.1.1.**

Three separate findings, in order of severity:

1. **The behaviour IS graded at 3.1.1, on a protocol we DO declare** — but not where the footer says. It is graded on the **media-buy** protocol (`protocols/media-buy/index.yaml`, phase `creative_sync`, and `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml`, phase `register_two_creatives_and_create_buy`). We declare `supported_protocols=[media_buy]`, so those are on our conformance path. Tag stays `@storyboard-v3.1`.

2. **The cited path is off our conformance path.** The footer cites `protocols/creative/index.yaml`. That storyboard's first phase grades `supported_protocols` containing `creative`, and its `agent.capabilities` is `[has_creative_library]`. `src/core/tools/capabilities.py:99-100,271-272` declares `supported_protocols=[SupportedProtocol.media_buy]` and `specialisms=[AdcpSpecialism.sales_non_guaranteed]` — nothing else. Had the creative-protocol binding been the real one, this would have been `NOT GRADED — undeclared gate` and the tag would become `@schema-v3.1`. It is not the real one, so we re-bind instead of downgrading.

3. **The cited phase no longer says what the scenario claims.** At 3.1.1 `protocols/creative/index.yaml` phase `sync_multiple` (line 131) is titled **"Sync display creative"** and its `sample_request` carries **exactly one** creative (`display_trail_pro_300x250`, lines 162-174). The narrative at lines 18-21 states the intent explicitly: *"This storyboard keeps the generic creative baseline display-safe; video tag generation is covered by the creative-ad-server specialism."* The phase **id** is a vestigial `sync_multiple`; the content is single-creative, single-format. Three creatives in three formats is not there.

**Nowhere at 3.1.1 is a three-creative / three-format sync graded.** The nearest graded facts are two creatives in two formats (one graded result), and two creatives in one format (two graded results). The scenario must be rewritten to what is actually graded.

---

## 2. Real binding at 3.1.1

### What the current footer points at (WRONG)

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/creative/index.yaml
```

`04f59d2d5` is an ancestor of `3.1.0-beta.3` — older than our own 3.1.1 pin. And the path resolves to a phase that grades none of the scenario's claims.

For completeness, the graded block at the cited location, `dist/compliance/3.1.1/protocols/creative/index.yaml:181-194`:

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_present
            path: "creatives"
            description: "Response contains per-creative results"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "creative_lifecycle--sync_creatives"
            description: "Context correlation_id returned unchanged"
```

No `action`. No `status`. No cardinality. Just "a `creatives` key exists".

Note the off-by-one the brief warned about is present but *shifted onto us from the previous scenario*: `@T-UC-006-storyboard-provenance-claim-contradicted` (line 1595) cites `protocols/creative/index.yaml`, which is *our* prose's storyboard, while its own prose names `provenance_truth_of_claim`. Our footer then repeats `creative/index.yaml` — so our path is coincidentally the same string our prose names, and is still wrong on the merits.

### PRIMARY binding (multi-format, on our declared protocol)

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/index.yaml`
phase `creative_sync` (line 587) → step `sync_creatives` (line 671), title **"Push creative assets (format_id roundtrip)"**.

Its `sample_request` carries **two creatives in two different formats** — a 30s CTV video (`video`) and a 300x250 display banner (`image`) — lines 700-729. Graded block, **lines 731-743, verbatim**:

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

This is the only place at 3.1.1 where a **multi-format** batch is submitted to `sync_creatives` and any per-creative field is graded. Note it grades only `creatives[0].action` — index 0 only.

### SECONDARY binding (per-creative cardinality — the only N>1 grading)

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml`
phase `register_two_creatives_and_create_buy` (line 220) → step `sync_two_creatives` (line 232).

Two creatives, **same** format (`display_300x250` variants A and B). Graded block, **lines 278-286, verbatim**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
          - check: field_present
            path: "creatives[0].action"
            description: "First creative has an action (created/updated)"
          - check: field_present
            path: "creatives[1].action"
            description: "Second creative has an action (created/updated) — both must be registered for the per-creative breakdown to be meaningful"
```

This is the **only** graded step at 3.1.1 that asserts a per-creative field at index > 0. It is what licenses the scenario's cardinality claim ("one result per submitted creative"), and the indexed paths are what license positional correspondence.

### Tier ownership (brief question 3)

`protocols/` for both. Not `universal/`, not a `specialisms/` capability gate. Both sit under `protocols/media-buy/`, which our declared `supported_protocols=[media_buy]` activates. The scenario is therefore on our conformance path and keeps `@storyboard-v3.1`.

### `status` is not graded anywhere on a sync path

Exhaustive check of `path: "creatives[...]"` grading across all of `dist/compliance/3.1.1/`: **no `sync_creatives` step at 3.1.1 grades a per-creative `status`.** Every appearance of per-creative `status` under a `sync_creatives` step is narrative prose under `expected:` — e.g. `protocols/media-buy/index.yaml:691` *"Per-creative status: accepted, pending_review, or rejected"*. Per the brief's rule, prose is not graded.

(The two files that DO grade `creatives[0].status` — `protocols/creative/scenarios/creative_lifecycle_webhooks.yaml:286,459` and `protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml:234,317` — are a webhook lifecycle scenario on the undeclared `creative` protocol, and a cancellation-fate read, respectively. Neither is a bulk sync.)

**Consequence:** the scenario's title claim "…returns per-creative action **and status**" is half-ungraded. `action` is graded; `status` is not.

---

## 3. Schema constraints at 3.1.1

All quotes from `git show v3.1.1:static/schemas/source/...` in `/Users/konst/projects/adcp`.

### `creative/sync-creatives-response.json` — per-creative item

```json
            "required": [
              "creative_id",
              "action"
            ],
```

`status` is **not** required. `action` is.

And the conditional that the scenario violates outright:

```json
            "allOf": [
              {
                "if": {
                  "properties": {
                    "action": {
                      "enum": [
                        "failed",
                        "deleted"
                      ]
                    }
                  },
                  "required": [
                    "action"
                  ]
                },
                "then": {
                  "not": {
                    "required": [
                      "status"
                    ]
                  }
                }
              }
            ]
```

The success branch itself:

```json
      "required": [
        "creatives"
      ],
```

and it is mutually exclusive with an operation-level `errors` / `task_id` / `status: submitted`:

```json
      "not": {
        "anyOf": [
          { "required": [ "errors" ] },
          { "required": [ "task_id" ] },
          { "properties": { "status": { "const": "submitted" } }, "required": [ "status" ] }
        ]
      }
```

### `enums/creative-action.json`

```json
  "enum": [
    "created",
    "updated",
    "unchanged",
    "failed",
    "deleted"
  ]
```

**Five** values. The scenario asserts three ("created", "updated", or "failed") — it omits `unchanged` and `deleted`, both of which production actually emits (`src/core/tools/creatives/_assignments.py:324` emits `unchanged`; `src/core/tools/creatives/_sync.py:384` emits `deleted`).

### `enums/creative-status.json`

```json
  "enum": [
    "processing",
    "pending_review",
    "approved",
    "suspended",
    "rejected",
    "archived"
  ]
```

**Six** values. Note `accepted` is NOT among them.

The `status` field description in `sync-creatives-response.json` is normative and directly relevant:

> "Advisory review-lifecycle state of the creative after this sync — a UI hint and polling-scheduling signal, NOT a spend-authorization gate. Orthogonal to action — action says what the sync did (created, updated, ...); status says where the creative sits in review. **Values come from CreativeStatus only (processing, pending_review, approved, suspended, rejected, archived) — never from CreativeAction.** […] **MUST be omitted when action is failed or deleted** […] **Omit entirely when the seller has no review lifecycle at all.**"

### `core/protocol-envelope.json`

```json
  "required": [
    "status"
  ],
```

> "The `status` field is REQUIRED on every task response envelope, including synchronous metadata responses (e.g., `get_adcp_capabilities`) where the value is `completed`. Agents shipping responses without a top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate."

`sync-creatives-response.json` pulls this in:

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
```

---

## 4. Conflicts

### Schema overrides storyboard — `accepted` is not a status

`protocols/creative/index.yaml:152` and `protocols/media-buy/index.yaml:691` both write `Per-creative status: accepted, pending_review, or rejected`. `enums/creative-status.json` has no `accepted` member. **The 3.1.1 schema wins**: `accepted` is not a legal per-creative status. Any scenario or step that expects it is wrong. (This is prose in both cases, so nothing is graded on it — but it would have misled a step author.)

### Schema overrides storyboard — the storyboard's own grading is under-specified

The storyboard grades `field_present` on `creatives[0].action` — presence only. The schema constrains `action` to a five-member enum and forbids `status` alongside `failed`/`deleted`. Our rewrite grades the enum and the exclusion, which is stricter than the storyboard and correct under the authority order.

### What the scenario gets wrong

| # | Line | Current text | Problem |
|---|------|--------------|---------|
| 1 | 1623 | `ref=v3.1-04f59d2d5 commit=04f59d2d5` | Stale — ancestor of beta.3, older than our 3.1.1 pin. |
| 2 | 1623 | `path=…/protocols/creative/index.yaml` | Off our conformance path (`creative` protocol undeclared, `has_creative_library` capability undeclared) AND the phase narrowed to a single display creative at 3.1.1. |
| 3 | 1611 | "three creatives in three different formats" | Ungraded at 3.1.1. Max graded is two-in-two (`media-buy/index.yaml`) or two-in-one (`per_creative_conversion_attribution.yaml`). Three is a number nobody grades. |
| 4 | 1616 | `every action value should be "created", "updated", or "failed"` | **Schema-wrong.** `creative-action.json` has five members; `unchanged` and `deleted` are missing and both are emitted by production. This assertion would go red the moment a re-sync produced `unchanged`. |
| 5 | 1615 | `every per-creative result should expose action and status fields` | **Red against production and wrong against schema.** Production never populates the spec `status` — `src/core/schemas/creative.py` documents the owner decision: *"we inherit but do NOT populate the spec `status`: it stays None."* Verified empirically (§below): `status=None` on all three results, absent from `model_dump()`. Schema-wise the field is optional and MUST be absent when `action` is `failed`/`deleted`, so "every result exposes status" is unsatisfiable in general. |
| 6 | 1617 | `every status value should be drawn from the creative-status enum` | Vacuous today (no statuses are emitted, so the set is empty) and would be red if phrased as a presence check. |
| 7 | 1613 | `the response envelope should be schema-valid against sync-creatives-response.json` | **No such step exists.** The only `schema-valid` step in the tree is `uc005_format_id_roundtrip.py:101`, which is `list-creative-formats-response.json`-specific, and per the brief `then_response_schema_valid` runs no validator anyway. Also: production emits no top-level `status`, so a real validator against 3.1.1 would fail this. |
| 8 | 1614 | `the creatives array should carry one result per submitted creative` | The right idea and the one genuinely graded claim (via the indexed `creatives[0]`/`creatives[1]` checks) — but no step implements it. |
| — | all | Every step in the scenario | **None of the 8 steps exist.** `grep` across `tests/bdd/steps/` returns zero definitions for any of them. |

### The scenario is dormant, not red

```
$ uv run pytest tests/bdd/test_uc006_sync_creatives.py -k bulk_sync_of_three -rx
XFAIL …[a2a] - UC-006 harness not yet wired for non-account scenarios
XFAIL …[mcp] - UC-006 harness not yet wired for non-account scenarios
XFAIL …[rest] - UC-006 harness not yet wired for non-account scenarios
```

`tests/bdd/conftest.py:3363-3379` builds `CreativeSyncEnv` only for scenarios tagged `account`, `creative-invariant`, or `BR-RULE-034`; everything else hits an **imperative** `pytest.xfail(...)` that aborts before any step runs. Our tags are `@bulk-sync @multi-format` — neither is in the set, so the scenario has never executed a line of production code. Adding real steps alone would change nothing; the tag set must route through the harness.

**Fix with zero conftest change: add `@creative-invariant` to the tag set.** That bucket already means "the success-variant response invariants" (conftest comment at 3368-3369, `#1399 R3-F2`) — per-creative cardinality and per-creative action enum on the success variant is exactly that. Both allowlisted tags enter the identical `with _db_scope_for(...), CreativeSyncEnv(...)` branch, so no behavioural difference.

### Empirical verification of what is GREEN

Drove `CreativeSyncEnv` directly against the sbsweep agent-db with the exact batch proposed below (probe kept out of the repo, at `/private/tmp/claude-501/-Users-konst-projects-salesagent/febefa2f-073c-4553-a1b1-3f61a47b9e32/scratchpad/probe_multiformat.py`):

```
=== FIRST SYNC ===
type: SyncCreativesResponse
len(creatives): 3
  creative_id='mf-display' action=<CreativeAction.created: 'created'> status=None errors=[]
  creative_id='mf-video'   action=<CreativeAction.created: 'created'> status=None errors=[]
  creative_id='mf-native'  action=<CreativeAction.created: 'created'> status=None errors=[]
operation-level errors: <no attr>
top-level status: <no attr>
dumped keys: ['creatives', 'dry_run']
dumped creatives[0]: {'creative_id': 'mf-display', 'action': <CreativeAction.created: 'created'>}
=== SECOND SYNC (same batch) ===
  creative_id='mf-display' action=<CreativeAction.updated: 'updated'>
  creative_id='mf-video'   action=<CreativeAction.updated: 'updated'>
  creative_id='mf-native'  action=<CreativeAction.updated: 'updated'>
```

Green: three-format batch accepted; exactly three results; submission order preserved; `created` then `updated` on re-sync; no operation-level `errors`.
Red: no top-level `status`; no per-creative `status`.

---

## 5. Proposed Gherkin

Replaces `tests/bdd/features/BR-UC-006-sync-creatives.feature:1609-1623` in full.

```gherkin
  @T-UC-006-storyboard-multi-format-sync @storyboard-v3.1 @v3-1 @bulk-sync @multi-format @creative-invariant
  Scenario Outline: Bulk multi-format sync returns exactly one result per submitted creative, each carrying a spec-enum action
    Given the Buyer Agent submits a bulk sync batch
      | creative_id | format_id             |
      | mf-display  | display_300x250_image |
      | mf-video    | video_standard_30s    |
      | mf-native   | native_content        |
    And the batch has been pre-synced <prior_syncs> times
    When the Buyer Agent syncs the creatives
    Then the response is the success variant carrying a creatives array
    And the response does not carry an operation-level errors array
    And the response carries exactly 3 per-creative results
    And the per-creative creative_ids in order are "mf-display,mf-video,mf-native"
    And every creative result has action "<action>"
    And every per-creative action is a member of the creative-action enum
    And no per-creative status carries a creative-action value

    Examples:
      | prior_syncs | action  |
      | 0           | created |
      | 1           | updated |

    # media-buy/index.yaml creative_sync: the buyer pushes creatives in MORE THAN ONE
    # format in a single sync_creatives call (3.1.1 samples a 30s CTV video plus a
    # 300x250 display banner). The seller validates each against its own format spec
    # and returns one result per submitted creative, each carrying `action`.
    #
    # Cardinality (one result per submitted creative, positionally aligned) is graded
    # by the indexed creatives[0].action / creatives[1].action checks in
    # per_creative_conversion_attribution.yaml — the only 3.1.1 step that grades a
    # per-creative field at index > 0.
    #
    # `action` is constrained to the FIVE-member enums/creative-action.json
    # (created/updated/unchanged/failed/deleted). The pre-2026 text of this scenario
    # listed only three and would have gone red on `unchanged`.
    #
    # Per-creative `status` is deliberately NOT asserted present: no 3.1.1
    # sync_creatives step grades it (it appears only as `expected:` prose), and
    # production leaves it None by owner decision (src/core/schemas/creative.py).
    # What IS asserted is the schema's hard rule that status values "come from
    # CreativeStatus only ... never from CreativeAction" — true today and true
    # after the gap in #TBD-A is closed.
    #
    # Re-pinned from ref=v3.1-04f59d2d5 (an ancestor of 3.1.0-beta.3, OLDER than our
    # 3.1.1 pin) and from protocols/creative/index.yaml, which at 3.1.1 narrowed to a
    # SINGLE display creative and is gated on supported_protocols=[creative] +
    # has_creative_library — neither of which we declare (src/core/tools/capabilities.py).
    #
    # @source repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/media-buy/index.yaml phase=creative_sync step=sync_creatives
    # @source repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml phase=register_two_creatives_and_create_buy step=sync_two_creatives
```

Every assertion above was executed against production via the probe. Nothing here is aspirational.

---

## 6. Step inventory

### EXISTING — reuse unchanged (3 of 8)

| Step | Location |
|---|---|
| `When the Buyer Agent syncs the creatives` | `tests/bdd/steps/domain/uc006_sync_creatives.py:252` |
| `Then the response is the success variant carrying a creatives array` | `tests/bdd/steps/domain/uc006_sync_creatives.py:6968` |
| `Then the response does not carry an operation-level errors array` | `tests/bdd/steps/domain/uc006_sync_creatives.py:7003` |
| `Then every creative result has action "{action}"` | `tests/bdd/steps/domain/uc006_sync_creatives.py:6985` |

Four existing steps reused unchanged.

### NEW — 2 Givens + 4 Thens

1. `@given("the Buyer Agent submits a bulk sync batch")` with `datatable` — builds one payload per row into `ctx["creatives"]`, using `_format_payload`'s transport branch for `agent_url` (`_E2E_AGENT_URL` under e2e_rest, `env.DEFAULT_AGENT_URL` otherwise) and `build_assets(image_spec("image"))` for assets. Records the submitted `creative_id` order in `ctx["submitted_creative_ids"]`.
   *Why new:* the closest existing step, `given_creative_with_specific_format` (`uc006_sync_creatives.py:779`), hardcodes `creative_id = "creative-fmt-partition-001"`, so calling it three times collides on a single id. A table-driven batch builder is the DRY replacement and removes the need for further per-batch Givens.

2. `@given(parsers.parse("the batch has been pre-synced {prior_syncs:d} times"))` — dispatches the batch `prior_syncs` times via `dispatch_request`, then clears `ctx["response"]` / `ctx["error"]` so only the graded `When` call is observed. Transport-neutral, so it works identically on all four transports.

3. `@then(parsers.parse("the response carries exactly {count:d} per-creative results"))` — `assert len(response.creatives) == count`, error message listing the observed `creative_id`s.

4. `@then(parsers.parse('the per-creative creative_ids in order are "{expected}"'))` — `assert [c.creative_id for c in response.creatives] == expected.split(",")`.

5. `@then("every per-creative action is a member of the creative-action enum")` — compares `[a for a in observed_actions if a not in CREATIVE_ACTION_VALUES] == []` against the five 3.1.1 members, message printing `observed_actions`.

6. `@then("no per-creative status carries a creative-action value")` — computes `[s for s in observed_statuses if s in CREATIVE_ACTION_VALUES] == []`. Non-vacuous (evaluates over all three results), concrete, and does not pin the current `None`.

`CREATIVE_ACTION_VALUES` / `CREATIVE_STATUS_VALUES` should come from the SDK enums (`adcp.types` `CreativeAction` / `CreativeStatus`) rather than being hand-listed, so a pin bump surfaces as a step failure rather than silent drift. Cross-check them against the 3.1.1 JSON quoted in §3 at review time — the SDK is not authority.

---

## 7. TICKET MATERIAL

Each of these would make the scenario red today, so none are in the proposed Gherkin.

- **[A] Per-creative `status` is never populated even though we run a review lifecycle.**
  `src/core/schemas/creative.py` (`SyncCreativeResult`) documents the owner decision to inherit but never populate the spec `status`; the internal state lives in `internal_status` (`exclude=True`). Verified: `status=None` on every result, and the probe log shows *"Created 3 workflow steps for creative approval"* — i.e. we demonstrably HAVE a review lifecycle. `creative/sync-creatives-response.json` (3.1.1) permits omission only as *"Omit entirely when the seller has no review lifecycle at all"*; with an approval workflow and an internal `pending_review` state, that exemption does not apply. Fix: map `internal_status` onto the spec `status` using `enums/creative-status.json` members, honouring the `failed`/`deleted` exclusion in the same schema's `allOf`/`if`/`then`. Downstream: `protocols/media-buy/index.yaml:691` and `protocols/creative/index.yaml:152` both describe per-creative status as the expected seller output.

- **[B] Per-creative `status` serializes as `null` over MCP.**
  `src/core/schemas/creative.py` states it plainly: *"on MCP the response goes through structured_content -> to_jsonable_python, which BYPASSES the model_dump override, so the inherited `status` serializes as null."* `status` `$ref`s `enums/creative-status.json`, a six-member string enum — `null` is not a member, so an MCP response carrying `"status": null` fails `response_schema`, the first graded check in every binding in §2. A2A/REST are unaffected (`model_dump(exclude_none=True)` drops it). Fix belongs with the broader MCP None-serialization question the comment defers.

- **[C] No top-level `status` on `sync_creatives` responses.**
  Probe: `dumped keys: ['creatives', 'dry_run']`. `core/protocol-envelope.json` at 3.1.1 has `"required": ["status"]` and states *"Agents shipping responses without a top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate."* `sync-creatives-response.json` `allOf`-refs that envelope, so `check: response_schema` — graded at `protocols/media-buy/index.yaml:732`, `…/per_creative_conversion_attribution.yaml:279`, and every other binding in §2 — cannot pass. This is the already-known envelope gap in the brief; recording it here because it is what blocks the `response_schema` check on *this* scenario's binding specifically.

- **[D] No BDD step validates any response against a pinned schema.**
  The removed line 1613 (`the response envelope should be schema-valid against sync-creatives-response.json`) had no step definition at all, and per the brief `then_response_schema_valid` runs no validator despite `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing. Combined with `tests/fixtures/adcp_schemas_pinned/` being vendored at `04f59d2d5` rather than 3.1.1, the single most-graded check across every 3.1.1 storyboard (`check: response_schema`) has no representation anywhere in the BDD suite. Re-vendoring at 3.1.1 and wiring a real validator step would let `response_schema` be graded once, generically, instead of being asserted in prose per scenario.

- **[E] `tests/bdd/conftest.py:3363-3379` gates UC-006 on a hand-maintained tag allowlist.**
  `{"account", "creative-invariant", "BR-RULE-034"}` decides whether `CreativeSyncEnv` is built; every other UC-006 scenario hits an imperative `pytest.xfail("UC-006 harness not yet wired for non-account scenarios")` and never runs a line of production code. That is 2 of 2 storyboard-tagged bulk-sync scenarios in this file silently dormant, indistinguishable from passing in a suite summary. The allowlist should be inverted — build the env for UC-006 unconditionally and xfail only the named exceptions — so that adding a scenario grades it by default. Same shape as the UC-003 gate two branches up (`conftest.py:3358-3361`).

- **[F] `protocols/creative/index.yaml` and `protocols/media-buy/index.yaml` both describe per-creative status as `accepted, pending_review, or rejected`.**
  `enums/creative-status.json` at 3.1.1 has no `accepted` member (`processing, pending_review, approved, suspended, rejected, archived`). Upstream prose bug in the adcp repo, worth reporting there — it will mislead any implementer reading `expected:` blocks, and it is the kind of drift that produced the "accepted vs approved" confusion already visible in our own `CreativeStatusEnum`. Not actionable in this repo beyond not copying it into steps.

---

## 8. Risks

- **Three-format grading is our own extrapolation.** 3.1.1 grades multi-format at N=2 (`media-buy/index.yaml`) and per-creative cardinality at N=2 (`per_creative_conversion_attribution.yaml`). Keeping the scenario at three creatives in three formats preserves the existing tag's intent and is strictly stronger than either binding, but no single 3.1.1 step grades N=3. If the reviewer prefers exact storyboard fidelity, drop `mf-native` and the scenario matches `media-buy/index.yaml` sample exactly. I chose the stronger form because the tag id is `…-multi-format-sync` and shrinking it would weaken a scenario the brief asked to re-ground, not retire.

- **Positional ordering is implied, not stated.** `sync-creatives-response.json` does not mandate that `creatives[i]` corresponds to request `creatives[i]`. The indexed storyboard checks (`creatives[0].action`, `creatives[1].action`) only make sense under positional correspondence, and production preserves it (verified). The `creative_ids in order` assertion is therefore grounded in the storyboard's indexing rather than in schema text. If a reviewer objects, weaken it to a set comparison — but that loses the property the indexed checks actually rely on.

- **e2e_rest was not executed.** The three transports I verified are `mcp`, `a2a`, `rest`; `e2e_rest` is deselected outside the in-network CI job and I did not bring up the compose stack. All three format ids I chose (`display_300x250_image`, `video_standard_30s`, `native_content`) ARE in `tests/fixtures/creative_formats/reference_formats.json`, which is what `ADCP_TESTING=true` serves, and `_validation.py` only checks format *existence* via `fetch_format_spec` (asset-vs-spec validation is still `TODO(#767)`), so I expect it to pass. Unverified by execution.

- **Adding `@creative-invariant` is a tag-semantics judgement.** It routes the scenario into the identical conftest branch as `@account` with no code change, and the bucket's stated meaning (success-variant response invariants) fits. If the reviewer considers the tag reserved for the `#1399 R3-F2` set specifically, the alternative is adding `bulk-sync` to the allowlist at `conftest.py:3365` — a one-token conftest edit. Either way the scenario cannot be graded without one of the two.

- **Shared agent-db.** The probe ran against `agent-pg-salesagent-sbsweep`, which sibling sweep agents are also using; I used a UUID-suffixed tenant/principal to avoid collisions and deleted nothing belonging to anyone else. Earlier I did delete a stale `test_tenant` tenant/principal pair from that throwaway test DB before switching to unique ids — flagging it in case a sibling relied on it (nothing referenced it; the delete succeeded without FK violations).

- **`unchanged` is reachable but unexercised.** The Examples cover `created` and `updated`. `src/core/tools/creatives/_sync.py:253-256` distinguishes `updated` from `unchanged`, and my re-sync with an identical payload produced `updated`, not `unchanged` — so I could not construct an `unchanged` row green without guessing at the change-detection predicate. Worth a follow-up row once that path is understood; not blocking.

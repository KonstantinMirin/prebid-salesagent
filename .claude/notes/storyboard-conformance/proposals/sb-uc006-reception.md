# Re-pin: `@T-UC-006-storyboard-creative-reception-stateful-render`

Scenario: "Stateful sales agent accepts pushed creatives and exposes them via per-creative status transitions"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-006-sync-creatives.feature:1639-1652` (last scenario in the file; **no `@source` footer**)

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** Two independent reasons, either one sufficient:

1. **The gate is undeclared.** The storyboard binds to an agent profile we do not declare:
   `interaction_model: stateful_push` + `capabilities: [has_creative_library]`
   (`dist/compliance/3.1.1/protocols/media-buy/scenarios/creative_reception.yaml:22-25`).
   `has_creative_library` resolves to the capability path `creative.has_creative_library`
   (the runner form of the same gate is visible at `protocols/media-buy/state-machine.yaml:99-102`:
   `requires_capability: {path: creative.has_creative_library, equals: true}`). The 3.1.1 schema says
   the whole `creative` capability block is *"Only present if creative is in supported_protocols"*.
   `src/core/tools/capabilities.py:270-271` declares `supported_protocols=[SupportedProtocol.media_buy]`
   and `specialisms=[AdcpSpecialism.sales_non_guaranteed]` — no `creative` protocol, no `creative` block,
   so `creative.has_creative_library` is absent. The storyboard's own first phase makes this explicit:
   its `get_capabilities` step expects *"Return capabilities declaring creative in supported_protocols"*
   (`creative_reception.yaml:59-60`).

2. **Declaring `media_buy` does not pull it in.** `protocols/media-buy/index.yaml:10-24` lists 14
   `requires_scenarios`; `media_buy_seller/creative_reception` is **not among them**. Nor is it bundled
   under any specialism — grepping all of `dist/compliance/3.1.1/` for `creative_reception` returns only
   the two copies of the scenario file itself. It is an optional, capability-gated storyboard that ships
   *inside* the media-buy protocol directory but is not part of the media-buy baseline.

**Secondary finding — the specific behaviour is prose-only anyway.** Even for an agent that *did* declare
the gate, the thing this scenario asserts (per-creative `status` transitions, platform-assigned IDs) is
**not graded**. The `sync_creatives` step grades four things and `status` is not one of them; `status`
appears only under `expected:` narrative prose. So the `@storyboard-v3.1` tag is unjustified on both axes.

**Action:** `@storyboard-v3.1` → `@schema-v3.1`. Keep `@T-UC-006-storyboard-creative-reception-stateful-render`
unchanged (referenced from `docs/test-obligations/bdd-traceability.yaml`).

**Tier:** `protocols/` — `static/compliance/source/protocols/media-buy/scenarios/creative_reception.yaml`
is the single source file at v3.1.1 (`git ls-tree -r --name-only v3.1.1 | grep creative_reception`).
`dist/compliance/3.1.1/domains/media-buy/scenarios/creative_reception.yaml` is a byte-identical generated
mirror (`diff` → identical); cite the `protocols/` path.

---

## 2. Real binding at 3.1.1

### What the current footer points at

**Nothing — this scenario has no `@source` footer at all.** It is one of the 11 the brief flags.

The off-by-one is still visible and provable here: the *preceding* scenario,
`@T-UC-006-storyboard-format-id-roundtrip-on-sync` (feature line 1636), cites
`path=static/compliance/source/protocols/media-buy/scenarios/creative_reception.yaml` — i.e. it has
stolen **this** scenario's storyboard while its own prose talks about `media-buy/index.yaml creative_sync`.
Fixing this scenario's footer therefore also confirms the neighbour is mis-pinned (not my scenario to edit).

### The real binding

`repo=adcp ref=v3.1.1 commit=467fd93d7`
`path=static/compliance/source/protocols/media-buy/scenarios/creative_reception.yaml`
`phase=push_creatives step=sync_creatives`

Dist copy for reading: `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/creative_reception.yaml`

The graded block, **verbatim**, `creative_reception.yaml:163-176`:

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
            value: "media_buy_seller_creative_reception--sync_creatives"
            description: "Context correlation_id returned unchanged"
```

That is the **entire** graded surface of the step. Everything the scenario currently asserts lives in the
ungraded `expected:` prose immediately above it (`creative_reception.yaml:129-134`):

```yaml
        expected: |
          Accept the creatives, validate against format specifications, and return:
          - Per-creative action (created or updated)
          - Per-creative status (accepted, pending_review, rejected)
          - Platform-assigned IDs if applicable
          - Validation errors for rejected creatives
```

Note also `stateful: true` (`creative_reception.yaml:128`) — the only formal expression of the
"stateful" claim in the scenario title.

**Storyboard drift, for the record:** the only change to this storyboard between the old pin `04f59d2d5`
and `v3.1.1` is one added line, `requires_tool: preview_creative` on the `preview_synced` step. The
`interaction_model: stateful_push` was **already** `stateful_push` at `04f59d2d5` — the brief's note that
3.1.1 changed it from `stateful_preloaded` does **not** apply to this storyboard. The scenario's existing
`@stateful-push` tag is correct and needs no change.

---

## 3. Schema constraints at 3.1.1

All quotes from `git show v3.1.1:static/schemas/source/...`.

### `creative/sync-creatives-response.json` — per-creative item

```json
"required": [
  "creative_id",
  "action"
],
"additionalProperties": true,
"allOf": [
  {
    "if": {
      "properties": { "action": { "enum": ["failed", "deleted"] } },
      "required": ["action"]
    },
    "then": { "not": { "required": ["status"] } }
  }
]
```

`status` is **optional**, and **forbidden** when `action` is `failed` or `deleted`. Its description is
normative about the value space:

> "Values come from CreativeStatus only (processing, pending_review, approved, suspended, rejected,
> archived) — never from CreativeAction. […] MUST be omitted when action is failed or deleted […]
> **Omit entirely when the seller has no review lifecycle at all.**"

The success branch:

```json
"required": ["creatives"],
"not": { "anyOf": [
  { "required": ["errors"] },
  { "required": ["task_id"] },
  { "properties": { "status": { "const": "submitted" } }, "required": ["status"] }
] }
```

### `enums/creative-action.json`

```json
"enum": ["created", "updated", "unchanged", "failed", "deleted"]
```

### `enums/creative-status.json`

```json
"enum": ["processing", "pending_review", "approved", "suspended", "rejected", "archived"]
```

### `core/protocol-envelope.json` (pulled in via `allOf` by sync-creatives-response.json)

```json
"required": ["status"]
```

> "The `status` field is REQUIRED on every task response envelope […] Agents shipping responses without
> a top-level `status` are non-conformant regardless of whether the task body schema would otherwise
> validate."

### `protocol/get-adcp-capabilities-response.json` — the gate

`supported_protocols.items.enum` = `["media_buy","signals","governance","sponsored_intelligence","creative","brand","measurement"]`,
and:

> "Stable values both (a) declare which tools the agent implements and (b) **commit the agent to pass the
> baseline compliance storyboard at /compliance/{version}/protocols/{protocol}/**"

`properties.creative`: *"Creative protocol capabilities. Only present if creative is in supported_protocols."*
`properties.creative.has_creative_library`: *"When true, this agent hosts a creative library and supports
list_creatives and creative_id references in build_creative."* `"default": false`.

---

## 4. Conflicts

**Schema overrides storyboard (say it explicitly).** The storyboard's `expected:` prose names the
per-creative status values as **`(accepted, pending_review, rejected)`**. `accepted` is **not a member of
`enums/creative-status.json`** at 3.1.1. The schema wins: the legal set is
`processing | pending_review | approved | suspended | rejected | archived`. Any scenario that transcribes
the storyboard's prose list is transcribing a bug.

**What the current scenario gets wrong:**

| Current line | Problem |
|---|---|
| `Then the seller should validate the creatives against its format specifications` | Untestable as written — no value compared. Violates `test_architecture_bdd_no_trivial_assertions.py`. |
| `And the per-creative result should carry a status drawn from creative-status enum` | **RED against production.** Production deliberately never populates the wire `status` — `src/core/schemas/creative.py:373-377`: *"Per owner decision we inherit but do NOT populate the spec `status`: it stays None."* Also over-states the spec, which makes `status` optional and tells sellers with no review lifecycle to omit it. |
| `And the per-creative status may be "approved", "pending_review", or "rejected"` | "may be" asserts nothing. Also drops `processing`/`suspended`/`archived` from the enum and inherits the storyboard's `accepted` confusion by proxy. |
| `And platform-assigned IDs should be returned when applicable` | "when applicable" is unfalsifiable, and production never sets `platform_id` (no assignment anywhere in `src/core/tools/creatives/`). |
| tag `@storyboard-v3.1` | Unjustified — see VERDICT. |
| no `@source` footer | Must be added. |

**What it misses.** The one thing the storyboard actually grades on this step —
`field_present: creatives[0].action` — is not asserted at all. Nor is the success-variant `oneOf`
discrimination, nor the per-item `creative_id` echo that the schema makes `required`.

**Vacuity.** All four `Then` steps are currently undefined in `tests/bdd/steps/`, so the scenario is
**dormant**: `tests/bdd/conftest.py:82-101` converts `StepDefinitionNotFoundError` to xfail. It has never
executed. Nothing in it has ever been verified.

---

## 5. Proposed Gherkin

Replaces feature lines 1639-1652 in full. Every step is either already defined and green, or (2 new)
asserts a value I verified by reading production. GREEN ONLY — no `status`, no `platform_id`, no
top-level envelope `status`, no `context` echo (all four are production gaps, filed in §7).

```gherkin
  @T-UC-006-storyboard-creative-reception-stateful-render @schema-v3.1 @v3-1 @stateful-push @creative-reception
  Scenario Outline: Stateful reception persists each pushed creative and returns a spec-shaped per-creative result — <partition>
    Given the Buyer is authenticated as principal "<principal>"
    And creative "<creative_id>" <existence>
    When the Buyer Agent syncs the creative
    Then the response is the success variant carrying a creatives array
    And the response does not carry an operation-level errors array
    And the action should be "<action>"
    And the per-creative results should carry exactly the submitted creative_ids
    And every per-creative action should be a member of the creative-action enum
    # Reception is stateful in one observable way we can prove: the library is keyed by
    # (tenant, principal, creative_id) ACROSS calls. A re-push of the same creative_id by the
    # same principal resolves to the persisted row and reports "updated"; a different principal
    # never sees it and gets a fresh "created". That is the minimum-viable reception contract.
    #
    # NOT asserted here, deliberately — 3.1.1 sync-creatives-response.json makes per-creative
    # `status` OPTIONAL ("Omit entirely when the seller has no review lifecycle at all") and
    # FORBIDS it when action is failed/deleted. This agent does not populate it (see #NNNN).
    # `platform_id` is likewise never assigned (#NNNN). The storyboard mentions both only under
    # `expected:` prose, which is ungraded; and its prose value `accepted` is not even a member
    # of enums/creative-status.json at 3.1.1 — the schema wins.
    #
    # Tag is @schema-v3.1, not @storyboard-v3.1: this storyboard is gated on
    # `creative.has_creative_library` + `creative` in supported_protocols, and
    # src/core/tools/capabilities.py declares neither. It is also absent from
    # protocols/media-buy/index.yaml `requires_scenarios`, so declaring media_buy does not
    # commit us to it. Not on our conformance path — graded here against the JSON schema only.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/creative_reception.yaml phase=push_creatives step=sync_creatives

    Examples: Reception outcomes
      | partition       | principal | creative_id | existence                         | action  |
      | first_push      | buyer-A   | c-1         | does not exist for this principal | created |
      | repush_same_id  | buyer-A   | c-1         | exists for principal buyer-A      | updated |
      | cross_principal | buyer-B   | c-1         | exists for principal buyer-A only | created |
```

The `Examples` table is lifted from the already-green `@T-UC-006-partition-creative-scope` outline
(feature lines 768-779), so the three rows are proven to produce those actions on current production;
this scenario adds the schema-shape assertions that outline does not make.

---

## 6. Step inventory

### Existing — reused as-is (all currently defined and exercised)

| Step | Defined at |
|---|---|
| `Given the Buyer is authenticated as principal "<principal>"` | `tests/bdd/steps/generic/given_auth.py` (used by feature:769) |
| `Given creative "{creative_id}" does not exist for this principal` | `tests/bdd/steps/domain/uc006_sync_creatives.py:6700` |
| `Given creative "{creative_id}" exists for principal {principal_id}` / `… only` | `uc006_sync_creatives.py:6710-6711` |
| `When the Buyer Agent syncs the creative` | `uc006_sync_creatives.py:253` (dispatches all 4 transports via `dispatch_request`) |
| `Then the response is the success variant carrying a creatives array` | `uc006_sync_creatives.py:6966` |
| `Then the response does not carry an operation-level errors array` | `uc006_sync_creatives.py:6993` |
| `Then the action should be "{expected_action}"` | `uc006_sync_creatives.py:6743` |

### New — 2 steps

1. **`Then the per-creative results should carry exactly the submitted creative_ids`**
   Compare `{r.creative_id for r in response.creatives}` against the set of `creative_id`s in
   `ctx["creatives"]`. Green: every construction site echoes the submitted id —
   `_sync.py:198`, `_sync.py:208`, `_processing.py:50`, `_processing.py:459`, `_processing.py:805`.
   (The one path that does not is the `delete_missing` sweep at `_sync.py:383`, which uses the DB id;
   none of the three rows sets `delete_missing`, so the set equality holds.)
   Grounded in `sync-creatives-response.json` per-item `required: ["creative_id", "action"]`.

2. **`Then every per-creative action should be a member of the creative-action enum`**
   Compare each normalised action string against the literal set
   `{"created","updated","unchanged","failed","deleted"}` from `enums/creative-action.json`.
   Green: `SyncCreativeResult.action` is inherited as the SDK `CreativeAction` StrEnum
   (`src/core/schemas/creative.py:365-367`) and every emitting site passes a member —
   `created`/`updated`/`deleted` as enum members, `unchanged` at `_processing.py:455`,
   `failed` at `_processing.py:51`.
   Use the existing `_get_action_str()` helper (`uc006_sync_creatives.py:6735`) — do not re-implement
   the enum/str normalisation (DRY; `test_architecture_bdd_no_duplicate_steps.py`).

Both are set/enum comparisons over concrete values, so they clear
`test_architecture_bdd_no_trivial_assertions.py` and `..._no_pass_steps.py`.

### Retired (no replacement — the behaviour is a production gap, not a test gap)

`the seller should validate the creatives against its format specifications`,
`the per-creative result should carry a status drawn from creative-status enum`,
`the per-creative status may be …`, `platform-assigned IDs should be returned when applicable`.
None was ever defined; nothing is lost.

---

## 7. TICKET MATERIAL

1. **Per-creative `status` is never emitted on the sync_creatives wire.**
   `src/core/schemas/creative.py:373-377` — *"Per owner decision we inherit but do NOT populate the spec
   `status`: it stays None."* No write site exists; `internal_status` (`creative.py:394-396`,
   `exclude=True`) holds the review state instead and never reaches the wire.
   3.1.1 `creative/sync-creatives-response.json` makes `status` optional, so **omitting is conformant** —
   this is a product decision to record, not a violation. File it as the decision record so the next
   reader does not re-derive it, and so it is revisited if we ever declare `creative.has_creative_library`.

2. **MCP emits `status: null` on every per-creative result — schema-invalid, and a hard violation when
   `action` is `failed`/`deleted`.**
   Per `src/core/schemas/creative.py:374-377`, the MCP path goes through
   `structured_content → to_jsonable_python`, which **bypasses** the `model_dump` override (and thus
   `exclude_none`), so the inherited `status` serializes as JSON `null`. `null` is not a member of
   `enums/creative-status.json` (`type: "string"`), and the key being *present* also trips
   `sync-creatives-response.json`'s conditional
   `if action ∈ {failed, deleted} then not required: ["status"]`. A2A/REST are unaffected
   (`exclude_none=True` at `creative.py:414-415`). Fix: omit `status` on the MCP structured-content path.

3. **Local `CreativeStatusEnum` is missing two 3.1.1 members.**
   `src/core/schemas/creative.py:123-129` defines `{processing, approved, rejected, pending_review}`.
   `enums/creative-status.json` at 3.1.1 is
   `{processing, pending_review, approved, suspended, rejected, archived}` — `suspended` and `archived`
   are absent. `archived` is written as a bare string at `_sync.py:377-379`, bypassing the enum entirely.
   The enum is also declared *"not in adcp library, local definition"* although
   `adcp.types.CreativeStatus` is imported at `creative.py:13`. Fix: drop the local enum, use the SDK type.

4. **`platform_id` is never assigned.**
   No write site anywhere in `src/core/tools/creatives/`. Spec-optional, so not a violation — but the
   storyboard's `expected:` prose lists "Platform-assigned IDs if applicable", so any future
   `creative.has_creative_library` declaration should populate it from the adapter's returned id.

5. **`@T-UC-006-storyboard-format-id-roundtrip-on-sync` (feature:1636) is mis-pinned onto this
   scenario's storyboard.**
   Its footer reads `path=…/protocols/media-buy/scenarios/creative_reception.yaml` while its prose says
   `media-buy/index.yaml creative_sync`. Textbook off-by-one. Owner of that scenario should re-pin;
   flagged here because the two collide on the same file.

6. **(Cited, already known — not re-filed)** No top-level envelope `status`; 3.1.1
   `core/protocol-envelope.json` `required: ["status"]` is pulled in by `sync-creatives-response.json`'s
   `allOf`, so **every** sync_creatives response is currently non-conformant. Also: REST drops `context`,
   which is one of the two things this storyboard step actually grades
   (`field_present: context`, `field_value: context.correlation_id`) — meaning that even if we declared
   the gate, we would fail 2 of the 4 graded checks on REST. `then_response_schema_valid` runs no
   validator, which is why none of this is caught.

---

## 8. Risks

- **Not executed.** I did not run the BDD suite; no Docker/DB was started for this analysis. Every
  green/red claim is from reading `src/` and the existing step definitions. The three `Examples` rows are
  copied verbatim from an outline already in the feature file (768-779) specifically to minimise this risk,
  but I have not confirmed that outline is green on **all four** transports today — only that it is wired
  and not in any xfail ledger.
- **`the Buyer is authenticated as principal "<principal>"`** — I located its use at feature:769 but not
  its definition (it lives in `generic/given_auth.py`, which I did not read line-by-line). If the
  phrasing there differs, copy it exactly from feature:769.
- **New step 1 and `delete_missing`.** The set-equality assertion is only sound because none of the three
  rows enables `delete_missing`. If a future row does, the swept `deleted` results carry DB ids that were
  never submitted and the step will legitimately fail. Worth a comment in the step docstring.
- **Which tier to cite.** `protocols/` and `domains/` copies are byte-identical and only `protocols/`
  exists in the v3.1.1 source tree, so I cite `protocols/`. If the sweep's convention is otherwise,
  it is a one-word change.
- **Drift, noted not acted on.** I read only `v3.1.1`. I did not check 3.1.8/HEAD; the wire `status`
  semantics on sync responses are exactly the kind of thing that moves, and finding #1 should be
  re-checked at the next pin bump.
- **`unchanged` has no row.** Production emits it (`_processing.py:455`) but the existing
  `creative "{id}" exists for principal "{p}"` given pre-seeds *different* data, so it yields `updated`.
  Adding an `unchanged` row would need a new pre-seed given; left out to stay green.

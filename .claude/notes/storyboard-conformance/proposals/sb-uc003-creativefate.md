# Re-pin: `@T-UC-003-storyboard-creative-fate-after-cancellation`

Scenario: `tests/bdd/features/BR-UC-003-update-media-buy.feature:2094`
Title today: *"Canceling a media buy releases package-creative assignments but leaves creatives in the library with review state intact"*

---

## 1. VERDICT

**GRADED** — the `@storyboard-v3.1` tag is justified, but only for **half** of what the scenario title claims.

- The behaviour is graded at 3.1.1 by `media_buy_seller/creative_fate_after_cancellation`, which lives in the **`protocols/media-buy/` and `domains/media-buy/` baseline tiers** (byte-identical copies), is listed under `requires_scenarios:` of the `media_buy_seller` index, and is gated by the **`media_buy` protocol — which we DO declare** (`src/core/tools/capabilities.py:99` `supported_protocols=[SupportedProtocol.media_buy]`). It is **not** specialism-gated, so the "undeclared gate" downgrade to `@schema-v3.1` does **not** apply.
- **The "releases package-creative assignments" half of the title is NOT graded.** The `cancel_buy` phase carries exactly one validation — `check: response_schema`. Assignment release appears only in that phase's `narrative:` prose. The scenario title therefore promises a grade that the storyboard does not issue.
- Only the **persistence** half is graded, by phase `verify_creative_persists_post_cancel` → step `list_creatives_after_cancel`.

Two caveats, both recorded honestly rather than used to downgrade the verdict:

1. **Capability-disclosure ambiguity.** The 3.1.1 prose scopes the library-persistence obligation to sellers advertising `creative.has_creative_library: true`; we advertise `media_buy.inline_creative_management: true` and never emit `has_creative_library` (zero hits in `src/`). The storyboard's own `prerequisites.description` says sellers *without* a creative library grade this `not_applicable`. We **have** a real library (`CreativeRepository`, `list_creatives`, `sync_creatives` — the storyboard's `required_tools`) and simply fail to advertise it. I read that as a disclosure defect (ticket below), not grounds for `@schema-v3.1`. Flagged in Risks — a reviewer could reasonably read it the other way.
2. **The scenario is DORMANT and cannot currently be graded by us at all** — see §4.

---

## 2. Real binding at 3.1.1

### What the footer points at today

**Nothing.** This scenario has **no `@source` footer at all**. The checked-in sweep agrees:

```
| `T-UC-003-storyboard-creative-fate-after-cancellation` | BR-UC-003-update-media-buy.feature:2094 | **C** | NO @source footer — binding is unverifiable |
```

The off-by-one defect is visible here in mirror image: the **preceding** scenario, `@T-UC-003-storyboard-not-cancellable-on-recancel` (tag line 2077), whose prose says *"invalid_transitions Phase 4 (double_cancel)"*, carries the footer

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml
```

i.e. it cites **my** scenario's storyboard, and mine got nothing. Classic shift-by-one: `invalid_transitions` → cites `creative_fate_after_cancellation` → cites nothing.

### The real file

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml`
(byte-identical to `domains/media-buy/scenarios/creative_fate_after_cancellation.yaml` — `diff` returns empty; and identical to the authoring source `static/compliance/source/protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml` at `v3.1.1`, so citing the `static/…/source/` path is exact, not approximate.)

Storyboard id: `media_buy_seller/creative_fate_after_cancellation`, `version: "1.0.0"`, `track: media_buy`,
`required_tools: [get_products, create_media_buy, update_media_buy, sync_creatives, list_creatives]`.

### The graded block — verbatim

**Phase `verify_creative_persists_post_cancel`, step `list_creatives_after_cancel`** (lines 272–319; validations at **306–319**):

```yaml
        validations:
          - check: response_schema
            description: "Response matches list-creatives-response.json schema"
          - check: field_present
            path: "creatives[0].creative_id"
            description: "Creative still in the library after buy cancellation"
          - check: field_value
            path: "creatives[0].creative_id"
            value: "acme_reuse_banner_001"
            description: "Creative ID is unchanged (not re-keyed on cancel)"
          - check: field_value
            path: "creatives[0].status"
            allowed_values: ["processing", "pending_review", "approved"]
            description: "Creative status is NOT rejected and NOT archived — no implicit review cascade from the buy cancel"
```

**Baseline phase `verify_creative_in_library_pre_cancel`, step `list_creatives_before_cancel`** (validations at **227–236**):

```yaml
        validations:
          - check: response_schema
            description: "Response matches list-creatives-response.json schema"
          - check: field_present
            path: "creatives[0].creative_id"
            description: "Creative is present in the library"
          - check: field_value
            path: "creatives[0].status"
            allowed_values: ["processing", "pending_review", "approved"]
            description: "Creative status is non-terminal (not rejected or archived) before cancel"
```

**Phase `cancel_buy`, step `update_media_buy_canceled`** (validations at **268–270**) — the *entire* graded content of the cancel:

```yaml
        validations:
          - check: response_schema
            description: "Response matches update-media-buy-response.json schema"
```

**Phase `reuse_creative_on_new_buy`, step `reassign_creative`** (validations at **417–419**):

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-creatives-response.json schema"
```

So: **release of assignments — ungraded prose. Reuse-by-creative_id — graded only as "the sync response is schema-valid". Library persistence + id stability + non-cascading status — genuinely graded.**

### Supporting normative prose at 3.1.1 (not graded, but it is the rule the storyboard encodes)

- `dist/docs/3.1.1/creative/creative-libraries.mdx:36` — *"Rejecting, canceling, or completing a media buy releases its assignments. It does not change the creative's review state, remove the creative from the library, or affect the creative's use in other media buys."*
- `dist/docs/3.1.1/media-buy/media-buys/index.mdx:317` — *"A media buy reaching `rejected`, `canceled`, or `completed` releases its creative assignments but does not modify the creatives themselves."*
- `dist/docs/3.1.1/media-buy/specification.mdx:158` — the `creative.has_creative_library: true` gate quoted in §1.

### Tier and gate

| Question | Answer |
|---|---|
| Tier | `protocols/media-buy/` **and** `domains/media-buy/` — baseline, **not** `specialisms/` |
| Gate | `media_buy` protocol |
| Do we declare it? | **Yes** — `capabilities.py:99` |
| `agent.capabilities` in the storyboard | `sells_media` — an interaction-model descriptor, **not** a value in `enums/specialism.json`; nothing to declare |
| Sweep verdict with the proposed footer | **bucket A**, `tier: protocols`, `grading: graded`, `findings: []` (verified by executing `scripts/audit/storyboard_binding_sweep.py` against a patched copy of the feature file) |

---

## 3. Schema constraints at 3.1.1

All quotes via `cd /Users/konst/projects/adcp && git show v3.1.1:<path>`.

**`static/schemas/source/enums/creative-status.json`** — the full enum is wider than the storyboard's `allowed_values`:

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

`suspended` is new relative to our local `CreativeStatusEnum` (`src/core/schemas/creative.py:123-129` declares only `processing/approved/rejected/pending_review`). The wire-typed field is the library enum (`from adcp.types import CreativeStatus`, `creative.py:13,148`), which does carry all six — verified: `['processing','pending_review','approved','suspended','rejected','archived']`. The local `CreativeStatusEnum` is dead weight, not the wire contract.

**`static/schemas/source/creative/list-creatives-response.json`** — the response `allOf`-composes the envelope:

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
```

and types each creative's status by reference:

```json
          "status": {
            "$ref": "/schemas/enums/creative-status.json",
            "description": "Current approval status of the creative"
          },
```

**`static/schemas/source/core/protocol-envelope.json`** — `required: ["status"]`, with the description leaving no wiggle room:

> *"The `status` field is REQUIRED on every task response envelope, including synchronous metadata responses (e.g., `get_adcp_capabilities`) where the value is `completed`. Agents shipping responses without a top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate."*

This is the known top-level-`status` gap from the brief — my scenario inherits it via the `response_schema` check and must not re-file it.

**`static/schemas/source/core/creative-filters.json`** — the filter the storyboard actually sends:

```json
### creative_ids
{
 "type": "array",
 "description": "Filter by specific creative IDs",
 "items": { "type": "string" },
 "minItems": 1,
 "maxItems": 100
}
```

**`static/schemas/source/media-buy/update-media-buy-request.json`** — the cancel field:

```json
### canceled
{
 "type": "boolean",
 "description": "Cancel the entire media buy. Cancellation is irreversible — canceled media buys cannot be reactivated. Sellers MAY reject with NOT_CANCELLABLE if the media buy cannot be canceled in its current state.",
 "const": true
}
### cancellation_reason
{
 "type": "string",
 "description": "Reason for cancellation. Sellers SHOULD store this and return it in subsequent get_media_buys responses.",
 "maxLength": 500
}
required: ['idempotency_key', 'account', 'media_buy_id']
```

Note `"const": true` — `canceled: false` is schema-invalid. A cancel request is legally `{media_buy_id, account, idempotency_key, canceled: true}` and nothing else.

---

## 4. Conflicts, and what the scenario gets wrong

### Where the 3.1.1 schema overrode the storyboard

One place, and it is a **tightening, not a contradiction**: the storyboard's `allowed_values: ["processing","pending_review","approved"]` is a strict subset of `creative-status.json`'s six-value enum. The schema is authoritative for *what values may appear*; the storyboard is authoritative for *which of them pass this scenario*. Both hold simultaneously — a `suspended` creative post-cancel would be schema-valid and storyboard-failing. I keep the storyboard's narrower set in the Examples table and say so in a comment.

No case in this scenario where schema and storyboard actually disagree.

### What the scenario gets wrong

1. **No `@source` footer.** Bucket C. Unverifiable binding.
2. **The title over-promises.** "…releases package-creative assignments…" is graded nowhere; `cancel_buy` grades only `response_schema`.
3. **Every Then is vacuous or unmeasurable.** All four are prose assertions with no comparable value:
   - *"should still appear in the library"* — existence, not a value comparison.
   - *"review status should be unchanged from before the cancellation"* — no baseline is ever recorded, so "unchanged" has nothing to compare against.
   - *"should NOT be auto-flipped to status 'rejected'"* — a negative existence check.
   - *"should remain reusable by creative_id in a subsequent create_media_buy or sync_creatives"* — describes a second and third tool call the scenario never makes.
   These would be rejected by `test_architecture_bdd_no_trivial_assertions.py` if they were ever wired.
4. **It is DORMANT and cannot go red.** `pytest.xfail()` fires imperatively at the harness fixture before any step runs:

   ```
   XFAIL …test_canceling_a_media_buy_releases_packagecreative_assignments…[a2a]
     - UC-003 harness not yet wired for non-extension scenarios (full graduation pending, PR #1567 follow-up)
   ```
   (`tests/bdd/conftest.py:3357-3360`; verified by execution across all 3 transports.) An imperative `pytest.xfail()` can never xpass, so **nothing I write here can turn the suite red — and nothing I write can turn it green either.** The Gherkin below is correct-by-construction against production, but its correctness is **unverified by execution**. That is the single most important caveat in this document.
5. **It uses no `Scenario Outline`,** so it expresses one unparametrised anecdote where the graded invariant is "for every non-terminal review state".

### What production actually does (traced, with evidence)

- **`update_media_buy` has no cancellation at all.** `src/core/tools/media_buy_update.py` is 1673 lines and contains zero occurrences of `cancel` in any case. It handles `paused` (lines 154-156, 701-745) and nothing else lifecycle-wise. `_build_update_request` (line 1425) has no `canceled` parameter; the MCP wrapper (line 1521) and A2A raw function (line 1598) do not expose one.
- **A spec-shaped cancel is actively rejected.** `UpdateMediaBuyRequest.has_updatable_fields()` (`src/core/schemas/_base.py:2089-2102`) enumerates `paused, start_time, end_time, packages, budget, push_notification_config, reporting_webhook, context, ext` — **`canceled` is absent**. So `{media_buy_id, account, idempotency_key, canceled: true}` fails the `has_updatable_fields()` gate at `media_buy_update.py:1506` and raises `AdCPInvalidRequestError("Update request must include at least one updatable field (paused, start_time, …)")`.
- **Consequently nothing on the cancel path touches creatives** — because there is no cancel path. `CreativeAssignment` (`src/core/database/models.py:760-796`) is its own table keyed `(assignment_id)` with a plain FK to `media_buys.media_buy_id` and **no** `ondelete` cascade; `Creative` (`models.py:661-702`) cascades only to `CreativeReview` (line 693). Nothing deletes or rewrites either on a status flip.
- **Reuse-by-`creative_id` IS implemented** — this half of the storyboard needs no production work. `_process_assignments` (`src/core/tools/creatives/_assignments.py:98`) resolves the library row with `assignment_repo.get_creative_by_id(creative_id, principal_id)` and proceeds to assign whenever it is found, keyed on the composite `(creative_id, tenant_id, principal_id)` PK. Package resolution is independent (`:120` `find_package_with_media_buy`) and never consults the old buy. So a creative whose only prior buy is `canceled` can be assigned to a fresh package exactly as phase `reuse_creative_on_new_buy` requires. What blocks grading it is the harness, not production.
- **`list_creatives` is purely library-scoped.** `CreativeRepository.get_by_principal` (`src/core/database/repositories/creative.py:99-183`) filters on `tenant_id` + `principal_id` + `data["assets"] IS NOT NULL`, and joins `CreativeAssignment` only when `media_buy_ids` is supplied. It never consults media-buy status. So a creative whose only buy is `canceled` is returned unchanged with its stored `status` — **the graded invariant holds in production today, for the reason that we simply never implemented the cascade.**
- **`filters.creative_ids` is silently dropped.** `get_by_principal` has no `creative_ids` parameter (signature, `creative.py:99-115`), and `_list_creatives_impl` never derives one — it threads `statuses[0]`, `tags`, `created_after/before`, `name_contains`, `media_buy_ids`, `concept_ids` and nothing else (`src/core/tools/creatives/listing.py:216-226`, call site `255-269`). The storyboard's own request shape uses `filters.creative_ids`, so a real conformance run hits this. It is not even reported in `filters_applied` (`listing.py:382-397`).

**Net:** the graded assertion is true of production; the *transition that triggers it* is not implemented; the *filter the storyboard queries with* is not implemented. So the honest green scenario asserts the invariant from a **pre-canceled state** (`Given` the buy is already `canceled`) and lists **unfiltered**, which is what production supports. That is faithful to what is graded — the graded phase is `verify_creative_persists_post_cancel`, and `cancel_buy` contributes only a schema check.

---

## 5. Proposed Gherkin

Complete replacement for feature lines 2093–2109. Assertions chosen so that each is true of production as traced above; the scenario nevertheless remains dormant (§4.4) until the two harness tickets land.

```gherkin
  @T-UC-003-storyboard-creative-fate-after-cancellation @storyboard-v3.1 @v3-1 @cancellation @creative-library @lifecycle-decoupling
  Scenario Outline: A creative assigned to a canceled media buy stays in the library at review state "<status>"
    Given the media buy "mb_creative_fate" is in "canceled" status
    And creative "cr_fate_<status>" is in the library with status "<status>" and was assigned to package "pkg_creative_fate" of media buy "mb_creative_fate"
    When the Buyer Agent sends list_creatives with no filters for the same account
    Then the returned creative_ids should be exactly ["cr_fate_<status>"]
    And the creative "cr_fate_<status>" should have status "<status>"

    # Identity table, deliberately: "expected == seeded" IS the invariant. The buy's
    # terminal state must not rewrite the creative's review state in either direction.
    Examples: Non-terminal review states graded by verify_creative_persists_post_cancel
      | status         |
      | processing     |
      | pending_review |
      | approved       |

    # creative_fate_after_cancellation, phase verify_creative_persists_post_cancel,
    # step list_creatives_after_cancel. Graded at 3.1.1 by three checks:
    #   field_present  creatives[0].creative_id  — still in the library after cancellation
    #   field_value    creatives[0].creative_id  — id unchanged (not re-keyed on cancel)
    #   field_value    creatives[0].status       — allowed_values [processing, pending_review, approved]
    # The Examples set is exactly that allowed_values list. creative-status.json at 3.1.1
    # enumerates six states (adds suspended, rejected, archived); the storyboard grades the
    # narrower three, so the schema (authoritative on which values may exist) and the
    # storyboard (authoritative on which values pass) are both satisfied.
    #
    # Scope note: the sibling half of the upstream storyboard — "cancellation RELEASES the
    # package-creative assignment" — is NOT graded. The cancel_buy phase carries exactly one
    # validation, `check: response_schema`; release lives only in that phase's narrative prose.
    # This scenario therefore grades persistence only, and enters from a buy already in
    # `canceled` status rather than performing the transition (see #TODO-cancel below).
    #
    # creative_fate_after_cancellation: creative lifecycle decoupled from media buy lifecycle
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 phase=list_creatives_after_cancel path=static/compliance/source/protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml
```

**Footer verified by execution.** Running `scripts/audit/storyboard_binding_sweep.py` against a patched copy of the feature file returns for this scenario:

```json
{"repo":"adcp","ref":"v3.1.1","commit":"467fd93d7","phase":"list_creatives_after_cancel",
 "path":"static/compliance/source/protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml",
 "resolved":"dist/compliance/3.1.1/protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml",
 "tier":"protocols","grading":"graded"}
findings: []   bucket: "A"
```

One deliberate footer choice: `phase=` cites the **step** id `list_creatives_after_cancel`, not the phase id `verify_creative_persists_post_cancel`. `phase_is_graded()` (`storyboard_binding_sweep.py:133-148`) truncates its search window at the next `\n      - id: ` line; anchored on the phase id that window ends *before* the step's `validations:` block and the sweep mis-reports `grading: "prose"` → bucket C. Anchored on the step id the window spans the whole step and reports `graded`. Both ids name the same graded thing; the step id is the one the tooling can actually verify. Worth a follow-up to fix the walker, but not in a baseline PR.

Transport-independence: no transport branching; `Given`/`When`/`Then` are identical for MCP / A2A / REST / e2e_rest, matching the surrounding UC-003 convention.

---

## 6. Step inventory

### Reused unchanged

| Phrase | Where | Note |
|---|---|---|
| `the Buyer Agent sends list_creatives with no filters for the same account` | `tests/bdd/test_uc018_list_creatives.py:182` | dispatches via `tests.bdd.steps.generic.when_request._call_via(ctx, ctx.get("transport"))` |

**Caveat, and it is a real one:** that `@when` is defined **module-locally** in `test_uc018_list_creatives.py`, which is *not* in the `pytest_plugins` list at `tests/bdd/conftest.py:49-71`. Module-local pytest-bdd steps are not visible to another feature's test module, so as things stand this phrase is **not** reusable from UC-003 — it has to be lifted into a shared step module first. That lift is ticketed below rather than assumed.

### New steps required

| Phrase | Kind | What it must do |
|---|---|---|
| `the media buy "{media_buy_id}" is in "{status}" status` | `@given` | Seed a `MediaBuy` at the given status via `MediaBuyFactory`. Near-identical phrasings already exist for UC-003 (`the media buy is in "canceled" status`) but are parameterless; parameterise rather than add a fourth near-duplicate — `test_architecture_bdd_no_duplicate_steps.py` counts identical bodies. |
| `creative "{creative_id}" is in the library with status "{status}" and was assigned to package "{package_id}" of media buy "{media_buy_id}"` | `@given` | `CreativeFactory` + a `CreativeAssignment` row. Must use factories, never `session.add()` (CLAUDE.md §8). |
| `the returned creative_ids should be exactly [{expected}]` | `@then` | Set-compare the wire `creatives[].creative_id` against the bracketed list. Model on `test_uc018_list_creatives.py:482` `_returned_creative_ids` + `:502` `then_all_creatives_belong_to`. |
| `the creative "{creative_id}" should have status "{status}"` | `@then` | Exact string compare on the wire item's `status`. |

The two Then helpers should serialise through the production serializer exactly as UC-018 does — `_require_response(ctx).model_dump(mode="json", exclude_none=True)` (`test_uc018_list_creatives.py:199-214`) — so the assertion grades the same bytes the buyer sees rather than an in-memory object.

Not reused, deliberately: `tests/bdd/steps/domain/uc003_update_media_buy.py:1246` `the package "{package_id}" should have creative assignments [{expected_ids}]` asserts against the DB, not the wire, and grades the *release* half that the storyboard does not grade.

---

## 7. TICKET MATERIAL

Every item below is something that cannot land green in this baseline PR.

- **`update_media_buy` implements no cancellation whatsoever.** `src/core/tools/media_buy_update.py` (1673 lines) contains zero occurrences of `cancel` in any case; it handles only `paused` (lines 154-156, 701-745). `_build_update_request` (`:1425`), the MCP wrapper (`:1521`) and `update_media_buy_raw` (`:1598`) expose no `canceled` / `cancellation_reason` parameter, though `adcp==6.6.0`'s `UpdateMediaBuyRequest` carries both. Mandated by `v3.1.1:static/schemas/source/media-buy/update-media-buy-request.json` (`canceled: {type: boolean, const: true}`, `cancellation_reason: {type: string, maxLength: 500}`) and by storyboard `protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml` phase `cancel_buy` step `update_media_buy_canceled`. Also a Pattern #5 boundary-completeness violation: the wrappers drop parameters the SDK request model defines.

- **A spec-shaped cancel request is rejected as an empty update.** `UpdateMediaBuyRequest.has_updatable_fields()` (`src/core/schemas/_base.py:2089-2102`) omits `canceled` from its field tuple, so `media_buy_update.py:1506` raises `AdCPInvalidRequestError("Update request must include at least one updatable field (paused, start_time, end_time, packages, budget, push_notification_config, reporting_webhook, context, ext)")`. Per `update-media-buy-request.json` the *only* required fields for a cancel are `idempotency_key`, `account`, `media_buy_id` plus `canceled: true` — that is a complete, valid request and we return `INVALID_REQUEST` for it.

- **Cancellation does not release package-creative assignments.** `CreativeAssignment` (`src/core/database/models.py:760-796`) has a plain `ForeignKeyConstraint(["media_buy_id"], ["media_buys.media_buy_id"])` with no `ondelete` and no application-level release. Mandated by `dist/docs/3.1.1/creative/creative-libraries.mdx:36` and `dist/docs/3.1.1/media-buy/media-buys/index.mdx:317` ("releases its creative assignments but does not modify the creatives themselves"), and by the `cancel_buy` phase narrative. **Prose-only upstream — ungraded**, so this is a spec-conformance gap, not a storyboard failure. File at lower priority than the two above.

- **`filters.creative_ids` is accepted and silently dropped.** `CreativeRepository.get_by_principal` (`src/core/database/repositories/creative.py:99-115`) takes no `creative_ids` argument, and `_list_creatives_impl` never derives one (`src/core/tools/creatives/listing.py:216-226`, call site `:255-269`). It is also absent from `filters_applied` (`:382-397`), so the buyer gets no signal that the filter was ignored — `query_summary.filters_applied` actively misreports. Mandated by `v3.1.1:static/schemas/source/core/creative-filters.json` (`creative_ids`, `minItems: 1`, `maxItems: 100`), referenced from `creative/list-creatives-request.json` `properties.filters`. The storyboard sends exactly this filter in both `list_creatives_before_cancel` (line 222-224) and `list_creatives_after_cancel` (line 301-303), so any real conformance run hits it. Sibling drops in the same block worth folding into one ticket: `format_ids`, `tags_any`, `accounts`, `unassigned`, `assigned_to_packages`.

- **We never advertise `creative.has_creative_library`.** Zero hits in `src/`; `capabilities.py` emits `media_buy.inline_creative_management=True` only. `v3.1.1:static/schemas/source/protocol/get-adcp-capabilities-response.json` defines `creative.has_creative_library` (default `false`), and `dist/docs/3.1.1/media-buy/specification.mdx:158` scopes the entire library-persistence obligation to sellers advertising it: *"Inline-only sellers that advertise `inline_creative_management` without a creative library MAY keep submitted creatives package-scoped; they do not advertise cross-buy reuse or `list_creatives` readback."* We ship `list_creatives`, `sync_creatives` and a real `CreativeRepository` library, so the flag is simply undeclared. Note the coupling: the `creative` capability object is *"Only present if creative is in supported_protocols"*, so declaring it means also declaring the `creative` protocol — which pulls in the `protocols/creative/` baseline bundle. Needs a decision, not just a one-line edit.

- **UC-003 BDD scenarios outside `T-UC-003-ext-*` are blanket-dormant.** `tests/bdd/conftest.py:3357-3360` fires `pytest.xfail("UC-003 harness not yet wired for non-extension scenarios (full graduation pending, PR #1567 follow-up)")`. Because it is an *imperative* `pytest.xfail()`, these scenarios can never xpass, so nothing signals when production catches up — the ledger is write-only. Graduating this scenario needs a wired branch in `_harness_env`.

- **No harness env can drive two different tools in one scenario.** Each env binds one tool (`CreativeListEnv` → `list_creatives`, `tests/harness/creative_list.py:52-84`); `MediaBuyDualEnv` (`tests/harness/media_buy_dual.py:88-101`) is the sole exception and sniffs create-vs-update by request type, both on the media-buy surface. The upstream storyboard is a five-phase, four-tool walk (`get_products → create_media_buy → sync_creatives → list_creatives → update_media_buy → list_creatives → create_media_buy → sync_creatives`). Grading even the reduced form below needs an env that can seed media-buy state and then dispatch `list_creatives`. Prerequisite for the previous item.

- **UC-018's `list_creatives` steps are module-local and unreusable.** They live in `tests/bdd/test_uc018_list_creatives.py` (`:148`, `:182`, `:199-249`, `:482-517`) and that module is absent from `pytest_plugins` (`tests/bdd/conftest.py:49-71`), so no other feature can reuse them. Lift them into `tests/bdd/steps/domain/` and register the module, or the next scenario that needs `list_creatives` will copy-paste them and trip `test_architecture_bdd_no_duplicate_steps.py`.

- **`storyboard_binding_sweep.py` mis-grades phase-anchored footers.** `phase_is_graded()` (`scripts/audit/storyboard_binding_sweep.py:133-148`) truncates its window at the next `\n      - id: ` (6-space step indent). Anchored on a *phase* id (2-space indent) the window stops at the phase's first step and never reaches `validations:`, so a genuinely graded phase reports `"prose"` → bucket C. Reproduce: `phase=verify_creative_persists_post_cancel` on the footer above. Fix: indent-aware window, or search to the next sibling id at the same indent level.

- **`then_response_schema_valid` is real in UC-018 but absent from UC-003.** `test_uc018_list_creatives.py:217-220` does call `validate_against_pinned_schema`; the brief's note that it "runs no validator" applies to the other copy. Either way `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not 3.1.1, so the validation grades the wrong version — already a known item, cited not re-filed.

---

## 8. Risks

- **Nothing here was verified by execution.** The scenario xfails imperatively at `conftest.py:3357` before any step runs, so the proposed Gherkin has never been executed and the four new step definitions have never been written, let alone run. My green claim rests on tracing production, not on a passing test. Highest-confidence part: `get_by_principal` genuinely ignores media-buy status. Lowest-confidence: the exact wire shape of `status` after `model_dump(mode="json")` on every transport.
- **The `has_creative_library` reading is a judgement call.** I ruled GRADED because the storyboard sits in the `media-buy` baseline whose protocol we declare and whose `required_tools` we implement. A reviewer who weights `prerequisites.description` more heavily ("sellers without a creative library grade this `not_applicable`") could argue the tag should be `@schema-v3.1` until we advertise the flag. I do not think that is right — we *have* the library — but the argument is not frivolous and the fix (declare the flag) is cheap.
- **Entering from a pre-canceled `Given` weakens the scenario relative to upstream.** The storyboard performs the cancel and compares pre/post. Mine asserts the post-state only, because the cancel is unimplemented (§7). It grades the same *invariant* but not the *transition*, and it will not catch a future regression where a newly-implemented cancel introduces a status cascade. That regression is exactly what the storyboard exists to catch. The reduction is a consequence of the production gap, not a preference — call it out in review so it is not mistaken for full coverage.
- **`test_architecture_bdd_no_trivial_assertions.py` was not run against the proposal.** Both Thens compare concrete values, so I expect them to pass, but I could not execute the guard without writing the step bodies into the repo (out of scope per the brief).
- **Two background investigation agents I dispatched had not reported when I finalised this.** Every production claim above is from my own tracing with file:line evidence, so nothing here depends on them.
- **One thing I did not trace to the end:** whether re-syncing an existing library creative (the storyboard's `reassign_creative` step re-sends the full creative body, not just the assignment) resets its `status` back to `pending_review` in `_sync_creatives_impl` (`src/core/tools/creatives/_sync.py:38`). The storyboard does not grade status after reuse, so it does not affect the proposal — but if it does reset, the "review state intact" guarantee is preserved only until the buyer's next sync, which would be worth its own scenario.
- **Drift note, no action:** 3.1.8/HEAD may have moved `creative_fate_after_cancellation`; I did not look, per the brief. Everything above is at `v3.1.1` = `467fd93d77112baf9e094e18980119edcd3a4d07`.

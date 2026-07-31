# Re-pin: `@T-UC-002-storyboard-pending-creatives-state-transition`

Scenario: "Media buy created without creatives sits in pending_creatives until sync_creatives
completes, then transitions to pending_start"
File: `tests/bdd/features/BR-UC-002-create-media-buy.feature:2729-2741`

---

## 1. VERDICT

**NOT GRADED — undeclared gate.**

The storyboard exists, is real, and is genuinely graded at 3.1.1 — but it carries a
scenario-level `requires_capability` gate on `media_buy.creative_approval_mode == auto_approve`,
and **we do not emit that field at all**. Per the 3.1.1 schema's own words, omission is *not* an
affirmative auto-approval claim, and per the storyboard's own header comment, sellers that omit
it "grade **not_applicable**". So this scenario is off our conformance path today. The tag must
become `@schema-v3.1`.

Two further findings that change what the scenario should even say:

- **The scenario is DORMANT, twice over.** Its `Given the buyer sends create_media_buy without
  inline creatives` has **no step definition anywhere** in `tests/bdd/steps/`.
  `tests/bdd/test_uc002_create_media_buy.py:14` binds the whole feature via `scenarios()`, so the
  scenario *is* collected — and then `tests/bdd/conftest.py:99-102` converts the resulting
  `StepDefinitionNotFoundError` into an auto-xfail. Even with steps it would still be dormant: the
  UC-002 catch-all at `tests/bdd/conftest.py:3283` xfails every scenario not explicitly routed to a
  harness branch. **Rewriting the Gherkin alone does not make this scenario grade** — see §5b.
- **The second half is unimplementable green.** There is no `pending_creatives → pending_start`
  transition anywhere in production. See §4.

The gate here is worth distinguishing from the usual "undeclared specialism" case. Both tiers
that own this scenario **are** declared by us (`protocols/media-buy` via
`supported_protocols=[media_buy]`, `specialisms/sales-non-guaranteed` via
`specialisms=[sales_non_guaranteed]`). What fails is a single missing capability field that we
already have the backing data for (`Tenant.approval_mode`). This is a one-field declaration away
from applying — not a business decision about what we sell. That makes it good ticket material
rather than a permanent exclusion.

---

## 2. Real binding at 3.1.1

### What the footer points at

**Nothing.** This scenario has **no `@source` footer at all** — it ends at line 2741 with a bare
summary comment. It is one of the 11 the brief flagged.

Separately, it is the *victim* end of the systematic off-by-one: the **preceding** scenario
(`@T-UC-002-storyboard-measurement-terms-rejected`, line 2727) cites
`.../scenarios/pending_creatives_to_start.yaml` — i.e. **our** storyboard. Fixing this scenario
does not fix that one; `measurement-terms-rejected` still needs its own re-pin to
`measurement_terms_rejected.yaml`.

### The real file

`dist/compliance/3.1.1/protocols/media-buy/scenarios/pending_creatives_to_start.yaml`
(id `media_buy_seller/pending_creatives_to_start`, 305 lines)

Byte-identical duplicate at `dist/compliance/3.1.1/domains/media-buy/scenarios/pending_creatives_to_start.yaml`
(verified identical). Cite the `protocols/` path — it is the one referenced from
`protocols/media-buy/index.yaml` `requires_scenarios`.

### The gate, verbatim (lines 8-14)

```yaml
# This scenario requires an explicit auto-approval declaration. Sellers that
# declare `require_human`, or omit the field because approval behavior is
# legacy-unspecified, grade not_applicable rather than false-failing on a
# manual-review workflow.
requires_capability:
  path: media_buy.creative_approval_mode
  equals: auto_approve
```

### Tier ownership

Both of these list `media_buy_seller/pending_creatives_to_start` under `requires_scenarios`:

- `dist/compliance/3.1.1/protocols/media-buy/index.yaml` — declared by us
- `dist/compliance/3.1.1/specialisms/sales-non-guaranteed/index.yaml` — declared by us

The specialism index also carries a cross-step invariant that is directly relevant:

```yaml
# Cross-step assertion (adcp#2664). status.monotonic rejects resource
# status transitions observed across steps that aren't on the spec
# lifecycle graph — e.g. active → pending_creatives on a media_buy.
invariants:
  - status.monotonic
```

### Graded `validations:` — phase `create_without_creatives`, step `create_buy_no_creatives` (lines 140-168)

This is the phase UC-002 owns. Quoted verbatim:

```yaml
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
          - check: field_present
            path: "media_buy_id"
            description: "Seller assigns a media_buy_id"
          - check: field_value
            path: "media_buy_status"
            value: "pending_creatives"
            description: "media_buy_status is pending_creatives because no creatives supplied"
          - check: field_value
            path: "status"
            value: "completed"
            description: "Envelope task-status is completed on synchronous success (protocol-envelope.json required: [status])"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "pending_creatives_to_start--create_buy_no_creatives"
            description: "Context correlation_id returned unchanged"
          - check: field_equals_context
            path: "packages[0].product_id"
            context_key: "product_id"
            description: "Created package echoes the requested product_id for package-to-product correlation"
          - check: field_value
            path: "packages[0].context.buyer_ref"
            value: "pending-creatives-line-001"
            description: "Created package echoes package-level context for legacy package correlation"
```

### Graded `validations:` — phase `supply_creatives`, step `assign_creative_to_package` (lines 238-260)

This is the transition half. Note it is graded on **`update_media_buy`**, not on `sync_creatives`:

```yaml
        validations:
          - check: response_schema
            description: "Response matches update-media-buy-response.json schema"
          - check: field_present
            path: "affected_packages"
            description: "Package-mutating update returns affected_packages"
          - check: field_contains
            path: "affected_packages[*]"
            value:
              package_id: "$context.package_id"
              product_id: "$context.product_id"
              pricing_option_id: "$context.pricing_option_id"
              creative_assignments:
                - creative_id: "acme-outdoor-display-q3"
            description: "Update response returns the affected package with the assigned creative state"
          - check: field_value
            path: "media_buy_status"
            allowed_values: ["pending_start", "active"]
            description: "media_buy_status advances out of pending_creatives once creatives attached"
          - check: field_value
            path: "status"
            value: "completed"
            description: "Envelope task-status is completed on synchronous update success (protocol-envelope.json required: [status])"
```

The `sync_creatives` step itself (lines 208-211) grades **only** `response_schema`. Nothing else.

### Graded `validations:` — phase `verify_transition`, step `get_media_buy_after_sync` (lines 291-305)

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-media-buys-response.json schema"
          - check: field_value
            path: "media_buys[0].status"
            allowed_values: ["pending_start", "active"]
            description: "Persisted status is past pending_creatives"
          - check: field_equals_context
            path: "media_buys[0].packages[0].product_id"
            context_key: "product_id"
            description: "Read package retains the product_id from the explicit create request"
          - check: field_value
            path: "media_buys[0].packages[0].context.buyer_ref"
            value: "pending-creatives-line-001"
            description: "Read package includes persisted package context for legacy package correlation"
```

### Prose that is NOT graded

Both are only under `expected:` / `narrative:`, so the scenario must not treat them as obligations:

- "valid_actions including sync_creatives" (line 115) — ungraded prose. (I still propose asserting
  it, because production happens to satisfy it and it is a concrete comparison — but it is our
  choice, not a graded requirement.)
- "valid_actions no longer includes sync_creatives as a required next step" (line 281) — ungraded
  prose, and structurally unassertable on that path anyway: `core/media-buy.json` at 3.1.1 has no
  `valid_actions` property on the media-buy object (props are `media_buy_id, account, status,
  health, impairments, rejection_reason, confirmed_at, cancellation, total_budget, packages,
  context, invoice_recipient, creative_deadline, revision, created_at, updated_at, ext`).

---

## 3. Schema constraints at 3.1.1

### `static/schemas/source/protocol/get-adcp-capabilities-response.json` → `media_buy.creative_approval_mode`

The gate field. Verbatim:

```json
"creative_approval_mode": {
  "type": "string",
  "description": "Tenant-wide applicability signal for media-buy creative approval behavior. This is not a notification or new approval workflow. `auto_approve` means human review does not block serving eligibility after creatives are assigned and automated validation passes. `require_human` means one or more products/accounts may require manual review before creatives become eligible to serve; buyers and compliance runners MUST treat this as a worst-case ceiling across this seller's portfolio unless a future product-level override says otherwise. Compliance runners use this mainly to decide whether auto-approval-dependent storyboards apply. When absent, approval behavior is legacy-unspecified; runners SHOULD NOT treat omission as an affirmative auto-approval claim. `ai_assisted` is intentionally not part of the enum until a behavioral contract is defined.",
  "enum": ["auto_approve", "require_human"]
}
```

Two things fall out of this:

1. It is a **first-class sibling** of `media_buy.features`, **not** inside it. Anyone looking for it
   in `MediaBuyFeatures` will not find it — and could not put it there anyway, since
   `core/media-buy-features.json` declares `"additionalProperties": {"type": "boolean"}` and this
   value is a string.
2. `ai_assisted` is deliberately absent from the enum. Our production has a third mode
   (`"ai-powered"`, `src/core/tools/creatives/_sync.py:122`) with **no 3.1.1 representation**.

### `static/schemas/source/enums/media-buy-status.json`

```json
"enum": ["pending_creatives","pending_start","active","paused","completed","rejected","canceled"],
```

`pending_creatives` enumDescription, verbatim:

> **Buyer-side action required.** The media buy is approved by the seller and has no creatives
> assigned — the buyer must attach creatives via `sync_creatives` before the buy can serve. Not to
> be confused with a publisher-side or governance-side approval queue: the seller has already
> accepted the buy; only the buyer's creative submission is missing. Naming convention: `pending_X`
> names the lifecycle phase that is next required (here, `creatives`), not a state of waiting on
> seller/operator approval — consistent with `pending_start` (waiting for the flight date to begin).

### `static/schemas/source/core/protocol-envelope.json`

```json
"required": ["status"]
```

and, verbatim from the description:

> The `status` field is REQUIRED on every task response envelope, including synchronous metadata
> responses (e.g., `get_adcp_capabilities`) where the value is `completed`. Agents shipping
> responses without a top-level `status` are non-conformant regardless of whether the task body
> schema would otherwise validate.

`status` `$ref`s `enums/task-status.json` (protocol TaskStatus) — **not** MediaBuyStatus.

### `static/schemas/source/media-buy/create-media-buy-response.json` → `media_buy_status`

```json
"media_buy_status": {
  "$ref": "/schemas/enums/media-buy-status.json",
  "description": "Initial media buy status. Either 'pending_creatives' (awaiting creative assets), 'pending_start' (ready to serve, waiting for flight date), 'active' (immediate activation), or 'paused' (created with delivery held after all activation prerequisites are satisfied). Added in 3.1: at the top level of flat-on-the-wire MCP responses, the `status` key is reserved for the envelope TaskStatus (`completed` on synchronous success). Sellers SHOULD emit `media_buy_status` from 3.1 onward; the legacy top-level `status: MediaBuyStatus` form is deprecated and removed in 3.2 (#4906). When the deprecated `status` is also present during the 3.1 deprecation window, both MUST carry identical values — divergent emission is a conformance violation flagged by 3.1 compliance storyboards."
}
```

### `static/schemas/source/core/media-buy.json` (read path)

```json
"required": ["media_buy_id", "status", "confirmed_at", "revision", "total_budget", "packages"]
```

`status` here `$ref`s `enums/media-buy-status.json` — the read-path object uses **`status`** for the
domain value, with no `media_buy_status` field. That is why the storyboard's `verify_transition`
checks `media_buys[0].status` and not `media_buys[0].media_buy_status`. The two paths use opposite
key names for the domain status; that is the schema, not a storyboard slip.

---

## 4. Conflicts

### 4a. Schema overrides storyboard: which action unblocks `pending_creatives`

**The `media-buy-status.json` enumDescription says the buyer "must attach creatives via
`sync_creatives`". The storyboard grades the transition on `update_media_buy`** — its
`sync_creatives` step validates `response_schema` and nothing else; the
`media_buy_status ∈ [pending_start, active]` check lives on `assign_creative_to_package`
(`task: update_media_buy`).

Per the brief's authority order the schema wins, so the *scenario title's* framing
("until sync_creatives completes") is schema-aligned prose. But the schema does not grade
anything, and the graded contract is unambiguous about the mechanism: sync alone attaches nothing
to a package. In practice both are needed — sync ingests the asset, update binds it to the
package. The current Gherkin asserts the transition off `sync_creatives` alone, which matches
neither. Moot for the proposal below, since the transition half cannot land green at all (4c).

### 4b. Schema self-tension on top-level `status` — storyboard resolves it, and we match

`create-media-buy-response.json` says the deprecated body `status` is a `MediaBuyStatus` that MUST
equal `media_buy_status`, while the *same description* says the top-level wire `status` key "is
reserved for the envelope TaskStatus (`completed` on synchronous success)". `protocol-envelope.json`
requires top-level `status` and types it as TaskStatus.

The storyboard resolves it in favour of TaskStatus: `status: "completed"` alongside
`media_buy_status: "pending_creatives"` in the same graded block. Production already implements
exactly this and documents it — `src/core/schemas/_base.py:260-290` states that
`TaskResultEnvelope._serialize` overwrites top-level `status` with the protocol TaskStatus, so on
the wire the two are different namespaces. So the brief's known-gap list item "No top-level
`status` on responses" **does not apply to this path** — create_media_buy emits it.

### 4c. Production gap: `pending_creatives → pending_start` does not exist

The scenario's second half is red and cannot be made green by editing Gherkin. Every writer of
`MediaBuy.status` on a buyer-facing path was enumerated; none performs this transition:

- `src/core/tools/creatives/_assignments.py:283-285` — `sync_creatives` transitions **`draft` →
  `pending_creatives`** only, and only when `approved_at is not None`. Opposite direction.
- `src/core/tools/media_buy_update.py:942-951` and `:1178-1187` — `update_media_buy` with
  `creative_ids` also transitions **`draft` → `pending_creatives`** only. Two copies of the same
  block, which is itself a DRY violation.
- `src/services/media_buy_status_scheduler.py:88-90` — the scheduler's candidate query is
  `["pending_start", "pending_activation", "scheduled", "active"]`. **`pending_creatives` is not in
  it**, so a buy parked there is never even examined.

Remaining writers are Admin-UI operator actions (`src/admin/blueprints/workflows.py:225,241`,
`src/admin/blueprints/operations.py:441-452`), not the buyer protocol path.

Net: a buy created without creatives is persisted `pending_creatives`
(`src/core/tools/media_buy_create.py:3645`) and stays there forever from the buyer's perspective.

### 4d. Production gap: package-level `context` is dropped

The storyboard grades `packages[0].context.buyer_ref` on create and
`media_buys[0].packages[0].context.buyer_ref` on read. `adcp.types.aliases.Package` **has** a
`context` field (`ContextObject | None`), but `src/core/tools/media_buy_create.py:4073-4086`
constructs the response `Package` without passing it — the args are `package_id, paused,
product_id, budget, bid_price, pricing_option_id, pacing, targeting_overlay, impressions,
creative_assignments, format_ids_to_provide`. No `context`. So that check fails; it cannot be
asserted green.

### 4e. What the current scenario gets wrong

1. No `@source` footer at all.
2. Tagged `@storyboard-v3.1` although the capability gate is undeclared → should be `@schema-v3.1`.
3. Dormant — the Given has no step definition, so it is auto-xfailed and grades nothing.
4. Asserts a transition production does not implement (4c).
5. Attributes the transition to `sync_creatives` alone; the graded contract puts it on
   `update_media_buy` (4a).
6. `Then the response should carry status "pending_creatives"` names the **wrong field**. On the
   wire, top-level `status` is the protocol TaskStatus (`completed`); the domain value lives on
   `media_buy_status`. Written as-is this assertion is wrong against both the schema and production.
7. Ignores every other graded field on the create step: `media_buy_id` presence, envelope
   `status`, `context.correlation_id` echo, `packages[0].product_id` echo.

### 4f. Note on the existing dual-emit step

`tests/bdd/steps/domain/uc002_create_media_buy.py:1724` (`then_dual_emit_media_buy_status`) already
cites this storyboard and is wired to a live scenario. It asserts only **set membership**
(`media_buy_status in {MediaBuyStatus values}`, `status in {TaskStatus values}`), never a concrete
value — it would pass with `media_buy_status: "canceled"`. It is not in my scope to change, but it
is weaker than `test_architecture_bdd_no_trivial_assertions.py` would ideally allow, and the
proposal below deliberately uses the value-pinning steps instead.

---

## 5. Proposed Gherkin

Replaces lines 2729-2741. Uses **only existing steps** — zero new step definitions — so nothing
can go red on a missing binding. Scoped to the `create_buy_no_creatives` phase, which is the phase
UC-002 owns; the transition phases become tickets.

The account-bearing Given is deliberate, not decoration: the conftest catch-all comment
(`tests/bdd/conftest.py:3278-3282`) records that unwired UC-002 scenarios "route to
`resolve_account_or_error` and fail with 'Account reference is required'", and
`_ensure_request_defaults` does not populate `account`.

```gherkin
  @T-UC-002-storyboard-pending-creatives-state-transition @schema-v3.1 @v3-1 @lifecycle @pending-creatives
  Scenario Outline: Media buy created without creatives is persisted in pending_creatives with a completed task envelope
    Given the tenant is configured for auto-approval
    And a valid create_media_buy request with account natural key brand "testbrand.com" operator "test-operator.example"
    When the Buyer Agent sends the create_media_buy request
    Then the wire media_buy_status should be "<media_buy_status>"
    And the wire status should be "<task_status>"
    And the wire valid_actions should include "<unblocking_action>"

    Examples:
      | media_buy_status  | task_status | unblocking_action |
      | pending_creatives | completed   | sync_creatives    |

    # Graded at AdCP 3.1.1 by phase `create_without_creatives`, step `create_buy_no_creatives`:
    #   media_buy_status = field_value "pending_creatives"  (no creatives supplied)
    #   status           = field_value "completed"          (protocol-envelope.json required: [status])
    # The two are DIFFERENT namespaces on the flat wire: top-level `status` is the protocol
    # TaskStatus, `media_buy_status` is the domain MediaBuyStatus. See src/core/schemas/_base.py
    # `_mirror_media_buy_status` and TaskResultEnvelope._serialize.
    #
    # valid_actions including sync_creatives is storyboard PROSE (`expected:` line 115), not a
    # graded `validations:` entry. Asserted here anyway because production satisfies it from the
    # same single source that drives media_buy_status (media_buy_create.py:4098-4099) and it is a
    # concrete comparison.
    #
    # Tagged @schema-v3.1, NOT @storyboard-v3.1: the storyboard gates on
    # `requires_capability: media_buy.creative_approval_mode == auto_approve`, and
    # src/core/tools/capabilities.py builds MediaBuy(portfolio=, features=, execution=) without
    # that field. Per 3.1.1 get-adcp-capabilities-response.json, "When absent, approval behavior
    # is legacy-unspecified; runners SHOULD NOT treat omission as an affirmative auto-approval
    # claim" — so the runner grades this not_applicable and it is not on our conformance path.
    #
    # The storyboard's later phases (supply_creatives, verify_transition) grade the
    # pending_creatives -> pending_start advance. Not asserted here: production implements no such
    # transition on any buyer-facing path (see GH ticket for the enumeration).
    # pending_creatives_to_start: buy created without creatives reports pending_creatives
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/media-buy/scenarios/pending_creatives_to_start.yaml phase=create_without_creatives step=create_buy_no_creatives
```

Notes on choices:

- **Keep the opaque `@T-UC-002-storyboard-pending-creatives-state-transition` tag unchanged** — it
  is referenced from `docs/test-obligations/bdd-traceability.yaml:1899`.
- `@pending-start` dropped from the tag list: the scenario no longer asserts anything about
  `pending_start`. Re-add it when the transition ticket lands.
- **Single Examples row.** I would rather ship one honest row than pad the table. The obvious
  second row — inline creatives supplied — reads from `_determine_media_buy_status`
  (`media_buy_create.py:3606-3613`: any package with creative_ids sets
  `creatives_approved = False`) as *also* `pending_creatives`, which would be a genuinely
  interesting row. I could not execute it, so it is in Risks rather than the table.
- Title changed to describe what is actually asserted. Leaving the old title's
  "…then transitions to pending_start" over a scenario that no longer checks it would be exactly
  the green-but-vacuous pattern this sweep exists to remove.

### 5b. Required conftest wiring — without this the scenario stays dormant

`tests/bdd/conftest.py:3277-3283` ends the UC-002 harness selector with a catch-all:

```python
        else:
            # Restore the xfail guard every other use case keeps on its catch-all:
            # non-account / non-extension UC-002 scenarios are NOT yet wired (no
            # dispatch_mode -> they route to resolve_account_or_error and fail with
            # "Account reference is required"). Mirror UC-003/004/006/011: xfail them
            # until each is explicitly wired into a run branch above. Dropping this
            # line is what flipped ~800 dormant scenarios from xfail to fail.
            pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")
```

The proposed tag matches none of the live branches — it has no `account` marker, does not start
with `T-UC-002-ext-`, and is in neither `_UC002_IDEMPOTENCY_WIRED` (`:2806`) nor
`_UC002_MANUAL_APPROVAL_WIRED` (`:2816`). So it lands on the catch-all and is xfailed.

**This is safe for the baseline** — `pytest.xfail()` called imperatively raises before the body
runs, so the scenario can never go red. But it also grades nothing, which is the dormant-scenario
anti-pattern this sweep exists to remove. To make it actually grade, add a wired set alongside the
two existing ones and a branch that routes to `MediaBuyCreateEnv`:

```python
# UC-002 storyboard scenarios wired to MediaBuyCreateEnv: grade the spec-3.1.1
# create_buy_no_creatives contract (media_buy_status=pending_creatives +
# envelope status=completed) across all 4 transports.
_UC002_STORYBOARD_WIRED: set[str] = {
    "T-UC-002-storyboard-pending-creatives-state-transition",
}
```

routed identically to the `T-UC-002-ext-` branch (`:3225-3249`) — `MediaBuyCreateEnv`,
`env.setup_media_buy_data()`, and `ctx["dispatch_mode"] = "create"`.

There is precedent for wiring a storyboard scenario this way:
`_UC002_MANUAL_APPROVAL_WIRED` already contains `T-UC-002-storyboard-governance-with-conditions`.

The Gherkin in §5 is correct either way. Whether to land the wiring in the same PR is the sweep
owner's call — if the baseline PR is Gherkin-only, the wiring should be filed as a ticket so the
scenario does not sit dormant indefinitely.

---

## 6. Step inventory

**All existing. No new step definitions required.**

| Step text | Kind | Defined at | Notes |
|---|---|---|---|
| `the tenant is configured for auto-approval` | Given | UC-002 step set (in use at `BR-UC-002…feature:34`) | already drives the main-flow scenario |
| `a valid create_media_buy request with account natural key brand "{brand}" operator "{operator}"` | Given | `tests/bdd/steps/domain/uc002_create_media_buy.py:78` | via `_attach_account_to_full_request` (`:30`) it calls `_ensure_request_defaults`, injects `account`, and sets `ctx["dispatch_mode"]="create"` — all three in one step |
| `the Buyer Agent sends the create_media_buy request` | When | `tests/bdd/steps/domain/uc002_create_media_buy.py:713` | transport-agnostic dispatch |
| `the wire media_buy_status should be "{status}"` | Then | `tests/bdd/steps/domain/uc003_update_media_buy.py:127` | strict `==` via `_assert_wire_field_equals` |
| `the wire status should be "{status}"` | Then | `tests/bdd/steps/domain/uc003_update_media_buy.py:137` | strict `==`; docstring already cites this storyboard |
| `the wire valid_actions should include "{action}"` | Then | `tests/bdd/steps/domain/uc003_update_media_buy.py:148` | membership in a concrete list |

Cross-UC reuse is safe: `tests/bdd/conftest.py:59-63` imports `uc002_create_media_buy`,
`uc003_update_media_buy` and `uc006_sync_creatives` step modules globally.

**Greenness of the Given/When pair, traced by reading:**
`_ensure_request_defaults` (`tests/bdd/steps/generic/given_media_buy.py:62-85`) builds
`packages: [{product_id, budget, pricing_option_id}]` with **no** `creative_assignments` and no
`creatives`, `start_time` = now+1d, `end_time` = now+30d. Into
`_determine_media_buy_status` (`media_buy_create.py:288-306`): not past end → not
Priority 1; `has_creatives=False` → **Priority 2 returns `pending_creatives`**. That single value
is both persisted (`media_buy_create.py:3645`) and put on the wire
(`media_buy_create.py:4098`), and drives `valid_actions_for_status` on the next line.
`valid_actions_for_status("pending_creatives")` returns
`['cancel','update_budget','update_dates','update_packages','add_packages','sync_creatives']`
(executed against `adcp.server.helpers`). The sync path returns
`CreateMediaBuyResult(..., status=AdcpTaskStatus.completed.value)`.

**Deliberately not reused:** `the media buy status should transition to "{target_status}"`
(`tests/bdd/steps/domain/uc006_sync_creatives.py:3125`) reads the DB directly, which is the right
idea for the anti-façade check — but it keys off `ctx["media_buy"]` (a factory-seeded buy), not a
buy just created through `create_media_buy`, and it `_xfail_if_e2e`s. Wiring UC-002's created buy
into it is real work, so the persisted read-back is a ticket, not part of this baseline.

---

## 7. TICKET MATERIAL

- **Declare `media_buy.creative_approval_mode` in `get_adcp_capabilities`.**
  `src/core/tools/capabilities.py:247-250` builds `MediaBuy(portfolio=…, features=…, execution=…)`
  and never sets `creative_approval_mode`. AdCP 3.1.1
  `static/schemas/source/protocol/get-adcp-capabilities-response.json` →
  `media_buy.creative_approval_mode` (enum `auto_approve` | `require_human`) states that "When
  absent, approval behavior is legacy-unspecified; runners SHOULD NOT treat omission as an
  affirmative auto-approval claim." The backing data already exists per-tenant:
  `src/core/database/models.py:84` `approval_mode: Mapped[str]` with values `auto-approve` /
  `require-human` / `ai-powered` (default `"require-human"`), read at
  `src/core/tools/creatives/_sync.py:125`. Map `auto-approve → auto_approve`,
  `require-human → require_human`. **`ai-powered` has no 3.1.1 enum member** — the schema says
  "`ai_assisted` is intentionally not part of the enum until a behavioral contract is defined" —
  so it must map to the worst-case ceiling `require_human`, not be dropped. Consequence today:
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/pending_creatives_to_start.yaml:12-14`
  (`requires_capability`) grades not_applicable for us, silently.

- **Correct the stale comment in `capabilities.py` that names this scenario as active.**
  `src/core/tools/capabilities.py:255-265` asserts that declaring
  `specialisms=[sales_non_guaranteed]` activates `pending_creatives_to_start`. At 3.1.1 that is
  false: the specialism gate passes, but the scenario's own
  `requires_capability: media_buy.creative_approval_mode == auto_approve` gate does not, so the
  runner reports not_applicable rather than the failure the comment says we are deliberately
  exposing ("the public declaration forces prioritization of the remaining gaps instead of hiding
  them"). Right now the gap *is* hidden. Fix alongside the declaration ticket above.

- **Implement the `pending_creatives → pending_start` transition on the buyer path.**
  No writer performs it. `src/core/tools/creatives/_assignments.py:283-285` and
  `src/core/tools/media_buy_update.py:942-951` / `:1178-1187` only handle `draft →
  pending_creatives`; `src/services/media_buy_status_scheduler.py:88-90` restricts its candidate
  query to `["pending_start","pending_activation","scheduled","active"]`, excluding
  `pending_creatives` entirely. Mandated by
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/pending_creatives_to_start.yaml:253-256`
  (`field_value media_buy_status allowed_values: ["pending_start","active"]` on step
  `assign_creative_to_package`) and again at `:294-297` on `get_media_buy_after_sync`. Also
  required by `enums/media-buy-status.json`, whose `pending_creatives` enumDescription defines the
  state as cleared once the buyer attaches creatives. Must respect the `status.monotonic` invariant
  declared at `dist/compliance/3.1.1/specialisms/sales-non-guaranteed/index.yaml`.

- **De-duplicate the two identical `draft → pending_creatives` blocks in `media_buy_update.py`.**
  `:942-951` and `:1178-1187` are the same guard and assignment with the same log line. CLAUDE.md
  DRY invariant. Fold into one helper shared with
  `src/core/tools/creatives/_assignments.py:283-285`, which is a third copy of the same rule — and
  the natural home for the transition logic in the ticket above.

- **Echo package-level `context` on create/read responses.**
  `src/core/tools/media_buy_create.py:4073-4086` constructs the response `Package` without
  `context=`, though `adcp.types.aliases.Package` declares
  `context: ContextObject | None`. Graded at
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/pending_creatives_to_start.yaml:165-168`
  (`field_value packages[0].context.buyer_ref`) and `:302-305`
  (`field_value media_buys[0].packages[0].context.buyer_ref`) — described there as "legacy package
  correlation", so buyers depend on it for package↔line-item mapping.

- **Wire `T-UC-002-storyboard-pending-creatives-state-transition` into the UC-002 harness selector.**
  Without it, `tests/bdd/conftest.py:3283` (`pytest.xfail("UC-002 harness not yet wired for
  non-extension scenarios")`) keeps the scenario dormant no matter how the Gherkin is written, so
  the 3.1.1 `create_buy_no_creatives` contract stays ungraded across all four transports. Add a
  `_UC002_STORYBOARD_WIRED` set next to `_UC002_IDEMPOTENCY_WIRED` (`:2806`) /
  `_UC002_MANUAL_APPROVAL_WIRED` (`:2816`) and route it to `MediaBuyCreateEnv` with
  `ctx["dispatch_mode"] = "create"`, mirroring the `T-UC-002-ext-` branch at `:3225-3249`. Full
  detail in §5b. Same shape as the existing
  `T-UC-002-storyboard-governance-with-conditions` wiring. Grades
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/pending_creatives_to_start.yaml:146-153`.

- **Re-pin the neighbouring `@T-UC-002-storyboard-measurement-terms-rejected` footer.**
  `tests/bdd/features/BR-UC-002-create-media-buy.feature:2711` cites
  `…/scenarios/measurement_terms_rejected.yaml` for the `inventory_list_targeting` scenario and
  `:2727` cites `…/scenarios/pending_creatives_to_start.yaml` for `measurement_terms_rejected` —
  both instances of the systematic off-by-one, both still stale at
  `ref=v3.1-04f59d2d5`. Out of scope for this scenario's re-pin; file so they are not lost.

- **Strengthen `then_dual_emit_media_buy_status` to pin values.**
  `tests/bdd/steps/domain/uc002_create_media_buy.py:1724-1773` asserts only that
  `media_buy_status` is *some* `MediaBuyStatus` and `status` is *some* `TaskStatus`. It would pass
  on `media_buy_status: "canceled"`. The storyboard it cites grades `field_value`, i.e. exact
  values. Migrate its callers to `the wire media_buy_status should be "…"` /
  `the wire status should be "…"` (`uc003_update_media_buy.py:127,137`).

---

## 8. Risks

- **Nothing here was executed.** No test run, no Docker, no `tox`. Every greenness claim in §6 is
  from reading `_ensure_request_defaults` → `_determine_media_buy_status` →
  `create_from_request` / `CreateMediaBuySuccess.sync_success`, plus one direct interpreter call
  against `adcp.server.helpers.valid_actions_for_status`. The proposed scenario should be run
  across all four transports before merge.
- **Biggest single unknown: does the harness seed a matching account row?** The Given supplies an
  account *reference* (natural key brand+operator) but does not *seed* an account. If
  `MediaBuyCreateEnv.setup_media_buy_data()` does not create a matching account, production emits
  `ACCOUNT_NOT_FOUND` on the wire and the scenario is red. The conftest comment at `:3208-3211`
  says the `@account` branch works because "the account Given steps seed the account rows on top",
  which implies seeding is a *separate* step I could not find for this shape — I searched all
  `@given` decorators mentioning "account" and found no create-path account-seeding step. Resolve
  by one of: (a) confirm `setup_media_buy_data()` seeds a default account whose natural key the
  Given should match — then fix the literals to match; (b) add an account-seeding Given; or
  (c) confirm the boundary tolerates an absent account for this tenant and fall back to the plain
  `Given a valid create_media_buy request` (`uc002:104`), in which case the wiring branch in §5b
  must set `ctx["dispatch_mode"] = "create"` itself since that Given does not. **Run it before
  merging.** `account` is optional on `CreateMediaBuyRequest` (verified:
  `model_fields['account'].is_required() is False`), so this is purely about the production
  boundary, not request validation.
- **`Given the tenant is configured for auto-approval` carries its own dormancy note.** Its
  docstring (`uc002_create_media_buy.py:1463-1465`) says "Only the wired idempotency scenarios
  (MediaBuyCreateEnv, with ctx["tenant"] provisioned by conftest's `_harness_env`) reach this step;
  every other UC-002 scenario using this text is blanket-xfailed before any step runs." It requires
  `ctx["tenant"]` and `env.mock["adapter"]`, so it only works under `MediaBuyCreateEnv` — i.e. it
  is fine exactly when the §5b wiring is in place, and irrelevant when it is not.
- **The inline-creatives Examples row I did not add.** `media_buy_create.py:3606-3613` sets
  `creatives_approved = False` for any package carrying creative_ids, which routes to
  `pending_creatives` just like the no-creatives case. If that holds under execution it is a
  strong second row and makes the Outline earn its keep. It also raises a spec question I could
  not settle: 3.1.1's `pending_creatives` enumDescription defines the state as "has no creatives
  assigned", and says nothing about *assigned but unapproved*. The spec being silent, production is
  authoritative — but someone should confirm that reading rather than inherit it from me.
- **Transport parity of `wire_dict(ctx)` unverified.** The three `the wire …` steps all read
  `ctx['wire_response']` through `tests/bdd/steps/_outcome_helpers.wire_dict`. They are in active
  use from UC-003 scenarios, so the plumbing works there; I did not confirm all four transports
  populate `valid_actions` identically on the **create** response. The brief's known-gap list notes
  REST drops `context` and `pagination` and MCP drops `pagination` — neither touches
  `media_buy_status` / `status` / `valid_actions`, but `valid_actions` is the one of my three
  assertions I have not seen exercised on a create response.
- **`response_schema` checks are not represented at all.** Both graded blocks lead with
  `check: response_schema`. The brief records that `then_response_schema_valid` runs no validator
  and that `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5` rather than 3.1.1, so I
  did not attempt it. Once the pinned fixtures are at 3.1.1 this scenario should gain a real
  schema-validation Then.
- **Drift, noted only.** 3.1.2–3.1.8 exist in `dist/compliance/`. I did not read them and treated
  3.1.1 as authority throughout, per the brief.
- **Tier duplication.** The storyboard is byte-identical under `protocols/media-buy/` and
  `domains/media-buy/`. I cite the `protocols/` path because `protocols/media-buy/index.yaml`
  lists it in `requires_scenarios`. If the sweep settles on a different convention across the 40
  scenarios, this footer should follow it.

# Re-ground `@T-UC-003-storyboard-not-cancellable-on-recancel` against AdCP 3.1.1

Scenario: `tests/bdd/features/BR-UC-003-update-media-buy.feature:2077-2091` (sbsweep worktree, `0eb879b62`)
Title: "Re-cancel of a canceled media buy returns NOT_CANCELLABLE, not silent success"

---

## 1. VERDICT

**GRADED — and on our conformance path — but the scenario asserts the wrong code, and it is DORMANT so it grades nothing today.**

Three separate findings, all verified:

1. The behaviour **is** storyboard-graded at 3.1.1, under a hard `check: error_code`. The cited path is wrong (off-by-one, as predicted) but the real binding exists.
2. It **is** on our conformance path. `invalid_transitions` is a `requires_scenarios` entry of the `media-buy` protocol/domain baseline, and `src/core/tools/capabilities.py:99-100,271-272` declares `supported_protocols=[SupportedProtocol.media_buy]`. No specialism gate. Tag stays `@storyboard-v3.1`.
3. **The 3.1.1 schema overrides the storyboard on the error code.** The storyboard hard-grades `NOT_CANCELLABLE`; the schema makes that a **MAY**, makes `error.code` an **open string**, and explicitly names `INVALID_STATE` for "updating a … canceled media buy". Per the brief's authority order (schema wins), our production's `INVALID_STATE` is schema-conformant. The scenario's `NOT_CANCELLABLE` assertion is not schema-mandated.

Separately: **the scenario is dormant.** `tests/bdd/conftest.py` (UC-003 branch, ~line 3360) wires only tags starting with `T-UC-003-ext-`, the two targeting-overlay tags, and three manual-approval tags. Everything else hits `pytest.xfail("UC-003 harness not yet wired for non-extension scenarios")`. Confirmed by execution — every UC-003 status partition/boundary variant xfails at fixture setup:

```
$ pytest tests/bdd/test_uc003_update_media_buy.py -k "status_partition_validation or status_boundary_validation"
1374 deselected, 36 xfailed in 0.81s

$ ... --runxfail -k "status_partition_validation and terminal_canceled"
E   ValueError: _harness_env did not yield a value      # a2a, mcp, rest — all three
```

So no Gherkin I propose can go red, and none can go green either, until the conftest gate opens for this tag. I state that plainly rather than presenting a rewrite as "verified green".

---

## 2. Real binding at 3.1.1

### What the footer wrongly points at

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml
```

Both defects confirmed:
- **Stale ref.** `v3.1-04f59d2d5` is an ancestor of beta.3, older than our 3.1.1 pin.
- **Off-by-one path.** It cites `creative_fate_after_cancellation.yaml` — which is the *next* scenario in the feature file (`@T-UC-003-storyboard-creative-fate-after-cancellation`, line 2093). The scenario's own prose names its true storyboard six times: `invalid_transitions Phase 4 (double_cancel)`.

### The real file

`/Users/konst/projects/adcp/dist/compliance/3.1.1/domains/media-buy/scenarios/invalid_transitions.yaml`
(byte-identical to `dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml` — `diff` returns clean; the two tiers are aliases at 3.1.1 per `dist/compliance/3.1.1/index.json`, which lists `media-buy` under **both** `protocols[]` and `domains[]`).

Source-of-truth path in the repo (only one tier exists in `static/`): `static/compliance/source/protocols/media-buy/scenarios/invalid_transitions.yaml`.

Phase `double_cancel`, **lines 217-289**. Two graded steps.

**`first_cancel` (lines 226-250)** — the first cancel MUST succeed:

```yaml
      - id: first_cancel
        title: "Cancel the media buy"
        task: update_media_buy
        ...
        sample_request:
          media_buy_id: "$context.media_buy_id"
          canceled: true
          cancellation_reason: "Testing NOT_CANCELLABLE on re-cancel"
          idempotency_key: "$generate:uuid_v4#media_buy_seller_invalid_transitions_double_cancel_first_cancel"
          context:
            correlation_id: "invalid_transitions--first_cancel"
        validations:
          - check: response_schema
            description: "Response matches update-media-buy-response.json schema"
```

**`second_cancel` (lines 252-289)** — the graded block, verbatim (lines 279-289):

```yaml
        validations:
          - check: error_code
            value: "NOT_CANCELLABLE"
            description: "Error code is NOT_CANCELLABLE on re-cancel of canceled buy"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object even on errors"
          - check: field_value
            path: "context.correlation_id"
            value: "invalid_transitions--second_cancel"
            description: "Context correlation_id returned unchanged"
```

with (lines 259-266):

```yaml
        expect_error: true
        negative_path: payload_well_formed
        stateful: true
        expected: |
          Reject with:
          - code: NOT_CANCELLABLE
          - recovery: correctable
          - context echoed unchanged
```

Note: `recovery: correctable` sits under `expected:` — **narrative prose, not graded.** Only the three `- check:` entries above are graded. The scenario's `recovery` claim is therefore storyboard-ungraded (though it *is* schema-mandated, see §3).

### Tier ownership

- **`protocols/media-buy` (= `domains/media-buy`)** — the media-buy protocol baseline. `dist/compliance/3.1.1/domains/media-buy/index.yaml:16` lists `media_buy_seller/invalid_transitions` under `requires_scenarios`.
- **Also independently graded by `universal/error-compliance.yaml`** (universal tier, always applies): "Context echo is required on error responses — the correlation ID is even more important for error diagnosis than for success cases. Every error response must include the caller's context object unchanged." Every error step there carries `check: field_present path: "context"` + `check: field_value path: "context.correlation_id"`. So the context-echo half of this scenario has a second, universal-tier mandate.

### Gate declaration

`agent.capabilities: [sells_media]` on the scenario; the baseline it belongs to declares `[sells_media, accepts_briefs, supports_guaranteed, supports_non_guaranteed]`. Neither is a `specialisms/` gate — `invalid_transitions` lives in the protocol baseline, not under `specialisms/`. We declare `supported_protocols=[media_buy]`, so this is on our conformance path. **Keep `@storyboard-v3.1`; do not downgrade to `@schema-v3.1`.**

---

## 3. Schema constraints at 3.1.1

All quotes via `cd /Users/konst/projects/adcp && git show v3.1.1:<path>`.

### `static/schemas/source/media-buy/update-media-buy-request.json`

```json
"canceled": {
  "type": "boolean",
  "description": "Cancel the entire media buy. Cancellation is irreversible — canceled media buys cannot be reactivated. Sellers MAY reject with NOT_CANCELLABLE if the media buy cannot be canceled in its current state.",
  "const": true
}
```

```json
"cancellation_reason": {
  "type": "string",
  "description": "Reason for cancellation. Sellers SHOULD store this and return it in subsequent get_media_buys responses.",
  "maxLength": 500
}
```

`required: ["idempotency_key", "account", "media_buy_id"]`

Two things matter here. `canceled` is `const: true` — there is no `canceled: false`; un-cancelling is not expressible. And the NOT_CANCELLABLE rejection is a **MAY**, not a MUST.

### `static/schemas/source/core/error.json`

`required: ["code", "message"]`. On `code`:

> "Error code for programmatic handling. The error-code vocabulary is open: `error.code` is wire-typed `string` (not a closed enum), the standard codes published in `enums/error-code.json` are **documentary**, and senders MAY emit codes outside that set… Receivers MUST decode unknown codes — treat the response as well-formed, read `error.recovery` for the recovery classification…"

On `recovery` (`enum: [transient, correctable, terminal]`):

> "Senders SHOULD populate `recovery` on every error from 3.1 onward — it is the normative carrier of recovery semantics across version skew… The `enumMetadata.recovery` block in `enums/error-code.json` is the documentary mirror for known codes; **`error.recovery` on the wire is authoritative**."

### `static/schemas/source/enums/error-code.json`

`NOT_CANCELLABLE` is in the enum (line 46). Its descriptions:

```
"NOT_CANCELLABLE": "The media buy or package cannot be canceled in its current state.
 The seller may have contractual or operational constraints that prevent cancellation.
 Recovery: correctable (check the seller's cancellation policy or contact the seller)."
```
```json
"NOT_CANCELLABLE": { "recovery": "correctable", "suggestion": "check the seller's cancellation policy or contact the seller" }
```

But `INVALID_STATE` in the **same enum** explicitly covers this case:

```
"INVALID_STATE": "Operation is not permitted for the resource's current status
 (e.g., updating a completed or canceled media buy, or modifying a canceled package).
 Recovery: correctable (check current status via get_media_buys and adjust request)."
```
```json
"INVALID_STATE": { "recovery": "correctable", "suggestion": "check current status via get_media_buys and adjust request" }
```

### `static/schemas/source/core/protocol-envelope.json`

> "The `status` field is REQUIRED on every task response envelope… Agents shipping responses without a top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate."

On `context`:

> "Per-request opaque caller-supplied correlation object echoed unchanged in the response… that the agent MUST preserve byte-for-byte without parsing."

### `static/schemas/source/media-buy/update-media-buy-response.json`

`allOf: [version-envelope.json, protocol-envelope.json]`, then `oneOf` three mutually-exclusive branches:

| branch | `required` |
|---|---|
| `UpdateMediaBuySuccess` | `["media_buy_id", "revision"]` |
| `UpdateMediaBuyError` | `["errors"]` |
| `UpdateMediaBuySubmitted` | `["status", "task_id"]` |

---

## 4. Conflicts

### 4a. Schema overrides storyboard on the error code — **stated explicitly, as the brief requires**

The storyboard grades `check: error_code value: "NOT_CANCELLABLE"` as a hard pass/fail. The schema does not back that as a requirement:

- `update-media-buy-request.json` says sellers **MAY** reject with NOT_CANCELLABLE — permissive, not mandatory.
- `error.json` makes `code` an **open string**; `enums/error-code.json` is **documentary**, not normative.
- `enums/error-code.json` `INVALID_STATE` names this exact situation: *"updating a completed or **canceled** media buy"*.
- Both codes carry identical `recovery: "correctable"`, so the buyer-facing recovery semantics — which `error.json` calls **authoritative** — are the same either way.

**Where schema and storyboard disagree, the 3.1.1 schema wins: `INVALID_STATE` on a re-cancel of a canceled buy is schema-conformant.** This is not a rationalisation of our production code — it happens to coincide, but the schema reading stands on its own. The storyboard remains a real conformance-runner failure (§7, TM-1); it just is not a *schema* violation.

### 4b. What the scenario gets wrong

- **`NOT_CANCELLABLE` is not schema-mandated** (4a). Production emits `INVALID_STATE` (`src/core/tools/media_buy_update.py:412-420` → `AdCPGoneError`, `src/core/exceptions.py`: `_default_error_code = "INVALID_STATE"`, `_default_status_code = 410`, `_default_recovery = "correctable"`). `grep -rn "NOT_CANCELLABLE" src/` returns **zero hits** — production has never emitted it.
- **`recovery` is asserted nowhere** even though `error.json` calls it the authoritative carrier and `enumMetadata` pins `correctable`. Missing.
- **`suggestion` is asserted nowhere** even though `enumMetadata` supplies the canonical hint. Missing.
- **"not silent success" is only in the title.** The scenario never checks that state was left alone. `expect_error: true` + `stateful: true` on the storyboard step means the buy must be unchanged; nothing grades it.
- **`Then the operation should fail` is a vacuous lead-in** — `And the error code should be "…"` already subsumes it (`tests/bdd/steps/generic/then_error.py:181` vs `:270`).
- **`And the response should echo the context.correlation_id unchanged` has no step definition anywhere.** `grep -rn "correlation_id" tests/bdd/steps/` returns **zero hits**. It appears three times in this feature (lines 2050, 2065, 2083) and is unimplemented in all three. Even if UC-003 were wired, this line alone would raise `StepDefinitionNotFoundError` and auto-xfail the whole scenario (`tests/bdd/conftest.py:95-101`).
- **The prose claim "Distinct from the existing terminal_canceled INVALID_STATE scenario" is false as written.** `T-UC-003-partition-media-buy-status` (line 992) and `T-UC-003-boundary-media-buy-status` (line 1016) both already grade `canceled` → `error "INVALID_STATE" with suggestion`. And `T-UC-003-ext-v` (line 2327) already carries the exact `error code should be "NOT_CANCELLABLE"` assertion under a **strict** xfail. This scenario is the third copy of the same obligation.

### 4c. Divergence found while tracing — the scenario cannot express a re-cancel at all

Sending `canceled: true` is impossible today on every transport:

- `_build_update_request` (`src/core/tools/media_buy_update.py:1425-1518`) has no `canceled` parameter. `grep -n "canceled" src/core/tools/media_buy_update.py` matches only `is_terminal_status` prose — the field is never read.
- `has_updatable_fields()` (`src/core/schemas/_base.py:2087+`) omits `canceled` and `cancellation_reason`, so a `media_buy_id + canceled` request trips the BR-RULE-022 empty-update `INVALID_REQUEST` at `media_buy_update.py:1506` **before** the terminal-state check at `:412`.
- REST's `UpdateMediaBuyBody` (`src/routes/api_v1.py:96-117`) declares no `canceled`; `SalesAgentBaseModel` is `extra="forbid"` outside production, so REST would reject the body outright — a *different* failure from A2A/MCP. Transport-divergent.
- The BDD datatable Given rejects it. Verified by execution against `T-UC-003-ext-v`:
  ```
  AssertionError: Unrecognized update field 'canceled' in datatable — step silently drops it.
  Supported: ['budget', 'end_time', 'idempotency_key', 'invoice_recipient',
              'media_buy_id', 'packages', 'paused', 'start_time'].
  ```
- The harness itself hides the gap: `tests/harness/media_buy_update.py:49-60` `_WRAPPER_UNSUPPORTED_FIELDS` **pops `canceled` and `cancellation_reason`** out of the A2A/MCP payload before dispatch.

---

## 5. Proposed Gherkin

Two proposals. **A** is what I recommend landing in the baseline PR. **B** is the spec-faithful target that becomes a ticket.

### Proposal A — recommended for the baseline PR

Everything here reuses steps that already exist, asserts the schema-authoritative code, and adds the "not silent success" grading the storyboard actually demands and that nothing else in the file covers. It is green today (dormant, cannot go red) and is designed to still be green the day the UC-003 conftest gate opens for this tag.

```gherkin
  @T-UC-003-storyboard-not-cancellable-on-recancel @storyboard-v3.1 @v3-1 @structured-errors @not-cancellable @terminal-state
  Scenario Outline: Further mutation of a terminal media buy is refused structurally and changes nothing - <probe>
    Given the media buy is in "<status>" status
    And a valid update_media_buy request with:
    | field        | value       |
    | media_buy_id | mb_existing |
    And the request includes 1 package update with:
    | field      | value    |
    | package_id | pkg_001  |
    | budget     | <budget> |
    And the package "pkg_001" exists in the media buy
    And the tenant is configured for auto-approval
    When the Buyer Agent sends the update_media_buy request
    Then the result should be error "INVALID_STATE" correctable with suggestion
    And no database records should be modified

    Examples: Terminal statuses refuse every further mutation
      | probe             | status    | budget |
      | recancel_canceled | canceled  | 9000   |
      | after_completed   | completed | 9000   |
      | after_rejected    | rejected  | 9000   |

    # invalid_transitions phase double_cancel (step second_cancel): "canceled is terminal
    # per the AdCP spec, so the second cancel cannot succeed." The storyboard grades
    # error_code = NOT_CANCELLABLE; the 3.1.1 SCHEMA overrides it and we follow the schema:
    #   - update-media-buy-request.json: sellers "MAY reject with NOT_CANCELLABLE" (permissive)
    #   - core/error.json: error.code is an OPEN string; enums/error-code.json is documentary
    #   - enums/error-code.json INVALID_STATE: "updating a completed or canceled media buy"
    #   - both codes carry recovery=correctable, the authoritative carrier per error.json
    # `no database records should be modified` is the "not silent success" half of the
    # storyboard's stateful/expect_error contract - the partition and boundary outlines
    # above grade the code but never grade that state was left alone.
    # The re-cancel payload itself (canceled: true) is NOT sendable today - see GH ticket
    # from TM-2; this outline probes the same terminal-state gate through the only
    # mutation the wrappers accept.
    # @source repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/media-buy/scenarios/invalid_transitions.yaml phase=double_cancel step=second_cancel
```

Deliberately **excluded** because they cannot pass:
- `And the error code should be "NOT_CANCELLABLE"` → TM-1.
- `And the response should echo the context.correlation_id unchanged` → TM-3 (no step, and production does not echo context on this error path).
- `| canceled | true |` in the datatable → TM-2.
- `Then the operation should fail` → dropped as vacuous; `the result should be error "…"` subsumes it.

**Duplication note.** The `after_completed` / `after_rejected` rows overlap the existing partition/boundary outlines on the *code* assertion. They are retained because this outline's second Then (`no database records should be modified`) is not graded anywhere else, and dropping them would leave a single-row outline. If a reviewer prefers zero overlap, cut the Examples table to the `recancel_canceled` row alone and keep it a plain `Scenario`.

### Proposal B — spec-faithful target (ticket, do NOT land)

```gherkin
  @T-UC-003-storyboard-not-cancellable-on-recancel @storyboard-v3.1 @v3-1 @structured-errors @not-cancellable @terminal-state
  Scenario: Re-cancel of a canceled media buy is refused with a structured error and echoed context
    Given the media buy is in "canceled" status
    And the request context correlation_id is "invalid_transitions--second_cancel"
    And a valid update_media_buy request with:
    | field               | value                                      |
    | media_buy_id        | mb_existing                                |
    | canceled            | true                                       |
    | cancellation_reason | Deliberate re-cancel to force the refusal  |
    When the Buyer Agent sends the update_media_buy request
    Then the result should be error "INVALID_STATE" correctable with suggestion
    And the response context.correlation_id should be "invalid_transitions--second_cancel"
    And no database records should be modified
```

Requires TM-2 (`canceled` plumbing, all four layers) and TM-3 (context echo + two new steps).

---

## 6. Step inventory

### Existing — reused unchanged by Proposal A

| Step | Definition |
|---|---|
| `Given the media buy is in "{status}" status` | `tests/bdd/steps/domain/uc003_update_media_buy.py:162` |
| `Given a valid update_media_buy request with:` (datatable) | `tests/bdd/steps/domain/uc003_update_media_buy.py:~250` |
| `And the request includes 1 package update with:` | `tests/bdd/steps/domain/uc003_update_media_buy.py` |
| `And the package "pkg_001" exists in the media buy` | `tests/bdd/steps/domain/uc003_update_media_buy.py` |
| `And the tenant is configured for auto-approval` | generic steps |
| `When the Buyer Agent sends the update_media_buy request` | `tests/bdd/steps/domain/uc003_update_media_buy.py:788` |
| `Then the result should be <outcome>` | `tests/bdd/steps/domain/uc002_create_media_buy.py:834` → `_assert_error_outcome:1287` |
| `And no database records should be modified` | `tests/bdd/steps/domain/uc003_ext_error_scenarios.py:811` |

`the result should be error "CODE" correctable with suggestion` is **wire-first**: `_assert_error_outcome` routes to `result.assert_wire_error(code, recovery=…, require_suggestion=True)` against `result.wire_error_envelope` whenever a wire transport dispatched (`uc002_create_media_buy.py:1339-1345`). The grammar already parses the optional `correctable | transient | terminal` middle token (`:1337`) — no step change needed. This satisfies the Error Verification Policy in `tests/CLAUDE.md`.

Existing steps deliberately **not** used:
- `And the error should include "recovery" field with value "correctable"` (`uc003_ext_error_scenarios.py:795`) — reads the *reconstructed* `ctx["error"]`, not the wire. The outcome grammar's `correctable` token asserts the same thing on the real envelope. Prefer the wire.
- `Then the operation should fail` (`generic/then_error.py:181`) — subsumed.

### New — required by Proposal A

**None.** Proposal A introduces no new step definitions.

### New — required by Proposal B (ticket only)

| Step | Why |
|---|---|
| `Given the request context correlation_id is "{cid}"` | No `correlation_id` step exists anywhere in `tests/bdd/steps/` (zero grep hits). |
| `Then the response context.correlation_id should be "{cid}"` | Same. Must read `ctx["wire_error_envelope"]["context"]["correlation_id"]`, not a reconstructed exception. |
| `canceled` / `cancellation_reason` added to the datatable Given's `_supported_fields` | Currently asserts out with "Unrecognized update field". |

---

## 7. TICKET MATERIAL

**TM-1 — `NOT_CANCELLABLE` is never emitted; we fail `invalid_transitions` phase `double_cancel`.**
`grep -rn "NOT_CANCELLABLE" src/` → 0 hits. Re-canceling a canceled buy yields `AdCPGoneError` → wire `INVALID_STATE`, HTTP 410 (`src/core/tools/media_buy_update.py:412-420`; `src/core/exceptions.py` `AdCPGoneError._default_error_code = "INVALID_STATE"`).
Mandated by: `dist/compliance/3.1.1/domains/media-buy/scenarios/invalid_transitions.yaml:279-282`, `check: error_code value: "NOT_CANCELLABLE"` — a hard grade, so the conformance runner fails this step for us.
Counter-weight to record on the ticket: `static/schemas/source/media-buy/update-media-buy-request.json` `canceled.description` says sellers **MAY** reject with NOT_CANCELLABLE, `core/error.json` makes `code` an open string with `enums/error-code.json` explicitly documentary, and `INVALID_STATE`'s own enumDescription names "updating a completed or canceled media buy". So this is a **storyboard-vs-schema conflict to raise upstream in `adcontextprotocol/adcp`**, not necessarily a production bug. Decide upstream first; only then change production.
Already partly tracked: `T-UC-003-ext-v` strict xfail, `tests/bdd/conftest.py:736-753`, FIXME `salesagent-gh8p.13`. That FIXME cites a beads id in a repo file — should be a GH issue number per CLAUDE.md.

**TM-2 — `canceled` / `cancellation_reason` are unreachable on every transport; a cancel request is silently converted into an empty-update rejection.**
- `src/core/tools/media_buy_update.py:1425-1518` — `_build_update_request` has no `canceled` parameter; the field is never read anywhere in the module.
- `src/core/schemas/_base.py:2087+` — `has_updatable_fields()` omits `canceled`/`cancellation_reason`, so `media_buy_id + canceled` hits BR-RULE-022 `INVALID_REQUEST` at `media_buy_update.py:1506` before the terminal-state check at `:412`.
- `src/routes/api_v1.py:96-117` — `UpdateMediaBuyBody` declares no `canceled`; `extra="forbid"` means REST rejects the body with a different error than A2A/MCP. **Transport divergence, Pattern #5 violation.**
Mandated by: `update-media-buy-request.json` declares `canceled` (`const: true`) and `cancellation_reason` (`maxLength: 500`, "Sellers SHOULD store this and return it in subsequent get_media_buys responses"); `invalid_transitions.yaml:237-247,268-278` sends both on the wire.
Blast radius: no cancel flow is reachable through any AdCP transport today. `T-UC-003-ext-v` is unrunnable for the same reason.

**TM-3 — `context` is not echoed on the terminal-state error, and no BDD step exists to grade context echo anywhere.**
`build_two_layer_error_envelope` (`src/core/exceptions.py`) only emits `envelope["context"]` when `exc.context` is set. The terminal-state raise at `media_buy_update.py:413-420` passes `field=` and `suggestion=` but **not** `context=req.context` — unlike `_verify_principal(..., context=req.context)` two lines earlier at `:403`. Inconsistent within one function.
Mandated by: `core/protocol-envelope.json` `context` — "echoed unchanged in the response… MUST preserve byte-for-byte"; `invalid_transitions.yaml:283-289` (`field_present: context`, `field_value: context.correlation_id`); and **`universal/error-compliance.yaml`** (universal tier, always applies) — "Every error response must include the caller's context object unchanged", graded on every error step in that storyboard.
Test-side: `grep -rn "correlation_id" tests/bdd/steps/` → 0 hits. Three UC-003 scenarios assert it (feature lines 2050, 2065, 2083); all three would raise `StepDefinitionNotFoundError`.
Suggested scope: audit every `raise AdCP*Error` in `src/core/tools/` for a missing `context=req.context`, then add the two steps from §6.

**TM-4 — the whole of UC-003 is dormant except six tag families; the storyboard scenarios grade nothing.**
`tests/bdd/conftest.py` UC-003 branch (~line 3360) runs only `T-UC-003-ext-*`, `T-UC-003-partition-targeting-overlay`, `T-UC-003-boundary-targeting-overlay`, `T-UC-003-alt-manual`, `T-UC-003-approval-tenant`, `T-UC-003-approval-adapter`. Everything else: `pytest.xfail("UC-003 harness not yet wired for non-extension scenarios (full graduation pending, PR #1567 follow-up)")`.
Measured: 36/36 status partition + boundary variants xfail at fixture setup across a2a/mcp/rest. All four `@storyboard-v3.1` UC-003 scenarios (lines 2043, 2058, 2077, 2093) are dormant.
This is the dormant-scenario anti-pattern: a `@storyboard-v3.1` tag advertising conformance grading that never executes. Graduating UC-003 is the prerequisite for TM-1/TM-2/TM-3 having any test teeth.

**TM-5 — the test harness masks TM-2 on A2A/MCP.**
`tests/harness/media_buy_update.py:49-60` `_WRAPPER_UNSUPPORTED_FIELDS` pops `canceled`, `cancellation_reason`, `new_packages`, `revision`, `account`, `invoice_recipient`, `proposal_id`, `today`, `total_budget` from the payload before calling the A2A/MCP wrapper, "so the flat-kwargs call doesn't fail on unexpected keyword arguments". The REST path (`_build_update_rest_body`) does **not** pop them. Net effect: the harness makes A2A/MCP look like they accept fields they drop, while REST fails differently — so a test can never observe the real divergence. Every entry in that tuple is a field the 3.1.1 request schema declares and our wrappers silently discard; the tuple is an undeclared allowlist that should shrink to empty as TM-2 lands.

**TM-6 — the storyboard `@source` footer format cannot express the graded step.**
Current footers carry only `path=`. The graded unit is a *step inside a phase* (`double_cancel` / `second_cancel`). Without `phase=` / `step=`, an off-by-one path swap is undetectable by inspection — which is exactly how this scenario ended up citing `creative_fate_after_cancellation.yaml`. Proposal A adds `phase=`/`step=`; the binding-sweep checker (`docs/test-obligations/storyboard-binding-baseline.md`) should require and verify both.

---

## 8. Risks

- **Proposal A is not execution-verified green.** It cannot be: the conftest gate xfails the tag before any step runs. I verified each *ingredient* separately — the steps exist, `_assert_error_outcome` handles the `correctable` token and asserts on `wire_error_envelope`, `AdCPGoneError` produces `INVALID_STATE`/410/`correctable`/`suggestion`, and `is_terminal_status("canceled") is True` (executed against `adcp.server.helpers`). But the assembled scenario has never run. If the UC-003 gate opens, re-verify before trusting it.
- **`no database records should be modified` may need `ctx["existing_package"]`.** It reads `ctx.get("existing_package")` and walks child `MediaPackage` rows. Under the `T-UC-003-ext-` harness branch `_setup_existing_media_buy` seeds one, so this should hold — unverified for this scenario's exact Given sequence.
- **The schema-over-storyboard call on `INVALID_STATE` is a judgement, not a mechanical derivation.** It rests on three independent schema signals (MAY, open-string `code`, `INVALID_STATE`'s enumDescription naming canceled buys) and the brief's explicit "schema wins" rule. A reviewer who weights the storyboard's hard `check: error_code` above the schema's MAY would land on `NOT_CANCELLABLE` + strict xfail instead — which would duplicate `T-UC-003-ext-v`. Worth confirming with the reviewer before landing.
- **`is_terminal_status("cancelled")` (British spelling) returns `False`** while `"canceled"` returns `True`. Executed and confirmed against `adcp.server.helpers`. Not in scope here, but any seeded status string using the double-l spelling silently bypasses the terminal gate.
- **Line numbers for the datatable/package Given steps in §6** are approximate; I confirmed the definitions exist and their supported-field set by execution (the `AssertionError` above enumerates it verbatim), but did not pin every decorator line.
- **`dist/compliance/3.1.1/protocols/…` vs `domains/…`** are byte-identical today. I cite the `static/compliance/source/protocols/…` path in the footer because that is the only tier that exists in `static/` at `v3.1.1`. If upstream splits the tiers, the footer needs revisiting.
- **I did not run the full BDD suite.** Only targeted UC-003 selections against the existing `agent-pg-salesagent-sbsweep` container. No files under `/Users/konst/projects/salesagent-sbsweep` were modified.

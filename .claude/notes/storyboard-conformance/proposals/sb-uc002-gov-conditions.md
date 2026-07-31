# Re-pin proposal — `@T-UC-002-storyboard-governance-with-conditions`

Scenario: "Governance approved with conditions -- seller attaches conditions to the buy"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-002-create-media-buy.feature:2634`

---

## 1. VERDICT

**NOT GRADED — undeclared gate.**

`media_buy_seller/governance_conditions` is pulled onto a conformance run by exactly **one**
index at 3.1.1: `specialisms/governance-aware-seller`. We do not declare that specialism.
The tag `@storyboard-v3.1` is unjustified and must become `@schema-v3.1`.

Two independent facts make this binary, not a judgement call:

1. The scenario is **absent** from `protocols/media-buy/index.yaml` `requires_scenarios`
   (lines 10–24) and from `domains/media-buy/index.yaml` — the two baselines every media-buy
   seller runs. It appears only under `specialisms/governance-aware-seller/index.yaml:23–28`.
2. `specialisms/sales-non-guaranteed/index.yaml` — the **one specialism we do declare** —
   requires 15 scenarios, and `media_buy_seller/governance_conditions` is not among them.
   (It does pull in `governance_aware_seller/governance_multi_agent_rejected`, so the omission
   is deliberate selection, not an oversight in the index.)

The spec states the consequence itself, at
`dist/compliance/3.1.1/specialisms/governance-aware-seller/index.yaml:58–60`:

> Sellers that do not claim this specialism are graded `not_applicable` on
> the `check_governance` scenarios rather than failed.

Secondary confirmation — the file's own gate declarations, which we fail on both counts:

```yaml
# dist/compliance/3.1.1/protocols/media-buy/scenarios/governance_conditions.yaml:7-10
required_tools:
  - sync_governance
  - get_products
  - create_media_buy
```
```yaml
# same file, lines 28-32
agent:
  interaction_model: media_buy_seller
  capabilities:
    - sells_media
    - governance_aware
```

We declare `specialisms=[sales_non_guaranteed]`, `supported_protocols=[media_buy]`
(`src/core/tools/capabilities.py:99-100`, `271-272`). No `governance_aware`. We ship no
`check_governance` and no `sync_governance` tool — `ls src/core/tools/` has neither, and the
only governance surface in production is the account-level `governance_agents` column
(`src/core/database/models.py:827`) written through `sync_accounts`
(`src/core/tools/accounts.py:629`).

**A third defect, independent of the gate:** the scenario is written **backwards**. It has the
buyer attaching a `governance_decision` payload to `create_media_buy`. Both the storyboard and
the 3.1.1 schema say the opposite — the *seller* calls `check_governance` on the account's
registered governance agent, and the only thing that crosses the buyer→seller wire is a
`governance_context` JWS string on the **protocol envelope**. There is no `governance_decision`
field anywhere in AdCP 3.1.1. See §4.

---

## 2. Real binding at 3.1.1

### What the footer says now (wrong twice)

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/governance_denied.yaml
```

* `ref=v3.1-04f59d2d5` is an ancestor of `3.1.0-beta.3` — older than our own 3.1.1 pin.
* The path names **`governance_denied`**, the *next* scenario's storyboard. The scenario's own
  prose line one above it says `# governance_conditions: conditions persist on the buy for
  downstream enforcement`. Classic off-by-one; matches the mechanically proven pattern.

### The real file

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/governance_conditions.yaml`
(byte-identical to `domains/media-buy/scenarios/governance_conditions.yaml` — `diff` is empty).

`id: media_buy_seller/governance_conditions` (line 1).
Phase `buy_with_conditions` (line 141) → step `create_media_buy_conditions` (line 173).

### The graded `validations:` block, verbatim

```yaml
# governance_conditions.yaml:202-204
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
```

That is the **entire** grading of the terminal step. Everything the BDD scenario asserts lives
in the `expected:` block — narrative prose, ungraded:

```yaml
# governance_conditions.yaml:181-186
        expected: |
          The buy succeeds with governance conditions attached:
          - media_buy_id: present
          - media_buy_status: active, pending_start, or pending_creatives (deprecated top-level status may mirror this during the 3.1 migration window)
          - governance_context: token from the governance agent
          - conditions visible to the buyer
```

So even for a seller that *does* claim `governance-aware-seller`, "conditions visible to the
buyer" is **not** a graded check. The only graded assertion is schema validity of the
create_media_buy response.

The other graded checks in this storyboard are on setup steps, not on the conditions behaviour:
`sync_plans` → `response_schema` (85–87); `sync_accounts` → `response_schema` +
`field_present accounts[0].account_id` (109–114); `sync_governance` → `response_schema`
(137–139); `get_products` → `response_schema` + `field_present products` (166–171).

### Tier

The scenario **file** sits under `protocols/` and `domains/`, but tier-by-path is misleading
here: the runner composes a run from `requires_scenarios`, and only the `specialisms/` tier
references this one. Effective tier = **specialism-gated**.
(Worth flagging to whoever maintains `scripts/audit/storyboard_binding_sweep.py`: it derives
tier from the path prefix, so it will classify this scenario as `protocols` and miss the gate.
See TICKET MATERIAL.)

---

## 3. Schema constraints at 3.1.1

All quotes via `cd /Users/konst/projects/adcp && git show v3.1.1:<path>`.

**`static/schemas/source/media-buy/create-media-buy-request.json`** — no governance input at all:

```
required:   ["idempotency_key", "account", "brand", "start_time", "end_time"]
properties: idempotency_key, plan_id, account, proposal_id, total_budget, packages, brand,
            advertiser_industry, invoice_recipient, io_acceptance, po_number,
            agency_estimate_number, start_time, end_time, paused, push_notification_config,
            reporting_webhook, artifact_webhook, context, ext
```

No `governance_decision`. No `conditions`. No `governance_context`.

**`static/schemas/source/core/protocol-envelope.json`** — this is where the governance token
actually lives, and it is buyer→seller, a *string*, not a decision object:

```json
"governance_context": {
  "type": "string",
  "description": "Governance context token issued by the account's governance agent during check_governance. Buyers attach it to governed purchase requests ... sellers persist it and include it on all subsequent governance calls for that action's lifecycle. ...",
  "minLength": 1,
  "maxLength": 4096,
  "pattern": "^[\\x20-\\x7E]+$"
}
```
```json
"required": ["status"]
```

**`static/schemas/source/enums/governance-decision.json:7`** — the decision vocabulary:

```json
"enum": ["approved", "denied", "conditions"]
```

with (line 11) `"conditions": "Approved if the caller accepts the listed conditions and re-calls
check_governance with adjusted parameters"`. **`APPROVED_WITH_CONDITIONS` is not a value in AdCP
3.1.1.** The scenario invented it.

**`static/schemas/source/governance/check-governance-response.json`** — the only schema in 3.1.1
that declares `conditions`, and it is the *governance agent's* response, not the seller's:

```json
"conditions": {
  "type": "array",
  "description": "Present when verdict is 'conditions'. Specific adjustments the caller must make. After applying conditions, the caller MUST re-call check_governance with the adjusted parameters before proceeding.",
  "items": {
    "type": "object",
    "properties": {
      "field":          { "type": "string", "description": "Dot-path to the field that needs adjustment ..." },
      "required_value": { "description": "The value the field must have for approval. ..." },
      "reason":         { "type": "string", "description": "Why this condition is required." }
    },
    "required": ["field", "reason"],
    "additionalProperties": false
  }
}
```

with the conditional `allOf` (lines ~13–40): `verdict == "conditions"` ⇒ `required: ["conditions"]`
with `minItems: 1`, and `verdict ∈ {approved, conditions}` ⇒ `required: ["expires_at"]`.
Response `required: ["check_id", "verdict", "plan_id", "explanation"]`.

Note the flow-control semantics the scenario also gets wrong: `conditions` means *the caller
adjusts and re-calls check_governance*. It does **not** mean "attach a conditions array to the
created buy for downstream enforcement". The storyboard's own prose ("conditions visible to the
buyer") is looser than the schema; **the schema wins.**

**`static/schemas/source/media-buy/create-media-buy-response.json`** — success branch:

```json
"required": ["media_buy_id", "confirmed_at", "revision", "packages"]
```

Declared properties: `media_buy_id, account, invoice_recipient, media_buy_status, status
(deprecated), confirmed_at, creative_deadline, revision, currency, total_budget, valid_actions,
available_actions, packages, planned_delivery, sandbox, context, ext`. **No `conditions`, no
`governance_decision`, no `governance_context`.** (`additionalProperties: true` means emitting
them would not *fail* validation — but nothing in 3.1.1 asks for them, and no graded check would
observe them.)

The one governance-adjacent response field that does exist is `planned_delivery`:

> "Present when the account has governance_agents or when the seller chooses to provide delivery transparency."

— i.e. a MAY/SHOULD with no `required` backing it, and we do not emit it. Not assertable green.

---

## 4. Conflicts

**Where the schema overrode the storyboard.** The storyboard's `expected:` prose promises
"conditions visible to the buyer" on the create_media_buy response. No 3.1.1 schema declares a
`conditions` field on that response, and the graded check is only `response_schema`. Per the
authority order, **the 3.1.1 schema wins**: conditions are a `check_governance` response
concept, and the create_media_buy response has no place to put them.

**What the current scenario gets wrong.**

| Line | Text | Defect |
|---|---|---|
| 2635 | `decision "APPROVED_WITH_CONDITIONS"` | Not a value in `enums/governance-decision.json`. The enum is `approved \| denied \| conditions`, lowercase. Fabricated. |
| 2636 | `the buyer attaches the governance_decision payload to the create_media_buy request` | Direction inverted. No `governance_decision` property exists in 3.1.1 anywhere. The seller calls `check_governance`; the buyer passes only a `governance_context` **string** on the envelope. |
| 2637 | `sends create_media_buy with the governance_decision payload` | Schema-impossible request. |
| 2638 | `the response should carry the media_buy_id` | Fine in isolation — but existence-only, and already covered by `T-UC-002-main`. |
| 2639 | `the response should echo the governance_decision with decision "..."` | Asserts a field no 3.1.1 schema declares, in response to an input no 3.1.1 schema accepts. |
| 2640 | `the response should carry the conditions array attached to the persisted buy` | Same. Also contradicts the flow-control semantics of `conditions` (re-call, don't persist). |
| footer | `ref=v3.1-04f59d2d5`, `path=.../governance_denied.yaml` | Stale ref (pre-beta.3) + off-by-one path. |

**Vacuity.** None of it currently executes. The scenario has zero matching step definitions and
is auto-xfailed by `tests/bdd/conftest.py:101` (`Step definition not found`). Independently, the
UC-002 catch-all at `tests/bdd/conftest.py:3282` blanket-xfails every UC-002 scenario that is not
`@account`, `T-UC-002-ext-*`, `nfr-highvalue`, `T-UC-002-nfr-001-enforcement`, or in
`_UC002_IDEMPOTENCY_WIRED`/`_UC002_MANUAL_APPROVAL_WIRED`. So this tag is dormant **twice over**
— and any rewrite that does not also add a wiring branch stays dormant no matter what it asserts.

**Duplication.** `BR-UC-030-manage-governance-binding.feature:288`
(`@T-UC-030-check-conditions`) already models this behaviour, and models it in the *correct*
direction: the Seller Agent calls `check_governance` outbound, the governance agent returns
`status "conditions"` with a conditions array (minItems 1), `expires_at`, and a
`governance_context` JWS. UC-030 is where the consultation loop belongs. (It is itself dormant —
see TICKET MATERIAL.)

---

## 5. Proposed Gherkin

Rewritten to the residue that is on our path and true at 3.1.1: governance never rides on
`create_media_buy` in either direction for a seller that does not claim `governance-aware-seller`.
The parametrized rows name the three fields the old scenario asserted, each with its real 3.1.1
owner in the footer.

**Verified green by execution.** With the wiring below applied to a scratch copy of the branch:
the scenario alone → **9 passed** (3 rows × mcp/a2a/rest). Whole UC-002 BDD file →
`135 passed, 3 skipped, 1228 xfailed, 0 failed`, against a measured baseline of
`126 passed, 3 skipped, 1231 xfailed` — exactly +9 passing rows, −3 xfails, no collateral.
BDD structural guards (`no_trivial_assertions`, `no_pass_steps`, `no_duplicate_steps`,
`no_silent_env`, `no_dict_registry`): 12 passed. The experiment was then reverted —
`/Users/konst/projects/salesagent-sbsweep` is untouched.

```gherkin
  @T-UC-002-storyboard-governance-with-conditions @schema-v3.1 @v3-1 @governance @governance-decision @conditions
  Scenario Outline: Governance conditions never ride on create_media_buy -- "<field>" is absent from the 3.1.1 create_media_buy response
    Given the tenant is configured for auto-approval
    And a valid create_media_buy request with account "acc-001"
    And the account "acc-001" exists and is active
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And the response status should be "completed"
    And the response should include a "media_buy_id"
    And the create_media_buy response should not carry a "<field>" field

    Examples: governance fields the 3.1.1 contract places outside create_media_buy
      | field               |
      | governance_decision |
      | conditions          |
      | governance_context  |
    # Retagged @storyboard-v3.1 -> @schema-v3.1: media_buy_seller/governance_conditions is
    # required only by specialisms/governance-aware-seller (index.yaml:23-28), which we do not
    # declare (capabilities.py:271-272 -> specialisms=[sales_non_guaranteed]). Non-claiming
    # sellers are graded not_applicable, not failed (governance-aware-seller/index.yaml:58-60).
    # The storyboard's only graded check on the terminal step is `response_schema`
    # (governance_conditions.yaml:202-204); "conditions visible to the buyer" is `expected:`
    # prose (181-186), never graded. Schema overrides that prose: conditions[] is declared on
    # governance/check-governance-response.json, not on create-media-buy-response.json, and
    # verdict=conditions means re-call check_governance, not persist-on-the-buy.
    # The prior text was direction-inverted (buyer attaches a governance_decision payload) and
    # used "APPROVED_WITH_CONDITIONS", which is not in enums/governance-decision.json
    # (approved | denied | conditions). governance_context is an envelope STRING
    # (core/protocol-envelope.json), buyer->seller, not a decision object.
    # The seller-side check_governance conditions loop is BR-UC-030 @T-UC-030-check-conditions.
    # @source repo=adcp ref=v3.1.1 phase=buy_with_conditions path=dist/compliance/3.1.1/protocols/media-buy/scenarios/governance_conditions.yaml#L173
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/enums/governance-decision.json
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/protocol-envelope.json
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/governance/check-governance-response.json
```

### Wiring required (otherwise it stays dormant)

`tests/bdd/conftest.py:2816` — add the tag to the set that routes UC-002 scenarios through
`MediaBuyCreateEnv` with `ctx["uc002_full_create"] = True`:

```python
_UC002_MANUAL_APPROVAL_WIRED: set[str] = {
    "T-UC-002-alt-manual",
    "T-UC-002-storyboard-governance-with-conditions",
}
```

The set name no longer describes its contents once a second scenario joins; renaming it to
something like `_UC002_FULL_CREATE_WIRED` in the same PR would be cleaner, but that touches the
UC-003 sibling comment block and is a judgement call for the lead.

---

## 6. Step inventory

**Existing — reused unchanged (4 of 5 Thens, all Givens, the When):**

| Step | Defined at |
|---|---|
| `Given the tenant is configured for auto-approval` | `tests/bdd/steps/domain/uc002_create_media_buy.py:1451` |
| `Given a valid create_media_buy request with account "{account_id}"` | `tests/bdd/steps/domain/uc002_create_media_buy.py:119` |
| `Given the account "{account_id}" exists and is active` | `tests/bdd/steps/domain/uc002_create_media_buy.py:264` |
| `When the Buyer Agent sends the create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:713` |
| `Then the response should succeed` | `tests/bdd/steps/generic/then_media_buy.py:18` |
| `Then the response status should be "{status}"` | `tests/bdd/steps/generic/then_success.py:40` |
| `Then the response should include a "{field}"` | `tests/bdd/steps/generic/then_media_buy.py:56` |

**New — one step.** Add to `tests/bdd/steps/domain/uc002_create_media_buy.py`:

```python
@then(parsers.parse('the create_media_buy response should not carry a "{field}" field'))
def then_create_response_omits_field(ctx: dict, field: str) -> None:
    """Assert the buyer-facing create_media_buy wire body omits ``field``."""
    from tests.bdd.steps._outcome_helpers import wire_dict

    wire = wire_dict(ctx)
    assert wire.get(field) is None, (
        f"create_media_buy response must not carry '{field}' — 3.1.1 places it outside "
        f"the create_media_buy contract, but the wire carried: {wire.get(field)!r}"
    )
```

It asserts on the **real serialized wire** via `wire_dict()`
(`tests/bdd/steps/_outcome_helpers.py:43`), which raises rather than passing vacuously if a
real-wire transport failed to stash `wire_response` — so it cannot degrade into a tautology on
mcp/a2a/rest.

**Deliberately not reused:** `the response should NOT contain "{field}" field`
(`tests/bdd/steps/domain/uc003_update_media_buy.py:1197`). Its success path calls
`_assert_a2a_submitted_task_has_no_artifacts(ctx)`, which is correct for a `submitted` envelope
and wrong for a synchronous success — reusing it here would fail on A2A. Worth a follow-up to
split that step (see TICKET MATERIAL).

---

## 7. TICKET MATERIAL

* **BR-UC-030 is collected by nothing — the entire governance-binding feature is dead code.**
  `tests/bdd/features/BR-UC-030-manage-governance-binding.feature` (582 lines, 45 scenarios
  including `@T-UC-030-check-conditions` at :288, `@T-UC-030-check-denied` at :297, the
  `governance_decision` BVA outline at :438) is referenced by **no** `scenarios()` call — a
  full-text scan of `tests/**/*.py` for `BR-UC-030` returns nothing. It is not xfailed; it is
  never collected, so it does not even appear in run counts. This is the file that owns the
  spec-correct `check_governance` conditions loop mandated by
  `governance/check-governance-response.json` (`verdict=conditions` ⇒ `conditions` minItems 1
  + `expires_at`) and by `specialisms/governance-aware-seller/index.yaml:23-28`. Either bind it
  with a `test_uc030_*.py` module or delete it — a feature file nobody runs is worse than no
  feature file.

* **Every UC-030 scenario carries the same stale `@source` ref, and all of them cite a request
  schema for response behaviour.** `BR-UC-030-...feature` lines 262, 271, 280, 289, 298, 307,
  … all read
  `@source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/schemas/source/account/sync-governance-request.json`,
  including `@T-UC-030-check-conditions`, whose assertions are entirely about
  `governance/check-governance-response.json`. Re-pin to `v3.1.1` and to the response schema.

* **`storyboard_binding_sweep.py` derives tier from the file path, so it cannot see
  specialism gating.** `scripts/audit/storyboard_binding_sweep.py:253` sets
  `source["tier"]` from the path prefix and only reports an undeclared-specialism finding when
  `tier == "specialisms"` (line 266). `governance_conditions.yaml` lives under
  `protocols/media-buy/scenarios/` but is required **only** by
  `specialisms/governance-aware-seller/index.yaml:23-28`, so the sweep classifies it as
  `protocols` and reports no gate finding — a false negative. Fix: resolve the gate by scanning
  every `index.yaml` `requires_scenarios:` for the scenario's `id:`, not by path prefix. The
  same false negative applies to all four `governance_*` scenarios and to
  `governance_aware_seller/governance_multi_agent_rejected`.

* **`the response should NOT contain "{field}" field` is submitted-envelope-specific but reads
  as generic.** `tests/bdd/steps/domain/uc003_update_media_buy.py:1197-1221` — the success path
  unconditionally calls `_assert_a2a_submitted_task_has_no_artifacts(ctx)`, which asserts the
  A2A task carries no artifacts. That is right for `CreateMediaBuySubmitted` /
  `UpdateMediaBuySubmitted` and wrong for any synchronous success, so the step silently cannot
  be reused for absence checks on a normal 200. Split it into a submitted-envelope variant and
  a plain wire-absence variant (the latter is the step proposed in §6, which should then move to
  a generic module).

* **`then_response_schema_valid` runs no validator** — pre-existing, listed in the brief. It is
  the single check the `governance_conditions` storyboard grades
  (`validations: - check: response_schema`, governance_conditions.yaml:202-204), so as long as
  it is a no-op we cannot claim the graded check even for the scenarios that *are* on our path.
  Wire it to `tests/helpers/pinned_schema.py::validate_against_pinned_schema` and re-vendor
  `tests/fixtures/adcp_schemas_pinned/` from `v3.1.1` (currently `04f59d2d5`).

* **No top-level `status` on responses** — pre-existing, listed in the brief.
  `core/protocol-envelope.json` `"required": ["status"]` with the normative note *"Agents
  shipping responses without a top-level `status` are non-conformant regardless of whether the
  task body schema would otherwise validate."* Blocks any real `response_schema` grading.

---

## 8. Risks

* **The scenario, as rewritten, is a negative-contract assertion.** It proves the three
  governance field names never appear on the create_media_buy wire. That is honest and it is
  green, but it is modest — it grades a boundary, not a behaviour. I chose it deliberately:
  the actual behaviour (`check_governance` → conditions → re-check) is `not_applicable` for us
  at 3.1.1, and inventing a green stand-in for it would be exactly the "built inverse to the
  spec" failure this sweep exists to undo. If the lead would rather this scenario simply be
  retagged and left dormant, that is defensible too — §5's rewrite is the more useful option,
  not the only correct one.
* **Not verified: the `@source` footer format with a `phase=` segment.** The sweep's regex
  (`scripts/audit/storyboard_binding_sweep.py:36`) documents
  `@source repo=<repo> ref=<ref> [phase=<phase>] path=<path>[#L..]`, and the phase matcher looks
  for `'<id> phase:'` / `'phase=<id>'`. I did not re-run the sweep against my proposed footer —
  the sweep reads scenarios out of the working tree and I reverted my edits before running it.
  Someone should re-run `storyboard_binding_sweep.py` after the footer lands to confirm it
  moves this scenario out of bucket **B**.
* **Multiple `@source` lines on one scenario** — I emitted four (one storyboard, three schemas).
  The regex is per-line and the sweep collects `binding.sources` as a list, so this parses; but
  no existing scenario in the tree does it, so the reviewers' expectations may differ. Collapsing
  to the single storyboard line loses the schema provenance that is doing most of the work here.
* **Renaming `_UC002_MANUAL_APPROVAL_WIRED`** — I did not do it in the verified run (I only added
  the tag). If the lead wants the rename, it needs a re-run; the tag addition alone is what I
  measured green.
* **I did not check whether `docs/test-obligations/bdd-traceability.yaml:1863` wants updating.**
  The opaque tag is unchanged so the entry still resolves, but its `upstream_refs:
  ["BR-UC-002-main"]` was already wrong for a governance scenario and is now wrong in a
  different way.
* **3.1.8 / HEAD drift, noted only.** `dist/compliance/` carries 3.1.2–3.1.8. I did not read
  them. If governance-aware-seller's `requires_scenarios` changed after 3.1.1, this verdict
  could move at the next pin bump — but 3.1.1 is the pin and 3.1.1 is what I graded.

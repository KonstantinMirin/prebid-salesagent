# Re-ground `@T-UC-002-storyboard-governance-denied` against AdCP 3.1.1

Scenario: `tests/bdd/features/BR-UC-002-create-media-buy.feature:2649`
Title: "Governance denied -- seller rejects the buy with GOVERNANCE_DENIED and propagates denial rationale"

---

## 1. VERDICT

**NOT GRADED — undeclared gate.**

The behaviour *is* graded at 3.1.1 (a real `validations:` entry exists, quoted below), but the
storyboard that grades it is **capability-gated on `media_buy.governance_aware: true`**, which this
seller does not declare. The 3.1.1 capability schema is explicit that a non-declaring seller is
skipped rather than failed:

> `governance_aware` — "…When false or absent, conformance runners skip those storyboards - a seller
> that does not implement outbound governance consultation is not expected to produce
> GOVERNANCE_DENIED."
> — `static/schemas/source/protocol/get-adcp-capabilities-response.json`, `properties.media_buy.properties.governance_aware.description` @ `v3.1.1`

Our declaration (`src/core/tools/capabilities.py:249-275`) builds `MediaBuy(portfolio=…, features=…,
execution=…)` and never sets `governance_aware`; the SDK default is `False` (verified:
`MediaBuy().governance_aware is False`, and it *is* emitted in `model_dump`). We also declare
`specialisms=[sales_non_guaranteed]` only — not `governance-aware-seller`, the specialism that pulls
this scenario into grading.

⇒ `@storyboard-v3.1` is **unjustified**. Retag to `@schema-v3.1`. Keep `@T-UC-002-storyboard-governance-denied`
(referenced from `docs/test-obligations/bdd-traceability.yaml`).

Two independent confirmations that we are not on this path:

- `GOVERNANCE_DENIED` appears **nowhere** in `src/` (`grep -rn "GOVERNANCE_DENIED" src/` → 0 hits).
- `sync_governance` — a `required_tools` entry of the storyboard — **is not implemented**. `src/core/main.py:352`
  registers `sync_accounts` only; there is no `sync_governance` or `check_governance` tool anywhere in `src/`.
  `governance_agents` exists solely as a persisted account field (`src/core/database/models.py:827`,
  round-tripped in `src/core/tools/accounts.py:70,255,586,629`) — stored, never consulted.

---

## 2. Real binding at 3.1.1

### What the footer currently points at (wrong twice)

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/governance_denied_recovery.yaml
```

1. **Stale ref.** `04f59d2d5` is an ancestor of `beta.3`, older than our own 3.1.1 pin (`v3.1.1` = `467fd93d7`).
2. **Off-by-one path.** It cites `governance_denied_recovery.yaml` — the *next* scenario's storyboard.
   The scenario's own prose line names the truth: `# governance_denied: seller surfaces governance denial as a structured error`.

### The real file

`dist/compliance/3.1.1/domains/media-buy/scenarios/governance_denied.yaml`
(id `media_buy_seller/governance_denied`; byte-identical to the `protocols/media-buy/` alias in the
same dist tree and to the source form `static/compliance/source/protocols/media-buy/scenarios/governance_denied.yaml` @ `v3.1.1` — verified by `diff`).

**Tier:** authored under `domains/` (media-buy domain baseline), self-gated by `requires_capability`,
and pulled into grading by the `specialisms/governance-aware-seller` bundle
(`specialisms/governance-aware-seller/index.yaml:24-28`, `requires_scenarios: … media_buy_seller/governance_denied`).
So it is a **domain-tier scenario behind a specialism-tier gate** — not universal, not protocol-tier.

The gate, verbatim (`governance_denied.yaml:15-22`):

```yaml
# Capability gate: this scenario asserts the seller produces GOVERNANCE_DENIED
# after consulting a registered governance agent, so it runs only for sellers
# that declare media_buy.governance_aware: true. Sellers without outbound
# governance consultation grade not_applicable rather than false-failing on a
# denial they have no mechanism to produce.
requires_capability:
  path: media_buy.governance_aware
  equals: true
```

### The graded `validations:` block — verbatim

Phase `buy_denied`, step `create_media_buy_denied`, **`governance_denied.yaml:236-239`**:

```yaml
        validations:
          - check: error_code
            value: "GOVERNANCE_DENIED"
            description: "Error code indicates governance denial — Case-2 wire placement: create_media_buy has no rejection arm, so GOVERNANCE_DENIED surfaces via errors[].code or adcp_error.code (per the two-layer model in error-handling.mdx)"
```

That is the **only** graded assertion on the denial step. Everything else on that step
(`governance_denied.yaml:206-217`) is `expected:` prose — narrative, not graded. In particular the
prose demands `adcp_error.code` **and** `errors[].code` **and** flipped transport failure markers, but
the single `check: error_code` is what a runner grades.

Also graded on the same scenario (setup phases, all `check: response_schema` / `field_present`):
`sync_plans` (l.100-102), `sync_accounts` (l.125-130), `sync_governance` (l.154-156),
`get_products` (l.188-193). Three of those five graded steps need tools we do not implement.

**Flow direction — this is the biggest correction.** In the storyboard the **seller** is the party that
consults governance: the buyer registers a governance agent via `sync_governance` (phase `seller_setup`,
l.132-156), then the seller calls `check_governance` outbound before committing spend
(`governance-aware-seller/index.yaml` narrative). The buyer never attaches a decision to
`create_media_buy`. Our Gherkin has it backwards.

---

## 3. Schema constraints at 3.1.1

### a) `GOVERNANCE_DENIED` is in the enum — 92 codes

`static/schemas/source/enums/error-code.json` @ `v3.1.1` contains `GOVERNANCE_DENIED` (and
`GOVERNANCE_UNAVAILABLE`). `enumMetadata`:

```json
"GOVERNANCE_DENIED": {
  "recovery": "correctable",
  "suggestion": "restructure the buy, escalate to human spending authority, or contact the governance agent for details"
}
```

`enumDescriptions.GOVERNANCE_DENIED` carries the normative wire-placement rule, verbatim (excerpt):

> "Sellers MUST place the denial in the task's structured rejection arm when one exists (e.g.,
> `acquire_rights` → `AcquireRightsRejected`, `creative_approval` → `CreativeRejected`); otherwise in
> `errors[]` + `adcp_error`. … **2. Task response has no rejection arm (e.g., `create_media_buy` returns
> Success / Error / Submitted arms only). The seller populates `errors[].code: GOVERNANCE_DENIED` in the
> payload AND `adcp_error.code: GOVERNANCE_DENIED` on the envelope per the two-layer model … Transport-level
> failure markers DO flip in this case (HTTP 4xx, MCP `isError: true`, A2A `failed`)** … `GOVERNANCE_DENIED`
> is reserved for verdicts received from a reachable governance agent; if the governance call itself failed
> (timeout, network, config error), use `GOVERNANCE_UNAVAILABLE` instead."

Note the code vocabulary is **open**, not a closed enum — `core/error.json` `code`: `"type": "string",
"minLength": 1, "maxLength": 64` with "the standard codes published in `enums/error-code.json` are
documentary". So the enum does not by itself oblige us to emit the code.

### b) `create_media_buy` genuinely has no rejection arm — confirmed against the schema

`static/schemas/source/media-buy/create-media-buy-response.json` @ `v3.1.1`, `oneOf` arms:

| arm | `required` |
|---|---|
| `CreateMediaBuySuccess` | `["media_buy_id", "confirmed_at", "revision", "packages"]` |
| `CreateMediaBuyError` | `["errors"]` |
| `CreateMediaBuySubmitted` | `["status", "task_id"]` |

`CreateMediaBuyError` verbatim constraints:

```json
"errors": { "type": "array", "items": { "$ref": "/schemas/core/error.json" }, "minItems": 1 },
"required": ["errors"],
"not": { "anyOf": [
  { "required": ["media_buy_id"] },
  { "required": ["packages"] },
  { "required": ["sandbox"] },
  { "properties": { "status": { "const": "submitted" } }, "required": ["status"] } ] }
```

So a denial response MUST carry `errors[]` (≥1) and MUST NOT carry `media_buy_id`, `packages`, `sandbox`,
or `status: submitted`. Case-2 of the wire-placement rule is confirmed by the schema, not just prose.

### c) Envelope

`core/protocol-envelope.json` @ `v3.1.1`: `"required": ["status"]` — "Agents shipping responses without a
top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate."
`adcp_error` is `$ref: /schemas/core/error.json` and is the envelope layer of the two-layer model:
"a fatal task failure SHOULD populate both this envelope-level field AND the payload's `errors[]` array".
`create-media-buy-response.json` `allOf`-refs both `core/version-envelope.json` and `core/protocol-envelope.json`.

### d) `governance_decision` does not exist at 3.1.1

`git grep -l governance_decision v3.1.1 -- static/schemas/` → **zero hits**.
`create-media-buy-request.json` @ `v3.1.1` properties are:
`idempotency_key, plan_id, account, proposal_id, total_budget, packages, brand, advertiser_industry,
invoice_recipient, io_acceptance, po_number, agency_estimate_number, start_time, end_time, paused,
push_notification_config, reporting_webhook, artifact_webhook, context, ext`
(`required: [idempotency_key, account, brand, start_time, end_time]`).

The 3.1.1 governance carriers are: `plan_id` on the request, `governance_context` (JWS) on the envelope,
and out-of-band `check_governance`. The decision enum is `enums/governance-decision.json`:
`["approved", "denied", "conditions"]` — **lowercase**, three values, and it is the return of
`check_governance`, never a request field.

---

## 4. Conflicts and what the scenario gets wrong

Schema vs storyboard: **no conflict on substance** — the storyboard's Case-2 prose and the response
schema's three-arm `oneOf` agree. The schema is stricter and wins on shape (`minItems: 1`, the `not`
block); the storyboard adds only the ungraded envelope/transport-marker prose.

What the current Gherkin gets wrong:

1. **Inverted flow (the serious one).** `Given the buyer's governance agent has returned decision "DENIED"` /
   `And the buyer attaches the governance_decision payload to the create_media_buy request` describes a
   buyer-supplied decision payload. At 3.1.1 the **seller** consults a registered governance agent; there is
   no `governance_decision` request field in any 3.1.1 schema. This is exactly the failure mode CLAUDE.md's
   spec-grounding gate warns about — a feature designed inverse to the spec.
2. **Wrong decision vocabulary.** `"DENIED"` uppercase; the 3.1.1 enum is `denied` lowercase.
3. **Fictional `@source`.** Stale ref *and* off-by-one path (§2).
4. **Unjustified `@storyboard-v3.1`.** Capability-gated on something we do not declare (§1).
5. **Wire assertion under-specified.** `And the error code should be "GOVERNANCE_DENIED"` reads a single
   layer. Case-2 mandates `errors[].code` **and** `adcp_error.code`, plus `errors` `minItems: 1` and the
   `not`-block exclusions. Our generic step `then_error.py:270` resolves one code, so even if production
   emitted the denial this assertion would under-grade it.
6. **Vacuous last Then.** `And the error details should include the denial reason from the governance decision`
   matches `then_error.py:760 @then(parsers.parse("the error details should include {key} {value}"))` only by
   accident of loose `{key} {value}` parsing — `key="the denial reason from the governance"`,
   `value="decision"`. It asserts nothing meaningful about a denial rationale.
7. **Missing the setup the storyboard grades.** No `sync_governance` registration step; the graded storyboard
   has four setup steps before the denial.

**Current execution state — dormant, not passing.** Verified by running:
`test_governance_denied__seller_rejects_the_buy_with_governance_denied_and_propagates_denial_rationale[a2a|mcp|rest]`
→ `XFAIL — "UC-002 harness not yet wired for non-extension scenarios"`. The blanket xfail is
`tests/bdd/conftest.py:3282`; the scenario's tags match none of the wired branches (`@account`,
`T-UC-002-ext-*`, `nfr-highvalue`, `_UC002_IDEMPOTENCY_WIRED`, `_UC002_MANUAL_APPROVAL_WIRED`).
Its Given/When steps have **no definitions at all** (`rg "governance agent has returned decision" tests/bdd/steps/`
→ 0 hits); the blanket xfail is what hides that. Note this regime also swallows the UC-002 main-flow
scenario — nothing in this feature file is currently executing outside the wired tag sets.

---

## 5. Proposed Gherkin (GREEN)

Replaces the scenario at `BR-UC-002-create-media-buy.feature:2649-2664`.

Design: since we do not declare `media_buy.governance_aware`, the honest 3.1.1-conformant assertion is
the **conformance-path guard** — a buy that a governance plan would deny is created on its merits, and
no governance-sourced code appears on either error layer. Parametrized over the two governance codes a
gated seller would be graded on. This passes today *and* would pass if wired; it turns red the moment
someone adds outbound governance consultation without also declaring the capability, which is exactly
the regression worth catching. The graded denial behaviour itself is in §7.

```gherkin
  # 3.1.1: `media_buy.governance_aware` defaults to false and this seller does not declare it
  # (src/core/tools/capabilities.py builds MediaBuy without the field). Per
  # get-adcp-capabilities-response.json, a non-declaring seller is skipped -- not failed -- on
  # media_buy_seller/governance_denied, so this is a schema-level conformance-path guard, not a
  # storyboard-graded scenario. Wiring the real denial contract is tracked in the follow-up issues
  # filed alongside this re-pin.
  @T-UC-002-storyboard-governance-denied @schema-v3.1 @v3-1 @governance @governance-decision @rejection
  Scenario Outline: Governance <verdict> is off this seller's conformance path -- create_media_buy never emits <gated_error_code>
    Given the tenant is configured for auto-approval
    And a valid create_media_buy request
    And the account exists and is active
    And the ad server adapter is available
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And the response status should be "completed"
    And the response should include a "media_buy_id"
    And the response should NOT have an "errors" field
    And the response should NOT carry error code "<gated_error_code>" on the payload or the envelope
    # 3.1.1 error-code.json enumDescriptions.GOVERNANCE_DENIED, Case-2: create_media_buy's oneOf is
    # Success / Error / Submitted with no rejection arm, so a gated seller would place the denial in
    # errors[].code AND adcp_error.code and flip transport failure markers. We consult no governance
    # agent (no sync_governance / check_governance tool in src/), so neither code can appear.
    # GOVERNANCE_UNAVAILABLE is the sibling code for an unreachable agent -- same reasoning.
    # governance_denied: seller surfaces governance denial as a structured error
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/governance_denied.yaml phase=buy_denied step=create_media_buy_denied

    Examples:
      | verdict     | gated_error_code       |
      | denied      | GOVERNANCE_DENIED      |
      | unreachable | GOVERNANCE_UNAVAILABLE |
```

Notes on the footer: the `dist` form of the same file is
`dist/compliance/3.1.1/domains/media-buy/scenarios/governance_denied.yaml` (byte-identical). I cited the
`static/compliance/source/...` path because that is the form every other footer in this feature file uses
and it resolves at `v3.1.1`. Adding `phase=`/`step=` makes the off-by-one class of defect detectable
mechanically next time.

**Not included, deliberately** (would be red — see §7): any assertion that we emit `GOVERNANCE_DENIED`,
populate `adcp_error`, propagate denial findings, or accept a `governance_decision`/`plan_id`-driven
governance consultation.

---

## 6. Step inventory

**Existing — reused as-is (9 of 10):**

| Step | Definition |
|---|---|
| `Given the tenant is configured for auto-approval` | `tests/bdd/steps/domain/uc002_create_media_buy.py:1451` |
| `And a valid create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:104` |
| `And the account exists and is active` | `tests/bdd/steps/domain/uc002_create_media_buy.py:286` |
| `And the ad server adapter is available` | `tests/bdd/steps/domain/uc002_create_media_buy.py:1641` |
| `When the Buyer Agent sends the create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:713` |
| `Then the response should succeed` | `tests/bdd/steps/generic/then_media_buy.py:18` |
| `And the response status should be "{status}"` | `tests/bdd/steps/generic/then_success.py:40` |
| `And the response should include a "{field}"` | `tests/bdd/steps/generic/then_media_buy.py:56` |
| `And the response should NOT have an "errors" field` | `tests/bdd/steps/generic/then_media_buy.py:638` |

**New — exactly one**, to add to `tests/bdd/steps/generic/then_error.py` (it already owns `_wire_code`
and the wire-envelope helpers):

```python
@then(parsers.parse('the response should NOT carry error code "{code}" on the payload or the envelope'))
def then_no_error_code_on_either_layer(ctx: dict, code: str) -> None:
    """Assert `code` appears on neither error layer of the two-layer model.

    3.1.1 core/protocol-envelope.json puts fatal failures on BOTH `adcp_error`
    (envelope) and payload `errors[]`; a single-layer check under-grades. Reads
    the real wire envelope when one was captured, and the payload errors array
    otherwise (IMPL / no-wire scenarios).
    """
    observed: set[str] = set()

    envelope_code = _wire_code(ctx)
    if envelope_code:
        observed.add(envelope_code)

    for source in (ctx.get("error_response"), ctx.get("response")):
        if source is None:
            continue
        inner = getattr(source, "response", source)
        errors = inner.get("errors") if isinstance(inner, dict) else getattr(inner, "errors", None)
        for err in errors or []:
            err_code = err.get("code") if isinstance(err, dict) else getattr(err, "code", None)
            if err_code:
                observed.add(err_code)

    assert code not in observed, (
        f"Expected no {code} on either error layer (adcp_error / errors[]), "
        f"but the response carried: {sorted(observed)}"
    )
```

Guard compliance: the assertion is `assert code not in observed` — a `Compare`, so
`test_architecture_bdd_no_trivial_assertions.py::_assert_is_meaningful` accepts it; not a `pass`/`_pending()`
body, so `test_architecture_bdd_no_pass_steps.py` is satisfied; it reads `ctx` keys directly with no
`ctx.get("env")` / `hasattr(env, …)`, so `test_architecture_bdd_no_silent_env.py` is satisfied. It has a
distinct body, so no `test_architecture_bdd_no_duplicate_steps.py` collision.

**Retired step phrasings (no definitions existed; nothing to delete):**
`the buyer's governance agent has returned decision "…" with a denial reason`,
`the buyer attaches the governance_decision payload to the create_media_buy request`,
`the Buyer Agent sends create_media_buy with the governance_decision payload`.
Sibling scenarios `governance-approved`, `governance-with-conditions` and `governance-denied-recovery`
use the same fictional `governance_decision` phrasings — the peer agents on those scenarios should retire
them consistently, or all four will keep implying a request field that does not exist at 3.1.1.

---

## 7. TICKET MATERIAL

Each of these is a separate GitHub issue; none can land green in this baseline PR.

- **`create_media_buy` never emits `GOVERNANCE_DENIED`.** `grep -rn "GOVERNANCE_DENIED" src/` → 0 hits;
  `src/core/tools/media_buy_create.py` has no governance branch. AdCP 3.1.1
  `enums/error-code.json` `enumDescriptions.GOVERNANCE_DENIED` Case-2 mandates, for tasks with no rejection
  arm, `errors[].code: GOVERNANCE_DENIED` in the payload **and** `adcp_error.code: GOVERNANCE_DENIED` on the
  envelope, with transport failure markers flipped. Graded by
  `dist/compliance/3.1.1/domains/media-buy/scenarios/governance_denied.yaml:236-239` (`check: error_code`,
  `value: "GOVERNANCE_DENIED"`) — gated on declaring `media_buy.governance_aware: true`.

- **No `sync_governance` tool.** `src/core/main.py:352` registers `sync_accounts` only; `sync_governance`
  does not exist in `src/`. It is a `required_tools` entry of `governance_denied.yaml:10-13` and a graded
  step at `governance_denied.yaml:132-156` (`check: response_schema` against
  `account/sync-governance-response.json`). Request/response schemas exist at
  `static/schemas/source/account/sync-governance-{request,response}.json` @ `v3.1.1`. This also blocks the
  whole of `BR-UC-030-manage-governance-binding.feature`, which is authored against the tool.

- **No outbound `check_governance` call.** `governance_agents` is persisted
  (`src/core/database/models.py:827`, round-tripped in `src/core/tools/accounts.py:70,255,299-305,586,629`)
  and then never read for a decision. `specialisms/governance-aware-seller/index.yaml` requires the seller to
  "call `check_governance` on that registered agent before confirming a spend-committing request". Schemas:
  `static/schemas/source/governance/check-governance-{request,response}.json` @ `v3.1.1`; decision enum
  `enums/governance-decision.json` = `["approved", "denied", "conditions"]`.

- **`media_buy.governance_aware` is never declared, and there is no test asserting the declaration.**
  `src/core/tools/capabilities.py:249-253` constructs `MediaBuy(portfolio=…, features=…, execution=…)`;
  the SDK default is `False`. That default is currently *correct*, but nothing pins it, so wiring governance
  consultation without flipping the flag would silently leave us mis-declared. The natural home is UC-010,
  which has no step module at all (`tests/bdd/steps/domain/` has no `uc010_*.py`) — every scenario in
  `BR-UC-010-discover-seller-capabilities.feature` is dormant, and there is no `get_adcp_capabilities`
  harness env under `tests/harness/`. Filing as: add a capabilities harness env + a UC-010 scenario asserting
  `media_buy.governance_aware == false` while we do not implement consultation.

- **`GOVERNANCE_UNAVAILABLE` has no production path either.** 3.1.1
  `enumDescriptions.GOVERNANCE_UNAVAILABLE`: "Sellers MUST place this code in `errors[]` + `adcp_error`
  (never a structured rejection arm) and flip transport-level failure markers (HTTP 5xx, MCP `isError: true`,
  A2A `failed`) … the seller MUST NOT proceed with the media buy without a valid decision." Fail-closed on an
  unreachable governance agent is a distinct requirement from the denial path and needs its own scenario once
  consultation exists.

- **UC-002's blanket xfail hides missing step definitions.** `tests/bdd/conftest.py:3282`
  (`pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")`) catches every scenario whose
  tags miss the wired branches — including the main happy-path scenario at
  `BR-UC-002-create-media-buy.feature:35`. A scenario whose Given steps have no definitions at all (this one,
  before the rewrite) is indistinguishable from one that is merely un-wired. Filing as: make the blanket
  branch assert that every step in the scenario resolves before xfailing, so undefined-step scenarios are
  reported distinctly from un-wired ones.

- **`the error details should include {key} {value}` is too loosely parsed.**
  `tests/bdd/steps/generic/then_error.py:760` accepts free prose as `{key} {value}`, which is how
  `And the error details should include the denial reason from the governance decision` "matched" a step at
  all. Any Gherkin sentence ending in two words binds to it. Filing as: tighten to a quoted-key form
  (the `:775` variant already quotes the value) and re-audit its call sites.

---

## 8. Risks

- **Could not execute the proposed scenario.** UC-002's `_harness_env` blanket-xfails every scenario outside
  the wired tag sets (`conftest.py:3282`), and my rewrite deliberately does not change the harness routing
  tags — that would be a wiring change, not a re-pin. So the rewrite is green in the trivial sense (it cannot
  go red), and my claim that it would *also* pass if wired rests on reading `src/` plus the fact that its
  Given/When block is the same one the wired `@account` and `T-UC-002-ext-*` branches drive through
  `MediaBuyCreateEnv`. Not execution-verified. If the team wants it live, tag it `@account` in a follow-up and
  run `tox -e bdd -- -k governance` — do not do that blind in the baseline PR.
- **`the response status should be "completed"`** — I took this from the main-flow scenario
  (`feature:51`), which is itself dormant, so its greenness is inferred, not observed. If the envelope
  `status` gap in the known-gaps list bites here, drop that one line; the remaining Thens stand alone.
- **Negative-assertion shape.** Four of five Thens are positive; the parametrized one is negative by nature.
  A conformance-path guard is inherently "this must not appear". I judged that better than deleting the
  scenario, but reviewers may reasonably prefer to fold it into UC-010 as a capability-declaration assertion
  once a capabilities harness exists.
- **Sibling coordination.** `governance-approved`, `governance-with-conditions` and `governance-denied-recovery`
  are owned by peer agents and share the same fictional `governance_decision` premise and the same
  `media_buy.governance_aware` gate. All four should reach the same verdict; if they diverge, the feature file
  will assert both that we do and do not consult governance.
- **Drift note only (not authority).** At 3.1.8/HEAD the `domains/` vs `protocols/` dist layout has settled
  differently; I cited the `static/compliance/source/protocols/...` form because it resolves at `v3.1.1` and
  matches the existing footer convention in this file. If a later pin bump renames it, the `phase=`/`step=`
  qualifiers I added still identify the graded step unambiguously.
- **Unverified:** whether the `adcp==6.6.0` SDK's `MediaBuy` serializes `governance_aware: false` on the wire
  for all transports (I verified `model_dump` includes it in-process only), and whether
  `tests/fixtures/adcp_schemas_pinned/` — vendored at `04f59d2d5`, per the known-gaps list — would even
  contain the 3.1.1 `governance_aware` field if a schema validator were wired.

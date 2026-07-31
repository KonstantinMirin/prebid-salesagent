# Re-pin proposal — `@T-UC-002-storyboard-governance-approved`

Scenario: `tests/bdd/features/BR-UC-002-create-media-buy.feature:2619-2632`
Title: "Governance approved -- seller creates the buy and propagates the governance decision payload"

---

## 1. VERDICT

**NOT GRADED — undeclared gate.**

`media_buy_seller/governance_approved` is required by exactly one index in the whole
3.1.1 compliance tree: `specialisms/governance-aware-seller/index.yaml:24`. We declare
`specialisms=[AdcpSpecialism.sales_non_guaranteed]`
(`src/core/tools/capabilities.py:100` and `:272`) and nothing else. The specialism index
states the consequence in its own words:

> `specialisms/governance-aware-seller/index.yaml:64-66`
> "Sellers that do not claim this specialism are graded `not_applicable` on the
> `check_governance` scenarios rather than failed."

So this behaviour is **not on our conformance path at 3.1.1**. Per BRIEF question 4 the
`@storyboard-v3.1` tag is unjustified and must become `@schema-v3.1`. The opaque
`@T-UC-002-storyboard-governance-approved` identifier stays (referenced from
`docs/test-obligations/bdd-traceability.yaml:1857`).

Two independent facts reinforce the verdict, either of which alone would sink the current
Gherkin:

* **Even inside the gate, the create step grades only `response_schema`** — no governance
  echo is graded at the step level (see §2).
* **The scenario's premise is schema-impossible at 3.1.1.** There is no
  `governance_decision` field anywhere in `static/schemas/source/` at v3.1.1, and the
  direction of the handshake is inverted (see §3/§4).

---

## 2. Real binding at 3.1.1

**Current footer points at (WRONG):**
`static/compliance/source/protocols/media-buy/scenarios/governance_conditions.yaml`
at `ref=v3.1-04f59d2d5 commit=04f59d2d5` — the next scenario's storyboard (the proven
off-by-one), pinned to a commit that is an ancestor of beta.3, i.e. older than our own
3.1.1 pin.

**Real file (verified on disk):**
`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/governance_approved.yaml`
(byte-identical duplicate at `domains/media-buy/scenarios/governance_approved.yaml`;
the tier that *gates* it is `specialisms/`, see §1).

The scenario has 3 phases / 5 steps. The one this BDD scenario claims to grade:

```yaml
# protocols/media-buy/scenarios/governance_approved.yaml:193-223
      - id: create_media_buy
        title: "Create buy (governance approves)"
        task: create_media_buy
        schema_ref: "media-buy/create-media-buy-request.json"
        response_schema_ref: "media-buy/create-media-buy-response.json"
        doc_ref: "/media-buy/task-reference/create_media_buy"
        comply_scenario: create_media_buy
        stateful: true
        expected: |
          The buy succeeds — governance approved because the $25K buy is within
          the plan's $100K budget.
        ...
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
```

**That is the entire graded block for the create step — one `response_schema` check.**
"The buy succeeds — governance approved" is under `expected:`, i.e. narrative prose, not
graded. The other four steps grade `response_schema` plus one `field_present` on
`accounts[0].account_id` (`:128-130`) and one on `products` (`:189-191`).

The governance semantics are graded elsewhere, and only for claimants — as **cross-step
invariants declared on the specialism**, not on this scenario:

```yaml
# specialisms/governance-aware-seller/index.yaml:18-21
invariants:
  - governance.denial_blocks_mutation
  - status.monotonic
```

**Required tools** for the scenario are `sync_governance`, `get_products`,
`create_media_buy` (`:7-10`). We implement none of `sync_governance` /
`check_governance` / `sync_plans` — `grep -rn "check_governance\|sync_governance" src/`
returns nothing but `Account.governance_agents` storage
(`src/core/database/models.py:827`, `src/core/tools/accounts.py`). We support governance
agent **registration** and not **consultation**, which is precisely the split the
specialism narrative draws (`index.yaml:36-44`).

---

## 3. Schema constraints at 3.1.1

**(a) `governance_decision` does not exist.** Exhaustive scan of every file in
`git show v3.1.1:static/schemas/source/` for the string `governance_decision`: **zero
hits.** The scenario's central noun is not a protocol concept at 3.1.1.

**(b) The decision enum is lowercase and has three values — `APPROVED_WITH_CONDITIONS`
is not one of them.**

```json
// v3.1.1:static/schemas/source/enums/governance-decision.json
"description": "Outcome of a governance check_governance call. ...
                'conditions' is a flow-control value requiring the caller to
                re-call check_governance after adjusting parameters.",
"type": "string",
"enum": ["approved", "denied", "conditions"]
```

**(c) The 3.1.1 governance surface on the create request is `plan_id`, and the check is
seller→governance-agent, not buyer→seller.**

```json
// v3.1.1:static/schemas/source/media-buy/create-media-buy-request.json:22-25
"plan_id": {
  "type": "string",
  "description": "Campaign governance plan identifier. Required when the account has
                  governance_agents. The seller includes this in the committed
                  check_governance request so the governance agent can validate
                  against the correct plan.",
  "x-entity": "governance_plan"
}
```

**(d) The artefact that actually travels back to the buyer is `governance_context`, on
the protocol envelope — not a "governance_decision payload".**

```json
// v3.1.1:static/schemas/source/core/protocol-envelope.json
"governance_context": {
  "type": "string",
  "description": "Governance context token issued by the account's governance agent
                  during check_governance. Buyers attach it to governed purchase
                  requests (media buys, rights acquisitions, signal activations,
                  creative services); sellers persist it and include it on all
                  subsequent governance calls for that action's lifecycle. ...
                  governance agents MUST emit a compact JWS per the AdCP JWS profile
                  ... In 3.1 all sellers MUST verify.",
  "minLength": 1, "maxLength": 4096, "pattern": "^[\\x20-\\x7E]+$"
}
```

`create-media-buy-response.json:6-13` `allOf`-refs `core/protocol-envelope.json`, so
`governance_context` is a legal (optional) response-envelope field on create_media_buy —
and `protocol-envelope.json` `"required": ["status"]` applies.

**(e) The verdict itself never rides on create_media_buy.** It rides on
`governance/check-governance-response.json`, a *different task on a different agent*, with
`verdict` (renamed from `status` in 3.1), plus conditional requirements: `denied` ⇒
`findings` minItems 1; `approved`/`conditions` ⇒ `expires_at` required; `conditions` ⇒
`conditions` minItems 1.

---

## 4. Conflicts — what the scenario gets wrong

**Schema overrode storyboard once, and it matters:** the specialism narrative
(`governance-aware-seller/index.yaml:50-51`) says the seller "echoes the
`governance_context` token back". The *scenario* storyboard grades nothing of the kind —
its create step grades `response_schema` only. Where the two disagree about what is
enforceable, **the 3.1.1 schema wins**: `governance_context` is an optional envelope
field (`protocol-envelope.json`), not a required create-response field, so no echo is
mandated by the schema and none is graded by the storyboard. The narrative is aspiration,
not contract.

Everything the current Gherkin asserts is wrong or vacuous:

| Current line | Problem |
|---|---|
| `Given the buyer's governance agent has returned decision "APPROVED"` | Direction inverted. At 3.1.1 the **seller** calls `check_governance` on the account's registered agent (`governance_approved.yaml:16-18`). The buyer never hands the seller a decision. |
| `And the buyer attaches the governance_decision payload to the create_media_buy request` | `governance_decision` is not a field in any 3.1.1 schema. The request-side governance field is `plan_id`; the envelope-side artefact is `governance_context`. |
| `Then the response should carry status "active" or "pending_start"` | Two problems. (1) "X or Y" is not a value comparison — it cannot fail meaningfully. (2) At 3.1.1 top-level `status` is the protocol `TaskStatus` (`completed`), and the domain lifecycle value lives on `media_buy_status`. Asserting a MediaBuyStatus on `status` targets the field the 3.1 deprecation moved off. |
| `And the response should carry the media_buy_id` | Bare existence, no value comparison. |
| `And the response should echo the governance_decision with decision "APPROVED"` | Asserts a field that does not exist in the protocol, with a casing (`APPROVED`) that is not in the enum (`approved`) even for the field that does exist (`verdict`). |
| `# @source ... path=.../governance_conditions.yaml` | Off-by-one, and pinned to `04f59d2d5`, older than our 3.1.1 pin. |
| `@storyboard-v3.1` | Unjustified — undeclared specialism gate. |

**Current status: DORMANT.** No step definition exists for any of these five steps
(`grep -rn "governance_decision" tests/ --include="*.py"` → zero hits), so
`tests/bdd/conftest.py` auto-xfails the scenario on `StepDefinitionNotFoundError`
(`conftest.py:85-99`). It grades nothing today, in either direction.

---

## 5. Proposed Gherkin — GREEN ONLY

Replaces lines 2619-2632. Every Then step below already exists and is already green in
this repo (see §6); the two `wire …` assertions are copied verbatim from the proven
`@T-UC-002-ext-dual-emit` scenario in
`tests/bdd/features/BR-UC-002-media-buy-status-dual-emit.feature:49-54`, which runs the
same `MediaBuyCreateEnv` create flow across all four transports.

The re-grounded subject is our actual, honest 3.1.1 conformance position: **registration
is not consultation.** We store `Account.governance_agents` (UC-011) but do not claim
`governance-aware-seller`, so `create_media_buy` is decided on its own merits and the
seller mints no governance artefact. The outline's varying axis is the account's
governance-registration state — the row pair is exactly what distinguishes a
registration-only seller from a governance-aware one.

```gherkin
  # AdCP 3.1.1 conformance position (re-pinned from a stale, off-by-one @source).
  # `media_buy_seller/governance_approved` is required by exactly ONE index at 3.1.1 —
  # specialisms/governance-aware-seller/index.yaml:24 — and that index states sellers
  # which do not claim the specialism are graded `not_applicable`, not failed
  # (index.yaml:64-66). We declare specialisms=[sales-non-guaranteed] only
  # (src/core/tools/capabilities.py:100,272), so the governance handshake is NOT on our
  # conformance path: hence @schema-v3.1, not @storyboard-v3.1.
  #
  # What IS ours at 3.1.1 is the schema surface. Registration and consultation are
  # deliberately separate layers (governance-aware-seller/index.yaml:36-44): we persist
  # the account's registered governance agent, and we do NOT call check_governance. So a
  # buy for an account WITH a registered governance agent must resolve identically to one
  # WITHOUT — same lifecycle status, same protocol status — and the seller must not mint a
  # governance_context token (core/protocol-envelope.json) it never obtained from a
  # check_governance call it never made.
  @T-UC-002-storyboard-governance-approved @schema-v3.1 @v3-1 @governance @governance-registration
  Scenario Outline: Registered governance agent does not gate create_media_buy for a seller that does not claim governance-aware-seller -- <registration_state>
    Given the tenant is configured for auto-approval
    And a valid create_media_buy request with:
      | field      | value                |
      | account    | account_id "acc-001" |
      | brand      | domain "acme.com"    |
      | start_time | {1 day from now}     |
      | end_time   | {30 days from now}   |
    And the request includes 2 packages with valid product_ids
    And each package has a positive budget meeting minimum spend
    And all packages use the same currency "USD"
    And each package has a valid pricing_option_id
    And the account "acc-001" exists and is active with <registration_state>
    And the ad server adapter is available
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    # Pin the DOMAIN lifecycle value, identical on both rows: a registered governance
    # agent changes nothing, because we never consult it. A regression that started
    # gating on governance_agents would move this off pending_creatives.
    And the wire media_buy_status should be "pending_creatives"
    # Pin the PROTOCOL value: core/protocol-envelope.json required:["status"]; synchronous
    # create success is TaskStatus 'completed' (a different namespace from media_buy_status).
    And the wire status should be "completed"
    # core/protocol-envelope.json: governance_context is issued by the governance agent
    # during check_governance and only then carried by the seller. We make no such call,
    # so emitting one would be a fabricated audit token.
    And the response should NOT contain "governance_context" field
    # Not a field in ANY 3.1.1 schema (exhaustive scan of static/schemas/source/): the
    # buyer-attaches-a-decision model this scenario previously asserted does not exist.
    And the response should NOT contain "governance_decision" field

    Examples: account governance registration state
      | registration_state             |
      | no registered governance agent |
      | a registered governance agent  |
```

---

## 6. Step inventory

**Existing — reused unchanged (all currently green):**

| Step | Owner |
|---|---|
| `Given the tenant is configured for auto-approval` | `tests/bdd/steps/domain/uc002_create_media_buy.py:1451` |
| `Given a valid create_media_buy request with:` (datatable) | `tests/bdd/steps/generic/given_media_buy.py:398` |
| `And the request includes 2 packages with valid product_ids` | `uc002_create_media_buy.py:1627` |
| `And each package has a positive budget meeting minimum spend` | `given_media_buy.py` |
| `And all packages use the same currency "USD"` | `given_media_buy.py` |
| `And each package has a valid pricing_option_id` | `given_media_buy.py` |
| `And the ad server adapter is available` | `uc002_create_media_buy.py:1641` |
| `When the Buyer Agent sends the create_media_buy request` | `uc002_create_media_buy.py:713` |
| `Then the response should succeed` | `uc002_create_media_buy.py:1692` |
| `And the wire media_buy_status should be "{status}"` | `uc003_update_media_buy.py:127` (registered plugin, globally available) |
| `And the wire status should be "{status}"` | `uc003_update_media_buy.py:137` |
| `And the response should NOT contain "{field_name}" field` | `uc003_update_media_buy.py:1197` — reads the REAL wire via `_submitted_wire_dict`, absent-or-null satisfies |

**New — one Given, one conftest entry:**

1. `Given the account "{account_id}" exists and is active with {registration_state}` —
   in `tests/bdd/steps/domain/uc002_create_media_buy.py`, a parametrized sibling of the
   existing `given_account_exists_active` (`:264`). Same `AccountFactory` +
   `AgentAccountAccessFactory` body; when `registration_state` is
   `"a registered governance agent"` it additionally passes
   `governance_agents=[GovernanceAgent(url=..., categories=None).model_dump()]`.
   `Account.governance_agents` is a real `JSONType(model=GovernanceAgent, is_list=True)`
   column (`src/core/database/models.py:827`), and `AccountFactory` forwards kwargs to the
   model (`tests/factories/account.py:12-30`), so no factory change is needed. Build the
   agent dict with the existing helper shape from
   `tests/bdd/steps/domain/uc011_accounts.py:91-108`.
   Raise `ValueError` on an unrecognized `registration_state` so a typo in the Examples
   table fails loudly rather than silently seeding "no agent".

2. **conftest wiring.** The scenario must reach `MediaBuyCreateEnv` with
   `dispatch_mode="create"`. `tests/bdd/conftest.py:3224-3227` currently keys that branch
   on `T-UC-002-ext-` prefix plus two literals. Add a named set beside
   `_UC002_IDEMPOTENCY_WIRED` / `_UC002_MANUAL_APPROVAL_WIRED` (`conftest.py:2806,2816`):

   ```python
   # UC-002 governance-registration scenario wired to MediaBuyCreateEnv: grades that a
   # registered governance agent does not gate create_media_buy for a seller that does
   # not claim the governance-aware-seller specialism (AdCP 3.1.1).
   _UC002_GOVERNANCE_WIRED: set[str] = {"T-UC-002-storyboard-governance-approved"}
   ```

   and OR it into the `dispatch_mode="create"` branch condition. Without this the scenario
   falls through to `pytest.xfail("UC-002 harness not yet wired…")` (`conftest.py:3282`)
   and grades nothing — the exact dormancy this sweep exists to end.

No new marker registration is needed: BDD tags are not listed in `pytest.ini`'s `markers`
block today (`@governance`, `@v3-1`, `@storyboard-v3.1` are all absent) and the suite runs
under `--strict-markers`, so pytest-bdd registers scenario tags itself.

---

## 7. TICKET MATERIAL

Each of these is a real 3.1.1 gap that cannot land green in this baseline PR.

* **`plan_id` is silently dropped at every transport boundary — the buyer's governance
  plan reference never reaches business logic.**
  `create-media-buy-request.json:22-25` (v3.1.1) defines `plan_id` and states it is
  "Required when the account has governance_agents"; `adcp==6.6.0`'s
  `CreateMediaBuyRequest` declares it. Our wrappers enumerate parameters explicitly and
  none declares `plan_id`: MCP `src/core/tools/media_buy_create.py:4373-4420`, A2A/REST
  raw `src/core/tools/media_buy_create.py:4495-4512`, REST body model
  `src/routes/api_v1.py:76-93`. `grep -rn "plan_id" src/` returns zero hits. Consequence
  is transport-divergent, which is itself a Pattern #5 violation: MCP strips it, A2A drops
  it, and REST — where `CreateMediaBuyBody` extends `SalesAgentBaseModel` and CI runs
  `extra="forbid"` (Pattern #7) — **rejects a schema-valid 3.1.1 request outright**. This
  is why the proposed scenario cannot send `plan_id`. Fix: declare `plan_id` on all three
  wrappers, forward it into `CreateMediaBuyRequest`, persist it on the media buy.

* **`governance_context` is not accepted, persisted, or forwarded.**
  `core/protocol-envelope.json` (v3.1.1): "Buyers attach it to governed purchase requests
  … sellers persist it and include it on all subsequent governance calls for that action's
  lifecycle… Sellers MAY verify; sellers that do not verify MUST persist and forward the
  token unchanged so auditors can verify downstream. In 3.1 all sellers MUST verify."
  `grep -rn "governance_context" src/` → zero hits. Same wrapper enumerations as above;
  the same REST `extra="forbid"` rejection applies. Even a seller that never claims
  `governance-aware-seller` is bound by the persist-and-forward clause once a buyer
  attaches a token.

* **No `check_governance` / `sync_governance` / `sync_plans` support — the
  `governance-aware-seller` specialism is unclaimable.**
  `specialisms/governance-aware-seller/index.yaml:6-7` requires tools
  `sync_governance` + `create_media_buy` and `requires_scenarios`
  `governance_approved`, `governance_conditions`, `governance_denied`,
  `governance_denied_recovery`, `governance_multi_agent_rejected` (`:22-27`), enforced by
  invariants `governance.denial_blocks_mutation` and `status.monotonic` (`:18-21`). We
  store `Account.governance_agents` (`src/core/database/models.py:827`) and never call
  them. Until this lands, the three sibling UC-002 governance scenarios
  (`-with-conditions`, `-denied`, `-denied-recovery`, feature lines 2634-2680) are in the
  same position as this one and should get the same `@schema-v3.1` treatment or be
  parked — they are currently dormant with inverted premises and non-enum decision values
  (`APPROVED_WITH_CONDITIONS` is not in `enums/governance-decision.json`).

* **`GOVERNANCE_DENIED` error path is asserted by a sibling scenario and does not exist in
  production.** `@T-UC-002-storyboard-governance-denied` (feature line 2648) expects error
  code `GOVERNANCE_DENIED`; `enums/error-code.json` at v3.1.1 carries governance codes, and
  we emit none of them. Flagged here only so it is not re-discovered — it belongs to that
  scenario's owner, not this one.

* **Pinned schema fixtures are stale for any governance work.**
  `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, which predates the
  3.1 `verdict`-rename (`check-governance-response.json` describes it as "Renamed from
  `status` in 3.1 to free the top-level `status` key for the envelope task-status"). Any
  future governance validation against those fixtures would validate the wrong shape.
  (Already known per BRIEF §"Known production gaps"; cited, not re-filed.)

---

## 8. Risks

* **I could not execute anything.** No test run, no DB. Every green claim is by
  construction: each reused Then step is lifted from a scenario that is already wired and
  green in this repo (`@T-UC-002-ext-dual-emit` for the two `wire …` steps and the whole
  Given block; `@T-UC-002-alt-manual` for `should NOT contain … field`). The one genuinely
  unverified assumption is that adding a *second* account row variant (with
  `governance_agents` populated) does not perturb `MediaBuyCreateEnv` — justified by
  `grep`: nothing in `src/` outside `accounts.py` reads that column.
* **`media_buy_status == "pending_creatives"` is inherited, not independently derived.**
  It is pinned by the dual-emit scenario with the same Given block and the same env; if
  that scenario's value ever changes, this one changes with it. Deliberate — they should
  move together.
* **The `status` vs `media_buy_status` reconciliation is contested inside the 3.1.1 schema
  itself.** `create-media-buy-response.json` says the deprecated top-level `status`
  "MUST carry identical values" to `media_buy_status` during the 3.1 window, while
  `core/protocol-envelope.json` requires top-level `status` to be a `TaskStatus`. The repo
  already resolved this in favour of GA/protocol-envelope
  (`uc002_create_media_buy.py:1724-1774`, `docs/adcp-spec-version.md` "Behavior target vs
  SDK pin"). I follow that resolution; I did not re-litigate it.
* **The `domains/` vs `protocols/` duplicate.**
  `domains/media-buy/scenarios/governance_approved.yaml` and
  `protocols/media-buy/scenarios/governance_approved.yaml` are byte-identical at 3.1.1
  (diffed). I cite the `protocols/` copy because the stale footer used a `protocols/`
  path; the gating tier is `specialisms/` either way, which is what drives the verdict.
* **Drift note only, not authority:** I did not read 3.1.2-3.1.8. If `governance_approved`
  is later promoted out of the specialism into `protocols/media-buy/index.yaml`'s
  `requires_scenarios` (it is absent there at 3.1.1, `index.yaml:9-23`), the verdict flips
  and the tag goes back to `@storyboard-v3.1`. That is a pin-bump decision, not this PR's.
* **`@governance-registration` is a new tag.** It replaces `@governance-decision`, which
  named a field that does not exist. If any tooling greps `@governance-decision`, it will
  stop matching — I found no such consumer (`scripts/audit/storyboard_binding_sweep.py`
  keys on `@storyboard-v3.1`; `scripts/compile_bdd.py` keys on `@T-` and
  `@schema-v<MAJ>.<MIN>`).

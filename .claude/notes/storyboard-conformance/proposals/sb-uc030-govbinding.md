# sb-uc030-govbinding — re-ground `@T-UC-030-storyboard-binding-used-during-create-media-buy`

Scenario: `tests/bdd/features/BR-UC-030-manage-governance-binding.feature:569`
Title: "Governance agent bound via sync_governance is invoked by the seller during create_media_buy"
Cited `@source`: **none** (no footer — derived below).

---

## 1. VERDICT

**NOT GRADED — twice over.**

1. **NOT GRADED — prose only.** At 3.1.1 the assertion "the seller calls `check_governance`
   against the registered URL during `create_media_buy`" appears **exclusively** under
   `narrative:` and `expected:` keys. Every `create_media_buy` step in every storyboard that
   sets up a governance binding grades only `response_schema` / `context` / `context.correlation_id`
   (+ `packages[0].package_id` and `upstream_traffic` in the non-guaranteed specialism). There is
   **no `- check:` anywhere in `dist/compliance/3.1.1/` that observes which governance URL the
   seller called, or that it called one at all.**
2. **NOT GRADED — undeclared gate.** The behaviour is owned by
   `specialisms/governance-aware-seller/`, which we do not declare. That specialism's own
   capability-discovery step grades `specialisms[*] contains "governance-aware-seller"`
   (`specialisms/governance-aware-seller/index.yaml:140-143`), and its narrative states verbatim:
   *"Sellers that do not claim this specialism are graded `not_applicable` on the
   `check_governance` scenarios rather than failed."* We declare
   `specialisms=[sales_non_guaranteed]`, `supported_protocols=[media_buy]`
   (`src/core/tools/capabilities.py:99-100`, `:271-272`) — so all four governance scenarios
   resolve `not_applicable` for us.

**Action: retag `@storyboard-v3.1` → `@schema-v3.1`.** The tag is unjustified on both the
"is it graded" test and the "is it on our conformance path" test. The `@T-UC-030-…` identifier
tag stays (referenced at `docs/test-obligations/bdd-traceability.yaml:15828`).

**A third, harder fact:** the scenario cannot be green in any form that mentions
`check_governance`, because **production has no `check_governance` and no `sync_governance`.**
Registered tools are `list_accounts` and `sync_accounts` only (`src/core/main.py:351-352`).
`governance_agents` exists purely as a persisted passthrough JSON column
(`src/core/database/models.py:827-829`) written through `sync_accounts`
(`src/core/tools/accounts.py:586,629`) and read back through `list_accounts`
(`src/core/tools/accounts.py:70`). Nothing in `src/` ever calls a governance agent.

**And a fourth:** `BR-UC-030-manage-governance-binding.feature` is **entirely dormant.** No
`scenarios()` binding exists for it (`tests/bdd/test_*.py` binds 20 other feature files; none
is UC-030) and there is no `tests/bdd/steps/domain/uc030_*.py`. Not one of the file's ~570
lines executes today. Whatever lands here is inert until someone adds the binding — which is
*not* something this baseline PR should do, because the rest of the file asserts `sync_governance`
behaviour that does not exist.

---

## 2. Real binding at 3.1.1

### What the footer wrongly points at

There is no `@source` footer. The scenario's trailing comment claims its binding in prose:

> `# governance/index.yaml and media-buy/index.yaml governance_setup phases:`

Both halves of that claim are wrong:

- **`governance/index.yaml`** (`domains/governance/index.yaml`, identical to
  `protocols/governance/index.yaml`) is the storyboard for the **governance agent** —
  `interaction_model: media_buy_seller` but `required_tools: [sync_plans, check_governance]`,
  i.e. the *callee* side. It has no `governance_setup` phase. Its `check_governance` steps
  (`:372`, `:447`) are the **buyer calling the governance agent**, not the seller. Wrong actor.
- **`media-buy/index.yaml` `governance_setup`** does exist (`domains/media-buy/index.yaml:204`)
  but grades only the `sync_governance` response shape — nothing about invocation.

### The real, graded surface — registration only

`dist/compliance/3.1.1/domains/media-buy/index.yaml:204-254` (phase `governance_setup`,
step `sync_governance`, validations at **:245-254**):

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-governance-response.json schema"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "media_buy_seller--sync_governance"
            description: "Context correlation_id returned unchanged"
```

The same phase under our declared specialism,
`dist/compliance/3.1.1/specialisms/sales-non-guaranteed/index.yaml:262-304`
(step `sync_governance`, validations at **:292-304**) adds one state assertion:

```yaml
        validations:
          - check: response_schema
            description: "Response matches sync-governance-response.json schema"
          - check: field_value
            path: "accounts[0].status"
            value: "synced"
            description: "Governance agent is registered on the account"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "sales_non_guaranteed--sync_governance"
            description: "Context correlation_id returned unchanged"
```

### The invocation half — ungraded everywhere

The `create_media_buy` step that immediately follows that registration in our own declared
specialism (`specialisms/sales-non-guaranteed/index.yaml:306`, validations at **:365-392**)
grades:

```yaml
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
          - check: field_present
            path: "context"
          - check: field_value
            path: "context.correlation_id"
            value: "sales_non_guaranteed--create_media_buy"
          - check: field_present
            path: "packages[0].package_id"
            description: "Seller assigns package_id — must be echoed in update_media_buy"
          - check: upstream_traffic
            description: "create_media_buy caused upstream traffic creating the campaign"
            min_count: 1
            endpoint_pattern: "POST *"
```

No governance check. The `upstream_traffic` check is deliberately URL-agnostic
(`endpoint_pattern: "POST *"`, comment at `:379-384`: *"the assertion is 'any upstream POST
happened during this step', leaving the specific endpoint to the adopter's upstream stack"*)
— it cannot distinguish a governance call from an ad-server call, so it does not grade our
scenario's claim even accidentally.

Even inside the gated specialism, `domains/media-buy/scenarios/governance_approved.yaml:193`
(`create_media_buy`, validations at **:221-223**) grades **only**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
```

The invocation claim lives only in prose:
- `domains/media-buy/index.yaml:207-208` — *"This tells your platform where to call
  check_governance before confirming media buys."*
- `domains/media-buy/index.yaml:429-432` — *"If the buyer registered governance agents in
  Phase 2, your platform calls check_governance before confirming the buy."*
- `specialisms/governance-aware-seller/index.yaml:72-79` — the composition bullet list.

`upstream_traffic` **is** used with governance endpoint patterns elsewhere
(`domains/brand/scenarios/single_side_trust_extension.yaml:220-228`,
`distributed_brand_resolution.yaml:263-264,340-341`) — proving the storyboard language *can*
grade "which URL did you call". 3.1.1 simply chose not to apply it to the seller→governance
hop. That is the authority; our scenario asserts more than the spec grades.

### Tier ownership (question 3)

| Half of the behaviour | Tier | File | Do we declare the gate? |
|---|---|---|---|
| Registration (`sync_governance` persists one agent per account) | `specialisms/sales-non-guaranteed/` | `:262-304` | **Yes** — `sales_non_guaranteed` |
| Registration (baseline seller flow) | `domains/`+`protocols/media-buy/` | `index.yaml:204-254` | n/a (domain tier) |
| **Invocation (`check_governance` during `create_media_buy`)** | **`specialisms/governance-aware-seller/`** | `index.yaml:23-27` `requires_scenarios` | **No** |
| Invariant `governance.denial_blocks_mutation` | `specialisms/governance-aware-seller/:20-21`, `-spend-authority`, `-delivery-monitor` | | **No** |

`universal/` has nothing governance-related (checked all 38 files).

Note: `sales-non-guaranteed` *does* pull in one governance scenario —
`governance_aware_seller/governance_multi_agent_rejected` (`:27`) — but that grades
`maxItems: 1` rejection on the **request**, not invocation.

---

## 3. Schema constraints at 3.1.1

### `core/account.json` — governance_agents (the read-back contract)

`git show v3.1.1:static/schemas/source/core/account.json`:

```json
"governance_agents": {
  "type": "array",
  "description": "Governance agent endpoint registered on this account. Exactly one entry per sync_governance's one-agent-per-account invariant. The array shape is preserved for wire compatibility with 3.0; `maxItems: 1` is load-bearing and mirrors the singular `governance_context` on the protocol envelope. Authentication credentials are write-only and not included in responses — use sync_governance to set or update credentials.",
  "items": {
    "type": "object",
    "properties": {
      "url": { "type": "string", "format": "uri", "pattern": "^https://",
               "description": "Governance agent endpoint URL. Must use HTTPS." }
    },
    "required": ["url"],
    "additionalProperties": false
  },
  "minItems": 1,
  "maxItems": 1
}
```

Three hard mandates: **exactly one** agent; **`^https://`**; on responses the item carries
**`url` and nothing else** (`additionalProperties: false` + the write-only credentials rule).

### `account/sync-governance-request.json` — the registration contract

```
"description": "... The seller persists the governance agent and calls it for approval during
media buy lifecycle events via check_governance. Uses replace semantics: each call replaces any
previously synced agent on the specified accounts. ... The binding is **account-scoped, not
plan-scoped**. Each account binds to exactly one governance agent ..."
```

```json
"required": ["idempotency_key", "accounts"],
"governance_agents": { ..., "minItems": 1, "maxItems": 1,
  "items": { "required": ["url", "authentication"], "additionalProperties": false } },
"url": { "format": "uri", "pattern": "^https://" },
"authentication": { "required": ["schemes","credentials"],
  "schemes": { "minItems": 1, "maxItems": 1 },
  "credentials": { "minLength": 32 } },
"idempotency_key": { "minLength": 16, "maxLength": 255, "pattern": "^[A-Za-z0-9_.:-]{16,255}$" }
```

**Asymmetry that matters:** `authentication` is **required on the request item** and
**forbidden on the response/account item**. Write-only.

### `account/sync-accounts-request.json` — what we actually implement

Account entry `properties` = `[account, brand, operator, billing, billing_entity,
payment_terms, sandbox, preferred_reporting_protocol, notification_configs]`. **No
`governance_agents`.** But `additionalProperties: true`, and the entry is a
`oneOf[ProvisioningMode, SettingsUpdateMode]`. So carrying the binding on `sync_accounts` is
*tolerated*, never *specified*. Verified live: `SyncAccountsRequest(accounts=[{..., 'governance_agents':
[{'url': 'https://…'}]}])` round-trips the field through the SDK entry model.

### `account/sync-governance-response.json`

`allOf` includes `core/protocol-envelope.json` → **`status` REQUIRED on every response**
(*"Agents shipping responses without a top-level `status` are non-conformant regardless of
whether the task body schema would otherwise validate."*). Success variant requires
`accounts[]`, each `required: ["account","status"]`, `status ∈ {synced, failed}`,
and `governance_agents` items again **url-only, `additionalProperties: false`, min/max 1**.

### `media-buy/create-media-buy-request.json` — `plan_id`

```json
"plan_id": { "type": "string",
  "description": "Campaign governance plan identifier. Required when the account has
  governance_agents. The seller includes this in the committed check_governance request so the
  governance agent can validate against the correct plan.",
  "x-entity": "governance_plan" }
```
`required: ["idempotency_key","account","brand","start_time","end_time"]` — `plan_id` is
conditionally required *in prose only*; no `if/then` encodes it.

### `core/protocol-envelope.json` — `governance_context`

```
"governance_context": { "type": "string", "minLength": 1, "maxLength": 4096,
  "pattern": "^[\\x20-\\x7E]+$",
  "description": "... An account binds to one governance agent (see sync_governance) ...
  governance agents MUST emit a compact JWS per the AdCP JWS profile ... In 3.1 all sellers
  MUST verify." }
```

---

## 4. Conflicts

**Schema overrode storyboard — twice:**

1. **Storyboard prose says the seller MUST call check_governance; no storyboard `validations:`
   entry grades it.** The scenario's three `Then`s are written as MUST/MUST NOT obligations
   sourced from that prose. Under the authority order, ungraded prose does not justify
   `@storyboard-v3.1`. → retag `@schema-v3.1`.
2. **`sync-governance-request` requires `authentication` on the agent item;
   `core/account.json` forbids it on the response item.** The scenario's sibling
   (`@T-UC-030-sync-happy`, line ~50) already encodes this as *"does NOT echo
   governance_agents[0].authentication"* — correct, and it is the schema, not the storyboard,
   that mandates it.

**What the scenario gets wrong:**

- **Names a tool that does not exist.** `sync_governance` is not registered
  (`src/core/main.py:351-352` registers `list_accounts`, `sync_accounts`). The Given can never
  be satisfied as written.
- **Asserts an interaction production never performs.** No `check_governance` caller exists
  anywhere in `src/`. All three `Then`s are unimplementable, not merely unimplemented.
- **Two of three `Then`s are negative universals.** *"MUST NOT skip"* and *"MUST NOT call a
  governance agent URL other than…"* are unbounded — no finite BDD run can establish them.
  They also compare no concrete values, so `test_architecture_bdd_no_trivial_assertions.py`
  would reject the step bodies that could satisfy them.
- **`Scenario`, not `Scenario Outline`.** No `Examples:` table, so the "which URL" specificity
  the scenario is entirely about is left to prose.
- **Vacuous by construction today.** With no step definitions and no `scenarios()` binding it
  is neither green nor red — it is invisible. The auto-xfail machinery
  (`tests/bdd/conftest.py:85-160`) never sees it because the file is never collected.

---

## 5. Proposed Gherkin

Replaces the scenario at `:569`. GREEN-capable: every assertion holds against current
production (`sync_accounts` persists `governance_agents`, `_account_fields_changed` →
`repo.update_fields` gives replace semantics, `_db_account_to_schema:70` echoes it on
`list_accounts`, and the SDK `GovernanceAgent` is `extra="forbid"` with `url` as its only
field, so credentials cannot leak). Transport-independent — the `list_accounts` `When` has a
transport-less form dispatched by `pytest_generate_tests`
(`tests/bdd/steps/domain/uc011_accounts.py:329-336`).

```gherkin
  @T-UC-030-storyboard-binding-used-during-create-media-buy @schema-v3.1 @v3-1 @binding @account-binding
  Scenario Outline: Account governance binding is single, HTTPS, replace-on-write, credential-free -- <case>
    Given the Buyer Agent has an authenticated connection
    And an account for brand domain "pinnacle-agency.example" is bound to governance agent "<first_url>"
    When the Buyer Agent rebinds brand domain "pinnacle-agency.example" to governance agent "<second_url>"
    And the Buyer Agent sends a list_accounts request
    Then the account for brand domain "pinnacle-agency.example" carries exactly 1 governance agent
    And the account for brand domain "pinnacle-agency.example" has governance_agents[0].url "<expected_url>"
    And the governance agent on brand domain "pinnacle-agency.example" exposes exactly the fields "url"
    # core/account.json governance_agents: minItems 1 / maxItems 1, items url-only with
    # additionalProperties:false, url pattern ^https:// . The description is explicit that
    # "Authentication credentials are write-only and not included in responses".
    # Replace semantics ("each call replaces any previously synced agent on the specified
    # accounts") come from account/sync-governance-request.json.
    #
    # Tagged @schema-v3.1, NOT @storyboard-v3.1, deliberately: at 3.1.1 no `validations:`
    # entry anywhere under dist/compliance/3.1.1/ grades that the seller invokes
    # check_governance against the registered URL -- it appears only under `narrative:` /
    # `expected:` (domains/media-buy/index.yaml:207,429; governance_approved.yaml:221 grades
    # response_schema alone). That half is owned by specialisms/governance-aware-seller,
    # which we do not declare (src/core/tools/capabilities.py:99-100), so it grades
    # not_applicable for us. See #<TICKET-A>.
    #
    # NOTE: production has no sync_governance tool; the binding is carried on the
    # sync_accounts entry, which account/sync-accounts-request.json tolerates via
    # additionalProperties:true but does not specify. See #<TICKET-B>.
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/account.json#governance_agents
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/account/sync-governance-request.json

    Examples:
      | case                          | first_url                                  | second_url                                 | expected_url                               |
      | replace with a different agent | https://governance.pinnacle-agency.example | https://governance.acme-buyer.example      | https://governance.acme-buyer.example      |
      | re-sync the same agent         | https://governance.pinnacle-agency.example | https://governance.pinnacle-agency.example | https://governance.pinnacle-agency.example |
```

Both rows compare concrete values; the count `1` and the field-set `"url"` are exact
comparisons, not truthiness. Note the second row also pins the one-agent invariant under
re-sync — the case where a naive append implementation would produce two entries.

**Caveat, stated plainly:** this is green *if wired*. It is not wired, and this PR should not
wire it — binding `BR-UC-030-…feature` lights up ~40 dormant `sync_governance` scenarios that
have no production behind them. See TICKET MATERIAL.

---

## 6. Step inventory

**Existing — reuse verbatim** (`tests/bdd/steps/domain/uc011_accounts.py`):

| Step | Location |
|---|---|
| `Given the Buyer Agent has an authenticated connection` | uc011_accounts.py (also `generic/given_auth.py`) |
| `When the Buyer Agent sends a list_accounts request` | uc011_accounts.py:329-336 (`parsers.re`, transport-less) |

**New — 4 steps, all belonging in `uc011_accounts.py`** (the account domain module), not a new
uc030 module, since none of them touch `sync_governance`:

| Step | Model |
|---|---|
| `Given an account for brand domain "{domain}" is bound to governance agent "{url}"` | mirrors `an account for brand domain "{domain}" already exists with billing "{billing}"` (:~2500) — route through `_sync_pre_create(ctx, domain, operator, billing, governance_agents=[{"url": url}])` |
| `When the Buyer Agent rebinds brand domain "{domain}" to governance agent "{url}"` | second `sync_accounts` dispatch on the same natural key |
| `Then the account for brand domain "{domain}" carries exactly {count:d} governance agent` | `len(agent_list) == count` |
| `Then the account for brand domain "{domain}" has governance_agents[0].url "{url}"` | exact string compare |
| `Then the governance agent on brand domain "{domain}" exposes exactly the fields "{fields}"` | `set(agent.model_dump(exclude_none=True)) == {"url"}` — exact set compare, survives the trivial-assertion guard |

**Do NOT reuse** `when_sync_with_governance_agents` (uc011_accounts.py:862) — it is broken, see
TICKET MATERIAL.

**Retire** (they have no definitions and cannot get correct ones):
`Then the Seller Agent should call check_governance against the previously registered governance agent URL`,
`And the seller MUST NOT skip the governance check…`,
`And the seller MUST NOT call a governance agent URL other than…`.

---

## 7. TICKET MATERIAL

- **A. `BR-UC-030-manage-governance-binding.feature` is 100% dormant — no `scenarios()`
  binding, no step module.** Evidence: 20 `scenarios(...)` calls exist across `tests/bdd/test_*.py`;
  none names UC-030. `ls tests/bdd/steps/domain/` has no `uc030_*.py`. Every one of the file's
  ~40 scenarios (including `@T-UC-030-storyboard-binding-used-during-create-media-buy`) is
  invisible to CI and to the auto-xfail machinery at `tests/bdd/conftest.py:85-160`. Mandate:
  `dist/compliance/3.1.1/specialisms/sales-non-guaranteed/index.yaml:262-304` puts
  `sync_governance` in `required_tools` for the specialism we declare, so the registration
  half is on our conformance path and must be graded. Fix requires the `sync_governance`
  tool first (ticket B) — file as an epic, not a quick wire-up.

- **B. `sync_governance` is not implemented.** Registered tools are `list_accounts` and
  `sync_accounts` only (`src/core/main.py:351-352`). `sales-non-guaranteed/index.yaml:9`
  lists `sync_governance` under `required_tools`, and `:292-304` grades
  `accounts[0].status == "synced"` plus `response_schema` against
  `account/sync-governance-response.json`. We declare `sales_non_guaranteed`
  (`src/core/tools/capabilities.py:100`) and therefore fail this step outright, not
  `not_applicable`. Wire schema: request `account/sync-governance-request.json`
  (`required: [idempotency_key, accounts]`), response `account/sync-governance-response.json`
  (`oneOf` success/error, success `required: [accounts]`, per-account
  `required: [account, status]`, `status ∈ {synced, failed}`).

- **C. `GovernanceAgent` rejects the `authentication` block the spec requires on the request.**
  `src/core/tools/accounts.py:255-273` (`_serialize_governance_agents`) validates every
  incoming agent through `adcp.types.generated_poc.core.account.GovernanceAgent`, which is
  `extra="forbid"` with `url` as its only field (verified: passing `authentication` raises
  `extra_forbidden`). `sync-governance-request.json` declares the agent item
  `required: ["url", "authentication"]` with `authentication.credentials.minLength: 32`. So a
  spec-shaped registration is **rejected at the model boundary** — we can never accept
  credentials, and therefore can never call a governance agent even if ticket D were done. The
  SDK type is modelled on the *response* shape (`core/account.json`, url-only) and is being
  reused for the *request* shape; those are deliberately asymmetric (credentials write-only).
  Needs a separate request-side model.

- **D. No `check_governance` caller exists.** Zero hits for `check_governance` in `src/`
  (only `governance_agents` as a persisted column: `src/core/database/models.py:827-829`,
  `src/core/tools/accounts.py:70,586,629`). `create_media_buy` never reads
  `account.governance_agents`. Mandated by `sync-governance-request.json`
  (*"The seller persists the governance agent and calls it for approval during media buy
  lifecycle events via check_governance"*) and by
  `specialisms/governance-aware-seller/index.yaml:72-79`. **Gated behind a specialism we do not
  declare**, so this is a *feature* ticket, not a conformance failure — but it is the
  prerequisite for ever claiming `governance-aware-seller`.

- **E. `_make_governance_agent` is dead code that always raises.**
  `tests/bdd/steps/domain/uc011_accounts.py:91-108` constructs
  `GovernanceAgent(url=..., categories=categories)`. `GovernanceAgent` has no `categories`
  field and is `extra="forbid"` — verified: `ValidationError … categories … Extra inputs are
  not permitted`. Its only caller, `when_sync_with_governance_agents` (`:862-889`), always
  passes `categories=["budget_authority", "strategic_alignment"]`, so that `When` step can only
  ever land in `ctx["error"]`. The step is referenced by no feature file (grep across
  `tests/bdd/features/` finds the phrasing nowhere), so nothing has ever exercised it. Its
  docstring is also stale: *"Constructs a valid GovernanceAgent entry (url + authentication)"* —
  it constructs neither. Delete or repair.

- **F. `^https://` on governance agent URLs is never enforced.** `core/account.json` and
  `sync-governance-request.json` both declare `"pattern": "^https://"` on `url`. The SDK
  `GovernanceAgent.url` is `{"type":"string","format":"uri","minLength":1}` — the pattern is
  dropped in codegen. Verified: `GovernanceAgent.model_validate({'url':'http://plain.example'})`
  is **accepted** and normalises to `http://plain.example/`. Since that model is our DB column
  type (`src/core/database/models.py:827-829`) and our response type, we will persist and echo
  plaintext governance endpoints. The UC-030 sibling scenario `@T-UC-030-bva-url` expects
  `URL_NOT_HTTPS` for `http://` — it will fail whenever the file is wired. Schema wins over
  SDK: add explicit validation, do not wait on an SDK fix.

- **G. `sync_accounts` response never echoes the governance binding.** `_build_sync_result`
  (`src/core/tools/accounts.py:~313`) omits `governance_agents` entirely; the value is only
  readable via a follow-up `list_accounts` (`:70`). `sync-governance-response.json` requires the
  persisted agent in `accounts[].governance_agents`. Not a `sync_accounts` violation today
  (that response schema does not declare the field), but it is the shape ticket B must ship.

- **H. `plan_id` governance gate is entirely unimplemented and its BDD is silently xfailed.**
  Four wired UC-002 scenarios (`tests/bdd/features/BR-UC-002-create-media-buy.feature:2031,2044,2056,2069`)
  assert `plan_id` is required when the account has `governance_agents`, forwarded to
  `check_governance`, and `PLAN_NOT_FOUND` when unresolvable. **None of their step phrasings
  has a definition** (`the account has governance_agents configured`, `the request should
  proceed past the governance gate`, `the plan_id should be forwarded to check_governance`,
  `the governance path should be skipped` — zero grep hits in `tests/bdd/steps/`), so all four
  are auto-xfailed. Mandate: `media-buy/create-media-buy-request.json` `plan_id`
  (*"Required when the account has governance_agents"*). Also: those four still carry the stale
  `@source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5` footer and need the same re-pin.

- **I. Top-level `status` missing on responses (known, cross-cutting).** Already filed per the
  brief; `sync-governance-response.json` `allOf`s `core/protocol-envelope.json`
  (`status` REQUIRED, *"Agents shipping responses without a top-level `status` are
  non-conformant"*), so ticket B inherits it.

---

## 8. Risks

- **Not executed.** The proposed Gherkin was never run — the feature file has no `scenarios()`
  binding, so there is nothing to run it against without also wiring ~40 dead scenarios. Green
  is argued from source, not observed: `_sync_pre_create` → `SyncAccountsRequest` accepts
  `governance_agents` on the entry (**verified live** in the venv);
  `_account_fields_changed:302-305` → `repo.update_fields` gives replace semantics (read, not
  run); `_db_account_to_schema:70` echoes the column (read, not run).
  `AccountRepository.update_fields` (`src/core/database/repositories/account.py:232-246`) is a
  blanket `setattr` loop with `_IMMUTABLE_FIELDS = {tenant_id, account_id, created_at}` — no
  column whitelist, so the `governance_agents` kwarg lands. The "replace with a different agent"
  row is therefore sound on the write path.
- **Tag change beyond `@storyboard-v3.1` → `@schema-v3.1`.** I also propose dropping
  `@create-media-buy-integration` (the scenario no longer touches `create_media_buy`) and adding
  `@account-binding`. The brief says keep the vocabulary; keeping a tag that names an
  integration the scenario deliberately no longer covers seemed worse. Revert if the lead
  disagrees — `@T-UC-030-storyboard-binding-used-during-create-media-buy` is unchanged either way.
- **Scenario title vs. identifier tag.** The proposed title no longer matches the
  `-storyboard-binding-used-during-create-media-buy` slug. The slug is load-bearing
  (`docs/test-obligations/bdd-traceability.yaml:15828`, `upstream_refs:
  ["BR-UC-030-main-sync", "BR-UC-030-main-check"]`) so I left it, but the mismatch will read
  oddly. A traceability-yaml update is the clean fix and is out of my scope.
- **`upstream_traffic` could grade this in a later version.** The grammar exists and is already
  applied to governance endpoints in the brand domain. If 3.1.x adds
  `endpoint_pattern: "POST */check_governance"` to a `sales-*` specialism, the invocation half
  becomes graded on our path. Noted as drift only — we are pinned to 3.1.1 and I did not read
  3.1.8/HEAD.
- **`domains/` and `protocols/` mirrors are byte-identical** for both `governance/index.yaml`
  and `media-buy/index.yaml` (verified with `diff`). I cite `domains/` throughout; the
  `protocols/` paths are equally valid and the line numbers match.
- **`requires_scenarios` inconsistency in the spec, unresolved.**
  `domains/media-buy/index.yaml:26-37` narrative claims *"Governance integration … tested by
  required scenarios"*, but its `requires_scenarios` list (`:10-24`) contains none of the four
  `governance_*` scenarios. Only `governance-aware-seller` requires them. I read this as the
  narrative being stale and the machine-readable list being authoritative — that reading is
  what makes the verdict "undeclared gate". If the reverse is true, the invocation half would
  be baseline-required for every media-buy seller and ticket D becomes urgent.

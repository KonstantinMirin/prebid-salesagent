# E2E wireability — Pass A (15 scenarios)

Repo read-only at `/Users/konst/projects/salesagent-sbsweep` (`test/storyboard-binding-baseline`).
Criterion per E2E-BRIEF.md: `realize_e2e` classification, not "does it look like mocking".

**Headline:** none of the 15 uses the one genuinely-unrealizable capability
(`set_adapter_error`, `tests/harness/_mixins.py:206-213`). Every setup step in this batch is
either a DB write, a ctx-only flag, or a mock mutation that is explicitly mirrored to the DB by
its own step body. So **no new `e2e_rest_known_failures.txt` entries are required by this batch.**

Three scenarios are broken — but two of them break on *all four* transports, not on e2e
specifically, and one is an env-routing error. The e2e mechanism is not the limiting factor here;
harness routing and missing Givens are.

---

## 1. Summary table

| Scenario | Verdict | Breaking step | Remediation |
|---|---|---|---|
| sb-uc001-finalize | E2E-WIREABLE (vacuous) | — | Needs a `_detect_uc` UC-001 branch; exercises zero server surface on e2e_rest |
| sb-uc001-refine | E2E-WIREABLE (vacuous) | — | Same |
| sb-uc002-async | **E2E-WIREABLE** | — | — |
| sb-uc002-gov-approved | **E2E-WIREABLE** | — | — |
| sb-uc002-gov-conditions | **E2E-WIREABLE** | — | (proposal's A2A-reuse rationale is factually wrong — §6) |
| sb-uc002-gov-denied | **E2E-WIREABLE** | — | Names no wiring branch → stays on the catch-all xfail |
| sb-uc002-gov-recovery | **NOT WIREABLE** (all transports) | `Then the package budget should be persisted as <corrected_budget>` | New create-side step; the existing one resolves package_id from `update_kwargs`/`existing_package`, neither of which exists on a create |
| sb-uc002-inv-nomatch | **E2E-WIREABLE** | — | — |
| sb-uc002-inv-targeting | **E2E-WIREABLE** | — | `uc019_query_media_buys` not in `pytest_plugins` (transport-independent) |
| sb-uc002-measurement | **E2E-WIREABLE** | — | — |
| sb-uc002-pending | **NOT WIREABLE** (all transports) | `Given a valid create_media_buy request with account natural key brand "testbrand.com" operator "test-operator.example"` | Add an Account-seeding Given; then E2E-WIREABLE |
| sb-uc003-mbnotfound | **E2E-WIREABLE** | — | — |
| sb-uc003-pkgnotfound | **E2E-WIREABLE** | — | Identity-map caveat on `no database records should be modified` (§7) |
| sb-uc003-notcancellable | **E2E-WIREABLE** | — | Must route onto the **ext** branch, not the `_UC003_MANUAL_APPROVAL` branch (§7) |
| sb-uc003-creativefate | **NOT-E2E-WIREABLE** (and not wireable on any transport) | `When the Buyer Agent sends list_creatives with no filters for the same account` | Needs a conftest branch routing this tag to `CreativeListEnv`; `MediaBuyDualEnv` cannot dispatch list_creatives |

---

## 2. Per scenario

### Shared facts used throughout

- Factory/ORM writes reach the live server: `tests/bdd/conftest.py:3136` `_production_db_pointed_at`
  + `tests/harness/_base.py:1136-1147` (env session bound to `e2e_config.postgres_url`).
- `env.get_session()` / `db_session(ctx)` (`tests/bdd/steps/_harness_db.py:18-20`) both yield
  `env._session`, i.e. the **server's** DB in e2e mode.
- Patches are still started in the test process over e2e (`tests/harness/_base.py:1152-1159`), so
  any `self.mock[...]` mutation with no realizer is a **silent no-op** against the live server.
  See §4 for the ones in this batch.
- e2e dispatch is `RestE2EDispatcher` (`tests/harness/dispatchers.py:229-320`); it reads
  `env.REST_ENDPOINT` / `env.REST_METHOD` — **the env decides which tool is called, not the step.**
- `RestE2EDispatcher` stashes `wire_response` (`dispatchers.py:313-320`), so every
  `wire_field` / `wire_dict` / `_submitted_wire_dict` assertion grades the real HTTP body.

---

### sb-uc001-finalize — E2E-WIREABLE (vacuously)

| Step | Classification |
|---|---|
| `Given a proposal-scoped refine entry with proposal_id … and action "finalize"` (NEW) | in-memory Pydantic build, no env |
| `And a get_products response proposal … proposal_status/expires_at/io_id` (NEW) | in-memory Pydantic build |
| `When the seller serializes the get_products request and response` (NEW) | `model_dump` only |
| Thens ×4 | dict comparisons + `tests/helpers/pinned_schema.py` |

Nothing to realize → nothing can break over e2e. Two caveats:

1. **Blocked before any step runs.** `_detect_uc` (`tests/bdd/conftest.py:3064-3093`) has no
   `T-UC-001` branch, so the autouse `_harness_env` fixture ends at
   `pytest.xfail(f"No harness wired for {uc}")` (`conftest.py:3531-3532`). The proposal names the
   missing `scenarios(...)` binder but not this. Both are required.
2. **The e2e_rest param is dead weight.** `pytest_generate_tests` (`conftest.py:2835-2892`)
   appends `E2E_REST` for any scenario not tagged `@rest/@mcp/@a2a` and not UC-019, so this
   scenario would mint an `[e2e_rest]` param that runs identical in-process schema code and never
   touches HTTP. Recommend the sweep owner decide whether these pure-schema scenarios should carry
   a transport-specific tag (the only existing opt-out) rather than 4 identical params.

### sb-uc001-refine — E2E-WIREABLE (vacuously)

Identical shape: one Given building `GetProductsRequest`, one When calling
`model_validate`, one Then comparing a string. Same two caveats as above verbatim.

---

### sb-uc002-async — **E2E-WIREABLE**

| Step | What it ultimately does |
|---|---|
| `Given a valid create_media_buy request with account "acc-001"` | ctx only — sets `ctx["account_ref"]` (`tests/bdd/steps/domain/uc002_create_media_buy.py:119-125`) |
| `And the account "acc-001" exists and is active` | `AccountFactory` + `AgentAccountAccessFactory` → **DB write** (`uc002_create_media_buy.py:264-283`) |
| `And the approval scenario is pending_human_review` | → `given_tenant_manual_approval` (`tests/bdd/steps/generic/given_media_buy.py:203-227`): `tenant.human_review_required = True` + `_commit_factory_data()` → **DB write**; mock mutation via `_configure_adapter_manual_approval`; then `_sync_adapter_approval_to_db` |
| `And the approval scenario is pending_adapter_approval` | → `given_tenant_auto_approval` + `given_adapter_manual_approval` (`given_media_buy.py:242-252`): mock mutation **plus** `_sync_adapter_approval_to_db(manual_approval_required=True)` |
| `When the Buyer Agent sends the create_media_buy request` | `uc002_create_media_buy.py:713` → `dispatch_request` → `env.call_via(E2E_REST, …)` |
| new `Then the task_id should be the step_id of the approval workflow step…` | `env.get_workflow_steps()` (`tests/harness/_base.py:1303-1315`) — SELECT over the env session = **server DB** |

The adapter half realizes over e2e: `_sync_adapter_approval_to_db` (`given_media_buy.py:93-106`)
→ `set_adapter_test_behavior` (`tests/factories/core.py:171-211`) writes
`AdapterConfig.mock_manual_approval_required`, which the live server reads at
`src/core/helpers/adapter_helpers.py:138-140` into the adapter config, consumed at
`src/adapters/base.py:229`. `manual_approval_operations` is **not** written, but the server-side
default already contains `create_media_buy` (`src/adapters/base.py:230-231`), so the production
gate at `src/core/tools/media_buy_create.py:2706-2725` fires. Precedent: `T-UC-003-approval-adapter`
is graduated across transports (`tests/bdd/conftest.py:561`).

Routing is e2e-correct: the `_UC002_MANUAL_APPROVAL_WIRED` branch uses `_db_scope_for`
(`conftest.py:3247-3269`).

### sb-uc002-gov-approved — **E2E-WIREABLE**

| Step | Classification |
|---|---|
| `Given the tenant is configured for auto-approval` | `uc002_create_media_buy.py:1451-1483` — `tenant.human_review_required = False` + commit → **DB write**; then *asserts* on `env.mock["adapter"]` (in-process object, assertion is inert over e2e but harmless) |
| `And a valid create_media_buy request with:` (datatable) | ctx only (`tests/bdd/steps/generic/given_media_buy.py:398`) |
| `And the request includes 2 packages…` / `positive budget` / `same currency` / `pricing_option_id` | ctx-only flags |
| new `And the account "acc-001" exists and is active with <registration_state>` | `AccountFactory(governance_agents=…)` → **DB write**; `Account.governance_agents` is a real column (`src/core/database/models.py:827`) |
| `And the ad server adapter is available` | ctx-only no-op (`uc002_create_media_buy.py:1641-1645`) |
| Thens (`wire media_buy_status`, `wire status`, `NOT contain …`) | real wire via `_submitted_wire_dict` (`uc003_update_media_buy.py:127/137/1197`) |

Auto-approval holds over e2e without an adapter DB sync because `MediaBuyCreateEnv.setup_media_buy_data`
already seeds `human_review_required=False` explicitly for the live server
(`tests/harness/media_buy_create.py:93-116`) and `AdapterConfig.mock_manual_approval_required`
defaults to `False` (`src/core/database/models.py:1278`). See §4 for why this is still a latent hazard.

### sb-uc002-gov-conditions — **E2E-WIREABLE**

Same Given set as sb-uc002-async minus the approval partition; the new Then reads `wire_dict(ctx)`
(`tests/bdd/steps/_outcome_helpers.py:43-59`), which hard-errors rather than going tautological when
a wire transport fails to stash a body. Nothing in-process-only.

One factual correction the sweep owner should carry: the proposal declines to reuse
`the response should NOT contain "{field}" field` because "its success path calls
`_assert_a2a_submitted_task_has_no_artifacts`, which is … wrong for a synchronous success —
reusing it here would fail on A2A." That helper early-returns unless
`wire_response["status"] == "submitted"` (`uc003_update_media_buy.py:1183-1185`), so on a
`completed` create it is a no-op. The stated reason for adding a near-duplicate step does not hold
(sb-uc002-gov-approved reuses the same step, correctly).

### sb-uc002-gov-denied — **E2E-WIREABLE**

All Givens are ctx-only or `AccountFactory` DB writes (`uc002_create_media_buy.py:104-125, 286-306`,
`:1641`). The new Then reads `_wire_code(ctx)` plus `ctx["error_response"]/["response"]`.

Two flags:
- The new step's docstring reasons about "IMPL / no-wire scenarios" — dead path (§5).
- The proposal specifies no conftest wiring branch. Without one the tag lands on
  `pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")` (`conftest.py:3282`)
  and grades nothing on any transport.

### sb-uc002-gov-recovery — **NOT WIREABLE (all transports, not e2e-specific)**

E2E mechanism is clean:

| Step | Classification |
|---|---|
| `Given the tenant has max_daily_package_spend configured at 1000` | `given_media_buy.py:377-380` → `_set_max_daily_package_spend` → `CurrencyLimit` UPDATE + `session.commit()` over `db_session(ctx)` = **server DB** |
| `But a package has budget 50000 over a 2-day flight` | ctx only (`given_media_buy.py:858-882`) |
| new `When the buyer corrects the package budget … and resubmits with a fresh idempotency_key` | re-dispatch through `dispatch_request`; the proposal's claim that `dispatch_request` does not clear prior ctx keys is **correct** (`tests/bdd/steps/generic/_dispatch.py:56-88`) |
| `Then no media buy record should be persisted in the database` | `then_media_buy.py:285-299`, DB count over the env session |

**Breaking step:** `And the package budget should be persisted as <corrected_budget>`.
`then_package_budget_persisted` (`tests/bdd/steps/generic/then_media_buy.py:398-428`) resolves the
package_id from `ctx["update_kwargs"]["packages"]`, falling back to `ctx["existing_package"]` and
asserting `pkg is not None`. This is a **create** scenario: neither key is ever set, so the step
raises `"No package in update request or ctx — cannot verify budget"` on a2a/mcp/rest **and**
e2e_rest alike.

Remediation: add a create-side sibling that reads the package_id off the response
(`wire_field(ctx, "packages")[0]["package_id"]`) and then does the same DB read — and extract the
DB-read half into a helper shared with the update-side step (DRY; the two bodies would otherwise be
the same query with a different id source).

### sb-uc002-inv-nomatch — **E2E-WIREABLE**

| Step | Classification |
|---|---|
| new `Given the tenant's product permits property_list targeting` | mutates `ctx["default_product"].property_targeting_allowed` + commit → **DB write**. Column is real and defaults False (`src/core/database/models.py:296`), enforced server-side at `src/services/targeting_capabilities.py:289-312` |
| new `And the buyer sets package targeting_overlay to "<lists_sent>" …` | writes `ctx["request_kwargs"]` — ctx only |
| new `And the create_media_buy request carries context correlation_id …` | ctx only |
| Thens (context echo, errors code+field, package overlay round-trip) | `wire_field(ctx, …)` — real HTTP body over e2e |

The `UNSUPPORTED_FEATURE` advisory is produced by `src/services/targeting_capabilities.py:163`
inside the server process, so it appears on the e2e wire identically. Requires the wiring branch
the proposal names (an ext-shaped `MediaBuyCreateEnv` branch, which uses `_db_scope_for`).

### sb-uc002-inv-targeting — **E2E-WIREABLE**

Same product-flag Given (DB write). `Then the persisted package 1 targeting_overlay field …` reads
`MediaPackage.package_config` — a DB read; over e2e it resolves against the server DB either via
the env session or via the repointed production engine (`conftest.py:3164-3180`). Fine.

Transport-independent blocker the proposal already names: `the response errors array should include
error code "{code}"` lives in `uc019_query_media_buys.py:1736`, which is **not** in
`conftest.py`'s `pytest_plugins` — not visible on any transport until lifted into a shared module.

### sb-uc002-measurement — **E2E-WIREABLE**

All three new steps are ctx writes (`context`, `measurement_terms` on the first package) plus one
wire read (`wire_field(ctx, "context")["correlation_id"]`). The reused `wire …` steps
(`uc003_update_media_buy.py:127/137/148`) all go through `_assert_wire_field_equals` → `wire_dict`,
which raises on a missing wire body rather than falling back. Either dispatch mode (`create` or
`create_raw`, `uc002_create_media_buy.py:713-757`) funnels through `dispatch_request`, so e2e is
unaffected by that choice.

### sb-uc002-pending — **NOT WIREABLE (all transports)**

Brief's two-tool question, answered: **no.** The final Gherkin was scoped to the
`create_buy_no_creatives` phase only — one `When`, one tool (`create_media_buy`), one Examples row.
It does **not** need `pending_creatives → pending_start` and therefore does not need a two-tool env.
`MediaBuyCreateEnv` (create-only: `REST_ENDPOINT = "/api/v1/media-buys"`,
`tests/harness/media_buy_create.py:80`, patches scoped to `media_buy_create`) is sufficient. The
transition phases were correctly moved to tickets.

**Breaking step (all four transports):**
`Given a valid create_media_buy request with account natural key brand "testbrand.com" operator "test-operator.example"`.

`given_request_with_natural_key` (`uc002_create_media_buy.py:78-90`) builds an
`AccountReferenceByNaturalKey` and attaches it to the request (`_attach_account_to_full_request`,
`:30-43`) — but **seeds no `Account` row**. At the transport boundary
`enrich_identity_with_account` (`src/core/transport_helpers.py:143-148`) calls `resolve_account`
(`src/core/helpers/account_helpers.py:65-67`), which raises `AdCPAccountNotFoundError` when the
natural key matches nothing. So the scenario resolves to `ACCOUNT_NOT_FOUND`, not
`pending_creatives`, on a2a/mcp/rest and e2e_rest alike.

Remediation (transport-uniform, no e2e-specific work): add a Given that seeds an `Account` with
`brand={"domain": "testbrand.com"}, operator="test-operator.example"` plus
`AgentAccountAccessFactory` — the same body as `given_account_exists_active`
(`uc002_create_media_buy.py:264-283`), parameterised on brand+operator rather than duplicated.
With that seeded the scenario is E2E-WIREABLE: every remaining step is a DB write, a ctx flag, or a
`wire_*` read.

Also note the proposal's own §5b: without a `_UC002_STORYBOARD_WIRED` branch the tag hits the
catch-all xfail and grades nothing.

### sb-uc003-mbnotfound — **E2E-WIREABLE**

| Step | Classification |
|---|---|
| `Given a valid update_media_buy request with:` | ctx; `media_buy_id` label resolved via `_resolve_media_buy_id` (`uc003_update_media_buy.py:53-59`), unknown ids pass through verbatim — exactly what this scenario wants |
| `And no media buy exists with media_buy_id "<id>"` | SELECT + DELETE + commit over `db_session(ctx)` → **server DB** (`uc003_ext_error_scenarios.py:113-137`) |
| new `And the request carries context.correlation_id …` | ctx only |
| new Thens | `result.assert_wire_error` / `result.wire_error_envelope` — the e2e dispatcher populates both from the real HTTP error body (`dispatchers.py:288-306`) |

The proposed routing (extend the `T-UC-003-ext-` branch condition) is the e2e-correct one — that
branch uses `_db_scope_for` (`conftest.py:3302-3321`).

### sb-uc003-pkgnotfound — **E2E-WIREABLE**

The two new presence Givens delegate to existing bodies that are DB delete/verify/create
(`uc003_ext_error_scenarios.py:113-137`, `:254-294`) — all e2e-realized. `Then the result should be
error "…" correctable with suggestion` routes to `result.assert_wire_error`
(`uc002_create_media_buy.py:1339-1345` → `tests/harness/transport.py:144-181`), wire-first.

Caveat on `Then no database records should be modified`
(`uc003_ext_error_scenarios.py:812-...`): it compares the DB row against the in-memory
`ctx["existing_media_buy"]`, and `db_session(ctx)` hands back the **same session** those objects are
attached to (`tests/bdd/steps/_harness_db.py:18-20`). It is non-vacuous only because
`expire_on_commit` forces a refetch after the last commit. That is pre-existing and shared with the
in-process transports, so it is not an e2e blocker — but over e2e the mutation would come from
*another process*, which is precisely the case where a stale identity map would hide a real
regression. Worth a follow-up (`session.expire_all()` before the read-back).

### sb-uc003-notcancellable — **E2E-WIREABLE**

**Confirmed from the step body, as the brief asked:** `given_media_buy_status`
(`tests/bdd/steps/domain/uc003_update_media_buy.py:162-193`) does exactly
`mb.status = status` followed by `env._commit_factory_data()`. Over e2e that commit lands in the
live server's database, which the server then reads on the next HTTP request. Production
implements no cancellation, so no request could produce this state — the DB write **is** the
fixture, and it is legitimate over e2e. Nothing here is in-process-only; no realizer is needed and
none is missing.

Remaining steps: `given_package_exists` creates a `MediaPackage` via factory when the label does not
resolve (`uc003_update_media_buy.py:379-400`) — DB write; the outcome Then is wire-first;
`no database records should be modified` is the DB read above. `mb_existing` resolves through the
label registered by the feature Background (`BR-UC-003-update-media-buy.feature:27` →
`given_buyer_owns_media_buy_by_id`, `uc003_update_media_buy.py:93`).

**Routing constraint (e2e-specific, must be honoured):** wire this tag onto the
`T-UC-003-ext-` branch (`conftest.py:3302`), which uses `_db_scope_for`. Do **not** put it on the
`_UC003_MANUAL_APPROVAL` branch (`conftest.py:3332-3356`): that branch calls
`request.getfixturevalue("integration_db")` unconditionally, which over e2e repoints production's
cached engine at an empty per-test DB while the env's factories write to the server DB — the exact
wrong-DB class `_db_scope_for` exists to prevent (`conftest.py:3164-3180`). That branch is
e2e-broken today for its three current occupants; see §7.

### sb-uc003-creativefate — **NOT-E2E-WIREABLE (and not wireable on any transport)**

The Givens are fine. Both are DB writes:
`the media buy "<id>" is in "canceled" status` (NEW, `MediaBuyFactory`) and
`creative "<id>" is in the library … assigned to package …` (NEW, `CreativeFactory` +
`CreativeAssignment`). Same class as `given_media_buy_status` — legitimate fixtures over e2e.

**Breaking step:** `When the Buyer Agent sends list_creatives with no filters for the same account`.

The tag is `T-UC-003-…`, so `_detect_uc` (`conftest.py:3069-3070`) routes the scenario to the UC-003
branch, i.e. `MediaBuyDualEnv`. That env dispatches **create or update media buy and nothing else**:
`call_a2a` / `call_mcp` / `call_impl` branch on `_is_update_request` and otherwise fall through to
`MediaBuyCreateEnv` (`tests/harness/media_buy_dual.py:87-102`), and `REST_ENDPOINT` is
`/api/v1/media-buys[/{id}]` (`media_buy_dual.py:132-145`, `media_buy_create.py:80`). Over e2e
`RestE2EDispatcher` reads `REST_ENDPOINT`/`REST_METHOD` directly (`dispatchers.py:265-278`), so the
call would go out as `POST/PUT /api/v1/media-buys…` — never `/api/v1/creatives`
(`tests/harness/creative_list.py:45`). There is no path by which `list_creatives` is reached.

This is on top of the module-local step-visibility problem the proposal already flags
(`tests/bdd/test_uc018_list_creatives.py:182` is not in `pytest_plugins`).

Remediation (both required, neither is an e2e-only fix):
1. Add a UC-003 conftest branch that routes this tag to `CreativeListEnv` under `_db_scope_for`
   (mirror `conftest.py:3406-3415`), and seed the media buy / package / creative there or in the
   Givens.
2. Lift the `list_creatives` When step out of `test_uc018_list_creatives.py` into a shared step
   module before any second feature uses it.

Until then: not a ledger entry — a dormant scenario. Do not add it to
`e2e_rest_known_failures.txt`; it fails everywhere, not just on e2e.

---

## 3. Dead IMPL assumptions

Only two, both mild — no proposal in this batch routes behaviour through an IMPL path.

| Proposal | Location | Text | Assessment |
|---|---|---|---|
| sb-uc002-gov-denied | §6, new step docstring (`sb-uc002-gov-denied.md:304`) | "Reads the real wire envelope when one was captured, and the payload errors array otherwise (IMPL / no-wire scenarios)" | IMPL is not parametrized (`conftest.py:2871-2874`). The fallback branch is unreachable for this scenario. Harmless (the code still works), but the justification is stale — reword or drop the branch. |
| sb-uc002-async | §6 prose (`sb-uc002-async.md:374`) | describes `_outcome_helpers.py:43-59` as having "the same IMPL fallback" | Accurate as a description of the *helper*, which retains a legacy IMPL branch. Not a claim that IMPL runs. No action on the proposal; the helper's dead branch is a separate cleanup. |

No proposal in this batch asserts an IMPL fallback, an IMPL-only degradation, or a
`_serialized_*`-on-IMPL behaviour.

---

## 4. In-process state with no `realize_e2e` declaration (silent-breakage class)

Nothing in this batch breaks silently today, but three undeclared mock mutations sit on the paths
these scenarios use. All three are realized by *convention* (a sibling DB write in the step body)
rather than by the decorator, which is the fragile part.

| Site | Mutation | Realized? | Risk |
|---|---|---|---|
| `tests/bdd/steps/generic/given_media_buy.py:171-186` `_configure_adapter_manual_approval` | `env.mock["adapter"]/["update_adapter"].return_value.manual_approval_required/_operations` | **Yes, but not by `realize_e2e`** — every caller pairs it with `_sync_adapter_approval_to_db` (`:93-106` → `tests/factories/core.py:171-211` → `AdapterConfig.mock_manual_approval_required`, read by the server at `src/core/helpers/adapter_helpers.py:138`) | A future caller that forgets the pairing silently no-ops over e2e. This is exactly the class `realize_e2e` was built for — the mutation belongs on an env method decorated with `@realize_e2e(_sync_adapter_approval)`. |
| `tests/bdd/steps/domain/uc002_create_media_buy.py:1451-1483` `given_tenant_auto_approval` | commits `tenant.human_review_required=False`, then **asserts** on `env.mock["adapter"]` and does **not** write the adapter side to the DB | Partially — the tenant half is a real commit; the adapter half is in-process only | Diverges from `_seed_auto_approval` (`given_media_buy.py:109-133`), which *does* sync the adapter. Two implementations of one intent (DRY). Safe today only because `AdapterConfig.mock_manual_approval_required` defaults False (`src/core/database/models.py:1278`) and `MediaBuyCreateEnv.setup_media_buy_data` pre-seeds auto-approve (`tests/harness/media_buy_create.py:93-116`). The day any scenario writes that column True and a later scenario in the same e2e DB relies on this Given, it flips to the pending path silently. Four scenarios in this batch use it (gov-approved, gov-conditions, gov-denied, pending). |
| `tests/harness/media_buy_create.py:241-285` `_configure_mocks` | the whole create-path adapter MagicMock (`create_media_buy` side_effect, `manual_approval_*`) | N/A — over e2e the live server's real Mock adapter runs instead | Not a breakage (behaviour is equivalent), but it means in-process and e2e exercise *different adapter implementations*. Worth knowing when a create-path assertion diverges between `[rest]` and `[e2e_rest]`. |

`set_adapter_error` — the one declared-unsupported capability (`tests/harness/_mixins.py:206-213`) —
is **not used by any scenario in this batch**. Its single caller remains
`tests/bdd/steps/domain/uc004_delivery.py:308`.

---

## 5. Ledger entries to REMOVE

**None.**

No scenario in this batch depends on an unrealizable setup capability. The three failures are:
- sb-uc002-gov-recovery — a step that fails on all four transports (fix the step, not the ledger).
- sb-uc002-pending — a missing Given, all four transports (fix the Given).
- sb-uc003-creativefate — wrong env / invisible step, all four transports (fix the routing).

Per `tests/bdd/e2e_rest_known_failures.txt` header, entries are for *genuine production or harness
gaps that fail only in-network*. None of these qualify. Adding them would be exactly the
"silent new failure" the brief forbids, in reverse — a ledger entry papering over a defect that is
not e2e-specific.

---

## 6. Cross-cutting issues found (not e2e, but they block the same scenarios)

1. **`sb-uc002-gov-conditions`'s rationale for a new step is wrong.**
   `_assert_a2a_submitted_task_has_no_artifacts` early-returns on a non-`submitted` wire status
   (`uc003_update_media_buy.py:1183-1185`). The existing
   `the response should NOT contain "{field}" field` step is safe to reuse on a synchronous create
   success — as sb-uc002-gov-approved already does. Adding
   `the create_media_buy response should not carry a "{field}" field` alongside it creates two step
   phrasings with the same body, which is the duplicate-step guard's target.

2. **Four proposals each invent their own conftest wired-set.** sb-uc002-async and
   sb-uc002-gov-conditions both extend `_UC002_MANUAL_APPROVAL_WIRED`; sb-uc002-gov-approved proposes
   `_UC002_GOVERNANCE_WIRED`; sb-uc002-measurement and sb-uc002-pending each propose a *different*
   `_UC002_STORYBOARD_WIRED` with different contents. Consolidate before landing, or the last PR
   merged silently drops the others' tags.

3. **`_UC003_MANUAL_APPROVAL` branch is e2e-broken today** (`conftest.py:3332`):
   `request.getfixturevalue("integration_db")` unconditionally, with no `_db_scope_for`. Its three
   occupants (`T-UC-003-alt-manual`, `-approval-tenant`, `-approval-adapter`) run over e2e against
   a repointed empty per-test DB while the env writes to the server DB. Not caused by this sweep,
   but any new UC-003 tag routed there inherits it. Separate ticket.

---

## 7. Uncertainties

- **`then_no_db_records_modified` identity-map staleness.** I traced that `db_session(ctx)` returns
  the env's own session and that `expire_on_commit` should force a refetch, but I did not execute an
  e2e run to prove the read-back sees a server-side mutation. If the sweep lands
  sb-uc003-pkgnotfound / sb-uc003-notcancellable, verify in-network that a deliberately-mutating
  variant actually fails the step (mutation-verify), rather than trusting it green.
- **`env.get_workflow_steps()` over e2e** (sb-uc002-async's new Then) reads rows the *server*
  wrote. The query is unconditional (`_base.py:1310-1315`) so READ COMMITTED should expose them,
  but this is the first proposed use of that method on an e2e path — worth an in-network check
  before graduating.
- **`assert_wire_error` code canonicality.** It rejects codes absent from the pinned
  `error-code.json @04f59d2d5` (`tests/harness/transport.py:164-169`). I did not verify that
  `INVALID_STATE`, `PACKAGE_NOT_FOUND`, `MEDIA_BUY_NOT_FOUND` and `BUDGET_EXCEEDED` are all present
  in that pin. Transport-uniform if wrong, so out of e2e scope, but it would turn three of these
  scenarios red identically on all four params.
- **sb-uc002-inv-nomatch / inv-targeting product flag.** I confirmed the column and the server-side
  validator, but not that `ctx["default_product"]` is the product the request's `product_id`
  actually resolves to over e2e after `_reset_e2e_db`. It is the same object the conftest branch
  stashes, so it should be — flagging because both scenarios hinge on it.
- I did not run anything. Every classification above is from reading the sources cited.

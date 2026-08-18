# E2E pass — batch B (14 scenarios)

Repo read-only at `/Users/konst/projects/salesagent-sbsweep` @ `692e5dfa4`. Nothing edited.

Criterion applied as the brief states it: follow every setup step to the harness method and classify
it as **DB write** / **`realize_e2e`-REALIZED** / **`realize_e2e`-UNSUPPORTED** / **in-process state
with no declaration**. Verified, not assumed: `set_adapter_response` and `set_registry_formats` are
both REALIZED and both behave correctly for the fixtures these proposals use.

Two facts dominate this batch and are established up front because most verdicts hang off them:

**F1 — `ADCP_TESTING=true` makes the live e2e server serve the SAME 57 reference formats as the
in-process harness.** `creative_agent_registry.py:654` (`get_formats_for_agent`) and `:763`
(`list_all_formats_with_errors`) short-circuit to `_get_reference_formats()` under that flag, and
`docker-compose.e2e.yml:59,193` sets it. `_connection_agent_url` (`:199-219`) reroutes only the
*connection*; the federation identity stays canonical `https://creative.adcontextprotocol.org/`.
Consequences: (a) format ids resolve over e2e regardless of the `agent_url` spelling in the payload;
(b) an id absent from the reference catalog is rejected for real over e2e; (c) the catalog is 57
formats on every transport.

**F2 — UC-006 has a harness tag gate that xfails on ALL FOUR transports.** `tests/bdd/conftest.py:3362-3378`
builds `CreativeSyncEnv` only when the scenario carries `@account`, `@creative-invariant`, or
`@BR-RULE-034`; every other UC-006 scenario hits `pytest.xfail("UC-006 harness not yet wired for
non-account scenarios")` before any step runs. Six of my eight UC-006 proposals do not carry a gate
tag. For four of them (`prov-dst`, `prov-corrected`, `fmtroundtrip`, `reception`) the proposal claims
GREEN — that claim is unreachable, on e2e and everywhere else.

---

## 1. Summary table

| # | Scenario | Verdict | Breaking step | Remediation |
|---|---|---|---|---|
| 1 | `sb-uc004-delivery` | **E2E-WIREABLE** | — | none |
| 2 | `sb-uc004-reqmetrics` | **E2E-WIREABLE** | — | none |
| 3 | `sb-uc004-vendormetric` | **E2E-WIREABLE (conditional)** | harness-wiring branch | new conftest branch must pass `e2e_config=e2e_config` (mirror `conftest.py:3508-3513`), else e2e is silently not wired |
| 4 | `repin-uc005-baseline` | **E2E-WIREABLE**, but one proposed Then is **RED on all 4 transports** | `Then the returned page should report has_more false with total_count equal to the number of entries` | catalog is 57, `max_results` default 50 (`creative_formats.py:436,451`) → `has_more=True`. Drop or restate the Then; do NOT "fix" it by sending `pagination` (see #5) |
| 5 | `repin-uc005-roundtrip` | **NOT-E2E-WIREABLE** (also not REST-wireable) | the `context.correlation_id` half of the When + `Then the response should echo context.correlation_id` | `ListCreativeFormatsBody` (`src/routes/api_v1.py:178-192`) has no `context` and is `extra="forbid"` → 422 on rest/e2e_rest. Either add `context` to the body + route mapping (production change) or drop the correlation-id clause |
| 6 | `repin-uc005-thirdparty` | **E2E-WIREABLE (conditional)** | new `Given the seller hosts no format under the third-party agent_url …` | it must derive the premise from `load_reference_formats()` / a real call, NOT from `env.mock["registry"]` — the mock is inert over e2e and the assertion would be vacuous |
| 7 | `sb-uc006-prov-required` | **DORMANT (intended)** — gate-blocked by F2 | — | none now; when the gap closes, the `context.correlation_id` echo is REST/e2e-unsatisfiable (see §5 note) |
| 8 | `sb-uc006-prov-dst` | **BLOCKED (F2)** — never runs on any transport | UC-006 tag gate | add a gate tag or extend `conftest.py:3364`; proposal is silent on this |
| 9 | `sb-uc006-prov-disclosure` | **DORMANT (intended)** — gate-blocked by F2 | — | as #7 |
| 10 | `sb-uc006-prov-corrected` | **BLOCKED (F2)** — never runs on any transport | UC-006 tag gate | as #8. Setup itself is e2e-clean (DB writes + e2e-aware payload builder) |
| 11 | `sb-uc006-prov-contradicted` | **NOT-E2E-WIREABLE (declared xfail)** | the two new `Then the stored creative …` steps | they go through `_get_creative_from_db` (`uc006_sync_creatives.py:577`) → `_xfail_if_e2e` (`:567`). Declared, not silent. Read back through the wire instead, or accept the xfail |
| 12 | `sb-uc006-multiformat` | **E2E-WIREABLE (conditional)** | `Given the Buyer Agent submits a bulk sync batch` — the assets it builds | per-row assets must match each reference format (`banner_image`+`click_url` / `video_file` / `headline,body,thumbnail,…`); `build_assets(image_spec("image"))` for all three will not resolve over e2e |
| 13 | `sb-uc006-fmtroundtrip` | **BLOCKED (F2)**; e2e design otherwise sound | UC-006 tag gate | as #8. Also: the row-3 `registry.get_format` shim is undeclared in-process state — guard it with `is_e2e(ctx)` |
| 14 | `sb-uc006-reception` | **NOT-E2E-WIREABLE** (and BLOCKED by F2) | `Given creative "<id>" <existence>` | `_build_creative_scope_payload` (`uc006_sync_creatives.py:6632-6651`) hardcodes `display_300x250` @ `env.DEFAULT_AGENT_URL`; bare `display_300x250` is **not** in the reference catalog → every row reports `failed` over e2e. Route it through `_format_payload` |

`set_adapter_error` (the one genuinely UNSUPPORTED capability) is **not reached by any proposed
Gherkin in this batch**. Its only caller is `Given the ad server adapter is unavailable`
(`tests/bdd/steps/domain/uc004_delivery.py:307-308`), which appears in none of the three UC-004
proposals.

---

## 2. Per scenario

### 1. `sb-uc004-delivery` — E2E-WIREABLE

| Step | Classification |
|---|---|
| `Given a media buy "mb-sb004" owned by "buyer-001" with status "active"` | `uc004_delivery.py:117` → `_ensure_media_buy_in_db` (`:2925-2969`) → `TenantFactory`/`PrincipalFactory`/`MediaBuyFactory` → **DB write**. Over e2e the factories are bound to the server DB engine (`tests/harness/_base.py:1136-1150`) |
| `And the ad server adapter has delivery data for … with impressions/clicks/spend` (NEW) | `env.set_adapter_response(...)` (`_mixins.py:174-199`) → `_realize_adapter_response` (`:201`) → **REALIZED** via `_persist_simulation_config` (`:38-58`), read by the live Mock adapter at `mock_ad_server.py:1155` / `:1208` |
| `When … requests delivery metrics for "…" with include_package_daily_breakdown …` (NEW) | `dispatch_request` → `ctx["wire_response"]` set (`tests/bdd/steps/generic/_dispatch.py:80`) |
| all `Then`s | read `ctx["response"]` / `wire_field` — REST-visible |

Two details I checked rather than assumed: **clicks survive the realization** (the realizer persists
`resp.model_dump(mode="json")` whole and the server does `AdapterGetMediaBuyDeliveryResponse.model_validate`
on it, `mock_ad_server.py:1180`), and **`ADCP_TESTING` is on in the e2e stack** (`docker-compose.e2e.yml:59,193`)
— without it `_load_delivery_simulation` returns `None` and the whole realization would be inert.

The proposal's analysis never mentions e2e; nothing in it needed to change.

### 2. `sb-uc004-reqmetrics` — E2E-WIREABLE

Identical shape: `Given a media buy …` (`uc004_delivery.py:117`, DB write) + new
`Given the ad server adapter reports impressions … and spend … for "…"` → `set_adapter_response`
(REALIZED) + `When … for media_buy_ids [...]` (`uc004_delivery.py:703`, dispatch) + three Thens on the
response. No undeclared in-process state.

The zero-delivery Examples row is fine over e2e too: it goes through the same realizer with
`impressions=0, spend=0.0`, not through a "no row" path.

### 3. `sb-uc004-vendormetric` — E2E-WIREABLE, conditional on the wiring change

| Step | Classification |
|---|---|
| `Given a tenant is configured for product discovery` | `uc_get_products_inventory.py:63` → **DB write**, and already e2e-aware: its docstring documents seeding the `Principal` row specifically so the e2e_rest token auth resolves |
| `And a product declaring reporting_capabilities.vendor_metrics <declared>` (NEW) | `ProductFactory` + `PricingOptionFactory` → **DB write**. `reporting_capabilities` is a real `Product` column (verified) |
| `When the buyer requests products with filters.required_vendor_metrics <pins>` (NEW) | `dispatch_request`; `ProductEnv.build_rest_body` (`tests/harness/product.py`) forwards `filters` → `POST /api/v1/products` exists |
| all `Then`s | read `ctx["wire_response"]["products"][0]…` — REST-visible |

**The condition.** The proposal's conftest change must construct `ProductEnv(e2e_config=e2e_config)`
under `_db_scope_for(request, e2e_config)`, exactly like the existing `UC-GET-PRODUCTS` branch
(`conftest.py:3508-3513`). A branch that constructs `ProductEnv()` bare would run e2e_rest against the
wrong DB with no error. The proposal's "cleaner alternative" (make `_detect_uc` return
`"UC-GET-PRODUCTS"`) avoids the risk entirely and is the better of the two — note it needs the new
check placed *before* the `T-UC-004` check at `conftest.py:3075`.

**Undeclared in-process state, tolerable here.** `ProductEnv.EXTERNAL_PATCHES` (`product.py`:
`policy_service`, `dynamic_variants`, `ranking_factory`, `resolve_property_list`) carry no
`realize_e2e`, and `_base.py:1152-1159` starts them unconditionally — in the *test* process, where
they are inert over e2e. The live server runs the real code. Precedent says that is fine: the
get_products inventory-profile e2e_rest entries GRADUATED (`e2e_rest_known_failures.txt:82-84`).
But `then_has_products` (`uc_get_products_inventory.py:201-213`) asserts `len(products) == 1`
*exactly*, so it is one live-server dynamic-variant away from breaking. Worth a sentence in the PR.

### 4. `repin-uc005-baseline` — E2E-WIREABLE; one Then is red everywhere

No injection at all: `Given the Buyer Agent calls list_creative_formats without filters` is
`when_request.py:130` → `_call` → `_call_via`, which stashes `ctx["wire_response"]` (`:74`). Nothing
touches a mock. The e2e path is clean.

**The pagination Then does not hold, on any transport.** `load_reference_formats()` returns **57**
formats (executed). `_list_creative_formats_impl` sets `total_count = len(formats)` and
`max_results = 50  # AdCP default` (`src/core/tools/creative_formats.py:435-436`), then
`has_more = end_index < total_count` (`:451`) → `has_more=True`, `total_count=57`, page length 50.
In-process the env seeds the same 57 (`tests/harness/creative_formats.py:99`); over e2e the live
server serves the same 57 by F1. So:

- `has_more false with total_count equal to the number of entries` → **fails**;
- the scenario's stated premise ("the has_more/total_count Then pins that this particular page IS
  the whole catalog") is false — `every entry` grades the first 50 of 57.

Remediation options, in preference order: (a) drop the Then and say plainly in the comment that the
claim is page-scoped; (b) assert the pagination *relation* instead —
`len(entries) == min(50, total_count)` and `has_more == (total_count > len(entries))` — which is true
on every transport and still falsifiable. **Do not** "fix" it by sending `pagination.max_results`:
`ListCreativeFormatsBody` has no `pagination` field and is `extra="forbid"`, so that 422s on
rest/e2e_rest (same mechanism as #5).

### 5. `repin-uc005-roundtrip` — NOT-E2E-WIREABLE (and not REST-wireable)

| Step | Classification |
|---|---|
| `Given … captured a format_id object from a prior get_products response` | `uc005_format_id_roundtrip.py:29-79` — `get_or_create` tenant + `ProductFactory` + `PricingOptionFactory` → **DB write**, then a TRANSPORT-BYPASS in-process `_get_products_impl`. Over e2e that in-process call reads the server DB because `_production_db_pointed_at` (`conftest.py:3137-3163`) repoints the production engine. Legitimate fixture |
| `And … respells the captured agent_url as "…"` (NEW) | ctx-only |
| `When … sends list_creative_formats with format_ids […] and context.correlation_id "…"` (MODIFIED) | **BREAKING** |
| `Then … echo context.correlation_id "…"` (NEW) | **BREAKING** |

`CreativeFormatsEnv` inherits `IntegrationEnv.build_rest_body`, which is
`req.model_dump(mode="json", exclude_none=True)` (`tests/harness/_base.py:969-978`). With
`req.context` set, the REST body carries `context`. `ListCreativeFormatsBody`
(`src/routes/api_v1.py:178-192`) declares no `context` field and its config is
`{'extra': 'forbid', 'defer_build': True}` (executed) → FastAPI 422 → `parse_rest_error` →
`ctx["error"]` → **every** Then in the scenario fails, on `rest` and on `e2e_rest`. Even if the body
accepted it, `response.context = req.context` (`creative_formats.py:517`) would be `None` because the
route never builds one.

Because this breaks plain `rest` as well, a ledger entry is not an available remedy — it must be
fixed. Sibling `sb-uc006-fmtroundtrip` reached the same conclusion independently ("REST drops
context, so they cannot pass transport-independently").

The six canonicalization rows themselves are sound over e2e: production filters on
`format_id_identity` before pagination (`creative_formats.py:302-313`, `:434`), and by F1 the live
catalog carries `display_300x250_image` under the canonical seller `agent_url`.

### 6. `repin-uc005-thirdparty` — E2E-WIREABLE, conditional

| Step | Classification |
|---|---|
| `Given the seller catalog holds format "display_300x250_image" under … "https://creative.adcontextprotocol.org"` (NEW) | `FormatFactory` + `env.set_registry_formats([local])` → **REALIZED** (`tests/harness/creative_formats.py:113-127`). Over e2e `_validate_registry_formats` (`:44-73`) checks `requested ⊆ reference`; `display_300x250_image` **is** in the reference set (executed), so it no-ops — **no `E2EUnsupportedSetup`** |
| `And the seller hosts no format under the third-party agent_url "…"` (NEW) | **CONDITIONAL — see below** |
| `When … sends list_creative_formats with format_ids [{agent_url …, id …}]` (NEW) | `_call(ctx, req=req)` → wire dispatch |
| `Then … exactly <resolved_count> entries` / identity-set equality | wire-readable |
| `Then the creative_agents referrals should not include agent_url "…"` (NEW) | `creative_agents` is emitted (`creative_formats.py:474-486`) — wire-readable |

The e2e semantics differ from in-process (live catalog = all 57, not the single seeded format) but the
assertions survive it, because every row narrows by `format_ids` and production matches on the
canonicalized `(agent_url, id)` pair: own-agent rows → exactly 1, third-party rows → 0.

**The condition.** The proposal describes Given 2 as "asserts the seeded registry contains zero
entries canonicalizing to that host". If that is implemented by reading `env.mock["registry"]`, it is
undeclared in-process state: over e2e the mock is never consulted by the server and the assertion
passes vacuously. Derive it from `load_reference_formats()` (or from an unfiltered
`list_creative_formats` call) instead.

One asymmetry worth knowing, harmless for the assertion as written: over e2e `_get_tenant_agents`
returns `DEFAULT_AGENT` with `agent_url = CREATIVE_AGENT_URL = http://creative-agent:8080/api/creative-agent`
(`creative_agent_registry.py:272`, `docker-compose.e2e.yml:67`), so the `creative_agents` referral
list differs between transports. The Then only requires the third-party URL to be *absent*, which
holds either way — but an assertion that pinned the referral list would not be transport-portable.

### 7. `sb-uc006-prov-required` — DORMANT (intended), gate-blocked

Dormancy is the proposal's explicit goal and F2 reinforces it (`@provenance @rejection` is not in the
allow-set), so the scenario xfails at the fixture before its unbound steps ever matter. E2E adds
nothing.

For whenever the production gap closes: the two Givens are `_setup_product_with_creative_policy`
(`uc006_sync_creatives.py:2817-2845` → `ProductFactory` + `_commit_factory_data` → **DB write**,
e2e-safe) and a ctx-only payload builder — both fine. The `context.correlation_id` Given/Then is
**not** e2e-portable: `CreativeSyncEnv.build_rest_body` (`tests/harness/creative_sync.py:215-236`)
forwards `creatives/assignments/creative_ids/delete_missing/dry_run/validation_mode/account` and
**never `context`**, so on rest/e2e_rest the correlation id never reaches the server. Same note
applies to #9.

### 8. `sb-uc006-prov-dst` — BLOCKED by F2

The proposal presents this as GREEN ONLY, verified by a throwaway probe module. The probe bypassed
`conftest.py:3362-3378`. With tags `@storyboard-v3.1 @v3-1 @provenance @rejection` the scenario gets
`pytest.xfail("UC-006 harness not yet wired for non-account scenarios")` on a2a/mcp/rest **and**
e2e_rest — it never executes a step. The "green" claim needs either a gate tag (`@creative-invariant`
is the precedent set by #11/#12) or a conftest change, and the lead should decide that consciously
rather than discover it at merge.

Setup itself is e2e-clean: `_setup_product_with_creative_policy` (DB write) +
`_build_creative_payload` (`:2688-2703`, ctx-only, and e2e-aware via `_format_payload`). If the gate
is opened, this is E2E-WIREABLE.

### 9. `sb-uc006-prov-disclosure` — DORMANT (intended), gate-blocked

Same as #7. The proposal correctly instructs that the steps must not be written yet. Its
`the response context.correlation_id should equal the request correlation_id` step carries the
`build_rest_body` limitation described in #7 — worth recording now since the proposal suggests
promoting it to `tests/bdd/steps/generic/then_payload.py`, where it would be reused by scenarios that
*do* run on REST.

### 10. `sb-uc006-prov-corrected` — BLOCKED by F2

Claims GREEN; blocked by the tag gate exactly as #8. Setup classification (if the gate opens):
`_setup_product_with_creative_policy` → DB write; `Given the creative library state … is "present"`
→ `CreativeFactory` → DB write (server DB over e2e); the submit Given reuses `_build_creative_payload`'s
plumbing, which is e2e-aware. No undeclared in-process state. Would be E2E-WIREABLE.

### 11. `sb-uc006-prov-contradicted` — NOT-E2E-WIREABLE, declared

This one *runs*: the proposal adds `@creative-invariant`, which routes it into the `CreativeSyncEnv`
branch. Givens are all DB/ctx (`uc006_sync_creatives.py:2754` → `_setup_product_with_creative_policy`;
`:3684` payload builder). The When is the shared dispatch (`:253`).

Both new `Then the stored creative …` steps call `_get_creative_from_db`
(`uc006_sync_creatives.py:577-596`), whose **first line** is `_xfail_if_e2e(ctx)` (`:567-574`) →
imperative `pytest.xfail` on e2e_rest. So the scenario is declared-unrunnable over e2e, not silently
broken. No ledger entry needed (the declaration is the mechanism).

Two observations on that declaration, both against #1739's theme:

- Its stated cause — *"factory-created creatives are not in Docker DB"* — looks **stale**.
  `db_session(ctx)` yields `env._session` (`tests/bdd/steps/_harness_db.py:17-20`), which over e2e is
  bound to the server DB engine (`_base.py:1136-1147`), and `_preseed_creative_for_principal`
  (`:6654-6697`) writes through the same factories. The read-back should work. Worth re-measuring
  before more scenarios are built on top of it.
- The FIXME cites a beads id (`salesagent-15cg`) in source, which the repo rule forbids — code
  comments take GitHub numbers.

If the lead wants this graded on e2e, the fix is to assert persistence through the wire (a follow-up
`list_creatives`/sync read-back) rather than a DB `select`.

### 12. `sb-uc006-multiformat` — E2E-WIREABLE, conditional on per-row assets

Runs (adds `@creative-invariant`). `Given the batch has been pre-synced <n> times` dispatches through
`dispatch_request` over the same transport — transport-neutral, no bypass, correct. Fixed creative
ids (`mf-display` etc.) are safe across runs because `_harness_env` flushes the shared e2e DB per
scenario (`conftest.py:3199-3200`).

**The condition.** The proposal builds every row's assets as `build_assets(image_spec("image"))`.
By F1 the live server resolves each `format_id` against the reference catalog and
`_validation.py:128-134` rejects an unresolvable one outright. The three reference formats declare
(executed):

- `display_300x250_image` → `banner_image, click_url, impression_tracker, viewability_tracker, click_tracker`
- `video_standard_30s` → `video_file, impression_tracker, viewability_tracker, click_tracker`
- `native_content` → `headline, body, thumbnail, author, click_url, disclosure, …`

`_format_payload`'s e2e branch (`uc006_sync_creatives.py:44-66`) already uses
`banner_image` + `click_url` for precisely this reason. Give each row assets matching its own format
(and keep `_format_payload`'s transport branch for `agent_url`, as the proposal already says).

Also note the undeclared in-process state this rides on in-process only:
`CreativeSyncEnv._configure_mocks` sets `registry.get_format = AsyncMock(return_value=…truthy…)`
(`tests/harness/creative_sync.py:85`) with no `realize_e2e`. In-process that accepts any format id;
over e2e format resolution is real. That asymmetry is exactly what the asset/format mismatch above
would expose.

### 13. `sb-uc006-fmtroundtrip` — BLOCKED by F2; e2e design otherwise sound

Tags `@storyboard-v3.1 @v3-1 @format-id-roundtrip` — no gate tag, and the proposal does not mention
the gate anywhere (it is the only UC-006 proposal in my batch with zero awareness of it). It xfails
on all four transports as written.

Its step design is the most e2e-literate in the batch: `_e2e_unique_id` for ids, `_product_format_entry`
/ `_format_payload` for the transport-correct `(agent_url, id)`, and a real same-transport
re-dispatch for `identical resubmission` (no in-process bypass, so no ledger entry needed).

One item belongs in the silent-breakage class: step 2's row-3 branch replaces
`registry.get_format` with an `AsyncMock(side_effect=…)` returning `None` for the unadvertised id.
That is in-process mock surgery with no `realize_e2e` declaration. It happens to be harmless — over
e2e `format_never_advertised` is genuinely absent from the reference catalog, so the live server
rejects it for real — but the patch should be guarded by `is_e2e(ctx)` so the step does not claim to
configure behaviour it is not configuring. The proposal's own framing ("harness-parity shim that
reproduces what e2e gets for free") is right; the guard makes it true in code.

The proposal correctly excludes the `context.correlation_id` echo on REST grounds — that judgement is
confirmed above at #5/#7 (`CreativeSyncEnv.build_rest_body` never forwards `context`).

### 14. `sb-uc006-reception` — NOT-E2E-WIREABLE, and BLOCKED by F2

Gate: tags `@schema-v3.1 @v3-1 @stateful-push @creative-reception` — not in the allow-set.

Independently of the gate, the reused Givens do not survive e2e:

`Given creative "<id>" does not exist for this principal` (`uc006_sync_creatives.py:6700`) and
`… exists for principal <p>` (`:6710-6712`) both land in `_build_creative_scope_payload`
(`:6632-6651`), which hardcodes:

```python
"format_id": {"id": "display_300x250", "agent_url": env.DEFAULT_AGENT_URL},
"assets": build_assets(image_spec("image")),
```

Bare `display_300x250` is **not** in the reference catalog (executed: only `display_300x250_image`,
`_html`, `_generative` exist), and `env.DEFAULT_AGENT_URL` is `https://creative.test.example.com`.
Over e2e the live server calls `fetch_format_spec` → `registry.get_format` → reference catalog (F1) →
`None` → `AdCPValidationError("Unknown format …")` (`src/core/tools/creatives/_validation.py:128-134`)
→ every row reports `action: "failed"`, so `the action should be "<created|updated>"` fails on all
three rows. This helper is the only creative-payload builder in the module that is **not** routed
through the e2e-aware `_format_payload` — that is the defect.

Remediation: make `_build_creative_scope_payload` call `_format_payload(ctx, env)` like its siblings.
That is a one-line harness fix and it also unblocks whatever else reuses those Givens.

**Correction to a load-bearing claim in the proposal.** It states the Examples table is "lifted from
the already-green `@T-UC-006-partition-creative-scope` outline (feature lines 768-779), so the three
rows are proven to produce those actions on current production". That outline carries
`@partition @creative-scope` (`BR-UC-006-sync-creatives.feature:768`), is not in the F2 allow-set, and
is therefore fixture-xfailed on every transport. It is dormant, not green — the rows are unproven.

---

## 3. Dead IMPL assumptions

IMPL is not in the parametrized set (`conftest.py:2871-2891`: `[A2A, MCP, REST]` + `E2E_REST`).
Every item below reasons about a branch that never executes.

| Where | Text | Note |
|---|---|---|
| `repin-uc005-baseline` §6 item 3 | extracts `_serialized_response` from `_serialized_formats`, described as keeping "single wire/IMPL branch" | the IMPL half of `wire_field` (`tests/bdd/steps/_outcome_helpers.py:37-40`) is dead. Harmless, but the new helper should not be justified by it |
| `repin-uc005-roundtrip` §5 "Modified" | "`_call_via` already forwards `context` on IMPL/A2A/MCP" | names the dead transport and, more importantly, **omits REST** — which is exactly where it breaks (#5) |
| `repin-uc005-thirdparty` §5.2 | "`Then the formats array should contain exactly {count:d} entries` — … (wire on REST/A2A/MCP, production serializer on IMPL)" | dead IMPL branch |
| existing code, `tests/bdd/steps/domain/uc005_format_id_shape.py:12-16` | module docstring: "IMPL has no wire, so it asserts the production serializer output … exercises `NestedModelSerializerMixin`" | dead; the three uc005 proposals all inherit this framing |
| existing code, `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:103-108` | `then_response_schema_valid` docstring: "or the production-serialized payload on IMPL" | dead |

None of these changes a verdict on its own. `wire_field` raises loudly when a non-IMPL transport has
no `wire_response` (`_outcome_helpers.py:33-36`), so the dead branch cannot degrade into a silent
tautology — the phrasing is stale, not dangerous.

---

## 4. In-process state with no `realize_e2e` declaration (the silent-breakage class)

`_base.py:1152-1159` starts `EXTERNAL_PATCHES` unconditionally, including over e2e — in the *test*
process, where the live server never sees them. Anything below that a step calls over e2e is a no-op
that reads as configuration.

**Harness methods, existing:**

| Method | File | Reached by this batch? |
|---|---|---|
| `set_policy_approved` / `set_policy_blocked` / `set_dynamic_variants` / `set_property_list` / `set_ranking_disabled` | `tests/harness/_mixins.py:512-558` (`ProductMixin`) | not called by `sb-uc004-vendormetric`, but its `ProductEnv` starts the patches |
| `set_run_async_result`, `setup_generative_build` | `tests/harness/creative_sync.py:159`, `:106` | not called by this batch |
| `CreativeSyncEnv._configure_mocks` — `registry.get_format` truthy, `run_async` → `[]` | `tests/harness/creative_sync.py:78-104` | **yes**, implicitly, by every UC-006 scenario; it is what makes #12/#14 diverge between in-process and e2e |
| `set_http_status` / `set_http_sequence` / `set_http_error` / `set_url_invalid` / `set_http_response` | `_mixins.py:266-295`, `:377-395` | not in this batch (covered by the tag-based `_UC004_E2E_WEBHOOK_INTERNAL_TAGS` xfail, `conftest.py:601-620` — a second, parallel mechanism to `realize_e2e`) |

**Proposed steps that would add to the class:**

1. `repin-uc005-thirdparty`, `Given the seller hosts no format under the third-party agent_url "…"` —
   if it inspects `env.mock["registry"]`, it asserts nothing over e2e. Derive from the reference
   catalog instead.
2. `sb-uc006-fmtroundtrip`, step 2 row 3 — the `registry.get_format` `AsyncMock` replacement. Guard
   with `is_e2e(ctx)`.

---

## 5. Ledger entries to REMOVE

**None.** Every not-wireable case in this batch resolves to a fix or an existing declared mechanism:

- #5 `repin-uc005-roundtrip` fails on `rest` as well as `e2e_rest`, so a ledger entry (which is
  `e2e_rest`-only, `conftest.py:2722-2730`) cannot cover it. Fix or drop the clause.
- #11 `sb-uc006-prov-contradicted` is already covered by the env-level `_xfail_if_e2e` declaration.
- #12 / #14 are harness fixes, not permanent gaps.
- #8/#10/#13 are blocked by the UC-006 tag gate on all transports — a routing decision, not a ledger
  item.

---

## 6. Finding against GH #1739 — the three uc005 ledger entries and their header

`tests/bdd/e2e_rest_known_failures.txt:122-137` groups ten entries under
*"parallel e2e_rest mock-injection artifacts … UC-004 `set_adapter_response` (delivery), UC-005
`set_registry_formats`, UC-018 injected cross-principal creatives — none visible to the separate HTTP
server."* The same claim is repeated in the loader comment at `tests/bdd/conftest.py:30-32` and in
`tests/unit/test_e2e_rest_ledger_state.py:68`.

**Both named mechanisms are now realized, so the stated cause is wrong for at least seven of the ten
entries.**

The three uc005 entries (`:132-134`):

| Entry | Does it call `set_registry_formats`? | Assessment |
|---|---|---|
| `test_baseline_list_creative_formats_response_carries_format_id_objects_with_agent_url_and_id[e2e_rest]` | **No.** Its only Given is `when_request.py:130` (a bare dispatch) | annotation is **wrong**; whatever fails is something else |
| `test_format_id_roundtrip__…[e2e_rest]` | **No.** `uc005_format_id_roundtrip.py:29-79` seeds by factory + an in-process `_get_products_impl` capture | annotation is **wrong** |
| `test_format_id_with_agent_url_pointing_at_a_thirdparty_creative_agent_…[e2e_rest]` | **Yes** (`uc005_format_id_third_party.py:61`) | but over e2e `set_registry_formats` is REALIZED, and `_validate_registry_formats` **no-ops** for this fixture because `display_300x250_image` is in the reference catalog. So "mock injection invisible to the server" is not the failure mode either |

Add F1: with `ADCP_TESTING=true` the live server serves the *same* 57 reference formats under the
*same* canonical `agent_url`, so the seller-catalog premise these scenarios need is satisfied
server-side by construction. There is no injection gap left to explain any of the three.

I cannot run the in-network suite from here, so I will not claim the three now xpass — the honest
statement is: **the recorded cause is falsified for all three, and they need one in-network
measurement to decide graduate-vs-re-annotate.** Note that whatever the outcome, the annotation and
the two comment copies must be corrected in the same change; `test_e2e_rest_ledger_state.py` locks the
file, so the stale prose is currently guarded as if it were true.

Same reasoning applies to the four uc004 entries in that block (`:128-131`), which cite
`set_adapter_response` — realized since #1418, persisting a `DeliverySimulationConfig` row that the
server reads including `by_geo`/`by_device_type` (`_mixins.py:144-153`, `mock_ad_server.py:1155`).
They are in my batch's UC and carry the same falsified cause. The three UC-018 entries (`:135-137`)
are outside my batch and I did not analyse them.

Secondary, same theme: `conftest.py:565-595` `_UC005_E2E_FIXTURE_INJECTION_TAGS` xfails 14 UC-005 tags
with `reason="E2E: set_registry_formats has no sidecar mock — real creative agent catalog used"`.
That reason is stale for the same reason. Those scenarios now take one of two realized paths — either
their fixture is a reference-catalog subset (the realizer no-ops and they may pass) or it is not (the
realizer raises `E2EUnsupportedSetup` and the env-owned xfail fires). Either way the tag list is a
redundant third mechanism sitting on top of the declared one.

---

## 7. Uncertainties

1. **No in-network run.** Everything above is static tracing plus in-process execution of the pieces
   that do not need Docker (`load_reference_formats()`, model configs, the reference-format asset
   lists). The graduate-vs-re-annotate call in §6 needs one `BDD_E2E_ENABLED=true` run.
2. **Docker creative-agent catalog vs the checked-in fixture.** My F1 conclusion rests on
   `ADCP_TESTING=true` short-circuiting to `_get_reference_formats()` *before* any HTTP call
   (`creative_agent_registry.py:654`, `:763`). If any live code path reaches the `creative-agent`
   container instead, the catalog could differ and #6/#12/#14 change. I checked the two list paths
   and `get_format`; I did not audit every registry entry point.
3. **Asset-manifest validation depth (#12).** I confirmed *format resolution* is strict
   (`_validation.py:128-134`). I did not fully trace whether the per-asset manifest is checked against
   the format's declared asset ids downstream in `_processing.py`. If it is not, #12's asset mismatch
   might survive e2e — but `_format_payload`'s e2e branch deliberately uses `banner_image`/`click_url`,
   which suggests it is. Treat the asset fix as required regardless.
4. **`_xfail_if_e2e` staleness (#11).** My read of `db_session` → `env._session` → server engine says
   the DB read-back would now work over e2e. I did not execute it. If the lead wants that declaration
   retired, it needs a measurement, not this analysis.
5. **UC-006 gate intent.** I report F2 as a fact about the code. Whether `prov-dst`,
   `prov-corrected`, `fmtroundtrip` and `reception` *should* get `@creative-invariant` (or the gate
   should be widened) is a routing decision for the lead — `sb-uc006-multiformat` and
   `sb-uc006-prov-contradicted` set the precedent, and #12's proposal argues the tag's stated meaning
   ("success-variant response invariants") fits.

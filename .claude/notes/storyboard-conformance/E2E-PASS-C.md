# E2E-PASS-C — e2e-wireability audit, batch C (11 scenarios)

Repo: `/Users/konst/projects/salesagent-sbsweep` @ `692e5dfa4`. Read-only; nothing edited.

Two facts dominate this batch and were established empirically, not by reading:

1. **`_harness_env` is autouse and xfails every unknown UC.** `tests/bdd/conftest.py:3184`
   (`@pytest.fixture(autouse=True)`) → `_detect_uc` (`:3064`) → `else: pytest.xfail(f"No harness
   wired for {uc}")` (`:3532`). `_detect_uc` recognizes only UC-002/003/004/005/006/011/018/019,
   ADMIN, UC-GET-PRODUCTS, COMPAT. Proof: `BR-UC-026` **is** bound (`tests/bdd/test_uc026_package_media_buy.py:9`)
   and `uv run pytest tests/bdd/test_uc026_package_media_buy.py` → **728 xfailed, every one
   "No harness wired for None"**. So a scenario tagged `@T-UC-008/014/020/021/030-*` xfails on
   **all four** params the moment it is bound — even a scenario that dispatches nothing and only
   reads vendored JSON. The `_harness_env` docstring's "Unknown UC → no harness (yields
   immediately)" is stale.
2. **The `realize_e2e` question does not arise anywhere in this batch.** No proposal in batch C
   calls `set_adapter_response`, `set_adapter_error`, or `set_registry_formats`, and the three
   UC-018 proposals seed exclusively through `CreativeFactory` DB writes, which the live server
   reads (`_production_db_pointed_at`, `conftest.py:3136`; the server DB is TRUNCATEd per e2e
   scenario at `conftest.py:2947`). The one exception is a *new* setup capability proposed by
   sb-uc021-preview (§4 below).

---

## 1. Summary table

| Scenario | Verdict | Breaking step / blocker | Remediation |
|---|---|---|---|
| sb-uc008-baseline | **NOT-E2E-WIREABLE** — and not wireable on *any* transport | `When … calls get_signals / activate_signal` — tool registered on no transport | Register a signals provider surface (MCP+A2A+REST) + new `SignalsEnv` + `_detect_uc` UC-008 branch. Nothing to ledger; the scenario cannot collect green today. |
| sb-uc008-agentdest | **E2E-WIREABLE in mechanism, blocked at the fixture** | none in the Gherkin; `_harness_env` xfails `T-UC-008-*` | Add a `_detect_uc` branch that yields with no env for schema-only UCs; **and** vendor `core/activation-key.json` (`deployment.json`'s `$ref` is a hard failure today) |
| sb-uc008-platformdest | **NOT-E2E-WIREABLE** — not wireable on any transport | `When … sends activate_signal with … destinations` — unregistered tool | Same as baseline. Also the wrapper discards `destinations` even if reached. |
| sb-uc014-session | **E2E-WIREABLE in mechanism, blocked at the fixture** | none in the Gherkin; `_harness_env` xfails `T-UC-014-*` | Same no-env branch; **and** the SI schemas are not vendored at all — the Given has no source to load from |
| sb-uc018-listall | **E2E-WIREABLE** | — | None required. Note the "no cursor" Then grades a re-serialization, not the e2e wire (§6). |
| sb-uc018-fmtfilter | **E2E-WIREABLE** | — | Add `"format-id-object"` to the wired-marker set at `conftest.py:3405`, else it xfails on all 4 params. Stash `ctx["result"]` in the new When or the wire-first error steps degrade (§4). |
| repin-uc018-conceptid | **E2E-WIREABLE — but the proposal's ledger claim is wrong** | — | Its nodeid **is** on the ledger (`e2e_rest_known_failures.txt:137`) and pinned in `tests/unit/test_e2e_rest_ledger_state.py:79`. The rewrite renames the scenario → the pinned entry stops collecting and 4 new e2e_rest nodeids run unprotected. Must be updated in the same PR (§5). |
| sb-uc019-statuspoll | **E2E-EXEMPT (UC-019)** | — | None. Confirmed from source; no remediation invented. |
| sb-uc020-vast | **NOT-E2E-WIREABLE** — not wireable on any transport | `When the Buyer Agent sends a build_creative request` — `build_creative` exists nowhere in `src/` | Implement + register the tool, then env + `_detect_uc` branch. |
| sb-uc021-preview | **NOT-E2E-WIREABLE** — not wireable on any transport | `When … sends preview_creative …` (unregistered) **and** `Given the creative agent returns a render …` — new in-process mock with no realizer | Tool first; then the render-injection Given needs `@realize_e2e(...)` or an explicit `e2e_unsupported(...)` (§4). |
| sb-uc030-govbinding | **NOT-E2E-WIREABLE as proposed** (tools exist; the read-back leg bypasses the wire) | `When the Buyer Agent sends a list_accounts request` → `uc011_accounts.py:363` TRANSPORT-BYPASS calls `_list_accounts_impl` in-process under `AccountSyncEnv` | Composite account env (precedent: `tests/harness/media_buy_dual.py`) so both `sync_accounts` and `list_accounts` dispatch on the wire; plus a `_detect_uc` UC-030 branch. |

---

## 2. Per scenario

### sb-uc008-baseline — NOT WIREABLE ON ANY TRANSPORT

Setup steps and their real destination:

| Step | Classification | Evidence |
|---|---|---|
| `Given the Buyer Agent is authenticated for the default tenant` | **Does not exist.** Proposal claims "an auth given of this shape lives in `tests/bdd/steps/generic/given_auth.py`" — that module's givens are `a valid tenant context exists` / `the Buyer has tenant context` (`given_auth.py:15-16`), `the Buyer has tenant context via MCP session` (`:23`), `the Buyer has no authentication credentials` (`:34`). No phrasing matches. | `tests/bdd/steps/generic/given_auth.py:15-74` |
| `Given the Buyer Agent captured signal_agent_segment_id "<x>" from get_signals` | NEW; would be pure ctx state (safe in itself) | — |
| `When … calls get_signals` / `activate_signal` | **Dispatch to a tool registered on no transport.** | MCP: absent from the `_register_tool(...)` block, `src/core/main.py:351-366` (16 tools, none signals). REST: absent from the 12 routes in `src/routes/api_v1.py:223-486`. A2A: no signals import in `src/a2a_server/adcp_a2a_server.py:77-109`. Raw layer: `src/core/tools/__init__.py:25` — `# Signals tools removed - should come from dedicated signals agents, not sales agent`. |

Verdict: **NOT-E2E-WIREABLE**, and the more important answer per the task brief — **the scenario can
run on zero transports**. It is not an e2e gap; it is a missing product surface. No `e2e_rest_known_failures.txt`
entry is appropriate (the ledger xfails scenarios that *collect*; this one would xfail at
`_harness_env` first, on every transport equally).

All 17 Thens are NEW, so no existing step drags in-process state along.

### sb-uc008-agentdest — E2E-WIREABLE in mechanism; two blockers

The proposed Gherkin dispatches nothing. Both outlines are `Given the pinned AdCP schema "<file>"`
→ `When a … document is built …` → `Then the pinned schema validation outcome should be "<outcome>"`,
reading `tests/fixtures/adcp_schemas_pinned/` through `tests/helpers/pinned_schema.py`. No env, no
DB, no mock, no transport. That is genuinely transport-independent — the one construction in this
batch that is e2e-safe by having nothing to realize.

Blockers, both real:

- **Fixture xfail.** Tagged `@T-UC-008-…`, so `_detect_uc` returns `None` → `pytest.xfail("No harness
  wired for None")` (`conftest.py:3532`) on a2a/mcp/rest/e2e_rest alike. A schema-only scenario is
  **not free**: it needs a `_detect_uc` branch that yields without constructing an env.
- **The `$ref` closure is broken.** `tests/fixtures/adcp_schemas_pinned/core/` contains
  `deployment.json` but **not** `activation-key.json` (verified: `ls .../core/ | grep -i activation` →
  empty). `pinned_schema.py:36-40` raises `AssertionError: Pinned schema not vendored` on a missing
  ref — a hard failure, by design. So `Given the pinned AdCP schema "activation-key.json"` fails on
  `_resolve_filename` (`:47-52`) and `deployment.json` fails the moment its `activation_key` ref is
  followed. Re-run `tests/fixtures/adcp_schemas_pinned/_refresh.py` before writing these steps.
  The proposal states this in its §7; it is correct and it gates its own §5.

### sb-uc008-platformdest — NOT WIREABLE ON ANY TRANSPORT

`When the Buyer Agent sends activate_signal with idempotency_key … and one destination of type
"platform" …` targets the same unregistered tool (evidence as in baseline). Additionally, even given
a transport, `src/core/tools/signals.py:239-247` hardcodes `destinations=[{"type": "platform",
"platform": "mock"}]` and synthesises the idempotency key, and the wrappers (`:317-323`, `:366-373`)
accept neither parameter — so the wire-supplied destination could not reach `_impl`. The Given
`the seller's platform activation for "the-trade-desk" resolves <mode>` is NEW and would require a
new mock-injection capability; it must not be written without a `realize_e2e` decision, but that
question is downstream of the tool existing at all.

### sb-uc014-session — E2E-WIREABLE in mechanism; two blockers

Same construction as uc008-agentdest: three schema-reading steps, no dispatch, no env. Same
fixture-xfail blocker (`T-UC-014-*` → `_detect_uc` → `None`).

Second blocker: **the SI schemas are not vendored**. `ls tests/fixtures/adcp_schemas_pinned/` →
`account core creative enums media-buy pricing-options signals` — no `sponsored-intelligence`
directory, and no `si-*.json` anywhere. The Given "loads the schema from the adcp pin" therefore has
no in-repo source; either vendor the three `si-*-response.json` + `enums/si-session-status.json`
files, or the steps must read from the external adcp checkout, which is not how any other step in
this repo resolves schemas. The proposal names this in §7 and is right to.

Note the SI tools (`si_initiate_session` / `si_send_message` / `si_terminate_session`) appear in no
`src/` registration site either — but the proposed Gherkin never calls them, so that is not a
wireability blocker for *this* scenario.

### sb-uc018-listall — E2E-WIREABLE

| Step | Classification | Evidence |
|---|---|---|
| `Given the Buyer is authenticated as principal "{id}"` (Background) | ctx + env principal switch, no mock | `tests/bdd/test_uc018_list_creatives.py:148-162` → `tests/bdd/steps/generic/_auth.py::authenticate_env_as` |
| `Given the buyer recently synced three creatives in three different formats via sync_creatives` | **DB write.** `CreativeFactory` via `_seed_creative`, tenant/principal via idempotent `get_or_create` | `test_uc018_list_creatives.py:164-180`, `_seed_creative:86-118`, `_get_or_create_tenant_and_principal:123-145` |
| `When the Buyer Agent sends list_creatives with no filters for the same account` | wire dispatch via `_call_via` | `test_uc018_list_creatives.py:182-197`; `tests/bdd/steps/generic/when_request.py:79-113` |
| all Thens | read `_serialized_response(ctx)` = `ctx["response"].model_dump(mode="json", exclude_none=True)` | `test_uc018_list_creatives.py:199-216` |

Over e2e_rest `ctx["response"]` is populated: `RestE2EDispatcher` parses the real HTTP body through
`env.parse_rest_response` (`tests/harness/dispatchers.py:312-315`; `tests/harness/creative_list.py:101-103`),
so the typed payload exists on e2e exactly as in-process. `build_rest_body` forwards nothing this
scenario needs to drop (`creative_list.py:86-99`).

Confirmation from the current state: the existing scenario's nodeid is **not** on
`tests/bdd/e2e_rest_known_failures.txt` — the unfiltered-list path already passes in-network. The
rewrite changes it to a `Scenario Outline` (3 rows) and adds count/order/pagination assertions; the
mechanism is unchanged, so it stays e2e-wireable. No new ledger entries.

Two honesty notes, neither breaking:
- The `pagination should report … with no cursor` Then asserts on the **re-serialized** typed model,
  not the wire. `src/routes/api_v1.py:459` returns `response.model_dump(mode="json")` **without**
  `exclude_none`, so the real e2e wire body carries `"cursor": null`. `"cursor" not in pagination`
  would be false on the wire and true on `_serialized_response`. The proposal's choice is
  deliberate and correct for wireability, but the assertion does not grade buyer-visible bytes.
- Ordering by `created_date desc` across three rows committed in one factory burst is the only
  redness risk, and it is transport-independent.

### sb-uc018-fmtfilter — E2E-WIREABLE

Seeding is `_seed_creative`/`CreativeFactory` (DB) as above. The interesting half is the rejection
outline, and it survives e2e:

- The raw payload reaches the server. `ListCreativesBody.filters` is typed `dict[str, Any] | None`
  (`src/routes/api_v1.py:158`), so a bare-string / missing-`agent_url` / empty-array `format_ids`
  passes FastAPI body validation untouched, and `build_rest_body` forwards `filters` verbatim
  (`tests/harness/creative_list.py:94-98`).
- The rejection is produced by **route code**, not FastAPI: `coerce_creative_filters(body.filters)`
  (`src/routes/api_v1.py:435`) → `adcp_validation_boundary` (`src/core/schema_helpers.py:216`) →
  typed `AdCPValidationError` carrying a suggestion. The live server runs the same app, so the real
  HTTP response is the same two-layer envelope, captured by `RestE2EDispatcher` as
  `wire_error_envelope` (`dispatchers.py:295-308`) and reconstructed with `recovery`/`suggestion`
  intact by `parse_rest_error` → `_envelope_to_adcp_error` (`tests/harness/_base.py:1005-1024`).
  This is *not* the FastAPI-422 path, so the `{"detail": [...]}` degradation at `_base.py:1015-1020`
  never applies here.

Two required changes, both in-scope for the same PR:
- **`conftest.py:3405`** — the UC-018 wired-marker set is `{"list-after-sync", "concept-id",
  "BR-RULE-034"}`. Without `"format-id-object"` the scenario hits
  `pytest.xfail("UC-018 harness wired only for …")` on all four params. The proposal names this.
- **`ctx["result"]` is not stashed by `_call_via`.** `when_request._call_via` sets only
  `error` / `response` / `wire_response` (`when_request.py:99-113`), whereas
  `steps/generic/_dispatch.py:62` sets `ctx["result"]`. `then_error._wire_code` and
  `_wire_suggestion` read `ctx["result"].wire_error_envelope` (`then_error.py:28-32`, `:35-42`) and
  return `None` when it is absent — so the two "wire-first" steps this scenario relies on
  (`the error code should be "VALIDATION_ERROR"`, `the error should include a "suggestion" field`)
  silently fall back to the reconstructed exception on **every** transport, e2e included.
  `the error recovery should be "correctable"` (`then_error.py:412-423`) never reads the wire at all.
  Not e2e-breaking, but the scenario claims wire grading it does not perform. The new When should
  stash `ctx["result"]` (or route through `dispatch_request`).

### repin-uc018-conceptid — E2E-WIREABLE, but the proposal's §7 is factually wrong

Mechanism is sound: the datatable Given routes through `_seed_creative` → `CreativeFactory` (DB
write, `test_uc018_list_creatives.py:86-118`), the When is the existing regex step at `:315-337`
(already parses multi-element lists, so row 3 needs no edit), and the Thens read `_wire_creatives`
(`:339-357`) — real wire bytes, which `RestE2EDispatcher` supplies over e2e
(`dispatchers.py:317-325`). `wire["pagination"].get("cursor") is None` is the right shape, since the
e2e wire carries `"cursor": null` rather than omitting the key.

**The correction.** The proposal states: *"this scenario is not on the ledger.
`tests/bdd/e2e_rest_known_failures.txt` contains zero lines matching `concept` and zero matching
`uc018`."* Both halves are false at this commit:

```
tests/bdd/e2e_rest_known_failures.txt:137
  tests/bdd/test_uc018_list_creatives.py::test_list_creatives_filtered_by_concept_ids_returns_only_creatives_in_that_concept_carrying_concept_id_and_concept_name[e2e_rest]
```
plus two sibling UC-018 entries (`test_brrule034_inv1_holds…`, `test_brrule034_inv1_counter…`) —
three `uc018` lines total, grouped under *"parallel e2e_rest mock-injection artifacts (10)"*, added
2026-07-09 under `E2E_PER_WORKER`. All three are pinned again in
`tests/unit/test_e2e_rest_ledger_state.py:77-79` (`EXPECTED_LEDGER` frozenset).

Consequence, and this is the actionable part: the rewrite renames the scenario
(`Scenario:` → `Scenario Outline: filters.concept_ids scopes the library to the requested concepts
-- <case>`), so the pinned nodeid **stops collecting** while four new `[e2e_rest]` nodeids start
running with no protection. `test_e2e_rest_ledger_state.py` only compares file↔frozenset — it never
checks that an entry still collects — so the stale entry stays green in unit tests while the
in-network job takes an unannounced new failure. That is exactly the silent-new-failure class. See §5.

(Whether the entry is still *needed* is a separate question worth answering in-network: the reason
recorded — "UC-018 injected cross-principal creatives … invisible to the separate HTTP server" —
describes the BR-RULE-034 pair, not the concept-id scenario, whose seeding is a plain DB write, and
`_reset_e2e_db` (`conftest.py:2947-2974`) TRUNCATEs the server DB per scenario. It may be a
graduatable artifact. Do not assume it; measure it.)

### sb-uc019-statuspoll — E2E-EXEMPT (UC-019)

Confirmed from source, as instructed:

- `tests/bdd/conftest.py:2832` — `_NO_REST_UC_TAG_PREFIXES = ("T-UC-019-",)`, with the comment
  "UCs whose tool has no REST route — parametrize across A2A + MCP only (a REST variant would 404)".
- `conftest.py:2883-2890` — `no_rest_uc` → `transports = [Transport.A2A, Transport.MCP]`, and the
  e2e append is guarded `if os.environ.get("BDD_E2E_ENABLED") == "true" and not no_rest_uc`. So
  e2e_rest is never generated for this scenario.
- Ground truth for the exemption: `src/routes/api_v1.py:223-486` has no `/media-buys/query` route.
  `tests/harness/media_buy_list.py:26` sets `REST_ENDPOINT = "/api/v1/media-buys/query"` — dead
  config pointing at a route that does not exist.

Record: **E2E-EXEMPT. No remediation.** The scenario runs a2a + mcp; the tag is in neither
`_UC019_XFAIL_TAGS` (`conftest.py:2072`) nor `_UC019_BOUNDARY_SELECTIVE`, so it runs unmarked once
the two new steps exist.

**Would an e2e_mcp driver change it?** Not by itself, and none exists. `McpE2EDispatcher`
(`tests/harness/dispatchers.py:335-340`) raises `NotImplementedError("E2E_MCP dispatcher is not yet
implemented")`; `A2AE2EDispatcher` (`:343-348`) likewise. Two changes would be needed: implement the
driver, **and** amend `pytest_generate_tests` (`conftest.py:2887-2890`), which appends
`Transport.E2E_REST` only. Tracked as GH #1430.

One flag on the proposed steps: `then_context_correlation_id_echoed` reads
`getattr(resp, "context", …)` off the **typed** response, not the wire. On a2a/mcp the harness does
stash `wire_response`, so the echo could be graded on real bytes; reading the typed model is weaker
than the storyboard check it cites.

### sb-uc020-vast — NOT WIREABLE ON ANY TRANSPORT

`build_creative` does not exist in `src/`: absent from the MCP registration block
(`src/core/main.py:351-366`), from all 12 REST routes (`src/routes/api_v1.py:223-486`), and from the
A2A tool imports (`src/a2a_server/adcp_a2a_server.py:77-109`). There is no `build_creative` harness
env (`ls tests/harness/` — 30 modules, none). `_detect_uc` has no UC-020 branch, so even the
schema-shaped Thens would xfail at `_harness_env`. The `When the Buyer Agent sends a build_creative
request` step has no dispatch target of any kind.

The rewrite is otherwise well-shaped for wireability (no transport branching, Examples-driven), and
none of its steps carries undeclared in-process state — the blocker is purely the missing surface.

### sb-uc021-preview — NOT WIREABLE ON ANY TRANSPORT; plus the one undeclared-state risk in this batch

`preview_creative` is not registered inbound anywhere (same three registration sites as above; the
only repo hits are an outbound `AsyncMock` on the creative-agent registry at
`tests/bdd/steps/domain/uc006_sync_creatives.py:2045`). No UC-021 in `_detect_uc`, no `uc021_*.py`
step module, no `scenarios()` binding.

Beyond the missing tool, this proposal contains **the only newly-proposed in-process-state setup in
batch C**:

> `And the creative agent returns a render with output_format "<output_format>" and dimensions 300x250`

That is creative-agent response injection. It has no server surface today — structurally the same
situation as `set_registry_formats`, whose realizer (`tests/harness/creative_formats.py:44-73`) can
only *validate* the intent against the live catalog and raises `E2EUnsupportedSetup` when the intent
is unrealizable. Whoever writes this env method must make an explicit `realize_e2e` decision — a
realizer, or `@realize_e2e(e2e_unsupported("<reason>"))`. Writing it undecorated is the silent-breakage
case (§4).

### sb-uc030-govbinding — NOT-E2E-WIREABLE AS PROPOSED (the interesting failure of this batch)

Unlike UC-008/020/021, the tools here **do** exist on every transport: `sync_accounts` and
`list_accounts` are MCP-registered (`src/core/main.py:352, 351`), A2A-imported
(`adcp_a2a_server.py:86, 100`) and REST-routed (`src/routes/api_v1.py:485` `/accounts/sync`,
`:474` `/accounts`). Both account envs are e2e-capable (`AccountSyncEnv.REST_ENDPOINT =
"/api/v1/accounts/sync"`, `account_sync.py:174`; `AccountListEnv.REST_ENDPOINT = "/api/v1/accounts"`,
`account_list.py:75`), and UC-011 already runs e2e_rest with only one ledger entry.

Step classification:

| Step | Classification |
|---|---|
| `Given the Buyer Agent has an authenticated connection` | env/ctx auth; safe |
| `Given an account … is bound to governance agent "<url>"` | **real wire dispatch** — `_sync_pre_create` (`uc011_accounts.py:111-141`) builds a `SyncAccountsRequest` and calls `dispatch_request` (`steps/generic/_dispatch.py:14`). Not a mock, not a raw DB write: e2e-safe and e2e-*correct*. |
| `When … rebinds … to governance agent "<url>"` | second `sync_accounts` dispatch; same |
| `When the Buyer Agent sends a list_accounts request` | **TRANSPORT-BYPASS** — `when_list_accounts_unfiltered` (`uc011_accounts.py:336-372`) branches on `isinstance(env, AccountSyncEnv)` and calls `_list_accounts_impl(identity=env.identity)` **in-process** (`:363-371`, comment `# TRANSPORT-BYPASS: cross-cutting list under sync env`). |

The bypass is the blocker. A scenario that both syncs and lists routes to the sync env
(`_detect_uc011_harness`, `conftest.py:3096-3112`: `has_sync and has_list → "sync"`), and one env has
exactly one `REST_ENDPOINT`, so the read-back leg cannot dispatch. Over e2e_rest the call would still
read the right database — `_db_scope_for` points production's engine at `e2e_config.postgres_url`
(`conftest.py:3163-3182`) — so the Thens would **pass**, having exercised no HTTP, no nginx, no auth
middleware and no serializer. An e2e row that passes while grading nothing is worse than a ledgered
failure, because nothing surfaces it. (The bypass is a governed escape hatch —
`tests/unit/test_architecture_bdd_no_direct_call_impl.py` requires the comment — but "declared" is
not "wire-grading".)

Second blocker: no UC-030 branch in `_detect_uc`, so as written every param xfails
"No harness wired for None".

Remediation: a composite account env on the model of `tests/harness/media_buy_dual.py:39` (which
extends `MediaBuyCreateEnv` with update dispatch precisely so a Given-creates/When-updates scenario
stays on the wire across a2a/mcp/rest). An `AccountDualEnv` routing `SyncAccountsRequest` →
`/accounts/sync` and `ListAccountsRequest` → `/accounts` removes the bypass for UC-011 as well.
Until then, do not ledger this — it is not a known e2e failure, it is an unwritten harness.

---

## 3. Dead IMPL assumptions

| # | Where | Text | Reality |
|---|---|---|---|
| 1 | `tests/bdd/test_uc018_list_creatives.py:190-192` (docstring of `when_list_creatives_no_filters`) — inherited unchanged by **sb-uc018-listall**, which reuses this step verbatim | "the helper maps a missing transport to IMPL" | False. `when_request._call_via` (`when_request.py:79-96`) accepts a `Transport` enum or one of `{"a2a","mcp","rest"}`; `None` falls through to `transport_map[None]` after the membership check and raises `RuntimeError: unrecognized wire transport None`. There is no IMPL fallback. |
| 2 | `test_uc018_list_creatives.py:352-355` (`_wire_creatives` guard) — depended on by **repin-uc018-conceptid** | "IMPL (and the unparametrized None default) legitimately have no wire" | The IMPL half is dead: `pytest_generate_tests` (`conftest.py:2871-2892`) never emits `Transport.IMPL`. Harmless, but the comment reasons about a path that cannot execute. |
| 3 | `test_uc018_list_creatives.py:35-44` (module docstring) — context for all three UC-018 proposals | "The repo sunsets the IMPL pseudo-transport in BDD…" then describes `_serialized_response` as the oracle | Accurate on the sunset; but the surrounding claim that the Then steps "validate its production JSON serialization" is what makes the `cursor`-absence assertion non-wire over e2e (§2, listall). |
| 4 | `tests/bdd/conftest.py:3178-3183` (`_harness_env` docstring) — governs every unbound-UC proposal in this batch | "Unknown UC → no harness (yields immediately)" | False since the `else: pytest.xfail(...)` at `:3532`. Empirically: 728/728 UC-026 params xfail with "No harness wired for None". Every proposal in this batch that reasons "my scenario needs no env, so it is free" is reasoning against this stale docstring. |
| 5 | `sb-uc008-baseline` §6 | "an auth given of this shape lives in `tests/bdd/steps/generic/given_auth.py`" | No matching phrasing exists (`given_auth.py:15-74`). |
| 6 | `repin-uc018-conceptid` §7 | "this scenario is not on the ledger … zero lines matching `concept` … zero matching `uc018`" | False; 3 `uc018` lines, one of them this scenario (`e2e_rest_known_failures.txt:137`). |

No proposal in batch C reasoned about an "IMPL fallback" for `_serialized_*` in the sense the brief
warned about — the UC-018 proposals use `_serialized_response` as a *transport-uniform* oracle, which
is a different (and defensible) claim, subject to the `exclude_none` caveat above.

---

## 4. Steps with in-process state and no `realize_e2e` declaration

Batch C introduces **one** proposed setup capability in this class:

| Proposed step | Proposal | Why it is the silent-breakage class |
|---|---|---|
| `And the creative agent returns a render with output_format "<x>" and dimensions 300x250` | sb-uc021-preview §5 | Injects a creative-agent response. There is no `PreviewEnv`; whoever writes it will add a `set_*` method on a new env. If undecorated, in-process transports mock it and e2e_rest silently reads whatever the live creative-agent registry returns — a passing-but-meaningless e2e row, not a visible failure. Must carry `@realize_e2e(<realizer>)` or `@realize_e2e(e2e_unsupported("…"))`. |

For completeness, the **existing** harness methods that touch mocks and carry no `realize_e2e`
declaration (AST scan of `tests/harness/*.py`; none is used by batch C, but they are the standing
inventory of this class):

| Method | File:line |
|---|---|
| `WebhookMixin.set_http_status` / `set_http_sequence` / `set_http_error` / `set_url_invalid` | `tests/harness/_mixins.py:266, 274, 288, 292` |
| `CircuitBreakerMixin.set_http_response` / `set_http_sequence` | `_mixins.py:377, 387` |
| `ProductMixin.set_policy_approved` / `set_policy_blocked` / `set_dynamic_variants` / `set_property_list` / `set_ranking_disabled` | `_mixins.py:512, 527, 538, 546, 554` |
| `CreativeSyncEnv.setup_generative_build` / `set_run_async_result` | `tests/harness/creative_sync.py:106, 159` |
| `DeliveryPollEnv.set_pricing_options` (unit env) | `tests/harness/delivery_poll_unit.py:122` |

Declared today, for reference: `set_adapter_response` → `_persist_simulation_config` (REALIZED,
`_mixins.py:201`), `set_registry_formats` → `_validate_registry_formats` (REALIZED with conditional
`E2EUnsupportedSetup`, `creative_formats.py:113`), `set_adapter_error` (UNSUPPORTED, `_mixins.py:206-210`).

---

## 5. Ledger entries to REMOVE

Only one scenario in batch C touches the ledger, and it is a **removal + replacement**, not a new gap.

**Remove** (`tests/bdd/e2e_rest_known_failures.txt:137` **and** the identical string in
`tests/unit/test_e2e_rest_ledger_state.py:79` `EXPECTED_LEDGER` — the unit test asserts exact set
equality and fails on either side drifting):

```
tests/bdd/test_uc018_list_creatives.py::test_list_creatives_filtered_by_concept_ids_returns_only_creatives_in_that_concept_carrying_concept_id_and_concept_name[e2e_rest]
```

**Then decide, in-network, per row.** The rewrite produces four `[e2e_rest]` params. Shape (pytest-bdd
slugifies the scenario name, appends `__<examples-table-name>`, and the param id is
`<transport>-<row cells>`):

```
tests/bdd/test_uc018_list_creatives.py::test_filtersconcept_ids_scopes_the_library_to_the_requested_concepts__concept_filter_partitions_the_library[e2e_rest-one concept spanning two formats-…-2-2]
…[e2e_rest-a different concept with a single member-…-1-1]
…[e2e_rest-two concept ids return the union-…-3-3]
…[e2e_rest-an unknown concept id returns no members-…-0-0]
```

Capture the exact ids with
`uv run pytest tests/bdd/test_uc018_list_creatives.py --collect-only -q` after the rewrite — do not
hand-write them. If the in-network run shows them green (plausible: `_reset_e2e_db` TRUNCATEs per
scenario and the seeding is a plain DB write), add **nothing** and the net effect is a ledger
shrink of one. If red, fix the realizer or re-express the Then — a red row is NOT a licence to add
a ledger entry. The ledger only shrinks; if a row genuinely cannot be fixed in this pass, that is an
escalation with a stated reason, not a routine addition.

No other batch-C scenario produces a ledger entry: UC-019 never generates an `[e2e_rest]` param;
sb-uc018-listall's current nodeid is already absent from the ledger and its mechanism is unchanged;
sb-uc018-fmtfilter is new and, if it fails in-network, that failure must be diagnosed rather than
ledgered on arrival; and the six unbound-UC scenarios xfail at `_harness_env` on every transport,
which is not what the ledger is for.

---

## 6. Uncertainties

1. **Whether the concept-id ledger entry is still live.** Its recorded reason describes the
   BR-RULE-034 pair ("injected cross-principal creatives"), not concept-id, whose setup is a plain
   `CreativeFactory` write. I could not run the in-network e2e job from here. It may be a stale
   artifact of the `E2E_PER_WORKER` rollout. Verify before/after the rename; do not assume either way.
2. **Ordering determinism in sb-uc018-listall.** The three-row Outline pins position↔format↔sync-order
   under `created_date desc`. Three factory rows committed in one burst can share a timestamp. The
   proposal says it verified this against live dumps on a2a/mcp/rest; I did not re-run it. Transport-
   independent either way, so not an e2e-specific risk.
3. **`ContextObject` echo over the wire (sb-uc019).** I did not verify that a2a/mcp actually stash a
   `wire_response` for `get_media_buys` in `MediaBuyListEnv`, only that the proposed Then reads the
   typed model instead. If the wire is stashed, the step should read it.
4. **Whether the "schema-only scenario" pattern is wanted at all.** Two proposals (uc008-agentdest,
   uc014-session) are transport-independent by construction, which makes them e2e-safe but also makes
   them run four identical times. Adding a `_detect_uc` no-env branch is the mechanical fix; whether
   the repo wants schema-shape scenarios inside the transport-parametrized BDD suite (versus a plain
   test module) is a lead call I am not making.
5. **`sync_governance` vs `sync_accounts` for UC-030.** I verified `sync_governance` is registered
   nowhere and that the proposal's Givens ride the binding on `sync_accounts` instead. Whether that
   substitution is acceptable is a spec question, out of scope here; it does not change the
   wireability verdict, which turns on the `list_accounts` TRANSPORT-BYPASS.

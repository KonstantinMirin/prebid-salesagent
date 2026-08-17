# PR #1858 — Round 2 Architecture Remediation Plan (frozen)

**Status**: FROZEN scope authority for `plan-lane-execute`. Later `## ALTERATIONS`
sections (appended under a lane, never edited in place) win over the original text
of that lane.

**Source**: multi-agent review at
`/Users/konst/.local/state/pr-review-queue/prebid-salesagent/queue/170826_1931/`
(`review-architecture.md`, `review-intent.md`, eight dimensional reviews folded
in as evidence). Reviewed head: `6d16d9b1e` (worktree
`salesagent-sbsweep-pr1858`, branch `pr-1858-review`) — one commit behind this
branch's HEAD at authoring time (`cd72fe443`, `test/storyboard-binding-baseline`).
Intent verdict: **Drifted** on the production half (#1512/#1193); §§1–3
(runner, check index, transport-generic client) **Achieves** #1247 and need
finishing, not redesign.

**Why this doc exists**: round 1 (`salesagent-vuz9t`, 37 tasks) closed real
findings but did not touch architecture — each review round since has found a
new instance of the *same* missing seam, one layer deeper. This plan names the
seven seams once, as the frozen goal for `plan-lane-execute`'s per-lane
solution-review (`review-intent`, graded against THIS doc, not re-derived) and
diff-review (`review-layering`, graded against the actual diff). Six lanes
below correspond to the review's AR-01…AR-07 findings, with AR-01+AR-05 merged
(literally the same seam, stated explicitly in the review).

**Meta-invariant that governs all six lanes**: a shared seam gets exactly ONE
implementation, and something in the diff makes it structurally impossible to
add a second one (a guard, a base-class delegation, a deleted exemption arm) —
not merely "this instance is now correct."

---

## Lane A — Request/response normalization seam (AR-01 + AR-05)

**Priority: P0, blocking.** This is a live correctness regression, not
architecture debt: `update_media_buy` accepts `canceled: true` and returns
success while the buy stays live and spending; `sync_creatives` drops a
schema-**required** `idempotency_key`, so a retried write silently
re-executes. CLAUDE.md's "No Quiet Failures" rule, inverted, on the money path.

**Core Invariant**: request-field acceptance is decided once, at the seam
every transport already crosses (wire dict → pinned SDK request model →
`_impl`), never at a transport's argument-binder signature — and a
body-semantic field is always honored or refused, never silently dropped.

**Scope**:
- `src/core/version_compat.py` — `accepts_spec_request_fields` /
  `_strip()` (:299 union, :308-323 strip), `spec_response_model` (dead in
  production, `tests/harness/client.py`-only — decide whether it moves there
  or stays with a doc comment; do not leave "owned by two concerns" silently).
- `src/core/main.py:351` — MCP registration chokepoint.
- The 6 hand-decorated `_raw()` functions + `activate_signal_raw` (currently
  unaccounted — decorated nowhere, excluded nowhere).
- `tests/unit/test_architecture_rest_body_completeness.py:74`
  `_decorator_injected_params()` and its inline twin in
  `tests/unit/test_raw_function_parameter_validation.py:52-56`.
- `tests/integration/test_raw_wrapper_spec_fields_accepted.py:47-72`,
  `tests/integration/test_spec_request_fields_accepted.py:96-125`.
- `@T-UC-003-storyboard-not-cancellable-on-recancel` (zero bound steps today).
- AR-05's three context-echo sites, same seam from the response side:
  `src/core/tools/task_management.py:121-131` (hand-built dict,
  `model_dump()` inside `_impl`), `src/a2a_server/adcp_a2a_server.py:1710,1858`
  (`ContextObject(**ctx_param)` duplicated instead of calling
  `src/core/schema_helpers.py:58 to_context_object()`), `get_task`/
  `complete_task` (no `context` param at all — sibling omission).

**Steps** (correct design, not the staged smallest-change — this lane owns
the full seam move):
1. Split the accepted-field set into two classes at the decorator: envelope
   (`adcp_version`, `adcp_major_version`, `context`, `context_id`,
   `governance_context`, `idempotency_key` on reads) stays accept-and-ignore
   — this is the entirety of what #1512 asked for. Everything else
   (`canceled`, `cancellation_reason`, `account`, `buying_mode`, `refine`,
   `total_budget`, `io_acceptance`, `push_notification_config`,
   `idempotency_key` on writes, …) moves to step 2.
2. At the shared seam (not per-transport), parse the wire dict into
   `spec_request_model(tool)`/`pinned_request_schema_fields(tool)` and thread
   the model to `_impl`. `_impl` honors the field or raises an explicit
   `AdCPError` — no third option. This is what makes #1193 step 3 ("pass
   `ext=ext` through to the request object constructor") reachable for the
   first time.
3. Because acceptance now lives at the model-construction seam, all four
   transports inherit it by construction: delete `_decorator_injected_params()`
   and its inline REST-completeness twin (nothing left to exempt); fold
   `activate_signal_raw` into the same mechanism, no special case; regrade both
   guards against `pinned_request_schema_fields(tool)`, not `model_fields`.
4. `__spec_required_fields__` either gets the real consumer the design implies
   (a place that reads it to decide honor-vs-refuse) or is deleted — it may not
   remain computed-and-unread.
5. AR-05: call `to_context_object()` at both A2A sites instead of the
   duplicated `isinstance` coercion; give `list_tasks` a declared response
   model so `model_dump()` leaves the tool body; extend the echo to `get_task`/
   `complete_task` so all task tools agree.
6. Wire `@T-UC-003-storyboard-not-cancellable-on-recancel` and one
   envelope-tolerance scenario through `dispatch_via_client` (needs Lane B's
   client, or `dispatch_request` if B hasn't landed yet — do not block A on B;
   use whichever dispatcher is live at implementation time) so the contract is
   graded on mcp/a2a/rest, not by `isinstance` on one door.

**§5 — what grades it** (must redden under reversion, per plan-lane's
test-verify mutation step):
- `@T-UC-003-storyboard-not-cancellable-on-recancel`, wired and asserting the
  wire envelope (`assert_wire_error`), across mcp/a2a/rest.
- A new/strengthened assertion in
  `test_spec_request_fields_accepted.py`/`test_raw_wrapper_spec_fields_accepted.py`
  that reads the **published MCP schema** minus the **honored** field set and
  asserts it is empty for body-semantic fields (replaces the `isinstance`/
  `is_success`-only assertions named in AR-01 TQ-01/TQ-02/TQ-04).
- `test_architecture_rest_body_completeness.py` passing with the exemption arm
  **removed**, not widened.
- `inspect.signature(update_media_buy).parameters` reversion-test: mutating
  step 3 back to accept-and-drop must make this test fail.

**Out of scope**: the broader ~14-handler A2A "hand-picked `parameters` dict"
pattern this diff doesn't touch (AR-05's note) — consolidating it is
transport-layer work outside this diff.

---

## Lane B — `AdCPTestClient` as the harness's one dispatch owner (AR-02)

**Priority: P1.**

**Core Invariant**: `AdCPTestClient` is the implementation `call_via`/
`call_mcp`/`call_a2a` delegate to, not a peer beside them — one dispatch
mechanism in the harness, per the intent review's invariant 5.

**Scope**:
- `tests/harness/_base.py` — add `MCP_TOOL`/`A2A_SKILL` class attributes
  alongside the existing `REST_ENDPOINT`/`REST_METHOD`; base `call_mcp`/
  `call_a2a` delegate to `_dispatch_core` when set.
- `tests/harness/client.py` — `_last_wire_response` (3 writers today,
  `:333,468,477`) becomes a typed `@dataclass DeliverResult` returned by
  DELIVER, read by UNWRAP — no more writing another object's private
  attribute (`env._run_mcp_client`/`_run_a2a_handler`/`_prepare_rest_request`/
  `_commit_factory_data` reuse becomes a declared contract, not an
  undeclared one).
- `McpE2EDispatcher.dispatch` / `A2AE2EDispatcher.dispatch` — collapse the
  divergent copies (`A2A_SKILL` fallback on one, `tool_name=` required on the
  other, defined by no env in the tree); `_unwrap_mcp_success`/
  `_unwrap_a2a_success` (byte-identical) collapse to one; the
  `if not env.e2e_config: raise` precondition (written 4x in 2 shapes)
  collapses to one.
- `_deliver_e2e_a2a` (`client.py:437-449`) — parse the body before
  `raise_for_status()`, matching the REST sibling's `>=400` handling
  (`:578-598`), so the A2A leg stops discarding the wire error envelope.
- `tests/bdd/steps/generic/when_request.py:67-77` `_call_via` — wire through
  `_populate_ctx_from_result` (already used by `dispatch_request` and
  `dispatch_via_client`) so error-path Thens reached through it stop silently
  degrading to lossy reconstruction.
- `tests/bdd/steps/generic/_dispatch.py:14` `_SENTINEL` → `NO_IDENTITY_OVERRIDE`
  (the constant this PR already extracted and guard-pinned elsewhere).
- `tests/harness/task_management.py:39-46` — the 34th env in the old
  quartet pattern, new in this diff. Delete `TaskManagementEnv.call_impl`/
  `call_mcp`; it has no legacy shape to preserve. Route its scenarios through
  the client instead.
- `ctx["client"]` — build once in the ctx fixture / `_run_env_route`, not per
  `ENV_ROUTES` row (currently one hand-wired seed callback).

**§5 — what grades it**:
- `test_harness_client_transport_parity.py` (already the genuine
  two-independent-paths proof — it caught the missing `A2A-Version` header;
  extend its coverage to the newly-delegating envs).
- A new guard: `grep -c 'def call_mcp\|def call_a2a' tests/harness/*.py`
  drops from 55 definitions toward 1 base + explicit-override count; assert
  the count in a structural guard so a 35th hand-rolled env fails CI.
- `salesagent-oyiv.10` (parked on this PR, still open) unparks when this
  lane lands — its stated precondition was "the direction is clearer"; base-
  class delegation is that direction. Reference it in the lane's commit.

**Depends on**: nothing (independent of Lane A).
**Blocks**: Lane C (AR-03) — C's fix is "route scenarios through the finished
client," which requires B's wire-capture completion first.

---

## Lane C — Storyboard scenarios grade the wire, not in-memory objects (AR-03)

**Priority: P1. Depends on Lane B.**

**Core Invariant**: every storyboard `Then` asserts a transport-observable
signal, on every transport, through the guarded accessors (`wire_dict`/
`wire_field`/`assert_wire_error` — deliberately loud, not silently degrading).
Setup goes through the env's per-transport primitive, never a direct `_impl`
call.

**Scope**:
- `tests/harness/creative_sync.py:192-205` `CreativeSyncEnv.call_a2a` — calls
  `sync_creatives_raw(**kwargs)` directly instead of `_run_a2a_handler`; wire
  `client.call("sync_creatives", …)` through the A2A leg Lane B finishes.
- `tests/bdd/steps/domain/uc006_storyboard_creative_sync.py:326-355`
  `then_response_envelope_schema_valid` — delete the `resp.model_dump()`
  fallback; assert via `wire_dict(ctx)`.
- `:510-535` format-id roundtrip — keep the `CreativeRepository` read only as
  a redundant in-process check; the primary assertion reads the creative back
  on the wire (`list_creatives` + `wire_field`). The `TRANSPORT-BYPASS` Given
  (`asyncio.run(_get_products_impl(...))`) is only acceptable for non-e2e_rest
  parametrizations; under `e2e_rest` it must go over real HTTP like the rest
  of that scenario.
- `tests/bdd/steps/domain/uc003_storyboard_generic_client.py:83-96`
  `then_response_not_500_or_non_adcp_shape` — populate a normalized transport
  status in `TransportResult.envelope` for the MCP/A2A families (currently
  only REST's UNWRAP sets `status_code`) so the `if status_code is not None`
  guard becomes unconditional instead of a silent no-op on two transports.
- Context-echo tests — assert against the captured `wire_response` with an
  exact dict comparison, not `response.context.model_dump(exclude_none=True)`
  (a re-serialization that normalizes exactly what 3.1.1 echo rule 5 forbids).
- `tests/integration/test_bdd_scenario_liveness_real_run.py:132` — until the
  A2A leg above is real, do not assert `{"mcp","a2a","rest"}`; the artifact
  must not publish a phantom transport.

**§5 — what grades it**:
- The eight UC-006 storyboard scenarios pass with `wire_dict`/`wire_field`
  assertions on all three transports, including a2a.
- `test_bdd_scenario_liveness_real_run.py` observation-set assertion is
  correct for what's actually measured (no phantom transport) — this test
  itself is part of the grader; if Lane C ships the a2a leg, the `{"mcp",
  "a2a","rest"}` assertion becomes true rather than needing weakening.
- Reversion test: revert the A2A `_run_a2a_handler` wiring → the storyboard
  A2A checks must fail loudly (`wire_dict`'s guard fires), not silently pass
  on a `model_dump()` fallback.

**Out of scope, with reason**: the production `_handle_sync_creatives_skill`
defect (`CreativeAsset` built from raw dicts) that `CreativeSyncEnv.call_a2a`
currently routes around predates this diff. This lane's job is to make that
gap *visible* — ledgered, with the defect named — not to fix the handler.
File a follow-up issue for the handler fix; do not fix it inside this lane.

---

## Lane D — One known-gap mechanism, not two (AR-04)

**Priority: P2. Independent.**

**Core Invariant**: a "known gap" is registered exactly one way in this repo
— a scenario/Examples-row tag in the ratcheted ledger — never as a per-assertion
escape hatch inside a step body.

**Scope**:
- `tests/bdd/steps/domain/uc006_storyboard_creative_sync.py` — 8
  `pytest.xfail("SPEC-PRODUCTION GAP: …")` calls, including the un-gated
  catch-all `_response_or_xfail()` (`:292-310`) that converts *any* dispatch
  failure (401 regression, 500, timeout, harness gap) into a green "known
  gap."
- `@T-UC-006-storyboard-multi-format-sync` — split its ungraded clause
  (`status` population) into its own tagged scenario/Examples row; the
  action/status enum assertions later in the same scenario are currently dead
  code on all three transports because `pytest.xfail()` aborts the scenario.
- `.claude/notes/storyboard-conformance/E2E-BRIEF.md:60-61`,
  `E2E-PASS-C.md:374` — correct "add an `e2e_rest_known_failures.txt` entry"
  to "add the realizer / re-express the Then"; rename "New ledger entries
  required" to "Ledger entries to REMOVE" (this diff's own checked-in guidance
  currently institutionalizes ratchet growth that `E2E-PASS-A.md:356-358`
  forbids elsewhere).
- Sibling precedent to match: `uc006_sync_creatives.py:466,474` xfails only
  when the observed code is in a curated `_SPEC_PRODUCTION_GAP_CODES` set —
  this is the correct shape; the new file should match it, not diverge from it.

**Steps**:
1. Delete `_response_or_xfail()`. Every Then becomes an unconditional assert
   against the pinned obligation (`assert_wire_error(...)` / the wire-success
   helper) — a dispatch error fails the test, full stop.
2. Split the multi-format-sync scenario; ledger the new tag (44+32-entry
   ledger convention already established this session for
   `tests/storyboard/known_failures.txt` — mirror it for the BDD ledger if a
   separate one applies here, or the existing `e2e_rest_known_failures.txt`
   triad if this scenario runs under that harness).
3. Fix the two guidance-doc lines.

**§5 — what grades it**: `grep -c pytest.xfail tests/bdd/steps/domain/uc006_storyboard_creative_sync.py` → 0 (down from 8); the split scenario's status-population clause is ledgered and its sibling action/status assertions are live (not dead code) on all three transports; a mutation test — inject a 500 into one previously-caught-by-`_response_or_xfail` path — must now fail the scenario instead of xfail-passing.

---

## Lane E — The measurement pipeline verifies itself (AR-06)

**Priority: P1. Loosely follows Lane D (shared ledger discipline) but not
blocked by it — sequence after D if convenient, not required.**

**Core Invariant**: every artifact this pipeline publishes is regenerable and
compared in `make quality`, not merely asserted by prose or by a unit test on
a frozen literal.

**Scope**:
1. **xdist-awareness.** `tests/bdd/scenario_liveness.py:146` `_RECORDS` is a
   per-process module global written from every process's
   `pytest_sessionfinish`; under `tox.ini:138`'s `-n auto` the controller
   writes last with an empty `_RECORDS`. Shard per-worker, merge at the
   controller. Add the `-n 2` case to
   `tests/integration/test_bdd_scenario_liveness_real_run.py::_run_bdd_slice`
   (currently shells out without `-n`, so it can't catch this) — measured:
   serial finds 3 scenarios, `-n 2` finds 0.
2. **Grading-provenance tag as filter, not column.** `scenario_liveness._TAG
   = "storyboard-v3.1"` removes a scenario from measurement the moment its tag
   changes (this diff retags two dormant scenarios `@storyboard-v3.1` →
   `@schema-v3.1`, and the real-run test then asserts the *reduced* set is
   correct). Widen `_TAG` to the union of provenance tags; record the tag as a
   field on the record, not as the collection filter.
3. **Ledger-fitness test.** `_collect_checks()` only enumerates
   `summary["failures"]`/`skip_causes`, so a graduating check produces no test
   item at all — combined with `xfail(strict=False)`, neither half of the
   ledger header's "graduation or regression both fail CI" claim holds. Port
   the e2e_rest precedent's missing piece
   (`test_every_ledger_entry_resolves_to_a_collected_item`) to storyboard.
4. **Regenerate-and-compare the remaining artifacts.** Put
   `docs/test-obligations/storyboard-binding-baseline.md` (currently claims 21
   `@storyboard-v3.1` scenarios against a tree of 20, and republishes pre-fix
   buckets this diff itself corrected) and the `storyboard-issue-map.yaml`
   `coverage: partial` notes citing an empty binding allowlist under the same
   artifact-truth-guard pattern already proven for the check index.
5. **Bookkeeping cleanup**, mechanical: `tests/unit/test_storyboard_ledger_state.py`
   docstring/headline count mismatches (52-vs-44, "none of the triad exists
   yet") — this session's `salesagent-syhj` a2a-seeding commit already
   corrected the ledger's own section counts; this lane corrects the lock
   test's prose to match. `test_architecture_required_ci_checks_frozen.py:35-36`
   — verify it no longer carries the `6d16d9b1e` stale-claim commit reference
   (also already corrected in `ci.yml` this session; confirm the test file
   agrees).
6. **Terminal gate.** After steps 1–5 land and one clean in-network CI run
   confirms the ledger (76 entries: 44 mcp + 32 a2a, seeded this session) is
   accurate under `-n auto`, add `storyboard-conformance` to `summary.needs`
   in `.github/workflows/ci.yml`. Do this LAST in this lane, not first — it
   is the enforcement step, and enforcing an unverified pipeline just moves
   the false-negative into the merge gate.

**§5 — what grades it**:
- The two-command reproduction from the review
  (`BDD_LIVENESS_ARTIFACT=... pytest ... -n 2` vs serial) must show matching
  scenario counts.
- `test_every_ledger_entry_resolves_to_a_collected_item`-equivalent for
  storyboard passes, and reverting it (comment out one ledger entry's
  underlying fix) must make it fail.
- `docs/test-obligations/storyboard-binding-baseline.md` regeneration is
  idempotent and the artifact-truth guard fails if the checked-in file
  diverges from a fresh run.
- `grep -n -A25 "^  summary:" .github/workflows/ci.yml | grep -c
  storyboard-conformance` → 1 (from 0), verified only after step 6.

---

## Lane F — One contract module between `tests/` and `scripts/audit/` (AR-07)

**Priority: P3. Independent, mechanical, low risk — good candidate to run
early or interleaved with the others.**

**Core Invariant**: a real layering constraint (a pytest plugin must not
import a CLI; `scripts/audit` — imported *by* tests — cannot depend on
`tests/helpers`) is resolved by extracting a shared, dependency-free contract
module both sides import — never by copying constants or re-implementing a
lookup on each side.

**Scope**:
- New module: `scripts/audit/storyboard_spec.py` (already stdlib-only) or a
  new `tests/helpers/liveness_contract.py` — owns: the ledger-line grammar
  (currently duplicated `tests/helpers/ledger.py:14` vs
  `scripts/audit/ledger.py:105-115`, which additionally *silently drops*
  unparsable lines the helper keeps — reconcile to one behavior, the loud
  one); `ARTIFACT_ENV_VAR` + default path (`scenario_liveness.py:243` vs
  `scenario_liveness_join.py:113`); `_UC_TAG_RE` (`conftest.py:3077` vs
  `scenario_liveness_join.py:47`); the storyboard tag
  (`scenario_liveness._TAG` vs `storyboard_spec.py:401`); and
  `resolve_env_route(tags) -> EnvRoute | None` (currently two independent
  lookups — `conftest.py:3379`'s bucket-keys-plus-hardcoded-`elif` and
  `scenario_liveness_join.py:118-129`'s tag-row-then-UC-bucket — which
  **already disagree**, producing the exact dormant-claim false positive the
  join was built to eliminate).
- `CheckRecord.to_dict()` / `Binding.to_dict()` — replace hand-mirrored field
  lists with `dataclasses.asdict(self)`.
- Add a frozen `StoryboardCheck` (id + status/reason/reason_kind) with
  `from_failure()`/`from_skip_cause()`/`no_graded_checks()` named
  constructors, replacing the three divergent `dict[str, Any]` builds in
  `tests/storyboard/test_storyboard_conformance.py`.
- `LedgerCheckId.track: str` constructed as `None` in one call site (renders
  literal `"None"`) — widen the field to `str | None`.
- `EnvRoute` callback types (`Callable[[object | None], …]` etc.) → the real
  `BaseTestEnv`/`E2EConfig` types; `load_env_routes() -> dict[str, EnvRoute]`,
  not `dict[str, Any]`.
- `build_review_report.py:394` hand-rolling an entry point
  `storyboard_spec.run_cli` declares to be the only sanctioned one — route
  through `run_cli`.
- Storyboard defaults duplicated between the module and `tox.ini` — pick one
  owner.

**§5 — what grades it**: a unit test asserting `tests/helpers/ledger.py` and
`scripts/audit/ledger.py` are the same object (import identity) or that only
one module defines the parse function; `resolve_env_route()` called from both
`_harness_env` and `registry_wired` returns identical results for every tag
combination in the tree (a property/parametrized test over the actual
`ENV_ROUTES` table) — this is the direct fix for the measured disagreement.

---

## Execution order (dependency-respecting)

```
Lane A (P0, blocking)  ─┐
Lane B (P1)             ├─ independent of each other
Lane D (P2)             ├─
Lane F (P3)             ┘
Lane C (P1) — depends on Lane B
Lane E (P1) — sequence after D for shared ledger discipline; not hard-blocked
```

Suggested `TASK_IDS` walk order for `plan-lane-execute`: **A, B, C, D, F, E**
(A first because it's the live regression; B before C because C is
structurally dependent; E last because its terminal step — gating CI — should
only happen once the ledger work in D has landed and the pipeline is proven).

## ALTERATIONS

(none yet — append here, do not edit the lane sections above in place)

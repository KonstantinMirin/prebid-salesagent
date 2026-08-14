# PR #1941 — frozen remediation plan

Scope authority for the `plan-lane-execute` formula. **This document is frozen**:
lanes transcribe it, no atom amends it. Later `## §6 ALTERATIONS` entries win over
anything earlier.

Provenance: a 30-finding deduplicated triage of the multi-agent review artifact
(`120826_1949`) plus @ChrisHuie's round-1 GitHub review, then nine per-cluster
architecture consults and a synthesis pass. Every file:line below was verified
against head `44b866f2a`. One review claim (stale `adcp==5.7.0` pin prose) was
REFUTED — fixed by `44b866f2a` — and is deliberately absent.

## §1 Verdict

Two blockers, both closable in this PR:

- **F1** — `revision`/`confirmed_at` are stated as by-construction contracts but
  implemented as compensating calls. `bump_revision()`
  (`src/core/database/repositories/media_buy.py:466`) has **zero production
  callers**; six writers set the columns on a bare ORM object.
- **F5** — the two new buyer-visible fields have **no wire oracle**. 32 already
  authored UC-019 params that grade them on the response are dormant; every
  assertion in the new integration file routes through `repo.get_by_id`.

Everything else in-PR finishes code this diff authored. The mapper-event/UoW
redesign, the backfill migration and the #1544 commitment-semantics
reconciliation stay in #1928.

## §2 Lane index

| Lane | Tier | Findings | Depends on | One-line scope |
|---|---|---|---|---|
| L1 | A | F1 core, F6 | — | Write seam, repository side + honest graders |
| L2 | B | F1 rest | L1 | Route the six bypass writers through the repository |
| L3 | B | F2, F3, F4 | L1 | Fail-closed vocabulary, narrowed resolver, producer agreement |
| L4 | A | F7, F8, F9, F10 | — | Delete the silent fallback; make the instruments loud |
| L5 | A | F5 | L4 | The wire oracle — graduate 32 authored params |
| L6 | C | F14, F15, F16, F17 | L4 | Step-vocabulary governance |
| L7 | C | F11, F12, F13 | — | Spec-copies: one declaration per divergence class |
| L8 | C | F21 | — | Envelope message ownership |
| L9 | C | F18, F19, F20 | — | Harness seams |
| L10 | C | F24, F25 | L9 | Thread-lifecycle oracle |
| L11 | C | F22, F23, F26–F29 | L3, L5, L9 | Mechanical tail; prose LAST |

**Tier A** closes both blockers and this PR's own defect class. **Tier B** is
production behavior change. **Tier C** is quality that does not block merge.

## §3 Lane specifications

### §3.1 L1 — write seam, repository side (Tier A)

**Scope.** Make `MediaBuyRepository` the only writer of `revision` and
`confirmed_at`, and make the new integration file grade what it claims.

**Edits — `src/core/database/repositories/media_buy.py`:**
- Stamp `confirmed_at` at create: in `create_from_request` before the flush
  (`:415`) and in `create()` — the sync path persists final statuses directly
  and never stamps today.
- Add `"confirmed_at"` to `_MEDIA_BUY_IMMUTABLE_FIELDS` (`:44`), so
  `update_fields(confirmed_at=...)` can no longer walk through the write-once
  guard.
- Fold the parent revision bump into the four package writers (`:539`, `:569`,
  `:586`, `:617`) — the four its own docstring already names.
- **Delete** the public `bump_revision()` (`:466`). Zero production callers.
- Drop the false `func.coalesce(revision, 0)` NULL-guard (`:449`); the column is
  `nullable=False, default=1, server_default='1'`.

**Edits — new guard `tests/unit/test_architecture_media_buy_write_seam.py`:**
AST-scan `src/` outside `repositories/` for attribute assignment to
`.confirmed_at` / `.revision`. Precedent:
`tests/unit/test_architecture_no_raw_media_package_select.py` (entity-scoped
guard). **Zero allowlist entries at merge.** Do NOT guard `.status` — too many
unrelated entities assign it.

**Edits — `tests/integration/test_media_buy_revision_confirmation.py`:**
- Repoint `test_package_level_write_can_bump_via_public_entry_point` at
  `repo.update_package_config` instead of calling `bump_revision` directly. It
  is RED at head and green with this lane — that red is the designed ordering
  signal, not a defect.
- Assert the stamp inside a `[t0, t1]` window with `created_at`/`approved_at`
  pinned in the past. Presence-only assertion currently survives mutating the
  stamp to write either of those.
- `update_fields(confirmed_at=...)` raises.
- Create path: `revision == 1` plus stamp-window.
- The two-session lost-update test must be mutation-verified: temporarily swap
  `_bump_revision` to a Python read-modify-write before landing. If it cannot
  discriminate, rewrite the module docstring's concurrency claim instead. Never
  ship it green-by-accident.

**Core Invariant.** A `MediaBuy` row's `revision` and `confirmed_at` cannot be
moved by any code outside `MediaBuyRepository`.

**What grades it.** The new write-seam guard (reverting any lane edit that moves
a write outside the repository reddens it); the repointed package test; the
stamp-window assertions.

### §3.2 L2 — route the six bypass writers (Tier B)

**Scope.** Every direct ORM write of media-buy status/approval goes through
`MediaBuyRepository`, so L1's guard can hold with an empty allowlist.

**Edits:**
- `src/admin/blueprints/workflows.py:225` and `:241-243` →
  `media_buy_repo.update_status(...)`. The repository is already in scope at
  `:192`; `update_status` already accepts `approved_at`/`approved_by`
  (`:486-487`).
- `src/admin/blueprints/operations.py:441-455` and `:574` — mirrors the pattern
  the same function already uses on its failure arm at `:468-472`.
- `src/admin/blueprints/creatives.py:649-657` → `uow2.media_buys.update_status(...)`.
  **Sixth bypass site, under-counted by both review sources** — it fetches
  through the repository then writes `mb.status`/`approved_at`/`approved_by`
  directly on the returned object. Verified present at head.
- `src/services/media_buy_status_scheduler.py:95-98` → repository. Extend its
  transition test to assert `revision` incremented.

**This is a behavior change, not a refactor.** Rows that previously never bumped
now bump. Any test pinning exact revision values reddens and gets updated to the
new correct expectation — never the reverse.

**Core Invariant.** Same as L1, now true of the whole tree rather than one class.

**What grades it.** L1's write-seam guard, with zero allowlist entries; the
scheduler transition test's new revision assertion.

**Out of scope.** Converting these handlers off bare sessions wholesale — that is
the admin-UoW mandate epic `salesagent-ctmz`. This lane routes only the MediaBuy
status writes.

### §3.3 L3 — vocabulary, resolver, producer agreement (Tier B)

**Scope.** Make the commitment vocabulary fail closed, narrow the read-time
fabricator to the single case that needs it, and stop three producers reporting
three different answers for one buy.

**Edits — `src/core/database/models.py`:**
- Declare `MEDIA_BUY_CONFIRMED_STATUSES` beside the existing unconfirmed set
  (`:909-911`), using #1544 semantics verbatim.
- Flip `is_media_buy_seller_confirmed` (`:940-948`) to fail-closed membership.
  Today `is_media_buy_seller_confirmed("some_new_status")` returns **True**, so
  any status a future writer adds silently manufactures a seller-commitment
  instant that reaches the buyer's wire.
- The partition stays in `models.py`: commitment is over *persisted* statuses
  (`draft` and `pending_creatives` both canonicalize to `pending_creatives` yet
  differ), and the DB layer must not import `src/core/tools`.
- Unit test at the test layer (so no production `database -> tools` import): the
  two sets are disjoint; their union equals `set(PERSISTED_STATUS_TO_CANONICAL)`
  exactly (`src/core/tools/_media_buy_status.py:94`);
  `is_media_buy_seller_confirmed("some_new_status") is False`.

**Edits — `src/core/tools/media_buy_list.py:430`:** narrow the fabrication to the
single schema-forbidden combination. Emit the column; substitute
`approved_at or created_at` **only** when the column is NULL **and** the computed
wire status is `active`. Fold `resolve_media_buy_confirmed_at`
(`models.py:914-937`, one caller, zero test references) into the wire producer —
the pinned conditional constrains the *wire* status, which only this module
knows. Rewrite its docstring as the legacy-row concession it now truthfully is,
and align the prose of migration `2c4e6a7b8d9e` (this PR's own, unmerged).

**Edits — `src/core/tools/media_buy_update.py`:** pass a real `revision=` at the
two non-dry-run success sites (`:738`, `:1392`) from the post-mutation row via
the in-scope UoW, and the current row's value at the dry-run site (`:560`).

**Edits — `src/core/schemas/_base.py`:** delete the now-false comment at
`:624-625` ("real per-buy revision tracking is separate media-buy lifecycle
work"). After L1 the create arm's defaults at `:378-386` are exact by
construction — correct the comment, no code change.

**Core Invariant.** One buy reports one `revision` and one `confirmed_at`,
whichever producer the buyer asks.

**What grades it.** Integration case: create + update twice → the two update
responses report 2 and 3 and `get_media_buys` reports 3. The pin names these as
interchangeable sources (`dist/schemas/3.1.1/media-buy/update-media-buy-request.json`:
`revision` — "Obtain from get_media_buys or the most recent create/update
response"). Plus the vocabulary unit test above.

### §3.4 L4 — delete the silent fallback; make the instruments loud (Tier A)

**Scope.** This PR's own thesis, applied to the four sites this diff authored
where "the instrument cannot observe what it was asked to grade" degrades to
green.

**Edits — `tests/bdd/steps/generic/then_schema.py`:**
- **Delete `serialized_response()`** (`:26-36`). Both steps call `wire_dict(ctx)`
  from `_outcome_helpers` (`:43-59`), whose loud guard is the precedent this PR
  itself followed at `tests/harness/media_buy_list.py:60-71` when the guard fired.
- Rewrite the docstring; the stale "IMPL falls back" sentence (`:12-13`) dies
  here — the IMPL transport it cites was dropped at
  `tests/bdd/conftest.py:2879-2883`, so every remaining fallback is a real-wire
  transport that stashed nothing.
- **No `exclude_none` flag on `wire_dict`.** Stripping literal nulls would mask
  exactly the regression class the wire reader exists to catch.
- Why this matters most: the module is registered globally at
  `tests/bdd/conftest.py:58`, and the fallback fires on
  `then_envelope_status_completed` — the step grading the exact obligation #1900
  owns, where `status` is a model field with a default and so passes whether or
  not the envelope reached the wire.
- Gate: `tox -e bdd`, expected delta zero. A guard-raise means a two-line env
  migration, per the `media_buy_list` precedent.

**Edits — `tests/unit/test_pydantic_schema_alignment.py`:**
- **F8** — replace the identity check at `:1285` with
  `b.__module__.startswith("adcp.types")`, which is the rule the gate's own
  docstring already documents. Measured: admits exactly `SyncAccountsResponse`
  and `CreateMediaBuySuccess`, both already registered, so the gate stays green
  and both rows become deletion-protected. Add a regression test pinning both in
  the enumeration. This is a bugfix of the current rule against its own
  docstring — **not** #1927's redesign, and it creates nothing for #1927 to unwind.
- **F9** — thread `strict` through `generate_example_value`; raise a typed
  `_CannotSynthesize` at **all five** no-rule exits: the two `except Exception`
  swallows at `:199` and `:295-298` (which contradict `load_json_schema`'s own
  HARD-FAILURE contract at `:115-118`), the bare-object exit `:336`, and the
  terminal `None` `:338`. `_synthesize_sample` passes `strict=True`; the lenient
  default preserves pre-existing request-side callers byte-for-byte. One
  `TestSampleSynthesisFailsLoud` case per newly covered shape. Any registry row
  that reddens was never graded — fix it with a generator rule or a
  `sample_override`, **never** an exclusion.
- **F10** — delete `GetMediaBuysResponse` from the exclusion prose at `:770`,
  25 lines above the row at `:792-796` that registers it.

**Core Invariant.** No instrument in this repo may report success because it
could not observe what it was asked to grade.

**What grades it.** The `TestSampleSynthesisFailsLoud` cases; the coverage-gate
regression test; for `then_schema`, deleting the fallback IS the grade — the
guarded reader raises where the fallback returned.

### §3.5 L5 — the wire oracle (Tier A, blocker)

**Scope.** Grade the two new fields at the layer that publishes them. Sequenced
**after L4** so the graders read the real wire.

**Edits — `tests/bdd/features/BR-UC-019-query-media-buys.feature`:**
- Append the verified one-liner at `:50`: `And the response should be
  schema-valid against media-buy/get-media-buys-response.json`. @ChrisHuie
  mutation-verified this in both directions.
- **Retire** the two premise-impossible defective-seller partitions, using the
  verbatim retired-block precedent at `:159-170` with the upstream-reconciliation
  note: revision-absent (column is `nullable=False, default=1,
  server_default='1'`, `models.py:975`) and confirmed_at-not-iso8601 (column is
  `DateTime(timezone=True)`, `models.py:982`).
- **Rewrite** `confirmed_at_missing_on_buy` into the resolver's explicit oracle:
  seed active + NULL, assert schema-valid wire with non-null `confirmed_at`.
  Stays correct after #1928 narrows the fallback.

**Edits — `tests/bdd/steps/domain/uc019_query_media_buys.py`:**
- One shared factory-backed seeder extending `_seed_simple_media_buy` (the
  module's own precedent at `:193-229`) — factories through the env session,
  **not** a new env API. This deliberately overrides the triage's framing:
  `MediaBuyListEnv` has no seeding methods and none of UC-019's ~30 Givens use one.
- The missing Given variants: persisted revision N (and defective 0 / -1 — both
  seedable, no CHECK constraint); "revision 5 after four writes" via four real
  `update_fields` calls; `confirmed_at` timestamps; the owns-3-buys alias.
- t1/t2 Whens snapshotting `wire_dict` per read.
- A real repository write for "update lands between reads" — the graded
  obligation is the *read* path; UC-002 owns the update tool's transport
  contract. Say so in the docstring.
- All Thens through `wire_dict`/`wire_field`: revision equality, integer + >= 1
  sweep, t1/t2 comparisons, `confirmed_at` KEY presence (the wire oracle for the
  required-nullable re-insert), datetime-parsed equality (never string-compare
  `Z` against `+00:00`), and the schema-invalid step via
  `validator_for(...).iter_errors` path-anchored to the buy's index.

**Run the module serially** — xdist deadlocks on the single agent-db.

**Core Invariant.** Every field this PR publishes on the buyer's wire has a
grader that reads the buyer's wire.

**What grades it.** The 32 params themselves, shown green after being shown
dormant. **If graduation surfaces real production failures, that is this lane
working: fix them or report them as a blocker — never re-route to xfail.**

### §3.6 L6 — step-vocabulary governance (Tier C)

**Scope.** A promotion into the global generic namespace must retire the
phrasing it replaces rather than coexist with it.

**Edits:**
- `then_schema.py`: parameterize the envelope step —
  `parsers.parse("the response envelope carries status {status}")`. Both existing
  feature lines already match with `completed`; zero feature edits.
- `then_success.py:40-52`: add a docstring declaring the migration direction. The
  incumbent reads the typed model and is structurally blind to the #1900 defect
  class; its wire successor is the envelope step; call sites migrate when
  touched, per `tests/CLAUDE.md` §"Migration path". **This deliberately overrides
  the triage's implied in-PR re-point**: that is an 88-site change gated on envs
  that do not stash success wire.
- `uc005_format_id_roundtrip.py:101-111`: delete the weak exact-text body
  (`isinstance(formats, list)`) so the generic full-document parser becomes the
  sentence's single meaning. If UC-005 then fails full validation, that is a real
  serialization gap to fix or surface — never a reason to restore the weak body.
- Strengthen `test_architecture_bdd_no_shadowed_steps.py` from fixture-name
  identity to **match-overlap**: run feature lines through every registered
  module's `parser.is_matching`, fail on 2+ modules matching one line. RED at head
  on the UC-005 collision, green after the deletion. `_ALLOWED_SHADOWS` stays
  empty; if more latent collisions surface, pick winners and land the guard anyway.
- Rewrite the inverted UC-018 rationale (`test_uc018_list_creatives.py:44-51`).
- Move the three orphaned BR-UC-011 traceability comments back onto
  `@T-UC-011-sync-create`. **Verify placement against merge base `61611c317`
  first** — this finding is PLAUSIBLE, not confirmed.

**Core Invariant.** One Gherkin sentence has exactly one meaning.

**What grades it.** The strengthened shadow guard.

### §3.7 L7 — spec-copies (Tier C)

**Scope.** One declaration per divergence class, with a mechanism that makes the
workaround delete rather than fossilize.

**Edits — `src/core/schemas/_base.py`:**
- Add `CompletedTaskStatusMixin` (`status: Literal["completed"] = "completed"`)
  beside `NestedModelSerializerMixin` (`:270`). Compose it first-in-bases into
  `CreateMediaBuySuccess`, `UpdateMediaBuySuccess`, `SyncAccountsResponse`
  (`account.py:141`/`:170`) and `SyncCreativesResponse`
  (`creative.py:480`/`:503`), collapsing four separately-written rationale blocks
  to one pointer each.
- **`GetMediaBuysResponse` stays outside.** It inherits the field correctly from
  the pin; pulling it in would create a redeclaration where none exists.
- The two types are **legitimately different** and must not be reconciled:
  `Literal` is a sync-only arm discriminator; `TaskStatus` is the pinned envelope
  enum.
- Divergence-pin test in `test_adcp_contract.py` (precedent `:246`): SDK parents
  that omit `status` stay omitting, with failure message "adcp now ships it —
  delete the mixin from this class"; create/update parents stay
  `Literal["completed"]` required.
- Add `AlwaysIncludeFieldsMixin` with class-declared `_ALWAYS_INCLUDE_NULL_FIELDS`,
  adopted by `GetMediaBuysMediaBuy` (deleting the hand-written re-insert at
  `:2833-2834`) and `Account` (`:50-57`). `delivery.py:337` is deliberately NOT
  converted — its rule is conditional, and converting it would change the wire.
- Focused pin test: required ∩ nullable on the get-media-buys item ==
  `{confirmed_at}` and is a subset of the declared set, with a pin-bump failure
  message. The pin stays in the test layer; production never reads schema files
  at runtime.
- `ApprovalStatus = LibraryCreativeApprovalStatus` alias (mirroring `:2739`,
  members verified 3/3), closing the producer/consumer split at
  `media_buy_list.py:619-625` by construction.

**Core Invariant.** One spec concern has one declaration, and the workaround
announces its own obsolescence.

**What grades it.** The divergence-pin test; the focused always-include pin test.

### §3.8 L8 — envelope message ownership (Tier C)

**Scope.** Restore a buyer-readable envelope message on `GetMediaBuysResponse`.

**Edits.** Curated `__str__` ("Found N media buy(s).", precedent
`account.py:184`) plus exact-string cases in
`tests/integration/test_a2a_response_compliance.py` (precedent `:68`/`:87`).

**Corrected framing** (the review's is wrong): the class never had a curated
`__str__`. Pre-PR `str()` was already a repr; this PR amplified it to a
316-character pydantic repr containing `message=None`. So this PR is the natural
first lander, and the class-level guarantee stays with **#1906**. Note the
overlap in the PR description so a rebaser treats the same-method conflict as
textual.

**`model_summary()` adoption is rejected on the merits, not deferred.** The SDK's
`_RESPONSE_MESSAGE_REGISTRY` has no `GetMediaBuysResponse` key but name-collides
with `GetProductsResponse` and others, so a boundary sweep would silently replace
every curated pinned wire string with text from an SDK this repo treats as
non-authoritative.

**Core Invariant.** No buyer-visible protocol field is a Python repr.

**What grades it.** The exact-string A2A compliance cases.

### §3.9 L9 — harness seams (Tier C)

**Scope.** Make the un-routed transport arm refuse instead of lying, and stop two
copies of the same test-support code.

**Edits:**
- `tests/harness/media_buy_create_list.py`: `build_rest_body` raises
  `NotImplementedError` for list requests — `get_media_buys` has no REST route
  (`src/routes/api_v1.py` has only create/update/delivery), and one seam covers
  both in-process and E2E dispatch. Phrase it in the `_outcome_helpers` refusal
  dialect; pin with a one-case test (precedent `test_harness_wire_response.py`).
  **Declare per env, never derive from the route table** — a deleted route must
  not silently shrink the test matrix.
- **F19, overriding the triage's direction**: `_create_request.py` stays
  canonical and `given_media_buy.py` delegates. Importing the other way would
  execute `@given` registrations cross-module — the UC-004 shadowing incident
  class. Make `po_number` optional so the delegation is byte-identical. The
  `idempotency_key` "third copy" is two genuinely different operations (a harness
  per-call default vs a per-scenario-stable replay key) — document the split; the
  builder stays key-free. Gate: full bdd run of uc002 + uc019, where the
  replay-hash scenarios are the canary.
- **F20**: publicize `bind_factories_to_session`
  (`tests/utils/database_helpers.py`, save/restore — the right discipline for
  anything not guaranteed outermost; the harness assert-unbound stays untouched
  and complementary). Add a shared `bound_factory_session` fixture in
  `tests/integration/conftest.py` and rewrite both new files' hand-rolled
  bind-then-None fixtures. Add the missing None-guard in `_revision` (`:44-46`).

**Core Invariant.** A transport the harness cannot dispatch refuses loudly rather
than dispatching something else.

**What grades it.** The one-case refusal test; the uc002+uc019 bdd run.

### §3.10 L10 — thread-lifecycle oracle (Tier C)

**Scope.** Make the leak test able to observe the leak it exists to prevent, and
restore the two assertions the same commit dropped. Sequenced after L9 (same
file, disjoint lines).

**Edits — `tests/integration/test_order_approval_background.py`:**
- `_join_worker(approval_id)` scanning `threading.enumerate()` for the name set
  at `order_approval_service.py:108`, then join + `assert not is_alive()`.
  Canonical oracle precedent: `tests/unit/_thread_registry_helpers.py:33-37`.
  This replaces the polling loop and makes both docstrings' "the test joins"
  claim true.
- Keep `assert not is_approval_running(...)` after the join — now a deterministic
  registry-hygiene check.
- New gated INSERT-time test: patch `_run_approval_thread` with an Event-blocked
  `side_effect` (precedent `test_order_approval_service.py:111-115`), pass a
  **real** `webhook_url` (safe only because the worker body never runs), assert
  `status == "running"` and that the URL round-trips through the persisted row;
  `finally: gate.set(); _join_worker(..., require_found=True)`, which pins the
  thread-name contract.

**Triage sub-claim overridden.** F25's "the failure path fires no outbound
request" is **false**: `_mark_approval_failed` POSTs with 3 retries to any truthy
URL (`order_approval_service.py:319-330`). The terminal test keeps
`webhook_url=None`.

**Core Invariant.** A test that exists to catch a leaked thread fails when the
thread leaks.

**What grades it.** The join assertion under a deliberately leaked worker.

### §3.11 L11 — mechanical tail; prose LAST (Tier C)

**Scope.** Small independent corrections. Prose is written against the shipped
state, so this lane runs after L3, L5 and L9.

**Edits:**
- `run_all_tests.sh:151`: split the `&&`-list so `errexit` applies. Record the
  A/B repro in the commit message.
- Extract `_resolved_allof_arms` and reduce both harvests (`:856-874`,
  `:898-917`) to comprehensions — the alignment walk's two halves are currently
  resolved by two independent loops, a DRY-invariant hit in the very file this PR
  is about.
- Swap the schema-inheritance guard to `assert_violations_match_allowlist`
  (helper at `_architecture_helpers.py:826`, ten sibling precedents) and remove
  the stale entries it surfaces. **Attempt this early in the lane**: if it flags
  demonstrably-live entries, the collector has a blind spot and that is the real
  finding. Fix the wrong comment at `:248-252` (word it consistently with L7's
  alias) and de-count `docs/development/structural-guards.md:118`.
- Re-query `gh`, then file **two** issues — retire `_run_mcp_wrapper` (including
  the guard requiring it at `test_harness_base.py:318-323`) and consolidate the
  `pricing_option_id` formatters — plus a comment on #1906. No
  `model_summary`-sweep issue (rejected in L8). Flag #1353's missing assignee.
- Replace the four beads-id comment lines with GitHub numbers (project rule: code
  comments cite GH #, never beads ids).
- Prose corrections against the shipped state: `media_buy_list.py:292-295` (name
  the resolver as producer), `models.py:897-903` (delete the false "cannot drift"
  sentence; qualify "MUST be absent" against present-as-null),
  `media_buy_create_list.py:42-45` (cite the dispatchers that actually run),
  uc019 storyboard wording (`:2517-2525` — "the three validations these Thens
  grade", not exhaustive).

**Core Invariant.** Every citation this diff added names the thing that actually
runs.

**What grades it.** The stale-entry companion on the inheritance guard; the
`errexit` A/B repro.

## §4 Deferred — do not do these in this PR

| Work | Destination | Why not now |
|---|---|---|
| Backfill migration for legacy `confirmed_at`; delete the narrowed read-time fallback | #1928 | Data-rewrite migration is new blast radius; the narrowed fallback keeps the wire schema-valid meanwhile |
| #1544 commitment-semantics reconciliation (is commitment an event? does manual approval bump? `finalizing`?) | #1928 | Its acceptance says "reconciled with #1544, not decided independently" |
| Whole-handler admin migration off bare sessions | salesagent-ctmz | L2 routes only the MediaBuy status writes |
| Auto-xfail mechanism hardening | #1929 | It owns the mechanism; L5 is the instance — neither launders the other |
| Registry admission redesign (transport-registration rule) | #1927 | Blocked on #1908; L4's one-liner fixes the current rule against its own docstring and creates no unwinding |
| Class-level "no response degrades to repr" guarantee | #1906 | Its acceptance criterion is verbatim this property |
| `update_media_buy` rejects stale revision tokens with CONFLICT | NEW ticket | New protocol behavior needing its own spec-grounding citation + BDD |
| Mirror the retired/rewritten UC-019 partitions upstream | NEW ticket (adcp repo) | In-feature rationale keeps the local tree consistent until it lands |
| Migrate the 88-site incumbent status step + UC-018's three `model_dump` Thens to wire readers, plus the wire-reader structural guard | NEW ticket | Gated on every UC-001..006 env stashing success wire. **A reviewer will challenge this** — counter: coexistence-with-declared-direction is `tests/CLAUDE.md`'s own sanctioned migration state, and the wire step ships graded now |
| Declarative harness transport routing + route-parity guard | NEW ticket | Must re-plumb `MediaBuyDualEnv`'s stateful REST routing; L9's raise already fails loud |
| Migrate 8 pre-existing factory binds + guard on raw `_meta.sqlalchemy_session =` | NEW ticket | Pre-existing debt; this PR's two copies are removed, so zero new instances |
| Strict request-side synthesis + recursive pin-derived always-include sets | NEW ticket | Flipping the lenient request path may redden never-graded rows — its own triage loop |
| Beads-id ban guard + storyboard-citation convention | NEW ticket | New guard machinery; L11's four line fixes stand without it |
| SDK enum-alias guard + `protocol_envelope.py:46-55`'s 8-member TaskStatus copy | NEW ticket | Changing `ProtocolEnvelope.status` touches every wrapper's validation surface |
| ThreadRegistry self-remove vs reaper-only semantics | NEW ticket | Production change across 5 registry sites for zero in-PR benefit |
| Repo-wide `str(response)` -> `model_summary()` sweep | **Rejected on merits** (see L8) | Verified name-collision would silently replace curated pinned wire strings |

## §5 Grading index

| Lane | What grades it |
|---|---|
| L1 | Write-seam AST guard (zero allowlist); repointed package test; stamp-window assertions |
| L2 | The same write-seam guard, now over admin + services; scheduler revision assertion |
| L3 | create+update+update producer-agreement integration case; vocabulary disjoint/union/fail-closed unit test |
| L4 | `TestSampleSynthesisFailsLoud` per shape; coverage-gate enumeration regression test; the guarded reader raising where the fallback returned |
| L5 | The 32 UC-019 params, shown dormant then green; the `:50` schema-valid line (mutation-verified both directions) |
| L6 | Match-overlap shadow guard (RED at head, green after the UC-005 deletion) |
| L7 | Divergence-pin test in `test_adcp_contract.py`; focused always-include pin test |
| L8 | Exact-string cases in `test_a2a_response_compliance.py` |
| L9 | One-case REST refusal test; uc002 + uc019 bdd run |
| L10 | Join assertion under a deliberately leaked worker |
| L11 | Stale-entry companion on the inheritance guard; `errexit` A/B repro |

## §6 ALTERATIONS

_Later entries here win over anything above._

### A1 — Owner ruling (2026-08-13): fix legacy data with a MIGRATION, not with code paths

**Raised by:** L2's solution-review gate escalated a blocker — routing the scheduler and
creative-approval writes through `update_status` makes `_stamp_confirmation_if_needed` stamp
`confirmed_at` on rows that were ALREADY in a confirmed status before this PR, recording the sweep
instant (for `active -> completed`, the END of the flight) as the seller-commitment moment. It is
write-once, so permanent, and it overwrites the truer answer the read-time fallback gives.

**Ruling.** The proposed remedy — gate the stamp on the previous status — was rejected on principle:

> Code should not contain any paths for legacy or back compatibility. It is very fragile this way.
> We trust what comes from the database or from the input; for the database we take care of it
> through migrations, for the input through verification at the boundary. This whole category of
> problem should not exist.

**Consequences, which override the sections above:**

1. **§4 is amended.** "Backfill migration for legacy `confirmed_at`; delete the narrowed read-time
   fallback → #1928" is PULLED IN-SCOPE. The backfill is the fix, not a deferral.
2. **A backfill migration is added to L2** — the lane whose routing exposes the problem is the lane
   that makes the data trustworthy. It sets `confirmed_at` for every existing row whose status is
   seller-confirmed and whose `confirmed_at` is NULL, using the same rule the read-time fallback
   encoded (`approved_at`, else `created_at`).
3. **No stamp gate is added.** After the backfill there is no confirmed row with a NULL
   `confirmed_at`, so the case that produced the blocker is unreachable by construction rather than
   handled by a branch. `_stamp_confirmation_if_needed` (L1, committed) stays exactly as it is.
4. **§3.3's first bullet changes.** L3 no longer "narrows the fabrication to the single
   schema-forbidden combination" — it DELETES `resolve_media_buy_confirmed_at` (`models.py:914`) and
   its one call site (`media_buy_list.py:430`), which then emit the column directly. The narrowing
   was a smaller version of the same legacy code path.
5. **§3.5's A3 is unaffected in intent but changes in mechanism.** The rewritten
   `confirmed_at_missing_on_buy` scenario must grade that an active buy carries a non-null
   `confirmed_at` from the COLUMN, not from a resolver. If L5 landed before this alteration, its
   scenario is re-verified against the post-deletion behaviour rather than rewritten again.

**Invariant this establishes:** a nullable column that production cannot legitimately read as NULL
is a data defect to be migrated, never a NULL to be interpreted at read time.

### A2 — Owner ruling (2026-08-13): the persisted status vocabulary becomes a type

**Raised by:** L2's routing writes statuses as raw strings (`"pending_creatives"`, `"scheduled"`,
`"draft"`, `"rejected"`), which prompted the question of why the SDK's enum is not used.

**Measured.** `adcp.types.MediaBuyStatus` is a real `StrEnum` with exactly the pinned seven wire
members, and it IS used — 89 sites. But the *persisted* vocabulary is a different, larger set and has
no type at all: `approved`, `draft`, `failed`, `pending`, `pending_activation`, `pending_approval`,
`ready`, `scheduled` have no SDK member. Across `src/` there are **584 raw status literals in 75
files** against those 89 typed usages.

**Ruling.** The vocabulary gets a type:

> How I would design it is `MediaBuyStatus.<literal>`. If I want more statuses that are persisted, I
> just expand the list of enums that I have, and only then I add a getter and setter on my model that
> convert.

**Consequences, which override §3.3:**

1. **§3.3's F2 is REPLACED.** L3 no longer declares a `MEDIA_BUY_CONFIRMED_STATUSES` frozenset, and
   no longer writes the disjoint/union/fail-closed drift test. It introduces
   `PersistedMediaBuyStatus(StrEnum)` in `models.py` as the superset of the wire enum, defines the
   commitment partition over its members, and puts the persisted→wire conversion on the model.
2. **The fail-closed bug disappears rather than being fixed.**
   `is_media_buy_seller_confirmed("some_new_status") is True` is not a logic error — it is the
   absence of a type. With the enum there is no unknown member to ask about.
3. **What this deletes:** the two frozensets, `PERSISTED_STATUS_TO_CANONICAL`,
   `is_media_buy_seller_confirmed(str)`, and the drift test that existed only to keep a
   hand-maintained set honest.
4. **Drop-in, not a coexistence shim.** `StrEnum` members compare equal to their string values, so
   every existing `== "draft"` comparison keeps working unchanged. No branch, no flag, no compat
   path — the values are identical.
5. **The 584 literals are NOT migrated in this lane.** Introducing the type and moving the partition
   onto it is L3's scope; replacing the literals is mechanical follow-up that touches files no lane
   owns.

**Invariant this establishes:** a closed vocabulary is a type, not a set of strings guarded by a test.

### A3 — Owner ruling (2026-08-13): the vocabulary is enforced at the write boundary

**Raised by:** L3's test-layer gate proved a claim in this lane FALSE. The retired UC-019 row
`confirmed_at_null_column_on_active_buy` was retired as premise-impossible; the premise is reachable,
and *this lane made it so*. F2 (fail-closed commitment predicate) and F3 (delete the read-time
resolver) are each correct, and together they open a path neither opened alone:

```
PERSISTED status='some_new_status' confirmed_at=None
WIRE      status=active            confirmed_at=None   <- pinned schema FORBIDS this
```

`update_status` accepts any string; `resolve_canonical_status` treats an unmapped status as a generic
serving state and date-refines it to `active`; the now-correct fail-closed predicate leaves
`confirmed_at` NULL. Before this lane the fail-OPEN predicate read the unknown status as committed and
the resolver substituted `approved_at`/`created_at`, hiding it.

**Ruling.** Fix it where the bad value enters, not where it is read:

1. **`MediaBuyRepository.update_status` validates its `status` argument** against
   `PersistedMediaBuyStatus` and raises on an unknown value. This is "verification at the boundary"
   (§6-A1's sibling principle) applied to writes.
2. **`resolve_canonical_status` stops guessing.** With writes validated, an unmapped persisted status
   is unrepresentable, so the read map is indexed directly rather than defaulting to a serving state.
   A `KeyError` there is a real defect, not a case to absorb.
3. **L3's `test_an_unrecognised_status_never_stamps` is rewritten, not deleted.** It currently asserts
   the write SUCCEEDS with an unknown status — that contract is now wrong. The obligation it carried
   (an unknown value must never mint a seller-commitment instant) survives as: the write is REFUSED,
   so no stamp can occur. The stamp predicate keeps its defensive read for values already in a row.

**Invariant this establishes:** a closed vocabulary is enforced where values enter the system; a
reader that has to guess is a boundary that was never enforced.

### A4 — Owner ruling (2026-08-14): §3.10's kept assertion is deleted, not kept

**Raised by:** L10's solution-review gate. §3.10 directs *"KEEP `assert not
is_approval_running(...)` after the join — now a deterministic registry-hygiene check rather than a
race."* That justification is false, and the plan could not have known why.

`is_approval_running` → `ThreadRegistry.contains` (`thread_registry.py:65-70`) calls `_reap_locked`
(`:102-108`) **first**, dropping every entry whose thread is not alive, and only then tests
membership. After a successful join the thread is provably dead, so any surviving entry is reaped by
that very call and the assertion returns False on every path — including the path where no thread was
ever found. It cannot fail.

**Ruling.** Delete the line. An assertion that cannot fail is precisely the defect class this lane
exists to remove, so the plan bullet and the lane's Core Invariant cannot both be honoured. Registry
membership stays graded where it *can* fail: `test_approval_thread_tracks_in_registry` asserts it
TRUE while the worker is blocked on an Event. The deletion removes no coverage.

**Invariant this establishes:** an assertion that cannot fail is not hygiene, it is decoration —
grade a property where it can be violated, or do not claim to grade it.
### A5 — Owner ruling (2026-08-14): §3.6's shadow-guard rule is narrowed to the named disease

**Raised by:** L6's solution-review gate, on measurement rather than argument.

§3.6 directs the strengthened guard to *"fail when 2+ modules match one line"* with
`_ALLOWED_SHADOWS` staying **EMPTY**. Measured at HEAD `af2167542` across all 14,125 feature step
lines × 1,168 registered plugin parsers (type-filtered, outline placeholders skipped): that rule
fires on **11 cross-module collision classes**, of which exactly one is the UC-005 target.

Three of the eleven are *legitimate* deliberate narrowing of a generic sentence by a domain module
(`then_error` vs `uc003_ext_error_scenarios`, 28 sites / 24 distinct texts; `then_error` vs
`uc003_ext`; `then_error` vs `uc002`). In all three the narrower parser wins **only because its
module is registered later in the conftest `pytest_plugins` list** — pytest-bdd sorts
`_arg2fixturedefs[bdd_name]` by baseid and pytest takes the last, so equal baseids preserve
registration order. Reorder that list and grading changes silently.

So the plan's two clauses are jointly unsatisfiable: "pick winners and land the guard anyway" means
**10 behavioural decisions in UC-002/003/004/006 grading**, none of which is this lane, and the
alternative is seeding a 10-entry allowlist the plan itself forbids.

**Ruling.** Narrow the RULE to exactly the disease §3.6 names: *a step module outside
`tests.bdd.steps.generic.*` must not register an EXACT-TEXT (string-parser) step whose text a
`tests.bdd.steps.generic.*` parser already matches.* Measured: fires on exactly **1** class at HEAD
(UC-005), and is **empty** after the F16 deletion — so RED-at-head / green-after holds with a
genuinely empty allowlist and zero out-of-lane winner-picking.

The broader bars — no generic-vs-domain overlap at all (5 classes), no cross-module overlap at all
(11), and intra-module ambiguity (34 further distinct texts across 7 modules, invisible to any
"2+ MODULES" rule) — are declared in the guard **docstring** and filed as a follow-up ticket. They
are not allowlist entries.

**Implementation constraints carried from the same gate (Q1), both load-bearing:**
- The guard MUST filter on step **type** (given/when/then) before comparing, because production
  filters on type first (`pytest_bdd/scenario.py:59-66`); without it the guard reports cross-type
  phantom overlaps.
- The guard MUST assert a **non-zero parser count and non-zero matched-line count**. The parser is
  reached via `vars(mod)[attr]._pytest_bdd_step_context.parser.is_matching(text)`, unwrapping
  defensively through `._fixture_function`; a pytest minor bump that changes the fixture shape would
  otherwise make the guard scan zero parsers and pass **vacuously**.

**Invariant this establishes:** a guard's rule is scoped to the disease it was written for; breadth
that forces unrelated behavioural decisions is a follow-up ticket, never a day-one allowlist.

### A6 — Owner ruling (2026-08-14): §3.6's grader grades the GUARD; the UC-005 scenario is routed

**Raised by:** L6's solution-review gate, established empirically — it deleted the uc005 step
fixture at `pytest_configure` time from a scratchpad plugin (no repo edits) and re-ran
`tests/bdd/test_uc005_discover_creative_formats.py -k roundtrip`: **3 passed → 3 failed**.

§3.6 ratifies the grader as *"RED at head on the UC-005 collision, green after F16's deletion."*
The second half is unreachable, and for two stacked reasons — neither of which is the serialization
gap the design predicted:

1. **Ambiguous pinned ref.** `tests/helpers/pinned_schema.py:158` raises `PinnedSchemaError`:
   the feature line at `BR-UC-005-discover-creative-formats.feature:1071` names
   `list-creative-formats-response.json`, which resolves to **two** pinned documents
   (`creative/…` and `media-buy/…`). The generic step passes the feature-line token straight to the
   resolver. This is the same *one sentence, two meanings* disease one level down, and it is in
   frame for this lane — fixed by one feature-line edit to the category-qualified ref. (Note it
   contradicts the design's blanket "ZERO feature edits needed", which was scoped to F14 and holds
   there.)
2. **Catalog-vs-pin gap.** After qualifying the ref (tried both categories, identical result):
   3 violations, every one a `pixel_tracker` asset — *"at formats.0.assets.2/.3/.4 … is not valid
   under any of the given schemas"*. Source is `tests/fixtures/creative_formats/reference_formats.json`,
   captured from a post-pin reference creative agent: **45 of 57** reference formats carry
   `pixel_tracker` assets, and the pinned AdCP 3.1.1 asset union does not model that `asset_type`.
   The ADCP_TESTING catalog puts assets on the wire that the pin forbids.

**Ruling.** The lane's oracle is the **guard**: RED at head, green after the deletion, empty
allowlist. Fix the ambiguous ref (one feature-line edit). Then **surface** the pixel_tracker
pin-vs-catalog gap as a spec-grounded xfail-ledger entry naming the pin gap, plus a follow-up
ticket. Reconciling 45 of 57 reference formats against pinned 3.1.1 is real AdCP conformance work
and a lane of its own; it is not step-vocabulary governance. Restoring the weak uc005 body remains
forbidden — that is the disease.

**Invariant this establishes:** when deleting a vacuous assertion exposes a real defect underneath,
the defect is surfaced and routed — never re-covered by the assertion that was hiding it.

### A7 — Owner ruling (2026-08-14): §3.11 fixes the inheritance guard's collector, not just its allowlist

**Raised by:** the L11 early probe §3.11 mandates ("ATTEMPT THIS EARLY … if it flags
demonstrably-live entries, the collector has a blind spot and THAT is the real finding — escalate
rather than allowlisting"). It fired.

Replaying the guard's own collector at HEAD: 44 allowlist entries, 43 found, **0 new**, **1 stale** —
`('AdCPPackageUpdate', 'targeting_overlay')`. That entry is not stale-because-fixed. The class still
declares `targeting_overlay` in its own body and still inherits `LibraryPackageUpdate`; it is simply
**never visited**. `_get_library_type_mapping()` derives the local class name by stripping the
`Library` prefix — `LibraryPackageUpdate` → expects a local class literally named `PackageUpdate`
(which is itself in `ALIAS_ONLY_TYPES`, so even that name is skipped).

Measured blind spot — **6 live field redefinitions across 3 classes, entirely ungraded**:

| local class | library base | ungraded redefinitions |
|---|---|---|
| `AdCPPackageUpdate` | `PackageUpdate` | `targeting_overlay` |
| `SyncAccountsResponse` | `SyncAccountsResponse1` | `accounts`, `context`, `dry_run`, `ext` |
| `SyncCreativesResponse` | `SyncCreativesResponse1` | `creatives` |

Two of those three are **exactly the classes L7 modifies**.

**Ruling.** L11 maps by **MRO membership** instead of by name-minus-prefix, and dispositions all six
individually (inherit, or allowlist with a documented reason). The swap to
`assert_violations_match_allowlist` still lands. Closing the hole belongs in the same PR that grew
the allowlist by 3 with no stale-entry companion, and it puts L7's two classes under the guard for
the first time.

**Invariant this establishes:** an allowlist entry that reads as stale must be diagnosed before it is
deleted — "the guard stopped seeing it" and "the violation is gone" are opposite facts with identical
symptoms.

### A8 — Owner ruling (2026-08-14): ticket-filing discipline (binding on every ticket this plan authorises)

**Applies to:** §3.11's two authorised issues, the #1906 comment, and every follow-up ticket added by
A5 (broader shadow-overlap bars), A6 (pixel_tracker catalog-vs-pin gap) and A7 (if any disposition
defers).

Before opening ANY issue:

1. **Search GitHub extensively first** — not one query. Search open *and* closed, by symptom, by
   symbol name, by file path, and by the error text a reader would paste. `gh issue list --search`
   plus `gh search issues` across states. A near-duplicate filed because the first query missed is
   worse than no ticket.
2. **If an existing issue already covers it, do not file** — comment on that issue with the new
   evidence instead, and cite the comment URL wherever this plan expected a ticket number.
3. **If existing issues are related but not an exact match, LINK them** — reference them in the new
   issue body ("related to #N", "narrower than #N", "blocked by #N") and add a back-reference comment
   on the older issue pointing at the new one. Partial overlap must be made visible in both
   directions, never silently duplicated.

**Invariant this establishes:** the issue tracker is a shared index, not an append-only log — a new
ticket must be reachable from every issue a reader would plausibly search first.

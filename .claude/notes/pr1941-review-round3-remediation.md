# PR #1941 — round-3 remediation plan

Scope authority for the round-3 remediation. Head reviewed: `a4931cbd8`
(verification tree `/Users/konst/projects/salesagent-1900-pr1941`; work lands in
`/Users/konst/projects/salesagent-1900`). Primary sources: the round-3 synthesis
(`~/.local/state/pr-review-queue/prebid-salesagent/queue/170826_1422/pr1941/full-findings.md`),
its architecture spine (`review-architecture.md`), and the round-2 plan
(`.claude/notes/pr1941-review-round2-remediation.md`). Every file:line below was
re-verified at `a4931cbd8` — either by the round-3 verification log (which recorded
command + output per claim) or by direct spot-check while writing this plan.

**Amendment discipline (replaces the 1210 ALTERATIONS pattern).** If a ruling
changes a lane mid-flight, the lane's own text is edited in place with a dated
`> AMENDED <date>:` marker and its done-when is re-run. No append-only override
section: a reader of any lane sees its current truth, not an archaeology exercise.

---

## §0 Verdict and the honest claim

**The PR still achieves #1900.** Bullet-by-bullet at `a4931cbd8`:

| #1900 acceptance bullet | Status at HEAD |
|---|---|
| 1. `allOf` `properties` merged in the property walk | **MET** — but only in one of the two resolvers (`_resolve_response_item_schema:1206`); `_success_arm`'s `oneOf` branch still skips the merge → SF-7 |
| 2. Sample generator synthesizes valid enum/`Literal` values (raises where it cannot) | **MET** |
| 3. `GetMediaBuysResponse` / `SyncAccountsResponse` declare `status`, validate clean | **MET** — re-based / `CompletedTaskStatusMixin` with biconditional pin |
| 4. `_PROTOCOL_ENVELOPE_FIELDS` + tripwire deleted, nothing excluded in its place | **MET** |
| 5. Suite green with `status` graded for all registered response models | **PARTIAL** — requiredness is graded for all three envelope models, but `status` never enters `declared_fields` for the two `oneOf` models, so the model_dump-survival check (`:1512-1523`) — the one written for exactly the `confirmed_at` bug class — never sees it. The mechanism, not two lucky passes, is what the bullet demands → SF-7 |

**What blocks merge** (all fixed by this plan, none deferred):

1. **The type-ignore ratchet is red at HEAD**: `check_type_ignore_count.py` → `64 (+1 NEW vs baseline 63)`, exit 1. The hook runs at pre-push, so `make quality` reads green — the gate is red regardless. (L5)
2. **An xfail set grew**: `_UC005_PARTIAL_TAGS` +1 with `strict=False` and a FIXME pointing at an unowned issue — shrink-only ratchet, grown by the same PR that restates the rule. (L8)
3. **A reachable production defect with the wrong wire code**: any persisted status outside the enum raises a bare `ValueError` from inside `get_media_buys`' / `get_media_buy_delivery`'s per-row loop (one bad row fails the whole tenant listing), reaches the buyer as `VALIDATION_ERROR`/"correctable" for a seller-side store defect, and the backfill migration's inverted predicate backfills unknown legacy statuses **as committed** — the outcome `models.py:958-966` says must never happen. (L1)
4. **Two producers for a field the pin calls "stable after it is set"**: `create_media_buy` mints its own `confirmed_at`/`revision` (`_base.py:466-467`) beside the columns this PR made authoritative — demonstrably divergent on the auto-approve path (create says `1`+own clock; `get_media_buys` says `2`+column). Round-1 blocker R1-19, still open on the third round. (L4)
5. **The rejected reconcile notes**: three "Reconcile upstream in adcp-req" prose notes and a traceability row deleted with no successor — rejected outright by the owner (Ruling 1). (L9)

`Closes #1900, Advances #1928` stand. The PR description additionally records, after
this remediation: the `get_media_buys` envelope obligation is graded on a2a+mcp — the
full reachable surface, since the tool has no REST route (pre-existing surface fact,
honestly encoded by `_NO_REST_UC_TAG_PREFIXES`); and the `health: "ok"` wire-shape
addition (spec-legal, R1-15) is stated.

---

## §1 Rulings

### R-1 (OWNER, binding) — the `adcp-req` reconcile note is rejected outright

The three notes in `tests/bdd/features/BR-UC-019-query-media-buys.feature`
(`:171`, `:810`, `:898`) ending *"Reconcile upstream in adcp-req so `--merge` does
not re-add it"* are BS and must go. The round-3 synthesis's fallback — "file an
adcp-req reconciliation issue and cite the number at each note" — is **also
rejected**; do not implement it. A prose note is not a mechanism, and neither is an
issue number pasted above one.

**The mechanics that make this real** (verified): the feature is generated —
`# Generated from adcp-req @ render ... (merge mode) / DO NOT EDIT -- re-run:
python scripts/compile_bdd.py --merge`. In `merge_feature` Pass 1
(`scripts/compile_bdd.py:1282+`), a scenario present in the adcp-req TARGET and
absent from the local LEGACY file classifies **NEW-ADD** and is re-added. There is
no tombstone mechanism. So a local deletion whose upstream row survives is a
deletion that does not exist. **And the upstream is ours**: `~/projects/adcp-req`
→ `github.com/KonstantinMirin/adcp-req-experiment` — the owner's own repo, locally
editable. Option (a) — fix the source of truth for real, now — is fully actionable.

Per-row verdicts (rows located in `~/projects/adcp-req/tests/features/BR-UC-019-query-media-buys.feature`):

| Row | Upstream location | Verdict | Reasoning |
|---|---|---|---|
| `revision absent` | `:719` (Examples row) | **(a) — delete upstream, now** | Premise-impossible, correctly argued: `MediaBuy.revision` is `nullable=False, default=1, server_default='1'`; the wire type is bare `int`. The reachable defective values (0, −1) stay and grade the schema minimum. |
| `confirmed_at_not_iso8601` | `:784` (Examples row) | **(a) — delete upstream, now** | Premise-impossible: column is `DateTime(timezone=True)`, wire value is a Pydantic datetime; a non-ISO string can neither persist nor round-trip. |
| BR-RULE-150 INV-11 (`unknown persisted status defaults to active`) | `:533` (scenario) + `:539` rule comment | **(a)+(b) — rewrite upstream to the enforced obligation, regenerate, grade it** [MINE — R-M2 below] | The upstream rule mandates a defensive default the pinned item schema forbids (`status: "active"` with null `confirmed_at` fails the `allOf/if` guard) and that owner ruling A3 (round 2) explicitly rejected: unknown values are refused at the write boundary, never defaulted at read. The obligation is real and regains a graded home: after L1, an unmapped status reaching the read path yields `CONFIGURATION_ERROR`/terminal on the wire — that IS the rewritten scenario's Then. The `T-UC-019-inv-150-11` traceability row (deleted from both the feature AND `bdd-traceability.yaml`, leaving the obligation homeless — the clearest instance of the disease) is restored under the rewritten scenario's id. |
| BR-RULE-291 error-code drop (`SCHEMA_VIOLATION` on defective-revision rows) | `:711-719` | **(a)+(b) — correct upstream, restore the assertion locally** | `SCHEMA_VIOLATION` is not in the pinned `enums/error-code.json` at all — conformance-runner vocabulary, never a wire code. Upstream: replace the outcome on the reachable rows (0, −1) with the real wire contract — refusal carrying `CONFIGURATION_ERROR`. Locally: restore the error-code assertion via `assert_wire_error("CONFIGURATION_ERROR")` (L6), after L1 makes production emit it. The current grader asserts NO code on a path that errors — a fix or regression in either direction is invisible. |

**Contingency (c)** — only if the owner rejects an upstream edit for some row: a
machine-checked tombstone (`RETIRED_UPSTREAM_IDS: frozenset[str]` in
`scripts/compile_bdd.py` that drops those scenario ids in Pass 1, plus a guard that
fails if a tombstoned id appears in a compiled feature). Not a comment. Not the plan
of record — (a) is.

### R-2 (OWNER, binding) — provenance classification on every finding

Every finding is exactly one of **INTRODUCED** (this PR's diff created it — fixed
here, non-negotiable), **IN-SCOPE** (pre-existing, but on the surface this PR
rebuilds or implicated by #1900/#1928 acceptance — fixed here), **UNCOVERED**
(pre-existing, outside the PR's surface, found because this work looked — filed and
routed with an owned ticket; fixing here needs explicit justification). The tag
appears in §2's ledger, in every lane header, and in every beads issue. No lane
mixes provenance classes in one step without saying so.

### R-M1 (MINE) — the wire code for a seller-side store defect is `CONFIGURATION_ERROR`/terminal

**Spec grounding (Spec-Grounding Gate):** pinned AdCP 3.1.1,
`dist/schemas/3.1.1/enums/error-code.json` `enumMetadata` —
`VALIDATION_ERROR = {recovery: correctable, suggestion: "review error details and
fix field values"}` (advice the buyer cannot act on for data the seller owns; an
invitation to retry), `CONFIGURATION_ERROR = {recovery: terminal, suggestion:
"surface to a human at the seller … MUST NOT auto-retry"}` — the metadata that
matches. The PR's own feature prose at `BR-UC-019:810` argues the same. Conformance
storyboard: ungraded by the pinned storyboards (the `check_buy_status` step does not
grade this refusal); graded locally by the restored BR-RULE-291 rows and the
rewritten INV-11 scenario (L6/L9). **Overturned if:** the owner reads the pin's
delegation differently — then L1's typed error changes its code member and L6/L9's
assertions follow; nothing else in the plan moves.

### R-M2 (MINE) — INV-11 is rewritten upstream, not retired

Stated in the R-1 table. **Overturned if:** the owner prefers retiring INV-11
outright upstream — then the obligation's home is only the L1 write-boundary
integration test plus the L6 read-path error scenario under a new local id, and the
traceability restoration points there instead.

### R-M3 (MINE) — the UC-005 fixture is repaired by regeneration first, narrowing second

`scripts/refresh-reference-formats.py` owns
`tests/fixtures/creative_formats/reference_formats.json`. Attempt regeneration
against the pin first; if the catalog's `pixel_tracker` tracker-URL requirements
genuinely cannot be expressed in the 3.1.1 declaration union, narrow the fixture the
one scenario seeds to the pin-expressible subset and self-assign #1998 for the full
catalog. **Either way the `_UC005_PARTIAL_TAGS` entry does not ship.** Overturned
if: the owner wants the catalog left byte-identical — then narrowing is the only
path, and the entry still goes.

### R-4 (required owner action, phase 0) — issue ownership

#1998, #1999, #2000 are OPEN with `assignees: []` (re-verified 2026-08-17). Under
the deferral rule an unassigned issue carries nothing. **Owner: KonstantinMirin.
When: before any remediation commit lands** — self-assign all three. #1353 and
#1906 (both OPEN, unassigned) likewise need an assignee before any Note in this PR
treats them as a home; they are not this PR's blockers.

---

## §2 Provenance ledger

The 4 re-raised round-1 items ARE SF-1..SF-4. Root-cause clusters are §3's; lanes
are §5's. Split: **12 INTRODUCED / 2 IN-SCOPE / 0 UNCOVERED among the 14**; the
UNCOVERED column below lists the adjacent pre-existing items the review surfaced,
routed not fixed.

| Id | One line | Provenance | Root cause (§3) | Lane | Priority |
|---|---|---|---|---|---|
| SF-1 (↩R1-19) | Create response mints `confirmed_at`/`revision` beside the authoritative columns; `_buy_and_revision_or_raise` re-implements `get_by_id_or_raise` with a degraded message | **INTRODUCED** (pre-existing defaults; the contradiction and the guard-blind second producer are this PR's) | C2 second producer | L4 | P1 |
| SF-2 (↩R1-17) | `AlwaysIncludeFieldsMixin` shaped as a `super().model_dump()` override: third site unconvertible, type-ignore ratchet red (64/63), vacuous named oracle | **INTRODUCED** | C4 wrong abstraction shape | L5 | **P0** |
| SF-3 (↩R1-20) | `bound_factory_session` built, adopted at one of the two named files; the unconverted file is one this PR adds | **INTRODUCED** | C6 conversion left incomplete | L11 | P2 |
| SF-4 (↩R1-27) | `KNOWN_OVERRIDES` comment: "Both narrowings" over three entries; "~30" vs measured 24 | **INTRODUCED** | C7 prose with no citable home | L10 | P2 |
| SF-5 | Status vocabulary landed as check not type: three coercions/three failure policies, blind read-path index raises wrong code, migration polarity inverted, dead residue | **INTRODUCED** | C1 vocabulary not a type at the seam | L1 | **P0** |
| SF-6 | The PR's own wire-grading standard not applied to its own new obligations: dormant UC-003/UC-002 scenarios, module-wide REST drop, no-code error grader, third wire reader | **INTRODUCED** | C5 grading wiring unfinished | L6 | P1 |
| SF-7 | Two success-arm resolvers; `oneOf` branch never merges the envelope arm, so `status` misses the dump-survival check on 2 of 3 models | **IN-SCOPE** (pre-existing dup, half-fixed here; #1900 bullet 5 is about the mechanism) | C3 two answers to one question | L7 | P1 |
| SF-8 | `_UC005_PARTIAL_TAGS` +1 `strict=False`: the retired anti-pattern re-enters through the xfail set; cause is repo-owned fixture data | **INTRODUCED** (entry; fixture data pre-existing but repo-owned and in reach) | C8 instrument went red → excluded | L8 | **P0** |
| SF-9 | Persisted→wire projection moved into `models.py` and re-exported back out; zero call sites import from the definition | **INTRODUCED** | C1 (layer half of the same move) | L3 | P2 |
| SF-10 | Approval-status transition decided in three divergent copies, two in admin routes — now an invariant input to the commitment stamp | **IN-SCOPE** (pre-existing dup, promoted into an invariant input by this PR's stamp) | C2 (decision has no domain owner) | L2 | P1 |
| SF-11 | Rules restated as prose, stale on the introducing commit: `MEDIA_BUY_UNCONFIRMED_STATUSES` ×7, phantom `REST_ENDPOINT`, two schema-ref spellings, two dead citations, one beads id, self-contradicting docstring | **INTRODUCED** | C7 prose with no citable home | L10 | P2 |
| SF-12 | Write-seam bookkeeping oracle copy-pasted ×6 in 5 files, 4 distinct state readers, one raw `SASession` in a test body | **INTRODUCED** | C6 conversion left incomplete (the contract this PR invented has no shared oracle) | L11 | P2 |
| SF-13 | New match-overlap guard hand-rolls a third Gherkin lexer instead of `pytest_bdd.feature.get_feature` | **INTRODUCED** | C4 wrong abstraction shape | L12 | P2 |
| SF-14 | Four retirements parked in feature prose, no issue; `T-UC-019-inv-150-11` homeless; #1998/#1999/#2000 unowned | **INTRODUCED** | C8 + Ruling 1 | L9 (+R-4) | P1 |

**UNCOVERED — routed, not fixed here** (each gets its own beads child, closable out
of this epic):

| Id | One line | Route |
|---|---|---|
| U-1 | Five pre-existing hand-rolled factory-session binds (`test_admin_ui_data_validation.py:292`, `test_execute_approved_platform_ids.py:41,136`, `test_inventory_tree_lazy_loading.py:37`, `test_delivery_simulation_config.py:50`, `tests/admin/conftest.py:44`) | Beads child (routing), per-A8 GitHub search before filing a GH issue; untouched by this diff |
| U-2 | UC-018's three remaining `_serialized_response` model_dump graders (`test_uc018_list_creatives.py:203,225,236,356`) | Beads child (routing); the natural next slice of the wire-grading work, not this PR's |
| U-3 | `get_media_buys` has no REST route — surface decision | PR-description note only (the honest encoding already exists: `_NO_REST_UC_TAG_PREFIXES`); no ticket unless the owner wants the route |
| U-4 | `str(response)` repr sweep beyond `GetMediaBuysResponse` | Evidence already on #1906 — needs an assignee (R-4), nothing else here |

---

## §3 The design faults under the findings

Lead diagnosis (from `review-architecture.md`, confirmed): in seven of the nine
architecture findings the shape is identical — **a boundary/abstraction was created,
and the call sites that were already written kept their old path.** The clusters:

**C1 — the closed vocabulary was landed as a runtime check, not as the seam's type**
(SF-5; SF-9 is the layer half of the same move). Every write door stays `str`, the
column stays `Mapped[str]`, three consumers re-derive the coercion with three
failure policies, and the read path's blind index depends on an invariant held by
convention over data no migration normalises — while the projection map was dragged
into the ORM module and re-exported to hide the move. *Correct architecture:* the
vocabulary is the type at the seam — typed signatures, one `parse()` coercion
raising one typed terminal error, a normalising migration; vocabulary in
persistence, projection in presentation, one import home each. *Smallest change:*
L1 + L3.

**C2 — the repository was declared the owner of the item state, and other layers
still produce or decide it** (SF-1, SF-10). The response model is a second producer
(`default_factory` is invisible to the write-seam guard, which scans assignments);
the transition decision that triggers the commitment stamp lives in three divergent
copies, two in admin routes. *Correct:* a response model carries no default for
persisted state — the tool binds the row; one domain function decides the
transition and hands the answer to `update_status`. *Smallest:* L4 + L2.

**C3 — the instrument holds two answers to "what shape does the pin promise"**
(SF-7). The PR's own headline correction — merge `allOf` `properties`, not just
`required` — was applied to one of the two resolvers, leaving a quieter version of
`_PROTOCOL_ENVELOPE_FIELDS`: not a subtraction list, an arm the walk forgets to
merge on one of two code paths. *Correct:* one `_success_shape()` both halves call.
*Smallest:* L7.

**C4 — abstractions given the wrong shape, so they cost what they were meant to
save** (SF-2, SF-13). A `super()`-calling `model_dump` override over an
unconditional frozenset: the conditional site has no seat, `super()` needs a new
type-ignore, `info.mode` is unavailable so the mode hazard is documented instead of
fixed — while `NestedModelSerializerMixin` one screen up shows the shape that has
none of these costs. The new guard's hand-rolled Gherkin lexer is the same fault:
the parse pytest-bdd already exposes was re-implemented, and the re-implementation
can silently under-read. *Correct:* `@model_serializer(mode="wrap")` with a
per-field predicate; `pytest_bdd.feature.get_feature`. *Smallest:* L5 + L12.

**C5 — the wire-grading standard exists, but the wiring makes bypassing it easier
than using it** (SF-6). The guarded success-side reader lives on the BDD `ctx`, its
error-side twin on `TransportResult`; the composite env this PR built is reachable
from pytest but not from `_harness_env` — so the cheapest home for a new obligation
was a pytest module while the scenarios written for those exact sentences sit
xfailed under a reason this PR made false. *Correct:* the guard lives on the object
that holds the wire (`TransportResult.require_wire()`); obligations live in the
feature corpus where the harness parametrizes transports. *Smallest:* L6.

**C6 — extractions closed on "mechanism built", not "instances zero"** (SF-3,
SF-12). The session-binding fixture and the write-seam contract each got the right
mechanism and left copies behind — one of them in a file this PR adds, against the
new fixture's own docstring. *Correct:* every extraction ends at instance-count
zero, machine-checked. *Smallest:* L11.

**C7 — rules whose only home is English in a comment, stale on the commit that
introduces them** (SF-4, SF-11). Seven citations of a symbol that does not exist,
with inverted polarity; a declared REST endpoint that routes nowhere; the sharpest
consequence being executable — the backfill migration encodes the partition as its
complement, so unknown legacy statuses backfill as committed. *Correct:* each rule
has one citable executable home; sites point at it. *Smallest:* L10 (prose) with the
executable half in L1 (migration predicate).

**C8 — the newly-honest instrument went red and the response was to exclude the
signal** (SF-8, SF-14). The exact anti-pattern #1900 exists to retire —
"the instrument can now measure X, X fails, so exclude X" — re-entering through an
xfail set and through prose-parked retirements. *Correct:* fix the cause (fixture /
upstream source), delete the routing. *Smallest:* L8 + L9.

---

## §4 Why round 2 did not hold

Four round-1 items re-raised, and two disease shapes re-introduced. The process
faults, named, with the corrections this plan adopts:

1. **Extraction lanes closed on "mechanism built", not "instances zero"** (R1-17,
   R1-20). Round 2's L7/L9 done-whens were satisfiable by building the mixin/fixture
   and converting the named sites — nothing counted the remainder, and R1-17's
   remainder was *unconvertible* because the abstraction's shape (unconditional
   frozenset) had no seat for the conditional case, which nobody noticed because no
   step tried the third site. **Correction:** every extraction lane in §5 ends with
   a machine-checkable zero (`grep -c` = 0, guard green with empty allowlist), and
   the abstraction's shape is validated against the *hardest* remaining site first.

2. **A plan assertion stood in for a grader** (R1-19). Round 2 §3.3 closed the
   create arm with *"After L1 the create arm's defaults are exact by construction —
   correct the comment, no code change"* — a claim that is false on the auto-approve
   path (create at rev 1, `update_status` bumps to 2 and stamps) and that no test
   ever checked; the lane closed on the sentence. **Correction:** no §5 step's
   done-when is a statement about the code; each carries a **Graded-by** or a
   red/green mutation, and any "already correct" claim is either graded or deleted.

3. **Finding halves dropped silently** (R1-27). The lane fixed the mechanism half
   (stale-entry companion, MRO collector) and never revisited the prose half — no
   per-finding checklist tied lane closure to finding closure. **Correction:** §2's
   ledger is 1:1 findings→lanes; a lane's done-when enumerates every finding id it
   subsumes, and closure re-checks each.

4. **Routing degraded into unowned parking under infrastructure failure** (SF-8,
   SF-14). The round-2 session hit beads/GitHub outages mid-flight
   (`pr1941-unrecorded-beads-state.md`: "GitHub is unreachable … deliberately not
   done"); the A6 ruling's "surface and route" steps were left half-done — issues
   filed later, never assigned; prose notes shipped in place of mechanisms — and
   nothing tracked the residue as a blocker. **Correction:** a final reconciliation
   step (§5 L13) re-runs the round-3 verification-log commands and re-checks every
   deferral's issue state (`OPEN` + assigned) before the branch is declared done;
   an unfinished routing step is a red gate, not a note.

5. **An instrument gap let a red ratchet read green** (SF-2b). The type-ignore hook
   runs at pre-push only, so `make quality` and the PR description both reported 63
   while the tree was at 64. **Correction:** every lane's verify step runs
   `uv run python .pre-commit-hooks/check_type_ignore_count.py` explicitly alongside
   `make quality` (the hook stays at pre-push — the commit-stage hook count is
   capped by D27).

6. **The frozen-plan + ALTERATIONS pattern hid the current truth** (both the 1210
   formula's weakness and round 2's: A1–A8 overrode §3 without correcting it, and
   the false R1-19 claim survived precisely because its section was frozen).
   **Correction:** the amendment discipline in this plan's preamble.

---

## §5 Work order — lanes

One lane per root cause. Steps are numbered and load-bearing in order. Notation:
**Graded by:** the named scenarios/tests and the transports that execute them
(in-process transports: a2a, mcp, rest; e2e_rest where noted). **Author:** new
coverage this lane writes. **Red/green:** the mutation that must redden the grader.
Every lane ends with a falsifiable done-when. Global verify per lane:
`make quality` **plus** `uv run python .pre-commit-hooks/check_type_ignore_count.py`.

Lane order/deps: L1 → {L2, L3, L6, L9}; L4 → L6; the rest independent. L13 last.

### L1 — the vocabulary becomes the type at the seam [SF-5 · INTRODUCED · P0]

1. **One coercion.** Add `PersistedMediaBuyStatus.parse(raw: str | None) -> Self`
   (classmethod, case-normalising) on the enum at
   `src/core/database/models.py:916+`, raising a new typed `AdCPError` subclass
   (e.g. `AdCPPersistedStateError`) carrying `CONFIGURATION_ERROR` /
   `recovery: terminal` (R-M1) and naming the buy id, the column, and the legal
   member set.
2. **Route the three coercion sites through it**:
   `repositories/media_buy.py:64` `_validated_status` (return type becomes
   `PersistedMediaBuyStatus`), `models.py:1016` `is_media_buy_seller_confirmed`
   (via a non-raising `parse_or_none` or membership on the parsed member — one
   policy, stated), `src/core/tools/_media_buy_status.py:149` (the blind
   `PersistedMediaBuyStatus(persisted)` index).
3. **Type the seam signatures**: `update_status(status: PersistedMediaBuyStatus)`,
   `create_from_request(..., status: PersistedMediaBuyStatus = PersistedMediaBuyStatus.DRAFT)`
   (`repositories/media_buy.py:371,514`); callers pass members. `StrEnum` keeps the
   SQLAlchemy bind, JSON serialization, and `== "draft"` comparisons identical —
   signature change, not behaviour change.
4. **Ship the status-normalising migration** next to `7f3a1c9e2b04` (owner ruling
   A1's own principle: legacy data is fixed by migration, never by a code path).
   Non-empty `upgrade()` and `downgrade()` (migration-completeness guard); survey
   first, then map any out-of-vocabulary value to its member or abort loudly listing
   affected ids — never silently coerce.
5. **Flip the backfill predicate**: `alembic/versions/7f3a1c9e2b04_...py:53,76` —
   `AND lower(status) NOT IN :unconfirmed` → freeze the **committed** list literally
   (`WHERE lower(status) IN (...)`), both arms, so the default for an unknown value
   matches the enum's stated rule. The freeze-not-import decision is unchanged and
   correct. Migration is unmerged, so editing it is allowed.
6. **Delete the residue**: `PersistedMediaBuyStatus.seller_confirmed`
   (`models.py:948-963`, zero callers — or make it the single predicate and thin the
   free function; one of the two, not both); the dead
   `normalize_persisted_media_buy_status` / `_PERSISTED_STATUS_TO_ADCP` /
   `_UNREFINED_PRE_FLIGHT_OVERRIDES` family (`media_buy_list.py:499-522`) with its
   three stale comment blocks and the test rows pinning the dead map
   (`test_media_buy_status_consistency.py:204-224`); dead `import logging`/`logger`
   (`_media_buy_status.py:41,53`).
7. **Rewrite the now-false docstring** at `_media_buy_status.py:116-120` ("never
   returned verbatim and never dropped") to state the enforced contract: unmapped
   persisted state is a seller-side defect surfaced as `CONFIGURATION_ERROR`.

- **Graded by:** the rewritten INV-11 scenario (L9/L6) on a2a+mcp asserting
  `assert_wire_error("CONFIGURATION_ERROR")` on a factory-seeded unmapped status
  (factories bypass the repository, so the Given is seedable);
  `tests/integration/test_media_buy_revision_confirmation.py::test_an_unrecognised_status_is_refused_at_the_write_boundary`
  (exists — update to the typed error); **Author:** one migration test beside
  `test_confirmed_at_backfill_migration.py` proving an out-of-vocabulary legacy row
  is normalised/aborted, and that a status in NEITHER list is **not** backfilled as
  committed (the polarity oracle).
- **Red/green:** revert step 5's predicate → the polarity test reddens; change the
  typed error's code member to `VALIDATION_ERROR` → the INV-11 wire assertion
  reddens.
- **Done-when:** `grep -rn 'or "").lower()' src/` shows one implementation (the
  parse); `_validated_status`/`update_status`/`create_from_request` signatures
  typed; `git grep -n normalize_persisted_media_buy_status` → 0;
  `git grep -n "\.seller_confirmed"` → 0 or 1 canonical; both migration arms use
  the committed list; SF-5's repro
  (`resolve_canonical_status(SimpleNamespace(status='legacy_state',...))`) raises
  the typed error, not `ValueError`.

### L2 — one owner for the approval-status transition decision [SF-10 · IN-SCOPE · P1 · dep L1]

1. Extract the scheduler's `_compute_new_status`
   (`src/services/media_buy_status_scheduler.py:122-177` — the most complete of the
   three) into one domain function in the media-buy business layer beside
   `_media_buy_status`/`media_buy_create`:
   `(media_buy, now, creatives_approved) -> PersistedMediaBuyStatus` (typed by L1).
2. Convert `src/admin/blueprints/operations.py:422-452` (inline copy, rewritten by
   this diff) to call it and hand the result to `update_status`.
3. Convert `src/admin/blueprints/creatives.py:81-103`
   (`_compute_media_buy_status_from_flight_dates`, call site `:653-659`) likewise;
   delete both route-local copies. Note the behaviour fix this encodes: a buy
   approved past its end date through the creative path becomes `completed`, not
   `active`-stamped-committed.
- **Graded by:** existing admin/scheduler transition tests
  (`test_media_buy_status_scheduler.py`, `tests/admin/test_workflows_blueprint.py`,
  `tests/admin/test_creatives_blueprint.py`) via the L11 shared oracle; **Author:**
  one integration case: approve a buy past its flight end through the creatives
  route → persisted status `completed`, `confirmed_at` stamped per the committed
  partition — the case the divergent copy got wrong.
- **Red/green:** re-inline a copy returning only `active|scheduled` in
  `creatives.py` → the authored past-end-date case reddens.
- **Done-when:** `grep -rn "def _compute" src/admin/blueprints/ | grep -i status`
  → 0; exactly one definition of the transition function in the business layer;
  the two admin blueprints contain no lifecycle arithmetic.

### L3 — the wire projection returns to presentation; one import home [SF-9 · INTRODUCED · P2 · dep L1]

1. Move `PERSISTED_STATUS_TO_CANONICAL` (`models.py:988`) and `CANONICAL_STATUSES`
   (`:1013`) — with their 25-line comment block — back to
   `src/core/tools/_media_buy_status.py`, keyed by the imported enum (the
   keyed-by-member typing win survives the import).
2. Delete both re-export forms at `_media_buy_status.py:45-51`
   (`CANONICAL_STATUSES as CANONICAL_STATUSES  # re-export: ...`); consumers
   (`media_buy_delivery.py:111,930`, `media_buy_list.py:23,504`,
   `test_media_buy_status_consistency.py:19-25`) already import from
   `_media_buy_status`, so most call sites do not move.
3. `PersistedMediaBuyStatus`'s docstring at `models.py:921-923` ("The wire
   projection lives in `src.core.tools._media_buy_status`") becomes true — verify,
   don't restate.
- **Graded by:** `tests/unit/test_media_buy_status_consistency.py` (existing map
  pins) + import-usage guard.
- **Red/green:** mechanical move — the grade is the done-when.
- **Done-when:**
  `grep -rn "PERSISTED_STATUS_TO_CANONICAL\|CANONICAL_STATUSES" src/core/database/`
  → 0; no `as X  # re-export` form remains; each symbol has exactly one import path.

### L4 — one producer per persisted field: the create arm reads the row [SF-1 ↩R1-19 · INTRODUCED · P1]

1. Bind the row at `src/core/tools/media_buy_create.py:3637` (the
   `create_from_request(...)` call whose returned row is currently discarded).
2. Thread `confirmed_at=row.confirmed_at`, `revision=row.revision` into every
   `sync_success(...)` site: `media_buy_create.py:3556,4090`,
   `src/admin/blueprints/operations.py:515`, `src/adapters/base.py:330`,
   `src/adapters/mock_ad_server.py:578,699`. If an adapter helper cannot see the
   row, move the boundary — do not keep a default.
3. **Delete both defaults** at `src/core/schemas/_base.py:466-467` so omission is a
   construction error. Declare `confirmed_at: AwareDatetime | None` locally with the
   `create-media-buy-response.json@3.1.1` citation (the schema types it
   `["string","null"]` and required — the SDK's non-nullable typing is the drifted
   side; the `SyncAccountsResponse` precedent applies). Delete the inverted-grounding
   NOTE comment at `:464-465` and the false comment at `_base.py:625`.
4. Delete `_buy_and_revision_or_raise` (`src/core/tools/media_buy_update.py:111-128`)
   in favour of `uow.media_buys.get_by_id_or_raise(media_buy_id, context=req.context)`
   at the three call sites (`:579,:758,:1414`), reading `.revision` off the row —
   restores message/suggestion/context (`AdCPMediaBuyNotFoundError('mb_123')`
   currently puts the bare id in `message` with `suggestion=None`).
5. Add the **create arm** to
   `tests/integration/test_media_buy_revision_producer_agreement.py` (today: zero
   `confirmed_at` occurrences, no create row): create → auto-approve →
   `get_media_buys`; assert the create response's `confirmed_at`/`revision` equal
   what `get_media_buys` publishes, on the wire.
- **Graded by:** the extended producer-agreement module (a2a+mcp; REST per L6);
  ultimately `@T-UC-002-v31-success-revision-and-actions` once L6 wakes it
  (asserts `confirmed_at` ISO-8601 + `revision >= 1` on the create wire, three
  in-process transports).
- **Red/green:** re-add `revision: int = 1` as a default and drop the threaded
  kwarg at one site → the create-vs-get agreement row reddens on the auto-approve
  path (create would report 1, get reports 2).
- **Done-when:** `grep -n "default_factory=lambda: datetime.now" src/core/schemas/_base.py`
  → 0 in `CreateMediaBuySuccess`; every `sync_success(` call site passes both
  fields; `git grep -n _buy_and_revision_or_raise` → 0;
  `grep -c confirmed_at tests/integration/test_media_buy_revision_producer_agreement.py` > 0.

### L5 — the always-include mixin becomes a wrap serializer with a conditional seat [SF-2 ↩R1-17 · INTRODUCED · P0]

1. Re-express `AlwaysIncludeFieldsMixin` (`src/core/schemas/_base.py:356-386`) as
   `@model_serializer(mode="wrap")` — the `NestedModelSerializerMixin` shape at
   `_base.py:281`: no `super()` call (ignore gone), `info.mode` available (the
   mode="json" hazard becomes fixed behaviour, not a docstring). Per-field
   predicate: `_ALWAYS_INCLUDE_NULL_FIELDS` for the unconditional set plus an
   overridable `_should_always_include(field) -> bool` (or `{field: gating_attr}`
   mapping) for the conditional case. **Shape-check against the hardest site first**
   (`delivery.py`, §4 correction 1).
2. Adopt at `src/core/schemas/delivery.py:329-339`; delete the hand-rolled
   `next_expected_at` block. Existing adopters (`account.py:54`, `_base.py:2907`)
   carry over.
3. Delete the `# type: ignore[misc]` at `_base.py:383`. Ratchet returns to 63.
4. **Grade it where it can fail**: the null-`confirmed_at` premise is reachable
   (`rejected`/`canceled` are published in `media_buys[]` via `T-UC-019-inv-150-7`).
   **Author:** one Gherkin line + one Examples row seeding a null-confirmed buy,
   asserting the `confirmed_at` KEY is present with value `null` on the wire
   (`wire_dict`), a2a+mcp.
5. Correct `tests/unit/test_adcp_contract.py:452`'s docstring — it names
   `then_media_buy_includes_confirmed_at` as the behavioural net, which cannot fail
   for this (only reached with non-null seeds). Name the authored step.
- **Graded by:** the authored null-confirmed row (a2a+mcp); the existing mixin
  adopter tests; `check_type_ignore_count.py` exit 0.
- **Red/green:** delete the wrap serializer's re-insert branch → the authored row
  reddens (key absent from the wire under `exclude_none`). Mutate the re-insert to
  emit the raw Python value under `mode="json"` → the same row reddens on the value.
- **Done-when:** `grep -rn "not in result" src/core/schemas/` → 0;
  `check_type_ignore_count.py` → `63`, exit 0; the authored row green on both
  transports.

### L6 — finish the wire-grading wiring the PR built [SF-6 · INTRODUCED · P1 · deps L1, L4]

1. **One guarded reader per side, on the object that holds the wire**: add
   `TransportResult.require_wire() -> dict[str, Any]` to `tests/harness/transport.py`
   beside `assert_wire_error`; re-express `wire_dict(ctx)`/`wire_field(ctx)`
   (`tests/bdd/steps/_outcome_helpers.py:18,43`) as thin delegations; delete
   `_wire()` (`tests/integration/test_media_buy_revision_producer_agreement.py:105-111`)
   and the partial fourth copy noted at `test_wire_omission_matrix.py:308`.
2. **Move the obligations into the feature corpus**: add a `_UC003_REVISION` arm to
   `_harness_env` (`tests/bdd/conftest.py`, beside `_UC003_MANUAL_APPROVAL` at
   `:3355-3387`) seeding through `MediaBuyCreateUpdateListEnv` — the env this PR
   built and wired only into `tests/integration/`. The `@T-UC-003-revision-*`
   family (19 parametrizations, xfailed at `:3390` under the now-false "UC-003
   harness not yet wired") executes with Thens reading `wire_field`. Same for
   `@T-UC-002-v31-success-revision-and-actions` (closes L4's grading gap). If
   waking them surfaces real production failures, fix or report as blocker — never
   re-route to xfail (test-integrity policy).
3. **Transport lists from reachability per scenario, not one module constant**:
   `_WIRE_TRANSPORTS` (`test_media_buy_revision_producer_agreement.py:73`) — the two
   vanished-row cases drive `update_media_buy` only, which routes
   `PUT /api/v1/media-buys/{id}` (proven by this PR's own
   `test_harness_rest_refusal.py::TestNonListRestRoutingIsPreserved`); they get
   `[A2A, MCP, REST]`. Only the cases polling `get_media_buys` keep the two-wire
   list, reason stated at the list.
4. **Restore the error-code outcome** on the defective-revision rows:
   `then_sub_minimum_revision_never_published`
   (`tests/bdd/steps/domain/uc019_query_media_buys.py:3042`) and
   `_published_media_buy_entries` (`:3002-3019`, hand-rolled
   `ctx.get("wire_error_envelope")`) re-expressed through
   `ctx["result"].assert_wire_error("CONFIGURATION_ERROR")` (recovery defaults to
   the pinned enum — non-vacuous). Depends on L1's code and L9's upstream row
   correction.
- **Graded by:** the woken UC-003 revision family (a2a/mcp/rest), the woken UC-002
  v31 scenario (a2a/mcp/rest), the restored BR-RULE-291 rows (a2a+mcp), the
  producer-agreement REST arm.
- **Red/green:** revert `media_buy_update.py`'s persisted-revision read to the
  schema default → `@T-UC-003-revision-success-increments` ("revision with value
  8") reddens on all three transports. Swap production's refusal code back to a
  bare `ValueError` → the restored 291 rows redden.
- **Done-when:** `pytest tests/bdd/test_uc003_update_media_buy.py -rxX -k increments`
  → 3 passed 0 xfailed; `pytest tests/bdd/test_uc002_create_media_buy.py -rxX -k
  v31_sync_success` → passed; `git grep -n "def _wire(" tests/` → 0; no module-wide
  `_WIRE_TRANSPORTS` constant applied to REST-reachable cases; zero new xfail
  entries.

### L7 — one success-shape resolver in the alignment suite [SF-7 · IN-SCOPE · P1]

1. Smallest step first: make `_success_arm`'s `oneOf` branch
   (`tests/unit/test_pydantic_schema_alignment.py:1046-1049`) return
   `_merge_composed(arm, schema)` exactly as `_resolve_response_item_schema:1206`
   does.
2. Collapse the two resolvers into one
   `_success_shape(schema, *, selector=None, item_key=None)`; both the
   declared-fields/sample derivation (`:1096`) and the requiredness check call it —
   the same argument this PR makes for unifying `required` and `properties`.
3. Add a standing assertion that `status` appears in the derived `declared_fields`
   of **every** registry row — the mechanism #1900's fifth bullet demands, not two
   models passing by accident.
- **Graded by:** `test_declared_fields_exist_in_schema`'s populate-dump-survive
  block (`:1512-1523`) now visiting `status` on `SyncAccountsResponse` /
  `SyncCreativesResponse`; the new standing assertion.
- **Red/green:** give `SyncAccountsResponse` a custom `model_dump()` that drops
  `status` → the survival check reddens (it does not today — that is the finding).
- **Done-when:** one resolver function; the measured triple
  (`declared` vs `required(resolver)`) agrees for all three models with `status` in
  both; the red/green mutation verified.

### L8 — repair the UC-005 fixture; the xfail entry does not ship [SF-8 · INTRODUCED · P0]

1. Regenerate `tests/fixtures/creative_formats/reference_formats.json` via
   `scripts/refresh-reference-formats.py` against the pin (R-M3). If `pixel_tracker`
   (139 occurrences, 45/57 formats) cannot be expressed in the 3.1.1 declaration
   union of `core/format.json` (16 arms, no `pixel_tracker` — verified; the
   manifest-side `asset-union.json` DOES carry it, so the follow-up must not chase
   the wrong file), narrow the formats that one scenario seeds to the expressible
   subset so the roundtrip obligation stays graded, and leave the full catalog to
   #1998 (self-assigned per R-4).
2. Delete the `T-UC-005-storyboard-format-id-roundtrip-from-products` entry from
   `_UC005_PARTIAL_TAGS` (`tests/bdd/conftest.py:774-792`).
- **Graded by:** the UC-005 storyboard scenario itself — 3 parametrizations
  (a2a/mcp/rest) back to plain PASS, grading verbatim `format_id` roundtrip,
  non-empty `formats[]`, and full pinned-schema validity.
- **Red/green:** re-introduce one `pixel_tracker` asset into a seeded format → the
  scenario reddens on schema validity (proving the grader is live, not vacuous).
- **Done-when:** `git diff main...HEAD -- tests/bdd/conftest.py | grep T-UC-005-storyboard`
  → no added entry; `pytest tests/bdd/test_uc005_discover_creative_formats.py -rxX
  -k roundtrip` → 3 passed (or 6 passed if both scenarios), 0 xfailed.

### L9 — generated-feature divergences reconciled at the source [SF-14 · INTRODUCED · P1 · dep L1; implements Ruling 1]

1. **Reconcile the in-flight upstream edit first**: `~/projects/adcp-req` has an
   uncommitted modification to `tests/features/BR-UC-019-query-media-buys.feature`
   — inspect and integrate or stash before editing (§7 uncertainty 1).
2. Apply the R-1 table upstream in `~/projects/adcp-req`: delete the
   `revision absent` row (`:719`) and `confirmed_at_not_iso8601` row (`:784`);
   rewrite INV-11 (`:533`) to the enforced obligation (unknown persisted value
   refused at the write boundary; if one reaches the read path, the buyer receives
   `CONFIGURATION_ERROR`/terminal — R-M2); replace `SCHEMA_VIOLATION` on the
   reachable defective-revision rows (`:717-718`) with the CONFIGURATION_ERROR
   refusal contract. Commit and push upstream; record the new sha.
3. Re-run `python scripts/compile_bdd.py --merge` locally. The regenerated
   `BR-UC-019` must not re-add any of the four rows; the three "Reconcile upstream
   in adcp-req" prose notes are deleted (their premise-impossible *reasoning*
   stays as ordinary retirement rationale where it documents a decision — the
   "reconcile upstream" instruction goes).
4. Restore the traceability row: `docs/test-obligations/bdd-traceability.yaml`
   regains a mapping for the rewritten INV-11 scenario id, wired by L6 step 4's
   grader — the obligation has a home again.
5. Contingency only (owner rejects an upstream edit): the `RETIRED_UPSTREAM_IDS`
   tombstone + guard from R-1(c). Not the plan of record.
- **Graded by:** `python scripts/compile_bdd.py --verify` clean after the merge;
  the rewritten INV-11 scenario executing (a2a+mcp) via L1+L6; the restored
  traceability row visible to the obligation-coverage guard.
- **Red/green:** re-add one deleted row upstream and re-merge → the compiled file
  diff shows the re-add (proving the merge round-trip is the real check, not the
  prose).
- **Done-when:** `grep -c "Reconcile upstream in adcp-req"
  tests/bdd/features/BR-UC-019-query-media-buys.feature` → 0; `--merge` is a no-op
  w.r.t. the four rows; `bdd-traceability.yaml` carries the INV-11 successor row;
  upstream commit sha recorded in the PR description.

### L10 — one citable home per rule: the prose sweep [SF-11, SF-4 · INTRODUCED · P2 · after L1]

1. Sweep the seven `MEDIA_BUY_UNCONFIRMED_STATUSES` citations (symbol does not
   exist; polarity inverted) onto `is_media_buy_seller_confirmed` /
   `_SELLER_COMMITTED_STATUSES` with corrected polarity:
   `alembic/versions/2c4e6a7b8d9e_...py:6`, `alembic/versions/7f3a1c9e2b04_...py:21`,
   `tests/integration/test_confirmed_at_backfill_migration.py:51`,
   `test_media_buy_status_scheduler.py:250`,
   `test_update_media_buy_creative_assignment.py:783`,
   `test_admin_media_buy_reject_webhook.py:369`,
   `tests/admin/test_workflows_blueprint.py:324`. (The executable polarity fix is
   L1 step 5 — this is the prose.)
2. Delete `REST_ENDPOINT = "/api/v1/media-buys/query"` + `_build_list_rest_body` +
   `_parse_list_rest_response` from `tests/harness/media_buy_list.py:72-94` — the
   route does not exist (`grep -rn "media-buys/query" src/` → 0); the sibling env's
   declared refusal (`media_buy_create_list.py:93-110`) covers both.
3. Qualify the bare schema ref at `BR-UC-019-query-media-buys.feature:1335` to
   `media-buy/get-media-buys-response.json` (the convention this diff introduced at
   `:51`). NOTE: coordinate with L9's regeneration — apply in the adcp-req source if
   the line originates there, else locally after the merge.
4. Fix the two dead citations: `tests/bdd/steps/generic/then_schema.py:20`
   (`then_envelope_status_completed` → `then_envelope_status`);
   `test_architecture_bdd_no_shadowed_steps.py`'s `beads: salesagent-g4cm` → the
   resolvable GitHub number (or delete the provenance line) — the only beads id in
   the src/tests diff, against the PR's own rule.
5. Restate `tests/integration/test_admin_media_buy_reject_webhook.py:402-404` in
   the present tense — the docstring argues "+1" against its own (correct) `+2`
   assertion at `:420`.
6. SF-4: `tests/unit/test_architecture_schema_inheritance.py:280-282` — "all three
   narrowings", one-line reason each for `packages`/`media_buys` (Pattern #4 local
   item subclasses), and state 24 or derive the count in the message.
- **Graded by:** prose has no runtime grader; the done-when is the machine check.
- **Done-when:** `git grep -n MEDIA_BUY_UNCONFIRMED_STATUSES` → 0;
  `git grep -n "media-buys/query" tests/` → 0;
  `grep -n "schema-valid against" BR-UC-019...feature` shows both lines qualified;
  `git grep -n then_envelope_status_completed` → 0;
  `git diff main...HEAD -- src tests | grep -E 'salesagent-[a-z0-9]{4}'` → 0;
  the KNOWN_OVERRIDES comment matches its three entries and the measured 24.

### L11 — one bookkeeping oracle, one session-binding path [SF-12, SF-3 ↩R1-20 · INTRODUCED · P2]

1. Create `tests/helpers/media_buy_write_seam.py`: `MediaBuyState` NamedTuple;
   `read_media_buy_state(tenant_id, media_buy_id, *, session=None)` owning the
   expire/refresh decision; `assert_status_move_carried_bookkeeping(before, after,
   *, expected_status, bumps=1, confirms=...)` carrying the messages ("a status
   move must bump revision by exactly 1" — today verbatim ×6).
2. Convert the six sites: `test_media_buy_status_scheduler.py:173,181,246-254,637-644`;
   `test_update_media_buy_creative_assignment.py:789,797,886-895`;
   `test_admin_media_buy_reject_webhook.py:198,386-392,421-427` (deletes the raw
   `SASession(bind=get_engine())` in a test body — against tests/CLAUDE.md);
   `tests/admin/test_workflows_blueprint.py:269,320-330,355-365`;
   `tests/admin/test_creatives_blueprint.py:468-480`. Delete `_MediaBuyState`,
   `_BuyState`, `_read_buy_state`, `_media_buy_state`, `_reload_media_buy`.
3. SF-3: `tests/integration/test_order_approval_background.py:71-82` — make
   `approval_env` depend on `bound_factory_session` (it already takes
   `integration_db`, so ordering holds); delete the bind-then-`None` loop the new
   fixture's own docstring calls wrong.
4. Fix `test_factory_session_binding.py:3`'s docstring: cite the public
   `bind_factories_to_session` (not the pre-rename `_bind_...`) and name both
   replaced sites.
- **Graded by:** the six converted tests staying green (they grade the write doors);
  `test_factory_session_binding.py` (grades the fixture's save/restore contract).
- **Red/green:** in the shared oracle, change `bumps=1` handling to accept any
  positive delta → every converted site's exact-bump assertion must still redden on
  a double-bump (verify by mutating one write door to bump twice).
- **Done-when:** `grep -rn "must bump revision by exactly 1" tests/` → 1 (the
  helper); `grep -rn "class _MediaBuyState\|class _BuyState\|def _read_buy_state\|def _media_buy_state\|def _reload_media_buy" tests/` → 0;
  `git grep -n "_meta.sqlalchemy_session" tests/integration/test_order_approval_background.py` → 0;
  `git grep -n "SASession(bind=get_engine())" tests/integration/` → 0 in the
  converted file; `git grep -n "_bind_factories_to_session" tests/` → 0.

### L12 — the guard reads Gherkin through pytest-bdd's own parser [SF-13 · INTRODUCED · P2]

1. Replace `_feature_step_lines()`'s hand-rolled lexer
   (`tests/unit/test_architecture_bdd_no_shadowed_steps.py:184-230` — `_STEP_RE`,
   `_STEP_KEYWORDS`, `_CONTINUATION_KEYWORDS`, `_BLOCK_KEYWORDS`, docstring toggle)
   with `from pytest_bdd.feature import get_feature` (the repo convention:
   `test_architecture_bdd_feature_parse.py:27`), reading each step's type, name and
   line from the parse production actually resolves against. Keep only the
   outline-placeholder filter as guard-specific logic.
2. Keep the guard's rule and scope untouched (owner ruling A5 — do not widen); keep
   the non-vacuity asserts and extend them: the `get_feature`-derived step count
   must match the count pytest-bdd collects for one known feature (closing the
   partial-under-read hole the counts-nonzero asserts cannot see).
- **Graded by:** the guard's own non-vacuity asserts (parser count, line count,
  matched count nonzero + the new known-feature count pin); the UC-005 collision
  regression (re-register the deleted step → guard names collision, file, line —
  already mutation-verified in round 2, must survive the rewrite).
- **Red/green:** re-register the deleted UC-005 exact-text step → guard reddens
  naming it.
- **Done-when:** `grep -n "_STEP_RE\|_STEP_KEYWORDS" tests/unit/test_architecture_bdd_no_shadowed_steps.py`
  → 0; guard green with empty allowlist; the mutation check passes.

### L13 — reconciliation gate (last)

1. Re-run every command in the round-3 verification log (`full-findings.md`
   § Verification log) and record the after-values — each must show the fixed
   state.
2. Re-verify deferral homes: `gh issue view 1998 1999 2000 --json state,assignees`
   → all OPEN + assigned (or closed by this work).
3. `make quality` + `uv run python .pre-commit-hooks/check_type_ignore_count.py`
   (63, exit 0) + `pre-commit run --all-files`.
4. Affected BDD modules serial on the box, then `./run_all_tests.sh` — zero
   failures, zero new xfails; BDD pass/xfail deltas recorded before/after (the
   graduations in L6/L8/L9 must appear as +passed/−xfailed, nothing else moves).
5. Update the PR description: the honest claim (§0), the upstream adcp-req sha
   (L9), the U-3 REST-surface note, the `health: "ok"` wire-shape note.
- **Done-when:** every lane's own done-when re-checked green; the ledger in §6 has
  no unchecked row.

---

## §6 Non-negotiable ledger

### 6.1 Every behavior this remediation changes, and what grades it

| Behavior | Grader (transports) |
|---|---|
| Unmapped persisted status → typed `CONFIGURATION_ERROR`/terminal instead of bare `ValueError`→`VALIDATION_ERROR` | Rewritten INV-11 scenario (a2a, mcp) via `assert_wire_error`; write-boundary integration test; L1 red/green |
| Backfill predicate: unknown legacy status is NOT backfilled as committed | Authored migration polarity test (L1); real upgrade→downgrade→upgrade run |
| Out-of-vocabulary legacy rows normalised (or migration aborts loudly) | Authored normalising-migration test (L1) |
| Creative-path approval past flight end → `completed`, not committed-`active` | Authored integration case (L2) |
| Create response reports the persisted `confirmed_at`/`revision` | Producer-agreement create arm (integration, a2a/mcp) + woken `@T-UC-002-v31-success-revision-and-actions` (a2a/mcp/rest) (L4/L6) |
| `update_media_buy` not-found path restores message+suggestion+context | Existing not-found graders + producer-agreement vanished-row cases, now incl. REST (L4/L6) |
| Null `confirmed_at` reaches the wire as an explicit `null` key | Authored null-confirmed Examples row (a2a, mcp) (L5) |
| `update_media_buy` persisted-revision response | Woken `@T-UC-003-revision-success-increments` + family, 3 in-process transports (L6) |
| Defective-revision refusal carries `CONFIGURATION_ERROR` | Restored BR-RULE-291 rows via `assert_wire_error` (a2a, mcp) (L6/L9) |
| `status` survives `model_dump()` on `oneOf` envelope models | `test_declared_fields_exist_in_schema` populate-dump-survive + standing declared-fields assertion (L7) |
| UC-005 storyboard roundtrip graded again | 3 parametrizations plain PASS (a2a/mcp/rest) + pixel_tracker mutation check (L8) |

### 6.2 Every duplication, and the abstraction that collapses it

| Duplication | Collapsed by |
|---|---|
| Status coercion ×3 (three failure policies) + dead duplicate predicate | `PersistedMediaBuyStatus.parse()` + typed seam (L1) |
| Transition decision ×3 (two in admin routes) | One domain function (L2) |
| Projection with two import homes (definition + re-export shim) | One home in `_media_buy_status.py` (L3) |
| `confirmed_at`/`revision` producers ×2 (model defaults beside columns) | Row-bound construction, defaults deleted (L4) |
| Lookup-or-raise ×2 (`_buy_and_revision_or_raise` vs `get_by_id_or_raise`) | Repository seam only (L4) |
| Always-include re-insert ×3 (2 mixin + 1 hand-rolled) | Wrap-serializer mixin with conditional seat (L5) |
| Guarded wire reader ×3 (+1 partial) | `TransportResult.require_wire()` + delegating `wire_dict`/`wire_field` (L6) |
| Success-shape resolver ×2 | `_success_shape()` (L7) |
| Gherkin lexer ×3 | `pytest_bdd.feature.get_feature` (L12; `scripts/compile_bdd.py`'s copy is upstream tooling, out of scope) |
| Write-seam oracle ×6 / state readers ×4 / identical NamedTuples ×2 | `tests/helpers/media_buy_write_seam.py` (L11) |
| Factory-session bind (1 new copy beside the fixture) | `bound_factory_session` (L11); the 5 pre-existing copies → U-1, routed |

Ratchets after this plan: type-ignore 64→63 (red→green); `_UC005_PARTIAL_TAGS` −1;
zero new allowlist entries anywhere; `KNOWN_OVERRIDES` count unchanged (entries
ruled genuine in R1 — only the comment corrects).

---

## §7 Right — do not touch

- The **write seam itself**: `MediaBuyRepository` ownership of
  `confirmed_at`/`revision`, `_stamp_confirmation_if_needed`,
  `test_architecture_media_buy_write_seam.py` with zero allowlist. The design is
  correct; L1/L4 finish routing onto it.
- **`GetMediaBuysResponse` re-based on the library envelope**;
  `CompletedTaskStatusMixin` with the biconditional pin;
  `GetMediaBuysResponse` staying OUT of the mixin.
- The deletion of `_PROTOCOL_ENVELOPE_FIELDS` and its tripwire; the sample
  generator's located refusal.
- `wire_dict`/`wire_field` guarded readers and the global registration of the
  schema-valid step; `MediaBuyListEnv` dispatching MCP through `_run_mcp_client`.
- The **match-overlap shadow guard's rule and scope** (owner ruling A5) and its
  empty allowlist — L12 changes only how it reads the corpus.
- `_NO_REST_UC_TAG_PREFIXES = ("T-UC-019-",)` — the honest encoding of the
  pre-existing REST surface fact.
- The backfill migration's **existence** and its freeze-not-import decision — only
  the predicate polarity flips (L1).
- The **two premise-impossible retirements' reasoning** (`revision absent`,
  `confirmed_at_not_iso8601`) — correct; only the mechanism changes (L9 fixes them
  at the source).
- `KNOWN_OVERRIDES` entries themselves (R1 ruled them genuine Pattern #4
  narrowings) and the MRO collector + `assert_violations_match_allowlist`.
- `GetMediaBuysResponse.__str__` and the A2A message grading (round-2 L8).
- `health: "ok"` on items (spec-legal, R1-15 ruled — describe in the PR
  description, change nothing).
- The `alembic/env.py` `disable_existing_loggers=False` fix and the
  `run_all_tests.sh` permission/`errexit` fixes.
- The UC-005 weak-step deletion (the trigger of SF-8 was correct; only the routing
  was wrong).

---

## §8 Uncertainties and what settles them

1. **The uncommitted adcp-req edit.** `~/projects/adcp-req` shows
   ` M tests/features/BR-UC-019-query-media-buys.feature` at planning time. What is
   in it, and does it collide with L9's edits? *Settled by:* `git diff` in that repo
   before L9 step 2; integrate or stash, owner call if it is substantive.
2. **Waking the UC-003/UC-002 families may surface real failures** (19+12
   parametrizations that have never executed). *Settled by:* running them; per the
   test-integrity policy each red is fixed or reported as a blocker — never
   xfailed. Budget L6 as the largest lane for this reason.
3. **Can `refresh-reference-formats.py` produce a pin-valid catalog?** The
   `pixel_tracker` entries are tracker-URL requirements the declaration union may
   genuinely not express. *Settled by:* running the script against the pin (L8 step
   1); if not expressible, the narrowing path is taken (R-M3) and #1998 carries the
   catalog.
4. **Normalising migration vs `TypeDecorator`** (L1 step 4): the migration is the
   plan of record (owner ruling A1's principle); the `TypeDecorator` is optional
   hardening. *Settled by:* if the survey in step 4 finds zero out-of-vocabulary
   rows in every environment, the migration is a no-op guard and the decorator can
   be a follow-up — decide at implementation, record in the migration docstring.
5. **Is the scheduler's creative-approval precondition the universal transition
   rule** for both admin paths (L2)? The scheduler's `_compute_new_status` is the
   most complete of the three, but the admin operations route also returns `draft`,
   which the scheduler never does. *Settled by:* owner confirmation of the unified
   function's answer set before L2 lands; the authored past-end-date test encodes
   whichever ruling.
6. **R-M1/R-M2 stand until the owner confirms** (stated overturn conditions in §1).

---

## §9 Beads epic (filed)

Epic **`salesagent-09ke0`** — one child per lane (root cause), two routing
children for the UNCOVERED items, dependencies wired
(`L2/L3/L9/L6/L10 ← L1`, `L6 ← L4+L9`, `L10 ← L9`, `L13 ← all lanes`):

| Bead | Lane | Priority |
|---|---|---|
| `salesagent-09ke0.1` | L1 vocabulary as type + migration polarity | P0 |
| `salesagent-09ke0.5` | L5 wrap-serializer mixin, ratchet → 63 | P0 |
| `salesagent-09ke0.8` | L8 UC-005 fixture, xfail entry out | P0 |
| `salesagent-09ke0.2` | L2 transition-decision owner | P1 |
| `salesagent-09ke0.4` | L4 create arm reads the row | P1 |
| `salesagent-09ke0.6` | L6 wire-grading wiring finished | P1 |
| `salesagent-09ke0.7` | L7 one success-shape resolver | P1 |
| `salesagent-09ke0.9` | L9 adcp-req reconciliation (Ruling 1) | P1 |
| `salesagent-09ke0.13` | L13 reconciliation gate | P1 |
| `salesagent-09ke0.3` | L3 projection back to presentation | P2 |
| `salesagent-09ke0.10` | L10 prose sweep | P2 |
| `salesagent-09ke0.11` | L11 shared oracle + session binding | P2 |
| `salesagent-09ke0.12` | L12 guard on pytest-bdd's parser | P2 |
| `salesagent-09ke0.14` | U-1 factory-bind sweep (UNCOVERED, routed) | P3 |
| `salesagent-09ke0.15` | U-2 UC-018 model_dump graders (UNCOVERED, routed) | P3 |

---

## §10 Audit lessons (post-remediation, from the independent audit)

### 10.1 L10 ↔ L12 coupling: the shadowed-steps guard is corpus-driven

`tests/unit/test_architecture_bdd_no_shadowed_steps.py::test_no_domain_exact_text_shadows_generic_parser`
fires only when an exact-text step in a domain module shadows a generic parser
**for a sentence that currently appears in a feature file**. The scan pairs
registered parsers against `_feature_step_lines()`; a sentence absent from the
corpus produces no line to match, so no overlap, so no failure.

That makes its blast radius a function of the corpus, and L10 changed the
corpus. L10 step 3 qualified the bare schema references, so
`"the response should be schema-valid against list-creative-formats-response.json"`
— the exact sentence the deleted UC-005 shadow step registered — no longer
exists anywhere. It is now
`"...against media-buy/list-creative-formats-response.json"`
(`tests/bdd/features/BR-UC-005-discover-creative-formats.feature:1071`).

**The lesson, which cost a wrong result to learn:** the audit's first attempt at
L12's mutation re-registered the *historical* sentence, and the guard stayed
GREEN. That looks like a dead guard and is not one — the mutation was simply
unreachable. Retargeted to the sentence actually in the corpus, the guard failed
immediately and named the collision, the offending module, the generic module it
shadows, and the feature file and line.

So: **a mutation test against this guard MUST target a sentence currently in the
feature corpus, or it proves nothing.** A green result from a corpus-absent
mutation is evidence about the mutation, not about the guard. The same caution
applies to any future rewording of feature prose — rewording a sentence silently
narrows what this guard can see, and nothing reports that.

### 10.2 `compile_bdd.py --verify` cannot grade merge-mode output

Documented at `scripts/compile_bdd.py::verify_features`. Measured behaviour:
the sha check returns before any file is compared, and past it `_render_feature`
re-renders without the merge, so all 31 merge-mode files compare unequal. The
real check is `--merge` for the one UC followed by a diff.

Two precisions for whoever uses that check:

* A no-op merge leaves the generation stamp **and incidental blank-line
  differences** — the measured no-op on `BR-UC-019` was the stamp plus two
  whitespace-only lines. Do not read a blank-line diff as a divergence.
* `--verify`'s own failure message still prints
  `Re-run: python scripts/compile_bdd.py --all`, which is the trap the docstring
  warns about (`--all` routes to `compile_features`, not `merge_features`, so the
  `LEGACY-PRESERVE` branch never runs and every `@hand-edited` scenario is
  discarded). The docstring is on the function; the operator sees the message.
  Fixing the printed suggestion is the follow-up.

### 10.3 A cassini wid is ambiguous across two roots — `status` can report the wrong one

`cassini test` and `cassini run` do NOT share a workspace. They are two roots on
the box:

* `cassini/main.py:88` — `BASE = "/srv/sa-tests"` (slices)
* `cassini/model.py:57` — `RUN_ROOT = "/srv/sa-runs"` (full runs)

Distinct directories, distinct inodes. A slice run during a full run does NOT
overwrite that run's source tree, and mutation-based red/green checks do not need
to be serialized against a full run for that reason.

**The real footgun is the reader.** `cassini wid` is a pure function of the
worktree PATH, so a slice and a full run launched from one worktree carry the
SAME wid while writing under different roots. `cassini status <id>` resolves the
wid and follows the run's `workdir` — and among candidates it can hand the
worktree's identity to whichever started LAST. So a slice can displace the full
run in the report, and `status` then reads the other root's manifest.

This is a known, already-diagnosed class in cassini, not a new discovery:
`cassini/main.py:694-706` records it verbatim — *"a subagent's slice displaced a
full run that had been in flight for 23 minutes: `status` followed
`run.workdir` to /srv/sa-tests, read the other root's manifest, and the
baseline's exit code and suite totals were never reported at all."* There is a
regression test at `tests/test_model.py:1682` (`TestStatusAsksTheRunWhereItRan`).

The tie-break added for it applies **only among RUNNING full runs**, and that
narrowness is CORRECT, not a gap — `cassini/main.py:709-713` rejects the broad
form explicitly: preferring `Kind.RUN` outright would mean a worktree holding a
FINISHED run and a LIVE slice reports the finished run's exit code while the
slice is what is actually happening (`cassini-03k.16`'s shape, a false green).
"Make finished runs win too" is a known-bad fix. Do not propose it.

What happened here sits outside that tie-break by design: the full run had
FINISHED, the later slice won the resolution, and `status` reported
`/srv/sa-tests/<wid>` — a directory where no full run has ever written a report —
showing the previous day's totals under a STALE banner. Note also that
`TestStatusAsksTheRunWhereItRan` covers the MIRROR direction (status reading
`/srv/sa-runs` when the answer was in `/srv/sa-tests`); this was the other way
round.

**The defect is in the REPORT, not the resolution.** `status` named the directory
correctly; nothing said which ROOT or KIND that directory belonged to, so a reader
cannot tell they have crossed namespaces. One line in the banner — "slice
workspace; full-run reports live in /srv/sa-runs/<wid>/test-results/" — would
have prevented both this and the documented 23-minute incident, without touching
the tie-break or risking a false green. That is the fix worth proposing.

**How not to be fooled by it:** the banner names the directory it is describing.
Read that path. If it says `/srv/sa-tests/...` you are looking at the slice
namespace, and it can tell you nothing about a full run. Before concluding a full
run produced no report, check `/srv/sa-runs/<wid>/test-results/` on the box. The
cheap disconfirming check is one `ls`; the expensive alternative is re-running a
28-minute suite.

#### Second dated instance — 2026-08-20, admin suite

Same class, opposite root, and worth recording because one witness is folklore.

`cassini run --detach admin` (supervisor `sa-abd78d70-supervisor-1685ebfb`).
Both `cassini status sa-abd78d70` and `cassini fetch sa-abd78d70` then reported:

```
run    : 1685ebfb1dcf4cd6971b839042124900
state  : finished, exit=0
  targeted   113p 3xf 24s  (140 total)  ⚠ STALE — this suite did NOT run in this invocation
  results → test-results/200826_1430/
```

Two things make this the sharp version of the failure:

* The **run id matched** the supervisor cassini itself printed at launch, so the
  usual "you are looking at someone else's run" tell was absent.
* `test-results/200826_1430/` is the LOCAL `./run_all_tests.sh ci tests/e2e/`
  run from earlier the same afternoon — a different root, a different suite, and
  a different runner entirely.

The composite reads as a green admin run: correct id, `exit=0`, a plausible
suite line. The only contradiction is the `⚠ STALE` marker at the END of that
line, past where most readers stop, and the suite NAME — `targeted`, when
`admin` was requested.

The real result was recovered by opening `test-results/innet_200826_1255/admin.json`
directly: 91 passed, 3 xfailed, exit 0, and both new node ids present by name
with `passed` outcomes.

**Working rule for the rest of this epic:** read the per-suite JSON, never the
`status` summary. Check the suite NAME matches what you asked for before reading
any number next to it. `exit=0` is trustworthy (it comes from the box's own
`.sa-run.exit`); the suite totals printed beside it are not.

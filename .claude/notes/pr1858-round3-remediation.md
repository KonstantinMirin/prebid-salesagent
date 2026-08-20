# PR #1858 round 3 plan: scope authority for the structural-change molecule

This note is the `PLAN_DOC` for the `structural-change` formula cooked over
`salesagent-grdgc`. The `baseline` atom records its SHA. The
`solution-review` atom grades each step's design against the section here that
names that step, and returns ESCALATE when this note under-specifies the step.

Round 3 triages ChrisHuie's review of PR #1858 at head `ee8f1ba5f`: 2 BLOCKER,
21 SHOULD-FIX, and 9 NIT findings. Four of the epic's eight children remain
open. This note covers those four.

## Why this molecule uses structural-change, not plan-lane-execute

None of the four open steps changes behavior on this branch. `plan-lane-execute`
opens each step with `write-test`, and a test author facing a step with no
behavior delta has nothing to assert. The author asserts a structural property
instead, the `test-verify` atom grades that assertion, and the guard corpus
grows past the thing it guards. Both atoms work correctly; the step is the wrong
input for them.

`structural-change` replaces that pair. The `predict` atom records a command,
the value it prints now, and the value it prints after. The
`verify-prediction` atom runs the command and compares. Every step also
declares a deletion list, and the `finalize` atom requires net lines under
`tests/` to be at most zero.

## The triage lens

The pinned `adcp` SDK's own Pydantic models are the typed carrier for request
and response data, with real validation. Hand-rolled dict-merging, raw-value
fallbacks, and bespoke Python-level static analysis are not. BDD scenarios on
the real wire grade behavioral correctness across MCP, A2A, and REST. Internal
guards that re-derive what the SDK already guarantees do not. A guard whose job
is to assert something about how you use an SDK class is a symptom of the wrong
architecture.

The lens carries one stated exception, which the LEDGER verdict formalizes:
harness and measurement internals have no wire manifestation of their own, so
guard-level grading is the correct layer for them. Such a guard asserts
artifact and ledger agreement, never an SDK shape.

## Step order

Cook the steps in this order. `structural-change` sets
`depends_on_prev_barrier`, so each step's design atom waits for the previous
step's commit.

1. `salesagent-grdgc.8` — the revert shrinks the surface every later step
   measures against.
2. `salesagent-grdgc.4` — the measurement pipeline must grade itself before you
   trust any later measurement.
3. `salesagent-grdgc.5` — harness integrity.
4. `salesagent-grdgc.7` — the citation sweep runs last, over the files that
   survive.

Steps 3 and 4 both edit `tests/unit/test_architecture_harness_single_dispatch.py`.
Step 3 extends it to the unwrap layer; step 4 removes the gitignored-path
citation at line 4. Order resolves the collision.

## Step 1: salesagent-grdgc.8, narrow #1858 to measurement-only

**Core invariant.** PR #1858 measures and exposes; it does not change behavior.
The only production change it owns is what #1512 requires: tolerate the
version-envelope fields at the seam so capability discovery works.

**Boundary.** Round 2's Lane A built a request-disposition system to fix a real
regression, in which the seam accepted `canceled` and then dropped it silently.
That work is legitimate and it is a behavior change, so it moves to
`fix/1858-field-disposition` as its own PR. This step is the revert on #1858's
side. Keep every Lane B through F deliverable: `AdCPTestClient`, storyboard
wire-grading, the known-gap ledger mechanism, the measurement pipeline's
self-verification, and the tests and scripts contract module. None of those
touches production behavior.

**Deletion list.**

- The `schema_fields | set(model.model_fields)` union in
  `src/core/version_compat.py`, narrowing `accepts_spec_request_fields` back to
  `SPEC_ENVELOPE_FIELDS` only.
- Every `*UNSUPPORTED*_FIELDS` map and every `refuse_unsupported_fields` call
  site added this round.
- `tests/harness/spec_field_consumption.py`,
  `tests/unit/test_architecture_spec_field_disposition.py`, and
  `UNDISPOSED_LEDGER`, with no replacement.
- The `canceled`-honoring code in `media_buy_update.py`, and the
  `idempotency_key`-honoring code in `creatives/_sync.py`.

**Owner decision on the idempotency seam.** The plan first said to revert "the
`idempotency_seam` migration". No such alembic migration exists; this branch
adds no file under `alembic/versions/`. The only referent is the module
`src/core/idempotency_seam.py`, and deleting it removes behavior that main
already has. Measured at the merged head: `origin/main` does not contain the
module, and main's `media_buy_create.py` carries the create_media_buy
idempotency inline, with 80 `idempotenc*` references and 7 `payload_hash`
references. This branch extracted that logic into the module, which
`media_buy_create.py:130-136` imports and calls at `:1692`, `:1714`, `:1786`,
`:1819`, and `:1878`.

**Keep `src/core/idempotency_seam.py`.** A behavior-neutral extraction of
main-existing logic changes no behavior, so the step's core invariant holds. The
step reverts only the Lane A behavior layered on top of it: the
`idempotency_key` honoring in `creatives/_sync.py`. The honor path continues on
`fix/1858-field-disposition`. Un-extracting the module back into
`media_buy_create.py` would re-duplicate logic that the DRY invariant in
`CLAUDE.md` treats as a defect.

**Additional consumers the deletion list must cover.** Deleting
`tests/harness/spec_field_consumption.py` leaves three imports unbuildable:

- `tests/integration/test_spec_request_fields_accepted.py:42` imports
  `UNDISPOSED_LEDGER`, `spec_tool_names`, and `undisposed_fields`. The file is
  new this round, so delete it.
- `tests/unit/test_mcp_tool_schemas.py:138` imports `published_input_fields`.
  This file exists on main and main's copy does not reference the harness
  module, so revert the import rather than deleting the file.
- `src/core/tools/media_buy_create.py:130-136` imports the five seam functions.
  Keeping the module resolves this one.

**Stale docstring references to correct**, all prose rather than imports:
`src/core/version_compat.py:425`, `src/core/spec_request_carrier.py:107`,
`src/core/transport_helpers.py:171`, and
`src/core/tools/media_buy_update.py:1627`.

**Inexpressibility.** After this step, the seam has one acceptance rule, so no
call site can express a second disposition policy.

**Measurement.** A `git diff` against the pre-Lane-A state is the source of
truth, not memory. Confirm that #1512 still closes, meaning the storyboard
runner's capability probe is no longer rejected, and that Lanes B through F
still pass.

**File, do not fix.** Every behavior gap the revert re-exposes becomes a GitHub
issue on `prebid/salesagent`, citing the file, the line, and the execution
traces this round already gathered. Search for duplicates first: #1983, #2018,
#2020, and #2026 cover adjacent ground.

## Step 2: salesagent-grdgc.4, make the measurement pipeline grade itself in CI

**Core invariant.** Every published conformance artifact is either regenerated
and verified by a guard that runs in CI, or it does not exist in the repo. "Not
measured" and "measured false" are never the same output.

**Root cause.** The artifact-grading guards root in a machine-local clone path,
`ADCP_HOME=~/projects/adcp`, and in prose. In CI, nothing grades the
deliverables, so the committed numbers drift silently.

**Change-set.**

- B1: point the 23 skipped artifact-truth guards at a CI-provided spec root,
  which is the tarball the storyboard job already extracts at `ci.yml:414-419`.
- B2: fix the `run_cli` short-circuit at
  `scripts/audit/storyboard_spec.py:795-799`, which emits only the JSONL on the
  published `--jsonl --markdown` flag pair. Regenerate all three artifacts, and
  add the offline ledger-to-artifact freshness guard.
- B3: fix the liveness join, which emits for 1135 records the exact output that
  `test_architecture_storyboard_check_index_liveness.py:59` defines for a
  missing artifact. Make the guard fail on the all-false shape when a liveness
  artifact exists.
- B6: add the reverse-direction assertion that every index entry is visited,
  plus `storyboard_count == len(storyboards)`.
- C6: root the storyboard version chain in the installed wheel, exactly as
  `test_pinned_schema_single_source.py:95` already does for the schema chain.
  `pinned_version()` regex-parses prose and is the sole version source for more
  than eight call sites.
- C1: correct the two wrong descriptions of the graduation mechanism, at
  `known_failures.txt:7` and `tests/storyboard/conftest.py:36`, to name the
  in-session fitness join at `test_storyboard_conformance.py:339-365`.
- F10: deduplicate `test_same_key_different_payload_conflicts`, and remove the
  set-emptiness skip at
  `test_architecture_storyboard_check_index_liveness.py:197`.

**Deletion list.**

- `tests/storyboard/runner/results/*.json`, all six captures, totaling 1.7MB.
  Deleting them leaves the suite byte-identical, and it removes `sb1d-full.json`,
  which at 1179KB exceeds the 1000KB pre-commit ceiling.
- The hand count at `ci.yml:377`, "IS seeded — 44 entries", which reads 75 and
  drifts by construction. Replace it with a non-numeric statement pointing at
  `known_failures.txt`, keeping the report-only disclosure.
- The hand-edited "drops from 80 checks to 48" at
  `storyboard-issue-map.yaml:101`, which the B2 regeneration refreshes.

**Correct-design fix.** One spec-root resolution serves both guards and
generators: CI provides the extracted tarball path, and `ADCP_HOME` remains a
local convenience. One version root: the installed wheel. One freshness guard
joins ledger to artifacts and needs neither.

**Inexpressibility.** After this step, no artifact can disagree with its
declared inputs while CI stays green, and no version claim can move without the
wheel moving.

**Measurement.** In CI at the resolved head, the skip count for
`requires_clone` in the storyboard job is 0, down from 23. The freshness guard
reddens when `known_failures.txt` changes without regeneration. The liveness
guard reddens on the all-false-with-artifact-present shape. A doc-only version
mutation reddens.

## Step 3: salesagent-grdgc.5, wire-grading integrity

**Core invariant.** The harness holds exactly one implementation of wire capture
and unwrap, and exactly one accessor family for reading it in steps. The set of
scenarios wired to the real wire can only grow.

**Change-set, and its verdicts under the LEDGER exception.**

- D3, expect PROCEED. `A2ADispatcher` and `McpDispatcher` build `TransportResult`
  inline at `dispatchers.py:93-97` and `:147-151`, with an unparsed payload and a
  hardcoded transport tag, while `_unwrap_tool_success` at `client.py:548-552`
  claims to be the unwrap for every tool-style transport. Two live producers
  exist, so zeroing either reddens a disjoint set. Both success paths delegate
  to the shared unwrap, and
  `test_architecture_harness_single_dispatch.py` extends from the deliver layer
  to the unwrap layer, which makes a third producer impossible.
- D2, expect PROCEED. The guarded wire accessors reach 3 of 5 eligible sites.
  The guard matches `wire_error_envelope` only and scans only
  `tests/bdd/steps`, so `test_uc018_list_creatives.py` and its 16 step
  definitions are invisible. Fix the scope: match `wire_response` too, and scan
  every module that defines steps. Migrate the two byte-equivalent twins the
  widened guard reddens, at `uc003_update_media_buy.py:1151` and
  `test_uc018_list_creatives.py:355`. Correct `_wire_creatives`' docstring,
  whose claimed production-serializer fallback the guard makes false. This step
  widens an existing guard's scope and deletes duplication; it adds no guard.
- D1, expect LEDGER. Deleting one `ENV_ROUTES` row at
  `tests/bdd/conftest.py:3465-3470` took `test_uc002_account_access.py` from 6
  passed to 6 xfailed with every agreement guard green, because both sides read
  the same registry. Add a shrink-only ratchet on the wired set, beside the
  agreement guard. The design must satisfy all four LEDGER conditions, and
  condition 2 requires naming what you would derive the wired set from and why
  the derivation fails. A derivable wired set earns DEEPEN instead, because
  deriving it from the scenario registry makes row deletion inexpressible.
  Current sizes: 499 wired, 426 registered and not wired, and 75 unclaimed, of
  1000.

**Deletion list.**

- `_base.py:1043`, the `call_rest` method, which has zero callers and a
  docstring claiming a symmetry that delegation made false. Delete it, or route
  it through `_deliver_via_client` like its siblings and fix the docstring.
- The six lazy imports in `dispatchers.py` that outlived the import cycle that
  justified them. Hoist them to module level.
- The two byte-equivalent accessor twins that D2's widened guard reddens.
- The inline-xfail pattern taught by four docstrings in
  `uc006_storyboard_creative_sync.py`, at `:382`, `:399`, `:437`, and `:510`.
  Correct them to the ledger-tag mechanism, which this PR's own commit
  introduced.

**Inexpressibility.** After this step, no third `TransportResult` producer can
exist, and no step module can read a wire attribute outside the accessor family.

**Measurement.** Mutating either dispatcher's success path to bypass the shared
unwrap reddens. Any `wire_response` or `wire_error_envelope` attribute read
outside the accessor family, in any step-defining module, reddens. Removing any
currently wired scenario id from the wired set reddens.

**Cross-reference.** #1995 covers adjacent ground on the `uc018` module, which
predates this PR. The guard-scope hole belongs to this PR, and widening the
guard forces the small migration.

## Step 4: salesagent-grdgc.7, resolvable citations

**Core invariant.** Every citation in committed source resolves for an outside
contributor. `CLAUDE.md` already mandates this for allowlist FIXMEs, requiring a
GitHub issue or PR number and never a local beads id. This PR violated the rule
broadly, which makes the whole class self-inflicted regardless of affected area.

**Root cause.** One habit produced every finding: citing machine-local working
state in committed artifacts, including beads ids, `.claude/` paths, absolute
`/Users/konst` paths, and hand counts.

**Deletion list.**

- More than 100 committed references to beads ids that do not resolve in the
  repo's own `.beads/issues.jsonl`, including `salesagent-vuz9t.14`,
  `salesagent-g6m2.10`, `salesagent-syhj`, `salesagent-exbf`,
  `salesagent-qbac1.1`, and `cassini-w37`, which does not even carry this
  project's prefix. Sites include `.github/workflows/ci.yml`, the
  `tests/storyboard/runner/package.json` description,
  `tests/storyboard/conftest.py:7`, and
  `tests/unit/test_storyboard_ledger_state.py`. For each cited id, file or find
  the GitHub issue carrying its content and swap the citation. Remove a
  citation that is stale working narrative rather than a live obligation. The
  PR-description merge gate `salesagent-vuz9t.14` must become a GitHub issue.
- Citations of gitignored machine-local paths:
  `scripts/audit/storyboard_spec.py:12` cites
  `.claude/code-review/salesagent-pw71/`, excluded by `.gitignore:142`;
  `tests/integration/test_spec_request_fields_accepted.py:129` and
  `tests/unit/test_architecture_harness_single_dispatch.py:4` cite a per-PR
  working note. Remove each, or replace it with the durable artifact.
- The 91 added `/Users/konst` absolute paths across 56 `.claude/` files and
  27,393 added lines. Trim by scope, not blanket.
  `sb1b-baseline-report.md` is load-bearing, cited from
  `test_storyboard_conformance.py:24` and `tox.ini:187` as the reproduce
  procedure; keep it and de-absolutize its paths. Remove working notes that
  nothing committed cites.
- The person handle in the code comment at `adcp_a2a_server.py:2249`. Keep the
  issue number.

**Reconciliation.** The PR modifies the 8.65MB binary `.beads/beads.db` without
updating `.beads/issues.jsonl`. Run `bd sync` so the two agree, or drop the
database churn from the diff.

**Inexpressibility.** After this step, no committed file cites a path that
`.gitignore` excludes, and no committed file cites an identifier that resolves
only on one machine.

**Measurement.** `grep -rE 'salesagent-[a-z0-9]+.?[0-9]*|cassini-'` over
committed source, excluding `.beads/`, returns zero. The count of `/Users/konst`
occurrences outside the load-bearing report returns zero.

**Scope note.** The primary deliverable is the sweep plus the GitHub issues that
replace the beads citations. If you want a ratchet, extend the existing
FIXME-citation guard's pattern. Do not write a new guard.

## Orchestrator-direct items

These items carry no ticket. Handle them in the PR description or as one-line
edits.

- C2: the headline reads "196 covered" and "497 neither"; correct them to 184
  and 509.
- C3: section 4's "src/ is three files different" and "+133/−0" went stale after
  round 2. The measured figures are 31 files and +2487/−186, with
  `version_compat.py` at +520/−0. Correct the numbers or drop the containment
  argument.
- C4: "55 definitions collapsed to 2" does not reproduce. The reviewer counts 34
  to 6, plus 18 new `deliver_*` overrides. Restate it honestly.
- E3: state in section 1 that the Storyboard Conformance job is report-only.
- F1: retitle the PR to `fix:`. It closes #1512, a wire-contract change across
  all 16 MCP tools, and `test:` is absent from release-please's
  changelog-sections. The comment in `pr-title-check.yml` claiming its list
  matches the config is a pre-existing mismatch of a few lines; flag it, do not
  file it.
- F15: disclose the patched `@adcp/sdk` at
  `patches/@adcp+sdk+11.0.0.patch`, covering the webhook-receiver host default,
  and give its containment story.
- E1 and E2: the PR conflicts, and no `pull_request` workflow has run at this
  head. The conflict spans 2 files and 3 hunks: two trivial additive hunks in
  `tests/helpers/__init__.py`, and one in `tests/bdd/conftest.py`. Keep the
  registry, re-add main's six comment lines from `5cc0497d6`, and re-verify with
  step 3's wired-set probe at the resolved head.

## Flags for the orchestrator

- Step 1's revert moves the honor path to `fix/1858-field-disposition`. When
  that path lands, close #1975 and the covered part of #2018 rather than leaving
  stale trackers.
- The reviewer did not run the integration, e2e, BDD, or in-network suites at
  this head. The suite figures in the PR description stay uncorroborated until
  CI runs on a resolved head.

## Follow-up issues already filed

This triage filed #2029, covering the `_spec_request` adoption census across 5
modules and 8 sites, and #2030, covering obligation docs still framed at SDK
3.6. Confirmed and not re-filed: F6 is #1952, and F8 is #1929. Adjacent
trackers: #1983, #2020, #2026, #2027, #1975, #2018, #1947, #1995, #1593, #1353,
#1075, and #1683.

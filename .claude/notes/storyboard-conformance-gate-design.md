# Design: gate `storyboard-conformance` in CI when conformant enough

## Status: DESIGN ONLY — no gate wired by this note or its originating task

Beads: `salesagent-zs64m.4`, child of epic `salesagent-vuz9t` (PR #1858
remediation, review finding 4). This note is the entire deliverable of that
task — it records the future gate-work design and its precondition. It does
**not** wire `storyboard-conformance` into `summary.needs` or otherwise turn
the job merge-blocking. The epic's own review disposition on finding 4 is
explicit: introducing a CI gate now is out of scope — the project is not
close enough to compliance for a red build on this job to mean anything
other than permanent noise.

## The precondition for gating

A red `storyboard-conformance` build is only *signal* once the project is
near enough to full conformance that "did this PR regress the ledger" is a
meaningful question. That means: the measured genuine-gap ledger
(`tests/storyboard/known_failures.txt`) trending toward zero, not sitting at
a large, roughly-static count.

State at the time of writing, measured (not derived) from the checked-in
ledger:

- First real in-network seed (`tests/storyboard/known_failures.txt`
  preamble, run `30962437988`, commit `1348eed70`): 72 failed / 11 skipped /
  0 passed across 83 graded checks — the capability probe itself was
  rejected, so almost nothing reached its assertions.
- After GH #1512 (`adcp_version` rejected) landed
  (`tests/unit/test_storyboard_ledger_state.py`, "RE-SEEDED" section): 52
  ledgered checks over 72 collected, down from 81 over 95.
- Current ledger size (`grep -c` on
  `tests/storyboard/known_failures.txt`'s `test_storyboard_check[` lines,
  this session): **44 entries** (43 `mcp::`, 1 `a2a::`).

That is real, measured progress (72 → 52 → 44), but 44 genuine-gap entries
is still far from "a regression is the only way to go red." Gate only once
the trend has continued and the remaining count is small enough that every
entry is either a tracked, actively-owned gap or the one permanent
`comply_test_controller/pagination-integrity` family. There is no fixed
number that defines "close enough" — it is a judgment call for whoever picks
this up, informed by the trend line above and how much of the remainder is
still cascading from a small number of root causes (as #1512 and #1861 were
at the first seed) versus genuinely independent gaps.

## The mechanism to apply once the precondition holds

Four pieces, all read from the bead text and cross-checked against the code
at the time of writing:

### 1. Graded universe = `measured_failures UNION ledger_entries`

**The gap today:** `tests/storyboard/test_storyboard_conformance.py`'s
`_collect_checks()` (line 264) parametrizes only what the runner's summary
JSON reports as a failure or a skip cause — passing checks are never
enumerated, because the runner's summary is an aggregate pass/fail/skip
*count*, not a per-check pass record (see the function's own docstring,
lines 264-270). `pytest_generate_tests` (line 308) then parametrizes
exactly that measured set (line 319).

Consequence: when a ledgered check starts passing, its `(protocol, track,
storyboard_id, step_id)` id simply is not produced this run. It is not a
passing parametrized test that could be inspected — it disappears from
collection entirely, and nothing reports the graduation. Contrast with the
`e2e_rest` precedent (`tests/bdd/conftest.py:2845`'s
`pytest_generate_tests`, `tests/bdd/e2e_rest_known_failures.txt`): every
Gherkin scenario is collected on every run regardless of ledger state
(scenarios come from feature files, not from a runner-reported failure
list), so a graduated entry there shows up as an un-xfailed PASS — visible,
not silent.

**The fix, when it is time:** widen `pytest_generate_tests` so the
parametrized id set is `measured_failures(protocol) UNION
ledger_entries(protocol)`, not `measured_failures(protocol)` alone. For each
id present in the ledger (`tests/storyboard/known_failures.txt`, parsed via
`scripts/audit/ledger.LedgerCheckId`) but absent from this run's measured
failures, synthesize a check entry whose status reads as a failing check —
something like `ledgered-but-not-measured-failing: graduated or no longer
graded, triage and remove` — rather than silently omitting it. That makes
the graduation (or the check disappearing from the spec entirely) a visible,
triageable CI event instead of an invisible one, matching the "genuine
regression AND genuine graduation both fail CI until reconciled" discipline
`tests/unit/test_storyboard_ledger_state.py`'s docstring already claims for
the ledger as a whole.

### 2. Add `storyboard-conformance` to the Summary job's `needs`

`.github/workflows/ci.yml`'s `summary` job (line 658) lists its `needs` at
lines 665-681 and validates each job's result at lines 689-702.
`storyboard-conformance` (job id, line 372) is in neither list today — a new
un-ledgered conformance failure on that job currently lands green because
nothing downstream depends on it. Once (1) is in place and the precondition
above holds, add `storyboard-conformance` to both the `needs` array and the
`if` validation block, the same way `bdd-in-network` already is.

### 3. Derive the ledger block-header counts; delete stale pre-seeding prose

`tests/storyboard/known_failures.txt` groups entries under `# ---
<storyboard_id> (<n>) ---` headers. At the time of writing, four of these
headers disagree with the actual entry count beneath them — they were
written at seed time and not kept in sync through subsequent graduations.
When the gate work lands, regenerate these header counts from the entries
themselves (mirroring however `scripts/audit/ledger.py` already parses the
file) rather than hand-maintaining them, so a future partial graduation
cannot leave a stale header behind again.

Three sites still carry pre-seeding prose that is stale now that the ledger
*has* been seeded and graded runs exist — delete all three when the gate
lands:

- `.github/workflows/ci.yml` around lines 376-382: the `storyboard-
  conformance` job comment still reads "the ledger is unseeded (empty)
  pending this job's first real in-network run; land report-only, seed
  ... THEN add this job to `needs`" — the ledger has 44 real entries
  today, not zero.
- `tests/unit/test_storyboard_ledger_state.py` lines 15-27: the module
  docstring still says "Until SB-4b lands the runner module and its first
  in-network run, `EXPECTED_LEDGER` is pinned empty" and "This test
  currently fails because none of the triad exists yet" — the triad
  (ledger file, `tests/storyboard/conftest.py` loader, this pytest module)
  has existed and been graded since the first seed; the docstring was never
  updated after that landed.
- `tests/unit/test_architecture_required_ci_checks_frozen.py` lines 34-38:
  the comment on the `"CI / Storyboard Conformance"` entry still says "Not
  yet in the Summary job's `needs` (report-only until the known-failures
  ledger is seeded from a real run)" — true at the time it was written,
  false today; update or remove once the job is actually added to `needs`
  under item (2).

### 4. Fold into a composite action shared with `bdd-in-network`

`storyboard-conformance` (`.github/workflows/ci.yml:372-438`) and `bdd-in-
network` (`.github/workflows/ci.yml:318-370`) are structurally the same job:
harden-runner → checkout → clean up lingering Docker containers → log in to
GHCR → (storyboard-only: download the pinned compliance/schema bundle) →
run the suite in-network via `run_all_tests.sh` → clean up Docker services.
Several of those steps are byte-identical between the two jobs today, and
the copies have already drifted once — `storyboard-conformance`'s cleanup
step (lines 396-399) dropped the `docker network prune -f` line that `bdd-
in-network`'s equivalent step (lines 342-346) still has, which is exactly
the kind of silent divergence a shared composite prevents. The repo already
has a composite-action convention (`.github/actions/_install-uv`,
`_setup-env`, `_pytest`, `_postgres`) for this; when the gate work lands,
extract the shared steps into a new composite under `.github/actions/` and
have both `bdd-in-network` and `storyboard-conformance` call it, keeping
only what's genuinely job-specific (the compliance/schema bundle download,
the `run_all_tests.sh` target name) inline.

## Explicitly out of scope for this note and for `salesagent-zs64m.4`

- Actually adding `storyboard-conformance` to `summary.needs` or the `if`
  validation block.
- Any other change that makes a `storyboard-conformance` failure
  merge-blocking.
- Report-side graduation *visibility* (the ledger going stale silently on
  the report side) — that was judged in-scope for PR #1858 itself under
  finding 5 and is tracked separately as `salesagent-vuz9t.12`.

Whoever picks this up next should re-measure the ledger size against the
numbers in "The precondition for gating" above before doing anything else —
if the trend has stalled or reversed, that is itself the signal that gating
is still premature.

# BDD harness migration

## Method

Every item below is executed the same way:

> Take one seeded thing. Build the general solution for it. Apply it to every
> place a partial version lived. Compare the result against before. If anything
> differs, answer why — did you fix something that was wrong, or break something?

The comparison is the gate. A difference is the finding, not the problem: either
the old partial version seeded a payload the pinned model rejects and a scenario
was passing on it (record the defect, ledger the scenario, continue), or you broke
something (revert, understand, retry). No item needs a gate of its own beyond the
one named in its **Compare** line.

That is the method. The rest of this document is the plan — what the things are,
which sites they live at, and what the comparison has to catch for each.

---

## What the research established

Five measurement clusters ran against the corpus. Reports:
[bdd-cluster-findings.html](../reports/bdd-cluster-findings.html); the decision
queue is [bdd-decisions.html](../reports/bdd-decisions.html), which measures itself
from the tree at render time rather than quoting a report.

**Seeding is bypassed more than it is duplicated.** The counts have a committed
classifier — `scripts/audit/creative_literal_sites.py`, which states its definition
in its docstring so it can be argued with rather than guessed at:

| `--scope` | literals | hand-built | omitting `assets` |
|---|---|---|---|
| `tests` | 234 | 210 | **97** |
| `bdd` | 50 | 50 | **4** |

`assets` is required on both `oneOf` branches of the pinned model, so an omitting
payload cannot validate and passes today only because nothing reads it.

**Only 4 of the 97 are in `tests/bdd`.** Fifty are in `tests/unit`, 37 in
`tests/integration`, 5 in `tests/e2e`. The number that made this urgent is real and
mostly NOT a harness defect — which is what decides the scope question below.

**Fifteen owners exist**, but they are heterogeneous artifact kinds — an ORM row
factory, an assets-slot builder, request-dict builders, `CreativeAsset`
constructors, JSON fixture data — that cannot share one owner. Three ship the
pre-3.1.1 shape. The owner-bypassing sites are the target, not the owner count.

**A wrong payload is sometimes the point, and nothing says which.** Six distinct
kinds of deliberate wrongness live in `uc006_sync_creatives.py` alone — wrong type,
explicit `None`, absent key (distinct from `None`), empty dict, empty string, and
semantically-wrong-but-shaped-right — and the same deliberate omission appears once
with an "intentionally" comment and once with no marker at all.

**Row seeding is transport-independent; mock seeding is not.** 41 step bodies reach
into `env.mock[...]`, bypassing the realization seam, declared unsupported nowhere.

**The scenario defects are volume, not judgment.** 337 sites across nine classes:
174 bare-truthiness assertions, 65 Then steps that grade nothing, 41 env.mock sites,
17 mutating Thens, 17 raw-ctx-heavy steps, 11 shadowed sentences, 5 mock-patching
steps, 4 dispatching Thens, 3 dispatching Givens.

---

## Item 1 — deliberate malformation

**First, and only for this reason:** every later item would otherwise silently
repair the scenarios whose entire purpose is being wrong.

**The thing.** Three sentinel families exist and disagree about scope:

- `OMIT = _Omit()` — `tests/factories/request.py:96`
- `OMIT_IDEMPOTENCY_KEY`, `OMIT_ACCOUNT` — `tests/harness/media_buy_create.py:35,41`
- a deliberate local clone — `tests/bdd/steps/domain/uc011_accounts.py:56`, kept
  local because *"that one is the create env's and this is the sync verb's wire path"*

Two carry recorded decisions NOT to unify. Overrule them with an argument or ratify
them in place — do not assume they merge.

**The general solution.** One sentinel vocabulary covering the six kinds above, each
expressible and distinguishable at the call site, extended to creatives and pricing.

**Every place.** Every inline creative and pricing literal in `tests/bdd/` and
`tests/harness/`.

**Compare.** A guard cannot find an unmarked malformation by looking for markers. It
validates every literal against the pinned model and requires the marker on whatever
fails. At this point the literals are still inline, so the guard sweeps *literals*,
not factory calls.

Task `.1`. The non-BDD deletion is `.6`.

## Item 2 — creatives

**The thing.** 50 hand-built literals in six step files, 40 of them in
`uc006_sync_creatives.py`. Four omit `assets`. Three owners ship the pre-3.1.1 shape
(`.10`).

**The general solution.** A factory API — names, override semantics, malformation
markers, and a named baseline. `build_create_request_kwargs`
(`tests/bdd/steps/generic/_create_request.py:26`, docstring: *"The single
base-request literal"*) already IS the baseline and lacks only a name, which is why
every caller re-inlines its own. Committing the API is `.2` and is a day's work; it
unblocks the parallel migration.

**Every place.** Sharded by file, list from
`creative_literal_sites.py --scope bdd`. Deliberate malformations migrate to the
marked form rather than being normalized away.

Also in scope here, because it is the same edit to the same files: the ctx protocol
(`.3`). `uc006` alone has 40 creative seeders leaving 18 distinct ctx key-sets, and
the corpus carries 89 ctx keys written and never read. Pre-measure the READ side —
which keys, read by which steps — before starting, or this discovers its scope after
it begins.

**Compare.** Outcome identity is necessary and NOT sufficient.
`scripts/audit/compare_runs.py` treats any per-nodeid outcome change as a failure,
including `passed -> xfailed`, and flags vanished nodeids — real, and verified in
code. But 97 structurally-invalid creatives pass green today, which proves outcomes
do not read the seeded object. A collapse that normalizes an invalid seed produces
zero outcome changes.

So the sufficient check is a request-payload diff, captured on the **REQUEST** side.
`_dispatch.py:69` is `_populate_ctx_from_result(ctx, result)` — it receives the
RESPONSE, and `TransportResult` carries `payload`/`envelope`/`wire_response`/
`wire_error_envelope` and no request-as-dispatched. There is no single request-side
convergence today: `dispatch_request` goes via `env.call_via`, `dispatch_via_client`
via `AdCPTestClient.call`, plus `when_request._call_via`. Capture at those three
entries, or introduce the convergence first and capture there — worth doing on its
own merits. That is `.5`.

Shards compare against a shared baseline in one batched run, not a full BDD run each
(8324 in-process nodeids × ~50 shards). `compare_runs.py`'s documented ~19-nodeid
transport-parameter flap between identical runs goes in the gate's tolerance, not in
a reader's head.

**Blind spot, stated because an agent will hit it.** The payload diff sees only
DISPATCHED requests. The DB-row-seeding literals (`given_entities`,
`given_media_buy` — about 5 of the 50) are guarded by Item 1's validity guard,
outcome identity, and a per-class production mutation instead.

Tasks `.2`, `.3`, `.10`, `.11`.

## Item 3 — pricing options

**A different disease, so a different solution.** Not owner collapse: *one writer,
fifteen mutators, one clobberer.* `ctx["default_pricing_option"]` is written once
(`tests/bdd/conftest.py:4936`) and mutated in place downstream.

**The general solution.** Freeze the default; convert the fifteen mutators to
overrides.

**Compare.** Same payload diff as Item 2.

Task `.4`.

## Item 4 — whatever the next iteration finds

The list is not fixed in advance. That is the point of running it as a loop.

---

## The separate track — checks that grade nothing

Independent of the seeding items, running alongside them. 337 sites.

**One question per site: does the check grade what the scenario names, against the
pinned AdCP standard?** An assertion that can cite the pinned schema or the spec
prose mandating it is done. One that can cite nothing is rewritten to what the
scenario actually means, or deleted with its sentence.

Resolves: 174 bare-truthiness assertions get real expected values, 65 empty Thens
get the assertion they imply or go with their sentence, 17 mutating Thens give up
the write, 11 shadowed sentences get one body, and the 29 sites an earlier draft left
unhoused — 17 raw-ctx-heavy, 5 mock-patching, 4 dispatching Thens, 3 dispatching
Givens.

Two rules specific to this track:

- **Assert against the request-as-sent or a named baseline reference, never a
  re-typed literal.** An assertion reading `ctx["request_kwargs"]` survives any
  reshaping of how the request was built. One step already does this; it is the
  model.
- **A passing assertion is not a grading assertion.** Flipping an expected value
  turns an equality assert red trivially and proves nothing. Breaking *production* is
  the real proof, and costs a controlled mutation, a run and a revert per scenario.
  Budget that or state plainly that the cheap version is what is being done.

Task `.7`, blocked on `.8` for the deletion half only.

## Where the two tracks contend

**They overlap on exactly six files** — the ones holding the creative literals.
Those six get their assertion work done by the same agent that takes their creatives
(`.11`). Every other file's assertion work is independent and starts immediately
(`.7`). An adversarial review measured this: 11 of the 12 files the mock-routing work
must touch are files the scenario work also touches, so these cannot be separate
agents.

That follows from one rule, learned by nearly losing a scenario:

> **One agent owns a file, for every job in it.** Shard by file, never by tag, never
> by defect class. A tag-sharded run once handed two halves of a same-named scenario
> pair to two agents; pytest-bdd stores scenarios in a plain dict, so a duplicate
> name deletes one silently. It was stopped one edit short.

Genuinely disjoint, and parallel with everything: `tests/harness/` seam changes,
conftest xfail cleanup, ratchet shrinking. None touch step bodies.

## Blockers and supporting work

**`.8` — regeneration, P0, blocks the deletion half of `.7`.** The `BR-UC-*` files
are generated by `scripts/compile_bdd.py` in this repo, driven from `~/projects/adcp-req`'s
phase-5 orchestrator. The track deletes 65 sentences from generated files. Either
every deletion is mirrored upstream — per-scenario work, budgeted rather than
discovered — or the next generation pass reintroduces them and the deleted steps
become unbound lines.

**`.6` — delete the 93 non-BDD invalid literals and the tests holding them.** The
validity guard stays scoped to `tests/bdd` + `tests/harness`, because the non-BDD
sites are not being marked, they are being removed. Gate: `creative_literal_sites.py
--scope tests` reports zero invalid literals outside BDD, the suite is green, and
every disappeared nodeid is on the deletion list with no surviving nodeid changing
outcome.

**`.9` — the env.mock gap, reduced to declaration.** The 41 sites work on all three
in-process transports; what they cost is e2e grading breadth. That gap is only
coarsely ratcheted: `tests/unit/test_architecture_e2e_rest_escape_hatches.py` scans
`_HARNESS_DIR.glob("*.py")` — harness-only — so no pinned tuple sees an `env.mock[...]`
reach in a step body, and a 42nd site added tomorrow fires no guard. The tuples it
does pin (`EXPECTED_XFAIL_ROUTES`, `EXPECTED_E2E_REST_PARAMETRIZE_GATES`,
`EXPECTED_E2E_REST_EXCLUSION_POINTS`, `EXPECTED_UNSUPPORTED_DECLARATIONS`) are exact
and cannot silently grow. So: add a step-body detector, declare unsupported out loud,
pin the tuple, shrink it opportunistically — instead of engineering per-site seam
routing entangled with the scenario work.

## Tools that already exist

- `scripts/audit/creative_literal_sites.py` — what is seeded where, and the shard
  list. `--scope bdd | tests`.
- `scripts/audit/compare_runs.py` — the before/after comparison, per test.
- `scripts/audit/build_bdd_decisions.py` — the assertion defects, measured from the
  tree at render time.

## If the budget halves

The core that must survive: Item 1 re-scoped to unify the three sentinel families,
the three pre-3.1.1 owners killed, the 4 BDD assets-omitting sites migrated,
the other 93 deleted, and the 65 empty Thens resolved. Those pass
unconditionally today and always will. Everything else degrades gracefully — the 174
truthiness assertions grade presence, which is weak but not nothing.

## Not in scope

**Transport de-pinning.** 81 scenarios skip parametrization entirely, so the suite
reads as covering three transports while covering one. Deferred: those steps have
only ever run on one transport, so de-pinning now yields failures indistinguishable
from a moved baseline. After the items above, a scenario built from shared primitives
is transport-agnostic by construction. The trap — 21 twin-sets whose names differ only
by transport, colliding into silent deletion if both are renamed — is recorded in
[bdd-harness-architecture.md](bdd-harness-architecture.md).

**Non-BDD seeding — deleted, not migrated.** The creative pipeline is not
implemented to 3.1.1, so the 93 invalid literals in `tests/unit`,
`tests/integration` and `tests/e2e` encode a shape production does not produce.
Those tests fail and get deleted (`.6`). Pinning them as a shrink-only ratchet, as
an earlier draft proposed, would have preserved 93 tests asserting a contract
nothing implements. The one piece of judgment in that deletion: if removing a test
leaves a real obligation ungraded, the obligation moves to `tests/bdd` as a
scenario — it does not vanish silently.

**Production defects.** GH #2012, #1998, #2058 and adcontextprotocol/adcp#7329 are
owned elsewhere. The harness grades and ledgers them; it does not fix them.

## The other live documents

[bdd-harness-architecture.md](bdd-harness-architecture.md) supplies the vocabulary
target — the roughly 32 Given primitives, of which P01 is built and rolled out.
[bdd-compliance-migration.md](bdd-compliance-migration.md) is finished: the
response-compliance instruction, already applied.

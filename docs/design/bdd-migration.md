# BDD harness migration

One loop, repeated until there is nothing left to take.

> **Take one seeded thing. Build the general solution for it. Apply it to every
> place a partial version lived. Compare the result against before. If anything
> differs, answer why — did you fix something that was wrong, or break something?
> Then take the next thing.**

That is the method. The comparison is the gate; there is no other gate to build.

An earlier version of this document was a four-phase plan with a dependency graph
and a bespoke verification apparatus. It survived three reviews and none of them
made it smaller. The work does not have that shape. It has the shape above.

## Why the loop is sufficient

The failure this migration exists to prevent is a silent change in behaviour. The
loop catches that by construction: each iteration ends with a before/after
comparison across the whole suite, and every difference gets explained before the
iteration closes. A difference is the finding, not the problem. Two answers are
legitimate:

- **You fixed something.** The old partial version seeded a payload the pinned
  model rejects, a scenario passed on it, and now it does not. Record the defect,
  ledger the scenario against it, continue.
- **You broke something.** Revert, understand, retry.

Anything a phased plan would gate is a special case of "explain the difference".

## The tools exist already

- `scripts/audit/creative_literal_sites.py` — what is seeded where, and which sites
  go through no owner at all. `--scope bdd` for this corpus, `--scope tests` for the
  wider tree. It states its definition in its docstring, so a count can be argued
  with instead of guessed at.
- `scripts/audit/compare_runs.py` — the before/after comparison, per test. It treats
  `passed -> xfailed` and a disappeared nodeid as regressions, because a green suite
  cannot see coverage draining away. It documents its own ~19-nodeid tolerance for
  transport-parameter flap between identical runs.
- `scripts/audit/build_bdd_decisions.py` — the assertion defects, measured from the
  tree at render time.

Nothing else needs building first.

## What to take, in order

Not a dependency graph. Just the order that makes each iteration cheapest, because
each one removes duplication the next would otherwise work around.

**1. Deliberate malformation.** Some payloads are wrong ON PURPOSE and nothing marks
which. This goes first for one reason: every later iteration would otherwise
silently repair the scenarios whose job is to be broken. Six kinds of deliberate
wrongness live in `uc006_sync_creatives.py` alone — wrong type, explicit `None`,
absent key (distinct from `None`), empty dict, empty string, and
semantically-wrong-but-shaped-right — and the same deliberate omission appears once
with an "intentionally" comment and once bare.

Three sentinel families already exist and disagree about scope:
`tests/factories/request.py:96`, `tests/harness/media_buy_create.py:35,41`, and a
deliberate local clone at `tests/bdd/steps/domain/uc011_accounts.py:56`. Two carry
recorded decisions NOT to unify. Overrule them with an argument or ratify them in
place — do not assume they merge.

A guard cannot find an unmarked malformation by looking for markers. It validates
every literal against the pinned model and requires a marker on whatever fails.

**2. Creatives.** 50 hand-built literals in six step files, 40 of them in
`uc006_sync_creatives.py`. Four omit `assets`, which the pinned model requires on
both `oneOf` branches — so those payloads cannot validate and pass today only
because nothing reads them. Those four are where the loop's "why did it change"
question earns its keep.

`build_create_request_kwargs` (`tests/bdd/steps/generic/_create_request.py:26`)
already is the base-request literal; it lacks a name, which is why every caller
re-inlines its own.

**3. Pricing options.** A different disease: one writer
(`tests/bdd/conftest.py:4936`), then in-place mutation of the shared default
downstream. The general solution is freeze-and-override, not a factory.

**4. Whatever the next iteration finds.** The list is not fixed in advance. That is
the point.

## One rule while applying

**One agent owns a file.** Two people editing one file for different reasons is how
a same-named scenario pair once got split between two agents — and pytest-bdd stores
scenarios in a plain dict, so a duplicate name deletes a scenario with no warning.
Shard by file, never by tag, never by defect class.

## The other track: checks that grade nothing

Independent of the seeding loop and running alongside it.
[bdd-decisions.html](../reports/bdd-decisions.html) lists 337 sites; the biggest
classes are 174 bare-truthiness assertions and 65 `Then` steps with no assertion at
all.

One question per site: **does the check grade what the scenario names, against the
current AdCP standard?** An assertion that can cite the pinned schema or the spec
prose mandating it is done. One that can cite nothing is either rewritten to what
the scenario actually means, or deleted along with its sentence.

This is mechanical and cheap in judgment — one agent per scenario, and verification
is reading the citation. It needs nothing from the seeding loop, and the seeding
loop needs nothing from it.

Two cautions specific to this track:

- **A passing assertion is not a grading assertion.** Flipping an expected value
  turns an equality assert red trivially and proves nothing. Breaking production is
  the real proof. Whichever is done, say which.
- **Assert against the request-as-sent or a named baseline, never a re-typed
  literal.** An assertion reading `ctx["request_kwargs"]` survives any reshaping of
  how the request was built. One step already does this; it is the model.

## Before deleting anything from a feature file

**The `BR-UC-*` files are generated** by `scripts/compile_bdd.py` in this repo,
driven from `~/projects/adcp-req`'s phase-5 orchestrator. Deleting a sentence
without mirroring it upstream means the next generation pass restores it and the
deleted step becomes an unbound line. Confirm whether that pipeline still runs
before deleting.

## Scope

This corpus: `tests/bdd/` and `tests/harness/`. The same seeding defect exists more
widely — 93 further invalid literals across `tests/unit`, `tests/integration` and
`tests/e2e` — and the validity guard can pin those tests-wide as a shrink-only
ratchet so they cannot grow while this proceeds. Migrating them is separate work
with its own verification; nothing here grades an edit to a unit test.

## Not in scope

**Transport de-pinning.** 81 scenarios skip parametrization entirely, so the suite
reads as covering three transports while covering one. Those steps have only ever
run on one transport, so de-pinning now produces failures indistinguishable from a
moved baseline. After the loop runs its course, a scenario built from shared
primitives is transport-agnostic by construction. The trap — 21 twin-sets whose
names differ only by transport, colliding into silent deletion if both are renamed —
is recorded in [bdd-harness-architecture.md](bdd-harness-architecture.md).

**Production defects.** GH #2012, #1998, #2058 and adcontextprotocol/adcp#7329 are
owned elsewhere. The harness grades and ledgers them; it does not fix them.

## The other live documents

[bdd-harness-architecture.md](bdd-harness-architecture.md) supplies the vocabulary
target — the roughly 32 Given primitives, of which P01 is built and rolled out.
[bdd-compliance-migration.md](bdd-compliance-migration.md) is finished: the
response-compliance instruction, already applied.

# BDD harness migration

> Supersedes the `salesagent-itsii` epic, which modelled this as "build the
> primitives, then migrate the scenarios once" — one pass over one problem. It is
> several problems with a partial order.
>
> Revised after an adversarial review that disproved part of the first draft with
> a measurement. Where this document says something the review corrected, it says
> so, because the correction is the useful part.

## What the research established

Five measurement clusters ran against the corpus. Their reports are in
[bdd-cluster-findings.html](../reports/bdd-cluster-findings.html); the decision
queue is [bdd-decisions.html](../reports/bdd-decisions.html), which measures itself
from the tree at render time rather than quoting a report.

**Seeding is bypassed more than it is duplicated.** 191 inline creative dict
literals across 53 files, 41 distinct key-sets — and **110 built entirely by hand,
going through no owner at all**, 84 of which omit `assets`, a field with no default
on either `oneOf` branch. The first draft made "fifteen owners" the headline. The
review corrected that: the fifteen are heterogeneous artifact kinds (an ORM row
factory, an assets-slot builder, request-dict builders, `CreativeAsset`
constructors, JSON fixture data) that cannot share one owner, and three of them
ship the pre-3.1.1 shape. **The 110 owner-bypassing sites are the target, not the
owner count.**

**A wrong payload is sometimes the point, and nothing says which.** *"You cannot
tell a deliberate malformation from an accidental one at the seeding site."* Six
distinct kinds of deliberate wrongness live in `uc006_sync_creatives.py` alone —
wrong type, explicit `None`, absent key (distinct from `None`), empty dict, empty
string, semantically-wrong-but-shaped-right — and the same deliberate omission
appears once with an "intentionally" comment and once with no marker at all.

**Row seeding is transport-independent; mock seeding is not.** 41 step bodies reach
into `env.mock[...]`, bypassing the realization seam, declared unsupported nowhere.

**The scenario defects are volume, not judgment.** 337 sites across nine classes:
174 bare-truthiness assertions, 65 Then steps that grade nothing, 41 env.mock
sites, 17 mutating Thens, 17 raw-ctx-heavy steps, 11 shadowed sentences, 5
mock-patching steps, 4 dispatching Thens, 3 dispatching Givens.

## The order, and where the first draft was wrong

**Intent must precede the collapse.** Collapsing owners while a deliberate
malformation is unmarked silently repairs the scenarios whose entire purpose is
being wrong. Uncontested, and cheap, so it stays first.

**The collapse does NOT gate all scenario work.** The first draft claimed *"every
scenario repaired before the collapse is work that gets redone."* That is true only
for assertions that echo a seeded value. Measured: of the Then-side defect sites,
**roughly half to three-quarters sit in step files containing no inline creative
literal at all** — `then_error.py`, `then_success.py`, `uc011_accounts.py`,
`uc019_query_media_buys.py`, `uc010_capabilities.py` and a dozen more. An
error-path assertion whose expected value is a spec error code does not care which
factory built the creative.

So the serial bottleneck is smaller than drawn, and Phase 3a starts immediately on
the decoupled files under one rule:

> **Assert against the request-as-sent or a named baseline reference, never a
> re-typed literal.** An assertion that reads `ctx["request_kwargs"]` survives any
> reshaping of how the request was built. One already does this; it is the model.

## Parallelism

One rule, learned by nearly losing a scenario: **shard by file, never by anything
that can split a related unit.** A tag-sharded run handed two halves of a same-named
scenario pair to two agents; neither could see the collision, and pytest-bdd
deletes a duplicate scenario name silently.

The first draft then asserted 3a and 3b could run concurrently because they touch
different directories. **The review measured that and it is false: 11 of the 12
files 3b must edit are files 3a also edits.** "Route through the seam" means
editing the call sites, and the call sites are step bodies. Corrected below.

| work | parallel | why |
|---|---|---|
| Commit the factory API (names, overrides, markers) | no | one decision, unblocks everything |
| Reconcile the ctx protocol | no | one shared surface |
| Migrate call sites + scenario defects + env.mock routing | **yes — ONE agent owns a file for all three** | avoids the 11-of-12 contention |
| `tests/harness/` seam changes, conftest xfail cleanup, ratchet shrinking | **yes, genuinely disjoint** | never touches step bodies |

---

## Phase 0 — make intent expressible

**Serial. Small. Blocks the collapse, not the whole plan.**

The first draft said `OMIT` exists and needs extending. There are **three sentinel
families already, and they disagree about scope**:

- `OMIT = _Omit()` — `tests/factories/request.py:96`
- `OMIT_IDEMPOTENCY_KEY`, `OMIT_ACCOUNT` — `tests/harness/media_buy_create.py:35,41`
- a deliberate local clone — `tests/bdd/steps/domain/uc011_accounts.py:56`, kept
  local because "that one is the create env's and this is the sync verb's wire path"

So Phase 0 is *unify three families, then extend* — the same multiplicity this plan
exists to remove, sitting inside the phase whose job is to remove it.

Acceptance set: the **six** kinds above, each expressible and distinguishable at
the call site.

**Gate — and the mechanism matters.** A guard cannot find an unmarked malformation
by looking for markers. It must **validate every inline creative and pricing
literal against the pinned model and require the marker on any that fails.** At
Phase 0 the 191 literals are still inline, so the guard sweeps *literals*, not
factory calls — otherwise it grades nothing until Phase 2 and is a gate for a
different phase wearing this one's name.

## Phase 1 — one owner per seeded thing

**Split, because the first draft conflated a fast decision with slow work.**

**1a — commit the factory API.** Names, override semantics, malformation markers,
and the named baseline. `build_create_request_kwargs`
(`tests/bdd/steps/generic/_create_request.py:26`, docstring: *"The single
base-request literal"*) already IS the baseline and lacks only a name, which is why
every caller re-inlines its own. A day's work, and it unblocks Phase 2's parallel
migration.

**1b — reconcile the ctx protocol.** Concurrent with Phase 2, not gating it. This
is the judgment-heavy part and the first draft left it unsized: `uc006` alone has
**40 creative seeders leaving 18 distinct ctx key-sets**, and the corpus carries
**89 ctx keys written and never read**. Pre-measure the READ side — which keys,
read by which steps — before starting, or this phase discovers its scope after it
begins, which is exactly how the retired epic failed.

**1c — pricing options are a different disease.** Not owner collapse:
*"one writer, fifteen mutators, one clobberer."* `ctx["default_pricing_option"]` is
written once (`tests/bdd/conftest.py:4930`) and mutated in place downstream. The fix
is freeze-the-default and convert mutators to overrides. Same phase, different work
shape.

**Gate — outcome identity is necessary and NOT sufficient.**
`scripts/audit/compare_runs.py` treats any per-nodeid outcome change as a failure,
including `passed -> xfailed`, and flags disappeared nodeids. That is real and
verified in code. But the evidence base proves outcomes do not read the seeded
object: **84 structurally-invalid creatives pass green today.** A collapse that
normalizes an invalid seed, or flips which production branch runs, produces zero
outcome changes.

So the sufficient gate is one seam away: both dispatch paths converge on a single
ctx writer (`tests/bdd/steps/generic/_dispatch.py:69`). **Capture the dispatched
wire payload per nodeid before and after, and diff those.** Any payload delta not
explained by a declared normalization is the silent repair this phase fears.
`compare_runs.py` becomes the cheaper outer check. Note its own documented ~19
nodeids of transport-parameter flap between identical runs — that tolerance goes in
the gate, not in a reader's head.

## Phase 2 — migrate the call sites

**Parallel, sharded by file.** 110 hand-built sites first — they bypass every owner
and hold the 84 invalid payloads — then the remaining literals. Deliberate
malformations migrate to the marked form rather than being normalized away.

**Gate:** payload-diff clean, plus collection count unchanged. The first draft said
"every shard verifies itself", which implies a full BDD run per shard — 8324
in-process nodeids × ~50 shards. **Shards compare against a shared baseline in one
batched run.**

## Phase 3 — the scenario work

**Parallel, one agent owns a FILE and does all three jobs in it:** the scenario
defects, the call-site migration for that file, and the env.mock routing. This is
the correction to the 11-of-12 contention — the three jobs cannot be separate
agents on the same file.

Starts immediately on the decoupled files (no inline creative literals), and on the
rest after 1a commits the API.

Resolves: 174 bare-truthiness assertions get real expected values, 65 empty Thens
get the assertion they imply or go with their sentence, 17 mutating Thens give up
the write, 11 shadowed sentences get one body, and the **29 sites the first draft
left unhoused** — 17 raw-ctx-heavy, 5 mock-patching, 4 dispatching Thens, 3
dispatching Givens.

**THE FEATURE FILES ARE GENERATED, and the first draft did not mention it.** The
`BR-UC-*` files are compiled; the sibling design records that a sentence fix
"regresses on the next generation pass" because it is a generation defect. Phase 3
deletes 65 sentences from generated files. Either every deletion is mirrored
upstream — per-scenario work, budgeted here rather than discovered — or the next
generation pass reintroduces them and the deleted steps become unbound lines. This
needs a home before Phase 3 starts.

**Gate per scenario, with the mechanism named.** "Verified to fail when the
obligation is broken" has two readings and only one counts: flipping the *expected
value* makes an equality assert go red trivially and proves nothing; breaking
*production* is the real proof and costs a controlled mutation, a run and a revert
per scenario. Budget the second or state plainly that the first is what is being
done.

## Phase 3b — mock seeding, reduced to declaration

**Cut, on the review's recommendation, and the reasoning is sound.** The 41
env.mock sites work on all three in-process transports; what they cost is e2e
grading breadth, and that gap is already visible and ratcheted by
`tests/unit/test_architecture_e2e_rest_escape_hatches.py`, which pins
`EXPECTED_XFAIL_ROUTES`, `EXPECTED_E2E_REST_PARAMETRIZE_GATES`,
`EXPECTED_E2E_REST_EXCLUSION_POINTS` and `EXPECTED_UNSUPPORTED_DECLARATIONS` as
exact tuples. It cannot silently grow.

So: **declare unsupported out loud, pin the tuples, shrink them opportunistically**
— instead of engineering per-site seam routing entangled with Phase 3.

**Gate:** those pinned tuples shrinking to declared targets. Monotone, exact, and
enforced by a guard that already runs. The first draft's gate — "the same scenario
passing on all transports" — is a sample of one and passes by construction if you
pick a scenario that already works.

---

## If the budget halves

The core that must survive: Phase 0 re-scoped to unify the three sentinel families,
the three pre-3.1.1 owners killed, the 84 assets-omitting hand-built sites
migrated, and the 65 empty Thens resolved. Those pass unconditionally today and
always will.

Everything else degrades gracefully. The 174 truthiness assertions grade presence —
weak, but not nothing.

## Not in scope

**Transport de-pinning.** 81 scenarios skip parametrization entirely, so the suite
reads as covering three transports while they cover one. Deferred: those steps have
only ever run on one transport, so de-pinning now yields failures indistinguishable
from a moved baseline. After Phase 3 a scenario in shared primitives is
transport-agnostic by construction. The trap there — 21 twin-sets whose names differ
only by transport, colliding into silent deletion if both are renamed — is recorded
in [bdd-harness-architecture.md](bdd-harness-architecture.md).

**Production defects.** GH #2012, #1998, #2058, adcontextprotocol/adcp#7329 are
owned elsewhere. The harness grades and ledgers them; it does not fix them.

## Relationship to the other live documents

Three migration documents now cover this corpus, and the review flagged that they
are unreconciled. This one is the parent.
[bdd-harness-architecture.md](bdd-harness-architecture.md) supplies the vocabulary
target (the ~32 Given primitives; P01 is built and rolled out) and its Phase A/B/C
ordering is subsumed by the phases here.
[bdd-compliance-migration.md](bdd-compliance-migration.md) is complete — the
response-compliance instruction, already applied.

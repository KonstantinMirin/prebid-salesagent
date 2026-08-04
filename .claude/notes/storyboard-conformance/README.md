# Storyboard conformance — evidence base

Working artifacts from the AdCP 3.1.1 storyboard re-grounding sweep. Beads epic
**`salesagent-xg5w`** and its 15 tasks reference these by name; several cannot be
executed without them, which is why they are committed rather than left in a
session scratchpad.

Branch: `test/storyboard-binding-baseline`.

## What is here

| Path | What it is |
|---|---|
| `proposals/` | 40 files — one per `@storyboard-v3.1` scenario. Each carries a VERDICT, the real 3.1.1 binding, schema constraints quoted verbatim, a proposed Gherkin replacement, a step inventory, and a TICKET MATERIAL section. Produced by one reviewer per scenario. |
| `CONSOLIDATED-ISSUES.md` | The 40 proposals' follow-ups, deduplicated into 49 issues — one per **defect**, not per scenario. Classified PRODUCTION / TEST-INFRA / SCENARIO / UPSTREAM, ranked by severity, each with `file:line` evidence and the 3.1.1 clause. Input to `SB-5c`. |
| `E2E-PASS-{A,B,C}.md` | e2e-wireability audit of all 40 proposed Gherkins. Classifies every setup step and gives a WIREABLE / NOT-WIREABLE / EXEMPT verdict with the breaking step and remediation. |
| `BRIEF.md` | The brief each per-scenario reviewer worked from — authority order, the two known defect classes, the green-only rule. |
| `E2E-BRIEF.md` | The wireability brief. **Its header records that its first version stated the criterion wrongly**; the correction is the `realize_e2e` mechanism. |

Generated (not hand-written) companions live in `docs/test-obligations/`:
`storyboard-binding-baseline.md`, `storyboard-coverage-map.md`,
`storyboard-reconciliation.md`, `storyboard-roadmap.md`. Regenerate with the
scripts in `scripts/audit/`.

## Read these with the right amount of trust

The proposals are careful and heavily cited, but they are **analysis, not verified
fact**, and several are known to be wrong in specific ways:

- Four UC-006 proposals claim GREEN while being blocked by the UC-006 harness tag
  gate — that claim is unreachable on any transport.
- `repin-uc005-baseline` proposes a `has_more false` assertion that is RED on all
  four transports: the reference catalog is 57 formats against a `max_results`
  default of 50.
- `repin-uc005-roundtrip`'s `context.correlation_id` clause 422s on REST —
  `ListCreativeFormatsBody` is `extra="forbid"` with no `context` field.
- The three pre-brief UC-005 proposals reason about an IMPL dispatch path. IMPL was
  sunsetted from BDD parametrization (`tests/bdd/conftest.py:2871`); it does not run.

The audit tooling itself was wrong four times during this sweep — loose phase
matching, `Path.stem` collapsing every `index.yaml`, `requires_scenarios` treated as
a whitelist, and gating by directory instead of by which index pulls a scenario in.
Each was caught by cross-checking against the spec or by a reviewer contradicting the
tool. Assume the same failure mode is still possible.

## The one number that matters

> Numbers below superseded by salesagent-pw71 (SB-5b): the parsing bugs this
> paragraph's own methodology inherited (see "The lesson" above) are now fixed
> in `scripts/audit/storyboard_spec.py`, and `docs/test-obligations/
> storyboard-coverage-map.md` is the current, regenerated source of truth
> (62 on-path storyboards, 51 with no scenario, as of that change).

70 storyboards apply to us at 3.1.1, containing **1,337 graded checks**. Our
scenarios touch 12 of the 70; **1,167 checks sit in storyboards with no scenario at
all**. ~97% of those are plain wire assertions, so the gap is volume rather than
difficulty.

All of that is **derived by reading YAML, not measured**. `SB-1b` runs the real
`runStoryboard` runner and `SB-1c` reconciles it against the derived map — any
disagreement is a defect in the classifier, to be fixed there. Until that lands,
treat every number here as an estimate.

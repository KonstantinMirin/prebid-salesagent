# PR #1600 — what was correct, what went wrong, and how it decomposes

**Status:** PR #1600 CLOSED 2026-07-31. Branch `refactor/transport-boundary` retained as the
reference — several measurements below exist nowhere else.
**Final state:** 252 files, +10,024 / −3,229, 100 commits, never reviewed by anyone.
**Reviewer:** review requested from @ChrisHuie 2026-07-13; never actionable (draft + conflicting +
stale CI for most of its life).

This document exists because the analysis lived only in a chat transcript. Everything below was
measured against the tree, not recalled.

---

## 1. What it set out to do

Four issues bundled under a "transport boundary" banner: #1088, #1169, #1172, #1442.

**The bundle had no architectural coherence.** Examined individually, not one is a
transport-boundary ticket:

| Issue | Stated as | Actually touches |
|---|---|---|
| #1088 | Principal at transport boundary | identity plumbing + deleting a dead duplicate (`auth_utils.py:84`) |
| #1169 | migrate `select(AdapterConfig)` to repository | **admin-layer data access** — 13 of ~20 sites are admin blueprints |
| #1172 | coerce `format_ids` at the DB boundary | **persistence typing** |
| #1442 | `*Body` models to `SalesAgentBaseModel` | **schema policy** (Pattern #7) |

Four layers, one name. There was no single invariant to hold, so each ticket's fallout ran in a
different direction, and "handle the fallout at the architecture level" was impossible — there were
four architectures. **The sprawl was structural, not a discipline failure.**

---

## 2. What was correct

Verified against the tree, not the PR description:

| Claim | Verification |
|---|---|
| #1088 — principal lookups banned in `_impl` | `IMPL_SESSION_ALLOWLIST = set()`, empty; 29 tests pass |
| #1169 — raw `select(AdapterConfig)` migrated | **0** outside repositories |
| #1172 — `normalize_agent_url` at zero callers | 1 hit, and it is a docstring cross-reference |
| #1442 — `*Body` models on `SalesAgentBaseModel` | 12 migrated, 0 remaining (11 of them already on `main`) |

**#1172 implements a normative spec MUST**, which is worth recording because it was later challenged
and the challenge was wrong. `v3.1.1 dist/schemas/3.1.1/core/format-id.json`:

> "Callers comparing two `format-id` values MUST canonicalize `agent_url` per the AdCP URL
> canonicalization rules before treating two formats as the same."

Also genuinely good, and reusable:

- **Verify-before-implement.** Six of seventeen tickets were materially wrong as written; two would
  have shipped defects if implemented as described. Later, 8 of 12 follow-up tickets were wrong.
- **Per-scenario xpass inspection** caught 2 of 10 ledger rows passing vacuously — bulk removal
  would have ratcheted nothing on those two.
- **The mutation-ratchet guard form** (`test_architecture_tripwire_mutation_sensitivity.py`) is the
  one enforcement mechanism on this branch that demonstrably works, because it *executes* rather
  than pattern-matches.
- **Six use cases wired to grading against AdCP 3.1.1** — the most valuable output, and independent
  of the refactor (§4).

---

## 3. What went wrong

### 3.1 The transport boundary was already clean

```
src/core/tools/   (the transport-boundary surface)  →  0  get_db_session() calls
IMPL_SESSION_ALLOWLIST                              →  set()   (empty)
```

The 326 session sites are in `admin/blueprints` (23 files), `services` (16), `core` (10),
`adapters` (5). **None in the layer the PR is named after.** #1169 is really the first slice of
persistence-ownership work, which starts somewhere else entirely.

### 3.2 Guards that never guarded

The branch's own thesis — that mechanisms which look like enforcement often aren't — turned out to
apply to its own guards:

| Mechanism | Defect |
|---|---|
| `test_architecture_bdd_no_duplicate_steps.py` | matches **zero** groups under its own key; empty allowlist read as "clean", meant "nothing checked" |
| `test_mcp_tool_type_alignment.py` | `normalize_type` matched only `typing.Union`; on 3.12 PEP 604 `X \| None` is `types.UnionType`, so **0 of 14** fields registered as arrays |
| the `fa3p` guard | inert its entire life |
| `ast-grep-bdd-guards` pre-push hook | two rules, both literal never-match placeholders |
| `test_architecture_obligation_test_quality.py` | only scans functions carrying a `Covers:` tag |

Every genuine discovery this month came from **mutation runs**, not from AST guards.

**The deeper point (owner):** a guard is code checking code, and nothing checks the checker. A test
is grounded in a spec; a guard encodes a convention. Adding a fifth guard is a dead end — the
regress terminates only when the bad state becomes *unrepresentable*.

### 3.3 `extra="allow"` — two mandated patterns that are mutually exclusive

~24 schema classes resolve to `extra="allow"`, inherited from the SDK `Library*` bases.
`SalesAgentBaseModel` — and Pattern #7 with it — **is not in their MRO at all**.

Measured:

| Form | Resolves to |
|---|---|
| `class Product(LibraryProduct)` — **CLAUDE.md Pattern #1, verbatim** | `extra='allow'` ❌ |
| `class Product(SalesAgentBaseModel, LibraryProduct)` | **still `extra='allow'`** ❌ |
| explicit `model_config = ConfigDict(extra=get_pydantic_extra_mode())` | `extra='forbid'` ✅ |

So **CLAUDE.md's Pattern #1 example is the form that produces the defect**, and
`test_architecture_schema_inheritance.py` enforces that example — the guard pushes every new schema
into the hole. It is not 24 mistakes; it is one documented instruction reproduced 24 times.

**On severity — the spec does not excuse it.** `core/product.json` sets `additionalProperties:
true`, which binds the *receiver* not to throw. It says nothing about propagation. Pattern #7 is
exactly that distinction: `forbid` in dev/CI so drift surfaces, `ignore` in prod so we stay
forward-compatible — and **ignore means drop, not carry**. `extra="allow"` fails both halves: it
does not raise in dev, so drift is invisible, and it does not drop in prod, so unknown fields
propagate into our objects and onto the wire.

### 3.4 Measurements that did not reproduce

The recurring failure was confident prose written from *reading* rather than *measuring*:

| Claimed | Actual |
|---|---|
| "13 orphaned `render_template` kwargs" | **71** pairs / 42 names (the scan used a name-global check and counted `.js` as a consumption source) |
| "28 duplicate step groups" | **0** under the guard's own key; 18 `@then` pairs under a corrected key |
| "nine undeclared fields, a closed set" | an undercount — pytest aborts each test at its first exception, masking later rejecting names |
| "`property_tags` reaches the buyer wire" | **it does not** — `dynamic_products.py:305` operates on the SQLAlchemy ORM model; that is a DB column write |
| "spec ranks `format_option_refs` > `format_kind` > `format_ids`, we read only the last" | real order is `format_option_refs` > **`format_ids`** > `format_kind`; `format_ids` is second, carries no `deprecated` flag, and its deprecation floor is 2027-Q4 |
| unit baseline 5777 / 91 failures | 5640 / 79 |

### 3.5 Real defects the survey found (independent of the refactor)

- **`estimated_exposures` is never written** by production (`models.py:270` says so outright) but is
  read by the `min_exposures` filter at `products.py:606` — so that filter **silently excludes every
  guaranteed product**, and logs a plausible-looking reason.
- **`get_products` never used the canonical format key.** `products.py:492` compares bare `id`,
  discarding `agent_url`, with a comment citing #1172 directly above it. The PR's headline invariant
  was false at the most-called discovery tool.
- **`measurement` reaches the buyer wire** from `product_conversion.py:449` — one undeclared field,
  spec-legal but under a name the spec reassigned.

### 3.6 Process

- **Never reviewable.** Draft + `CONFLICTING` for most of its life, which silently skips
  `pull_request` CI. Two red checks (a CVE and a broken dependency) hid for weeks behind that.
- **No correction signal.** A 252-file PR nobody can open produces no feedback, so a wrong premise
  ran unchecked for a week. A 40-file PR reviewed on day two would have surfaced "the guards are
  fiction" immediately.
- **Ticket provenance was unknowable.** With a shared beads board, only 17 of 473 open tickets (4%)
  carried a `Branch:` line, and selecting by title/epic pattern-matching pulled in other branches'
  work twice. *(Historical: the beads tooling has since moved to bd 1.1.2/Dolt and the remedy is
  different — see the beads notes. The lesson stands: attribute by recorded provenance, not by
  pattern-matching.)*

---

## 4. What the branch actually produced

Production is ~1,000 lines across 51 files; tests are ~8,800 across 180. Not a refactor — a survey.

But the test mass is **not** scaffolding for the patches. It is six protocol surfaces wired to
grading against AdCP 3.1.1, four of which have no dependency on the refactor:

| Stream | Source | Depends on branch production? |
|---|---|---|
| BR-UC-001 `get_products` binding | `4e7b300d5` | **No** |
| BR-UC-008 `get_signals` binding | `63985d113` | **No** |
| BR-UC-009 `update_performance_index` binding | `0540ca47d` | **No** |
| BR-UC-010 capabilities binding | `f4f968325` | **No** |
| UC-002 create-paused + UC-019 status precedence | `ec6313aa0` | Yes — `paused` precedence (#1619) |
| UC-002 unknown-top-level-field | `2cec9c20a` | Yes — this is #1442's grading, already written |

Also: 10 feature files reconciled to 3.1.1; 3 locally-added feature files; 7 new step modules;
7 new test modules; 10 new architecture guards (4 executable, 6 AST); 3 dead pre-commit hook scripts
and 2 zero-import sham test files deleted; `PrincipalRepository` (the only new `src/` file); an
offline UI round-trip test.

**`main` wires nothing for UC-001/008/009/010** — grepping `origin/main:tests/bdd/conftest.py` for
those tags returns empty. All four are green-field.

---

## 5. The decomposition

### 5.1 Ports — the grading slices

Code exists and is green on this branch. **Do not re-implement.** Extract onto a branch off fresh
`origin/main`, run the suite, ship. One ticket per PR.

| Ticket | Slice | Ships | Masked → moved to |
|---|---|---|---|
| **#1822** | BR-UC-001 + **shared harness base** | `alt-empty`, `alt-filtered` | `main` → #1595 · `alt-anonymous` → #1591 |
| **#1823** | BR-UC-008 | `main-rest`, `main-context-echo` | `main-mcp` → #1783 |
| **#1824** | BR-UC-009 | all 5 — **nothing masked** | — |
| **#1825** | BR-UC-010 | `main-readonly`, `main-timestamp` | `main-mcp`, `main-rest` → #1592 |

Umbrella #1594 stays open for the sets still dormant after these (notably UC-010's `protocols`-filter
and `context`-echo scenarios, which have no step definitions on any transport).

**The de-scope rule:** a scenario wired straight into a strict-xfail grades nothing — it is a dormant
scenario with extra steps. Each slice ships only the tags that genuinely assert and must be **fully
green on `main`**: no new strict-xfail entries, no ledger growth. **#1824 is the model** (5 of 5
grade).

The masked scenarios are wired **in the same change as the fix that unblocks them**, so the fix
arrives verified and the wiring arrives grading. Recorded on #1595, #1591, #1783, #1592.

> Ordering trap on #1783: two gaps stack behind `T-UC-008-main-mcp`. The zero-signals matcher fails
> *first*, so fixing `value_type` (#1593) alone leaves the tag still masked.

### 5.2 Rebuilds — the four original tickets

**Do not copy how the branch does it.** The branch has the *patched* form; the structural forms are
smaller. In every case the guard exists only because the wrong thing is still expressible.

| Ticket | Branch has | Should be |
|---|---|---|
| **#1442** | 24 per-class configs + a new guard | a module re-exporting SDK types **policy-stamped**, plus one `TID251` banned-api line. Pattern #1's documented form then works unchanged; 122 scattered `adcp.types` imports collapse to one boundary. Its BDD grounding (`2cec9c20a`) already exists. Also fix CLAUDE.md's Pattern #1 example, which currently manufactures the defect |
| **#1172** | canonical helper + a guard banning the alternative; `products.py:492` still bypasses it | canonical identity **on `FormatId` itself**, so a bare-`id` comparison is unwritable. Retires the guard and fixes `products.py:492` |
| **#1088** | ratchet guard banning principal lookups | `_impl` does not receive a session, so the lookup is unreachable |
| **#1169** | — | reframed and retitled as **persistence-ownership, slice 1** (admin blueprints). 326 sites; a `UnitOfWork` exists at `repositories/uow.py` but is not the only door. A program, not a PR |

For these, the branch is a reference for **what the fallout will be** — which fixtures break, which
call sites exist, what the counts are — not for how to do it.

### 5.3 Small independent extractions

Each its own PR, no ticket-per-PR decision needed until reached: `paused` status precedence (#1619)
+ its UC-002/UC-019 grading · `get_signals` request typing · the A2A validation-envelope operation
label · the admin format-picker `agent_url` fix + its offline UI test · the DRY consolidations · the
four **executable** guards · removal of the dead pre-commit hook scripts.

### 5.4 What does not survive

The six **AST** guards that pattern-match; the `extra="allow"` 10-subtask epic (replaced by the
structural form); and whatever in `tests/unit` / `tests/integration` exists only to prove a patch
works.

---

## 6. Extraction mechanics

- Branch off **freshly fetched `origin/main`**, never local `main` (stale in every worktree here).
- New files (`tests/harness/<env>.py`, `steps/domain/uc0XX_*.py`, `test_uc0XX_*.py`) port as-is.
- **`tests/bdd/conftest.py` is hand-edited every time** — it is where the `wired_tags` registration
  lives *and* where the de-scope happens (drop masked tags + their `_SPEC_GAP_XFAILS` entries). That
  one file is the whole of the per-slice work, so be deliberate rather than mechanical.
- **#1822 carries the shared base** the others need: `tests/harness/_base.py` (+80/−22),
  `steps/_outcome_helpers.py` (+15), `steps/generic/_dispatch.py` (+6), `steps/_datatable.py` (new).
  Deliberately bundled with its first consumer rather than shipped as infrastructure with no user.
- **Verify against `main`, not the branch.** A green run on the old base confirms a coupling instead
  of exposing one. UC-001 grades `get_products`, which #1172 touched — that is exactly where a hidden
  dependency would hide, and a red result there means *resequence behind #1172*, not debug.

---

## 7. Method lessons

1. **Measure, do not read.** Every wrong claim in §3.4 was written from reading code that "clearly"
   did something.
2. **Fix the level, not the site.** Two tickets produced ten follow-ups because each finding was
   treated as a site. Grouped by level, ~20 open items are about four levels.
3. **Never defer a class without a guard — and prefer making it unrepresentable.** Where a structural
   form exists, it is smaller than the guard plus the sites.
4. **Batch size is a correctness property.** The binding constraint was never engineering capacity;
   it was that nothing could tell the work it was wrong. If a PR cannot be reviewed in an hour, it is
   too big to be corrected.
5. **A wired-then-masked scenario is not coverage.** Ship what grades.
6. **Never write an issue number you have not confirmed.** Predicted references were produced twice
   in this effort (and once by me while filing #1822–#1825). File first, cross-link after.

---

## 8. Issue index

**Origin:** #1088, #1169, #1172, #1442 (all reopened by the closure — none merged).

**Created from this branch:** #1756, #1775, #1782, #1783, #1784, #1785, #1786, #1789, #1796, #1797,
#1798, #1822, #1823, #1824, #1825. (#1799 was closed as in-scope, then superseded by the structural
form.)

**Widened/connected:** #1589 (SSRF egress seam — creative-agent outbound path), #1591, #1592, #1593,
#1594 (decomposition recorded), #1595, #1602 (error-code taxonomy — two further sites), #1711
(`daily_breakdown` as a third silently-ignored request field), #1619.

**Owed and delivered in the closing comment:** @ChrisHuie's #1585 item "creative-format check
implemented three divergent ways" **is fixed** — the canonicalizer consolidation, with a guard
keeping `normalize_agent_url` at zero callers. It arrives via the #1172 slice.

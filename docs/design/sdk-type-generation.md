# SDK type generation: the principles it is missing

**Status:** design. Rewritten 2026-10-18 after a review refuted the first version's central
claim. What that version got wrong is recorded in §8, because the wrong story is still the
intuitive one and will be proposed again.

**Provenance convention.** This document cites three different trees and they disagree. Every
citation is tagged:

- `(pin)` — the installed wheel, `adcp 9.0.0b3+sa.8qela.f33d4fc71`, AdCP 3.2.3. **This is
  what salesagent runs and the only tree whose line numbers bind.**
- `(main)` — `adcontextprotocol/adcp-client-python` upstream `main` @ `734bf3acd`.
- `(ts)` — `adcontextprotocol/adcp-client`, `@adcp/sdk` 16.0.0-beta.7/8.

The first version of this document cited `(main)` line numbers under a `(pin)` header. That
is how it came to recommend extending a function the pin had deleted.

---

## 1. The one-line summary

The Python SDK's generated surface is **named by position in places where the schema carries
an identity**, and every other defect here either follows from that or was hidden by a guard
keyed on a name. The TypeScript SDK is better on three of the five principles below and worse
or equal on two; it is a reference for specific mechanisms, not a model to copy wholesale.

**The response arms are not the generator's doing.** `CreateMediaBuyResponse1/2/3` comes from
one line of this repo's own emitter:

```python
# post_generate_fixes.py:6454 (pin)
class_names = [f"{self.base}{index}" for index in range(1, len(branches) + 1)]
```

Two more sites defend that numbering: `:6449-6453` remaps `BuildCreativeResponse` branches
`(0, 4, 1, 2, 3, 5)` "to preserve the long-standing public numbering", and `:6408-6411`
detects the success arm by `class_name.endswith("1")`. **The naming decision has exactly one
site and it is a line of our code.** `--use-title-as-name` is absent from the generator's
argument list `(main)`, and adding it would rename nested anonymous classes while leaving
every response arm numbered.

**And the fix largely exists at the pin already.** `scripts/union_branch_names.py` (pin) names
a union branch by rungs — `title`, else discriminator `const`, else the full required set,
else **fail closed** — and `tests/test_union_branch_names.py:66-73` (pin) pins the result over
the pinned bundle by equality:

```
557 root branches:  169 named by title · 82 by const · 27 by required set
                    278 mint no class (96 ref, 10 scalar, 172 validation-only)
                      1 unnameable  (content-standards/get-content-standards-response.json#/oneOf/0)
```

The wheel already ships `CreateMediaBuyRequestExplicitPackagesWithFixedAllocation` and its
siblings. So the work is to **wire the rungs into the response-arm emitter**, not to invent a
naming scheme and not to file 327 upstream tickets.

---

## 2. The principles

Each is stated so a build can refuse a violation, because a principle nothing enforces is how
this surface got here. Cost is stated, not elided.

### P1 — A name is a function of the schema node's identity, never of a traversal position or a loop index

Forbids `f"{base}{index}"`; forbids `AssetsNN`; and forbids *fixing* an index by reordering,
which is what the `BuildCreativeResponse` remap does — pinning a wrong name is not holding a
right one.

**Cost:** a node with no derivable identity gets **no class**. The pin pays this today on
exactly one branch, which is the evidence the cost is affordable.

**TS:** holds for titled arms (`generate-types.ts:708-711` preserves `branch.title`, and
`json-schema-to-typescript` names by title) and fails elsewhere — 45 numbered declarations
`(ts)`, including `BrandReference1..12` and `MacroBearingURL1..8`.

**Enforceable today:** `tests/test_lazy_types.py::test_partial_modules_avoid_numbered_codegen_names`
(pin) already refuses `[A-Za-z]\d+$` on the curated partials. Widen its population.

**Scale, and the nested rule.** 1045 of 4076 classes in non-bundled domain modules carry a
trailing digit (pin). 80 are RootModel or enum wrappers with no field set; the remaining 965
form **238 families** — `CreativeItem1` and `CreativeItem2` are one family in one module. Key
each member by (field-name set, required-name set, `Literal` const defaults), which is the
nested form of the root rungs:

```
206 of 238 families   key is injective -> every member gets a content-derived name
 85 colliding groups  IDENTICAL shape -> P2 failures; one class, so no name needed
  9 colliding groups  differ only in a field typed as ANOTHER numbered class
```

So the nested residue is not a naming gap. 85 of the 94 collisions are the same node generated
several times, and the 9 remaining differ only through a cascade one level down
(`MacroDeclaration` holding `Location6` versus `Location8`). **No arm in the wheel differs only
by a scalar constraint** such as `maxLength`.

**Which rung, and why it matters.** The rung choice decides churn under upstream change. A
full-field-set key renames the class whenever the spec adds an *optional* field, which is an
`ImportError` downstream on every bump. The required-set key is stable under optional
additions and renames exactly when **requiredness** changes — a semantic change a caller
should see loudly. Title and discriminator const are stable under all content change. So the
honest claim for P1 is: a silent swap becomes unrepresentable, and an upstream semantic change
becomes a loud `ImportError` instead of a silent repoint.

### P2 — One schema node, one class; a `$ref` is a reference

Forbids a copy by any route — remote-ref resolution (§3.2) and `create_model` copies alike;
the canonical layer used to build 32 public classes that way
(`tests/test_canonical_models_are_subclasses.py`, #1368, pin).

**Cost:** every ref must be local before generation, and a layer wanting a different public
shape must subclass rather than re-derive.

**TS:** holds. `Warning` references `WarningCode`, `WarningAffectedResource`, `ExtensionObject`
by name; nothing inlined.

### P3 — The model's accepted set is the schema's accepted set

Already the SDK's own stated principle — the `--strict-types` rationale at
`generate_types.py:1266-1279` (pin) says the point is that the two validators the SDK ships
do not disagree about the same bytes. §4.3 is a live violation of it.

**And `extra` is part of the accepted set, so it is derived too.** `AdCPBaseModel` sets
`extra="ignore"` for every model. Wherever a schema declares `additionalProperties: false`,
that base setting makes the model accept what the schema rejects — which is a P3 violation,
**not** a deliberate divergence to be excluded. A schema declaring
`additionalProperties: false` generates `extra="forbid"`, so an unknown field raises at
assignment instead of being dropped silently.

The environment-dependent choice belongs to the **consumer**, at the consumer's boundary, not
to the SDK's base class. This repo already makes it: `get_pydantic_extra_mode()` selects
`ignore` in production for forward compatibility and `forbid` in development so an
unimplemented spec field is loud (CLAUDE.md pattern #7). An SDK that hardcodes one of the two
takes that decision away from every caller.

This also removes the only reason P3's check needed an exclusion list. With `extra` derived
there is no standing divergence to exclude, and an exclusion list was a declared table — the
thing P5 and P8 reject.

**TS:** holds at the type level (`warnings?: (Warning & { code?: 'a' | 'b' })[]`). Runtime not
established — the Zod layer was not examined.

### P4 — Identity is graded by shape, not by name

Forbids a snapshot keyed only on name → `module:QualName` **as the sole gate**.

**Cost:** a committed fixture that churns on every legitimate schema bump.

**TS:** does **not** hold it — no public-surface snapshot exists in `adcp-client`.

**Python already half-holds it:** `tests/test_asset_aliases_stable.py` grades asset aliases by
their `asset_type` discriminator and `tests/test_collision_aliases.py` grades by `__module__`
(pin). Those are the precedent to extend.

**And field names are not enough.** `diff_generated_types.snapshot` records field *names*
only, so a change from `Literal['a']` to `Literal['b']`, or `str` to `AnyUrl`, is invisible.
Record the **annotation text** alongside the name — one line in the AST walk.

### P5 — Every public binding is derived by one rule, and the build refuses what the rule cannot derive

Forbids hand tables: `aliases.py` (2704 lines, 136 plain + 98 annotated), `KNOWN_COLLISIONS`,
`_eager.py:1097-1098`, and both hand-written `__init__` files (pin).

**Cost, stated plainly:** a name only a human knows is lost. `AccountReferenceById` over an
untitled arm is the example — unless a rung derives it, it goes.

**TS:** does **not** hold this either. It carries a hand rename table at
`generate-types.ts:368-384`, a hand handler for the title `Size-mode mutex` at `:986-1003`,
and `export type { Error as TaskErrorDetail }` at `src/lib/index.ts:1296` `(ts)`.

**The question this document cannot yet answer, and it blocks the work:** *which class does a
derived alias bind to?* Verified from salesagent's venv:

```
alias   adcp.types.aliases.CreateMediaBuySuccessResponse
        -> adcp.types.canonical_creative.CreateMediaBuyResponse1
arm     adcp.types.domains.media_buy.create_media_buy_response.CreateMediaBuyResponse1
alias is arm         False
alias subclasses arm True
```

The semantic alias resolves to a **subclass in the canonical layer**, with legacy format
identity removed — not to the generated arm. So "switch to the semantic name" is a
**base-class change**, not a rename, and the canonical-versus-wire-faithful layering has to be
decided before P5 can say what a name means.

### P6 — A name that shadows a host-language builtin never claims the bare public slot

**TS applies it:** `Error as TaskErrorDetail`. **Python plausibly does:**
`"Warning" in adcp.types.__all__` is `False` (verified). Intent is not established — and that
is the problem. This should be a rule the build knows, not an absence someone has to guess at.

### P7 — Determinism is a precondition of grading, not a fix

`run_datamodel_codegen.py`'s input-order patch makes the output a function of the input.
Without it, `make validate-generated`'s byte compare and every snapshot are meaningless. The
first version of this document called that patch a guard protecting the defect; it conflated
*order being total* (necessary) with *which order was chosen* (cosmetic). Already enforced by
`tests/test_code_generation.py:3189::test_codegen_input_order_is_total` (pin).

### P8 — The import path is one namespace level, and the generation layout is private

A caller writes `adcp.types.<domain>.<Class>` and nothing deeper. The per-schema-file module is
an artifact of how generation works, not a contract, so it moves under a private package and
the domain package re-exports from it.

Measured depth today, excluding the `bundled/` mirror:

```
  1 level     44 modules
  2 levels    34 modules
  3 levels   962 modules   adcp.types.domains.a2ui.bound_value
  4 levels    57 modules   adcp.types.domains.core.assets.asset_union
  5 levels    39 modules   adcp.types.domains.core.async_response_refs.creative...
```

So the common case is three levels and the worst is five:

```
today   adcp.types.domains.core.warning.Warning
        adcp.types.domains.media_buy.create_media_buy_response.CreateMediaBuyResponse1
target  adcp.types.core.Warning
        adcp.types.media_buy.CreateMediaBuySuccess
```

`domains` carries no information — every type is in a domain. The schema stem repeats the
class name. Both are generation detail leaking into the caller's import.

**Cost:** this breaks every deep import, including five of this repo's eleven. That is why it
belongs in the one change in §5 and nowhere else — flattening the namespace later would be a
second break, which the §5 constraint forbids.

**The same applies to the flat loader.** `adcp.schemas.load_schema("adcp-agents.json")` makes a
caller name a package, a verb, and a filename with an extension. One accessor at the root
taking a schema name is the ergonomic form.

**TS holds this and exceeds Python:** a caller writes
`import { CreateMediaBuySuccess } from '@adcp/sdk'` — one level, no domain, no file stem.

### P9 — The spec version is read from the SDK, never written as a literal

`adcp.get_adcp_spec_version()` is the authority. A literal version in a path is a defect
waiting for the next pin bump, because the SDK reports the new version while the literal keeps
resolving the old bundle, and nothing fails.

The bundle directory is not equal to the spec version — the SDK reports `3.2.3` and bundles
`3.2` — so the derivation takes the exact directory when it exists, else the longest dotted
prefix, and **raises** when neither matches. `generate_types.py:1296-1303` solves the same
mismatch with a hardcoded `/3.2.3/` → `/3.2/` symlink, which is the literal in another form.

`scripts/audit/sdk_dx_probes.py` in this repo had the literal `"3.2"` and now derives it; that
function is the reference implementation.

### P10 — A check compares the output to the inputs, never to a previous output

This is the principle the rest of the document was missing, and the repo's own history
establishes it. Every check in the pin that has found a real defect is **derived**:
`_enforce_every_class_is_reachable` found #911, the reachability test found the double-load in
#1360, and the rung-4 fail-closed refusal found the one unnameable arm. Every check that held
a defect **green** carries a **blessed value**: `test_public_api.py`'s 7944-name snapshot held
the four mislabelled activation-key names, and the alias-stability tests assert a hand-listed
expectation per alias.

A blessed value records whatever the tree held on the day someone committed it. It detects
*change*, which is not the same as detecting *wrongness*, and it cannot tell a fix from a
regression without a human who already knows the answer.

**So `make validate-generated`'s byte compare survives and the snapshots do not.** The byte
compare asserts a property — the committed tree equals `f(schemas, pinned generator)` — and
carries no blessed value at all. P7's determinism is what makes that `f` a function.

**Rules derived:** R1←P1, R2←P2, R3←P3, R4←P5, R5←P4, R6←P5. Nothing in the first version
followed from P6 through P10, and its headline thesis followed from none of them. P10 also
retires R5 as the first version stated it: see §5.

---

## 3. The developer-experience requirements

These eight requirements are normative. A generator change satisfies them or it is not done.
They are not a test artifact bolted on afterwards: each one states a question a caller asks
the SDK, and each failure below is a caller getting the wrong answer or no answer.

`scripts/audit/sdk_dx_probes.py` in the salesagent repository measures the Python column. The
TypeScript column is measured statically against `adcp-client` `main` — the generated files and
both root index files — because the two languages share no test harness.

| # | Requirement | Python | TypeScript |
|---|---|---|---|
| DX1 | A caller resolves a tool's request and response types from `<Tool>Request` / `<Tool>Response` | **PASS** 10/10 | **PASS** all five tools |
| DX2 | A caller resolves every arm of a multi-arm response by the arm's own schema title | **FAIL** 0/9 | **PASS** all three arms exported |
| DX3 | The model accepts exactly what the schema accepts | **FAIL** validators disagree | not established at runtime |
| DX4 | A caller emits an error, including a code the registry does not list | **PASS** | **PASS**, and exceeds Python |
| DX5 | A caller emits a non-blocking observation | **FAIL** | **FAIL** |
| DX6 | A caller extends a response type with their own fields | **FAIL** 98 of 260 | **PASS** by language |
| DX7 | A semantic name resolves to the class the schema describes | **FAIL** | **PASS** |
| DX8 | No positional name appears in the surface a caller imports | **FAIL** 39 + 949 | **PASS** 1 |
| DX9 | A caller imports a type with one namespace level, `adcp.types.<domain>.<Class>` | **FAIL** 3 levels typical, 5 worst | **PASS** 1, flat root export |
| DX10 | Nothing in the SDK names a spec version as a literal | **FAIL** symlink alias | not examined |

Python satisfies two of ten; TypeScript satisfies six, fails one, and leaves two
unexamined. The findings behind each row:

- **DX2.** TypeScript declares `CreateMediaBuySuccess`, `CreateMediaBuyError` and
  `CreateMediaBuySubmitted` as named interfaces and exports all three from
  `src/lib/types/index.ts:162-164`. Python exports `CreateMediaBuyResponse1` and resolves
  **neither** `CreateMediaBuyError` nor `CreateMediaBuySubmitted` under any top-level name —
  two of the three arms of a tool this seller serves have no name a caller can import.
- **DX3.** TypeScript preserves the narrowing in the type (`Warning & { code?: 'a' | 'b' }`) and
  ships runtime schemas from a separate entry point, `@adcp/sdk/schemas`. Whether those
  schemas preserve the narrowing was not examined, so the cell reads unestablished rather than
  pass.
- **DX4, where TypeScript exceeds Python.** `error.code` is `string` in both, matching the
  schema's open vocabulary. TypeScript then ships `STANDARD_ERROR_CODES`,
  `isStandardErrorCode()` and `getErrorRecovery()` (`src/lib/index.ts:1294-1301`) and exports
  no `ErrorCode` type at all. That is the right shape for a documentary vocabulary: a caller
  asks whether a code is standard instead of being refused for using one that is not. Python
  exports a closed `ErrorCode` enum, which invites exactly the refusal the schema forbids.
  **Python should adopt the TypeScript shape here**, and this is the one row where matching is
  not enough.
- **DX4, second TypeScript lesson.** `export type { Error as TaskErrorDetail }` dodges the
  JavaScript global rather than leaving the name unexported. That is P6 applied, and it is
  what Python should do with `Warning` instead of omitting it.
- **DX5 is the shared failure, and it is not a generator defect.** Neither root index exports
  `Warning`, `WarningCode` or `WarningAffectedResource`, and the vocabulary is three closed
  members in both. §6 covers it: the channel cannot express the condition, so the fix is a
  spec change, not a codegen change.
- **DX6.** A TypeScript interface extends without ceremony. Python's 98 annotated aliases
  cannot serve as a base class, which is §4.4.
- **DX7.** TypeScript's index takes `CreateMediaBuySuccess` from `./tools.generated`, one
  definite projection. Python's semantic alias resolves to a `canonical_creative` subclass
  (§2, P5).
- **DX8.** Exactly one name in a TypeScript root index matches the positional pattern, and it
  is `PreviewRenderV3`, a version suffix rather than a traversal index.

**What this settles.** TypeScript is the reference for DX2, DX4, DX6, DX7 and DX8, and the one
change in §4 is what moves Python onto all five. DX3 is Python's own behavior defect and lands
before that change. DX5 is shared, belongs upstream in the schema, and no amount of generator
work reaches it.

---

## 4. The defects, as consequences

### 3.1 Positional names, and the live swap

`src/core/tools/creatives/listing.py:10-11` in this repo:

```python
from adcp.types.domains.core.creative_item import CreativeItem1 as MediaItem
from adcp.types.domains.core.creative_item import CreativeItem2 as TextItem
```

```
CreativeItem1  ['asset_id','asset_kind','asset_type','content_uri']   media, correct today
CreativeItem2  ['asset_id','asset_kind','asset_type','content']       text,  correct today
both arms untitled · both 4 fields · 4 required · 3 of 4 names shared
symmetric difference {'content','content_uri'}
```

Correct today; one reorder from meaning the opposite, with no type error. **Under P1 this
becomes unrepresentable rather than detectable**: the required-set rung names these two from
their own content, and a reorder cannot then swap them. That is a stronger fix than any gate,
and it is why the naming work outranks the snapshot — the reverse of what the first version
said.

It also shows why P4 must key on **name sets, not counts**: both arms have four fields.

### 3.2 A remote `$ref` is resolved as a copy

Demonstrated on a three-file tree with production's flags: with `--allow-remote-refs`, the
first referencing module gets a fresh copy named from the URL stem and the canonical class
generated from the file's own title is orphaned; `--reuse-model` then anchors later referrers
on *the copy*. With local relative refs: `thing: c.SharedThing`, zero duplication.

`rewrite_refs` (`:631` pin, `:503` main) already rewrites URLs to relative paths, which is why
production mostly does reuse — `core/ext.json` is `$ref`'d by 326 files and yields 2 classes;
`protocol-envelope.json` 78 → 1. The work is shrinking the carve-outs:
`PRESERVE_CANONICAL_URL_REFS` (3 paths) and the macro refs forced absolute.

Census: 2216 model names defined in more than one module, **809 with a differing declaration
under one name**. Worst: `Creative` 9 modules / 8 shapes, `Account` 8/8, `Scope` 14/6,
`Location` 14/4. Nothing checks shape compatibility.

`Error` is a naming defect, not a reuse failure: `get-task-status-response.json` and
`tasks-get-response.json` declare inline anonymous `properties.error` objects — genuinely
distinct shapes, correctly generated, **named `Error` from the property name**.

### 3.3 An `allOf` enum narrowing is lost — P3 violated

`media-buy-commitment-response.json` narrows `warnings[].code` to two members; the generated
model accepts a third. `jsonschema` rejects the payload, `model_validate` accepts it. The
merge **unioned** the vocabularies and left `_1`-suffixed aliases of its own members as the
tell. The `const` case is correct, so the defect is specific to `enum`. **Scope not
established** — one site demonstrated, no sweep run, and the sweep is a prerequisite.

### 3.4 Two declaration forms for one kind of name

`aliases.py` (pin): 136 plain assignments, 98 annotated `X: TypeAlias = Y`. Only the plain
form can be inherited from (`Invalid base class [misc]`). 92 of the 98 resolve to a class and
6 to unions, which are uninheritable in any form. No rule separates the groups:
`CreateMediaBuySuccessResponse` and `UpdateMediaBuySuccessResponse` have identical roles and
are declared two different ways. **Dropping the annotation is the cheapest item here.**

### 3.5 The `ActivationKey` names were wrong on day one

Two of them are not in `aliases.py` at all — `_eager.py:1097-1098` (pin) declares
`PropertyIdActivationKey = SegmentIdActivationKey` and
`PropertyTagActivationKey = KeyValueActivationKey` as **synonyms**. And they were never
correct: at `5c63decdd` (#47, 2025-11-16) `aliases.py:143` already bound the property-id name
to the *first positional arm*, with the docstring "using property_id for identification",
while the activation-key schema at that same commit already had two arms — segment-id and
key-value.

So the first version's story — drift from a four-arm schema — is wrong. They are compat
synonyms that were mislabelled at birth, which means they leave through the deprecation
staging in §4, not silently.

---

## 5. Implementation: ONE structural change, and the constraint that forces it

**The governing constraint, from the user: this is the second large rewrite of this surface in
a month, and there must not be a third.** So the sequence this document first proposed is
itself rejected — seven stages produce *three* separate public-surface breaks (aliases become
derived; classes get renamed; duplicate classes disappear), each wanting its own deprecation
window, its own snapshot regeneration, and its own round of adopter churn. That is the pattern
being complained about, written down as a plan.

The rule instead: **every change that moves a public name happens in one release, or it does
not happen.**

### Before the change — additive only, no public name moves

Neither of these touches a name, so neither is a rewrite and neither needs staging. They land
first so the one structural change is *measured* rather than asserted.

- **The narrowing intersect (P3).** Sweep for every `allOf`+`enum` narrowing site, fix the
  merge to intersect, assert accepts-iff-schema-accepts over the found sites. A behaviour fix
  with no rename. Build the check as a **sampled** instrument — the bundle resolves offline
  once `/3.2.3/` is aliased to `/3.2/`, and 113 of 1057 schemas carry root `examples` as a
  payload source. It is not total, and that is acceptable: today nothing checks P3 at all.
  Each **deliberate** divergence gets its own assertion naming why (`AdCPBaseModel` sets
  `extra="ignore"`, so wherever a schema says `additionalProperties: false` the model is wider
  on purpose). One assertion per divergence, never a ledger of them.

**The shape fixture is NOT part of this, and must not be committed.** The first version of
this document put it first. Under P10 it fails: it records whatever the tree held when someone
committed it, so it would have blessed the four mislabelled activation-key names exactly as
`test_public_api.py` did. Its legitimate use is proving the one change did what it claims, and
that is a **before/after diff attached to the pull request** — take the snapshot before, diff
after, commit nothing. `SCHEMA_DELTAS.md` already produces it (`generate_types.py:1704-1712`).
Once P1 lands, the swap the fixture exists to detect cannot occur.

### The one change

Six things that each move public names, landed together because landing them apart is six
breaks instead of one:

1. **Name every union branch by the rungs (P1).** Delete `post_generate_fixes.py:6454`'s index
   naming, `:6449-6453`'s reorder, and `:6408-6411`'s `endswith("1")` success detection —
   detect the success arm from the schema's `status` const. Use
   `generated_names.generated_root_class_name` / `generated_nested_class_name`, **not**
   `_schema_title_to_class_name`, which the pin deleted as wrong for 94 of 946 roots.
2. **Decide the layer, once (P5).** Whether a semantic name binds to the generated arm or to
   the `canonical_creative` subclass. Today it is the subclass and nobody chose that. This is
   the base-class change, and it is the one structural change being accepted.
3. **Derive the whole binding layer (P5).** `aliases.py`, `_eager.py`, both `__init__` files,
   and `KNOWN_COLLISIONS` — generated from the module tree under the decision in (2), with the
   98 `TypeAlias` annotations gone.
4. **Local refs only (P2).** Shrink `PRESERVE_CANONICAL_URL_REFS` to empty and fix the
   sibling-document alias case. This is in the same change because removing a duplicate class
   removes a public name.
5. **Flatten the namespace to `adcp.types.<domain>.<Class>` (P8).** Move the per-file modules
   under a private package and re-export from the domain package. This breaks every deep
   import, so it cannot be a later step — a second namespace break is what the constraint at
   the top of this section forbids. Give the flat schema loader one root accessor at the same
   time.
6. **Derive the spec version (P9).** Replace the `/3.2.3/` → `/3.2/` symlink and every version
   literal with the derivation, failing closed when no bundle matches.

Emitted together: semantic names as the real classes, positional names as deprecated aliases,
one snapshot regeneration under review (`test_public_api.py:505-520`'s `repointed` check fires
for every renamed class — intended), one `DeprecationWarning` cycle, one major for removal.

### After, and not part of it

- **One metadata PR upstream:** a `title` for
  `content-standards/get-content-standards-response.json#/oneOf/0`, the single branch the
  rungs cannot name.
- **The nested positional names** (~1045) stay. The root-branch rungs do not reach them, this
  document has no rule for them (§9), and inventing one would be the third rewrite. They are
  ratcheted shrink-only and left alone until a rule exists that is worth one more break.

**For this repo:** the 11 positional imports move exactly once, after the change, in one
commit. Not before — switching early is the base-class change without the decision behind it.

---

## 6. Guards: keep, replace, delete

The first version implied most of these were worthless. Three of them are load-bearing and the
ones that actually pin the wrongness were not on its list.

| guard | verdict | why |
|---|---|---|
| `run_datamodel_codegen.py` order patch | **KEEP** | P7. Deleting it first makes `--check` disagree between APFS and ext4 — the bug it fixed. Retire when zero classes are traversal-named. |
| `tests/test_public_api.py` 7944-name snapshot | **REPLACE**, then **DELETE** | A blessed value (P10). It held the four mislabelled activation-key names green. Replace it with the derived bare-slot rule: bind a bare `_generated` slot only when every definition under the name has one shape, else leave it unbound. Under derived names, repointing is unrepresentable. |
| `make validate-generated` byte compare | **KEEP** | The one check with no blessed value: committed tree equals `f(schemas, pinned generator)`. P7 is what makes that a function. |
| `post_generate_fixes.py:6454`, `:6449-6453`, `:6408-6411` | **DELETE** | These *are* the positional naming and its defences. The most directly defect-preserving code in the pipeline. |
| `KNOWN_COLLISIONS` (13 at pin) | **REPLACE** then delete | Its comments state the rule 13 times by hand. Derive it; keep `_enforce_every_class_is_reachable` and `test_collision_guard.py`. |
| `scripts/collision_allowlist.json` | **DELETE now** | Dead; referenced only from a doc. |
| `PRESERVE_CANONICAL_URL_REFS` | **REPLACE** | A carve-out, not a guard. Shrink to empty, then fail the build on any surviving remote ref. |
| `stabilize_inlined_core_refs` | **DELETE** after Stage 6 | Exists only because of remote refs. |
| `stabilize_nested_discriminators` | **KEEP** | Unrelated to refs — it drops a flattened duplicate discriminator pydantic rejects at import. |
| `_eager.py:1097-1098` synonyms | **DELETE** via staging | Mislabelled at birth; still a compat surface. |
| 98 `TypeAlias` annotations | **DELETE** | §4.4. |
| `test_asset_aliases_stable.py`, `test_collision_aliases.py` | **DELETE after the change** | Hand-listed expectations per alias — blessed values. Until the change they are the only thing holding the hand table honest; afterwards the alias *is* the derivation and they assert a tautology. |
| `test_lazy_types.py::test_partial_modules_avoid_numbered_codegen_names` | **KEEP, widen** | A regex over `__all__`, no blessed value. Widen to the whole surface; it becomes P1's grade. |
| `post_generation_manifest.json` | **REPLACE** | Keep the rule (a fix that changes nothing fails the run), drop the per-fix table. The seven fixes it records as no-ops at this pin are dead code; delete them. |
| `test_union_branch_names.py` | **SPLIT** | Keep the partition identity (`named + classless + refused == total`) and the single-refusal assertion — both derived. Drop the five equality counts (557/169/82/27/1); they are a ledger. |
| `union_branch_names` rung 4 (fail closed) | **KEEP** | A build failure, not a value. This is P1's enforcement, and it is what found the one unnameable arm. |
| `_enforce_every_class_is_reachable` | **KEEP** | Derived; found #911. |
| `test_canonical_models_are_subclasses.py`, `test_export_surface_is_derived.py` | **KEEP** | Properties over the live tree. |
| shape fixture | **DO NOT ADD** | P10. A one-off before/after diff in the pull request instead. |

**Churn versus correctness.** The positional→semantic rename of response arms is *required* by
P1, so it beats the emitter sites that defend the numbering. Re-exporting `Warning` on
`adcp.types` is ergonomics and P6 argues against it — it loses. Switching salesagent's four
"switchable" imports is neither: it is a layering decision, and the layer comes first.

---

## 7. What must not change

- Every class already named by its schema title (`CreateMediaBuyRequest`, `Product`,
  `Warning`, …) keeps its name. **The module paths do not survive** — P8 flattens
  `adcp.types.domains.<domain>.<schema_stem>` to `adcp.types.<domain>`, and the first version
  of this document was wrong to list the deep paths as fixed. The class names are the
  contract; the paths are generation detail.
- The 136 plain-assignment alias *names*. Only their provenance becomes derived.
- The request-side split classes the pin already emits
  (`CreateMediaBuyRequestExplicitPackagesWithFixedAllocation`, …) — already correct under P1.
- `_generated` bare-name resolution for every non-colliding name.
- The codegen flags (`--strict-types bool int float`, `--reuse-model`, `--use-annotated`, …),
  `rewrite_refs` itself, and `flatten_validation_oneof`.
- `adcp.types`' PEP 562 lazy mechanism. Stage 2 generates the *contents* of `__init__` /
  `_eager.py`; it does not replace the loading shape.
- Positional names as deprecated aliases through one major.

---

## 8. What the first version of this document got wrong

Recorded because each wrong claim is the intuitive one and will be proposed again.

1. **"The cause is the missing `--use-title-as-name`."** Not for the response arms — those are
   `post_generate_fixes.py:6454`, our own code. The flag repro measured a path that does not
   produce them.
2. **"327 untitled arms, and no generator change can name them."** The pin's own rungs name
   all but one of 557 root branches, graded by equality.
3. **"Stage 5: file 327 titles upstream."** One title.
4. **"Extend `post_generate_fixes._schema_title_to_class_name`."** Deleted at the pin as wrong
   for 94 of 946 roots.
5. **"The field-shape gate is the only item that would have caught either live bug."**
   `make validate-generated` already reddens on a reorder. The gate's value is at the
   acceptance step.
6. **"The gate goes first."** Naming by derivation makes the swap unrepresentable; a detector
   of a class of failure loses to its elimination. (The gate still lands first — but because
   it is additive and measures the real change, not because it is the fix.)
7. **"The `ActivationKey` aliases drifted when the schema shrank from four arms to two."**
   Wrong on day one, and two of the four are `_eager.py` synonyms, not aliases.
8. **"Four of our imports could switch today."** The alias binds to a `canonical_creative`
   subclass; that is a base-class change.
9. **"`run_datamodel_codegen.py` is a guard protecting the defect."** It is the determinism
   precondition. Only the *choice* of order is cosmetic.
10. **"`Error` is not exported from the TS SDK."** It is, renamed to `TaskErrorDetail` — which
    is P6 applied, not a gap.
11. **Citations under a `(pin)` header that resolved against `main`.** The cause of 1, 4 and
    part of 2.
12. **"Commit the shape fixture and assert it."** It carries a blessed value, so it would
    have held the mislabelled activation-key names green exactly as the public-API snapshot
    did. P10 is the rule it violates, and the document did not have it.
13. **A seven-stage plan.** Three separate public breaks, each with its own deprecation window
    and adopter churn — the repeated-rewrite pattern this work exists to end, proposed as the
    way to end it. §5 is now one change.

---

## 9. Not established

- Whether `branch_classes`' emitter is wired for all eleven split roots or only some — its
  test docstring says "not wired into the generation pipeline", yet the wheel carries the
  split classes for `create-media-buy-request`.
- Whether the 98 `TypeAlias` annotations were deliberate. No rule or comment found.
- Whether the 9 cascade families reach zero after a fixed-point naming pass — name the leaves,
  collapse identical shapes, re-key. Not iterated.
- Whether any bundle schema sets `additionalProperties: false`. If none does, the
  `extra="ignore"` divergence is empty at this pin and P3's exclusion set is empty with it.
- The scope of P3 divergences beyond §4.3. The sampled check is how to find out.
- The scope of the `allOf`+`enum` narrowing loss beyond one field (§4.3).
- The generator condition behind the sibling-document `allOf` re-derivation.
- Whether `Warning`'s absence from `adcp.types.__all__` is builtin-shadowing policy or an
  omission (P6 wants it to be policy either way).
- Whether each of this repo's positional use sites needs a base class or only a type position.
- Whether the TS SDK validates at runtime as Python does; the Zod layer was not examined.
- Go and Java SDKs.

# SDK type generation: the principles it is missing

**Status:** design. Rewritten 2026-10-18 after a review refuted the first version's central
claim. What that version got wrong is recorded in §7, because the wrong story is still the
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

**Scale:** 1045 of 4076 classes in non-bundled domain modules carry a trailing digit (pin,
introspected). The root-branch rungs do not reach the nested ones; that residue needs a
nested rule, and this document does not have one.

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
do not disagree about the same bytes. §3.3 is a live violation of it.

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

**Rules derived:** R1←P1, R2←P2, R3←P3, R4←P5, R5←P4, R6←P5. Nothing in the first version
followed from P6 or P7, and its headline thesis followed from neither.

---

## 3. The defects, as consequences

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

## 4. Implementation: ONE structural change, and the constraint that forces it

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

- **The shape fixture (P4).** Commit `diff_generated_types.snapshot()` as a fixture and assert
  it, keyed on field name sets **plus annotation text**. Honest value: a per-class artifact a
  reviewer reads at the acceptance step. *Not* "the only thing that would catch a reorder" —
  `make validate-generated` already reddens on any reorder; the hole is a developer
  regenerating and committing the diff unread. This is the instrument that will prove the one
  change below did what it claims.
- **The narrowing intersect (P3).** Sweep for every `allOf`+`enum` narrowing site, fix the
  merge to intersect, assert accepts-iff-schema-accepts over the found sites. A behaviour fix
  with no rename.

### The one change

Four things that each move public names, landed together because landing them apart is three
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

Emitted together: semantic names as the real classes, positional names as deprecated aliases,
one snapshot regeneration under review (`test_public_api.py:505-520`'s `repointed` check fires
for every renamed class — intended), one `DeprecationWarning` cycle, one major for removal.

### After, and not part of it

- **One metadata PR upstream:** a `title` for
  `content-standards/get-content-standards-response.json#/oneOf/0`, the single branch the
  rungs cannot name.
- **The nested positional names** (~1045) stay. The root-branch rungs do not reach them, this
  document has no rule for them (§8), and inventing one would be the third rewrite. They are
  ratcheted shrink-only and left alone until a rule exists that is worth one more break.

**For this repo:** the 11 positional imports move exactly once, after the change, in one
commit. Not before — switching early is the base-class change without the decision behind it.

---

## 5. Guards: keep, replace, delete

The first version implied most of these were worthless. Three of them are load-bearing and the
ones that actually pin the wrongness were not on its list.

| guard | verdict | why |
|---|---|---|
| `run_datamodel_codegen.py` order patch | **KEEP** | P7. Deleting it first makes `--check` disagree between APFS and ext4 — the bug it fixed. Retire when zero classes are traversal-named. |
| `tests/test_public_api.py` snapshot | **KEEP** | Grades *repointing* — a bare name resolving to a different class by sort order — which a shape gate does not. |
| `make validate-generated` byte compare | **KEEP** | The only proof the committed tree is the generator's output. |
| `post_generate_fixes.py:6454`, `:6449-6453`, `:6408-6411` | **DELETE** | These *are* the positional naming and its defences. The most directly defect-preserving code in the pipeline. |
| `KNOWN_COLLISIONS` (13 at pin) | **REPLACE** then delete | Its comments state the rule 13 times by hand. Derive it; keep `_enforce_every_class_is_reachable` and `test_collision_guard.py`. |
| `scripts/collision_allowlist.json` | **DELETE now** | Dead; referenced only from a doc. |
| `PRESERVE_CANONICAL_URL_REFS` | **REPLACE** | A carve-out, not a guard. Shrink to empty, then fail the build on any surviving remote ref. |
| `stabilize_inlined_core_refs` | **DELETE** after Stage 6 | Exists only because of remote refs. |
| `stabilize_nested_discriminators` | **KEEP** | Unrelated to refs — it drops a flattened duplicate discriminator pydantic rejects at import. |
| `_eager.py:1097-1098` synonyms | **DELETE** via staging | Mislabelled at birth; still a compat surface. |
| 98 `TypeAlias` annotations | **DELETE** | §3.4. |
| `test_asset_aliases_stable.py`, `test_collision_aliases.py` | **KEEP** | The P4 precedent already in the tree. |
| `test_lazy_types.py::test_partial_modules_avoid_numbered_codegen_names` | **KEEP, widen** | The one existing refusal of positional names. |
| `post_generation_manifest.json` | **KEEP** | A fix that fires nothing fails the run. |
| `test_union_branch_names.py` equality counts | **KEEP** | They move when the emitter is rewired. That is the point. |

**Churn versus correctness.** The positional→semantic rename of response arms is *required* by
P1, so it beats the emitter sites that defend the numbering. Re-exporting `Warning` on
`adcp.types` is ergonomics and P6 argues against it — it loses. Switching salesagent's four
"switchable" imports is neither: it is a layering decision, and the layer comes first.

---

## 6. What must not change

- Module paths `adcp.types.domains.<domain>.<schema_stem>`, and every class already named by
  its schema title (`CreateMediaBuyRequest`, `Product`, `Warning`, …). Semantic arm classes
  are emitted **into the same module**, never moved.
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

## 7. What the first version of this document got wrong

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
12. **A seven-stage plan.** Three separate public breaks, each with its own deprecation window
    and adopter churn — the repeated-rewrite pattern this work exists to end, proposed as the
    way to end it. §4 is now one change.

---

## 8. Not established

- Whether `branch_classes`' emitter is wired for all eleven split roots or only some — its
  test docstring says "not wired into the generation pipeline", yet the wheel carries the
  split classes for `create-media-buy-request`.
- Whether the 98 `TypeAlias` annotations were deliberate. No rule or comment found.
- A nested-class naming rule. The root-branch rungs do not reach the ~1045 nested positional
  names, and this document has no mechanism for them.
- The scope of the `allOf`+`enum` narrowing loss beyond one field (§3.3).
- The generator condition behind the sibling-document `allOf` re-derivation.
- Whether `Warning`'s absence from `adcp.types.__all__` is builtin-shadowing policy or an
  omission (P6 wants it to be policy either way).
- Whether each of this repo's positional use sites needs a base class or only a type position.
- Whether the TS SDK validates at runtime as Python does; the Zod layer was not examined.
- Go and Java SDKs.

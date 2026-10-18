# SDK type generation: what is wrong, and how it should work

**Status:** design, not yet implemented. Written 2026-10-18.
**Subject:** the `adcp` Python SDK's generated type surface, measured at pin
`9.0.0b3+sa.8qela.f33d4fc71` (AdCP 3.2.3).
**Reference implementation:** `adcontextprotocol/adcp-client` (`@adcp/sdk` 16.0.0-beta.8),
which solves four of the five problems below and is worth copying on each of them.

Every claim here is followed by the command, file or line it came from. Where something was
not established, it says so instead of guessing.

---

## 1. The verdict

The Python SDK's public type surface is **named by traversal order rather than by the
schema**, and that single property causes or hides every other defect in this document. The
numbering is sparse — `Assets29` exists, `Assets30` does not, `Assets94` does — so the number
is an artifact of generation order, not an identity.

Two counts, because two instruments were used and neither is wrong:

```
1077  across 240 stems   live attribute walk of adcp.types.*  (undercounts: 198 of the
                                                               lazy-resolution paths raise)
1798  excluding bundled/ AST over the generated files         (1893 including the mirror)
1014  of those are in some package __all__; 879 are reachable only by deep module path
```

Deep paths are not a safety barrier — this repo reaches 5 of its 11 that way — so the exposed
surface is the whole 1798, not the 29 that reach `adcp` / `adcp.types`.

The TypeScript SDK generates from the *same schemas* and does not have this problem, because
`json-schema-to-typescript` uses a subschema's `title` as its type name by default. The
Python pipeline passes eleven flags to `datamodel-code-generator` and `--use-title-as-name`
is not among them (`scripts/generate_types.py:1119-1165`).

This was known upstream and frozen rather than fixed. `scripts/run_datamodel_codegen.py`
exists only to monkeypatch `pathlib.Path.rglob` so traversal order is total, and its docstring
says why: "the anonymous variant classes the generator numbers by traversal (`Result9` versus
`Result13`) then differ between a developer machine and CI" — and the ordering was chosen "so
the numbering adopters already see stays put." The instability was pinned in place; the cause
was left.

**The cost is not developer experience. It is silent wrongness.** Two instances are already
in shipped code, below.

---

## 2. What is broken, measured

### 2.1 Positional names, and the two live bugs they have already caused

The arms of `media-buy/create-media-buy-response.json` carry the titles
`CreateMediaBuySuccess`, `CreateMediaBuyError`, `CreateMediaBuySubmitted` — already valid
PascalCase identifiers. The generator ignores them and emits `CreateMediaBuyResponse1/2/3`.
Reproduced both ways on a three-arm minimal schema: without the flag, positional names; with
`--use-title-as-name`, the three semantic names.

**Live bug 1 — four of the SDK's own exported aliases are wrong today.**
`adcp/types/aliases.py` hand-maintains 154 semantic names over positional classes.
`core/activation-key.json` has exactly two arms. The SDK exports four names over them:

| exported name | resolves to arm | fields that arm actually has |
|---|---|---|
| `PropertyIdActivationKey` | arm 1 | `type`, `segment_id` |
| `SegmentIdActivationKey` | arm 1 | `type`, `segment_id` |
| `KeyValueActivationKey` | arm 2 | `type`, `key`, `value` |
| `PropertyTagActivationKey` | arm 2 | `type`, `key`, `value` |

Two exported names per arm, and the arms are positionally named, so the table has four
entries over a two-arm schema.

`PropertyIdActivationKey` promises a property-id shape and delivers `segment_id`. These read
as leftovers from a spec version with four arms, never updated when the schema shrank to two.
The public-API snapshot keeps them green, because it gates on name →`module:QualName` and a
reorder changes neither.

**Live bug 2 — this repo is one reorder away from a silent semantic swap.**
`src/core/tools/creatives/listing.py:10-11`:

```python
from adcp.types.domains.core.creative_item import CreativeItem1 as MediaItem
from adcp.types.domains.core.creative_item import CreativeItem2 as TextItem
```

```
CreativeItem1  ['asset_id','asset_kind','asset_type','content_uri']   media, correct today
CreativeItem2  ['asset_id','asset_kind','asset_type','content']       text,  correct today
core/creative-item.json   arm[0] title=None   arm[1] title=None
```

The two arms differ by exactly one field. A reorder makes `MediaItem` the text shape with no
type error and nothing red. Both arms are **untitled**, so no amount of title-based renaming
fixes this one — only a field-shape gate can.

**And it must key on field NAME SETS, not field counts.** Both arms have four fields, four
required, and share three of the four names; the symmetric difference is
`{'content', 'content_uri'}`. A snapshot keyed on class name plus field *count* — which is the
obvious-sounding design, and was the first sketch of this gate — ships this swap green. The
instrument that is right already exists; the one that sounds equivalent is the trap.

**The flag alone is not the fix, and claiming otherwise would be wrong.** Of the root-level
arms at 3.2 (excluding the `bundled/` and `mcp/` mirrors) 142 have PascalCase-identifier
titles, 88 have prose titles, and **327 have no title at all**. `--use-title-as-name` is
global: it also renames nested anonymous classes, and for prose titles it emits *unprefixed*
names — a repro turned `CreateMediaBuyRequest1/2/3` into a bare
`ExplicitPackagesWithFixedAllocation`, and the bundle has prose arm titles like `fixed`,
`none` and `Dataset` that would collide across 240 stems.

Measured clean scope for a title-based rename: **78 positional classes across 34 files**, of
which 26 files / 58 classes rename with zero collision. The 8 collisions are `*Submitted`
arms colliding with the class generated from the separate async-response-submitted file, a
case the repo already tools for.

### 2.2 The alias surface is split between two declaration forms, and the split has no rule

`aliases.py` declares 234 semantic names in two different ways, measured by AST:

```
plain assignments  (X = Y)            136
annotated          (X: TypeAlias = Y)  98
```

Only one form can be inherited from. Proven against this repo's own mypy config:

```python
class FromPlainAssignment(CreateMediaBuySuccessResponse): pass   # no error
class FromTypeAlias(UpdateMediaBuySuccessResponse): pass
# error: Invalid base class "UpdateMediaBuySuccessResponse"  [misc]
```

So **98 of 234 semantic names are unusable as base classes**, and nothing separates them from
the 136 that are: `CreateMediaBuySuccessResponse` and `UpdateMediaBuySuccessResponse` have
identical roles and are declared two different ways. A consumer that subclasses — as this repo
must, to attach `WireSerializerMixin` — cannot predict which form it will get. **This is a
third independent defect, and the cheapest fix in this document: drop the annotation.**

This repo records the consequence at `src/core/schemas/_base.py:125-131`:

> The concrete class, NOT `adcp.types.aliases.LegacyUpdateMediaBuySuccessResponse`. That
> alias is declared `X: TypeAlias = UpdateMediaBuyResponse1`, and mypy refuses an explicit
> TypeAlias as a base class ("Invalid base class") even though it is a plain class at
> runtime.

That note is correct about the name it cites and **over-generalises**: the name it names is
annotated, but `_base.py:108` is on the other side of the split. Mapping this repo's 11
positional imports against both forms:

| positional class | arm title | plain alias (inheritable) | annotated only |
|---|---|---|---|
| `CreateMediaBuyResponse1` | `CreateMediaBuySuccess` | `CreateMediaBuySuccessResponse` | — |
| `CreateMediaBuyResponse2` | `CreateMediaBuyError` | `CreateMediaBuyErrorResponse` | — |
| `CreateMediaBuyResponse3` | `CreateMediaBuySubmitted` | `CreateMediaBuySubmittedResponse` | — |
| `UpdateMediaBuyResponse1` | `UpdateMediaBuySuccess` | — | `UpdateMediaBuySuccessResponse` |
| `UpdateMediaBuyResponse3` | `UpdateMediaBuySubmitted` | — | `UpdateMediaBuySubmittedResponse` |
| `SyncCreativesResponse1` | `SyncCreativesSuccess` | — | `SyncCreativesSuccessResponse` |
| `AccountReference1` | **none** | `AccountReferenceById` | — |
| `Accounts1` | not resolved | — | — |
| `BrandDiscovery3` | not resolved | — | — |
| `CreativeItem1` | **none** | — | — |
| `CreativeItem2` | **none** | — | — |

Four could switch today; three are blocked *only* by the annotation.

**And one row argues against the whole title-based framing.** `AccountReference1` has a
semantic alias despite its arm being **untitled** — so the hand-maintained table already
reaches further than any title-driven rename can. Titles are not the limiting mechanism, which
is why the gate outranks the rename in §5.

**The direction of the rename is fixed by this:** the semantic name must be the real class and
the positional name the alias, never the reverse. An alias-only rename leaves every
subclassing consumer pinned to positional names permanently.

### 2.3 A remote `$ref` is resolved as a copy, orphaning the canonical class

This is the mechanism behind the duplication, demonstrated on a three-file tree with
production's flag set and a mirror laid out the way `generate_types.py` does it:

```python
# remote $ref + --allow-remote-refs --http-local-ref-path
# out/core/c.py
class SharedThing(BaseModel): ...     # canonical -- and NOTHING references it
# out/media/a_property_ref.py
class C(BaseModel): ...               # a fresh COPY, named from the ref's URL stem
class APropertyRef(BaseModel):
    thing: C
# out/media/b_allof_ref.py
from .a_property_ref import C         # --reuse-model anchored on the COPY
class BAllofRef(C): pass
```

```python
# the same tree with local relative $refs and the flag off
from ..core import c
class APropertyRef(BaseModel):
    thing: c.SharedThing              # the CANONICAL class. zero duplication.
```

So `--reuse-model` is not broken — it prevents N copies by anchoring later referrers on the
*first* copy, which is why the counts look healthy while the canonical class goes unused.

**The pre-pass that fixes this already exists.** `rewrite_refs` at `generate_types.py:503`
rewrites canonical `/schemas/<ver>/...` URLs to relative paths before generation, which is
why production mostly *does* reuse — `accept_proposal_response.py` really does contain
`from ..core.warning import Warning as Warning_1`. The work is not to add a pass; it is to
**shrink the carve-outs in the one that is there**: `PRESERVE_CANONICAL_URL_REFS` (3 paths —
`core/assets/asset-union.json`, `core/assets/card-asset.json`, `core/macro-declaration.json`),
macro refs deliberately forced to absolute temp-dir paths, and the two compensating passes
(`stabilize_inlined_core_refs`, `stabilize_nested_discriminators`) that exist because the
generator "resolves refs nested inside an `allOf` target against the caller's directory."

Reuse does work at scale where the rewrite applies:

| core schema | `$ref`'d by | generated definitions |
|---|---|---|
| `core/ext.json` | 326 | 2 |
| `core/error.json` | 83 | 5 |
| `core/protocol-envelope.json` | 78 | 1 |
| `core/brand-ref.json` | 52 | 1 |
| `core/provenance.json` | 23 | 5 |

**Residual, cause not established:** a root-level `allOf` alias of a *same-directory sibling
document* re-derives that document's classes instead of importing them.
`accept_proposal_response.py` and `buy_products_response.py` each `$ref` only
`media-buy/media-buy-commitment-response.json`, import nothing from it, and re-generate
`ProposalStatus`, `PurchaseBinding`, `Code`, the `Warning` narrowing subclass and
`AcceptedProposal` — 12 classes each against the sibling's 8. A minimal repro with a
plain-object target inherited cleanly, so the trigger is probably the target's own `oneOf`
needing re-expansion per arm. Not confirmed.

### 2.4 One bare name, unrelated types — and nothing checks it

Counting model classes by full annotation text across the generated tree: **8207 distinct
model names, 2216 defined in more than one module, 809 of those with a differing declaration
under one name.** Enums: 672 names, 221 multi-module, 55 differing.

Worst offenders, and they are not error- or warning-related:

```
Creative        9 modules, 8 distinct shapes
Account         8 / 8
Scope          14 / 6
Identifier      8 / 6
Authentication  8 / 6
Metric          9 / 6
Source         11 / 5
Location       14 / 4
```

`Error` is a smaller but sharper case, because unlike `Warning` **none** of its duplicates
subclass the canonical class. The cause is not reuse: `protocol/get-task-status-response.json`
and `core/tasks-get-response.json` each declare an inline anonymous
`properties.error = {"type":"object", ...}` described as a "Convenience summary for failed
tasks" — a genuinely distinct spec shape, correctly generated as a distinct class. **The
defect is that the generator named it `Error` from the property name**, colliding with
`core/error.json`'s type. Same family as positional naming: a name derived from position in
the document rather than from the schema's own identity.

`scripts/collision_allowlist.json` is dead — its `_comment` describes a `generated_poc` path
that no longer exists, and it is referenced only from `docs/design/type-generation.md`. The
live table is `KNOWN_COLLISIONS` in `consolidate_exports.py`, 14 names. The two build guards
check that every public class is reachable under some name and that no two `(name, module)`
pairs want the same qualified name. **Neither checks shape compatibility**, so nothing knows
about the 809.

### 2.5 An `allOf` enum narrowing is silently lost

`media-buy-commitment-response.json` narrows `warnings[].code` to two members. The generated
model accepts a third:

```
payload code='fields_ignored_due_to_precedence'
  jsonschema on warnings[].items        REJECTS
  Warning.model_validate (same bytes)   ACCEPTS
```

The `allOf` merge **unioned** the vocabularies instead of intersecting them, and the emitted
enum carries the tell — aliased duplicates:

```python
class Code(StrEnum):
    inventory_shortfall_forecast      = 'inventory_shortfall_forecast'
    flight_change_creates_pacing_risk = 'flight_change_creates_pacing_risk'
    fields_ignored_due_to_precedence  = 'fields_ignored_due_to_precedence'   # schema forbids
    inventory_shortfall_forecast_1    = 'inventory_shortfall_forecast'       # alias
    flight_change_creates_pacing_risk_1 = 'flight_change_creates_pacing_risk'
```

This is exactly the failure `generate_types.py`'s own `--strict-types` rationale says the
flags exist to prevent: that the model's accepted set *is* the schema's accepted set, "or the
two validators the SDK ships disagree about the same bytes."

The `const` case is correct — `control_media_buy_response.Warning.code` is
`Literal['inventory_shortfall_forecast']` and rejects the same payload. So the defect is
specific to `enum` narrowing. TypeScript preserves both, including the two-member case, via
`warnings?: (Warning & { code?: 'a' | 'b' })[]`.

**Scope not established.** Demonstrated on one field. Nobody has swept the tree for other
`allOf` + `enum` narrowing sites, and that sweep is a prerequisite for calling this fixed.

### 2.6 The export surface is hand-written at the top

The derived layers are correct. `consolidate_exports.py` builds `_generated.py` and the
domain roots from the module tree, and the canonical `core.warning.Warning` won the bare slot:

```
Warning      adcp=False  types=False  _generated=True   -> adcp.types.domains.core.warning
WarningCode  adcp=False  types=False  _generated=True   -> adcp.types.domains.enums.warning_code
Error        adcp=True   types=True   _generated=False
_generated.__all__   ['Warning','WarningAffectedResource','WarningCode']
adcp.types.__all__   []
```

The break is the layer above: `adcp/types/__init__.py` (2257 lines) and `adcp/__init__.py`
(2569 lines) are **hand-written**, with explicit per-name imports and no generated marker.
`Warning` and `WarningCode` were simply never added. No exclusion rule was found; builtin
shadowing is a plausible motive and is **not established**.

The pattern across 2.1, 2.2 and 2.6 is one pattern: **the derived machinery is sound and
every hand-maintained layer on top of it has drifted.**

---

## 3. The reference implementation, and where not to copy it

`json-schema-to-typescript` gets the naming right by default, and `adcp-client` defends it:
`scripts/generate-types.ts:708-711` preserves branch titles through schema preprocessing, and
`npm run ci:codegen-strict` (`scripts/check-no-loose-oneof.ts`) fails the build when a `oneOf`
arm collapses to a bare index signature. The output:

```ts
} & (CreateMediaBuySuccess | CreateMediaBuyError | CreateMediaBuySubmitted);
export interface CreateMediaBuySuccess { ...
export type Warning = { } & { code: WarningCode; message: string;
                              affected_resource: WarningAffectedResource; ... };
warnings?: (Warning & { code?: 'inventory_shortfall_forecast' })[];
```

Four mechanisms worth copying: **the arm title becomes the type name**; **a `$ref` becomes a
reference to a named type, never a copy**; **a narrowing is expressed as an intersection that
preserves the base type**; and **a CI gate refuses a degraded arm**.

**Do not copy these.** TS has its own defects, measured:

- 47 numbered declarations of its own (`BrandReference1..12`, `MacroBearingURL1..8`,
  `DeliveryForecast1/2`) — the same defect, roughly 23× smaller, not absent.
- `Warning` and `Error` are **not exported** from `src/lib/types/index.ts`,
  `src/lib/index.ts` or `src/lib/types/adcp.ts`. Identical gap to Python; the export problem
  is not Python-only and this document should not claim it is.
- `enums.generated.ts` is 237 `export const` and 0 `export type`, so an adopter gets the
  vocabulary as a runtime array and never gets the union type.
- `export interface Error` shadows the JS global in type position. Latent only because it
  is unexported — fixing the export gap without renaming ships the footgun.
- `details?: {}` (the empty object type) is weaker than Python's `dict[str, Any] | None` for
  a field whose schema is `additionalProperties: true`.

---

## 4. The design

Five rules. Each is stated so a build can refuse a violation, because a rule nothing enforces
is how this surface got here.

**R1 — A public name comes from the schema, never from traversal order.** Resolution order:
the file's root `title`; else the subschema's own `title`; else a name derived from the
schema's *path* (`CreativeItemContentUri`), which is stable under reordering because it names
the shape rather than the position. A trailing-digit name is a **build failure**, not a
fallback. Until R5 lands, the failure is a shrink-only ratchet with today's 1077 as the
ceiling.

**R2 — A `$ref` is a reference, not a copy.** Generation runs on a tree whose refs are all
local and relative; a remote `$ref` surviving into the generator is a build failure. This
means `PRESERVE_CANONICAL_URL_REFS` shrinks to empty, and the two `stabilize_*` passes become
unnecessary rather than load-bearing.

**R3 — A narrowing intersects.** An `allOf` that narrows an `enum` produces the
intersection. A generated vocabulary that is larger than the schema's, or that contains
`_N`-suffixed aliases of its own members, is a build failure. The invariant to assert
directly: for every generated model, the set it accepts equals the set `jsonschema` accepts
for the same node.

**R4 — Every public name is derived.** No hand-maintained alias table, no hand-written
`__init__`. `aliases.py`, `adcp/types/__init__.py` and `adcp/__init__.py` become generated
from the module tree, with the semantic name as the **real class** and the positional name as
a deprecated alias (R2 of §2.2: never the reverse, or subclassing consumers stay stuck).

**R5 — Identity is the field shape, not the name.** The regeneration gate compares per-class
**field name sets** — not names alone, and specifically not field counts, which §2.1 shows
would miss the live case. This is the only rule that covers the 327 untitled arms and the only
one that would have caught either live bug.

**R6 — One declaration form.** A generated alias is a plain assignment, never
`X: TypeAlias = Y`, so every public name can be inherited from. §2.2 shows 98 of 234 names
currently cannot, with no rule separating them.

---

## 5. Implementation sequence

Ordered so that each stage is measurable by the stage before it. Stage 0 first is not a
preference: without it, no later stage can be shown not to have changed behaviour.

**Stage 0 — the field-name-set gate (R5).** `scripts/diff_generated_types.py` already AST-walks
the tree and returns `{path: {ClassName: [field_name, ...]}}`; `generate_types.py:1609-1616`
writes it to `SCHEMA_DELTAS.md` and returns 0. Commit that snapshot as a fixture beside
`public_api_snapshot.json` and assert it in the same test module. A reorder then fails with
"`CreativeItem1` lost `content_uri`, gained `content`". **Key it on name sets, not counts.**
*Largest coverage — all 1798 regardless of titles — no behaviour change, nothing else depends
on it, and it is the only item that would have caught either live bug.*

**Stage 1 — drop the `: TypeAlias` annotations (R6).** 98 names, no rename, no behaviour
change, no schema involvement: the declaration form changes and the names become inheritable.
Unblocks `_base.py:131`, `:134` and `creative.py:36` in this repo immediately. *Cheapest item
in the document and independent of every other stage — it could ship first if Stage 0 slips.*

**Stage 2 — the narrowing intersect (R3).** First sweep the tree for every `allOf` + `enum`
narrowing site, because the one known instance is a sample and the scope is unestablished.
Then fix the merge to intersect, and assert the model-accepts-iff-schema-accepts invariant
over the found sites. *This is a correctness fix shipping a wrong accepted set today; it is
independent of all naming work.*

**Stage 3 — semantic arm classes (R1).** Emit the arm `title` as the class name where it is a
PascalCase identifier and does not collide — the measured 78 classes across 34 files — with
the positional name as an alias. Extend the existing post-generate pass
(`post_generate_fixes.py`, whose `_schema_title_to_class_name` at line 743 already does the
transform) rather than flipping the global flag, for the reasons in §2.1. Then fix the
property-name-derived collisions from §2.4 (`Error` from `properties.error`) by deriving from
the schema path instead.

**Stage 4 — derive the export surface (R4).** Generate `aliases.py` and both `__init__.py`
files. This is what retires the four wrong `ActivationKey` aliases permanently instead of
correcting them once.

**Stage 5 — upstream the titles, then close the loop.** File the 327 untitled root-level arms
against `adcontextprotocol/adcp`; no generator change can name them.
`core/creative-item.json`'s two arms are the first candidate — a URI-versus-inline-content
pair with obvious names, and the pair §2.1's live bug sits on. When titles exist, flip R1's
ratchet to a hard build failure.

**Stage 6 — local refs only (R2).** Shrink `PRESERVE_CANONICAL_URL_REFS` one entry at a time,
each time checking whether the `stabilize_*` compensation is still needed. Then establish the
sibling-document `allOf` trigger from §2.3 and either extend `rewrite_refs` to cover
root-level sibling refs or special-case the pure-alias shape to a module-level re-export.
Stage 0 measures this: duplicate class definitions should fall and no field set should change.
*Last deliberately: this is bloat plus an `isinstance` hazard, it carries no silent-swap risk,
and it touches no downstream name.*

**Breaking-change staging.** Removing `CreateMediaBuyResponse1` is breaking. Minor N emits the
semantic name and keeps the positional one as an alias listed in the public API snapshot, so
no adopter breaks and both resolve to the same class. Minor N+1 adds a `DeprecationWarning`
on the positional name. A major removes it. Blast radius upstream: `aliases.py`, `_eager.py`,
`legacy.py`, `consolidate_exports.py`, the snapshot fixture, `SCHEMA_DELTAS.md`. Downstream in
this repo: the 11 imports in §2.2.

**Do not switch this repo's four switchable imports before Stage 0.** They *can* switch today
— the `create_media_buy` trio plus `AccountReference1` are plain assignments — but a
hand-maintained alias buys no drift protection, and §2.1 shows that table has already drifted.
Switching early trades a name that is honestly positional for one that reads semantic and is
equally unguarded. After Stage 0, switch all eleven; `listing.py:10-11` is the pair the gate
exists to protect.

---

## 6. The adjacent spec finding, recorded here because it is the same root cause

The `oneOf` split that produced the positional names also produced a channel the protocol
cannot use. `error.code` is wire-typed `string` with a 120-code *documentary* registry, a
`recovery` field, and `Error.model_validate` **accepts** an unregistered code. `warning.code`
is a `$ref` to a 3-member enum whose own description says "Closed warning vocabulary", has no
`recovery` field, and `Warning.model_validate` **rejects** an unregistered code. `details` and
`ext` can carry an observation and are explicitly non-portable — `warning.json` says "buyers
MUST NOT require portable keys inside `details`".

So there is no way to express "the buyer requested a capability I persist but cannot honour."
Upstream #4248 — the RFC that created this channel, filed from this repo — proposed
`warnings: list[Error]` precisely so codes came from the open registry; a new closed 3-member
vocabulary shipped instead. Upstream #6978 is this exact condition for targeting dimensions,
closed 2026-10-09 with experts split and status "ready-for-human", and framed throughout as an
**error**.

Consequence for this repo, decided but not yet implemented: `create_media_buy` and
`update_media_buy` currently attach an `UNSUPPORTED_FEATURE` **error** to a **success**
response, which `core/targeting.json`'s "MUST be applied exactly or rejected" forbids. The
fix is to raise it. Five call sites, one helper
(`property_list_unsupported_advisories`), and the refusal object already exists. Deferred:
it changes buyer-visible outcomes in two tools and is not this document's subject.

---

## 7. Not established

- Whether omitting `--use-title-as-name` was deliberate. Every other flag in
  `generate_types.py` carries a rationale comment; this one has no comment either way.
- Whether the 98 `TypeAlias` annotations were deliberate. No rule or comment was found
  separating them from the 136 plain assignments.
- What `Accounts1` and `BrandDiscovery3` correspond to in the schema bundle. The stem→schema
  mapping did not resolve them, so their arm titles are unknown and whether Stage 3 reaches
  them is undetermined.
- Whether each of the four switchable use sites in this repo needs a base class or only a type
  position. The declaration *form* was shown to permit inheritance; the use sites were not
  audited individually.
- The exact generator condition that makes a root-level sibling-document `allOf` alias
  re-derive rather than import (§2.3).
- Whether the three `PRESERVE_CANONICAL_URL_REFS` entries still need to be carve-outs
  against the current generator version.
- Whether the `enum`-narrowing loss affects fields beyond `warnings[].code` (§2.5). One site
  demonstrated; no sweep run.
- Why `Warning`/`WarningCode` are absent from the two hand-written `__init__` files.
- Whether `code` requiredness is actually lost on the four `Warning` subclasses —
  `is_required()` reports False, but no missing-`code` payload got past validation, so which
  mechanism refuses it is unknown.
- Whether the four `ActivationKey` aliases are drift or an intentional convenience. The
  field/name mismatch is measured; the intent is not.
- Whether the TS SDK validates at runtime the way Python does. Its emitted types were read,
  not a validator; the Zod layer (`generate-zod-from-ts.ts`) was not examined.
- The Go and Java SDKs were not examined.

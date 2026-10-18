# SDK type generation: the principles it is missing

**Status:** design. Rewritten 2026-10-18 after a review refuted the first version's central
claim, then audited again the same night against the installed wheel; that audit removed the
namespace flattening from the plan and corrected the `extra=` paragraph. What each earlier
version got wrong is recorded in §8, because the wrong story is still the intuitive one and
will be proposed again. §1.1 says which claims are measured and which are inherited.

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
keyed on a name. Of the ten principles below the TypeScript SDK holds P2, P6 and P8, fails P4
and P5, and holds P1 only for titled arms; it is a reference for specific mechanisms, not a
model to copy wholesale — and §3.1 names the axes where Python is built to exceed it.

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

### 1.1 What is measured, and what is inherited

This document has been wrong five times in one night. A reader deciding whether to act on it
needs to know which claims were measured against the wheel and which are text carried forward
from a draft. The list is short on purpose; everything not on it is either a principle (an
argument, not a measurement) or marked "not established" in §9.

| claim | replaced | established by |
|---|---|---|
| Response-arm numbering is one line of this repo's emitter, `post_generate_fixes.py:6454` (pin), defended at `:6449-6453` and `:6408-6411` | "the cause is the missing `--use-title-as-name`" | the three lines read at `f33d4fc71`; re-verified in the audit |
| The rungs name 556 of 557 root branches; one is unnameable | "327 untitled arms no generator can name" | `tests/test_union_branch_names.py:66-73` (pin), equality over the bundle |
| `adcp.types.<SemanticName>` binds to a `canonical_creative` subclass of the generated arm, for every canonical name (`Product`, `Format`, `Package`, `CreateMediaBuyRequest`, `CreateMediaBuySuccessResponse`, …) | "four of our imports could switch today" | `__module__` of each name in salesagent's venv (pin) |
| The generator already derives `extra` from `additionalProperties`: `extra='forbid'` at 1002 sites and `extra='allow'` at 1187 in the non-bundled domain modules; the bundle has 256 root-level `additionalProperties: false` | "`AdCPBaseModel`'s `extra="ignore"` is a live P3 violation" (rev 5) | `grep` over `adcp/types/domains` and the 3.2 bundle; `types/base.py:316-320` (pin) states the rule |
| `adcp.types.media_buy`, `.creative`, `.signals`, `.protocol`, `.core`, `.error_details` already exist as hand-written modules, four of them the curated partials guarded by `tests/test_lazy_types.py` | "flatten to `adcp.types.<domain>.<Class>`" (rev 5) | `ls adcp/types/*.py` (pin); `_PARTIAL_MODULES` at `types/__init__.py:1086` |
| 335 class names are declared in more than one module of the same domain, 145 with differing shapes; the generated domain root binds only once-declared names | the depth table alone | AST walk over `adcp/types/domains` (pin); `domains/core/__init__.py` docstring |
| This repo has 108 `from adcp.types.domains…` statements in 33 `src/` files, 124 names, 16 of them multiply-declared in their domain | "five of this repo's eleven deep imports" | AST walk over `src/` |
| The import path already moved once this major: `adcp.types.generated_poc` → `adcp.types.domains`, codemod shipped 2026-04-20 | not mentioned | `adcp/migrate/v3_to_v4.py` (pin); `types/__init__.py` docstring, removal in v10 |
| The success arm of `create-media-buy-response` and `update-media-buy-response` has **no** `status` const; only the submitted arm does | "detect the success arm from the schema's `status` const" (rev 3) | the two schema files in the 3.2 bundle |
| The rung module's `pascal_case` and the generator's `generated_root_class_name` disagree on 115 root titles; 5 roots get a branch prefix that does not match their generated base class | item 1 named one function and the rungs use the other | both functions run over the bundle from the pin's venv |
| `emit_branch_classes` is wired (`post_generate_fixes.py:8778`, fix list `:9174`) and 19 generated roots (12 exported on `adcp.types`) dispatch at runtime through `BranchDispatchMixin`; `CreateMediaBuyResponse` is a plain union and does not | "not wired" (`tests/test_branch_classes.py:11`, stale) | the fix list at the pin; `_branch_models` declared on 19 classes in the generated tree; probe S11 |
| `CreateMediaBuyErrorResponse` and `CreateMediaBuySubmittedResponse` are in `adcp.types.__all__` | "two of the three arms have no name a caller can import" (rev 4) | `aliases.py:634,637` (pin) |
| The `ActivationKey` names were wrong at birth; two are `_eager.py` synonyms | "drifted from four arms to two" | git archaeology at `5c63decdd` (not re-verified in the audit) |
| The seven-stage plan is replaced by one change | the staged plan | the user's constraint, not a measurement |

Still carried forward without measurement: the P1 nested-family census (206 / 85 / 9) and the
`(ts)` cells of §3, both from the first version. The decisions the plan rests on that are NOT
measurements — the layer choice in §5 item 2, the alias placement in §5 — are stated as
decisions, with their reasons, and §9 names what would still falsify them.

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

Forbids a copy by any route — remote-ref resolution (§4.2) and `create_model` copies alike;
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

**`extra` is part of the accepted set, and the generator already derives it.** The fifth
revision of this document claimed `AdCPBaseModel`'s `extra="ignore"` made every model wider
than a schema declaring `additionalProperties: false`, and called that a live P3 violation. It
is not. The 3.2 bundle declares `additionalProperties: false` on 256 roots and 9729 nodes
(non-bundled), and the generated domain modules carry `extra='forbid'` at 1002 sites and
`extra='allow'` at 1187 — `core/media-buy.json` is `false` and `domains/core/media_buy.py:32`
(pin) is `forbid`; `core/warning.json` is `true` and `domains/core/warning.py` is `allow`.
`types/base.py:316-320` (pin) states the rule. The base class's `ignore` applies only where the
schema says nothing, and there the accepted sets agree (both accept the unknown field; one
retains it and one drops it, which is not a P3 question). So there is no `extra` divergence to
fix and none to exclude — P3's check needs no exclusion list, and §5 no longer carries an
assertion about one.

The consumer-side choice this repo makes — `get_pydantic_extra_mode()` selects `ignore` in
production and `forbid` in development (CLAUDE.md pattern #7) — sits on the consumer's own
subclasses and does not conflict with the derived value on the library class underneath.

**The `extra=` deviation that does exist is this repo's, not the SDK's.** Of the 61
`ConfigDict(extra=…)` sites under `src/`, 43 read `get_pydantic_extra_mode()` and 18 write a
literal: 10 `"forbid"` (`src/adapters/base.py` ×5, `capability_declarations.py` ×2,
`notification.py`, `resolved_identity.py`, `signing/posture.py`) and 8 `"ignore"`
(`src/core/schemas/_base.py` ×7, `config.py`). A literal on a wire model is the one place the
dev/prod split of pattern #7 does not apply, and nothing in the repo says which of the 18 chose
that on purpose; the `_base.py` seven are the serializer mixins every wire model inherits.
That is a salesagent defect to grade in salesagent (a guard over `src/core/schemas` refusing a
literal `extra=` on a wire model), and it is recorded here only so it is not mistaken for the
SDK divergence the fifth revision described. Counted by `grep -rn 'extra=' src/` filtered to
`ConfigDict` / `model_config` lines; the count the review that found this quoted (10 of 48) was
over a different selection and is not the one above.

**TS:** holds at the type level (`warnings?: (Warning & { code?: 'a' | 'b' })[]`). Runtime
not established — the Zod layer was not examined. Structurally the TypeScript SDK cannot hold
P3 as a property of one object: `generate-types` and `generate-zod-schemas`
(`scripts/generate-zod-schemas.ts:4`, `json-schema-to-zod`) are two generators over the same
cache, exported at `.` and `./schemas` `(ts)`, and nothing makes them agree. §3.1 axis A.

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

**The question the first versions could not answer, decided in §5 item 2:** *which class does a
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
**base-class change**, not a rename. This is not special to the media-buy arms: every canonical
name on `adcp.types` (`Product`, `Format`, `Package`, `Creative`, `CreativeAsset`,
`CreateMediaBuyRequest`, `GetProductsResponse`, `UpdateMediaBuySuccessResponse`) resolves to
`adcp.types.canonical_creative` (pin). The pin's rule, never written down, is: the flat
namespace is the canonical layer; the domain path is the wire-faithful class. §5 item 2 writes
it down and keeps it.

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

### P8 — A caller imports by domain; the schema module is the path for a name the domain declares twice

A caller writes `adcp.types.domains.<domain>.<Class>` for a name the domain declares once, and
`adcp.types.domains.<domain>.<schema>.<Class>` for a name it declares more than once. Nothing
deeper, and nothing under an underscore. That is what the pin already does — the generated
domain root (`domains/core/__init__.py`, pin) is a lazy PEP 562 facade binding exactly the
once-declared names, and its docstring sends the rest to the schema module — so P8 is a rule
the build must refuse violations of, not a move.

The fifth revision of this document proposed flattening to `adcp.types.<domain>.<Class>` with
the schema modules made private. The audit refuted it on three measurements:

- **The target is occupied.** `adcp/types/media_buy.py`, `creative.py`, `signals.py`,
  `protocol.py`, `core.py` and `error_details.py` exist at the pin as hand-written modules — six
  of the 26 domain names. Four are the curated partials (`_PARTIAL_MODULES`,
  `types/__init__.py:1086`), whose docstrings say they "never expose the internal generated
  layer" and which `tests/test_lazy_types.py::test_partial_modules_never_import_generated_layer`
  (pin) holds to that. `types/core.py` is 408 lines of hand-written types. The hand modules and
  the generated domains overlap on 33 names in `media_buy`, 47 in `error_details`, 15 in
  `protocol`.
- **Privatising the schema module orphans the names the domain root cannot bind.** 335 class
  names are declared in more than one module of the same domain, 145 with differing shapes
  (`core` 190 / 98; `Location` 14 modules / 4 shapes, `Identifier` 7 / 6, `Authentication`
  6 / 5). Item 4 of §5 collapses the 190 identical-shape duplicates (P2: the same node generated
  twice). The 145 are distinct nodes sharing a bare name, and §5 has no rule for naming nested
  classes by content — so after a flattening they have no public path at all. This repo imports
  16 of them (`Identifier`, `Unit`, `Authentication`, `Creative`, `Account`, `Setup`, `Source`,
  `Provenance`, `Parameters`, `DateRangeSupport`, `MediaBuyDelivery`, `EventType`,
  `NotificationType`, `DeliveryAuth`).
- **The path has already moved once this major.** `adcp.types.generated_poc` →
  `adcp.types.domains`, codemod `adcp migrate v3-to-v4` (pin, SDK commit 32bfbeb88,
  2026-04-20), old path removed in v10. A second move inside the first move's deprecation window
  is the pattern §5 forbids.

So the `domains` token stays. It costs one word per import and buys an uncolliding package for
26 generated domains beside the hand-written ones. The flattening is **rejected, not deferred**:
a later flattening would be the third rewrite, and this document says no to it now so that it
is not proposed as a small follow-up.

Measured depth today, excluding the `bundled/` mirror:

```
  1 level     44 modules
  2 levels    34 modules
  3 levels   962 modules   adcp.types.domains.a2ui.bound_value
  4 levels    57 modules   adcp.types.domains.core.assets.asset_union
  5 levels    39 modules   adcp.types.domains.core.async_response_refs.creative...
```

So the common case is three levels and the worst is five. Under P8 as stated the caller sees
two for a once-declared name and three for the rest, and the four- and five-level modules
(`core/assets/`, `core/async_response_refs/`) are reached only through their domain root or
their schema module — the subdirectory is generation layout and the build refuses an import
that names it:

```
today      adcp.types.domains.core.warning.Warning
           adcp.types.domains.media_buy.create_media_buy_response.CreateMediaBuyResponse1
after §5   adcp.types.domains.core.Warning
           adcp.types.domains.media_buy.CreateMediaBuySuccess          (declared once)
           adcp.types.domains.core.property.Identifier                 (declared 7 times)
```

**Cost:** none to existing imports — every path that resolves today keeps resolving. The
cost is the one that was already paid: a caller who wants the one-level
`import { CreateMediaBuySuccess } from '@adcp/sdk'` form does not get it from Python, because
`adcp.types.CreateMediaBuySuccess` is the canonical layer (§5 item 2) and the domain path is
the wire-faithful one. That is a real difference between the two SDKs and this document stops
pretending it can be closed without a third rewrite.

**The flat loader is a separate, additive item.** `adcp.schemas.load_schema("adcp-agents.json")`
makes a caller name a package, a verb, and a filename with an extension. One accessor at the
root taking a schema name is the ergonomic form; adding it moves no name, so it lands before
the change (§5).

**TS exceeds Python here and keeps doing so:** one level, no domain, no file stem. The
compensating advantages are in §3.1.

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

Nothing in the first version followed from P6 through P10, and its headline thesis followed
from none of them. P10 is also what retires the committed shape fixture the first version put
first: see §5.

---

## 3. The developer-experience requirements

These twelve requirements are normative. A generator change satisfies them or it is not done.
They are not a test artifact bolted on afterwards: each one states a question a caller asks
the SDK, and each failure below is a caller getting the wrong answer or no answer.

`scripts/audit/sdk_dx_probes.py` in the salesagent repository measures the Python column
(probes S1–S8, S11, S12; DX9 and DX10 were measured by hand and are not yet probed). The
TypeScript column is measured statically against `adcp-client` `main` — the generated files
and both root index files — because the two languages share no test harness. A TypeScript cell
reads **n/a** where the requirement is one the language cannot state at runtime, which is the
point of §3.1.

| # | Requirement | Python | TypeScript |
|---|---|---|---|
| DX1 | A caller resolves a tool's request and response types from `<Tool>Request` / `<Tool>Response` | **PASS** 10/10 | **PASS** all five tools |
| DX2 | A caller resolves every arm of a multi-arm response by the arm's own schema title | **FAIL** 0/9 by title (6 reachable under a hand alias with a `Response` suffix) | **PASS** all three arms exported |
| DX3 | The model accepts exactly what the schema accepts | **FAIL** validators disagree | not established at runtime; two generated artifacts (`generate-types`, `generate-zod-schemas`) |
| DX4 | A caller emits an error, including a code the registry does not list | **PASS** | **PASS**, and exceeds Python |
| DX5 | A caller emits a non-blocking observation | **FAIL** | **FAIL** |
| DX6 | A caller extends a response type with their own fields | **FAIL** 98 of 260 | **PASS** by language |
| DX7 | A semantic name resolves to the class the schema describes | **FAIL** | **PASS** |
| DX8 | No positional name appears in the surface a caller imports | **FAIL** 39 + 949 | **PASS** 1 |
| DX9 | A caller imports a type by domain, `adcp.types.domains.<domain>.<Class>`, and reaches a schema module only for a name the domain declares more than once | **PARTIAL** the domain root binds once-declared names today; 335 names (145 after P2) need the schema module; nothing refuses a deeper import | **PASS** 1 level, flat root export — and exceeds Python, see P8 |
| DX10 | Nothing in the SDK names a spec version as a literal | **FAIL** symlink alias | not examined |
| DX11 | A caller validates a document against a root with branches and gets the branch's class back, on every path (`Root(**d)`, `model_validate`, nested, `TypeAdapter`) | **PARTIAL** 19 roots dispatch; the response roots are plain unions with hand guards | **n/a** types are erased; a discriminated union is compile-time and the guard is hand-written |
| DX12 | A refusal names the JSON-Schema keyword that failed, so it can be projected onto `core/error.json`'s `issues[].keyword` without a mapping table | **PARTIAL** `anyOf`/`oneOf` named on the 19 dispatch roots; `missing`, `string_too_short`, … are pydantic's names | **n/a** Zod issues carry Zod codes |

Python satisfies two of twelve outright and three partially; TypeScript satisfies seven, fails
one, leaves two unexamined, and cannot state two. The findings behind each row:

- **DX2.** TypeScript declares `CreateMediaBuySuccess`, `CreateMediaBuyError` and
  `CreateMediaBuySubmitted` as named interfaces and exports all three from
  `src/lib/types/index.ts:162-164`. Python's titles are the same three strings
  (`create-media-buy-response.json` arm titles, pin) and none resolves on `adcp.types`. What
  does resolve is a hand alias per arm with a `Response` suffix —
  `CreateMediaBuySuccessResponse`, `CreateMediaBuyErrorResponse`,
  `CreateMediaBuySubmittedResponse` (`aliases.py:631-637`, pin) — so the failure is "not by
  the schema's own name", not "no name". The fourth revision of this document said the latter;
  §8 item 19.
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
  members in both. The channel cannot express the condition, so the fix is a spec change, not
  a codegen change, and no section of this document plans one.
- **DX6.** A TypeScript interface extends without ceremony. Python's 98 annotated aliases
  cannot serve as a base class, which is §4.4.
- **DX7.** TypeScript's index takes `CreateMediaBuySuccess` from `./tools.generated`, one
  definite projection. Python's semantic alias resolves to a `canonical_creative` subclass
  (§2, P5).
- **DX8.** Exactly one name in a TypeScript root index matches the positional pattern, and it
  is `PreviewRenderV3`, a version suffix rather than a traversal index.

**What this settles.** TypeScript is the reference for DX2, DX4, DX6, DX7 and DX8, and the one
change in §5 is what moves Python onto all five. DX3's sweep lands before that change and its
fix inside it (§5). DX5 is shared, belongs upstream in the schema, and no amount of generator
work reaches it. DX9 TypeScript keeps. DX11 and DX12 are Python's to win, and §3.1 says how.

### 3.1 Where Python exceeds TypeScript, and what the SDK must do to realise it

The body above treats TypeScript as the reference. That is right for five rows and wrong as a
ceiling: a TypeScript type is erased at runtime, and everything the SDK does with a type at
runtime — validate, dispatch, refuse with a reason, extend with the contract intact — is a
separate artifact there and the same object here. The audit tested six candidate axes against
the wheel. Four hold and are design intent; two do not survive and are recorded so nobody
re-proposes them.

**A. One object is the type and the validator (DX3, made a property).** TypeScript ships
`generate-types` and `generate-zod-schemas` as two generators over the same cache, exported at
`.` and `./schemas` `(ts)`; nothing makes their accepted sets agree, and nothing can short of a
third generator comparing them. A pydantic class is one artifact, so "the model accepts
exactly what the schema accepts" can be a property OF THE CLASS rather than a hoped-for
agreement between files. It is not held at the pin — §4.3 is the counterexample — and nothing
grades it: the 19 pin tests that import `jsonschema` are conformance tests of other things.
*What the SDK changes:* the P3 instrument in §5 becomes a per-class property test, `model_validate(x)`
succeeds iff `jsonschema.validate(x, node)` succeeds, over the bundle's 113 root `examples` and
a generated negative per node (one required field removed, one enum value replaced). *How a
caller observes it:* `Model.model_json_schema()` and the bundle node accept the same documents,
so a caller validating with either gets one answer; today they get two.

**B. Runtime branch dispatch, with the refusal naming the combinator (DX11, DX12).** The SDK
already ships this for 19 generated roots, 12 of them exported on `adcp.types`:
`BranchDispatchMixin` (`types/_branch_dispatch.py`, pin) makes
a root with branches validate as the branch the document satisfies on all four paths — direct
construction, `model_validate`, nested field, `TypeAdapter` — and a document satisfying no
branch is refused with `type: 'anyOf'` and the selecting field names in `ctx`
(`_conditions.py:636 name_the_combinator`, pin), which is the keyword `core/error.json`
requires on `issues[]`. Measured: `WebhookChallengeResponse(challenge=…)` returns
`WebhookChallengeResponseChallenge`; `model_validate({"token": …})` returns
`WebhookChallengeResponseToken`; `{"x": 1}` is refused with one `anyOf` error. The response
roots are NOT among the 19: `adcp.types.CreateMediaBuyResponse` is a plain `types.UnionType`
over the three canonical arms, a `TypeAdapter` over it picks an arm by pydantic's smart union
with no keyword on refusal, and the SDK carries ~30 hand-written `TypeGuard`s instead
(`guards.py:176 is_create_media_buy_success`, listed in `_EAGER_ONLY_EXTRAS`, pin) — which is
exactly the TypeScript shape. *What the SDK changes:* §5 item 1 routes the response-arm
emitter through `emit_branch_classes` (`post_generate_fixes.py:8778`, pin, already wired for
partitioning roots), so the response base carries the mixin; the hand guards are then
derivable (`isinstance(r, CreateMediaBuySuccess)`) and are deleted with the other hand tables
in item 3. *How a caller observes it:* `CreateMediaBuyResponse.model_validate(payload)` returns
`CreateMediaBuySuccess`, `CreateMediaBuyError` or `CreateMediaBuySubmitted`, and a payload
matching none is refused with `keyword: oneOf` and the three titles. TypeScript cannot: the
union is compile-time and the guard is a function someone wrote.

**C. A refusal projects onto the spec's error shape without a mapping table (DX12 beyond the
combinators).** `core/error.json` requires `issues[].keyword` to be a JSON-Schema keyword. A
pydantic error carries `type` (`missing`, `string_too_short`, `literal_error`, `enum`), `loc`
and `ctx`; the mapping from those to `required`, `minLength`, `const`, `enum` is finite and
mechanical, and `_conditions.name_the_combinator` and `error_narrowing.narrow_union_errors`
(pin) already do the two hardest cases. Zod issue codes (`invalid_type`, `too_small`) are Zod's
vocabulary, not the schema's, and the TypeScript server maps them by hand. *What the SDK
changes:* one function on `AdCPBaseModel` — `issues_from(exc: ValidationError) -> list[Issue]`
— finishing the projection for every pydantic error type the generated classes can raise,
graded by a test that raises each one and checks the keyword is in the JSON-Schema vocabulary.
*How a caller observes it:* a seller's `INVALID_REQUEST` carries spec-valid `issues[]` from the
model's own refusal, with no table in the seller's code.

**D. A subclass inherits the parent's validators, and that is graded (DX6, strengthened).**
A TypeScript `interface X extends Y` carries Y's fields and none of Y's runtime checks, because
Y has none. `tests/test_canonical_models_are_subclasses.py` (pin) grades that every canonical
model inherits every `model_validator` of its generated parent — a property the language can
state and TypeScript cannot. It is undercut today by the 98 `TypeAlias` annotations (§4.4),
which make a public name un-subclassable. *What the SDK changes:* §5 item 3 drops the
annotations; the subclass test stays and widens to every public name. *How a caller observes
it:* `class MyProduct(adcp.types.Product)` validates as `Product` does and adds fields, with
`mypy` clean. The §3 table marks the TypeScript cell "by language"; counting validators it is
the weaker of the two.

**Discarded.** *Behaviour on the error type* (`Error.is_standard`, `Error.recovery` as
methods): `adcp.types.Error` has no public method of its own and `ErrorCode` is a closed
120-member `StrEnum` with no metadata (pin); the TypeScript helpers exist in Python already,
server-side and off the type (`adcp.server.helpers.STANDARD_ERROR_CODES:145`,
`adcp.server.translate._recovery_for_code:97`, pin). Moving them onto the class is a small
ergonomic gain, not an inherent advantage — DX4's verdict stands and TypeScript's shape is the
one to adopt. *`__init_subclass__`*: used nowhere in `adcp/types/*.py` (pin) and no caller-
visible requirement follows from it.

---

## 4. The defects, as consequences

### 4.1 Positional names, and the live swap

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

### 4.2 A remote `$ref` is resolved as a copy

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

### 4.3 An `allOf` enum narrowing is lost — P3 violated

`media-buy-commitment-response.json` narrows `warnings[].code` to two members; the generated
model accepts a third. `jsonschema` rejects the payload, `model_validate` accepts it. The
merge **unioned** the vocabularies and left `_1`-suffixed aliases of its own members as the
tell. The `const` case is correct, so the defect is specific to `enum`. **Scope not
established** — one site demonstrated, no sweep run, and the sweep is a prerequisite.

### 4.4 Two declaration forms for one kind of name

`aliases.py` (pin): 136 plain assignments, 98 annotated `X: TypeAlias = Y`. Only the plain
form can be inherited from (`Invalid base class [misc]`). 92 of the 98 resolve to a class and
6 to unions, which are uninheritable in any form. No rule separates the groups:
`CreateMediaBuySuccessResponse` and `UpdateMediaBuySuccessResponse` have identical roles and
are declared two different ways. **Dropping the annotation is the cheapest item here.**

### 4.5 The `ActivationKey` names were wrong on day one

Two of them are not in `aliases.py` at all — `_eager.py:1097-1098` (pin) declares
`PropertyIdActivationKey = SegmentIdActivationKey` and
`PropertyTagActivationKey = KeyValueActivationKey` as **synonyms**. And they were never
correct: at `5c63decdd` (#47, 2025-11-16) `aliases.py:143` already bound the property-id name
to the *first positional arm*, with the docstring "using property_id for identification",
while the activation-key schema at that same commit already had two arms — segment-id and
key-value.

So the first version's story — drift from a four-arm schema — is wrong. They are compat
synonyms that were mislabelled at birth, which means they leave through the deprecation
staging in §5, not silently.

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

The audit of the fifth revision tested whether its six items could land together. One could not
land at all (the namespace flattening — P8 records why, and it is out), one moved a public name
while labelled additive (the narrowing fix, now inside the change), one described a fix the pin
already has (`extra=`, now nothing), two had unstated dependencies that are now stated (the
success-arm rule and the naming-function pair in item 1; the layer decision in item 2), and one
decision the document left open is now made (where the deprecated positional aliases live). The
result is still one change. It did not have to become two, and the reason is worth saying: the
only item that would have forced a second break was the flattening, and it is rejected rather
than deferred.

### Before the change — additive only, no public name moves

Neither of these touches a name, so neither is a rewrite and neither needs staging. They land
first so the one structural change is *measured* rather than asserted.

- **The P3 instrument, and the sweep it runs (P3).** Build the accepts-iff-schema-accepts check
  as a **sampled** property test over every generated class — the bundle resolves offline once
  the version derivation of item 6 is in, 113 of 1057 schemas carry root `examples` as a payload
  source, and one negative per node is generated (a required field removed, an enum value
  replaced). It is not total, and that is acceptable: today nothing checks P3 at all. Run it to
  find every `allOf`+`enum` narrowing site (§4.3) and every other divergence; record the list in
  the pull request, not in the tree. **The fix to the merge is NOT here** — see item 7 below; it
  removes enum members, and an enum member is a public name. There is no `extra=` assertion to
  write: the generator already derives it (P3), and the fifth revision's "one assertion per
  deliberate divergence" named a divergence that does not exist.
- **The root schema accessor (P8).** One function at the package root taking a schema name,
  beside `adcp.schemas.load_schema`. A new name, no moved name.

**The shape fixture is NOT part of this, and must not be committed.** The first version of
this document put it first. Under P10 it fails: it records whatever the tree held when someone
committed it, so it would have blessed the four mislabelled activation-key names exactly as
`test_public_api.py` did. Its legitimate use is proving the one change did what it claims, and
that is a **before/after diff attached to the pull request** — take the snapshot before, diff
after, commit nothing. `SCHEMA_DELTAS.md` already produces it (`generate_types.py:1704-1712`).
Once P1 lands, the swap the fixture exists to detect cannot occur.

### The one change

Seven things that each move public names, landed together because landing them apart is seven
breaks instead of one. The order below is a dependency order, not a sequence of releases:
(2) is a decision the rest read; (1) and (4) change what exists; (3) derives the bindings over
the result; (5) and (6) are independent of all of them.

1. **Name every union branch by the rungs (P1), and emit the response base with dispatch.**
   Delete `post_generate_fixes.py:6454`'s index naming, `:6449-6453`'s reorder, and
   `:6408-6411`'s `endswith("1")` success detection. **The success arm is not found by a
   `status` const** — on `create-media-buy-response.json` and `update-media-buy-response.json`
   (pin) the success arm carries no const, the error arm carries none, and only the submitted
   arm pins `status: submitted`; the commitment response pins all three. The rule that holds on
   every response root in the bundle: the arm that gets `_normalize_legacy_status` is the one
   whose schema requires neither `errors` nor `task_id` — the backfill exists precisely for the
   arm whose status the schema leaves unpinned. Two naming functions exist at the pin and they
   disagree on 115 root titles (`A2UIBoundValue` / `A2UiBoundValue`, `CSSAsset` / `CssAsset`):
   `union_branch_names.pascal_case` and `generated_names.generated_root_class_name`, the latter
   being what the wheel's root classes are actually named by. The rungs keep deriving the
   *branch* name (titled branches: 0 of 302 disagree) and take the *parent prefix* from
   `generated_root_class_name`, so a const- or required-set-named branch shares its base class's
   spelling; 5 roots change under that rule (`a2ui/bound-value`, `adagents`, `daast-asset`,
   `vast-asset`, and one more), none of them yet shipped. `_schema_title_to_class_name` stays
   deleted. Route the response-arm emitter through `emit_branch_classes`
   (`post_generate_fixes.py:8778`, pin) so the response base carries `BranchDispatchMixin` like
   the 19 partitioning roots already do (§3.1 axis B).
2. **The layer, decided (P5).** A semantic name on `adcp.types` binds to the
   `canonical_creative` subclass where the canonical layer declares one, and to the generated
   class otherwise; the domain path always binds the wire-faithful generated class. This is
   what the pin does for every canonical name (`Product`, `Format`, `Package`,
   `CreateMediaBuyRequest`, … all resolve to `adcp.types.canonical_creative`) and what
   `canonical_creative.py:1-6` (pin) says the layer is for — "the primary application-facing
   models". Writing it down changes nothing at the pin; it decides what items 1 and 3 emit. The
   rename in item 1 therefore produces `domains.media_buy.CreateMediaBuySuccess` (generated) and
   `adcp.types.CreateMediaBuySuccess` (canonical subclass of it), the same pairing `Product`
   has today. **A caller who needs the wire-faithful arm as a base class imports it from the
   domain path.** This repo does (`src/core/schemas/_base.py:107-112` subclasses the generated
   arm), and the comment at `_base.py:1261` that calls the base `CreateMediaBuySuccessResponse`
   is wrong about which layer it subclasses; it is corrected when the imports move.
3. **Derive the whole binding layer (P5).** `aliases.py`, `_eager.py`, both `__init__` files,
   `KNOWN_COLLISIONS`, and the hand `TypeGuard`s (`guards.py`, `_EAGER_ONLY_EXTRAS`) — generated
   from the module tree under (2), with the 98 `TypeAlias` annotations gone. Depends on (1),
   (2) and (4) having run.
4. **Local refs only (P2).** Shrink `PRESERVE_CANONICAL_URL_REFS` to empty and fix the
   sibling-document alias case. This is in the same change because removing a duplicate class
   removes a public name. It also collapses 190 of the 335 intra-domain duplicate names (the
   identical-shape ones), which is what makes the DX9 residue 145.
5. **Refuse the deep import (P8).** No flattening. The domain root already binds once-declared
   names; add the rule that refuses an import naming a generation subdirectory
   (`domains.core.assets.<module>`) or an underscore module, and nothing else moves. In the
   change rather than before it only because the refusal is what the deprecation shim in (8)
   is measured against.
6. **Derive the spec version (P9).** Replace the `/3.2.3/` → `/3.2/` symlink and every version
   literal with the derivation, failing closed when no bundle matches.
7. **Intersect the `allOf`+`enum` narrowing (P3).** The fix the instrument above found the
   sites for. At the one known site it deletes `Code.inventory_shortfall_forecast_1`,
   `Code.flight_change_creates_pacing_risk_1` and `Code.fields_ignored_due_to_precedence` from
   `media_buy_commitment_response.py:37-42` (pin) — three public enum members — so it belongs
   here and not in the additive set, where the fifth revision put it.

8. **Where the deprecated positional names live — decided.** Every positional name
   (`CreateMediaBuyResponse1`, …) is emitted as an alias **in the module that declares it
   today** — the schema module, the domain root, and `adcp.types` for the ones exported there —
   bound to the renamed class, with a `DeprecationWarning` raised on access through each
   module's `__getattr__` (the mechanism `adcp.types` already uses for `generated_poc`, pin).
   Because no module path moves (item 5), a deep import of a positional name keeps working for
   the whole window, which is the only reading of §7's "aliases through one major" under which
   the promise means anything to the callers who actually import deep. The aliases are
   generated by item 3's derivation, not hand-listed, and are deleted in the following major.
   Nothing goes behind a `domains` shim, because `domains` is not moving.

Emitted together: semantic names as the real classes, positional names as deprecated aliases
where they are now, one snapshot regeneration under review (`test_public_api.py:505-520`'s
`repointed` check fires for every renamed class — intended), one `DeprecationWarning` cycle,
one major for removal.

### After, and not part of it

- **One metadata PR upstream:** a `title` for
  `content-standards/get-content-standards-response.json#/oneOf/0`, the single branch the
  rungs cannot name.
- **The nested positional names** (~1045) stay. The root-branch rungs do not reach them, this
  document has no rule for them (§9), and inventing one would be the third rewrite. They are
  ratcheted shrink-only and left alone until a rule exists that is worth one more break. This
  is also why the schema module stays public (P8): 145 of them share a bare name with a
  differently-shaped sibling in the same domain, and the schema module is the only path that
  names them.

**For this repo:** the 108 `adcp.types.domains` import statements (33 files) keep resolving
through the window; the 15 positional names among them move exactly once, after the change, in
one commit, to the domain path of the renamed generated class. Not to the `adcp.types` alias —
that is the canonical layer (item 2) and a base-class change this repo has not asked for.

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
| `stabilize_inlined_core_refs` | **DELETE** with §5 item 4 | Exists only because of remote refs. |
| `stabilize_nested_discriminators` | **KEEP** | Unrelated to refs — it drops a flattened duplicate discriminator pydantic rejects at import. |
| `_eager.py:1097-1098` synonyms | **DELETE** via staging | Mislabelled at birth; still a compat surface. |
| 98 `TypeAlias` annotations | **DELETE** | §4.4. |
| `test_asset_aliases_stable.py`, `test_collision_aliases.py` | **DELETE after the change** | Hand-listed expectations per alias — blessed values. Until the change they are the only thing holding the hand table honest; afterwards the alias *is* the derivation and they assert a tautology. |
| `test_lazy_types.py::test_partial_modules_avoid_numbered_codegen_names` | **KEEP, widen** | A regex over `__all__`, no blessed value. Widen to the whole surface; it becomes P1's grade. |
| `test_lazy_types.py::test_partial_modules_never_import_generated_layer` | **KEEP** | The guard that refuses the fifth revision's flattening: `adcp.types.media_buy` is a curated partial, not a generated domain. A derived property, no blessed value. |
| `BranchDispatchMixin`, `name_the_combinator` | **KEEP, extend** | The runtime dispatch and the keyword-named refusal (§3.1 B, C). Extend to the response roots through item 1; the hand `TypeGuard`s in `guards.py` are then derived and go with the hand tables. |
| `post_generation_manifest.json` | **REPLACE** | Keep the rule (a fix that changes nothing fails the run), drop the per-fix table. The seven fixes it records as no-ops at this pin are dead code; delete them. |
| `test_union_branch_names.py` | **SPLIT** | Keep the partition identity (`named + classless + refused == total`) and the single-refusal assertion — both derived. Drop the five equality counts (557/169/82/27/1); they are a ledger. |
| `union_branch_names` rung 4 (fail closed) | **KEEP** | A build failure, not a value. This is P1's enforcement, and it is what found the one unnameable arm. |
| `_enforce_every_class_is_reachable` | **KEEP** | Derived; found #911. |
| `test_canonical_models_are_subclasses.py`, `test_export_surface_is_derived.py` | **KEEP** | Properties over the live tree. |
| shape fixture | **DO NOT ADD** | P10. A one-off before/after diff in the pull request instead. |

**Churn versus correctness.** The positional→semantic rename of response arms is *required* by
P1, so it beats the emitter sites that defend the numbering. Re-exporting `Warning` on
`adcp.types` is ergonomics and P6 argues against it — it loses. Switching salesagent's four
"switchable" imports to the `adcp.types` aliases is neither: under §5 item 2 those aliases are
the canonical layer, and this repo subclasses the wire-faithful arm, so the imports move to the
renamed domain-path class and nowhere else.

---

## 7. What must not change

- Every class already named by its schema title (`CreateMediaBuyRequest`, `Product`,
  `Warning`, …) keeps its name. The rungs name branches, not roots, and the parent prefix they
  use is the generator's own root name (§5 item 1), so no root is renamed by the change.
- **Every module path that resolves at the pin keeps resolving.** `adcp.types.domains.<d>`,
  `adcp.types.domains.<d>.<schema>`, and the curated partials `adcp.types.media_buy` /
  `.creative` / `.signals` / `.protocol` / `.buyer` / `.seller`. The fifth revision said the
  deep paths do not survive; the audit found the flat target occupied and the deep path the
  only one for 145 names (P8), so they stay. What is new is a refusal of the paths that were
  never a contract: generation subdirectories and underscore modules.
- The `generated_poc` → `domains` deprecation window, closing in v10 as the pin states. Nothing
  in §5 opens a second one over the same paths.
- The 136 plain-assignment alias *names*. Only their provenance becomes derived.
- The request-side split classes the pin already emits
  (`CreateMediaBuyRequestExplicitPackagesWithFixedAllocation`, …) — already correct under P1.
- `_generated` bare-name resolution for every non-colliding name.
- The codegen flags (`--strict-types bool int float`, `--reuse-model`, `--use-annotated`, …),
  `rewrite_refs` itself, and `flatten_validation_oneof`.
- `adcp.types`' PEP 562 lazy mechanism, and the per-domain lazy facades. §5 item 3 generates
  the *contents* of `__init__` / `_eager.py`; it does not replace the loading shape.
- Positional names as deprecated aliases through one major, **at the module that declares them
  today** (§5 item 8).
- `BranchDispatchMixin`'s four-path dispatch on the 19 roots that have it, and the `anyOf` /
  `oneOf` keyword on their refusals. Item 1 adds roots to it; nothing removes one.

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

The fifth revision (`131df0569`, the same night) added three items and a reviewer's audit
against the wheel refuted two of them and found four more errors in the body. Recorded in the
same spirit:

14. **"Flatten the namespace to `adcp.types.<domain>.<Class>`; the module paths do not
    survive."** The target is occupied by six hand-written modules, four of them the curated
    partials a kept guard protects; privatising the schema modules orphans 145 differently-
    shaped names that share a bare name within a domain; and the path already moved once this
    major (`generated_poc` → `domains`, April 2026). Rejected, not deferred — P8.
15. **"`AdCPBaseModel`'s `extra="ignore"` is a live P3 violation; derive `extra="forbid"` from
    `additionalProperties: false`."** The generator already does: 1002 `forbid` and 1187 `allow`
    sites in the non-bundled domain modules, `types/base.py:316-320` (pin) states the rule. The
    same revision's §5 called the same divergence "wider on purpose" and asked for an assertion
    per divergence; the two paragraphs contradicted each other and both described a pin that
    does not exist.
16. **"This breaks every deep import, including five of this repo's eleven."** 108 import
    statements in 33 `src/` files, 124 names, 16 with no flat destination. The eleven were the
    positional imports; the sentence was about deep imports.
17. **"Detect the success arm from the schema's `status` const."** The success arm of the
    create and update responses has no `status` const (pin); only the submitted arm does. The
    rule as written selects nothing.
18. **"Use `generated_names.generated_root_class_name`"**, while the rungs being wired use
    `union_branch_names.pascal_case` — two functions that disagree on 115 root titles and on
    the parent prefix of 5 roots' branches. Item 1 now names both and says which does what.
19. **"Python resolves neither `CreateMediaBuyError` nor `CreateMediaBuySubmitted` under any
    top-level name — two of the three arms have no name a caller can import."** `aliases.py:634`
    and `:637` (pin) export `CreateMediaBuyErrorResponse` and `CreateMediaBuySubmittedResponse`
    on `adcp.types.__all__`. The failure is "not by the schema's own title", which DX2 measures
    correctly; the text overstated it.
20. **"The narrowing intersect is additive — a behaviour fix with no rename."** It deletes
    three members of a public `StrEnum` at the one known site (`Code`,
    `media_buy_commitment_response.py:37-42`, pin). Moved into the one change as item 7.
21. **Text the rewrite left standing from the first version:** "three of the five principles"
    (there were ten); "R1←P1 … R6←P5" (rules defined nowhere); "the one change in §4" and "§6
    covers it" (wrong sections); §4's subsections numbered 3.1–3.5 with cross-references that
    disagreed among themselves; "Stage 2" and "Stage 6" from the retired plan; and §8 item 6's
    parenthesis "the gate still lands first" beside §8 item 12 and §5 saying it must not be
    committed. All corrected in the body; item 6 is left as written above so the contradiction
    stays on record.
22. **"Whether `branch_classes`' emitter is wired" (§9).** It is: `post_generate_fixes.py:8778`,
    in the fix list at `:9174` (pin). The docstring at `tests/test_branch_classes.py:11` that
    says otherwise is stale, and §9 carried the stale text as an open question.

---

## 9. Not established

What the design rests on that is not yet measured, and what would measure it:

- **The layer decision (§5 item 2) rests on the pin's behaviour being the intended one.** The
  pin binds every canonical name to `canonical_creative`; no commit message or document in the
  SDK was found saying that was chosen rather than accumulated. If upstream disagrees, items 1
  and 3 emit the other pairing and nothing else in the plan changes. Verifier: upstream's
  answer; until then `test_canonical_models_are_subclasses.py` grades whichever layer is public.
- **The success-arm rule in item 1** ("requires neither `errors` nor `task_id`") was checked on
  the three response roots named in this document, not on every response root in the bundle.
  Verifier: run it over every `*-response.json` with branches and assert exactly one arm
  matches, or the emitter fails closed.
- **How many enum members the narrowing fix (item 7) removes across the bundle.** Three at
  the one known site. The P3 instrument's sweep is the measurement; until it runs, item 7's
  public-name footprint is one site.
- **Whether any caller constructs a model with a value the unioned vocabulary accepts and the
  intersected one refuses.** This repo does not touch the commitment response's warnings (grep
  empty); other adopters not examined.
- **The sibling-document `allOf` re-derivation** (item 4): the generator condition behind it is
  not established, and the audit did not measure the case.
- Whether the 98 `TypeAlias` annotations were deliberate. No rule or comment found.
- Whether the 9 cascade families reach zero after a fixed-point naming pass — name the leaves,
  collapse identical shapes, re-key. Not iterated. The 145 differing-shape intra-domain names
  (P8) overlap this set; how far they shrink under such a pass is not established either.
- The scope of P3 divergences beyond §4.3, now that `extra=` is known not to be one.
- Whether `Warning`'s absence from `adcp.types.__all__` is builtin-shadowing policy or an
  omission (P6 wants it to be policy either way).
- Whether each of this repo's positional use sites needs a base class or only a type position
  (15 positional names imported; `_base.py:107-112` is a base-class use).
- Whether the TS SDK's Zod layer preserves the `allOf` narrowing that its types preserve. Two
  generators make disagreement possible; whether it occurs was not examined.
- Whether the mapping in §3.1 axis C from pydantic error types to JSON-Schema keywords is total
  over the error types the generated classes can raise. Enumerate them from the core schemas
  and check; not done.
- Go and Java SDKs.

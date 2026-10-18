# SDK type generation: the principles it is missing

**Status:** design.

**Provenance convention.** This document cites three trees, and they disagree. Every citation
carries a tag:

- `(pin)` — the installed wheel, `adcp 9.0.0b3+sa.8qela.f33d4fc71`, AdCP 3.2.3. **This is
  what salesagent runs, and it is the only tree whose line numbers bind.**
- `(main)` — `adcontextprotocol/adcp-client-python` upstream `main` @ `734bf3acd`.
- `(ts)` — `adcontextprotocol/adcp-client`, `@adcp/sdk` 16.0.0-beta.7/8.

---

## 1. The one-line summary

The Python SDK's generated surface is **named by position in places where the schema carries
an identity**. Every other defect in this document either follows from that or was hidden by a
guard keyed on a name. Of the ten principles in §2, the TypeScript SDK holds P2, P6, and P8,
fails P4 and P5, and holds P1 only for titled arms. It is a reference for specific mechanisms,
not a model to copy wholesale; §3.1 names the axes where Python is built to exceed it.

**The generator does not number the response arms.** `CreateMediaBuyResponse1/2/3` comes from
one line of this repo's own emitter:

```python
# post_generate_fixes.py:6454 (pin)
class_names = [f"{self.base}{index}" for index in range(1, len(branches) + 1)]
```

Two more sites defend that numbering: `:6449-6453` remaps `BuildCreativeResponse` branches
`(0, 4, 1, 2, 3, 5)` "to preserve the long-standing public numbering", and `:6408-6411`
detects the success arm by `class_name.endswith("1")`. **The naming decision has exactly one
site, and it is a line of this repo's code.** `--use-title-as-name` is absent from the
generator's argument list `(main)`, and adding it renames nested anonymous classes while
leaving every response arm numbered.

**Most of the fix exists at the pin.** `scripts/union_branch_names.py` (pin) resolves a union
branch's name by four rules in precedence order, each a fallback for the one before it:

1. The branch's declared `title`.
2. Else, the discriminator `const`.
3. Else, the full required-property set.
4. Else, refuse: the build **fails closed**.

This document calls them rule 1 through rule 4, and calls the set the resolution rules.
`tests/test_union_branch_names.py:66-73` (pin) pins their result over the pinned bundle by
equality:

```
557 root branches:  169 named by title · 82 by const · 27 by required set
                    278 mint no class (96 ref, 10 scalar, 172 validation-only)
                      1 unnameable  (content-standards/get-content-standards-response.json#/oneOf/0)
```

The wheel ships `CreateMediaBuyRequestExplicitPackagesWithFixedAllocation` and its siblings.
So the work is to **wire the resolution rules into the response-arm emitter**, not to invent a
naming scheme and not to file 327 upstream tickets.

---

## 2. The principles

Each principle is stated so that a build can refuse a violation, because a principle nothing
enforces is how this surface got here. Each states its cost.

### P1 — A name is a function of the schema node's identity, never of a traversal position or a loop index

P1 forbids `f"{base}{index}"`, forbids `AssetsNN`, and forbids *fixing* an index by
reordering, which is what the `BuildCreativeResponse` remap does. Pinning a wrong name is not
holding a right one.

**Cost:** a node with no derivable identity gets **no class**. The pin pays this on exactly one
branch, which is the evidence that the cost is affordable.

**TS:** holds for titled arms (`generate-types.ts:708-711` preserves `branch.title`, and
`json-schema-to-typescript` names by title) and fails elsewhere: 45 numbered declarations
`(ts)`, including `BrandReference1..12` and `MacroBearingURL1..8`.

**Enforceable at the pin:** `tests/test_lazy_types.py::test_partial_modules_avoid_numbered_codegen_names`
(pin) refuses `[A-Za-z]\d+$` on the curated partials. Widen its population.

**Scale, and the nested rule.** 1045 of 4076 classes in non-bundled domain modules carry a
trailing digit (pin). 80 are RootModel or enum wrappers with no field set; the remaining 965
form **238 families**. `CreativeItem1` and `CreativeItem2` are one family in one module. Key
each member by (field-name set, required-name set, `Literal` const defaults), which is the
nested form of the root resolution rules:

```
146 of 241 families   key is injective -> every member gets a content-derived name
 84 colliding groups  IDENTICAL shape -> one node generated more than once
 11 colliding groups  differ, and 9 of the 11 differ only through a cascade
```

A runtime-shape census produces those figures. An earlier count of 206 / 85 / 9 does not
reproduce, so disregard it.

The nested residue is not a naming gap, and it is smaller than the 84 suggests. Of those
groups, 2 are aliases, 69 are chains — reuse-model empty subclasses and the `allOf` products
from §4.2, where the composed class is the one to keep — and 13 are independent siblings, of
which 8 are byte-identical copies of one node and 5 differ only in description text. So the
duplication to collapse is 13 groups, and fixing the `allOf` copy removes the 69 chains as a
side effect.

The 11 differing groups resolve individually. Six vanish once identical leaves collapse. Two
take their names from a leaf const — the `asset_union` `MacroDeclaration` groups become
`MacroDeclarationLocationUrl` and `MacroDeclarationLocationContent`, from
`vast-asset.json#/oneOf/0,1/properties/macro_declarations/items/properties/location`.
`Subject3` takes its name from a title at `core/attestation-subject.json#/oneOf/0..2`. The
last two, `CheckGovernanceRequest2/3` and `BoundedValueLevel31/21`, need the fixed-point
pass. **No arm in the wheel differs only by a scalar constraint** such as `maxLength`.

Nothing downstream moves. This repository has 124 domain imports and none of them names a
member of a colliding group.

**Which rule names a branch, and why it matters.** The rule decides churn under upstream
change. A full-field-set key renames the class whenever the spec adds an *optional* field,
which is an `ImportError` downstream on every bump. The required-set key (rule 3) is stable
under optional additions and renames exactly when **requiredness** changes, a semantic change
that a caller should see loudly. Title (rule 1) and discriminator const (rule 2) are stable
under all content change. So the claim for P1 is: a silent swap becomes unrepresentable, and an
upstream semantic change becomes a loud `ImportError` instead of a silent repoint.

### P2 — One schema node, one class; a `$ref` is a reference

P2 forbids a copy by any route, remote-ref resolution (§4.2) and `create_model` copies alike.
The canonical layer used to build 32 public classes that way
(`tests/test_canonical_models_are_subclasses.py`, #1368, pin).

**Cost:** every ref must be local before generation, and a layer that wants a different public
shape must subclass rather than re-derive.

**TS:** holds. `Warning` references `WarningCode`, `WarningAffectedResource`, and
`ExtensionObject` by name; nothing is inlined.

### P3 — The model's accepted set is the schema's accepted set

This is the SDK's own stated principle. The `--strict-types` rationale at
`generate_types.py:1266-1279` (pin) says the point is that the two validators the SDK ships
do not disagree about the same bytes. §4.3 is a live violation of it.

**`extra` is part of the accepted set, and the generator derives it.** `AdCPBaseModel`'s
`extra="ignore"` does not make a model wider than a schema declaring
`additionalProperties: false`. The 3.2 bundle declares `additionalProperties: false` on 256
roots and 9729 nodes (non-bundled), and the generated domain modules carry `extra='forbid'` at
1002 sites and `extra='allow'` at 1187. `core/media-buy.json` is `false` and
`domains/core/media_buy.py:32` (pin) is `forbid`; `core/warning.json` is `true` and
`domains/core/warning.py` is `allow`. `types/base.py:316-320` (pin) states the rule. The base
class's `ignore` applies only where the schema says nothing, and there the accepted sets agree:
both accept the unknown field; one retains it and one drops it, which is not a P3 question. So
there is no `extra` divergence to fix, and P3's check needs no exclusion list.

The consumer-side choice this repo makes, `get_pydantic_extra_mode()` selecting `ignore` in
production and `forbid` in development (CLAUDE.md pattern #7), sits on the consumer's own
subclasses and does not conflict with the derived value on the library class underneath.

**The `extra=` deviation that does exist is this repo's.** The census is every
`ConfigDict(...)` call under `src/` that passes `extra=`, found by AST and classified by whether
the value is the call `get_pydantic_extra_mode()` or a string literal. 60 calls: 43 derived, 10
literal `"forbid"` (`src/adapters/base.py` ×5, `src/core/schemas/capability_declarations.py` ×2,
`src/core/schemas/notification.py`, `src/core/resolved_identity.py`,
`src/core/signing/posture.py`), and 7 literal `"ignore"`, all in `src/core/schemas/_base.py`
(lines 1495, 1681, 1703, 2069, 2284, 2840, 4230), the serializer mixins every wire model
inherits. Within `src/core/schemas/` alone: 48 calls, 38 derived, 3 forbid, 7 ignore.
**Excluded by name:** the two `SettingsConfigDict(..., extra="ignore", ...)` sites at
`src/core/config.py:42` and `:442`. Those are pydantic-settings environment loading, where
`extra="ignore"` means "tolerate unrelated variables in the process environment"; they say
nothing about what a buyer may send on the wire, which is what the dev-forbid / prod-ignore
rule governs. The census is specified as an AST count rather than a search for a reason: the
second `SettingsConfigDict` call wraps, its `extra=` sits on the line after the `ConfigDict`
token, and a line-oriented `grep` sees only the first of the two. That `grep` reports 61 calls
and 8 `ignore` literals. A wrapped call is invisible to a line-oriented instrument, and that is
the general form of the error, not a property of this file. A literal on a wire model is the
one place the dev/prod split of pattern #7 does not apply, and nothing in the repo says which of
the 17 chose that on purpose. Whether a comment beside each states a reason was not graded,
because a comment-line count is not a measurement of a reason. That is a salesagent defect to
grade in salesagent, with a guard over `src/core/schemas` refusing a literal `extra=` on a wire
model. It is recorded here so that nobody mistakes it for an SDK divergence.

**TS:** holds at the type level (`warnings?: (Warning & { code?: 'a' | 'b' })[]`). Runtime
not established; the Zod layer was not examined. Structurally the TypeScript SDK cannot hold
P3 as a property of one object: `generate-types` and `generate-zod-schemas`
(`scripts/generate-zod-schemas.ts:4`, `json-schema-to-zod`) are two generators over the same
cache, exported at `.` and `./schemas` `(ts)`, and nothing makes them agree. See §3.1 axis A.

### P4 — Identity is graded by shape, not by name

P4 forbids a snapshot keyed only on name (`module:QualName`) **as the sole gate**.

**Cost:** a committed fixture that churns on every legitimate schema bump.

**TS:** does **not** hold it. No public-surface snapshot exists in `adcp-client`.

**Python half-holds it:** `tests/test_asset_aliases_stable.py` grades asset aliases by
their `asset_type` discriminator, and `tests/test_collision_aliases.py` grades by `__module__`
(pin). Those are the precedent to extend.

**Field names are not enough.** `diff_generated_types.snapshot` records field *names*
only, so a change from `Literal['a']` to `Literal['b']`, or `str` to `AnyUrl`, is invisible.
Record the **annotation text** beside the name: one line in the AST walk.

### P5 — Every public binding is derived by one rule, and the build refuses what the rule cannot derive

P5 forbids hand tables: `aliases.py` (2704 lines, 136 plain + 98 annotated),
`KNOWN_COLLISIONS`, `_eager.py:1097-1098`, and both hand-written `__init__` files (pin).

**Cost, stated plainly:** a name only a human knows is lost. `AccountReferenceById` over an
untitled arm is the example: unless a resolution rule derives it, it goes.

**TS:** does **not** hold this either. It carries a hand rename table at
`generate-types.ts:368-384`, a hand handler for the title `Size-mode mutex` at `:986-1003`,
and `export type { Error as TaskErrorDetail }` at `src/lib/index.ts:1296` `(ts)`.

**The question §5 item 2 decides: which class does a derived alias bind to?** Verified from
salesagent's venv:

```
alias   adcp.types.aliases.CreateMediaBuySuccessResponse
        -> adcp.types.canonical_creative.CreateMediaBuyResponse1
arm     adcp.types.domains.media_buy.create_media_buy_response.CreateMediaBuyResponse1
alias is arm         False
alias subclasses arm True
```

The semantic alias resolves to a **subclass in the canonical layer**, with legacy format
identity removed, not to the generated arm. So "switch to the semantic name" is a
**base-class change**, not a rename. This is not special to the media-buy arms: every canonical
name on `adcp.types` (`Product`, `Format`, `Package`, `Creative`, `CreativeAsset`,
`CreateMediaBuyRequest`, `GetProductsResponse`, `UpdateMediaBuySuccessResponse`) resolves to
`adcp.types.canonical_creative` (pin). The pin's rule, never written down, is: the flat
namespace is the canonical layer; the domain path is the wire-faithful class. §5 item 2 writes
it down and keeps it.

### P6 — A name that shadows a host-language builtin never claims the bare public slot

**TS applies it:** `Error as TaskErrorDetail`. **Python plausibly does:**
`"Warning" in adcp.types.__all__` is `False` (verified). Intent is not established, and that
is the problem. This should be a rule the build knows, not an absence someone has to guess at.

### P7 — Determinism is a precondition of grading, not a fix

`run_datamodel_codegen.py`'s input-order patch makes the output a function of the input.
Without it, `make validate-generated`'s byte compare and every snapshot are meaningless.
*Order being total* is necessary; *which order was chosen* is cosmetic.
`tests/test_code_generation.py:3189::test_codegen_input_order_is_total` (pin) enforces it.

### P8 — A caller imports by domain; the schema module is the path for a name the domain declares twice

A caller writes `adcp.types.domains.<domain>.<Class>` for a name the domain declares once, and
`adcp.types.domains.<domain>.<schema>.<Class>` for a name it declares more than once. Nothing
deeper, and nothing under an underscore. That is what the pin does: the generated domain root
(`domains/core/__init__.py`, pin) is a lazy PEP 562 facade binding exactly the once-declared
names, and its docstring sends the rest to the schema module. So P8 is a rule the build must
refuse violations of, not a move.

Flattening to `adcp.types.<domain>.<Class>` with the schema modules made private is rejected on
three measurements:

- **The target is occupied.** `adcp/types/media_buy.py`, `creative.py`, `signals.py`,
  `protocol.py`, `core.py`, and `error_details.py` exist at the pin as hand-written modules, six
  of the 26 domain names. Four are the curated partials (`_PARTIAL_MODULES`,
  `types/__init__.py:1086`), whose docstrings say they "never expose the internal generated
  layer" and which `tests/test_lazy_types.py::test_partial_modules_never_import_generated_layer`
  (pin) holds to that. `types/core.py` is 408 lines of hand-written types. The hand modules and
  the generated domains overlap on 33 names in `media_buy`, 47 in `error_details`, and 15 in
  `protocol`.
- **Privatizing the schema module orphans the names the domain root cannot bind.** 335 class
  names are declared in more than one module of the same domain, 145 with differing shapes
  (`core` 190 / 98; `Location` 14 modules / 4 shapes, `Identifier` 7 / 6, `Authentication`
  6 / 5). Item 4 of §5 collapses the 190 identical-shape duplicates (P2: the same node generated
  twice). The 145 are distinct nodes sharing a bare name, and §5 has no rule for naming nested
  classes by content, so after a flattening they have no public path at all. This repo imports
  16 of them (`Identifier`, `Unit`, `Authentication`, `Creative`, `Account`, `Setup`, `Source`,
  `Provenance`, `Parameters`, `DateRangeSupport`, `MediaBuyDelivery`, `EventType`,
  `NotificationType`, `DeliveryAuth`).
- **The path has moved once this major.** `adcp.types.generated_poc` →
  `adcp.types.domains`, codemod `adcp migrate v3-to-v4` (`adcp/migrate/v3_to_v4.py`, pin, SDK
  commit 32bfbeb88, 2026-04-20), old path removed in v10 as the `types/__init__.py` docstring
  states. A second move inside the first move's deprecation window is the pattern §5 forbids.

So the `domains` token stays. It costs one word per import and buys an uncolliding package for
26 generated domains beside the hand-written ones. The flattening is **rejected, not deferred**:
a later flattening is the third rewrite, and this document says no to it so that nobody
proposes it as a small follow-up.

Measured depth at the pin, excluding the `bundled/` mirror:

```
  1 level     44 modules
  2 levels    34 modules
  3 levels   962 modules   adcp.types.domains.a2ui.bound_value
  4 levels    57 modules   adcp.types.domains.core.assets.asset_union
  5 levels    39 modules   adcp.types.domains.core.async_response_refs.creative...
```

So the common case is three levels and the worst is five. Under P8 as stated, the caller sees
two for a once-declared name and three for the rest. The four- and five-level modules
(`core/assets/`, `core/async_response_refs/`) are reached only through their domain root or
their schema module; the subdirectory is generation layout, and the build refuses an import
that names it:

```
pin        adcp.types.domains.core.warning.Warning
           adcp.types.domains.media_buy.create_media_buy_response.CreateMediaBuyResponse1
after §5   adcp.types.domains.core.Warning
           adcp.types.domains.media_buy.CreateMediaBuySuccess          (declared once)
           adcp.types.domains.core.property.Identifier                 (declared 7 times)
```

**Cost:** none to imports that resolve at the pin; every such path keeps resolving. The cost
is the one that was already paid: a caller who wants the one-level
`import { CreateMediaBuySuccess } from '@adcp/sdk'` form does not get it from Python, because
`adcp.types.CreateMediaBuySuccess` is the canonical layer (§5 item 2) and the domain path is
the wire-faithful one. That is a real difference between the two SDKs, and closing it takes a
third rewrite.

**The flat loader is a separate, additive item.** `adcp.schemas.load_schema("adcp-agents.json")`
makes a caller name a package, a verb, and a filename with an extension. One accessor at the
root taking a schema name is the ergonomic form; adding it moves no name, so it lands before
the change (§5).

**TS exceeds Python here and keeps doing so:** one level, no domain, no file stem. The
compensating advantages are in §3.1.

### P9 — The spec version is read from the SDK, never written as a literal

`adcp.get_adcp_spec_version()` is the authority. A literal version in a path is a defect
waiting for the next pin bump: the SDK reports the bumped version, the literal keeps
resolving the old bundle, and nothing fails.

The bundle directory is not equal to the spec version (the SDK reports `3.2.3` and bundles
`3.2`), so the derivation takes the exact directory when it exists, else the longest dotted
prefix, and **raises** when neither matches. `generate_types.py:1296-1303` solves the same
mismatch with a hardcoded `/3.2.3/` → `/3.2/` symlink, which is the literal in another form.

`scripts/audit/sdk_dx_probes.py` in this repo replaced the literal `"3.2"` with the derivation;
that function is the reference implementation.

### P10 — A check compares the output to the inputs, never to a previous output

The repo's own history establishes this principle. Every check in the pin that has found a
real defect is **derived**: `_enforce_every_class_is_reachable` found #911, the reachability
test found the double-load in #1360, and rule 4's fail-closed refusal found the one unnameable
arm. Every check that held a defect **green** carries a **blessed value**:
`test_public_api.py`'s 7944-name snapshot held the four mislabeled activation-key names, and
the alias-stability tests assert a hand-listed expectation per alias.

A blessed value records whatever the tree held on the day someone committed it. It detects
*change*, which is not the same as detecting *wrongness*, and it cannot tell a fix from a
regression without a human who already knows the answer.

**So `make validate-generated`'s byte compare survives and the snapshots do not.** The byte
compare asserts a property, that the committed tree equals `f(schemas, pinned generator)`, and
carries no blessed value at all. P7's determinism is what makes that `f` a function. P10 is
also what rules out a committed shape fixture; see §5.

---

## 3. The developer-experience requirements

These twelve requirements are normative. A generator change satisfies them or it is not done.
They are not a test artifact bolted on afterwards: each one states a question a caller asks
the SDK, and each failure in the table is a caller getting the wrong answer or no answer.

`scripts/audit/sdk_dx_probes.py` in the salesagent repository measures the Python column
(probes S1–S8, S11, S12; DX9 and DX10 were measured by hand and are not probed). The
TypeScript column is measured statically against `adcp-client` `main`, the generated files
and both root index files, because the two languages share no test harness; those cells were
measured once and are not re-verified. A TypeScript cell reads **n/a** where the requirement is
one the language cannot state at runtime, which is the point of §3.1.

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
| DX9 | A caller imports a type by domain, `adcp.types.domains.<domain>.<Class>`, and reaches a schema module only for a name the domain declares more than once | **PARTIAL** the domain root binds once-declared names at the pin; 335 names (145 after P2) need the schema module; nothing refuses a deeper import | **PASS** 1 level, flat root export, and exceeds Python; see P8 |
| DX10 | Nothing in the SDK names a spec version as a literal | **FAIL** symlink alias | not examined |
| DX11 | A caller validates a document against a root with branches and gets the branch's class back, on every path (`Root(**d)`, `model_validate`, nested, `TypeAdapter`) | **PARTIAL** 19 roots dispatch; the response roots are plain unions with hand guards | **n/a** types are erased; a discriminated union is compile-time and the guard is hand-written |
| DX12 | A refusal names the JSON-Schema keyword that failed, so it can be projected onto `core/error.json`'s `issues[].keyword` without a mapping table | **PARTIAL** `anyOf`/`oneOf` named on the 19 dispatch roots; `missing`, `string_too_short`, … are pydantic's names | **n/a** Zod issues carry Zod codes |

Python satisfies two of twelve outright and three partially; TypeScript satisfies seven, fails
one, leaves two unexamined, and cannot state two. The findings behind each row:

- **DX2.** TypeScript declares `CreateMediaBuySuccess`, `CreateMediaBuyError`, and
  `CreateMediaBuySubmitted` as named interfaces and exports all three from
  `src/lib/types/index.ts:162-164`. Python's titles are the same three strings
  (`create-media-buy-response.json` arm titles, pin), and none resolves on `adcp.types`. What
  does resolve is a hand alias per arm with a `Response` suffix:
  `CreateMediaBuySuccessResponse`, `CreateMediaBuyErrorResponse`,
  `CreateMediaBuySubmittedResponse` (`aliases.py:631-637`, pin). So every arm has a name, and
  the failure is that no arm resolves by the schema's own name.
- **DX3.** TypeScript preserves the narrowing in the type (`Warning & { code?: 'a' | 'b' }`) and
  ships runtime schemas from a separate entry point, `@adcp/sdk/schemas`. Whether those
  schemas preserve the narrowing was not examined, so the cell reads unestablished rather than
  pass.
- **DX4, where TypeScript exceeds Python.** `error.code` is `string` in both, matching the
  schema's open vocabulary. TypeScript then ships `STANDARD_ERROR_CODES`,
  `isStandardErrorCode()`, and `getErrorRecovery()` (`src/lib/index.ts:1294-1301`) and exports
  no `ErrorCode` type at all. That is the right shape for a documentary vocabulary: a caller
  asks whether a code is standard instead of being refused for using one that is not. Python
  exports a closed `ErrorCode` enum, which invites exactly the refusal the schema forbids.
  **Python should adopt the TypeScript shape here**; this is the one row where matching is
  not enough.
- **DX4, second TypeScript lesson.** `export type { Error as TaskErrorDetail }` dodges the
  JavaScript global rather than leaving the name unexported. That is P6 applied, and it is
  what Python should do with `Warning` instead of omitting it.
- **DX5 is the shared failure, and it is not a generator defect.** Neither root index exports
  `Warning`, `WarningCode`, or `WarningAffectedResource`, and the vocabulary is three closed
  members in both. The channel cannot express the condition, so the fix is a spec change, not
  a codegen change, and no section of this document plans one.
- **DX6.** A TypeScript interface extends without ceremony. Python's 98 annotated aliases
  cannot serve as a base class, which is §4.4.
- **DX7.** TypeScript's index takes `CreateMediaBuySuccess` from `./tools.generated`, one
  definite projection. Python's semantic alias resolves to a `canonical_creative` subclass
  (§2, P5).
- **DX8.** Exactly one name in a TypeScript root index matches the positional pattern, and it
  is `PreviewRenderV3`, a version suffix rather than a traversal index.

**What this settles.** TypeScript is the reference for DX2, DX4, DX6, DX7, and DX8, and the
one change in §5 is what moves Python onto all five. DX3's sweep lands before that change and
its fix inside it (§5). DX5 is shared, belongs upstream in the schema, and no amount of
generator work reaches it. DX9 TypeScript keeps. DX11 and DX12 are Python's to win, and §3.1
says how.

### 3.1 Where Python exceeds TypeScript, and what the SDK must do to realize it

§3 treats TypeScript as the reference. That is right for five rows and wrong as a ceiling: a
TypeScript type is erased at runtime, and everything the SDK does with a type at runtime
(validate, dispatch, refuse with a reason, extend with the contract intact) is a separate
artifact there and the same object here. This document tests six candidate axes against the
wheel. Four hold and are design intent; two do not survive and are recorded so that nobody
re-proposes them.

**A. One object is the type and the validator (DX3, made a property).** TypeScript ships
`generate-types` and `generate-zod-schemas` as two generators over the same cache, exported at
`.` and `./schemas` `(ts)`; nothing makes their accepted sets agree, and nothing can short of a
third generator comparing them. A pydantic class is one artifact, so "the model accepts
exactly what the schema accepts" can be a property OF THE CLASS rather than a hoped-for
agreement between files. It is not held at the pin (§4.3 is the counterexample), and nothing
grades it: the 19 pin tests that import `jsonschema` are conformance tests of other things.
*What the SDK changes:* the P3 instrument in §5 becomes a per-class property test,
`model_validate(x)` succeeds iff `jsonschema.validate(x, node)` succeeds, over the bundle's 113
root `examples` and a generated negative per node (one required field removed, one enum value
replaced). *How a caller observes it:* `Model.model_json_schema()` and the bundle node accept
the same documents, so a caller validating with either gets one answer; at the pin they get
two.

**B. Runtime branch dispatch, with the refusal naming the combinator (DX11, DX12).** The SDK
ships this for 19 generated roots, 12 of them exported on `adcp.types`:
`BranchDispatchMixin` (`types/_branch_dispatch.py`, pin) makes
a root with branches validate as the branch the document satisfies on all four paths (direct
construction, `model_validate`, nested field, `TypeAdapter`), and a document satisfying no
branch is refused with `type: 'anyOf'` and the selecting field names in `ctx`
(`_conditions.py:636 name_the_combinator`, pin), which is the keyword `core/error.json`
requires on `issues[]`. The emitter behind it, `emit_branch_classes`, is wired:
`post_generate_fixes.py:8778`, in the fix list at `:9174` (pin), and `_branch_models` is
declared on 19 classes in the generated tree. The docstring at `tests/test_branch_classes.py:11`
says the emitter is not wired; that docstring is stale. Measured:
`WebhookChallengeResponse(challenge=…)` returns `WebhookChallengeResponseChallenge`;
`model_validate({"token": …})` returns `WebhookChallengeResponseToken`; `{"x": 1}` is refused
with one `anyOf` error. The response roots are NOT among the 19: `adcp.types.CreateMediaBuyResponse`
is a plain `types.UnionType` over the three canonical arms, a `TypeAdapter` over it picks an
arm by pydantic's smart union with no keyword on refusal, and the SDK carries ~30 hand-written
`TypeGuard` functions instead (`guards.py:176 is_create_media_buy_success`, listed in
`_EAGER_ONLY_EXTRAS`, pin), which is exactly the TypeScript shape. *What the SDK changes:* §5
item 1 routes the response-arm emitter through `emit_branch_classes`
(`post_generate_fixes.py:8778`, pin, wired for partitioning roots), so the response base
carries the mixin; the hand guards are then derivable (`isinstance(r, CreateMediaBuySuccess)`)
and are deleted with the other hand tables in item 3. *How a caller observes it:*
`CreateMediaBuyResponse.model_validate(payload)` returns `CreateMediaBuySuccess`,
`CreateMediaBuyError`, or `CreateMediaBuySubmitted`, and a payload matching none is refused
with `keyword: oneOf` and the three titles. TypeScript cannot: the union is compile-time and
the guard is a function someone wrote.

**C. A refusal projects onto the spec's error shape without a mapping table (DX12 beyond the
combinators).** `core/error.json` requires `issues[].keyword` to be a JSON-Schema keyword. A
pydantic error carries `type` (`missing`, `string_too_short`, `literal_error`, `enum`), `loc`,
and `ctx`; the mapping from those to `required`, `minLength`, `const`, `enum` is finite and
mechanical, and `_conditions.name_the_combinator` and `error_narrowing.narrow_union_errors`
(pin) do the two hardest cases. Zod issue codes (`invalid_type`, `too_small`) are Zod's
vocabulary, not the schema's, and the TypeScript server maps them by hand. *What the SDK
changes:* one function on `AdCPBaseModel`, `issues_from(exc: ValidationError) -> list[Issue]`,
finishing the projection for every pydantic error type the generated classes can raise,
graded by a test that raises each one and checks that the keyword is in the JSON-Schema
vocabulary. *How a caller observes it:* a seller's `INVALID_REQUEST` carries spec-valid
`issues[]` from the model's own refusal, with no table in the seller's code.

**D. A subclass inherits the parent's validators, and that is graded (DX6, strengthened).**
A TypeScript `interface X extends Y` carries Y's fields and none of Y's runtime checks, because
Y has none. `tests/test_canonical_models_are_subclasses.py` (pin) grades that every canonical
model inherits every `model_validator` of its generated parent, a property the language can
state and TypeScript cannot. It is undercut at the pin by the 98 `TypeAlias` annotations
(§4.4), which make a public name un-subclassable. *What the SDK changes:* §5 item 3 drops the
annotations; the subclass test stays and widens to every public name. *How a caller observes
it:* `class MyProduct(adcp.types.Product)` validates as `Product` does and adds fields, with
`mypy` clean. The §3 table marks the TypeScript cell "by language"; counting validators, it is
the weaker of the two.

**Discarded.** *Behavior on the error type* (`Error.is_standard`, `Error.recovery` as
methods): `adcp.types.Error` has no public method of its own, and `ErrorCode` is a closed
120-member `StrEnum` with no metadata (pin); the TypeScript helpers exist in Python,
server-side and off the type (`adcp.server.helpers.STANDARD_ERROR_CODES:145`,
`adcp.server.translate._recovery_for_code:97`, pin). Moving them onto the class is a small
ergonomic gain, not an inherent advantage: DX4's verdict stands, and TypeScript's shape is the
one to adopt. *`__init_subclass__`*: used nowhere in `adcp/types/*.py` (pin), and no caller-
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
CreativeItem1  ['asset_id','asset_kind','asset_type','content_uri']   media, correct at the pin
CreativeItem2  ['asset_id','asset_kind','asset_type','content']       text,  correct at the pin
both arms untitled · both 4 fields · 4 required · 3 of 4 names shared
symmetric difference {'content','content_uri'}
```

Correct at the pin; one reorder from meaning the opposite, with no type error.
`make validate-generated` reddens on that reorder, so a committed field-shape gate is not what
catches it; the gate's value is at the acceptance step (§5). **Under P1 this becomes
unrepresentable rather than detectable**: rule 3, the required set, names these two from their
own content, and a reorder cannot then swap them. That is a stronger fix than any gate, and it
is why the naming work outranks the snapshot.

It also shows why P4 must key on **name sets, not counts**: both arms have four fields.

### 4.2 A remote `$ref` is resolved as a copy

A three-file tree with production's flags demonstrates it. With `--allow-remote-refs`, the
first referencing module gets a fresh copy named from the URL stem, and the canonical class
generated from the file's own title is orphaned; `--reuse-model` then anchors later referrers
on *the copy*. With local relative refs: `thing: c.SharedThing`, zero duplication.

`rewrite_refs` (`:631` pin, `:503` main) rewrites URLs to relative paths, which is why
production mostly does reuse: 326 files reference `core/ext.json` by `$ref`, and it yields 2
classes; `protocol-envelope.json` 78 → 1. The work is shrinking the carve-outs:
`PRESERVE_CANONICAL_URL_REFS` (3 paths) and the macro refs forced absolute.

Census: 2216 model names defined in more than one module, **809 with a differing declaration
under one name**. Worst: `Creative` 9 modules / 8 shapes, `Account` 8/8, `Scope` 14/6,
`Location` 14/4. Nothing checks shape compatibility.

`Error` is a naming defect, not a reuse failure: `get-task-status-response.json` and
`tasks-get-response.json` declare inline anonymous `properties.error` objects, genuinely
distinct shapes, correctly generated, **named `Error` from the property name**.

**The sibling-document copy has a different cause, and `--allow-remote-refs` is not it.** A
root `allOf` whose single member is a `$ref` to a document whose own root carries `oneOf` or
`anyOf` makes the generator re-parse the target's arms under the referring schema's name and
path, minting every arm again. A discriminator makes no difference, and local relative refs
reproduce it, so "local refs give zero duplication" holds for plain-object targets only. The
site is `datamodel_code_generator/parser/jsonschema.py:3379-3388` in `_parse_all_of_item`;
the plain-object branch at `:3390` does the right thing, adding a reference, a base class, and
an import, and the fast path at `:3544` never applies to a file reference.

This is a generator defect rather than a schema one: `allOf: [{$ref}]` is draft-07's only way
to keep a `title` beside a `$ref`, so the schemas are written correctly and nothing goes
upstream.

Of the bundle's 113 root single-`$ref` `allOf`s, 100 target an object (36 already inherit
cleanly), 10 sit under `mcp/` which the generator excludes, and 3 target a `oneOf`. Only two
of those three are defects: `media-buy/accept-proposal-response.json` and
`media-buy/buy-products-response.json` add no narrowing, so the copy is pure duplication,
while `core/package-signal-targeting.json` adds properties, which makes distribution the
correct output and the source of the `PackageSignalTargeting4..7` chains. **A fix that
collapses that third case is wrong.**

### 4.3 An `allOf` enum narrowing is lost — P3 violated

`media-buy-commitment-response.json` narrows `warnings[].code` to two members; the generated
model accepts a third. `jsonschema` rejects the payload, `model_validate` accepts it. The
merge **unioned** the vocabularies and left `_1`-suffixed aliases of its own members as the
tell. The `const` case is correct, so the defect is specific to `enum`. **Scope not
established**: one site demonstrated, no sweep run, and the sweep is a prerequisite.

### 4.4 Two declaration forms for one kind of name

`aliases.py` (pin): 136 plain assignments, 98 annotated `X: TypeAlias = Y`. Only the plain
form can be inherited from (`Invalid base class [misc]`). 92 of the 98 resolve to a class and
6 to unions, which are uninheritable in any form. No rule separates the groups:
`CreateMediaBuySuccessResponse` and `UpdateMediaBuySuccessResponse` have identical roles and
are declared two different ways. **Dropping the annotation is the cheapest item here.**

### 4.5 The `ActivationKey` names were wrong on day one

Two of them are not in `aliases.py` at all: `_eager.py:1097-1098` (pin) declares
`PropertyIdActivationKey = SegmentIdActivationKey` and
`PropertyTagActivationKey = KeyValueActivationKey` as **synonyms**. And they were never
correct: at `5c63decdd` (#47, 2025-11-16) `aliases.py:143` bound the property-id name to the
*first positional arm*, with the docstring "using property_id for identification", while the
activation-key schema at that same commit had two arms, segment-id and key-value. That history
comes from git at `5c63decdd` and is not re-verified against the wheel.

They are compat synonyms, mislabeled at birth rather than drifted from a wider schema, which
means they leave through the deprecation staging in §5, not silently.

---

## 5. Implementation: one structural change, and the constraint that forces it

**The governing constraint, from the user: this is the second large rewrite of this surface in
a month, and there must not be a third.** A staged sequence is therefore rejected: seven stages
produce *three* separate public-surface breaks (aliases become derived; classes get renamed;
duplicate classes disappear), each wanting its own deprecation window, its own snapshot
regeneration, and its own round of adopter churn. That is the pattern being complained about,
written down as a plan.

The rule instead: **every change that moves a public name happens in one release, or it does
not happen.**

The only item that forces a second break is the namespace flattening, and P8 rejects it rather
than defers it. Everything else lands together as one change. The narrowing fix moves a public
name, so it is inside the change (item 7); the success-arm rule and the naming-function pair
are stated in item 1; the layer decision is item 2; where the deprecated positional aliases
live is item 8.

### Before the change — additive only, no public name moves

Neither item touches a name, so neither is a rewrite and neither needs staging. They land
first so that the one structural change is *measured* rather than asserted.

- **The P3 instrument, and the sweep it runs (P3).** Build the accepts-iff-schema-accepts check
  as a **sampled** property test over every generated class: the bundle resolves offline once
  the version derivation of item 6 is in, 113 of 1057 schemas carry root `examples` as a payload
  source, and one negative per node is generated (a required field removed, an enum value
  replaced). It is not total, and that is acceptable: at the pin nothing checks P3 at all. Run
  it to find every `allOf`+`enum` narrowing site (§4.3) and every other divergence; record the
  list in the pull request, not in the tree. **The fix to the merge is NOT here**; see item 7.
  It removes enum members, and an enum member is a public name. There is no `extra=` assertion
  to write: the generator derives `extra` (P3).
- **The root schema accessor (P8).** One function at the package root taking a schema name,
  beside `adcp.schemas.load_schema`. An added name; no name moves.

**Do not commit a shape fixture.** Under P10 it fails: it records whatever the tree held when
someone committed it, and a fixture committed at the pin blesses the four mislabeled
activation-key names exactly as `test_public_api.py` did. Its legitimate use is proving that
the one change did what it claims, and that is a **before/after diff attached to the pull
request**: take the snapshot before, diff after, commit nothing. `SCHEMA_DELTAS.md` produces
it (`generate_types.py:1704-1712`). Once P1 lands, the swap the fixture exists to detect cannot
occur.

### The one change

Seven things that each move public names, landed together because landing them apart is seven
breaks instead of one. The order of the list is a dependency order, not a sequence of releases:
(2) is a decision the rest read; (1) and (4) change what exists; (3) derives the bindings over
the result; (5) and (6) are independent of all of them.

1. **Name every union branch by the resolution rules (P1), and emit the response base with
   dispatch.** Delete `post_generate_fixes.py:6454`'s index naming, `:6449-6453`'s reorder,
   and `:6408-6411`'s `endswith("1")` success detection. **A `status` const does not find the
   success arm**: on `create-media-buy-response.json` and `update-media-buy-response.json`
   (pin) the success arm carries no const, the error arm carries none, and only the submitted
   arm pins `status: submitted`; the commitment response pins all three. The rule that holds on
   every response root in the bundle: the arm that gets `_normalize_legacy_status` is the one
   whose schema requires neither `errors` nor `task_id`; the backfill exists precisely for the
   arm whose status the schema leaves unpinned. Two naming functions exist at the pin, and they
   disagree on 115 root titles (`A2UIBoundValue` / `A2UiBoundValue`, `CSSAsset` / `CssAsset`):
   `union_branch_names.pascal_case` and `generated_names.generated_root_class_name`, the latter
   being what names the wheel's root classes. The resolution rules keep deriving the *branch*
   name (titled branches: 0 of 302 disagree) and take the *parent prefix* from
   `generated_root_class_name`, so a const- or required-set-named branch shares its base class's
   spelling; 5 roots change under that rule (`a2ui/bound-value`, `adagents`, `daast-asset`,
   `vast-asset`, and one more), none of which has shipped. `_schema_title_to_class_name`, which
   the pin deleted as wrong for 94 of 946 roots, stays deleted. Route the response-arm emitter
   through `emit_branch_classes` (`post_generate_fixes.py:8778`, pin) so that the response base
   carries `BranchDispatchMixin` like the 19 partitioning roots (§3.1 axis B).
2. **The layer, decided (P5).** A semantic name on `adcp.types` binds to the
   `canonical_creative` subclass where the canonical layer declares one, and to the generated
   class otherwise; the domain path always binds the wire-faithful generated class. This is
   what the pin does for every canonical name (`Product`, `Format`, `Package`,
   `CreateMediaBuyRequest`, … all resolve to `adcp.types.canonical_creative`) and what
   `canonical_creative.py:1-6` (pin) says the layer is for: "the primary application-facing
   models". Writing it down changes nothing at the pin; it decides what items 1 and 3 emit. The
   rename in item 1 therefore produces `domains.media_buy.CreateMediaBuySuccess` (generated) and
   `adcp.types.CreateMediaBuySuccess` (canonical subclass of it), the same pairing `Product`
   has at the pin. **A caller who needs the wire-faithful arm as a base class imports it from
   the domain path.** This repo does (`src/core/schemas/_base.py:107-112` subclasses the
   generated arm), and the comment at `_base.py:1261` that calls the base
   `CreateMediaBuySuccessResponse` is wrong about which layer it subclasses; correct it when the
   imports move.

   **The layer is deliberate.** Commit `b5c6f1644` (2026-07-29, #994) is a breaking release
   titled "make canonical models primary in v7", and `canonical_creative.py:1-7` states the
   purpose: legacy named-format identity removed at every depth. So this pairing implements a
   decision rather than codifying an accident.

   **Membership is hand-maintained and has drifted, so derive it.** Of 940 public names, 862
   resolve into `domains` and 43 into `canonical_creative`. Three of the 33
   `PRIMARY_CANONICAL_MODELS` are shadowed on `adcp.types` by a generated class: `MediaBuy`
   resolves to `domains.core.media_buy.MediaBuy`, which is not the canonical class's parent;
   `MediaBuyPackage` resolves to `get_media_buys_response.Package` through
   `_generated.py:3761`; and `DeliveryCreative` resolves to
   `get_creative_delivery_response.Creative`. A fourth inconsistency mixes layers inside one
   union: `GetProductsSuccessResponse` is canonical while `GetProductsSubmittedResponse` is
   generated. The rule stated earlier — canonical if and only if the canonical layer declares
   one — flips exactly those three names and that union, and replacing the membership list
   with the rule is what stops the drift recurring.
3. **Derive the whole binding layer (P5).** `aliases.py`, `_eager.py`, both `__init__` files,
   `KNOWN_COLLISIONS`, and the hand-written `TypeGuard` functions (`guards.py`,
   `_EAGER_ONLY_EXTRAS`) are generated from the module tree under (2), with the 98 `TypeAlias`
   annotations gone. Depends on (1), (2), and (4) having run.
4. **Local refs only (P2).** Shrink `PRESERVE_CANONICAL_URL_REFS` to empty and fix the
   sibling-document alias case. This is in the same change because removing a duplicate class
   removes a public name. It also collapses 190 of the 335 intra-domain duplicate names (the
   identical-shape ones), which is what makes the DX9 residue 145.
5. **Refuse the deep import (P8).** No flattening. The domain root binds once-declared
   names; add the rule that refuses an import naming a generation subdirectory
   (`domains.core.assets.<module>`) or an underscore module, and nothing else moves. It is in
   the change rather than before it only because the refusal is what the deprecation shim in
   (8) is measured against.
6. **Derive the spec version (P9).** Replace the `/3.2.3/` → `/3.2/` symlink and every version
   literal with the derivation, failing closed when no bundle matches.
7. **Intersect the `allOf`+`enum` narrowing (P3).** The fix for the sites the P3 instrument
   finds. At the one known site it deletes `Code.inventory_shortfall_forecast_1`,
   `Code.flight_change_creates_pacing_risk_1`, and `Code.fields_ignored_due_to_precedence` from
   `media_buy_commitment_response.py:37-42` (pin), three public enum members, so it belongs
   here and not in the additive set.

8. **Where the deprecated positional names live, decided.** Every positional name
   (`CreateMediaBuyResponse1`, …) is emitted as an alias **in the module that declares it at
   the pin**: the schema module, the domain root, and `adcp.types` for the ones exported there.
   Each alias binds to the renamed class and raises a `DeprecationWarning` on access through
   the module's `__getattr__` (the mechanism `adcp.types` uses for `generated_poc`, pin).
   Because no module path moves (item 5), a deep import of a positional name keeps working for
   the whole window, which is the only reading of §7's "aliases through one major" under which
   the promise means anything to the callers who import deep. Item 3's derivation generates the
   aliases, nothing hand-lists them, and the following major deletes them. Nothing goes behind
   a `domains` shim, because `domains` is not moving.

Emitted together: semantic names as the real classes, positional names as deprecated aliases
where they are at the pin, one snapshot regeneration under review (`test_public_api.py:505-520`'s
`repointed` check fires for every renamed class, which is intended), one `DeprecationWarning`
cycle, one major for removal.

### After, and not part of it

- **One metadata PR upstream:** a `title` for
  `content-standards/get-content-standards-response.json#/oneOf/0`, the single branch the
  resolution rules cannot name.
- **The nested positional names** (~1045) stay. The root-branch resolution rules do not reach
  them, this document has no rule for them (§8), and inventing one is the third rewrite. They
  are ratcheted shrink-only and left alone until a rule exists that is worth one more break.
  This is also why the schema module stays public (P8): 145 of them share a bare name with a
  differently shaped sibling in the same domain, and the schema module is the only path that
  names them.

**For this repo:** the 108 `adcp.types.domains` import statements (33 files, 124 names) keep
resolving through the window; the 15 positional names among them move exactly once, after the
change, in one commit, to the domain path of the renamed generated class. Not to the
`adcp.types` alias: that is the canonical layer (item 2) and a base-class change this repo has
not asked for.

---

## 6. Guards: keep, replace, delete

The table gives each guard a verdict and the reason for it. Three of the guards are essential
and stay; the code that pins the positional names is the emitter's own, and it goes.

| Guard | Verdict | Why |
|---|---|---|
| `run_datamodel_codegen.py` order patch | **KEEP** | P7. Deleting it first makes `--check` disagree between APFS and ext4, the bug it fixed. Retire when zero classes are traversal-named. |
| `tests/test_public_api.py` 7944-name snapshot | **REPLACE**, then **DELETE** | A blessed value (P10). It held the four mislabeled activation-key names green. Replace it with the derived bare-slot rule: bind a bare `_generated` slot only when every definition under the name has one shape, else leave it unbound. Under derived names, repointing is unrepresentable. |
| `make validate-generated` byte compare | **KEEP** | The one check with no blessed value: committed tree equals `f(schemas, pinned generator)`. P7 is what makes that a function. |
| `post_generate_fixes.py:6454`, `:6449-6453`, `:6408-6411` | **DELETE** | These *are* the positional naming and its defenses. The most directly defect-preserving code in the pipeline. |
| `KNOWN_COLLISIONS` (13 at pin) | **REPLACE** then delete | Its comments state the rule 13 times by hand. Derive it; keep `_enforce_every_class_is_reachable` and `test_collision_guard.py`. |
| `scripts/collision_allowlist.json` | **DELETE** before the change | Dead; referenced only from a doc. |
| `PRESERVE_CANONICAL_URL_REFS` | **REPLACE** | A carve-out, not a guard. Shrink to empty, then fail the build on any surviving remote ref. |
| `stabilize_inlined_core_refs` | **DELETE** with §5 item 4 | Exists only because of remote refs. |
| `stabilize_nested_discriminators` | **KEEP** | Unrelated to refs: it drops a flattened duplicate discriminator pydantic rejects at import. |
| `_eager.py:1097-1098` synonyms | **DELETE** via staging | Mislabeled at birth; still a compat surface. |
| 98 `TypeAlias` annotations | **DELETE** | §4.4. |
| `test_asset_aliases_stable.py`, `test_collision_aliases.py` | **DELETE after the change** | Hand-listed expectations per alias, which are blessed values. Until the change they are the only thing holding the hand table honest; afterwards the alias *is* the derivation and they assert a tautology. |
| `test_lazy_types.py::test_partial_modules_avoid_numbered_codegen_names` | **KEEP, widen** | A regex over `__all__`, no blessed value. Widen to the whole surface; it becomes P1's grade. |
| `test_lazy_types.py::test_partial_modules_never_import_generated_layer` | **KEEP** | The guard that refuses the flattening P8 rejects: `adcp.types.media_buy` is a curated partial, not a generated domain. A derived property, no blessed value. |
| `BranchDispatchMixin`, `name_the_combinator` | **KEEP, extend** | The runtime dispatch and the keyword-named refusal (§3.1 B, C). Extend to the response roots through item 1; the hand-written `TypeGuard` functions in `guards.py` are then derived and go with the hand tables. |
| `post_generation_manifest.json` | **REPLACE** | Keep the rule (a fix that changes nothing fails the run), drop the per-fix table. The seven fixes it records as no-ops at this pin are dead code; delete them. |
| `test_union_branch_names.py` | **SPLIT** | Keep the partition identity (`named + classless + refused == total`) and the single-refusal assertion, both derived. Drop the five equality counts (557/169/82/27/1); they are a ledger. |
| `union_branch_names` rule 4 (fail closed) | **KEEP** | A build failure, not a value. This is P1's enforcement, and it is what found the one unnameable arm. |
| `_enforce_every_class_is_reachable` | **KEEP** | Derived; found #911. |
| `test_canonical_models_are_subclasses.py`, `test_export_surface_is_derived.py` | **KEEP** | Properties over the live tree. |
| shape fixture | **DO NOT ADD** | P10. A one-off before/after diff in the pull request instead. |

**Churn versus correctness.** P1 *requires* the positional→semantic rename of response arms,
so it beats the emitter sites that defend the numbering. Re-exporting `Warning` on
`adcp.types` is ergonomics, and P6 argues against it, so it loses. Switching salesagent's four
"switchable" imports to the `adcp.types` aliases is neither: under §5 item 2 those aliases are
the canonical layer, and this repo subclasses the wire-faithful arm, so the imports move to the
renamed domain-path class and nowhere else.

---

## 7. What must not change

- Every class named by its schema title (`CreateMediaBuyRequest`, `Product`, `Warning`, …)
  keeps its name. The resolution rules name branches, not roots, and the parent prefix they
  use is the generator's own root name (§5 item 1), so the change renames no root.
- **Every module path that resolves at the pin keeps resolving.** `adcp.types.domains.<d>`,
  `adcp.types.domains.<d>.<schema>`, and the curated partials `adcp.types.media_buy` /
  `.creative` / `.signals` / `.protocol` / `.buyer` / `.seller`. The flat target is occupied,
  and the deep path is the only one for 145 names (P8), so the deep paths stay. The change adds
  a refusal of the paths that were never a contract: generation subdirectories and underscore
  modules.
- The `generated_poc` → `domains` deprecation window, closing in v10 as the pin states. Nothing
  in §5 opens a second one over the same paths.
- The 136 plain-assignment alias *names*. Only their provenance becomes derived.
- The request-side split classes the pin emits
  (`CreateMediaBuyRequestExplicitPackagesWithFixedAllocation`, …), which are correct under P1.
- `_generated` bare-name resolution for every non-colliding name.
- The codegen flags (`--strict-types bool int float`, `--reuse-model`, `--use-annotated`, …),
  `rewrite_refs` itself, and `flatten_validation_oneof`.
- `adcp.types`' PEP 562 lazy mechanism, and the per-domain lazy facades. §5 item 3 generates
  the *contents* of `__init__` / `_eager.py`; it does not replace the loading shape.
- Positional names as deprecated aliases through one major, **at the module that declares them
  at the pin** (§5 item 8).
- `BranchDispatchMixin`'s four-path dispatch on the 19 roots that have it, and the `anyOf` /
  `oneOf` keyword on their refusals. Item 1 adds roots to it; nothing removes one.

---

## 8. Not established

What the design rests on that is not yet measured, and what would measure it:

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
- Whether the 98 `TypeAlias` annotations were deliberate. No rule or comment found.
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

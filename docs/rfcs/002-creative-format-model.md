# RFC: Re-engineer the creative format model on canonical format kinds

**Status:** Request for comment
**Scope:** AdCP 3.1.1 (pinned), 3.1.21 (published stable), 3.2.0-rc.1 (in flight)
**Decision proposed:** Canonicalize creative format identity internally on `format_kind`. Treat
`format_id` as a retained buyer assertion that business logic never keys on. Deliver the data
model, migration, tools, and adapters as one feature, and fold the SDK schema migration into
it.

## Summary

The sales agent implements the creative format model that AdCP replaced in 3.1. It stores
format identity as a name across three columns, resolves that name against a creative-agent
registry, and compares it without canonicalization in four places. It accepts the 3.1+ identity
at the request boundary and implements nothing behind that boundary.

A compatibility shim cannot close this gap, because the two models resolve in opposite
directions. AdCP defines a normative six-step order for projecting a legacy `format_id` onto a
canonical kind, and forbids deriving a `format_id` from a kind. Four canonical kinds carry
`v1_translatable: false` and can never have a legacy form. A subsystem keyed on `format_id`
therefore has no way to represent a spec-legal 3.1+ creative. Reversing which side is canonical
is the only change that gives it one.

**The format model is the stable part of the specification.** Across every published release,
`canonical-format-kind.json` holds the same 13 values from 3.1.1 through 3.1.21, and
`creative-asset.json` holds the same two branches with the same required fields. 3.2.0-rc.1
changes the model additively: three new kinds, identical branches, identical requirements. The
open-enum promotion mechanism behaved as the schema documented. Building on `format_kind` is a
safe bet today, and it is the one representation both directions share.

**The defects sit in the schemas around the model.** For six patch releases,
`list-creatives-response` could not report a creative that `sync_creatives` accepted.
`list-creative-formats-response` still enumerates 16 of 21 asset types. Both are drift between
artifacts rather than flaws in the identity design.

**Most of the breakage belongs to this repository, and it is long-standing.** 82 open issues
here touch creative formats. They are not 82 independent bugs. They are a handful of root
causes emitting symptoms, and the largest cause is that this codebase never adopted the 3.1
model.

## The version position

| | Version | Source |
|---|---|---|
| This repository pins | **3.1.1** (`adcp==6.6.0`) | `pyproject.toml` |
| Published stable spec | **3.1.21** | `dist/schemas/latest.json` |
| Latest stable SDK | **7.0.2** (spec 3.1.15) | PyPI |
| In flight | **3.2.0-rc.1** spec, `8.0.0b14` SDK | `dist/schemas/3.2.0-rc.1/`, PyPI |

The pin trails by 20 patch releases, and one blocking defect is already fixed upstream, out of
reach at this pin.

[Upgrade adcp SDK from 6.6.0 to 7.0.2](https://github.com/prebid/salesagent/issues/2138)
describes `format_ids` → `format_options` and `measurement` → `delivery_measurement` as
breaking schema renames. The schemas disagree. `core/product.json` carries both `format_ids`
and `format_options` in 3.1.1 and in 3.1.21, marks neither deprecated, and joins them with a
root `anyOf` requiring at least one. It carries `delivery_measurement` as deprecated in both.
The rename applies to the SDK's generated class names rather than to the wire contract. Plan
the bump against the schemas.

## Part 1: What the specification requires

### Identity is an object, and the two identities resolve asymmetrically

`core/format-id.json` requires `agent_url` and `id`, with optional `width`, `height`, and
`duration_ms` that pin a template to a variant. The schema states the rule outright: "A JSON
object — never a plain string… Using a plain string here is a schema violation." Callers
comparing two values MUST canonicalize `agent_url` first.

`core/creative-asset.json` is a root `oneOf` over two branches:

| Branch | Requires | The schema's own title |
|---|---|---|
| 1 | `format_id` | Legacy creative (named-format reference), "remains supported through 4.x" |
| 2 | `format_kind` | 3.1+ creative (canonical format kind), introduced by RFC #3305 |

`format_id` on an upload is therefore the legacy branch of 3.1.1 itself, rather than a
pre-3.1.1 artifact. Refusing it refuses a spec-legal request.

The asymmetry between the branches carries the argument for the proposed direction:

- **Legacy resolves to canonical.** `registries/v1-canonical-mapping.json` defines a six-step
  normative order: the seller's `v1_format_ref`, then an explicit `canonical` field, then a
  registry glob, then a structural match, then an ambiguous family, then fail closed. Step 4
  yields a family, which is what a `format_kind` is.
- **Canonical does not resolve to legacy.** The registry is "authoritative for v1 → v2
  projection only", and SDKs "MUST NOT synthesize a v1 `format_id` from the registry by
  inverting structural matches." All seven registry entries published at 3.1 are
  pure-structural, so nothing inverts even on a best-effort basis. Four kinds
  (`image_carousel`, `sponsored_placement`, `responsive_creative`, and `agent_placement`) carry
  `v1_translatable: false`, and the schema calls that unreachability structural.

One direction resolves. The other is forbidden, and for four kinds impossible. The canonical
kind is therefore the one representation every downstream consumer can share. This asymmetry,
rather than any preference about style, is the technical core of the proposal.

### Why the model changed

The pin names the failure mode of the old model directly, in the AAO-convention paragraph of
`v1_format_ref`:

> Without this convention, every publisher's 300x250 ships with a different `v1_format_ref`
> (theirs vs nytimes.example vs cnn.example vs …) and the v1 wire fragments into per-publisher
> namespaces — exactly what canonical-formats was designed to eliminate.

A `format_id` names something someone owns, so the same IAB MREC carried N identities and a
buyer needed per-vendor catalog integration to learn they were the same thing. `format_kind`
replaces a pointer with a description: a closed set of shapes a buyer reasons about
generically, plus open machine-readable parameters per product. Identity survives the change
with a different scope. `format_option_id` remains stable, namespaced to the product instead of
to an agent's global namespace. Shape is global and closed; identity is local and open.

### Stability of the model

| Artifact | 3.1.1 | 3.1.21 | 3.2.0-rc.1 |
|---|---|---|---|
| `canonical-format-kind` values | 13 | 13, identical | 16, adding `audio_vast`, `coordinated_placements`, and `seller_rendered_stateful_display` |
| `creative-asset` branches | `[format_id]`, `[format_kind]` | identical | identical |
| `product-format-declaration` required | `format_kind`, `params` | identical | identical, plus 5 optional properties |

The identity contract held across 20 patch releases and one minor version. The producer-side
enum stays closed, consumers MUST retain unknown values, and new kinds arrive by promotion in a
minor release, which the schema calls "non-breaking by design" and which 3.2.0-rc.1
demonstrates.

### The three-part 3.1+ identity

| Field | Answers | Scope |
|---|---|---|
| `format_kind` | Which canonical shape | Global, closed at 12 kinds plus `custom` |
| `format_option_ref` | Which concrete option of the product realizes it | `{scope: "publisher", publisher_domain, format_option_id}` or `{scope: "product", format_option_id}` |
| `format_id` | Which named format in an agent's namespace | Legacy, global name |

A seller defines a shape outside the enum in two ways: today, as `custom` plus `format_shape`
(a recognized pattern from `core/format-shape-vocabulary.json`) plus `format_schema` (a URI and
digest reference to a fetchable schema); later, by promotion into the enum in a minor release.
The payoff the specification claims for the fetchable schema is that "buyer agents fetch the
schema, validate manifests structurally, and reason about manifests without per-seller
integration code."

### Assets is a slot map by design

Both `core/creative-asset.json` and `core/creative-manifest.json` key `assets` by slot. On the
legacy path each key matches an `asset_id` from the format's `assets` array, such as
`banner_image` or `vast_tag`. On the 3.1+ path each key matches an `asset_group_id` from the
format's `slots` declaration, drawn from the canonical vocabulary registry, such as
`images_landscape`, `video`, `published_post`, or `landing_page_url`. A value is a single asset
object, or an array for slots whose `min` or `max` exceeds 1, such as carousel `cards` or
responsive `headlines`. Each asset carries an `asset_type` discriminator selecting its schema.

### Genuine upstream defects

A bounded list. All are filed, and none touches the identity model.

| Issue | Defect | State |
|---|---|---|
| [list_creatives cannot report a format_kind creative](https://github.com/adcontextprotocol/adcp/issues/7402) | `list-creatives-response` required `format_id` unconditionally, making the `format_kind` branch unroundtrippable | **Fixed in 3.1.7**, invisible at the 3.1.1 pin |
| [list-creative-formats-response asset oneOf omits 5 asset types](https://github.com/adcontextprotocol/adcp/issues/7338) | Triage found a second drift site at `format.json`'s `repeatable_group.assets`, short at 13 of 21 | Open, ready-to-implement, P1 |
| [format_kind typing in the Python SDK](https://github.com/adcontextprotocol/adcp-client-python/issues/1140) | The SDK closes the `format_kind` enum where the specification mandates openness, and admits `custom` without the required `format_shape` and `format_schema` | Open, ready-to-implement |
| SDK, unreported | `adcp.types.CreativeAsset` resolves to `CreativeAsset1`, the legacy branch, at runtime, while mypy resolves the alias to the union | Recorded in code |

All four share one pattern: two artifacts describing the same thing disagree. None invalidates
the identity design, and each makes implementing against it harder.

## Part 2: What this codebase does

### The thirteen gaps

| # | Gap |
|---|---|
| G1 | The boundary admits the `format_kind` branch and the code behind it fails. `CreativeAssetRequest._exactly_one_format_identifier` accepts the branch, then `Creative(**schema_data)` raises `ValidationError` on `format_id: None`. A spec-legal upload clears validation and then fails internally, which is worse than an outright refusal |
| G2 | No resolution machinery exists in either direction. A grep over `src/` finds `format_kind` only inside the validator that admits it and in comments; `v1_format_ref`, `format_options`, `canonical_formats_only`, and `format_option_ref` appear nowhere |
| G3 | `list_creatives` cannot report a `format_kind` creative. Upstream, fixed in 3.1.7 |
| G4 | The ORM has no column for the 3.1+ identity. One wire object, `FormatId {agent_url, id, width, height, duration_ms}`, maps to three columns (`format: String(100)`, `agent_url`, `format_parameters: JSONB`), and none of them holds a kind or an option reference |
| G5 | No creative manifest exists. `core/creative-manifest.json` is the specification's adapter-facing shape, and a hand-rolled dict stands in for it, carrying `{creative_id, package_assignments, width, height, url, click_url, asset_type, name}` |
| G6 | Three non-GAM adapters index `asset["format"]`, a key the live builder never sets, so they raise `KeyError` on contact. GAM, the mature adapter, reads only `creative_id`, `package_assignments`, `snippet`, and `snippet_type` |
| G7 | The SDK closes the `format_kind` enum, and admits `custom` without the fields the specification requires alongside it |
| G8 | `Creative` extends the listing response model and serves three roles: response type, database rehydration, and internal validation vehicle |
| G9 | `assets` is retyped to `dict[str, Any]`, which discards the SDK parent's constrained slot map and its discriminated `asset_type` union. Every coercion branch in the listing code is the bill for that |
| G10 | The request DTO extends the legacy branch by accident, because `adcp.types.CreativeAsset` resolves to `CreativeAsset1` at runtime while mypy resolves it to the union |
| G11 | `Creative.format` is a non-spec alias with three production readers, and it exists only because the database column is named `format` |
| G12 | A request round-trips through a response model so the code can read one field back |
| G13 | The live adapter path supports exactly one impression tracker. The deleted dead converter built a multi-URL list, and its tests were the only record of that capability |

### The 82 open issues, clustered by root cause

82 open issues in this repository touch creative formats. They resolve to seven root causes.

**A. Format identity behaves like a string in a structured model.**
[FormatId does not own its identity](https://github.com/prebid/salesagent/issues/2093) records
four `agent_url` normalizers and no owner.
[MCP idempotency canonicalization crashes on structured format_id](https://github.com/prebid/salesagent/issues/1768)
and [internal CanonicalizationError surfaces as buyer VALIDATION](https://github.com/prebid/salesagent/issues/1679)
are the same defect reaching the buyer.
[list_creatives filter by format_id object](https://github.com/prebid/salesagent/issues/1406)
cannot filter on the object form. The specification mandates canonicalizing `agent_url` before
comparison, and a helper that does so already exists in `src/core/schemas/_base.py`.

**B. The 3.1+ selectors reach the code and the code drops them.**
[3.1+ format selectors accepted then silently ignored](https://github.com/prebid/salesagent/issues/1789)
is G1 on the media-buy path: a package carries three format selectors, the boundary accepts all
three because they arrive inherited from the SDK's `LibraryPackageRequest`, and the code reads
only the legacy one. Together with G1, both write paths, `sync_creatives` and
`create_media_buy`, discard a spec-legal 3.1+ selector without telling the buyer.

**C. `Creative` occupies a request position and a response position at once.**
[Creative occupies both a response and a request position](https://github.com/prebid/salesagent/issues/2121)
records that neither pin restores while it serves both.
[Widened Creative.assets makes the long-video suggestion silently dead](https://github.com/prebid/salesagent/issues/2118)
and [Provenance.verification is the unswept sibling](https://github.com/prebid/salesagent/issues/1910)
are consequences. G8 and G9 state the same cause on the schema side.

**D. Products do not drive format selection.**
[Inventory bundles should drive creative-format selection](https://github.com/prebid/salesagent/issues/1347)
and [Inventory bundles should inherit formats from canonical placements](https://github.com/prebid/salesagent/issues/1348)
describe the intended shape.
[Product edit: format changes silently fail to persist](https://github.com/prebid/salesagent/issues/1238)
and [saving the GAM edit-product form with no edits rebinds format agent_url](https://github.com/prebid/salesagent/issues/1796)
are the write path failing.
[Should format override path silently swallow format-not-found errors?](https://github.com/prebid/salesagent/issues/1091)
asks the resulting question. Under the 3.1 model, a product's `format_options[]` is where
identity resolves. In this codebase the product holds a list of names and resolution happens by
dialling a registry.

**E. The read path cannot report or filter what the write path accepts.**
G3 upstream, plus
[structured CreativeFilters reported but not applied to the query](https://github.com/prebid/salesagent/issues/1502),
[cap concept_ids/statuses/format_ids filter length](https://github.com/prebid/salesagent/issues/1505),
and [harden remaining untyped-blob readers](https://github.com/prebid/salesagent/issues/1779).

**F. Adapters read a shape that nothing produces.**
G5 and G6, plus
[Repeatable Group Assets Not Supported](https://github.com/prebid/salesagent/issues/947) and
[GAM native creatives ignore configured native_style_id](https://github.com/prebid/salesagent/issues/1516).

**G. The format catalog is non-conformant and fragile.**
[Reference creative-format catalog emits pixel_tracker assets the pinned schema does not define](https://github.com/prebid/salesagent/issues/1998)
mirrors upstream #7338.
[Per-format resilient ingestion](https://github.com/prebid/salesagent/issues/1333) records that
one non-conforming format invalidates the whole ingest.
[CI dials the public creative agent](https://github.com/prebid/salesagent/issues/2172) and
[allowlisted silent per-item loop failures](https://github.com/prebid/salesagent/issues/1566)
complete the cluster.

## Part 3: Root causes

Four statements. Each explains a cluster, and patching a call site fixes none of them.

**1. The codebase canonicalizes on the identity that the specification forbids deriving.**
Every downstream consumer keys on `format_id`. Nothing can produce a `format_id` from a
canonical kind, and four kinds never have one, so no correct implementation of the 3.1+ branch
keeps `format_id` as the internal identity. This explains cluster B and G2.

**2. One wire object persists as three columns.** Nothing holds a `format_kind` or a
`format_option_ref`, so even a correctly resolved value has nowhere to live. Every serializer
straddling row and schema pays for this, and naming the column `format` is why the non-spec
`Creative.format` alias exists. This explains cluster A, G4, and G11.

**3. One class serves as request DTO, response model, and persistence shape.** Because it
extends the listing response model, tightening it for one role breaks another. That is why
`assets` widened to `dict[str, Any]`, and that widening is what makes the coercion branches and
the silently dead `isinstance` path necessary. This explains cluster C, G8, G9, and G12.

**4. No adapter-facing contract exists.** The specification publishes one,
`core/creative-manifest.json`. This codebase emits a hand-rolled dict from a single builder,
and three adapters read a key that builder never sets. This explains cluster F, G5, G6, and
G13.

**Why the breakage persists:** each symptom is small enough to patch where it surfaces, so each
one got patched there. A subsystem accumulates 82 open issues that way without any single issue
justifying re-engineering. The work therefore belongs together, as one change rather than an
82-item backlog.

## Part 4: Proposed architecture

### Canonicalize on `format_kind`

`format_kind` becomes the internal identity. `format_id` becomes a retained buyer assertion:
stored verbatim, echoed back on the legacy wire, and never the value that business logic keys
on. The legacy branch survives at the edge, where the code projects an inbound `format_id` onto
a kind through the six-step order.

The resolution asymmetry drives this choice. It also removes `isinstance` branching everywhere
except that edge.

### Resolve at the product declaration

Under the 3.1 model, a product's `format_options[]` declares which canonical kinds the product
accepts and with which parameters. Resolution becomes a lookup against declarations the seller
already published, with no outbound call. The `fetch_format_spec` dial-out belongs to the
legacy branch alone, and its typed failures (429 to `RATE_LIMITED`, 5xx to
`SERVICE_UNAVAILABLE`) stay scoped there.

### A callable discriminator

The stated reason for flattening the `oneOf` is that a failing branch puts a codegen class name
(`CreativeAsset1`) into `issues[].pointer`, where `core/error.json` requires a field the buyer
sent. Pydantic's callable `Discriminator` dissolves that objection, because it selects a branch
by presence and the author chooses the `Tag` names:

```python
def which_branch(v):
    if v.get("format_id") is not None:   return "format_id"
    if v.get("format_kind") is not None: return "format_kind"

Asset = Annotated[Union[Annotated[ByFormatId,   Tag("format_id")],
                        Annotated[ByFormatKind, Tag("format_kind")]],
                  Discriminator(which_branch)]
```

Behaviour against the `RootModel` union it replaces:

| Input | Result |
|---|---|
| Legacy branch | Resolves to `ByFormatId`, same as the union |
| 3.1+ branch | Resolves to `ByFormatKind`, same as the union |
| Missing `name` on the 3.1+ branch | `loc = ('format_kind', 'name')` instead of `('CreativeAsset1', 'name')` |
| Neither identifier | `loc = ()` with `union_tag_not_found`, instead of two branch-shaped errors |

The extra pointer segment becomes a closed two-value set named after real specification fields,
which the pointer builder drops deterministically. A payload carrying neither identifier lands
at the root, which is where a `oneOf` violation belongs.

### One accessor and one identity helper

Downstream code asks the request for its format identity once instead of branching.
`CreativeAssetRequest` has no such accessor, and `Creative` has three ad-hoc ones (`format`,
`format_id_str`, and `format_agent_url`). Build on the existing `format_id_identity()` in
`src/core/schemas/_base.py`, which returns the canonicalized `(agent_url, id)` pair that the
pin mandates for comparison. Adding a second helper beside it recreates cluster A, which exists
because four already compete.

### Split the roles of `Creative`

Three classes take the three jobs: a request DTO built on the discriminated union, a
persistence model, and a response model that keeps the SDK's typed `assets` slot map. The
parent already types it as `dict[Annotated[str, StringConstraints(pattern='^[a-z0-9_]+$')],
AssetVariant | Assets] | None`. Restoring that deletes the coercion branches, which exist only
because the type was discarded.

### Implement the manifest

`core/creative-manifest.json` becomes the adapter-facing contract and replaces the hand-rolled
dict. Adapters consume a typed manifest carrying `assets` plus whichever identity applies.

## Part 5: Work required

### Data model and migration

| Change | Note |
|---|---|
| Add `format_kind` and `format_option_ref` to `creatives` | Nothing holds the 3.1+ identity (G4) |
| Decide between additional columns and one structured identity column replacing `format`, `agent_url`, and `format_parameters` | Open question, see Part 8 |
| Backfill existing rows by projecting stored `format_id` values through the six-step order | Rows that fail to project are the interesting ones. Fail closed and report them rather than guessing |
| Retire the `format` column name | It is the sole reason the non-spec `Creative.format` alias exists (G11) |
| Persist a product's `format_options[]` as declarations rather than as a list of names | Cluster D |

Migrations follow the repository rules: name the schema explicitly in foreign keys, supply a
non-empty `upgrade()` and `downgrade()`, and never modify a migration after commit.

### Tools

- `sync_creatives` accepts both branches, projects the legacy one, and persists the canonical
  kind (G1).
- `create_media_buy` and `update_media_buy` read `format_option_refs` and `format_kind` with
  `params` instead of discarding them
  ([#1789](https://github.com/prebid/salesagent/issues/1789)).
- `list_creatives` reports the canonical identity and applies structured filters to the query
  (G3, [#1502](https://github.com/prebid/salesagent/issues/1502)).
- `list_creative_formats` emits only the asset types the pinned schema admits
  ([#1998](https://github.com/prebid/salesagent/issues/1998)).

### Adapters

GAM is the mature adapter, and it reads only `creative_id`, `package_assignments`, `snippet`,
and `snippet_type`. It never touches format, so the manifest change reaches it cleanly.

Kevel, Triton, and mock index a key the live builder never sets (G6), so they already break on
contact. The choice is between fixing three adapters against a contract that does not exist yet
and declaring them unsupported until the manifest lands. Declaring them unsupported needs a
carve-out for mock, because the whole test harness and every BDD scenario run on mock.

### Error taxonomy

Nothing needs wiring. `src/core/errors/codes.py` builds `CODE_TABLE` by loading the published codes from
`enums/error-code.json` inside the installed wheel and unioning this seller's own
`AppErrorCode` values. It is derived rather than transcribed, so a published code is present by
construction. On the pin, 92 published codes plus 8 platform codes give a table of
100, `FORMAT_NOT_SUPPORTED` is in it with `recovery: correctable`, and all 92 published codes
carry `enumMetadata`, so no `recovery` value needs choosing. `FORMAT_NOT_SUPPORTED` even
carries an authored suggestion naming the migration window.

The corollary matters for triage. A spec code missing from `CODE_TABLE` is a gap in the SDK's
schema bundle and belongs upstream, never a task in this repository.

The real defect in this area is the opposite one.
[Map FORMAT_NOT_FOUND to REFERENCE_NOT_FOUND](https://github.com/prebid/salesagent/issues/1847)
is a conformance bug rather than a mapping preference: `FORMAT_NOT_FOUND` is absent from the
pinned enum entirely, so raising it emits a code the specification does not publish.
`REFERENCE_NOT_FOUND` is published, carries `recovery: correctable`, and its suggestion covers
the case. Related:
[creative-sync discards the validation error type](https://github.com/prebid/salesagent/issues/1977)
and
[sync_creatives reports an agent_url failure as CONFIGURATION_ERROR](https://github.com/prebid/salesagent/issues/1790).

## Part 6: The SDK migration belongs inside this work

Moving off `adcp==6.6.0` is a precondition for the read path, because the `list_creatives` fix
landed in spec 3.1.7 and the pin hides it. The question is whether to migrate separately or
inside this feature.

Coupling unrelated work carries a cost, worth paying here for one reason: the schema half of the bump edits the same models this feature rewrites. `Creative`,
`CreativeAsset`, and `PackageRequest` all change shape under 7.x, and all three are the classes
Part 4 splits and re-types. Migrating them first means porting the old creative model onto 7.x
and then discarding that port. That is the patching a separate migration produces, and while
patching does keep each step small, here it means paying twice for the same files.

The bump carries two independent concerns, and the proposal splits by concern rather than by
timing:

| Concern | What it covers | Proposal |
|---|---|---|
| Transport | mcp 2.x streamable HTTP replacing SSE-first, and `protocolBinding: "JSONRPC"` on the A2A agent card | Ship separately and immediately. It has nothing to do with creatives, and any buyer on adcp 7.x cannot reach this agent at all today, which the client sees as "SSE stream ended without a response" |
| Schemas and models | The generated model changes, including the `format_kind` enum closure | Fold into this feature |

`7.0.2` is the stable SDK and carries spec 3.1.15, which contains the 3.1.7 fix. The `8.0.0bN`
line carries 3.2 and stays out of scope while it is beta. Reaching 3.1.21 exactly is not
required; reaching 3.1.7 or later is.

## Part 7: Sequencing

One decision settles before the work starts, because it determines the first lane either way:
what happens to the legacy branch while somebody builds the resolver.

| Option | First lane | Cost |
|---|---|---|
| **A** | Flip the identity, accept both branches, and build the six-step resolver immediately | The resolver up front, including catalog reads. Its refusal is the specification's own fail-closed step rather than an invention |
| **B** | Flip the identity, accept only `format_kind`, and refuse the legacy branch with `FORMAT_NOT_SUPPORTED` until the resolver lands | One refusal, built once, pointing where the design goes. It refuses spec-legal traffic explicitly and visibly |

Taking B first and A as a later lane avoids building a refusal and then deleting it. It also
refuses spec-legal 3.1.1 traffic for the duration, which makes it a product decision rather
than an engineering one. **A and B are the first item in Part 8.**

Refusing `format_kind`, which is the behaviour today, is correct only while `format_id` holds
the identity. The refusal flips when the identity flips, so doing both in the stated order
produces throwaway work.

## Part 8: Open questions

1. **A or B in Part 7.** Whether to refuse spec-legal legacy traffic while somebody builds the
   resolver.
2. **Columns or one structured identity column.** Does `creatives` gain `format_kind` and
   `format_option_ref` alongside the three columns it has, or does one structured column
   replace all of them?
3. **Non-GAM adapters.** Ratify or overrule declaring Kevel and Triton unsupported, with the
   mock carve-out.
4. **SDK coupling.** Ratify or overrule the Part 6 split, which ships the transport fix
   separately and folds the schema migration into this feature.
5. **Where producer-side `custom` validation belongs**, at the seller's boundary or in the SDK.
   Raised in [format_kind typing in the Python SDK](https://github.com/adcontextprotocol/adcp-client-python/issues/1140)
   and unanswered.
6. **`list_creatives` reporting for the four unreachable kinds.** Does the unconditional
   `format_id` requirement get an escape upstream, or does the seller mint a seller-scoped
   synthetic identifier? The latter is a SHOULD on the products path only, and impossible for
   the four kinds carrying `v1_translatable: false`.
7. **3.2 timing.** 3.2.0-rc.1 restructures the product surface, replacing `get_products` with
   `list_products`, `request_proposals`, `refine_proposals`, and `buy_products`, and deprecates
   `list_creative_formats`. The format model survives that additively, so this work is safe.
   The product-side work in cluster D may not be.

## Part 9: Non-goals

- **Fixing the specification.** Upstream defects are filed and tracked, and this work consumes
  their outcomes.
- **The 3.2 product-surface migration.** Separate work, gated on 3.2 shipping.
- **Generative and build paths.**
  [Generative refinement round-trip is unwired](https://github.com/prebid/salesagent/issues/2143),
  [A2A CreativeAsset construction loses generative-build data](https://github.com/prebid/salesagent/issues/2011),
  and [generative build and update paths have drifted apart](https://github.com/prebid/salesagent/issues/1746)
  touch creatives without touching format identity.
- **A backlog sweep.** The 82 issues are evidence for the root causes rather than a work list.
  Most close as a consequence of the four fixes in Part 3. Re-triage the rest afterwards.

## Sources

| Claim | Where to check it |
|---|---|
| 3.1.1 schema text | The vendored `_schemas/3.1` set inside `adcp==6.6.0` |
| 3.1.21 and 3.2.0-rc.1 schema text | `dist/schemas/3.1.21/` and `dist/schemas/3.2.0-rc.1/` in the AdCP repository |
| Published spec and SDK versions | `dist/schemas/latest.json`, and the `adcp` project on PyPI |
| `CODE_TABLE` contents | `src/core/errors/codes.py`, which loads `enums/error-code.json` from the installed wheel |
| The behaviour of every gap in Part 2 | The file and symbol named in the row |

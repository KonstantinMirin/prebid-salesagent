# RFC: Re-engineer the creative format model on canonical format kinds

**Status:** Request for comment
**Scope:** AdCP 3.2.1 (pinned, `adcp==9.0.0b3`), bundle `schemas/cache/3.2`
**Decision proposed:** Author products canonically on `format_options[]`, which the pin
requires. Canonicalize creative format identity internally on `format_kind`. Treat `format_id`
as a retained buyer assertion that business logic never keys on, and project to it outbound only
from a seller-asserted `v1_format_ref`. Call the SDK's projection and advisory machinery rather
than reimplementing it.

**Revision note.** Parts 1 through 5 were written against AdCP 3.1.1 and argued the canonical
direction from the resolution asymmetry. The pin now states that direction outright, so
[Part 10](#part-10-the-canonical-authoring-contract) carries the obligation text and the
authoring contract that Parts 4 and 5 leave out. Part 6 is superseded, and
[Part 11](#part-11-what-grades-each-obligation) names what grades each obligation. Read
Part 10 first if you are implementing.

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
| This repository pins | **3.2.1** (`adcp==9.0.0b3`) | `pyproject.toml`, bundle `schemas/cache/3.2` |
| Canonical format kinds | **16** values | `core/canonical-format-kind.json` |
| Published error codes | **120** | `enums/error-code.json` |

The 3.1.1 pin this RFC was written against trailed the published spec by 20 patch releases, and
the `list_creatives` defect it names was fixed upstream out of reach of that pin. Both are
closed: the epic moved the pin to 3.2.1, which is why Part 6 is superseded.

The format model survived the minor-version move exactly as the schema said it would.
`canonical-format-kind` grew from 13 values to 16 by promotion, `creative-asset` holds the same
two branches, and `product-format-declaration` still requires `format_kind` and `params`. What
3.2 added is the authoring direction, stated normatively, plus the placement and locale rules
Part 10 covers.

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

| Artifact | 3.1.1 | 3.1.21 | 3.2.1 (pinned) |
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

**This section understates `format_options[]`, and the understatement is the gap this RFC was
reopened to close.** A lookup target for an inbound legacy id is the smaller half of its job.
Under the pin, `format_options[]` is the catalog the seller AUTHORS, and `format_ids` is the
projection a seller may publish beside it. Part 10 carries that obligation and the contract a
declaration has to satisfy.

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

## Part 6: Superseded — the SDK migration landed

This part asked whether to migrate off `adcp==6.6.0` separately or inside this feature, and
recommended folding the schema half in while shipping the transport fix separately. The question
is closed: the pin is `adcp==9.0.0b3` at spec 3.2.1, past both the 3.1.7 `list_creatives` fix
and the 7.x shape changes this part planned for. The reasoning is kept below because it records
why the two concerns were split, which is still the right split to describe even though the
timing question it served has expired.

What the move changes for the rest of this RFC, beyond the version table:

- **The six-step resolver is no longer the seller's to build.** `adcp.canonical_formats` ships
  it as `project_v1_format_to_declaration`, which walks the documented resolution order, plus
  `project_product_to_v1` for the outbound direction and `check_narrows` for the narrowing
  check. Part 7's sequencing question assumed the seller would write that resolver, and that
  assumption is what made the question hard.
- **Producer-side `custom` validation has an answer.** Open question 5 asked whether it belongs
  at the seller's boundary or in the SDK. The SDK ships `validate_format_kind_in_options` and
  `FormatKindNotInClosedSetError`, so it is the SDK's, and the seller's job is to call it.
- **The advisory channel exists.** `make_sdk_advisory` builds the `errors[]` entry the
  projection rules mandate, setting `source=sdk` and `sdk_id` itself.

The original reasoning follows.

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

### The A-or-B question is closed, and the answer is neither

Both options priced the seller building the six-step resolver. It does not: the SDK ships it
(Part 6). That removes B's whole justification, which was to defer resolver work behind one
refusal.

B is also refused by the pin independently. `core/product.json` requires that "Products MUST
carry `format_ids`, `format_options`, or both during the 3.x migration window", and
`format_ids` is deprecated in 3.2 and removed in 4.0 rather than removed now. A seller that
refuses the legacy branch with `FORMAT_NOT_SUPPORTED` refuses conformant traffic for the whole
3.x window, so B is not available at this pin regardless of sequencing preference.

The first lane is therefore: author canonically, accept both branches inbound, and call the
SDK's projection. Part 10 states what that lane has to produce.

## Part 8: Open questions

Five of the seven below are settled by the 3.2.1 pin or by the SDK that ships with it. They are
kept with their answers, because a reader who finds only the open ones cannot tell whether the
rest were decided or forgotten.

1. ~~**A or B in Part 7.**~~ **Closed: neither.** The SDK ships the resolver, and the pin
   requires the legacy branch to keep working through the 3.x window. See Part 7.
2. **Columns or one structured identity column.** Does `creatives` gain `format_kind` and
   `format_option_ref` alongside the three columns it has, or does one structured column
   replace all of them? **Still open**, and Part 10 adds a constraint on the answer: whichever
   shape wins, the comparable identity it yields must be the kind rather than the legacy pair.
3. **Non-GAM adapters.** Ratify or overrule declaring Kevel and Triton unsupported, with the
   mock carve-out.
4. ~~**SDK coupling.**~~ **Closed.** The pin moved to `adcp==9.0.0b3` and the transport concern
   shipped separately, which is the split this part recommended.
5. ~~**Where producer-side `custom` validation belongs.**~~ **Closed: the SDK.** It ships
   `validate_format_kind_in_options`, raising `FormatKindNotInClosedSetError` when a kind a
   buyer's manifest targets is absent from the product's published `format_options[]`. The
   seller calls it; it does not write its own closed-set check.
6. ~~**`list_creatives` reporting for the four unreachable kinds.**~~ **Closed, and the
   synthetic-identifier option is refused.** `registries/v1-canonical-mapping.json` states that
   SDKs "MUST NOT synthesize a plausible-but-arbitrary v1 `format_id`" and must instead surface
   `FORMAT_DECLARATION_V1_AMBIGUOUS` through `errors[]`. A canonical carrying
   `v1_translatable: false` "never has any v1 form regardless of registry coverage", so there is
   nothing to mint. The reporting path is the advisory, not an invented id.
7. ~~**3.2 timing.**~~ **Closed: 3.2.1 is the pin.** The format model did survive the move
   additively, as this part predicted. The product-surface restructure it worried about is
   separate work and stays a non-goal.
8. **How a seller authors `v1_format_ref`.** New, and the one genuinely open design question
   Part 10 raises. The pin makes `v1_format_ref` the only sanctioned v2 to v1 link and makes it
   seller-asserted, so a seller that wants legacy reach has to record the pairing somewhere an
   operator can edit. Nothing in the product model holds it today.
9. **Whether to publish `placements[]`.** The pin ties the answer to a hard constraint: a
   product spanning multiple publishers that omits `placements[]` must narrow its
   `format_options[]` to the common intersection across every selected publisher scope. A
   seller wanting the union MUST publish `placements[]` with publisher-scoped identities. This
   is a product decision with a schema consequence, not an engineering one.

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

## Part 10: The canonical authoring contract

Parts 1 through 5 argue that the canonical kind is the representation every consumer can share,
and they argue it from the resolution asymmetry. The pin no longer leaves that to inference.
This part carries the obligation text, the contract a declaration satisfies, and the rules the
earlier parts omit.

### The obligation, quoted

`core/product.json`, `properties.format_ids.description`, at 3.2.1:

> Deprecated in AdCP 3.2; removed in AdCP 4.0. Legacy named-format compatibility path. Products
> MUST carry `format_ids`, `format_options`, or both during the 3.x migration window. New
> products MUST author canonical `format_options[]`; sellers MAY additionally project those
> declarations to `format_ids` for legacy buyers. When both fields are present they MUST
> describe the same underlying formats, and buyers MUST prefer `format_options`. Do not author a
> new product from `format_ids` alone.

`properties.format_options.description`, same file:

> New 3.2 products MUST carry format_options; a seller MAY additionally project the same
> declarations to deprecated format_ids for older 3.x peers.

And the root `anyOf` names the two branches, with `deprecated: true` on exactly one:

| Branch | Title | Requires | Deprecated |
|---|---|---|---|
| `anyOf[0]` | Named-format product | `format_ids` | Yes |
| `anyOf[1]` | Canonical-format product | `format_options` | No |

So the direction is a pinned property description with MUST on the authoring side, not a reading
of the registry. The last sentence refuses this seller's current shape by name: `format_ids` is
the authored `NOT NULL` catalog and `format_options` is carried through unauthored.

### What a declaration has to say

`core/product-format-declaration.json` requires `format_kind` and `params`, and offers 15
properties. Five carry obligations an authoring path has to honour:

| Property | Obligation |
|---|---|
| `format_kind` | Required. One of the 16 canonical kinds, or `custom`. |
| `params` | Required. The narrowing of that kind this product accepts. |
| `format_option_id` | "REQUIRED when a product contains multiple declarations with the same format_kind and SHOULD be set on every entry." Buyers "MUST NOT fall back to deprecated format_ids merely because this optional ID is absent." |
| `publisher_domain` | Pairs with `format_option_id` for a publisher-backed option; omitted for a product-local one. |
| `v1_format_ref` | The authoritative v2 to v1 link, an array of `format_id` values. "The v2 declaration's `params` MUST narrow (be compatible with) each referenced v1 format's `requirements`." |

`locale_policy` carries a coupled constraint rather than a standalone one: a declaration
carrying it "MUST set `canonical_formats_only` to true and MUST NOT carry `v1_format_ref`",
because "legacy format_ids cannot preserve this constraint". A seller that wants locale
eligibility therefore gives up legacy reach for that option, by construction and not by choice.

### Outbound projection is seller-asserted, and the SDK emits the advisories

`registries/v1-canonical-mapping.json` states the direction of truth normatively: the registry
is "authoritative for v1 → v2 projection only", v2 to v1 "MUST rely on `v1_format_ref` on the v2
`ProductFormatDeclaration` — sellers assert the v1 pairing explicitly", and SDKs "MUST NOT
synthesize a v1 `format_id` from the registry by inverting structural matches". Step 4 of the
six-step order repeats it for structural matches, which yield a family rather than an id.

Three advisory codes ride on that path, and **the pin assigns all three to the SDK, not to
seller business logic.** Each is in the pin's 120-code enum.

| Code | Raised when | Actor, per the registry text |
|---|---|---|
| `FORMAT_DECLARATION_DIVERGENT` | The narrowing check between a declaration's `params` and its referenced v1 `requirements` conflicts | "SDKs SHOULD run the *narrows* check … surface `FORMAT_DECLARATION_DIVERGENT` on the `get_products` response `errors[]`" |
| `FORMAT_DECLARATION_V1_AMBIGUOUS` | A v2 declaration carries no `v1_format_ref` and a v1-only buyer queries the product | "SDKs MUST surface … via `errors[]` augmentation rather than synthesize a plausible-but-arbitrary v1 `format_id`" |
| `FORMAT_PROJECTION_FAILED` | Resolution fails closed | "SDKs MUST augment the response's `errors[]` array with an entry carrying `source: "sdk"`, `sdk_id: "<package>@<version>"` … `field: "products[N].format_ids[K]"`" |

The consequence for this seller is narrow and worth stating plainly, because Part 5's error
taxonomy section reads as though nothing were owed. Nothing is owed on the code TABLE, which
`src/core/errors/codes.py` derives from the published enum. What is owed is the CALL: the seller
has to run the SDK's projection on the outbound path so the advisories can be produced at all.
It calls none of it today, so no advisory can reach a `get_products` response whatever the SDK
is capable of.

The machinery to call, all from `adcp.canonical_formats`:

| Helper | Role |
|---|---|
| `project_v1_format_to_declaration` | Inbound: walks the six-step order. Replaces the resolver Parts 4 and 7 planned to write. |
| `project_product_to_v1` | Outbound: walks a product's declarations and accumulates refs plus advisories. Additive — it "produces the *additive* set that the seller publishes alongside seller-declared v1 ids". |
| `check_narrows` | Returns one `Divergence` per diverging field, empty when the declaration narrows. |
| `validate_format_kind_in_options` | The closed-set gate, raising `FormatKindNotInClosedSetError`. |
| `find_declaration_by_kind` | Lookup by kind, disambiguated by `format_option_id`. |
| `make_sdk_advisory` | Builds the `errors[]` entry, setting `source=sdk` and `sdk_id` itself. |
| `V1_TRANSLATABLE` | The four kinds with no v1 form: `agent_placement`, `sponsored_placement`, `responsive_creative`, `image_carousel`. |

### Placements layer, and an unresolved reference fails closed

`format_options.description` carries the layering rule, which no part of this RFC covered. When
placements are published, product-level `format_options` are "the union of formats deliverable
somewhere in the product and the upper bound for every placement", and a placement's effective
accepted set is the intersection of three layers:

1. The product's `format_options`.
2. The product placement's inline `format_options`, when present.
3. For kind `publisher_ref`, the named publisher's `adagents.json` catalog narrowing.

Two rules govern the edges, and both are refusals rather than defaults. "An omitted optional
layer is unconstrained, but an unresolved publisher placement or format-option reference MUST
fail closed." And "A product- or placement-level declaration MUST NOT introduce a format outside
the product upper bound." A publisher-referenced placement without inline product
`format_options` therefore "does NOT inherit the full product union" when the publisher catalog
narrows further.

Matching across layers is specified rather than left to equality:

- Publisher-declared options match by `{publisher_domain, format_option_id}`.
- Product-local options match by `format_option_id` when `publisher_domain` is omitted.
- Otherwise, declarations match when they share a `format_kind` and the narrower `params`
  satisfy the broader declaration.

That third rule is the satisfaction relation, and it is the one the four creative-versus-product
gates should collapse into. `format_is_supported` already implements the asymmetric version of
it in the SDK and is "intentionally stricter than `formats_are_equivalent`".

Locale policy follows the same intersection, under RFC 4647 Basic Filtering: with no product
policy a placement may introduce any concrete policy as a narrowing, and with both present
"every placement range must be contained by a product range".

### Creative coverage across placements

One more rule, which bears on assignment rather than on discovery: for a product or package with
multiple included placements, a single creative meant for all of them "MUST lie in the
intersection of every selected placement's effective set". Per-placement creatives MAY use the
union, "but the selected creative set MUST cover every included placement; uncovered inventory
MUST be rejected or refined, never silently omitted".

The closing clause is the one to implement against. Silently omitting uncovered inventory is the
failure mode, and it is the shape a seller falls into by filtering rather than refusing.

### What has to change, and what the measured state is

Stated as the delta from the tree, so the work is bounded. Measured on
`integrate/sdk9-lanes` at `b6e2554c5`, which is the most advanced tree; `main` is 250 commits
behind it and carries none of the partial work.

| Obligation | State |
|---|---|
| A canonical-only product can exist and be served | Done on the integration branch for a product with no inventory profile. `products.format_ids` is nullable (`models.py:390`) and the `format_kinds` filter applies (`products.py:570`). |
| A canonical-only product can be AUTHORED through the admin surface | Absent for profile-linked products. `InventoryProfile.format_ids` is `NOT NULL` (`models.py:2082`) and the class has no `format_options` column, while `Product.effective_format_ids` (`models.py:509`) prefers the profile's arm whenever one is linked. An operator authoring there can only produce the shape the pin tells sellers not to author (salesagent-8qela.154). |
| Business logic keys on the kind | Absent. The only comparable identity is `FormatKey = NewType("FormatKey", str)` (`src/core/schemas/_base.py:445`), built by `format_id_identity()` from a LEGACY `format_id`. |
| One satisfaction function | Absent on every tree. `git grep -E 'def [a-z_]*satisf' -- src/` returns zero on `main` and on the integration branch. |
| Outbound projection from `v1_format_ref` | Absent. `project_product_to_v1`, `check_narrows`, `find_declaration_by_kind`, `validate_format_kind_in_options` and `make_sdk_advisory` are each called in zero files under `src/`. |
| The three advisory codes reach a buyer | Absent. Each appears in zero files under `src/`. |
| Placement layering and intersection | Absent, and not previously designed. See the layering rules above. |
| Creative coverage across placements | Absent, and not previously designed. |

The second row is the structural one. While the only comparable identity is derived from the
legacy pair, every comparison is legacy-keyed by construction, and the inventory of comparison
sites cannot be closed by fixing sites one at a time. The identity type is the fix: if the
comparable identity is the kind, the call sites converge on it because nothing else is
available to compare. That is the same reasoning as the directive against guards — a type that
cannot express the wrong comparison forbids it, where a scan over comparison sites permits it
and reports afterwards.

`FormatKey`'s own comment records that it was once stronger: "the frozen dataclass this replaced
did refuse that at type-check time" (`_base.py:443`). A `NewType` over `str` constrains nothing
at runtime and catches only a direct `str` assignment under mypy.

## Part 11: What grades each obligation

The directive on this stream is that grading is visible system behaviour through the BDD layer,
not guards and not type introspection. This part names what exists, so an obligation without a
scenario is visible as such rather than assumed covered.

Three features grade the canonical product surface today, and all three route through real
environment rows rather than falling through to the setup xfail:

| Feature | Scenarios | Grades |
|---|---|---|
| `BR-UC-GET-PRODUCTS-format-options` | A stored declaration reaches the buyer with its `v1_format_ref` intact; a product declaring none omits the key rather than announcing null; **a canonically-authored product is announced with its declarations and no `format_ids`**; a stored declaration the seller cannot announce is refused rather than half-announced | The authoring direction, end to end |
| `BR-UC-GET-PRODUCTS-canonical-format-filters` | A `format_kinds` filter selects only products declaring one of the named kinds; a `format_option_refs` filter selects on the option's scope rather than its id alone; `standard_formats_only` excludes a canonical product declaring a custom format | The canonical read filters |
| `BR-UC-GET-PRODUCTS-format-id-filter` | Legacy id filtering | That the legacy half still works |

The third scenario in the first row is the obligation of this RFC, graded directly. So the
canonical half is not ungraded where it has been built; the gap is between what the pin requires
and what has been built, which Part 10's table bounds.

**One grading hole, filed as salesagent-8qela.152.** The row routing
`BR-UC-GET-PRODUCTS-canonical-format-filters` is wired but is not pinned in
`EXPECTED_WIRED_ROUTES`, where its three siblings are. Deleting that row would auto-xfail its
three scenarios at fixture setup, grading nothing while reading green, and no guard would
notice. `test_every_wired_env_route_is_still_registered` fails on exactly that tag today, and
its failure text is the fix.

Obligations with no scenario, stated as such:

| Obligation | Grading |
|---|---|
| One satisfaction function governs all four creative-versus-product gates | **Ungraded.** No scenario exercises a canonical creative against a canonical product declaration. |
| Outbound projection from `v1_format_ref`, and its advisories | **Ungraded.** No scenario asserts an `errors[]` advisory on a `get_products` response. |
| Placement layering, three-layer intersection, fail-closed on an unresolved reference | **Ungraded**, and the behaviour is unbuilt. |
| Creative coverage across multiple placements, with uncovered inventory refused | **Ungraded**, and the behaviour is unbuilt. |
| Locale policy intersection under RFC 4647 | **Ungraded**, and the behaviour is unbuilt. |

Creative format identity underpins creative, media buy, packages, and delivery, so a stage that
changes what business logic keys on is graded in all four rather than in the creative features
alone. Grading it only on the creative side is how a regression reaches a media buy.

## Sources

| Claim | Where to check it |
|---|---|
| 3.2.1 schema text, every Part 10 quotation | The bundle at `schemas/cache/3.2` — `core/product.json`, `core/product-format-declaration.json`, `registries/v1-canonical-mapping.json`, `enums/error-code.json` |
| The SDK helpers Part 10 names | `adcp.canonical_formats`, in `adcp==9.0.0b3` |
| The measured state in Part 10's delta table | `git grep` at `integrate/sdk9-lanes` `b6e2554c5`, named per row |
| The grading surface in Part 11 | `tests/bdd/features/BR-UC-GET-PRODUCTS-*.feature`, the `ENV_ROUTES` rows in `tests/bdd/conftest.py`, and `EXPECTED_WIRED_ROUTES` in `tests/unit/test_architecture_measurement_floors.py` |
| 3.1.1 schema text | The vendored `_schemas/3.1` set inside `adcp==6.6.0` |
| 3.1.21 and 3.2.0-rc.1 schema text | `dist/schemas/3.1.21/` and `dist/schemas/3.2.0-rc.1/` in the AdCP repository |
| Published spec and SDK versions | `dist/schemas/latest.json`, and the `adcp` project on PyPI |
| `CODE_TABLE` contents | `src/core/errors/codes.py`, which loads `enums/error-code.json` from the installed wheel |
| The behaviour of every gap in Part 2 | The file and symbol named in the row |

# The persistence mapping layer

**Status:** design, not implemented. Proven on `Creative` first (salesagent-3zmsd).

A domain model is the pinned SDK model the seller extends. A row is what Postgres holds.
Today those are the same object: a repository returns the ORM class, so every caller above it
reads ORM attributes and the domain model carries whatever persistence needed. This document
defines the layer that separates them, for every aggregate rather than for one.

## What is actually wrong today

Measured at `b9138b19c`, adcp `9.0.0b3+sa.8qela.f33d4fc71`:

- **Repositories return ORM rows.** `CreativeRepository.get_by_id(...) -> Creative` is the
  ORM class, not a domain model. There is no `to_domain` anywhere in the repository layer, so
  the row IS the value that flows upward into `_impl` functions and adapters.
- **26 repository classes across 24 modules share no base class.** `BaseUoW` has 12 domain
  subclasses; the repositories below it have nothing in common. So each one hand-rolls its
  own mapping, and there is no single place a rule about mapping could live.
- **Mapping already exists, unnamed and partial.** `repositories/creative.py:49`
  `_identity_columns(identity) -> dict` is a hand-written mapper whose docstring explains that
  `create` and `set_identity` must share it, "which is what happened while the identity was
  three partial columns and each path assigned them itself". That is this layer, for four
  columns of one aggregate, discovered by a bug.
- **16 fields are marked `Field(exclude=True)` on a wire model.** `exclude=True` strips a
  field from the wire *and* persistence *and* the idempotency hash, so each of those fields
  cannot persist where it is declared. They are on the nested domain objects — `Format` (4),
  `Product` (3), `PackageRequest` (2), `AffectedPackage` (2), `SignalDeployment` (2),
  `SyncCreativeResult` (2), `Creative` (1) — and 0 of 14 request DTOs and 0 of 14 response
  models carry one, so the coupling is one level below the tool boundary.
- **Twelve pinned `CreativeAsset` fields have no column** and live inside the `data` JSONType
  blob: `assets`, `component_assets`, `industry_identifiers`, `inputs`, `placement_ids`,
  `placement_refs`, `provenance`, `representation_selection`, `rights`, `tags`, `weight`,
  plus `format_id` (accounted for by `legacy_format_id`). Callers know that layout: the read
  side queries `Creative.data["assets"]` and `jsonb_exists(Creative.data["tags"], tag)`
  directly (salesagent-dufcl).

None of this is a missing patch on one model. It is a missing layer.

## The three models, named

| | what it is | who owns it | may it change? |
|---|---|---|---|
| **domain model** | the pinned SDK class the seller extends, plus the wire serializer | `src/core/schemas/` | the seller MAY extend it; it declares no field that exists only to persist |
| **row** | the SQLAlchemy ORM class | `src/core/database/models.py` | freely — it is private to persistence |
| **mapper** | the one translation between them | `src/core/database/mapping/` (new) | per aggregate |

The domain model stays extendable. That is deliberate and is not what this layer restricts:
a seller may declare a field the pin does not have. What the layer removes is the need to
declare a field *for persistence's sake*, and the `exclude=True` trap that follows from it.

## The interface

```python
class RowMapper(Protocol[DomainT, RowT]):
    """The one translation between a domain model and its row."""

    domain: type[DomainT]
    row: type[RowT]

    #: Columns persistence owns outright: the caller never supplies them and the domain
    #: model never sees them. Derived coverage (below) requires each to be named here.
    repository_owned: frozenset[str]

    def to_row(self, obj: DomainT, /, **owned: Any) -> RowT: ...
    def to_domain(self, row: RowT, /) -> DomainT: ...
```

Three rules make it an interface rather than a convention:

**1. Column coverage is DERIVED, not declared.** At mapper construction, every column in
`row.__table__.columns` must be accounted for by exactly one of: a field of the same name on
the domain model, an explicit per-column override, a member of `repository_owned`, or a
column the database defaults. A column that is none of those raises `TypeError` at import
time, naming the column.

This is the rule that earns the layer. A by-name row copy that omits silently has already
caused a defect in this repo once, and in a shape that could widen auth. The omission set is
computed from `__table__.columns` so a new migration that adds a column breaks the mapper
loudly instead of writing `NULL` quietly. It refuses at construction rather than in a test,
per the epic's directive: write the code so the incorrect representation is impossible.

**2. The blob is the mapper's business, not the caller's.** A pinned field with no column is
mapped into `data` BY THE MAPPER, and read back out by it. `Creative.data["assets"]` stops
appearing in tool code. Where a blob-held field needs to be *queried*, that is a repository
method over a JSON path — the repository still owns queries — but the shape is stated once,
in the mapper, instead of at each call site.

**3. One direction per obligation, and both are explicit.** `to_row` takes the domain object
plus the repository-owned values as keyword arguments, so a caller cannot forget `tenant_id`;
it is a required argument, not a field someone might leave unset. `to_domain` takes a row and
returns a domain model, validated — so a row that cannot produce a valid domain model is a
loud failure at the read, not a malformed response three layers up.

## How it composes with what already exists

Nothing about the Unit of Work changes. It still opens the session, commits on a clean exit,
rolls back on a raise, and repositories hang off it. Nothing about the repository's ownership
changes either: it owns queries, tenant scoping and the business rules about which rows a
caller may see.

What changes is the repository's **return type**:

```python
# today — the ORM row escapes upward
def get_by_id(self, creative_id: str, principal_id: str) -> Creative: ...

# with the layer — the row stays inside
def get_by_id(self, creative_id: str, principal_id: str) -> CreativeAsset | None: ...
```

So the layering becomes:

```
_impl / service        domain models only
    |
repository            queries, tenant scoping, business rules   <- owns the mapper
    |   to_row / to_domain
row (ORM)             private to persistence
    |
UoW                   session lifetime
```

A repository is already named as a persistence edge in CLAUDE.md pattern #4, which is what
permits it to turn a model into a document. The mapper is that permission given a type.

### Where a repository-owned column lives

`Creative`'s columns split cleanly, which is why it is the pilot:

- **domain**: `creative_id`, `name`, `format_kind`, `legacy_format_id`, `legacy_format_key`,
  `format_option_ref` (via `CreativeFormatIdentity` — the existing `_identity_columns`
  becomes the mapper's identity override), and the twelve blob-held pinned fields.
- **repository-owned**: `tenant_id`, `principal_id`, `status`, `group_id`, `strategy_id`,
  `created_at`, `updated_at`, `approved_at`, `approved_by`.

`Creative.principal_id` is currently declared on the DOMAIN model as an added field
(1 of the 51) and is simultaneously an ORM column. Under this layer it is repository-owned
and leaves the domain model — which is the shape the whole exercise is for.

## What this must not become

- **A second representation that drifts.** The point is fewer values, not three. The domain
  model remains the value; the row is a projection; there is no DTO-of-a-row.
- **A generic ORM-to-pydantic bridge.** Per-aggregate mappers with explicit overrides, not a
  framework that infers. `from_attributes=True` already handles the trivial direction; the
  mapper exists for the parts that are not trivial, and those are exactly the parts a
  framework would get wrong silently.
- **A reason to resurrect `model_dump()` in business logic.** The mapper is a named edge like
  the wire and the idempotency hash. A tool still hands the model through.
- **A data migration.** No column moves in the first cut. The mapper describes the schema
  that exists; changing the schema is a separate, later decision with its own gate.

## Proving it on Creative

In order, each step measurable on its own:

1. `src/core/database/mapping/_base.py` — the protocol and the derived coverage check. Its
   own grading is a fire-probe: construct a mapper that omits a real column and confirm it
   raises, then add the column and confirm it does not.
2. `src/core/database/mapping/creative.py` — the `CreativeAsset` ↔ `Creative` mapper,
   absorbing `_identity_columns` and the twelve blob fields.
3. `CreativeRepository` returns domain models. Its ~12 read methods and `create` /
   `set_identity` change signature; the ~18 call sites in `src/core/tools/creatives/` and
   `src/admin/blueprints/` stop reading ORM attributes.
4. `Creative.principal_id` deleted from the domain model, now repository-owned.

**The grading is behavioural, per the epic's second directive.** The creative BDD scenarios
on a2a, mcp, rest and e2e_rest must pass exactly as before, measured on a cassini box run
against a named baseline, judged per nodeid. This change is a refactor: a nodeid that passed
before and fails after is a defect in the mapper, and a nodeid that was xfailed before and
passes after needs explaining before it is believed.

No schema change, no data change, no wire change. If the wire moves, the mapper is wrong.

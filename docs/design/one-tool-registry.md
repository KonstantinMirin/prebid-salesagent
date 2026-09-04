# One tool registry

**Status:** design, not implemented.
**Measured at:** `c7a3a98d5`, 2026-09-04.

## The rule

A tool is declared **once**. Everything else is derived from that declaration:
the MCP tool, the A2A skill, the A2A agent card entry, the REST route, and the
request handed to the implementation.

There is **one builder**. Not one per tool. One.

## What exists today

A tool is declared between **three and four times**, and each declaration can
disagree with the others.

| transport | where a tool is declared | count |
|---|---|---|
| MCP | `_register_tool(fn)` in `src/core/main.py` | 16 |
| A2A | `AgentSkill(...)` literal in the agent card, **and** a row in the `skill_handlers` dict | 13 |
| REST | `@router.post(...)` decorator, **and** a `derived_body_model_for(...)` assignment | 13 |

Plus 16 hand-written `build_*_request` functions.

Three tools — `get_task`, `list_tasks`, `complete_task` — exist on MCP and
nowhere else. Nothing declares that to be deliberate; it is what the three
lists happen to contain.

### The cost, measured

`build_*_request` functions are hand-written subsets of their DTO:

| | |
|---|---|
| DTO fields no builder accepts | **68** |
| builders that take the DTO's field set exactly | 6 of 16 |
| builder parameters that are not DTO fields | 2 (`flight_start_date`, `flight_end_date`, one tool) |

Because all three transports build through the per-tool builder, **all three are
missing the identical set** in 11 of the 13 shared tools. The divergence is not
transport-vs-transport. It is builder-vs-DTO, reproduced three times.

`get_products` accepts **5 of its 21 declared fields**.

## What makes this possible now

Two facts, both measured, that were not true when the builders were written:

1. **Every `_impl` already takes `req`.** All twelve. Three additionally take
   `context_id`, `raw_wire_payload` or `request_hash` — transport-derived values,
   not buyer fields.
2. **Every DTO is, or extends, the SDK's pinned request model.** `_register_tool`
   already refuses to register a tool whose DTO is not SDK-grounded.

So the implementation boundary is already uniform. Only the construction of the
request is not.

## The design

### One declaration

The tool's shape is **a subclass of the SDK's spec model with the unimplemented
fields removed**. That subclass is the whole definition: it is what we announce,
what we validate against, and what we pass around internally.

```python
# src/core/schemas/product.py

@omit("catalog", "fields", "if_pricing_version", "pagination", ...)
class GetProductsRequest(LibraryGetProductsRequest):
    """What this seller implements of get_products.

    The SDK model is the spec. This is the subset we have built.
    """
    TAGS: ClassVar[tuple[str, ...]] = ("products", "inventory", "catalog", "adcp")
```

`@omit` exists only because pydantic inherits fields — a subclass cannot
un-declare one by leaving it out. It removes them after class construction and
rebuilds:

```python
def omit(*fields: str):
    def deco(cls):
        for f in fields:
            cls.model_fields.pop(f, None)
        cls.model_rebuild(force=True)
        return cls
    return deco
```

**`model_rebuild(force=True)` is not optional, and skipping it fails in the
dangerous direction.** `model_fields` is metadata; the validator and the JSON
schema are compiled separately. Popping without rebuilding leaves them stale, so
the class *looks* narrowed and is not:

| after `model_fields.pop("c")` | without rebuild | with rebuild |
|---|---|---|
| `model_fields` | `['a']` | `['a']` |
| `model_json_schema()` | `['a', 'c']` | `['a']` |
| `model_validate({"a":1,"c":9})` | **accepted**, `hasattr(i,"c")` True | rejected |

That is the same three-sets-out-of-step failure this design exists to remove,
occurring inside pydantic. The rebuild is what makes `model_fields`, the
published schema, and the validator one thing.

**Verified against the real SDK model, not a synthetic one.** Applying `@omit`
to the 16 fields no transport accepts today:

```
spec fields before : 21
spec fields after  : 21        <- untouched
ours               : brand, brief, context, filters, property_list
json_schema props  : brand, brief, context, filters, property_list
catalog            : ValidationError
hasattr(catalog)   : False
isinstance of spec : True
```

Forward references in the SDK model resolve; `model_rebuild(force=True)` handles
them. The narrowed set is exactly the five fields all three transports accept
today, which is the measurement this design started from.

Announced, accepted, and implemented are **the same class** — not three sets kept
in step, and not a runtime narrowing applied at three call sites.

### Why a subclass, and what it costs

Pydantic inheritance is additive: subclass and you get all 21 fields. There is no
"inherit these five", so removing them is the only way to narrow while inheriting.

**The narrowing may be permanent.** An earlier version of this document defended
`@omit` on the grounds that the list converges to zero as fields are implemented.
That defence is withdrawn: this agent may be permanently behind a fast-moving
spec, and may deliberately diverge — retiring a field the spec keeps, or keeping
one the spec retires. Nothing operational here depends on the list reaching zero.
A permanent `@omit` list is one line per tool naming the gap.

**This is a Liskov violation, stated rather than discovered later.** The subtype
strengthens a precondition: it accepts a strict subset of what the parent accepts.
Concretely, code typed to `LibraryGetProductsRequest` doing `req.catalog` gets an
`AttributeError` on our instance, and **mypy will not catch it**, because mypy
believes the parent's contract.

It is accepted for one measurable reason: **the victim set is empty and is
cheaply kept empty.** A `Library*Request` used as an annotation or isinstance
target outside `src/core/schemas/` appears once in `src/`, at
`task_management.py:230`, where it is used *as* the DTO with no narrowing — so it
cannot be a victim. LSP is a theorem about consumers; with no consumers it has no
operational content. A guard forbidding `Library*Request` annotations outside the
schemas package is what makes that provable rather than incidental, and it is
part of this design rather than a follow-up.

**What inheritance is actually claiming here is provenance, not
substitutability**: these field definitions come from the spec, unretyped. That
is precisely what `sdk_grounding()` checks by walking the MRO, and it is why
bumping the SDK moves every advertised type with it. Python offers exactly one
mechanism that carries provenance through the type system.

The alternative — `create_model` from the SDK's own `FieldInfo` objects — was
tested and works, with no mutation and no rebuild. It is rejected because it
breaks `sdk_grounding()`'s MRO walk, and rewriting that gate around a declared
`_SPEC_MODEL` link reintroduces the import-spelling dependence the gate was
rebuilt to eliminate. **A reversal threshold is recorded below**, because that
judgement can change.

### The registry is wiring only

```python
@dataclass(frozen=True)
class RestBinding:
    verb: Literal["POST", "PUT"]
    path: str                       # "/media-buys/{media_buy_id}"
    path_fields: frozenset[str] = frozenset()

@dataclass(frozen=True)
class ToolSpec:
    dto: type[BaseModel]            # the subclass above
    impl: Callable                  # async def (*, req, identity, ...) -> Result
    rest: RestBinding | None        # None = not exposed over REST
    a2a: bool                       # exposed as an A2A skill
    auth: Literal["required", "optional"]   # a property of the TOOL, not of a transport

TOOLS: Mapping[str, ToolSpec] = {
    "get_products": ToolSpec(
        dto=GetProductsRequest,
        impl=_get_products_impl,
        rest=RestBinding("POST", "/products"),
        a2a=True,
        auth="optional",
    ),
    ...
}
```

`ToolSpec` says where a tool is reachable and what runs it. It says nothing about
its shape, because the shape says that itself.

### One builder

```python
def build_request(tool: str, payload: Mapping[str, Any]) -> BaseModel:
    """The ONE construction seam."""
    return TOOLS[tool].dto.model_validate(payload)
```

One line, and it replaces all sixteen `build_*_request` functions. It performs
no selection, because the DTO is already the accepted shape — the narrowing
happened at class definition, once, where a reader looking for "what does this
seller accept" will find it.

There is no `supported_model()`, no `UNIMPLEMENTED` set consulted at runtime, and
no cache. A field we have not implemented is not declared on the class, so:

| | `extra="forbid"` (dev/CI) | `extra="ignore"` (production) |
|---|---|---|
| buyer sends an unimplemented field | **rejected**, naming the field | accepted, **field absent from the instance** |
| `hasattr(instance, field)` | — | `False` |

An unimplemented field therefore **cannot propagate on any transport**. This
matters because the transports are not equally protected: MCP validates against
its published schema and would catch a stray field anyway, but **A2A and REST
have no such boundary** — `model_validate` is their only gate. Narrowing the
class is what makes that one gate sufficient.

The alternative — validate against the full spec model and drop unimplemented
fields afterwards — does not work. A field the model *declares* is not `extra`,
so the extra policy never sees it, and it reaches the implementation to be
silently ignored. That is accept-and-ignore: a 200 with no effect,
indistinguishable from having done what was asked.

Nothing else selects. Coercion (`to_account_reference`, `to_brand_reference`,
the brand shorthand) is what `model_validate` already does; those helpers exist
because the hand-written builders bypassed validation, not because pydantic
cannot do it.

A malformed payload raises `pydantic.ValidationError`, which every transport
boundary already translates to `INVALID_REQUEST` with `field` and `issues`
(`adcp_error_for`, checked before `ValueError` deliberately).

### The implementation is typed to OUR model, not the spec's

```python
async def _get_products_impl(*, req: GetProductsRequest, identity: ResolvedIdentity) -> ...:
```

where `GetProductsRequest` is **our narrowed subclass**, never the SDK's model.

**The `*` is a change, not the status quo.** No implementation is keyword-only
today. It is proposed because this design introduces a *generic* call site: the
registry invokes `spec.impl(...)` for every tool, so a parameter added or
reordered in one implementation would silently rebind under positional calling.
Keyword-only makes that a `TypeError` instead. It costs one character per
signature and is worth stating rather than smuggling in.

The direction matters. Ours subclasses the spec model, so
`isinstance(ours, LibraryGetProductsRequest)` is `True` — but
`isinstance(spec_instance, GetProductsRequest)` is `False`. Typing the parameter
to the spec model would therefore accept an instance carrying every omitted
field; typing it to ours cannot, because ours has no such attribute to carry.

So the guarantee is not "the boundary strips unimplemented fields and we trust
it". It is that a value carrying an unimplemented field **cannot be constructed
as the type the implementation accepts**. The narrowing holds at the type level,
checked by mypy, not only at the validation call.

This is the reason the SDK model must never appear in an `_impl` signature. It is
the spec's shape, and the spec's shape is wider than what we built.

### Derived registration

```python
# MCP
for name, spec in TOOLS.items():
    mcp.tool(**_sdk_annotations(name))(_mcp_wrapper(name, spec))

# A2A card + dispatch, from the same mapping
skills = [AgentSkill(id=n, name=n, description=_sdk_description(n), tags=list(s.tags))
          for n, s in TOOLS.items() if s.a2a]
handlers = {n: _a2a_handler(n, s) for n, s in TOOLS.items() if s.a2a}

# REST
for name, spec in TOOLS.items():
    if spec.rest:
        router.add_api_route(spec.rest.path, _rest_handler(name, spec),
                             methods=[spec.rest.verb])
```

There is no `@router.post` to write, no `_register_tool(x)` line to add, no
`AgentSkill` literal to keep in step. The three generators are the only places
that know a transport exists.

### One call path

Every transport reduces to the same three lines:

```python
payload = <transport-specific extraction>      # body, params, or kwargs
req = build_request(name, payload)
return await spec.impl(req=req, identity=identity, **transport_derived)
```

`transport_derived` is a **closed set of three**, not open kwargs. Measured
across all twelve implementations:

| impl | beyond `req` and `identity` |
|---|---|
| `_create_media_buy_impl` | `context_id`, `raw_wire_payload` |
| `_update_media_buy_impl` | `context_id` |
| `_sync_creatives_impl` | `request_hash` |
| the other nine | nothing |

**No implementation takes `**kwargs`**, and none may. The generic call passes only
what the target declares — `accepted_kwargs(impl)` already exists for exactly
this. An open `**kwargs` at this seam would let a transport hand an
implementation anything at all, which is the accept-and-ignore hazard one layer
below the one this design removes.

These three are supplied by the boundary and never by a buyer. `raw_wire_payload`
in particular is the request as sent, captured before normalisation, and exists
because RFC 8785 idempotency hashing needs the payload the buyer actually sent —
not the model built from it.

## Decisions this forces, and the answers

**Internal fields do not belong on a request DTO.** `product_selectors`,
`format`, `page` and `today` are marked `exclude=True` on buyer-facing request
models. They are not buyer input; they are values internal callers set. They move
to an extended model:

```python
class GetProductsInternal(GetProductsRequest):
    product_selectors: list[ProductSelector] | None = None
```

The buyer DTO then declares only buyer fields, `exclude=True` disappears from
requests entirely, and internal callers name the model that has what they need.
Measured: `product_selectors` is read **nowhere** in `src/`; `today` is read once,
by `media_buy_update.py:503`.

This also removes a bug class. `exclude=True` survived a nested `model_dump` and
deleted a buyer's `creative_ids` from a request, producing a cross-principal
acceptance. The marker means "do not send this back"; it silently also meant "do
not accept this". With internal fields on a separate model there is no marker on
the request path to misread.

**Tags belong to the DTO, not to the registry.** The SDK supplies `description`
and per-field descriptions; it carries no tags, so tags are ours — but they
describe the *tool's shape*, like the descriptions beside them, not its wiring.
`DTO.TAGS` sits with them. The agent card reads it.

**Auth is a property of the tool, not of a transport.** It cannot be true that a
route needs a caller over REST and not over MCP. Today it is declared twice —
`resolve_auth` on five REST routes, `require_valid_token=False` in the matching
raw wrappers — and they happen to agree; nothing makes them. `ToolSpec.auth`
declares it once and every transport reads it.

It is resolved **above** `_impl`, in three steps, and a request reaches the
implementation only if all three hold: the route is one that requires a caller;
the credential is valid; the caller is authorized to invoke this tool. `_impl`
receives a `ResolvedIdentity` and makes no auth decision — which is already the
rule (critical pattern \#5) and is unchanged by this design.

**Path fields.** `media_buy_id` comes from the URL. `RestBinding.path_fields`
declares it; the REST generator merges it into the payload before validation.

**`GET /capabilities` is deleted.** It is a second shape for a tool that already
has one: it takes no body, so a buyer cannot send `protocols`, `context`, `ext`
or the version envelope, while the same tool over `POST`, MCP and A2A accepts all
five. One tool, one shape.

**The version envelope.** `core/version-envelope.json` declares `adcp_version`
and `adcp_major_version`, referenced by 68 of 115 pinned request schemas.
**Neither is required.** They are ordinary DTO fields needing no special
handling — which removes the `_VERSION_ENVELOPE_FIELDS` stripping that currently
binds `adcp_version` on 11 REST routes and drops it before the builder. For
`list_accounts` and `sync_accounts` that is a live defect today: the builders
take both parameters and never receive them.

## The known gap, deliberately not closed here

After this lands there is exactly one problem left, and it is the one worth
having:

> the set of fields an implementation honours is smaller than the set its DTO declares.

**68 fields**, listed per tool in the measurement. This design does not fix that,
and — done as step 5 prescribes — does not change a single one of them on the day
it lands. It converts them from invisible to declared.
It makes it **visible in one place** — the `@omit` list on each DTO — where today it
is invisible, spread across sixteen builder signatures, and reproduced three
times per tool.

Populating `unimplemented` is mechanical: it is `DTO.model_fields` minus what the
implementation reads. Deciding what to do about each field — implement, or
announce it as unsupported — is the next piece of work and needs the spec, not
this document.

## The conformance statement is derived, not authored

Standards practice for implementing a subset of a protocol is a **PICS** — a
Protocol Implementation Conformance Statement, *"a structured document which
asserts which specific requirements are met by a given implementation"*. The
`@omit` lists are exactly that, and the statement should be **computed** from
them rather than maintained beside them:

```python
def conformance_gap(dto) -> frozenset[str]:
    return library_declared_fields(dto) - set(dto.model_fields)
```

Both halves exist in `_announced_shape.py` today. There is still exactly one
place specifying the fields — the SDK model minus the omit list — and the PICS is
output. It is what the alignment tests grade against, and it is publishable to
buyers if we choose.

## Two guards this design requires

Not decoration. This narrows a spec type inside the type system, which peer
ecosystems do not do — they untype (Stripe), prune at the boundary (Kubernetes
CRDs), or declare the subset out-of-band (PICS). The scaffolding is what makes
the novelty safe.

**1. The rebuild footgun becomes a test, not a paragraph.** For every registered
DTO, assert `set(model_fields) == set(model_json_schema()["properties"])` modulo
`_NON_SCHEMA_FIELDS`, and that each omitted field actually rejects under
`extra="forbid"`. Forgetting `model_rebuild` then fails loudly instead of leaving
a class that looks narrowed and is not.

**2. No `Library*Request` annotation outside `src/core/schemas/`.** This is what
keeps the LSP victim set empty by construction rather than by luck.

## The alignment suite grades the opposite invariant

`tests/unit/test_pydantic_schema_alignment.py` asserts the reverse of what this
design introduces:

> *"Every property the pinned schema declares is a field on the model. Extra
> model fields are fine (internal use); a MISSING schema field is not."*
> — `test_no_model_is_missing_a_field_its_schema_declares`

and `test_no_model_rejects_a_field_its_pinned_schema_declares` beside it. **Any
narrowed DTO fails both, by construction.** Those tests exist because missing
fields were defects; this design redefines some of them as declared gaps.

They must be renegotiated to: *every pinned-schema field is either declared on
the DTO or named in its omit list; nothing else may be absent.* That is the PICS
made executable, and it is real migration work — it belongs in the step list
below rather than being discovered during step 3.

## Migration order

Each step leaves the tree green and is independently revertible.

1. **Add the registry**, populated from what exists. Assert it agrees with the
   current three declarations. No behaviour change; the assertion is the proof
   the rows are right.
2. **Delete `GET /capabilities`.**
3. **Move internal fields to extended models.** Four fields, three DTOs. No
   buyer-visible change — they are `exclude=True` today, so no transport accepts
   them already. This must precede step 5, because after it the DTO is the
   accepted shape without qualification.
4. **Renegotiate the alignment suite** to grade *declared or omitted* rather than
   *declared*, and add the two guards. This comes BEFORE any narrowing, because
   the first `@omit` fails the current suite immediately.
5. **Narrow the DTO and swap its builder, in one change, per tool.**

   These two cannot be separated, and the order matters in both directions:
   swapping the builder first makes the full DTO the accepted shape, widening
   acceptance to fields nothing implements — accept-and-ignore on up to 16 fields
   for one tool. Narrowing first does nothing, because the builder is still
   selecting. Done together, the accepted set is unchanged on the day of the
   change: the builder's hand-written subset is replaced by the same subset,
   declared on the DTO.

   That is what makes this step *safe* rather than merely staged — it is a
   refactor with no wire change, and every subsequent field is added by
   **shortening an `@omit` list**, deliberately, with its own blast radius
   measured over **payload producers, not constructions of the class**. A
   type-name grep found 76 of 89 sites when that was measured.

6. **Generate MCP registration from the registry**, deleting the 16
   `_register_tool` calls.
7. **Generate the A2A card and dispatch**, deleting the `AgentSkill` literals and
   the `skill_handlers` dict.
8. **Generate REST routes**, deleting the decorators and body-model assignments.

Steps 6–8 are where "declared once" becomes true. Step 5 is the only one that
touches what a buyer can send — and, done as one change per tool, it does not
change it at all.

## Why this needs no guards

The guards that exist today — transport parity, A2A-selects-off-the-tool,
REST-forwards-what-it-declares, builders-respect-declared-defaults — all grade
agreement between declarations that this design deletes. A tool cannot be
registered on MCP and missing from A2A when both are `for name, spec in
TOOLS.items()`. A route cannot declare a field it does not forward when the body
model and the forwarded set are the same object.

They should be deleted as the steps that make their diseases unreachable land,
and not before. Each deletion states which structural change made it impossible.

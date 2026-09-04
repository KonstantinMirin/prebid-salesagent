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

```python
# src/core/tools/registry.py

@dataclass(frozen=True)
class RestBinding:
    verb: Literal["POST", "PUT"]
    path: str                       # "/media-buys/{media_buy_id}"
    path_fields: frozenset[str] = frozenset()

@dataclass(frozen=True)
class ToolSpec:
    dto: type[BaseModel]            # the ONLY declaration of request shape
    impl: Callable                  # async def (*, req, identity, **transport) -> Result
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

`ToolSpec` carries **wiring only**: what the tool is, where it is reachable, and
whether it needs a caller. Everything that describes the *shape* lives on the
shape.

```python
# src/core/schemas/product.py

class GetProductsRequest(LibraryGetProductsRequest):
    """Extends the SDK's pinned request model."""

    TAGS: ClassVar[tuple[str, ...]] = ("products", "inventory", "catalog", "adcp")
    UNIMPLEMENTED: ClassVar[frozenset[str]] = frozenset({
        "catalog", "fields", "if_pricing_version", ...
    })
```

`TOOLS` is the source of truth. Adding a tool is adding a row. Forgetting a
transport is not possible, because all three read the same mapping.

### One builder

```python
def build_request(tool: str, payload: Mapping[str, Any]) -> BaseModel:
    """The ONE construction seam."""
    return _supported_model(TOOLS[tool].dto).model_validate(payload)
```

This replaces all sixteen `build_*_request` functions.

**It does select — and the selection is derived, not written.** `_supported_model`
returns the DTO narrowed to the fields we actually honour: `model_fields` minus
`DTO.UNIMPLEMENTED`, built once and cached.

That narrowing is what makes the unsupported fields behave correctly with
machinery that already exists rather than new machinery. An unimplemented field
is not *declared* on the model we validate against, so it is **extra** — and the
extra policy is already decided and already environment-aware (critical pattern
\#7): `extra="forbid"` in development and CI, `extra="ignore"` in production.
A buyer sending an unimplemented field is refused in CI, where we want to hear
about it, and ignored in production, where forward compatibility matters.

The alternative — validate against the full DTO and drop unimplemented fields
afterwards — is **accept-and-ignore**, the quiet failure CLAUDE.md forbids. The
buyer would get a 200 and no effect, with nothing distinguishing "we do not
support this" from "we did what you asked".

Nothing else selects. Coercion (`to_account_reference`, `to_brand_reference`,
the brand shorthand) is what `model_validate` already does — those helpers exist
because the hand-written builders bypassed validation, not because pydantic
cannot do it.

A malformed payload raises `pydantic.ValidationError`, which every transport
boundary already translates to `INVALID_REQUEST` with `field` and `issues`
(`adcp_error_for`, checked before `ValueError` deliberately).

**The published schema is the same narrowing.** MCP announces
`_supported_model(dto)`, not `dto`, so a field we do not honour is never
advertised. Announced, accepted and implemented become one set by construction
rather than three sets kept in step.

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

`transport_derived` is the three known values — `context_id`,
`raw_wire_payload`, `request_hash` — supplied by the boundary, never by a buyer.

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

**68 fields**, listed per tool in the measurement. This design does not fix that.
It makes it **visible in one place** — `ToolSpec.unimplemented` — where today it
is invisible, spread across sixteen builder signatures, and reproduced three
times per tool.

Populating `unimplemented` is mechanical: it is `DTO.model_fields` minus what the
implementation reads. Deciding what to do about each field — implement, or
announce it as unsupported — is the next piece of work and needs the spec, not
this document.

## Migration order

Each step leaves the tree green and is independently revertible.

1. **Add the registry**, populated from what exists. Assert it agrees with the
   current three declarations. No behaviour change; the assertion is the proof
   the rows are right.
2. **Delete `GET /capabilities`.**
2b. **Move internal fields to extended models.** Four fields, three DTOs. No
   buyer-visible change — they are `exclude=True` today, so no transport accepts
   them already. This must precede step 3, because after it the DTO is the
   accepted shape without qualification.
3. **Replace the sixteen builders with `build_request`**, one tool at a time.
   Per tool, the accepted set grows from the builder's subset to the DTO's full
   set — this is a wire change and each tool needs its blast radius measured the
   way `prkv.68` and `prkv.86` were: **count over payload producers, not over
   constructions of the class**. A type-name grep found 76 of 89 sites there.
4. **Generate MCP registration from the registry**, deleting the 16
   `_register_tool` calls.
5. **Generate the A2A card and dispatch**, deleting the `AgentSkill` literals and
   the `skill_handlers` dict.
6. **Generate REST routes**, deleting the decorators and body-model assignments.
7. **Populate `DTO.UNIMPLEMENTED`** from the measurement, per tool.

Steps 4–6 are where "declared once" becomes true. Step 3 is where the 68 fields
start reaching implementations, and is the only step with buyer-visible risk.

## Why this needs no guards

The guards that exist today — transport parity, A2A-selects-off-the-tool,
REST-forwards-what-it-declares, builders-respect-declared-defaults — all grade
agreement between declarations that this design deletes. A tool cannot be
registered on MCP and missing from A2A when both are `for name, spec in
TOOLS.items()`. A route cannot declare a field it does not forward when the body
model and the forwarded set are the same object.

They should be deleted as the steps that make their diseases unreachable land,
and not before. Each deletion states which structural change made it impossible.

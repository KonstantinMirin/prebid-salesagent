"""Centralized version compatibility transform registry.

Provides `apply_version_compat(tool_name, response, adcp_version)` that
transports call at their boundary. When the response has a model with products,
v2 compat fields are derived from model attributes (not post-hoc dict mutation).
Transforms are registered per-tool and only applied for pre-3.0 clients.

Also provides `accepts_spec_request_fields()`, the request-side counterpart: the
decorator that lets an MCP tool (or an A2A/REST `_raw()` wrapper) RECEIVE every
field its pinned request schema defines — including the AdCP version envelope,
which those schemas compose in — UNION the spec-prose envelope fields no
per-tool request schema declares in its own `properties` (see
`SPEC_ENVELOPE_FIELDS`).
"""

import contextlib
import contextvars
import functools
import inspect
import posixpath
from collections.abc import Callable, Iterator
from typing import Any

from adcp import types as adcp_types
from pydantic import BaseModel, TypeAdapter, ValidationError

from src.core import adcp_pinned_schema
from src.core.product_conversion import dump_products_v2_compat, needs_v2_compat

# AdCP 3.1.1, dist/docs/3.1.1/building/by-layer/L1/security.mdx, "Server-side
# tool wrapper conformance": a seller MUST accept idempotency_key on every task
# request, and MUST accept context_id, context, push_notification_config, and
# governance_context on EVERY tool -- including reads -- ignoring what it
# cannot act on rather than rejecting the call. This is a spec-PROSE mandate,
# not a schema-SHAPE one: `context_id` and `governance_context` appear in no
# per-tool request schema's `properties` at the 3.1.1 pin -- they exist only
# on `core/protocol-envelope.json`, which composes into RESPONSES, not
# requests. `pinned_request_schema_fields()` below, sourced from each tool's
# own request schema, therefore cannot see them either; this constant is the
# union partner that closes that gap regardless of what an individual tool's
# schema says. This is a known SDK-vs-spec divergence, filed upstream against
# the adcp SDK; this set is the salesagent-side compensating seam until the
# SDK models carry these fields themselves.
# The single carrier parameter by which a tool receives the wire request as its
# pinned model. One name, identical on every tool that opts in — a per-field
# parameter would move acceptance back to the argument binder, which is the whole
# defect this seam replaces. Underscore-prefixed because it is plumbing, not a
# spec field, and it is filtered out of the published schema.
SPEC_REQUEST_PARAM = "_spec_request"

# ---------------------------------------------------------------------------
# The inbound wire carrier (Lane A / S4)
# ---------------------------------------------------------------------------
# Acceptance is decided at the seam every transport crosses. That is only true
# if the seam SEES the whole request — and a decorator can only see what the
# caller already bound. MCP happened to satisfy this (FastMCP binds from the
# decorator-rewritten signature); A2A hands over a curated dict and REST a Body
# model, both BEFORE the decorator runs, so for them the deciding site stayed at
# the transport's argument binder — exactly what the Core Invariant forbids.
#
# So each transport hands the seam the request it ALREADY holds, at the one point
# it already normalizes it. Three set-sites, read at exactly one place
# (`_build_spec_request`). The rejected alternative — threading a `_wire_request=`
# parameter through ~6 REST routes and ~14 A2A handlers — is 20 places to forget;
# the 15th handler would rejoin the seam in name only.
#
# NORMALIZED wire dict, never `raw_wire_payload`: that one is deliberately
# pre-normalization because its consumer is the idempotency payload hash, where
# seller-side compat-table changes must not turn honest retries into conflicts.
# Feeding it here would reintroduce deprecated-name drops. Two consumers of "the
# wire dict"; they are not interchangeable.
_WIRE_REQUEST: contextvars.ContextVar[tuple[str, dict[str, Any]] | None] = contextvars.ContextVar(
    "adcp_wire_request", default=None
)


@contextlib.contextmanager
def set_wire_request(tool_name: str, params: dict[str, Any] | None) -> Iterator[None]:
    """Publish the normalized wire request for *tool_name* to the seam.

    Tool-scoped on purpose: `_build_spec_request` ignores this unless the tool
    names match, so a nested tool call cannot inherit the outer request's fields.
    """
    token = _WIRE_REQUEST.set((tool_name, dict(params or {})))
    try:
        yield
    finally:
        _WIRE_REQUEST.reset(token)


def _ambient_wire_request(tool_name: str) -> dict[str, Any]:
    """The published wire dict for *tool_name*, or empty when absent/mismatched.

    Empty is the correct fallback, not an error: direct `_impl` and harness calls
    have no transport boundary, and they keep working off bound kwargs alone.
    """
    current = _WIRE_REQUEST.get()
    if current is None or current[0] != tool_name:
        return {}
    return current[1]


SPEC_ENVELOPE_FIELDS = frozenset(
    {
        "idempotency_key",
        "context_id",
        "context",
        "push_notification_config",
        "governance_context",
    }
)

# Real SDK types for the SPEC_ENVELOPE_FIELDS members no request model
# declares (empirically: exactly these 4, across every 3.1.1 spec tool —
# `context` itself is already a first-class field on every request model).
# `test_architecture_wrapper_typed_params.py` forbids `Any`-typed parameters
# on every registered MCP/A2A wrapper, so these are sourced from where the
# SDK DOES type each name — `context_id`/`governance_context` are `str | None`
# on every SDK response model that carries them (e.g.
# `GetAdcpCapabilitiesResponse`); `push_notification_config` reuses the SDK's
# own `PushNotificationConfig` type, the same type the tools that DO declare
# this field already use.
_ENVELOPE_ONLY_FIELD_ANNOTATIONS: dict[str, Any] = {
    "context_id": str | None,
    "governance_context": str | None,
    "idempotency_key": str | None,
    "push_notification_config": adcp_types.PushNotificationConfig | None,
}


def _category_qualified_ref(model: type[BaseModel]) -> str:
    """The pinned schema tree's category-qualified ref for *model*'s request
    schema, derived mechanically from the model's own ``__module__``.

    The SDK's generated module path already carries the category directory
    (``adcp.types.generated_poc.media_buy.get_products_request`` ->
    ``media-buy/get-products-request.json``) -- the exact ref
    ``adcp_pinned_schema.load()`` needs. Category-qualified, not a bare
    filename: ``list-creative-formats-request.json`` exists at BOTH
    ``creative/`` and ``media-buy/`` in the pinned tree, so a bare-filename
    lookup for ``list_creative_formats`` would be ambiguous.
    """
    module_parts = model.__module__.split(".")
    category = module_parts[-2].replace("_", "-")
    name = module_parts[-1].replace("_", "-")
    return f"{category}/{name}.json"


def _resolve_composed_ref(ref: str, *, from_ref: str) -> str:
    """Resolve a schema's own relative ``$ref`` (e.g. ``"../core/x.json"``,
    the plain tree's convention, found inside a schema loaded FROM
    *from_ref*) to the root-relative form ``adcp_pinned_schema.load()``
    accepts."""
    category_dir = posixpath.dirname(from_ref)
    return posixpath.normpath(posixpath.join(category_dir, ref))


def _flatten_request_schema(schema: dict[str, Any], *, ref: str) -> tuple[set[str], set[str]]:
    """The (properties, required) pair for one request schema, following its
    ``allOf`` composition one level deep (the AdCP convention for including
    ``core/version-envelope.json``).

    Only ``allOf`` branches contribute to ``required`` — a ``oneOf``/``anyOf``
    branch is an ALTERNATIVE, not something every request carries, so folding
    its ``required`` in would overstate what the schema actually mandates.
    """
    properties: set[str] = set(schema.get("properties", {}) or {})
    required: set[str] = set(schema.get("required", []) or [])
    for branch in schema.get("allOf", []) or []:
        branch_ref = branch.get("$ref")
        if not branch_ref:
            properties |= set(branch.get("properties", {}) or {})
            required |= set(branch.get("required", []) or [])
            continue
        try:
            composed = adcp_pinned_schema.load(_resolve_composed_ref(branch_ref, from_ref=ref))
        except adcp_pinned_schema.PinnedSchemaError:
            continue
        properties |= set(composed.get("properties", {}) or {})
        required |= set(composed.get("required", []) or [])
    return properties, required


def pinned_request_schema_fields(tool_name: str) -> tuple[frozenset[str], frozenset[str]]:
    """The (properties, required) pair for *tool_name*'s pinned 3.1.1 request
    schema, read from the installed adcp SDK's own schema tree
    (`src/core/adcp_pinned_schema.py` -- never the network, never an
    independently vendored copy).

    Returns two empty frozensets if the tool has no SDK request model, or if
    its schema cannot be resolved (e.g. the SDK's generated module layout
    changed) -- callers fall back to `SPEC_ENVELOPE_FIELDS` and the model's
    own `model_fields` cross-check in that case, never a hard failure at
    decoration time.
    """
    model = spec_request_model(tool_name)
    if model is None:
        return frozenset(), frozenset()
    ref = _category_qualified_ref(model)
    try:
        schema = adcp_pinned_schema.load(ref)
    except adcp_pinned_schema.PinnedSchemaError:
        return frozenset(), frozenset()
    properties, required = _flatten_request_schema(schema, ref=ref)
    return frozenset(properties), frozenset(required)


def spec_request_model(tool_name: str) -> type[BaseModel] | None:
    """The pinned SDK request model for an MCP tool, or None if it is not a spec task.

    `get_products` -> `adcp.types.GetProductsRequest`. Mechanical, with no
    exception table — and its misses carry information. At the 3.1.1 pin the
    four tools that do NOT resolve are exactly the four that are not spec
    tasks: `list_authorized_properties` (retired at 3.1.1),
    `update_performance_index` (our local name for the spec's
    provide_performance_feedback), and `get_task` / `complete_task` (a local
    task-management surface). "No model" therefore means "no spec fields to
    accept", which is the correct answer rather than a gap.
    """
    model = getattr(adcp_types, "".join(part.title() for part in tool_name.split("_")) + "Request", None)
    return model if isinstance(model, type) and issubclass(model, BaseModel) else None


# `spec_response_model()` used to live here. It resolved a tool's pinned SDK
# RESPONSE model, and had ZERO production callers — its only consumers were
# the test harness client and its tests. A response-side parse-back helper
# for the harness is not a production concern, and leaving a test-only export
# in a production module is the "owned by two concerns" this lane exists to
# resolve rather than leave silent. Moved to tests/harness/spec_models.py.


def _field_annotation(model: type[BaseModel], name: str) -> Any:
    """The best available type annotation for a newly-accepted parameter.

    Prefers the SDK request model's own annotation when the model declares
    the field. Falls back to ``_ENVELOPE_ONLY_FIELD_ANNOTATIONS`` for the
    handful of names the model never declares at all — never ``Any``:
    ``test_architecture_wrapper_typed_params.py`` forbids it on every
    registered wrapper this decorator applies to, and a permissive-but-untyped
    parameter would defeat the point of publishing an accurate tool schema.
    A name in neither source falls back to ``str | None`` as the least-risky
    guess (a widen-only "accept but don't act" field, same posture the model
    fallback already carries) rather than raising at decoration time, which
    would crash tool registration outright on the next spec bump.
    """
    field = model.model_fields.get(name)
    if field is not None:
        return field.annotation
    return _ENVELOPE_ONLY_FIELD_ANNOTATIONS.get(name, str | None)


def _build_spec_request(model: Any, carried: set[str], tool_name: str, kwargs: dict[str, Any]) -> Any:
    """The wire request as the pinned model, TOLERANT of missing required fields.

    A partial request is normal here: a buyer legitimately sends only the
    fields it wants to change, and this seam's job is to carry what arrived,
    not to enforce required-ness (that is `_impl`'s, and enforcing it here
    would fail requests the graders require to succeed).

    Values that ARE present are coerced against their field's ANNOTATION —
    `model_construct` alone skips validation entirely and would hand `_impl`
    raw wire types. Two limits, stated because the previous wording overclaimed
    and contradicted the code four lines below it:

    - TYPE coercion only. `field.annotation` drops `field.metadata`, so
      constraint validators (Ge, MaxLen, pattern) do NOT run here. That is
      deliberate: this carrier's job is to CARRY the request, and enforcing
      constraints at the seam would push more fields into the raw arm — less
      typing, not more. `_impl` enforces.
    - A field that fails coercion is NOT left out; its RAW value rides
      through and `_impl` decides. One malformed optional must not deny
      service to a request the tool could otherwise honor.
    """
    # The wire dict the transport published, overlaid by the kwargs actually
    # bound. BOUND KWARGS WIN: by the time they exist they are coerced objects
    # (AccountReference, BrandReference, PushNotificationConfig), while the
    # ambient dict is raw wire — preferring the raw form would undo the
    # transport's own coercion. The ambient dict's job is to supply the fields
    # the transport never bound at all, which is precisely the set that used
    # to be accepted and dropped.
    merged = {**_ambient_wire_request(tool_name), **kwargs}
    present = {k: v for k, v in merged.items() if k in carried}
    validated: dict[str, Any] = {}
    for name, value in present.items():
        field = model.model_fields.get(name)
        if field is None or field.annotation is None:
            validated[name] = value
            continue
        try:
            # Coerce against the FIELD'S OWN annotation. A TypeAdapter returns
            # the coerced VALUE; `validate_assignment` returns the model and
            # would need subscripting it, which BaseModel does not support —
            # that mistake silently routed every field into the except arm
            # below and handed `_impl` raw wire dicts and strings.
            validated[name] = TypeAdapter(field.annotation).validate_python(value)
        except ValidationError:
            # One malformed OPTIONAL must not deny service to a request the
            # tool could otherwise honor, so the raw value rides through and
            # `_impl` decides. Deliberately ValidationError only: a TypeError
            # or AttributeError here means the coercion machinery itself is
            # wrong, and swallowing that is what hid this bug.
            validated[name] = value
    return model.model_construct(**validated)


def accepts_spec_request_fields(tool_func: Callable) -> Callable:
    """Let an MCP tool (or A2A/REST ``_raw()`` wrapper) accept every field its
    pinned request schema defines.

    FastMCP derives each tool's input schema from its Python signature and
    validates arguments with pydantic BEFORE the tool body runs. Any field the
    spec defines but the signature omits is therefore REJECTED outright —
    `VALIDATION_ERROR: Unexpected keyword argument` — rather than ignored. A
    seller that rejects a field its own schema DEFINES is non-conformant
    regardless of whether it can act on it.

    The sibling ``_raw()`` functions in ``src/core/tools/`` that A2A and REST
    call directly have no FastMCP schema validation in front of them, but they
    have the same underlying defect: calling one with a keyword its own
    signature omits raises a plain Python ``TypeError`` at argument-binding
    time (salesagent-g6m2.10). Applying this SAME decorator directly to a
    ``_raw()`` function closes that gap identically — the tool name is
    recovered by stripping the trailing ``_raw`` (``get_products_raw`` ->
    ``get_products``), so one mechanism, one field-set source, covers both
    the MCP registration chokepoint and the raw-wrapper call sites.

    Scope is exactly the defined fields. `additionalProperties: true` on those
    schemas is a statement about the SENDER — a buyer may send more and must not
    get an exception — not a licence for undefined fields to reach us. Undefined
    fields stay outside: rejected in development, ignored in production (Critical
    Pattern #7), so nothing absent from our models can ever reach the application
    layer and envelope validation stays out of application code.

    The field set is the UNION of three sources, in this priority order:

    1. ``pinned_request_schema_fields(tool_name)`` — the tool's own pinned
       JSON request schema (`src/core/adcp_pinned_schema.py`, reading the
       installed adcp SDK's schema tree), flattened across its `allOf`
       composition. This is the PRIMARY source: it is what a buyer's own
       schema-validation actually checks against, and it is what carries
       correct required-ness (see below) — the SDK request models diverge
       from it (`get-products-request.json` requires `buying_mode`; the SDK's
       `GetProductsRequest` does not mark it required).
    2. ``SPEC_ENVELOPE_FIELDS`` — the spec-PROSE mandate
       (security.mdx's "Server-side tool wrapper conformance") that no
       per-tool schema's `properties` carries in its own shape:
       `context_id` / `governance_context` live only on the RESPONSE-side
       `core/protocol-envelope.json`, never a request schema.
    3. ``model.model_fields`` — the SDK request model, demoted from primary
       source to CROSS-CHECK/fallback. Kept because a schema-resolution
       failure (SDK layout change) must not silently narrow acceptance below
       what the model itself already declares, and because the model is what
       ships with the pin, so a spec bump widens this arm automatically even
       before `adcp_pinned_schema.py` is updated for a new layout.

    Required-ness (`pinned_request_schema_fields`'s second element) is
    recorded on the decorated function as `__spec_required_fields__` for
    later callers that need it — this decorator's own job is acceptance, not
    enforcement, so it never rejects a call for a missing required field.

    Applied once at the registration chokepoint (or once per ``_raw()``
    function definition) rather than as parameters on sixteen signatures, so a
    seventeenth tool cannot forget. This SUBSUMES the narrower version-envelope
    acceptance it replaced: the request models already declare `adcp_version`
    / `adcp_major_version`.

    Why an explicit ``__signature__`` AND ``__annotations__``: ``functools.wraps``
    points ``inspect.signature`` at the undecorated function, so FastMCP would
    build the old schema; and pydantic builds a callable's argument schema from
    ``get_type_hints()`` rather than the signature object, so a parameter present
    only in ``__signature__`` raises KeyError during schema generation. A bare
    ``**kwargs`` wrapper fixes neither, and would additionally let undefined
    fields through to the tool body — the one thing the layering above exists
    to prevent.

    SCOPE — this makes fields ACCEPTED, not ACTED ON. A buyer sending
    `pagination` still gets unpaginated results, and `account` still does not
    select billing. That is strictly better than failing the whole call, and the
    spec models these as optional, but "accepts the field" must never be read as
    "honors the field"; honoring each is separate, per-field work. On the
    ``_raw()`` path specifically, today's A2A skill handlers also do not yet
    forward these fields down from the wire `parameters` dict — this decorator
    only makes the raw function itself callable with them; wiring each A2A
    handler to forward them is separate, per-field work tracked elsewhere.
    """
    is_async = inspect.iscoroutinefunction(tool_func)
    original = inspect.signature(tool_func)
    declared = set(original.parameters)

    model = spec_request_model(tool_func.__name__.removesuffix("_raw"))
    if model is None:
        return tool_func

    # UNION of the tool's pinned schema, the spec-prose envelope set, and the
    # SDK model itself (cross-check/fallback) — see the docstring's "field set
    # is the UNION of three sources" section. `idempotency_key` is included
    # via SPEC_ENVELOPE_FIELDS for every tool, including reads: security.mdx
    # mandates it on every task request, and `universal/read-tool-idempotency
    # .yaml` grades reads for accepting it (the 5 known_failures.txt entries
    # this closes are graduated separately, by a live conformance run, not by
    # this decorator edit).
    schema_fields, _schema_required = pinned_request_schema_fields(tool_func.__name__.removesuffix("_raw"))

    # DISPOSITION IS DERIVED, NEVER DECLARED. Every candidate field gets exactly
    # one of three dispositions, decided here from the tool's own pinned model —
    # there is no per-tool marker, allowlist or registry to keep in sync, which
    # is precisely what stops a seventeenth tool from silently opting out.
    #
    #   on the model            -> BODY-SEMANTIC. Rides to the tool in the
    #                              request model (`_spec_request`). Whether the
    #                              tool HONORS or REFUSES it is the tool's own
    #                              runtime job; what is forbidden is dropping it
    #                              silently at the TRANSPORT. A tool that declares
    #                              the carrier and ignores it still drops the
    #                              field — that is per-field work, not something
    #                              this seam can assert away.
    #   envelope-only           -> accept-and-ignore, still published. These are
    #                              the spec-prose envelope names (security.mdx);
    #                              refusing them would be a conformance regression.
    #   in the schema, neither  -> NOT accepted. It never enters the published
    #                              schema, so the transport refuses it loudly
    #                              rather than accepting and dropping it.
    #
    # The third arm is empty at the 3.1.1 pin (every tool's schema fields are a
    # subset of its model fields) and `test_architecture_spec_field_disposition`
    # asserts that. It is implemented anyway: without it, a spec bump that adds a
    # schema field the SDK model lacks would silently reinstate accept-and-drop.
    model_field_names = set(model.model_fields)
    candidates = (schema_fields | SPEC_ENVELOPE_FIELDS | model_field_names) - declared
    body_semantic = {name for name in candidates if name in model_field_names}
    envelope_only = {name for name in candidates - body_semantic if name in SPEC_ENVELOPE_FIELDS}
    accepted_names = sorted(body_semantic | envelope_only)

    additions = [
        inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=_field_annotation(model, name))
        for name in accepted_names
    ]
    if not additions:
        return tool_func

    accepted = {p.name for p in additions}
    # Every field the model declares, including ones the tool's own signature
    # already binds — the model is the tool's view of the request, not a diff
    # against its signature.
    #
    # NOT `- SPEC_ENVELOPE_FIELDS`. A name in that set is envelope-class only
    # when the model does NOT declare it; when the model DOES, it is a real field
    # of this request and must ride. `idempotency_key` is the case that matters:
    # it is envelope-class on reads (no model declares it) but body-semantic on
    # writes, and subtracting the whole set dropped it from exactly the requests
    # whose retry-safety depends on it.
    carried = model_field_names

    def _strip(kwargs: dict[str, Any]) -> dict[str, Any]:
        """Remove the decorator-added names from the FLAT kwargs.

        This stays whole on purpose. A body-semantic field is not rescued by
        surviving here — it is rescued by riding in `_spec_request`. Letting
        honored names through would push them at a signature that never declared
        them (TypeError), and "honored means unstripped" is the drift this seam
        exists to prevent.
        """
        return {k: v for k, v in kwargs.items() if k not in accepted}

    tool_name = tool_func.__name__.removesuffix("_raw")

    # The ONE carrier. A tool opts in by declaring `SPEC_REQUEST_PARAM` in its own
    # signature; the decorator then hands it the parsed request model. Per-field
    # parameters are deliberately NOT how a field reaches a tool — that would put
    # acceptance back at the transport's argument binder, one signature at a time,
    # which is the defect this seam replaces. One parameter, same name everywhere.
    def _call_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        stripped = _strip(kwargs)
        # UNCONDITIONAL. The carrier is not opt-in: a tool that does not declare
        # it fails loudly here rather than quietly reverting to accept-and-drop.
        # That noise IS the enforcement — it is what stops a seventeenth tool
        # from rejoining the seam in name only, which is the whole property the
        # derived disposition above exists to guarantee.
        stripped[SPEC_REQUEST_PARAM] = _build_spec_request(model, carried, tool_name, kwargs)
        return stripped

    if is_async:

        @functools.wraps(tool_func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await tool_func(*args, **_call_kwargs(kwargs))

        wrapper: Callable = async_wrapper
    else:

        @functools.wraps(tool_func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return tool_func(*args, **_call_kwargs(kwargs))

        wrapper = sync_wrapper

    # Keyword-only additions go last, after any **kwargs-free tail, so the
    # resulting signature stays valid regardless of the tool's own parameters.
    #
    # The carrier is FILTERED OUT here. FastMCP builds the published input schema
    # from this signature, so leaving it in would advertise an internal plumbing
    # parameter to buyers as if it were a spec field — and the
    # published-schema-minus-honored grader would (correctly) flag it.
    parameters = [
        p
        for p in original.parameters.values()
        if p.kind is not inspect.Parameter.VAR_KEYWORD and p.name != SPEC_REQUEST_PARAM
    ]
    var_keyword = [p for p in original.parameters.values() if p.kind is inspect.Parameter.VAR_KEYWORD]

    # `__signature__` is not a declared attribute of Callable, so the assignment
    # goes through an Any-typed alias rather than a silencing comment — that
    # count is a ratchet in this repo, and growing it to add a parameter is not
    # a trade worth making.
    decorated: Any = wrapper
    decorated.__signature__ = original.replace(parameters=[*parameters, *additions, *var_keyword])

    # __annotations__ as well as __signature__, and AFTER functools.wraps has
    # copied the original's: pydantic builds a callable's argument schema from
    # `get_type_hints()`, not from the signature object, so a parameter present
    # only in __signature__ raises KeyError while the schema is generated.
    decorated.__annotations__ = {k: v for k, v in tool_func.__annotations__.items() if k != SPEC_REQUEST_PARAM} | {
        p.name: p.annotation for p in additions
    }

    # `__spec_required_fields__` used to be recorded here, computed and read by
    # nobody, against the day some later caller wanted to enforce required-ness
    # at this seam. That day cannot come: enforcing it here would reject the
    # partial requests this decorator exists to carry. Required-ness is `_impl`'s
    # to enforce, on the model it now receives.
    return wrapper


def apply_version_compat(
    tool_name: str,
    response: Any,
    adcp_version: str | None,
) -> dict[str, Any]:
    """Apply registered version compat transforms for a tool.

    Called at the transport boundary (MCP, A2A, REST). For V3+ clients,
    serializes with standard model_dump(). For pre-3.0 clients, pricing
    options are serialized with v2 compat fields derived from models.

    The response can be:
    - A Pydantic model with .products attribute (preferred — enables model-level v2 compat)
    - A pre-serialized dict (legacy path — v2 compat skipped since models are unavailable)

    Args:
        tool_name: Name of the tool (e.g., "get_products")
        response: Response model or pre-serialized dict
        adcp_version: Client's declared AdCP version (None -> applies compat)

    Returns:
        Serialized response dict, with v2 compat fields added for pre-3.0 clients
    """
    # If response is already a dict, serialize it as-is (no model available for v2 compat)
    if isinstance(response, dict):
        return response

    # V3+ clients: standard serialization, no compat needed
    if not needs_v2_compat(adcp_version):
        return response.model_dump(mode="json")

    # Pre-3.0 clients: apply model-level v2 compat transforms
    if tool_name == "get_products" and hasattr(response, "products"):
        response_dict = response.model_dump(mode="json")
        # Replace pricing_options with v2-compat serialization from models
        if response.products:
            v2_products = dump_products_v2_compat(response.products)
            response_dict["products"] = v2_products
        return response_dict

    # Unknown tool or no transform: standard serialization
    return response.model_dump(mode="json")

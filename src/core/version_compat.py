"""Centralized version compatibility transform registry.

Provides `apply_version_compat(tool_name, response, adcp_version)` that
transports call at their boundary. When the response has a model with products,
v2 compat fields are derived from model attributes (not post-hoc dict mutation).
Transforms are registered per-tool and only applied for pre-3.0 clients.

Also provides `accepts_spec_request_fields()`, the request-side counterpart: the
decorator that lets an MCP tool RECEIVE every field its pinned request schema
defines — including the AdCP version envelope, which those schemas compose in.
"""

import functools
import inspect
from collections.abc import Callable
from typing import Any

from adcp import types as adcp_types
from pydantic import BaseModel

from src.core.product_conversion import dump_products_v2_compat, needs_v2_compat


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


def accepts_spec_request_fields(tool_func: Callable) -> Callable:
    """Let an MCP tool accept every field its pinned request schema defines.

    FastMCP derives each tool's input schema from its Python signature and
    validates arguments with pydantic BEFORE the tool body runs. Any field the
    spec defines but the signature omits is therefore REJECTED outright —
    `VALIDATION_ERROR: Unexpected keyword argument` — rather than ignored. A
    seller that rejects a field its own schema DEFINES is non-conformant
    regardless of whether it can act on it.

    Scope is exactly the defined fields. `additionalProperties: true` on those
    schemas is a statement about the SENDER — a buyer may send more and must not
    get an exception — not a licence for undefined fields to reach us. Undefined
    fields stay outside: rejected in development, ignored in production (Critical
    Pattern #7), so nothing absent from our models can ever reach the application
    layer and envelope validation stays out of application code.

    The field set comes from the SDK request model, which is the only candidate
    source that is both complete and available at runtime: the JSON bundle is
    test-only and gitignored, and `ADCP_TOOL_DEFINITIONS[*]["inputSchema"]` is a
    partial hint (4 properties for get_products against 18 in the real schema).
    Because the model is pinned, a spec bump widens acceptance automatically
    instead of silently re-opening this bug.

    Applied once at the registration chokepoint rather than as parameters on
    sixteen signatures, so a seventeenth tool cannot forget. This SUBSUMES the
    narrower version-envelope acceptance it replaced: the request models
    already declare `adcp_version` / `adcp_major_version`.

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
    "honors the field"; honoring each is separate, per-field work.
    """
    is_async = inspect.iscoroutinefunction(tool_func)
    original = inspect.signature(tool_func)
    declared = set(original.parameters)

    model = spec_request_model(tool_func.__name__)
    if model is None:
        return tool_func

    # DEFINED fields only. `idempotency_key` is deliberately NOT added to read
    # tools: the read-tool request schemas do not define it (only the mutating
    # ones do), and a field the schema does not define is not ours to accept as
    # a parameter. `universal/read-tool-idempotency.yaml` grades read tools for
    # accepting it, but a grading tool does not outrank the schema — if the two
    # disagree, the storyboard is what is wrong. See the note on that storyboard
    # in docs/test-obligations/storyboard-issue-map.yaml.
    additions = [
        inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=field.annotation)
        for name, field in model.model_fields.items()
        if name not in declared
    ]
    if not additions:
        return tool_func

    accepted = {p.name for p in additions}

    def _strip(kwargs: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in kwargs.items() if k not in accepted}

    if is_async:

        @functools.wraps(tool_func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await tool_func(*args, **_strip(kwargs))

        wrapper: Callable = async_wrapper
    else:

        @functools.wraps(tool_func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return tool_func(*args, **_strip(kwargs))

        wrapper = sync_wrapper

    # Keyword-only additions go last, after any **kwargs-free tail, so the
    # resulting signature stays valid regardless of the tool's own parameters.
    parameters = [p for p in original.parameters.values() if p.kind is not inspect.Parameter.VAR_KEYWORD]
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
    decorated.__annotations__ = {**tool_func.__annotations__, **{p.name: p.annotation for p in additions}}
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

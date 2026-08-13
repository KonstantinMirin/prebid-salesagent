"""Centralized version compatibility transform registry.

Provides `apply_version_compat(tool_name, response, adcp_version)` that
transports call at their boundary. When the response has a model with products,
v2 compat fields are derived from model attributes (not post-hoc dict mutation).
Transforms are registered per-tool and only applied for pre-3.0 clients.

Also provides `accepts_version_envelope()`, the request-side counterpart: the
decorator that lets an MCP tool RECEIVE the AdCP version envelope at all.
"""

import functools
import inspect
from collections.abc import Callable
from typing import Any

from src.core.product_conversion import dump_products_v2_compat, needs_v2_compat

# The AdCP request version envelope, per `core/version-envelope.json` at the
# pinned spec version: "Composed via allOf into every AdCP request and response
# schema so the version semantics live in exactly one place." Neither field is
# required. `adcp_major_version` is deprecated in favour of `adcp_version` and
# removed in 4.0, but servers MUST continue to honor it through 3.x.
VERSION_ENVELOPE_FIELDS: tuple[str, ...] = ("adcp_version", "adcp_major_version")

_ENVELOPE_PARAMETERS = (
    inspect.Parameter(
        "adcp_version",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
        annotation=str | None,
    ),
    inspect.Parameter(
        "adcp_major_version",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
        annotation=int | None,
    ),
)


def accepts_version_envelope(tool_func: Callable) -> Callable:
    """Let an MCP tool accept `adcp_version` / `adcp_major_version`.

    FastMCP derives each tool's input schema from its Python signature and
    validates arguments with pydantic BEFORE the tool body runs. A tool that
    does not declare these two fields therefore rejects every spec-conformant
    3.1 request with `VALIDATION_ERROR: Unexpected keyword argument` — which is
    what a conformance runner sends on EVERY call, since the envelope is
    composed into every request schema.

    Applied once at the registration chokepoint rather than as a parameter pair
    on sixteen tool signatures: the envelope is one protocol constant, and a
    seventeenth tool must not be able to forget it.

    Why an explicit ``__signature__``: ``functools.wraps`` sets ``__wrapped__``,
    so ``inspect.signature`` would follow through to the undecorated function
    and FastMCP would build the old schema. A bare ``**kwargs`` wrapper fails
    for the same reason AND would silently swallow typos, defeating the
    unknown-field handling that `universal/schema-validation.yaml` grades.

    SCOPE — this makes the fields ACCEPTED, not ACTED ON. Negotiating the pin
    (VERSION_UNSUPPORTED on cross-major mismatch, same-major downshift) is a
    separate behavior, graded by `universal/version-negotiation.yaml`, and is
    not implemented here. `apply_version_compat` above remains the only place
    that reads a client's version, and only for v2 response shaping.
    """
    is_async = inspect.iscoroutinefunction(tool_func)
    original = inspect.signature(tool_func)
    declared = set(original.parameters)
    # A tool that already declares the envelope keeps its own handling.
    additions = [p for p in _ENVELOPE_PARAMETERS if p.name not in declared]
    if not additions:
        return tool_func

    def _strip(kwargs: dict[str, Any]) -> dict[str, Any]:
        for field in VERSION_ENVELOPE_FIELDS:
            kwargs.pop(field, None)
        return kwargs

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

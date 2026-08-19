"""Which request fields a tool's code ACTUALLY consumes, measured from its source.

The acceptance seam (`src/core/version_compat.py`) delivers the whole pinned
request model to every tool. That made the first version of the §5 grader
vacuous: it counted `type(delivered).model_fields` as "honored", so DELIVERING
the carrier marked every field of the model honored whether or not any line of
the tool ever read it. Fourteen tools passed while dropping the buyer's fields
one frame further in than before.

Consumption is therefore measured from the SOURCE of the code that owes the
disposition — the tool's wrapper module plus the module that defines its
`_impl`:

    HONORED  a field the code reads off the request it acts on
             (`req.buying_mode`, `getattr(spec_request, "idempotency_key")`).
    REFUSED  a field named in one of the tool's `_UNSUPPORTED_*` maps, which
             `refuse_unsupported_fields` raises on
             (`src/core/spec_request_carrier.py`).

Both count as DISPOSED — the Core Invariant is "honored or refused, never
silently dropped", and plan §5's own note defines the honored set as
HAS-A-DISPOSITION rather than ACTED-ON. What cannot exist is a published
body-semantic field that no line of the tool's code mentions at all.

Static, not runtime: a runtime probe can only see the fields a particular call
happens to exercise, so it would report "not consumed" for every branch the
probe's payload misses. The source is the whole population.
"""

from __future__ import annotations

import ast
import functools
import pathlib

# Names a tool binds its request to. `req` is the codebase's universal name for
# the internal request model the wrappers build and `_impl` acts on;
# `spec_request` / `_spec_request` is the seam carrier itself, which
# `sync_creatives` reads directly (`getattr(_spec_request, "idempotency_key")`)
# — the form the previous hand-maintained `_CARRIER_CONSUMERS` set missed.
_REQUEST_BINDINGS = frozenset({"req", "request", "spec_request", "_spec_request"})

_TOOLS_ROOT = pathlib.Path("src/core/tools")


class _FieldReferenceVisitor(ast.NodeVisitor):
    """Collects every request-field name the module names."""

    def __init__(self) -> None:
        self.fields: set[str] = set()
        #: `_UNSUPPORTED_*` map name -> the field names it declares.
        self.refusal_maps: dict[str, set[str]] = {}
        #: `_UNSUPPORTED_*` map names actually handed to `refuse_unsupported_fields`.
        self.refused_maps_called: set[str] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in _REQUEST_BINDINGS:
            self.fields.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # refuse_unsupported_fields(req, tool="...", unsupported=_UNSUPPORTED_X)
        # THE call that turns a refusal map into an actual disposition.
        if isinstance(node.func, ast.Name) and node.func.id == "refuse_unsupported_fields":
            for kw in node.keywords:
                if kw.arg == "unsupported" and isinstance(kw.value, ast.Name):
                    self.refused_maps_called.add(kw.value.id)
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id.startswith("_UNSUPPORTED"):
                    self.refused_maps_called.add(arg.id)

        # getattr(spec_request, "idempotency_key", None)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in _REQUEST_BINDINGS
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            self.fields.add(node.args[1].value)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # _UNSUPPORTED_<TOOL>_FIELDS = {"time_granularity": "...", ...}
        # Recorded by NAME, not credited yet: a refusal map is only a disposition
        # if the tool actually PASSES it to `refuse_unsupported_fields`. Crediting
        # the keys on sight made the dict alone sufficient, and deleting the call
        # while leaving the dict kept all 27 disposition guards green while the
        # fields went back to being silently accepted and dropped (PR #1858 Lane A
        # diff-review round 3 proved this by mutation). `_refused_field_names`
        # below intersects these with the maps that reach a real call.
        if isinstance(node.value, ast.Dict) and any(
            isinstance(target, ast.Name) and target.id.startswith("_UNSUPPORTED") for target in node.targets
        ):
            keys = {
                key.value for key in node.value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("_UNSUPPORTED"):
                    self.refusal_maps[target.id] = keys
        self.generic_visit(node)


@functools.cache
def _module_fields(path: pathlib.Path) -> frozenset[str]:
    """Fields this module disposes: ones it READS, plus ones it actually REFUSES.

    A refusal counts only when the map reaches a `refuse_unsupported_fields`
    call. Deleting the call now drops every field that map declared, so the
    disposition guard reddens instead of staying green on a dict nobody uses.
    """
    visitor = _FieldReferenceVisitor()
    visitor.visit(ast.parse(path.read_text()))
    refused: set[str] = set()
    for name in visitor.refused_maps_called:
        refused |= visitor.refusal_maps.get(name, set())
    return frozenset(visitor.fields | refused)


@functools.cache
def tool_source_files(tool_name: str) -> tuple[pathlib.Path, ...]:
    """The files that owe *tool_name* its dispositions.

    Derived, never listed: the module that defines the tool wrapper (`async def
    <tool>`) or its raw sibling (`def <tool>_raw`), plus the module that defines
    `_<tool>_impl` — which is a different file for `sync_creatives`
    (`creatives/sync_wrappers.py` vs `creatives/_sync.py`) and would be missed by
    any per-tool file map.
    """
    wanted = (f"def {tool_name}(", f"def {tool_name}_raw(", f"def _{tool_name}_impl(")
    return tuple(sorted(path for path in _TOOLS_ROOT.rglob("*.py") if any(w in path.read_text() for w in wanted)))


def consumed_fields(tool_name: str) -> frozenset[str]:
    """Every request field *tool_name*'s own code honors or explicitly refuses."""
    fields: set[str] = set()
    for path in tool_source_files(tool_name):
        fields |= _module_fields(path)
    return frozenset(fields)


# The accept-and-ignore class: fields a seller MUST accept without acting on, so
# they owe no per-tool disposition.
#
#   adcp_version / adcp_major_version / context / context_id / governance_context
#   / push_notification_config -- AdCP 3.1.1
#   `dist/docs/3.1.1/building/by-layer/L1/security.mdx`, "Server-side tool wrapper
#   conformance": a seller MUST accept these on EVERY tool, "ignoring what it
#   cannot act on rather than rejecting the call". Refusing one is a conformance
#   regression, which is exactly why they are exempt here and nowhere else.
#
#   ext -- AdCP 3.1.1 `core/ext.json`: "Extension object for platform-specific,
#   vendor-namespaced parameters ... namespaced under a vendor/platform key". A
#   namespace this seller does not implement is by construction one it ignores;
#   that IS the extension mechanism.
#
#   idempotency_key -- envelope-class on READS only (nothing to de-duplicate) and
#   body-semantic on WRITES, where dropping it silently re-executes a retried
#   mutation. The read/write split is taken from the SDK's own `readOnlyHint`.
ACCEPT_AND_IGNORE_FIELDS = frozenset(
    {
        "adcp_version",
        "adcp_major_version",
        "context",
        "context_id",
        "governance_context",
        "push_notification_config",
        "ext",
    }
)

IDEMPOTENCY_KEY = "idempotency_key"

# Tools whose published body-semantic fields are NOT yet all disposed. SHRINK-ONLY:
# an entry may be removed when its field gains a disposition, and nothing may be
# added -- a new undisposed field is accept-and-drop, restored.
#
# This REPLACES the hand-maintained `_CARRIER_CONSUMERS` set, which listed tools
# that read the carrier at all and therefore counted 1 of 16 while its own
# detection pattern missed `sync_creatives`' `getattr(_spec_request, ...)` form.
#
# sync_accounts.idempotency_key cannot be refused -- security.mdx mandates
# accepting it on every task request -- and honoring it means joining
# `src/core/idempotency_seam.py`, which is a tool-sized change of its own
# (`AccountUoW` has no idempotency_attempts repository yet).
UNDISPOSED_LEDGER: dict[str, frozenset[str]] = {
    "sync_accounts": frozenset({IDEMPOTENCY_KEY}),
}


def _is_read_tool(tool_name: str) -> bool:
    from src.core.main import ADCP_TOOL_DEFINITIONS

    for definition in ADCP_TOOL_DEFINITIONS:
        if definition["name"] == tool_name:
            return bool((definition.get("annotations") or {}).get("readOnlyHint"))
    raise AssertionError(f"{tool_name} has no SDK tool definition — cannot classify it as a read or a write")


def accept_and_ignore_fields(tool_name: str) -> frozenset[str]:
    """The accept-and-ignore class for one tool, read/write split applied."""
    if _is_read_tool(tool_name):
        return ACCEPT_AND_IGNORE_FIELDS | {IDEMPOTENCY_KEY}
    return ACCEPT_AND_IGNORE_FIELDS


def published_input_fields(tool_name: str) -> frozenset[str]:
    """The properties a tool actually ADVERTISES over MCP.

    The registered tool's published input schema — what a buyer sees from
    `tools/list` and what FastMCP validates against — not
    `inspect.signature(main.<tool>)`, which is the UNDECORATED function
    (acceptance is applied at registration, `src/core/main.py:_register_tool`).
    """
    import asyncio

    from src.core.main import mcp

    tool = asyncio.run(mcp.get_tool(tool_name))
    assert tool is not None, f"{tool_name} is no longer registered with the MCP server"
    return frozenset(tool.parameters.get("properties", {}))


@functools.cache
def _wrapper_def(path: pathlib.Path, tool_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """The `async def <tool_name>` definition in *path*, or None."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == tool_name:
            return node
    return None


def declared_params(tool_name: str) -> frozenset[str]:
    """Declared parameters the wrapper body actually REFERENCES.

    A signature declaration alone is not a disposition. It only means the field
    reaches the body's local scope — the body is still free to ignore it, and
    then the buyer is told a value was applied that nothing ever read. Crediting
    declaration-as-honoring is the SAME class of error as round 2's "carrier
    delivery == honoring": both measure that a field ARRIVED somewhere rather
    than that any code acted on it.

    It was not hypothetical. `update_media_buy` declared `targeting_overlay` and
    `creatives`, published both on its MCP schema, and dropped both — with every
    disposition guard green, because the signature alone satisfied the oracle.

    So this applies the rule the module already applies to `req.X`: measure
    consumption from the source. A parameter counts only if the wrapper body
    names it — including pass-through forwarding (`targeting_overlay=targeting_overlay`),
    which is a real disposition since the value reaches the request the tool acts on.
    """
    import inspect as _inspect

    import src.core.main as main_module

    undecorated = getattr(main_module, tool_name)
    signature_params = frozenset(_inspect.signature(undecorated).parameters)

    # Read the definition from the file that DEFINES the wrapper, which is not
    # `src/core/main.py` — main re-exports these from `src/core/tools/*`. Parsing
    # main.py found no definition, silently fell through to the signature, and
    # restored the exact oracle this function exists to replace: a guard that
    # cannot find the code it grades must not report "all disposed".
    # (`inspect.getsource` is banned in tests, TID251; the defining module is on
    # disk and this module already knows how to parse files.)
    defining_module = _inspect.getmodule(undecorated)
    assert defining_module is not None and getattr(defining_module, "__file__", None), (
        f"{tool_name}: cannot locate the module that defines the wrapper, so its parameters "
        "cannot be measured for consumption. Fix the resolution — do not fall back to the "
        "signature, which would credit every declared parameter as honored."
    )
    func = _wrapper_def(pathlib.Path(defining_module.__file__), tool_name)
    assert func is not None, (
        f"{tool_name}: no `def {tool_name}` found in {defining_module.__file__}. The oracle "
        "cannot measure what it cannot parse; failing loudly beats crediting every parameter."
    )

    referenced = {node.id for stmt in func.body for node in ast.walk(stmt) if isinstance(node, ast.Name)}
    return frozenset(signature_params & referenced)


def undisposed_fields(tool_name: str) -> list[str]:
    """Published body-semantic fields the tool neither honors nor refuses.

    The §5 grader's subtraction, measured against ACTUAL consumption rather than
    against carrier DELIVERY — delivering the pinned model to a tool that never
    reads it moved the drop one frame in, it did not remove it.
    """
    disposed = declared_params(tool_name) | consumed_fields(tool_name)
    return sorted(published_input_fields(tool_name) - accept_and_ignore_fields(tool_name) - disposed)


def spec_tool_names() -> list[str]:
    """Every registered MCP tool that has a pinned 3.1.1 request schema."""
    import asyncio

    from src.core.main import ADCP_TOOL_DEFINITIONS, mcp
    from src.core.version_compat import spec_request_model

    names = []
    for definition in ADCP_TOOL_DEFINITIONS:
        name = definition["name"]
        if spec_request_model(name) is None:
            continue
        if asyncio.run(mcp.get_tool(name)) is None:
            continue
        names.append(name)
    return sorted(names)

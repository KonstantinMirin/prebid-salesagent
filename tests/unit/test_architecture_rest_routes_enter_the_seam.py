"""Guard: every /api/v1 route reaches its tool through the DECORATED wrapper.

PR #1858 Lane A. `get_products` was the one route that hand-built a request and
called `_get_products_impl` directly while its eleven siblings called their
`<tool>_raw` wrapper. Only the wrapper carries `@accepts_spec_request_fields`,
which is what reads the wire body `RestCompatMiddleware` publishes onto the
`_spec_request` carrier — so on REST every field outside that route's three
hand-listed arguments was accepted and silently dropped, while MCP and A2A
honored or refused them correctly. A buyer sending `time_budget` got 200 OK and
no effect.

The existing seam test checks only that a route's PATH resolves to a carrier
tool, which was true of `get_products` the whole time it was leaking. That is
the gap this guard closes: the path resolving is not the same as the route
ENTERING the seam.

Detection is AST over the route module, deliberately, and not a live call: a
behavioral test would only catch the routes someone remembered to exercise,
and the failure mode here is a route nobody wrote a wire test for.
"""

import ast
import pathlib

from tests.unit._architecture_helpers import iter_call_expressions

ROUTES = pathlib.Path(__file__).resolve().parents[2] / "src" / "routes" / "api_v1.py"

#: Routes that legitimately reach no `<tool>_raw`, with the reason. Shrink-only.
#: A route added here must be one that addresses no AdCP tool at all.
_NON_TOOL_ROUTES: dict[str, str] = {
    "health": "liveness probe — addresses no AdCP tool",
    "root": "service descriptor — addresses no AdCP tool",
}


def _route_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function carrying an `@router.<method>(...)` decorator."""
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            func = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "router":
                routes.append(node)
                break
    return routes


def _called_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Every callable name this body invokes, bare or attribute-qualified.

    Uses the shared `iter_call_expressions` rather than a local `ast.walk` over
    Call nodes — `test_architecture_no_handrolled_call_walk` enforces exactly
    that, and it caught the first version of this guard.
    """
    names = set()
    for call in iter_call_expressions(func):
        target = call.func
        names.add(target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", ""))
    return names


def _calls_a_raw_wrapper(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Does this route body call some `*_raw(...)`?"""
    return any(name.endswith("_raw") for name in _called_names(func))


def _calls_an_impl_directly(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Does this route body call a `_<tool>_impl(...)` directly, bypassing the seam?"""
    return any(name.startswith("_") and name.endswith("_impl") for name in _called_names(func))


def test_no_rest_route_calls_an_impl_directly():
    """A route that calls `_impl` skips `@accepts_spec_request_fields` entirely."""
    tree = ast.parse(ROUTES.read_text())
    offenders = sorted(f.name for f in _route_functions(tree) if _calls_an_impl_directly(f))

    assert offenders == [], (
        f"{offenders} call a `_<tool>_impl` directly instead of the `<tool>_raw` wrapper. "
        "Only the wrapper carries @accepts_spec_request_fields, so every pinned request field "
        "the route's own arguments do not name is accepted on the wire and dropped before the "
        "tool — the exact defect PR #1858 Lane A fixed in get_products."
    )


def test_every_tool_route_enters_through_the_decorated_wrapper():
    """Positive form: each tool-addressing route body calls some `<tool>_raw`."""
    tree = ast.parse(ROUTES.read_text())
    routes = _route_functions(tree)
    assert routes, "No @router routes found — the module's shape changed; update this guard."

    missing = sorted(f.name for f in routes if f.name not in _NON_TOOL_ROUTES and not _calls_a_raw_wrapper(f))

    assert missing == [], (
        f"{missing} do not reach a `<tool>_raw` wrapper. Either route them through it, or — if the "
        f"route addresses no AdCP tool — add it to _NON_TOOL_ROUTES with a reason. That map is "
        "shrink-only; it is not a place to park a route that should be on the seam."
    )

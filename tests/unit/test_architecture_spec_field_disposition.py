"""Structural guards for the acceptance seam (Lane A / S4).

Three of these exist because a COMMENT claimed they did. `version_compat.py`
cited `test_architecture_spec_field_disposition` as the safety net for the
residue arm; no such test existed. A cited-but-absent guard is worse than an
uncited invariant — it tells the next reader the property is protected when
nothing checks it. The citation is now true.
"""

import ast
import pathlib

import pytest

from src.core.version_compat import (
    SPEC_ENVELOPE_FIELDS,
    pinned_request_schema_fields,
    spec_request_model,
)

_TOOLS = [
    "get_products",
    "create_media_buy",
    "update_media_buy",
    "sync_creatives",
    "list_creatives",
    "get_media_buys",
    "get_media_buy_delivery",
    "get_adcp_capabilities",
    "list_accounts",
    "sync_accounts",
    "list_creative_formats",
    "list_tasks",
]


@pytest.mark.arch_guard
@pytest.mark.parametrize("tool_name", _TOOLS)
def test_residue_arm_is_empty_at_the_pin(tool_name: str):
    """No pinned schema field is absent from its SDK request model.

    The decorator's third disposition — "in the schema, on neither the model nor
    the envelope set" — drops a field from `accepted_names` so the transport
    refuses it loudly. That arm is empty at 3.1.1, which is exactly why it is easy
    to leave untested and why a spec bump could silently repopulate it: a field
    that lands in the schema but not the model would start being REFUSED, and
    nothing else would notice.
    """
    model = spec_request_model(tool_name)
    assert model is not None, f"{tool_name} has no pinned request model"
    schema_fields, _ = pinned_request_schema_fields(tool_name)
    residue = sorted(set(schema_fields) - set(model.model_fields) - SPEC_ENVELOPE_FIELDS)
    assert residue == [], (
        f"{tool_name}: {residue} are in the pinned request schema but on neither the SDK model "
        "nor the envelope set, so the seam will REFUSE them. Either the SDK pin needs updating or "
        "these fields need an explicit disposition."
    )


@pytest.mark.arch_guard
def test_every_rest_write_route_is_covered_by_the_seam():
    """Every /api/v1 write route must resolve to a tool for the carrier.

    The REST set-site publishes the wire dict only for paths it can name. A route
    it cannot name is a route where acceptance silently reverts to whatever the
    Body model happens to declare — which is how `PUT /media-buys/{id}` (the tool
    this lane exists to fix) was the one route the seam never saw.
    """
    from src.routes.rest_compat_middleware import RestCompatMiddleware

    source = pathlib.Path("src/routes/api_v1.py").read_text()
    tree = ast.parse(source)
    uncovered: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                continue
            if deco.func.attr not in ("post", "put", "patch"):
                continue
            if not deco.args or not isinstance(deco.args[0], ast.Constant):
                continue
            path = "/api/v1" + deco.args[0].value
            if RestCompatMiddleware._resolve_carrier_tool(path) is None:
                uncovered.append(f"{deco.func.attr.upper()} {path}")
    assert uncovered == [], (
        f"REST write routes the acceptance seam cannot name: {uncovered}. "
        "Add them to _CARRIER_PATHS (or teach _resolve_carrier_tool the shape) — "
        "an unnamed route decides acceptance at its Body model instead of the seam."
    )


@pytest.mark.arch_guard
def test_all_three_transports_publish_to_the_seam():
    """MCP, A2A and REST must each publish the wire request.

    One missing publication is invisible at runtime — that transport simply falls
    back to bound kwargs and quietly decides acceptance at its own argument binder
    again, which is the exact regression this lane closed.
    """
    sites = {
        "MCP": "src/core/mcp_compat_middleware.py",
        "A2A": "src/a2a_server/adcp_a2a_server.py",
        "REST": "src/routes/rest_compat_middleware.py",
    }
    missing = [name for name, path in sites.items() if "set_wire_request(" not in pathlib.Path(path).read_text()]
    assert missing == [], (
        f"{missing} no longer publish the wire request to the acceptance seam. "
        "Without it that transport decides acceptance at its own argument binder."
    )


# Tools whose `_impl` actually READS the carrier the seam hands them. Everything
# else declares `_spec_request` and discards it — which is still a drop, just one
# frame further in than the transport binders this lane moved it from.
#
# The Core Invariant says a field is "honored or refused, NEVER SILENTLY dropped".
# Per-field honoring is separate work the plan scopes out, so this list is not a
# TODO to close in this lane. What it does is stop the drop being SILENT: adding a
# tool without wiring its carrier is now visible here, and the list may only GROW.
_CARRIER_CONSUMERS = frozenset({"media_buy_update"})


@pytest.mark.arch_guard
def test_carrier_consumers_only_grow():
    """The set of tools that actually read the carrier may not shrink.

    Deliberately a ratchet, not a completeness demand. Requiring every tool to
    consume the carrier today would either block the lane or invite a fake
    consumption that reads the model and ignores it — worse than an honest gap.
    What must not happen is a tool QUIETLY dropping out of the honored set.
    """
    consumers = set()
    for path in pathlib.Path("src/core/tools").rglob("*.py"):
        text = path.read_text()
        if "spec_request=_spec_request" in text or "spec_request is not None" in text:
            consumers.add(path.stem)

    regressed = sorted(_CARRIER_CONSUMERS - consumers)
    assert not regressed, (
        f"{regressed} stopped consuming the seam's request model. The field is accepted on the "
        "wire and now reaches nothing — accept-and-drop, restored."
    )
    if consumers - _CARRIER_CONSUMERS:
        pytest.fail(
            f"New carrier consumers {sorted(consumers - _CARRIER_CONSUMERS)} — good. "
            "Add them to _CARRIER_CONSUMERS so the ratchet holds at the new level."
        )

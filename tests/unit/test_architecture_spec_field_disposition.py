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
from tests.harness.spec_field_consumption import UNDISPOSED_LEDGER, undisposed_fields
from tests.unit._architecture_helpers import assert_violations_match_allowlist

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


@pytest.mark.arch_guard
@pytest.mark.parametrize("tool_name", _TOOLS)
def test_every_published_body_semantic_field_has_a_disposition(tool_name: str):
    """Published, body-semantic, and never mentioned by the tool's code == dropped.

    The seam DELIVERS the pinned request model to all sixteen tools. Delivery is
    not disposition: a tool that never reads the carrier drops the buyer's field
    one frame further in than the transport binder it was moved from, and the
    buyer still gets success. Consumption is therefore measured from the tool's
    own source (`tests/harness/spec_field_consumption.py`) — a field is disposed
    when the code READS it off the request or names it in an `_UNSUPPORTED_*` map
    that `refuse_unsupported_fields` raises on.

    Its predecessor, `test_carrier_consumers_only_grow`, ratcheted a hand-written
    set of tools that "read the carrier at all" — it counted one of sixteen, and
    its own detection pattern could not see `sync_creatives`' `getattr(
    _spec_request, ...)` form. This grades the actual obligation instead.
    """
    undisposed = undisposed_fields(tool_name)
    ledgered = sorted(UNDISPOSED_LEDGER.get(tool_name, frozenset()))

    assert undisposed == ledgered, (
        f"{tool_name}: published body-semantic fields with no disposition: "
        f"{sorted(set(undisposed) - set(ledgered))} (unexpected), "
        f"{sorted(set(ledgered) - set(undisposed))} (ledgered but now disposed — remove them from "
        "UNDISPOSED_LEDGER, it only shrinks). Each field must be HONORED (read off the request) or "
        "REFUSED (named in the tool's _UNSUPPORTED_* map). Accepting it and dropping it tells the "
        "buyer it was applied."
    )


@pytest.mark.arch_guard
def test_the_undisposed_ledger_only_shrinks():
    """The ledger may not grow, and may not keep entries for tools it no longer applies to."""
    # Routed through the shared helper rather than a hand-rolled `set(A) - set(B)`
    # assertion: `test_architecture_no_handrolled_allowlist_diff` forbids the
    # hand-rolled form, because it reports only one of the two failure directions
    # and each copy words its message differently. Expressing the stale keys as
    # violations against an EMPTY allowlist says "no ledger key may name a
    # non-tool" in the project's one sanctioned shape.
    stale = {(tool,) for tool in UNDISPOSED_LEDGER if tool not in _TOOLS}
    assert_violations_match_allowlist(
        stale,
        set(),
        fix_hint=(
            "UNDISPOSED_LEDGER names tools that are not spec tools. Remove them — the ledger keys "
            "must be real AdCP task names, or the per-tool disposition check silently skips them."
        ),
    )

    assert sum(len(fields) for fields in UNDISPOSED_LEDGER.values()) <= 1, (
        "UNDISPOSED_LEDGER grew. It stood at exactly one field "
        "(sync_accounts.idempotency_key, which needs the idempotency seam) when this guard was "
        "written; a new entry means a field was accepted and dropped instead of disposed."
    )

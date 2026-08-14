"""Guard: every MCP tool accepts every field its pinned request schema defines.

GH #1512 and GH #1193 were the same shape twice. FastMCP builds
each tool's input schema from its Python signature and validates with pydantic
before our code runs, so any field the spec declares but the signature omits is
REJECTED — ``VALIDATION_ERROR: Unexpected keyword argument`` — rather than
ignored. The AdCP request schemas carry ``additionalProperties: true``, so
tolerating more than we implement is the explicitly specified posture; rejecting
a field our own schema declares is non-conformant regardless of whether we can
act on it.

Measured cost of not having this guard: 31 graded conformance checks failing on
the version envelope, plus 12 more on per-tool fields — and, because one of them
was capability discovery, 40 further failures on a storyboard that should have
been skipped entirely.

This is a signature-shape guard rather than a behavioural test on purpose: the
behaviour is covered by
``tests/integration/test_spec_request_fields_accepted.py`` and
``tests/integration/test_version_envelope_accepted.py``, which drive real MCP
calls. What those cannot do is cover all 16 tools without 16 fixtures, so this
guard covers the class and they prove the mechanism.

Offline: reads the installed ``adcp`` SDK's request models, which ship with the
pin. It never touches the vendored JSON bundle (gitignored, test-only).
"""

from __future__ import annotations

import pytest

from src.core.version_compat import spec_request_model


def _live_registered_tools() -> tuple[str, ...]:
    """The MCP registry's live tool roster, in registration order.

    Async enumeration of ``mcp.list_tools()`` — the same registry object
    ``_published_input_fields`` below already queries per-tool. Deriving the
    parametrization from it means a newly-registered tool is guarded with no
    test edit; the drop-out risk that motivated hand-typing the old tuple is
    covered instead by cross-checking against a genuinely independent second
    derivation, see ``_structurally_registered_tools``.
    """
    import asyncio

    from src.core.main import mcp

    return tuple(tool.name for tool in asyncio.run(mcp.list_tools()))


def _structurally_registered_tools() -> frozenset[str]:
    """Second, independent derivation of the tool roster: static AST parse.

    Reads ``src/core/main.py``'s source text and collects the positional
    argument of every module-level ``_register_tool(<name>)`` call — the
    helper that wires each tool module's function into ``mcp.tool(...)``.
    This never touches the live FastMCP registry, so it is a different code
    path from ``_live_registered_tools`` (which is also the path
    ``tests/harness/address_table.py`` uses — reusing it here would just be
    the same live query twice, not an independent check). A tool that is
    removed from one side but not the other — dropped from registration, or
    a live-registry bug that silently omits a tool — makes the two
    derivations disagree.
    """
    import ast
    from pathlib import Path

    import src.core.main as main_module

    main_path = Path(main_module.__file__)
    tree = ast.parse(main_path.read_text(), filename=str(main_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_register_tool"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            names.add(node.args[0].id)
    return frozenset(names)


# Live-derived tool roster, in registration order — see _live_registered_tools.
REGISTERED_TOOLS = _live_registered_tools()

# Tools with no SDK request model at the pin. This is NOT an allowlist of
# violations — it is the set of surfaces that are not 3.1.1 spec tasks at all,
# and the reason each one is absent is a fact about the spec:
#   list_authorized_properties — RETIRED at 3.1.1 (salesagent-g6m2.4)
#   update_performance_index   — our local name for provide_performance_feedback
#   get_task / complete_task   — local task-management surface
# A tool leaving this set (the SDK gaining a model for it) must make the guard
# demand the fields, not silently keep exempting it.
NON_SPEC_TOOLS = frozenset(
    {
        "list_authorized_properties",
        "update_performance_index",
        "get_task",
        "complete_task",
    }
)


def _published_input_fields(name: str) -> set[str]:
    """The properties a tool actually ADVERTISES over MCP.

    Deliberately not `inspect.signature(main.<tool>)`: the module-level name is
    the UNDECORATED function, since acceptance is applied at registration. That
    distinction is the whole bug — inspecting the import would have passed while
    the wire still rejected every spec field. This reads the registered tool's
    published input schema, which is what a buyer sees from `tools/list` and
    what FastMCP validates against.
    """
    import asyncio

    from src.core.main import mcp

    tool = asyncio.run(mcp.get_tool(name))
    assert tool is not None, f"{name} is no longer registered with the MCP server"
    return set(tool.parameters.get("properties", {}))


@pytest.mark.parametrize("tool_name", REGISTERED_TOOLS)
def test_tool_accepts_every_field_its_request_schema_defines(tool_name: str):
    """A registered tool may not reject a field the pinned spec declares."""
    model = spec_request_model(tool_name)
    if model is None:
        assert tool_name in NON_SPEC_TOOLS, (
            f"{tool_name} has no SDK request model but is not recorded as a non-spec surface — "
            "either the SDK dropped it or the tool is misnamed relative to the spec task"
        )
        return

    accepted = _published_input_fields(tool_name)
    missing = sorted(set(model.model_fields) - accepted)

    assert not missing, (
        f"{tool_name} rejects {len(missing)} field(s) that {model.__name__} declares: {missing}. "
        "FastMCP validates against the signature before the tool body runs, so these are hard "
        "rejections, not ignored fields."
    )


@pytest.mark.parametrize("tool_name", sorted(NON_SPEC_TOOLS))
def test_non_spec_tools_are_still_non_spec(tool_name: str):
    """The exemptions must expire on their own.

    If the SDK gains a request model for one of these, the tool becomes a spec
    task and owes the full field set — this fails so that decision is made
    deliberately rather than by an exemption quietly outliving its reason.
    """
    assert spec_request_model(tool_name) is None, (
        f"{tool_name} now has an SDK request model — remove it from NON_SPEC_TOOLS "
        "so the field-acceptance guard applies to it"
    )


def test_live_registration_matches_structural_registration():
    """Drop-out detector: the two independent roster derivations must agree.

    ``REGISTERED_TOOLS`` (used above to parametrize the field-acceptance
    guard) is derived live from ``mcp.list_tools()``. This test re-derives
    the roster by statically parsing ``src/core/main.py``'s
    ``_register_tool(...)`` call list instead — a different code path that
    never touches the runtime registry. A tool silently dropping out of
    registration (removed from one side, or a live-registry bug that omits
    it) fails this test naming the tool, rather than just shrinking
    ``REGISTERED_TOOLS`` — and the parametrization count — with nothing to
    notice.
    """
    live = set(REGISTERED_TOOLS)
    structural = _structurally_registered_tools()
    only_live = sorted(live - structural)
    only_structural = sorted(structural - live)
    assert not only_live and not only_structural, (
        "Live MCP registration and the static _register_tool(...) call list in "
        f"src/core/main.py disagree. Only in live registry: {only_live}. "
        f"Only in source: {only_structural}."
    )


def test_the_version_envelope_is_covered_by_this_guard():
    """The envelope is not special-cased anywhere — it rides on the models.

    GH #1512 originally shipped a dedicated envelope decorator. It was
    deleted when this generalised one landed; this pins that the envelope is
    genuinely covered, so nobody re-adds the narrower mechanism beside it.
    """
    model = spec_request_model("get_products")
    assert model is not None
    assert {"adcp_version", "adcp_major_version"} <= set(model.model_fields)

    assert {"adcp_version", "adcp_major_version"} <= _published_input_fields("get_products")

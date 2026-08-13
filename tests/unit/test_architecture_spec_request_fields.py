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

# The tools registered with the MCP server, in registration order.
# Kept explicit rather than scraped: a tool silently dropping out of
# registration should break this guard loudly, not shrink its own coverage.
REGISTERED_TOOLS = (
    "list_accounts",
    "sync_accounts",
    "get_adcp_capabilities",
    "get_products",
    "list_creative_formats",
    "sync_creatives",
    "list_creatives",
    "list_authorized_properties",
    "create_media_buy",
    "update_media_buy",
    "get_media_buy_delivery",
    "get_media_buys",
    "update_performance_index",
    "list_tasks",
    "get_task",
    "complete_task",
)

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

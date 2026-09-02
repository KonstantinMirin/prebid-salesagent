"""A spec tool's request DTO must inherit the SPEC's vocabulary, not restate the signature.

The advertised MCP shape is ``DTO fields INTERSECT the implementation's arguments``, and
``_register_tool`` refuses a tool whose DTO cannot be resolved. Resolvability alone is a weak
gate: it is satisfied by a DTO authored FROM the wrapper's own signature, and for such a tool
the intersection is a tautology. The DTO declares what the wrapper declares, the derivation
reproduces the hand-written shape, and the tool advertises whatever we happened to write --
with every test green, because nothing in the loop ever consulted the spec.

So the DTO has to come from somewhere else: for a tool the PINNED SDK defines, it must
inherit that SDK request model (critical pattern #1, the ``Library*`` alias convention).
Then bumping the SDK moves the advertised shape, and a field we invent is visible as a
redeclaration rather than as the vocabulary itself.

The obligation is DERIVED, not allowlisted: it applies exactly to the tools
``ADCP_TOOL_DEFINITIONS`` names. A tool the pinned SDK does not define has no SDK model to
extend -- it cannot meet the obligation, and it gains one automatically the day it is
renamed onto its spec operation. The four in that state are RECORDED below by hand so each
names itself and can be audited; entries may only be removed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from adcp.server.mcp_tools import ADCP_TOOL_DEFINITIONS
from adcp.types.base import AdCPBaseModel as _AdCPBaseModel

from src.core.tools._announced_shape import request_model_for, sdk_grounding

_MAIN = Path("src/core/main.py")

#: Registered tool -> the pinned spec operation it must be rebased onto before its DTO can be
#: grounded. Every one is an operation this repo implements under a name AdCP 3.1.1 does not
#: define, so there is no SDK request model to inherit -- the DTO is hand-authored, and its
#: intersection with the wrapper grades nothing until the rename lands.
#:
#: Entries may only be REMOVED. Adding one means shipping a new off-spec tool, which
#: test_every_skill_names_a_spec_tool (tests/unit/test_architecture_a2a_skills_are_spec_tools.py)
#: already refuses for the A2A surface.
_UNGROUNDED_PENDING_SPEC_RENAME = {
    "update_performance_index": "provide_performance_feedback — a rename AND a reshape: the "
    "spec takes one scalar reading per call with a required measurement period, we take a "
    "list of per-product indices",
    "list_authorized_properties": "the property-list family (list_property_lists / get_property_list)",
    "get_task": "get_task_status — close to a pure rename, same required task_id",
    "complete_task": "no counterpart among the 63 tools the pinned SDK defines; the "
    "human-in-the-loop completion step is ours, so the rename target has to be decided "
    "before this can be grounded",
}


def _registered_tool_names() -> list[str]:
    """The names passed to ``_register_tool`` in main.py, read out of the source.

    Parsed rather than kept as a list here: a tool this file does not know about is exactly
    the one that goes ungraded. Registration is a sequence of module-level calls, so the AST
    is the artifact -- it cannot fall behind the way a second list would.
    """
    tree = ast.parse(_MAIN.read_text(), filename=str(_MAIN))
    return [
        node.args[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_register_tool"
        and node.args
        and isinstance(node.args[0], ast.Name)
    ]


def _tool(name: str):
    """The undecorated tool function, off main's namespace.

    ``main`` imports every tool by name before registering it, and registration replaces
    nothing, so the attribute is still the function whose bytecode names the builder. The
    REGISTERED object is the error-logging wrapper, whose own bytecode names no builder --
    reading the DTO off that would report every tool as having none.
    """
    from src.core import main

    return getattr(main, name)


def _spec_tool_names() -> set[str]:
    """Tool names the PINNED adcp SDK defines (a list of dicts, not a mapping)."""
    return {definition["name"] for definition in ADCP_TOOL_DEFINITIONS}


def test_the_registered_tools_were_actually_found():
    """Guard the guard: an empty read would make every assertion below vacuous."""
    names = _registered_tool_names()
    assert len(names) >= 16, f"only found {names} — the AST read is not seeing the _register_tool calls"


@pytest.mark.parametrize("tool_name", sorted(set(_registered_tool_names()) & _spec_tool_names()))
def test_every_spec_tool_dto_inherits_the_sdk_request_model(tool_name: str) -> None:
    """The pinned SDK defines this tool, so its request vocabulary is the SDK's."""
    model = request_model_for(_tool(tool_name))
    assert model is not None, (
        f"{tool_name} resolves no request DTO — _register_tool should have refused it, so "
        f"either the builder edge broke or this test is reading the wrong function"
    )
    grounding = sdk_grounding(model)
    assert grounding is not None, (
        f"{tool_name} announces {model.__name__}, which inherits no SDK request model. Its "
        f"advertised shape is 'DTO fields INTERSECT the implementation's arguments' — with a "
        f"DTO written from that same implementation, the intersection is a tautology and the "
        f"tool advertises whatever we wrote. Extend the SDK's request model instead."
    )


def test_the_ungrounded_tools_are_exactly_the_recorded_ones():
    """The record is the tree's, not a wish: no unlisted tool, no stale entry.

    Parametrizing over the record alone would let a NEW ungrounded tool appear unnoticed;
    this compares both directions.
    """
    ungrounded = set()
    for name in _registered_tool_names():
        model = request_model_for(_tool(name))
        if model is not None and sdk_grounding(model) is None:
            ungrounded.add(name)
    assert ungrounded == set(_UNGROUNDED_PENDING_SPEC_RENAME), (
        f"ungrounded tools are {sorted(ungrounded)}, recorded {sorted(_UNGROUNDED_PENDING_SPEC_RENAME)}. "
        f"A tool that gained an SDK-grounded DTO must be REMOVED from the record; a new one "
        f"must not be added — ground it instead."
    )


@pytest.mark.parametrize("tool_name", sorted(_UNGROUNDED_PENDING_SPEC_RENAME))
def test_a_recorded_entry_is_still_off_spec(tool_name: str) -> None:
    """The excuse is 'the pinned SDK does not define this tool'. It must still be true."""
    assert tool_name not in _spec_tool_names(), (
        f"the pinned SDK DOES define {tool_name!r} now, so it has a request model to inherit "
        f"and no longer belongs in _UNGROUNDED_PENDING_SPEC_RENAME — ground its DTO"
    )


class TestGroundingIsDecidedByAncestryNotBySpelling:
    """``sdk_grounding`` graded on fixtures, because the tree cannot show it failing.

    Every spec tool is grounded today, so a tree-wide test stays green even if the helper
    starts answering "grounded" for everything — which is precisely how a gate rots.
    """

    def test_a_library_request_model_grounds_itself(self):
        from adcp.types import ListCreativesRequest

        assert sdk_grounding(ListCreativesRequest) is ListCreativesRequest

    def test_a_local_subclass_is_grounded_by_its_library_parent(self):
        from adcp.types import ListCreativesRequest as LibraryListCreativesRequest

        from src.core.schemas import ListCreativesRequest

        assert sdk_grounding(ListCreativesRequest) is LibraryListCreativesRequest

    def test_the_sdk_base_class_alone_does_not_ground(self):
        """The four recorded tools are in exactly this state: an SDK ancestor with no fields.

        Inheriting ``AdCPBaseModel`` puts an ``adcp`` module in the MRO while leaving every
        buyer-facing field hand-written, so a membership test that only asked "does an adcp
        class appear in the MRO?" would call these grounded and grade nothing.
        """
        from adcp.types.base import AdCPBaseModel

        class _HandAuthored(AdCPBaseModel):
            whatever_the_wrapper_takes: str | None = None

        assert sdk_grounding(_HandAuthored) is None


class _HandAuthoredRequest(_AdCPBaseModel):
    """A DTO with no spec ancestry — its fields are whatever the wrapper below declares."""

    brief: str | None = None


def _build_hand_authored_request(brief: str | None = None) -> _HandAuthoredRequest:
    return _HandAuthoredRequest(brief=brief)


def create_property_list(brief: str | None = None):
    """A fixture tool NAMED after a spec operation this repo does not implement.

    The name matters and the choice of name matters. ``_register_tool`` looks the name up in
    ADCP_TOOL_DEFINITIONS to decide whether the grounding obligation applies, so the fixture
    has to be a spec tool; picking one we do NOT register keeps it out of the way of the
    other suites, which resolve tools by scanning loaded modules for a matching ``__name__``.

    Defined at module level, not inside the test: ``request_model_for`` resolves the DTO
    through ``typing.get_type_hints`` on the builder, and a return annotation naming a
    function-local class cannot be resolved from module globals — the builder edge would
    break for the wrong reason and the fixture would prove nothing.
    """
    return _build_hand_authored_request(brief)


class TestRegistrationRefusesAnUngroundedSpecTool:
    """The live refusal, not just the predicate.

    A rule that lives in a helper ``_register_tool`` never consults leaves the tree green
    while grading nothing. This calls the real registration path.
    """

    def test_registration_refuses_it(self):
        from src.core.main import _register_tool

        with pytest.raises(RuntimeError, match="does not inherit the SDK's request model"):
            _register_tool(create_property_list)

    def test_the_fixture_is_refused_for_the_grounding_reason_only(self):
        """It must reach the grounding check — a DTO it cannot resolve would refuse first."""
        model = request_model_for(create_property_list)
        assert model is _HandAuthoredRequest, (
            "the fixture no longer resolves its DTO, so the refusal above is the "
            "'no request DTO' one and grades nothing about grounding"
        )
        assert "create_property_list" in _spec_tool_names()

    def test_the_refusal_is_specific_to_ungrounded_dtos(self):
        """A refusal that fired on everything would pass the test above and break the tree.

        The live registration of all 16 tools is the positive control: importing ``main``
        runs ``_register_tool`` on each, so an over-broad refusal cannot import.
        """
        from src.core import main

        assert main.mcp is not None

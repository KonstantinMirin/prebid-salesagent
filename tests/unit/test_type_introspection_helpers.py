#!/usr/bin/env python3
"""Meta-tests for the annotation-introspection primitives the type-alignment guards depend on.

A guard that walks annotations can only fail when its walker resolves the annotation. When the
walker silently returns "nothing here" — because it matched one union spelling but not the other,
or stopped at an ``Annotated`` wrapper, or at a ``RootModel`` class — every membership check
downstream is false and the guard passes while grading nothing.

That failure mode is why these primitives were centralised: the identical union blind spot was
written twice inside ``tests/unit/test_mcp_tool_type_alignment.py``, and both times it was caught
by mutation rather than review. A shared primitive that lies is worse than four that do, so it is
pinned here directly rather than only through its callers.
"""

import typing
from typing import Any

import pytest
from pydantic import RootModel

from tests.helpers import rootmodel_root, union_args, unwrap_annotated

pytestmark = pytest.mark.schema


class TestUnionArgs:
    """Both union spellings must resolve — ``X | None`` is what this codebase writes."""

    def test_pep604_union(self):
        assert union_args(str | None) == (str, type(None))
        assert union_args(list[str] | None) == (list[str], type(None))

    def test_typing_union_spelling(self):
        # noqa UP007/UP045 below: the explicit typing spellings ARE the point — they have a
        # different get_origin() than `X | None` and both must resolve.
        assert union_args(typing.Optional[list[str]]) == (list[str], type(None))  # noqa: UP045
        assert union_args(typing.Union[str, int]) == (str, int)  # noqa: UP007

    def test_both_spellings_agree(self):
        assert union_args(str | None) == union_args(typing.Optional[str])  # noqa: UP045

    def test_non_union_returns_empty(self):
        assert union_args(str) == ()
        assert union_args(list[str]) == ()
        assert union_args(dict[str, Any]) == ()
        assert union_args(None) == ()


class TestUnwrapAnnotated:
    def test_unwraps_to_base_type(self):
        # `==` not `is`: parameterized generics are rebuilt per expression, not interned.
        assert unwrap_annotated(typing.Annotated[list[str], "constraint"]) == list[str]
        assert unwrap_annotated(typing.Annotated[str, "a", "b"]) is str

    def test_passes_through_unannotated(self):
        assert unwrap_annotated(str) is str
        assert unwrap_annotated(list[str] | None) == list[str] | None

    def test_unwrapping_exposes_a_union_to_union_args(self):
        """The two primitives compose: metadata must not hide a union."""
        hint = typing.Annotated[str | None, "constraint"]
        assert union_args(hint) == ()
        assert union_args(unwrap_annotated(hint)) == (str, type(None))


class TestRootModelRoot:
    def test_returns_root_annotation(self):
        class StrList(RootModel[list[str]]):
            pass

        assert rootmodel_root(StrList) == list[str]

    def test_sdk_array_alias_resolves_to_a_list(self):
        """The real shape this exists for: the adcp SDK spells a JSON array as a RootModel."""
        from adcp.types.generated_poc.media_buy.get_media_buy_delivery_request import StatusFilter

        root = rootmodel_root(StatusFilter)
        assert root is not None, "StatusFilter is a RootModel; its root must be reachable"
        assert typing.get_origin(root) is list

    def test_returns_none_for_non_rootmodel(self):
        from pydantic import BaseModel

        class Plain(BaseModel):
            x: int = 0

        assert rootmodel_root(Plain) is None
        assert rootmodel_root(str) is None
        assert rootmodel_root(list[str]) is None
        assert rootmodel_root(str | None) is None

"""Annotation introspection primitives shared by the type-alignment guards.

Several guards walk type annotations to answer questions like "does this parameter accept an
array?" or "is this wrapper parameter typed as a bare scalar?". Each guard has its own return
contract — names, classes, scalars, raw args — but they all need the same three primitives, and
getting any of them wrong makes a guard fall through to a value that satisfies no membership
check, so it passes while grading nothing.

That is not hypothetical: the identical union blind spot was written twice inside
``tests/unit/test_mcp_tool_type_alignment.py`` (``_scalar_leaves`` and ``normalize_type``), and
both times it was caught by mutation rather than review. These primitives exist so a future
walker cannot be born blind:

- ``union_args`` — the members of a union under BOTH spellings. ``get_origin`` returns
  ``typing.Union`` for ``Optional[X]`` / ``Union[X, Y]`` but ``types.UnionType`` for the PEP 604
  ``X | None`` this codebase actually writes.
- ``unwrap_annotated`` — the base type behind ``Annotated[T, ...]``, whose metadata otherwise
  hides ``T``.
- ``rootmodel_root`` — the root annotation of a pydantic ``RootModel``. The adcp SDK spells a
  JSON array as ``RootModel[list[X]]`` (e.g. ``StatusFilter``), so array-ness lives one level
  down and is invisible to a walker that stops at the class.

Meta-tested by ``tests/unit/test_type_introspection_helpers.py``.
"""

from __future__ import annotations

import types
import typing
from typing import Any, get_args, get_origin

__all__ = ["rootmodel_root", "union_args", "unwrap_annotated"]


def unwrap_annotated(hint: Any) -> Any:
    """Return the base type behind ``Annotated[T, ...]``; any other hint unchanged."""
    if get_origin(hint) is typing.Annotated:
        return get_args(hint)[0]
    return hint


def union_args(hint: Any) -> tuple[Any, ...]:
    """Return the members of ``hint`` if it is a union, under either spelling; ``()`` otherwise.

    Handles ``typing.Union[X, Y]`` / ``typing.Optional[X]`` (``get_origin`` -> ``typing.Union``)
    and the PEP 604 ``X | Y`` (``get_origin`` -> ``types.UnionType``). Matching only the first
    makes every ``X | None`` annotation in this codebase read as "not a union".
    """
    origin = get_origin(hint)
    if origin is typing.Union or origin is types.UnionType:
        return get_args(hint)
    return ()


def rootmodel_root(hint: Any) -> Any | None:
    """Return the root annotation of a pydantic ``RootModel`` subclass, else ``None``.

    ``RootModel[list[X]]`` is an array on the wire, so a guard asking "does this accept an array?"
    must see through the wrapper class.
    """
    if not isinstance(hint, type):
        return None
    try:
        from pydantic import RootModel
    except ImportError:  # pragma: no cover - pydantic is a hard dependency
        return None
    if not issubclass(hint, RootModel):
        return None
    root_field = hint.model_fields.get("root")
    return root_field.annotation if root_field is not None else None

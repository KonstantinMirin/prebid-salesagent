"""Structural guard: MCP wrapper scalar params must have Field(description=...).

Ensures that scalar parameters (str, int, float, bool) in MCP tool wrapper
functions use Annotated[type, Field(description=...)] so buyer agents see
meaningful descriptions in the JSON Schema, not just parameter names.
"""

import typing
from typing import Any

import pytest
from pydantic.fields import FieldInfo

from tests.helpers import union_args, unwrap_annotated
from tests.unit.test_architecture_wrapper_typed_params import MCP_WRAPPERS

# Parameters to skip — transport infrastructure or non-domain params
SKIP_PARAMS = {
    "ctx",  # FastMCP Context — transport infra
    "return",  # Return type annotation
}

# Base scalar types that need descriptions
SCALAR_TYPES = {str, int, float, bool}


def _get_base_types(annotation: Any) -> set[type]:
    """Extract the concrete base types from an annotation, unwrapping Annotated and Union.

    The unwrapping goes through ``tests.helpers.type_introspection`` so that both union spellings
    stay handled in one place: a walker that resolves only ``typing.Union`` reads every PEP 604
    ``X | None`` as an opaque leaf, and this guard then sees no scalars anywhere and passes
    without grading anything.
    """
    annotation = unwrap_annotated(annotation)

    if members := union_args(annotation):
        result: set[type] = set()
        for arg in members:
            result.update(_get_base_types(arg))
        return result

    # Discard NoneType
    if annotation is type(None):
        return set()

    return {annotation}


def _is_scalar_type(annotation: Any) -> bool:
    """Check if annotation resolves to a scalar type (str, int, float, bool).

    Returns False for Pydantic models, lists, dicts, and other complex types.
    """
    base_types = _get_base_types(annotation)
    if not base_types:
        return False
    # All non-None base types must be scalar
    return all(t in SCALAR_TYPES for t in base_types)


def _has_field_description(annotation: Any) -> bool:
    """Check if annotation uses Annotated[..., Field(description=...)]."""
    metadata = getattr(annotation, "__metadata__", None)
    if metadata is None:
        return False
    for meta in metadata:
        if isinstance(meta, FieldInfo) and meta.description:
            return True
    return False


class TestMcpWrapperFieldDescriptions:
    """MCP wrapper scalar params must have Field(description=...)."""

    @pytest.mark.parametrize("module_path,func_name", MCP_WRAPPERS)
    @pytest.mark.arch_guard
    def test_scalar_params_have_descriptions(self, module_path: str, func_name: str):
        """Every scalar param in MCP wrappers must have a Field description."""
        import importlib

        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        try:
            hints = typing.get_type_hints(func, include_extras=True)
        except Exception:
            import inspect

            sig = inspect.signature(func)
            hints = {n: p.annotation for n, p in sig.parameters.items()}

        violations = []
        for name, annotation in hints.items():
            if name in SKIP_PARAMS:
                continue
            if not _is_scalar_type(annotation):
                continue
            if not _has_field_description(annotation):
                violations.append(f"  {name}: {annotation!r}")

        assert not violations, (
            f"{module_path}.{func_name} has scalar params without Field(description=...):\n"
            + "\n".join(violations)
            + "\nUse Annotated[type, Field(description='...')] for buyer agent visibility."
        )

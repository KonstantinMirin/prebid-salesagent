#!/usr/bin/env python3
"""
Test that MCP tool function signatures match their schema type definitions.

This test validates that:
1. MCP tool parameter types match the corresponding schema field types
2. Parameters that accept arrays in the schema also accept arrays in the tool signature
3. Union types are properly propagated from schema to tool signature

This would have caught the status_filter bug where:
- Schema defined: str | list[str] | None
- Tool signature had: str | None (missing list[str])
"""

import inspect
import typing
from typing import Any, get_args, get_origin

import pytest

from tests.helpers import rootmodel_root, union_args, unwrap_annotated


def normalize_type(type_hint: Any) -> set[str]:
    """Normalize a type hint to a set of base type names for comparison.

    Returns simplified type names like {'str', 'list', 'None'} for union types.

    Every branch below is a way this function can stop resolving a type. When it does, it falls
    through to the opaque ``{str(type_hint)}`` fallback, which contains neither ``'list'`` nor
    ``'dict'`` — so every guard in this file that asks "does this accept an array?" answers no,
    for every annotation, and passes without grading anything. The three unwrapping steps are
    therefore load-bearing, not conveniences:

    - unions under BOTH spellings (``X | None`` has origin ``types.UnionType``, not ``typing.Union``)
    - ``Annotated[T, ...]``, whose metadata hides ``T``
    - pydantic ``RootModel[list[X]]``, which is how the adcp SDK spells a JSON array

    The walk itself lives in ``tests/helpers/type_introspection`` — shared with the other
    annotation walkers in the suite, because this exact blind spot was written twice in this one
    file (see ``TestGetSignalsObjectTypedParams._scalar_leaves``) and caught by mutation both times.
    """
    if type_hint is None:
        return {"None"}

    type_hint = unwrap_annotated(type_hint)

    # Handle Union types (both `typing.Union[...]` and the PEP 604 `X | None`)
    if members := union_args(type_hint):
        result = set()
        for arg in members:
            result.update(normalize_type(arg))
        return result

    # Handle pydantic RootModel wrappers (the SDK's spelling for a JSON array)
    root = rootmodel_root(type_hint)
    if root is not None:
        return normalize_type(root)

    origin = get_origin(type_hint)

    # Handle list types
    if origin is list:
        return {"list"}

    # Handle dict types
    if origin is dict:
        return {"dict"}

    # Handle None
    if type_hint is type(None):
        return {"None"}

    # Handle basic types
    if isinstance(type_hint, type):
        return {type_hint.__name__}

    # Handle string annotations
    if isinstance(type_hint, str):
        if "list" in type_hint.lower():
            return {"list", "str"}  # Simplified
        return {type_hint}

    return {str(type_hint)}


def get_function_param_types(func) -> dict[str, set[str]]:
    """Extract parameter types from a function signature."""
    sig = inspect.signature(func)
    hints = typing.get_type_hints(func) if hasattr(func, "__annotations__") else {}

    result = {}
    for param_name, param in sig.parameters.items():
        if param_name in ["self", "cls", "ctx", "context"]:
            continue

        type_hint = hints.get(param_name, param.annotation)
        if type_hint is inspect.Parameter.empty:
            result[param_name] = set()
        else:
            result[param_name] = normalize_type(type_hint)

    return result


def get_schema_field_types(schema_class) -> dict[str, set[str]]:
    """Extract field types from a Pydantic schema."""
    result = {}
    for field_name, field_info in schema_class.model_fields.items():
        annotation = field_info.annotation
        result[field_name] = normalize_type(annotation)
    return result


class TestNormalizeType:
    """Meta-tests: the normalizer every guard in this file depends on must actually resolve types.

    ``normalize_type`` is the oracle for both alignment guards below. When it falls through to
    its opaque ``{str(type_hint)}`` fallback, ``"list" in <result>`` is False for every real
    annotation, both guards' conditions go permanently false, and they pass while grading
    nothing. These meta-tests pin the three fall-through causes:

    - **PEP 604 unions.** ``get_origin(X | None)`` is ``types.UnionType``, not ``typing.Union``
      — and ``X | None`` is what this codebase writes everywhere. (The identical defect in this
      file's ``_scalar_leaves`` was caught by mutation, not review.)
    - **``typing.Annotated``.** Constrained SDK aliases carry metadata that hides the base type.
    - **Pydantic ``RootModel``.** The SDK expresses a JSON array as a RootModel wrapping
      ``list[...]`` (``StatusFilter`` is ``RootModel[list[MediaBuyStatus]]``), so the array-ness
      the guards check for is one level down — invisible to a normalizer that stops at the class.
    """

    def test_normalize_type_handles_both_union_spellings(self):
        """PEP 604 ``X | None`` must normalize identically to ``typing.Optional[X]``."""
        # noqa UP045 below: the explicit typing.Optional spelling IS the point — the two
        # spellings have different get_origin() results and both must be handled.
        assert normalize_type(typing.Optional[list[str]]) == {"list", "None"}  # noqa: UP045
        assert normalize_type(list[str] | None) == {"list", "None"}
        assert normalize_type(str | list[str] | None) == {"str", "list", "None"}
        assert normalize_type(dict[str, Any] | None) == {"dict", "None"}

    def test_normalize_type_unwraps_annotated(self):
        """``Annotated[T, ...]`` must normalize to ``T`` — the metadata is not part of the type."""
        assert normalize_type(typing.Annotated[list[str], "constraint"]) == {"list"}
        assert normalize_type(typing.Annotated[list[str], "constraint"] | None) == {"list", "None"}

    def test_normalize_type_unwraps_rootmodel(self):
        """A ``RootModel[list[...]]`` is an array on the wire and must normalize as one.

        Without this, the status_filter regression test below cannot fire: the SDK types
        ``status_filter`` as ``MediaBuyStatus | StatusFilter | None`` where ``StatusFilter`` is
        ``RootModel[list[MediaBuyStatus]]``, so ``"list"`` never appears in the schema types.
        """
        from adcp.types.generated_poc.media_buy.get_media_buy_delivery_request import StatusFilter

        assert normalize_type(StatusFilter) == {"list"}
        assert "list" in normalize_type(StatusFilter | None)


class TestMCPToolTypeAlignment:
    """Test that MCP tool signatures match schema definitions."""

    def test_get_media_buy_delivery_status_filter_type(self):
        """Test that get_media_buy_delivery accepts status_filter as array.

        Regression test for: status_filter defined as str | list[str] | None in schema
        but MCP tool only accepted str | None.
        """
        from src.core.schemas import GetMediaBuyDeliveryRequest
        from src.core.tools.media_buy_delivery import get_media_buy_delivery

        # Get types from schema
        schema_types = get_schema_field_types(GetMediaBuyDeliveryRequest)
        schema_status_filter = schema_types.get("status_filter", set())

        # Get types from function
        func_types = get_function_param_types(get_media_buy_delivery)
        func_status_filter = func_types.get("status_filter", set())

        # Pin the PREMISE first. This assertion used to be the condition of an `if`, which made
        # the whole test inert for its entire lifetime: normalize_type could not resolve the
        # annotation, "list" was never in the result, and the regression this test is named for
        # would have slipped through. The schema allowing an array is a fact about the pin — if
        # it stops being true, this test must fail and point at the pin, not silently stop
        # grading. (Same reason test_request_model_still_types_them_as_objects below pins its own
        # premise.)
        assert "list" in schema_status_filter, (
            f"GetMediaBuyDeliveryRequest.status_filter no longer resolves to an array type "
            f"(got {schema_status_filter}). Either the pin dropped the array form — re-derive "
            f"this guard — or normalize_type stopped resolving the annotation, in which case "
            f"every array check in this file is inert."
        )

        # Schema allows list - function must also allow list
        assert "list" in func_status_filter, (
            f"get_media_buy_delivery.status_filter should accept list type.\n"
            f"Schema type: {schema_status_filter}\n"
            f"Function type: {func_status_filter}"
        )

    def test_all_mcp_tools_array_parameters_match_schema(self):
        """Test all MCP tools accept arrays when their schemas define array types.

        This is a generalized test that catches any tool where the schema
        allows an array but the function signature doesn't.
        """
        # Import tools and their corresponding schemas
        from src.core.schemas import (
            CreateMediaBuyRequest,
            GetMediaBuyDeliveryRequest,
            GetProductsRequest,
            ListCreativesRequest,
            UpdateMediaBuyRequest,
        )
        from src.core.tools.creatives import list_creatives
        from src.core.tools.media_buy_create import create_media_buy
        from src.core.tools.media_buy_delivery import get_media_buy_delivery
        from src.core.tools.media_buy_update import update_media_buy
        from src.core.tools.products import get_products

        # Note: get_signals removed — signals is dead code (UC-008)
        tool_schema_pairs = [
            (get_media_buy_delivery, GetMediaBuyDeliveryRequest, "get_media_buy_delivery"),
            (create_media_buy, CreateMediaBuyRequest, "create_media_buy"),
            (update_media_buy, UpdateMediaBuyRequest, "update_media_buy"),
            (get_products, GetProductsRequest, "get_products"),
            (list_creatives, ListCreativesRequest, "list_creatives"),
        ]

        issues = []
        array_params_compared = []

        for func, schema_class, name in tool_schema_pairs:
            schema_types = get_schema_field_types(schema_class)
            func_types = get_function_param_types(func)

            for param_name in func_types:
                if param_name not in schema_types:
                    # Parameter not in schema (like webhook_url) - skip
                    continue

                schema_type = schema_types[param_name]
                func_type = func_types[param_name]

                if "list" in schema_type or "dict" in schema_type:
                    array_params_compared.append(f"{name}.{param_name}")

                # If schema allows list, function must also allow list
                if "list" in schema_type and "list" not in func_type:
                    issues.append(
                        f"{name}.{param_name}: Schema allows list but function doesn't.\n"
                        f"  Schema: {schema_type}\n"
                        f"  Function: {func_type}"
                    )

                # If schema allows dict, function must also allow dict
                if "dict" in schema_type and "dict" not in func_type:
                    issues.append(
                        f"{name}.{param_name}: Schema allows dict but function doesn't.\n"
                        f"  Schema: {schema_type}\n"
                        f"  Function: {func_type}"
                    )

        # Pin the premise: this test's only two conditions are "list"/"dict" membership, so a
        # normalizer that stops resolving annotations empties `issues` and the assertion below
        # passes for every possible signature. That is exactly what happened for this test's whole
        # lifetime. Requiring that the sweep actually SAW container-typed schema params makes the
        # inert state fail loudly instead of reading as clean.
        assert array_params_compared, (
            "No list/dict-typed schema parameter was compared across the 5 covered tools — the "
            "sweep below graded nothing. Either normalize_type stopped resolving annotations, or "
            "every covered schema dropped its array/object params."
        )

        assert not issues, "Found MCP tool type mismatches with schemas:\n\n" + "\n\n".join(issues)

    def test_raw_functions_match_mcp_tools(self):
        """Test that _raw functions have the same parameter types as MCP tools.

        The _raw functions (for A2A) should accept the same types as MCP tools.
        """
        from src.core.tools.media_buy_delivery import (
            get_media_buy_delivery,
            get_media_buy_delivery_raw,
        )

        mcp_types = get_function_param_types(get_media_buy_delivery)
        raw_types = get_function_param_types(get_media_buy_delivery_raw)

        # Compare common parameters
        for param in set(mcp_types.keys()) & set(raw_types.keys()):
            # Skip special params
            if param in ["webhook_url", "push_notification_config"]:
                continue

            assert mcp_types[param] == raw_types[param], (
                f"get_media_buy_delivery.{param} type mismatch between MCP and raw:\n"
                f"  MCP: {mcp_types[param]}\n"
                f"  Raw: {raw_types[param]}"
            )


class TestParameterTypeDocumentation:
    """Document parameter types for reference and debugging."""

    def test_document_delivery_parameter_types(self):
        """Document get_media_buy_delivery parameter types for reference."""
        from src.core.schemas import GetMediaBuyDeliveryRequest
        from src.core.tools.media_buy_delivery import (
            get_media_buy_delivery,
            get_media_buy_delivery_raw,
        )

        print("\n" + "=" * 80)
        print("GET_MEDIA_BUY_DELIVERY PARAMETER TYPES")
        print("=" * 80)

        print("\nSchema (GetMediaBuyDeliveryRequest):")
        for name, field in GetMediaBuyDeliveryRequest.model_fields.items():
            print(f"  {name}: {field.annotation}")

        print("\nMCP Tool (get_media_buy_delivery):")
        hints = typing.get_type_hints(get_media_buy_delivery)
        for name, hint in hints.items():
            if name not in ["return"]:
                print(f"  {name}: {hint}")

        print("\nRaw Function (get_media_buy_delivery_raw):")
        hints = typing.get_type_hints(get_media_buy_delivery_raw)
        for name, hint in hints.items():
            if name not in ["return"]:
                print(f"  {name}: {hint}")


class TestGetSignalsObjectTypedParams:
    """get_signals' $ref'd OBJECT params must not be hand-narrowed to strings.

    Regression test for the round-2 finding: ``account``, ``signal_refs[]`` and
    ``signal_ids[]`` are objects per v3.1.1
    (dist/schemas/3.1.1/signals/get-signals-request.json $refs core/account-ref.json,
    core/signal-ref.json, core/signal-id.json), and ``GetSignalsRequest`` types them as
    the SDK's AccountReference / SignalRef / SignalId. The flat MCP wrapper and the REST
    body model had them as ``str`` / ``list[str]``, so a conformant buyer was rejected at
    the FastMCP TypeAdapter (MCP) and the body model (REST) before the boundary ran —
    while A2A accepted the same payload. Same input, opposite accept/reject per transport.

    Pins the SHAPE (object, not scalar) rather than an exact annotation, so a later switch
    between ``dict[str, Any]`` and the SDK types stays green while a regression back to
    ``str``/``list[str]`` fails.
    """

    OBJECT_PARAMS = ("account", "signal_refs", "signal_ids")

    @staticmethod
    def _scalar_leaves(hint) -> set[str]:
        """Scalar type names reachable through unions and list element types.

        The union walk goes through ``tests.helpers.union_args`` because both spellings must be
        handled: ``get_origin`` returns ``typing.Union`` for ``Optional[X]`` / ``Union[X, Y]`` but
        ``types.UnionType`` for the PEP 604 ``X | None`` that this codebase actually writes.
        Matching only ``typing.Union`` makes the whole walk fall through to the scalar check, which
        a parameterised generic fails — so the function returns "no scalars" for every annotation
        and the guard silently passes. (That exact defect was present in the first draft of this
        guard and caught by mutation, not by review; it was then written a second time in
        ``normalize_type`` above, which is why the walk is now shared rather than re-implemented.)
        """
        if members := union_args(hint):
            leaves: set[str] = set()
            for arg in members:
                leaves |= TestGetSignalsObjectTypedParams._scalar_leaves(arg)
            return leaves
        origin, args = get_origin(hint), get_args(hint)
        if origin is list:
            return TestGetSignalsObjectTypedParams._scalar_leaves(args[0]) if args else set()
        if isinstance(hint, type) and hint.__name__ in ("str", "int", "float", "bool"):
            return {hint.__name__}
        return set()

    def test_scalar_leaves_detects_both_union_spellings(self):
        """Meta-test: the detector must not be blind to PEP 604 unions.

        Without this, a regression to ``list[str] | None`` — the exact shape being
        guarded against — reads as clean.
        """
        assert self._scalar_leaves(list[str] | None) == {"str"}
        # noqa UP045: the explicit typing.Optional spelling is the POINT of this
        # assertion — the two spellings have different get_origin() results, and the
        # detector must handle both. Rewriting it to `X | None` would delete the test.
        assert self._scalar_leaves(typing.Optional[list[str]]) == {"str"}  # noqa: UP045
        assert self._scalar_leaves(str | None) == {"str"}
        assert self._scalar_leaves(list[dict[str, Any]] | None) == set()
        assert self._scalar_leaves(dict[str, Any] | None) == set()

    def test_mcp_wrapper_declares_object_typed_params(self):
        from src.core.tools.signals import get_signals

        hints = typing.get_type_hints(get_signals)
        for param in self.OBJECT_PARAMS:
            assert param in hints, f"get_signals lost the {param!r} parameter"
            scalars = self._scalar_leaves(hints[param])
            assert not scalars, (
                f"get_signals MCP wrapper types {param!r} as {hints[param]} — a scalar "
                f"({', '.join(sorted(scalars))}) where v3.1.1 declares an object. A conformant "
                f"buyer's payload is rejected at the FastMCP TypeAdapter before the boundary runs."
            )

    def test_rest_body_declares_object_typed_params(self):
        from src.routes.api_v1 import GetSignalsBody

        for param in self.OBJECT_PARAMS:
            assert param in GetSignalsBody.model_fields, f"GetSignalsBody lost the {param!r} field"
            annotation = GetSignalsBody.model_fields[param].annotation
            scalars = self._scalar_leaves(annotation)
            assert not scalars, (
                f"GetSignalsBody types {param!r} as {annotation} — a scalar "
                f"({', '.join(sorted(scalars))}) where v3.1.1 declares an object. The REST body "
                f"model rejects a conformant buyer before the boundary runs."
            )

    def test_request_model_still_types_them_as_objects(self):
        """If the SDK ever widened these to accept strings, the guard above is moot.

        Pins the premise, so this file cannot keep enforcing a constraint the schema
        has dropped — the failure would point at the pin bump, not at the wrappers.
        """
        from src.core.schemas import GetSignalsRequest

        for param in self.OBJECT_PARAMS:
            annotation = GetSignalsRequest.model_fields[param].annotation
            assert not self._scalar_leaves(annotation), (
                f"GetSignalsRequest.{param} now accepts a scalar ({annotation}); "
                f"re-derive this guard against the current pin."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

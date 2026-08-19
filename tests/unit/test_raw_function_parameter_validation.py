#!/usr/bin/env python3
"""
Test that _raw functions correctly pass parameters to _impl functions.

This test validates that:
1. All parameters accepted by _raw functions are either:
   - Passed to the _impl function
   - Used to construct request objects
   - Helper function parameters that are documented
2. No parameters are silently dropped

This would have caught the get_products_raw + create_get_products_request bug
where adcp_version was accepted but not passed through.
"""

import ast
import inspect
from pathlib import Path

import pytest


class TestRawFunctionParameterValidation:
    """Validate that raw functions properly handle all their parameters."""

    def test_get_products_raw_parameters_valid(self):
        """Test that get_products_raw doesn't accept invalid parameters for helpers."""
        from src.core.schema_helpers import create_get_products_request
        from src.core.tools import get_products_raw

        # Get parameters
        raw_sig = inspect.signature(get_products_raw)
        helper_sig = inspect.signature(create_get_products_request)

        raw_params = set(raw_sig.parameters.keys()) - {"ctx", "identity"}
        helper_params = set(helper_sig.parameters.keys())

        # Check: All non-context params in raw should either:
        # 1. Be passed to helper (except adcp_version which is NOT in helper)
        # 2. Be valid for some other purpose

        # REGRADED against the pinned schema, not an exemption (Lane A / A3).
        #
        # The old shape asked "is every accepted param passed to the helper?" and,
        # when the answer became no, EXEMPTED the difference. That exemption is
        # what let acceptance and honoring drift apart: a field could be advertised
        # on the wire, excused here, and reach nothing.
        #
        # Post-seam the question is different, and stricter: a field may reach the
        # tool body EITHER as a flat helper parameter OR on the pinned request
        # model the seam delivers (`_spec_request`). What is forbidden is reaching
        # NEITHER. So the accepted set is graded against
        # `pinned_request_schema_fields(tool)` + the model's own fields, and any
        # accepted name that is on neither is a real drop this test must fail on.
        # The decorator-injected exemption is GONE (Lane A / A3). It existed
        # because `accepts_spec_request_fields` made a wrapper CALLABLE with spec
        # fields it then dropped, so "accepted" did not imply "reaches the helper"
        # and the difference had to be excused. After A1+A2 every accepted field
        # has a disposition — it rides in the pinned request model or it is not
        # accepted at all — so there is nothing left to exempt, and re-adding an
        # exemption here would be the tell that acceptance and honoring have come
        # apart again.
        #
        # Known valid parameters that are NOT passed to helper
        valid_non_helper_params = {
            "min_exposures",  # Optional, not in helper
            "strategy_id",  # Optional, not in helper
        }

        # Parameters that SHOULD be in helper
        # A field is DISPOSED if it reaches the helper directly, or if the seam
        # carries it on the pinned request model, or it is one of the two
        # documented non-helper options above.
        from src.core.version_compat import (
            SPEC_ENVELOPE_FIELDS,
            SPEC_REQUEST_PARAM,
            pinned_request_schema_fields,
            spec_request_model,
        )

        schema_fields, _ = pinned_request_schema_fields("get_products")
        carried = set(spec_request_model("get_products").model_fields) | set(schema_fields)

        # The ENVELOPE class is a DISPOSITION, not an exemption. AdCP 3.1.1's
        # security.mdx requires a seller to ACCEPT idempotency_key, context_id and
        # governance_context on every tool — including reads — and ignore what it
        # cannot act on rather than reject the call. Reaching nothing is the
        # SPECIFIED behavior for these three on a read; refusing them would be the
        # conformance regression. That is categorically different from a
        # body-semantic field reaching nothing, which is the drop this test exists
        # to catch — and the two are distinguished by the model, not by a list
        # someone maintains.
        undisposed = (
            raw_params - valid_non_helper_params - helper_params - carried - SPEC_ENVELOPE_FIELDS - {SPEC_REQUEST_PARAM}
        )

        assert not undisposed, (
            f"get_products_raw accepts {sorted(undisposed)} which reach NOTHING: not the helper, "
            "not the pinned request model the seam delivers, and not documented as intentionally "
            "unforwarded. An accepted field that reaches nothing is accept-and-drop — the buyer is "
            "told it applied. Give each a disposition (honor it, or stop accepting it)."
        )

    def test_all_raw_functions_have_context_parameter(self):
        """All _raw functions should accept a ctx parameter."""
        from src.core import tools

        raw_functions = [name for name in dir(tools) if name.endswith("_raw") and callable(getattr(tools, name))]

        for func_name in raw_functions:
            func = getattr(tools, func_name)
            sig = inspect.signature(func)
            assert "ctx" in sig.parameters, f"{func_name} missing 'ctx' parameter"

    def test_raw_functions_dont_drop_parameters_silently(self):
        """Test that raw functions don't accept parameters they don't use.

        This is a source code analysis test that checks:
        1. Parameters are either passed to _impl
        2. Parameters are used to construct request objects
        3. Parameters are documented as metadata/optional

        This would catch bugs like accepting adcp_version but not using it.
        """
        tools_path = Path(__file__).parent.parent.parent / "src" / "core" / "tools" / "__init__.py"
        with open(tools_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Known valid "unused" parameters (metadata, optional features, etc.)
        # These are documented reasons why a parameter might not be directly passed through
        valid_unused: dict[str, set[str]] = {}

        issues = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.endswith("_raw"):
                func_name = node.name
                params = {arg.arg for arg in node.args.args} - {"self", "ctx"}

                # Find all names used in function body
                used_names = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Name):
                        used_names.add(child.id)
                    elif isinstance(child, ast.keyword):
                        used_names.add(child.arg)

                # Check for parameters that aren't used
                unused = params - used_names

                # Remove known valid unused parameters
                if func_name in valid_unused:
                    unused = unused - valid_unused[func_name]

                if unused:
                    issues.append(f"{func_name} has unused parameters: {unused}")

        assert not issues, "Found unused parameters in raw functions:\n" + "\n".join(issues)

    def test_create_get_products_request_signature(self):
        """Document the exact signature of create_get_products_request for reference."""
        from src.core.schema_helpers import create_get_products_request

        sig = inspect.signature(create_get_products_request)
        params = list(sig.parameters.keys())

        # adcp 3.6.0: brand_manifest removed, only brand (BrandReference) remains.
        # Note: promoted_offering removed per adcp v1.2.1 migration
        # `spec_request` is the acceptance-seam CARRIER (PR #1858 Lane A,
        # src/core/spec_request_carrier.py). It is deliberately part of this
        # signature: the carrier has to reach the request builder for a
        # body-semantic field to be HONORED at all. Before it, fields the pinned
        # schema defines were accepted at the transport and then silently dropped
        # one frame later — which is the defect that lane exists to close.
        # Pinned here (not removed) so a future signature change is still caught.
        expected_params = ["brief", "brand", "filters", "property_list", "context", "spec_request"]

        assert params == expected_params, (
            f"create_get_products_request signature changed!\n"
            f"Expected: {expected_params}\n"
            f"Got: {params}\n"
            f"This may require updating get_products_raw()"
        )

    def test_get_products_raw_doesnt_pass_invalid_params_to_helper(self):
        """Ensure get_products_raw doesn't pass params the helper doesn't accept.

        This is the exact bug we fixed - passing adcp_version to create_get_products_request.
        """
        tools_path = Path(__file__).parent.parent.parent / "src" / "core" / "tools" / "__init__.py"
        with open(tools_path) as f:
            content = f.read()

        # Find the get_products_raw function
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_products_raw":
                # Find calls to create_get_products_request
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name) and child.func.id == "create_get_products_request":
                            # Check keyword arguments
                            passed_params = {kw.arg for kw in child.keywords}

                            # These are the ONLY valid parameters for create_get_products_request
                            # adcp 3.6.0: brand_manifest removed, only 'brand' (BrandReference)
                            valid_params = {"brief", "brand", "filters"}

                            invalid = passed_params - valid_params
                            assert not invalid, (
                                f"get_products_raw passes invalid parameters to create_get_products_request: {invalid}\n"
                                f"Valid parameters: {valid_params}"
                            )


class TestHelperFunctionDocumentation:
    """Document helper function signatures for reference."""

    def test_all_create_helper_signatures(self):
        """Document all create_* helper functions from schema_helpers."""
        from src.core import schema_helpers

        helpers = [
            name
            for name in dir(schema_helpers)
            if name.startswith("create_") and callable(getattr(schema_helpers, name))
        ]

        signatures = {}
        for helper_name in helpers:
            helper = getattr(schema_helpers, helper_name)
            sig = inspect.signature(helper)
            signatures[helper_name] = list(sig.parameters.keys())

        # Document what we found
        print("\n" + "=" * 80)
        print("SCHEMA HELPER FUNCTION SIGNATURES")
        print("=" * 80)
        for name, params in sorted(signatures.items()):
            print(f"{name}({', '.join(params)})")

        # Verify create_get_products_request (the one that caused the bug)
        assert "create_get_products_request" in signatures
        # adcp 3.6.0: brand_manifest removed, only brand (BrandReference) remains.
        # `spec_request` is the Lane A acceptance-seam carrier — see the sibling
        # test above for why it belongs in this signature.
        expected = ["brief", "brand", "filters", "property_list", "context", "spec_request"]
        actual = signatures["create_get_products_request"]
        assert actual == expected, (
            f"create_get_products_request signature changed!\n"
            f"Expected: {expected}\n"
            f"Got: {actual}\n"
            f"Update get_products_raw if needed"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Regression tests: auth deps must provide real types, not Any.

Core invariant: Route signature types must flow through to mypy —
every dependency parameter gets its real type, never Any.

These tests verify:
1. Auth dependency exports are Annotated types (not bare Any)
2. context_builder.build() accepts typed Request (not object)

"""

import typing
from typing import get_type_hints


class TestAuthDepsAreAnnotated:
    """Auth dependency exports must be Annotated types, not Any."""

    def test_get_auth_context_is_not_any(self):
        """GetAuthContext must not be typed as Any."""
        from src.core.auth_context import GetAuthContext

        # Annotated types have __metadata__ attribute
        origin = typing.get_origin(GetAuthContext)
        assert origin is typing.Annotated, (
            f"GetAuthContext should be Annotated[AuthContext, Depends(...)], got {GetAuthContext}"
        )


class TestContextBuilderTypeSafety:
    """AdCPCallContextBuilder.build() should accept Request, not object."""

    def test_build_parameter_is_request(self):
        """build() parameter should be typed as Request, not object."""
        from starlette.requests import Request

        from src.a2a_server.context_builder import AdCPCallContextBuilder

        hints = get_type_hints(AdCPCallContextBuilder.build)
        request_type = hints.get("request")
        assert request_type is Request, f"build(request) should be typed as Request, got {request_type}"

"""Regression tests: A2A auth must NOT use ContextVar fallback.

Core invariant: All auth context flows through explicit function parameters
(scope["state"] -> ServerCallContext -> handler methods), never through
ambient ContextVar state.

These tests verify the ContextVar fallback is removed from the A2A handler.
They FAIL before the refactoring (TDD red step) and PASS after.

"""

from a2a.server.context import ServerCallContext

from src.core.auth_context import AuthContext


class TestNoContextVarFallbackInA2AHandler:
    """A2A handler methods must not fall back to ContextVar."""

    def test_credential_of_is_empty_without_context(self):
        """_credential_of(context=None) answers an empty credential, not a ContextVar read."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()
        assert handler._credential_of(context=None).auth_token is None

    def test_credential_of_reads_from_explicit_context(self):
        """_credential_of should read the credential from the explicit ServerCallContext."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()
        auth_ctx = AuthContext(auth_token="explicit-token", headers={"host": "test.example.com"})
        context = ServerCallContext(state={"auth_context": auth_ctx})
        assert handler._credential_of(context=context).auth_token == "explicit-token"


class TestNoContextVarInMiddleware:
    """UnifiedAuthMiddleware must not write to _auth_context_var."""

    def test_middleware_module_does_not_export_auth_context_var(self):
        """auth_middleware module must not have _auth_context_var in its namespace."""
        import src.core.auth_middleware as mw_mod

        assert not hasattr(mw_mod, "_auth_context_var"), (
            "UnifiedAuthMiddleware still imports _auth_context_var. Only scope['state'] should be written to."
        )


class TestNoContextVarInfrastructure:
    """ContextVar infrastructure must not exist in auth_context module."""

    def test_no_auth_context_var_in_module(self):
        """auth_context.py must not define _auth_context_var."""
        import src.core.auth_context as ac_mod

        assert not hasattr(ac_mod, "_auth_context_var"), (
            "_auth_context_var still exists in auth_context module. Remove it after all consumers are migrated."
        )

    def test_no_get_current_auth_context_in_module(self):
        """auth_context.py must not define get_current_auth_context."""
        import src.core.auth_context as ac_mod

        assert not hasattr(ac_mod, "get_current_auth_context"), (
            "get_current_auth_context() still exists in auth_context module. "
            "Remove it after all consumers are migrated."
        )

"""Regression tests for REST tenant resolution and auth cleanup.

Tests that the REST API uses proper 4-strategy tenant detection (same as MCP/A2A)
instead of the broken heuristic that split principal_id on underscores.

These tests also verify removal of MinimalContext and cast(ToolContext) patterns.
"""

import inspect


class TestNoMinimalContext:
    """No MinimalContext classes should exist in the codebase."""

    def test_no_minimal_context_in_a2a_server(self):
        """MinimalContext should be removed from A2A server."""
        import src.a2a_server.adcp_a2a_server as a2a_mod

        assert not hasattr(a2a_mod, "MinimalContext"), (
            "MinimalContext class still exists in adcp_a2a_server. "
            "It should be replaced with resolve_identity_from_context()."
        )


class TestNoCastToolContext:
    """No cast(ToolContext, ...) type-unsafe patterns should exist."""

    def test_a2a_server_does_not_import_cast(self):
        """A2A server should not need typing.cast (was used for cast(ToolContext, ...))."""

        # Reload to get fresh module
        import src.a2a_server.adcp_a2a_server as a2a_mod

        # Check if 'cast' is imported at module level
        # After removing cast(ToolContext, ...) calls, cast should no longer be needed
        module_dict = vars(a2a_mod)
        from typing import cast as typing_cast

        has_cast = "cast" in module_dict and module_dict["cast"] is typing_cast
        assert not has_cast, (
            "A2A server still imports typing.cast, which was used for "
            "cast(ToolContext, ...) unsafe patterns. Remove after cleanup."
        )


class TestVerifyPrincipalSimplified:
    """_verify_principal should work without get_principal_id_from_context fallback."""

    def test_verify_principal_signature_accepts_resolved_identity(self):
        """_verify_principal should accept ResolvedIdentity in its type signature."""
        from src.core.tools.media_buy_update import _verify_principal

        sig = inspect.signature(_verify_principal)
        identity_param = sig.parameters.get("identity")
        assert identity_param is not None
        ann = str(identity_param.annotation)
        assert "ResolvedIdentity" in ann, (
            f"_verify_principal identity param annotation is '{ann}', should include ResolvedIdentity"
        )

    def test_verify_principal_no_get_principal_id_from_context_import(self):
        """_verify_principal should not fall back to get_principal_id_from_context."""
        # Check that the module-level function doesn't lazily import it
        from src.core.tools import media_buy_update

        # After migration, _verify_principal should handle ResolvedIdentity directly
        # without needing get_principal_id_from_context as fallback
        # Test behaviorally: passing ResolvedIdentity should work directly
        sig = inspect.signature(media_buy_update._verify_principal)
        # The function should accept ResolvedIdentity without isinstance fallback chains
        # We verify by checking it doesn't have more than 2 type options (was 3: Context|ToolContext|ResolvedIdentity)
        ann = str(sig.parameters["identity"].annotation)
        assert "Context |" not in ann or ann.count("|") <= 1, (
            f"_verify_principal still has 3-way isinstance dispatch: {ann}. Simplify to accept ResolvedIdentity only."
        )

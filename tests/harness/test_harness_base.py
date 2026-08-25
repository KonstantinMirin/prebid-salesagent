"""Meta-tests for BaseTestEnv / IntegrationEnv base contracts.

Guards the DRY-01 refactor: merging IntegrationEnv + ImplTestEnv into
a single BaseTestEnv. These tests verify that both integration and unit
modes share the same lifecycle contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBaseClassContract:
    """BaseTestEnv must work in both integration (use_real_db=True) and unit modes."""

    def test_integration_env_has_mock_dict(self):
        """IntegrationEnv.__enter__ populates self.mock from EXTERNAL_PATCHES."""
        from tests.harness._base import IntegrationEnv

        class _TestEnv(IntegrationEnv):
            EXTERNAL_PATCHES = {
                "some_dep": "os.getcwd",
            }

        env = _TestEnv()
        # Before enter, mock dict is empty
        assert env.mock == {}

        with patch("src.core.database.database_session.get_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            with patch("tests.factories.ALL_FACTORIES", []):
                with env:
                    assert "some_dep" in env.mock
                    assert isinstance(env.mock["some_dep"], MagicMock)

        # After exit, mock dict is cleared
        assert env.mock == {}

    def test_unit_env_has_mock_dict(self):
        """BaseTestEnv.__enter__ populates self.mock from EXTERNAL_PATCHES."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"some_dep": "os.getcwd"}

        env = _TestEnv()
        assert env.mock == {}

        with env:
            assert "some_dep" in env.mock
            assert isinstance(env.mock["some_dep"], MagicMock)

        assert env.mock == {}

    def test_integration_env_identity_is_lazy(self):
        """Identity is built on first access, not in __init__."""
        from tests.harness._base import IntegrationEnv

        env = IntegrationEnv(principal_id="p1", tenant_id="t1")
        assert env._identity_cache == {}
        identity = env.identity
        assert identity.principal_id == "p1"
        assert identity.tenant_id == "t1"

    def test_unit_env_identity_is_lazy(self):
        """Identity is built on first access, not in __init__."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv(principal_id="p1", tenant_id="t1")
        assert env._identity_cache == {}
        identity = env.identity
        assert identity.principal_id == "p1"
        assert identity.tenant_id == "t1"

    def test_integration_env_patches_are_reversed_on_exit(self):
        """Patches are stopped in reverse order on exit."""
        from tests.harness._base import IntegrationEnv

        class _TestEnv(IntegrationEnv):
            EXTERNAL_PATCHES = {
                "a": "os.getcwd",
                "b": "os.getpid",
            }

        env = _TestEnv()
        with patch("src.core.database.database_session.get_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            with patch("tests.factories.ALL_FACTORIES", []):
                with env:
                    assert len(env._patchers) == 2
                # After exit, patchers are cleared
                assert len(env._patchers) == 0

    def test_unit_env_patches_are_reversed_on_exit(self):
        """Patches are stopped in reverse order on exit."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"a": "os.getcwd", "b": "os.getpid"}

        env = _TestEnv()
        with env:
            assert len(env._patchers) == 2
        assert len(env._patchers) == 0

    def test_identity_respects_dry_run(self):
        """Both base classes pass dry_run to testing_context."""
        from tests.harness._base import BaseTestEnv, IntegrationEnv

        for cls in [IntegrationEnv, BaseTestEnv]:
            env = cls(dry_run=True)
            assert env.identity.testing_context.dry_run is True

    def test_configure_mocks_called_during_enter(self):
        """_configure_mocks is called after patches start."""
        from tests.harness._base import BaseTestEnv

        configure_called = []

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"dep": "os.getcwd"}

            def _configure_mocks(self):
                # Verify mocks are already available when configure is called
                configure_called.append(list(self.mock.keys()))

        with _TestEnv():
            pass

        assert configure_called == [["dep"]]

    def test_integration_env_has_use_real_db(self):
        """IntegrationEnv has use_real_db=True, BaseTestEnv has False."""
        from tests.harness._base import BaseTestEnv, IntegrationEnv

        assert BaseTestEnv.use_real_db is False
        assert IntegrationEnv.use_real_db is True

    def test_exit_cleans_up_even_when_patcher_raises(self):
        """__exit__ must stop all patchers even if one raises during stop."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {
                "a": "os.getcwd",
                "b": "os.getpid",
            }

        env = _TestEnv()
        env.__enter__()

        # Sabotage patcher "b" (last started, first stopped) to raise on stop
        env._patchers[-1].stop = MagicMock(side_effect=RuntimeError("stop failed"))

        # __exit__ should still clean up patcher "a" and clear state
        # even though patcher "b" raises
        try:
            env.__exit__(None, None, None)
        except RuntimeError:
            pass  # Expected from the sabotaged patcher

        # Key assertion: mock dict and patchers list must be cleared
        assert env._patchers == []
        assert env.mock == {}

    def test_exception_in_test_body_still_cleans_up(self):
        """If test body raises, __exit__ still cleans up patches and mock dict."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"a": "os.getcwd", "b": "os.getpid"}

        env = _TestEnv()
        try:
            with env:
                assert len(env.mock) == 2
                raise ValueError("simulated test failure")
        except ValueError:
            pass

        # Cleanup must have happened despite the exception
        assert env.mock == {}
        assert env._patchers == []

    def test_identity_for_returns_correct_protocol(self):
        """identity_for(transport) sets the correct protocol on identity."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv(principal_id="p1", tenant_id="t1")

        mcp_id = env.identity_for(Transport.MCP)
        assert mcp_id.protocol == "mcp"

        a2a_id = env.identity_for(Transport.A2A)
        assert a2a_id.protocol == "a2a"

        rest_id = env.identity_for(Transport.REST)
        assert rest_id.protocol == "rest"

        # All share same principal/tenant
        for ident in [mcp_id, a2a_id, rest_id]:
            assert ident.principal_id == "p1"
            assert ident.tenant_id == "t1"

    def test_identity_for_is_cached_per_protocol(self):
        """Repeated calls with same transport return same identity object."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv()
        id1 = env.identity_for(Transport.REST)
        id2 = env.identity_for(Transport.REST)
        assert id1 is id2

    def test_identity_backward_compat(self):
        """env.identity still works and defaults to the mcp protocol."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv(principal_id="p1")
        assert env.identity.principal_id == "p1"
        assert env.identity.protocol == "mcp"

    def test_call_via_raises_for_unimplemented_transport(self):
        """call_via with Transport.A2A raises NotImplementedError if call_a2a not overridden."""

        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv()
        result = env.call_via(Transport.A2A)
        assert result.is_error
        assert isinstance(result.error, NotImplementedError)

    def test_call_via_mcp_raises_for_unimplemented(self):
        """call_via with Transport.MCP raises NotImplementedError if call_mcp not overridden."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv()
        result = env.call_via(Transport.MCP)
        assert result.is_error
        assert isinstance(result.error, NotImplementedError)

    def test_call_via_mcp_routes_through_call_mcp(self):
        """call_via(Transport.MCP) dispatches through McpDispatcher → call_mcp."""

        from pydantic import BaseModel

        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        class _Resp(BaseModel):
            ok: bool = True

        class _TestEnv(BaseTestEnv):
            def call_mcp(self, **kwargs):
                return _Resp()

        env = _TestEnv()
        result = env.call_via(Transport.MCP)
        assert result.is_success
        assert result.payload.ok is True
        assert result.envelope.get("transport") == "mcp"

    def test_nested_integration_env_raises(self):
        """Nesting two IntegrationEnvs must raise to prevent session corruption."""
        import pytest

        from tests.harness._base import IntegrationEnv

        class _TestEnv(IntegrationEnv):
            EXTERNAL_PATCHES = {"dep": "os.getcwd"}

        with patch("src.core.database.database_session.get_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            # First env binds factories
            with patch("tests.factories.ALL_FACTORIES", [MagicMock(_meta=MagicMock(sqlalchemy_session=None))]):
                with _TestEnv():
                    # Second env should fail because factories are already bound
                    with pytest.raises(AssertionError, match="already bound"):
                        _TestEnv().__enter__()


class TestEnvMethodNamingConsistency:
    """Env methods with the same name across subclasses must have consistent semantics."""

    def test_integration_env_has_setup_default_data(self):
        """IntegrationEnv.setup_default_data creates tenant + principal via factories."""
        from tests.harness._base import IntegrationEnv

        assert hasattr(IntegrationEnv, "setup_default_data"), (
            "IntegrationEnv should have setup_default_data() to reduce boilerplate"
        )

    def test_base_env_has_no_run_mcp_wrapper(self):
        """BaseTestEnv must NOT expose a wrapper-bypass dispatch path.

        Inverted from a test that asserted ``_run_mcp_wrapper`` EXISTS -- a test
        demanding the bypass stay alive was the only thing keeping it alive.

        The method invoked a tool wrapper directly, skipping the FastMCP
        middleware chain and TypeAdapter validation. On an error path a raised
        AdCPError therefore never became a ToolError, so the dispatcher captured
        ``wire_error_envelope=None`` and every mcp error assertion in such an env
        silently graded a reconstructed exception instead of the wire -- the exact
        false-green salesagent-3dawm exists to remove. Deleting it makes the
        bypass unexpressible rather than merely deprecated, which is also why no
        guard forbidding its use is needed. Use ``_run_mcp_client``.
        """
        from tests.harness._base import BaseTestEnv

        assert not hasattr(BaseTestEnv, "_run_mcp_wrapper"), (
            "BaseTestEnv._run_mcp_wrapper is back. It bypasses the FastMCP pipeline, "
            "so mcp error scenarios capture no wire envelope and grade a reconstructed "
            "exception instead. Dispatch by tool name through _run_mcp_client."
        )

    def test_creative_sync_env_has_set_run_async_result(self):
        """CreativeSyncEnv uses set_run_async_result, not set_registry_formats.

        set_registry_formats patches registry.list_all_formats (CreativeFormatsEnv).
        CreativeSyncEnv patches run_async.side_effect, which is a different mechanic.
        Using the same name is a trap for new Env authors.
        """
        from tests.harness.creative_sync import CreativeSyncEnv

        assert hasattr(CreativeSyncEnv, "set_run_async_result"), (
            "CreativeSyncEnv should have set_run_async_result (not set_registry_formats)"
        )
        assert not hasattr(CreativeSyncEnv, "set_registry_formats"), (
            "CreativeSyncEnv should NOT have set_registry_formats — "
            "that name belongs to CreativeFormatsEnv (different mechanic)"
        )


class TestIsE2EProperty:
    """BaseTestEnv.is_e2e keys on e2e_config, not database_url."""

    def test_is_e2e_true_when_e2e_config_set(self):
        """e2e_config set -> is_e2e True."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        env = BaseTestEnv(e2e_config=E2EConfig(base_url="http://unused", postgres_url="postgresql://x/y"))
        assert env.is_e2e is True

    def test_is_e2e_false_with_database_url_only(self):
        """database_url alone rebinds the DB but is NOT e2e mode."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv(database_url="postgresql://x/y")
        assert env.is_e2e is False

    def test_is_e2e_false_when_neither_set(self):
        """No e2e_config, no database_url -> in-process mode."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv()
        assert env.is_e2e is False

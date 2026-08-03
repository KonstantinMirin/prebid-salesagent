"""Meta-tests for AdCPTestClient — the transport-generic dispatch core (SB-2b).

``AdCPTestClient.call(tool, payload, transport)`` bypasses every env's
hand-written ``call_a2a``/``call_mcp``/``build_rest_body``/``parse_rest_response``
quartet (design doc §1) and dispatches purely from the derived
``ADDRESS_TABLE`` + the shared ``_run_mcp_client``/``_run_a2a_handler``/
``_prepare_rest_request`` primitives on ``BaseTestEnv``/``IntegrationEnv``.

These tests deliberately use envs that do NOT implement ``call_a2a``/
``call_mcp`` (e.g. ``tests.harness.product_unit.ProductEnv``) to prove the
client does not need those per-env methods at all — the whole point of the
design (§1 "MediaBuyDualEnv is the reductio").
"""

from __future__ import annotations

import json

import pytest

from tests.harness._base import BareIntegrationEnv, BaseTestEnv
from tests.harness.address_table import NoAddressForTransport, ToolAddress
from tests.harness.client import AdCPTestClient, _wrap_rest
from tests.harness.transport import Transport


class TestClientMcpDispatchNoDb:
    """MCP dispatch through the generic client — no per-env call_mcp needed."""

    def test_get_products_via_mcp_succeeds(self):
        from tests.harness.product_unit import ProductEnv

        with ProductEnv() as env:
            env.add_product(product_id="prod_001", name="Display Ad")
            client = AdCPTestClient(env)

            result = client.call("get_products", {"brief": "display ads"}, Transport.MCP)

        assert result.is_success, result.error
        assert result.envelope["transport"] == "mcp"
        assert result.wire_response is not None
        product_ids = [p["product_id"] for p in result.payload["products"]]
        assert product_ids == ["prod_001"]

    def test_unauthenticated_dispatch_surfaces_auth_required(self):
        """identity=None (EXPLICIT) reaches the server unauthenticated — the same
        convention env._run_mcp_client already gives identity=None (design doc §3
        table). Proves the client's _NO_IDENTITY_OVERRIDE sentinel correctly
        distinguishes "no override" from "explicit unauthenticated"."""

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            result = client.call("list_accounts", {}, Transport.MCP, identity=None)

        assert result.is_error
        result.assert_wire_error("AUTH_REQUIRED")


class TestClientA2ADispatchNoDb:
    """A2A dispatch through the generic client — no per-env call_a2a needed."""

    def test_get_products_via_a2a_succeeds(self):
        from tests.harness.product_unit import ProductEnv

        with ProductEnv() as env:
            env.add_product(product_id="prod_001", name="Display Ad")
            client = AdCPTestClient(env)

            result = client.call("get_products", {"brief": "display ads"}, Transport.A2A)

        assert result.is_success, result.error
        assert result.envelope["transport"] == "a2a"
        product_ids = [p["product_id"] for p in result.payload["products"]]
        assert product_ids == ["prod_001"]


class TestClientNoAddressForTransport:
    """Tools that don't exist on a transport raise, they don't KeyError or hang."""

    def test_a2a_only_skill_on_rest_raises_no_address(self):
        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            with pytest.raises(NoAddressForTransport):
                client.call("approve_creative", {}, Transport.REST)


class TestClientRestWrapPathParamPeeling:
    """Pure-function coverage of the path-param generalization (design doc §4) —
    the rule that replaces MediaBuyDualEnv's hand-coded single-route version."""

    def test_peels_path_param_into_url_and_out_of_body(self):
        address = ToolAddress(
            Transport.REST, name="update_media_buy", path_template="/api/v1/media-buys/{media_buy_id}", method="put"
        )
        wrapped = _wrap_rest(address, {"media_buy_id": "mb_123", "paused": True})

        assert wrapped["url"] == "/api/v1/media-buys/mb_123"
        assert wrapped["body"] == {"paused": True}

    def test_no_path_params_leaves_body_and_url_untouched(self):
        address = ToolAddress(Transport.REST, name="get_products", path_template="/api/v1/products", method="post")
        wrapped = _wrap_rest(address, {"brief": "video ads"})

        assert wrapped["url"] == "/api/v1/products"
        assert wrapped["body"] == {"brief": "video ads"}

    def test_multiple_path_params_all_peeled(self):
        address = ToolAddress(Transport.REST, name="fake_tool", path_template="/api/v1/a/{a_id}/b/{b_id}", method="put")
        wrapped = _wrap_rest(address, {"a_id": "1", "b_id": "2", "extra": "kept"})

        assert wrapped["url"] == "/api/v1/a/1/b/2"
        assert wrapped["body"] == {"extra": "kept"}


class TestClientE2eRestDelivery:
    """E2E_REST DELIVER (``_deliver_e2e_rest``, salesagent-uz00/SB-3a) — real
    HTTP through nginx to a live Docker stack. Mocks ``httpx.Client`` so
    coverage does not require a live server; genuine e2e-with-real-server
    verification happens in ``tests/e2e/``."""

    def _make_env_with_e2e_config(self):
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        return _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack.test", postgres_url="postgresql://x/y"))

    def test_e2e_rest_delivery_sends_real_http_request(self, monkeypatch):
        import httpx

        from tests.factories.principal import PrincipalFactory

        captured = {}

        class _FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return {"products": []}

        class _FakeClient:
            def __init__(self, *, base_url, timeout):
                captured["base_url"] = base_url
                captured["timeout"] = timeout

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def post(self, url, *, json, headers):
                captured["url"] = url
                captured["json"] = json
                captured["headers"] = headers
                return _FakeResponse()

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        identity = PrincipalFactory.make_identity(
            principal_id="p1", tenant_id="t1", protocol="rest", auth_token="tok_abc"
        )

        with self._make_env_with_e2e_config() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "video ads"}, Transport.E2E_REST, identity=identity)

        assert result.is_success, result.error
        assert captured["base_url"] == "http://e2e-stack.test"
        assert captured["url"] == "/api/v1/products"
        assert captured["json"] == {"brief": "video ads"}
        assert captured["headers"]["x-adcp-auth"] == "tok_abc"
        assert captured["headers"]["x-adcp-tenant"] == identity.tenant["subdomain"]

    def test_e2e_rest_delivery_unauthenticated_omits_auth_header(self, monkeypatch):
        import httpx

        from src.core.exceptions import AdCPAuthRequiredError, build_two_layer_error_envelope

        wire_body = build_two_layer_error_envelope(AdCPAuthRequiredError("no credentials"))
        captured = {}

        class _FakeResponse:
            status_code = 401
            headers = {"content-type": "application/json"}
            text = '{"errors": [{"code": "AUTH_REQUIRED"}]}'

            def json(self):
                return wire_body

        class _FakeClient:
            def __init__(self, *, base_url, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def post(self, url, *, json, headers):
                captured["headers"] = headers
                return _FakeResponse()

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        with self._make_env_with_e2e_config() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "x"}, Transport.E2E_REST, identity=None)

        assert "x-adcp-auth" not in captured["headers"]
        assert result.is_error
        result.assert_wire_error("AUTH_REQUIRED")

    def test_e2e_rest_delivery_requires_e2e_config(self):
        from tests.harness.address_table import ToolAddress
        from tests.harness.client import _deliver_e2e_rest

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            address = ToolAddress(Transport.E2E_REST, name="/api/v1/products", method="post")
            with pytest.raises(RuntimeError, match="e2e_config"):
                _deliver_e2e_rest(env, address, {"url": "/api/v1/products", "body": {}}, None)


class TestClientE2eMcpDelivery:
    """Real e2e MCP DELIVER (salesagent-wu78/SB-3b) — mocks the fastmcp
    ``Client``/HTTP transport layer for unit-level coverage. Genuine
    e2e-with-a-real-server verification happens in ``tests/e2e/`` via
    ``./run_all_tests.sh`` (no Docker stack available in this worktree)."""

    class _FakeToolResult:
        def __init__(self, structured_content: dict) -> None:
            self.structured_content = structured_content

    class _FakeMcpClient:
        """Records the transport it was built with and the tool_name/arguments
        of the last call_tool — enough to assert DELIVER built the real HTTP
        transport with the right URL/headers and dispatched the right tool."""

        instances: list = []

        def __init__(self, transport=None):
            self.transport = transport
            self.calls: list[tuple[str, dict]] = []
            type(self).instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return TestClientE2eMcpDelivery._FakeToolResult({"products": [{"product_id": "prod_e2e"}]})

    def test_e2e_mcp_dispatch_builds_real_http_transport_and_succeeds(self, monkeypatch):
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        self._FakeMcpClient.instances = []
        monkeypatch.setattr("fastmcp.Client", self._FakeMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))
        client = AdCPTestClient(env)

        result = client.call("get_products", {"brief": "video ads"}, Transport.E2E_MCP, identity=None)

        assert result.is_success, result.error
        assert result.envelope["transport"] == "mcp"
        assert result.wire_response == {"products": [{"product_id": "prod_e2e"}]}

        fake_client = self._FakeMcpClient.instances[0]
        assert fake_client.transport.url == "http://e2e-host:9000/mcp/"
        assert fake_client.transport.headers == {}  # identity=None -> no auth headers
        assert fake_client.calls == [("get_products", {"brief": "video ads"})]

    def test_e2e_mcp_dispatch_sends_auth_headers_from_identity(self, monkeypatch):
        from tests.factories.principal import PrincipalFactory
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        self._FakeMcpClient.instances = []
        monkeypatch.setattr("fastmcp.Client", self._FakeMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))
        client = AdCPTestClient(env)
        identity = PrincipalFactory.make_identity(
            principal_id="p1", tenant_id="t1", protocol="mcp", auth_token="tok_123"
        )

        client.call("get_products", {"brief": "video ads"}, Transport.E2E_MCP, identity=identity)

        fake_client = self._FakeMcpClient.instances[0]
        assert fake_client.transport.headers["x-adcp-auth"] == "tok_123"

    def test_e2e_mcp_dispatch_requires_e2e_config(self):
        """Missing env.e2e_config is a genuine precondition failure (mirrors
        RestE2EDispatcher.dispatch's own check) — caught by
        AdCPTestClient.call()'s generic except and surfaced as an error
        TransportResult, same as any other DELIVER-raised Exception (NOT the
        NotImplementedError special-case that re-raises loudly)."""
        from tests.harness._base import BaseTestEnv

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "x"}, Transport.E2E_MCP, identity=None)

        assert result.is_error
        assert "e2e_config" in str(result.error)

    def test_e2e_mcp_dispatch_tool_error_unwraps_to_adcp_error(self, monkeypatch):
        from fastmcp.exceptions import ToolError

        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        class _FailingMcpClient(self._FakeMcpClient):
            async def call_tool(self, name, arguments):
                raise ToolError(
                    '{"errors": [{"code": "AUTH_REQUIRED", "message": "no auth", "recovery": "correctable"}], '
                    '"adcp_error": {"code": "AUTH_REQUIRED", "message": "no auth", "recovery": "correctable"}}'
                )

        monkeypatch.setattr("fastmcp.Client", _FailingMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))
        client = AdCPTestClient(env)

        result = client.call("get_products", {"brief": "x"}, Transport.E2E_MCP, identity=None)

        assert result.is_error
        result.assert_wire_error("AUTH_REQUIRED")


class TestClientE2eA2aDelivery:
    """``_deliver_e2e_a2a`` (salesagent-tisr / SB-3c) — real JSON-RPC
    ``message/send`` HTTP delivery, HTTP layer mocked (unit-level; genuine
    e2e-with-real-server verification happens in tests/e2e/ against a live
    Docker stack, per this task's scope)."""

    @staticmethod
    def _rpc_success_body(*, task_id: str = "task_abc123", state: str = "TASK_STATE_COMPLETED", artifact_data: dict):
        return {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "task": {
                    "id": task_id,
                    "contextId": "ctx_1",
                    "status": {"state": state},
                    "artifacts": [{"artifactId": "art-1", "parts": [{"data": artifact_data}]}],
                }
            },
        }

    def test_success_posts_jsonrpc_and_returns_stripped_artifact_data(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        artifact_data = {"products": [{"product_id": "prod_001"}], "message": "ok", "success": True}
        rpc_response = self._rpc_success_body(artifact_data=artifact_data)

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("get_products", {"brief": "video ads"}, Transport.E2E_A2A)

        assert result.is_success, result.error
        assert result.payload == {"products": [{"product_id": "prod_001"}]}
        assert result.wire_response == artifact_data  # unstripped — captured before pop
        assert env._last_wire_response == artifact_data

        # POST went to the real A2A JSON-RPC endpoint with a well-formed envelope.
        call_args = mock_post.call_args
        assert call_args.args[0] == "/a2a"
        rpc_body = call_args.kwargs["json"]
        assert rpc_body["jsonrpc"] == "2.0"
        assert rpc_body["method"] == "SendMessage"
        skill_part = rpc_body["params"]["message"]["parts"][0]["data"]
        assert skill_part["skill"] == "get_products"
        assert skill_part["parameters"] == {"brief": "video ads"}

    def test_identity_maps_to_auth_and_tenant_headers(self):
        from unittest.mock import MagicMock, patch

        from tests.factories.principal import PrincipalFactory
        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        identity = PrincipalFactory.make_identity(
            principal_id="p1", tenant_id="t1", protocol="a2a", auth_token="tok_123"
        )
        rpc_response = self._rpc_success_body(artifact_data={"message": "ok", "success": True})

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("get_products", {"brief": "x"}, Transport.E2E_A2A, identity=identity)

        assert result.is_success, result.error
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["x-adcp-auth"] == "tok_123"
        assert headers["x-adcp-tenant"] == identity.tenant["subdomain"]

    def test_unauthenticated_dispatch_sends_no_auth_header(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        rpc_response = self._rpc_success_body(artifact_data={"message": "ok", "success": True})

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                client.call("get_products", {"brief": "x"}, Transport.E2E_A2A, identity=None)

        headers = mock_post.call_args.kwargs["headers"]
        assert "x-adcp-auth" not in headers
        assert "x-adcp-tenant" not in headers

    def test_task_state_failed_reconstructs_wire_error(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        envelope = {"adcp_error": {"code": "PRODUCT_NOT_FOUND", "message": "no such product", "recovery": "retry"}}
        rpc_response = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "task": {
                    "id": "task_fail",
                    "status": {"state": "TASK_STATE_FAILED"},
                    "artifacts": [{"artifactId": "art-1", "parts": [{"data": envelope}]}],
                }
            },
        }

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("get_products", {"brief": "x"}, Transport.E2E_A2A)

        assert result.is_error
        assert result.wire_error_envelope == envelope

    def test_task_state_submitted_synthesizes_submitted_wire(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        rpc_response = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "task": {
                    "id": "task_submitted_1",
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [],
                }
            },
        }

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("create_media_buy", {"buyer_ref": "x"}, Transport.E2E_A2A)

        assert result.is_success, result.error
        assert result.payload == {"status": "submitted", "task_id": "task_submitted_1"}

    def test_missing_e2e_config_raises(self):
        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "x"}, Transport.E2E_A2A)

        assert result.is_error
        assert "e2e_config" in str(result.error)


class TestA2AE2EDispatcher:
    """``A2AE2EDispatcher`` (salesagent-tisr / SB-3c) — the legacy
    ``env.call_via(Transport.E2E_A2A, ...)`` entry point, delegating to
    ``AdCPTestClient``/``_deliver_e2e_a2a`` under the hood."""

    def test_dispatch_requires_a_tool_name(self):
        from tests.harness.dispatchers import A2AE2EDispatcher
        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            with pytest.raises(NotImplementedError, match="tool_name"):
                A2AE2EDispatcher().dispatch(env, brief="video ads")

    def test_dispatch_with_tool_name_delegates_to_client(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.dispatchers import A2AE2EDispatcher
        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        rpc_response = TestClientE2eA2aDelivery._rpc_success_body(
            artifact_data={"products": [], "message": "ok", "success": True}
        )

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = A2AE2EDispatcher().dispatch(env, tool_name="get_products", brief="video ads")

        assert result.is_success, result.error
        skill_part = mock_post.call_args.kwargs["json"]["params"]["message"]["parts"][0]["data"]
        assert skill_part["skill"] == "get_products"
        assert skill_part["parameters"] == {"brief": "video ads"}


class TestMcpE2EDispatcherDelegation:
    """``McpE2EDispatcher`` (``tests/harness/dispatchers.py``) is the legacy
    ``env.call_via(Transport.E2E_MCP, **kwargs)`` entry point — it must
    delegate to ``AdCPTestClient`` rather than reimplement ADDRESS/WRAP/
    DELIVER/UNWRAP a second time."""

    def test_requires_tool_name(self):
        from tests.harness._base import BaseTestEnv
        from tests.harness.dispatchers import McpE2EDispatcher

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            with pytest.raises(TypeError, match="tool_name"):
                McpE2EDispatcher().dispatch(env, identity=None)

    def test_delegates_to_client_with_flattened_req(self, monkeypatch):
        from tests.harness._base import BaseTestEnv
        from tests.harness.dispatchers import McpE2EDispatcher
        from tests.harness.transport import E2EConfig

        TestClientE2eMcpDelivery._FakeMcpClient.instances = []
        monkeypatch.setattr("fastmcp.Client", TestClientE2eMcpDelivery._FakeMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        class _FakeReq:
            def model_dump(self, **kwargs):
                return {"brief": "video ads"}

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))

        result = McpE2EDispatcher().dispatch(env, tool_name="get_products", req=_FakeReq(), identity=None)

        assert result.is_success, result.error
        fake_client = TestClientE2eMcpDelivery._FakeMcpClient.instances[0]
        assert fake_client.calls == [("get_products", {"brief": "video ads"})]


@pytest.mark.integration
@pytest.mark.requires_db
class TestClientTransportParity:
    """The client's core promise: the SAME call() drives MCP/A2A/REST identically
    (CLAUDE.md Pattern #7 "Transport parity") — using tests.harness.product.ProductEnv
    (the IntegrationEnv/real-DB variant) so REST dispatch (which needs
    get_rest_client()) is available alongside MCP/A2A."""

    def test_get_products_identical_across_all_three_transports(self, integration_db):
        from tests.factories import PricingOptionFactory, PrincipalFactory, ProductFactory, TenantFactory
        from tests.harness.product import ProductEnv

        with ProductEnv(tenant_id="client-parity", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="client-parity", subdomain="client-parity")
            PrincipalFactory(tenant=tenant, principal_id="p1")
            product = ProductFactory(tenant=tenant, product_id="prod_parity")
            PricingOptionFactory(product=product)

            client = AdCPTestClient(env)

            mcp_result = client.call("get_products", {"brief": "video ads"}, Transport.MCP)
            a2a_result = client.call("get_products", {"brief": "video ads"}, Transport.A2A)
            rest_result = client.call("get_products", {"brief": "video ads"}, Transport.REST)

        assert mcp_result.is_success, mcp_result.error
        assert a2a_result.is_success, a2a_result.error
        assert rest_result.is_success, rest_result.error

        mcp_ids = {p["product_id"] for p in mcp_result.payload["products"]}
        a2a_ids = {p["product_id"] for p in a2a_result.payload["products"]}
        rest_ids = {p["product_id"] for p in rest_result.payload["products"]}

        assert mcp_ids == {"prod_parity"}
        assert mcp_ids == a2a_ids == rest_ids

    def test_rest_unauthenticated_dispatch_surfaces_auth_required(self, integration_db):
        with BareIntegrationEnv(tenant_id="client-parity-noauth", principal_id="p1") as env:
            client = AdCPTestClient(env)
            result = client.call("list_accounts", {}, Transport.REST, identity=None)

        assert result.is_error
        result.assert_wire_error("AUTH_REQUIRED")

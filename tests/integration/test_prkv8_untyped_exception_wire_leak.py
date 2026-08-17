"""Reproduction for salesagent-prkv.8: raw exception text reaching the buyer-facing wire.

An untyped exception raised inside a dispatched skill's business logic is
normalized to a wire-safe ``AdCPError`` by ``normalize_to_adcp_error()``
(src/core/exceptions.py) — the single chokepoint used by all three transport
boundaries (A2A, MCP, REST). Its final fallback branch,
``return AdCPError(str(exc) or type(exc).__name__)``, uses the raw exception's
``str()`` as the buyer-facing ``message`` verbatim: whatever internal detail
the exception happened to carry (a DB DSN, a stack fragment, an upstream
response body) lands directly in the wire's two-layer error envelope.

AdCP 3.1.1 transport-errors.mdx, Security Considerations, is a MUST-NOT list
covering exactly this: credentials, SQL, hostnames, stack traces, upstream
responses must never reach the buyer.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# A distinctive, plainly-internal-looking payload — if this string appears
# anywhere in the wire envelope, the raw exception leaked.
_SECRET_MARKER = "postgres://admin:s3cr3t-prkv8@10.0.0.5:5432/prod_shadow"

# Patched at the module the skill actually calls through (A2A's get_products_raw,
# MCP's get_products, and REST's api_v1 handler all call `_get_products_impl`
# unqualified/via module reference from src.core.tools.products) so every
# transport really dispatches a real skill whose business logic raises for real.
_PATCH_TARGET = "src.core.tools.products._get_products_impl"


def _assert_no_leak(envelope: dict, label: str) -> None:
    assert envelope is not None, f"no wire envelope captured on {label}"
    rendered = str(envelope)
    assert _SECRET_MARKER not in rendered, f"raw exception text leaked into the {label} wire envelope: {rendered!r}"


@pytest.mark.parametrize("transport", [Transport.A2A, Transport.MCP], ids=lambda t: t.value)
class TestUntypedExceptionDoesNotLeakOntoWireA2AAndMcp:
    """An untyped exception inside a dispatched skill must not put its own
    text on the buyer-facing wire, on A2A or MCP."""

    def test_no_raw_exception_text_in_wire_envelope(self, integration_db, transport):
        with ProductEnv(tenant_id="prkv8-leak", principal_id="prkv8-principal") as env:
            tenant = TenantFactory(tenant_id="prkv8-leak", subdomain="prkv8-leak")
            PrincipalFactory(tenant=tenant, principal_id="prkv8-principal")

            with patch(_PATCH_TARGET, new=AsyncMock(side_effect=RuntimeError(_SECRET_MARKER))):
                result = env.call_via(transport, brief="video ads")

            assert result.is_error, f"expected an error result on {transport.value}, got {result.payload!r}"
            _assert_no_leak(result.wire_error_envelope, transport.value)


class TestUntypedExceptionDoesNotLeakOntoWireRest:
    """Same obligation on REST — exercised with a raw client because REST's
    untyped-exception path is caught only by the ``@app.exception_handler(Exception)``
    catch-all, which Starlette routes through ``ServerErrorMiddleware`` (the
    outermost middleware layer, wrapping *everything* so unhandled exceptions
    anywhere in the stack still get a response). Real deployments see the
    handler's response over the wire same as any other error; a plain
    ``TestClient(app)`` additionally re-raises the exception into the test
    afterward by design ("allows test clients to optionally raise the error
    within the test case" — starlette.middleware.errors.ServerErrorMiddleware),
    which would make this specific path untestable through the shared harness's
    default client. ``raise_server_exceptions=False`` observes the real response
    instead, same as an actual buyer would receive."""

    def test_no_raw_exception_text_in_wire_envelope(self, integration_db):
        from starlette.testclient import TestClient

        with ProductEnv(tenant_id="prkv8-leak-rest", principal_id="prkv8-principal-rest") as env:
            tenant = TenantFactory(tenant_id="prkv8-leak-rest", subdomain="prkv8-leak-rest")
            PrincipalFactory(tenant=tenant, principal_id="prkv8-principal-rest")

            rest_identity = env.identity_for(Transport.REST)
            base_client = env.get_rest_client()  # installs the auth dep overrides on the shared app
            env._configure_rest_auth(rest_identity)

            with patch(_PATCH_TARGET, new=AsyncMock(side_effect=RuntimeError(_SECRET_MARKER))):
                with TestClient(base_client.app, raise_server_exceptions=False) as raw_client:
                    response = raw_client.post(env.REST_ENDPOINT, json={"brief": "video ads"})

            assert response.status_code >= 400, f"expected an error response, got {response.status_code}"
            _assert_no_leak(response.json(), "rest")


class TestInternalErrorForDoesNotLeakOntoWire:
    """Separate obligation: adcp_a2a_server.py's ``_internal_error_for()`` (the
    ticket's literal WHERE) builds the top-level A2A JSON-RPC ``error.message``
    field independently of ``normalize_to_adcp_error()`` — it is reachable only
    from NON-skill A2A boundary failures (``on_message_send``'s outer
    fallthrough, and the push-notification-config JSON-RPC methods), never from
    a dispatched skill's own per-invocation catch (that goes through
    ``_build_failed_skill_result`` instead, covered by the class above).
    Mutation-verified: this test does NOT fail if only
    ``normalize_to_adcp_error()``'s fix is reverted — it exercises the OTHER
    mechanism specifically, by raising during identity resolution, which runs
    inside ``on_message_send``'s outer try/except, before skill dispatch."""

    def test_no_raw_exception_text_in_internal_error_message(self, integration_db):
        import asyncio

        from a2a.server.routes.common import ServerCallContext
        from a2a.types import SendMessageRequest

        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler, InternalError
        from tests.utils.a2a_helpers import create_a2a_message_with_skill

        handler = AdCPRequestHandler()
        # get_products is in DISCOVERY_SKILLS (no auth required), so on_message_send
        # still calls _resolve_a2a_identity(None, require_valid_token=False, ...)
        # even with no auth token presented -- the simplest way to raise inside the
        # outer try/except, before the skill-dispatch loop's own catch takes over.
        handler._get_auth_token = lambda *a, **kw: None  # type: ignore[assignment]
        handler._resolve_a2a_identity = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError(_SECRET_MARKER))  # type: ignore[assignment]

        message = create_a2a_message_with_skill(skill_name="get_products", parameters={"brief": "video ads"})
        params = SendMessageRequest(message=message)

        with pytest.raises(InternalError) as exc_info:
            asyncio.run(handler.on_message_send(params, ServerCallContext()))

        raised = exc_info.value
        assert _SECRET_MARKER not in str(raised.message), (
            f"raw exception text leaked into InternalError.message: {raised.message!r}"
        )
        # The safe two-layer envelope must still be present in data= -- this fix
        # must not regress the one channel that WAS already safe.
        envelope = raised.data
        _assert_no_leak(envelope, "a2a InternalError.data")
        assert envelope.get("adcp_error", {}).get("code"), f"expected a code in InternalError.data: {envelope!r}"

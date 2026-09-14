"""Tests for REST API /api/v1/* endpoints (all handlers except get_products).

The route-level forwarding tests this file used to carry (scalar forwarding, account
coercion before enrichment, path fields binding from the URL) graded transport behaviour
and are deleted: BDD grades those on the wire across every transport (BR-UC-002 for the
create scalars, BR-UC-004 for the delivery account, local-context-echo for context).
What remains is the one auth-refusal shape no scenario sends on REST alone.
"""

from starlette.testclient import TestClient

from src.app import app
from tests.factories.request import CreateMediaBuyRequestFactory
from tests.helpers import assert_envelope_shape

client = TestClient(app)


# ---------------------------------------------------------------------------
# Auth-required endpoints
# ---------------------------------------------------------------------------


class TestCreateMediaBuyEndpoint:
    """Verify POST /api/v1/media-buys endpoint."""

    def test_requires_auth(self):
        """create_media_buy rejects a request that presents no credential.

        The body must be VALID. FastAPI validates it while resolving the handler's
        parameters, which is strictly before ``invoke_tool`` sees the credential, so a
        body the DTO rejects answers INVALID_REQUEST and never reaches the auth check
        this asserts. The previous ``{"packages": []}`` was such a body: it graded
        request validation while claiming to grade authentication.
        """
        body = CreateMediaBuyRequestFactory.build().model_dump(mode="json", exclude_none=True)

        response = client.post("/api/v1/media-buys", json=body)

        assert response.status_code == 401, response.text
        assert_envelope_shape(response.json(), "AUTH_MISSING", recovery="correctable")

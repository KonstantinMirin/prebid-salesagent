"""Tests for REST API /api/v1/* endpoints (all handlers except get_products).

Validates that each REST transport endpoint:
- Route exists (not 404)
- Returns 200 with valid mock data
- Auth-optional endpoints work without auth

"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ContextObject, PushNotificationConfig, ReportingWebhook
from starlette.testclient import TestClient

from src.app import app
from src.core.resolved_identity import ResolvedIdentity
from tests.helpers import assert_envelope_shape

client = TestClient(app)

_MOCK_IDENTITY = ResolvedIdentity(
    principal_id="test-principal",
    tenant_id="default",
    tenant={"tenant_id": "default"},
    auth_token="test-token",
    protocol="rest",
)


# ---------------------------------------------------------------------------
# Discovery endpoints (auth-optional)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Auth-required endpoints
# ---------------------------------------------------------------------------


class TestCreateMediaBuyEndpoint:
    """Verify POST /api/v1/media-buys endpoint."""

    def test_requires_auth(self):
        """create_media_buy requires authentication."""
        response = client.post(
            "/api/v1/media-buys",
            json={"packages": []},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Runtime scalar-forwarding oracles (#1417)
#
# The body-completeness guard proves each REST scalar is DECLARED on the *_raw
# wrapper signature; it does NOT prove the route actually forwards the request
# value. These TestClient tests patch the *_raw wrapper and assert the sentinel
# value the buyer sent reaches the wrapper — one test per non-echoed scalar.
# ---------------------------------------------------------------------------

# field -> (wire value, value the route must forward to the raw wrapper).
# Object params are coerced to SDK types at the route (#1417), so the
# forwarded value is the typed model, not the wire dict; ext stays a raw dict.
_CREATE_WEBHOOK_WIRE = {
    "url": "https://example.com/hook",
    "authentication": {"schemes": ["Bearer"], "credentials": "e9kw-credential-value-of-32-chars"},
    "reporting_frequency": "daily",
}
_CREATE_PNC_WIRE = {"url": "https://example.com/push"}
_CREATE_CONTEXT_WIRE = {"conversation_id": "conv-e9kw"}
_CREATE_FORWARDED_SCALARS = {
    "reporting_webhook": (_CREATE_WEBHOOK_WIRE, ReportingWebhook.model_validate(_CREATE_WEBHOOK_WIRE)),
    "push_notification_config": (_CREATE_PNC_WIRE, PushNotificationConfig.model_validate(_CREATE_PNC_WIRE)),
    "context": (_CREATE_CONTEXT_WIRE, ContextObject.model_validate(_CREATE_CONTEXT_WIRE)),
    "ext": ({"e9kw_marker": "create-value"}, {"e9kw_marker": "create-value"}),
}

_UPDATE_FORWARDED_SCALARS = {
    "pacing": "even",
    "daily_budget": 1234.5,
}


class TestCreateMediaBuyScalarForwarding:
    """Each non-echoed create scalar reaches create_media_buy_raw at runtime."""

    @pytest.mark.parametrize(
        ("field", "wire_value", "expected"),
        [(f, w, e) for f, (w, e) in _CREATE_FORWARDED_SCALARS.items()],
        ids=list(_CREATE_FORWARDED_SCALARS),
    )
    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.tools.media_buy_create.create_media_buy_raw", new_callable=AsyncMock)
    def test_scalar_forwards_to_raw(self, mock_raw, mock_resolve, field, wire_value, expected):
        mock_raw.return_value = MagicMock(model_dump=lambda **kw: {})
        body = {
            "packages": [],
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-02-01T00:00:00Z",
            field: wire_value,
        }
        response = client.post("/api/v1/media-buys", json=body, headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200, response.text
        assert mock_raw.call_args.kwargs[field] == expected, (
            f"REST create route did not forward {field!r} to create_media_buy_raw"
        )


class TestUpdateMediaBuyScalarForwarding:
    """Each non-echoed update scalar reaches update_media_buy_raw at runtime."""

    @pytest.mark.parametrize(
        ("field", "value"), list(_UPDATE_FORWARDED_SCALARS.items()), ids=list(_UPDATE_FORWARDED_SCALARS)
    )
    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.tools.media_buy_update.update_media_buy_raw")
    def test_scalar_forwards_to_raw(self, mock_raw, mock_resolve, field, value):
        mock_raw.return_value = MagicMock(model_dump=lambda **kw: {})
        body = {field: value}
        response = client.put("/api/v1/media-buys/mb_e9kw", json=body, headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200, response.text
        assert mock_raw.call_args.kwargs[field] == value, (
            f"REST update route did not forward {field!r} to update_media_buy_raw"
        )


class TestGetMediaBuyDeliveryEndpoint:
    """Verify POST /api/v1/media-buys/delivery endpoint."""

    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.transport_helpers.enrich_identity_with_account")
    @patch("src.core.tools.media_buy_delivery.get_media_buy_delivery_raw")
    def test_account_is_coerced_before_enriching_identity(self, mock_impl, mock_enrich, mock_resolve):
        enriched_identity = _MOCK_IDENTITY.model_copy(update={"account_id": "acct-1"})
        mock_enrich.return_value = enriched_identity
        mock_impl.return_value = MagicMock(model_dump=lambda **kw: {"media_buys": []})

        response = client.post(
            "/api/v1/media-buys/delivery",
            json={
                "media_buy_ids": ["mb1"],
                "account": {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False},
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        expected_account = LibraryAccountReference.model_validate(
            {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
        )
        mock_enrich.assert_called_once_with(_MOCK_IDENTITY, expected_account)
        assert mock_impl.call_args.kwargs["identity"] is enriched_identity

    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.transport_helpers.enrich_identity_with_account")
    @patch("src.core.tools.media_buy_delivery.get_media_buy_delivery_raw")
    def test_malformed_account_returns_validation_error(self, mock_impl, mock_enrich, mock_resolve):
        response = client.post(
            "/api/v1/media-buys/delivery",
            json={"media_buy_ids": ["mb1"], "account": {}},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "VALIDATION_ERROR", recovery="correctable")
        mock_enrich.assert_not_called()
        mock_impl.assert_not_called()


# ---------------------------------------------------------------------------
# The value-vs-structural split at the REST schema boundary (src/app.py)
#
# REST bodies are DERIVED from their DTO, so FastAPI enforces the DTO's enums and
# ranges BEFORE any AdCP code runs. MCP and A2A hand the same value to the shared
# adcp_validation_boundary instead. If every FastAPI rejection were INVALID_REQUEST,
# the same payload would carry two different codes depending on transport.
#
# The split is graded cross-transport by BR-UC-010 @T-UC-010-ext-d-invalid-value;
# these pin the two halves directly, on one route, so a regression names the rule
# instead of surfacing as a single failing Gherkin scenario.
# ---------------------------------------------------------------------------


@patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
class TestRestSchemaRejectionCodes:
    """A VALUE violation is VALIDATION_ERROR; a STRUCTURAL one is INVALID_REQUEST.

    Identity is patched only so the auth-optional dependency does not reach a database;
    every assertion here is about the schema boundary, which rejects before the tool runs.
    """

    def test_out_of_enum_value_is_validation_error(self, _mock_resolve):
        """protocols:["marketing"] is outside the closed enum -- a bad VALUE.

        The pinned enums/error-code.json defines VALIDATION_ERROR as "Request contains
        invalid field values"; get-adcp-capabilities-request.json
        /properties/protocols/items/enum is the closed vocabulary being violated.
        """
        response = client.post("/api/v1/capabilities", json={"protocols": ["marketing"]})

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "VALIDATION_ERROR", recovery="correctable")

    def test_wrong_type_is_invalid_request(self, _mock_resolve):
        """protocols as a bare string is not a bad value, it is the wrong SHAPE.

        INVALID_REQUEST is "Request is malformed ... or violates schema constraints",
        which is where a type-coercion failure belongs.
        """
        response = client.post("/api/v1/capabilities", json={"protocols": "media-buy"})

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "INVALID_REQUEST", recovery="correctable")

    def test_unknown_field_is_invalid_request(self, _mock_resolve):
        """An undeclared key is structural, not a bad value (Pattern #7 extra="forbid")."""
        response = client.post("/api/v1/capabilities", json={"not_a_declared_field": 1})

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "INVALID_REQUEST", recovery="correctable")

"""MCP Tool Roundtrip Tests with Minimal Parameters.

These tests verify that MCP tools work correctly when called with only required parameters,
catching issues like the datetime.combine() bug where optional fields defaulted to None
and caused errors.

Focus: Test parameter-to-schema mapping, not business logic.
"""

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from tests.helpers.credentials import credential_headers


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.requires_db
class TestMCPToolRoundtripMinimal:
    """Test MCP tools with minimal parameters to catch schema construction bugs.

    Uses the mcp_server fixture which starts a real MCP server with test database.
    """

    @pytest.fixture
    async def mcp_client(self, mcp_server, sample_tenant, sample_principal, sample_account, sample_products):
        """Create MCP client for testing with test data."""
        # Use the mcp_server fixture which provides port and manages lifecycle.
        # The SELLER travels with the credential: these calls reach the server on
        # localhost, so no host maps to a tenant and the resolver has no tenant to verify
        # the token inside -- every tool answered AUTH_INVALID without it.
        headers = credential_headers(
            token=sample_principal["access_token"],
            tenant=sample_tenant["tenant_id"],
        )
        transport = StreamableHttpTransport(url=f"http://localhost:{mcp_server.port}/mcp/", headers=headers)
        client = Client(transport=transport)

        async with client:
            yield client

    # SEVEN ROUNDTRIP CASES STOOD HERE AND ARE DELETED. Each drove one tool over MCP with
    # its required fields and checked the answer; BDD already grades every one of them,
    # over THREE wire transports instead of this one, against the stack's own server.
    #
    # Measured from run innet_200926_1903 (tests/bdd/conftest.py:4867 parametrizes
    # scenarios over a2a/mcp/rest — `impl` was dropped by #1417 and BDD asserts wire
    # conformance only), counting nodeids graded over [mcp]:
    #
    #     create_media_buy 132   update_media_buy 75   sync_creatives 76
    #     list_creatives    48   get_products     11
    #
    # The error case went the same way: test_get_media_buy_delivery_invalid_date_range
    # asserted assert_envelope_shape(..., "VALIDATION_ERROR", recovery="correctable") for
    # start_date after end_date, and
    # test_delivery_date_range_partition__partition carries exactly that obligation —
    # `start_after_end` -> `error "VALIDATION_ERROR" with suggestion` — on mcp, a2a AND
    # rest, alongside the boundary twin test_delivery_date_range_boundary__boundary_point.
    #
    # What could not be deleted is below: the MCP PRESENTATION property, which is about
    # this transport's rendering rather than any tool's contract, so no wire-conformance
    # scenario grades it.

    async def test_get_products_content_is_summary_not_json(self, mcp_client):
        """MCP text content is a human-readable summary, not a JSON dump of structured_content."""
        import json

        result = await mcp_client.call_tool("get_products", {"brand": {"domain": "testbrand.com"}})
        text = result.content[0].text
        assert text != json.dumps(result.structured_content)
        assert not text.strip().startswith("{")

    def test_update_media_buy_request_construction(self):
        """Test that UpdateMediaBuyRequest can be constructed with minimal params."""
        from src.core.schemas import UpdateMediaBuyRequest

        # Test with only media_buy_id (required via oneOf constraint)
        req = UpdateMediaBuyRequest(
            account={"account_id": "acct_test"}, idempotency_key="test-idem-key-0001", media_buy_id="test_buy_123"
        )

        assert req.media_buy_id == "test_buy_123"
        assert req.paused is None  # adcp 2.12.0+: replaced 'active' with 'paused'

        # No internal field survives on this DTO. ``today`` used to be asserted here, both
        # for its presence and for its absence from model_dump(); it is deleted, so the
        # question the assertions answered no longer has a subject. The rule that keeps it
        # that way is graded in
        assert not [f for f, info in req.model_fields.items() if info.exclude]

    def test_all_request_schemas_have_optional_or_default_fields(self):
        """Every request schema constructs from its REQUIRED fields alone.

        "Minimal" means the spec's own /required set, not the empty set. UpdateMediaBuyRequest
        used to appear here with only media_buy_id, which worked while account and
        idempotency_key were wrongly overridden to optional; AdCP 3.1.1 lists both in
        /required, so a request without them is not minimal, it is invalid. The obligation
        that still matters -- no schema demands MORE than the spec does -- is unchanged.
        """
        from src.core import schemas

        # Test schemas that should work with minimal params
        test_cases = [
            (schemas.GetProductsRequest, {"brand": {"domain": "testbrand.com"}}),
            (
                schemas.UpdateMediaBuyRequest,
                {
                    "media_buy_id": "test",
                    "account": {"account_id": "acct_test"},
                    "idempotency_key": "test-idem-key-0001",
                },
            ),
            (schemas.GetMediaBuyDeliveryRequest, {}),
            (schemas.ListCreativesRequest, {}),
        ]

        for schema_class, minimal_params in test_cases:
            try:
                instance = schema_class(**minimal_params)
                assert instance is not None, f"{schema_class.__name__} failed to construct with minimal params"
            except Exception as e:
                pytest.fail(f"{schema_class.__name__} raised {type(e).__name__}: {e}")


@pytest.mark.unit  # Changed from integration - these don't require server
class TestParameterToSchemaMapping:
    """Test that tool parameters map correctly to schema fields."""

    def test_update_media_buy_parameter_mapping(self):
        """Test that update_media_buy parameters map to UpdateMediaBuyRequest fields."""
        from src.core.schemas import UpdateMediaBuyRequest

        # Simulate what the tool does when constructing the request
        # Note: Tool should convert float to Budget object before passing
        # Updated: Only use valid AdCP fields (start_time/end_time, not flight_start_date/flight_end_date)
        tool_params = {
            "media_buy_id": "test_buy_123",
            "paused": True,  # adcp 2.12.0+: replaced 'active' with 'paused'
        }

        # Create request with valid fields only
        req = UpdateMediaBuyRequest(
            account={"account_id": "acct_test"}, idempotency_key="test-idem-key-0001", **tool_params
        )

        # Valid fields should be set
        assert req.media_buy_id == "test_buy_123"
        assert req.paused is True  # adcp 2.12.0+: paused=True means pause

        # start_time/end_time should be None since not provided
        assert req.start_time is None
        assert req.end_time is None

        # No top-level budget to assert: AdCP 3.1.1 does not define one on
        # update-media-buy-request.json (budget is package-level), so the field was removed
        # rather than left as a convenience. `packages` is where a budget update lives.
        assert req.packages is None

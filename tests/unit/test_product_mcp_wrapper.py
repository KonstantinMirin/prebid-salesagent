"""Unit tests for get_products MCP transport wrapper.

Covers ValidationError/ValueError handling and ToolResult construction.

DUPLICATION, recorded not resolved: every test here has a counterpart in
tests/unit/test_products_transport_wrappers.py::TestMcpGetProductsWrapper, which grades
the same wrapper plus the A2A and REST ones. Merging them is a separate change -- the two
files were edited together here only because both graded the wrapper's now-deleted
ValueError translation.
Version compat lives at the transport handler level (parity with A2A).

These test the transport boundary layer, NOT business logic.
_get_products_impl is always mocked.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from src.core.tool_error_logging import with_error_logging
from tests.helpers import assert_envelope_shape


class TestGetProductsMCPWrapper:
    """Test the MCP get_products() wrapper function."""

    @pytest.mark.asyncio
    async def test_mcp_boundary_answers_invalid_request_for_a_validation_error(self):
        """A pydantic rejection reaches the buyer as INVALID_REQUEST naming the field.

        Graded at ``with_error_logging`` -- the MCP boundary FastMCP registers -- not at
        the wrapper. The wrapper used to catch ValueError and re-raise AdCPValidationError;
        since a pydantic ValidationError IS a ValueError, that handler answered a bare
        VALIDATION_ERROR for a schema rejection and discarded the ``field`` and ``issues``
        the boundary derives. The wrapper translates nothing now, so the assertion is on
        the envelope the boundary emits.
        """
        envelope = await self._envelope_for(
            ValidationError.from_exception_data(
                title="GetProductsRequest",
                line_errors=[
                    {
                        "type": "missing",
                        "loc": ("brief",),
                        "msg": "Field required",
                        "input": {},
                    }
                ],
            )
        )

        assert_envelope_shape(envelope, "INVALID_REQUEST", recovery="correctable")
        assert envelope["adcp_error"]["field"] == "brief"

    @pytest.mark.asyncio
    async def test_mcp_boundary_answers_validation_error_for_a_plain_value_error(self):
        """A plain ValueError stays VALIDATION_ERROR -- the distinction the wrapper erased.

        error-code.json: INVALID_REQUEST is "violates schema constraints", VALIDATION_ERROR
        is "invalid field values or violates business rules BEYOND schema validation". A
        ValueError our own logic raises is the latter.
        """
        envelope = await self._envelope_for(ValueError("invalid filter combination"))

        assert_envelope_shape(envelope, "VALIDATION_ERROR", recovery="correctable")

    @staticmethod
    async def _envelope_for(side_effect: Exception) -> dict:
        """The wire envelope MCP emits when request construction raises ``side_effect``.

        ``str(ToolError)`` IS the MCP wire text -- FastMCP serializes a raised ToolError as
        ``CallToolResult(content=[TextContent(text=str(error))])`` -- so this parses the
        bytes a buyer parses.
        """
        with patch("src.core.tools.products.create_get_products_request", side_effect=side_effect):
            from src.core.tools.products import get_products

            with pytest.raises(ToolError) as exc_info:
                await with_error_logging(get_products)(brief="test", ctx=None)

        return json.loads(str(exc_info.value))

    @pytest.mark.asyncio
    async def test_returns_tool_result_with_structured_content(self):
        """Happy path: returns ToolResult with structured_content from response."""
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "metadata": {}}
        mock_response.__str__ = lambda self: "0 products found"

        mock_req = MagicMock()

        with (
            patch("src.core.tools.products.create_get_products_request", return_value=mock_req),
            patch(
                "src.core.tools.products._get_products_impl",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            from src.core.tools.products import get_products

            result = await get_products(brief="video ads", ctx=None)

        assert result.structured_content == {"products": [], "metadata": {}}
        assert "0 products found" in str(result.content)

    @pytest.mark.asyncio
    async def test_wrapper_does_not_apply_version_compat(self):
        """Wrapper does NOT apply version compat — that's the transport handler's job."""
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": []}
        mock_response.__str__ = lambda self: "result"

        mock_req = MagicMock()

        with (
            patch("src.core.tools.products.create_get_products_request", return_value=mock_req),
            patch(
                "src.core.tools.products._get_products_impl",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
            patch("src.core.version_compat.apply_version_compat") as mock_compat,
        ):
            from src.core.tools.products import get_products

            await get_products(brief="test", ctx=None)

        mock_compat.assert_not_called()

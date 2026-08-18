"""Starlette middleware for REST AdCP backward-compatibility normalization.

Normalizes deprecated field names in JSON request bodies for /api/v1/
endpoints before FastAPI's Pydantic model parsing strips unknown fields.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.request_compat import normalize_request_params
from src.core.version_compat import set_wire_request

logger = logging.getLogger(__name__)

# Map URL path suffixes to tool names for normalization.
_PATH_TO_TOOL: dict[str, str] = {
    "/products": "get_products",
    "/media-buys": "create_media_buy",
    "/creatives/sync": "sync_creatives",
}


# Every /api/v1 write route's tool identity. Wider than _PATH_TO_TOOL on purpose:
# this drives the acceptance seam (which must cover all of them), not deprecated-
# field normalization (which must not change coverage silently).
_CARRIER_PATHS: dict[str, str] = {
    "/products": "get_products",
    "/creative-formats": "list_creative_formats",
    "/authorized-properties": "list_authorized_properties",
    "/media-buys": "create_media_buy",
    "/media-buys/delivery": "get_media_buy_delivery",
    "/creatives/sync": "sync_creatives",
    "/creatives": "list_creatives",
    "/performance-index": "update_performance_index",
    "/accounts": "list_accounts",
    "/accounts/sync": "sync_accounts",
}


class RestCompatMiddleware(BaseHTTPMiddleware):
    """Normalize deprecated fields in REST JSON bodies.

    Intercepts POST requests to /api/v1/* endpoints, normalizes the JSON
    body using the shared normalizer, and replaces the request body so
    Pydantic models see current-version field names.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in ("POST", "PUT", "PATCH") or not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        # Two different resolutions, deliberately (Lane A / S4).
        #
        # `carrier_tool` covers EVERY /api/v1 write route, because the acceptance
        # seam must see the wire dict for all of them — that is the whole point of
        # S4. `_PATH_TO_TOOL` keeps its ORIGINAL, narrower coverage: it drives
        # deprecated-field NORMALIZATION, and widening that silently would change
        # translation behaviour for routes nobody reviewed for it.
        carrier_tool = self._resolve_carrier_tool(request.url.path)
        if not carrier_tool:
            return await call_next(request)

        # Determine tool name from URL path (normalization only)
        tool_name = self._resolve_tool_name(request.url.path)

        content_type = request.headers.get("content-type", "")
        if "json" not in content_type:
            return await call_next(request)

        try:
            raw_body = await request.body()
            if not raw_body:
                return await call_next(request)

            # The wire bytes AS SENT — the idempotency payload-hash input.
            # Stashed before any rewrite (bytes are immutable, so downstream
            # mutation cannot corrupt the capture); read by api_v1's
            # _raw_json_body dependency.
            request.state.raw_wire_payload = raw_body

            body_dict: dict[str, Any] = json.loads(raw_body)
            carrier_params: dict[str, Any] = body_dict
            if tool_name:
                result = normalize_request_params(tool_name, body_dict)
                carrier_params = result.params
            else:
                result = None

            if result is not None and result.translations_applied:
                # Replace the request body with normalized JSON
                normalized_bytes = json.dumps(result.params).encode("utf-8")
                request._body = normalized_bytes  # noqa: SLF001

            # Publish the NORMALIZED body to the acceptance seam (Lane A / S4).
            # One site covers every /api/v1 route. Without it, the REST Body model
            # decides which fields exist at all — the route can only forward what
            # the Body declared — so acceptance was decided per-Body, which is the
            # per-transport disease the seam replaces. The Body models keep their
            # declared fields for coercion and documentation; they no longer decide
            # what the seller ACCEPTS.
            #
            # `result.params`, NOT `raw_body`: the raw bytes are the idempotency
            # payload-hash input and are deliberately pre-normalization.
            with set_wire_request(carrier_tool, carrier_params):
                return await call_next(request)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Let FastAPI handle malformed JSON

        return await call_next(request)

    @staticmethod
    def _resolve_tool_name(path: str) -> str | None:
        """Map URL path to tool name for normalization."""
        # Strip /api/v1 prefix
        suffix = path.removeprefix("/api/v1")
        return _PATH_TO_TOOL.get(suffix)

    @staticmethod
    def _resolve_carrier_tool(path: str) -> str | None:
        """The tool a /api/v1 write route addresses, for the acceptance seam.

        Handles the one path-parameter route (`PUT /media-buys/{id}`) that a plain
        suffix lookup cannot: without it, update_media_buy — the tool whose dropped
        `canceled` this lane exists to fix — would be the single route the seam
        never saw.
        """
        suffix = path[len("/api/v1") :] if path.startswith("/api/v1") else path
        suffix = suffix.rstrip("/") or "/"
        if suffix in _CARRIER_PATHS:
            return _CARRIER_PATHS[suffix]
        parts = [p for p in suffix.split("/") if p]
        if len(parts) == 2 and parts[0] == "media-buys":
            return "update_media_buy"
        return None

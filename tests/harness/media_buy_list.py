"""MediaBuyListEnv — integration test environment for _get_media_buys_impl.

Minimal harness — list operation has no adapter calls, just DB queries.
No patches needed (pure DB read).

Requires: integration_db fixture + existing media buys in the DB.

"""

from __future__ import annotations

from typing import Any

from src.core.schemas._base import GetMediaBuysRequest, GetMediaBuysResponse
from tests.harness._base import IntegrationEnv
from tests.harness.transport import DeliverResult


class MediaBuyListEnv(IntegrationEnv):
    """Integration test environment for _get_media_buys_impl.

    No patches — list is read-only, no external service calls.
    """

    # Dispatch declaration: the base owns call_mcp/call_a2a (Lane B, B1).
    RESPONSE_MODEL = GetMediaBuysResponse

    EXTERNAL_PATCHES: dict[str, str] = {}
    REST_ENDPOINT = "/api/v1/media-buys/query"

    def _configure_mocks(self) -> None:
        """No mocks needed for read-only list operation."""

    def call_impl(self, **kwargs: Any) -> GetMediaBuysResponse:
        """Call _get_media_buys_impl with real DB."""
        from src.core.tools.media_buy_list import _get_media_buys_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        include_snapshot = kwargs.pop("include_snapshot", False)

        req = kwargs.pop("req", None)
        if req is None:
            req = GetMediaBuysRequest(**kwargs)

        return _get_media_buys_impl(req=req, identity=identity, include_snapshot=include_snapshot)

    def deliver_a2a(self, **kwargs: Any) -> DeliverResult:
        """Dispatch get_media_buys through the real A2A handler pipeline.

        FIXME(#1928): JUSTIFIED OVERRIDE — does NOT declare A2A_SKILL, so it does
        not take the base's client-core delegation. The core's UNWRAP parses into
        the PINNED GetMediaBuysResponse, whose media_buys items REQUIRE
        `confirmed_at` and `revision` (get-media-buys-response.json); production
        emits neither, so every response fails that parse. Parsing here with the
        LOCAL model keeps this env working while the gap stays attributable — a
        production schema defect, not a dispatch defect, and deliberately not
        hidden by loosening the core's parse. Delete this override and its
        `_KNOWN_DELIVER_OVERRIDES` entry when #1928 lands.
        """
        return self._run_a2a_handler("get_media_buys", GetMediaBuysResponse, **kwargs)

    def deliver_mcp(self, **kwargs: Any) -> DeliverResult:
        """Call get_media_buys through the legacy MCP wrapper.

        JUSTIFIED OVERRIDE: uses ``_run_mcp_wrapper`` (mock Context -> async
        wrapper), a different mechanism from ``_run_mcp_client``, which observes
        no structured_content — hence wire_response=None.
        """
        from src.core.tools.media_buy_list import get_media_buys

        return DeliverResult(
            payload=self._run_mcp_wrapper(get_media_buys, GetMediaBuysResponse, **kwargs),
            wire_response=None,
        )

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Convert kwargs to GetMediaBuysBody shape for REST POST."""
        body: dict[str, Any] = {}
        for key in ("media_buy_ids", "status_filter", "account_id", "context"):
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]
        if kwargs.get("include_snapshot"):
            body["include_snapshot"] = True
        return body

    def parse_rest_response(self, data: dict[str, Any]) -> GetMediaBuysResponse:
        """Parse REST response JSON."""
        return GetMediaBuysResponse(**data)

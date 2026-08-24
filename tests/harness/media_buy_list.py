"""MediaBuyListEnv — integration test environment for _get_media_buys_impl.

Minimal harness — list operation has no adapter calls, just DB queries.
No patches needed (pure DB read).

Requires: integration_db fixture + existing media buys in the DB.

beads: salesagent-4n0
"""

from __future__ import annotations

from typing import Any

from src.core.schemas._base import GetMediaBuysRequest, GetMediaBuysResponse
from tests.harness._base import IntegrationEnv


class MediaBuyListEnv(IntegrationEnv):
    """Integration test environment for _get_media_buys_impl.

    No patches — list is read-only, no external service calls.
    """

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

    def call_a2a(self, **kwargs: Any) -> Any:
        """Dispatch get_media_buys through the REAL A2A pipeline (on_message_send).

        The production A2A path is ``_handle_get_media_buys_skill`` —
        ``get_media_buys_raw`` has ZERO production callers, so dispatching to it
        here gave false confidence (#1417): a boundary fix on the raw
        wrapper made 'A2A' tests green while the real skill handler still
        leaked bare ValidationErrors.
        """
        return self._run_a2a_handler("get_media_buys", GetMediaBuysResponse, **kwargs)

    def call_mcp(self, **kwargs: Any) -> Any:
        """Dispatch get_media_buys through the REAL FastMCP pipeline.

        Was ``_run_mcp_wrapper``, whose own docstring deprecates it: it calls the
        tool wrapper directly and so bypasses the FastMCP middleware chain and
        TypeAdapter validation. The consequence on the ERROR path is that a raised
        ``AdCPError`` propagated raw out of ``asyncio.run(wrapper_fn(...))`` and
        was never serialized into a ``ToolError``, so ``McpDispatcher`` captured
        ``wire_error_envelope=None``. Every mcp error assertion in UC-019 was
        therefore graded against a reconstructed exception rather than the wire,
        and could not have failed if production stopped emitting an envelope at
        all (salesagent-3dawm.18/.19).

        ``_run_mcp_client`` is the same path the conformant envs already use
        (list_accounts, list_creative_formats, sync_accounts,
        list_authorized_properties).
        """
        return self._run_mcp_client("get_media_buys", GetMediaBuysResponse, **kwargs)

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Convert kwargs to GetMediaBuysBody shape for REST POST."""
        body: dict[str, Any] = {}
        # "account" belongs here: the steps dispatch account={"account_id": ...}
        # (the AdCP 3.x reference shape), so a list naming only the legacy
        # "account_id" silently dropped the filter on REST -- the request then
        # SUCCEEDED where MCP and A2A correctly rejected it with
        # UNSUPPORTED_FEATURE. Invisible until UC-019 regained REST
        # parametrization (salesagent-ma52s); the same shape of harness gap as
        # CreativeFormatsEnv.build_rest_body in salesagent-3dawm.16.
        for key in ("media_buy_ids", "status_filter", "account", "account_id", "context"):
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]
        if kwargs.get("include_snapshot"):
            body["include_snapshot"] = True
        return body

    def parse_rest_response(self, data: dict[str, Any]) -> GetMediaBuysResponse:
        """Parse REST response JSON."""
        return GetMediaBuysResponse(**data)

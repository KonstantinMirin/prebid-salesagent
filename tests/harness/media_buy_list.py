"""MediaBuyListEnv — integration test environment for _get_media_buys_impl.

Minimal harness — list operation has no adapter calls, just DB queries.
No patches needed (pure DB read).

Requires: integration_db fixture + existing media buys in the DB.

The dispatch itself lives in ``MediaBuyListDispatchMixin`` so a composite env can
reuse it verbatim: ``MediaBuyCreateListEnv`` (tests/harness/media_buy_create_list.py)
needs the SAME get_media_buys dispatch alongside the create path, and a second copy
of these four bodies would be a DRY violation — the next fix to the list dispatch
would land in one copy only.

GH #1335, GH #1900
"""

from __future__ import annotations

from typing import Any

from src.core.schemas._base import GetMediaBuysRequest, GetMediaBuysResponse
from tests.harness._base import IntegrationEnv


class MediaBuyListDispatchMixin:
    """get_media_buys dispatch across impl/A2A/MCP/REST.

    Deliberately named ``_call_list_*`` rather than ``call_*``: the composite env
    inherits create dispatch from ``MediaBuyCreateEnv`` under those public names
    and routes to these explicitly, so neither tool's dispatch can shadow the
    other's by MRO accident.
    """

    def _call_list_impl(self, **kwargs: Any) -> GetMediaBuysResponse:
        """Call _get_media_buys_impl with real DB."""
        from src.core.tools.media_buy_list import _get_media_buys_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        include_snapshot = kwargs.pop("include_snapshot", False)

        req = kwargs.pop("req", None)
        if req is None:
            req = GetMediaBuysRequest(**kwargs)

        return _get_media_buys_impl(req=req, identity=identity, include_snapshot=include_snapshot)

    def _call_list_a2a(self, **kwargs: Any) -> Any:
        """Dispatch get_media_buys through the REAL A2A pipeline (on_message_send).

        The production A2A path is ``_handle_get_media_buys_skill`` —
        ``get_media_buys_raw`` has ZERO production callers, so dispatching to it
        here gave false confidence (#1417): a boundary fix on the raw
        wrapper made 'A2A' tests green while the real skill handler still
        leaked bare ValidationErrors.
        """
        return self._run_a2a_handler("get_media_buys", GetMediaBuysResponse, **kwargs)

    def _call_list_mcp(self, **kwargs: Any) -> Any:
        """Dispatch get_media_buys through the REAL FastMCP ``Client`` pipeline.

        Was ``_run_mcp_wrapper``, which is deprecated precisely because it hand-builds
        a mock Context and calls the wrapper directly: it skips the middleware,
        TypeAdapter validation and the token→DB→identity auth chain, and — the reason
        it had to change here — it stashes NO ``wire_response``. Every MCP assertion
        on this tool therefore graded a re-serialized typed payload rather than the
        bytes a buyer receives, which is exactly the blind spot GH #1900 slipped
        through. ``_run_mcp_client`` stashes ``structured_content``, the real MCP wire.

        The ERROR path was blind for the same reason: a raised ``AdCPSalesAgentError``
        propagated raw out of ``asyncio.run(wrapper_fn(...))`` and was never serialized
        into a ``ToolError``, so ``McpDispatcher`` captured ``wire_error_envelope=None``
        and every MCP error assertion in UC-019 graded a reconstructed exception that
        could not have failed if production stopped emitting an envelope at all
        (salesagent-3dawm.18/.19).
        """
        return self._run_mcp_client("get_media_buys", GetMediaBuysResponse, **kwargs)


class MediaBuyListEnv(MediaBuyListDispatchMixin, IntegrationEnv):
    """Integration test environment for _get_media_buys_impl.

    No patches — list is read-only, no external service calls.
    """

    EXTERNAL_PATCHES: dict[str, str] = {}
    # REST_ENDPOINT is declared because the route now EXISTS:
    # `@router.post("/media-buys/query")` in src/routes/api_v1.py. It did not when
    # the surrounding mixin was extracted, and declaring an endpoint for a path
    # absent from src/ was the defect that removal fixed — a REST parametrization
    # would have failed as if production were broken rather than as if the route
    # were missing. With the route landed, the opposite failure is the live one:
    # dropping the endpoint silently deletes the REST arm of every UC-019 scenario,
    # which then grades nothing instead of failing. The sibling composite env still
    # refuses this dispatch (`media_buy_create_list.py::build_rest_body`) — it is
    # keyed on its own create/list discriminator and is not touched here.
    REST_ENDPOINT = "/api/v1/media-buys/query"

    def _configure_mocks(self) -> None:
        """No mocks needed for read-only list operation."""

    def call_impl(self, **kwargs: Any) -> GetMediaBuysResponse:
        return self._call_list_impl(**kwargs)

    def call_a2a(self, **kwargs: Any) -> Any:
        return self._call_list_a2a(**kwargs)

    def call_mcp(self, **kwargs: Any) -> Any:
        return self._call_list_mcp(**kwargs)

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

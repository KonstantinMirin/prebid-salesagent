"""REST API v1 endpoints.

REST transport for AdCP tools, proving the 3-transport pattern
(MCP + A2A + REST). Each endpoint calls the shared _impl/_raw function
and applies version compat at the boundary.
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.resolved_identity import ResolvedIdentity

from adcp.types import BrandReference
from adcp.types.generated_poc.media_buy.get_media_buy_delivery_request import (
    AttributionWindow,
    ReportingDimensions,
)
from fastapi import APIRouter, Depends, Request

from src.core.auth_context import require_auth, resolve_auth
from src.core.schema_helpers import (
    coerce_creative_filters,
    select_request_fields,
    to_account_reference,
    to_brand_reference,
    to_context_object,
    to_push_notification_config,
    to_reporting_webhook,
)
from src.core.schemas import ListCreativesRequest as ListCreativesRequestDTO
from src.core.schemas import SalesAgentBaseModel
from src.core.tools import accounts as accounts_module
from src.core.tools import capabilities as capabilities_module
from src.core.tools import creative_formats as creative_formats_module
from src.core.tools import media_buy_create as media_buy_create_module
from src.core.tools import media_buy_delivery as media_buy_delivery_module
from src.core.tools import media_buy_list as media_buy_list_module
from src.core.tools import media_buy_update as media_buy_update_module
from src.core.tools import performance as performance_module
from src.core.tools import products as products_module
from src.core.tools import properties as properties_module
from src.core.tools.creatives import listing as creatives_listing_module
from src.core.tools.creatives import sync_wrappers as creatives_sync_module
from src.core.validation_helpers import adcp_validation_boundary
from src.core.version_compat import apply_version_compat
from src.routes._derived_body import derived_body_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


# Note: ToolError handling lives entirely in the global ``@app.exception_handler``
# in src/app.py — REST routes never catch ToolError or import the MCP-boundary
# type (AdCPToolError). The wire-code -> HTTP status table moved to
# src/core/tool_error_logging.py alongside handle_tool_error.


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
#
# These REST request models extend SalesAgentBaseModel so they inherit the
# Pattern #7 environment-based extra-field policy (extra="forbid" in dev/CI,
# extra="ignore" in prod) — the same validation the MCP/A2A request models get.


class GetProductsBody(SalesAgentBaseModel):
    brief: str = ""
    # dict BrandReference or string domain/URL shorthand (#1324)
    brand: dict[str, Any] | str | None = None
    filters: dict[str, Any] | None = None
    # create_get_products_request accepts these; REST passed only 3 of its 5 kwargs, so a
    # buyer's property_list filter and context echo were dropped on this transport alone
    # (salesagent-e8wt.1 scan row 9).
    property_list: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class CreateMediaBuyBody(SalesAgentBaseModel):
    # dict BrandReference or string domain/URL shorthand (#1324); coerced to
    # BrandReference at the boundary via to_brand_reference.
    brand: BrandReference | dict[str, Any] | str | None = None  # adcp 3.6.0: BrandReference with domain field
    packages: list[dict[str, Any]] = []  # Validated downstream by CreateMediaBuyRequest
    start_time: str | None = None
    end_time: str | None = None
    po_number: str | None = None
    account: dict[str, Any] | None = None  # AccountReference; resolved at the transport boundary
    reporting_webhook: dict[str, Any] | None = None
    push_notification_config: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    ext: dict[str, Any] | None = None
    idempotency_key: str | None = None
    # AdCP 3.1.1 create-in-paused-state; accepted, validated, and forwarded to the
    # raw wrapper on all transports for wire parity, but pause-on-create is not yet
    # honored by _impl — see #1619.
    paused: bool | None = None
    adcp_version: str = "1.0.0"


class UpdateMediaBuyBody(SalesAgentBaseModel):
    paused: bool | None = None
    flight_start_date: str | None = None
    flight_end_date: str | None = None
    budget: float | None = None
    currency: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    # Fields update_media_buy_raw plumbs through to UpdateMediaBuyRequest. Raw dicts
    # are coerced downstream (Pattern #7 extra policy inherited from SalesAgentBaseModel).
    # NOTE: top-level targeting_overlay/creatives are intentionally omitted — the raw
    # wrapper accepts them in its signature but drops them before _build_update_request,
    # so declaring them here would be a silent no-op (see #1417).
    packages: list[dict[str, Any]] | None = None
    pacing: str | None = None
    daily_budget: float | None = None
    push_notification_config: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    reporting_webhook: dict[str, Any] | None = None
    ext: dict[str, Any] | None = None
    idempotency_key: str | None = None
    # The buyer's expected-current optimistic-concurrency token. Declared because the
    # pinned update-media-buy-request.json defines it ("Expected current revision for
    # optimistic concurrency ... Obtain from get_media_buys or the most recent
    # create/update response") and this model is extra="forbid" — so omitting it did
    # not make the field optional over REST, it made a spec-legal request a hard
    # INVALID_REQUEST. A buyer that read the token off a create/update response and
    # handed it back, exactly as the spec instructs, was rejected for doing so.
    #
    # The seller does not yet ACT on it — the stale-token CONFLICT check is a separate,
    # still-xfailed gap (BR-RULE-215 partitions). Accepting it is transport parity, not
    # a claim that concurrency is enforced.
    revision: int | None = None
    adcp_version: str = "1.0.0"


class GetMediaBuyDeliveryBody(SalesAgentBaseModel):
    media_buy_ids: list[str] | None = None
    status_filter: Any = None
    start_date: str | None = None
    end_date: str | None = None
    reporting_dimensions: ReportingDimensions | None = None
    attribution_window: AttributionWindow | None = None
    include_package_daily_breakdown: bool | None = None
    account: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class GetMediaBuysBody(SalesAgentBaseModel):
    # `Any`, not `list[str] | None`, and for the same reason status_filter is Any
    # in GetMediaBuyDeliveryBody: a typed field here makes FASTAPI reject a bad
    # value before any AdCP code runs, which returns INVALID_REQUEST, while MCP
    # and A2A reject the identical request inside adcp_validation_boundary and
    # return VALIDATION_ERROR. Same request, two different codes depending on
    # transport -- exactly what "each transport returns the same typed response"
    # forbids. Keeping it permissive defers validation to the ONE shared boundary
    # in _build_get_media_buys_request, so all three answer alike. Surfaced by
    # test_request_validation_failed[rest] once UC-019 regained REST coverage.
    media_buy_ids: Any = None
    status_filter: Any = None
    include_snapshot: bool | None = None
    account: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class SyncCreativesBody(SalesAgentBaseModel):
    creatives: list[dict[str, Any]] = []
    assignments: dict[str, Any] | None = None
    creative_ids: list[str] | None = None
    delete_missing: bool = False
    dry_run: bool = False
    validation_mode: str = "strict"
    push_notification_config: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    account: dict[str, Any] | None = None  # AccountReference; resolved at the transport boundary
    adcp_version: str = "1.0.0"


# DERIVED, not hand-written: DTO fields INTERSECT list_creatives_raw's parameters, plus the
# version envelope the route negotiates on. The 21-field class this replaces carried 15
# parameters AdCP 3.1.1 does not define (media_buy_id, status, format, page, limit,
# sort_by, sort_order, ...) and was MISSING `sort`, so a spec-shaped REST payload sorted on
# MCP and A2A and silently did not here. REST and MCP now advertise the same set by
# construction, and e2e_rest -- real HTTP against this route, with no schema of its own --
# inherits it.
ListCreativesBody = derived_body_model(
    "ListCreativesBody",
    ListCreativesRequestDTO,
    creatives_listing_module.list_creatives_raw,
)


class UpdatePerformanceIndexBody(SalesAgentBaseModel):
    media_buy_id: str
    performance_data: list[dict[str, Any]] = []
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class ListCreativeFormatsBody(SalesAgentBaseModel):
    format_ids: list[dict[str, Any]] | None = None
    name_search: str | None = None
    is_responsive: bool | None = None
    asset_types: list[str] | None = None
    min_width: int | None = None
    max_width: int | None = None
    min_height: int | None = None
    max_height: int | None = None
    wcag_level: str | None = None
    disclosure_positions: list[str] | None = None
    disclosure_persistence: list[str] | None = None
    output_format_ids: list[dict[str, Any]] | None = None
    input_format_ids: list[dict[str, Any]] | None = None
    # Application-level context is echoed back per the AdCP envelope; MCP and A2A both
    # carry it, so omitting it here dropped the echo on REST alone (salesagent-e8wt.1).
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class ListAuthorizedPropertiesBody(SalesAgentBaseModel):
    property_tags: list[str] | None = None
    publisher_domains: list[str] | None = None
    # Application-level context is echoed back per the AdCP envelope; MCP and A2A both
    # carry it, so omitting it here dropped the echo on REST alone (salesagent-e8wt.1).
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class ListAccountsBody(SalesAgentBaseModel):
    account: dict[str, Any] | None = None
    status: str | None = None
    sandbox: bool | None = None
    idempotency_key: str | None = None
    ext: dict[str, Any] | None = None
    pagination: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class SyncAccountsBody(SalesAgentBaseModel):
    accounts: list[dict[str, Any]] = []
    delete_missing: bool = False
    dry_run: bool = False
    # Client-generated at-most-once key. sync-accounts-request.json 3.1.1 lists it in
    # /required; omitting it from this body made a spec-conformant buyer's request fail
    # here as an extra input while MCP minted its own and A2A dropped it (salesagent-e8wt.1).
    idempotency_key: str | None = None
    push_notification_config: dict[str, Any] | None = None
    ext: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    adcp_version: str = "1.0.0"


class GetAdcpCapabilitiesBody(SalesAgentBaseModel):
    # Named for the TOOL, not the route: the transport-parity guard derives the body
    # class from the tool name (get_adcp_capabilities -> GetAdcpCapabilitiesBody), so
    # the old GetCapabilitiesBody spelling meant this tool never entered the
    # comparison at all -- which is why the dropped `ext` stayed invisible.
    protocols: list[str] | None = None
    context: dict[str, Any] | None = None
    adcp_version: str | None = None
    adcp_major_version: int | None = None
    ext: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Discovery endpoints (auth-optional)
# ---------------------------------------------------------------------------


@router.post("/products")
async def get_products(body: GetProductsBody, identity: ResolvedIdentity | None = resolve_auth):
    """Get available products matching the brief (auth-optional discovery skill).

    ``ToolError`` propagates to the global handler in ``src.app`` for envelope
    translation; no defensive catch needed here.
    """
    from src.core.schemas import GetProductsRequest

    with adcp_validation_boundary(context="get_products request"):
        # Selected off the BUILDER's signature, not GetProductsRequest's fields: the model
        # declares 13 fields this builder does not take (catalog, refine, pagination, ...),
        # and handing it those would turn a key that is ignored today into a TypeError --
        # a 500 on a spec-conformant payload (salesagent-prkv.5 Lane D / F3).
        req = products_module.create_get_products_request(
            **select_request_fields(
                GetProductsRequest,
                body,
                inspect.signature(products_module.create_get_products_request).parameters,
            )
        )
    response = await products_module._get_products_impl(req, identity)
    result = response.model_dump(mode="json")
    return apply_version_compat("get_products", result, body.adcp_version)


@router.get("/capabilities")
async def get_capabilities(identity: ResolvedIdentity | None = resolve_auth):
    """Get AdCP capabilities (auth-optional discovery skill)."""
    response = await capabilities_module.get_adcp_capabilities_raw(identity=identity)
    return response.model_dump(mode="json")


@router.post("/capabilities")
async def post_capabilities(body: GetAdcpCapabilitiesBody, identity: ResolvedIdentity | None = resolve_auth):
    """Get AdCP capabilities with request parameters (auth-optional discovery skill).

    Additive alongside the parameterless GET route above (owner decision
    2026-07-24): protocols filtering and context echo need a real request
    body, which a bare GET cannot carry — matches the POST+JSON-body
    convention every other route in this file follows.
    """
    from adcp.types import GetAdcpCapabilitiesRequest

    # Version pair forwarded explicitly -- see the A2A handler's note: the selector strips
    # the version-envelope fields by design, but this tool negotiates on them.
    response = await capabilities_module.get_adcp_capabilities_raw(
        **select_request_fields(GetAdcpCapabilitiesRequest, body),
        adcp_version=body.adcp_version,
        adcp_major_version=body.adcp_major_version,
        identity=identity,
    )
    return response.model_dump(mode="json")


@router.post("/creative-formats")
async def list_creative_formats(body: ListCreativeFormatsBody, identity: ResolvedIdentity | None = resolve_auth):
    """List available creative formats (auth-optional discovery skill)."""
    from src.core.schemas import ListCreativeFormatsRequest

    body_fields = body.model_dump(exclude={"adcp_version"}, exclude_none=True)
    with adcp_validation_boundary(context="list_creative_formats request"):
        req = ListCreativeFormatsRequest(**body_fields) if body_fields else None

    response = creative_formats_module.list_creative_formats_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


@router.post("/authorized-properties")
async def list_authorized_properties(
    body: ListAuthorizedPropertiesBody, identity: ResolvedIdentity | None = resolve_auth
):
    """List authorized properties (auth-optional discovery skill)."""
    from src.core.schemas import ListAuthorizedPropertiesRequest

    body_fields = body.model_dump(exclude={"adcp_version"}, exclude_none=True)
    with adcp_validation_boundary(context="list_authorized_properties request"):
        req = ListAuthorizedPropertiesRequest(**body_fields) if body_fields else None

    response = properties_module.list_authorized_properties_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Auth-required endpoints
# ---------------------------------------------------------------------------


async def _raw_json_body(request: Request) -> dict[str, Any]:
    """The HTTP body as sent on the wire — the idempotency payload-hash input.

    A dependency rather than a route ``request`` parameter, so route signatures
    stay Depends-only (the rest-depends-auth guard). Prefers the pre-rewrite
    bytes stashed by ``RestCompatMiddleware`` — when a deprecated-field
    translation fires, ``request.json()`` would observe the NORMALIZED body,
    not the bytes the buyer sent, and seller-side compat-table changes would
    flip honest retries into conflicts mid-TTL. Starlette caches the body, so
    the fallback read does not consume it before model parsing.
    """
    raw = getattr(request.state, "raw_wire_payload", None)
    if raw is not None:
        return json.loads(raw)
    return await request.json()


# Module-level singleton, matching require_auth (ruff B008 forbids Depends() in defaults).
raw_json_body = Depends(_raw_json_body)


@router.post("/media-buys")
async def create_media_buy(
    body: CreateMediaBuyBody,
    identity: ResolvedIdentity = require_auth,
    raw_wire_payload: dict[str, Any] = raw_json_body,
):
    """Create a new media buy (auth required).

    Per AdCP 3.1.1 (media-buy/package-request.json) per-package fields (budget, product_id,
    targeting_overlay, creatives, pacing, daily_budget) live inside packages[].
    """
    # Coerce wire dicts to the SDK types the raw wrapper declares, inside the
    # shared boundary so a malformed object rejects with the two-layer envelope
    # (top-level suggestion + field) instead of a raw-ValidationError leak.
    # The string/dict brand shorthand (#1324/#1537) is coerced here too, so an
    # invalid brand yields the same boundary-translated envelope.
    with adcp_validation_boundary(context="create_media_buy request"):
        account_ref = to_account_reference(body.account)
        brand_ref = to_brand_reference(body.brand)
        reporting_webhook = to_reporting_webhook(body.reporting_webhook)
        push_notification_config = to_push_notification_config(body.push_notification_config)
        context = to_context_object(body.context)
    response = await media_buy_create_module.create_media_buy_raw(
        brand=brand_ref,
        # packages stay wire dicts: CreateMediaBuyRequest validates them as the
        # request's packages[] field, preserving full-request error field paths.
        packages=body.packages,
        start_time=body.start_time,
        end_time=body.end_time,
        po_number=body.po_number,
        account=account_ref,
        reporting_webhook=reporting_webhook,
        push_notification_config=push_notification_config,
        context=context,
        ext=body.ext,
        idempotency_key=body.idempotency_key,
        paused=body.paused,
        identity=identity,
        raw_wire_payload=raw_wire_payload,
    )
    return response.model_dump(mode="json")


@router.put("/media-buys/{media_buy_id}")
async def update_media_buy(media_buy_id: str, body: UpdateMediaBuyBody, identity: ResolvedIdentity = require_auth):
    """Update an existing media buy (auth required)."""
    # Same context string as _build_update_request's boundary, so a malformed
    # object rejects with an identical message prefix wherever it validates.
    with adcp_validation_boundary(context="update_media_buy request"):
        push_notification_config = to_push_notification_config(body.push_notification_config)
        context = to_context_object(body.context)
        reporting_webhook = to_reporting_webhook(body.reporting_webhook)
    response = media_buy_update_module.update_media_buy_raw(
        media_buy_id=media_buy_id,
        paused=body.paused,
        flight_start_date=body.flight_start_date,
        flight_end_date=body.flight_end_date,
        budget=body.budget,
        currency=body.currency,
        start_time=body.start_time,
        end_time=body.end_time,
        pacing=body.pacing,
        daily_budget=body.daily_budget,
        # packages stay wire dicts: UpdateMediaBuyRequest validates them as the
        # request's packages[] field, preserving full-request error field paths.
        packages=body.packages,
        push_notification_config=push_notification_config,
        context=context,
        reporting_webhook=reporting_webhook,
        ext=body.ext,
        idempotency_key=body.idempotency_key,
        revision=body.revision,
        identity=identity,
    )
    return response.model_dump(mode="json")


@router.post("/media-buys/delivery")
async def get_media_buy_delivery(body: GetMediaBuyDeliveryBody, identity: ResolvedIdentity = require_auth):
    """Get delivery metrics for media buys (auth required)."""
    if body.account is not None:
        from src.core.transport_helpers import enrich_identity_with_account

        with adcp_validation_boundary(context="get_media_buy_delivery request"):
            account_ref = to_account_reference(body.account)
        enriched = enrich_identity_with_account(identity, account_ref)
        assert enriched is not None  # identity is non-None (from require_auth)
        identity = enriched

    response = media_buy_delivery_module.get_media_buy_delivery_raw(
        media_buy_ids=body.media_buy_ids,
        status_filter=body.status_filter,
        start_date=body.start_date,
        end_date=body.end_date,
        reporting_dimensions=body.reporting_dimensions,
        attribution_window=body.attribution_window,
        include_package_daily_breakdown=body.include_package_daily_breakdown,
        context=to_context_object(body.context),
        identity=identity,
    )
    return response.model_dump(mode="json")


@router.post("/media-buys/query")
async def get_media_buys(body: GetMediaBuysBody, identity: ResolvedIdentity = require_auth):
    """Query media buys with status and optional delivery snapshots (auth required).

    POST /media-buys is create_media_buy, so the query surface is a distinct
    path rather than a GET on the same one: the AdCP request carries filters and
    an account reference in a body, which a GET cannot express cleanly.

    This route existed for MCP and A2A but not REST, which silently dropped every
    UC-019 scenario from REST parametrization -- 61 scenarios graded on two
    transports while the suite read as covering three (salesagent-ma52s).
    """
    # NO enrich_identity_with_account here, deliberately -- unlike the
    # /media-buys/delivery sibling this route was modelled on. get_media_buys
    # REJECTS an account filter outright (AdCPCapabilityNotSupportedError ->
    # UNSUPPORTED_FEATURE), so resolving the account first is not just
    # unnecessary, it is WRONG: enriching raised ACCOUNT_NOT_FOUND for an
    # unresolvable account and pre-empted the UNSUPPORTED_FEATURE the buyer is
    # owed. The MCP wrapper does no enrichment either -- it forwards `account`
    # into the request and lets _impl reject it -- and REST must answer
    # identically. Both wrong shapes were caught by
    # test_account_filter_not_supported[rest] the moment REST parametrization
    # came back, which is the coverage this route exists to restore.
    account_ref = None
    if body.account is not None:
        with adcp_validation_boundary(context="get_media_buys request"):
            account_ref = to_account_reference(body.account)

    response = media_buy_list_module.get_media_buys_raw(
        media_buy_ids=body.media_buy_ids,
        status_filter=body.status_filter,
        include_snapshot=bool(body.include_snapshot),
        account=account_ref,
        context=to_context_object(body.context),
        identity=identity,
    )
    return response.model_dump(mode="json")


@router.post("/creatives/sync")
async def sync_creatives(body: SyncCreativesBody, identity: ResolvedIdentity = require_auth):
    """Sync creatives (auth required)."""
    # Coerce the raw account dict into an AccountReference so sync_creatives_raw
    # resolves it at the transport boundary (mirror create_media_buy / the sibling
    # handlers above — #1417).
    with adcp_validation_boundary(context="sync_creatives request"):
        account_ref = to_account_reference(body.account)
        push_notification_config = to_push_notification_config(body.push_notification_config)
        context = to_context_object(body.context)

    response = creatives_sync_module.sync_creatives_raw(
        # creatives stay wire dicts: _sync_creatives_impl validates each entry
        # individually (partial-success semantics with per-creative results).
        creatives=body.creatives,
        assignments=body.assignments,
        creative_ids=body.creative_ids,
        delete_missing=body.delete_missing,
        dry_run=body.dry_run,
        validation_mode=body.validation_mode,
        push_notification_config=push_notification_config,
        context=context,
        account=account_ref,
        identity=identity,
    )
    return response.model_dump(mode="json")


@router.post("/creatives")
async def list_creatives(body: ListCreativesBody, identity: ResolvedIdentity = require_auth):
    """List creatives (auth required)."""
    # Coerce the raw wire filters dict into a typed CreativeFilters here (#1493): the
    # merged list_creatives_raw expects a typed object (it calls .model_dump()), and
    # this is where an empty concept_ids etc. surfaces the VALIDATION_ERROR envelope.
    from src.core.schemas import ListCreativesRequest

    filters = coerce_creative_filters(body.filters)
    # Selected off "DTO fields INTERSECT the raw wrapper's parameters" rather than the
    # 18-name hand-list this replaces, which never forwarded `sort` -- so a spec-shaped
    # REST payload sorted on MCP and A2A and silently did not on REST. `filters` is set
    # after selection because it needs typed coercion (an empty concept_ids must surface
    # a VALIDATION_ERROR envelope, not reach the impl as a dict).
    selected = select_request_fields(
        ListCreativesRequest,
        body,
        inspect.signature(creatives_listing_module.list_creatives_raw).parameters,
    )
    selected["filters"] = filters
    response = creatives_listing_module.list_creatives_raw(**selected, identity=identity)
    return response.model_dump(mode="json")


@router.post("/performance-index")
async def update_performance_index(body: UpdatePerformanceIndexBody, identity: ResolvedIdentity = require_auth):
    """Update performance index for a media buy (auth required)."""
    response = performance_module.update_performance_index_raw(
        media_buy_id=body.media_buy_id,
        performance_data=body.performance_data,
        context=to_context_object(body.context),
        identity=identity,
    )
    return response.model_dump(mode="json")


@router.post("/accounts")
async def list_accounts(body: ListAccountsBody, identity: ResolvedIdentity = require_auth):
    """List accounts accessible to the authenticated agent (auth required)."""
    from src.core.schemas.account import ListAccountsRequest
    from src.core.tools.accounts import build_list_accounts_request

    with adcp_validation_boundary(context="list_accounts request"):
        req = build_list_accounts_request(**select_request_fields(ListAccountsRequest, body))
    response = accounts_module.list_accounts_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


@router.post("/accounts/sync")
async def sync_accounts(body: SyncAccountsBody, identity: ResolvedIdentity = require_auth):
    """Sync accounts by natural key (auth required)."""
    from src.core.schemas.account import SyncAccountsRequest
    from src.core.tools.accounts import build_sync_accounts_request

    with adcp_validation_boundary(context="sync_accounts request"):
        req = build_sync_accounts_request(**select_request_fields(SyncAccountsRequest, body))
    response = await accounts_module.sync_accounts_raw(req=req, identity=identity)
    return response.model_dump(mode="json")

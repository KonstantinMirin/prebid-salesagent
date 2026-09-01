"""REST API v1 endpoints.

REST transport for AdCP tools, proving the 3-transport pattern
(MCP + A2A + REST). Each endpoint calls the shared _impl/_raw function
and applies version compat at the boundary.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.resolved_identity import ResolvedIdentity

from adcp.types import GetAdcpCapabilitiesRequest
from adcp.types.generated_poc.protocol.get_adcp_capabilities_request import (
    GetAdcpCapabilitiesRequest as GetAdcpCapabilitiesRequestDTO,
)
from fastapi import APIRouter, Depends, Request

from src.core.auth_context import require_auth, resolve_auth
from src.core.schema_helpers import (
    accepted_kwargs,
    coerce_creative_filters,
    select_request_fields,
    to_account_reference,
    to_brand_reference,
    to_context_object,
    to_push_notification_config,
    to_reporting_webhook,
)
from src.core.schemas import CreateMediaBuyRequest as CreateMediaBuyRequestDTO
from src.core.schemas import GetMediaBuyDeliveryRequest as GetMediaBuyDeliveryRequestDTO
from src.core.schemas import GetMediaBuysRequest as GetMediaBuysRequestDTO
from src.core.schemas import GetProductsRequest as GetProductsRequestDTO
from src.core.schemas import ListAuthorizedPropertiesRequest as ListAuthorizedPropertiesRequestDTO
from src.core.schemas import ListCreativeFormatsRequest as ListCreativeFormatsRequestDTO
from src.core.schemas import ListCreativesRequest as ListCreativesRequestDTO
from src.core.schemas import UpdateMediaBuyRequest as UpdateMediaBuyRequestDTO
from src.core.schemas import UpdatePerformanceIndexRequest as UpdatePerformanceIndexRequestDTO
from src.core.schemas.account import ListAccountsRequest as ListAccountsRequestDTO
from src.core.schemas.account import SyncAccountsRequest as SyncAccountsRequestDTO
from src.core.schemas.creative import SyncCreativesRequest as LocalSyncCreativesRequest
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
from src.routes._derived_body import DerivedBodyEnvelope, derived_body_model

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


# DERIVED: GetProductsRequest fields INTERSECT create_get_products_request's parameters,
# plus the version envelope this route negotiates on. The hand-written class it replaces
# happened to name the same five fields, but it also defaulted `adcp_version` to "1.0.0" --
# a pre-3.0 version, so a REST buyer who simply omitted the field was served v2 compat
# fields (is_fixed/rate/price_guidance) that the pinned 3.1.1 schema does not define, while
# MCP and A2A (which read an ABSENT version as None) served the pinned shape. Deriving the
# envelope removes the guess: absent means absent on every transport.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class GetProductsBody(DerivedBodyEnvelope, GetProductsRequestDTO): ...

else:
    GetProductsBody = derived_body_model(
        "GetProductsBody", GetProductsRequestDTO, products_module.create_get_products_request
    )


if TYPE_CHECKING:
    # TYPE-CHECKER ONLY; the runtime class is the derivation in the else branch.
    class CreateMediaBuyBody(DerivedBodyEnvelope, CreateMediaBuyRequestDTO): ...

else:
    # DERIVED. It was hand-written to keep the DTO's annotations off the wire, and each
    # reason has since stopped holding:
    #
    #   packages / the error shape -- binding it was said to replace the full-request field
    #   path with a FastAPI location and the graded code with INVALID_REQUEST. The pointer
    #   is JSONPath-lite on every transport now (src/app.py), and INVALID_REQUEST is what a
    #   schema violation is supposed to answer, so both halves of that objection are gone.
    #
    #   start_time / end_time -- the DTO types them StartTiming / AwareDatetime while
    #   create_media_buy_raw declares ``str``. That is the WRAPPER having drifted from the
    #   DTO, not a reason for the body to hide the DTO's types; deriving makes the drift
    #   visible instead of preserving it.
    CreateMediaBuyBody = derived_body_model(
        "CreateMediaBuyBody",
        CreateMediaBuyRequestDTO,
        media_buy_create_module.create_media_buy_raw,
    )

if TYPE_CHECKING:
    # TYPE-CHECKER ONLY; the runtime class is the derivation in the else branch.
    class UpdateMediaBuyBody(DerivedBodyEnvelope, UpdateMediaBuyRequestDTO): ...

else:
    # DERIVED. Two things blocked it, and both are expressed here rather than by
    # hand-writing the whole model:
    #
    # ``flight_start_date`` / ``flight_end_date`` are flat DATE ALIASES that
    # _build_update_request folds into start_time/end_time. They are live REST inputs and
    # not UpdateMediaBuyRequest fields, so they come in as extra_fields -- the one thing a
    # derived body cannot know from the DTO.
    #
    # ``media_buy_id`` is the URL PATH segment. Deriving it would make a REST caller send
    # the same value twice, and since requiredness is preserved it would turn a spec-legal
    # request that puts the id only in the path into an INVALID_REQUEST.
    UpdateMediaBuyBody = derived_body_model(
        "UpdateMediaBuyBody",
        UpdateMediaBuyRequestDTO,
        media_buy_update_module.update_media_buy_raw,
        extra_fields={
            "flight_start_date": (str | None, None),
            "flight_end_date": (str | None, None),
        },
        path_fields=frozenset({"media_buy_id"}),
    )


if TYPE_CHECKING:
    # TYPE-CHECKER ONLY; the runtime class is the derivation in the else branch.
    class GetMediaBuyDeliveryBody(DerivedBodyEnvelope, GetMediaBuyDeliveryRequestDTO): ...

else:
    # DERIVED. It was hand-written to keep ``account`` a bare dict so FastAPI would not
    # reject ``{}`` before AdCP code ran -- because A2A answered VALIDATION_ERROR for the
    # same payload and typing it here would have moved REST alone. That comment named the
    # real fix itself: the missing-vs-value split belongs in adcp_error_for, where it moves
    # every transport at once. Keeping the body permissive worked around a divergence
    # instead of removing it, and a permissive REST body is exactly how a required field
    # goes unenforced on one transport.
    GetMediaBuyDeliveryBody = derived_body_model(
        "GetMediaBuyDeliveryBody",
        GetMediaBuyDeliveryRequestDTO,
        # The BUILDER -- the raw wrapper takes the built request now.
        media_buy_delivery_module._build_get_media_buy_delivery_request,
    )


if TYPE_CHECKING:
    # TYPE-CHECKER ONLY; the runtime class is the derivation in the else branch.
    class GetMediaBuysBody(DerivedBodyEnvelope, GetMediaBuysRequestDTO): ...

else:
    # DERIVED. It was hand-written to keep media_buy_ids/status_filter as ``Any``, because a
    # typed field made FastAPI reject a bad value with INVALID_REQUEST while mcp and a2a
    # rejected the same request inside adcp_validation_boundary with VALIDATION_ERROR --
    # one request, two codes, chosen by transport.
    #
    # That premise no longer holds: adcp_error_for maps a pydantic ValidationError to
    # AdCPInvalidRequestError, so the boundary answers INVALID_REQUEST too, and
    # src/app.py no longer special-cases which FastAPI rejections get which code. The
    # transports agree, so the body can carry the DTO's own types instead of hiding them.
    GetMediaBuysBody = derived_body_model(
        "GetMediaBuysBody",
        GetMediaBuysRequestDTO,
        media_buy_list_module._build_get_media_buys_request,
    )


# DERIVED, like ListCreativesBody below. Hand-written, this class declared
# `assignments: dict[str, Any]` -- the AdCP 2.5 map form ({creative_id: [package_ids]}),
# retired in 3.x, which the pinned 3.1 schema replaces with an ARRAY of
# {creative_id, package_id, weight?, placement_ids?}. MCP announced the 3.1 array (its shape
# comes from the DTO) while REST went on advertising the 2.5 map, so the SAME spec-conformant
# payload was accepted on one transport and rejected as INVALID_REQUEST on the other. That is
# the divergence deriving both from one artifact exists to make unrepresentable.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class SyncCreativesBody(DerivedBodyEnvelope, LocalSyncCreativesRequest): ...

else:
    SyncCreativesBody = derived_body_model(
        "SyncCreativesBody", LocalSyncCreativesRequest, creatives_sync_module.sync_creatives_raw
    )


# DERIVED, not hand-written: DTO fields INTERSECT list_creatives_raw's parameters, plus the
# version envelope the route negotiates on. The 21-field class this replaces carried 15
# parameters AdCP 3.1.1 does not define (media_buy_id, status, format, page, limit,
# sort_by, sort_order, ...) and was MISSING `sort`, so a spec-shaped REST payload sorted on
# MCP and A2A and silently did not here. REST and MCP now advertise the same set by
# construction, and e2e_rest -- real HTTP against this route, with no schema of its own --
# inherits it.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class ListCreativesBody(DerivedBodyEnvelope, ListCreativesRequestDTO): ...

else:
    ListCreativesBody = derived_body_model(
        "ListCreativesBody",
        ListCreativesRequestDTO,
        creatives_listing_module.list_creatives_raw,
    )


# DERIVED against the shared BUILDER, not the ``req=``-taking raw wrapper: the wrapper's only
# request parameter is the already-built model, so intersecting with it would yield the empty
# set. The builder is the seam every transport constructs through, so it is what defines the
# body's field set.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class UpdatePerformanceIndexBody(DerivedBodyEnvelope, UpdatePerformanceIndexRequestDTO): ...

else:
    UpdatePerformanceIndexBody = derived_body_model(
        "UpdatePerformanceIndexBody",
        UpdatePerformanceIndexRequestDTO,
        performance_module._build_update_performance_index_request,
    )


# DERIVED against the shared BUILDER, not the ``req=``-taking raw wrapper: the wrapper's
# only parameter is the already-built request, so intersecting with it would yield the empty
# set. ``build_list_creative_formats_request`` is the seam A2A already selects against
# (_handle_list_creative_formats_skill), so REST and A2A now compute their field sets from
# the same two artifacts.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class ListCreativeFormatsBody(DerivedBodyEnvelope, ListCreativeFormatsRequestDTO): ...

else:
    ListCreativeFormatsBody = derived_body_model(
        "ListCreativeFormatsBody",
        ListCreativeFormatsRequestDTO,
        creative_formats_module.build_list_creative_formats_request,
    )


# DERIVED against the builder, same as ListCreativeFormatsBody above. The builder was added
# for this: list_authorized_properties had none, so every transport re-enumerated the three
# fields by hand (the MCP wrapper, the A2A handler, and this body), which is the enumeration
# this work exists to delete.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class ListAuthorizedPropertiesBody(DerivedBodyEnvelope, ListAuthorizedPropertiesRequestDTO): ...

else:
    ListAuthorizedPropertiesBody = derived_body_model(
        "ListAuthorizedPropertiesBody",
        ListAuthorizedPropertiesRequestDTO,
        properties_module.build_list_authorized_properties_request,
    )


# DERIVED: ListAccountsRequest fields INTERSECT build_list_accounts_request's kwargs. The
# hand-written class dropped ``adcp_major_version``, which the builder accepts and the DTO
# declares -- the version envelope's other half, so a buyer could negotiate by version
# string here but not by major version.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class ListAccountsBody(DerivedBodyEnvelope, ListAccountsRequestDTO): ...

else:
    ListAccountsBody = derived_body_model(
        "ListAccountsBody", ListAccountsRequestDTO, accounts_module.build_list_accounts_request
    )


# DERIVED: SyncAccountsRequest fields INTERSECT build_sync_accounts_request's kwargs.
if TYPE_CHECKING:
    # TYPE-CHECKER ONLY. The runtime class is the derivation in the else branch; this says
    # what it reads as, because derived_body_model returns a VARIABLE holding a class and a
    # variable cannot annotate a route parameter. Not a second field-set definition: nothing
    # here exists at runtime, and test_architecture_rest_body_completeness.py still grades the
    # real class via __derived_from_dto__. Imprecision is deliberate and one-way -- a derived
    # body is DTO fields INTERSECT impl parameters, a SUBSET, so the checker may believe in a
    # field the body dropped; it never hides a field the body has.

    class SyncAccountsBody(DerivedBodyEnvelope, SyncAccountsRequestDTO): ...

else:
    SyncAccountsBody = derived_body_model(
        "SyncAccountsBody", SyncAccountsRequestDTO, accounts_module.build_sync_accounts_request
    )


if TYPE_CHECKING:
    # TYPE-CHECKER ONLY; the runtime class is the derivation in the else branch.
    class GetAdcpCapabilitiesBody(DerivedBodyEnvelope, GetAdcpCapabilitiesRequestDTO): ...

else:
    # DERIVED. It was hand-written to keep ``protocols`` a bare list[str], because bound to
    # the DTO's enum FastAPI rejected an unknown member with INVALID_REQUEST while
    # impl/mcp/a2a reached the shared boundary and answered VALIDATION_ERROR.
    #
    # That is the same violation graded two ways, and the spec settles which: an
    # out-of-enum value violates a SCHEMA constraint, and 3.1/enums/error-code.json assigns
    # those to INVALID_REQUEST -- which is exactly what BR-UC-018's pagination rows already
    # demand for an out-of-enum sort.direction. Keeping this body permissive preserved the
    # disagreement rather than resolving it.
    GetAdcpCapabilitiesBody = derived_body_model(
        "GetAdcpCapabilitiesBody",
        GetAdcpCapabilitiesRequestDTO,
        # The BUILDER, not the raw wrapper: the wrapper takes the built request now, so
        # intersecting the DTO with its signature would announce an empty body.
        capabilities_module.build_get_adcp_capabilities_request,
    )

# ---------------------------------------------------------------------------
# Discovery endpoints (auth-optional)
# ---------------------------------------------------------------------------


@router.post("/products")
async def get_products(body: GetProductsBody, identity: ResolvedIdentity | None = resolve_auth):
    """Get available products matching the brief (auth-optional discovery skill).

    ``ToolError`` propagates to the global handler in ``src.app`` for envelope
    translation; no defensive catch needed here.
    """
    with adcp_validation_boundary(context="get_products request"):
        # Selected off the BUILDER's signature, not GetProductsRequest's fields: the model
        # declares 13 fields this builder does not take (catalog, refine, pagination, ...),
        # and handing it those would turn a key that is ignored today into a TypeError --
        # a 500 on a spec-conformant payload.
        req = products_module.create_get_products_request(
            **select_request_fields(
                GetProductsRequestDTO,
                body,
                accepted_kwargs(products_module.create_get_products_request),
            )
        )
    response = await products_module._get_products_impl(req, identity)
    result = response.model_dump(mode="json")
    return apply_version_compat("get_products", result, body.adcp_version)


@router.get("/capabilities")
async def get_capabilities(identity: ResolvedIdentity | None = resolve_auth):
    """Get AdCP capabilities (auth-optional discovery skill)."""
    # Parameterless, but still built through the shared builder: the wrapper takes a
    # request, and an empty one is what "no filters" means. Calling with no request at all
    # is the shape that made this route the odd one out. The boundary wraps it even though
    # there is no buyer input to reject -- the rule is uniform per route, so a later
    # argument added here cannot quietly escape it.
    with adcp_validation_boundary(context="get_adcp_capabilities request"):
        req = capabilities_module.build_get_adcp_capabilities_request()
    response = await capabilities_module.get_adcp_capabilities_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


@router.post("/capabilities")
async def post_capabilities(body: GetAdcpCapabilitiesBody, identity: ResolvedIdentity | None = resolve_auth):
    """Get AdCP capabilities with request parameters (auth-optional discovery skill).

    Additive alongside the parameterless GET route above (owner decision
    2026-07-24): protocols filtering and context echo need a real request
    body, which a bare GET cannot carry — matches the POST+JSON-body
    convention every other route in this file follows.
    """

    # Through the shared builder, selected off "DTO fields INTERSECT builder kwargs" --
    # the same two steps the A2A handler takes, so neither transport can construct a
    # different request from the same payload.
    #
    # Version pair forwarded explicitly -- see the A2A handler's note: the selector strips
    # the version-envelope fields by design, but this tool negotiates on them.
    builder = capabilities_module.build_get_adcp_capabilities_request
    with adcp_validation_boundary(context="get_adcp_capabilities request"):
        req = builder(
            **select_request_fields(GetAdcpCapabilitiesRequest, body, accepted_kwargs(builder)),
            adcp_version=body.adcp_version,
            adcp_major_version=body.adcp_major_version,
        )
    response = await capabilities_module.get_adcp_capabilities_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


@router.post("/creative-formats")
async def list_creative_formats(body: ListCreativeFormatsBody, identity: ResolvedIdentity | None = resolve_auth):
    """List available creative formats (auth-optional discovery skill)."""
    # Through the shared builder, selected off "DTO fields INTERSECT builder kwargs" --
    # the same call A2A's _handle_list_creative_formats_skill makes, so the two transports
    # cannot construct different requests from the same payload.
    builder = creative_formats_module.build_list_creative_formats_request
    with adcp_validation_boundary(context="list_creative_formats request"):
        selected = select_request_fields(ListCreativeFormatsRequestDTO, body, accepted_kwargs(builder))
        req = builder(**selected) if selected else None

    response = creative_formats_module.list_creative_formats_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


@router.post("/authorized-properties")
async def list_authorized_properties(
    body: ListAuthorizedPropertiesBody, identity: ResolvedIdentity | None = resolve_auth
):
    """List authorized properties (auth-optional discovery skill)."""
    # Through the shared builder the MCP wrapper also calls -- see
    # build_list_authorized_properties_request.
    builder = properties_module.build_list_authorized_properties_request
    with adcp_validation_boundary(context="list_authorized_properties request"):
        selected = select_request_fields(ListAuthorizedPropertiesRequestDTO, body, accepted_kwargs(builder))
        req = builder(**selected) if selected else None

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
        # Through the same converter the sync route uses, rather than handing the wrapper a
        # raw dict where it declares AccountReference. The converter is also where a
        # malformed account object is rejected with the message every other route gives it.
        account=to_account_reference(body.account),
        paused=body.paused,
        flight_start_date=body.flight_start_date,
        flight_end_date=body.flight_end_date,
        start_time=body.start_time,
        end_time=body.end_time,
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
    # Builds through the shared builder and hands the request over. The account
    # enrichment this route used to perform inline now happens once, inside
    # get_media_buy_delivery_raw, off req.account.
    with adcp_validation_boundary(context="get_media_buy_delivery request"):
        account_ref = to_account_reference(body.account) if body.account is not None else None
    req = media_buy_delivery_module._build_get_media_buy_delivery_request(
        media_buy_ids=body.media_buy_ids,
        status_filter=body.status_filter,
        start_date=body.start_date,
        end_date=body.end_date,
        reporting_dimensions=body.reporting_dimensions,
        attribution_window=body.attribution_window,
        include_package_daily_breakdown=body.include_package_daily_breakdown,
        account=account_ref,
        context=to_context_object(body.context),
    )
    response = media_buy_delivery_module.get_media_buy_delivery_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


@router.post("/media-buys/query")
async def get_media_buys(body: GetMediaBuysBody, identity: ResolvedIdentity = require_auth):
    """Query media buys with status and optional delivery snapshots (auth required).

    POST /media-buys is create_media_buy, so the query surface is a distinct
    path rather than a GET on the same one: the AdCP request carries filters and
    an account reference in a body, which a GET cannot express cleanly.

    This route existed for MCP and A2A but not REST, which silently dropped every
    UC-019 scenario from REST parametrization -- 61 scenarios graded on two
    transports while the suite read as covering three.
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

    # Built through the SHARED builder, then handed over as the request -- the same two
    # steps a2a and mcp take, instead of this route re-listing the DTO's fields.
    req = media_buy_list_module._build_get_media_buys_request(
        body.media_buy_ids,
        body.status_filter,
        account_ref,
        to_context_object(body.context),
        bool(body.include_snapshot),
    )
    response = media_buy_list_module.get_media_buys_raw(req=req, identity=identity)
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
        # The buyer's key was NOT forwarded here. SyncCreativesBody carries it and
        # sync-creatives-request.json lists it in /required, but the route omitted it from
        # this call, so a REST buyer's key was discarded before anything looked at it --
        # while mcp and a2a both forward it. What that costs today is the shape check:
        # _sync_creatives_impl runs validate_idempotency_key_shape, so a malformed key was
        # rejected on mcp and a2a and silently accepted on REST. It does NOT yet buy replay:
        # sync_creatives, unlike create_media_buy, does not implement one.
        idempotency_key=body.idempotency_key,
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
        accepted_kwargs(creatives_listing_module.list_creatives_raw),
    )
    selected["filters"] = filters
    response = creatives_listing_module.list_creatives_raw(**selected, identity=identity)
    return response.model_dump(mode="json")


@router.post("/performance-index")
async def update_performance_index(body: UpdatePerformanceIndexBody, identity: ResolvedIdentity = require_auth):
    """Update performance index for a media buy (auth required)."""
    # Built through the SHARED builder, exactly as a2a and mcp do, then handed over as the
    # request. The route no longer re-lists the DTO's fields on the way in.
    req = performance_module._build_update_performance_index_request(
        body.media_buy_id,
        body.performance_data,
        to_context_object(body.context),
    )
    response = performance_module.update_performance_index_raw(
        req=req,
        identity=identity,
    )
    return response.model_dump(mode="json")


@router.post("/accounts")
async def list_accounts(body: ListAccountsBody, identity: ResolvedIdentity = require_auth):
    """List accounts accessible to the authenticated agent (auth required)."""
    from src.core.schemas.account import ListAccountsRequest
    from src.core.tools.accounts import build_list_accounts_request

    with adcp_validation_boundary(context="list_accounts request"):
        req = build_list_accounts_request(
            **select_request_fields(ListAccountsRequest, body, accepted_kwargs(build_list_accounts_request))
        )
    response = accounts_module.list_accounts_raw(req=req, identity=identity)
    return response.model_dump(mode="json")


@router.post("/accounts/sync")
async def sync_accounts(body: SyncAccountsBody, identity: ResolvedIdentity = require_auth):
    """Sync accounts by natural key (auth required)."""
    from src.core.schemas.account import SyncAccountsRequest
    from src.core.tools.accounts import build_sync_accounts_request

    with adcp_validation_boundary(context="sync_accounts request"):
        req = build_sync_accounts_request(
            **select_request_fields(SyncAccountsRequest, body, accepted_kwargs(build_sync_accounts_request))
        )
    response = await accounts_module.sync_accounts_raw(req=req, identity=identity)
    return response.model_dump(mode="json")

"""Get Media Buys tool implementation.

Returns media buy status, creative approval state, and optional delivery snapshots
for monitoring and reporting workflows.

Per-row failure policy
----------------------

Seller-side data corruption in one row has three possible outcomes, and picking one
takes two questions, in this order.

**1. Does the corrupt field have a legal absent value?** Its schema decides.

* OPTIONAL, so an empty value is legal: the row RENDERS with that value and the
  buyer is told on the ``errors[]`` advisory channel. ``targeting_overlay`` takes
  this path — ``None`` is a value the schema permits, and a silent ``None``,
  indistinguishable from "no targeting", is what the advisory exists to prevent.
  This answer is final; question 2 does not apply.
* REQUIRED, so nothing can be put there: the row cannot be rendered at all, and
  question 2 decides what happens instead. ``_persisted_revision`` and
  ``_compute_status`` raise ``AdCPPersistedStateError`` to signal this — a
  fabricated ``revision`` is a concurrency token nobody looked up, and a defaulted
  ``status`` is a lifecycle claim nobody defined.

**2. Did the buyer name this row?** ``_buyer_named_rows`` reads the request shape.

* NAMED it in ``media_buy_ids``: the read REFUSES, terminally, with the error that
  names the seller-side defect. Omitting the row here would answer "no such media
  buy" to a buyer who just asked about that specific one, which is a worse answer
  than an error they can escalate. Ruling R-M1; graded by
  ``@T-UC-019-boundary-revision``.
* Did NOT name it — an unfiltered listing: the row is OMITTED and an advisory
  naming its ``media_buy_id`` takes its place. One corrupt row must not deny a
  tenant every buy they own, and an advisory that does not say WHICH row went
  missing cannot be reconciled against. Graded by
  ``@T-UC-019-listing-omits-unrenderable-row``.

So: never fabricate a required field; never fail a whole listing over one row;
never answer "not found" when the buyer named the row that broke.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, cast

from fastmcp.server.context import Context
from pydantic import Field, RootModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.resolved_identity import ResolvedIdentity
from src.core.tool_context import ToolContext
from src.core.tools._media_buy_status import resolve_canonical_status

logger = logging.getLogger(__name__)


@dataclass
class _MediaBuyData:
    """Plain data extracted from a MediaBuy ORM row."""

    media_buy_id: str
    currency: str | None
    budget: Decimal | None
    start_date: date | None
    end_date: date | None
    start_time: datetime | None
    end_time: datetime | None
    raw_request: dict | None
    created_at: datetime | None
    updated_at: datetime | None
    status: str | None
    is_paused: bool
    # Spec-required on media_buys[] at AdCP 3.1.1; carried through this row object so
    # the response is built from persisted values rather than defaults.
    confirmed_at: datetime | None
    revision: int


@dataclass
class _PackageData:
    """Plain data extracted from a MediaPackage ORM row."""

    media_buy_id: str
    package_id: str
    package_config: dict | None
    budget: Decimal | None
    bid_price: Decimal | None


from adcp.server.helpers import valid_actions_for_status
from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ContextObject, MediaBuyStatus

from src.core.auth import get_principal_object, require_identity, require_tenant
from src.core.database.models import CreativeAssignment, MediaBuy
from src.core.database.repositories import MediaBuyUoW
from src.core.database.repositories.creative import CreativeRepository
from src.core.exceptions import (
    AdCPCapabilityNotSupportedError,
    AdCPPersistedStateError,
    AdCPValidationError,
)
from src.core.helpers.adapter_helpers import get_adapter
from src.core.schemas import (
    ApprovalStatus,
    CreativeApproval,
    Error,
    GetMediaBuysMediaBuy,
    GetMediaBuysPackage,
    GetMediaBuysRequest,
    GetMediaBuysResponse,
    Snapshot,
    SnapshotUnavailableReason,
    Targeting,
)
from src.core.schemas._pinned_fields import revision_minimum
from src.core.tools._mcp import mcp_result
from src.core.validation_helpers import adcp_validation_boundary


def _get_media_buys_impl(
    req: GetMediaBuysRequest,
    identity: ResolvedIdentity | None = None,
    include_snapshot: bool = False,
) -> GetMediaBuysResponse:
    """Get media buys with status, creative approval state, and optional delivery snapshots.

    Args:
        req: Validated GetMediaBuysRequest with all protocol fields
        identity: ResolvedIdentity with principal/tenant info (transport-agnostic)
        include_snapshot: When True, include near-real-time delivery stats per package.
            This is an internal flag controlled by transport wrappers, not by the request object.

    Returns:
        GetMediaBuysResponse with matching media buys
    """
    identity = require_identity(identity, context=req.context)

    if req.account is not None or req.account_id is not None:
        raise AdCPCapabilityNotSupportedError(
            "account filtering is not yet supported",
            suggestion="Omit account/account_id from the request; the seller infers the account from the auth token.",
        )

    testing_ctx = identity.testing_context
    principal_id = identity.principal_id
    if not principal_id:
        return GetMediaBuysResponse(
            media_buys=[],
            errors=[
                Error(  # structural-guard: advisory: get_media_buys degrades to empty list + error, not a raise
                    code="AUTH_REQUIRED", message="Principal ID not found in context"
                )
            ],
        )

    principal = get_principal_object(principal_id, tenant_id=identity.tenant_id)
    if not principal:
        return GetMediaBuysResponse(
            media_buys=[],
            errors=[
                Error(  # structural-guard: advisory: get_media_buys degrades to empty list + error, not a raise
                    code="AUTH_REQUIRED", message=f"Principal {principal_id} not found"
                )
            ],
        )

    # require_tenant raises the canonical auth envelope instead of a raw TypeError
    # if no tenant resolved (the principal advisories above take precedence).
    tenant = require_tenant(identity, context=req.context)
    today = datetime.now(UTC).date()
    tenant_id: str = tenant["tenant_id"]

    # Every non-fatal per-row advisory lands here — a degraded optional field and an
    # omitted unrenderable row alike. Surfaced on the response so the buyer can
    # reconcile out-of-band; see the module docstring for which fault takes which path.
    row_advisories: list[Error] = []

    # Single DB session for all reads — ORM objects are converted to plain
    # dataclasses inside the UoW scope so nothing is accessed after session close.
    with MediaBuyUoW(tenant_id) as uow:
        assert uow.media_buys is not None
        # Resolve which media buys to return
        target_media_buys = _fetch_target_media_buys(req, principal_id, uow, today, row_advisories)

        # Resolve creative approvals for all packages in one batch query
        all_media_buy_ids = [buy.media_buy_id for buy in target_media_buys]
        # FIXME: _fetch_creative_approvals should use a repository method
        assert uow.session is not None
        creative_approvals_by_package = _fetch_creative_approvals(
            all_media_buy_ids, tenant_id, principal_id, uow.session
        )

        # Resolve package configs for all media buys in one batch query
        packages_by_media_buy = _fetch_packages(all_media_buy_ids, uow)

    # Get snapshots from adapter if requested
    snapshot_data: dict[str, dict[str, Snapshot | None]] = {}  # media_buy_id -> package_id -> Snapshot
    unavailable_reason: SnapshotUnavailableReason | None = None

    if include_snapshot:
        adapter = get_adapter(
            principal,
            dry_run=testing_ctx.dry_run if testing_ctx else False,
            testing_context=testing_ctx,
            tenant=tenant,
        )
        if adapter.capabilities.supports_realtime_reporting:
            # Build list of (media_buy_id, package_id, platform_line_item_id) for the adapter
            package_refs = []
            for buy in target_media_buys:
                for pkg in packages_by_media_buy.get(buy.media_buy_id, []):
                    line_item_id = (pkg.package_config or {}).get("platform_line_item_id")
                    package_refs.append((buy.media_buy_id, pkg.package_id, line_item_id))

            snapshot_data = adapter.get_packages_snapshot(package_refs)
        else:
            unavailable_reason = SnapshotUnavailableReason.SNAPSHOT_UNSUPPORTED

    # Build response
    response_media_buys = []
    buyer_named_rows = _buyer_named_rows(req)
    for buy in target_media_buys:
        try:
            status = _compute_status(buy, today)
        except AdCPPersistedStateError as exc:
            if buyer_named_rows:
                # The buyer named this row, so a listing without it answers "no such
                # media buy" — a worse answer than the terminal error naming the
                # seller-side defect (ruling R-M1).
                raise
            row_advisories.append(_omitted_row_advisory(buy.media_buy_id, exc))
            continue

        # Build packages
        packages = packages_by_media_buy.get(buy.media_buy_id, [])
        response_packages = []
        buy_snapshots = snapshot_data.get(buy.media_buy_id, {})

        for pkg in packages:
            pkg_config = pkg.package_config or {}
            pkg_id = pkg.package_id

            # Get creative approvals for this package
            approvals = creative_approvals_by_package.get((buy.media_buy_id, pkg_id), [])

            # Get snapshot for this package
            snapshot = buy_snapshots.get(pkg_id)
            snapshot_unavailable = None
            if include_snapshot and snapshot is None:
                snapshot_unavailable = unavailable_reason or SnapshotUnavailableReason.SNAPSHOT_TEMPORARILY_UNAVAILABLE

            # Materialize targeting_overlay from package_config so callers can verify
            # what was persisted. Tolerates the legacy "targeting" key for data written
            # before the targeting_overlay rename (see media_buy_create.py:638-642).
            # OPTIONAL-field branch of the module's per-row failure policy (see the
            # module docstring): targeting_overlay has a legal empty value, so a
            # single corrupted package_config row renders as None with a non-fatal
            # TARGETING_REHYDRATION_FAILED advisory rather than crashing the whole
            # tenant's get_media_buys response. The REQUIRED-field branch of the same
            # policy is _persisted_revision / _compute_status, which refuse.
            #
            # Narrow ``except`` to ``TypeError`` only: production
            # ``extra="ignore"`` already absorbs unknown-field drift, so
            # ``ValidationError`` here would only fire in dev/CI and we want
            # that canary to surface forgotten field declarations as a hard
            # test failure (CLAUDE.md "No Quiet Failures"). ``TypeError``
            # covers the real-corruption case (non-dict input from a bad row).
            targeting_raw = pkg_config.get("targeting_overlay") or pkg_config.get("targeting")
            targeting_overlay: Targeting | None
            if not targeting_raw:
                targeting_overlay = None
            else:
                try:
                    targeting_overlay = Targeting(**targeting_raw)
                except TypeError as exc:
                    logger.warning(
                        "Failed to rehydrate targeting_overlay for media_buy=%s package=%s; "
                        "returning targeting_overlay=None for this package. Error: %s",
                        buy.media_buy_id,
                        pkg_id,
                        exc,
                    )
                    # Seller-side data-integrity failure (the buyer can't fix it),
                    # surfaced with the standard ``SERVICE_UNAVAILABLE`` wire code —
                    # matching the sibling per-creative advisory in
                    # creatives/_processing.py — with the specific
                    # ``TARGETING_REHYDRATION_FAILED`` shape in the message so
                    # callers can grep/route on it.
                    row_advisories.append(
                        Error(  # structural-guard: advisory per-package result in GetMediaBuysResponse.errors[]
                            code="SERVICE_UNAVAILABLE",
                            message=(
                                f"TARGETING_REHYDRATION_FAILED: targeting overlay for "
                                f"package '{pkg_id}' on media buy '{buy.media_buy_id}' "
                                f"could not be rehydrated; returning "
                                f"targeting_overlay=None for this package."
                            ),
                            field=f"media_buys[].packages[{pkg_id}].targeting_overlay",
                        )
                    )
                    targeting_overlay = None

            response_packages.append(
                GetMediaBuysPackage(
                    package_id=pkg_id,
                    budget=float(pkg.budget) if pkg.budget is not None else None,
                    bid_price=float(pkg.bid_price) if pkg.bid_price is not None else None,
                    product_id=pkg_config.get("product_id"),
                    start_time=pkg_config.get("start_time"),
                    end_time=pkg_config.get("end_time"),
                    paused=pkg_config.get("paused"),
                    targeting_overlay=targeting_overlay,
                    creative_approvals=approvals if approvals else None,
                    snapshot=snapshot,
                    snapshot_unavailable_reason=snapshot_unavailable if include_snapshot else None,
                )
            )

        total_budget = float(buy.budget) if buy.budget else 0.0
        buyer_campaign_ref = (buy.raw_request or {}).get("buyer_campaign_ref")

        response_media_buys.append(
            GetMediaBuysMediaBuy(
                media_buy_id=buy.media_buy_id,
                buyer_campaign_ref=buyer_campaign_ref,
                status=status,
                valid_actions=valid_actions_for_status(status.value),
                currency=buy.currency or "USD",
                total_budget=total_budget,
                packages=response_packages,
                created_at=buy.created_at,
                updated_at=buy.updated_at,
                # Both spec-required on media_buys[] at AdCP 3.1.1, and both read
                # straight off the persisted columns rather than defaulted here.
                # Neither is produced at this site: MediaBuyRepository owns both
                # writes — `_stamp_confirmation_if_needed` writes confirmed_at once,
                # the first time the buy reaches a committed status, and
                # `_bump_parent_revision` advances revision as the buy's monotonic
                # mutation counter. This function is a pure reader of what that seam
                # decided.
                confirmed_at=buy.confirmed_at,
                revision=_persisted_revision(buy),
            )
        )

    return GetMediaBuysResponse(
        media_buys=response_media_buys,
        context=req.context,
        errors=row_advisories or None,
    )


def _build_get_media_buys_request(
    media_buy_ids: list[str] | None,
    status_filter: MediaBuyStatus | list[MediaBuyStatus] | None,
    account: LibraryAccountReference | None,
    context: ContextObject | None,
) -> GetMediaBuysRequest:
    """Build a GetMediaBuysRequest from individual wire params.

    Shared by the MCP wrapper and the A2A/REST raw wrapper so request
    construction runs inside the ONE validation boundary — previously the raw
    wrapper built the request unprotected and REST leaked a raw pydantic
    ``ValidationError`` with no top-level suggestion (#1417).
    """
    with adcp_validation_boundary(context="get_media_buys request"):
        return GetMediaBuysRequest(
            media_buy_ids=media_buy_ids,
            status_filter=cast(MediaBuyStatus | list[MediaBuyStatus] | None, status_filter),
            account=account,
            context=cast(ContextObject | None, context),
        )


async def get_media_buys(
    media_buy_ids: list[str] | None = None,
    status_filter: MediaBuyStatus | list[MediaBuyStatus] | None = None,
    include_snapshot: Annotated[
        bool, Field(description="When true, include near-real-time delivery stats per package")
    ] = False,
    account: LibraryAccountReference | None = None,
    context: ContextObject | None = None,
    ctx: Context | ToolContext | None = None,
):
    """Get media buys with status, creative approval state, and optional delivery snapshots.

    MCP tool wrapper that resolves identity and delegates to the shared implementation.

    Args:
        media_buy_ids: Array of publisher media buy IDs to retrieve (optional)
        status_filter: Filter by status - single status or array of MediaBuyStatus values (optional)
        include_snapshot: When true, include near-real-time delivery stats per package (default: false)
        account: Account reference per AdCP 3.x (optional). Legacy account_id is normalized by middleware.
        context: Application level context object (optional)
        ctx: FastMCP context (automatically provided)

    Returns:
        ToolResult with GetMediaBuysResponse data
    """
    req = _build_get_media_buys_request(media_buy_ids, status_filter, account, context)
    # Read identity pre-resolved by MCPAuthMiddleware
    identity = (await ctx.get_state("identity")) if isinstance(ctx, Context) else None
    response = _get_media_buys_impl(req, identity=identity, include_snapshot=include_snapshot)
    return mcp_result(response)


def get_media_buys_raw(
    media_buy_ids: list[str] | None = None,
    status_filter: MediaBuyStatus | list[MediaBuyStatus] | None = None,
    include_snapshot: bool = False,
    account: LibraryAccountReference | None = None,
    context: ContextObject | None = None,
    ctx: Context | ToolContext | None = None,
    identity: ResolvedIdentity | None = None,
):
    """Get media buys (raw function for A2A server use).

    Args:
        media_buy_ids: Array of publisher media buy IDs to retrieve (optional)
        status_filter: Filter by status - single status or array of MediaBuyStatus values (optional)
        include_snapshot: When true, include near-real-time delivery stats per package (default: false)
        account: Account reference per AdCP 3.x (optional). Legacy account_id is normalized by middleware.
        context: Application level context (optional)
        ctx: Context for authentication (used if identity not pre-resolved)
        identity: Pre-resolved identity (preferred over ctx)

    Returns:
        GetMediaBuysResponse
    """
    if identity is None:
        from src.core.transport_helpers import resolve_identity_from_context

        identity = resolve_identity_from_context(ctx, require_valid_token=True, protocol="a2a")

    req = _build_get_media_buys_request(media_buy_ids, status_filter, account, context)
    return _get_media_buys_impl(req, identity=identity, include_snapshot=include_snapshot)


# --- Helper functions ---


def _buyer_named_rows(req: GetMediaBuysRequest) -> bool:
    """Did the buyer name the rows they want, or ask for whatever this account has?

    The request shape, read in one place, because it decides two unrelated things: the
    default status filter, and what an unrenderable row does. Naming it here keeps the
    second decision visible instead of falling out of a downstream filter, so a reader
    can see which rule applies without tracing where the id list came from.
    """
    return bool(req.media_buy_ids)


def _omitted_row_advisory(media_buy_id: str, exc: AdCPPersistedStateError) -> Error:
    """The advisory that stands in for a media buy too corrupt to render.

    Names the ``media_buy_id`` deliberately. An advisory that says a row was dropped
    without saying which one cannot be reconciled against: the buyer has no way to
    tell whether the buy they are looking for is missing or was never there.
    """
    # CONFIGURATION_ERROR, not SERVICE_UNAVAILABLE, and the pin's own enumMetadata is
    # the reason. SERVICE_UNAVAILABLE carries recovery "transient" / "retry with
    # exponential backoff" — advice that can never succeed here, because no amount of
    # backoff repairs a row whose persisted revision is 0. CONFIGURATION_ERROR carries
    # "terminal" / "surface to a human at the seller ... MUST NOT auto-retry", which is
    # what this fault actually needs. It is also the code ruling R-M1 chose for the
    # REFUSAL on this same fault: one defect, one code, two mechanisms.
    # recovery is stated rather than left to be inferred from the code's enumMetadata:
    # a client that does not consult the enum still learns not to retry.
    return Error(  # structural-guard: advisory per-row omission in GetMediaBuysResponse.errors[]
        code="CONFIGURATION_ERROR",
        recovery="terminal",
        message=(
            f"MEDIA_BUY_UNRENDERABLE: media buy {media_buy_id!r} is omitted from this "
            f"listing because a spec-required field could not be published from the "
            f"persisted row; the remaining media buys are unaffected. Cause: {exc}"
        ),
        field="media_buys[]",
    )


def _fetch_target_media_buys(
    req: GetMediaBuysRequest,
    principal_id: str,
    uow: MediaBuyUoW,
    today: date,
    row_advisories: list[Error],
) -> list[_MediaBuyData]:
    """Fetch media buys from database matching the request filters.

    A row whose spec-required ``status`` or ``revision`` cannot be published is
    either REFUSED or OMITTED, and ``_buyer_named_rows`` decides which. See the module
    docstring for both dimensions of the policy.
    """
    assert uow.media_buys is not None
    # Per AdCP spec: the default status filter (active-only) applies only when
    # media_buy_ids are omitted. When the caller specifies
    # explicit IDs, return all matching buys regardless of status.
    #
    # The same fact also decides what an unrenderable row does, which is why it is
    # read from the request here rather than inferred downstream: a buyer who NAMED
    # a broken row must be told that row is broken, and a buyer who asked for
    # everything must still get the rest.
    buyer_named_rows = _buyer_named_rows(req)
    filter_statuses = _resolve_status_filter(req.status_filter, skip_default=buyer_named_rows)

    buys = uow.media_buys.get_by_principal(
        principal_id,
        media_buy_ids=req.media_buy_ids,
    )

    renderable: list[_MediaBuyData] = []
    for buy in buys:
        try:
            if filter_statuses is not None and _compute_status(buy, today) not in filter_statuses:
                continue
            revision = _persisted_revision(buy)
        except AdCPPersistedStateError as exc:
            if buyer_named_rows:
                # The buyer named this row, so a listing without it answers "no such
                # media buy" — a worse answer than the terminal error naming the
                # seller-side defect (ruling R-M1).
                raise
            row_advisories.append(_omitted_row_advisory(buy.media_buy_id, exc))
            continue
        renderable.append(
            _MediaBuyData(
                media_buy_id=buy.media_buy_id,
                currency=buy.currency,
                budget=buy.budget,
                start_date=cast(date, buy.start_date),
                end_date=cast(date, buy.end_date),
                start_time=buy.start_time,
                end_time=buy.end_time,
                raw_request=buy.raw_request,
                created_at=buy.created_at,
                updated_at=buy.updated_at,
                status=buy.status,
                is_paused=buy.is_paused,
                confirmed_at=buy.confirmed_at,
                revision=revision,
            )
        )
    return renderable


def _resolve_status_filter(
    status_filter: MediaBuyStatus | Any | None,
    *,
    skip_default: bool = False,
) -> set[MediaBuyStatus] | None:
    """Resolve status_filter request field to a set of MediaBuyStatus values.

    Returns None when no filtering should be applied (explicit IDs with no filter).
    """
    if status_filter is None:
        if skip_default:
            return None  # No filtering — return all statuses
        # Default: active only
        return {MediaBuyStatus.active}

    # Normalize every element to a MediaBuyStatus enum. On the wire the filter
    # arrives as bare strings (GetMediaBuysRequest.status_filter is not coerced
    # to the enum), while _compute_status returns MediaBuyStatus members — so a
    # raw ``set(status_filter)`` of strings never matches the enum membership
    # test at the call site, silently dropping every buy. ``MediaBuyStatus(x)``
    # is idempotent for enum members and coerces valid strings.
    if isinstance(status_filter, RootModel):
        raw = status_filter.root
    elif isinstance(status_filter, list):
        raw = status_filter
    else:
        raw = [status_filter]

    try:
        return {MediaBuyStatus(s) for s in raw}
    except ValueError as e:
        # An unknown status string is a bad request, not a server fault — surface
        # a clean VALIDATION_ERROR instead of letting the ValueError escape as a
        # 500. (A dedicated STATUS_FILTER_INVALID_VALUE code is a separate,
        # unimplemented gap; see the xfailed boundary-status-filter rows.)
        raise AdCPValidationError(
            f"Invalid status_filter value: {e}",
            field="status_filter",
            suggestion="status_filter values must be valid media-buy statuses",
        ) from e


# A row below the pin's bound on media_buys[].revision cannot be published at all — and
# the refusal has to be raised HERE rather than left to the response model, because a
# model-level ValidationError reaches the buyer as VALIDATION_ERROR/correctable: advice
# to "fix field values" for a column the SELLER owns and the buyer has never seen. Same
# reasoning, same typed error, and the same read boundary as an out-of-vocabulary
# status (PersistedMediaBuyStatus.parse). The bound itself is read from the pin.
def _persisted_revision(buy) -> int:
    """The row's revision, or ``AdCPPersistedStateError``.

    REQUIRED-field branch of the module's per-row failure policy: ``revision`` is the
    buyer's optimistic-concurrency token, so there is no value to substitute. Raising
    here does not fail the listing — the fetch stage catches it and omits this one row
    with an advisory naming it.
    """
    minimum = revision_minimum()
    revision = buy.revision
    if revision is None or revision < minimum:
        raise AdCPPersistedStateError(
            f"media buy {buy.media_buy_id!r} carries persisted revision {revision!r}, below the "
            f"pinned minimum of {minimum}; the optimistic-concurrency token cannot be published",
            field="revision",
        )
    return revision


def _compute_status(buy: MediaBuy | _MediaBuyData, today: date) -> MediaBuyStatus:
    """Resolve a media buy's AdCP status for the get_media_buys read path.

    Delegates the persisted-status map + flight-window refinement to the shared
    ``resolve_canonical_status`` (the single source of truth also used by
    get_media_buy_delivery, so both required tools describe the same buy with
    the same status — pinned by test_media_buy_status_consistency). The only
    adaptation to the lifecycle surface: the canonical vocabulary's delivery-only
    "failed" has no AdCP lifecycle equivalent, so it collapses to the closest
    terminal state, "rejected" (enums/media-buy-status.json).

    """
    canonical = resolve_canonical_status(buy, today)
    if canonical == "failed":
        return MediaBuyStatus.rejected
    return MediaBuyStatus(canonical)


def _fetch_packages(media_buy_ids: list[str], uow: MediaBuyUoW) -> dict[str, list[_PackageData]]:
    """Fetch all packages for the given media buy IDs, grouped by media_buy_id."""
    assert uow.media_buys is not None
    if not media_buy_ids:
        return {}

    packages_by_buy = uow.media_buys.get_packages_for_ids(media_buy_ids)

    result: dict[str, list[_PackageData]] = {}
    for media_buy_id, packages in packages_by_buy.items():
        result[media_buy_id] = [
            _PackageData(
                media_buy_id=pkg.media_buy_id,
                package_id=pkg.package_id,
                package_config=pkg.package_config,
                budget=pkg.budget,
                bid_price=pkg.bid_price,
            )
            for pkg in packages
        ]
    return result


def _fetch_creative_approvals(
    media_buy_ids: list[str],
    tenant_id: str,
    principal_id: str,
    session: Session,
) -> dict[tuple[str, str], list[CreativeApproval]]:
    """Fetch creative approvals for all packages, grouped by (media_buy_id, package_id)."""
    if not media_buy_ids:
        return {}

    # Get all creative assignments for these media buys
    assignment_stmt = select(CreativeAssignment).where(
        CreativeAssignment.tenant_id == tenant_id,
        CreativeAssignment.media_buy_id.in_(media_buy_ids),
    )
    assignments: Sequence[CreativeAssignment] = session.scalars(assignment_stmt).all()

    if not assignments:
        return {}

    # Fetch all referenced creatives in one principal-scoped query. The map is
    # keyed by bare creative_id, but the creatives PK is composite (creative_id,
    # tenant_id, principal_id) — a tenant-only load could resolve a colliding id
    # to ANOTHER principal's row and show their approval status to this buyer.
    creative_ids = [a.creative_id for a in assignments]
    creatives = {
        c.creative_id: c for c in CreativeRepository(session, tenant_id).get_by_ids(creative_ids, principal_id)
    }

    # Build approval objects grouped by (media_buy_id, package_id)
    result: dict[tuple[str, str], list[CreativeApproval]] = {}
    for assignment in assignments:
        creative = creatives.get(assignment.creative_id)
        if creative is None:
            continue

        approval_status = _map_creative_status(creative.status)
        rejection_reason = None
        if approval_status == ApprovalStatus.rejected:
            rejection_reason = creative.data.get("rejection_reason") if creative.data else None

        key = (assignment.media_buy_id, assignment.package_id)
        result.setdefault(key, []).append(
            CreativeApproval(
                creative_id=assignment.creative_id,
                approval_status=approval_status,
                rejection_reason=rejection_reason,
            )
        )

    return result


def _map_creative_status(status: str) -> ApprovalStatus:
    """Map internal creative status to AdCP ApprovalStatus."""
    if status == "approved":
        return ApprovalStatus.approved
    if status == "rejected":
        return ApprovalStatus.rejected
    return ApprovalStatus.pending_review

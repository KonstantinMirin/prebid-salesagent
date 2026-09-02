"""MCP and A2A wrapper functions for sync_creatives."""

from typing import Annotated

from adcp import PushNotificationConfig
from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ContextObject, ValidationMode
from adcp.types.generated_poc.creative.sync_creatives_request import Assignment
from fastmcp.server.context import Context
from pydantic import Field

from src.core.helpers import enum_value
from src.core.idempotency_canonical import canonical_request_hash
from src.core.schemas.creative import CreativeAssetRequest, SyncCreativesRequest
from src.core.tool_context import ToolContext
from src.core.tools._mcp import mcp_result
from src.core.transport_helpers import NOT_PROVIDED, IdentityOrNotProvided, resolve_identity_if_not_provided

from ._sync import _sync_creatives_impl


def build_sync_creatives_request(
    *,
    creatives: list[CreativeAssetRequest],
    idempotency_key: str | None = None,
    account: LibraryAccountReference | None = None,
    assignments: list[Assignment] | None = None,
    creative_ids: list[str] | None = None,
    delete_missing: bool | None = None,
    dry_run: bool | None = None,
    validation_mode: ValidationMode | None = None,
    push_notification_config: PushNotificationConfig | None = None,
    context: ContextObject | None = None,
) -> SyncCreativesRequest:
    """Build the shared sync_creatives request for transport wrappers.

    The ONE seam every transport constructs the typed request through, matching
    build_list_authorized_properties_request and friends. It is what makes the tool's
    ADVERTISED shape derivable: _register_tool resolves the DTO from the builder a wrapper
    calls, so with this in place sync_creatives no longer needs the explicit ``dto=``
    escape hatch.

    ``account`` and ``idempotency_key`` are typed OPTIONAL here and REQUIRED by
    SyncCreativesRequest, which lists both in /required. That split is deliberate: a
    transport wrapper cannot make them positional-required without reordering its whole
    signature, and the DTO is the one place the requirement should live anyway. Passing
    None reaches the model and comes back as an INVALID_REQUEST naming the field -- which
    is what a buyer omitting a required field should get. Before anything built the DTO,
    the same omission was simply accepted.
    """
    return SyncCreativesRequest(
        # Normalised to the request item type. A wire dict pydantic coerces on its own, but
        # a MODEL instance of a different class it does not -- and in-process callers hand
        # over library CreativeAsset objects, which would fail validation against
        # CreativeAssetRequest despite carrying the same data. Coercing here keeps that
        # detail at the boundary instead of making every caller convert.
        creatives=[
            c if isinstance(c, CreativeAssetRequest) else CreativeAssetRequest.model_validate(c, from_attributes=True)
            for c in creatives
        ],
        idempotency_key=idempotency_key,
        account=account,
        assignments=assignments,
        creative_ids=creative_ids,
        delete_missing=delete_missing,
        dry_run=dry_run,
        validation_mode=validation_mode,
        push_notification_config=push_notification_config,
        context=context,
    )


async def sync_creatives(
    creatives: list[CreativeAssetRequest],
    idempotency_key: Annotated[
        str,
        Field(
            description=(
                "Client-generated key for safe retries; resending with the same key is "
                "at-most-once. 16-255 chars, ^[A-Za-z0-9_.:-]{16,255}$. Required by AdCP 3.1.1."
            )
        ),
    ],
    assignments: list[Assignment] | None = None,
    creative_ids: list[str] | None = None,
    delete_missing: Annotated[
        bool, Field(description="Delete creatives not in the sync payload (use with caution)")
    ] = False,
    dry_run: Annotated[bool, Field(description="Preview changes without applying them")] = False,
    validation_mode: ValidationMode | None = None,
    push_notification_config: PushNotificationConfig | None = None,
    context: ContextObject | None = None,  # Application level context per adcp spec
    account: LibraryAccountReference | None = None,
    ctx: Context | ToolContext | None = None,
):
    """Sync creative assets to centralized library (AdCP v2.5 spec compliant endpoint).

    MCP tool wrapper that delegates to the shared implementation.
    FastMCP automatically validates and coerces JSON inputs to Pydantic models.

    Args:
        creatives: List of creative assets to sync
        assignments: Bulk assignment map of creative_id to package_ids (spec-compliant)
        creative_ids: Filter to limit sync scope to specific creatives (AdCP 2.5)
        delete_missing: Delete creatives not in sync payload (use with caution)
        dry_run: Preview changes without applying them
        validation_mode: Validation strictness (strict or lenient)
        push_notification_config: Push notification config for async notifications (AdCP spec, optional)
        context: Application level context per adcp spec
        ctx: FastMCP context (automatically provided)

    Returns:
        ToolResult with SyncCreativesResponse data
    """
    identity = (await ctx.get_state("identity")) if isinstance(ctx, Context) else None

    # Resolve account at transport boundary (before _impl)
    from src.core.transport_helpers import enrich_identity_with_account

    identity = enrich_identity_with_account(identity, account)

    # Build the typed request FIRST, so the schema's own rules (idempotency_key's pattern,
    # account's presence, the assignments item shape) are enforced here rather than only on
    # whichever transport happened to construct the model. This is also the seam that makes
    # the advertised shape derivable -- _register_tool reads the DTO off this builder.
    req = build_sync_creatives_request(
        creatives=creatives,
        idempotency_key=idempotency_key,
        account=account,
        assignments=assignments,
        creative_ids=creative_ids,
        delete_missing=delete_missing,
        dry_run=dry_run,
        validation_mode=validation_mode,
        push_notification_config=push_notification_config,
        context=context,
    )

    response = _sync_creatives_impl(
        creatives=req.creatives,
        assignments=req.assignments,
        creative_ids=req.creative_ids,
        delete_missing=bool(req.delete_missing),
        dry_run=bool(req.dry_run),
        validation_mode=enum_value(req.validation_mode) or "strict",
        push_notification_config=req.push_notification_config,
        context=req.context,
        idempotency_key=req.idempotency_key,
        identity=identity,
    )
    return mcp_result(response)


def sync_creatives_raw(
    req: SyncCreativesRequest,
    ctx: Context | ToolContext | None = None,
    identity: IdentityOrNotProvided = NOT_PROVIDED,
):
    """Sync creative assets to the centralized creative library (raw function for A2A server use).

    Delegates to the shared implementation.

    Args:
        creatives: List of CreativeAsset models
        assignments: Bulk assignment map of creative_id to package_ids (spec-compliant)
        creative_ids: Filter to limit sync scope to specific creatives (AdCP 2.5)
        delete_missing: Delete creatives not in sync payload (use with caution)
        dry_run: Preview changes without applying them
        validation_mode: Validation strictness (strict or lenient)
        push_notification_config: Push notification config for status updates
        context: Application level context per adcp spec
        ctx: FastMCP context (automatically provided)
        identity: ResolvedIdentity (transport-agnostic, preferred over ctx)

    Returns:
        SyncCreativesResponse with synced creatives and assignments
    """
    identity = resolve_identity_if_not_provided(identity, ctx)

    # Account resolution at the boundary, read OFF the request rather than from a separate
    # parameter beside it -- account is a SyncCreativesRequest field, so one carrier.
    from src.core.transport_helpers import enrich_identity_with_account

    identity = enrich_identity_with_account(identity, req.account)

    return _sync_creatives_impl(
        # Canonicalised HERE, from the built request, because _impl must not call
        # model_dump (the no-model-dump-in-impl guard) and must not rebuild the request.
        request_hash=canonical_request_hash(req) if req.idempotency_key and not req.dry_run else None,
        creatives=req.creatives,
        assignments=req.assignments,
        creative_ids=req.creative_ids,
        delete_missing=bool(req.delete_missing),
        dry_run=bool(req.dry_run),
        validation_mode=enum_value(req.validation_mode) or "strict",
        push_notification_config=req.push_notification_config,
        context=req.context,
        idempotency_key=req.idempotency_key,
        identity=identity,
    )

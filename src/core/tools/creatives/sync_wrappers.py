"""MCP and A2A wrapper functions for sync_creatives."""

from typing import Annotated, Any

from adcp import PushNotificationConfig
from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ContextObject, CreativeAsset, ValidationMode
from adcp.types.generated_poc.creative.sync_creatives_request import SyncCreativesRequest as LibrarySyncCreativesRequest
from fastmcp.server.context import Context
from pydantic import Field

from src.core.helpers import enum_value
from src.core.resolved_identity import ResolvedIdentity
from src.core.tool_context import ToolContext
from src.core.tools._mcp import mcp_result
from src.core.version_compat import accepts_spec_request_fields

from ._sync import _sync_creatives_impl


async def sync_creatives(
    creatives: list[CreativeAsset],
    assignments: dict[str, list[str]] | None = None,
    creative_ids: list[str] | None = None,
    delete_missing: Annotated[
        bool, Field(description="Delete creatives not in the sync payload (use with caution)")
    ] = False,
    dry_run: Annotated[bool, Field(description="Preview changes without applying them")] = False,
    validation_mode: ValidationMode | None = None,
    push_notification_config: PushNotificationConfig | None = None,
    context: ContextObject | None = None,  # Application level context per adcp spec
    account: LibraryAccountReference | None = None,
    # Seam carrier: the wire request as its pinned model. Same NAME on every
    # tool that opts in; typed as this tool's own pinned request model, and
    # filtered out of the published schema by the decorator.
    _spec_request: LibrarySyncCreativesRequest | None = None,
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

    # Phase 1a: Pass typed models directly to impl (no more model_dump conversion)
    validation_mode_str = enum_value(validation_mode) or "strict"

    response = _sync_creatives_impl(
        creatives=creatives,
        assignments=assignments,
        creative_ids=creative_ids,
        delete_missing=delete_missing,
        dry_run=dry_run,
        validation_mode=validation_mode_str,
        push_notification_config=push_notification_config,
        context=context,
        identity=identity,
        # From the acceptance seam's request model, not a per-tool parameter:
        # the wire may carry idempotency_key even when this wrapper's own
        # signature never bound it, which is exactly the case the seam exists for.
        idempotency_key=getattr(_spec_request, "idempotency_key", None),
    )
    return mcp_result(response)


@accepts_spec_request_fields
def sync_creatives_raw(
    # A2A/REST send wire dicts; _sync_creatives_impl validates each entry
    # individually (partial-success semantics with per-creative results).
    creatives: list[CreativeAsset] | list[dict[str, Any]],
    assignments: dict = None,
    creative_ids: list[str] = None,
    delete_missing: bool = False,
    dry_run: bool = False,
    validation_mode: str = "strict",
    push_notification_config: PushNotificationConfig | None = None,
    context: ContextObject | None = None,
    account: LibraryAccountReference | None = None,
    ctx: Context | ToolContext | None = None,
    identity: ResolvedIdentity | None = None,
    # Seam carrier — see the MCP sibling above. Present on every seam member,
    # raw wrappers included: the decorator passes it unconditionally.
    _spec_request: LibrarySyncCreativesRequest | None = None,
):
    """Sync creative assets to the centralized creative library (raw function for A2A server use).

    Delegates to the shared implementation.

    @accepts_spec_request_fields additionally lets this function be CALLED
    with every field SyncCreativesRequest defines (e.g. ext) without raising
    TypeError — accepted, not yet forwarded or honored by _impl
    (salesagent-g6m2.10).

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
    if identity is None:
        from src.core.transport_helpers import resolve_identity_from_context

        identity = resolve_identity_from_context(ctx)

    # Resolve account at transport boundary (before _impl)
    from src.core.transport_helpers import enrich_identity_with_account

    identity = enrich_identity_with_account(identity, account)

    return _sync_creatives_impl(
        creatives=creatives,
        assignments=assignments,
        creative_ids=creative_ids,
        delete_missing=delete_missing,
        dry_run=dry_run,
        validation_mode=validation_mode,
        push_notification_config=push_notification_config,
        context=context,
        identity=identity,
        # From the acceptance seam's request model, not a per-tool parameter:
        # the wire may carry idempotency_key even when this wrapper's own
        # signature never bound it, which is exactly the case the seam exists for.
        idempotency_key=getattr(_spec_request, "idempotency_key", None),
    )

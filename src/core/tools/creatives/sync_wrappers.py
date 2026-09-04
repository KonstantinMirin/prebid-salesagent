"""MCP and A2A wrapper functions for sync_creatives."""

from collections.abc import Sequence
from typing import Annotated, Any

from adcp import PushNotificationConfig
from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ContextObject, ValidationMode
from adcp.types.generated_poc.creative.sync_creatives_request import Assignment
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from src.core.idempotency_canonical import canonical_request_hash
from src.core.schema_helpers import to_push_notification_config
from src.core.schemas.creative import CreativeAssetRequest, SyncCreativesRequest
from src.core.tool_context import ToolContext
from src.core.tools._mcp import mcp_result
from src.core.tools._request_defaults import omit_unset
from src.core.transport_helpers import NOT_PROVIDED, IdentityOrNotProvided, resolve_identity_if_not_provided

from ._sync import _sync_creatives_impl


def build_sync_creatives_request(
    *,
    # Widened to what this builder demonstrably ACCEPTS, for the same reason
    # push_notification_config below is: the annotation used to say
    # ``list[CreativeAssetRequest]`` while the body coerced anything model_validate could
    # read, so it was decorative on every caller that is not the MCP wrapper -- A2A and
    # REST hand over wire dicts, and the in-process media-buy callers hand over
    # PackageRequest.creatives, which is typed as the listing RESPONSE model. What the body
    # actually accepts is what ``model_validate(..., from_attributes=True)`` can read, so
    # that is what this now says -- the same union ``_sync_creatives_impl`` already declared
    # for the sequence it received. Widening changes no advertised shape:
    # derived_body_model and accepted_kwargs read this signature for parameter NAMES only,
    # taking field TYPES from the DTO.
    creatives: Sequence[CreativeAssetRequest | BaseModel | dict[str, Any]],
    idempotency_key: str | None = None,
    account: LibraryAccountReference | None = None,
    assignments: list[Assignment] | None = None,
    creative_ids: list[str] | None = None,
    delete_missing: bool | None = None,
    dry_run: bool | None = None,
    validation_mode: ValidationMode | None = None,
    # Widened deliberately: A2A hands the buyer's raw wire dict straight to this builder
    # (select_request_fields off the parameter bag), so a bare PushNotificationConfig
    # annotation here would be decorative. It is coerced below.
    push_notification_config: PushNotificationConfig | dict[str, Any] | None = None,
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
        # Omitted when unsent so SyncCreativesRequest's own defaults apply: delete_missing
        # and dry_run declare False and validation_mode declares strict, and forwarding a
        # None overwrote all three with null. _sync_creatives_impl used to re-establish
        # them by hand at the read site (bool(...), or "strict"); those are gone with this.
        **omit_unset(
            idempotency_key=idempotency_key,
            account=account,
            assignments=assignments,
            creative_ids=creative_ids,
            delete_missing=delete_missing,
            dry_run=dry_run,
            validation_mode=validation_mode,
        ),
        # Coerced through the shared funnel rather than left to the model's own validation:
        # this is the seam where the untyped wire document arrives (A2A forwards the buyer's
        # raw dict), and to_push_notification_config carries the boundary with it -- a
        # document the pinned schema forbids refuses HERE as a typed AdCP error naming
        # push_notification_config.<field>, instead of reaching _impl unchallenged. It is
        # idempotent for the callers (MCP, REST) that already hold a typed config.
        push_notification_config=to_push_notification_config(push_notification_config),
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
    # ``= None`` states NOTHING: the advertised default comes from the DTO field
    # (derived_signature), and an omitted value reaches the builder as None, which
    # omit_unset drops so the model's own default applies. Restating the DTO's value
    # here made it two declarations of one fact.
    delete_missing: Annotated[
        bool | None, Field(description="Delete creatives not in the sync payload (use with caution)")
    ] = None,
    dry_run: Annotated[bool | None, Field(description="Preview changes without applying them")] = None,
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

    # Delegated to the raw wrapper rather than calling _impl a second time. Idempotency is
    # transport-agnostic (AdCP 3.1.1 idempotency.yaml: the at-most-once promise is attached
    # to the field, not to a channel), but the request_hash that carries it was threaded in
    # from ONE of the two call sites: this one dropped it, so `cache_success` never fired on
    # MCP and a repeated key re-executed the sync there while replaying on a2a and rest.
    # A second call site is a second chance to drop the next parameter, so there is now one:
    # a2a, rest and mcp all reach _impl through sync_creatives_raw, which resolves identity
    # (explicit here, so it is returned unchanged rather than re-resolved from ambient
    # context) and enriches it off req.account exactly as this wrapper used to inline.
    return mcp_result(sync_creatives_raw(req=req, identity=identity))


def sync_creatives_raw(
    req: SyncCreativesRequest,
    ctx: Context | ToolContext | None = None,
    identity: IdentityOrNotProvided = NOT_PROVIDED,
):
    """Sync creative assets to the centralized creative library (raw function for A2A server use).

    Delegates to the shared implementation.

    Args:
        req: The built SyncCreativesRequest — every protocol field travels on it. The
            per-field parameters this docstring used to list (creatives, assignments,
            creative_ids, delete_missing, dry_run, validation_mode,
            push_notification_config, context) are fields of that request.
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
        req=req,
        identity=identity,
        # Canonicalised HERE, from the built request, because _impl must not call
        # model_dump (the no-model-dump-in-impl guard) and must not rebuild the request.
        # It is the ONE argument that travels beside the request rather than on it: the
        # hash is a property of the TRANSMISSION (the RFC 8785 canonical form of what
        # arrived), not a field the buyer sends, and nothing in the pinned
        # creative/sync-creatives-request.json declares it.
        request_hash=canonical_request_hash(req) if req.idempotency_key and not req.dry_run else None,
    )

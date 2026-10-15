"""Creative format parsing and asset conversion helpers.

SDK 5.7 type:ignore tracking (adcontextprotocol/adcp-client-python#913):
- [attr-defined] on lines ~694, ~696, ~816, ~826, ~884, ~896:
  AssetSpec (ImageFormatAsset) is a RootModel proxy; .asset_type and .asset_id
  exist at runtime but mypy cannot see through __getattr__. Fixable when the SDK
  ships typed accessors or a shared unwrapper helper.
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any

from adcp.types import ValidationMode
from adcp.types.domains.core.format_id import FormatReferenceStructuredObject as LibraryFormatId
from pydantic import BaseModel, ValidationError

from src.core.tenant_context import TenantContext

if TYPE_CHECKING:
    from adcp.types import AccountReference as LibraryAccountReference

    from src.core.resolved_identity import ResolvedIdentity
    from src.core.schemas import PackageRequest

from src.core.errors.details import CreativeRejectionDetails

logger = logging.getLogger(__name__)


def _extract_format_namespace(format_value: Any) -> tuple[str, str]:
    """Extract agent_url and format ID from format_id field (AdCP v2.4).

    Args:
        format_value: FormatId dict/object with agent_url+id fields

    Returns:
        Tuple of (agent_url, format_id) - both as strings

    Raises:
        ValueError: If format_value doesn't have required agent_url and id fields

    Note:
        Converts Pydantic AnyUrl types to strings for database compatibility.
        The adcp library's FormatId.agent_url is typed as AnyUrl, but PostgreSQL
        needs strings.
    """
    if isinstance(format_value, dict):
        agent_url = format_value.get("agent_url")
        format_id = format_value.get("id")
        if not agent_url or not format_id:
            raise ValueError(f"format_id must have both 'agent_url' and 'id' fields. Got: {format_value}")
        # Convert to string in case agent_url is AnyUrl from Pydantic model
        return str(agent_url), format_id
    if isinstance(format_value, LibraryFormatId):
        # Convert AnyUrl to string for database compatibility
        return str(format_value.agent_url), format_value.id
    if isinstance(format_value, str):
        raise ValueError(
            f"format_id must be an object with 'agent_url' and 'id' fields (AdCP v2.4). "
            f"Got string: '{format_value}'. "
            f"String format_id is no longer supported - all formats must be namespaced."
        )
    raise ValueError(f"Invalid format_id format. Expected object with agent_url and id, got: {type(format_value)}")


def _normalize_format_value(format_value: Any) -> str:
    """Normalize format value to string ID (for legacy code compatibility).

    Args:
        format_value: FormatId dict/object with agent_url+id fields

    Returns:
        String format identifier

    Note: This is a legacy compatibility function. New code should use _extract_format_namespace
    to properly handle the agent_url namespace.
    """
    _, format_id = _extract_format_namespace(format_value)
    return format_id


def _validate_creative_assets(assets: Any) -> dict[str, dict[str, Any]] | None:
    """Validate that creative assets are in AdCP v2.1+ dictionary format.

    AdCP v2.1+ requires assets to be a dictionary keyed by asset_id from the format's
    asset_requirements.

    Args:
        assets: Assets in dict format keyed by asset_id, or None

    Returns:
        Dictionary of assets keyed by asset_id, or None if no assets provided

    Raises:
        ValueError: If assets are not in the correct dict format, or if asset structure is invalid

    Example:
        # Correct format (AdCP v2.1+)
        assets = {
            "main_image": {"asset_type": "image", "url": "https://..."},
            "logo": {"asset_type": "image", "url": "https://..."}
        }
    """
    if assets is None:
        return None

    # Must be a dict
    if not isinstance(assets, dict):
        raise ValueError(
            f"Invalid assets format: expected dict keyed by asset_id (AdCP v2.1+), got {type(assets).__name__}. "
            f"Assets must be a dictionary like: {{'main_image': {{'asset_type': 'image', 'url': '...'}}}}"
        )

    # Validate structure of each asset
    for asset_id, asset_data in assets.items():
        # Asset ID must be a non-empty string
        if not isinstance(asset_id, str):
            raise ValueError(
                f"Asset key must be a string (asset_id from format), got {type(asset_id).__name__}: {asset_id!r}"
            )
        if not asset_id.strip():
            raise ValueError("Asset key (asset_id) cannot be empty or whitespace-only")

        # Asset data must be a dict or Pydantic model (typed Asset from CreativeAsset)
        if not isinstance(asset_data, dict) and not isinstance(asset_data, BaseModel):
            raise ValueError(
                f"Asset '{asset_id}' data must be a dict or model, got {type(asset_data).__name__}. "
                f"Expected format: {{'asset_type': '...', 'url': '...', ...}}"
            )

    return assets


def _detect_snippet_type(snippet: str) -> str:
    """Auto-detect snippet type from content for legacy support."""
    if snippet.startswith("<?xml") or ".xml" in snippet:
        return "vast_xml"
    elif snippet.startswith("http") and "vast" in snippet.lower():
        return "vast_url"
    elif snippet.startswith("<script"):
        return "javascript"
    else:
        return "html"  # Default


def process_and_upload_package_creatives(
    packages: list["PackageRequest"],
    *,
    identity: "ResolvedIdentity",
    # The OUTER create_media_buy's account, because the nested sync is built as a real
    # SyncCreativesRequest and these creatives belong to that account. No idempotency_key:
    # this calls the creative-sync SERVICE, and idempotency is the controller's job.
    account: "LibraryAccountReference | None" = None,
    principal_id: str,
    tenant: TenantContext,
) -> tuple[list["PackageRequest"], dict[str, list[str]]]:
    """Upload creatives from package.creatives arrays and return updated packages.

    For each package with a non-empty `creatives` array:
    1. Converts Creative objects to dicts
    2. Uploads them via _sync_creatives_impl
    3. Extracts uploaded creative IDs
    4. Creates updated package with merged creative_ids

    This function is immutable - it returns new Package instances instead of
    modifying the input packages.

    Args:
        packages: List of Package objects to process
        identity: The caller the create controller already resolved
        account: The outer create_media_buy's account, carried onto the nested sync request
        principal_id: The already-resolved caller, passed to the creative-sync service
        tenant: The already-resolved tenant, likewise

    Returns:
        Tuple of (updated_packages, uploaded_ids_by_product):
        - updated_packages: New Package instances with creative_ids merged
        - uploaded_ids_by_product: Mapping of product_id -> uploaded creative IDs

    Raises:
        ToolError: If creative upload fails for any package (CREATIVES_UPLOAD_FAILED)

    Example:
        >>> packages = [PackageRequest(product_id="p1", creatives=[creative1, creative2])]
        >>> updated_pkgs, uploaded_ids = process_and_upload_package_creatives(packages, identity=identity, ...)
        >>> # updated_pkgs[0].creative_ids contains uploaded IDs
        >>> assert uploaded_ids["p1"] == ["c1", "c2"]
    """
    import logging

    # Lazy import to avoid circular dependency
    from src.core.exceptions import AdCPAdapterError, AdCPCreativeRejectedError, AdCPSalesAgentError
    from src.core.schemas import SyncCreativesRequest
    from src.core.tools.creatives import sync_creatives

    logger = logging.getLogger(__name__)
    uploaded_by_product: dict[str, list[str]] = {}
    updated_packages: list[PackageRequest] = []

    for pkg_idx, pkg in enumerate(packages):
        # Skip packages without creatives (type system guarantees this attribute exists)
        if not pkg.creatives:
            updated_packages.append(pkg)  # No changes needed
            continue

        product_id = pkg.product_id or f"package_{pkg_idx}"
        logger.info(f"Processing {len(pkg.creatives)} creatives for package with product_id {product_id}")

        try:
            # Step 1: Upload creatives to database via sync_creatives
            # Phase 1a: Pass models directly (impl handles both models and dicts)
            # Built through the SAME builder the three transports use, rather than handed
            # to _impl as loose fields. _sync_creatives_impl takes a request; an in-process
            # caller that could not produce one was reaching into the tool instead of
            # invoking it.
            #
            # No request_hash is passed: there is no transmission here to canonicalise, and
            # that absence is what keeps the outer media buy's key out of the shared
            # (agent, account, key) idempotency cache scope -- see _sync_creatives_impl.
            # A pydantic ValidationError from this builder must NOT reach the
            # `except Exception` below, which reclassifies it as AdCPAdapterError --
            # "Service temporarily unavailable" -- telling a buyer who sent a malformed
            # inline creative that the SERVER is broken and to retry, instead of which of
            # their fields to fix. That is why the handler list below re-raises it.
            sync_req = SyncCreativesRequest(
                creatives=pkg.creatives,
                account=account,
                # ITS OWN key, not the outer request's. sync-creatives-request.json puts
                # idempotency_key in /required so the model needs one, but this request is
                # never sent by anyone and the SERVICE never reads it -- idempotency belongs
                # to the controller, which ran once for the create the buyer actually sent.
                # Borrowing the outer key here is what used to make this call look like a
                # second buyer request wearing the same identifier.
                idempotency_key=f"internal-creative-upload-{uuid.uuid4().hex}",
                # AdCP 2.5: Full upsert semantics (no patch parameter)
                assignments=None,  # Assign separately after creation
                dry_run=False,
                validation_mode=ValidationMode.strict,
                push_notification_config=None,
            )
            # The create controller resolved the caller before reaching here; no auth is
            # re-run inside a service, which is the layering this extraction removed.
            sync_response = sync_creatives(sync_req, identity=identity, principal_id=principal_id, tenant=tenant)

            # A failed sync result means the creative was REJECTED (e.g. missing
            # required URL / dimensions in strict validation). Surface it instead
            # of silently merging the failed id and letting the downstream
            # "Creative IDs not found" check mask the real reason ('No Quiet
            # Failures'). The per-creative error message names the offending
            # field (e.g. the missing URL) so the buyer can remediate (POST-F3).
            failed_results = [r for r in sync_response.creatives if r.action == "failed"]
            if failed_results:
                detail_msgs = [f"{r.creative_id}: {err.message}" for r in failed_results for err in (r.errors or [])]
                error_msg = "Creative validation failed:\n" + "\n".join(f"  • {m}" for m in detail_msgs)
                logger.error(error_msg)
                raise AdCPCreativeRejectedError(
                    # `creative_errors` was a synonym for the pin's `reasons`.
                    details=CreativeRejectionDetails(reasons=detail_msgs),
                )

            # Extract creative IDs from successfully synced creatives only.
            uploaded_ids = [
                result.creative_id
                for result in sync_response.creatives
                if result.creative_id and result.action != "failed"
            ]

            logger.info(
                f"Synced {len(uploaded_ids)} creatives to database for package "
                f"with product_id {product_id}: {uploaded_ids}"
            )

            # Note: Ad server upload happens later in media buy creation flow
            # This function runs BEFORE media_buy_id exists, so we can't call
            # adapter.add_creative_assets() here (it requires media_buy_id, assets, today).
            # The creatives are synced to database above and will be uploaded to
            # the ad server during media buy creation when media_buy_id is available.

            # Create updated package with merged creative_ids (immutable)
            existing_ids = pkg.creative_ids or []
            merged_ids = [*existing_ids, *uploaded_ids]
            updated_pkg = pkg.model_copy(update={"creative_ids": merged_ids})
            updated_packages.append(updated_pkg)

            # Track uploads for return value
            uploaded_by_product[product_id] = uploaded_ids

        except (AdCPSalesAgentError, ValidationError):
            # ValidationError travels with the typed errors, not with the adapter
            # failures. It is the buyer's document failing the request SCHEMA, and the
            # transport boundary turns it into INVALID_REQUEST carrying the field and the
            # issues (adcp_error_for tests ValidationError before ValueError, deliberately).
            # Reclassifying it below as AdCPAdapterError would tell the buyer the server is
            # unavailable and to retry an unfixed request. This branch is what replaced the
            # adcp_validation_boundary that used to wrap the builder call: the boundary
            # produced the same envelope, one frame earlier, at the cost of a translation
            # this layer has no business performing.
            raise
        except Exception as e:
            error_msg = f"Failed to upload creatives for package with product_id {product_id}: {str(e)}"
            logger.error(error_msg)
            # Re-raise as ToolError for consistent error handling
            raise AdCPAdapterError() from e

    return updated_packages, uploaded_by_product


# =============================================================================
# URL Extraction Helpers
# =============================================================================
# These functions extract media URLs, click-through URLs, and impression tracker
# URLs from creative data. They are used by both media_buy_create.py and
# creatives.py to ensure consistent URL extraction logic.
# =============================================================================

# Asset types that contain media content with URLs
# Based on AdCP creative agent format specs:
# - image: banner_image, main_image, thumbnail, billboard_image, etc.
# - video: video_file
# - audio: audio_file
# NOT included:
# - url: Used for clickthrough URLs and trackers (url_type field distinguishes them)
# - html/javascript/vast/text: These have 'content' field, not 'url' field
#
# frozen because it is also the ASSET-TYPE FILTER handed to
# ``canonical_slot_asset_ids``, which caches on its arguments.
MEDIA_ASSET_TYPES = frozenset({"image", "video", "audio"})

# Asset types that carry dimensions. Audio does not, so a slot of that type contributes a
# URL and nothing else -- the same split priority 1 has always made, stated once.
SIZED_ASSET_TYPES = frozenset({"image", "video"})

# Known media asset IDs for a creative whose format spec did NOT resolve and whose
# canonical kind declares nothing -- a LEGACY reference the registry could not project.
# Based on AdCP creative agent format specs + common conventions.
#
# THE LAST RESORT, and no longer the only one: a creative identified by its canonical kind
# reads its asset ids off the declaration's slots (priority 2 below), which is what the
# pin actually says they are. This list is the v1-era stand-in for that and MAY ONLY
# SHRINK. Measured against the declaration-derived ids at adcp 6.6.0: the slots name
# ``icon``, ``main_image`` and ``video`` among them, so those three are redundant for any
# creative carrying a kind -- but ``Creative.format_kind`` is nullable ("a legacy reference
# only has a kind once something projects it"), and for a creative with no kind this list
# is still the only path to its media asset. So none of the thirteen is dead yet, and the
# list shrinks when the kindless row does.
MEDIA_ASSET_FALLBACK_IDS = {
    # image assets
    "banner_image",
    "billboard_image",
    "icon",
    "main_image",
    "product_image",
    "screen_image",
    "thumbnail",
    # video assets
    "video_file",
    # audio assets
    "audio_file",
    # common conventions
    "main",
    "image",
    "video",
    "audio",
}

# Common asset IDs for clickthrough URLs
CLICKTHROUGH_ASSET_IDS = {
    "click_url",
    "clickthrough",
    "click",
    "landing_page",
    "landing_url",
    "destination_url",
}

# Common asset IDs for impression trackers
IMPRESSION_TRACKER_ASSET_IDS = {
    "impression_tracker",
    "tracker_pixel",
    "pixel",
    "impression_pixel",
}


def _coerce_dimension(raw: Any, axis: str) -> int | None:
    """One pinned-int read of a creative's declared dimension, or None with the reason said.

    ONE spelling of the coercion, which used to be four: the format-spec branch logged a
    warning on a value it could not read and the allowlist branch swallowed it with a bare
    ``pass``, so the same malformed asset was loud or silent depending on which branch found
    it. A quiet failure here answers the buyer "missing dimensions" and never says that a
    dimension WAS there and was unreadable.
    """
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.warning("Invalid %s in creative assets: %r (type=%s)", axis, raw, type(raw).__name__)
        return None


def _media_asset_candidates(format_spec: Any | None, kind: str | None) -> list[tuple[str, bool]]:
    """Which asset ids could hold this creative's media, in priority order.

    Each entry is ``(asset_id, carries_dimensions)``. THREE sources, and they are tried in
    this order because they differ in how much they actually know:

    1. A resolved LEGACY format spec, which names its own ``asset_id`` values and their
       types. Authoritative for the creative it was resolved for.
    2. The CANONICAL declaration's slots for the kind the creative carries, which
       ``core/product-format-declaration.json`` states and each canonical schema defaults.
       Equally authoritative, and the ONLY source for a creative identified by its kind: it
       asserts no legacy reference, so no spec resolves and there is nothing to ask.
    3. :data:`MEDIA_ASSET_FALLBACK_IDS`, a guess by naming convention. Last, because it is
       a guess -- and before this existed it was the only thing left for a canonical
       creative, which meant its assets were readable by coincidence of naming.

    Sorted within each source so two candidate ids in one creative's assets resolve the same
    way on every run; the sets above are unordered, and which one won used to depend on hash
    iteration.
    """
    # Lazy import to avoid circular dependencies
    from adcp.types import ImageFormatAsset as Assets
    from adcp.utils import get_individual_assets, has_assets

    from src.core.format_satisfaction import canonical_slot_asset_ids

    candidates: list[tuple[str, bool]] = []

    if format_spec is not None and has_assets(format_spec):
        for asset_spec in get_individual_assets(format_spec):
            # Type guard: get_individual_assets only returns individual Assets, not repeatable groups
            if not isinstance(asset_spec, Assets):
                continue
            asset_type = str(asset_spec.asset_type).lower()  # type: ignore[attr-defined]
            if asset_type in MEDIA_ASSET_TYPES:
                candidates.append((asset_spec.asset_id, asset_type in SIZED_ASSET_TYPES))  # type: ignore[attr-defined]

    if kind:
        sized = canonical_slot_asset_ids(kind, SIZED_ASSET_TYPES)
        candidates.extend(
            (asset_id, asset_id in sized) for asset_id in sorted(canonical_slot_asset_ids(kind, MEDIA_ASSET_TYPES))
        )

    # Dimensions assumed present: a convention name says nothing about its asset's type.
    candidates.extend((asset_id, True) for asset_id in sorted(MEDIA_ASSET_FALLBACK_IDS))
    return candidates


def extract_media_url_and_dimensions(
    creative_data: dict[str, Any], format_spec: Any | None, kind: str | None = None
) -> tuple[str | None, int | None, int | None]:
    """Extract media URL and dimensions from creative data.

    All production creatives now use AdCP v2.4+ format with data.assets[asset_id]
    containing typed asset objects per the creative format specification.

    Which asset ids are looked at, and in what order, is :func:`_media_asset_candidates`.
    Whatever those name, the first candidate present in the creative's assets fills each of
    the three fields, and the root-level fallback below fills whatever is still missing.

    Args:
        creative_data: Creative data dict from database
        format_spec: Format specification with assets, when a legacy reference resolved one
        kind: The creative's canonical ``format_kind``, whose declaration names its slots.
            ``None`` for a creative carrying a legacy reference nothing projects -- the one
            row for which the fallback allowlist is still the only path.

    Returns:
        Tuple of (url, width, height). Values are None if not found.

    Note:
        - Media URL extracted from asset types: image, video, audio
        - Dimensions extracted from asset types: image, video
        - Type validation: width/height must be int or coercible to int
        - Uses adcp.utils.get_individual_assets() for backward compatibility with assets_required
    """
    url = None
    width = None
    height = None

    assets = creative_data.get("assets") or {}
    if assets:
        for asset_id, carries_dimensions in _media_asset_candidates(format_spec, kind):
            asset_obj = assets.get(asset_id)
            if not isinstance(asset_obj, dict):
                continue
            if not url and asset_obj.get("url"):
                url = asset_obj["url"]
                logger.debug("Extracted media URL from creative asset %r", asset_id)
            if carries_dimensions:
                width = width or _coerce_dimension(asset_obj.get("width"), "width")
                height = height or _coerce_dimension(asset_obj.get("height"), "height")
            if url and width and height:
                break

    # Last: root-level fields, for simple creatives that carry no assets structure at all.
    if not url:
        root_url = creative_data.get("url")
        if root_url:
            url = root_url
            logger.debug("Extracted media URL from root-level 'url' field (legacy fallback)")

    width = width or _coerce_dimension(creative_data.get("width"), "width")
    height = height or _coerce_dimension(creative_data.get("height"), "height")

    return url, width, height


def extract_click_url(
    creative_data: dict[str, Any],
    format_spec: Any | None,
    apply_macro_substitution: bool = True,
) -> str | None:
    """Extract click-through URL from creative data.

    Extraction priority:
    1. Format spec assets with requirements.url_type == 'clickthrough'
    2. Fallback to known clickthrough asset_id names (click_url, etc.)

    Args:
        creative_data: Creative data dict from database
        format_spec: Format specification with assets
        apply_macro_substitution: If True, apply AdCP-to-GAM macro substitution

    Returns:
        Click-through URL string (optionally with macros substituted), or None if not found.
    """
    # Lazy import to avoid circular dependencies
    from adcp.types import ImageFormatAsset as Assets
    from adcp.utils import get_individual_assets, has_assets

    click_url = None

    # Priority 1: Use format spec to find clickthrough URL (url_type == 'clickthrough')
    if creative_data.get("assets") and format_spec and has_assets(format_spec):
        for asset_spec in get_individual_assets(format_spec):
            if not isinstance(asset_spec, Assets):
                continue
            asset_type = str(asset_spec.asset_type).lower()  # type: ignore[attr-defined]
            if asset_type == "url":
                requirements = getattr(asset_spec, "requirements", None)
                if requirements:
                    req_url_type = None
                    if isinstance(requirements, dict):
                        req_url_type = requirements.get("url_type")
                    elif hasattr(requirements, "url_type"):
                        req_url_type = requirements.url_type
                    if req_url_type == "clickthrough":
                        asset_id = asset_spec.asset_id  # type: ignore[attr-defined]
                        if asset_id in creative_data["assets"]:
                            asset_obj = creative_data["assets"][asset_id]
                            if isinstance(asset_obj, dict) and asset_obj.get("url"):
                                click_url = asset_obj["url"]
                                logger.debug(f"Extracted click URL from format spec asset '{asset_id}'")
                                break

    # Priority 2: Fallback to known clickthrough asset_id names
    if not click_url and creative_data.get("assets"):
        for asset_id in CLICKTHROUGH_ASSET_IDS:
            if asset_id in creative_data["assets"]:
                asset_obj = creative_data["assets"][asset_id]
                if isinstance(asset_obj, dict) and asset_obj.get("url"):
                    click_url = asset_obj["url"]
                    logger.debug(f"Extracted click URL from fallback asset '{asset_id}'")
                    break

    # Apply macro substitution if requested
    if click_url and apply_macro_substitution:
        try:
            from src.adapters.gam.utils.macros import substitute_macros

            click_url = substitute_macros(click_url)
        except ImportError:
            # GAM adapter not available, skip macro substitution
            pass

    return click_url


def extract_impression_tracker_url(creative_data: dict[str, Any], format_spec: Any | None) -> str | None:
    """Extract impression tracker URL from creative data.

    Looks for impression tracker URL in the creative's assets, checking:
    1. Format spec assets with asset_type 'url' AND requirements.url_type == 'tracker_pixel'
    2. Assets with url_type 'tracker_pixel'
    3. Assets with common impression tracker asset_id names

    Args:
        creative_data: Creative data dict from database
        format_spec: Format specification with assets (or deprecated assets_required)

    Returns:
        Impression tracker URL string or None if not found.
    """
    # Lazy import to avoid circular dependencies
    from adcp.types import ImageFormatAsset as Assets
    from adcp.utils import get_individual_assets, has_assets

    tracker_url = None

    # Priority 1: Use format spec to find impression tracker
    # Match url assets where requirements.url_type == 'tracker_pixel'
    if creative_data.get("assets") and format_spec and has_assets(format_spec):
        for asset_spec in get_individual_assets(format_spec):
            if not isinstance(asset_spec, Assets):
                continue
            asset_type = str(asset_spec.asset_type).lower()  # type: ignore[attr-defined]
            if asset_type == "url":
                # Check if this is a tracker_pixel by looking at requirements.url_type
                requirements = getattr(asset_spec, "requirements", None)
                if requirements:
                    req_url_type = None
                    if isinstance(requirements, dict):
                        req_url_type = requirements.get("url_type")
                    elif hasattr(requirements, "url_type"):
                        req_url_type = requirements.url_type
                    # Only match tracker_pixel type
                    if req_url_type == "tracker_pixel":
                        asset_id = asset_spec.asset_id  # type: ignore[attr-defined]
                        if asset_id in creative_data["assets"]:
                            asset_obj = creative_data["assets"][asset_id]
                            if isinstance(asset_obj, dict) and asset_obj.get("url"):
                                tracker_url = asset_obj["url"]
                                logger.debug(f"Extracted impression tracker from format spec asset '{asset_id}'")
                                break

    # Priority 2: Look for assets with tracker_pixel url_type
    if not tracker_url and creative_data.get("assets"):
        for asset_id, asset_obj in creative_data["assets"].items():
            if isinstance(asset_obj, dict):
                url_type = asset_obj.get("url_type", "")
                if url_type == "tracker_pixel" and asset_obj.get("url"):
                    tracker_url = asset_obj["url"]
                    logger.debug(f"Extracted impression tracker from asset '{asset_id}' with url_type='tracker_pixel'")
                    break

    # Priority 3: Check common impression tracker asset_id names
    if not tracker_url and creative_data.get("assets"):
        for asset_id in IMPRESSION_TRACKER_ASSET_IDS:
            if asset_id in creative_data["assets"]:
                asset_obj = creative_data["assets"][asset_id]
                if isinstance(asset_obj, dict) and asset_obj.get("url"):
                    tracker_url = asset_obj["url"]
                    logger.debug(f"Extracted impression tracker from fallback asset '{asset_id}'")
                    break

    return tracker_url


def asset_value_attr(asset: Any, *attr_names: str) -> str | None:
    """Read a named attribute off one asset-slot value, whatever shape it arrived in.

    The library wraps a repeatable slot in an ``Assets`` RootModel holding a
    ``list[AssetVariant]``, each variant itself a RootModel proxying the concrete typed
    asset; a single slot is the concrete asset; a stored row may still hold a plain dict.
    The first truthy value among *attr_names* wins (for example ``"content", "text"``).
    Shared by the sync pipeline and the creative-engine adapters, so it lives here rather
    than inside a tool module.
    """
    if isinstance(asset, dict):
        for attr in attr_names:
            val = asset.get(attr)
            if val:
                return str(val)
        return None

    items = getattr(asset, "root", None)
    if isinstance(items, list) and items:
        first = items[0]
        inner = getattr(first, "root", first)
        for attr in attr_names:
            val = getattr(inner, attr, None) or getattr(first, attr, None)
            if val:
                return str(val)
        return None

    for attr in attr_names:
        val = getattr(asset, attr, None)
        if val:
            return str(val)
    return None

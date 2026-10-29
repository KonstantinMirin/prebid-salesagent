"""Creative input validation: schema and business rule checks."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from adcp.types.canonical_creative import CanonicalFormatKindStr
from adcp.types.legacy import LegacyCreativeAsset as CreativeAsset
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from src.core.errors.details import EntityRefDetails, ValidationDetails
from src.core.exceptions import (
    AdCPFormatNotFoundError,
    AdCPProvenanceDigitalSourceTypeMissingError,
    AdCPProvenanceDisclosureMissingError,
    AdCPProvenanceEmbeddedMissingError,
    AdCPProvenanceRequiredError,
    AdCPValidationError,
)
from src.core.format_resolver import is_dialled_agent_url
from src.core.schemas import (
    Creative,
    CreativePolicy,
    CreativeStatusEnum,
    canonical_agent_url,
)

#: The pinned canonical-kind vocabulary as a validator. Built once: a TypeAdapter compiles
#: its core schema on construction, and this is the only vocabulary check on the sync path.
_CANONICAL_KIND: TypeAdapter[CanonicalFormatKindStr] = TypeAdapter(CanonicalFormatKindStr)

logger = logging.getLogger(__name__)


def _get_field(obj: Any, field: str, default: Any = None) -> Any:
    """Get a field from a model or dict (transitional helper for Phase 1a).

    Removed in Phase 1b when all callers pass typed models.
    """
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _validate_creative_input(
    creative: CreativeAsset,
    registry: Any,
    principal_id: str,
    index: int = 0,
) -> Creative:
    """Validate a CreativeAsset and return a validated Creative model.

    Builds schema_data from the creative model, validates via Creative(**schema_data),
    checks business logic (empty name, missing format), and validates the format_id
    against the creative agent registry.

    Args:
        creative: CreativeAsset model from the sync payload.
        registry: CreativeAgentRegistry instance for format validation.
        principal_id: Authenticated principal ID for ownership.
        index: This creative's position in the request's ``creatives`` array,
            used to build the JSONPath-lite ``field`` carried on a refusal of the
            buyer-supplied ``agent_url`` — a sync may hold up to 100 creatives and
            the refusal message says nothing, so an unindexed path would leave the
            buyer unable to tell WHICH one to fix.

    Returns:
        Validated Creative schema object.

    Raises:
        ValidationError: If the creative fails Pydantic schema validation.
        ValueError: If business logic checks fail (empty name, missing format,
            unknown format, unreachable agent).
    """
    # Create temporary schema object for validation (AdCP v1 spec compliant)
    # Only include AdCP spec fields + internal fields
    # WHICHEVER ARM the buyer used, carried through unchanged. The identity is the one of
    # format_id / format_kind the creative names, and the state mirrors the input -- a
    # creative synced by one arm is listed by that arm -- so neither is translated here.
    # Carrying only format_id made a canonical creative unrepresentable: the receiving
    # model's oneOf refuses a creative with neither identity.
    # ``format_option_ref`` rides with EITHER arm: core/creative-asset.json declares it
    # beside the root oneOf, and neither arm forbids it.
    identity_members: dict[str, Any] = {
        **(
            {"format_id": creative.format_id}
            if creative.format_id is not None
            else {"format_kind": creative.format_kind}
        ),
        "format_option_ref": creative.format_option_ref,
    }
    schema_data: dict[str, Any] = {
        "creative_id": creative.creative_id or str(uuid.uuid4()),
        "name": creative.name,
        **identity_members,
        # Handed through as the model it is. The sync input types the asset map with a
        # different generated ``Assets`` class from the listing model's; the receiving
        # ``Creative.assets`` adopts the sibling instance (see the validator there).
        "assets": creative.assets,
        # Internal fields (added by sales agent)
        "principal_id": principal_id,
        "created_date": datetime.now(UTC),
        "updated_date": datetime.now(UTC),
        "status": CreativeStatusEnum.pending_review.value,
    }

    # Add optional AdCP v1 fields if provided
    # NOTE: creative.inputs is NOT included — Creative model (extra="forbid")
    # doesn't accept it. Processing reads inputs from the original CreativeAsset.
    if creative.tags:
        schema_data["tags"] = creative.tags
    approved = getattr(creative, "approved", None)
    if approved is not None:
        schema_data["approved"] = approved

    # No provenance copy. The listing model this builds declares no ``provenance`` field --
    # the pin declares it on the REQUEST item (core/creative-asset.json) and not on
    # list-creatives-response.json's ``creatives[]`` -- and the only consumer,
    # :func:`check_provenance_policy`, now reads the request item it came from. The persisted
    # document is written from that same request item (``_assets.py``), so nothing that
    # stores or enforces provenance went through here.

    # Validate by creating a Creative schema object
    # This will fail if required fields are missing or invalid (like empty name)
    validated_creative = Creative(**schema_data)

    # Additional business logic validation
    if not creative.name or str(creative.name).strip() == "":
        raise AdCPValidationError(field="name")

    # THE VOCABULARY CHECK, asked of the pinned type directly. This used to build a
    # ``CreativeFormatIdentity`` purely to borrow that type's construction validator -- but
    # this function holds no projection, and the identity's ``kind`` is mandatory, so it was
    # constructing an identity it had no business owning and could no longer supply. The
    # user's ruling on exactly this shape: a function other than the creation path that
    # needs to derive a kind is reading the wrong field.
    #
    # It is still a real check and not redundant, measured rather than assumed:
    # ``Creative.format_kind`` is annotated ``str | None``, so the DTO accepts
    # ``format_kind="not_a_kind"`` and this is the only place on the sync path that refuses
    # it. What the DTO DOES already enforce is the arm exclusivity -- both arms and neither
    # arm are both refused on construction above -- which is the other half the identity
    # construction used to provide here.
    if creative.format_kind is not None:
        try:
            _CANONICAL_KIND.validate_python(creative.format_kind)
        except PydanticValidationError as exc:
            raise AdCPValidationError(
                details=ValidationDetails(rejected_value=str(creative.format_kind)),
                field="format_kind",
            ) from exc

    # The retained assertion, read off the arm the creative carries rather than off an
    # identity. ``format_id`` IS the assertion verbatim; the identity's ``assertion`` member
    # was only ever a copy of it.
    assertion = creative.format_id
    if assertion is None:
        # No retained assertion, so the creative named a KIND from a closed vocabulary rather
        # than a reference to a format some agent hosts. There is no agent to ask: the
        # registry walk below does not apply and the vocabulary check above is the whole of
        # its validation. Asked of the identity rather than by branching on its type —
        # the identity is one shape now, and what varies is whether it retains an assertion.
        #
        # ``assertion`` and not ``legacy``: the two are written together by ``of_legacy`` and
        # are exactly co-null, but this branch needs the REFERENCE's two halves below, and
        # ``legacy`` is one indexable key that is compared whole and never taken apart.
        return validated_creative

    # The retained assertion names a format a creative agent must actually serve. Canonical
    # agent_url, because a comparison requires it and because this is the value that gets
    # dialled — the same form the identity's ``legacy`` key is built from.
    agent_url = canonical_agent_url(assertion.agent_url)
    format_id = assertion.id

    # Skip external validation for adapter-provided formats (non-HTTP URLs)
    # These formats are served by the adapter itself (e.g., broadstreet://default)
    # and validation is handled internally by the adapter
    is_adapter_format = not is_dialled_agent_url(agent_url)

    if not is_adapter_format:
        # Check if the format exists via the SINGLE shared fetch path
        # (format_resolver.fetch_format_spec): a typed AdCPSalesAgentError from the
        # registry (429 -> RATE_LIMITED, 5xx/timeout -> SERVICE_UNAVAILABLE)
        # PROPAGATES with its own recovery semantics — the old bare-except
        # rewrap into AdCPAdapterError made a rate-limited agent look like a
        # creative problem . None = the agent genuinely
        # doesn't expose the format.
        from src.core.format_resolver import fetch_format_spec
        from src.core.security.outbound_http import CounterpartyUrl

        format_spec = fetch_format_spec(
            agent_url, format_id, provenance=CounterpartyUrl(field=f"creatives[{index}].format_id.agent_url")
        )
        if not format_spec:
            # A format_id no agent serves is a REFERENCE that does not resolve, and the
            # pinned enums/error-code.json routes exactly that to REFERENCE_NOT_FOUND
            # ("Generic fallback for a referenced identifier ... that does not exist ...
            # Use when no resource-specific not-found code applies"); VALIDATION_ERROR is
            # for "invalid field values or business rules beyond schema validation", and
            # a well-formed id that simply is not in the catalog is neither. The typed
            # subclass says WHICH kind of reference failed; the wire code is the same.
            raise AdCPFormatNotFoundError(
                details=EntityRefDetails(format_id=format_id),
                field="format_id",
            )
        # TODO(#767): Call validate_creative when available in creative agent spec
        # to validate that creative manifest matches format requirements
    else:
        logger.debug(f"Skipping external validation for adapter-provided format '{format_id}' (agent_url: {agent_url})")

    return validated_creative


def _assets_carry_provenance(creative: CreativeAsset) -> bool:
    """Whether any individual asset declares its own provenance object."""
    for value in (creative.assets or {}).values():
        for asset in value if isinstance(value, list) else [value]:
            inner = getattr(asset, "root", asset)
            if isinstance(inner, dict):
                if inner.get("provenance") is not None:
                    return True
            elif getattr(inner, "provenance", None) is not None:
                return True
    return False


def check_provenance_policy(
    creative: CreativeAsset,
    creative_policy: CreativePolicy | dict | None,
    *,
    creative_id: str,
) -> None:
    """Refuse a creative that does not meet the product's provenance policy.

    core/creative-policy.json: ``provenance_required`` says provenance must be attached, and
    ``provenance_requirements`` refines it -- "Sellers that publish a requirement here MUST
    enforce it on creative submission: a sync_creatives request that omits a required field
    is rejected with the corresponding PROVENANCE_* error code" -- while being ignored
    unless ``provenance_required`` is true. enums/error-code.json: PROVENANCE_REQUIRED is
    "no provenance object on the manifest, on the creative-asset, or on any individual
    asset"; each *_MISSING code is "provenance is present, just missing this specific
    field", inspected on the resolved provenance. All are correctable per-item failures,
    naming in ``field`` the path inspected.

    This used to append a warning and route the creative to review instead. BR-RULE-094's
    "warning" reading lost to the pin, which defines the codes for exactly this refusal.
    The resolved provenance inspected for the *_MISSING checks is the creative-level
    object; a creative carrying provenance only on individual assets satisfies
    ``provenance_required`` and is not inspected field by field here.

    INSPECTS THE REQUEST ITEM, which is where the pin puts the field.
    ``core/creative-asset.json`` -- the sync request's ``creatives[]`` -- declares
    ``provenance``; the listing model (``creatives[]`` of list-creatives-response.json, 28
    properties) does not. This used to take the listing model, so ``_validate_creative_input``
    had to COPY the value from the request item onto a local ``Creative`` subclass that
    declared a non-spec ``provenance`` field purely to carry it two lines -- and the field
    then appeared in the advertised list_creatives shape, where a buyer could not validate
    it. Reading the request item directly deletes the copy, the field and the hand-over.

    ``creative_id`` is passed rather than read off *creative*: the pin makes it OPTIONAL on a
    sync item (the seller assigns one when the buyer omits it), so the refusal would
    otherwise name no creative in exactly the case where a buyer most needs to know which of
    up to 100 items to fix.
    """
    if creative_policy is None:
        return
    # Read off whichever shape arrived. The repository hands back the persisted document
    # for a stored policy and the model for a typed one, and neither is serialized here:
    # a model dumped to inspect one field is a second representation of the same value
    # (CLAUDE.md pattern 4, serialize-only-at-the-edges).
    if not _get_field(creative_policy, "provenance_required"):
        return

    details = EntityRefDetails(creative_id=creative_id)
    provenance = creative.provenance
    if provenance is None:
        if _assets_carry_provenance(creative):
            return
        raise AdCPProvenanceRequiredError(field="provenance", details=details)

    requirements = _get_field(creative_policy, "provenance_requirements") or {}
    if _get_field(requirements, "require_digital_source_type") and provenance.digital_source_type is None:
        raise AdCPProvenanceDigitalSourceTypeMissingError(field="provenance.digital_source_type", details=details)
    if _get_field(requirements, "require_disclosure_metadata"):
        disclosure = provenance.disclosure
        required = getattr(disclosure, "required", None)
        if required is None or (required is True and not getattr(disclosure, "jurisdictions", None)):
            raise AdCPProvenanceDisclosureMissingError(field="provenance.disclosure", details=details)
    if _get_field(requirements, "require_embedded_provenance") and not provenance.embedded_provenance:
        raise AdCPProvenanceEmbeddedMissingError(field="provenance.embedded_provenance", details=details)

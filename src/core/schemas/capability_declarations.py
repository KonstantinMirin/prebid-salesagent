"""Per-tenant AdCP capability declarations (#1592 T1a).

The store behind ``tenants.capability_declarations``: the blocks an operator may
declare and have echoed on ``get_adcp_capabilities``.

STRICT policy (KonstantinMirin's decision, 2026-07-27). A capability posture may be
declared -- and therefore emitted -- ONLY when the implementation backs it. So this
model carries fields for *business facts* the response merely echoes, and has NO
field at all for a *behavioral posture* production does not implement. Naming an
unbacked block is a deployment fault, not a buyer error: it raises
``AdCPConfigurationError`` -> ``CONFIGURATION_ERROR`` (recovery ``terminal``),
naming the block and the issue that will implement it.

Why "no field" rather than "a field we validate": a field that exists but is always
rejected still tempts the next implementer to relax the check. The absence is the
enforcement.

Shape follows ``IdempotencyPosture`` (repositories/idempotency_attempt.py): a typed
model whose ``validate_backing()`` raises ``AdCPConfigurationError`` rather than
silently clamping or emitting a non-conformant response.
"""

from typing import Any

from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import TrustedMatch as LibraryTrustedMatch
from pydantic import BaseModel, ConfigDict, ValidationError

# Blocks the AdCP schema defines but this deployment does NOT back, mapped to the
# GitHub issue that will implement them. Declaring one is rejected by name so the
# operator gets an actionable error instead of pydantic's generic "extra fields
# not permitted". Every entry here is a promise we would otherwise make to buyers
# and could not keep.
#
# RFC 9421 message signing (#1291) gates the whole signing family: request_signing
# and webhook_signing directly, identity because its brand_json_url/key_origins
# subfields exist only to anchor signing keys, and
# content_standards.supports_webhook_delivery / reporting_delivery_methods /
# offline_delivery_protocols because the schema's must_equal_when rule forces
# webhook_signing.supported=true the moment any of them is declared.
_UNBACKED_BLOCKS: dict[str, str] = {
    "request_signing": "#1291 (RFC 9421 request signing is not implemented)",
    "webhook_signing": "#1291 (RFC 9421 webhook signing is not implemented)",
    "identity": "#1291 (identity.brand_json_url/key_origins anchor signing keys we do not publish)",
    "content_standards": "#1291 (supports_webhook_delivery forces webhook_signing.supported=true)",
    "reporting_delivery_methods": "#1291 (declaring [webhook] forces webhook_signing.supported=true)",
    "offline_delivery_protocols": "#1291 (no offline report delivery is implemented)",
}


class TrustedMatchDeclaration(LibraryTrustedMatch):
    """The tenant's deployed TMP surfaces.

    Extends the library type (Pattern #1) so the closed surface enum, uniqueItems
    and minItems come from the SDK rather than being restated here. Presence of the
    object is itself the signal that TMP infrastructure is deployed, which is a
    tenant-side operational fact -- not a protocol behavior this codebase has to
    implement -- so it is declarable under STRICT.
    """


class CapabilityDeclarations(BaseModel):
    """Implementation-backed capability blocks for one tenant.

    ``extra="forbid"`` is unconditional -- deliberately NOT
    ``get_pydantic_extra_mode()``. That helper relaxes to ``ignore`` in production
    for forward compatibility at the BUYER boundary, which is right for inbound
    requests and wrong here: this is operator configuration, and silently dropping
    a block an operator wrote means their declaration never reaches the wire with
    no indication why.
    """

    model_config = ConfigDict(extra="forbid")

    trusted_match: TrustedMatchDeclaration | None = None

    @classmethod
    def from_tenant(cls, declared: Any) -> "CapabilityDeclarations | None":
        """Parse a tenant's stored declarations, or ``None`` when nothing is declared.

        ``None``/empty reproduces the pre-#1592 wire exactly, which is what every
        tenant that never declared anything must keep seeing.
        """
        from src.core.exceptions import AdCPConfigurationError

        if not declared:
            return None
        if not isinstance(declared, dict):
            raise AdCPConfigurationError(
                f"capability_declarations must be a JSON object, got {type(declared).__name__}",
                details={"capability_declarations": repr(declared)},
            )

        # Name unbacked blocks explicitly, before pydantic's generic extra-field
        # error, so the operator learns WHICH promise they cannot keep and where
        # the work is tracked.
        for block in sorted(_UNBACKED_BLOCKS):
            if block in declared:
                raise AdCPConfigurationError(
                    f"capability_declarations.{block} cannot be declared: this deployment does not "
                    f"implement it, and advertising it would promise buyers behavior that does not "
                    f"exist. Tracked by {_UNBACKED_BLOCKS[block]}.",
                    details={"block": block, "tracked_by": _UNBACKED_BLOCKS[block]},
                )

        # ValidationError only -- never a broad `except Exception`, which would
        # flatten any typed AdCPError raised from a nested validator into a
        # generic CONFIGURATION_ERROR and lose its code
        # (guard: test_architecture_no_error_flattening).
        try:
            parsed = cls.model_validate(declared)
        except ValidationError as exc:
            raise AdCPConfigurationError(
                f"capability_declarations is not a valid declaration document: {exc}",
                details={"capability_declarations": sorted(declared)},
            ) from exc

        parsed.validate_backing()
        return parsed

    def validate_backing(self) -> None:
        """Cross-field and platform-backing rules the JSON Schema cannot express.

        Batch A declares only ``trusted_match``, whose every constraint (closed
        surface enum, uniqueItems, minItems) is enforced by the library type, so
        there is nothing left to check here yet. The method exists as the single
        seam later batches extend -- ``measurement`` requires
        ``supported_protocols`` to contain ``measurement``; ``creative_specs`` must
        be a subset of what the bound adapter advertises -- each landing with the
        scenario that grades it, so no rule ever ships ungraded.

        Rule ORDER when the signing family lands under #1291: spec cross-field
        coherence BEFORE platform backing, so an identity rejection still names
        ``brand_json_url`` rather than being pre-empted by a backing error.
        """
        return

"""The signing layer's PUBLIC SURFACE — the one place callers import signing behaviour.

#1291 (``salesagent-z6nr.33``). ``src/core/signing`` owns the application's signing
contract. Where the pinned ``adcp.signing`` is correct the layer delegates; where
upstream has merged a fix the pin lacks, the layer carries a verbatim, provenance-cited
copy (:mod:`src.core.signing._upstream`). The property this surface exists to hold: a
caller can never observe — and never needs to know — which of the two provided a
behaviour, so an SDK bump is a layer-internal event that changes no caller.

Everything below this package is PRIVATE to the layer. Callers import names from
``src.core.signing`` only — never ``src.core.signing.<submodule>``, and never
``adcp.signing`` directly. Both rules are enforced, with empty shrink-only allowlists,
by ``tests/unit/test_architecture_signing_layer_boundary.py``.

The exports are grouped by submodule below; each group is the deliberate public
surface of that unit. Add to these lists consciously — an export is a contract.

Zero hand-rolled crypto anywhere in the layer: key generation, PEM loading, JWK
derivation and signing come from ``adcp.signing``; the layer adds lifecycle,
canonicalization gating and posture on top.

Note: ``adcp.signing`` exports a symbol named ``SigningConfig`` (the SDK's
auto-signing bundle). Ours — :class:`src.core.config.SigningConfig` — is a different
thing. Alias at any import site that touches both.
"""

from src.core.signing._mcp_client_signing_shim import (
    bootstrap_capabilities_for_signed_call,
    sign_scoped_mcp_call,
)
from src.core.signing._upstream.errors import (
    REQUEST_TO_WEBHOOK_CODE,
    WEBHOOK_TARGET_URI_MALFORMED,
)
from src.core.signing.algorithms import (
    MINTABLE_PURPOSES,
    REQUEST_SIGNING,
    SIGNING_ALG_VALUES,
    sql_value_list,
)
from src.core.signing.canonical import (
    REQUEST_TARGET_URI_MALFORMED,
    TargetUriMalformedError,
    canonical_authority,
    canonical_target_uri,
    malformed_authority_reason,
    reject_malformed_target,
)
from src.core.signing.operations import (
    ADCP_SURFACE_PREFIXES,
    is_adcp_surface,
    matches_surface_prefix,
    operation_for_rest_route,
    resolved_operation_names,
    sdk_operation_names,
)
from src.core.signing.posture import (
    IdentityDeclaration,
    KeyBacking,
    RequestSigningPosture,
    WebhookSigningPosture,
    bucket_names,
    emitted_identity,
    origin_is_publishable,
    posture_for_tenant,
    posture_from_declarations,
    request_signing_buckets_declared,
    requires_trust_root,
    signing_key_backed,
    unsupported_webhook_signing_posture,
    webhook_signing_posture,
)
from src.core.signing.revocation_list import build_revocation_list, sign_revocation_list
from src.core.signing.trust_root import (
    CACHE_MAX_AGE_SECONDS,
    build_adagents_json,
    build_brand_json,
    build_jwks,
)

#: Facade names resolved LAZILY (PEP 562) because their module closes an import cycle
#: with a facade consumer. Each entry documents its cycle; add here only for a PROVEN
#: cycle, never for convenience — every other export stays eager and explicit above.
#:
#: * ``request_verifier_middleware`` imports ``src.core.metrics``, and metrics imports
#:   this facade (for the vendored ``REQUEST_TO_WEBHOOK_CODE``).
#: * ``keys`` and ``provider`` import ``src.core.database.models`` at module level, and
#:   models imports this facade (for the algorithm value sets its CHECK constraints
#:   derive from). ``webhook_sender_factory`` imports ``provider`` at module level and
#:   is in the same cycle transitively.
_LAZY_EXPORTS = {
    "RequestSignatureMiddleware": "src.core.signing.request_verifier_middleware",
    "MINTABLE_REF_SCHEMES": "src.core.signing.keys",
    "provision_signing_key": "src.core.signing.keys",
    "clear_signing_provider_cache": "src.core.signing.provider",
    "resolve_signing_material": "src.core.signing.provider",
    "signing_config_from_material": "src.core.signing.provider",
    "adcp_challenge_signer": "src.core.signing.webhook_sender_factory",
    "credential_fingerprint": "src.core.signing.webhook_sender_factory",
    "declared_auth": "src.core.signing.webhook_sender_factory",
    "deliver_adcp_webhook": "src.core.signing.webhook_sender_factory",
    "deliver_adcp_webhook_sync": "src.core.signing.webhook_sender_factory",
    "delivery_auth_mode": "src.core.signing.webhook_sender_factory",
    "send_signed_challenge": "src.core.signing.webhook_sender_factory",
}


def __getattr__(name: str):
    """Resolve the cycle-closing exports on first attribute access (PEP 562)."""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module_path), name)


__all__ = [
    "ADCP_SURFACE_PREFIXES",
    "CACHE_MAX_AGE_SECONDS",
    "IdentityDeclaration",
    "KeyBacking",
    "MINTABLE_PURPOSES",
    "MINTABLE_REF_SCHEMES",
    "REQUEST_SIGNING",
    "REQUEST_TARGET_URI_MALFORMED",
    "REQUEST_TO_WEBHOOK_CODE",
    "RequestSignatureMiddleware",
    "RequestSigningPosture",
    "SIGNING_ALG_VALUES",
    "TargetUriMalformedError",
    "WEBHOOK_TARGET_URI_MALFORMED",
    "WebhookSigningPosture",
    "adcp_challenge_signer",
    "bootstrap_capabilities_for_signed_call",
    "bucket_names",
    "build_adagents_json",
    "build_brand_json",
    "build_jwks",
    "build_revocation_list",
    "canonical_authority",
    "canonical_target_uri",
    "clear_signing_provider_cache",
    "credential_fingerprint",
    "declared_auth",
    "deliver_adcp_webhook",
    "deliver_adcp_webhook_sync",
    "delivery_auth_mode",
    "emitted_identity",
    "is_adcp_surface",
    "malformed_authority_reason",
    "matches_surface_prefix",
    "operation_for_rest_route",
    "origin_is_publishable",
    "posture_for_tenant",
    "posture_from_declarations",
    "provision_signing_key",
    "reject_malformed_target",
    "request_signing_buckets_declared",
    "requires_trust_root",
    "resolved_operation_names",
    "resolve_signing_material",
    "sdk_operation_names",
    "send_signed_challenge",
    "sign_revocation_list",
    "sign_scoped_mcp_call",
    "signing_config_from_material",
    "signing_key_backed",
    "sql_value_list",
    "unsupported_webhook_signing_posture",
    "webhook_signing_posture",
]

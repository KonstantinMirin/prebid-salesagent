"""The three trust-root documents this agent publishes (#1291 A3, salesagent-z6nr.9).

Pure builders — no session, no request, no clock. They take a tenant, ONE
``SigningKeyRepository.publishable_at()`` result, and (for adagents.json) the
authorized-property records that back the claim, and return plain dicts. The
route layer (``src/routes/well_known.py``) owns the reads; this module owns the
SHAPE, which is what the schemas grade.

Two trust roots, two surfaces (AdCP 3.1.1 ``security.mdx``:1105-1111):

* **brand.json -> ``agents[].jwks_uri`` -> JWKS** is authoritative for REQUEST
  signatures and operator-side webhook signatures. This is the chain a verifier
  walks from ``get_adcp_capabilities``' ``identity.brand_json_url``.
* **adagents.json ``authorized_agents[].signing_keys[]``** is a publisher pin,
  authoritative for exactly one tuple — SELL-SIDE webhook delivery. It is not in
  the request-signing chain.

Both are built from the SAME ``publishable_at()`` result, so the pin and the
JWKS cannot drift into disagreeing about which keys exist. One query, two
projections.

**``revoked_at`` travels with the key into BOTH projections.** The schema's
justification for the grace window is that caches which have not yet refreshed
"still find the key and can evaluate the revocation marker". A JWKS entry
WITHOUT the marker is indistinguishable from a live key — and the JWKS is the
document that governs request signing, so omitting it there would leave a
revoked request-signing key silently verifiable for the whole window. Carrying
it is a deliberate SUPERSET of the per-JWK member table at
``security.mdx``:1067-1075: ``core/agent-signing-key.json`` is
``additionalProperties: true`` and RFC 7517 tolerates unknown members, so both
documents stay valid.

The JWK itself is ``row.public_jwk`` VERBATIM — ``adcp.signing.keygen`` already
emits the whole ``{kty, crv, alg, use: "sig", key_ops: ["verify"], adcp_use,
kid, x[, y]}`` table and A2 stores it unmodified. Re-deriving any member here
would be a second opinion about our own key.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from src.core.agent_identity import agent_endpoint_urls, agent_entry_id, canonical_agent_url, jwks_uri
from src.core.signing._rfc3339 import rfc3339

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.core.database.models import AuthorizedProperty, SigningKey, Tenant


_SCHEMA_BASE = "https://adcontextprotocol.org/schemas/3.1.1"

# ``brand_agent_entry.type`` — this agent sells inventory.
_SALES_AGENT_TYPE = "sales"


def _published_jwk(key: SigningKey) -> dict[str, Any]:
    """One published JWK: the stored public JWK, plus its revocation marker.

    The marker is present only for a key inside its grace window, which is the
    only way a revoked key reaches this function at all.
    """
    jwk = dict(key.public_jwk)
    if key.revoked_at is not None:
        jwk["revoked_at"] = rfc3339(key.revoked_at)
    return jwk


def _last_updated(keys: Sequence[SigningKey]) -> str | None:
    """When the published key set last changed, or None when it is empty.

    Derived from the keys rather than from the clock so two GETs of an unchanged
    document return an unchanged document — a ``last_updated`` that moved on
    every request would defeat the caching the ``Cache-Control`` header asks for.
    """
    moments = [moment for key in keys for moment in (key.created_at, key.revoked_at) if moment is not None]
    return rfc3339(max(moments)) if moments else None


def build_jwks(keys: Sequence[SigningKey]) -> dict[str, Any]:
    """The RFC 7517 JWKS served at ``/.well-known/jwks.json``.

    Authoritative for request-signature verification: this is where the
    brand.json hop lands.
    """
    return {"keys": [_published_jwk(key) for key in keys]}


def build_brand_json(tenant: Tenant, keys: Sequence[SigningKey]) -> dict[str, Any]:
    """The "Brand Agent" variant of brand.json for *tenant*.

    ONE ``agents[]`` entry per endpoint we actually serve, because step 5 of the
    discovery algorithm byte-equals the URL whose ``get_adcp_capabilities`` the
    counterparty invoked — and that is an endpoint, never a bare origin. The
    schema blesses this shape explicitly: "Multiple entries with the same type
    are permitted when they have distinct url values, such as one endpoint URL
    per tenant or property scope."

    Choosing this variant costs us ``authorized_operators[]`` (it exists only on
    the House Portfolio variant), which is the eTLD+1 delegation escape hatch of
    ``security.mdx``:1102 step 3. The requirement there is eTLD+1 EQUALITY;
    serving brand.json on the tenant's own host is sufficient and strictly
    stricter, and ``canonical_agent_url`` makes it true by construction.

    *keys* are not published here — brand.json points AT the JWKS rather than
    inlining it — but they date the document, so a counterparty polling
    brand.json can see the key set changed without diffing the JWKS.
    """
    document: dict[str, Any] = {
        "$schema": f"{_SCHEMA_BASE}/brand.json",
        "agents": [
            {
                "type": _SALES_AGENT_TYPE,
                "url": url,
                "id": agent_entry_id(tenant, transport),
                "jwks_uri": jwks_uri(tenant),
                "description": f"{tenant.name} sales agent ({transport.upper()} endpoint)"[:500],
            }
            for transport, url in sorted(agent_endpoint_urls(tenant).items())
        ],
    }
    if last_updated := _last_updated(keys):
        document["last_updated"] = last_updated
    return document


def _property_entry(prop: AuthorizedProperty) -> dict[str, Any]:
    """One ``core/property.json`` object built from an authorized-property record."""
    entry: dict[str, Any] = {
        "property_id": prop.property_id,
        "property_type": prop.property_type,
        "name": prop.name,
        "identifiers": prop.identifiers,
        "publisher_domain": prop.publisher_domain,
    }
    if prop.tags:
        entry["tags"] = list(prop.tags)
    return entry


def build_adagents_json(
    tenant: Tenant,
    keys: Sequence[SigningKey],
    authorizations: Sequence[AuthorizedProperty],
) -> dict[str, Any]:
    """The inline variant of adagents.json for *tenant*.

    *authorizations* are the tenant's existing authorized-property records — the
    document NEVER fabricates one. Fabricating an entry would mean
    self-attesting an authorization no publisher granted, and this file's entire
    purpose is to be a publisher's attestation. With no backing record the
    document claims nothing: an empty ``authorized_agents`` asserts *no sales
    authorization*, which the schema explicitly distinguishes from deny-all,
    authorize-all, and revocation.

    ``authorization_type: "inline_properties"`` carries the property objects on
    the entry itself, so the document is self-contained and needs no top-level
    ``properties[]`` for a consumer to resolve.

    The ``url`` here is the ORIGIN, not an endpoint: ``authorized-agent-base``
    mandates the OTHER comparison rule — "canonicalize both sides ..., not
    byte-equality" — and a canonical-by-construction producer satisfies both
    rules at once.
    """
    document: dict[str, Any] = {"$schema": f"{_SCHEMA_BASE}/adagents.json", "authorized_agents": []}

    if authorizations:
        entry: dict[str, Any] = {
            "authorization_type": "inline_properties",
            "properties": [_property_entry(prop) for prop in authorizations],
            "url": canonical_agent_url(tenant),
            "authorized_for": f"Advertising inventory on properties operated by {tenant.name}"[:500],
        }
        if keys:
            # Same projection as the JWKS — the sell-side-webhook pin and the
            # request-signing trust root describe one key set or our own
            # webhooks get rejected against our own published document.
            entry["signing_keys"] = [_published_jwk(key) for key in keys]
        document["authorized_agents"].append(entry)

    if last_updated := _last_updated(keys):
        document["last_updated"] = last_updated
    return document

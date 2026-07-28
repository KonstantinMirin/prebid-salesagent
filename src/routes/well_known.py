"""The three trust-root documents, served per Host (#1291 A3, salesagent-z6nr.9).

``/.well-known/brand.json``, ``/.well-known/adagents.json`` and
``/.well-known/jwks.json``. Plain GETs, no auth, no signature: these documents
BOOTSTRAP the trust chain, so requiring the signature they exist to let a
verifier check would deadlock every counterparty. (The inbound signature
verifier — B1, salesagent-z6nr.12 — must exempt these three paths for the same
reason.)

Each request resolves its tenant from the Host the way every other host-routed
surface does (:func:`route_landing_page`), then RE-READS that tenant through the
repository layer: the routing result is a dict, and the identity helpers take
the ORM model. One :class:`TrustRootUoW` per request performs all three reads
and builds the document inside the session, so the JWKS and the adagents pin are
projections of ONE ``publishable_at()`` result and cannot disagree about which
keys exist.

Every read is dispatched with ``asyncio.to_thread`` — these are synchronous DB
calls on an async route, and blocking the event loop on an unauthenticated
endpoint is a denial-of-service surface.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from src.core.agent_identity import ADAGENTS_JSON_PATH, BRAND_JSON_PATH, JWKS_PATH, agent_origin_host
from src.core.config import get_config
from src.core.database.models import AuthorizedProperty, SigningKey, Tenant
from src.core.database.repositories.uow import TrustRootUoW
from src.core.domain_routing import route_landing_page
from src.core.signing.trust_root import (
    CACHE_MAX_AGE_SECONDS,
    build_adagents_json,
    build_brand_json,
    build_jwks,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# A builder takes everything a trust-root document can need and returns the
# document. Passing the builder in (rather than returning the three loaded
# collections) keeps every ORM read inside the session that owns it.
DocumentBuilder = Callable[[Tenant, Sequence[SigningKey], Sequence[AuthorizedProperty]], dict[str, Any]]


def _build_document(tenant_id: str, build: DocumentBuilder) -> dict[str, Any] | None:
    """Load everything a trust-root document needs and build it, in one session.

    Returns None when the tenant cannot be re-read — a deletion between routing
    and this read. Synchronous by design; the caller hands it to a thread.
    """
    with TrustRootUoW(tenant_id) as uow:
        assert uow.tenant_config is not None
        assert uow.signing_keys is not None
        assert uow.authorized_properties is not None

        tenant = uow.tenant_config.get_tenant()
        if tenant is None:
            return None

        grace_seconds = get_config().signing.grace_seconds
        keys = uow.signing_keys.publishable_at(now=datetime.now(UTC), grace_seconds=grace_seconds)
        # An adagents.json served at OUR host speaks for the properties on that
        # host — never for properties a publisher hosts elsewhere, whose own
        # adagents.json is the document a verifier consults. A tenant whose
        # agent host is not a property domain therefore claims nothing here.
        properties = uow.authorized_properties.list_for_publisher_domain(agent_origin_host(tenant))

        return build(tenant, keys, properties)


async def _serve(request: Request, build: DocumentBuilder) -> JSONResponse:
    """Resolve the Host's tenant, build its document, and answer with our cache TTL.

    The published ``max-age`` is a contract, not a hint: the revocation grace
    window is derived from it (``SigningConfig.grace_seconds``), and an
    intermediary inventing its own TTL can mask a rotation.
    """
    routing = await asyncio.to_thread(route_landing_page, dict(request.headers))
    if not routing.tenant:
        logger.info("[TRUST-ROOT] no tenant for host %s", routing.effective_host)
        raise HTTPException(status_code=404, detail="Not found")

    tenant_id = routing.tenant["tenant_id"]
    document = await asyncio.to_thread(_build_document, tenant_id, build)
    if document is None:
        # Routing resolved a tenant id the repository cannot re-read — a
        # deletion between the two reads. 404 rather than 500: there is no
        # trust root at this host.
        logger.warning("[TRUST-ROOT] tenant %s vanished between routing and read", tenant_id)
        raise HTTPException(status_code=404, detail="Not found")

    return JSONResponse(document, headers={"Cache-Control": f"public, max-age={CACHE_MAX_AGE_SECONDS}"})


@router.get(BRAND_JSON_PATH)
async def brand_json(request: Request) -> JSONResponse:
    """The brand.json a verifier reaches from ``identity.brand_json_url``.

    Hop 2 of the discovery algorithm: it carries the ``agents[]`` entry whose
    ``url`` byte-equals the endpoint the counterparty invoked, and that entry's
    ``jwks_uri``.
    """
    return await _serve(request, lambda tenant, keys, _properties: build_brand_json(tenant, keys))


@router.get(ADAGENTS_JSON_PATH)
async def adagents_json(request: Request) -> JSONResponse:
    """The publisher-pin document for properties on this host.

    Its ``signing_keys[]`` is authoritative for SELL-SIDE webhook delivery only
    — request signatures are governed by brand.json's ``jwks_uri``. Both are
    built from the same key set so the two cannot drift.
    """
    return await _serve(request, build_adagents_json)


@router.get(JWKS_PATH)
async def jwks_json(request: Request) -> JSONResponse:
    """The RFC 7517 key set that governs request-signature verification."""
    return await _serve(request, lambda _tenant, keys, _properties: build_jwks(keys))

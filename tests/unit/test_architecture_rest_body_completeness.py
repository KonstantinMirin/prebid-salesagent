"""Structural guard: REST *Body models forward every field their raw wrapper accepts.

The REST transport (src/routes/api_v1.py) exposes each AdCP tool via a ``*Body``
Pydantic model that the route forwards field-by-field into the tool's raw
wrapper. If a ``Body`` omits a parameter the raw wrapper accepts, REST buyers
silently lose that capability — FastAPI never binds an undeclared field, so the
value is dropped before it reaches the wrapper. That is the disease fixed in the
buyer-facing REST parity work (UpdateMediaBuyBody dropped packages;
SyncCreativesBody dropped account, etc.).

This guard fails if any field-by-field Body drops a raw-wrapper parameter that is
not explicitly allowlisted with a justification.

Scope: only the field-by-field forwarding routes. The ``req=req`` routes
(creative_formats, authorized_properties, accounts, sync_accounts) build the
request from ``body.model_dump()`` and forward everything by construction, so
they cannot exhibit this disease and are out of scope.
"""

from __future__ import annotations

import inspect

from src.core.tools.creatives.listing import list_creatives_raw
from src.core.tools.creatives.sync_wrappers import sync_creatives_raw
from src.core.tools.media_buy_create import create_media_buy_raw
from src.core.tools.media_buy_delivery import get_media_buy_delivery_raw
from src.core.tools.media_buy_update import update_media_buy_raw
from src.core.tools.performance import update_performance_index_raw
from src.routes.api_v1 import (
    CreateMediaBuyBody,
    GetMediaBuyDeliveryBody,
    ListCreativesBody,
    SyncCreativesBody,
    UpdateMediaBuyBody,
    UpdatePerformanceIndexBody,
)

# Raw-wrapper parameters that are transport plumbing, never buyer-facing body fields.
# Server-injected plumbing, never buyer-supplied body fields: ctx/identity are
# resolved at the transport boundary; raw_wire_payload is the raw wire request
# body captured server-side for idempotency hashing (FastAPI raw_json_body dependency).
_TRANSPORT_PARAMS = {"ctx", "identity", "raw_wire_payload"}
# Body-only meta field (not a raw-wrapper param). ``adcp_version`` here is a
# REST-only response-shape compat pin (see apply_version_compat) that predates
# and is NOT the same field as the raw wrappers' AdCP request-envelope
# ``adcp_version`` (AdcpVersionEnvelope) — confirmed by their incompatible
# formats: this one defaults to full semver "1.0.0", while the spec field is
# pattern-constrained to VERSION.RELEASE (e.g. "3.1") and rejects "1.0.0"
# outright. Forwarding body.adcp_version into the raw wrapper's adcp_version
# param was tried and reverted (salesagent-xg5w.1) — it broke every REST
# create/update/sync/list call with a VALIDATION_ERROR. Real fix needs a
# non-colliding REST field for the buyer's AdCP version pin; tracked below via
# the per-class allowlist entries until that lands.
_BODY_META = {"adcp_version"}

# Allowlisted omissions: {BodyClassName: {param_name: justification}}.
# Allowlists can only SHRINK — every entry needs a real reason, never a blanket escape.
# All 5 "adcp_version" entries below share one root cause: the REST Body's
# pre-existing adcp_version field (a response-shape compat pin) collides in
# name and format with the raw wrappers' new AdCP request-envelope adcp_version
# param (salesagent-xg5w.1) -- forwarding one into the other breaks every call.
# Tracked for a real fix (non-colliding field) at salesagent-xg5w.10; remove
# these 5 entries when that lands.
_ADCP_VERSION_COLLISION = (
    "REST Body's adcp_version is a pre-existing response-compat pin (format '1.0.0'), "
    "not the raw wrapper's AdCP request-envelope adcp_version (format 'VERSION.RELEASE', "
    "e.g. '3.1') -- forwarding one into the other rejects with VALIDATION_ERROR. "
    "salesagent-xg5w.10 tracks a non-colliding REST field for the real fix."
)

_ALLOWLIST: dict[str, dict[str, str]] = {
    "UpdateMediaBuyBody": {
        # media_buy_id is the URL path parameter (/media-buys/{media_buy_id}),
        # resolved by FastAPI from the path — legitimately not a body field.
        "media_buy_id": "URL path parameter, not a body field",
        # update_media_buy_raw accepts these in its signature but DROPS them before
        # _build_update_request (which has no targeting_overlay/creatives params), so
        # exposing them on the body would be a silent no-op. Remove from this allowlist
        # once the raw wrapper actually plumbs them through.
        "targeting_overlay": "raw wrapper accepts but drops before _build_update_request",
        "creatives": "raw wrapper accepts but drops before _build_update_request",
        "adcp_version": _ADCP_VERSION_COLLISION,
    },
    "CreateMediaBuyBody": {"adcp_version": _ADCP_VERSION_COLLISION},
    "GetMediaBuyDeliveryBody": {"adcp_version": _ADCP_VERSION_COLLISION},
    "SyncCreativesBody": {"adcp_version": _ADCP_VERSION_COLLISION},
    "ListCreativesBody": {"adcp_version": _ADCP_VERSION_COLLISION},
}

# Each field-by-field REST Body paired with the raw wrapper its route forwards into.
_PAIRS = [
    (CreateMediaBuyBody, create_media_buy_raw),
    (UpdateMediaBuyBody, update_media_buy_raw),
    (GetMediaBuyDeliveryBody, get_media_buy_delivery_raw),
    (SyncCreativesBody, sync_creatives_raw),
    (ListCreativesBody, list_creatives_raw),
    (UpdatePerformanceIndexBody, update_performance_index_raw),
]


def _raw_param_names(fn) -> set[str]:
    """Named keyword/positional parameters of a raw wrapper, minus transport plumbing."""
    return {
        name
        for name, p in inspect.signature(fn).parameters.items()
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) and name not in _TRANSPORT_PARAMS
    }


def test_rest_bodies_forward_all_raw_wrapper_params():
    """Every field-by-field REST Body must declare every param its raw wrapper accepts."""
    violations = []
    for body_cls, raw_fn in _PAIRS:
        body_fields = set(body_cls.model_fields) - _BODY_META
        allow = set(_ALLOWLIST.get(body_cls.__name__, {}))
        missing = _raw_param_names(raw_fn) - body_fields - allow
        if missing:
            violations.append(f"  {body_cls.__name__} drops {sorted(missing)} accepted by {raw_fn.__name__}()")
    assert not violations, (
        "REST Body models drop parameters their raw wrappers accept — REST buyers lose these "
        "fields silently. Add them to the Body and forward them in the route, or allowlist with "
        "a justification:\n" + "\n".join(violations)
    )


def test_rest_body_allowlist_has_no_stale_entries():
    """Allowlist entries must be real raw-wrapper params still missing from the Body.

    Keeps the allowlist shrinking: once a field is added to its Body (or removed from
    the raw wrapper), its allowlist entry must be deleted.
    """
    pairs_by_name = {body_cls.__name__: (body_cls, raw_fn) for body_cls, raw_fn in _PAIRS}
    stale = []
    for body_name, entries in _ALLOWLIST.items():
        body_cls, raw_fn = pairs_by_name[body_name]
        raw_params = _raw_param_names(raw_fn)
        body_fields = set(body_cls.model_fields) - _BODY_META
        for param in entries:
            if param not in raw_params:
                stale.append(f"  {body_name}.{param}: not a parameter of {raw_fn.__name__}()")
            elif param in body_fields:
                stale.append(f"  {body_name}.{param}: now declared on the Body — remove from allowlist")
    assert not stale, "Stale REST-body allowlist entries:\n" + "\n".join(stale)

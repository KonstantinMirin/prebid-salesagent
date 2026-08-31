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
(creative_formats, authorized_properties, accounts, sync_accounts) forward everything by
construction, so they cannot exhibit this disease and are out of scope for the LAG check.
They are still graded, because they are all DERIVED now and the intersection test below
covers every derived body wherever its route forwards.

The lag check alone was never enough. It compares a body against its RAW WRAPPER, so it
only ever notices a field the wrapper names and the body does not; a field the DTO declares
under a spelling the wrapper does not take is invisible to it, which is how ``sort`` stayed
absent from the old ListCreativesBody. Every body in api_v1 is therefore graded against
``DTO fields INTERSECT impl parameters`` by one of two tests -- the intersection test for
generated bodies, ``test_hand_written_bodies_carry_the_derived_field_set`` for the four that
cannot be generated -- and ``test_every_hand_written_body_is_either_derived_or_graded``
refuses to let a new hand-written class escape both.
"""

from __future__ import annotations

import inspect

from src.core.schemas import (
    CreateMediaBuyRequest,
    GetMediaBuyDeliveryRequest,
    GetMediaBuysRequest,
    UpdateMediaBuyRequest,
)
from src.core.tools.creatives.listing import list_creatives_raw
from src.core.tools.creatives.sync_wrappers import sync_creatives_raw
from src.core.tools.media_buy_create import create_media_buy_raw
from src.core.tools.media_buy_delivery import get_media_buy_delivery_raw
from src.core.tools.media_buy_list import get_media_buys_raw
from src.core.tools.media_buy_update import update_media_buy_raw
from src.core.tools.performance import update_performance_index_raw
from src.routes.api_v1 import (
    CreateMediaBuyBody,
    GetMediaBuyDeliveryBody,
    GetMediaBuysBody,
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
# Body-only meta field (not a raw-wrapper param).
_BODY_META = {"adcp_version"}

# Allowlisted omissions: {BodyClassName: {param_name: justification}}.
# Allowlists can only SHRINK — every entry needs a real reason, never a blanket escape.
_ALLOWLIST: dict[str, dict[str, str]] = {
    "UpdateMediaBuyBody": {
        # media_buy_id is the URL path parameter (/media-buys/{media_buy_id}),
        # resolved by FastAPI from the path — legitimately not a body field.
        "media_buy_id": "URL path parameter, not a body field",
        # targeting_overlay / creatives were allowlisted here while update_media_buy_raw
        # accepted them and dropped them before _build_update_request. Both parameters are
        # now GONE from the raw wrapper (prkv.5 D7): AdCP 3.1.1 declares them on
        # media-buy/package-update.json, not on update-media-buy-request.json, so a
        # request-level parameter advertised a no-op. Entries deleted rather than
        # re-worded -- there is no divergence left to allow.
    },
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
    """A HAND-WRITTEN REST Body must declare every param its raw wrapper accepts.

    A DERIVED body (``derived_body_model``) is graded by the intersection rule instead, in
    the test below. It deliberately declares LESS than the wrapper accepts: the wrapper's
    non-spec parameters are exactly what it drops, and requiring them here would demand REST
    advertise fields AdCP 3.1.1 does not define.
    """
    violations = []
    for body_cls, raw_fn in _PAIRS:
        if getattr(body_cls, "__derived_from_dto__", None) is not None:
            continue
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


#: Bodies that CANNOT be generated by ``derived_body_model`` but must still carry exactly the
#: derived FIELD SET. Each row is (Body, DTO, impl, extra_names, reason). ``extra_names`` are
#: fields the body carries that the DTO does not declare -- non-spec flat aliases the impl
#: really honours -- and every one of them must be a parameter of ``impl``, which the test
#: below checks, so the escape cannot be used to smuggle in a field nothing reads.
#:
#: The exemption buys permissive TYPES (or a legacy alias), never a missing field: without
#: this list a hand-written body is graded by nothing but the raw-wrapper comparison above,
#: which is a LAG check -- it never notices a body that is missing a field the DTO declares
#: and the impl accepts under a different spelling, and it is what let ``sort`` go absent
#: from the old ListCreativesBody while every other transport carried it.
_HAND_WRITTEN_GRADED: list[tuple[type, type, object, frozenset[str], str]] = [
    (
        CreateMediaBuyBody,
        CreateMediaBuyRequest,
        create_media_buy_raw,
        frozenset(),
        "packages/start_time/end_time must stay wire-shaped so CreateMediaBuyRequest, not "
        "FastAPI, produces the graded rejection",
    ),
    (
        UpdateMediaBuyBody,
        UpdateMediaBuyRequest,
        update_media_buy_raw,
        frozenset({"flight_start_date", "flight_end_date", "currency", "pacing", "daily_budget"}),
        "five flat aliases _build_update_request folds into the spec-nested fields; they are "
        "not UpdateMediaBuyRequest fields but the MCP wrapper announces all five",
    ),
    (
        GetMediaBuyDeliveryBody,
        GetMediaBuyDeliveryRequest,
        get_media_buy_delivery_raw,
        frozenset(),
        "account/status_filter stay permissive so the shared AdCP boundary, not FastAPI, "
        "grades them -- which is what the A2A handler does for the same payload",
    ),
    (
        GetMediaBuysBody,
        GetMediaBuysRequest,
        get_media_buys_raw,
        frozenset(),
        "media_buy_ids/status_filter stay Any so _build_get_media_buys_request grades them "
        "(pinned by test_request_validation_failed[rest])",
    ),
]


def test_hand_written_bodies_carry_the_derived_field_set():
    """A body that cannot be DERIVED must still carry the field set derivation would give.

    Being un-derivable is a statement about TYPES, not about which fields exist. A body
    exempted for typing reasons that then quietly loses a field is the original disease
    wearing an exemption, so the set is computed here from the same two artifacts the
    generator uses -- ``DTO fields INTERSECT impl parameters`` -- and compared exactly.
    """
    import inspect

    for body_cls, dto, impl, extras, _reason in _HAND_WRITTEN_GRADED:
        assert getattr(body_cls, "__derived_from_dto__", None) is None, (
            f"{body_cls.__name__} is derived now -- move it out of _HAND_WRITTEN_GRADED so the "
            f"intersection test grades it instead."
        )
        expected = (set(dto.model_fields) & set(inspect.signature(impl).parameters)) | set(extras)
        # media_buy_id travels in the URL path on the update route, never in the body.
        expected -= set(_ALLOWLIST.get(body_cls.__name__, {}))
        actual = set(body_cls.model_fields) - _BODY_META
        assert actual == expected, (
            f"{body_cls.__name__} carries {sorted(actual - expected)} beyond, and is missing "
            f"{sorted(expected - actual)} from, (DTO fields INTERSECT {impl.__name__} parameters)"
            f"{' + ' + str(sorted(extras)) if extras else ''}."
        )


def test_hand_written_extra_names_are_really_accepted_by_the_impl():
    """A non-DTO field on an exempted body must be a parameter the impl actually takes.

    Otherwise ``extra_names`` becomes a way to keep advertising an input whose only outcome
    is nothing happening -- the inverse of the rule the derivation enforces.
    """
    import inspect

    for body_cls, _dto, impl, extras, _reason in _HAND_WRITTEN_GRADED:
        params = set(inspect.signature(impl).parameters)
        unaccepted = sorted(name for name in extras if name not in params)
        assert not unaccepted, (
            f"{body_cls.__name__} declares {unaccepted}, which {impl.__name__}() does not "
            f"accept -- REST would advertise an input that reaches nothing."
        )


def test_every_hand_written_body_is_either_derived_or_graded():
    """No ``*Body`` in api_v1 may be hand-written AND ungraded.

    The two escapes are exhaustive by construction: a body is generated by
    ``derived_body_model`` (and graded by the intersection test), or it is listed in
    ``_HAND_WRITTEN_GRADED`` with a reason (and graded by the test above). A new
    hand-written class added to api_v1.py lands in neither and fails here, which is the
    point -- it is exactly how the 11 hand-maintained field lists accumulated.
    """
    from src.routes import api_v1

    graded = {body_cls.__name__ for body_cls, *_ in _HAND_WRITTEN_GRADED}
    ungraded = sorted(
        name
        for name, obj in vars(api_v1).items()
        if name.endswith("Body")
        and isinstance(obj, type)
        and obj.__module__ == api_v1.__name__
        and getattr(obj, "__derived_from_dto__", None) is None
        and name not in graded
    )
    assert not ungraded, (
        f"Hand-written REST bodies with no grading: {ungraded}. Generate them with "
        f"derived_body_model(), or add a row to _HAND_WRITTEN_GRADED naming why the DTO's "
        f"annotations cannot reach the wire."
    )


def test_derived_bodies_carry_exactly_the_dto_fields_the_impl_accepts():
    """A derived body IS ``DTO fields INTERSECT impl parameters`` -- graded, not assumed.

    This is the invariant that makes REST drift-proof, and e2e_rest with it: e2e is real
    HTTP against this same route and has no schema of its own. If the generator ever stops
    intersecting -- carrying a non-spec field, or dropping an implemented one -- REST starts
    disagreeing with MCP and this fails.
    """
    import inspect

    checked = 0
    for body_cls, _raw_fn in _PAIRS:
        derived = getattr(body_cls, "__derived_from_dto__", None)
        if derived is None:
            continue
        dto, impl = derived
        expected = set(dto.model_fields) & set(inspect.signature(impl).parameters)
        actual = set(body_cls.model_fields) - _BODY_META - {"adcp_version"}
        checked += 1
        assert actual == expected, (
            f"{body_cls.__name__} carries {sorted(actual ^ expected)} outside "
            f"(DTO fields INTERSECT {impl.__name__} parameters)."
        )
    assert checked, "no derived REST body found -- the generator is not in use, so this grades nothing"

"""Shared dispatch helper for BDD domain step definitions.

Provides a single implementation of the transport-aware dispatch pattern
used across UC-004, UC-011, and future domain step files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

from tests.harness.transport import NO_IDENTITY_OVERRIDE, Transport

if TYPE_CHECKING:
    from tests.harness._base import WireError
    from tests.harness.transport import TransportResult

# NOTE: NO_IDENTITY_OVERRIDE is IMPORTED, never re-declared. A local
# `_SENTINEL = object()` renamed into this name would be a SECOND distinct
# object wearing the canonical name, and `identity is not NO_IDENTITY_OVERRIDE`
# would then compare against the local one — so a caller passing the harness's
# real sentinel (meaning "no override") would be misread as HAVING overridden
# identity. One object, one name.


class WireCtx(TypedDict, total=False):
    """What a WIRE dispatch may publish into ``ctx``, and with what types.

    The type that made the defect possible was ``ctx`` itself: an unowned dict slot
    with no invariant, written from two step modules and read hundreds of times.
    Naming the shape closes the WRITE at typecheck, which no runtime trap can -- a
    sentinel object only fires when something READS it, and readers that merely test
    ``is not None`` or format ``type(x).__name__`` slip past silently
    (salesagent-3dawm.15).

    ``total=False`` because a dispatch publishes the success keys or the error key,
    never both.

    There is deliberately NO ``response`` key. A provenance-stripped copy of the
    payload cannot tell a Then whether it is reading a wire fact or an in-process
    reconstruction — which is how a self-grading transport stayed green — and the
    key had three writers with three meanings. Steps read the dispatch's own
    ``TransportResult`` through ``tests/bdd/steps/_outcome_helpers.py``'s
    ``require_payload`` / ``payload_or_none``; modules whose When calls production
    directly stash under the explicitly-named ``ctx["self_dispatched_response"]``,
    which those accessors know by name. Enforced by
    ``test_architecture_bdd_wire_discipline``'s Check D (empty allowlist).
    """

    result: TransportResult
    wire_response: dict[str, Any]
    wire_error_envelope: dict[str, Any]
    #: The CARRIER, never a production error class. On a wire transport a failed
    #: dispatch raises ``WireError``, which holds the envelope verbatim; typing the
    #: slot as that carrier is what makes
    #:
    #:     ctx["error"] = AdCPValidationError(field="x")
    #:
    #: a mypy error rather than a convention someone must remember not to break.
    #: That is exactly the subject test_architecture_bdd_wire_discipline's Check A
    #: detects today, closed here at the type instead of watched for.
    #:
    #: The key is still PUBLISHED because ~40 step sites reach the envelope through
    #: it (``_wire_of(error)`` reads ``error.envelope``). Dropping it outright is a
    #: READER migration, not a recorder change -- measured: doing it without
    #: migrating them first costs 41 UC-006 failures.
    error: WireError


def _populate_ctx_from_result(ctx: WireCtx, result: TransportResult) -> None:
    """Project a ``TransportResult`` into ``ctx``. The SINGLE writer.

    Every dispatch path routes through here — :func:`dispatch_request` via
    ``env.call_via``, :func:`dispatch_via_client` via ``AdCPTestClient.call``,
    and ``when_request._call_via`` — so no two step modules can disagree about
    what a scenario may read after a dispatch. They did disagree: ``when_request``
    published neither ``ctx["result"]`` nor ``ctx["wire_error_envelope"]``, so
    every scenario routed through it had no object to call
    ``result.assert_wire_error(...)`` on, and the Error Verification Policy's
    prescribed assertion was literally unreachable there (salesagent-3dawm.18).
    ``ctx['result']`` is the key with exactly one producer; leaving it unset
    silently downgrades the wire-first Then steps (``then_error.py``'s
    ``_wire_code`` / ``_wire_suggestion`` / ``_wire_error_object``) to the lossy
    reconstructed ``ctx['error']`` fallback.

    Both branches are projected here, not just the error branch. Unifying only
    the error branch would leave the success branch with two writers — the same
    divergence one level down.
    """
    # Expose the normalized TransportResult so Then-steps can use the
    # harness-provided, transport-independent assertions (result.assert_wire_error)
    # instead of hand-rolling envelope parsing.
    ctx["result"] = result
    if result.is_error:
        # BDD dispatches on a WIRE transport only (IMPL was dropped from the default
        # parametrization, #1417), so a failed dispatch here is always the WireError
        # carrier -- never a production class rebuilt from wire bytes, which is what
        # this slot used to hold.
        ctx["error"] = cast("WireError", result.error)
        # Capture the REAL wire envelope only (A2A/REST/MCP) so Then steps can
        # assert the two-layer AdCP shape per the Error Verification Policy. This
        # is a passthrough copy of the field, not a second implementation of the
        # accessor's guard/fallback logic — which is why
        # ``test_architecture_bdd_wire_discipline``'s Check E names this module as
        # one of the two sanctioned direct readers of the field. Steps that need
        # the guarded reading still go through ``_outcome_helpers``'
        # ``wire_error_dict`` / ``wire_error_envelope_or_none``, whose source of
        # truth is ``ctx["result"]``.
        #
        # The synthesized envelope is deliberately NOT published: copying it into
        # ctx let a step write `ctx.get("wire_error_envelope") or
        # ctx.get("synthesized_error_envelope")` and thereby reinstate exactly
        # the fallback McpDispatcher refuses (tests/harness/dispatchers.py —
        # "a dead MCP wire path must yield None here"). The dataclass field
        # TransportResult.synthesized_error_envelope still exists for the
        # integration suites that legitimately grade the envelope BUILDER.
        # None-safe; an absent key means "no envelope".
        if result.wire_error_envelope is not None:
            ctx["wire_error_envelope"] = result.wire_error_envelope
        return

    # Success path. Written as an early return above rather than an ``else``:
    # each branch publishes its own key CONDITIONALLY, so an absent key means
    # "this dispatch captured no such wire" on both sides of the split.
    #
    # Propagate the real serialized success-path wire body so Then steps
    # can assert on what the buyer actually receives (ctx["wire_response"]),
    # not the reconstructed typed payload (REST HTTP body; A2A/MCP artifact
    # only when the env routes through _run_a2a_handler/_run_mcp_client).
    # None on IMPL / non-stashing envs; the wire_field() helper guards
    # against silent tautologies (#1417). See tests/CLAUDE.md
    # "TransportResult.wire_response".
    if result.wire_response is not None:
        ctx["wire_response"] = result.wire_response


def _as_transport(ctx: dict, caller: str) -> Transport:
    """Read ``ctx['transport']`` as a :class:`Transport`. The SINGLE normalizer.

    ``ctx["transport"]`` is *usually* already the enum — the ``ctx`` fixture
    injects it that way (``tests/bdd/conftest.py``, "gets a fresh dict with
    ``ctx['transport']`` set to the Transport enum"). But three step modules
    overwrite it with a STRING mid-scenario (``given_auth.py`` with ``"mcp"``,
    ``uc010_capabilities.py`` with ``"MCP"``/``"A2A"``, ``uc011_accounts.py``
    with ``"A2A"``), and the two spellings differ in case.

    ``dispatch_request`` grew an inline map for that and ``dispatch_via_client``
    did not, so the client seam raised ``KeyError``/``NoAddressForTransport`` on
    exactly the scenarios that re-assign the key — a latent trap that only fires
    once a string-assigning module is migrated onto the client. Normalizing in
    ONE place means the two dispatch entry points cannot disagree about what the
    key may hold (CLAUDE.md DRY invariant).

    A missing transport is a WIRING BUG, not an IMPL fallback: BDD dispatches on
    a wire transport only (IMPL was dropped from the default parametrization,
    #1417), so fail loudly rather than silently bypassing the wire.
    """
    transport = ctx.get("transport")
    if transport is None:
        raise RuntimeError(
            f"{caller}: ctx['transport'] is unset. BDD scenarios must dispatch "
            "through a wire transport (a2a/mcp/rest); the IMPL call_impl fallback was removed."
        )
    if isinstance(transport, Transport):
        return transport
    if isinstance(transport, str):
        try:
            # Transport values are lowercase ("a2a"/"mcp"/"rest"/"e2e_rest"), so
            # casefolding covers both the "mcp" and "MCP" spellings in use without
            # a hand-maintained alias map that a new member would silently miss.
            return Transport(transport.lower())
        except ValueError as exc:
            raise RuntimeError(f"{caller}: unrecognized wire transport {transport!r}") from exc
    raise RuntimeError(f"{caller}: ctx['transport'] is neither a Transport nor a str: {transport!r}")


def dispatch_request(ctx: dict, *, identity: Any = NO_IDENTITY_OVERRIDE, **kwargs: Any) -> None:
    """Dispatch a request through ctx['transport'] via ``env.call_via``.

    Stores the TransportResult in ctx["result"]; ctx["error"] on failure.
    If ctx["transport"] is a Transport enum, uses call_via directly.
    If it's a string, maps to Transport enum first.

    The ``identity`` kwarg overrides the default identity for multi-agent
    and no-auth scenarios. When provided, it flows through to call_via
    (which uses kwargs.setdefault, so an explicit identity won't be clobbered).
    Use ``identity=None`` for no-auth scenarios.
    """
    if identity is not NO_IDENTITY_OVERRIDE:
        kwargs["identity"] = identity

    env = ctx["env"]
    transport = _as_transport(ctx, "dispatch_request")
    try:
        result = env.call_via(transport, **kwargs)
        _populate_ctx_from_result(cast("WireCtx", ctx), result)
    except Exception as exc:
        # NOT a wire rejection: env.call_via itself blew up, so nothing reached a
        # transport and there is no envelope to publish. That is a genuinely different
        # outcome from "the buyer received an error", which is why WireCtx has no
        # `error` key of this type and this write lives outside it (salesagent-3dawm.15).
        ctx["error"] = exc


def dispatch_via_client(ctx: dict, tool: str, payload: dict[str, Any], *, identity: Any = NO_IDENTITY_OVERRIDE) -> None:
    """Dispatch through ``AdCPTestClient.call`` instead of ``env.call_via``.

    The same single dispatch seam reached through the transport-generic client
    (``tests/harness/client.py``, whose module docstring states the design), for
    scenarios wired onto it — one scenario, one request model, four transports.
    Publishes the ctx contract through the same
    :func:`_populate_ctx_from_result`, so every wire-first Then step works
    unmodified regardless of which entry point the When used.

    Deliberately does NOT wrap ``client.call()`` in a blanket
    ``except Exception`` the way ``dispatch_request`` does for
    ``env.call_via``: ``AdCPTestClient.call`` already converts ordinary
    transport errors into an error ``TransportResult`` internally, and
    re-raises ``NotImplementedError`` / lets ``NoAddressForTransport``
    propagate on purpose — a harness wiring gap must surface as a hard
    failure, not get silently downgraded into ``ctx["error"]`` where
    ``then_operation_fails`` would mistake it for a real AdCP rejection
    (client.py's own anti-vacuity comment on ``call()``).
    """
    client = ctx["client"]
    transport = _as_transport(ctx, "dispatch_via_client")
    if identity is not NO_IDENTITY_OVERRIDE:
        result = client.call(tool, payload, transport, identity=identity)
    else:
        result = client.call(tool, payload, transport)
    _populate_ctx_from_result(cast("WireCtx", ctx), result)

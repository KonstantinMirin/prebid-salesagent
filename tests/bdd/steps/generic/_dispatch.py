"""Shared dispatch helper for BDD domain step definitions.

Provides a single implementation of the transport-aware dispatch pattern
used across UC-004, UC-011, and future domain step files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tests.harness.transport import TransportResult

_SENTINEL = object()


def record_transport_result(ctx: dict, result: TransportResult) -> None:
    """Project a ``TransportResult`` into ``ctx``. The SINGLE writer.

    Every wire dispatch routes through here — :func:`dispatch_request` below and
    ``when_request._call_via`` — so the two step modules cannot disagree about
    what a scenario may read after a dispatch. They did disagree: ``when_request``
    published neither ``ctx["result"]`` nor ``ctx["wire_error_envelope"]``, so
    every scenario routed through it had no object to call
    ``result.assert_wire_error(...)`` on, and the Error Verification Policy's
    prescribed assertion was literally unreachable there (salesagent-3dawm.18).

    Both branches are projected here, not just the error branch. Unifying only
    the error branch would leave the success branch with two writers — the same
    divergence one level down.
    """
    # Expose the normalized TransportResult so Then-steps can use the
    # harness-provided, transport-independent assertions (result.assert_wire_error)
    # instead of hand-rolling envelope parsing.
    ctx["result"] = result
    if result.is_error:
        ctx["error"] = result.error
        # Capture the REAL wire envelope only (A2A/REST/MCP) so Then steps can
        # assert the two-layer AdCP shape per the Error Verification Policy.
        # The synthesized envelope is deliberately NOT published here: copying
        # it into ctx let a step write `ctx.get("wire_error_envelope") or
        # ctx.get("synthesized_error_envelope")` and thereby reinstate exactly
        # the fallback McpDispatcher refuses (tests/harness/dispatchers.py —
        # "a dead MCP wire path must yield None here"). The dataclass field
        # TransportResult.synthesized_error_envelope still exists for the
        # integration suites that legitimately grade the envelope BUILDER.
        # None-safe; an absent key means "no envelope".
        ctx["wire_error_envelope"] = result.wire_error_envelope
    else:
        ctx["response"] = result.payload
        # Propagate the real serialized success-path wire body so Then steps
        # can assert on what the buyer actually receives (ctx["wire_response"]),
        # not the reconstructed typed payload (REST HTTP body; A2A/MCP artifact
        # only when the env routes through _run_a2a_handler/_run_mcp_client).
        # None on IMPL / non-stashing envs; the wire_field() helper guards
        # against silent tautologies (#1417). See tests/CLAUDE.md
        # "TransportResult.wire_response".
        ctx["wire_response"] = result.wire_response


def dispatch_request(ctx: dict, *, identity: Any = _SENTINEL, **kwargs: Any) -> None:
    """Dispatch a request through ctx['transport'] via call_via, or direct call_impl.

    Stores result in ctx["response"] on success, ctx["error"] on failure.
    If ctx["transport"] is a Transport enum, uses call_via directly.
    If it's a string, maps to Transport enum first.
    If absent, falls back to call_impl.

    The ``identity`` kwarg overrides the default identity for multi-agent
    and no-auth scenarios. When provided, it flows through to call_via
    (which uses kwargs.setdefault, so an explicit identity won't be clobbered).
    Use ``identity=None`` for no-auth scenarios.
    """
    if identity is not _SENTINEL:
        kwargs["identity"] = identity

    transport = ctx.get("transport")
    env = ctx["env"]
    # BDD dispatches on a wire transport only (IMPL was dropped from the default
    # parametrization, #1417). A missing transport is a wiring bug, not
    # an IMPL fallback — fail loudly rather than silently bypassing the wire.
    if transport is None:
        raise RuntimeError(
            "dispatch_request: ctx['transport'] is unset. BDD scenarios must dispatch "
            "through a wire transport (a2a/mcp/rest); the IMPL call_impl fallback was removed."
        )

    from tests.harness.transport import Transport

    if isinstance(transport, Transport):
        pass  # Already a Transport enum — use as-is
    elif isinstance(transport, str):
        transport_map = {
            "MCP": Transport.MCP,
            "mcp": Transport.MCP,
            "A2A": Transport.A2A,
            "a2a": Transport.A2A,
            "REST": Transport.REST,
            "rest": Transport.REST,
        }
        if transport not in transport_map:
            raise RuntimeError(f"dispatch_request: unrecognized wire transport {transport!r}")
        transport = transport_map[transport]
    try:
        result = env.call_via(transport, **kwargs)
        record_transport_result(ctx, result)
    except Exception as exc:
        ctx["error"] = exc

"""Transport enum and TransportResult for multi-transport behavioral tests.

Defines the seven dispatch transports (IMPL, A2A, REST, MCP + E2E variants)
and a frozen result container that separates transport-specific envelope from
shared payload.

Usage::

    result = env.call_via(Transport.REST, creatives=[...])
    assert result.is_success
    assert result.payload.creatives[0].action == CreativeAction.created
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from tests.helpers import pinned_schema


@functools.lru_cache(maxsize=1)
def _pinned_error_metadata() -> dict[str, dict[str, str]]:
    """code -> {recovery, suggestion} from the installed SDK's error-code enum.

    Only the ``recovery`` field is actually read by this module (assert_wire_error
    below) — verified safe to source from the SDK tree: the SDK's enum is a
    strict superset of the older vendored fixture (92 vs 64 codes, fixture-only
    set empty) and its ``recovery`` classification is IDENTICAL across every one
    of the 64 shared codes (0 divergences). ``suggestion`` DOES diverge on 4
    codes between the two sources — but this module never reads that field
    (extract_wire_suggestion below reads the WIRE's own suggestion text, not
    this metadata), so that divergence has no effect here. Consumers that DO
    grade ``suggestion`` content (test_architecture_error_suggestion_enum_conformance.py)
    stay on the vendored fixture — see docs/adcp-spec-version.md "Pinned schema sources"
    (which also cites the command to reproduce the 64-code fixture count).
    """
    return pinned_schema.load("error-code.json")["enumMetadata"]


def extract_wire_suggestion(envelope: dict | None) -> str | None:
    """The buyer-facing ``suggestion`` from a two-layer AdCP wire error envelope.

    STRICT error.json conformance: ``suggestion`` is a top-level sibling of
    code/message/field/retry_after/recovery on the error object (in either the
    ``errors[0]`` or the envelope-level ``adcp_error`` layer). A suggestion
    buried in the free-form ``details`` dict is NOT at the protocol position
    and deliberately does not satisfy this lookup — emitters that bury it are
    conformance bugs the harness must surface, not mask (#1417).
    Single source of truth for both ``TransportResult.assert_wire_error`` and
    the BDD ``_wire_suggestion`` step (#1417). Returns ``None`` when
    there is no envelope (IMPL / no-wire).
    """
    if not envelope:
        return None
    errors = envelope.get("errors") or [{}]
    adcp_error = envelope.get("adcp_error") or {}
    return errors[0].get("suggestion") or adcp_error.get("suggestion")


class Transport(StrEnum):
    """Dispatch transports for behavioral tests."""

    IMPL = "impl"  # Direct _impl() call
    A2A = "a2a"  # _raw() A2A wrapper
    REST = "rest"  # FastAPI TestClient → route → _raw() → _impl()
    MCP = "mcp"  # Mock Context → MCP wrapper → _impl()
    E2E_REST = "e2e_rest"  # Real HTTP via httpx → nginx → server
    E2E_MCP = "e2e_mcp"  # Real MCP via httpx → nginx → server (placeholder)
    E2E_A2A = "e2e_a2a"  # Real A2A via httpx → nginx → server (placeholder)


# Maps Transport → ResolvedIdentity.protocol value
TRANSPORT_PROTOCOL: dict[Transport, str] = {
    Transport.IMPL: "mcp",  # _impl doesn't inspect protocol; keep default
    Transport.A2A: "a2a",
    Transport.REST: "rest",
    Transport.MCP: "mcp",
    Transport.E2E_REST: "rest",
    Transport.E2E_MCP: "mcp",
    Transport.E2E_A2A: "a2a",
}


@dataclass(frozen=True)
class E2EConfig:
    """Configuration for E2E transport dispatch.

    Attributes:
        base_url: Docker stack URL (e.g., ``http://localhost:8092``). Stays
            PLAINTEXT — 487 bdd_e2e and 95 e2e tests target it and do not move.
        postgres_url: Docker PostgreSQL URL for factory data writes.
        tls_base_url: The SECOND origin the same stack serves, over real TLS at a
            dotted host (e.g. ``https://proxy.adcp.test:8443``). ``None`` when the
            stack publishes no TLS listener. Additive: only scenarios that need a
            real handshake read it (salesagent-tgzb).
        ca_bundle: ABSOLUTE path to the CA that signed the stack's leaf. Absolute
            because pytest does not always run from the repo root. ``None`` when
            there is no TLS listener to verify.
    """

    base_url: str
    postgres_url: str
    tls_base_url: str | None = None
    ca_bundle: str | None = None


@dataclass(frozen=True)
class TransportResult:
    """Normalized result from any transport dispatch.

    Attributes:
        payload: Pydantic response model (shared assertions target this).
        envelope: Transport-specific metadata (HTTP status, ToolResult, etc.).
        error: Exception raised during dispatch, if any.
        raw_response: Unprocessed transport response (httpx.Response, ToolResult, etc.).
        wire_response: Serialized success-path response body as a dict, captured
            from the real wire (REST HTTP JSON body, MCP structured_content, A2A
            artifact DataPart). ``None`` on error and on IMPL (no wire — serialize
            the typed ``payload`` instead). Lets success-path tests assert the
            actual serialized shape (e.g. the v3.1 format_id federation contract).
        wire_error_envelope: Raw two-layer error envelope dict captured from
            the actual wire bytes (REST HTTP body, MCP ToolError content text,
            A2A failed-Task artifact DataPart). ``None`` on success or on the
            IMPL transport, which has no wire. This is the canonical field
            for error verification — see ``tests/CLAUDE.md`` § Error
            Verification Policy.
        has_wire: Whether these bytes crossed a REAL wire, declared by the
            dispatcher AT CONSTRUCTION. Positive and required — never inferred
            at a read site from which transport enum happens to be in play,
            because that inference breaks (or, worse, silently reclassifies)
            the day ``Transport.IMPL`` is removed.

            REQUIRED and keyword-only, deliberately: a default would make
            omission mean "no wire", so a forgetful new dispatcher would send
            readers down the re-serialize path and a wire-shape assertion would
            pass green against a ``model_dump`` — the silent tautology the wire
            readers exist to raise on. Omitting it is a ``TypeError`` instead.

            Declared PER SITE, not per transport class: it is True only where
            the construction is downstream of an actual send/receive. A wire
            dispatcher's "missing config" guard constructs a result for a request
            that never left. Its catch-all ``except`` arm is a STRADDLE — it may
            fire before OR after bytes moved, and cannot tell which — so it
            declares False, because claiming a wire that may not exist is the
            failure mode that matters here: it would send a reader looking for a
            capture nothing produced.

            ``has_wire=True`` with ``wire_response is None`` on a success path
            means the env failed to STASH the wire. That is a harness bug to
            raise on loudly; it must never fall back to serializing the typed
            payload, which would assert nothing about the wire.

            SCOPE — this predicate governs the SUCCESS path only, and
            deliberately does NOT feed ``assert_wire_error``'s no-envelope
            diagnostic (which lane salesagent-gra7.4 originally specified).
            The reason is concrete: a dispatcher's catch-all arm declares
            ``has_wire=False`` because it may fire before anything was sent, yet
            it can still derive a ``wire_error_envelope`` from the exception —
            ``A2ADispatcher``'s does exactly that. Wiring ``has_wire`` into that
            diagnostic would therefore report a genuine wire rejection as "no
            wire", which is worse than the message it replaces. Error-path
            wire-presence needs its own per-site declaration; that is not this
            lane's, and inventing one here would be the same identity-inference
            mistake in a new spelling.
        _synthesized_error_envelope: Two-layer envelope produced by
            ``build_two_layer_error_envelope`` against the IMPL-caught
            ``AdCPError`` — what production WOULD emit at the boundary.
            ``None`` on success and on REST/MCP/A2A (those expose the real
            wire envelope above instead). PRIVATE: read it through
            :meth:`error_envelope`, which is the only place allowed to decide
            that this value may stand in for a wire. A test that reads it
            directly verifies the envelope-builder contract against itself —
            production and the harness compute it from the same in-memory
            exception — so a regression in the boundary translator cannot be
            caught that way. Use REST/MCP/A2A for wire-shape regressions.
    """

    payload: BaseModel | None = None
    envelope: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None
    raw_response: Any = None
    wire_response: dict[str, Any] | None = None
    wire_error_envelope: dict[str, Any] | None = None
    _synthesized_error_envelope: dict[str, Any] | None = None
    has_wire: bool = field(kw_only=True)

    @property
    def is_success(self) -> bool:
        return self.error is None and self.payload is not None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def error_envelope(self) -> dict[str, Any]:
        """The two-layer error envelope this dispatch produced. Raises if there is none.

        Three branches, spelled out because getting them wrong is this lane's
        whole subject:

        1. a captured wire envelope is present -> return it;
        2. no wire was captured AND the dispatcher declared no wire AND a
           synthesized envelope exists -> return the synthesized one;
        3. otherwise -> RAISE.

        Branch 2 is reachable only on IMPL, and NOT because ``has_wire`` says
        so. ``has_wire`` is ``False`` on every A2A, MCP and IMPL error — a
        catch-all may fire before anything was sent — so keying on it alone
        would hand back a rebuilt envelope on transports that HAVE a wire, and
        on A2A and MCP it would discard a real captured one. What actually
        isolates IMPL is that IMPL is the only dispatcher that populates the
        synthesized field at all. That single-producer invariant is the load
        bearing one, and it is pinned by
        ``tests/unit/test_harness_mcp_never_synthesizes.py``.

        Branch 3 covers the case every operand is ``None`` — an A2A catch-all
        that derived nothing. Falling back to re-serializing the typed payload
        there would assert nothing about the wire while looking green, which is
        the tautology this reader exists to prevent.
        """
        envelope = self.error_envelope_or_none()
        assert envelope is not None, (
            "Expected an error envelope, but none was captured "
            f"(is_error={self.is_error}, payload={self.payload!r}). The operation either "
            "succeeded or errored before reaching a transport."
        )
        return envelope

    def error_envelope_or_none(self) -> dict[str, Any] | None:
        """:meth:`error_envelope`, returning ``None`` instead of raising.

        For the callers that branch on envelope-presence as CONTROL FLOW rather
        than reading it — an MCP dispatch can fail with a ``ToolError`` that is
        genuinely not an AdCP envelope, and collapsing that branch would turn a
        correct assertion into an error. The success path already ships this
        same pair: ``_wire_or_none`` returns ``None`` for a declared no-wire
        while ``wire_field``/``wire_dict`` raise. Prefer the raising one.
        """
        if isinstance(self.wire_error_envelope, dict):
            return self.wire_error_envelope
        if not self.has_wire and isinstance(self._synthesized_error_envelope, dict):
            return self._synthesized_error_envelope
        return None

    def assert_wire_error(
        self,
        code: str,
        *,
        recovery: str | None = None,
        require_suggestion: bool = False,
        message_substr: str | None = None,
    ) -> None:
        """Assert this result carries the AdCP two-layer wire error ``code``.

        Transport-independent: reads the normalized ``wire_error_envelope`` the
        dispatcher captured for whatever transport produced this result, so the
        same call holds on a2a/mcp/rest. Recovery defaults to the PINNED AdCP
        enum's classification for ``code`` (pin-wins), making the assertion
        non-vacuous without per-scenario duplication. This is the single
        harness-provided way to verify an error on the wire — step definitions
        must not hand-roll envelope parsing.
        """
        from tests.helpers import assert_envelope_shape

        meta = _pinned_error_metadata()
        spec = meta.get(code)
        assert spec is not None, (
            f"{code!r} is not a canonical AdCP error code (pinned error-code.json). "
            "Reconcile the feature to a canonical code."
        )
        expected_recovery = recovery if recovery is not None else spec["recovery"]

        envelope = self.wire_error_envelope
        assert envelope is not None, (
            f"Expected a wire rejection with {code}, but no wire_error_envelope was captured "
            f"(is_error={self.is_error}, payload={self.payload!r}). The operation either "
            "succeeded or errored before reaching a transport."
        )
        assert_envelope_shape(envelope, code, recovery=expected_recovery, message_substr=message_substr)
        if require_suggestion:
            suggestion = extract_wire_suggestion(envelope)
            assert suggestion, f"Expected a non-empty suggestion in the {code} wire envelope: {envelope}"

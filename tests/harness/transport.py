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
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from tests.helpers import pinned_schema


@functools.lru_cache(maxsize=1)
def _pinned_error_metadata() -> dict[str, dict[str, str]]:
    """code -> {recovery, suggestion} from the installed SDK's error-code enum.

    The SDK tree is the single source of truth for schema SHAPE
    (``tests/helpers/pinned_schema.py``). Sourcing this enum from it rather than
    from the vendored ``tests/fixtures/adcp_schemas_pinned/`` copy is a no-op on
    every field any consumer reads: measured 2026-08-12, the two trees carry the
    same 92 enum codes and 93 ``enumMetadata`` entries, with ZERO ``recovery``
    and ZERO ``suggestion`` divergences. They are not byte-identical — the
    ``$id`` differs, each naming its own tree — so the vendored copy is retained
    deliberately as an INDEPENDENT pin (docs/adcp-spec-version.md "Pinned schema
    sources"), not as a second source of shape.

    Only ``recovery`` is read here (see ``assert_wire_error``);
    ``extract_wire_suggestion`` below reads the WIRE's own suggestion text, not
    this metadata. Consumers that grade ``suggestion`` CONTENT
    (test_architecture_error_suggestion_enum_conformance.py) stay on the
    vendored fixture — see docs/adcp-spec-version.md "Pinned schema sources".
    """
    return pinned_schema.load("error-code.json")["enumMetadata"]


def is_pinned_error_code(code: str | None) -> bool:
    """Whether ``code`` is a canonical AdCP error code in the pinned enum.

    The guard an outcome-dispatch step needs BEFORE calling
    :meth:`TransportResult.assert_wire_error`: that method hard-fails on a code
    production cannot emit (a scenario-only code like ``DOMAIN_INVALID_FORMAT``),
    so a step whose scenarios can carry one must route those through a
    reconstructed-exception branch instead of the wire assertion.

    EMITTABILITY, not spec membership. The question is CODE_TABLE membership —
    "can production put this code on the wire at all" — not "is this code in the
    pinned spec enum". Those diverged when the code rewriters were deleted: the
    AdCP error vocabulary is OPEN (core/error.json: ``error.code`` is a wire-typed
    string, published codes are documentary, senders MAY emit codes outside the
    set), so a platform code like ``MEDIA_BUY_REJECTED`` now reaches the buyer
    unrewritten and IS assertable on the wire. Keeping the pinned-enum question
    here would silently route every platform-coded wire error to the lossy
    reconstruction branch. Same source as ``assert_wire_error``, so the two never
    disagree on what "emittable" means.
    """
    from src.core.errors.codes import CODE_TABLE

    return code is not None and code in CODE_TABLE


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

    A2A = "a2a"  # _raw() A2A wrapper
    REST = "rest"  # FastAPI TestClient → route → _raw() → _impl()
    MCP = "mcp"  # Mock Context → MCP wrapper → _impl()
    E2E_REST = "e2e_rest"  # Real HTTP via httpx → nginx → server
    E2E_MCP = "e2e_mcp"  # Real MCP via httpx → nginx → server (placeholder)
    E2E_A2A = "e2e_a2a"  # Real A2A via httpx → nginx → server (placeholder)


# Maps Transport → ResolvedIdentity.protocol value
TRANSPORT_PROTOCOL: dict[Transport, str] = {
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
        base_url: Docker stack URL (e.g., ``http://localhost:8092``).
        postgres_url: Docker PostgreSQL URL for factory data writes.
    """

    base_url: str
    postgres_url: str


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
            wire envelope above instead). Tests asserting on this field
            verify the envelope-builder contract, NOT the wire shape — a
            regression in the production boundary translator would not be
            caught here. Use REST/MCP/A2A for wire-shape regressions.
    """

    payload: BaseModel | None = None
    envelope: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None
    raw_response: Any = None
    wire_response: dict[str, Any] | None = None
    wire_error_envelope: dict[str, Any] | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None and self.payload is not None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def wire_error_object(self) -> dict[str, Any] | None:
        """The payload-layer error object (``errors[0]``) from the captured wire.

        The sanctioned READER for the error region. It exists because the harness
        previously published only assertions plus a raw envelope dict, leaving a
        step that needed the code, message or details with nothing to call — so
        every module hand-rolled ``(envelope.get("errors") or [{}])[0]`` its own
        way. Resolves through the single locator in
        ``tests/helpers/envelope_assertions.py``, so reader and assertion can
        never disagree about where the spec puts a field.

        Tolerant: ``None`` when no wire envelope was captured. Callers that must
        NOT tolerate that use :meth:`assert_wire_error` or
        :meth:`wire_error_details`.
        """
        from tests.helpers import locate_envelope_error

        return locate_envelope_error(self.wire_error_envelope)

    def error_code(self) -> str | None:
        """The error code for THIS result, whatever transport produced it.

        The wire envelope when there is one; otherwise the in-process exception's own
        ``error_code``. Both are legitimate: on a wire transport the envelope is what
        the buyer received, and on IMPL there is no wire at all -- the raised
        ``AdCPError`` IS the product, and its code comes from CODE_TABLE.

        What this deliberately does NOT do is rebuild a production error class from
        wire bytes to make the two look alike; that reconstruction is gone
        (salesagent-3dawm.15). Use this where a test is parametrized ACROSS
        transports including IMPL; use ``assert_wire_error`` where the scenario is
        specifically about the buyer-facing envelope.
        """
        wire = self.wire_error_code()
        if wire is not None:
            return wire
        code = getattr(self.error, "error_code", None)
        return str(code) if code is not None else None

    def wire_error_code(self) -> str | None:
        """``errors[0].code`` from the captured wire, or ``None`` with no wire."""
        error = self.wire_error_object()
        return error.get("code") if error else None

    def wire_error_details(self, code: str, *, recovery: str | None = None) -> Mapping[str, Any]:
        """The ``errors[0].details`` block, AFTER asserting the envelope carries ``code``.

        The escape hatch for oracles that cannot be expressed as an equality
        subset (non-empty array; every entry matches a regex; membership) — and
        it is deliberately STRONGER than the ``details=`` kwarg, not a way around
        it: taking the expected ``code`` means a details block from the wrong
        error is unreadable. Without that, an oracle grades the details of
        whatever envelope happened to be captured.

        Required-not-optional: raises if there is no wire envelope or no details
        block, so a caller never has to ``None``-check what the spec guarantees.
        """
        self.assert_wire_error(code, recovery=recovery)
        error = self.wire_error_object() or {}
        details = error.get("details")
        assert isinstance(details, dict), (
            f"expected a details object at errors[0].details for {code}, got {details!r}: {self.wire_error_envelope}"
        )
        return details

    def assert_wire_error(
        self,
        code: str,
        *,
        recovery: str | None = None,
        require_suggestion: bool = False,
        field: str | None = None,
        details: Mapping[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Assert this result carries the AdCP two-layer wire error ``code``.

        Transport-independent: reads the normalized ``wire_error_envelope`` the
        dispatcher captured for whatever transport produced this result, so the
        same call holds on a2a/mcp/rest. Recovery defaults to the PINNED AdCP
        enum's classification for ``code`` (pin-wins), making the assertion
        non-vacuous without per-scenario duplication. This is the single
        harness-provided way to verify an error on the wire — step definitions
        must not hand-roll envelope parsing.

        ``field`` pins ``errors[0].field``, the error.json pointer naming WHICH
        request field was rejected, and ``details`` subset-checks
        ``errors[0].details``. They are kwargs here rather than separate
        wire_error_field()/wire_error_details() assertions on purpose: one
        sanctioned error surface means a step never has to decide which
        mechanism to reach for.
        """
        from src.core.errors.codes import CODE_TABLE
        from tests.helpers import assert_envelope_shape

        entry = CODE_TABLE.get(code)
        assert entry is not None, (
            f"{code!r} is not an emittable error code (absent from CODE_TABLE, so no raise site "
            "can put it on the wire). Reconcile the feature to a code production can emit."
        )
        # CODE_TABLE, not the pinned spec enum: the vocabulary is OPEN and platform codes reach
        # the buyer unrewritten, so the default must come from the one table that classifies
        # every emittable code rather than from the spec subset.
        expected_recovery = recovery if recovery is not None else entry.recovery.value

        envelope = self.wire_error_envelope
        assert envelope is not None, (
            f"Expected a wire rejection with {code}, but no wire_error_envelope was captured "
            f"(is_error={self.is_error}, payload={self.payload!r}). The operation either "
            "succeeded or errored before reaching a transport."
        )
        assert_envelope_shape(
            envelope,
            code,
            recovery=expected_recovery,
            field=field,
            details=details,
            retry_after=retry_after,
        )
        if require_suggestion:
            # Presence, not equality: error.json defines `suggestion` as free-form
            # remediation text with no enumMetadata tie — unlike its sibling
            # `recovery`, whose enum relationship the schema does spell out. The
            # spec's own worked examples emit site-specific wording that differs
            # from the enum default, so pinning the text would grade the emitter's
            # prose rather than the contract.
            #
            # BOTH mirrored layers by name (#1547 item 3): an either-layer check
            # (`errors[0].get(...) or adcp_error.get(...)`) lets an emitter that
            # populates one layer satisfy every call site in the suite, making the
            # only defect this assertion exists to catch — the mirror breaking —
            # invisible.
            for layer, error in (("adcp_error", envelope["adcp_error"]), ("errors[0]", envelope["errors"][0])):
                assert error.get("suggestion"), (
                    f"{layer} carries no buyer-facing suggestion for {code}; the spec places the "
                    f"hint at the top level of the error object: {envelope}"
                )

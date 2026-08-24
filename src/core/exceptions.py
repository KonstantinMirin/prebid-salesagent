"""AdCP exception hierarchy for typed error handling across transport layers.

Business logic raises these exceptions. Transport layers (A2A, MCP, REST)
translate them to their protocol's error format via registered handlers.

Exception classes define the error vocabulary — transport layers format them.
Each exception carries a recovery classification (transient/correctable/terminal)
to help buyer agents decide whether to retry, fix, or abandon a request.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from adcp.server.helpers import adcp_error
from adcp.types import ErrorCode
from pydantic import BaseModel, ValidationError

from src.core.errors.codes import CODE_TABLE, AppErrorCode, CodeEntry, ErrorCodeT

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from adcp.types import ContextObject

logger = logging.getLogger(__name__)

RecoveryHint = Literal["transient", "correctable", "terminal"]

# ---------------------------------------------------------------------------
# Error codes on the wire
# ---------------------------------------------------------------------------
# There is ONE classifier: ``CODE_TABLE`` in src/core/errors/codes.py, loaded from
# the pinned enums/error-code.json (92 published codes) plus this platform's own
# ``AppErrorCode`` members (12) = 104. The SDK's ``STANDARD_ERROR_CODES`` is a
# cross-check, never the authority, and is consulted only as a message fallback.
#
# Every code a raise site declares reaches the buyer VERBATIM: the AdCP error
# vocabulary is OPEN, so there is no translation at the transport boundary and no
# server-only set. Message, recovery and suggestion are all functions of the code
# (see docs/decisions/adr-010-graded-wire-fields-are-functions-of-the-code.md), so a
# raise site cannot make one of them disagree with the pin.


def advisory_recovery_for(code: str) -> RecoveryHint:
    """Recovery classification for a hand-built ``errors[]`` advisory.

    A LOOKUP in :data:`CODE_TABLE`, the single authority for what a code means to
    a buyer -- all 104 of them, spec and platform alike.

    It used to read a second hand-maintained table, and its raise was documented as
    UNREACHABLE by construction because a now-deleted collapse rewrote anything
    unmapped to ``SERVICE_UNAVAILABLE`` before the value arrived. Deleting that
    collapse falsified the closed world: a platform-coded advisory would have
    raised KeyError inside an ``_impl``. CODE_TABLE covers every code a raise site
    can name, so the hole closes without reintroducing a rewrite.

    The raise STAYS, and it is no longer decorative: an ad-hoc advisory string is
    still expressible, and a few former INTERNAL_CODES entries (``API_ERROR``,
    ``FLIGHT_NOT_FOUND``, ``API_UPDATE_FAILED``) are absent from CODE_TABLE. A
    silent default here would put an unclassified code on the buyer's wire.
    """
    # CODE_TABLE is keyed by the ErrorCode/AppErrorCode StrEnums; both compare equal to
    # their string values at runtime, but the Mapping's declared key type is the union, so
    # a plain str needs the cast to satisfy the checker.
    return cast(RecoveryHint, _advisory_entry_for(code).recovery.value)


def _advisory_entry_for(code: str) -> CodeEntry:
    """The table entry an advisory code resolves to, or KeyError naming the code.

    ONE lookup and ONE raise, shared by the recovery and suggestion fills in
    the advisory recovery lookup. Two independent lookups would duplicate both.
    """
    # CODE_TABLE is keyed by the ErrorCode/AppErrorCode StrEnums; both compare equal to
    # their string values at runtime, but the Mapping's declared key type is the union, so
    # a plain str needs the cast to satisfy the checker.
    entry = CODE_TABLE.get(cast("ErrorCodeT", code))
    if entry is None:
        raise KeyError(
            f"No recovery classification for error code {code!r}: it is absent from CODE_TABLE, "
            "so no raise site can emit it. Name a code the table classifies."
        )
    return entry


def _serialize_context(
    context: ContextObject | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Serialize an AdCP ContextObject (or dict) into a JSON-safe dict.

    Single source of truth for context serialization — used by ``to_dict``,
    ``to_adcp_error``, and ``build_two_layer_error_envelope`` so all three
    paths emit byte-identical context payloads.

    Behavior:
        - ``None`` → ``None`` (caller decides whether to omit the key).
        - ``dict`` → shallow copy. Prevents aliasing footguns when one
          serialization layer mutates its copy and accidentally mutates
          the source context still held on the exception.
        - ``ContextObject`` → ``model_dump(mode="json", exclude_none=True)``.
          ``mode="json"`` coerces datetimes/UUIDs/etc. to JSON-serializable
          primitives; ``exclude_none=True`` matches the spec's emit-only-
          populated-fields norm.
        - anything else → log a warning and return ``None``. This is reached
          from ``to_dict``/``to_adcp_error``/``build_two_layer_error_envelope``,
          all of which run inside exception handlers — raising here would shadow
          the original exception and the boundary translator would fail open
          with no envelope. A malformed context drops to ``None`` instead.
    """
    if context is None:
        return None
    if isinstance(context, dict):
        return dict(context)
    if not isinstance(context, BaseModel):
        logger.warning(
            "_serialize_context expected dict or BaseModel, got %s; dropping context", type(context).__name__
        )
        return None
    return context.model_dump(mode="json", exclude_none=True)


def _rebuild_error(cls: type[AdCPError], code: ErrorCodeT) -> AdCPError:
    """Reconstruct a pickled or copied error.

    The ``hasattr`` branch is load-bearing: a class-coded subclass IS its code, so
    naming it again would trip ``AdCPError.__new__``'s "already names a code" refusal.
    ``__dict__`` restoration then repopulates ``_error_code`` and the rest.
    """
    return cls() if hasattr(cls, "_code") else cls(error_code=code)


class AdCPError(Exception):
    """Base exception for all AdCP errors.

    Class-level identity (``_code``, ``_default_status_code``) is declared
    with ``ClassVar`` per PEP 526 — each typed subclass overrides the
    ``_default_*`` slot, not the public name. The public ``error_code``,
    ``message``, ``recovery`` and ``suggestion`` are read-only properties
    over ``_error_code`` — functions of the code, resolved from
    ``CODE_TABLE`` at every read, so no instance can carry a value that
    disagrees with the table by any route, assignment included.
    ``status_code`` remains an instance attribute: the HTTP status is a
    transport choice, not a field of the wire error object, so it is the one
    per-class default a caller may override (``error_code=`` on the base,
    refused on a coded subclass).

    Code that needs class-level identity (e.g. ``_build_error_code_to_status``
    walking ``__subclasses__()`` to build the wire-code → HTTP-status table)
    reads ``cls._code`` / ``cls._default_status_code`` directly.
    Instance code reads ``self.error_code`` etc. as before.

    Attributes:
        message: Human-readable error description (read-only, from CODE_TABLE).
        status_code: HTTP status code for REST/FastAPI responses (instance).
        error_code: Machine-readable error code string (read-only).
        recovery: Recovery classification for buyer agents (read-only, from
            CODE_TABLE).
        details: Optional structured error details.
        field: Optional field name that caused the error.
        suggestion: Correction hint for buyer agents (read-only, from
            CODE_TABLE).
        context: Optional AdCP ContextObject (or dict) echoed in the
            envelope so buyer agents can correlate failures to the
            request that produced them (spec 3.0.0 normative).
        internal_detail: Optional NON-WIRE diagnostic payload — the raw
            third-party exception (or free text) that caused this error.
            NEVER serialized: ``to_dict``, ``to_adcp_error`` and
            ``build_two_layer_error_envelope`` all ignore it. It exists so a
            raise site has a sanctioned destination for text whose provenance
            we do not control, instead of interpolating it into ``message``.
            See the class note below.

    Message provenance (AdCP 3.1.1 ``transport-errors.mdx`` § Security
    Considerations / Seller Requirements, lines 659-670): "Error responses
    flow through LLM context. Every field is client-facing. Implementations
    MUST NOT include: internal service names, hostnames, or IP addresses;
    database error text …; stack traces or file paths; upstream API responses
    from internal services; credentials, tokens, or session identifiers."

    ``normalize_to_adcp_error()`` returns an already-typed ``AdCPError``
    unchanged, so for a typed error THE RAISE SITE IS THE WIRE — there is no
    downstream sanitization point. That is why ``message`` is no longer
    authored at all: it is a read-only property returning
    ``CODE_TABLE[code].message``, and ``__init__`` takes no ``message``
    parameter, so the prohibited categories above cannot be interpolated into
    buyer-facing text even by accident. The trust decision is made once, in the
    table, instead of per raise site.

    Where the spec POSITIVELY requires request-specific content — version
    negotiation must name the buyer's requested version and the seller's
    supported set — that content goes in ``details``, which is exactly where
    the spec reads it from: see ``AdCPVersionUnsupportedError`` below, whose
    recovery is "re-pin to a release in the returned
    ``error.details.supported_versions``". Structured values in ``details``,
    third-party text in ``internal_detail`` (logged server-side by
    ``normalize_to_adcp_error()``, never emitted), and nothing at all in
    ``message``.
    """

    # Class-level identity defaults. Subclasses override these.
    _default_status_code: ClassVar[int] = 500
    #: The code this class IS. Annotation only on the base: a class that declares
    #: none cannot be constructed (see ``__new__``), so a code is identity rather
    #: than a default anyone can fall through to.
    #:
    #: There is NO class-level recovery or suggestion knob. Both existed as
    #: ``_default_recovery``/``_default_suggestion`` overrides until it was
    #: measured that zero subclasses used either — the table owned every value
    #: in practice, so the knobs were only a route by which a class could come
    #: to disagree with the pin. They were deleted rather than guarded.
    _code: ClassVar[ErrorCodeT]

    # Instance attributes — set in __init__.
    # ``error_code``, ``message``, ``recovery`` and ``suggestion`` are NOT
    # here: they are read-only properties over ``_error_code``, so none of
    # those slots can be written after construction.
    _error_code: ErrorCodeT
    status_code: int
    internal_detail: BaseException | str | None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Refuse, at class creation, a subclass whose code the table does not classify.

        ``CODE_TABLE`` is the single classifier: every code carries its
        recovery, suggestion and message there, so a class naming a code
        outside it could never resolve those three. Failing here moves that
        contradiction from the first raise (a ``KeyError`` deep in an error
        path) to import time, where the class definition itself is the error.
        """
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_code") and cls._code not in CODE_TABLE:
            raise TypeError(
                f"{cls.__name__} declares _code {cls._code!r}, which CODE_TABLE does not "
                "classify. Declare a code the table knows, or add the entry."
            )

    def __new__(cls, *args: Any, **kwargs: Any) -> AdCPError:
        """Refuse to build an error whose code is absent, or doubly named.

        The invariant is: an error names a code, by its class OR explicitly. Both
        halves are refused here, so neither can be expressed.

        ``_code`` is annotation-only on the base, so ``hasattr`` is False here and
        True on every subclass that declares one. This is the check
        ``object.__new__`` performs for an abstract class and that
        ``BaseException.__new__`` does not: ABC is a runtime no-op for exception
        classes, so without this a bare ``AdCPError()`` would construct and put a
        null code on the buyer's wire.

        The second branch is why there is no ``synthesize()``: a boundary that needs
        a code the class hierarchy does not model names it on the base, and a class
        that already IS a code cannot be overridden into disagreeing with itself.
        Nothing scans for either violation; neither can be constructed.
        """
        has_class_code = hasattr(cls, "_code")
        named = kwargs.get("error_code") is not None
        if has_class_code and named:
            raise TypeError(f"{cls.__name__} already names a code; do not override it")
        if not has_class_code and not named:
            raise TypeError(f"{cls.__name__} declares no _code and none was named")
        return cast("AdCPError", super().__new__(cls, *args, **kwargs))

    def __init__(
        self,
        *,
        error_code: ErrorCodeT | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        field: str | None = None,
        retry_after: int | None = None,
        context: ContextObject | dict[str, Any] | None = None,
        internal_detail: BaseException | str | None = None,
    ) -> None:
        # There is no ``message`` parameter. Buyer-facing text comes from CODE_TABLE
        # via the read-only ``message`` property, so no raise site can author it and
        # no caught exception's text can reach the wire. Provenance-bearing text goes
        # to ``internal_detail`` (server log only); values go to ``field``/``details``.
        #
        # Assigned FIRST: every derived property keys on it.
        self._error_code = error_code if error_code is not None else type(self)._code
        # A class-coded error's membership is already settled at class creation
        # (``__init_subclass__``); a NAMED code is checked here, so an
        # out-of-table code cannot outlive construction on either path.
        # ``message``/``recovery``/``suggestion`` need no assignment at all:
        # they are read-only properties resolving from CODE_TABLE per read.
        if self._error_code not in CODE_TABLE:
            raise TypeError(
                f"error_code {self._error_code!r} is not classified by CODE_TABLE; "
                "name a code the table knows, or add the entry."
            )
        self.details = details
        self.field = field
        self.retry_after = retry_after
        self.context = context
        # NON-WIRE. Deliberately absent from to_dict()/to_adcp_error()/
        # build_two_layer_error_envelope(); emitted only to the server-side log
        # by normalize_to_adcp_error(). Never add it to a serializer.
        self.internal_detail = internal_detail
        self.status_code = status_code if status_code is not None else type(self)._default_status_code
        # args stays EMPTY: BaseException.__reduce__ replays ``cls(*args)``, and this
        # constructor takes none. ``__reduce__`` below replays the keyword form instead,
        # and ``__str__`` reads the property, so str(e) and .message cannot diverge.
        super().__init__()

    @property
    def error_code(self) -> ErrorCodeT:
        """The code this error carries. Read-only: a code cannot be swapped after the
        fact, so ``str(e)``, ``.message``, ``recovery`` and ``status_code`` cannot drift
        apart from it, and an out-of-table value cannot be introduced post-construction.
        """
        return self._error_code

    @property
    def message(self) -> str:
        """Buyer-facing text, derived from the code. There is no setter and no
        parameter: the text is a function of the code, not of the raise site.
        """
        return CODE_TABLE[self._error_code].message

    @property
    def recovery(self) -> RecoveryHint:
        """The pinned recovery classification for this code. Read-only for the
        same reason as ``message``: recovery is the one field a receiver MUST
        read to decode an unknown code, so no instance may carry one that
        disagrees with the table.
        """
        return cast("RecoveryHint", CODE_TABLE[self._error_code].recovery.value)

    @property
    def suggestion(self) -> str:
        """The pinned correction hint for this code, derived like ``message``."""
        return CODE_TABLE[self._error_code].suggestion

    def __str__(self) -> str:
        return self.message

    def __reduce__(self) -> tuple[Any, ...]:
        # ``BaseException.__reduce__`` would replay ``cls(*args)``; args is empty and
        # this constructor is keyword-only, so the default breaks pickle and copy.
        return (_rebuild_error, (type(self), self._error_code), self.__dict__)

    @classmethod
    def iter_concrete_subclasses(cls) -> Iterator[type[AdCPError]]:
        """Yield every transitive *concrete* subclass of ``cls`` exactly once.

        Single source of truth for the subclass walk that builds the
        wire-code -> HTTP-status table (``_build_error_code_to_status``) and
        backs the error-code compliance tests. Yields descendants only — not
        ``cls`` itself — deduplicates so a class reachable by more than one
        path is visited once, and skips abstract bases (their descendants are
        still walked) so the name's "concrete" promise holds.
        """
        import inspect

        seen: set[type] = set()
        stack: list[type] = list(cls.__subclasses__())
        while stack:
            sub = stack.pop()
            if sub in seen:
                continue
            seen.add(sub)
            stack.extend(sub.__subclasses__())
            if not inspect.isabstract(sub):
                yield sub

    def to_dict(self) -> dict[str, Any]:
        """Serialize to flat response body dict (legacy format).

        Returns a flat dict with the raw ``error_code``. Transport boundary
        handlers (FastAPI exception handler, MCP wrapper, A2A wrapper) are
        responsible for translating to wire-compliant codes via
        the transport boundary -- the declared code IS the wire code.

        Includes ``context`` when present so callers building advisory
        payloads (audit logging, retry-loop diagnostics) have the same
        request-correlation envelope key the two-layer wire shape exposes.
        """
        result: dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
            "recovery": self.recovery,
            "details": self.details,
        }
        if self.field is not None:
            result["field"] = self.field
        # ``suggestion`` is a read-only property over CODE_TABLE, and every
        # entry carries one, so it is unconditionally present.
        result["suggestion"] = self.suggestion
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        serialized_context = _serialize_context(self.context)
        if serialized_context is not None:
            result["context"] = serialized_context
        return result

    def to_adcp_error(self) -> dict[str, Any]:
        """Serialize to AdCP spec-compliant ``{"errors": [...]}`` format.

        Uses ``adcp_error()`` from the SDK to produce the canonical error
        envelope. No translation occurs at the transport boundaries, and this
        method preserves the raw ``error_code`` so internal callers retain the source classification.

        ``context`` flows into ``details["context"]`` so the SDK helper
        doesn't drop request-correlation data on the floor.

        .. deprecated::
            Effectively legacy now that ``build_two_layer_error_envelope()``
            is the single source of truth for the wire envelope. Prefer the
            envelope builder for any new code path. This method intentionally
            differs in shape — ``context`` is nested under ``details`` here
            but appears at the top level in the two-layer envelope — and is
            retained only for non-envelope callers (audit logging, SDK
            interop) that still want the flat ``{"errors": [...]}`` payload.
        """
        merged_details = dict(self.details) if self.details else {}
        serialized_context = _serialize_context(self.context)
        if serialized_context is not None:
            merged_details.setdefault("context", serialized_context)
        return adcp_error(
            self.error_code,
            self.message,
            recovery=self.recovery,
            field=self.field,
            suggestion=self.suggestion,
            retry_after=self.retry_after,
            details=merged_details or None,
        )


class AdCPValidationError(AdCPError):
    """Invalid parameters or request data (400)."""

    _default_status_code: ClassVar[int] = 400
    _code: ClassVar[ErrorCodeT] = ErrorCode.VALIDATION_ERROR


class AdCPVersionUnsupportedError(AdCPError):
    """Buyer pinned an adcp_version/adcp_major_version this seller doesn't support (400).

    Recovery is correctable per v3.1.1 error-code.json enumMetadata: re-pin to
    a release in the returned error.details.supported_versions and retry.
    """

    _default_status_code: ClassVar[int] = 400
    _code: ClassVar[ErrorCodeT] = ErrorCode.VERSION_UNSUPPORTED


class AdCPInvalidRequestError(AdCPValidationError):
    """A structurally invalid request graded as INVALID_REQUEST by the storyboard (400).

    Distinct from operation-level VALIDATION_ERROR failures. The AdCP storyboard
    defines the code per operation, so callers must use the exception class graded
    for that scenario rather than inferring the code from validation phase alone.
    Inherits 400 + correctable from AdCPValidationError.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.INVALID_REQUEST


# v3.1.1 error-code.json deprecates the single AUTH_REQUIRED code in favor of
# a split: AUTH_MISSING (no credentials presented; correctable — provide
# credentials and retry) vs AUTH_INVALID (credentials presented but rejected;
# terminal — do not auto-retry, rotate/escalate). AUTH_REQUIRED itself is
# retained by the spec only as a deprecated backward-compat alias. See
# salesagent-mkso for the migration; distinct suggestion strings per code
# since "provide valid credentials" reads as invalid-framing for the
# genuinely-absent-credential sites.


class AdCPAuthenticationError(AdCPError):
    """Presented-but-invalid authentication credentials (401, AUTH_INVALID).

    Emits ``AUTH_INVALID`` per the v3.1.1 error-code enum: "Credentials were
    presented but rejected — revoked, malformed signature, or a key no longer
    in the seller's keystore ... Recovery: terminal." This is the base class
    for the presented-but-rejected case; ``AdCPAuthRequiredError`` below
    overrides to ``AUTH_MISSING`` for the genuinely-absent-credential case.

    Recovery is ``terminal`` — the buyer MUST NOT blindly auto-retry
    (rejected credentials, retried unmodified, will be rejected again);
    rotate/refresh once if applicable, otherwise escalate to a human.
    """

    _default_status_code: ClassVar[int] = 401
    _code: ClassVar[ErrorCodeT] = ErrorCode.AUTH_INVALID


class AdCPAuthRequiredError(AdCPAuthenticationError):
    """No authentication context present (401, AUTH_MISSING).

    Raised when the request contains no auth token / identity at all. Per
    the v3.1.1 error-code enum: "No credentials were presented ... Recovery:
    correctable (provide credentials via the auth header and retry)."
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.AUTH_MISSING


class AdCPAuthorizationError(AdCPError):
    """Authenticated but not authorized for this resource (403).

    Emits ``PERMISSION_DENIED`` with ``correctable`` recovery per the v3.1.1
    error-code enum: "The authenticated caller is not authorized for the
    requested action under the seller's own policies." Distinct from
    ``AUTHORIZATION_REQUIRED`` (a downstream-platform-connection gap, not this
    class's shape) — migrated off the deprecated AUTH_REQUIRED alias
    (salesagent-otc5, completing salesagent-mkso for this axis).
    """

    _default_status_code: ClassVar[int] = 403
    _code: ClassVar[ErrorCodeT] = ErrorCode.PERMISSION_DENIED


class AdCPPolicyViolationError(AdCPAuthorizationError):
    """Request content blocked by an advertising/content policy (403, POLICY_VIOLATION).

    Refines ``AdCPAuthorizationError`` (still a 403, still ``isinstance`` of it):
    the caller is permitted to call the tool, but the *content* of the request
    (brief, brand, targeting) violates a publisher policy. Carries the distinct
    ``POLICY_VIOLATION`` wire code, and the buyer can revise and retry, so
    recovery is ``correctable`` rather than the parent's ``terminal``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.POLICY_VIOLATION


class AdCPNotFoundError(AdCPError):
    """Requested resource does not exist (404, REFERENCE_NOT_FOUND).

    Emits the PUBLISHED ``REFERENCE_NOT_FOUND`` rather than a minted generic
    ``NOT_FOUND``. error-handling.mdx: "Fall back to ``REFERENCE_NOT_FOUND`` for
    resource types without a dedicated code" and "Typed parameters that lack a
    dedicated standard code MUST use ``REFERENCE_NOT_FOUND`` rather than minting a
    custom ``*_NOT_FOUND`` code." A bare ``NOT_FOUND`` is exactly such a mint.

    Recovery=correctable, unchanged: ``REFERENCE_NOT_FOUND``'s pinned enumMetadata
    classifies it correctable, the same class the retired code carried.

    Subclasses that DO have a dedicated standard code (account, media buy,
    package, ...) override ``_code`` and are unaffected — the spec's not-found
    precedence prefers the resource-specific code when the resolved type is known
    from the request, and this base is only the fallback.
    """

    _default_status_code: ClassVar[int] = 404
    _code: ClassVar[ErrorCodeT] = ErrorCode.REFERENCE_NOT_FOUND


class AdCPAccountNotFoundError(AdCPNotFoundError):
    """Account not found by ID or natural key (404, ACCOUNT_NOT_FOUND).

    Recovery=terminal per the pinned enumMetadata for ACCOUNT_NOT_FOUND —
    declared explicitly (the AdCPNotFoundError parent is correctable to
    match its INVALID_REQUEST wire code).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_NOT_FOUND


class AdCPAccountSetupRequiredError(AdCPError):
    """Account exists but requires setup before use (422, ACCOUNT_SETUP_REQUIRED)."""

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_SETUP_REQUIRED


class AdCPAccountSuspendedError(AdCPError):
    """Account is suspended and cannot be used (403, ACCOUNT_SUSPENDED).

    Recovery=terminal per the pinned enumMetadata — declared explicitly
    (the base default is transient to match its SERVICE_UNAVAILABLE wire code).
    """

    _default_status_code: ClassVar[int] = 403
    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_SUSPENDED


class AdCPAccountPaymentRequiredError(AdCPError):
    """Account has outstanding payment requirements (402, ACCOUNT_PAYMENT_REQUIRED).

    Recovery=terminal: from the sales agent's perspective there is
    no in-band remediation — the buyer must settle the outstanding balance
    externally before resubmitting. Matches the BDD storyboard contract for
    UC-002 account-reference partition/boundary rows. Declared explicitly
    (the base default is transient to match its SERVICE_UNAVAILABLE wire code).
    """

    _default_status_code: ClassVar[int] = 402
    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_PAYMENT_REQUIRED


class AdCPConflictError(AdCPError):
    """Resource conflict, e.g. duplicate idempotency key (409).

    Recovery=transient per the pinned error-code.json enumMetadata (CONFLICT):
    a generic resource conflict (e.g. concurrent modification) is resolved by
    retrying with backoff. Subclasses whose specific code the enum classifies as
    correctable (ACCOUNT_AMBIGUOUS, IDEMPOTENCY_CONFLICT, IDEMPOTENCY_EXPIRED)
    override this (#1417).
    """

    _default_status_code: ClassVar[int] = 409
    _code: ClassVar[ErrorCodeT] = ErrorCode.CONFLICT


class AdCPAccountAmbiguousError(AdCPConflictError):
    """Natural key matches multiple accounts (409, ACCOUNT_AMBIGUOUS)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_AMBIGUOUS
    # ACCOUNT_AMBIGUOUS is correctable per the enum (the buyer disambiguates with
    # an explicit account_id) — override the transient CONFLICT parent (#1417).


class AdCPGoneError(AdCPError):
    """Resource previously existed but is no longer available (410).

    Recovery=correctable: the resource itself is gone, but the buyer can
    recover by referencing a different resource (a fresh proposal, a new
    media buy) and re-issuing the request.
    """

    _default_status_code: ClassVar[int] = 410
    _code: ClassVar[ErrorCodeT] = ErrorCode.INVALID_STATE


class AdCPBudgetExhaustedError(AdCPError):
    """Budget or spend limit has been reached (422).

    Recovery=terminal per the pinned error-code.json enumMetadata (BUDGET_EXHAUSTED):
    an exhausted budget cannot be recovered autonomously — an operator must add
    budget — so the buyer agent must not retry (#1417).
    """

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.BUDGET_EXHAUSTED


class AdCPRateLimitError(AdCPError):
    """Too many requests (429)."""

    _default_status_code: ClassVar[int] = 429
    _code: ClassVar[ErrorCodeT] = ErrorCode.RATE_LIMITED


class AdCPAdapterError(AdCPError):
    """External adapter (GAM, etc.) failure (502)."""

    _default_status_code: ClassVar[int] = 502
    _code: ClassVar[ErrorCodeT] = ErrorCode.SERVICE_UNAVAILABLE


class AdCPConfigurationError(AdCPError):
    """Server-side configuration is broken (500).

    Raised when encrypted secrets cannot be decrypted (key rotation,
    corruption, missing ENCRYPTION_KEY). Callers should NOT silently
    fall back — the configuration needs admin intervention, so recovery is
    ``terminal``: the buyer has no lever to fix server config and per the
    pinned enum "MUST NOT auto-retry". CONFIGURATION_ERROR is a code the pinned
    table classifies — it reaches the wire untranslated
    (#1430 review).
    """

    _default_status_code: ClassVar[int] = 500
    _code: ClassVar[ErrorCodeT] = ErrorCode.CONFIGURATION_ERROR


class AdCPServiceUnavailableError(AdCPError):
    """Service or product temporarily unavailable (503).

    503 indicates a temporary outage in a downstream service the sales
    agent depends on. Recovery=transient so buyer agents retry rather
    than mutate the request.
    """

    _default_status_code: ClassVar[int] = 503
    _code: ClassVar[ErrorCodeT] = ErrorCode.SERVICE_UNAVAILABLE


class AdCPInternalError(AdCPError):
    """The seller's own state is inconsistent, so the request cannot be completed (500).

    Distinct from AdCPServiceUnavailableError, which names a downstream outage, and from
    AdCPValidationError, which says the buyer's request is at fault. This says neither: the
    request was well formed and no dependency is down, but an invariant this seller relies
    on did not hold. The buyer cannot fix it by changing anything, and recovery is transient
    because the inconsistency may be a race that a retry resolves.

    INTERNAL_ERROR is a platform code (AppErrorCode), legal on the wire because AdCP 3.1.1's
    code vocabulary is open, and classified in CODE_TABLE like every other code this seller
    emits.
    """

    _default_status_code: ClassVar[int] = 500
    _code: ClassVar[ErrorCodeT] = AppErrorCode.INTERNAL_ERROR


class AdCPUrlNotAllowedError(AdCPError):
    """A buyer-supplied URL names a host this seller will not contact (400).

    Emits the PUBLISHED ``VALIDATION_ERROR``, not a platform code. This class briefly
    carried a minted ``URL_NOT_ALLOWED`` on the reasoning that VALIDATION_ERROR "tells a
    buyer nothing they can act on differently". That reasoning does not survive the pin:
    malformed-vs-value-refused is already the published INVALID_REQUEST / VALIDATION_ERROR
    split (INVALID_REQUEST is "malformed, missing required fields, or violates schema
    constraints"; VALIDATION_ERROR is "invalid field values or violates business rules
    beyond schema validation"), and a schema-valid https URI refused by a deny-list is the
    second. The pinned spec then applies it to this exact vector:
    ``dist/docs/3.1.0/learning/specialist/security.mdx:84`` has the practitioner register
    ``https://169.254.169.254/latest/meta-data/`` and "observe that the agent refuses it
    synchronously with a ``VALIDATION_ERROR`` on ``notification_configs[].url``".

    The open vocabulary permits minting a code the spec has NOT defined; it does not make
    a private synonym of a published member a good idea, because a buyer switching on
    ``error.code`` across sellers loses the ability to handle this uniformly.

    The class survives the code change on purpose: the A2A boundary catches it BY TYPE to
    select ``InvalidParamsError``, which a bare ``AdCPValidationError`` could not express
    without also catching every other validation failure.

    The buyer's actionable signal is the CODE plus ``field`` (which URL was refused). The
    rejection REASON never reaches the buyer -- the spec's Security Considerations forbid
    disclosing internal service names, hostnames or IP addresses, so the cause rides
    ``internal_detail`` (server log only). Deliberate loss in the switch: the retired
    entry's suggestion enumerated the refused host classes, where VALIDATION_ERROR's is
    the generic "review error details and fix field values". A per-class override is NOT
    the fix -- it would make the suggestion a function of the class rather than the code,
    which ADR-010 forbids (the override knob that once allowed it is deleted).
    """

    _default_status_code: ClassVar[int] = 400
    _code: ClassVar[ErrorCodeT] = ErrorCode.VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Typed subclasses for spec-compliant error codes.
# ---------------------------------------------------------------------------
# Each subclass pins its wire error_code to a CODE_TABLE entry (the pinned
# enums/error-code.json plus this platform's own AppErrorCode members), so
# raise sites can use semantic names (AdCPMediaBuyNotFoundError) instead of
# constructing Error(code="MEDIA_BUY_NOT_FOUND") inline. The boundary
# translator runs build_two_layer_error_envelope() on the raised exception.


class AdCPMediaBuyNotFoundError(AdCPNotFoundError):
    """Media buy lookup failed (404, MEDIA_BUY_NOT_FOUND).

    Recovery=correctable: the buyer can correct by supplying the right
    media_buy_id (typo, wrong tenant, stale reference). Overrides the
    ``AdCPNotFoundError`` ``terminal`` default — for this specific not-found
    case the buyer's own request is the lever for recovery.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.MEDIA_BUY_NOT_FOUND


class AdCPPackageNotFoundError(AdCPNotFoundError):
    """Package lookup failed within a media buy (404, PACKAGE_NOT_FOUND).

    Recovery=correctable: the buyer can correct by supplying the right
    package_id. Overrides the ``AdCPNotFoundError`` ``terminal`` default for
    the same reason as ``AdCPMediaBuyNotFoundError``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.PACKAGE_NOT_FOUND


class AdCPProductNotFoundError(AdCPNotFoundError):
    """Requested product does not exist (404, PRODUCT_NOT_FOUND).

    Recovery=correctable: the buyer can correct by supplying a valid
    product_id (discoverable via get_products). Overrides the
    ``AdCPNotFoundError`` ``terminal`` default for the same reason as
    ``AdCPMediaBuyNotFoundError`` — the buyer's own request is the lever
    for recovery. PRODUCT_NOT_FOUND is a standard SDK code (passthrough,
    emitted as itself).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.PRODUCT_NOT_FOUND


class AdCPContextNotFoundError(AdCPNotFoundError):
    """Buyer-supplied context_id does not resolve (404, SESSION_NOT_FOUND).

    A ``context_id`` that does not map to a persistent context is a not-found
    condition, not a gone/expired one: ``Context`` rows have no TTL, expiry, or
    delete path anywhere in ``src/``, so a non-resolving id never existed. That
    rules out ``AdCPGoneError`` (``INVALID_STATE``) — the correct wire code is
    ``SESSION_NOT_FOUND``, the standard SDK code for an unresolvable
    session/context (emitted as itself).

    Recovery=correctable: the buyer can correct by supplying a valid context_id
    or omitting it to start a fresh context. Overrides the ``AdCPNotFoundError``
    ``terminal`` default for the same reason as ``AdCPMediaBuyNotFoundError``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.SESSION_NOT_FOUND


class AdCPCreativeNotFoundError(AdCPNotFoundError):
    """Requested creative does not exist (404, wire CREATIVE_NOT_FOUND).

    ``CREATIVE_NOT_FOUND`` is a pinned-spec wire code (enums/error-code.json @
    04f59d2d5): correctable, and MANDATED uniformly for any creative_id not
    owned by the calling account — never distinguish "exists under another
    principal/tenant" from "does not exist" (anti-enumeration). It reaches the
    wire untranslated: CODE_TABLE classifies it.

    Recovery=correctable: the buyer can correct by supplying a valid creative_id
    (discoverable via list_creatives / sync_creatives).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.CREATIVE_NOT_FOUND


class AdCPFormatNotFoundError(AdCPNotFoundError):
    """Requested creative format does not exist on the agent (404, REFERENCE_NOT_FOUND).

    Emits the PUBLISHED ``REFERENCE_NOT_FOUND``, not a minted ``FORMAT_NOT_FOUND``.
    The pinned spec forbids the latter by name: release-notes.mdx (#2704) lists
    ``FORMAT_NOT_FOUND`` among eleven custom codes that "collapse to
    ``REFERENCE_NOT_FOUND`` with ``error.field`` naming the failed parameter" and
    closes "Sellers returning any of the 11 collapsed codes today MUST switch to
    ``REFERENCE_NOT_FOUND``". error-handling.mdx restates it generally: "Typed
    parameters that lack a dedicated standard code MUST use ``REFERENCE_NOT_FOUND``
    rather than minting a custom ``*_NOT_FOUND`` code".

    This is NOT the open-vocabulary allowance. An open vocabulary permits a code
    the spec has not defined; it does not permit one the spec explicitly REMOVED
    and replaced under a MUST.

    ``field="format_id"`` is retained deliberately. The uniform-response rule
    requires a type-NEUTRAL field when naming it would leak a polymorphic
    parameter's resolved type, but creative/specification.mdx names this exact
    case the other way: "``REFERENCE_NOT_FOUND``: Requested format does not exist
    or is not accessible (``error.field`` identifies the ``format_id``)".
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.REFERENCE_NOT_FOUND


class AdCPTaskNotFoundError(AdCPNotFoundError):
    """Requested workflow task/step does not exist (404, REFERENCE_NOT_FOUND).

    ``TASK_NOT_FOUND`` is not among the eight resource-specific not-found codes
    the pinned spec enumerates (PRODUCT/PACKAGE/MEDIA_BUY/CREATIVE/SIGNAL/SESSION/
    ACCOUNT/PLAN), so error-handling.mdx's general MUST applies: "Typed parameters
    that lack a dedicated standard code MUST use ``REFERENCE_NOT_FOUND`` rather
    than minting a custom ``*_NOT_FOUND`` code -- the vocabulary grows by upstream
    spec change, not by per-seller inflation."

    Positively graded upstream: the get_products_async storyboard step
    ``get_products_task_status_wrong_account`` expects ``REFERENCE_NOT_FOUND``, and
    ``get_task`` is a registered MCP tool, so this envelope is buyer-facing.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.REFERENCE_NOT_FOUND


class AdCPBudgetTooLowError(AdCPError):
    """Requested budget falls below product minimum (422, BUDGET_TOO_LOW)."""

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.BUDGET_TOO_LOW


class AdCPCapabilityNotSupportedError(AdCPError):
    """Requested capability is not supported by this seller (422, UNSUPPORTED_FEATURE).

    .. note::
        **Spec-conformant.** The pinned AdCP error-code enum classifies
        ``UNSUPPORTED_FEATURE`` as ``correctable`` ("check
        get_adcp_capabilities and remove unsupported fields"), and we emit
        ``correctable`` — so this matches the spec, it is not a divergence.
        The buyer holds the recovery lever: they can fix the request by
        dropping the unsupported feature (e.g. removing ``property_list``
        targeting against an adapter that doesn't compile it).

        Only the adcp SDK's ``STANDARD_ERROR_CODES`` table classifies it
        ``terminal``; the SDK is not authoritative (the pinned spec enum is),
        so its table diverges from the spec here. If the SDK runtime ever
        starts enforcing ``terminal`` at the wire (rejecting our spec-correct
        ``correctable`` hint), reconcile with the SDK then.
    """

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.UNSUPPORTED_FEATURE


class AdCPIdempotencyConflictError(AdCPConflictError):
    """idempotency_key reused with a different request payload (409, IDEMPOTENCY_CONFLICT).

    Recovery=correctable: the buyer can fix this and resend — either replay the
    ORIGINAL bytes under the same key, or mint a fresh idempotency_key for the
    new payload. This matches the AdCP 3.0.1 prose example envelope and the
    conformance storyboard's stated expectation. The SDK's
    ``STANDARD_ERROR_CODES`` table classifies the code ``terminal``, but that
    table is only a default applied when no recovery is supplied — an explicit
    recovery always wins, and nothing in the SDK or the storyboard's machine
    validations grades the value.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.IDEMPOTENCY_CONFLICT


class AdCPIdempotencyExpiredError(AdCPConflictError):
    """idempotency_key seen before, but its replay window has expired (409, IDEMPOTENCY_EXPIRED).

    Raised when a same-key buy exists but outlived the advertised replay TTL
    (``get_adcp_capabilities.adcp.idempotency.replay_ttl_seconds``): per
    security.mdx#idempotency rule 6, a request arriving after eviction with a
    key the seller has seen SHOULD be rejected with ``IDEMPOTENCY_EXPIRED``
    rather than silently treated as new or answered with another buy's data.

    Recovery=correctable, matching the sibling ``IDEMPOTENCY_CONFLICT``: the
    buyer agent recovers autonomously — a natural-key existence check (e.g.
    ``get_media_buys`` by ``context.internal_campaign_id``) to learn whether the
    original request succeeded, then either accept that result or mint a fresh
    idempotency_key for a new attempt. The 3.0.1 ``error-code.json`` enum
    description classifies the code ``correctable`` (that buyer-recovery path),
    and the recovery taxonomy reserves ``terminal`` for conditions requiring
    HUMAN action (account suspended, payment required) — not an agent-resolvable
    retry. The SDK's ``STANDARD_ERROR_CODES`` default table lists it ``terminal``,
    but that default applies only when no recovery is supplied; an explicit
    recovery wins, exactly as for ``IDEMPOTENCY_CONFLICT``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.IDEMPOTENCY_EXPIRED


class AdCPCreativeRejectedError(AdCPError):
    """Creative failed policy or technical validation (422, CREATIVE_REJECTED)."""

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.CREATIVE_REJECTED


class AdCPBudgetExceededError(AdCPError):
    """Requested budget exceeds tenant or product ceiling (422, BUDGET_EXCEEDED)."""

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.BUDGET_EXCEEDED


class AdCPProductUnavailableError(AdCPError):
    """Product is offline, deactivated, or otherwise unavailable (422, PRODUCT_UNAVAILABLE)."""

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.PRODUCT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Adapter-taxonomy subclasses (502 → SERVICE_UNAVAILABLE).
# ---------------------------------------------------------------------------
# These extend AdCPAdapterError to carry a failure taxonomy as the class identity
# instead of smuggling it through ``details["internal_code"]`` (which is
# buyer-visible). Each class's ``error_code`` now reaches the buyer AS ITSELF: the
# AdCP vocabulary is open, so a specific platform code plus its recovery tells the
# buyer more than a collapse onto SERVICE_UNAVAILABLE did.


class AdCPWorkflowError(AdCPAdapterError):
    """Workflow-step orchestration failed inside an adapter (502 → SERVICE_UNAVAILABLE).

    Carries the WORKFLOW_CREATION_FAILED taxonomy as the class identity so
    logs/audit retain the specific failure mode while the wire shows the
    standard SERVICE_UNAVAILABLE. Recovery=transient (inherited): the
    workflow subsystem may succeed on retry.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.WORKFLOW_CREATION_FAILED


class AdCPLineItemError(AdCPAdapterError):
    """Adapter line-item creation failed (502 → SERVICE_UNAVAILABLE).

    Carries the LINE_ITEM_CREATION_FAILED taxonomy as the class identity;
    same rationale as ``AdCPWorkflowError``.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.AD_SERVER_CREATE_FAILED


class AdCPBulkUpdateError(AdCPAdapterError):
    """A bulk update partially failed — N operations attempted, M failed (502 → SERVICE_UNAVAILABLE).

    Unifies the cross-adapter partial-failure event under one class and one
    status (502) so REST clients filtering on HTTP status don't fork by
    adapter (previously broadstreet raised 502, GAM raised 503 for the same
    semantic event). Carries the PARTIAL_FAILURE taxonomy as the class
    identity; per-operation detail (failed IDs, counts) belongs in ``details``
    as data. Recovery=transient (inherited): failed operations may succeed
    on retry.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.PARTIAL_FAILURE


class AdCPActivationWorkflowError(AdCPAdapterError):
    """Adapter order/line-item activation workflow failed (502 → SERVICE_UNAVAILABLE).

    Distinct from ``AdCPWorkflowError`` (creation): this is the activation step
    of an existing order. Carries the ACTIVATION_WORKFLOW_FAILED taxonomy as the
    class identity; same wire mapping as the other adapter-workflow failures.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.ACTIVATION_WORKFLOW_FAILED


class AdCPGamUpdateError(AdCPAdapterError):
    """A GAM line-item update API call failed (502 → SERVICE_UNAVAILABLE).

    Carries the GAM_UPDATE_FAILED taxonomy as the class identity; per-operation
    detail (package_id, line_item_id) belongs in ``details`` as data.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.AD_SERVER_UPDATE_FAILED


class AdCPMediaBuyRejectedError(AdCPError):
    """The seller declined the media buy (422 → POLICY_VIOLATION).

    A business rejection, not a server failure: recovery=correctable so the
    buyer can adjust the request and resubmit. Carries the MEDIA_BUY_REJECTED
    taxonomy as the class identity; the wire code is the standard POLICY_VIOLATION.
    """

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = AppErrorCode.MEDIA_BUY_REJECTED


class AdCPInventoryUnavailableError(AdCPError):
    """Requested inventory is not available (422, PRODUCT_UNAVAILABLE).

    Emits the PUBLISHED ``PRODUCT_UNAVAILABLE``, whose pinned description is
    exactly this condition: "The requested product is sold out or no longer
    available." A private ``INVENTORY_UNAVAILABLE`` synonym of a published member
    costs buyers the ability to switch on ``error.code`` across sellers, which is
    the whole point of a published vocabulary -- the openness of that vocabulary
    exists for conditions the spec has NOT named, not for renaming ones it has.

    This docstring previously claimed "the wire code is the standard
    PRODUCT_UNAVAILABLE" while ``_code`` said otherwise; the claim is now true.

    recovery=correctable, unchanged: PRODUCT_UNAVAILABLE's pinned enumMetadata
    classifies it correctable, the same class the retired platform code carried.
    """

    _default_status_code: ClassVar[int] = 422
    _code: ClassVar[ErrorCodeT] = ErrorCode.PRODUCT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Two-layer envelope serializer — single source of truth for wire shape.
# ---------------------------------------------------------------------------
# All three boundary translators (MCP, A2A, REST) and
# ContextManager.audit_workflow_step_failure call this so wire
# responses and persisted workflow_step.response_data share the same
# two-layer shape. _impl functions never build wire shape; they raise
# AdCPError subclasses and the boundary translator runs this.
#
# Spec: two-layer model is normative since AdCP 3.0.0 (``error-handling.mdx``).
# Storyboard runners (@adcp/sdk 6.11.0+) check errors[0].code (when
# success===false) AND adcp_error.code; missing either layer causes the
# runner to synthesize "MCP_ERROR" and erase the real code.


def build_error_object(exc: AdCPError) -> dict[str, Any]:
    """The single per-error object for an advisory list (``errors[]`` entries).

    Same derivation as ``build_two_layer_error_envelope``, which is the point: a second
    place that turns a code into buyer-facing text will disagree with this one, and did —
    a tools-layer copy keyed the message off the WIRE code while this keys it off the RAW
    code, so 10 of 41 subclasses produced two different sentences for one failure.
    """
    return dict(build_two_layer_error_envelope(exc)["errors"][0])


def build_two_layer_error_envelope(exc: AdCPError) -> dict[str, Any]:
    """Build the AdCP spec-compliant two-layer error envelope from an exception.

    Wraps the stable ``adcp_error()`` SDK helper for the payload half
    (``errors[]``), then mirrors the single error object at envelope level
    as ``adcp_error`` so the storyboard runner can read either path. Echoes
    ``exc.context`` when present.

    Returns:
        Plain dict with shape::

            {
                "adcp_error": {"code": "...", "message": "...", "recovery": "...", ...},
                "errors": [{"code": "...", "message": "...", "recovery": "...", ...}],
                "context": {...},     # only when exc.context is set
            }

    Both layers carry ``exc.error_code`` VERBATIM. There is no translation step: the
    AdCP error vocabulary is OPEN (core/error.json -- ``error.code`` is a wire-typed
    string, the published codes are documentary, senders MAY emit codes outside that
    set, and receivers MUST decode an unknown code by reading ``error.recovery``), so
    a platform code reaches the buyer as the raise site declared it.
    """
    payload = adcp_error(
        exc.error_code,
        exc.message,
        recovery=exc.recovery,
        field=exc.field,
        suggestion=exc.suggestion,
        retry_after=exc.retry_after,
        details=exc.details,
    )
    # Copy errors[0] for the envelope-level mirror so callers that mutate one
    # layer don't accidentally mutate the other (aliasing footgun once both
    # layers may be mutated independently).
    envelope: dict[str, Any] = {
        "adcp_error": dict(payload["errors"][0]),
        "errors": payload["errors"],
    }
    serialized_context = _serialize_context(exc.context)
    if serialized_context is not None:
        envelope["context"] = serialized_context
    return envelope


# Canonical buyer-facing suggestions from error-code.json enumMetadata (AdCP 3.1.1):
# each code carries its own default hint, so a VALIDATION_ERROR must not borrow
# INVALID_REQUEST's text.


def first_validation_error_field(validation_error: ValidationError) -> str | None:
    """Return the bracket-notation path of the first Pydantic error, or ``None``.

    Lets a transport boundary attach a structured ``field`` to the
    ``AdCPValidationError`` it raises, so the wire envelope carries the offending
    field path instead of only the rendered message. List indices render as
    ``[i]`` so boundary-derived paths such as ``packages[0].budget`` align with
    the ``packages[].budget`` field strings raised by the implementation layer.
    """
    errors = validation_error.errors()
    if not errors:
        return None
    parts: list[str] = []
    for loc in errors[0]["loc"]:
        if isinstance(loc, int):
            parts.append(f"[{loc}]")
        elif parts:
            parts.append(f".{loc}")
        else:
            parts.append(str(loc))
    return "".join(parts)


def build_validation_error_details(errors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Project Pydantic errors into the buyer-safe structured detail shape."""
    return {
        "validation_errors": [
            {
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg"),
                "type": error.get("type"),
            }
            for error in errors
        ]
    }


def _log_internal_detail(exc: AdCPError) -> None:
    """Emit an ``AdCPError``'s non-wire ``internal_detail`` to the server log.

    The single emission point for every raise site that hands its raw cause to
    ``internal_detail=`` instead of interpolating it into the buyer-facing
    ``message``. It lives here because ``normalize_to_adcp_error()`` is the one
    place every error from every transport (MCP, A2A, REST) passes through, so
    one line replaces a hand-rolled ``logger.error(raw)`` at each raise site —
    and covers the sites that log nothing at all today.
    """
    detail = exc.internal_detail
    if detail is None:
        return
    logger.error(
        "AdCPError %s internal detail (not emitted to the buyer): %s",
        type(exc).__name__,
        detail,
        exc_info=detail if isinstance(detail, BaseException) else None,
    )


def normalize_to_adcp_error(exc: Exception) -> AdCPError:
    """Normalize untyped exceptions to typed AdCPError subclasses.

    Single source of truth for the wrapping applied at all three transport
    boundaries (MCP, A2A, REST). Already-typed ``AdCPError`` passes through
    unchanged. Pydantic ``ValidationError`` maps to a structured, sanitized
    ``AdCPValidationError``; other ``ValueError`` instances map to the plain
    validation error, ``PermissionError`` to ``AdCPAuthorizationError``, and
    anything else names INTERNAL_ERROR on the base.

    Every branch keeps its type mapping and carries NO text: an untyped exception's
    string has no provenance guarantee (it may be a DB DSN, a stack fragment, or an
    upstream response body -- AdCP 3.1.1 transport-errors.mdx Security Considerations
    MUST-NOT list), and the code's own table sentence is what the buyer sees. The
    original exception is still logged in full server-side by the transport
    boundary's record_boundary_error() / audit logger.
    """
    if isinstance(exc, AdCPError):
        _log_internal_detail(exc)
        return exc
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        return AdCPValidationError(
            field=first_validation_error_field(exc),
            details=build_validation_error_details(errors),
        )
    if isinstance(exc, ValueError):
        return AdCPValidationError()
    if isinstance(exc, PermissionError):
        return AdCPAuthorizationError()
    return AdCPError(error_code=AppErrorCode.INTERNAL_ERROR)

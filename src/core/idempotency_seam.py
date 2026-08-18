"""The one place the verbatim idempotency cache is read and written.

AdCP 3.1.1 (`universal/idempotency.yaml`) requires every mutating task to accept
an `idempotency_key` and, on replay with an equivalent payload, return the CACHED
response without re-executing mutations. Two tools need that contract today
(`create_media_buy`, `sync_creatives`) and more will: every task whose pinned
request schema marks `idempotency_key` required.

This module exists so that is ONE implementation rather than one per tool. The
alternative — each tool probing and recording against the repository itself —
looks harmless per tool and drifts immediately: the conflict check, the
hash-input choice and the "cache successes only" rule each have to be got right,
and a second copy gets them right only until one side changes.
`test_architecture_idempotency_single_seam` pins that exactly one production
module reaches the cache, which is why `_attempts_of` below is the ONLY
production read of `unit_of_work.idempotency_attempts`.

Tool-specific concerns stay with the tool: which unit of work to open, what goes
into the canonical hash, and how to parse a stored envelope back into that tool's
response type. Everything shared — locate the repository, compare the hash, raise
the conflict BEFORE replaying, never fabricate a response, stamp the replay
marker — lives here.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from src.core.exceptions import AdCPIdempotencyConflictError
from src.core.idempotency_canonical import canonical_payload_hash


def _attempts_of(unit_of_work: Any) -> Any:
    """The verbatim-cache repository for a unit of work.

    The single production reader of that handle. Every tool reaches the cache
    through this module, so a tool that wants replay protection has to JOIN the
    seam rather than grow a second copy of it — which is the property
    `test_architecture_idempotency_single_seam` grades.

    Raises rather than asserting: a unit of work wired without the repository is
    a construction bug, and under `python -O` a bare assert would vanish and turn
    it into an AttributeError further away from the cause.
    """
    # Real attribute access, deliberately not getattr(): this line IS the seam
    # anchor `test_architecture_idempotency_single_seam` counts, and a string
    # literal inside getattr() is invisible to that AST scan — the guard would
    # read "no module reaches the cache" and pass vacuously.
    attempts = unit_of_work.idempotency_attempts
    if attempts is None:
        raise RuntimeError(
            f"{type(unit_of_work).__name__} exposes no idempotency_attempts repository; "
            "wire it in the unit of work before joining the idempotency seam"
        )
    return attempts


def hash_payload(request_payload: dict[str, Any]) -> str:
    """The canonical hash of a request payload, as stored on the cache row.

    Re-exported so callers that already hold a hash (create_media_buy computes
    one earlier for its race resolution) and callers that hold a payload
    (sync_creatives) both feed the SAME function into the conflict comparison.
    """
    return canonical_payload_hash(request_payload)


def raise_on_payload_conflict(stored_hash: str | None, request_hash: str | None) -> None:
    """Raise IDEMPOTENCY_CONFLICT when the same key carries a different canonical payload.

    Applied at every lookup point so a conflicting duplicate can never be
    resolved to someone else's response. Production writes always store a hash
    (`record_success` requires it); a row without one carries no conflict signal,
    so it never conflicts (legacy tolerance).

    No explicit recovery: AdCPIdempotencyConflictError already pins the
    spec-mandated "correctable". AdCP 3.1.1
    compliance/universal/idempotency.yaml:423-424 ("Same key, different payload
    returns IDEMPOTENCY_CONFLICT") grades `recovery: correctable (buyer should
    use a fresh UUID v4)`. The SDK's STANDARD_ERROR_CODES table says "terminal"
    and is WRONG here — it is a cross-check, not the authority. Passing recovery=
    at a call site would silently re-diverge that site from the shared class.
    """
    if stored_hash is not None and stored_hash != request_hash:
        raise AdCPIdempotencyConflictError("idempotency_key was reused with a different request payload")


def probe_verbatim_replay[ResponseT: BaseModel](
    unit_of_work: Any,
    *,
    principal_id: str,
    account_id: str | None,
    idempotency_key: str,
    request_hash: str | None,
    parse: Callable[[dict[str, Any]], ResponseT | None],
    on_miss: Callable[[Any], None] | None = None,
) -> ResponseT | None:
    """The cached response for this key, or None to execute freshly.

    Order matters and is the contract: the payload-hash CONFLICT is checked
    BEFORE any replay, so a buyer who reused a key with a different body is told
    so rather than silently handed someone else's result.

    A hit whose stored envelope no longer validates returns None — the same as a
    miss. Reconstructing a response the buyer cannot distinguish from a faithful
    replay is the named failure mode, so this never fabricates one.

    ``parse`` receives the WHOLE stored envelope (``{"status": ..., "response":
    ...}``) rather than a pre-extracted body: the wrapper each tool rebuilds
    differs (create_media_buy carries the protocol status on a result envelope;
    sync_creatives declares its status on the response itself), and having the
    seam guess the shape is how a replay starts reconstructing instead of
    replaying. Returning None from ``parse`` is a miss, same as raising.

    ``on_miss`` runs only when no row exists, receiving the repository — the
    front probe uses it to rate-limit the insert a fresh key is about to cause.
    """
    attempts = _attempts_of(unit_of_work)
    cached = attempts.find_by_key(
        principal_id=principal_id,
        account_id=account_id,
        idempotency_key=idempotency_key,
    )
    if cached is None:
        if on_miss is not None:
            on_miss(attempts)
        return None
    raise_on_payload_conflict(cached.payload_hash, request_hash)
    try:
        replay = parse(cached.response_envelope or {})
    except ValidationError:
        return None
    if replay is None:
        return None
    # Stamp the spec's replay marker. It is deliberately NOT stored in the cached
    # body: the cache holds the ORIGINAL response, and `replayed` describes THIS
    # delivery of it, not the response itself. AdCP 3.1.1
    # compliance/universal/idempotency.yaml:389-392 grades `replayed: true` on the
    # replay, while :332-335 forbids `true` on the fresh call that populated the
    # cache -- storing it would fail the second step on the next cold read.
    if "replayed" in type(replay).model_fields:
        replay = replay.model_copy(update={"replayed": True})
    return replay


def record_verbatim_success(
    unit_of_work: Any,
    *,
    principal_id: str,
    account_id: str | None,
    idempotency_key: str,
    tool_name: str,
    request_hash: str,
    response: BaseModel,
    protocol_status: str,
) -> None:
    """Store a SUCCESS envelope for replay.

    Successes only, and only after the mutations have happened — rule 3 ("Only
    successful responses are cached"). Caching an error would mask legitimate
    recovery: most AdCP terminal states are state-dependent and flip once the
    buyer remediates, so a cached failure would outlive the condition that caused it.
    """
    _attempts_of(unit_of_work).record_success(
        principal_id=principal_id,
        account_id=account_id,
        idempotency_key=idempotency_key,
        tool_name=tool_name,
        payload_hash=request_hash,
        response_model=response,
        protocol_status=protocol_status,
    )


def find_attempt_including_expired(
    unit_of_work: Any,
    *,
    principal_id: str,
    account_id: str | None,
    idempotency_key: str,
) -> Any:
    """The cache row for this key even if its replay window has closed.

    The expiry decision needs the row's STORED ``expires_at`` — the single
    replay-window authority the read path filters on — so the caller can tell
    "expired" from "never existed" and fail closed per security.mdx rule 6.
    """
    return _attempts_of(unit_of_work).find_including_expired(
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        account_id=account_id,
    )


def expire_old_attempts(unit_of_work: Any) -> None:
    """Reclaim storage for rows past their replay window (housekeeping only).

    Replay CORRECTNESS comes from read-path TTL filtering, never from this
    running — callers treat it as best-effort.
    """
    _attempts_of(unit_of_work).expire_old()

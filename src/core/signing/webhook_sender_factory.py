"""The ONE seam that decides how an outbound AdCP webhook is authenticated (#1291 C1).

``salesagent-z6nr.18``. Core Invariant: *every outbound AdCP webhook is authenticated
by exactly ONE mode, selected at ONE seam from the receiver's own registration, and
the bytes signed are the bytes sent.*

This module owns **policy only**. ``adcp.webhooks.WebhookSender`` owns the mechanism —
it serializes once, signs those exact bytes, and POSTs them
(``send_raw``: *"Byte-exact serialization — this is the ONLY representation that gets
signed AND posted"*). So #1441 (a signature computed over a re-serialization of the
body) is unreachable through this boundary by construction rather than by three call
sites remembering a rule.

What we decide, and nothing else:

* **which mode a receiver gets** — :func:`legacy_auth_mode`. security.mdx @ v3.1.1
  :1424 keys mode selection on ``authentication`` being PRESENT, *not* on its value
  being HMAC: an ``authentication`` block naming Bearer selects the LEGACY arm too.
  The three senders spelled this three different ways before C1 (``"HMAC-SHA256"``,
  ``"Bearer"``, ``"bearer"``/``"basic"``), so a bearer-registered receiver could be
  handed an RFC 9421 signature it must answer with ``webhook_mode_mismatch``
  (:1466). One case-insensitive predicate replaces all three.
* **where the tenant's key comes from** — ``resolve_signing_material``, which is the
  same row -> ref -> PEM -> published-JWK-tripwire path the request signer uses.
* **what we may honestly declare** — :func:`webhook_signing_posture`, checked against
  the algorithm we are about to sign with before the sender is handed back.

Mode selection is a CONSTRUCTOR choice, so "signed both ways" (which :1425 forbids)
is not a rule to enforce but a shape that cannot be expressed: a ``WebhookSender``
holds exactly one auth strategy, and ``signs_with_rfc9421`` reports which.

**Destination policy is deliberately unchanged by C1.** The sender is handed an
``httpx.AsyncClient`` we own, which puts it on the SDK's operator-supplied-client
path — the operator's transport owns SSRF, exactly as today. Adopting the SDK's
IP-pinned transport (DNS pre-resolution + private-range refusal) is a real behaviour
change to every existing receiver URL and belongs with the SSRF work (GH #1697), not
with the signing switch.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from adcp.webhooks import WebhookDeliveryResult, WebhookSender

from src.core.enum_helpers import enum_value
from src.core.exceptions import AdCPConfigurationError
from src.core.signing.posture import webhook_signing_posture
from src.core.signing.provider import resolve_signing_material

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.core.database.models import PushNotificationConfig
    from src.core.database.repositories.signing_key import SigningKeyRepository

logger = logging.getLogger(__name__)

#: The receiver registered HMAC-SHA256 and supplied a credential.
LEGACY_HMAC = "hmac"

#: The receiver registered a token-bearing scheme (Bearer / Basic). The SDK has one
#: token constructor; ``Basic`` receivers therefore get ``Authorization: Bearer
#: <token>``. That is a deliberate consequence of routing every legacy scheme through
#: one sender and is logged below, not silently swallowed.
LEGACY_BEARER = "bearer"

#: ``authentication`` is present but carries no usable credential. Still the LEGACY
#: arm: :1425 forbids answering a legacy registration with an RFC 9421 signature, so
#: the honest outcome is an unauthenticated delivery, never a signed one.
LEGACY_UNCREDENTIALED = "uncredentialed"

#: Spellings of the legacy HMAC scheme seen on real registrations, lower-cased.
_HMAC_SCHEMES = frozenset({"hmac-sha256", "hmac_sha256", "hmac"})

#: Minimum HMAC credential length. Carried over verbatim from the delivery
#: service's own floor, which C1 folded into this boundary rather than dropping:
#: a secret shorter than this is brute-forceable and the pre-C1 behaviour was to
#: refuse to sign with it (and say so) rather than emit a weak signature.
_MIN_HMAC_SECRET_CHARS = 32

#: Per-request timeout, matching what the three senders used before C1.
_TIMEOUT_SECONDS = 10.0

#: ``X-AdCP-Key-Id`` value for the legacy HMAC arm. The scheme has no key registry —
#: the SDK echoes this for receiver-side rotation only, and it is not part of the
#: signature.
_LEGACY_HMAC_KEY_ID = "adcp-legacy-hmac"

#: Tenants already warned about having no signing key. security.mdx obliges an
#: honest posture, not a log line per webhook: without this the WARNING fires on
#: EVERY delivery for every keyless tenant, which today is all of them.
_keyless_warned: set[str] = set()
_keyless_lock = threading.Lock()


@dataclass(frozen=True)
class _UnauthenticatedStrategy:
    """No auth headers at all — the pre-#1291 wire, kept reachable on purpose.

    Two registrations land here: a tenant with no active signing key (the 100% case
    until keys are provisioned — ``salesagent-7x8t``), and a legacy registration
    carrying no credential. Both must still DELIVER; what they must not do is
    acquire an RFC 9421 signature they never earned.

    It implements the SDK's public ``WebhookAuthStrategy`` protocol and is bound
    through ``WebhookSender._from_strategy``, the same internal constructor the SDK's
    own ``from_bearer_token`` / ``from_adcp_legacy_hmac`` classmethods use. The SDK
    exposes no unauthenticated constructor, and the alternative — keeping a raw
    ``httpx`` POST in the delivery services for this one case — would reintroduce
    exactly the second sending path the boundary exists to remove (and
    ``tests/unit/test_architecture_webhook_sender_boundary.py`` would catch it).
    """

    def build_auth_headers(self, *, method: str, url: str, body: bytes) -> dict[str, str]:
        return {}

    def reserved_headers(self) -> frozenset[str]:
        return frozenset({"content-length", "content-type", "host"})


def legacy_auth_mode(config: PushNotificationConfig | None) -> str | None:
    """Which legacy mode *config* selected, or ``None`` for the RFC 9421 arm.

    ``None`` is returned only when ``authentication`` is ABSENT, which is the default
    shape of every registration — so RFC 9421 is the default and legacy can never be
    a silent global fallback; it is reachable only when a buyer explicitly asked for
    it (security.mdx @ v3.1.1 :1424, and the research note on ``legacy_hmac_fallback``
    being a seller-level DECLARATION rather than a per-receiver switch).

    Case-insensitive by construction: ``authentication_type`` is persisted verbatim
    from the buyer's ``authentication.schemes[0]``, so ``"Bearer"`` and ``"bearer"``
    are the same registration and used to reach two different code paths.

    The retired second selector is ``webhook_secret``: it is read nowhere else after
    C1 and was never written by production, so honouring it would be the "signed two
    ways" shape :1425 forbids.
    """
    if config is None:
        return None
    scheme = (config.authentication_type or "").strip().lower()
    token = (config.authentication_token or "").strip()
    if not scheme and not token:
        return None
    if not token:
        return LEGACY_UNCREDENTIALED
    if scheme not in _HMAC_SCHEMES:
        return LEGACY_BEARER
    if len(token) < _MIN_HMAC_SECRET_CHARS:
        # A short HMAC key is not a signature, it is a shared password. The
        # registration still selects the LEGACY arm (:1425 forbids answering it
        # with RFC 9421), so the honest outcome is an unauthenticated delivery
        # plus a loud log — the same posture the pre-C1 delivery service took.
        logger.warning(
            "Webhook receiver %s registered HMAC-SHA256 with a %d-character secret; "
            "at least %d are required, so this delivery goes out UNSIGNED",
            config.url,
            len(token),
            _MIN_HMAC_SECRET_CHARS,
        )
        return LEGACY_UNCREDENTIALED
    return LEGACY_HMAC


def _log_legacy_registration(config: PushNotificationConfig, mode: str) -> None:
    """security.mdx @ v3.1.1 :1464 — "Sellers MUST log" every legacy registration.

    The inbound twin of this obligation is ``src/core/signing/operations.py``
    ``_authenticated_configs`` / ``_forces_signature``; the shared rule is "a
    non-empty ``authentication`` block opts this receiver out of RFC 9421".
    """
    logger.warning(
        "Webhook receiver %s opted into the LEGACY authentication scheme %r (mode=%s); "
        "RFC 9421 webhook signing is suppressed for it (security.mdx @ v3.1.1 :1424, :1464). "
        "Legacy HMAC-SHA256 is removed in AdCP 4.0.",
        config.url,
        config.authentication_type,
        mode,
    )


def _warn_keyless_once(tenant_id: str | None) -> None:
    """WARN once per tenant per process that deliveries are going out unsigned."""
    key = tenant_id or "<unknown-tenant>"
    with _keyless_lock:
        if key in _keyless_warned:
            return
        _keyless_warned.add(key)
    logger.warning(
        "Tenant %s has no ACTIVE signing key, so its outbound AdCP webhooks are delivered "
        "UNSIGNED. This is the honest posture only while webhook_signing.supported is false; "
        "provision a request-signing key to enable the RFC 9421 profile (#1291).",
        key,
    )


def reset_keyless_warning_state() -> None:
    """Forget which tenants have been warned. For rotation tooling and test isolation."""
    with _keyless_lock:
        _keyless_warned.clear()


def _unauthenticated_sender(client: httpx.AsyncClient | None) -> WebhookSender:
    return WebhookSender._from_strategy(
        _UnauthenticatedStrategy(),
        key_id="unauthenticated",
        client=client,
        timeout_seconds=_TIMEOUT_SECONDS,
        allow_private_destinations=False,
        allowed_destination_ports=None,
    )


def _rfc9421_sender(
    *,
    tenant_id: str | None,
    repo: SigningKeyRepository | None,
    now: datetime,
    client: httpx.AsyncClient | None,
) -> WebhookSender:
    """The RFC 9421 arm: the tenant's own key, or an honest unsigned delivery.

    The algorithm about to go on the wire is checked against the posture this tenant
    could honestly DECLARE before the sender is handed back — declaring an algorithm
    we never emit, or emitting one we never declared, is the dishonesty the STRICT
    declaration policy exists to prevent, and it is cheaper to refuse here than to
    have every receiver reject the delivery.
    """
    if repo is None or tenant_id is None:
        _warn_keyless_once(tenant_id)
        return _unauthenticated_sender(client)

    posture = webhook_signing_posture(repo, now=now)
    if not posture.supported:
        _warn_keyless_once(tenant_id)
        return _unauthenticated_sender(client)

    material = resolve_signing_material(repo, tenant_id=tenant_id, now=now)
    declared = {enum_value(alg) for alg in posture.algorithms or ()}
    if material.alg not in declared:
        raise AdCPConfigurationError(
            f"Tenant {tenant_id!r} would sign outbound webhooks with alg {material.alg!r} while "
            f"declaring webhook_signing.algorithms={sorted(declared)}; a receiver validating the "
            "declaration against the wire would reject every delivery"
        )

    return WebhookSender(
        private_key=material.private_key,
        key_id=material.kid,
        alg=material.alg,
        client=client,
        timeout_seconds=_TIMEOUT_SECONDS,
    )


def build_webhook_sender(
    *,
    config: PushNotificationConfig | None,
    tenant_id: str | None,
    repo: SigningKeyRepository | None,
    now: datetime,
    client: httpx.AsyncClient | None = None,
) -> WebhookSender:
    """The sender *config*'s receiver has earned — exactly one authentication mode.

    ``client`` is the operator-supplied transport (see the module docstring). Omit it
    and the SDK owns its own client, which is what callers grading only
    ``signs_with_rfc9421`` want: no socket is opened either way.
    """
    mode = legacy_auth_mode(config)
    if mode is not None:
        assert config is not None  # legacy_auth_mode returns None for a missing config
        _log_legacy_registration(config, mode)
        if mode == LEGACY_HMAC:
            return WebhookSender.from_adcp_legacy_hmac(
                (config.authentication_token or "").encode("utf-8"),
                key_id=_LEGACY_HMAC_KEY_ID,
                client=client,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        if mode == LEGACY_BEARER:
            return WebhookSender.from_bearer_token(
                config.authentication_token or "",
                client=client,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        return _unauthenticated_sender(client)

    return _rfc9421_sender(tenant_id=tenant_id, repo=repo, now=now, client=client)


@contextmanager
def _signing_repo(repo: SigningKeyRepository | None, tenant_id: str | None) -> Iterator[SigningKeyRepository | None]:
    """The tenant-scoped signing repository, opening a session only if we must.

    Callers that already hold a session (``webhook_delivery_service`` reads its
    receiver rows inside one) pass their own repository; callers that do not get one
    opened here rather than each growing its own ``get_db_session`` + repository
    construction — the duplication the DRY invariant names.
    """
    if repo is not None or tenant_id is None:
        yield repo
        return

    from src.core.database.database_session import get_db_session
    from src.core.database.repositories.signing_key import SigningKeyRepository

    with get_db_session() as session:
        yield SigningKeyRepository(session, tenant_id)


@asynccontextmanager
async def adcp_webhook_sender(
    *,
    config: PushNotificationConfig | None,
    tenant_id: str | None,
    repo: SigningKeyRepository | None = None,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[WebhookSender]:
    """A configured sender bound to an HTTP client.

    A caller with a long-lived pool (``ProtocolWebhookService``) passes it in and
    keeps owning its lifecycle; callers without one — the two synchronous senders,
    which run each delivery on their own event loop and so cannot share a client —
    get a per-delivery client opened and closed here.
    """
    async with AsyncExitStack() as stack:
        if client is None:
            client = await stack.enter_async_context(httpx.AsyncClient(timeout=_TIMEOUT_SECONDS))
        resolved_repo = stack.enter_context(_signing_repo(repo, tenant_id))
        yield build_webhook_sender(
            config=config,
            tenant_id=tenant_id,
            repo=resolved_repo,
            now=now or datetime.now(UTC),
            client=client,
        )


async def deliver_adcp_webhook(
    *,
    url: str,
    payload: dict[str, Any],
    idempotency_key: str,
    config: PushNotificationConfig | None,
    tenant_id: str | None,
    repo: SigningKeyRepository | None = None,
    now: datetime | None = None,
    extra_headers: Mapping[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> WebhookDeliveryResult:
    """Serialize, authenticate and POST one AdCP webhook — the single delivery act.

    ``idempotency_key`` is generated ONCE PER EVENT by the caller and reused across
    its retries; the SDK injects it into the signed body, so a fresh key per attempt
    would defeat receiver-side dedup.
    """
    async with adcp_webhook_sender(config=config, tenant_id=tenant_id, repo=repo, now=now, client=client) as sender:
        return await sender.send_raw(
            url=url,
            idempotency_key=idempotency_key,
            payload=payload,
            extra_headers=extra_headers,
        )


def deliver_adcp_webhook_sync(
    *,
    url: str,
    payload: dict[str, Any],
    idempotency_key: str,
    config: PushNotificationConfig | None,
    tenant_id: str | None,
    repo: SigningKeyRepository | None = None,
    now: datetime | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> WebhookDeliveryResult:
    """:func:`deliver_adcp_webhook` for the two senders that are still synchronous.

    ``run_async_in_sync_context`` is the codebase's existing sync->async hop, NOT a
    second one invented here. Using it adds two call sites to a helper the owner has
    recorded as a band-aid for the synchronous-adapter architecture
    (``.claude/notes/async-sync-architecture.md``) — named debt, not silent debt: the
    real fix is moving webhook delivery onto the background worker.
    """
    from src.core.validation_helpers import run_async_in_sync_context

    return run_async_in_sync_context(
        deliver_adcp_webhook(
            url=url,
            payload=payload,
            idempotency_key=idempotency_key,
            config=config,
            tenant_id=tenant_id,
            repo=repo,
            now=now,
            extra_headers=extra_headers,
        )
    )

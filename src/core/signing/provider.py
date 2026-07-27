"""Resolve a ``SigningProvider`` for a tenant: row -> ref -> PEM -> tripwire -> provider.

We construct ``adcp.signing.InMemorySigningProvider``; we never subclass it and
never implement the Protocol ourselves. Its ``__init__`` already type- and
curve-checks the private key against the algorithm, so this module does not.

Contract reminder, because getting it wrong is silent: ``sign`` is ASYNC, and
``key_id()`` / ``algorithm()`` are METHODS. Attribute access yields a truthy
bound method, which is how ``<bound method ...>`` ends up in a ``keyid`` header.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol

from adcp.signing import InMemorySigningProvider, load_private_key_pem, pem_to_adcp_jwk
from adcp.signing.provider import SigningProvider

from src.core.database.models import SigningKey
from src.core.database.repositories.signing_key import SigningKeyRepository
from src.core.exceptions import AdCPConfigurationError
from src.core.signing.algorithms import REQUEST_SIGNING, narrow_alg, narrow_purpose

# The cache holds the expensive, PURELY DERIVED part: PEM read + key parse +
# tripwire. It deliberately does NOT cache the DB read — resolution keys on
# ``kid``, and learning the kid means querying Postgres, so the round-trip
# happens on every call regardless. Caching the row instead would be the thing
# that lets a revoked key keep signing.
#
# Revocation converges two ways: a revoked row is refused BEFORE the cache is
# consulted (immediate, because the row is always freshly read), and the TTL
# bounds the other drift this cache can hide — a PEM rotated behind an unchanged
# ``private_key_ref``, which the tripwire only sees on a cache miss.
_CACHE_TTL_SECONDS = 60.0
_provider_cache: dict[tuple[str, str], tuple[float, SigningProvider]] = {}


class _RefResolver(Protocol):
    def __call__(self, locator: str) -> bytes: ...


def _read_file_ref(locator: str) -> bytes:
    path = Path(locator)
    if not path.is_file():
        raise AdCPConfigurationError(f"Signing key file {locator!r} does not exist or is not a file")
    return path.read_bytes()


def _read_env_ref(locator: str) -> bytes:
    value = os.getenv(locator)
    if not value:
        raise AdCPConfigurationError(f"Signing key env var {locator!r} is unset or empty")
    return value.encode()


# Every scheme this process knows how to resolve. Which of them a DEPLOYMENT will
# actually resolve is the agent-level ``SigningConfig.allowed_key_ref_schemes``
# gate below, so production can forbid ``file:`` without touching tenant rows.
_REF_RESOLVERS: dict[str, _RefResolver] = {
    "file": _read_file_ref,
    "env": _read_env_ref,
}


def _resolve_key_ref(private_key_ref: str) -> bytes:
    """Resolve a scheme-prefixed reference to PEM bytes."""
    from src.core.config import get_config

    scheme, separator, locator = private_key_ref.partition(":")
    if not separator or not locator:
        raise AdCPConfigurationError(
            f"private_key_ref {private_key_ref!r} is not scheme-prefixed (expected 'env:NAME' or 'file:/path')"
        )

    allowed = get_config().signing.key_ref_scheme_list
    if scheme not in allowed:
        raise AdCPConfigurationError(
            f"private_key_ref scheme {scheme!r} is not permitted by this deployment (allowed: {allowed})"
        )
    resolver = _REF_RESOLVERS.get(scheme)
    if resolver is None:
        raise AdCPConfigurationError(f"private_key_ref scheme {scheme!r} has no resolver")
    return resolver(locator)


def _select_row(
    repo: SigningKeyRepository, *, tenant_id: str, purpose: str, now: datetime, kid: str | None
) -> SigningKey:
    """Pick the row to sign with: an explicit *kid* wins, else the active key.

    The ``kid`` axis is what expresses "this signing surface uses that key" —
    security.mdx's blast-radius isolation publishes a SECOND request-signing key
    under a distinct kid, so isolation comes from the kid, not from a distinct
    purpose. Without this axis both surfaces necessarily share one key.

    A revoked key never signs, however it was selected. ``active_at`` already
    excludes revoked rows; the explicit-kid path has to say so itself.
    """
    if kid is not None:
        row = repo.get_by_kid(kid)
        if row is None:
            raise AdCPConfigurationError(f"Tenant {tenant_id!r} has no signing key with kid {kid!r}")
        if row.revoked_at is not None:
            raise AdCPConfigurationError(
                f"Signing key {kid!r} for tenant {tenant_id!r} was revoked at {row.revoked_at.isoformat()}"
            )
        return row

    row = repo.active_at(now=now, purpose=purpose)
    if row is None:
        raise AdCPConfigurationError(f"Tenant {tenant_id!r} has no active {purpose} signing key at {now.isoformat()}")
    return row


def _build_provider(row: SigningKey) -> SigningProvider:
    """Load the private half behind *row* and bind it to the row's published JWK.

    The tripwire (security.mdx "assert public key at init") is the middle step:
    re-derive the public JWK from the PEM the reference resolves to and compare
    it against the JWK the row publishes. A file rotated behind an unchanged
    ``private_key_ref`` otherwise yields signatures every counterparty rejects,
    with nothing wrong locally to look at — so a mismatch fails loudly here
    rather than silently on every signed call.

    The passphrase is resolved ONCE and threaded into both ``load_private_key_pem``
    and ``pem_to_adcp_jwk``: omitting it from the second is a false alarm the
    moment a passphrase is configured, and it reads exactly like a real mismatch.
    """
    from src.core.config import get_config

    passphrase = get_config().signing.key_passphrase
    pem = _resolve_key_ref(row.private_key_ref)

    private_key = load_private_key_pem(pem, password=passphrase)
    derived_jwk = pem_to_adcp_jwk(
        pem,
        kid=row.kid,
        purpose=narrow_purpose(row.purpose),
        password=passphrase,
    )
    if derived_jwk != row.public_jwk:
        raise AdCPConfigurationError(
            f"Signing key {row.kid!r} for tenant {row.tenant_id!r} does not match the public JWK it "
            "publishes — the key material behind its private_key_ref has changed. Signatures made with "
            "it would be rejected by every counterparty."
        )

    return InMemorySigningProvider(
        private_key=private_key,
        key_id=row.kid,
        algorithm=narrow_alg(row.alg),
    )


def resolve_signing_provider(
    repo: SigningKeyRepository,
    *,
    tenant_id: str,
    purpose: str = REQUEST_SIGNING,
    now: datetime,
    kid: str | None = None,
) -> SigningProvider:
    """Return the ``SigningProvider`` *tenant_id* signs *purpose* with at *now*.

    Pass ``kid`` to designate a specific key; otherwise the active key wins.

    No session is opened here — the caller supplies the repository, so this stays
    callable from an ``_impl`` without reaching for ``get_db_session()``.

    Raises:
        AdCPConfigurationError: no key resolves, the key is revoked, its
            reference scheme is forbidden, or the tripwire fires.
    """
    row = _select_row(repo, tenant_id=tenant_id, purpose=purpose, now=now, kid=kid)

    cache_key = (tenant_id, row.kid)
    cached = _provider_cache.get(cache_key)
    if cached is not None and time.monotonic() < cached[0]:
        return cached[1]

    provider = _build_provider(row)
    # Cache success, never errors — a transient resolution failure must not pin
    # itself for the TTL.
    _provider_cache[cache_key] = (time.monotonic() + _CACHE_TTL_SECONDS, provider)
    return provider


def clear_signing_provider_cache() -> None:
    """Drop every cached provider. For rotation tooling and test isolation."""
    _provider_cache.clear()

"""Shared helpers for the A2 signing-key integration tests (salesagent-z6nr.8).

One home for the three things both signing test modules do — build the
tenant-scoped repository off the harness session, provision a key through
production, and resolve a provider through production — so a signature change in
``src.core.signing`` lands in one place instead of once per test module.

Deliberately thin: these forward to production entry points and add nothing.
Anything that decides or asserts belongs in the test, not here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# An RFC 9421 signature base: the canonicalized component list joined by LF with
# ``"@signature-params"`` last. A SigningProvider signs this as a RAW MESSAGE —
# never as a pre-hashed digest — so passing it verbatim is what the profile means.
SIGNATURE_BASE = (
    b'"@method": POST\n'
    b'"@target-uri": https://seller.example/mcp/\n'
    b'"@signature-params": ("@method" "@target-uri");created=1767225600;'
    b'keyid="adcp-key";alg="ed25519"'
)

REQUEST_SIGNING = "request-signing"


def signing_key_repo(env: Any, tenant_id: str) -> Any:
    """Commit pending factory data and build a tenant-scoped SigningKeyRepository."""
    from src.core.database.repositories.signing_key import SigningKeyRepository

    return SigningKeyRepository(env.get_session(), tenant_id)


def provision_key(
    repo: Any,
    tenant_id: str,
    kid: str,
    key_path: Path,
    *,
    alg: str = "ed25519",
    purpose: str = REQUEST_SIGNING,
) -> Any:
    """Mint a keypair through production and return the persisted SigningKey row."""
    from src.core.signing.keys import provision_signing_key

    return provision_signing_key(
        repo,
        tenant_id=tenant_id,
        alg=alg,
        kid=kid,
        purpose=purpose,
        key_path=key_path,
    )


def resolve_provider(
    repo: Any,
    tenant_id: str,
    *,
    now: datetime,
    kid: str | None = None,
    purpose: str = REQUEST_SIGNING,
) -> Any:
    """Resolve a SigningProvider through production (row -> ref -> PEM -> tripwire)."""
    from src.core.signing.provider import resolve_signing_provider

    return resolve_signing_provider(repo, tenant_id=tenant_id, purpose=purpose, now=now, kid=kid)


def just_after_provisioning() -> datetime:
    """An instant safely inside the activity window of a key provisioned just now.

    ``provision_signing_key`` stamps ``not_before`` from the wall clock, so a
    fixed literal instant would sit outside the window and make window-sensitive
    resolution fail for reasons that have nothing to do with the behavior tested.
    """
    return datetime.now(UTC) + timedelta(minutes=1)

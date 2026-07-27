"""Provision this agent's own signing keys. Zero hand-rolled crypto.

``adcp.signing.keygen.generate_signing_keypair`` mints the keypair — it is the
programmatic counterpart of the ``adcp-keygen`` CLI and emits a JWK whose
``kty``/``crv``/``alg``/``use``/``key_ops``/``adcp_use``/``kid`` members are
already byte-shape-identical to the publication shape the spec mandates. We
assemble no JWK and touch no curve.

What this module owns is the part the SDK deliberately leaves to the caller:
where the private half goes, and how the row that references it is written.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from adcp.signing import generate_signing_keypair

from src.core.database.models import SigningKey
from src.core.database.repositories.signing_key import SigningKeyRepository
from src.core.exceptions import AdCPConfigurationError
from src.core.signing.algorithms import REQUEST_SIGNING, keygen_alg, narrow_alg, narrow_purpose


def _write_private_key_pem(path: Path, pem: bytes) -> None:
    """Write *pem* to *path*, mode 0600, refusing to clobber an existing file.

    ``Path.write_bytes`` inherits the process umask — typically 0644, i.e. a
    world-readable private key — which the SDK's own quickstart calls out as the
    thing not to do. ``O_EXCL`` is the other half: provisioning over a live key
    would strand every counterparty holding the published public half, with no
    local signal until signatures start being rejected.

    Raises:
        FileExistsError: *path* already exists. Deliberately not caught.
    """
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, pem)
    finally:
        os.close(fd)


def provision_signing_key(
    repo: SigningKeyRepository,
    *,
    tenant_id: str,
    alg: str,
    kid: str,
    key_path: Path,
    purpose: str = REQUEST_SIGNING,
) -> SigningKey:
    """Mint a keypair for *tenant_id*, store the PEM at *key_path*, persist the row.

    The ``kid`` is always explicit. The SDK's default kid documents itself as
    "collision-resistant within a single process but does not guarantee
    uniqueness across processes" and states that callers managing rotation MUST
    supply their own — we manage rotation, so the default never fires.

    The key is minted open-ended (``not_after`` NULL): a newly provisioned key is
    the current key, and the current key has no upper bound. Retirement is a
    later revocation.

    The PEM is written BEFORE the row exists. A row whose ``private_key_ref``
    resolves to nothing is the failure the init tripwire has to catch later;
    ordering the write first means an ``O_EXCL`` collision leaves no row at all.

    Raises:
        FileExistsError: *key_path* already holds key material.
        AdCPConfigurationError: *alg*/*purpose* are outside the profile, or
            *tenant_id* does not match the repository's tenant scope.
    """
    if tenant_id != repo.tenant_id:
        raise AdCPConfigurationError(
            f"Cannot provision a signing key for tenant {tenant_id!r} through a repository scoped to {repo.tenant_id!r}"
        )
    if not kid:
        raise AdCPConfigurationError("A signing key kid must be a non-empty string")

    # Validate against OUR value-sets before the SDK sees them, so an off-profile
    # value fails with our message and never reaches the DB CHECK.
    stored_alg = narrow_alg(alg)
    stored_purpose = narrow_purpose(purpose)

    # Resolved once here and threaded through — the tripwire in
    # src/core/signing/provider.py needs the same passphrase to re-derive the JWK.
    from src.core.config import get_config

    passphrase = get_config().signing.key_passphrase

    pem, public_jwk = generate_signing_keypair(
        alg=keygen_alg(stored_alg),
        kid=kid,
        purpose=stored_purpose,
        passphrase=passphrase,
    )

    _write_private_key_pem(key_path, pem)

    return repo.create_from_keypair(
        kid=kid,
        alg=stored_alg,
        purpose=stored_purpose,
        public_jwk=public_jwk,
        private_key_ref=f"file:{key_path}",
        not_before=datetime.now(UTC),
        not_after=None,
    )

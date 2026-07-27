"""Integration tests for signing-key provisioning and SigningProvider resolution.

TDD RED for salesagent-z6nr.8 (A2 — signing key lifecycle). Nothing here passes
until ``src/core/signing/{keys,provider,algorithms}.py``, the ``SigningKey``
model and its migration exist.

This file grades the KEY-MATERIAL half of A2's core invariant: that the key we
sign with, the key we publish, and the key material on disk can never silently
disagree. Concretely —

* Two overlapping active ``request-signing`` keys, distinguished only by ``kid``,
  BOTH resolve through production and BOTH produce signatures that verify against
  their own STORED ``public_jwk`` (and not against the other's). This is the one
  mechanism that serves both rotation overlap and the webhook blast-radius
  isolation security.mdx:955 describes ("isolation comes from the ``kid``").
  Resolution goes through ``resolve_signing_provider(..., kid=...)`` — a test
  that hand-constructs ``InMemorySigningProvider`` grades nothing, and skips the
  tripwire it is supposed to be exercising.
* The private-key PEM is written 0600 and with ``O_EXCL`` — a second write to the
  same path fails rather than clobbering live key material.
* The init tripwire (security.mdx:951) fires on a GENUINE mismatch and — the
  failure mode actually worth guarding — does NOT false-alarm on a healthy
  passphrase-encrypted PEM.

Note the SDK's provider contract: ``sign`` is ASYNC, and ``key_id()`` /
``algorithm()`` are METHODS. Attribute access yields a truthy bound method, which
is how ``<bound method ...>`` ends up in a ``keyid`` header.
"""

from __future__ import annotations

import asyncio
import os
import stat
from datetime import UTC, datetime

import pytest
from adcp.signing import alg_for_jwk, public_key_from_jwk, verify_signature

from tests.harness._base import BareIntegrationEnv
from tests.helpers.signing import (
    REQUEST_SIGNING,
    SIGNATURE_BASE,
    just_after_provisioning,
    provision_key,
    resolve_provider,
    signing_key_repo,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# NULL not_after means open-ended, so a key provisioned today must still resolve
# at an arbitrarily distant instant.
_FAR_FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def _verifies(row, signature: bytes) -> bool:
    """Verify *signature* against the row's STORED public JWK, via SDK crypto only.

    Zero hand-rolled crypto: ``public_key_from_jwk`` rehydrates the key,
    ``alg_for_jwk`` maps the JWK's own ``alg`` member ("EdDSA"/"ES256") back to
    the RFC 9421 name the profile uses ("ed25519"/"ecdsa-p256-sha256").
    """
    return verify_signature(
        alg=alg_for_jwk(row.public_jwk),
        public_key=public_key_from_jwk(row.public_jwk),
        signature_base=SIGNATURE_BASE,
        signature=signature,
    )


class TestOverlappingActiveKeys:
    """Two active request-signing keys under one tenant, distinguished by kid."""

    def test_both_keys_resolve_and_both_signatures_verify(self, integration_db, tmp_path):
        from tests.factories import TenantFactory

        tenant_id = "sk_two_t1"
        with BareIntegrationEnv() as env:
            TenantFactory(tenant_id=tenant_id)
            repo = signing_key_repo(env, tenant_id)

            row_a = provision_key(repo, tenant_id, "adcp-key-a", tmp_path / "a.pem")
            row_b = provision_key(repo, tenant_id, "adcp-key-b", tmp_path / "b.pem", alg="ecdsa-p256-sha256")
            now = just_after_provisioning()

            # Distinct rows, distinct published material, same purpose.
            assert {row_a.kid, row_b.kid} == {"adcp-key-a", "adcp-key-b"}
            assert row_a.public_jwk != row_b.public_jwk
            assert row_a.purpose == row_b.purpose == REQUEST_SIGNING

            signatures = {}
            for row, expected_alg in ((row_a, "ed25519"), (row_b, "ecdsa-p256-sha256")):
                provider = resolve_provider(repo, tenant_id, now=now, kid=row.kid)

                # key_id()/algorithm() are METHODS on the SDK provider.
                assert provider.key_id() == row.kid
                assert provider.algorithm() == expected_alg
                assert row.alg == expected_alg

                # The JWK we publish must announce the same algorithm the column
                # stores — the "third alg namespace" trap (JWK alg is EdDSA/ES256).
                assert alg_for_jwk(row.public_jwk) == row.alg
                # Publication shape: the JWK carries its own kid and adcp_use.
                assert row.public_jwk["kid"] == row.kid
                assert row.public_jwk["adcp_use"] == REQUEST_SIGNING

                signature = asyncio.run(provider.sign(SIGNATURE_BASE))
                assert _verifies(row, signature), f"{row.kid} signature failed its own JWK"
                signatures[row.kid] = signature

            # Each signature verifies ONLY under its own published key — proof the
            # kid axis selected different key material, not the same key twice.
            assert not _verifies(row_b, signatures["adcp-key-a"])
            assert not _verifies(row_a, signatures["adcp-key-b"])

    def test_open_ended_key_resolves_without_an_explicit_kid(self, integration_db, tmp_path):
        """not_after IS NULL is open-ended: the sole active key still resolves.

        Without an explicit kid the resolver falls back to ``active_at``, and the
        current key is always open-ended — so a NULL-blind window predicate leaves
        the tenant with no signable key at all.
        """
        from tests.factories import TenantFactory

        tenant_id = "sk_open_t1"
        with BareIntegrationEnv() as env:
            TenantFactory(tenant_id=tenant_id)
            repo = signing_key_repo(env, tenant_id)
            row = provision_key(repo, tenant_id, "adcp-only-key", tmp_path / "only.pem")

            assert row.not_after is None, "provisioning must mint the current key open-ended"

            provider = resolve_provider(repo, tenant_id, now=_FAR_FUTURE)

            assert provider.key_id() == "adcp-only-key"
            assert _verifies(row, asyncio.run(provider.sign(SIGNATURE_BASE)))


class TestPrivateKeyFileHandling:
    """The PEM is written 0600 and O_EXCL — no umask leak, no silent clobber."""

    def test_pem_is_written_mode_0600(self, integration_db, tmp_path):
        """0644 is what ``Path.write_bytes`` produces under the usual umask.

        A world-readable private key is the failure this asserts against, so the
        mode is compared exactly rather than masked for the owner bits.
        """
        from tests.factories import TenantFactory

        tenant_id = "sk_mode_t1"
        key_path = tmp_path / "mode.pem"
        with BareIntegrationEnv() as env:
            TenantFactory(tenant_id=tenant_id)
            repo = signing_key_repo(env, tenant_id)
            row = provision_key(repo, tenant_id, "adcp-mode-key", key_path)

            assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600
            assert key_path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")

            # The row holds a REFERENCE, never the material itself.
            assert row.private_key_ref.startswith("file:")
            assert str(key_path) in row.private_key_ref
            assert "PRIVATE KEY" not in row.private_key_ref

    def test_second_provision_to_the_same_path_raises_and_preserves_the_key(self, integration_db, tmp_path):
        """O_EXCL: provisioning over a live key must fail, not overwrite it.

        Overwriting would strand every counterparty holding the published public
        half, with no local signal until signatures start being rejected.
        """
        from tests.factories import TenantFactory

        tenant_id = "sk_excl_t1"
        key_path = tmp_path / "excl.pem"
        with BareIntegrationEnv() as env:
            TenantFactory(tenant_id=tenant_id)
            repo = signing_key_repo(env, tenant_id)
            provision_key(repo, tenant_id, "adcp-first", key_path)
            original = key_path.read_bytes()

            with pytest.raises(FileExistsError):
                provision_key(repo, tenant_id, "adcp-second", key_path)

            assert key_path.read_bytes() == original


class TestInitTripwire:
    """security.mdx:951 — assert the public key at signer init, fail loudly on drift."""

    def test_mismatched_pem_behind_an_unchanged_ref_raises(self, integration_db, tmp_path):
        """The row's stored JWK and the PEM the ref resolves to must agree.

        This is the silent failure the tripwire exists for: rotate the file behind
        an unchanged ``private_key_ref`` and every signature is rejected by every
        counterparty, with nothing wrong locally to look at.
        """
        from src.core.exceptions import AdCPConfigurationError
        from tests.factories import SigningKeyFactory, TenantFactory

        tenant_id = "sk_trip_t1"
        with BareIntegrationEnv() as env:
            tenant = TenantFactory(tenant_id=tenant_id)
            repo = signing_key_repo(env, tenant_id)

            row_a = provision_key(repo, tenant_id, "adcp-real-a", tmp_path / "real_a.pem")
            row_b = provision_key(repo, tenant_id, "adcp-real-b", tmp_path / "real_b.pem")

            # A row pointing at A's PEM while publishing B's public half — exactly
            # the state a file rotated behind an unchanged ref leaves behind.
            SigningKeyFactory(
                tenant=tenant,
                kid="adcp-drifted",
                alg=row_b.alg,
                public_jwk={**row_b.public_jwk, "kid": "adcp-drifted"},
                private_key_ref=row_a.private_key_ref,
            )
            now = just_after_provisioning()

            with pytest.raises(AdCPConfigurationError):
                resolve_provider(repo, tenant_id, now=now, kid="adcp-drifted")

            # Control: the untouched rows still resolve, so the tripwire is
            # discriminating between drifted and healthy, not failing everything.
            assert resolve_provider(repo, tenant_id, now=now, kid="adcp-real-a").key_id() == "adcp-real-a"

    def test_passphrase_encrypted_pem_passes_the_tripwire(self, integration_db, tmp_path, monkeypatch):
        """A healthy ENCRYPTED PEM must pass — the guarded failure is a FALSE alarm.

        ``pem_to_adcp_jwk`` takes ``password``; omitting it means that the moment
        ``ADCP_SIGNING_KEY_PASSPHRASE_ENV`` is configured, the tripwire raises on a
        perfectly healthy key at provider init — reading exactly like a genuine key
        mismatch. The passphrase must be resolved once and threaded into both
        ``load_private_key_pem`` and ``pem_to_adcp_jwk``.
        """
        from tests.factories import TenantFactory

        monkeypatch.setenv("ADCP_SIGNING_KEY_PASSPHRASE_ENV", "SIGNING_TEST_PASSPHRASE")
        monkeypatch.setenv("SIGNING_TEST_PASSPHRASE", "correct-horse-battery-staple")
        # Drop the cached AppConfig so SigningConfig re-reads the env above.
        monkeypatch.setattr("src.core.config._config", None, raising=False)

        tenant_id = "sk_pass_t1"
        key_path = tmp_path / "encrypted.pem"
        with BareIntegrationEnv() as env:
            TenantFactory(tenant_id=tenant_id)
            repo = signing_key_repo(env, tenant_id)
            row = provision_key(repo, tenant_id, "adcp-encrypted", key_path)

            # Non-vacuity: the PEM really is encrypted, so the passphrase path ran.
            assert key_path.read_bytes().startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")

            provider = resolve_provider(repo, tenant_id, now=just_after_provisioning(), kid=row.kid)

            assert provider.key_id() == "adcp-encrypted"
            assert _verifies(row, asyncio.run(provider.sign(SIGNATURE_BASE)))

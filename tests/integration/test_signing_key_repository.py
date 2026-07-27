"""Integration tests for SigningKeyRepository and the signing_keys table constraints.

TDD RED for salesagent-z6nr.8 (A2 — signing key lifecycle). Nothing here passes
until the ``SigningKey`` model, its migration, and
``src/core/database/repositories/signing_key.py`` exist.

Core invariant under test: every signing key this agent uses exists as exactly
one row binding a unique ``kid`` to the public JWK we publish and to a reference
the process resolves for private material it never stores — so the key we sign
with, the key we publish, and the key material on disk can never silently
disagree.

This file grades the ROW-level half of that: the uniqueness the spec makes a MUST
(security.mdx:1074 — "Unique within the JWKS. MUST NOT collide with any other
entry's kid regardless of adcp_use"), the CHECKs that keep an off-profile
algorithm or a deprecated purpose out of material we publish, and the activity
window ``active_at`` resolves over. The key-material half — signing, verifying,
the init tripwire, PEM file handling — is in ``test_signing_provider.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from tests.harness._base import BareIntegrationEnv
from tests.helpers.signing import REQUEST_SIGNING, signing_key_repo

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Fixed instants — the window arithmetic must be evaluated against the caller's
# ``now``, never against wall-clock time.
_LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)
_MID = datetime(2026, 1, 1, tzinfo=UTC)
_EXPIRY = datetime(2026, 6, 1, tzinfo=UTC)
_FAR_FUTURE = datetime(2099, 1, 1, tzinfo=UTC)

_PURPOSE = REQUEST_SIGNING

# Shared with test_signing_provider.py via tests/helpers/signing.py.
_repo = signing_key_repo


class TestKidUniqueness:
    """UNIQUE(tenant_id, kid) — a spec MUST, enforced in the DB, scoped per tenant."""

    def test_duplicate_kid_in_one_tenant_is_rejected(self, integration_db):
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv():
            tenant = TenantFactory(tenant_id="sk_uniq_t1")
            SigningKeyFactory(tenant=tenant, kid="adcp-rot-2026-a")

            with pytest.raises(IntegrityError):
                SigningKeyFactory(tenant=tenant, kid="adcp-rot-2026-a")

    def test_same_kid_in_two_tenants_is_allowed(self, integration_db):
        """Uniqueness is per-tenant: each tenant publishes its own JWKS."""
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv() as env:
            t1 = TenantFactory(tenant_id="sk_uniq_t2")
            t2 = TenantFactory(tenant_id="sk_uniq_t3")
            SigningKeyFactory(tenant=t1, kid="adcp-shared-kid")
            SigningKeyFactory(tenant=t2, kid="adcp-shared-kid")

            assert _repo(env, "sk_uniq_t2").get_by_kid("adcp-shared-kid").tenant_id == "sk_uniq_t2"
            assert _repo(env, "sk_uniq_t3").get_by_kid("adcp-shared-kid").tenant_id == "sk_uniq_t3"


class TestValueSetChecks:
    """The CHECKs that keep non-profile material out of the published JWKS."""

    def test_alg_check_rejects_off_profile_algorithm(self, integration_db):
        """Only the two RFC 9421 profile algorithms may reach the column.

        The v3.1.1 algorithms enum is exactly ``ed25519`` / ``ecdsa-p256-sha256``;
        anything else is a value A3 would publish and every conformant verifier
        would reject. ``tests/unit/test_signing_alg_parity.py`` pins that the
        CHECK derives from SIGNING_ALG_VALUES rather than a hand-copied literal.
        """
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv():
            tenant = TenantFactory(tenant_id="sk_alg_t1")

            with pytest.raises(IntegrityError):
                SigningKeyFactory(tenant=tenant, kid="adcp-bad-alg", alg="rsa-pss-sha512")

    def test_alg_check_admits_both_profile_algorithms(self, integration_db):
        """Control for the rejection above — the CHECK must not be over-tight."""
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="sk_alg_t2")
            SigningKeyFactory(tenant=tenant, kid="adcp-ed", alg="ed25519")
            SigningKeyFactory(tenant=tenant, kid="adcp-es", alg="ecdsa-p256-sha256")

            repo = _repo(env, "sk_alg_t2")
            assert repo.get_by_kid("adcp-ed").alg == "ed25519"
            assert repo.get_by_kid("adcp-es").alg == "ecdsa-p256-sha256"

    def test_purpose_check_rejects_deprecated_webhook_signing(self, integration_db):
        """A2 mints request-signing only.

        ``webhook-signing`` is a deprecated purpose pending removal
        (security.mdx:1073, adcp#5555) and webhooks are signed with a
        request-signing key (security.mdx:955) — stamping it into material we
        publish is a self-inflicted migration. The SDK still ACCEPTS the value,
        so the DB is the only thing standing between an operator and minting it.
        """
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv():
            tenant = TenantFactory(tenant_id="sk_purpose_t1")

            with pytest.raises(IntegrityError):
                SigningKeyFactory(tenant=tenant, kid="adcp-webhook", purpose="webhook-signing")


class TestActiveAt:
    """active_at resolves the key valid at a caller-supplied instant."""

    def test_open_ended_key_resolves_at_any_future_instant(self, integration_db):
        """``not_after IS NULL`` means open-ended — read as +infinity, not as expired.

        The CURRENT key is always open-ended, so this is the common case, not an
        edge case: a NULL-blind window predicate would leave every tenant with no
        resolvable key at all.
        """
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="sk_win_t1")
            SigningKeyFactory(
                tenant=tenant,
                kid="adcp-current",
                not_before=_LONG_AGO,
                not_after=None,
            )
            repo = _repo(env, "sk_win_t1")

            assert repo.active_at(now=_MID, purpose=_PURPOSE).kid == "adcp-current"
            assert repo.active_at(now=_FAR_FUTURE, purpose=_PURPOSE).kid == "adcp-current"

    def test_window_is_half_open_and_excludes_expired(self, integration_db):
        """``[not_before, not_after)`` — inclusive lower bound, EXCLUSIVE upper bound."""
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="sk_win_t2")
            SigningKeyFactory(
                tenant=tenant,
                kid="adcp-retiring",
                not_before=_MID,
                not_after=_EXPIRY,
            )
            repo = _repo(env, "sk_win_t2")

            # Inside the window, and at the inclusive lower bound.
            assert repo.active_at(now=_MID, purpose=_PURPOSE).kid == "adcp-retiring"
            # At the exclusive upper bound, and past it.
            assert repo.active_at(now=_EXPIRY, purpose=_PURPOSE) is None
            assert repo.active_at(now=_FAR_FUTURE, purpose=_PURPOSE) is None
            # Before it began.
            assert repo.active_at(now=_LONG_AGO, purpose=_PURPOSE) is None

    def test_revoked_key_is_never_active(self, integration_db):
        """revoked_at wins over the window — an open-ended revoked key is NOT active.

        Without this, a revoked open-ended key would keep resolving forever: its
        window never closes.
        """
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="sk_win_t3")
            SigningKeyFactory(
                tenant=tenant,
                kid="adcp-compromised",
                not_before=_LONG_AGO,
                not_after=None,
                revoked_at=_MID,
            )

            assert _repo(env, "sk_win_t3").active_at(now=_FAR_FUTURE, purpose=_PURPOSE) is None

    def test_revoke_stamps_the_row_and_retires_it(self, integration_db):
        """repo.revoke(kid, at=...) is the transition, not a hand-set column."""
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="sk_revoke_t1")
            SigningKeyFactory(tenant=tenant, kid="adcp-to-revoke", not_before=_LONG_AGO, not_after=None)
            repo = _repo(env, "sk_revoke_t1")

            assert repo.active_at(now=_MID, purpose=_PURPOSE).kid == "adcp-to-revoke"

            repo.revoke("adcp-to-revoke", at=_MID)

            assert repo.get_by_kid("adcp-to-revoke").revoked_at == _MID
            assert repo.active_at(now=_MID, purpose=_PURPOSE) is None

    def test_active_at_is_tenant_scoped(self, integration_db):
        """One tenant's active key is never resolvable through another's repository."""
        from tests.factories import SigningKeyFactory, TenantFactory

        with BareIntegrationEnv() as env:
            t1 = TenantFactory(tenant_id="sk_scope_t1")
            TenantFactory(tenant_id="sk_scope_t2")
            SigningKeyFactory(tenant=t1, kid="adcp-t1-only", not_before=_LONG_AGO, not_after=None)

            assert _repo(env, "sk_scope_t1").active_at(now=_MID, purpose=_PURPOSE).kid == "adcp-t1-only"
            assert _repo(env, "sk_scope_t2").active_at(now=_MID, purpose=_PURPOSE) is None
            assert _repo(env, "sk_scope_t2").get_by_kid("adcp-t1-only") is None

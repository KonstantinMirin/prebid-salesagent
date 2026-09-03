"""The nested in-process creative sync borrows the outer media buy's client key.

``create_media_buy`` and ``update_media_buy`` upload their packages' inline creatives by
building a real ``SyncCreativesRequest`` and calling ``_sync_creatives_impl``. The key on
that nested request is the OUTER request's ``idempotency_key`` — the buyer's own
client-generated key, not an invented one, because the nested upload is part of that one
operation.

That borrowing collides with the verbatim success cache unless the at-most-once probe is
gated on ``request_hash``. The cache's lookup scope is the spec's (agent, account, key)
tuple with NO tool dimension (``IdempotencyAttemptRepository.find_by_key`` says so
explicitly: "a key reused by a different tool must hit this same row"). So a nested sync
probing with the borrowed key finds the MEDIA BUY's own row, and — having no transmission to
canonicalise, so presenting ``request_hash=None`` against a stored hash —
``raise_on_payload_conflict`` would reject a perfectly valid nested sync with
IDEMPOTENCY_CONFLICT.

These tests pin both halves of the gate: the in-process caller is exempt, and the transports
are not.
"""

import pytest

from src.core.exceptions import AdCPIdempotencyConflictError
from tests.factories import PrincipalFactory, TenantFactory
from tests.harness import CreativeSyncEnv
from tests.helpers.creative_test_helpers import creative_payload
from tests.helpers.idempotency_seeds import make_active_cached_success, seed_cached_success

#: The buyer's key on the OUTER create_media_buy / update_media_buy.
_OUTER_KEY = "outer-media-buy-key-0001"

#: The canonical hash of that outer request, as production stored it beside the key.
_OUTER_HASH = "0" * 64


class TestNestedSyncBorrowsTheOuterKey:
    """The gate on ``request_hash`` in ``_sync_creatives_impl``'s at-most-once probe."""

    def _seed(self, env: CreativeSyncEnv) -> None:
        tenant = TenantFactory(tenant_id="test_tenant")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        env._commit_factory_data()
        seed_cached_success(
            "test_tenant",
            "test_principal",
            _OUTER_KEY,
            response_model=make_active_cached_success(),
            payload_hash=_OUTER_HASH,
        )

    @pytest.mark.requires_db
    def test_in_process_sync_with_the_borrowed_key_executes(self, integration_db):
        """No transmission, so no probe: the nested sync runs instead of conflicting.

        Without the ``request_hash is not None`` gate this raises IDEMPOTENCY_CONFLICT — the
        probe hits the seeded create_media_buy row and compares its stored hash against the
        None the in-process caller carries.
        """
        with CreativeSyncEnv() as env:
            self._seed(env)

            response = env.call_impl(
                creatives=[creative_payload(creative_id="c_nested")],
                idempotency_key=_OUTER_KEY,
                # EXPLICIT None: this is what create_media_buy's and update_media_buy's
                # nested uploads pass, because neither has wire bytes to canonicalise.
                request_hash=None,
            )

        assert [r.creative_id for r in response.creatives] == ["c_nested"]
        assert response.creatives[0].action == "created"

    @pytest.mark.requires_db
    def test_a_transport_reusing_the_same_key_still_conflicts(self, integration_db):
        """The gate exempts the in-process caller ONLY — it does not disable the conflict.

        A transport canonicalises what arrived, so it presents a real hash. Reusing the media
        buy's key for a sync_creatives payload must still be refused, which is what stops the
        gate from being a way to opt out of at-most-once.
        """
        with CreativeSyncEnv() as env:
            self._seed(env)

            with pytest.raises(AdCPIdempotencyConflictError):
                env.call_impl(
                    creatives=[creative_payload(creative_id="c_nested")],
                    idempotency_key=_OUTER_KEY,
                    # A DIFFERENT hash from the stored one — a different payload under the
                    # same key, which is the definition of the conflict.
                    request_hash="1" * 64,
                )

    @pytest.mark.requires_db
    def test_both_in_process_callers_borrow_a_required_outer_key(self):
        """Both converted call sites borrow, so the gate protects both — not just one.

        ``update_media_buy``'s account and idempotency_key are both spec-REQUIRED on
        UpdateMediaBuyRequest, and ``create_media_buy``'s idempotency_key is required too, so
        neither nested upload can avoid carrying a real outer key. Read off the models rather
        than asserted in prose, so a requiredness change here fails this test.
        """
        from src.core.schemas import CreateMediaBuyRequest, UpdateMediaBuyRequest

        assert CreateMediaBuyRequest.model_fields["idempotency_key"].is_required()
        assert UpdateMediaBuyRequest.model_fields["idempotency_key"].is_required()

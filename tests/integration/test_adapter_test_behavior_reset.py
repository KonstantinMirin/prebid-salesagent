"""Reset semantics for ``set_adapter_test_behavior`` (#1585 review follow-up).

``set_adapter_test_behavior`` MERGES behavior flags into
``config_json["test_behavior"]`` and never removes keys, so ``fail_on_create`` /
``fail_on_update`` / ``error_message`` accumulate for the tenant's lifetime.
That merge is deliberate — BDD Given steps (tests/bdd/steps/generic/
given_media_buy.py) build a scenario's behavior across several calls — but it
makes "reset to the default baseline" impossible to express: merging
``manual_approval_required=False`` in leaves every other injected fault standing.

The e2e suite shares ONE live database whose ci-test tenant is mutated by
whichever test ran last, so the autouse baseline fixture in tests/e2e/conftest.py
needs a REAL reset. ``replace=True`` is that reset: the blob is REPLACED by the
passed flags and the ``mock_manual_approval_required`` column is rewritten from
the resulting value, not from the passed kwargs.

Integration (not unit) because the contract is what is PERSISTED: the guarantee
is worthless if the replaced blob or the recomputed column never reaches
Postgres.
"""

from __future__ import annotations

import pytest

from src.core.database.repositories.adapter_config import AdapterConfigRepository
from tests.factories import AdapterConfigFactory, TenantFactory
from tests.factories.core import set_adapter_test_behavior
from tests.harness._base import IntegrationEnv


def _reload(env: IntegrationEnv, tenant_id: str):
    """Re-read the AdapterConfig row from Postgres, bypassing the identity map."""
    session = env.get_session()
    session.expire_all()
    return AdapterConfigRepository(session, tenant_id).find_by_tenant()


@pytest.mark.integration
@pytest.mark.requires_db
class TestAdapterTestBehaviorMergeDefault:
    """Merge stays the default — BDD Given steps accumulate flags across calls."""

    def test_flags_accumulate_across_calls(self, integration_db):
        with IntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="atb_merge")
            AdapterConfigFactory(tenant=tenant, adapter_type="mock")

            set_adapter_test_behavior(env, "atb_merge", fail_on_create=True, error_message="boom")
            set_adapter_test_behavior(env, "atb_merge", manual_approval_required=True)

            row = _reload(env, "atb_merge")
            assert row is not None
            assert row.config_json["test_behavior"] == {
                "fail_on_create": True,
                "error_message": "boom",
                "manual_approval_required": True,
            }
            assert row.mock_manual_approval_required is True


@pytest.mark.integration
@pytest.mark.requires_db
class TestAdapterTestBehaviorReplace:
    """``replace=True`` REPLACES the blob — the only real reset-to-baseline."""

    def test_replace_drops_accumulated_flags(self, integration_db):
        """Every previously-merged fault flag is gone, not merely overridden."""
        with IntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="atb_replace")
            AdapterConfigFactory(tenant=tenant, adapter_type="mock")

            set_adapter_test_behavior(
                env,
                "atb_replace",
                fail_on_create=True,
                fail_on_update=True,
                error_message="boom",
                manual_approval_required=True,
            )
            set_adapter_test_behavior(env, "atb_replace", replace=True, manual_approval_required=False)

            row = _reload(env, "atb_replace")
            assert row is not None
            assert row.config_json["test_behavior"] == {"manual_approval_required": False}
            assert row.mock_manual_approval_required is False

    def test_replace_with_no_flags_empties_blob_and_clears_column(self, integration_db):
        """The column mirrors the RESULTING blob, not the passed kwargs.

        A replace that omits ``manual_approval_required`` means "no manual
        approval configured" — the column must fall back to the default, not
        keep the value a previous merge wrote.
        """
        with IntegrationEnv() as env:
            tenant = TenantFactory(tenant_id="atb_replace_empty")
            AdapterConfigFactory(tenant=tenant, adapter_type="mock")

            set_adapter_test_behavior(env, "atb_replace_empty", manual_approval_required=True, fail_on_create=True)
            set_adapter_test_behavior(env, "atb_replace_empty", replace=True)

            row = _reload(env, "atb_replace_empty")
            assert row is not None
            assert row.config_json["test_behavior"] == {}
            assert row.mock_manual_approval_required is False

    def test_replace_creates_row_when_absent(self, integration_db):
        """Reset on a tenant with no AdapterConfig row yet still persists a baseline."""
        with IntegrationEnv() as env:
            TenantFactory(tenant_id="atb_replace_norow")

            set_adapter_test_behavior(env, "atb_replace_norow", replace=True, manual_approval_required=False)

            row = _reload(env, "atb_replace_norow")
            assert row is not None
            assert row.config_json["test_behavior"] == {"manual_approval_required": False}
            assert row.mock_manual_approval_required is False

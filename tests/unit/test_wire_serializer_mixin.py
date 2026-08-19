"""The ``WireSerializerMixin`` seat: what it keeps, and what it must not override.

These grade the two rules the previous ``model_dump()`` override could only DOCUMENT
as footguns (src/core/schemas/_base.py). Both are reachable through the public
serialization API, so each is a behaviour test, not a shape assertion.
"""

from __future__ import annotations

import pytest

from src.core.schemas.account import Account


@pytest.fixture
def unconfirmed_account() -> Account:
    """An account whose three required-nullable fields are all null."""
    return Account(account_id="acct-1", name="Acme", status="active")


NULLABLE_FIELDS = ("advertiser", "rate_card", "payment_terms")


class TestRequiredNullableRetention:
    def test_null_fields_survive_exclude_none_in_python_mode(self, unconfirmed_account: Account) -> None:
        dumped = unconfirmed_account.model_dump()
        for field in NULLABLE_FIELDS:
            assert field in dumped, f"{field} was dropped by exclude_none; the schema requires it"
            assert dumped[field] is None

    def test_null_fields_survive_in_json_mode(self, unconfirmed_account: Account) -> None:
        dumped = unconfirmed_account.model_dump(mode="json")
        for field in NULLABLE_FIELDS:
            assert dumped[field] is None


class TestCallerSelectionIsHonoured:
    """Footgun 1, fixed: the wrap serializer receives the caller's selection on ``info``."""

    def test_explicit_exclude_is_not_undone(self, unconfirmed_account: Account) -> None:
        dumped = unconfirmed_account.model_dump(exclude={"advertiser"})
        assert "advertiser" not in dumped, "an explicitly excluded field must not be re-inserted"
        assert dumped["rate_card"] is None, "the fields the caller did NOT exclude are still retained"

    def test_include_selection_is_not_widened(self, unconfirmed_account: Account) -> None:
        dumped = unconfirmed_account.model_dump(include={"account_id"})
        assert set(dumped) == {"account_id"}, f"retention widened an include= selection: {sorted(dumped)}"


class TestOnlyNullValuesArePutBack:
    """Footgun 2, fixed: nothing but ``None`` is ever written by the retention step.

    The old override re-inserted ``getattr(self, field)``, so under ``mode="json"`` a
    live ``datetime`` could land in a JSON document. Writing only ``None`` removes
    that by construction rather than by test — which is why there is no
    "is it JSON-encodable" case here: ``None`` is encodable in every mode, and the
    retention behaviour itself is already pinned by the survival tests above.
    """

    def test_a_populated_field_is_untouched_by_retention(self) -> None:
        account = Account(account_id="acct-2", name="Acme", status="active", payment_terms="net_30")
        assert account.model_dump()["payment_terms"] == "net_30"

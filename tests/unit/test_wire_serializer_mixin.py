"""The ``WireSerializerMixin`` seat: what it keeps, and what it must not override.

These grade the two rules the previous ``model_dump()`` override could only DOCUMENT
as footguns (src/core/schemas/_base.py). Both are reachable through the public
serialization API, so each is a behaviour test, not a shape assertion.
"""

from __future__ import annotations

import json

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

    def test_null_fields_survive_model_dump_json(self, unconfirmed_account: Account) -> None:
        """``model_dump_json`` is a serializer path a ``model_dump()`` override never saw.

        The pre-fix shape re-inserted inside ``model_dump()`` only, so a response
        serialized straight to JSON silently lost the keys. The wrap serializer runs
        for both.
        """
        payload = json.loads(unconfirmed_account.model_dump_json())
        for field in NULLABLE_FIELDS:
            assert field in payload, f"{field} absent from model_dump_json output"
            assert payload[field] is None


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

    A raw Python value re-inserted under ``mode="json"`` would not survive JSON
    encoding — the reason the old docstring called it a hazard. Since only ``None``
    is written, every retained value round-trips through ``json.dumps``.
    """

    def test_retained_values_are_json_encodable(self, unconfirmed_account: Account) -> None:
        json.dumps(unconfirmed_account.model_dump(mode="json"))

    def test_a_populated_field_is_untouched_by_retention(self) -> None:
        account = Account(account_id="acct-2", name="Acme", status="active", payment_terms="net_30")
        assert account.model_dump()["payment_terms"] == "net_30"

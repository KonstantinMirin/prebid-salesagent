"""Regression tests for the local pricing option schemas (src.core.schemas.pricing).

The SDK's pricing union members carry ``extra="allow"``, which leaked internal
annotations (``supported`` / ``unsupported_reason``) onto the buyer-facing wire
and silently accepted pre-V3 keywords such as ``rate=``. The local subclasses
close both holes: this project's extra policy on every member, and the internal
annotations declared once with ``exclude=True`` so they never serialize.
"""

import pytest
from pydantic import ValidationError

from src.core.config import get_pydantic_extra_mode
from src.core.schemas.pricing import _MEMBER_TYPES, CpmPricingOption, PricingOption


def _cpm_kwargs(**overrides):
    kwargs = {
        "pricing_option_id": "cpm_usd_fixed",
        "pricing_model": "cpm",
        "currency": "USD",
        "fixed_price": 5.0,
    }
    kwargs.update(overrides)
    return kwargs


class TestMemberExtraPolicy:
    def test_every_member_applies_project_extra_policy(self):
        """All nine members must carry get_pydantic_extra_mode(), not the SDK's "allow".

        The mixin's config wins pydantic's base-config merge only when it is the
        LAST base; this pins that ordering for every member.
        """
        expected = get_pydantic_extra_mode()
        for member in _MEMBER_TYPES:
            assert member.model_config.get("extra") == expected, (
                f"{member.__name__}.model_config['extra'] is "
                f"{member.model_config.get('extra')!r}, expected {expected!r} — "
                "the _AdapterSupportAnnotations mixin must be the last base"
            )

    def test_union_covers_all_nine_spec_members(self):
        """The local union mirrors the nine-member oneOf of 3.1.1 core/pricing-option.json."""
        discriminators = {member.model_fields["pricing_model"].default for member in _MEMBER_TYPES}
        assert discriminators == {"cpm", "vcpm", "cpc", "cpcv", "cpv", "cpp", "cpa", "flat_rate", "time"}

    def test_pre_v3_rate_keyword_is_rejected_outside_production(self):
        """A pre-V3 ``rate=`` keyword is drift and must fail loud, not be echoed.

        Tests always run with the non-production extra policy ("forbid",
        Pattern #7); the assertion below pins that precondition.
        """
        assert get_pydantic_extra_mode() == "forbid"
        with pytest.raises(ValidationError, match="rate"):
            CpmPricingOption(**_cpm_kwargs(rate=5.0))


class TestInternalAnnotationsStayOffTheWire:
    def test_supported_fields_are_declared_writes(self):
        option = CpmPricingOption(**_cpm_kwargs())
        option.supported = False
        option.unsupported_reason = "Current adapter does not support CPM pricing"
        assert option.supported is False
        assert option.unsupported_reason == "Current adapter does not support CPM pricing"

    def test_supported_fields_never_serialize(self):
        option = CpmPricingOption(**_cpm_kwargs())
        option.supported = False
        option.unsupported_reason = "Current adapter does not support CPM pricing"
        dump = option.model_dump(mode="json")
        assert "supported" not in dump
        assert "unsupported_reason" not in dump
        wrapped_dump = PricingOption(option).model_dump(mode="json")
        assert "supported" not in wrapped_dump
        assert "unsupported_reason" not in wrapped_dump

    def test_wire_shape_matches_sdk_member(self):
        """Beyond the two internal fields, the local member serializes exactly like the SDK's."""
        from adcp.types import CpmPricingOption as LibraryCpmPricingOption

        local = CpmPricingOption(**_cpm_kwargs()).model_dump(mode="json", exclude_none=True)
        sdk = LibraryCpmPricingOption(**_cpm_kwargs()).model_dump(mode="json", exclude_none=True)
        assert local == sdk


class TestWrapperCoercion:
    def test_kwargs_construct_local_member(self):
        wrapped = PricingOption(**_cpm_kwargs())
        assert type(wrapped.root) is CpmPricingOption
        assert wrapped.fixed_price == 5.0  # proxied attribute access

    def test_local_member_instance_passes_through_by_identity(self):
        member = CpmPricingOption(**_cpm_kwargs())
        assert PricingOption(member).root is member

    def test_sdk_member_instance_is_revalidated_into_local_member(self):
        from adcp.types import CpmPricingOption as LibraryCpmPricingOption

        sdk_member = LibraryCpmPricingOption(**_cpm_kwargs())
        assert type(PricingOption(sdk_member).root) is CpmPricingOption

    def test_sdk_wrapper_instance_is_unwrapped_and_revalidated(self):
        from adcp.types import CpmPricingOption as LibraryCpmPricingOption
        from adcp.types.generated_poc.core.pricing_option import (
            PricingOption as LibraryPricingOptionWrapper,
        )

        sdk_wrapped = LibraryPricingOptionWrapper(LibraryCpmPricingOption(**_cpm_kwargs()))
        assert type(PricingOption(sdk_wrapped).root) is CpmPricingOption

    def test_sdk_instance_carrying_undeclared_extras_is_drift(self):
        """extras riding on an extra="allow" SDK instance must not slip through."""
        assert get_pydantic_extra_mode() == "forbid"
        from adcp.types import CpmPricingOption as LibraryCpmPricingOption

        sdk_member = LibraryCpmPricingOption(**_cpm_kwargs(rate=5.0))
        with pytest.raises(ValidationError, match="rate"):
            PricingOption(sdk_member)


class TestProductIntegration:
    @staticmethod
    def _product(pricing_options):
        from src.core.schemas import Product

        return Product(
            product_id="p1",
            name="P1",
            description="d",
            delivery_type="guaranteed",
            format_ids=[{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"}],
            publisher_properties=[{"selection_type": "all", "publisher_domain": "example.com"}],
            delivery_measurement={"provider": "test"},
            pricing_options=pricing_options,
            is_custom=False,
        )

    def test_product_wraps_options_in_local_wrapper(self):
        product = self._product([_cpm_kwargs()])
        assert type(product.pricing_options[0]) is PricingOption
        assert type(product.pricing_options[0].root) is CpmPricingOption

    def test_product_wire_omits_internal_annotations(self):
        """The get_products annotation path must never reach the buyer-facing wire."""
        product = self._product([_cpm_kwargs()])
        inner = product.pricing_options[0].root
        inner.supported = False
        inner.unsupported_reason = "Current adapter does not support CPM pricing"

        wire = product.model_dump(mode="json")
        assert wire["pricing_options"] == [
            {
                "pricing_option_id": "cpm_usd_fixed",
                "pricing_model": "cpm",
                "currency": "USD",
                "fixed_price": 5.0,
                "max_bid": False,
            }
        ]

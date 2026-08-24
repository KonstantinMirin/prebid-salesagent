"""Pricing option schemas extending the adcp library's discriminated union.

The SDK's ``PricingOption`` RootModel wraps a nine-member discriminated union
(discriminator ``pricing_model``). Its members carry ``extra="allow"``, which
this seller must not expose: unknown inbound fields would be silently echoed
back onto the wire, and pre-V3 keywords such as ``rate=`` would be accepted
instead of rejected. The RootModel wrapper itself cannot carry an ``extra``
policy (pydantic forbids ``extra`` on RootModel — see
adcontextprotocol/adcp-client-python#1077), but the members can: each one is a
plain BaseModel and subclasses cleanly.

This module therefore defines:

- Nine local subclasses of the SDK union members. Each inherits its full field
  set from the library type (Pattern #1 — never copy fields) and mixes in the
  internal ``supported`` / ``unsupported_reason`` annotations, declared once on
  a shared mixin with ``exclude=True`` so they exist as typed attributes but
  never serialize. The mixin also applies this project's ``extra`` policy
  (``forbid`` outside production), replacing the SDK's ``allow``.
- A ``PricingOption`` wrapper subclassing the SDK's RootModel with its root
  narrowed to OUR union, so ``option.root`` and proxied attribute access keep
  working at call sites.

Naming note: this wrapper is intentionally NOT star-exported from
``src.core.schemas`` — the package-level ``PricingOption`` name still refers to
the legacy flat model in ``_base.py``, which remains only because ledgered
schema-validation tests (T-UC-001-boundary-pricing-xor) still grade it. Import
the wrapper explicitly via ``from src.core.schemas.pricing import
PricingOption``. The nine member subclasses ARE star-exported and shadow the
SDK names at package level, so ``from src.core.schemas import
CpmPricingOption`` resolves to the local subclass (Pattern #7 applies).
"""

from typing import Annotated, Any

from adcp.types import CpaPricingOption as LibraryCpaPricingOption
from adcp.types import CpcPricingOption as LibraryCpcPricingOption
from adcp.types import CpcvPricingOption as LibraryCpcvPricingOption
from adcp.types import CpmPricingOption as LibraryCpmPricingOption
from adcp.types import CppPricingOption as LibraryCppPricingOption
from adcp.types import CpvPricingOption as LibraryCpvPricingOption
from adcp.types import FlatRatePricingOption as LibraryFlatRatePricingOption
from adcp.types import TimeBasedPricingOption as LibraryTimeBasedPricingOption
from adcp.types import VcpmPricingOption as LibraryVcpmPricingOption

# The SDK's RootModel wrapper. NOT importable as adcp.types.PricingOption —
# that public name is a plain Union alias over the members, not the wrapper.
# Underscore-prefixed (not the usual Library* alias) on purpose: the
# schema-inheritance guard maps every Library* alias against the PACKAGE-level
# class of the same bare name, and src.core.schemas.PricingOption is still the
# legacy flat model (see the naming note above), not this wrapper's subclass.
from adcp.types.generated_poc.core.pricing_option import (
    PricingOption as _LibraryPricingOption,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.config import get_pydantic_extra_mode

__all__ = [
    "AdCPPricingOption",
    "CpaPricingOption",
    "CpcPricingOption",
    "CpcvPricingOption",
    "CpmPricingOption",
    "CppPricingOption",
    "CpvPricingOption",
    "FlatRatePricingOption",
    "TimeBasedPricingOption",
    "VcpmPricingOption",
]


class _AdapterSupportAnnotations(BaseModel):
    """Internal adapter-capability annotations shared by all pricing members.

    ``supported`` / ``unsupported_reason`` are populated at discovery time
    (get_products) to record whether the tenant's ad-server adapter can honor
    the pricing model. Neither field exists in AdCP 3.1.1
    core/pricing-option.json, so both are ``exclude=True``: readable as model
    attributes, never serialized to the wire.

    The ``extra`` policy declared here replaces the SDK members'
    ``extra="allow"``. For the mixin's config to win pydantic's base-config
    merge, subclasses must list the library parent FIRST and this mixin LAST
    (pydantic applies base configs in ``__bases__`` order, last one wins).
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    supported: bool | None = Field(
        default=None,
        exclude=True,
        description="Internal: whether the tenant's adapter supports this pricing model (set at discovery time)",
    )
    unsupported_reason: str | None = Field(
        default=None,
        exclude=True,
        description="Internal: why this pricing model is unsupported (set when supported=False)",
    )


# Base order matters in every subclass below: (Library*, _AdapterSupportAnnotations)
# keeps the mixin last so its extra policy overrides the SDK's extra="allow".


class CpmPricingOption(LibraryCpmPricingOption, _AdapterSupportAnnotations):
    """CPM pricing option — library fields plus internal adapter annotations."""


class VcpmPricingOption(LibraryVcpmPricingOption, _AdapterSupportAnnotations):
    """vCPM pricing option — library fields plus internal adapter annotations."""


class CpcPricingOption(LibraryCpcPricingOption, _AdapterSupportAnnotations):
    """CPC pricing option — library fields plus internal adapter annotations."""


class CpcvPricingOption(LibraryCpcvPricingOption, _AdapterSupportAnnotations):
    """CPCV pricing option — library fields plus internal adapter annotations."""


class CpvPricingOption(LibraryCpvPricingOption, _AdapterSupportAnnotations):
    """CPV pricing option — library fields plus internal adapter annotations."""


class CppPricingOption(LibraryCppPricingOption, _AdapterSupportAnnotations):
    """CPP pricing option — library fields plus internal adapter annotations."""


class CpaPricingOption(LibraryCpaPricingOption, _AdapterSupportAnnotations):
    """CPA pricing option — library fields plus internal adapter annotations."""


class FlatRatePricingOption(LibraryFlatRatePricingOption, _AdapterSupportAnnotations):
    """Flat-rate pricing option — library fields plus internal adapter annotations."""


class TimeBasedPricingOption(LibraryTimeBasedPricingOption, _AdapterSupportAnnotations):
    """Time-based pricing option — library fields plus internal adapter annotations."""


_MEMBER_TYPES: tuple[type[BaseModel], ...] = (
    CpmPricingOption,
    VcpmPricingOption,
    CpcPricingOption,
    CpcvPricingOption,
    CpvPricingOption,
    CppPricingOption,
    CpaPricingOption,
    FlatRatePricingOption,
    TimeBasedPricingOption,
)

# Union of all nine AdCP pricing option types (the pinned spec's
# pricing-option.json oneOf), in local-subclass form. Also the root type of the
# PricingOption wrapper below.
AdCPPricingOption = (
    CpmPricingOption
    | VcpmPricingOption
    | CpcPricingOption
    | CpcvPricingOption
    | CpvPricingOption
    | CppPricingOption
    | CpaPricingOption
    | FlatRatePricingOption
    | TimeBasedPricingOption
)


class PricingOption(_LibraryPricingOption):
    """The SDK's RootModel wrapper, narrowed to OUR union members.

    ``Product.pricing_options`` is typed with this wrapper so every element
    carries the local members' extra policy and internal annotations while the
    call-site contract (``option.root``, proxied attribute access via the
    inherited ``__getattr__``) stays identical to the SDK wrapper it replaces.
    Every local member subclasses its SDK counterpart, so this root type is a
    strict narrowing of the parent's.
    """

    root: Annotated[
        AdCPPricingOption,
        Field(
            description=(
                "A pricing model option offered by a publisher for a product. Discriminated by pricing_model field."
            ),
            discriminator="pricing_model",
            title="Pricing Option",
        ),
    ]

    @model_validator(mode="before")
    @classmethod
    def _coerce_sdk_instances(cls, value: Any) -> Any:
        """Accept SDK-typed inputs by revalidating them into local members.

        A raw SDK member (or SDK RootModel wrapper) is not an instance of the
        local subclasses, so pydantic's model validation would reject it.
        Round-tripping through ``model_dump`` revalidates the same wire shape
        against the local members — which also applies this project's ``extra``
        policy, so undeclared fields riding on an ``extra="allow"`` SDK
        instance are surfaced (forbid) or dropped (ignore) instead of leaking.
        """
        if isinstance(value, PricingOption):
            return value
        if isinstance(value, _LibraryPricingOption):
            value = value.root
        if isinstance(value, BaseModel) and not isinstance(value, _MEMBER_TYPES):
            value = value.model_dump(mode="python", exclude_none=True)
        return value

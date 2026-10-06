"""Pricing option schemas extending the adcp library's discriminated union.

The SDK's ``PricingOption`` is a nine-member discriminated union (discriminator
``pricing_model``). Its members carry ``extra="allow"``, which this seller must
not expose: unknown inbound fields would be silently echoed back onto the wire,
and pre-V3 keywords such as ``rate=`` would be accepted instead of rejected.
The members can carry an ``extra`` policy: each one is a plain BaseModel and
subclasses cleanly.

At adcp 6.6.0 the union also had a ``RootModel`` WRAPPER class, which this
module's ``PricingOption`` subclassed. adcp 9 deletes that wrapper and ships
only the union — the fix for adcontextprotocol/adcp-client-python#1077 — so
there is nothing left to subclass and the local wrapper is a plain
``RootModel`` over the local union.

This module therefore defines:

- Nine local subclasses of the SDK union members. Each inherits its full field
  set from the library type (Pattern #1 — never copy fields) and mixes in a
  derived ``is_fixed`` property. The mixin also applies this project's ``extra``
  policy (``forbid`` outside production), replacing the SDK's ``allow``.
- A ``PricingOption`` RootModel over OUR union, so ``option.root`` and proxied
  attribute access keep working at call sites.

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
from pydantic import BaseModel, ConfigDict, Field, RootModel

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
    """What every local pricing member adds to its library parent: nothing on the wire.

    The ``extra`` policy declared here replaces the SDK members'
    ``extra="allow"``. For the mixin's config to win pydantic's base-config
    merge, subclasses must list the library parent FIRST and this mixin LAST
    (pydantic applies base configs in ``__bases__`` order, last one wins).

    ``is_fixed`` is DERIVED, not stored: AdCP V3 decides fixed-rate versus auction by
    which price field is present, so a property reads it off the member and there is
    no field to keep off the wire.
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    @property
    def is_fixed(self) -> bool:
        return getattr(self, "fixed_price", None) is not None


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


class PricingOption(RootModel[AdCPPricingOption]):
    """A RootModel over OUR union members, with the SDK wrapper's call contract.

    ``Product.pricing_options`` is typed with this wrapper so every element
    carries the local members' extra policy and internal annotations while the
    call-site contract (``option.root``, proxied attribute access) stays what it
    has always been.

    IT NO LONGER INHERITS AN SDK WRAPPER, because adcp 9 has none to inherit.
    At 6.6.0 ``adcp.types.domains.core.pricing_option.PricingOption`` was a
    ``RootModel`` subclass that added exactly two things -- a ``root`` annotation
    over the nine arms and an ``__getattr__`` proxy -- and the public
    ``adcp.types.PricingOption`` name was a plain union alias. adcp 9 deletes the
    wrapper and keeps only the union (the fix for
    adcp-client-python#1077, which is why the RootModel-cannot-be-subclassed note
    elsewhere in this file is obsolete), so there is no class left to extend: the
    inheritance that matters moved down to the MEMBERS, each of which still
    subclasses its SDK counterpart, which is what makes this root type a strict
    narrowing. ``__getattr__`` is restated below because it came from the wrapper.
    """

    # A RootModel has no named fields, so there is no ``extra`` policy to set -- pydantic
    # forbids ``extra`` on RootModel outright (adcontextprotocol/adcp-client-python#1077).
    # The policy that matters lives on the nine MEMBERS, via _AdapterSupportAnnotations.
    # Declared empty rather than omitted because the no-bare-BaseModel guard reads the
    # presence of ``model_config`` as the signal that the extra policy was CONSIDERED, and
    # the adcp 6.6.0 wrapper this class used to inherit carried exactly this: ``{}``.
    model_config = ConfigDict()

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

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the wrapped member.

        Verbatim from the adcp 6.6.0 wrapper this class used to inherit. Call sites
        read ``option.pricing_model`` / ``option.fixed_price`` directly, so deleting
        the wrapper upstream would have silently turned every one of those into an
        AttributeError.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.root, name)

    # NO SDK-COERCING VALIDATOR. A ``mode="before"`` validator used to accept an SDK-typed
    # member (or the SDK's own wrapper) by serializing it to a plain dict and revalidating
    # that dict against the local members. That is the one spelling critical pattern 4 names
    # twice: a pydantic
    # validator on a wire model may not serialize, and a receiving model adopts a sibling
    # generated class by reading its attributes, never by a dump. It survived only because
    # this file carried a per-file exemption in ruff-serialization.toml and in the ast-grep
    # rule; both entries are gone with it, so the ban now covers this file.
    #
    # It was deleted rather than rewritten to the attribute-reading form because nothing
    # needs it. No production path produces an SDK-typed pricing option: every construction
    # site under src/ imports the local subclass (product_conversion.py, whose comment says
    # exactly that; dynamic_pricing_service.py; the Xandr adapter), and the single direct SDK
    # pricing import in src/ is TimeParameters, a nested sub-object rather than a union
    # member. Only tests ever built an SDK member.
    #
    # Its docstring claimed the dump was what kept an undeclared field from leaking off an
    # ``extra="allow"`` SDK instance. That was backwards: the dump is what ACCEPTED the SDK
    # instance in the first place, and re-applying the extra policy was a side effect of
    # that acceptance. With no coercion an SDK instance is refused outright, under either
    # extra mode, so there is nothing left for a field to leak through.

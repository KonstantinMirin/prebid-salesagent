"""Factory_boy factories for Product and PricingOption models."""

from __future__ import annotations

from decimal import Decimal

import factory
from factory import LazyAttribute, Sequence, SubFactory

from src.core.database.models import PricingOption, Product
from src.core.schemas.pricing import PricingOption as PricingOptionSchema
from tests.factories.core import TenantFactory
from tests.factories.request import _RequestFactory


class ProductFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Product
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.tenant_id)
    product_id = Sequence(lambda n: f"prod_{n:04d}")
    name = LazyAttribute(lambda o: f"Product {o.product_id}")
    description = LazyAttribute(lambda o: f"Description for {o.name}")
    # Default to a format_id present in the captured reference catalog
    # (tests/fixtures/creative_formats/reference_formats.json). The legacy
    # "display_300x250" id is NOT in the agent's catalog; "display_300x250_image" is,
    # so format resolution against the reference formats succeeds. See issue #1418.
    format_ids = factory.LazyFunction(
        lambda: [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}]
    )
    targeting_template = factory.LazyFunction(lambda: {"geo": ["US"]})
    delivery_type = "guaranteed"
    property_tags = factory.LazyFunction(lambda: ["all_inventory"])
    delivery_measurement = factory.LazyFunction(lambda: {"provider": "publisher"})


class PricingOptionFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PricingOption
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    product = SubFactory(ProductFactory)
    tenant_id = LazyAttribute(lambda o: o.product.tenant_id)
    product_id = LazyAttribute(lambda o: o.product.product_id)
    pricing_model = "cpm"
    rate = Decimal("5.00")
    currency = "USD"
    is_fixed = True


class PricingOptionRequestFactory(_RequestFactory):
    """One pricing option as the WIRE DICT, the payload-side counterpart to ``PricingOptionFactory``.

    ``PricingOptionFactory`` above builds the ORM row; this builds the schema payload. The
    ``Request`` infix is the disambiguator ``tests/factories/webhook.py`` already
    established for exactly this ORM/payload pair, and the two are not interchangeable —
    ``is_fixed`` is a DB column with no schema field, which is why feeding ORM kwargs to
    the schema reports ``extra_forbidden``.

    HONEST ABOUT ITS WEIGHT TODAY: it replaces ONE site, ``_DEFAULT_PRICING_OPTION`` in
    ``tests/harness/product_unit.py``. It is declared now because ``GATED_ITEMS``
    (``tests/factories/malformed.py``) already names ``PricingOption`` as a graded item
    type, and because the fifteen pricing mutators that would make it earn its keep are
    scheduled work that needs the name to exist first (salesagent-b341x.4).

    IT BINDS A ``RootModel``. ``src.core.schemas.pricing.PricingOption.model_fields`` is
    ``{'root': ...}`` — a nine-member discriminated union — so this factory works through
    pydantic's ``RootModel(**data)`` kwargs path: ``build()`` returns the RootModel and
    ``model_dump()`` returns the root dict. The declared attributes below are the CPM
    member's fields; a ``pricing_model="cpc"`` variant selects a different member and
    needs that member's own companion fields supplied at ``build()`` time.

    ``payload()`` carries ``max_bid: False``, which the hand-written literal it replaces
    did not. That is the pinned model's OWN default for the field surfaced by the dump
    (``CpmPricingOption.max_bid`` defaults to ``False``, not to ``None``, so
    ``exclude_none`` does not drop it), not a new value this factory invents.
    """

    class Meta:
        model = PricingOptionSchema

    pricing_option_id = "po_default"
    pricing_model = "cpm"
    currency = "USD"
    # V3: the pre-V3 "rate" key is rejected by the local union members.
    fixed_price = 5.0

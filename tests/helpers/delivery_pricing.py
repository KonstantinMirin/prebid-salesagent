"""The pricing a conformant media buy always carries, for delivery fixtures.

Two clauses of the pinned schema meet here:

* ``media-buy/package-request.json`` REQUIRES ``pricing_option_id`` on every package
  (``required: ['product_id', 'budget', 'pricing_option_id']`` at AdCP 3.1), so every
  media buy reachable through ``create_media_buy`` names a pricing option, and
  ``MediaBuyRepository.create_from_request`` stores that request verbatim as
  ``raw_request``;
* ``media-buy/get-media-buy-delivery-response.json`` REQUIRES ``pricing_model``, ``rate``
  and ``currency`` on every ``by_package`` entry, and types all three non-nullable.

``_package_pricing`` (``src/core/tools/media_buy_delivery.py``) joins the two: it resolves
the three fields from ``MediaPackage.package_config['pricing_info']`` or from the
``PricingOption`` row the package names, and raises when neither resolves. A fixture buy
whose packages declare no ``pricing_option_id`` is a shape the protocol cannot produce, so
that raise is the correct answer to it — the fixture is what has to change.

Build fixture packages through :func:`delivery_package` rather than hand-rolling
``{"package_id": ..., "product_id": ...}``, and pair them with
:func:`delivery_pricing_options` wherever ``_get_pricing_options`` is patched.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.core.database.models import PricingOption
from tests.factories.product import PricingOptionFactory

# The SYNTHETIC id `_get_pricing_options` reconstructs, `{model}_{currency}_{fixed|auction}`
# — the pricing_options table has no id column of its own. Matches PricingOptionFactory's
# defaults (cpm / USD / is_fixed), which is what makes the two halves below line up.
PRICING_OPTION_ID = "cpm_usd_fixed"


def delivery_package(
    package_id: str = "pkg_001",
    product_id: str = "prod_001",
    pricing_option_id: str = PRICING_OPTION_ID,
    **extra: Any,
) -> dict[str, Any]:
    """One ``raw_request['packages']`` entry, shaped the way the protocol requires."""
    return {
        "package_id": package_id,
        "product_id": product_id,
        "pricing_option_id": pricing_option_id,
        **extra,
    }


def delivery_packages(*package_ids: str, **kwargs: Any) -> list[dict[str, Any]]:
    """``raw_request['packages']`` for one buy; defaults to a single ``pkg_001``."""
    return [delivery_package(package_id=pid, **kwargs) for pid in (package_ids or ("pkg_001",))]


def delivery_pricing_options(
    pricing_option_id: str = PRICING_OPTION_ID,
    pricing_model: str = "cpm",
    rate: str | Decimal = "5.00",
    currency: str = "USD",
) -> dict[str, PricingOption]:
    """What ``_get_pricing_options`` returns for :func:`delivery_package`'s packages.

    A real (unpersisted) ``PricingOption`` row, not a ``MagicMock``: an auto-created mock
    attribute is a truthy non-``None`` object, so a mock option satisfies
    ``_package_pricing``'s ``is not None`` checks and then fails ``PackageDelivery``
    validation with a ``MagicMock`` where the pin wants an ISO-4217 string.
    """
    return {
        pricing_option_id: PricingOptionFactory.build(
            pricing_model=pricing_model,
            rate=Decimal(str(rate)),
            currency=currency,
            is_fixed=True,
        )
    }

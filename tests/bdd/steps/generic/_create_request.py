"""Shared builder for a valid create_media_buy request against the seeded product.

Both UC-002 (idempotency replay) and UC-019 (the post-create get_media_buys poll)
need "a create_media_buy request that succeeds against the product this env
seeded". That is one logical operation with one parameter — the buyer's PO number
— so it lives here rather than being copied per use case.

Reads ctx["default_product"] / ctx["default_pricing_option"], which
``MediaBuyCreateEnv.setup_media_buy_data()`` puts there via conftest.
"""

from __future__ import annotations

from typing import Any


def pricing_option_id(pricing_option: Any) -> str:
    """Synthetic pricing_option_id string from a PricingOption ORM row.

    Matches the production/`given_media_buy` convention
    ``{pricing_model}_{currency_lower}_{fixed|auction}``.
    """
    fixed_str = "fixed" if pricing_option.is_fixed else "auction"
    return f"{pricing_option.pricing_model}_{pricing_option.currency.lower()}_{fixed_str}"


def build_create_request_kwargs(ctx: dict, *, po_number: str, budget: float = 5000.0) -> dict[str, Any]:
    """Assemble a valid create_media_buy request dict against the seeded product.

    Stored on ctx["request_kwargs"] and returned. ``po_number`` is explicit
    because the A2A wrapper no longer mints a random one when the caller omits it
    (it stays None for idempotency-hash + cross-transport parity), so any caller
    that hashes the canonical payload — or just wants a stable, human-readable
    request — has to supply its own, exactly as a real buyer does.
    """
    from datetime import UTC, datetime, timedelta

    product = ctx["default_product"]
    option = ctx["default_pricing_option"]
    now = datetime.now(UTC)
    ctx["request_kwargs"] = {
        "brand": {"domain": "testbrand.com"},
        "po_number": po_number,
        "start_time": (now + timedelta(days=1)).isoformat(),
        "end_time": (now + timedelta(days=30)).isoformat(),
        "packages": [
            {
                "product_id": product.product_id,
                "budget": budget,
                "pricing_option_id": pricing_option_id(option),
            }
        ],
    }
    return ctx["request_kwargs"]

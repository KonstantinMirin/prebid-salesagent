"""Pricing option helper utilities.

Handles the RootModel wrapper pattern used by adcp 2.14.0+ for discriminated unions.
"""

from typing import Any


def pricing_option_has_rate(pricing_option: Any) -> bool:
    """Check if a pricing option carries a fixed rate.

    V3 renamed the fixed rate to ``fixed_price`` (auction options have no rate;
    they carry ``floor_price`` / ``price_guidance``). The pre-V3 ``rate`` key is
    still honored as a fallback for ORM rows and stored legacy dicts, whose
    column keeps that name. Before this check knew about ``fixed_price`` it only
    matched ``rate``, so every V3-shaped option counted as rate-less — the
    anonymous-pricing heuristic in GetProductsResponse.__str__ misfired for
    authenticated buyers, hidden by test fixtures that leaked ``rate`` through
    the SDK members' ``extra="allow"``.

    Handles multiple formats:
    - Dict format (from JSON/serialization): checks fixed_price, then rate
    - Pydantic RootModel wrapper: checks the wrapped member's fixed_price
    - Direct attribute access (SQLAlchemy models): checks fixed_price, then rate

    Args:
        pricing_option: A pricing option in any supported format

    Returns:
        True if the pricing option has a non-None fixed rate value
    """
    # Dict format (JSON/serialization)
    if isinstance(pricing_option, dict):
        return pricing_option.get("fixed_price", pricing_option.get("rate")) is not None

    # Unwrap RootModel wrapper if present, then check the model/row attributes
    target = getattr(pricing_option, "root", pricing_option)
    if getattr(target, "fixed_price", None) is not None:
        return True
    return getattr(target, "rate", None) is not None

"""Service for managing GAM product implementation configurations."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GAMProductConfigService:
    """Handles GAM-specific product configuration management."""

    @staticmethod
    def generate_default_config(delivery_type: str, formats: list[str] | None = None) -> dict[str, Any]:
        """Generate default GAM implementation config based on product delivery type.

        Args:
            delivery_type: "guaranteed" or "non_guaranteed"
            formats: List of format IDs to derive creative placeholders

        Returns:
            Dictionary of GAM implementation config with sensible defaults. It writes no
            ``priority``: the line item's priority is the booked type's GAM default unless
            the seller sets one (``PricingCompatibility.plan_line_item``). It writes no goal
            unit type either: the goal is in the unit the package is sold in.
        """
        # Base configuration shared across all types
        base_config = {
            "cost_type": "CPM",
            "creative_rotation_type": "EVEN",
            "include_descendants": True,
        }

        # Delivery-type-specific defaults
        if delivery_type == "guaranteed":
            base_config.update(
                {
                    "line_item_type": "STANDARD",
                    "primary_goal_type": "LIFETIME",  # the only goal type GAM accepts on STANDARD
                    "delivery_rate_type": "EVENLY",
                    "non_guaranteed_automation": "manual",  # Guaranteed always manual
                }
            )
        else:  # non_guaranteed
            base_config.update(
                {
                    "line_item_type": "PRICE_PRIORITY",
                    "primary_goal_type": "NONE",
                    "delivery_rate_type": "AS_FAST_AS_POSSIBLE",
                    "creative_rotation_type": "OPTIMIZED",
                    "non_guaranteed_automation": "confirmation_required",  # Safe default
                }
            )

        # Generate creative placeholders from formats if provided
        if formats:
            base_config["creative_placeholders"] = GAMProductConfigService._generate_creative_placeholders(formats)
        else:
            # Default fallback placeholder
            base_config["creative_placeholders"] = [
                {"width": 300, "height": 250, "expected_creative_count": 1, "is_native": False}
            ]

        return base_config

    @staticmethod
    def _generate_creative_placeholders(formats: list[str]) -> list[dict[str, Any]]:
        """Generate creative placeholders from format IDs.

        Args:
            formats: List of format IDs (e.g., ["display_300x250", "display_728x90"])

        Returns:
            List of creative placeholder dictionaries for GAM
        """
        placeholders = []

        # Common format mappings (format_id -> dimensions)
        format_dimensions = {
            "display_300x250": (300, 250),
            "display_728x90": (728, 90),
            "display_160x600": (160, 600),
            "display_300x600": (300, 600),
            "display_970x250": (970, 250),
            "display_320x50": (320, 50),
            "display_320x100": (320, 100),
            "display_300x50": (300, 50),
        }

        for format_item in formats:
            # Handle both format storage patterns:
            # 1. Simple string: "display_300x250"
            # 2. Dict with format_id: {"format_id": "display_300x250", "name": "...", ...}
            if isinstance(format_item, dict):
                format_id = format_item.get("format_id", "")
            else:
                format_id = format_item

            if format_id in format_dimensions:
                width, height = format_dimensions[format_id]
                placeholders.append(
                    {
                        "width": width,
                        "height": height,
                        "expected_creative_count": 1,
                        "is_native": False,
                    }
                )
            elif format_id.startswith("native_"):
                # Native format - use default dimensions
                placeholders.append(
                    {
                        "width": 1,
                        "height": 1,
                        "expected_creative_count": 1,
                        "is_native": True,
                    }
                )
            elif format_id.startswith("video_"):
                # Video format - use standard video dimensions
                placeholders.append(
                    {
                        "width": 640,
                        "height": 480,
                        "expected_creative_count": 1,
                        "is_native": False,
                    }
                )

        # If no placeholders generated, return default
        if not placeholders:
            placeholders = [{"width": 300, "height": 250, "expected_creative_count": 1, "is_native": False}]

        return placeholders

    @staticmethod
    def validate_config(config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate GAM implementation config for required fields.

        The booking fields (``line_item_type``, ``priority``, ``primary_goal_type``) are not
        checked here: ``PricingCompatibility.plan_line_item`` is their one reader and
        validator, on the create path and on the seller's approval alike.

        Args:
            config: GAM implementation configuration dictionary

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not config:
            return False, "implementation_config is required for GAM products"

        # Required fields
        required_fields = ["creative_placeholders"]

        for field in required_fields:
            if field not in config:
                return False, f"Missing required GAM field: {field}"

        # Validate creative placeholders
        placeholders = config.get("creative_placeholders", [])
        if not placeholders:
            return False, "At least one creative placeholder is required"

        for placeholder in placeholders:
            if "width" not in placeholder or "height" not in placeholder:
                return False, "Creative placeholders must have width and height"

        # Warn if no inventory targeting specified (will use network root as fallback)
        has_inventory_targeting = config.get("targeted_ad_unit_ids") or config.get("targeted_placement_ids")
        if not has_inventory_targeting:
            logger.warning(
                "No inventory targeting specified (targeted_ad_unit_ids or targeted_placement_ids). "
                "Will use network root ad unit as fallback."
            )

        return True, None

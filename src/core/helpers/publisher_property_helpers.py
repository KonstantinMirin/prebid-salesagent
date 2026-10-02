"""Helpers for normalizing publisher_properties to AdCP discriminated union format.

AdCP 2.13.0+ requires PublisherPropertySelector dicts to have a selection_type
discriminator ("all", "by_id", or "by_tag"). Legacy data and inventory profiles
created via the admin UI "full JSON" mode may lack this field.

This module provides ensure_selection_type() to normalize on read.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

_PROPERTY_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
_PROPERTY_TAG_PATTERN = re.compile(r"^[a-z0-9_]+$")


def ensure_selection_type(properties: list[dict]) -> list[dict] | None:
    """Ensure each publisher_properties dict has a selection_type discriminator.

    Non-destructive: adds selection_type when missing, keeps all other fields intact.
    Only filters property_ids/property_tags to valid values (^[a-z0-9_]+$).

    For each dict in the list:
    - Already has selection_type → passthrough unchanged
    - Has valid property_ids → adds selection_type "by_id", replaces property_ids with valid subset
    - Has valid property_tags → adds selection_type "by_tag", replaces property_tags with valid subset
    - Neither → adds selection_type "all"

    Non-dict entries are skipped. Returns None if result is empty.
    """
    converted = []
    for prop in properties:
        if not isinstance(prop, dict):
            continue

        if "selection_type" in prop:
            converted.append(prop)
            continue

        # Work on a copy — don't mutate the original
        result = dict(prop)
        result.setdefault("publisher_domain", "unknown")

        prop_ids = prop.get("property_ids", [])
        prop_tags = prop.get("property_tags", [])

        valid_ids = [pid for pid in prop_ids if _PROPERTY_ID_PATTERN.match(str(pid))]
        valid_tags = [tag for tag in prop_tags if _PROPERTY_TAG_PATTERN.match(str(tag))]

        if valid_ids:
            result["property_ids"] = valid_ids
            result["selection_type"] = "by_id"
        elif valid_tags:
            result["property_tags"] = valid_tags
            result["selection_type"] = "by_tag"
        else:
            result["selection_type"] = "all"

        converted.append(result)

    return converted if converted else None


# ---------------------------------------------------------------------------
# Selectors resolved against the seller's authorized properties
# ---------------------------------------------------------------------------

#: The seller's default property tag. Its stored description is "Default tag that applies to
#: all properties", so it matches every authorized property whether or not the row lists it.
ALL_INVENTORY_TAG = "all_inventory"


class SelectableProperty(Protocol):
    """The three facts of an authorized property that a selector is built from."""

    @property
    def property_id(self) -> str: ...

    @property
    def publisher_domain(self) -> str: ...

    @property
    def tags(self) -> Sequence[str] | None: ...


@dataclass(frozen=True)
class AuthorizedPropertyRef:
    """An authorized property as a value, so it outlives the session that read it.

    ``get_products`` converts dynamic variants after its unit of work has closed, where an
    ORM row would raise on its first attribute read.
    """

    property_id: str
    publisher_domain: str
    tags: tuple[str, ...]


def _by_publisher(properties: Iterable[SelectableProperty]) -> dict[str, list[SelectableProperty]]:
    """*properties* grouped by publisher domain, domains in first-seen order."""
    grouped: dict[str, list[SelectableProperty]] = {}
    for prop in properties:
        grouped.setdefault(prop.publisher_domain, []).append(prop)
    return grouped


def by_id_selectors(properties: Iterable[SelectableProperty]) -> list[dict]:
    """One ``by_id`` selector per publisher, holding the IDs of that publisher's properties.

    AdCP 3.1.1 ``core/publisher-property-selector.json``: by_id is "Single-publisher only —
    property IDs are publisher-scoped".
    """
    return [
        {"publisher_domain": domain, "property_ids": [p.property_id for p in props], "selection_type": "by_id"}
        for domain, props in _by_publisher(properties).items()
    ]


def by_tag_selectors(tags: Sequence[str], properties: Iterable[SelectableProperty]) -> list[dict]:
    """One ``by_tag`` selector per publisher whose properties carry any of *tags*.

    Each selector lists the requested tags that publisher's properties carry, in the order
    requested. A publisher carrying none of them is not named.
    """
    selectors = []
    for domain, props in _by_publisher(properties).items():
        carried = {ALL_INVENTORY_TAG}.union(*(p.tags or () for p in props))
        matched = [tag for tag in tags if tag in carried]
        if matched:
            selectors.append({"publisher_domain": domain, "property_tags": matched, "selection_type": "by_tag"})
    return selectors


def legacy_selectors(
    property_ids: Sequence[str] | None,
    property_tags: Sequence[str] | None,
    properties: Sequence[SelectableProperty],
) -> list[dict]:
    """The ``publisher_properties`` of a product selecting by the legacy columns.

    Resolved against the seller's *properties*, one selector per publisher (AdCP 3.1.1
    ``core/product.json`` admits only the singular ``publisher_domain`` form on a product).
    A product that selects nothing offers every authorized publisher whole. Returns ``[]``
    when no authorized property backs the selection: there is then no publisher to name.
    """
    if property_ids:
        wanted = set(property_ids)
        return by_id_selectors(p for p in properties if p.property_id in wanted)
    if property_tags:
        return by_tag_selectors(property_tags, properties)
    return [{"publisher_domain": domain, "selection_type": "all"} for domain in _by_publisher(properties)]

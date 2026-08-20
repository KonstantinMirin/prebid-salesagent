"""Read field facts from the pinned AdCP schema tree that ships with the SDK.

The always-include set is a fact the pin states: a field is kept on the wire when
null exactly when the schema lists it in ``required`` AND types it nullable. Every
hand-declared copy of that fact is correct on the day it is written and unverified
afterwards — two of the three adopters had drifted from the pin by the time this
was added, and both emitted schema-invalid nulls to buyers.

Reads the SDK's own installed tree, so the fact moves with the ``adcp`` pin in
``pyproject.toml`` rather than with anyone's memory.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path


@cache
def _schema_root() -> Path:
    import adcp

    major_minor = ".".join(adcp.get_adcp_spec_version().split(".")[:2])
    return Path(adcp.__file__).parent / "_schemas" / major_minor


@cache
def required_nullable_fields(ref: str) -> frozenset[str]:
    """Fields the pinned schema at *ref* marks both required and nullable.

    *ref* is a category-qualified path, optionally with a JSON pointer for a
    nested subschema: ``core/account.json`` or
    ``media-buy/get-media-buys-response.json#/properties/media_buys/items``.

    A ref that cannot be resolved is a hard failure. Returning an empty set on a
    missing file would silently drop every field from the wire — the exact
    omission class this derivation exists to prevent.
    """
    path_part, _, pointer = ref.partition("#")
    schema = json.loads((_schema_root() / path_part).read_text())
    for token in (t for t in pointer.split("/") if t):
        schema = schema[token]
    properties = schema.get("properties") or {}
    return frozenset(
        field
        for field in schema.get("required", [])
        if isinstance((properties.get(field) or {}).get("type"), list) and "null" in properties[field]["type"]
    )

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


class UnderivablePinnedSchema(Exception):
    """The pin composes *ref* in a way no complete ``required`` list can be read from.

    Raised rather than returning an empty set, so a caller can never mistake "I could
    not read the list" for "the pin declares none". The two are indistinguishable by
    return value, which is what let the fail-open survive.
    """


@cache
def _schema_root() -> Path:
    import adcp

    major_minor = ".".join(adcp.get_adcp_spec_version().split(".")[:2])
    return Path(adcp.__file__).parent / "_schemas" / major_minor


@cache
def package_update_forbidden_shapes() -> tuple[tuple[tuple[str, ...], frozenset[str]], ...]:
    """The shapes ``media-buy/package-update.json``'s root ``not`` forbids, as the pin states them.

    Each ``anyOf`` branch of that ``not`` is one forbidden shape: the members it ``required``s,
    and the subset of them its ``properties`` additionally constrain to ``type: object``. At the
    pin that is six fully-immutable fields, the pre-GA ``capability_ids``,
    ``budget_cap_timezone``, and ``bidding`` (an object) together with ``bid_price``. Read here
    so the list moves with the ``adcp`` pin instead of with a hand-kept copy -- the hand-kept
    copy named three of the nine.

    Raises:
        UnderivablePinnedSchema: a branch uses a keyword other than ``required`` and an
            object-typed ``properties`` member. Refused rather than skipped, so a branch this
            reader cannot evaluate is never mistaken for a branch that forbids nothing.
    """
    schema = json.loads((_schema_root() / "media-buy" / "package-update.json").read_text())
    shapes = []
    for branch in schema["not"]["anyOf"]:
        members = branch.get("properties", {})
        if set(branch) - {"required", "properties"} or any(spec != {"type": "object"} for spec in members.values()):
            raise UnderivablePinnedSchema(f"package-update.json root not branch {branch!r}")
        shapes.append((tuple(branch["required"]), frozenset(members)))
    return tuple(shapes)


@cache
def revision_minimum() -> int:
    """The lower bound the pin puts on ``media_buys[].revision``.

    Subscripted, never ``.get()``: if the pin drops the key, a ``KeyError`` here is a
    loud failure rather than a silent substitute bound.
    """
    schema = json.loads((_schema_root() / "media-buy" / "get-media-buys-response.json").read_text())
    return schema["properties"]["media_buys"]["items"]["properties"]["revision"]["minimum"]

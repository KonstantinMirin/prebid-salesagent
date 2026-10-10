"""Pydantic model factories for Format and FormatId.

These are factory-boy factories for Pydantic models (not ORM models),
used by BDD Given steps to construct real Format objects directly.

Usage::

    from tests.factories.format import FormatFactory, make_asset

    # Simple format
    fmt = FormatFactory.build(name="banner")

    # With assets
    fmt = FormatFactory.build(
        name="rich-ad",
        assets=[make_asset("image"), make_asset("video")],
    )

    # With render dimensions
    fmt = FormatFactory.build(
        name="leaderboard",
        renders=[make_renders(width=728, height=90)],
    )
"""

from __future__ import annotations

from collections.abc import Callable

import factory
from adcp.types import (
    AudioFormatAsset,
    FormatAssetUnion,
    HtmlFormatAsset,
    ImageFormatAsset,
    MarkdownFormatAsset,
    Responsive,
    TextFormatAsset,
    VideoFormatAsset,
)
from adcp.types.domains.core.format import Dimensions, Renders  # TODO: no stable alias in adcp.types

from src.core.schemas import Format, FormatId

AGENT_URL = "https://creative.adcontextprotocol.org"

# ── Asset class mapping ──────────────────────────────────────────────

_ASSET_CLASS_MAP = {
    "image": ImageFormatAsset,
    "video": VideoFormatAsset,
    "audio": AudioFormatAsset,
    "text": TextFormatAsset,
    "markdown": MarkdownFormatAsset,
    "html": HtmlFormatAsset,
}

# The asset-type vocabulary this factory can build, for steps that need to check
# a claimed asset type is real rather than build one. Derived, not restated.
ASSET_TYPES = frozenset(_ASSET_CLASS_MAP)


def make_asset(asset_type: str, asset_id: str | None = None) -> FormatAssetUnion:
    """Create a typed asset object from an asset type string.

    Refuses an asset type it cannot build. This used to resolve the class with
    ``.get(asset_type, ImageFormatAsset)``, so a Given asking for a video, audio
    or html asset was handed an IMAGE asset and every assertion downstream graded
    the image path — a wrong-object pass, not a visible gap. A factory that
    substitutes an object for the one asked for cannot fail.

    >>> a = make_asset("video")
    >>> a.asset_type
    'video'
    """
    try:
        cls = _ASSET_CLASS_MAP[asset_type]
    except KeyError:
        raise ValueError(
            f"make_asset cannot build asset type {asset_type!r}. Buildable types: "
            f"{sorted(_ASSET_CLASS_MAP)}. If the pinned core/format.json assets union "
            "admits this type, add it to _ASSET_CLASS_MAP; if it does not, the scenario "
            "is asking for an asset this spec version has no schema for."
        ) from None
    return cls(asset_id=asset_id or f"{asset_type}_asset", required=True)


def _find_repeatable_group_class():
    """Return the RepeatableAssetGroup class (stable alias)."""
    from adcp.types import RepeatableAssetGroup

    return RepeatableAssetGroup


def _find_inner_asset_class(asset_type: str):
    """Find the inner asset class for a repeatable group by asset_type, or raise.

    Inner assets within a repeatable_group use different classes than
    top-level assets, and those classes carry no stable alias in ``adcp.types``
    (only the numbered generated names), so they are found dynamically — which
    also survives SDK regeneration.

    The ``assets`` field annotation is nested:
        list[Annotated[Union[Annotated[AssetX, Tag], ...], Discriminator]]
    so we unwrap the list element (Annotated), then the discriminated Union,
    then each member (Annotated) down to the concrete asset model.
    """
    from typing import Annotated, get_args, get_origin

    def _unwrap_annotated(tp):
        return get_args(tp)[0] if get_origin(tp) is Annotated else tp

    _RepeatableGroupCls = _find_repeatable_group_class()
    assets_field = _RepeatableGroupCls.model_fields["assets"]
    # list[...] -> element type (Annotated[Union[...], Discriminator])
    element = _unwrap_annotated(get_args(assets_field.annotation)[0])
    # Union[Annotated[AssetX, Tag], ...] -> concrete member classes
    members = [_unwrap_annotated(m) for m in get_args(element)]
    members = [m for m in members if hasattr(m, "model_fields")]
    by_type = {cls.model_fields["asset_type"].default: cls for cls in members if "asset_type" in cls.model_fields}
    try:
        return by_type[asset_type]
    except KeyError:
        raise ValueError(
            f"a repeatable asset group cannot hold asset type {asset_type!r}. The pinned "
            f"group assets union admits: {sorted(t for t in by_type if isinstance(t, str))}. "
            "This used to fall back to the union's FIRST member (an image asset), so a group "
            "asked for two types could come back holding two of the wrong kind."
        ) from None


def make_asset_group(
    *asset_types: str,
    group_id: str = "asset_group",
    min_count: int = 1,
    max_count: int = 10,
):
    """Create a repeatable asset group containing typed inner assets.

    All class lookups are dynamic to survive SDK regeneration where
    numbered class names (Assets18→Assets94, etc.) shift.
    """
    _RepeatableGroupCls = _find_repeatable_group_class()
    # No `if inner_cls` guard: _find_inner_asset_class raises rather than returning
    # None, so a group never comes back holding fewer assets than it was asked for.
    inner_assets = [_find_inner_asset_class(at)(asset_id=f"{at}_asset", required=True) for at in asset_types]
    return _RepeatableGroupCls(
        item_type="repeatable_group",
        asset_group_id=group_id,
        required=True,
        min_count=min_count,
        max_count=max_count,
        assets=inner_assets,
    )


def make_renders(
    *,
    width: int | None = None,
    height: int | None = None,
    min_width: int | None = None,
    max_width: int | None = None,
    responsive_width: bool | None = None,
) -> Renders:
    """Create a Renders object with dimensions.

    >>> r = make_renders(width=728, height=90)
    >>> r.dimensions.width
    728
    """
    dims_kwargs: dict = {}
    if width is not None:
        dims_kwargs["width"] = width
    if height is not None:
        dims_kwargs["height"] = height
    if min_width is not None:
        dims_kwargs["min_width"] = min_width
    if max_width is not None:
        dims_kwargs["max_width"] = max_width
    if responsive_width is not None:
        dims_kwargs["responsive"] = Responsive(width=responsive_width, height=False)
    return Renders(role="primary", dimensions=Dimensions(**dims_kwargs))


def make_responsive_renders() -> Renders:
    """Create a responsive Renders object with standard defaults."""
    return make_renders(min_width=300, max_width=970, responsive_width=True)


def make_fixed_renders(width: int = 728, height: int = 90) -> Renders:
    """Create a fixed-dimension Renders object."""
    return make_renders(width=width, height=height)


# ── Reference catalog selection ──────────────────────────────────────


def pick_reference_formats(predicate: Callable[[Format], bool], min_count: int = 1) -> list[Format]:
    """Select formats from the captured reference catalog that satisfy ``predicate``.

    This is the single source for "a format with property X" in scenarios: it draws
    from the same checked-in fixture the in-process harness and the e2e server serve,
    so a selected format is guaranteed to exist on the live server too.

    Raises loud (ValueError) if fewer than ``min_count`` reference formats match —
    that is the true signal the scenario needs a format registered in the creative
    agent's own registry, not a synthetic FormatFactory mint. See issue #1418.

    >>> displays = pick_reference_formats(lambda f: f.format_id.id.startswith("display_"))
    >>> all(f.format_id.id.startswith("display_") for f in displays)
    True
    """
    from src.core.format_cache import load_reference_formats

    matches = [fmt for fmt in load_reference_formats() if predicate(fmt)]
    if len(matches) < min_count:
        raise ValueError(
            f"Reference catalog has {len(matches)} format(s) matching the predicate, "
            f"need at least {min_count}. The scenario needs a format the reference agent "
            "does not serve — register it in the creative agent's registry rather than "
            "minting a synthetic one."
        )
    return matches


def _category_of(fmt: Format) -> str | None:
    """The catalog category a reference format is served under, as a plain string."""
    value = getattr(fmt, "type", None)
    return None if value is None else str(getattr(value, "value", value))


def _uses_asset_type(fmt: Format, asset_type: str) -> bool:
    return any(
        str(getattr(getattr(a, "asset_type", None), "value", getattr(a, "asset_type", None))) == asset_type
        for a in fmt.assets or []
    )


def pick_reference_format(category: str, *, without_asset_type: str | None = None) -> Format:
    """The first reference format served under *category*, in catalog order.

    A scenario that says "a display format" wants a REAL one -- served by the in-process
    fixture and the live e2e stack alike -- not a minted ``fmt_N`` that the live stack can
    never realize and that carries no assets to grade. Catalog order makes the choice
    deterministic across runs and transports.

    ``without_asset_type`` skips formats carrying that asset type; it exists for
    ``pixel_tracker``, which the pinned 3.1.1 ``core/format.json`` assets union does not
    admit (adcp#7338) although the reference agent serves it, so a scenario whose Then
    validates the response against the pin can still pick a format the pin accepts.
    """
    return pick_reference_formats(
        lambda f: (
            _category_of(f) == category and (without_asset_type is None or not _uses_asset_type(f, without_asset_type))
        )
    )[0]


# ── Factories ────────────────────────────────────────────────────────


class FormatIdFactory(factory.Factory):
    """Factory for FormatId Pydantic model."""

    class Meta:
        model = FormatId

    agent_url = AGENT_URL
    id = factory.Sequence(lambda n: f"fmt_{n}")


class FormatFactory(factory.Factory):
    """Factory for Format Pydantic model.

    Only ``format_id`` and ``name`` are required. All other fields
    are optional and can be passed as keyword overrides.
    """

    class Meta:
        model = Format

    format_id = factory.SubFactory(FormatIdFactory)
    name = factory.Sequence(lambda n: f"format_{n}")
    is_standard = True


# ── Category mapping (compat shim) ──────────────────────────────────
# FormatCategory was removed in adcp 3.12. Format.type no longer exists.
# BDD steps still pass type= as an extra field (Pydantic ignores in dev mode).
# This mapping provides string values so existing step code doesn't crash.

CATEGORY_MAP: dict[str, str | None] = {
    "display": "display",
    "video": "video",
    "audio": "audio",
    "native": "native",
    "dooh": "dooh",
}

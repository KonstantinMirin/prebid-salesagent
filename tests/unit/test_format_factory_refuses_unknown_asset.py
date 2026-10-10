"""The format factory refuses an asset type it cannot build, instead of guessing.

``make_asset`` used to resolve its class with ``_ASSET_CLASS_MAP.get(asset_type,
ImageFormatAsset)``, so a Given asking for a video, audio or html asset got an
IMAGE asset and every assertion downstream graded the image path. A factory that
substitutes a different object for the one asked for cannot fail, and a scenario
built on it cannot falsify — which is why this is graded here rather than left to
the scenarios that consume it.

The same hole existed one level down: ``make_asset_group``'s inner-class lookup
fell back to the union's first member (also image) and ``make_asset_group`` then
dropped a ``None`` silently, so a group asked for two asset types could come back
holding one, or two of the wrong kind.
"""

from __future__ import annotations

import pytest

from tests.factories.format import make_asset, make_asset_group


def test_make_asset_refuses_an_unknown_asset_type() -> None:
    """An asset type outside the vocabulary raises instead of yielding an image."""
    with pytest.raises(ValueError, match="not_a_real_asset_type"):
        make_asset("not_a_real_asset_type")


def test_make_asset_group_refuses_an_unknown_asset_type() -> None:
    """A group member the inner union has no class for raises, never silently drops."""
    with pytest.raises(ValueError, match="not_a_real_asset_type"):
        make_asset_group("image", "not_a_real_asset_type")

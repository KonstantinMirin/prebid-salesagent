"""The format factory builds the asset it was asked for, or refuses.

``make_asset`` used to resolve its class with ``_ASSET_CLASS_MAP.get(asset_type,
ImageFormatAsset)`` over a map covering 6 of the 14 asset types the generated
``Format.assets`` union models, so a Given asking for a video, audio or html asset
got an IMAGE asset and every assertion downstream graded the image path. A factory
that substitutes a different object for the one asked for cannot fail, and a
scenario built on it cannot falsify — which is why this is graded here rather than
left to the scenarios that consume it.

The same hole existed one level down: ``make_asset_group``'s inner-class lookup
fell back to the union's first member (also image) and ``make_asset_group`` then
dropped a ``None`` silently, so a group asked for two asset types could come back
holding one, or two of the wrong kind.

Three properties, which together are the whole contract:

* an unbuildable asset type RAISES;
* every type the factory claims it can build comes back carrying that
  ``asset_type`` — not merely "an object";
* the vocabulary is exactly what the pinned union admits, top-level and in-group.
  The factory DERIVES it (a hand-written map went stale at 6 of 14, and the group's
  classes have no stable alias to hand-write against); the expected sets are
  DECLARED here, so an SDK bump that changes either union fails loudly in both
  directions instead of silently widening what scenarios can seed.
"""

from __future__ import annotations

import pytest

from tests.factories.format import ASSET_TYPES, make_asset, make_asset_group

#: The asset_type discriminators of the pinned core/format.json ``assets`` union.
#: The repeatable_group member and the SDK's ``_unknown`` fallback branch are not
#: asset types and are not buildable by name.
PINNED_ASSET_TYPES = frozenset(
    {
        "image",
        "video",
        "audio",
        "text",
        "markdown",
        "html",
        "css",
        "javascript",
        "vast",
        "daast",
        "url",
        "webhook",
        "brief",
        "catalog",
    }
)

#: Inside a repeatable_group the union is narrower: no brief, no catalog.
PINNED_GROUP_ASSET_TYPES = PINNED_ASSET_TYPES - {"brief", "catalog"}


def test_make_asset_refuses_an_unknown_asset_type() -> None:
    """An asset type outside the vocabulary raises instead of yielding an image."""
    with pytest.raises(ValueError, match="not_a_real_asset_type"):
        make_asset("not_a_real_asset_type")


def test_make_asset_group_refuses_an_unknown_asset_type() -> None:
    """A group member the inner union has no class for raises, never silently drops."""
    with pytest.raises(ValueError, match="not_a_real_asset_type"):
        make_asset_group("image", "not_a_real_asset_type")


def test_make_asset_group_refuses_a_type_the_group_union_excludes() -> None:
    """brief is a real top-level asset type and still not groupable."""
    assert "brief" in PINNED_ASSET_TYPES
    with pytest.raises(ValueError, match="brief"):
        make_asset_group("brief")


@pytest.mark.parametrize("asset_type", sorted(PINNED_ASSET_TYPES))
def test_make_asset_builds_the_asset_type_it_was_asked_for(asset_type: str) -> None:
    """The object carries the requested discriminator — the wrong-object check."""
    assert make_asset(asset_type).asset_type == asset_type


@pytest.mark.parametrize("asset_type", sorted(PINNED_GROUP_ASSET_TYPES))
def test_make_asset_group_builds_the_asset_types_it_was_asked_for(asset_type: str) -> None:
    assert [a.asset_type for a in make_asset_group(asset_type).assets] == [asset_type]


def test_factory_vocabulary_is_the_pinned_union() -> None:
    """Derived in the factory, declared here, so a union change cannot pass quietly."""
    assert ASSET_TYPES == PINNED_ASSET_TYPES

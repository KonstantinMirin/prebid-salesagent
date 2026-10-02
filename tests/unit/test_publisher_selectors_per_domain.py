"""A product's legacy selectors resolve to one ``publisher_properties`` entry per publisher.

AdCP 3.1.1 ``core/product.json`` requires ``publisher_properties`` (``minItems: 1``) and
admits only the singular ``publisher_domain`` form on a product, so a product spanning N
publishers carries N entries. ``core/publisher-property-selector.json`` makes property IDs
publisher-scoped ("Single-publisher only"). The domain each entry names is where a buyer
fetches ``/.well-known/adagents.json`` to verify the seller (``authorized-properties.mdx``,
"Authorization Validation Workflow"), so it is the PUBLISHER's domain, read off the
authorized-property rows — never the host the seller's agent answers on.

No database: the resolution reads three fields of each authorized property and nothing else.
"""

from src.core.helpers.publisher_property_helpers import (
    AuthorizedPropertyRef,
    by_id_selectors,
    by_tag_selectors,
    legacy_selectors,
)

NEWS = AuthorizedPropertyRef(property_id="news_home", publisher_domain="news.example", tags=("premium",))
NEWS_SPORT = AuthorizedPropertyRef(property_id="news_sport", publisher_domain="news.example", tags=("sport",))
SPORTS = AuthorizedPropertyRef(property_id="sports_home", publisher_domain="sports.example", tags=("premium", "sport"))
WEATHER = AuthorizedPropertyRef(property_id="weather_home", publisher_domain="weather.example", tags=())

AUTHORIZED = (NEWS, NEWS_SPORT, SPORTS, WEATHER)


class TestByIdSelectors:
    def test_ids_are_grouped_under_the_publisher_that_owns_them(self):
        assert by_id_selectors([NEWS, SPORTS, NEWS_SPORT]) == [
            {
                "publisher_domain": "news.example",
                "property_ids": ["news_home", "news_sport"],
                "selection_type": "by_id",
            },
            {"publisher_domain": "sports.example", "property_ids": ["sports_home"], "selection_type": "by_id"},
        ]

    def test_no_properties_select_nothing(self):
        assert by_id_selectors([]) == []


class TestByTagSelectors:
    def test_each_publisher_carrying_a_tag_gets_its_own_entry_with_the_tags_it_carries(self):
        assert by_tag_selectors(["sport", "premium"], AUTHORIZED) == [
            {"publisher_domain": "news.example", "property_tags": ["sport", "premium"], "selection_type": "by_tag"},
            {"publisher_domain": "sports.example", "property_tags": ["sport", "premium"], "selection_type": "by_tag"},
        ]

    def test_a_publisher_carrying_none_of_the_tags_is_not_named(self):
        assert by_tag_selectors(["premium"], [WEATHER]) == []

    def test_all_inventory_applies_to_every_property(self):
        """The seller's default tag: "Default tag that applies to all properties"."""
        assert by_tag_selectors(["all_inventory"], [WEATHER, NEWS]) == [
            {"publisher_domain": "weather.example", "property_tags": ["all_inventory"], "selection_type": "by_tag"},
            {"publisher_domain": "news.example", "property_tags": ["all_inventory"], "selection_type": "by_tag"},
        ]


class TestLegacySelectors:
    def test_property_ids_keep_only_the_authorized_ones(self):
        assert legacy_selectors(["sports_home", "gone_away"], None, AUTHORIZED) == [
            {"publisher_domain": "sports.example", "property_ids": ["sports_home"], "selection_type": "by_id"},
        ]

    def test_property_tags_resolve_per_publisher(self):
        assert legacy_selectors(None, ["sport"], AUTHORIZED) == [
            {"publisher_domain": "news.example", "property_tags": ["sport"], "selection_type": "by_tag"},
            {"publisher_domain": "sports.example", "property_tags": ["sport"], "selection_type": "by_tag"},
        ]

    def test_no_selector_offers_every_authorized_publisher_whole(self):
        """An empty ``property_tags`` (the admin form's "nothing selected") is the default."""
        assert legacy_selectors(None, [], AUTHORIZED) == [
            {"publisher_domain": "news.example", "selection_type": "all"},
            {"publisher_domain": "sports.example", "selection_type": "all"},
            {"publisher_domain": "weather.example", "selection_type": "all"},
        ]

    def test_nothing_authorized_resolves_to_nothing(self):
        """No row backs the product, so there is no publisher to name -- and no host to borrow."""
        assert legacy_selectors(None, [], []) == []
        assert legacy_selectors(None, ["all_inventory"], []) == []
        assert legacy_selectors(["news_home"], None, []) == []

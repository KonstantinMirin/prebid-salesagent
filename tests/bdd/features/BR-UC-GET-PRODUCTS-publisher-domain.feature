# Manual feature: which publisher a product's publisher_properties name (#1845).

Feature: A product names the publishers whose inventory it sells
  As a Buyer Agent
  I want each product's publisher_properties to name the publishers it sells
  So that I can verify the seller against each publisher's adagents.json

  # A seller (one sales agent, one host) represents many publishers. Each publisher
  # authorizes the agent in its OWN /.well-known/adagents.json, and a buyer verifies a
  # product by fetching that file at every publisher_properties[].publisher_domain and
  # failing closed when it finds no authorization (AdCP 3.1.1
  # governance/property/authorized-properties.mdx, "Authorization Validation Workflow"
  # and "Missing adagents.json: Treat as unauthorized").
  #
  # So publisher_domain is the PUBLISHER's domain. A product that selects by tag, by
  # property id, or not at all resolves against the seller's authorized properties,
  # one entry per publisher: core/product.json admits only the singular publisher_domain
  # form on a product, and core/publisher-property-selector.json makes property ids
  # publisher-scoped. The seller's own agent host is never a publisher here.
  #
  # core/product.json requires publisher_properties with minItems 1, so a product no
  # authorized property backs has nothing it may truthfully claim and is not offered.
  #
  # A product's legacy property_ids column cannot be stored on its own: the table's
  # ck_product_properties_xor admits exactly one of properties / property_tags, so
  # there is no by-id scenario here. The by-id grouping is graded through inventory
  # profiles (tests/admin/test_inventory_profiles.py) and the selector unit tests.
  #
  # Ungraded by the 3.1.1 storyboards: no compliance step compares publisher_domain
  # against the seller's authorized properties.

  Background:
    Given a tenant is configured for product discovery
    And the seller is authorized for property "news_home" of publisher "news.example" tagged "premium"
    And the seller is authorized for property "sports_home" of publisher "sports.example" tagged "premium"
    And the seller is authorized for property "weather_home" of publisher "weather.example" tagged "standard"


  @T-UC-GET-PRODUCTS-publisher-by-tag @publisher_domain_resolution @requires_db
  Scenario: a product selecting by tag names each publisher that carries the tag
    Given the seller offers product "premium" selecting property tags "premium"
    When the buyer requests products
    Then product "premium" announces publisher_properties [{"publisher_domain": "news.example", "property_tags": ["premium"], "selection_type": "by_tag"}, {"publisher_domain": "sports.example", "property_tags": ["premium"], "selection_type": "by_tag"}]

  @T-UC-GET-PRODUCTS-publisher-all-inventory @publisher_domain_resolution @requires_db
  Scenario: the seller's all_inventory tag names every authorized publisher
    Given the seller offers product "run_of_network" selecting property tags "all_inventory"
    When the buyer requests products
    Then product "run_of_network" announces publisher_properties [{"publisher_domain": "news.example", "property_tags": ["all_inventory"], "selection_type": "by_tag"}, {"publisher_domain": "sports.example", "property_tags": ["all_inventory"], "selection_type": "by_tag"}, {"publisher_domain": "weather.example", "property_tags": ["all_inventory"], "selection_type": "by_tag"}]

  @T-UC-GET-PRODUCTS-publisher-default-all @publisher_domain_resolution @requires_db
  Scenario: a product selecting nothing offers every authorized publisher whole
    Given the seller offers product "everything" selecting no properties
    When the buyer requests products
    Then product "everything" announces publisher_properties [{"publisher_domain": "news.example", "selection_type": "all"}, {"publisher_domain": "sports.example", "selection_type": "all"}, {"publisher_domain": "weather.example", "selection_type": "all"}]

  @T-UC-GET-PRODUCTS-publisher-unbacked @publisher_domain_resolution @requires_db
  Scenario: a product no authorized property backs is not offered
    Given the seller offers product "premium" selecting property tags "premium"
    And the seller offers product "orphan" selecting property tags "podcast"
    When the buyer requests products
    Then the buyer receives exactly the products "premium"

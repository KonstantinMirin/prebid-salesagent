# Manual feature: which products a legacy format_id filter selects. Sibling of
# BR-UC-GET-PRODUCTS-format-options.feature and built the same way — the scenario stores
# REAL products rows and reads the REAL wire.

Feature: A legacy format_id filter on get_products selects on the declaring agent, not the id alone
  As a Buyer Agent
  I want filters.format_ids to name the format of ONE agent
  So that a reference to another agent's format is never answered with this seller's product

  # core/format-id.json, on agent_url: "Callers comparing two `format-id` values MUST
  # canonicalize `agent_url` per the AdCP URL canonicalization rules before treating two
  # formats as the same." core/product-filters.json binds that MUST to this filter: its
  # `format_ids.items` is a $ref to that file, so each item is a reference object whose
  # identity is the (agent_url, id) PAIR — not a bare slug.
  #
  # A format id is only unique inside its declaring agent's namespace: "display_300x250"
  # at one creative agent and "display_300x250" at another are different formats, and the
  # ids are human-chosen slugs so the collision is the common case rather than the odd one.
  # So a filter that matched on the id alone answers a reference to SOMEBODY ELSE'S format
  # with this seller's product — a false positive, which is the worse direction: the buyer
  # proceeds to buy inventory for a format the seller does not host.
  #
  # The sibling filter on list_creative_formats already honours this
  # (src/core/tools/creative_formats.py), and tests/bdd/e2e_rest_known_failures.txt records
  # why the row below names a DIFFERENT agent rather than a respelling of the same one: the
  # UC-005 third-party scenario xpassed VACUOUSLY for exactly as long as its discriminating
  # assertion compared a hand-built raw tuple against canonicalized identities.
  #
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/format-id.json property=agent_url
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/product-filters.json property=format_ids

  Background:
    Given a tenant is configured for product discovery

  @T-UC-GET-PRODUCTS-format-id-filter-foreign-agent @format_id_filter @requires_db
  Scenario: a format_ids filter naming one agent's format does not select another agent's product that shares the id
    Given the seller stores two products whose formats share one id under two different creative agents
    When the buyer requests products filtering format_ids by that id under the second agent only
    Then the announced products are exactly the product whose format the filter named
    And the announced products do not include the product declaring that id under the other agent
    # Falsifiable in BOTH directions by one request, which is what the second outcome adds.
    # The catalog holds a product the filter does NOT select, so:
    #
    #   * a filter comparing the (agent_url, id) pair returns one product — the named one;
    #   * a filter comparing the id alone returns BOTH, and fails the first outcome;
    #   * a filter that matched nothing returns NEITHER, and also fails the first outcome.
    #
    # A fixture whose every product the filter selects cannot distinguish the first case
    # from the second, and a bare "does not include" outcome cannot distinguish it from the
    # third. Both products are otherwise identical — same id, same pricing — so a row that
    # fails is reporting on the agent_url comparison and on nothing else.

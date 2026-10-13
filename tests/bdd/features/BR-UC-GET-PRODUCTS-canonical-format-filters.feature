# Manual feature: which products the CANONICAL format filters select. Sibling of
# BR-UC-GET-PRODUCTS-format-id-filter.feature and built the same way — every scenario
# stores REAL products rows, including one the filter must NOT select, and reads the REAL
# wire.

Feature: Canonical format filters on get_products narrow the catalogue the buyer receives
  As a Buyer Agent
  I want filters.format_kinds and standard_formats_only to decide which products come back
  So that a product I excluded is never in the answer

  # core/product-filters.json, root: "Filters decide which products MAY BE RETURNED based
  # on metadata, commercial fit, availability assumptions, dates, budget, and reporting
  # support; they do not become package delivery targeting."
  #
  # That makes an ignored filter a correctness defect rather than a missing capability. An
  # unsupported OPERATION can be refused (see salesagent-8qela.8, where the spec's answer
  # for keyword targeting is UNSUPPORTED_FEATURE); a filter has no such story available,
  # because silently ignoring one hands the buyer products it asked to exclude and nothing
  # in the response says so. `filters.format_kinds` was DECLARED on the request and read by
  # nothing — measured, `git grep format_kinds -- src/` hit one docstring.
  #
  # Every scenario here stores a product the filter must NOT return. A filter test whose
  # expected set is derived from the seeded catalogue passes with the filter deleted, which
  # is the trap the sibling format_id feature documents at length.
  #
  # @source repo=adcp ref=v3.2.3 path=_schemas/3.2/core/product-filters.json property=format_kinds
  # @source repo=adcp ref=v3.2.3 path=_schemas/3.2/core/product-filters.json property=standard_formats_only

  Background:
    Given a tenant is configured for product discovery

  @T-UC-GET-PRODUCTS-format-kinds-filter @canonical_format_filter @requires_db
  Scenario: a format_kinds filter selects only products declaring one of the named kinds
    Given the seller stores two canonical products declaring different format kinds
    When the buyer requests products filtering format_kinds by the first product's kind only
    Then the announced products are exactly the product declaring the named kind
    And the announced products do not include the product declaring the other kind
    # core/product-filters.json: "Filter to products accepting any of these canonical format
    # kinds", items a $ref to canonical-format-kind.json. So membership is OR over the kind,
    # and the comparison is between closed-vocabulary values rather than the human-chosen
    # slugs the legacy format_ids filter has to canonicalize first.
    #
    # Falsifiable in both directions by one request, which is what the second outcome adds:
    #
    #   * a filter keyed on the declared kind returns one product — the named one;
    #   * a filter that is IGNORED returns BOTH, and fails the first outcome;
    #   * a filter that matched nothing returns NEITHER, and also fails the first outcome.
    #
    # The two products are otherwise identical — same pricing, same properties, neither
    # carrying a legacy arm — so a row that fails is reporting on the kind comparison and
    # on nothing else.

  @T-UC-GET-PRODUCTS-format-option-refs-filter @canonical_format_filter @requires_db
  Scenario: a format_option_refs filter selects on the option's scope, not its id alone
    Given the seller stores two products whose format options share one id under two different scopes
    When the buyer requests products filtering format_option_refs by the product-scoped option only
    Then the announced products are exactly the product whose option the filter named
    And the announced products do not include the product declaring that id under publisher scope
    # core/product-filters.json: "Filter to products accepting any of these EXACT publisher-
    # or product-scoped canonical format options". EXACT is the operative word, and
    # core/format-option-ref.json is a oneOf whose two arms make `publisher_domain` required
    # on one and FORBIDDEN on the other -- so the domain's presence IS the scope
    # discriminator, and a publisher-catalog option and a product-local option sharing one
    # `format_option_id` are DIFFERENT options.
    #
    # This is the exact shape of the legacy format_ids scenario in the sibling feature, one
    # axis over: there, one id under two declaring AGENTS; here, one id under two SCOPES.
    # Both guard the same false positive in the same direction -- answering a reference to
    # somebody else's namespace with this seller's product, so the buyer proceeds to buy
    # inventory for an option the seller does not offer under that scope.
    #
    #   * a filter comparing whole identities returns one product — the named one;
    #   * a filter comparing the id alone returns BOTH, and fails the first outcome;
    #   * an IGNORED filter also returns both, and fails the first outcome;
    #   * a filter that matched nothing returns NEITHER, and also fails the first outcome.
    #
    # The two products are otherwise identical — same option id, same kind, same params,
    # same pricing, both canonical-only — so a failing row is reporting on the scope
    # comparison and on nothing else.

  @T-UC-GET-PRODUCTS-standard-formats-only-canonical @canonical_format_filter @requires_db
  Scenario: standard_formats_only excludes a canonical product declaring a custom format
    Given the seller stores two canonical products, one declaring a custom format kind
    When the buyer requests products with standard_formats_only
    Then the announced products are exactly the product declaring the standard kind
    And the announced products do not include the product declaring the custom kind
    # "Only return products accepting IAB standard formats" (core/product-filters.json).
    #
    # THIS SCENARIO EXISTS BECAUSE A SIBLING TICKET OPENED THE HOLE IT GRADES. The filter
    # used to loop `product.format_ids or []` and prefix-guess "standard" from the legacy
    # slug, so a product with NO legacy arm ran an empty loop and passed the filter
    # UNCONDITIONALLY. Canonical-only products were unrepresentable when that was written —
    # products.format_ids was NOT NULL until migration 08cd415b3d91 — so the hole was
    # latent. Making canonical authoring possible turned it into a live false positive, in
    # the direction that matters: the buyer is handed a product it asked to exclude.
    #
    # `custom` is the discriminating kind because it is the one member of the pinned
    # sixteen-kind vocabulary that names a format outside the standard set. The other
    # fifteen ARE the standard vocabulary, so no prefix heuristic is needed on this arm —
    # which is the whole reason re-keying is an improvement and not a translation.

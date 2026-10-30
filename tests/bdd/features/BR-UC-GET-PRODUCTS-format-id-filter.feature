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

  # THE SAME AGENT IN ANOTHER SPELLING IS THE SAME AGENT. core/format-id.json makes
  # canonicalizing agent_url a MUST before two references are treated as the same format, and
  # docs/reference/url-canonicalization.mdx (3.2.7) says "Implementations MUST apply every
  # step". Each row respells the declaring agent by one step: host case and the default port
  # (steps 2 and 4), the trailing root-label dot (step 2), a removable dot segment (step 5), a
  # percent-encoded unreserved character (step 6), and the root-label dot on an IDN host's
  # A-label (step 2: "This removal applies identically to an input U-label and its equivalent
  # A-label"). A raw U-label is not a row: step 2 has the comparer reject a host that was not
  # ToASCII-normalized, so it is no spelling of the same agent. The counter-example
  # product sits on the same host under another path, which canonicalization keeps distinct
  # ("canonicalization removes only dot segments, never real path segments"), so a filter that
  # dropped the agent from the comparison returns both products and fails the exact set.
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/format-id.json pointer=/properties/agent_url/description
  # @source repo=adcp ref=v3.2.7 path=docs/reference/url-canonicalization.mdx
  @T-UC-GET-PRODUCTS-format-id-filter-respelled-agent @format_id_filter @requires_db
  Scenario Outline: a format_ids filter naming the declaring agent in another spelling selects its product - <spelling>
    Given the seller stores a product declaring "spelled_banner" under "<declared>" and another declaring it under "<other>"
    When the buyer requests products filtering format_ids by "spelled_banner" under "<requested>"
    Then the announced products are exactly the product whose format the filter named

    Examples:
      | spelling                            | declared                           | other                                | requested                              |
      | host case and default port          | https://formats.agent.example/api  | https://formats.agent.example/other  | https://FORMATS.Agent.Example:443/api  |
      | trailing root-label dot             | https://formats.agent.example/api  | https://formats.agent.example/other  | https://formats.agent.example./api     |
      | removable dot segment               | https://formats.agent.example/api  | https://formats.agent.example/other  | https://formats.agent.example/x/../api |
      | percent-encoded unreserved octet    | https://formats.agent.example/api  | https://formats.agent.example/other  | https://formats.agent.example/%61pi    |
      | root-label dot on an IDN host       | https://xn--bcher-kva.example/api  | https://xn--bcher-kva.example/other  | https://xn--bcher-kva.example./api     |

  # A LEGACY REFERENCE IS MATCHED ON THE CANONICAL SHAPE IT NORMALIZES TO.
  # docs/creative/template-format-ids.mdx (3.2.7) § Compatibility: "Normalize them to
  # canonical declarations immediately and do all matching on the canonical shape", and
  # core/product-format-declaration.json: "do not exact-match raw (agent_url, id) pairs once
  # a format_id has been projected". The filter names display_300x250, which the registry
  # projects to an image at 300x250. One product declares display_300x250_image (the same
  # shape under another id), one declares only a canonical image fixed at 300x250, and one
  # declares display_728x90_image. A seller comparing raw pairs selects none of them.
  #
  # Which relation the deprecated filter uses is the SELLER'S CHOICE: the pin names two
  # (canonical-formats.mdx § Format matching vs product satisfaction: equivalence and
  # satisfaction) and product-filters.json says only "Filter by legacy named-format
  # references". This seller answers it with product satisfaction -- a product matches when it
  # would accept a package naming the reference -- the relation create_media_buy applies to
  # the same reference.
  # @source repo=adcp ref=v3.2.7 path=docs/creative/template-format-ids.mdx
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/product-format-declaration.json pointer=/description
  # @source repo=adcp ref=v3.2.7 path=docs/creative/canonical-formats.mdx
  @T-UC-GET-PRODUCTS-format-id-filter-canonical-shape @format_id_filter @requires_db
  Scenario: a format_ids filter selects the products that accept the canonical shape its reference normalizes to
    Given the seller stores products declaring a 300x250 image as "display_300x250_image", as a canonical image option, and a 728x90 image as "display_728x90_image"
    When the buyer requests products filtering format_ids by "display_300x250" at the standard creative agent
    Then the announced products are exactly the two that accept a 300x250 image

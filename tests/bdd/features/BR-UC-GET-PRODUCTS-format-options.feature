# Manual feature: what a stored canonical format declaration looks like when a buyer
# discovers it. Sibling of BR-UC-GET-PRODUCTS-pricing-options.feature and built the same
# way — every scenario stores a REAL products row and reads the REAL wire.

Feature: Canonical format options a seller stores are announced to buyers on the wire
  As a Buyer Agent
  I want each of the seller's canonical format declarations to reach me whole
  So that I can tell which canonical shapes a product accepts without a named-format lookup

  # core/product.json: "Products MUST carry format_ids, format_options, or BOTH" — a root
  # anyOf. This seller carried only the deprecated half; format_options had zero references
  # under src/, so a product could describe itself to a 3.x peer and not at all to a
  # canonical one. These scenarios grade the half that was unrepresentable.
  #
  # The field that makes the whole arrangement work is v1_format_ref. The projection between
  # the two identities runs ONE WAY — registries/v1-canonical-mapping.json is "authoritative
  # for v1 -> v2 projection only" and a seller MUST NOT synthesize a v1 format_id by
  # inverting a structural match — so a canonical declaration that wants a legacy projection
  # has to ASSERT one. That turns serving a legacy peer into a lookup instead of a synthesis,
  # and it is only worth anything if the assertion survives to the buyer, which is what the
  # first scenario grades.
  #
  # @source repo=adcp ref=v3.2.3 path=_schemas/3.2/core/product.json
  # @source repo=adcp ref=v3.2.3 path=_schemas/3.2/core/product-format-declaration.json

  Background:
    Given a tenant is configured for product discovery

  @T-UC-GET-PRODUCTS-format-options-v1-ref @format_option_announcement @requires_db
  Scenario: a stored declaration reaches the buyer with its v1_format_ref intact
    Given the seller stores a canonical format option for "image" with a v1_format_ref to "display_300x250"
    When the buyer requests products
    Then the announced format option declares format_kind "image" and params the seller stored
    And the announced format option carries v1_format_ref naming "display_300x250"
    # Both halves are asserted because either alone is satisfiable without the other. A
    # declaration that arrived with its format_kind and params but no v1_format_ref would
    # pass the first outcome while having lost the one field that makes a legacy projection
    # a lookup — which is exactly what happens on the sibling SDK surface, where
    # v1_format_ref parses into a private attribute and never reaches the wire.

  @T-UC-GET-PRODUCTS-format-options-absent @format_option_announcement @requires_db
  Scenario: a product declaring no format options omits the key rather than announcing null
    Given the seller stores a product with no canonical format options
    When the buyer requests products
    Then the announced product carries no format_options key at all
    And the announced product still carries its format_ids
    # The pin's anyOf is satisfied by either half, so a product carrying only format_ids is
    # legal and must not be answered with format_options: null — an explicitly null member
    # says "declared, and empty", which is a different claim from "not declared".
    #
    # The second outcome is what stops this from passing vacuously: a response that dropped
    # BOTH halves would satisfy the first and leave the product undescribed.

  @T-UC-GET-PRODUCTS-format-options-canonical-only @format_option_announcement @requires_db
  Scenario: a canonically-authored product is announced with its declarations and no format_ids
    Given the seller stores a canonically-authored product for "image" with no format_ids
    When the buyer requests products
    Then the announced format option declares format_kind "image" and params the seller stored
    And the announced product carries no format_ids key at all
    # The exact MIRROR of the scenario above, and the shape 3.2 tells new products to use:
    # core/product.json's root anyOf has a "Canonical-format product" branch, format_ids is
    # "Deprecated in AdCP 3.2; removed in AdCP 4.0", and it is absent from the root
    # `required` list. So a product declaring only format_options is legal and must not be
    # answered with format_ids at all.
    #
    # Omission is the whole point, and an EMPTY array would be worse than absence: the
    # deprecated anyOf branch requires only the KEY, so `format_ids: []` satisfies that
    # branch by presence while declaring no format whatever. That is the bug this grades.
    #
    # The first outcome is what stops it passing vacuously. A response that dropped BOTH
    # halves would satisfy "no format_ids key" and leave the product undescribed -- the
    # same trap the sibling scenario above guards with its second outcome, in the other
    # direction.
    #
    # Two things had to change for this to be representable at all: products.format_ids
    # was NOT NULL until migration 08cd415b3d91, and product_conversion REFUSED a product
    # whose legacy arm was absent -- so the canonical shape was unstorable and then
    # unservable.

  @T-UC-GET-PRODUCTS-format-options-unannounceable @format_option_announcement @requires_db
  Scenario Outline: a stored declaration the seller cannot announce is refused, not half-announced
    # core/product-format-declaration.json puts format_kind and params in `required`. A
    # stored row missing either cannot become a valid declaration, and no database
    # constraint covers the contents of this JSON column, so the seller really can hold one.
    #
    # INTERNAL_ERROR, on the same reasoning the sibling pricing scenarios use: it is the
    # seller's own data that is wrong and there is nothing the buyer can correct. Emitting a
    # declaration that would fail the buyer's own schema check is the alternative, and it is
    # worse.
    Given the seller stores a canonical format option <missing a required member>
    When the buyer requests products
    Then the response contains error code INTERNAL_ERROR

    Examples: stored declarations that cannot be announced
      | missing a required member |
      | with no params            |
      | with no format_kind       |

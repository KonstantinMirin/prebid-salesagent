# Manual feature: whether a buyer's format selector satisfies what the product declares.
# Sibling of BR-UC-GET-PRODUCTS-format-options.feature — that one grades that a canonical
# declaration REACHES the buyer; this one grades that the seller then HOLDS the buyer to it.

Feature: A format selector must satisfy the canonical declaration the product published
  As a Buyer Agent
  I want a package whose format selector under-specifies the product's declaration refused
  So that I am told before the buy exists, rather than sold inventory no creative can fill

  # THE AUTHORITY is docs/creative/formats.mdx § Matching and satisfaction (3.2.3, the
  # pinned version), which states the relation as five rules:
  #
  #   - Exact dimensions and durations must match.
  #   - A requested range must be contained within the accepted range; overlap is
  #     insufficient.
  #   - Required slots must be present with compatible asset types.
  #   - An exact publisher claim must match both publisher_domain and format_option_id.
  #   - Equal format_kind values alone do not prove compatibility.
  #
  # and core/product-format-declaration.json's seller_preference, which is normative that
  # format_options[] "IS the closed set of accepted formats; anything outside the list is
  # rejected at create_media_buy regardless of preference". The refusal is
  # UNSUPPORTED_FEATURE: the pinned error-code enum classifies it `correctable` ("check
  # get_adcp_capabilities and remove unsupported fields"), which is exactly the buyer's
  # lever here — name a format this product publishes.
  #
  # WHAT WAS WRONG BEFORE. Four separate gates asked this question and all four read only
  # the DEPRECATED format_ids arm, so a product declaring format_options[] imposed no
  # format restriction anywhere: a buyer naming a bare `image` against a product that
  # fixes 300x250 was accepted. The two canonical selector arms the pin added
  # (format_option_refs, and format_kind + params) were parsed and then ignored. The four
  # gates did not even agree on their shared blind spot — the create gate SKIPPED a
  # creative carrying no legacy assertion while the update and assignment gates REFUSED
  # one, so one buyer input had two answers depending on which tool received it.
  #
  # EVERY SCENARIO HERE SEEDS A DUAL-ARM PRODUCT — format_ids AND format_options, which is
  # the shape the conformance fixture canonical_formats_mrec_display uses. Not incidental:
  # a canonical-ONLY product's legacy selector route is resolved by stage 4 (work item C3),
  # so seeding one would make these scenarios fail on a route nothing has wired yet instead
  # of on the satisfaction rule each one names.
  #
  # @source repo=adcp ref=v3.2.3 path=docs/creative/formats.mdx
  # @source repo=adcp ref=v3.2.3 path=_schemas/3.2/core/product-format-declaration.json
  # @source repo=adcp ref=v3.2.3 path=dist/compliance/3.2.3/protocols/media-buy/scenarios/canonical_formats.yaml

  Background:
    Given a tenant is configured for media buy creation

  @T-UC-FORMAT-SATISFACTION-accepted @format_satisfaction @requires_db
  Scenario Outline: a selector that satisfies the declaration is accepted - <selector>
    Given the seller declares a canonical format option "<declaration>"
    And the buyer's package selects "<selector>"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer receives the media buy

    Examples:
      | declaration    | selector                        |
      | fixed_300x250  | exact_300x250                   |
      | fixed_300x250  | product_option_ref              |
      | fixed_300x250  | legacy_display_300x250          |
      | duration_range | contained_range                 |
      | required_slots | covering_slots                  |
      | publisher_300  | matching_publisher_claim        |
      | fixed_300x250  | option_plus_projectable_legacy  |
      | fixed_300x250  | direct_plus_legacy              |

    # These rows are what stops the refusal outline below from passing vacuously. Every
    # pair (declaration, selector) here differs from a row there by ONE thing — the
    # selector — against the SAME declaration, so a gate that refused everything would
    # redden here and a gate that refused nothing would redden there. Measured: before the
    # satisfaction function existed, every row in BOTH outlines was accepted.
    #
    # `product_option_ref` and `legacy_display_300x250` are the two EXACT routes: each
    # names one declaration outright, so a selector stating no params is complete and must
    # be accepted. That is the distinction between
    # create_media_buy_with_canonical_format_option (an option ref, no params, ACCEPT) and
    # reject_bare_image_selector_for_fixed_mrec (a kind, no params, REJECT) — without it
    # they are the same input.

  @T-UC-FORMAT-SATISFACTION-refused @format_satisfaction @requires_db
  Scenario Outline: a selector that does not satisfy the declaration is refused - <selector>
    Given the seller declares a canonical format option "<declaration>"
    And the buyer's package selects "<selector>"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused UNSUPPORTED_FEATURE naming the "<arm>" selector

    Examples:
      | declaration    | selector                          | arm                |
      | fixed_300x250  | bare_image_kind                   | format_kind        |
      | fixed_300x250  | mismatched_728x90                 | format_kind        |
      | fixed_300x250  | unpublished_video_kind            | format_kind        |
      | fixed_300x250  | unpublished_option_ref            | format_option_refs |
      | duration_range | overlapping_range                 | format_kind        |
      | required_slots | slot_missing                      | format_kind        |
      | publisher_300  | wrong_publisher_domain            | format_option_refs |
      | fixed_300x250  | option_plus_unprojectable_legacy  | format_ids         |
      | fixed_300x250  | bare_kind_beside_option_ref       | format_kind        |

    # bare_image_kind IS the storyboard's reject_bare_image_selector_for_fixed_mrec, and
    # mismatched_728x90 is formats.mdx's fifth rule stated as an input: the two selectors
    # name the SAME format_kind the product publishes and differ only in their params, so a
    # seller that treated an equal kind as proof of compatibility would accept both.
    #
    # The field is asserted, not just the code: core/error.json defines `field` as the
    # JSONPath-lite pointer naming WHICH request field was rejected, and the two canonical
    # arms are different fields — a refusal that named the wrong one would send the buyer
    # to edit a selector they did not write. The buyer-facing MESSAGE is deliberately not
    # asserted anywhere here: it is a function of the code through CODE_TABLE, so pinning
    # both would compare the table to itself.
    #
  # ── The CREATIVE side of the same function ────────────────────────────────────────────
  #
  # The two scenarios above grade a PACKAGE SELECTOR. These two grade a stored CREATIVE
  # through the same function, on the create path's pre-adapter gate -- one of the four
  # gates the satisfaction function replaced. A creative seeded by canonical kind asserts
  # NO legacy reference, which is precisely the input those four gates disagreed about: the
  # create gate skipped it, the update and assignment gates refused it, and NONE of them
  # looked at format_options[] at all. So before this change a canonical creative was
  # accepted onto any product whatever its closed set said.
  #
  # A creative passes params=None into the function -- it states no canonical params, because
  # the stored identity is a kind and an option and a creative's dimensions live on its
  # assets. So only the CLOSED-SET step can refuse it here, and that is the step these two
  # scenarios separate. Grading a creative on params needs the manifest's assets read as
  # params, which is salesagent-ol033.7.

  @T-UC-FORMAT-SATISFACTION-creative-accepted @format_satisfaction @requires_db
  Scenario: a creative whose canonical kind the product publishes is accepted
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer assigns a creative identified by canonical kind "image"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer receives the media buy

  @T-UC-FORMAT-SATISFACTION-creative-refused @format_satisfaction @requires_db
  Scenario: a creative whose canonical kind the product does not publish is refused
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer assigns a creative identified by canonical kind "video_hosted"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused UNSUPPORTED_FEATURE naming the packages field

    # The pair is what makes either one informative. Both creatives are seeded the same way
    # and differ ONLY in the canonical kind they carry, against the SAME image-only product
    # -- so a gate that refused every canonical creative would redden the row above and a
    # gate that refused none would redden this one. Measured before the change: both were
    # accepted.

    # wrong_publisher_domain is the second half of formats.mdx's fourth rule. It carries
    # the SAME format_option_id the product publishes under a DIFFERENT publisher_domain,
    # which the pin makes a different option outright: the two arms of
    # core/format-option-ref.json declare publisher_domain required on one and forbidden on
    # the other, so the domain's presence is the discriminator and matching the id alone
    # would answer a publisher-catalogue reference with a product-local option.
    #
    # THE LAST TWO ROWS ARE THE ORDERING OBLIGATION, and they are the reason every route is
    # resolved rather than the first that succeeds. Both carry a format_option_ref that
    # RESOLVES, so a seller that stopped at the first satisfied route would accept both.
    # core/product-format-declaration.json's step-15 step states it: "Resolution failure is
    # reported before selector equivalence and must not be mislabeled
    # CONFLICTING_SELECTORS" -- and step 13 says "canonical precedence MUST NOT hide the
    # dimensional conflict", so precedence is not a short circuit. The `arm` column is what
    # grades it: the refusal must name format_ids / format_kind, the route that actually
    # failed, and NOT the format_option_refs that succeeded. Their mirrors in the accept
    # outline (option_plus_projectable_legacy, direct_plus_legacy) are the same two shapes
    # with the second route RESOLVING, so neither outline can pass by refusing or by
    # accepting everything that carries two routes.
    #
    # What is deliberately NOT graded here: CONFLICTING_SELECTORS when two routes both
    # resolve and select DIFFERENT declarations (steps 13 and 14). That comparison is stage
    # 4's; this stage resolves each route and reports a resolution failure, which is the
    # half the ordering obligation constrains.

# Manual feature: whether a buyer's format selector satisfies what the product declares.
# Sibling of BR-UC-GET-PRODUCTS-format-options.feature — that one grades that a canonical
# declaration REACHES the buyer; this one grades that the seller then HOLDS the buyer to it.

Feature: A format selector must satisfy the canonical declaration the product published
  As a Buyer Agent
  I want a package whose format selector under-specifies the product's declaration refused
  So that I am told before the buy exists, rather than sold inventory no creative can fill

  # THE AUTHORITY is docs/creative/formats.mdx § Matching and satisfaction (at the pin),
  # which states the relation as five rules:
  #
  #   - Exact dimensions and durations must match.
  #   - A requested range must be contained within the accepted range; overlap is
  #     insufficient.
  #   - Required slots must be present with compatible asset types.
  #   - An exact publisher claim must match both publisher_domain and format_option_id.
  #   - Equal format_kind values alone do not prove compatibility.
  #
  # WHICH CONSTRAINTS A SELECTOR MUST STATE is named, not left to the shape of the
  # constraint. docs/creative/canonical-formats.mdx § Format matching vs product
  # satisfaction: "When the product declares a fixed width, height, duration_ms_exact, or
  # duration_ms_range, the requested creative or package selector MUST declare and match
  # that constraint." Any other constraint a selector is silent about is INHERITED -- the
  # same document's normative "Narrows" definition: "when v2.params omits a parameter that
  # v1 specified, v2 inherits v1's value (no narrowing constraint added)" -- and a
  # constraint it does state must still be met. The pin's storyboard grades exactly that
  # split: create_media_buy_with_equivalent_direct_legacy_emission sends a direct route of
  # {width, height} against a declaration that also fixes max_file_size_kb and
  # image_formats, and expects it ACCEPTED with every route graded independently. The
  # direct-selector step that restates those two (create_media_buy_with_direct_canonical_
  # selector) restates them because an earlier runner refused their omission; the changesets
  # that added them say so, and the runner has since been corrected to inherit.
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
  # NEARLY EVERY SCENARIO HERE SEEDS A DUAL-ARM PRODUCT — format_ids AND format_options,
  # which is the shape the conformance fixture canonical_formats_mrec_display uses. Not
  # incidental: a product carrying both arms leaves every selector route reachable, so a
  # refusal is attributable to the satisfaction rule the scenario names rather than to an
  # arm the product never declared.
  #
  # THE ONE EXCEPTION is the purchasability scenario at the end, which seeds a
  # CANONICAL-ONLY product. That was deferred while stage 4 (work item C3) had not yet
  # resolved a canonical-only product's legacy selector route — it now has, so the
  # deferral is spent, and the scenario it was blocking is the one stage-1 guarantee
  # nothing graded.
  #
  # @source repo=adcp ref=v3.2.7 path=docs/creative/formats.mdx
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/product-format-declaration.json
  # @source repo=adcp ref=v3.2.7 path=static/compliance/source/protocols/media-buy/scenarios/canonical_formats.yaml
  # @source repo=adcp ref=v3.2.7 path=docs/creative/canonical-formats.mdx

  Background:
    Given a tenant is configured for media buy creation

  @T-UC-FORMAT-SATISFACTION-accepted @format_satisfaction @requires_db
  Scenario Outline: a selector that satisfies the declaration is accepted - <selector>
    Given the seller declares a canonical format option "<declaration>"
    And the buyer's package selects "<selector>"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer receives the media buy

    Examples:
      | declaration          | selector                       |
      | fixed_300x250        | exact_300x250                  |
      | fixed_300x250        | complete_300x250               |
      | text_limited_300x250 | exact_300x250                  |
      | duration_range       | exact_duration_in_range        |
      | exact_duration       | exact_duration_in_range        |
      | fixed_300x250        | product_option_ref             |
      | fixed_300x250        | legacy_display_300x250         |
      | duration_range       | contained_range                |
      | required_slots       | covering_slots                 |
      | publisher_300        | matching_publisher_claim       |
      | fixed_300x250        | option_plus_projectable_legacy |
      | fixed_300x250        | direct_plus_legacy             |
      | two_image_options    | exact_300x250                  |
      | two_image_options    | mismatched_728x90              |

    # `exact_300x250` against `fixed_300x250` states the fixed size and omits the size cap
    # and the file-format set the declaration also fixes; `complete_300x250` restates them.
    # Both are accepted, and their refusal mirrors below (`oversized_file_300x250`,
    # `unaccepted_image_format_300x250`) state one of those constraints and break it -- so a
    # seller that refused every omission reddens here and one that ignored every
    # non-dimension constraint reddens there. `text_limited_300x250` is the same pair over a
    # numeric limit whose name carries no bound prefix, which is the case that separates a
    # rule keyed on the pin's list from one keyed on the constraint's shape.
    #
    # THE LAST TWO ROWS ARE WORK ITEM M2, and they are the same two selectors that appear
    # in the refusal outline below against `fixed_300x250` — which is what makes them
    # informative. A product publishing TWO image declarations, 300x250 and 728x90, accepts
    # both; a product publishing only the first accepts one and refuses the other. So a
    # seller that graded a bare-kind selector against the FIRST same-kind declaration
    # instead of the one the selector satisfies reddens `two_image_options |
    # mismatched_728x90` and nothing else — which is exactly what it did
    # (salesagent-ky23p). core/product-format-declaration.json is why a product may be
    # shaped that way: format_option_id is "REQUIRED when a product contains multiple
    # declarations with the same format_kind", so several per kind is the case the pin
    # names, not an exotic one.

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
      | declaration          | selector                         | arm                |
      | fixed_300x250        | bare_image_kind                  | format_kind        |
      | fixed_300x250        | mismatched_728x90                | format_kind        |
      | fixed_300x250        | unpublished_video_kind           | format_kind        |
      | fixed_300x250        | unpublished_option_ref           | format_option_refs |
      | duration_range       | overlapping_range                | format_kind        |
      | required_slots       | slot_missing                     | format_kind        |
      | publisher_300        | wrong_publisher_domain           | format_option_refs |
      | fixed_300x250        | option_plus_unprojectable_legacy | format_ids         |
      | fixed_300x250        | legacy_display_728x90            | format_ids         |
      | two_image_options    | mismatched_160x600               | format_kind        |
      | fixed_300x250        | oversized_file_300x250           | format_kind        |
      | fixed_300x250        | unaccepted_image_format_300x250  | format_kind        |
      | text_limited_300x250 | headline_over_limit_300x250      | format_kind        |
      | duration_range       | duration_omitted                 | format_kind        |
      | duration_range       | exact_duration_outside_range     | format_kind        |
      | duration_range       | range_over_upper_bound           | format_kind        |
      | exact_duration       | exact_duration_mismatched        | format_kind        |
      | exact_duration       | contained_range                  | format_kind        |
      | required_slots       | slot_wrong_asset_type            | format_kind        |
      | publisher_300        | wrong_publisher_option_id        | format_option_refs |

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
    # legacy_display_728x90 is a SINGLE legacy route that normalizes and then selects
    # nothing: measured on the pinned wheel, display_728x90 upgrades to display_image +
    # 728x90 and canonical_kind_for answers `image`, so against a product fixing 300x250 it
    # resolves and satisfies no declaration. The pin puts that in this bucket by itself —
    # "A single resolved route that does not satisfy the product is rejected with
    # UNSUPPORTED_FEATURE" — and the SAME legacy id beside a resolving option ref is
    # CONFLICTING_SELECTORS in the outline below. The two rows differ in the presence of the
    # second route and in nothing else, which is what grades the distinction rather than
    # asserting it: before this change this row was ACCEPTED, because an unmatched legacy
    # route fell through to the bare-kind route whose params grading a legacy route skips
    # (salesagent-t0uoo).
    #
    # duration_omitted is the duration half of the named list: a range is one of the four
    # constraints a selector MUST state, so a bare video_hosted is under-specified for a
    # product that bounds its duration -- canonical-formats.mdx's own example row,
    # "video_hosted with no duration ... Reject for this product". exact_duration_outside_range
    # pairs with exact_duration_in_range above: the same key, inside and outside the range.
    #
    # THE FIVE ROWS AFTER exact_duration_outside_range each grade one half of a rule that a
    # sibling row grades only together with another half, so a seller checking one half
    # passes the sibling and reddens here:
    #   - range_over_upper_bound mirrors overlapping_range on the HIGH endpoint ([10000,
    #     90000] against [5000, 60000]); containment tests both ends.
    #   - exact_duration_mismatched is "Exact ... durations must match" against a
    #     duration_ms_exact declaration, paired with exact_duration | exact_duration_in_range
    #     in the accept outline (30000 against 30000 accepted, 15000 refused).
    #   - exact_duration | contained_range: a RANGE claim does not satisfy an exact duration,
    #     because a 10s creative meets the claim and not the product. duration_ms_exact is
    #     one of the four constraints a selector MUST state (canonical-formats.mdx).
    #   - slot_wrong_asset_type offers the required group video_main as an image. slot_missing
    #     differs in the group AND the type, so only this row grades "with compatible asset
    #     types" by itself.
    #   - wrong_publisher_option_id names the RIGHT publisher_domain and an option id it does
    #     not publish; wrong_publisher_domain is the other half of "must match both
    #     publisher_domain and format_option_id".
    #
    # mismatched_160x600 is M2's refusal half: a selector that satisfies NEITHER of the two
    # image declarations the product publishes. Without it, the two M2 accept rows above are
    # satisfied by a seller that accepts any image selector whatever its params say.

  @T-UC-FORMAT-SATISFACTION-conflicting @format_satisfaction @requires_db
  Scenario Outline: co-present selector routes that select different declarations are refused - <selector>
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer's package selects "<selector>"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused CONFLICTING_SELECTORS naming the package

    Examples:
      | selector                       |
      | option_plus_conflicting_legacy |
      | option_plus_conflicting_direct |
      | bare_kind_beside_option_ref    |

    # THE STORYBOARD'S TWO CONFLICT STEPS, as inputs.
    # option_plus_conflicting_legacy is reject_conflicting_dual_emission ("The canonical
    # option selects the product's 300x250 image declaration while the registry-backed
    # legacy display_728x90 selector normalizes to a 728x90 image. Canonical precedence must
    # not hide the dimensional conflict."), and option_plus_conflicting_direct is
    # reject_conflicting_canonical_routes ("The product-local option selects the fixed
    # 300x250 declaration while the co-present direct selector describes a 728x90 image.").
    #
    # WHY AN EMPTY SELECTED SET IS A CONFLICT AND NOT AN UNSUPPORTED_FEATURE. The product
    # publishes ONE image option, so the 728x90 route selects no option at all — and
    # reject_conflicting_canonical_routes grades that exact fixture as
    # CONFLICTING_SELECTORS. There is no other mechanism by which that step produces that
    # code, so "selects nothing" is a differing selected option set under
    # media-buy/package-request.json step (2) ("require the selected option sets to match").
    # bare_kind_beside_option_ref is the same shape with the params OMITTED rather than
    # wrong, so it takes the same code; it was graded UNSUPPORTED_FEATURE until this change,
    # when the comparison did not exist yet (salesagent-iql3e).
    #
    # THE PAIRING THAT MAKES THIS OUTLINE INFORMATIVE is in the accept outline above:
    # option_plus_projectable_legacy and direct_plus_legacy are these same two shapes with
    # the second route AGREEING, against the same declaration. So an always-conflict seller
    # reddens there and an always-accept seller reddens here, and neither outline can be
    # satisfied by a seller that reads only one route.
    #
    # The field is the PACKAGE and not an arm, which is this refusal's own shape: no single
    # arm is at fault, the set of them is, and enums/error-code.json says so for this code —
    # "error.field SHOULD point at the conflicting package". The sibling row
    # option_plus_unprojectable_legacy above stays UNSUPPORTED_FEATURE naming format_ids,
    # because an unnormalizable legacy id fails step (1) and the pin forbids relabelling it:
    # "Resolution failure is reported before selector equivalence and must not be
    # mislabeled CONFLICTING_SELECTORS."

  # ── Coverage: the selected format must cover every INCLUDED placement ─────────────────
  #
  # docs/creative/formats.mdx § Matching and satisfaction: "For a product with multiple
  # included placements, the selected format set must cover every placement. A seller must
  # reject or refine a package with an uncovered placement; it must not silently remove
  # inventory." core/product.json's format_options description restates it ("uncovered
  # inventory MUST be rejected or refined, never silently omitted") and says how a
  # placement's accepted set is computed: the intersection of the product format_options
  # and the placement's inline format_options, matched by format_option_id. This seller
  # rejects, with the satisfaction refusal: UNSUPPORTED_FEATURE naming the arm whose
  # selection left the placement uncovered.
  #
  # Every row stores two_image_options (image 300x250 and image 728x90) and differs only in
  # the stored placements and the selector. `split` has two INCLUDED placements, one
  # accepting each option, so neither option covers both. `split_leaderboard_targetable`
  # is `split` with the 728x90 placement TARGETABLE: core/placement.json makes an included
  # placement "fixed product inventory" that every package buys, while a targetable one is
  # bought only through placement_selection, so that row grades the mode and nothing else.
  # `shared` has both included placements accepting 300x250.
  #
  # A package with NO selector is accepted against `split`: media-buy/package-request.json,
  # "omitting both selects all formats supported by the product", and the product set
  # covers both placements.
  #
  # @source repo=adcp ref=v3.2.7 path=docs/creative/formats.mdx
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/product.json pointer=/properties/format_options/description
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/placement.json pointer=/properties/mode/description

  @T-UC-FORMAT-SATISFACTION-placements-covered @format_satisfaction @requires_db
  Scenario Outline: a selected format that covers every included placement is accepted - <placements> <selector>
    Given the seller declares canonical format options "two_image_options" across placements "<placements>"
    And the buyer's package selects "<selector>"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer receives the media buy

    Examples:
      | placements                   | selector           |
      | shared                       | product_option_ref |
      | split_leaderboard_targetable | product_option_ref |
      | split                        | no_selector        |

  @T-UC-FORMAT-SATISFACTION-placements-uncovered @format_satisfaction @requires_db
  Scenario Outline: a selected format that leaves an included placement uncovered is refused - <selector>
    Given the seller declares canonical format options "two_image_options" across placements "split"
    And the buyer's package selects "<selector>"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused UNSUPPORTED_FEATURE naming the "<arm>" selector

    Examples:
      | selector           | arm                |
      | product_option_ref | format_option_refs |
      | exact_300x250      | format_kind        |

    # Each refusal row has an accept row that differs in ONE thing: `shared` (the second
    # placement also accepts 300x250) and `split_leaderboard_targetable` (the second
    # placement is not included). A seller that ignored placements accepts both refusal
    # rows; one that refused every multi-placement product reddens all three accept rows.
    # Both selectors select the same 300x250 declaration by different routes, so the refusal
    # is about the selected declaration and not the route that named it.

  # ── The CREATIVE side of the same function ────────────────────────────────────────────
  #
  # The two scenarios above grade a PACKAGE SELECTOR. The ones below grade a stored CREATIVE
  # through the same function, on the create path's pre-adapter gate -- one of the four
  # gates the satisfaction function replaced. A creative seeded by canonical kind asserts
  # NO legacy reference, which is precisely the input those four gates disagreed about: the
  # create gate skipped it, the update and assignment gates refused it, and NONE of them
  # looked at format_options[] at all. So before this change a canonical creative was
  # accepted onto any product whatever its closed set said.
  #
  # A creative passes params=None into the satisfaction function -- it states no canonical
  # params, because the stored identity is a kind and an option and a creative's dimensions
  # live on its assets. So the SATISFACTION function can refuse it only on the CLOSED-SET
  # step, which is what the first two scenarios separate. The gate's OTHER check, the one
  # that reads those assets, is a different refusal with a different code and is the third
  # scenario. Grading a creative's assets as satisfaction PARAMS -- dimensions on the
  # manifest against dimensions on the declaration -- is neither, and is salesagent-ol033.7.

  @T-UC-FORMAT-SATISFACTION-creative-accepted @format_satisfaction @requires_db
  Scenario: a creative whose canonical kind the product publishes is accepted
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer assigns a creative identified by canonical kind "image" with its media asset keyed "image_main"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer receives the media buy

  @T-UC-FORMAT-SATISFACTION-creative-refused @format_satisfaction @requires_db
  Scenario: a creative whose canonical kind the product does not publish is refused
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer assigns a creative identified by canonical kind "video_hosted" with its media asset keyed "image_main"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused UNSUPPORTED_FEATURE naming the packages field

    # The pair is what makes either one informative. Both creatives are seeded the same way
    # and differ ONLY in the canonical kind they carry, against the SAME image-only product
    # -- so a gate that refused every canonical creative would redden the row above and a
    # gate that refused none would redden this one. Measured before the change: both were
    # accepted.
    #
    # The asset key is stated on both rows and is the SAME on both, which is what keeps the
    # kind the only difference. On this row it is also inert: the closed-set refusal is
    # raised before the asset gate's collected errors are answered, so this creative is
    # refused for its kind whatever its assets are keyed.

  # ── Whether the seller can READ a canonical creative's assets at all ──────────────────
  #
  # The accept row above is only reachable if the seller can find the creative's media
  # asset, and for a canonical creative that is a separate question from the closed set.
  # core/product-format-declaration.json's params.slots[] carries
  # {asset_group_id, asset_type, required}, and each canonical schema states its own list as
  # the slots DEFAULT -- formats/canonical/image.json defaults to image_main (image) plus
  # headline/body_text/primary_text/cta (text) and landing_page_url (url). So the
  # declaration ALREADY SAYS what a canonical creative's assets are called.
  #
  # WHAT WAS WRONG BEFORE. extract_media_url_and_dimensions found a creative's media asset
  # either by asking the LEGACY format spec for its asset_id, or by matching a hardcoded
  # 9-member MEDIA_ASSET_FALLBACK_IDS allowlist of naming conventions. A creative identified
  # by its canonical kind asserts no legacy reference, so no spec resolves and the allowlist
  # was the only path left -- meaning a canonical creative's assets were readable only by
  # COINCIDENCE of asset-id naming. Measured: the same creative keyed image_main (what the
  # pin declares) was refused "missing required URL field in assets", and keyed banner_image
  # (what this seller happened to guess) was accepted. That is salesagent-ol033.16, and it is
  # why the accept row above used to seed banner_image with a comment apologising for it.
  #
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/formats/canonical/image.json pointer=/properties/slots/default

  @T-UC-FORMAT-SATISFACTION-creative-asset-unnamed @format_satisfaction @requires_db
  Scenario: a canonical creative whose media asset no slot names is refused
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer assigns a creative identified by canonical kind "image" with its media asset keyed "banner"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused VALIDATION_ERROR naming the packages field

    # THE CONTROL FOR THE ACCEPT ROW, and the reason that row is not satisfied by a gate
    # that simply stopped checking. This creative and the accepted one are the same kind,
    # the same asset, the same product, and differ in ONE character sequence: the key its
    # media asset is stored under. `banner` is CreativeFactory's own default and is named by
    # nothing -- not a slot of any of the sixteen canonical kinds, and not a member of the
    # fallback allowlist either -- so the seller genuinely cannot find a URL or dimensions
    # for it, and refusing is correct. A fix that made the gate read the declaration would
    # redden the accept row if it failed and redden this one if it over-reached.
    #
    # The CODE differs from its sibling refusal above, and that is graded rather than
    # incidental: a creative outside the published closed set is UNSUPPORTED_FEATURE, while
    # a creative the product does publish whose assets cannot be read is VALIDATION_ERROR.
    # The two have different buyer recoveries -- name another format, versus re-sync this
    # creative -- so a gate that collapsed them would send the buyer to the wrong fix.
    #
    # NOT GRADED HERE, and filed rather than assumed: a canonical audio creative carries no
    # dimensions at all and this same gate demands them of every creative
    # (salesagent-bcqev), and a canonical creative's clickthrough slot landing_page_url is
    # in no allowlist so the click URL is dropped silently (salesagent-7xi64). Both block
    # stage 6.

  @T-UC-FORMAT-SATISFACTION-schema-invalid @format_satisfaction @requires_db
  Scenario: an atomically-incomplete dimension is a SCHEMA refusal, not a satisfaction one
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer's package selects "width_without_height"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused INVALID_REQUEST

    # The storyboard's reject_image_width_without_height, and it is in THIS phase, so it is
    # accounted for here rather than assumed to be someone else's. Its negative_path is
    # `schema_invalid` while every other refusal in the phase is `payload_well_formed`, and
    # the error bucket differs with it: INVALID_REQUEST, not UNSUPPORTED_FEATURE.
    #
    # MEASURED, not assumed: the pinned PackageRequest refuses `params: {width: 300}` with
    # no height on construction -- "violates a constraint its schema states outside its
    # properties (media-buy/package-request.json, root conjunct 3) over format_kind, height,
    # params" -- so fixed-size dimension atomicity is enforced by the REQUEST BOUNDARY and
    # the selector never reaches the satisfaction function. The owner is the pinned model,
    # which is the right owner; what needed grading is that the two buckets stay apart,
    # because a seller that let this through to satisfaction would answer the buyer
    # UNSUPPORTED_FEATURE ("this product cannot do that") for a request that is simply
    # malformed ("you did not finish the dimensions"). Those are different recoveries.

  # ── The same function on the UPDATE and ASSIGNMENT paths ──────────────────────────────
  #
  # The bead's grading clause names three paths -- "BDD scenarios run against CREATE, UPDATE
  # and ASSIGNMENT paths" -- and everything above dispatches create_media_buy. These grade
  # the other two. All four gates call ONE function, so the canonical lane is live on all of
  # them by construction; what was ungraded is whether each path actually REACHES it and
  # answers on the wire with the same code.
  #
  # This is also where the skip-vs-refuse divergence lived: a creative carrying no legacy
  # assertion was SKIPPED by the create gate and REFUSED by these two, so one buyer input
  # had two answers depending on which tool received it. The accept rows here and the
  # creative accept row above are the same input through three tools, which is what makes
  # the convergence observable rather than asserted.

  @T-UC-FORMAT-SATISFACTION-update-accepted @format_satisfaction @requires_db
  Scenario: update_media_buy accepts a creative whose canonical kind the product publishes
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer already holds a media buy for that product
    And a creative identified by canonical kind "image" exists
    When the Buyer Agent assigns that creative through update_media_buy
    Then the update is accepted

  @T-UC-FORMAT-SATISFACTION-update-refused @format_satisfaction @requires_db
  Scenario: update_media_buy refuses a creative whose canonical kind the product does not publish
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer already holds a media buy for that product
    And a creative identified by canonical kind "video_hosted" exists
    When the Buyer Agent assigns that creative through update_media_buy
    Then the buyer is refused UNSUPPORTED_FEATURE naming the "creative_ids" array

    # The field is asserted here too, and it is a DIFFERENT pointer from the create path's:
    # core/error.json wants it to name the array the buyer actually sent, and this path has
    # two of them (creative_ids / creative_assignments). A canonical refusal used to travel
    # with field=None while the legacy refusals on the same path carried one -- the only
    # refusal here that did not say which array it was about.

  @T-UC-FORMAT-SATISFACTION-sync-accepted @format_satisfaction_sync @requires_db
  Scenario: sync_creatives accepts an assignment whose canonical kind the product publishes
    Given a packaged product declaring a canonical image option fixed at 300x250
    And the buyer syncs a creative identified by canonical kind "image"
    When the Buyer Agent assigns it to that package
    Then the assignment is recorded with no assignment error

  @T-UC-FORMAT-SATISFACTION-sync-refused @format_satisfaction_sync @requires_db
  Scenario: sync_creatives refuses an assignment whose canonical kind the product does not publish
    Given a packaged product declaring a canonical image option fixed at 300x250
    And the buyer syncs a creative identified by canonical kind "video_hosted"
    When the Buyer Agent assigns it to that package
    Then the buyer is refused UNSUPPORTED_FEATURE

  @T-UC-FORMAT-SATISFACTION-sync-lenient-canonical @format_satisfaction_sync @requires_db
  Scenario: lenient validation does not soften a closed-set refusal
    Given a packaged product declaring a canonical image option fixed at 300x250
    And the buyer syncs a creative identified by canonical kind "video_hosted"
    And the buyer asks for lenient validation
    When the Buyer Agent assigns it to that package
    Then the buyer is refused UNSUPPORTED_FEATURE

    # THE ASYMMETRY, graded deliberately because it reads like a bug to anyone who meets it
    # without this scenario. ``validation_mode: "lenient"`` means "skip an assignment this
    # product will not take and record the reason", and the LEGACY lane still does exactly
    # that -- the row below proves it. A CANONICAL refusal does not soften, because the
    # product published a closed set and this creative is outside it: there is no partial
    # assignment to fall back to, and core/product-format-declaration.json calls the
    # closed-set rejection "structural, not negotiable". Without these two rows side by
    # side the next person to read the raise site sees one branch ignoring validation_mode
    # and "fixes" it.

  @T-UC-FORMAT-SATISFACTION-sync-lenient-legacy @format_satisfaction_sync @requires_db
  Scenario: lenient validation does soften a deprecated-arm refusal
    Given a packaged product declaring only the deprecated format_ids
    And the buyer syncs a creative identified by format_id "video_1280x720"
    And the buyer asks for lenient validation
    When the Buyer Agent assigns it to that package
    Then the sync succeeds and records an assignment error for that package

  # ── The LIBRARY UPSERT path: a creative whose format resolves to no canonical kind ────
  #
  # Everything else in this module reaches the satisfaction function through a gate that
  # already exists. These two reach the path that has NONE: sync_creatives writing a
  # creative into the library with no assignment at all.
  #
  # MEASURED: `satisfies` is called once in creatives/_assignments.py and ZERO times in
  # creatives/_processing.py, the upsert path. format_satisfaction.py is the only place that
  # refuses kind=None, and it is not on this path -- so a legacy format_id with no canonical
  # projection was STORED with format_kind NULL rather than refused.
  #
  # The user's ruling is "gate at writing, not write if we can't resolve it", so these grade
  # the refusal AND the absence of the row: a wire envelope cannot tell a seller that refused
  # before writing from one that wrote and then errored, and the second leaves the NULL
  # behind for every later reader.
  #
  # THE PAIR DIFFERS IN ONE THING -- whether the claimed id has a canonical projection.
  # Both ids are SERVED by the pinned agent, so neither row can pass or fail on
  # resolvability over the wire, which is what makes the projection the only variable.
  # Measured against the capture (71 formats) with the spec supplied as the live path
  # supplies it: 64 project, 7 do not, and the 7 are the card/product-card variants.
  # `product_card_standard` is one of them; `display_300x250_image` projects to `image`.
  # The control id has to be SERVED as well as projectable -- `display_300x250` is projectable
  # but ABSENT from the capture, so the authoring door refuses it before the gate is reached.
  #
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/registries/v1-canonical-mapping.json

  @T-UC-FORMAT-SATISFACTION-upsert-unprojectable @creative_library_upsert @requires_db
  Scenario: a creative whose format resolves to no canonical kind is refused, not stored
    Given a packaged product declaring only the deprecated format_ids
    And the buyer syncs a creative identified by format_id "product_card_standard"
    When the Buyer Agent syncs it into the library
    Then the buyer is refused UNSUPPORTED_FEATURE and nothing is stored

  @T-UC-FORMAT-SATISFACTION-upsert-projectable @creative_library_upsert @requires_db
  Scenario: a creative whose format does resolve is stored with its canonical kind
    Given a packaged product declaring only the deprecated format_ids
    And the buyer syncs a creative identified by format_id "display_300x250_image"
    When the Buyer Agent syncs it into the library
    Then the creative is stored carrying canonical kind "image"

    # THE CONTROL, and without it the row above is satisfied by a seller that refuses every
    # library upsert. Same tool, same When, same product, an id the same agent serves -- and
    # it differs only in having a registry projection. It also pins the POSITIVE half of the
    # write gate: the kind actually reaches the column, which is the thing a NOT NULL
    # constraint alone would not show (a seller could satisfy NOT NULL by writing a wrong
    # kind, which is what the fire-probe for this change perturbs).

    # The OTHER half of the asymmetry, and the control for the row above: same tool, same
    # lenient mode, same "this product will not take this creative" condition -- and the
    # legacy lane skips with a recorded error instead of refusing. Both rows are needed:
    # either one alone is satisfied by a gate that treats every mode the same.

  @T-UC-FORMAT-SATISFACTION-sync-sized-conforming @format_satisfaction_sync @requires_db
  Scenario: a creative sized as the deprecated arm requires is accepted
    Given a packaged product selling only a deprecated format sized 300x250
    And the buyer syncs a creative identified by format_id "display_image" sized 300x250
    When the Buyer Agent assigns it to that package
    Then the assignment is recorded with no assignment error

  @T-UC-FORMAT-SATISFACTION-sync-sized-mismatched @format_satisfaction_sync @requires_db
  Scenario: a creative sized differently from the deprecated arm is refused
    Given a packaged product selling only a deprecated format sized 300x250
    And the buyer syncs a creative identified by format_id "display_image" sized 728x90
    When the Buyer Agent assigns it to that package
    Then the buyer is refused VALIDATION_ERROR naming the 300x250 it accepts

    # THE PAIR IS ONE INSTRUMENT and neither row works alone: the accept row alone is
    # satisfied by a seller that takes everything, which is the defect, and the refuse row
    # alone is satisfied by a seller that takes nothing. They differ in exactly the
    # creative's declared dimensions, so what they grade is the comparison and not the id.
    #
    # core/product-format-declaration.json states it under its own "Format matching vs
    # satisfaction (normative)" heading: "when this declaration specifies fixed constraints
    # such as width, height ... a buyer request or creative manifest MUST declare and
    # satisfy those constraints", and it forbids the comparison that was being made --
    # "do not exact-match raw (agent_url, id) pairs". The deprecated arm's accepted set was
    # built from template keys, so a product restricting to 300x250 and one restricting to
    # nothing were the same set and a 728x90 creative was accepted (salesagent-4764o).
    #
    # A TEMPLATE id carrying parameters, because a name-encoded one cannot express this:
    # upgrade_legacy_format_id rewrites the parameters from the name, so
    # display_300x250_image sized 728x90 becomes display_image at 300x250 and matches.

  @T-UC-FORMAT-SATISFACTION-sync-density-mismatched @format_satisfaction_sync @requires_db
  Scenario: a creative at the wrong asset density is refused
    Given a packaged product selling only a deprecated format sized 300x250 at 2x density
    And the buyer syncs a creative identified by format_id "display_image" sized 300x250 at 1x density
    When the Buyer Agent assigns it to that package
    Then the buyer is refused VALIDATION_ERROR naming the 300x250 it accepts

  @T-UC-FORMAT-SATISFACTION-sync-density-silent @format_satisfaction_sync @requires_db
  Scenario: a creative silent about asset density is refused by a product that fixes one
    Given a packaged product selling only a deprecated format sized 300x250 at 2x density
    And the buyer syncs a creative identified by format_id "display_image" sized 300x250
    When the Buyer Agent assigns it to that package
    Then the buyer is refused VALIDATION_ERROR naming the 300x250 it accepts

    # THE FOURTH PARAMETER, and it needs BOTH rows because the two ways to fail it are
    # different: a creative CONTRADICTING the density, and a creative SILENT about it. The
    # pin requires the claim to "declare and satisfy" a fixed constraint, so silence fails
    # it just as a wrong value does -- and core/format-id.json calls pixel_ratio "Required
    # intrinsic-pixel density for a parameterized visual format".
    #
    # These two grade a check this seller makes BESIDE the SDK's, deliberately. adcp's
    # format_is_supported compares a hand-written ("width", "height", "duration_ms") and
    # never reads the fourth field, so a product requiring a 2x asset accepted a 1x one and
    # also accepted one that said nothing. Measured on 9.0.0b3+sa.8qela.bf0228b68: all three
    # of those answered supported=True. Without these rows the local supplement is correct
    # and unfalsifiable -- removing it reddened nothing.

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

  # ── What the seller EMITS and RECORDS once the selector is accepted ───────────────────
  #
  # Everything above grades a refusal or an acceptance. These grade what an acceptance
  # LEAVES BEHIND, which is a separate obligation and an unobserved one:
  # core/package.json calls formats_to_provide the package's "immutable canonical creative
  # contracts ... Each entry is a PackageFormatSnapshot of the selected effective Product
  # format declaration", and requires that "the live Product is never substituted for the
  # package snapshot". The seller emitted the field on no package at all, and emitted its
  # deprecated projection format_ids_to_provide as an ECHO of the buyer's own request arm.
  #
  # BOTH HALVES ARE ASSERTED — the response AND the stored row — and the bead says why: a
  # response-only assertion is echo-satisfiable, which is precisely how
  # T-UC-026-partition-paused passed while the money bug was live. A seller that assembled
  # the snapshot for the reply and stored nothing would pass a response-only scenario and
  # then answer a later read from the live product, which is the substitution the pin names.
  #
  # NEITHER HALF IS GRADED BY THE STORYBOARD: grep over dist/compliance/3.2.3 for
  # formats_to_provide, formats_pending, format_ids_to_provide and format_ids_pending
  # returns ZERO occurrences in any scenario. So these scenarios are the only grading these
  # obligations have, which is the reason they are mandatory rather than nice to have.

  @T-UC-FORMAT-SATISFACTION-snapshot-emitted @format_satisfaction @requires_db
  Scenario: the selected declaration is emitted as a snapshot and persisted on the package
    Given the seller declares a canonical format option "fixed_300x250"
    And the buyer's package selects "product_option_ref"
    When the Buyer Agent sends the create_media_buy request
    Then the package snapshots the "satisfaction_image_mrec" declaration fixed at 300x250
    And the stored package snapshot names the same declaration
    And the package's deprecated format_ids_to_provide names "display_300x250"

    # THE BUYER SENT NO format_ids AT ALL, which is what makes the last Then a derivation
    # rather than an echo: display_300x250 reaches the response only because the SELECTED
    # declaration asserts it in v1_format_ref. Before this change the field was
    # `format_ids_to_provide=package.format_ids`, so this request received nothing on a
    # field whose absence the pin gives a defined meaning to (core/package.json on
    # format_ids_pending: "Absence means legacy readiness was not reported and MUST NOT be
    # interpreted as full coverage").
    #
    # v1_format_ref is the ONLY legal source. registries/v1-canonical-mapping.json:
    # "v2 → v1 projection MUST rely on v1_format_ref on the v2 ProductFormatDeclaration —
    # sellers assert the v1 pairing explicitly. SDKs MUST NOT synthesize a v1 format_id
    # from the registry by inverting structural matches."

  @T-UC-FORMAT-SATISFACTION-snapshot-no-legacy-ref @format_satisfaction @requires_db
  Scenario: a declaration asserting no legacy reference projects to no deprecated array
    Given the seller declares a canonical format option "fixed_300x250_no_ref"
    And the buyer's package selects "product_option_ref"
    When the Buyer Agent sends the create_media_buy request
    Then the package snapshots the "satisfaction_image_mrec" declaration fixed at 300x250
    And the package carries no deprecated format_ids_to_provide

    # THE PAIRED POSITIVE FOR THE ABSENCE, and it is the first Then of this scenario rather
    # than a separate row: an assertion that format_ids_to_provide is ABSENT passes for free
    # under any perturbation that drops the whole package, so it is only informative beside
    # a positive assertion on the same response. The two scenarios differ in ONE thing — the
    # declaration asserts a v1_format_ref or it does not — so a seller that synthesized a
    # legacy reference from the registry reddens here, and a seller that emitted none at all
    # reddens the row above.

  # ── THE MANUAL-APPROVAL PATH, which none of the above reaches ─────────────────────────
  #
  # Every scenario above runs on the AUTO path, and that is not a choice any of them made:
  # MediaBuyCreateEnv seeds human_review_required=False deliberately (its own comment
  # explains why — so the live e2e server's gate state matches the other transports), and
  # its mocked adapter sets manual_approval_operations=[]. So no satisfaction question in
  # this feature has ever been asked with that tenant column flipped.
  #
  # MEASURED on d5c1b3507, through the real _create_media_buy_impl: it is not asked
  # because production cannot answer it. One product declaring one image option fixed at
  # 300x250, one package selecting a bare `image`, and the ONLY difference the tenant
  # column:
  #
  #     human_review_required=False  ->  REFUSED  (UNSUPPORTED_FEATURE)
  #     human_review_required=True   ->  ACCEPTED, submitted
  #
  # The cause is ordering and it is structural, not conditional: the manual-approval branch
  # opens at media_buy_create.py:2828 and its only non-exceptional exit is the return at
  # :3147, while the canonical selector gate is at :3337 — 190 lines later. A second early
  # return at :3267 (product-level configuration approval) bypasses it identically. So
  # everything the gate owns is skipped on this path: the closed set, the params rules, M2,
  # the resolution/selection split and CONFLICTING_SELECTORS.
  #
  # core/product-format-declaration.json leaves no room for an approval-mode carve-out —
  # format_options[] "IS the closed set of accepted formats; anything outside the list is
  # rejected at create_media_buy REGARDLESS OF PREFERENCE" — and
  # media-buy/package-request.json states its four receiver steps with no mode condition
  # either.
  #
  # THESE SCENARIOS ARE RED ON PURPOSE. They are the instrument three beads have been
  # missing, and each one is red for the obligation it names rather than for a reason it
  # inherits: salesagent-gz86t (the gate does not run), salesagent-1dcfo (so no snapshot is
  # recorded), salesagent-zoo82 (so C8 has nothing to read). They land WITHOUT the
  # behaviour change that greens them, which is a different commit and a different scope.
  #
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/media-buy/package-request.json pointer=/description
  # @source repo=adcp ref=v3.2.7 path=static/schemas/source/core/package.json pointer=/properties/formats_to_provide/description

  @T-UC-FORMAT-SATISFACTION-approval-gate-refuses @format_satisfaction @requires_db
  Scenario: a human-review tenant still refuses a selector the product does not accept
    Given the seller declares a canonical format option "fixed_300x250"
    And the tenant requires manual approval
    And the buyer's package selects "bare_image_kind"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer is refused UNSUPPORTED_FEATURE naming the "format_kind" selector

  @T-UC-FORMAT-SATISFACTION-approval-gate-accepts @format_satisfaction @requires_db
  Scenario: a human-review tenant parks a buy whose selector the product does accept
    Given the seller declares a canonical format option "fixed_300x250"
    And the tenant requires manual approval
    And the buyer's package selects "product_option_ref"
    When the Buyer Agent sends the create_media_buy request
    Then the buy is parked for a human decision

    # THE PAIR, and it is the pair that makes the refusal informative rather than a
    # restatement of "manual approval refuses things". Same product, same tenant column,
    # same tool — the selectors differ in exactly whether the product accepts them, which
    # is the dimension being judged. A seller that refused every selector on the approval
    # path would redden this row; one that accepts every selector reddens the row above.
    # This row passes today; the one above does not.

  @T-UC-FORMAT-SATISFACTION-approval-snapshot-recorded @format_satisfaction @requires_db
  Scenario: a parked buy records the declaration its selector selected
    Given the seller declares a canonical format option "fixed_300x250"
    And the tenant requires manual approval
    And the buyer's package selects "product_option_ref"
    When the Buyer Agent sends the create_media_buy request
    Then the parked package snapshots the "satisfaction_image_mrec" declaration fixed at 300x250
    And the parked package's deprecated format_ids_to_provide names "display_300x250"

    # WHY THE PARKED BUY IS THE CASE THAT MATTERS MOST, not an edge of the auto path:
    # core/package.json requires a package to "retain and return this checklist" and says
    # "the live Product is never substituted for the package snapshot". A buy waiting for a
    # human has by construction the LONGEST window between create and execution, so it is
    # where the live product is most likely to have moved on — and measured, it is the one
    # case with no snapshot at all. Its package_config carries the buyer's request arm
    # (`format_ids`) and neither canonical field, so a canonical-only buyer's parked buy
    # records NOTHING about what creative it needs.
    #
    # Read off the stored row rather than the reply, and here that is forced rather than
    # preferred: the submitted envelope carries no media_buy_id at all — correct, and the
    # reason the buy is located by tenant through the repository.

  @T-UC-FORMAT-SATISFACTION-approval-executes-from-snapshot @format_satisfaction @requires_db
  Scenario: approving a parked buy executes the recorded snapshot, not the product as it is now
    Given the seller declares a canonical format option "fixed_300x250"
    And the tenant requires manual approval
    And the buyer's package selects "product_option_ref"
    And the Buyer Agent sent the create_media_buy request
    And the seller then republishes that option fixed at 728x90
    When the publisher approves the parked buy
    Then the ad server is asked for a 300x250 package

    # THE FIXTURE DIFFERS IN THE JUDGED DIMENSION, which is the whole design of this
    # scenario: the product is EDITED between create and approval, so "read the snapshot"
    # and "read the live product" give different answers — 300x250 against 728x90. Without
    # the edit both answers agree and the scenario grades nothing, which is how an approval
    # test passes while reading the live product.
    #
    # The option id is unchanged and only its params move, so this is not a different
    # option being selected: it is the SAME contract the buyer bought, republished with
    # different dimensions. That is exactly what
    # core/package-format-snapshot.json's immutability rule is about — "changing selected
    # format, placement set, execution version, or tracker contract requires a replacement
    # package_id; never mutate this snapshot in place".
    #
    # The observable is what the AD SERVER was asked for, read off the adapter boundary
    # the approval actually calls (_execute_adapter_media_buy_creation ->
    # adapter.create_media_buy), not off a response field. An approval's whole product is
    # the ad-server call; its reply says almost nothing.
    #
    # ONE TRANSPORT NOTE, recorded because it reads like a gap otherwise.
    # execute_approved_media_buy has no registry row and no transport — the admin UI calls
    # it — so this scenario is transport-parametrized on its CREATE half with one identical
    # approval execution. That is still four-transport grading of the half that is a
    # transport, and it is the load-bearing half here: the snapshot is persisted BY the
    # create path, so a transport that persisted a malformed one would be caught. It is not
    # four approval executions, and nothing here pretends otherwise.

  @T-UC-FORMAT-SATISFACTION-canonical-only-purchasable @format_satisfaction @requires_db
  Scenario Outline: a product declaring only canonical format options is purchasable - <selector>
    Given the seller declares a canonical format option "fixed_300x250" and no format_ids
    And the buyer's package selects "<selector>"
    When the Buyer Agent sends the create_media_buy request
    Then the buyer receives the media buy
    And the package snapshots the "satisfaction_image_mrec" declaration fixed at 300x250
    And the package's deprecated format_ids_to_provide names "display_300x250"

    Examples: canonical selector routes against a product with no deprecated arm
      | selector           |
      | exact_300x250      |
      | product_option_ref |

    # THE SHAPE 3.2 TELLS NEW PRODUCTS TO AUTHOR, graded on the buy path rather than the
    # discovery path. core/product.json's root anyOf has a "Canonical-format product"
    # branch, format_ids is "Deprecated in AdCP 3.2; removed in AdCP 4.0" and is absent
    # from the root `required` list — so a product declaring only format_options is legal,
    # and the sibling BR-UC-GET-PRODUCTS-format-options feature already grades that such a
    # product is ANNOUNCED. Whether it can then be BOUGHT was graded by nothing: every
    # other scenario in this file, and every create scenario elsewhere, seeds a product
    # that still carries the deprecated arm. Discoverable-but-unpurchasable is a coherent
    # failure and it had no detector.
    #
    # NO CREATIVE IS ASSIGNED, deliberately. A creative's claimed format reference is
    # RESOLVED against a live catalog, whereas a product's declaration is compared as an
    # identity — so a creative would add a second, independent reason for this scenario to
    # fail (an id the pinned agent does not serve: salesagent-yfu33) while saying nothing
    # about the product's arms, which is its subject. create_media_buy requires no
    # creative; assigning one is BR-UC-FORMAT-SATISFACTION's own creative scenarios' job.
    #
    # THE THIRD OUTCOME SAYS THE PROJECTION STILL HAPPENS WITH NO ARM TO PROJECT FROM.
    # registries/v1-canonical-mapping.json is normative that v2 -> v1 projection "MUST rely
    # on v1_format_ref on the v2 ProductFormatDeclaration", and here the product declares no
    # format_ids whatever — so display_300x250 reaching the package proves the seller read
    # the selected declaration's assertion, and that a canonical-only product still reports
    # legacy readiness rather than leaving a 3.x peer with a field whose absence the pin
    # gives a defined meaning to (format_ids_pending: "Absence means legacy readiness was
    # not reported and MUST NOT be interpreted as full coverage").
    #
    # IT DOES NOT PROVE MORE THAN THAT, and an earlier draft of this comment claimed it
    # did — that a dual-arm fixture cannot tell a projection sourced from the snapshot from
    # one sourced from the product's own arm, because both name display_300x250. Measured,
    # that ambiguity does not exist: _legacy_formats_to_provide reads the snapshot when
    # there is one and the BUYER'S REQUEST arm when there is not, and the product's
    # format_ids column is not a candidate source at either branch. The sibling scenario
    # above already separates the two real sources by sending no request arm. Left here
    # because the claim is the kind that reads plausibly and would have been inherited.
    #
    # WHICH OUTCOME CARRIES THE GRADING, measured by perturbation rather than assumed.
    # Dropping the product's declarations before the selector is graded does NOT refuse the
    # buy — a selector that selects nothing "imposes no format restriction", so the buy
    # succeeds and the package simply carries no snapshot. So the SNAPSHOT outcome is this
    # scenario's discriminating assertion, and the acceptance outcome is its precondition:
    # it is live (grading every canonical claim as under-specified refuses the buy and fails
    # it) but it cannot catch a declarations-plumbing regression on its own. The pairing is
    # what makes the scenario non-vacuous in both directions: the acceptance outcome alone
    # would pass with no format contract at all, and the snapshot outcome alone has no
    # package to read when the buy is refused.
    #
    # BOTH CANONICAL ROUTES, because they resolve independently — a direct format_kind +
    # params selector and a product-scoped format_option_ref reach the declaration by
    # different code, and one working says nothing about the other. The legacy selector
    # route against a canonical-only product is a different question (it resolves through
    # the declaration's asserted ref) and belongs to stage 4's own scenarios, not here.

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
      | declaration       | selector                        |
      | fixed_300x250     | exact_300x250                   |
      | fixed_300x250     | product_option_ref              |
      | fixed_300x250     | legacy_display_300x250          |
      | duration_range    | contained_range                 |
      | required_slots    | covering_slots                  |
      | publisher_300     | matching_publisher_claim        |
      | fixed_300x250     | option_plus_projectable_legacy  |
      | fixed_300x250     | direct_plus_legacy              |
      | two_image_options | exact_300x250                   |
      | two_image_options | mismatched_728x90               |

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
      | declaration       | selector                          | arm                |
      | fixed_300x250     | bare_image_kind                   | format_kind        |
      | fixed_300x250     | mismatched_728x90                 | format_kind        |
      | fixed_300x250     | unpublished_video_kind            | format_kind        |
      | fixed_300x250     | unpublished_option_ref            | format_option_refs |
      | duration_range    | overlapping_range                 | format_kind        |
      | required_slots    | slot_missing                      | format_kind        |
      | publisher_300     | wrong_publisher_domain            | format_option_refs |
      | fixed_300x250     | option_plus_unprojectable_legacy  | format_ids         |
      | fixed_300x250     | legacy_display_728x90             | format_ids         |
      | two_image_options | mismatched_160x600                | format_kind        |

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
    And the buyer syncs a creative identified by format_id "video_640x480"
    And the buyer asks for lenient validation
    When the Buyer Agent assigns it to that package
    Then the sync succeeds and records an assignment error for that package

    # The OTHER half of the asymmetry, and the control for the row above: same tool, same
    # lenient mode, same "this product will not take this creative" condition -- and the
    # legacy lane skips with a recorded error instead of refusing. Both rows are needed:
    # either one alone is satisfied by a gate that treats every mode the same.

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

  # What stage 4 deliberately does NOT land: C8, the approval/HITL replay paths, which still
  # rebuild their legacy format list from the LIVE product rather than from the snapshot
  # persisted above. The data is now there for them to read, but no BDD environment drives
  # execute_approved_media_buy, and the epic's charter refuses an implemented-but-ungraded
  # obligation. Filed as salesagent-zoo82, blocking stage 7.

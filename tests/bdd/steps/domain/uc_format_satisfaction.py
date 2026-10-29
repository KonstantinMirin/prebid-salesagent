"""Steps for BR-UC-FORMAT-SATISFACTION: a format claim against a canonical declaration.

Setup stores a REAL dual-arm ``products`` row through ``ProductFactory`` -- the same factory
every other product fixture uses -- and the refusal is read off the WIRE through
``assert_wire_error``, which is the sanctioned error surface.

THREE TOOLS, because the satisfaction function has gates on three paths and the bead grades
all three. ``create_media_buy`` reuses the shared When from ``uc002_create_media_buy``;
``update_media_buy`` and ``sync_creatives`` get their own Whens here, which dispatch through
the same parametrized transport. The two in-feature envs differ and are routed by tag:
``@format_satisfaction`` takes ``MediaBuyDualEnv`` (create AND update dispatch off one
seeded chain) and ``@format_satisfaction_sync`` takes ``CreativeSyncEnv``.

TWO TABLES, and both of them are DATA rather than behaviour: one maps a declaration name to
the ``format_options`` document the seller stores, the other maps a selector name to the
package members the buyer sends. They are stored documents and request members -- the
faithful shapes -- not a registry of objects a factory should be building:
``core/product-format-declaration.json`` generates a sixteen-branch discriminated union over
``format_kind``, so the column holds a document and the model picks its branch on readback.
Naming each row lets the feature's Examples say which rule it is exercising instead of
carrying JSON a reader has to decode.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlsplit

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps._outcome_helpers import (
    parked_media_buy,
    payload_or_none,
    stored_package_config,
    wire_absent,
    wire_entry,
    wire_envelope_errors,
    wire_field,
)
from tests.factories import PricingOptionFactory, ProductFactory, StoredPlacementFactory
from tests.factories.creative import DEFAULT_CREATIVE_AGENT_URL
from tests.factories.mint import mint

#: The legacy arm every product here also carries, matching ``MediaBuyCreateEnv``'s own
#: seeded default so the deprecated selector route and the rest of the create flow behave
#: exactly as they do for every other create scenario. The canonical arm is what varies.
_LEGACY_ARM: list[dict[str, str]] = [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}]

#: THE SAME legacy entry, SIZED. Every other product fixture in this module leaves the
#: deprecated arm's width and height unset, which is why nothing here could grade the
#: dimension-precedence rule: with no dimensions on the product's catalogue entry, "the
#: buyer's own sizing wins" and "the product's entry fills in" give the SAME answer, so
#: inverting the rule changed nothing (salesagent-49m16, measured: 0 of 8759 nodeids).
#: The conjunction needed a fixture, and this is it.
_LEGACY_ARM_SIZED: list[dict[str, Any]] = [
    {"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250", "width": 300, "height": 250}
]

#: The creative agent's host, which every spelling below is written against.
_AGENT_HOST = urlsplit(DEFAULT_CREATIVE_AGENT_URL).netloc

#: Spellings of the creative agent's url, by the name a scenario gives them. AUTHORED, never
#: computed by ``canonical_agent_url``: asking the canonicalizer under test to build its own
#: inputs would compare the implementation with itself.
#:
#: The first three name the SAME agent under docs/reference/url-canonicalization at the pin,
#: one algorithm step each -- step 2 lowercases the host, step 2 removes "a single trailing
#: [root-label] dot", step 5 applies ``remove_dot_segments`` to the path (``/x/..`` is ``/``,
#: which is also what step 5 gives the empty path). The host case is the CONTROL: the SDK's
#: own comparison already applied that step, so a row that only ever passed proves the
#: scenario can pass. The last names a DIFFERENT agent, because "canonicalization removes
#: only dot segments, never real path segments" -- it is the row a seller that collapsed
#: too much would fail.
_AGENT_URL_SPELLINGS: dict[str, str] = {
    "an upper-cased host": f"https://{_AGENT_HOST.upper()}",
    "a trailing root-label dot": f"https://{_AGENT_HOST}.",
    "a removable dot segment": f"https://{_AGENT_HOST}/x/..",
    "a different path": f"https://{_AGENT_HOST}/other-agent",
}


def _agent_url_spelled(variant: str) -> str:
    """The creative agent's url in the named spelling, refusing a row that respells nothing.

    The spellings are written against a bare-authority url, so the guard checks that is
    still what the factory's default is: an agent url that grew a path would turn
    ``/x/..`` into a different path and the dot-segment row into a different agent.
    """
    assert DEFAULT_CREATIVE_AGENT_URL == f"https://{_AGENT_HOST}", (
        f"the spellings are written for a bare https authority; the default agent is now "
        f"{DEFAULT_CREATIVE_AGENT_URL!r}, so rewrite them against its path"
    )
    spelled = _AGENT_URL_SPELLINGS.get(variant)
    assert spelled is not None, f"no agent url spelling named {variant!r}; have {sorted(_AGENT_URL_SPELLINGS)}"
    assert spelled != DEFAULT_CREATIVE_AGENT_URL, f"{variant!r} does not respell the agent url at all"
    return spelled


#: The option id the product publishes, and the id a publisher-scoped declaration publishes
#: under its own domain. Named once so a selector row and its declaration cannot drift.
_PRODUCT_OPTION_ID = "satisfaction_image_mrec"
_PUBLISHER_DOMAIN = "shorts.streamhaus.example"

#: What the seller STORES, per declaration name. Each is a
#: ``core/product-format-declaration.json`` document.
_DECLARATIONS: dict[str, list[dict[str, Any]]] = {
    # The conformance fixture's own shape: an image kind fixed at 300x250, publishing a
    # product-local option id and asserting the legacy id it projects to. The size cap and
    # the file-format set are the pinned canonical_formats_mrec_display declaration's own,
    # and they are what make ``exact_300x250`` -- which states neither -- grade the pin's
    # inheritance rule rather than a declaration with nothing else to omit.
    "fixed_300x250": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "v1_format_ref": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
            "params": {"width": 300, "height": 250, "max_file_size_kb": 200, "image_formats": ["jpg", "png"]},
        }
    ],
    # The same fixed size with a NUMERIC limit whose name is no bound prefix. A claim silent
    # about it inherits it exactly as it inherits ``max_file_size_kb``: what decides
    # silence is the pin's list of constraints a claim must state, not the constraint's
    # shape.
    "text_limited_300x250": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "params": {"width": 300, "height": 250, "headline_max_chars": 40},
        }
    ],
    # A RANGE constraint, which formats.mdx grades by containment rather than overlap.
    "duration_range": [
        {
            "format_kind": "video_hosted",
            "format_option_id": "satisfaction_video_range",
            "params": {"duration_ms_range": [5000, 60000]},
        }
    ],
    # An EXACT duration, the other half of "Exact dimensions and durations must match"
    # (formats.mdx). ``duration_ms_exact`` is one of the four constraints a claim must state.
    "exact_duration": [
        {
            "format_kind": "video_hosted",
            "format_option_id": "satisfaction_video_exact",
            "params": {"duration_ms_exact": 30000},
        }
    ],
    # BOTH duration keys, so the pin's "Duration precedence is duration_ms_exact >
    # duration_ms_range" (core/product-format-declaration.json) decides which one a selector
    # is held to: the exact value is ``exact_duration``'s, the range ``duration_range``'s.
    "exact_over_range": [
        {
            "format_kind": "video_hosted",
            "format_option_id": "satisfaction_video_exact_in_range",
            "params": {"duration_ms_exact": 30000, "duration_ms_range": [5000, 60000]},
        }
    ],
    # A REQUIRED SLOT, which formats.mdx grades on both the group and the asset type.
    "required_slots": [
        {
            "format_kind": "video_hosted",
            "format_option_id": "satisfaction_video_slots",
            "params": {"slots": [{"asset_group_id": "video_main", "asset_type": "video", "required": True}]},
        }
    ],
    # A PUBLISHER-SCOPED option. The domain's presence is the pin's scope discriminator, so
    # this option and a product-local one sharing the id are different options.
    "publisher_300": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "publisher_domain": _PUBLISHER_DOMAIN,
            "params": {"width": 300, "height": 250},
        }
    ],
    # TWO declarations of ONE kind, which is work item M2's shape and the case
    # ``core/product-format-declaration.json`` names: ``format_option_id`` is "REQUIRED
    # when a product contains multiple declarations with the same format_kind". A bare
    # ``format_kind: image`` selector has to be graded against the declaration its params
    # satisfy, not against whichever is declared first.
    "two_image_options": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "params": {"width": 300, "height": 250},
        },
        {
            "format_kind": "image",
            "format_option_id": "satisfaction_image_leaderboard",
            "params": {"width": 728, "height": 90},
        },
    ],
    # TWO 300x250 image declarations that differ only in the file formats they take. Both
    # NARROW the v1 projection of ``display_300x250`` (canonical-formats.mdx § "Narrows"),
    # so that legacy id selects BOTH, and an option ref naming either one selects a
    # different set (media-buy/package-request.json step (2)).
    "two_mrec_options": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "params": {"width": 300, "height": 250, "image_formats": ["jpg", "png"]},
        },
        {
            "format_kind": "image",
            "format_option_id": "satisfaction_image_mrec_gif",
            "params": {"width": 300, "height": 250, "image_formats": ["gif"]},
        },
    ],
    # A video option fixed at 15 seconds. ``duration_ms_exact`` is the declaration's
    # spelling of one fixed duration; a legacy reference spells it ``duration_ms``.
    "fixed_15s_video": [
        {
            "format_kind": "video_hosted",
            "format_option_id": "satisfaction_video_15s",
            "params": {"duration_ms_exact": 15000},
        }
    ],
    # A 300x250 image declaration with no other constraint, and the same declaration
    # accepting Retina renditions. The pair differs ONLY in ``pixel_ratios``, which
    # formats/canonical/image.json makes the density axis: "Absence means [1]", and with
    # ``[1, 2]`` "a 600x500 intrinsic asset at 2x satisfies a logical 300x250 size".
    "plain_300x250": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "params": {"width": 300, "height": 250},
        }
    ],
    "retina_300x250": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "params": {"width": 300, "height": 250, "pixel_ratios": [1, 2]},
        }
    ],
    # A RENDITION SET: the pinned acme_retina_mrec example's declaration
    # (static/examples/products/canonical/acme_retina_mrec.json), its image_main slot
    # requiring the 1x and 2x renditions and accepting an optional 1.5x.
    # formats/canonical/_base.json ``required_pixel_ratios``: "the manifest slot value MUST be
    # an array containing exactly one matching image rendition for each required ratio".
    # ``retina_300x250`` is the same density axis with no requirement, the control that an
    # acceptance set alone does not demand every rendition.
    "retina_rendition_set": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "params": {
                "width": 300,
                "height": 250,
                "pixel_ratios": [1, 1.5, 2],
                "slots": [
                    {
                        "asset_group_id": "image_main",
                        "asset_type": "image",
                        "required": True,
                        "min": 2,
                        "max": 3,
                        "pixel_ratios": [1, 1.5, 2],
                        "required_pixel_ratios": [1, 2],
                    }
                ],
            },
        }
    ],
    # ``fixed_300x250`` with the ``v1_format_ref`` assertion REMOVED, and nothing else
    # changed. That one difference decides whether the accepted package's deprecated
    # ``format_ids_to_provide`` projection has a source at all, which is the pair the two
    # emission scenarios grade.
    "fixed_300x250_no_ref": [
        {
            "format_kind": "image",
            "format_option_id": _PRODUCT_OPTION_ID,
            "params": {"width": 300, "height": 250, "max_file_size_kb": 200, "image_formats": ["jpg", "png"]},
        }
    ],
}

#: The two declarations ``two_image_options`` publishes, named so a placement can narrow
#: to one of them by restating it inline -- ``core/placement.json``'s ``format_options``
#: items are whole declarations, matched to the product's by ``format_option_id``.
_MREC, _LEADERBOARD = _DECLARATIONS["two_image_options"]


def _manifest(name: str) -> dict[str, Any]:
    """The ``assets`` of a canonical creative, by the name a scenario gives its manifest.

    The third table, and data like the other two: each entry is the asset map a buyer
    sends, keyed by slot id as creative-manifests.mdx § Basic structure keys it. Every entry
    differs from ``image_300x250`` -- the manifest ``fixed_300x250`` accepts -- in ONE member,
    so a refusal row and its accept row differ in the fact under test and nothing else.
    Built per call because a scenario may mutate what it was handed.
    """
    from tests.factories.creative_asset import build_assets, image_spec, manifest_image_spec, text_spec

    mrec = manifest_image_spec("image_main")

    def rendition(width: int, height: int, **fields: object) -> Any:
        """One rendition of the 300x250 in an ``image_main`` array, at *width* x *height* intrinsic."""
        return manifest_image_spec("image_main", width=width, height=height, multiple=True).with_fields(**fields)

    manifests: dict[str, Any] = {
        "image_300x250": lambda: build_assets(mrec),
        "image_728x90": lambda: build_assets(manifest_image_spec("image_main", width=728, height=90)),
        "image_160x600": lambda: build_assets(manifest_image_spec("image_main", width=160, height=600)),
        # 200 KB exactly, the cap ``fixed_300x250`` declares, and 500 KB over it.
        "image_300x250_200kb": lambda: build_assets(mrec.with_fields(file_size_bytes=200 * 1024)),
        "image_300x250_500kb": lambda: build_assets(mrec.with_fields(file_size_bytes=500 * 1024)),
        # The 300x250 image silent about its file size -- the member a capped declaration needs.
        "image_300x250_unsized": lambda: build_assets(image_spec("image_main")),
        # A Retina rendition of the 300x250: 600x500 intrinsic pixels, the ratio stated or
        # left for the seller to infer (core/assets/image-asset.json ``pixel_ratio``).
        "image_600x500_2x": lambda: build_assets(
            manifest_image_spec("image_main", width=600, height=500).with_fields(pixel_ratio=2)
        ),
        "image_600x500": lambda: build_assets(manifest_image_spec("image_main", width=600, height=500)),
        # The 300x250 at 1.5x: a density between the two ``retina_300x250`` accepts.
        "image_450x375_1_5x": lambda: build_assets(
            manifest_image_spec("image_main", width=450, height=375).with_fields(pixel_ratio=1.5)
        ),
        # RENDITION SETS of the 300x250: image_main as an array, one image per density
        # (formats/canonical/_base.json ``required_pixel_ratios``). Each differs from
        # ``image_renditions_1x_2x`` in one rendition: inferred instead of stated ratios, an
        # added optional 1.5x, the 1x dropped, the 1x sent twice.
        "image_renditions_1x_2x": lambda: build_assets(
            rendition(300, 250, pixel_ratio=1), rendition(600, 500, pixel_ratio=2)
        ),
        "image_renditions_1x_2x_inferred": lambda: build_assets(rendition(300, 250), rendition(600, 500)),
        "image_renditions_1x_1_5x_2x": lambda: build_assets(
            rendition(300, 250, pixel_ratio=1), rendition(450, 375, pixel_ratio=1.5), rendition(600, 500, pixel_ratio=2)
        ),
        "image_renditions_2x": lambda: build_assets(rendition(600, 500, pixel_ratio=2)),
        "image_renditions_1x_1x_2x": lambda: build_assets(
            rendition(300, 250, pixel_ratio=1), rendition(300, 250, pixel_ratio=1), rendition(600, 500, pixel_ratio=2)
        ),
        # One of the image_formats ``fixed_300x250`` declares, and one it does not.
        "image_300x250_png": lambda: build_assets(mrec.with_fields(format="png")),
        "image_300x250_gif": lambda: build_assets(mrec.with_fields(format="gif")),
        # The required slot holding the wrong asset type, and the media keyed by no slot.
        "image_main_as_text": lambda: build_assets(text_spec("image_main", content="Trail Pro")),
        "image_unnamed": lambda: build_assets(image_spec("banner")),
    }
    assert name in manifests, f"no manifest named {name!r}; have {sorted(manifests)}"
    return manifests[name]()


def _placement(placement_id: str, mode: str, *accepted: dict[str, Any]) -> dict[str, Any]:
    """One stored ``core/placement.json`` document: a seller-inline placement narrowing inline.

    With no *accepted* declaration the placement states no ``format_options`` at all:
    core/product.json, "An omitted optional layer is unconstrained", so it inherits the
    product's set. An EMPTY list would be a present layer admitting nothing.
    """
    placement: dict[str, Any] = StoredPlacementFactory(placement_id=placement_id, mode=mode)
    if accepted:
        placement["format_options"] = list(accepted)
    return placement


#: The publisher-referenced placement the unresolved-layer rows store: ``core/placement.json``
#: ``kind: publisher_ref``, identified by ``{publisher_domain, placement_id}`` in the
#: publisher's adagents.json, which this seller does not resolve on the buy path.
_PUBLISHER_PLACEMENT_ID = "satisfaction_publisher_slot"


def _publisher_placement(mode: str) -> dict[str, Any]:
    """One stored publisher-referenced placement, in *mode*, narrowing nothing inline."""
    placement: dict[str, Any] = StoredPlacementFactory(
        kind="publisher_ref", placement_id=_PUBLISHER_PLACEMENT_ID, publisher_domain=_PUBLISHER_DOMAIN, mode=mode
    )
    return placement


#: What the seller STORES in ``placements``, per name, for the coverage scenarios. Every
#: row but ``narrowed_inline`` is stored beside ``two_image_options``, and the rows differ
#: only in which option each placement accepts and whether it is included.
_PLACEMENTS: dict[str, list[dict[str, Any]]] = {
    # Two INCLUDED placements that each accept a different option: no single option covers
    # both, so a package selecting one leaves the other placement's inventory uncovered.
    "split": [
        _placement("satisfaction_mrec_slot", "included", _MREC),
        _placement("satisfaction_leaderboard_slot", "included", _LEADERBOARD),
    ],
    # ``split`` with the leaderboard placement TARGETABLE instead of included: a package
    # does not buy it unless it selects it, so the 300x250 option covers what is bought.
    "split_leaderboard_targetable": [
        _placement("satisfaction_mrec_slot", "included", _MREC),
        _placement("satisfaction_leaderboard_slot", "targetable", _LEADERBOARD),
    ],
    # Two included placements that BOTH accept the 300x250 option.
    "shared": [
        _placement("satisfaction_mrec_slot", "included", _MREC),
        _placement("satisfaction_leaderboard_slot", "included", _MREC, _LEADERBOARD),
    ],
    # The ID-LESS inline declarations: no ``format_option_id``, so a placement declaration
    # is matched to the product's by kind and params (``core/product.json``'s third
    # matching rule). ``shared_inline``'s second placement restates 300x250 and accepts the
    # mrec option; ``split_inline``'s states 728x90 and does not.
    "shared_inline": [
        _placement("satisfaction_mrec_slot", "included", _MREC),
        _placement(
            "satisfaction_inline_slot", "included", {"format_kind": "image", "params": {"width": 300, "height": 250}}
        ),
    ],
    "split_inline": [
        _placement("satisfaction_mrec_slot", "included", _MREC),
        _placement(
            "satisfaction_inline_slot", "included", {"format_kind": "image", "params": {"width": 728, "height": 90}}
        ),
    ],
    # Two included placements that narrow NOTHING, so each inherits the product's whole set
    # and any selection the product accepts covers both.
    "unnarrowed": [
        _placement("satisfaction_mrec_slot", "included"),
        _placement("satisfaction_leaderboard_slot", "included"),
    ],
    # Stored beside ``fixed_300x250`` (image 300x250, max_file_size_kb 200, jpg/png): one
    # included placement narrowing ONLY the file-size cap, to 150, with no
    # ``format_option_id``. It states no width or height, so it inherits the option's fixed
    # 300x250 (canonical-formats.mdx § "Narrows": "when v2.params omits a parameter that v1
    # specified, v2 inherits v1's value"); a seller grading the placement's silence about
    # the size as a conflict refuses it.
    "narrowed_file_size": [
        _placement(
            "satisfaction_small_mrec_slot", "included", {"format_kind": "image", "params": {"max_file_size_kb": 150}}
        ),
    ],
    # Stored beside ``duration_range``: an included placement BROADER than the option, its
    # range [1000, 120000] containing the product's [5000, 60000]. The option is the narrower
    # side here, so the match is the reverse direction.
    "widened_inline": [
        _placement(
            "satisfaction_long_video_slot",
            "included",
            {"format_kind": "video_hosted", "params": {"duration_ms_range": [1000, 120000]}},
        ),
    ],
    # Stored beside ``exact_duration`` (``duration_ms_exact`` 30000): an included placement
    # stating only a range that EXCLUDES the option's exact duration. Neither side satisfies
    # the other, so the placement admits nothing the product sells.
    "short_range_inline": [
        _placement(
            "satisfaction_short_video_slot",
            "included",
            {"format_kind": "video_hosted", "params": {"duration_ms_range": [5000, 20000]}},
        ),
    ],
    # Stored beside ``duration_range`` (video_hosted, ``duration_ms_range`` [5000, 60000]):
    # one included placement NARROWING it to [5000, 30000] with no ``format_option_id``. The
    # placement is the narrower side, so it matches; graded the other way round it does not.
    "narrowed_inline": [
        _placement(
            "satisfaction_short_video_slot",
            "included",
            {"format_kind": "video_hosted", "params": {"duration_ms_range": [5000, 30000]}},
        ),
    ],
    # Stored beside ``two_image_options``: the 300x250 seller-inline placement of ``split``
    # plus a PUBLISHER-REFERENCED one. Included, its effective set is the intersection with
    # the publisher's adagents.json catalog, which this seller cannot resolve, so it fails
    # closed (core/product.json: "an unresolved publisher placement or format-option
    # reference MUST fail closed"). Targetable, it is not bought, so it does not constrain.
    "publisher_ref_included": [
        _placement("satisfaction_mrec_slot", "included", _MREC),
        _publisher_placement("included"),
    ],
    "publisher_ref_targetable": [
        _placement("satisfaction_mrec_slot", "included", _MREC),
        _publisher_placement("targetable"),
    ],
}

#: What the buyer SENDS on its package, per selector name. The members are
#: ``media-buy/package-request.json``'s three format selectors.
_SELECTORS: dict[str, dict[str, Any]] = {
    # --- selectors that satisfy ---
    # NO selector at all: "omitting both selects all formats supported by the product"
    # (media-buy/package-request.json).
    "no_selector": {},
    # States the fixed size and nothing else, so every other constraint is inherited.
    "exact_300x250": {"format_kind": "image", "params": {"width": 300, "height": 250}},
    # The pin's create_media_buy_with_direct_canonical_selector: every param the product
    # constrains, restated.
    "complete_300x250": {
        "format_kind": "image",
        "params": {"width": 300, "height": 250, "max_file_size_kb": 200, "image_formats": ["jpg", "png"]},
    },
    "product_option_ref": {"format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}]},
    # ``two_image_options``'s OTHER option, the 728x90, alone.
    "leaderboard_option_ref": {
        "format_option_refs": [{"scope": "product", "format_option_id": _LEADERBOARD["format_option_id"]}]
    },
    # BOTH of ``two_image_options``'s product-local options on one arm: a SET, which is how a
    # buyer covers two included placements that accept one option each.
    "both_option_refs": {
        "format_option_refs": [
            {"scope": "product", "format_option_id": _PRODUCT_OPTION_ID},
            {"scope": "product", "format_option_id": _LEADERBOARD["format_option_id"]},
        ]
    },
    # The legacy arm ALONE, which is what the storyboard's step 10
    # (create_media_buy_with_legacy_mrec_format) sends: format_ids and no format_kind, no
    # params. This row used to carry ``"format_kind": "image"`` as well, which the old
    # merged-claim design needed and which is NOT a shape any storyboard step sends -- and
    # once routes became independent the row correctly started failing, because a bare
    # ``image`` kind beside it is its own under-specified route (step 16). The fixture was
    # the defect, not the refusal: `bare_kind_beside_option_ref` below now grades that
    # two-route shape deliberately, and this one grades step 10 as written.
    "legacy_display_300x250": {"format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}]},
    # A legacy id that reaches the 300x250 declaration ONLY through normalization. Nothing
    # this module's products carry spells it -- their deprecated arm and their
    # ``v1_format_ref`` both say ``display_300x250`` -- while the SDK's registry upgrade
    # takes both ids to display_image 300x250. So it is the one selector on which a seller
    # matching raw (agent_url, id) pairs and one matching the canonical shape disagree, which
    # is the comparison core/product-format-declaration.json forbids ("do not exact-match raw
    # (agent_url, id) pairs once a format_id has been projected"). It is also the id the
    # storyboard's create_media_buy_with_legacy_mrec_format step sends.
    "legacy_display_300x250_image": {
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250_image"}]
    },
    # The storyboard's create_media_buy_with_equivalent_dual_emission: the product-local
    # option ref and ``display_300x250_image`` "normalize to the same declaration", so the
    # two routes agree and the buy is accepted.
    "option_plus_equivalent_legacy_image": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250_image"}],
    },
    # The SAME deprecated id the seller publishes, sized EXPLICITLY by the buyer and
    # differently from the seller's catalogue entry. ``core/format-id.json`` carries
    # width/height on the reference for exactly this parameterized case, and the two halves
    # of the dimension rule give different answers here -- which is what makes the pair of
    # scenarios below able to fail.
    "legacy_sized_728x90": {
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250", "width": 728, "height": 90}]
    },
    "contained_range": {"format_kind": "video_hosted", "params": {"duration_ms_range": [10000, 30000]}},
    # An EXACT duration inside the declared range: "An exact value, such as
    # duration_ms_exact, satisfies a range when that exact value falls inside the accepted
    # interval" (canonical-formats.mdx).
    "exact_duration_in_range": {"format_kind": "video_hosted", "params": {"duration_ms_exact": 30000}},
    "covering_slots": {
        "format_kind": "video_hosted",
        "params": {"slots": [{"asset_group_id": "video_main", "asset_type": "video"}]},
    },
    "matching_publisher_claim": {
        "format_option_refs": [
            {"scope": "publisher", "publisher_domain": _PUBLISHER_DOMAIN, "format_option_id": _PRODUCT_OPTION_ID}
        ]
    },
    # Step 11: two co-present routes that BOTH resolve, to the same declaration. The
    # declaration asserts this exact legacy id in its v1_format_ref, so the legacy route is
    # a lookup rather than a guess.
    "option_plus_projectable_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
    # Step 12: a complete DIRECT canonical selector beside the legacy one, same declaration.
    "direct_plus_legacy": {
        "format_kind": "image",
        "params": {"width": 300, "height": 250},
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
    # --- selectors that do not ---
    # The SECOND of ``two_mrec_options``' declarations by option ref, beside a legacy id that
    # both declarations narrow: the option ref selects one entry, the legacy id both.
    "second_mrec_option_plus_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": "satisfaction_image_mrec_gif"}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
    # ``fixed_15s_video``'s option by ref, beside a legacy video id parameterized at 30
    # seconds. ``video_640x480`` projects to ``video_hosted`` on the pinned registry and the
    # upgrade carries ``duration_ms`` through, so the legacy route states a duration the
    # option contradicts.
    "option_plus_conflicting_duration_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": "satisfaction_video_15s"}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "video_640x480", "duration_ms": 30000}],
    },
    # The storyboard's reject_bare_image_selector_for_fixed_mrec: the right kind, no params.
    "bare_image_kind": {"format_kind": "image"},
    # formats.mdx's fifth rule as an input: the same kind, different dimensions.
    "mismatched_728x90": {"format_kind": "image", "params": {"width": 728, "height": 90}},
    # A kind in the pinned vocabulary that THIS product does not publish -- the closed set.
    "unpublished_video_kind": {"format_kind": "video_hosted", "params": {"width": 300, "height": 250}},
    "unpublished_option_ref": {"format_option_refs": [{"scope": "product", "format_option_id": "no_such_option"}]},
    "overlapping_range": {"format_kind": "video_hosted", "params": {"duration_ms_range": [1000, 30000]}},
    # The UPPER-bound mirror of ``overlapping_range``: the low end is inside the accepted
    # window and the high end is past it, so a seller testing one endpoint passes one row.
    "range_over_upper_bound": {"format_kind": "video_hosted", "params": {"duration_ms_range": [10000, 90000]}},
    # An exact duration that is not the declared exact duration.
    "exact_duration_mismatched": {"format_kind": "video_hosted", "params": {"duration_ms_exact": 15000}},
    # The exact-duration row's refusal half: the same key, a value outside the range.
    "exact_duration_outside_range": {"format_kind": "video_hosted", "params": {"duration_ms_exact": 90000}},
    # A duration range is one of the four constraints a selector MUST state, so silence
    # about it is under-specification, not inheritance.
    "duration_omitted": {"format_kind": "video_hosted"},
    # Inherited constraints still bind a claim that STATES them: a cap above the
    # product's and a file format outside its set each fail.
    "oversized_file_300x250": {
        "format_kind": "image",
        "params": {"width": 300, "height": 250, "max_file_size_kb": 500},
    },
    "unaccepted_image_format_300x250": {
        "format_kind": "image",
        "params": {"width": 300, "height": 250, "image_formats": ["gif"]},
    },
    "headline_over_limit_300x250": {
        "format_kind": "image",
        "params": {"width": 300, "height": 250, "headline_max_chars": 90},
    },
    "slot_missing": {
        "format_kind": "video_hosted",
        "params": {"slots": [{"asset_group_id": "caption", "asset_type": "text"}]},
    },
    # The required group, offered as the WRONG asset type. ``slot_missing`` differs in both
    # halves, so only this row grades "with compatible asset types" on its own.
    "slot_wrong_asset_type": {
        "format_kind": "video_hosted",
        "params": {"slots": [{"asset_group_id": "video_main", "asset_type": "image"}]},
    },
    # The same option id under a DIFFERENT publisher domain: the second half of the
    # exact-publisher-claim rule.
    "wrong_publisher_domain": {
        "format_option_refs": [
            {"scope": "publisher", "publisher_domain": "other.example", "format_option_id": _PRODUCT_OPTION_ID}
        ]
    },
    # The other half: the RIGHT publisher domain with an option id it does not publish.
    "wrong_publisher_option_id": {
        "format_option_refs": [
            {"scope": "publisher", "publisher_domain": _PUBLISHER_DOMAIN, "format_option_id": "no_such_option"}
        ]
    },
    # Step 15, the ORDERING obligation: the option ref RESOLVES and the legacy id does not.
    # The refusal must be UNSUPPORTED_FEATURE naming format_ids -- not an acceptance on the
    # option route, and not CONFLICTING_SELECTORS.
    "option_plus_unprojectable_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "unmapped_legacy_selector_6648"}],
    },
    # The same ordering obligation on the OTHER canonical arm: the option ref fails to
    # resolve and a complete direct selector beside it resolves. format_option_refs'
    # description: sellers "reject unresolved options with UNSUPPORTED_FEATURE and a field
    # path to the failing entry before comparing co-present routes".
    "unpublished_option_plus_exact_300x250": {
        "format_option_refs": [{"scope": "product", "format_option_id": "no_such_option"}],
        "format_kind": "image",
        "params": {"width": 300, "height": 250},
    },
    # Step 17: fixed-size image dimensions are ATOMIC, so width without height is
    # SCHEMA-invalid and belongs in the other error bucket -- INVALID_REQUEST, not
    # UNSUPPORTED_FEATURE. Measured: the pinned PackageRequest refuses it itself
    # ("violates a constraint its schema states outside its properties,
    # media-buy/package-request.json, root conjunct 3, over format_kind, height, params"),
    # so the refusal comes from the request boundary and never reaches the satisfaction
    # function at all. That is the right owner and the scenario below pins it, because the
    # alternative -- satisfaction answering UNSUPPORTED_FEATURE for a schema violation --
    # is exactly the bucket confusion the step exists to prevent.
    "width_without_height": {"format_kind": "image", "params": {"width": 300}},
    # A SINGLE legacy route that normalizes and then selects nothing. Measured on the pinned
    # wheel: ``display_728x90`` upgrades to ``display_image`` + 728x90 and
    # ``canonical_kind_for`` answers ``image``, so against a product fixing 300x250 the
    # route resolves and satisfies no declaration -- the pin's "a single resolved route that
    # does not satisfy the product". The SAME id beside a resolving option ref is the
    # conflict row below, and the two differ in nothing else.
    "legacy_display_728x90": {"format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_728x90"}]},
    # Two legacy references that normalize to the KIND alone. The registry maps both to
    # ``image`` by glob, while neither carries or projects a size: ``display_image`` is the
    # unparameterized template, and the SDK upgrades ``display_300x250`` to 300x250 only for
    # the reference agent, so at another agent it projects nothing. Against a product fixing
    # 300x250 each is "a broad request with no dimensions", which
    # core/product-format-declaration.json says "does not satisfy a fixed-size ... product".
    # Both were accepted by satisfaction and refused only by a raw-key gate that ran after
    # it -- VALIDATION_ERROR, and for the wrong reason (salesagent-ol033.20.26).
    "legacy_unsized_template": {"format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_image"}]},
    "foreign_agent_display_300x250": {
        "format_ids": [{"agent_url": "https://another-creative-agent.example", "id": "display_300x250"}]
    },
    # The creative agent's host with TWO trailing dots. docs/reference/url-canonicalization,
    # step 2: "More than one trailing dot creates an empty DNS label rather than a root-label
    # spelling and MUST be rejected", and comparers MUST reject a malformed authority. The
    # wire accepts it (``format: uri``), so the refusal is the seller's: it names no agent and
    # so no format. It used to raise out of the comparison and answer INTERNAL_ERROR.
    "malformed_agent_display_300x250": {
        "format_ids": [{"agent_url": f"https://{_AGENT_HOST}..", "id": "display_300x250"}]
    },
    # M2's refusal half: a selector satisfying NEITHER image declaration ``two_image_options``
    # publishes, so the two M2 accept rows cannot be passed by accepting every image.
    "mismatched_160x600": {"format_kind": "image", "params": {"width": 160, "height": 600}},
    # --- co-present routes that select DIFFERENT declarations ---
    # The storyboard's reject_conflicting_dual_emission: the option ref selects the 300x250
    # declaration, and the registry-backed legacy id normalizes to a 728x90 image the
    # product does not publish. Both routes resolve, so the refusal is the EQUIVALENCE one.
    "option_plus_conflicting_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_728x90"}],
    },
    # The storyboard's reject_conflicting_canonical_routes: two CANONICAL routes, and the
    # direct one describes a 728x90 image. "Canonical precedence must not hide a conflict
    # between two resolvable canonical routes."
    "option_plus_conflicting_direct": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_kind": "image",
        "params": {"width": 728, "height": 90},
    },
    # The same shape with the params OMITTED rather than wrong: the kind route selects no
    # declaration (silence does not satisfy an exact dimension) while the option ref selects
    # one, so the selected option sets differ. Graded UNSUPPORTED_FEATURE until the
    # equivalence comparison existed; see salesagent-iql3e for why the pin says otherwise.
    "bare_kind_beside_option_ref": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_kind": "image",
    },
    # The broad legacy template beside the option ref. display_image states no size, so --
    # like a bare ``format_kind: image`` -- it selects no fixed-size declaration (package-
    # request.json format_kind: broad image "does not satisfy a fixed-size product
    # declaration"), while the option ref selects the 300x250: the sets differ.
    "option_plus_broad_legacy": {
        "format_option_refs": [{"scope": "product", "format_option_id": _PRODUCT_OPTION_ID}],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_image"}],
    },
    # ``both_option_refs`` beside display_300x250: the option arm selects BOTH of
    # ``two_image_options``' entries, the legacy route only the 300x250 one its projection
    # narrows to. One option SET against another, so the two refs are not a conflict between
    # themselves and the arm as a whole is.
    "both_option_refs_plus_legacy": {
        "format_option_refs": [
            {"scope": "product", "format_option_id": _PRODUCT_OPTION_ID},
            {"scope": "product", "format_option_id": _LEADERBOARD["format_option_id"]},
        ],
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
    # --- co-present routes on a product publishing ONLY the deprecated arm ---
    # A direct route of another size beside the legacy id the product carries: against the
    # SDK's projection of that id (image 300x250) the direct route selects nothing.
    "kind_728x90_plus_legacy": {
        "format_kind": "image",
        "params": {"width": 728, "height": 90},
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
    # A direct route of another SHAPE: video beside an image legacy id.
    "video_kind_plus_legacy": {
        "format_kind": "video_hosted",
        "params": {"duration_ms_exact": 15000},
        "format_ids": [{"agent_url": DEFAULT_CREATIVE_AGENT_URL, "id": "display_300x250"}],
    },
}


# ── Given steps ─────────────────────────────────────────────────────


@given("a tenant is configured for media buy creation")
def given_tenant_for_create(ctx: dict) -> None:
    """Assert the route already seeded a tenant and buyer, rather than seeding a second one.

    Both routes this feature uses seed before any Given runs -- the media-buy one seeds the
    whole create chain, the sync one a tenant and principal -- so the Background's job is to
    say the precondition exists and check it, not to establish it. A Background that seeded
    would create a SECOND tenant and leave the request pointing at whichever ran last, and
    ``setup_default_data`` re-creating a missing principal is how a later Given comes to
    undo an earlier one.

    The tenant is what BOTH routes have in common and so is what this asserts; the product
    is deliberately not checked, because the sync scenarios declare their own.
    """
    assert ctx.get("tenant") is not None, (
        "a format-satisfaction route must seed a tenant and principal before the Background runs; "
        "check the ENV_ROUTES rows claiming @format_satisfaction / @format_satisfaction_sync"
    )


def _store_declaring_product(
    ctx: dict, declaration: str, *, with_legacy_arm: bool, placements: str | None = None
) -> None:
    """Store one product carrying *declaration*, with or without the deprecated arm.

    *placements* names a :data:`_PLACEMENTS` row stored in the product's ``placements``
    column; ``None`` stores none, which is every scenario but the coverage ones.

    ``with_legacy_arm=False`` stores a CANONICAL-ONLY product: ``format_ids`` NULL, which
    migration 08cd415b3d91 made representable. The product id carries the shape so two
    scenarios naming the same declaration cannot collide on one row.
    """
    product_id = f"satisfaction_{declaration}" if with_legacy_arm else f"satisfaction_canonical_{declaration}"
    _store_product(
        ctx,
        f"{product_id}_{placements}" if placements else product_id,
        format_ids=list(_LEGACY_ARM) if with_legacy_arm else None,
        format_options=_DECLARATIONS[declaration],
        placements=_PLACEMENTS[placements] if placements else None,
    )


def _store_product(
    ctx: dict,
    product_id: str,
    *,
    format_ids: list[dict[str, Any]] | None,
    format_options: list[dict[str, Any]] | None,
    placements: list[dict[str, Any]] | None = None,
) -> None:
    """Store one product with the given arms and point the buyer's package at it.

    The product becomes ``ctx["default_product"]``, which is what the shared create-request
    builder points the package at -- so the buyer's request names THIS product without this
    module duplicating the request literal.
    """
    from tests.bdd.steps.generic.given_media_buy import _ensure_request_defaults

    product = ProductFactory(
        tenant=ctx["tenant"],
        product_id=product_id,
        delivery_type="non_guaranteed",
        format_ids=format_ids,
        format_options=format_options,
        placements=placements,
        property_tags=["all_inventory"],
    )
    ctx["default_pricing_option"] = PricingOptionFactory(
        product=product, pricing_model="cpm", currency="USD", is_fixed=True
    )
    ctx["default_product"] = product
    # Built AFTER the product exists so the package names it; the builder reads
    # ctx["default_product"] and is guarded against re-running.
    ctx.pop("request_kwargs", None)
    _ensure_request_defaults(ctx)


@given(parsers.parse('the seller declares a canonical format option "{declaration}"'))
def given_declaration(ctx: dict, declaration: str) -> None:
    """Store a DUAL-ARM product -- the named canonical declarations plus the legacy arm.

    Dual-arm is what the satisfaction scenarios want: the rule each one names is about the
    SELECTOR, and a product carrying both arms leaves every selector route reachable, so a
    refusal is attributable to the rule rather than to an arm the product never declared.
    """
    _store_declaring_product(ctx, declaration, with_legacy_arm=True)


@given(parsers.parse('the seller declares canonical format options "{declaration}" across placements "{placements}"'))
def given_declaration_across_placements(ctx: dict, declaration: str, placements: str) -> None:
    """Store the dual-arm product of :func:`given_declaration` with stored placements.

    The placements are what the coverage rule reads: each is a stored ``core/placement.json``
    document, and an included one may narrow the product's declarations inline.
    """
    _store_declaring_product(ctx, declaration, with_legacy_arm=True, placements=placements)


@given(parsers.parse("the seller publishes only a deprecated format sized {width:d}x{height:d}"))
def given_legacy_only_sized_product(ctx: dict, width: int, height: int) -> None:
    """Store a LEGACY-ONLY product whose deprecated entry CARRIES its dimensions.

    The fixture the dimension-precedence rule needs, and it is deliberately neither of this
    module's other two shapes. Dual-arm will not do: a legacy selector normalizes through
    ``upgrade_legacy_format_id``, so a buyer sizing ``display_300x250`` at 728x90 against a
    product whose declaration FIXES 300x250 is refused by satisfaction before any dimension
    is resolved -- correctly, and it would grade the refusal rather than the precedence.
    With no ``format_options`` the product narrows no canonical set, so the selector is
    accepted and the create path's dimension resolution is what decides what the ad server
    is asked to traffic.

    Legacy-only is spec-legal for the 3.x window -- ``core/product.json``: "Products MUST
    carry ``format_ids``, ``format_options``, or both during the 3.x migration window" --
    and is the population this rule still serves.
    """
    _store_legacy_only_sized_product(ctx, width, height, agent_url=DEFAULT_CREATIVE_AGENT_URL)


@given(
    parsers.parse(
        "the seller publishes only a deprecated format sized {width:d}x{height:d} "
        "at the creative agent's url with {variant}"
    )
)
def given_legacy_only_sized_product_spelled(ctx: dict, width: int, height: int, variant: str) -> None:
    """The same legacy-only product, its entry naming the creative agent in another spelling.

    The create-path half of ``core/format-id.json``'s MUST: "Callers comparing two
    format-id values MUST canonicalize agent_url per the AdCP URL canonicalization rules
    before treating two formats as the same." Only the PRODUCT's spelling moves; the buyer's
    selector names the agent as the factory does, so the two references disagree in bytes
    and in nothing the algorithm keeps.
    """
    _store_legacy_only_sized_product(ctx, width, height, agent_url=_agent_url_spelled(variant))


def _store_legacy_only_sized_product(ctx: dict, width: int, height: int, *, agent_url: str) -> None:
    """Store a legacy-only product whose one deprecated entry is sized, at *agent_url*."""
    entry = dict(_LEGACY_ARM_SIZED[0]) | {"width": width, "height": height, "agent_url": agent_url}
    _store_product(ctx, f"satisfaction_legacy_{width}x{height}", format_ids=[entry], format_options=None)


@given("the seller publishes only the deprecated format_ids")
def given_legacy_only_product(ctx: dict) -> None:
    """Store a LEGACY-ONLY product: this module's deprecated arm, and no format_options.

    Still legal at the pin -- ``core/product.json``: "Products MUST carry ``format_ids``,
    ``format_options``, or both during the 3.x migration window" -- and the shape on which
    a canonical route has no ``format_options[]`` entry to resolve against.
    """
    _store_product(ctx, "satisfaction_legacy_only", format_ids=list(_LEGACY_ARM), format_options=None)


@given(parsers.parse('the seller declares a canonical format option "{declaration}" and no format_ids'))
def given_canonical_only_declaration(ctx: dict, declaration: str) -> None:
    """Store a CANONICAL-ONLY product -- the declaration, and no deprecated arm at all.

    The shape AdCP 3.2 tells new products to author, and the one stage-1 guarantee nothing
    graded: that such a product is PURCHASABLE and not merely discoverable. Every other
    product fixture on the create path carries the deprecated arm, so
    discoverable-but-unpurchasable had no detector.
    """
    _store_declaring_product(ctx, declaration, with_legacy_arm=False)


@given(
    parsers.parse(
        'the buyer assigns a creative identified by canonical kind "{kind}" with its media asset keyed "{asset_key}"'
    )
)
def given_canonical_creative(ctx: dict, kind: str, asset_key: str) -> None:
    """Seed a creative carrying a CANONICAL identity and assign it to the package.

    ``canonical_kind`` rather than ``format``, which is the whole point: a creative seeded
    this way asserts NO legacy reference, so the four gates' deprecated comparison has
    nothing to compare and the canonical closed-set step is the only thing that can refuse
    it. The factory derives the stored columns through the same production mapping the sync
    path uses, so this row and a synced row cannot differ in shape.

    THE ASSET KEY IS A SCENARIO PARAMETER and not a fixture decision, because it is the one
    axis two of the scenarios below vary. A canonical creative has no format spec to ask for
    an ``asset_id`` -- it asserts no legacy reference -- so the key under which its media
    asset is stored is the whole of what the create path's pre-adapter gate has to go on,
    and whether the gate can read it is the obligation. ``image_main`` is what
    ``formats/canonical/image.json`` declares (its ``slots`` default), and a key the
    declaration does not name must still be refused; the feature states both.

    This key used to be hardcoded ``banner_image``, a member of this seller's own
    ``MEDIA_ASSET_FALLBACK_IDS`` guess-list, because nothing read the declaration and the
    allowlist was the only path a canonical creative had -- so the scenarios graded the
    closed set and never the asset reader. That was salesagent-ol033.16; the workaround goes
    with it.
    """
    creative = _seed_canonical_creative(ctx, kind=kind, asset_key=asset_key)
    ctx["request_kwargs"]["packages"][0]["creative_ids"] = [creative.creative_id]


def _seed_canonical_creative(
    ctx: dict,
    *,
    kind: str,
    asset_key: str = "image_main",
    assets: dict[str, Any] | None = None,
    status: str = "approved",
    **row: Any,
) -> Any:
    """One creative carrying the named CANONICAL kind, committed. Returns the row.

    Approved unless the caller names another review ``status``; ``row`` carries any other
    column a caller pins (a ``creative_id`` a later sync must address). ``assets`` replaces
    the one 300x250 image keyed ``asset_key`` with a whole named manifest (:func:`_manifest`).

    The default asset key is ``image_main``, which ``formats/canonical/image.json`` declares
    as the ``image`` kind's required image slot -- so a caller that does not care about the
    key gets the one the pin names rather than a convention this seller invented. The image
    states its file size (``manifest_image_spec``), because a declaration capping it is owed
    the member.

    CANONICAL ONLY. This grew a ``format_id`` arm for a legacy caller and then lost that
    caller, and the dead parameter is removed rather than left: it built a creative carrying
    a legacy reference WITHOUT routing it through ``resolvable_format_ref``, the door that
    refuses a reference the pinned capture does not serve. A bypass sitting beside a new
    door is how the door gets routed around later by someone who finds the simpler
    parameter -- and this change exists precisely because an unserved id went unnoticed for
    months. A legacy-arm caller goes through ``given_sync_legacy_creative``, which uses the
    door.
    """
    from tests.factories.creative import CreativeFactory
    from tests.factories.creative_asset import build_assets, manifest_image_spec

    arm: dict[str, Any] = {"canonical_kind": kind}
    creative = CreativeFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        status=status,
        data={"assets": assets if assets is not None else build_assets(manifest_image_spec(asset_key))},
        **arm,
        **row,
    )
    ctx["env"]._commit_factory_data()
    ctx["manifest_creative_id"] = creative.creative_id
    return creative


@given(parsers.parse('the buyer assigns a canonical "{kind}" creative carrying the "{manifest}" manifest'))
def given_canonical_creative_with_manifest(ctx: dict, kind: str, manifest: str) -> None:
    """A stored canonical creative with the named manifest, assigned to the package.

    The create path grades the STORED creative, so it is seeded as stored -- the same
    production identity mapping a sync writes -- and only its assets vary between rows.
    """
    creative = _seed_canonical_creative(ctx, kind=kind, assets=_manifest(manifest))
    ctx["request_kwargs"]["packages"][0]["creative_ids"] = [creative.creative_id]


@given(parsers.parse('a canonical "{kind}" creative carrying the "{manifest}" manifest exists'))
def given_canonical_creative_with_manifest_exists(ctx: dict, kind: str, manifest: str) -> None:
    """The update path's creative: stored with the named manifest, assigned by the When."""
    ctx["creative_to_assign"] = _seed_canonical_creative(ctx, kind=kind, assets=_manifest(manifest))


# ── UPDATE path ─────────────────────────────────────────────────────


@given("the buyer already holds a media buy for that product")
def given_existing_media_buy(ctx: dict) -> None:
    """Seed a committed media buy with one package naming the canonical product.

    The package's ``package_config.product_id`` is what the update gate resolves the product
    from, so the buy has to name THIS product rather than the env's default one -- the gate
    would otherwise grade the selector against a product the scenario never declared.
    """
    from datetime import UTC, datetime, timedelta

    from tests.factories import MediaBuyFactory, MediaPackageFactory

    media_buy = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        status="pending_approval",
        currency="USD",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(days=30),
    )
    package = MediaPackageFactory(
        media_buy=media_buy,
        package_config={"product_id": ctx["default_product"].product_id, "budget": 5000.0},
    )
    ctx["env"]._commit_factory_data()
    ctx["existing_media_buy"] = media_buy
    ctx["existing_package"] = package


@given(parsers.parse('a creative identified by canonical kind "{kind}" exists'))
def given_creative_exists(ctx: dict, kind: str) -> None:
    """Seed the creative the update will assign, without assigning it yet."""
    ctx["creative_to_assign"] = _seed_canonical_creative(ctx, kind=kind)


@when("the Buyer Agent assigns that creative through update_media_buy")
def when_update_assigns_creative(ctx: dict) -> None:
    """Dispatch a real update_media_buy carrying the creative on its package.

    A RAW flat body: ``media_buy_id`` is what ``MediaBuyDualEnv._is_update_request`` routes
    on, and dispatching the flat kwargs sends them through the real route and production
    Pydantic rather than constructing the request in the test process -- the same reason the
    create side dispatches raw.
    """
    _dispatch_package_update(ctx, creative_ids=[ctx["creative_to_assign"].creative_id])


@when("the Buyer Agent uploads the package's creatives through update_media_buy")
def when_update_uploads_creatives(ctx: dict) -> None:
    """Dispatch a real update_media_buy whose package carries the creatives inline.

    The creatives are the ones a Given put on the package the buyer is building
    (``ctx["request_kwargs"]["packages"][0]["creatives"]``), so the create and update
    scenarios upload the same bytes through one Given.
    """
    _dispatch_package_update(ctx, creatives=ctx["request_kwargs"]["packages"][0]["creatives"])


def _dispatch_package_update(ctx: dict, **package_members: Any) -> None:
    """One update_media_buy against the held buy's package, carrying *package_members*.

    A RAW flat body: ``media_buy_id`` is what ``MediaBuyDualEnv._is_update_request`` routes
    on, and the transport validates, so a malformed member reaches production's boundary.
    """
    from tests.bdd.steps.generic._dispatch import dispatch_request

    dispatch_request(
        ctx,
        media_buy_id=ctx["existing_media_buy"].media_buy_id,
        account={"account_id": ctx["env"].setup_default_account().account_id},
        idempotency_key=mint(f"satisfaction-update-{uuid.uuid4().hex}"),
        packages=[{"package_id": ctx["existing_package"].package_id, **package_members}],
    )


# ── ASSIGNMENT path (sync_creatives) ────────────────────────────────


@given("a packaged product declaring a canonical image option fixed at 300x250")
def given_sync_canonical_product(ctx: dict) -> None:
    """Seed tenant + principal + a DUAL-ARM product + a media buy and package to assign to.

    Its own seeding rather than the create chain's: ``CreativeSyncEnv`` is a different env
    with a different default seed, and the assignment gate resolves the product from
    ``package_config.product_id``, so the package has to name the product this scenario
    declared.
    """
    _seed_sync_chain(ctx, format_options=_DECLARATIONS["fixed_300x250"], format_ids=list(_LEGACY_ARM))


@given(parsers.parse('a packaged product declaring canonical format options "{declaration}"'))
def given_sync_declaring_product(ctx: dict, declaration: str) -> None:
    """The sync chain over a dual-arm product carrying the named :data:`_DECLARATIONS` row.

    The named sibling of the fixed-300x250 Given above, for the rows that need a product
    publishing SEVERAL declarations of one kind -- the case ``format_option_ref`` exists for.
    """
    _seed_sync_chain(ctx, format_options=_DECLARATIONS[declaration], format_ids=list(_LEGACY_ARM))


@given("a packaged product declaring only the deprecated format_ids")
def given_sync_legacy_product(ctx: dict) -> None:
    """The LEGACY-arm control for the lenient asymmetry: no ``format_options`` at all.

    Which lane the satisfaction function takes is decided by what the PRODUCT declares, so
    this is the one knob that moves the sibling scenario from the canonical lane to the
    deprecated one -- same tool, same mode, same condition.
    """
    _seed_sync_chain(ctx, format_options=None, format_ids=list(_LEGACY_ARM))


@given(parsers.parse("a packaged product selling only a deprecated format sized {width:d}x{height:d}"))
def given_sync_legacy_sized_product(ctx: dict, width: int, height: int) -> None:
    """A legacy-only product whose deprecated entry names a TEMPLATE id and SIZES it.

    The fixture the acceptance rule needs, and the module had no shape that could express it:
    ``_LEGACY_ARM`` leaves the arm's dimensions unset, so a product restricting to 300x250 and
    a product restricting to nothing produce the same accepted set and no assertion can tell
    a conforming creative from a mis-sized one (salesagent-4764o).

    A TEMPLATE id carrying parameters, not a name-encoded one, and that is measured rather
    than stylistic: ``upgrade_legacy_format_id`` rewrites a reference's parameters from its
    NAME, so ``display_300x250_image`` sized 728x90 upgrades to ``display_image`` at 300x250
    and compares equal to the product -- a name-encoded id cannot express a mis-sized claim at
    all. ``core/format-id.json`` is explicit that the two spellings are different things: an
    id "used alone, references a template format. When combined with dimension/duration
    fields, creates a parameterized format ID for a specific variant."

    LEGACY-ONLY because the lane is chosen by what the PRODUCT declares. With a canonical arm
    present the claim would be graded by ``_canonical_lane``, which projects, and the row
    would grade the projection instead of the deprecated arm's own comparison.
    """
    _seed_legacy_sized_sync_chain(ctx, width, height, agent_url=DEFAULT_CREATIVE_AGENT_URL)


@given(
    parsers.parse(
        "a packaged product selling only a deprecated format sized {width:d}x{height:d} "
        "at the creative agent's url with {variant}"
    )
)
def given_sync_legacy_sized_product_spelled(ctx: dict, width: int, height: int, variant: str) -> None:
    """The same legacy-only product, its entry naming the creative agent in another spelling.

    The assignment path's half of ``core/format-id.json``'s MUST. It is the one comparison the
    deprecated lane makes that a respelling reaches: the creative's claim is resolved against
    the agent's catalog under its own spelling, and only the PRODUCT's entry is respelled, so
    nothing upstream of the satisfaction verdict sees the second spelling at all.
    """
    _seed_legacy_sized_sync_chain(ctx, width, height, agent_url=_agent_url_spelled(variant))


def _seed_legacy_sized_sync_chain(ctx: dict, width: int, height: int, *, agent_url: str) -> None:
    """The sync chain over a legacy-only product selling one sized template at *agent_url*."""
    _seed_sync_chain(
        ctx,
        format_options=None,
        format_ids=[{"agent_url": agent_url, "id": "display_image", "width": width, "height": height}],
    )


@given(
    parsers.parse(
        "a packaged product selling only a deprecated format sized {width:d}x{height:d} at {pixel_ratio:d}x density"
    )
)
def given_sync_legacy_density_product(ctx: dict, width: int, height: int, pixel_ratio: int) -> None:
    """The same legacy-only product, additionally fixing the asset DENSITY it requires.

    ``pixel_ratio`` is the fourth parameterizing field and the one the SDK's comparison does
    not read, so this row is what makes ``_pixel_ratio_unsatisfied`` falsifiable. Without it
    that clause is in exactly the position the dimensions were in before this change: correct
    per the pin, and unfalsifiable by the suite -- removing it reddened nothing (measured).

    The pin requires the match and requires the dimensions alongside it:
    ``core/format-id.json`` calls the field "**Required** intrinsic-pixel density for a
    parameterized visual format" and says it "Requires ``width`` and ``height``", so a
    density is seeded WITH a size rather than instead of one.
    """
    _seed_sync_chain(
        ctx,
        format_options=None,
        format_ids=[
            {
                "agent_url": DEFAULT_CREATIVE_AGENT_URL,
                "id": "display_image",
                "width": width,
                "height": height,
                "pixel_ratio": pixel_ratio,
            }
        ],
    )


def _seed_sync_chain(
    ctx: dict, *, format_options: list[dict[str, Any]] | None, format_ids: list[dict[str, str]]
) -> None:
    """The product, media buy and package a sync_creatives assignment needs.

    The tenant and principal are the ROUTE's (``_seed_default_tenant_and_principal``), not
    re-seeded here: ``setup_default_data`` re-creates a missing principal, and calling it
    twice is how a Given comes to undo what the route already established.
    """
    from tests.factories import MediaBuyFactory, MediaPackageFactory

    tenant, principal = ctx["tenant"], ctx["principal"]
    product = ProductFactory(
        tenant=tenant,
        product_id="satisfaction_sync_product",
        delivery_type="non_guaranteed",
        format_ids=format_ids,
        format_options=format_options,
        property_tags=["all_inventory"],
    )
    PricingOptionFactory(product=product, pricing_model="cpm", currency="USD", is_fixed=True)
    media_buy = MediaBuyFactory(tenant=tenant, principal=principal)
    package = MediaPackageFactory(media_buy=media_buy, package_config={"product_id": product.product_id})
    ctx["env"]._commit_factory_data()
    ctx["default_product"] = product
    ctx["existing_package"] = package


#: The creative the sync scenarios send. One id, because the assignment is about this one
#: creative and the result is read off ``creatives[0]``.
_SYNC_CREATIVE_ID = "satisfaction_sync_creative"


@given(parsers.parse('the buyer syncs a creative identified by canonical kind "{kind}"'))
def given_sync_canonical_creative(ctx: dict, kind: str) -> None:
    """The creative payload the sync will carry, identified by its CANONICAL kind.

    A PAYLOAD rather than a pre-seeded row, because ``SyncCreativesRequest.creatives`` is
    required with ``min_length=1`` -- a buyer cannot assign without syncing, so sync-and-
    assign in one call IS the real flow and seeding a row then sending an empty list is a
    shape the pin refuses (measured: ``List should have at least 1 item``).
    """
    _sync_canonical_claim(ctx, kind)


@given(
    parsers.parse(
        'the buyer syncs a creative whose format_option_ref names product option "{option}" of canonical kind "{kind}"'
    )
)
def given_sync_canonical_creative_with_option(ctx: dict, option: str, kind: str) -> None:
    """The canonical claim NARROWED to one product option, as creative-manifests.mdx
    § Exact option routing spells it: ``format_kind`` plus a product-scoped
    ``format_option_ref`` ``{scope: "product", format_option_id}``.

    Worded to not end on the kind's quoted value, so the bare-kind Given above (whose
    ``"{kind}"`` would otherwise match across the rest of this sentence) cannot bind it.
    """
    _sync_canonical_claim(ctx, kind, format_option_ref={"scope": "product", "format_option_id": option})


@given(parsers.parse('the buyer syncs a canonical "{kind}" creative carrying the "{manifest}" manifest'))
def given_sync_canonical_creative_with_manifest(ctx: dict, kind: str, manifest: str) -> None:
    """The canonical claim on the wire with the named manifest (:func:`_manifest`)."""
    _sync_canonical_claim(ctx, kind, assets=_manifest(manifest))


@given(
    parsers.parse(
        'the buyer syncs a canonical "{kind}" creative carrying the "{manifest}" manifest '
        'and naming product option "{option}"'
    )
)
def given_sync_canonical_creative_with_manifest_and_option(ctx: dict, kind: str, manifest: str, option: str) -> None:
    """The same claim routed to one product option by ``format_option_ref``.

    creative-manifests.mdx § Exact option routing: "When a product accepts multiple
    declarations of the same kind ... add format_option_ref."
    """
    _sync_canonical_claim(
        ctx,
        kind,
        assets=_manifest(manifest),
        format_option_ref={"scope": "product", "format_option_id": option},
    )


def _sync_canonical_claim(ctx: dict, kind: str, **members: Any) -> None:
    """ONE canonical claim on the wire: ``format_kind`` and no ``format_id`` key at all.

    ``format_id=OMIT`` is what makes it canonical: ``core/creative-asset.json`` is a oneOf
    on the identifier, so the legacy arm has to be ABSENT rather than null -- the pin
    reports absent and null identically, and the factory's ``OMIT`` is the only way a call
    site can say which it meant.

    The assets fill the kind's required slots (``canonical_assets``): the seller grades a
    canonical manifest against the declaration it selects, or its kind when it selects none
    (creative-manifests.mdx § Validation), so the factory's default ``image``-keyed asset
    would be a manifest missing ``image_main``. *members* may replace them.
    """
    from tests.factories.creative_asset import canonical_assets
    from tests.factories.request import OMIT, CreativeAssetRequestFactory

    ctx["creatives"] = [
        CreativeAssetRequestFactory.payload(
            creative_id=_SYNC_CREATIVE_ID,
            format_id=OMIT,
            format_kind=kind,
            **{"assets": canonical_assets(kind), **members},
        )
    ]
    ctx["manifest_creative_id"] = _SYNC_CREATIVE_ID


def _mixed_identity_creative(format_id: str, kind: str) -> dict[str, Any]:
    """A creative naming BOTH identifiers, declared as the malformation it is.

    creative-manifests.mdx § Deprecated compatibility branch: a 3.2 implementation "must
    not ... mix format_id and format_kind in one manifest", and core/creative-asset.json's
    root oneOf refuses it (each arm carries a ``not`` on the other's identifier). The
    ``format_id`` is one the agent serves (``resolvable_format_ref``) and the kind is in the
    vocabulary, so each half is valid alone and only the MIX is wrong.
    """
    from src.core.errors.codes import ErrorCode
    from tests.factories.format import resolvable_format_ref
    from tests.factories.malformed import malformed
    from tests.factories.request import CreativeAssetRequestFactory

    return malformed(
        "semantic",
        "both format_id and format_kind present, each valid on its own; core/creative-asset.json's "
        "root oneOf admits exactly one, so the pin refuses the item with [type=oneOf].",
        CreativeAssetRequestFactory.payload(
            creative_id=_SYNC_CREATIVE_ID, format_id=resolvable_format_ref(format_id), format_kind=kind
        ),
        obligation=ErrorCode.INVALID_REQUEST,
    )


@given(
    parsers.parse('the buyer syncs a creative identified by both format_id "{format_id}" and canonical kind "{kind}"')
)
def given_sync_mixed_identity_creative(ctx: dict, format_id: str, kind: str) -> None:
    """The sync item carries both identifiers (see ``_mixed_identity_creative``)."""
    ctx["creatives"] = [_mixed_identity_creative(format_id, kind)]


@given(parsers.parse('the buyer syncs a creative identified by canonical kind "{kind}" beside a null format_id'))
def given_sync_kind_beside_null_format_id(ctx: dict, kind: str) -> None:
    """The canonical claim with the legacy key PRESENT and null, as a dict on the wire.

    A dict and not a model, because a model dumped for the wire drops the null (an unset
    optional member is absent on a buyer's wire) and would send the legal canonical item.
    """
    from src.core.errors.codes import ErrorCode
    from tests.factories.malformed import malformed
    from tests.factories.request import CreativeAssetRequestFactory

    ctx["creatives"] = [
        malformed(
            "explicit_none",
            "format_kind beside format_id: null. core/creative-asset.json's root oneOf arms each pair a "
            "required with a not-required, and required counts a present key whatever its value, so the "
            "item names both identifiers and matches neither arm.",
            CreativeAssetRequestFactory.payload(creative_id=_SYNC_CREATIVE_ID, format_id=None, format_kind=kind),
            obligation=ErrorCode.INVALID_REQUEST,
        )
    ]


@given(
    parsers.parse(
        'the buyer\'s package uploads a creative identified by both format_id "{format_id}" and canonical kind "{kind}"'
    )
)
def given_package_mixed_identity_creative(ctx: dict, format_id: str, kind: str) -> None:
    """The package the buyer is building carries the mixed creative inline.

    ``packages[].creatives[]`` is core/creative-asset.json on both create_media_buy
    (media-buy/package-request.json) and update_media_buy (media-buy/package-update.json),
    so the create When sends this package as built and the update When sends its creatives.
    """
    ctx["request_kwargs"]["packages"][0]["creatives"] = [_mixed_identity_creative(format_id, kind)]


@given(parsers.parse('a creative identified by canonical kind "{kind}" is already in the library as "{status}"'))
def given_canonical_creative_in_library(ctx: dict, kind: str, status: str) -> None:
    """The library row a later sync of the SAME creative_id updates, in review *status*.

    Same id as the sync Givens' item, and the route's principal, so the sync takes the
    update path (``creative_repo.get_by_id(creative_id, principal_id)``).
    """
    _seed_canonical_creative(ctx, kind=kind, status=status, creative_id=_SYNC_CREATIVE_ID)


def _sync_legacy_claim(ctx: dict, format_id: str, **parameters: int) -> None:
    """ONE legacy claim on the wire, against the catalog that answers it.

    The three Givens below differ only in which of the reference's own parameterizing
    fields the scenario names, so the payload and the catalog are set up here once.

    Built through ``resolvable_format_ref`` rather than from the scenario's string
    directly, because a CREATIVE's claim is resolved over the wire: the id has to be one
    the creative agent actually serves, or the sync is refused REFERENCE_NOT_FOUND before
    any satisfaction verdict exists to grade. The scenario still says WHICH id, and it
    cannot name one that only the in-process registry mock would answer.

    AND THE CATALOG IS ALREADY THERE, which is why this step arranges none. The door
    ``resolvable_format_ref`` guards asks whether the AGENT serves the id; the projection
    then asks the agent what canonical kind it declares, and both now read the committed
    capture on every env this step routes to -- ``CreativeSyncEnv`` installs production's
    ``ReferenceFormatsRegistry`` serving all 71 formats (1883dedc4), and
    ``LibraryUpsertCreativeSyncEnv`` leaves ``get_creative_agent_registry`` unpatched, so
    the registry it reaches serves the same capture for itself. Measured:
    ``video_1280x720`` is in the capture and declares ``canonical.kind = video_hosted``,
    and no registry glob matches it.

    THIS STEP USED TO CALL ``serve_reference_catalog()`` HERE (since deleted). That
    method wrote through ``mock["registry"]``, a key ``LibraryUpsertCreativeSyncEnv``
    DELETES after ``__enter__`` (the trap its own docstring names), so the two
    ``@creative_library_upsert`` scenarios routed there died in this Given with
    ``KeyError: 'registry'`` on all four transports -- measured red at
    ``tests/harness/creative_sync.py:1148`` in box run innet_171026_2156, and before
    1883dedc4 renamed the key, as ``KeyError: 'run_async'`` in innet_171026_2038. The call
    bought nothing on either env: it only UNDOES a prior narrowing, no Given here narrows,
    and the capture is the default. A catalogue a scenario needs narrowed says so with
    ``set_served_catalogue``, which seeds a real peer agent rather than the registry and
    so works on the real-registry env too.
    """
    from tests.factories.format import resolvable_format_ref
    from tests.factories.request import CreativeAssetRequestFactory

    ctx["creatives"] = [
        CreativeAssetRequestFactory.payload(
            creative_id=_SYNC_CREATIVE_ID,
            format_id=resolvable_format_ref(format_id, **parameters),
        )
    ]


@given(
    parsers.parse(
        'the buyer syncs a creative whose format_option_ref names product option "{option}" beside format_id "{format_id}"'
    )
)
def given_sync_legacy_creative_with_option(ctx: dict, option: str, format_id: str) -> None:
    """The DEPRECATED arm carrying a ``format_option_ref`` beside it.

    ``core/creative-asset.json`` declares ``format_option_ref`` at the item's top level and
    forbids it in neither oneOf arm, so a v1 item may route to an exact product option too.
    Worded like the canonical sibling, option first, so neither this sentence nor the plain
    ``identified by format_id "{format_id}"`` Given can bind the other's text.
    """
    _sync_legacy_claim(ctx, format_id)
    ctx["creatives"][0]["format_option_ref"] = {"scope": "product", "format_option_id": option}


@given(parsers.parse('the buyer syncs a creative identified by format_id "{format_id}"'))
def given_sync_legacy_creative(ctx: dict, format_id: str) -> None:
    """The same payload identified by its DEPRECATED reference, for the legacy lane's row.

    The ONE difference from its canonical sibling is which identifier arm the creative
    carries, which is what decides the lane -- so the lenient asymmetry's two rows differ in
    the creative's arm and the product's arm and nothing else.

    The factory's default asset -- one 300x250 image -- is kept DELIBERATELY under a video
    claim, and is left inconsistent rather than tidied. Nothing validates a creative's assets
    against the format it claims: ``creatives/_validation.py`` carries ``TODO(#767)`` exactly
    where that comparison would go, and this row passing with a mismatched asset is the
    evidence. Authoring a video asset here would make the fixture look right and remove the
    only thing in the suite that shows the check is missing.
    """
    _sync_legacy_claim(ctx, format_id)


@given(parsers.parse('the buyer syncs a creative identified by format_id "{format_id}" sized {width:d}x{height:d}'))
def given_sync_legacy_creative_sized(ctx: dict, format_id: str, width: int, height: int) -> None:
    """The same claim, PARAMETERIZED -- the buyer naming one variant of a template.

    The ONE difference from the unsized sibling is that the reference carries its own
    width and height, which ``core/format-id.json`` says is what names a specific variant
    rather than the template. That is the dimension every other fixture in this module holds
    constant, and holding it constant is why the acceptance comparison could be wrong with
    the whole module green: with no parameters on either side, "compare the template" and
    "compare the variant" return the same answer for every row.

    The parameters go through ``resolvable_format_ref`` with the rest of the reference, so the
    pin's own field names are the only ones a scenario can spell.
    """
    _sync_legacy_claim(ctx, format_id, width=width, height=height)


@given(
    parsers.parse(
        'the buyer syncs a creative identified by format_id "{format_id}" '
        "sized {width:d}x{height:d} at {pixel_ratio:d}x density"
    )
)
def given_sync_legacy_creative_density(ctx: dict, format_id: str, width: int, height: int, pixel_ratio: int) -> None:
    """The claim naming a DENSITY as well as a size -- the fourth parameterizing field.

    Its own step rather than an optional clause on the sized sibling, because a scenario
    that says nothing about density means the claim CARRIES no density, and that silence is
    one of the two cases the rule has to refuse against a product that fixes one. A step
    defaulting the field would make that case unreachable.
    """
    _sync_legacy_claim(ctx, format_id, width=width, height=height, pixel_ratio=pixel_ratio)


@given("the buyer asks for lenient validation")
def given_lenient(ctx: dict) -> None:
    """``validation_mode: "lenient"`` -- "skip what this product will not take"."""
    ctx["validation_mode"] = "lenient"


@when("the Buyer Agent syncs it into the library")
def when_sync_library_only(ctx: dict) -> None:
    """Dispatch a real sync_creatives that WRITES the creative and assigns it to nothing.

    The sibling below assigns as well, and that difference is the whole point: the
    assignment path has a satisfaction gate (``_assignments.py`` calls ``satisfies``) while
    the library UPSERT path has none, so a scenario that assigns cannot tell which gate
    refused. With no ``assignments`` member there is exactly one thing under test -- whether
    the seller will STORE a creative whose format it cannot resolve to a canonical kind.
    """
    from tests.bdd.steps.generic._dispatch import dispatch_request

    dispatch_request(
        ctx,
        account={"account_id": ctx["env"].setup_default_account().account_id},
        creatives=ctx["creatives"],
    )


@when("the Buyer Agent assigns it to that package")
def when_sync_assigns(ctx: dict) -> None:
    """Dispatch a real sync_creatives that syncs the creative AND assigns it to the package."""
    from tests.bdd.steps.generic._dispatch import dispatch_request

    kwargs: dict[str, Any] = {
        "account": {"account_id": ctx["env"].setup_default_account().account_id},
        "creatives": ctx["creatives"],
        "assignments": [{"creative_id": _SYNC_CREATIVE_ID, "package_id": ctx["existing_package"].package_id}],
    }
    if "validation_mode" in ctx:
        kwargs["validation_mode"] = ctx["validation_mode"]
    dispatch_request(ctx, **kwargs)


@given(parsers.parse('the buyer\'s package selects "{selector}"'))
def given_selector(ctx: dict, selector: str) -> None:
    """Put the named format selector on the request's single package.

    MERGED onto the package the shared builder already assembled rather than replacing it:
    the package carries a product_id, a pricing_option_id and a budget that every other
    create scenario also sends, and a selector scenario is not about any of those.
    """
    packages = ctx["request_kwargs"]["packages"]
    assert len(packages) == 1, f"expected exactly one package to put a selector on, got {len(packages)}"
    packages[0].update(_SELECTORS[selector])
    # Which selector was sent, for the conflict Then: its refusal must summarize exactly the
    # arms the buyer supplied, and reading them back off this table is what keeps the
    # scenario's claim tied to its own input rather than to a restated list.
    ctx["selector"] = selector


# ── Then steps ──────────────────────────────────────────────────────


@then("the buyer receives the media buy")
def then_media_buy_allocated(ctx: dict) -> None:
    """Assert the buy exists ON THE WIRE and the response carries no error.

    BOTH halves. ``media_buy_id`` alone is satisfied by a response that allocated the buy
    and then reported a problem alongside it, and an absent ``errors`` key alone is
    satisfied by any non-answer -- so a gate that refused the selector could pass either
    one of them on its own. Read off the serialized body rather than the typed result: the
    typed payload has already coerced every field to its declared type, and what the
    scenario claims is what the buyer received.
    """
    allocated = wire_entry(ctx, "packages", index=0)
    assert allocated.get("product_id") == ctx["default_product"].product_id, (
        f"the allocated package names {allocated.get('product_id')!r}, not the product the selector was graded against"
    )
    media_buy_id = wire_field(ctx, "media_buy_id")
    assert isinstance(media_buy_id, str) and media_buy_id, (
        f"expected a non-empty media_buy_id on the wire, got {media_buy_id!r}"
    )
    wire_absent(ctx, "errors")


@then(parsers.parse('the buyer is refused UNSUPPORTED_FEATURE naming the "{arm}" selector'))
def then_refused_unsupported_feature(ctx: dict, arm: str) -> None:
    """Assert the wire envelope: the code, its pinned recovery, and the field.

    ``assert_wire_error`` defaults ``recovery`` to the PINNED enum's classification for the
    code, so the recovery is graded without this scenario restating it -- UNSUPPORTED_FEATURE
    is ``correctable`` there ("check get_adcp_capabilities and remove unsupported fields"),
    which is the right lever for a buyer who can name a different format.

    The field is pinned because the two canonical selector arms are DIFFERENT fields and a
    refusal naming the wrong one sends the buyer to edit a selector they did not write. The
    buyer-facing message is deliberately not asserted: it is a function of the code through
    CODE_TABLE, so asserting both compares the table to itself.

    The feature's Examples name the ARM and the pointer is composed here, rather than the
    Examples carrying ``packages[0].format_kind`` whole. The square brackets are why: an
    Examples value lands in the pytest nodeid, and the BDD artifact readers take the FIRST
    bracketed token of a nodeid as the transport -- so a bracket inside a parametrize value
    silently misattributes every one of these scenarios to a transport named
    ``0].format_kind`` (salesagent-8qela.159 is that corruption measured on another suite).
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE", field=f"packages[0].{arm}")


@then(
    parsers.parse(
        'the buyer is refused UNSUPPORTED_FEATURE naming the "{arm}" selector '
        'for an uncovered placement of "{selected}"'
    )
)
def then_refused_uncovered_placement(ctx: dict, arm: str, selected: str) -> None:
    """The selector refusal above, narrowed to the placement-coverage rule by its details.

    ``details.capability`` names the rule that refused, which is what separates this
    refusal from an unpublished option ref or an unsatisfied param on the same arm and code.
    ``details.rejected_value`` is the declaration the package selected, compared to the
    option id the scenario names. ``core/error.json`` defines it as "the offending value the
    buyer supplied", and here that is the selection the placement does not admit.
    """
    _assert_placement_refusal(ctx, arm, "placement_uncovered", selected)


@then(
    parsers.parse(
        'the buyer is refused UNSUPPORTED_FEATURE naming the "{arm}" selector '
        'for the unresolved publisher placement "{placement_id}"'
    )
)
def then_refused_unresolved_placement(ctx: dict, arm: str, placement_id: str) -> None:
    """The selector refusal for an included placement whose effective set cannot be resolved.

    ``details.capability`` names the rule (``placement_unresolved``) and
    ``details.rejected_value`` the placement, which is what the buyer cannot be sold until
    the seller resolves the publisher's catalog for it.
    """
    _assert_placement_refusal(ctx, arm, "placement_unresolved", placement_id)


def _assert_placement_refusal(ctx: dict, arm: str, capability: str, rejected: str) -> None:
    """A placement-rule UNSUPPORTED_FEATURE at the arm, naming the rule and the rejected value."""
    ctx["result"].assert_wire_error(
        "UNSUPPORTED_FEATURE",
        field=f"packages[0].{arm}",
        details={"capability": capability, "rejected_value": rejected},
    )


@then("the update is accepted")
def then_update_accepted(ctx: dict) -> None:
    """Assert the update answered on the wire and carries no error.

    Paired halves, same reasoning as the create accept: ``media_buy_id`` alone is satisfied
    by a response that answered and then reported a problem, and an absent ``errors`` key
    alone is satisfied by a non-answer.
    """
    media_buy_id = wire_field(ctx, "media_buy_id")
    assert media_buy_id == ctx["existing_media_buy"].media_buy_id, (
        f"the update answered about {media_buy_id!r}, not the buy the scenario holds"
    )
    wire_absent(ctx, "errors")


@then(parsers.parse('the buyer is refused UNSUPPORTED_FEATURE naming the "{array}" array'))
def then_refused_naming_array(ctx: dict, array: str) -> None:
    """The UPDATE path's refusal, whose pointer names which creative array the buyer sent.

    ``packages[0].<array>`` composed here rather than written in the Examples, for the
    bracket reason the sibling Then records: a bracket inside a parametrize value lands in
    the nodeid and the BDD artifact readers take the first bracketed token as the transport.
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE", field=f"packages[0].{array}")


@then("the assignment is recorded with no assignment error")
def then_assignment_recorded(ctx: dict) -> None:
    """Assert the sync answered AND the creative's assignment carries no error for the package.

    BOTH halves, and the second is the load-bearing one: lenient mode answers SUCCESS while
    recording per-package failures in ``assignment_errors``, so a scenario asserting only
    that the sync succeeded would pass on a refusal that was merely recorded instead of
    raised. Read off the WIRE entry for this creative (``creatives[]`` carries the
    per-creative ``assignment_errors`` map), not the typed payload, which has already been
    coerced to its declared type.
    """
    entry = wire_entry(ctx, "creatives", creative_id=_SYNC_CREATIVE_ID)
    assert entry.get("action") in ("created", "updated"), f"the creative was not accepted: {entry!r}"
    errors = entry.get("assignment_errors") or {}
    assert errors == {}, f"expected no assignment error, got {errors!r}"


@then("the sync succeeds and records an assignment error for that package")
def then_assignment_error_recorded(ctx: dict) -> None:
    """Assert lenient mode SOFTENED the deprecated-arm refusal: success plus a recorded error.

    The control for the canonical row above. Three things together, because any two of them
    are satisfied by the wrong behaviour: the call succeeded (not refused), the error map
    names THIS package, and the recorded reason names both format identities -- the refused
    one and what the product accepts. The reason is graded on those VALUES and not on its
    wording, the same correction made to the sibling integration test.

    ``video_1280x720`` is the refused id, and it is a CATALOG id on purpose: the scenario's
    creative claims a reference production RESOLVES, so what the record names is a
    satisfaction verdict rather than an unresolvable-reference refusal upstream of the gate.
    It also cannot satisfy the second assertion by accident, which a nearer id would --
    ``display_300x250`` is a substring of the catalog's ``display_300x250_image``.
    """
    result = ctx["result"]
    assert result.is_success, f"lenient mode should have answered success, got {result.error!r}"
    creative_results = result.payload.creatives
    assert creative_results, "sync_creatives answered with no creative results"
    package_id = ctx["existing_package"].package_id
    errors = creative_results[0].assignment_errors or {}
    assert package_id in errors, f"no assignment error recorded for {package_id!r}: {errors!r}"
    recorded = errors[package_id]
    assert "video_1280x720" in recorded, f"the record does not name the refused format: {recorded}"
    assert "display_300x250" in recorded, f"the record does not name what the product accepts: {recorded}"


@then("the buyer is refused INVALID_REQUEST")
def then_refused_invalid_request(ctx: dict) -> None:
    """Assert the SCHEMA bucket, which is the point: a malformed selector is not an
    unsupported one.

    No ``field`` asserted, and that is this refusal's own shape rather than an omission: the
    pin's conjunct is stated at the PackageRequest ROOT (over ``format_kind``, ``height``
    and ``params`` jointly), so there is no single member to point at -- pinning one would
    assert a pointer the pinned model has no basis to emit. The CODE is the obligation the
    storyboard step states, and the code is what this grades.
    """
    ctx["result"].assert_wire_error("INVALID_REQUEST")


@then(parsers.parse('the creative is stored carrying canonical kind "{kind}"'))
def then_stored_with_canonical_kind(ctx: dict, kind: str) -> None:
    """The POSITIVE half of the write gate: the projected kind reaches the column.

    Read off the stored row rather than off the response, because the column is the subject
    -- a NOT NULL constraint is satisfied by any non-null value, so what has to be shown is
    that the value is the kind the registry projects and not merely that something was
    written. The fire-probe for this change perturbs exactly that: make the projection
    return a WRONG kind and this assertion is the one that must redden.

    The sync is asserted to have SUCCEEDED first. Without that, an exception path that
    stored nothing and answered an error would make the kind assertion fail for the wrong
    reason and read as a projection bug.
    """
    stored_kind = _stored_synced_creative_column(ctx, "format_kind")
    assert stored_kind == kind, (
        f"stored format_kind={stored_kind!r}, expected {kind!r} -- the kind the buyer named, or the "
        f"one the registry projects its legacy id to; a different value is not the identity it sent"
    )


@then(parsers.parse('the creative is stored with its format_option_ref naming product option "{option}"'))
def then_stored_with_option_ref(ctx: dict, option: str) -> None:
    """The option ref the buyer sent reaches the column WHOLE, scope discriminator included.

    core/format-option-ref.json is a oneOf whose arms differ by ``scope`` (and by
    ``publisher_domain``, required on one arm and forbidden on the other), so the stored
    document is compared whole: an id kept without its scope would read back as neither arm.
    """
    stored = _stored_synced_creative_column(ctx, "format_option_ref")
    assert stored == {"scope": "product", "format_option_id": option}, (
        f"stored format_option_ref={stored!r}, expected the product-scoped ref to {option!r}"
    )


def _stored_synced_creative_column(ctx: dict, column: str) -> Any:
    """One column of the synced creative's stored row, after asserting the sync succeeded.

    The sync is asserted to have SUCCEEDED first: an exception path that stored nothing
    and answered an error would otherwise fail the column assertion for the wrong reason.
    Read off the row because the column is the subject -- a constraint is satisfied by any
    value, so what has to be shown is that the value is the one the buyer's identity names.
    """
    from tests.bdd.steps._outcome_helpers import stored_creative_column

    result = ctx["result"]
    assert result.is_success, f"the sync was expected to succeed but answered {result.error!r}"
    return stored_creative_column(ctx, _SYNC_CREATIVE_ID, column)


@then("the buyer is refused UNSUPPORTED_FEATURE and nothing is stored")
def then_refused_and_nothing_stored(ctx: dict) -> None:
    """The refusal AND the absence of the row, because the wire alone cannot show the write.

    The user's ruling is "gate at writing, not write if we can't resolve it", and a wire
    envelope cannot distinguish a seller that refused BEFORE writing from one that wrote the
    row and then answered an error. Those are different sellers: the second leaves a
    ``format_kind`` NULL behind for every later reader, which is the defect. So the state
    that must NOT have changed is asserted alongside the code -- read back through
    ``CreativeUoW``, the same repository production writes through, rather than by a raw
    query that could see a different transaction.

    BOTH halves, and each is needed. The code alone passes on a seller that stored the row
    and refused afterwards; the empty library alone passes on a seller that refused for some
    unrelated reason and never got near the write.

    THE REFUSAL IS PER-CREATIVE, NOT A WIRE ENVELOPE, and this step asserted the envelope
    first and was wrong to. ``sync_creatives`` is a BATCH tool: the pinned
    ``sync-creatives-response.json`` carries the outcome per entry in ``creatives[]``, with
    ``failed`` among the ``creative-action`` enum's members and an ``errors`` list on the
    entry, so one unservable creative in a batch of three must not fail the other two. The
    request itself therefore completes. Measured before the assertion was corrected:
    production answered ``status=completed``, "Synced 0 creatives, 1 failed",
    ``action=failed``, with ``UNSUPPORTED_FEATURE`` and ``recovery=correctable`` on the entry
    -- the right behaviour failing a demand for the wrong shape. The entry is located by
    ``creative_id`` rather than by position, so the obligation does not quietly become "and
    it was first".

    READ OFF THE TYPED PAYLOAD, not the wire dict. Indexing ``wire["creatives"][...]
    ["errors"]`` is a step re-deriving where the spec puts a field, which
    ``test_architecture_bdd_wire_discipline`` refuses by name -- and it refused this step
    when it was written that way. ``assert_wire_error`` is not the remedy here either: that
    asserts the ENVELOPE, and this is a batch tool whose request COMPLETES while one entry
    fails. ``payload_or_none`` is the sanctioned reader that keeps the value's provenance,
    and the typed model exposes ``action`` and ``errors`` as attributes, so no position is
    restated. Same primitive the UC-006 per-creative steps use.
    """
    _assert_entry_failed_and_nothing_stored(ctx, "UNSUPPORTED_FEATURE")


@then(parsers.parse("the creative is reported failed with {code:w} and nothing is stored"))
def then_reported_failed_and_nothing_stored(ctx: dict, code: str) -> None:
    """A library-only sync refused per item for its manifest, and the row not written.

    The same two halves as the unprojectable-format refusal above, for a different code:
    a canonical manifest assigned to nothing is held to the slots its kind declares
    (creative-manifests.mdx § Validation), and one that does not fill them is a per-entry
    failure of the batch, not a stored creative.
    """
    _assert_entry_failed_and_nothing_stored(ctx, code)


def _assert_entry_failed_and_nothing_stored(ctx: dict, code: str) -> None:
    """The synced creative's batch entry FAILED with exactly *code*, and no row was written.

    Read off the typed payload by ``creative_id`` and the library read back through
    ``CreativeUoW``; the reasons both halves are needed are on
    :func:`then_refused_and_nothing_stored`.
    """
    from src.core.database.repositories.uow import CreativeUoW

    resp = payload_or_none(ctx)
    assert resp is not None, (
        f"the dispatch produced no payload, so the batch never answered about "
        f"{_SYNC_CREATIVE_ID!r} ({ctx.get('error')!r})"
    )
    entries = {entry.creative_id: entry for entry in resp.creatives}
    assert _SYNC_CREATIVE_ID in entries, f"the batch answered about {sorted(entries)}, not {_SYNC_CREATIVE_ID!r}"
    entry = entries[_SYNC_CREATIVE_ID]
    action = entry.action.value if hasattr(entry.action, "value") else str(entry.action)
    assert action == "failed", (
        f"the creative was reported {action!r}; the gate is supposed to refuse it, and any "
        f"other action means it was admitted"
    )
    codes = [error.code for error in entry.errors or []]
    assert codes == [code], (
        f"expected exactly {code} on the entry, got {codes!r}. The pinned enum classifies it "
        f"correctable, which is what leaves the buyer a lever to resend a creative this seller takes"
    )
    # Values, not rows: a ``Creative`` read past the UoW is detached and raises on attribute
    # access, which would surface as a DetachedInstanceError instead of this assertion.
    with CreativeUoW(ctx["tenant"].tenant_id) as uow:
        assert uow.creatives is not None
        stored_kinds = {
            c.creative_id: c.format_kind for c in uow.creatives.list_by_principal(ctx["principal"].principal_id)
        }
    assert _SYNC_CREATIVE_ID not in stored_kinds, (
        f"the seller refused on the wire but STORED {_SYNC_CREATIVE_ID!r} anyway, with "
        f"format_kind={stored_kinds[_SYNC_CREATIVE_ID]!r}. The ruling is to gate at the "
        f"write, so a refusal that leaves the row behind is the defect rather than the fix."
    )


@then(parsers.parse("the creative is refused {code:w} naming the packages field"))
def then_creative_refused_naming_packages(ctx: dict, code: str) -> None:
    """The create path's manifest refusal: the code, the ``packages`` pointer and the creative.

    enums/error-code.json on CREATIVE_SIZE_MISMATCH: "Sellers SHOULD identify the offending
    creative" -- the pointer names the request field the buyer sent (the packages array, as
    every creative refusal on this path does) and ``details.creative_id`` names the creative.
    """
    _assert_creative_refused(ctx, code, field="packages")


@then(parsers.parse('the creative is refused {code:w} naming the "{array}" array'))
def then_creative_refused_naming_array(ctx: dict, code: str, array: str) -> None:
    """The update path's manifest refusal, pointing at the creative array the buyer sent."""
    _assert_creative_refused(ctx, code, field=f"packages[0].{array}")


@then(parsers.parse("the creative is refused {code:w}"))
def then_creative_refused(ctx: dict, code: str) -> None:
    """The sync assignment path's manifest refusal: the code and the creative, no pointer.

    No ``field`` for the reason :func:`then_refused_unsupported_feature_bare` gives: the
    assignment gate refuses a STORED creative, and which one is ``details.creative_id``.
    """
    _assert_creative_refused(ctx, code, field=None)


def _assert_creative_refused(ctx: dict, code: str, *, field: str | None) -> None:
    """The wire envelope carries *code* (its pinned recovery) and names the scenario's creative."""
    result = ctx["result"]
    result.assert_wire_error(code, field=field)
    details = result.wire_error_details(code)
    assert details.get("creative_id") == ctx["manifest_creative_id"], (
        f"the refusal names creative {details.get('creative_id')!r}, not {ctx['manifest_creative_id']!r}: {details}"
    )
    ctx["refused_code"] = code


def _refusal_problem(ctx: dict, path: str) -> dict[str, Any]:
    """The ``problems[]`` entry for manifest *path* in the refusal a prior Then asserted."""
    details = ctx["result"].wire_error_details(ctx["refused_code"])
    problems = {problem.get("field"): problem for problem in details.get("problems") or []}
    assert path in problems, f"the refusal names no problem at {path!r}; it names {sorted(problems)}"
    problem = problems[path]
    assert problem.get("subject_id") == ctx["manifest_creative_id"], f"the problem is about another subject: {problem}"
    return dict(problem)


@then(parsers.parse('the refusal names "{path}" stating "{rejected}" where "{accepted}" is accepted'))
def then_refusal_names_stated_value(ctx: dict, path: str, rejected: str, accepted: str) -> None:
    """One failed constraint, as values: what the asset states and what the declaration accepts.

    The SIZE_MISMATCH entry in enums/error-code.json: a seller "MAY include the submitted and
    accepted dimensions in buyer-safe error.details". ``accepted`` is the declaration's set
    or bound, comma-separated in the feature.
    """
    problem = _refusal_problem(ctx, path)
    assert problem.get("rejected_value") == rejected, f"{path}: stated {problem.get('rejected_value')!r}"
    assert problem.get("accepted_values") == [value.strip() for value in accepted.split(",")], (
        f"{path}: accepted {problem.get('accepted_values')!r}"
    )


@then(parsers.parse('the refusal names "{path}" missing where "{accepted}" is accepted'))
def then_refusal_names_missing_slot(ctx: dict, path: str, accepted: str) -> None:
    """Something the manifest does not supply: nothing stated, what the declaration requires accepted.

    A required slot left empty (its asset type accepted), an asset silent about a capped member
    (the cap accepted), or a rendition set lacking a required pixel ratio (that ratio accepted).
    """
    problem = _refusal_problem(ctx, path)
    assert "rejected_value" not in problem, f"{path} is reported as stating {problem.get('rejected_value')!r}"
    assert problem.get("accepted_values") == [accepted], f"{path}: accepted {problem.get('accepted_values')!r}"


@then(parsers.parse('the refusal names the compatible options "{options}"'))
def then_refusal_names_compatible_options(ctx: dict, options: str) -> None:
    """An ambiguous selection names the declarations the manifest fits, the values a ref may take.

    core/creative-asset.json, ``format_option_ref``: "Required when the target product has
    multiple format_options entries sharing the same format_kind". ``accepted_values`` is the
    pin's canonical rejection-set key, and here it lists exactly the options the buyer can
    name to disambiguate.
    """
    details = ctx["result"].wire_error_details(ctx["refused_code"])
    assert details.get("accepted_values") == [option.strip() for option in options.split(",")], details


@then("the buyer is refused UNSUPPORTED_FEATURE")
def then_refused_unsupported_feature_bare(ctx: dict) -> None:
    """The ASSIGNMENT path's refusal: the code and its pinned recovery, no field.

    No ``field`` here, deliberately and not as an omission. The assignment gate refuses a
    STORED creative's identity, and ``core/error.json``'s ``field`` names a request field --
    which creative is in ``details.creative_id`` and which package in ``details.package_id``,
    both of which the raise site supplies. Asserting a pointer this path does not own would
    pin a value production has no reason to carry.
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE")


@then(parsers.parse("the buyer is refused VALIDATION_ERROR naming the {width:d}x{height:d} it accepts"))
def then_refused_legacy_not_accepted(ctx: dict, width: int, height: int) -> None:
    """The DEPRECATED lane's refusal, and the dimensions have to be in it.

    A DIFFERENT CODE from the canonical sibling, and that is production's documented
    decision rather than this scenario's preference: the creative ASSIGNMENT sites skip
    ``canonical_refusal`` for ``LEGACY_NOT_ACCEPTED`` and raise ``AdCPValidationError``
    themselves -- "violates business rules beyond schema validation". (A package's own
    format selector is a different site, coded UNSUPPORTED_FEATURE by
    ``media-buy/package-request.json``'s selector contract.) A row asserting UNSUPPORTED_FEATURE here would be asserting the canonical
    lane's code against the deprecated lane's refusal, which is the mistake this Then was
    written to replace. No ``field``: the site carries none, for the same reason the bare
    UNSUPPORTED_FEATURE sibling asserts none.

    THE DIMENSIONS ARE THE POINT, not the code. Before the fix the accepted set was built
    from TEMPLATE keys, so it could only ever say ``<agent>/display_image`` -- the same
    string for a product restricting to 300x250 and one restricting to nothing. Asserting
    the code alone would pass against that, since a refusal would still arrive once anything
    reddened. Asserting that the buyer is told WHICH size the product accepts is what
    distinguishes a represented restriction from an unrepresentable one.

    Graded as a substring of the accepted set rather than against a rendered literal: the
    exact spelling is ``_reference_display``'s and pinning it would grade this seller's
    formatting, where the obligation is that the dimensions reach the buyer at all.

    The array comes from ``wire_envelope_errors``, not from indexing the envelope here. Its
    own docstring names this mistake: "without this one, a step needing it wrote
    ``envelope.get('errors')`` itself and the guard flagged it, correctly." It did -- check F
    of ``test_architecture_bdd_wire_discipline`` caught the first version of this step.
    """
    ctx["result"].assert_wire_error("VALIDATION_ERROR")
    _assert_accepted_size_named(ctx, width, height)


@then(
    parsers.parse(
        'the buyer is refused UNSUPPORTED_FEATURE naming the "format_ids" selector and the {width:d}x{height:d} it accepts'
    )
)
def then_refused_legacy_selector_not_accepted(ctx: dict, width: int, height: int) -> None:
    """The deprecated lane's refusal of a PACKAGE selector: UNSUPPORTED_FEATURE, and the size.

    ``media-buy/package-request.json``'s "Format selector contract (normative)": "A single
    resolved route that does not satisfy the product is rejected with
    ``UNSUPPORTED_FEATURE``", and "a legacy ``format_id`` that cannot be normalized ...
    MUST be rejected with ``UNSUPPORTED_FEATURE``". A legacy-only product is still a product
    the route has to satisfy, so its selector refusal carries this code and the
    ``format_ids`` pointer, where the creative assignment sites above keep VALIDATION_ERROR.
    The accepted size is graded for the reason :func:`then_refused_legacy_not_accepted` gives.
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE", field="packages[0].format_ids")
    _assert_accepted_size_named(ctx, width, height)


def _assert_accepted_size_named(ctx: dict, width: int, height: int) -> None:
    """Assert the refusal's ``details.accepted_values`` tells the buyer the size accepted."""
    accepted = str(wire_envelope_errors(ctx)[0].get("details", {}).get("accepted_values"))
    for value in (width, height):
        assert str(value) in accepted, (
            f"the refusal does not tell the buyer the product accepts {width}x{height}; "
            f"accepted_values={accepted!r}. A template-key accepted set cannot carry a size."
        )


@then("the buyer is refused CONFLICTING_SELECTORS naming the package")
def then_refused_conflicting_selectors(ctx: dict) -> None:
    """Assert the equivalence refusal: the code, its pinned recovery, and the PACKAGE pointer.

    The pointer is ``packages[0]`` and not ``packages[0].<arm>``, which is this refusal's
    own shape rather than a looser assertion: no single arm is at fault, the set of them is,
    and ``enums/error-code.json``'s entry for the code says so -- "``error.field`` SHOULD
    point at the conflicting package". Asserting an arm here would pin the pointer of the
    refusal this one is deliberately NOT: ``option_plus_unprojectable_legacy`` is
    UNSUPPORTED_FEATURE naming ``format_ids``, and the two must not converge.

    ``assert_wire_error`` defaults ``recovery`` to the pinned enum's classification, which
    for this code is ``correctable`` -- the buyer's lever is to send one route, or to make
    the routes agree.

    The DETAILS are asserted too, and they are what stops this passing on a seller that
    answers the code without having compared anything: the pin asks for "the supplied
    selector routes and their normalized canonical summaries", and a route's summary is the
    option SET it selected, because sets are what step (2) compares ("require the selected
    option sets to match"). So, per route -- a route is an arm, and an array arm is one route
    selecting a set:

    - every arm the buyer sent is summarized ONCE, and no other;
    - every summary states its selected set as a list, empty when it selected nothing;
    - on a product that publishes ``format_options[]``, every option named is one it
      publishes (a legacy-only product's selection is the SDK's projection of its
      deprecated arm, whose option ids the product never published);
    - the ``format_option_refs`` arm selected exactly the options its refs name, which is
      the request's own statement and not this seller's derivation: "Each reference
      matches one target product ``format_options[]`` entry";
    - the arms' sets differ, because that disagreement IS the refusal. A summary that
      names one entry of a set two options narrow shows two routes agreeing beside a
      refusal that says they differ.

    WHICH set any other route selected is the scenario's to state, through
    :func:`then_conflict_route_selects`.
    """
    routes = _conflict_route_summaries(ctx)
    request = _SELECTORS[ctx["selector"]]
    sent = [arm for arm in ("format_option_refs", "format_kind", "format_ids") if arm in request]
    assert sorted(route.get("field") for route in routes) == sorted(sent), (
        f"the refusal summarizes routes {[r.get('field') for r in routes]}, but the buyer sent one route per arm {sent}"
    )
    assert all(isinstance(route.get("selected_option"), list) for route in routes), (
        f"every route summary must state the option set it selected (empty when none); got {routes!r}"
    )
    arms = {route["field"]: set(route["selected_option"]) for route in routes}
    published = {option["format_option_id"] for option in ctx["default_product"].format_options or ()}
    named = set().union(*arms.values())
    if published:
        assert named <= published, (
            f"the refusal names options {sorted(named - published)} the product does not publish ({sorted(published)})"
        )
    if "format_option_refs" in request:
        referenced = {ref["format_option_id"] for ref in request["format_option_refs"]}
        assert arms["format_option_refs"] == referenced, (
            f"the format_option_refs route names {sorted(referenced)} but its summary selected "
            f"{sorted(arms['format_option_refs'])}"
        )
    summarized = {arm: sorted(selected) for arm, selected in arms.items()}
    assert len({frozenset(selected) for selected in arms.values()}) > 1, (
        f"every route's summary selected the same set, yet the routes were refused as differing -- got {summarized!r}"
    )


def _conflict_route_summaries(ctx: dict) -> list[dict[str, Any]]:
    """The wire ``CONFLICTING_SELECTORS`` refusal at the package, and its per-route summaries.

    ``wire_error_object`` and not the envelope dict: the envelope WRAPS ``errors[]`` and
    ``details`` lives on the error object inside it, which this reader resolves through the
    one locator the assertion also uses.
    """
    result = ctx["result"]
    result.assert_wire_error("CONFLICTING_SELECTORS", field="packages[0]")
    error_object = result.wire_error_object() or {}
    return list(((error_object.get("details") or {}).get("selector_routes")) or [])


@then(parsers.parse('the conflict summarizes the "{arm}" route as selecting "{options}"'))
def then_conflict_route_selects(ctx: dict, arm: str, options: str) -> None:
    """Assert the summary of route *arm* reports exactly the option SET *options* (comma-separated).

    ``enums/error-code.json`` asks ``CONFLICTING_SELECTORS`` details to "identify the supplied
    selector routes and their normalized canonical summaries", and step (2) of
    ``media-buy/package-request.json`` compares "the selected option sets", so a summary
    carries the set its route selected and this compares it as a set.
    """
    _assert_conflict_route_selected(ctx, arm, set(options.split(",")))


@then(parsers.parse('the conflict summarizes the "{arm}" route as selecting nothing'))
def then_conflict_route_selects_nothing(ctx: dict, arm: str) -> None:
    """Assert the summary of route *arm* reports an EMPTY selected set: it resolved and selected no option."""
    _assert_conflict_route_selected(ctx, arm, set())


def _assert_conflict_route_selected(ctx: dict, arm: str, expected: set[str]) -> None:
    """The one summary for *arm* names *expected* as its selected option set."""
    summaries = [route for route in _conflict_route_summaries(ctx) if route.get("field") == arm]
    assert len(summaries) == 1, f"expected one summary for the {arm!r} route, got {summaries!r}"
    selected = summaries[0].get("selected_option")
    assert isinstance(selected, list) and set(selected) == expected, (
        f"the {arm!r} route is summarized as selecting {selected!r}, expected the set {sorted(expected)!r}"
    )


@then(parsers.parse('the package snapshots the "{option_id}" declaration fixed at {width:d}x{height:d}'))
def then_package_snapshots_declaration(ctx: dict, option_id: str, width: int, height: int) -> None:
    """Assert the accepted package carries the SELECTED declaration as a wire snapshot.

    Read off the serialized body: ``core/package.json`` declares ``formats_to_provide`` as
    an array of ``PackageFormatSnapshot``, whose product-format fields "remain flattened at
    the root", so the kind, the option id and the params are read where the pin puts them.

    The PARAMS are asserted and not only the option id, because the params are what stage
    7's adapters read off the snapshot -- an entry naming the right option with the wrong
    dimensions is the defect a snapshot exists to prevent. ``product_id`` is asserted
    because the pin pairs it with the snapshot ("Product whose effective selected format
    was snapshotted") and because it is the binding that makes the record readable without
    the live product.
    """
    package = wire_entry(ctx, "packages", index=0)
    snapshots = package.get("formats_to_provide")
    assert isinstance(snapshots, list) and len(snapshots) == 1, (
        f"expected exactly one package format snapshot on the wire, got {snapshots!r}"
    )
    snapshot = snapshots[0]
    assert snapshot.get("format_option_id") == option_id, (
        f"the snapshot names option {snapshot.get('format_option_id')!r}, not the selected {option_id!r}"
    )
    assert snapshot.get("format_kind") == "image", f"the snapshot names kind {snapshot.get('format_kind')!r}"
    assert snapshot.get("product_id") == ctx["default_product"].product_id, (
        f"the snapshot binds product {snapshot.get('product_id')!r}, not the one the selector was graded against"
    )
    params = snapshot.get("params") or {}
    assert (params.get("width"), params.get("height")) == (width, height), (
        f"the snapshot's dimensions are {params.get('width')}x{params.get('height')}, expected {width}x{height}"
    )
    ctx["wire_snapshot"] = snapshot


@then("the stored package snapshot names the same declaration")
def then_stored_snapshot_matches(ctx: dict) -> None:
    """Assert the PERSISTED row carries the snapshot the response reported.

    THE HALF A RESPONSE CANNOT PROVIDE. ``core/package.json`` requires a package to "retain
    and return this checklist", and core/package-format-snapshot.json adds "never mutate
    this snapshot in place" -- so a seller that assembled the snapshot for the reply and
    stored nothing would satisfy the sibling Then and then answer every later read from the
    live product, which is the substitution the pin names ("the live Product is never
    substituted for the package snapshot").

    Compared on the three fields that identify the selection rather than on the whole
    document: the stored shape is the persistence edge's serialization (nulls included,
    defaults materialized) and the wire's is ``to_wire``'s, so a whole-document equality
    would be asserting that two serializers agree about absent optionals.
    """
    wire_snapshot = ctx["wire_snapshot"]
    package_id = wire_entry(ctx, "packages", index=0).get("package_id")
    assert package_id, "the response package carries no package_id, so the stored row cannot be read back"
    stored = stored_package_config(ctx, wire_field(ctx, "media_buy_id"), str(package_id))
    snapshots = stored.get("formats_to_provide")
    assert isinstance(snapshots, list) and len(snapshots) == 1, (
        f"expected exactly one persisted package format snapshot, got {snapshots!r}"
    )
    snapshot = snapshots[0]
    stored_identity = (snapshot.get("format_kind"), snapshot.get("format_option_id"), snapshot.get("product_id"))
    wire_identity = (
        wire_snapshot.get("format_kind"),
        wire_snapshot.get("format_option_id"),
        wire_snapshot.get("product_id"),
    )
    assert stored_identity == wire_identity, (
        f"the stored snapshot names {stored_identity!r} and the response reported {wire_identity!r}"
    )
    stored_params = snapshot.get("params") or {}
    wire_params = wire_snapshot.get("params") or {}
    assert (stored_params.get("width"), stored_params.get("height")) == (
        wire_params.get("width"),
        wire_params.get("height"),
    ), (
        f"the stored snapshot's dimensions are {stored_params.get('width')}x{stored_params.get('height')} "
        f"and the response reported {wire_params.get('width')}x{wire_params.get('height')}"
    )


@then(parsers.parse('the package\'s deprecated format_ids_to_provide names "{legacy_id}"'))
def then_legacy_formats_to_provide(ctx: dict, legacy_id: str) -> None:
    """Assert the deprecated projection was DERIVED from the snapshot, not echoed back.

    The buyer's request carries no ``format_ids`` at all in this scenario, so *legacy_id*
    can only have reached the response through the selected declaration's own
    ``v1_format_ref`` -- which is the one legal v2 -> v1 direction
    (``registries/v1-canonical-mapping.json``) and the one source
    ``format_resolver.snapshot_legacy_arm`` reads.
    """
    package = wire_entry(ctx, "packages", index=0)
    assert package.get("format_ids") is None, (
        "this scenario only grades a DERIVATION if the buyer sent no legacy arm, and the "
        f"response echoes format_ids={package.get('format_ids')!r}"
    )
    provided = package.get("format_ids_to_provide")
    assert isinstance(provided, list), f"expected a deprecated format_ids_to_provide array, got {provided!r}"
    assert [entry.get("id") for entry in provided] == [legacy_id], (
        f"format_ids_to_provide names {[e.get('id') for e in provided]}, expected exactly [{legacy_id!r}]"
    )


@then("the package carries no deprecated format_ids_to_provide")
def then_no_legacy_formats_to_provide(ctx: dict) -> None:
    """Assert the projection is ABSENT when the declaration asserts no legacy reference.

    Absent and not empty: ``core/package.json`` types the field as an array of format
    references with no empty-array meaning assigned, and an invented reference is what
    ``registries/v1-canonical-mapping.json`` forbids ("SDKs MUST NOT synthesize a v1
    ``format_id`` from the registry by inverting structural matches ... SDKs that synthesize
    unilaterally produce inter-SDK divergence on structurally-equal values").

    Informative only beside this scenario's first Then, which asserts the snapshot IS
    present on the same response -- an absence assertion alone passes under any perturbation
    that drops the package entirely.

    Asserted on the ENTRY DICT and not through ``wire_absent``, which is deliberate: its
    dotted-path resolver walks objects only, so ``"packages.0.format_ids_to_provide"`` hits
    the list, reads as WIRE_MISSING and would pass whatever the package carried. The key's
    presence on the entry is the real claim, and ``wire_entry`` has already proved the
    package is there.
    """
    package = wire_entry(ctx, "packages", index=0)
    assert "format_ids_to_provide" not in package, (
        "the declaration asserts no v1_format_ref, so there is nothing to project -- yet the "
        f"package carries format_ids_to_provide={package['format_ids_to_provide']!r}"
    )


@then("the buyer is refused UNSUPPORTED_FEATURE naming the packages field")
def then_refused_naming_packages(ctx: dict) -> None:
    """The creative-side refusal, which names ``packages`` rather than one selector arm.

    A creative is not a selector: the buyer sent ``creative_ids``, and WHICH creative is in
    ``details.creative_id`` rather than in the pointer, because the pointer names a request
    FIELD and the request field here is the packages array. The same pointer the sibling
    creative refusals on this path already use (``PACKAGES_FIELD``).
    """
    ctx["result"].assert_wire_error("UNSUPPORTED_FEATURE", field="packages")


# ── The MANUAL-APPROVAL path ────────────────────────────────────────
#
# Everything above dispatches on the AUTO path. These four grade the same satisfaction
# question, and the same snapshot obligation, with the tenant's human_review_required
# column flipped -- which production answers differently, because the manual-approval
# branch returns 190 lines before the selector gate. See the feature's own section comment
# for the measurement and the three beads these are the instrument for.
#
# The Given "the tenant requires manual approval" is the SHARED generic step
# (steps/generic/given_media_buy.py): it flips the tenant column, configures the env's
# adapter mocks' manual_approval_operations (production needs both), and writes the
# AdapterConfig row so the Docker-hosted adapter reads the same state over e2e_rest. Not
# re-implemented here -- one spelling of "this tenant reviews by hand".


@given("the Buyer Agent sent the create_media_buy request")
def given_create_already_sent(ctx: dict) -> None:
    """Dispatch the create as a GIVEN, so the approval scenario's When is the approval.

    The same shared When every other scenario in this feature uses, reached from the Given
    side because this scenario's subject is what happens AFTER the buy is parked. A
    scenario whose When is the create cannot also have the approval as its When.
    """
    from tests.bdd.steps.domain.uc002_create_media_buy import when_send_create_media_buy

    when_send_create_media_buy(ctx)


@given(parsers.parse("the seller then republishes that option fixed at {width:d}x{height:d}"))
def given_product_republished(ctx: dict, width: int, height: int) -> None:
    """Move the LIVE product's declaration after the buy was parked, keeping the option id.

    THE ONE KNOB THIS SCENARIO TURNS, and the reason it can grade anything: with the
    product unchanged, "execute the recorded snapshot" and "execute the live product" give
    the same answer and the scenario is satisfied by either. Editing the params makes the
    two answers differ -- 300x250 against 728x90 -- so the assertion separates them.

    The ``format_option_id`` is deliberately NOT changed. This is the same published option
    the buyer selected, republished with different dimensions, which is the case
    core/package-format-snapshot.json's immutability rule names ("changing selected format
    ... requires a replacement package_id; never mutate this snapshot in place"). Changing
    the id instead would make it a different option and the buy's selector simply
    unresolvable, which is a different question.
    """
    product = ctx["default_product"]
    product.format_options = [{**dict(_DECLARATIONS["fixed_300x250"][0]), "params": {"width": width, "height": height}}]
    ctx["env"]._commit_factory_data()


@when("the publisher approves the parked buy")
def when_publisher_approves(ctx: dict) -> None:
    """Run the real approval execution, the way an admin route runs it.

    ``run_approval`` is the ONE spelling of this call (``tests/helpers/media_buy_approval``),
    shared with the three integration modules that drive it directly, so a BDD scenario and
    an integration test cannot drift on its keyword arguments. Nothing is patched out: the
    callee, both units of work and every commit run for real, and the ad-server boundary is
    the env's adapter mock -- which is what makes the ask observable.
    """
    from tests.helpers.media_buy_approval import run_approval

    buy = parked_media_buy(ctx)
    ctx["approval_result"] = run_approval(buy.media_buy_id, ctx["tenant"].tenant_id)


@then(parsers.parse('the parked package snapshots the "{option_id}" declaration fixed at {width:d}x{height:d}'))
def then_parked_package_snapshots(ctx: dict, option_id: str, width: int, height: int) -> None:
    """Assert the PARKED buy's persisted package records the declaration its selector chose.

    The stored row and not the reply, and that is forced: the submitted envelope carries no
    media_buy_id, so there is nothing on the wire to read a package off. ``parked_media_buy``
    locates the buy by tenant through the repository for the same reason.

    Asserted on the same three identity fields plus the params as the auto-path sibling, so
    the two paths are held to one obligation rather than two.
    """
    from src.core.database.repositories.uow import MediaBuyUoW

    buy = parked_media_buy(ctx)
    with MediaBuyUoW(ctx["tenant"].tenant_id) as uow:
        assert uow.media_buys is not None
        packages = uow.media_buys.get_packages(buy.media_buy_id)
        configs = [dict(p.package_config or {}) for p in packages]
    assert len(configs) == 1, f"expected one persisted package on the parked buy, got {len(configs)}"
    snapshots = configs[0].get("formats_to_provide")
    assert isinstance(snapshots, list) and len(snapshots) == 1, (
        f"the parked buy's package records formats_to_provide={snapshots!r}; "
        f"core/package.json requires the selected declaration to be retained, and the package "
        f"carries only {sorted(configs[0])}"
    )
    snapshot = snapshots[0]
    assert snapshot.get("format_option_id") == option_id, (
        f"the recorded snapshot names option {snapshot.get('format_option_id')!r}, not {option_id!r}"
    )
    assert snapshot.get("product_id") == ctx["default_product"].product_id, (
        f"the recorded snapshot binds product {snapshot.get('product_id')!r}"
    )
    params = snapshot.get("params") or {}
    assert (params.get("width"), params.get("height")) == (width, height), (
        f"the recorded snapshot's dimensions are {params.get('width')}x{params.get('height')}, "
        f"expected {width}x{height}"
    )


@then(parsers.parse("the ad server is asked to traffic a {width:d}x{height:d} package"))
def then_adapter_trafficks_dimensions(ctx: dict, width: int, height: int) -> None:
    """Assert what the CREATE handed the ad server, read off the adapter boundary.

    The create-path sibling of :func:`then_adapter_asked_for_dimensions`, separate rather
    than shared because the two read a different call: that one grades an APPROVAL replay
    and asserts an approval ran first, while this one grades the create that the When
    dispatched. A shared step would have to branch on which ran, which is the silent-env
    shape the BDD guards forbid.

    IN-PROCESS ONLY, and NOT for the reason the approval sibling appears to share. That one
    IS graded on e2e_rest and non-vacuously -- its row went PASSED, FAILED, PASSED across
    three in-network runs -- so "the adapter is unobservable on a live transport" would be
    false. The real difference is WHICH PROCESS RUNS THE BEHAVIOUR. ``when_publisher_approves``
    calls ``run_approval`` directly in the TEST process on every transport (that helper has no
    e2e branch at all), so on e2e_rest only the CREATE crosses the wire and the approval it
    grades is in-process, populating this same mock for real.

    This step grades the create itself, which on e2e_rest executes inside the container
    against the Docker mock ad server. There is no in-process call to read, and no
    server-written record of what the ad server was asked to traffic: ``package_config``
    holds the package's creative CONTRACT (``formats_to_provide`` /
    ``format_ids_to_provide``, which for a legacy-only product is the BUYER'S request arm),
    and the create path's audit records carry budget and counts and no dimensions. Reading
    either would grade the ask rather than the resolution. ``salesagent-6k1g0`` is the record
    that would lift these scenarios to four transports.
    """
    from tests.bdd.steps._outcome_helpers import is_e2e

    assert not is_e2e(ctx), (
        "this step reads the in-process adapter mock, and on a live transport the create runs "
        "in the container where that mock is never populated -- unlike the approval sibling, "
        "whose When runs in-process on every transport. A scenario using this step must not be "
        "routed to a live transport until salesagent-6k1g0 gives the server a record of what "
        "it asked the ad server to traffic."
    )
    adapter = ctx["env"].mock["adapter"].return_value
    calls = adapter.create_media_buy.call_args_list
    assert calls, "the create never reached the ad server, so there is nothing to grade"
    media_packages = calls[-1].kwargs.get("packages") or calls[-1].args[1]
    dimensions = [(f.width, f.height) for pkg in media_packages for f in (pkg.format_ids or [])]
    assert (width, height) in dimensions, (
        f"the ad server was asked to traffic {dimensions!r}, which does not include the "
        f"{width}x{height} this scenario requires"
    )


@then(parsers.parse("the ad server is asked for a {width:d}x{height:d} package"))
def then_adapter_asked_for_dimensions(ctx: dict, width: int, height: int) -> None:
    """Assert what the APPROVAL handed the ad server, read off the adapter boundary.

    An approval's product IS the ad-server call, so that is the observable rather than a
    response field. ``_execute_adapter_media_buy_creation`` resolves ``get_adapter`` as a
    module global in ``media_buy_create``, which is the name this env patches, so the
    MediaPackage list the approval reconstructed is recorded on the mock.

    Graded on the DIMENSIONS and not on the format id: the id is unchanged by the Given
    that republishes the option, so an id comparison would pass whichever declaration the
    approval read. The dimensions are the axis the two answers differ on.
    """
    approval = ctx.get("approval_result")
    assert approval is not None, "no approval was run — the When must dispatch it before this Then"
    adapter = ctx["env"].mock["adapter"].return_value
    calls = adapter.create_media_buy.call_args_list
    assert calls, (
        f"the approval never reached the ad server, so there is nothing to grade "
        f"(approval outcome={getattr(approval, 'outcome', approval)!r})"
    )
    # The tool calls adapter.create_media_buy(request, packages, ...) positionally.
    media_packages = calls[-1].kwargs.get("packages") or calls[-1].args[1]
    dimensions = [(f.width, f.height) for pkg in media_packages for f in (pkg.format_ids or [])]
    assert (width, height) in dimensions, (
        f"the ad server was asked for {dimensions!r}, which does not include the "
        f"{width}x{height} the parked buy recorded — the approval read the live product, "
        f"not the package snapshot"
    )


@then("the buy is parked for a human decision")
def then_buy_is_parked(ctx: dict) -> None:
    """Assert the SUBMITTED task envelope, and that a buy was actually parked.

    Its own step rather than the generic "the approval path should be manual", and the
    difference is the obligation, not the spelling: that step accepts ``completed`` and
    ``active`` as well, because the Docker-hosted mock adapter auto-approves over e2e. This
    scenario's whole claim is that the buy is PARKED -- it is the accept half of the pair
    whose refuse half asserts a refusal -- so a status that means "already executed" must
    not satisfy it.

    BOTH halves, for the reason the sibling accept steps in this module record: the
    envelope alone is satisfied by a seller that answered ``submitted`` and persisted
    nothing, and a persisted row alone says nothing about what the buyer was told.
    ``parked_media_buy`` asserts there is exactly one buy for the tenant, which is also
    what the later approval steps address.
    """
    payload = ctx["result"].payload
    status = str(getattr(payload, "status", None) or "")
    assert status.endswith("submitted"), f"expected the submitted task envelope for a parked buy, got status={status!r}"
    buy = parked_media_buy(ctx)
    assert str(buy.status).endswith("pending_approval"), (
        f"the buy was reported submitted but persisted status={buy.status!r}, "
        "so nothing is actually waiting for an approver"
    )


@then(parsers.parse('the parked package\'s deprecated format_ids_to_provide names "{legacy_id}"'))
def then_parked_legacy_formats_to_provide(ctx: dict, legacy_id: str) -> None:
    """Assert the PARKED buy's deprecated projection is derived, not echoed, like the auto path's.

    The buyer sent only ``format_option_refs``, so *legacy_id* can have reached the record
    only through the selected declaration's own ``v1_format_ref`` -- the one legal v2 -> v1
    direction (``registries/v1-canonical-mapping.json``). Before the manual branch recorded
    a snapshot there was nothing to derive from and the field was absent, which
    ``core/package.json`` says a buyer must not read as full coverage
    ("Absence means legacy readiness was not reported").

    The auto-path sibling asserts the same thing off the WIRE; this one reads the stored
    row, because a parked buy's envelope carries no package at all.
    """
    from src.core.database.repositories.uow import MediaBuyUoW

    buy = parked_media_buy(ctx)
    with MediaBuyUoW(ctx["tenant"].tenant_id) as uow:
        assert uow.media_buys is not None
        configs = [dict(p.package_config or {}) for p in uow.media_buys.get_packages(buy.media_buy_id)]
    assert len(configs) == 1, f"expected one persisted package on the parked buy, got {len(configs)}"
    provided = configs[0].get("format_ids_to_provide")
    assert isinstance(provided, list), (
        f"the parked buy records format_ids_to_provide={provided!r}; the selected declaration "
        f"asserts a v1_format_ref, so the projection has a source"
    )
    assert [entry.get("id") for entry in provided] == [legacy_id], (
        f"format_ids_to_provide names {[e.get('id') for e in provided]}, expected exactly [{legacy_id!r}]"
    )

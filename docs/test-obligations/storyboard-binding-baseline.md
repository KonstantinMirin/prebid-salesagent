# Storyboard binding baseline — AdCP 3.1.1

`40` scenarios tagged `@storyboard-v3.1`. Declared specialisms: `sales_non_guaranteed`; protocols: `media_buy`.

Buckets — **A** binding verified · **B** wrong/stale `@source` · **C** tag unjustified (ungraded or undeclared gate) · **D** graded but under-asserted · **E** graded, blocked on production.

| Scenario | Feature:line | Bucket | Findings |
|---|---|---|---|
| `T-UC-001-storyboard-proposal-finalize-action` | BR-UC-001-discover-available-inventory.feature:1747 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-001-storyboard-finalize-uses-refine-vocabulary` | BR-UC-001-discover-available-inventory.feature:1766 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip` | BR-UC-002-create-media-buy.feature:2601 | **B** | self-declared storyboard ['create_media_buy_async'] does not match cited file ['governance_approved'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-governance-approved` | BR-UC-002-create-media-buy.feature:2620 | **B** | self-declared storyboard ['governance_approved'] does not match cited file ['governance_conditions'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-governance-with-conditions` | BR-UC-002-create-media-buy.feature:2634 | **B** | self-declared storyboard ['governance_conditions'] does not match cited file ['governance_denied'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-governance-denied` | BR-UC-002-create-media-buy.feature:2649 | **B** | self-declared storyboard ['governance_denied'] does not match cited file ['governance_denied_recovery'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-governance-denied-recovery` | BR-UC-002-create-media-buy.feature:2664 | **B** | self-declared storyboard ['governance_denied_recovery'] does not match cited file ['inventory_list_no_match'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-inventory-list-no-match` | BR-UC-002-create-media-buy.feature:2680 | **B** | self-declared storyboard ['inventory_list_no_match'] does not match cited file ['inventory_list_targeting'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-inventory-list-targeting-parity` | BR-UC-002-create-media-buy.feature:2699 | **B** | self-declared storyboard ['inventory_list_targeting'] does not match cited file ['measurement_terms_rejected'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-measurement-terms-rejected` | BR-UC-002-create-media-buy.feature:2714 | **B** | self-declared storyboard ['measurement_terms_rejected'] does not match cited file ['pending_creatives_to_start'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-pending-creatives-state-transition` | BR-UC-002-create-media-buy.feature:2730 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-003-storyboard-media-buy-not-found` | BR-UC-003-update-media-buy.feature:2048 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-003-storyboard-package-not-found` | BR-UC-003-update-media-buy.feature:2063 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-003-storyboard-not-cancellable-on-recancel` | BR-UC-003-update-media-buy.feature:2078 | **B** | self-declared storyboard ['invalid_transitions'] does not match cited file ['creative_fate_after_cancellation'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-003-storyboard-creative-fate-after-cancellation` | BR-UC-003-update-media-buy.feature:2094 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | BR-UC-004-deliver-media-buy-metrics.feature:1318 | **B** | self-declared storyboard ['delivery_reporting'] does not match cited file ['measurement_accountability'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | BR-UC-004-deliver-media-buy-metrics.feature:1334 | **B** | self-declared storyboard ['measurement_accountability'] does not match cited file ['vendor_metric_accountability'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-004-storyboard-vendor-metric-end-to-end` | BR-UC-004-deliver-media-buy-metrics.feature:1357 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-005-storyboard-format-id-roundtrip-from-products` | BR-UC-005-discover-creative-formats.feature:1068 | **B** | self-declared storyboard ['list_formats_integrity'] does not match cited file ['index'] — footer points at a storyboard this scenario never claims<br>names phase 'list_formats_integrity' but cites ['protocols/creative/index.yaml'] — that phase lives in ['domains/media-buy/index.yaml', 'protocols/media-buy/index.yaml']<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope` | BR-UC-005-discover-creative-formats.feature:1086 | **B** | self-declared storyboard ['list_formats_integrity'] does not match cited file ['index'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-005-storyboard-baseline-format-id-object-shape` | BR-UC-005-discover-creative-formats.feature:1102 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-provenance-required-rejection` | BR-UC-006-sync-creatives.feature:1537 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-provenance-digital-source-type-missing` | BR-UC-006-sync-creatives.feature:1550 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-provenance-disclosure-missing` | BR-UC-006-sync-creatives.feature:1563 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-provenance-corrected-acceptance` | BR-UC-006-sync-creatives.feature:1576 | **B** | self-declared storyboard ['provenance_enforcement'] does not match cited file ['provenance_truth_of_claim'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-provenance-claim-contradicted` | BR-UC-006-sync-creatives.feature:1591 | **B** | self-declared storyboard ['provenance_truth_of_claim'] does not match cited file ['index'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-multi-format-sync` | BR-UC-006-sync-creatives.feature:1610 | **B** | self-declared storyboard ['sync_multiple'] does not match cited file ['index'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-format-id-roundtrip-on-sync` | BR-UC-006-sync-creatives.feature:1626 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-creative-reception-stateful-render` | BR-UC-006-sync-creatives.feature:1640 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-008-storyboard-baseline-end-to-end` | BR-UC-008-manage-audience-signals.feature:1112 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-008-storyboard-activate-agent-destination` | BR-UC-008-manage-audience-signals.feature:1129 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-008-storyboard-activate-platform-destination` | BR-UC-008-manage-audience-signals.feature:1144 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-014-storyboard-baseline-session-id-roundtrip` | BR-UC-014-sponsored-intelligence-session.feature:1284 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-018-storyboard-list-all-creatives-after-sync` | BR-UC-018-list-creatives.feature:760 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-018-storyboard-filter-by-format-id-object` | BR-UC-018-list-creatives.feature:774 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-018-storyboard-filter-by-concept-id` | BR-UC-018-list-creatives.feature:788 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-019-storyboard-post-create-status-poll` | BR-UC-019-query-media-buys.feature:1235 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-020-storyboard-build-vast-tag-from-synced-creative` | BR-UC-020-build-creative.feature:1016 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-021-storyboard-preview-display-from-synced-manifest` | BR-UC-021-preview-creative.feature:948 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-030-storyboard-binding-used-during-create-media-buy` | BR-UC-030-manage-governance-binding.feature:569 | **C** | NO @source footer — binding is unverifiable |


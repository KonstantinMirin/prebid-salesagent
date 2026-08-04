# Storyboard binding baseline — AdCP 3.1.1

`21` scenarios tagged `@storyboard-v3.1`. Declared specialisms: `sales-non-guaranteed`; protocols: `media-buy`.

Buckets — **A** binding verified · **B** wrong/stale `@source` · **C** tag unjustified (ungraded or undeclared gate) · **D** graded but under-asserted · **E** graded, blocked on production.

| Scenario | Feature:line | Bucket | Findings |
|---|---|---|---|
| `T-UC-002-storyboard-inventory-list-no-match` | BR-UC-002-create-media-buy.feature:2697 | **B** | self-declared storyboard ['inventory_list_no_match'] does not match cited file ['inventory_list_targeting'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-002-storyboard-inventory-list-targeting-parity` | BR-UC-002-create-media-buy.feature:2716 | **A** | — |
| `T-UC-002-storyboard-measurement-terms-rejected` | BR-UC-002-create-media-buy.feature:2731 | **B** | self-declared storyboard ['measurement_terms_rejected'] does not match cited file ['pending_creatives_to_start'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-003-storyboard-media-buy-not-found` | BR-UC-003-update-media-buy.feature:2048 | **A** | — |
| `T-UC-003-storyboard-package-not-found` | BR-UC-003-update-media-buy.feature:2063 | **A** | — |
| `T-UC-003-storyboard-not-cancellable-on-recancel` | BR-UC-003-update-media-buy.feature:2078 | **B** | self-declared storyboard ['invalid_transitions'] does not match cited file ['creative_fate_after_cancellation'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-003-storyboard-creative-fate-after-cancellation` | BR-UC-003-update-media-buy.feature:2094 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | BR-UC-004-deliver-media-buy-metrics.feature:1329 | **A** | — |
| `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | BR-UC-004-deliver-media-buy-metrics.feature:1345 | **B** | self-declared storyboard ['measurement_accountability'] does not match cited file ['vendor_metric_accountability'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-004-storyboard-vendor-metric-end-to-end` | BR-UC-004-deliver-media-buy-metrics.feature:1368 | **C** | NO @source footer — binding is unverifiable |
| `T-UC-005-storyboard-format-id-roundtrip-from-products` | BR-UC-005-discover-creative-formats.feature:1068 | **B** | self-declared storyboard ['list_formats_integrity'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |
| `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope` | BR-UC-005-discover-creative-formats.feature:1086 | **B** | self-declared storyboard ['list_formats_integrity'] does not match cited file ['creative'] — footer points at a storyboard this scenario never claims<br>stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-005-storyboard-baseline-format-id-object-shape` | BR-UC-005-discover-creative-formats.feature:1102 | **A** | — |
| `T-UC-006-storyboard-provenance-required-rejection` | BR-UC-006-sync-creatives.feature:1554 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-provenance-digital-source-type-missing` | BR-UC-006-sync-creatives.feature:1567 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-006-storyboard-provenance-disclosure-missing` | BR-UC-006-sync-creatives.feature:1580 | **A** | — |
| `T-UC-006-storyboard-provenance-corrected-acceptance` | BR-UC-006-sync-creatives.feature:1593 | **A** | — |
| `T-UC-006-storyboard-multi-format-sync` | BR-UC-006-sync-creatives.feature:1627 | **B** | self-declared storyboard ['sync_multiple'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |
| `T-UC-006-storyboard-format-id-roundtrip-on-sync` | BR-UC-006-sync-creatives.feature:1643 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-018-storyboard-list-all-creatives-after-sync` | BR-UC-018-list-creatives.feature:760 | **B** | stale ref 'v3.1-04f59d2d5' — pinned version is 3.1.1 |
| `T-UC-019-storyboard-post-create-status-poll` | BR-UC-019-query-media-buys.feature:1235 | **B** | self-declared storyboard ['check_buy_status'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |


# Storyboard binding baseline — AdCP 3.1.1

`21` scenarios tagged `@storyboard-v3.1`. Declared specialisms: `sales-non-guaranteed`; protocols: `media-buy`.

Buckets — **A** binding verified · **B** wrong/stale `@source` · **C** tag unjustified (ungraded or undeclared gate) · **D** graded but under-asserted · **E** graded, blocked on production.

| Scenario | Feature:line | Bucket | Findings |
|---|---|---|---|
| `T-UC-002-storyboard-inventory-list-no-match` | BR-UC-002-create-media-buy.feature:2698 | **A** | — |
| `T-UC-002-storyboard-inventory-list-targeting-parity` | BR-UC-002-create-media-buy.feature:2717 | **A** | — |
| `T-UC-002-storyboard-measurement-terms-rejected` | BR-UC-002-create-media-buy.feature:2732 | **A** | — |
| `T-UC-003-storyboard-media-buy-not-found` | BR-UC-003-update-media-buy.feature:2048 | **A** | — |
| `T-UC-003-storyboard-package-not-found` | BR-UC-003-update-media-buy.feature:2063 | **A** | — |
| `T-UC-003-storyboard-not-cancellable-on-recancel` | BR-UC-003-update-media-buy.feature:2078 | **A** | — |
| `T-UC-003-storyboard-creative-fate-after-cancellation` | BR-UC-003-update-media-buy.feature:2102 | **A** | — |
| `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | BR-UC-004-deliver-media-buy-metrics.feature:1329 | **A** | — |
| `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | BR-UC-004-deliver-media-buy-metrics.feature:1345 | **A** | — |
| `T-UC-004-storyboard-vendor-metric-end-to-end` | BR-UC-004-deliver-media-buy-metrics.feature:1368 | **A** | — |
| `T-UC-005-storyboard-format-id-roundtrip-from-products` | BR-UC-005-discover-creative-formats.feature:1068 | **B** | self-declared storyboard ['list_formats_integrity'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |
| `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope` | BR-UC-005-discover-creative-formats.feature:1086 | **B** | self-declared storyboard ['list_formats_integrity'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |
| `T-UC-005-storyboard-baseline-format-id-object-shape` | BR-UC-005-discover-creative-formats.feature:1102 | **A** | — |
| `T-UC-006-storyboard-provenance-required-rejection` | BR-UC-006-sync-creatives.feature:1591 | **A** | — |
| `T-UC-006-storyboard-provenance-digital-source-type-missing` | BR-UC-006-sync-creatives.feature:1604 | **A** | — |
| `T-UC-006-storyboard-provenance-disclosure-missing` | BR-UC-006-sync-creatives.feature:1617 | **A** | — |
| `T-UC-006-storyboard-provenance-corrected-acceptance` | BR-UC-006-sync-creatives.feature:1630 | **A** | — |
| `T-UC-006-storyboard-multi-format-sync` | BR-UC-006-sync-creatives.feature:1664 | **B** | self-declared storyboard ['sync_multiple'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |
| `T-UC-006-storyboard-multi-format-sync-status` | BR-UC-006-sync-creatives.feature:1681 | **B** | self-declared storyboard ['sync_multiple'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |
| `T-UC-006-storyboard-format-id-roundtrip-on-sync` | BR-UC-006-sync-creatives.feature:1692 | **A** | — |
| `T-UC-019-storyboard-post-create-status-poll` | BR-UC-019-query-media-buys.feature:1235 | **B** | self-declared storyboard ['check_buy_status'] does not match cited file ['media-buy'] — footer points at a storyboard this scenario never claims |

# Storyboard coverage map — AdCP 3.1.1

Declared protocols: `media-buy` · specialisms: `sales-non-guaranteed`

- storyboards examined: **121**
- on our conformance path: **62**
- **on-path with NO scenario: 52**
- off-path/gated but claimed by a scenario: **0**

## On our conformance path

| Storyboard | Why on path | Covered by |
|---|---|---|
| `protocols/media-buy/index.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` |
| `protocols/media-buy/scenarios/audience_buy_flow.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/billing_finality_delivery.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/canonical_formats.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/create_media_buy_async.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-003-storyboard-creative-fate-after-cancellation` |
| `protocols/media-buy/scenarios/creative_reception.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/delivery_reporting.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` |
| `protocols/media-buy/scenarios/dependency_impairment.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/get_products_async.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/invalid_transitions.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` |
| `protocols/media-buy/scenarios/inventory_list_no_match.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-002-storyboard-inventory-list-no-match` |
| `protocols/media-buy/scenarios/inventory_list_targeting.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-002-storyboard-inventory-list-targeting-parity` |
| `protocols/media-buy/scenarios/measurement_accountability.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` |
| `protocols/media-buy/scenarios/measurement_terms_rejected.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-002-storyboard-measurement-terms-rejected` |
| `protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/performance_buy_flow.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/pricing_currency_filter.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/product_signal_targeting.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/provenance_enforcement.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/reach_buy_flow.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/refine_products.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/vendor_metric_accountability.yaml` | protocol 'media-buy', required_tools advertised | `T-UC-004-storyboard-vendor-metric-end-to-end` |
| `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | protocol 'media-buy', required_tools advertised | **— NOT COVERED —** |
| `specialisms/sales-non-guaranteed/index.yaml` | specialism 'sales-non-guaranteed' declared | **— NOT COVERED —** |
| `universal/billing-gate-dispatch.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/capability-discovery.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/error-compliance-signals.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/error-compliance.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/get-media-buys-pagination-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/get-products-pagination-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/get-signals-pagination-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/idempotency.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/notification-config-event-scope.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/notification-config-lifecycle.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/notification-config-rejections.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/pagination-integrity-creative-formats.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/pagination-integrity-list-accounts.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/pagination-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/read-tool-idempotency.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/schema-validation-signals.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/schema-validation.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/security.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/signed-requests.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/stale-response-advisory.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/v3-envelope-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/version-negotiation.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/webhook-emission.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/webhook-receiver-envelope.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/wholesale-feed-bulk-webhooks.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/wholesale-feed-product-webhooks.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/wholesale-feed-products.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/wholesale-feed-signal-webhooks.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/wholesale-feed-signals.yaml` | universal — applies to every agent | **— NOT COVERED —** |

## Off path or gated, but a scenario claims them

| Storyboard | Why off path | Claimed by |
|---|---|---|

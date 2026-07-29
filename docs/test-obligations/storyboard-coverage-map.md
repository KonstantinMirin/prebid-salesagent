# Storyboard coverage map — AdCP 3.1.1

Declared protocols: `media-buy` · specialisms: `sales-non-guaranteed`

- storyboards examined: **123**
- on our conformance path: **50**
- **on-path with NO scenario: 43**
- off-path/gated but claimed by a scenario: **15**

## On our conformance path

| Storyboard | Why on path | Covered by |
|---|---|---|
| `protocols/media-buy/index.yaml` | protocol 'media-buy' index | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/create_media_buy_async.yaml` | in 'media-buy' requires_scenarios | `T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip` |
| `protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml` | in 'media-buy' requires_scenarios | `T-UC-003-storyboard-creative-fate-after-cancellation`, `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` |
| `protocols/media-buy/scenarios/delivery_reporting.yaml` | in 'media-buy' requires_scenarios | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` |
| `protocols/media-buy/scenarios/dependency_impairment.yaml` | in 'media-buy' requires_scenarios | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | in 'media-buy' requires_scenarios | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/invalid_transitions.yaml` | in 'media-buy' requires_scenarios | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` |
| `protocols/media-buy/scenarios/inventory_list_no_match.yaml` | in 'media-buy' requires_scenarios | `T-UC-002-storyboard-governance-denied`, `T-UC-002-storyboard-governance-denied-recovery`, `T-UC-002-storyboard-inventory-list-no-match` |
| `protocols/media-buy/scenarios/inventory_list_targeting.yaml` | in 'media-buy' requires_scenarios | `T-UC-002-storyboard-governance-denied`, `T-UC-002-storyboard-governance-denied-recovery`, `T-UC-002-storyboard-inventory-list-no-match`, `T-UC-002-storyboard-inventory-list-targeting-parity` |
| `protocols/media-buy/scenarios/measurement_terms_rejected.yaml` | in 'media-buy' requires_scenarios | `T-UC-002-storyboard-governance-denied-recovery`, `T-UC-002-storyboard-inventory-list-no-match`, `T-UC-002-storyboard-inventory-list-targeting-parity`, `T-UC-002-storyboard-measurement-terms-rejected` |
| `protocols/media-buy/scenarios/product_signal_targeting.yaml` | in 'media-buy' requires_scenarios | **— NOT COVERED —** |
| `protocols/media-buy/scenarios/refine_products.yaml` | in 'media-buy' requires_scenarios | **— NOT COVERED —** |
| `specialisms/sales-non-guaranteed/index.yaml` | specialism 'sales-non-guaranteed' declared | **— NOT COVERED —** |
| `universal/billing-gate-dispatch.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/canonical-format-validate-input.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/capability-discovery.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/collection-lists-pagination-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/comply-controller-mode-gate.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/content-standards-pagination-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/deterministic-testing.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/error-compliance-signals.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/error-compliance.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/fictional-entities.yaml` | universal — applies to every agent | **— NOT COVERED —** |
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
| `universal/property-lists-pagination-integrity.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/read-tool-idempotency.yaml` | universal — applies to every agent | **— NOT COVERED —** |
| `universal/runner-output-contract.yaml` | universal — applies to every agent | **— NOT COVERED —** |
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
| `protocols/creative/index.yaml` | protocol 'creative' not declared | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-provenance-claim-contradicted`, `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-018-storyboard-filter-by-format-id-object`, `T-UC-018-storyboard-list-all-creatives-after-sync` |
| `protocols/media-buy/scenarios/creative_reception.yaml` | not in 'media-buy' requires_scenarios | `T-UC-006-storyboard-creative-reception-stateful-render`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-provenance-claim-contradicted` |
| `protocols/media-buy/scenarios/governance_approved.yaml` | not in 'media-buy' requires_scenarios | `T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip`, `T-UC-002-storyboard-governance-approved` |
| `protocols/media-buy/scenarios/governance_conditions.yaml` | not in 'media-buy' requires_scenarios | `T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip`, `T-UC-002-storyboard-governance-approved` |
| `protocols/media-buy/scenarios/governance_denied.yaml` | requires_capability media_buy.governance_aware == true | `T-UC-002-storyboard-governance-approved`, `T-UC-002-storyboard-governance-denied` |
| `protocols/media-buy/scenarios/governance_denied_recovery.yaml` | requires_capability media_buy.governance_aware == true | `T-UC-002-storyboard-governance-approved`, `T-UC-002-storyboard-governance-denied`, `T-UC-002-storyboard-governance-denied-recovery` |
| `protocols/media-buy/scenarios/measurement_accountability.yaml` | not in 'media-buy' requires_scenarios | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance`, `T-UC-004-storyboard-required-metrics-end-to-end-accountability` |
| `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | requires_capability media_buy.creative_approval_mode == auto_approve | `T-UC-002-storyboard-inventory-list-no-match`, `T-UC-002-storyboard-inventory-list-targeting-parity`, `T-UC-002-storyboard-measurement-terms-rejected`, `T-UC-002-storyboard-pending-creatives-state-transition` |
| `protocols/media-buy/scenarios/proposal_finalize.yaml` | requires_capability media_buy.supports_proposals == true | `T-UC-001-storyboard-finalize-uses-refine-vocabulary`, `T-UC-001-storyboard-proposal-finalize-action` |
| `protocols/media-buy/scenarios/provenance_enforcement.yaml` | not in 'media-buy' requires_scenarios | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | not in 'media-buy' requires_scenarios | `T-UC-006-storyboard-provenance-claim-contradicted`, `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `protocols/media-buy/scenarios/vendor_metric_accountability.yaml` | not in 'media-buy' requires_scenarios | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance`, `T-UC-004-storyboard-required-metrics-end-to-end-accountability`, `T-UC-004-storyboard-vendor-metric-end-to-end` |
| `protocols/signals/index.yaml` | protocol 'signals' not declared | `T-UC-008-storyboard-activate-agent-destination`, `T-UC-008-storyboard-baseline-end-to-end` |
| `specialisms/brand-rights/scenarios/governance_denied.yaml` | specialism 'brand-rights' not declared | `T-UC-002-storyboard-governance-approved`, `T-UC-002-storyboard-governance-denied` |
| `specialisms/signal-marketplace/scenarios/governance_denied.yaml` | specialism 'signal-marketplace' not declared | `T-UC-002-storyboard-governance-approved`, `T-UC-002-storyboard-governance-denied` |


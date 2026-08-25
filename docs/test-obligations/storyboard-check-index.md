# Storyboard check index — AdCP 3.1.1

**One row per graded check**, not per storyboard. Generated from `storyboard-checks.jsonl`, which is the source of truth — every table below is a view of those same records, so they cannot disagree. Regenerate both with `scripts/audit/storyboard_check_index.py` (`--jsonl` / `--markdown`).

- checks the pinned spec defines for storyboards on our protocol: **1351** across **68** storyboards
- of those, GRADED (`gate=ON-PATH`): **1143** across **61** storyboards — every metric below is over this set
- GATED, not graded (`gate=GATED`): **208** across **7** storyboards. GATED means the storyboard declares `requires_capability` and the OFFLINE classifier cannot evaluate it — `declared_capabilities()` exposes specialisms and protocols only, so a `media_buy.features.*` path is not expressible. It is not a claim that we lack the capability: the live runner reads the real capability document off the wire and may grade what we gate. These rows are listed, with their reason, in §7.
- claimed by a BDD scenario: **184**
- graded by a LIVE scenario (steps bound + registry-verified harness): **89**
- tracked by an issue: **450**
- **neither scenario nor ticket: 509**
- measured FAILING: **150**
- permanently ungradable (`comply_test_controller`): **482**
- graduation candidates (ledgered, not measured FAILING): **89**

E2E wireability — **451** wireable as-is, **204** conditional on provisioning, **488** not wireable.

**Two grains, both indexed.** The conformance ledger keys on `(storyboard_id, step_id)` and takes `step_id` VERBATIM from the real `@adcp/sdk` runner, which this repo does not control. The pinned tree grades a step two ways: by a literal `check:` line (owned by the innermost enclosing step) and by an assertion TASK — `expect_webhook` and friends — whose step declares no `check:` of its own and whose failure the runner attributes to the step named in its `triggered_by`. Both now produce rows here (`storyboard_spec.checks_by_owner` and `graded_steps_by_task`), so the `measured` join resolves: every ledger entry lands on a record except `signed_requests`' runtime-generated `negative-NNN` steps (built from vector fixtures, as the pinned file states) and the `agent_reachability` runner-level synthetic, neither of which is a spec check. Before this, seven `universal/webhook-emission.yaml` entries resolved to nothing and a check reading `no ledger entry` was not evidence it passed.

Scenario coverage is declared per STORYBOARD (`@storyboard-v3.1` tags a scenario to a storyboard, not to a check), so a scenario shown against a check means "this check's storyboard is claimed" — not that this check is asserted. That distinction is the whole reason for indexing at this grain, and the whole reason **claimed by a BDD scenario** and **graded by a LIVE scenario** are reported as two separate numbers rather than one: claimed only asks whether a scenario's tag names this storyboard; graded additionally requires, from a real `pytest tests/bdd` run, that every one of that scenario's steps has a bound step definition AND that its harness routing resolves to a non-placeholder row in the declarative `ENV_ROUTES` registry — a data lookup, never reason-text matching. A claim with no live scenario behind it is a dormant claim, not coverage.

## 1. Measured status

| Check | Status | Protocols failing |
|---|---|---|
| `media_buy_seller/audience_buy_flow/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/audience_buy_flow/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/audience_buy_flow/get_products_for_audience/response_schema` | ungradable | — |
| `media_buy_seller/audience_buy_flow/get_products_for_audience/field_present` | ungradable | — |
| `media_buy_seller/audience_buy_flow/sync_audience/response_schema` | ungradable | — |
| `media_buy_seller/audience_buy_flow/sync_audience/field_present` | ungradable | — |
| `media_buy_seller/audience_buy_flow/sync_audience/field_present#1` | ungradable | — |
| `media_buy_seller/audience_buy_flow/sync_audience/upstream_traffic` | ungradable | — |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_audience/response_schema` | ungradable | — |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_audience/field_present` | ungradable | — |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_phantom_audience/error_code` | ungradable | — |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_phantom_audience/field_value` | ungradable | — |
| `media_buy_seller/audience_buy_flow/simulate_audience_delivery/field_value` | ungradable | — |
| `media_buy_seller/audience_buy_flow/get_audience_delivery/response_schema` | ungradable | — |
| `media_buy_seller/audience_buy_flow/get_audience_delivery/field_present` | ungradable | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/response_schema` | gated | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_value` | gated | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains` | gated | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#1` | gated | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#2` | gated | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#3` | gated | — |
| `media_buy_seller/available_actions/sync_available_actions_creative/response_schema` | gated | — |
| `media_buy_seller/available_actions/sync_available_actions_creative/field_value` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/response_schema` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present#1` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_value` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_value#1` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains#1` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains#2` | gated | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present#2` | gated | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/response_schema` | gated | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value` | gated | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value#1` | gated | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains` | gated | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains#1` | gated | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains#2` | gated | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value#2` | gated | — |
| `media_buy_seller/available_actions/increase_budget/response_schema` | gated | — |
| `media_buy_seller/available_actions/increase_budget/field_value` | gated | — |
| `media_buy_seller/available_actions/increase_budget/field_present` | gated | — |
| `media_buy_seller/available_actions/increase_budget/field_contains` | gated | — |
| `media_buy_seller/available_actions/increase_budget/field_contains#1` | gated | — |
| `media_buy_seller/available_actions/increase_budget/field_value#1` | gated | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/error_code` | gated | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value` | gated | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#1` | gated | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#2` | gated | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_contains` | gated | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#3` | gated | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/error_code` | gated | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value` | gated | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#1` | gated | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#2` | gated | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_contains` | gated | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#3` | gated | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/error_code` | gated | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value` | gated | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#1` | gated | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#2` | gated | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_contains` | gated | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#3` | gated | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/error_code` | gated | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value` | gated | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#1` | gated | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#2` | gated | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_contains` | gated | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#3` | gated | — |
| `media_buy_seller/billing_finality_delivery/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/create_media_buy/response_schema` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/create_media_buy/field_present` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/simulate_provisional_delivery/field_value` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/response_schema` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_absent` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value#1` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value#2` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_absent#1` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/simulate_final_delivery/field_value` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/response_schema` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_present` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value#1` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value#2` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/report_final_usage/response_schema` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/report_final_usage/field_value` | ungradable | — |
| `media_buy_seller/billing_finality_delivery/report_final_usage/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/response_schema` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#2` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#3` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#4` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#5` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#6` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#7` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#8` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#9` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#10` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/refs_resolve` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_present` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#11` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/response_schema` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value#2` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_absent` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#2` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#3` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#4` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_absent` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#2` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#3` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#4` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#5` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#6` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/response_schema` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#2` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#3` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/refs_resolve` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/response_schema` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value#2` | ungradable | — |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/response_schema` | ungradable | — |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value` | ungradable | — |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value#1` | ungradable | — |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value#2` | ungradable | — |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/response_schema` | ungradable | — |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/field_present` | ungradable | — |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/canonical_format_satisfaction` | ungradable | — |
| `media_buy_seller/canonical_formats/reject_bare_image_selector_for_fixed_mrec/error_code` | ungradable | — |
| `media_buy_seller/canonical_formats/reject_bare_image_selector_for_fixed_mrec/canonical_format_satisfaction` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/get_products_for_clicks/response_schema` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/get_products_for_clicks/field_present` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/create_media_buy_clicks/response_schema` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/create_media_buy_clicks/field_present` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/simulate_clicks_delivery/field_value` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/response_schema` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/field_present` | ungradable | — |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/get_products_for_cpcv/response_schema` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/get_products_for_cpcv/field_present` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_cpcv/response_schema` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_cpcv/field_present` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_with_phantom_view_duration/error_code` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_with_phantom_view_duration/field_value` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/simulate_cpcv_delivery/field_value` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/response_schema` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/field_present` | ungradable | — |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value` | ungradable | — |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value#1` | ungradable | — |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_present` | ungradable | — |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_present#1` | ungradable | — |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value#2` | ungradable | — |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/response_schema` | ungradable | — |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value` | ungradable | — |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_present` | ungradable | — |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value#1` | ungradable | — |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_present#1` | ungradable | — |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value#2` | ungradable | — |
| `media_buy_seller/delivery_reporting/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/delivery_reporting/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_products_brief/response_schema` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_products_brief/field_present` | ungradable | — |
| `media_buy_seller/delivery_reporting/create_media_buy/response_schema` | ungradable | — |
| `media_buy_seller/delivery_reporting/simulate_delivery/field_value` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_delivery/response_schema` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_delivery/field_present` | ungradable | — |
| `media_buy_seller/delivery_reporting/create_media_buy_viewability/response_schema` | ungradable | — |
| `media_buy_seller/delivery_reporting/create_media_buy_viewability/field_present` | ungradable | — |
| `media_buy_seller/delivery_reporting/simulate_viewability_delivery/field_value` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/response_schema` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#2` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#3` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#4` | ungradable | — |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#5` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_products_brief/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_products_brief/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_products_brief/field_present#1` | ungradable | — |
| `media_buy_seller/dependency_impairment/create_buy/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/create_buy/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment/create_buy/field_present#1` | ungradable | — |
| `media_buy_seller/dependency_impairment/sync_creative/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/sync_creative/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/field_contains` | ungradable | — |
| `media_buy_seller/dependency_impairment/force_creative_approved/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/force_creative_approved/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_baseline/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value#1` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value_or_absent` | ungradable | — |
| `media_buy_seller/dependency_impairment/force_creative_rejected/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/force_creative_rejected/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/field_value#1` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_impaired/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_contains` | ungradable | — |
| `media_buy_seller/dependency_impairment/sync_replacement_creative/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/sync_replacement_creative/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment/force_replacement_approved/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/force_replacement_approved/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment/swap_assignment/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/swap_assignment/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment/swap_assignment/field_contains` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_recovered/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_recovered/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment/get_buy_recovered/field_value_or_absent` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/field_present#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present#2` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/field_present#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_contains` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_contains#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_both_approved/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_both_approved/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_b_approved/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_b_approved/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/field_value_or_absent` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_a_rejected/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_a_rejected/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/field_value#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value#2` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_b_rejected/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_b_rejected/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/field_value#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_present#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_c/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_c/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_c_approved/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_c_approved/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/field_contains` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value#1` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value_or_absent` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_d/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_d/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_d_approved/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/force_d_approved/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/field_present` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/field_contains` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/response_schema` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/field_value` | ungradable | — |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/field_value_or_absent` | ungradable | — |
| `media_buy_seller/event_dedup_flow/sync_accounts/response_schema` | gated | — |
| `media_buy_seller/event_dedup_flow/sync_accounts/field_present` | gated | — |
| `media_buy_seller/event_dedup_flow/get_products_for_dedup/response_schema` | gated | — |
| `media_buy_seller/event_dedup_flow/get_products_for_dedup/field_present` | gated | — |
| `media_buy_seller/event_dedup_flow/sync_event_sources/response_schema` | gated | — |
| `media_buy_seller/event_dedup_flow/sync_event_sources/field_present` | gated | — |
| `media_buy_seller/event_dedup_flow/sync_event_sources/field_present#1` | gated | — |
| `media_buy_seller/event_dedup_flow/create_media_buy_dedup/response_schema` | gated | — |
| `media_buy_seller/event_dedup_flow/create_media_buy_dedup/field_present` | gated | — |
| `media_buy_seller/event_dedup_flow/log_event_from_pixel/response_schema` | gated | — |
| `media_buy_seller/event_dedup_flow/log_event_from_capi/response_schema` | gated | — |
| `media_buy_seller/event_dedup_flow/simulate_deduplicated_delivery/field_value` | gated | — |
| `media_buy_seller/event_dedup_flow/get_dedup_delivery/response_schema` | gated | — |
| `media_buy_seller/event_dedup_flow/get_dedup_delivery/field_value` | gated | — |
| `media_buy_seller/frequency_cap_enforcement/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/get_products_for_frequency_cap/response_schema` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/get_products_for_frequency_cap/field_present` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/create_media_buy_with_frequency_cap/response_schema` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/create_media_buy_with_frequency_cap/field_present` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/simulate_capped_delivery/field_value` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/response_schema` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_present` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_less_than` | ungradable | — |
| `media_buy_seller/get_products_async/force_get_products_submitted/response_schema` | ungradable | — |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value` | ungradable | — |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value#1` | ungradable | — |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value#2` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_submitted/response_schema` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_submitted/field_value` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_submitted/field_value#1` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent#1` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent#2` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/response_schema` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/field_value` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/field_value#1` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/field_value#2` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/field_value#3` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/field_value#4` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/field_value#5` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task/field_value#6` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/response_schema` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/field_value` | ungradable | — |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/field_value#1` | ungradable | — |
| `media_buy_seller/get_products_async/complete_products_task/response_schema` | ungradable | — |
| `media_buy_seller/get_products_async/complete_products_task/field_value` | ungradable | — |
| `media_buy_seller/get_products_async/complete_products_task/field_value#1` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_wrong_account/error_code` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/response_schema` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#1` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#2` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#3` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#4` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#5` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#6` | ungradable | — |
| `media_buy_seller/get_products_async/get_products_submitted/expect_webhook` | ungradable | — |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_present` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_value#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present#2` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_present` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_present#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_value#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_equals_context` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_equals_context#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_contains` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_present` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_present#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_present` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_present#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_value#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_equals_context` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_equals_context#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_contains` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_equals_context` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_equals_context#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_value#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/response_schema` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_equals_context` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_equals_context#1` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_value` | gated | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_value#1` | gated | — |
| `media_buy_seller/measurement_accountability/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/measurement_accountability/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/response_schema` | ungradable | — |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present` | ungradable | — |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present#1` | ungradable | — |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present#2` | ungradable | — |
| `media_buy_seller/measurement_accountability/create_media_buy/response_schema` | ungradable | — |
| `media_buy_seller/measurement_accountability/create_media_buy/field_present` | ungradable | — |
| `media_buy_seller/measurement_accountability/simulate_delivery/field_value` | ungradable | — |
| `media_buy_seller/measurement_accountability/get_delivery_clean/response_schema` | ungradable | — |
| `media_buy_seller/measurement_accountability/get_delivery_clean/field_value_or_absent` | ungradable | — |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/response_schema` | gated | — |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/field_present` | gated | — |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/field_present#1` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/response_schema` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_present` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#1` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_present#1` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#2` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_equals_context` | gated | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#3` | gated | — |
| `media_buy_seller/pending_creatives_to_start/sync_creative/response_schema` | gated | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/response_schema` | gated | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_present` | gated | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_contains` | gated | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_value` | gated | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_value#1` | gated | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/response_schema` | gated | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_value` | gated | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_equals_context` | gated | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_value#1` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_accounts/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_accounts/field_present` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/get_products_for_per_creative/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/get_products_for_per_creative/field_present` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/field_present` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/upstream_traffic` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/field_present` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/field_present#1` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/create_media_buy_two_creatives/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/create_media_buy_two_creatives/field_present` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/log_purchase_event_1/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/log_purchase_event_2/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/simulate_per_creative_delivery/field_value` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/response_schema` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#1` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#2` | gated | — |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#3` | gated | — |
| `media_buy_seller/performance_buy_flow/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow/get_products_for_performance/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow/get_products_for_performance/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow/sync_event_sources/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow/sync_event_sources/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow/sync_event_sources/field_present#1` | ungradable | — |
| `media_buy_seller/performance_buy_flow/create_media_buy_cpa/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow/create_media_buy_cpa/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow/create_media_buy_with_phantom_source/error_code` | ungradable | — |
| `media_buy_seller/performance_buy_flow/create_media_buy_with_phantom_source/field_value` | ungradable | — |
| `media_buy_seller/performance_buy_flow/log_purchase_event/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow/log_purchase_event/upstream_traffic` | ungradable | — |
| `media_buy_seller/performance_buy_flow/simulate_performance_delivery/field_value` | ungradable | — |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/get_products_for_roas/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/get_products_for_roas/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/field_present#1` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/upstream_traffic` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_roas/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_roas/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_per_ad_spend_no_value_field/error_code` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_per_ad_spend_no_value_field/field_value` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/log_purchase_event/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/log_purchase_event/upstream_traffic` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/simulate_roas_delivery/field_value` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/response_schema` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#2` | ungradable | — |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#3` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/response_schema` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_present` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#1` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#2` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_absent` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_absent#1` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_present#1` | ungradable | — |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#3` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/response_schema` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_value` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present#1` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present#2` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_value#1` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/response_schema` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#1` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#2` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#3` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_value` | ungradable | — |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/response_schema` | ungradable | — |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/field_present` | ungradable | — |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/field_present#1` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_after_create/response_schema` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value#1` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value#2` | ungradable | — |
| `media_buy_seller/product_signal_targeting/get_after_create/field_present` | ungradable | — |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_unknown_signal/error_code` | ungradable | — |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_unknown_signal/field_value` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/response_schema` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/field_present` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/field_value` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/response_schema` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_absent` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value#1` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_absent#1` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value#2` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/upstream_traffic` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/upstream_traffic#1` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/response_schema` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#1` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#2` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#3` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/response_schema` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#1` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#2` | ungradable | — |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#3` | ungradable | — |
| `media_buy_seller/reach_buy_flow/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_products_for_reach/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_products_for_reach/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_with_unsupported_reach_unit/error_code` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_with_unsupported_reach_unit/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/simulate_reach_delivery/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_cumulative_reach/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_cumulative_reach/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/simulate_cumulative_reach/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_period_reach/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_period_reach/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/simulate_period_reach/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_rolling_reach/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_rolling_reach/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/simulate_rolling_reach/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_present#1` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach_no_window/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach_no_window/field_present` | ungradable | — |
| `media_buy_seller/reach_buy_flow/simulate_reach_no_window/field_value` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_delivery_reach_no_window/response_schema` | ungradable | — |
| `media_buy_seller/reach_buy_flow/get_delivery_reach_no_window/field_present` | ungradable | — |
| `media_buy_seller/refine_finalize_exclusivity/sync_accounts/response_schema` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/sync_accounts/field_present` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief/response_schema` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief/field_present` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief_second/field_present` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_mixed_finalize/error_code` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_mixed_finalize/field_present` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_product_finalize/error_code` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/response_schema` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_present` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_contains` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_contains#1` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#1` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#2` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#3` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_unsupported/error_code` | gated | — |
| `media_buy_seller/refine_finalize_exclusivity/assert_multi_finalize/any_of` | gated | — |
| `media_buy_seller/vendor_metric_accountability/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#1` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#2` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#3` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#4` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/create_media_buy/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/create_media_buy/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/simulate_delivery_with_vendor_metrics/field_value` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#1` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#2` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#3` | ungradable | — |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#4` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_value` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_value#1` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_accept/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_accept/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_reject/error_code` | ungradable | — |
| `media_buy_seller/vendor_metric_catalog_precondition/assert_vendor_metric_catalog_miss_handled/any_of` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/sync_accounts/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/sync_accounts/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present#1` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present#2` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value#1` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value#2` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_positive/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_positive/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_targetless_positive/response_schema` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_targetless_positive/field_present` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_metric/error_code` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_metric/field_value` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_target/error_code` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_target/field_value` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_missing_committed/error_code` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_missing_committed/field_value` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unreportable_metric/error_code` | ungradable | — |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unreportable_metric/field_value` | ungradable | — |
| `media_buy_state_machine/get_capabilities/response_schema` | gated | — |
| `media_buy_state_machine/get_capabilities/field_present` | gated | — |
| `media_buy_state_machine/get_capabilities/field_present#1` | gated | — |
| `media_buy_state_machine/get_capabilities/field_value` | gated | — |
| `media_buy_state_machine/discover_products/response_schema` | gated | — |
| `media_buy_state_machine/discover_products/field_present` | gated | — |
| `media_buy_state_machine/discover_products/field_present#1` | gated | — |
| `media_buy_state_machine/discover_products/field_value` | gated | — |
| `media_buy_state_machine/discover_products/field_present#2` | gated | — |
| `media_buy_state_machine/discover_products/field_present#3` | gated | — |
| `media_buy_state_machine/discover_products/field_present#4` | gated | — |
| `media_buy_state_machine/sync_creative/response_schema` | gated | — |
| `media_buy_state_machine/sync_creative/field_present` | gated | — |
| `media_buy_state_machine/sync_creative/field_value` | gated | — |
| `media_buy_state_machine/create_buy/response_schema` | gated | — |
| `media_buy_state_machine/create_buy/field_present` | gated | — |
| `media_buy_state_machine/create_buy/field_value` | gated | — |
| `media_buy_state_machine/create_buy/field_present#1` | gated | — |
| `media_buy_state_machine/create_buy/field_value#1` | gated | — |
| `media_buy_state_machine/create_buy/field_present#2` | gated | — |
| `media_buy_state_machine/pause_buy/field_present` | gated | — |
| `media_buy_state_machine/pause_buy/field_present#1` | gated | — |
| `media_buy_state_machine/pause_buy/field_value` | gated | — |
| `media_buy_state_machine/resume_buy/field_present` | gated | — |
| `media_buy_state_machine/resume_buy/field_present#1` | gated | — |
| `media_buy_state_machine/resume_buy/field_value` | gated | — |
| `media_buy_state_machine/cancel_buy/field_present` | gated | — |
| `media_buy_state_machine/cancel_buy/field_present#1` | gated | — |
| `media_buy_state_machine/cancel_buy/field_value` | gated | — |
| `media_buy_state_machine/pause_canceled_buy/error_code` | gated | — |
| `media_buy_state_machine/pause_canceled_buy/field_present` | gated | — |
| `media_buy_state_machine/pause_canceled_buy/field_value` | gated | — |
| `media_buy_state_machine/resume_canceled_buy/error_code` | gated | — |
| `media_buy_state_machine/resume_canceled_buy/field_present` | gated | — |
| `media_buy_state_machine/resume_canceled_buy/field_value` | gated | — |
| `media_buy_state_machine/recancel_buy/error_code` | gated | — |
| `media_buy_state_machine/recancel_buy/field_present` | gated | — |
| `media_buy_state_machine/recancel_buy/field_value` | gated | — |
| `billing_gate_dispatch/get_capabilities/response_schema` | FAILING | `mcp` |
| `billing_gate_dispatch/get_capabilities/field_present` | FAILING | `mcp` |
| `billing_gate_dispatch/get_capabilities/field_present#1` | FAILING | `mcp` |
| `billing_gate_dispatch/get_capabilities/field_value` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/response_schema` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#1` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#2` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#3` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#4` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_present` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#1` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#2` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#3` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#4` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#5` | FAILING | `mcp` |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#5` | FAILING | `mcp` |
| `capability_discovery/get_capabilities/response_schema` | FAILING | `mcp` |
| `capability_discovery/get_capabilities/field_present` | FAILING | `mcp` |
| `capability_discovery/get_capabilities/field_present#1` | FAILING | `mcp` |
| `capability_discovery/get_capabilities/field_present#2` | FAILING | `mcp` |
| `capability_discovery/get_capabilities/field_value` | FAILING | `mcp` |
| `capability_discovery/get_capabilities_filtered/response_schema` | FAILING | `mcp` |
| `capability_discovery/get_capabilities_filtered/field_present` | FAILING | `mcp` |
| `capability_discovery/get_capabilities_filtered/field_value` | FAILING | `mcp` |
| `error_compliance/get_capabilities/response_schema` | FAILING | `mcp` |
| `error_compliance/get_capabilities/field_present` | FAILING | `mcp` |
| `error_compliance/get_capabilities/field_present#1` | FAILING | `mcp` |
| `error_compliance/get_capabilities/field_value` | FAILING | `mcp` |
| `error_compliance/nonexistent_product/error_code` | FAILING | `mcp` |
| `error_compliance/nonexistent_product/field_present` | FAILING | `mcp` |
| `error_compliance/nonexistent_product/field_value` | FAILING | `mcp` |
| `error_compliance/missing_fields/response_schema` | FAILING | `mcp` |
| `error_compliance/missing_fields/field_present` | FAILING | `mcp` |
| `error_compliance/missing_fields/field_value` | FAILING | `mcp` |
| `error_compliance/reversed_dates_error/error_code` | FAILING | `mcp` |
| `error_compliance/reversed_dates_error/field_present` | FAILING | `mcp` |
| `error_compliance/reversed_dates_error/field_value` | FAILING | `mcp` |
| `error_compliance/unsupported_major_version/error_code` | FAILING | `mcp` |
| `error_compliance/unsupported_major_version/field_present` | FAILING | `mcp` |
| `error_compliance/unsupported_major_version/field_value` | FAILING | `mcp` |
| `error_compliance/unsupported_release_version/error_code` | FAILING | `mcp` |
| `error_compliance/unsupported_release_version/field_present` | FAILING | `mcp` |
| `error_compliance/unsupported_release_version/field_value` | FAILING | `mcp` |
| `error_compliance/supported_major_version/response_schema` | FAILING | `mcp` |
| `error_compliance/supported_major_version/field_present` | FAILING | `mcp` |
| `error_compliance/supported_major_version/field_value` | FAILING | `mcp` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/response_schema` | FAILING | `mcp` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value` | FAILING | `mcp` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#1` | FAILING | `mcp` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#2` | FAILING | `mcp` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#3` | FAILING | `mcp` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#4` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/response_schema` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_present` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#1` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#2` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#3` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#4` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_absent` | FAILING | `mcp` |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#5` | FAILING | `mcp` |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/response_schema` | FAILING | `mcp` |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value` | FAILING | `mcp` |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#1` | FAILING | `mcp` |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#2` | FAILING | `mcp` |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#3` | FAILING | `mcp` |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#4` | FAILING | `mcp` |
| `pagination_integrity_creative_formats/seed_format_1/field_value` | ungradable | — |
| `pagination_integrity_creative_formats/seed_format_2/field_value` | ungradable | — |
| `pagination_integrity_list_accounts/seed_account_1/field_value` | ungradable | — |
| `pagination_integrity_list_accounts/seed_account_2/field_value` | ungradable | — |
| `pagination_integrity_list_accounts/seed_account_3/field_value` | ungradable | — |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/response_schema` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/field_present` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/field_present#1` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/field_value` | FAILING | `mcp` |
| `read_tool_idempotency/get_products_with_idempotency_key/response_schema` | FAILING | `mcp` |
| `read_tool_idempotency/get_products_with_idempotency_key/field_present` | FAILING | `mcp` |
| `read_tool_idempotency/get_products_with_idempotency_key/field_present#1` | FAILING | `mcp` |
| `read_tool_idempotency/get_products_with_idempotency_key/field_value` | FAILING | `mcp` |
| `read_tool_idempotency/list_accounts_with_idempotency_key/response_schema` | FAILING | `mcp` |
| `read_tool_idempotency/list_accounts_with_idempotency_key/field_present` | FAILING | `mcp` |
| `read_tool_idempotency/list_accounts_with_idempotency_key/field_present#1` | FAILING | `mcp` |
| `read_tool_idempotency/list_accounts_with_idempotency_key/field_value` | FAILING | `mcp` |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/response_schema` | FAILING | `mcp` |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/field_present` | FAILING | `mcp` |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/field_present#1` | FAILING | `mcp` |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/field_value` | FAILING | `mcp` |
| `read_tool_idempotency/list_creatives_with_idempotency_key/response_schema` | FAILING | `mcp` |
| `read_tool_idempotency/list_creatives_with_idempotency_key/field_present` | FAILING | `mcp` |
| `read_tool_idempotency/list_creatives_with_idempotency_key/field_present#1` | FAILING | `mcp` |
| `read_tool_idempotency/list_creatives_with_idempotency_key/field_value` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_accept/response_schema` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_accept/field_present` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_accept/field_value` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_reject/error_code` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_reject/field_present` | FAILING | `mcp` |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_reject/field_value` | FAILING | `mcp` |
| `read_tool_idempotency/assert_omitted_key_grace_handled/any_of` | FAILING | `mcp` |
| `security_baseline/probe_unauth/http_status_in` | FAILING | `mcp` |
| `security_baseline/probe_unauth/on_401_require_header` | FAILING | `mcp` |
| `security_baseline/assert_mechanism/any_of` | FAILING | `mcp` |
| `signed_requests/get_capabilities/field_present` | FAILING | `mcp` |
| `signed_requests/get_capabilities/field_value` | FAILING | `mcp` |
| `stale_response_advisory/get_capabilities/response_schema` | FAILING | `mcp` |
| `stale_response_advisory/get_capabilities/field_present` | FAILING | `mcp` |
| `stale_response_advisory/get_capabilities/field_present#1` | FAILING | `mcp` |
| `stale_response_advisory/get_capabilities/field_value` | FAILING | `mcp` |
| `stale_response_advisory/force_upstream_unavailable/response_schema` | ungradable | — |
| `stale_response_advisory/force_upstream_unavailable/field_present` | ungradable | — |
| `stale_response_advisory/force_upstream_unavailable/field_value` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/response_schema` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/field_present` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/field_value` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/field_value#1` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/field_present#1` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/field_present#2` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/field_value#2` | ungradable | — |
| `stale_response_advisory/stale_response_wire_placement/field_present#3` | ungradable | — |
| `stale_response_advisory/no_stale_on_healthy_upstream/response_schema` | FAILING | `mcp` |
| `stale_response_advisory/no_stale_on_healthy_upstream/field_present` | FAILING | `mcp` |
| `stale_response_advisory/no_stale_on_healthy_upstream/field_value` | FAILING | `mcp` |
| `v3_envelope_integrity/no_legacy_status_fields/response_schema` | FAILING | `mcp` |
| `v3_envelope_integrity/no_legacy_status_fields/envelope_field_present` | FAILING | `mcp` |
| `v3_envelope_integrity/no_legacy_status_fields/envelope_field_absent` | FAILING | `mcp` |
| `v3_envelope_integrity/no_legacy_status_fields/envelope_field_absent#1` | FAILING | `mcp` |
| `v3_envelope_integrity/no_legacy_status_fields/field_present` | FAILING | `mcp` |
| `v3_envelope_integrity/no_legacy_status_fields/field_value` | FAILING | `mcp` |
| `version_negotiation/get_capabilities_with_version/response_schema` | FAILING | `mcp` |
| `version_negotiation/get_capabilities_with_version/field_present` | FAILING | `mcp` |
| `version_negotiation/get_capabilities_with_version/field_present#1` | FAILING | `mcp` |
| `version_negotiation/get_capabilities_with_version/envelope_field_present` | FAILING | `mcp` |
| `version_negotiation/get_capabilities_with_version/envelope_field_pattern` | FAILING | `mcp` |
| `version_negotiation/get_capabilities_with_version/field_present#2` | FAILING | `mcp` |
| `version_negotiation/get_capabilities_with_version/field_value` | FAILING | `mcp` |
| `webhook_emission/get_capabilities/field_present` | FAILING | `mcp` |
| `webhook_emission/trigger_webhook_operation/expect_webhook` | FAILING | `mcp` |
| `webhook_emission/trigger_operation_id_echo/expect_webhook` | FAILING | `mcp` |
| `webhook_emission/trigger_idempotent_webhook_initial/expect_webhook` | FAILING | `mcp` |
| `webhook_emission/trigger_retry_scenario/expect_webhook_retry_keys_stable` | FAILING | `mcp` |
| `webhook_emission/fetch_brand_json/fetch_brand_jwks` | FAILING | `mcp` |
| `webhook_emission/assert_webhook_signing_key_present/assert_jwks_purpose` | FAILING | `mcp` |
| `webhook_emission/trigger_signed_webhook/expect_webhook_signature_valid` | FAILING | `mcp` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/response_schema` | FAILING | `mcp` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value` | FAILING | `mcp` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value#1` | FAILING | `mcp` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value#2` | FAILING | `mcp` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value#3` | FAILING | `mcp` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/response_schema` | FAILING | `mcp` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value` | FAILING | `mcp` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value#1` | FAILING | `mcp` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value#2` | FAILING | `mcp` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value#3` | FAILING | `mcp` |
| `wholesale_feed_products/bootstrap_products/response_schema` | FAILING | `mcp` |
| `wholesale_feed_products/bootstrap_products/field_present` | FAILING | `mcp` |
| `wholesale_feed_products/bootstrap_products/field_present#1` | FAILING | `mcp` |
| `wholesale_feed_products/bootstrap_products/field_value` | FAILING | `mcp` |
| `wholesale_feed_products/bootstrap_products/field_absent` | FAILING | `mcp` |
| `wholesale_feed_products/bootstrap_products/field_value#1` | FAILING | `mcp` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/response_schema` | FAILING | `mcp` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value` | FAILING | `mcp` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value#1` | FAILING | `mcp` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value#2` | FAILING | `mcp` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value#3` | FAILING | `mcp` |

## 2. Tracking

Checks whose storyboard carries an issue. `coverage` is the map's own assessment of how much of the storyboard that issue covers.

| Check | Issue(s) | Coverage |
|---|---|---|
| `media_buy_seller/audience_buy_flow/sync_accounts/response_schema` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/sync_accounts/field_present` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/get_products_for_audience/response_schema` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/get_products_for_audience/field_present` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/sync_audience/response_schema` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/sync_audience/field_present` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/sync_audience/field_present#1` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/sync_audience/upstream_traffic` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_audience/response_schema` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_audience/field_present` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_phantom_audience/error_code` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_phantom_audience/field_value` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/simulate_audience_delivery/field_value` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/get_audience_delivery/response_schema` | #1059 | partial |
| `media_buy_seller/audience_buy_flow/get_audience_delivery/field_present` | #1059 | partial |
| `media_buy_seller/billing_finality_delivery/sync_accounts/response_schema` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/sync_accounts/field_present` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/create_media_buy/response_schema` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/create_media_buy/field_present` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/simulate_provisional_delivery/field_value` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/response_schema` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_absent` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value#1` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value#2` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_absent#1` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/simulate_final_delivery/field_value` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/response_schema` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_present` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value#1` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_present#1` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value#2` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/report_final_usage/response_schema` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/report_final_usage/field_value` | #1772 | partial |
| `media_buy_seller/billing_finality_delivery/report_final_usage/field_value#1` | #1772 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/response_schema` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#1` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#2` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#3` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#4` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#5` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#6` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#7` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#8` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#9` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#10` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/refs_resolve` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_present` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#11` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/response_schema` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value#1` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value#2` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_absent` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#1` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#2` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#3` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#4` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_absent` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#1` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#2` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#3` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#4` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#5` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#6` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/response_schema` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#1` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#2` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#3` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/refs_resolve` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/response_schema` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value#1` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value#2` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/response_schema` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value#1` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value#2` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/response_schema` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/field_present` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/canonical_format_satisfaction` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/reject_bare_image_selector_for_fixed_mrec/error_code` | #1789, #1172 | partial |
| `media_buy_seller/canonical_formats/reject_bare_image_selector_for_fixed_mrec/canonical_format_satisfaction` | #1789, #1172 | partial |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value#1` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_present` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_present#1` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value#2` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/response_schema` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_present` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value#1` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_present#1` | #1305, #1531 | partial |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value#2` | #1305, #1531 | partial |
| `media_buy_seller/get_products_async/force_get_products_submitted/response_schema` | #1305 | partial |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value` | #1305 | partial |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value#1` | #1305 | partial |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value#2` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_submitted/response_schema` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_submitted/field_value` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_submitted/field_value#1` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent#1` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent#2` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/response_schema` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/field_value` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/field_value#1` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/field_value#2` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/field_value#3` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/field_value#4` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/field_value#5` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task/field_value#6` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/response_schema` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/field_value` | #1305 | partial |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/field_value#1` | #1305 | partial |
| `media_buy_seller/get_products_async/complete_products_task/response_schema` | #1305 | partial |
| `media_buy_seller/get_products_async/complete_products_task/field_value` | #1305 | partial |
| `media_buy_seller/get_products_async/complete_products_task/field_value#1` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_wrong_account/error_code` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/response_schema` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#1` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#2` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#3` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#4` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#5` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#6` | #1305 | partial |
| `media_buy_seller/get_products_async/get_products_submitted/expect_webhook` | #1305 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/response_schema` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_present` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#1` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#2` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_absent` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_absent#1` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_present#1` | #1525 | partial |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#3` | #1525 | partial |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/response_schema` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_value` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present#1` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present#2` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_value#1` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/response_schema` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#1` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#2` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#3` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_value` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/response_schema` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/field_present` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/field_present#1` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_after_create/response_schema` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value#1` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value#2` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/get_after_create/field_present` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_unknown_signal/error_code` | #1593, #1783 | partial |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_unknown_signal/field_value` | #1593, #1783 | partial |
| `billing_gate_dispatch/get_capabilities/response_schema` | #1772 | partial |
| `billing_gate_dispatch/get_capabilities/field_present` | #1772 | partial |
| `billing_gate_dispatch/get_capabilities/field_present#1` | #1772 | partial |
| `billing_gate_dispatch/get_capabilities/field_value` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/response_schema` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#1` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#2` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#3` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#4` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_present` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#5` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/response_schema` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#1` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#2` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#3` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#4` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_present` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#1` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#2` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#3` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#4` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#5` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#5` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/response_schema` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/field_present` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/field_value` | #1772 | partial |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/field_value#1` | #1772 | partial |
| `capability_discovery/get_capabilities/response_schema` | #1825, #1684, #1408, #1525, #1724 | partial |
| `capability_discovery/get_capabilities/field_present` | #1825, #1684, #1408, #1525, #1724 | partial |
| `capability_discovery/get_capabilities/field_present#1` | #1825, #1684, #1408, #1525, #1724 | partial |
| `capability_discovery/get_capabilities/field_present#2` | #1825, #1684, #1408, #1525, #1724 | partial |
| `capability_discovery/get_capabilities/field_value` | #1825, #1684, #1408, #1525, #1724 | partial |
| `capability_discovery/get_capabilities_filtered/response_schema` | #1825, #1684, #1408, #1525, #1724 | partial |
| `capability_discovery/get_capabilities_filtered/field_present` | #1825, #1684, #1408, #1525, #1724 | partial |
| `capability_discovery/get_capabilities_filtered/field_value` | #1825, #1684, #1408, #1525, #1724 | partial |
| `error_compliance_signals/get_capabilities/response_schema` | #1604, #1680 | partial |
| `error_compliance_signals/get_capabilities/field_present` | #1604, #1680 | partial |
| `error_compliance_signals/get_capabilities/field_present#1` | #1604, #1680 | partial |
| `error_compliance_signals/get_capabilities/field_value` | #1604, #1680 | partial |
| `error_compliance_signals/nonexistent_signal/error_code` | #1604, #1680 | partial |
| `error_compliance_signals/nonexistent_signal/field_present` | #1604, #1680 | partial |
| `error_compliance_signals/nonexistent_signal/field_value` | #1604, #1680 | partial |
| `error_compliance_signals/missing_required_field/error_code` | #1604, #1680 | partial |
| `error_compliance_signals/missing_required_field/field_present` | #1604, #1680 | partial |
| `error_compliance_signals/missing_required_field/field_value` | #1604, #1680 | partial |
| `error_compliance_signals/validate_error_shape/error_code` | #1604, #1680 | partial |
| `error_compliance_signals/validate_error_shape/field_present` | #1604, #1680 | partial |
| `error_compliance_signals/validate_error_shape/field_value` | #1604, #1680 | partial |
| `error_compliance_signals/unsupported_major_version/error_code` | #1604, #1680 | partial |
| `error_compliance_signals/unsupported_major_version/field_present` | #1604, #1680 | partial |
| `error_compliance_signals/unsupported_major_version/field_value` | #1604, #1680 | partial |
| `error_compliance_signals/supported_major_version/response_schema` | #1604, #1680 | partial |
| `error_compliance_signals/supported_major_version/field_present` | #1604, #1680 | partial |
| `error_compliance_signals/supported_major_version/field_value` | #1604, #1680 | partial |
| `error_compliance_signals/validate_transport_binding/error_code` | #1604, #1680 | partial |
| `error_compliance_signals/validate_transport_binding/field_present` | #1604, #1680 | partial |
| `error_compliance_signals/validate_transport_binding/field_value` | #1604, #1680 | partial |
| `error_compliance/get_capabilities/response_schema` | #1604, #1680, #1753 | partial |
| `error_compliance/get_capabilities/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/get_capabilities/field_present#1` | #1604, #1680, #1753 | partial |
| `error_compliance/get_capabilities/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/negative_budget/error_code` | #1604, #1680, #1753 | partial |
| `error_compliance/negative_budget/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/negative_budget/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/nonexistent_product/error_code` | #1604, #1680, #1753 | partial |
| `error_compliance/nonexistent_product/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/nonexistent_product/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/missing_fields/response_schema` | #1604, #1680, #1753 | partial |
| `error_compliance/missing_fields/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/missing_fields/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/reversed_dates_error/error_code` | #1604, #1680, #1753 | partial |
| `error_compliance/reversed_dates_error/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/reversed_dates_error/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/validate_error_shape/error_code` | #1604, #1680, #1753 | partial |
| `error_compliance/validate_error_shape/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/validate_error_shape/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/unsupported_major_version/error_code` | #1604, #1680, #1753 | partial |
| `error_compliance/unsupported_major_version/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/unsupported_major_version/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/unsupported_release_version/error_code` | #1604, #1680, #1753 | partial |
| `error_compliance/unsupported_release_version/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/unsupported_release_version/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/supported_major_version/response_schema` | #1604, #1680, #1753 | partial |
| `error_compliance/supported_major_version/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/supported_major_version/field_value` | #1604, #1680, #1753 | partial |
| `error_compliance/validate_transport_binding/error_code` | #1604, #1680, #1753 | partial |
| `error_compliance/validate_transport_binding/field_present` | #1604, #1680, #1753 | partial |
| `error_compliance/validate_transport_binding/field_value` | #1604, #1680, #1753 | partial |
| `idempotency/get_capabilities/response_schema` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_capabilities/field_present` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_capabilities/field_value` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_capabilities/field_present#1` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_capabilities/field_present#2` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_capabilities/field_value#1` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_missing_key/error_code` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_missing_key/field_present` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_missing_key/field_value` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_initial/response_schema` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_initial/field_present` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_initial/field_value_or_absent` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_initial/field_present#1` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_initial/field_value` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_replay/response_schema` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_replay/field_present` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_replay/field_value` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_replay/field_value#1` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_replay/field_present#1` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_replay/field_value#2` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_conflict/error_code` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_conflict/field_present` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_conflict/field_value` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_fresh_key/response_schema` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_fresh_key/field_present` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_fresh_key/field_value_or_absent` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_fresh_key/field_present#1` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_fresh_key/field_value` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_concurrent/cross_response_count_distinct` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/create_media_buy_concurrent/cross_response_field_equal` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_media_buys_dedup_check/response_schema` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_media_buys_dedup_check/field_present` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_media_buys_dedup_check/field_present#1` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/get_media_buys_dedup_check/field_value` | #1683, #1685, #1470, #1075 | partial |
| `idempotency/expect_rate_limit_not_replayed/replay_not_cached_rate_limit` | #1683, #1685, #1470, #1075 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/response_schema` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_present` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#1` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#2` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#3` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#4` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_absent` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_create_paused_notification_config/field_value#5` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_notification_config/response_schema` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_notification_config/field_value` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_notification_config/field_value#1` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_notification_config/field_value#2` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_notification_config/field_value#3` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/response_schema` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/field_value` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/field_value#1` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/field_value#2` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/field_value#3` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/field_value#4` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/field_absent` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_replace_and_pause_subscriber/field_value#5` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_paused_replacement/response_schema` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_paused_replacement/field_value` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_paused_replacement/field_value#1` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_paused_replacement/field_value#2` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_paused_replacement/field_value#3` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_clear_subscribers/response_schema` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_clear_subscribers/field_present` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_clear_subscribers/field_absent` | #1727, #1608 | partial |
| `notification_config_lifecycle/sync_accounts_clear_subscribers/field_value` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_cleared_subscribers/response_schema` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_cleared_subscribers/field_value` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_cleared_subscribers/field_present` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_cleared_subscribers/field_absent` | #1727, #1608 | partial |
| `notification_config_lifecycle/list_accounts_echoes_cleared_subscribers/field_value#1` | #1727, #1608 | partial |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/response_schema` | #1747 | partial |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value` | #1747 | partial |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#1` | #1747 | partial |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#2` | #1747 | partial |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#3` | #1747 | partial |
| `notification_config_rejections/sync_accounts_rejects_duplicate_subscriber_id/field_value#4` | #1747 | partial |
| `pagination_integrity/get_capabilities/response_schema` | #1033 | partial |
| `pagination_integrity/get_capabilities/field_present` | #1033 | partial |
| `pagination_integrity/get_capabilities/field_present#1` | #1033 | partial |
| `pagination_integrity/get_capabilities/field_value` | #1033 | partial |
| `pagination_integrity/first_page/response_schema` | #1033 | partial |
| `pagination_integrity/first_page/field_value` | #1033 | partial |
| `pagination_integrity/first_page/field_present` | #1033 | partial |
| `pagination_integrity/first_page/field_value#1` | #1033 | partial |
| `pagination_integrity/first_page/field_value#2` | #1033 | partial |
| `pagination_integrity/first_page/field_value_or_absent` | #1033 | partial |
| `pagination_integrity/first_page/field_present#1` | #1033 | partial |
| `pagination_integrity/first_page/field_value#3` | #1033 | partial |
| `pagination_integrity/terminal_page/response_schema` | #1033 | partial |
| `pagination_integrity/terminal_page/field_value` | #1033 | partial |
| `pagination_integrity/terminal_page/field_value_or_absent` | #1033 | partial |
| `pagination_integrity/terminal_page/field_value#1` | #1033 | partial |
| `pagination_integrity/terminal_page/field_value#2` | #1033 | partial |
| `pagination_integrity/terminal_page/field_value_or_absent#1` | #1033 | partial |
| `pagination_integrity/terminal_page/field_present` | #1033 | partial |
| `pagination_integrity/terminal_page/field_value#3` | #1033 | partial |
| `schema_validation_signals/get_capabilities/response_schema` | #1442 | partial |
| `schema_validation_signals/get_capabilities/field_present` | #1442 | partial |
| `schema_validation_signals/get_capabilities/field_present#1` | #1442 | partial |
| `schema_validation_signals/get_capabilities/field_value` | #1442 | partial |
| `schema_validation_signals/get_signals_schema/response_schema` | #1442 | partial |
| `schema_validation_signals/get_signals_schema/field_present` | #1442 | partial |
| `schema_validation_signals/get_signals_schema/field_present#1` | #1442 | partial |
| `schema_validation_signals/get_signals_schema/field_present#2` | #1442 | partial |
| `schema_validation_signals/get_signals_schema/field_present#3` | #1442 | partial |
| `schema_validation_signals/get_signals_schema/field_value` | #1442 | partial |
| `schema_validation_signals/pricing_options_present/field_present` | #1442 | partial |
| `schema_validation_signals/pricing_options_present/field_present#1` | #1442 | partial |
| `schema_validation_signals/pricing_options_present/field_present#2` | #1442 | partial |
| `schema_validation_signals/pricing_options_present/field_value` | #1442 | partial |
| `schema_validation/get_capabilities/response_schema` | #1442 | partial |
| `schema_validation/get_capabilities/field_present` | #1442 | partial |
| `schema_validation/get_capabilities/field_present#1` | #1442 | partial |
| `schema_validation/get_capabilities/field_value` | #1442 | partial |
| `schema_validation/get_products_schema/response_schema` | #1442 | partial |
| `schema_validation/get_products_schema/field_present` | #1442 | partial |
| `schema_validation/get_products_schema/field_present#1` | #1442 | partial |
| `schema_validation/get_products_schema/field_present#2` | #1442 | partial |
| `schema_validation/get_products_schema/field_present#3` | #1442 | partial |
| `schema_validation/get_products_schema/field_value` | #1442 | partial |
| `schema_validation/pricing_options_present/field_present` | #1442 | partial |
| `schema_validation/pricing_options_present/field_present#1` | #1442 | partial |
| `schema_validation/pricing_options_present/field_present#2` | #1442 | partial |
| `schema_validation/pricing_options_present/field_value` | #1442 | partial |
| `schema_validation/get_products_for_formats/response_schema` | #1442 | partial |
| `schema_validation/get_products_for_formats/field_present` | #1442 | partial |
| `schema_validation/get_products_for_formats/field_present#1` | #1442 | partial |
| `schema_validation/get_products_for_formats/field_present#2` | #1442 | partial |
| `schema_validation/get_products_for_formats/field_present#3` | #1442 | partial |
| `schema_validation/get_products_for_formats/field_present#4` | #1442 | partial |
| `schema_validation/get_products_for_formats/field_present#5` | #1442 | partial |
| `schema_validation/get_products_for_formats/field_value` | #1442 | partial |
| `schema_validation/list_formats_match/response_schema` | #1442 | partial |
| `schema_validation/list_formats_match/field_present` | #1442 | partial |
| `schema_validation/list_formats_match/field_present#1` | #1442 | partial |
| `schema_validation/list_formats_match/field_value` | #1442 | partial |
| `schema_validation/list_formats_match/field_present#2` | #1442 | partial |
| `schema_validation/list_formats_match/field_value#1` | #1442 | partial |
| `schema_validation/reversed_dates/field_present` | #1442 | partial |
| `schema_validation/reversed_dates/field_present#1` | #1442 | partial |
| `schema_validation/reversed_dates/field_value` | #1442 | partial |
| `schema_validation/create_buy_past_start_reject/error_code` | #1442 | partial |
| `schema_validation/create_buy_past_start_reject/field_present` | #1442 | partial |
| `schema_validation/create_buy_past_start_reject/field_value` | #1442 | partial |
| `security_baseline/probe_unauth/http_status_in` | #1859 | partial |
| `security_baseline/probe_unauth/on_401_require_header` | #1859 | partial |
| `security_baseline/probe_api_key/field_present` | #1859 | partial |
| `security_baseline/probe_api_key/field_value` | #1859 | partial |
| `security_baseline/probe_invalid_api_key/http_status_in` | #1859 | partial |
| `security_baseline/probe_invalid_api_key/on_401_require_header` | #1859 | partial |
| `security_baseline/probe_basic/field_present` | #1859 | partial |
| `security_baseline/probe_basic/field_value` | #1859 | partial |
| `security_baseline/probe_invalid_basic/http_status_in` | #1859 | partial |
| `security_baseline/probe_invalid_basic/on_401_require_header` | #1859 | partial |
| `security_baseline/probe_protected_resource/http_status` | #1859 | partial |
| `security_baseline/probe_protected_resource/field_present` | #1859 | partial |
| `security_baseline/probe_protected_resource/field_present#1` | #1859 | partial |
| `security_baseline/probe_protected_resource/resource_equals_agent_url` | #1859 | partial |
| `security_baseline/probe_auth_server_metadata/http_status` | #1859 | partial |
| `security_baseline/probe_auth_server_metadata/field_present` | #1859 | partial |
| `security_baseline/probe_auth_server_metadata/field_present#1` | #1859 | partial |
| `security_baseline/probe_invalid_oauth_token/http_status_in` | #1859 | partial |
| `security_baseline/probe_invalid_oauth_token/on_401_require_header` | #1859 | partial |
| `security_baseline/assert_mechanism/any_of` | #1859 | partial |
| `signed_requests/get_capabilities/field_present` | #1291 | partial |
| `signed_requests/get_capabilities/field_value` | #1291 | partial |
| `v3_envelope_integrity/no_legacy_status_fields/response_schema` | #1449, #1706, #1684 | partial |
| `v3_envelope_integrity/no_legacy_status_fields/envelope_field_present` | #1449, #1706, #1684 | partial |
| `v3_envelope_integrity/no_legacy_status_fields/envelope_field_absent` | #1449, #1706, #1684 | partial |
| `v3_envelope_integrity/no_legacy_status_fields/envelope_field_absent#1` | #1449, #1706, #1684 | partial |
| `v3_envelope_integrity/no_legacy_status_fields/field_present` | #1449, #1706, #1684 | partial |
| `v3_envelope_integrity/no_legacy_status_fields/field_value` | #1449, #1706, #1684 | partial |
| `version_negotiation/get_capabilities_with_version/response_schema` | #1512 | partial |
| `version_negotiation/get_capabilities_with_version/field_present` | #1512 | partial |
| `version_negotiation/get_capabilities_with_version/field_present#1` | #1512 | partial |
| `version_negotiation/get_capabilities_with_version/envelope_field_present` | #1512 | partial |
| `version_negotiation/get_capabilities_with_version/envelope_field_pattern` | #1512 | partial |
| `version_negotiation/get_capabilities_with_version/field_present#2` | #1512 | partial |
| `version_negotiation/get_capabilities_with_version/field_value` | #1512 | partial |
| `webhook_emission/get_capabilities/field_present` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/trigger_idempotent_webhook_replay/field_value` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/sync_get_products_with_webhook_config_success/response_schema` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/sync_get_products_with_webhook_config_success/field_present` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/sync_get_products_with_webhook_config_success/field_absent` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/sync_get_products_with_webhook_config_success/field_value` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/sync_get_products_with_webhook_config_reject/error_code` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/assert_synchronous_completion_handled/any_of` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/trigger_webhook_operation/expect_webhook` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/trigger_operation_id_echo/expect_webhook` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/trigger_idempotent_webhook_initial/expect_webhook` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/trigger_retry_scenario/expect_webhook_retry_keys_stable` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/fetch_brand_json/fetch_brand_jwks` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/assert_webhook_signing_key_present/assert_jwks_purpose` | #1869, #1291, #1639, #1735, #1712 | partial |
| `webhook_emission/trigger_signed_webhook/expect_webhook_signature_valid` | #1869, #1291, #1639, #1735, #1712 | partial |

## 3. Scenario coverage

`live?` is this row's `graded_by_live_scenario` — at least one claiming scenario with steps bound and a registry-verified wired harness. A claim with no live scenario renders "claimed only", not silently as covered.

| Check | Scenario(s) claiming the storyboard | live? |
|---|---|---|
| `media_buy_seller/get_capabilities/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_capabilities/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_capabilities/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_capabilities/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_accounts/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_accounts/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_accounts/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_accounts/field_present#2` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_accounts/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_governance/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_governance/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_governance/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present#2` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present#3` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present#4` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present#5` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present#6` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_products_brief/field_present#7` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats_integrity/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats_integrity/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats_integrity/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats_integrity/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats_integrity/field_value#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/create_media_buy/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/create_media_buy/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/create_media_buy/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/check_buy_status/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/check_buy_status/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/check_buy_status/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/check_buy_status/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/check_buy_status/field_equals_context` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/check_buy_status/field_value#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats/field_present#2` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats/field_present#3` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/list_formats/refs_resolve` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_creatives/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_creatives/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_creatives/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/sync_creatives/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_delivery/response_schema` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_delivery/field_present` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_delivery/field_present#1` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/get_delivery/field_value` | `T-UC-005-storyboard-format-id-roundtrip-from-products`, `T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`, `T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-multi-format-sync-status`, `T-UC-019-storyboard-post-create-status-poll` | yes |
| `media_buy_seller/creative_fate_after_cancellation/get_products_brief/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/get_products_brief/field_present` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/get_products_brief/field_present#1` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/create_buy/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/create_buy/field_present` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/create_buy/field_present#1` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/sync_creative_with_assignment/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/sync_creative_with_assignment/field_present` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/list_creatives_before_cancel/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/list_creatives_before_cancel/field_present` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/list_creatives_before_cancel/field_value` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/update_media_buy_canceled/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/list_creatives_after_cancel/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/list_creatives_after_cancel/field_present` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/list_creatives_after_cancel/field_value` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/list_creatives_after_cancel/field_value#1` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/create_second_buy/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/create_second_buy/field_present` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/create_second_buy/field_present#1` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/creative_fate_after_cancellation/reassign_creative/response_schema` | `T-UC-003-storyboard-creative-fate-after-cancellation` | claimed only |
| `media_buy_seller/delivery_reporting/sync_accounts/response_schema` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/sync_accounts/field_present` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_products_brief/response_schema` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_products_brief/field_present` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/create_media_buy/response_schema` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/simulate_delivery/field_value` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_delivery/response_schema` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_delivery/field_present` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/create_media_buy_viewability/response_schema` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/create_media_buy_viewability/field_present` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/simulate_viewability_delivery/field_value` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/response_schema` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#1` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#2` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#3` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#4` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#5` | `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` | claimed only |
| `media_buy_seller/invalid_transitions/update_unknown_media_buy/error_code` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/update_unknown_media_buy/field_present` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/update_unknown_media_buy/field_value` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/get_products_brief/response_schema` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/get_products_brief/field_present` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/create_buy/response_schema` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/create_buy/field_present` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/update_unknown_package/error_code` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/update_unknown_package/field_present` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/update_unknown_package/field_value` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/first_cancel/response_schema` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/second_cancel/error_code` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/second_cancel/field_present` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/invalid_transitions/second_cancel/field_value` | `T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-003-storyboard-package-not-found` | yes |
| `media_buy_seller/inventory_list_no_match/get_products_brief/response_schema` | `T-UC-002-storyboard-inventory-list-no-match` | claimed only |
| `media_buy_seller/inventory_list_no_match/get_products_brief/field_present` | `T-UC-002-storyboard-inventory-list-no-match` | claimed only |
| `media_buy_seller/inventory_list_no_match/create_buy_no_match/field_present` | `T-UC-002-storyboard-inventory-list-no-match` | claimed only |
| `media_buy_seller/inventory_list_no_match/create_buy_no_match/field_value` | `T-UC-002-storyboard-inventory-list-no-match` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_products_brief/response_schema` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_products_brief/field_present` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_products_brief/field_present#1` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/create_buy_with_lists/response_schema` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/create_buy_with_lists/field_present` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/create_buy_with_lists/field_present#1` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_after_create/response_schema` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_after_create/field_value` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_after_create/field_value#1` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/update_buy_swap_lists/response_schema` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/update_buy_swap_lists/field_present` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/update_buy_swap_lists/field_contains` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_after_update/response_schema` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_after_update/field_value` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/inventory_list_targeting/get_after_update/field_value#1` | `T-UC-002-storyboard-inventory-list-targeting-parity` | claimed only |
| `media_buy_seller/measurement_accountability/sync_accounts/response_schema` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/sync_accounts/field_present` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/response_schema` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present#1` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present#2` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/create_media_buy/response_schema` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/create_media_buy/field_present` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/simulate_delivery/field_value` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/get_delivery_clean/response_schema` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_accountability/get_delivery_clean/field_value_or_absent` | `T-UC-004-storyboard-required-metrics-end-to-end-accountability` | claimed only |
| `media_buy_seller/measurement_terms_rejected/get_products_brief/response_schema` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/get_products_brief/field_present` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/get_products_brief/field_present#1` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/create_media_buy_aggressive_terms/error_code` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/create_media_buy_aggressive_terms/field_present` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/create_media_buy_aggressive_terms/field_value` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/create_media_buy_relaxed_terms/response_schema` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/create_media_buy_relaxed_terms/field_present` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/create_media_buy_relaxed_terms/field_present#1` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/measurement_terms_rejected/create_media_buy_relaxed_terms/field_value` | `T-UC-002-storyboard-measurement-terms-rejected` | claimed only |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_present` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_with_disclosure/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_with_disclosure/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/provenance_enforcement/sync_creatives_with_disclosure/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` | yes |
| `media_buy_seller/vendor_metric_accountability/sync_accounts/response_schema` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/sync_accounts/field_present` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/response_schema` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#1` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#2` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#3` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#4` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/create_media_buy/response_schema` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/create_media_buy/field_present` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/simulate_delivery_with_vendor_metrics/field_value` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/response_schema` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#1` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#2` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#3` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#4` | `T-UC-004-storyboard-vendor-metric-end-to-end` | claimed only |

## 4. Graduation candidates

A claiming scenario locally xfails this check's storyboard as a known gap (the `ledgered` bucket, from a real BDD run — see `tests/bdd/scenario_liveness.py`), but the real conformance-ledger run (`tests/storyboard/known_failures.txt`) does not currently measure this check FAILING. That mismatch is a candidate for the xpass-graduation workflow — inspect per scenario before removing the xfail, per scenario, never in bulk. Visibility only: no CI gate reads this table.

| Check | Ledgered scenario(s) |
|---|---|
| `media_buy_seller/get_capabilities/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_capabilities/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_capabilities/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_capabilities/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_accounts/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_accounts/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_accounts/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_accounts/field_present#2` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_accounts/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_governance/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_governance/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_governance/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present#2` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present#3` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present#4` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present#5` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present#6` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_products_brief/field_present#7` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats_integrity/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats_integrity/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats_integrity/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats_integrity/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats_integrity/field_value#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/create_media_buy/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/create_media_buy/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/create_media_buy/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/check_buy_status/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/check_buy_status/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/check_buy_status/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/check_buy_status/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/check_buy_status/field_equals_context` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/check_buy_status/field_value#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats/field_present#2` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats/field_present#3` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/list_formats/refs_resolve` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_creatives/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_creatives/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_creatives/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/sync_creatives/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_delivery/response_schema` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_delivery/field_present` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_delivery/field_present#1` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/get_delivery/field_value` | `T-UC-006-storyboard-multi-format-sync-status` |
| `media_buy_seller/invalid_transitions/update_unknown_media_buy/error_code` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/update_unknown_media_buy/field_present` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/update_unknown_media_buy/field_value` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/get_products_brief/response_schema` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/get_products_brief/field_present` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/create_buy/response_schema` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/create_buy/field_present` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/update_unknown_package/error_code` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/update_unknown_package/field_present` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/update_unknown_package/field_value` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/first_cancel/response_schema` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/second_cancel/error_code` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/second_cancel/field_present` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/invalid_transitions/second_cancel/field_value` | `T-UC-003-storyboard-not-cancellable-on-recancel` |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_present` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_provenance/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_no_digital_source_type/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_off_list_verifier/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value#2` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_with_disclosure/response_schema` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_with_disclosure/field_value` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |
| `media_buy_seller/provenance_enforcement/sync_creatives_with_disclosure/field_value#1` | `T-UC-006-storyboard-provenance-corrected-acceptance`, `T-UC-006-storyboard-provenance-digital-source-type-missing`, `T-UC-006-storyboard-provenance-disclosure-missing`, `T-UC-006-storyboard-provenance-required-rejection` |

## 5. End-to-end wireability

Can a BDD scenario for this check be wired in the e2e environment — Given seeded by sending requests or by ordinary stack fixtures, When constructed and sent by a client, Then asserted on the wire? Curated in `storyboard-wireability.yaml`; the harness is a client, so building a signed request, sending a malformed one or firing N requests to trip a rate limit are all wireable. Controller-gated checks are `not_wireable` by policy rather than by assessment.

| Check | Wireable | Needs provisioning | Blocker |
|---|---|---|---|
| `media_buy_seller/create_media_buy/response_schema` | conditional | `webhook_receiver` | The sample_request's push_notification_config points at a buyer webhook (https://buyer.example/webhooks/adcp with HMAC credentials) that the harness must host and address for the c |
| `media_buy_seller/create_media_buy/field_present` | conditional | `webhook_receiver` | The sample_request's push_notification_config points at a buyer webhook (https://buyer.example/webhooks/adcp with HMAC credentials) that the harness must host and address for the c |
| `media_buy_seller/create_media_buy/field_value` | conditional | `webhook_receiver` | The sample_request's push_notification_config points at a buyer webhook (https://buyer.example/webhooks/adcp with HMAC credentials) that the harness must host and address for the c |
| `media_buy_seller/audience_buy_flow/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/get_products_for_audience/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/get_products_for_audience/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/sync_audience/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/sync_audience/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/sync_audience/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/sync_audience/upstream_traffic` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_audience/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_audience/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_phantom_audience/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/create_media_buy_with_phantom_audience/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/simulate_audience_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/get_audience_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/audience_buy_flow/get_audience_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/available_actions/get_product_allowed_actions/response_schema` | unassessed | — | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#1` | unassessed | — | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#2` | unassessed | — | — |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#3` | unassessed | — | — |
| `media_buy_seller/available_actions/sync_available_actions_creative/response_schema` | unassessed | — | — |
| `media_buy_seller/available_actions/sync_available_actions_creative/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/response_schema` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present#1` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_value#1` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains#1` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains#2` | unassessed | — | — |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present#2` | unassessed | — | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/response_schema` | unassessed | — | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value#1` | unassessed | — | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains#1` | unassessed | — | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains#2` | unassessed | — | — |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value#2` | unassessed | — | — |
| `media_buy_seller/available_actions/increase_budget/response_schema` | unassessed | — | — |
| `media_buy_seller/available_actions/increase_budget/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/increase_budget/field_present` | unassessed | — | — |
| `media_buy_seller/available_actions/increase_budget/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/increase_budget/field_contains#1` | unassessed | — | — |
| `media_buy_seller/available_actions/increase_budget/field_value#1` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/error_code` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#1` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#2` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#3` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/error_code` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#1` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#2` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#3` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/error_code` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#1` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#2` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#3` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/error_code` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#1` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#2` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_contains` | unassessed | — | — |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#3` | unassessed | — | — |
| `media_buy_seller/billing_finality_delivery/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/create_media_buy/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/create_media_buy/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/simulate_provisional_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_provisional_delivery/field_absent#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/simulate_final_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/get_final_delivery/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/report_final_usage/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/report_final_usage/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/billing_finality_delivery/report_final_usage/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#5` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#6` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#7` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#8` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#9` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#10` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/refs_resolve` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_canonical_product/field_value#11` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v1_only_product/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_v2_only_product/field_value#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#5` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_custom_v2_only_product/field_value#6` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_experimental_product/refs_resolve` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_seeded_divergent_product/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/get_canonical_product_for_create_satisfaction/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/create_media_buy_with_legacy_mrec_format/canonical_format_satisfaction` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/reject_bare_image_selector_for_fixed_mrec/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/canonical_formats/reject_bare_image_selector_for_fixed_mrec/canonical_format_satisfaction` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/get_products_for_clicks/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/get_products_for_clicks/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/create_media_buy_clicks/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/create_media_buy_clicks/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/simulate_clicks_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/get_products_for_cpcv/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/get_products_for_cpcv/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_cpcv/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_cpcv/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_with_phantom_view_duration/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_with_phantom_view_duration/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/simulate_cpcv_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/force_arm_submitted/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/create_media_buy_async/create_media_buy_submitted/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/creative_reception/preview_synced/response_schema` | conditional | `other` | The step carries an explicit capability gate, `requires_tool: preview_creative`, and the graded output is a rendered artifact URL (`path: "previews[0].renders[0].preview_url"`). In |
| `media_buy_seller/creative_reception/preview_synced/field_present` | conditional | `other` | The step carries an explicit capability gate, `requires_tool: preview_creative`, and the graded output is a rendered artifact URL (`path: "previews[0].renders[0].preview_url"`). In |
| `media_buy_seller/creative_reception/preview_synced/field_present#1` | conditional | `other` | The step carries an explicit capability gate, `requires_tool: preview_creative`, and the graded output is a rendered artifact URL (`path: "previews[0].renders[0].preview_url"`). In |
| `media_buy_seller/creative_reception/preview_synced/field_value` | conditional | `other` | The step carries an explicit capability gate, `requires_tool: preview_creative`, and the graded output is a rendered artifact URL (`path: "previews[0].renders[0].preview_url"`). In |
| `media_buy_seller/delivery_reporting/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_products_brief/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_products_brief/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/create_media_buy/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/simulate_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/create_media_buy_viewability/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/create_media_buy_viewability/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/simulate_viewability_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/delivery_reporting/get_viewability_delivery/field_present#5` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_products_brief/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_products_brief/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_products_brief/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/create_buy/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/create_buy/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/create_buy/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/sync_creative/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/sync_creative/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/field_contains` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/force_creative_approved/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/force_creative_approved/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_baseline/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value_or_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/force_creative_rejected/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/force_creative_rejected/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_impaired/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_contains` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/sync_replacement_creative/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/sync_replacement_creative/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/force_replacement_approved/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/force_replacement_approved/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/swap_assignment/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/swap_assignment/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/swap_assignment/field_contains` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_recovered/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_recovered/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment/get_buy_recovered/field_value_or_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_contains` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_contains#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_both_approved/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_both_approved/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_b_approved/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_b_approved/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/field_value_or_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_a_rejected/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_a_rejected/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_b_rejected/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_b_rejected/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_c/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_c/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_c_approved/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_c_approved/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/field_contains` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value_or_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_d/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_d/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_d_approved/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/force_d_approved/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/field_contains` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/field_value_or_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/get_products_for_dedup/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/get_products_for_dedup/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/sync_event_sources/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/sync_event_sources/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/sync_event_sources/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/create_media_buy_dedup/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/create_media_buy_dedup/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/log_event_from_pixel/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/log_event_from_capi/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/simulate_deduplicated_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/get_dedup_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/event_dedup_flow/get_dedup_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/get_products_for_frequency_cap/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/get_products_for_frequency_cap/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/create_media_buy_with_frequency_cap/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/create_media_buy_with_frequency_cap/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/simulate_capped_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_less_than` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/force_get_products_submitted/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/force_get_products_submitted/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_submitted/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_submitted/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_submitted/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_submitted/field_absent#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/field_value#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/field_value#5` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task/field_value#6` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/list_products_task_wrong_account/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/complete_products_task/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/complete_products_task/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/complete_products_task/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_wrong_account/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#5` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_task_status_completed/field_value#6` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/get_products_async/get_products_submitted/expect_webhook` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_present` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_value#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present#2` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_present` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_present#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_value#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_equals_context` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_equals_context#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_contains` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_present` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_present#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_present` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_present#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_value#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_equals_context` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_equals_context#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_contains` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_equals_context` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_equals_context#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_value#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/response_schema` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_equals_context` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_equals_context#1` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_value` | unassessed | — | — |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_value#1` | unassessed | — | — |
| `media_buy_seller/inventory_list_no_match/create_buy_no_match/field_present` | conditional | `other` | The buyer-side inventory lists referenced in targeting_overlay must exist as resolvable lists for the seller: 'This scenario exercises the no-match path using the test kit's pre-po |
| `media_buy_seller/inventory_list_no_match/create_buy_no_match/field_value` | conditional | `other` | The buyer-side inventory lists referenced in targeting_overlay must exist as resolvable lists for the seller: 'This scenario exercises the no-match path using the test kit's pre-po |
| `media_buy_seller/inventory_list_targeting/create_buy_with_lists/response_schema` | conditional | `other` | The two matching test-kit lists must be resolvable by the seller before the call: prerequisites say 'The seller must accept PropertyListReference and CollectionListReference in pac |
| `media_buy_seller/inventory_list_targeting/create_buy_with_lists/field_present` | conditional | `other` | The two matching test-kit lists must be resolvable by the seller before the call: prerequisites say 'The seller must accept PropertyListReference and CollectionListReference in pac |
| `media_buy_seller/inventory_list_targeting/create_buy_with_lists/field_present#1` | conditional | `other` | The two matching test-kit lists must be resolvable by the seller before the call: prerequisites say 'The seller must accept PropertyListReference and CollectionListReference in pac |
| `media_buy_seller/inventory_list_targeting/get_after_create/response_schema` | conditional | `other` | Same test-kit list provisioning as the create step ('List contents come from test-kits/acme-outdoor.yaml -> inventory_targets'), since the assertion requires the seller to have acc |
| `media_buy_seller/inventory_list_targeting/get_after_create/field_value` | conditional | `other` | Same test-kit list provisioning as the create step ('List contents come from test-kits/acme-outdoor.yaml -> inventory_targets'), since the assertion requires the seller to have acc |
| `media_buy_seller/inventory_list_targeting/get_after_create/field_value#1` | conditional | `other` | Same test-kit list provisioning as the create step ('List contents come from test-kits/acme-outdoor.yaml -> inventory_targets'), since the assertion requires the seller to have acc |
| `media_buy_seller/inventory_list_targeting/get_after_update/response_schema` | conditional | `other` | Same test-kit list provisioning ('List contents come from test-kits/acme-outdoor.yaml -> inventory_targets'); the swapped ids acme_outdoor_no_match_v1 / acme_outdoor_no_match_colle |
| `media_buy_seller/inventory_list_targeting/get_after_update/field_value` | conditional | `other` | Same test-kit list provisioning ('List contents come from test-kits/acme-outdoor.yaml -> inventory_targets'); the swapped ids acme_outdoor_no_match_v1 / acme_outdoor_no_match_colle |
| `media_buy_seller/inventory_list_targeting/get_after_update/field_value#1` | conditional | `other` | Same test-kit list provisioning ('List contents come from test-kits/acme-outdoor.yaml -> inventory_targets'); the swapped ids acme_outdoor_no_match_v1 / acme_outdoor_no_match_colle |
| `media_buy_seller/measurement_accountability/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/get_products_required_metrics/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/create_media_buy/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/create_media_buy/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/simulate_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/get_delivery_clean/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/measurement_accountability/get_delivery_clean/field_value_or_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/response_schema` | conditional | — | GIVEN: the legacy package shape (a package with no product_id) cannot be produced by any AdCP client request — the storyboard requires controller seeding via seed_media_buy |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value` | conditional | — | GIVEN: the legacy package shape (a package with no product_id) cannot be produced by any AdCP client request — the storyboard requires controller seeding via seed_media_buy |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value#1` | conditional | — | GIVEN: the legacy package shape (a package with no product_id) cannot be produced by any AdCP client request — the storyboard requires controller seeding via seed_media_buy |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_absent` | conditional | — | GIVEN: the legacy package shape (a package with no product_id) cannot be produced by any AdCP client request — the storyboard requires controller seeding via seed_media_buy |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value#2` | conditional | — | GIVEN: the legacy package shape (a package with no product_id) cannot be produced by any AdCP client request — the storyboard requires controller seeding via seed_media_buy |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value#3` | conditional | — | GIVEN: the legacy package shape (a package with no product_id) cannot be produced by any AdCP client request — the storyboard requires controller seeding via seed_media_buy |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/response_schema` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/field_present` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/field_present#1` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/response_schema` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_present` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#1` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_present#1` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#2` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_equals_context` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#3` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/sync_creative/response_schema` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/response_schema` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_present` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_contains` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_value` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_value#1` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/response_schema` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_value` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_equals_context` | unassessed | — | — |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_value#1` | unassessed | — | — |
| `media_buy_seller/per_creative_conversion_attribution/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/get_products_for_per_creative/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/get_products_for_per_creative/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/upstream_traffic` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/create_media_buy_two_creatives/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/create_media_buy_two_creatives/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/log_purchase_event_1/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/log_purchase_event_2/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/simulate_per_creative_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/get_products_for_performance/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/get_products_for_performance/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/sync_event_sources/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/sync_event_sources/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/sync_event_sources/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/create_media_buy_cpa/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/create_media_buy_cpa/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/create_media_buy_with_phantom_source/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/create_media_buy_with_phantom_source/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/log_purchase_event/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/log_purchase_event/upstream_traffic` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/simulate_performance_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/get_products_for_roas/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/get_products_for_roas/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/upstream_traffic` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_roas/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_roas/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_per_ad_spend_no_value_field/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_per_ad_spend_no_value_field/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/log_purchase_event/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/log_purchase_event/upstream_traffic` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/simulate_roas_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_absent#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/pricing_currency_filter/get_products_usd_pricing/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_products_wholesale/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_present#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_signals_wholesale/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_signal_groups/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_after_create/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_after_create/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/get_after_create/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_unknown_signal/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/product_signal_targeting/create_media_buy_with_unknown_signal/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_absent` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_absent#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/upstream_traffic` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/upstream_traffic#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/response_schema` | conditional | `prior_state` | Requires a pre-seeded product whose creative_policy carries provenance_required / provenance_requirements / accepted_verifiers — reachable as an ordinary product fixture, but not p |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value` | conditional | `prior_state` | Requires a pre-seeded product whose creative_policy carries provenance_required / provenance_requirements / accepted_verifiers — reachable as an ordinary product fixture, but not p |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value#1` | conditional | `prior_state` | Requires a pre-seeded product whose creative_policy carries provenance_required / provenance_requirements / accepted_verifiers — reachable as an ordinary product fixture, but not p |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_present` | conditional | `prior_state` | Requires a pre-seeded product whose creative_policy carries provenance_required / provenance_requirements / accepted_verifiers — reachable as an ordinary product fixture, but not p |
| `media_buy_seller/provenance_enforcement/get_products_with_disclosure_policy/field_value#2` | conditional | `prior_state` | Requires a pre-seeded product whose creative_policy carries provenance_required / provenance_requirements / accepted_verifiers — reachable as an ordinary product fixture, but not p |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/response_schema` | conditional | `prior_state` | Same seeded provenance policy as the discovery step: the enforcement only fires if the seller has a product/tenant creative_policy with provenance_requirements.require_disclosure_m |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value` | conditional | `prior_state` | Same seeded provenance policy as the discovery step: the enforcement only fires if the seller has a product/tenant creative_policy with provenance_requirements.require_disclosure_m |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value#1` | conditional | `prior_state` | Same seeded provenance policy as the discovery step: the enforcement only fires if the seller has a product/tenant creative_policy with provenance_requirements.require_disclosure_m |
| `media_buy_seller/provenance_enforcement/sync_creatives_missing_disclosure/field_value#2` | conditional | `prior_state` | Same seeded provenance policy as the discovery step: the enforcement only fires if the seller has a product/tenant creative_policy with provenance_requirements.require_disclosure_m |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/response_schema` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#1` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_present` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_present#1` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#2` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#3` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#4` | conditional | `second_agent`, `prior_state` | Requires a reachable on-list verifier that deterministically returns ai_generated:true with confidence >= 0.9 for the fixture asset URL; the contradiction cannot be produced by the |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_consistent/response_schema` | conditional | `second_agent`, `prior_state` | The accept path is only meaningful if an on-list governance verifier implementing get_creative_features is actually reachable and returns ai_generated:false for the fixture asset U |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_consistent/field_value` | conditional | `second_agent`, `prior_state` | The accept path is only meaningful if an on-list governance verifier implementing get_creative_features is actually reachable and returns ai_generated:false for the fixture asset U |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_consistent/field_value#1` | conditional | `second_agent`, `prior_state` | The accept path is only meaningful if an on-list governance verifier implementing get_creative_features is actually reachable and returns ai_generated:false for the fixture asset U |
| `media_buy_seller/reach_buy_flow/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_products_for_reach/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_products_for_reach/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_with_unsupported_reach_unit/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_with_unsupported_reach_unit/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/simulate_reach_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_cumulative_reach/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_cumulative_reach/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/simulate_cumulative_reach/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_period_reach/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_period_reach/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/simulate_period_reach/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_rolling_reach/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_rolling_reach/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/simulate_rolling_reach/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach_no_window/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach_no_window/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/simulate_reach_no_window/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_delivery_reach_no_window/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/reach_buy_flow/get_delivery_reach_no_window/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/refine_finalize_exclusivity/sync_accounts/response_schema` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/sync_accounts/field_present` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief/response_schema` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief/field_present` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief_second/field_present` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_mixed_finalize/error_code` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_mixed_finalize/field_present` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_product_finalize/error_code` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/response_schema` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_present` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_contains` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_contains#1` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#1` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#2` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#3` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_unsupported/error_code` | unassessed | — | — |
| `media_buy_seller/refine_finalize_exclusivity/assert_multi_finalize/any_of` | unassessed | — | — |
| `media_buy_seller/refine_products/get_products_refine/response_schema` | conditional | `prior_state` | The refine array pins a literal catalog id — `product_id: "sports_preroll_q2"` — that no earlier step produces and no `fixtures:` block in this storyboard declares (prerequisites o |
| `media_buy_seller/refine_products/get_products_refine/field_present` | conditional | `prior_state` | The refine array pins a literal catalog id — `product_id: "sports_preroll_q2"` — that no earlier step produces and no `fixtures:` block in this storyboard declares (prerequisites o |
| `media_buy_seller/vendor_metric_accountability/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_products_required_vendor_metrics/field_present#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/create_media_buy/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/create_media_buy/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/simulate_delivery_with_vendor_metrics/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_accountability/get_delivery_with_vendor_metrics/field_present#4` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_accept/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_accept/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_reject/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_catalog_precondition/assert_vendor_metric_catalog_miss_handled/any_of` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/sync_accounts/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/sync_accounts/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_positive/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_positive/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_targetless_positive/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_targetless_positive/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_metric/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_metric/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_target/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_target/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_missing_committed/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_missing_committed/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unreportable_metric/error_code` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unreportable_metric/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `media_buy_state_machine/get_capabilities/response_schema` | unassessed | — | — |
| `media_buy_state_machine/get_capabilities/field_present` | unassessed | — | — |
| `media_buy_state_machine/get_capabilities/field_present#1` | unassessed | — | — |
| `media_buy_state_machine/get_capabilities/field_value` | unassessed | — | — |
| `media_buy_state_machine/discover_products/response_schema` | unassessed | — | — |
| `media_buy_state_machine/discover_products/field_present` | unassessed | — | — |
| `media_buy_state_machine/discover_products/field_present#1` | unassessed | — | — |
| `media_buy_state_machine/discover_products/field_value` | unassessed | — | — |
| `media_buy_state_machine/discover_products/field_present#2` | unassessed | — | — |
| `media_buy_state_machine/discover_products/field_present#3` | unassessed | — | — |
| `media_buy_state_machine/discover_products/field_present#4` | unassessed | — | — |
| `media_buy_state_machine/sync_creative/response_schema` | unassessed | — | — |
| `media_buy_state_machine/sync_creative/field_present` | unassessed | — | — |
| `media_buy_state_machine/sync_creative/field_value` | unassessed | — | — |
| `media_buy_state_machine/create_buy/response_schema` | unassessed | — | — |
| `media_buy_state_machine/create_buy/field_present` | unassessed | — | — |
| `media_buy_state_machine/create_buy/field_value` | unassessed | — | — |
| `media_buy_state_machine/create_buy/field_present#1` | unassessed | — | — |
| `media_buy_state_machine/create_buy/field_value#1` | unassessed | — | — |
| `media_buy_state_machine/create_buy/field_present#2` | unassessed | — | — |
| `media_buy_state_machine/pause_buy/field_present` | unassessed | — | — |
| `media_buy_state_machine/pause_buy/field_present#1` | unassessed | — | — |
| `media_buy_state_machine/pause_buy/field_value` | unassessed | — | — |
| `media_buy_state_machine/resume_buy/field_present` | unassessed | — | — |
| `media_buy_state_machine/resume_buy/field_present#1` | unassessed | — | — |
| `media_buy_state_machine/resume_buy/field_value` | unassessed | — | — |
| `media_buy_state_machine/cancel_buy/field_present` | unassessed | — | — |
| `media_buy_state_machine/cancel_buy/field_present#1` | unassessed | — | — |
| `media_buy_state_machine/cancel_buy/field_value` | unassessed | — | — |
| `media_buy_state_machine/pause_canceled_buy/error_code` | unassessed | — | — |
| `media_buy_state_machine/pause_canceled_buy/field_present` | unassessed | — | — |
| `media_buy_state_machine/pause_canceled_buy/field_value` | unassessed | — | — |
| `media_buy_state_machine/resume_canceled_buy/error_code` | unassessed | — | — |
| `media_buy_state_machine/resume_canceled_buy/field_present` | unassessed | — | — |
| `media_buy_state_machine/resume_canceled_buy/field_value` | unassessed | — | — |
| `media_buy_state_machine/recancel_buy/error_code` | unassessed | — | — |
| `media_buy_state_machine/recancel_buy/field_present` | unassessed | — | — |
| `media_buy_state_machine/recancel_buy/field_value` | unassessed | — | — |
| `sales_non_guaranteed/get_products_brief/response_schema` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#1` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#2` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#3` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#4` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#5` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#6` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#7` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#8` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_value` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#9` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#10` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/get_products_brief/field_present#11` | conditional | `other` | The step is stateless on the wire (`stateful: false`, no $context inputs), but nine of its fourteen checks are assertions about a specific seeded auction catalog: two non-guarantee |
| `sales_non_guaranteed/sync_governance/response_schema` | conditional | `second_agent`, `seeded_account` | Registration targets an external governance agent — `url: "$context.governance_agent_url"` resolving to the storyboard's `context: governance_agent_url: "https://test-agent.adconte |
| `sales_non_guaranteed/sync_governance/field_value` | conditional | `second_agent`, `seeded_account` | Registration targets an external governance agent — `url: "$context.governance_agent_url"` resolving to the storyboard's `context: governance_agent_url: "https://test-agent.adconte |
| `sales_non_guaranteed/sync_governance/field_present` | conditional | `second_agent`, `seeded_account` | Registration targets an external governance agent — `url: "$context.governance_agent_url"` resolving to the storyboard's `context: governance_agent_url: "https://test-agent.adconte |
| `sales_non_guaranteed/sync_governance/field_value#1` | conditional | `second_agent`, `seeded_account` | Registration targets an external governance agent — `url: "$context.governance_agent_url"` resolving to the storyboard's `context: governance_agent_url: "https://test-agent.adconte |
| `sales_non_guaranteed/create_media_buy/response_schema` | not_wireable | — | THEN. One of the five checks is `upstream_traffic`, which asserts on what the agent sent to its ad server / DSP — traffic that never appears on the client's wire. The storyboard's  |
| `sales_non_guaranteed/create_media_buy/field_present` | not_wireable | — | THEN. One of the five checks is `upstream_traffic`, which asserts on what the agent sent to its ad server / DSP — traffic that never appears on the client's wire. The storyboard's  |
| `sales_non_guaranteed/create_media_buy/field_value` | not_wireable | — | THEN. One of the five checks is `upstream_traffic`, which asserts on what the agent sent to its ad server / DSP — traffic that never appears on the client's wire. The storyboard's  |
| `sales_non_guaranteed/create_media_buy/field_present#1` | not_wireable | — | THEN. One of the five checks is `upstream_traffic`, which asserts on what the agent sent to its ad server / DSP — traffic that never appears on the client's wire. The storyboard's  |
| `sales_non_guaranteed/create_media_buy/upstream_traffic` | not_wireable | — | THEN. One of the five checks is `upstream_traffic`, which asserts on what the agent sent to its ad server / DSP — traffic that never appears on the client's wire. The storyboard's  |
| `sales_non_guaranteed/get_media_buys_pacing/response_schema` | conditional | `prior_state` | Needs the media buy from the earlier create_media_buy step to exist and its seller-assigned id carried in context (`media_buy_ids: - "$context.media_buy_id"`), which in turn rests  |
| `sales_non_guaranteed/get_media_buys_pacing/field_present` | conditional | `prior_state` | Needs the media buy from the earlier create_media_buy step to exist and its seller-assigned id carried in context (`media_buy_ids: - "$context.media_buy_id"`), which in turn rests  |
| `sales_non_guaranteed/get_media_buys_pacing/field_present#1` | conditional | `prior_state` | Needs the media buy from the earlier create_media_buy step to exist and its seller-assigned id carried in context (`media_buy_ids: - "$context.media_buy_id"`), which in turn rests  |
| `sales_non_guaranteed/get_media_buys_pacing/field_value` | conditional | `prior_state` | Needs the media buy from the earlier create_media_buy step to exist and its seller-assigned id carried in context (`media_buy_ids: - "$context.media_buy_id"`), which in turn rests  |
| `sales_non_guaranteed/update_media_buy/response_schema` | conditional | — | THEN. The final validation is `check: upstream_traffic` — it grades what the agent sent to the auction platform, which is not observable from a client holding only the update_media |
| `sales_non_guaranteed/update_media_buy/field_present` | conditional | — | THEN. The final validation is `check: upstream_traffic` — it grades what the agent sent to the auction platform, which is not observable from a client holding only the update_media |
| `sales_non_guaranteed/update_media_buy/field_contains` | conditional | — | THEN. The final validation is `check: upstream_traffic` — it grades what the agent sent to the auction platform, which is not observable from a client holding only the update_media |
| `sales_non_guaranteed/update_media_buy/field_contains#1` | conditional | — | THEN. The final validation is `check: upstream_traffic` — it grades what the agent sent to the auction platform, which is not observable from a client holding only the update_media |
| `sales_non_guaranteed/update_media_buy/field_present#1` | conditional | — | THEN. The final validation is `check: upstream_traffic` — it grades what the agent sent to the auction platform, which is not observable from a client holding only the update_media |
| `sales_non_guaranteed/update_media_buy/field_value` | conditional | — | THEN. The final validation is `check: upstream_traffic` — it grades what the agent sent to the auction platform, which is not observable from a client holding only the update_media |
| `sales_non_guaranteed/update_media_buy/upstream_traffic` | conditional | — | THEN. The final validation is `check: upstream_traffic` — it grades what the agent sent to the auction platform, which is not observable from a client holding only the update_media |
| `sales_non_guaranteed/get_delivery/response_schema` | conditional | `prior_state` | The request keys off `media_buy_ids: - "$context.media_buy_id"`, a seller-assigned id produced by the earlier create_media_buy step — that step is itself a request we send, so it i |
| `sales_non_guaranteed/get_delivery/field_present` | conditional | `prior_state` | The request keys off `media_buy_ids: - "$context.media_buy_id"`, a seller-assigned id produced by the earlier create_media_buy step — that step is itself a request we send, so it i |
| `sales_non_guaranteed/get_delivery/field_present#1` | conditional | `prior_state` | The request keys off `media_buy_ids: - "$context.media_buy_id"`, a seller-assigned id produced by the earlier create_media_buy step — that step is itself a request we send, so it i |
| `sales_non_guaranteed/get_delivery/field_value` | conditional | `prior_state` | The request keys off `media_buy_ids: - "$context.media_buy_id"`, a seller-assigned id produced by the earlier create_media_buy step — that step is itself a request we send, so it i |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/response_schema` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#1` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#2` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#3` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#4` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_present` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_unsupported_billing/field_value#5` | conditional | `seeded_account` | GIVEN requires an agent whose advertised `supported_billing` excludes the probe value; the phase self-skips otherwise, so the tenant/agent capability config has to be provisioned t |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/response_schema` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#1` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#2` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#3` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#4` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_present` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#1` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#2` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#3` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#4` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_absent#5` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_passthrough_rejects_agent/field_value#5` | conditional | `seeded_account`, `prior_state` | GIVEN needs a buyer agent pre-onboarded as passthrough-only; no AdCP call establishes it, so it must come from stack fixture/seed data before the run. |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/response_schema` | conditional | `seeded_account`, `prior_state` | GIVEN needs the same passthrough-only onboarding seed plus the preceding reject step's captured `suggested_billing`; the latter is fine (an earlier wireable request), the former is |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/field_present` | conditional | `seeded_account`, `prior_state` | GIVEN needs the same passthrough-only onboarding seed plus the preceding reject step's captured `suggested_billing`; the latter is fine (an earlier wireable request), the former is |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/field_value` | conditional | `seeded_account`, `prior_state` | GIVEN needs the same passthrough-only onboarding seed plus the preceding reject step's captured `suggested_billing`; the latter is fine (an earlier wireable request), the former is |
| `billing_gate_dispatch/sync_accounts_recover_with_suggested/field_value#1` | conditional | `seeded_account`, `prior_state` | GIVEN needs the same passthrough-only onboarding seed plus the preceding reject step's captured `suggested_billing`; the latter is fine (an earlier wireable request), the former is |
| `get_media_buys_pagination_integrity/list_call/response_schema` | conditional | `prior_state`, `seeded_account` | Three media buys must exist before the call, and the storyboard provisions them out-of-band: prerequisites say "The runner seeds three media buys via `controller_seeding: true`" wi |
| `get_media_buys_pagination_integrity/list_call/field_present` | conditional | `prior_state`, `seeded_account` | Three media buys must exist before the call, and the storyboard provisions them out-of-band: prerequisites say "The runner seeds three media buys via `controller_seeding: true`" wi |
| `get_media_buys_pagination_integrity/list_call/field_present#1` | conditional | `prior_state`, `seeded_account` | Three media buys must exist before the call, and the storyboard provisions them out-of-band: prerequisites say "The runner seeds three media buys via `controller_seeding: true`" wi |
| `get_media_buys_pagination_integrity/list_call/field_present#2` | conditional | `prior_state`, `seeded_account` | Three media buys must exist before the call, and the storyboard provisions them out-of-band: prerequisites say "The runner seeds three media buys via `controller_seeding: true`" wi |
| `get_media_buys_pagination_integrity/list_call/field_value` | conditional | `prior_state`, `seeded_account` | Three media buys must exist before the call, and the storyboard provisions them out-of-band: prerequisites say "The runner seeds three media buys via `controller_seeding: true`" wi |
| `get_products_pagination_integrity/wholesale_first_page/response_schema` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_present` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_value` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_contains` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_absent` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_value#1` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_present#1` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_value_or_absent` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_present#2` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_first_page/field_value#2` | conditional | `prior_state`, `seeded_account` | The graded assertions depend on exactly two catalog products existing under one unique format id, and no AdCP client call creates products — prerequisites: "The runner seeds two pr |
| `get_products_pagination_integrity/wholesale_terminal_page/response_schema` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_present` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_contains` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_absent` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value#1` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value_or_absent` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value_or_absent#1` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_present#1` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value#2` | conditional | `prior_state`, `seeded_account` | Same out-of-band product seeding as the first page (two fixtures under `get_products_pagination_integrity_display` via `controller_seeding: true`), plus a live cursor carried from  |
| `get_signals_pagination_integrity/first_page/response_schema` | conditional | `prior_state`, `seeded_account` | No fixture seeding is defined, but the graded assertion only holds if the agent's signal set already contains more than one match for "audience" — prerequisites: "No fixtures requi |
| `get_signals_pagination_integrity/first_page/field_value` | conditional | `prior_state`, `seeded_account` | No fixture seeding is defined, but the graded assertion only holds if the agent's signal set already contains more than one match for "audience" — prerequisites: "No fixtures requi |
| `get_signals_pagination_integrity/first_page/field_present` | conditional | `prior_state`, `seeded_account` | No fixture seeding is defined, but the graded assertion only holds if the agent's signal set already contains more than one match for "audience" — prerequisites: "No fixtures requi |
| `get_signals_pagination_integrity/first_page/field_present#1` | conditional | `prior_state`, `seeded_account` | No fixture seeding is defined, but the graded assertion only holds if the agent's signal set already contains more than one match for "audience" — prerequisites: "No fixtures requi |
| `get_signals_pagination_integrity/first_page/field_value#1` | conditional | `prior_state`, `seeded_account` | No fixture seeding is defined, but the graded assertion only holds if the agent's signal set already contains more than one match for "audience" — prerequisites: "No fixtures requi |
| `get_signals_pagination_integrity/next_page/response_schema` | conditional | `prior_state`, `seeded_account` | Needs the cursor minted by the preceding step — `pagination: cursor: "$context.signals_next_cursor"` — which is fine because `first_page` is itself a request the harness sends, but |
| `get_signals_pagination_integrity/next_page/field_present` | conditional | `prior_state`, `seeded_account` | Needs the cursor minted by the preceding step — `pagination: cursor: "$context.signals_next_cursor"` — which is fine because `first_page` is itself a request the harness sends, but |
| `get_signals_pagination_integrity/next_page/field_value` | conditional | `prior_state`, `seeded_account` | Needs the cursor minted by the preceding step — `pagination: cursor: "$context.signals_next_cursor"` — which is fine because `first_page` is itself a request the harness sends, but |
| `idempotency/expect_rate_limit_not_replayed/replay_not_cached_rate_limit` | conditional | `rate_limit` | The invariant is only graded if the agent's per-agent idempotency-cache insert limiter actually trips inside the burst budget; otherwise the step self-grades not_applicable. The en |
| `pagination_integrity_creative_formats/seed_format_1/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `pagination_integrity_creative_formats/seed_format_2/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `pagination_integrity_creative_formats/first_page/response_schema` | conditional | `prior_state` | Requires exactly two creative formats matching name_search 'Pagination Integrity Format' to exist for the calling principal. The storyboard provisions them with comply_test_control |
| `pagination_integrity_creative_formats/first_page/field_value` | conditional | `prior_state` | Requires exactly two creative formats matching name_search 'Pagination Integrity Format' to exist for the calling principal. The storyboard provisions them with comply_test_control |
| `pagination_integrity_creative_formats/first_page/field_present` | conditional | `prior_state` | Requires exactly two creative formats matching name_search 'Pagination Integrity Format' to exist for the calling principal. The storyboard provisions them with comply_test_control |
| `pagination_integrity_creative_formats/first_page/field_value_or_absent` | conditional | `prior_state` | Requires exactly two creative formats matching name_search 'Pagination Integrity Format' to exist for the calling principal. The storyboard provisions them with comply_test_control |
| `pagination_integrity_creative_formats/first_page/field_present#1` | conditional | `prior_state` | Requires exactly two creative formats matching name_search 'Pagination Integrity Format' to exist for the calling principal. The storyboard provisions them with comply_test_control |
| `pagination_integrity_creative_formats/first_page/field_value#1` | conditional | `prior_state` | Requires exactly two creative formats matching name_search 'Pagination Integrity Format' to exist for the calling principal. The storyboard provisions them with comply_test_control |
| `pagination_integrity_creative_formats/terminal_page/response_schema` | conditional | `prior_state` | Two provisioned preconditions: (a) the same two seeded formats matching name_search 'Pagination Integrity Format' (no AdCP write tool for formats — needs a stack fixture creative a |
| `pagination_integrity_creative_formats/terminal_page/field_value` | conditional | `prior_state` | Two provisioned preconditions: (a) the same two seeded formats matching name_search 'Pagination Integrity Format' (no AdCP write tool for formats — needs a stack fixture creative a |
| `pagination_integrity_creative_formats/terminal_page/field_value_or_absent` | conditional | `prior_state` | Two provisioned preconditions: (a) the same two seeded formats matching name_search 'Pagination Integrity Format' (no AdCP write tool for formats — needs a stack fixture creative a |
| `pagination_integrity_creative_formats/terminal_page/field_value_or_absent#1` | conditional | `prior_state` | Two provisioned preconditions: (a) the same two seeded formats matching name_search 'Pagination Integrity Format' (no AdCP write tool for formats — needs a stack fixture creative a |
| `pagination_integrity_creative_formats/terminal_page/field_present` | conditional | `prior_state` | Two provisioned preconditions: (a) the same two seeded formats matching name_search 'Pagination Integrity Format' (no AdCP write tool for formats — needs a stack fixture creative a |
| `pagination_integrity_creative_formats/terminal_page/field_value#1` | conditional | `prior_state` | Two provisioned preconditions: (a) the same two seeded formats matching name_search 'Pagination Integrity Format' (no AdCP write tool for formats — needs a stack fixture creative a |
| `pagination_integrity_list_accounts/seed_account_1/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `pagination_integrity_list_accounts/seed_account_2/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `pagination_integrity_list_accounts/seed_account_3/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `pagination_integrity_list_accounts/first_page/response_schema` | conditional | `prior_state`, `seeded_account` | Requires at least three sandbox accounts visible to the calling principal before the call. The storyboard provisions them via 'comply_test_controller.seed_account' ('requires: [con |
| `pagination_integrity_list_accounts/first_page/field_value` | conditional | `prior_state`, `seeded_account` | Requires at least three sandbox accounts visible to the calling principal before the call. The storyboard provisions them via 'comply_test_controller.seed_account' ('requires: [con |
| `pagination_integrity_list_accounts/first_page/field_present` | conditional | `prior_state`, `seeded_account` | Requires at least three sandbox accounts visible to the calling principal before the call. The storyboard provisions them via 'comply_test_controller.seed_account' ('requires: [con |
| `pagination_integrity_list_accounts/first_page/field_present#1` | conditional | `prior_state`, `seeded_account` | Requires at least three sandbox accounts visible to the calling principal before the call. The storyboard provisions them via 'comply_test_controller.seed_account' ('requires: [con |
| `pagination_integrity_list_accounts/first_page/field_value#1` | conditional | `prior_state`, `seeded_account` | Requires at least three sandbox accounts visible to the calling principal before the call. The storyboard provisions them via 'comply_test_controller.seed_account' ('requires: [con |
| `pagination_integrity_list_accounts/next_page/response_schema` | conditional | `prior_state`, `seeded_account` | Needs the cursor produced by the preceding first_page step plus at least three sandbox accounts visible to the calling principal; the storyboard sources those from comply_test_cont |
| `pagination_integrity_list_accounts/next_page/field_present` | conditional | `prior_state`, `seeded_account` | Needs the cursor produced by the preceding first_page step plus at least three sandbox accounts visible to the calling principal; the storyboard sources those from comply_test_cont |
| `pagination_integrity_list_accounts/next_page/field_present#1` | conditional | `prior_state`, `seeded_account` | Needs the cursor produced by the preceding first_page step plus at least three sandbox accounts visible to the calling principal; the storyboard sources those from comply_test_cont |
| `pagination_integrity_list_accounts/next_page/field_value` | conditional | `prior_state`, `seeded_account` | Needs the cursor produced by the preceding first_page step plus at least three sandbox accounts visible to the calling principal; the storyboard sources those from comply_test_cont |
| `pagination_integrity/first_page/response_schema` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/first_page/field_value` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/first_page/field_present` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/first_page/field_value#1` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/first_page/field_value#2` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/first_page/field_value_or_absent` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/first_page/field_present#1` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/first_page/field_value#3` | conditional | `prior_state`, `seeded_account` | Needs exactly three creatives with the fixture ids in the library (plus the account acct_pagination_integrity). The storyboard says the runner seeds them via the controller ('contr |
| `pagination_integrity/terminal_page/response_schema` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `pagination_integrity/terminal_page/field_value` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `pagination_integrity/terminal_page/field_value_or_absent` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `pagination_integrity/terminal_page/field_value#1` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `pagination_integrity/terminal_page/field_value#2` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `pagination_integrity/terminal_page/field_value_or_absent#1` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `pagination_integrity/terminal_page/field_present` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `pagination_integrity/terminal_page/field_value#3` | conditional | `prior_state`, `seeded_account` | Needs the same exact three-creative library seed plus $context.next_cursor captured from first_page (itself a list_creatives request we send). Seeding is doable via sync_creatives/ |
| `schema_validation/create_buy_past_start_reject/error_code` | conditional | `prior_state` | Seeded product 'test-product' with pricing option 'test-pricing' must exist before the call, otherwise a catalog-availability error masks the temporal rejection. |
| `schema_validation/create_buy_past_start_reject/field_present` | conditional | `prior_state` | Seeded product 'test-product' with pricing option 'test-pricing' must exist before the call, otherwise a catalog-availability error masks the temporal rejection. |
| `schema_validation/create_buy_past_start_reject/field_value` | conditional | `prior_state` | Seeded product 'test-product' with pricing option 'test-pricing' must exist before the call, otherwise a catalog-availability error masks the temporal rejection. |
| `security_baseline/probe_basic/field_present` | conditional | `seeded_account` | The phase only runs when the test kit carries HTTP Basic credentials (`skip_if: "!test_kit.auth.basic"`), and the agent must be configured to accept Basic on protected operations.  |
| `security_baseline/probe_basic/field_value` | conditional | `seeded_account` | The phase only runs when the test kit carries HTTP Basic credentials (`skip_if: "!test_kit.auth.basic"`), and the agent must be configured to accept Basic on protected operations.  |
| `security_baseline/probe_invalid_basic/http_status_in` | conditional | `seeded_account` | Same phase gate as probe_basic: `skip_if: "!test_kit.auth.basic"` plus `contributes_if: "prior_step.probe_basic.passed"` mean the step only runs, and only counts, when a valid HTTP |
| `security_baseline/probe_invalid_basic/on_401_require_header` | conditional | `seeded_account` | Same phase gate as probe_basic: `skip_if: "!test_kit.auth.basic"` plus `contributes_if: "prior_step.probe_basic.passed"` mean the step only runs, and only counts, when a valid HTTP |
| `security_baseline/probe_protected_resource/http_status` | conditional | `other` | The agent deployment under test must actually be OAuth-configured and serve RFC 9728 protected-resource metadata. The phase is `optional: true` and the storyboard explicitly tells  |
| `security_baseline/probe_protected_resource/field_present` | conditional | `other` | The agent deployment under test must actually be OAuth-configured and serve RFC 9728 protected-resource metadata. The phase is `optional: true` and the storyboard explicitly tells  |
| `security_baseline/probe_protected_resource/field_present#1` | conditional | `other` | The agent deployment under test must actually be OAuth-configured and serve RFC 9728 protected-resource metadata. The phase is `optional: true` and the storyboard explicitly tells  |
| `security_baseline/probe_protected_resource/resource_equals_agent_url` | conditional | `other` | The agent deployment under test must actually be OAuth-configured and serve RFC 9728 protected-resource metadata. The phase is `optional: true` and the storyboard explicitly tells  |
| `security_baseline/probe_auth_server_metadata/http_status` | conditional | `prior_state`, `other` | The issuer to probe comes from the prior step's PRM document, and a real HTTPS OAuth authorization server must exist and serve an RFC 8414 metadata document at <issuer>/.well-known |
| `security_baseline/probe_auth_server_metadata/field_present` | conditional | `prior_state`, `other` | The issuer to probe comes from the prior step's PRM document, and a real HTTPS OAuth authorization server must exist and serve an RFC 8414 metadata document at <issuer>/.well-known |
| `security_baseline/probe_auth_server_metadata/field_present#1` | conditional | `prior_state`, `other` | The issuer to probe comes from the prior step's PRM document, and a real HTTPS OAuth authorization server must exist and serve an RFC 8414 metadata document at <issuer>/.well-known |
| `security_baseline/assert_mechanism/any_of` | not_wireable | — | There is no request to send and no response to read: the step's task is `assert_contribution`, a runner-internal aggregation over branch_set flags accumulated from earlier phases. |
| `stale_response_advisory/force_upstream_unavailable/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/force_upstream_unavailable/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/force_upstream_unavailable/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/response_schema` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/field_present` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/field_value` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/field_value#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/field_present#1` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/field_present#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/field_value#2` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `stale_response_advisory/stale_response_wire_placement/field_present#3` | not_wireable | — | requires comply_test_controller, which will not be implemented |
| `webhook_emission/trigger_idempotent_webhook_replay/field_value` | conditional | `prior_state`, `webhook_receiver` | The replay only means anything after trigger_idempotent_webhook_initial has run and cached a response, and both requests point at "{{runner.webhook_url:trigger_idempotent_webhook_i |
| `webhook_emission/sync_get_products_with_webhook_config_success/response_schema` | conditional | `webhook_receiver`, `seeded_account` | Same as the rejection branch: the sample_request carries "{{runner.webhook_url:sync_get_products_with_webhook_config_success}}", which the narrative forbids sending unresolved, and |
| `webhook_emission/sync_get_products_with_webhook_config_success/field_present` | conditional | `webhook_receiver`, `seeded_account` | Same as the rejection branch: the sample_request carries "{{runner.webhook_url:sync_get_products_with_webhook_config_success}}", which the narrative forbids sending unresolved, and |
| `webhook_emission/sync_get_products_with_webhook_config_success/field_absent` | conditional | `webhook_receiver`, `seeded_account` | Same as the rejection branch: the sample_request carries "{{runner.webhook_url:sync_get_products_with_webhook_config_success}}", which the narrative forbids sending unresolved, and |
| `webhook_emission/sync_get_products_with_webhook_config_success/field_value` | conditional | `webhook_receiver`, `seeded_account` | Same as the rejection branch: the sample_request carries "{{runner.webhook_url:sync_get_products_with_webhook_config_success}}", which the narrative forbids sending unresolved, and |
| `webhook_emission/sync_get_products_with_webhook_config_reject/error_code` | conditional | `webhook_receiver`, `seeded_account` | The request embeds a runner-hosted receiver URL that must be resolved to a real endpoint before sending, and it names a concrete brand/operator account that must exist for the whol |
| `webhook_emission/assert_synchronous_completion_handled/any_of` | conditional | `webhook_receiver`, `prior_state` | The step sends nothing of its own — "task: assert_contribution" is a synthetic aggregation over the two optional branch phases, so it can only be driven by first issuing the wholes |
| `webhook_emission/trigger_webhook_operation/expect_webhook` | conditional | `webhook_receiver` | The assertion is that a webhook ARRIVES: the step is `task: expect_webhook`-family with `triggered_by` scoping it to the per-step receiver URL (`{{runner.webhook_url:<step>}}`) and |
| `webhook_emission/trigger_operation_id_echo/expect_webhook` | conditional | `webhook_receiver` | The assertion is that a webhook ARRIVES: the step is `task: expect_webhook`-family with `triggered_by` scoping it to the per-step receiver URL (`{{runner.webhook_url:<step>}}`) and |
| `webhook_emission/trigger_idempotent_webhook_initial/expect_webhook` | conditional | `webhook_receiver` | The assertion is that a webhook ARRIVES: the step is `task: expect_webhook`-family with `triggered_by` scoping it to the per-step receiver URL (`{{runner.webhook_url:<step>}}`) and |
| `webhook_emission/trigger_retry_scenario/expect_webhook_retry_keys_stable` | conditional | `webhook_receiver` | The assertion is that a webhook ARRIVES: the step is `task: expect_webhook`-family with `triggered_by` scoping it to the per-step receiver URL (`{{runner.webhook_url:<step>}}`) and |
| `webhook_emission/fetch_brand_json/fetch_brand_jwks` | conditional | `signing_keypair` | Graded against the agent's PUBLISHED signing material, not a response we elicit: the step fetches brand.json, follows `agents[].jwks_uri`, and asserts a key with a webhook-valid pu |
| `webhook_emission/assert_webhook_signing_key_present/assert_jwks_purpose` | conditional | `signing_keypair` | Graded against the agent's PUBLISHED signing material, not a response we elicit: the step fetches brand.json, follows `agents[].jwks_uri`, and asserts a key with a webhook-valid pu |
| `webhook_emission/trigger_signed_webhook/expect_webhook_signature_valid` | conditional | `webhook_receiver` | The assertion is that a webhook ARRIVES: the step is `task: expect_webhook`-family with `triggered_by` scoping it to the per-step receiver URL (`{{runner.webhook_url:<step>}}`) and |

## 6. Neither scenario nor ticket

The list to take to triage: 3.1.1 grades these, we do not test them, and nothing in the tracker names them.

| Check | Storyboard | Required tools |
|---|---|---|
| `media_buy_seller/available_actions/get_product_allowed_actions/response_schema` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_product_allowed_actions/field_contains#3` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/sync_available_actions_creative/response_schema` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/sync_available_actions_creative/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/response_schema` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_value#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_contains#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/create_media_buy_with_available_actions/field_present#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_created_buy_available_actions/response_schema` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_contains#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/get_created_buy_available_actions/field_value#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/increase_budget/response_schema` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/increase_budget/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/increase_budget/field_present` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/increase_budget/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/increase_budget/field_contains#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/increase_budget/field_value#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_extend_requires_approval/error_code` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_extend_requires_approval/field_value#3` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/error_code` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_cancel_requires_approval/field_value#3` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/error_code` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_decrease_wrong_status/field_value#3` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/error_code` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#1` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#2` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_contains` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/available_actions/direct_pause_not_supported_on_product/field_value#3` | `protocols/media-buy/scenarios/available_actions.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/clicks_buy_flow/sync_accounts/response_schema` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/sync_accounts/field_present` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/get_products_for_clicks/response_schema` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/get_products_for_clicks/field_present` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/create_media_buy_clicks/response_schema` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/create_media_buy_clicks/field_present` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/simulate_clicks_delivery/field_value` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/response_schema` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/field_present` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/clicks_buy_flow/get_clicks_delivery/field_present#1` | `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/sync_accounts/response_schema` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/sync_accounts/field_present` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/get_products_for_cpcv/response_schema` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/get_products_for_cpcv/field_present` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_cpcv/response_schema` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_cpcv/field_present` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_with_phantom_view_duration/error_code` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/create_media_buy_with_phantom_view_duration/field_value` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/simulate_cpcv_delivery/field_value` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/response_schema` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/field_present` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/completed_views_buy_flow/get_cpcv_delivery/field_present#1` | `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/creative_reception/get_capabilities/response_schema` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/get_capabilities/field_present` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/get_capabilities/field_present#1` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/get_capabilities/field_value` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/sync_creatives/response_schema` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/sync_creatives/field_present` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/sync_creatives/field_present#1` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/sync_creatives/field_value` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/preview_synced/response_schema` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/preview_synced/field_present` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/preview_synced/field_present#1` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/creative_reception/preview_synced/field_value` | `protocols/media-buy/scenarios/creative_reception.yaml` | `sync_creatives` |
| `media_buy_seller/dependency_impairment/get_products_brief/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_products_brief/field_present` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_products_brief/field_present#1` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/create_buy/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/create_buy/field_present` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/create_buy/field_present#1` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/sync_creative/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/sync_creative/field_present` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/field_present` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/assign_creative_to_package/field_contains` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/force_creative_approved/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/force_creative_approved/field_value` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_baseline/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value#1` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_baseline/field_value_or_absent` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/force_creative_rejected/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/force_creative_rejected/field_value` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/field_value` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/reread_creative_rejected/field_value#1` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_impaired/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_value` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_present` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_impaired/field_contains` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/sync_replacement_creative/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/sync_replacement_creative/field_present` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/force_replacement_approved/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/force_replacement_approved/field_value` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/swap_assignment/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/swap_assignment/field_present` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/swap_assignment/field_contains` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_recovered/response_schema` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_recovered/field_value` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment/get_buy_recovered/field_value_or_absent` | `protocols/media-buy/scenarios/dependency_impairment.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/get_products_brief/field_present#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/create_buy_two_packages/field_present#2` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/sync_two_creatives/field_present#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_contains` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/assign_creatives_to_packages/field_contains#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_both_approved/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_both_approved/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_b_approved/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_b_approved/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/baseline_healthy/field_value_or_absent` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_a_rejected/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_a_rejected/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/reread_a_rejected/field_value#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_one/field_value#2` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_b_rejected/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_b_rejected/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/reread_b_rejected/field_value#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_two/field_present#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_c/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_c/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_c_approved/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_c_approved/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_a/field_contains` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value#1` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_back_to_one/field_value_or_absent` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_d/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/sync_replacement_d/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_d_approved/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/force_d_approved/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/field_present` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/swap_package_b/field_contains` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/response_schema` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/field_value` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/dependency_impairment_cardinality/verify_cardinality_zero/field_value_or_absent` | `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buys`, `get_products`, `list_creatives`, `sync_creatives`, `update_media_buy` |
| `media_buy_seller/event_dedup_flow/sync_accounts/response_schema` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/sync_accounts/field_present` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/get_products_for_dedup/response_schema` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/get_products_for_dedup/field_present` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/sync_event_sources/response_schema` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/sync_event_sources/field_present` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/sync_event_sources/field_present#1` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/create_media_buy_dedup/response_schema` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/create_media_buy_dedup/field_present` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/log_event_from_pixel/response_schema` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/log_event_from_capi/response_schema` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/simulate_deduplicated_delivery/field_value` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/get_dedup_delivery/response_schema` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/event_dedup_flow/get_dedup_delivery/field_value` | `protocols/media-buy/scenarios/event_dedup_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `log_event`, `sync_event_sources` |
| `media_buy_seller/frequency_cap_enforcement/sync_accounts/response_schema` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/sync_accounts/field_present` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/get_products_for_frequency_cap/response_schema` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/get_products_for_frequency_cap/field_present` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/create_media_buy_with_frequency_cap/response_schema` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/create_media_buy_with_frequency_cap/field_present` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/simulate_capped_delivery/field_value` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/response_schema` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_present` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_present#1` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/frequency_cap_enforcement/get_capped_delivery/field_less_than` | `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_present` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_capabilities/field_value#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_present#2` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_canonical_format/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_present` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_present#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_canonical_inline_creative/field_value#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_equals_context` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_equals_context#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_contains` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_canonical_inline_creative/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_present` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_present#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_products_legacy_format/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_present` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_present#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/create_buy_with_legacy_inline_creative/field_value#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_equals_context` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_equals_context#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_contains` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/update_buy_with_replacement_legacy_inline_creative/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_equals_context` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_equals_context#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_canonical_media_buy_after_inline_replacement/field_value#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/response_schema` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_equals_context` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_equals_context#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_value` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/inline_creatives_without_sync/get_legacy_media_buy_after_inline_replacement/field_value#1` | `protocols/media-buy/scenarios/inline_creatives_without_sync.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `update_media_buy` |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/response_schema` | `protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml` | `get_media_buys` |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value` | `protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml` | `get_media_buys` |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value#1` | `protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml` | `get_media_buys` |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_absent` | `protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml` | `get_media_buys` |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value#2` | `protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml` | `get_media_buys` |
| `media_buy_seller/package_correlation_legacy_fallback/get_seeded_legacy_buy/field_value#3` | `protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml` | `get_media_buys` |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/response_schema` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/field_present` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/get_products_brief/field_present#1` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/response_schema` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_present` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#1` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_present#1` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#2` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_equals_context` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/create_buy_no_creatives/field_value#3` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/sync_creative/response_schema` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/response_schema` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_present` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_contains` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_value` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/assign_creative_to_package/field_value#1` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/response_schema` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_value` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_equals_context` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/pending_creatives_to_start/get_media_buy_after_sync/field_value#1` | `protocols/media-buy/scenarios/pending_creatives_to_start.yaml` | `create_media_buy`, `get_media_buys`, `get_products`, `sync_creatives` |
| `media_buy_seller/per_creative_conversion_attribution/sync_accounts/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/sync_accounts/field_present` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/get_products_for_per_creative/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/get_products_for_per_creative/field_present` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/field_present` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/sync_event_sources/upstream_traffic` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/field_present` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/sync_two_creatives/field_present#1` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/create_media_buy_two_creatives/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/create_media_buy_two_creatives/field_present` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/log_purchase_event_1/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/log_purchase_event_2/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/simulate_per_creative_delivery/field_value` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/response_schema` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#1` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#2` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/per_creative_conversion_attribution/get_per_creative_delivery/field_present#3` | `protocols/media-buy/scenarios/per_creative_conversion_attribution.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_creatives`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/sync_accounts/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/sync_accounts/field_present` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/get_products_for_performance/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/get_products_for_performance/field_present` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/sync_event_sources/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/sync_event_sources/field_present` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/sync_event_sources/field_present#1` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/create_media_buy_cpa/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/create_media_buy_cpa/field_present` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/create_media_buy_with_phantom_source/error_code` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/create_media_buy_with_phantom_source/field_value` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/log_purchase_event/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/log_purchase_event/upstream_traffic` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/simulate_performance_delivery/field_value` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/field_present` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow/get_attributed_delivery/field_present#1` | `protocols/media-buy/scenarios/performance_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/sync_accounts/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/sync_accounts/field_present` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/get_products_for_roas/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/get_products_for_roas/field_present` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/field_present` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/field_present#1` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/sync_event_sources/upstream_traffic` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_roas/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_roas/field_present` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_per_ad_spend_no_value_field/error_code` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/create_media_buy_per_ad_spend_no_value_field/field_value` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/log_purchase_event/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/log_purchase_event/upstream_traffic` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/simulate_roas_delivery/field_value` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/response_schema` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#1` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#2` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/performance_buy_flow_roas/get_attributed_roas_delivery/field_present#3` | `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products`, `log_event`, `sync_event_sources` |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/response_schema` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/field_present` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/get_products_with_accepted_verifiers/field_value` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/response_schema` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_absent` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value#1` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_absent#1` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/field_value#2` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/upstream_traffic` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/sync_creatives_carveout_claim/upstream_traffic#1` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/response_schema` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#1` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#2` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_directed_audit_observation/field_value#3` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/response_schema` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#1` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#2` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_audit_observation/query_edited_audit_observation/field_value#3` | `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | `comply_test_controller`, `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/get_products_with_accepted_verifiers/response_schema` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/get_products_with_accepted_verifiers/field_present` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/get_products_with_accepted_verifiers/field_value` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/response_schema` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#1` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_present` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_present#1` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#2` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#3` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_contradicted/field_value#4` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_consistent/response_schema` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_consistent/field_value` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/provenance_truth_of_claim/sync_creatives_consistent/field_value#1` | `protocols/media-buy/scenarios/provenance_truth_of_claim.yaml` | `get_products`, `sync_creatives` |
| `media_buy_seller/reach_buy_flow/sync_accounts/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/sync_accounts/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_products_for_reach/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_products_for_reach/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_with_unsupported_reach_unit/error_code` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_with_unsupported_reach_unit/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/simulate_reach_delivery/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_reach_delivery/field_present#1` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_cumulative_reach/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_cumulative_reach/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/simulate_cumulative_reach/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_cumulative_reach_delivery/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_period_reach/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_period_reach/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/simulate_period_reach/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_period_reach_delivery/field_present#1` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_rolling_reach/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_rolling_reach/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/simulate_rolling_reach/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_rolling_reach_delivery/field_present#1` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach_no_window/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/create_media_buy_reach_no_window/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/simulate_reach_no_window/field_value` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_delivery_reach_no_window/response_schema` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/reach_buy_flow/get_delivery_reach_no_window/field_present` | `protocols/media-buy/scenarios/reach_buy_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_media_buy_delivery`, `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/sync_accounts/response_schema` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/sync_accounts/field_present` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief/response_schema` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief/field_present` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_brief_second/field_present` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_mixed_finalize/error_code` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_mixed_finalize/field_present` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_product_finalize/error_code` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/response_schema` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_present` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_contains` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_contains#1` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#1` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#2` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_atomic/field_value#3` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/get_products_multi_finalize_unsupported/error_code` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_finalize_exclusivity/assert_multi_finalize/any_of` | `protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml` | `get_products` |
| `media_buy_seller/refine_products/sync_accounts/response_schema` | `protocols/media-buy/scenarios/refine_products.yaml` | `get_products` |
| `media_buy_seller/refine_products/sync_accounts/field_present` | `protocols/media-buy/scenarios/refine_products.yaml` | `get_products` |
| `media_buy_seller/refine_products/get_products_brief/response_schema` | `protocols/media-buy/scenarios/refine_products.yaml` | `get_products` |
| `media_buy_seller/refine_products/get_products_brief/field_present` | `protocols/media-buy/scenarios/refine_products.yaml` | `get_products` |
| `media_buy_seller/refine_products/get_products_brief/field_present#1` | `protocols/media-buy/scenarios/refine_products.yaml` | `get_products` |
| `media_buy_seller/refine_products/get_products_refine/response_schema` | `protocols/media-buy/scenarios/refine_products.yaml` | `get_products` |
| `media_buy_seller/refine_products/get_products_refine/field_present` | `protocols/media-buy/scenarios/refine_products.yaml` | `get_products` |
| `media_buy_seller/vendor_metric_catalog_precondition/sync_accounts/response_schema` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/sync_accounts/field_present` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_value` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_present` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/seed_attention_vendor_catalog/field_value#1` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_accept/response_schema` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_accept/field_present` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/create_media_buy_catalog_miss_reject/error_code` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_catalog_precondition/assert_vendor_metric_catalog_miss_handled/any_of` | `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | `comply_test_controller`, `create_media_buy`, `sync_accounts` |
| `media_buy_seller/vendor_metric_optimization_flow/sync_accounts/response_schema` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/sync_accounts/field_present` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/response_schema` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present#1` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_present#2` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value#1` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/get_products_vendor_metric_opt/field_value#2` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_positive/response_schema` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_positive/field_present` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_targetless_positive/response_schema` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_targetless_positive/field_present` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_metric/error_code` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_metric/field_value` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_target/error_code` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unsupported_target/field_value` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_missing_committed/error_code` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_missing_committed/field_value` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unreportable_metric/error_code` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_seller/vendor_metric_optimization_flow/create_media_buy_unreportable_metric/field_value` | `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | `comply_test_controller`, `create_media_buy`, `get_products` |
| `media_buy_state_machine/get_capabilities/response_schema` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/get_capabilities/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/get_capabilities/field_present#1` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/get_capabilities/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/discover_products/response_schema` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/discover_products/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/discover_products/field_present#1` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/discover_products/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/discover_products/field_present#2` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/discover_products/field_present#3` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/discover_products/field_present#4` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/sync_creative/response_schema` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/sync_creative/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/sync_creative/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/create_buy/response_schema` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/create_buy/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/create_buy/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/create_buy/field_present#1` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/create_buy/field_value#1` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/create_buy/field_present#2` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/pause_buy/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/pause_buy/field_present#1` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/pause_buy/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/resume_buy/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/resume_buy/field_present#1` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/resume_buy/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/cancel_buy/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/cancel_buy/field_present#1` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/cancel_buy/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/pause_canceled_buy/error_code` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/pause_canceled_buy/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/pause_canceled_buy/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/resume_canceled_buy/error_code` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/resume_canceled_buy/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/resume_canceled_buy/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/recancel_buy/error_code` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/recancel_buy/field_present` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `media_buy_state_machine/recancel_buy/field_value` | `protocols/media-buy/state-machine.yaml` | `create_media_buy`, `sync_creatives`, `update_media_buy` |
| `sales_non_guaranteed/get_capabilities/response_schema` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_capabilities/field_present` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_capabilities/field_contains` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_capabilities/field_contains#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_capabilities/field_present#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_capabilities/field_value` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/response_schema` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#2` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#3` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#4` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#5` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#6` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#7` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#8` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_value` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#9` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#10` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_products_brief/field_present#11` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/sync_governance/response_schema` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/sync_governance/field_value` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/sync_governance/field_present` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/sync_governance/field_value#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/create_media_buy/response_schema` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/create_media_buy/field_present` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/create_media_buy/field_value` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/create_media_buy/field_present#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/create_media_buy/upstream_traffic` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_media_buys_pacing/response_schema` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_media_buys_pacing/field_present` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_media_buys_pacing/field_present#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_media_buys_pacing/field_value` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/update_media_buy/response_schema` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/update_media_buy/field_present` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/update_media_buy/field_contains` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/update_media_buy/field_contains#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/update_media_buy/field_present#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/update_media_buy/field_value` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/update_media_buy/upstream_traffic` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_delivery/response_schema` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_delivery/field_present` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_delivery/field_present#1` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `sales_non_guaranteed/get_delivery/field_value` | `specialisms/sales-non-guaranteed/index.yaml` | `create_media_buy`, `get_products`, `sync_governance` |
| `get_media_buys_pagination_integrity/get_capabilities/response_schema` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/get_capabilities/field_present` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/get_capabilities/field_present#1` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/get_capabilities/field_value` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/list_call/response_schema` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/list_call/field_present` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/list_call/field_present#1` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/list_call/field_present#2` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_media_buys_pagination_integrity/list_call/field_value` | `universal/get-media-buys-pagination-integrity.yaml` | `get_media_buys` |
| `get_products_pagination_integrity/get_capabilities/response_schema` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/get_capabilities/field_present` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/get_capabilities/field_present#1` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/get_capabilities/field_value` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/response_schema` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_present` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_value` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_contains` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_absent` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_value#1` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_present#1` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_value_or_absent` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_present#2` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_first_page/field_value#2` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/response_schema` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_present` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_contains` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_absent` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value#1` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value_or_absent` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value_or_absent#1` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_present#1` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_products_pagination_integrity/wholesale_terminal_page/field_value#2` | `universal/get-products-pagination-integrity.yaml` | `get_products` |
| `get_signals_pagination_integrity/get_capabilities/response_schema` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/get_capabilities/field_present` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/get_capabilities/field_present#1` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/get_capabilities/field_value` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/first_page/response_schema` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/first_page/field_value` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/first_page/field_present` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/first_page/field_present#1` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/first_page/field_value#1` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/next_page/response_schema` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/next_page/field_present` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `get_signals_pagination_integrity/next_page/field_value` | `universal/get-signals-pagination-integrity.yaml` | `get_signals` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/response_schema` | `universal/notification-config-event-scope.yaml` | `sync_accounts` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value` | `universal/notification-config-event-scope.yaml` | `sync_accounts` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#1` | `universal/notification-config-event-scope.yaml` | `sync_accounts` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#2` | `universal/notification-config-event-scope.yaml` | `sync_accounts` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#3` | `universal/notification-config-event-scope.yaml` | `sync_accounts` |
| `notification_config_event_scope/sync_accounts_rejects_scheduled_account_notification/field_value#4` | `universal/notification-config-event-scope.yaml` | `sync_accounts` |
| `pagination_integrity_creative_formats/get_capabilities/response_schema` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/get_capabilities/field_present` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/get_capabilities/field_present#1` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/get_capabilities/field_value` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/seed_format_1/field_value` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/seed_format_2/field_value` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/first_page/response_schema` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/first_page/field_value` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/first_page/field_present` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/first_page/field_value_or_absent` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/first_page/field_present#1` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/first_page/field_value#1` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/terminal_page/response_schema` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/terminal_page/field_value` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/terminal_page/field_value_or_absent` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/terminal_page/field_value_or_absent#1` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/terminal_page/field_present` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_creative_formats/terminal_page/field_value#1` | `universal/pagination-integrity-creative-formats.yaml` | `list_creative_formats` |
| `pagination_integrity_list_accounts/get_capabilities/response_schema` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/get_capabilities/field_present` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/get_capabilities/field_present#1` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/get_capabilities/field_value` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/seed_account_1/field_value` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/seed_account_2/field_value` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/seed_account_3/field_value` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/first_page/response_schema` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/first_page/field_value` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/first_page/field_present` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/first_page/field_present#1` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/first_page/field_value#1` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/next_page/response_schema` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/next_page/field_present` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/next_page/field_present#1` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `pagination_integrity_list_accounts/next_page/field_value` | `universal/pagination-integrity-list-accounts.yaml` | `list_accounts` |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/response_schema` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/field_present` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/field_present#1` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_with_idempotency_key/field_value` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_products_with_idempotency_key/response_schema` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_products_with_idempotency_key/field_present` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_products_with_idempotency_key/field_present#1` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_products_with_idempotency_key/field_value` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_accounts_with_idempotency_key/response_schema` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_accounts_with_idempotency_key/field_present` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_accounts_with_idempotency_key/field_present#1` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_accounts_with_idempotency_key/field_value` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/response_schema` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/field_present` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/field_present#1` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creative_formats_with_idempotency_key/field_value` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creatives_with_idempotency_key/response_schema` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creatives_with_idempotency_key/field_present` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creatives_with_idempotency_key/field_present#1` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/list_creatives_with_idempotency_key/field_value` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_accept/response_schema` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_accept/field_present` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_accept/field_value` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_reject/error_code` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_reject/field_present` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/get_capabilities_without_idempotency_key_3_1_reject/field_value` | `universal/read-tool-idempotency.yaml` | — |
| `read_tool_idempotency/assert_omitted_key_grace_handled/any_of` | `universal/read-tool-idempotency.yaml` | — |
| `stale_response_advisory/get_capabilities/response_schema` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/get_capabilities/field_present` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/get_capabilities/field_present#1` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/get_capabilities/field_value` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/force_upstream_unavailable/response_schema` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/force_upstream_unavailable/field_present` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/force_upstream_unavailable/field_value` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/response_schema` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/field_present` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/field_value` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/field_value#1` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/field_present#1` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/field_present#2` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/field_value#2` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/stale_response_wire_placement/field_present#3` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/no_stale_on_healthy_upstream/response_schema` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/no_stale_on_healthy_upstream/field_present` | `universal/stale-response-advisory.yaml` | `get_products` |
| `stale_response_advisory/no_stale_on_healthy_upstream/field_value` | `universal/stale-response-advisory.yaml` | `get_products` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/response_schema` | `universal/wholesale-feed-bulk-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value` | `universal/wholesale-feed-bulk-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value#1` | `universal/wholesale-feed-bulk-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value#2` | `universal/wholesale-feed-bulk-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_bulk_webhooks/register_bulk_change_webhook/field_value#3` | `universal/wholesale-feed-bulk-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/response_schema` | `universal/wholesale-feed-product-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value` | `universal/wholesale-feed-product-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value#1` | `universal/wholesale-feed-product-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value#2` | `universal/wholesale-feed-product-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_product_webhooks/register_product_pricing_webhook/field_value#3` | `universal/wholesale-feed-product-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_products/bootstrap_products/response_schema` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/bootstrap_products/field_present` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/bootstrap_products/field_present#1` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/bootstrap_products/field_value` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/bootstrap_products/field_absent` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/bootstrap_products/field_value#1` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/unchanged_probe/response_schema` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/unchanged_probe/field_value` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/unchanged_probe/field_equals_context` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/unchanged_probe/field_value#1` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/unchanged_probe/field_absent` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/unchanged_probe/field_value#2` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_products/standalone_pricing_token_rejected/error_code` | `universal/wholesale-feed-products.yaml` | `get_products` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/response_schema` | `universal/wholesale-feed-signal-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value` | `universal/wholesale-feed-signal-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value#1` | `universal/wholesale-feed-signal-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value#2` | `universal/wholesale-feed-signal-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_signal_webhooks/register_signal_pricing_webhook/field_value#3` | `universal/wholesale-feed-signal-webhooks.yaml` | `sync_accounts` |
| `wholesale_feed_signals/bootstrap_signals/response_schema` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/bootstrap_signals/field_present` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/bootstrap_signals/field_present#1` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/bootstrap_signals/field_value` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/bootstrap_signals/field_value#1` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/unchanged_probe/response_schema` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/unchanged_probe/field_value` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/unchanged_probe/field_equals_context` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/unchanged_probe/field_value#1` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/unchanged_probe/field_absent` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/unchanged_probe/field_value#2` | `universal/wholesale-feed-signals.yaml` | `get_signals` |
| `wholesale_feed_signals/standalone_pricing_token_rejected/error_code` | `universal/wholesale-feed-signals.yaml` | `get_signals` |

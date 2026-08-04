# SB-5d: `comply_test_controller` — recorded divergence and triage

beads: `salesagent-n63t`. Epic: `salesagent-xg5w`.

## Part 1 — the divergence

**Decision:** `comply_test_controller` will not be implemented, in any
environment, sandbox included. This is a deliberate, owner-approved product
decision, not a gap to close later.

### The spec does not require it

`comply_test_controller` is documented at
`dist/docs/3.1.1/building/by-layer/L3/comply-test-controller.mdx` (adcp
checkout, pinned 3.1.1). The spec's own framing:

> The compliance test controller is a dev/staging-only affordance, not a
> production-time concept. AAO grading does NOT require or use it. The AAO
> compliance heartbeat drives storyboards against the seller's registered
> production URL with `account.sandbox: true` on every request, and the
> seller's prod stack is responsible for honoring the flag — no controller
> endpoint needed.
>
> Sellers MAY implement the controller in their dev or staging environment
> to support their own integration testing... It MUST NOT be exposed on
> production deployments.

So conformance at 3.1.1 does not hinge on this tool existing anywhere. What
the spec mandates is the opposite direction — a **MUST NOT** on production
exposure, with an elaborate sandbox-gating contract (absent from
`tools/list`/`skills[]`, absent from `get_adcp_capabilities`, dispatch
returns the transport's unknown-tool error, `FORBIDDEN` reserved for
authenticated-sandbox-caller-references-live-account). Declining to build
the tool at all is a strict subset of "gate it correctly" — there is no
surface to leak, no gate to get wrong, no per-principal projection logic to
maintain.

### Why we decline the optional affordance anyway

The tool's own schema
(`comply-test-controller-request.json` / same `.mdx`) is a single endpoint
whose `scenario` enum includes `force_account_status`, `force_media_buy_status`,
`force_creative_status`, `force_session_status`, `force_task_completion`,
`simulate_delivery`, `simulate_budget_spend`, and a family of `seed_*`
fixture-injection scenarios — i.e. one authenticated call that can force any
tenant's account/media-buy/creative/session into an arbitrary state on
demand. That is the shape of a privileged admin backdoor regardless of which
environment it's wired into; "sandbox-only" is a deployment-topology
argument, not a design argument that removes the hazard from the codebase.
The owner's call is not to build that shape of endpoint at all, in this
product, ever — matching the spec's own characterization of the tool as
optional tooling for the seller's *own* integration testing, not a
conformance-graded surface.

### What this means for storyboards that name it

29 storyboards in the pinned 3.1.1 fixture
(`tests/fixtures/adcp_storyboards_pinned/index.json`) list
`comply_test_controller` in `required_tools`. Of those, 20 sit on our
declared conformance path with no scenario today (the "on-path, NOT COVERED"
58 in `docs/test-obligations/storyboard-coverage-map.md` — that total is now 51
after salesagent-pw71 (SB-5b) fixed the coverage map's parsing bugs; the
comply_test_controller total of 29 above is unaffected, since it comes from
`required_tools` extraction, not the fixed window/key logic). Every storyboard
step that dispatches `task: comply_test_controller` is permanently
unreachable for us — not "pending implementation," not a coverage gap to
close, a **closed** branch. These 20 stay dormant/ungraded by design. See
the triage below for which of them can still be exercised *around* that
missing tool, via real AdCP calls instead.

This entry belongs in the same family as the `media_buy_status` dual-emit
divergence recorded in `docs/adcp-spec-version.md` § "Behavior target vs SDK
pin," and the "known WRONG" items in
`.claude/notes/storyboard-conformance/README.md`: a considered choice,
cited against the spec, recorded so nobody re-discovers "why don't we
implement comply_test_controller" as an open question.

## Part 2 — triage of the 20

**Method.** Cross-referenced `tests/fixtures/adcp_storyboards_pinned/index.json`
`required_tools` against the 58 "on-path, NOT COVERED" rows in
`docs/test-obligations/storyboard-coverage-map.md` → 20 storyboards. For each,
read the actual scenario YAML at
`~/projects/adcp/dist/compliance/3.1.1/<path>` (git checkout, pinned 3.1.1) —
every `phases[].steps[]` entry whose `task` is `comply_test_controller`, plus
`prerequisites`/`narrative` for the 5 files where the tool is declared but no
step in `phases` actually calls it (those declare
`prerequisites.controller_seeding: true` instead — a **fixture-seeding**
convention documented at
`dist/docs/3.1.1/contributing/storyboard-authoring.md` L106: "tell the
runner to auto-inject a fixtures phase before the main phases," distinct from
a graded runtime step).

**Bucket test applied:** does any *other*, already-real AdCP tool or
mechanism in this codebase reach the same precondition state? If yes →
PRIOR STATE ONLY. If the state is a forced/injected fault, an exact
numeric delivery result, a terminal-state jump, or third-party data we do
not own → DETERMINISTIC INJECTION.

| Storyboard | Bucket | Why |
|---|---|---|
| `protocols/media-buy/scenarios/audience_buy_flow.yaml` | DETERMINISTIC INJECTION | `simulate_audience_delivery` forces exact impressions/spend into `get_media_buy_delivery`. No AdCP tool writes delivery numbers; only the controller's `simulate_delivery` does — real ad-serving delivery is time-accrued and non-deterministic. |
| `protocols/media-buy/scenarios/billing_finality_delivery.yaml` | DETERMINISTIC INJECTION | `simulate_provisional_delivery` / `simulate_final_delivery` force provisional and post-finalization delivery snapshots with a finalization timestamp — same "no tool writes delivery" gap. |
| `protocols/media-buy/scenarios/canonical_formats.yaml` | PRIOR STATE ONLY | Tool declared only via `prerequisites.controller_seeding: true` (product catalog: dual `format_ids`/`format_options`). Our products are seller-configured, not buyer-created over the wire — real product setup reaches the same state. |
| `protocols/media-buy/scenarios/clicks_buy_flow.yaml` | DETERMINISTIC INJECTION | `simulate_clicks_delivery` forces impressions+clicks+spend — delivery-injection class, same as audience/billing above. |
| `protocols/media-buy/scenarios/completed_views_buy_flow.yaml` | DETERMINISTIC INJECTION | `simulate_cpcv_delivery` forces impressions+completed_views+spend — delivery-injection class. |
| `protocols/media-buy/scenarios/dependency_impairment.yaml` | PRIOR STATE ONLY | `force_creative_approved`/`force_creative_rejected`/`force_replacement_approved` transition creative review status. Our real creative-review path already does this: `sync_creatives` → auto-approve gate (`src/adapters/mock_creative_engine.py` `auto_approve_format_ids`) or the real admin review action (`src/admin/blueprints/creatives.py::review_creatives`, which sets `creative.status = "rejected"`). No controller needed to reach approved/rejected. |
| `protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml` | PRIOR STATE ONLY | Same mechanism as above, applied to 4 creatives (A/B/C/D) instead of 1. |
| `protocols/media-buy/scenarios/frequency_cap_enforcement.yaml` | DETERMINISTIC INJECTION | `simulate_capped_delivery` forces delivery with an exact observed frequency value — delivery-injection class. |
| `protocols/media-buy/scenarios/get_products_async.yaml` | DETERMINISTIC INJECTION | `force_get_products_submitted`/`complete_products_task` force an async `submitted → completed` task arm for `get_products`. Our `get_products` (`src/core/tools/products.py::_get_products_impl`) is fully synchronous — there is no task lifecycle to sequence into; the "submitted" arm cannot occur under real operation. |
| `protocols/media-buy/scenarios/performance_buy_flow.yaml` | DETERMINISTIC INJECTION | `simulate_performance_delivery` forces impressions+conversions+spend — delivery-injection class. |
| `protocols/media-buy/scenarios/performance_buy_flow_roas.yaml` | DETERMINISTIC INJECTION | `simulate_roas_delivery` — same class, ROAS variant. |
| `protocols/media-buy/scenarios/pricing_currency_filter.yaml` | PRIOR STATE ONLY | Tool declared only via `prerequisites.controller_seeding: true` (product `pricing_options` in multiple currencies) — our own catalog config, same reasoning as `canonical_formats.yaml`. |
| `protocols/media-buy/scenarios/product_signal_targeting.yaml` | PRIOR STATE ONLY | `prerequisites.controller_seeding: true` seeds a product plus a `get_signals` wholesale feed — both are our own seller-declared catalogs (products and signals), not third-party data; reachable via real catalog/product configuration. |
| `protocols/media-buy/scenarios/provenance_audit_observation.yaml` | DETERMINISTIC INJECTION | `query_directed_audit_observation`/`query_edited_audit_observation` read the controller's internal audit trail. The storyboard's own `expected:` text says it plainly: "Public seller responses are not required to expose this internal audit log." There is no public/real equivalent to query. |
| `protocols/media-buy/scenarios/reach_buy_flow.yaml` | DETERMINISTIC INJECTION | `simulate_reach_delivery` plus 4 reach-window variants (cumulative/period/rolling/absent) all force exact reach+frequency delivery rows — delivery-injection class. |
| `protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml` | DETERMINISTIC INJECTION | `seed_attention_vendor_catalog` seeds `attentionvendor.example`'s published `measurement.metrics[]` catalog — the storyboard's own narrative calls this a "deterministic **external** catalog miss." This is a third-party vendor's data, not ours to configure; no real API sequence produces a controlled miss/hit against someone else's real catalog. |
| `protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml` | PRIOR STATE ONLY | `prerequisites.controller_seeding: true` seeds a product's own `vendor_metric_optimization.supported_metrics[]` — our catalog, same reasoning as `canonical_formats.yaml`/`pricing_currency_filter.yaml`. (Contrast with `vendor_metric_catalog_precondition.yaml` above, which seeds the *external vendor's* catalog, not the product's.) |
| `universal/canonical-format-validate-input.yaml` | PRIOR STATE ONLY | `prerequisites.controller_seeding: true` seeds one product declaring `synthesis_nondeterministic: true` — our own catalog, same reasoning as the other `controller_seeding` rows. |
| `universal/comply-controller-mode-gate.yaml` | DETERMINISTIC INJECTION | `deny_live_caller` tests that `comply_test_controller` itself returns `FORBIDDEN` for a live-mode account reference — i.e. it grades the controller's own sandbox-gating behavior. Moot: there is no controller to gate. |
| `universal/deterministic-testing.yaml` | DETERMINISTIC INJECTION | This is the controller's own meta-storyboard — `list_scenarios`, `force_account_*`, `force_media_buy_*`, `force_creative_*`, `force_session_terminated`, `simulate_delivery`, `simulate_budget_95`/`100`, `unknown_scenario`/`missing_params`/`not_found_entity` error paths. Every phase exists to validate the tool we are not building. |

### Final count

**13 DETERMINISTIC INJECTION** (stay dormant/ungraded — expected, no action):
`audience_buy_flow`, `billing_finality_delivery`, `clicks_buy_flow`,
`completed_views_buy_flow`, `frequency_cap_enforcement`,
`get_products_async`, `performance_buy_flow`, `performance_buy_flow_roas`,
`provenance_audit_observation`, `reach_buy_flow`,
`vendor_metric_catalog_precondition`, `comply-controller-mode-gate`,
`deterministic-testing`.

**7 PRIOR STATE ONLY** (potentially reachable via real API sequencing once
multi-tool sequencing is cheap — see `salesagent-xxa1`/`salesagent-geru`,
the transport-generic client design in
`.claude/notes/storyboard-conformance/sb2a-transport-generic-client-design.md`):
`canonical_formats`, `dependency_impairment`,
`dependency_impairment_cardinality`, `pricing_currency_filter`,
`product_signal_targeting`, `vendor_metric_optimization_flow`,
`canonical-format-validate-input`.

### The ticket's unverified expectation was wrong

The expectation going in was "most of the 20 are PRIOR STATE ONLY, now that
multi-tool sequencing is cheap." Counted, not assumed: **13/20 (65%) are
DETERMINISTIC INJECTION, only 7/20 (35%) are PRIOR STATE ONLY.** The
dominant pattern among these 20 specifically is not "sequence two real
tool calls," it's "force an exact delivery number/state that no AdCP tool
can write" — 11 of the 13 deterministic-injection storyboards are
delivery-metric simulation (`simulate_*_delivery`), because `get_media_buy_delivery`
is read-only everywhere in this protocol and only the test controller can
inject numbers into it. The `controller_seeding`-only storyboards (catalog
fixtures, not runtime state-forcing) are the reliably-reachable group, and
that group is smaller than assumed.

Two of the 7 PRIOR STATE ONLY storyboards (`dependency_impairment`,
`dependency_impairment_cardinality`) are reachable today, in principle,
through code that already exists (`sync_creatives` + the real admin review
action) — the missing piece for those two is BDD/harness wiring
(`salesagent-xxa1`/`geru`), not new production behavior. The other 5
(`canonical_formats`, `pricing_currency_filter`, `product_signal_targeting`,
`vendor_metric_optimization_flow`, `canonical-format-validate-input`) need a
real path to configure products/pricing/signals with the specific declared
shapes each storyboard's fixtures ask for (dual-format, multi-currency
pricing, wholesale signal groups, vendor-metric optimization support,
nondeterministic-synthesis flag) — establishable via our own product-catalog
configuration, but that path is not yet exercised by any harness Given step
today; this triage doesn't claim the wiring exists, only that the
*mechanism* to reach the state is real and controller-free.

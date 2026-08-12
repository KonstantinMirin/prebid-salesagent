# Business Rules -- Test Obligations — AdCP 3.1.1

## Spec grounding — AdCP 3.1.1

Grounded against the version this repo pins, resolved from
`docs/adcp-spec-version.md` (never hardcoded here). Citations use the form
`repo=adcp ref=3.1.1 path=<compliance-tree path>`.

This replaces a "3.6 Upgrade Impact" table framed against the `adcp 3.2.0 ->
3.6.0` SDK upgrade. Each row below was re-checked against the pinned schema
bundle; the verdict column says what was verified, not what the upgrade did.

| Rule | Verified at 3.1.1 | Bug |
|------|-------------------|-----|
| BR-RULE-006 | HOLDS. `core/pricing-option.json` is a `oneOf` over exactly 9 branches (cpm, vcpm, cpc, cpcv, cpv, cpp, cpa, flat_rate, time), discriminated on `pricing_model`. `pricing-options/cpa-option.json` does carry `exclusiveMinimum: 0` on `fixed_price` | salesagent-mq3n |
| BR-RULE-007 | HOLDS. `core/product.json` has `additionalProperties: true` and all 7 named fields | salesagent-qo8a (FIXED) |
| BR-RULE-011 | HOLDS. `min_spend_per_package` is present on the pricing-option branches (spot-checked cpm and cpa) | salesagent-mq3n |
| BR-RULE-015 | HOLDS. `core/creative-asset.json` exists at the pin | salesagent-goy2 |
| BR-RULE-021 | Re-check pending — the row's own citation (salesagent-7gnv, "MediaBuy boundary drops buyer_campaign_ref") is false at the pin: `core/media-buy.json` has no `buyer_campaign_ref`. See constraints.md's grounding table | salesagent-7gnv |
| BR-RULE-008, 043, 048, 051-078 | Decided individually — see each rule's own `**Grounded at 3.1.1:**` verdict below | -- |

**Every one of the 72 per-rule verdicts below has been individually re-decided
against the pin** and carries `**Grounded at 3.1.1:**` with the paths it was
checked against. Each was traced to the pinned tree, schema bundle or spec
prose, then adversarially re-verified — that second pass rejected 38 of the 202
verdicts across this file and `constraints.md`, mostly for citing a real file
that did not support the claim. Every citation path was then resolved
mechanically on disk (1423 references, 0 unresolvable, 0 pointing at a version
other than the pin).

`SPEC-SILENT` is a legitimate verdict here: several of these rules are our own
and have no counterpart at 3.1.1. Where a verdict says so, it grades OUR
behavior rather than AdCP conformance, and names what was searched to establish
the silence.

The superseded upgrade table is kept below for provenance, since several rows
name real defects that are still open.

<details>
<summary>Superseded: 3.6 Upgrade Impact table (framing only — verdicts above are authoritative)</summary>

| Rule | Impact | Bug |
|------|--------|-----|
| BR-RULE-006 | PricingOption XOR now covers 9 models (cpm, vcpm, cpc, cpcv, cpv, cpp, cpa, time, flat_rate). CPA has `exclusiveMinimum: 0` on fixed_price. | salesagent-mq3n (PricingOption delivery lookup string vs integer PK) |
| BR-RULE-007 | Product schema now has `additional_properties: true`; new fields: channels, catalog_match, catalog_types, conversion_tracking, data_provider_signals, forecast, signal_targeting_allowed | salesagent-qo8a (6 Product fields missing from DB -- FIXED) |
| BR-RULE-008 | Budget positivity unchanged but total_budget now schema-validated | -- |
| BR-RULE-011 | min_spend_per_package now explicit in all 9 v3 pricing models | salesagent-mq3n |
| BR-RULE-015 | Creative now uses v3 creative-asset schema (format_id is object, not string) | salesagent-goy2 (Creative extends wrong adcp type) |
| BR-RULE-021 | XOR identification now applies to performance feedback as well | salesagent-7gnv (MediaBuy boundary drops buyer_campaign_ref, creative_deadline, ext) |
| BR-RULE-043 | Context echo now applies to capabilities and accounts endpoints | -- |
| BR-RULE-048 | Signal activation is new in v3 | -- |
| BR-RULE-051-078 | Performance feedback, capabilities, accounts, content standards, property lists are all new v3 domains | -- |

</details>

## Rules

### BR-RULE-001: Brand Manifest Policy Enforcement
**Obligation ID** BR-RULE-001-01
**Layer** behavioral
**Invariant:** The system enforces `brand_manifest_policy` at product discovery entry. Three levels: `require_auth`, `require_brand`, `public`. Default is `require_auth`.
**Scenario:**
```gherkin
Given a tenant with brand_manifest_policy set to "require_brand"
When a buyer requests products without providing a brand manifest
Then the request is rejected

Given a tenant with brand_manifest_policy set to "public"
When an anonymous buyer requests products
Then the request proceeds and products are returned
```
**Priority:** P1
**Grounded at 3.1.1:** SPEC-SILENT. AdCP 3.1.1 defines no `brand_manifest_policy` and no three-level (`require_auth` / `require_brand` / `public`) discovery gate — the term `brand_manifest` is not present in the 3.1.1 schema bundle at all, having been replaced by the `brand` BrandRef. On the wire, `get_products` requires only `buying_mode`; `brand` is an optional `$ref` to `core/brand-ref.json` and becomes mandatory only through `dependencies: {"catalog": ["brand"]}` (composition resolved: the request's `allOf` is `core/version-envelope.json` plus a wholesale-only `if/then` that adds no brand requirement) — repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json. The one brand-gating code that exists, `BRAND_REQUIRED`, is scoped to billable operations ("A billable operation was attempted without a brand reference. Every billable operation requires either a seller-assigned `account_id` or a natural key including `brand`"), not to discovery — repo=adcp ref=3.1.1 path=schemas/enums/error-code.json. Only the `public` leg has any spec anchor: the security storyboard classes "`get_products` without pricing" among the public discovery operations — repo=adcp ref=3.1.1 path=universal/security.yaml. Rejecting an unbranded discovery call is therefore a seller-side tenant policy; this obligation grades our production behavior, not AdCP conformance.

---

### BR-RULE-002: Brief Policy Compliance
**Obligation ID** BR-RULE-002-01
**Layer** behavioral
**Invariant:** When advertising_policy is enabled, the buyer's brief is checked via LLM. BLOCKED briefs are rejected. RESTRICTED briefs with manual review enabled are rejected. Service unavailable fails open.
**Scenario:**
```gherkin
Given a tenant with advertising_policy enabled
When a buyer submits a brief evaluated as BLOCKED
Then the request is rejected with POLICY_VIOLATION

Given a tenant with advertising_policy enabled
When the LLM policy service is unavailable
Then the request proceeds (fail-open)
```
**Priority:** P2
**Grounded at 3.1.1:** SPEC-SILENT on the mechanism; only the error code is anchored. `POLICY_VIOLATION` is a real 3.1.1 code — "Request violates the seller's content or advertising policies. Recovery: correctable (review policy requirements in the error details)." — so rejecting a policy-failing brief under that code is spec-conformant — repo=adcp ref=3.1.1 path=schemas/enums/error-code.json — and 3.1.1 supplies the recommended details shape (`policy_id`, `policy_url`, `violated_rules`) — repo=adcp ref=3.1.1 path=schemas/error-details/policy-violation.json. Nothing in 3.1.1 mandates LLM-based brief screening, a BLOCKED/RESTRICTED classification vocabulary, coupling RESTRICTED to a manual-review setting, or fail-open when the classifier is unavailable: a grep for `POLICY_VIOLATION` across every storyboard in the pinned compliance tree returns zero hits, and the error storyboard's graded surfaces are all generic input and version-negotiation rejections — negative budget and reversed dates (business-rule violations that pass schema validation), a nonexistent `product_id`, a `get_products` call missing `buying_mode`, an unsupported `adcp_version`, plus the error-envelope and MCP transport-binding shapes — none of which is brief-content policy screening — repo=adcp ref=3.1.1 path=universal/error-compliance.yaml. The enablement flag, the classification tiers, and the fail-open rule all grade our production behavior.

---

### BR-RULE-003: Principal-Scoped Product Visibility
**Obligation ID** BR-RULE-003-01
**Layer** behavioral
**Invariant:** Products with `allowed_principal_ids` are visible only to listed principals. Products without restrictions are visible to all. Anonymous users cannot see restricted products.
**Scenario:**
```gherkin
Given a product with allowed_principal_ids = ["principal_A"]
When principal_B requests products
Then the restricted product is not included in results

Given a product with allowed_principal_ids = null
When an anonymous user requests products
Then the product is included in results
```
**Priority:** P1
**Grounded at 3.1.1:** SPEC-SILENT. `core/product.json` — with its top-level `anyOf` (legacy `format_ids` branch vs 3.1+ `format_options` branch) and its signal-targeting `allOf` if/then both resolved — declares no `allowed_principal_ids` and no per-principal visibility or ACL field of any kind; "principal" is not a product-level concept anywhere in the 3.1.1 bundle — repo=adcp ref=3.1.1 path=schemas/core/product.json. The nearest spec surface is `account` on the discovery request, which scopes *pricing* ("Account for product lookup. Returns products with pricing specific to this account's rate card"), not catalogue visibility — repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json. Anonymous versus authenticated access is graded only as an auth tier, where "`get_products` without pricing" is public — repo=adcp ref=3.1.1 path=universal/security.yaml — with no statement about which products an anonymous caller may see. Per-principal product entitlement is entirely our own model.

---

### BR-RULE-004: Anonymous Pricing Suppression
**Obligation ID** BR-RULE-004-01
**Layer** behavioral
**Invariant:** Anonymous requests have `pricing_options` set to empty array on every product.
**Scenario:**
```gherkin
Given a product with 3 pricing options
When an anonymous user requests products
Then the product has pricing_options = []

Given a product with 3 pricing options
When an authenticated user requests products
Then the product has all 3 pricing options
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED. The *intent* — withhold pricing from unauthenticated callers — is grounded: the security storyboard classes "`get_products` without pricing" among the public discovery operations while operations returning tenant-scoped data require credentials — repo=adcp ref=3.1.1 path=universal/security.yaml. The *mechanism* claimed here is not valid at 3.1.1. `get-products-response.products[]` is `$ref` to `core/product.json` (response composition resolved: `allOf` of `core/version-envelope.json` + `core/protocol-envelope.json`; there is no relaxed or anonymous Product variant in the bundle) — repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-response.json — and that Product lists `pricing_options` in `required` with `minItems: 1` — repo=adcp ref=3.1.1 path=schemas/core/product.json. A product emitted with `pricing_options: []` therefore fails Product validation at 3.1.1. The only projection lever 3.1.1 declares is the request's `fields` array ("Required fields (product_id, name) are always included regardless of selection") — repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json — so the empty-array shape specifically is contradicted; the authenticated half of the obligation (all pricing options returned) is unaffected.

---

### BR-RULE-005: AI Ranking Minimum Threshold
**Obligation ID** BR-RULE-005-01
**Layer** schema
**Invariant:** When AI ranking is applied, products scoring below 0.1 are filtered out. Products >= 0.1 are sorted descending. Without ranking, no threshold.
**Scenario:**
```gherkin
Given AI ranking is active and product scores [0.05, 0.15, 0.9]
When products are returned
Then only products scoring >= 0.1 are included (0.15, 0.9) sorted descending

Given no brief is provided
When products are returned
Then all products are included regardless of score
```
**Priority:** P2
**Grounded at 3.1.1:** SPEC-SILENT. `core/product.json` (top-level `anyOf` and the signal-targeting `allOf` resolved) carries no numeric relevance or ranking score at all — the sole brief-match surface is `brief_relevance`, typed `string`: "Explanation of why this product matches the brief (only included when brief is provided)" — so a 0.1 numeric cutoff has no wire representation to be graded against — repo=adcp ref=3.1.1 path=schemas/core/product.json. The request defines `buying_mode: "brief"` curation ("publisher curates product recommendations from the provided brief") but mandates no score, no threshold, and no ordering of `products[]` — repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json. The only storyboard mention of ranking in the media-buy domain is the note that wholesale mode returns products "without brief-mode ranking or curation", which grades mode behaviour rather than any score cutoff — repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/canonical_formats.yaml. The 0.1 threshold and the descending sort grade our own ranking implementation.

---

### BR-RULE-006: PricingOption XOR Constraint
**Obligation ID** BR-RULE-006-01
**Layer** schema
**Invariant:** Each pricing option must have exactly one of `fixed_price` or `floor_price`. Both or neither is invalid. CPA always has `fixed_price`.
**Scenario:**
```gherkin
Given a pricing option with fixed_price=10 and floor_price=null
Then the pricing option is valid

Given a pricing option with both fixed_price=10 and floor_price=5
Then the pricing option is invalid

Given a CPA pricing option
Then fixed_price is required and floor_price must be null
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED. `core/pricing-option.json` declares no properties of its own — it is a `oneOf` over 9 branch schemas discriminated by `pricing_model` (cpm, vcpm, cpc, cpcv, cpv, cpp, cpa, flat_rate, time), so every claim must be evaluated per branch — repo=adcp ref=3.1.1 path=schemas/core/pricing-option.json. The CPA leg HOLDS: `cpa-option.json` declares no `floor_price` property whatsoever and places `fixed_price` (with `exclusiveMinimum: 0`) in `required` alongside `pricing_option_id`, `pricing_model`, `event_type`, `currency` — repo=adcp ref=3.1.1 path=schemas/pricing-options/cpa-option.json. "Exactly one of fixed_price or floor_price; neither is invalid" is FALSE for the other eight branches: `cpm-option.json` requires only `pricing_option_id`, `pricing_model`, `currency`, and its own description makes the neither-present case explicitly valid ("If fixed_price is present, it's fixed pricing. If absent, auction-based"); and the mutual exclusion survives only as prose inside the `floor_price` description ("mutually exclusive with fixed_price") with no `oneOf`, `not`, or `dependencies` enforcing it — repo=adcp ref=3.1.1 path=schemas/pricing-options/cpm-option.json.

---

### BR-RULE-007: Product Schema Validity
**Obligation ID** BR-RULE-007-01
**Layer** schema
**Invariant:** Each product must have >= 1 format_id, >= 1 publisher_property, >= 1 pricing_option. Conversion failure is treated as data corruption and fails the entire request.
**Scenario:**
```gherkin
Given a product with 0 format_ids
When the product is converted to AdCP schema
Then a ValueError is raised and the request fails

Given a product with 1 format_id, 1 property, 1 pricing_option
When the product is converted to AdCP schema
Then conversion succeeds
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED. Two of the three cardinalities HOLD: `core/product.json` places both `publisher_properties` and `pricing_options` in `required`, and each is an array with `minItems: 1`. The `>= 1 format_id` leg is FALSE — `format_ids` is absent from `required` and carries no `minItems`, and the product's top-level `anyOf` accepts EITHER the legacy branch (`required: ["format_ids"]`) OR the 3.1+ branch (`required: ["format_options"]`, itself `minItems: 1`), so a conformant 3.1.1 product may legitimately carry zero `format_ids` — repo=adcp ref=3.1.1 path=schemas/core/product.json. (The stale note about `additional_properties` is also mis-stated: the field is `additionalProperties: true` on the same schema.) The second half — "conversion failure is treated as data corruption and fails the entire request" — is spec-silent: 3.1.1 defines no seller-internal ORM→schema conversion step, and the error storyboard's graded surfaces are all buyer-input and version-negotiation rejections (negative budget, reversed dates, nonexistent `product_id`, a `get_products` call missing `buying_mode`, unsupported version, plus the error-envelope and transport-binding shapes) — none of them covering seller-side serialization failure — repo=adcp ref=3.1.1 path=universal/error-compliance.yaml.

---

### BR-RULE-008: Budget Positivity
**Obligation ID** BR-RULE-008-01
**Layer** behavioral
**Invariant:** Total budget must be strictly positive (> 0). Schema allows 0 but business rule rejects it.
**Scenario:**
```gherkin
Given a media buy with total_budget.amount = 0
When create_media_buy is called
Then the request is rejected

Given a media buy with total_budget.amount = 100
When create_media_buy is called
Then budget validation passes
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED. The premise "schema allows 0" HOLDS exactly: `create-media-buy-request.total_budget` is an object with `amount` `{type: number, minimum: 0}` and `currency`, both `required`, `additionalProperties: false` — no `exclusiveMinimum` — and the request's only `allOf` is `core/version-envelope.json`, which contributes no budget constraint — repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json; the per-package `budget` is likewise `{type: number, minimum: 0}` — repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json. The rejection half is only partly grounded: 3.1.1 grades rejection of a NEGATIVE budget ("A negative budget is never valid... VALIDATION_ERROR is the canonical code for business-rule violations that pass schema validation", allowed codes VALIDATION_ERROR / INVALID_REQUEST / BUDGET_TOO_LOW, recovery `correctable`) and says nothing at all about zero — repo=adcp ref=3.1.1 path=universal/error-compliance.yaml. So "strictly positive" overstates the pinned contract: only the negative case is AdCP-graded; rejecting exactly 0 grades our own business rule.

---

### BR-RULE-009: Single Currency Per Media Buy
**Obligation ID** BR-RULE-009-01
**Layer** behavioral
**Invariant:** All packages must use the same currency. Currency must be in tenant's CurrencyLimit table.
**Scenario:**
```gherkin
Given two packages with currencies ["USD", "EUR"]
When create_media_buy is called
Then the request is rejected for mixed currencies

Given two packages both using "USD" and USD is in tenant's CurrencyLimit
When create_media_buy is called
Then currency validation passes
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED. The scenario's premise is not expressible at 3.1.1: there is no per-package currency field. `media-buy/package-request.json` (composition resolved: `allOf` is only `core/version-envelope.json`) has no currency-bearing property, and its `budget` is documented as "Budget allocation for this package in the media buy's currency" — repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json; the response-side `core/package.json` likewise has none and states budget is "in the currency specified by the pricing option" — repo=adcp ref=3.1.1 path=schemas/core/package.json. Currency enters only via `total_budget.currency` on the request and via each selected pricing option's own `currency` — repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json. 3.1.1 states no single-currency-per-media-buy rule and has no tenant currency-allowlist concept; the only currency conformance surface in the pinned tree is get_products `filters.pricing_currencies` pruning at discovery time — repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/pricing_currency_filter.yaml. Both halves of the invariant grade our production behavior, and the scenario should be restated in terms of pricing-option currency rather than a package `currency` field.

---

### BR-RULE-010: No Duplicate Products Per Media Buy
**Obligation ID** BR-RULE-010-01
**Layer** behavioral
**Invariant:** Each product_id can appear at most once across all packages in a media buy.
**Scenario:**
```gherkin
Given two packages both referencing product_id="prod_1"
When create_media_buy is called
Then the request is rejected for duplicate product

Given two packages with distinct product_ids
When create_media_buy is called
Then validation passes
```
**Priority:** P1
**Grounded at 3.1.1:** SPEC-SILENT. `create-media-buy-request.packages` is an array of `media-buy/package-request.json` with `minItems: 1` and NO `uniqueItems` and no product_id-uniqueness constraint anywhere; composition resolved — the request's `allOf` is only `core/version-envelope.json`, there is no `oneOf`/`anyOf`, and the sole `dependencies` entry is `proposal_id → total_budget` — repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json. The package request's `product_id` carries only an echo obligation ("Sellers MUST echo this value on every response package object that represents this requested package") — it is never declared to be a package identity key — repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json. 3.1.1 in fact supplies a per-package correlation key independent of `product_id`, `context.buyer_ref`, for correlating requested line items back to seller-assigned `package_id`s — repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/package_correlation_legacy_fallback.yaml. Rejecting a repeated `product_id` across packages is our own rule and grades our production behavior.

---

### BR-RULE-011: Minimum Spend Per Package
**Obligation ID** BR-RULE-011-01
**Layer** schema
**Invariant:** Package budget must meet min_spend from product pricing or tenant currency limit fallback.
**Scenario:**
```gherkin
Given a product with min_spend_per_package=500 and package budget=400
When create_media_buy is called
Then the request is rejected for budget below minimum

Given no product min_spend and tenant min_package_budget=100 and budget=50
When create_media_buy is called
Then the request is rejected

Given no minimum configured at any level
When create_media_buy is called
Then minimum spend check is skipped
```
**Priority:** P1
**Grounded at 3.1.1:** Partly grounded. The product-pricing tier holds: `core/pricing-option.json` is a `pricing_model`-discriminated `oneOf` over nine branch schemas with no properties of its own (repo=adcp ref=3.1.1 path=schemas/core/pricing-option.json), and after resolving that `oneOf` every branch declares `min_spend_per_package` as `{"type":"number","minimum":0}` — "Minimum spend requirement per package using this pricing option, in the specified currency" (repo=adcp ref=3.1.1 path=schemas/pricing-options/cpm-option.json, repo=adcp ref=3.1.1 path=schemas/pricing-options/cpa-option.json). It is in no branch's `required` list, so the scenario's "minimum spend check is skipped when nothing is configured" arm is consistent with the schema. The rejection code is vocabulary: `BUDGET_TOO_LOW` (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json), documented as "Budget below product minimum" at repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/task-reference/create_media_buy.mdx line 1022. FALSE part: the tenant/currency-limit fallback tier has no AdCP counterpart — walking repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json recursively finds no `limits` node and no seller-level minimum-budget declaration anywhere, so the second Gherkin arm grades our own tenant configuration, not AdCP conformance. Also ungraded: repo=adcp ref=3.1.1 path=universal/error-compliance.yaml exercises only `negative_budget` (allowed_values VALIDATION_ERROR/INVALID_REQUEST/BUDGET_TOO_LOW); no pinned storyboard drives a below-minimum budget.

---

### BR-RULE-012: Maximum Daily Spend Cap
**Obligation ID** BR-RULE-012-01
**Layer** schema
**Invariant:** Daily budget (package_budget / max(1, flight_days)) must not exceed tenant's max_daily_package_spend.
**Scenario:**
```gherkin
Given tenant max_daily_package_spend=1000 and package budget=5000 over 3 days (daily=1667)
When create_media_buy is called
Then the request is rejected for exceeding daily cap

Given no max_daily_package_spend configured
When create_media_buy is called
Then daily cap check is skipped
```
**Priority:** P1
**Grounded at 3.1.1:** AdCP 3.1.1 says nothing about a derived daily spend rate or a seller-side daily package cap; this obligation grades our own tenant configuration, not AdCP conformance. `budget` on a package is a flat scalar with no rate constraint — `{"type":"number","minimum":0,"description":"Budget allocation for this package in the media buy's currency"}` (repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json); its composition was resolved before claiming absence — the only `allOf` is `$ref` to repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json (which contributes only `adcp_version`/`adcp_major_version`) and the only `not` is `{"required":["capability_ids"]}`. The request root adds no daily field either (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json, `allOf` = version-envelope only). No seller-declared spend ceiling exists to compare against: repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json has no `limits` node under any path. The only 3.1.1 pacing control is the per-package `pacing` enum, which is a delivery-shape hint, not a cap.

---

### BR-RULE-013: DateTime Validity
**Obligation ID** BR-RULE-013-01
**Layer** behavioral
**Invariant:** start_time must be in the future, end_time must be after start_time. "asap" (case-sensitive) resolves to current UTC.
**Scenario:**
```gherkin
Given start_time is "asap"
When create_media_buy is called
Then start_time resolves to current UTC and bypasses past-time check

Given start_time is "ASAP" (wrong case)
When create_media_buy is called
Then the value is not recognized and fails validation

Given end_time <= start_time
When create_media_buy is called
Then the request is rejected
```
**Priority:** P0
**Grounded at 3.1.1:** All three arms hold, and all three are graded. (1) `start_time` is `$ref` to a two-branch `oneOf`: the literal `{"type":"string","const":"asap"}` or an ISO 8601 `date-time` string (repo=adcp ref=3.1.1 path=schemas/core/start-timing.json, referenced from repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json where `start_time` and `end_time` are both `required`). `const` is case-exact, so `"ASAP"` matches neither branch — it is not the literal and is not a parseable date-time — which is exactly the scenario's second arm. Sellers accepting the `"asap"` form is separately graded end-to-end by repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/proposal_finalize_asap_timing.yaml ("The seller MUST accept start_time: \"asap\" (string literal) without rejecting it at the wrapper/input-validation layer"). (2) Past start times: "For new media buys, the top-level `start_time` MUST be either `\"asap\"` or a date-time that is not in the past. A past concrete `start_time` MUST return an `INVALID_REQUEST` error" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/task-reference/create_media_buy.mdx lines 1180-1182), graded by the `past_start_rejection` step of repo=adcp ref=3.1.1 path=universal/schema-validation.yaml. (3) `end_time` after `start_time`: the `reversed_dates` step of the same storyboard sends `start_time: 2099-12-31` / `end_time: 2099-01-01` and requires an error, and repo=adcp ref=3.1.1 path=universal/error-compliance.yaml `reversed_dates_error` grades the same input with allowed codes VALIDATION_ERROR or INVALID_REQUEST. Note our obligation says "rejected" without naming a code; the pinned graders accept VALIDATION_ERROR or INVALID_REQUEST for the reversed-date case and require INVALID_REQUEST for past-start.

---

### BR-RULE-014: Targeting Overlay Validation
**Obligation ID** BR-RULE-014-01
**Layer** behavioral
**Invariant:** Unknown field names rejected, managed-only dimensions cannot be set by buyers, same geo value cannot be in both include and exclude lists.
**Scenario:**
```gherkin
Given a targeting overlay with unknown field "custom_segment"
When create_media_buy is called
Then the request is rejected

Given a targeting overlay with geo "US" in both include and exclude
When create_media_buy is called
Then the request is rejected
```
**Priority:** P1
**Grounded at 3.1.1:** One of the three clauses is grounded; the other two are not. GROUNDED — same-value include/exclude overlap: "Sellers SHOULD reject requests where the same value appears in both the inclusion and exclusion field at the same level (e.g., `geo_countries: [\"US\"]` with `geo_countries_exclude: [\"US\"]`) and return a descriptive error" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/advanced-topics/targeting.mdx line 493) — note this is SHOULD, not MUST, so our unconditional rejection is stricter than the pin requires. FALSE — unknown-field rejection: the targeting overlay is explicitly open. repo=adcp ref=3.1.1 path=schemas/core/targeting.json declares `"additionalProperties": true` at its root and has no `allOf`/`oneOf`/`anyOf` to add a closing constraint, and it is reached by plain `$ref` from `packages[].targeting_overlay` in repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json — so a `custom_segment` key is schema-valid at 3.1.1 and rejecting it grades our own strictness, not AdCP. SPEC-SILENT — "managed-only dimensions": 3.1.1 has no managed-only/publisher-reserved targeting concept at all; what it has instead is capability gating ("If a seller only supports one direction, it MUST return a validation error for unsupported fields rather than silently ignoring them", same file line 495) plus per-field `get_adcp_capabilities` declaration notes, which is a support question, not a buyer-permission question.

---

### BR-RULE-015: Creative Asset Validation
**Obligation ID** BR-RULE-015-01
**Layer** behavioral
**Invariant:** Reference creatives must have URL and dimensions. Generative formats are exempt. Errors collected non-fail-fast.
**Scenario:**
```gherkin
Given a reference creative without a URL
When creative validation runs
Then an error is collected for the missing URL

Given a generative format creative without a URL
When creative validation runs
Then the creative passes validation (exempt)
```
**Priority:** P1
**Grounded at 3.1.1:** All three parts hold. URL + dimensions on hosted reference assets: after resolving `creative-asset.json` → `assets` → the 20-branch `oneOf` in repo=adcp ref=3.1.1 path=schemas/core/assets/asset-union.json (discriminated on `asset_type`), the hosted-media branches make url and geometry mandatory — repo=adcp ref=3.1.1 path=schemas/core/assets/image-asset.json has `"required": ["asset_type","url","width","height"]`, and repo=adcp ref=3.1.1 path=schemas/core/assets/video-asset.json the same, with the rationale spelled out ("`width` and `height` are required because a hosted video file has intrinsic, native pixel dimensions"). The generative exemption is structural, not a carve-out: the brief-carrying branch requires only the discriminator — repo=adcp ref=3.1.1 path=schemas/core/assets/brief-asset.json has `"required": ["asset_type"]` and a single property, so a generative creative that supplies a brief instead of finished bytes is valid with no url and no dimensions. Non-fail-fast collection: repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-response.json describes the success shape as "per-creative results in the creatives array (best-effort processing with per-item status/failures)" and gives each entry its own `errors` array of `core/error.json` "(only present when action='failed')", with an `if/then` requiring `status` be omitted when `action` is `failed` — i.e. one bad creative is reported in place rather than aborting the batch. Aside on the stale 3.6 note: `format_id` being a structured `{agent_url, id}` object rather than a string is also true at 3.1.1 (repo=adcp ref=3.1.1 path=schemas/core/creative-asset.json, "structured `{agent_url, id}`"), but it is not part of this obligation's claim.

---

### BR-RULE-017: Approval Workflow Determination
**Obligation ID** BR-RULE-017-01
**Layer** behavioral
**Invariant:** If tenant `human_review_required` or adapter `manual_approval_required` is true, media buy enters pending state. Default is human_review_required=true.
**Scenario:**
```gherkin
Given tenant human_review_required=false and adapter manual_approval_required=false
When create_media_buy is called
Then the media buy is auto-approved

Given tenant human_review_required=true
When create_media_buy is called
Then the media buy enters pending manual approval state
```
**Priority:** P1
**Grounded at 3.1.1:** The human-in-the-loop concept exists but this obligation states both its trigger and its state wrong. WRONG STATE: there is no pending-approval media buy state. repo=adcp ref=3.1.1 path=schemas/enums/media-buy-status.json enumerates exactly `pending_creatives, pending_start, active, paused, completed, rejected, canceled`, and the `CreateMediaBuySubmitted` branch of repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-response.json says it outright: "Do not use a 'pending_approval' MediaBuy.status for this case — that value is not in MediaBuyStatus; IO review and similar pre-issuance workflows are modeled at the task layer only"; that branch requires `status` + `task_id` and carries `not: anyOf[required media_buy_id, required packages]`. repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/media-buys/lifecycle.mdx line 51 restates it: pending-review statuses are "**task-level** statuses — they describe whether the *operation* is queued for human review, not the media buy's own state." WRONG TRIGGER: 3.1.1 makes the submitted-vs-synchronous choice per-call on protocol-visible inputs, not on a seller-wide toggle — "Sellers MUST return `submitted` when: the request references one or more products with `delivery_type: \"guaranteed\"` **and** the seller declares the `requires_io_approval` capability... Sellers MUST return synchronous success when: all referenced products have `delivery_type: \"non_guaranteed\"`" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/task-reference/create_media_buy.mdx lines 286-297). A default of `human_review_required=true` applied uniformly is non-conformant there: "Sellers that uniformly return `submitted` fail the non-IO-approval paths in the `sales-guaranteed` compliance storyboard." The tenant `human_review_required` and adapter `manual_approval_required` flags themselves are ours and spec-silent; the wire shape they must produce is graded by repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/create_media_buy_async.yaml (status literal `submitted`, `task_id` present, no `media_buy_id`, no `packages`).

---

### BR-RULE-018: Atomic Response Semantics
**Obligation ID** BR-RULE-018-01
**Layer** schema
**Invariant:** Responses contain EITHER success data OR error data, never both. Enforced by oneOf schema.
**Scenario:**
```gherkin
Given a successful media buy creation
When the response is returned
Then it contains success fields and no errors field

Given a validation failure
When the response is returned
Then it contains errors array and no success fields
```
**Priority:** P0
**Grounded at 3.1.1:** The success-XOR-error core holds and is genuinely `oneOf`-enforced, but "never both" is too absolute across all response shapes. GROUNDED: repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-response.json has an empty root `properties`, composes `allOf(core/version-envelope.json, core/protocol-envelope.json)`, and puts every field in a three-branch `oneOf` whose exclusivity is explicit — `CreateMediaBuySuccess` carries `"not": {"required": ["errors"]}` and `CreateMediaBuyError` carries `not: anyOf[required media_buy_id, required packages, required sandbox, status == "submitted"]`. The 3.6 note's extension is also true at 3.1.1: repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-response.json states it in words — "Returns either success confirmation OR error information, never both" — with branches required `[success]` vs required `[errors]`, and repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json uses the same `SyncAccountsSuccess`/`SyncAccountsError` split. CORRECTION: the invariant is two-shape reasoning applied to schemas that have three shapes. The `CreateMediaBuySubmitted` branch is neither success nor terminal failure and is expressly allowed to carry errors — "The submitted branch MAY carry advisory errors for non-blocking warnings; terminal failures belong in the error branch" (same file's root description); the `not` on the error branch excluding `status == "submitted"` is what keeps that legal under the `oneOf`. Separately, repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-response.json places per-item `errors` arrays *inside* its success branch ("best-effort processing with per-item status/failures"), so a successful response there does carry error data. Both scenario arms as written remain correct for create_media_buy.

---

### BR-RULE-020: Adapter Atomicity
**Obligation ID** BR-RULE-020-01
**Layer** behavioral
**Invariant:** If adapter call fails on auto-approval path, no DB records are persisted. Manual approval path persists in pending state before adapter.
**Scenario:**
```gherkin
Given auto-approval path and adapter returns error
When create_media_buy processes
Then no database records are created

Given manual approval path
When create_media_buy processes
Then records are persisted in pending state before adapter execution
```
**Priority:** P0
**Grounded at 3.1.1:** The manual-approval half is grounded on the wire; the auto-approval half is stated in a way 3.1.1 contradicts. MANUAL PATH: 3.1.1 does forbid handing the buyer an artifact before the buy is confirmed — the `CreateMediaBuySubmitted` branch of repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-response.json carries `not: anyOf[required media_buy_id, required packages]` ("the media_buy_id and packages land on the completion artifact, not this envelope"), graded by repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/create_media_buy_async.yaml. Whether we persist a row in a pending state behind that envelope is our implementation detail and spec-silent. AUTO-APPROVAL PATH: the absolute "no database records are created" is not an AdCP requirement and cuts against the pin's preferred pattern. repo=adcp ref=3.1.1 path=../../docs/3.1.1/building/by-layer/L1/security.mdx rule 10 ("Crossing service boundaries — downstream reconciliation") names exactly this case — "SSP/ad-server calls on `create_media_buy`" — and requires the opposite discipline: "Sellers MUST adopt one of two reconciliation patterns for every downstream call whose duplicate-invocation has business consequences", the preferred default being **write-claim-before-invoke**, where "before invoking the downstream, the seller persists a 'claim' row in the same transaction as the idempotency cache row", and "the seller MUST NOT treat a missing local record as 'downstream call did not happen'". Only the alternative thread-buyer-key pattern leaves nothing persisted before a failed adapter call. What 3.1.1 *does* mandate near this claim is narrower: rule 3, "Only successful responses are cached. On any error — validation, governance denial, transport failure, internal error — the key is **not** stored. A retry re-executes." Rule 10 is also explicitly reviewer-graded, not storyboard-graded.

---

### BR-RULE-021: Dual Identification (XOR)
**Obligation ID** BR-RULE-021-01
**Layer** behavioral
**Invariant:** Update/performance operations must use exactly one of media_buy_id or buyer_ref. Both or neither is invalid.
**Scenario:**
```gherkin
Given an update request with both media_buy_id and buyer_ref
When update_media_buy is called
Then the request is rejected by schema validation

Given an update request with only buyer_ref
When update_media_buy is called
Then the system resolves the media buy via buyer_ref lookup
```
**Priority:** P0
**Grounded at 3.1.1:** The `media_buy_id` XOR `buyer_ref` alternation this obligation polices no longer exists — top-level `buyer_ref` has been removed from the request surface and survives only as a conventional key inside the opaque `context` object. Both named operations now take a single mandatory identifier: repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json has `"required": ["idempotency_key", "account", "media_buy_id"]` and no `buyer_ref` property, and repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json has `"required": ["idempotency_key", "media_buy_id", ...]` with `media_buy_id` typed `{"type":"string","minLength":1}` and again no `buyer_ref`. That absence was verified after composition: each request's only `allOf` is `$ref` to repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json, which contributes just `adcp_version` and `adcp_major_version`; neither schema has a `oneOf`, `anyOf`, or `dependencies` entry that could reintroduce the field. The removal is stated explicitly: repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json directs buyers to per-package `context` correlation and adds "Do not use deprecated top-level buyer_ref for v3 correlation", and repo=adcp ref=3.1.1 path=schemas/enums/error-code.json repeats it in the MEDIA_BUY_NOT_FOUND and PACKAGE_NOT_FOUND recovery guidance ("reconcile via get_media_buys and the opaque request/response context correlation handle... rather than deprecated top-level buyer_ref"). The surviving usage is buyer-side and read-only, graded that way by repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/package_correlation_legacy_fallback.yaml, which asserts `media_buys[0].packages[0].context.buyer_ref` on a *legacy* response shape and labels itself "a compatibility fixture, not the current seller conformance path." Both Gherkin arms are therefore moot at 3.1.1: a request carrying both is simply an unknown extra property (`additionalProperties: true`), and buyer_ref lookup is not a resolution path.

---

### BR-RULE-022: Partial Update Semantics
**Obligation ID** BR-RULE-022-01
**Layer** behavioral
**Invariant:** Only fields present in request are modified. Omitted fields unchanged. Empty updates rejected.
**Scenario:**
```gherkin
Given an update request with only budget field
When update_media_buy processes
Then only budget is changed; all other fields retain current values

Given an update request with no updatable fields
When update_media_buy is called
Then the request is rejected
```
**Priority:** P1
**Grounded at 3.1.1:** The PATCH half holds; the empty-update half is not a 3.1.1 requirement. GROUNDED: "**PATCH Semantics**: Only specified fields are updated; omitted fields remain unchanged" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/task-reference/update_media_buy.mdx line 62, restated at line 793 with a worked example), reinforced per-field for the replacement-semantics collections ("`optimization_goals` — Replace all optimization goals for this package. Uses replacement semantics — omit to leave goals unchanged", line 241) and by "Updates are atomic - either all changes apply or none do" (line 908). The response side backs this: `affected_packages` is documented as "a state snapshot, not a sparse delta" (line 267). NOT GROUNDED: nothing at 3.1.1 rejects an update that names no updatable field. repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json requires only `["idempotency_key", "account", "media_buy_id"]`, and the absence of any minimum-payload constraint was checked after composition — the schema's sole `allOf` is `$ref` to repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json, and there is no `minProperties`, no `anyOf`/`oneOf`, and no `dependencies` entry anywhere in the chain. A search of the pinned prose for a no-op/empty-update rule returns nothing for `update_media_buy`. So arm 2 of the scenario grades our own strictness, not AdCP conformance.

---

### BR-RULE-024: Creative Replacement Semantics
**Obligation ID** BR-RULE-024-01
**Layer** behavioral
**Invariant:** creative_ids or creative_assignments completely replaces the existing set. Not a merge.
**Scenario:**
```gherkin
Given existing creative assignments [A, B, C] and update provides [B, D]
When update_media_buy processes
Then assignments become [B, D]; A and C are deleted
```
**Priority:** P1
**Grounded at 3.1.1:** The replacement-not-merge half holds and is GRADED; the `creative_ids` half is false for this version. `packages[].creative_assignments` is specified as "Replace creative assignments for this package with optional weights and placement targeting. Uses replacement semantics - omit to leave assignments unchanged", and its peer array `packages[].creatives` as "Replace this package's inline creative assets" (repo=adcp ref=3.1.1 path=schemas/media-buy/package-update.json) — so an update carrying [B, D] yields [B, D] and A/C fall out, since removal at 3.x is expressed by sending the desired post-state rather than a delete primitive. Two storyboards grade this directly: `dependency_impairment.yaml` step `swap_assignment` ("the new list fully replaces the old. Provide ONLY creative B; creative A is unbound from the package") validates `affected_packages[*]` for "complete replacement assignment state" and then grades that the displaced creative's impairment clears on the next read; `dependency_impairment_cardinality.yaml` grades the multi-package form — swap package_a A→C, then package_b B→D, with `verify_cardinality_back_to_one` and `verify_cardinality_zero` asserting the displaced creatives are no longer buy dependencies (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/dependency_impairment.yaml, repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/dependency_impairment_cardinality.yaml). The `creative_ids` half is false: `update-media-buy-request.json` composes only `allOf: [core/version-envelope.json]` and its property set is account, media_buy_id, revision, paused, canceled, cancellation_reason, start_time, end_time, packages, invoice_recipient, new_packages, reporting_webhook, push_notification_config, idempotency_key, context, ext — there is no `creative_ids` on the update path, and `package-update.json` (no allOf/oneOf of its own; a root `not` bars immutable fields) exposes `creative_assignments`/`creatives` instead (repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json). A full-tree scan of the pinned bundle finds `creative_ids` only on creative-filters, list-creatives-request, sync-creatives-request and get-creative-delivery-request, never on a media-buy update.

---

### BR-RULE-026: Creative Assignment Validation
**Obligation ID** BR-RULE-026-01
**Layer** behavioral
**Invariant:** Creatives in error/rejected state cannot be assigned. Format must be compatible with product. All errors returned as INVALID_CREATIVES.
**Scenario:**
```gherkin
Given a creative in "error" state
When creative assignment is attempted
Then the request is rejected with INVALID_CREATIVES

Given a creative with incompatible format
When creative assignment is attempted
Then the request is rejected with INVALID_CREATIVES
```
**Priority:** P1
**Grounded at 3.1.1:** The error code is wrong and one of the two states does not exist. `INVALID_CREATIVES` appears zero times in the pinned schema bundle and zero times in the pinned compliance tree; the standard vocabulary carries `CREATIVE_REJECTED`, `CREATIVE_VALUE_NOT_ALLOWED`, `CREATIVE_NOT_FOUND`, `FORMAT_NOT_SUPPORTED`, `VALIDATION_ERROR` and `INVALID_REQUEST` instead (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json). The creative lifecycle vocabulary is processing, pending_review, approved, suspended, rejected, archived — there is no "error" state at 3.1.1; `rejected` and `suspended` are the ineligible-for-delivery states, and `suspended` is explicitly "temporarily ineligible for delivery" (repo=adcp ref=3.1.1 path=schemas/enums/creative-status.json). For the format-incompatibility half, the graded contract routes constraint violations to specific codes, not a single blanket one: the native-format storyboard requires `CREATIVE_VALUE_NOT_ALLOWED` for a value outside a declared closed enum and `VALIDATION_ERROR` or `INVALID_REQUEST` for size/length/schema-constraint violations, and explicitly distinguishes those from `CREATIVE_REJECTED` as the generic content-policy failure (repo=adcp ref=3.1.1 path=domains/creative/scenarios/native_in_feed.yaml). The intent — an ineligible or format-incompatible creative must not be assigned — survives; the state name and the single `INVALID_CREATIVES` code do not.

---

### BR-RULE-028: Placement ID Validation
**Obligation ID** BR-RULE-028-01
**Layer** behavioral
**Invariant:** placement_ids must be valid for the product. Products without placement support reject placement_ids.
**Scenario:**
```gherkin
Given a placement_id not valid for the package's product
When creative assignment is attempted
Then the request is rejected with invalid_placement_ids

Given a product that does not support placement targeting
When creative assignment includes placement_ids
Then the request is rejected
```
**Priority:** P2
**Grounded at 3.1.1:** The referencing half is grounded, the targetability gate is partially grounded, and the error name is fabricated. `creative_assignments[].placement_refs` "References entries from the product's `placements[]` array by `{ publisher_domain, placement_id }`", and the legacy `placement_ids` string array is the publisher-scoped shorthand for the same thing, with the normative rule being precedence: "If both `placement_refs` and legacy `placement_ids` are present, `placement_refs` wins and receivers MUST ignore `placement_ids`" (repo=adcp ref=3.1.1 path=schemas/core/creative-assignment.json). That schema also says "When omitted, the creative runs on all buyer-targetable placements in the package" — and "buyer-targetable" is defined by composition, not left open: `placement.mode` is a REQUIRED product-level field where "`targetable` means the buyer may reference this placement_id when assigning creatives" while "`included` means the placement is part of the product's public delivery composition but the buyer cannot cherry-pick it by placement_id", with buyers instructed to fail closed on products omitting `mode` after 2026-11-25 (repo=adcp ref=3.1.1 path=schemas/core/placement.json). So AdCP does define which placements a product exposes to creative-level routing; what it does NOT define is any seller-side MUST-reject mandate for an out-of-mode or unknown placement id, and no error code covers it — the named outcome `invalid_placement_ids` does not exist (zero case-insensitive hits across the pinned compliance and docs trees, and it is not among the standard codes, repo=adcp ref=3.1.1 path=schemas/enums/error-code.json). No storyboard grades placement-level routing at all: `placement_refs` appears zero times in dist/compliance/3.1.1. The rejection *mechanics* therefore grade our production choices; the targetability *criterion* they enforce is spec-defined.

---

### BR-RULE-029: Webhook Delivery Contract
**Obligation ID** BR-RULE-029-01
**Layer** behavioral
**Invariant:** Webhooks use monotonically increasing sequence numbers, typed notifications, and exponential backoff retry for 5xx. 4xx not retried.
**Scenario:**
```gherkin
Given a webhook delivery attempt fails with 503
When the retry policy executes
Then the system retries up to 3 times with exponential backoff (1s, 2s, 4s + jitter)

Given a webhook delivery attempt fails with 400
When the retry policy evaluates
Then the system does not retry (client error)

Given notification_type is "final"
When the webhook payload is assembled
Then next_expected_at is omitted
```
**Priority:** P1
**Grounded at 3.1.1:** Two of the three claims hold and the retry clause is contradicted. Typed notifications and the final-fire rule are in the schema: `notification_type` is a closed enum `scheduled | final | delayed | adjusted | window_update` (note `window_update` — five values, not the three or four older docs imply), `sequence_number` is an integer with `minimum: 1` described as the "Sequential notification number for this reporting webhook stream", and `next_expected_at` is "Omitted on final notifications" (repo=adcp ref=3.1.1 path=schemas/media-buy/media-buy-delivery-webhook-result.json — a flat object with no allOf/oneOf, so those fields are the whole story). The retry policy is where the obligation diverges: 3.1.1's graded webhook contract is at-least-once with a stable `idempotency_key` and treats ANY non-2xx as a failed delivery to be retried — "senders retry non-2xx responses" (repo=adcp ref=3.1.1 path=universal/webhook-receiver-envelope.yaml), so "4xx is not retried" is false as a conformance claim. The emission storyboard grades only that the key stays byte-identical across retries triggered by 5xx, requiring at least two deliveries; it fixes no attempt count and no backoff curve (repo=adcp ref=3.1.1 path=universal/webhook-emission.yaml). The specific 3-attempt 1s/2s/4s+jitter schedule and strict monotonicity of the sequence are our own policy, ungraded at 3.1.1.

---

### BR-RULE-030: Multi-Entity Identification (OR)
**Obligation ID** BR-RULE-030-01
**Layer** behavioral
**Invariant:** Delivery requests use optional media_buy_ids (priority) and/or buyer_refs. Neither returns all. Partial resolution silently omits missing. Zero results return empty array.
**Scenario:**
```gherkin
Given both media_buy_ids and buyer_refs provided
When get_media_buy_delivery is called
Then only media_buy_ids are used (priority rule)

Given neither media_buy_ids nor buyer_refs provided
When get_media_buy_delivery is called
Then all media buys for the principal are returned

Given some media_buy_ids do not exist
When get_media_buy_delivery is called
Then results include only found media buys (partial, no error)
```
**Priority:** P1
**Grounded at 3.1.1:** The priority rule cannot hold because one of its two operands does not exist on this request. `get-media-buy-delivery-request.json` composes `allOf: [core/version-envelope.json]` (which contributes only version-negotiation fields) and its own properties are account, media_buy_ids, status_filter, start_date, end_date, include_package_daily_breakdown, time_granularity, include_window_breakdown, attribution_window, reporting_dimensions — there is no `buyer_refs`, and a full-tree scan of the pinned bundle finds `buyer_ref` only on package/account/create-and-update-media-buy surfaces, never on the delivery request (repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buy-delivery-request.json). `media_buy_ids` is optional (the schema declares no `required` at all), so omitting it is legal, and the response's required `media_buy_deliveries` array carries no `minItems`, so a zero-result empty array is schema-valid (repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buy-delivery-response.json). What the pinned artifacts do NOT state: that omitting filters returns every media buy for the caller, and that unresolvable ids are silently omitted rather than erroring — the delivery storyboard only ever calls the task with an explicit `media_buy_ids` array and grades no partial-resolution path (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/delivery_reporting.yaml). Those two clauses grade our behavior.

---

### BR-RULE-031: Format Discovery Filter Conjunction
**Obligation ID** BR-RULE-031-01
**Layer** behavioral
**Invariant:** All filters combine as AND. Results sorted by type then name.
**Scenario:**
```gherkin
Given type_filter="display" and name_search="banner"
When list_creative_formats is called
Then only formats matching BOTH display type AND "banner" name are returned

Given any valid format discovery request
When results are returned
Then they are sorted by format type then name
```
**Priority:** P2
**Grounded at 3.1.1:** Neither clause has a counterpart in the pinned artifacts. The request schema defines the filter fields the obligation names — `type` (enum audio/video/display/dooh), `name_search` ("case-insensitive partial match"), plus asset_types, dimension bounds, is_responsive, wcag_level, disclosure_*, and the 3.1-deprecated output_format_ids/input_format_ids — but says nothing about how multiple filters combine, and defines no sort, order_by, or result-ordering field anywhere; its only `allOf` members are core/version-envelope.json and a conditional requiring `account` when `include_pricing: true`, so nothing is contributed by composition either (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json). The one storyboard that walks list_creative_formats results asserts only the pagination invariants (`has_more`, `cursor`, `total_count`) and explicitly narrows its scope, never grading order across pages (repo=adcp ref=3.1.1 path=universal/pagination-integrity-creative-formats.yaml). "Filters AND, results sorted by type then name" therefore grades our production behavior. Note further that the sort key has no schema basis on the response side at all: `list-creative-formats-response.formats[]` items are `core/format.json`, which carries no `type` property — `type` exists at 3.1.1 only as a request-side filter (repo=adcp ref=3.1.1 path=schemas/core/format.json).

---

### BR-RULE-033: Validation Mode Semantics
**Obligation ID** BR-RULE-033-01
**Layer** behavioral
**Invariant:** strict mode aborts on assignment error. lenient mode logs warning and continues. Default is strict. Per-creative failures always produce action=failed regardless of mode.
**Scenario:**
```gherkin
Given validation_mode="strict" and an assignment error occurs
When sync_creatives processes
Then a ToolError is raised and remaining assignments are aborted

Given validation_mode="lenient" and an assignment error occurs
When sync_creatives processes
Then a warning is logged and the remaining assignments continue
```
**Priority:** P1
**Grounded at 3.1.1:** All four claims are grounded. `validation_mode` carries `"default": "strict"` and the semantics "'strict' fails entire sync on any validation error. 'lenient' processes valid creatives and reports errors" (repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json), over the closed enum strict|lenient (repo=adcp ref=3.1.1 path=schemas/enums/validation-mode.json). Per-creative failure reporting is independent of mode: the success branch's `creatives[]` is documented as "Items with action='failed' indicate per-item validation/processing failures, not operation-level failures", with `action` drawn from the creative-action enum created|updated|unchanged|failed|deleted (repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-response.json, repo=adcp ref=3.1.1 path=schemas/enums/creative-action.json). The graded storyboard confirms the default and the abort behavior: "The validation_mode is strict (default); the seller stops on the first violation" (repo=adcp ref=3.1.1 path=domains/creative/scenarios/native_in_feed.yaml). Two wording caveats that do not change the verdict: "ToolError" is our transport-layer name for what the spec calls an operation-level failure, and 3.1.1 does not carve `validation_mode` out specifically for assignment errors — it applies to sync validation errors generally.

---

### BR-RULE-034: Cross-Principal Creative Isolation
**Obligation ID** BR-RULE-034-01
**Layer** behavioral
**Invariant:** Creative lookup always filters by tenant_id + principal_id + creative_id. Cross-principal collision silently creates new creative.
**Scenario:**
```gherkin
Given creative_id "cr_1" exists under principal_A
When principal_B syncs a creative with creative_id "cr_1"
Then a new creative is created for principal_B (no error, no cross-visibility)
```
**Priority:** P0
**Grounded at 3.1.1:** The pinned artifacts define an ownership axis and a same-id rule, but leave the cross-owner case unscoped. `sync_creatives` requires `account` — "Account that owns these creatives" — alongside idempotency_key and creatives, and the request composes only `allOf: [core/version-envelope.json]`, so account is the sole ownership scope AdCP names; there is no tenant, principal, or namespace field (repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json). What the docs DO state is the same-id rule: sync_creatives "uses upsert semantics" and "Same `creative_id` updates existing creative rather than creating duplicates" (repo=adcp ref=3.1.1 path=creative/task-reference/sync_creatives.mdx, repo=adcp ref=3.1.1 path=creative/creative-libraries.mdx), with a SHOULD toward globally unique creative_ids and `concept_id` as the disambiguator when uniqueness cannot be guaranteed (repo=adcp ref=3.1.1 path=creative/specification.mdx). What is unstated is the scope of that upsert — nothing says whether two owners submitting the same `creative_id` collide or are isolated, no code covers the case (`CREATIVE_ID_EXISTS` appears zero times in the pinned bundle and is not among the standard codes, repo=adcp ref=3.1.1 path=schemas/enums/error-code.json), and dist/compliance/3.1.1 carries no collision scenario. So "lookup filters by tenant_id + principal_id + creative_id" is our isolation model, ungraded at 3.1.1 — but note that "a cross-principal collision silently creates a new creative" only reconciles with the upsert prose if the upsert is read as account-scoped; state that reading explicitly rather than treating the area as fully silent.

---

### BR-RULE-035: Creative Format Validation
**Obligation ID** BR-RULE-035-01
**Layer** behavioral
**Invariant:** format_id is required. Non-HTTP agent_url skips external validation. HTTP agents checked for reachability and format registration.
**Scenario:**
```gherkin
Given a creative with format_id having non-HTTP agent_url
When format validation runs
Then external validation is skipped

Given a creative with format_id whose HTTP agent is unreachable
When format validation runs
Then a ValueError with agent-unreachable message is raised
```
**Priority:** P1
**Grounded at 3.1.1:** The structured-object shape is right; "format_id is required" is not. `format-id.json` is "A JSON object — never a plain string" with `required: [agent_url, id]` (id matching `^[a-zA-Z0-9_-]+$`), so the 3.1 change the old verdict flagged is real and correctly described (repo=adcp ref=3.1.1 path=schemas/core/format-id.json). But resolving the composition on the creative itself shows format_id is conditionally required, not unconditionally: `creative-asset.json` declares `required: [creative_id, name, assets]` and then a two-branch `oneOf` — branch 1 "Legacy creative (named-format reference)" requires `format_id` and forbids `format_kind`; branch 2 "3.1+ creative (canonical format kind)" requires `format_kind` and forbids `format_id`. A conforming 3.1 creative may legitimately carry no format_id at all (repo=adcp ref=3.1.1 path=schemas/core/creative-asset.json). The rest of the invariant has no pinned counterpart: `agent_url` is typed `format: uri` with a canonicalization requirement for equality comparison, and nothing at 3.1.1 mandates fetching the agent, distinguishes HTTP from non-HTTP schemes, or defines an unreachable-agent failure — so "non-HTTP skips external validation" and the unreachable-agent ValueError grade our behavior.

---

### BR-RULE-036: Generative Creative Build
**Obligation ID** BR-RULE-036-01
**Layer** behavioral
**Invariant:** Creative is generative when format has output_format_ids. Prompt priority: asset roles > inputs[0].context_description > name (create only). Update without prompt preserves existing data.
**Scenario:**
```gherkin
Given a format with output_format_ids = ["fmt_responsive"]
When a creative is synced with assets containing a "message" role
Then the message content is used as the generative build prompt

Given a format with output_format_ids and an update request with no prompt
When the creative is updated
Then the generative build is skipped and existing data is preserved
```
**Priority:** P2
**Grounded at 3.1.1:** The generative trigger is legacy at this version, and the prompt rules have no pinned counterpart. `output_format_ids` on a format is marked `"deprecated": true` — "**DEPRECATED in 3.1. Removed at 4.0.** Use `list_transformers` instead — a transformer declares its own `output_format_ids`, so what a builder can produce is a property of the transformer, not a relationship hung on a format" — while retaining the legacy reading "when present, indicates this format can build creatives in these output formats" for 3.1–3.x, which SDKs "MUST continue to honor" (repo=adcp ref=3.1.1 path=schemas/core/format.json). So "generative when the format has output_format_ids" still functions at the pin but is the deprecated path; the 3.1 way is `transformer_id`, selected from list_transformers, with target formats that "MUST be a subset of the transformer's output_format_ids" (repo=adcp ref=3.1.1 path=schemas/media-buy/build-creative-request.json). The prompt-priority chain is ours: build_creative carries the brief in `message` ("For pure generation, this is the creative brief"), and the `inputs[].context_description` the obligation ranks second is defined on the creative as a preview context — "Preview contexts for generative formats - defines what scenarios to generate previews for" / "Natural language description of the context for AI-generated content" — not as a build prompt, and nothing at 3.1.1 orders asset roles above it or above `name`, nor states that an update without a prompt preserves existing generative data (repo=adcp ref=3.1.1 path=schemas/core/creative-asset.json).

---

### BR-RULE-037: Creative Approval Workflow
**Obligation ID** BR-RULE-037-01
**Layer** behavioral
**Invariant:** approval_mode determines routing: auto-approve (immediate), require-human (pending + workflow + Slack), ai-powered (pending + workflow + background AI). Default is require-human.
**Scenario:**
```gherkin
Given tenant approval_mode = "auto-approve"
When a creative is synced
Then status is set to "approved" with no workflow steps

Given tenant approval_mode = "require-human"
When a creative is synced
Then status is "pending_review", workflow steps created, Slack notification sent immediately
```
**Priority:** P1
**Grounded at 3.1.1:** Partly true. AdCP 3.1.1 does declare a tenant-wide creative approval posture — `media_buy.creative_approval_mode` with enum exactly `["auto_approve", "require_human"]` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json) — and the compliance runner gates auto-approval-dependent storyboards on it via `requires_capability: {path: media_buy.creative_approval_mode, equals: auto_approve}` (repo=adcp ref=3.1.1 path=domains/media-buy/state-machine.yaml). The creative statuses the scenario names are real: `approved` and `pending_review` are both members of the creative lifecycle enum (repo=adcp ref=3.1.1 path=schemas/enums/creative-status.json). Two parts are false. (1) There is no third "ai-powered" mode: the field description states "`ai_assisted` is intentionally not part of the enum until a behavioral contract is defined", and the prose repeats "`ai_assisted` is intentionally not a value until the protocol defines what assistance changes in observable behavior" (repo=adcp ref=3.1.1 path=protocol/get_adcp_capabilities.mdx). (2) There is no mandated default of require-human; 3.1.1 declines a default outright — "When the field is absent, approval behavior is legacy-unspecified; runners SHOULD NOT treat omission as an affirmative `auto_approve` claim" (repo=adcp ref=3.1.1 path=protocol/get_adcp_capabilities.mdx). The routing consequences the invariant asserts — workflow-step creation, Slack notification, background AI review — are nowhere in 3.1.1; `creative_approval_mode` is explicitly "not a notification surface or a new approval workflow", it is only a declaration of whether human review can block serving eligibility. Those consequences grade our own production behavior.

---

### BR-RULE-038: Assignment Package Validation
**Obligation ID** BR-RULE-038-01
**Layer** behavioral
**Invariant:** Package lookup joins MediaPackage to MediaBuy filtered by tenant_id. Strict/lenient per BR-RULE-033. Existing assignments idempotently updated.
**Scenario:**
```gherkin
Given a package_id not found in any media buy for this tenant
When strict mode assignment is attempted
Then a ToolError is raised

Given an assignment for the same creative-package pair already exists
When assignment is attempted again
Then the existing assignment is updated (weight reset to 100)
```
**Priority:** P1
**Grounded at 3.1.1:** Partly true. The failure signal is grounded: `PACKAGE_NOT_FOUND` is a member of the 3.1.1 error-code vocabulary (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json), `sync_creatives` documents it as "Package ID doesn't exist in media buy" (repo=adcp ref=3.1.1 path=creative/task-reference/sync_creatives.mdx), and it is graded as a hard `check: error_code` in the `unknown_package` phase, whose narrative says "the lookup succeeds at the buy level and only fails at the package lookup" (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/invalid_transitions.yaml). Idempotent re-assignment is also grounded in shape: `sync_creatives` upsert mode "Merges package assignments (additive)" and "Same `creative_id` updates existing creative rather than creating duplicates" (repo=adcp ref=3.1.1 path=creative/task-reference/sync_creatives.mdx). Strict/lenient is grounded too: `sync_creatives` declares `validation_mode` — "Validation strictness: `"strict"` (default) or `"lenient"`" (repo=adcp ref=3.1.1 path=creative/task-reference/sync_creatives.mdx) — typed by a two-value enum (repo=adcp ref=3.1.1 path=schemas/enums/validation-mode.json) and carried on the request with `default: "strict"` and the description "'strict' fails entire sync on any validation error. 'lenient' processes valid creatives and reports errors" (repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json). What is false is the weight rule: `CreativeAssignment.weight` is a 0–100 relative delivery weight and "When omitted, the creative receives equal rotation with other unweighted creatives" — there is no reset-to-100 semantics, and 0 means assigned-but-paused (repo=adcp ref=3.1.1 path=schemas/core/creative-assignment.json). The remaining clauses — joining MediaPackage to MediaBuy on tenant_id and raising a ToolError — have no 3.1.1 counterpart; tenant scoping and transport error types are our own production concerns (ToolError is transport-specific and forbidden in `_impl` by our own architecture, not by AdCP).

---

### BR-RULE-039: Assignment Format Compatibility
**Obligation ID** BR-RULE-039-01
**Layer** schema
**Invariant:** Format compatibility checks normalized agent_url and exact format_id against product's format_ids. Empty format_ids means all allowed.
**Scenario:**
```gherkin
Given product format_ids accepts agent "http://agent.com/mcp" id "banner_300x250"
When a creative with agent_url "http://agent.com/mcp/" and id "banner_300x250" is assigned
Then URL normalization strips trailing "/" and the format matches

Given a product with empty format_ids
When any creative format is assigned
Then format compatibility passes (all formats allowed)
```
**Priority:** P1
**Grounded at 3.1.1:** Both halves are contradicted. (1) Trailing-slash stripping is not AdCP normalization. `format-id` mandates that "Callers comparing two `format-id` values MUST canonicalize `agent_url` per the AdCP URL canonicalization rules before treating two formats as the same" (repo=adcp ref=3.1.1 path=schemas/core/format-id.json), and the authoritative eight-step algorithm never strips a trailing path slash — step 5 applies RFC 3986 `remove_dot_segments` and substitutes `/` only "If the path is empty AND an authority is present" — closing with "After all eight steps, comparison is byte-for-byte. Implementations MUST NOT apply additional transformations before comparison" (repo=adcp ref=3.1.1 path=reference/url-canonicalization.mdx). So `http://agent.com/mcp/` and `http://agent.com/mcp` canonicalize to different identifiers at 3.1.1 and MUST NOT match; stripping the slash is exactly the forbidden extra transformation. (2) "Empty `format_ids` means all formats allowed" has no basis and is contradicted: "Products MUST carry `format_ids`, `format_options`, or BOTH; at least one is required" (repo=adcp ref=3.1.1 path=schemas/core/product.json), and the format declaration carries normative closed-set semantics — "`format_options[]` is the closed set of accepted formats for this product. Sellers MUST reject `create_media_buy` requests targeting any `format_kind` (or format option reference) not present in this list ... the rejection is structural, not negotiable" (repo=adcp ref=3.1.1 path=schemas/core/product-format-declaration.json). The same file also forbids the exact-match comparison this obligation assumes: "Legacy named formats MUST be normalized to canonical declarations before comparison; do not exact-match raw `(agent_url, id)` pairs."

---

### BR-RULE-040: Media Buy Status Transition on Assignment
**Obligation ID** BR-RULE-040-01
**Layer** behavioral
**Invariant:** Draft media buy with non-null approved_at transitions to pending_creatives on creative assignment. Other statuses unchanged.
**Scenario:**
```gherkin
Given media buy status="draft" and approved_at is set
When a creative assignment is made
Then status transitions to "pending_creatives"

Given media buy status="draft" and approved_at is null
When a creative assignment is made
Then status remains "draft"
```
**Priority:** P1
**Grounded at 3.1.1:** There is no `draft` media-buy status at 3.1.1 and the transition runs the other way. The status enum is exactly `[pending_creatives, pending_start, active, paused, completed, rejected, canceled]` (repo=adcp ref=3.1.1 path=schemas/enums/media-buy-status.json); `MediaBuy.status` is a direct `$ref` to that enum, and the object's only `allOf` is a `confirmed_at` conditional that contributes no additional status values (repo=adcp ref=3.1.1 path=schemas/core/media-buy.json), so no composition branch reintroduces `draft`. Furthermore `pending_creatives` is the state *before* creatives are attached, not the state entered on assignment: its enumDescription reads "The media buy is approved by the seller and has no creatives assigned — the buyer must attach creatives via `sync_creatives` before the buy can serve." The graded lifecycle is the inverse of the obligation: the buy is created without `creative_assignments` and returns `media_buy_status: pending_creatives`, and after the creative is synced and assigned the validation asserts "media_buy_status advances out of pending_creatives once creatives attached" to `pending_start` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/pending_creatives_to_start.yaml). `approved_at` is likewise not a 3.1.1 media-buy field — the confirmation marker on `core/media-buy.json` is `confirmed_at` (required).

---

### BR-RULE-041: Discovery Endpoint Authentication
**Obligation ID** BR-RULE-041-01
**Layer** behavioral
**Invariant:** Authentication optional for discovery. Invalid tokens treated as missing (MCP). A2A requires valid token if one is provided. Data not scoped by identity.
**Scenario:**
```gherkin
Given no authentication token
When list_authorized_properties is called
Then the system returns full discovery data with principal as "anonymous"

Given an invalid/expired token via MCP
When list_authorized_properties is called
Then the token is treated as absent and full data is returned

Given an invalid token via A2A
When discover_seller_capabilities is called
Then the request is rejected with authentication error
```
**Priority:** P1
**Grounded at 3.1.1:** Both tasks this obligation grades are gone. The "Removed in v3" table lists `list_authorized_properties` task -> `get_adcp_capabilities` portfolio section, with the migration checklist item "Replace `list_authorized_properties` calls with `get_adcp_capabilities` portfolio" (repo=adcp ref=3.1.1 path=reference/whats-new-in-v3.mdx); the task reference states it flatly: "The `list_authorized_properties` task was removed in v3" (repo=adcp ref=3.1.1 path=protocol/get_adcp_capabilities.mdx). `discover_seller_capabilities` does not exist at 3.1.1 either — the string returns zero hits across the pinned prose tree, the compliance tree, and the full schema bundle (an exhaustive name search, so no allOf/$ref branch can reintroduce it); the discovery task is `get_adcp_capabilities` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-request.json), whose request schema resolves `allOf` to core/version-envelope.json only. The successor also gives no anonymous-discovery guarantee to inherit: its documented error table carries `AUTH_MISSING` ("No credentials presented" -> "Provide credentials via auth header") and `AUTH_INVALID` ("Credentials rejected (expired / revoked)") (repo=adcp ref=3.1.1 path=protocol/get_adcp_capabilities.mdx), so 3.1.1 neither mandates nor forbids anonymous discovery — the MCP-treats-invalid-as-missing vs A2A-rejects split is purely our own transport policy and grades our production behavior.

---

### BR-RULE-042: Property Portfolio Assembly
**Obligation ID** BR-RULE-042-01
**Layer** behavioral
**Invariant:** All registered publisher partnerships returned regardless of verification status. Sorted alphabetically. Empty portfolio returns empty array with description.
**Scenario:**
```gherkin
Given a tenant with 3 publisher partnerships (2 verified, 1 unverified)
When list_authorized_properties is called
Then all 3 publishers are returned sorted alphabetically

Given a tenant with no publisher partnerships
When list_authorized_properties is called
Then an empty publisher_domains array is returned with a portfolio_description
```
**Priority:** P1
**Grounded at 3.1.1:** The task this grades no longer exists — the "Removed in v3" table maps `list_authorized_properties` to the `get_adcp_capabilities` portfolio section (repo=adcp ref=3.1.1 path=reference/whats-new-in-v3.mdx), and the migration table maps the old `publisher_domains` field to `media_buy.portfolio.publisher_domains` and the old `portfolio_description` to `media_buy.portfolio.description` (repo=adcp ref=3.1.1 path=protocol/get_adcp_capabilities.mdx). At the successor location the empty-portfolio half of the scenario is now schema-invalid, not merely unmandated: `portfolio.required` is `["publisher_domains"]` and the array carries `minItems: 1`, so a seller cannot conformantly emit an empty `publisher_domains` array with only a description (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). I resolved that response schema's `allOf` (core/version-envelope.json + core/protocol-envelope.json) before checking the portfolio object, and neither branch adds any ordering or verification-status rule; no alphabetical-sort requirement and no verified/unverified distinction appears anywhere in the portfolio field set or the pinned prose. Sort order and inclusion-regardless-of-verification therefore grade our own production behavior.

---

### BR-RULE-043: Context Echo Invariant
**Obligation ID** BR-RULE-043-01
**Layer** schema
**Invariant:** Request context is echoed unchanged in the response. Context is opaque. Applies to all response paths.
**Scenario:**
```gherkin
Given a request with context = {"trace_id": "abc123"}
When the response is returned
Then context = {"trace_id": "abc123"} is in the response

Given a request without context
When the response is returned
Then context is absent from the response
```
**Priority:** P1
**Grounded at 3.1.1:** True, and it is graded. The envelope defines `context` as "Per-request opaque caller-supplied correlation object echoed unchanged in the response ... that the agent MUST preserve byte-for-byte without parsing", and declares itself authoritative for the field across all task schemas: "The envelope declaration is **authoritative** for the schema definition; per-task body declarations are mirrors" — covering the 147 task schemas that also declare a body-level `context` (repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json). The referenced type is opaque: "Context data is never parsed by AdCP agents - it's simply preserved and returned" (repo=adcp ref=3.1.1 path=schemas/core/context.json). The absence half also holds: the envelope's `required` list is `["status"]` only, so omitting `context` is conformant. The echo is graded on the wire with an exact-value check — `check: field_present path: "context"` plus `check: field_value path: "context.correlation_id" value: "capability_discovery--get_capabilities"` described as "Context correlation_id returned unchanged" (repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml). Note this closes the old note's caveat from the spec side: the capabilities endpoint is exactly where 3.1.1 grades context echo, and its request schema does declare `context` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-request.json).

---

### BR-RULE-044: Advertising Policy Disclosure
**Obligation ID** BR-RULE-044-01
**Layer** behavioral
**Invariant:** When advertising_policy enabled and at least one policy array non-empty, human-readable summary included. Omitted when disabled or all arrays empty.
**Scenario:**
```gherkin
Given tenant advertising_policy enabled with prohibited_categories = ["tobacco"]
When list_authorized_properties is called
Then advertising_policies field contains a summary mentioning tobacco

Given tenant advertising_policy disabled
When list_authorized_properties is called
Then advertising_policies field is omitted
```
**Priority:** P2
**Grounded at 3.1.1:** The task is removed — `list_authorized_properties` -> `get_adcp_capabilities` portfolio section (repo=adcp ref=3.1.1 path=reference/whats-new-in-v3.mdx) — and the field it names moved: the migration table maps `advertising_policies` to `media_buy.portfolio.advertising_policies` (repo=adcp ref=3.1.1 path=protocol/get_adcp_capabilities.mdx). At the new location the field survives only as a free-form optional string, "Advertising content policies, restrictions, and guidelines", `type: string`, `maxLength: 10000`, and it is not in `portfolio.required` (which is `["publisher_domains"]`) (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). I resolved that response schema's `allOf` (core/version-envelope.json + core/protocol-envelope.json) before making that absence claim. 3.1.1 states no conditional-inclusion rule at all: nothing ties emission of this string to an `advertising_policy` enable flag, to non-empty `prohibited_categories` arrays, or to any summarization requirement, and no storyboard grades it. The present/omitted logic therefore grades our own production behavior.

---

### BR-RULE-045: Publisher Domain Filter Validation
**Obligation ID** BR-RULE-045-01
**Layer** schema
**Invariant:** Domain must match lowercase alphanumeric pattern. Filter array must have >= 1 item. Valid but non-matching domains yield empty results (not error).
**Scenario:**
```gherkin
Given filter with domain "CNN.COM" (uppercase)
When list_authorized_properties is called
Then the request is rejected with DOMAIN_INVALID_FORMAT

Given filter with domain "nonexistent.com" (valid format, no match)
When list_authorized_properties is called
Then the request succeeds with empty results for that domain
```
**Priority:** P2
**Grounded at 3.1.1:** The filtered request this grades no longer exists. `list_authorized_properties` was removed in v3 (repo=adcp ref=3.1.1 path=reference/whats-new-in-v3.mdx), and its successor's request schema carries no domain filter at all — after resolving its `allOf` (core/version-envelope.json), the only declared properties are `protocols`, `context`, and `ext`, with no `publisher_domains` or `property_tags` array (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-request.json). So "filter array must have >= 1 item" and "valid but non-matching domains yield empty results" have no 3.1.1 surface to grade. The error code is also gone/never existed at this pin: `DOMAIN_INVALID_FORMAT` is absent from the 3.1.1 error vocabulary (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json) and returns zero hits across the pinned prose and compliance trees. The only surviving fragment is the lowercase-domain shape, and it now constrains an emitted *response* value rather than a rejected filter: `media_buy.portfolio.publisher_domains` items carry `pattern: ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$` with `minItems: 1` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json), under which "CNN.COM" is an invalid value to emit.

---

### BR-RULE-047: Signal Filter Conjunction & Defaults
**Obligation ID** BR-RULE-047-01
**Layer** behavioral
**Invariant:** Signal filters are optional, combine as AND. max_results limits final count.
**Scenario:**
```gherkin
Given catalog_types=["marketplace"] and max_cpm=5.0
When get_signals is called
Then only marketplace signals with cpm <= 5.0 are returned

Given max_results=3 and 10 signals match
When results are returned
Then only 3 signals are included
```
**Priority:** P2
**Grounded at 3.1.1:** Partly true. Optionality holds: `get-signals-request.json` declares no `required` list, its `allOf` branches (core/version-envelope.json plus a wholesale-only conditional) and its if/then/else never reference `filters`, and every member of the filters object is optional (repo=adcp ref=3.1.1 path=schemas/signals/get-signals-request.json; repo=adcp ref=3.1.1 path=schemas/core/signal-filters.json). Three parts need correcting. (1) `max_results` is deprecated at this pin: "**Deprecated.** Use `pagination.max_results` instead. When both are present, `pagination.max_results` takes precedence. Will be removed in AdCP 4.0", and `pagination.max_results` is a page size (max 100, default 50), not a cap on the final matched count (repo=adcp ref=3.1.1 path=signals/tasks/get_signals.mdx); the graded storyboard exercises `pagination.max_results`, never the legacy field (repo=adcp ref=3.1.1 path=domains/signals/scenarios/get_signals_async.yaml). (2) The `max_cpm` semantics in the scenario are wrong: 3.1.1 says it "Excludes signals where all CPM-based pricing options exceed this value. Signals without CPM-based pricing options are not affected by this filter" — so a `max_cpm=5.0` result set is not "only signals with cpm <= 5.0"; non-CPM-priced signals pass through (repo=adcp ref=3.1.1 path=schemas/core/signal-filters.json; repo=adcp ref=3.1.1 path=signals/tasks/get_signals.mdx). (3) Cross-field AND combination is never stated; the only combination semantics 3.1.1 spells out on this task are OR, and for a different field — "Signals are returned if they are available on *any* of the requested destinations (OR semantics)" (repo=adcp ref=3.1.1 path=signals/tasks/get_signals.mdx). AND-combination across filter fields therefore grades our own production behavior.

---

### BR-RULE-048: Signal Activation Validation
**Obligation ID** BR-RULE-048-01
**Layer** behavioral
**Invariant:** Premium signals (IDs starting with "premium_") require manual approval. Response is atomic (success XOR error).
**Scenario:**
```gherkin
Given signal_id = "premium_auto_intenders"
When activate_signal is called
Then APPROVAL_REQUIRED error is returned

Given a valid non-premium signal_id
When activate_signal is called
Then activation proceeds and deployments are returned
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — the atomicity half holds, the premium half is ours. Atomicity is enforced structurally at `repo=adcp ref=3.1.1 path=schemas/signals/activate-signal-response.json`, whose description reads "Returns either complete success data OR error information, never both. This enforces atomic operation semantics" and which composes allOf(core/version-envelope, core/protocol-envelope) plus a `oneOf` over ActivateSignalSuccess (`required: ["deployments"]`, `not: {required: ["errors"]}`) and ActivateSignalError (`required: ["errors"]` with `minItems: 1`, `not: {anyOf: [deployments, sandbox]}`). The premium-approval half is not the spec's: activation is keyed on `signal_agent_segment_id` — "Opaque activation handle ... Pass this string verbatim — do not pass the signal_id object" (`repo=adcp ref=3.1.1 path=schemas/signals/activate-signal-request.json`, required `[idempotency_key, signal_agent_segment_id, destinations]`) — so a `"premium_"`-prefixed signal_id is not the field activate_signal reads; `APPROVAL_REQUIRED` is absent from the 92-value enum at `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json`; the graded activate_signal error arms allow only REFERENCE_NOT_FOUND/INVALID_REQUEST and INVALID_REQUEST/VALIDATION_ERROR (`repo=adcp ref=3.1.1 path=universal/error-compliance-signals.yaml`); and the marketplace storyboard grades both activation paths straight through with no approval gate (`repo=adcp ref=3.1.1 path=specialisms/signal-marketplace/index.yaml`). The premium gate grades our own seller policy, not AdCP conformance.

---

### BR-RULE-049: Per-Filter Format Discovery Semantics
**Obligation ID** BR-RULE-049-01
**Layer** behavioral
**Invariant:** type=exact match, format_ids=(agent_url, id) pair match with silent exclusion, asset_types=OR, dimensions=ANY render, is_responsive=bidirectional, name_search=case-insensitive substring.
**Scenario:**
```gherkin
Given type_filter="video"
When list_creative_formats is called
Then only formats with category "video" are returned

Given asset_types=["image", "video"]
When list_creative_formats is called
Then formats with either image OR video assets are returned (OR semantics)

Given is_responsive=false
When list_creative_formats is called
Then only formats with no responsive dimensions are returned
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — four of the six filter semantics hold, two do not. HOLDS: `format_ids` really is an (agent_url, id) pair match — `repo=adcp ref=3.1.1 path=schemas/core/format-id.json` is "A JSON object — never a plain string" with `required: ["agent_url", "id"]` and an explicit canonicalization rule on agent_url; dimension filters are ANY-render on the sales-agent surface — `max_width` is "Returns formats where ANY render has width <= this value. For multi-render formats, matches if at least one render fits" (`repo=adcp ref=3.1.1 path=schemas/media-buy/list-creative-formats-request.json`); `name_search` is "Search for formats by name (case-insensitive partial match)" in that same file; and `asset_types` is OR — the pinned prose task reference for list_creative_formats states "Uses OR logic. **Recommended over `type` filter.**", which settles the AND-shaped example wording in the schema description. FALSE/mislocated: there is no `type` filter on the sales-agent request at all — after resolving its only `allOf` member (core/version-envelope, which contributes just adcp_version/adcp_major_version) the property set is format_ids, asset_types, max/min_width, max/min_height, is_responsive, name_search, publisher_domain, property_id, wcag_level, disclosure_positions, disclosure_persistence, output_format_ids, input_format_ids, pagination, context, ext; `type` exists only on the creative-agent variant `repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json` as "Filter by format type (technical categories with distinct requirements)" with `enum: [audio, video, display, dooh]`, and the prose marks it deprecated in favour of asset_types. Note that the pin does treat these values as a category vocabulary — they are the "format category" axis ("describes HOW an ad renders", orthogonal to channels) at `repo=adcp ref=3.1.1 path=docs/reference/media-channel-taxonomy.mdx` — so the objection to the scenario is that this filter is mislocated onto the sales-agent surface and deprecated, not that "category" is the wrong word for it. SPEC-SILENT: `is_responsive` is documented only in the true direction ("When true, returns formats without fixed dimensions") — the bidirectional false branch and the silent exclusion of unmatched format_ids are our behavior.

---

### BR-RULE-050: Per-Filter Signal Discovery Semantics
**Obligation ID** BR-RULE-050-01
**Layer** behavioral
**Invariant:** catalog_types and data_providers use OR within-filter. max_cpm and min_coverage enforce numeric thresholds. signal_spec is case-insensitive substring.
**Scenario:**
```gherkin
Given catalog_types=["marketplace", "custom"]
When get_signals is called
Then signals of either marketplace OR custom type are returned

Given max_cpm=2.0 and a signal with cpm=2.5
When get_signals filters
Then that signal is excluded
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED. `catalog_types` and `data_providers` are real array filters at `repo=adcp ref=3.1.1 path=schemas/core/signal-filters.json` ("Filter by catalog type", "Filter by specific data providers", each `minItems: 1`) and the pinned get_signals prose confirms they carry set semantics for wholesale-feed-version canonicalization — but the spec never states "OR within filter" in those words, so membership-OR is consistent-with, not mandated-by, 3.1.1. `max_cpm` exists with `minimum: 0` but is narrower than the obligation: "Maximum CPM filter. Applies only to signals with model='cpm'", and the prose adds "Excludes signals where **all** CPM-based pricing options exceed this value. Signals without CPM-based pricing options are not affected" — so the scenario's "signal with cpm=2.5 is excluded at max_cpm=2.0" holds only when every CPM option on that signal exceeds the cap. The threshold field is named `min_coverage_percentage` (number, 0–100), not `min_coverage`. The `signal_spec` claim is FALSE at the pin: `repo=adcp ref=3.1.1 path=schemas/signals/get-signals-request.json` defines it as "Natural language description of the desired signals. When used alone, enables semantic discovery", and `discovery_mode: "brief"` is "semantic discovery — signal_spec, signal_refs, or legacy signal_ids is required and the agent performs inference/RAG"; case-insensitive substring matching is our implementation of that contract, not the contract.

---

### BR-RULE-051: Performance Index Scale Semantics
**Obligation ID** BR-RULE-051-01
**Layer** schema
**Invariant:** 0.0 = no value, 1.0 = expected, > 1.0 = above expected. Must be >= 0. Scores < 0.8 trigger optimization recommendation.
**Scenario:**
```gherkin
Given performance_index = -0.5
When provide_performance_feedback is called
Then the request is rejected by schema validation

Given performance_index = 0.3
When performance feedback is processed
Then the system flags low performance and recommends optimization
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — the scale and the floor hold, the 0.8 trigger does not. `repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json` defines `performance_index` verbatim as "Normalized performance score (0.0 = no value, 1.0 = expected, >1.0 = above expected)" with `"minimum": 0`, and lists it in `required: [idempotency_key, media_buy_id, measurement_period, performance_index]` — so `performance_index: -0.5` is a schema rejection, exactly as the first scenario says (identical wording and floor on the entity at `repo=adcp ref=3.1.1 path=schemas/core/performance-feedback.json`). No 0.8 threshold exists anywhere at the pin: the only storyboard that grades this task submits `performance_index: 1.4` and validates only `response_schema` plus `success: true` (`repo=adcp ref=3.1.1 path=specialisms/sales-catalog-driven/index.yaml`), and its phase narrative puts the reference boundary at 1.0 — "A performance_index above 1.0 means the campaign is exceeding expectations ... Below 1.0 means underperforming". The 0.8 optimization trigger grades our own recommendation policy.

---

### BR-RULE-052: Capabilities Graceful Degradation
**Obligation ID** BR-RULE-052-01
**Layer** behavioral
**Invariant:** When internal deps fail, return valid but degraded response. No tenant = minimal. Adapter failure = default channels/targeting. DB failure = placeholder domain. Never propagate error to caller.
**Scenario:**
```gherkin
Given no tenant context can be resolved
When discover_seller_capabilities is called
Then a minimal response with adcp v3 + supported_protocols=[media_buy] is returned

Given adapter lookup fails
When capabilities are assembled
Then channels default to [display] and targeting defaults to geo_countries=true, geo_regions=true
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED, and one of the stated defaults is actively wrong. There is no `discover_seller_capabilities` task at 3.1.1 — capability discovery is `get_adcp_capabilities` (`repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml`, `task: get_adcp_capabilities`), whose graded checks are `field_present adcp.major_versions` and `field_present supported_protocols` against an expectation of "your agent's full capability declaration". The "minimal response" shape is at least well-formed: after resolving allOf(core/version-envelope, core/protocol-envelope), `repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json` has `required: ["adcp", "supported_protocols"]` — but "adcp v3" is carried as `adcp.major_versions` (integers, deprecated in favour of release-precision `supported_versions`), and declaring `media_buy` in `supported_protocols` "commit[s] the agent to pass the baseline compliance storyboard at /compliance/{version}/protocols/{protocol}/", so a degraded default is a substantive claim, not a neutral placeholder. The targeting default is contradicted outright: `media_buy.execution.targeting` in that same schema states "If declared true/supported, buyer can use these targeting parameters and seller MUST honor them", so defaulting `geo_countries`/`geo_regions` to true when the adapter lookup failed asserts a binding capability the agent cannot honor; likewise `media_buy.portfolio.primary_channels` items `$ref` `repo=adcp ref=3.1.1 path=schemas/enums/channels.json`, so a fabricated `[display]` is an unverified inventory claim. The graceful-degradation rule itself (never propagate the error, placeholder domain on DB failure) is spec-silent and grades our own behavior.

---

### BR-RULE-053: Channel Alias Resolution
**Obligation ID** BR-RULE-053-01
**Layer** behavioral
**Invariant:** "video" maps to "olv", "audio" maps to "streaming_audio". Unrecognized channels silently dropped.
**Scenario:**
```gherkin
Given adapter reports channel "video"
When capabilities response is assembled
Then channel is mapped to "olv" in the response

Given adapter reports channel "metaverse"
When capabilities response is assembled
Then that channel is silently dropped (not included)
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED. The drop half is a schema consequence and holds: `media_buy.portfolio.primary_channels` in `repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json` has `items: {$ref: enums/channels.json}`, and the 20-value enum at `repo=adcp ref=3.1.1 path=schemas/enums/channels.json` contains neither "video", "audio" nor "metaverse" — so an adapter value outside that enum must not be emitted. The mapping half is not spec-defined and is over-simplified: 3.1.1 treats video and audio as *format categories* orthogonal to channels, and the enumDescriptions split each across several channels — `olv` is "Online video advertising **outside CTV** (pre-roll, outstream, in-app video)" while `ctv` is "Connected TV and streaming on television screens"; `streaming_audio` is "Digital audio streaming services (Spotify, Pandora, etc.)" while `radio` is "Traditional AM/FM radio broadcast" and `podcast` is "Podcast advertising (host-read or dynamically inserted)". A blanket video→olv / audio→streaming_audio map therefore mislabels CTV, social, retail-media video and podcast/radio audio. Nothing at the pin requires the drop to be *silent* either — the response carries an `errors` array typed as core/error.json for warnings. The specific mapping table grades our adapter normalization, not AdCP conformance.

---

### BR-RULE-054: Account Access Scoping
**Obligation ID** BR-RULE-054-01
**Layer** behavioral
**Invariant:** list_accounts returns only accounts accessible to the authenticated agent. No accounts = empty array, not error.
**Scenario:**
```gherkin
Given agent_A has access to 2 accounts
When agent_A calls list_accounts
Then only those 2 accounts are returned

Given agent_B has no accessible accounts
When agent_B calls list_accounts
Then an empty accounts array is returned (not an error)
```
**Priority:** P1
**Grounded at 3.1.1:** HOLDS, both halves. Caller scoping is stated on the wire contract itself: `repo=adcp ref=3.1.1 path=schemas/account/list-accounts-response.json` types `accounts` as "Array of accounts accessible to the authenticated agent", and `repo=adcp ref=3.1.1 path=schemas/account/list-accounts-request.json` is "Request parameters for listing accounts accessible to the authenticated agent" whose `account` filter returns "only matching accounts visible to the authenticated caller". The empty-array half follows structurally: the response composes allOf(core/version-envelope, core/protocol-envelope) — neither of which contributes an alternative arm (version-envelope adds only adcp_version/adcp_major_version; protocol-envelope adds the status/context/task envelope fields) — there is no `oneOf` success/error split as there is on sync_accounts, and `required: ["accounts"]` carries no `minItems`. A caller with zero accessible accounts therefore has exactly one conformant rendering: `accounts: []`. The storyboard grades the same scoping model, seeding accounts that "are visible to the requesting compliance principal for this run and MUST NOT rely on production tenant data already present in the seller's sandbox" (`repo=adcp ref=3.1.1 path=universal/pagination-integrity-list-accounts.yaml`).

---

### BR-RULE-055: Account Operation Authentication Policy
**Obligation ID** BR-RULE-055-01
**Layer** behavioral
**Invariant:** sync_accounts requires valid auth. list_accounts works without auth but scopes results. Unauthenticated list returns empty array.
**Scenario:**
```gherkin
Given no valid authentication
When sync_accounts is called
Then AUTH_REQUIRED error is returned

Given no authentication
When list_accounts is called
Then an empty accounts array is returned (not an error)
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED. That sync_accounts is an authenticated operation is consistent with the pin — its error variant is "Operation failed completely, no accounts were processed" carrying "Operation-level errors (e.g., authentication failure, service unavailable)" (`repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json`) — but the demanded code is stale: `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json` documents `AUTH_REQUIRED` as "**Deprecated** — use `AUTH_MISSING` (no credentials presented) or `AUTH_INVALID` (credentials presented and rejected). Retained as a backward-compatible alias during the 3.x deprecation window", and `AUTH_MISSING` is the MUST: "Sellers MUST return this code when no `Authorization` header was included in the request". A scenario asserting literally AUTH_REQUIRED is over-specified at 3.1.1. The list_accounts half is unsupported: `repo=adcp ref=3.1.1 path=schemas/account/list-accounts-request.json` and `repo=adcp ref=3.1.1 path=schemas/account/list-accounts-response.json` define the task only over "the authenticated agent" / "the authenticated caller"; 3.1.1 defines no unauthenticated list mode and nowhere says an anonymous caller gets an empty array instead of AUTH_MISSING. Returning `accounts: []` to an unauthenticated caller grades our own auth policy, not AdCP conformance.

---

### BR-RULE-056: Sync Upsert Semantics
**Obligation ID** BR-RULE-056-01
**Layer** behavioral
**Invariant:** sync_accounts creates new or updates existing, returning per-account action (created/updated/unchanged/failed). House is echoed.
**Scenario:**
```gherkin
Given a new account not on the seller
When sync_accounts is called
Then per-account result has action=created with seller-assigned account_id

Given an existing account with no changes
When sync_accounts is called
Then per-account result has action=unchanged
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED — the upsert action vocabulary holds exactly, the two side claims do not. Inside the SyncAccountsSuccess branch of `repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json`, each `accounts[]` entry carries `action` with `enum: ["created", "updated", "unchanged", "failed"]` described as "created: new account provisioned. updated: existing account modified. unchanged: no changes needed. failed: could not process (see errors)", and `action` is in the entry's `required: ["brand", "operator", "action", "status"]` — so the upsert semantics and both scenario outcomes are grounded. But `account_id` is NOT required on a created entry: the pinned example "Rejected account — no account_id assigned" shows `action: "created"` with `status: "rejected"` and no `account_id`, so "created with seller-assigned account_id" is the normal case, not the invariant. And there is no `house` field to echo — after resolving the response's allOf(version-envelope, protocol-envelope) and its oneOf branches, the echoed identity fields on the entry are `brand` ("Brand reference, echoed from the request") and `operator` ("Operator domain, echoed from request"); "house" appears at 3.1.1 only as the brand.json portfolio concept behind `brand_id` — "Brand identifier within the house portfolio" at `repo=adcp ref=3.1.1 path=schemas/core/brand-ref.json` — never as a sync_accounts wire field.

---

### BR-RULE-057: Sync Atomic Response
**Obligation ID** BR-RULE-057-01
**Layer** behavioral
**Invariant:** Response contains EITHER accounts[] (success) OR errors[] (error), never both. Per-account failures are within the success variant.
**Scenario:**
```gherkin
Given sync_accounts processes 3 accounts, 1 fails
When the response is returned
Then response is success variant with accounts[] (including action=failed for 1)

Given an authentication failure
When sync_accounts is called
Then response is error variant with errors[], no accounts[]
```
**Priority:** P0
**Grounded at 3.1.1:** HOLDS, exactly as written. `repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json` composes allOf(core/version-envelope, core/protocol-envelope) with a `oneOf` over two mutually exclusive branches: SyncAccountsSuccess (`required: ["accounts"]`, `not: {required: ["errors"]}`) and SyncAccountsError (`required: ["errors"]` with `minItems: 1`, `not: {anyOf: [{required: [accounts]}, {required: [dry_run]}]}`) — the `not` clauses make "never both" a structural guarantee in both directions, not just prose. The per-account placement is equally explicit: the success branch is titled "Sync operation processed accounts (individual accounts may be pending or have `action=failed`)", each entry's `errors` array is "Per-account errors (only present when action is 'failed')", and the error branch is "Operation failed completely, no accounts were processed" listing "authentication failure" as its example — matching both scenarios (3-of-4 succeed with one `action: "failed"` inside the success variant; auth failure yields the errors-only variant). The pinned example "Unsupported billing — seller rejects the request" shows the mixed case on the wire: `status: "completed"` with `accounts[0].action: "failed"` and a per-entry `BILLING_NOT_SUPPORTED` error, no top-level `errors`.

---

### BR-RULE-058: Brand Identity Resolution
**Obligation ID** BR-RULE-058-01
**Layer** behavioral
**Invariant:** Brands identified by house domain + optional brand_id, resolved via /.well-known/brand.json. House echoed in response.
**Scenario:**
```gherkin
Given account with house="acme.com" and brand_id="widgets"
When sync_accounts processes the account
Then brand identity resolved via acme.com/.well-known/brand.json

Given a per-account result is returned
Then it echoes the same house value from the request
```
**Priority:** P2
**Grounded at 3.1.1:** Holds. The account key is a BrandRef with `required: ["domain"]` and `brand_id` optional ("Brand identifier within the house portfolio. Optional for single-brand domains"); `domain` is "Domain where /.well-known/brand.json is hosted, or the brand's operating domain", and the schema description spells out the house case explicitly — "For house-of-brands domains, brand_id identifies the specific brand" (repo=adcp ref=3.1.1 path=schemas/core/brand-ref.json). sync_accounts consumes that ref as the provisioning-mode `brand` field and resolves the counterparty against the same document: `operator` is "Verified against the brand's authorized_operators in brand.json" (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json). The per-account result echoes it — `brand` is "Brand reference, echoed from the request" and appears in the result item's `required: ["brand","operator","action","status"]` (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). Two wording nuances the obligation glosses over: brand-ref.json allows the domain to be "registered in the brand registry" as an alternative to hosting /.well-known/brand.json, so well-known resolution is the primary but not the sole mechanism; and there is no wire field literally named `house` on the accounts surface — the house is carried as `brand.domain` (checked after resolving the request/response `allOf` into core/version-envelope.json and core/protocol-envelope.json, whose properties are `adcp_version`/`adcp_major_version` and the protocol envelope fields respectively).

---

### BR-RULE-059: Billing Model Policy
**Obligation ID** BR-RULE-059-01
**Layer** behavioral
**Invariant:** Seller assigns billing model, may override buyer's request with warning. Omitted billing uses seller default.
**Scenario:**
```gherkin
Given buyer requests billing model "brand_direct" but seller only supports "operator"
When sync_accounts processes
Then billing is set to "operator" with a per-account warning explaining the override
```
**Priority:** P2
**Grounded at 3.1.1:** False on both halves. `billing` is never seller-defaulted: each entry's key shape is a `oneOf`, whose `ProvisioningMode` branch carries `required: ["brand","operator","billing"]`, while the `SettingsUpdateMode` branch forbids it outright — "MUST be absent in settings-update mode (billing is fixed at provisioning time and cannot be changed via settings-update)" (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json). Nor may the seller silently substitute a different model with a warning: the response field is specified as "Who is invoiced on this account. Matches the requested billing model", and the worked example titled "Unsupported billing — seller rejects the request" returns `action: "failed"`, `status: "rejected"` and `errors[0].code = "BILLING_NOT_SUPPORTED"` — a rejection, not an override (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). `BILLING_NOT_SUPPORTED` is a published standard code (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json). The result's `warnings[]` array exists but is a free-text `string` list with no binding to a billing decision. The omit-uses-seller-default behavior the obligation asserts is specified in 3.1.1 for `payment_terms` only ("When omitted, the seller applies its default terms", with `PAYMENT_TERMS_NOT_SUPPORTED` on refusal), not for `billing`.

---

### BR-RULE-060: Account Approval Workflow
**Obligation ID** BR-RULE-060-01
**Layer** behavioral
**Invariant:** Accounts requiring review enter pending_approval with setup info (message required, optional url/expiry). Push notification webhook for async updates.
**Scenario:**
```gherkin
Given an account requires seller review
When sync_accounts processes
Then per-account result has status=pending_approval with setup.message

Given an account does not require review
When sync_accounts processes
Then per-account result has status=active (no setup)
```
**Priority:** P2
**Grounded at 3.1.1:** Holds. Every element of the invariant is in the pinned schema: the per-account result `status` enum contains `pending_approval`, glossed "seller reviewing (credit, legal)"; the `setup` object is "Setup information for pending accounts. Provides the agent (or human) with next steps to complete account activation" with `required: ["message"]` and optional `url` (`format: uri`) and `expires_at` (`format: date-time`) — exactly the message-required / url+expiry-optional shape claimed; the schema's own worked example returns `status: "pending_approval"` with a populated `setup` block (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). The async channel is likewise present: `push_notification_config` is "Webhook for async notifications when account status changes (e.g., pending_approval transitions to active)", and the request further states that account status changes are observed "through `list_accounts` polling or the one-shot `sync_accounts.push_notification_config` async result channel" rather than through account-level `notification_configs` (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json). One scoping caveat: the pending⇒setup binding is prose in the field descriptions, not a JSON-Schema conditional — after resolving the response `allOf` (core/version-envelope.json, core/protocol-envelope.json) and the success/error `oneOf`, there is no `if/then` requiring `setup` when `status` is `pending_approval` nor forbidding it on `active`, so the scenario's second leg ("status=active (no setup)") grades our production choice rather than a 3.1.1 constraint.

---

### BR-RULE-061: Delete Missing Deactivation Policy
**Obligation ID** BR-RULE-061-01
**Layer** behavioral
**Invariant:** delete_missing=true deactivates absent accounts scoped to authenticated agent only. Default is false.
**Scenario:**
```gherkin
Given delete_missing=true and agent previously synced accounts [A, B, C] but current request has [A, B]
When sync_accounts processes
Then account C is deactivated

Given delete_missing=true and agent_X previously synced [X1]
When agent_Y syncs with delete_missing=true without X1
Then X1 is NOT affected (agent-scoped deactivation)
```
**Priority:** P1
**Grounded at 3.1.1:** Holds essentially verbatim. `delete_missing` is declared `{"type": "boolean", "default": false}` with the description "When true, accounts previously synced by this agent but not included in this request will be deactivated. Scoped to the authenticated agent — does not affect accounts managed by other agents. Use with caution." (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json). That covers all three clauses: the deactivate-on-absent semantics, the agent-scoping that makes the obligation's agent_X/agent_Y leg correct, and the `false` default. Composition resolved: the request's only composition is `allOf: [core/version-envelope.json]`, which contributes `adcp_version`/`adcp_major_version` and no `required` array, so the effective required set is the declared `required: ["idempotency_key","accounts"]` — `delete_missing` is optional and omission is equivalent to explicit `false`. Coverage caveat: no pinned storyboard exercises it — grep for `delete_missing` across the whole compliance tree returns zero hits, so this obligation is spec-grounded but ungraded by conformance.

---

### BR-RULE-062: Dry Run Preview Mode
**Obligation ID** BR-RULE-062-01
**Layer** schema
**Invariant:** dry_run=true returns what would change without applying modifications. Response includes dry_run=true.
**Scenario:**
```gherkin
Given dry_run=true
When sync_accounts is called
Then response includes dry_run=true and per-account results, but no state is changed

Given dry_run=false (or omitted)
When sync_accounts is called
Then changes are applied normally
```
**Priority:** P2
**Grounded at 3.1.1:** Partly true — the request semantics hold, the mandatory response echo does not. On the request side the claim is exact: `dry_run` is `{"type": "boolean", "default": false}`, "When true, preview what would change without applying. Returns what would be created/updated/deactivated." (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json). On the response side the field exists but is not obligatory: resolving the response `allOf` (core/version-envelope.json + core/protocol-envelope.json) and its `oneOf`, the `SyncAccountsSuccess` branch declares `dry_run` ("Whether this was a dry run (no actual changes made)") but its `required` array is `["accounts"]` only — so a conformant seller MAY omit the echo, and requiring `dry_run: true` on the response grades our own behavior. The one hard rule 3.1.1 does state about it is the inverse: the `SyncAccountsError` branch forbids the field via `"not": {"anyOf": [{"required": ["accounts"]}, {"required": ["dry_run"]}]}`, so `dry_run` MUST NOT appear on an operation-level failure (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json).

---

### BR-RULE-063: Content Standards Authentication
**Obligation ID** BR-RULE-063-01
**Layer** behavioral
**Invariant:** All content standards CRUD operations require valid authentication. No anonymous access.
**Scenario:**
```gherkin
Given no authentication token
When any content standards operation is called
Then the operation is rejected with authentication error

Given a valid authentication token
When create_content_standards is called
Then the operation proceeds under the resolved tenant and principal
```
**Priority:** P1
**Grounded at 3.1.1:** The authentication requirement is real but the rejection shape in the obligation is wrong, and the second scenario leg is not spec vocabulary. 3.1.1 grades auth universally: "Every AdCP agent MUST require authentication on protected operations", with the tiered rule that discovery tasks are public while "operations that return tenant-scoped data or modify state ... require credentials" (repo=adcp ref=3.1.1 path=universal/security.yaml). Content-standards CRUD sits in that protected class — `create_content_standards` carries `x-mutates-state: true` (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-request.json) — though 3.1.1 never names a content-standards task as the auth probe; the probe task is test-kit configurable and defaults to `list_creatives`. Corrections: (a) the graded rejection is at the transport layer, not in-band — the `probe_unauth` step asserts `check: http_status_in` with `allowed_values: [401, 403]` plus `on_401_require_header` demanding a `WWW-Authenticate` header, and no step requires an AdCP error payload; `AUTH_REQUIRED`/`AUTH_MISSING`/`AUTH_INVALID` exist in the vocabulary (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json) but 3.1.1 mandates none of them for this case. (b) "proceeds under the resolved tenant and principal" has no 3.1.1 counterpart — tenant/principal are our internal identity model, so that leg grades our production behavior.

---

### BR-RULE-064: Content Standards Scope Requirements
**Obligation ID** BR-RULE-064-01
**Layer** schema
**Invariant:** Scope requires languages (minItems: 1). countries_all uses AND logic. channels_any uses OR logic. countries and channels are optional.
**Scenario:**
```gherkin
Given a content standard with scope languages_any=["en"] and countries_all=["US", "UK"]
When the standard is applied
Then it applies to content in English AND in both US AND UK

Given a content standard with scope channels_any=["display", "social"]
When the standard is applied
Then it applies to display OR social channels
```
**Priority:** P2
**Grounded at 3.1.1:** True of create, not of the other two surfaces. On `create_content_standards` the claim is exact: `scope` is an object with `required: ["languages_any"]`; `languages_any` has `minItems: 1` and is described "BCP 47 language tags ... Standards apply to content in ANY of these languages (OR logic)"; `countries_all` is "ISO 3166-1 alpha-2 country codes. Standards apply in ALL listed countries (AND logic)" and `channels_any` is "Advertising channels. Standards apply to ANY of the listed channels (OR logic)", both `minItems: 1` and both absent from `scope.required` — i.e. optional, exactly as claimed, and `scope` itself is in the request's top-level `required: ["idempotency_key","scope"]` (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-request.json). The correction: `update_content_standards` carries the same three properties with identical AND/OR descriptions but its `scope` object has **no** `required` array at all, so `languages_any` is optional on update (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-request.json); and the persisted resource has no `scope` wrapper — `countries_all`/`channels_any`/`languages_any` sit flat on the object with `required: ["standards_id"]` only (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json). So "Scope requires languages" is a create-time constraint, not an invariant of the standards object.

---

### BR-RULE-065: Scope Conflict Detection
**Obligation ID** BR-RULE-065-01
**Layer** behavioral
**Invariant:** Create/update that would overlap scope with existing standard for same tenant is rejected with SCOPE_CONFLICT and conflicting_standards_id.
**Scenario:**
```gherkin
Given an existing standard covering scope {en, US, display}
When creating a new standard with overlapping scope {en, US, display}
Then the operation is rejected with SCOPE_CONFLICT and the existing standard's ID
```
**Priority:** P2
**Grounded at 3.1.1:** The scope-conflict rejection is grounded; the error code is documented but not enum-published, and the schema and the task page disagree on where the conflict id sits. 3.1.1 models overlapping scope as a create/update failure: the error branch of the create response carries `conflicting_standards_id` — "If the error is a scope conflict, the ID of the existing standards that conflict" (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-response.json) — and the update response carries the same field, "If scope change conflicts with another configuration, the ID of the conflicting standards" (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-response.json). Notes: (a) `SCOPE_CONFLICT` is not a member of the published 92-code standard vocabulary (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json) and appears nowhere in the schema bundle, but it is not merely permitted-by-open-vocabulary either — the pinned task page prescribes it in the worked Scope Conflict error example and states the rule "Multiple standards cannot have overlapping scopes for the same country/channel/language combination" (repo=adcp ref=3.1.1 path=dist/docs/3.1.1/governance/content-standards/tasks/create_content_standards.mdx). Emission is legal in any case because `error.code` is deliberately open — "wire-typed `string` (not a closed enum) ... senders MAY emit codes outside that set" (repo=adcp ref=3.1.1 path=schemas/core/error.json). (b) Placement is ambiguous in the pin: after resolving the response `allOf` (version-envelope + protocol-envelope) and `oneOf`, the schema declares `conflicting_standards_id` at the **error-branch root**, sibling to `errors[]`, while the task page's example nests it inside `errors[0]` — and since core/error.json is `additionalProperties: true` the nested form is schema-valid too. A test should assert the schema-declared root position and tolerate the nested form rather than treat either as non-conformant. (c) It is ungraded: none of the ten steps in the content-standards storyboard attempts an overlapping-scope create (repo=adcp ref=3.1.1 path=specialisms/content-standards/index.yaml).

---

### BR-RULE-066: Content Standards Immutable Versioning
**Obligation ID** BR-RULE-066-01
**Layer** behavioral
**Invariant:** Updates create new versions. Partial fields supported. standards_id remains stable across versions.
**Scenario:**
```gherkin
Given an existing content standard with policy_text="v1 policy"
When update is called with policy_text="v2 policy"
Then a new version is created; previous version preserved; same standards_id returned
```
**Priority:** P2
**Grounded at 3.1.1:** Two of three clauses hold; "previous version preserved" is not observable in the pin. New-version-on-update is verbatim — the request is titled "Update Content Standards Request" and described "Request parameters for updating an existing content standards configuration. **Creates a new version.**", with `required: ["idempotency_key","standards_id"]` and everything else (`scope`, `policies`, `registry_policy_ids`, `calibration_exemplars`) optional, which grounds the partial-update clause at the top level (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-request.json). Stable identity likewise holds: the success branch of the response requires `["success","standards_id"]` with `standards_id` = "ID of the updated standards configuration" (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-response.json), and the storyboard's `standards_version_change` phase drives `update_content_standards` and then `calibrate_content` against the same `$context.content_standards_id` (repo=adcp ref=3.1.1 path=specialisms/content-standards/index.yaml). Corrections: (a) partial is top-level only — `policies`, when sent, "Replaces the existing policies array; use stable policy_ids to track policies across versions", so it is array-replace, not a field-level merge; (b) there is no read path to a prior version at 3.1.1 — the resource carries no version field (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json) and the read request takes only `standards_id` with no version selector (repo=adcp ref=3.1.1 path=schemas/content-standards/get-content-standards-request.json). What the storyboard actually grades is the opposite obligation: after the update, `calibrate_content` on previously-passing content must return `verdict: "fail"` — the current version must apply and must not be cached.

---

### BR-RULE-067: Content Standards Referential Integrity
**Obligation ID** BR-RULE-067-01
**Layer** behavioral
**Invariant:** Cannot delete standard referenced by active media buys. Unreferenced delete cascades versions and exemplars.
**Scenario:**
```gherkin
Given a content standard referenced by 2 active media buys
When delete is called
Then STANDARDS_IN_USE error is returned

Given a content standard with no active media buy references
When delete is called
Then the standard, all versions, and calibration exemplars are deleted
```
**Priority:** P2
**Grounded at 3.1.1:** 3.1.1 defines no delete surface for content standards at all, so both legs of this obligation grade our own production behavior rather than AdCP conformance. The content-standards schema directory holds 17 files — create/get/list/update request+response pairs plus `calibrate-content`, `validate-content-delivery`, `get-media-buy-artifacts`, `artifact.json`, `artifact-webhook-payload.json` and the resource itself (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json) — and there is no `delete-content-standards-*` schema; a bundle-wide filename search for "delete" returns only the property-list and collection-list delete tasks, so the spec does define delete tasks where it intends them (repo=adcp ref=3.1.1 path=schemas/property/delete-property-list-request.json). `STANDARDS_IN_USE` is not a member of the 92-code error vocabulary and does not appear anywhere in the bundle (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json). The graded contract confirms it: the content-standards storyboard's ten steps are get_capabilities, create_content_standards, list_content_standards, get_content_standards, update_content_standards, calibrate_content, calibrate_must_violation, update_stricter_standards, calibrate_after_policy_change and validate_content_delivery — no delete step (repo=adcp ref=3.1.1 path=specialisms/content-standards/index.yaml). There is also no versions or calibration-exemplar sub-resource with independent identity to cascade to — `calibration_exemplars` is an inline `{pass[], fail[]}` object on the standards resource. Referential-integrity-on-delete is therefore ours to specify, not AdCP's.

---

### BR-RULE-068: Content Standards List Filter Semantics
**Obligation ID** BR-RULE-068-01
**Layer** behavioral
**Invariant:** Within-dimension OR, cross-dimension AND. No filters returns all tenant standards.
**Scenario:**
```gherkin
Given filter channels=["display", "social"] and languages=["en"]
When list_content_standards is called
Then standards matching (display OR social) AND (en) are returned
```
**Priority:** P3
**Grounded at 3.1.1:** SPEC-SILENT on how `list_content_standards` filters combine. The request declares `channels`, `languages`, `countries` as three independent optional arrays (each `minItems: 1`; descriptions are only "Filter by channel" / "Filter by BCP 47 language tags" / "Filter by ISO 3166-1 alpha-2 country codes"; there is no `required` block and the `allOf` resolves to core/version-envelope alone, which contributes only adcp_version/adcp_major_version) — no within-dimension or cross-dimension combination rule is stated (repo=adcp ref=3.1.1 path=schemas/content-standards/list-content-standards-request.json). The response says only "Array of content standards configurations matching the filter criteria" (repo=adcp ref=3.1.1 path=schemas/content-standards/list-content-standards-response.json), and the one graded `list_content_standards` step passes no filters at all, asserting only response_schema plus the context echo (repo=adcp ref=3.1.1 path=specialisms/content-standards/index.yaml); the other pinned storyboard touching this tool grades cursor/has_more only (repo=adcp ref=3.1.1 path=universal/content-standards-pagination-integrity.yaml). Do not derive the rule from the record: the ALL/ANY semantics in the pin belong to a standard's own scope fields — `countries_all` "Standards apply in ALL listed countries (AND logic)", `channels_any` and `languages_any` "(OR logic)" (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json) — so a blanket "within-dimension OR" is not derivable, since countries is AND there. "All tenant standards" is also untranslatable: 3.1.1 scopes by `account`, never by tenant. This obligation grades our production filter behavior, not AdCP conformance.

---

### BR-RULE-069: Calibration Exemplar Polymorphism
**Obligation ID** BR-RULE-069-01
**Layer** schema
**Invariant:** Exemplars accept URL references or artifact objects (oneOf). Both may coexist. URL references resolved to artifacts on ingest.
**Scenario:**
```gherkin
Given calibration_exemplars.pass contains both URL references and artifact objects
When create_content_standards processes
Then both formats are accepted in the same collection
```
**Priority:** P3
**Grounded at 3.1.1:** Partly true — the oneOf and the coexistence hold on the WRITE path only. `calibration_exemplars.pass`/`.fail` items are a per-item `oneOf` of [URL-reference object with `type` const "url" plus required `value` (format uri) and optional `language`] and [full artifact `$ref` content-standards/artifact.json], so a single array may legitimately mix both forms (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-request.json; identical shape on update, repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-request.json). What is false is the unqualified scope: on the stored resource the exemplar items are artifact objects ONLY — a bare `$ref` to artifact.json with no oneOf branch (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json), and that record is exactly what get_content_standards returns (success branch is allOf(content-standards.json), repo=adcp ref=3.1.1 path=schemas/content-standards/get-content-standards-response.json). Note a URL reference is not merely "an artifact with a url field": artifact.json requires property_rid, artifact_id and assets (repo=adcp ref=3.1.1 path=schemas/content-standards/artifact.json). The third clause, "URL references resolved to artifacts on ingest", is stated nowhere as a normative requirement — the write-vs-read shape asymmetry is consistent with it but does not mandate it, so that clause grades our production ingest behavior.

---

### BR-RULE-070: Property List Authentication
**Obligation ID** BR-RULE-070-01
**Layer** behavioral
**Invariant:** All property list CRUD operations require authenticated principal. No tenant = rejected.
**Scenario:**
```gherkin
Given no valid authentication credentials
When any property list operation is called
Then LIST_ACCESS_DENIED is returned

Given valid auth but tenant cannot be resolved
When create_property_list is called
Then the request is rejected with tenant error
```
**Priority:** P1
**Grounded at 3.1.1:** The auth-required half holds; the error code is wrong. Property-list CRUD is state-modifying and account-scoped (`x-mutates-state: true` on create, repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json), and the pinned security baseline grades exactly this: "Agent returned 200 or 5xx on an unauthenticated protected call — it MUST reject with 401 (and send WWW-Authenticate) or 403" (repo=adcp ref=3.1.1 path=universal/security.yaml). `LIST_ACCESS_DENIED` is NOT the pinned code for that rejection: it is absent from the 92-entry standard vocabulary, which instead mandates `AUTH_MISSING` — "Sellers MUST return this code when no `Authorization` header was included in the request" — and `AUTH_INVALID` when credentials were presented and rejected (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json). LIST_ACCESS_DENIED occurs exactly once in the whole pin, inside a per-property record described as "Error information for a property that could not be evaluated", which no other schema in the bundle `$ref`s (repo=adcp ref=3.1.1 path=schemas/property/property-error.json). The "no tenant" half maps to accounts, not tenants: with `account` omitted, "if exactly one account is accessible to the authenticated caller, the seller may assign the list to that account; otherwise it MUST return an account-required or ambiguous-account error" (repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json), and the vocabulary carries ACCOUNT_AMBIGUOUS and ACCOUNT_NOT_FOUND for it (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json).

---

### BR-RULE-071: Property List Tenant Isolation
**Obligation ID** BR-RULE-071-01
**Layer** behavioral
**Invariant:** Property lists scoped to auth-derived tenant. Cross-tenant access returns NOT_FOUND (not ACCESS_DENIED) to prevent enumeration.
**Scenario:**
```gherkin
Given list_id "list_1" belongs to tenant_A
When tenant_B requests get_property_list("list_1")
Then LIST_NOT_FOUND is returned (prevents information disclosure)
```
**Priority:** P0
**Grounded at 3.1.1:** The anti-enumeration rule holds; the code name does not. 3.1.1 mandates a uniform response and names property lists explicitly: REFERENCE_NOT_FOUND is the "Generic fallback for a referenced identifier, grant, session, or other resource that does not exist or is not accessible by the caller. Use when no resource-specific not-found code applies (e.g., property lists, content standards, ...). Typed parameters that lack a dedicated standard code MUST also use REFERENCE_NOT_FOUND rather than minting a custom *_NOT_FOUND code", and "sellers MUST return the same response for 'exists but the caller lacks access' as for 'does not exist' across every observable channel" — code/message/field/details, HTTP status, A2A task.status.state, MCP isError, headers, side effects, and observability (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json). So answering a cross-account `list_id` with not-found is correct at 3.1.1, but the emitted code MUST be REFERENCE_NOT_FOUND; `LIST_NOT_FOUND` is not in the standard vocabulary and appears only in the unreferenced per-property record (repo=adcp ref=3.1.1 path=schemas/property/property-error.json). One further correction of vocabulary: the pin scopes lists by `account` — "Account that owns the list" — not by tenant (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-request.json).

---

### BR-RULE-072: Property Source Validation
**Obligation ID** BR-RULE-072-01
**Layer** behavioral
**Invariant:** base_properties uses discriminated union (publisher_tags/publisher_ids/identifiers). Non-empty selection arrays required. Omitted base_properties = entire catalog.
**Scenario:**
```gherkin
Given base_properties with selection_type="publisher_tags" and publisher_domain="example.com" and tags=["sports"]
When create_property_list processes
Then the selection is valid

Given base_properties omitted
When create_property_list processes
Then the system resolves against the agent's entire property catalog
```
**Priority:** P2
**Grounded at 3.1.1:** Holds in full. `base_properties` items resolve to a discriminated union — `"discriminator": {"propertyName": "selection_type"}` over three `oneOf` branches: Publisher Tags Source (required selection_type + publisher_domain + tags), Publisher Property IDs Source (required selection_type + publisher_domain + property_ids), and Direct Identifiers Source (required selection_type + identifiers) — each branch `additionalProperties: false` and each selection array `minItems: 1`, so empty selection arrays are rejected (repo=adcp ref=3.1.1 path=schemas/property/base-property-source.json). The scenario's publisher_tags example is valid: `tags` items are property tags matching `^[a-z0-9_]+$`, with "sports" listed among the schema's own examples (repo=adcp ref=3.1.1 path=schemas/core/property-tag.json). Omission is defined exactly as claimed — base_properties is "Array of property sources to evaluate. Each entry is a discriminated union: publisher_tags (publisher_domain + tags), publisher_ids (publisher_domain + property_ids), or identifiers (direct identifiers). If omitted, queries the agent's entire property database", and the array itself is `minItems: 1` when present (repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json). The pinned storyboard exercises the identifiers branch on create (repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml).

---

### BR-RULE-073: Property List Filter Requirements
**Obligation ID** BR-RULE-073-01
**Layer** behavioral
**Invariant:** filters object requires both countries_all (AND) and channels_any (OR) as non-empty arrays. Evaluated at resolution time.
**Scenario:**
```gherkin
Given filters with countries_all=["US", "UK"] and channels_any=["display"]
When property list is resolved
Then only properties with data in US AND UK that support display are included
```
**Priority:** P2
**Grounded at 3.1.1:** The AND/OR semantics hold; the requiredness is false. property-list-filters.json is a plain object with no `allOf`/`oneOf`/`$ref` at its root and declares NO `required` block, and both fields are documented as optional: `countries_all` — "Property must have feature data for ALL listed countries (ISO codes). When omitted, no country restriction is applied." — and `channels_any` — "Property must support ANY of the listed channels. When omitted, no channel restriction is applied." So the AND (countries_all) / OR (channels_any) reading and the non-empty constraint when present (`minItems: 1` on both) hold, but a filters object carrying only one of them, neither of them, or only `property_types` / `feature_requirements` / `exclude_identifiers` is fully valid at 3.1.1 (repo=adcp ref=3.1.1 path=schemas/property/property-list-filters.json). "Evaluated at resolution time" holds: filters are "Dynamic filters to apply when resolving the list" (repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json) and get_property_list gates them behind `resolve` — "Whether to apply filters and return resolved identifiers (default: true)" (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-request.json). No pinned storyboard grades filter evaluation; the graded list step passes only `name_contains` (repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml).

---

### BR-RULE-074: Auth Token One-Shot Delivery
**Obligation ID** BR-RULE-074-01
**Layer** behavioral
**Invariant:** auth_token returned exactly once in create response. Not in any subsequent response. No recovery mechanism.
**Scenario:**
```gherkin
Given create_property_list succeeds
When the response is returned
Then it includes auth_token

Given get_property_list is called for the same list
When the response is returned
Then auth_token is NOT included
```
**Priority:** P1
**Grounded at 3.1.1:** Holds. create_property_list is the only response carrying the token: `auth_token` sits in `required: ["list", "auth_token"]` and is described as "Token that can be shared with sellers to authorize fetching this list. Store this - it is only returned at creation time." (repo=adcp ref=3.1.1 path=schemas/property/create-property-list-response.json). The absence claim was checked with composition resolved: get/update/delete responses are allOf(core/version-envelope, core/protocol-envelope) plus their own properties, and neither envelope declares auth_token (repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json, repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json), nor do the task bodies (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-response.json, repo=adcp ref=3.1.1 path=schemas/property/update-property-list-response.json, repo=adcp ref=3.1.1 path=schemas/property/delete-property-list-response.json), nor the returned `list` object, which is `additionalProperties: false` and has no auth_token (repo=adcp ref=3.1.1 path=schemas/property/property-list.json). Two precisions: those response roots are `additionalProperties: true`, so the once-only rule rides on the normative create-response description rather than being mechanically enforced by the read schemas; and "no recovery mechanism" is not stated anywhere — it is supported only by the absence of any reissue/rotate task across the pinned property tool surface (create/get/list/update/delete/validate).

---

### BR-RULE-075: Update Replacement Semantics
**Obligation ID** BR-RULE-075-01
**Layer** behavioral
**Invariant:** Update uses full replacement per field. webhook_url only in update (not create). Empty string removes webhook.
**Scenario:**
```gherkin
Given update_property_list with base_properties=[new_set]
When the update processes
Then base_properties completely replaces existing (not merged)

Given update_property_list with webhook_url=""
When the update processes
Then the previously set webhook URL is removed
```
**Priority:** P2
**Grounded at 3.1.1:** Holds on all three clauses. Full replacement per field is explicit: base_properties is "Complete replacement for the base properties list (not a patch)" and filters is "Complete replacement for the filters (not a patch)"; `webhook_url` is declared only on update — "Update the webhook URL for list change notifications (set to empty string to remove)" (repo=adcp ref=3.1.1 path=schemas/property/update-property-list-request.json). Create declares no webhook_url, verified with its `allOf` resolved to core/version-envelope, which contributes only adcp_version/adcp_major_version (repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json, repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json); the field nonetheless exists on the returned resource as "URL to receive notifications when the resolved list changes" (repo=adcp ref=3.1.1 path=schemas/property/property-list.json). Two precisions: the create request is `additionalProperties: true`, so a seller that accepted webhook_url at create time would be undeclared rather than schema-invalid; and update's webhook_url carries `format: "uri"`, so the empty-string removal sentinel is prose-normative but does not satisfy the declared format. The graded update step replaces base_properties and never exercises webhook_url (repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml).

---

### BR-RULE-076: Property List Referential Integrity
**Obligation ID** BR-RULE-076-01
**Layer** behavioral
**Invariant:** get/update/delete require existing list_id. Missing = LIST_NOT_FOUND. Delete blocked by active media buys (LIST_IN_USE).
**Scenario:**
```gherkin
Given list_id "nonexistent" does not exist
When get_property_list is called
Then LIST_NOT_FOUND is returned with the provided list_id

Given list_id "list_1" is referenced by an active media buy
When delete_property_list is called
Then LIST_IN_USE is returned; list is not deleted
```
**Priority:** P1
**Grounded at 3.1.1:** The list_id requirement holds; both error codes are wrong and the delete-blocking rule is spec-silent. Required list_id holds on all three: get `required: ["list_id"]` (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-request.json), update `required: ["idempotency_key", "list_id"]` (repo=adcp ref=3.1.1 path=schemas/property/update-property-list-request.json), delete `required: ["idempotency_key", "list_id"]` (repo=adcp ref=3.1.1 path=schemas/property/delete-property-list-request.json). A nonexistent list_id resolves to REFERENCE_NOT_FOUND, not LIST_NOT_FOUND — "Use when no resource-specific not-found code applies (e.g., property lists ...) ... MUST also use REFERENCE_NOT_FOUND rather than minting a custom *_NOT_FOUND code" — and the same entry's uniform-response MUST forbids distinguishing nonexistent from inaccessible and requires the message be generic, which constrains how much of the requested list_id may be echoed back (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json). `LIST_IN_USE` does not exist anywhere in the pin: zero hits across the schema bundle and the compliance tree. Delete declares no referential precondition, its response is simply `required: ["deleted", "list_id"]` (repo=adcp ref=3.1.1 path=schemas/property/delete-property-list-response.json), and the graded delete step asserts only response_schema plus the context echo (repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml). The active-media-buy block therefore grades our own production behavior.

---

### BR-RULE-077: Property List Resolution and Pagination
**Obligation ID** BR-RULE-077-01
**Layer** behavioral
**Invariant:** resolve=true (default) resolves filters against current catalog. max_results 1-10000, default 1000. Cursor-based pagination.
**Scenario:**
```gherkin
Given resolve=true and max_results=100
When get_property_list is called
Then up to 100 resolved identifiers are returned with a cursor for next page

Given resolve=false
When get_property_list is called
Then identifiers are not returned; pagination params have no effect
```
**Priority:** P2
**Grounded at 3.1.1:** The invariant holds exactly as written. get_property_list declares `resolve` — "Whether to apply filters and return resolved identifiers (default: true)" — and its own inline pagination object (deliberately not core/pagination-request.json, "Uses higher limits than standard pagination because property lists can contain tens of thousands of identifiers") with max_results `minimum: 1`, `maximum: 10000`, `default: 1000`, plus `cursor` "Opaque cursor from a previous response to fetch the next page" (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-request.json); the standard pagination block it overrides caps at 100 with default 50 (repo=adcp ref=3.1.1 path=schemas/core/pagination-request.json). The resolve=false branch is supported with composition resolved: the response is allOf(core/version-envelope, core/protocol-envelope) plus body fields, only `list` is required, and `identifiers` is described as "Resolved identifiers that passed filters (if resolve=true)" (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-response.json). One scenario clause is unstated rather than false: "pagination params have no effect" under resolve=false appears nowhere in the pin — it is a reasonable consequence, not a cited requirement. Note also that cursor/has_more integrity is graded only for list_property_lists, not get_property_list (repo=adcp ref=3.1.1 path=universal/property-lists-pagination-integrity.yaml).

---

### BR-RULE-078: Property List Filtering
**Obligation ID** BR-RULE-078-01
**Layer** behavioral
**Invariant:** list-property-lists supports optional filtering by principal (exact) and name (case-insensitive substring). Unfiltered returns all tenant lists.
**Scenario:**
```gherkin
Given name_contains="sports"
When list_property_lists is called
Then only lists whose name contains "sports" (case-insensitive) are returned

Given no filters
When list_property_lists is called
Then all property lists for the tenant are returned
```
**Priority:** P3
**Grounded at 3.1.1:** Partly grounded. `list_property_lists` is a real 3.1.1 task and its request schema (allOf resolves to `core/version-envelope.json` only, so the listed properties are the complete filter surface) defines exactly two filters: `name_contains` — "Filter to lists whose name contains this string" — and `account` (a `core/account-ref.json`), whose description states "Filter to lists owned by this account. When omitted, returns lists across all accounts accessible to the authenticated agent" (repo=adcp ref=3.1.1 path=schemas/property/list-property-lists-request.json; repo=adcp ref=3.1.1 path=schemas/core/account-ref.json). So the substring-name filter and the "unfiltered returns everything the caller may see" half of the invariant are grounded. Two parts are NOT: (1) there is no `principal` filter at 3.1.1 — the ownership/tenancy dimension of a property list is `account` (and `brand`), and `property/property-list.json` (`additionalProperties: false`, no allOf/oneOf) carries no principal field at all, so "filtering by principal (exact)" is our own extension, permitted only because the request schema sets `additionalProperties: true`, not a spec obligation (repo=adcp ref=3.1.1 path=schemas/property/property-list.json); (2) case-insensitivity of `name_contains` is not specified for property lists — 3.1.1 states case-insensitivity explicitly where it means it (`core/creative-filters.json`: "Filter by creative names containing this text (case-insensitive)") and says nothing of the kind here (repo=adcp ref=3.1.1 path=schemas/core/creative-filters.json). The pinned storyboard exercises the filter with an exact-case value (`name_contains: "Acme Outdoor"`, step `list_property_lists`, comply_scenario `property_list_filters`) but grades only `response_schema` plus the `context.correlation_id` echo — filter semantics are ungraded (repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml). The only other pinned `list_property_lists` storyboard grades cursor/`has_more` pagination integrity, not filtering (repo=adcp ref=3.1.1 path=universal/property-lists-pagination-integrity.yaml). Net: keep the name-substring and unfiltered clauses; restate the ownership filter as `account`, and treat case-insensitivity as our production choice.

---

### BR-RULE-079: Enrichment Service Fail-Open with Exception Narrowing
**Obligation ID** BR-RULE-079-01
**Layer** behavioral
**Origin** product decision (GitHub #1093)
**Invariant:** Optional enrichment services (dynamic variants, dynamic pricing, AI ranking, adapter annotation) degrade gracefully on expected service failures (ImportError, RuntimeError, OSError). Programming errors (TypeError, AttributeError, KeyError) must propagate — they indicate bugs, not transient failures. Core data path services (product conversion, property list resolution) always fail closed.
**Scenario:**
```gherkin
Given the dynamic variant service raises RuntimeError (network failure)
When _get_products_impl processes the request
Then static products are returned without dynamic variants
And a warning is logged

Given the dynamic variant service raises TypeError (programming bug)
When _get_products_impl processes the request
Then the TypeError propagates as an unhandled exception

Given product conversion raises ValueError (data corruption)
When _get_products_impl processes the request
Then the ValueError propagates (core path — never fail open)
```
**Priority:** P1
**Grounded at 3.1.1:** Partly grounded — silent on the mechanism, not on the consequence. The invariant is about internal Python exception taxonomy inside `_get_products_impl` (which host-language exception classes are swallowed with a log warning versus propagated, and which internal services count as "enrichment" versus "core data path"). On that, 3.1.1 says nothing: no pinned artifact classifies agent-internal subsystems or exception types, and no `get_products` storyboard in the pinned tree exercises a failed-enrichment path (`grep -rln 'task: get_products'` matches 97 files across domains/, protocols/, universal/, specialisms/; none exercise one, and the token `incomplete` appears in no storyboard at all — its only compliance-tree hits are request-/webhook-signing test vectors). What is NOT silent is the buyer-visible consequence of degrading. `get-products-response.json` (allOf resolves to `core/version-envelope.json` + `core/protocol-envelope.json`, plus an if/then/else conditioning required fields on `unchanged`/`status`) defines `incomplete[]` — "Declares what the seller could not finish within the buyer's time_budget or due to internal limits ... Absent when the response is fully complete" — with scopes `products|pricing|forecast|proposals|wholesale_feed`, and `errors[]` — "Task-specific errors and warnings" (repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-response.json). The pinned prose makes the trigger explicit: "When the seller cannot complete all work within the `time_budget` (or due to its own internal limits), the response includes `incomplete` — an array declaring what is missing," and names `pricing` ("products returned but pricing is absent or unconfirmed") and `forecast` ("products returned but forecast data is absent") as the scopes for exactly this case (repo=adcp ref=3.1.1 path=dist/docs/3.1.1/media-buy/task-reference/get_products.mdx). Neither surface is schema-required on the standard success branch (which requires only `products` and `cache_scope`), so the duty is normative prose rather than a schema constraint, and it is ungraded — no storyboard asserts on `incomplete[]`. Net: the exception-taxonomy half of this obligation grades our own production behavior (GitHub #1093) and stays ungrounded; but the "silently swallow and return a degraded response" half is NOT free at 3.1.1 — when an enrichment scope is dropped for internal reasons, the pin says the response declares it via `incomplete[]` (scope `pricing`/`forecast`), with `errors[]` available for advisory detail.
**Cross-references:** UC-001-MAIN-41, UC-001-MAIN-42, UC-001-MAIN-32, UC-001-MAIN-43, UC-001-EXT-A-03

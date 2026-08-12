# Constraints -- Test Obligations — AdCP 3.1.1

## Spec grounding — AdCP 3.1.1

Grounded against the version this repo pins, resolved from
`docs/adcp-spec-version.md` (never hardcoded here). Citations use the form
`repo=adcp ref=3.1.1 path=<compliance-tree path>`.

This section replaces a "3.6 Upgrade Impact" table that assessed the
`adcp 3.2.0 -> 3.6.0` SDK upgrade. That framing was two spec lines stale, and
some of its claims are false at the pin — corrected below, with what was checked.

| Constraint area | Verified at 3.1.1 | Related |
|---|---|---|
| `core/product.json` | HOLDS. `additionalProperties: true`, and all 7 named fields exist: channels, catalog_match, catalog_types, conversion_tracking, data_provider_signals, forecast, signal_targeting_allowed | salesagent-qo8a (FIXED) |
| `core/pricing-option.json` | HOLDS, with a shape correction: 9 pricing models, but expressed as a `oneOf` over `pricing-options/*.json` discriminated on `pricing_model` — cpm, vcpm, cpc, cpcv, cpv, cpp, cpa, flat_rate, time. It has no `properties` of its own; a constraint asserting a field "on pricing-option" must name the branch | salesagent-mq3n |
| `core/media-buy.json` | **CORRECTED — 2 of 5 claimed fields exist.** `creative_deadline` and `ext` are present; `account_id`, `proposal_id` and `buyer_campaign_ref` are NOT. The entity carries `account` (an `account.json` ref), not `account_id`. Its 17 properties are the complete set — the `allOf` is a conditional (`if`/`then` on `confirmed_at`) and contributes no fields | salesagent-7gnv |
| `media-buy/create-media-buy-request.json` | **CORRECTED.** `proposal_id`, `brand`, `artifact_webhook` and `packages` exist; `account_id` does NOT — the field is `account`. Required at the pin: account, brand, end_time, idempotency_key, start_time. Note `account` is REQUIRED here while our implementation treats it as temporarily optional | salesagent-7gnv |
| `media-buy/create-media-buy-response.json` | **CORRECTED — the claim is unverifiable as stated.** The response is composed: `allOf` of `core/version-envelope.json` + `core/protocol-envelope.json`, then a `oneOf` over success/failure variants. `warnings`/`ext` are not top-level properties, so a constraint must name the variant it means | -- |
| `media-buy/update-media-buy-request.json` | **CORRECTED.** `ext` exists; `account_id` and `buyer_campaign_ref` do NOT. Required at the pin: account, idempotency_key, media_buy_id | salesagent-7gnv |
| per-status async responses | HOLDS, and there are more than the old row implies: 15 `*-async-response-{submitted,working,input-required}.json` under `media-buy/` | -- |
| account_* | HOLDS. 10 schemas under `account/` | -- |
| content_standards_* | HOLDS. 17 schemas under `content-standards/` | -- |
| property_list_* | HOLDS. 24 schemas under `property/` | -- |
| signal_* | HOLDS. 6 schemas under `signals/` | -- |
| capabilities_* | HOLDS. `protocol/get-adcp-capabilities-{request,response}.json` both exist | -- |
| auth/principal_id | Unchanged by this audit — an auth convention of ours, not a pinned schema | -- |

**One finding worth carrying out of this table.** Every request AND response
schema composes `core/version-envelope.json` via `allOf`, so `adcp_version` /
`adcp_major_version` are part of the shape on both directions of the wire. Our
MCP tools reject those fields today — see salesagent-g6m2.6 / GH #1512, which
measured 31 graded conformance checks failing on exactly that.

**Every one of the 134 per-constraint verdicts below has been individually
re-decided against the pin** and carries `**Grounded at 3.1.1:**` with the paths
it was checked against. Each was traced to the pinned tree, schema bundle or
spec prose, then adversarially re-verified — that second pass rejected 38 of the
202 verdicts across this file and `business-rules.md`, mostly for citing a real
file that did not support the claim. Every citation path was then resolved
mechanically on disk (1423 references, 0 unresolvable, 0 pointing at a version
other than the pin).

`SPEC-SILENT` is a legitimate and common verdict here: many of these constraints
are our own validation rules with no counterpart at 3.1.1. Where a verdict says
so, it grades OUR behavior, not AdCP conformance — and it names what was
searched to establish the silence.

## Constraints

### product: Product Entity Schema
**Obligation ID** CONSTR-PRODUCT-01
**Layer** schema
**Requirement:** Product must have required fields (product_id, name, description, publisher_properties, format_ids, delivery_type, delivery_measurement, pricing_options). v3 changes `additional_properties` from false to true. New optional fields: channels, catalog_match, catalog_types, conversion_tracking, data_provider_signals, forecast, signal_targeting_allowed.
**Scenario:**
```gherkin
Given a product with all required fields populated
When serialized to AdCP schema
Then all required fields are present and extra fields are allowed

Given a product with new v3 field channels=["display", "olv"]
When serialized to AdCP schema
Then channels array is included with uniqueItems enforcement
```
**Priority:** P0
**Grounded at 3.1.1:** HOLDS. `repo=adcp ref=3.1.1 path=core/product.json` has `additionalProperties: true` and carries all 7 named optional fields (channels, catalog_match, catalog_types, conversion_tracking, data_provider_signals, forecast, signal_targeting_allowed). Verified field-by-field against the pinned schema.

---

### pricing-option: Pricing Option Entity Schema
**Obligation ID** CONSTR-PRICING-OPTION-01
**Layer** schema
**Requirement:** PricingOption requires pricing_model (enum of 9 models), currency (ISO 4217), and exactly one of fixed_price/floor_price (XOR). v3 adds model-specific sub-schemas under /schemas/pricing/. delivery field is now an object reference, not an integer.
**Scenario:**
```gherkin
Given a pricing option with pricing_model="cpm" and fixed_price=5.0
When validated against the v3 schema
Then the option is valid with the cpm sub-schema applied

Given a pricing option with delivery field as integer
When processed in v3
Then the system must handle the delivery field as an object reference, not integer PK
```
**Priority:** P0
**Grounded at 3.1.1:** HOLDS with a shape correction. `repo=adcp ref=3.1.1 path=core/pricing-option.json` is a `oneOf` over 9 branch schemas discriminated on `pricing_model` (cpm, vcpm, cpc, cpcv, cpv, cpp, cpa, flat_rate, time) — it declares no `properties` itself, so an obligation naming a field "on pricing-option" must name the branch. The delivery-lookup defect this cites (salesagent-mq3n) is ours, not the spec's.

---

### media-buy: Media Buy Entity Schema
**Obligation ID** CONSTR-MEDIA-BUY-01
**Layer** schema
**Requirement:** MediaBuy requires media_buy_id, buyer_ref, status. v3 adds: account_id, buyer_campaign_ref, creative_deadline, ext. additional_properties: true.
**Scenario:**
```gherkin
Given a media buy with buyer_campaign_ref="CAMP-2024-Q1"
When serialized to AdCP schema
Then buyer_campaign_ref is preserved in the response

Given a media buy with ext={"custom_field": "value"}
When serialized to AdCP schema
Then ext object is preserved unchanged
```
**Priority:** P0
**Grounded at 3.1.1:** PARTLY FALSE as previously written. `repo=adcp ref=3.1.1 path=core/media-buy.json` carries `creative_deadline` and `ext`, but NOT `account_id`, `proposal_id` or `buyer_campaign_ref` — the entity has `account` (an account.json ref). Its 17 properties are the complete set: the schema's `allOf` is a conditional on `confirmed_at` and contributes no fields. salesagent-7gnv stands for creative_deadline and ext; the buyer_campaign_ref half of it does not describe this entity at the pin.

---

### package: Package Entity Schema
**Obligation ID** CONSTR-PACKAGE-01
**Layer** schema
**Requirement:** Package requires product_id, budget, pricing_option. v3 changes: additional_properties: true, delivery is object reference. Targeting overlay is optional.
**Scenario:**
```gherkin
Given a package with all required fields and a targeting_overlay
When validated
Then the package is valid

Given a package in update mode with product_id in payload
When update schema validates
Then product_id is rejected (immutable field, not in update schema)
```
**Priority:** P0
**Grounded at 3.1.1:** FALSE as previously written. `repo=adcp ref=3.1.1 path=core/package.json` has no `delivery` field at all — there is nothing here whose type could have changed. The package carries `pricing_option_id` (a reference to the product's chosen pricing option), 29 properties in total, `additionalProperties: true`, and `package_id` as its only required field.

---

### targeting: Targeting Schema
**Obligation ID** CONSTR-TARGETING-01
**Layer** schema
**Requirement:** Targeting object supports geo_countries, geo_regions, geo_dma, geo_zip, and custom dimensions. v3: additional_properties: true.
**Scenario:**
```gherkin
Given targeting with geo_countries include=["US"] and exclude=["US"]
When validated
Then rejected (same value in include and exclude per BR-RULE-014)
```
**Priority:** P1
**Grounded at 3.1.1:** Partly true. The `additionalProperties: true` clause holds — `core/targeting.json` ends with `"additionalProperties": true`, so custom/unknown dimensions are accepted, not rejected (repo=adcp ref=3.1.1 path=schemas/core/targeting.json). `geo_countries` (ISO 3166-1 alpha-2, `pattern: ^[A-Z]{2}$`) and `geo_regions` (ISO 3166-2, `pattern: ^[A-Z]{2}-[A-Z0-9]{1,3}$`) exist as named. But `geo_dma` and `geo_zip` DO NOT EXIST at 3.1.1 — the schema declares `geo_metros` (array of `{system, values}` where `system` $refs `enums/metro-system.json`, e.g. `nielsen_dma`) and `geo_postal_areas` (items $ref `core/postal-area.json`) instead (repo=adcp ref=3.1.1 path=schemas/core/targeting.json, repo=adcp ref=3.1.1 path=schemas/enums/metro-system.json, repo=adcp ref=3.1.1 path=schemas/core/postal-area.json). The scenario is also mis-shaped: 3.1.1 does not model include/exclude as sub-keys of one field — exclusion is a separate sibling array (`geo_countries_exclude`, `geo_regions_exclude`, `geo_metros_exclude`, `geo_postal_areas_exclude`), and NOTHING in the pinned line forbids the same value appearing in both the include and exclude array. `targeting.json` has no `oneOf`/`allOf`/`not` at its root (flat `properties` + `additionalProperties: true`, resolved before asserting absence) and no compliance storyboard grades geo include/exclude overlap. The overlap-rejection half of this obligation grades our production behavior, not AdCP conformance.

---

### targeting_overlay: Targeting Overlay Validation
**Obligation ID** CONSTR-TARGETING-OVERLAY-01
**Layer** behavioral
**Requirement:** Targeting overlay applied on packages validates: unknown fields rejected, managed-only dimensions rejected, geo overlap rejected. Empty/absent is valid.
**Scenario:**
```gherkin
Given a targeting overlay with unknown field "custom_xyz"
When validated
Then the overlay is rejected with unknown field error

Given an empty targeting overlay {}
When validated
Then the overlay passes validation
```
**Priority:** P1
**Grounded at 3.1.1:** The headline clause is FALSE and the tail clause HOLDS. "Unknown fields rejected" contradicts the pin: `targeting_overlay` on a package is `{"$ref": "/schemas/3.1.1/core/targeting.json"}` (repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json), and `core/targeting.json` closes with `"additionalProperties": true` — an unknown field such as `custom_xyz` VALIDATES at 3.1.1 rather than being rejected (repo=adcp ref=3.1.1 path=schemas/core/targeting.json). The carrying schema is permissive too: `package-request.json` itself declares `"additionalProperties": true`. "Empty/absent is valid" HOLDS: `core/targeting.json` declares no `required` array, and `targeting_overlay` is absent from `package-request.json`'s `"required": ["product_id", "budget", "pricing_option_id"]`, so both `{}` and omission validate (repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json). Both absence claims were made only after resolving `package-request.json`'s `allOf` (single member, `core/version-envelope.json`, which contributes only `adcp_version`/`adcp_major_version`) and its root-level `not` (`{"required": ["capability_ids"]}`) and `dependencies` (`{"params": ["format_kind"]}`), none of which constrain `targeting_overlay` (repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json). The "managed-only dimensions rejected" and "geo overlap rejected" clauses are SPEC-SILENT — no schema constraint and no storyboard grades either. Note that `targeting_overlay` IS graded at 3.1.1, but only for round-trip persistence of list and signal references, not for dimension admissibility or geo overlap: `inventory_list_targeting.yaml` asserts `field_value` on `media_buys[0].packages[0].targeting_overlay.property_list.list_id` and `.collection_list.list_id` after both create and update (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/inventory_list_targeting.yaml), and `product_signal_targeting.yaml` asserts `field_value` on `...targeting_overlay.signal_targeting_groups.operator` and `...groups[0].signals[0].pricing_option_id` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/product_signal_targeting.yaml); the remaining three (`audience_buy_flow`, `inventory_list_no_match`, `frequency_cap_enforcement`) carry `targeting_overlay` as sample-request input with zero `targeting_overlay`-pathed validations (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/frequency_cap_enforcement.yaml). A compliance-tree scan returns zero hits for `geo_countries`, `geo_metros`, and `geo_postal`, and the five `overlap` hits are unrelated senses (rolling reporting rows, duplicate event_source_ids, storyboard-schema prose). Those two clauses therefore grade our production behavior.

---

### create-media-buy-request: Create Media Buy Request Schema
**Obligation ID** CONSTR-CREATE-MEDIA-BUY-REQUEST-01
**Layer** behavioral
**Requirement:** Required: buyer_ref, brand, start_time, end_time. v3: packages no longer unconditionally required (conditional on proposal_id). New fields: account_id, proposal_id, artifact_webhook. brand is now BrandReference object.
**Scenario:**
```gherkin
Given a create request with proposal_id and total_budget but no packages
When validated against v3 schema
Then the request is valid (proposal mode)

Given a create request without buyer_ref
When validated
Then the request is rejected (required field)

Given a create request with brand as a BrandReference object
When processed
Then brand is validated as BrandReference, not plain string
```
**Priority:** P0
**Grounded at 3.1.1:** Three of five claims hold; the required-field list is wrong. `create-media-buy-request.json` declares `"required": ["idempotency_key", "account", "brand", "start_time", "end_time"]` — `buyer_ref` is NOT a property of the request at all, and `idempotency_key` + `account` (both required) are missing from the obligation (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json). Top-level `buyer_ref` is explicitly retired for v3 correlation: `package-request.json` says "Do not use deprecated top-level buyer_ref for v3 correlation", directing per-line correlation into `context.buyer_ref` instead (repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json), and the only compliance fixture carrying `buyer_ref` places it under `packages[].context` as a legacy-compat handle (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/package_correlation_legacy_fallback.yaml). So the scenario "a create request without buyer_ref → rejected" is FALSE at 3.1.1. HOLDS: `packages` is no longer unconditionally required (absent from `required[]`; the description states "One of packages or proposal_id must be provided" but the only machine constraint is `"dependencies": {"proposal_id": ["total_budget"]}` — proposal mode with `proposal_id` + `total_budget` and no `packages` validates, and is graded end-to-end where `create_media_buy` sends `proposal_id: "$context.proposal_id"` + `total_budget: {amount: 50000, currency: USD}` with no packages array, repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/proposal_finalize.yaml). HOLDS: `proposal_id` and `artifact_webhook` are new properties. HOLDS: `brand` is a BrandReference object — `{"$ref": "/schemas/3.1.1/core/brand-ref.json"}`, an object with `"required": ["domain"]`, not a plain string (repo=adcp ref=3.1.1 path=schemas/core/brand-ref.json). CORRECTED: there is no top-level `account_id`; the new field is `account`, a required `AccountRef` that is a `oneOf` over `{account_id}` XOR `{brand, operator, sandbox?}` (repo=adcp ref=3.1.1 path=schemas/core/account-ref.json). All absence claims were made after resolving the request's single `allOf` member `core/version-envelope.json`, which contributes only `adcp_version`/`adcp_major_version` (repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json).

---

### create-media-buy-response: Create Media Buy Response Schema
**Obligation ID** CONSTR-CREATE-MEDIA-BUY-RESPONSE-01
**Layer** behavioral
**Requirement:** Atomic: success variant (media_buy_id, buyer_ref, packages, status) OR error variant (errors[]). v3 adds: warnings, ext to success variant.
**Scenario:**
```gherkin
Given a successful creation with warnings
When the response is assembled
Then both success fields and warnings are present, no errors field
```
**Priority:** P0
**Grounded at 3.1.1:** Atomicity holds but the variant count, the success field list, and `warnings` are all wrong. The response is `allOf(core/version-envelope.json, core/protocol-envelope.json)` plus a `oneOf` over THREE arms, not two: `CreateMediaBuySuccess`, `CreateMediaBuyError`, and `CreateMediaBuySubmitted` (`status: "submitted"` + `task_id`, where "media_buy_id and packages land on the task's completion artifact, not this response") (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-response.json). Atomicity HOLDS: the success arm carries `"not": {"required": ["errors"]}` and the error arm carries `"not": {"anyOf": [...media_buy_id, packages, sandbox, status==submitted]}`. The success arm's `"required"` is `["media_buy_id", "confirmed_at", "revision", "packages"]` — `buyer_ref` is not a property of any arm, and `confirmed_at` + `revision` are required but unmentioned by the obligation. `status` on the success arm is present but `"deprecated": true` ("DEPRECATED in 3.1, removed in 3.2 (#4906). Use `media_buy_status` instead"), so citing `status` as a success field is stale — `media_buy_status` ($ref `enums/media-buy-status.json`) is the successor (repo=adcp ref=3.1.1 path=schemas/enums/media-buy-status.json). FALSE: `warnings` is NOT added to the success variant — it is not declared on any arm of this schema; a bundle-wide scan finds a `"warnings"` property only on `sync-catalogs-response.json`, `log-event-response.json`, `sync-creatives-response.json`, and `sync-accounts-response.json`. Non-blocking advisories at 3.1.1 ride in `errors[]` with `severity: warning` — the submitted arm's `errors` is documented as "Optional advisory errors ... Use only for non-blocking warnings", and the envelope's `adcp_error` states "Non-fatal warnings populate ONLY `payload.errors[]` with `severity: warning`" (repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json). HOLDS: `ext` ($ref `core/ext.json`) is present on all three arms. The scenario as written cannot be graded at 3.1.1 because the field it asserts does not exist on this response.

---

### update-media-buy-request: Update Media Buy Request Schema
**Obligation ID** CONSTR-UPDATE-MEDIA-BUY-REQUEST-01
**Layer** behavioral
**Requirement:** XOR identification (media_buy_id or buyer_ref). Partial update semantics. v3 adds: account_id, buyer_campaign_ref, ext.
**Scenario:**
```gherkin
Given an update request with buyer_campaign_ref="CAMP-2024-Q2"
When processed
Then buyer_campaign_ref is updated on the media buy

Given an update request with ext={"tracking": "abc"}
When processed
Then ext field is preserved
```
**Priority:** P0
**Grounded at 3.1.1:** The headline XOR claim is FALSE and two of the three "v3 adds" fields are wrong; only `ext` survives. `update-media-buy-request.json` declares `"required": ["idempotency_key", "account", "media_buy_id"]` — `media_buy_id` is UNCONDITIONALLY required, `buyer_ref` is not a property of the request, and the schema has no `oneOf`/`anyOf` at any level that could express an XOR (its only `allOf` member is `core/version-envelope.json`, which contributes just `adcp_version`/`adcp_major_version`) (repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json, repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json). Top-level `buyer_ref` is deprecated for v3 correlation generally — `package-request.json` states "Do not use deprecated top-level buyer_ref for v3 correlation" (repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json). CORRECTED: there is no `account_id` field; the added, required field is `account`, an `AccountRef` `oneOf` over `{account_id}` XOR `{brand, operator, sandbox?}` (repo=adcp ref=3.1.1 path=schemas/core/account-ref.json). FALSE: `buyer_campaign_ref` DOES NOT EXIST at 3.1.1 — a scan of every non-bundled file in the schema bundle returns zero occurrences of that literal, so the first scenario cannot be graded against the pin. HOLDS: `ext` is present, `{"$ref": "/schemas/3.1.1/core/ext.json"}` (repo=adcp ref=3.1.1 path=schemas/core/ext.json). SPEC-SILENT on "partial update semantics": everything beyond the three required fields is optional, but nothing in the pinned schema or in the media-buy storyboards states merge-vs-replace semantics for a partial update payload; that clause grades our production behavior.

---

### update-media-buy-response: Update Media Buy Response Schema
**Obligation ID** CONSTR-UPDATE-MEDIA-BUY-RESPONSE-01
**Layer** behavioral
**Requirement:** Atomic: success OR error. v3 adds warnings, ext to success variant.
**Scenario:**
```gherkin
Given an update that produces warnings
When the response is returned
Then warnings array is included alongside success fields
```
**Priority:** P1
**Grounded at 3.1.1:** Atomicity holds, the variant count is wrong, and `warnings` does not exist. `update-media-buy-response.json` is `allOf(core/version-envelope.json, core/protocol-envelope.json)` plus a `oneOf` over THREE arms — `UpdateMediaBuySuccess`, `UpdateMediaBuyError`, and a submitted task envelope — described as "Exactly one of three shapes ... These three shapes are mutually exclusive" (repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-response.json). Atomicity HOLDS: the success arm carries `"not": {"required": ["errors"]}`. HOLDS: `ext` ($ref `core/ext.json`) is on the success arm. FALSE: `warnings` is NOT added to the success variant — it is not a declared property of any arm of this schema; a bundle-wide scan for the `"warnings"` key finds it only on `sync-catalogs-response.json`, `log-event-response.json`, `sync-creatives-response.json`, and `sync-accounts-response.json`. At 3.1.1 non-blocking advisories ride in `errors[]` with `severity: warning` — this response's own description says "The submitted branch MAY carry advisory errors for non-blocking warnings; terminal failures belong in the error branch", and the envelope's `adcp_error` field states "Non-fatal warnings populate ONLY `payload.errors[]` with `severity: warning`" (repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json). The success arm's actual `"required"` is `["media_buy_id", "revision"]`. The scenario as written asserts a field the pin does not define, so it grades our production behavior rather than AdCP conformance.

---

### get-products-request: Get Products Request Schema
**Obligation ID** CONSTR-GET-PRODUCTS-REQUEST-01
**Layer** behavioral
**Requirement:** Optional brief, brand, budget, filters. v3 adds channels filter, product-filters object with delivery_type.
**Scenario:**
```gherkin
Given a get_products request with channels=["display", "ctv"]
When products are filtered
Then only products matching those channels are returned
```
**Priority:** P1
**Grounded at 3.1.1:** Partly true, and it omits the one field that is now mandatory. `get-products-request.json` declares `"required": ["buying_mode"]` — `buying_mode` (enum `["brief", "wholesale", "refine"]`, "v3 clients MUST include buying_mode") is the sole required field and is missing from the obligation entirely (repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json). `brief` and `brand` are optional at the schema level as claimed (`brief` is prose-conditional on `buying_mode: "brief"` but not machine-enforced; the schema's only conditionals are the `if/then` binding `if_wholesale_feed_version`/`if_pricing_version` to wholesale mode, plus `"dependencies": {"catalog": ["brand"], "if_pricing_version": ["if_wholesale_feed_version"]}`). FALSE: there is no top-level `budget` property — the 18 declared properties are buying_mode, brief, refine, brand, catalog, account, preferred_delivery_types, filters, property_list, fields, time_budget, push_notification_config, pagination, if_wholesale_feed_version, if_pricing_version, context, required_policies, ext; the nearest thing is `filters.budget_range`. HOLDS with a shape correction: `filters` is `{"$ref": "/schemas/3.1.1/core/product-filters.json"}`, and that object declares BOTH `channels` (array, items $ref `enums/channels.json`, a 20-value enum including `display` and `ctv`) and `delivery_type` ($ref `enums/delivery-type.json`) — so both new filters exist, but `channels` is nested at `filters.channels`, not a sibling of `brief` (repo=adcp ref=3.1.1 path=schemas/core/product-filters.json, repo=adcp ref=3.1.1 path=schemas/enums/channels.json). The scenario's semantic assertion — that only channel-matching products come back — is SPEC-SILENT/ungraded: storyboards send `filters: {channels: ["display"], delivery_type: "guaranteed"}` purely as request input with no channel-honoring validation (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/canonical_formats.yaml), and the only storyboard that grades filter-honoring semantics does so for `pricing_currencies`, not `channels` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/pricing_currency_filter.yaml). That half grades our production behavior.

---

### get-products-response: Get Products Response Schema
**Obligation ID** CONSTR-GET-PRODUCTS-RESPONSE-01
**Layer** schema
**Requirement:** products array with relevance_score, matching context echo. v3: additional_properties: true on products, proposal_id in response.
**Scenario:**
```gherkin
Given products returned with proposal_id
When the response is assembled
Then proposal_id is included for use in create_media_buy proposal mode
```
**Priority:** P1
**Grounded at 3.1.1:** The `additionalProperties` half holds; both named fields are wrong. HOLDS: `products` is an array of `core/product.json`, and that schema declares `"additionalProperties": true` (repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-response.json, repo=adcp ref=3.1.1 path=schemas/core/product.json). FALSE: `relevance_score` DOES NOT EXIST — a scan of every non-bundled file in the schema bundle returns zero occurrences of that literal; the analogous field on a product is `brief_relevance`, a string ("Explanation of why this product matches the brief (only included when brief is provided)"), and `core/product.json`'s `"required"` is `[product_id, name, description, publisher_properties, delivery_type, pricing_options, reporting_capabilities]`. CORRECTED: `proposal_id` is NOT a top-level field of the response. `get-products-response.json` declares exactly 17 properties — products, extensions, proposals, errors, property_list_applied, catalog_applied, refinement_applied, incomplete, filter_diagnostics, pagination, wholesale_feed_version, pricing_version, cache_scope, unchanged, sandbox, context, ext — with no `proposal_id` among them; this absence was checked after resolving the response's `allOf` (`core/version-envelope.json` + `core/protocol-envelope.json`, which contribute only version and envelope fields) and its root `if/then/else` chain, which adds only conditional `required` entries (`wholesale_feed_version`/`cache_scope` on the unchanged branch, `errors` on the failed branch, `products`/`cache_scope` on the standard branch) and no new properties. The obligation's INTENT is nonetheless satisfiable at 3.1.1 through `proposals[]`: each item is `core/proposal.json` with `"required": ["proposal_id", "name", "allocations"]` (repo=adcp ref=3.1.1 path=schemas/core/proposal.json), and the proposal→create_media_buy handoff is graded — the storyboard captures `context_outputs: path "proposals[0].proposal_id"` and validates `field_present: proposals[0].proposal_id`, then feeds it to `create_media_buy` as `proposal_id: "$context.proposal_id"` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/proposal_finalize.yaml). Rewrite the scenario against `proposals[0].proposal_id`.

---

### protocol-envelope: Protocol Envelope Schema
**Obligation ID** CONSTR-PROTOCOL-ENVELOPE-01
**Layer** behavioral
**Requirement:** Wrapper with status (9-value enum), payload, optional context_id, task_id, message, timestamp, push_notification_config. State machine: submitted/working/input-required are non-terminal; completed/failed/canceled/rejected/auth-required are terminal.
**Scenario:**
```gherkin
Given a response with status="submitted"
When a webhook is configured
Then webhook notification is triggered for async updates

Given a response with status="completed"
Then no webhook is triggered (terminal state)
```
**Priority:** P1
**Grounded at 3.1.1:** Substantially true, with three corrections. HOLDS: `core/protocol-envelope.json` declares `context_id`, `context`, `task_id`, `status`, `message`, `timestamp`, `push_notification_config` and `payload`, with `"required": ["status"]` (repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json). HOLDS: `status` is a 9-value enum — `enums/task-status.json` lists exactly `submitted, working, input-required, completed, canceled, failed, rejected, auth-required, unknown` (repo=adcp ref=3.1.1 path=schemas/enums/task-status.json). HOLDS: the non-terminal set is `submitted`/`working`/`input-required`, stated normatively as "a non-terminal task envelope (status `submitted` / `working` / `input-required`, carrying a `task_id`)" (repo=adcp ref=3.1.1 path=universal/storyboard-schema.yaml). CORRECTION 1: the obligation's terminal list drops `unknown`, the 9th enum value, which it neither classifies nor mentions. CORRECTION 2: `payload` is NOT a required wrapper member — the schema calls it "a documentary construct — it is NOT a required wire field", and only `status` is required. CORRECTION 3: the envelope also carries `replayed`, `adcp_error`, and `governance_context`, none of which the obligation lists, and it bans the legacy names via a root `"not": {"anyOf": [{"required": ["task_status"]}, {"required": ["response_status"]}]}` — graded by `envelope_field_present: status` plus `envelope_field_absent: task_status`/`response_status` (repo=adcp ref=3.1.1 path=universal/v3-envelope-integrity.yaml). BOTH scenario branches HOLD and are graded: "`push_notification_config` registers a notification channel for operations whose initial response is non-terminal (`working` or `submitted`)", and conversely "Sellers MUST NOT emit task webhooks for inline terminal responses ... it does not ask the seller to duplicate an inline terminal result onto the webhook channel" (repo=adcp ref=3.1.1 path=universal/webhook-emission.yaml).

---

### async-response-get-products: Get Products Async Responses
**Obligation ID** CONSTR-ASYNC-RESPONSE-GET-PRODUCTS-01
**Layer** schema
**Requirement:** Per-status response schemas: submitted (estimated_completion), working (percentage, current_step), input-required (reason, partial_results, suggestions). All include context + ext.
**Scenario:**
```gherkin
Given a long-running product search
When status transitions to "working"
Then the response includes percentage and current_step fields

Given status is "input-required" with reason="CLARIFICATION_NEEDED"
When the response is returned
Then partial_results may be included to help inform the clarification
```
**Priority:** P2
**Grounded at 3.1.1:** True as stated, field for field. Submitted: `get-products-async-response-submitted.json` declares `estimated_completion` (`format: date-time`, "Estimated completion time for the search") with `"required": ["status", "task_id"]`, `status` pinned to `"const": "submitted"`, and a root `"not": {"anyOf": [{required:[products]}, {required:[proposals]}, {required:[result]}]}` keeping terminal data off the envelope (repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-async-response-submitted.json). Working: `percentage` (number, 0–100) and `current_step` (string, e.g. 'searching_inventory') are both declared, alongside `total_steps` and `step_number` (repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-async-response-working.json). Input-required: `reason` (string enum `["CLARIFICATION_NEEDED", "BUDGET_REQUIRED"]` — so the scenario's `CLARIFICATION_NEEDED` is a valid value), `partial_results` (array of `core/product.json`, "Partial product results that may help inform the clarification") and `suggestions` (array of string) are all declared and all optional, matching the scenario's "partial_results MAY be included" (repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-async-response-input-required.json). "All include context + ext" HOLDS: each of the three files declares `context` ($ref `core/context.json`) and `ext` ($ref `core/ext.json`). None of the three schemas uses `allOf`/`oneOf`/`anyOf`, so the field readings are direct. GRADING CAVEAT worth recording on the obligation: only the submitted arm is exercised by the pinned storyboards — `get_products_async.yaml` sets `response_schema_ref: "media-buy/get-products-async-response-submitted.json"` and asserts `status == submitted` plus field-absence of products/proposals/result (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/get_products_async.yaml); a full-tree scan finds zero storyboard references to the working or input-required schemas, so those two arms are schema-defined but ungraded.

---

### async-response-create-media-buy: Create Media Buy Async Responses
**Obligation ID** CONSTR-ASYNC-RESPONSE-CREATE-MEDIA-BUY-01
**Layer** behavioral
**Requirement:** Per-status schemas: submitted (context, ext), working (percentage, current_step), input-required (reason: APPROVAL_REQUIRED | BUDGET_EXCEEDS_LIMIT, errors).
**Scenario:**
```gherkin
Given a create_media_buy that requires approval
When status is "input-required"
Then reason="APPROVAL_REQUIRED" maps to HITL pattern
```
**Priority:** P2
**Grounded at 3.1.1:** Holds. 3.1.1 ships exactly the three status-specific create_media_buy async payload schemas the obligation names. Submitted declares `status` (const "submitted"), `task_id`, `message`, `errors`, `context`, `ext`, `"required": ["status","task_id"]` (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-async-response-submitted.json). Working declares `percentage` (minimum 0, maximum 100), `current_step`, plus `total_steps`/`step_number`, `context`, `ext` (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-async-response-working.json). Input-required declares `reason` with `"enum": ["APPROVAL_REQUIRED", "BUDGET_EXCEEDS_LIMIT"]` and an optional `errors` array of core/error.json (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-async-response-input-required.json). All three are arms of the `anyOf` in repo=adcp ref=3.1.1 path=schemas/core/async-response-data.json ("For working/input-required/submitted, use the status-specific schemas"), and the status literals are members of repo=adcp ref=3.1.1 path=schemas/enums/task-status.json. Two scoping notes: on the submitted arm `context`/`ext` are optional while `status`+`task_id` are the required pair, and "maps to HITL pattern" is our own mapping — 3.1.1 fixes only the reason code. Composition resolved on the synchronous response (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-response.json): its allOf is version-envelope + protocol-envelope and its oneOf is success/error/submitted only — no working or input-required arm exists there, confirming these three shapes are task-layer payloads, which is what the graded storyboard exercises (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/create_media_buy_async.yaml grades only the submitted arm).

---

### get-media-buy-delivery-request: Delivery Request Schema
**Obligation ID** CONSTR-GET-MEDIA-BUY-DELIVERY-REQUEST-01
**Layer** schema
**Requirement:** Optional media_buy_ids (priority), buyer_refs, start_date, end_date, status_filter, account_id. media_buy_ids takes precedence. Neither = all principal's buys.
**Scenario:**
```gherkin
Given both media_buy_ids and buyer_refs provided
When delivery is queried
Then only media_buy_ids are used

Given start_date after end_date
When delivery is queried
Then the request is rejected (inverted date range)
```
**Priority:** P1
**Grounded at 3.1.1:** Partly true — two of the six named fields are wrong. Confirmed at repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buy-delivery-request.json: `media_buy_ids` (array, `minItems: 1`, optional), `status_filter` (oneOf single MediaBuyStatus or non-empty array), `start_date` and `end_date` (both `"pattern": "^\\d{4}-\\d{2}-\\d{2}$"`, optional, "When omitted along with end_date, returns campaign lifetime data"). FALSE part 1: there is no `buyer_refs` field — composition resolved, the schema's only `allOf` member is repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json, which contributes just `adcp_version`/`adcp_major_version`, and there is no oneOf/anyOf; `buyer_refs` appears nowhere in the request schema or in the pinned compliance tree, so "media_buy_ids takes precedence over buyer_refs" has no 3.1.1 counterpart. FALSE part 2: the account filter is not a scalar `account_id` — it is `account`, a `$ref` to repo=adcp ref=3.1.1 path=schemas/core/account-ref.json, whose oneOf is either `{account_id}` or the natural key `{brand, operator, sandbox}`; `account_id` is one branch of that ref, not a top-level request field. Its description carries the only spec-side omission rule: "When omitted, returns data across all accessible accounts" — note "accessible accounts", not "the principal's buys". The inverted-date-range rejection in the scenario is spec-silent at schema level (both dates carry only a format pattern, with no cross-field if/then and no ordering constraint); the pinned get_media_buy_delivery task-reference prose does list an INVALID_DATE_RANGE code with "ensure start < end", but that code is not a member of the canonical vocabulary at repo=adcp ref=3.1.1 path=schemas/enums/error-code.json (92 entries, no INVALID_DATE_RANGE), so date ordering grades our own behavior under the enum's "Sellers MAY return codes not listed here" allowance.

---

### reporting-webhook: Webhook Configuration Schema
**Obligation ID** CONSTR-REPORTING-WEBHOOK-01
**Layer** behavioral
**Requirement:** url (URI), authentication (schemes: Bearer|HMAC-SHA256, credentials min 32 chars), reporting_frequency (hourly|daily|monthly), optional requested_metrics, token (min 16 chars). Payload: notification_type, sequence_number, next_expected_at (conditional), partial_data.
**Scenario:**
```gherkin
Given webhook credentials with 31 characters
When webhook configuration is validated
Then it is rejected (minimum 32 chars)

Given HMAC-SHA256 signing
When a webhook is delivered
Then X-ADCP-Signature and X-ADCP-Timestamp headers are present
```
**Priority:** P1
**Grounded at 3.1.1:** Holds, field for field. repo=adcp ref=3.1.1 path=schemas/core/reporting-webhook.json declares `url` (`"format": "uri"`), `token` (`"minLength": 16`), `authentication` (object, `"required": ["schemes","credentials"]`, `additionalProperties: false`, with `credentials` carrying `"minLength": 32` and `schemes` a 1-item array of repo=adcp ref=3.1.1 path=schemas/enums/auth-scheme.json whose `enum` is exactly `["Bearer", "HMAC-SHA256"]`), `reporting_frequency` (`"enum": ["hourly","daily","monthly"]`), and optional `requested_metrics`; the schema's `"required"` is `["url","authentication","reporting_frequency"]`, so the 31-character-credentials rejection in the scenario is a direct `minLength: 32` violation. The payload half is confirmed at repo=adcp ref=3.1.1 path=schemas/media-buy/media-buy-delivery-webhook-result.json: `notification_type` (enum scheduled/final/delayed/adjusted/window_update, and a member of that schema's `required`), `sequence_number` (integer, minimum 1), `next_expected_at` (date-time, "Omitted on final notifications" — the conditional the obligation names), and `partial_data` (boolean). One scoping correction to record: the `X-ADCP-Signature`/`X-ADCP-Timestamp` header pair is not defined by reporting-webhook.json itself — it belongs to the shared legacy HMAC-SHA256 signing profile, which the bundle states normatively at repo=adcp ref=3.1.1 path=schemas/collection/collection-list-changed-webhook.json ("Recipients MUST verify against the X-ADCP-Signature and X-ADCP-Timestamp headers using timing-safe comparison and MUST reject requests where |now - timestamp| > 300 seconds"), and which the pinned L1 security prose specifies as `X-ADCP-Signature: sha256=<hex digest>`. That profile is deprecated at 3.1.1 in favor of RFC 9421 (reporting-webhook.json: "Both schemes are deprecated; the preferred signing profile for new integrations is RFC 9421"), and every webhook-signing test vector in the pinned compliance tree is 9421-shaped, so the HMAC header assertion grades a deprecated-but-still-required 3.x path, not the default one.

---

### brand_manifest_policy: Brand Manifest Policy Gate
**Obligation ID** CONSTR-BRAND-MANIFEST-POLICY-01
**Layer** schema
**Requirement:** Enum: public, require_auth, require_brand. Default require_auth. require_brand requires brand field in request.
**Scenario:**
```gherkin
Given policy="require_brand" and no brand in request
When get_products is called
Then the request is rejected

Given default policy (require_auth) and authenticated caller
When get_products is called
Then the request proceeds
```
**Priority:** P1
**Grounded at 3.1.1:** Spec-silent — no `brand_manifest_policy` concept exists at 3.1.1 in any form. A full-text scan for `brand_manifest_policy`, `require_brand`, and `require_auth` across the 3.1.1 schema bundle, the pinned compliance tree, and the pinned docs tree returns zero hits, so the three-value enum and its `require_auth` default are ours, not AdCP's. The one thing the spec does fix is the opposite of what the obligation asserts for get_products: composition resolved at repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json, its `"required"` is `["buying_mode"]` alone and its `allOf` is version-envelope plus a wholesale-feed-version conditional that adds no brand requirement, so `brand` (a `$ref` to core/brand-ref.json) is unconditionally OPTIONAL on discovery — a seller cannot ground a mandatory-brand rejection of get_products in the pinned request schema. The nearest pinned analogue is the `BRAND_REQUIRED` code at repo=adcp ref=3.1.1 path=schemas/enums/error-code.json, but its semantics are narrower and non-configurable: "A billable operation was attempted without a brand reference. Every billable operation requires either a seller-assigned `account_id` or a natural key including `brand`" — it is scoped to billable operations, not discovery, and is not a per-tenant policy toggle. This obligation therefore grades our own tenant access policy, not AdCP conformance.

---

### publisher_domains (response): Portfolio Assembly Output
**Obligation ID** CONSTR-PUBLISHER-DOMAINS-PORTFOLIO-01
**Layer** behavioral
**Requirement:** Array of domain strings, sorted alphabetically. All partnerships included regardless of verification. Empty = empty array.
**Scenario:**
```gherkin
Given publishers ["xyz.com", "abc.com"]
When list_authorized_properties returns
Then domains are ["abc.com", "xyz.com"] (alphabetical)
```
**Priority:** P1
**Grounded at 3.1.1:** Partly true, and the scenario's carrier task no longer exists. The `list_authorized_properties` task the scenario calls is retired at 3.1.1 — repo=adcp ref=3.1.1 path=specialisms/signal-owned/index.yaml states "the v2 `list_authorized_properties` task is retired; portfolio advertising now lives on `get_adcp_capabilities`", and no list-authorized-properties schema exists in the bundle. The field itself survives, relocated: repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json defines `media_buy.portfolio.publisher_domains` as an array of domain strings (`"pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$"`) and makes it the sole member of `portfolio`'s `"required"`, with the description "Publisher domains this seller is authorized to represent." FALSE part: "Empty = empty array" is contradicted — the field carries `"minItems": 1`, so an empty array is a schema violation, and since `publisher_domains` is required whenever `portfolio` is emitted, the correct 3.1.1 encoding of an empty portfolio is to omit `portfolio`, not to emit `[]`. SPEC-SILENT parts: alphabetical ordering is nowhere stated (the items schema carries only a pattern; no `x-ordering`, no prose ordering rule) and no compliance storyboard grades ordering — a scan of compliance/3.1.1 for `publisher_domains` returns zero hits and only three files mention `portfolio` at all, none of them media-buy scenarios. The "all partnerships regardless of verification" rule is likewise unstated. Ordering and inclusion therefore grade our own behavior.

---

### publisher_domains_filter (request): Domain Filter
**Obligation ID** CONSTR-PUBLISHER-DOMAINS-FILTER-01
**Layer** schema
**Requirement:** Optional array, minItems: 1. Pattern: lowercase alphanumeric + hyphens + dots. Invalid format = DOMAIN_INVALID_FORMAT. Valid non-matching = empty results.
**Scenario:**
```gherkin
Given filter=["CNN.COM"]
Then rejected with DOMAIN_INVALID_FORMAT

Given filter=[]
Then rejected (minItems: 1)
```
**Priority:** P2
**Grounded at 3.1.1:** Retired. The request-side `publisher_domains` filter belonged to the v2 `list_authorized_properties` task, which repo=adcp ref=3.1.1 path=specialisms/signal-owned/index.yaml records as removed: "the v2 `list_authorized_properties` task is retired; portfolio advertising now lives on `get_adcp_capabilities`". The replacement surface carries no such filter — composition resolved at repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-request.json, whose only `allOf` member is core/version-envelope.json (no oneOf/anyOf), and whose complete property set is `protocols`, `context`, `ext`; there is no `publisher_domains`, hence no `minItems: 1` on a filter and no valid-non-matching-returns-empty semantics to grade. The error code the obligation demands does not exist either: `DOMAIN_INVALID_FORMAT` appears nowhere in the 3.1.1 bundle, and the canonical 92-value vocabulary at repo=adcp ref=3.1.1 path=schemas/enums/error-code.json contains no DOMAIN_* code at all. The lowercase domain pattern the obligation cites does survive, but only on the RESPONSE side (`media_buy.portfolio.publisher_domains[]` items pattern in repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json) — a seller emission constraint, not a request-rejection rule. Nothing in 3.1.1 grades a `["CNN.COM"]` request rejection.

---

### advertising_policies: Policy Disclosure
**Obligation ID** CONSTR-ADVERTISING-POLICIES-01
**Layer** schema
**Requirement:** Optional string (minLength: 1, maxLength: 10000). Present only when policy enabled AND at least one array non-empty. Omitted otherwise.
**Scenario:**
```gherkin
Given policy enabled with prohibited_categories=["gambling"]
Then advertising_policies field contains "gambling" text

Given policy enabled but all arrays empty
Then advertising_policies field is omitted entirely
```
**Priority:** P2
**Grounded at 3.1.1:** Partly true — one constraint is invented and the presence rule is ours. At repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json the field is `media_buy.portfolio.advertising_policies`, declared in full as `{"type": "string", "description": "Advertising content policies, restrictions, and guidelines", "maxLength": 10000}`. So "optional string" holds (composition resolved: `portfolio`'s `"required"` is `["publisher_domains"]` only, `media_buy` declares no `required`, and the response's own `"required"` is `["adcp", "supported_protocols"]`; the response `allOf` is version-envelope + protocol-envelope, contributing no constraint here) and `maxLength: 10000` holds verbatim. FALSE part: there is no `minLength: 1` — the pinned declaration has exactly three keywords and an empty string validates. SPEC-SILENT part: "Present only when policy enabled AND at least one array non-empty. Omitted otherwise" has no counterpart — 3.1.1 attaches no conditional-presence rule to this field, and a full-text scan finds `advertising_policies` in only three bundle files (this response schema, manifest.json, and the `CREATIVE_REJECTED` description at schemas/enums/error-code.json, which merely says "revise the creative per the seller's advertising_policies"), with zero occurrences anywhere in the pinned compliance tree. The emission rule therefore grades our production behavior.

---

### validation_mode: Sync Creatives Validation Mode
**Obligation ID** CONSTR-VALIDATION-MODE-01
**Layer** schema
**Requirement:** Enum: strict|lenient. Default strict. Strict aborts on assignment error. Lenient logs warning and continues.
**Scenario:**
```gherkin
Given validation_mode="partial" (unknown value)
Then schema validation error
```
**Priority:** P1
**Grounded at 3.1.1:** The schema half holds exactly; the behavioral half is mis-stated. repo=adcp ref=3.1.1 path=schemas/enums/validation-mode.json is a closed `"enum": ["strict", "lenient"]` with no composition keywords of its own, and composition is resolved on both consumers: repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json (`required` `["idempotency_key","account","creatives"]`) and repo=adcp ref=3.1.1 path=schemas/media-buy/sync-catalogs-request.json (`required` `["idempotency_key","account"]`) each carry a single `allOf` member — repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json — and no oneOf/anyOf, so nothing widens or overrides the vocabulary and the scenario's `validation_mode: "partial"` is a genuine schema validation error. Both consumers pin `"default": "strict"` on the `$ref`. FALSE part: the pinned semantics are not "aborts on assignment error" / "logs warning and continues". The sync_creatives declaration reads "'strict' fails entire sync on any validation error. 'lenient' processes valid creatives and reports errors" (sync_catalogs is identical with "catalogs"). Two corrections follow — the strict trigger is ANY validation error on the sync payload, not specifically an assignment error; and lenient carries a wire obligation to REPORT the errors back in the response, which is stronger than logging a warning and continuing. The only pinned storyboard touching the field confirms the default rather than the arms: repo=adcp ref=3.1.1 path=domains/creative/scenarios/native_in_feed.yaml narrates "The validation_mode is strict (default); the seller stops on the first violation."

---

### brief_policy: Brief Policy Compliance
**Obligation ID** CONSTR-BRIEF-POLICY-01
**Layer** behavioral
**Requirement:** Behavioral constraint. Policy disabled = unchecked. BLOCKED = POLICY_VIOLATION. Service unavailable = fail-open.
**Scenario:**
```gherkin
Given policy enabled and LLM returns BLOCKED
Then request rejected with POLICY_VIOLATION
```
**Priority:** P2
**Grounded at 3.1.1:** Spec-silent on the rule; only the error code is pinned. `POLICY_VIOLATION` is a member of the canonical vocabulary at repo=adcp ref=3.1.1 path=schemas/enums/error-code.json, described as "Request violates the seller's content or advertising policies" with `enumMetadata` `{"recovery": "correctable", "suggestion": "review policy requirements in the error details"}`, so emitting POLICY_VIOLATION when a brief is blocked is spec-consistent — the pinned get_products task-reference likewise lists it for "Category blocked for advertiser". Everything else in the obligation has no pinned counterpart. Composition resolved on the only candidate carrier, repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json: its `allOf` is version-envelope plus a wholesale-feed-version conditional, it has no oneOf/anyOf, and of its 18 declared properties `brief` is a bare `{"type": "string"}` with no policy or moderation sibling (`required_policies` is a registry-policy-ID filter, not a content gate) — so 3.1.1 defines no brief-policy toggle ("policy disabled = unchecked" is unstated), no LLM adjudication step or BLOCKED verdict, and no fail-open-on-service-unavailable rule for policy checks. A scan of the pinned compliance tree finds zero YAML storyboards referencing POLICY_VIOLATION at all, so this obligation is ungraded by AdCP conformance, and a scan for "fail-open"/"fail open" across compliance/3.1.1 (0 hits) and docs/3.1.1 hits only trusted-match, versioning, and L1 security — none of them brief policy. The gating and failure-mode behavior therefore grades our own production behavior, with only the error-code choice constrained by AdCP.

---

### principal_visibility: Principal-Scoped Visibility
**Obligation ID** CONSTR-PRINCIPAL-VISIBILITY-01
**Layer** behavioral
**Requirement:** null/empty allowed_principal_ids = visible to all. Non-empty = only listed principals. Anonymous cannot see restricted.
**Scenario:**
```gherkin
Given allowed_principal_ids=["p1"] and caller is anonymous
Then product is suppressed
```
**Priority:** P1
**Grounded at 3.1.1:** Spec-silent — 3.1.1 has no product-visibility ACL. A full-text scan for `allowed_principal` across the 3.1.1 schema bundle, the pinned compliance tree, and the pinned docs tree returns zero hits, and `principal_id` appears nowhere in the bundle. Composition resolved on the product model at repo=adcp ref=3.1.1 path=schemas/core/product.json: its `allOf` is a single conditional (signal-targeting declaration) contributing no fields, its `anyOf` is the legacy-`format_ids` vs 3.1-`format_options` discriminator, its `"required"` is `["product_id","name","description","publisher_properties","delivery_type","pricing_options","reporting_capabilities"]`, and none of its 49 declared properties expresses visibility, allow-listing, or caller restriction — the nearest neighbours, `allowed_actions` and `enforced_policies`, are an advisory buy-action template and a registry-policy-ID list, neither keyed to a caller — so there is no field on which "null/empty = visible to all" or "non-empty = only listed principals" could be graded. The word "principal" survives at 3.1.1 only as caller scoping in prose (17 non-bundled schema files), never as a product-side identifier: repo=adcp ref=3.1.1 path=schemas/core/tasks-list-request.json says "Sellers MUST only return tasks created for the caller's authenticated account + principal pair", and the protocol's actual actor key is the AccountRef (account_id, or brand+operator). Nothing in 3.1.1 speaks to anonymous callers and suppressed products. This obligation grades our own tenant/principal authorization model, not AdCP conformance.

---

### anonymous_pricing: Anonymous Pricing Suppression
**Obligation ID** CONSTR-ANONYMOUS-PRICING-01
**Layer** behavioral
**Requirement:** Authenticated = full pricing. Anonymous = pricing_options=[].
**Scenario:**
```gherkin
Given anonymous request
Then every product has pricing_options=[]
```
**Priority:** P1
**Grounded at 3.1.1:** The authenticated/anonymous tiering is real but permissive, and the specific empty-array representation is wrong. `get_products` responses put `products[]` items behind `$ref` to the Product schema (the response itself is `allOf` version-envelope + protocol-envelope with an if/then/else on `unchanged` / `status: "failed"`; the standard branch requires `products` and `cache_scope`, and no branch relaxes the item schema for unauthenticated callers) — repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-response.json. Product lists `pricing_options` in `required` and constrains it with `minItems: 1`, so `pricing_options: []` is schema-INVALID at 3.1.1 for any caller, authenticated or not — repo=adcp ref=3.1.1 path=schemas/core/product.json. The graded storyboard restates this: "pricing_options: array (minItems: 1) — each with pricing_option_id, pricing_model, and currency" and "Responses missing any of these fields fail schema validation" — repo=adcp ref=3.1.1 path=universal/schema-validation.yaml. The pinned prose (building/by-layer/L2/authentication.mdx "Unauthenticated `get_products` MAY return … No pricing information or CPM details"; media-buy/task-reference/get_products.mdx "Authentication Behavior") states the tiering as a permission, not an obligation, and the only graded auth storyboard covers 401/403 rejection of protected operations — it does not grade anonymous pricing redaction — repo=adcp ref=3.1.1 path=universal/security.yaml. Conformant redaction is therefore "return fewer products" or omit priced products, never a product carrying an empty `pricing_options`. This obligation grades our own redaction policy, and its stated shape must change.

---

### relevance_threshold: AI Ranking Threshold
**Obligation ID** CONSTR-RELEVANCE-THRESHOLD-01
**Layer** behavioral
**Requirement:** Score >= 0.1 included, < 0.1 excluded. Range 0.0-1.0. No ranking = no threshold.
**Scenario:**
```gherkin
Given ranking active and score=0.09
Then product excluded

Given score=0.1
Then product included (boundary)
```
**Priority:** P2
**Grounded at 3.1.1:** AdCP 3.1.1 defines no numeric relevance score and therefore no inclusion threshold. The only relevance-named field on a product is `brief_relevance`, typed `"type": "string"` — "Explanation of why this product matches the brief (only included when brief is provided)" — free-text rationale, not a 0.0-1.0 score; resolving the schema's `allOf` (a conditional on signal-targeting that contributes no fields) and its `anyOf` (format_ids vs format_options presence) adds no scoring field either — repo=adcp ref=3.1.1 path=schemas/core/product.json. In the request, `brief_relevance` appears only as one value in the `fields` enum — the response field-selection projection list ("Specific product fields to include in the response"), not a sort key; there is no sort-by-relevance construct at all — repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json. The other relevance hit in the bundle is keyword-relevance filtering for retail media, with no score — repo=adcp ref=3.1.1 path=schemas/core/product-filters.json. A grep for `relevance` across the whole compliance tree returns zero hits, so no storyboard grades ranking, scoring, or a cut-off. The 0.1 boundary, the 0.0-1.0 range, and "no ranking = no threshold" are entirely our own product-ranking behavior.

---

### pricing_option_xor: Fixed/Floor Price XOR
**Obligation ID** CONSTR-PRICING-OPTION-XOR-01
**Layer** schema
**Requirement:** Exactly one of fixed_price or floor_price. Both = invalid. Neither = invalid. CPA always fixed_price.
**Scenario:**
```gherkin
Given both fixed_price and floor_price set
Then pricing option is invalid
```
**Priority:** P0
**Grounded at 3.1.1:** Only the CPA half survives. PricingOption has NO properties of its own — it is a `oneOf` over nine model schemas discriminated by `pricing_model`, and its description states the rule directly: "If fixed_price is present, it's fixed pricing. If absent, it's auction-based (floor_price and price_guidance optional)" — repo=adcp ref=3.1.1 path=schemas/core/pricing-option.json. So "neither = invalid" is FALSE: omitting both is the open-auction case (pinned prose, reference/whats-new-in-v3.mdx: "Open auction inventory omits both fields"). "Both = invalid" is not enforced at the schema layer this obligation claims: the branch schemas carry no `oneOf`/`allOf`/`anyOf`/`dependencies`/`not`, and both `fixed_price` and `floor_price` are plain optional numbers with `minimum: 0`; the exclusion exists only as prose inside `floor_price.description` ("mutually exclusive with fixed_price") and in reference/migration/pricing.mdx — repo=adcp ref=3.1.1 path=schemas/pricing-options/cpm-option.json. "CPA always fixed_price" HOLDS: cpa-option.json lists `fixed_price` in `required` with `"exclusiveMinimum": 0` and declares no `floor_price` property at all (no composition keywords on that file, so the absence is complete) — repo=adcp ref=3.1.1 path=schemas/pricing-options/cpa-option.json. The nine-model count also still holds.

---

### product_min_cardinality: Product Array Minimums
**Obligation ID** CONSTR-PRODUCT-MIN-CARDINALITY-01
**Layer** schema
**Requirement:** format_ids >= 1, publisher_properties >= 1, pricing_options >= 1. Empty = ValueError.
**Scenario:**
```gherkin
Given product with format_ids=[]
Then conversion fails with ValueError
```
**Priority:** P0
**Grounded at 3.1.1:** Two of the three cardinalities hold; the `format_ids` one does not. Product `required` is [product_id, name, description, publisher_properties, delivery_type, pricing_options, reporting_capabilities], with `publisher_properties.minItems: 1` and `pricing_options.minItems: 1` — both confirmed — but `format_ids` carries NO `minItems` (only `format_options` does), so `format_ids: []` satisfies the schema; the top-level `anyOf` (Legacy Product vs 3.1+ Product) constrains only PRESENCE of `format_ids` or `format_options`, not their length, and the top-level `allOf` is a signal-targeting if/then that contributes no cardinality — repo=adcp ref=3.1.1 path=schemas/core/product.json. The graded storyboard's own enumeration mirrors that asymmetry, annotating minItems: 1 on `publisher_properties` and `pricing_options` while listing `format_ids` as a plain "array of format_id objects" — repo=adcp ref=3.1.1 path=universal/schema-validation.yaml. The "empty = ValueError" outcome is our conversion-layer behavior; AdCP grades this as response-schema validation failure, not a named error.

---

### currency_consistency: Currency Across Packages
**Obligation ID** CONSTR-CURRENCY-CONSISTENCY-01
**Layer** behavioral
**Requirement:** All packages same currency. Currency in tenant CurrencyLimit table.
**Scenario:**
```gherkin
Given packages with ["USD", "EUR"]
Then rejected for mixed currencies
```
**Priority:** P0
**Grounded at 3.1.1:** The mechanism is right, the mandate is not. PackageRequest has no `currency` property at all — `budget` is a bare number described as "Budget allocation for this package in the media buy's currency" and currency is carried by the referenced `pricing_option_id`; resolving the file's `allOf` (core/version-envelope.json), its `dependencies` (`params` → `format_kind`) and its top-level `not` (bans `capability_ids`) adds no currency field — repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json. Currency enters through the pricing option (`"pattern": "^[A-Z]{3}$"`) — repo=adcp ref=3.1.1 path=schemas/pricing-options/cpm-option.json — and via `total_budget.currency` on the proposal-execution path — repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json. But 3.1.1 does NOT require one currency per media buy: media-buy/task-reference/create_media_buy.mdx:1099 states "Packages can use different currencies when sellers support it", and advanced-topics/pricing-models.mdx:784 makes it a seller duty rather than a protocol invariant ("Sellers validate currency compatibility across packages"). What AdCP DOES grade on currency is discovery-side, not execution-side: a storyboard requires the seller to honour `filters.pricing_currencies` on get_products by pruning a product's `pricing_options` to the requested currency and excluding products whose mandatory charges cannot be satisfied in it — repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/pricing_currency_filter.yaml, mirrored at repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/pricing_currency_filter.yaml. No storyboard grades a mixed-currency rejection at create_media_buy. So rejecting `["USD", "EUR"]` is a permitted seller-capability limit, not AdCP conformance — and the conformant way to keep buyers out of that state is the `pricing_currencies` filter, not a create-time error. "Currency in the tenant CurrencyLimit table" is purely our own model.

---

### product_uniqueness: Product ID Uniqueness
**Obligation ID** CONSTR-PRODUCT-UNIQUENESS-01
**Layer** behavioral
**Requirement:** No duplicate product_id across packages in a media buy.
**Scenario:**
```gherkin
Given two packages both with product_id="prod_1"
Then rejected for duplicate product
```
**Priority:** P1
**Grounded at 3.1.1:** AdCP explicitly permits what this obligation rejects. A graded storyboard builds a media buy whose two packages carry the SAME `product_id` (both `$context.product_id`, same `pricing_option_id`), with the narrative stating outright "create a buy with two packages (same product is fine — packages are independent line items)", and it grades that the seller returns `packages[1].package_id` — i.e. a seller that rejected the duplicate would FAIL the scenario — repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/dependency_impairment_cardinality.yaml, mirrored at repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml. The schema agrees: `packages` is an array with `minItems: 1` and NO `uniqueItems`, its items `$ref` PackageRequest, and no dependency or conditional keys uniqueness — repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json, repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json. The pinned prose is the same (media-buy/media-buys/index.mdx: "the same product appears as multiple packages with different date windows and budgets"; "Multiple packages for the same product may have overlapping date ranges"). Our duplicate-product rejection is non-conformant, not merely ungraded.

---

### creative_asset: Creative Asset Conditional Presence
**Obligation ID** CONSTR-CREATIVE-ASSET-01
**Layer** behavioral
**Requirement:** Reference creatives require url+width+height. Generative formats exempt. Errors collected.
**Scenario:**
```gherkin
Given reference creative missing url
Then error collected
```
**Priority:** P1
**Grounded at 3.1.1:** The url+width+height rule is per-ASSET-TYPE, not per-"reference creative", and 3.1.1 has no reference-vs-generative discriminator to exempt on. `url`, `width`, `height` are all in `required` (with `width`/`height` `minimum: 1`) on exactly two of the twenty union members, the hosted-file types — repo=adcp ref=3.1.1 path=schemas/core/assets/image-asset.json and repo=adcp ref=3.1.1 path=schemas/core/assets/video-asset.json — while siblings require far less: url-asset.json requires [asset_type, url] with no dimensions, text-asset.json requires [asset_type, content], and brief-asset.json requires [asset_type] directly plus, via its `allOf` → core/creative-brief.json, `name` — repo=adcp ref=3.1.1 path=schemas/core/assets/url-asset.json, repo=adcp ref=3.1.1 path=schemas/core/assets/text-asset.json, repo=adcp ref=3.1.1 path=schemas/core/assets/brief-asset.json, repo=adcp ref=3.1.1 path=schemas/core/creative-brief.json. Which member applies is chosen by the `asset_type` discriminator over a 20-branch `oneOf` — repo=adcp ref=3.1.1 path=schemas/core/assets/asset-union.json. CreativeAsset itself requires only [creative_id, name, assets], its root `oneOf` splits on `format_id` XOR `format_kind` (not on generative-ness) and its root `not` bans `capability_id`/`capability_ref`; the generative signal is the optional `inputs[]` array — repo=adcp ref=3.1.1 path=schemas/core/creative-asset.json. "Errors collected" HOLDS: the sync response (composition resolved — `allOf` version-envelope + protocol-envelope, then a 3-branch `oneOf`) has a SyncCreativesSuccess branch described as "may include per-item failures", whose `creatives[]` items carry an `errors` array of core/error.json "only present when action='failed'" — repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-response.json, repo=adcp ref=3.1.1 path=schemas/core/error.json.

---

### budget_amount: Budget Positivity
**Obligation ID** CONSTR-BUDGET-AMOUNT-01
**Layer** schema
**Requirement:** amount > 0. Schema minimum: 0 but business rule requires > 0.
**Scenario:**
```gherkin
Given amount=0
Then rejected by business rule (not schema)
```
**Priority:** P0
**Grounded at 3.1.1:** The schema half holds; the ">0 business rule" is ours, not AdCP's. `total_budget` is an inline object with `required: [amount, currency]`, `additionalProperties: false`, and `amount.minimum: 0` — so zero is schema-VALID — repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json; package `budget` is likewise a plain number with `minimum: 0` and the file adds no conditional (`allOf` is just core/version-envelope.json, `dependencies` only maps `params` → `format_kind`) — repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json. What 3.1.1 actually grades is the NEGATIVE case, not the zero boundary: the error-compliance storyboard sends `budget: -500`, marks it `negative_path: schema_invalid`, and accepts VALIDATION_ERROR, INVALID_REQUEST, or BUDGET_TOO_LOW — repo=adcp ref=3.1.1 path=universal/error-compliance.yaml. The only spec-side floor above zero is seller-declared, not protocol-fixed: BUDGET_TOO_LOW is "Budget is below the seller's minimum" with the suggestion "increase budget or check capabilities.media_buy.limits" — repo=adcp ref=3.1.1 path=schemas/manifest.json — and per-option `min_spend_per_package` (`minimum: 0`) — repo=adcp ref=3.1.1 path=schemas/pricing-options/cpm-option.json. So rejecting amount=0 is a legitimate seller minimum; the obligation must not present it as an AdCP requirement.

---

### daily_spend_cap: Daily Spend Cap
**Obligation ID** CONSTR-DAILY-SPEND-CAP-01
**Layer** schema
**Requirement:** daily_budget = budget / max(1, flight_days) <= max_daily_package_spend. Cap not configured = skipped.
**Scenario:**
```gherkin
Given budget=10000, flight=2 days, cap=4000 (daily=5000)
Then rejected (5000 > 4000)
```
**Priority:** P1
**Grounded at 3.1.1:** No such field and no such rule exist at the pin. There is no daily-spend property anywhere in the schema bundle: every `daily` occurrence outside bundled/ is a reporting cadence, update frequency, or forecast granularity enum, never a spend ceiling — repo=adcp ref=3.1.1 path=schemas/core/reporting-capabilities.json. Nothing in the request carries a daily cap either: PackageRequest exposes `budget`, `pacing`, `impressions`, `start_time`, `end_time` and no per-day limit, with its `allOf` (core/version-envelope.json), `dependencies` (`params` → `format_kind`) and `not` (bans `capability_ids`) contributing none — repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json. Daily spend appears in the pinned material only as non-normative background, never as a protocol field or a graded check: an illustrative implementer JS snippet comparing `budget.amount` to an out-of-band `limits.daily_spend_limit` (building/by-layer/L1/security.mdx:1724), brief-authoring guidance listing "Daily budget: Maximum daily spend" as something a buyer may say in prose (media-buy/product-discovery/brief-expectations.mdx:157), and one storyboard narrative describing a buyer "changing daily spend caps" through update_media_buy with no validation attached — repo=adcp ref=3.1.1 path=specialisms/sales-non-guaranteed/index.yaml. The nearest actual spec constructs are a per-package spend FLOOR, `min_spend_per_package` — repo=adcp ref=3.1.1 path=schemas/pricing-options/cpm-option.json — and the seller-minimum error BUDGET_TOO_LOW pointing at `capabilities.media_buy.limits` — repo=adcp ref=3.1.1 path=schemas/manifest.json. The `budget / max(1, flight_days)` derivation, the cap comparison, and the skip-when-unconfigured behavior are entirely our tenant policy; this obligation grades our production behavior, not AdCP conformance.

---

### start_time: Start Time Validation
**Obligation ID** CONSTR-START-TIME-01
**Layer** behavioral
**Requirement:** Required. "asap" (case-sensitive) = current UTC. Must be future. Naive = UTC.
**Scenario:**
```gherkin
Given start_time in the past
Then rejected

Given start_time="asap"
Then resolves to now
```
**Priority:** P0
**Grounded at 3.1.1:** Three of the four sub-claims hold; two details are ours. Required: `start_time` is in `create-media-buy-request.json`'s `required: [idempotency_key, account, brand, start_time, end_time]` — repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json. Case-sensitive "asap": StartTiming is a two-branch `oneOf` — `{"const": "asap"}` (a JSON Schema `const`, so byte-exact and case-sensitive) or a `format: date-time` string — with no third branch — repo=adcp ref=3.1.1 path=schemas/core/start-timing.json. Both forms are graded: a dedicated scenario exists specifically to catch wrapper-layer rejection of the literal, requiring that "The seller MUST accept start_time: 'asap' (string literal) without rejecting it at the wrapper/input-validation layer" — repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/proposal_finalize_asap_timing.yaml, mirrored at repo=adcp ref=3.1.1 path=protocols/media-buy/scenarios/proposal_finalize_asap_timing.yaml. Past rejection holds, but the pinned wording is "not in the past" (so start_time == now is acceptable), not "must be future": create_media_buy.mdx §Flight date validation says a past concrete `start_time` MUST return INVALID_REQUEST. Spec-silent: nothing at 3.1.1 says "asap" RESOLVES to the current UTC instant (StartTiming only says "Start campaign as soon as possible"), and nothing coerces a timezone-naive datetime to UTC — `format: date-time` implies an offset, and a search for naive/timezone-default prose across dist/docs/3.1.1 found no such rule. Those two are our own semantics.

---

### end_time: End Time Validation
**Obligation ID** CONSTR-END-TIME-01
**Layer** schema
**Requirement:** Required. Must be strictly after start_time. Naive = UTC.
**Scenario:**
```gherkin
Given end_time = start_time
Then rejected (must be strictly after)
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED — two of the three claims hold, and the ordering half is storyboard-graded rather than schema-encoded. `end_time` IS required: `repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json` lists it in `required: [idempotency_key, account, brand, start_time, end_time]`, typed `{"type":"string","format":"date-time"}`. (a) Ordering is not expressible in the schema — the request's only composition is `allOf: [core/version-envelope.json]`, contributing solely `adcp_version`/`adcp_major_version` (`repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json`); its only `dependencies` entry is `proposal_id → total_budget`; there is no root `if`/`then`; and the comparison is not always well-formed because `start_time` is `repo=adcp ref=3.1.1 path=schemas/core/start-timing.json`, a `oneOf` of the literal `"asap"` or an ISO 8601 date-time. But the constraint IS an AdCP obligation at the storyboard layer: `repo=adcp ref=3.1.1 path=universal/schema-validation.yaml` § `temporal_validation` step `reversed_dates` sends `start_time: 2099-12-31 / end_time: 2099-01-01` and requires rejection with `INVALID_REQUEST`, and `repo=adcp ref=3.1.1 path=universal/error-compliance.yaml` step `reversed_dates_error` grades the same case with `error_code ∈ {VALIDATION_ERROR, INVALID_REQUEST}` and `recovery: correctable` (VALIDATION_ERROR canonical). Both grade end BEFORE start; the equality boundary (`end_time == start_time`) is still ungraded, as is the package-level rule, which is descriptive only — `repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json` says a package's `start_time`/`end_time` "Must fall within the media buy's date range" without schema enforcement. (b) No naive-datetime→UTC rule appears anywhere in the bundle; `format: date-time` (RFC 3339) requires an explicit offset, so accepting a naive value at all is our own leniency. Net: `Required` is schema-graded, `end after start` is storyboard-graded (INVALID_REQUEST / VALIDATION_ERROR, correctable), and only the equality boundary and `naive = UTC` grade our own production validation.

---

### creative_replacement: Creative Replacement Semantics
**Obligation ID** CONSTR-CREATIVE-REPLACEMENT-01
**Layer** behavioral
**Requirement:** creative_ids/creative_assignments replaces all existing. Not a merge.
**Scenario:**
```gherkin
Given existing [A,B,C] and update provides [B,D]
Then result is [B,D]; A,C deleted
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED — the replacement semantic holds, the field name does not. `repo=adcp ref=3.1.1 path=schemas/media-buy/package-update.json` defines `creative_assignments` as "Replace creative assignments for this package with optional weights and placement targeting. Uses replacement semantics - omit to leave assignments unchanged", and `creatives` as "Replace this package's inline creative assets" — so `[A,B,C]` updated with `[B,D]` yields `[B,D]`, not a merge. The pin makes the distinction deliberately: in the same schema `negative_keywords_add` "Appends to the existing negative keyword list — does not replace it" and `keyword_targets_add` "Upserts by (keyword, match_type) identity", so replace-vs-append is an expressed choice, not an accident. But there is no `creative_ids` field on the media-buy write path: `package-update.json` composes nothing at its root (no `allOf`/`oneOf`/`anyOf`/`$ref` — only a `not: anyOf[...]` barring the immutable fields), so its listed properties are the complete set, and `repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json` likewise carries `creative_assignments`/`creatives` and no `creative_ids`. The name `creative_ids` survives at 3.1.1 only as a read/sync-side filter — `repo=adcp ref=3.1.1 path=schemas/core/creative-filters.json` — not as an assignment payload. Restate the obligation against `creative_assignments` (and `creatives`).

---

### creative_state_validation: Creative State + Format Compatibility
**Obligation ID** CONSTR-CREATIVE-STATE-VALIDATION-01
**Layer** behavioral
**Requirement:** error/rejected state cannot be assigned. Format must be compatible with product.
**Scenario:**
```gherkin
Given creative in "error" state
Then assignment rejected with INVALID_CREATIVES
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED — the format half is grounded, the state half and the error code are not. There is no `error` creative state at 3.1.1: `repo=adcp ref=3.1.1 path=schemas/enums/creative-status.json` is a flat 6-value enum — `processing, pending_review, approved, suspended, rejected, archived` — and `rejected` is documented as "Not terminal — the buyer may fix the issue and resubmit via sync_creatives". `INVALID_CREATIVES` is not a pinned code: `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json` is a flat 92-value enum that does not contain it (the code vocabulary is open — sellers MAY return unlisted codes — but nothing in 3.1.1 mandates this one). More importantly the pin models a non-serviceable creative on a live buy the opposite way from this obligation: not as an assignment-time refusal but as an open impairment — creative-status.json states "Sellers MUST surface a corresponding impairment on any active media buy that references this creative" for `approved → suspended` and `approved → rejected`, and `repo=adcp ref=3.1.1 path=schemas/core/impairment.json` carries `resource_type` including `creative`, graded by `repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/dependency_impairment.yaml`. Assigning a creative that is not yet approved is explicitly a supported flow, not an error — `repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/pending_creatives_to_start.yaml`. The format-compatibility half does have a pinned counterpart: `repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json` requires the package's selected formats to be "supported by the product" with directional product satisfaction, and mandates rejection with `UNSUPPORTED_FEATURE` (with `error.field` pointing at the failing package entry) when the selector does not resolve against the product's `format_options[]`.

---

### placement_id_validation: Placement ID Validation
**Obligation ID** CONSTR-PLACEMENT-ID-VALIDATION-01
**Layer** behavioral
**Requirement:** All placement_ids must be valid for product. Product without placement support rejects placement_ids.
**Scenario:**
```gherkin
Given invalid placement_id for product
Then rejected with invalid_placement_ids
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — the premise is pinned, the rejection rule and the error identifier are not. Placement selection really is scoped to the product's declared placements: `repo=adcp ref=3.1.1 path=schemas/core/creative-assignment.json` says `placement_refs` "References entries from the product's `placements[]` array by `{ publisher_domain, placement_id }`" and `placement_ids` is its "Legacy shorthand" (with `placement_refs` winning and receivers MUST-ignoring `placement_ids` when both are present), and `repo=adcp ref=3.1.1 path=schemas/core/product.json` requires each product placement to declare `mode: 'targetable'` ("buyer may select the placement by PlacementRef") or `mode: 'included'` ("not buyer-selectable"). But nothing in the pin obliges a seller to REJECT an unrecognized `placement_id`, and nothing says a product with no `placements[]` must reject the field — `placements` is optional on the product and `placement_ids` is documented only as narrowing within already-purchased inventory, defaulting to "all buyer-targetable placements in the package" when omitted. `invalid_placement_ids` is not an AdCP error identifier: `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json` (flat 92-value enum, no composition) has no such member and its codes are SCREAMING_SNAKE; the generic fallbacks a seller would actually use are `REFERENCE_NOT_FOUND` ("Typed parameters that lack a dedicated standard code MUST also use REFERENCE_NOT_FOUND rather than minting a custom *_NOT_FOUND code") or `VALIDATION_ERROR`. The behavior is also entirely ungraded: the substring `placement_id` does not appear in any of the 286 files of the pinned compliance tree. This obligation therefore grades our own validation choice and, if kept, must not demand a `invalid_placement_ids` code.

---

### approval_workflow: Approval Workflow Determination
**Obligation ID** CONSTR-APPROVAL-WORKFLOW-01
**Layer** behavioral
**Requirement:** Dual-flag: tenant human_review_required (default true) + adapter manual_approval_required. Either true = pending.
**Scenario:**
```gherkin
Given both flags false
Then auto-approved
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED (not spec-silent) — our two field names are ours, but the pin does define and grade a seller-side approval-mode declaration. Neither `manual_approval_required` nor a tenant-level `human_review_required` exists in the bundle (zero hits for `manual_approval` and `approval_required`; `human_review` appears only governance-side, e.g. the boolean `requires_human_review` in `repo=adcp ref=3.1.1 path=schemas/governance/policy-entry.json`). But the pinned analogue of our tenant flag is `repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json` → `media_buy.creative_approval_mode`, `enum: [auto_approve, require_human]`: "Tenant-wide applicability signal for media-buy creative approval behavior… `require_human` means one or more products/accounts may require manual review before creatives become eligible to serve… When absent, approval behavior is legacy-unspecified". It is load-bearing in compliance: `repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/pending_creatives_to_start.yaml`, `domains/media-buy/scenarios/available_actions.yaml` and `domains/media-buy/state-machine.yaml` (and their `protocols/media-buy/` twins) all gate on `requires_capability: path: media_buy.creative_approval_mode`. What remains genuinely ours is the dual-flag composition (per-object `manual_approval_required` OR tenant `human_review_required`) and its resolution rule. Two AdCP-facing constraints bind it: (1) the resulting status must stay inside the 7-value `repo=adcp ref=3.1.1 path=schemas/enums/media-buy-status.json` enum — `repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-response.json` states outright "Do not use a 'pending_approval' MediaBuy.status for this case — that value is not in MediaBuyStatus; IO review and similar pre-issuance workflows are modeled at the task layer only", so a pause is expressed as the async task envelope `repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-async-response-input-required.json` ("Payload when task is paused waiting for user input or approval"); and (2) whatever our flags resolve to must be advertised truthfully as `creative_approval_mode`, since storyboards select on it.

---

### media_buy_resolution: Media Buy Resolution (OR)
**Obligation ID** CONSTR-MEDIA-BUY-RESOLUTION-01
**Layer** behavioral
**Requirement:** Optional media_buy_ids (priority), buyer_refs (fallback), neither = all. Partial resolution, zero results = empty array.
**Scenario:**
```gherkin
Given neither media_buy_ids nor buyer_refs
Then all principal's media buys returned
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED — two of four claims survive. `media_buy_ids` is optional (`repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buys-request.json`, array of media-buy-id strings, `minItems: 1`, absent from any `required`), and zero results really is an empty array: `repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buys-response.json` puts `media_buys` in `required` with no `minItems`, so `[]` is a valid successful response. Partial resolution is supported the same way — that response carries `errors` typed as "Task-specific errors (e.g., media buy not found)", i.e. unknown ids surface per-item rather than failing the call. The `buyer_refs` fallback is gone: the request composes only `allOf: [core/version-envelope.json]` and declares no `buyer_refs`, and the token `buyer_refs` appears nowhere in the bundle; the singular `buyer_ref` survives only in `repo=adcp ref=3.1.1 path=schemas/core/mcp-webhook-payload.json`, and `repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json` explicitly redirects correlation to `context` — "Do not use deprecated top-level buyer_ref for v3 correlation". And "neither = all" is false: the request says "When omitted, returns a paginated set of accessible media buys matching status_filter", with `status_filter` "Defaults to [\"active\"] when media_buy_ids is omitted. When media_buy_ids is provided, no implicit status filter is applied" — so the no-selector default is active-only-and-paginated, not all.

---

### delivery_date_range: Delivery Date Range
**Obligation ID** CONSTR-DELIVERY-DATE-RANGE-01
**Layer** schema
**Requirement:** start_date < end_date. Both omitted = full campaign range.
**Scenario:**
```gherkin
Given start_date = end_date
Then rejected (zero-length period)
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — the omission default holds, the strict-inequality rule does not. `repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buy-delivery-request.json` states for both `start_date` and `end_date`: "When omitted along with [the other], returns campaign lifetime data" — so "both omitted = full campaign range" is pinned. The `start_date < end_date` rule is not: both fields are plain day-granularity strings constrained only by `pattern: ^\\d{4}-\\d{2}-\\d{2}$`, the request's only root composition is `allOf: [core/version-envelope.json]` (contributing only the two version fields), and the schema's other `allOf` blocks live inside `reporting_dimensions.geo` and are conditionals on `geo_level` alone — nothing anywhere relates the two dates. The scenario is additionally wrong on its own terms: because these are whole-day dates, `start_date == end_date` denotes a single reporting day, not a zero-length period, and rejecting it would deny same-day reporting. The one real gate the pin does put on these fields is capability-based, not ordering-based — "Only accepted when the product's `reporting_capabilities.date_range_support` is 'date_range'", per `repo=adcp ref=3.1.1 path=schemas/core/reporting-capabilities.json` (`enum: [date_range, lifetime_only]`, default `date_range`); a `lifetime_only` seller MUST NOT accept them at all. Ordering validation grades our own production behavior.

---

### format_type_filter: Format Type Filter
**Obligation ID** CONSTR-FORMAT-TYPE-FILTER-01
**Layer** schema
**Requirement:** FormatCategory enum (audio, video, display, native, dooh, rich_media, universal). Exact match.
**Scenario:**
```gherkin
Given type_filter="display"
Then only display formats returned
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — a type filter exists, but not with this name, not with this enum, and not on this surface. There is no `type_filter` anywhere in the pinned bundle. On the seller/media-buy surface our agent implements, `repo=adcp ref=3.1.1 path=schemas/media-buy/list-creative-formats-request.json` has no type or category filter at all — its complete filter set is `format_ids, asset_types, max_width, max_height, min_width, min_height, is_responsive, name_search, publisher_domain, property_id, wcag_level, disclosure_positions, disclosure_persistence, output_format_ids, input_format_ids, pagination, context, ext`, and its only root composition is `allOf: [core/version-envelope.json]`, so that list is complete. The creative-agent twin does carry one: `repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json` declares `type` — "Filter by format type (technical categories with distinct requirements)" — with `enum: [audio, video, display, dooh]`. That is four values, not seven: `native`, `rich_media` and `universal` are absent from the pin (`rich_media` and a `"universal"` category string return zero hits bundle-wide). There is also no `FormatCategory` type to point at — `repo=adcp ref=3.1.1 path=schemas/core/format.json` has no `type` or `category` property and its single `allOf` is an `if/then` on `canonical_parameters` that contributes no fields. `type="display" → only display formats` is a defensible restatement only against the creative-agent request; against the media-buy request it is grading a filter the pin does not define.

---

### format_ids_filter: Format IDs Filter
**Obligation ID** CONSTR-FORMAT-IDS-FILTER-01
**Layer** behavioral
**Requirement:** Array of FormatId. Matches on id field. Non-matching silently excluded.
**Scenario:**
```gherkin
Given format_ids=["fmt_1", "fmt_nonexistent"]
Then only fmt_1 returned (fmt_nonexistent silently excluded)
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — the field and its type hold, the match rule is wrong, and only the miss behavior is unpinned. The filter exists: `repo=adcp ref=3.1.1 path=schemas/media-buy/list-creative-formats-request.json` declares `format_ids` as an array (`minItems: 1`) of `core/format-id.json`, "Return only these specific format IDs (e.g., from get_products response)". But "matches on id field" is false — `repo=adcp ref=3.1.1 path=schemas/core/format-id.json` is "A JSON object — never a plain string" with `required: [agent_url, id]`, and mandates "Callers comparing two `format-id` values MUST canonicalize `agent_url` per the AdCP URL canonicalization rules before treating two formats as the same". Identity is the canonicalized `(agent_url, id)` pair; `id` alone is only namespace-local (`pattern: ^[a-zA-Z0-9_-]+$`), so the scenario's bare strings `["fmt_1", "fmt_nonexistent"]` are themselves schema violations and cannot be graded as written. That whole-object match rule is actively graded: `repo=adcp ref=3.1.1 path=universal/schema-validation.yaml` step `list_formats_match` sends `format_ids: [$context.product_format_id]` and requires `field_value formats[0].format_id == $context.product_format_id` ("Filtered format response returns the product's exact format_id"), with `format_id.agent_url` and `format_id.id` both required present. What is NOT pinned is filter-MISS behavior: neither request schema says what happens to an unmatched entry, no scenario sends a non-existent format_id, and the tool's other coverage grades orthogonal invariants — `repo=adcp ref=3.1.1 path=universal/pagination-integrity-creative-formats.yaml` grades only cursor↔has_more, `repo=adcp ref=3.1.1 path=universal/read-tool-idempotency.yaml` only read-idempotency. So silent exclusion grades our own behavior; the `(agent_url, id)` match rule is AdCP-graded and the obligation must be restated to it.

---

### dimension_filter: Dimension Filter
**Obligation ID** CONSTR-DIMENSION-FILTER-01
**Layer** behavioral
**Requirement:** min/max width/height. ANY render match semantics. Formats without dimension info excluded.
**Scenario:**
```gherkin
Given min_width=300 and max_width=728
Then formats where ANY render has width in [300,728] are returned
```
**Priority:** P3
**Grounded at 3.1.1:** CORRECTED — the ANY-render semantics is pinned verbatim; the exclusion rule is not. `repo=adcp ref=3.1.1 path=schemas/media-buy/list-creative-formats-request.json` defines all four bounds with explicit any-render language: `max_width` — "Maximum width in pixels (inclusive). Returns formats where ANY render has width <= this value. For multi-render formats, matches if at least one render fits"; `min_width` — "Returns formats where ANY render has width >= this value"; same for `max_height`/`min_height`. So `min_width=300, max_width=728` returning formats where any render's width falls in `[300,728]` is exactly the pinned rule. Note the surface split: the creative-agent twin `repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json` states the weaker plain form — "Returns formats with width <= this value. Omit for responsive/fluid formats" — with no ANY-render clause, so the obligation is only literally true against the media-buy request. "Formats without dimension info excluded" is not stated anywhere: the media-buy request composes only `allOf: [core/version-envelope.json]`, so its property set is complete and contains no such rule, and the nearest thing is the separate opt-in `is_responsive` ("When true, returns formats without fixed dimensions") — a distinct filter, not an exclusion clause on the bounds. Dimensions live in the optional `renders[]` array of `repo=adcp ref=3.1.1 path=schemas/core/format.json` (whose `required` is only `[format_id, name]`), so a dimensionless format is well-formed and the pin simply does not say how the bounds treat it. That sub-claim grades our own behavior.

---

### is_responsive_filter: Responsive Filter
**Obligation ID** CONSTR-IS-RESPONSIVE-FILTER-01
**Layer** schema
**Requirement:** Boolean. true=only responsive. false=only non-responsive. Omitted=all.
**Scenario:**
```gherkin
Given is_responsive=true
Then only formats with at least one responsive render returned
```
**Priority:** P3
**Grounded at 3.1.1:** Partly true. `is_responsive` is a boolean filter on `list_creative_formats` — `"is_responsive": {"type": "boolean", "description": "Filter for responsive formats that adapt to container size. When true, returns formats without fixed dimensions."}` (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json). Two parts of the obligation are NOT what 3.1.1 says: (a) the true-branch is defined as "formats without fixed dimensions", not "at least one responsive render" — responsiveness is a per-render property (`renders[].dimensions.responsive` with required `width`/`height` booleans, alongside `min_width`/`max_width`/`min_height`/`max_height` "for responsive renders", repo=adcp ref=3.1.1 path=schemas/core/format.json), and the only "any render matches" rule stated for this request is on the dimension filters, not on `is_responsive`; (b) the `false` and omitted semantics ("false=only non-responsive, omitted=all") are stated nowhere at 3.1.1 — the request schema (whose `allOf` resolves to `core/version-envelope.json`, which contributes only `adcp_version`/`adcp_major_version`, plus an `if/then` conditional on `include_pricing` that contributes no filter fields) says nothing, and the compliance tree contains no `is_responsive` step at all. Those two sub-claims grade our own filter behavior, not AdCP conformance.

---

### name_search_filter: Name Search Filter
**Obligation ID** CONSTR-NAME-SEARCH-FILTER-01
**Layer** behavioral
**Requirement:** Case-insensitive substring match on format name.
**Scenario:**
```gherkin
Given name_search="BANNER"
Then formats with "banner" in name returned (case-insensitive)
```
**Priority:** P3
**Grounded at 3.1.1:** True. `name_search` is defined as `{"type": "string", "description": "Search for formats by name (case-insensitive partial match)"}` on the `list_creative_formats` request (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json), and the docs request-parameter table repeats it verbatim (repo=adcp ref=3.1.1 path=../../docs/3.1.1/creative/task-reference/list_creative_formats.mdx) — "case-insensitive partial match" on the format name is exactly the obligation's case-insensitive substring match, so `name_search="BANNER"` matching a format named "...banner..." is required behavior. The filter is also exercised in the graded tree: both pages of the creative-formats pagination storyboard scope their request with `name_search: "Pagination Integrity Format"` against exactly two seeded formats, and the terminal page asserts `pagination.has_more: false` — which only passes if the agent narrowed the catalog to the two matching names (repo=adcp ref=3.1.1 path=universal/pagination-integrity-creative-formats.yaml, steps `first_page` and `terminal_page`). Two caveats on how strongly it is graded: only `has_more` is pinned unconditionally — `total_count: 2` and the terminal `cursor: null` are `field_value_or_absent` checks that pass when the field is simply omitted — and the storyboard sends the term in its exact seeded case, so case-insensitivity itself is ungraded at 3.1.1.

---

### asset_types_filter: Asset Types Filter
**Obligation ID** CONSTR-ASSET-TYPES-FILTER-01
**Layer** schema
**Requirement:** OR semantics. Checks both individual and group assets. Enum: image, video, audio, text, etc.
**Scenario:**
```gherkin
Given asset_types=["image", "video"]
Then formats with either image OR video assets returned
```
**Priority:** P3
**Grounded at 3.1.1:** OR semantics is right; the rest is not. 3.1.1 states it normatively under "Asset Types Filter Logic": "The `asset_types` parameter uses **OR logic** - formats matching ANY specified asset type are returned" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/creative/task-reference/list_creative_formats.mdx). Note the request schema's own example text pulls the other way — "E.g., ['image', 'text'] returns formats with images and text" — so the schema alone would read as AND; the prose is the disambiguating authority, and the schema otherwise gives `type: array`, `items: $ref enums/asset-content-type.json`, `minItems: 1` (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json). Two corrections: (a) the enum is a closed 15-value list — `image, video, audio, text, markdown, html, css, javascript, vast, daast, url, webhook, brief, catalog, published_post` (repo=adcp ref=3.1.1 path=schemas/enums/asset-content-type.json) — so "image, video, audio, text, etc." understates it, and notably there is no `zip` member even though `core/format.json` defines an `IndividualZipAsset`; (b) "checks both individual and group assets" is spec-silent — `format.json` `assets[]` is a `oneOf` over fifteen `item_type: "individual"` branches plus one `RepeatableGroupAsset` (`item_type: "repeatable_group"`) (repo=adcp ref=3.1.1 path=schemas/core/format.json), but 3.1.1 nowhere says whether asset types nested inside a repeatable group satisfy the filter. That last part grades our own behavior.

---

### signal_catalog_types_filter: Signal Catalog Types Filter
**Obligation ID** CONSTR-SIGNAL-CATALOG-TYPES-FILTER-01
**Layer** schema
**Requirement:** Enum: marketplace, custom, owned. OR semantics within filter. minItems: 1.
**Scenario:**
```gherkin
Given catalog_types=["marketplace", "custom"]
Then signals of either type returned
```
**Priority:** P2
**Grounded at 3.1.1:** The shape holds, the semantics claim does not. `catalog_types` is `{"type": "array", "description": "Filter by catalog type", "items": {"$ref": "enums/signal-catalog-type.json"}, "minItems": 1}` and it lives under `get_signals`'s `filters` object, not at request top level (repo=adcp ref=3.1.1 path=schemas/core/signal-filters.json, reached via the `filters` property of repo=adcp ref=3.1.1 path=schemas/signals/get-signals-request.json). The enum is exactly `marketplace`, `custom`, `owned` (repo=adcp ref=3.1.1 path=schemas/enums/signal-catalog-type.json), so that part and `minItems: 1` are correct. "OR semantics within filter" is spec-silent: `signal-filters.json` has no `allOf`/`oneOf`/`anyOf`/`$ref` composition on this property, its description is the bare "Filter by catalog type", and no storyboard in the compliance tree sends `catalog_types` at all — so the OR reading grades our own filter, not AdCP conformance.

---

### signal_max_cpm_filter: Signal Max CPM Filter
**Obligation ID** CONSTR-SIGNAL-MAX-CPM-FILTER-01
**Layer** schema
**Requirement:** Number, minimum: 0. Signals with cpm > max_cpm excluded.
**Scenario:**
```gherkin
Given max_cpm=0
Then only free signals returned

Given max_cpm=-1
Then rejected (minimum: 0)
```
**Priority:** P2
**Grounded at 3.1.1:** The bounds hold, the exclusion rule is narrower than claimed. `filters.max_cpm` is `{"type": "number", "description": "Maximum CPM filter. Applies only to signals with model='cpm'.", "minimum": 0}` (repo=adcp ref=3.1.1 path=schemas/core/signal-filters.json) — so "number, minimum 0" is right and `max_cpm=-1` is a schema violation. But "signals with cpm > max_cpm excluded" overreaches: at 3.1.1 the filter applies ONLY to signals whose pricing model is `cpm`, so a signal with no CPM-model pricing option is untouched by the filter and is still returned; therefore the scenario's `max_cpm=0 → only free signals returned` is not an AdCP obligation. The only graded use in the pinned tree sends `filters: {max_cpm: 5.00}` with `signal_spec: "Purchase behavior signals"` and expects "Return only signals matching the filter criteria. If no signals match, return an empty signals array — not an error", but its `validations` only assert `response_schema`, presence of `signals`, and context echo — the per-signal price exclusion itself is ungraded (repo=adcp ref=3.1.1 path=specialisms/signal-owned/index.yaml, step `filter_by_criteria`).

---

### signal_min_coverage_filter: Signal Min Coverage Filter
**Obligation ID** CONSTR-SIGNAL-MIN-COVERAGE-FILTER-01
**Layer** schema
**Requirement:** Number, 0-100. Signals with coverage < threshold excluded.
**Scenario:**
```gherkin
Given min_coverage=100
Then only full-coverage signals returned

Given min_coverage=101
Then rejected (maximum: 100)
```
**Priority:** P2
**Grounded at 3.1.1:** The bounds are right but the field name is wrong, and that inverts the rejection scenario. The pinned field is `filters.min_coverage_percentage`: `{"type": "number", "description": "Minimum coverage requirement", "minimum": 0, "maximum": 100}` (repo=adcp ref=3.1.1 path=schemas/core/signal-filters.json). There is no `min_coverage` property at 3.1.1, and `signal-filters.json` sets `"additionalProperties": true` with no `allOf`/`oneOf`/`anyOf` composition — so a request carrying `min_coverage: 101` is SCHEMA-VALID at 3.1.1 and would not be rejected; only `min_coverage_percentage: 101` violates `maximum: 100`. The exclusion semantics ("signals with coverage < threshold excluded") is spec-silent beyond the one-line "Minimum coverage requirement" — and note the scalar it filters on is itself legacy: `coverage_percentage` is "DEPRECATED for detailed planning ... retained only as a fallback ... When coverage_forecast is present, coverage_forecast is authoritative" (repo=adcp ref=3.1.1 path=schemas/signals/get-signals-response.json). No storyboard in the pinned tree exercises this filter.

---

### signal_max_results: Signal Max Results
**Obligation ID** CONSTR-SIGNAL-MAX-RESULTS-01
**Layer** schema
**Requirement:** Integer, minimum: 1. Applied as array slice after filtering.
**Scenario:**
```gherkin
Given max_results=0
Then rejected (minimum: 1)

Given max_results=5 and 10 signals match
Then only 5 returned
```
**Priority:** P2
**Grounded at 3.1.1:** Half true, and the "array slice" mechanism is explicitly non-conformant. The top-level `max_results` on `get_signals` still has `minimum: 1` (so `max_results=0` is rejected) but is `"deprecated": true` at 3.1.1: "DEPRECATED: Use pagination.max_results instead. When both fields are present, agents MUST honor pagination.max_results. When only this field is present without a pagination envelope, agents SHOULD treat it as the page size subject to a maximum of 100 results. This field will be removed in AdCP 4.0" (repo=adcp ref=3.1.1 path=schemas/signals/get-signals-request.json). The live field is `pagination.max_results`: `{"type": "integer", "minimum": 1, "maximum": 100, "default": 50}` (repo=adcp ref=3.1.1 path=schemas/core/pagination-request.json, `additionalProperties: false`). "Applied as array slice after filtering" is wrong as stated: page size is cursor-paginated, not truncating — with `pagination.max_results: 1` against a broader match set "Conformant agents MUST report `has_more: true` with a `cursor` on this page — an agent that caps internally and reports `has_more: false` while more candidates match" is the graded failure (repo=adcp ref=3.1.1 path=universal/get-signals-pagination-integrity.yaml, step `first_page`). So the scenario's "max_results=5 and 10 signals match → only 5 returned" holds only if the response also carries `has_more: true` plus a cursor. What is NOT graded is the continuation: the follow-up step `next_page` follows the captured cursor but the storyboard states "The terminal state of this page depends on the agent's signal set size ... so we do not pin `has_more` here", and its validations are `response_schema` plus context echo only — returning the remainder is unenforced at 3.1.1.

---

### signal_agent_segment_id: Signal Agent Segment ID
**Obligation ID** CONSTR-SIGNAL-AGENT-SEGMENT-ID-01
**Layer** behavioral
**Requirement:** Required for activate_signal. Premium IDs (prefix "premium_") trigger APPROVAL_REQUIRED. Auth required.
**Scenario:**
```gherkin
Given signal_id="premium_auto_intenders"
Then APPROVAL_REQUIRED returned

Given no authentication
Then ToolError for missing auth
```
**Priority:** P2
**Grounded at 3.1.1:** Required-ness and auth hold; the APPROVAL_REQUIRED clause does not. `signal_agent_segment_id` is in `"required": ["idempotency_key", "signal_agent_segment_id", "destinations"]` on the activate request, described as the "Opaque activation handle returned in the signal_agent_segment_id field of each get_signals response entry. Pass this string verbatim — do not pass the signal_id object" (repo=adcp ref=3.1.1 path=schemas/signals/activate-signal-request.json); omitting it is graded — step `missing_required_field` requires rejection with `INVALID_REQUEST` or `VALIDATION_ERROR`, `recovery: correctable` (repo=adcp ref=3.1.1 path=universal/error-compliance-signals.yaml). Auth is grounded generically, not per-field: "Every AdCP agent MUST require authentication on protected operations" (repo=adcp ref=3.1.1 path=universal/security.yaml), and `activate_signal` is `x-mutates-state: true`. The "premium_ prefix triggers APPROVAL_REQUIRED" rule is spec-silent — it is our fixture convention, not AdCP: the activate response composes to `allOf(core/version-envelope.json, core/protocol-envelope.json)` plus a two-branch `oneOf` of ActivateSignalSuccess (`required: [deployments]`) and ActivateSignalError (`required: [errors]`) with no approval arm (repo=adcp ref=3.1.1 path=schemas/signals/activate-signal-response.json), and the only `APPROVAL_REQUIRED` occurrence in the envelope is inside the non-normative `examples` array for a media-buy input-required response (repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json).

---

### signal_data_providers_filter: Signal Data Providers Filter
**Obligation ID** CONSTR-SIGNAL-DATA-PROVIDERS-FILTER-01
**Layer** behavioral
**Requirement:** Array of strings. OR semantics. Case-sensitive match.
**Scenario:**
```gherkin
Given data_providers=["Oracle", "LiveRamp"]
Then signals from either provider returned
```
**Priority:** P3
**Grounded at 3.1.1:** The shape holds; both semantic claims are spec-silent. `filters.data_providers` is `{"type": "array", "description": "Filter by specific data providers", "items": {"type": "string"}, "minItems": 1}` (repo=adcp ref=3.1.1 path=schemas/core/signal-filters.json), reached from the `filters` property of the request, which is a bare `$ref` to that file carrying no description of its own (repo=adcp ref=3.1.1 path=schemas/signals/get-signals-request.json). The only behavioral hint at 3.1.1 is in prose, not schema: filters "constrain the enumerated signals feed (e.g., `filters.data_providers: [\"acme-data\"]` returns only that provider's signals)" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/signals/tasks/get_signals.mdx) — and that example is single-element, so it says nothing about how multiple providers combine. Nothing at 3.1.1 states OR-across-elements, and nothing states case sensitivity of the provider match; the property has no `allOf`/`oneOf`/`anyOf` composition that could carry such a rule, and no storyboard in the pinned compliance tree sends `data_providers` (the only tree occurrences are the `data_providers:` fixture roster in repo=adcp ref=3.1.1 path=universal/fictional-entities.yaml and a pointer comment in test-kits/nova-motors.yaml, which define entities rather than filter semantics). Both the OR reading and the case-sensitive match therefore grade our own filter implementation.

---

### signal_spec: Signal Spec Query
**Obligation ID** CONSTR-SIGNAL-SPEC-01
**Layer** schema
**Requirement:** Natural language string. Case-insensitive substring match against name/description/type. Required if signal_ids omitted (anyOf).
**Scenario:**
```gherkin
Given signal_spec="auto intenders" and no signal_ids
Then signals matching "auto intenders" in name/description returned

Given neither signal_spec nor signal_ids
Then schema validation rejects (anyOf violation)
```
**Priority:** P2
**Grounded at 3.1.1:** The field and its conditional requirement are real, but both details are stale. `signal_spec` is "Natural language description of the desired signals ... MUST NOT be provided when discovery_mode is 'wholesale'" (repo=adcp ref=3.1.1 path=schemas/signals/get-signals-request.json). The anyOf is no longer top-level and no longer a two-way choice against `signal_ids`: it sits in the `else` (brief-mode) branch of the request's `discovery_mode` conditional — `"anyOf": [{"required": ["signal_spec"]}, {"required": ["signal_refs"]}, {"required": ["signal_ids"]}]` — so `signal_refs` (the successor; `signal_ids` is `"deprecated": true`) also satisfies it, and in the `then` (wholesale) branch all three MUST be absent, making "neither signal_spec nor signal_ids → rejected" true only for `discovery_mode: "brief"`. "Case-insensitive substring match against name/description/type" is NOT the pinned semantic: brief mode is defined as "semantic discovery ... the agent performs inference/RAG" (same schema, `discovery_mode` description), and the graded step reads "The buyer describes a target audience in natural language. The agent returns a list of signals from its catalog that match" with validations on response schema and identity/pricing fields, not on substring behavior (repo=adcp ref=3.1.1 path=domains/signals/index.yaml, step `search_signals`). The substring rule grades our own matcher.

---

### signal_deliver_to: Signal Delivery Targets
**Obligation ID** CONSTR-SIGNAL-DELIVER-TO-01
**Layer** schema
**Requirement:** Required object with deployments (minItems: 1) and countries (minItems: 1, pattern ^[A-Z]{2}$).
**Scenario:**
```gherkin
Given countries=["us"] (lowercase)
Then rejected (pattern requires uppercase)

Given deployments=[]
Then rejected (minItems: 1)
```
**Priority:** P2
**Grounded at 3.1.1:** RETIRED — there is no `deliver_to` object at 3.1.1. The nested wrapper was flattened to two top-level fields (`deliver_to.destinations` → `destinations`, `deliver_to.countries` → `countries`) per the "Deliver-to flattening" table (repo=adcp ref=3.1.1 path=../../docs/3.1.1/reference/migration/signals.mdx). In repo=adcp ref=3.1.1 path=schemas/signals/get-signals-request.json both replacements are OPTIONAL — neither appears in any `required` list; the only conditional requirements are the brief/wholesale `if/then/else` on signal_spec/signal_refs/signal_ids — so "Required object" is false at the pin. The two sub-constraints do survive on the flattened fields: `countries.items` carries `"pattern": "^[A-Z]{2}$"` with `minItems: 1` (so `["us"]` is still rejected), and `destinations` carries `minItems: 1`. But there is no `deployments` request field at all — `deployments` exists only as a projectable response value in the `fields` enum. Composition resolved before asserting absence: the request's `allOf` is core/version-envelope.json plus an `if/then` on wholesale feed-version tokens, and the root `if/then/else` + `dependencies` — none contribute a deliver_to or deployments member.

---

### format_id_structure: Format ID Object Structure
**Obligation ID** CONSTR-FORMAT-ID-STRUCTURE-01
**Layer** schema
**Requirement:** Object with required agent_url (URI) and id (string). Not a plain string.
**Scenario:**
```gherkin
Given format_id as plain string "banner_300x250"
Then rejected (must be object with agent_url + id)

Given format_id={agent_url: "http://agent.com", id: "banner_300x250"}
Then valid
```
**Priority:** P0
**Grounded at 3.1.1:** HOLDS. repo=adcp ref=3.1.1 path=schemas/core/format-id.json is `"type": "object"` with `"required": ["agent_url", "id"]`; `agent_url` is `{"type":"string","format":"uri"}` and `id` is `{"type":"string","pattern":"^[a-zA-Z0-9_-]+$"}`. Its title is "Format Reference (Structured Object)" and the description states the rejection branch verbatim: "A JSON object — never a plain string" and "Using a plain string here is a schema violation." Both scenario branches therefore grade exactly as written. Composition resolved: the schema declares no allOf/oneOf/anyOf/$ref — all properties are inline — so nothing relaxes the object requirement. The pin is marginally stronger than the obligation states: `id` is pattern-constrained, and optional parameterization via width/height/duration_ms is permitted with a width⇄height `dependencies` pair.

---

### principal_ownership: Principal Ownership Verification
**Obligation ID** CONSTR-PRINCIPAL-OWNERSHIP-01
**Layer** behavioral
**Requirement:** Authenticated principal must match media buy owner. Mismatch = PermissionError or not_found.
**Scenario:**
```gherkin
Given principal_A tries to update media buy owned by principal_B
Then PermissionError or media_buy_not_found returned
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED. The ownership scoping half is grounded — repo=adcp ref=3.1.1 path=schemas/enums/error-code.json defines MEDIA_BUY_NOT_FOUND as "Referenced media buy does not exist **or is not accessible to the requesting agent**". But the obligation's disjunction "PermissionError **or** media_buy_not_found" is wrong at 3.1.1. The "Uniform response for inaccessible references" rule in repo=adcp ref=3.1.1 path=../../docs/3.1.1/building/by-layer/L3/error-handling.mdx requires that for every not-found code, MEDIA_BUY_NOT_FOUND included, "sellers MUST return the same response for 'exists but the caller lacks access' as for 'does not exist'. Never distinguish the two — this is how cross-tenant enumeration lands", with `error.code`/`message`/`field`/`details` byte-equivalent between the two cases and resolve-then-authorize latency parity on both paths. Emitting PERMISSION_DENIED on the cross-principal path while emitting MEDIA_BUY_NOT_FOUND on a true miss is exactly the oracle that rule closes, so the correct obligation is MEDIA_BUY_NOT_FOUND indistinguishable from the true-miss response — not "either code". Grading coverage: repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/invalid_transitions.yaml grades only the true-miss arm (phase `unknown_media_buy`, `expect_error: true`, expected `code: MEDIA_BUY_NOT_FOUND` / `recovery: correctable`); the resolve-then-deny arm is ungraded by any pinned storyboard.

---

### immutable_fields: Immutable Package Fields
**Obligation ID** CONSTR-IMMUTABLE-FIELDS-01
**Layer** behavioral
**Requirement:** product_id, format_ids, pricing_option_id not in update schema. Schema-enforced immutability.
**Scenario:**
```gherkin
Given update request with product_id in package payload
Then rejected by schema (field not present in update schema)
```
**Priority:** P1
**Grounded at 3.1.1:** HOLDS, and the pin is broader than the obligation states. repo=adcp ref=3.1.1 path=schemas/media-buy/package-update.json carries a root-level `"not": {"anyOf": [{"required":["product_id"]}, {"required":["format_ids"]}, {"required":["format_option_refs"]}, {"required":["format_kind"]}, {"required":["params"]}, {"required":["capability_ids"]}, {"required":["pricing_option_id"]}]}`, so all three named fields are schema-rejected in an update payload plus four more. Its description states the mechanism normatively: "Fully-immutable fields (product_id, format_ids, format_option_refs, format_kind, params, pricing_option_id) cannot appear in update payloads — schema-enforced via the `not` constraint at the root of this object." The obligation's phrasing "not in update schema" understates how it works: the schema is `additionalProperties: true` and these fields are simply absent from `properties`, so mere omission would NOT reject them — the `not` is what does. Composition resolved: package-update.json has no allOf/oneOf/anyOf/$ref of its own, and repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json reaches it via `packages.items.$ref` while composing only `allOf(core/version-envelope.json)`, contributing no relaxation.

---

### principal_id (sync_creatives): Authentication Context
**Obligation ID** CONSTR-PRINCIPAL-AUTHENTICATION-CONTEXT-01
**Layer** behavioral
**Requirement:** Required non-empty string from auth context. Used for creative isolation.
**Scenario:**
```gherkin
Given no authentication context
Then AUTH_REQUIRED error

Given empty principal_id string
Then AUTH_REQUIRED error
```
**Priority:** P0
**Grounded at 3.1.1:** CORRECTED. The "from auth context, never from the payload" half is strongly grounded: repo=adcp ref=3.1.1 path=../../docs/3.1.1/building/by-layer/L2/authentication.mdx states "AdCP resolves tenant from the authenticated principal, not from request payloads... Task payloads never carry tenant identifiers", and that buyer-principal credentials "MUST arrive on the transport's authentication channel and MUST NOT be placed in the task payload — top-level, inside `context`, inside `ext`, or in any other nested location... There is no AdCP version, capability, or seller policy under which a buyer principal authenticates via a payload field." Consistently, repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json declares no `principal_id` property (properties: account, creatives, creative_ids, assignments, delete_missing, dry_run, validation_mode, idempotency_key, push_notification_config, context, ext; `"required": ["idempotency_key","account","creatives"]`), and its only composition is `allOf(core/version-envelope.json)` which contributes just adcp_version/adcp_major_version — so creative isolation keys off the authenticated principal plus the `account` ref, never a request field. What is false is the demanded error code: repo=adcp ref=3.1.1 path=schemas/enums/error-code.json marks AUTH_REQUIRED "**Deprecated** — use `AUTH_MISSING` (no credentials presented) or `AUTH_INVALID` (credentials presented and rejected)", and says sellers "MUST return" AUTH_MISSING when no `Authorization` header was included. The "empty principal_id string" branch has no pinned counterpart at all (no such field exists); a credential smuggled into args is CREDENTIAL_IN_ARGS. repo=adcp ref=3.1.1 path=universal/security.yaml grades that protected operations including `sync_creatives` reject an unauthenticated call and a bad-credential call, but does not grade a specific code.

---

### media_buy_identification: XOR Identification
**Obligation ID** CONSTR-MEDIA-BUY-IDENTIFICATION-01
**Layer** schema
**Requirement:** Exactly one of media_buy_id or buyer_ref (oneOf). Both = rejected. Neither = rejected.
**Scenario:**
```gherkin
Given both media_buy_id and buyer_ref
Then schema validation rejects

Given neither
Then schema validation rejects
```
**Priority:** P0
**Grounded at 3.1.1:** RETIRED. `buyer_ref` does not exist at 3.1.1, so the `oneOf` it participated in is gone. repo=adcp ref=3.1.1 path=../../docs/3.1.1/reference/migration/v3-readiness.mdx §7 "Remove `buyer_ref` — use `idempotency_key`" states: "v3 removes `buyer_ref`, `buyer_campaign_ref`, and `campaign_ref` from all requests and responses. Seller-assigned `media_buy_id` and `package_id` are now the only canonical identifiers", with the migration table row "`buyer_ref` | Removed — use `media_buy_id` (seller-assigned)". Confirmed in both affected requests: repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json has `"required": ["idempotency_key","media_buy_id","measurement_period","performance_index"]` and no buyer_ref property; repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json has `"required": ["idempotency_key","account","media_buy_id"]` and likewise none. Composition resolved before asserting absence: each request's sole composition is `allOf(core/version-envelope.json)` (properties adcp_version, adcp_major_version, no `required`), and neither declares oneOf/anyOf/not/if at any level. Both scenario branches are therefore unreachable at the pin — `media_buy_id` alone is mandatory, and sending a `buyer_ref` is merely an unknown property under `additionalProperties: true`.

---

### performance_index: Performance Index Scale
**Obligation ID** CONSTR-PERFORMANCE-INDEX-01
**Layer** schema
**Requirement:** Number, minimum: 0. 0.0=no value, 1.0=expected, >1.0=above expected. <0.8 triggers optimization.
**Scenario:**
```gherkin
Given performance_index=-0.5
Then rejected (below minimum)

Given performance_index=0.79
Then optimization recommendation triggered
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED. The first sentence holds verbatim: repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json declares `performance_index` as `{"type":"number","minimum":0,"description":"Normalized performance score (0.0 = no value, 1.0 = expected, >1.0 = above expected)"}` and lists it in `required`, so `-0.5` is rejected by `minimum: 0`; repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/task-reference/provide_performance_feedback.mdx §"Performance Index Scale" restates the same scale (0.0 no measurable value, 0.5 significantly below, 1.0 baseline, 1.5 exceeds by 50%, 2.0+ exceptional). The second half is NOT in the pin: nothing at 3.1.1 defines a 0.8 threshold or mandates that any index value triggers an optimization recommendation. In repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/media-buys/optimization-reporting.mdx the only appearance of 0.8 is the illustrative gloss "`< 1.0` = Below average (e.g., 0.8 = 20% worse)", and the task reference says only that feedback "is optional but highly valuable" and that "optimization impact depends on the publisher's algorithm sophistication". That scenario branch grades our production behavior, not AdCP conformance.

---

### measurement_period: Measurement Period
**Obligation ID** CONSTR-MEASUREMENT-PERIOD-01
**Layer** schema
**Requirement:** Required object with start (date-time) and end (date-time). No schema-level start < end validation.
**Scenario:**
```gherkin
Given measurement_period with missing start
Then schema validation rejects

Given valid ISO 8601 start and end
Then accepted
```
**Priority:** P2
**Grounded at 3.1.1:** HOLDS in full, including the negative half. `measurement_period` appears in `"required": ["idempotency_key","media_buy_id","measurement_period","performance_index"]` of repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json and `$ref`s repo=adcp ref=3.1.1 path=schemas/core/datetime-range.json, which is `"type": "object"` with `"required": ["start", "end"]` and both members `{"type":"string","format":"date-time"}` — so a missing `start` is rejected and a well-formed ISO-8601 pair is accepted. The "no schema-level start < end validation" claim was verified by resolving composition, not assumed: datetime-range.json declares no allOf/oneOf/anyOf/$ref/if/then and no cross-field keyword of any kind (its only remaining keyword is `additionalProperties: true`), and the referencing request's sole composition is `allOf(core/version-envelope.json)`, which contributes only adcp_version/adcp_major_version. Ordering is therefore ungraded by schema at 3.1.1 — any start<end enforcement is our own behavior.

---

### metric_type: Metric Type Enum
**Obligation ID** CONSTR-METRIC-TYPE-01
**Layer** schema
**Requirement:** Enum: overall_performance, conversion_rate, brand_lift, click_through_rate, completion_rate, viewability, brand_safety, cost_efficiency. Default: overall_performance.
**Scenario:**
```gherkin
Given metric_type omitted
Then defaults to "overall_performance"

Given metric_type="engagement_rate"
Then rejected (not in enum)
```
**Priority:** P3
**Grounded at 3.1.1:** CORRECTED. The enum is exact: repo=adcp ref=3.1.1 path=schemas/enums/metric-type.json lists precisely `overall_performance, conversion_rate, brand_lift, click_through_rate, completion_rate, viewability, brand_safety, cost_efficiency` (a bare `"type": "string"` + `enum`, no composition), so `engagement_rate` is rejected. What the obligation misses is that the field is deprecated at this pin: the schema's title is "Metric Type (Deprecated)" and its description opens "**Deprecated as of this minor.** Legacy free-form enum... New implementations SHOULD use `performance-feedback.metric`... retained for one-minor backwards compatibility... removed at the next major", followed by a per-value migration table. repo=adcp ref=3.1.1 path=../../docs/3.1.1/media-buy/task-reference/provide_performance_feedback.mdx marks `metric_type` "**Deprecated**" and "No longer required at the schema level", with the `(scope, metric_id, qualifier)` `metric` object preferred. The defaulting branch is also weaker than claimed: in repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json `"default": "overall_performance"` sits as a sibling of `$ref` (draft-07 ignores $ref siblings) and `default` is an annotation, not a validation keyword — no pinned text requires a seller to materialize it, and the migration table maps `overall_performance` to omitting `metric` entirely.

---

### feedback_source: Feedback Source Enum
**Obligation ID** CONSTR-FEEDBACK-SOURCE-01
**Layer** schema
**Requirement:** Enum: buyer_attribution, third_party_measurement, platform_analytics, verification_partner. Default: buyer_attribution.
**Scenario:**
```gherkin
Given feedback_source omitted
Then defaults to "buyer_attribution"
```
**Priority:** P3
**Grounded at 3.1.1:** HOLDS. repo=adcp ref=3.1.1 path=schemas/enums/feedback-source.json is `"type": "string"` with exactly `["buyer_attribution", "third_party_measurement", "platform_analytics", "verification_partner"]` and no allOf/oneOf/anyOf/$ref, and repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json declares `feedback_source` as a `$ref` to it with `"default": "buyer_attribution"`, absent from that request's `"required": ["idempotency_key","media_buy_id","measurement_period","performance_index"]` — so omission is legal and the declared default is exactly `buyer_attribution`. Unlike its sibling `metric_type`, this enum is not deprecated at 3.1.1. One caveat on grading strength: `default` is a JSON Schema annotation (and here a draft-07 `$ref` sibling), so "omitted → defaults to buyer_attribution" is a documented default rather than a schema-enforced or normatively-mandated server materialization — asserting our server actually materializes it grades our behavior, not the pin.

---

### perf_feedback_package_id: Package ID in Performance Feedback
**Obligation ID** CONSTR-PERF-FEEDBACK-PACKAGE-ID-01
**Layer** schema
**Requirement:** Optional string, minLength: 1. When omitted, feedback applies to overall media buy.
**Scenario:**
```gherkin
Given package_id="" (empty string)
Then rejected (minLength: 1)

Given package_id omitted
Then feedback applies at media buy level
```
**Priority:** P2
**Grounded at 3.1.1:** Holds. `provide-performance-feedback-request.json` declares `package_id` as `{"type": "string", "minLength": 1, "x-entity": "package"}` and its `required` list is `["idempotency_key", "media_buy_id", "measurement_period", "performance_index"]` — `package_id` is absent from it, so the field is optional and `""` fails `minLength: 1` exactly as the scenario states (repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json). The media-buy-level fallback is the spec's own reading: `media_buy_id` is required on every submission and `package_id` is described as "Specific package within the media buy (if feedback is package-specific)", mirrored on the response entity `core/performance-feedback.json` (repo=adcp ref=3.1.1 path=schemas/core/performance-feedback.json). The composed `allOf` on the request resolves only to `core/version-envelope.json` and adds no constraint on `package_id`. Graded: the one storyboard step that exercises this task submits media-buy-level feedback with no `package_id` (repo=adcp ref=3.1.1 path=specialisms/sales-catalog-driven/index.yaml). The old "new in v3" note is not evidence of anything at 3.1.1.

---

### perf_feedback_creative_id: Creative ID in Performance Feedback
**Obligation ID** CONSTR-PERF-FEEDBACK-CREATIVE-ID-01
**Layer** schema
**Requirement:** Optional string, minLength: 1. When omitted, feedback applies at package/media buy level.
**Scenario:**
```gherkin
Given creative_id="" (empty string)
Then rejected (minLength: 1)
```
**Priority:** P3
**Grounded at 3.1.1:** Holds. `provide-performance-feedback-request.json` declares `creative_id` as `{"type": "string", "minLength": 1, "x-entity": "creative"}` and omits it from `required` (`["idempotency_key", "media_buy_id", "measurement_period", "performance_index"]`), so an empty string is rejected by `minLength: 1` and omission is legal (repo=adcp ref=3.1.1 path=schemas/media-buy/provide-performance-feedback-request.json). The request's only `allOf` member is `core/version-envelope.json`, which contributes no `creative_id` constraint, so the absence-from-required claim is composition-resolved. The "applies at package/media buy level when omitted" reading matches the field's own description, "Specific creative asset (if feedback is creative-specific)", repeated on the response entity (repo=adcp ref=3.1.1 path=schemas/core/performance-feedback.json). No storyboard step supplies `creative_id` to this task — the sole graded invocation is media-buy-level (repo=adcp ref=3.1.1 path=specialisms/sales-catalog-driven/index.yaml) — so the constraint is schema-graded only.

---

### status_filter: Delivery Status Filter
**Obligation ID** CONSTR-STATUS-FILTER-01
**Layer** schema
**Requirement:** Enum: pending_activation, active, paused, completed. Single string or array (minItems: 1). Omitted = no filter.
**Scenario:**
```gherkin
Given status_filter=["active", "paused"]
Then only active and paused media buys' delivery data returned

Given status_filter="failed"
Then rejected (not in enum)
```
**Priority:** P2
**Grounded at 3.1.1:** Partly false — the shape holds, the enum does not. `get-media-buy-delivery-request.json` defines `status_filter` as a `oneOf` of a single `$ref` to `enums/media-buy-status.json` and an array of the same `$ref` with `minItems: 1`, and leaves it out of the request (the request declares no `required` at all), so "single string or array (minItems: 1), omitted = no filter" is correct (repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buy-delivery-request.json). But the claimed enum `pending_activation, active, paused, completed` is wrong: after resolving the `oneOf`/`$ref`, the pinned enum is `["pending_creatives", "pending_start", "active", "paused", "completed", "rejected", "canceled"]` — `pending_activation` does not exist at 3.1.1, and `rejected`, `canceled`, `pending_creatives`, `pending_start` are all accepted values the obligation omits (repo=adcp ref=3.1.1 path=schemas/enums/media-buy-status.json). The second scenario still stands: `"failed"` is not a member and is rejected. No storyboard exercises `status_filter` — a full-text scan of dist/compliance/3.1.1 returns zero hits — so this is schema-graded only.

---

### webhook_credentials: Webhook Authentication Credentials
**Obligation ID** CONSTR-WEBHOOK-CREDENTIALS-01
**Layer** schema
**Requirement:** schemes: Bearer|HMAC-SHA256, credentials min 32 chars. HMAC signs with X-ADCP-Signature + X-ADCP-Timestamp.
**Scenario:**
```gherkin
Given credentials with 31 characters
Then rejected

Given scheme="Basic"
Then rejected (not in enum)
```
**Priority:** P1
**Grounded at 3.1.1:** The constraints hold; the framing of HMAC as *the* signing model does not. Both scenarios are correct: the `authentication` block (identical in `core/push-notification-config.json` and `core/reporting-webhook.json`, and inlined in `create-media-buy-request.json`'s `artifact_webhook`) requires `["schemes", "credentials"]`, sets `credentials` to `minLength: 32` (31 chars rejected), and constrains `schemes` to an array of `enums/auth-scheme.json` with `minItems`/`maxItems` 1 — that enum is exactly `["Bearer", "HMAC-SHA256"]`, so `"Basic"` is rejected (repo=adcp ref=3.1.1 path=schemas/core/push-notification-config.json, repo=adcp ref=3.1.1 path=schemas/core/reporting-webhook.json, repo=adcp ref=3.1.1 path=schemas/enums/auth-scheme.json). What is stale is "HMAC signs with X-ADCP-Signature + X-ADCP-Timestamp" as the description of *this* webhook path: at 3.1.1 both legacy schemes are deprecated and removed in 4.0, presence of the `authentication` block is "a switch, not a fallback", and the baseline is the RFC 9421 webhook profile signed under `tag="adcp/webhook-signing/v1"` with `content-digest` REQUIRED — graded by the runner-hosted receiver in the webhook-emission universal (repo=adcp ref=3.1.1 path=universal/webhook-emission.yaml) against the Signature/Signature-Input vectors (repo=adcp ref=3.1.1 path=test-vectors/webhook-signing/README.md). The `X-ADCP-*` header pair appears nowhere in the compliance tree, but it is NOT absent from the 3.1.1 bundle: it survives on one unrelated surface, the governance collection-list webhook, whose `signature` field mandates HMAC-SHA256 over `{unix_timestamp}.{raw_http_body_bytes}` verified against `X-ADCP-Signature`/`X-ADCP-Timestamp` within a 300s skew (repo=adcp ref=3.1.1 path=schemas/collection/collection-list-changed-webhook.json). So the correction is scoped: that header pair is not the media-buy/push-notification signing model, not that it no longer exists.

---

### channels: Advertising Media Channel Enum
**Obligation ID** CONSTR-CHANNELS-01
**Layer** schema
**Requirement:** 18 values: display, olv, social, search, ctv, linear_tv, radio, streaming_audio, podcast, dooh, ooh, print, cinema, email, gaming, retail_media, influencer, affiliate, product_placement. Array with minItems: 1.
**Scenario:**
```gherkin
Given channels=["display", "ctv"]
Then products matching either channel returned

Given channels=[]
Then rejected (minItems: 1)
```
**Priority:** P2
**Grounded at 3.1.1:** The array shape holds; the enum inventory is stale. `core/product-filters.json` defines `channels` as `{"type": "array", "items": {"$ref": "enums/channels.json"}, "minItems": 1}` and the object declares no `required`, so `[]` is rejected and omission is legal — and this is the filter surface reached from `get_products` via `filters` (repo=adcp ref=3.1.1 path=schemas/core/product-filters.json, repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json). The enum is not 18 values: resolving the `$ref`, `enums/channels.json` carries 20 members — the 19 the obligation lists plus `sponsored_intelligence` ("advertising within AI assistants, AI search, and generative AI experiences via the reversed data flow") (repo=adcp ref=3.1.1 path=schemas/enums/channels.json). The obligation's own list also miscounts itself (19 items under an "18 values" header). Graded, but weakly: `get_products` storyboards send `filters.channels: ["display"]` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/available_actions.yaml, repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/canonical_formats.yaml) and `filters.channels: ["ctv"]` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/measurement_accountability.yaml), but no step asserts that only matching-channel products come back — the validations are `response_schema` plus `field_value`/`field_present` on `products[0]` identifiers and capabilities, never on `products[*].channels`.

---

### delivery_type: Delivery Type Enum
**Obligation ID** CONSTR-DELIVERY-TYPE-01
**Layer** schema
**Requirement:** Enum: guaranteed, non_guaranteed. Optional filter.
**Scenario:**
```gherkin
Given delivery_type="guaranteed"
Then only guaranteed products returned
```
**Priority:** P2
**Grounded at 3.1.1:** Holds. `enums/delivery-type.json` is exactly `["guaranteed", "non_guaranteed"]` (repo=adcp ref=3.1.1 path=schemas/enums/delivery-type.json), and `core/product-filters.json` exposes `delivery_type` as a bare `$ref` to that enum inside an object with no `required` list, so it is an optional filter reached from `get_products` through `filters` (repo=adcp ref=3.1.1 path=schemas/core/product-filters.json, repo=adcp ref=3.1.1 path=schemas/media-buy/get-products-request.json). Graded, with a caveat on the scenario's strength: storyboards send `filters.delivery_type: "non_guaranteed"` and `"guaranteed"` (repo=adcp ref=3.1.1 path=specialisms/sales-non-guaranteed/index.yaml, repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/canonical_formats.yaml), but the validations are `field_present` on `products[0].delivery_type` rather than a value assertion — so "only guaranteed products returned" is the described intent, not something the pinned suite mechanically enforces.

---

### pacing: Budget Pacing Strategy
**Obligation ID** CONSTR-PACING-01
**Layer** schema
**Requirement:** Enum: even, asap, front_loaded. Default: even.
**Scenario:**
```gherkin
Given pacing omitted
Then defaults to "even"

Given pacing="accelerated"
Then rejected (not in enum)
```
**Priority:** P2
**Grounded at 3.1.1:** The enum holds; "Default: even" is not a schema default. `enums/pacing.json` is exactly `["even", "asap", "front_loaded"]`, so `"accelerated"` is rejected (repo=adcp ref=3.1.1 path=schemas/enums/pacing.json). But every consumer — `media-buy/package-request.json`, `media-buy/package-update.json`, `core/package.json` — declares `pacing` as a bare `$ref` to that enum with no `default` keyword and never lists it in `required` (`package-request.required` is `["product_id", "budget", "pricing_option_id"]`; `package.required` is `["package_id"]`), and neither the request `allOf` members nor the `dependencies` block touch it (repo=adcp ref=3.1.1 path=schemas/media-buy/package-request.json, repo=adcp ref=3.1.1 path=schemas/core/package.json). The only place "default" appears is the enum's own `enumDescriptions.even`: "Allocate remaining budget evenly over remaining campaign duration (default)" — descriptive prose, so an omitted `pacing` is not schema-filled and the first scenario grades our own defaulting behavior, not AdCP conformance. No storyboard exercises pacing selection.

---

### delivery_mode: Artifact Webhook Delivery Mode
**Obligation ID** CONSTR-DELIVERY-MODE-01
**Layer** schema
**Requirement:** Enum: realtime, batched. Required in artifact_webhook. batched requires batch_frequency.
**Scenario:**
```gherkin
Given delivery_mode="batched" and no batch_frequency
Then rejected (batch_frequency required when batched)
```
**Priority:** P2
**Grounded at 3.1.1:** Two-thirds true. `artifact_webhook` is an inline object on `media-buy/create-media-buy-request.json`; its `delivery_mode` is `{"type": "string", "enum": ["realtime", "batched"]}` and its `required` is `["url", "authentication", "delivery_mode"]`, so the enum and the requiredness both hold (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json). The scenario is wrong about rejection: I resolved the `artifact_webhook` subschema fully — it has only `$comment`, `type`, `description`, `properties`, `required`, `additionalProperties` — with no `if`/`then`, no `dependencies`, no `allOf`/`oneOf`/`anyOf`, and the request's own `allOf` is a single `$ref` to `core/version-envelope.json` while its `dependencies` block covers only `proposal_id → total_budget`. So `delivery_mode: "batched"` with `batch_frequency` omitted is schema-VALID at 3.1.1; "Required when delivery_mode is 'batched'" exists only as `batch_frequency`'s description prose. Nothing in dist/compliance/3.1.1 mentions `artifact_webhook`, `delivery_mode`, or `batch_frequency`, so that rejection grades our own validation, not AdCP conformance.

---

### batch_frequency: Artifact Webhook Batch Frequency
**Obligation ID** CONSTR-BATCH-FREQUENCY-01
**Layer** schema
**Requirement:** Enum: hourly, daily. Required when delivery_mode=batched.
**Scenario:**
```gherkin
Given delivery_mode="batched" and batch_frequency="hourly"
Then valid

Given delivery_mode="realtime" and batch_frequency omitted
Then valid (not applicable)
```
**Priority:** P3
**Grounded at 3.1.1:** Holds, with the enforcement caveat. Inside `artifact_webhook` on `media-buy/create-media-buy-request.json`, `batch_frequency` is `{"type": "string", "enum": ["hourly", "daily"]}` and is absent from that object's `required` (`["url", "authentication", "delivery_mode"]`), so both scenarios pass: `batched` + `hourly` validates, and `realtime` with `batch_frequency` omitted validates (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json). Note this enum is narrower than `enums/reporting-frequency.json` — no `monthly` (repo=adcp ref=3.1.1 path=schemas/enums/reporting-frequency.json). The "Required when delivery_mode=batched" half is the field's own description only: I resolved the whole `artifact_webhook` subschema and the request envelope and found no `if`/`then`, no `dependencies` on `batch_frequency`, and only a `$ref` to `core/version-envelope.json` in the top-level `allOf`, so no validator enforces it. Nothing in dist/compliance/3.1.1 references `batch_frequency`, so the conditional grades our own behavior.

---

### reporting_frequency: Reporting Webhook Frequency
**Obligation ID** CONSTR-REPORTING-FREQUENCY-01
**Layer** schema
**Requirement:** Enum: hourly, daily, monthly. Required in reporting_webhook. GAP: only daily implemented.
**Scenario:**
```gherkin
Given reporting_frequency="hourly"
Then schema-valid but silently skipped in implementation (GAP)
```
**Priority:** P2
**Grounded at 3.1.1:** Holds on the spec half. `core/reporting-webhook.json` inlines `reporting_frequency` as `{"type": "string", "enum": ["hourly", "daily", "monthly"]}` and lists it in `required` alongside `url` and `authentication`, so all three values are legal and the field is mandatory whenever a `reporting_webhook` is supplied (repo=adcp ref=3.1.1 path=schemas/core/reporting-webhook.json); the same three-value vocabulary is the shared `enums/reporting-frequency.json`, which `get_media_buy_delivery`'s `time_granularity` also `$ref`s (repo=adcp ref=3.1.1 path=schemas/enums/reporting-frequency.json, repo=adcp ref=3.1.1 path=schemas/media-buy/get-media-buy-delivery-request.json). The description adds a capability constraint the obligation omits — the value "Must be supported by all products in the media buy". The "GAP: only daily implemented" clause is a statement about our production, not about 3.1.1: no storyboard in dist/compliance/3.1.1 sets `reporting_frequency`, so "schema-valid but silently skipped" grades our own behavior and the spec neither sanctions nor forbids it.

---

### task_status: Task Status Enum
**Obligation ID** CONSTR-TASK-STATUS-01
**Layer** schema
**Requirement:** 9 values: submitted, working, input-required, completed, canceled, failed, rejected, auth-required, unknown. Filter accepts single or array (minItems: 1).
**Scenario:**
```gherkin
Given task_status=["submitted", "working"]
Then only tasks in those states returned
```
**Priority:** P2
**Grounded at 3.1.1:** The nine-value enum is exactly right — `enums/task-status.json` declares `enum: [submitted, working, input-required, completed, canceled, failed, rejected, auth-required, unknown]` (repo=adcp ref=3.1.1 path=schemas/enums/task-status.json). The single-or-array filter shape also holds, but the wire keys are NOT `task_status`: the task-list request exposes `filters.status` (`$ref` task-status.json) and `filters.statuses` (`items.$ref` task-status.json, `"minItems": 1`) (repo=adcp ref=3.1.1 path=schemas/protocol/list-tasks-request.json, repo=adcp ref=3.1.1 path=schemas/core/tasks-list-request.json). The absence of a `task_status` key was checked after resolving the schema's only `allOf`, `core/version-envelope.json`, which contributes just `adcp_version` and `adcp_major_version` (repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json). The scenario should read `filters.statuses=["submitted","working"]`. Graded: the `list_products_task` step asserts `tasks[0].status` == `"submitted"` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/get_products_async.yaml).

---

### task_type: Task Type Enum
**Obligation ID** CONSTR-TASK-TYPE-01
**Layer** schema
**Requirement:** 14 values covering all AdCP domains. Filter accepts single or array (minItems: 1).
**Scenario:**
```gherkin
Given task_type="sync_accounts"
Then only sync_accounts tasks returned

Given task_type="delete_media_buy"
Then rejected (not in enum)
```
**Priority:** P2
**Grounded at 3.1.1:** The count is wrong — `enums/task-type.json` carries **24** values, not 14: create_media_buy, update_media_buy, media_buy_delivery, sync_creatives, build_creative, activate_signal, get_products, get_signals, create_property_list, update_property_list, get_property_list, list_property_lists, delete_property_list, sync_accounts, get_account_financials, get_creative_delivery, sync_event_sources, sync_audiences, sync_catalogs, log_event, get_brand_identity, search_brands, get_rights, acquire_rights (repo=adcp ref=3.1.1 path=schemas/enums/task-type.json). Both scenario legs survive the correction: `sync_accounts` IS in the enum, and `delete_media_buy` is NOT (the enum's `notes` also state "New task types require a minor version bump"). The single-or-array filter shape holds via `filters.task_type` (`$ref` task-type.json) and `filters.task_types` (`items.$ref` task-type.json, `"minItems": 1`) (repo=adcp ref=3.1.1 path=schemas/protocol/list-tasks-request.json, repo=adcp ref=3.1.1 path=schemas/core/tasks-list-request.json). Graded: `list_products_task` sends `filters.task_type: "get_products"` and asserts `tasks[0].task_type` == `"get_products"` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/get_products_async.yaml).

---

### wcag_level: WCAG Accessibility Level
**Obligation ID** CONSTR-WCAG-LEVEL-01
**Layer** schema
**Requirement:** Enum: A, AA, AAA. Hierarchical. Optional filter on creative formats.
**Scenario:**
```gherkin
Given wcag_level="AA"
Then formats meeting at least AA returned
```
**Priority:** P3
**Grounded at 3.1.1:** `enums/wcag-level.json` declares exactly `enum: [A, AA, AAA]` with enumDescriptions ordering them minimum → highest conformance (repo=adcp ref=3.1.1 path=schemas/enums/wcag-level.json). The hierarchical, "at least" filter semantics are stated verbatim in the filter's own description — `wcag_level`: "Filter to formats that meet at least this WCAG conformance level (A < AA < AAA)" — and the property is optional on both request surfaces: neither declares a `required` array, the media-buy variant's single `allOf` member is `core/version-envelope.json` (no required fields), and the creative variant's two `allOf` members are that same envelope plus a conditional (`if include_pricing == true → then required: [account]`) that adds only `account`, never `wcag_level` (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json, repo=adcp ref=3.1.1 path=schemas/media-buy/list-creative-formats-request.json). The reporting side is the format's `accessibility.wcag_level` (`required: ["wcag_level"]` within that sub-object) (repo=adcp ref=3.1.1 path=schemas/core/format.json). Ungraded: `wcag` appears zero times anywhere in dist/compliance/3.1.1, so no storyboard exercises this filter.

---

### adcp_domain: AdCP Domain Enum
**Obligation ID** CONSTR-ADCP-DOMAIN-01
**Layer** schema
**Requirement:** Enum: media_buy, governance, signals. Used in capabilities response.
**Scenario:**
```gherkin
Given supported domains reported
Then each domain is from the adcp_domain enum
```
**Priority:** P2
**Grounded at 3.1.1:** There is no enum named `adcp_domain` in the pinned bundle, and the claimed 3-value membership is wrong. The capabilities-response domain axis is `supported_protocols`, an inline `items.enum` of **seven** snake_case values — media_buy, signals, governance, sponsored_intelligence, creative, brand, measurement — with `"minItems": 1` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). Its named kebab-case counterpart is `enums/adcp-protocol.json` (media-buy, signals, governance, creative, brand, sponsored-intelligence, measurement), whose description says it "shares the same axis as supported_protocols ... which uses snake_case on the wire" (repo=adcp ref=3.1.1 path=schemas/enums/adcp-protocol.json). Separately, `tasks[].domain` in the list_tasks response is its own narrower inline enum of just [media-buy, signals, creative] and is `required` on each task (repo=adcp ref=3.1.1 path=schemas/protocol/list-tasks-response.json). So media_buy/governance/signals are a subset, not the enum. Graded: `universal/capability-discovery.yaml` asserts `check: field_present, path: "supported_protocols"` (repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml).

---

### available_metric: Available Metric Enum
**Obligation ID** CONSTR-AVAILABLE-METRIC-01
**Layer** schema
**Requirement:** 10 values: impressions, clicks, conversions, spend, ctr, cpm, viewability, completion_rate, frequency, reach.
**Scenario:**
```gherkin
Given requested_metrics=["impressions", "clicks"]
Then webhook payload includes those metrics
```
**Priority:** P3
**Grounded at 3.1.1:** The count is wrong — `enums/available-metric.json` carries **36** values, not 10 (impressions, spend, clicks, ctr, views, completed_views, completion_rate, conversions, conversion_value, roas, cost_per_acquisition, new_to_brand_rate, leads, reach, frequency, grps, engagements, engagement_rate, follows, saves, profile_visits, viewability, quartile_data, dooh_metrics, cost_per_click, cost_per_completed_view, cpm, downloads, units_sold, new_to_brand_units, plays, incremental_sales_lift, brand_lift, foot_traffic, conversion_lift, brand_search_lift) (repo=adcp ref=3.1.1 path=schemas/enums/available-metric.json). Membership is otherwise sound: all ten named values are present. The scenario's mechanism holds — `reporting-webhook.json` defines `requested_metrics` as an array of `available-metric.json` with `"uniqueItems": true`, described as "Optional list of metrics to include in webhook notifications. If omitted, all available metrics are included. Must be subset of product's available_metrics." (repo=adcp ref=3.1.1 path=schemas/core/reporting-webhook.json). Ungraded: `requested_metrics` appears zero times in dist/compliance/3.1.1.

---

### creative_agent_format_type: Creative Agent Format Type
**Obligation ID** CONSTR-CREATIVE-AGENT-FORMAT-TYPE-01
**Layer** schema
**Requirement:** FormatCategory enum for creative agent context (same as format_type_filter).
**Scenario:**
```gherkin
Given creative agent reports format type "display"
Then valid FormatCategory enum value
```
**Priority:** P3
**Grounded at 3.1.1:** There is no enum named `FormatCategory`, and no `format-category`/`format-type` enum file, in the pinned bundle. The format-type filter value set survives only as an inline enum on the creative-agent request: `creative/list-creative-formats-request.json` property `type` — "Filter by format type (technical categories with distinct requirements)", `enum: [audio, video, display, dooh]` — so the scenario's "display" is a legal value there (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json). Three corrections: (a) the sales-agent variant has no `type` filter at all, so this filter is creative-namespace-only (repo=adcp ref=3.1.1 path=schemas/media-buy/list-creative-formats-request.json); (b) the returned format carries no property named `type` or `category` — `formats[]` is `core/format.json`, whose property set (format_id, name, description, example_url, accepts_parameters, renders, assets, delivery, supported_macros, input_format_ids, output_format_ids, format_card, accessibility, supported_disclosure_positions, disclosure_capabilities, format_card_detailed, reported_metrics, pricing_options, canonical, canonical_parameters) has neither, and its sole `allOf` is a conditional (`if: required[canonical_parameters]`) contributing no such field (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-response.json, repo=adcp ref=3.1.1 path=schemas/core/format.json); (c) a format-kind vocabulary nevertheless DOES exist and IS reportable — `core/canonical-format-kind.json` ("Canonical Format Kind": image, html5, display_tag, image_carousel, video_hosted, video_vast, audio_hosted, audio_daast, sponsored_placement, native_in_feed, responsive_creative, agent_placement, custom) is reached through format.json's optional `canonical` ($ref `core/canonical-projection-ref.json`, `required: ["kind"]` within that object), and the same `kind` vocabulary is inlined in the bundled creative list-formats response (repo=adcp ref=3.1.1 path=schemas/core/canonical-format-kind.json, repo=adcp ref=3.1.1 path=schemas/core/canonical-projection-ref.json, repo=adcp ref=3.1.1 path=schemas/bundled/creative/list-creative-formats-response.json). The storyboard is consistent with that: "There is no format_kind filter in the protocol; the buyer identifies the native_in_feed format from the returned format metadata" — no filter, but the kind is expressible in what comes back (repo=adcp ref=3.1.1 path=domains/creative/scenarios/native_in_feed.yaml).

---

### creative_agent_asset_type: Creative Agent Asset Type
**Obligation ID** CONSTR-CREATIVE-AGENT-ASSET-TYPE-01
**Layer** schema
**Requirement:** AssetContentType enum for creative agent context.
**Scenario:**
```gherkin
Given creative agent reports asset type "image"
Then valid AssetContentType enum value
```
**Priority:** P3
**Grounded at 3.1.1:** `enums/asset-content-type.json` is titled "Asset Content Type" and declares `enum: [image, video, audio, text, markdown, html, css, javascript, vast, daast, url, webhook, brief, catalog, published_post]`, so the scenario's "image" is a valid value (repo=adcp ref=3.1.1 path=schemas/enums/asset-content-type.json). It is wired into the creative-agent surface specifically: `creative/list-creative-formats-request.json` property `asset_types` is an array whose `items.$ref` is that enum, `"minItems": 1` (repo=adcp ref=3.1.1 path=schemas/creative/list-creative-formats-request.json), and the format definitions the creative agent returns carry the same vocabulary as `asset_type` consts on each `assets[]` oneOf branch (IndividualImageAsset → `"asset_type": {"const": "image"}`) (repo=adcp ref=3.1.1 path=schemas/core/format.json). Graded: the `list_native_formats` step calls list_creative_formats with `asset_types: ["text", "image"]` against `creative/list-creative-formats-request.json` (repo=adcp ref=3.1.1 path=domains/creative/scenarios/native_in_feed.yaml, repo=adcp ref=3.1.1 path=protocols/creative/scenarios/native_in_feed.yaml).

---

### tasks_sort_field: Tasks Sort Field
**Obligation ID** CONSTR-TASKS-SORT-FIELD-01
**Layer** schema
**Requirement:** Enum for sorting tasks list results.
**Scenario:**
```gherkin
Given sort_by a valid tasks sort field
Then results are sorted accordingly
```
**Priority:** P3
**Grounded at 3.1.1:** A tasks sort-field enum does exist, with one nuance: it is declared inline rather than as a standalone `enums/*.json` file. The task-list request defines `sort.field` as `"type": "string", "enum": [created_at, updated_at, status, task_type, protocol], "default": "created_at"`, paired with `sort.direction` (`$ref` sort-direction.json, `"default": "desc"`) (repo=adcp ref=3.1.1 path=schemas/protocol/list-tasks-request.json, repo=adcp ref=3.1.1 path=schemas/core/tasks-list-request.json). The schema's own example exercises the scenario shape: `"sort": {"field": "updated_at", "direction": "asc"}` under "Find media-buy tasks requiring attention". Ungraded: a full-tree scan of dist/compliance/3.1.1 finds no storyboard step that sends a `sort` block, so ordering of tasks-list results is graded by our production behavior, not by AdCP conformance.

---

### creative_status: Creative Status Enum
**Obligation ID** CONSTR-CREATIVE-STATUS-01
**Layer** schema
**Requirement:** Status values for creative lifecycle: pending_review, approved, rejected, error, etc.
**Scenario:**
```gherkin
Given creative status filter with valid status
Then only creatives in that status returned
```
**Priority:** P2
**Grounded at 3.1.1:** `enums/creative-status.json` declares exactly six values — processing, pending_review, approved, suspended, rejected, archived (repo=adcp ref=3.1.1 path=schemas/enums/creative-status.json). pending_review, approved and rejected are correct, but **`error` is not a creative status at 3.1.1** — processing failure transitions to `rejected` ("Automatically transitions to pending_review when processing completes, or to rejected if processing fails"), and the obligation's "etc." must be spelled out as `processing`, `suspended`, `archived`. The filter leg holds under one key only: `core/creative-filters.json` exposes `statuses` (array, `items.$ref` creative-status.json, `"minItems": 1`, "Filter by creative approval statuses") and there is no singular `status` filter key in its property set (repo=adcp ref=3.1.1 path=schemas/core/creative-filters.json, repo=adcp ref=3.1.1 path=schemas/creative/list-creatives-request.json). Graded: `specialisms/creative-ad-server/index.yaml` sends `filters.statuses: ["approved"]` to list_creatives (repo=adcp ref=3.1.1 path=specialisms/creative-ad-server/index.yaml), and the approved→suspended→rejected transitions are graded in `domains/creative/scenarios/creative_lifecycle_webhooks.yaml` (repo=adcp ref=3.1.1 path=domains/creative/scenarios/creative_lifecycle_webhooks.yaml).

---

### sort_direction: Sort Direction Enum
**Obligation ID** CONSTR-SORT-DIRECTION-01
**Layer** schema
**Requirement:** Enum: asc, desc. Used with sort fields.
**Scenario:**
```gherkin
Given sort_direction="asc"
Then results sorted ascending
```
**Priority:** P3
**Grounded at 3.1.1:** `enums/sort-direction.json` is titled "Sort Direction" ("Sort direction for list queries") and declares exactly `enum: [asc, desc]` (repo=adcp ref=3.1.1 path=schemas/enums/sort-direction.json). It is used with sort fields as claimed: `sort.direction` `$ref`s it alongside `sort.field` on the task-list request (`"default": "desc"`, with the schema example sending `{"field": "updated_at", "direction": "asc"}`) (repo=adcp ref=3.1.1 path=schemas/protocol/list-tasks-request.json, repo=adcp ref=3.1.1 path=schemas/core/tasks-list-request.json) and on the creative library listing, paired with `enums/creative-sort-field.json` (repo=adcp ref=3.1.1 path=schemas/creative/list-creatives-request.json, repo=adcp ref=3.1.1 path=schemas/enums/creative-sort-field.json). Ungraded: no storyboard in dist/compliance/3.1.1 sends a `sort` block, so the actual ordering of results grades our production behavior rather than AdCP conformance.

---

### creative_sort_field: Creative Sort Field
**Obligation ID** CONSTR-CREATIVE-SORT-FIELD-01
**Layer** schema
**Requirement:** Enum for sorting creatives list results.
**Scenario:**
```gherkin
Given sort_by a valid creative sort field
Then results sorted accordingly
```
**Priority:** P3
**Grounded at 3.1.1:** The sort enum exists but the request parameter is not named `sort_by`. `enums/creative-sort-field.json` is a 5-value string enum (`created_date`, `updated_date`, `name`, `status`, `assignment_count`) titled "Creative Sort Field" (repo=adcp ref=3.1.1 path=schemas/enums/creative-sort-field.json). `list_creatives` consumes it at `sort.field` — a nested `sort` object with `field` ($ref to the enum, `default: created_date`) and `direction` ($ref `enums/sort-direction.json`, `default: desc`); resolving the request's `allOf` (only `core/version-envelope.json` plus an `if/then` conditional that requires `account` when `include_pricing: true`, contributing no fields) confirms no top-level `sort_by`/`sort_order` property exists at 3.1.1 (repo=adcp ref=3.1.1 path=schemas/creative/list-creatives-request.json). The "results sorted accordingly" half is schema-shaped only: no storyboard in the pinned tree exercises sorting — the one `list_creatives` universal storyboard grades the cursor↔has_more pagination invariant, not ordering (repo=adcp ref=3.1.1 path=universal/pagination-integrity.yaml), so the ordering behavior grades our production, not AdCP conformance.

---

### preview_output_format: Preview Output Format
**Obligation ID** CONSTR-PREVIEW-OUTPUT-FORMAT-01
**Layer** schema
**Requirement:** Enum for creative preview output format.
**Scenario:**
```gherkin
Given preview output_format is valid enum value
Then preview is generated in that format
```
**Priority:** P3
**Grounded at 3.1.1:** `enums/preview-output-format.json` is a string enum titled "Preview Output Format" with exactly two values, `url` and `html` (repo=adcp ref=3.1.1 path=schemas/enums/preview-output-format.json). `preview_creative` references it at `output_format` with `default: "url"` and the normative description "'url' returns preview_url (iframe-embeddable URL), 'html' returns preview_html (raw HTML). In batch mode, sets the default for all requests (individual items can override)" — declared both at the single-mode root and per item inside `requests[]` (repo=adcp ref=3.1.1 path=schemas/creative/preview-creative-request.json). The "preview is generated in that format" half is structurally enforced on the response side: `preview-render.json` is a `oneOf` discriminated on `propertyName: output_format`, whose branches bind `const: "url"` to `preview_url` and `const: "html"` to `preview_html` (repo=adcp ref=3.1.1 path=schemas/creative/preview-render.json). One nuance worth recording: that response discriminator carries a third branch, `const: "both"` (both `preview_url` and `preview_html` supplied), which is not a member of the request-side enum — a render may satisfy the request format as part of a superset.

---

### list_creatives_fields: List Creatives Response Fields
**Obligation ID** CONSTR-LIST-CREATIVES-FIELDS-01
**Layer** schema
**Requirement:** Defines which fields are included in list_creatives response.
**Scenario:**
```gherkin
Given list_creatives request with field selection
Then response includes only requested fields
```
**Priority:** P3
**Grounded at 3.1.1:** The field-selection parameter is real, but the scenario's "only requested fields" is too strong for the whole response. `list_creatives` declares `fields`: an array with `minItems: 1` whose items are a closed 13-value enum — `creative_id`, `name`, `format_id`, `status`, `created_date`, `updated_date`, `tags`, `assignments`, `snapshot`, `items`, `variables`, `concept`, `pricing_options` — described as "Specific fields to include in response (omit for all fields). The 'concept' value returns both concept_id and concept_name", with a worked example `{"fields": ["creative_id", "name", "status"], "include_assignments": false}` (repo=adcp ref=3.1.1 path=schemas/creative/list-creatives-request.json). Selection is per-creative, not whole-response: resolving the response's `allOf` (`core/version-envelope.json` + `core/protocol-envelope.json`) leaves `required: [query_summary, pagination, creatives]` in force regardless of `fields`, so an agent honoring a 3-field selection still MUST emit `query_summary` and `pagination` (repo=adcp ref=3.1.1 path=schemas/creative/list-creatives-response.json). No storyboard in the pinned tree grades sparse field selection — the `list_creatives` universal storyboard grades pagination cursor integrity (repo=adcp ref=3.1.1 path=universal/pagination-integrity.yaml).

---

### approval_mode: Approval Mode Enum
**Obligation ID** CONSTR-APPROVAL-MODE-01
**Layer** schema
**Requirement:** Enum: auto-approve, require-human, ai-powered. Default: require-human.
**Scenario:**
```gherkin
Given approval_mode not set
Then defaults to "require-human"
```
**Priority:** P1
**Grounded at 3.1.1:** Every specific in this obligation is wrong at the pin. There is no `approval_mode` field; the field is `media_buy.creative_approval_mode` on the capabilities response, and its enum has exactly two snake_case values, `["auto_approve", "require_human"]` — not the hyphenated triple. The schema explicitly rejects the third value: "`ai_assisted` is intentionally not part of the enum until a behavioral contract is defined." It also explicitly rejects the claimed default — the property declares no `default`, is not in any `required` list, and its description states "When absent, approval behavior is legacy-unspecified; runners SHOULD NOT treat omission as an affirmative auto-approval claim", so the scenario "Given approval_mode not set / Then defaults to require-human" is contradicted (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). The pinned tree treats the field as a storyboard applicability gate rather than a default: the media-buy state-machine storyboard declares `requires_capability: {path: media_buy.creative_approval_mode, equals: auto_approve}` and applies only to sellers that make that affirmative declaration (repo=adcp ref=3.1.1 path=domains/media-buy/state-machine.yaml).

---

### sampling_method: Sampling Method Enum
**Obligation ID** CONSTR-SAMPLING-METHOD-01
**Layer** schema
**Requirement:** Enum for content standards sampling.
**Scenario:**
```gherkin
Given sampling_method is valid enum value
Then content standard uses that sampling approach
```
**Priority:** P3
**Grounded at 3.1.1:** No `sampling_method` field and no sampling enum exist at the pin, and sampling is modeled as a numeric rate rather than an enumerated method. `content-standards/content-standards.json` composes nothing (no `allOf`/`oneOf`/`$ref` at the root) and its complete property set is `standards_id`, `name`, `countries_all`, `channels_any`, `languages_any`, `policies`, `calibration_exemplars`, `pricing_options`, `ext` — no sampling field of any kind (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json); every other content-standards request/response composes only `core/version-envelope.json` and `core/protocol-envelope.json`, neither of which contributes a sampling field, so the absence is composition-resolved. Sampling is configured as a rate at buy creation: `create_media_buy` declares `artifact_webhook.sampling_rate`, `type: number`, `minimum: 0`, `maximum: 1`, "Fraction of impressions to include (0-1). 1.0 = all impressions, 0.1 = 10% sample. Default: 1.0" (repo=adcp ref=3.1.1 path=schemas/media-buy/create-media-buy-request.json), and `get_media_buy_artifacts` reports back what that rate produced via `collection_info` — "Sampling is configured at buy creation time — this reports what was actually collected", carrying integer `total_deliveries`/`total_collected`/`returned_count` and numeric `effective_rate` ("Actual collection rate achieved (total_collected / total_deliveries)") (repo=adcp ref=3.1.1 path=schemas/content-standards/get-media-buy-artifacts-response.json). `sampling_method` returns zero hits across the schema bundle, docs/3.1.1 and compliance/3.1.1, and `schemas/enums/` contains no sampling enum.

---

### protocols: Supported Protocols Enum
**Obligation ID** CONSTR-PROTOCOLS-01
**Layer** schema
**Requirement:** Enum: media_buy, governance, signals. Lists supported protocol areas in capabilities.
**Scenario:**
```gherkin
Given capabilities response
Then supported_protocols contains valid protocol enum values
```
**Priority:** P2
**Grounded at 3.1.1:** The field is real and required, but the enum is seven values, not three. `supported_protocols` is a required top-level array on the capabilities response (`required: ["adcp", "supported_protocols"]`, `minItems: 1`) whose items enumerate `media_buy`, `signals`, `governance`, `sponsored_intelligence`, `creative`, `brand`, `measurement` — with `measurement` flagged experimental in 3.1 and requiring `measurement.core` in `experimental_features`; declaring a stable value both names the tools implemented and "commit[s] the agent to pass the baseline compliance storyboard at /compliance/{version}/protocols/{protocol}/" (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). Note the pin carries a second, parallel protocol enum on the same axis for task categorization, kebab-cased: `media-buy`, `signals`, `governance`, `creative`, `brand`, `sponsored-intelligence`, `measurement` — its description states it "shares the same axis as supported_protocols ... which uses snake_case on the wire" (repo=adcp ref=3.1.1 path=schemas/enums/adcp-protocol.json). The scenario itself is graded: the universal capability-discovery storyboard asserts `field_present: supported_protocols` (repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml).

---

### context_echo: Context Echo Constraint
**Obligation ID** CONSTR-CONTEXT-ECHO-01
**Layer** schema
**Requirement:** Request context echoed unchanged in response. Opaque object. Applies to success, empty, and error paths. GAP: capabilities endpoint does not echo context.
**Scenario:**
```gherkin
Given request with context={"trace":"abc"}
Then response has context={"trace":"abc"}

Given capabilities request with context
Then context is NOT echoed (known GAP)
```
**Priority:** P1
**Grounded at 3.1.1:** The echo requirement holds, but the recorded GAP does not. `core/context.json` is an open object (`additionalProperties: true`) described as "Opaque correlation data that is echoed unchanged in responses ... never parsed by AdCP agents - it's simply preserved and returned" (repo=adcp ref=3.1.1 path=schemas/core/context.json), and the response envelope makes it normative: `context` is "a per-request opaque caller-supplied correlation object echoed unchanged in the response ... that the agent MUST preserve byte-for-byte without parsing", distinct from the server-owned `context_id`, with the envelope declaration authoritative over the 147 per-task body-level mirrors; because the envelope also carries `adcp_error`, the echo rides success and error responses alike (repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json). The GAP clause "capabilities endpoint does not echo context" is FALSE at 3.1.1: the capabilities request declares `context` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-request.json), the response composes `allOf: [core/version-envelope.json, core/protocol-envelope.json]` *and* redeclares `context: {$ref: core/context.json}` as its own property (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json), and the universal storyboard grades the echo twice, in both the unfiltered and protocol-filtered steps, with `field_present: context` plus `field_value` on `context.correlation_id` ("Context correlation_id returned unchanged") (repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml).

---

### event_type: Event Type Enum
**Obligation ID** CONSTR-EVENT-TYPE-01
**Layer** schema
**Requirement:** Enum for marketing/conversion events (log_event task).
**Scenario:**
```gherkin
Given event_type is valid enum value
Then event is logged
```
**Priority:** P3
**Grounded at 3.1.1:** `enums/event-type.json` is titled "Event Type" and described as "Standard marketing event types for event logging, aligned with IAB ECAPI", carrying 31 values including `page_view`, `add_to_cart`, `purchase`, `refund`, `lead`, `subscribe`, `app_install` and `custom` ("Custom event type (specify in custom_event_name)"), each with an `enumDescriptions` entry (repo=adcp ref=3.1.1 path=schemas/enums/event-type.json). It is bound to logging exactly as the obligation states: `core/event.json` lists `event_type` in `required: [event_id, event_type, event_time]` and `$ref`s the enum (repo=adcp ref=3.1.1 path=schemas/core/event.json), and `log_event` takes `events` — an array of `core/event.json`, `minItems: 1`, `maxItems: 10000` — in `required: [idempotency_key, event_source_id, events]` (repo=adcp ref=3.1.1 path=schemas/media-buy/log-event-request.json). The behavior is graded: the event-dedup storyboard drives `log_event` with `event_type: "purchase"` payloads against an event source declaring `event_types: ["purchase", "add_to_cart"]` (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/event_dedup_flow.yaml).

---

### sync_atomic_response: Sync Accounts Atomic Response
**Obligation ID** CONSTR-SYNC-ATOMIC-RESPONSE-01
**Layer** behavioral
**Requirement:** Success variant (accounts[]) XOR error variant (errors[]). Per-account failure is within success variant.
**Scenario:**
```gherkin
Given operation-level auth failure
Then error variant with errors[], no accounts[]

Given 3 accounts processed, 1 failed
Then success variant with accounts[] (including action=failed)
```
**Priority:** P0
**Grounded at 3.1.1:** The XOR is structural. `sync-accounts-response.json` composes `allOf: [core/version-envelope.json, core/protocol-envelope.json]` and then a two-branch `oneOf`: `SyncAccountsSuccess` ("Sync operation processed accounts (individual accounts may be pending or have action=failed)") with `required: [accounts]` and `not: {required: [errors]}`, versus `SyncAccountsError` ("Operation failed completely, no accounts were processed") with `required: [errors]` and `not: {anyOf: [{required: [accounts]}, {required: [dry_run]}]}` — so accounts[] and top-level errors[] are mutually exclusive by schema, not convention. Per-account failure lives inside the success variant: each `accounts[]` entry carries `action` with enum `created|updated|unchanged|failed` and its own `errors` array ("Per-account errors (only present when action is 'failed')") plus a per-account `status` enum (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). The pinned tree grades exactly that split: the billing-gate storyboard notes "sync_accounts returns transport-level success with per-account errors in accounts[].errors[] — this is the per-account-error envelope, not a transport-layer failure. expect_error: true would incorrectly require an MCP isError / A2A failed marker", expecting `accounts[0].action: "failed"`, `accounts[0].status: "rejected"`, `accounts[0].errors[0].code: BILLING_NOT_SUPPORTED` (repo=adcp ref=3.1.1 path=universal/billing-gate-dispatch.yaml), and the notification-scope storyboard grades the same shape (repo=adcp ref=3.1.1 path=universal/notification-config-event-scope.yaml). One narrowing: the schema scopes the error variant to "operation failed completely" generically — nothing at 3.1.1 singles out *auth* failure as the trigger, so that specific instantiation grades our production choice.

---

### sync_upsert_semantics: Sync Accounts Upsert
**Obligation ID** CONSTR-SYNC-UPSERT-SEMANTICS-01
**Layer** behavioral
**Requirement:** Creates new or updates existing. Per-account action: created/updated/unchanged/failed. House echoed.
**Scenario:**
```gherkin
Given new account
Then action=created with seller-assigned account_id

Given identical account re-synced
Then action=unchanged
```
**Priority:** P1
**Grounded at 3.1.1:** Upsert and the four-value action enum hold; "House echoed" has no counterpart in sync_accounts. The request describes provisioning mode as "the seller provisions or links accounts via upsert" keyed on the `brand` + `operator` + `billing` trio, versus settings-update mode keyed on an `account` AccountRef where "When `account` is present, the seller MUST NOT create a new account — entries that would otherwise trigger provisioning are rejected with `UNSUPPORTED_PROVISIONING`", the two shapes enforced by a per-entry `oneOf` (ProvisioningMode requires brand+operator+billing and forbids `account`; SettingsUpdateMode is its inverse) (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json). The response's per-account `action` enum is exactly `created|updated|unchanged|failed` — "created: new account provisioned. updated: existing account modified. unchanged: no changes needed. failed: could not process (see errors)" — `account_id` is the "Seller-assigned account identifier", and the echoed identity fields are `brand` ("Brand reference, echoed from the request"), `operator` ("Operator domain, echoed from request"), `billing_entity` and `sandbox`; no `house` field appears in either sync_accounts schema (verified over schemas/account/*.json) (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). `house` does exist elsewhere at 3.1.1 — it is a required object (`domain`, `name`) on the brand-identity response, "The house (corporate entity) this brand belongs to" (repo=adcp ref=3.1.1 path=schemas/brand/get-brand-identity-response.json), and appears as prose in brand-ref's root description for "house-of-brands domains" (repo=adcp ref=3.1.1 path=schemas/core/brand-ref.json) — but it is not part of the sync_accounts contract, so nothing there echoes it. The `created` half is graded (`field_present: accounts[0].account_id`, "Account has a platform-assigned ID") (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/clicks_buy_flow.yaml), and the recovery step expects "accounts[0].action is `created` or `updated`" (repo=adcp ref=3.1.1 path=universal/billing-gate-dispatch.yaml); no storyboard in the pinned tree asserts `action: unchanged`, so the identical-re-sync half grades our production.

---

### dry_run_preview: Dry Run Mode
**Obligation ID** CONSTR-DRY-RUN-PREVIEW-01
**Layer** schema
**Requirement:** dry_run=true returns what would change without applying. Response includes dry_run=true.
**Scenario:**
```gherkin
Given dry_run=true
Then no state changes; response shows would-be actions
```
**Priority:** P2
**Grounded at 3.1.1:** The preview half of this obligation is real: `sync_accounts` request declares `dry_run` (boolean, `default: false`) described as "When true, preview what would change without applying. Returns what would be created/updated/deactivated" (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json), and the prose adds a normative no-side-effect rule — "`dry_run: true` MUST NOT send network challenges; it can only report structural validation and what would require proof" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/accounts/tasks/sync_accounts.mdx). The echo half is over-stated: resolving the response schema's `allOf` (version-envelope + protocol-envelope) and its two-branch `oneOf`, the `SyncAccountsSuccess` branch declares `dry_run` ("Whether this was a dry run (no actual changes made)") but `required` on that branch is only `["accounts"]`, so echoing `dry_run: true` is permitted, not mandated; the `SyncAccountsError` branch actively forbids it via `not.anyOf[required: dry_run]` (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). No storyboard exercises `dry_run`, so the echo assertion grades our own behavior.

---

### delete_missing_policy: Delete Missing Deactivation
**Obligation ID** CONSTR-DELETE-MISSING-POLICY-01
**Layer** behavioral
**Requirement:** delete_missing=true deactivates absent accounts scoped to agent. Default false.
**Scenario:**
```gherkin
Given delete_missing=true and account absent from request
Then account deactivated

Given delete_missing not specified (default false)
Then absent accounts unchanged
```
**Priority:** P1
**Grounded at 3.1.1:** Verbatim match. The `sync_accounts` request declares `delete_missing` as a boolean with `"default": false` and the description "When true, accounts previously synced by this agent but not included in this request will be deactivated. Scoped to the authenticated agent — does not affect accounts managed by other agents" (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json), restated normatively in the task prose parameter table as "When true, accounts previously synced by this agent but not in this request are deactivated. Scoped to the authenticated agent. Default: `false`" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/accounts/tasks/sync_accounts.mdx). Both scenario legs — deactivate-on-true and leave-unchanged on the omitted default — are exactly the spec's semantics. No storyboard sets `delete_missing`, so the behavior is spec-defined but ungraded by the conformance suite.

---

### billing: Billing Model
**Obligation ID** CONSTR-BILLING-01
**Layer** schema
**Requirement:** Billing model enum for account sync.
**Scenario:**
```gherkin
Given billing model in sync request
Then seller assigns or overrides per policy
```
**Priority:** P2
**Grounded at 3.1.1:** A closed billing enum for account sync exists at 3.1.1: `enum: ["operator", "agent", "advertiser"]`, titled "Billing Party" — "Which party the seller invoices for an account" (repo=adcp ref=3.1.1 path=schemas/enums/billing-party.json). It is `$ref`'d by the sync request's per-account `billing` field, which is required in provisioning mode (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json), and echoed on the per-account result as "Who is invoiced on this account. Matches the requested billing model" (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). It is graded: the storyboard `sync_accounts` step sends `billing: "operator"` under a `response_schema` check against sync-accounts-response.json (repo=adcp ref=3.1.1 path=domains/media-buy/scenarios/billing_finality_delivery.yaml). Naming note only — the spec calls the enum "billing party" while the prose and response description use "billing model" for the same values.

---

### billing_model_policy: Billing Model Override Policy
**Obligation ID** CONSTR-BILLING-MODEL-POLICY-01
**Layer** behavioral
**Requirement:** Seller may override unsupported billing model with warning. Omitted = seller default.
**Scenario:**
```gherkin
Given unsupported billing model requested
Then overridden with warning in per-account result
```
**Priority:** P2
**Grounded at 3.1.1:** Both halves of this claim are contradicted. (1) "Omitted = seller default" is false — resolving the per-account entry's `oneOf`, the `ProvisioningMode` branch has `"required": ["brand", "operator", "billing"]`, so `billing` cannot be omitted when provisioning (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json); the prose parameter table marks `billing` Required=Yes (repo=adcp ref=3.1.1 path=../../docs/3.1.1/accounts/tasks/sync_accounts.mdx). (2) "Seller may override unsupported billing model with warning" is false — the same prose states "The seller must either accept this billing model or reject the request" and defines two distinct rejection codes, `BILLING_NOT_SUPPORTED` (seller-wide capability gate) and `BILLING_NOT_PERMITTED_FOR_AGENT` (per-buyer-agent commercial gate). The response schema's own worked example encodes rejection, not silent remap: `action: "failed"`, `status: "rejected"`, `errors[0].code: "BILLING_NOT_SUPPORTED"` (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json). The per-account `warnings[]` array exists but nothing in 3.1.1 sanctions using it to carry a billing override; the sibling `payment_terms` field states the same accept-or-reject rule explicitly ("terms are never silently remapped").

---

### brand_identity_resolution: Brand Identity Resolution
**Obligation ID** CONSTR-BRAND-IDENTITY-RESOLUTION-01
**Layer** behavioral
**Requirement:** House domain + optional brand_id. Resolved via /.well-known/brand.json.
**Scenario:**
```gherkin
Given house="acme.com" and brand_id="widgets"
Then resolved via acme.com/.well-known/brand.json
```
**Priority:** P2
**Grounded at 3.1.1:** The brand reference shape and its resolution path are exactly as claimed. `core/brand-ref.json` is "Reference to a brand by domain and optional brand_id. The domain hosts /.well-known/brand.json or is registered in the brand registry. For single-brand domains, brand_id can be omitted. For house-of-brands domains, brand_id identifies the specific brand", with `"required": ["domain"]` and `brand_id` optional (repo=adcp ref=3.1.1 path=schemas/core/brand-ref.json). The brand-protocol prose confirms the well-known location `https://example.com/.well-known/brand.json` and that "Tasks reference brands by domain and brand_id — the system resolves full identity from `brand.json` or the registry", including the House Portfolio variant where a house domain publishes its brands (repo=adcp ref=3.1.1 path=../../docs/3.1.1/brand-protocol/brand-json.mdx). Two precisions that do not falsify the claim: the wire field is named `domain` (not `house`; `house` is a field *inside* brand.json), and the brand registry is a co-equal resolution path alongside the well-known document.

---

### si_termination_reason: Structured Interaction Termination Reason
**Obligation ID** CONSTR-SI-TERMINATION-REASON-01
**Layer** schema
**Requirement:** Enum for why a structured interaction ended.
**Scenario:**
```gherkin
Given termination with valid reason
Then reason is from the enum
```
**Priority:** P3
**Grounded at 3.1.1:** The termination-reason enum exists and is mandatory. `si-terminate-session-request.json` declares `reason` as a string with `enum: ["handoff_transaction", "handoff_complete", "user_exit", "session_timeout", "host_terminated"]`, description "Reason for termination", and `"required": ["session_id", "reason"]` (repo=adcp ref=3.1.1 path=schemas/sponsored-intelligence/si-terminate-session-request.json). It is graded: the SI storyboard's `si_terminate_session` step binds `schema_ref: sponsored-intelligence/si-terminate-session-request.json` and sends `reason: "handoff_complete"` (repo=adcp ref=3.1.1 path=domains/sponsored-intelligence/index.yaml). Note the schema carries `x-status: "experimental"`, so this is a conforming-but-experimental surface at 3.1.1.

---

### si_transaction_action: Structured Interaction Transaction Action
**Obligation ID** CONSTR-SI-TRANSACTION-ACTION-01
**Layer** schema
**Requirement:** Enum for transaction actions in structured interactions.
**Scenario:**
```gherkin
Given transaction action is valid enum value
Then action processed
```
**Priority:** P3
**Grounded at 3.1.1:** A transaction-action enum exists for structured interactions, though it is nested rather than a standalone enum file: on the terminate-session request, `termination_context.transaction_intent.action` is a string with `enum: ["purchase", "subscribe"]`, under a `transaction_intent` object described as "For handoff_transaction - what user wants to buy" (repo=adcp ref=3.1.1 path=schemas/sponsored-intelligence/si-terminate-session-request.json). Resolving the request's only `allOf` (core/version-envelope.json) confirms no other transaction-action surface is composed in, and a scan of schemas/enums/ found no separate SI transaction-action enum — `enums/event-type.json` and `enums/governance-phase.json` also carry a "purchase" member but are unrelated conversion/governance vocabularies. The obligation's claim holds against the nested enum; nothing in 3.1.1 requires a top-level enum file for it. No storyboard sends `transaction_intent`, so the value is schema-graded only.

---

### channel_mapping: Channel Alias Mapping
**Obligation ID** CONSTR-CHANNEL-MAPPING-01
**Layer** behavioral
**Requirement:** "video" -> "olv", "audio" -> "streaming_audio". Case-insensitive matching. Unrecognized channels silently dropped.
**Scenario:**
```gherkin
Given adapter reports "video"
Then mapped to "olv"

Given adapter reports "metaverse" (unknown)
Then silently dropped
```
**Priority:** P2
**Grounded at 3.1.1:** The target vocabulary is right, the mapping arity is wrong, and the normalization policy is spec-silent. `enums/channels.json` is a flat closed string enum (no allOf/$ref) containing `olv` ("Online video advertising outside CTV") and `streaming_audio` ("Digital audio streaming services"), and containing no `video` and no `audio` member (repo=adcp ref=3.1.1 path=schemas/enums/channels.json). But the pinned legacy-migration table maps `video` to **`olv`, `ctv`** ("Split by viewing environment") and `audio` to **`streaming_audio`, `podcast`, `radio`** ("Split by audio type") — one-to-many, resolved by buying context, not the 1:1 rewrite this obligation asserts (repo=adcp ref=3.1.1 path=../../docs/3.1.1/reference/media-channel-taxonomy.mdx). Case-insensitive matching and silently dropping unrecognized channels appear nowhere in the channel enum or the taxonomy reference; those are our production normalization choices and are graded as such (a non-enum value on the wire would be a schema violation, not a defined drop).

---

### account_access_scoping: Account Access Scoping
**Obligation ID** CONSTR-ACCOUNT-ACCESS-SCOPING-01
**Layer** behavioral
**Requirement:** list_accounts returns only agent-accessible accounts. Status filter narrows within accessible set.
**Scenario:**
```gherkin
Given agent has access to 3 accounts, status_filter="active"
Then only active accounts among the 3 are returned
```
**Priority:** P1
**Grounded at 3.1.1:** The semantics hold; the parameter name in the scenario does not. Scoping: the request is "Request parameters for listing accounts accessible to the authenticated agent" and the response's `accounts` array is "Array of accounts accessible to the authenticated agent" (repo=adcp ref=3.1.1 path=schemas/account/list-accounts-request.json, repo=adcp ref=3.1.1 path=schemas/account/list-accounts-response.json); the prose is normative — "Returns all accounts the authenticated agent can operate on this vendor agent", and the optional exact-account filter returns "only matching accounts visible to the authenticated caller" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/accounts/tasks/list_accounts.mdx). Narrowing: the status filter is `enum: ["active", "pending_approval", "rejected", "payment_required", "suspended", "closed"]`, "Omit to return accounts in all statuses" — i.e. it narrows within the accessible set rather than widening it. The correction: the wire field is `status`, not `status_filter`; resolving the request's `allOf` (core/version-envelope.json, which contributes only `adcp_version`/`adcp_major_version`) confirms no `status_filter` is composed in from anywhere, and the response items resolve through core/account-with-authorization.json → allOf(core/account.json) whose properties likewise carry no such field.

---

### account_approval_workflow: Account Approval Workflow
**Obligation ID** CONSTR-ACCOUNT-APPROVAL-WORKFLOW-01
**Layer** behavioral
**Requirement:** Accounts requiring review enter pending_approval with setup info.
**Scenario:**
```gherkin
Given account requires review
Then status=pending_approval with setup.message
```
**Priority:** P2
**Grounded at 3.1.1:** Directly grounded in both schema and storyboard. The per-account sync result declares `status` with `pending_approval` in its enum ("seller reviewing (credit, legal)") alongside a `setup` object whose own `"required": ["message"]` guarantees the human-readable next step, with optional `url` and `expires_at` (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-response.json); the schema's worked example returns `action: "created", status: "pending_approval"` with `setup.url`/`setup.message`/`setup.expires_at` populated. The conformance storyboard states the rule normatively: "If your platform requires manual approval (credit checks, sales team review), return the account with status pending_approval and account.setup.url populated", and its `expected` block requires "setup.url and setup.message: populated on the account when status is pending_approval" (repo=adcp ref=3.1.1 path=domains/media-buy/index.yaml). The task prose confirms the follow-up leg — `pending_approval` → "Human may need to visit `setup.url`... Poll `list_accounts` for updates" (repo=adcp ref=3.1.1 path=../../docs/3.1.1/accounts/tasks/sync_accounts.mdx).

---

### account_auth_policy: Account Authentication Policy
**Obligation ID** CONSTR-ACCOUNT-AUTH-POLICY-01
**Layer** behavioral
**Requirement:** sync_accounts requires valid auth. list_accounts allows anonymous (empty results).
**Scenario:**
```gherkin
Given no auth on sync_accounts
Then AUTH_REQUIRED error
```
**Priority:** P0
**Grounded at 3.1.1:** Partly true, and the named error code is stale. The auth-required half is grounded only generically: the universal security storyboard makes rejection of unauthenticated protected operations the baseline conformance bar — the `probe_unauth` step requires `http_status_in: [401, 403]` plus a `WWW-Authenticate` header on 401, and its prerequisites name `get_adcp_capabilities` as the sort of "public task ... [that] return[s] 200 without credentials by design" (repo=adcp ref=3.1.1 path=universal/security.yaml). `sync_accounts` is a state-mutating provisioning task (`x-mutates-state: true`, required `idempotency_key`) whose whole contract is written against "the authenticated agent" (repo=adcp ref=3.1.1 path=schemas/account/sync-accounts-request.json), so it sits inside that baseline; 3.1.1 never names it individually. The anonymous half is false: `list_accounts` is defined over "accounts accessible to the authenticated agent" / "visible to the authenticated caller" in both the request and the response, whose composition (allOf version-envelope + protocol-envelope) adds no anonymous branch (repo=adcp ref=3.1.1 path=schemas/account/list-accounts-request.json, repo=adcp ref=3.1.1 path=schemas/account/list-accounts-response.json). 3.1.1 grants no anonymous carve-out for `list_accounts`; answering an anonymous caller with 200 + empty results is precisely the shape `probe_unauth` grades as non-conformant. Finally, `AUTH_REQUIRED` is marked "**Deprecated** — use `AUTH_MISSING` (no credentials presented) or `AUTH_INVALID` (credentials presented and rejected)" and retained only as a 3.x alias (repo=adcp ref=3.1.1 path=schemas/enums/error-code.json); 3.1.1 also grades this at the transport layer (401/403), not as a payload error code.

---

### account_status: Account Status Enum
**Obligation ID** CONSTR-ACCOUNT-STATUS-01
**Layer** behavioral
**Requirement:** Account lifecycle status values including pending_approval, active, suspended, deactivated.
**Scenario:**
```gherkin
Given account status filter with valid status
Then only matching accounts returned
```
**Priority:** P2
**Grounded at 3.1.1:** The filter behavior holds but one status value does not exist. `Account.status` resolves to the shared enum whose complete value set is `active`, `pending_approval`, `rejected`, `payment_required`, `suspended`, `closed` — with `closed` described as "Was active, now terminated — terminal state" (repo=adcp ref=3.1.1 path=schemas/enums/account-status.json, repo=adcp ref=3.1.1 path=schemas/core/account.json). `deactivated` is not a 3.1.1 account status; `closed` is the terminal value the obligation is reaching for, and the obligation also omits the real values `rejected` and `payment_required`. The scenario half holds: `list_accounts` takes an optional `status` filter over exactly that enum, documented "Filter accounts by status. Omit to return accounts in all statuses" (repo=adcp ref=3.1.1 path=schemas/account/list-accounts-request.json), and the response returns only the accounts visible to the caller (repo=adcp ref=3.1.1 path=schemas/account/list-accounts-response.json).

---

### capabilities_degradation: Capabilities Graceful Degradation
**Obligation ID** CONSTR-CAPABILITIES-DEGRADATION-01
**Layer** behavioral
**Requirement:** No tenant = minimal response. Adapter failure = default channels/targeting. DB failure = placeholder domain. Never propagate error.
**Scenario:**
```gherkin
Given adapter lookup fails
Then channels defaults to [display], targeting defaults to geo

Given DB query fails
Then placeholder domain used
```
**Priority:** P1
**Grounded at 3.1.1:** 3.1.1 says nothing about degraded capability assembly. There is no notion of "no tenant", adapter failure, DB failure, placeholder domains, or default-on-failure targeting anywhere in the pinned compliance tree or the capabilities schema — a grep for `degrad|placeholder|fallback|partial capabilit` across /compliance/3.1.1 returns 125 hits across ~30 files (request-signing test vectors, universal/idempotency.yaml, universal/error-compliance.yaml, universal/webhook-emission.yaml, media-buy and creative scenarios, brand/signals/creative specialism indexes), and not one of them concerns capability assembly or a degraded capabilities response. The capability-discovery storyboard grades only response-schema conformance, presence of `adcp.major_versions`, `supported_protocols` and `context`, and the echo of `context.correlation_id`; it defines no failure or degradation path (repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml). The only pinned floor is structural: the response requires `adcp` and `supported_protocols` (with `adcp` itself requiring `major_versions` and `idempotency`), so even a "minimal" response must carry those (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). Everything else in this obligation — never propagating the error, defaulting channels to [display], defaulting targeting to geo, substituting a placeholder domain — grades our own production degradation policy, not AdCP conformance.

---

### capabilities_features: Capabilities Feature Flags
**Obligation ID** CONSTR-CAPABILITIES-FEATURES-01
**Layer** schema
**Requirement:** Boolean feature flags in capabilities response (signals, content_standards, accounts, etc.).
**Scenario:**
```gherkin
Given capabilities response assembled
Then feature flags reflect tenant configuration
```
**Priority:** P2
**Grounded at 3.1.1:** Booleans exist in the capabilities response, but not under the names or shape this obligation asserts. Resolving the response (allOf core/version-envelope.json + core/protocol-envelope.json, then its own `properties`), there is no top-level boolean named `signals`, `content_standards`, or `accounts`: `signals` is an **object** and signals support is declared by membership in the `supported_protocols` string enum (`media_buy`, `signals`, `governance`, `sponsored_intelligence`, `creative`, `brand`, `measurement`); `account` is an **object** (required `supported_billing`) that carries the booleans `require_operator_auth`, `required_for_products`, `account_financials`, and `sandbox`; and `content_standards` is an **object nested under `media_buy`** whose "[p]resence ... indicates the seller supports content_standards" and which carries the booleans `supports_local_evaluation` and `supports_webhook_delivery` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). The genuine flat boolean-flag surface at 3.1.1 is `media_buy.features`, an open map of booleans (`inline_creative_management`, `property_list_filtering`, `catalog_management`, `committed_metrics_supported`, `additionalProperties: {type: boolean}`) whose contract is "[i]f a seller declares a feature as true, they MUST honor requests using that feature" (repo=adcp ref=3.1.1 path=schemas/core/media-buy-features.json). So: boolean feature flags — yes; those three names as top-level booleans — no. The claim that they "reflect tenant configuration" is a property of our implementation; the storyboard grades only that `supported_protocols` is present (repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml).

---

### capabilities_targeting: Capabilities Targeting Support
**Obligation ID** CONSTR-CAPABILITIES-TARGETING-01
**Layer** behavioral
**Requirement:** Targeting dimensions supported by the seller. Defaults: geo_countries=true, geo_regions=true.
**Scenario:**
```gherkin
Given adapter provides targeting capabilities
Then response reflects adapter-reported targeting dimensions

Given adapter fails
Then defaults to geo_countries=true, geo_regions=true
```
**Priority:** P2
**Grounded at 3.1.1:** The first sentence holds; the defaults do not. Targeting capability declaration lives at `media_buy.execution.targeting`, described "Targeting capabilities. If declared true/supported, buyer can use these targeting parameters and seller MUST honor them", with `geo_countries` and `geo_regions` as booleans alongside `geo_metros`, `geo_postal_areas`, `age_restriction`, `language`, `keyword_targets`, `negative_keywords`, and `geo_proximity` (repo=adcp ref=3.1.1 path=schemas/protocol/get-adcp-capabilities-response.json). But resolving that subtree, neither `geo_countries` nor `geo_regions` carries a JSON Schema `default`, neither is listed in any `required`, and `media_buy` and `execution` declare no `required` at all — 3.1.1 sets no default value for either and never prescribes what an agent should emit when an adapter lookup fails. Contrast `account.account_financials` and `account.sandbox`, which do carry `"default": false` in the same file, so the absence here is a deliberate silence, not an oversight. "Defaults to geo_countries=true, geo_regions=true on adapter failure" therefore grades our production fallback, not AdCP conformance; the capability-discovery storyboard asserts nothing about targeting (repo=adcp ref=3.1.1 path=universal/capability-discovery.yaml).

---

### content_standards_calibration_exemplars: Calibration Exemplars
**Obligation ID** CONSTR-CONTENT-STANDARDS-CALIBRATION-EXEMPLARS-01
**Layer** schema
**Requirement:** Optional. Pass/fail arrays of URL references or artifact objects (oneOf polymorphism). URL resolved to artifact on ingest.
**Scenario:**
```gherkin
Given pass exemplars with URL references
Then accepted and resolved to artifacts

Given pass exemplars with artifact objects
Then accepted directly
```
**Priority:** P3
**Grounded at 3.1.1:** Confirmed on the wire. `calibration_exemplars` is absent from the create request's `required` list (`["idempotency_key", "scope"]`, plus an `anyOf` over `policies` / `registry_policy_ids` that does not mention it), so it is optional; it is an object with `pass` and `fail` arrays whose items are literally `oneOf: [ URL-reference object, $ref content-standards/artifact.json ]` — the URL branch being `{ "type": { "const": "url" }, "value": { "format": "uri" }, "language" }` with `required: ["type", "value"]`, described "URL reference - specific page to fetch and evaluate", and the artifact branch "Full artifact with pre-extracted content (text, images, video, audio)" (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-request.json). The same oneOf pair appears on the update request (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-request.json). The resolve-on-ingest half is corroborated structurally: the persisted Content Standards object's `calibration_exemplars.pass`/`.fail` items are `$ref content-standards/artifact.json` **only** — the URL branch is gone from the stored shape (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json), and `artifact.json` requires `property_rid`, `artifact_id`, and `assets`, i.e. extracted content (repo=adcp ref=3.1.1 path=schemas/content-standards/artifact.json).

---

### content_standards_list_filters: Content Standards List Filters
**Obligation ID** CONSTR-CONTENT-STANDARDS-LIST-FILTERS-01
**Layer** behavioral
**Requirement:** Optional filters by channels (OR), languages (OR), countries (OR). Cross-dimension AND. No filters = all.
**Scenario:**
```gherkin
Given channels=["display"] and languages=["en"]
Then standards matching display AND en returned
```
**Priority:** P3
**Grounded at 3.1.1:** The filter surface holds; the boolean-combination semantics are not in 3.1.1. `list_content_standards` does take three optional array filters — `channels` (items `$ref enums/channels.json`, `minItems: 1`, "Filter by channel"), `languages` (BCP 47 tags), and `countries` (ISO 3166-1 alpha-2) — the request declares no `required` at all, and its only composition is `allOf: [$ref core/version-envelope.json]`, which contributes no further constraint (repo=adcp ref=3.1.1 path=schemas/content-standards/list-content-standards-request.json). The response returns "[a]rray of content standards configurations matching the filter criteria" (repo=adcp ref=3.1.1 path=schemas/content-standards/list-content-standards-response.json). What 3.1.1 does **not** state anywhere is that values within a filter are OR-combined, that the three dimensions are AND-combined, or that an empty request returns everything. The `_any`/`_all` suffixes that carry explicit OR/AND semantics exist on the *standard's own scope* (`channels_any` OR, `countries_all` AND, `languages_any` OR — repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-request.json), not on these filter names, and the content-standards storyboard exercises `list_content_standards` with no filters at all and asserts only schema conformance and the `context.correlation_id` echo (repo=adcp ref=3.1.1 path=specialisms/content-standards/index.yaml). Those combination rules therefore grade our production behavior.

---

### content_standards_policy: Content Standards Policy Text
**Obligation ID** CONSTR-CONTENT-STANDARDS-POLICY-01
**Layer** behavioral
**Requirement:** Required string containing the policy content. Free-form text describing acceptable/unacceptable content.
**Scenario:**
```gherkin
Given create with policy text
Then stored as current version
```
**Priority:** P2
**Grounded at 3.1.1:** A required free-form policy string does exist, but one level down from where this obligation puts it, and it is not unconditionally required. There is no `policy` field on the create request root; policy text lives inside each entry of the `policies` array, which is `$ref governance/policy-entry.json` — and there `policy` is required (`required: ["policy_id", "enforcement", "policy"]`) and is a free-form `string` with `maxLength: 5000` described "Natural language policy text describing what is required, prohibited, or recommended" (repo=adcp ref=3.1.1 path=schemas/governance/policy-entry.json). At the request level the create schema requires only `["idempotency_key", "scope"]` with a top-level `anyOf: [required policies, required registry_policy_ids]`, so a create that supplies `registry_policy_ids` alone carries no policy text at all — the request even keeps a vestigial note that "[t]he 'policy' field becomes optional when registry_policy_ids is provided", pointing at a root-level `policy` field that no longer exists at 3.1.1 (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-request.json). The "stored as current version" half is also not modeled on the wire: `update_content_standards` is described as "Creates a new version" (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-request.json), but the persisted Content Standards object carries no version field (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json) and `get_content_standards` accepts only `standards_id` with no version selector (repo=adcp ref=3.1.1 path=schemas/content-standards/get-content-standards-request.json) — reads implicitly return the current configuration; version history is not addressable.

---

### content_standards_scope: Content Standards Scope
**Obligation ID** CONSTR-CONTENT-STANDARDS-SCOPE-01
**Layer** schema
**Requirement:** languages_any required (minItems: 1). countries_all optional (AND). channels_any optional (OR).
**Scenario:**
```gherkin
Given scope with languages_any=[] (empty)
Then rejected (minItems: 1)

Given scope with countries_all=["US", "UK"]
Then standard applies in BOTH US AND UK
```
**Priority:** P2
**Grounded at 3.1.1:** All three clauses match the pinned schema verbatim. On `create_content_standards`, `scope` is itself required (`required: ["idempotency_key", "scope"]`) and the scope object declares `required: ["languages_any"]`, with `languages_any` an array of BCP 47 tags carrying `minItems: 1` — so `languages_any: []` is rejected exactly as the scenario states. `countries_all` is optional and documented "ISO 3166-1 alpha-2 country codes. Standards apply in ALL listed countries (AND logic)", which is the `["US","UK"]` → both-countries case; `channels_any` is optional and documented "Standards apply to ANY of the listed channels (OR logic)" (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-request.json). The same three fields with the same AND/OR wording and `minItems: 1` recur on the persisted object (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json). One scoping note that does not disturb the verdict: on `update_content_standards` the `scope` object omits the `required: ["languages_any"]` constraint, since updates send a partial scope (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-request.json).

---

### content_standards_standards_id: Content Standards ID
**Obligation ID** CONSTR-CONTENT-STANDARDS-STANDARDS-ID-01
**Layer** behavioral
**Requirement:** Stable identifier across versions. Same ID through updates. System-assigned on create.
**Scenario:**
```gherkin
Given create returns standards_id="std_1"
When update is called
Then response still has standards_id="std_1"
```
**Priority:** P2
**Grounded at 3.1.1:** Confirmed across the create/update pair and the graded storyboard. `create_content_standards` returns a system-assigned id: resolving the response's `oneOf`, the success branch has `required: ["standards_id"]` with `standards_id` described "Unique identifier for the created standards configuration" (repo=adcp ref=3.1.1 path=schemas/content-standards/create-content-standards-response.json), and the storyboard's expectation for that step is "standards_id: platform-assigned identifier" (repo=adcp ref=3.1.1 path=specialisms/content-standards/index.yaml). The id survives updates: `update_content_standards` is described "Creates a new version", takes `standards_id` — "ID of the standards configuration to update" (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-request.json) — and its success branch (again resolving the response `oneOf`) has `required: ["success", "standards_id"]` echoing "ID of the updated standards configuration", i.e. the same id, not a new one; the error branch instead surfaces `conflicting_standards_id` (repo=adcp ref=3.1.1 path=schemas/content-standards/update-content-standards-response.json). The storyboard grades exactly this stability by threading one `$context.content_standards_id` from create through `get_content_standards` and then `update_content_standards` (repo=adcp ref=3.1.1 path=specialisms/content-standards/index.yaml). `standards_id` is also the sole `required` field of the persisted object (repo=adcp ref=3.1.1 path=schemas/content-standards/content-standards.json).

---

### auth/principal_id: Discovery Authentication
**Obligation ID** CONSTR-AUTH-PRINCIPAL-ID-01
**Layer** behavioral
**Requirement:** Authentication optional for discovery (require_valid_token=false). Invalid tokens degraded to anonymous (MCP). A2A requires valid token if provided. No data scoping by identity.
**Scenario:**
```gherkin
Given invalid token via MCP on discovery endpoint
Then treated as anonymous, full data returned

Given invalid token via A2A on discovery endpoint
Then rejected with authentication error
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED — one of four clauses survives. "Authentication optional for discovery" HOLDS: `building/by-layer/L2/authentication.mdx` §"Public Operations (No Authentication Required)" lists `get_adcp_capabilities`, `list_creative_formats` and `get_products` as working "without credentials to enable discovery and evaluation". "Invalid tokens degraded to anonymous (MCP)" is FALSE: `enums/error-code.json` defines `AUTH_INVALID` as "Credentials were presented but rejected — revoked, malformed signature, or a key no longer in the seller's keystore. Sellers MUST return this code when an `Authorization` header was present but verification failed." That MUST carries no transport qualifier, so there is also no spec basis for the claimed MCP-vs-A2A asymmetry — `authentication.mdx` §"Error Responses" gives the same `AUTH_INVALID` shape for "Invalid or Expired Credentials" with no protocol split. "No data scoping by identity" is FALSE for at least `get_products`: the same §Public Operations warns that unauthenticated `get_products` may return "Partial catalog (standard products only)", "No pricing information or CPM details", "No custom product offerings". What 3.1.1 actually grades is narrower than the obligation: `universal/security.yaml` runs its unauth and invalid-credential probes (`probe_unauth`, `probe_invalid_api_key`) against a *protected* task (`$test_kit.auth.probe_task`, default `list_creatives`), so behavior on a discovery task with a bad token is ungraded and remains our production choice. (repo=adcp ref=3.1.1 path=../../docs/3.1.1/building/by-layer/L2/authentication.mdx; repo=adcp ref=3.1.1 path=schemas/enums/error-code.json; repo=adcp ref=3.1.1 path=universal/security.yaml)

---

### discovery_auth: Discovery Auth Pattern
**Obligation ID** CONSTR-DISCOVERY-AUTH-01
**Layer** behavioral
**Requirement:** Discovery endpoints allow anonymous access. Invalid tokens treated as absent. Identical data regardless of auth state.
**Scenario:**
```gherkin
Given authenticated caller on list_authorized_properties
Then receives same data as anonymous caller
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED, and the scenario's subject no longer exists. Clause 1 HOLDS — `building/by-layer/L2/authentication.mdx` §"Public Operations (No Authentication Required)" makes `get_adcp_capabilities`, `list_creative_formats` and `get_products` callable with no credentials, rationale "Publishers want potential buyers to discover their capabilities before establishing a business relationship." Clause 2, "invalid tokens treated as absent", is FALSE: `enums/error-code.json` `AUTH_INVALID` — "Sellers MUST return this code when an `Authorization` header was present but verification failed" — with no discovery carve-out. Clause 3, "identical data regardless of auth state", is FALSE as a general rule: the same §Public Operations states unauthenticated `get_products` may return a "Partial catalog (standard products only)" with "No pricing information or CPM details" and "No custom product offerings". The Gherkin's tool is gone: `protocol/get_adcp_capabilities.mdx` §"Migration from list_authorized_properties (v2)" states "The `list_authorized_properties` task was removed in v3", with its fields relocated to `media_buy.portfolio.*`. Re-anchor the scenario on `get_adcp_capabilities` before it can grade anything. (repo=adcp ref=3.1.1 path=../../docs/3.1.1/building/by-layer/L2/authentication.mdx; repo=adcp ref=3.1.1 path=schemas/enums/error-code.json; repo=adcp ref=3.1.1 path=../../docs/3.1.1/protocol/get_adcp_capabilities.mdx)

---

### property_type: Property Type Enum
**Obligation ID** CONSTR-PROPERTY-TYPE-01
**Layer** schema
**Requirement:** Enum for property types in property list definitions.
**Scenario:**
```gherkin
Given property_type is valid enum value
Then property list entry is valid
```
**Priority:** P3
**Grounded at 3.1.1:** HOLDS. `schemas/enums/property-type.json` is a closed `"type": "string"` enum of exactly ten values — `website`, `mobile_app`, `ctv_app`, `desktop_app`, `dooh`, `podcast`, `radio`, `linear_tv`, `streaming_audio`, `ai_assistant` — each with an `enumDescriptions` entry. It is wired into property-list definitions through `schemas/property/property-list-filters.json`, whose `property_types` array declares `"items": {"$ref": "/schemas/3.1.1/enums/property-type.json"}` with `minItems: 1`, so a non-enum value fails validation of any create/update/get property-list payload carrying filters. The prose filter table in `governance/property/tasks/property_lists.mdx` mirrors it ("`property_types` | string[] | Property types (website, mobile_app, ctv_app, etc.)"). (repo=adcp ref=3.1.1 path=schemas/enums/property-type.json; repo=adcp ref=3.1.1 path=schemas/property/property-list-filters.json; repo=adcp ref=3.1.1 path=../../docs/3.1.1/governance/property/tasks/property_lists.mdx)

---

### property_list_auth_token: Property List Auth Token
**Obligation ID** CONSTR-PROPERTY-LIST-AUTH-TOKEN-01
**Layer** behavioral
**Requirement:** Returned once in create response. Not in get/list/update/delete. min 32 chars. No recovery.
**Scenario:**
```gherkin
Given create_property_list succeeds
Then auth_token in response

Given get_property_list called
Then auth_token NOT in response
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED — the create-only/no-recovery half is spec-backed, the "min 32 chars" half is invented. `schemas/property/create-property-list-response.json` declares `auth_token` and lists it in `required: ["list", "auth_token"]`, described as "Token that can be shared with sellers to authorize fetching this list. Store this - it is only returned at creation time"; `governance/property/tasks/property_lists.mdx` repeats it normatively — "The `auth_token` is only returned when the list is created via `create_property_list`. Store it securely" — and the property-list task set defines no re-issue or recovery task, so "no recovery" HOLDS. Absence on the other tasks was verified by resolving composition: `get-`, `list-`, `update-` and `delete-property-list-response.json` each `allOf` only `core/version-envelope.json` (contributes `adcp_version`, `adcp_major_version`; itself composition-free) and `core/protocol-envelope.json` (contributes `context_id`/`context`/`task_id`/`status`/`message`/`timestamp`/`replayed`/`adcp_error`/`push_notification_config`/`governance_context`/`payload`; also composition-free) — neither declares `auth_token` — and the nested `list` is `property/property-list.json`, which is `additionalProperties: false` with no `auth_token` member. Caveat: those response envelopes are themselves `additionalProperties: true`, so a stray top-level `auth_token` is not *structurally* rejected; the prose Note is what forbids it. The length floor is FALSE: `auth_token` in `create-property-list-response.json` carries no `minLength`/`maxLength`/`pattern`, and neither does the `auth_token` on `core/property-list-ref.json`. Scoped to `schemas/property/` and `schemas/core/` there are exactly three `auth_token` sites (`property/create-property-list-response.json`, `core/property-list-ref.json`, `core/collection-list-ref.json`); bundle-wide there are more — notably `collection/create-collection-list-response.json`, whose token description does impose real MUSTs (secret-manager storage, per-seller issuance, no reuse across lists, no logging, revoke on delete) that the property-list token does not carry — but no `auth_token` anywhere in the bundle, including the `bundled/` mirrors, declares any length or pattern constraint. (repo=adcp ref=3.1.1 path=schemas/property/create-property-list-response.json; repo=adcp ref=3.1.1 path=schemas/property/get-property-list-response.json; repo=adcp ref=3.1.1 path=schemas/property/update-property-list-response.json; repo=adcp ref=3.1.1 path=schemas/property/delete-property-list-response.json; repo=adcp ref=3.1.1 path=schemas/property/list-property-lists-response.json; repo=adcp ref=3.1.1 path=schemas/property/property-list.json; repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json; repo=adcp ref=3.1.1 path=schemas/core/protocol-envelope.json; repo=adcp ref=3.1.1 path=schemas/core/property-list-ref.json; repo=adcp ref=3.1.1 path=schemas/collection/create-collection-list-response.json; repo=adcp ref=3.1.1 path=../../docs/3.1.1/governance/property/tasks/property_lists.mdx)

---

### property_list_base_properties: Base Properties Source
**Obligation ID** CONSTR-PROPERTY-LIST-BASE-PROPERTIES-01
**Layer** schema
**Requirement:** Discriminated union: publisher_tags (domain+tags), publisher_ids (domain+ids), identifiers (ids). Non-empty arrays. Omitted = entire catalog.
**Scenario:**
```gherkin
Given selection_type="publisher_tags" with empty tags array
Then rejected (non-empty required)
```
**Priority:** P2
**Grounded at 3.1.1:** HOLDS on all three clauses. `schemas/property/base-property-source.json` is a `oneOf` of exactly three branches under `"discriminator": {"propertyName": "selection_type"}`: "Publisher Tags Source" (`selection_type` const `publisher_tags`, `required: [selection_type, publisher_domain, tags]`), "Publisher Property IDs Source" (const `publisher_ids`, `required: [selection_type, publisher_domain, property_ids]`), and "Direct Identifiers Source" (const `identifiers`, `required: [selection_type, identifiers]`) — each branch `additionalProperties: false`. Non-empty is enforced per branch: `tags`, `property_ids` and `identifiers` all carry `minItems: 1`, so the scenario's `selection_type="publisher_tags"` with an empty `tags` array fails both the `minItems` and the branch. Omission semantics are stated identically on `schemas/property/property-list.json` and `schemas/property/create-property-list-request.json`: "If omitted, queries the agent's entire property database." The compliance storyboard exercises the `identifiers` branch — `specialisms/property-lists/index.yaml` step `create_inclusion_list` posts `base_properties: [{selection_type: identifiers, identifiers: [...]}]` and validates against `create-property-list-response.json`. (repo=adcp ref=3.1.1 path=schemas/property/base-property-source.json; repo=adcp ref=3.1.1 path=schemas/property/property-list.json; repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json; repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml)

---

### property_list_filters: Property List Filters
**Obligation ID** CONSTR-PROPERTY-LIST-FILTERS-01
**Layer** schema
**Requirement:** When present, both countries_all and channels_any required as non-empty arrays. Evaluated at resolution time.
**Scenario:**
```gherkin
Given filters with countries_all but no channels_any
Then rejected (both required)
```
**Priority:** P2
**Grounded at 3.1.1:** CORRECTED — "non-empty" and "evaluated at resolution time" hold, "both required" does not. `schemas/property/property-list-filters.json` is a plain `"type": "object"` with no `allOf`/`oneOf`/`anyOf` and no top-level `$ref` (its `$ref`s appear only inside `items`), so the absence of any `required` keyword is real: every one of `countries_all`, `channels_any`, `property_types`, `feature_requirements`, `exclude_identifiers` is optional, and nothing couples `countries_all` to `channels_any`. The non-empty clause HOLDS — `countries_all` (items `pattern: ^[A-Z]{2}$`) and `channels_any` (items `$ref` `enums/channels.json`) each carry `minItems: 1`. Resolution timing HOLDS — `governance/property/tasks/property_lists.mdx` §Filters: "Filters are applied when the list is resolved (via `get_property_list`)". Beware an internal contradiction in that same prose file: its §Filters table marks both fields "Optional — omit for global lists" / "Optional — omit for all-channel lists", while a stale §"Required Filters" section still asserts "Every property list must include at least: One country in `countries_all` … One channel in `channels_any`". The schema and the field-level table agree against the stale section, so the Gherkin (`countries_all` without `channels_any` ⇒ rejected) is not enforceable at 3.1.1 and is not graded by `specialisms/property-lists/index.yaml`. (repo=adcp ref=3.1.1 path=schemas/property/property-list-filters.json; repo=adcp ref=3.1.1 path=../../docs/3.1.1/governance/property/tasks/property_lists.mdx; repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml)

---

### property_list_list_id: Property List ID
**Obligation ID** CONSTR-PROPERTY-LIST-LIST-ID-01
**Layer** behavioral
**Requirement:** System-assigned unique identifier. Used for get/update/delete. Must exist within tenant for operations.
**Scenario:**
```gherkin
Given list_id not found in tenant
Then LIST_NOT_FOUND returned
```
**Priority:** P1
**Grounded at 3.1.1:** CORRECTED — the identifier semantics hold, the error code is wrong. System-assigned and required: `schemas/property/property-list.json` has `required: ["list_id", "name"]` with `list_id` described "Unique identifier for this property list" (`x-entity: property_list`); `specialisms/property-lists/index.yaml` captures it via `context_outputs: [{path: list.list_id}]` and asserts `field_present` on `list.list_id` with the description "Governance agent assigns list_id — must be echoed in get/update/delete". Used for the three operations: `list_id` is `required` on `get-property-list-request.json`, `update-property-list-request.json` and `delete-property-list-request.json`. The scenario's `LIST_NOT_FOUND` is FALSE at the task-error layer. `schemas/enums/error-code.json` — a flat string enum, no composition — does not contain `LIST_NOT_FOUND`; its `REFERENCE_NOT_FOUND` entry names this case explicitly: "Generic fallback for a referenced identifier … Use when no resource-specific not-found code applies (e.g., property lists, …). Typed parameters that lack a dedicated standard code MUST also use REFERENCE_NOT_FOUND rather than minting a custom *_NOT_FOUND code." `governance/property/tasks/property_lists.mdx` §Error Codes agrees: "`REFERENCE_NOT_FOUND` | Property list ID doesn't exist, or the caller lacks access. Returned uniformly for both cases … Sellers MUST NOT distinguish 'exists but unauthorized' from 'does not exist.'" `LIST_NOT_FOUND` survives only inside `schemas/property/property-error.json`, a per-property error object (`enum: [PROPERTY_NOT_FOUND, PROPERTY_NOT_MONITORED, LIST_NOT_FOUND, LIST_ACCESS_DENIED, METHODOLOGY_NOT_SUPPORTED, JURISDICTION_NOT_SUPPORTED]`), not a task-envelope code. Note the uniform-response MUST also kills the obligation's "must exist within tenant" framing as an observable distinction — a cross-tenant list and a nonexistent list MUST be indistinguishable. (repo=adcp ref=3.1.1 path=schemas/property/property-list.json; repo=adcp ref=3.1.1 path=schemas/property/get-property-list-request.json; repo=adcp ref=3.1.1 path=schemas/property/update-property-list-request.json; repo=adcp ref=3.1.1 path=schemas/property/delete-property-list-request.json; repo=adcp ref=3.1.1 path=schemas/enums/error-code.json; repo=adcp ref=3.1.1 path=schemas/property/property-error.json; repo=adcp ref=3.1.1 path=../../docs/3.1.1/governance/property/tasks/property_lists.mdx; repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml)

---

### property_list_name: Property List Name
**Obligation ID** CONSTR-PROPERTY-LIST-NAME-01
**Layer** behavioral
**Requirement:** Required string for property list. Used in name_contains search filter.
**Scenario:**
```gherkin
Given name_contains="sports" in list filter
Then only lists with "sports" in name returned
```
**Priority:** P3
**Grounded at 3.1.1:** HOLDS, with the filter *semantics* left to us. `name` is a required string on both the resource and the create call: `schemas/property/property-list.json` declares `"name": {"type": "string", "description": "Human-readable name for the list"}` in `required: ["list_id", "name"]`, and `schemas/property/create-property-list-request.json` has `required: ["idempotency_key", "name"]`. The search filter exists: `schemas/property/list-property-lists-request.json` declares `"name_contains": {"type": "string", "description": "Filter to lists whose name contains this string"}`, echoed by the prose request example `{"name_contains": "UK", "pagination": {"max_results": 50}}` in `governance/property/tasks/property_lists.mdx`. Note the storyboard sends `name_contains: "Acme Outdoor"` on `specialisms/property-lists/index.yaml` step `list_property_lists` but its `validations` are only `response_schema` plus the `context`/`correlation_id` echo — no assertion that returned names actually contain the needle. So the substring-matching behavior in the Gherkin grades our production filter, not AdCP conformance. (repo=adcp ref=3.1.1 path=schemas/property/property-list.json; repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json; repo=adcp ref=3.1.1 path=schemas/property/list-property-lists-request.json; repo=adcp ref=3.1.1 path=../../docs/3.1.1/governance/property/tasks/property_lists.mdx; repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml)

---

### property_list_pagination: Property List Pagination
**Obligation ID** CONSTR-PROPERTY-LIST-PAGINATION-01
**Layer** schema
**Requirement:** max_results 1-10000, default 1000. Cursor-based pagination for resolved identifiers.
**Scenario:**
```gherkin
Given max_results=0
Then rejected (minimum: 1)

Given max_results=10001
Then rejected (maximum: 10000)
```
**Priority:** P2
**Grounded at 3.1.1:** HOLDS for the surface the obligation names — resolved identifiers on `get_property_list` — but the window is task-local, so scope it. `schemas/property/get-property-list-request.json` defines an inline `pagination` object (`additionalProperties: false`) whose `max_results` is `"type": "integer", "minimum": 1, "maximum": 10000, "default": 1000`, alongside `"cursor": {"type": "string", "description": "Opaque cursor from a previous response to fetch the next page"}`; its own description states the reason — "Uses higher limits than standard pagination because property lists can contain tens of thousands of identifiers." So `max_results: 0` and `max_results: 10001` are both schema-rejected exactly as the scenario says. Correction to guard against over-generalizing: `list_property_lists` does NOT share that window — `schemas/property/list-property-lists-request.json` `$ref`s `core/pagination-request.json`, which is `minimum: 1, maximum: 100, default: 50`. The cursor↔`has_more` invariant on the list side is separately graded by `universal/property-lists-pagination-integrity.yaml` ("when `has_more` is true the `cursor` MUST be present … when `has_more` is false the `cursor` MUST be absent"), which notes JSON Schema does not gate the two fields against each other. (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-request.json; repo=adcp ref=3.1.1 path=schemas/property/list-property-lists-request.json; repo=adcp ref=3.1.1 path=schemas/core/pagination-request.json; repo=adcp ref=3.1.1 path=schemas/core/pagination-response.json; repo=adcp ref=3.1.1 path=universal/property-lists-pagination-integrity.yaml)

---

### property_list_resolve: Property List Resolution
**Obligation ID** CONSTR-PROPERTY-LIST-RESOLVE-01
**Layer** behavioral
**Requirement:** resolve=true (default) evaluates filters. resolve=false returns metadata only.
**Scenario:**
```gherkin
Given resolve=false
Then identifiers not resolved, only metadata returned
```
**Priority:** P2
**Grounded at 3.1.1:** HOLDS. `schemas/property/get-property-list-request.json` declares `"resolve": {"type": "boolean", "description": "Whether to apply filters and return resolved identifiers (default: true)", "default": true}`, so `resolve=true` is the default and it is precisely the filter-application switch. The metadata-only shape is spec-defined too: `schemas/property/get-property-list-response.json` has `required: ["list"]` with `list` described "The property list metadata (always returned)", while `identifiers` is optional and described "Resolved identifiers that passed filters (if resolve=true)" — as are the resolution-only companions `resolved_at`, `cache_valid_until` and `coverage_gaps`. `governance/property/tasks/property_lists.mdx` shows the exact scenario end to end: a "Request - Get Metadata Only" with `{"list_id": "pl_abc123", "resolve": false}` whose "Response (Metadata Only)" carries only the `list` object (base_properties, filters, timestamps, property_count) and no `identifiers`/`resolved_at`. The same file's webhook flow confirms the inverse direction — "Recipient calls get_property_list(list_id, resolve=true)". (repo=adcp ref=3.1.1 path=schemas/property/get-property-list-request.json; repo=adcp ref=3.1.1 path=schemas/property/get-property-list-response.json; repo=adcp ref=3.1.1 path=../../docs/3.1.1/governance/property/tasks/property_lists.mdx)

---

### property_list_webhook_url: Property List Webhook URL
**Obligation ID** CONSTR-PROPERTY-LIST-WEBHOOK-URL-01
**Layer** behavioral
**Requirement:** Only in update (not create). Empty string removes webhook. URI format when set.
**Scenario:**
```gherkin
Given webhook_url in create request
Then rejected (not in create schema)

Given webhook_url="" in update
Then previously set webhook removed
```
**Priority:** P2
**Grounded at 3.1.1:** Partly true. `webhook_url` (`"type": "string"`, `"format": "uri"`, description "Update the webhook URL for list change notifications (set to empty string to remove)") is declared on the update request — `repo=adcp ref=3.1.1 path=schemas/property/update-property-list-request.json` — and on the property-list resource itself ("URL to receive notifications when the resolved list changes", `repo=adcp ref=3.1.1 path=schemas/property/property-list.json`), but is absent from the create request, whose sole composition is `"allOf": [{"$ref": "/schemas/3.1.1/core/version-envelope.json"}]`, contributing only `adcp_version` / `adcp_major_version`: `repo=adcp ref=3.1.1 path=schemas/property/create-property-list-request.json` (`"required": ["idempotency_key", "name"]`), `repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json`. The scenario's second half is FALSE: create-property-list-request.json sets `"additionalProperties": true`, so a stray `webhook_url` on create VALIDATES (and is ignored) rather than being rejected — nothing in the pinned schema rejects it. The empty-string-removes and uri-format halves exist only as schema description text and are ungraded: the pinned storyboard's sole `update_property_list` step sends `list_id`, `account`, `base_properties`, `idempotency_key`, `context` and never `webhook_url` — `repo=adcp ref=3.1.1 path=specialisms/property-lists/index.yaml`. The "rejected on create" behavior therefore grades our own strictness, not AdCP conformance.

---

### creative_scope: Cross-Principal Creative Isolation
**Obligation ID** CONSTR-CREATIVE-SCOPE-01
**Layer** behavioral
**Requirement:** Triple key: tenant_id + principal_id + creative_id. Cross-principal collision = silent create.
**Scenario:**
```gherkin
Given same creative_id under different principal
Then new creative created silently (no cross-visibility)
```
**Priority:** P0
**Grounded at 3.1.1:** The shape of the claim holds but the key is named wrong. AdCP scopes the creative library by `account`, not by `tenant_id` + `principal_id` — neither of those terms occurs anywhere in the 758-file pinned bundle. `sync_creatives` lists `account` in `"required": ["idempotency_key", "account", "creatives"]` with the description "Account that owns these creatives", and the request itself is titled as having "upsert semantics" — `repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json`. `creative_id` is described as "Unique identifier for the creative" with no cross-account uniqueness constraint and is required on every creative asset (`"required": ["creative_id", "name", "assets"]`, plus a root `oneOf` over format_id/format_kind that adds no identity fields) — `repo=adcp ref=3.1.1 path=schemas/core/creative-asset.json`. So the same `creative_id` under a different account is a distinct creative that upsert creates rather than collides with; the "silent create, no cross-visibility" outcome is consistent with 3.1.1, but our tenant+principal pair is an implementation of the spec's single `account` dimension, and no pinned storyboard grades a cross-account `creative_id` collision.

---

### format_id_validation: Creative Format Validation
**Obligation ID** CONSTR-FORMAT-ID-VALIDATION-01
**Layer** behavioral
**Requirement:** format_id required. Non-HTTP agent_url skips external validation. HTTP agent checked for reachability + format registration.
**Scenario:**
```gherkin
Given missing format_id
Then CREATIVE_FORMAT_REQUIRED error

Given unknown format on HTTP agent
Then CREATIVE_FORMAT_UNKNOWN error
```
**Priority:** P1
**Grounded at 3.1.1:** Both load-bearing claims contradict the pin. (1) `format_id` is NOT required. `core/creative-asset.json` has `"required": ["creative_id", "name", "assets"]` and a root `oneOf` of exactly two branches — "Legacy creative (named-format reference)" `{required: [format_id], not: {required: [format_kind]}}` and "3.1+ creative (canonical format kind)" `{required: [format_kind], not: {required: [format_id]}}` — i.e. exactly one of `format_id` XOR `format_kind`, so a creative with only `format_kind` is valid: `repo=adcp ref=3.1.1 path=schemas/core/creative-asset.json`. (2) Neither `CREATIVE_FORMAT_REQUIRED` nor `CREATIVE_FORMAT_UNKNOWN` exists in the pinned 92-value error enum — `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json`; the graded code for an unbuildable format target is `FORMAT_NOT_SUPPORTED`, asserted at the unsupported-target step of `repo=adcp ref=3.1.1 path=domains/creative/scenarios/canonical_supported_formats.yaml`. (3) The HTTP-vs-non-HTTP `agent_url` reachability split is spec-silent: `core/format-id.json` requires `["agent_url", "id"]`, types `agent_url` as `"format": "uri"`, and mandates only canonicalization before equality comparison — no reachability probe, no registration lookup — `repo=adcp ref=3.1.1 path=schemas/core/format-id.json`.

---

### generative_build: Generative Creative Build
**Obligation ID** CONSTR-GENERATIVE-BUILD-01
**Layer** behavioral
**Requirement:** Generative when output_format_ids truthy. Prompt priority: assets > inputs > name. Update without prompt = skip. GEMINI_API_KEY required.
**Scenario:**
```gherkin
Given generative format without GEMINI_API_KEY
Then CREATIVE_GEMINI_KEY_MISSING error
```
**Priority:** P2
**Grounded at 3.1.1:** The trigger condition is legacy-only at the pin and the error is not an AdCP code. `output_format_ids` on `core/format.json` is marked `"deprecated": true` with "**DEPRECATED in 3.1. Removed at 4.0.** Use `list_transformers` instead"; its retained legacy reading — "array of format IDs this format can produce as output; when present, indicates this format can build creatives in these output formats" — is exactly the truthiness test the obligation uses, and readers "MUST continue to honor this field when present" through 3.x, so keying on it is still conformant at 3.1.1 but is the deprecated surface: `repo=adcp ref=3.1.1 path=schemas/core/format.json`. The 3.1 replacement hangs build capability on the transformer, which lists `output_format_ids` in `"required": ["transformer_id", "name", "output_format_ids"]`: `repo=adcp ref=3.1.1 path=schemas/core/transformer.json`. The rest of the obligation is spec-silent and grades our own behavior: `CREATIVE_GEMINI_KEY_MISSING` is not among the 92 pinned error codes (a bundle-wide scan for 'GEMINI' returns 0 hits) — `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json` — and no pinned schema or storyboard specifies a prompt-source precedence (assets > inputs > name), a skip-on-update-without-prompt rule, or any vendor API-key precondition.

---

### assignment_package: Assignment Package Validation
**Obligation ID** CONSTR-ASSIGNMENT-PACKAGE-01
**Layer** behavioral
**Requirement:** Package lookup joins MediaPackage to MediaBuy filtered by tenant. Strict/lenient per validation_mode. Idempotent upsert (weight=100).
**Scenario:**
```gherkin
Given package not found in tenant's media buys (strict mode)
Then ToolError raised

Given existing assignment for same creative-package
Then weight reset to 100 (idempotent)
```
**Priority:** P1
**Grounded at 3.1.1:** One clause holds, one is contradicted, one is spec-silent. HOLDS: strict/lenient is the pinned contract — `validation_mode` on `sync_creatives` defaults to `"strict"` with "'strict' fails entire sync on any validation error. 'lenient' processes valid creatives and reports errors" (`repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json`), over the two-value enum at `repo=adcp ref=3.1.1 path=schemas/enums/validation-mode.json`. CONTRADICTED: the idempotent-upsert "weight reset to 100" outcome has no pinned basis — both assignment shapes bound weight to `minimum: 0, maximum: 100` and state "When omitted, the creative receives equal rotation with other unweighted creatives", with no `default` keyword and no re-assignment reset rule; 100 is the ceiling, not a default (`repo=adcp ref=3.1.1 path=schemas/core/creative-assignment.json`, and the inline `assignments[]` item in `repo=adcp ref=3.1.1 path=schemas/creative/sync-creatives-request.json`, whose only required members are `creative_id` and `package_id`). SPEC-SILENT: the MediaPackage-to-MediaBuy join filtered by tenant, and raising `ToolError`, are our internals — AdCP scopes by `account` (required on `sync_creatives`) and knows no tenant, and `ToolError` is a transport artifact with no counterpart in the pinned error enum.

---

### assignment_format: Assignment Format Compatibility
**Obligation ID** CONSTR-ASSIGNMENT-FORMAT-01
**Layer** behavioral
**Requirement:** URL normalization (strip trailing "/" and "/mcp"). Both agent_url AND format_id must match. Empty format_ids = all allowed.
**Scenario:**
```gherkin
Given agent_url "http://agent.com/" and product expects "http://agent.com"
Then URL normalization makes them match

Given product has empty format_ids
Then all creative formats allowed
```
**Priority:** P1
**Grounded at 3.1.1:** The comparison model holds, the normalization rules and the wildcard do not. HOLDS: format identity IS the pair — `core/format-id.json` sets `"required": ["agent_url", "id"]` and states "Callers comparing two `format-id` values MUST canonicalize `agent_url` per the AdCP URL canonicalization rules before treating two formats as the same" (`repo=adcp ref=3.1.1 path=schemas/core/format-id.json`). CORRECTED: the pinned canonicalization is not "strip trailing '/' and '/mcp'". `http://agent.com` and `http://agent.com/` do compare equal, but via the empty-path rule, pinned as the vector `empty-path-with-authority-becomes-slash` — `input_url: https://seller.example.com?x=1` → `expected_target_uri: https://seller.example.com/?x=1` — while sibling vectors preserve path bytes (`consecutive-slashes-preserved`: `/a//b` stays `/a//b`); there is no vector or rule that strips a trailing slash from a non-empty path or removes an `/mcp` suffix, and stripping either would be an extra transformation the algorithm forbids: `repo=adcp ref=3.1.1 path=test-vectors/request-signing/canonicalization.json`. FALSE: "empty format_ids = all allowed" is contradicted — `core/product.json` carries a root `anyOf` of `{required: [format_ids]}` OR `{required: [format_options]}`, and `format_ids` states "Products MUST carry `format_ids`, `format_options`, or BOTH; at least one is required", so a product with no declared formats is invalid rather than a wildcard: `repo=adcp ref=3.1.1 path=schemas/core/product.json`.

---

### media_buy_status: Media Buy Status Transition
**Obligation ID** CONSTR-MEDIA-BUY-STATUS-01
**Layer** behavioral
**Requirement:** draft + approved_at transitions to pending_creatives on assignment. Draft without approved_at stays draft. Non-draft unchanged.
**Scenario:**
```gherkin
Given draft media buy with approved_at set
When creative assigned
Then status becomes pending_creatives
```
**Priority:** P1
**Grounded at 3.1.1:** No part of this transition exists at the pin. There is no `draft` media-buy status: the enum is exactly `["pending_creatives", "pending_start", "active", "paused", "completed", "rejected", "canceled"]`, and `pending_creatives` is defined as "**Buyer-side action required.** The media buy is approved by the seller and has no creatives assigned — the buyer must attach creatives via `sync_creatives` before the buy can serve" — i.e. it is the state a buy is in BEFORE creatives are attached, so assigning a creative moves a buy out of it, not into it: `repo=adcp ref=3.1.1 path=schemas/enums/media-buy-status.json`. There is also no `approved_at` on the resource: `core/media-buy.json` exposes `[media_buy_id, account, status, health, impairments, rejection_reason, confirmed_at, cancellation, total_budget, packages, context, invoice_recipient, creative_deadline, revision, created_at, updated_at, ext]` with `"required": ["media_buy_id", "status", "confirmed_at", "revision", "total_budget", "packages"]`, and its single `allOf` member is a conditional (`if confirmed_at is null then status MUST NOT be "active"` and packages MUST NOT carry `committed_metrics`) that contributes no fields — `repo=adcp ref=3.1.1 path=schemas/core/media-buy.json`; a bundle-wide scan finds `approved_at` only on `brand/creative-approval-response.json`. The pinned lifecycle graph runs create → pause/resume → cancel with terminal-state enforcement and never mentions a draft state: `repo=adcp ref=3.1.1 path=domains/media-buy/state-machine.yaml`. Our draft/approved_at machinery is internal and grades our own behavior.

---

### minimum_spend: Minimum Spend Per Package
**Obligation ID** CONSTR-MINIMUM-SPEND-01
**Layer** schema
**Requirement:** Product min_spend_per_package (primary) or tenant min_package_budget (fallback). Neither = skipped.
**Scenario:**
```gherkin
Given product min_spend=500 and budget=499.99
Then rejected (BUDGET_BELOW_MINIMUM)
```
**Priority:** P1
**Grounded at 3.1.1:** The primary source is real but sits one level lower than stated, the error code is wrong, and the behavior is ungraded. `min_spend_per_package` (`"type": "number"`, `"minimum": 0`, "Minimum spend requirement per package using this pricing option, in the specified currency") is a PRICING-OPTION field, not a product field — it appears on all nine branch schemas of the `oneOf` at `repo=adcp ref=3.1.1 path=schemas/core/pricing-option.json` (which declares no `properties` of its own — only `discriminator` + a nine-way `$ref` `oneOf` to cpm/vcpm/cpc/cpcv/cpv/cpp/cpa/flat-rate/time), e.g. `repo=adcp ref=3.1.1 path=schemas/pricing-options/cpm-option.json`, where it is optional (`"required": ["pricing_option_id", "pricing_model", "currency"]`), so "neither set = skipped" is consistent. FALSE: `BUDGET_BELOW_MINIMUM` is not among the 92 pinned error codes; the pinned code is `BUDGET_TOO_LOW` — "Budget is below the seller's minimum. Recovery: correctable (increase budget or check capabilities.media_buy.limits)." — `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json`. UNGRADED: no pinned storyboard exercises a below-minimum budget; `BUDGET_TOO_LOW` appears exactly once in the compliance tree, as a permitted alternative in `allowed_values: ["VALIDATION_ERROR", "INVALID_REQUEST", "BUDGET_TOO_LOW"]` on the *negative*-budget step (`budget: -500`) of `repo=adcp ref=3.1.1 path=universal/error-compliance.yaml`. SPEC-SILENT: the tenant-level `min_package_budget` fallback has no counterpart (0 hits bundle-wide); the pin's out-of-band minimum lives on seller capabilities, not on a tenant record.

---

### persistence_timing: Adapter Atomicity Gate
**Obligation ID** CONSTR-PERSISTENCE-TIMING-01
**Layer** behavioral
**Requirement:** Auto-approval: persist only after adapter success. Adapter failure = no records. Manual approval: persist in pending before adapter.
**Scenario:**
```gherkin
Given auto-approval and adapter fails
Then no database records created
```
**Priority:** P0
**Grounded at 3.1.1:** AdCP 3.1.1 says nothing about when a seller writes its own database relative to calling a downstream ad server. Resolving the full composition of the create/update request and response schemas ($ref/allOf expanded transitively — 147 schemas reached) surfaces no persistence-ordering or all-or-nothing language; the only atomicity requirement anywhere in that graph is optimistic concurrency on `update-media-buy-request.json`'s `revision` ("sellers MUST reject the update with CONFLICT if the media buy's current revision does not match, and MUST enforce that comparison atomically with the write"), which constrains compare-and-write, not write ordering against a downstream call: `repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json`. The closest pinned side-effect contract is replay semantics, where `universal/idempotency.yaml` requires a replayed call to return "the same response — same media_buy_id, no new side effects" and "No new side effects (no duplicate audit log entry or resource mutation)" — a statement about repeats, not about a first attempt that fails downstream: `repo=adcp ref=3.1.1 path=universal/idempotency.yaml`. The failure-path storyboard grades only the returned envelope (code, recovery, context echo) and never re-reads state to assert that no record was created: `repo=adcp ref=3.1.1 path=universal/error-compliance.yaml`. The approval axis the pin does model is the `media_buy.creative_approval_mode: auto_approve` capability gate, which selects which storyboard applies rather than prescribing write ordering: `repo=adcp ref=3.1.1 path=domains/media-buy/state-machine.yaml`. This obligation therefore grades our own production behavior, not AdCP conformance.

---

### adapter_dispatch: Partial Update Semantics
**Obligation ID** CONSTR-ADAPTER-DISPATCH-01
**Layer** behavioral
**Requirement:** Present fields modified, omitted fields unchanged. At least one field required.
**Scenario:**
```gherkin
Given update with no updatable fields
Then rejected (EMPTY_UPDATE)
```
**Priority:** P1
**Grounded at 3.1.1:** First half holds, second half does not. HOLDS: sparse-patch semantics are pinned at the package level — `package-update.json` states "Identifies package by package_id and specifies fields to modify. Fields not present are left unchanged", with `"required": ["package_id"]` and a root `not` constraint rejecting fully-immutable fields (product_id, format_ids, format_option_refs, format_kind, params, pricing_option_id): `repo=adcp ref=3.1.1 path=schemas/media-buy/package-update.json`. FALSE: "at least one field required" is not enforced and `EMPTY_UPDATE` is not an AdCP code. `update-media-buy-request.json` requires only `["idempotency_key", "account", "media_buy_id"]`; its sole composition is `"allOf": [{"$ref": "/schemas/3.1.1/core/version-envelope.json"}]` (which contributes only `adcp_version`/`adcp_major_version`) and it carries no `anyOf`/`oneOf`/`minProperties` demanding a mutable field, so a request naming just the buy validates: `repo=adcp ref=3.1.1 path=schemas/media-buy/update-media-buy-request.json`, `repo=adcp ref=3.1.1 path=schemas/core/version-envelope.json`. `EMPTY_UPDATE` does not appear anywhere in the bundle and is absent from the 92-value enum at `repo=adcp ref=3.1.1 path=schemas/enums/error-code.json`; rejecting a no-op update grades our own strictness.

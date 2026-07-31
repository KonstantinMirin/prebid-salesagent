# Re-pin: `@T-UC-004-storyboard-vendor-metric-end-to-end`

Scenario: "Vendor metric accountability -- declaration on product, filter at discovery, emission in delivery"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-004-deliver-media-buy-metrics.feature:1357`

---

## 1. VERDICT

**GRADED — but only one of its three phases can be green today.**

The storyboard is real, it is at 3.1.1, it lives in a tier we declare (`protocols/media-buy`, and we
declare `supported_protocols=[media_buy]`), its agent gate is `sells_media` — not a specialism we lack.
So the `@storyboard-v3.1` tag is **justified** and stays. This is on our conformance path.

What is not true is the scenario as written. All three of its lifecycle phases are graded by
`validations:` blocks, and **two of the three are impossible against current production**:

| Storyboard phase | Graded? | Production | Verdict |
|---|---|---|---|
| 1. `reporting_capabilities.vendor_metrics` declared → echoed at `get_products` | yes, 6 checks | works, byte-exact, all 3 transports | **GREEN — keep** |
| 2. `filters.required_vendor_metrics` excludes non-matching products | yes, via check #2 | filter is **silently ignored** | **RED — ticket** |
| 3. `by_package[].vendor_metric_values` emitted in delivery | yes, 5 checks | field does not exist on our model | **RED — ticket** |

The scenario is also **doubly dormant** right now, which is why nobody noticed:

```
XFAIL ...test_vendor_metric_accountability__...[mcp|a2a|rest]
  Step definition not found: Given "the seller's product declared
  reporting_capabilities.vendor_metrics for vendor "attentionvendor.example"..."
```

`grep -rn vendor_metric src/` → **0 hits.** Not one step definition, not one line of production code.
And even once steps exist, `tests/bdd/conftest.py::_detect_delivery_harness` routes every UC-004 tag
that is not `@webhook`/`@webhook-reliability`/`webhook-creds` to `"poll"` → `DeliveryPollEnv`, which
dispatches `_get_media_buy_delivery_impl` **only**. A `get_products` scenario cannot run there.
See §6 for the one-line routing fix.

I verified every green claim by executing it against `ProductEnv` on mcp + a2a + rest with a real
Postgres. Nothing below is inferred from types.

---

## 2. Real binding at 3.1.1

### What the footer points at

The scenario **has no `@source` footer of its own** (one of the 11). The `@source` line sitting
immediately above its tag block —

```
tests/bdd/features/BR-UC-004-deliver-media-buy-metrics.feature:1354
    # @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/vendor_metric_accountability.yaml
```

— belongs to the **previous** scenario (`@T-UC-004-storyboard-required-metrics-end-to-end-accountability`,
the `measurement_accountability` one). That is the systematic off-by-one from the brief, caught in the
act: the neighbour is citing **my** storyboard. So this scenario's binding was not merely stale, it was
**taken by the scenario above it**. Both need fixing; I only propose mine.

### The true binding

```
repo=adcp ref=v3.1.1 commit=467fd93d7
path=static/compliance/source/protocols/media-buy/scenarios/vendor_metric_accountability.yaml
```

Verified to exist at that tag and to be byte-identical to the built artifact:

```
$ git ls-tree v3.1.1 static/compliance/source/protocols/media-buy/scenarios/ --name-only | grep vendor
static/compliance/source/protocols/media-buy/scenarios/vendor_metric_accountability.yaml
$ diff <(git show v3.1.1:static/.../vendor_metric_accountability.yaml) \
       dist/compliance/3.1.1/protocols/media-buy/scenarios/vendor_metric_accountability.yaml
IDENTICAL
```

**Which storyboard actually grades this** (the brief flagged three candidates):

- `vendor_metric_accountability.yaml` — **this one.** `title: "End-to-end vendor-metric accountability:
  declaration → filter → emission"`, `capabilities: [sells_media]`. Exactly the scenario's three-piece prose.
- `vendor_metric_optimization_flow.yaml` — `optimization_goal.kind: "vendor_metric"` accept/reject.
  Gated on `capabilities: [sells_media]` but the whole storyboard is about a bidding-side capability we
  do not implement. **Not ours, not this scenario.**
- `vendor_metric_catalog_precondition.yaml` — explicitly gated
  `capabilities: [sells_media, supports_vendor_metric_optimization]`. We declare no such capability
  (`src/core/tools/capabilities.py:271-272` declares only `supported_protocols=[media_buy]`,
  `specialisms=[sales_non_guaranteed]`). **Off our conformance path entirely.**

### Tier

`protocols/media-buy/` — a protocol tier we declare. The 3.1.1 dist also carries a byte-identical copy
under `domains/media-buy/` (`diff` → identical); the v3.1.1 **source** tree has only
`protocols/ specialisms/ test-kits/ test-vectors/ universal/`, so `domains/` is a build-time alias.
Cite the `protocols/` source path — that is the one that exists at the tag.

### Graded `validations:`, verbatim

**Phase 1** — `discover_with_required_vendor_metrics` / step `get_products_required_vendor_metrics`,
`dist/compliance/3.1.1/protocols/media-buy/scenarios/vendor_metric_accountability.yaml:148-165`:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-products-response.json schema"
          - check: field_present
            path: "products[0].product_id"
            description: "At least one product matched the required_vendor_metrics filter"
          - check: field_present
            path: "products[0].reporting_capabilities.vendor_metrics"
            description: "Matched product declares vendor_metrics in reporting_capabilities"
          - check: field_present
            path: "products[0].reporting_capabilities.vendor_metrics[0].vendor.domain"
            description: "Each declared vendor metric entry carries a vendor domain"
          - check: field_present
            path: "products[0].reporting_capabilities.vendor_metrics[0].metric_id"
            description: "Each declared vendor metric entry carries a metric_id"
          - check: field_present
            path: "products[0].pricing_options[0].fixed_price"
            description: "The captured pricing option is fixed-price; fixed-price storyboards do not send bid_price"
```

**Phase 3** — `simulate_and_validate_vendor_metrics` / step `get_delivery_with_vendor_metrics`,
same file `:276-293`:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-media-buy-delivery-response.json schema"
          - check: field_present
            path: "media_buy_deliveries[0].by_package[0].vendor_metric_values"
            description: "by_package[0] includes vendor_metric_values — vendor metric emission contract honored"
          - check: field_present
            path: "media_buy_deliveries[0].by_package[0].vendor_metric_values[0].vendor.domain"
            description: "Each vendor_metric_value entry carries a vendor domain"
          - check: field_present
            path: "media_buy_deliveries[0].by_package[0].vendor_metric_values[0].metric_id"
            description: "Each vendor_metric_value entry carries a metric_id"
          - check: field_present
            path: "media_buy_deliveries[0].by_package[0].vendor_metric_values[0].value"
            description: "Each vendor_metric_value entry carries a value"
          - check: field_present
            path: "media_buy_deliveries[0].by_package[0].vendor_metric_values[0].measurable_impressions"
            description: "Coverage denominator is present — buyers can compute vendor measurement coverage rate"
```

Also graded, and relevant to scope: `:204-209` (create_media_buy → `field_present media_buy_id`) and
`:249-253` (`comply_test_controller` → `field_value success == true`).

**Not graded — prose only.** The de-duplication rule the scenario's fourth Then asserts
("MUST NOT emit duplicate rows for the same tuple") appears **only** in the storyboard `narrative:` at
`:218-222` and in the phase narrative — there is no `validations:` entry for it anywhere in the file.
It is normative in the **schema** (§3), but it is **ungraded by the storyboard**.

`required_tools:` lists `comply_test_controller` (`:11`), which we do not implement
(`grep -rn comply_test_controller src/` → 0). Phases 2 and 3 of the storyboard cannot be driven against
us at all until that exists or the BDD harness substitutes for it.

---

## 3. Schema constraints at 3.1.1

All quotes: `cd /Users/konst/projects/adcp && git show v3.1.1:static/schemas/source/<path>`.

### `core/reporting-capabilities.json` — the declaration

```json
"vendor_metrics": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "vendor":    { "$ref": "/schemas/core/brand-ref.json" },
      "metric_id": { "$ref": "/schemas/core/vendor-metric-id.json" }
    },
    "required": ["vendor", "metric_id"],
    "additionalProperties": false
  }
}
```

Description, verbatim and normative:

> "Semantic uniqueness key is `(vendor.domain, vendor.brand_id, metric_id)`; sellers MUST de-duplicate
> before emission and MUST NOT declare the same vendor metric twice. Buyers MAY treat duplicate
> `(vendor, metric_id)` rows as a seller-side conformance bug. (JSON Schema `uniqueItems` is not used
> here because BrandRef carries optional fields whose absence/presence would defeat deep-equal —
> uniqueness is on the semantic key, enforced at build/validation time on the seller side.)"

`vendor_metrics` is **not** in `required` (that list is
`["available_reporting_frequencies","expected_delay_minutes","timezone","supports_webhooks","available_metrics","date_range_support"]`),
and the object is `"additionalProperties": true`.

### `core/vendor-metric-id.json` — the identifier

```json
{ "type": "string", "x-entity": "vendor_metric",
  "minLength": 1, "maxLength": 64, "pattern": "^[a-z][a-z0-9_]*$",
  "examples": ["attention_units","gco2e_per_impression","demographic_reach",
               "co_view_index","incremental_lift_percent"] }
```

> "Identifier is namespaced by the vendor — the same `metric_id` may mean different things in different
> vendors' vocabularies."

### `core/brand-ref.json` — the vendor pointer

```json
"required": ["domain"], "additionalProperties": false
"domain": { "type": "string",
            "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$" }
"brand_id": { "$ref": "/schemas/core/brand-id.json",
              "description": "...Optional for single-brand domains." }
```

This is why the uniqueness key has a hole in the middle: `brand_id` is optional, so for single-brand
vendors the operative key is `(domain, ⌀, metric_id)`.

### `core/product-filters.json` — the discovery filter

```json
"required_vendor_metrics": {
  "type": "array", "minItems": 1,
  "items": {
    "type": "object",
    "properties": { "vendor": {...brand-ref...}, "metric_id": {...vendor-metric-id...} },
    "anyOf": [ { "required": ["vendor"] }, { "required": ["metric_id"] } ],
    "additionalProperties": false
  }
}
```

> "A product matches if its declared `vendor_metrics` covers ALL listed entries (AND across entries;
> pins within an entry are conjunctive). ... **Sellers MUST silently exclude non-matching products
> (filter-not-fail; do not return an error)** — same convention as the other `required_*` filters."

Note the `anyOf`: **at least one of `vendor` / `metric_id` must be pinned per entry.** A pinless `{}`
entry is schema-invalid. (Our SDK model accepts it — see §4.)

### `core/delivery-metrics.json` — the emission

```json
"vendor_metric_values": {
  "type": "array",
  "items": { "$ref": "/schemas/core/vendor-metric-value.json" }
}
```

> "One row per `(vendor.domain, vendor.brand_id, metric_id)` per reporting period — sellers MUST
> de-duplicate before emission and MUST NOT emit the same vendor metric twice; buyers MAY treat
> duplicate rows as a seller-side conformance bug."

`delivery-metrics.json` has **no** `required` list and `"additionalProperties": true` — so
`vendor_metric_values` is optional. Absence is conformant; the storyboard grades presence only because
the controller injected data first.

### `core/vendor-metric-value.json` — the row shape

```json
"required": ["vendor", "metric_id", "value"], "additionalProperties": false
```

with `unit` free-form, `measurable_impressions` `minimum: 0`, and `breakdown` as the only extension slot
(`"x-adcp-open-payload": true`). On `measurable_impressions`:

> "When absent, coverage is unspecified — buyers MUST NOT compute a coverage rate or assume full coverage."

### `media-buy/get-media-buy-delivery-response.json` — where the row lives

```json
"by_package": {
  "type": "array",
  "items": { "allOf": [ { "$ref": "/schemas/core/delivery-metrics.json" },
                        { "type": "object", "properties": { "package_id": {...}, "pacing_index": {...}, ... } } ] }
}
```

So `vendor_metric_values` reaches `by_package[]` through the `delivery-metrics.json` half of the `allOf`.
That is the exact inheritance our `PackageDelivery` does not have (§4).

---

## 4. Conflicts

**Schema vs storyboard.** No contradiction; the schema is strictly stronger and **overrides on two points**:

1. **De-duplication.** The storyboard states it in `narrative:` only — ungraded. `reporting-capabilities.json`
   and `delivery-metrics.json` both make it a **MUST** in normative description text. **The 3.1.1 schema wins:
   de-dup is binding on us even though the storyboard does not grade it.** It still cannot be asserted green
   (nothing to de-duplicate — we emit nothing), so it moves to TICKET.
2. **Filter pin cardinality.** The storyboard only ever sends a vendor-pinned entry.
   `product-filters.json` `anyOf` additionally admits metric_id-only and both-pinned forms, and forbids
   pinless. **The 3.1.1 schema wins** — the Examples table below exercises all three legal pin shapes.

**Schema vs SDK.** `ProductFilters(required_vendor_metrics=[{}])` **is accepted** by `adcp==6.6.0` —
the `anyOf` is not enforced by the generated model. Executed and confirmed. Per the authority order the
schema wins and this is a conformance gap on the request boundary → TICKET T5.

**What the scenario gets wrong.**

- **No `@source` footer at all**, and its true storyboard is cited by the scenario above it (off-by-one).
- **Then #2** ("should carry one row per (vendor.domain, vendor.brand_id, metric_id)") asserts a
  structural property of a field our model cannot hold. `PackageDelivery` at
  `src/core/schemas/delivery.py:159` is a hand-rolled `SalesAgentBaseModel` whose fields are
  `package_id, impressions, spend, clicks, completed_views, pacing_index, pricing_model, rate, currency,
  by_placement*, by_geo*, by_device_type*` — no `vendor_metric_values`, no `missing_metrics`, no
  `committed_metrics`. Its own docstring at `:162` concedes it: *"Note: Does not yet extend library
  ByPackageItem."* Permanently red.
- **Then #3** ("the row for vendor … should include metric_id …") — same field, same wall.
- **Then #4** ("should NOT emit duplicate rows …") — an assertion about rows we never emit. This is the
  classic **vacuous negative**: it would pass today for the wrong reason (empty set satisfies "no
  duplicates"), which is worse than red. `test_architecture_bdd_no_trivial_assertions.py` should be
  catching this shape.
- **Then #1** ("schema-valid against get-media-buy-delivery-response.json") is **vacuous by
  construction** — the brief already records that `then_response_schema_valid` runs no validator despite
  `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing.
- **Given #2** ("the buyer declared filters.required_vendor_metrics matching that pointer") implies the
  filter did something. It does not. `_get_products_impl` filters on `delivery_type`, `is_fixed_price`,
  `format_ids`, `standard_formats_only`, `countries`, `channels`, `device_types` and nothing else
  (`src/core/tools/products.py:461-604`). Proven by execution: two products, one declaring
  `attentionvendor.example` and one declaring nothing, filtered by
  `required_vendor_metrics=[{"vendor":{"domain":"attentionvendor.example"}}]` →
  **both returned**. Same for `required_metrics=["completed_views"]` → both returned.
- **Given #3/#4** ("created a media buy", "controller-driven simulated delivery") describe a
  `comply_test_controller` flow we do not implement at all.

**What is missing.** The one thing that *does* work — verbatim pointer fidelity through the whole
DB→JSONType→conversion→Pydantic-revalidation→wire path — the scenario never asserts. That is the entire
green surface and it was left on the floor.

**What I verified green** (real Postgres, `ProductEnv`, mcp + a2a + rest, wire body not typed payload):

| declared `vendor_metrics` | filter pin form | wire echo |
|---|---|---|
| single-brand vendor | vendor-only | byte-identical, all 3 transports |
| `brand_id`-bearing (house-of-brands) | vendor + metric_id | byte-identical, `brand_id` preserved |
| two entries, two vendors | metric_id-only | byte-identical, both rows, order preserved |

No `brand_id: null` injection, no key drop, no reordering that mattered. The mechanism is
`src/core/product_conversion.py:482-483` — a straight passthrough of the `JSONType` column into
`Product.reporting_capabilities`, which `src/core/schemas/product.py:82` types as `Any` and
`:169` pins into `core_fields` so it is never stripped as null.

---

## 5. Proposed Gherkin

Replaces `tests/bdd/features/BR-UC-004-deliver-media-buy-metrics.feature:1356-1379` (tag line through
the trailing comment block). The `@T-UC-004-storyboard-vendor-metric-end-to-end` identifier tag is
unchanged — `docs/test-obligations/bdd-traceability.yaml` references it.

```gherkin
  @T-UC-004-storyboard-vendor-metric-end-to-end @storyboard-v3.1 @v3-1 @vendor-metric @accountability @vendor-metric-discovery
  Scenario Outline: Vendor metric accountability -- the product's (vendor, metric_id) pointer survives discovery unaltered
    Given a tenant is configured for product discovery
    And a product declaring reporting_capabilities.vendor_metrics <declared>
    When the buyer requests products with filters.required_vendor_metrics <pins>
    Then the response contains at least one product
    And the wire product reporting_capabilities.vendor_metrics should equal <declared>
    And the wire product reporting_capabilities.vendor_metrics should have <rows> entries
    And every wire vendor_metrics entry should carry exactly the keys "vendor,metric_id"
    And the wire vendor_metrics semantic keys should be "<semantic_keys>"
    # Storyboard phase 1 of 3 (discover_with_required_vendor_metrics). Phases 2-3
    # (create_media_buy carry-forward; by_package[].vendor_metric_values emission)
    # are NOT wired here: production has no vendor_metric_values field on
    # by_package and no comply_test_controller. See #TBD-VM-EMIT / #TBD-VM-FILTER.
    #
    # The three graded field_present checks on the storyboard's get_products step
    # (vendor_metrics, [0].vendor.domain, [0].metric_id) are upgraded here to value
    # equality on the WIRE body -- existence checks would pass on a response that
    # dropped brand_id or injected nulls.
    #
    # semantic_keys is the buyer-side uniqueness key the seller must de-duplicate
    # on, computed as domain/brand_id/metric_id with an empty middle segment when
    # the vendor is single-brand (brand_ref.brand_id is optional). It is derived
    # from the wire rows, not echoed from <declared>.
    #
    # Pin forms cover all three shapes product-filters.json anyOf admits:
    # vendor-only, vendor+metric_id, metric_id-only. A pinless {} entry is
    # schema-invalid but our SDK model accepts it -- see #TBD-VM-PINLESS.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/vendor_metric_accountability.yaml phase=discover_with_required_vendor_metrics step=get_products_required_vendor_metrics

    Examples:
      | case              | declared                                                                                                                                                              | pins                                                                            | rows | semantic_keys                                                                    |
      | single-brand      | [{"vendor": {"domain": "attentionvendor.example"}, "metric_id": "attention_units"}]                                                                                   | [{"vendor": {"domain": "attentionvendor.example"}}]                             | 1    | attentionvendor.example//attention_units                                         |
      | house-of-brands   | [{"vendor": {"domain": "panelmeasurement.example", "brand_id": "panel_us"}, "metric_id": "demographic_reach"}]                                                        | [{"vendor": {"domain": "panelmeasurement.example"}, "metric_id": "demographic_reach"}] | 1    | panelmeasurement.example/panel_us/demographic_reach                              |
      | two distinct keys | [{"vendor": {"domain": "attentionvendor.example"}, "metric_id": "attention_units"}, {"vendor": {"domain": "emissionsvendor.example"}, "metric_id": "gco2e_per_impression"}] | [{"metric_id": "gco2e_per_impression"}]                                         | 2    | attentionvendor.example//attention_units,emissionsvendor.example//gco2e_per_impression |
```

Every row was executed. `single-brand` and `house-of-brands` ran verbatim; `two distinct keys` ran with
the same declared pair (the metric_id-only pin form was validated separately against `ProductFilters`).
Transport-independent: identical Gherkin, no branching, dispatch via `dispatch_request`.

**Why no `Then` about exclusion.** The storyboard's own description for that check is *"At least one
product matched the required_vendor_metrics filter"* — which is what `the response contains at least one
product` asserts (and that step is stricter than the storyboard: it asserts `len(products) == 1` and
`product_id`/`name` equality against the seeded row). Asserting that a **non-**declaring product is
excluded is proven red and is ticket T1, not scenario content.

---

## 6. Step inventory

### Existing — reuse as-is

| Step | Defined at |
|---|---|
| `Given a tenant is configured for product discovery` | `tests/bdd/steps/domain/uc_get_products_inventory.py:63` |
| `Then the response contains at least one product` | `tests/bdd/steps/domain/uc_get_products_inventory.py:201` — already asserts exactly 1 product and compares `product_id` + `name` to `ctx["product"]`; sets `ctx["first_product"]` |

### New — 4 steps, all in `tests/bdd/steps/domain/uc004_delivery.py`

| Step | Notes |
|---|---|
| `Given a product declaring reporting_capabilities.vendor_metrics <declared>` | `json.loads` the cell; `ProductFactory(tenant=ctx["tenant"], reporting_capabilities={...base..., "vendor_metrics": parsed})` + `PricingOptionFactory(product=...)`; store the product on `ctx["product"]` so the reused `Then` can compare, and the parsed list on `ctx["declared_vendor_metrics"]`. Base block must satisfy `reporting-capabilities.json` `required`. Factory-based per CLAUDE.md #8 — no `session.add()`. |
| `When the buyer requests products with filters.required_vendor_metrics <pins>` | `dispatch_request(ctx, brief=..., filters={"required_vendor_metrics": json.loads(pins)})`. Mirrors `_call_get_products`; consider lifting that helper rather than duplicating (DRY). |
| `Then the wire product reporting_capabilities.vendor_metrics should equal <declared>` / `... should have <rows> entries` / `... exactly the keys "vendor,metric_id"` | Read `ctx["wire_response"]["products"][0]["reporting_capabilities"]["vendor_metrics"]`, **not** the typed payload — `GetProductsResponse.products` is declared `list[LibraryProduct]`, so the typed object re-validates into the SDK's `ReportingCapabilities` model and `.get()` on it returns `None`. Use `wire_field()` per `tests/CLAUDE.md` so a missing wire body fails loudly instead of silently passing. |
| `Then the wire vendor_metrics semantic keys should be "<semantic_keys>"` | Compute `f'{e["vendor"]["domain"]}/{e["vendor"].get("brand_id","")}/{e["metric_id"]}'` per row, join with `,`, compare to the literal. Derived from the wire, so not an echo of `<declared>`. |

Three phrasings share one body — extract a single `_wire_vendor_metrics(ctx)` accessor; three
near-identical step functions with copy-pasted traversal would trip
`test_architecture_bdd_no_duplicate_steps.py`.

### Harness wiring — required, one line

`tests/bdd/conftest.py::_detect_delivery_harness` currently returns `"poll"` for this scenario, giving
`DeliveryPollEnv`, which has no `get_products` dispatch. Add ahead of the final `return "poll"`:

```python
    if "vendor-metric-discovery" in marker_names:
        return "product"
```

and a `harness_type == "product"` branch in the UC-004 arm of `_harness_env` mirroring the existing
`UC-GET-PRODUCTS` branch (`ProductEnv(e2e_config=e2e_config)`; `ctx["env"] = env`; the `Given` seeds
tenant/principal/product). This is BDD wiring, not production code — no `src/` change, so GREEN-ONLY holds.

Cleaner alternative: extend `_detect_uc` so `@vendor-metric-discovery` returns `"UC-GET-PRODUCTS"`
directly and reuse the existing branch verbatim. Either is fine; the second adds no new branch.

---

## 7. TICKET MATERIAL

**T1 — `filters.required_vendor_metrics` is accepted and then silently ignored.**
`_get_products_impl` (`src/core/tools/products.py:461-604`) filters on `delivery_type`,
`is_fixed_price`, `format_ids`, `standard_formats_only`, `countries`, `channels`, `device_types`.
`required_vendor_metrics` is parsed into typed SDK models on the request and never read. Executed
proof: tenant with `vm_capable` (declares `attentionvendor.example`) + `vm_incapable` (declares none),
request `filters.required_vendor_metrics=[{"vendor":{"domain":"attentionvendor.example"}}]` →
returns `['vm_capable','vm_incapable']`. Violates 3.1.1 `core/product-filters.json`
`required_vendor_metrics`: *"Sellers MUST silently exclude non-matching products (filter-not-fail; do
not return an error)"*, and defeats storyboard
`protocols/media-buy/scenarios/vendor_metric_accountability.yaml:152` (*"At least one product matched
the required_vendor_metrics filter"*). Matching rule to implement, from the same description:
*"A product matches if its declared `vendor_metrics` covers ALL listed entries (AND across entries;
pins within an entry are conjunctive)."*

**T2 — `filters.required_metrics` is likewise accepted and ignored.**
Same code path, same absence. Executed proof: `filters.required_metrics=["completed_views"]` against
two products, neither declaring `completed_views` → both returned. Violates
`core/product-filters.json` `required_metrics`: *"Sellers MUST silently exclude products that cannot
meet this list."* This is the sibling storyboard `measurement_accountability.yaml`'s phase 1 — flagging
it here because it is the *same missing filter loop* as T1 and both should be fixed in one change.

**T3 — `by_package[]` cannot carry `vendor_metric_values` (nor `missing_metrics`, nor
`committed_metrics`).**
`PackageDelivery` (`src/core/schemas/delivery.py:159`) is a hand-rolled `SalesAgentBaseModel` with a
closed field list; its docstring at `:162` says *"Does not yet extend library ByPackageItem."*
3.1.1 `media-buy/get-media-buy-delivery-response.json` defines `by_package.items` as
`allOf [ {$ref: core/delivery-metrics.json}, {package_id, pacing_index, pricing_model, rate, currency,
delivery_status, paused, is_final, ...} ]`, and `core/delivery-metrics.json` is where
`vendor_metric_values` lives. This is a **CLAUDE.md Pattern #1 violation** (extend library schemas, do
not hand-roll) and it is the single blocker for storyboard phase 3
(`vendor_metric_accountability.yaml:279-293`, five graded `field_present` checks). `DeliveryTotals`
(`src/core/schemas/delivery.py`, same module) has the same defect and blocks `metric_aggregates`.
Fix = make `PackageDelivery` extend the library `delivery-metrics` type; that unblocks T4 and the 12
other dormant UC-004 vendor/missing-metrics scenarios in one move.

**T4 — vendor-metric row de-duplication is unimplemented (and unimplementable until T3).**
3.1.1 `core/delivery-metrics.json` `vendor_metric_values`: *"One row per `(vendor.domain,
vendor.brand_id, metric_id)` per reporting period — sellers MUST de-duplicate before emission and MUST
NOT emit the same vendor metric twice"*; `core/reporting-capabilities.json` `vendor_metrics` repeats it
for the declaration side and explains why `uniqueItems` cannot express it (BrandRef optional fields
defeat deep-equal). Note for the implementer: the storyboard does **not** grade this — it is
`narrative:` prose at `vendor_metric_accountability.yaml:218-222` — so the **schema is the authority**,
per the brief's authority order. Depends on T3.

**T5 — a pinless `required_vendor_metrics` entry is accepted where the schema forbids it.**
`ProductFilters(required_vendor_metrics=[{}])` validates clean under `adcp==6.6.0`; executed.
3.1.1 `core/product-filters.json` `required_vendor_metrics.items` carries
`"anyOf": [{"required": ["vendor"]}, {"required": ["metric_id"]}]` — at least one pin is mandatory.
The generated SDK model does not enforce the `anyOf`, so the request boundary lets a meaningless filter
through instead of emitting `VALIDATION_ERROR`. Per authority order the schema wins; needs a validator
at our boundary (and an upstream SDK issue). Do not fix by asserting the SDK — it is cross-check only.

**T6 — `comply_test_controller` does not exist.**
`grep -rn comply_test_controller src/` → 0. It is in `required_tools` at
`vendor_metric_accountability.yaml:11` and drives phases 2-3 (`:224-253`). Without it, two thirds of
this storyboard cannot be run against us by the conformance runner at all — regardless of T3. Scope
decision needed: implement a sandbox-gated controller, or accept partial conformance on the
`reporting` track and say so.

**T7 — the two `@storyboard-*` scenarios above this one have swapped/stale `@source` footers.**
`BR-UC-004-deliver-media-buy-metrics.feature:1354` cites
`.../vendor_metric_accountability.yaml` while sitting under the `measurement_accountability` scenario
(`:1334`), and `:1331` cites `.../measurement_accountability.yaml` under the `delivery_reporting`
scenario. All still pinned `ref=v3.1-04f59d2d5 commit=04f59d2d5`, an ancestor of beta.3 and older than
our own 3.1.1 pin. Owned by the sibling re-pin tasks; recorded so the off-by-one chain is documented
end to end.

---

## 8. Risks

- **The proposed scenario needs a conftest harness route to run at all.** Without the
  `_detect_delivery_harness` / `_detect_uc` change in §6 it stays xfailed at
  `pytest.xfail("UC-004 harness not yet wired...")` — green in the sense of "not red", but still dormant.
  If the baseline PR wants zero conftest churn, this scenario should move to `BR-UC-001` instead, which
  already routes to `ProductEnv`; that is a bigger diff and I did not assume it.
- **I could not execute the proposal end to end**, because the four new step definitions do not exist and
  I was told to propose only. What I *did* execute is every production behaviour each proposed `Then`
  depends on, through `ProductEnv.call_via` on mcp/a2a/rest against real Postgres, asserting on
  `wire_response`. The residual risk is step-implementation error, not production behaviour.
- **`ctx["wire_response"]` availability.** It was populated on all three transports in my probes. If it
  is ever `None` for an env that does not stash the wire body, the steps must fail loudly (`wire_field()`),
  not silently fall back to the typed payload — a fallback would make the whole scenario tautological.
- **`e2e_rest` not exercised.** I ran mcp/a2a/rest. The fourth transport dispatches over real HTTP against
  a shared live-server DB; the `get_or_create` idempotency in `given_tenant` exists precisely for that, and
  my new `Given` inserts a *product* per scenario, which could collide across scenarios on the shared DB.
  Use a `product_id` unique per Examples row (e.g. `vm_<case>`) if this is wired for `e2e_rest`.
- **`then_response_schema_valid` is a no-op**, so I deliberately did not include a "schema-valid against
  get-products-response.json" Then — it would look like it grades the storyboard's `response_schema`
  check while grading nothing. Wiring `validate_against_pinned_schema` is out of scope here, but note the
  vendored `tests/fixtures/adcp_schemas_pinned/` **does** already contain the 3.1.1-era
  `core/vendor-metric-value.json`, `core/reporting-capabilities.json` (with `vendor_metrics`) and
  `core/product-filters.json` (with `required_vendor_metrics`) — so the pinned fixtures are less stale
  than the brief's blanket "vendored at 04f59d2d5" suggests, at least for these files. Worth a separate
  check before anyone acts on that assumption.
- **Drift beyond our pin, noted only.** 3.1.8 / HEAD reorganise the compliance tree (the `domains/` tier
  is byte-identical to `protocols/` at 3.1.1 but may diverge later). Nothing here depends on it; we stay
  at 3.1.1.

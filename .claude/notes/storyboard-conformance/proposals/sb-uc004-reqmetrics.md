# Re-pin: `@T-UC-004-storyboard-required-metrics-end-to-end-accountability`

Scenario: "Measurement accountability -- required_metrics declared at discovery surfaces missing_metrics in delivery"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-004-deliver-media-buy-metrics.feature:1334`

---

## 1. VERDICT

**GRADED — but the scenario asserts the one branch that is NOT graded, and it currently grades nothing at all (dormant).**

Three separate facts, all verified:

1. **The behaviour is graded at 3.1.1**, in `media_buy_seller/measurement_accountability`, which lives in the
   `protocols/media-buy/` tier — the protocol we declare (`supported_protocols=[media_buy]`,
   `src/core/tools/capabilities.py:99`). No specialism gate. So `@storyboard-v3.1` is **justified** and stays.
2. **Only the CLEAN branch is graded.** The storyboard's single `missing_metrics` validation is
   `check: field_value_or_absent … value: []`. The **breach** branch — "a declared metric was not emitted, so it
   MUST appear in `missing_metrics`" — appears *only* in the storyboard `narrative:`/`expected:` prose and in the
   JSON schema's `examples:`. Neither is graded. The scenario's headline Then asserts exactly that ungraded breach.
3. **Today the scenario grades nothing.** None of its six steps has a definition anywhere in `tests/bdd/steps/`
   (verified: `grep -rn 'missing_metrics\|required_metrics' tests/bdd/steps/` → zero hits). `scenarios()` binds it
   (`tests/bdd/test_uc004_deliver_media_buy_metrics.py:11`), so it is collected and then converted to xfail by the
   `StepDefinitionNotFoundError` hook at `tests/bdd/conftest.py:99-101`. It is a dormant scenario.

The same is true of its two siblings `@T-UC-004-missing-metrics-flagged` (line 1131) and
`@T-UC-004-missing-metrics-clean` (line 1144) — also stepless, also dormant. The scenario's own comment claim
*"Existing UC-004 missing_metrics scenarios target single missing entries"* implies those are live. They are not.

---

## 2. Real binding at 3.1.1

### What the footer wrongly points at

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/vendor_metric_accountability.yaml
```

Both defects confirmed:

* **Stale ref.** `04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin.
* **Off-by-one path.** It cites `vendor_metric_accountability.yaml`, which is the storyboard of the **next**
  scenario in the file (`@T-UC-004-storyboard-vendor-metric-end-to-end`, line 1355 — which itself carries no
  footer). The shift is visible in both directions: the **previous** scenario (line 1317, prose line
  `# delivery_reporting: schema compliance after controller-driven delivery`) cites
  `measurement_accountability.yaml` — i.e. *my* storyboard. Each scenario cites its successor's file.

The scenario's own prose names the truth: `# measurement_accountability: required_metrics at discovery -> missing_metrics in delivery`.

### The real file

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/measurement_accountability.yaml`
(id `media_buy_seller/measurement_accountability`, version 1.0.0)

Provenance checks I ran, because the adcp worktree is checked out at HEAD (`ac1f4bb46`, a 3.1.8 forward-merge), not at the tag:

* `git show v3.1.1:dist/compliance/3.1.1/protocols/media-buy/scenarios/measurement_accountability.yaml` is
  **byte-identical** to the on-disk copy. Safe to read from disk.
* `static/compliance/source/…` and `dist/compliance/3.1.1/…` are **identical at v3.1.1**, so the `@source`
  `static/compliance/source/…` path convention resolves. (`v3.1.1` = `467fd93d7`.)
* `domains/media-buy/scenarios/measurement_accountability.yaml` is a byte-identical mirror of the `protocols/`
  copy. Either path is correct; I keep `protocols/` to match the rest of the file's footers.

### Tier ownership

`protocols/media-buy/` — the protocol we declare. Not `universal/`, not `specialisms/`.

Gate check, since this drives whether the tag survives:

* `agent.capabilities: [sells_media]` — a storyboard-level agent descriptor, not a specialism gate.
* No `requires:` key on this storyboard (contrast `governance_denied.yaml:7` → `requires: [multi_agent]`, and
  `universal/comply-controller-mode-gate.yaml:10` → `requires: [controller]`). So it is **not capability-gated**.
* It is **not** in the media-buy baseline `requires_scenarios` list (`protocols/media-buy/index.yaml:10-24`) — it is
  an additional scenario under a declared protocol, not part of the baseline bundle.
* `required_tools` includes `comply_test_controller`, which we do not implement. That is a **runner precondition**
  shared with baseline scenarios like `delivery_reporting.yaml`, not a conformance gate — but it does mean the
  storyboard cannot literally execute against us. Our BDD substitutes adapter fault-injection for the controller.

### The graded validations, verbatim

Phase `simulate_and_validate_accountability` (line 182), step `get_delivery_clean` (line 218), validations at 238-244:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-media-buy-delivery-response.json schema (validates missing_metrics shape when present)"
          - check: field_value_or_absent
            path: "media_buy_deliveries[0].by_package[0].missing_metrics"
            value: []
            description: "missing_metrics is empty (or absent) — clean delivery against the declared contract, no accountability breach"
```

The `expected:` prose for that same step (lines 226-230) — **narrative, not graded**:

```yaml
        expected: |
          Return delivery metrics with completed_views populated. The
          by_package entry includes `missing_metrics: []` (or omits the
          field entirely) because every metric the product advertised is
          present in this report.
```

Note what the storyboard actually injects one step earlier (`simulate_delivery`, lines 201-216):
`impressions: 100000`, **`completed_views: 72000`**, `reported_spend: 2500.00 USD`. The storyboard **emits**
`completed_views` and then asserts clean. Our scenario says delivery "did not emit `completed_views`" and asserts a
breach entry. **The scenario is inverted relative to its own storyboard.**

The discovery phase's graded block (step `get_products_required_metrics`, lines 105-145) — this is where
`required_metrics` is graded, and it is graded only as *presence*, never as exclusion:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-products-response.json schema"
          - check: field_present
            path: "products[0].product_id"
            description: "At least one product matched the required metrics"
          - check: field_present
            path: "products[0].reporting_capabilities.available_metrics"
            description: "Matched product declares its available_metrics — schema validation confirms the superset relationship via the closed enum"
          - check: field_present
            path: "products[0].pricing_options[0].fixed_price"
            description: "The captured pricing option is fixed-price; fixed-price storyboards do not send bid_price"
```

The MUST-exclude rule the scenario's line 1336 asserts ("the seller filtered products to those whose
`available_metrics` is a superset") is graded **nowhere**. It lives in the storyboard `narrative:` (lines 19-23)
and in the schema description. It is a real spec MUST — just not a graded one.

---

## 3. Schema constraints at 3.1.1

All quotes via `git show v3.1.1:<path>`.

**`static/schemas/source/core/product-filters.json:474`** — `required_metrics`:

> Filter to products whose `reporting_capabilities.available_metrics` is a superset of these metrics — i.e.,
> products that commit to reporting all listed metrics in delivery responses. […] Sellers MUST silently exclude
> products that cannot meet this list (filter-not-fail; do not return an error). The product's declared
> `available_metrics` becomes the binding reporting contract carried into the resulting media buy — the same metric
> vocabulary is used to compute `missing_metrics` on `get_media_buy_delivery`.

Constraints: `items: {$ref: /schemas/enums/available-metric.json}`, `minItems: 1`, `uniqueItems: true`.

**`static/schemas/source/core/reporting-capabilities.json`** —
`required: ["available_reporting_frequencies", "expected_delay_minutes", "timezone", "supports_webhooks", "available_metrics", "date_range_support"]`.
`available_metrics` description:

> Metrics available in reporting. **Impressions and spend are always implicitly included.** When a creative format
> declares `reported_metrics`, buyers receive the intersection of these product-level metrics and the format's
> `reported_metrics`.

That implicit-inclusion clause matters for the rewrite: a product declaring `available_metrics: ["impressions"]`
still satisfies `required_metrics: ["spend"]`.

**`static/schemas/source/media-buy/get-media-buy-delivery-response.json:357`** — `missing_metrics`
(at `properties.media_buy_deliveries.items.properties.by_package.items.allOf[1].properties.missing_metrics`):

> Metrics that the binding reporting contract declared but that are NOT populated in this report. Reconciliation
> source: when `package.committed_metrics` is present, `missing_metrics` is computed against entries where
> `committed_at < reporting_period.end` […] When `package.committed_metrics` is absent, fall back to the product's
> current `reporting_capabilities.available_metrics` (no timestamp filter). **Empty array (or absent) indicates
> clean delivery against the contract. Non-empty signals an accountability breach** — the seller committed to the
> metric but did not produce the value here. Sellers MUST exclude metrics that are not yet measurable for the
> current `measurement_window` […] Each entry uses an explicit `scope` discriminator: `standard` for entries from
> the closed `available-metric.json` enum, `vendor` for vendor-defined metrics anchored on a BrandRef.

`items: {$ref: /schemas/core/missing-metric.json}`. Its `examples:` include `[]` and
`[{"scope": "standard", "metric_id": "completed_views"}]` — **examples, not grading**.

**`static/schemas/source/core/missing-metric.json`** — `oneOf` discriminated on `scope`:

```json
{ "properties": { "scope": {"const": "standard"},
                  "metric_id": {"$ref": "/schemas/enums/available-metric.json"},
                  "qualifier": { … "additionalProperties": false } },
  "required": ["scope", "metric_id"], "additionalProperties": false }
```
```json
{ "properties": { "scope": {"const": "vendor"},
                  "vendor": {"$ref": "/schemas/core/brand-ref.json"},
                  "metric_id": {"$ref": "/schemas/core/vendor-metric-id.json"} },
  "required": ["scope", "vendor", "metric_id"], "additionalProperties": false }
```

So the scenario's `scope "standard"` + `metric_id "completed_views"` shape is schema-correct — `completed_views`
is in the `available-metric.json` enum (36 values: `impressions, spend, clicks, ctr, views, completed_views,
completion_rate, conversions, …`).

**`by_package` item requirements** — this is the one that bites us:

```
allOf[0] → $ref /schemas/core/delivery-metrics.json
allOf[1] → required: ["package_id", "spend", "pricing_model", "rate", "currency"]
```

`missing_metrics` is **not** required — absence is schema-legal, which is precisely why the graded check is
`field_value_or_absent`.

**Envelope** — `get-media-buy-delivery-response.json` top level:

```json
"allOf": [ {"$ref": "/schemas/core/version-envelope.json"},
           {"$ref": "/schemas/core/protocol-envelope.json"} ],
"required": ["reporting_period", "currency", "media_buy_deliveries"]
```

`core/protocol-envelope.json`: *"The `status` field is REQUIRED on every task response envelope […] Agents
shipping responses without a top-level `status` are non-conformant regardless of whether the task body schema would
otherwise validate."* — the known repo-wide gap.

No pagination on this response.

---

## 4. Conflicts

**Schema vs storyboard.** No contradiction here, but the schema is *broader* than the storyboard: the schema
mandates the breach semantics ("Non-empty signals an accountability breach") and the discovery MUST-exclude rule;
the storyboard grades neither. Where they differ in force, **the 3.1.1 schema wins** — so the breach behaviour is a
genuine spec MUST that we owe, it simply cannot be claimed as `@storyboard-v3.1`-graded, and it cannot land green
today. It goes to TICKET MATERIAL, not into the Gherkin.

**What the scenario gets wrong:**

1. **Inverted against its own storyboard.** Storyboard emits `completed_views: 72000` and asserts clean. Line 1338
   says delivery "did not emit `completed_views`" and line 1341 asserts a breach row. That is the ungraded branch.
2. **Wrong `@source` on both axes** (stale ref + next-scenario path), per §2.
3. **Line 1336 is not a Given, it is the assertion.** *"the seller filtered products to those whose
   available_metrics is a superset"* states the seller's MUST as a precondition, so nothing ever checks it. This is
   the "Given asserts the behaviour under test" anti-pattern.
4. **Line 1342 is unfalsifiable as written** — *"missing_metrics should be empty or absent when all
   product-declared metrics were emitted"* has a conditional in the Then and no antecedent anywhere in the
   scenario (the scenario's Given established the opposite condition). It can never fail.
5. **Line 1340 (`schema-valid against get-media-buy-delivery-response.json`) would be red** if it were wired.
   `then_response_schema_valid` runs no validator today (known), but with a real validator our response fails
   twice: no top-level `status`, and `by_package[].pricing_model/rate/currency` are emitted as `None` whenever the
   package has no `package_config.pricing_info` (`src/core/tools/media_buy_delivery.py:489-497`), while 3.1.1
   requires all three.
6. **Zero of it executes.** Dormant, per §1.

**What production actually does** (all verified by reading `src/`):

* `required_metrics` is **accepted and silently ignored**. `ProductFilters` (adcp 6.6) carries the field and
  `model_config.extra == "allow"`, so no error — but `src/core/tools/products.py:460-606` applies only
  `delivery_type`, `is_fixed_price`, `format_ids`, `standard_formats_only`, `countries`, `channels`,
  `device_types`. No metric filtering exists. Filter-not-fail is satisfied vacuously; superset exclusion is not.
* `missing_metrics` **does not exist in the codebase** — zero hits in `src/`. `PackageDelivery`
  (`src/core/schemas/delivery.py:162-215`) has no such field, so it can never be emitted and the
  `field_value_or_absent … value: []` check passes by absence.
* `reporting_capabilities.available_metrics` **is** emitted: `src/core/product_conversion.py:482-493` falls back to
  a hard-coded `{"available_metrics": ["impressions"], …}` when the DB column is null, and
  `reporting_capabilities` is in `Product.model_dump`'s always-included `core_fields`
  (`src/core/schemas/product.py:161-169`).

**Harness constraint that shapes the rewrite.** UC-004 scenarios are routed to `DeliveryPollEnv`
(`tests/bdd/conftest.py:3460-3478` via `_detect_delivery_harness`, default `"poll"`). `get_products` lives in a
different env (`tests/harness/product.py`, routed only for `UC-GET-PRODUCTS`, conftest:3509-3514). **One scenario
gets one env**, so a discovery→create→delivery chain is not expressible in UC-004 without harness work. The
storyboard's three phases cannot be one Gherkin scenario here. I keep the delivery leg (the only graded
`missing_metrics` check) and file the discovery leg.

---

## 5. Proposed Gherkin — GREEN ONLY

Replaces lines 1333-1352 (tag line through footer).

```gherkin
  @T-UC-004-storyboard-required-metrics-end-to-end-accountability @storyboard-v3.1 @v3-1 @polling @missing-metrics @accountability
  Scenario Outline: Measurement accountability -- a package reporting every metric it committed to carries no missing_metrics
    Given a media buy "mb-001" owned by "buyer-001" with status "active"
    And the ad server adapter reports impressions <impressions> and spend <spend> for "mb-001"
    When the Buyer Agent requests delivery metrics for media_buy_ids ["mb-001"]
    Then the response packages should report "impressions" as <impressions> for "pkg_001"
    And the response packages should report "spend" as <spend> for "pkg_001"
    And the response packages should have an empty or absent missing_metrics array for "pkg_001"
    # measurement_accountability phase simulate_and_validate_accountability, step get_delivery_clean:
    # the seller injects delivery for the metrics it advertised, then the buyer polls. The single
    # graded accountability check is field_value_or_absent on
    # media_buy_deliveries[0].by_package[0].missing_metrics with value [] -- empty OR absent means
    # clean delivery against the declared contract. available_metrics declares impressions and spend
    # implicitly for every product (core/reporting-capabilities.json), so a report that carries both
    # values it was given is clean by construction and missing_metrics must stay empty/absent.
    # The breach branch (a declared metric NOT emitted MUST appear in missing_metrics) is spec-MUST
    # per core/missing-metric.json but is graded nowhere in the 3.1.1 storyboard, and production has
    # no missing_metrics field at all -- tracked separately, deliberately not asserted here.
    # @source repo=adcp ref=v3.1.1 commit=467fd93d7 path=static/compliance/source/protocols/media-buy/scenarios/measurement_accountability.yaml phase=simulate_and_validate_accountability step=get_delivery_clean

    Examples: storyboard-scale delivery
      | impressions | spend   |
      | 100000      | 2500.00 |

    Examples: harness-default delivery
      | impressions | spend   |
      | 5000        | 250.00  |

    Examples: zero-delivery reporting period
      | impressions | spend   |
      | 0           | 0.00    |
```

Why each line is green:

* **Given media buy** — existing step (`uc004_delivery.py:117`). `DeliveryPollEnv` runs as principal `buyer-001`
  and pre-seeds `ctx["db_tenant"]` / `ctx["db_principal_buyer-001"]` (conftest:3470-3477), so
  `_ensure_media_buy_in_db` reuses them. `MediaBuyFactory.raw_request` is
  `{"packages": [{"package_id": "pkg_001", "product_id": "prod_001"}]}` (`tests/factories/media_buy.py:35-39`),
  and `by_package` is built from `buy.raw_request["packages"]`
  (`src/core/tools/media_buy_delivery.py:419-424`) — so `pkg_001` is the emitted package id.
* **Given adapter reports N/S** — new step wrapping the existing `env.set_adapter_response(...)`
  (`tests/harness/_mixins.py:174-199`), whose default `package_id` is already `"pkg_001"`, matching the factory.
* **Then impressions / spend** — production copies the adapter's per-package values through unchanged
  (`media_buy_delivery.py:338-348` → `441-445` → `479-484`), so the assertion compares the exact injected literal.
  Exact-value comparison, not truthiness.
* **Then missing_metrics empty-or-absent** — the graded check verbatim. Passes today because `PackageDelivery` has
  no such field, so `model_dump()` yields no key and the normalized value is `[]`. Stated plainly rather than
  dressed up: today this cannot fail; it becomes load-bearing the moment `missing_metrics` is implemented, and it
  is exactly what the storyboard grades. The two value assertions above it are what carry weight now.
* **Zero row** — proven-safe: the existing `the ad server adapter has no delivery data for "{mb_id}" in the
  requested period` step already drives `impressions=0, spend=0.0` and a sibling scenario asserts on it.

Deliberately **not** included (each would go red — see TICKET MATERIAL): `schema-valid against
get-media-buy-delivery-response.json`; any `required_metrics` discovery step; any breach-branch
`missing_metrics` entry assertion.

Transport-independence: `When the Buyer Agent requests delivery metrics for media_buy_ids [...]` routes through
`dispatch_request` → `env.call_via` (`tests/bdd/steps/generic/_dispatch.py:41-72`); the Thens read only
`ctx["response"]`. No transport branching.

---

## 6. Step inventory

**Existing — reused unchanged**

| Step | Definition |
|---|---|
| `Given a media buy "{mb_id}" owned by "{owner}" with status "{status}"` | `tests/bdd/steps/domain/uc004_delivery.py:117` |
| `When the Buyer Agent requests delivery metrics for media_buy_ids [...]` | `tests/bdd/steps/domain/uc004_delivery.py:703` (also `:1159`) |

**New — 3 step functions**

1. `Given the ad server adapter reports impressions {impressions:d} and spend {spend:f} for "{mb_id}"`
   → `env.set_adapter_response(media_buy_id=mb_id, impressions=impressions, spend=spend)`.
   The parametrized sibling of the existing fixed-value `the ad server adapter has delivery data for "{mb_id}"`
   (`uc004_delivery.py:273`); both are one-liners over the same env method, so no duplication to extract.

2. `Then the response packages should report "{field}" as {expected:f} for "{package_id}"`
   → one step for both metrics (`PackageDelivery.impressions` and `.spend` are both `float`), so impressions and
   spend do **not** get two near-identical functions. Locates the package by `package_id` across
   `resp.media_buy_deliveries[*].by_package`, then `assert float(getattr(pkg, field)) == expected`.
   Deliberately distinct from the existing `the response packages should include "{field}"`
   (`uc004_delivery.py:2225`), which only checks non-None and would be a trivial assertion here.

3. `Then the response packages should have an empty or absent missing_metrics array for "{package_id}"`
   → `assert pkg.model_dump().get("missing_metrics", []) == []` — `model_dump()` rather than `getattr` so the
   check is meaningful for a field the model does not define (same reasoning as the existing
   `the response packages should NOT include "{field}"` at `uc004_delivery.py:2265-2280`).
   **Phrasing chosen to match the dormant sibling `@T-UC-004-missing-metrics-clean` (feature line 1149) verbatim**,
   so one definition serves both. That sibling stays xfailed regardless — its Given
   (`package "pkg-1" committed to deliver metric "completed_views"`) is still undefined — so adding this step
   introduces no new red.

All three use `assert x == y` comparisons, so they clear `test_architecture_bdd_no_trivial_assertions.py`
(`_assert_is_meaningful` accepts `ast.Compare`) and `test_architecture_bdd_no_pass_steps.py`.

---

## 7. TICKET MATERIAL

* **`filters.required_metrics` is accepted and silently ignored — products that cannot report the requested
  metrics are still returned.** `src/core/tools/products.py:460-606` filters on `delivery_type`,
  `is_fixed_price`, `format_ids`, `standard_formats_only`, `countries`, `channels`, `device_types` only; zero
  references to `required_metrics` anywhere in `src/`. 3.1.1 `core/product-filters.json:474`: *"Sellers MUST
  silently exclude products that cannot meet this list (filter-not-fail; do not return an error)."* Superset test
  must account for `available_metrics`'s implicit `impressions`/`spend` (`core/reporting-capabilities.json`).

* **`by_package[].missing_metrics` is never emitted — the accountability contract has no implementation.**
  `PackageDelivery` (`src/core/schemas/delivery.py:162-215`) declares no `missing_metrics` field, and
  `src/core/tools/media_buy_delivery.py:479-500` never populates one. 3.1.1
  `media-buy/get-media-buy-delivery-response.json:357` + `core/missing-metric.json` mandate the field's semantics
  and shape; `measurement_accountability.yaml:241-244` grades the clean case. Until the field exists, the graded
  check passes only by absence, and the breach branch cannot be tested. Unblocks the two dormant siblings
  `@T-UC-004-missing-metrics-flagged` / `@T-UC-004-missing-metrics-clean` (feature lines 1131, 1144).

* **`package.committed_metrics` is not implemented, so `missing_metrics` has no primary reconciliation source.**
  `core/package.json` (mirrored at `tests/fixtures/adcp_schemas_pinned/core/package.json:76`) defines
  `committed_metrics` with per-entry `committed_at` as the audit-grade contract; the delivery schema says absence
  forces fallback to *"the product's current `reporting_capabilities.available_metrics`"*. We implement neither
  side. Blocks the previous item.

* **`by_package[]` omits three schema-required fields whenever the package carries no pricing info.**
  `src/core/tools/media_buy_delivery.py:489-497` emits `pricing_model`, `rate`, `currency` as `None` when
  `MediaPackage.package_config["pricing_info"]` is absent. 3.1.1
  `get-media-buy-delivery-response.json` → `by_package.items.allOf[1].required` is
  `["package_id", "spend", "pricing_model", "rate", "currency"]`. Any real schema validation of a delivery
  response fails here. This is why the proposed Gherkin drops the `schema-valid` Then.

* **`reporting_capabilities.available_metrics` is a hard-coded `["impressions"]` fallback, not a product
  declaration.** `src/core/product_conversion.py:485-493`. Products whose adapter/DB row has no
  `reporting_capabilities` all advertise the same minimal contract, so `required_metrics` discovery can never
  match anything beyond impressions/spend even once filtering is implemented.

* **`get_products` never emits `filter_exclusions.excluded_by`.** 3.1.1
  `media-buy/get-products-response.json:238-249` defines per-filter exclusion counts keyed by filter name, with
  `required_metrics` named explicitly as an example key and *"the metric names that excluded products"* as the
  `values` payload. Buyers cannot tell a metric-driven exclusion from an empty catalogue.

* **No `comply_test_controller` surface.** `measurement_accountability.yaml:7-11` lists it in `required_tools` and
  sets `prerequisites.controller_seeding: true`; its `simulate_delivery` scenario is how the storyboard injects
  delivery. Zero references in `src/` (only in four `.feature` files). The storyboard cannot be executed against us
  as written; our BDD substitutes `env.set_adapter_response`. Also blocks
  `universal/comply-controller-mode-gate.yaml` (`requires: [controller]`), which is the keystone for the
  Sandbox AAO Verified tier.

* **UC-004 has no route to `ProductEnv`, so no single BDD scenario can grade a discovery→create→delivery chain.**
  `tests/bdd/conftest.py:3460-3478` (`_detect_delivery_harness`, conftest:3117-3134) binds every UC-004 scenario to
  `DeliveryPollEnv`/`WebhookEnv`/`CircuitBreakerEnv`/`MediaBuyCreateEnv`; `ProductEnv` is reachable only from the
  `UC-GET-PRODUCTS` branch (conftest:3509-3514). The three-phase storyboard needs a composite env (or a
  cross-tool env) before `required_metrics`-at-discovery → `missing_metrics`-in-delivery can be graded end to end
  as the tag name promises.

* **`then_response_schema_valid` runs no validator.** Already known (brief §"Known production gaps"); relevant here
  because the scenario's line 1340 is currently a no-op and would go red the moment a validator is wired, for the
  two reasons above (missing top-level `status`, missing `by_package` required fields).

---

## 8. Risks

* **Nothing here was executed.** No DB in this session and the brief is propose-only. Every green claim is from
  reading `src/`, `tests/harness/`, `tests/factories/`, and `tests/bdd/conftest.py`. The proposed scenario needs a
  real `tox -e bdd -k required_metrics` run across all four transports before landing.
* **`pkg_001` coupling.** The assertion depends on `MediaBuyFactory.raw_request` (`"pkg_001"`) matching
  `set_adapter_response`'s default `package_id` (`"pkg_001"`). Both are defaults today; if either drifts, the
  package lookup fails. A shared constant would be better but is out of scope for a propose-only pass.
* **`spend` as `{spend:f}`.** `"250.00"` parses to `250.0` and `PackageDelivery.spend` is `float`, so `==` is
  exact for these literals. If someone adds a row with a value not exactly representable, the comparison needs a
  tolerance.
* **Zero-delivery row over `e2e_rest`.** The in-process path is proven by the existing
  `no delivery data … in the requested period` step; the e2e path persists a `DeliverySimulationConfig` row
  (`tests/harness/_mixins.py:201`) which I did not trace for zero-value handling. If that row misbehaves, drop the
  zero Examples block — the other two rows stand on their own.
* **The `missing_metrics` Then is unfalsifiable today**, by construction (the field does not exist). I kept it
  because it is the storyboard's only graded accountability check and it becomes real the day the field ships, but
  it should not be counted as coverage of the accountability contract. The two value assertions are the ones doing
  work.
* **`@polling` tag added** for consistency with the sibling missing-metrics scenarios. It does not change harness
  routing (`_detect_delivery_harness` returns `"poll"` by default), but it is a behaviour-affecting tag elsewhere,
  so worth a second look.
* **Drift note, not a proposal:** the adcp worktree sits at `ac1f4bb46` (3.1.8 forward-merge). I verified the
  3.1.1 storyboard on disk is byte-identical to the tag, but I did not audit whether 3.1.8 changes
  `missing_metrics` or the grading. Out of scope — we are pinned to 3.1.1 and not moving.
* **Tier path choice.** `domains/media-buy/…` and `protocols/media-buy/…` are byte-identical mirrors at 3.1.1. I
  cite `protocols/` to match the rest of the file. If the repo standardises on `domains/`, the footer needs a
  sweep, not a one-off change.

# Re-pin: `@T-UC-004-storyboard-controller-driven-delivery-schema-compliance`

Scenario: `tests/bdd/features/BR-UC-004-deliver-media-buy-metrics.feature:1317-1331`
Title: *Delivery reporting -- controller-injected impressions and spend produce schema-compliant get_media_buy_delivery response*

---

## 1. VERDICT

**GRADED** — and the tag `@storyboard-v3.1` stays.

The behaviour is graded by `media_buy_seller/delivery_reporting`, which lives in the
**`protocols/media-buy/`** tier and is listed in `requires_scenarios` of the media-buy
protocol baseline. We declare `supported_protocols=[media_buy]`
(`src/core/tools/capabilities.py:99,271`), so this scenario is squarely on our
conformance path. It is not specialism-gated (`agent.capabilities: [sells_media]` only),
so `@schema-v3.1` would be **wrong** here.

Two qualifications, both material:

1. **The scenario is dormant today.** No step definition in `tests/bdd/steps/` matches
   any of its three lines, so `tests/bdd/conftest.py`'s auto-xfail
   ("Step definition not found") swallows it. It asserts nothing at present.
2. **The headline graded check — `check: response_schema` — fails against current
   production.** I validated a faithful production response against the 3.1.1 schema
   with a `Draft7Validator` over `git show v3.1.1:static/schemas/source/...` and got
   exactly four errors (verbatim):

   ```
   ERR []                                          -> 'status' is a required property
   ERR ['media_buy_deliveries', 0, 'by_package', 0] -> 'pricing_model' is a required property
   ERR ['media_buy_deliveries', 0, 'by_package', 0] -> 'rate' is a required property
   ERR ['media_buy_deliveries', 0, 'by_package', 0] -> 'currency' is a required property
   ```

   So the "should be schema-valid against get-media-buy-delivery-response.json" Then
   **cannot land green** and is removed from the proposed Gherkin. The second graded
   check (`field_present: media_buy_deliveries`) *is* satisfiable and is asserted, with
   concrete values, in the replacement.

---

## 2. Real binding at 3.1.1

### What the footer wrongly points at

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/measurement_accountability.yaml
```

Both defects confirmed:

* **Stale ref.** `04f59d2d5` is an ancestor of beta.3 — older than our own 3.1.1 pin.
* **Off-by-one path.** `measurement_accountability.yaml` is the storyboard of the
  *next* scenario in the file (`@T-UC-004-storyboard-required-metrics-end-to-end-accountability`,
  line 1333) — which in turn cites `vendor_metric_accountability.yaml`, the storyboard of
  the scenario after *that* (line 1356). Classic shift-by-one.

The scenario's own prose names the truth twice — `# delivery_reporting storyboard: …`
(line 1324) and `# delivery_reporting: schema compliance after controller-driven delivery`
(line 1330).

### The correct binding

`static/compliance/source/protocols/media-buy/scenarios/delivery_reporting.yaml` @ `v3.1.1`
(verified present in the tag's tree; byte-identical to
`dist/compliance/3.1.1/protocols/media-buy/scenarios/delivery_reporting.yaml`, and to the
`domains/media-buy/` copy).

Phase **`simulate_and_verify`**, step **`get_delivery`** — file lines **206–232**.

Graded block, verbatim (lines 227–232):

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-media-buy-delivery-response.json schema"
          - check: field_present
            path: "media_buy_deliveries"
            description: "Response contains delivery data"
```

The request the graded step sends (lines 219–226) — note the flag, which is what the
current scenario's `include_package_daily_breakdown true` is echoing:

```yaml
        sample_request:
          account:
            brand:
              domain: "acmeoutdoor.example"
            operator: "pinnacle-agency.example"
          media_buy_ids:
            - "$context.media_buy_id"
          include_package_daily_breakdown: true
```

The injected numbers in the scenario title come from the preceding step
`simulate_delivery` (lines 182–204), whose own graded block is only
`field_value success == true`:

```yaml
        sample_request:
          account:
            sandbox: true
          scenario: "simulate_delivery"
          params:
            media_buy_id: "$context.media_buy_id"
            impressions: 5000
            clicks: 150
            reported_spend:
              amount: 250.00
              currency: "USD"
```

**Prose, not graded** (lines 214–218) — this is where "per-package breakdown with
impressions and spend" lives:

```yaml
        expected: |
          Return delivery metrics reflecting the simulated data:
          - media_buy_deliveries array with at least one entry
          - Per-package breakdown with impressions, spend
          - Response matches the get-media-buy-delivery-response.json schema
```

Only `media_buy_deliveries` presence and full-schema validity are graded. Per-package
impressions/spend is narrative. I still assert it — but as a *schema-required-field*
assertion (`by_package[].package_id`, `spend`) plus a pass-through value check, not as a
storyboard obligation.

**Tier: `protocols/`.** Referenced from `dist/compliance/3.1.1/protocols/media-buy/index.yaml:12`
(`requires_scenarios: - media_buy_seller/delivery_reporting`). Identical copy under
`domains/media-buy/`; the protocols tier is the one our `supported_protocols` declaration
activates.

---

## 3. Schema constraints at 3.1.1

All quotes from `git show v3.1.1:static/schemas/source/…`.

**`media-buy/get-media-buy-delivery-response.json`**

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
  "required": ["reporting_period", "currency", "media_buy_deliveries"]
```

* `currency`: `{"type": "string", "description": "ISO 4217 currency code", "pattern": "^[A-Z]{3}$"}`
* `reporting_period`: `required: ["start", "end"]`, both `"format": "date-time"`
* `media_buy_deliveries.items.required`: `["media_buy_id", "status", "totals", "by_package"]`
* `…items.status.enum`: `["pending_creatives","pending_start","pending","active","paused","completed","rejected","canceled","failed","reporting_delayed"]`
* `…items.totals`: `allOf[core/delivery-metrics.json, {required: ["spend"]}]`
* `…items.by_package.items`: `allOf[core/delivery-metrics.json, {…}]` with

```json
   "required": ["package_id", "spend", "pricing_model", "rate", "currency"]
```

* `…by_package.items.…currency`: `"pattern": "^[A-Z]{3}$"`
* `…items.daily_breakdown.items.required`: `["date", "impressions", "spend"]`, `date` pattern `^\d{4}-\d{2}-\d{2}$`

**`core/protocol-envelope.json`** — new in the 3.1 line, composed into this response:

```json
  "required": [ "status" ]
```

with the description leaving no wiggle room:

> "The `status` field is REQUIRED on every task response envelope, including
> synchronous metadata responses … Agents shipping responses without a top-level
> `status` are non-conformant regardless of whether the task body schema would
> otherwise validate."

**`media-buy/get-media-buy-delivery-request.json`** — the flag the graded step sets:

```json
    "include_package_daily_breakdown": {
      "type": "boolean",
      "default": false,
      "description": "When true, include daily_breakdown arrays within each package in by_package. …"
    }
```

(`required: null` — every request field is optional.)

**`core/delivery-metrics.json`** — no `required` at all; `impressions`, `spend`, `clicks`
are each `{"type": "number", "minimum": 0}`. `viewability` is an **object**
(`measurable_impressions`, `viewable_impressions`, `viewable_rate`, `viewed_seconds`,
`standard`, `vendor`), not a scalar.

---

## 4. Conflicts

**Schema vs storyboard.** No direct contradiction — but where the storyboard's `expected:`
prose is looser than the schema, **the 3.1.1 schema wins**, and I wrote the assertions from
the schema's `required:` arrays rather than from the prose bullets. Concretely: the prose says
"per-package breakdown with impressions, spend"; the schema additionally requires
`pricing_model`, `rate`, `currency` on every `by_package` entry. The schema is the assertion
target — which is precisely why three of the four validator errors sit there.

**What the current scenario gets wrong:**

1. **Wrong `@source` path and stale ref** (§2).
2. **Dormant** — zero of its three steps exist, so the whole thing is auto-xfailed. It has
   never graded anything.
3. **`Then the response should be schema-valid against get-media-buy-delivery-response.json`
   is a vacuous phrasing *and* a red assertion.** Vacuous: the only step in the repo with that
   shape (`tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101`) is
   list-creative-formats-specific and asserts nothing but `isinstance(formats, list)`. Red:
   a real validator produces the four errors in §1, and `tests/helpers/pinned_schema.py`
   would validate against `04f59d2d5`, not 3.1.1, anyway.
4. **`And the response should carry a media_buy_deliveries array with at least one entry`**
   is an existence check — rejected by `test_architecture_bdd_no_trivial_assertions.py`.
   Replaced with an exact-list comparison.
5. **`And the per-package breakdown should reflect the injected impressions and spend`** is
   unquantified prose. Replaced with literal value comparisons parametrized from the
   Examples table.
6. **`Given a comply_test_controller has injected …` claims a tool we do not implement.**
   `grep -r comply_test_controller src/` returns nothing. The storyboard makes it a hard
   prerequisite (`required_tools:` line 11, `prerequisites.controller_seeding: true` line 40).
   The proposed Gherkin uses the repo's real seeding seam — the adapter-response
   injection used by every other green UC-004 scenario — and says so in a comment rather
   than naming a tool that does not exist.
7. **`clicks 150` is injected and then silently dropped.** Production hardcodes
   `clicks = 0` (`src/core/tools/media_buy_delivery.py:521`) and discards the adapter's
   per-package clicks (`:343`). Kept in the Given (it is in the storyboard's
   `sample_request`) as a no-corruption control; deliberately **not** asserted, because
   asserting the current `0` would pin the bug. Ticket filed.
8. **`include_package_daily_breakdown true` is accepted and ignored.** Nothing in
   production emits any `daily_breakdown`. Rather than assert its absence (pinning a
   bug), the Outline runs both `true` and `false` and asserts the graded invariants are
   flag-independent — which is true today and remains true after the gap is fixed.

---

## 5. Proposed Gherkin

Replaces lines 1317–1331 verbatim.

```gherkin
  @T-UC-004-storyboard-controller-driven-delivery-schema-compliance @storyboard-v3.1 @v3-1 @schema-compliance @controller-driven
  Scenario Outline: Delivery reporting -- injected impressions and spend surface on the fields the delivery_reporting storyboard grades
    Given a media buy "mb-sb004" owned by "buyer-001" with status "active"
    And the ad server adapter has delivery data for "mb-sb004" with impressions <impressions>, clicks <clicks>, and spend <spend> USD
    When the Buyer Agent requests delivery metrics for "mb-sb004" with include_package_daily_breakdown <daily_breakdown>
    Then the response should include delivery data for "mb-sb004" only
    And the response should include the media buy status "active"
    And the delivery totals for "mb-sb004" should be impressions <impressions> and spend <spend>
    And the by_package entry "pkg_001" should report impressions <impressions>, spend <spend>, and pacing_index 1.0
    And the response currency should be "USD"
    And the response reporting_period should span 30 days
    # delivery_reporting phase simulate_and_verify / step get_delivery grades exactly two
    # things: check=response_schema and check=field_present media_buy_deliveries. The
    # assertions above are the 3.1.1 required-field set this seller actually satisfies:
    #   response.required           -> reporting_period(start,end), currency ^[A-Z]{3}$, media_buy_deliveries
    #   deliveries[].required       -> media_buy_id, status(enum), totals(spend), by_package
    #   by_package[].required       -> package_id, spend   (pricing_model/rate/currency: gap, see #NNNN)
    # Full response_schema validity is NOT asserted: the response omits the
    # protocol-envelope `status` and three required by_package fields (#NNNN, #NNNN).
    # The storyboard seeds delivery through comply_test_controller/simulate_delivery,
    # which this seller does not implement (#NNNN); the adapter-response seam is the
    # equivalent injection point and is what every green UC-004 scenario uses.
    # clicks is injected because the storyboard's sample_request injects it, and is
    # deliberately not asserted -- production hardcodes totals.clicks = 0 (#NNNN).
    # Both daily_breakdown modes run: the graded fields are flag-independent, and
    # production honours neither (#NNNN).
    # @source repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/media-buy/scenarios/delivery_reporting.yaml phase=simulate_and_verify step=get_delivery

    Examples: storyboard simulate_delivery injection (delivery_reporting.yaml:189-199)
      | impressions | clicks | spend   | daily_breakdown |
      | 5000        | 150    | 250.00  | true            |
      | 5000        | 150    | 250.00  | false           |

    Examples: storyboard viewability_delivery injection magnitude (delivery_reporting.yaml:309-320)
      | impressions | clicks | spend   | daily_breakdown |
      | 80000       | 0      | 1030.00 | true            |
```

Replace each `#NNNN` with the GitHub issue numbers filed from §7 before landing.

**Why every Then is green** (all verified against `src/`, plus the serializer run below):

| Then | Production evidence |
|---|---|
| `…delivery data for "mb-sb004" only` | `media_buy_ids=[mb]` filters to one buy; `then_includes_delivery_data_only` compares `mb_ids == [mb_id]` |
| `…media buy status "active"` | `resolve_canonical_status` → `"active"` (flight 2025-01-01→2027-12-31 from `MediaBuyFactory`); `MediaBuyDeliveryStatus` is a `StrEnum`, so `== "active"` holds. Same step is green at feature line 42 |
| totals impressions/spend | `media_buy_delivery.py:352-353` — `spend`/`impressions` taken straight from `adapter_response.totals` |
| by_package impressions/spend/pacing_index | `:439-447` uses `adapter_package_metrics["pkg_001"]` (the factory's `raw_request` package id matches the harness adapter's default); `:485` `pacing_index=1.0 if status == "active"` |
| currency `"USD"` | `:675` hardcoded `currency="USD"` |
| reporting_period spans 30 days | `:221-226` — no `start_date`/`end_date` in the request → `end = now(UTC)`, `start = end - timedelta(days=30)` |

Serializer check I ran (production models, not a mock):

```
PKG WIRE: {'package_id': 'pkg_001', 'impressions': 5000.0, 'spend': 250.0, 'pacing_index': 1.0}
MB  WIRE: {'media_buy_id': 'mb-sb004', 'status': 'active', 'is_adjusted': False,
           'pricing_model': 'cpm',
           'totals': {'impressions': 5000.0, 'spend': 250.0, 'clicks': 0.0, 'ctr': 0.0},
           'by_package': [{'package_id': 'pkg_001', 'impressions': 5000.0, 'spend': 250.0,
                           'pacing_index': 1.0}],
           'ext': {}}
```

Note `clicks: 0.0` on the wire despite 150 injected, and `pricing_model`/`rate`/`currency`
absent from `by_package` — the two gaps, confirmed empirically.

---

## 6. Step inventory

### Reused as-is (no new code)

| Step | Location |
|---|---|
| `Given a media buy "{mb_id}" owned by "{owner}" with status "{status}"` | `tests/bdd/steps/domain/uc004_delivery.py:117` |
| `Then the response should include delivery data for "{mb_id}" only` | `…/uc004_delivery.py:1204` |
| `Then the response should include the media buy status "{status}"` | `…/uc004_delivery.py:1317` |

### New (5 steps, all in `tests/bdd/steps/domain/uc004_delivery.py`)

1. `@given(parsers.parse('the ad server adapter has delivery data for "{mb_id}" with impressions {impressions:d}, clicks {clicks:d}, and spend {spend:f} USD'))`
   → `env.set_adapter_response(media_buy_id=mb_id, impressions=impressions, spend=spend, clicks=clicks)`.
   The parametrized sibling of the existing `:273` step, which hardcodes the harness
   defaults (5000/250.0). Not a duplicate body — `test_architecture_bdd_no_duplicate_steps.py`
   compares bodies, and this one forwards four parameters the existing one cannot express.

2. `@when(parsers.parse('the Buyer Agent requests delivery metrics for "{mb_id}" with include_package_daily_breakdown {flag}'))`
   → `dispatch_request(ctx, media_buy_ids=[mb_id], include_package_daily_breakdown=json.loads(flag))`.

3. `@then(parsers.parse('the delivery totals for "{mb_id}" should be impressions {impressions:d} and spend {spend:f}'))`
   → locate the delivery row by id; `assert row.totals.impressions == impressions` and
   `assert row.totals.spend == spend`.

4. `@then(parsers.parse('the by_package entry "{package_id}" should report impressions {impressions:d}, spend {spend:f}, and pacing_index {pacing:f}'))`
   → find `by_package` entry by `package_id` (assert it exists by id, not by index),
   then three literal comparisons.

5. `@then(parsers.parse('the response currency should be "{currency}"'))` and
   `@then(parsers.parse('the response reporting_period should span {days:d} days'))`
   → `assert wire_field(ctx, "currency") == currency`; and
   `assert (period.end - period.start) == timedelta(days=days)`.
   Prefer `wire_field`/`wire_dict` (`tests/bdd/steps/_outcome_helpers.py:18,43`) so the
   assertion lands on the bytes the buyer receives, not the typed model.

### Shadowing check (done, per the UC-004 generic-shadowing history)

* `@when(parsers.re(r"the Buyer Agent requests delivery metrics with (?P<request_params>\w+=.+)"))` (`:722`)
  needs the literal `metrics with` and an `=`; the new When reads `metrics for "…" with` and
  has no `=`. No match.
* `@when(parsers.parse('the Buyer Agent requests delivery metrics for "{mb_id}"'))` (`:999`) —
  `parse` is end-anchored; the longer string does not match.
* `@when(parsers.re(r'…for "(?P<mb_id>[^"]+)" with reporting_dimensions (?P<dims_json>\{.+\})'))` (`:982`)
  requires `with reporting_dimensions`. No match.
* `@when(parsers.parse("the Buyer Agent requests delivery metrics with include_package_daily_breakdown {value}"))` (`:1051`)
  exists but sends **no `media_buy_ids`** (it is a partition-dispatch step). Deliberately not
  reused — this scenario must scope to one buy.
* `@given(parsers.parse('the ad server adapter has delivery data for "{mb_id}"'))` (`:273`) —
  end-anchored, will not swallow the `with impressions …` suffix.

---

## 7. TICKET MATERIAL

Everything below is real and cannot land green in this PR.

**Already known — cite, do not re-file**

* No top-level `status` on responses. `GetMediaBuyDeliveryResponse`
  (`src/core/schemas/delivery.py:310-327`) declares no `status`; 3.1.1 composes
  `core/protocol-envelope.json` (`required: ["status"]`) into
  `get-media-buy-delivery-response.json`. Confirmed as validator error #1 in §1.
* `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not 3.1.1
  (`tests/helpers/pinned_schema.py:1-8`).
* No BDD step runs a real schema validator. The only `schema-valid against …` step,
  `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-111`, is
  list-creative-formats-specific and asserts `isinstance(formats, list)` and nothing more,
  while `tests/helpers/pinned_schema.py::validate_against_pinned_schema` sits unused by BDD.

**New**

* **`by_package[]` omits three schema-required fields.** 3.1.1
  `get-media-buy-delivery-response.json` →
  `media_buy_deliveries.items.by_package.items.allOf[1].required = ["package_id","spend","pricing_model","rate","currency"]`.
  Production sets all three from `MediaPackage.package_config["pricing_info"]`
  (`src/core/tools/media_buy_delivery.py:487-495`) and leaves them `None` when the key is
  absent; `PackageDelivery` declares them optional
  (`src/core/schemas/delivery.py:173-185`), and `AdCPBaseModel` drops `None`, so they
  vanish from the wire entirely (serializer output in §5). This is 3 of the 4 errors that
  make the graded `check: response_schema` at
  `delivery_reporting.yaml:228` fail. Fix: derive `pricing_model`/`rate`/`currency` from the
  buy's pricing option when `package_config` has no `pricing_info`, and make the three
  fields required on `PackageDelivery`.

* **`totals.clicks` is hardcoded to 0 and `ctr` with it.**
  `src/core/tools/media_buy_delivery.py:521` — `clicks = 0`, followed by
  `ctr = (clicks / impressions) …` at `:523`. The adapter's clicks are explicitly thrown
  away at `:343` (`"clicks": None,  # AdapterPackageDelivery doesn't have clicks yet`).
  The graded storyboard injects `clicks: 150`
  (`delivery_reporting.yaml:196`). This is worse than a missing metric: `ctr: 0.0` is an
  affirmatively wrong number on the wire, and `core/delivery-metrics.json` defines both
  as `{"type":"number","minimum":0}` with no "0 means unknown" semantics. Fix: carry
  clicks through `AdapterPackageDelivery` and emit `ctr` as `None` when clicks are unknown.

* **`include_package_daily_breakdown` is accepted and ignored.** The 3.1.1 request schema
  defines it as *"When true, include daily_breakdown arrays within each package in
  by_package"*; the graded step sends `true`
  (`delivery_reporting.yaml:226`). Production threads the flag from all three transports
  (`src/core/tools/media_buy_delivery.py:733,751,804,860`; `src/routes/api_v1.py:396`;
  `src/a2a_server/adcp_a2a_server.py:2051`) into the request model and then never reads
  it. `MediaBuyDeliveryData.daily_breakdown` is hardcoded `None`
  (`src/core/tools/media_buy_delivery.py:549`) and `PackageDelivery`
  (`src/core/schemas/delivery.py:159+`) has no `daily_breakdown` field at all, so the
  package-level array the flag names cannot even be represented. Fix: add
  `daily_breakdown: list[DailyBreakdownEntry] | None` to `PackageDelivery` (schema:
  `required: ["date","impressions","spend"]`, `date` pattern `^\d{4}-\d{2}-\d{2}$`) and
  populate it when the flag is true.

* **`comply_test_controller` is not implemented, so this storyboard cannot be run against
  us at all.** `delivery_reporting.yaml:7-11` lists it under `required_tools`;
  `:34-40` sets `prerequisites.controller_seeding: true` and states *"The seller must
  implement comply_test_controller with the simulate_delivery scenario."*
  `grep -r comply_test_controller src/` returns nothing. Every `simulate_and_verify` and
  `viewability_delivery` step depends on it. Scope note: `universal/comply-controller-mode-gate.yaml`
  additionally requires FORBIDDEN for live-mode callers, but that one is gated on the
  `supports_test_controller` capability, so it only bites once the controller ships.

* **`response.currency` is hardcoded `"USD"`.**
  `src/core/tools/media_buy_delivery.py:675` — `currency="USD"` with an in-tree
  `TODO: @yusuf - This is wrong`. It satisfies the 3.1.1 `^[A-Z]{3}$` pattern, so it is not
  a schema violation, but it misreports the currency for any non-USD buy — and
  `MediaBuy.currency` is right there on the model. Fix: derive from the buy / tenant
  currency limit.

* **`DeliveryTotals.viewability` is a scalar where 3.1.1 requires an object.**
  `src/core/schemas/delivery.py:119` declares
  `viewability: float | None = Field(None, ge=0, le=1, …)`. In 3.1.1
  `core/delivery-metrics.json`, `viewability` is `{"type": "object"}` carrying
  `measurable_impressions`, `viewable_impressions`, `viewable_rate`, `viewed_seconds`,
  `standard`, `vendor`. Production assigns it straight from the adapter
  (`src/core/tools/media_buy_delivery.py:360,548`), so any seller that populates it emits a
  bare float and fails `response_schema`. This also leaves the storyboard's entire
  `viewability_delivery` phase (`delivery_reporting.yaml:234-370`, **six** graded
  `field_present` checks on `media_buy_deliveries[0].totals.viewability.*`) with zero
  coverage in our feature files. Fix: model `viewability` as an object extending the
  library type, then wire a second scenario against that phase.

---

## 8. Risks

* **Not executed.** No step definitions exist for this scenario yet and the brief forbids
  editing the repo, so the proposed Gherkin has not been run. Green-ness is argued from
  source reading plus two things I *did* execute: the production model serialization and
  the 3.1.1 `Draft7Validator` run in §1/§5.
* **`reporting_period should span 30 days`** depends on the default branch at
  `media_buy_delivery.py:221-226`. `end = datetime.now(UTC)`, `start = end - 30d`, so the
  delta is exact and clock-independent — but it would break if a future change defaults the
  window to the buy's flight instead. That is arguably the more correct behaviour, so treat
  this Then as the one most likely to need updating.
* **Package-id coupling.** `pkg_001` is green only because `MediaBuyFactory.raw_request`
  (`tests/factories/media_buy.py:35-39`) and the harness adapter default
  (`tests/harness/_mixins.py:174-182`) both use `pkg_001`. If either changes the scenario
  goes red for a reason unrelated to the protocol. The step looks the entry up **by
  `package_id`** rather than by index specifically so the failure message says which id it
  expected.
* **Zero-delivery row not included.** I considered an `impressions 0 / spend 0` Examples row;
  the storyboard does not motivate one and `then_has_metrics` already covers the
  nonzero-spend-implies-nonzero-impressions invariant elsewhere.
* **Drift beyond our pin, noted only.** 3.1.8/HEAD were not consulted and are not
  authority here.
* **`@controller-driven` tag kept** even though the seeding no longer names a controller,
  per the brief's "keep the tag vocabulary". If the reviewer would rather the tag track
  reality, it should become something like `@adapter-seeded` — but that changes vocabulary,
  so I left it.

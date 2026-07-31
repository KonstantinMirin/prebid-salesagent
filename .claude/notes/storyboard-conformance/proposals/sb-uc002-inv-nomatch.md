# Re-pin: `@T-UC-002-storyboard-inventory-list-no-match`

Scenario: `tests/bdd/features/BR-UC-002-create-media-buy.feature:2680`
Title today: *"Inventory list references that resolve to zero inventory -- zero-forecast or informative error, never silent success"*

---

## 1. VERDICT

**NOT GRADED — prose only** (for the behaviour the scenario currently asserts).

The scenario *is* on our conformance path — `media_buy_seller/inventory_list_no_match` is listed in
`requires_scenarios` of `protocols/media-buy` (we declare `supported_protocols=[media_buy]`) and of
`specialisms/sales-non-guaranteed` (we declare it). So the `@storyboard-v3.1` tag stays.

But the *behaviour the Gherkin asserts* — "zero-forecast OR `PRODUCT_UNAVAILABLE`/`INVALID_REQUEST` with
findings" — appears **only under `expected:`**, which is narrative prose. The step's `validations:` block
grades **two things and nothing else: that `context` is echoed and that `context.correlation_id` comes back
unchanged.**

Two consequences, both load-bearing:

* Every Then currently in the scenario grades nothing the storyboard grades.
* The one thing 3.1.1 *does* grade here — context echo — **our production passes on the success path and
  fails on the error path** (verified on all three transports, §4). So an error-shaped scenario cannot be
  both green and storyboard-graded. The rewrite in §5 therefore takes the success branch.

Secondary: the scenario is **dormant today**. None of its step texts exist anywhere in `tests/bdd/steps/`
(`grep` for "no-match list references", "one of the following two outcomes" → zero hits), and
`tests/bdd/conftest.py:3282` blanket-xfails it via
`pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")`. Confirmed by running it:
`3 xfailed` (mcp/a2a/rest).

---

## 2. Real binding at 3.1.1

**What the footer wrongly points at (line 2696):**

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/inventory_list_targeting.yaml
```

Both defects present: stale `ref` (04f59d2d5 is an ancestor of beta.3, older than our 3.1.1 pin) **and**
the off-by-one path — it cites `inventory_list_targeting`, which is the *next* scenario's storyboard
(`@T-UC-002-storyboard-inventory-list-targeting-parity` at line 2698). The scenario's own prose line 2695
self-declares `inventory_list_no_match`.

**The real file:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_no_match.yaml`
(byte-identical mirror also at `dist/compliance/3.1.1/domains/media-buy/scenarios/inventory_list_no_match.yaml`;
`git show v3.1.1:static/compliance/source/protocols/media-buy/scenarios/inventory_list_no_match.yaml` is
byte-identical to the 3.1.1 dist copy — verified by `diff`).

**Phase/step:** `phases[1].id = no_match_attempt` → `steps[0].id = create_buy_no_match`
(`task: create_media_buy`, `comply_scenario: create_media_buy`, `stateful: true`).

**The graded block, verbatim (lines 141–148):**

```yaml
        validations:
          - check: field_present
            path: "context"
            description: "Response echoes back the context object (success or error)"
          - check: field_value
            path: "context.correlation_id"
            value: "inventory_list_no_match--create_buy_no_match"
            description: "Context correlation_id returned unchanged"
```

That is the **entire** graded surface of the step. For contrast, the ungraded prose (lines 102–115):

```yaml
        expected: |
          One of two acceptable outcomes:

          1. Buy accepted with zero-forecast reporting — status may be
             pending_creatives/pending_start/active, but the seller returns
             packages with forecast indicating zero deliverable inventory and
             a message explaining the list mismatch.

          2. Buy rejected with an informative error — typically
             INSUFFICIENT_INVENTORY or INVALID_TARGETING — including findings
             that identify which list(s) matched nothing.

          What is NOT acceptable: a silently-successful buy with normal forecast
          numbers, or a crash / non-AdCP error shape.
```

The preceding `discover` phase (`get_products_brief`) grades `response_schema` and
`field_present: products[0].pricing_options[0].fixed_price` — out of scope for a UC-002 create scenario.

**Tier ownership.** Registered in four indexes:

| index | line | we declare it? |
|---|---|---|
| `dist/compliance/3.1.1/protocols/media-buy/index.yaml` | 16 | **yes** — `supported_protocols=[media_buy]` |
| `dist/compliance/3.1.1/domains/media-buy/index.yaml` | 16 | mirror of the protocol tier |
| `dist/compliance/3.1.1/specialisms/sales-non-guaranteed/index.yaml` | 19 | **yes** — `specialisms=[sales_non_guaranteed]` |
| `dist/compliance/3.1.1/specialisms/sales-guaranteed/index.yaml` | 18 | no |

Declared on two counts → on our conformance path → `@storyboard-v3.1` is justified, **not** `@schema-v3.1`.

One nuance worth recording: the storyboard's own `agent.capabilities` block requires
`supports_property_list_targeting` and `supports_collection_list_targeting`. We declare
`MediaBuyFeatures.property_list_filtering = supports_property_list_filtering(adapter)`
(`src/core/tools/capabilities.py:176`), and **no adapter sets that ClassVar to True today**
(`src/services/targeting_capabilities.py:200-213` says so explicitly). There is no collection-list
capability declaration at all. So we are on the tier path but we advertise the feature OFF — which is
exactly why production emits the `UNSUPPORTED_FEATURE` advisory the rewrite asserts.

---

## 3. Schema constraints at 3.1.1

**`core/context.json`** — the whole file:

```json
{
  "title": "Context Object",
  "description": "Opaque correlation data that is echoed unchanged in responses. ... Context data is never parsed by AdCP agents - it's simply preserved and returned.",
  "type": "object",
  "additionalProperties": true
}
```

**`media-buy/create-media-buy-response.json`**, `oneOf[0] CreateMediaBuySuccess`:

```
required: ["media_buy_id", "confirmed_at", "revision", "packages"]
additionalProperties: true
properties: account, available_actions, confirmed_at, context, creative_deadline, currency, ext,
            invoice_recipient, media_buy_id, media_buy_status, packages, planned_delivery,
            revision, sandbox, status, total_budget, valid_actions
```

`context` on **both** the Success and the Error variant (identical wording):

> "Opaque media-buy-level correlation data echoed unchanged from the create_media_buy request. Sellers
> **MUST** echo this object verbatim when the originating request carried context, including synchronous
> success, **error**, submitted, and webhook task-status payloads. Sellers MUST NOT parse this object for
> business logic."

`media_buy_status`:

> "Initial media buy status. Either 'pending_creatives' (awaiting creative assets), 'pending_start' (ready
> to serve, waiting for flight date), 'active' (immediate activation), or 'paused' ... Added in 3.1: at the
> top level of flat-on-the-wire MCP responses, the `status` key is reserved for the envelope TaskStatus
> (`completed` on synchronous success)."

`CreateMediaBuyError`: `required: ["errors"]`, `errors.minItems: 1`, items `$ref core/error.json`.

**`core/protocol-envelope.json`** — `required: ["status"]`, and on the two-layer error model:

> "a fatal task failure SHOULD populate both this envelope-level field AND the payload's `errors[]` array …
> Non-fatal warnings populate ONLY `payload.errors[]` with `severity: warning` — the envelope MUST NOT carry
> `adcp_error` for non-failures."

**`core/error.json`** — `required: ["code","message"]`, `additionalProperties: true`,
properties: `code, details, field, issues, message, recovery, retry_after, sdk_id, source, suggestion`.
Note: **`severity` is not a declared property at 3.1.1.** `field`:

> "Field path associated with the error in JSONPath-lite format (e.g., 'packages[0].targeting')."

**`enums/error-code.json`** — 92 entries. Present: `PRODUCT_UNAVAILABLE`, `INVALID_REQUEST`,
`VALIDATION_ERROR`, `UNSUPPORTED_FEATURE`, `REFERENCE_NOT_FOUND`.
**Absent: `INSUFFICIENT_INVENTORY`. Absent: `INVALID_TARGETING`.** (Only `SIGNAL_TARGETING_INCOMPATIBLE`
matches `*TARGET*`; nothing matches `*INVENT*`.)

**`core/targeting.json`** `property_list`:

> "$ref: /schemas/core/property-list-ref.json — Reference to a property list for targeting specific
> properties within this product. The package runs on the intersection of the product's
> publisher_properties and this list. **Sellers SHOULD return a validation error if the product has
> `property_targeting_allowed: false`.**"

`collection_list`:

> "The package runs on the intersection of matched collections and this list. Use for inclusion-based
> collection targeting. **Seller must declare support in get_adcp_capabilities.**"

**`core/property-list-ref.json` / `core/collection-list-ref.json`** — both
`required: ["agent_url","list_id"]`, `additionalProperties: false`, `list_id.minLength: 1`,
`agent_url` `format: uri`.

---

## 4. Conflicts

### 4a. Schema overrides storyboard — the storyboard names two non-existent error codes

The storyboard prose (`expected:` line 110-112, and its `narrative:` line 17) tells sellers to reject with
"`INSUFFICIENT_INVENTORY` or `INVALID_TARGETING`". **Neither code exists in `enums/error-code.json` at
3.1.1.** Per the authority order, the **schema wins**: no scenario may assert either code. This also
retroactively justifies why the current Gherkin substituted `PRODUCT_UNAVAILABLE`/`INVALID_REQUEST` — but
that substitution was never grounded in anything, it was a guess, and it is not what production emits.

### 4b. Schema overrides envelope prose on `severity`

`protocol-envelope.json` says non-fatal warnings carry `severity: warning`. `core/error.json` at 3.1.1 does
not declare a `severity` property at all (`additionalProperties: true` permits it, nothing requires it). Our
advisories omit it; that is schema-conformant. Not a defect.

### 4c. What the scenario gets wrong today

1. **Footer is off-by-one and stale** (§2).
2. **`Then the response should NOT be a silent success with normal forecast numbers`** — a negative
   existence check with no concrete comparison. `test_architecture_bdd_no_trivial_assertions.py` territory.
3. **`And one of the following two outcomes should be observed:` + a two-row table** is not an assertion at
   all. It is a Gherkin data table whose "required behavior" column is English prose. Whichever outcome
   occurs, the step passes. This is the exact vacuous-Then shape the guards exist to reject.
4. **The error codes asserted (`PRODUCT_UNAVAILABLE` / `INVALID_REQUEST`) are not what production emits.**
5. **It grades nothing the storyboard grades** — no context assertion anywhere.
6. **"findings identifying lists"** — there is no `findings` field in AdCP 3.1.1. The nearest concepts are
   `error.details` and `error.issues[]`.
7. **Dormant** — no step definitions exist; blanket-xfailed at `tests/bdd/conftest.py:3282`.

### 4d. Verified production behaviour (the ground truth the rewrite is built on)

I drove `MediaBuyCreateEnv.call_via()` across **MCP, A2A and REST** (18 combinations) with the
storyboard's own list_ids and `context.correlation_id`. Results were transport-uniform:

| product `property_targeting_allowed` | lists sent | outcome |
|---|---|---|
| `false` (the DB default) | `property_list` | **rejected**: `adcp_error.code` and `errors[0].code` = `VALIDATION_ERROR`, `field` = `packages[].targeting_overlay.property_list`, `recovery` = `correctable`, `details.violations` = `["Product prod_1 does not allow property_list targeting (property_targeting_allowed=false)"]`. **No `context` on the envelope. No top-level `status`.** |
| `false` | `property_list` + `collection_list` | identical to the row above — the collection reference does not change the outcome |
| `false` | `collection_list` only | **accepted, `errors` absent entirely** — silent success |
| `true` | `property_list` | accepted: `status`=`completed`, `media_buy_status`=`pending_creatives`, `context`=`{"correlation_id":"inventory_list_no_match--create_buy_no_match"}`, `errors[0].code`=`UNSUPPORTED_FEATURE` with `field`=`packages[0].targeting_overlay.property_list`, `packages[0].targeting_overlay.property_list.list_id` round-trips |
| `true` | `property_list` + `collection_list` | as above, and `packages[0].targeting_overlay.collection_list.list_id` also round-trips |
| `true` | `collection_list` only | accepted, `errors` absent — silent success |

Corroborated by the existing green integration suite
`tests/integration/test_property_targeting_allowed_enforcement.py` (5 passed).

Two structural facts behind this:

* **Production never resolves an inventory list at create time.** `resolve_property_list()`
  (`src/core/property_list_resolver.py:42`) is only called from `get_products`
  (`src/core/tools/products.py:400-404`). `media_buy_create.py` never calls it. So a "no-match" list is
  indistinguishable from a matching one at `create_media_buy` — the zero-forecast branch of the storyboard
  is unreachable by construction.
* The `UNSUPPORTED_FEATURE` advisory (`src/services/targeting_capabilities.py:230-269`, emitted at
  `media_buy_create.py:1841/3561/4102`) is the honest wire signal we *do* have: it tells the buyer the
  list_id is persisted but will not affect targeting. That is precisely the storyboard's
  "must not silently drop the targeting" clause, answered truthfully for `property_list`.

**Why the rewrite takes the success branch.** It is the only branch where the graded validation
(`context` present, `correlation_id` unchanged) passes. On the rejection branch our error envelope drops
`context` on all three transports, so a rejection-shaped scenario would grade zero graded checks and would
go red the moment anyone added the graded one.

---

## 5. Proposed Gherkin

Complete replacement for `tests/bdd/features/BR-UC-002-create-media-buy.feature:2679-2696`.
GREEN ONLY — every asserted value was observed on the wire on all three transports (§4d).

```gherkin
  @T-UC-002-storyboard-inventory-list-no-match @storyboard-v3.1 @v3-1 @inventory-list @no-match
  Scenario Outline: Inventory list references that match no seller inventory are surfaced on the wire, never silently dropped -- <lists_sent>
    Given the tenant's product permits property_list targeting
    And the buyer sets package targeting_overlay to "<lists_sent>" using list_ids that match no seller inventory
    And the create_media_buy request carries context correlation_id "inventory_list_no_match--create_buy_no_match"
    When the Buyer Agent sends the create_media_buy request
    Then the response status should be "completed"
    And the response should include "media_buy_status" matching "pending_creatives"
    And the response context should carry correlation_id "inventory_list_no_match--create_buy_no_match"
    And the response errors should carry code "UNSUPPORTED_FEATURE" on field "packages[0].targeting_overlay.property_list"
    And the response package targeting_overlay "<echoed_list_field>" should carry list_id "<echoed_list_id>"

    Examples: list references that resolve to zero seller inventory
      | lists_sent                        | echoed_list_field | echoed_list_id                       |
      | property_list                     | property_list     | acme_outdoor_no_match_v1             |
      | property_list and collection_list | collection_list   | acme_outdoor_no_match_collections_v1 |

    # inventory_list_no_match storyboard, phase no_match_attempt, step create_buy_no_match.
    # The step's ONLY graded validations are context echo + context.correlation_id unchanged;
    # the "zero-forecast OR informative error" language lives under `expected:` and is narrative
    # prose, not a graded check. The two error codes that prose names —
    # INSUFFICIENT_INVENTORY and INVALID_TARGETING — are absent from
    # enums/error-code.json at 3.1.1, so no scenario may assert them (schema > storyboard).
    #
    # What this seller can truthfully claim at 3.1.1: it declares
    # media_buy.property_list_filtering=false (capabilities.py -> supports_property_list_filtering,
    # false for every adapter today), so it does NOT resolve buyer lists against inventory and
    # cannot report a zero forecast. It instead surfaces an UNSUPPORTED_FEATURE advisory on the
    # success envelope naming the exact field, and round-trips the list_ids on the package —
    # i.e. the targeting is neither silently dropped nor falsely forecast. That is the
    # "never silent success" invariant, honoured through the capability-advisory route.
    # Zero-forecast reporting, collection_list advisories, and context echo on the error
    # envelope are open gaps — see #<TBD-1>..#<TBD-5>.
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_no_match.yaml phase=no_match_attempt step=create_buy_no_match
```

Notes on the design:

* **Transport-independent.** Zero transport branching; all five Thens were observed identical on
  MCP / A2A / REST.
* **Both Examples rows are uniform** — same Thens, different concrete values. The second row proves a
  co-present `collection_list` neither suppresses the `property_list` advisory nor is itself dropped.
* **Every Then compares a concrete value.** No truthiness, no existence-only.
* `collection_list`-alone is deliberately **not** an Examples row: production accepts it with no advisory at
  all, and pinning that green would enshrine the silent-success failure mode the storyboard forbids. It is
  ticketed instead (§7).
* Do **not** assert `agent_url`: it round-trips normalised with a trailing slash
  (`https://governance.pinnacle-agency.example` → `…example/`). `list_id` round-trips byte-exact.

---

## 6. Step inventory

**Existing — reuse as-is (2):**

| step | definition |
|---|---|
| `When the Buyer Agent sends the create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:713` (default branch → `_dispatch_full_create`, builds a typed `CreateMediaBuyRequest` from `ctx["request_kwargs"]` and dispatches through the parametrized transport) |
| `Then the response should include "{field}" matching "{value}"` | `tests/bdd/steps/generic/then_media_buy.py:66` |
| `Then the response status should be "{status}"` | `tests/bdd/steps/generic/then_success.py:40` |

(Three reused step texts: one When, two Then.)

**New (6)** — 3 Given + 3 Then. Suggested home: `tests/bdd/steps/domain/uc002_create_media_buy.py`
(scenario-specific) except the last two, which are candidates for `generic/then_payload.py` if UC-003's
dormant `the response should echo the context.correlation_id unchanged` scenarios are wired later.

1. `@given("the tenant's product permits property_list targeting")` — flips
   `Product.property_targeting_allowed = True` on `ctx["default_product"]` and commits. Required: the
   column defaults to `False` (`src/core/database/models.py`, `mapped_column(Boolean, nullable=False,
   default=False)`) and `ProductFactory` (`tests/factories/product.py:14`) does not override it, so the
   harness product would otherwise trip `validate_property_targeting_allowed` and reject.
2. `@given(parsers.parse('the buyer sets package targeting_overlay to "{lists_sent}" using list_ids that match no seller inventory'))`
   — writes `request_kwargs["packages"][0]["targeting_overlay"]` from a two-entry mapping
   (`"property_list"` / `"property_list and collection_list"`) using the storyboard's own list_ids
   (`acme_outdoor_no_match_v1`, `acme_outdoor_no_match_collections_v1`) and agent_url
   `https://governance.pinnacle-agency.example`. A `KeyError` on an unknown phrase is the right failure —
   no silent fallback.
3. `@given(parsers.parse('the create_media_buy request carries context correlation_id "{corr}"'))` —
   sets `request_kwargs["context"] = {"correlation_id": corr}`.
4. `@then(parsers.parse('the response context should carry correlation_id "{corr}"'))` — reads
   `wire_field(ctx, "context")["correlation_id"]` (`tests/bdd/steps/_outcome_helpers.py:18`, which raises
   loudly if a wire transport failed to stash `wire_response`, so the assertion cannot go tautological)
   and compares `==`.
5. `@then(parsers.parse('the response errors should carry code "{code}" on field "{field}"'))` — reads
   `wire_field(ctx, "errors")`, asserts exactly one entry matches both `code` and `field`.
6. `@then(parsers.parse('the response package targeting_overlay "{list_field}" should carry list_id "{list_id}"'))`
   — reads `wire_field(ctx, "packages")[0]["targeting_overlay"][list_field]["list_id"]` and compares `==`.

Items 1–3 are the Givens, items 4–6 the Thens.

**Wiring change required (otherwise the scenario stays xfailed):**
`tests/bdd/conftest.py` — the UC-002 branch chain currently ends at
`pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")` (line 3282). Add
`T-UC-002-storyboard-inventory-list-no-match` to a branch that yields `MediaBuyCreateEnv` with
`setup_media_buy_data()` (same shape as the existing `T-UC-002-ext-` / idempotency branches at
lines ~3226 and ~3263). Without this the scenario keeps xfailing regardless of the steps.

---

## 7. TICKET MATERIAL

1. **`create_media_buy` error envelope drops `context` — schema-mandated echo violated.**
   `raise_if_property_targeting_violations` (`src/services/targeting_capabilities.py:315-330`) constructs
   `AdCPValidationError(...)` with no `context=`, and nothing at the MCP/A2A/REST boundary re-attaches
   `req.context`. Observed on all three transports: the wire error envelope has keys
   `{adcp_error, errors}` only — no `context`, no top-level `status`.
   Mandated by `media-buy/create-media-buy-response.json` @3.1.1, `CreateMediaBuyError.context`:
   *"Sellers MUST echo this object verbatim when the originating request carried context, including
   synchronous success, **error**, submitted, and webhook task-status payloads."* Also graded by
   `dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_no_match.yaml:141-148`
   (`field_present: context` — *"Response echoes back the context object (success or error)"*).
   This is almost certainly class-wide across every `AdCPError` raise site, not specific to this one.

2. **`collection_list` targeting is accepted silently — no capability gate, no advisory.**
   `src/services/targeting_capabilities.py:216-227` states the asymmetry explicitly ("Collection-list
   capability infrastructure lands separately"). Result: a `collection_list` that matches nothing is
   persisted, never resolved, never mentioned on the wire — `errors` is absent from the response entirely
   (verified, all three transports). This is exactly the failure mode the storyboard narrative forbids:
   *"What the seller must NOT do: … silently drop the targeting and deliver against unintended inventory."*
   `core/targeting.json` @3.1.1 `collection_list`: *"Seller must declare support in
   get_adcp_capabilities."* We declare nothing either way. Fix: declare collection-list support in
   `get_adcp_capabilities` and emit the sibling `UNSUPPORTED_FEATURE` advisory while it is off.

3. **Inventory lists are never resolved at `create_media_buy`, so zero-forecast reporting is unreachable.**
   `resolve_property_list()` (`src/core/property_list_resolver.py:42`) is called only from
   `src/core/tools/products.py:400-404` (`get_products`). `src/core/tools/media_buy_create.py` never calls
   it, and the response `packages[]` carry no forecast field at all
   (observed package keys: `package_id, product_id, budget, pricing_option_id, targeting_overlay, paused,
   canceled`). Storyboard `expected:` outcome (1) at
   `dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_no_match.yaml:105-108` requires
   *"packages with forecast indicating zero deliverable inventory and a message explaining the list
   mismatch."* Ungraded prose today, so not a conformance failure — but it is the reason this scenario can
   only ever grade the capability-advisory route.

4. **Error `field` uses an index-less path `packages[].targeting_overlay.property_list`, which is not
   JSONPath-lite.**
   `src/core/validation_helpers.py::package_field_path` produces `packages[]` with an empty subscript;
   `raise_if_property_targeting_violations` passes it through
   (`src/services/targeting_capabilities.py:325`). Observed verbatim on the wire on MCP/A2A/REST.
   `core/error.json` @3.1.1 `field`: *"Field path associated with the error in JSONPath-lite format
   (e.g., 'packages[0].targeting')."* The buyer cannot tell which package failed when more than one is
   sent. Note the *advisory* path already gets this right —
   `build_property_list_unsupported_advisories` emits `packages[{index}].targeting_overlay.property_list`
   (`src/services/targeting_capabilities.py:257`) — so the fix is to make the rejection path carry the
   same index.

5. **Upstream: the `inventory_list_no_match` storyboard prescribes two error codes that do not exist in
   the 3.1.1 vocabulary.**
   `dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_no_match.yaml:17` and `:110-112`
   name `INSUFFICIENT_INVENTORY` and `INVALID_TARGETING`. Neither is in
   `static/schemas/source/enums/error-code.json` @v3.1.1 (92 entries; nothing matching `*INVENT*`, and the
   only `*TARGET*` entry is `SIGNAL_TARGETING_INCOMPATIBLE`). Still present unchanged at 3.1.8. File
   upstream against `adcontextprotocol/adcp`: either add the codes to the enum or rewrite the prose to
   name enum members (`PRODUCT_UNAVAILABLE` is the natural fit). Until then no local scenario may assert
   either code.

6. **Upstream (minor): the graded surface of `inventory_list_no_match` is context echo only, so the
   scenario's whole point is ungraded.** The narrative describes three named failure modes (crash,
   misleading forecast, silent drop) and grades none of them. Worth proposing `validations:` entries — e.g.
   a `field_present` on a forecast/advisory signal — so the scenario grades what its title claims.

---

## 8. Risks

* **The three new Then steps and two new Given steps do not exist yet, so I could not execute the rewritten
  scenario end-to-end.** What I *did* execute is the underlying production path they will assert against:
  `MediaBuyCreateEnv.call_via()` over MCP/A2A/REST with the exact request shape and the exact
  `correlation_id` from the storyboard, 18 parameter combinations, all 18 passing, wire bodies captured and
  reproduced in §4d. Every literal in the proposed Gherkin is copied from those captures. The residual risk
  is step-plumbing (e.g. `wire_field` key access), not behavioural.
* **Two reused Thens read `ctx["response"]` (the typed payload) rather than `ctx["wire_response"]`.**
  `then_response_status` and `then_response_field_matches` predate the wire-assertion convention. Their
  values (`status="completed"`, `media_buy_status="pending_creatives"`) match the wire exactly in my
  captures, so they are green — but if the reviewer wants strict wire-only grading, replace both with
  `wire_field`-based steps. I left the reuse in to keep the new-step count down.
* **`media_buy_status` is `pending_creatives` because the harness creates the buy with no inline
  creatives.** Any future change to `MediaBuyCreateEnv.setup_media_buy_data()` that seeds creatives would
  flip this to `pending_start` and break the row. It is a legitimate concrete assertion, but it is coupled
  to harness setup rather than to the list-reference behaviour under test. Dropping that line costs little
  if the reviewer prefers.
* **The scenario now grades the accept-with-advisory branch only.** The rejection branch
  (`VALIDATION_ERROR` on a product with `property_targeting_allowed=false`) is real, green, and arguably
  the storyboard's outcome (2) — but it cannot carry the one graded validation (context echo, ticket #1),
  so folding it in would mean either two scenarios sharing one `@T-UC-…` identifier tag or dropping the
  graded assertion. I chose the graded assertion. If the lead prefers coverage of both branches, the clean
  shape is a sibling locally-added scenario with its own identifier once ticket #1 lands.
* **A2A emits a legacy top-level `"success"` boolean** (`false` on the advisory rows, `true` on the clean
  row — i.e. it is inverted/meaningless here). Not in any 3.1.1 schema. I deliberately assert nothing on
  it; flagging it in case it belongs in someone else's sweep.
* **Top-level `status` semantics.** We emit the envelope TaskStatus (`completed`) at the response root
  while `create-media-buy-response.json` `CreateMediaBuySuccess.status` declares that slot as the
  *deprecated* `MediaBuyStatus`. We also emit `media_buy_status` alongside, which is what 3.1 says buyers
  MUST prefer. This is the known dual-emit question already tracked by
  `tests/bdd/test_media_buy_status_dual_emit.py`; out of scope here, noted so it is not rediscovered.
* **Version drift (noted only, per the brief):** the graded `validations:` block is byte-identical at
  3.1.1 and 3.1.8; the only diff in the whole file is a `brief:` string. Nothing to reconcile.
* I did not modify any file under `/Users/konst/projects/salesagent-sbsweep`. The two temporary probe
  modules used for §4d were copied in, run, and deleted in the same command; `git status` afterwards shows
  only other agents' files.

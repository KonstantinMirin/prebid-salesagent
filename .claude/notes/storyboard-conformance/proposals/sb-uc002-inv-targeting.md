# Re-pin: `@T-UC-002-storyboard-inventory-list-targeting-parity`

Scenario: "PropertyListReference and CollectionListReference honored in package targeting on create_media_buy"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-002-create-media-buy.feature:2699`

---

## 1. VERDICT

**GRADED.** The `@storyboard-v3.1` tag is justified and the scenario is on our conformance path.

Three separate gate checks, all pass:

- **Tier.** The storyboard lives at `protocols/media-buy/` — the `media_buy` protocol, which we declare
  (`src/core/tools/capabilities.py:100` → `supported_protocols=[SupportedProtocol.media_buy]`). Not a
  specialism-tier storyboard.
- **`requires_capability:` is ABSENT** from `inventory_list_targeting.yaml`. That is the only real
  storyboard-level applicability gate at 3.1.1 (`universal/storyboard-schema.yaml:259-280`: "storyboard-level
  applicability gate evaluated against the agent's `get_adcp_capabilities` response before executing
  phases... the runner skips the storyboard with `skip_result.reason: not_applicable`"). No gate declared →
  the runner executes it against us.
- **`agent.capabilities` is NOT a gate.** The storyboard declares
  `capabilities: [sells_media, supports_property_list_targeting, supports_collection_list_targeting]`
  (lines 30-33), which looks like a gate but is explicitly not one.
  `universal/storyboard-schema.yaml:365` states verbatim:

  > `#   capabilities: string[] (legacy descriptive capability labels; bundle selection is driven by get_adcp_capabilities.supported_protocols and specialisms)`

**On the specialism directories** (the brief flagged these): `specialisms/property-lists/index.yaml` and
`specialisms/collection-lists/index.yaml` both exist at 3.1.1, but neither gates this scenario. They are
`interaction_model: governance_agent` storyboards covering the **list-hosting CRUD lifecycle**
(`required_tools: [create_property_list]`, "You run a governance agent that manages property lists for brand
safety"). Our scenario is the **buyer→seller consumption** side: `interaction_model: media_buy_seller`,
`required_tools: [get_products, create_media_buy, update_media_buy]`. Different agent role, different tier.
We are not required to declare the `property_lists` / `collection_lists` specialisms to be graded on
honouring a list *reference* in package targeting.

**Caveat that does not change the verdict:** this scenario is currently **DORMANT** — it never executes.
See §4.

---

## 2. Real binding at 3.1.1

### What the footer wrongly points at

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/measurement_terms_rejected.yaml
```

Both defects confirmed:
- **Stale ref.** `v3.1-04f59d2d5` is an ancestor of beta.3, older than our own 3.1.1 pin.
- **Off-by-one path.** It cites `measurement_terms_rejected.yaml`, which is the *next* scenario's storyboard.
  The scenario's own prose names the truth: `# inventory_list_targeting: list-based targeting honored on create`.

### The real file

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_targeting.yaml`

Canonical source path at the tag (`git ls-tree -r --name-only v3.1.1 -- static/compliance/source/`):
`static/compliance/source/protocols/media-buy/scenarios/inventory_list_targeting.yaml`.

> **Note on `domains/` vs `protocols/`.** `dist/compliance/3.1.1/domains/media-buy/scenarios/inventory_list_targeting.yaml`
> exists and is **byte-identical** (`index.json` lists `domains` and `protocols` as parallel tiers with the
> same six ids and the same titles). Only `protocols/` exists in the v3.1.1 *source* tree — `domains/` is a
> generated alias in `dist/`. Cite `protocols/`.

Storyboard header (lines 1-10):
```yaml
id: media_buy_seller/inventory_list_targeting
version: "1.0.0"
title: "Seller honors property_list and collection_list targeting on create and update"
category: media_buy_seller
summary: "Verifies that a seller accepts PropertyListReference and CollectionListReference in package targeting on create_media_buy AND update_media_buy, with parity between both paths."
track: media_buy
required_tools:
  - get_products
  - create_media_buy
  - update_media_buy
```

### The graded `validations:` — verbatim

Two phases are in UC-002's scope. Everything else in this storyboard (`update_swap_lists`) is UC-003 territory.

**Phase `create_with_both_lists` → step `create_buy_with_lists`** (lines 92-152). Sample request carries
BOTH refs on the SAME package (lines 129-135), then:

```yaml
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json schema"
          - check: field_present
            path: "media_buy_id"
            description: "Seller assigns a media_buy_id"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
```

**This is the whole graded set on create.** Note what is *not* here: there is **no** graded check that the
create response echoes `packages[].targeting_overlay`. The `expected:` prose at lines 108-112 ("the package
retains both the property_list and collection_list targeting fields") is **narrative, not graded**.

**Phase `verify_create_persisted` → step `get_after_create`** (lines 154-195) — this is where persistence is
actually graded:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-media-buys-response.json schema"
          - check: field_value
            path: "media_buys[0].packages[0].targeting_overlay.property_list.list_id"
            value: "acme_outdoor_allowlist_v1"
            description: "property_list.list_id persisted after create"
          - check: field_value
            path: "media_buys[0].packages[0].targeting_overlay.collection_list.list_id"
            value: "acme_outdoor_collections_v1"
            description: "collection_list.list_id persisted after create"
```

Also relevant, and NOT ours: phase `update_swap_lists` (lines 197-293) grades `affected_packages` presence
and a `field_contains` on the full post-update package state, then re-reads via `get_media_buys` for
`acme_outdoor_no_match_v1` / `acme_outdoor_no_match_collections_v1`. That is the "parity" half of the
storyboard title and belongs on UC-003, not here. The existing UC-002 scenario title says "parity" but the
Gherkin never touches `update_media_buy` — the tag name over-claims.

### Corrected footer

```
# @source repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/media-buy/scenarios/inventory_list_targeting.yaml phases=create_with_both_lists,verify_create_persisted
```

---

## 3. Schema constraints at 3.1.1

Read via `git show v3.1.1:static/schemas/source/<path>` in `/Users/konst/projects/adcp`.

### `core/property-list-ref.json` and `core/collection-list-ref.json`

Both are structurally identical:

```json
  "required": ["agent_url", "list_id"],
  "additionalProperties": false
```
```json
    "agent_url": { "type": "string", "format": "uri", "description": "URL of the agent managing the property list" },
    "list_id":   { "type": "string", "minLength": 1, "x-entity": "property_list" },
    "auth_token":{ "type": "string", "description": "JWT or other authorization token for accessing the list. Optional if the list is public or caller has implicit access." }
```

So `agent_url` + `list_id` are both REQUIRED, `list_id` has `minLength: 1`, `auth_token` is optional, and
`additionalProperties: false`.

### `core/targeting.json` — the three list fields

```json
    "property_list": {
      "$ref": "/schemas/core/property-list-ref.json",
      "description": "Reference to a property list for targeting specific properties within this product. The package runs on the intersection of the product's publisher_properties and this list. Sellers SHOULD return a validation error if the product has property_targeting_allowed: false."
    },
    "collection_list": {
      "$ref": "/schemas/core/collection-list-ref.json",
      "description": "Reference to a collection list for including specific collections (programs, shows) within this product. The package runs on the intersection of matched collections and this list. Use for inclusion-based collection targeting. Seller must declare support in get_adcp_capabilities."
    },
    "collection_list_exclude": {
      "$ref": "/schemas/core/collection-list-ref.json",
      "description": "Reference to a collection list for excluding specific collections (programs, shows) from this product. Matched collections must not carry the buyer's ads. Use for brand safety do-not-air lists. Seller must declare support in get_adcp_capabilities."
    }
```

Two different gating mechanisms, and this asymmetry is spec-defined:
- `property_list` → per-**product** flag `property_targeting_allowed` (SHOULD reject when false).
- `collection_list` / `collection_list_exclude` → **capability** declaration only ("Seller must declare
  support in get_adcp_capabilities"). No per-product flag exists.

### `core/package.json`

`"required": ["package_id"]`; `targeting_overlay` is `{"$ref": "/schemas/core/targeting.json"}` with no
further constraint. So echoing the overlay on the response package is schema-legal but not schema-required.

### `media-buy/create-media-buy-response.json` — the load-bearing constraint

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
  "oneOf": [ CreateMediaBuySuccess, CreateMediaBuyError, CreateMediaBuySubmitted ]
```

`CreateMediaBuySuccess`:
```json
      "required": ["media_buy_id", "confirmed_at", "revision", "packages"],
      "additionalProperties": true,
      "not": { "required": ["errors"] }
```

**`CreateMediaBuySuccess` forbids an `errors` key outright.** Only `CreateMediaBuySubmitted` may carry
advisories: `"errors": { "description": "Optional advisory errors accompanying the submitted envelope. Use
only for non-blocking warnings..." }`. This is the biggest conflict — see §4.

`core/protocol-envelope.json` is `allOf`-merged into every branch and requires top-level `status` (the
known gap from the brief; we emit none).

---

## 4. Conflicts

### 4.1 SCHEMA OVERRIDES OUR GROUNDING: advisory `errors` on a successful create is schema-invalid at 3.1.1

Production emits an `UNSUPPORTED_FEATURE` advisory on the **success** envelope whenever a package carries
`property_list`:

- `src/core/tools/media_buy_create.py:4102` — `errors=property_list_unsupported_advisories(req.packages, adapter)`
  passed to `CreateMediaBuySuccess.sync_success(...)`. Same call at `:1841` and `:3561`; update path at
  `src/core/tools/media_buy_update.py:566,591,743,1398`.
- The rationale comment at `src/services/targeting_capabilities.py:174-180` cites **AdCP 3.0.0
  `error-handling.mdx`** prose: *"non-fatal errors as 'populate only the payload... MUST NOT populate
  `adcp_error`' — i.e. advisories ride on the success envelope."*

At 3.1.1 that is no longer true for this response. `CreateMediaBuySuccess` carries
`"not": {"required": ["errors"]}`, so a response with `media_buy_id` + `packages` + `errors` matches **zero**
`oneOf` branches → the storyboard's `- check: response_schema` on `create_buy_with_lists` **fails**.

Per the brief's authority order, **the 3.1.1 schema wins over the 3.0.0 prose the code cites.** Filed in §7.
The advisory is only emitted when `property_list` is present, so this fires on exactly the request this
storyboard sends.

### 4.2 The scenario is DORMANT — every current assertion is vacuous

`tests/bdd/conftest.py:3272-3282`: the UC-002 harness router matches on markers. This scenario's tags
(`@T-UC-002-storyboard-inventory-list-targeting-parity @storyboard-v3.1 @v3-1 @inventory-list
@property-list @collection-list`) match **no** branch, so it lands on the catch-all:

```python
        else:
            pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")
```

Belt and braces: none of its five step phrasings exist anywhere in `tests/bdd/steps/` (grep for
`property_list|collection_list` across `tests/bdd/steps/` returns **zero** hits), and
`tests/bdd/conftest.py:83-95` auto-xfails `StepDefinitionNotFoundError`. So the scenario xfails twice over
and has never graded anything. Making it real requires adding its tag to a wired branch — a **test-side**
change, no production change.

### 4.3 What the current Gherkin gets wrong

- `Then the response should carry the media_buy_id` — no such step; and phrased as bare existence, which
  `test_architecture_bdd_no_trivial_assertions.py` rejects.
- `And the persisted package targeting should reflect the property_list and collection_list references` —
  "should reflect" compares nothing. No values, no field paths. This is the exact shape the trivial-assertion
  guard exists to stop.
- Neither Given sets `property_targeting_allowed`, so if the scenario were wired as written it would go
  **red**: `src/core/database/models.py:296` defaults `property_targeting_allowed` to **False**, and
  `src/core/tools/media_buy_create.py:2330-2341` raises `AdCPValidationError` via
  `raise_if_property_targeting_violations` for any package sending `property_list` against such a product.
- The title and tag say "parity", but the Gherkin never calls `update_media_buy`. The parity half of the
  storyboard (`update_swap_lists`) is unbound anywhere in the repo.
- Scenario claims to test `PropertyListReference`/`CollectionListReference` but never names the concrete
  `list_id` / `agent_url` values the storyboard grades on.

### 4.4 What production actually does (all verified by reading `src/`)

| Step | Behaviour | Evidence |
|---|---|---|
| Request boundary | `property_list` / `collection_list` are declared fields on our `Targeting` (inherited from library `TargetingOverlay`), so they do NOT land in `model_extra` and `validate_unknown_targeting_fields` raises nothing | `src/core/schemas/_base.py:1167`; `src/services/targeting_capabilities.py:193-196` |
| `property_list` gate | rejected iff `product.property_targeting_allowed` is false | `media_buy_create.py:2330-2341` |
| `collection_list` gate | **nothing validates it at all** — no capability check, no product flag, no rejection | grep for `collection_list` in `src/` returns only `_base.py` type wiring + comments |
| Persistence | whole `Targeting` object stored on the package JSON blob | `media_buy_create.py:2967` → `package_config["targeting_overlay"] = req_pkg.targeting_overlay`; column `MediaPackage.package_config: Mapped[dict] = mapped_column(JSONType, ...)` at `src/core/database/models.py:1126` |
| Create response echo | overlay echoed verbatim on the response package | `media_buy_create.py:4081` → `Package(..., targeting_overlay=package.targeting_overlay, ...)` |
| `get_media_buys` readback | rehydrated from the blob | `src/core/tools/media_buy_list.py:223` `targeting_raw = pkg_config.get("targeting_overlay") or pkg_config.get("targeting")` → `:229` `Targeting(**targeting_raw)` → `:267` |
| Advisory | always emitted for `property_list`, because **no adapter** sets the ClassVar (`grep supports_property_list_filtering src/adapters/` → empty), so `supports_property_list_filtering()` is universally False | `targeting_capabilities.py:199-213`, `:151-172` |

Schema-layer round-trip executed against the installed SDK (adcp 6.6) — both refs survive
`Targeting(...) → model_dump(mode="json", exclude_none=True) → Targeting(**d)` intact, `model_extra` is
`None`, and `agent_url` normalizes through `pydantic.AnyUrl` to a **trailing slash**:

```
rt pl: acme_outdoor_allowlist_v1 https://governance.pinnacle-agency.example/
rt cl: acme_outdoor_collections_v1 https://governance.pinnacle-agency.example/
```

The Examples table below asserts the trailing-slash form because that is what production emits.

---

## 5. Proposed Gherkin

Replaces `BR-UC-002-create-media-buy.feature:2698-2712` (tag line through footer).

GREEN ONLY: every Then below asserts behaviour I verified in `src/`. The `UNSUPPORTED_FEATURE` row pins a
**known spec divergence** (§4.1) rather than the spec-correct outcome — that is deliberate, so the divergence
is visible and the scenario turns red the day ticket §7.1 lands. Flagged again in §8.

```gherkin
  @T-UC-002-storyboard-inventory-list-targeting @storyboard-v3.1 @v3-1 @inventory-list @property-list @collection-list
  Scenario Outline: PropertyListReference and CollectionListReference survive create_media_buy verbatim
    Given a valid create_media_buy request
    And the product allows property_list targeting
    And package 1 targeting_overlay references property_list "acme_outdoor_allowlist_v1" and collection_list "acme_outdoor_collections_v1" hosted at "https://governance.pinnacle-agency.example"
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And the response package 1 targeting_overlay field "<path>" should equal "<value>"
    And the persisted package 1 targeting_overlay field "<path>" should equal "<value>"

    # agent_url values carry a trailing slash: PropertyListReference.agent_url and
    # CollectionListReference.agent_url are pydantic AnyUrl (adcp 6.6), which normalizes
    # an authority-only URL to "https://host/". The storyboard sample_request sends the
    # un-slashed form; both round-trip to the normalized form on our wire.
    Examples: both list references round-trip through create and persistence
      | path                       | value                                       |
      | property_list.list_id      | acme_outdoor_allowlist_v1                   |
      | property_list.agent_url    | https://governance.pinnacle-agency.example/ |
      | collection_list.list_id    | acme_outdoor_collections_v1                 |
      | collection_list.agent_url  | https://governance.pinnacle-agency.example/ |

  @T-UC-002-storyboard-inventory-list-targeting-advisory @schema-v3.1 @v3-1 @inventory-list @property-list
  Scenario: property_list is persisted but flagged UNSUPPORTED_FEATURE while no adapter compiles it
    Given a valid create_media_buy request
    And the product allows property_list targeting
    And package 1 targeting_overlay references property_list "acme_outdoor_allowlist_v1" and collection_list "acme_outdoor_collections_v1" hosted at "https://governance.pinnacle-agency.example"
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And the response errors array should include error code "UNSUPPORTED_FEATURE"
    And the response error for code "UNSUPPORTED_FEATURE" should have field "packages[0].targeting_overlay.property_list"
    # DIVERGENCE, tagged @schema-v3.1 not @storyboard-v3.1 on purpose: 3.1.1
    # create-media-buy-response.json > CreateMediaBuySuccess carries
    # `"not": {"required": ["errors"]}`, so a success envelope with an errors array
    # matches zero oneOf branches and fails the storyboard's `check: response_schema`.
    # The advisory-on-success pattern was grounded in AdCP 3.0.0 error-handling.mdx
    # (src/services/targeting_capabilities.py:174-180), which 3.1.1 supersedes for this
    # response. This scenario pins CURRENT production so the gap is visible; retire it
    # when the advisory moves off the success branch. See GH ticket in §7.1.

  # inventory_list_targeting storyboard, phases create_with_both_lists +
  # verify_create_persisted: the seller MUST accept PropertyListReference and
  # CollectionListReference (agent_url + list_id) in package targeting_overlay on
  # create_media_buy, and the list_id values MUST be readable back off the persisted
  # package -- not merely echoed. The storyboard's third phase (update_swap_lists)
  # grades create/update parity through update_media_buy and belongs on UC-003; it is
  # unbound in this repo today.
  # @source repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/media-buy/scenarios/inventory_list_targeting.yaml phases=create_with_both_lists,verify_create_persisted
```

**Tag changes.** The opaque identifier tag is referenced from `docs/test-obligations/bdd-traceability.yaml`
and I have dropped the `-parity` suffix because the Gherkin does not test parity. **If that file pins the
literal string `T-UC-002-storyboard-inventory-list-targeting-parity`, keep the old tag verbatim and ignore
this rename** — the traceability binding matters more than the name. The second scenario's tag is new either
way and needs a traceability entry.

---

## 6. Step inventory

### Existing — reuse as-is

| Step | Defined at | Registered? |
|---|---|---|
| `Given a valid create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:104` | yes (`conftest.py:58`) |
| `When the Buyer Agent sends the create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:713` | yes |
| `Then the response should succeed` | `tests/bdd/steps/domain/uc002_create_media_buy.py:1692` | yes |

### New — 4 step definitions

All belong in `tests/bdd/steps/domain/uc002_create_media_buy.py` (already a registered plugin).

1. `Given the product allows property_list targeting`
   Sets `ctx["default_product"].property_targeting_allowed = True` and calls `ctx["env"]._commit_factory_data()`.
   Same mutate-then-commit shape as `_seed_auto_approval` at `uc002_create_media_buy.py:747-770`.
   Required — the ORM default is `False` (`src/core/database/models.py:296`) and without it the create is rejected.

2. `Given package 1 targeting_overlay references property_list "{pl_id}" and collection_list "{cl_id}" hosted at "{agent_url}"`
   Writes `ctx["request_kwargs"]["packages"][0]["targeting_overlay"] = {"property_list": {...}, "collection_list": {...}}`
   after `_ensure_request_defaults(ctx)` (`tests/bdd/steps/generic/given_media_buy.py:62`).
   One step sets both refs, matching the storyboard's single `sample_request`.

3. `Then the response package 1 targeting_overlay field "{path}" should equal "{value}"`
   Walks the dotted path on `ctx["response"].packages[0].targeting_overlay`, `str()`-normalizes (AnyUrl),
   compares to `value`. Transport-independent — asserts the parsed response object, which every transport
   produces.

4. `Then the persisted package 1 targeting_overlay field "{path}" should equal "{value}"`
   Reads `MediaPackage.package_config["targeting_overlay"]` for the response's `media_buy_id` inside
   `_db_session(ctx)`, walks the same dotted path. Copy the DB-assertion shape from
   `then_package_budget_persisted` (`tests/bdd/steps/generic/then_media_buy.py:398-425`).
   **Extract the dotted-path walker into one helper shared by steps 3 and 4** — the two bodies are otherwise
   the same logic with a different source object, which is exactly what the DRY invariant and
   `test_architecture_bdd_no_duplicate_steps.py` are there to stop.

5. `Then the response errors array should include error code "{code}"` — this phrasing **already exists** at
   `tests/bdd/steps/domain/uc019_query_media_buys.py:1736`, but `uc019_query_media_buys` is **not** in
   `conftest.py`'s `pytest_plugins` list, so it is not visible. Either add the module to `pytest_plugins`
   (it may collide with other registrations — check first) or lift the assertion into a shared helper both
   modules call. Do **not** paste a second copy.

6. `Then the response error for code "{code}" should have field "{field}"` — new; asserts the `field` on the
   matching `Error` entry. Production sets `field=f"packages[{index}].targeting_overlay.property_list"`
   (`src/services/targeting_capabilities.py:163`).

### Harness wiring — required, test-side only

`tests/bdd/conftest.py` UC-002 router: add the two tags to a `MediaBuyCreateEnv` branch (the same env used by
the `T-UC-002-ext-*` branch at `conftest.py:3238-3247`, which sets `ctx["dispatch_mode"] = "create"`).
Without this the scenarios stay on the `pytest.xfail("UC-002 harness not yet wired...")` catch-all at
`conftest.py:3282` and grade nothing.

---

## 7. TICKET MATERIAL

**7.1 — `create_media_buy` success envelope carries `errors`, which 3.1.1 forbids (schema-invalid response).**
`src/core/tools/media_buy_create.py:1841,3561,4102` pass `errors=property_list_unsupported_advisories(...)`
into `CreateMediaBuySuccess.sync_success(...)`; same pattern on update at
`src/core/tools/media_buy_update.py:566,591,743,1398`. AdCP 3.1.1
`static/schemas/source/media-buy/create-media-buy-response.json` > `oneOf` > `CreateMediaBuySuccess` declares
`"not": {"required": ["errors"]}`, and only the `CreateMediaBuySubmitted` branch permits `errors` ("Optional
advisory errors accompanying the submitted envelope"). A success response carrying `media_buy_id` + `packages`
+ `errors` therefore matches zero branches and fails `- check: response_schema` on
`protocols/media-buy/scenarios/inventory_list_targeting.yaml` step `create_buy_with_lists`. The code's
rationale comment (`src/services/targeting_capabilities.py:174-180`) cites AdCP **3.0.0**
`error-handling.mdx`; 3.1.1 supersedes it for this response shape. Fix: carry the advisory somewhere the
success branch permits, or drop it. Same defect on `update-media-buy-response.json`.

**7.2 — `collection_list` and `collection_list_exclude` are accepted with zero validation and zero capability
declaration.** `core/targeting.json` at 3.1.1 says for both fields: *"Seller must declare support in
get_adcp_capabilities."* `src/core/tools/capabilities.py:161-186` builds `MediaBuyFeatures` with
`inline_creative_management`, `property_list_filtering`, `catalog_management` — nothing for collection lists.
Grep for `collection_list` across `src/` returns only type wiring in `src/core/schemas/_base.py:104-112,1167`
and the explanatory comment at `src/services/targeting_capabilities.py:221-227`; no validator, no rejection,
no advisory. So we silently accept and persist a collection-list reference that no adapter will ever compile,
with no wire signal to the buyer — the exact silent-drop window that `property_list` got an advisory for. Fix:
declare collection-list support (as False) in `get_adcp_capabilities`, and mirror the property_list advisory
path (or hard-reject) for `collection_list` / `collection_list_exclude`.

**7.3 — the create/update parity half of `inventory_list_targeting.yaml` is unbound.** Storyboard phase
`update_swap_lists` (lines 197-293) grades `field_present: affected_packages` and a `field_contains` on
`affected_packages[*]` carrying complete post-update targeting, then re-reads via `get_media_buys` for
`acme_outdoor_no_match_v1` / `acme_outdoor_no_match_collections_v1`. The storyboard narrative names the exact
regression it exists to catch: *"a seller accepts list references on create_media_buy but silently drops them
on update_media_buy, so a buyer who edits a live buy loses their list targeting."* No UC-003 scenario covers
it. `tests/harness/media_buy_dual.py` (`MediaBuyDualEnv`) already provides create+update dispatch, so this is
wirable. File against UC-003.

**7.4 — no BDD env can execute the storyboard's `verify_create_persisted` phase on the wire.** The storyboard
grades persistence through `get_media_buys` (`media_buys[0].packages[0].targeting_overlay.property_list.list_id`).
`MediaBuyCreateEnv` (`tests/harness/media_buy_create.py`) dispatches only `create_media_buy`;
`MediaBuyDualEnv` adds only `update_media_buy`. Neither can call `get_media_buys`, so my proposed step 4
asserts the DB row (`MediaPackage.package_config`) instead of the wire readback. The production readback path
is real and correct (`src/core/tools/media_buy_list.py:223-267`), but it is not exercised by any
create→read scenario. Fix: a create+read env, or move the readback assertion into a UC-019 scenario seeded
by a real create.

**7.5 — `check: field_present path: "context"` on create is graded and untested.** The storyboard grades that
create_media_buy echoes the request `context` object; `create-media-buy-response.json` says sellers *"MUST
echo this object verbatim when the originating request carried context, including synchronous success, error,
submitted, and webhook task-status payloads."* Production does pass it through
(`src/core/tools/media_buy_create.py:4100` `context=req.context`; REST at `src/routes/api_v1.py:322,332`),
but no BDD Given sets a request `context` and no Then asserts the echo, so the guarantee is unverified across
transports. I did not include it in the Gherkin above because it needs a new Given and I could not verify the
echo survives all four transports without running them.

**7.6 — the `-parity` tag name over-claims.** `@T-UC-002-storyboard-inventory-list-targeting-parity` promises
create/update parity; the Gherkin only ever calls `create_media_buy`. Either rename the tag (and its entry in
`docs/test-obligations/bdd-traceability.yaml`) or land 7.3 so the name becomes true.

---

## 8. Risks

- **Nothing here was executed.** No BDD run, no `pytest`. Every green/red claim is from reading `src/` plus
  one schema-layer `Targeting` round-trip in a bare Python process. The scenario is currently double-xfailed
  (catch-all router + missing steps), so there is no baseline run to compare against.
- **Deliberately pinning a spec violation.** The second scenario asserts the `UNSUPPORTED_FEATURE` advisory,
  which §4.1 shows is schema-invalid at 3.1.1. I chose visible-and-green over silent; it is tagged
  `@schema-v3.1` (not `@storyboard-v3.1`) and carries an inline retirement note. If the team would rather not
  encode a known violation in a feature file, drop that scenario entirely and keep only ticket §7.1 — the
  first Scenario Outline stands on its own.
- ~~**Advisory emission depends on the adapter being a mock.**~~ RESOLVED by execution.
  `supports_property_list_filtering()` reads `getattr(adapter.__class__, "supports_property_list_filtering", False)`.
  In `MediaBuyCreateEnv` the adapter is a `MagicMock` instance; I ran
  `getattr(MagicMock().__class__, "supports_property_list_filtering", False)` → `False` (auto-attribute
  creation is instance-level, not class-level). The advisory IS emitted under the harness.
- **Harness router edit is a prerequisite.** Without adding the tags to a `MediaBuyCreateEnv` branch in
  `tests/bdd/conftest.py`, the proposed Gherkin xfails exactly like the current one and grades nothing. That
  edit is test-side, but it is outside the feature file and someone has to make it.
- **Traceability tag rename.** I have not read `docs/test-obligations/bdd-traceability.yaml`. If it pins the
  literal `-parity` tag string, keep the old tag and ignore my rename.
- **`Given a valid create_media_buy request` package shape.** I read `_ensure_request_defaults`
  (`given_media_buy.py:62-85`) and it seeds `packages[0]` as a plain dict, so writing a `targeting_overlay`
  key into it should flow through `CreateMediaBuyRequest(**kwargs)` in `_dispatch_full_create`
  (`uc002_create_media_buy.py:759-780`). I did not execute that path.
- **Trailing-slash values.** Asserted from an SDK round-trip in isolation, not through the four transports.
  REST returns `response.model_dump(mode="json")` (`api_v1.py:338`) so the JSON form should match, but MCP/A2A
  reconstruction was not checked.
- **`domains/` vs `protocols/` citation.** Both dist copies are byte-identical and both tiers appear in
  `index.json`. I cite `protocols/` because that is the only path in the v3.1.1 *source* tree. If the sweep
  standardizes on `domains/`, the two are interchangeable for this scenario.

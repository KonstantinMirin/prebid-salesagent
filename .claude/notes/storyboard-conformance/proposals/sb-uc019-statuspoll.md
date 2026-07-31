# Re-grounding `@T-UC-019-storyboard-post-create-status-poll` against AdCP 3.1.1

Scenario: `tests/bdd/features/BR-UC-019-query-media-buys.feature:1234-1247`
Repo under audit: `/Users/konst/projects/salesagent-sbsweep` (read-only; nothing edited)

---

## 1. VERDICT

**GRADED** — and the scenario's own prose named the right storyboard all along; it just never
carried an `@source` footer.

The behaviour is graded at 3.1.1 by the `media_buy_seller` storyboard, phase `create_buy`,
step `check_buy_status`, which carries a real `validations:` block with six `- check:` entries
(quoted verbatim in §2). The storyboard's `track:` is `media_buy`, which
`src/core/tools/capabilities.py` declares under `supported_protocols`, so this is on our
conformance path. `@storyboard-v3.1` stays; it must NOT become `@schema-v3.1`.

Two further qualifications, both material:

- **The scenario is currently DORMANT.** None of its three step texts exist anywhere under
  `tests/bdd/steps/` (verified by full-tree grep of the exact strings). `tests/bdd/conftest.py:99-101`
  converts `StepDefinitionNotFoundError` into `xfail`, so today this scenario grades **nothing**
  while reporting green. Whatever we do here, we are converting a vacuous xfail into either a real
  test or an honest one.
- **Only 3 of the 6 graded checks can land green.** The other 3 are real production gaps
  (§4, §7). In particular the storyboard's signature check — `media_buys[0].media_buy_id`
  equalling the id `create_media_buy` returned — cannot be exercised as a genuine create→read
  chain in this harness at all (§4.3).

---

## 2. Real binding at 3.1.1

### What the current footer points at

**Nothing.** There is no `@source` footer. Lines 1243-1247 are a free-text comment block that
names `media-buy/index.yaml create_buy / check_buy_status` in prose. That prose is **correct** —
this scenario is one of the 11 with no footer, not one of the 16 with the off-by-one path defect.
It needs a footer added, not corrected.

### The real file + line

`/Users/konst/projects/adcp/dist/compliance/3.1.1/domains/media-buy/index.yaml`
- phase `create_buy` — line 416
- step `create_media_buy` — line 435 (issues the `media_buy_id` into storyboard context, line 512-514)
- step **`check_buy_status`** — line 526
- graded `validations:` — **lines 565-585**

`protocols/media-buy/index.yaml` is **byte-identical** to `domains/media-buy/index.yaml`
(`diff` returns empty). Both tiers carry the same step at the same line numbers. Cite the
`protocols/` path in the footer: that is the tier keyed to our declared `supported_protocols`.

### The graded `validations:` block, verbatim (lines 565-585)

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-media-buys-response.json schema"
          - check: field_present
            path: "media_buys[0].status"
            description: "Each media buy has a status"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "media_buy_seller--check_buy_status"
            description: "Context correlation_id returned unchanged"
          - check: field_equals_context
            path: "media_buys[0].media_buy_id"
            context_key: "media_buy_id"
            description: "get_media_buys returns the media_buy_id created earlier"
          - check: field_value
            path: "media_buys[0].context.correlation_id"
            value: "media_buy_seller--create_media_buy"
            description: "get_media_buys includes persisted media-buy context from create_media_buy"
```

The `$context.media_buy_id` referenced by `field_equals_context` is bound at the *preceding* step
(`create_media_buy`, line 512-514):

```yaml
        context_outputs:
          - name: media_buy_id
            path: 'media_buy_id'
```

and consumed by `check_buy_status`'s `sample_request` (line 561-562):

```yaml
          media_buy_ids:
            - "$context.media_buy_id"
```

That is the whole point of the step: **the id issued by create is the query key on the very next call.**

### Tier ownership

- Primary: **`protocols/media-buy/index.yaml`** (identical twin at `domains/media-buy/index.yaml`),
  `track: media_buy` → declared → **on our conformance path**.
- `universal/get-media-buys-pagination-integrity.yaml` also grades `get_media_buys`, but a
  *different* behaviour (`pagination` envelope shape, lines 145-160) and it is gated on
  `requires: [controller]` + `controller_seeding: true` — a comply-test-controller surface we do
  not ship in production. Not this scenario's binding; the pagination gap belongs to whoever owns
  that storyboard.
- `universal/read-tool-idempotency.yaml` **does not grade `get_media_buys` at all**. Its read
  probes are `get_adcp_capabilities`, `get_products`, `list_accounts`, `list_creative_formats`,
  `list_creatives` (steps at lines 62, 100, 146, 189, 231). The lead's note that it "may grade this
  tool" is not borne out by the 3.1.1 file — no `task: get_media_buys` appears in it.

### Non-graded prose worth knowing

The step's `expected:` block (lines 546-555) additionally names `packages`, `valid_actions`, and a
`message` when `pending_creatives`. **None of that is under `validations:`, so none of it is graded.**
Do not manufacture assertions from it.

---

## 3. Schema constraints at 3.1.1

Read via `git show v3.1.1:static/schemas/source/<path>` in `/Users/konst/projects/adcp`.

### `media-buy/get-media-buys-response.json`

Envelope composition:

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
```

Response-level required set:

```json
  "required": [
    "media_buys"
  ],
  "additionalProperties": true
```

Per-`media_buys[]`-item required set:

```json
        "required": [
          "media_buy_id",
          "status",
          "currency",
          "total_budget",
          "confirmed_at",
          "revision",
          "packages"
        ],
        "additionalProperties": true
```

Item-level `status` is the **media-buy lifecycle enum**, not the task envelope status:

```json
          "status": {
            "$ref": "/schemas/enums/media-buy-status.json"
          },
```

Item-level `context` — the field graded by the sixth check:

```json
          "context": {
            "$ref": "/schemas/core/context.json",
            "description": "Opaque media-buy-level correlation data echoed unchanged from the create_media_buy request. Sellers MUST include persisted context on read surfaces when the media buy was created through AdCP with context, so buyers can reconcile seller-assigned media_buy_id values with their own tracking state. Sellers MAY omit context for media buys created outside AdCP or created without context. Sellers MUST NOT parse this object for business logic."
          },
```

Note the escape hatch: *"Sellers MAY omit context for media buys created outside AdCP or created
without context."* A buy seeded by a factory was not created through AdCP with context, so omission
is schema-legal for a seeded buy — but the storyboard's chain creates through AdCP *with* context,
so in the graded flow the MUST applies.

`confirmed_at` is required-but-nullable, and is coupled to `status` by a conditional guard:

```json
        "allOf": [
          {
            "$comment": "When get_media_buys gains canonical media_buy_status during the 3.1 -> 3.2 status migration, extend this provisional-buy guard to reject media_buy_status: active alongside legacy status: active.",
            "if": {
              "properties": { "confirmed_at": { "type": "null" } },
              "required": ["confirmed_at"]
            },
            "then": {
              "not": {
                "properties": { "status": { "const": "active" } },
                "required": ["status"]
              },
              ...
```

### `enums/media-buy-status.json`

```json
  "enum": [
    "pending_creatives",
    "pending_start",
    "active",
    "paused",
    "completed",
    "rejected",
    "canceled"
  ]
```

### `core/protocol-envelope.json`

```json
  "required": [
    "status"
  ],
  "additionalProperties": true,
  "not": {
    "anyOf": [
      { "required": ["task_status"] },
      { "required": ["response_status"] }
    ]
  }
```

with the description clause: *"The `status` field is REQUIRED on every task response envelope,
including synchronous metadata responses … Agents shipping responses without a top-level `status`
are non-conformant regardless of whether the task body schema would otherwise validate."*

### `core/pagination-response.json` (referenced by the response's optional `pagination`)

```json
  "required": [ "has_more" ],
  "additionalProperties": false
```

`pagination` is **optional** on `get-media-buys-response.json` (not in `required`), so its absence
is not a schema failure — it is a `universal/get-media-buys-pagination-integrity.yaml` failure,
which is a different storyboard.

---

## 4. Conflicts

### 4.1 Schema overrides the lead's brief on `media_buy_status` and `confirmed_at`

The lead's note — *"3.1.1's media-buy index expects `media_buy_status: active, pending_start, or
pending_creatives` with the deprecated top-level `status` allowed to mirror it; `confirmed_at` was
dropped from the expectation"* — describes the **`create_media_buy` step** (index.yaml lines 468-471),
not `check_buy_status`. It does not transfer:

- On `get_media_buys`, the item field is `status`, full stop. `media_buy_status` does not exist on
  `get-media-buys-response.json` at 3.1.1 — the schema's own `$comment` says so explicitly:
  *"When get_media_buys **gains** canonical media_buy_status during the 3.1 -> 3.2 status
  migration…"*. Asserting `media_buy_status` on a get_media_buys response would be asserting a 3.2
  field against a 3.1.1 pin.
- `confirmed_at` is **not** dropped for `get_media_buys` — it is in the item `required` array.
  It is dropped only from the create step's narrative `expected:` prose, which is ungraded anyway.

**Schema wins over both the lead's note and the storyboard prose.** Stated explicitly as the brief asks.

### 4.2 What the scenario currently gets wrong

| Current line | Problem |
|---|---|
| `Then the response should be schema-valid against get-media-buys-response.json` | Would be a lie even if wired. The sibling implementation of this exact phrasing (`tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-111`) runs **no validator** — it asserts `isinstance(formats, list)`. A UC-019 clone would assert `isinstance(media_buys, list)` and call it schema conformance. Worse, the real 3.1.1 schema **fails** against our output (§4.4), so an honest validator here would be red. |
| `And the media_buys array should include the freshly-created buy` | Truthiness/existence only — rejected by `test_architecture_bdd_no_trivial_assertions.py`. Also "freshly-created" is unverifiable: nothing in this scenario creates anything. |
| `And the included entry should expose the same media_buy_id and current status` | "the same … and current" compares against nothing. Two claims in one step, neither with a concrete expected value. |
| No `Scenario Outline` | Three distinct post-create statuses (`pending_creatives`, `pending_start`, `active`) are the whole substance of "observe its initial status", and the scenario collapses them into a single vague poll. |
| No `@source` footer | Binding unverifiable; that is what put it in bucket **C**. |
| Zero of the 6 graded checks appear | `context` echo (checks 3 and 4) — the cheapest green win available — is entirely absent from the Gherkin. |

### 4.3 The graded check we cannot honestly exercise

`field_equals_context media_buys[0].media_buy_id == $context.media_buy_id` requires calling
`create_media_buy`, capturing the returned id, and then calling `get_media_buys` with it — one
scenario, two tools.

`tests/bdd/conftest.py:3502-3527` hands **every** UC-019 scenario `MediaBuyListEnv` unconditionally.
`tests/harness/media_buy_list.py` exposes only `get_media_buys` (`call_impl` → `_get_media_buys_impl`,
`call_a2a` → `_run_a2a_handler("get_media_buys", …)`, `call_mcp` → the create-path). There is no
create+list composite env. `MediaBuyDualEnv` (`tests/harness/media_buy_dual.py`) is create+**update**,
not create+list.

So the proposal below seeds the buy through the existing factory Given and asserts the id round-trips
**verbatim through the by-ID query**. That is the honest subset: it proves the seller resolves a
known `media_buy_id` and returns it unchanged, which is the load-bearing half of the check. It does
**not** prove the id came from `create_media_buy`. The comment in the proposed Gherkin says so, and
the composite-env work is filed in §7.

### 4.4 The two graded checks that are red against production

- **`response_schema`.** `src/core/schemas/_base.py::GetMediaBuysMediaBuy` declares
  `media_buy_id, buyer_campaign_ref, status, valid_actions, currency, total_budget, packages,
  created_at, updated_at`. The 3.1.1 item `required` array demands `confirmed_at` and `revision`
  as well — **both absent**. Separately `GetMediaBuysResponse` has no top-level `status`, which
  `core/protocol-envelope.json` marks `required`. A real validator fails on three counts.
- **`media_buys[0].context.correlation_id`.** `src/core/tools/media_buy_list.py:270-283` builds
  `GetMediaBuysMediaBuy(...)` with no `context=` argument, and the model declares no `context`
  field. Per-buy context is neither persisted at create nor emitted at read.

Both go to §7 as tickets, not into the Gherkin.

### 4.5 One check is green but partly unobservable

Top-level `context` echo works: `media_buy_list.py:291-295` returns
`GetMediaBuysResponse(media_buys=…, context=req.context, errors=…)`, and both wire paths preserve
it — A2A via `_serialize_for_a2a`'s `model_dump(mode="json")` (`adcp_a2a_server.py:1390`, no
`exclude_none`), MCP via `ToolResult(structured_content=response)`. `ContextObject`
(`adcp.types`) is `extra="allow"` with no declared fields, so `correlation_id` rides as an extra and
survives the round trip.

Caveat: `MediaBuyListEnv.call_mcp` uses the **deprecated** `_run_mcp_wrapper`
(`tests/harness/_base.py:851-889`), which bypasses FastMCP middleware and TypeAdapter validation and
stashes no `wire_response`. So `ctx["wire_response"]` is `None` on MCP for every UC-019 scenario,
and Then steps must read `ctx["response"]` (the typed model) — which is exactly what all 80-odd
existing UC-019 Then steps already do. Filed in §7.

### 4.6 Transport reality

UC-019 parametrizes across **a2a + mcp only** — `conftest.py:2831` `_NO_REST_UC_TAG_PREFIXES =
("T-UC-019-",)`, because `src/routes/api_v1.py` has no `/media-buys/query` route (only
`POST /media-buys`, `PUT /media-buys/{id}`, `POST /media-buys/delivery`). `e2e_rest` is skipped for
the same reason. `MediaBuyListEnv.REST_ENDPOINT = "/api/v1/media-buys/query"` points at a route that
does not exist — dead config. The proposed Gherkin contains zero transport branching, so it is
correct on whatever set the harness parametrizes; the missing REST route is a §7 item, not a
Gherkin concern.

---

## 5. Proposed Gherkin

Replaces `tests/bdd/features/BR-UC-019-query-media-buys.feature:1234-1247` in full.

```gherkin
  # AdCP 3.1.1 media_buy_seller storyboard, phase create_buy, step check_buy_status:
  # the buyer polls get_media_buys with the media_buy_id create_media_buy just
  # issued and reads the buy's initial lifecycle status. Graded checks covered
  # here: media_buys[0].status (concrete value per row), media_buys[0].media_buy_id
  # round-trip, top-level context presence, context.correlation_id echoed unchanged.
  #
  # SCOPE LIMIT — the buy is seeded, not created through create_media_buy. UC-019 is
  # handed MediaBuyListEnv unconditionally (tests/bdd/conftest.py), and no create+list
  # composite harness exists, so the create leg of the storyboard chain cannot be
  # driven from this feature file today. What IS graded here is the load-bearing half:
  # a known media_buy_id resolves synchronously and round-trips verbatim. See the
  # composite-env issue for the full chain.
  #
  # NOT asserted here, deliberately (all three are open production gaps, see issues):
  #   - response_schema: GetMediaBuysMediaBuy omits confirmed_at and revision, both
  #     REQUIRED on get-media-buys-response.json items at 3.1.1; the response carries
  #     no top-level status, REQUIRED by core/protocol-envelope.json.
  #   - media_buys[0].context.correlation_id: per-buy context is neither persisted at
  #     create nor emitted at read.
  # Status vocabulary is enums/media-buy-status.json at 3.1.1. get_media_buys items
  # carry `status`, NOT `media_buy_status` — the latter arrives in 3.2 per the
  # get-media-buys-response.json $comment.
  @T-UC-019-storyboard-post-create-status-poll @storyboard-v3.1 @v3-1 @post-create-poll
  Scenario Outline: post-create status poll resolves the buy by media_buy_id and reports <expected_status>
    Given the principal "buyer-001" owns media buy "mb-poll" with status "<seeded_status>"
    When the Buyer Agent sends a get_media_buys request for media_buy_ids ["mb-poll"] with context correlation_id "media_buy_seller--check_buy_status"
    Then the response should include media buy "mb-poll" with status "<expected_status>"
    And no error should be present in the response
    And the response context correlation_id should equal "media_buy_seller--check_buy_status"

    Examples: initial statuses a synchronous create can hand back
      | seeded_status     | expected_status   |
      | pending_creatives | pending_creatives |
      | pending_start     | pending_start     |
      | active            | active            |

    # @source adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/media-buy/index.yaml
    #   phase=create_buy step=check_buy_status lines=526-585
    #   (byte-identical twin at dist/compliance/3.1.1/domains/media-buy/index.yaml)
```

### Why each row is green

`given_owns_media_buy_with_status` (`tests/bdd/steps/domain/uc019_query_media_buys.py:248-258`) →
`_seed_simple_media_buy` (line 229-247) → `MediaBuyFactory(status=<seeded>)` with the factory's
**default mid-flight** window. Then `_compute_status` → `resolve_canonical_status`
(`src/core/tools/_media_buy_status.py:121-160`) maps:

- `pending_creatives` → `pending_creatives`; canonical ≠ `CANONICAL_SERVING`, `should_refine` False → verbatim ✔
- `pending_start` → `pending_start`; same, verbatim ✔
- `active` → `active`; `should_refine` True, mid-flight window → stays `active` ✔

Deliberately **not** using the `with persisted status "…"` Given: that seeder
(`_seed_media_buy_with_persisted_status`, line 190-220) forces `_UC019_PERSISTED_SEED_WINDOW`
(pre-flight), which would date-refine `active` to `pending_start` and turn this scenario into a
date-refinement test — an obligation already owned by the `T-UC-019-inv-150-*` scenarios.

By-ID query path: `_fetch_target_media_buys` (`media_buy_list.py:397-410`) sets
`skip_default=True` when `media_buy_ids` is present, so no default active-only filter suppresses the
`pending_*` rows. Confirmed green by the already-graduated `T-UC-019-inv-150-5`.

---

## 6. Step inventory

### Existing — reuse verbatim, no changes

| Step text | Location |
|---|---|
| `Given the principal "{principal_id}" owns media buy "{mb_id}" with status "{status}"` | `tests/bdd/steps/domain/uc019_query_media_buys.py:248` |
| `Then the response should include media buy "{mb_id}" with status "{status}"` | `tests/bdd/steps/domain/uc019_query_media_buys.py:1317` — resolves the Gherkin label to the real id, asserts **exactly one** match, then asserts the status string equals the expected value. Covers graded checks 2 and (the tractable half of) 5 in one concrete comparison. |
| `Then no error should be present in the response` | `tests/bdd/steps/domain/uc019_query_media_buys.py:1541` |

### New — two steps

**1.** `When the Buyer Agent sends a get_media_buys request for media_buy_ids {ids} with context correlation_id "{correlation_id}"`

Extends the existing `when_query_for_ids` (line 1205-1214) with a context payload. Same
`_resolve_media_buy_ids` + `_dispatch_query` plumbing, one extra kwarg:

```python
@when(
    parsers.re(
        r'the Buyer Agent sends a get_media_buys request for media_buy_ids (?P<ids>\[.+\]) '
        r'with context correlation_id "(?P<correlation_id>[^"]+)"'
    )
)
def when_query_for_ids_with_context(ctx: dict, ids: str, correlation_id: str) -> None:
    """By-ID poll carrying the storyboard's context object.

    AdCP 3.1.1 protocols/media-buy/index.yaml check_buy_status grades
    context.correlation_id round-tripping unchanged, so the request must
    actually carry one.
    """
    import json

    real_ids = _resolve_media_buy_ids(ctx, json.loads(ids))
    ctx["sent_correlation_id"] = correlation_id
    _dispatch_query(ctx, media_buy_ids=real_ids, context={"correlation_id": correlation_id})
```

`parsers.re` rather than `parsers.parse` so the existing greedy
`… for media_buy_ids {ids}` binding cannot swallow the trailing clause into `ids` — the exact
shadowing bug the `with status` Given already documents at line 251-257.

**2.** `Then the response context correlation_id should equal "{correlation_id}"`

```python
@then(parsers.parse('the response context correlation_id should equal "{correlation_id}"'))
def then_context_correlation_id_echoed(ctx: dict, correlation_id: str) -> None:
    """Assert top-level context echoes the request's correlation_id unchanged.

    AdCP 3.1.1 check_buy_status validations:
      - field_present  path: "context"
      - field_value    path: "context.correlation_id"
    ContextObject is extra="allow" with no declared fields, so correlation_id
    rides as a model extra.
    """
    resp = ctx.get("response")
    assert resp is not None, f"Expected response, got error: {ctx.get('error')}"
    context_obj = getattr(resp, "context", None)
    assert context_obj is not None, "Response dropped the request context object entirely"
    actual = getattr(context_obj, "correlation_id", None)
    assert actual == correlation_id, f"Expected context.correlation_id {correlation_id!r}, got {actual!r}"
```

Both new steps belong in `tests/bdd/steps/domain/uc019_query_media_buys.py` (module-scoped import,
per `tests/bdd/test_uc019_query_media_buys.py:14`).

No conftest change needed: the tag is not in `_UC019_XFAIL_TAGS` (`conftest.py:2072-2121`) and not in
`_UC019_BOUNDARY_SELECTIVE`, so it runs unmarked on a2a + mcp once the steps exist.

No traceability change needed: `docs/test-obligations/bdd-traceability.yaml:11144` keys on
`T-UC-019-storyboard-post-create-status-poll`, which the proposal keeps unchanged.

---

## 7. TICKET MATERIAL

- **`get_media_buys` response items omit `confirmed_at`, REQUIRED at 3.1.1.**
  `src/core/schemas/_base.py::GetMediaBuysMediaBuy` declares no `confirmed_at`; the impl at
  `src/core/tools/media_buy_list.py:270-283` never sets one.
  `git show v3.1.1:static/schemas/source/media-buy/get-media-buys-response.json` lists
  `confirmed_at` in the `media_buys[].required` array (type `["string","null"]`). The schema further
  couples it: an item with `confirmed_at: null` MUST NOT carry `status: "active"` (the `allOf`
  provisional-buy guard), so emitting it is not cosmetic — it changes what `active` is allowed to
  mean. Graded by `protocols/media-buy/index.yaml:566-567` `check: response_schema`.

- **`get_media_buys` response items omit `revision`, REQUIRED at 3.1.1.**
  Same model, same impl block. `revision` is in the item `required` array
  (`"type": "integer", "minimum": 1`) and is the optimistic-concurrency token
  `update_media_buy` consumes — without it a buyer cannot construct a conflict-safe update from a
  read. Graded by the same `response_schema` check.

- **No top-level `status` on any AdCP response envelope.**
  `GetMediaBuysResponse` (`src/core/schemas/_base.py`) has `media_buys`, `errors`, `context` and
  nothing else. `git show v3.1.1:static/schemas/source/core/protocol-envelope.json` has
  `"required": ["status"]` and states agents shipping responses without it *"are non-conformant
  regardless of whether the task body schema would otherwise validate."*
  `get-media-buys-response.json` `$ref`s that envelope in its `allOf`. Already on the brief's
  known-gaps list; recording the get_media_buys instance for completeness.

- **Per-media-buy `context` is never persisted at create nor emitted at read.**
  `media_buy_list.py:270-283` constructs `GetMediaBuysMediaBuy(...)` with no `context=`, and the
  model declares no such field. `protocols/media-buy/index.yaml:583-585` grades
  `field_value path: "media_buys[0].context.correlation_id" value: "media_buy_seller--create_media_buy"`,
  and `get-media-buys-response.json` states *"Sellers MUST include persisted context on read surfaces
  when the media buy was created through AdCP with context, so buyers can reconcile seller-assigned
  media_buy_id values with their own tracking state."* Needs a create-side persist plus a read-side
  emit; the create-side half also blocks the storyboard's `package.context` sibling clause.

- **No create+list composite harness, so the create→poll chain cannot be graded.**
  `tests/bdd/conftest.py:3502-3527` binds every UC-019 scenario to `MediaBuyListEnv`, which exposes
  only `get_media_buys` (`tests/harness/media_buy_list.py`). `MediaBuyDualEnv`
  (`tests/harness/media_buy_dual.py:39`) is create+update. The storyboard's
  `check: field_equals_context path: "media_buys[0].media_buy_id" context_key: "media_buy_id"`
  (`protocols/media-buy/index.yaml:579-582`) explicitly consumes the `context_outputs` binding
  emitted by the preceding `create_media_buy` step (lines 512-514) — it is a two-tool chain by
  construction. Needs a `MediaBuyCreateListEnv` (create env + list dispatch) and a conftest branch
  keyed off the storyboard tag.

- **`then_response_schema_valid` validates nothing.**
  `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-111` — the step claiming "schema-valid
  against list-creative-formats-response.json" asserts only `isinstance(formats, list)`.
  `tests/helpers/pinned_schema.py::validate_against_pinned_schema` exists and is not called. Any
  scenario using this phrasing is reporting schema conformance it never checked. On the brief's
  known-gaps list; flagged again because the UC-019 scenario under audit was about to clone it.

- **`tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not 3.1.1.**
  Even once a validator is wired, it would validate against a pre-beta.3 ancestor of our own pin.
  On the brief's known-gaps list; blocking for the `response_schema` check above.

- **`MediaBuyListEnv.REST_ENDPOINT` points at a non-existent route.**
  `tests/harness/media_buy_list.py:26` declares `/api/v1/media-buys/query`; `src/routes/api_v1.py`
  registers only `POST /media-buys` (302), `PUT /media-buys/{media_buy_id}` (344),
  `POST /media-buys/delivery` (377). `conftest.py:2831` works around it by excluding UC-019 from
  `rest` and `e2e_rest`. Either add the route (`get_media_buys` is a required tool on the
  `media_buy` track — `protocols/media-buy/index.yaml:6-8`) or delete the dead constant. As-is,
  one third of our transports never exercise this tool.

- **`MediaBuyListEnv.call_mcp` uses the deprecated `_run_mcp_wrapper`.**
  `tests/harness/media_buy_list.py:56-60` → `tests/harness/_base.py:851-889`, whose own docstring
  says *"bypasses FastMCP middleware and TypeAdapter validation"* and which stashes no
  `wire_response`. Every UC-019 MCP assertion therefore runs against a typed model whose fields are
  already coerced, and `ctx["wire_response"]` is `None`. Migrate to `_run_mcp_client`.

- **`GetMediaBuysRequest` / `GetMediaBuysResponse` do not extend the `adcp` library types.**
  Both subclass `SalesAgentBaseModel` directly (`src/core/schemas/_base.py`) with docstrings citing
  *"the adcp 3.6.0 spec"* — a version string that matches neither the pinned SDK (`adcp==6.6.0`) nor
  the spec pin (3.1.1). CLAUDE.md Pattern #1 requires inheritance from the library types
  (`Library*` alias), which is also what would make the missing `confirmed_at` / `revision` /
  per-buy `context` fields arrive for free. Low priority relative to the field gaps, but the same
  root cause.

---

## 8. Risks

- **Not executed.** No test run — no DB was started and the brief scopes this to a proposal. Every
  green claim is from reading `src/` and the step definitions. The three status rows are the highest
  confidence (they reuse `given_owns_media_buy_with_status` + `then_response_includes_mb_with_status`,
  both already green in sibling UC-019 scenarios). The **context-echo assertion is the one to verify
  first** — it is the only claim resting on a step that does not exist yet.
- **Context echo on A2A is inferred, not observed.** The chain is
  `GetMediaBuysResponse(context=req.context)` → `_serialize_for_a2a` `model_dump(mode="json")`
  (`adcp_a2a_server.py:1390`) → artifact extraction → `GetMediaBuysResponse(**data)`. I confirmed no
  `exclude_none` on the dump and that `ContextObject` is `extra="allow"`, but I did not confirm that
  `normalize_request_params` on the inbound A2A side preserves a `context` key it has no declared
  slot for. If it strips it, the assertion is red on a2a and green on mcp — a transport split, which
  would make it a ticket rather than a Gherkin line.
- **Step-shadowing.** `when_query_for_ids` (line 1205) is registered with
  `parsers.parse('… for media_buy_ids {ids}')`, whose `{ids}` is greedy. I proposed `parsers.re` for
  the new When specifically to avoid the collision, but pytest-bdd registration order across the two
  bindings is worth confirming with a single-scenario run before trusting it — this file already
  carries one documented instance of exactly this bug (line 251-257).
- **The scope limit is a real reduction in grading.** Seeding instead of creating means the scenario
  proves "a known id round-trips", not "the id create issued round-trips". If the team would rather
  keep the scenario dormant than ship the weaker version, that is a defensible call — but the current
  state is a dormant scenario that reports green while asserting nothing, which is strictly worse
  than either option.
- **3.1.8 / HEAD drift, noted only.** 3.1.2 through 3.1.8 exist under
  `dist/compliance/`. I did not read them and they are not authority here. If a later cut moves
  `check_buy_status` or promotes `media_buy_status` onto `get-media-buys-response.json`, this footer
  needs revisiting at pin-bump time.
- **`valid_actions` left unasserted.** The step's `expected:` prose names it and production does emit
  it (`valid_actions_for_status(status.value)`, `media_buy_list.py:277`), so a per-status Examples
  column would be attractive. I left it out because (a) it is ungraded prose, not a `validations:`
  entry, and (b) the exact per-status output comes from the SDK's
  `adcp.server.helpers.valid_actions_for_status` and I could not verify the values without running.
  Worth a follow-up once someone can execute.

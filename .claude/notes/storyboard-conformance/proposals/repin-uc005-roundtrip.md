# Re-pin UC-005 `format-id-roundtrip` to AdCP 3.1.1

Target scenario: `tests/bdd/features/BR-UC-005-discover-creative-formats.feature:1060-1076`
Current footer pins `v3.1-04f59d2d5` @ `static/compliance/source/protocols/creative/index.yaml` — **both the version and the path are wrong**.

---

## 1. Storyboard checks at 3.1.1

### 1a. Where the phase actually lives

`list_formats_integrity` is **not** in `protocols/creative/index.yaml` at 3.1.1. It lives in the media-buy protocol:

- `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/index.yaml:352`
- mirrored byte-identically at `dist/compliance/3.1.1/domains/media-buy/index.yaml:352`

`protocols/creative/index.yaml` at 3.1.1 has no `list_formats_integrity`; its format phase is `discover_formats` → step `list_formats` (creative/index.yaml:79, 85), which is what the *sibling* baseline-shape scenario binds to.

The `product_format_id` the scenario roundtrips is captured one step earlier, in `get_products_brief`:

```yaml
# dist/compliance/3.1.1/protocols/media-buy/index.yaml:313-315
        context_outputs:
          - name: product_format_id
            path: 'products[0].format_ids[0]'
```

### 1b. `list_formats_integrity` — verbatim (media-buy/index.yaml:352-413)

```yaml
      - id: list_formats_integrity                                    # :352
        title: "Verify format_ids on products resolve to real formats"
        narrative: |
          The buyer asks the sales agent to filter `list_creative_formats` by
          `products[0].format_ids[0]`. The sales agent MUST return the format
          it advertised on its own product — whether it hosts that format
          directly or proxies to the creative agent named in
          `format_ids[0].agent_url`. An empty `formats[]` means the sales
          agent's product catalog references a format that does not resolve —
          a stale or typo'd entry that would have failed silently at
          `sync_creatives` after the media buy was already committed.
        task: list_creative_formats
        schema_ref: "creative/list-creative-formats-request.json"          # :368
        response_schema_ref: "creative/list-creative-formats-response.json" # :369
        sample_request:                                                    # :380
          format_ids:
            - "$context.product_format_id"
          context:
            correlation_id: "media_buy_seller--list_formats_integrity"
        context_inputs:                                                    # :397
          - key: product_format_id
            inject_at: "format_ids[0]"
        validations:                                                       # :400-414
          - check: response_schema
            description: "Response matches list-creative-formats-response.json schema"
          - check: field_present
            path: "formats[0]"
            description: "Sales agent resolves the format_id — products[0].format_ids[0] exists in the catalog"
          - check: field_value
            path: "formats[0].format_id"
            value: "$context.product_format_id"
            description: "Returned format_id round-trips verbatim — the agent cannot substitute a different format in response to the filter"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "media_buy_seller--list_formats_integrity"
            description: "Context correlation_id returned unchanged"
```

Note `schema_ref` / `response_schema_ref` point at the **`creative/`** variants of the schema, not `media-buy/`, even inside the media-buy protocol.

### 1c. The second graded step for the same behaviour — `list_formats` (media-buy/index.yaml:604-670)

This one is easy to miss and carries the *real* roundtrip grader (`refs_resolve`, set-membership across `formats[*]`, not just `formats[0]`), plus a pagination cap:

```yaml
      - id: list_formats                                                 # :604
        title: "Check creative format requirements"
        narrative: |
          The buyer confirms the first creative format referenced by the discovered
          product. ... This is a bounded integrity check, not a
          full format-catalog dump.
        sample_request:                                                   # :623
          format_ids:
            - "$context.product_format_id"
          pagination:
            max_results: 1
          context:
            correlation_id: "media_buy_seller--list_formats"
        validations:
          - check: field_present
            path: "formats[0].format_id.agent_url"                        # :638
          - check: field_present
            path: "formats[0].format_id.id"
            description: "Format IDs include id — must match those in get_products"
          - check: field_present
            path: "context"
          - check: field_value
            path: "context.correlation_id"
            value: "media_buy_seller--list_formats"
          - check: refs_resolve                                           # :649
            description: |
              The captured format_id returned on the first product resolves to a
              format in this agent's list_creative_formats. ... Third-party
              format_ids (agent_url pointing at a different creative agent)
              can't be verified without calling that agent and are reported as
              observations rather than failures.
            source:
              from: context
              path: "product_format_id"
            target:
              from: current_step
              path: "formats[*].format_id"                                # :662
            match_keys: [agent_url, id]                                   # :663
            scope:
              key: agent_url
              equals: $agent_url
            on_out_of_scope: warn                                         # :668
```

### 1d. `discover_formats` / `list_formats` in the creative protocol (creative/index.yaml:79-129)

This is where the `max_results: 5` cap the lead mentioned actually lives — it binds to the **baseline catalog** scenario, not to the roundtrip:

```yaml
        expected: |                                                       # creative/index.yaml:98
          Return the first page of creative formats your platform accepts:
          ...
          - Up to five formats on this compliance request; callers paginate for the rest when needed
        sample_request:
          pagination:
            max_results: 5
```

---

## 2. Schema constraints at 3.1.1

All quotes from `cd /Users/konst/projects/adcp && git show v3.1.1:<path>`.

### `static/schemas/source/core/format-id.json`

```
"description": "A JSON object — never a plain string — that identifies a creative format ...
                Required properties: agent_url ... and id (slug matching [a-zA-Z0-9_-]+) ...
                Using a plain string here is a schema violation."
"required": ["agent_url", "id"]
"additionalProperties": true
"properties.id.pattern": "^[a-zA-Z0-9_-]+$"
"properties.agent_url.description": "... Callers comparing two `format-id` values MUST
   canonicalize `agent_url` per the AdCP URL canonicalization rules before treating two
   formats as the same. See docs/reference/url-canonicalization."
"dependencies": { "width": ["height"], "height": ["width"] }
```

Byte-identical to the currently-vendored 04f59d2d5 copy modulo unicode escaping — **no drift here**.

### `docs/reference/url-canonicalization.mdx` (authoritative home of the algorithm cited above)

> "The canonicalization applies RFC 3986 §6.2.2 ... and §6.2.3, in this order. Implementations MUST apply every step and compare the result byte-for-byte."
> 1 lowercase scheme · 2 lowercase host (UTS-46 A-labels) · 3 strip userinfo · 4 strip default ports · 5 `remove_dot_segments`, empty path → `/` · 6 normalize percent-encoding · 7 preserve query byte-for-byte · 8 strip fragment

and, in the "Where it applies" table:

> | `format-id` resolution | `format-id.agent_url` against the URL an agent publishes for its formats |

### `static/schemas/source/media-buy/list-creative-formats-request.json`

```
"format_ids": { "type":"array", "description":"Return only these specific format IDs (e.g., from get_products response)",
                "items": {"$ref":"/schemas/core/format-id.json"}, "minItems": 1 }
"pagination": { "$ref": "/schemas/core/pagination-request.json" }
"context":    { "$ref": "/schemas/core/context.json" }
```

"Return only these specific format IDs" is the **subset mandate**: the response's `formats[]` must be a subset of the requested references. The current scenario never checks this.

### `static/schemas/source/creative/list-creative-formats-response.json` (the `response_schema_ref` the storyboard names)

```json
"allOf": [
  { "$ref": "/schemas/core/version-envelope.json" },
  { "$ref": "/schemas/core/protocol-envelope.json" }   <-- ADDED at 3.1.1
],
"required": ["formats"],
"properties": { "formats": {"items": {"$ref": "/schemas/core/format.json"}},
                "creative_agents": ..., "errors": ...,
                "pagination": {"$ref": "/schemas/core/pagination-response.json"},
                "context": {"$ref": "/schemas/core/context.json"}, "ext": ... }
```

`pagination` is **optional** (confirms the lead's note — only `formats` is required).

### `static/schemas/source/core/protocol-envelope.json`

```
"required": ["status"]
"description": "... The `status` field is REQUIRED on every task response envelope, including
  synchronous metadata responses ... Agents shipping responses without a top-level `status`
  are non-conformant regardless of whether the task body schema would otherwise validate."
```

### `static/schemas/source/core/format.json`

```
"required": ["format_id", "name"]
"format_id": { "$ref": "/schemas/core/format-id.json",
  "description": "This format's own identifier — a structured object {agent_url, id}, not a string." }
```

### `static/schemas/source/core/pagination-response.json`

```
"required": ["has_more"]
"cursor": "Opaque cursor to pass in the next request ... Only present when has_more is true."
"total_count": {"type":"integer","minimum":0}
"additionalProperties": false
```

The `cursor ↔ has_more` coupling is prose only — no `if/then`, so JSON Schema does not gate it (matches the lead's note).

### `static/schemas/source/core/pagination-request.json`

```
"max_results": {"type":"integer","minimum":1,"maximum":100,"default":50}
"additionalProperties": false
```

---

## 3. Conflicts

### C1 — Schema overrides storyboard: verbatim `field_value` vs mandatory canonicalization. **Schema wins.**

The storyboard grades `field_value formats[0].format_id == $context.product_format_id` — byte equality. `core/format-id.json` says callers **MUST canonicalize `agent_url`** before treating two format ids as the same. These disagree the moment producer and consumer spell the URL differently, which is not hypothetical here:

```
FormatId(agent_url="https://creative.adcontextprotocol.org")  ->  wire "https://creative.adcontextprotocol.org/"
canonical_agent_url(...)                                      ->  "https://creative.adcontextprotocol.org"
```

Pydantic's `AnyUrl` appends the empty-path `/` on serialization. A buyer who typed the slashless form and byte-compares the wire fails the storyboard's `field_value` check against a fully conformant seller. **Per the authority order, comparison is canonical, not verbatim.** `id` stays a byte comparison (no canonicalization rule; `^[a-zA-Z0-9_-]+$`).

This also exposes why the current step is weaker than it reads: it captures `str(fid.agent_url)` — already Pydantic-normalized — and compares it to the same Pydantic-normalized wire value. Both sides are laundered through the same normalizer, so the "verbatim roundtrip" assertion cannot observe the buyer's actual input at all.

### C2 — Wrong `@source` path and a backwards pin

Footer says `path=static/compliance/source/protocols/creative/index.yaml`. At 3.1.1 the phase is in `protocols/media-buy/index.yaml:352`; the creative protocol has no `list_formats_integrity`. And `04f59d2d5` is an ancestor of beta.3, i.e. older than the repo's own pin.

### C3 — The scenario grades `formats[0]` only; the spec grades the set

3.1.1's `refs_resolve` targets `formats[*].format_id` with `match_keys: [agent_url, id]`, and the request schema says "Return only these specific format IDs". Checking `formats[0]` alone passes a seller that ignores the `format_ids` filter entirely and happens to sort the right format first. Missing checks: (a) every returned entry is in the requested set, (b) the captured pair is a member of `formats[*].format_id`.

### C4 — Missing: context echo (two graded checks)

`field_present context` + `field_value context.correlation_id` are graded on **both** media-buy steps. The scenario checks neither. Production does echo (`creative_formats.py:512  context=req.context`), so this is gradeable — except on REST, see C7.

### C5 — Missing: `status` on the response envelope (new at 3.1.1)

3.1.1 added `{"$ref": "/schemas/core/protocol-envelope.json"}` to `creative/list-creative-formats-response.json`'s `allOf` — it is not in the 04f59d2d5 copy vendored at `tests/fixtures/adcp_schemas_pinned/creative/list-creative-formats-response.json`. `protocol-envelope.json` has `"required": ["status"]`. Our `ListCreativeFormatsResponse` deliberately carries no `status` (`src/core/schemas/creative.py:547-549`: "Protocol fields ... are added by the protocol layer"), and the REST route returns the bare `response.model_dump(mode="json")` (`src/routes/api_v1.py:211`) with no envelope wrapper. **This is a genuine production gap that the re-pin surfaces**, not a scenario defect.

### C6 — The `schema-valid` step over-claims

`then_response_schema_valid` (`uc005_format_id_roundtrip.py:97`) says "schema-valid against list-creative-formats-response.json" but asserts only `isinstance(formats, list)`. A real validator already exists — `tests/helpers/pinned_schema.py::validate_against_pinned_schema` — and the response schema is already vendored. It is not wired to this step. Fixing that requires re-vendoring at v3.1.1 (which pulls in `core/protocol-envelope.json` and its ref closure) and then C5 goes red.

### C7 — Transport-parity defect: REST drops `context`, REST **and** MCP drop `pagination`

`ListCreativeFormatsBody` (`src/routes/api_v1.py:133-147`) declares no `context` and no `pagination` field, so both are silently discarded on REST. The MCP wrapper `list_creative_formats(...)` (`src/core/tools/creative_formats.py:522-535`) takes `context` but no `pagination`. This violates Pattern #5 ("Forward **every** `_impl` parameter") and means:
- the C4 context-echo check is **red on REST / e2e_rest** until `ListCreativeFormatsBody` gains `context`;
- a `pagination.max_results` Examples column would be unreachable on MCP and vacuous on REST — which is why the proposed rewrite deliberately does **not** parameterize `max_results`, and asserts the pagination invariants that hold for the unpaginated request instead.

Adjacent, out of scope: `ListCreativeFormatsBody.adcp_version` defaults to `"1.0.0"`, which does not match `version-envelope.json`'s `^\d+\.\d+(-[a-zA-Z0-9.-]+)?$`.

### C8 — POST-S1 conflict (flagged, not fixed)

Line 10 claims "Buyer knows the **complete catalog** of creative formats available from this seller". At 3.1.1 no single `list_creative_formats` call promises a complete catalog: `max_results` defaults to 50 and caps at 100, `has_more`/`cursor` paginate, and the compliance storyboard deliberately requests only 5 ("callers paginate for the rest when needed", creative/index.yaml:98-103). This roundtrip scenario is a *filtered single-reference* lookup and must not be tagged `@post-s1`; the proposed scenario carries no post-condition tag. POST-S1 as written is unachievable in one call and needs a separate decision.

---

## 4. Proposed Gherkin

Replaces lines 1060-1076. `<canonical_agent_url>` is identical on every row on purpose — that *is* the invariant: six wire spellings, one federation identity.

```gherkin
  @T-UC-005-storyboard-format-id-roundtrip-from-products @storyboard-v3.1 @v3-1 @format-id-roundtrip
  Scenario Outline: Format ID roundtrip -- list_creative_formats resolves the format_id a product advertised, however the buyer spells agent_url
    Given the Buyer Agent captured a format_id object {agent_url, id} from a prior get_products response
    And the Buyer Agent respells the captured agent_url as "<agent_url_on_the_wire>"
    When the Buyer Agent sends list_creative_formats with format_ids [{respelled agent_url, captured id}] and context.correlation_id "media_buy_seller--list_formats_integrity"
    Then the response should be schema-valid against list-creative-formats-response.json
    And the formats array should contain at least one entry
    And every returned format_id.id should equal the captured id exactly
    And every returned format_id.agent_url should canonicalize to "<canonical_agent_url>"
    And every entry's format_id should be an object carrying both agent_url and id
    And the captured {agent_url, id} pair should appear in formats[*].format_id
    And the response includes pagination metadata with has_more false
    And the response pagination total_count should equal 1
    And the response should echo context.correlation_id "media_buy_seller--list_formats_integrity"
    # media-buy/index.yaml list_formats_integrity (:352) + list_formats (:604): the buyer
    # captures products[0].format_ids[0] from get_products and asks list_creative_formats
    # to resolve it. The sales agent MUST return the format it advertised on its own
    # product. An empty formats[] means the catalog references a stale or typo'd format
    # that would have failed silently at sync_creatives after the buy was committed --
    # so "at least one entry" IS the compliance failure check, asserted once, not twice.
    #
    # Set semantics, not formats[0]: list_formats refs_resolve targets formats[*].format_id
    # with match_keys [agent_url, id] (:662-663), and the request schema says format_ids
    # means "Return only these specific format IDs". Grading formats[0] alone passes a
    # seller that ignores the filter and happens to sort the right format first.
    #
    # Canonical, not verbatim: the storyboard grades field_value formats[0].format_id
    # byte-for-byte (:408-411), but core/format-id.json mandates that callers comparing
    # two format-id values MUST canonicalize agent_url first (RFC 3986 6.2.2/6.2.3, see
    # docs/reference/url-canonicalization). Schema outranks storyboard: the Examples rows
    # below are six wire spellings of ONE federation identity, and every one of them must
    # resolve. Pydantic AnyUrl already folds scheme/host case, the default port and dot
    # segments, so the fragment row is the one that only canonicalization can strip --
    # it is what falsifies a seller comparing raw agent_url strings. id stays a byte
    # comparison: no canonicalization rule, pattern ^[a-zA-Z0-9_-]+$.
    #
    # pagination is OPTIONAL on the 3.1.1 response (required only on list-creatives /
    # list-tasks / tasks-list). We emit it, so it is graded: one matching format under the
    # default max_results=50 means has_more false, total_count 1, and no cursor
    # (cursor "only present when has_more is true" is prose in core/pagination-response.json,
    # not gated by JSON Schema).
    # list_formats_integrity: format_ids advertised on products MUST resolve through list_creative_formats
    # @source repo=adcp ref=v3.1.1 phase=list_formats_integrity path=dist/compliance/3.1.1/protocols/media-buy/index.yaml#L352
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/format-id.json
    # @source repo=adcp ref=v3.1.1 path=docs/reference/url-canonicalization.mdx

    Examples: agent_url spellings that MUST canonicalize to one federation identity
      | agent_url_on_the_wire                             | canonical_agent_url                    |
      | https://creative.adcontextprotocol.org            | https://creative.adcontextprotocol.org |
      | https://creative.adcontextprotocol.org/           | https://creative.adcontextprotocol.org |
      | HTTPS://Creative.AdContextProtocol.ORG            | https://creative.adcontextprotocol.org |
      | https://creative.adcontextprotocol.org:443        | https://creative.adcontextprotocol.org |
      | https://creative.adcontextprotocol.org/#formats   | https://creative.adcontextprotocol.org |
      | https://creative.adcontextprotocol.org/./         | https://creative.adcontextprotocol.org |
```

Every spelling was executed against the real production helpers before proposing the table:

| wire spelling | `str(FormatId.agent_url)` | `canonical_agent_url()` |
|---|---|---|
| `…org` | `…org/` | `…org` |
| `…org/` | `…org/` | `…org` |
| `HTTPS://Creative.…ORG` | `…org/` | `…org` |
| `…org:443` | `…org/` | `…org` |
| `…org/#frag` | `…org/#frag` | `…org` |
| `…org/./` | `…org/` | `…org` |

Production filters on `format_id_identity` = `(canonical_agent_url, id)` (`src/core/tools/creative_formats.py:306-307`, `src/core/schemas/_base.py:145-188`), and applies the filter **before** pagination (`:428-446`), so `total_count == 1` is post-filter.

### Two lines dropped, and why

- `And formats[0].format_id should roundtrip verbatim with the captured {agent_url, id}` → replaced by strictly stronger checks (every entry, canonical `agent_url`, exact `id`, set membership). See C1: the verbatim form is weaker than it reads and conflicts with the schema's canonicalization mandate.
- `And an empty formats[] would indicate a stale catalog reference and is a compliance failure` → this asserted the *same predicate* as the preceding line with a different message (`_assert_formats_non_empty` called twice). The compliance framing is preserved in the comment block and in the assertion message of the surviving non-empty step. Nothing is lost; a duplicate is.

---

## 5. Step inventory

### Reused verbatim — no new code

| Step text | Definition |
|---|---|
| `Given the Buyer Agent captured a format_id object {agent_url, id} from a prior get_products response` | `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:29` |
| `Then the response should be schema-valid against list-creative-formats-response.json` | same file `:97` — **body must be upgraded**, see below |
| `And the formats array should contain at least one entry` | same file `:108` |
| `And every entry's format_id should be an object carrying both agent_url and id` | `tests/bdd/steps/domain/uc005_format_id_shape.py:66` |
| `And the response includes pagination metadata with has_more false` | `tests/bdd/steps/domain/uc011_accounts.py:615` (generic — reads `resp.pagination` only; loaded globally via `tests/bdd/conftest.py:62`) |

### Modified

| Step | Change |
|---|---|
| `When the Buyer Agent sends list_creative_formats with format_ids [{respelled agent_url, captured id}] and context.correlation_id "…"` | replaces the When at `uc005_format_id_roundtrip.py:74`. Must build `FormatId(agent_url=ctx["respelled_agent_url"], id=captured["id"])` and set `req.context` with the correlation id. `_call_via` already forwards `context` on IMPL/A2A/MCP. |
| `Then the response should be schema-valid against …` | today asserts `isinstance(formats, list)`. Should call `validate_against_pinned_schema("list-creative-formats-response.json", wire)` (`tests/helpers/pinned_schema.py:60`). **Blocked on re-vendoring the pinned tree at v3.1.1** and on C5 (`status`). |

### New (5 step definitions)

| Step text | Notes |
|---|---|
| `Given the Buyer Agent respells the captured agent_url as "<agent_url_on_the_wire>"` | stores `ctx["respelled_agent_url"]`; asserts it is not already equal to nothing — trivial state setter, no assertion required of a Given |
| `Then every returned format_id.id should equal the captured id exactly` | iterate `_serialized_formats(ctx)`; `entry["format_id"]["id"] == ctx["captured_format_id"]["id"]` |
| `Then every returned format_id.agent_url should canonicalize to "<canonical_agent_url>"` | `canonical_agent_url(entry["format_id"]["agent_url"]) == expected` — imports the production helper from `src.core.schemas._base` |
| `Then the captured {agent_url, id} pair should appear in formats[*].format_id` | mirrors `refs_resolve` `match_keys: [agent_url, id]`: build the identity set over `formats[*]`, assert membership |
| `Then the response pagination total_count should equal 1` | `_require_response(ctx).pagination.total_count == 1` |
| `Then the response should echo context.correlation_id "…"` | **phrasing precedent exists in features only** — `BR-UC-003-update-media-buy.feature:2050, 2065, 2079` use `the response should echo the context.correlation_id unchanged`, and **no step definition implements it** (those UC-003 scenarios are dormant). Implementing a parameterized variant here also un-blocks wiring those three. |

Reusable helpers already in place: `_serialized_formats` (`uc005_format_id_shape.py:34`, wire-first with the loud no-wire guard), `assert_wire_format_id_is_object` (`tests/helpers/format_assertions.py:22`), `_require_response` (`tests/bdd/steps/_outcome_helpers.py`), `_call_via` (`tests/bdd/steps/generic/when_request.py:39`).

---

## 6. Risks

1. **The context-echo Then is red on REST and e2e_rest today** (C7). `ListCreativeFormatsBody` has no `context` field, so the correlation id never reaches `_impl` and the echo comes back `None`. Fix is one field on the REST body model plus forwarding — small, and the 3.1.1 storyboard grades it on both media-buy steps. This needs a decision before the scenario lands: fix production in the same change, or land the scenario and accept a red transport (which the no-allowlist-growth rule argues against).
2. **The `schema-valid` Then is red once it is made real** (C5/C6). Re-vendoring `creative/list-creative-formats-response.json` at v3.1.1 pulls in `core/protocol-envelope.json` (`required: ["status"]`) and its ref closure (`enums/task-status.json`, `core/error.json`, `core/context.json`, `core/push-notification-config.json`). Our response has no top-level `status` on any transport. I did not soften the step text to dodge this — the mandate is real and the gap is production's. Recommend a separate ticket for envelope `status`, and keeping the Then as-is (weak) only until that lands, with the upgrade tracked.
3. **`total_count == 1` assumes the mock registry holds exactly one format matching the seeded `(agent_url, id)` pair.** True today: the Given seeds one product format id (`display_300x250_image`) and the filter is pair-exact. It would break if `_get_mock_formats()` ever gains a duplicate id under the same agent_url. Alternative if that feels brittle: `total_count` equals the number of `formats` entries returned.
4. **Unused-column risk in the Examples table.** Both columns are consumed by step text, so nothing is dangling — but I did not run the BDD suite, so I have not confirmed pytest-bdd is happy with the `<canonical_agent_url>` placeholder inside a quoted step argument (standard usage; low risk).
5. **`#formats` fragment row.** Pydantic preserves the fragment on the wire, and `canonicalize_target_uri` strips it, so production resolves it. If the SDK's `canonicalize_target_uri` ever stops stripping fragments this row goes red — which is the intended alarm, not a flake.
6. **A2A/MCP wire shape for `context`.** Production puts `context` inside the response *model*, so it appears in the payload on every transport; the A2A stash happens before the message/success strip. I traced the code but did not execute the BDD run, so the exact wire key placement on A2A is verified by reading, not by execution.
7. **`max_results` is deliberately not parameterized** (C7): MCP's wrapper has no `pagination` parameter at all, and REST drops it. Adding rows for the storyboard's `max_results: 1` (media-buy `list_formats`) and `max_results: 5` (creative `discover_formats`) requires fixing the two wrappers first. Worth a follow-up — the storyboard grades `formats[0]` *with* `max_results: 1`, i.e. a seller that paginates before filtering fails, and we cannot currently express that on two of four transports.
8. **Sibling scenario at line 1078** (`third-party-agent`) carries the same wrong `@source` footer (`protocols/creative/index.yaml` @ 04f59d2d5); its real home is the `scope.equals: $agent_url` / `on_out_of_scope: warn` block at `media-buy/index.yaml:664-668`. Out of scope here, but it should be re-pinned in the same pass.

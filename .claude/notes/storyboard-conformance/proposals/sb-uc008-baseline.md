# sb-uc008-baseline — `@T-UC-008-storyboard-baseline-end-to-end`

Scenario: "Signals baseline conformance -- discovery propagates signal_agent_segment_id into activation"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-008-manage-audience-signals.feature:1111`

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** Two independent reasons, either one sufficient:

1. **We do not declare the `signals` protocol.** `src/core/tools/capabilities.py:271-272` emits
   `supported_protocols=[SupportedProtocol.media_buy]`, `specialisms=[AdcpSpecialism.sales_non_guaranteed]`.
   The `signals_baseline` storyboard is `protocol: signals` and its own narrative scopes itself to
   agents that declare it: *"Agents declaring supported_protocols: [\"signals\"] MUST pass this
   baseline."* We declare `media_buy` only, so the entire signals track is off our conformance path.

2. **The behaviour this scenario describes is not in `signals_baseline` at 3.1.1 at all.** The
   storyboard has exactly two phases — `capability_discovery` and `discovery`. There is **no
   activation phase**, no `activate_signal` step, and `activate_signal` is not in its
   `required_tools` (`required_tools: [get_signals]` only). The scenario's entire premise —
   "discovery propagates signal_agent_segment_id **into activation**" — is graded in a *different
   tier*: the `signal_marketplace` **specialism**, which we also do not declare.

The storyboard says so explicitly (`protocols/signals/index.yaml:26-30`):

> This baseline tests those calls and nothing beyond them. Specialism storyboards (signal-owned,
> signal-marketplace) exercise the richer flows specific to each model — pricing option selection,
> source/provenance discriminators, and, for marketplace signal agents, **activation/deactivation
> on downstream destinations**.

So `@storyboard-v3.1` is unjustified. It should become `@schema-v3.1`.

**Additionally — and this outranks the tagging question — the scenario is dormant.** There is no
`scenarios("features/BR-UC-008-manage-audience-signals.feature")` binding anywhere in `tests/bdd/`,
no `tests/bdd/steps/domain/uc008*.py`, and no signals env in `tests/harness/`. Not one of the ~40
scenarios in this feature file has ever executed. Its three assertions are not weak — they are
**absent**.

---

## 2. Real binding at 3.1.1

**The current footer is wrong on both counts.**

Current:
```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/signals/index.yaml
```

- `ref=v3.1-04f59d2d5` is an ancestor of beta.3 — older than our own 3.1.1 pin. Stale.
- The *path* is right in name only. `protocols/signals/index.yaml` exists at 3.1.1, but it does not
  contain the activation step the scenario asserts. This is not the off-by-one defect seen elsewhere
  in this sweep; it is a **tier** error — the cited file grades discovery, the scenario asserts
  activation.

### What `signals_baseline` actually grades at 3.1.1

`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/signals/index.yaml`

Phase `discovery`, step `search_signals`, **lines 129-148**, verbatim:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-signals-response.json schema"
          - check: field_present
            path: "signals[0].signal_agent_segment_id"
            description: "First signal carries a signal_agent_segment_id"
          - check: field_present
            path: "signals[0].signal_id.source"
            description: "Signal ID carries a source discriminator (agent_native or data_provider)"
          - check: field_present
            path: "signals[0].pricing_options"
            description: "Signal carries pricing options the buyer can select"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "signals_baseline--search_signals"
            description: "Context correlation_id returned unchanged"
```

And phase `capability_discovery`, step `get_capabilities`, **lines 78-89**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches get-adcp-capabilities-response.json schema"
          - check: field_present
            path: "supported_protocols"
            description: "Agent declares supported protocols"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "signals_baseline--get_capabilities"
            description: "Context correlation_id returned unchanged"
```

That is the **whole** storyboard. `deployments`, `activation_key`, `is_live`,
`estimated_activation_duration_minutes` — none of it appears anywhere in `signals_baseline`.

Note the `context_outputs` at lines 124-128 do capture `signal_agent_segment_id` and
`pricing_option_id` — but purely to hand them to *downstream specialism* storyboards. Capturing a
value is not grading its reuse; nothing in `signals_baseline` re-reads them.

### Where activation is actually graded

`/Users/konst/projects/adcp/dist/compliance/3.1.1/specialisms/signal-marketplace/index.yaml`,
phase `platform_activation`, step `activate_on_platform`, **lines 330-359**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches activate-signal-response.json schema"
          - check: field_present
            path: "deployments[0].type"
            description: "Deployment includes type"
          - check: field_value
            path: "deployments[0].type"
            value: "platform"
            description: "Deployment type is 'platform'"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "signal_marketplace--activate_on_platform"
            description: "Context correlation_id returned unchanged"
          - check: field_present
            path: "deployments[0].activation_key"
            description: "Deployment includes activation_key for targeting"
          - check: upstream_traffic
            description: "activate_on_platform caused upstream traffic to a DSP carrying the signal_agent_segment_id"
            min_count: 1
            endpoint_pattern: "POST *"
```

`signal_marketplace` declares `required_tools: [get_signals, activate_signal]` and
`requires_scenarios: [signal_marketplace/governance_denied]`. We declare neither the specialism nor
the tools' real behaviour (see §4). The two sibling scenarios
`@T-UC-008-storyboard-activate-agent-destination` and
`@T-UC-008-storyboard-activate-platform-destination` cite the same wrong path and belong here too —
flagging for the lead, not chasing.

Also note the anti-façade `upstream_traffic` check: a mock that fabricates an `activation_key`
without calling a DSP **fails by design**. Our `_activate_signal_impl` is exactly that mock.

---

## 3. Schema constraints at 3.1.1

### `signals/activate-signal-response.json` — `deployments` is REQUIRED on success

`git show v3.1.1:static/schemas/source/signals/activate-signal-response.json`:

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
  "oneOf": [
    {
      "title": "ActivateSignalSuccess",
      "properties": {
        "deployments": {
          "type": "array",
          "items": { "$ref": "/schemas/core/deployment.json" }
        },
        ...
      },
      "required": ["deployments"],
      "not": { "required": ["errors"] }
    },
```

The error branch carries `"not": {"anyOf": [{"required": ["deployments"]}, {"required": ["sandbox"]}]}`
— i.e. success and error are mutually exclusive, atomically.

### `signals/get-signals-response.json` — `signal_id` is DEPRECATED at 3.1.1

```json
          "signal_id": {
            "$ref": "/schemas/core/signal-id.json",
            "description": "DEPRECATED. Use signal_ref instead. Legacy SignalId retained for compatibility with older Signals Protocol clients.",
            "deprecated": true
          },
          "signal_ref": {
            "$ref": "/schemas/core/signal-ref.json",
            "description": "Canonical signal reference for discovery, activation, and media-buy targeting. ..."
          },
```

`signal_agent_segment_id` is the opaque activation handle, and the schema states the roundtrip
contract the scenario title gestures at:

```json
          "signal_agent_segment_id": {
            "type": "string",
            "description": "Opaque resolved-segment handle issued by this signal source. Pass this string verbatim to activate_signal.signal_agent_segment_id, and echo it in package signal targeting when the selected product option exposes the same handle. ... Do not pass the signal_id object as this handle, and do not reconstruct a segment handle from categorical values when get_signals returned a resolved segment."
          },
```

### `core/signal-id.json` — the source enum is `catalog` | `agent`

```json
  "deprecated": true,
  "discriminator": { "propertyName": "source" },
```
with `"source": {"const": "catalog", ...}` (requiring `data_provider_domain` + `id`) and
`"source": {"const": "agent", ...}` (requiring `agent_url` + `id`).

### `core/protocol-envelope.json` — `status` REQUIRED

```
The `status` field is REQUIRED on every task response envelope, including synchronous metadata
responses (e.g., `get_adcp_capabilities`) where the value is `completed`. Agents shipping responses
without a top-level `status` are non-conformant regardless of whether the task body schema would
otherwise validate.
```

`get-signals-request.json` has **no** `required` array — `signal_spec` is optional.

---

## 4. Conflicts

### Schema overrides storyboard (stated explicitly, per the authority order)

- **Source discriminator vocabulary.** The storyboard's line 137 description says the discriminator
  is *"(agent_native or data_provider)"*. `core/signal-id.json` at 3.1.1 defines the enum as
  **`catalog` | `agent`**. **The 3.1.1 schema wins** — the storyboard description is prose drift and
  binds nothing. Our production emits `source: "agent"`, which is schema-correct. The sibling
  scenarios `@T-UC-008-v31-signal-source-catalog` / `-agent` use the correct schema vocabulary and
  need no change on this axis.
- **`signal_id` deprecation.** The storyboard grades `signals[0].signal_id.source`; the 3.1.1 schema
  marks `signal_id` `"deprecated": true` and names `signal_ref` canonical. Grading a deprecated
  field is legal but is upstream drift. **The schema wins on what the canonical identity surface
  is** — we should not build new assertions on `signal_id`. (Already noted in
  `src/core/tools/signals.py:51`.)

### What the scenario gets wrong

| Line | Assertion | Status |
|---|---|---|
| 1116 | `Given the Buyer Agent calls get_signals with signal_spec "Adults interested in electric vehicles"` | **Produces zero signals.** See below. |
| 1117 | `And the response carries at least one signal entry` | **RED** — consequence of the above. Also bare existence, banned by `test_architecture_bdd_no_trivial_assertions.py`. |
| 1119 | `When ... activate_signal with the captured signal_agent_segment_id and pricing_option_id` | **Not expressible.** The wrapper takes no `pricing_option_id` and no `destinations`. |
| 1120 | `Then the activation response should be schema-valid against activate-signal-response.json` | **RED** — response has no `deployments`. |
| 1121 | `And the deployments array should carry at least one entry with a type discriminator` | **RED** — `ActivateSignalResponse` has no `deployments` field at all. |
| 1122 | `And the signal_agent_segment_id ... should match the value captured from discovery` | Green in substance, but asserted against the wrong field name (`signal_id`, not `deployments`). |

**The `signal_spec` produces an empty array.** `_get_signals_impl` filters by naive substring
containment (`src/core/tools/signals.py:161-168`):

```python
        if req.signal_spec:
            spec_lower = req.signal_spec.lower()
            if (
                spec_lower not in signal.name.lower()
                and spec_lower not in signal.description.lower()
                and spec_lower not in signal.signal_type.lower()
            ):
                continue
```

The storyboard's own `sample_request` spec, `"Adults interested in electric vehicles"`, is not a
substring of any of the six hardcoded sample signals' name, description, or type. Result:
`signals == []`, and the graded `field_present: signals[0].signal_agent_segment_id` fails. **If we
ever declared `signals`, we would fail the baseline on its own sample request.**

**The activation response is structurally incapable of validating.**
`src/core/schemas/_base.py:2458` — and its docstring admits the divergence:

```python
class ActivateSignalResponse(SalesAgentBaseModel):
    """Response from signal activation.

    NOT migrated to library base (evaluated in salesagent-xeb):
    1. Library uses RootModel[SuccessVariant | ErrorVariant] — cannot add fields
    2. Library has no signal_id field (no request correlation in response)
    3. Library uses structured list[Deployment] vs our generic activation_details dict
    4. Library enforces atomic success/error; we allow both simultaneously
    """
    signal_id: str
    activation_details: dict[str, Any] | None
    errors: list[Error] | None
    context: ContextObject | None
```

No `deployments`. Point 4 directly contradicts the schema's `oneOf` + `not` construction.

**Destinations are fabricated, not wired.** `_build_activate_signal_request`
(`src/core/tools/signals.py:239-247`) hardcodes
`destinations=[{"type": "platform", "platform": "mock"}]` and a synthesised
`idempotency_key`, with a docstring conceding both are REQUIRED on the spec request and neither is
surfaced at the wrapper. The two sibling `activate-*-destination` scenarios are therefore not merely
red — they are inexpressible through the current boundary.

---

## 5. Proposed Gherkin

**Recommendation for the baseline PR: correct the tag and `@source`, and leave the file dormant
(do not add a `scenarios()` binding).** Adding a binding would collect ~40 scenarios with zero step
definitions and fail the whole file. The Gherkin below is written so that every assertion matches
production *today* — it goes green the moment a signals harness env exists (ticket T1), and not
before.

The scenario is split in two because 3.1.1 puts the two halves in different tiers: discovery is
`protocols/signals` (baseline), the roundtrip is `specialisms/signal-marketplace`. Both are behind
gates we do not declare, so both carry `@schema-v3.1`, not `@storyboard-v3.1`.

```gherkin
  # UC-008 signals are NOT on our conformance path: capabilities.py declares
  # supported_protocols=[media_buy] only, and 3.1.1 scopes the signals baseline to agents
  # declaring supported_protocols=["signals"] (protocols/signals/index.yaml:31-33).
  # Tagged @schema-v3.1 (schema-grounded), not @storyboard-v3.1 (storyboard-graded).
  @T-UC-008-storyboard-baseline-end-to-end @schema-v3.1 @v3-1 @baseline-conformance
  Scenario Outline: get_signals returns schema-shaped signal identity for <case>
    Given the Buyer Agent is authenticated for the default tenant
    When the Buyer Agent calls get_signals with signal_spec "<signal_spec>"
    Then the get_signals response should carry exactly <count> signal entries
    And the first signal's signal_agent_segment_id should equal "<segment_id>"
    And the first signal's signal_id.source should equal "agent"
    And the first signal's signal_id.id should equal "<segment_id>"
    And the first signal's pricing_options should carry exactly 1 entry
    And the first signal's first pricing_option_id should equal "cpm_usd"
    And the first signal's first pricing_option model should equal "cpm"
    And the first signal's first pricing_option currency should equal "USD"

    # signal_id.source enum is "catalog" | "agent" per core/signal-id.json at v3.1.1 —
    # NOT the "agent_native | data_provider" wording in the storyboard prose (schema wins).
    # signal_id itself is deprecated at 3.1.1 in favour of signal_ref; we assert it here only
    # because it is what production emits. New identity assertions belong on signal_ref (#T3).
    Examples:
      | case                    | signal_spec    | count | segment_id                |
      | marketplace_catalog     | marketplace    | 4     | auto_intenders_q1_2025    |
      | owned_catalog           | owned          | 2     | sports_content            |
      | name_substring_match    | Luxury Travel  | 1     | luxury_travel_enthusiasts |

    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/signals/index.yaml
    #         phase=discovery step=search_signals lines=129-148
    #         (NOT on our conformance path — we do not declare supported_protocols=["signals"])

  # Characterization row, deliberately separated: the storyboard's OWN sample_request spec
  # returns zero signals against our substring matcher (signals.py:161-168), which would fail
  # the graded check field_present signals[0].signal_agent_segment_id. Pinned so the gap is
  # visible; this scenario MUST be updated when semantic matching lands (#T2).
  @T-UC-008-baseline-spec-no-semantic-match @schema-v3.1 @v3-1 @known-gap
  Scenario: storyboard sample signal_spec matches no signal under substring filtering
    Given the Buyer Agent is authenticated for the default tenant
    When the Buyer Agent calls get_signals with signal_spec "Adults interested in electric vehicles"
    Then the get_signals response should carry exactly 0 signal entries
    And the get_signals response message should equal "No signals found matching your criteria."
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/protocols/signals/index.yaml
    #         phase=discovery step=search_signals sample_request.signal_spec (line 121)

  # Activation is NOT in signals_baseline at 3.1.1 — it is graded by the signal_marketplace
  # SPECIALISM (specialisms/signal-marketplace/index.yaml:330-359), which we do not declare.
  # Assertions below cover only the segment-id roundtrip, which production does honour.
  # deployments / activation_key / is_live are omitted deliberately: production has no
  # deployments field (#T4), so any such assertion would be red.
  @T-UC-008-baseline-segment-id-roundtrip @schema-v3.1 @v3-1 @activation
  Scenario Outline: activate_signal echoes the discovered signal_agent_segment_id unmodified
    Given the Buyer Agent is authenticated for the default tenant
    And the Buyer Agent captured signal_agent_segment_id "<segment_id>" from get_signals
    When the Buyer Agent calls activate_signal with the captured signal_agent_segment_id
    Then the activate_signal response signal_id should equal "<segment_id>"
    And the activation_details status should equal "processing"
    And the activation_details estimated_activation_duration_minutes should equal 15.0
    And the activation_details decisioning_platform_segment_id should start with "seg_<segment_id>_"

    Examples:
      | segment_id                |
      | auto_intenders_q1_2025    |
      | sports_content            |
      | luxury_travel_enthusiasts |

    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/specialisms/signal-marketplace/index.yaml
    #         phase=platform_activation step=activate_on_platform lines=330-359
    #         (NOT on our conformance path — we do not declare the signal_marketplace specialism)
```

The two sibling scenarios `@T-UC-008-storyboard-activate-agent-destination` and
`@T-UC-008-storyboard-activate-platform-destination` (lines 1130-1155) should be **deleted or
retagged `@schema-v3.1` and left unwired** — they cite the same wrong path, assert `deployments`
that do not exist, and specify `destinations` the wrapper cannot accept. That is a lead decision;
I have not proposed replacement Gherkin for them.

---

## 6. Step inventory

**Existing and reusable: essentially none.** There is no signals domain step module
(`tests/bdd/steps/domain/` has no `uc008*.py`) and no signals harness env
(`tests/harness/` — nothing signals-related; the only `signal` hits in `tests/bdd/` are the
unrelated string `"signals"` as a task-query *domain* value in
`uc002_task_query.py:100` and `uc002_create_media_buy.py:1170`).

| Step | Status |
|---|---|
| `Given the Buyer Agent is authenticated for the default tenant` | **Existing pattern** — an auth given of this shape lives in `tests/bdd/steps/generic/given_auth.py`; exact phrasing must be matched to the module before use. |
| `When the Buyer Agent calls get_signals with signal_spec "{spec}"` | **NEW** |
| `Then the get_signals response should carry exactly {n:d} signal entries` | **NEW** |
| `Then the first signal's signal_agent_segment_id should equal "{v}"` | **NEW** |
| `Then the first signal's signal_id.source should equal "{v}"` | **NEW** |
| `Then the first signal's signal_id.id should equal "{v}"` | **NEW** |
| `Then the first signal's pricing_options should carry exactly {n:d} entries` | **NEW** |
| `Then the first signal's first pricing_option_id should equal "{v}"` | **NEW** |
| `Then the first signal's first pricing_option model should equal "{v}"` | **NEW** |
| `Then the first signal's first pricing_option currency should equal "{v}"` | **NEW** |
| `Then the get_signals response message should equal "{v}"` | **NEW** |
| `Given the Buyer Agent captured signal_agent_segment_id "{v}" from get_signals` | **NEW** |
| `When the Buyer Agent calls activate_signal with the captured signal_agent_segment_id` | **NEW** |
| `Then the activate_signal response signal_id should equal "{v}"` | **NEW** |
| `Then the activation_details status should equal "{v}"` | **NEW** |
| `Then the activation_details estimated_activation_duration_minutes should equal {v:f}` | **NEW** |
| `Then the activation_details decisioning_platform_segment_id should start with "{v}"` | **NEW** |

All `When` steps must route through `dispatch_request` (`tests/bdd/steps/generic/_dispatch.py:14`)
so the same Gherkin runs across MCP / A2A / REST / e2e_rest with no transport branching. That
requires a new harness env — ticket T1. No step above branches on transport.

---

## 7. TICKET MATERIAL

- **T1 — No BDD harness env for the signals protocol; BR-UC-008 has never executed.**
  There is no `scenarios("features/BR-UC-008-manage-audience-signals.feature")` binding in
  `tests/bdd/`, no `tests/bdd/steps/domain/uc008*.py`, and no signals module in `tests/harness/`
  (cf. `tests/harness/product.py`, `creative_list.py` for the pattern). All ~40 scenarios in that
  feature file — including 3 tagged `@storyboard-v3.1` — are dormant. Build a `tests/harness/
  signals.py` env exposing `get_signals` and `activate_signal` through
  `tests/harness/transport.py` so scenarios dispatch via `dispatch_request`
  (`tests/bdd/steps/generic/_dispatch.py:14`) across all four transports. Mandated by
  `dist/compliance/3.1.1/protocols/signals/index.yaml:129-148` (the graded discovery block) — we
  currently have no way to observe conformance either way.

- **T2 — `get_signals` signal_spec matching is naive substring containment; the 3.1.1 storyboard's
  own sample request returns zero signals.**
  `src/core/tools/signals.py:161-168` does
  `spec_lower not in signal.name.lower() and ... description ... and ... signal_type`. The
  storyboard `sample_request.signal_spec` is `"Adults interested in electric vehicles"`
  (`dist/compliance/3.1.1/protocols/signals/index.yaml:121`), which matches none of the six
  hardcoded signals, so `signals == []` and the graded
  `- check: field_present / path: "signals[0].signal_agent_segment_id"` (lines 132-134) fails.
  `signals/get-signals-response.json` describes `signal_spec` as a natural-language audience
  description; substring containment is not an implementation of that. Blocks any future
  declaration of `supported_protocols: ["signals"]`.

- **T3 — `get_signals` emits only the deprecated `signal_id`; 3.1.1 makes `signal_ref` canonical.**
  `src/core/tools/signals.py:45-55` (`_agent_signal_id`) builds a `SignalId` and every sample signal
  sets `signal_id=` only. At 3.1.1, `signals/get-signals-response.json` marks `signal_id`
  `"deprecated": true` with *"DEPRECATED. Use signal_ref instead"*, and defines `signal_ref`
  (`$ref: /schemas/core/signal-ref.json`) as *"Canonical signal reference for discovery, activation,
  and media-buy targeting."* We emit no `signal_ref` at all. The existing code comment at
  `signals.py:51` already flags this as a follow-up; this is that follow-up.

- **T4 — `ActivateSignalResponse` cannot validate against `activate-signal-response.json`: no
  `deployments`.**
  `src/core/schemas/_base.py:2458-2470` defines `ActivateSignalResponse(SalesAgentBaseModel)` with
  `signal_id` / `activation_details: dict` / `errors` / `context` and deliberately does not extend
  the library type. `git show v3.1.1:static/schemas/source/signals/activate-signal-response.json`
  puts `"required": ["deployments"]` on the `ActivateSignalSuccess` branch of a `oneOf`, with
  `items: {"$ref": "/schemas/core/deployment.json"}`. Our response omits `deployments` entirely, so
  it matches neither branch. The class docstring concedes this ("Library uses structured
  list[Deployment] vs our generic activation_details dict"; "Library enforces atomic success/error;
  we allow both simultaneously" — the schema's error branch carries
  `"not": {"anyOf": [{"required": ["deployments"]}, {"required": ["sandbox"]}]}`, so both-at-once is
  non-conformant). Graded by `specialisms/signal-marketplace/index.yaml:331-347`
  (`response_schema`, `deployments[0].type`, `deployments[0].activation_key`).

- **T5 — `activate_signal` fabricates the two REQUIRED request fields; `destinations` and
  `idempotency_key` are never accepted from the wire.**
  `src/core/tools/signals.py:239-247` hardcodes
  `destinations=[{"type": "platform", "platform": "mock"}]` and
  `idempotency_key=f"activate-{signal_agent_segment_id}".ljust(16, "0")[:255]`. Neither
  `activate_signal` (line 317) nor `activate_signal_raw` (line 366) exposes a `destinations`
  parameter. `signals/activate-signal-request.json` at v3.1.1 requires both; the marketplace
  storyboard's `sample_request` supplies
  `destinations: [{type: platform, platform: pinnacle-dsp, account: agency-123-pd}]` and
  `idempotency_key: "$generate:uuid_v4#..."`
  (`specialisms/signal-marketplace/index.yaml:313-322`). Consequence: the scenarios
  `@T-UC-008-storyboard-activate-agent-destination` and
  `@T-UC-008-storyboard-activate-platform-destination` are not merely red, they are inexpressible.

- **T6 — `_activate_signal_impl` is a pure mock and would fail the 3.1.1 anti-façade check.**
  `src/core/tools/signals.py:279-308` synthesises
  `decisioning_platform_segment_id = f"seg_{signal_agent_segment_id}_{uuid4().hex[:8]}"` and returns
  a fixed `estimated_activation_duration_minutes: 15.0`, with a comment block listing the four
  things a real implementation would do. `specialisms/signal-marketplace/index.yaml:353-359` grades
  `- check: upstream_traffic ... min_count: 1, endpoint_pattern: "POST *"` with the explicit
  rationale *"An adapter returning a fabricated activation_key without touching the DSP fails this
  check."* Blocks declaring the `signal_marketplace` specialism.

- **T7 — `get_signals` / `activate_signal` responses carry no top-level `status`.**
  `GetSignalsResponse` (`src/core/schemas/_base.py:2408`) and `ActivateSignalResponse`
  (`:2458`) emit no `status`. Both response schemas `allOf`-compose
  `/schemas/core/protocol-envelope.json`, whose description states: *"The `status` field is REQUIRED
  on every task response envelope... Agents shipping responses without a top-level `status` are
  non-conformant regardless of whether the task body schema would otherwise validate."* Graded by
  the `- check: response_schema` entry at
  `dist/compliance/3.1.1/protocols/signals/index.yaml:130-131`. This is the known repo-wide envelope
  gap from the brief — filing the signals instance for completeness, fold into the existing issue.

- **T8 — Decide and record whether the signals protocol is on our conformance path at all.**
  `src/core/tools/capabilities.py:271-272` declares `supported_protocols=[media_buy]` and
  `specialisms=[sales_non_guaranteed]`, yet `get_signals` and `activate_signal` are registered tools.
  The comment at `capabilities.py:256-265` documents a deliberate policy of declaring a specialism
  even with known gaps, to force prioritisation — that policy has not been applied to signals either
  way. Either declare `signals` and fix T2/T3/T7 (baseline) plus T4/T5/T6 (marketplace specialism),
  or record that signals is intentionally undeclared and retag all `@storyboard-v3.1` scenarios in
  BR-UC-008 to `@schema-v3.1`. Related but out of scope here, flagged by the lead: the capabilities
  emitter and the AgentCard disagree about advertising `get_signals`.

---

## 8. Risks

- **Nothing here was verified by execution.** The feature file has no step definitions, no
  `scenarios()` binding, and no harness env, so I could not run a single assertion. Every "green"
  claim in §5 is derived by reading `src/core/tools/signals.py` and `src/core/schemas/_base.py`, not
  observed. The proposed Gherkin's expected values (counts of 4 / 2 / 1, `cpm_usd`, `seg_<id>_`
  prefix, the 15.0 duration, the `"No signals found matching your criteria."` message from
  `_base.py:2419-2426`) must be confirmed against a real run once T1 lands.
- **The `count` column in the discovery Examples table is coupled to a hardcoded six-signal sample
  list** (`signals.py:89-156`). Any edit to that list silently changes the expected counts. That is
  a real characterization risk, but the alternative — asserting only existence — is banned by
  `test_architecture_bdd_no_trivial_assertions.py`. If the lead prefers, the counts can be dropped
  in favour of the per-field equality assertions alone, which are stable against list growth as long
  as ordering holds.
- **The `@known-gap` characterization scenario is deliberately pinned to broken behaviour.** When T2
  lands, that scenario goes red and must be updated. I judged visible-and-pinned better than
  invisible, but it is a defensible call either way and the lead may prefer to move it entirely into
  T2 and drop the scenario.
- **I did not verify how the compliance runner gates protocol-tier storyboards.** My conclusion that
  `signals_baseline` is off our path rests on the storyboard's own narrative
  (`protocols/signals/index.yaml:31-33`) plus `dist/compliance/3.1.1/index.json` listing signals as a
  distinct protocol entry with `has_baseline: true`. The existing repo comment at
  `capabilities.py:259` asserts "the runner gates scenarios by specialism, not by
  `supported_protocols` alone" — which, read strictly, could mean protocol baselines are gated by
  something other than `supported_protocols`. I could not find runner source to settle it. If
  protocol baselines turn out to be ungated, the verdict weakens from "undeclared gate" to "wrong
  tier" — but the tag is still unjustified, because the activation half is genuinely not in
  `signals_baseline` at 3.1.1 (reason 2 in §1 stands independently).
- **Renaming the two new scenarios adds `@T-UC-…` identifiers not present in
  `docs/test-obligations/bdd-traceability.yaml`.** The original opaque tag
  `T-UC-008-storyboard-baseline-end-to-end` is preserved (traceability entry at
  `bdd-traceability.yaml:5745`), but `T-UC-008-baseline-spec-no-semantic-match` and
  `T-UC-008-baseline-segment-id-roundtrip` would need new entries. I did not edit that file.
- **3.1.8 / HEAD drift not assessed.** I read only `v3.1.1` and the on-disk
  `dist/compliance/3.1.1/` tree, per the brief. `signal_ref` supplanting `signal_id` is already in
  motion at 3.1.1 and will likely harden later; T3 should be sized with that in mind.

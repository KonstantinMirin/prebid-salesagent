# Re-pin: `@T-UC-008-storyboard-activate-platform-destination`

Scenario: "Signals baseline activation -- platform destination returns activation_key of type segment_id"
File: `/Users/konst/projects/salesagent-sbsweep/tests/bdd/features/BR-UC-008-manage-audience-signals.feature:1143-1154` (end of file; **no `@source` footer**)

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** Triple-gated, and every gate is closed for us.

1. **Wrong storyboard entirely.** The scenario's prose claims `signals_baseline`. At 3.1.1, `signals_baseline` (`protocols/signals/index.yaml`, 148 lines) has exactly **two phases** — `capability_discovery` and `discovery` — and **no activation phase at all**. `activate_signal` does not appear anywhere in that file. The behaviour is graded only in the **`signal-marketplace` specialism**.
2. **Specialism not declared.** `src/core/tools/capabilities.py:99-100,271-272` declares `specialisms=[AdcpSpecialism.sales_non_guaranteed]`. `signal-marketplace` is not declared.
3. **Protocol not declared.** Same lines declare `supported_protocols=[SupportedProtocol.media_buy]`. `signals` is not declared. The `signal-marketplace` storyboard's own capability step grades `field_contains supported_protocols[*] == "signals"` and `field_contains specialisms[*] == "signal-marketplace"` (`specialisms/signal-marketplace/index.yaml:86-93`) — we fail both, so the runner never reaches `platform_activation`.

The universal-tier signals storyboards do not rescue it either: `universal/schema-validation-signals.yaml:6-8` gates on `required_tools: [get_signals]` and mentions `activate_signal` **only in narrative prose** (line 19); `universal/error-compliance-signals.yaml:7-9` gates on `required_tools: [get_signals, activate_signal]` and grades error paths, not the platform happy path.

Beyond the conformance gate, **the tool is not reachable at all in production.** `get_signals` / `activate_signal` in `src/core/tools/signals.py` are registered on **no transport** — they appear in neither `src/core/main.py`, `src/routes/api_v1.py`, nor the A2A server. We are a signals *consumer* (`src/core/signals_agent_registry.py` calls out to external signal agents), not a signals *provider*. `docs/V2_ROADMAP_SUGGESTION.md` records UC-008 as "Dead code, deregistered (#1003)".

→ `@storyboard-v3.1` must become **`@schema-v3.1`**. Keep `@T-UC-008-storyboard-activate-platform-destination` (referenced from `docs/test-obligations/bdd-traceability.yaml:5757`).

**The whole feature file is dormant.** No `scenarios()` call anywhere in `tests/bdd/` binds `BR-UC-008-manage-audience-signals.feature`, and there is no `tests/bdd/steps/domain/uc008_*.py`. Zero UC-008 scenarios execute. This is the same posture as `BR-UC-013`, whose scenarios already carry `@schema-v3.1` — so the retag puts UC-008 in a bucket the repo already recognises.

---

## 2. Real binding at 3.1.1

### What the footer points at
Nothing — the scenario has **no `@source` footer**. Its two immediate siblings (`@T-UC-008-storyboard-baseline-end-to-end` at :1110, `@T-UC-008-storyboard-activate-agent-destination` at :1127) both cite:

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/signals/index.yaml
```

That citation is doubly wrong and my scenario would inherit the error if derived from the neighbours: `04f59d2d5` is an ancestor of beta.3 (older than our own pin), **and** `protocols/signals/index.yaml` contains no activation phase at 3.1.1.

### The real location

`/Users/konst/projects/adcp/dist/compliance/3.1.1/specialisms/signal-marketplace/index.yaml`
- phase `platform_activation` — **line 279**
- step `activate_on_platform` — **line 290**
- `validations:` — **lines 330-363**

Graded `validations:` block, verbatim:

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
          # Anti-façade: a real activation calls the DSP's segment-deployment
          # endpoint with the captured signal_agent_segment_id. An adapter
          # returning a fabricated activation_key without touching the DSP
          # fails this check. The since: search_by_spec window scopes the
          # assertion to traffic caused after this storyboard captured the
          # signal IDs, ignoring earlier discovery traffic.
          - check: upstream_traffic
            description: "activate_on_platform caused upstream traffic to a DSP carrying the signal_agent_segment_id"
            min_count: 1
            endpoint_pattern: "POST *"
            since: search_by_spec
            identifier_paths:
              - "signal_agent_segment_id"
```

### The scenario's headline claim is prose-only

The scenario title asserts "returns activation_key **of type segment_id**". `activation_key.type == "segment_id"` appears **only** under `expected:` (line 311, `- activation_key with type: "segment_id" and a platform-native segment ID`) — narrative prose. The graded checks require `activation_key` to be **present**, and say nothing about its discriminator. Per the brief's rule 2, that specific claim is ungraded even for an agent that *does* declare the specialism.

The `is_live` story is also inverted relative to the scenario. `expected:` (lines 303-311) says the platform path is **async first** — `is_live: false` initially with `estimated_activation_duration_minutes`, then `is_live: true` with `activation_key` + `deployed_at` after polling. The scenario treats live as the primary case and async as an afterthought ("may report").

Note `domains/signals/index.yaml` is byte-identical to `protocols/signals/index.yaml` (verified with `diff`) — no alternative binding hides there.

---

## 3. Schema constraints at 3.1.1

All via `cd /Users/konst/projects/adcp && git show v3.1.1:static/schemas/source/<path>`.

### `signals/activate-signal-request.json`

```json
  "required": [
    "idempotency_key",
    "signal_agent_segment_id",
    "destinations"
  ],
```
```json
    "destinations": {
      "type": "array",
      "description": "Target destination(s) for activation. If the authenticated caller matches one of these destinations, activation keys will be included in the response.",
      "items": { "$ref": "/schemas/core/destination.json" },
      "minItems": 1
    },
    "pricing_option_id": {
      "type": "string",
      "description": "The pricing option selected from the signal's pricing_options in the get_signals response. Required when the signal has pricing options. ...",
      "x-entity": "vendor_pricing_option"
    },
    "idempotency_key": {
      "type": "string",
      "minLength": 16,
      "maxLength": 255,
      "pattern": "^[A-Za-z0-9_.:-]{16,255}$"
    },
    "action": { "type": "string", "enum": ["activate", "deactivate"], "default": "activate" }
```

### `signals/activate-signal-response.json`

```json
  "allOf": [
    { "$ref": "/schemas/core/version-envelope.json" },
    { "$ref": "/schemas/core/protocol-envelope.json" }
  ],
  "oneOf": [
    { "title": "ActivateSignalSuccess", ...
      "required": ["deployments"],
      "not": { "required": ["errors"] } },
    { "title": "ActivateSignalError", ...
      "required": ["errors"],
      "not": { "anyOf": [{"required": ["deployments"]}, {"required": ["sandbox"]}] } }
  ]
```

Two hard constraints: the success branch **requires `deployments`**, and success/error are **mutually exclusive** ("Returns either complete success data OR error information, never both").

### `core/destination.json` — platform variant

```json
      "properties": {
        "type": { "const": "platform" },
        "platform": { "type": "string", "description": "Platform identifier for DSPs (e.g., 'the-trade-desk', 'amazon-dsp')" },
        "account": { "type": "string", "description": "Optional account identifier on the platform" }
      },
      "required": ["type", "platform"]
```

### `core/deployment.json` — platform variant

```json
      "required": [
        "type",
        "platform",
        "is_live"
      ],
```
```json
        "activation_key": {
          "$ref": "/schemas/core/activation-key.json",
          "description": "The key to use for targeting. Only present if is_live=true AND requester has access to this deployment."
        },
        "estimated_activation_duration_minutes": {
          "type": "number",
          "description": "Estimated time to activate if not live, or to complete activation if in progress",
          "minimum": 0
        },
        "deployed_at": { "type": "string", "format": "date-time",
          "description": "Timestamp when activation completed (if is_live=true)" }
```

`is_live` is **required**; `activation_key` is conditional on `is_live=true`. `discriminator.propertyName: "type"`.

### `core/activation-key.json`

```json
      "properties": {
        "type": { "type": "string", "const": "segment_id" },
        "segment_id": { "type": "string", "description": "The platform-specific segment identifier to use in campaign targeting" }
      },
      "required": ["type", "segment_id"]
```
(second variant: `const: "key_value"`, `required: ["type", "key", "value"]`)

### `core/protocol-envelope.json`

```json
  "required": [ "status" ],
```
> "The `status` field is REQUIRED on every task response envelope … Agents shipping responses without a top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate."

---

## 4. Conflicts

**Schema overrode storyboard — stated explicitly, per the brief.**

- The storyboard's graded checks stop at `field_present deployments[0].activation_key`. The **schema** goes further and is authoritative: `deployment.json` makes `activation_key` conditional on `is_live=true`, and `activation-key.json` fixes the discriminator to `segment_id` | `key_value` with per-variant required fields. Where the two differ in strength, I take the schema — so the rewrite asserts `activation_key.type` **only on the `is_live: true` row**, and asserts its **absence** on the async row. The storyboard would (incorrectly, given its own `expected:` narrative of an async-first platform path) demand `activation_key` present on a `is_live: false` first response; the schema says it must not be there. **Schema wins.**
- `deployment.json` requires `is_live`; the storyboard never grades it. Schema wins — the rewrite asserts it as a concrete boolean per row.
- `activate-signal-response.json` requires `deployments` and forbids `errors` alongside it; the storyboard grades neither. Schema wins.

**What the scenario gets wrong or asserts vacuously.**

| Line | Current text | Problem |
|---|---|---|
| :1150 | `And the deployments array should carry at least one entry whose type is "platform"` | "at least one entry" is an existence check on an array the request pins to exactly one destination. Not a value comparison in the sense the guards want. |
| :1151 | `And a live deployment should carry an activation_key with type "segment_id"` | Conditional on an antecedent the scenario never establishes — nothing sets `is_live`. If no deployment is live, the step is vacuously true. Also the `segment_id` claim is prose-only in the storyboard (§2). |
| :1152 | `And an async deployment may report is_live false with estimated_activation_duration_minutes` | **"may"** — asserts nothing at all. This is exactly the shape `test_architecture_bdd_no_trivial_assertions.py` exists to reject. |
| :1145 | Given "holds a signal_agent_segment_id and pricing_option_id" | No concrete values, so nothing downstream can compare against captured identity. |
| :1146 | When … `destinations of type "platform" …` | Omits `idempotency_key`, which 3.1.1 makes **REQUIRED** on the request. |
| footer | (none) | No `@source` at all. |
| tag | `@storyboard-v3.1` | Unjustified — see §1. |

**What it misses:** `is_live` as a required field; `deployed_at` on the live path; the success/error mutual exclusion; the `platform` and `account` echo (the requested `the-trade-desk` / `agency-123-ttd` never get compared to what came back); the top-level `status` envelope field.

---

## 5. Proposed Gherkin

Replaces `tests/bdd/features/BR-UC-008-manage-audience-signals.feature:1143-1154` verbatim.

**Green because the feature file is dormant** — no `scenarios()` binding, no `uc008_*.py` step module, so no step in this block executes today. It must **stay** dormant until the TICKET MATERIAL below lands; wiring it as-is would go red immediately (production returns no `deployments` at all). I have deliberately *not* softened the assertions to match today's non-conformant output — codifying `activation_details.decisioning_platform_segment_id` as if it were the contract would make the drift permanent.

```gherkin
  @T-UC-008-storyboard-activate-platform-destination @schema-v3.1 @v3-1 @activation @platform-destination
  Scenario Outline: activate_signal platform destination -- deployment record shape by activation mode
    Given the Buyer Agent holds signal_agent_segment_id "auto_intenders_q1_2025" and pricing_option_id "cpm_usd"
    And the seller's platform activation for "the-trade-desk" resolves <mode>
    When the Buyer Agent sends activate_signal with idempotency_key "uc008-platform-dest-0001" and one destination of type "platform", platform "the-trade-desk", account "agency-123-ttd"
    Then the response should be schema-valid against activate-signal-response.json
    And the response should carry exactly 1 deployment
    And deployment 1 field "type" should equal "platform"
    And deployment 1 field "platform" should equal "the-trade-desk"
    And deployment 1 field "account" should equal "agency-123-ttd"
    And deployment 1 field "is_live" should equal <is_live>
    And deployment 1 field "activation_key.type" should equal <activation_key_type>
    And deployment 1 field "estimated_activation_duration_minutes" should equal <estimated_minutes>
    And the response should carry no errors array

    # 3.1.1 core/deployment.json requires ["type", "platform", "is_live"] on the platform
    # variant. activation_key is conditional -- "Only present if is_live=true AND requester
    # has access to this deployment" -- so the async row asserts its ABSENCE, not its shape.
    # core/activation-key.json fixes the discriminator to segment_id | key_value; the
    # platform path uses segment_id (platform-native segment identifier).
    # signals/activate-signal-response.json requires "deployments" on the success branch and
    # forbids "errors" alongside it (atomic success-or-error semantics).
    # NOT on our conformance path: this behaviour is graded only under the signal-marketplace
    # SPECIALISM, and capabilities.py declares specialisms=[sales_non_guaranteed] and
    # supported_protocols=[media_buy] -- hence @schema-v3.1, not @storyboard-v3.1.
    # activation_key.type == "segment_id" is storyboard PROSE (expected:), not a graded
    # validation; it is asserted here on the 3.1.1 activation-key.json schema authority.
    # @source repo=adcp ref=v3.1.1 path=dist/compliance/3.1.1/specialisms/signal-marketplace/index.yaml phase=platform_activation step=activate_on_platform
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/deployment.json
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/activation-key.json

    Examples: activation modes
      | mode           | is_live | activation_key_type | estimated_minutes |
      | synchronously  | true    | "segment_id"        | null              |
      | asynchronously | false   | null                | 15                |
```

Design notes:
- Every Then compares a concrete value. `null` in a cell is a literal, parsed by the step, meaning "the JSON pointer resolves to nothing" — an absence assertion, not truthiness. No `may`, no `at least one`.
- The two rows carry the live/async split the current scenario conflated into one vacuous `may` line, and encode the storyboard's own `expected:` narrative (async first, live after polling) as two distinct observable shapes.
- `idempotency_key "uc008-platform-dest-0001"` is 24 chars and matches `^[A-Za-z0-9_.:-]{16,255}$`.
- Transport-independent: no MCP/A2A/REST branching. The two `@source` schema lines are supplementary; the first is the storyboard binding.
- Top-level `status` is deliberately **not** asserted — known production gap, see TICKET MATERIAL.

---

## 6. Step inventory

**Existing — reusable as-is:** none. There is no `tests/bdd/steps/domain/uc008_*.py` module; UC-008 has zero step definitions.

**Existing — near-miss, not reusable:**
- `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101` — `@then("the response should be schema-valid against list-creative-formats-response.json")`. Hardcoded filename, and (per the brief) its body only checks `isinstance(formats, list)` — it never calls `tests/helpers/pinned_schema.py::validate_against_pinned_schema`. A parametrized `should be schema-valid against {filename}` step does not exist.
- `tests/bdd/steps/generic/then_success.py:100` — `@then(parsers.parse('the response should contain "{field}" array'))`. Existence only; too weak for deployment-field comparison.

**New phrasings required (5 Given/When/Then + 1 outline-parametrized family):**

| Phrasing | Kind |
|---|---|
| `the Buyer Agent holds signal_agent_segment_id "{sid}" and pricing_option_id "{pid}"` | Given — new |
| `the seller's platform activation for "{platform}" resolves {mode}` | Given — new |
| `the Buyer Agent sends activate_signal with idempotency_key "{key}" and one destination of type "platform", platform "{platform}", account "{account}"` | When — new |
| `the response should be schema-valid against {filename}` | Then — new (parametrized; must actually call `validate_against_pinned_schema`) |
| `the response should carry exactly {n:d} deployment` | Then — new |
| `deployment {index:d} field "{path}" should equal {expected}` | Then — new; `expected` parsed as a JSON literal, `null` ⇒ assert the dotted path is absent |
| `the response should carry no errors array` | Then — new (encodes the schema's `not: {required: ["errors"]}`) |

None of these should be written until the production gaps below are closed — writing steps against a tool that is not registered on any transport produces exactly the dormant-scenario anti-pattern this sweep is trying to remove.

---

## 7. TICKET MATERIAL

- **`activate_signal` returns no `deployments` array — the response model has no such field.** `src/core/schemas/_base.py:2458-2471` defines `ActivateSignalResponse` with `signal_id: str` + `activation_details: dict[str, Any] | None` and a docstring stating it was deliberately **not** migrated to the library base ("Library uses structured `list[Deployment]` vs our generic `activation_details` dict"; "Library enforces atomic success/error; we allow both simultaneously"). `src/core/tools/signals.py:299-308` populates `activation_details={"decisioning_platform_segment_id": ..., "estimated_activation_duration_minutes": 15.0, "status": "processing"}`. 3.1.1 `signals/activate-signal-response.json` `required: ["deployments"]` on the success branch, items `$ref /schemas/core/deployment.json`; the same schema's `not: {required: ["errors"]}` forbids the simultaneous success+error our model permits. Every one of the storyboard's `deployments[0].*` checks is unsatisfiable today.

- **The transport wrapper discards the caller's `destinations` and synthesises a fake `idempotency_key`.** `src/core/tools/signals.py:239-247` hardcodes `destinations=[{"type": "platform", "platform": "mock"}]` and `idempotency_key=f"activate-{signal_agent_segment_id}".ljust(16, "0")[:255]`; `activate_signal` / `activate_signal_raw` (`:317-323`, `:366-373`) accept only `signal_agent_segment_id`, `campaign_id`, `media_buy_id`, `context`. 3.1.1 `signals/activate-signal-request.json` `required: ["idempotency_key", "signal_agent_segment_id", "destinations"]`, `destinations.minItems: 1`. A wire-supplied `the-trade-desk` destination can never reach `_impl` — Pattern #5 boundary-completeness violation (the wrapper does not forward parameters the schema mandates). `pricing_option_id` is likewise unrepresented.

- **`activate_signal` and `get_signals` are registered on no transport.** Neither appears in `src/core/main.py`, `src/routes/api_v1.py`, nor the A2A server; the only production references are the outbound consumer path `src/core/signals_agent_registry.py` and `src/services/dynamic_products.py`. `docs/V2_ROADMAP_SUGGESTION.md` records UC-008 as "Dead code, deregistered (#1003)". Decide explicitly: either implement the signals *provider* surface against 3.1.1 `signals/*`, or delete `src/core/tools/signals.py` and retire `BR-UC-008-manage-audience-signals.feature`. Leaving an unregistered mock plus a dormant 1154-line feature file is the worst of the three.

- **`tests/fixtures/adcp_schemas_pinned/core/activation-key.json` is missing, breaking the `$ref` closure.** `tests/fixtures/adcp_schemas_pinned/core/deployment.json` `$ref`s `/schemas/core/activation-key.json`, but that file is not vendored (`ls tests/fixtures/adcp_schemas_pinned/core/ | grep activation` → empty). `tests/helpers/pinned_schema.py:36-40` treats a missing ref as a **hard failure**, so `validate_against_pinned_schema("activate-signal-response.json", ...)` raises `AssertionError: Pinned schema not vendored` the moment a `deployments[]` entry is validated — before any real conformance check runs. Re-run `tests/fixtures/adcp_schemas_pinned/_refresh.py`.

- **The vendored `activate-signal-response.json` predates the `protocol-envelope` requirement.** `tests/fixtures/adcp_schemas_pinned/signals/activate-signal-response.json` has `allOf: [{"$ref": "/schemas/core/version-envelope.json"}]` only; 3.1.1 adds `{"$ref": "/schemas/core/protocol-envelope.json"}` whose `required: ["status"]` is normative ("Agents shipping responses without a top-level `status` are non-conformant regardless of whether the task body schema would otherwise validate"). Validating against the vendored copy silently passes responses that 3.1.1 rejects. Same root cause as the repo-wide `04f59d2d5` fixture pin noted in the brief.

- **`_activate_signal_impl` fabricates the activation key without any upstream call — the exact anti-façade case the storyboard grades.** `src/core/tools/signals.py:298` builds `decisioning_platform_segment_id = f"seg_{signal_agent_segment_id}_{uuid.uuid4().hex[:8]}"` with no HTTP call to any DSP. `specialisms/signal-marketplace/index.yaml:357-363` grades `check: upstream_traffic` with `min_count: 1`, `endpoint_pattern: "POST *"`, `identifier_paths: ["signal_agent_segment_id"]`, commented "An adapter returning a fabricated activation_key without touching the DSP fails this check." File this even if the specialism is never declared — it documents that the current implementation is a façade, not an implementation.

- **`then_response_schema_valid` runs no validator.** `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-108` asserts `isinstance(formats, list)` while `tests/helpers/pinned_schema.py::validate_against_pinned_schema` sits unused. Any new `should be schema-valid against {filename}` step must call the real validator; the existing step should be migrated to it. (Already known per the brief — cross-referenced here because the proposed Gherkin depends on it.)

- **`BR-UC-008-manage-audience-signals.feature` (1154 lines) is bound by no `scenarios()` call.** No `tests/bdd/test_uc008_*.py`, no `tests/bdd/steps/domain/uc008_*.py`. All UC-008 rows in `docs/test-obligations/bdd-traceability.yaml` (including `:5757`) claim traceability to scenarios that never execute. Either wire the file or mark the traceability rows as unbound — a traceability index that points at dead scenarios is worse than no index.

---

## 8. Risks

- **The proposed Gherkin is green only because the block is dead code.** Nothing in the feature file executes. I did not run pytest to prove this — I proved it structurally (no `scenarios()` reference to the file, no `uc008` step module). If a `scenarios()` binding is added in a parallel branch, this scenario goes red on the first Then, because production emits no `deployments`. That is the honest state, and §7 is the price of making it green for real.
- I could not verify anything by execution: the tool is unregistered on all transports, so there is no wire response to inspect and no way to confirm what a conformant serialization would look like here.
- **Judgment call I'd flag for review:** I asserted `activation_key.type == "segment_id"` on the live row on **schema** authority (`core/activation-key.json`) even though the storyboard grades only `field_present`. The storyboard's `expected:` prose says the same thing, so the two agree in substance — but a strict reading of the brief's rule 2 would drop the `.type` assertion and keep only presence. I kept it because the platform path has no plausible `key_value` reading and the scenario title turns on it.
- **`estimated_minutes: 15`** on the async row is a guess at a concrete value. Neither the 3.1.1 schema nor the storyboard fixes a number (`minimum: 0` only); `src/core/tools/signals.py:303` happens to use `15.0`. If a step author prefers, assert `>= 0` via a dedicated comparison step rather than a literal — but that weakens the row. Worth a second opinion.
- Drift note, not authority: I read only `v3.1.1` and `dist/compliance/3.1.1/`. I did not check whether 3.1.8 or HEAD moves `platform_activation` back into a baseline tier or changes the `activation_key` conditionality.
- I did not verify whether the compliance runner gates specialism storyboards on the *declared* `specialisms[]` alone or also on `required_tools` reachability. Either way the conclusion holds — we declare neither `signals` nor `signal-marketplace`, and expose neither tool — but the precise gating mechanism is unconfirmed. `src/core/tools/capabilities.py:256-259` carries a comment asserting "The runner gates scenarios by specialism, not by `supported_protocols` alone," which is consistent with but not proof of my reading.

# Re-pin: `T-UC-008-storyboard-activate-agent-destination`

Scenario: `tests/bdd/features/BR-UC-008-manage-audience-signals.feature:1128-1141`
Title: "Signals baseline activation -- agent destination type returns schema-valid deployment"
Repo under audit: `/Users/konst/projects/salesagent-sbsweep` @ `test/storyboard-binding-baseline`

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** Three independent reasons, each sufficient on its own:

1. **The cited storyboard does not grade this behaviour at all.** The footer points at
   `protocols/signals/index.yaml`. At 3.1.1 that file has exactly two phases —
   `capability_discovery` and `discovery` — and **zero** activation steps. It explicitly
   disclaims activation in prose (lines 19-23, 93-95). There is no `activate_signal` task,
   no `deployments` validation, nothing about destination types anywhere in the file.
2. **The behaviour is graded, but under a specialism we do not declare.** Its real home is
   `specialisms/signal-marketplace/index.yaml`, phase `agent_activation`, step
   `activate_on_agent`. That is the `specialisms/` tier — capability-gated on **both** the
   `signals` protocol and the `signal-marketplace` specialism. We declare
   `supported_protocols=[media_buy]` and `specialisms=[sales_non_guaranteed]`
   (`src/core/tools/capabilities.py:99-100`, `:271-272`). Neither gate is declared.
3. **The tool does not exist on any transport.** Signals tools were deliberately removed
   from the sales agent. `src/core/tools/__init__.py:25`:
   `# Signals tools removed - should come from dedicated signals agents, not sales agent`
   Same decision recorded at `src/a2a_server/adcp_a2a_server.py:89, 1484, 1819, 2318`.
   `activate_signal` is registered on **neither MCP, nor A2A, nor REST** — the only
   references to it anywhere in `src/` are inside `src/core/tools/signals.py` itself, which
   nothing imports.

The tag must become `@schema-v3.1`. The opaque `@T-UC-008-storyboard-activate-agent-destination`
identifier stays (referenced from `docs/test-obligations/bdd-traceability.yaml:5751`).

**Correction to the mechanical baseline.** `docs/test-obligations/storyboard-binding-baseline.md:39`
classifies this scenario as **Bucket B** ("stale ref only"). That is wrong — the mechanical
check only compared the ref string. It is **Bucket C**: the cited path grades nothing, and the
real binding sits behind a gate we do not declare. Sibling
`T-UC-008-storyboard-baseline-end-to-end` (line 1112, also Bucket B) inherits reason (1) and
(3) identically and should be re-triaged the same way, as should
`T-UC-008-storyboard-activate-platform-destination` (line 1143, Bucket C for a different
reason — no footer at all).

---

## 2. Real binding at 3.1.1

**Correct location:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/specialisms/signal-marketplace/index.yaml`
— phase `agent_activation` (line 364), step `activate_on_agent` (line 376).

The **graded** block, verbatim (lines 416-433):

```yaml
        validations:
          - check: response_schema
            description: "Response matches activate-signal-response.json schema"
          - check: field_present
            path: "deployments[0].activation_key"
            description: "Deployment includes activation key"
          - check: field_value
            path: "deployments[0].type"
            value: "agent"
            description: "Deployment type is 'agent'"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "signal_marketplace--activate_on_agent"
            description: "Context correlation_id returned unchanged"
```

Note what is graded and what is **not**. `is_live: true`, `activation_key.type == "key_value"`,
and `deployed_at` appear **only** under `expected:` (lines 388-398) — narrative prose, ungraded.
Our scenario's Then #3 ("a live deployment should carry an activation_key") and Then #4
("an async deployment may carry is_live false with estimated_activation_duration_minutes") are
both drawn from that prose, not from any `- check:`. Even if we declared the specialism, those
two lines would be ungraded.

**Provenance of the current scenario is not in doubt.** The `agent_url`
`"https://wonderstruck.salesagents.example"` in the When step is copied verbatim from the
`activate_on_agent` `sample_request` (line 409). The scenario was authored from the
signal-marketplace specialism and then footered against the signals *protocol baseline*.

**What the footer wrongly points at:**
`static/compliance/source/protocols/signals/index.yaml` @ `ref=v3.1-04f59d2d5 commit=04f59d2d5`.
Two defects:
- `04f59d2d5` is an ancestor of `v3.1.0-beta.3`, i.e. **older** than our own 3.1.1 pin.
- The file grades no activation at any version I can see at 3.1.1. Verbatim, the whole of
  `protocols/signals/index.yaml` phases (lines 49-148) is `capability_discovery` →
  `get_capabilities` and `discovery` → `search_signals`. Its narrative (lines 19-23) says:

  > This baseline tests those calls and nothing beyond them. Specialism
  > storyboards (signal-owned, signal-marketplace) exercise the richer flows
  > specific to each model — pricing option selection, source/provenance
  > discriminators, and, for marketplace signal agents, activation/deactivation
  > on downstream destinations.

  and again at lines 93-95:

  > Every signals agent — owned or marketplace — must return a schema-valid
  > response. Activation-specific obligations live in specialisms that
  > require activation, such as signal_marketplace.

  This is not an off-by-one to the next scenario's storyboard (the pattern found in 16 of 40).
  It is a tier error: specialism content footered against the protocol baseline.

I also checked the other signals specialism: `specialisms/signal-owned/index.yaml` has phases
`capability_discovery` and `discovery` only (`search_owned_signals`, `filter_by_criteria`) —
no activation. `activate_signal` is graded in exactly one place at 3.1.1: `signal-marketplace`.

**Tier:** `specialisms/` — capability-gated, and gated twice over (`signals` protocol +
`signal-marketplace` specialism, both asserted by the specialism's own `capability_discovery`
step at lines 86-93).

---

## 3. Schema constraints at 3.1.1

### `signals/activate-signal-response.json` — requires `deployments`, and now carries the protocol envelope

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
    {
      "title": "ActivateSignalError",
      "properties": { "errors": { "items": {"$ref": "/schemas/core/error.json"}, "minItems": 1 } },
      "required": ["errors"],
      "not": { "anyOf": [ {"required": ["deployments"]}, {"required": ["sandbox"]} ] }
    }
  ]
```

Two hard constraints: success **requires** `deployments`, and success/error are mutually
exclusive (`not.required`). Via the `protocol-envelope` ref, `status` is also required
(`core/protocol-envelope.json`, `"required": ["status"]`).

### `core/deployment.json` — the agent variant's required set

`git show v3.1.1:static/schemas/source/core/deployment.json`, agent branch:

```json
    {
      "type": "object",
      "properties": {
        "type": { "type": "string", "const": "agent" },
        "agent_url": { "type": "string", "format": "uri" },
        "account": { "type": "string" },
        "is_live": { "type": "boolean" },
        "activation_key": { "$ref": "/schemas/core/activation-key.json",
          "description": "The key to use for targeting. Only present if is_live=true AND requester has access to this deployment." },
        "estimated_activation_duration_minutes": { "type": "number", "minimum": 0 },
        "deployed_at": { "type": "string", "format": "date-time" }
      },
      "required": ["type", "agent_url", "is_live"],
      "additionalProperties": true
    }
```

`required: ["type", "agent_url", "is_live"]`. The scenario currently asserts only `type`.
`agent_url` and `is_live` — both required, both directly observable — go unasserted.

### `core/activation-key.json` — `key_value` needs three fields, not one

```json
    {
      "properties": {
        "type": { "type": "string", "const": "key_value" },
        "key": { "type": "string" },
        "value": { "type": "string" }
      },
      "required": ["type", "key", "value"]
    }
```

The `segment_id` branch requires `["type", "segment_id"]`. The storyboard's prose says agent
activations return `type: "key_value"`; the scenario's "should carry an activation_key" asserts
neither the discriminator nor the payload fields.

### `signals/activate-signal-request.json` — the request the scenario claims to send

```json
  "required": ["idempotency_key", "signal_agent_segment_id", "destinations"],
  "properties": {
    "destinations": { "type": "array", "items": {"$ref": "/schemas/core/destination.json"}, "minItems": 1 },
    "idempotency_key": { "type": "string", "minLength": 16, "maxLength": 255,
                         "pattern": "^[A-Za-z0-9_.:-]{16,255}$" },
    ...
  }
```

and `core/destination.json` agent branch: `"required": ["type", "agent_url"]`.

---

## 4. Conflicts

### Schema vs storyboard

One place they disagree, and **the schema wins**: the storyboard's `activate_on_agent`
`expected:` prose (lines 388-394) promises `is_live: true` and `activation_key` with
`type: "key_value"` on every agent activation. `core/deployment.json` makes `activation_key`
optional and conditions it — *"Only present if is_live=true AND requester has access to this
deployment"* — and `core/activation-key.json` permits either discriminator. So "an agent
deployment always carries a key_value activation_key" is **not** a schema obligation. It is not
a graded one either (§2). Any assertion built on it would be over-specified against the pin.

### What the scenario gets wrong

**a. The footer cites a file that grades nothing.** Covered in §2. Stale ref *and* wrong tier.

**b. Every Then is red against production; none could ever have run.** `ActivateSignalResponse`
(`src/core/schemas/_base.py:2458-2477`) is not derived from the library type and has **no
`deployments` field at all** — its fields are `signal_id`, `activation_details` (a bare
`dict[str, Any]`), `errors`, `context`. Its own docstring concedes the divergence:

> 3. Library uses structured list[Deployment] vs our generic activation_details dict
> 4. Library enforces atomic success/error; we allow both simultaneously

`_activate_signal_impl` (`src/core/tools/signals.py:299-308`) returns
`{signal_id, activation_details: {decisioning_platform_segment_id, estimated_activation_duration_minutes, status}}`.
So Then #1 (schema-valid) fails on `required: ["deployments"]`, and Thens #2-#4 reference a
field that does not exist.

**c. The When step is not expressible on any wire.** The MCP wrapper
(`src/core/tools/signals.py:317-323`) takes `signal_agent_segment_id, campaign_id,
media_buy_id, context, ctx` — there is no `destinations` parameter. `_build_activate_signal_request`
(`:242-243`) **hardcodes** `destinations=[{"type": "platform", "platform": "mock"}]` and
synthesizes `idempotency_key` from the segment id. A buyer cannot request an `agent`
destination, so the scenario's subject is unreachable by construction.

**d. Two of the four Thens are vacuous by grammar.** "a live deployment should carry an
activation_key" and "an async deployment **may** carry is_live false..." are conditionals with
no antecedent binding — they pass on an empty `deployments` array. `may` cannot be asserted at
all. Both would be flagged by `test_architecture_bdd_no_trivial_assertions.py` if steps existed.

**e. There are no steps, and the feature is not wired.** No step matches any of the four Then
phrasings, no step matches the Given or the When, and there is **no `tests/bdd/test_uc008_*.py`**
— `BR-UC-008-manage-audience-signals.feature` is the only file in the repo that mentions itself.
pytest-bdd binds features via explicit `scenarios(...)` calls (18 such files exist; none names
UC-008). The entire 1100+ line feature is dormant: nothing in it executes. The scenario has
never been green or red — it has never run.

**f. Missed assertions even on its own terms.** `agent_url` and `is_live` are required by
`core/deployment.json` and are the two fields that actually distinguish an agent deployment
from a platform one. Neither is asserted. So is `status` (required by the 3.1.1 protocol
envelope) and the success/error exclusivity.

**g. The vendored fixture has already drifted from the pin.**
`tests/fixtures/adcp_schemas_pinned/signals/activate-signal-response.json` differs from
`v3.1.1` by exactly the `core/protocol-envelope.json` `allOf` entry — the vendored copy lacks
it, so it does not require `status`. (`tests/fixtures/adcp_schemas_pinned/core/deployment.json`
is byte-identical to 3.1.1 — I diffed both.) This is the known "vendored at 04f59d2d5"
gap from the brief, now with a concrete instance.

---

## 5. Proposed Gherkin

**Design rationale.** The behaviour is off our conformance path (§1) and unreachable on every
transport (§4c), and there is no harness env for signals or capabilities — `tests/harness/`
has envs for media buys, creatives, products, accounts, delivery, and properties, but none for
`activate_signal` or `get_adcp_capabilities`. So **no dispatching scenario can be green in this
PR**; anything that calls `dispatch_request` requires new env + step infrastructure, which is
ticket material, not baseline material.

What *is* green today is the schema layer: `tests/helpers/pinned_schema.py::validate_against_pinned_schema`
already exists, is already used for real by `tests/bdd/test_uc018_list_creatives.py:217-220`,
needs no env and no transport, and `core/deployment.json` is vendored byte-identical to 3.1.1.
So the replacement pins the 3.1.1 **agent-destination deployment contract** as a schema
obligation — which is precisely what `@schema-v3.1` means in this vocabulary — and it is
transport-independent by construction because it never touches a transport.

This is not a test of `jsonschema`. It is a regression guard on the vendored pin, and §4g proves
that guard has teeth: the sibling `activate-signal-response.json` fixture has *already* silently
drifted from 3.1.1. Encoding the required-field set here means a future re-vendor that changes
the agent-destination contract fails loudly instead of passing quietly.

```gherkin
  # NOT on our conformance path. Agent-destination signal activation is graded only by
  # specialisms/signal-marketplace/index.yaml (phase agent_activation, step activate_on_agent).
  # That is gated on supported_protocols=[signals] + specialisms=[signal-marketplace]; we declare
  # media_buy + sales_non_guaranteed (src/core/tools/capabilities.py:271-272), and signals tools are
  # deliberately absent from every transport (src/core/tools/__init__.py:25). Retagged
  # @storyboard-v3.1 -> @schema-v3.1: what remains binding on us is the 3.1.1 schema shape, which we
  # pin here so a future re-vendor of the fixtures cannot silently change it. See #TBD for the
  # production gap (ActivateSignalResponse has no deployments array) and #TBD for wiring UC-008.
  @T-UC-008-storyboard-activate-agent-destination @schema-v3.1 @v3-1 @activation @agent-destination
  Scenario Outline: AdCP 3.1.1 agent-destination deployment -- required fields per core/deployment.json
    Given the pinned AdCP schema "deployment.json"
    When an agent deployment document is built with type "<type>", agent_url "<agent_url>", and is_live "<is_live>"
    Then the pinned schema validation outcome should be "<outcome>"

    Examples: core/deployment.json requires exactly type, agent_url, is_live on the agent variant
      | type  | agent_url                                  | is_live | outcome  |
      | agent | https://wonderstruck.salesagents.example   | true    | accepted |
      | agent | https://wonderstruck.salesagents.example   | false   | accepted |
      | agent | https://wonderstruck.salesagents.example   | <omit>  | rejected |
      | agent | <omit>                                     | true    | rejected |
      | <omit>| https://wonderstruck.salesagents.example   | true    | rejected |

  # activation_key is OPTIONAL on core/deployment.json and conditioned ("Only present if
  # is_live=true AND requester has access"). The signal-marketplace storyboard's promise of a
  # key_value key on agent activations lives under `expected:` (prose), not under `validations:` --
  # ungraded, and over-specified against the pin. What IS binding is core/activation-key.json's
  # required set per discriminator, pinned here.
  @T-UC-008-schema-activation-key-discriminator @schema-v3.1 @v3-1 @activation @agent-destination
  Scenario Outline: AdCP 3.1.1 activation_key -- required fields per discriminator
    Given the pinned AdCP schema "activation-key.json"
    When an activation_key document is built with type "<type>" and fields "<fields>"
    Then the pinned schema validation outcome should be "<outcome>"

    Examples: core/activation-key.json oneOf branches
      | type       | fields              | outcome  |
      | segment_id | segment_id=seg_9931 | accepted |
      | segment_id | <none>              | rejected |
      | key_value  | key=aud,value=ev    | accepted |
      | key_value  | key=aud             | rejected |
      | key_value  | <none>              | rejected |
```

Both outlines are green today: they read vendored fixtures only, touch no transport, no DB, no
production code path, and every Then compares a concrete value drawn from the Examples table.

**If the reviewer prefers deletion over retention:** the honest alternative is to delete both
UC-008 storyboard-activation scenarios outright and drop their `bdd-traceability.yaml` entries,
on the grounds that a sales agent that will never implement `activate_signal` has no business
carrying scenarios for it. I did not propose that as primary because the brief directs retagging
to `@schema-v3.1` and preserving the `@T-UC-…` identifier. Flagging it as a live option.

---

## 6. Step inventory

**Existing — reused as-is:** none. There is no signals step vocabulary anywhere in
`tests/bdd/steps/` (the only `grep -i signal` hits in that tree are unrelated comments in
`given_media_buy.py:2767,2908` and two `uc002_task_query` domain strings).

**Existing — precedent to follow, not reused verbatim:**

| Phrasing | Location | Why not reused |
|---|---|---|
| `the response should be schema-valid against {schema_file}` | `tests/bdd/test_uc018_list_creatives.py:217` | Real — calls `validate_against_pinned_schema`. But it validates `ctx["response"]`, i.e. presupposes a dispatched call. My scenario validates a constructed document with no dispatch. |
| `the response should be schema-valid against list-creative-formats-response.json` | `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101` | **Do not copy this one.** Its body is `assert isinstance(formats, list)` — the step text claims schema validation and the body performs none. This is the vacuous variant the brief flags; it deserves its own ticket. |

**New — 3 step definitions, all in a new `tests/bdd/steps/domain/uc008_signal_schema.py`:**

| Kind | Phrasing |
|---|---|
| `@given` | `the pinned AdCP schema "{schema_file}"` |
| `@when` | `an agent deployment document is built with type "{type}", agent_url "{agent_url}", and is_live "{is_live}"` |
| `@when` | `an activation_key document is built with type "{type}" and fields "{fields}"` |
| `@then` | `the pinned schema validation outcome should be "{outcome}"` |

The `@then` body is `assert outcome == expected` — a `Compare` node, so it satisfies
`test_architecture_bdd_no_trivial_assertions.py`. The two `@when` bodies differ in what they
construct and share the validate-and-classify tail via one helper, satisfying
`test_architecture_bdd_no_duplicate_steps.py` and the DRY invariant.

**Also required (and currently missing):** `tests/bdd/test_uc008_signals.py` with
`scenarios("features/BR-UC-008-manage-audience-signals.feature")`. **Do not add it in this PR.**
Binding the feature file would activate ~90 other dormant UC-008 scenarios that have no steps
and would all error. Wiring UC-008 is its own ticket (§7).

---

## 7. TICKET MATERIAL

- **`ActivateSignalResponse` is structurally non-conformant with AdCP 3.1.1.**
  `src/core/schemas/_base.py:2458-2477` declares `signal_id` + `activation_details: dict[str, Any]`
  and has no `deployments` field; `_activate_signal_impl` returns that shape at
  `src/core/tools/signals.py:299-308`. `v3.1.1:static/schemas/source/signals/activate-signal-response.json`
  makes `deployments` **required** on the success branch (`"required": ["deployments"]`, items
  `$ref core/deployment.json`) and mutually exclusive with `errors` (`"not": {"required": ["errors"]}`),
  while our model permits both simultaneously (its own docstring, point 4, admits this). No
  `activate_signal` response we can emit is schema-valid.

- **`activate_signal` cannot receive `destinations` or a caller `idempotency_key`.**
  `src/core/tools/signals.py:317-323` (MCP) and `:366-373` (A2A raw) expose only
  `signal_agent_segment_id, campaign_id, media_buy_id, context`.
  `_build_activate_signal_request` hardcodes `destinations=[{"type": "platform", "platform": "mock"}]`
  at `:242` and synthesizes `idempotency_key` at `:243`.
  `v3.1.1:static/schemas/source/signals/activate-signal-request.json` marks all three of
  `idempotency_key`, `signal_agent_segment_id`, `destinations` as required, with
  `destinations.minItems: 1` and `idempotency_key` `pattern: ^[A-Za-z0-9_.:-]{16,255}$` — a
  client-generated value whose whole purpose (dedupe on retry) is defeated by server synthesis.
  This is a Pattern #5 boundary-completeness violation: the wrapper drops parameters `_impl`
  needs. Blocks the whole `agent_activation` phase.

- **Decide and record: is the sales agent a signals agent at all?**
  `src/core/tools/__init__.py:25` and `src/a2a_server/adcp_a2a_server.py:89,1484,1819,2318` say
  no — signals belong to dedicated signals agents. Yet `src/core/tools/signals.py` (393 lines,
  6 hardcoded sample signals) is still carried, and `BR-UC-008-manage-audience-signals.feature`
  (1100+ lines, ~90 scenarios) still exists. The 3.1.1 `signal-marketplace` specialism requires
  `required_tools: [get_signals, activate_signal]` plus `requires_scenarios: [signal_marketplace/governance_denied]`.
  Either declare the protocol + specialism and build to it, or delete `signals.py` and the
  UC-008 feature. The current middle state is dead code plus dormant tests.

- **`BR-UC-008-manage-audience-signals.feature` is entirely unbound.** No
  `tests/bdd/test_uc008_*.py` exists; pytest-bdd binds features only via explicit
  `scenarios(...)` (18 such call sites, none for UC-008). ~90 scenarios never execute. This is
  the dormant-scenario anti-pattern at feature scale — the file reads as coverage and provides
  none. Blocked on the previous ticket (there is nothing to bind it to until the signals
  question is decided).

- **`uc005_format_id_roundtrip.py:101` claims schema validation and performs none.**
  `@then("the response should be schema-valid against list-creative-formats-response.json")`
  has body `assert isinstance(formats, list)`. `tests/helpers/pinned_schema.py::validate_against_pinned_schema`
  exists and is used correctly at `tests/bdd/test_uc018_list_creatives.py:217-220`. The step
  should call it. (This is the brief's "`then_response_schema_valid` runs no validator" item,
  localized: the UC-018 copy *is* real; the UC-005 copy is the vacuous one.)

- **Vendored fixture drift, instance:**
  `tests/fixtures/adcp_schemas_pinned/signals/activate-signal-response.json` is missing the
  `{"$ref": "/schemas/core/protocol-envelope.json"}` entry that `v3.1.1` adds to its `allOf`
  (diffed; that is the sole difference). Because `core/protocol-envelope.json` carries
  `"required": ["status"]`, the vendored copy silently does not enforce the top-level `status`
  field. Whole tree is pinned at `04f59d2d5`, an ancestor of `v3.1.0-beta.3` — older than our
  own 3.1.1 pin. Re-vendor via `tests/fixtures/adcp_schemas_pinned/_refresh.py` at `v3.1.1`.

- **Re-triage the sibling UC-008 storyboard scenarios.**
  `docs/test-obligations/storyboard-binding-baseline.md:38-40` marks
  `T-UC-008-storyboard-baseline-end-to-end` (feature:1112) as Bucket B and
  `T-UC-008-storyboard-activate-platform-destination` (feature:1143) as Bucket C. The first is
  actually Bucket C for the same reason as mine — its "buyer then calls activate_signal"
  half is not in `protocols/signals/index.yaml` at 3.1.1 (only its get_signals half is, at
  `search_signals`, lines 98-148). The second binds to the same specialism file, phase
  `platform_activation` / step `activate_on_platform` (lines 279-363) — which additionally
  carries an `upstream_traffic` anti-façade check (lines 357-364) we could not satisfy with a
  mock adapter.

---

## 8. Risks

- **Nothing here was verified by execution.** UC-008 has no test module, no steps, and no
  harness env, so there is no way to run the scenario before or after. Every green/red claim is
  from reading `src/core/tools/signals.py`, `src/core/schemas/_base.py:2458`, and
  `src/core/tools/capabilities.py`. The proposed replacement's greenness rests on
  `validate_against_pinned_schema` behaving as its source reads and on
  `tests/fixtures/adcp_schemas_pinned/core/deployment.json` being byte-identical to `v3.1.1`
  (that diff I did run — it is identical).

- **`core/deployment.json` uses a bare `oneOf` with a `discriminator` keyword.** Draft-07 has no
  `discriminator`, so `Draft7Validator` ignores it and falls back to `oneOf` exclusivity. I
  reasoned through each Examples row (an agent doc fails the platform branch on the
  `const: "platform"` mismatch, so exactly one branch matches) but did not execute the
  validator. If any row behaves unexpectedly, the row is what is wrong, not the schema —
  adjust the table, do not weaken the Then.

- **My proposal replaces a dispatching scenario with a non-dispatching one.** That is a real
  reduction in what the scenario claims to cover, and I want it read as such rather than as
  equivalent coverage. It is deliberate: the dispatching version cannot run today and could not
  pass if it did. A reviewer may reasonably prefer deletion (see the note at the end of §5).

- **`@schema-v3.1` on a `Scenario Outline` that validates constructed documents** is a slightly
  different use than the existing `@schema-v3.1` scenarios in UC-014 and UC-004, which tag
  dispatching scenarios whose expectations are schema-derived. I believe it is within the tag's
  meaning; if the team reads `@schema-v3.1` as strictly "dispatching, schema-grounded", this
  scenario needs a different tag or deletion.

- **The second proposed outline introduces a new `@T-…` identifier**
  (`@T-UC-008-schema-activation-key-discriminator`) not present in
  `docs/test-obligations/bdd-traceability.yaml`. It needs an entry added, or it should be folded
  into the first outline. I split them because they pin two different schema files.

- **I did not check 3.1.8 or HEAD.** Per the brief, 3.1.1 is authority and I stayed there. I
  have no read on whether the signals specialism structure changed afterward.

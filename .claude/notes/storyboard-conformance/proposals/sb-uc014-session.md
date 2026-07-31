# Re-pin: `T-UC-014-storyboard-baseline-session-id-roundtrip`

Scenario: `tests/bdd/features/BR-UC-014-sponsored-intelligence-session.feature:1284`
Title: "SI baseline conformance -- session_id roundtrips from initiate through send_message to terminate"

---

## 1. VERDICT

**NOT GRADED — undeclared gate.** Two independent reasons, either one sufficient:

1. **The gate is a protocol we do not declare.** The behaviour is graded only by the
   `sponsored-intelligence` **protocol** baseline storyboard. `src/core/tools/capabilities.py:99`
   and `:271` declare `supported_protocols=[SupportedProtocol.media_buy]`. The 3.1.1 capabilities
   schema makes that declaration the *definition* of the conformance path (quoted verbatim in §3).
   We are committed to `protocols/media-buy/` and nothing else. The SI baseline is not on our path.

2. **The specific behaviour the scenario names is not graded even for an SI agent.** The
   storyboard grades `field_present: session_id` on `si_initiate_session` **only**. On
   `si_send_message` and `si_terminate_session` there is **no** `session_id` check of any kind —
   not `field_present`, not `field_value`. The roundtrip *equality* the scenario is named after
   exists solely as the `description:` string on the initiate-side `field_present` check, which is
   narrative prose hanging off a presence check. Nothing grades equality.

Additionally, production has **zero** sponsored-intelligence code:
`grep -rn "si_initiate_session|si_send_message|si_terminate_session|si_get_offering" --include='*.py' src/`
returns **0 hits**; `grep -rni "sponsored_intelligence|sponsored-intelligence" src/` returns **0 hits**.

**Consequence:** the `@storyboard-v3.1` tag is unjustified. It becomes `@schema-v3.1` — which is
already the dominant tier tag in this very file (29 of 30 tier-tagged scenarios in
`BR-UC-014-…feature` are `@schema-v3.1`; this one scenario is the lone `@storyboard-v3.1`).

**Also material, and not in the baseline audit doc:** the entire feature file is **DORMANT**. There
is no `scenarios("features/BR-UC-014-sponsored-intelligence-session.feature")` binding anywhere —
`grep -rn "scenarios(" tests/bdd/*.py` lists 27 bindings and UC-014 is not among them; `grep -rn
"BR-UC-014" tests/bdd/*.py tests/bdd/steps/` returns nothing. Not one of the ~200 scenarios in this
file executes, and not one UC-014 step definition exists. Whatever Gherkin lands here is
documentation until someone wires the file.

---

## 2. Real binding at 3.1.1

### What the current footer points at

**Nothing.** This scenario has **no `@source` footer at all** (bucket C in
`docs/test-obligations/storyboard-binding-baseline.md:41`). Its trailing comment block asserts a
binding in prose — "si_baseline storyboard exercises the four-call lifecycle… The runner captures
session_id from initiate and asserts it on every subsequent call" — with no machine-checkable
citation. That prose claim is **false** on the second half: the runner substitutes
`$context.session_id` into the *requests*, but grades nothing about it in the *responses*.

For contrast, the neighbouring scenarios in this same file that *do* carry footers all cite
`path=static/schemas/source/sponsored-intelligence/si-get-offering-request.json` — the
**request** schema for a *different* call than the one under test (e.g.
`T-UC-014-user-action-roundtrip`, `T-UC-014-offering-anchors-session`, `T-UC-014-inv-286-1/2/3`).
That is the same systematic mis-citation the brief describes, in a different shape: a whole block of
scenarios sharing one copy-pasted, wrong path.

### The real storyboard

Storyboard `id: si_baseline`, `protocol: sponsored-intelligence`, `category: si_baseline`,
phase **`session_lifecycle`**.

- dist:   `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/sponsored-intelligence/index.yaml`
- source: `static/compliance/source/protocols/sponsored-intelligence/index.yaml` @ `v3.1.1`
  (verified **byte-identical** to the dist file via `diff`)
- `domains/sponsored-intelligence/index.yaml` is **byte-identical** to the `protocols/` copy
  (verified via `diff`) — the two tiers are the same document, so citing `protocols/` is correct
  and unambiguous.

### The graded `validations:` blocks, verbatim

`protocols/sponsored-intelligence/index.yaml`, phase `session_lifecycle` (line 129), step
`si_initiate_session` (line 138), validations at **lines 171–184**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches si-initiate-session-response.json schema"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "si_session--si_initiate_session"
            description: "Context correlation_id returned unchanged"
          - check: field_present
            path: "session_id"
            description: "Platform assigns session_id — must be echoed in si_send_message and si_terminate_session"
```

Step `si_send_message` (line 185), validations at **lines 210–220**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches si-send-message-response.json schema"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "si_session--si_send_message"
            description: "Context correlation_id returned unchanged"
```

Step `si_terminate_session` (line 221), validations at **lines 246–256**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches si-terminate-session-response.json schema"

          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "si_session--si_terminate_session"
            description: "Context correlation_id returned unchanged"
```

Read those three together: **no `session_id` validation on send_message or terminate.** The graded
surface of the whole phase is response-schema conformance + `context.correlation_id` echo, plus one
`field_present: session_id` on initiate. The scenario's headline claim is ungraded prose.

The runner *does* thread the value — `sample_request: session_id: "$context.session_id"` on both
later steps (lines ~207 and ~243), fed by `context_outputs: - name: session_id / path: 'session_id'`
(lines 168–170). But that is **test-vector plumbing on the request side**, not a graded check on the
response side. A platform that fabricates a fresh `session_id` in each response passes every listed
validation.

### Which tier owns it

**`protocols/`** — `protocols/sponsored-intelligence/index.yaml` (mirrored byte-for-byte in
`domains/`). Not universal, not a specialism we hold.

The `specialisms/sponsored-intelligence/index.yaml` tier exists but grades nothing and says so
outright:

```yaml
id: sponsored_intelligence
status: preview
summary: "Specialism claim for agents that expose conversational sponsored experiences via the SI
  session lifecycle. Preview while the underlying SI tools remain `x-status: experimental`; ..."
...
phases: []
```

and in its narrative:

```
  The storyboard for this specialism is a placeholder while the underlying SI tools
  remain `x-status: experimental`. Conformance for SI agents is currently exercised by
  the `sponsored-intelligence` protocol baseline (which already covers the full session
  lifecycle); claiming this specialism today is graded as `{ status: "preview",
  passed: null }` per the preview-status contract in
  /docs/building/verification/compliance-catalog.
```

`phases: []` and `passed: null` — even an agent that *did* claim `sponsored_intelligence` as a
specialism would receive no graded verdict from that tier. The only grading route is the protocol
baseline, which is gated on `supported_protocols`.

### The gate, stated by the storyboard itself

`protocols/sponsored-intelligence/index.yaml:47–82`, phase `capability_discovery`:

```yaml
        expected: |
          Return capabilities declaring sponsored_intelligence in supported_protocols, confirming the agent supports conversational ad experiences.
```

with graded validations at lines 69–82 including:

```yaml
          - check: field_present
            path: "supported_protocols"
            description: "Agent declares supported protocols"
```

Phase 0 of the SI baseline expects `sponsored_intelligence` in `supported_protocols`. We emit
`[media_buy]`.

---

## 3. Schema constraints at 3.1.1

### The gate is schema-defined, not merely storyboard convention

`git show v3.1.1:static/schemas/source/protocol/get-adcp-capabilities-response.json`,
`properties.supported_protocols`:

```json
"supported_protocols": {
  "type": "array",
  "description": "AdCP protocols this agent supports. Stable values both (a) declare which tools the agent implements and (b) commit the agent to pass the baseline compliance storyboard at /compliance/{version}/protocols/{protocol}/ (with snake_case → kebab-case path mapping, e.g. media_buy → /compliance/.../protocols/media-buy/). ...",
  "items": {
    "type": "string",
    "enum": ["media_buy", "signals", "governance", "sponsored_intelligence", "creative", "brand", "measurement"]
  },
  "minItems": 1
}
```

This is the decisive clause and it is **schema**, the highest authority tier: declaring a protocol
*is* the commitment to its baseline storyboard. `sponsored_intelligence` is a valid enum value we
deliberately do not emit. Therefore `protocols/sponsored-intelligence/` is, by the schema's own
definition, outside our conformance path.

### The three SI response schemas — what they actually mandate

All three carry `"x-status": "experimental"` and `allOf` → `core/version-envelope.json` +
`core/protocol-envelope.json`.

`git show v3.1.1:static/schemas/source/sponsored-intelligence/si-initiate-session-response.json`:

```json
"session_id": {
  "type": "string",
  "description": "Unique session identifier for subsequent messages",
  "x-entity": "si_session"
},
...
"required": ["session_id", "session_status"],
"additionalProperties": true
```

`…/si-send-message-response.json`:

```json
"session_id": {
  "type": "string",
  "description": "Session identifier",
  "x-entity": "si_session"
},
...
"required": ["session_id", "session_status"],
"additionalProperties": true
```

`…/si-terminate-session-response.json`:

```json
"session_id": {
  "type": "string",
  "description": "Terminated session identifier",
  "x-entity": "si_session"
},
"terminated": {
  "type": "boolean",
  "description": "Whether session was successfully terminated"
},
...
"required": ["session_id", "terminated"],
"additionalProperties": true
```

Note the asymmetry the scenario misses entirely: terminate requires `session_id` + **`terminated`**,
*not* `session_status` — the other two require `session_id` + **`session_status`**, not `terminated`.

`git show v3.1.1:static/schemas/source/core/protocol-envelope.json`:

```json
"required": ["status"],
"additionalProperties": true,
"not": { "anyOf": [ { "required": ["task_status"] }, { "required": ["response_status"] } ] }
```

with the description clause:

> "The `status` field is REQUIRED on every task response envelope, including synchronous metadata
> responses (e.g., `get_adcp_capabilities`) where the value is `completed`. Agents shipping responses
> without a top-level `status` are non-conformant regardless of whether the task body schema would
> otherwise validate."

So the true per-response required set at 3.1.1 is `{status}` ∪ the body's own `required` — three
fields on each of initiate/send_message, and `{status, session_id, terminated}` on terminate.

`git show v3.1.1:static/schemas/source/enums/si-session-status.json`:

```json
"enum": ["active", "pending_handoff", "complete", "terminated"]
```

Request-side, at `v3.1.1`:

- `si-initiate-session-request.json` — `required: ["idempotency_key", "intent", "identity"]`
- `si-send-message-request.json` — `required: ["idempotency_key", "session_id"]`
- `si-terminate-session-request.json` — `required: ["session_id", "reason"]`, with
  `reason.enum = ["handoff_transaction", "handoff_complete", "user_exit", "session_timeout", "host_terminated"]`

The scenario's `reason "handoff_complete"` is a valid enum member — one thing it gets right. But it
omits `idempotency_key` on both initiate and send_message, and both are `required`.

**Schema vs storyboard conflict, resolved for the schema:** the storyboard grades `session_id` as
merely `field_present` on initiate and grades it **not at all** on the two later steps; the 3.1.1
schemas make `session_id` **`required`** on all three responses. The schema is the stronger and
authoritative statement, and it is what the rewrite encodes. Neither source mandates *equality*
across the three — that remains a description string.

---

## 4. Conflicts — what the scenario gets wrong

1. **Asserts a graded roundtrip that is not graded.** The trailing comment claims "The runner
   captures session_id from initiate and asserts it on every subsequent call." It does not. Only the
   request side is substituted. Three of the scenario's Thens (`the session_id sent on si_send_message
   should match…`, `…si_terminate_session should match…`, and by extension the roundtrip framing)
   restate `$context.session_id` request substitution as if it were a graded response check.

2. **Two Thens assert the *request*, not the response.** "the session_id **sent on** si_send_message
   should match the value captured" is a tautology about the test harness's own outbound payload — it
   cannot fail for any reason attributable to the agent under test. This is the vacuous-assertion
   pattern `test_architecture_bdd_no_trivial_assertions.py` exists to catch; it survives only because
   the file is dormant and the guard never sees a step body.

3. **"should carry a platform-assigned session_id" is a bare existence check.** No concrete value
   compared. Same guard, same reason it survives.

4. **Misses everything the schema actually mandates**: `status` on the envelope (`protocol-envelope`
   `required: ["status"]`), `session_status` on initiate and send_message, `terminated` on terminate,
   the `si-session-status` enum domain, and the initiate/terminate required-set asymmetry.

5. **Omits `idempotency_key`,** which is `required` on both `si-initiate-session-request.json` and
   `si-send-message-request.json`, and which the storyboard supplies via
   `"$generate:uuid_v4#si_baseline_session_lifecycle_si_initiate_session"`.

6. **Drops the two things the storyboard actually grades on every step**: `context` echo and
   `context.correlation_id` returned unchanged. Those are the real graded surface of this phase and
   the scenario mentions neither.

7. **`@storyboard-v3.1` is a false conformance claim** (§1), as is the `@baseline-conformance` tag.

8. **Background is false for this agent.** Line 39 of the feature: `And the Seller Agent has SI
   protocol support enabled`. We declare `[media_buy]`. No `Given` can make that true against
   `capabilities.py`.

9. **The named schema-validity assertions are landmines, not green assertions.**
   `tests/fixtures/adcp_schemas_pinned/` has directories `account core creative enums media-buy
   pricing-options signals` and **no `sponsored-intelligence`** (`find … -iname 'si-*'` → 0 hits).
   `tests/helpers/pinned_schema.py:36-41` raises `AssertionError("Pinned schema not vendored: …")` on
   a miss — deliberately a hard failure, never a skip. So "schema-valid against
   si-initiate-session-response.json" would hard-fail the instant the feature is wired. The rewrite
   must not use that phrasing.

---

## 5. Proposed Gherkin

Rationale for the shape: the tier tag drops to `@schema-v3.1`, so the scenario documents the
**3.1.1 wire contract** the SI lifecycle must satisfy, rather than claiming graded conformance we do
not hold. It is a `Scenario Outline` over the three lifecycle calls, every Then compares a concrete
enumerated value, and no assertion depends on SI production code or on unvendored SI schemas — so it
cannot go red when this file is eventually bound. The opaque `@T-UC-014-…` identifier tag is
preserved verbatim (`docs/test-obligations/bdd-traceability.yaml:8301` references it).
`@baseline-conformance` is removed: it asserted membership of a conformance path §1 proves we are not
on.

```gherkin
  @T-UC-014-storyboard-baseline-session-id-roundtrip @schema-v3.1 @v3-1 @session-id-roundtrip
  Scenario Outline: SI session lifecycle response contract -- <call> carries session_id plus its call-specific required fields
    Given the AdCP 3.1.1 response schema for the SI lifecycle call "<call>" is "<response_schema>"
    When the SI response contract for "<call>" is resolved at AdCP 3.1.1
    Then the envelope-level required field set for "<call>" should be exactly "status"
    And the body-level required field set for "<call>" should be exactly "<body_required>"
    And "session_id" should be a required body field of "<response_schema>" with type "string"
    And the request field carrying the session identity for "<call>" should be "<request_session_field>"

    Examples: SI session lifecycle calls
      | call                  | response_schema                      | body_required                | request_session_field |
      | si_initiate_session   | si-initiate-session-response.json    | session_id,session_status    | (none)                |
      | si_send_message       | si-send-message-response.json        | session_id,session_status    | session_id            |
      | si_terminate_session  | si-terminate-session-response.json   | session_id,terminated        | session_id            |

  @T-UC-014-si-session-status-enum @schema-v3.1 @v3-1 @session-id-roundtrip
  Scenario Outline: SI session_status is constrained to the 3.1.1 si-session-status enum
    Given the AdCP 3.1.1 enum schema "si-session-status.json"
    When the value "<value>" is checked against that enum
    Then membership should be "<member>"

    Examples: Enum domain
      | value           | member |
      | active          | yes    |
      | pending_handoff | yes    |
      | complete        | yes    |
      | terminated      | yes    |
      | in_progress     | no     |
      | closed          | no     |
    # AdCP 3.1.1 enums/si-session-status.json: enum is exactly these four values.
    # `terminate` returns `complete` for handoff_* reasons and `terminated` for
    # user_exit / session_timeout / host_terminated (si-terminate-session-response.json
    # session_status description).

  # WHY @schema-v3.1 AND NOT @storyboard-v3.1 (re-pinned against AdCP 3.1.1):
  #
  # The SI session lifecycle is graded ONLY by the sponsored-intelligence PROTOCOL
  # baseline storyboard (id: si_baseline, phase: session_lifecycle). AdCP 3.1.1
  # protocol/get-adcp-capabilities-response.json defines supported_protocols as the
  # commitment: declaring a protocol "commit[s] the agent to pass the baseline
  # compliance storyboard at /compliance/{version}/protocols/{protocol}/". This agent
  # declares supported_protocols = [media_buy] only (src/core/tools/capabilities.py),
  # so protocols/sponsored-intelligence/ is not on our conformance path.
  #
  # The specialisms/sponsored-intelligence/ tier grades nothing either: status:
  # preview, phases: [], graded as { status: "preview", passed: null } while the SI
  # tools remain x-status: experimental.
  #
  # The prior wording claimed the storyboard runner "asserts [session_id] on every
  # subsequent call". It does not. Verbatim at 3.1.1, session_lifecycle grades
  # field_present: session_id on si_initiate_session ONLY (index.yaml:182-184); the
  # si_send_message (:210-220) and si_terminate_session (:246-256) validations grade
  # response_schema + context echo + context.correlation_id and NOTHING about
  # session_id. The runner substitutes $context.session_id into the two later
  # REQUESTS, which is test-vector plumbing, not a graded response check. Roundtrip
  # EQUALITY is ungraded at 3.1.1; what IS mandated is that session_id be required on
  # all three responses -- schema, not storyboard, and the schema is authoritative.
  #
  # The 3.1.1 schemas additionally require an envelope-level `status`
  # (core/protocol-envelope.json required: ["status"]) on all three responses, and the
  # body required sets are asymmetric: initiate/send_message require session_status,
  # terminate requires `terminated`.
  #
  # @source repo=adcp ref=v3.1.1 path=static/schemas/source/sponsored-intelligence/si-initiate-session-response.json
  # @source repo=adcp ref=v3.1.1 path=static/schemas/source/sponsored-intelligence/si-send-message-response.json
  # @source repo=adcp ref=v3.1.1 path=static/schemas/source/sponsored-intelligence/si-terminate-session-response.json
  # @source repo=adcp ref=v3.1.1 path=static/schemas/source/core/protocol-envelope.json
  # @source repo=adcp ref=v3.1.1 path=static/schemas/source/enums/si-session-status.json
  # @source-ungraded repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/sponsored-intelligence/index.yaml phase=session_lifecycle
  #   (the real storyboard; cited for traceability, NOT as a conformance claim -- gate
  #    supported_protocols=[sponsored_intelligence] is not declared by this agent)
```

Two notes on this proposal:

- I split off a second scenario for the enum rather than cramming a fourth Examples axis into the
  first outline; both keep the shared `@session-id-roundtrip` tag. If the team prefers exactly one
  scenario per identifier tag, drop the second block — it is additive, not load-bearing.
- `@source-ungraded` is a **new** footer key. It exists because the honest citation here is "this is
  where the behaviour lives, and it is *not* graded for us", which the existing single-`@source`
  vocabulary cannot express. If introducing a key is unwanted, the fallback is to keep the five
  `@source` schema lines and demote the storyboard reference to plain prose in the comment block
  above — the schema lines are the ones that carry the authority anyway.

---

## 6. Step inventory

**Existing steps reused: none — and none are available to reuse.** UC-014 has no step definitions at
all (`grep -rn "BR-UC-014" tests/bdd/*.py tests/bdd/steps/` → 0 hits) and the feature is unbound.

Phrasings deliberately **avoided** despite existing elsewhere:

| Phrasing | Where it lives | Why not reused |
|---|---|---|
| `the response should be schema-valid against {schema_file}` | `tests/bdd/test_uc018_list_creatives.py:217` (calls `validate_against_pinned_schema`) | SI schemas are not vendored under `tests/fixtures/adcp_schemas_pinned/`; `pinned_schema.py:36-41` hard-fails on a miss. Using it would guarantee red the day UC-014 is wired. Also module-local to `test_uc018_…`, not in a shared `steps/` package, so not importable from UC-014 anyway. |
| `the response should be schema-valid against list-creative-formats-response.json` | `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101` | Hardcoded to one schema, and its body runs no validator (it asserts `isinstance(formats, list)`) — the known gap named in the brief. |

**New steps required (6):**

| Step | Type | Notes |
|---|---|---|
| `the AdCP 3.1.1 response schema for the SI lifecycle call "<call>" is "<response_schema>"` | Given | Loads the schema from the adcp pin; see ticket §7 on vendoring. |
| `the SI response contract for "<call>" is resolved at AdCP 3.1.1` | When | Pure schema resolution — no production call, no transport. |
| `the envelope-level required field set for "<call>" should be exactly "status"` | Then | Compares `core/protocol-envelope.json` `required` to a literal. |
| `the body-level required field set for "<call>" should be exactly "<body_required>"` | Then | Compares the schema's `required` list to the parametrized literal. |
| `"session_id" should be a required body field of "<response_schema>" with type "string"` | Then | Two concrete comparisons: membership in `required`, and `properties.session_id.type == "string"`. |
| `the request field carrying the session identity for "<call>" should be "<request_session_field>"` | Then | Compares against `si-*-request.json` `required`; `(none)` for initiate. |
| `the AdCP 3.1.1 enum schema "si-session-status.json"` / `the value "<value>" is checked against that enum` / `membership should be "<member>"` | Given/When/Then | Third block; enum-domain comparison. |

All six are transport-independent by construction — they read schemas, not responses, so there is no
MCP/A2A/REST/e2e_rest axis to branch on. That is the only way this scenario can be transport-neutral
*and* green while we implement no SI.

---

## 7. TICKET MATERIAL

- **UC-014 feature file is entirely dormant — ~200 scenarios, zero executions.**
  `tests/bdd/features/BR-UC-014-sponsored-intelligence-session.feature` has no
  `scenarios(...)` binding; `grep -rn "scenarios(" tests/bdd/*.py` lists 27 bound features and UC-014
  is absent, and `grep -rn "BR-UC-014" tests/bdd/*.py tests/bdd/steps/` returns nothing. Every
  assertion in the file — including the three vacuous ones catalogued in §4 — is invisible to
  `test_architecture_bdd_no_trivial_assertions.py` and `..._no_pass_steps.py`, because those guards
  scan step *bodies* and no bodies exist. Decide explicitly: bind it (blocked on the two tickets
  below) or move it to a documented `features/unbound/` area so the dormancy is visible rather than
  inferred. This is the same dormant-scenario anti-pattern recorded for PR #1260 and PR #1544.

- **SI JSON schemas are not vendored in the pinned fixture tree.**
  `tests/fixtures/adcp_schemas_pinned/` contains `account core creative enums media-buy
  pricing-options signals` and no `sponsored-intelligence/`;
  `find tests/fixtures/adcp_schemas_pinned -iname 'si-*'` → 0 hits. Any step using the existing
  `the response should be schema-valid against <file>` phrasing
  (`tests/bdd/test_uc018_list_creatives.py:217` → `tests/helpers/pinned_schema.py:36-41`) hard-fails
  with `AssertionError("Pinned schema not vendored: …")`. AdCP 3.1.1 ships 14 SI schemas under
  `static/schemas/source/sponsored-intelligence/`. Either vendor them (via
  `tests/fixtures/adcp_schemas_pinned/_refresh.py`) or record that SI schema-shape assertions are
  out of scope. Compounded by the brief's known gap that the fixture tree is pinned at `04f59d2d5`,
  not 3.1.1 — SI schemas vendored from the wrong pin would be worse than none.

- **The SI storyboard grades no session_id continuity; the 3.1.1 schemas require the field on all
  three responses. Report the gap upstream, not locally.**
  `protocols/sponsored-intelligence/index.yaml:210-220` (`si_send_message`) and `:246-256`
  (`si_terminate_session`) contain no `session_id` check, while
  `si-send-message-response.json` and `si-terminate-session-response.json` both carry
  `required: ["session_id", …]`. The storyboard is weaker than the schema it grades against. An
  agent can fabricate a fresh `session_id` per response and pass the baseline. Worth an upstream
  issue on `adcontextprotocol/adcp` proposing `field_value` checks bound to
  `$context.session_id` on both later steps. Do **not** patch our local generated `.feature` to
  assert behaviour the upstream contract does not grade — mirror the diff upstream.

- **`@source` footers across UC-014 cite the wrong file wholesale.** At least six scenarios
  (`T-UC-014-user-action-roundtrip`, `T-UC-014-offering-anchors-session`,
  `T-UC-014-inv-286-1/2/3`, and neighbours) all carry
  `path=static/schemas/source/sponsored-intelligence/si-get-offering-request.json` regardless of
  which call they exercise — `si_send_message` and `si_initiate_session` scenarios citing the
  *offering request* schema. Same class as the off-by-one described in the brief, but here it is a
  single copy-pasted path rather than a shift. All are `ref=v3.1-04f59d2d5`, older than our 3.1.1
  pin. Sweep the whole file.

- **Feature `Background` asserts a capability we do not have.**
  `BR-UC-014-sponsored-intelligence-session.feature:39`: `And the Seller Agent has SI protocol
  support enabled`. `src/core/tools/capabilities.py:99,271` emit
  `supported_protocols=[SupportedProtocol.media_buy]`. If UC-014 is ever bound, this Given has no
  truthful implementation. Per AdCP 3.1.1 `get-adcp-capabilities-response.json`
  `supported_protocols`, declaring `sponsored_intelligence` would commit us to passing
  `/compliance/3.1.1/protocols/sponsored-intelligence/` — a four-tool implementation
  (`si_get_offering`, `si_initiate_session`, `si_send_message`, `si_terminate_session`) that does
  not exist. Either scope SI as a product decision or make the Background honest.

- **`then_response_schema_valid` divergence between two modules (pre-existing, cited not
  rediscovered).** `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101` runs no validator
  (asserts `isinstance(formats, list)`), while `tests/bdd/test_uc018_list_creatives.py:217` calls
  `validate_against_pinned_schema`. Two steps, same name, different strength. Named in the brief's
  known-gaps list; recorded here because §6 had to reason about both.

---

## 8. Risks

- **Nothing here was verified by execution.** The feature is unbound, so I could not run the current
  scenario or the proposal. The green-ness claim for the rewrite rests on the fact that its
  assertions read JSON schemas rather than call production — but it is an argument, not a test run.
  If UC-014 is bound as part of this baseline PR, the six new steps must be written and run before
  the proposal can be called green.
- **The `@source-ungraded` key is invented by me.** It is not in the existing footer vocabulary. If
  the tooling that parses `@source` (the audit script behind
  `docs/test-obligations/storyboard-binding-baseline.md`) does strict key matching, it may error or
  silently ignore it. I did not read that script. §5 gives the fallback.
- **Second scenario adds a tag not in `bdd-traceability.yaml`.** `@T-UC-014-si-session-status-enum`
  is new; `docs/test-obligations/bdd-traceability.yaml` would need a matching entry, or a
  traceability guard may flag an unregistered identifier. I did not check whether such a guard
  exists. Dropping the second block avoids this entirely.
- **`protocols/` vs `domains/` tier naming.** The two SI index files are byte-identical at 3.1.1 and
  `index.json` lists sponsored-intelligence under both `protocols` and `domains`. I cited
  `protocols/` because the capabilities schema's commitment clause names
  `/compliance/{version}/protocols/{protocol}/` explicitly. If the repo convention elsewhere prefers
  `domains/`, the path swaps and nothing else changes.
- **3.1.8 / HEAD drift, noted only.** All SI schemas carry `"x-status": "experimental"` and the
  specialism carries `status: preview` with a promotion path ("promotes to `stable` (with
  required_tools and a graded storyboard) when the SI tools graduate from experimental"). A later
  minor could make SI grading real and could add the missing `session_id` checks. Irrelevant to a
  3.1.1-pinned baseline; flagged so nobody re-derives it.
- **I did not read the generator** (`scripts/compile_bdd.py`). The file header says `DO NOT EDIT`,
  though the project's recorded position is that local edits to generated `BR-*.feature` files
  survive because generation merges semantically. If that is wrong for this file specifically, the
  rewrite reverts on the next compile.

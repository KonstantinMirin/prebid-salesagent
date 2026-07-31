# Re-grounding `@T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip` against AdCP 3.1.1

Scenario: `tests/bdd/features/BR-UC-002-create-media-buy.feature:2601`
Title: "Async submitted envelope -- task_id matches deterministic value registered via comply_test_controller"

---

## 1. VERDICT

**NOT GRADED — undeclared gate.**

The storyboard the scenario actually belongs to (`create_media_buy_async`) *is* real, *is* graded
(`validations:` blocks, not prose), and *is* a `requires_scenarios` member of the `media-buy`
protocol baseline we declare. But every graded step in it is reachable only through
`comply_test_controller` / `force_create_media_buy_arm`, and the storyboard self-declares that
sellers without controller support grade **`not_applicable`, not failed**:

> `dist/compliance/3.1.1/protocols/media-buy/scenarios/create_media_buy_async.yaml:36-38`
> "The directive is keyed to the caller's authenticated sandbox account (account + principal pair);
> sellers that do not implement the controller scenario return UNKNOWN_SCENARIO and the runner
> grades this storyboard not_applicable rather than failed."

We implement no controller at all — `grep -rn "comply_test_controller\|force_create_media_buy_arm" src/`
returns **zero hits**, and `src/core/tools/capabilities.py:271-272` declares only
`supported_protocols=[media_buy]` + `specialisms=[sales_non_guaranteed]`, with **no
`compliance_testing` block** (the 3.1.1 field whose *presence* is the declaration of controller
support). So the whole storyboard, including the `$context.forced_task_id` round-trip this scenario
is named after, is off our conformance path.

Therefore: **drop `@storyboard-v3.1`.** `@schema-v3.1` is already the Feature-level tag
(`BR-UC-002-create-media-buy.feature:4`), so the scenario inherits it; I restate it on the scenario
line anyway to match the convention the sibling rewrite of
`@T-UC-002-storyboard-governance-with-conditions` just established in the working tree. The opaque
`@T-UC-002-…` identifier is unchanged.

The *behaviour* does not go away with the gate: the submitted-envelope shape is mandated by the
**3.1.1 JSON schema** (highest authority), and our production really does emit that envelope on the
manual-approval path. So the scenario is re-grounded on the schema and re-pointed at the production
trigger we actually have.

---

## 2. Real binding at 3.1.1

### What the current footer points at — wrong on both axes

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/governance_approved.yaml
```

* **Stale ref.** `git merge-base --is-ancestor 04f59d2d5 v3.1.1` → true; `git rev-list --count
  04f59d2d5..v3.1.1` → **717**. The pin is 717 commits *behind* the version we target.
* **Wrong path — the proven off-by-one.** `governance_approved.yaml` is
  `"Seller creates buy when governance approves"` — that is the **next** scenario's storyboard
  (`@T-UC-002-storyboard-governance-approved`, feature line 2621), which in turn cites
  `governance_conditions.yaml`, and so on. The scenario's own prose names its true storyboard twice:
  `# create_media_buy_async storyboard: …` and `# create_media_buy_async: deterministic task_id
  roundtrips …`.

### The real storyboard

`dist/compliance/3.1.1/protocols/media-buy/scenarios/create_media_buy_async.yaml`
(byte-identical to `git show v3.1.1:static/compliance/source/protocols/media-buy/scenarios/create_media_buy_async.yaml`,
and byte-identical again to the `domains/media-buy/` copy — the two tiers ship the same file).

Phase `submitted_arm_response` (L159), step `create_media_buy_submitted` (L178). Graded block,
verbatim, **L217-237**:

```yaml
        validations:
          - check: response_schema
            description: "Response matches create-media-buy-response.json — submitted-arm not.required clauses block media_buy_id and packages"
          - check: field_value
            path: "status"
            value: "submitted"
            description: "Status is the literal 'submitted' task-status value, not a MediaBuyStatus"
          - check: field_present
            path: "task_id"
            description: "task_id is present at the top of the envelope (snake_case payload field, even when the A2A adapter surfaces it as taskId on the wire)"
          - check: field_value
            path: "task_id"
            value: "$context.forced_task_id"
            description: "task_id matches the captured value from the controller directive — sellers that fabricate a fresh task_id instead of honoring the registered one fail here"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object"
          - check: field_value
            path: "context.correlation_id"
            value: "create_media_buy_async--create_media_buy_submitted"
            description: "Context correlation_id returned unchanged"
```

The preceding phase `force_submitted_arm` (L94) grades the controller call itself (L139-157:
`success`, `forced.arm == "submitted"`, `forced.task_id` present, `context.correlation_id` echo).
`$context.forced_task_id` is captured there via `context_outputs` (L117-119) — which is exactly why
the round-trip is unreachable without a controller.

### Tier ownership

`protocols/media-buy/` (and its identical `domains/media-buy/` twin) — **not** a specialism.
`protocols/media-buy/index.yaml:22` lists `media_buy_seller/create_media_buy_async` under
`requires_scenarios`, and we declare `supported_protocols=[media_buy]`. The gate that excludes us is
not the tier, it is the **agent capability** `supports_test_controller`
(`create_media_buy_async.yaml:58-60`, mirrored by `universal/comply-controller-mode-gate.yaml:38-40`),
surfaced in the capabilities schema as the `compliance_testing` block we do not emit.

Drift note (Risks only): the storyboard changed between `04f59d2d5` and `v3.1.1` **only** in
`sample_request` (`account` added to the controller call; `start_time: "asap"`, `end_time: 2099-…`).
The `validations:` are identical. So the stale ref never changed the grading — the path was simply
wrong all along.

---

## 3. Schema constraints at 3.1.1

`git show v3.1.1:static/schemas/source/media-buy/create-media-buy-response.json`, **L218-270**:

```json
    {
      "title": "CreateMediaBuySubmitted",
      "description": "Async task envelope returned when the media buy cannot be confirmed before the response is emitted — for example, when a guaranteed buy requires IO signing, when governance review is outstanding, or when the seller has queued the request for batch processing. The buyer polls tasks/get with task_id or receives a webhook when the task completes; the media_buy_id and packages land on the completion artifact, not this envelope. Do not use a 'pending_approval' MediaBuy.status for this case — that value is not in MediaBuyStatus; IO review and similar pre-issuance workflows are modeled at the task layer only.",
      "type": "object",
      "properties": {
        "status": {
          "type": "string",
          "const": "submitted",
          ...
        },
        "task_id": {
          "type": "string",
          "description": "Task handle the buyer uses with tasks/get, and that the seller references on push-notification callbacks. The media_buy_id is issued on the completion artifact, not here. Per AdCP wire conventions this is snake_case; A2A adapters MAY surface it as taskId, but the payload field emitted by the agent is task_id.",
          "x-entity": "task"
        },
        "message": { "type": "string", "maxLength": 2000, ... },
        "errors": { "type": "array", "description": "Optional advisory errors ... Terminal failures belong in the error branch, not here.", ... },
        "context": { "$ref": "/schemas/core/context.json", "description": "... Sellers MUST echo this object verbatim when the originating request carried context, including synchronous success, error, submitted, and webhook task-status payloads. ..." },
        "ext": { "$ref": "/schemas/core/ext.json" }
      },
      "required": [
        "status",
        "task_id"
      ],
      "additionalProperties": true,
      "not": {
        "anyOf": [
          { "required": [ "media_buy_id" ] },
          { "required": [ "packages" ] }
        ]
      }
    }
```

Envelope, `git show v3.1.1:static/schemas/source/core/protocol-envelope.json`:

```json
  "required": [ "status" ],
```
> "The `status` field is REQUIRED on every task response envelope … Agents shipping responses without
> a top-level `status` are non-conformant regardless of whether the task body schema would otherwise
> validate."

and, for `task_id`:
> "Unique identifier for tracking asynchronous operations. Present when a task requires extended
> processing time. Used to query task status and retrieve results when complete."

Note what the schema does **not** say: nothing about a caller-registrable task_id. The determinism
the storyboard grades is a *test-harness* construct layered on top of the schema, not a protocol
requirement. What the schema *does* require of `task_id` is that it is the handle "the buyer uses
with tasks/get" — i.e. it must name a task the seller actually holds. That is the assertable
substance of "round-trip" for an implementation without a controller, and it is what the proposed
Gherkin grades.

---

## 4. Conflicts

**Schema vs storyboard.** No contradiction on shape — the storyboard's `response_schema` check just
defers to the same `not.anyOf`. Where they diverge is *reachability*: the storyboard makes the
envelope observable only via a capability-gated tool; the schema makes the envelope normative for
**every** async create, however triggered. **The 3.1.1 schema wins** — we grade the envelope on the
trigger we have (human/adapter approval), and we drop the controller round-trip.

**What the scenario gets wrong today**

1. `@source` cites the wrong storyboard (`governance_approved`) at a ref 717 commits stale. Both
   defects, in one footer.
2. `@storyboard-v3.1` claims conformance grading we cannot receive — the storyboard grades
   `not_applicable` for us.
3. Every step it declares is **fictional**. `grep` over `tests/bdd/steps/` for
   `"registered force_create_media_buy_arm"`, `"under the registered sandbox account"`,
   `"carry status \"submitted\""`, `"carry task_id"`, `"NOT carry media_buy_id"`,
   `"NOT carry packages"`, `"match the value registered by the controller"` → **zero hits**. The
   scenario therefore raises `StepDefinitionNotFoundError` and is silently converted to xfail by
   `tests/bdd/conftest.py:99-102`.
4. Even if the steps existed it would not run: `T-UC-002-…-roundtrip` is not in
   `_UC002_MANUAL_APPROVAL_WIRED` / `_UC002_IDEMPOTENCY_WIRED` (`tests/bdd/conftest.py:2806-2819`),
   so it falls to the catch-all `pytest.xfail("UC-002 harness not yet wired for non-extension
   scenarios")` at `tests/bdd/conftest.py:3282`. **Two independent dormancy mechanisms.**
5. Its last Then — "the task_id on the response should match the value registered by the controller
   directive" — is a restatement of the Then two lines above it (`carry task_id "task_async_…"`).
   Even fully wired it would grade nothing new.

**What it misses.** `packages` absence is not graded anywhere live (the sibling
`@T-UC-002-alt-manual` grades `media_buy_id` / `confirmed_at` / `revision` only), and the
`context`-echo MUST is graded nowhere at all on the submitted branch.

---

## 5. Proposed Gherkin

Replaces `tests/bdd/features/BR-UC-002-create-media-buy.feature:2600-2619` in full.

```gherkin
  @T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip @schema-v3.1 @v3-1 @submitted-envelope @async @task-id-roundtrip
  Scenario Outline: Submitted task envelope -- task_id names the seller's real approval task (<approval_trigger>)
    Given a valid create_media_buy request with account "acc-001"
    And the account "acc-001" exists and is active
    And the approval scenario is <approval_trigger>
    When the Buyer Agent sends the create_media_buy request
    Then the response status should be "submitted"
    And the response should contain a task_id
    And the response should NOT contain "packages" field
    And the task_id should be the step_id of the approval workflow step awaiting the seller
    # 3.1.1 create-media-buy-response.json oneOf CreateMediaBuySubmitted (L218-270):
    #   required ["status","task_id"]; status const "submitted";
    #   not.anyOf [{required:[media_buy_id]}, {required:[packages]}].
    # task_id is "the task handle the buyer uses with tasks/get" (L227-230), so it MUST
    # name a task the seller actually holds. Production returns the approval workflow
    # step's step_id after moving that step to status "requires_approval"
    # (src/core/tools/media_buy_create.py::_submitted_approval_result) -- the last Then
    # grades that identity. It is the green analogue of the storyboard's
    # $context.forced_task_id round-trip, which we cannot run: it needs
    # comply_test_controller/force_create_media_buy_arm, and we declare no
    # compliance_testing block (src/core/tools/capabilities.py), so the storyboard
    # grades not_applicable for this agent -- hence @schema-v3.1, not @storyboard-v3.1.
    # media_buy_id / confirmed_at / revision absence is graded by @T-UC-002-alt-manual
    # and is deliberately not repeated here.
    # @source repo=adcp ref=v3.1.1 path=static/schemas/source/media-buy/create-media-buy-response.json#L218-L270
    # storyboard (informational, NOT on our conformance path):
    #   dist/compliance/3.1.1/protocols/media-buy/scenarios/create_media_buy_async.yaml
    #   phase=submitted_arm_response step=create_media_buy_submitted (L217-237)

    Examples: Production triggers of the submitted arm
      | approval_trigger         |
      | pending_human_review     |
      | pending_adapter_approval |
```

### Required companion edit (conftest — without it the scenario stays dormant)

`tests/bdd/conftest.py:2816`

```python
_UC002_MANUAL_APPROVAL_WIRED: set[str] = {
    "T-UC-002-alt-manual",
    "T-UC-002-storyboard-governance-with-conditions",          # sibling agent, already in working tree
    "T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip",
}
```

This is what routes the scenario to `MediaBuyCreateEnv` and sets `ctx["uc002_full_create"]`, which in
turn makes the shared When step dispatch a full create through all four transports
(`tests/bdd/steps/domain/uc002_create_media_buy.py:740-754`).

### Why each row is green

* Givens are the exact trio `@T-UC-002-alt-manual` uses (feature L64-66), which passes on all four
  transports and appears in **no** ledger (`tests/bdd/conftest.py`, `tests/bdd/e2e_rest_known_failures.txt`).
* `the approval scenario is <partition>` (`tests/bdd/steps/generic/given_media_buy.py:255`) dispatches
  `pending_human_review` → tenant `human_review_required=True`; `pending_adapter_approval` → tenant
  auto-approve + adapter `manual_approval_required=True` with `manual_approval_operations =
  {"create_media_buy","update_media_buy"}` (`given_media_buy.py:180`), and both write through to the
  DB via `_sync_adapter_approval_to_db` so the Docker-hosted adapter agrees in e2e.
* Production gate: `manual_approval_required = tenant_approval_required or adapter_approval_required`
  and `"create_media_buy" in manual_approval_operations`
  (`src/core/tools/media_buy_create.py:2705-2725`) → both rows reach
  `_submitted_approval_result(step, req, adapter)` at `media_buy_create.py:3096`.
* `_submitted_approval_result` (`media_buy_create.py:1827-1844`) returns
  `CreateMediaBuySubmitted(task_id=step.step_id, context=req.context, errors=…)` wrapped with
  `status="submitted"`; `TaskResultEnvelope._serialize` (`src/core/schemas/_base.py:467-471`) flattens
  it and stamps the top-level `status`. So `status == "submitted"`, `task_id` non-empty, `packages`
  absent (the model has no such field).
* The step immediately before returning sets that workflow step to `status="requires_approval"`
  (`media_buy_create.py:2760-2764` for the tenant/adapter branch), which is what the new Then compares
  against.
* The adapter-only trigger is the create-side mirror of `T-UC-003-approval-adapter`, which conftest
  records as **graduated** across transports (`tests/bdd/conftest.py:561`).

---

## 6. Step inventory

**Existing — reused verbatim, no new code**

| Step | Owner |
|---|---|
| `Given a valid create_media_buy request with account "{account_id}"` | `tests/bdd/steps/domain/uc002_create_media_buy.py:119` |
| `And the account "{account_id}" exists and is active` | `tests/bdd/steps/domain/uc002_create_media_buy.py:264` |
| `And the approval scenario is {partition}` | `tests/bdd/steps/generic/given_media_buy.py:255` |
| `When the Buyer Agent sends the create_media_buy request` | `tests/bdd/steps/domain/uc002_create_media_buy.py:713` |
| `Then the response status should be "{status}"` | `tests/bdd/steps/generic/then_success.py:40` |
| `And the response should contain a task_id` | `tests/bdd/steps/domain/uc003_update_media_buy.py:1157` (wire-based, transport-generic) |
| `And the response should NOT contain "{field_name}" field` | `tests/bdd/steps/domain/uc003_update_media_buy.py:1197` (wire-based; includes the A2A no-artifact guard) |

**New — one step**, to be added to `tests/bdd/steps/domain/uc002_create_media_buy.py`:

```python
@then("the task_id should be the step_id of the approval workflow step awaiting the seller")
def then_task_id_is_the_approval_step(ctx: dict) -> None:
    """3.1.1 create-media-buy-response.json L227-230: task_id is "the task handle the
    buyer uses with tasks/get". Grade that the handle names the seller's REAL persisted
    approval task rather than a fabricated value — the green analogue of the
    create_media_buy_async storyboard's $context.forced_task_id round-trip, which needs
    a comply_test_controller we do not expose. Production returns step.step_id from
    _submitted_approval_result after moving that step to status "requires_approval".
    """
    from tests.bdd.steps._outcome_helpers import wire_dict

    task_id = wire_dict(ctx).get("task_id")
    steps = ctx["env"].get_workflow_steps()
    named = [s for s in steps if s.step_id == task_id]
    assert len(named) == 1, (
        f"task_id {task_id!r} must name exactly one persisted workflow step, matched "
        f"{len(named)}; persisted step_ids={[s.step_id for s in steps]}"
    )
    assert named[0].status == "requires_approval", (
        f"the task named by task_id must be the approval task awaiting the seller, "
        f"got status {named[0].status!r}"
    )
```

Both assertions compare concrete values (`test_architecture_bdd_no_trivial_assertions.py`), the step
body asserts rather than delegating (`..._no_pass_steps.py`), no `ctx.get("env")` /
`hasattr(env, …)` (`..._no_silent_env.py`), and it reuses `wire_dict` +
`env.get_workflow_steps()` (`tests/harness/_base.py:1303`) rather than opening a session
(repository-pattern guard).

---

## 7. TICKET MATERIAL

* **`context` is never echoed on the submitted envelope, and nothing grades it.**
  3.1.1 `create-media-buy-response.json` CreateMediaBuySubmitted `context` (L240-243):
  *"Sellers MUST echo this object verbatim when the originating request carried context, including
  synchronous success, error, submitted, and webhook task-status payloads."* The storyboard grades it
  twice (`create_media_buy_async.yaml:231-237` — `field_present: context`,
  `field_value: context.correlation_id`). Production does pass it through
  (`src/core/tools/media_buy_create.py:1839` `context=req.context`), but no BDD Given sets
  `context` on a create request and no Then asserts the echo, so the MUST is untested on every
  branch. Needs: a `Given the request carries context correlation_id "<id>"` and a wire-level echo
  Then, applied to the success, error and submitted branches.

* **`T-UC-002-partition-approval-workflow` asserts a status production stopped emitting.**
  `_assert_workflow_outcome` (`tests/bdd/steps/domain/uc002_create_media_buy.py:1105-1109`) requires
  `status == "pending_approval"` for outcome `manual approval required`. Since PR #1567 the
  manual-approval branch returns `CreateMediaBuySubmitted` with `status="submitted"`
  (`src/core/tools/media_buy_create.py:1837-1844`), and `pending_approval` is not even a member of
  the 3.1.1 `MediaBuyStatus` enum — the schema says so explicitly at
  `create-media-buy-response.json:220` ("Do not use a 'pending_approval' MediaBuy.status for this
  case — that value is not in MediaBuyStatus"). The assertion is only invisible because the scenario
  is blanket-xfailed by `tests/bdd/conftest.py:3282`. Fix the oracle when the scenario is wired,
  otherwise wiring it flips it red.

* **`@T-UC-002-v31-submitted-envelope-shape` is permanently dormant and duplicates live coverage.**
  `tests/bdd/features/BR-UC-002-create-media-buy.feature:1964-1976` uses
  `the response should not include a media_buy_id at the envelope level` and
  `… a packages array at the envelope level` — neither phrasing exists in `tests/bdd/steps/`
  (`grep` → zero hits), so the scenario auto-xfails at `tests/bdd/conftest.py:99`. Its content is a
  subset of `@T-UC-002-alt-manual` plus the `packages` clause the proposal above picks up. Retire it
  or re-point it at the existing phrasings; do not wire a third copy.

* **`_submitted_wire_dict` duplicates `wire_dict`.**
  `tests/bdd/steps/domain/uc003_update_media_buy.py:1135-1154` is a line-for-line re-implementation
  of `tests/bdd/steps/_outcome_helpers.py:43-59` (same guard, same IMPL fallback, same docstring
  argument). DRY invariant (CLAUDE.md): delete the UC-003 copy and import the shared helper. Two
  copies means the next fix to the wire-guard lands in one of them only.

* **`task_id` stability across an idempotent replay is implemented but ungraded.**
  `_cache_and_return` (`src/core/tools/media_buy_create.py:1866-1874`) and `_replay_cached_success`
  (`:1738-1748`) exist specifically so a replayed pending-approval create returns the *same*
  `task_id` instead of minting a second workflow step. Nothing tests it: the only replay seed Given
  (`tests/bdd/steps/domain/uc002_create_media_buy.py:1567`) hard-asserts `media_buy_id` on the first
  response and so cannot seed a submitted create, and the `uc002_full_create` When step mints a fresh
  `idempotency_key` per dispatch (`:748`). Needs one Given ("a create_media_buy with that
  idempotency_key was already submitted for approval") sharing the existing seed helper, plus a Then
  comparing the two `task_id`s. Mandated by `core/protocol-envelope.json` `replayed` +
  `universal/idempotency.yaml`; it is also the closest we can get to the storyboard's
  "sellers that fabricate a fresh task_id" invariant.

* **The submitted `task_id` is not proven resolvable through a buyer-facing read.**
  Schema L227-230 defines `task_id` as the handle "the buyer uses with tasks/get". Our grading (and
  the proposal above) reaches the workflow step through the harness DB, not through a protocol call.
  `list_tasks` exists (`src/core/tools/task_management.py`) and UC-002 has a task-list When step
  (`tests/bdd/steps/domain/uc002_task_query.py:247`), but no scenario chains create → task read on
  the returned `task_id`. That chain is the real buyer polling contract.

* **We advertise no `compliance_testing` block, which silently removes `create_media_buy_async`
  from our conformance report.** `protocols/media-buy/index.yaml:22` lists
  `media_buy_seller/create_media_buy_async` under `requires_scenarios` for the protocol we *do*
  declare, so the runner will attempt it and grade `not_applicable`. Decide explicitly: either
  implement `comply_test_controller` + `force_create_media_buy_arm` and declare
  `compliance_testing.scenarios` (`get-adcp-capabilities-response.json:1431-1445`), or record the
  permanent `not_applicable` as a conscious conformance-surface decision. Today it is neither — it
  is an accident that also produced this dead BDD scenario.

---

## 8. Risks

* **Not executed.** The `salesagent-sbsweep` worktree has uncommitted edits from concurrent sibling
  agents (`tests/bdd/conftest.py`, `tests/bdd/features/BR-UC-002-create-media-buy.feature`,
  `tests/bdd/steps/domain/uc002_create_media_buy.py`), and the brief is propose-only, so I did not
  start `agent-db` and run the suite. Greenness is argued from source, not observed. The two
  load-bearing unverified claims are (a) the `pending_adapter_approval` row reaching the submitted
  branch on `e2e_rest`, and (b) `env.get_workflow_steps()` reading Docker's DB under `e2e_rest`.
* On (b): `tests/bdd/steps/domain/uc002_task_query.py:200-205` states the harness session is bound to
  the correct DB in both modes and uses it deliberately *because* `get_db_session()` is not, and
  `uc006_sync_creatives.py:599-606` asserts on `env.get_workflow_steps()` with no `e2e_rest` ledger
  entry. That is strong but indirect evidence.
* **Conftest coupling.** The proposal is not a pure `.feature` edit — without the
  `_UC002_MANUAL_APPROVAL_WIRED` addition the scenario silently stays xfailed and the whole exercise
  is a no-op. If the baseline PR is meant to touch only feature files, this scenario cannot become
  live in it.
* **Sibling collision.** Another agent is adding
  `the create_media_buy response should not carry a "{field}" field` (uncommitted, `wire_dict`-based)
  to the same module. It overlaps semantically with the committed
  `the response should NOT contain "{field}" field`. I deliberately used the committed one; if the
  sibling's step lands, the two should be reconciled to one (DRY / `..._no_duplicate_steps.py`).
* **Examples-row cost.** Each row re-runs a full create across four transports — eight dispatches for
  this scenario. Acceptable, but it is not free.
* **3.1.8 / HEAD drift not assessed.** I read only `v3.1.1` and the stale `04f59d2d5`, per the brief.

---

Summary:

1. Verdict: **NOT GRADED — undeclared gate**; drop `@storyboard-v3.1`, keep `@schema-v3.1`.
2. Real storyboard is `create_media_buy_async.yaml`, phase `submitted_arm_response`, L217-237 — the footer's `governance_approved.yaml` is the next scenario's, the classic off-by-one.
3. Stale ref confirmed: `04f59d2d5` is an ancestor of `v3.1.1` by 717 commits; only `sample_request` drifted, the `validations:` did not.
4. Every graded step needs `comply_test_controller`; `grep src/` returns zero hits and we emit no `compliance_testing` block, so the storyboard grades `not_applicable` for us.
5. The envelope itself is still normative — `CreateMediaBuySubmitted` (L218-270): `required [status, task_id]`, `status` const `submitted`, `not.anyOf` on `media_buy_id` and `packages`.
6. The scenario was doubly dormant: all seven of its steps are fictional, and its tag is absent from `_UC002_MANUAL_APPROVAL_WIRED` so conftest blanket-xfails it.
7. Rewrite is a `Scenario Outline` over the two production triggers of the submitted arm (`pending_human_review`, `pending_adapter_approval`), reusing seven existing steps.
8. One new Then grades the real round-trip we can grade: `task_id` names exactly one persisted workflow step whose status is `requires_approval`.
9. Requires one conftest line — adding the tag to `_UC002_MANUAL_APPROVAL_WIRED` — or it stays xfailed.
10. Seven follow-ups filed as ticket material; largest are the ungraded `context`-echo MUST, the stale `pending_approval` oracle, and the duplicated `_submitted_wire_dict`.

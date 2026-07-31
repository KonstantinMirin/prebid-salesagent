# Re-pin: `@T-UC-003-storyboard-package-not-found`

Scenario: `tests/bdd/features/BR-UC-003-update-media-buy.feature:2063`
Title: "update_media_buy with known media_buy_id but unknown package_id returns PACKAGE_NOT_FOUND"

---

## 1. VERDICT

**GRADED** — and doubly so. `PACKAGE_NOT_FOUND` is graded by exactly one storyboard at 3.1.1,
`media_buy_seller/invalid_transitions`, phase `unknown_package`. That storyboard is listed under
`requires_scenarios` of **both**:

- `protocols/media-buy/index.yaml:19` — we declare `supported_protocols=[media_buy]`
  (`src/core/tools/capabilities.py:99`), and
- `specialisms/sales-non-guaranteed/index.yaml:21` — we declare
  `specialisms=[sales_non_guaranteed]` (`src/core/tools/capabilities.py:100`).

Tier: **`protocols/`** (mirrored byte-identically under `domains/media-buy/`; `diff` is empty).
Gate: `agent.capabilities: [sells_media]` only — no capability we fail to declare.
The `@storyboard-v3.1` tag is **justified**. Keep it. Do NOT downgrade to `@schema-v3.1`.

**But the scenario does not run.** It is dormant twice over, which the binding sweep did not detect:

1. **Env gate.** `tests/bdd/conftest.py:3303` admits UC-003 scenarios to `MediaBuyDualEnv` only when a
   tag starts with `T-UC-003-ext-` or is in the targeting-overlay / manual-approval sets. This tag is
   none of those, so it falls to `pytest.xfail(...)` at `tests/bdd/conftest.py:3359`
   ("UC-003 harness not yet wired for non-extension scenarios").
2. **Missing steps.** None of its four step texts exist anywhere in `tests/bdd/steps/`. Even past the
   env gate, `tests/bdd/conftest.py:99` auto-converts `StepDefinitionNotFoundError` to xfail.

So today the tag asserts a conformance claim that is never executed. Re-pinning the footer without
un-dormanting it would leave that claim false.

---

## 2. Real binding at 3.1.1

**Correct location:**
`/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml`
— phase `unknown_package` (line 169), step `update_unknown_package` (line 177), graded block at
**lines 205–215**.

Verified identical to the tag: `git show v3.1.1:dist/compliance/3.1.1/…` diffs clean against the
on-disk file, and against `git show v3.1.1:static/compliance/source/protocols/…` — all three agree.

Graded `validations:` verbatim (lines 205–215):

```yaml
        validations:
          - check: error_code
            value: "PACKAGE_NOT_FOUND"
            description: "Error code is PACKAGE_NOT_FOUND"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object even on errors"
          - check: field_value
            path: "context.correlation_id"
            value: "invalid_transitions--update_unknown_package"
            description: "Context correlation_id returned unchanged"
```

The request the storyboard grades this against (lines 193–204) — note it is a **package budget
update**, which is exactly the production branch that raises:

```yaml
        sample_request:
          account:
            brand:
              domain: "acmeoutdoor.example"
            operator: "pinnacle-agency.example"
          media_buy_id: "$context.media_buy_id"
          idempotency_key: "$generate:uuid_v4#update_unknown_package"
          packages:
            - package_id: "does-not-exist-package-invalid-transitions-v1"
              budget: 5001
          context:
            correlation_id: "invalid_transitions--update_unknown_package"
```

**What the current footer points at.** Unlike 16 of the 40 swept scenarios, this one is **not**
off-by-one — the cited *filename* is right:

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/invalid_transitions.yaml
```

Two defects remain:
- `ref=v3.1-04f59d2d5 commit=04f59d2d5` is an **ancestor of beta.3**, older than our own 3.1.1 pin.
- `path=static/compliance/source/…` is the **generator input**, which is unversioned and tracks HEAD.
  At `v3.1.1` it happens to equal the dist output, but that is a coincidence of that tag, not a
  guarantee. Cite the version-frozen `dist/compliance/3.1.1/…` path instead.

Also worth recording: `expected:` at lines 187–191 mentions `recovery: correctable`, but there is **no
`- check:` for recovery** — not in this file, and not in `universal/error-compliance.yaml` either
(every `validations:` block there grades only `error_code`, `field_present: context`, and
`field_value: context.correlation_id`). Recovery is **prose, therefore ungraded by the storyboard**.
It is nonetheless mandated by schema — see §3 — so the proposed scenario asserts it, on schema
authority rather than storyboard authority.

---

## 3. Schema constraints at 3.1.1

**`PACKAGE_NOT_FOUND` is in the enum.** `static/schemas/source/enums/error-code.json` @ `v3.1.1`
carries 92 codes; `PACKAGE_NOT_FOUND` is one of them. `enumMetadata.PACKAGE_NOT_FOUND`:

```json
{
  "recovery": "correctable",
  "suggestion": "verify package_id; for legacy package correlation use get_media_buys plus package context, such as context.buyer_ref"
}
```

with `enumDescriptions`: *"Referenced package does not exist within the specified media buy. Recovery:
correctable (verify package_id within the media buy…)."*

**Recovery is schema-normative.** `static/schemas/source/core/error.json` @ `v3.1.1`, `recovery`:

> "Senders SHOULD populate `recovery` on every error from 3.1 onward — it is the normative carrier of
> recovery semantics across version skew. A receiver that does not recognize `error.code` … MUST still
> be able to classify the error from `recovery`. The `enumMetadata.recovery` block in
> `enums/error-code.json` is the documentary mirror for known codes; **`error.recovery` on the wire is
> authoritative**."

`error.json` `required: ["code", "message"]`; `code` is `type: string`, `minLength: 1`,
`maxLength: 64` — an **open** vocabulary, not a closed enum.

**Context echo is schema-normative and MUST-level.**
`static/schemas/source/media-buy/update-media-buy-response.json` @ `v3.1.1`, the `UpdateMediaBuyError`
branch (`required: ["errors"]`, properties `errors`, `context`, `ext`), on `context`:

> "Opaque operation-level correlation data echoed unchanged from the update_media_buy request. Sellers
> **MUST echo this object verbatim** when the originating request carried context, including
> synchronous success, **error**, submitted, and webhook task-status payloads. Sellers MUST NOT parse
> this object for business logic."

`static/schemas/source/core/context.json` @ `v3.1.1` is `type: object`, `additionalProperties: true`
with no declared properties — `correlation_id` is a **caller-chosen key**, not a spec field. Verified
the SDK honours this: `adcp.types.ContextObject` has `model_config = {'extra': 'allow'}` and
round-trips `correlation_id` through `model_dump(mode="json", exclude_none=True)`.

**Request side.** `static/schemas/source/media-buy/update-media-buy-request.json` @ `v3.1.1`:
`required: ["idempotency_key", "account", "media_buy_id"]`; `packages` is
`{"type":"array","minItems":1,"items":{"$ref":"/schemas/media-buy/package-update.json"}}`;
`context` is `{"$ref":"/schemas/core/context.json"}`.
`package-update.json` @ `v3.1.1`: `required: ["package_id"]`; `budget` is
`{"type":"number","minimum":0}`.

**Envelope.** `core/protocol-envelope.json` @ `v3.1.1` is `required: ["status"]` and is `allOf`-mixed
into the update response. We emit no top-level `status` — already-known gap, not re-filed.

---

## 4. Conflicts

**Schema overrides storyboard on `recovery`.** The storyboard grades only three checks and leaves
recovery in prose. The 3.1.1 `core/error.json` makes `error.recovery` the authoritative wire carrier
and `enums/error-code.json` classifies `PACKAGE_NOT_FOUND` as `correctable`. **The schema wins** — the
proposed scenario asserts recovery even though the storyboard does not grade it. Production already
emits it (`src/core/exceptions.py:692-693`, `_default_recovery = "correctable"`), so this is free.

**What the current scenario gets wrong:**

- **It never executes.** Two independent dormancy gates (§1). Everything below is downstream of that.
- **`Then the operation should fail`** is a bare failure check — passes on any error at all, including
  the wrong code. It only survives because a later step pins the code.
- **`And the response should NOT be a 500 or non-AdCP error shape`** (present on the sibling
  media-buy-not-found scenario, same cluster) is a negative existence assertion with no concrete
  comparison. `test_architecture_bdd_no_trivial_assertions.py` would reject it. Dropped.
- **`And the error code should be "PACKAGE_NOT_FOUND"`** resolves through
  `tests/bdd/steps/generic/then_error.py:270`, which falls back to the *reconstructed* `ctx["error"]`
  when no wire envelope is present. That violates the Error Verification Policy. Routing through
  `the result should be error "…"` instead reaches `result.assert_wire_error(...)`
  (`tests/bdd/steps/domain/uc002_create_media_buy.py:1343` →
  `tests/harness/transport.py:144`), which asserts `assert_envelope_shape` on the real
  `wire_error_envelope` for both layers plus recovery.
- **It misses the storyboard's own discriminator.** The scenario's prose says PACKAGE_NOT_FOUND is
  meaningful precisely because it is *"distinguishing from MEDIA_BUY_NOT_FOUND"*, but a single row
  asserting one code proves nothing about the distinction. That is what the `Scenario Outline` below
  is for.
- **It asserts nothing about POST-F1** despite the feature's stated postcondition set.
- **`recovery` is asserted nowhere**, although it is the schema-authoritative field.

**Verified green against current production** (read, not guessed):

- `src/core/tools/media_buy_update.py:832-834` — the budget branch calls
  `uow.media_buys.get_package_or_raise(req.media_buy_id, pkg_update.package_id, context=req.context)`.
  This is the exact storyboard payload shape (`packages[0].{package_id, budget}`).
- `src/core/database/repositories/media_buy.py:192-209` — raises `AdCPPackageNotFoundError` with a
  `suggestion` and the request `context` attached.
- `src/core/exceptions.py:684-693` — `_default_error_code = "PACKAGE_NOT_FOUND"`,
  `_default_recovery = "correctable"`.
- `src/core/exceptions.py:1023-1025` — `build_two_layer_error_envelope` echoes the serialized context.
  Executed end-to-end to confirm, not inferred:

  ```
  {"adcp_error": {"code": "PACKAGE_NOT_FOUND", "recovery": "correctable", "suggestion": "…"},
   "errors": [{"code": "PACKAGE_NOT_FOUND", "recovery": "correctable", "suggestion": "…"}],
   "context": {"correlation_id": "invalid_transitions--update_unknown_package"}}
  ```

- All four boundaries build that same envelope: `src/app.py:155` (REST),
  `src/core/tool_error_logging.py:295` (MCP), `src/a2a_server/adcp_a2a_server.py:180,628` (A2A).
  The harness captures the raw body verbatim: `tests/harness/dispatchers.py:169` (REST body),
  `:201` (MCP `ToolError` JSON), `tests/harness/_base.py:263` (A2A artifact stash).
- `context` plumbs on every transport: `src/core/tools/media_buy_update.py:1536` (MCP tool param),
  `:1615` (A2A raw param), `:1489-1490` (`_build_update_request`), `src/routes/api_v1.py:113` (REST
  body field). It is **not** in the harness's `_WRAPPER_UNSUPPORTED_FIELDS`
  (`tests/harness/media_buy_update.py:49-60`), so `_flatten_update_request`
  (`tests/harness/media_buy_dual.py:181`) forwards it.
- The MEDIA_BUY_NOT_FOUND discriminator row is green: `_verify_principal` runs at
  `src/core/tools/media_buy_update.py:403` — long before the packages loop at `:763` — and
  `get_by_id_or_raise` (`src/core/database/repositories/media_buy.py:81-85`) raises with a suggestion
  and context. `T-UC-003-ext-b` already passes on that path today.
- `PACKAGE_NOT_FOUND` and `MEDIA_BUY_NOT_FOUND` are both present in the vendored pinned enum
  (`tests/fixtures/adcp_schemas_pinned/enums/error-code.json`, 64 codes) with
  `recovery: correctable`, so `assert_wire_error`'s canonical-code gate
  (`tests/harness/transport.py:166`) passes and its default recovery matches 3.1.1.

---

## 5. Proposed Gherkin

Replaces lines 2062–2075 of `tests/bdd/features/BR-UC-003-update-media-buy.feature`.
Transport-independent — no branching. Every `Then` compares a concrete value.

```gherkin
  @T-UC-003-storyboard-package-not-found @storyboard-v3.1 @v3-1 @structured-errors @package-not-found @post-f1 @post-f2 @post-f3
  Scenario Outline: update_media_buy lookup failure resolves at the level that actually failed - <partition>
    Given media buy "<media_buy_id>" <media_buy_presence> in the seller catalog
    And package "<package_id>" <package_presence> in media buy "<media_buy_id>"
    And a valid update_media_buy request with:
    | field        | value          |
    | media_buy_id | <media_buy_id> |
    And the request includes 1 package update with:
    | field      | value        |
    | package_id | <package_id> |
    | budget     | 5001         |
    And the request carries context.correlation_id "<correlation_id>"
    When the Buyer Agent sends the update_media_buy request
    Then the result should be error "<error_code>" correctable with suggestion
    And the response should echo context.correlation_id "<correlation_id>" unchanged
    And no database records should be modified
    # invalid_transitions phase `unknown_package` (step `update_unknown_package`) grades exactly three
    # things: error_code == PACKAGE_NOT_FOUND, context present on the ERROR response, and
    # context.correlation_id echoed unchanged. The storyboard's own narrative states the point is that
    # PACKAGE_NOT_FOUND is "distinct from MEDIA_BUY_NOT_FOUND — because the lookup succeeds at the buy
    # level and only fails at the package lookup", so the second row pins that discrimination: the same
    # package payload against an absent buy must resolve at the BUY level instead. Production orders it
    # that way (media_buy_update.py:403 ownership/lookup, then :763 the packages loop).
    #
    # `correctable` is NOT graded by the storyboard — `expected:` mentions it in prose and no
    # `- check:` covers it, in this file or in universal/error-compliance.yaml. It is asserted here on
    # SCHEMA authority: core/error.json @ v3.1.1 makes `error.recovery` "authoritative" on the wire,
    # and enums/error-code.json @ v3.1.1 classifies both codes `correctable`.
    #
    # Not asserted, deliberately: top-level `status`. core/protocol-envelope.json @ v3.1.1 is
    # `required: ["status"]` and we emit none — see #<envelope-status-issue>.
    # @source repo=adcp ref=v3.1.1 commit=v3.1.1 path=dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml phase=unknown_package step=update_unknown_package

    Examples: invalid_transitions error-level discrimination
      | partition                | media_buy_id   | media_buy_presence | package_id      | package_presence | error_code          | correlation_id                                |
      | package_absent_from_buy  | mb_existing    | exists             | pkg_nonexistent | does not exist   | PACKAGE_NOT_FOUND   | invalid_transitions--update_unknown_package   |
      | buy_absent_entirely      | mb_nonexistent | does not exist     | pkg_nonexistent | does not exist   | MEDIA_BUY_NOT_FOUND | invalid_transitions--update_unknown_media_buy |
```

**The footer must be accompanied by the two un-dormanting edits, or the tag stays a false claim:**

1. `tests/bdd/conftest.py:3303` — add `"T-UC-003-storyboard-package-not-found"` to the set of tags
   admitted to `MediaBuyDualEnv`. That branch already seeds `existing_media_buy` + `pkg_001` via
   `_setup_existing_media_buy` (`conftest.py:3322`) and sets `env._seeded_media_buy_id`, which is
   exactly what these rows need. Prefer a named set (e.g. `_UC003_STORYBOARD`) over widening the
   `startswith` prefix, so sibling storyboard scenarios graduate one at a time.
2. Add the four new step definitions in §6.

---

## 6. Step inventory

**Existing — reused unchanged (5):**

| Step text | Owner |
|---|---|
| `Given a valid update_media_buy request with:` | `tests/bdd/steps/domain/uc003_update_media_buy.py:242` |
| `Given the request includes 1 package update with:` | `tests/bdd/steps/domain/uc003_update_media_buy.py:344` |
| `When the Buyer Agent sends the update_media_buy request` | `tests/bdd/steps/domain/uc003_update_media_buy.py:788` |
| `Then the result should be <outcome>` | `tests/bdd/steps/domain/uc002_create_media_buy.py:834` → `_assert_error_outcome:1287` → `result.assert_wire_error` |
| `Then no database records should be modified` | `tests/bdd/steps/domain/uc003_ext_error_scenarios.py:813` |

The outcome string `error "PACKAGE_NOT_FOUND" correctable with suggestion` parses cleanly through the
existing branch: `_assert_error_outcome` strips the quotes (`parts[0].strip('"')`, line 1333), detects
the structured code, reads `correctable` from `parts[1]` (line 1338), sets `require_suggestion` from
the `"with suggestion"` substring (line 1339), and dispatches to
`result.assert_wire_error(code, recovery=..., require_suggestion=True)` (line 1343). Quoted codes in
outline rows are already the established convention there.

**New — 4 phrasings, all thin:**

| Step text | Where it belongs | What it does |
|---|---|---|
| `Given media buy "{media_buy_id}" {presence} in the seller catalog` | `uc003_ext_error_scenarios.py` | `presence` is `exists` / `does not exist`. Delegate to the same helpers the existing guards use — reuse `given_no_media_buy_by_id`'s delete-and-verify body (`:115-138`) for the absent branch and `_verify_existing_media_buy` for the present branch. Must NOT re-implement either (DRY). |
| `Given package "{package_id}" {presence} in media buy "{media_buy_id}"` | `uc003_ext_error_scenarios.py` | Same two-valued presence. The absent branch is the existing `given_package_not_in_media_buy` body (`:254-280`) with the buy id passed in rather than read from `ctx["existing_media_buy"]`; the present branch is `given_package_exists_bare` (`:283-294`). Extract the shared bodies into helpers and have both the old and new steps call them. |
| `Given the request carries context.correlation_id "{correlation_id}"` | `uc003_update_media_buy.py` | `_ensure_update_defaults(ctx)["context"] = ContextObject(correlation_id=correlation_id)`. A separate step rather than a new row in `given_update_request_with_table`'s `_supported_fields` (`:248-257`) — that table maps a flat scalar per field and would have to magic a bare string into a nested object. |
| `Then the response should echo context.correlation_id "{correlation_id}" unchanged` | `then_error.py` (generic — the contract is not UC-003-specific) | Read `ctx["result"].wire_error_envelope`; assert it is not `None`, assert `envelope["context"]["correlation_id"] == correlation_id`. Wire-only, no reconstructed fallback: a reconstructed `AdCPError` would make the assertion vacuous, and the point of the graded check is what the buyer actually receives. |

Two of these guards are two-valued booleans, not dispatch chains — implement as
`absent = presence.strip() == "does not exist"` with an explicit
`assert presence in {"exists", "does not exist"}`, not an `if/elif` ladder.

---

## 7. TICKET MATERIAL

Everything here is out of scope for a green baseline PR.

- **UC-003 storyboard scenarios are dormant behind the conftest env gate.**
  `tests/bdd/conftest.py:3303` admits only `T-UC-003-ext-*` plus two named sets to `MediaBuyDualEnv`;
  every other UC-003 scenario hits `pytest.xfail` at `tests/bdd/conftest.py:3359`. All five
  `@storyboard-v3.1` UC-003 scenarios (feature lines 2048, 2063, 2078, 2094, and the
  `T-UC-003-v31-error-*` cluster above them) therefore assert conformance that is never executed. The
  proposal graduates one of them; the remaining four need the same treatment or their tags should be
  removed. Mandate: they carry `@storyboard-v3.1`, which claims grading against
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml` and
  `…/creative_fate_after_cancellation.yaml`.

- **No top-level `status` on any update_media_buy response.**
  `core/protocol-envelope.json` @ `v3.1.1` is `allOf`-mixed into
  `media-buy/update-media-buy-response.json` and declares `required: ["status"]`, with prose: *"Agents
  shipping responses without a top-level `status` are non-conformant regardless of whether the task
  body schema would otherwise validate."* Known gap — cite the existing envelope-status issue, do not
  re-file. It is why the proposed scenario cannot assert `status: "failed"`.

- **`then_response_schema_valid` runs no validator.** The storyboard's sibling steps
  (`get_products_brief`, `create_buy`, `first_cancel` in the same file, lines 123-125, 162-164,
  248-250) are graded by `- check: response_schema`. We have
  `tests/helpers/pinned_schema.py::validate_against_pinned_schema` and never call it. Known gap —
  cite, do not re-file. Consequence for this scenario: no `Then` can honestly claim the error body
  validates against `update-media-buy-response.json`'s `UpdateMediaBuyError` branch, so none is
  proposed.

- **`tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not 3.1.1 — and it gates error
  assertions.** `TransportResult.assert_wire_error` (`tests/harness/transport.py:164-169`) rejects any
  code absent from that 64-code snapshot; 3.1.1 has 92. `PACKAGE_NOT_FOUND` and `MEDIA_BUY_NOT_FOUND`
  happen to be in both, with matching `recovery: correctable`, so this scenario is unaffected — but
  the gate silently blocks any scenario grading one of the 28 codes 3.1.1 added. Known gap — cite, do
  not re-file.

- **`NOT_CANCELLABLE` is graded in the same file and the sibling scenario cites the wrong storyboard.**
  `T-UC-003-storyboard-not-cancellable-on-recancel` (feature line 2078) cites
  `creative_fate_after_cancellation.yaml`; the graded block is
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml` phase `double_cancel`,
  step `second_cancel`, lines 279–289. Independently corroborated by
  `dist/compliance/3.1.1/protocols/media-buy/state-machine.yaml:474-495`, which grades the same
  NOT_CANCELLABLE-over-INVALID_STATE precedence and cites `media_buy_seller/invalid_transitions` as
  the canonical vector. Owned by another agent in this sweep — flagged here only because it is the
  same file, one phase over.

- **Cross-media-buy package reference is untested.**
  `MediaBuyRepository.get_package` (`src/core/database/repositories/media_buy.py:180-190`) filters on
  `(tenant_id, media_buy_id, package_id)`, so a package_id belonging to a *different* buy in the same
  tenant correctly yields `PACKAGE_NOT_FOUND`. No BDD row covers it, and it is the sharper reading of
  the scenario's own title ("a package_id that does not belong to the media buy"). Not proposed as an
  Examples row because it needs a second seeded media buy + package, which `_setup_existing_media_buy`
  (`tests/bdd/conftest.py:3030`) does not create — a fixture change, not a green baseline edit.
  Mandate: `invalid_transitions.yaml:171-174` — *"the seller must return PACKAGE_NOT_FOUND … because
  the lookup succeeds at the buy level and only fails at the package lookup."*

- **`account` and `idempotency_key` are required by the 3.1.1 request schema and we do not enforce
  them on update.** `update-media-buy-request.json` @ `v3.1.1` is
  `required: ["idempotency_key", "account", "media_buy_id"]`; `UpdateMediaBuyRequest`
  (`src/core/schemas/_base.py:2005-2011`) overrides both to optional, with an in-code note calling the
  required-key enforcement "a deliberate fast-follow". The harness compounds it —
  `account` is in `_WRAPPER_UNSUPPORTED_FIELDS` (`tests/harness/media_buy_update.py:50`) and is
  stripped before dispatch, so the storyboard's `account` block cannot even reach production through
  BDD. The proposed scenario therefore sends neither field, diverging from the storyboard's
  `sample_request`.

---

## 8. Risks

- **Not executed.** The proposal was verified by reading production and by running the envelope
  builder end-to-end in-process (§4), but the scenario itself could not be run: activating it requires
  editing `tests/bdd/conftest.py` and adding step definitions inside
  `/Users/konst/projects/salesagent-sbsweep`, which the brief forbids. Highest-residual-risk
  assertion is the context echo on the **A2A** transport specifically — REST
  (`tests/harness/dispatchers.py:169`) and MCP (`:201`) capture the raw body/JSON directly, while A2A
  round-trips through `_envelope_to_adcp_error` (`tests/harness/_base.py:228-264`), which
  reconstructs an `AdCPError` and re-attaches the original envelope as `_wire_error_envelope`. The
  stash is the untouched dict, so `context` survives by construction — but that is a read, not a run.
  If it does turn red on a2a only, drop the echo `Then` from the outline and move it to TICKET
  MATERIAL as an A2A envelope-capture gap; the code + recovery + POST-F1 assertions stand alone.
- **Overlap with the sibling scenario.** Row 2 (`buy_absent_entirely`) asserts `MEDIA_BUY_NOT_FOUND`,
  which is also the whole subject of `T-UC-003-storyboard-media-buy-not-found` (feature line 2048),
  owned by `sb-uc003-mbnotfound`. The overlap is deliberate — the storyboard's stated point is the
  *discrimination between* the two codes, which one row cannot express — but the two proposals should
  be read together so the pair does not end up asserting the same thing twice. If the sibling's
  scenario also becomes an outline covering both codes, collapse mine to the single
  `package_absent_from_buy` row and let the sibling own the discrimination.
- **`no database records should be modified` on row 2.** The step reads `ctx["existing_media_buy"]`
  (`uc003_ext_error_scenarios.py:824`), which is the Background's `mb_existing` — untouched while the
  request targets `mb_nonexistent`, so the assertion holds but is weaker on that row than on row 1.
  Acceptable: POST-F1 is about the seeded state surviving, and it does.
- **`_resolve_media_buy_id` falls through to the literal** for unregistered labels
  (`uc003_update_media_buy.py:53-59`), which is what makes `mb_nonexistent` work. That is
  fall-through-by-design, matching `T-UC-003-ext-b`, but it means a typo in a label silently becomes a
  not-found id rather than failing loudly.
- **Drift beyond the pin.** 3.1.8 and HEAD were not consulted as authority. The only thing noted: the
  `dist/compliance/<version>/` tree ships a copy of `invalid_transitions.yaml` per version, so any
  future re-pin is a one-line path edit in the footer, not a re-derivation.
- **Tag-set change.** The proposal adds `@post-f1 @post-f2 @post-f3` to the scenario. These are
  registered dynamically by `pytest_configure` and are not keys in any UC-003 xfail map
  (`tests/bdd/conftest.py:659-702`), so they should be inert — but they are a tag-surface change on a
  file where tags drive env routing.

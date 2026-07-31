# Re-pin `@T-UC-003-storyboard-media-buy-not-found` against AdCP 3.1.1

Scenario: `tests/bdd/features/BR-UC-003-update-media-buy.feature:2047-2060`
Title: *update_media_buy with unknown media_buy_id returns structured MEDIA_BUY_NOT_FOUND, not a 500*

---

## 1. VERDICT

**GRADED.** The `@storyboard-v3.1` tag is justified.

The behaviour is graded at 3.1.1 by three `validations:` entries on step `update_unknown_media_buy`
(phase `unknown_media_buy`) of the `media_buy_seller/invalid_transitions` storyboard. The tier is
`protocols/media-buy/` — protocol `media_buy`, which `src/core/tools/capabilities.py:99` declares
(`supported_protocols=[SupportedProtocol.media_buy]`). No specialism gate applies: the storyboard's
`agent.capabilities: [sells_media]` is a free-form descriptor, **not** a member of the 3.1.1
specialism enum (`static/schemas/source/enums/specialism.json` — `sells_media` is absent; the
enum holds `sales-non-guaranteed`, `sales-guaranteed`, … ). So this scenario **is** on our
conformance path and the tag stays `@storyboard-v3.1`.

The cited `path=` is, unusually for this sweep, **correct**. The off-by-one defect is present two
scenarios downstream (`@T-UC-003-storyboard-not-cancellable-on-recancel` at line 2078 cites
`creative_fate_after_cancellation.yaml` while its own prose says *"invalid_transitions Phase 4
(double_cancel)"*) — not here. Only the `ref`/`commit` is stale and must move to `v3.1.1`.

Everything in the proposed Gherkin below was **executed green on a2a / mcp / rest** against a real
Postgres before being written down (see §8).

---

## 2. Real binding at 3.1.1

**File:** `/Users/konst/projects/adcp/dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml`
**Source of record at the tag:** `git show v3.1.1:static/compliance/source/protocols/media-buy/scenarios/invalid_transitions.yaml` — byte-identical to the `dist/3.1.1` rendering (verified by diff).
**Phase:** `unknown_media_buy` (line 45) · **Step:** `update_unknown_media_buy` (line 53)

Graded block, verbatim (lines **79-89**):

```yaml
        validations:
          - check: error_code
            value: "MEDIA_BUY_NOT_FOUND"
            description: "Error code is MEDIA_BUY_NOT_FOUND"
          - check: field_present
            path: "context"
            description: "Response echoes back the context object even on errors"
          - check: field_value
            path: "context.correlation_id"
            value: "invalid_transitions--update_unknown_media_buy"
            description: "Context correlation_id returned unchanged"
```

Governing request, verbatim (lines 69-78):

```yaml
        sample_request:
          account:
            brand:
              domain: "acmeoutdoor.example"
            operator: "pinnacle-agency.example"
          media_buy_id: "does-not-exist-invalid-transitions-v1"
          paused: true
          idempotency_key: "$generate:uuid_v4#update_unknown_media_buy"
          context:
            correlation_id: "invalid_transitions--update_unknown_media_buy"
```

**Graded vs. prose — the split that matters.** The step's `expected:` block (lines 63-67) reads:

```yaml
        expected: |
          Reject with:
          - code: MEDIA_BUY_NOT_FOUND
          - recovery: correctable
          - context echoed unchanged
```

`recovery: correctable` appears **only** here, under `expected:` — it is narrative prose and is
**NOT storyboard-graded**. It survives in the proposed scenario anyway, because the **3.1.1 schema**
mandates it independently (§3), and schema outranks storyboard.

Likewise `negative_path: payload_well_formed` / the narrative *"a seller that returns a 500 …
fails the scenario outright"* (lines 23-25) is prose. There is no `check:` for an HTTP status. The
"not a 500" obligation is graded **only** through `check: error_code` — a 500 would carry
`INTERNAL_ERROR`, not `MEDIA_BUY_NOT_FOUND`.

**What the current footer wrongly points at:**

```
# @source repo=adcp ref=v3.1-04f59d2d5 commit=04f59d2d5 path=static/compliance/source/protocols/media-buy/scenarios/invalid_transitions.yaml
```

`04f59d2d5` is an ancestor of `beta.3`, i.e. older than our own 3.1.1 pin. The path is right; the ref
is stale. For this particular step the staleness is *benign* — I diffed
`04f59d2d5` against `v3.1.1` for this file and the `unknown_media_buy` phase is **unchanged**
(the drift is confined to the `setup` phase, which gained `filters.is_fixed_price` + a
`fixed_price` `field_present` check and moved to `start_time: "asap"` / `end_time: "2099-…"`,
and to `unknown_package`, whose probe switched `paused: true` → `budget: 5001`). The footer must
still be re-pinned to `v3.1.1`: the next regeneration is not guaranteed to be benign, and a footer
that lies about which version graded it is unreviewable.

---

## 3. Schema constraints at 3.1.1

### 3a. `MEDIA_BUY_NOT_FOUND` is a real enum member, and it carries a mandated recovery

`git show v3.1.1:static/schemas/source/enums/error-code.json` — 92-member enum; `MEDIA_BUY_NOT_FOUND`
present. Its `enumMetadata` entry, verbatim:

```json
{
 "recovery": "correctable",
 "suggestion": "verify media_buy_id; for legacy correlation use get_media_buys plus context, such as context.internal_campaign_id"
}
```

`enumDescriptions`:

> "Referenced media buy does not exist or is not accessible to the requesting agent. Recovery:
> correctable (verify media_buy_id; when recovering across legacy sellers or missing echoed IDs,
> reconcile via get_media_buys and the opaque request/response context correlation handle, such as
> context.internal_campaign_id, rather than deprecated top-level buyer_ref)."

So `recovery: correctable` is **schema-mandated**, and the buyer-facing `suggestion` is not optional
decoration — the enum ships a canonical one.

### 3b. `context` is an opaque, byte-preserved echo

`git show v3.1.1:static/schemas/source/core/context.json` — the whole file:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "/schemas/core/context.json",
  "title": "Context Object",
  "description": "Opaque correlation data that is echoed unchanged in responses. Used for internal tracking, UI session IDs, trace IDs, and other caller-specific identifiers that don't affect protocol behavior. Context data is never parsed by AdCP agents - it's simply preserved and returned.",
  "type": "object",
  "additionalProperties": true
}
```

`correlation_id` is not a declared property — it rides on `additionalProperties: true`. That makes
the *echo* the entire contract: there is nothing to validate structurally, only preservation.

### 3c. The envelope requires `status` — including on errors

`git show v3.1.1:static/schemas/source/core/protocol-envelope.json`:

```json
  "required": [
    "status"
  ],
```

> "The `status` field is REQUIRED on every task response envelope … Agents shipping responses without
> a top-level `status` are non-conformant regardless of whether the task body schema would otherwise
> validate."

and on `context`:

> "Per-request opaque caller-supplied correlation object echoed unchanged in the response … that the
> agent MUST preserve byte-for-byte without parsing. … The envelope declaration is **authoritative**
> for the schema definition; per-task body declarations are mirrors."

Our error envelope carries no `status`. That is the known repo-wide gap — cited in §7, not re-filed.

### 3d. `account` and `idempotency_key` are REQUIRED on the request

`git show v3.1.1:static/schemas/source/media-buy/update-media-buy-request.json`:

```json
"required": ["idempotency_key", "account", "media_buy_id"]
```

`context` on the request is `{"$ref": "/schemas/core/context.json"}`; `paused` is
`{"type": "boolean", "description": "Pause/resume the entire media buy (true = paused, false = active)"}`.

Our `UpdateMediaBuyRequest` makes both `account` and `idempotency_key` **optional** (verified by
introspection). The storyboard's `sample_request` sends both. §7.

---

## 4. Conflicts

**Schema overrode storyboard — once, and in our favour.** `recovery: correctable` is storyboard
**prose only** (`expected:`, ungraded). Under a storyboard-only reading, asserting recovery would be
unjustified. The 3.1.1 `error-code.json` `enumMetadata` mandates it outright, so the assertion
stays — sourced to the schema, not to the storyboard. I've said so in the scenario comment so the
next reader doesn't "clean up" an assertion they can't find a `check:` for.

**No schema-vs-storyboard contradiction otherwise.** Both agree on code, on context echo, and on
correlation_id preservation.

### What the current scenario gets wrong

1. **Stale `@source` ref** — `v3.1-04f59d2d5` is older than our 3.1.1 pin (§2).
2. **It is DORMANT, and silently so.** All three parametrizations currently report
   `XFAIL … "UC-003 harness not yet wired for non-extension scenarios (full graduation pending,
   PR #1567 follow-up)"` — the blanket `else:` at `tests/bdd/conftest.py:3357-3360`. The scenario has
   graded nothing since the day it was written. Worse: **four of its six steps have no definition at
   all** — `the buyer fabricates a media_buy_id that does not exist in the seller catalog`,
   `the Buyer Agent sends update_media_buy with the unknown media_buy_id and paused true`,
   `the error recovery hint should indicate correctable`, and
   `the response should echo the context.correlation_id unchanged` match nothing in
   `tests/bdd/steps/`. Even if the conftest gate were lifted, the auto-xfail-on-missing-step path
   (`tests/bdd/conftest.py:85-104`) would keep it green-by-absence.
3. **`And the response should NOT be a 500 or non-AdCP error shape` is a negative-truthiness Then.**
   It compares no value and would be rejected by `test_architecture_bdd_no_trivial_assertions.py` the
   moment anyone implemented it. It is also redundant: `assert_wire_error("MEDIA_BUY_NOT_FOUND")`
   checks **both** envelope layers agree on the code, which is exactly and precisely "structured AdCP
   error, not a 500" — a 500 yields `INTERNAL_ERROR`. Deleted, folded into the code assertion.
4. **`the error recovery hint should indicate correctable` is vague prose.** "Indicate" is not an
   assertion. Replaced with an exact `recovery` comparison on the wire envelope.
5. **`the response should echo the context.correlation_id unchanged` cannot pass as written** — the
   scenario never *sends* a correlation_id. There is no Given that puts one on the request, and the
   table-driven request builder (`tests/bdd/steps/domain/uc003_update_media_buy.py:248-257`) hard-rejects
   any field outside its `_supported_fields` set, which has no `context`. The graded check is
   `field_value context.correlation_id == "invalid_transitions--update_unknown_media_buy"` — you
   cannot grade an echo without an input.
6. **It is a flat `Scenario`, not a `Scenario Outline`.** The brief asks for parametrized rows; the
   storyboard hands us one concrete id/correlation_id pair, and a second "buyer typo" row costs
   nothing and proves the behaviour is not id-specific.
7. **The `@source` footer sits below a duplicated one-line summary** (`# invalid_transitions: unknown
   media_buy_id surfaces as structured MEDIA_BUY_NOT_FOUND` repeats the three lines above it).
   Trimmed.

### What it misses

8. **No `suggestion` assertion.** 3.1.1 `enumMetadata` ships a canonical suggestion for this code and
   production emits one (`"Verify the media_buy_id is correct and belongs to your account."`). The
   sibling `@T-UC-003-ext-b` already grades it; the storyboard twin should not be weaker than the
   extension scenario it duplicates.
9. **No wire-envelope discipline.** Per `tests/CLAUDE.md` § Error Verification Policy and
   `test_architecture_bdd_wire_discipline.py` (whose `_RECONSTRUCTED_ASSERTION_ALLOWLIST` is
   **empty** — zero tolerance), error assertions must read `result.wire_error_envelope`, not the
   reconstructed `ctx["error"]`. This matters concretely here: I measured it, and the reconstructed
   exception object on a2a/mcp/rest has **`error.context is None`** while the wire envelope carries
   `context.correlation_id` correctly. A reconstructed-object assertion would have declared a
   production gap that does not exist.

---

## 5. Proposed Gherkin — GREEN ONLY

Replaces `tests/bdd/features/BR-UC-003-update-media-buy.feature:2047-2060` in full.

```gherkin
  @T-UC-003-storyboard-media-buy-not-found @storyboard-v3.1 @v3-1 @structured-errors @media-buy-not-found
  Scenario Outline: update_media_buy against an unknown media_buy_id returns the structured <code> envelope with the buyer's context echoed
    Given a valid update_media_buy request with:
    | field        | value          |
    | media_buy_id | <media_buy_id> |
    | paused       | true           |
    And no media buy exists with media_buy_id "<media_buy_id>"
    And the request carries context.correlation_id "<correlation_id>"
    When the Buyer Agent sends the update_media_buy request
    Then the operation should fail
    And the wire error envelope should carry code "<code>" with recovery "<recovery>"
    And the error should include a "suggestion" field
    And the response should echo context.correlation_id "<correlation_id>"

    Examples: storyboard probe, plus a buyer-typo id to prove the behaviour is not id-specific
      | media_buy_id                          | correlation_id                                | code                | recovery    |
      | does-not-exist-invalid-transitions-v1 | invalid_transitions--update_unknown_media_buy | MEDIA_BUY_NOT_FOUND | correctable |
      | mb_typo_9f2c                          | uc003--unknown-media-buy-typo                 | MEDIA_BUY_NOT_FOUND | correctable |
    # invalid_transitions phase unknown_media_buy, step update_unknown_media_buy: the buyer
    # references a fabricated media_buy_id. Three graded checks: error_code MEDIA_BUY_NOT_FOUND,
    # field_present context, field_value context.correlation_id echoed unchanged. Row 1 replays
    # the storyboard's own sample_request ids verbatim.
    #
    # recovery=correctable is NOT storyboard-graded (it appears only under `expected:` prose).
    # It is asserted here on 3.1.1 SCHEMA authority: enums/error-code.json enumMetadata pins
    # MEDIA_BUY_NOT_FOUND to recovery "correctable" and ships a canonical suggestion. Schema
    # outranks storyboard.
    #
    # "not a 500" needs no separate Then: assert_wire_error checks BOTH envelope layers
    # (adcp_error.code and errors[0].code) agree on MEDIA_BUY_NOT_FOUND. A 500 emits
    # INTERNAL_ERROR and fails the same assertion.
    # @source repo=adcp ref=v3.1.1 path=static/compliance/source/protocols/media-buy/scenarios/invalid_transitions.yaml phase=unknown_media_buy step=update_unknown_media_buy
```

### Required companion change (test infra, not production)

The scenario is currently swallowed by the UC-003 blanket dormancy gate. It must be routed into the
already-wired `MediaBuyDualEnv` branch — the same branch `T-UC-003-ext-*` uses, which seeds a tenant,
principal, product and an existing media buy and dispatches `UpdateMediaBuyRequest` through the real
update wrappers. In `tests/bdd/conftest.py`, alongside `_UC003_MANUAL_APPROVAL` (line 3297):

```python
        # Storyboard-graded scenarios wired onto the ext branch's MediaBuyDualEnv:
        # media_buy_seller/invalid_transitions phase unknown_media_buy (AdCP 3.1.1).
        _UC003_STORYBOARD_WIRED = {
            "T-UC-003-storyboard-media-buy-not-found",
        }
```

and extend the ext-branch condition at line 3302:

```python
        if (
            any(t.startswith("T-UC-003-ext-") for t in marker_names)
            or (marker_names & _UC003_TARGETING_OVERLAY)
            or (marker_names & _UC003_STORYBOARD_WIRED)
        ):
```

No other conftest change is needed. This narrows the blanket dormancy gate by exactly one tag —
it does not remove it.

---

## 6. Step inventory

### Existing — reused unchanged (3 of 6)

| Step | Owner |
|---|---|
| `Given a valid update_media_buy request with:` (datatable) | `tests/bdd/steps/domain/uc003_update_media_buy.py:242` |
| `Given no media buy exists with media_buy_id "{media_buy_id}"` | `tests/bdd/steps/domain/uc003_ext_error_scenarios.py:115` |
| `When the Buyer Agent sends the update_media_buy request` | `tests/bdd/steps/domain/uc003_update_media_buy.py:788` |
| `Then the operation should fail` | `tests/bdd/steps/generic/then_error.py:181` |
| `Then the error should include a "suggestion" field` | `tests/bdd/steps/generic/then_error.py:427` (wire-first) |

`<param>` substitution inside datatables is already load-bearing in this very feature file
(e.g. `| budget | <amount> |` at line 1027, in a scenario that passes today), so the outline form is
not novel plumbing.

### New — 3 step definitions

Belong in `tests/bdd/steps/domain/uc003_update_media_buy.py` (Given/Then 3, request-shaped) and
`tests/bdd/steps/generic/then_error.py` (Then 2, generic and reusable by the sibling
`PACKAGE_NOT_FOUND` / `NOT_CANCELLABLE` storyboard scenarios, which grade the identical context-echo
check).

```python
# → tests/bdd/steps/domain/uc003_update_media_buy.py
@given(parsers.parse('the request carries context.correlation_id "{correlation_id}"'))
def given_request_context_correlation_id(ctx: dict, correlation_id: str) -> None:
    """Attach the AdCP opaque context echo (core/context.json) to the pending request.

    context.json is additionalProperties:true, so correlation_id rides as a free-form key;
    the seller MUST preserve it byte-for-byte (protocol-envelope.json, AdCP 3.1.1).
    """
    kwargs = _ensure_update_defaults(ctx)
    kwargs["context"] = {"correlation_id": correlation_id}


# → tests/bdd/steps/generic/then_error.py
@then(parsers.parse('the wire error envelope should carry code "{code}" with recovery "{recovery}"'))
def then_wire_envelope_code_recovery(ctx: dict, code: str, recovery: str) -> None:
    """Assert code + recovery + a non-empty suggestion on the real two-layer wire envelope.

    Delegates to TransportResult.assert_wire_error, which checks BOTH layers
    (adcp_error.code and errors[0].code) agree — the "structured AdCP error, not a 500"
    obligation from invalid_transitions/unknown_media_buy.
    """
    result = ctx.get("result")
    assert result is not None, "No transport result captured to assert the wire envelope on"
    result.assert_wire_error(code, recovery=recovery, require_suggestion=True)


@then(parsers.parse('the response should echo context.correlation_id "{correlation_id}"'))
def then_wire_context_correlation_id(ctx: dict, correlation_id: str) -> None:
    """Assert the caller's opaque context survived the error path unchanged.

    Wire-only by design: the reconstructed ctx['error'] carries context=None on every wire
    transport, so a reconstructed-object read would report a phantom production gap.
    """
    result = ctx.get("result")
    assert result is not None, "No transport result captured"
    envelope = result.wire_error_envelope
    assert envelope is not None, "No wire error envelope captured — cannot verify the context echo"
    echoed = envelope.get("context", {}).get("correlation_id")
    assert echoed == correlation_id, (
        f"Expected context.correlation_id {correlation_id!r} echoed unchanged, got {echoed!r}"
    )
```

Both new Then steps read `wire_error_envelope` / `assert_wire_error`, so they satisfy Check B of
`test_architecture_bdd_wire_discipline.py` (empty allowlist) without needing an entry. Neither
constructs an error test-side, so Check A is clean too. Every Then compares concrete values —
no truthiness, no bare existence — so `test_architecture_bdd_no_trivial_assertions.py` and
`..._no_pass_steps.py` are satisfied.

### Deleted step phrasings (never had definitions)

- `the buyer fabricates a media_buy_id that does not exist in the seller catalog`
- `the Buyer Agent sends update_media_buy with the unknown media_buy_id and paused true`
- `the error recovery hint should indicate correctable`
- `the response should echo the context.correlation_id unchanged`
- `the response should NOT be a 500 or non-AdCP error shape`

---

## 7. TICKET MATERIAL

Follow-ups that cannot land green in a baseline PR. Each is filed against 3.1.1 authority.

- **`update_media_buy` accepts requests missing `account` and `idempotency_key`, both REQUIRED at 3.1.1.**
  `git show v3.1.1:static/schemas/source/media-buy/update-media-buy-request.json` declares
  `"required": ["idempotency_key", "account", "media_buy_id"]`, and the graded storyboard step
  `update_unknown_media_buy` (`dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml:69-78`)
  sends both. Our `src/core/schemas/_base.py` `UpdateMediaBuyRequest` marks both optional —
  `UpdateMediaBuyRequest(media_buy_id="x", paused=True)` constructs cleanly (verified by
  introspection). `account` optionality is a deliberate, tracked interim (account management is in
  flight); **`idempotency_key` optionality is not covered by that** and is a separate conformance
  break — every 3.1.1 `update_media_buy` request must carry one. Tightening either would turn most
  of BR-UC-003 red today, so it is out of scope for a baseline PR.

- **No top-level `status` on the error envelope.** `core/protocol-envelope.json` at 3.1.1 declares
  `"required": ["status"]` and states agents shipping responses without a top-level `status` are
  "non-conformant regardless of whether the task body schema would otherwise validate."
  `build_two_layer_error_envelope` (`src/core/exceptions.py:1019-1026`) emits only
  `{adcp_error, errors, context}`. Measured on all three wire transports for this scenario. This is
  the known repo-wide envelope gap — cited here for traceability, **not re-filed**.

- **The UC-003 blanket dormancy gate hides an entire graded storyboard family.**
  `tests/bdd/conftest.py:3357-3360` xfails every non-`ext-`/non-targeting/non-manual-approval UC-003
  scenario. Three storyboard-graded scenarios sit behind it —
  `@T-UC-003-storyboard-media-buy-not-found`, `@T-UC-003-storyboard-package-not-found`,
  `@T-UC-003-storyboard-not-cancellable-on-recancel` — grading nothing. This proposal narrows the
  gate by one tag; the sibling two need the same treatment (and `NOT_CANCELLABLE` additionally needs
  a production check for re-cancel of a terminal buy, which I did not verify). Track the full
  graduation as the PR #1567 follow-up it already claims to be.

- **`@T-UC-003-storyboard-not-cancellable-on-recancel` cites the wrong storyboard file.**
  Its footer (`tests/bdd/features/BR-UC-003-update-media-buy.feature:2088`) says
  `path=…/scenarios/creative_fate_after_cancellation.yaml`, but its own prose two lines above says
  *"invalid_transitions Phase 4 (double_cancel)"* — and the graded `check: error_code
  NOT_CANCELLABLE` lives at
  `dist/compliance/3.1.1/protocols/media-buy/scenarios/invalid_transitions.yaml:279-289`, phase
  `double_cancel`, step `second_cancel`. Classic off-by-one. Out of my scope; flagging so it is not
  lost.

- **A stale xfail asserts a gap that no longer exists.**
  `tests/bdd/steps/domain/uc011_accounts.py:2194-2201` xfails with *"context not echoed on the wire
  error envelope — AdCPError carries no context field on a2a/mcp/rest"*. That is wrong as a general
  claim: `build_two_layer_error_envelope` echoes `exc.context`, `normalize_to_adcp_error` passes a
  typed `AdCPError` through unchanged, and I measured `context.correlation_id` present on the a2a,
  mcp and rest error envelopes for this scenario. The real limitation is narrower — the
  *reconstructed* `ctx["error"]` object carries `context=None`, and that step reads the object, not
  the envelope. It should be re-pointed at `result.wire_error_envelope` and the xfail retired if
  `sync_accounts` threads `req.context` into its raises. Worth checking before someone cites that
  comment as evidence of a gap (I nearly did).

---

## 8. Verification performed

Not argued from reading — executed, against `agent-pg-salesagent-sbsweep` (real Postgres).

1. **Direct harness probe**, `UpdateMediaBuyRequest(media_buy_id="does-not-exist-invalid-transitions-v1",
   paused=True, context={"correlation_id": "invalid_transitions--update_unknown_media_buy"})` through
   `env.call_via` on **impl, a2a, mcp, rest** — 4/4. Observed wire envelope, identical on all three
   wire transports:

   ```json
   {"adcp_error": {"code": "MEDIA_BUY_NOT_FOUND",
                   "message": "Media buy 'does-not-exist-invalid-transitions-v1' not found",
                   "recovery": "correctable",
                   "suggestion": "Verify the media_buy_id is correct and belongs to your account."},
    "errors": [{ …identical… }],
    "context": {"correlation_id": "invalid_transitions--update_unknown_media_buy"}}
   ```

   REST returned **HTTP 404**, not 500. On `impl` there is no wire envelope, but the exception itself
   carries `context=ContextObject(correlation_id='invalid_transitions--update_unknown_media_buy')`.

2. **The proposed Gherkin, run verbatim** as a temporary feature + step module routed onto the ext
   branch: **6 passed** (2 example rows × a2a/mcp/rest). The UC-003 BDD module parametrizes wire
   transports only — no `impl` — so `wire_error_envelope` is always populated and the wire-first
   steps need no fallback.

3. **Mutation check** — I perturbed the Given to send `correlation_id + "-MUTATED"`; all 6 failed
   with `Expected context.correlation_id 'invalid_transitions--update_unknown_media_buy', got
   '…-MUTATED'`. The echo assertion genuinely reads production output; it is not green-by-vacuity.

All probe files were deleted afterwards. **No file under `/Users/konst/projects/salesagent-sbsweep`
was modified** — `git status --porcelain` shows only two untracked files belonging to a sibling agent.

---

## 9. Risks

- **The conftest change is load-bearing and I could not run it in place.** I proved the scenario green
  by routing an identical copy through the ext branch under a `T-UC-003-ext-…` tag. The proposed
  `_UC003_STORYBOARD_WIRED` set reaches the *same* branch with the *same* fixture setup, so the
  behaviour should be identical — but the exact conftest edit above was never executed, because the
  brief forbids editing the repo. Whoever lands this must run
  `tests/bdd/test_uc003_update_media_buy.py -k unknown_media_buy_id` and confirm 3 passed, 0 xfailed.
- **`docs/test-obligations/bdd-traceability.yaml:2494` references this `adcp_scenario_id`.** I kept the
  opaque `@T-UC-003-storyboard-media-buy-not-found` tag byte-identical, so the mapping holds — but the
  scenario *name* changes (flat `Scenario` → `Scenario Outline`, new title), which changes the
  generated pytest node id. If anything keys off node ids rather than the tag, it will need updating.
  I did not audit for that.
- **Second Examples row is my invention.** `mb_typo_9f2c` / `uc003--unknown-media-buy-typo` are not in
  the storyboard. It passed, and it defends against an id-specific implementation, but a reviewer who
  wants the scenario to mirror the storyboard exactly should drop it — the first row alone is the
  graded one.
- **`suggestion` text is asserted as non-empty, not as the enum's canonical string.** 3.1.1
  `enumMetadata` ships `"verify media_buy_id; for legacy correlation use get_media_buys plus context,
  such as context.internal_campaign_id"`; production emits `"Verify the media_buy_id is correct and
  belongs to your account."` These differ. Nothing in the storyboard grades suggestion *text*, and
  pinning it would go red, so I left it at presence. Whether we should adopt the enum's canonical
  suggestions repo-wide is a real question I am deliberately not answering here.
- **`get_by_id_or_raise` was verified through the update path only.** I did not check that every
  other caller threads `context=` — if some do not, their error envelopes will silently drop the echo.
  Unverified.
- **Drift beyond our pin not investigated.** 3.1.8/HEAD may have changed this storyboard; per the
  brief I treated 3.1.1 as authority and did not look.

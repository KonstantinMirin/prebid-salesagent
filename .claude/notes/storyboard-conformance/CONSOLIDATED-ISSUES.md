# Consolidated issue slate — `@storyboard-v3.1` re-grounding sweep vs AdCP 3.1.1

Source: 40 per-scenario re-grounding proposals in this scratchpad (`sb-*.md`, `repin-*.md`), plus
`docs/test-obligations/storyboard-binding-baseline.md`, `…/storyboard-coverage-map.md`,
`…/storyboard-reconciliation.md` in `/Users/konst/projects/salesagent-sbsweep`
(branch `test/storyboard-binding-baseline`).

**Slate completeness.** The brief listed four proposals as outstanding
(`uc002-measurement`, `uc003-mbnotfound`, `uc004-vendormetric`, `uc006-prov-contradicted`).
All four landed before extraction. `storyboard-reconciliation.md` reports **40 of 40 assessed**
and I read all 40. The slate below is complete for this sweep — no extension pending.

Reconciliation aggregate: GRADED 19 · NOT GRADED 21 · RETAG 19 · REPIN 10 · FIX-ASSERT 4 ·
PARTIAL 5 · TICKET 2.

---

## 1. Slate summary

Ranked by severity: conformance-breaking on our declared path first, cosmetic last.
"Raised by" counts distinct proposals. "Blocks" counts BDD scenarios named as blocked.

| # | Issue | Class | Severity | Raised by | Blocks |
|---|---|---|---|---|---|
| P-01 | Response envelopes carry no top-level `status` (error envelope always; 6 response models) | PRODUCTION | S1 critical | 14 | 12 |
| P-02 | `create_media_buy` / `update_media_buy` success envelope carries `errors`, which 3.1.1 forbids | PRODUCTION | S1 critical | 2 | 2 |
| P-03 | `Provenance` / `DigitalSourceType` are hand-rolled and reject spec-legal 3.1.1 submissions | PRODUCTION | S1 critical | 4 | 6 |
| P-04 | `provenance_requirements` / `accepted_verifiers` never read — 4 graded `PROVENANCE_*` codes unreachable | PRODUCTION | S1 critical | 5 | 5 |
| P-05 | `sync_governance` unimplemented — a `required_tools` entry of the specialism we **declare** | PRODUCTION | S1 critical | 3 | 6 |
| P-06 | Delivery models don't extend the library type; `by_package[]` omits 3 required fields | PRODUCTION | S1 critical | 3 | 4 |
| P-07 | `update_media_buy` implements no cancellation — `canceled` unreachable on every transport | PRODUCTION | S1 critical | 2 | 3 |
| P-08 | Request filters accepted and silently ignored (`format_ids`, `required_metrics`, `required_vendor_metrics`, `creative_ids`, …) | PRODUCTION | S1 critical | 5 | 6 |
| P-09 | `context` echo missing on some error envelopes — raise-site-dependent | PRODUCTION | S2 high | 6 | 8 |
| P-10 | `get_media_buys` items omit `confirmed_at` and `revision`, both REQUIRED at 3.1.1 | PRODUCTION | S2 high | 1 | 1 |
| P-11 | `pagination.cursor` never emitted while `has_more` can be true; REST emits `cursor: null` | PRODUCTION | S2 high | 4 | 3 |
| P-12 | Format identity compared on `id` alone — `agent_url` never canonicalized or compared | PRODUCTION | S2 high | 3 | 4 |
| P-13 | `get_adcp_capabilities` under-declares five 3.1.1 capability flags; comment claims a scenario is active that is not | PRODUCTION | S2 high | 9 | 11 |
| P-14 | Per-creative validation failures emitted as transient `SERVICE_UNAVAILABLE`; `error.field` unset | PRODUCTION | S2 high | 3 | 4 |
| P-15 | REST body models drop spec-required fields — transport-divergent (Pattern #5) | PRODUCTION | S2 high | 5 | 6 |
| P-16 | `plan_id` and `governance_context` dropped at every transport boundary | PRODUCTION | S2 high | 4 | 6 |
| P-17 | Delivery emits affirmatively wrong numbers: `clicks=0`, `ctr=0.0`, `currency="USD"` | PRODUCTION | S2 high | 2 | 2 |
| P-18 | `measurement_terms` accepted and silently dropped; `TERMS_REJECTED` never emitted | PRODUCTION | S2 high | 1 | 1 |
| P-19 | `SyncCreativeResult.status` never populated; MCP serializes it as `null` (schema-invalid) | PRODUCTION | S2 high | 5 | 4 |
| P-20 | Signals surface is structurally non-conformant and registered on no transport | PRODUCTION | S3 medium | 3 | 3 |
| P-21 | Provenance policy resolved tenant-wide from `provenance_policies[0]`, not per-product | PRODUCTION | S3 medium | 4 | 4 |
| P-22 | Proposal/refine lifecycle absent; `refine` silently discarded; `brief` accepted with `buying_mode: refine` | PRODUCTION | S3 medium | 2 | 5 |
| P-23 | `collection_list` accepted with zero validation, zero capability declaration, zero wire signal | PRODUCTION | S3 medium | 2 | 2 |
| P-24 | `error.field` is index-less and transport-dependent | PRODUCTION | S3 medium | 2 | 2 |
| P-25 | `include_package_daily_breakdown` accepted and ignored; `viewability` is a scalar where 3.1.1 requires an object | PRODUCTION | S3 medium | 1 | 2 |
| P-26 | `update_media_buy` does not enforce `idempotency_key` (REQUIRED at 3.1.1) | PRODUCTION | S3 medium | 2 | 2 |
| P-27 | No inbound `preview_creative` or `build_creative` tool; two stale comments claim they aren't in the spec | PRODUCTION | S3 medium | 2 | 2 |
| P-28 | `pending_creatives → pending_start` transition does not exist; three duplicated transition blocks | PRODUCTION | S3 medium | 1 | 1 |
| P-29 | `GovernanceAgent` rejects the required `authentication` block and accepts plaintext `http://` URLs | PRODUCTION | S3 medium | 1 | 2 |
| T-01 | `then_response_schema_valid` runs no validator — and exists twice with divergent strength | TEST-INFRA | S1 critical | 22 | ~30 |
| T-02 | Pinned schema fixtures vendored at `04f59d2d5`, behind our own 3.1.1 pin | TEST-INFRA | S1 critical | 20 | ~30 |
| T-03 | 21 BDD feature files have no `scenarios()` binding — never collected | TEST-INFRA | S1 critical | 8 | ~600 |
| T-04 | Blanket harness `pytest.xfail` gates make every storyboard scenario dormant and hide missing steps | TEST-INFRA | S1 critical | 13 | ~25 |
| T-05 | `@source` footers: 16 off-by-one, 40 stale refs, 10 absent, no `phase=`/`step=` grammar | TEST-INFRA | S2 high | 12 | 40 |
| T-06 | No BDD step asserts `context` / `context.correlation_id` echo anywhere | TEST-INFRA | S2 high | 14 | ~20 |
| T-07 | `storyboard_binding_sweep.py` has two false-negative classes and mis-triaged UC-008 | TEST-INFRA | S2 high | 3 | 3 |
| T-08 | Test harness silently drops spec-required fields, masking transport divergence | TEST-INFRA | S2 high | 4 | 5 |
| T-09 | UC-006 per-creative error codes inferred from message substrings, not read off the wire | TEST-INFRA | S2 high | 1 | ~10 |
| T-10 | No harness env can drive two tools in one scenario — every create→read chain ungraded | TEST-INFRA | S3 medium | 6 | 6 |
| T-11 | Step-definition defects: duplication, over-broad parsers, mis-attributed assertions, dead code | TEST-INFRA | S3 medium | 9 | 8 |
| T-12 | UC-019 harness: deprecated MCP wrapper, `REST_ENDPOINT` points at a nonexistent route | TEST-INFRA | S3 medium | 1 | ~80 |
| S-01 | 19 scenarios claim `@storyboard-v3.1` grading that does not apply — retag `@schema-v3.1` | SCENARIO | S2 high | 19 | 19 |
| S-02 | Scenarios asserting values production never emits or the spec never defined | SCENARIO | S3 medium | 7 | 10 |
| S-03 | `provenance_enforcement` phase 4 (`PROVENANCE_VERIFIER_NOT_ACCEPTED`) has no scenario at all | SCENARIO | S3 medium | 2 | 0 |
| U-01 | Storyboards name error codes that do not exist in `error-code.json` | UPSTREAM | S3 medium | 1 | 1 |
| U-02 | Storyboard prose names fields and enum members no 3.1.1 schema defines | UPSTREAM | S3 medium | 4 | 4 |
| U-03 | `NOT_CANCELLABLE` hard-graded by storyboard, `MAY` in the schema — genuine conflict | UPSTREAM | S3 medium | 2 | 2 |
| U-04 | Storyboards grade less than their own schemas require (session_id, forecast, `field`/`recovery`) | UPSTREAM | S4 low | 4 | 0 |
| U-05 | `ask` semantics under `action: finalize` undefined at 3.1.1 | UPSTREAM | S4 low | 2 | 0 |
| M-01 | The sweep brief's "known production gaps" list is wrong per-tool | META | S2 high | 4 | ~6 |

Totals: **29 PRODUCTION · 12 TEST-INFRA · 3 SCENARIO · 5 UPSTREAM · 1 META = 50 issues.**

---

## 2. Full issue bodies

Each block below is file-ready. Bodies are written for `gh issue create --title … --body-file …`.

---

### P-01 — Response envelopes carry no top-level `status`; the error envelope never can

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc002-gov-conditions, uc003-mbnotfound,
uc003-pkgnotfound, uc004-delivery, uc004-reqmetrics, uc005-roundtrip, uc006-multiformat,
uc006-prov-corrected, uc006-reception, uc008-baseline, uc008-agentdest, uc014-session,
uc019-statuspoll, uc020-vast, uc021-preview

**What is broken.** `build_two_layer_error_envelope` emits exactly `{adcp_error, errors, context}` —
there is no `status` key on any error response, on any transport.

```
src/core/exceptions.py:1019-1026
    envelope: dict[str, Any] = {
        "adcp_error": dict(payload["errors"][0]),
        "errors": payload["errors"],
    }
    serialized_context = _serialize_context(exc.context)
    if serialized_context is not None:
        envelope["context"] = serialized_context
    return envelope
```

On the success side the gap is **per response model, not universal** — this is the correction that
matters for scoping. Measured:

| Tool | top-level `status` on success | evidence |
|---|---|---|
| `create_media_buy` | present (`completed`) | uc002-measurement, real REST wire body |
| `list_creatives` | present (`completed`) | uc018-listall, uc018-fmtfilter, a2a+mcp+rest |
| `sync_creatives` | **absent** — dumped keys `['creatives','dry_run']` | uc006-multiformat, executed probe |
| `get_media_buys` | **absent** — `GetMediaBuysResponse` declares `media_buys, errors, context` only | uc019-statuspoll |
| `get_media_buy_delivery` | **absent** — `Draft7Validator` error `[] -> 'status' is a required property` | uc004-delivery |
| `list_creative_formats` | **absent** — `src/core/schemas/creative.py:547-549` states protocol fields are "added by the protocol layer" | uc005-roundtrip |
| `get_signals` / `activate_signal` | **absent** | uc008-baseline |

**Mandate.** `git show v3.1.1:static/schemas/source/core/protocol-envelope.json`:

> `"required": ["status"]` … "The `status` field is REQUIRED on every task response envelope …
> Agents shipping responses without a top-level `status` are non-conformant regardless of whether
> the task body schema would otherwise validate."

Composed via `allOf` into `create-media-buy-response.json`, `update-media-buy-response.json`,
`get-media-buys-response.json`, `get-media-buy-delivery-response.json`,
`sync-creatives-response.json`, `list-creatives-response.json`,
`list-creative-formats-response.json`, `activate-signal-response.json`,
`preview-creative-response.json`, `build-creative-response.json`, `sync-governance-response.json`.

**Blocked scenarios.** Every `- check: response_schema` on every graded step — the single
most-graded check in the 3.1.1 tree. Named explicitly:
`T-UC-003-storyboard-media-buy-not-found`, `T-UC-003-storyboard-package-not-found`,
`T-UC-004-storyboard-controller-driven-delivery-schema-compliance`,
`T-UC-004-storyboard-required-metrics-end-to-end-accountability`,
`T-UC-005-storyboard-format-id-roundtrip-from-products`,
`T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-creative-reception-stateful-render`,
`T-UC-006-storyboard-provenance-*` (4), `T-UC-019-storyboard-post-create-status-poll`.

**Done when**
- [ ] `build_two_layer_error_envelope` emits `status` (the `TaskStatus` for the failure arm) on all four transports.
- [ ] The six response models above carry a top-level `status`, or the protocol layer stamps it uniformly.
- [ ] A single BDD step asserts `status` on the wire for both success and error paths, wired into at least one scenario per tool.
- [ ] `docs/test-obligations/` records which tools were already conformant (create_media_buy, list_creatives) so nobody re-derives it.

---

### P-02 — `create_media_buy` / `update_media_buy` success envelope carries `errors`, which 3.1.1 forbids

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc002-inv-targeting (7.1), uc002-inv-nomatch

**What is broken.** Production attaches `UNSUPPORTED_FEATURE` advisories to the **success** envelope
whenever a package carries `property_list`:

```
src/core/tools/media_buy_create.py:1841   errors=property_list_unsupported_advisories(req.packages, adapter)
src/core/tools/media_buy_create.py:3561   errors=property_list_unsupported_advisories(req.packages, adapter)
src/core/tools/media_buy_create.py:4102   errors=property_list_unsupported_advisories(req.packages, adapter)
src/core/tools/media_buy_update.py:566,591,743,1398   same pattern
```

The rationale comment at `src/services/targeting_capabilities.py:174-180` cites AdCP **3.0.0**
`error-handling.mdx` ("non-fatal errors … MUST NOT populate `adcp_error`", i.e. advisories ride the
success envelope). 3.1.1 supersedes that for this response shape.

**Mandate.** `v3.1.1:static/schemas/source/media-buy/create-media-buy-response.json` →
`oneOf` → `CreateMediaBuySuccess` carries `"not": {"required": ["errors"]}`. Only the
`CreateMediaBuySubmitted` branch permits `errors` ("Optional advisory errors accompanying the
submitted envelope"). A response with `media_buy_id` + `packages` + `errors` matches **zero**
branches. Same defect on `update-media-buy-response.json`.

Graded at `dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_targeting.yaml`,
step `create_buy_with_lists`, `- check: response_schema`.

**Note the coupling.** The advisory fires on exactly the request the `inventory_list_targeting`
storyboard sends, and `supports_property_list_filtering()` is universally `False` today
(no adapter sets the ClassVar), so it fires on *every* `property_list` request.

**Blocked scenarios.** `T-UC-002-storyboard-inventory-list-targeting-parity`,
`T-UC-002-storyboard-inventory-list-no-match`.

**Done when**
- [ ] The advisory rides somewhere the success branch permits, or is dropped for the success arm.
- [ ] The 3.0.0 citation at `targeting_capabilities.py:174-180` is replaced with the 3.1.1 decision.
- [ ] Fixed on `update_media_buy` in the same change (four call sites).
- [ ] A scenario grades that a success response validates against exactly one `oneOf` branch.

---

### P-03 — `Provenance` and `DigitalSourceType` are hand-rolled and reject spec-legal 3.1.1 submissions

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc006-prov-corrected (1,2),
uc006-prov-dst (T2,T3), uc006-prov-contradicted (T1,T2), uc006-prov-disclosure

**What is broken.** `src/core/schemas/creative.py:82` declares
`class Provenance(SalesAgentBaseModel)` — not an extension of the library type — under
`extra="forbid"`. Verified field-by-field against `v3.1.1:static/schemas/source/core/provenance.json`:

| field | 3.1.1 schema | ours (`creative.py:82-120`) |
|---|---|---|
| `digital_source_type` | optional (no `required` array) | **required** (`Field(...)`) |
| `disclosure` | object, `required: ["required"]` | `str \| None` |
| `declared_by` | object, `required: ["role"]` (`creator\|advertiser\|agency\|platform\|tool`) | `str \| None` |
| `human_oversight` | string enum `none\|prompt_only\|selected\|edited\|directed` | `bool \| None` |
| `c2pa` | object `{manifest_url}` | `str \| None` |
| `verification` | array | `dict \| None` |
| `embedded_provenance` | array, `minItems: 1`, items carry `method`/`standard`/`provider`/`verify_agent` | **absent** |
| `watermarks`, `declared_at`, `ext` | present | **absent** |

`DigitalSourceType` (`creative.py:64-79`) invents three members that do not exist at 3.1.1 —
`composite_with_trained_model`, `trained_algorithmic_model`, `minor_human_edits` — and is missing
three that do: `trained_algorithmic_media`, `composite_with_trained_algorithmic_media`,
`data_driven_media`.

Reproduced by execution (uc006-prov-corrected, calling the real `_validate_creative_input` with the
storyboard's own phase-6 provenance object):

```
LOCAL Creative REJECTED — errors:
   ('provenance','digital_source_type') | enum            | Input should be 'digital_capture', …
   ('provenance','declared_by')         | string_type     | Input should be a valid string
   ('provenance','disclosure')          | string_type     | Input should be a valid string
   ('provenance','embedded_provenance') | extra_forbidden | Extra inputs are not permitted
```

`src/core/tools/creatives/_sync.py`'s `except Exception` turns that into a per-creative
`action: "failed"` carrying a raw pydantic message — the exact inverse of the graded
`creatives[0].action ∈ ["created","updated"]`.

**Mandate.** `v3.1.1:static/schemas/source/core/provenance.json`,
`v3.1.1:static/schemas/source/enums/digital-source-type.json`. CLAUDE.md Pattern #1 /
`test_architecture_schema_inheritance.py`. Also the practical stake: an EU AI Act Art. 50 workflow
submitting the correct, most-used disclosure value `trained_algorithmic_media` is **rejected today**
(reproduced on mcp, a2a and rest by uc006-prov-contradicted).

**Blocked scenarios.** All four `T-UC-006-storyboard-provenance-*`, plus
`T-UC-006-storyboard-provenance-claim-contradicted`, and structurally the entire
`provenance_enforcement.yaml` storyboard (its phase 4/5/6 payloads cannot be parsed by us).

**Done when**
- [ ] `Provenance` extends the library type; the seven local redeclarations are deleted.
- [ ] `DigitalSourceType` is the SDK enum, not a local `StrEnum`.
- [ ] A `Scenario Outline` over the full 3.1.1 enum accepts every member.
- [ ] The storyboard's own phase-4/5/6 `sample_request` payloads parse.
- [ ] Blocks P-04 — land this first.

---

### P-04 — `provenance_requirements` / `accepted_verifiers` never read; four graded `PROVENANCE_*` codes unreachable

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc006-prov-required (T1,T3),
uc006-prov-disclosure (T1), uc006-prov-dst (T1), uc006-prov-corrected (3,4),
uc006-prov-contradicted (T4,T5)

**What is broken.** Verified: `grep -rn "PROVENANCE_\|accepted_verifiers" src/ --include='*.py'` →
**0 hits each.** The entire provenance surface is one advisory:

```
src/core/tools/creatives/_validation.py:144-175  check_provenance_required(...)
    → returns early with None as soon as creative.provenance is not None
    → otherwise returns a warning *string*
src/core/tools/creatives/_sync.py:180-184, 275-278, 328-330
    → appends the string to result.warnings, leaves action at created/updated
src/core/database/repositories/creative.py:263-273  get_provenance_policies()
    → filters on creative_policy["provenance_required"] only; never reads provenance_requirements
```

So `require_digital_source_type`, `require_disclosure_metadata`, `require_embedded_provenance` and
`accepted_verifiers` are dead config.

**Mandate.** `v3.1.1:static/schemas/source/core/creative-policy.json`:

> "Sellers that publish a requirement here MUST enforce it on creative submission: a
> `sync_creatives` request that omits a required field is rejected with the corresponding
> `PROVENANCE_*` error code."

and, for the verifier half:

> "Sellers MUST reject `sync_creatives` submissions whose `verify_agent.agent_url` does not match
> any entry here with `PROVENANCE_VERIFIER_NOT_ACCEPTED`" … "Sellers MUST NOT call this URL until
> the canonicalized match is confirmed."

Graded at `dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml`:
`reject_no_provenance` (188-207), `reject_missing_digital_source_type` (261-275),
`reject_off_list_verifier` (277-363), `reject_missing_disclosure` (422-436).

**The emission plumbing already exists.** `_failed_sync_result(creative_id, msg, code=…, recovery=…)`
(`src/core/tools/creatives/_processing.py:34-59`) produces exactly the graded shape —
`action: "failed"`, `errors[0].code`, `recovery`, no `status`. The work is gate logic at the
`check_provenance_required` call site, plus turning a warning into a per-item failure.

Note the precise trigger for disclosure: a missing `disclosure.required` **flag**, not a missing
`disclosure` object.

**Blocked scenarios.** `T-UC-006-storyboard-provenance-required-rejection`,
`…-digital-source-type-missing`, `…-disclosure-missing`, `…-corrected-acceptance`, plus the
uncovered phase-4 scenario (see S-03).

**Done when**
- [ ] P-03 landed (spec-shaped payloads must parse before policy can run).
- [ ] All four `PROVENANCE_*` codes emitted with `error.field` pointing at the inspected path.
- [ ] `action: "failed"` items omit `status` per the schema's `if action in [failed,deleted] then not status`.
- [ ] `accepted_verifiers` canonicalized-matched **before** any outbound call.
- [ ] The four dormant scenarios wired and green.

---

### P-05 — `sync_governance` is unimplemented and it is a `required_tools` entry of the specialism we declare

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc030-govbinding (B), uc002-gov-denied,
uc002-gov-conditions

**Why this outranks the other governance items.** Every other governance gap sits behind
`governance-aware-seller`, a specialism we do not claim — those grade `not_applicable`.
**`sync_governance` does not.** `dist/compliance/3.1.1/specialisms/sales-non-guaranteed/index.yaml:9`
lists it under `required_tools` for the specialism `src/core/tools/capabilities.py:100` **does**
declare, and `:292-304` grades `accounts[0].status == "synced"` plus `response_schema` against
`account/sync-governance-response.json`. We fail that step outright.

**What is broken.** `src/core/main.py:351-352` registers `list_accounts` and `sync_accounts` only.
Verified: `grep -rn "sync_governance\|check_governance" src/ --include='*.py'` → **0 hits each**.
`governance_agents` exists purely as a persisted passthrough JSON column
(`src/core/database/models.py:827-829`) written through `sync_accounts`
(`src/core/tools/accounts.py:586,629`) and read back through `list_accounts` (`:70`).

**Mandate.** Request `v3.1.1:static/schemas/source/account/sync-governance-request.json`
(`required: [idempotency_key, accounts]`); response `…/sync-governance-response.json`
(`oneOf` success/error; success `required: [accounts]`; per-account `required: [account, status]`,
`status ∈ {synced, failed}`).

**Blocked scenarios.** The whole of `BR-UC-030-manage-governance-binding.feature` (45 scenarios,
582 lines) is authored against this tool — and is itself unbound (see T-03).

**Done when**
- [ ] `sync_governance` `_impl` + MCP/A2A/REST wrappers + harness env.
- [ ] Response echoes the persisted agent in `accounts[].governance_agents` (see P-29 / M).
- [ ] P-29 resolved so a spec-shaped registration is accepted at all.
- [ ] BR-UC-030 bound with at least the registration half green.

---

### P-06 — Delivery models don't extend the library type; `by_package[]` omits three REQUIRED fields

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc004-delivery, uc004-reqmetrics,
uc004-vendormetric (T3)

**What is broken.** `src/core/schemas/delivery.py:159` — `class PackageDelivery(SalesAgentBaseModel)`
with a closed field list; its own docstring at `:162` concedes *"Does not yet extend library
ByPackageItem."* `DeliveryTotals` has the same defect. Consequences:

1. `pricing_model`, `rate`, `currency` are declared optional (`delivery.py:173-185`) and are set from
   `MediaPackage.package_config["pricing_info"]`, left `None` when the key is absent
   (`src/core/tools/media_buy_delivery.py:487-497`). `AdCPBaseModel` drops `None`, so they vanish
   from the wire entirely.
2. `vendor_metric_values`, `missing_metrics` and `committed_metrics` cannot be represented at all.

A `Draft7Validator` run against the real 3.1.1 schema (uc004-delivery, executed) returns exactly
four errors on a faithful production response:

```
ERR []                                           -> 'status' is a required property        (P-01)
ERR ['media_buy_deliveries',0,'by_package',0]    -> 'pricing_model' is a required property
ERR ['media_buy_deliveries',0,'by_package',0]    -> 'rate' is a required property
ERR ['media_buy_deliveries',0,'by_package',0]    -> 'currency' is a required property
```

**Mandate.** `v3.1.1:static/schemas/source/media-buy/get-media-buy-delivery-response.json` →
`media_buy_deliveries.items.by_package.items.allOf[1].required =
["package_id","spend","pricing_model","rate","currency"]`, with
`allOf[0] = {$ref: core/delivery-metrics.json}` — which is where `vendor_metric_values` lives.
CLAUDE.md Pattern #1.

Graded at `delivery_reporting.yaml:228` (`response_schema`) and
`vendor_metric_accountability.yaml:279-293` (five `field_present` checks).

**Blocked scenarios.** `T-UC-004-storyboard-controller-driven-delivery-schema-compliance`,
`…-required-metrics-end-to-end-accountability`, `…-vendor-metric-end-to-end`, plus 12 other dormant
UC-004 vendor/missing-metrics scenarios that unblock in one move.

**Done when**
- [ ] `PackageDelivery` / `DeliveryTotals` extend the library `delivery-metrics` types.
- [ ] `pricing_model`/`rate`/`currency` derived from the buy's pricing option when `package_config` has no `pricing_info`, and made required.
- [ ] `vendor_metric_values` emitted, de-duplicated per `(vendor.domain, vendor.brand_id, metric_id)` per period — a schema MUST that the storyboard leaves as prose (`core/delivery-metrics.json`).
- [ ] `by_package[].missing_metrics` emitted (needs `package.committed_metrics` as the reconciliation source, or the documented fallback to `reporting_capabilities.available_metrics`).

---

### P-07 — `update_media_buy` implements no cancellation; `canceled` is unreachable on every transport

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc003-creativefate,
uc003-notcancellable (TM-2)

**What is broken.** Verified — `has_updatable_fields()` omits `canceled` and `cancellation_reason`:

```
src/core/schemas/_base.py:2089-2102
    return any(f is not None for f in (
        self.paused, self.start_time, self.end_time, self.packages, self.budget,
        self.push_notification_config, self.reporting_webhook, self.context, self.ext,
    ))
```

So `{media_buy_id, account, idempotency_key, canceled: true}` — a complete, valid 3.1.1 cancel —
trips the BR-RULE-022 empty-update gate at `src/core/tools/media_buy_update.py:1506` and returns
`INVALID_REQUEST`, **before** the terminal-state check at `:412`. Additionally:

- `_build_update_request` (`media_buy_update.py:1425-1518`) has no `canceled` parameter; the field is never read anywhere in the 1673-line module.
- `src/routes/api_v1.py:96-117` `UpdateMediaBuyBody` declares no `canceled`; `SalesAgentBaseModel` is `extra="forbid"` outside production, so **REST rejects the body with a different error than A2A/MCP** — a Pattern #5 transport divergence.
- The BDD datatable Given rejects it: `Unrecognized update field 'canceled' … Supported: ['budget','end_time','idempotency_key','invoice_recipient','media_buy_id','packages','paused','start_time']`.

**Mandate.** `v3.1.1:static/schemas/source/media-buy/update-media-buy-request.json` declares
`canceled: {type: boolean, const: true}` and `cancellation_reason: {type: string, maxLength: 500}`
("Sellers SHOULD store this and return it in subsequent get_media_buys responses"), with
`required: ["idempotency_key","account","media_buy_id"]`. `adcp==6.6.0`'s `UpdateMediaBuyRequest`
carries both. Sent on the wire at `invalid_transitions.yaml:237-247,268-278`.

**Blast radius.** No cancel flow is reachable through any AdCP transport today.
`T-UC-003-ext-v` is unrunnable for the same reason.

**Blocked scenarios.** `T-UC-003-storyboard-not-cancellable-on-recancel`,
`T-UC-003-storyboard-creative-fate-after-cancellation`, `T-UC-003-ext-v`.

**Done when**
- [ ] `canceled` + `cancellation_reason` added to `has_updatable_fields()`, `_build_update_request`, the MCP wrapper, `update_media_buy_raw`, and `UpdateMediaBuyBody`.
- [ ] Cancellation releases package-creative assignments (`CreativeAssignment`, `src/core/database/models.py:760-796`, has a plain FK with no `ondelete` and no application-level release) — mandated by `dist/docs/3.1.1/creative/creative-libraries.mdx:36` and `dist/docs/3.1.1/media-buy/media-buys/index.mdx:317`, prose-only upstream so lower priority than the wire fix.
- [ ] `tests/harness/media_buy_update.py::_WRAPPER_UNSUPPORTED_FIELDS` shrinks by two entries (see T-08).
- [ ] U-03 decided before choosing the rejection code for a re-cancel.

---

### P-08 — Request filters accepted and silently ignored

**Class:** PRODUCTION · **Severity:** S1 · **Raised by:** uc018-fmtfilter, uc003-creativefate,
uc004-reqmetrics, uc004-vendormetric (T1,T2), uc001-refine

One defect class, five instances. Every one is a "filter-not-fail" MUST that we satisfy vacuously by
never filtering.

**8a. `list_creatives` ignores `filters.format_ids`.** Verified: in
`src/core/tools/creatives/listing.py` the only occurrence of `format_ids` is the
`filters_applied` string at `:386-387`. The repository's `format=` argument is fed only by the
out-of-band flat `format` string. Measured on a2a/mcp/rest (uc018-fmtfilter, real harness dispatch,
3 seeded creatives, 1 matching): filter returned **all three**, `query_summary.total_matching: 3`.
Same defect class as the `concept_ids` drop fixed in #1493 — `format_ids` was left behind.
Mandate: `v3.1.1 core/creative-filters.json` → `format_ids`: *"Filter by structured format IDs.
Returns creatives that match any of these formats."*

**8b. `list_creatives` ignores `filters.creative_ids`** (and `format_ids`, `tags_any`, `accounts`,
`unassigned`, `assigned_to_packages`). `CreativeRepository.get_by_principal`
(`src/core/database/repositories/creative.py:99-115`) has no `creative_ids` parameter and
`_list_creatives_impl` never derives one (`listing.py:216-226`, call site `:255-269`).
Mandate: `v3.1.1 core/creative-filters.json` `creative_ids` (`minItems: 1`, `maxItems: 100`).
The `creative_fate_after_cancellation` storyboard sends exactly this filter in both
`list_creatives_before_cancel` (222-224) and `list_creatives_after_cancel` (301-303).

**8c. `get_products` ignores `filters.required_metrics`.** Verified: `grep required_metrics src/` →
0 hits. `src/core/tools/products.py:460-606` filters on `delivery_type`, `is_fixed_price`,
`format_ids`, `standard_formats_only`, `countries`, `channels`, `device_types` only.
Mandate: `v3.1.1 core/product-filters.json:474` — *"Sellers MUST silently exclude products that
cannot meet this list (filter-not-fail; do not return an error)."* The superset test must account
for `available_metrics`'s implicit `impressions`/`spend`.

**8d. `get_products` ignores `filters.required_vendor_metrics`.** Same code path, verified 0 hits.
Executed proof (uc004-vendormetric): tenant with `vm_capable` (declares
`attentionvendor.example`) + `vm_incapable` (declares none), filter
`[{"vendor":{"domain":"attentionvendor.example"}}]` → returns `['vm_capable','vm_incapable']`.
Matching rule from the same description: *"A product matches if its declared `vendor_metrics`
covers ALL listed entries (AND across entries; pins within an entry are conjunctive)."*

**8e. `query_summary.filters_applied` reports unapplied filters and leaks a Pydantic repr.**
`listing.py:386-387` — `filters_applied.append(f"format_ids={','.join(str(f) for f in …)}")`.
Measured wire value:

```
"format_ids=agent_url=AnyUrl('https://creative.adcontextprotocol.org/') id='display_300x250' width=None height=None duration_ms=None"
```

Two bugs in one line. Mandate: `v3.1.1 creative/list-creatives-response.json` defines
`query_summary.filters_applied` as *"List of filters that were applied to the query"* with
`items: {type: string}`.

**Also missing:** `get_products` never emits `filter_exclusions.excluded_by`
(`v3.1.1 media-buy/get-products-response.json:238-249`, which names `required_metrics` as an
example key), so buyers cannot distinguish a metric-driven exclusion from an empty catalogue.

**Blocked scenarios.** `T-UC-018-storyboard-filter-by-format-id-object`,
`T-UC-003-storyboard-creative-fate-after-cancellation`,
`T-UC-004-storyboard-required-metrics-end-to-end-accountability`,
`T-UC-004-storyboard-vendor-metric-end-to-end`.

**Done when**
- [ ] All five filters push into the query (8c and 8d are the *same missing filter loop* — fix in one change).
- [ ] `filters_applied` reports only filters actually applied, formatted from object fields, never `str(model)`.
- [ ] `filter_exclusions.excluded_by` emitted.
- [ ] P-12 landed for the `format_ids` comparison rule.

---

### P-09 — `context` echo missing on some error envelopes (raise-site-dependent)

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc002-inv-nomatch (1),
uc002-gov-recovery, uc003-notcancellable (TM-3), uc003-mbnotfound, uc003-pkgnotfound, uc002-async

**Proposals disagree, and both are right — record both.**

`build_two_layer_error_envelope` (`src/core/exceptions.py:1023-1025`) **does** echo `exc.context`
when it is set. So the gap is per raise-site, not class-wide:

| raise site | `context=` passed? | measured |
|---|---|---|
| `src/core/database/repositories/media_buy.py:192-209` (`AdCPPackageNotFoundError`) | yes | `context.correlation_id` present on a2a/mcp/rest (uc003-pkgnotfound, executed) |
| `get_by_id_or_raise` on the update path | yes | present on all three (uc003-mbnotfound, measured) |
| `src/core/tools/media_buy_update.py:413-420` (terminal-state) | **no** — passes `field=`/`suggestion=` but not `context=`, while `_verify_principal(…, context=req.context)` ten lines earlier at `:403` does | inconsistent within one function |
| `src/services/targeting_capabilities.py:315-330` (`raise_if_property_targeting_violations`) | **no** | wire error envelope keys were `{adcp_error, errors}` only, all three transports (uc002-inv-nomatch, executed) |

**Mandate.** `v3.1.1 core/protocol-envelope.json` → `context`: "echoed unchanged in the response …
MUST preserve byte-for-byte." `create-media-buy-response.json` `CreateMediaBuyError.context`:
*"Sellers MUST echo this object verbatim when the originating request carried context, including
synchronous success, **error**, submitted, and webhook task-status payloads."*
`universal/error-compliance.yaml` (universal tier — always applies): "Every error response must
include the caller's context object unchanged." Graded on essentially every error step:
`inventory_list_no_match.yaml:141-148`, `invalid_transitions.yaml:283-289`,
`governance_denied_recovery.yaml:231-234`, `provenance_enforcement.yaml:137-140/204-207/272-275/360-363/433-436/514-517`.

**Blocked scenarios.** `T-UC-002-storyboard-inventory-list-no-match` (this is why its rewrite had to
take the success branch), `T-UC-003-storyboard-not-cancellable-on-recancel`, and the error half of
every UC-006 provenance scenario.

**Done when**
- [ ] Every `raise AdCP*Error` in `src/core/tools/` and `src/services/` audited for a missing `context=req.context`; a guard or a shared raise helper prevents regressions.
- [ ] T-06 landed so the echo is actually graded.
- [ ] The stale xfail at `tests/bdd/steps/domain/uc011_accounts.py:2194-2201` retired — it claims *"context not echoed on the wire error envelope — AdCPError carries no context field on a2a/mcp/rest"*, which is **false as a general claim** (measured present). The real limitation is that the *reconstructed* `ctx["error"]` object carries `context=None`; the step reads the object, not the envelope. Re-point it at `result.wire_error_envelope`.

---

### P-10 — `get_media_buys` items omit `confirmed_at` and `revision`, both REQUIRED at 3.1.1

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc019-statuspoll

**What is broken.** Verified — `src/core/schemas/_base.py:2721`:

```python
class GetMediaBuysMediaBuy(SalesAgentBaseModel):
    media_buy_id: str
    buyer_campaign_ref: str | None
    status: MediaBuyStatus
    valid_actions: list[MediaBuyValidAction] | None
    currency: str
    total_budget: float
    packages: list[GetMediaBuysPackage]
    created_at: datetime | None
    updated_at: datetime | None
```

No `confirmed_at`, no `revision`, no per-buy `context`. `src/core/tools/media_buy_list.py:270-283`
never sets any of them.

**Mandate.** `git show v3.1.1:static/schemas/source/media-buy/get-media-buys-response.json` lists
`confirmed_at` (type `["string","null"]`) and `revision` (`{"type":"integer","minimum":1}`) in the
`media_buys[].required` array. The schema further couples `confirmed_at`: an item with
`confirmed_at: null` MUST NOT carry `status: "active"` (the `allOf` provisional-buy guard) — so
emitting it changes what `active` is allowed to mean. `revision` is the optimistic-concurrency token
`update_media_buy` consumes; without it a buyer cannot construct a conflict-safe update from a read.

Per-buy `context`: `get-media-buys-response.json` — *"Sellers MUST include persisted context on read
surfaces when the media buy was created through AdCP with context, so buyers can reconcile
seller-assigned media_buy_id values with their own tracking state."* Graded at
`protocols/media-buy/index.yaml:583-585`
(`field_value media_buys[0].context.correlation_id`). Needs a create-side persist as well as a
read-side emit; the create-side half also blocks the `package.context` sibling clause (P-28).

Note: `media_buy_status` does **not** exist on `get-media-buys-response.json` at 3.1.1 — the
schema's own `$comment` says *"When get_media_buys gains canonical media_buy_status during the
3.1 → 3.2 status migration…"*. Do not add it here.

**Blocked scenarios.** `T-UC-019-storyboard-post-create-status-poll` (`response_schema` +
`media_buys[0].context.correlation_id`).

**Done when**
- [ ] `confirmed_at`, `revision`, per-buy `context` emitted; `GetMediaBuysRequest`/`Response` extend the library types (their docstrings currently cite *"the adcp 3.6.0 spec"*, a version matching neither the SDK pin nor the spec pin).
- [ ] The provisional-buy `allOf` guard honoured.

---

### P-11 — `pagination.cursor` never emitted while `has_more` can be true; REST emits `cursor: null`

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc018-conceptid, uc018-listall (2,3),
uc005-baseline (risk 1)

**What is broken.** Verified in `src/core/tools/creatives/listing.py`:

```
:376   has_more = (page * limit) < total_count
:443   pagination=SchemaPagination(has_more=has_more, total_count=total_count)   # no cursor, ever
```

A buyer told `has_more: true` has no way to fetch page 2. Separately, `src/routes/api_v1.py`
returns `response.model_dump(mode="json")` at **ten** call sites (`:237,245,258,273,341,374,400,428,459,471`)
with no `exclude_none`, so every `None` optional serializes as a literal `null` — including
`pagination.cursor` on a terminal page, plus `format_summary`, `status_summary`, `sandbox`,
`context`, `errors`, `ext`.

**Mandate.** `v3.1.1 core/pagination-response.json` documents `cursor` as *"Only present when
has_more is true"*, types it `{"type": "string"}` (so `null` fails validation), and sets
`additionalProperties: false` on the block. Graded by `universal/pagination-integrity.yaml`
(universal tier, applies to every agent) — *"when `has_more` is true the `cursor` MUST be present"*
and *"An agent that carries a stale cursor onto the terminal page fails the second-page assertion."*

**Gate caveat, recorded not resolved.** uc018-listall could not settle whether
`universal/pagination-integrity.yaml` applies to us: it is `track: core` but declares
`agent.capabilities: [has_creative_library]` and `requires: [controller]`, and
`has_creative_library` lives inside the capabilities `creative` block, which the schema says is
*"Only present if creative is in supported_protocols."* This changes the **severity**, not the
correctness.

**Blocked scenarios.** `@T-UC-018-edge-pagination-next` (feature `:514-521`) literally says *"the
pagination includes a cursor for the next page"* and is dormant; wiring it will go **RED**, which is
the correct outcome. `T-UC-018-storyboard-list-all-creatives-after-sync`,
`T-UC-018-storyboard-filter-by-concept-id`, `T-UC-005-storyboard-baseline-format-id-object-shape`.

**Done when**
- [ ] `list_creatives` (and the sibling paginated reads) emit a `cursor` whenever `has_more` is true.
- [ ] REST routes use `model_dump(mode="json", exclude_none=True)` — audit all ten call sites.
- [ ] `@T-UC-018-edge-pagination-next` wired and green.

---

### P-12 — Format identity compared on `id` alone; `agent_url` never canonicalized or compared

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc006-fmtroundtrip (T1,T2,T3),
uc018-fmtfilter, uc005-roundtrip (C1)

**What is broken.** Three sites, one rule violated, and an internal asymmetry that proves the fix
is known:

1. `CreativeAgentRegistry.get_format` (`src/core/creative_agent_registry.py:863-884`) builds a
   throwaway `CreativeAgent(agent_url=…)`, fetches that agent's catalog, then matches
   `if fmt.format_id.id == format_id` — **`agent_url` is ignored entirely**. Under
   `ADCP_TESTING=true` (`:654-655`) the catalog is returned regardless of which agent was asked.
   A creative referencing `{agent_url: "https://someone-else.example", id: "display_300x250_image"}`
   is accepted as though we hosted it.
2. `src/core/tools/creatives/_processing.py:194-196` (create) and `:511-514` (update) do
   `if fmt.format_id == creative_format` — raw Pydantic equality. A trailing slash, uppercase host
   or explicit default port makes the match fail, `format_obj` stays `None`, the
   `if format_obj and format_obj.agent_url:` guard at `:199`/`:517` falls through, and generative
   detection + preview generation are **skipped with no error and no warning** (CLAUDE.md
   "No Quiet Failures").
3. `_update_existing_creative` (`_processing.py:118-128`) compares
   `new_agent_url != existing_creative.agent_url` byte-wise, so a canonically-equal resubmission
   rewrites the row and reports a spurious `changes: ["format"]`.
4. On the read side, `Creative.agent_url` is stored (`listing.py:296` reads it back) but participates
   in no filter predicate — two creatives with the same `id` on different agents are
   indistinguishable to every filter path.

**Asymmetry:** `list_creative_formats` already does it correctly —
`src/core/tools/creative_formats.py:296-307,312-313` filters on `format_id_identity`, and
`src/core/schemas/_base.py:145-199` canonicalizes via `adcp.signing.canonicalize_target_uri`.
One concept, two identity rules.

**Mandate.** `v3.1.1:static/schemas/source/core/format-id.json`: `required: ["agent_url","id"]` and
*"Callers comparing two `format-id` values MUST canonicalize `agent_url` per the AdCP URL
canonicalization rules before treating two formats as the same."* Canonicalization algorithm at
`dist/docs/3.1.1/reference/url-canonicalization.mdx`.

**Consequence for grading.** Because `agent_url` is never compared, a `Scenario Outline` over six
canonicalization spellings *would pass on every row and prove nothing* — it would pass because the
field is ignored, not because canonicalization works. This is why uc006-fmtroundtrip deliberately did
not write one, and why this issue must land before any canonicalization scenario is written.

**Blocked scenarios.** `T-UC-006-storyboard-format-id-roundtrip-on-sync`,
`T-UC-018-storyboard-filter-by-format-id-object`,
`T-UC-005-storyboard-format-id-roundtrip-from-products`,
`T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`.

**Done when**
- [ ] All four sites compare via `format_id_identity`.
- [ ] Canonicalization scenarios written only after the comparison is real.
- [ ] Note for the roundtrip scenario: production normalizes `agent_url` through Pydantic `AnyUrl`, which appends a trailing `/`; `canonical_agent_url` strips it. The storyboard's `field_value … == $context.product_format_id` byte-equality check and the schema's canonicalization MUST disagree the moment producer and consumer spell the URL differently. **Schema wins** — comparison is canonical, not verbatim.

---

### P-13 — `get_adcp_capabilities` under-declares five 3.1.1 flags, and a code comment claims a scenario is active that is not

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc001-finalize, uc001-refine,
uc002-gov-denied, uc002-gov-recovery, uc002-pending, uc003-creativefate, uc006-reception,
uc002-inv-nomatch, uc020-vast

**What is broken.** Verified — `src/core/tools/capabilities.py`:

```python
features = MediaBuyFeatures(
    inline_creative_management=True,
    property_list_filtering=supports_property_list_filtering(adapter),
    catalog_management=False,
)
media_buy = MediaBuy(portfolio=portfolio, features=features, execution=execution)
...
supported_protocols=[SupportedProtocol.media_buy],
specialisms=[AdcpSpecialism.sales_non_guaranteed],
```

Five 3.1.1 capability flags are never emitted. Confirmed by grep — 0 hits each in `src/`:

| flag | schema location | why it matters | correct value today |
|---|---|---|---|
| `media_buy.supports_proposals` | `get-adcp-capabilities-response.json:209`, `default: false` | gates the whole proposal-lifecycle storyboard set | `false` — honest, but undeclared reads as omission not decision |
| `media_buy.governance_aware` | same file, `default: false` — *"When false or absent, conformance runners skip those storyboards"* | gates `governance_denied` / `governance_denied_recovery` | `false` |
| `media_buy.creative_approval_mode` | enum `auto_approve`\|`require_human` — *"When absent, approval behavior is legacy-unspecified; runners SHOULD NOT treat omission as an affirmative auto-approval claim"* | gates `pending_creatives_to_start` | derivable **today** from `Tenant.approval_mode` (`src/core/database/models.py:84`, values `auto-approve`/`require-human`/`ai-powered`, read at `_sync.py:125`). Map `auto-approve → auto_approve`, `require-human → require_human`; **`ai-powered` has no 3.1.1 member** ("`ai_assisted` is intentionally not part of the enum until a behavioral contract is defined") so it must map to the ceiling `require_human`, not be dropped. |
| `creative.has_creative_library` | same file, `default: false` | gates library-persistence obligations; we ship `list_creatives`, `sync_creatives` and a real `CreativeRepository` and simply do not advertise it | needs a decision — the `creative` capability object is *"Only present if creative is in supported_protocols"*, so declaring it means declaring the `creative` protocol and its baseline bundle |
| collection-list targeting support | `core/targeting.json` — *"Seller must declare support in get_adcp_capabilities"* | see P-23 | `false` |

**Stale comment.** `src/core/tools/capabilities.py:255-265` asserts that declaring
`specialisms=[sales_non_guaranteed]` activates `pending_creatives_to_start`. At 3.1.1 that is false:
the specialism gate passes but the scenario's own
`requires_capability: media_buy.creative_approval_mode == auto_approve` does not, so the runner
grades `not_applicable`. The comment's stated purpose — *"the public declaration forces
prioritization of the remaining gaps instead of hiding them"* — is defeated: right now the gap **is**
hidden.

**Also.** There is no BDD or harness coverage of `get_adcp_capabilities` at all
(`grep -rn "get_adcp_capabilities" tests/harness/ tests/bdd/steps/` → only a middleware smoke test),
and `BR-UC-010-discover-seller-capabilities.feature` is unbound (T-03). Our specialism/protocol
declaration — the thing that decides which storyboards grade us — is asserted nowhere behaviourally.

**Blocked scenarios.** `T-UC-001-storyboard-proposal-finalize-action`,
`T-UC-001-storyboard-finalize-uses-refine-vocabulary`, `T-UC-002-storyboard-governance-*` (4),
`T-UC-002-storyboard-pending-creatives-state-transition`,
`T-UC-003-storyboard-creative-fate-after-cancellation`,
`T-UC-006-storyboard-creative-reception-stateful-render`, and every RETAG in S-01.

**Done when**
- [ ] `creative_approval_mode` derived from `Tenant.approval_mode` (the only one with backing data today).
- [ ] `supports_proposals`, `governance_aware`, collection-list support declared explicitly `false` with a rationale comment, mirroring the existing `catalog_management=False` block (`capabilities.py:170-190`).
- [ ] `has_creative_library` decided — a product call, not a one-line edit.
- [ ] The stale comment at `:255-265` corrected.
- [ ] A capabilities harness env + a UC-010 scenario pinning the declaration, so wiring a feature without flipping its flag fails loudly.

---

### P-14 — Per-creative validation failures emitted as transient `SERVICE_UNAVAILABLE`; `error.field` unset

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc006-prov-dst (T4),
uc006-fmtroundtrip (T4), uc006-prov-corrected

**What is broken.** Verified — `src/core/tools/creatives/_processing.py:34-56`:

```python
def _failed_sync_result(creative_id, error_msg, *, recovery=None, code="SERVICE_UNAVAILABLE") -> SyncCreativeResult:
```

`src/core/tools/creatives/_sync.py:177` and `:338-355` call it **without** forwarding the code or
recovery from the caught `AdCPValidationError`, whose class defaults are
`error_code="VALIDATION_ERROR"`, `recovery="correctable"` (`src/core/exceptions.py:421-426`).
So a buyer whose payload is wrong is told to retry an infra outage.

**Mandate.** `v3.1.1 enums/error-code.json` classifies `SERVICE_UNAVAILABLE` as
`recovery: "transient"` ("Retry with exponential backoff"). A conforming buyer retries a request
that can never succeed without correction. The same call site leaves `error.field` unset, which
`error-code.json:165` marks **MUST** for the `PROVENANCE_*` family.

The fix is small: `_failed_sync_result` already accepts `code=` and `recovery=` — pass them through.

**Blocked scenarios.** `T-UC-006-storyboard-format-id-roundtrip-on-sync` (its proposed row 3 asserts
only the error *count*, because asserting `SERVICE_UNAVAILABLE` would pin the defect into the
baseline), `T-UC-006-storyboard-provenance-digital-source-type-missing` (whose only satisfiable
graded fact today is `action == "failed"`, and it satisfies it for a reason unrelated to provenance).

**Done when**
- [ ] `_sync.py` forwards the caught error's code and recovery.
- [ ] `error.field` populated for validation failures.
- [ ] The `SERVICE_UNAVAILABLE` characterization assertions in the sweep's proposals are replaced with the correctable code.

---

### P-15 — REST body models drop spec-required fields (Pattern #5 boundary-completeness)

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc005-roundtrip (C7), uc018-listall (4,5),
uc003-notcancellable, uc002-gov-approved, uc008-*

**What is broken.** One defect class across five REST body models in `src/routes/api_v1.py`:

| body model | missing | consequence |
|---|---|---|
| `ListCreativeFormatsBody` (`:133-147`) | `context`, `pagination` | context echo unassertable on REST/e2e_rest; MCP wrapper (`creative_formats.py:522-535`) also takes no `pagination` |
| `ListCreativesBody` (`:146-168`) | structured `pagination`, `sort`, `account` | only legacy `page`/`limit`/`sort_by`/`sort_order` scalars; `list_creatives()` at `:438-458` never forwards a `PaginationRequest` even though the tool signature accepts one. The `list_all` storyboard's own `sample_request` posts `account: {brand:{domain}, operator, sandbox: true}` — a 422 under `extra="forbid"` |
| `UpdateMediaBuyBody` (`:96-117`) | `canceled`, `cancellation_reason` | REST rejects a spec-valid cancel with a *different* error than A2A/MCP (P-07) |
| `CreateMediaBuyBody` (`:76-93`) | `plan_id`, `governance_context` | REST **rejects a schema-valid 3.1.1 request outright** while MCP strips it and A2A drops it (P-16) |
| `activate_signal` wrappers (`signals.py:317-323`, `:366-373`) | `destinations`, `idempotency_key`, `pricing_option_id` | see P-20 |

`ListCreativeFormatsBody.adcp_version` additionally defaults to `"1.0.0"`, which does not match
`version-envelope.json`'s `^\d+\.\d+(-[a-zA-Z0-9.-]+)?$`.

**Mandate.** CLAUDE.md Pattern #5 — *"Forward **every** `_impl` parameter — don't silently drop
any"* — enforced by `test_architecture_boundary_completeness.py`, which evidently does not cover the
REST body models. Plus the per-field schema mandates cited in P-07/P-16/P-20.

The divergence is the sharp edge: the same request produces three different outcomes across three
transports, so no test can observe the real behaviour.

**Blocked scenarios.** `T-UC-005-storyboard-format-id-roundtrip-from-products` (context echo red on
REST/e2e_rest), `T-UC-018-storyboard-list-all-creatives-after-sync`,
`T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-002-storyboard-governance-approved`.

**Done when**
- [ ] All five body models carry the fields their `_impl` accepts.
- [ ] `test_architecture_boundary_completeness.py` extended to cover REST body models, not just wrappers.
- [ ] `adcp_version` default fixed.

---

### P-16 — `plan_id` and `governance_context` dropped at every transport boundary

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc002-gov-approved, uc002-gov-recovery,
uc030-govbinding (H), uc002-gov-conditions

**What is broken.** Verified: `grep -rn "plan_id\|governance_context" src/ --include='*.py'` →
**0 hits each.** Our wrappers enumerate parameters explicitly and declare neither:
MCP `src/core/tools/media_buy_create.py:4373-4420`, A2A/REST raw `:4495-4512`,
REST body `src/routes/api_v1.py:76-93`.

Transport-divergent: MCP strips it, A2A drops it, REST (`extra="forbid"` in dev/CI) **rejects a
schema-valid 3.1.1 request outright**.

**Mandate.**
- `v3.1.1 media-buy/create-media-buy-request.json:22-25` → `plan_id`: *"Required when the account has governance_agents. The seller includes this in the committed check_governance request so the governance agent can validate against the correct plan."* `adcp==6.6.0`'s `CreateMediaBuyRequest` declares it.
- `v3.1.1 core/protocol-envelope.json` → `governance_context`: *"Buyers attach it to governed purchase requests … sellers persist it and include it on all subsequent governance calls for that action's lifecycle … Sellers MAY verify; sellers that do not verify MUST persist and forward the token unchanged so auditors can verify downstream. In 3.1 all sellers MUST verify."*

The persist-and-forward clause binds **even a seller that never claims `governance-aware-seller`**,
once a buyer attaches a token. That makes this issue independent of P-05/P-13.

The "required when" condition is reachable today — UC-011 wires `governance_agents` end to end
(`tests/bdd/steps/domain/uc011_accounts.py:862-884`).

**Blocked scenarios.** `T-UC-002-storyboard-governance-approved`, `…-with-conditions`, `…-denied`,
`…-denied-recovery`, plus four wired UC-002 `plan_id` scenarios
(`BR-UC-002-create-media-buy.feature:2031,2044,2056,2069`) whose step phrasings all have zero
definitions, so all four are silently auto-xfailed.

**Done when**
- [ ] `plan_id` and `governance_context` declared on all three wrappers, forwarded into the request model, persisted on the media buy.
- [ ] Minimum honest behaviour: reject a create against a governance-bearing account when `plan_id` is absent.
- [ ] `governance_context` persisted and echoed unchanged on the envelope.
- [ ] The four dormant `plan_id` scenarios get step definitions and stop being invisible.

---

### P-17 — Delivery emits affirmatively wrong numbers: `clicks=0`, `ctr=0.0`, `currency="USD"`

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc004-delivery, uc004-reqmetrics

**What is broken.** Verified in `src/core/tools/media_buy_delivery.py`:

```
:343   "clicks": None,   # AdapterPackageDelivery doesn't have clicks yet   ← adapter clicks discarded
:521   clicks = 0
:523   ctr = (clicks / impressions) if clicks is not None and impressions > 0 else None
:675   currency="USD",  # TODO: @yusuf - This is wrong. Currency should be at the media buy delivery level, not on aggregated totals.
```

This is worse than a missing metric. `core/delivery-metrics.json` defines both `clicks` and `ctr` as
`{"type":"number","minimum":0}` with **no "0 means unknown" semantics**, so `ctr: 0.0` is an
affirmatively wrong number on the wire. The graded storyboard injects `clicks: 150`
(`delivery_reporting.yaml:196`).

`currency="USD"` satisfies the `^[A-Z]{3}$` pattern so it is not a schema violation, but it
misreports the currency for any non-USD buy — and `MediaBuy.currency` is right there on the model.

**Blocked scenarios.** `T-UC-004-storyboard-controller-driven-delivery-schema-compliance` (its
proposed Gherkin keeps `clicks 150` in the Given as a no-corruption control and deliberately does
**not** assert it, because asserting the current `0` would pin the bug).

**Done when**
- [ ] Clicks carried through `AdapterPackageDelivery`.
- [ ] `ctr` emitted as `None` when clicks are unknown, never `0.0`.
- [ ] `currency` derived from the buy / tenant currency limit; the TODO removed.

---

### P-18 — `measurement_terms` accepted and silently dropped; `TERMS_REJECTED` never emitted

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc002-measurement

**What is broken.** Verified: `grep -rn "measurement_terms\|TERMS_REJECTED" src/ --include='*.py'` →
**0 hits each.** `src/core/schemas/_base.py:1564` `PackageRequest(LibraryPackageRequest)` inherits the
field so it validates, and `src/core/tools/media_buy_create.py` never reads it.

Measured on all three wire transports against real Postgres: a create carrying the storyboard's own
deliberately-unacceptable terms (`max_variance_percent: 0`, `measurement_window: "c28"`) returns
`status: "completed"` with a `media_buy_id`, **byte-identical** to the same request with
`measurement_terms` omitted entirely. Confirmed packages also carry no `measurement_terms` echo —
real wire `packages[0]` = `{package_id, product_id, budget, pricing_option_id, paused, canceled}`.

**Mandate.**
- Graded at `protocols/media-buy/scenarios/measurement_terms_rejected.yaml:132-142` — `- check: error_code, value: "TERMS_REJECTED"`. Code defined at `v3.1.1 enums/error-code.json` index 53, `enumMetadata.TERMS_REJECTED.recovery = "correctable"`.
- Echo: `v3.1.1 media-buy/package-request.json` — "Seller accepts (**echoed on confirmed package**), rejects with TERMS_REJECTED, or adjusts"; `core/measurement-terms.json` — "Appears on products (seller defaults), package requests (buyer proposals), and **confirmed packages (agreed terms)**". Storyboard-ungraded prose (`:160-162`), so it does not block, but it makes the negotiation round-trip unobservable.
- Also needed for green: `field_present context` + `field_value context.correlation_id` **on the error envelope** (`:136-142`) — see P-09.

**Related, blocked behind this.** `measurement_terms_rejected.yaml:203` `reviewer_checks` requires
that after a `TERMS_REJECTED` response, a retry with the **same** `idempotency_key` and corrected
terms returns a **fresh** `media_buy_id`, not `IDEMPOTENCY_CONFLICT` (`security.mdx#idempotency`
rule 3, "Only successful responses are cached"). `_cache_and_return`
(`media_buy_create.py:1847`) documents the right shape, but no test exercises it and none can until
`TERMS_REJECTED` exists.

**Tier caveat, recorded.** uc002-measurement flagged that `measurement_terms_rejected` is in
`protocols/media-buy/index.yaml:13` `requires_scenarios` (we declare the protocol) but absent from
`sales-non-guaranteed` — and `capabilities.py:256-259` asserts *"The runner gates scenarios by
specialism, not by `supported_protocols` alone."* If the comment is right the tag should be
`@schema-v3.1`. Cheap to flip; worth a second opinion. This is the same ambiguity as T-07.

**Blocked scenarios.** `T-UC-002-storyboard-measurement-terms-rejected`.

**Done when**
- [ ] `measurement_terms` evaluated; `TERMS_REJECTED` emitted with `recovery: correctable`.
- [ ] Accepted terms echoed on the confirmed package.
- [ ] The idempotency-claim-release behaviour tested.

---

### P-19 — `SyncCreativeResult.status` never populated; MCP serializes it as `null`

**Class:** PRODUCTION · **Severity:** S2 · **Raised by:** uc006-multiformat ([A],[B]),
uc006-reception (1,2,3), uc006-fmtroundtrip (T5), uc006-prov-corrected (6), uc006-prov-required

**What is broken.** `src/core/schemas/creative.py:369-378` records the owner decision to inherit but
not populate the spec `status`: it stays `None`. The internal state lives in `internal_status`
(`exclude=True`). Executed probe (uc006-multiformat, three creatives): `status=None` on every
result, absent from `model_dump()`.

Two separable defects:

**19a — the omission may not be permitted for us.** `v3.1.1 creative/sync-creatives-response.json`
permits omission only as *"Omit entirely when the seller has no review lifecycle at all."* The same
probe log shows *"Created 3 workflow steps for creative approval"* — we demonstrably **have** a
review lifecycle and an internal `pending_review` state, so the carve-out does not apply.

**19b — MCP emits `status: null`, which is schema-invalid.** The in-code comment states it plainly:
*"on MCP the response goes through `structured_content` → `to_jsonable_python`, which BYPASSES the
`model_dump` override, so the inherited `status` serializes as null."* `status` `$ref`s
`enums/creative-status.json`, a string enum — `null` is not a member. The key being *present* also
trips the schema's `if action ∈ {failed, deleted} then not required: ["status"]`. A2A/REST are
unaffected (`exclude_none=True` at `creative.py:414-415`).

**Adjacent.** Local `CreativeStatusEnum` (`creative.py:123-129`) defines
`{processing, approved, rejected, pending_review}` while 3.1.1 has
`{processing, pending_review, approved, suspended, rejected, archived}` — `suspended` and `archived`
are missing, and `archived` is written as a bare string at `_sync.py:377-379`, bypassing the enum.
The enum is declared *"not in adcp library, local definition"* although `adcp.types.CreativeStatus`
is imported at `creative.py:13`.

**Blocked scenarios.** `T-UC-006-storyboard-multi-format-sync`,
`T-UC-006-storyboard-creative-reception-stateful-render`.

**Done when**
- [ ] `internal_status` mapped onto the spec `status` using `enums/creative-status.json` members, honouring the `failed`/`deleted` exclusion — **or** the omission decision is recorded with the "no review lifecycle" carve-out explicitly ruled inapplicable.
- [ ] MCP's `structured_content` path stops emitting `status: null` (19b is a violation either way).
- [ ] Local `CreativeStatusEnum` replaced with `adcp.types.CreativeStatus`.

---

### P-20 — Signals surface is structurally non-conformant and registered on no transport

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc008-baseline (T2–T8),
uc008-agentdest, uc008-platformdest

**Six defects in one subsystem, gated behind one decision.**

1. **`ActivateSignalResponse` has no `deployments`.** Verified — `src/core/schemas/_base.py:2458-2471`
   declares `signal_id`, `activation_details: dict[str, Any] | None`, `errors`, `context`, with a
   docstring conceding *"Library uses structured list[Deployment] vs our generic activation_details
   dict"* and *"Library enforces atomic success/error; we allow both simultaneously."*
   `v3.1.1 signals/activate-signal-response.json` puts `"required": ["deployments"]` on the success
   branch (items `$ref core/deployment.json`) and `"not": {"required": ["errors"]}` — our response
   matches **neither** branch.
2. **The wrapper fabricates the two REQUIRED request fields.** `src/core/tools/signals.py:239-247`
   hardcodes `destinations=[{"type":"platform","platform":"mock"}]` and
   `idempotency_key=f"activate-{signal_agent_segment_id}".ljust(16,"0")[:255]`. Neither
   `activate_signal` (`:317`) nor `activate_signal_raw` (`:366`) exposes `destinations` or
   `pricing_option_id`. `activate-signal-request.json` requires `idempotency_key`,
   `signal_agent_segment_id`, `destinations` (`minItems: 1`); `idempotency_key` is a
   client-generated value whose whole purpose — dedupe on retry — is defeated by server synthesis.
3. **`get_signals` matching is naive substring containment** (`signals.py:161-168`) and the
   `signals_baseline` storyboard's own `sample_request.signal_spec`,
   `"Adults interested in electric vehicles"` (`protocols/signals/index.yaml:121`), matches **none**
   of the six hardcoded sample signals → `signals == []` and the graded
   `field_present signals[0].signal_agent_segment_id` (`:132-134`) fails.
4. **Only the deprecated `signal_id` is emitted.** `signals.py:45-55`. 3.1.1 marks `signal_id`
   `"deprecated": true` and defines `signal_ref` (`$ref core/signal-ref.json`) as the canonical
   reference. The existing comment at `signals.py:51` already flags this.
5. **`_activate_signal_impl` is a pure façade.** `signals.py:279-308` synthesises
   `decisioning_platform_segment_id = f"seg_{…}_{uuid4().hex[:8]}"` and a fixed
   `estimated_activation_duration_minutes: 15.0` with no HTTP call.
   `specialisms/signal-marketplace/index.yaml:353-363` grades `check: upstream_traffic`
   (`min_count: 1`, `endpoint_pattern: "POST *"`) with the explicit rationale *"An adapter returning
   a fabricated activation_key without touching the DSP fails this check."*
6. **The tools are registered on no transport.** `src/core/tools/__init__.py:25`:
   *"Signals tools removed - should come from dedicated signals agents, not sales agent"*; same
   decision at `src/a2a_server/adcp_a2a_server.py:89,1484,1819,2318`.
   `docs/V2_ROADMAP_SUGGESTION.md` records UC-008 as "Dead code, deregistered (#1003)". We are a
   signals *consumer* (`src/core/signals_agent_registry.py`), never a provider.

**The decision that gates all six.** Either declare `supported_protocols: [signals]`
(+ `signal-marketplace` for activation) and build to it, or delete `src/core/tools/signals.py` and
retire `BR-UC-008-manage-audience-signals.feature` (1154 lines, ~90 scenarios, unbound — T-03).
The current middle state is dead code plus dormant tests. Related, flagged by the lead: the
capabilities emitter and the AgentCard disagree about advertising `get_signals`.

**Blocked scenarios.** All three `T-UC-008-storyboard-*`.

**Done when**
- [ ] The scope decision recorded (declare-and-build, or delete-and-retire).
- [ ] If building: items 1–5 fixed and the tools registered.
- [ ] If deleting: `signals.py`, the feature file, and its `bdd-traceability.yaml` rows removed together.

---

### P-21 — Provenance policy resolved tenant-wide from `provenance_policies[0]`, not per-product

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc006-prov-required (T2),
uc006-prov-disclosure (T2), uc006-prov-dst (T6), uc006-prov-corrected (5)

**What is broken.** `src/core/tools/creatives/_sync.py:140-146,184` passes
`provenance_policies[0]` — with the in-code comment *"Use the first matching policy (tenant-wide
enforcement)"* — to every creative in the sync, regardless of which product the creative targets.
The list comes from `CreativeRepository.get_provenance_policies()`
(`src/core/database/repositories/creative.py:263-273`), which filters on
`p.creative_policy.get("provenance_required")` alone.

Two defects: (a) a tenant with two products under different `provenance_requirements` gets whichever
row the query returns first — non-deterministic across tenants; (b) a product publishing
`provenance_requirements` **without** `provenance_required: true` is invisible to enforcement
entirely.

**Mandate.** `v3.1.1 core/creative-policy.json` title: *"Creative requirements and restrictions for
**a product**."* The storyboard binds the requirement to the product discovered via `get_products`
(`provenance_enforcement.yaml:83-140`, phase `discover_requirement`).

**Blocks.** Any correct implementation of P-04.

**Done when**
- [ ] Policy resolved from the product(s) the creative is destined for.
- [ ] `get_provenance_policies` reads `provenance_requirements`, not only `provenance_required`.

---

### P-22 — Proposal/refine lifecycle absent; `refine` silently discarded; `brief` accepted with `buying_mode: refine`

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc001-finalize, uc001-refine

**Ordered by what is actually on our conformance path.**

**22a — `brief` alongside `buying_mode: "refine"` is accepted. This one is on our path.**
`GetProductsRequest.model_validate({"buying_mode":"refine","brief":"x","refine":[…]})` succeeds
(executed). `v3.1.1 media-buy/get-products-request.json:50-52` → `properties.brief.description`:
*"Must not be provided when `buying_mode` is 'wholesale' or 'refine'."* Not proposal-gated —
`media_buy_seller/refine_products` is in `protocols/media-buy/index.yaml:11` `requires_scenarios`,
which we do declare. **Highest-value item in this issue.**

**22b — `refine` is accepted and silently discarded.** The request model accepts the array
(inherited at `src/core/schemas/product.py:231`) and `src/core/tools/products.py` never reads
`req.refine` — a quiet failure, prohibited by `.claude/rules/patterns/code-patterns.md`.
`get-products-request.json` `refine`: *"The seller responds to each entry via `refinement_applied`
in the response, matched by position."* We emit no `refinement_applied`.

**22c — finalize-exclusivity is not enforced.** Executed: `GetProductsRequest` accepts
`refine: [{scope: proposal, proposal_id: p1, action: finalize}, {scope: request, ask: "more CTV"}]`.
3.1.1 `get-products-request.json:53`: *"if any entry has `action: 'finalize'`, ALL entries in the
array MUST be proposal-scoped with `action: 'finalize'` — mixing finalize entries with
`include`/`omit` entries or with request-/product-scoped entries MUST be rejected by the seller with
`INVALID_REQUEST`."* Graded at `refine_finalize_exclusivity.yaml:204-212`. Independently
implementable today as a `model_validator`.

**22d — multi-finalize atomicity unenforced; `MULTI_FINALIZE_UNSUPPORTED` not in our catalog.**
Two proposal-scoped finalize entries are accepted. Same schema clause: *"Sellers that cannot
guarantee atomic pre-commit validation MUST reject multi-finalize arrays with
`MULTI_FINALIZE_UNSUPPORTED` (preferred …) or `INVALID_REQUEST`."* Graded at
`refine_finalize_exclusivity.yaml:390-403`. The code exists in the SDK catalog and is never emitted —
feeds the existing error-code reconciliation epic.

**22e — no proposal lifecycle at all.** `grep -rn "proposals\|proposal_status\|PROPOSAL_NOT_FOUND" src/`
→ zero hits. Gated behind the `media_buy.supports_proposals` decision (P-13).

**Caveat recorded.** uc001-refine notes `refine_finalize_exclusivity.yaml` is required by no
`requires_scenarios:` list in `dist/compliance/3.1.1/` — treated as informative for spec intent
(it quotes the same normative schema clauses), not as a grading authority. If the runner discovers
scenario files by directory scan rather than by index, 22c/22d rise in priority.

**Executed evidence matrix** (uc001-refine, against
`GetProductsRequest.model_validate({"buying_mode":"refine","refine":[entry]})`) — ten rows match
3.1.1 correctly; the four that do not are 22a, 22c and 22d (two rows).

**Blocked scenarios.** `T-UC-001-storyboard-proposal-finalize-action`,
`T-UC-001-storyboard-finalize-uses-refine-vocabulary` and its four `BR-RULE-086` siblings
(feature `:741,749,758,766,1766`) — all inside a feature file that is unbound (T-03).

**Done when**
- [ ] 22a fixed first — cross-field validator on `GetProductsRequest`, on our conformance path today.
- [ ] 22c as an array-level `model_validator` raising `INVALID_REQUEST` with `field` naming the offending entry index.
- [ ] 22b/22d/22e sequenced behind the `supports_proposals` decision in P-13.

---

### P-23 — `collection_list` accepted with zero validation, zero capability declaration, zero wire signal

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc002-inv-nomatch (2),
uc002-inv-targeting (7.2)

**What is broken.** `collection_list` / `collection_list_exclude` are declared fields on our
`Targeting` (inherited from the library `TargetingOverlay`, `src/core/schemas/_base.py:104-112,1167`),
so they never land in `model_extra` and `validate_unknown_targeting_fields` raises nothing. Then
nothing validates them: no capability check, no product flag, no rejection, no advisory.
`src/services/targeting_capabilities.py:216-227` states the asymmetry explicitly ("Collection-list
capability infrastructure lands separately").

Measured (uc002-inv-nomatch, 18 combinations across mcp/a2a/rest): a `collection_list` that matches
nothing is persisted, never resolved, never mentioned on the wire — `errors` is **absent from the
response entirely**. That is exactly the failure mode the `inventory_list_no_match` narrative
forbids: *"What the seller must NOT do: … silently drop the targeting and deliver against unintended
inventory."*

`property_list` got an `UNSUPPORTED_FEATURE` advisory for precisely this window; `collection_list`
did not.

**Mandate.** `v3.1.1 core/targeting.json` → `collection_list` and `collection_list_exclude`:
*"Seller must declare support in get_adcp_capabilities."* We declare nothing either way (P-13).

**Blocked scenarios.** `T-UC-002-storyboard-inventory-list-no-match`,
`T-UC-002-storyboard-inventory-list-targeting-parity`.

**Done when**
- [ ] Collection-list support declared (as `false`) in `get_adcp_capabilities`.
- [ ] The sibling `UNSUPPORTED_FEATURE` advisory emitted while it is off — or a hard rejection, but not silence. (Coordinate with P-02: the advisory must not ride the success envelope.)

---

### P-24 — `error.field` is index-less and transport-dependent

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc002-inv-nomatch (4), uc018-fmtfilter

**24a — index-less path.** `src/core/validation_helpers.py::package_field_path` produces
`packages[]` with an **empty subscript**; `raise_if_property_targeting_violations` passes it through
(`src/services/targeting_capabilities.py:325`). Observed verbatim on the wire on mcp/a2a/rest:
`field = "packages[].targeting_overlay.property_list"`. `v3.1.1 core/error.json` → `field`:
*"Field path associated with the error in JSONPath-lite format (e.g., 'packages[0].targeting')."*
The buyer cannot tell which package failed when several are sent.

**The fix is already written elsewhere:** `build_property_list_unsupported_advisories` emits
`packages[{index}].targeting_overlay.property_list` (`targeting_capabilities.py:257`). The rejection
path just needs the same index.

**24b — transport-dependent path.** Measured (uc018-fmtfilter) for one malformed request:
a2a/rest emit `field: "format_ids[0]"`, mcp emits `field: "filters.format_ids[0]"`; the a2a/rest
`message` is the long "does not match the AdCP specification" narrative while mcp's is the bare
Pydantic string. `core/error.json` types `field` as a single protocol-level pointer — one request
shape must produce one pointer. Pattern #5.

**Done when**
- [ ] Rejection paths carry the package index.
- [ ] One request shape produces one `field` pointer and one message across all four transports.

---

### P-25 — `include_package_daily_breakdown` ignored; `viewability` is a scalar where 3.1.1 requires an object

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc004-delivery

**25a.** `include_package_daily_breakdown` is threaded from all three transports
(`media_buy_delivery.py:733,751,804,860`; `api_v1.py:396`; `adcp_a2a_server.py:2051`) into the
request model and then **never read**. `MediaBuyDeliveryData.daily_breakdown` is hardcoded `None`
(`media_buy_delivery.py:549`) and `PackageDelivery` (`delivery.py:159+`) has no `daily_breakdown`
field at all, so the package-level array the flag names cannot be represented. The 3.1.1 request
schema defines it as *"When true, include daily_breakdown arrays within each package in
by_package"*; the graded step sends `true` (`delivery_reporting.yaml:226`).
Fix: add `daily_breakdown: list[DailyBreakdownEntry] | None` to `PackageDelivery`
(schema `required: ["date","impressions","spend"]`, `date` pattern `^\d{4}-\d{2}-\d{2}$`).

**25b.** `src/core/schemas/delivery.py:119` declares
`viewability: float | None = Field(None, ge=0, le=1, …)`. In 3.1.1 `core/delivery-metrics.json`,
`viewability` is `{"type": "object"}` carrying `measurable_impressions`, `viewable_impressions`,
`viewable_rate`, `viewed_seconds`, `standard`, `vendor`. Production assigns it straight from the
adapter (`media_buy_delivery.py:360,548`), so any seller that populates it emits a bare float and
fails `response_schema`. This also leaves the storyboard's entire `viewability_delivery` phase
(`delivery_reporting.yaml:234-370`, **six** graded `field_present` checks on
`media_buy_deliveries[0].totals.viewability.*`) with zero coverage.

Both fold naturally into P-06 (extend the library type) but are separately testable.

---

### P-26 — `update_media_buy` does not enforce `idempotency_key` (REQUIRED at 3.1.1)

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc003-mbnotfound, uc003-pkgnotfound

**What is broken.** `git show v3.1.1:static/schemas/source/media-buy/update-media-buy-request.json`
declares `"required": ["idempotency_key", "account", "media_buy_id"]`.
`UpdateMediaBuyRequest` (`src/core/schemas/_base.py:2005-2011`) overrides **both** `account` and
`idempotency_key` to optional, with an in-code note calling the required-key enforcement
"a deliberate fast-follow". Verified by introspection: `UpdateMediaBuyRequest(media_buy_id="x", paused=True)`
constructs cleanly.

**Scope split — this matters.** `account` optionality is a deliberate, tracked interim (account
management is in flight; see the project note that the `account` field is temporarily optional).
**`idempotency_key` is not covered by that** and is a separate conformance break: every 3.1.1
`update_media_buy` request must carry one.

Compounded on the test side: `account` is in `_WRAPPER_UNSUPPORTED_FIELDS`
(`tests/harness/media_buy_update.py:50`) and stripped before dispatch, so the storyboard's `account`
block cannot even reach production through BDD (T-08).

**Caveat.** Tightening either turns most of BR-UC-003 red today, so this is not a baseline-PR change.

**Done when**
- [ ] `idempotency_key` required on `UpdateMediaBuyRequest`, with the BR-UC-003 fallout fixed in the same change.
- [ ] `account` tracked separately under the account-management work.

---

### P-27 — No inbound `preview_creative` or `build_creative` tool; two stale comments claim they aren't in the spec

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc021-preview, uc020-vast

**What is broken.** Both tools exist only as **outbound** MCP client calls we make *to* third-party
creative agents from `sync_creatives`:

```
src/core/creative_agent_registry.py:885   CreativeAgentRegistry.preview_creative   (outbound)
src/core/creative_agent_registry.py:996   client.call_tool("build_creative", params) (outbound)
   reached from src/core/tools/creatives/_processing.py:253,359,565,649
```

`src/core/main.py:351-366` registers 16 tools; neither is among them. No MCP wrapper, no A2A raw
function, no REST route, no harness env (`tests/harness/` has 20 envs, none for preview).

**Two stale comments actively mislead the "should we implement this" decision:**

- `src/core/creative_agent_registry.py:917`: *"Use custom MCP client for non-standard tools (preview_creative not in AdCP spec)"* — it **is** in the spec at 3.1.1: `static/schemas/source/creative/preview-creative-{request,response}.json`, with `doc_ref: "/creative/task-reference/preview_creative"` on three separate storyboard steps.
- `src/core/creative_agent_registry.py:981`: *"build_creative not in AdCP spec"* — false at 3.1.1: `static/schemas/source/media-buy/build-creative-{request,response}.json` both exist.

**The `preview_creative` gap is on a protocol we DO declare.**
`protocols/media-buy/scenarios/creative_reception.yaml:186-240` — a media-buy step — has
`requires_tool: preview_creative` (line 197), and we forfeit the only graded `preview_url` check at
3.1.1 (`previews[0].renders[0].preview_url`, line 239). `build_creative` sits behind the
`creative-ad-server` specialism + `creative` protocol, neither declared, so it is a scope decision
rather than a conformance failure.

**Blocked scenarios.** `T-UC-021-storyboard-preview-display-from-synced-manifest`,
`T-UC-020-storyboard-build-vast-tag-from-synced-creative` (both in unbound files, T-03).

**Done when**
- [ ] Both comments corrected (one-line each, but load-bearing for the decision).
- [ ] `preview_creative` `_impl` + 3 transport wrappers + a preview harness env — it is on the media-buy path.
- [ ] `build_creative` scope decided alongside the `creative` protocol question in P-13.

---

### P-28 — `pending_creatives → pending_start` transition does not exist; three duplicated transition blocks

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc002-pending

**What is broken.** Every writer of `MediaBuy.status` on a buyer-facing path was enumerated; none
performs this transition:

```
src/core/tools/creatives/_assignments.py:283-285   draft → pending_creatives only (when approved_at is not None)
src/core/tools/media_buy_update.py:942-951         draft → pending_creatives only
src/core/tools/media_buy_update.py:1178-1187       draft → pending_creatives only  ← identical to the above (DRY)
src/services/media_buy_status_scheduler.py:88-90   candidate query = ["pending_start","pending_activation","scheduled","active"]
                                                    → pending_creatives is NOT in it, so a buy parked there is never examined
```

A buy created without creatives is persisted `pending_creatives`
(`media_buy_create.py:3645`) and stays there forever from the buyer's perspective. The remaining
writers are Admin-UI operator actions, not the buyer protocol path.

**Mandate.** `pending_creatives_to_start.yaml:253-256`
(`field_value media_buy_status allowed_values: ["pending_start","active"]` on step
`assign_creative_to_package`) and again at `:294-297` on `get_media_buy_after_sync`. Also
`enums/media-buy-status.json`, whose `pending_creatives` enumDescription defines the state as
cleared once the buyer attaches creatives. Must respect the `status.monotonic` invariant declared at
`specialisms/sales-non-guaranteed/index.yaml`.

**Which action unblocks it — a real schema/storyboard split.** `media-buy-status.json` says the buyer
"must attach creatives via `sync_creatives`"; the storyboard grades the transition on
`update_media_buy` (its `sync_creatives` step validates `response_schema` and nothing else). In
practice both are needed: sync ingests the asset, update binds it to the package. The current
scenario asserts the transition off `sync_creatives` alone, which matches neither.

**Related.** Package-level `context` is dropped: `media_buy_create.py:4073-4086` constructs the
response `Package` without `context=` though `adcp.types.aliases.Package` declares
`context: ContextObject | None`. Graded at `pending_creatives_to_start.yaml:165-168` and `:302-305`
("legacy package correlation" — buyers depend on it for package↔line-item mapping). Pairs with the
per-buy `context` half in P-10.

**Done when**
- [ ] The transition implemented on the buyer path, honouring `status.monotonic`.
- [ ] The three `draft → pending_creatives` copies folded into one shared helper (CLAUDE.md DRY) — the natural home for the new transition logic.
- [ ] `media_buy_status_scheduler` candidate query includes `pending_creatives`.
- [ ] Package-level `context` echoed on create and read.

---

### P-29 — `GovernanceAgent` rejects the required `authentication` block and accepts plaintext `http://` URLs

**Class:** PRODUCTION · **Severity:** S3 · **Raised by:** uc030-govbinding (C, F, G)

**29a — spec-shaped registration is rejected at the model boundary.**
`src/core/tools/accounts.py:255-273` (`_serialize_governance_agents`) validates every incoming agent
through `adcp.types.generated_poc.core.account.GovernanceAgent`, which is `extra="forbid"` with
`url` as its only field (verified: passing `authentication` raises `extra_forbidden`).
`sync-governance-request.json` declares the agent item `required: ["url", "authentication"]` with
`authentication.credentials.minLength: 32`. So we can never accept credentials, and therefore can
never call a governance agent even if P-05 were done. The SDK type is modelled on the *response*
shape (`core/account.json`, url-only) and is being reused for the *request* shape; those are
deliberately asymmetric (credentials are write-only). Needs a separate request-side model.

**29b — `^https://` is never enforced.** `core/account.json` and `sync-governance-request.json` both
declare `"pattern": "^https://"` on `url`. The SDK `GovernanceAgent.url` is
`{"type":"string","format":"uri","minLength":1}` — the pattern is **dropped in codegen**. Verified:
`GovernanceAgent.model_validate({'url':'http://plain.example'})` is **accepted** and normalises to
`http://plain.example/`. Since that model is our DB column type
(`src/core/database/models.py:827-829`) and our response type, we persist and echo plaintext
governance endpoints. Schema wins over SDK: add explicit validation, do not wait on an SDK fix.
(This is the same class as #1582 — see §3.)

**29c — `sync_accounts` never echoes the governance binding.** `_build_sync_result`
(`src/core/tools/accounts.py:~313`) omits `governance_agents` entirely; the value is only readable
via a follow-up `list_accounts` (`:70`). Not a `sync_accounts` violation today (that response schema
does not declare the field), but it is the shape P-05 must ship
(`sync-governance-response.json` requires the persisted agent in `accounts[].governance_agents`).

**Blocked scenarios.** `@T-UC-030-bva-url` expects `URL_NOT_HTTPS` for `http://` and will fail
whenever BR-UC-030 is wired (T-03).

---

### T-01 — `then_response_schema_valid` runs no validator, and exists twice with divergent strength

**Class:** TEST-INFRA · **Severity:** S1 · **Raised by:** 22 proposals

**This is the single highest-leverage test-infra item on the slate.** `- check: response_schema` is
the most-graded check across every 3.1.1 storyboard, and it has no honest representation anywhere in
the BDD suite.

**Verified — two steps, one phrasing, different rigour:**

```python
# tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-108   ← THE VACUOUS ONE
@then("the response should be schema-valid against list-creative-formats-response.json")
def then_response_schema_valid(ctx: dict) -> None:
    formats = _serialized_formats(ctx)
    assert isinstance(formats, list), f"Expected formats to be a list, got {type(formats).__name__!r}"
```

```python
# tests/bdd/test_uc018_list_creatives.py:216-220                 ← THE REAL ONE
@then(parsers.parse("the response should be schema-valid against {schema_file}"))
def then_response_schema_valid(ctx: dict, schema_file: str) -> None:
    validate_against_pinned_schema(schema_file, _serialized_response(ctx))
```

`tests/helpers/pinned_schema.py::validate_against_pinned_schema` exists and is called by exactly one
module. Two steps with one phrasing and different rigour is the DRY defect CLAUDE.md treats as a
correctness bug — and the weak one is the one most scenarios would bind to.

**Correction to the brief.** The blanket claim "`then_response_schema_valid` runs no validator" is
wrong as stated: it is true of the UC-005 copy and false of the UC-018 copy. Several proposals
(uc003-creativefate, uc018-fmtfilter, uc018-listall) independently caught this.

**Wiring it will go red** — deliberately, and correctly — on P-01 (missing `status`), P-02
(advisory `errors` on success), P-06 (`by_package` required fields), P-11 (`cursor: null`),
P-19 (`status: null` on MCP). Do not soften the step to dodge them.

**Blocked scenarios.** ~30 — every scenario whose storyboard grades `response_schema`.

**Done when**
- [ ] One registered implementation in a shared plugin module (pytest-bdd 8 resolves per-module, so it must be a registered plugin, not an import).
- [ ] The UC-005 copy migrated to it and deleted.
- [ ] T-02 landed first, or the validator grades a superseded contract.
- [ ] The scenarios it turns red are triaged against P-01/P-02/P-06/P-11/P-19, not worked around.

---

### T-02 — Pinned schema fixtures vendored at `04f59d2d5`, behind our own 3.1.1 pin

**Class:** TEST-INFRA · **Severity:** S1 · **Raised by:** 20 proposals

**Verified.** `tests/helpers/pinned_schema.py:5-6` — *"pinned at adcontextprotocol/adcp@04f59d2d5
(tag `v3.1-04f59d2d5`)"*. That commit is an **ancestor of `v3.1.0-beta.3`**, i.e. older than the
repo's own 3.1.1 pin. Concrete measured consequences:

| instance | measured |
|---|---|
| `enums/error-code.json` holds **64** codes; 3.1.1 has **92** | verified by `json.load` — `TransportResult.assert_wire_error` (`tests/harness/transport.py:164-169`) rejects any code absent from the snapshot, so it silently blocks any scenario grading one of the 28 codes 3.1.1 added |
| `core/activation-key.json` is **missing** | verified `ls` — `core/deployment.json` `$ref`s it, and `pinned_schema.py:36-40` treats a missing ref as a **hard failure**, so validating any `deployments[]` entry raises `AssertionError: Pinned schema not vendored` before any real check runs |
| no `sponsored-intelligence/` directory | verified `ls` — every SI schema assertion hard-fails the instant UC-014 is wired |
| `signals/activate-signal-response.json` lacks the `{"$ref": "/schemas/core/protocol-envelope.json"}` `allOf` entry | that is the sole diff vs v3.1.1 — the vendored copy silently does not enforce top-level `status` (P-01) |
| `media-buy/get-products-request.json` lacks the 3.1.1 top-level `allOf` conditional and the whole finalize-exclusivity / multi-finalize contract in the `refine` description | any request-level assertion against the pinned tree is weaker than 3.1.1 (P-22) |
| `creative/list-creative-formats-response.json` lacks the `protocol-envelope` ref | P-01 unenforced there too |

**Not uniformly stale.** uc004-vendormetric verified the vendored tree **does** already carry
3.1.1-era `core/vendor-metric-value.json`, `core/reporting-capabilities.json` (with `vendor_metrics`)
and `core/product-filters.json` (with `required_vendor_metrics`) — so the blanket "vendored at
04f59d2d5" framing overstates it for some files. Check per file before acting.

**Where re-vendoring is free.** uc018-listall validated live a2a/mcp/rest `list_creatives` responses
against the true v3.1.1 `$ref` closure: **0 errors on all three**. For that tool the refresh is a
no-op risk-wise and a real strengthening.

**Done when**
- [ ] `tests/fixtures/adcp_schemas_pinned/_refresh.py` re-run at `v3.1.1` (`467fd93d7`), closing the `$ref` closure (`activation-key.json`, `protocol-envelope.json` + `task-status`/`error`/`context`/`push-notification-config`).
- [ ] SI schemas vendored, or SI schema-shape assertions explicitly recorded as out of scope.
- [ ] The docstring pin string updated.
- [ ] Full BDD suite re-run to find the tools where the refresh is **not** free — that list is the real output of this ticket.

---

### T-03 — 21 BDD feature files have no `scenarios()` binding and are never collected

**Class:** TEST-INFRA · **Severity:** S1 · **Raised by:** uc001-finalize, uc001-refine,
uc002-gov-conditions, uc008-baseline, uc008-agentdest, uc008-platformdest, uc014-session,
uc020-vast, uc021-preview, uc030-govbinding

**Verified independently and it is broader than any single proposal saw.** Diffing every
`BR-UC-*.feature` against every `scenarios("features/…")` call in `tests/bdd/*.py`:

```
BR-UC-001-discover-available-inventory.feature      BR-UC-016-sync-audiences.feature
BR-UC-007-list-authorized-properties.feature        BR-UC-017-account-financials-usage.feature
BR-UC-008-manage-audience-signals.feature           BR-UC-020-build-creative.feature
BR-UC-009-update-performance-index.feature          BR-UC-021-preview-creative.feature
BR-UC-010-discover-seller-capabilities.feature      BR-UC-022-creative-delivery-features.feature
BR-UC-012-manage-content-standards.feature          BR-UC-023-sync-product-catalogs.feature
BR-UC-013-manage-property-lists.feature             BR-UC-024-content-compliance.feature
BR-UC-014-sponsored-intelligence-session.feature    BR-UC-025-property-features-validation.feature
BR-UC-015-track-conversions.feature                 BR-UC-027-manage-async-tasks.feature
                                                    BR-UC-028-manage-collection-lists.feature
                                                    BR-UC-030-manage-governance-binding.feature
                                                    BR-UC-032-compliance-test-controller.feature
```

**21 files. Roughly 600 scenarios that have never executed a line of production code.** Not xfailed —
never *collected*, so they do not appear in run counts at all, and the BDD structural guards
(`test_architecture_bdd_no_trivial_assertions.py`, `..._no_pass_steps.py`) never see them because
those guards scan step *bodies* and no bodies exist.

Named instances with size: UC-001 (~40 scenarios, 2000+ lines), UC-008 (1154 lines, ~90 scenarios),
UC-014 (~200 scenarios), UC-020 (1028 lines, ~60 scenarios), UC-021 (966 lines, ~40 scenarios),
UC-030 (582 lines, 45 scenarios).

Six `@storyboard-v3.1` scenarios live in these files and claim conformance grading they cannot
receive. `docs/test-obligations/bdd-traceability.yaml` claims traceability for all of them
(`:746`, `:752`, `:5745`, `:5751`, `:5757`, `:11649`, `:12076`, `:15828`, …) — a traceability index
pointing at dead scenarios is worse than no index.

**Sequencing trap.** Adding a binder without step definitions fails collection wholesale. Bind and
implement together, use-case by use-case, or the file silently re-enters dormancy.

**Done when**
- [ ] Each of the 21 files gets an explicit decision: bind (with steps), delete, or move to a documented `features/unbound/` area so dormancy is visible rather than inferred.
- [ ] A guard fails when a `.feature` file under `tests/bdd/features/` has no `scenarios()` binder — this class of defect should never again be discoverable only by hand.
- [ ] `bdd-traceability.yaml` rows for unbound scenarios marked unbound.

---

### T-04 — Blanket harness `pytest.xfail` gates make every storyboard scenario dormant and hide missing steps

**Class:** TEST-INFRA · **Severity:** S1 · **Raised by:** uc002-async, uc002-gov-denied,
uc002-gov-conditions, uc002-measurement, uc002-pending, uc002-inv-nomatch, uc002-inv-targeting,
uc003-creativefate, uc003-mbnotfound, uc003-notcancellable (TM-4), uc003-pkgnotfound,
uc004-vendormetric, uc006-multiformat ([E]), uc006-prov-contradicted, uc018-fmtfilter

**Verified — five imperative catch-all gates in `tests/bdd/conftest.py`:**

```
:3282   pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")
:3359   pytest.xfail("UC-003 harness not yet wired for non-extension scenarios (full graduation pending, PR #1567 follow-up)")
:3378   pytest.xfail("UC-006 harness not yet wired for non-account scenarios")
:3440   pytest.xfail(f"UC-011 harness not yet wired for markers: {marker_names}")
:3507   pytest.xfail(f"UC-004 harness not yet wired for type: {harness_type}")
```

plus a UC-018 gate admitting only `{list-after-sync, concept-id, BR-RULE-034}`.

Each fires at the harness fixture **before any step runs**. Measured examples:
36/36 UC-003 status partition + boundary variants xfail at fixture setup across a2a/mcp/rest;
all 36 UC-006 provenance scenarios XFAIL; every `@T-UC-002-storyboard-*` tag falls through the
UC-002 catch-all.

**Four compounding defects:**

1. **Every `@storyboard-v3.1` scenario in UC-002/003/004/006/018 is dormant.** Rewriting Gherkin changes nothing without a wiring edit — this is why nearly every proposal in this sweep is "correct by construction, unverified by execution."
2. **An imperative `pytest.xfail()` can never xpass**, so nothing signals when production catches up. The ledger is write-only.
3. **A scenario whose steps have no definitions at all is indistinguishable from one that is merely un-wired.** The blanket branch swallows both.
4. **The allowlists are hand-maintained tag sets**, so adding a scenario grades nothing by default. UC-006's is `{"account","creative-invariant","BR-RULE-034"}`.

**Done when**
- [ ] The allowlists are **inverted** — build the env unconditionally and xfail only named exceptions — so a new scenario grades by default.
- [ ] The blanket branch asserts that every step in the scenario resolves before xfailing, so undefined-step scenarios are reported distinctly from un-wired ones.
- [ ] Non-strict xfails replaced with strict where possible, so production catching up shows up as an xpass.
- [ ] The UC-003 "PR #1567 follow-up" graduation actually completed — it is the prerequisite for P-07/P-09/U-03 having any test teeth.

---

### T-05 — `@source` footers: 16 off-by-one, 40 stale refs, 10 absent, and a grammar that cannot express the graded unit

**Class:** TEST-INFRA · **Severity:** S2 · **Raised by:** essentially all 40; explicitly ticketed by
uc002-gov-recovery, uc002-pending, uc003-mbnotfound, uc003-notcancellable (TM-6),
uc004-vendormetric (T7), uc006-prov-corrected (9), uc006-prov-required (T6), uc006-reception (5),
uc014-session, uc018-conceptid

**Four separable defects.**

**5a — systematic off-by-one.** The generator emitted each scenario's footer pointing at the *next*
scenario's storyboard. `storyboard-binding-baseline.md` catches 16 of them mechanically. The UC-002
run is the clearest: `:2649` (governance_denied) cites `governance_denied_recovery.yaml`; `:2664`
cites `inventory_list_no_match.yaml`; `:2680` cites `inventory_list_targeting.yaml`; `:2699` cites
`measurement_terms_rejected.yaml`; `:2714` cites `pending_creatives_to_start.yaml` — a shifted chain
to the end of the block. Same in UC-004 (`:1331`/`:1354` swapped), UC-006 (`:1588`, `:1607`, `:1626`),
UC-003 (`:2078`). **Fix at the generator, not scenario by scenario.**

**5b — every footer is pinned behind our own pin.** All 40 read
`ref=v3.1-04f59d2d5 commit=04f59d2d5`, an ancestor of `v3.1.0-beta.3` and therefore *older* than the
repo's 3.1.1 pin. Re-pin to `v3.1.1` / `467fd93d7`.

**5c — 10 scenarios have no footer at all** (bucket C in the baseline): UC-001 refine, UC-002
pending, UC-003 creative-fate, UC-004 vendor-metric, UC-006 reception, UC-008 platform-dest,
UC-014 session, UC-019 status-poll, UC-020 VAST, UC-021 preview.

**5d — the grammar cannot express the graded unit, which is why 5a went undetected.** The graded unit
is a *step inside a phase* (e.g. `double_cancel` / `second_cancel`), and footers carry only `path=`.
Without `phase=` / `step=`, an off-by-one path swap is invisible to inspection. The sweep's regex
already documents `@source repo=<repo> ref=<ref> [phase=<phase>] path=<path>[#L..]` — the checker
should **require and verify** both.

**5e — a distinct variant in UC-014.** At least six scenarios all carry
`path=static/schemas/source/sponsored-intelligence/si-get-offering-request.json` regardless of which
call they exercise — a single copy-pasted path rather than a shift.

**Also unresolved and worth settling once:** `domains/` vs `protocols/` tier naming. The two trees
are byte-identical at 3.1.1 (multiple proposals confirmed with `diff`), and every proposal cited
`protocols/` because that is the only tier present under `static/compliance/source/` at the tag. If
the repo standardizes on `domains/`, it is a mechanical sweep with identical line numbers.

**Done when**
- [ ] Generator fixed so footers cannot shift.
- [ ] All 40 footers re-pinned to `v3.1.1`, with `phase=` and `step=`.
- [ ] The 10 missing footers added.
- [ ] A lint: the footer's `path=` must name a file that exists at the pinned `ref`, and where a scenario carries a `# <storyboard_id>: …` summary line, the two must name the same storyboard.

---

### T-06 — No BDD step asserts `context` / `context.correlation_id` echo anywhere

**Class:** TEST-INFRA · **Severity:** S2 · **Raised by:** uc002-async, uc002-inv-nomatch,
uc002-measurement, uc002-gov-recovery, uc003-mbnotfound, uc003-notcancellable (TM-3), uc004-delivery,
uc005-roundtrip (C4), uc006-fmtroundtrip (T6), uc006-prov-disclosure (T4), uc006-prov-required (T8),
uc018-fmtfilter, uc019-statuspoll, uc021-preview

**What is missing.** `grep -rn "correlation_id" tests/bdd/steps/` → **zero hits.** The context echo is
graded in essentially every 3.1.1 storyboard, on every phase, on both success and error paths — and
in several cases (`inventory_list_no_match`, `create_media_buy_async`) it is the **only** thing
graded on the step.

Scenarios that *assert* it in Gherkin but have no step definition, so they auto-xfail:
`BR-UC-003:2050,2065,2083`, `BR-UC-007:258,275,283,428,528`, `BR-UC-009:174,175,196,560`,
`BR-UC-011:449,461`, `BR-UC-012:348,364`, `BR-UC-016:712,719`.

**Mandate.** `core/protocol-envelope.json` → `context`: "echoed unchanged in the response … MUST
preserve byte-for-byte." Graded at (non-exhaustive) `create_media_buy_async.yaml:231-237`,
`inventory_list_no_match.yaml:141-148`, `invalid_transitions.yaml:283-289`,
`governance_denied_recovery.yaml:231-234`, `measurement_terms_rejected.yaml:136-142`,
`provenance_enforcement.yaml` (all six phases), `protocols/creative/index.yaml:237-243`,
`protocols/media-buy/index.yaml` `list_formats` + `sync_creatives`.

**One step definition retires a large dormant surface.** It belongs in
`tests/bdd/steps/generic/then_payload.py`, must read the **wire** (`ctx["wire_response"]` /
`result.wire_error_envelope`), and needs a companion Given that puts a `correlation_id` on the
request — several scenarios currently assert an echo they never seeded.

**Prerequisite check.** Confirm per tool whether `context` survives on all four transports before
writing assertions — P-09 (some error raise sites), P-15 (`ListCreativeFormatsBody` has no `context`
field), and T-08 (`build_rest_body` drops it) each break a different tool.

**Done when**
- [ ] One generic Given (`the request carries context correlation_id "<id>"`) and one generic wire-reading Then.
- [ ] Applied to the success, error and submitted branches of at least `create_media_buy`, `update_media_buy`, `sync_creatives`, `list_creatives`, `list_creative_formats`, `get_media_buys`.
- [ ] The dormant scenarios listed above wired onto it.

---

### T-07 — `storyboard_binding_sweep.py` has two false-negative classes and mis-triaged UC-008

**Class:** TEST-INFRA · **Severity:** S2 · **Raised by:** uc002-gov-conditions,
uc003-creativefate, uc008-agentdest

**7a — tier derived from path prefix, so specialism gating is invisible.**
`scripts/audit/storyboard_binding_sweep.py:253` sets `source["tier"]` from the path prefix and only
reports an undeclared-specialism finding when `tier == "specialisms"` (line 266).
`governance_conditions.yaml` lives under `protocols/media-buy/scenarios/` but is required **only** by
`specialisms/governance-aware-seller/index.yaml:23-28`, so the sweep classifies it `protocols` and
reports no gate finding. Same false negative on all four `governance_*` scenarios and on
`governance_aware_seller/governance_multi_agent_rejected`.
**Fix:** resolve the gate by scanning every `index.yaml` `requires_scenarios:` for the scenario's
`id:`, not by path prefix.

**7b — `phase_is_graded()` truncates phase-anchored windows.**
`storyboard_binding_sweep.py:133-148` truncates its window at the next `\n      - id: ` (6-space
step indent). Anchored on a *phase* id (2-space indent), the window stops at the phase's first step
and never reaches `validations:`, so a genuinely graded phase reports `"prose"` → bucket C.
Reproduce with `phase=verify_creative_persists_post_cancel` on
`creative_fate_after_cancellation.yaml`.
**Fix:** indent-aware window, or search to the next sibling id at the same indent level.

**7c — concrete mis-triage.** `docs/test-obligations/storyboard-binding-baseline.md:38-40` marks
`T-UC-008-storyboard-activate-agent-destination` and `T-UC-008-storyboard-baseline-end-to-end` as
bucket **B** ("stale ref only"). Both are bucket **C**: the cited `protocols/signals/index.yaml`
has exactly two phases (`capability_discovery`, `discovery`) and grades no activation at all, and the
real binding sits behind two undeclared gates.

**7d — an open question the sweep cannot answer and should record.** Whether the compliance runner
gates protocol-tier baselines on `supported_protocols` alone, or by specialism as
`src/core/tools/capabilities.py:256-259` asserts (*"The runner gates scenarios by specialism, not by
`supported_protocols` alone"*). Four proposals hit this and none could settle it without runner
source. It flips the verdict on `measurement_terms_rejected` (P-18) and on
`universal/pagination-integrity.yaml` (P-11). Worth resolving upstream once.

**Done when**
- [ ] Gate resolution by `requires_scenarios` membership, not path prefix.
- [ ] Indent-aware `phase_is_graded()`.
- [ ] The baseline regenerated; UC-008 rows move to C.
- [ ] Footer verification requires `phase=`/`step=` (T-05d).

---

### T-08 — Test harness silently drops spec-required fields, masking transport divergence

**Class:** TEST-INFRA · **Severity:** S2 · **Raised by:** uc003-notcancellable (TM-5),
uc003-pkgnotfound, uc018-listall (1), uc019-statuspoll

**Verified — two undeclared allowlists.**

```python
# tests/harness/media_buy_update.py:49-60
_WRAPPER_UNSUPPORTED_FIELDS = (
    "account", "adcp_major_version", "canceled", "cancellation_reason",
    "invoice_recipient", "new_packages", "proposal_id", "revision", "today", "total_budget",
)
```

Popped from the payload before the A2A/MCP wrapper call "so the flat-kwargs call doesn't fail on
unexpected keyword arguments". The REST path (`_build_update_rest_body`) does **not** pop them.
Net effect: the harness makes A2A/MCP look like they accept fields they drop, while REST fails
differently — so **no test can ever observe the real divergence** (P-07, P-26). Every entry is a
field the 3.1.1 request schema declares and our wrappers silently discard.

```python
# tests/harness/creative_list.py:86-98
def build_rest_body(self, **kwargs):
    body = {}
    for key in ("media_buy_id", "media_buy_ids", "status", "format"):
        ...
    filters = kwargs.get("filters")
    ...
```

Whitelists four keys plus `filters`; silently discards everything else, including `context`.
Probed live (uc018-listall): a2a and mcp echo
`{"correlation_id": "creative_lifecycle--list_all"}`; rest returns `context: null`.
**Production is not at fault here** — `src/routes/api_v1.py:456` threads
`context=to_context_object(body.context)` into `list_creatives_raw` and
`listing.py:451` sets `context=req.context`. This is a pure harness defect masquerading as a
production gap, and it is the source of the brief's "REST drops `context`" claim for this tool
(see M-01).

**Done when**
- [ ] `_WRAPPER_UNSUPPORTED_FIELDS` shrinks to empty as P-07/P-26/P-15 land; it is an undeclared allowlist and should be tracked as one (allowlists may only shrink).
- [ ] `build_rest_body` forwards everything, or at minimum `context`, `pagination`, `sort`, `account`.
- [ ] A guard: any harness field-stripping must be declared, justified, and shrinking.

---

### T-09 — UC-006 per-creative error codes are inferred from message substrings, not read off the wire

**Class:** TEST-INFRA · **Severity:** S2 · **Raised by:** uc006-prov-dst (T5)

**What is broken.** `tests/bdd/steps/domain/uc006_sync_creatives.py:2132-2143`
(`_infer_error_code_from_message`) maps message **text** to invented codes
(`CREATIVE_VALIDATION_FAILED`, `CREATIVE_NAME_EMPTY`, …) that are not in the 3.1.1 enum.
`_promote_creative_errors_to_ctx` (`:2100-2129`) feeds that synthetic object to the generic
`the error code should be "{code}"` step, and `_assert_per_creative_failure` (`:1484-1514`)
**xfails** on mismatch.

So every per-creative error assertion in UC-006 asserts a *reconstruction*, and
`creatives[0].errors[0].code` — the field the storyboard actually grades — is never read.

**Mandate.** `tests/CLAUDE.md` § Error Verification Policy: new error-path tests must assert on the
wire envelope; the reconstruction is lossy. `test_architecture_bdd_wire_discipline.py`'s
`_RECONSTRUCTED_ASSERTION_ALLOWLIST` is **empty** — zero tolerance — so this code appears to predate
or evade the guard.

**Concrete proof the reconstruction is lossy:** uc003-mbnotfound measured that the reconstructed
exception object carries `error.context is None` on a2a/mcp/rest while the wire envelope carries
`context.correlation_id` correctly. A reconstructed-object assertion would have declared a production
gap that does not exist.

**Related, same class:** `tests/bdd/steps/generic/then_error.py:270` falls back to the reconstructed
`ctx["error"]` when no wire envelope is present, and `:413-423` (`the error recovery should be …`)
reads the reconstructed object. Both are weaker than they look.

**Done when**
- [ ] `_infer_error_code_from_message` deleted; per-creative assertions read `creatives[0].errors[0].code` off the wire.
- [ ] The invented codes purged.
- [ ] `then_error.py`'s reconstruction fallbacks hardened or removed, and the wire-discipline guard extended to cover UC-006.

---

### T-10 — No harness env can drive two tools in one scenario; every create→read chain is ungraded

**Class:** TEST-INFRA · **Severity:** S3 · **Raised by:** uc003-creativefate, uc004-reqmetrics,
uc004-vendormetric, uc019-statuspoll, uc002-inv-targeting (7.4), uc006-fmtroundtrip

**What is broken.** Each harness env binds one tool (`CreativeListEnv` → `list_creatives`,
`tests/harness/creative_list.py:52-84`). `MediaBuyDualEnv`
(`tests/harness/media_buy_dual.py:88-101`) is the sole exception and sniffs create-vs-update by
request type — both on the media-buy surface. Conftest routing is per-use-case, so **one scenario
gets one env**.

Consequences, each named by a different proposal:

| chain the storyboard grades | why we cannot | proposal |
|---|---|---|
| `create_media_buy` → `get_media_buys` on the returned id (`field_equals_context media_buys[0].media_buy_id == $context.media_buy_id`, `protocols/media-buy/index.yaml:579-582`) | UC-019 binds `MediaBuyListEnv` unconditionally (`conftest.py:3502-3527`); `MediaBuyDualEnv` is create+**update** | uc019-statuspoll |
| create → `get_media_buys` readback of `packages[0].targeting_overlay.property_list.list_id` | `MediaBuyCreateEnv` dispatches create only; the proposed step asserts the DB row instead of the wire readback | uc002-inv-targeting |
| `get_products` (required_metrics) → create → delivery (missing_metrics) | UC-004 routes to `DeliveryPollEnv`; `ProductEnv` reachable only from `UC-GET-PRODUCTS` (`conftest.py:3509-3514`) | uc004-reqmetrics |
| `get_products` vendor_metrics echo → delivery `vendor_metric_values` | same routing wall; needs a one-line `_detect_delivery_harness` change | uc004-vendormetric |
| `get_products` → `sync_creatives` format_id provenance | no env can dispatch a *different* tool over the scenario's transport; UC-005 pays for its workaround with an `e2e_rest` ledger entry | uc006-fmtroundtrip |
| `create → sync_creatives → list_creatives → update(cancel) → list_creatives → create → sync` | a five-phase four-tool walk | uc003-creativefate |

**Also.** UC-018's `list_creatives` steps are module-local (`tests/bdd/test_uc018_list_creatives.py:148,182,199-249,482-517`)
and that module is absent from `pytest_plugins` (`conftest.py:49-71`), so no other feature can reuse
them — the next scenario needing `list_creatives` will copy-paste and trip
`test_architecture_bdd_no_duplicate_steps.py`.

**Done when**
- [ ] A composite env pattern (e.g. `MediaBuyCreateListEnv`) with conftest branches keyed off storyboard tags.
- [ ] Reusable `list_creatives` steps lifted into `tests/bdd/steps/domain/` and registered as a plugin.
- [ ] The create→read assertions currently reaching into the DB re-pointed at the wire.

---

### T-11 — Step-definition defects: duplication, over-broad parsers, mis-attributed assertions, dead code

**Class:** TEST-INFRA · **Severity:** S3 · **Raised by:** uc002-async, uc002-gov-denied,
uc002-gov-conditions, uc002-pending, uc003-mbnotfound, uc006-prov-contradicted (T6,T7),
uc006-prov-corrected (7), uc030-govbinding (E), uc018-listall (7)

Nine small, independently fixable defects. Grouped because each is a one-file change.

1. **`_submitted_wire_dict` duplicates `wire_dict`.** `tests/bdd/steps/domain/uc003_update_media_buy.py:1135-1154`
   is a line-for-line re-implementation of `tests/bdd/steps/_outcome_helpers.py:43-59` — same guard,
   same IMPL fallback, same docstring argument. Delete the UC-003 copy, import the shared helper.
   CLAUDE.md DRY.
2. **`the error details should include {key} {value}` is too loosely parsed.**
   `tests/bdd/steps/generic/then_error.py:760` accepts free prose as `{key} {value}`, which is how
   *"the error details should include the denial reason from the governance decision"* "matched" a
   step at all (`key="the denial reason from the governance"`, `value="decision"`). Any Gherkin
   sentence ending in two words binds to it. Tighten to the quoted-key form (the `:775` variant
   already quotes the value) and re-audit call sites.
3. **`the response should NOT contain "{field}" field` is submitted-envelope-specific but reads
   generic.** `uc003_update_media_buy.py:1197-1221` unconditionally calls
   `_assert_a2a_submitted_task_has_no_artifacts(ctx)` — right for `CreateMediaBuySubmitted`, wrong
   for any synchronous success, so it silently cannot be reused for absence checks on a 200.
   Split into a submitted-envelope variant and a plain wire-absence variant.
4. **`then_dual_emit_media_buy_status` asserts set membership, not values.**
   `uc002_create_media_buy.py:1724-1773` checks `media_buy_status in {MediaBuyStatus values}` and
   `status in {TaskStatus values}` — it would pass on `media_buy_status: "canceled"`. The storyboard
   it cites grades `field_value`. Migrate callers to the value-pinning steps
   (`uc003_update_media_buy.py:127,137`).
5. **`then("the creative should be flagged for review")` mis-attributes its assertion.**
   `uc006_sync_creatives.py:3839-3846` asserts `creative.status == "pending_review"` with the
   docstring *"flagged for review due to missing provenance"*. The status actually comes from
   `approval_mode = require-human` (`_sync.py:126`) and holds identically when provenance is
   **present** (verified on all six accepted claims). It tests the approval-mode default, not
   provenance enforcement.
6. **`given_creative_with_provenance_source_type` is not e2e-safe.**
   `uc006_sync_creatives.py:3684-3700` hard-codes `format_id = "display_300x250"` +
   `env.DEFAULT_AGENT_URL` instead of the e2e-aware `_format_payload(ctx, env)` (`:44-66`), and
   hard-codes `creative_id = "creative-provenance-source-001"`, so two `Scenario Outline` rows
   collide if the DB scope is widened past per-test.
7. **`a creative with provenance metadata` builds a payload `adcp==6.6.0` rejects.**
   `uc006_sync_creatives.py:2707-2717` emits `{"source", "model", "disclosure": <string>}`.
   Executed: `LIBRARY REJECT: ('provenance','disclosure') model_type — Input should be a valid
   dictionary or instance of Disclosure`. `CreativeAsset(**creative_data)` (`_sync.py:158`) raises →
   `except Exception` → `action: "failed"`. **Every scenario using this Given is asserting against a
   failed sync.** Blocked on P-03 for the disclosure half; re-check what those scenarios were
   claiming.
8. **`_make_governance_agent` is dead code that always raises.**
   `tests/bdd/steps/domain/uc011_accounts.py:91-108` constructs
   `GovernanceAgent(url=…, categories=…)`; `GovernanceAgent` has no `categories` field and is
   `extra="forbid"` (verified: `ValidationError … Extra inputs are not permitted`). Its only caller
   (`:862-889`) always passes `categories`, so that `When` can only ever land in `ctx["error"]` —
   and it is referenced by no feature file. Its docstring is also stale. Delete or repair.
9. **The stale xfail at `uc011_accounts.py:2194-2201`** — see P-09's "Done when".

---

### T-12 — UC-019 harness: deprecated MCP wrapper and a `REST_ENDPOINT` pointing at a nonexistent route

**Class:** TEST-INFRA · **Severity:** S3 · **Raised by:** uc019-statuspoll

**12a.** `tests/harness/media_buy_list.py:56-60` uses `_run_mcp_wrapper`
(`tests/harness/_base.py:851-889`), whose own docstring says it *"bypasses FastMCP middleware and
TypeAdapter validation"* and which stashes no `wire_response`. So `ctx["wire_response"]` is `None`
on MCP for **every** UC-019 scenario (~80 Then steps), and every MCP assertion runs against a typed
model whose fields are already coerced. Migrate to `_run_mcp_client`.

**12b.** `tests/harness/media_buy_list.py:26` declares
`REST_ENDPOINT = "/api/v1/media-buys/query"`. `src/routes/api_v1.py` registers only
`POST /media-buys` (302), `PUT /media-buys/{media_buy_id}` (344), `POST /media-buys/delivery` (377).
`conftest.py:2831` works around it via `_NO_REST_UC_TAG_PREFIXES = ("T-UC-019-",)`, excluding UC-019
from `rest` and `e2e_rest` entirely. `get_media_buys` is a **required tool** on the media-buy track
(`protocols/media-buy/index.yaml:6-8`), so one third of our transports never exercise it. Either add
the route or delete the dead constant — but the missing route is itself a conformance question.

---

### S-01 — 19 scenarios claim `@storyboard-v3.1` grading that does not apply to us

**Class:** SCENARIO · **Severity:** S2 · **Raised by:** all 19 RETAG proposals

**What is broken.** Nineteen scenarios carry `@storyboard-v3.1`, which asserts conformance grading
against a 3.1.1 storyboard. For each, either the storyboard is gated behind something we do not
declare, or the specific behaviour is `narrative:`/`expected:` prose with no `validations:` entry —
often both. Per `storyboard-reconciliation.md`, action **RETAG**: `@storyboard-v3.1` →
`@schema-v3.1`, **opaque `@T-…` identifier preserved** (all are referenced from
`docs/test-obligations/bdd-traceability.yaml`, and
`tests/unit/test_architecture_bdd_obligation_sync.py` enforces the mapping bidirectionally).

| scenario | gate that closes |
|---|---|
| `T-UC-001-storyboard-proposal-finalize-action` | `media_buy.supports_proposals` undeclared; graded step is 2 checks that say nothing about the subject |
| `T-UC-001-storyboard-finalize-uses-refine-vocabulary` | same; claim appears only as `sample_request` fixture shape |
| `T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip` | every graded step needs `comply_test_controller`; storyboard self-declares `not_applicable` for non-implementers |
| `T-UC-002-storyboard-governance-approved` / `-with-conditions` / `-denied` / `-denied-recovery` | `governance-aware-seller` specialism + `media_buy.governance_aware` both undeclared |
| `T-UC-002-storyboard-pending-creatives-state-transition` | `media_buy.creative_approval_mode == auto_approve` undeclared |
| `T-UC-006-storyboard-provenance-claim-contradicted` | orphan storyboard (in no `requires_scenarios` anywhere at 3.1.1) + `has_creative_library` undeclared |
| `T-UC-006-storyboard-creative-reception-stateful-render` | `interaction_model: stateful_push` + `has_creative_library`; behaviour is prose anyway |
| `T-UC-008-storyboard-baseline-end-to-end` / `-activate-agent-destination` / `-activate-platform-destination` | `signals` protocol + `signal-marketplace` specialism undeclared; tools registered nowhere |
| `T-UC-014-storyboard-baseline-session-id-roundtrip` | `sponsored_intelligence` protocol undeclared; equality never graded even for an SI agent |
| `T-UC-018-storyboard-filter-by-format-id-object` / `-list-all-creatives-after-sync` / `-filter-by-concept-id` | `creative` protocol undeclared; exclusion semantics ungraded |
| `T-UC-020-storyboard-build-vast-tag-from-synced-creative` | `creative-ad-server` specialism + `creative` protocol + `build_creative` tool all absent |
| `T-UC-021-storyboard-preview-display-from-synced-manifest` | `creative` protocol undeclared; `requires_tool: preview_creative` unsatisfied; assertions are prose |
| `T-UC-030-storyboard-binding-used-during-create-media-buy` | prose-only **and** `governance-aware-seller` undeclared |

**One caveat worth stating plainly.** `@schema-v3.1` vs `@storyboard-v3.1` has **no written
definition anywhere in the repo** — uc020-vast grepped `.py`/`.yaml`/`.md`/`.ini`/`.toml` outside
`.feature` files and found zero consumers; `scripts/audit/storyboard_binding_sweep.py` keys on
`@storyboard-v3.1` and `scripts/compile_bdd.py` on `@T-` and `@schema-v<MAJ>.<MIN>`. The retag is
inferred from usage. Document the vocabulary as part of this change.

**Done when**
- [ ] 19 tags changed, identifiers untouched.
- [ ] The tag vocabulary written down (a doc or a guard, not tribal knowledge).
- [ ] `storyboard_binding_sweep.py` re-run to confirm the 19 leave the storyboard bucket (blocked on T-07).
- [ ] Note: several of these become `@storyboard-v3.1` again if P-13's capability decisions go the other way — record the coupling.

---

### S-02 — Scenarios asserting values production never emits or the spec never defined

**Class:** SCENARIO · **Severity:** S3 · **Raised by:** uc002-async, uc002-gov-recovery,
uc003-notcancellable, uc005-baseline, uc006-fmtroundtrip, uc021-preview, uc030-govbinding

Ten scenario-level defects that will bite the moment their file or gate is wired. Each needs a
decision, not a mechanical fix.

1. **`T-UC-002-partition-approval-workflow` asserts a status production stopped emitting.**
   `_assert_workflow_outcome` (`uc002_create_media_buy.py:1105-1109`) requires
   `status == "pending_approval"`. Since PR #1567 the manual-approval branch returns
   `CreateMediaBuySubmitted` with `status="submitted"` (`media_buy_create.py:1837-1844`), and
   `pending_approval` is **not a member of the 3.1.1 `MediaBuyStatus` enum** — the schema says so at
   `create-media-buy-response.json:220`. Invisible only because of T-04; wiring flips it red.
2. **`@T-UC-002-v31-submitted-envelope-shape` is permanently dormant and duplicates live coverage.**
   `BR-UC-002…feature:1964-1976` uses phrasings that exist nowhere in `tests/bdd/steps/`. Its content
   is a subset of `@T-UC-002-alt-manual`. Retire it or re-point it — do not wire a third copy.
3. **`@T-UC-002-ext-k` asserts `BUDGET_TOO_LOW` where production correctly emits `BUDGET_EXCEEDED`.**
   `feature:357` vs `media_buy_create.py:2605,2621` (`AdCPBudgetExceededError`) and
   `src/core/exceptions.py` (`_default_error_code = "BUDGET_EXCEEDED"`). Both codes exist at 3.1.1;
   `enumMetadata.BUDGET_EXCEEDED.suggestion` matches our message. **The generated feature is stale,
   not production.** Ledgered at `tests/bdd/conftest.py:249-255` awaiting upstream regen — resolve in
   the same pass as this sweep.
4. **`T-UC-003-partition/boundary-media-buy-status` and `T-UC-003-ext-v` already cover the
   re-cancel obligation**, making `T-UC-003-storyboard-not-cancellable-on-recancel` a third copy
   (its own prose claims it is "Distinct from the existing terminal_canceled INVALID_STATE
   scenario" — false as written).
5. **UC-021 siblings contradict the pinned schema.** `:51`/`:71` assert `expires_at` is present —
   3.1.1 marks it **optional** with an explicit "Omit when preview URLs do not expire"; `:49` asserts
   every render has `preview_url` — `preview-render.json` requires it only on the `url` and `both`
   branches, the `html` branch requires `preview_html`; `:52-53` use "the response may include …" as
   Then steps, which cannot assert and will trip `test_architecture_bdd_no_pass_steps.py`.
6. **UC-005 sibling "Discover filtered format catalog" (`~:38`, `~:542`) filters on `type`**, a
   property `media-buy/list-creative-formats-request.json` no longer defines at 3.1.1 (production
   already no-ops it — `when_request.py:186-192`).
7. **`@T-UC-030-bva-url` expects `URL_NOT_HTTPS`** and will fail whenever BR-UC-030 is wired,
   because of P-29b.
8. **Four wired UC-002 `plan_id` scenarios** (`feature:2031,2044,2056,2069`) have zero step
   definitions for any of their four phrasings, so all four are silently auto-xfailed (P-16).
9. **`@T-UC-006-storyboard-format-id-roundtrip-on-sync` and `-creative-reception-stateful-render`
   collide** on the same storyboard file — the former's footer cites
   `creative_reception.yaml`, which is the latter's. Textbook off-by-one (T-05a).
10. **`T-UC-005-storyboard-format-id-third-party-agent-out-of-scope` asserts the runner's grading
    policy, not seller behaviour.** *"the verification result should be reported as an observation
    rather than a graded failure"* is a claim about `on_out_of_scope: warn`. Our seller does not
    implement `refs_resolve`, does not read `on_out_of_scope`, and emits an identical response for
    `warn`/`ignore`/`fail` — **no seller behavior can falsify it.** The step body
    (`uc005_format_id_third_party.py:91-102`) is a generic no-error check plus a verbatim duplicate
    of its sibling's first assertion (`:78-80`). Delete the Then; the gradeable half
    (*"MUST NOT fabricate a local format entry"*) is grounded twice in the schema and is worth
    keeping. Also: every assertion in that scenario is negative, so a seller returning `formats: []`
    for **every** request passes it unchanged — it needs a positive control.

---

### S-03 — `provenance_enforcement` phase 4 (`PROVENANCE_VERIFIER_NOT_ACCEPTED`) has no scenario at all

**Class:** SCENARIO · **Severity:** S3 · **Raised by:** uc006-prov-required (T5),
uc006-prov-corrected (4)

`BR-UC-006-sync-creatives.feature` has scenarios for `provenance_enforcement` phases 2, 3, 5 and 6 —
and **none** for phase 4, `reject_off_list_verifier` (`provenance_enforcement.yaml:277-363`). That is
the phase whose narrative states the seller *"MUST cross-check the URL before any outbound call […]
closing the buyer-controlled-URL trust gap"* — the security-relevant member of the family, entirely
uncovered on both the test side and the production side (P-04).

**Done when**
- [ ] A scenario added (dormant until P-04 lands) with a matching `docs/test-obligations/bdd-traceability.yaml` entry alongside the existing five at `:4807-4835`.

---

### U-01 — Storyboards name error codes that do not exist in `error-code.json`

**Class:** UPSTREAM · **Severity:** S3 · **Raised by:** uc002-inv-nomatch (5)

`dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_no_match.yaml:17` and `:110-112`
tell sellers to reject with **`INSUFFICIENT_INVENTORY`** or **`INVALID_TARGETING`**. Neither exists in
`git show v3.1.1:static/schemas/source/enums/error-code.json` (92 entries; nothing matching `*INVENT*`,
and the only `*TARGET*` entry is `SIGNAL_TARGETING_INCOMPATIBLE`). Still present unchanged at 3.1.8.

This also retroactively explains why our scenario substituted `PRODUCT_UNAVAILABLE`/`INVALID_REQUEST`
— an ungrounded guess, and not what production emits either.

**File at `github.com/adcontextprotocol/adcp`:** either add the codes to the enum or rewrite the prose
to name enum members (`PRODUCT_UNAVAILABLE` is the natural fit). Until then **no local scenario may
assert either code.**

---

### U-02 — Storyboard prose names fields and enum members no 3.1.1 schema defines

**Class:** UPSTREAM · **Severity:** S3 · **Raised by:** uc021-preview, uc006-multiformat ([F]),
uc006-reception, uc008-agentdest

Four instances of the same failure mode: `expected:` prose invents vocabulary, an implementer copies
it into an assertion, and it can never pass.

1. **`protocols/creative/index.yaml:318`** — `- render_dimensions: matches the 300x250 format`.
   No 3.1.1 schema and no `adcp==6.6.0` type defines `render_dimensions`; the real field is
   `dimensions`, nested at `previews[i].renders[j].dimensions`, and optional. Line `:319`'s
   `- status: preview available` is likewise not a member of `enums/task-status.json`.
   **Our scenario was written straight off this prose**, so the trap is live for every implementer.
2. **`protocols/creative/index.yaml:152` and `protocols/media-buy/index.yaml:691`** both write
   *"Per-creative status: `accepted`, `pending_review`, or `rejected`."* `enums/creative-status.json`
   has **no `accepted` member** (`processing, pending_review, approved, suspended, rejected,
   archived`). This is the drift already visible in our own `CreativeStatusEnum` (P-19).
3. **`specialisms/signal-marketplace/index.yaml`** `activate_on_agent` `expected:` (388-394) promises
   `is_live: true` and an `activation_key` with `type: "key_value"` on every agent activation.
   `core/deployment.json` makes `activation_key` optional and conditional — *"Only present if
   is_live=true AND requester has access to this deployment"* — and `core/activation-key.json`
   permits either discriminator. Not a schema obligation and not a graded one.
4. **`protocols/signals/index.yaml:137`** describes the source discriminator as
   *"(agent_native or data_provider)"*; `core/signal-id.json` defines the enum as `catalog | agent`.

**File upstream.** In each case the schema wins locally and the prose binds nothing — but the prose is
what implementers read.

---

### U-03 — `NOT_CANCELLABLE` hard-graded by the storyboard, `MAY` in the schema

**Class:** UPSTREAM · **Severity:** S3 · **Raised by:** uc003-notcancellable (TM-1),
uc003-pkgnotfound

**A genuine storyboard-vs-schema conflict that must be decided upstream before production changes.**

- **Storyboard:** `dist/compliance/3.1.1/…/invalid_transitions.yaml:279-282` grades
  `check: error_code, value: "NOT_CANCELLABLE"` as a **hard pass/fail**. Corroborated by
  `protocols/media-buy/state-machine.yaml:474-495`, which grades the same
  NOT_CANCELLABLE-over-INVALID_STATE precedence.
- **Schema:** `update-media-buy-request.json` `canceled.description` says sellers **MAY** reject with
  `NOT_CANCELLABLE`; `core/error.json` makes `code` an **open string** with
  `enums/error-code.json` explicitly documentary; and `INVALID_STATE`'s own enumDescription names
  this exact situation — *"updating a completed or **canceled** media buy."* Both codes carry
  identical `recovery: "correctable"`, which `error.json` calls the authoritative carrier.

**Our production emits `INVALID_STATE`** (`src/core/tools/media_buy_update.py:412-420` →
`AdCPGoneError`, `_default_error_code = "INVALID_STATE"`, `_default_status_code = 410`,
`_default_recovery = "correctable"`). Verified: `grep -rn "NOT_CANCELLABLE" src/` → **0 hits**.

Under the project's authority order (schema wins) our behaviour is conformant and the conformance
runner still fails us. **Decide upstream first; only then change production.**

Already partly tracked: `T-UC-003-ext-v` strict xfail, `tests/bdd/conftest.py:736-753`, with a FIXME
citing `salesagent-gh8p.13` — **a beads id in a repo file, which CLAUDE.md prohibits; it must be a
GitHub issue number.** Fix that in passing.

A reviewer weighting the storyboard's hard `check:` above the schema's MAY lands on
`NOT_CANCELLABLE` + strict xfail instead — which duplicates `T-UC-003-ext-v`. Both readings are
recorded here deliberately; this is the one item on the slate where the proposals' recommendation is
a judgment, not a derivation.

---

### U-04 — Storyboards grade less than their own schemas require

**Class:** UPSTREAM · **Severity:** S4 · **Raised by:** uc014-session, uc002-inv-nomatch (6),
uc006-prov-disclosure, uc005-thirdparty

Four "the runner cannot catch this" gaps worth proposing `validations:` entries for:

1. **SI session continuity is ungraded.** `protocols/sponsored-intelligence/index.yaml:210-220`
   (`si_send_message`) and `:246-256` (`si_terminate_session`) contain **no `session_id` check of any
   kind**, while `si-send-message-response.json` and `si-terminate-session-response.json` both carry
   `required: ["session_id", …]`. An agent can fabricate a fresh `session_id` per response and pass
   the baseline. Propose `field_value` checks bound to `$context.session_id` on both later steps.
   **Do not patch our local generated `.feature` to assert behaviour the upstream contract does not
   grade — mirror the diff upstream.**
2. **`inventory_list_no_match`'s graded surface is context echo only.** Its narrative describes three
   named failure modes (crash, misleading forecast, silent drop) and grades **none** of them —
   so the scenario's whole point is ungraded.
3. **`provenance_enforcement` phases promise `field` + `recovery: correctable` in prose
   (`:386-388`) and grade neither.**
4. **`list_formats_integrity` internal tension.** `:356-359` states an unconditional MUST that
   explicitly includes the third-party case — resolve it *"whether it hosts that format directly or
   proxies to the creative agent named in `format_ids[0].agent_url`"* — while
   `creative_sync/list_formats` `refs_resolve` (`:655-658`) says third-party refs are unverifiable and
   downgraded to observations. Two checks in two phases pulling opposite directions on the same input.
   Resolution under our authority order: **the 3.1.1 schemas are silent on any obligation to proxy**
   (`list-creative-formats-response.json` never requires resolving foreign references and explicitly
   permits an empty `formats`), so "the seller MUST proxy" is not assertable locally.

---

### U-05 — `ask` semantics under `action: finalize` are undefined at 3.1.1

**Class:** UPSTREAM · **Severity:** S4 · **Raised by:** uc001-refine, uc001-finalize

`v3.1.1 media-buy/get-products-request.json:141` says `ask` is *"Ignored when action is `'omit'`"*
and is **silent on `finalize`**. Our production retains it (executed:
`Refine3(scope='proposal', proposal_id='p', action=Action2.finalize, ask='shift budget')` — accepted
and preserved on round-trip).

A buyer sending `{action: finalize, ask: "…"}` has no defined answer to "was my ask applied before
the commit?" — which matters, because finalize *is* a commit.

Not a salesagent bug. Note also that our sibling scenario
`@T-UC-001-storyboard-finalize-uses-refine-vocabulary` **generalised the `omit` rule to `finalize`**
in both its Then and its comment block ("mirrors the existing INV-10 pattern for omit action") — that
generalisation is in no schema and no storyboard, and it asserts the opposite of observable
behaviour. Fix locally (S-01 covers the retag); raise the ambiguity upstream.

---

### M-01 — The sweep brief's "known production gaps" list is wrong per-tool

**Class:** META (test-infra documentation) · **Severity:** S2 · **Raised by:** uc002-measurement,
uc018-fmtfilter, uc018-listall, uc003-mbnotfound

**Why this is on the slate.** Four independent proposals measured the brief's known-gaps list and
found it false for their tool. Scenario authors write *around* stated gaps, so a wrong gap list
produces weakened scenarios — the opposite of what it is for.

| brief claim | measured reality |
|---|---|
| "No top-level `status` on responses" | **Per tool.** Present on `create_media_buy` (`"completed"`, real REST wire body) and `list_creatives` (a2a/mcp/rest). Absent on `sync_creatives`, `get_media_buys`, `get_media_buy_delivery`, `list_creative_formats`, signals. **Always absent on error envelopes.** (P-01) |
| "REST drops `context`" | **Per tool, and one instance is a harness bug.** REST **does** echo `context` on `create_media_buy`. On `list_creatives` the drop is `tests/harness/creative_list.py::build_rest_body`, not production — `api_v1.py:456` threads it correctly (T-08). On `list_creative_formats` it is genuinely production: `ListCreativeFormatsBody` has no `context` field (P-15). |
| "REST and MCP drop `pagination`" | **False for `list_creatives`.** Measured REST wire top-level keys: `['creatives','pagination','query_summary','replayed','status']`. True for `list_creative_formats` (no `pagination` on the REST body model or the MCP wrapper). |
| "`then_response_schema_valid` runs no validator" | **True of the UC-005 copy, false of the UC-018 copy** (T-01). |
| "`tests/fixtures/adcp_schemas_pinned/` vendored at 04f59d2d5" | **True overall, but not uniformly** — some files already carry 3.1.1-era content (T-02). |
| "`context` not echoed on wire error envelopes" (`uc011_accounts.py:2194`) | **False as a general claim.** Measured present on a2a/mcp/rest for `PACKAGE_NOT_FOUND` and `MEDIA_BUY_NOT_FOUND`. The real limitation is that the *reconstructed* error object carries `context=None` (P-09, T-09). |

**Done when**
- [ ] The known-gaps list is rewritten **per tool and per path (success/error)**, not globally.
- [ ] Each entry states whether it is production or harness.
- [ ] It lives somewhere durable (`docs/test-obligations/`) rather than in a task brief, since it is now the input to every future scenario author.

---

## 3. Mapped to existing issues — comment, do not re-file

### → #1582 (lax pydantic coercion vs JSON-Schema strict types)

Two new instances from the storyboard sweep, both where the generated SDK model drops a JSON-Schema
constraint and our boundary inherits the gap:

> Two more instances found during the AdCP 3.1.1 storyboard re-grounding sweep, both the same shape —
> the codegen'd SDK model silently drops a JSON-Schema constraint, and because we validate through the
> SDK type, the constraint is never enforced at our boundary.
>
> 1. **`required_vendor_metrics` accepts a pinless entry.** `ProductFilters(required_vendor_metrics=[{}])`
>    validates clean under `adcp==6.6.0` (executed). `v3.1.1 core/product-filters.json`
>    `required_vendor_metrics.items` carries `"anyOf": [{"required": ["vendor"]}, {"required": ["metric_id"]}]`
>    — at least one pin is mandatory. The generated model does not enforce the `anyOf`, so a meaningless
>    filter reaches `_get_products_impl` instead of producing `VALIDATION_ERROR`.
>
> 2. **`GovernanceAgent.url` accepts plaintext `http://`.** `core/account.json` and
>    `sync-governance-request.json` both declare `"pattern": "^https://"`. The SDK type is
>    `{"type":"string","format":"uri","minLength":1}` — the pattern is dropped in codegen. Verified:
>    `GovernanceAgent.model_validate({'url':'http://plain.example'})` is accepted and normalises to
>    `http://plain.example/`. That model is our DB column type (`src/core/database/models.py:827-829`)
>    **and** our response type, so we persist and echo plaintext governance endpoints. The BDD scenario
>    `@T-UC-030-bva-url` expects `URL_NOT_HTTPS` and will fail whenever BR-UC-030 is wired.
>
> Both need explicit validators at our boundary — the schema is authoritative and the SDK is a
> cross-check, so neither should wait on an SDK fix. Full context in the consolidated slate as P-22e / P-29b.

### → #1319 (BDD strict-marker debt umbrella)

Three items from the sweep belong here rather than as new issues:

> Three findings from the AdCP 3.1.1 storyboard sweep that are strict-marker debt rather than new defects:
>
> 1. **Imperative `pytest.xfail()` can never xpass.** Five catch-all gates
>    (`tests/bdd/conftest.py:3282`, `:3359`, `:3378`, `:3440`, `:3507`) fire at the harness fixture before
>    any step runs, so nothing signals when production catches up — the ledger is write-only. Measured:
>    36/36 UC-003 status partition + boundary variants xfail at fixture setup; all 36 UC-006 provenance
>    scenarios XFAIL. Converting these to strict where possible is the single change that would have
>    surfaced most of this sweep's findings years earlier.
>
> 2. **A stale xfail asserts a gap that no longer exists.** `tests/bdd/steps/domain/uc011_accounts.py:2194-2201`
>    xfails with *"context not echoed on the wire error envelope — AdCPError carries no context field on
>    a2a/mcp/rest"*. Measured false: `build_two_layer_error_envelope` echoes `exc.context`, and
>    `context.correlation_id` is present on the a2a, mcp and rest error envelopes for `PACKAGE_NOT_FOUND`
>    and `MEDIA_BUY_NOT_FOUND`. The real limitation is narrower — the *reconstructed* `ctx["error"]`
>    object carries `context=None`, and the step reads the object, not the envelope. Re-point it at
>    `result.wire_error_envelope` and retire the xfail.
>
> 3. **`@T-UC-002-ext-k`'s `BUDGET_TOO_LOW` ledger entry (`conftest.py:249-255`) is resolvable now.**
>    Production correctly emits `BUDGET_EXCEEDED` (`media_buy_create.py:2605,2621` → `AdCPBudgetExceededError`);
>    both codes exist at 3.1.1 and `enumMetadata.BUDGET_EXCEEDED.suggestion` matches our message text.
>    The generated feature is stale, not production. Worth clearing in the same pass as the storyboard re-pin.
>
> Also, unrelated to markers but in the same file: the FIXME at `conftest.py:736-753` cites
> `salesagent-gh8p.13`, a beads id — CLAUDE.md requires a GitHub issue number in repo files.

### → #1739 (parallel e2e_rest mock-injection artifacts)

One data point, no new issue:

> One more instance of the in-process-capture-is-invisible-to-Docker pattern, found during the AdCP 3.1.1
> storyboard sweep. UC-005's format-id roundtrip captures the advertised `format_id` from an in-process
> `get_products` call (`tests/bdd/steps/domain/uc005_format_id_roundtrip.py:29-79`), which is exactly why
> `test_format_id_roundtrip__list_creative_formats_returns_the_same_format_object_that_get_products_advertised[e2e_rest]`
> sits on the ledger.
>
> The relevant constraint for anyone writing new format-id scenarios: because the ledger may only shrink,
> the UC-006 sibling proposal deliberately sources the advertised object from `_product_format_entry(ctx, env)`
> — the same `{agent_url, id}` the product is seeded with — rather than from a live `get_products` call.
> Identical value, weaker provenance. Making it a true cross-tool chain needs a harness that can dispatch
> a *different* tool over the scenario's transport, which does not exist today (tracked as T-10 in the
> consolidated slate).

### → #1318, #1726, #1727

**No new material.** Across all 40 proposals nothing touched cross-principal isolation
(#1318), seller attribution defaults (#1726), or push-notification registration acks (#1727).
Recorded so the absence is deliberate rather than an oversight — the sweep's scope was
`@storyboard-v3.1` scenarios only, and none of those three areas carries one.

---

## 4. Dropped — judged not worth filing

| Item | Raised by | Why dropped |
|---|---|---|
| `domains/` vs `protocols/` citation convention | ~30 proposals | The trees are byte-identical at 3.1.1 (multiple `diff` confirmations) and line numbers match. Folded into T-05 as a one-line convention note rather than its own issue. |
| "3.1.8 / HEAD drift not assessed" | all 40 | Explicitly out of scope per the brief; we are pinned at 3.1.1 and not moving. Nothing actionable until a pin bump, at which point it is a bump-procedure concern. |
| `@source` footer with multiple lines / a `phase=` segment may not parse | uc002-gov-conditions, uc014-session | Speculative — the regex is per-line and `binding.sources` is a list, so it should parse. Folded into T-05's "Done when" as a verification step. |
| `@controller-driven` tag now names seeding that no longer uses a controller | uc004-delivery | Tag-vocabulary churn with no correctness consequence; the brief said keep the vocabulary. |
| Examples-row count growth (4 → 24 test instances on some rewrites) | uc005-thirdparty, uc005-baseline | Runtime cost only, bounded, and the alternative (existence-only assertions) is banned by the trivial-assertion guard. |
| Node-id churn from `Scenario` → `Scenario Outline` conversions | uc018-listall, uc003-mbnotfound | Traceability keys on tags, not node ids. Worth a glance at `test_e2e_rest_ledger_state.py` and `scripts/ci/shard_split.py` at edit time, not a ticket. |
| `is_terminal_status("cancelled")` (British spelling) returns `False` | uc003-notcancellable | Real but latent — no code path produces the double-l spelling today. Note it in the cancel implementation (P-07), do not file. |
| `pkg_001` / `prod_1` / `cpm_usd_fixed` fixture coupling in proposed assertions | uc004-delivery, uc004-reqmetrics | Test-authoring guidance for the wiring PRs, not a defect. A shared constant would be better; out of scope for a propose-only pass. |
| Scenario titles no longer matching their opaque `@T-…` slugs after rewrites | uc002-measurement, uc006-prov-corrected, uc030-govbinding | Cosmetic and self-inflicted by the rewrites. `bdd-traceability.yaml` keys on `adcp_scenario_id`, so nothing breaks. Handle at edit time. |
| Renaming `_UC002_MANUAL_APPROVAL_WIRED` | uc002-gov-conditions | Pure naming; subsumed by T-04's allowlist inversion. |
| "`ai-powered` approval mode has no 3.1.1 enum member" as a standalone item | uc002-pending | Genuinely important, but it is a one-line mapping decision inside P-13, not a separate issue. |
| `A2A emits a legacy top-level `success` boolean not in any 3.1.1 schema | uc002-inv-nomatch | Observed (inverted/meaningless on advisory rows) but out of this sweep's scope and likely already known to whoever owns the A2A envelope. Flagged here so it is not lost; file separately if it survives triage. |

---

## 5. Verification notes

### Spot-checked by me, in `/Users/konst/projects/salesagent-sbsweep` — CONFIRMED

Every PRODUCTION issue on the slate rests on at least one of these.

**Zero-hit greps** over `src/ --include='*.py'`, all confirmed **0**:
`PROVENANCE_`, `NOT_CANCELLABLE`, `GOVERNANCE_DENIED`, `plan_id`, `governance_context`,
`comply_test_controller`, `measurement_terms`, `TERMS_REJECTED`, `missing_metrics`, `vendor_metric`,
`required_metrics`, `accepted_verifiers`, `check_governance`, `sync_governance`, `supports_proposals`,
`governance_aware`, `creative_approval_mode`, `has_creative_library`.
(`collection_list` → 12 hits, all type wiring + comments, consistent with P-23.)

**File:line reads confirmed verbatim:**
- `src/core/exceptions.py:1019-1026` — envelope is `{adcp_error, errors, context}`, no `status` (P-01).
- `src/core/tools/creatives/_processing.py:34-56` — `code: str = "SERVICE_UNAVAILABLE"` default (P-14).
- `src/core/tools/creatives/listing.py:376,386-387,443-444` — `format_ids` appears only in `filters_applied` with `str(f)`; `Pagination` built with no cursor (P-08a, P-08e, P-11).
- `src/core/schemas/creative.py:64-79,82-120` — `DigitalSourceType` members and the full hand-rolled `Provenance` field list, `digital_source_type` required (P-03).
- `src/core/schemas/_base.py:2089-2102` — `has_updatable_fields()` tuple, `canceled` absent (P-07).
- `src/core/schemas/_base.py:2458-2471` — `ActivateSignalResponse`, no `deployments`, docstring points 3 and 4 (P-20).
- `src/core/schemas/_base.py:2721` — `GetMediaBuysMediaBuy` full field list, no `confirmed_at`/`revision`/`context`; `GetMediaBuysRequest` docstring cites "adcp 3.6.0" (P-10).
- `src/core/schemas/delivery.py:159-201` — `PackageDelivery(SalesAgentBaseModel)`, docstring *"Does not yet extend library ByPackageItem"*, `pricing_model`/`rate`/`currency` optional (P-06).
- `src/core/tools/media_buy_delivery.py:343,521,523,549,675` — clicks discarded, `clicks = 0`, `ctr` derived, `daily_breakdown=None`, `currency="USD"` + TODO (P-17, P-25a).
- `src/core/tools/media_buy_create.py:1841,3561,4102` — `errors=property_list_unsupported_advisories(...)` into `sync_success` (P-02).
- `src/core/tools/capabilities.py` — `MediaBuyFeatures` 3 flags; `MediaBuy(portfolio, features, execution)`; `supported_protocols=[media_buy]`; `specialisms=[sales_non_guaranteed]`; the stale comment block (P-13).
- `src/core/tools/products.py` — no `required_metrics` / `required_vendor_metrics` (P-08c, P-08d).
- `src/routes/api_v1.py` — `model_dump(mode="json")` with no `exclude_none` at **10** call sites: `:237,245,258,273,341,374,400,428,459,471` (P-11).
- `tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-108` — asserts only `isinstance(formats, list)`; `tests/bdd/test_uc018_list_creatives.py:216-220` calls `validate_against_pinned_schema` (T-01).
- `tests/helpers/pinned_schema.py:5-6` — pinned at `04f59d2d5`; `tests/fixtures/adcp_schemas_pinned/` has 64 error codes (vs 92), **no** `core/activation-key.json`, **no** `sponsored-intelligence/` (T-02).
- `tests/harness/media_buy_update.py:49-60` — `_WRAPPER_UNSUPPORTED_FIELDS` 10 entries verbatim (T-08).
- `tests/harness/creative_list.py:86-98` — `build_rest_body` whitelists 4 keys + `filters`, drops `context` (T-08, M-01).
- `tests/bdd/conftest.py:3282,3359,3378,3440,3507` — the five catch-all `pytest.xfail` gates (T-04). Note: 1–3 line drift from several proposals' citations, because the working tree carries concurrent sibling edits.

**Independently derived, stronger than any single proposal:**
**21 unbound feature files** (T-03) — computed by diffing every `BR-UC-*.feature` against every
`scenarios("features/…")` call in `tests/bdd/*.py`. Individual proposals named six; the real count is
21, roughly 600 scenarios.

### Taken on trust — not re-verified by me

- **Every 3.1.1 spec quotation.** All `git show v3.1.1:static/schemas/source/…` and `dist/compliance/3.1.1/…` citations, line numbers and prose come from the proposals. They are mutually corroborating (e.g. the `protocol-envelope.json` `required: ["status"]` clause is quoted verbatim and identically by 15 independent proposals, the `creative-policy.json` MUST-enforce clause by 5), which is good evidence but is not the same as my having opened the spec repo. **I did not open `/Users/konst/projects/adcp` at all.**
- **Executed measurements reported by proposals.** The wire-body captures (uc002-inv-nomatch's 18 combinations, uc002-measurement's 3-transport REST body, uc018-fmtfilter's 3-transport filter probe, uc018-listall's 3-transport `Draft7Validator` run at 0 errors, uc004-delivery's 4 validator errors, uc006-multiformat's 3-creative probe, uc006-prov-corrected's model-rejection probe, uc004-vendormetric's `ProductEnv` runs). I confirmed the *source-code* facts these rest on; I re-ran none of the probes.
- **Line numbers inside `dist/compliance/3.1.1/**/*.yaml`.** Several proposals note their line numbers come from the on-disk working tree rather than `git show v3.1.1:`. Schema quotations are `git show`-sourced and safer; storyboard line numbers should be re-confirmed at edit time.
- **`adcp==6.6.0` SDK introspection claims** (`MediaBuyFeatures` field set, `CreativePolicy.model_fields`, `GovernanceAgent` `extra="forbid"`, `canonicalize_target_uri` behaviour). Reported as executed by the proposals; I did not import the SDK.
- **Which proposals ran green vs argued from source.** The majority state plainly they were not executed — the harness dormancy (T-04) made execution impossible for most. `uc003-mbnotfound`, `uc002-measurement`, `uc002-inv-nomatch`, `uc004-vendormetric`, `uc018-fmtfilter`, `uc018-listall` and `uc006-multiformat` ran real probes; the rest did not. Weight their green claims accordingly.

### Where proposals disagree — both readings recorded

1. **P-09, `context` on error envelopes.** uc002-inv-nomatch measured it **absent** on all three transports for the property-targeting rejection; uc003-mbnotfound and uc003-pkgnotfound measured it **present** on all three for not-found errors. Both are right — it is per raise-site, not class-wide. Recorded as such; the fix is a raise-site audit, not a single patch.
2. **U-03, `NOT_CANCELLABLE` vs `INVALID_STATE`.** The storyboard hard-grades one, the schema permits the other. Recorded as an upstream conflict with both readings and their consequences.
3. **P-18 / P-11, protocol-tier gating.** Whether the runner gates protocol baselines by `supported_protocols` or by specialism (as `capabilities.py:256-259` asserts) is unresolved and flips two verdicts. Recorded in T-07d as a question to settle upstream once.
4. **P-13, `has_creative_library`.** uc003-creativefate ruled `@storyboard-v3.1` justified because we *have* a real library and merely fail to advertise it; uc006-reception and uc018-* ruled the opposite. The proposals themselves flag it as a judgment call. Recorded, not adjudicated.
5. **T-02, fixture staleness.** Most proposals treat the pinned tree as uniformly `04f59d2d5`; uc004-vendormetric found several files already carrying 3.1.1-era content. Recorded — check per file.

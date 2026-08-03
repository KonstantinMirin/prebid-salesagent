# SB-5c — draft issues / sharpen notes for the 49-item storyboard-conformance slate

**Status: NOT POSTED.** Nothing in this file has been filed or commented via `gh`. Every block
below is drafted for a human to review and post with `gh issue create` / `gh issue edit` /
`gh issue comment` as appropriate.

Source slate: `.claude/notes/storyboard-conformance/CONSOLIDATED-ISSUES.md` (49 items: P-01..P-29,
T-01..T-12, S-01..S-03, U-01..U-05). `M-01` is a 50th, bonus item from the same file (a documentation
fix, not itself a defect) — drafted at the end for completeness even though it falls outside the
ticket's "49."

All PRODUCTION / TEST-INFRA / SCENARIO drafts target **prebid/salesagent** and should be filed under
milestone **Storyboard Compliance (#2)** — apply the milestone via the `gh issue create --milestone`
flag shown below; this file does not create or assign the milestone. All UPSTREAM drafts target
**adcontextprotocol/adcp** — that repo has no "Storyboard Compliance" milestone, so those drafts carry
no milestone flag; where useful a short companion tracking issue in prebid/salesagent is drafted
alongside so the upstream dependency is visible on our own board.

Every draft states its evidence was gathered on branch `test/storyboard-binding-baseline` in
prebid/salesagent.

No new label is proposed anywhere in this file (owner decision per the ticket).

---

## 0. Disposition summary

**Methodology note.** Every disposition below was checked against real GitHub state — `gh issue
view` on all candidate matches, plus `gh issue list --search` sweeps across every item's key terms —
not just inferred from the source slate's own text. This surfaced several corrections to the
slate's original SHARPEN-target guesses (notably T-04, P-09, U-03) and, more importantly, **13
additional exact-or-close matches the slate's authors had not identified**, mostly against older
(AdCP 3.0.x-era) issues from a prior gap-analysis pass (`#1247` and its children) that are still
open and describe the identical gap this fresh 3.1.1 sweep re-confirms. Items marked NEW below were
searched with multiple keyword variants and no matching open issue was found; absence of a hit is
not proof none exists, but this is a materially more rigorous check than the slate alone provided.

| # | Item | Disposition |
|---|---|---|
| P-01 | No top-level `status` on responses | NEW (related: closed #1304, open #1305 — see notes) |
| P-02 | Success envelope carries `errors` | NEW |
| P-03 | `Provenance`/`DigitalSourceType` hand-rolled | SHARPEN #1074 |
| P-04 | `provenance_requirements`/`accepted_verifiers` unread | NEW (depends on P-03/#1074) |
| P-05 | `sync_governance` unimplemented | **SHARPEN #1325** (exact match) |
| P-06 | Delivery models don't extend library type | NEW |
| P-07 | No cancellation path in `update_media_buy` | **SHARPEN #1261** (exact match) |
| P-08 | Request filters silently ignored (5 instances) | NEW |
| P-09 | `context` echo missing, raise-site-dependent | NEW (stale-xfail sub-part → SHARPEN #1797) |
| P-10 | `get_media_buys` omits `confirmed_at`/`revision` | NEW |
| P-11 | `pagination.cursor` never emitted | NEW |
| P-12 | Format identity compared on `id` alone | NEW (adjacent: #1768, closed #1409) |
| P-13 | `get_adcp_capabilities` under-declares flags | NEW |
| P-14 | Per-creative failures emit `SERVICE_UNAVAILABLE` | NEW |
| P-15 | REST body models drop spec-required fields | NEW (related: #1761, #1442) |
| P-16 | `plan_id`/`governance_context` dropped | NEW |
| P-17 | Delivery emits wrong numbers (`clicks`, `ctr`, `currency`) | NEW |
| P-18 | `measurement_terms` dropped; no `TERMS_REJECTED` | NEW |
| P-19 | `SyncCreativeResult.status` never populated | NEW |
| P-20 | Signals surface non-conformant, unregistered | SPLIT: SHARPEN #1783 (sub-3), SHARPEN #1353 (sub-6), related #1593 (sub-1/2), NEW (sub-4/5) |
| P-21 | Provenance policy resolved tenant-wide | NEW |
| P-22 | Proposal/refine lifecycle absent | **SHARPEN #1272** (exact match) |
| P-23 | `collection_list` zero validation/declaration | **SHARPEN #1446** (exact match) |
| P-24 | `error.field` index-less, transport-dependent | NEW |
| P-25 | `include_package_daily_breakdown` ignored; `viewability` scalar | SPLIT: SHARPEN #1776 (part a), NEW (part b) |
| P-26 | `update_media_buy` doesn't enforce `idempotency_key` | **SHARPEN #1470** (exact match, answers open question) |
| P-27 | No `preview_creative`/`build_creative` tool | NEW (context: closed #998 — gap re-surfaced or never finished) |
| P-28 | `pending_creatives → pending_start` missing | SHARPEN #1305 (claimed closed by its invariant 6; measured still open) |
| P-29 | `GovernanceAgent` auth/URL validation gaps | NEW (+ 29b SHARPEN #1582, with caveat — see §1) |
| T-01 | `then_response_schema_valid` runs no validator | NEW (related: #1778, #1773) |
| T-02 | Pinned schema fixtures behind spec pin | SPLIT: SHARPEN #1753 (error-code angle), NEW (broader schema staleness) |
| T-03 | 21 feature files unbound (~600 scenarios) | SPLIT: SHARPEN #1594 (4 files, worse than described), NEW (17 files) |
| T-04 | Blanket harness `pytest.xfail` gates | **SHARPEN #1740** (corrected from slate's #1319 guess) |
| T-05 | `@source` footer defects | NEW |
| T-06 | No step asserts `context` echo | NEW |
| T-07 | `storyboard_binding_sweep.py` false negatives | NEW |
| T-08 | Harness silently drops spec-required fields | NEW |
| T-09 | UC-006 error codes inferred from message text | SHARPEN #1590 (corrected — tighter fit than staying NEW) |
| T-10 | No harness env drives two tools in one scenario | NEW (+ footnote feeds SHARPEN #1739) |
| T-11 | Step-definition defect grab-bag (9 items) | NEW |
| T-12 | UC-019 harness: deprecated wrapper, dead REST const | NEW |
| S-01 | 19 scenarios mis-tagged `@storyboard-v3.1` | NEW |
| S-02 | Scenarios asserting values never emitted/defined | NEW (+ item 3 feeds SHARPEN #1319 via doc entry) |
| S-03 | `provenance_enforcement` phase 4 has no scenario | NEW |
| U-01 | Storyboard names error codes not in enum | NEW (upstream: adcontextprotocol/adcp) |
| U-02 | Storyboard prose names undefined fields/enums | NEW (upstream: adcontextprotocol/adcp) |
| U-03 | `NOT_CANCELLABLE` storyboard vs `MAY` schema conflict | NEW (upstream: adcontextprotocol/adcp; beads-id cleanup → SHARPEN #1767, corrected from slate's #1319 guess) |
| U-04 | Storyboards grade less than their own schemas require | NEW (upstream: adcontextprotocol/adcp) |
| U-05 | `ask` semantics under `action: finalize` undefined | NEW (upstream: adcontextprotocol/adcp) |
| — | (bonus) M-01 — sweep brief's known-gaps list is wrong | NEW (internal docs fix) |
| — | #1582 | SHARPEN (comment only, fed by P-29b — caveat in §1) |
| — | #1319 | SHARPEN (one doc-entry addition, fed by S-02 item 3 only — corrected scope) |
| — | #1739 | SHARPEN (comment only, fed by T-10 footnote) |
| — | #1318, #1726, #1727 | No action — confirmed no new material (see §5) |

**Count against the ticket's "49" (29 P + 12 T + 3 S + 5 U):**

- **Whole-item SHARPEN (primary disposition targets an existing issue directly):** P-03, P-05, P-07,
  P-22, P-23, P-26, P-28, T-04, T-09 = **9 items**.
- **Split items (part SHARPEN, part NEW):** P-20, P-25, T-02, T-03 = **4 items**, each counted once
  above under its dominant sub-part's issue number in the table but genuinely mixed — see each
  item's section for the exact split.
- **NEW (no existing open issue found covering the specific finding, after live search):** the
  remaining **36 items** (P-01, P-02, P-04, P-06, P-08, P-09, P-10, P-11, P-12, P-13, P-14, P-15,
  P-16, P-17, P-18, P-19, P-21, P-24, P-29, T-01, T-05, T-06, T-07, T-08, T-10, T-11, T-12, S-01,
  S-02, S-03, U-01, U-02, U-03, U-04, U-05, plus the P-25/T-02/T-03 NEW sub-parts already counted
  above as split items — not double-counted in the 36).
- Net: roughly **9 clean SHARPEN, 4 split, 36 clean NEW** out of 49; plus 3 more existing issues
  (#1582, #1319, #1739) sharpened via small comments fed by sub-parts of otherwise-NEW items, and 3
  existing issues (#1318, #1726, #1727) confirmed to need no action.

---

## 1. Known existing issues — read and evaluated

### #1739 — "10 parallel e2e_rest entries are mock-injection artifacts, not genuine gaps — realize the setup or declare E2EUnsupportedSetup"

**Read via `gh issue view 1739 --repo prebid/salesagent`.** Real title confirmed as above. Existing
issue tracks the general pattern: in-process test capture (mocks/monkeypatches) is invisible to the
Dockerized e2e_rest runner, producing ledger entries that look like production gaps but are
test-capture artifacts (three named injection surfaces: UC-004 `set_adapter_response`, UC-005
`set_registry_formats`, UC-018 injected cross-principal creatives).

**What it's missing that our sweep found:** one more concrete instance — UC-005's format-id
roundtrip captures the advertised `format_id` from an in-process `get_products` call
(`tests/bdd/steps/domain/uc005_format_id_roundtrip.py:29-79`), which is exactly why
`test_format_id_roundtrip__list_creative_formats_returns_the_same_format_object_that_get_products_advertised[e2e_rest]`
sits on the ledger. This is a data point for the existing pattern, not a new pattern — **do not
file a new issue**, comment instead.

**Disposition: SHARPEN #1739.**

**Comment to add (`gh issue comment 1739 --repo prebid/salesagent --body-file ...`):**

```
One more instance of the in-process-capture-is-invisible-to-Docker pattern, found during an AdCP
3.1.1 storyboard re-grounding sweep on branch `test/storyboard-binding-baseline`.

UC-005's format-id roundtrip captures the advertised `format_id` from an in-process `get_products`
call (`tests/bdd/steps/domain/uc005_format_id_roundtrip.py:29-79`), which is exactly why
`test_format_id_roundtrip__list_creative_formats_returns_the_same_format_object_that_get_products_advertised[e2e_rest]`
sits on the ledger.

Relevant constraint for anyone writing new format-id scenarios: because the ledger may only shrink,
a UC-006 sibling scenario deliberately sources the advertised object from a fixture helper (the same
`{agent_url, id}` the product is seeded with) rather than from a live `get_products` call —
identical value, weaker provenance. Making it a true cross-tool chain needs a harness that can
dispatch a *different* tool over the scenario's transport, which does not exist today (tracked as a
separate test-infra gap — no harness env can drive two tools in one BDD scenario).
```

---

### #1582 — Numeric-string coercion diverges from AdCP JSON-schema strict types (update revision wrong-type partition)

**Read via `gh issue view 1582 --repo prebid/salesagent`.** Real title/scope, verified: the issue is
specifically about `update-media-buy-request.json`'s `revision` field (`type: integer`) — production
runs Pydantic in lax mode at every transport boundary, so a numeric *string* like `"7"` coerces to
`7` instead of being rejected, and the generated conformance partition (`T-UC-003-partition-revision`,
`wrong_type` row) expects `INVALID_REQUEST`. The issue body itself generalizes: "This affects any
integer/number field, not just `revision`" and references a sibling "divergence ledger" issue (#1564,
prose/schema optionality).

**Important caveat before filing anything here.** The two new findings below are the *same root-cause
class* as #1582 (our validation is looser than the JSON-Schema the spec defines) but a **different
mechanism**: #1582 is about Pydantic's lax numeric-string coercion in our own wire request models;
the two new findings are about the **generated SDK type** silently dropping an `anyOf` combinator and
a `pattern` constraint respectively — codegen gaps, not coercion-mode gaps. They belong to the same
family in spirit (and the issue's closing reference to a "divergence ledger" suggests the maintainer
already thinks of this as a family, not a single narrow bug), but a maintainer skimming #1582's title
("update revision wrong-type partition") could reasonably prefer these filed separately, or against
#1564 instead. **Recommend the human reviewer make the call** — comment on #1582 as drafted below, or
split finding 2 (GovernanceAgent) into its own new issue, since it is not about type coercion at all.

**What #1582 is missing that our sweep found:** two new concrete instances of the broader family it
already gestures at.

**Disposition: SHARPEN #1582** (with the caveat above flagged to the reviewer).

**Comment to add (`gh issue comment 1582 --repo prebid/salesagent --body-file ...`):**

```
Two more instances found during an AdCP 3.1.1 storyboard re-grounding sweep on branch
`test/storyboard-binding-baseline`, both the same shape as this issue — the codegen'd SDK model
silently drops a JSON-Schema constraint, and because we validate through the SDK type, the
constraint is never enforced at our boundary.

1. `required_vendor_metrics` accepts a pinless entry. `ProductFilters(required_vendor_metrics=[{}])`
   validates clean under `adcp==6.6.0` (executed). `v3.1.1 core/product-filters.json`
   `required_vendor_metrics.items` carries
   `"anyOf": [{"required": ["vendor"]}, {"required": ["metric_id"]}]` — at least one pin is
   mandatory. The generated model does not enforce the `anyOf`, so a meaningless filter reaches
   `_get_products_impl` instead of producing `VALIDATION_ERROR`.

2. `GovernanceAgent.url` accepts plaintext `http://`. `core/account.json` and
   `sync-governance-request.json` both declare `"pattern": "^https://"`. The SDK type is
   `{"type":"string","format":"uri","minLength":1}` — the pattern is dropped in codegen. Verified:
   `GovernanceAgent.model_validate({'url':'http://plain.example'})` is accepted and normalises to
   `http://plain.example/`. That model is our DB column type
   (`src/core/database/models.py:827-829`) **and** our response type, so we persist and echo
   plaintext governance endpoints. The BDD scenario `@T-UC-030-bva-url` expects `URL_NOT_HTTPS` and
   will fail whenever `BR-UC-030-manage-governance-binding.feature` is wired up (that feature file
   currently has no `scenarios()` binding at all).

Both need explicit validators at our boundary — the schema is authoritative and the SDK is a
cross-check, so neither should wait on an SDK fix. Full context in the storyboard-conformance slate,
`.claude/notes/storyboard-conformance/CONSOLIDATED-ISSUES.md`.
```

---

### #1319 — BDD strict-marker debt umbrella

**Read via `gh issue view 1319 --repo prebid/salesagent`.** Real scope, verified: #1319 is the
tracking issue for the **16 non-security items catalogued in
`docs/test-debt-bdd-strict-markers.md`** (the doc, not the issue body, is the canonical source of
truth — items C4–C11, B1–B7, H1–H2; the three security-tier items from the same audit, C1–C3, are
filed separately as #1316/#1317/#1318). The lifecycle is: fix the gap → flip the `conftest.py`
marker to `strict=True` → remove the FIXME → **delete the entry from the doc** → check the box on
#1319.

**Verified against the doc directly (read in full, 386 lines):** none of the three findings below —
the five blanket `pytest.xfail()` catch-all gates, the stale `uc011_accounts.py:2194` xfail, or the
`@T-UC-002-ext-k` `BUDGET_TOO_LOW` ledger entry — appear anywhere in
`docs/test-debt-bdd-strict-markers.md`. They are genuinely new material, not duplicates of an
existing C/B/H item. They are, however, the *same class* of debt the doc exists to catalogue
(non-strict xfail markers hiding scenario dormancy), so the correct sharpen action is **not just a
GitHub comment** — it is adding new lettered entries (continuing the C/B/H scheme, e.g. a new
section for the five blanket harness-gate items) to the doc itself, per the doc's own stated
lifecycle, with a comment on #1319 pointing at the new entries.

**Disposition: SHARPEN #1319** (via a doc update, not comment-only) — this is the slate's T-04 item,
plus contributions from P-09, S-02, and U-03.

**Comment to add to #1740 (`gh issue comment 1740 --repo prebid/salesagent --body-file ...`):**

```
Concrete additional instance of the pattern this issue already names, found during an AdCP 3.1.1
storyboard re-grounding sweep on branch test/storyboard-binding-baseline.

Five blanket `pytest.xfail()` gates in tests/bdd/conftest.py (:3282, :3359, :3378, :3440, :3507; plus
a UC-018 allowlist admitting only {list-after-sync, concept-id, BR-RULE-034}) fire at the harness
fixture *before any step runs*, gating entire scenario collections rather than individual rows:

    :3282   pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")
    :3359   pytest.xfail("UC-003 harness not yet wired for non-extension scenarios (full graduation pending, PR #1567 follow-up)")
    :3378   pytest.xfail("UC-006 harness not yet wired for non-account scenarios")
    :3440   pytest.xfail(f"UC-011 harness not yet wired for markers: {marker_names}")
    :3507   pytest.xfail(f"UC-004 harness not yet wired for type: {harness_type}")

Measured: 36/36 UC-003 status-partition + boundary variants xfail at fixture setup across
a2a/mcp/rest; all 36 UC-006 provenance scenarios XFAIL. Every @T-UC-002-storyboard-*,
@T-UC-003-storyboard-*, @T-UC-004-storyboard-*, @T-UC-006-storyboard-* and
@T-UC-018-storyboard-* scenario in the AdCP 3.1.1 conformance suite is dormant because of this —
plausibly the single highest-value instance of the "unenumerable local-variable registry" pattern
this issue already describes, since it blocks an entire conformance-grading track rather than a
handful of partition rows.

Concrete remediation shape for this instance: invert the allowlists (build the harness env
unconditionally, xfail only named exceptions) so a new scenario grades by default; make the blanket
branch assert every step resolves before xfailing, so a scenario with zero step definitions reports
distinctly from one that is merely un-wired.
```

**Separately: `docs/test-debt-bdd-strict-markers.md` addition, tracked via #1319**

One narrower finding from the same sweep genuinely belongs in the #1319 doc (verified: the doc's 386
lines, read in full, do not contain this item today) rather than #1740, since it's a specific stale
scenario-expectation, the exact shape #1319's C/B/H items already catalogue:

```markdown
### <next free ID> — `@T-UC-002-ext-k`'s `BUDGET_TOO_LOW` ledger entry is resolvable now
- **Scope:** `@T-UC-002-ext-k` (`BR-UC-002-create-media-buy.feature:357`)
- **Where:** `tests/bdd/conftest.py:249-255` (ledger entry); production emits `BUDGET_EXCEEDED` at
  `src/core/tools/media_buy_create.py:2605,2621` (`AdCPBudgetExceededError`)
- **Impact:** The generated feature asserts `BUDGET_TOO_LOW`; production correctly emits
  `BUDGET_EXCEEDED`. Both codes exist at 3.1.1 and `enumMetadata.BUDGET_EXCEEDED.suggestion` matches
  our message text verbatim — the generated feature is stale, not production.
- **Unblocks:** Update the generated feature's expected code to `BUDGET_EXCEEDED` and clear the
  ledger entry in the same pass as the storyboard re-pin work.
- **Severity:** P3 (stale generated scenario)
- **Origin:** AdCP 3.1.1 storyboard re-grounding sweep
```

with a short comment on #1319 pointing at the new doc entry.

**On the stale xfail at `uc011_accounts.py:2194` and the beads-id FIXME:** these are handled under
P-09 and U-03 below, respectively, each pointing at a better-fitting existing issue (#1797 and #1767)
found on direct verification — see those sections rather than duplicating here.

---

### #1318 — "bug(repo): cross-principal media_buy access returns 200+empty instead of 403 [P1 security]"

**Read via `gh issue view 1318 --repo prebid/salesagent`.** Confirmed: this is item C3 from
`docs/test-debt-bdd-strict-markers.md`, filed separately from #1319 because it's security-tier.
Tracks cross-principal data isolation — `MediaBuyRepository.get_by_principal` filters silently by
`principal_id`, so a foreign principal gets an empty list instead of a 403/404.

**What the sweep found:** nothing. All 40 source proposals in this sweep were scoped to
`@storyboard-v3.1` scenarios; none of them touched cross-principal isolation.

**Disposition: No action.** Recorded here so the absence is a deliberate finding, not an oversight.
Do not comment — there is no new material to add.

---

### #1726 — "UC-004: seller attribution default not implemented — production echoes the buyer's requested window (BR-092)"

**Read via `gh issue view 1726 --repo prebid/salesagent`.** Confirmed: tracks a genuine, already
known production gap (seller doesn't apply its own `attribution_window` default) surfaced from
`e2e_rest_known_failures.txt` Wave 3 triage, unrelated to this sweep's `@storyboard-v3.1` scope.

**What the sweep found:** nothing, for the same scoping reason as #1318.

**Disposition: No action.**

---

### #1727 — "UC-011: push_notification_config webhook registration acknowledgement not implemented"

**Read via `gh issue view 1727 --repo prebid/salesagent`.** Confirmed: tracks a genuine, already
known production gap (no ack on push-notification registration), also surfaced from the same Wave 3
triage.

**What the sweep found:** nothing, for the same scoping reason as #1318.

**Disposition: No action.**

---

## 2. PRODUCTION items (P-01 .. P-29)

Target prebid/salesagent for all. Several are SHARPEN, not NEW — see each item's own disposition
line (P-03, P-05, P-07, P-22, P-23, P-26, P-28 are whole-item SHARPEN; P-20 and P-25 are split).

Each draft below assumes:
```
gh issue create --repo prebid/salesagent \
  --title "<Title>" \
  --milestone "Storyboard Compliance" \
  --body-file <path-to-body>
```

### P-01 — Response envelopes carry no top-level `status`; the error envelope never can

**Disposition: NEW** — searched broadly, no existing issue found asserting this specific,
cross-tool, top-level `status` gap. **Related context worth citing in the issue, not a duplicate:**
`#1304` (closed) built the current `build_two_layer_error_envelope` two-layer serializer this
finding's error-envelope evidence points at — it completed the error-emission architecture but did
not add a `status` key, so this is a fresh gap in code #1304 shipped, not a reopening of it. `#1305`
(open) covers a related but distinct envelope-shape problem (async/submitted `Response3` shape,
`task_id` population) — worth sequencing together since both touch "what shape does this tool's
envelope have," but neither covers the universal top-level `status` omission across
`sync_creatives`/`get_media_buys`/`get_media_buy_delivery`/`list_creative_formats`/signals this
finding names.

**Title:** `Response envelopes carry no top-level "status" — mandatory at AdCP 3.1.1`

**Body:**
```
## What is broken

`build_two_layer_error_envelope` emits exactly `{adcp_error, errors, context}` — there is no
`status` key on any error response, on any transport.

    src/core/exceptions.py:1019-1026
        envelope: dict[str, Any] = {
            "adcp_error": dict(payload["errors"][0]),
            "errors": payload["errors"],
        }
        serialized_context = _serialize_context(exc.context)
        if serialized_context is not None:
            envelope["context"] = serialized_context
        return envelope

On the success side the gap is per response model, not universal:

| Tool | top-level `status` on success | evidence |
|---|---|---|
| `create_media_buy` | present (`completed`) | real REST wire body |
| `list_creatives` | present (`completed`) | a2a+mcp+rest |
| `sync_creatives` | **absent** — dumped keys `['creatives','dry_run']` | executed probe |
| `get_media_buys` | **absent** — `GetMediaBuysResponse` declares `media_buys, errors, context` only | code inspection |
| `get_media_buy_delivery` | **absent** — `Draft7Validator` error `[] -> 'status' is a required property` | executed |
| `list_creative_formats` | **absent** — `src/core/schemas/creative.py:547-549` says protocol fields are "added by the protocol layer" | code inspection |
| `get_signals` / `activate_signal` | **absent** | code inspection |

## Spec mandate (3.1.1)

`git show v3.1.1:static/schemas/source/core/protocol-envelope.json`:

> "required": ["status"] … "The `status` field is REQUIRED on every task response envelope …
> Agents shipping responses without a top-level `status` are non-conformant regardless of whether
> the task body schema would otherwise validate."

Composed via `allOf` into `create-media-buy-response.json`, `update-media-buy-response.json`,
`get-media-buys-response.json`, `get-media-buy-delivery-response.json`,
`sync-creatives-response.json`, `list-creatives-response.json`,
`list-creative-formats-response.json`, `activate-signal-response.json`,
`preview-creative-response.json`, `build-creative-response.json`, `sync-governance-response.json`.

## Blocked BDD scenarios

Every `- check: response_schema` step in the 3.1.1 storyboard tree — the single most-graded check.
Named explicitly: `T-UC-003-storyboard-media-buy-not-found`,
`T-UC-003-storyboard-package-not-found`,
`T-UC-004-storyboard-controller-driven-delivery-schema-compliance`,
`T-UC-004-storyboard-required-metrics-end-to-end-accountability`,
`T-UC-005-storyboard-format-id-roundtrip-from-products`,
`T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-creative-reception-stateful-render`,
the four `T-UC-006-storyboard-provenance-*` scenarios, `T-UC-019-storyboard-post-create-status-poll`.

## Acceptance criteria

- [ ] `build_two_layer_error_envelope` emits `status` (the `TaskStatus` for the failure arm) on all
      four transports.
- [ ] The six response models above carry a top-level `status`, or the protocol layer stamps it
      uniformly.
- [ ] A single BDD step asserts `status` on the wire for both success and error paths, wired into at
      least one scenario per tool.
- [ ] Test-obligations docs record which tools were already conformant (`create_media_buy`,
      `list_creatives`) so nobody re-derives it.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-02 — `create_media_buy` / `update_media_buy` success envelope carries `errors`, which 3.1.1 forbids

**Title:** `create_media_buy/update_media_buy success envelope carries "errors" — forbidden by 3.1.1 schema`

**Body:**
```
## What is broken

Production attaches `UNSUPPORTED_FEATURE` advisories to the **success** envelope whenever a package
carries `property_list`:

    src/core/tools/media_buy_create.py:1841   errors=property_list_unsupported_advisories(req.packages, adapter)
    src/core/tools/media_buy_create.py:3561   errors=property_list_unsupported_advisories(req.packages, adapter)
    src/core/tools/media_buy_create.py:4102   errors=property_list_unsupported_advisories(req.packages, adapter)
    src/core/tools/media_buy_update.py:566,591,743,1398   same pattern

The rationale comment at `src/services/targeting_capabilities.py:174-180` cites AdCP 3.0.0
`error-handling.mdx` ("non-fatal errors … MUST NOT populate `adcp_error`", i.e. advisories ride the
success envelope). 3.1.1 supersedes that for this response shape.

## Spec mandate (3.1.1)

`v3.1.1:static/schemas/source/media-buy/create-media-buy-response.json` → `oneOf` →
`CreateMediaBuySuccess` carries `"not": {"required": ["errors"]}`. Only the
`CreateMediaBuySubmitted` branch permits `errors` ("Optional advisory errors accompanying the
submitted envelope"). A response with `media_buy_id` + `packages` + `errors` matches **zero**
branches. Same defect on `update-media-buy-response.json`.

Graded at `dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_targeting.yaml`, step
`create_buy_with_lists`, `- check: response_schema`.

Note the coupling: the advisory fires on exactly the request the `inventory_list_targeting`
storyboard sends, and `supports_property_list_filtering()` is universally `False` today (no adapter
sets the ClassVar), so it fires on every `property_list` request.

## Blocked BDD scenarios

`T-UC-002-storyboard-inventory-list-targeting-parity`, `T-UC-002-storyboard-inventory-list-no-match`.

## Acceptance criteria

- [ ] The advisory rides somewhere the success branch permits, or is dropped for the success arm.
- [ ] The 3.0.0 citation at `targeting_capabilities.py:174-180` is replaced with the 3.1.1 decision.
- [ ] Fixed on `update_media_buy` in the same change (four call sites).
- [ ] A scenario grades that a success response validates against exactly one `oneOf` branch.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-03 — `Provenance` and `DigitalSourceType` are hand-rolled and reject spec-legal 3.1.1 submissions

**Disposition: SHARPEN existing #1074** — corrected after direct verification
(`gh issue view 1074 --repo prebid/salesagent`, full body read). #1074, "feat: Add AI provenance
support to creative policy," is the origin issue for this exact subsystem — it proposed the
`Provenance`/`DigitalSourceType`/`CreativePolicy.provenance_required` shape the current (buggy) code
appears to have been built from. It is **pinned to AdCP v3.0.0-rc1** and its own field list and
9-value `DigitalSourceType` enum are themselves now stale relative to 3.1.1 (different field set,
different enum members than either the current code or the 3.1.1 schema). It is still open. **Do not
file a new issue — comment on #1074 with the 3.1.1 re-grounding.**

**What #1074 is missing that this sweep adds:** (1) the current field-by-field diff against the real
3.1.1 `core/provenance.json` (the issue's own proposed shape is a *third*, older shape — neither what
shipped nor what 3.1.1 requires); (2) the corrected `DigitalSourceType` 3.1.1 membership (the issue's
9 IPTC values are not the 3.1.1 enum either); (3) executed proof the current implementation rejects a
spec-legal 3.1.1 submission outright (reproduced on mcp/a2a/rest); (4) the practical EU AI Act Art. 50
stake this issue itself raised — the correct, most-used disclosure value
(`trained_algorithmic_media`) is rejected today; (5) branch `test/storyboard-binding-baseline`
citation.

**Comment to add (`gh issue comment 1074 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment, re-grounded at 3.1.1):**

**Title (unused if commenting on #1074; keep for reference only):** `Provenance/DigitalSourceType schemas are hand-rolled, not extended from the library — rejects spec-legal 3.1.1 payloads`

**Body:**
```
## What is broken

`src/core/schemas/creative.py:82` declares `class Provenance(SalesAgentBaseModel)` — not an
extension of the library type — under `extra="forbid"`. Verified field-by-field against
`v3.1.1:static/schemas/source/core/provenance.json`:

| field | 3.1.1 schema | ours (creative.py:82-120) |
|---|---|---|
| `digital_source_type` | optional (no `required` array) | **required** (`Field(...)`) |
| `disclosure` | object, `required: ["required"]` | `str \| None` |
| `declared_by` | object, `required: ["role"]` | `str \| None` |
| `human_oversight` | string enum | `bool \| None` |
| `c2pa` | object `{manifest_url}` | `str \| None` |
| `verification` | array | `dict \| None` |
| `embedded_provenance` | array, `minItems: 1` | **absent** |
| `watermarks`, `declared_at`, `ext` | present | **absent** |

`DigitalSourceType` (`creative.py:64-79`) invents three members that do not exist at 3.1.1 —
`composite_with_trained_model`, `trained_algorithmic_model`, `minor_human_edits` — and is missing
three that do: `trained_algorithmic_media`, `composite_with_trained_algorithmic_media`,
`data_driven_media`.

Reproduced by execution, calling the real `_validate_creative_input` with a 3.1.1-shaped provenance
object:

    LOCAL Creative REJECTED — errors:
       ('provenance','digital_source_type') | enum            | Input should be 'digital_capture', …
       ('provenance','declared_by')         | string_type     | Input should be a valid string
       ('provenance','disclosure')          | string_type     | Input should be a valid string
       ('provenance','embedded_provenance') | extra_forbidden | Extra inputs are not permitted

`src/core/tools/creatives/_sync.py`'s `except Exception` turns that into a per-creative
`action: "failed"` carrying a raw pydantic message — the exact inverse of the graded
`creatives[0].action ∈ ["created","updated"]`.

## Spec mandate (3.1.1)

`v3.1.1:static/schemas/source/core/provenance.json`,
`v3.1.1:static/schemas/source/enums/digital-source-type.json`. Practical stake: an EU AI Act Art. 50
workflow submitting the correct, most-used disclosure value `trained_algorithmic_media` is
**rejected today** (reproduced on mcp, a2a and rest).

## Blocked BDD scenarios

All four `T-UC-006-storyboard-provenance-*`, plus
`T-UC-006-storyboard-provenance-claim-contradicted`, and structurally the entire
`provenance_enforcement.yaml` storyboard (its phase 4/5/6 payloads cannot be parsed by us).

## Acceptance criteria

- [ ] `Provenance` extends the library type; the seven local redeclarations are deleted.
- [ ] `DigitalSourceType` is the SDK enum, not a local `StrEnum`.
- [ ] A test outline over the full 3.1.1 enum accepts every member.
- [ ] The storyboard's own phase-4/5/6 sample_request payloads parse.
- [ ] Land before the dependent provenance-enforcement issue (provenance_requirements /
      accepted_verifiers never read).

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-04 — `provenance_requirements` / `accepted_verifiers` never read; four graded `PROVENANCE_*` codes unreachable

**Disposition: NEW, but closely related to #1074** (see P-03 above). #1074's own implementation plan
step 2 ("Creative validation... If required and missing → reject with `correctable` error or flag
for review") is exactly the behavior this finding shows was never built — the current code only ever
warns, never rejects, and reads none of `require_digital_source_type`,
`require_disclosure_metadata`, `require_embedded_provenance`, or `accepted_verifiers`. Recommend
filing this as a new issue (it is a large, separately-scoped piece of work — four distinct error
codes, a verifier allowlist, a security-relevant pre-call check) but explicitly linking it from the
#1074 comment as "the enforcement half of this issue, tracked separately," so the two don't get
implemented in isolation and re-diverge.

**Title:** `provenance_requirements and accepted_verifiers are dead config — four PROVENANCE_* error codes unreachable`

**Body:**
```
## What is broken

`grep -rn "PROVENANCE_\|accepted_verifiers" src/ --include='*.py'` → **0 hits each.** The entire
provenance surface is one advisory:

    src/core/tools/creatives/_validation.py:144-175  check_provenance_required(...)
        → returns early with None as soon as creative.provenance is not None
        → otherwise returns a warning *string*
    src/core/tools/creatives/_sync.py:180-184, 275-278, 328-330
        → appends the string to result.warnings, leaves action at created/updated
    src/core/database/repositories/creative.py:263-273  get_provenance_policies()
        → filters on creative_policy["provenance_required"] only; never reads provenance_requirements

So `require_digital_source_type`, `require_disclosure_metadata`, `require_embedded_provenance` and
`accepted_verifiers` are dead config.

## Spec mandate (3.1.1)

`v3.1.1:static/schemas/source/core/creative-policy.json`:

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

The emission plumbing already exists: `_failed_sync_result(creative_id, msg, code=…, recovery=…)`
(`src/core/tools/creatives/_processing.py:34-59`) produces exactly the graded shape —
`action: "failed"`, `errors[0].code`, `recovery`, no `status`. The work is gate logic at the
`check_provenance_required` call site, plus turning a warning into a per-item failure.

Note the precise trigger for disclosure: a missing `disclosure.required` **flag**, not a missing
`disclosure` object.

## Blocked BDD scenarios

`T-UC-006-storyboard-provenance-required-rejection`, `…-digital-source-type-missing`,
`…-disclosure-missing`, `…-corrected-acceptance`, plus a currently-missing phase-4 scenario (see
separate SCENARIO item on `provenance_enforcement` phase 4).

## Acceptance criteria

- [ ] Depends on: `Provenance`/`DigitalSourceType` extending the library types (spec-shaped payloads
      must parse before policy can run).
- [ ] All four `PROVENANCE_*` codes emitted with `error.field` pointing at the inspected path.
- [ ] `action: "failed"` items omit `status` per the schema's
      `if action in [failed,deleted] then not status`.
- [ ] `accepted_verifiers` canonicalized-matched **before** any outbound call.
- [ ] The four dormant scenarios wired and green.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-05 — `sync_governance` is unimplemented and it is a `required_tools` entry of the specialism we declare

**Disposition: SHARPEN existing #1325** — corrected after direct verification
(`gh issue view 1325 --repo prebid/salesagent`). #1325, "feat(governance): implement sync_governance
tool | storyboard phase 3 (4.3 gap)," is an exact, open, unclaimed match: it already documents that
the tool doesn't exist anywhere in `src/`, cites the same "required tool for the media-buy protocol"
mandate, and lays out an acceptance contract (MCP/A2A/REST wrappers, `_impl` pattern, boundary
translators, contract test, capability declaration). **Do not file a new issue.**

**What #1325 is missing that this sweep adds:** (1) the specific S1-tier framing — this outranks
other governance gaps because it's a `required_tools` entry of `sales-non-guaranteed`, a specialism
we already declare, so it isn't gated behind an undeclared specialism the way the rest of the
governance surface is; (2) the dependency on the separate `GovernanceAgent` request-model gap (rejects
`authentication`, accepts plaintext `http://`) that must land first for a spec-shaped registration to
be acceptable at all; (3) the concrete blocked-scenario count (`BR-UC-030-manage-governance-binding.feature`,
45 scenarios, 582 lines, itself currently unbound); (4) branch `test/storyboard-binding-baseline`
citation. #1325 is pinned generically to "the media_buy_seller storyboard" without a spec version —
worth re-confirming against the 3.1.1 schema files cited below (`sync-governance-{request,response}.json`)
since the repo has moved pins since this issue was filed.

**Comment to add (`gh issue comment 1325 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment):**
```
## Why this outranks other governance gaps

Every other governance gap sits behind `governance-aware-seller`, a specialism we do not claim —
those grade `not_applicable`. `sync_governance` does not.
`dist/compliance/3.1.1/specialisms/sales-non-guaranteed/index.yaml:9` lists it under
`required_tools` for the specialism `src/core/tools/capabilities.py:100` **does** declare, and
`:292-304` grades `accounts[0].status == "synced"` plus `response_schema` against
`account/sync-governance-response.json`. We fail that step outright.

## What is broken

`src/core/main.py:351-352` registers `list_accounts` and `sync_accounts` only. Verified:
`grep -rn "sync_governance\|check_governance" src/ --include='*.py'` → **0 hits each**.
`governance_agents` exists purely as a persisted passthrough JSON column
(`src/core/database/models.py:827-829`) written through `sync_accounts`
(`src/core/tools/accounts.py:586,629`) and read back through `list_accounts` (`:70`).

## Spec mandate (3.1.1)

Request `v3.1.1:static/schemas/source/account/sync-governance-request.json`
(`required: [idempotency_key, accounts]`); response `…/sync-governance-response.json` (`oneOf`
success/error; success `required: [accounts]`; per-account `required: [account, status]`,
`status ∈ {synced, failed}`).

## Blocked BDD scenarios

The whole of `BR-UC-030-manage-governance-binding.feature` (45 scenarios, 582 lines) is authored
against this tool — and is itself unbound (no `scenarios()` call).

## Acceptance criteria

- [ ] `sync_governance` `_impl` + MCP/A2A/REST wrappers + a harness env.
- [ ] Response echoes the persisted agent in `accounts[].governance_agents`.
- [ ] The `GovernanceAgent` request-model gap (rejects `authentication`, accepts plaintext `http://`)
      is resolved so a spec-shaped registration is accepted at all.
- [ ] `BR-UC-030` bound with at least the registration half green.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-06 — Delivery models don't extend the library type; `by_package[]` omits three REQUIRED fields

**Title:** `PackageDelivery/DeliveryTotals don't extend the library delivery-metrics type — by_package[] missing pricing_model/rate/currency`

**Body:**
```
## What is broken

`src/core/schemas/delivery.py:159` — `class PackageDelivery(SalesAgentBaseModel)` with a closed
field list; its own docstring at `:162` concedes "Does not yet extend library ByPackageItem."
`DeliveryTotals` has the same defect. Consequences:

1. `pricing_model`, `rate`, `currency` are declared optional (`delivery.py:173-185`) and are set from
   `MediaPackage.package_config["pricing_info"]`, left `None` when the key is absent
   (`src/core/tools/media_buy_delivery.py:487-497`). `AdCPBaseModel` drops `None`, so they vanish
   from the wire entirely.
2. `vendor_metric_values`, `missing_metrics` and `committed_metrics` cannot be represented at all.

A `Draft7Validator` run against the real 3.1.1 schema, executed against a faithful production
response, returns exactly four errors:

    ERR []                                           -> 'status' is a required property
    ERR ['media_buy_deliveries',0,'by_package',0]    -> 'pricing_model' is a required property
    ERR ['media_buy_deliveries',0,'by_package',0]    -> 'rate' is a required property
    ERR ['media_buy_deliveries',0,'by_package',0]    -> 'currency' is a required property

## Spec mandate (3.1.1)

`v3.1.1:static/schemas/source/media-buy/get-media-buy-delivery-response.json` →
`media_buy_deliveries.items.by_package.items.allOf[1].required =
["package_id","spend","pricing_model","rate","currency"]`, with
`allOf[0] = {$ref: core/delivery-metrics.json}` — which is where `vendor_metric_values` lives.

Graded at `delivery_reporting.yaml:228` (`response_schema`) and
`vendor_metric_accountability.yaml:279-293` (five `field_present` checks).

## Blocked BDD scenarios

`T-UC-004-storyboard-controller-driven-delivery-schema-compliance`,
`…-required-metrics-end-to-end-accountability`, `…-vendor-metric-end-to-end`, plus 12 other dormant
UC-004 vendor/missing-metrics scenarios that unblock in one move.

## Acceptance criteria

- [ ] `PackageDelivery`/`DeliveryTotals` extend the library `delivery-metrics` types.
- [ ] `pricing_model`/`rate`/`currency` derived from the buy's pricing option when
      `package_config` has no `pricing_info`, and made required.
- [ ] `vendor_metric_values` emitted, de-duplicated per `(vendor.domain, vendor.brand_id, metric_id)`
      per period — a schema MUST the storyboard leaves as prose.
- [ ] `by_package[].missing_metrics` emitted (needs `package.committed_metrics` as the reconciliation
      source, or the documented fallback to `reporting_capabilities.available_metrics`).

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-07 — `update_media_buy` implements no cancellation; `canceled` is unreachable on every transport

**Disposition: SHARPEN existing #1261** — corrected after direct verification
(`gh issue view 1261 --repo prebid/salesagent`). #1261, "feat: implement media buy cancellation on
update_media_buy for adcp 3.0.6," is an exact match, still open: "salesagent silently ignores
canceled and cancellation_reason on update_media_buy. No code path — MCP, A2A, REST, repository,
adapter, scheduler — transitions a media buy to AdCP's terminal canceled state." **Do not file a new
issue.**

**What #1261 is missing that this sweep adds:** (1) it is pinned to "adcp 3.0.6" in its title — this
sweep re-confirms the exact same gap is still live at the 3.1.1 pin, with fresh file:line evidence
(`_base.py:2089-2102`, `media_buy_update.py:1425-1518,1506`, `api_v1.py:96-117`) and the precise
3.1.1 schema clause (`canceled: {type: boolean, const: true}`, `cancellation_reason: {maxLength:
500}`); (2) the transport-divergence detail — REST rejects the body outright under `extra="forbid"`
while A2A/MCP silently drop the fields, so the three transports fail differently for the same
request; (3) the harness masking — the test harness's `_WRAPPER_UNSUPPORTED_FIELDS` allowlist strips
`canceled`/`cancellation_reason` before the A2A/MCP wrapper call, so no test today can observe the
real divergence (tracked separately); (4) the coupling to a genuine upstream question (does a
re-cancel get `NOT_CANCELLABLE` or `INVALID_STATE`?) that should be resolved before picking the
rejection code; (5) branch `test/storyboard-binding-baseline` citation.

**Comment to add (`gh issue comment 1261 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment):**
```
## What is broken

`has_updatable_fields()` omits `canceled` and `cancellation_reason`:

    src/core/schemas/_base.py:2089-2102
        return any(f is not None for f in (
            self.paused, self.start_time, self.end_time, self.packages, self.budget,
            self.push_notification_config, self.reporting_webhook, self.context, self.ext,
        ))

So `{media_buy_id, account, idempotency_key, canceled: true}` — a complete, valid 3.1.1 cancel —
trips the BR-RULE-022 empty-update gate at `src/core/tools/media_buy_update.py:1506` and returns
`INVALID_REQUEST`, **before** the terminal-state check at `:412`. Additionally:

- `_build_update_request` (`media_buy_update.py:1425-1518`) has no `canceled` parameter; the field is
  never read anywhere in the 1673-line module.
- `src/routes/api_v1.py:96-117` `UpdateMediaBuyBody` declares no `canceled`; production is
  `extra="forbid"` outside test/dev, so **REST rejects the body with a different error than
  A2A/MCP** — a transport-boundary divergence (project Pattern #5).

## Spec mandate (3.1.1)

`v3.1.1:static/schemas/source/media-buy/update-media-buy-request.json` declares
`canceled: {type: boolean, const: true}` and `cancellation_reason: {type: string, maxLength: 500}`
("Sellers SHOULD store this and return it in subsequent get_media_buys responses"), with
`required: ["idempotency_key","account","media_buy_id"]`. `adcp==6.6.0`'s `UpdateMediaBuyRequest`
carries both. Sent on the wire at `invalid_transitions.yaml:237-247,268-278`.

## Blast radius

No cancel flow is reachable through any AdCP transport today.

## Blocked BDD scenarios

`T-UC-003-storyboard-not-cancellable-on-recancel`,
`T-UC-003-storyboard-creative-fate-after-cancellation`, `T-UC-003-ext-v`.

## Acceptance criteria

- [ ] `canceled` + `cancellation_reason` added to `has_updatable_fields()`, `_build_update_request`,
      the MCP wrapper, `update_media_buy_raw`, and `UpdateMediaBuyBody`.
- [ ] Cancellation releases package-creative assignments (`CreativeAssignment` has a plain FK with no
      `ondelete` and no application-level release).
- [ ] The harness's `_WRAPPER_UNSUPPORTED_FIELDS` allowlist shrinks by two entries.
- [ ] Resolve the `NOT_CANCELLABLE` vs `INVALID_STATE` upstream question before choosing the
      rejection code for a re-cancel (separate upstream item).

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-08 — Request filters accepted and silently ignored (five instances, one defect class)

**Title:** `Five request filters accepted and silently ignored — filter-not-fail MUSTs satisfied vacuously`

**Body:**
```
## What is broken

One defect class, five instances. Every one is a "filter-not-fail" MUST that we satisfy vacuously
by never filtering.

**a. `list_creatives` ignores `filters.format_ids`.** In `src/core/tools/creatives/listing.py` the
only occurrence of `format_ids` is the `filters_applied` string at `:386-387`. The repository's
`format=` argument is fed only by the out-of-band flat `format` string. Measured on a2a/mcp/rest (3
seeded creatives, 1 matching): filter returned **all three**, `query_summary.total_matching: 3`.
Mandate: `v3.1.1 core/creative-filters.json` → `format_ids`: "Filter by structured format IDs.
Returns creatives that match any of these formats."

**b. `list_creatives` ignores `filters.creative_ids`** (and `tags_any`, `accounts`, `unassigned`,
`assigned_to_packages`). `CreativeRepository.get_by_principal`
(`src/core/database/repositories/creative.py:99-115`) has no `creative_ids` parameter. Mandate:
`v3.1.1 core/creative-filters.json` `creative_ids` (`minItems: 1`, `maxItems: 100`).

**c. `get_products` ignores `filters.required_metrics`.** `grep required_metrics src/` → 0 hits.
`src/core/tools/products.py:460-606` filters on `delivery_type`, `is_fixed_price`, `format_ids`,
`standard_formats_only`, `countries`, `channels`, `device_types` only. Mandate:
`v3.1.1 core/product-filters.json:474` — "Sellers MUST silently exclude products that cannot meet
this list (filter-not-fail; do not return an error)."

**d. `get_products` ignores `filters.required_vendor_metrics`.** Same code path, verified 0 hits.
Executed proof: tenant with `vm_capable` (declares `attentionvendor.example`) + `vm_incapable`
(declares none), filter `[{"vendor":{"domain":"attentionvendor.example"}}]` → returns
`['vm_capable','vm_incapable']`.

**e. `query_summary.filters_applied` reports unapplied filters and leaks a Pydantic repr.**
`listing.py:386-387` — measured wire value:

    "format_ids=agent_url=AnyUrl('https://creative.adcontextprotocol.org/') id='display_300x250' width=None height=None duration_ms=None"

Mandate: `v3.1.1 creative/list-creatives-response.json` defines `query_summary.filters_applied` as
"List of filters that were applied to the query" with `items: {type: string}`.

Also missing: `get_products` never emits `filter_exclusions.excluded_by`
(`v3.1.1 media-buy/get-products-response.json:238-249`, which names `required_metrics` as an example
key), so buyers cannot distinguish a metric-driven exclusion from an empty catalogue.

## Blocked BDD scenarios

`T-UC-018-storyboard-filter-by-format-id-object`,
`T-UC-003-storyboard-creative-fate-after-cancellation`,
`T-UC-004-storyboard-required-metrics-end-to-end-accountability`,
`T-UC-004-storyboard-vendor-metric-end-to-end`.

## Acceptance criteria

- [ ] All five filters push into the query (c and d are the same missing filter loop — fix in one
      change).
- [ ] `filters_applied` reports only filters actually applied, formatted from object fields, never
      `str(model)`.
- [ ] `filter_exclusions.excluded_by` emitted.
- [ ] Format identity comparison rule (separate item on `format_id` canonicalization) lands first.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-09 — `context` echo missing on some error envelopes (raise-site-dependent)

**Title:** `context echo on error envelopes is raise-site-dependent — some AdCPError raise sites omit context=`

**Body:**
```
## What is broken

`build_two_layer_error_envelope` (`src/core/exceptions.py:1023-1025`) **does** echo `exc.context`
when it is set. So the gap is per raise-site, not class-wide:

| raise site | `context=` passed? | measured |
|---|---|---|
| `src/core/database/repositories/media_buy.py:192-209` (`AdCPPackageNotFoundError`) | yes | `context.correlation_id` present on a2a/mcp/rest |
| `get_by_id_or_raise` on the update path | yes | present on all three |
| `src/core/tools/media_buy_update.py:413-420` (terminal-state) | **no** — passes `field=`/`suggestion=` but not `context=`, while `_verify_principal(…, context=req.context)` ten lines earlier at `:403` does | inconsistent within one function |
| `src/services/targeting_capabilities.py:315-330` (`raise_if_property_targeting_violations`) | **no** | wire error envelope keys were `{adcp_error, errors}` only, all three transports |

## Spec mandate (3.1.1)

`v3.1.1 core/protocol-envelope.json` → `context`: "echoed unchanged in the response … MUST preserve
byte-for-byte." `create-media-buy-response.json` `CreateMediaBuyError.context`: "Sellers MUST echo
this object verbatim when the originating request carried context, including synchronous success,
error, submitted, and webhook task-status payloads." `universal/error-compliance.yaml` (universal
tier — always applies): "Every error response must include the caller's context object unchanged."
Graded on essentially every error step: `inventory_list_no_match.yaml:141-148`,
`invalid_transitions.yaml:283-289`, `governance_denied_recovery.yaml:231-234`,
`provenance_enforcement.yaml:137-140/204-207/272-275/360-363/433-436/514-517`.

## Blocked BDD scenarios

`T-UC-002-storyboard-inventory-list-no-match`, `T-UC-003-storyboard-not-cancellable-on-recancel`,
and the error half of every UC-006 provenance scenario.

## Acceptance criteria

- [ ] Every `raise AdCP*Error` in `src/core/tools/` and `src/services/` audited for a missing
      `context=req.context`; a guard or a shared raise helper prevents regressions.
- [ ] A BDD step actually asserts the echo on the wire (there is none today, see the companion
      test-infra item), so this is actually graded.
- [ ] The stale xfail at `tests/bdd/steps/domain/uc011_accounts.py:2194-2201` retired — it claims
      "context not echoed on the wire error envelope", which is false as a general claim (measured
      present). The real limitation is that the *reconstructed* `ctx["error"]` object carries
      `context=None`; the step reads the object, not the envelope. Re-point it at
      `result.wire_error_envelope`.

## Companion action — SHARPEN #1797, not #1319

On direct verification (`gh issue view 1797 --repo prebid/salesagent`), the retirement of the stale
`uc011_accounts.py:2194` xfail belongs as a comment on **#1797** ("in-step `pytest.xfail()` is an
unreviewable third xfail mechanism — 16 unconditional, 108 guarded, all in `@then`"), not #1319.
#1797 is scoped exactly to `pytest.xfail()` calls inside `tests/bdd/steps/**/*.py` step bodies — this
xfail's location — and its own body already gives a structurally identical example (a wrong xfail
*reason* text citing a rule that doesn't exist, at `uc006_sync_creatives.py:3552`). Suggested comment
for #1797:

```
Another instance of the pattern this issue already catalogues (in-step pytest.xfail() with a reason
that turns out to be false), found during an AdCP 3.1.1 storyboard re-grounding sweep on branch
test/storyboard-binding-baseline.

tests/bdd/steps/domain/uc011_accounts.py:2194-2201 xfails with "context not echoed on the wire error
envelope — AdCPError carries no context field on a2a/mcp/rest". Measured false: build_two_layer_error_envelope
(src/core/exceptions.py:1023-1025) echoes exc.context, and context.correlation_id is present on the
a2a, mcp and rest error envelopes for PACKAGE_NOT_FOUND and MEDIA_BUY_NOT_FOUND (verified by direct
wire inspection). The real, narrower limitation: the step reads the harness's *reconstructed*
ctx["error"] object, which carries context=None, not the wire envelope. Re-point it at
result.wire_error_envelope and retire the xfail.
```

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-10 — `get_media_buys` items omit `confirmed_at` and `revision`, both REQUIRED at 3.1.1

**Title:** `get_media_buys items omit confirmed_at and revision — both REQUIRED at 3.1.1, revision needed for conflict-safe updates`

**Body:**
```
## What is broken

    src/core/schemas/_base.py:2721
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

No `confirmed_at`, no `revision`, no per-buy `context`. `src/core/tools/media_buy_list.py:270-283`
never sets any of them.

## Spec mandate (3.1.1)

`git show v3.1.1:static/schemas/source/media-buy/get-media-buys-response.json` lists `confirmed_at`
(type `["string","null"]`) and `revision` (`{"type":"integer","minimum":1}`) in the
`media_buys[].required` array. The schema further couples `confirmed_at`: an item with
`confirmed_at: null` MUST NOT carry `status: "active"` (the `allOf` provisional-buy guard) — so
emitting it changes what `active` is allowed to mean. `revision` is the optimistic-concurrency token
`update_media_buy` consumes; without it a buyer cannot construct a conflict-safe update from a read.

Per-buy `context`: "Sellers MUST include persisted context on read surfaces when the media buy was
created through AdCP with context, so buyers can reconcile seller-assigned media_buy_id values with
their own tracking state." Graded at `protocols/media-buy/index.yaml:583-585`
(`field_value media_buys[0].context.correlation_id`). Needs a create-side persist as well as a
read-side emit.

Note: `media_buy_status` does **not** exist on `get-media-buys-response.json` at 3.1.1 — do not add
it here.

## Blocked BDD scenarios

`T-UC-019-storyboard-post-create-status-poll` (`response_schema` +
`media_buys[0].context.correlation_id`).

## Acceptance criteria

- [ ] `confirmed_at`, `revision`, per-buy `context` emitted; `GetMediaBuysRequest`/`Response` extend
      the library types (their docstrings currently cite a spec version matching neither the SDK pin
      nor the spec pin — fix that too).
- [ ] The provisional-buy `allOf` guard honoured.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-11 — `pagination.cursor` never emitted while `has_more` can be true; REST emits `cursor: null`

**Title:** `pagination.cursor never emitted despite has_more=true; REST also emits literal null for every optional field`

**Body:**
```
## What is broken

    src/core/tools/creatives/listing.py:376   has_more = (page * limit) < total_count
    src/core/tools/creatives/listing.py:443   pagination=SchemaPagination(has_more=has_more, total_count=total_count)   # no cursor, ever

A buyer told `has_more: true` has no way to fetch page 2. Separately, `src/routes/api_v1.py` returns
`response.model_dump(mode="json")` at **ten** call sites (`:237,245,258,273,341,374,400,428,459,471`)
with no `exclude_none`, so every `None` optional serializes as a literal `null` — including
`pagination.cursor` on a terminal page, plus `format_summary`, `status_summary`, `sandbox`,
`context`, `errors`, `ext`.

## Spec mandate (3.1.1)

`v3.1.1 core/pagination-response.json` documents `cursor` as "Only present when has_more is true",
types it `{"type": "string"}` (so `null` fails validation), and sets `additionalProperties: false`
on the block. Graded by `universal/pagination-integrity.yaml` (universal tier, applies to every
agent) — "when `has_more` is true the `cursor` MUST be present" and "An agent that carries a stale
cursor onto the terminal page fails the second-page assertion."

Gate caveat, recorded not resolved: whether `universal/pagination-integrity.yaml` applies to us is
ambiguous — it is `track: core` but declares `agent.capabilities: [has_creative_library]` and
`requires: [controller]`, and `has_creative_library` lives inside the capabilities `creative` block,
which the schema says is "Only present if creative is in supported_protocols." This changes the
**severity**, not the correctness.

## Blocked BDD scenarios

`T-UC-018-edge-pagination-next` (a locally-added scenario, currently dormant, that literally says
"the pagination includes a cursor for the next page"), `T-UC-018-storyboard-list-all-creatives-after-sync`,
`T-UC-018-storyboard-filter-by-concept-id`, `T-UC-005-storyboard-baseline-format-id-object-shape`.

## Acceptance criteria

- [ ] `list_creatives` (and sibling paginated reads) emit a `cursor` whenever `has_more` is true.
- [ ] REST routes use `model_dump(mode="json", exclude_none=True)` — audit all ten call sites.
- [ ] `T-UC-018-edge-pagination-next` wired and green.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-12 — Format identity compared on `id` alone; `agent_url` never canonicalized or compared

**Disposition: NEW** — searched, no existing issue covers the four specific comparison sites this
finding names. **Adjacent, not overlapping:** `#1768` (open) is a narrower, different bug in the same
problem space — MCP's idempotency-hash canonicalization *crashes* on a structured `FormatId` before
reaching any validator; this finding is about comparison logic silently *ignoring* `agent_url`, not
crashing. `#1409` (closed) fixed `list_creative_formats`'s format_id shape — this finding's
"asymmetry" section cites that same tool as the one place identity comparison is already done
correctly, confirming #1409 landed cleanly and pointing at exactly the pattern
(`format_id_identity`) the other three sites should copy.

**Title:** `Format identity comparison ignores agent_url — reads generative/preview requests for third-party formats as ours`

**Body:**
```
## What is broken

Three sites, one rule violated, and an internal asymmetry proving the fix is known:

1. `CreativeAgentRegistry.get_format` (`src/core/creative_agent_registry.py:863-884`) builds a
   throwaway `CreativeAgent(agent_url=…)`, fetches that agent's catalog, then matches
   `if fmt.format_id.id == format_id` — **`agent_url` is ignored entirely**. Under
   `ADCP_TESTING=true` the catalog is returned regardless of which agent was asked. A creative
   referencing `{agent_url: "https://someone-else.example", id: "display_300x250_image"}` is
   accepted as though we hosted it.
2. `src/core/tools/creatives/_processing.py:194-196` (create) and `:511-514` (update) do
   `if fmt.format_id == creative_format` — raw Pydantic equality. A trailing slash, uppercase host
   or explicit default port makes the match fail, `format_obj` stays `None`, and generative
   detection + preview generation are **skipped with no error and no warning**.
3. `_update_existing_creative` (`_processing.py:118-128`) compares
   `new_agent_url != existing_creative.agent_url` byte-wise, so a canonically-equal resubmission
   rewrites the row and reports a spurious `changes: ["format"]`.
4. On the read side, `Creative.agent_url` participates in no filter predicate — two creatives with
   the same `id` on different agents are indistinguishable to every filter path.

**Asymmetry:** `list_creative_formats` already does it correctly —
`src/core/tools/creative_formats.py:296-307,312-313` filters on `format_id_identity`, and
`src/core/schemas/_base.py:145-199` canonicalizes via `adcp.signing.canonicalize_target_uri`. One
concept, two identity rules.

## Spec mandate (3.1.1)

`v3.1.1:static/schemas/source/core/format-id.json`: `required: ["agent_url","id"]` and "Callers
comparing two format-id values MUST canonicalize `agent_url` per the AdCP URL canonicalization rules
before treating two formats as the same." Canonicalization algorithm at
`dist/docs/3.1.1/reference/url-canonicalization.mdx`.

## Blocked BDD scenarios

`T-UC-006-storyboard-format-id-roundtrip-on-sync`, `T-UC-018-storyboard-filter-by-format-id-object`,
`T-UC-005-storyboard-format-id-roundtrip-from-products`,
`T-UC-005-storyboard-format-id-third-party-agent-out-of-scope`.

## Acceptance criteria

- [ ] All four sites compare via `format_id_identity`.
- [ ] Canonicalization test scenarios written only after the comparison is real (a scenario over
      canonicalization spellings written before this fix would pass on every row and prove nothing —
      it would pass because the field is ignored, not because canonicalization works).
- [ ] Note for the roundtrip scenario: production normalizes `agent_url` through Pydantic `AnyUrl`,
      which appends a trailing `/`; `canonical_agent_url` strips it — comparison must be canonical,
      not verbatim.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-13 — `get_adcp_capabilities` under-declares five 3.1.1 flags; a code comment claims a scenario is active that is not

**Title:** `get_adcp_capabilities under-declares five 3.1.1 capability flags; stale comment claims a gated scenario is active`

**Body:**
```
## What is broken

    features = MediaBuyFeatures(
        inline_creative_management=True,
        property_list_filtering=supports_property_list_filtering(adapter),
        catalog_management=False,
    )
    ...
    supported_protocols=[SupportedProtocol.media_buy],
    specialisms=[AdcpSpecialism.sales_non_guaranteed],

Five 3.1.1 capability flags are never emitted (confirmed by grep — 0 hits each in `src/`):

| flag | schema location | correct value today |
|---|---|---|
| `media_buy.supports_proposals` | `get-adcp-capabilities-response.json:209`, `default: false` | `false` — honest, but undeclared reads as omission not decision |
| `media_buy.governance_aware` | same file, `default: false` | `false` |
| `media_buy.creative_approval_mode` | enum `auto_approve`\|`require_human` | derivable **today** from `Tenant.approval_mode` (`src/core/database/models.py:84`); `ai-powered` has no 3.1.1 member and must map to the ceiling `require_human`, not be dropped |
| `creative.has_creative_library` | same file, `default: false` | needs a product decision — declaring it means declaring the `creative` protocol and its baseline bundle |
| collection-list targeting support | `core/targeting.json` | `false` |

**Stale comment.** `src/core/tools/capabilities.py:255-265` asserts that declaring
`specialisms=[sales_non_guaranteed]` activates `pending_creatives_to_start`. At 3.1.1 that is false:
the specialism gate passes but the scenario's own
`requires_capability: media_buy.creative_approval_mode == auto_approve` does not, so the runner
grades `not_applicable`. The comment's stated purpose — "the public declaration forces prioritization
of the remaining gaps instead of hiding them" — is defeated: right now the gap **is** hidden.

Also: there is no BDD or harness coverage of `get_adcp_capabilities` at all, and
`BR-UC-010-discover-seller-capabilities.feature` is unbound (no `scenarios()` call). Our
specialism/protocol declaration — the thing that decides which storyboards grade us — is asserted
nowhere behaviourally.

## Blocked BDD scenarios

`T-UC-001-storyboard-proposal-finalize-action`, `T-UC-001-storyboard-finalize-uses-refine-vocabulary`,
the four `T-UC-002-storyboard-governance-*` scenarios, `T-UC-002-storyboard-pending-creatives-state-transition`,
`T-UC-003-storyboard-creative-fate-after-cancellation`,
`T-UC-006-storyboard-creative-reception-stateful-render`, and every scenario in the parallel retag
set (19 scenarios mis-tagged `@storyboard-v3.1`).

## Acceptance criteria

- [ ] `creative_approval_mode` derived from `Tenant.approval_mode` (the only one with backing data
      today).
- [ ] `supports_proposals`, `governance_aware`, collection-list support declared explicitly `false`
      with a rationale comment, mirroring the existing `catalog_management=False` block.
- [ ] `has_creative_library` decided — a product call, not a one-line edit.
- [ ] The stale comment at `:255-265` corrected.
- [ ] A capabilities harness env + a UC-010 scenario pinning the declaration.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-14 — Per-creative validation failures emitted as transient `SERVICE_UNAVAILABLE`; `error.field` unset

**Title:** `Per-creative validation failures wrongly coded SERVICE_UNAVAILABLE (transient) instead of correctable; error.field unset`

**Body:**
```
## What is broken

    src/core/tools/creatives/_processing.py:34-56
    def _failed_sync_result(creative_id, error_msg, *, recovery=None, code="SERVICE_UNAVAILABLE") -> SyncCreativeResult:

`src/core/tools/creatives/_sync.py:177` and `:338-355` call it **without** forwarding the code or
recovery from the caught `AdCPValidationError`, whose class defaults are
`error_code="VALIDATION_ERROR"`, `recovery="correctable"` (`src/core/exceptions.py:421-426`). So a
buyer whose payload is wrong is told to retry an infra outage.

## Spec mandate (3.1.1)

`v3.1.1 enums/error-code.json` classifies `SERVICE_UNAVAILABLE` as `recovery: "transient"` ("Retry
with exponential backoff"). A conforming buyer retries a request that can never succeed without
correction. The same call site leaves `error.field` unset, which `error-code.json:165` marks
**MUST** for the `PROVENANCE_*` family.

The fix is small: `_failed_sync_result` already accepts `code=` and `recovery=` — pass them through.

## Blocked BDD scenarios

`T-UC-006-storyboard-format-id-roundtrip-on-sync` (its proposed assertion asserts only error
*count*, because asserting `SERVICE_UNAVAILABLE` would pin the defect into the baseline),
`T-UC-006-storyboard-provenance-digital-source-type-missing`.

## Acceptance criteria

- [ ] `_sync.py` forwards the caught error's code and recovery.
- [ ] `error.field` populated for validation failures.
- [ ] Any test assertions characterizing `SERVICE_UNAVAILABLE` as the expected code are replaced
      with the correctable code once fixed.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-15 — REST body models drop spec-required fields (transport boundary-completeness gap)

**Disposition: NEW** — searched, no existing issue names this specific set of five missing-field
instances. **Related, worth sequencing together, not a duplicate:** `#1761` (open) is about
generalizing a *test-harness* drift guard (`_BODY_FIELDS`) across REST body harnesses, so the test
side doesn't silently diverge from the REST `Body` model — a different, narrower problem (test-guard
completeness) than this finding (the REST `Body` models themselves missing spec-required fields).
`#1442` (open) migrates the REST `*Body` models to `SalesAgentBaseModel` for the Pattern #7
extra-field policy — a prerequisite-adjacent change to the same 11 models this finding's five-model
subset lives in, but addresses `extra=` handling, not missing fields. Recommend citing both as
related context in the new issue rather than commenting on either.

**Title:** `REST body models drop spec-required fields — same request produces three different outcomes across transports`

**Body:**
```
## What is broken

One defect class across five REST body models in `src/routes/api_v1.py`:

| body model | missing | consequence |
|---|---|---|
| `ListCreativeFormatsBody` (`:133-147`) | `context`, `pagination` | context echo unassertable on REST/e2e_rest; MCP wrapper also takes no `pagination` |
| `ListCreativesBody` (`:146-168`) | structured `pagination`, `sort`, `account` | only legacy `page`/`limit`/`sort_by`/`sort_order` scalars; a storyboard's own sample_request posting `account: {brand:{domain}, operator, sandbox: true}` is a 422 under `extra="forbid"` |
| `UpdateMediaBuyBody` (`:96-117`) | `canceled`, `cancellation_reason` | REST rejects a spec-valid cancel with a *different* error than A2A/MCP |
| `CreateMediaBuyBody` (`:76-93`) | `plan_id`, `governance_context` | REST **rejects a schema-valid 3.1.1 request outright** while MCP strips it and A2A drops it |
| `activate_signal` wrappers (`signals.py:317-323`, `:366-373`) | `destinations`, `idempotency_key`, `pricing_option_id` | see the signals-surface item |

`ListCreativeFormatsBody.adcp_version` additionally defaults to `"1.0.0"`, which does not match
`version-envelope.json`'s `^\d+\.\d+(-[a-zA-Z0-9.-]+)?$`.

## Spec mandate

Project pattern: "Forward **every** `_impl` parameter — don't silently drop any" — enforced by
`test_architecture_boundary_completeness.py`, which evidently does not cover the REST body models.
Plus per-field 3.1.1 schema mandates on the affected fields (see the linked companion issues on
cancellation, `plan_id`/`governance_context`, and the signals surface).

The same request produces three different outcomes across three transports, so no test can observe
the real behaviour today.

## Blocked BDD scenarios

`T-UC-005-storyboard-format-id-roundtrip-from-products` (context echo red on REST/e2e_rest),
`T-UC-018-storyboard-list-all-creatives-after-sync`,
`T-UC-003-storyboard-not-cancellable-on-recancel`, `T-UC-002-storyboard-governance-approved`.

## Acceptance criteria

- [ ] All five body models carry the fields their `_impl` accepts.
- [ ] `test_architecture_boundary_completeness.py` extended to cover REST body models, not just
      wrappers.
- [ ] `adcp_version` default fixed.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-16 — `plan_id` and `governance_context` dropped at every transport boundary

**Title:** `plan_id and governance_context are declared nowhere — REST rejects a schema-valid create_media_buy request outright`

**Body:**
```
## What is broken

`grep -rn "plan_id\|governance_context" src/ --include='*.py'` → **0 hits each.** Our wrappers
enumerate parameters explicitly and declare neither: MCP `src/core/tools/media_buy_create.py:4373-4420`,
A2A/REST raw `:4495-4512`, REST body `src/routes/api_v1.py:76-93`.

Transport-divergent: MCP strips it, A2A drops it, REST (`extra="forbid"` outside test/dev) **rejects
a schema-valid 3.1.1 request outright**.

## Spec mandate (3.1.1)

- `v3.1.1 media-buy/create-media-buy-request.json:22-25` → `plan_id`: "Required when the account has
  governance_agents. The seller includes this in the committed check_governance request so the
  governance agent can validate against the correct plan." `adcp==6.6.0`'s `CreateMediaBuyRequest`
  declares it.
- `v3.1.1 core/protocol-envelope.json` → `governance_context`: "Buyers attach it to governed purchase
  requests … sellers persist it and include it on all subsequent governance calls for that action's
  lifecycle … In 3.1 all sellers MUST verify."

The persist-and-forward clause binds **even a seller that never claims `governance-aware-seller`**,
once a buyer attaches a token — independent of the specialism/capability-declaration gaps.

The "required when" condition is reachable today — `governance_agents` is wired end to end via
`sync_accounts`.

## Blocked BDD scenarios

`T-UC-002-storyboard-governance-approved`, `…-with-conditions`, `…-denied`, `…-denied-recovery`,
plus four wired UC-002 `plan_id` scenarios (`BR-UC-002-create-media-buy.feature:2031,2044,2056,2069`)
whose step phrasings all have zero definitions, so all four are silently auto-xfailed.

## Acceptance criteria

- [ ] `plan_id` and `governance_context` declared on all three wrappers, forwarded into the request
      model, persisted on the media buy.
- [ ] Minimum honest behaviour: reject a create against a governance-bearing account when `plan_id`
      is absent.
- [ ] `governance_context` persisted and echoed unchanged on the envelope.
- [ ] The four dormant `plan_id` scenarios get step definitions and stop being invisible.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-17 — Delivery emits affirmatively wrong numbers: `clicks=0`, `ctr=0.0`, `currency="USD"`

**Title:** `Delivery emits affirmatively wrong numbers — clicks/ctr default to 0 instead of null, currency hardcoded USD`

**Body:**
```
## What is broken

    src/core/tools/media_buy_delivery.py:343   "clicks": None,   # AdapterPackageDelivery doesn't have clicks yet   ← adapter clicks discarded
    src/core/tools/media_buy_delivery.py:521   clicks = 0
    src/core/tools/media_buy_delivery.py:523   ctr = (clicks / impressions) if clicks is not None and impressions > 0 else None
    src/core/tools/media_buy_delivery.py:675   currency="USD",  # TODO: @yusuf - This is wrong. Currency should be at the media buy delivery level, not on aggregated totals.

This is worse than a missing metric. `core/delivery-metrics.json` defines both `clicks` and `ctr` as
`{"type":"number","minimum":0}` with **no "0 means unknown" semantics**, so `ctr: 0.0` is an
affirmatively wrong number on the wire. The graded storyboard injects `clicks: 150`
(`delivery_reporting.yaml:196`).

`currency="USD"` satisfies the `^[A-Z]{3}$` pattern so it is not a schema violation, but it
misreports the currency for any non-USD buy — and `MediaBuy.currency` is right there on the model.

## Blocked BDD scenarios

`T-UC-004-storyboard-controller-driven-delivery-schema-compliance` (its proposed Gherkin keeps
`clicks 150` in the Given as a no-corruption control and deliberately does not assert it, because
asserting the current `0` would pin the bug).

## Acceptance criteria

- [ ] Clicks carried through `AdapterPackageDelivery`.
- [ ] `ctr` emitted as `None` when clicks are unknown, never `0.0`.
- [ ] `currency` derived from the buy / tenant currency limit; the TODO removed.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-18 — `measurement_terms` accepted and silently dropped; `TERMS_REJECTED` never emitted

**Title:** `measurement_terms accepted and silently dropped — TERMS_REJECTED never emitted, no echo on confirmed packages`

**Body:**
```
## What is broken

`grep -rn "measurement_terms\|TERMS_REJECTED" src/ --include='*.py'` → **0 hits each.**
`src/core/schemas/_base.py:1564` `PackageRequest(LibraryPackageRequest)` inherits the field so it
validates, and `src/core/tools/media_buy_create.py` never reads it.

Measured on all three wire transports against real Postgres: a create carrying deliberately
unacceptable terms (`max_variance_percent: 0`, `measurement_window: "c28"`) returns
`status: "completed"` with a `media_buy_id`, byte-identical to the same request with
`measurement_terms` omitted entirely.

## Spec mandate (3.1.1)

- Graded at `protocols/media-buy/scenarios/measurement_terms_rejected.yaml:132-142` —
  `- check: error_code, value: "TERMS_REJECTED"`. Code defined at `v3.1.1 enums/error-code.json`
  index 53, `enumMetadata.TERMS_REJECTED.recovery = "correctable"`.
- Echo: `v3.1.1 media-buy/package-request.json` — "Seller accepts (echoed on confirmed package),
  rejects with TERMS_REJECTED, or adjusts"; `core/measurement-terms.json` — "Appears on products
  (seller defaults), package requests (buyer proposals), and confirmed packages (agreed terms)."

Also needed for green: `field_present context` + `field_value context.correlation_id` **on the
error envelope**.

## Related, blocked behind this

`measurement_terms_rejected.yaml:203` requires that after a `TERMS_REJECTED` response, a retry with
the same `idempotency_key` and corrected terms returns a **fresh** `media_buy_id`, not
`IDEMPOTENCY_CONFLICT` (only successful responses are cached per the security spec). The right shape
is already documented in `_cache_and_return` (`media_buy_create.py:1847`), but no test exercises it
and none can until `TERMS_REJECTED` exists.

## Blocked BDD scenarios

`T-UC-002-storyboard-measurement-terms-rejected`.

## Acceptance criteria

- [ ] `measurement_terms` evaluated; `TERMS_REJECTED` emitted with `recovery: correctable`.
- [ ] Accepted terms echoed on the confirmed package.
- [ ] The idempotency-claim-release behaviour tested.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-19 — `SyncCreativeResult.status` never populated; MCP serializes it as `null`

**Title:** `SyncCreativeResult.status is never populated; MCP path additionally serializes it as schema-invalid null`

**Body:**
```
## What is broken

`src/core/schemas/creative.py:369-378` records the decision to inherit but not populate the spec
`status`: it stays `None`. The internal state lives in `internal_status` (`exclude=True`). Executed
probe (three creatives): `status=None` on every result, absent from `model_dump()`.

**Two separable defects.**

**a — the omission may not be permitted for us.** `v3.1.1 creative/sync-creatives-response.json`
permits omission only as "Omit entirely when the seller has no review lifecycle at all." The same
probe log shows "Created 3 workflow steps for creative approval" — we demonstrably **have** a review
lifecycle and an internal `pending_review` state, so the carve-out does not apply.

**b — MCP emits `status: null`, which is schema-invalid.** The in-code comment states it plainly:
"on MCP the response goes through `structured_content` → `to_jsonable_python`, which BYPASSES the
`model_dump` override, so the inherited `status` serializes as null." `status` `$ref`s
`enums/creative-status.json`, a string enum — `null` is not a member. The key being present also
trips the schema's `if action ∈ {failed, deleted} then not required: ["status"]`. A2A/REST are
unaffected (`exclude_none=True`).

**Adjacent.** Local `CreativeStatusEnum` (`creative.py:123-129`) defines
`{processing, approved, rejected, pending_review}` while 3.1.1 has
`{processing, pending_review, approved, suspended, rejected, archived}` — `suspended` and `archived`
are missing, and `archived` is written as a bare string bypassing the enum, even though
`adcp.types.CreativeStatus` is already imported at `creative.py:13`.

## Blocked BDD scenarios

`T-UC-006-storyboard-multi-format-sync`, `T-UC-006-storyboard-creative-reception-stateful-render`.

## Acceptance criteria

- [ ] `internal_status` mapped onto the spec `status` using `enums/creative-status.json` members,
      honouring the `failed`/`deleted` exclusion — or the omission decision is recorded with the
      "no review lifecycle" carve-out explicitly ruled inapplicable.
- [ ] MCP's `structured_content` path stops emitting `status: null` either way.
- [ ] Local `CreativeStatusEnum` replaced with `adcp.types.CreativeStatus`.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-20 — Signals surface is structurally non-conformant and registered on no transport

**Disposition: SPLIT across three existing issues + one closed decision issue for context** —
corrected after direct verification (`gh issue view` on 1003, 1353, 1593, 1783, all
`--repo prebid/salesagent`). The framing in this sweep ("decide build-out vs retire") is **stale**:
that decision was already made and closed as **#1003** ("chore: Decide fate of Signals tools —
re-enable or remove code," CLOSED) — the follow-up issues below are all "build it out," not
"retire it," so this issue's own "decision that gates all six" framing should be corrected before
posting anything, not repeated.

- **Sub-defect 3 (naive substring matching on `signal_spec`) → SHARPEN #1783.** Exact match, open:
  "get_signals: whole-phrase substring match on signal_spec returns zero signals for any
  natural-language brief," same file, nearly identical line numbers
  (`signals.py:162-168` there vs `:161-168` measured here), same storyboard sample spec ("Adults
  interested in electric vehicles") producing zero matches. **Do not file a new issue for this
  sub-defect** — comment on #1783 only if this sweep adds anything past its own already-precise
  writeup (it largely doesn't; skip commenting unless a maintainer wants the cross-reference to the
  storyboard slate).
- **Sub-defect 6 (tools registered on no transport) → SHARPEN #1353.** Exact match, open: "register
  or remove dead get_signals and activate_signal _raw functions." Given #1003's closed decision is
  "build it out," this issue's "remove" option is moot — worth a comment saying so.
- **Sub-defects 1 and 2 (`ActivateSignalResponse` has no `deployments`; wrapper fabricates
  `destinations`/`idempotency_key`) → related to #1593** ("signals: expose activate_signal on the
  wire + populate value_type in the signal catalog"), which covers the registration half but not
  these two schema/request-shape defects specifically. Comment with the added detail.
- **Sub-defects 4 and 5 (deprecated `signal_id` only; `_activate_signal_impl` is a façade with no
  HTTP call) → no existing issue found.** These remain **NEW**, but should be filed as follow-ups
  referencing #1593/#1353 rather than as a restatement of "decide build-out or retire."

**Comment to add to #1353 (`gh issue comment 1353 --repo prebid/salesagent --body-file ...`):**

```
Correcting the framing on this from an AdCP 3.1.1 storyboard re-grounding sweep (branch
test/storyboard-binding-baseline): #1003 already closed the "re-enable or remove" decision in favor
of building it out (that issue and its follow-ups #1593 and this one are all "build" work), so this
issue's "remove" option should be treated as moot rather than a live alternative.

For context, the signals surface has several more structural gaps beyond registration, gated behind
the same "build it out" decision — worth tracking together so registering the dead functions doesn't
ship a surface that still fails schema/behavioral grading immediately after registration:
- ActivateSignalResponse has no `deployments` field (src/core/schemas/_base.py:2458-2471); 3.1.1
  requires it on the success branch and forbids `errors` there — our response matches neither
  discriminated-union branch.
- The activate_signal wrapper fabricates the two REQUIRED request fields
  (destinations, idempotency_key) rather than accepting them from the caller
  (src/core/tools/signals.py:239-247) — a server-synthesized idempotency_key defeats its entire
  retry-dedupe purpose.
- Only the deprecated signal_id is emitted; 3.1.1 defines signal_ref as canonical.
- _activate_signal_impl is a pure façade — synthesizes a fake activation key and duration with no
  outbound HTTP call, failing the graded upstream_traffic check
  (specialisms/signal-marketplace/index.yaml:353-363).

Full detail (with file:line) in the storyboard-conformance slate if useful:
.claude/notes/storyboard-conformance/CONSOLIDATED-ISSUES.md, item P-20.
```

**NEW draft (sub-defects 4 and 5 only), for reference if the human wants to file separately:**

**Title:** `Signals: deprecated signal_id emitted instead of signal_ref; activate_signal is a façade with no outbound HTTP call`

**Body:**
```
## Context

#1003 already decided to build out the signals surface rather than delete it (that issue is closed;
#1353 and #1593 are open follow-ups toward registration). This issue covers two remaining defects
that neither of those two currently names:

1. **Only the deprecated `signal_id` is emitted.** `src/core/tools/signals.py:45-55`. 3.1.1 marks
   `signal_id` `"deprecated": true` and defines `signal_ref` (`$ref core/signal-ref.json`) as the
   canonical reference. An existing comment in the file already flags this.
2. **`_activate_signal_impl` is a pure façade.** `signals.py:279-308` synthesises a fake
   `decisioning_platform_segment_id` and a fixed `estimated_activation_duration_minutes: 15.0` with
   no HTTP call. `specialisms/signal-marketplace/index.yaml:353-363` grades `check: upstream_traffic`
   (`min_count: 1`, `endpoint_pattern: "POST *"`) — an adapter returning a fabricated activation key
   without touching the DSP fails this check.

Also relevant, covered separately by comments on #1783 (naive substring matching, exact match
already tracked) and #1353/#1593 (registration, `ActivateSignalResponse` shape, request-field
fabrication) — see the accompanying storyboard-conformance drafts for those.

## Blocked BDD scenarios

All three `T-UC-008-storyboard-*` (in `BR-UC-008-manage-audience-signals.feature`, currently unbound
— see the separate test-infra item on unbound feature files).

## Acceptance criteria

- [ ] `signal_ref` emitted alongside (or instead of) the deprecated `signal_id`.
- [ ] `_activate_signal_impl` makes a real outbound call to the destination, or the seller declines
      to claim `signal-marketplace` until it does.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-21 — Provenance policy resolved tenant-wide from `provenance_policies[0]`, not per-product

**Title:** `Provenance policy resolved tenant-wide from provenance_policies[0] instead of per-product`

**Body:**
```
## What is broken

`src/core/tools/creatives/_sync.py:140-146,184` passes `provenance_policies[0]` — with the in-code
comment "Use the first matching policy (tenant-wide enforcement)" — to every creative in the sync,
regardless of which product the creative targets. The list comes from
`CreativeRepository.get_provenance_policies()` (`src/core/database/repositories/creative.py:263-273`),
which filters on `p.creative_policy.get("provenance_required")` alone.

Two defects: (a) a tenant with two products under different `provenance_requirements` gets whichever
row the query returns first — non-deterministic across tenants; (b) a product publishing
`provenance_requirements` **without** `provenance_required: true` is invisible to enforcement
entirely.

## Spec mandate (3.1.1)

`v3.1.1 core/creative-policy.json` title: "Creative requirements and restrictions for **a
product**." The storyboard binds the requirement to the product discovered via `get_products`
(`provenance_enforcement.yaml:83-140`, phase `discover_requirement`).

## Blocks

The correctness of the `provenance_requirements`/`accepted_verifiers` enforcement item depends on
this being fixed.

## Acceptance criteria

- [ ] Policy resolved from the product(s) the creative is destined for.
- [ ] `get_provenance_policies` reads `provenance_requirements`, not only `provenance_required`.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-22 — Proposal/refine lifecycle absent; `refine` silently discarded; `brief` accepted with `buying_mode: refine`

**Disposition: SHARPEN existing #1272** — corrected after direct verification
(`gh issue view 1272 --repo prebid/salesagent`). #1272, "feat: wire buying_mode and refine through
get_products and storyboard refine_products compliance," is an exact match, still open: "salesagent
currently parses requests with all three modes... but discards both buying_mode and refine at every
layer downstream. The AdCP media_buy_seller/refine_products storyboard scenario... cannot pass." Its
body also references a broader sibling, #1073 (proposal persistence, intelligent refinement
application, finalize HITL flow), which is where part (e) below (no proposal lifecycle at all)
belongs. **Do not file a new issue for parts (a)–(d); part (e) is already out-of-scope-by-design in
#1272 and belongs on #1073 instead.**

**What #1272 is missing that this sweep adds:** (1) it's pinned to spec 3.0.6/3.1.0-rc.14 in its own
text — re-verified live against the 3.1.1 request schema and confirmed still broken with fresh
executed evidence; (2) the specific `brief`-alongside-`buying_mode:refine` acceptance bug (part a) —
the **highest-value, already-reachable** part of this gap, since it needs no new lifecycle work, just
a cross-field validator; (3) the finalize-exclusivity enforcement gap (part c) and the
multi-finalize-atomicity gap (part d), each independently implementable as a model validator without
touching the full proposal lifecycle; (4) the specific blocked-scenario list; (5) branch
`test/storyboard-binding-baseline` citation.

**Comment to add (`gh issue comment 1272 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment):**
```
## Ordered by what is actually on our conformance path

**a — `brief` alongside `buying_mode: "refine"` is accepted. This is on our conformance path today.**
`GetProductsRequest.model_validate({"buying_mode":"refine","brief":"x","refine":[…]})` succeeds
(executed). `v3.1.1 media-buy/get-products-request.json:50-52` → `properties.brief.description`:
"Must not be provided when `buying_mode` is 'wholesale' or 'refine'." Not proposal-gated —
`media_buy_seller/refine_products` is a scenario our declared protocol requires. **Highest-value
part of this issue.**

**b — `refine` is accepted and silently discarded.** `src/core/tools/products.py` never reads
`req.refine` — a quiet failure. The schema requires the seller respond to each entry via
`refinement_applied` matched by position; we emit none.

**c — finalize-exclusivity is not enforced.** Executed:
`GetProductsRequest` accepts a mix of `finalize` and `include`/request-scoped entries in the same
array. 3.1.1 requires the seller reject that mix with `INVALID_REQUEST`. Independently implementable
today as a model validator.

**d — multi-finalize atomicity unenforced; `MULTI_FINALIZE_UNSUPPORTED` never emitted.** Two
proposal-scoped finalize entries are accepted together, when the schema requires rejecting
multi-finalize arrays a seller cannot guarantee atomic pre-commit validation for.

**e — no proposal lifecycle at all.** `grep -rn "proposals\|proposal_status\|PROPOSAL_NOT_FOUND" src/`
→ zero hits. Gated behind the `media_buy.supports_proposals` capability decision (separate item).

## Blocked BDD scenarios

`T-UC-001-storyboard-proposal-finalize-action`, `T-UC-001-storyboard-finalize-uses-refine-vocabulary`
and its four `BR-RULE-086` siblings — all inside a feature file that is currently unbound.

## Acceptance criteria

- [ ] Part (a) fixed first — cross-field validator on `GetProductsRequest`, on our conformance path
      today.
- [ ] Part (c) as an array-level model validator raising `INVALID_REQUEST` with `field` naming the
      offending entry index.
- [ ] Parts (b), (d), (e) sequenced behind the `supports_proposals` capability decision.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-23 — `collection_list` accepted with zero validation, zero capability declaration, zero wire signal

**Disposition: SHARPEN existing #1446** — corrected after direct verification
(`gh issue view 1446 --repo prebid/salesagent`). #1446, "feat: collection_list targeting end-to-end —
Product.collections persistence, resolver, capability declaration, adapter passthrough," is an exact
match, still open, split from the (closed) #1302 property_list work specifically for the
collection-list half: "None of it is built yet." **Do not file a new issue.**

**What #1446 is missing that this sweep adds:** (1) it's pinned to "3.0.1; collections optional at
the 3.1 target, verified 3.1.0-rc.14" — this sweep re-confirms the gap at the 3.1.1 pin with fresh
executed evidence (18 mcp/a2a/rest combinations; a matching-nothing `collection_list` is persisted,
never resolved, and `errors` is absent from the response entirely); (2) the specific comparison to
`property_list`, which got an `UNSUPPORTED_FEATURE` advisory for the identical situation while
`collection_list` got none — a concrete asymmetry to fix in the same change; (3) the exact blocked
scenarios (`T-UC-002-storyboard-inventory-list-no-match`,
`T-UC-002-storyboard-inventory-list-targeting-parity`); (4) branch
`test/storyboard-binding-baseline` citation. Note the coordination point: any advisory added here
must ride a response branch the 3.1.1 schema actually permits — see the SHARPEN note on the separate
"success envelope carries errors" finding (P-02) filed alongside this one.

**Comment to add (`gh issue comment 1446 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment):**
```
## What is broken

`collection_list` / `collection_list_exclude` are declared fields on our `Targeting` (inherited from
the library `TargetingOverlay`), so they never land in `model_extra` and
`validate_unknown_targeting_fields` raises nothing. Then nothing validates them: no capability check,
no product flag, no rejection, no advisory.

Measured (18 combinations across mcp/a2a/rest): a `collection_list` that matches nothing is
persisted, never resolved, never mentioned on the wire — `errors` is **absent from the response
entirely**. That is exactly the failure mode the corresponding storyboard narrative forbids:
"What the seller must NOT do: … silently drop the targeting and deliver against unintended
inventory."

`property_list` got an `UNSUPPORTED_FEATURE` advisory for precisely this window; `collection_list`
did not.

## Spec mandate (3.1.1)

`v3.1.1 core/targeting.json` → `collection_list` and `collection_list_exclude`: "Seller must declare
support in get_adcp_capabilities." We declare nothing either way.

## Blocked BDD scenarios

`T-UC-002-storyboard-inventory-list-no-match`, `T-UC-002-storyboard-inventory-list-targeting-parity`.

## Acceptance criteria

- [ ] Collection-list support declared (as `false`) in `get_adcp_capabilities`.
- [ ] The sibling `UNSUPPORTED_FEATURE` advisory emitted while it is off — or a hard rejection, but
      not silence. (Coordinate with the success-envelope-carrying-errors item: the advisory must not
      ride the success envelope.)

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-24 — `error.field` is index-less and transport-dependent

**Title:** `error.field omits the package/entry index and differs by transport for the same request`

**Body:**
```
## What is broken

**a — index-less path.** `src/core/validation_helpers.py::package_field_path` produces `packages[]`
with an **empty subscript**; `raise_if_property_targeting_violations` passes it through. Observed
verbatim on the wire on mcp/a2a/rest: `field = "packages[].targeting_overlay.property_list"`.
`v3.1.1 core/error.json` → `field`: "Field path associated with the error in JSONPath-lite format
(e.g., 'packages[0].targeting')." The buyer cannot tell which package failed when several are sent.
The fix is already written elsewhere: `build_property_list_unsupported_advisories` emits
`packages[{index}].targeting_overlay.property_list` — the rejection path just needs the same index.

**b — transport-dependent path.** Measured for one malformed request: a2a/rest emit
`field: "format_ids[0]"`, mcp emits `field: "filters.format_ids[0]"`; the a2a/rest `message` is a
long narrative while mcp's is the bare Pydantic string. `core/error.json` types `field` as a single
protocol-level pointer — one request shape must produce one pointer.

## Acceptance criteria

- [ ] Rejection paths carry the package index.
- [ ] One request shape produces one `field` pointer and one message across all four transports.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-25 — `include_package_daily_breakdown` ignored; `viewability` is a scalar where 3.1.1 requires an object

**Disposition: SPLIT.** Part (a) is SHARPEN existing #1776; part (b) is NEW.

**Part (a) — SHARPEN #1776.** Corrected after direct verification (`gh issue view 1776 --repo
prebid/salesagent`). #1776, "get_media_buy_delivery silently ignores
include_package_daily_breakdown=true," is an exact match, still open, same file and same line
(`src/core/tools/media_buy_delivery.py:549`, hardcoded `daily_breakdown=None`). **Do not file a new
issue for part (a).** What #1776 is missing: the schema-required shape for the field once
implemented (`PackageDelivery` needs a `daily_breakdown: list[DailyBreakdownEntry] | None` field it
doesn't have yet — `required: ["date","impressions","spend"]`, `date` pattern `^\d{4}-\d{2}-\d{2}$`),
and a note that a sibling issue (#1711) covers the adjacent `time_granularity`/
`include_window_breakdown` fields in the same function — worth sequencing together. Branch
`test/storyboard-binding-baseline` citation.

**Comment to add to #1776 (`gh issue comment 1776 --repo prebid/salesagent --body-file ...`):**

```
Additional detail found during an AdCP 3.1.1 storyboard re-grounding sweep (branch
test/storyboard-binding-baseline): PackageDelivery (src/core/schemas/delivery.py) has no
daily_breakdown field at all yet, so even once media_buy_delivery.py:549 stops hardcoding None, the
package-level array this flag names cannot be represented. Fix: add
daily_breakdown: list[DailyBreakdownEntry] | None to PackageDelivery, matching the 3.1.1 schema
(required: ["date","impressions","spend"], date pattern ^\d{4}-\d{2}-\d{2}$). The graded step sends
include_package_daily_breakdown: true at delivery_reporting.yaml:226. Also worth sequencing with
#1711 (time_granularity / include_window_breakdown), same function, same shape of gap.
```

**Part (b) — NEW.** `viewability` emitted as a bare float where 3.1.1 requires an object; no existing
issue found covering this. This folds naturally into the delivery-schema-inheritance item (P-06,
extend the library type) but is separately testable.

**Title (if filed as its own issue, or folded into P-06's PR):** `viewability emitted as a bare float instead of the 3.1.1-required object shape`

**Body:**
```
## What is broken

`src/core/schemas/delivery.py:119` declares
`viewability: float | None = Field(None, ge=0, le=1, …)`. In 3.1.1 `core/delivery-metrics.json`,
`viewability` is `{"type": "object"}` carrying `measurable_impressions`, `viewable_impressions`,
`viewable_rate`, `viewed_seconds`, `standard`, `vendor`. Production assigns it straight from the
adapter, so any seller that populates it emits a bare float and fails `response_schema`. This leaves
the storyboard's entire `viewability_delivery` phase (six graded `field_present` checks) with zero
coverage.

This folds naturally into the delivery-schema-inheritance item (P-06, extend the library type) but is
separately testable and worth its own PR-sized fix.

## Acceptance criteria

- [ ] `viewability` emitted as the required object shape, sourced from adapter data where available.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-26 — `update_media_buy` does not enforce `idempotency_key` (REQUIRED at 3.1.1)

**Disposition: SHARPEN existing #1470** — corrected after direct verification
(`gh issue view 1470 --repo prebid/salesagent`). #1470, "idempotency_key required on
update_media_buy: schema requires it, impl leaves it optional — how to proceed?" is an exact match,
still open, and already asks the exact product question this finding raises. It even cites the same
stale pin (`adcp@04f59d2d5`) this sweep flags elsewhere as behind our 3.1.1 pin. **Do not file a new
issue — this comment answers the "how to proceed" question with the scope split below and should
help unblock it.**

**What #1470 is missing that this sweep adds:** (1) the scope split that separates this from the
`account`-field optionality question — `account` is a deliberate, separately-tracked interim (account
management is in flight), but `idempotency_key` is not covered by that and should be tightened
independently; (2) the harness-masking detail — `account` is already stripped before dispatch by the
test harness's `_WRAPPER_UNSUPPORTED_FIELDS` allowlist, so the storyboard's `account` block cannot
reach production through BDD today regardless of this decision; (3) an explicit caveat that
tightening either turns most of `BR-UC-003` red today, so this needs fallout planning, not a drive-by
change; (4) branch `test/storyboard-binding-baseline` citation.

**Comment to add (`gh issue comment 1470 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment):**
```
## What is broken

`git show v3.1.1:static/schemas/source/media-buy/update-media-buy-request.json` declares
`"required": ["idempotency_key", "account", "media_buy_id"]`. `UpdateMediaBuyRequest`
(`src/core/schemas/_base.py:2005-2011`) overrides **both** `account` and `idempotency_key` to
optional, with an in-code note calling the required-key enforcement "a deliberate fast-follow".
Verified by introspection: `UpdateMediaBuyRequest(media_buy_id="x", paused=True)` constructs
cleanly.

## Scope split — this matters

`account` optionality is a deliberate, tracked interim (account management is in flight as separate
work). `idempotency_key` is **not** covered by that and is a separate conformance break: every 3.1.1
`update_media_buy` request must carry one.

Compounded on the test side: `account` is in the harness's `_WRAPPER_UNSUPPORTED_FIELDS` allowlist
and stripped before dispatch, so a storyboard's `account` block cannot even reach production through
BDD today.

## Caveat

Tightening either turns most of `BR-UC-003` red today, so this is not a drop-in baseline-PR change —
plan the fallout.

## Acceptance criteria

- [ ] `idempotency_key` required on `UpdateMediaBuyRequest`, with the BR-UC-003 fallout fixed in the
      same change.
- [ ] `account` tracked separately under the ongoing account-management work.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-27 — No inbound `preview_creative` or `build_creative` tool; two stale comments claim they aren't in the spec

**Disposition: NEW, but this is contesting a deliberate prior decision, not a re-surfaced gap —
read carefully before filing.** Verified via `gh issue view 998 --repo prebid/salesagent` including
its closing comment: **#998**, "feat: Expose Build/Preview Creative as public AdCP tools," proposed
exactly this and was **closed as COMPLETED with the comment "Closing - sales agent isn't a creative
agent. Creative building/preview happens via integrated creative agents, not the sales agent
itself."** This is not an abandoned or stale issue — it's a considered product decision against
building this.

**Why this sweep's finding is not simply "the decision needs re-litigating in general" but does
identify a specific, narrower gap the closing rationale doesn't address:** the closing comment
reasons from "we're not a creative agent" — true for `build_creative` (gated behind the
`creative-ad-server` specialism + `creative` protocol, neither of which we declare, so #998's
rationale fully applies there). But `preview_creative` is required by
`protocols/media-buy/scenarios/creative_reception.yaml:186-240` (`requires_tool: preview_creative`,
line 197) — a **media-buy** protocol step, not a creative-protocol one, and **media-buy is the
protocol we already declare and are trying to conform to**. So the "we're not a creative agent"
rationale, correct for `build_creative`, does not obviously extend to `preview_creative` once a
buyer is mid-flow on a media-buy storyboard we claim to support.

**Recommend:** do not silently reopen #998 or file a new issue restating the old ask. Instead, file
(or comment) with this narrower, re-argued case — `preview_creative` specifically, scoped to the
media-buy protocol requirement, with the two stale code comments that currently miscite the AdCP
spec as not covering these tools (which independently need fixing regardless of the scope decision).
Leave `build_creative` out of scope, consistent with #998's still-valid rationale, unless the
`creative` protocol declaration decision (tracked under the capabilities item, P-13) changes.

**Title:** `preview_creative and build_creative exist only as outbound calls to third-party agents — no inbound tool, and two comments wrongly claim they aren't in the spec`

**Body:**
```
## What is broken

Both tools exist only as **outbound** MCP client calls we make *to* third-party creative agents from
`sync_creatives`:

    src/core/creative_agent_registry.py:885   CreativeAgentRegistry.preview_creative   (outbound)
    src/core/creative_agent_registry.py:996   client.call_tool("build_creative", params) (outbound)
       reached from src/core/tools/creatives/_processing.py:253,359,565,649

`src/core/main.py:351-366` registers 16 tools; neither is among them. No MCP wrapper, no A2A raw
function, no REST route, no harness env.

**Two stale comments actively mislead the "should we implement this" decision:**

- `src/core/creative_agent_registry.py:917`: "Use custom MCP client for non-standard tools
  (preview_creative not in AdCP spec)" — it **is** in the spec at 3.1.1:
  `static/schemas/source/creative/preview-creative-{request,response}.json`, referenced by three
  separate storyboard steps.
- `src/core/creative_agent_registry.py:981`: "build_creative not in AdCP spec" — false at 3.1.1:
  `static/schemas/source/media-buy/build-creative-{request,response}.json` both exist.

**The `preview_creative` gap is on a protocol we DO declare.**
`protocols/media-buy/scenarios/creative_reception.yaml:186-240` — a media-buy step — has
`requires_tool: preview_creative` (line 197), and we forfeit the only graded `preview_url` check at
3.1.1. `build_creative` sits behind the `creative-ad-server` specialism + `creative` protocol,
neither declared, so it is a scope decision rather than a conformance failure.

## Blocked BDD scenarios

`T-UC-021-storyboard-preview-display-from-synced-manifest`,
`T-UC-020-storyboard-build-vast-tag-from-synced-creative` (both in unbound feature files).

## Acceptance criteria

- [ ] Both comments corrected (one-line each, but load-bearing for the decision).
- [ ] `preview_creative` `_impl` + 3 transport wrappers + a preview harness env — it is on the
      media-buy path.
- [ ] `build_creative` scope decided alongside the `creative` protocol capability question.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-28 — `pending_creatives → pending_start` transition does not exist; three duplicated transition blocks

**Disposition: SHARPEN existing #1305** — corrected after direct verification
(`gh issue view 1305 --repo prebid/salesagent`). #1305, "feat: spec-conformant async/submitted
response envelopes — Response3 shape, task_id population, status lifecycle alignment," is a large
issue whose invariant 6 explicitly claims to close "#1247 gap #12 (pending_creatives → pending_start
status transition)" and lists `pending_creatives_to_start.yaml` as a storyboard it unblocks. **This
sweep's direct code measurement shows that specific transition is still not implemented** — no writer
of `MediaBuy.status` on any buyer-facing path performs `pending_creatives → pending_start`, and the
status scheduler's candidate query doesn't even examine buys in `pending_creatives`. Either #1305's
invariant 6 was never actioned, or it was scoped out during implementation of the issue's other
invariants. **Do not file a new issue — comment on #1305 with the fresh evidence so the gap doesn't
get silently dropped when the rest of that issue lands.**

**What #1305 is missing that this sweep adds:** (1) fresh, precise file:line evidence that the
specific transition (not the rest of #1305's async-envelope scope) is still open:
`_assignments.py:283-285`, `media_buy_update.py:942-951` and `:1178-1187` (duplicated), and
`media_buy_status_scheduler.py:88-90` (candidate query omits `pending_creatives` entirely); (2) the
DRY finding that the two `draft → pending_creatives` blocks are byte-identical copies, a natural
extraction point for the new transition logic; (3) the schema/storyboard split — the schema says the
buyer "must attach creatives via sync_creatives," but the storyboard actually grades the transition on
`update_media_buy`'s response after a `sync_creatives` step, meaning both tools plausibly need to
participate; (4) the package-level `context` omission on the same code path
(`media_buy_create.py:4073-4086` builds `Package` without `context=`), graded on the same storyboard;
(5) branch `test/storyboard-binding-baseline` citation.

**Comment to add (`gh issue comment 1305 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment, scoped to just this sub-part of #1305's larger invariant list):**
```
## What is broken

Every writer of `MediaBuy.status` on a buyer-facing path was enumerated; none performs this
transition:

    src/core/tools/creatives/_assignments.py:283-285   draft → pending_creatives only (when approved_at is not None)
    src/core/tools/media_buy_update.py:942-951         draft → pending_creatives only
    src/core/tools/media_buy_update.py:1178-1187       draft → pending_creatives only  ← identical to the above (DRY)
    src/services/media_buy_status_scheduler.py:88-90   candidate query = ["pending_start","pending_activation","scheduled","active"]
                                                        → pending_creatives is NOT in it, so a buy parked there is never examined

A buy created without creatives is persisted `pending_creatives` and stays there forever from the
buyer's perspective. The remaining writers are Admin-UI operator actions, not the buyer protocol
path.

## Spec mandate (3.1.1)

`pending_creatives_to_start.yaml:253-256` (`field_value media_buy_status allowed_values:
["pending_start","active"]` on step `assign_creative_to_package`) and again at `:294-297` on
`get_media_buy_after_sync`. Also `enums/media-buy-status.json`, whose `pending_creatives`
enumDescription defines the state as cleared once the buyer attaches creatives. Must respect the
`status.monotonic` invariant.

**A real schema/storyboard split.** `media-buy-status.json` says the buyer "must attach creatives via
`sync_creatives`"; the storyboard grades the transition on `update_media_buy` (its `sync_creatives`
step validates `response_schema` and nothing else). In practice both are needed: sync ingests the
asset, update binds it to the package.

**Related.** Package-level `context` is dropped: `media_buy_create.py:4073-4086` constructs the
response `Package` without `context=` though `adcp.types.aliases.Package` declares
`context: ContextObject | None`. Graded at `pending_creatives_to_start.yaml:165-168` and `:302-305`
("legacy package correlation" — buyers depend on it for package↔line-item mapping). Pairs with the
per-buy `context` half of the `get_media_buys` schema-completeness item.

## Acceptance criteria

- [ ] The transition implemented on the buyer path, honouring `status.monotonic`.
- [ ] The three `draft → pending_creatives` copies folded into one shared helper — the natural home
      for the new transition logic.
- [ ] `media_buy_status_scheduler` candidate query includes `pending_creatives`.
- [ ] Package-level `context` echoed on create and read.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### P-29 — `GovernanceAgent` rejects the required `authentication` block and accepts plaintext `http://` URLs

**Title:** `GovernanceAgent request model rejects authentication and accepts plaintext http:// — sync_governance can never accept a spec-shaped registration`

**Body:**
```
## What is broken

**a — spec-shaped registration is rejected at the model boundary.** `src/core/tools/accounts.py:255-273`
(`_serialize_governance_agents`) validates every incoming agent through
`adcp.types.generated_poc.core.account.GovernanceAgent`, which is `extra="forbid"` with `url` as its
only field (verified: passing `authentication` raises `extra_forbidden`).
`sync-governance-request.json` declares the agent item `required: ["url", "authentication"]` with
`authentication.credentials.minLength: 32`. So we can never accept credentials, and therefore can
never call a governance agent even once `sync_governance` is implemented. The SDK type is modelled
on the *response* shape (`core/account.json`, url-only) and is being reused for the *request* shape;
those are deliberately asymmetric (credentials are write-only) and need a separate request-side
model.

**b — `^https://` is never enforced.** `core/account.json` and `sync-governance-request.json` both
declare `"pattern": "^https://"` on `url`. The SDK `GovernanceAgent.url` is
`{"type":"string","format":"uri","minLength":1}` — the pattern is dropped in codegen. Verified:
`GovernanceAgent.model_validate({'url':'http://plain.example'})` is accepted and normalises to
`http://plain.example/`. Since that model is our DB column type
(`src/core/database/models.py:827-829`) and our response type, we persist and echo plaintext
governance endpoints. Schema wins over SDK: add explicit validation, do not wait on an SDK fix. (This
sub-finding is the same class as an existing issue on lax pydantic coercion vs JSON-Schema strict
types — filing a comment there in addition to this issue; see companion note below.)

**c — `sync_accounts` never echoes the governance binding.** `_build_sync_result`
(`src/core/tools/accounts.py:~313`) omits `governance_agents` entirely; the value is only readable
via a follow-up `list_accounts`. Not a `sync_accounts` violation today (that response schema does not
declare the field), but it is the shape the `sync_governance` implementation must ship
(`sync-governance-response.json` requires the persisted agent in `accounts[].governance_agents`).

## Blocked BDD scenarios

`@T-UC-030-bva-url` expects `URL_NOT_HTTPS` for `http://` and will fail whenever
`BR-UC-030-manage-governance-binding.feature` is wired (it currently has no `scenarios()` binding).

## Acceptance criteria

- [ ] A request-side `GovernanceAgent` model that accepts `authentication` per
      `sync-governance-request.json`.
- [ ] `^https://` enforced explicitly at our boundary regardless of SDK codegen.
- [ ] `sync_accounts` response shape decided (echo now, or defer to `sync_governance`'s landing).

## Companion action

Part (b) above (plaintext `http://` acceptance) is also being raised as a comment on the existing
"lax pydantic coercion vs JSON-Schema strict types" issue (#1582) rather than duplicated as a
separate bug — see the SHARPEN note for #1582 in the accompanying drafts file. This issue should
still be filed for parts (a) and (c), which are new and not covered by #1582.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

## 3. TEST-INFRA items (T-01 .. T-12)

### T-01 — `then_response_schema_valid` runs no validator, and exists twice with divergent strength

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `then_response_schema_valid step exists twice with divergent rigor — one copy asserts only isinstance(list)`

**Body:**
```
## What is broken

This is the single highest-leverage test-infra item on the slate. `- check: response_schema` is the
most-graded check across every 3.1.1 storyboard, and it has no honest representation everywhere in
the BDD suite.

Two steps, one phrasing, different rigour:

    # tests/bdd/steps/domain/uc005_format_id_roundtrip.py:101-108   ← THE VACUOUS ONE
    @then("the response should be schema-valid against list-creative-formats-response.json")
    def then_response_schema_valid(ctx: dict) -> None:
        formats = _serialized_formats(ctx)
        assert isinstance(formats, list), f"Expected formats to be a list, got {type(formats).__name__!r}"

    # tests/bdd/test_uc018_list_creatives.py:216-220                 ← THE REAL ONE
    @then(parsers.parse("the response should be schema-valid against {schema_file}"))
    def then_response_schema_valid(ctx: dict, schema_file: str) -> None:
        validate_against_pinned_schema(schema_file, _serialized_response(ctx))

`tests/helpers/pinned_schema.py::validate_against_pinned_schema` exists and is called by exactly one
module. Two steps with one phrasing and different rigour is a DRY defect this project treats as a
correctness bug — and the weak one is the one most scenarios would bind to.

**Correction to prior framing.** The blanket claim "`then_response_schema_valid` runs no validator"
is wrong as stated: it is true of the UC-005 copy and false of the UC-018 copy.

**Wiring it will go red** — deliberately, and correctly — on several open production gaps (missing
top-level `status`, advisory `errors` on success envelopes, missing `by_package` required fields,
`cursor: null`, `status: null` on MCP for creatives). Do not soften the step to dodge them; triage
each red result against its production issue instead.

## Blocked BDD scenarios

~30 — every scenario whose storyboard grades `response_schema`.

## Acceptance criteria

- [ ] One registered implementation in a shared plugin module (pytest-bdd 8 resolves per-module, so
      it must be a registered plugin, not an import).
- [ ] The UC-005 copy migrated to it and deleted.
- [ ] Land after the pinned-schema-fixtures refresh (see companion issue), or the validator grades a
      superseded contract.
- [ ] The scenarios it turns red are triaged against their production issues, not worked around.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-02 — Pinned schema fixtures vendored at `04f59d2d5`, behind our own 3.1.1 pin

**Disposition: NEW, with one sub-finding that should be a comment on existing #1753 instead.**
Verified via `gh issue view 1753 --repo prebid/salesagent`: #1753 ("BDD feature files assert ~560
error codes production never emits, and the guard that should catch them is scoped to two use
cases," open) already measures the exact same three-layer error-code drift this item's first table
row cites — its numbers (production `WIRE_STANDARD_CODES`: 41; pinned fixture: 66; AdCP 3.1.1 enum:
92) are the same phenomenon as this sweep's measurement (64 codes vendored vs 92 at 3.1.1; small
count difference likely just measured at different commits). **File the broader schema-staleness
issue below as NEW** (it covers far more than error codes — missing `activation-key.json`, missing
`sponsored-intelligence/`, missing `protocol-envelope.json` refs in several response schemas — none
of which #1753 touches), but add a short comment to #1753 cross-referencing the schema-fixture angle
so the two don't diverge.

**Comment to add to #1753 (`gh issue comment 1753 --repo prebid/salesagent --body-file ...`):**

```
Cross-reference from an AdCP 3.1.1 storyboard re-grounding sweep (branch
test/storyboard-binding-baseline): the same three-layer error-code drift this issue measures
(production 41 / pinned fixture ~64-66 / 3.1.1 enum 92) also affects tests/helpers/pinned_schema.py
and tests/fixtures/adcp_schemas_pinned/enums/error-code.json, which TransportResult.assert_wire_error
(tests/harness/transport.py:164-169) validates against — so any scenario grading one of the 28+
codes 3.1.1 added over the vendored snapshot is silently blocked at the harness layer, not just
under-asserted at the feature-file layer this issue tracks. Filing the broader pinned-schema-fixture
staleness (missing core/activation-key.json, missing sponsored-intelligence/, missing
protocol-envelope.json $refs in several response schemas) as its own issue since it goes well beyond
error codes, but wanted this noted here so the re-vendoring work (whichever issue does it) closes
both gaps in one pass.
```

**NEW draft for the broader schema-fixture staleness** (searched — no existing issue found covering
the non-error-code parts). Target: prebid/salesagent.

**Title:** `Pinned test schema fixtures are vendored behind the repo's own 3.1.1 spec pin`

**Body:**
```
## What is broken

`tests/helpers/pinned_schema.py:5-6` — "pinned at adcontextprotocol/adcp@04f59d2d5 (tag
v3.1-04f59d2d5)". That commit is an **ancestor of v3.1.0-beta.3**, i.e. older than the repo's own
3.1.1 pin. Concrete measured consequences:

| instance | measured |
|---|---|
| `enums/error-code.json` holds **64** codes; 3.1.1 has **92** | verified by `json.load` — `TransportResult.assert_wire_error` (`tests/harness/transport.py:164-169`) rejects any code absent from the snapshot, so it silently blocks any scenario grading one of the 28 codes 3.1.1 added |
| `core/activation-key.json` is **missing** | verified `ls` — `core/deployment.json` `$ref`s it, and `pinned_schema.py:36-40` treats a missing ref as a hard failure |
| no `sponsored-intelligence/` directory | verified `ls` — every SI schema assertion hard-fails the instant UC-014 is wired |
| `signals/activate-signal-response.json` lacks the `protocol-envelope.json` `allOf` entry | the vendored copy silently does not enforce top-level `status` |
| `media-buy/get-products-request.json` lacks the 3.1.1 top-level `allOf` conditional and the whole finalize-exclusivity / multi-finalize contract | any request-level assertion against the pinned tree is weaker than 3.1.1 |
| `creative/list-creative-formats-response.json` lacks the `protocol-envelope` ref | same status-enforcement gap there |

**Not uniformly stale.** The vendored tree already carries some 3.1.1-era files (`core/vendor-metric-value.json`,
`core/reporting-capabilities.json` with `vendor_metrics`, `core/product-filters.json` with
`required_vendor_metrics`) — the blanket "vendored at 04f59d2d5" framing overstates it for some
files. Check per-file before acting.

**Where re-vendoring is free.** Live a2a/mcp/rest `list_creatives` responses validate against the
true v3.1.1 `$ref` closure with 0 errors on all three — the refresh is a no-op risk-wise there and a
real strengthening.

## Acceptance criteria

- [ ] `tests/fixtures/adcp_schemas_pinned/_refresh.py` re-run at `v3.1.1` (`467fd93d7`), closing the
      `$ref` closure (`activation-key.json`, `protocol-envelope.json` + `task-status`/`error`/`context`/`push-notification-config`).
- [ ] SI schemas vendored, or SI schema-shape assertions explicitly recorded as out of scope.
- [ ] The docstring pin string updated.
- [ ] Full BDD suite re-run to find the tools where the refresh is **not** free — that list is the
      real output of this issue.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-03 — 21 BDD feature files have no `scenarios()` binding and are never collected

**Disposition: SPLIT.** For the four files named in an existing issue (BR-UC-001/008/009/010) →
SHARPEN #1594, with a materially worse finding. For the other 17 files → NEW.

**SHARPEN #1594** ("test(bdd): wire the remaining dormant UC-001/UC-008/UC-009/UC-010 scenarios onto
harness envs," open). Verified via `gh issue view 1594` and direct repo inspection
(`grep -rn "scenarios(" tests/bdd/*.py`): #1594's premise — that harness envs (`ProductEnv`,
`SignalsEnv`, `PerformanceEnv`, `CapabilitiesEnv`) exist and cover "the main-flow tag sets only,"
with the remaining scenarios in those four files xfailing at the fixture — describes a state where
the files **are** bound (collected) but only partially wired. **That is no longer true today**: a
direct grep for `scenarios(` across every `tests/bdd/*.py` module finds **zero** bindings for any of
`BR-UC-001`, `BR-UC-007`, `BR-UC-008`, `BR-UC-009`, or `BR-UC-010` — these files are not collected at
all, which is a strictly worse and more foundational problem than "wired for main-flow tags only."
Either #1594 has drifted stale since it was filed, or the binding regressed since. **Comment on
#1594 with this correction rather than filing a new issue for these four files** — the harness envs
it names are still the right target once a `scenarios()` binder is added back.

**Comment to add (`gh issue comment 1594 --repo prebid/salesagent --body-file ...`):**

```
Correction found during an AdCP 3.1.1 storyboard re-grounding sweep (branch
test/storyboard-binding-baseline): as of this sweep, BR-UC-001-discover-available-inventory.feature,
BR-UC-008-manage-audience-signals.feature, BR-UC-009-update-performance-index.feature and
BR-UC-010-discover-seller-capabilities.feature (plus BR-UC-007) have ZERO scenarios() bindings
anywhere in tests/bdd/*.py — grep -rn "scenarios(" tests/bdd/*.py returns no match for any of them.
That's a step below what this issue describes (main-flow tags wired, remainder xfailing at the
fixture) — right now none of the scenarios in these files are collected by pytest-bdd at all, so
they don't even reach the harness fixture to xfail. Worth confirming whether this is a regression
since the issue was filed or whether the issue's premise was already slightly ahead of the code. The
named harness envs (ProductEnv, SignalsEnv, PerformanceEnv, CapabilitiesEnv) are still the right
target once a scenarios() binder exists. Broader context: 21 feature files total have no
scenarios() binding today (~600 scenarios never executed), tracked in the storyboard-conformance
slate at .claude/notes/storyboard-conformance/CONSOLIDATED-ISSUES.md, item T-03.
```

**NEW draft, for the remaining 17 unbound files not covered by #1594** (searched, no existing issue
found: BR-UC-012, 013, 014, 015, 016, 017, 020, 021, 022, 023, 024, 025, 027, 028, 030, 032, and
BR-UC-007 if not folded into the #1594 comment above). Target: prebid/salesagent.

**Title:** `17 BR-UC-*.feature files (beyond the four tracked in #1594) have no scenarios() binding — ~500+ scenarios never execute a line of production code`

**Body:**
```
## What is broken

The full picture, for context (BR-UC-001/007/008/009/010 are tracked separately via a comment on
#1594 — this issue is scoped to the other 17):

Diffing every `BR-UC-*.feature` against every `scenarios("features/…")` call in `tests/bdd/*.py`:

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

**21 files. Roughly 600 scenarios that have never executed a line of production code.** Not xfailed —
never *collected*, so they do not appear in run counts at all, and the BDD structural guards
(no-trivial-assertions, no-pass-steps) never see them because those guards scan step *bodies* and no
bodies exist.

Named instances with size: UC-001 (~40 scenarios, 2000+ lines), UC-008 (1154 lines, ~90 scenarios),
UC-014 (~200 scenarios), UC-020 (1028 lines, ~60 scenarios), UC-021 (966 lines, ~40 scenarios),
UC-030 (582 lines, 45 scenarios).

Six `@storyboard-v3.1` scenarios live in these files and claim conformance grading they cannot
receive. The traceability doc (`docs/test-obligations/bdd-traceability.yaml`) claims traceability
for all of them — a traceability index pointing at dead scenarios is worse than no index.

**Sequencing trap.** Adding a binder without step definitions fails collection wholesale. Bind and
implement together, use-case by use-case, or the file silently re-enters dormancy.

## Acceptance criteria

- [ ] Each of the 21 files gets an explicit decision: bind (with steps), delete, or move to a
      documented `features/unbound/` area so dormancy is visible rather than inferred.
- [ ] A guard fails when a `.feature` file under `tests/bdd/features/` has no `scenarios()` binder —
      this class of defect should never again be discoverable only by hand.
- [ ] Traceability rows for unbound scenarios marked unbound.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-04 — Blanket harness `pytest.xfail` gates make every storyboard scenario dormant and hide missing steps

**Disposition: SHARPEN existing #1740** — corrected after direct verification. `gh issue view 1319`
and `gh issue view 1740 --repo prebid/salesagent` were both read; #1319 (BDD strict-marker debt
umbrella) turned out to be the tracking issue for a *specific, already-enumerated* 16-item list in
`docs/test-debt-bdd-strict-markers.md` (mostly UC-004/005/006 partition-row production gaps) — not a
fit for this finding. **#1740, "BDD conftest: 2,376-line collection hook hides dead and
never-executing xfail routes," is the real match.** It already names the exact root cause: 20+ named
routing registries (`_UC005_E2E_FIXTURE_INJECTION_TAGS`, `_UC003_EXT_XFAILS`, `_UC004_XFAIL_TAGS`,
etc.) are local variables inside a single 2,376-line `pytest_collection_modifyitems` function, so
"nothing can import them, no guard test can read them, no tool can enumerate them." The five blanket
`pytest.xfail()` gates this sweep found are concrete, previously-uncounted instances of exactly that
problem, in the same function.

**What #1740 is currently missing:** it doesn't yet name these five specific gates
(`tests/bdd/conftest.py:3282,3359,3378,3440,3507`), doesn't note that they gate **entire storyboard
scenario collections** (not just individual rows) across UC-002/003/004/006/018 — i.e., they are
plausibly the single highest-value instance of the pattern #1740 already describes — and doesn't
carry the allowlist-inversion fix (build the harness env unconditionally, xfail only named
exceptions) as a concrete remediation shape for this instance.

**Comment to add (`gh issue comment 1740 --repo prebid/salesagent --body-file ...`):**

```
Adding file:line detail on the "every storyboard scenario is dormant" side of this umbrella, found
during an AdCP 3.1.1 storyboard re-grounding sweep on branch `test/storyboard-binding-baseline`.

Five imperative catch-all gates in `tests/bdd/conftest.py` fire at the harness fixture *before any
step runs*:

    :3282   pytest.xfail("UC-002 harness not yet wired for non-extension scenarios")
    :3359   pytest.xfail("UC-003 harness not yet wired for non-extension scenarios (full graduation pending, PR #1567 follow-up)")
    :3378   pytest.xfail("UC-006 harness not yet wired for non-account scenarios")
    :3440   pytest.xfail(f"UC-011 harness not yet wired for markers: {marker_names}")
    :3507   pytest.xfail(f"UC-004 harness not yet wired for type: {harness_type}")

plus a UC-018 gate admitting only `{list-after-sync, concept-id, BR-RULE-034}`.

Measured: 36/36 UC-003 status-partition + boundary variants xfail at fixture setup across a2a/mcp/rest;
all 36 UC-006 provenance scenarios XFAIL; every `@T-UC-002-storyboard-*` tag falls through the UC-002
catch-all.

Four compounding defects worth fixing in the same change as the strict-marker conversion this issue
already tracks:

1. Every `@storyboard-v3.1` scenario in UC-002/003/004/006/018 is dormant. Rewriting Gherkin changes
   nothing without a wiring edit.
2. An imperative `pytest.xfail()` can never xpass, so nothing signals when production catches up —
   the ledger is write-only.
3. A scenario whose steps have no definitions at all is indistinguishable from one that is merely
   un-wired. The blanket branch swallows both; it should assert every step resolves before xfailing,
   so undefined-step scenarios report distinctly.
4. The allowlists are hand-maintained tag sets (e.g. UC-006's is
   `{"account","creative-invariant","BR-RULE-034"}`) — inverting them (build unconditionally, xfail
   only named exceptions) is the structural fix so a newly added scenario grades by default instead
   of silently joining the catch-all.

Also worth closing out under this umbrella: the "UC-003 harness not yet wired... PR #1567
follow-up" gate references a graduation that is itself a prerequisite for several open production
issues (cancellation path, context-echo audit, and an upstream NOT_CANCELLABLE-vs-INVALID_STATE
conflict) having any test teeth at all.
```

**Suggested milestone note:** if this comment leads to substantial rework, consider also tagging the
resulting PR(s) with milestone "Storyboard Compliance" (#2) in prebid/salesagent alongside whatever
milestone #1319 already carries, since the fix directly unblocks the storyboard sweep.

---

### T-05 — `@source` footers: 16 off-by-one, 40 stale refs, 10 absent, no `phase=`/`step=` grammar

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `@source footers on storyboard-bound scenarios: 16 off-by-one, all 40 pinned behind our own spec pin, 10 missing, no phase=/step= grammar`

**Body:**
```
## What is broken — four separable defects

**a — systematic off-by-one.** The generator that emitted `@source` footers pointed each scenario at
the *next* scenario's storyboard. 16 confirmed mechanically. Example: a UC-002 run cites
`governance_denied_recovery.yaml` where `governance_denied` should be cited, and the citations shift
one position down the block for `inventory_list_no_match`, `inventory_list_targeting`,
`measurement_terms_rejected`, `pending_creatives_to_start`. Similar shifts in UC-004, UC-006, UC-003.
**Fix at the generator, not scenario by scenario.**

**b — every footer is pinned behind our own pin.** All 40 read `ref=v3.1-04f59d2d5
commit=04f59d2d5`, an ancestor of `v3.1.0-beta.3` and therefore *older* than the repo's 3.1.1 pin.
Re-pin to `v3.1.1` / `467fd93d7`.

**c — 10 scenarios have no footer at all**: UC-001 refine, UC-002 pending, UC-003 creative-fate,
UC-004 vendor-metric, UC-006 reception, UC-008 platform-dest, UC-014 session, UC-019 status-poll,
UC-020 VAST, UC-021 preview.

**d — the grammar cannot express the graded unit, which is why (a) went undetected.** The graded
unit is a *step inside a phase*, and footers carry only `path=`. Without `phase=` / `step=`, an
off-by-one path swap is invisible to inspection. The convention already documents
`@source repo=<repo> ref=<ref> [phase=<phase>] path=<path>[#L..]` — a checker should require and
verify both.

**e — a distinct variant in UC-014.** At least six scenarios all carry the same
`sponsored-intelligence/si-get-offering-request.json` path regardless of which call they exercise —
a single copy-pasted path rather than a shift.

**Also unresolved and worth settling once:** `domains/` vs `protocols/` tier naming in citations —
the two trees are byte-identical at 3.1.1, so this is cosmetic, folded into this issue's "Done when"
rather than filed separately.

## Acceptance criteria

- [ ] Generator fixed so footers cannot shift.
- [ ] All 40 footers re-pinned to `v3.1.1`, with `phase=` and `step=`.
- [ ] The 10 missing footers added.
- [ ] A lint added: the footer's `path=` must name a file that exists at the pinned `ref`, and where
      a scenario carries a `# <storyboard_id>: …` summary line, the two must name the same
      storyboard.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-06 — No BDD step asserts `context` / `context.correlation_id` echo anywhere

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `No BDD step asserts context/correlation_id echo — graded on nearly every storyboard phase and entirely untested`

**Body:**
```
## What is missing

`grep -rn "correlation_id" tests/bdd/steps/` → **zero hits.** The context echo is graded in
essentially every 3.1.1 storyboard, on every phase, on both success and error paths — and in several
cases it is the **only** thing graded on the step.

Scenarios that *assert* it in Gherkin but have no step definition, so they auto-xfail:
`BR-UC-003:2050,2065,2083`, `BR-UC-007:258,275,283,428,528`, `BR-UC-009:174,175,196,560`,
`BR-UC-011:449,461`, `BR-UC-012:348,364`, `BR-UC-016:712,719`.

## Spec mandate (3.1.1)

`core/protocol-envelope.json` → `context`: "echoed unchanged in the response … MUST preserve
byte-for-byte." Graded at (non-exhaustive) `create_media_buy_async.yaml:231-237`,
`inventory_list_no_match.yaml:141-148`, `invalid_transitions.yaml:283-289`,
`governance_denied_recovery.yaml:231-234`, `measurement_terms_rejected.yaml:136-142`,
`provenance_enforcement.yaml` (all six phases), `protocols/creative/index.yaml:237-243`,
`protocols/media-buy/index.yaml` `list_formats` + `sync_creatives`.

**One step definition retires a large dormant surface.** Belongs in
`tests/bdd/steps/generic/then_payload.py`, must read the **wire**
(`ctx["wire_response"]` / `result.wire_error_envelope`), and needs a companion Given that puts a
`correlation_id` on the request — several scenarios currently assert an echo they never seeded.

**Prerequisite check.** Confirm per tool whether `context` survives on all four transports before
writing assertions — several open production/harness issues (raise-site context gaps, REST body
models missing `context`, harness `build_rest_body` dropping fields) each break a different tool
first.

## Acceptance criteria

- [ ] One generic Given (`the request carries context correlation_id "<id>"`) and one generic
      wire-reading Then.
- [ ] Applied to the success, error and submitted branches of at least `create_media_buy`,
      `update_media_buy`, `sync_creatives`, `list_creatives`, `list_creative_formats`,
      `get_media_buys`.
- [ ] The dormant scenarios listed above wired onto it.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-07 — `storyboard_binding_sweep.py` has two false-negative classes and mis-triaged UC-008

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `storyboard_binding_sweep.py has two false-negative classes and mis-triaged UC-008 as bucket B instead of C`

**Body:**
```
## What is broken

**a — tier derived from path prefix, so specialism gating is invisible.**
`scripts/audit/storyboard_binding_sweep.py:253` sets `source["tier"]` from the path prefix and only
reports an undeclared-specialism finding when `tier == "specialisms"` (line 266).
`governance_conditions.yaml` lives under `protocols/media-buy/scenarios/` but is required **only**
by `specialisms/governance-aware-seller/index.yaml:23-28`, so the sweep classifies it `protocols` and
reports no gate finding. Same false negative on all four `governance_*` scenarios. **Fix:** resolve
the gate by scanning every `index.yaml` `requires_scenarios:` for the scenario's `id:`, not by path
prefix.

**b — `phase_is_graded()` truncates phase-anchored windows.**
`storyboard_binding_sweep.py:133-148` truncates its window at the next `\n      - id: ` (6-space step
indent). Anchored on a *phase* id (2-space indent), the window stops at the phase's first step and
never reaches `validations:`, so a genuinely graded phase reports "prose" and lands in the wrong
bucket. Reproduce with `phase=verify_creative_persists_post_cancel` on
`creative_fate_after_cancellation.yaml`. **Fix:** indent-aware window, or search to the next sibling
id at the same indent level.

**c — concrete mis-triage.** `docs/test-obligations/storyboard-binding-baseline.md:38-40` marks
`T-UC-008-storyboard-activate-agent-destination` and `T-UC-008-storyboard-baseline-end-to-end` as
bucket B ("stale ref only"). Both are bucket C: the cited `protocols/signals/index.yaml` has exactly
two phases and grades no activation at all, and the real binding sits behind two undeclared gates.

**d — an open question the sweep cannot answer and should record.** Whether the compliance runner
gates protocol-tier baselines on `supported_protocols` alone, or by specialism (a comment in
`src/core/tools/capabilities.py:256-259` asserts the latter). This flips the verdict on the
`measurement_terms_rejected` and `universal/pagination-integrity.yaml` gating questions raised
elsewhere in the sweep. Worth resolving upstream once.

## Acceptance criteria

- [ ] Gate resolution by `requires_scenarios` membership, not path prefix.
- [ ] Indent-aware `phase_is_graded()`.
- [ ] The baseline regenerated; UC-008 rows move to bucket C.
- [ ] Footer verification requires `phase=`/`step=` (companion `@source` footer issue).

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-08 — Test harness silently drops spec-required fields, masking transport divergence

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `Harness allowlists (_WRAPPER_UNSUPPORTED_FIELDS, build_rest_body) silently drop spec-required fields, masking real transport divergence`

**Body:**
```
## What is broken — two undeclared allowlists

    # tests/harness/media_buy_update.py:49-60
    _WRAPPER_UNSUPPORTED_FIELDS = (
        "account", "adcp_major_version", "canceled", "cancellation_reason",
        "invoice_recipient", "new_packages", "proposal_id", "revision", "today", "total_budget",
    )

Popped from the payload before the A2A/MCP wrapper call "so the flat-kwargs call doesn't fail on
unexpected keyword arguments". The REST path (`_build_update_rest_body`) does **not** pop them. Net
effect: the harness makes A2A/MCP look like they accept fields they drop, while REST fails
differently — so **no test can ever observe the real divergence**. Every entry is a field the 3.1.1
request schema declares and our wrappers silently discard.

    # tests/harness/creative_list.py:86-98
    def build_rest_body(self, **kwargs):
        body = {}
        for key in ("media_buy_id", "media_buy_ids", "status", "format"):
            ...
        filters = kwargs.get("filters")
        ...

Whitelists four keys plus `filters`; silently discards everything else, including `context`. Probed
live: a2a and mcp echo `{"correlation_id": "creative_lifecycle--list_all"}`; rest returns
`context: null`. **Production is not at fault here** — `src/routes/api_v1.py:456` threads
`context=to_context_object(body.context)` into `list_creatives_raw` and `listing.py:451` sets
`context=req.context`. This is a pure harness defect masquerading as a production gap, and it is the
source of a previously-circulated (and inaccurate) claim that "REST drops context" for this tool.

## Acceptance criteria

- [ ] `_WRAPPER_UNSUPPORTED_FIELDS` shrinks to empty as the corresponding production issues (cancel
      path, idempotency-key enforcement, REST body model completeness) land; it is an undeclared
      allowlist and should be tracked as one (allowlists may only shrink).
- [ ] `build_rest_body` forwards everything, or at minimum `context`, `pagination`, `sort`, `account`.
- [ ] A guard added: any harness field-stripping must be declared, justified, and shrinking.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-09 — UC-006 per-creative error codes are inferred from message substrings, not read off the wire

**Disposition: SHARPEN existing #1590** — corrected after direct verification
(`gh issue view 1590 --repo prebid/salesagent`). #1590, "Unify BDD error/wire assertion in one
harness primitive (kill `_WIRE_ASSERTED_FIELDS` staged migration)," names the exact root cause this
finding is an instance of, verbatim: "the recurring 'assertion is on the reconstructed exception, not
the wire envelope' finding is not a per-scenario oversight — it is a harness-design defect... each
place hand-rolls its own escape (a per-field allowlist, a legacy reconstructed-error branch, a
bespoke helper)." **Do not file a new issue — this is another concrete instance for that issue's
"concrete instances" list.** Related, broader context: #1773 ("test: eliminate the three invisibility
patterns") and #1778 ("BDD success-path oracles grade the reconstructed typed payload, not the wire")
are siblings of #1590 covering the same underlying defect class on the success-path side and at a
taxonomy level — worth being aware of but #1590 is the tightest fit for this specific UC-006 finding
since it already frames the fix as "a single harness/environment primitive" rather than a
per-use-case patch.

**What #1590 is missing that this sweep adds:** the specific UC-006 instance — `_infer_error_code_from_message`
(`tests/bdd/steps/domain/uc006_sync_creatives.py:2132-2143`) invents codes not in the 3.1.1 enum
(`CREATIVE_VALIDATION_FAILED`, `CREATIVE_NAME_EMPTY`, …) and `_assert_per_creative_failure`
(`:1484-1514`) xfails on mismatch against the reconstruction rather than reading
`creatives[0].errors[0].code` off the wire — plus concrete proof the reconstruction is lossy
(measured `error.context is None` on the reconstructed object while the wire envelope carries
`context.correlation_id` correctly for the same request). Branch
`test/storyboard-binding-baseline` citation.

**Comment to add (`gh issue comment 1590 --repo prebid/salesagent --body-file ...`):**

**Body (reuse as the comment):**

**Title:** `UC-006 per-creative error assertions infer error codes from message text instead of reading creatives[0].errors[0].code off the wire`

**Body:**
```
## What is broken

`tests/bdd/steps/domain/uc006_sync_creatives.py:2132-2143` (`_infer_error_code_from_message`) maps
message **text** to invented codes (`CREATIVE_VALIDATION_FAILED`, `CREATIVE_NAME_EMPTY`, …) that are
not in the 3.1.1 enum. `_promote_creative_errors_to_ctx` (`:2100-2129`) feeds that synthetic object
to the generic `the error code should be "{code}"` step, and `_assert_per_creative_failure`
(`:1484-1514`) **xfails** on mismatch.

So every per-creative error assertion in UC-006 asserts a *reconstruction*, and
`creatives[0].errors[0].code` — the field the storyboard actually grades — is never read.

## Why this matters

Project convention (error verification policy) requires new error-path tests to assert on the wire
envelope; the reconstruction is lossy, and the guard that should catch reconstructed assertions
(`test_architecture_bdd_wire_discipline.py`'s allowlist) is empty by design — zero tolerance — so
this code appears to predate or evade the guard.

**Concrete proof the reconstruction is lossy:** a separate probe measured that the reconstructed
exception object carries `error.context is None` on a2a/mcp/rest while the wire envelope carries
`context.correlation_id` correctly. A reconstructed-object assertion would have declared a
production gap that does not exist.

**Related, same class:** `tests/bdd/steps/generic/then_error.py:270` falls back to the reconstructed
`ctx["error"]` when no wire envelope is present, and `:413-423` (`the error recovery should be …`)
reads the reconstructed object. Both are weaker than they look.

## Acceptance criteria

- [ ] `_infer_error_code_from_message` deleted; per-creative assertions read
      `creatives[0].errors[0].code` off the wire.
- [ ] The invented codes purged.
- [ ] `then_error.py`'s reconstruction fallbacks hardened or removed, and the wire-discipline guard
      extended to cover UC-006.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-10 — No harness env can drive two tools in one scenario; every create→read chain is ungraded

**Disposition:** NEW. Target: prebid/salesagent. (One footnote below also feeds the #1739 SHARPEN
comment — see §1.)

**Title:** `No BDD harness env can dispatch two different tools in one scenario — every create→read chain in the storyboards is ungraded`

**Body:**
```
## What is broken

Each harness env binds one tool (`CreativeListEnv` → `list_creatives`). `MediaBuyDualEnv` is the sole
exception and sniffs create-vs-update by request type — both on the media-buy surface. Conftest
routing is per-use-case, so **one scenario gets one env**.

Consequences, each blocking a different storyboard chain:

| chain the storyboard grades | why we cannot |
|---|---|
| `create_media_buy` → `get_media_buys` on the returned id (`field_equals_context media_buys[0].media_buy_id == $context.media_buy_id`) | UC-019 binds `MediaBuyListEnv` unconditionally; `MediaBuyDualEnv` is create+update only |
| create → `get_media_buys` readback of `packages[0].targeting_overlay.property_list.list_id` | `MediaBuyCreateEnv` dispatches create only |
| `get_products` (required_metrics) → create → delivery (missing_metrics) | UC-004 routes to `DeliveryPollEnv`; `ProductEnv` reachable only from the get-products use case |
| `get_products` vendor_metrics echo → delivery `vendor_metric_values` | same routing wall |
| `get_products` → `sync_creatives` format_id provenance | no env can dispatch a different tool over the scenario's transport |
| `create → sync_creatives → list_creatives → update(cancel) → list_creatives → create → sync` | a five-phase four-tool walk |

**Also.** UC-018's `list_creatives` steps are module-local and that module is absent from
`pytest_plugins`, so no other feature can reuse them — the next scenario needing `list_creatives`
will copy-paste and trip the no-duplicate-steps guard.

**Footnote (feeds #1739):** the workaround some proposals used to avoid needing a second tool
dispatch — sourcing an "advertised format" value from a fixture instead of a live cross-tool call —
is the same in-process-capture pattern already tracked on #1739; see the SHARPEN comment for that
issue.

## Acceptance criteria

- [ ] A composite env pattern (e.g. `MediaBuyCreateListEnv`) with conftest branches keyed off
      storyboard tags.
- [ ] Reusable `list_creatives` steps lifted into `tests/bdd/steps/domain/` and registered as a
      plugin.
- [ ] The create→read assertions currently reaching into the DB re-pointed at the wire.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-11 — Step-definition defects: duplication, over-broad parsers, mis-attributed assertions, dead code

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `Nine step-definition defects: duplicated helpers, an over-broad parser, mis-attributed assertions, and dead code in BDD step files`

**Body:**
```
## Nine small, independently fixable defects, grouped because each is a one-file change

1. **`_submitted_wire_dict` duplicates `wire_dict`.**
   `tests/bdd/steps/domain/uc003_update_media_buy.py:1135-1154` is a line-for-line re-implementation
   of `tests/bdd/steps/_outcome_helpers.py:43-59` — same guard, same IMPL fallback, same docstring
   argument. Delete the UC-003 copy, import the shared helper (DRY).
2. **`the error details should include {key} {value}` is too loosely parsed.**
   `tests/bdd/steps/generic/then_error.py:760` accepts free prose as `{key} {value}`, which is how a
   sentence ending in two arbitrary words "matched" a step at all. Tighten to the quoted-key form
   (the `:775` variant already quotes the value) and re-audit call sites.
3. **`the response should NOT contain "{field}" field` is submitted-envelope-specific but reads
   generic.** `uc003_update_media_buy.py:1197-1221` unconditionally calls
   `_assert_a2a_submitted_task_has_no_artifacts(ctx)` — right for `CreateMediaBuySubmitted`, wrong
   for any synchronous success. Split into a submitted-envelope variant and a plain wire-absence
   variant.
4. **`then_dual_emit_media_buy_status` asserts set membership, not values.**
   `uc002_create_media_buy.py:1724-1773` checks membership in the full enum set — it would pass on
   `media_buy_status: "canceled"` regardless of what the storyboard actually requires. Migrate
   callers to the value-pinning steps (`uc003_update_media_buy.py:127,137`).
5. **`then("the creative should be flagged for review")` mis-attributes its assertion.**
   `uc006_sync_creatives.py:3839-3846` asserts `creative.status == "pending_review"` with the
   docstring "flagged for review due to missing provenance." The status actually comes from
   `approval_mode = require-human` and holds identically when provenance is **present**. It tests the
   approval-mode default, not provenance enforcement.
6. **`given_creative_with_provenance_source_type` is not e2e-safe.**
   `uc006_sync_creatives.py:3684-3700` hard-codes a format id and a fixed creative id instead of the
   e2e-aware helper already used elsewhere in the file, so two outline rows collide if the DB scope
   is widened past per-test.
7. **`a creative with provenance metadata` builds a payload `adcp==6.6.0` rejects.**
   `uc006_sync_creatives.py:2707-2717` emits a `disclosure` as a bare string, which the library
   rejects (`model_type` error), routing every scenario using this Given through a failed sync — a
   different code path than the one it claims to test. Blocked on the Provenance schema-inheritance
   production fix; re-check what those scenarios were actually claiming once that lands.
8. **`_make_governance_agent` is dead code that always raises.**
   `tests/bdd/steps/domain/uc011_accounts.py:91-108` constructs `GovernanceAgent(url=…,
   categories=…)`; the model has no `categories` field and is `extra="forbid"`. Its only caller
   always passes `categories`, so the step can only ever land in `ctx["error"]`, and it is
   referenced by no feature file. Delete or repair.
9. **The stale xfail at `uc011_accounts.py:2194-2201`.** Covered as part of the #1319 SHARPEN
   comment and the raise-site-context-echo production issue — do not fix twice, coordinate.

## Acceptance criteria

- [ ] All nine fixed (each is small and independently verifiable).

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### T-12 — UC-019 harness: deprecated MCP wrapper, `REST_ENDPOINT` points at a nonexistent route

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `UC-019 harness uses a deprecated MCP wrapper (bypasses middleware) and a REST_ENDPOINT that doesn't exist — get_media_buys never exercised on REST/e2e_rest`

**Body:**
```
## What is broken

**a.** `tests/harness/media_buy_list.py:56-60` uses `_run_mcp_wrapper`
(`tests/harness/_base.py:851-889`), whose own docstring says it "bypasses FastMCP middleware and
TypeAdapter validation" and which stashes no `wire_response`. So `ctx["wire_response"]` is `None` on
MCP for **every** UC-019 scenario (~80 Then steps), and every MCP assertion runs against a typed
model whose fields are already coerced. Migrate to `_run_mcp_client`.

**b.** `tests/harness/media_buy_list.py:26` declares
`REST_ENDPOINT = "/api/v1/media-buys/query"`. `src/routes/api_v1.py` registers only
`POST /media-buys` (302), `PUT /media-buys/{media_buy_id}` (344), `POST /media-buys/delivery` (377).
`conftest.py:2831` works around it via `_NO_REST_UC_TAG_PREFIXES = ("T-UC-019-",)`, excluding UC-019
from `rest` and `e2e_rest` entirely. `get_media_buys` is a **required tool** on the media-buy track,
so one third of our transports never exercise it. Either add the route or delete the dead constant —
but the missing route is itself a conformance question, not purely a test-infra one.

## Acceptance criteria

- [ ] Migrate the UC-019 MCP harness to `_run_mcp_client`.
- [ ] Add the REST `get_media_buys` route, or explicitly decide `get_media_buys` is REST-unreachable
      and record why (given it is a required tool, this needs a product decision, not a silent
      workaround).

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

## 4. SCENARIO items (S-01 .. S-03)

### S-01 — 19 scenarios claim `@storyboard-v3.1` grading that does not apply to us

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `19 scenarios carry @storyboard-v3.1 for storyboards gated behind capabilities/specialisms we don't declare — retag @schema-v3.1`

**Body:**
```
## What is broken

Nineteen scenarios carry `@storyboard-v3.1`, which asserts conformance grading against a 3.1.1
storyboard. For each, either the storyboard is gated behind something we do not declare, or the
specific behaviour is narrative/expected prose with no `validations:` entry — often both. Action:
retag `@storyboard-v3.1` → `@schema-v3.1`, preserving the opaque `@T-…` identifier (all are
referenced from `docs/test-obligations/bdd-traceability.yaml`, and a bidirectional-mapping guard
enforces the identifier).

| scenario | gate that closes |
|---|---|
| `T-UC-001-storyboard-proposal-finalize-action` | `media_buy.supports_proposals` undeclared |
| `T-UC-001-storyboard-finalize-uses-refine-vocabulary` | same |
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

**Caveat worth stating plainly.** `@schema-v3.1` vs `@storyboard-v3.1` has no written definition
anywhere in the repo outside `.feature` files. The retag is inferred from usage; document the
vocabulary as part of this change.

## Acceptance criteria

- [ ] 19 tags changed, identifiers untouched.
- [ ] The tag vocabulary written down (a doc or a guard, not tribal knowledge).
- [ ] `storyboard_binding_sweep.py` re-run to confirm the 19 leave the storyboard bucket (depends on
      the sweep-tool false-negative fixes).
- [ ] Note: several of these become `@storyboard-v3.1` again if the capability-declaration decisions
      go the other way — record the coupling in the PR description.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### S-02 — Scenarios asserting values production never emits or the spec never defined

**Disposition:** NEW (item 3 below also feeds the #1319 SHARPEN comment — see §1).

**Title:** `Ten scenario-level defects that will fail the moment their gate is wired — each needs a decision, not a mechanical fix`

**Body:**
```
## What is broken

1. **`T-UC-002-partition-approval-workflow` asserts a status production stopped emitting.**
   `_assert_workflow_outcome` (`uc002_create_media_buy.py:1105-1109`) requires
   `status == "pending_approval"`. Production now returns `CreateMediaBuySubmitted` with
   `status="submitted"` for the manual-approval branch, and `pending_approval` is **not a member** of
   the 3.1.1 `MediaBuyStatus` enum. Invisible only because of the blanket xfail gates (see the
   companion harness-dormancy issue); wiring flips it red.
2. **`@T-UC-002-v31-submitted-envelope-shape` is permanently dormant and duplicates live coverage.**
   Uses phrasings that exist nowhere in `tests/bdd/steps/`; its content is a subset of
   `@T-UC-002-alt-manual`. Retire it or re-point it — do not wire a third copy.
3. **`@T-UC-002-ext-k` asserts `BUDGET_TOO_LOW` where production correctly emits `BUDGET_EXCEEDED`.**
   Both codes exist at 3.1.1; the generated feature is stale, not production. (This item is also
   being raised as a comment on #1319 — coordinate so it isn't fixed twice.)
4. **`T-UC-003-partition/boundary-media-buy-status` and `T-UC-003-ext-v` already cover the re-cancel
   obligation**, making `T-UC-003-storyboard-not-cancellable-on-recancel` a third copy — its own
   prose claims it is "distinct," which is false as written.
5. **UC-021 siblings contradict the pinned schema.** Assert `expires_at` is always present — 3.1.1
   marks it optional; assert every render has `preview_url` — the schema requires it only on the
   `url`/`both` branches; use "the response may include …" as Then steps, which cannot assert and
   will trip the no-pass-steps guard.
6. **UC-005 sibling "Discover filtered format catalog" filters on `type`**, a property
   `list-creative-formats-request.json` no longer defines at 3.1.1 (production already no-ops it).
7. **`@T-UC-030-bva-url` expects `URL_NOT_HTTPS`** and will fail whenever `BR-UC-030` is wired,
   because of the GovernanceAgent URL-pattern gap.
8. **Four wired UC-002 `plan_id` scenarios** have zero step definitions for any of their four
   phrasings, so all four are silently auto-xfailed.
9. **`@T-UC-006-storyboard-format-id-roundtrip-on-sync` and `-creative-reception-stateful-render`
   collide** on the same storyboard file — an off-by-one footer citation.
10. **`T-UC-005-storyboard-format-id-third-party-agent-out-of-scope` asserts the runner's grading
    policy, not seller behaviour.** No seller behavior can falsify it as written; every assertion in
    the scenario is negative, so a seller returning `formats: []` for every request passes it
    unchanged. Needs a positive control, and the vacuous Then should be deleted (the gradeable half —
    "MUST NOT fabricate a local format entry" — is worth keeping).

## Acceptance criteria

- [ ] Each of the 10 items resolved with an explicit decision recorded (retag, retire, re-point,
      strengthen, or accept as a genuine gap), not silently patched to pass.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### S-03 — `provenance_enforcement` phase 4 (`PROVENANCE_VERIFIER_NOT_ACCEPTED`) has no scenario at all

**Disposition:** NEW. Target: prebid/salesagent.

**Title:** `provenance_enforcement phase 4 (reject_off_list_verifier / PROVENANCE_VERIFIER_NOT_ACCEPTED) has no BDD scenario at all`

**Body:**
```
## What is broken

`BR-UC-006-sync-creatives.feature` has scenarios for `provenance_enforcement` phases 2, 3, 5 and 6 —
and **none** for phase 4, `reject_off_list_verifier`
(`dist/compliance/3.1.1/protocols/media-buy/scenarios/provenance_enforcement.yaml:277-363`). That is
the phase whose narrative states the seller "MUST cross-check the URL before any outbound call […]
closing the buyer-controlled-URL trust gap" — the security-relevant member of the family, entirely
uncovered on both the test side and the production side (see the companion
`provenance_requirements`/`accepted_verifiers` production issue).

## Acceptance criteria

- [ ] A scenario added (dormant until the production enforcement lands) with a matching
      `docs/test-obligations/bdd-traceability.yaml` entry alongside the existing five.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

## 5. UPSTREAM items (U-01 .. U-05)

These five target **adcontextprotocol/adcp**, not prebid/salesagent — the defect is in the spec or
storyboard prose itself, not our implementation. That repo has no "Storyboard Compliance" milestone,
so the primary draft below carries no milestone flag. A short companion tracking issue in
prebid/salesagent (with the milestone and branch reference) is included for each, so the dependency
stays visible on our own board while the upstream question is open.

### U-01 — Storyboards name error codes that do not exist in `error-code.json`

**Disposition:** NEW-UPSTREAM. Target: adcontextprotocol/adcp.

**Upstream title:** `inventory_list_no_match storyboard names INSUFFICIENT_INVENTORY / INVALID_TARGETING, neither of which exists in error-code.json`

**Upstream body:**
```
`dist/compliance/3.1.1/protocols/media-buy/scenarios/inventory_list_no_match.yaml:17` and
`:110-112` tell sellers to reject with INSUFFICIENT_INVENTORY or INVALID_TARGETING. Neither exists
in `git show v3.1.1:static/schemas/source/enums/error-code.json` (92 entries; nothing matching
`*INVENT*`, and the only `*TARGET*` entry is SIGNAL_TARGETING_INCOMPATIBLE). Still present unchanged
at 3.1.8.

This also explains why at least one implementer's scenario substituted PRODUCT_UNAVAILABLE /
INVALID_REQUEST instead — an ungrounded guess to work around the gap, and not what a real seller
implementation emits either.

Requesting either: add the named codes to the error-code enum, or rewrite the storyboard prose to
name enum members that actually exist (PRODUCT_UNAVAILABLE looks like the natural fit for the
no-match case). Until resolved, no conformant seller can assert either named code, which makes this
storyboard step unimplementable as written.
```

**Companion tracking issue (prebid/salesagent, milestone "Storyboard Compliance"):**

**Title:** `Track upstream: inventory_list_no_match names error codes absent from error-code.json`

**Body:**
```
Filed upstream at adcontextprotocol/adcp: [link once created]. Our `inventory_list_no_match` BDD
scenario cannot correctly assert a named error code until this is resolved upstream — do not
hardcode INSUFFICIENT_INVENTORY or INVALID_TARGETING locally in the meantime.

Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### U-02 — Storyboard prose names fields and enum members no 3.1.1 schema defines

**Disposition:** NEW-UPSTREAM. Target: adcontextprotocol/adcp.

**Upstream title:** `Four storyboard "expected:" prose blocks invent vocabulary (render_dimensions, "accepted" creative status, is_live/activation_key guarantee, source discriminator name) not defined by any 3.1.1 schema`

**Upstream body:**
```
Four instances of the same failure mode: `expected:` prose invents vocabulary, an implementer copies
it straight into an assertion, and it can never pass because no schema defines the term.

1. `protocols/creative/index.yaml:318` — "render_dimensions: matches the 300x250 format." No 3.1.1
   schema and no generated SDK type defines `render_dimensions`; the real field is `dimensions`,
   nested at `previews[i].renders[j].dimensions`, and optional. Line `:319`'s "status: preview
   available" is likewise not a member of `enums/task-status.json`.
2. `protocols/creative/index.yaml:152` and `protocols/media-buy/index.yaml:691` both write
   "Per-creative status: accepted, pending_review, or rejected." `enums/creative-status.json` has no
   `accepted` member (the enum is `processing, pending_review, approved, suspended, rejected,
   archived`).
3. `specialisms/signal-marketplace/index.yaml` `activate_on_agent` `expected:` (388-394) promises
   `is_live: true` and an `activation_key` with `type: "key_value"` on every agent activation, but
   `core/deployment.json` makes `activation_key` optional and conditional ("Only present if
   is_live=true AND requester has access to this deployment") and `core/activation-key.json` permits
   either discriminator. Not a schema obligation and not gradeable as written.
4. `protocols/signals/index.yaml:137` describes the source discriminator as "(agent_native or
   data_provider)"; `core/signal-id.json` defines the enum as `catalog | agent`.

Requesting: either the schema is corrected to match the prose's intent, or the prose is corrected to
use the actual defined vocabulary. Implementers reading only the narrative (which is how these
scenarios are usually authored) will reproduce the same wrong assertion every time.
```

**Companion tracking issue (prebid/salesagent, milestone "Storyboard Compliance"):**

**Title:** `Track upstream: four storyboard prose blocks name undefined vocabulary — do not encode locally`

**Body:**
```
Filed upstream at adcontextprotocol/adcp: [link once created]. Do not write local BDD assertions
against `render_dimensions`, creative status `accepted`, a guaranteed `is_live`/`activation_key` pair,
or the `agent_native`/`data_provider` source discriminator names — none of these exist in the pinned
3.1.1 schemas. Use the real field names (`dimensions`, the real `creative-status` enum, the
conditional `activation_key`, `catalog`/`agent`) until upstream resolves the prose.

Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### U-03 — `NOT_CANCELLABLE` hard-graded by the storyboard, `MAY` in the schema

**Disposition:** NEW-UPSTREAM (primary), plus a small SHARPEN contribution to #1319 (the beads-id
FIXME cleanup — already included in that comment, see §1). Target: adcontextprotocol/adcp for the
primary conflict.

**Upstream title:** `invalid_transitions storyboard hard-grades NOT_CANCELLABLE for a re-cancel, but update-media-buy-request.json only says sellers MAY use it — INVALID_STATE is equally schema-conformant`

**Upstream body:**
```
A genuine storyboard-vs-schema conflict, not (as far as we can tell) an implementation bug on our
side.

Storyboard: `dist/compliance/3.1.1/.../invalid_transitions.yaml:279-282` grades
`check: error_code, value: "NOT_CANCELLABLE"` as a hard pass/fail. Corroborated by
`protocols/media-buy/state-machine.yaml:474-495`, which grades the same NOT_CANCELLABLE-over-
INVALID_STATE precedence.

Schema: `update-media-buy-request.json` `canceled.description` says sellers MAY reject with
NOT_CANCELLABLE; `core/error.json` makes `code` an open string with `enums/error-code.json`
explicitly documentary; and INVALID_STATE's own enumDescription names this exact situation —
"updating a completed or canceled media buy." Both codes carry identical
`recovery: "correctable"`, which `error.json` calls the authoritative carrier for client behavior.

Our seller implementation emits INVALID_STATE for a re-cancel. Under a schema-is-authoritative
reading, that is conformant, yet the storyboard's hard `check:` fails us for not returning
NOT_CANCELLABLE specifically.

Requesting a decision: either the storyboard should accept either code (matching the schema's MAY),
or the schema should be tightened to require NOT_CANCELLABLE specifically for this transition (in
which case the schema text should say MUST, not MAY, and INVALID_STATE's enumDescription should stop
naming this exact scenario as its own use case).
```

**Companion tracking issue (prebid/salesagent, milestone "Storyboard Compliance"):**

**Title:** `Track upstream: NOT_CANCELLABLE vs INVALID_STATE conflict blocks the re-cancel storyboard scenario`

**Body:**
```
Filed upstream at adcontextprotocol/adcp: [link once created]. Do not change production's
INVALID_STATE emission for a re-cancel until the upstream conflict is resolved — under this
project's schema-wins authority order, our current behavior is conformant.

Drive-by cleanup while looking at this: the existing FIXME at `tests/bdd/conftest.py:736-753` cites
an internal beads task ID (`salesagent-gh8p.13`) rather than a GitHub issue number, which does not
resolve for outside contributors. On direct verification (`gh issue view 1767 --repo
prebid/salesagent`), there is already an open issue for exactly this class of problem — "63 internal
beads-task IDs in src/ comments, unresolvable by external contributors" — but its own measurement is
scoped to `src/` (63 occurrences across 28 files); `tests/bdd/conftest.py` sits outside that scope.
Recommend a short comment on #1767 noting this `tests/` instance and suggesting the scan be widened,
rather than a new issue. Replace the FIXME with this tracking issue's number once filed.

Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### U-04 — Storyboards grade less than their own schemas require

**Disposition:** NEW-UPSTREAM. Target: adcontextprotocol/adcp.

**Upstream title:** `Four storyboard steps grade less than their own referenced schemas require (SI session_id continuity, inventory_list_no_match narrative, provenance field/recovery, list_formats_integrity third-party proxy tension)`

**Upstream body:**
```
Four "the runner cannot catch this" gaps, proposed as additions to `validations:` blocks.

1. SI session continuity is ungraded. `protocols/sponsored-intelligence/index.yaml:210-220`
   (si_send_message) and `:246-256` (si_terminate_session) contain no `session_id` check of any kind,
   while `si-send-message-response.json` and `si-terminate-session-response.json` both carry
   `required: ["session_id", …]`. An agent can fabricate a fresh `session_id` per response and pass
   the baseline. Proposing `field_value` checks bound to `$context.session_id` on both later steps.
2. `inventory_list_no_match`'s graded surface is context-echo only. Its narrative describes three
   named failure modes (crash, misleading forecast, silent drop) and grades none of them.
3. `provenance_enforcement` phases promise `field` + `recovery: correctable` in prose (`:386-388`)
   and grade neither.
4. `list_formats_integrity` has an internal tension: `:356-359` states an unconditional MUST that
   explicitly includes the third-party case ("whether it hosts that format directly or proxies to
   the creative agent named in format_ids[0].agent_url"), while `creative_sync/list_formats`
   `refs_resolve` (`:655-658`) says third-party refs are unverifiable and downgraded to observations.
   Two checks in two phases pull opposite directions on the same input, and the schemas are silent on
   any obligation to proxy — `list-creative-formats-response.json` never requires resolving foreign
   references and explicitly permits an empty `formats`.

Requesting these be considered for tightened `validations:` blocks, or an explicit statement that
they are intentionally left as narrative-only observations.
```

**Companion tracking issue (prebid/salesagent, milestone "Storyboard Compliance"):**

**Title:** `Track upstream: four storyboard steps grade less than their own schemas require`

**Body:**
```
Filed upstream at adcontextprotocol/adcp: [link once created]. No local action required unless
upstream tightens these — recorded so a future storyboard refresh doesn't silently start grading
something we haven't implemented (SI session continuity in particular).

Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

### U-05 — `ask` semantics under `action: finalize` are undefined at 3.1.1

**Disposition:** NEW-UPSTREAM. Target: adcontextprotocol/adcp.

**Upstream title:** `get-products-request.json defines "ask" semantics for action: omit but is silent for action: finalize`

**Upstream body:**
```
`v3.1.1 media-buy/get-products-request.json:141` says `ask` is "Ignored when action is 'omit'" and
is silent on `finalize`. A buyer sending `{action: finalize, ask: "…"}` has no defined answer to
"was my ask applied before the commit?" — which matters, because finalize is itself a commit action.

Not a seller-implementation bug on our end. We currently retain `ask` unmodified through a finalize
action (verified: round-trips unchanged), which is one reasonable reading, but nothing in the schema
confirms or denies it.

Requesting clarification of `ask` semantics under `action: finalize` in the next schema revision.
```

**Companion tracking issue (prebid/salesagent, milestone "Storyboard Compliance"):**

**Title:** `Track upstream: ask semantics under action:finalize are undefined — do not over-generalize the omit rule locally`

**Body:**
```
Filed upstream at adcontextprotocol/adcp: [link once created]. Note: a local scenario
(`@T-UC-001-storyboard-finalize-uses-refine-vocabulary`) generalised the `omit` rule to `finalize` in
both its Then and its comment block — that generalisation is in no schema and no storyboard, and
asserts the opposite of observable behaviour. Fix locally as part of the retag work tracked in the
SCENARIO item on mis-tagged `@storyboard-v3.1` scenarios; raise the semantic ambiguity itself only
upstream.

Evidence gathered on branch `test/storyboard-binding-baseline`.
```

---

## 6. Bonus item — not one of the ticket's 49, drafted for completeness

### M-01 — The sweep brief's "known production gaps" list is wrong per-tool

**Disposition:** NEW (internal documentation fix, no external repo). This is a docs-only action
item, not itself a defect in production or tests — recommend filing as a `docs`-labeled task in
prebid/salesagent if the team wants to track it, but it does not need to compete for a GitHub issue
number.

**Title (if filed):** `Rewrite the storyboard-sweep known-gaps list per-tool and per-path — the global framing was measurably wrong for several tools`

**Body:**
```
## Why this matters

Four independent findings during the sweep measured a prior "known production gaps" brief and found
it false for their tool. Scenario authors write *around* stated gaps, so a wrong gap list produces
weakened scenarios — the opposite of what such a list is for.

| brief claim | measured reality |
|---|---|
| "No top-level status on responses" | Per tool. Present on create_media_buy and list_creatives. Absent on sync_creatives, get_media_buys, get_media_buy_delivery, list_creative_formats, signals. Always absent on error envelopes. |
| "REST drops context" | Per tool, and one instance is a harness bug, not production. REST does echo context on create_media_buy. On list_creatives the drop is in the test harness's build_rest_body, not production. On list_creative_formats it is genuinely production (ListCreativeFormatsBody has no context field). |
| "REST and MCP drop pagination" | False for list_creatives (pagination is present on the wire). True for list_creative_formats. |
| "then_response_schema_valid runs no validator" | True of one copy, false of the other (see the companion test-infra issue). |
| "pinned schema fixtures vendored at 04f59d2d5" | True overall, but not uniformly — some files already carry 3.1.1-era content. |
| "context not echoed on wire error envelopes" | False as a general claim — measured present for several error codes. The real limitation is that the harness's *reconstructed* error object drops context; the wire envelope does not. |

## Acceptance criteria

- [ ] The known-gaps list rewritten per tool and per path (success/error), not globally.
- [ ] Each entry states whether it is a production gap or a harness gap.
- [ ] It lives somewhere durable (`docs/test-obligations/`) rather than in a task brief, since it is
      now the input to every future scenario author.

---
Evidence gathered on branch `test/storyboard-binding-baseline`.
```

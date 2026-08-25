# Storyboard scenario reconciliation — AdCP 3.1.1

**40 of 40 scenarios assessed** — complete.

Status: **GRADED** 19 · **NOT GRADED** 21

Action: **FIX-ASSERT** 4 · **PARTIAL** 5 · **REPIN** 10 · **RETAG** 19 · **TICKET** 2

Actions — `RETAG` tag claims a grading that does not apply to us (becomes `@schema-v3.1`, identifier preserved) · `REPIN` graded, `@source` stale/wrong/absent · `FIX-ASSERT` graded, scenario asserts the wrong thing · `TICKET` graded, production non-conformant, scenario stays dormant · `PARTIAL` verdict is compound (part salvageable green, part not) — needs a human split.

| Scenario | Status | Action | Verdict |
|---|---|---|---|
| `uc002-inv-targeting` | GRADED | **REPIN** | GRADED. The @storyboard-v3.1 tag is justified and the scenario is on our conformance path. |
| `uc002-measurement` | GRADED | **PARTIAL** | GRADED — but the half this scenario asserts is 100% unimplemented, so it cannot land green as written. |
| `uc003-creativefate` | GRADED | **PARTIAL** | GRADED — the @storyboard-v3.1 tag is justified, but only for half of what the scenario title claims. |
| `uc003-mbnotfound` | GRADED | **REPIN** | GRADED. The @storyboard-v3.1 tag is justified. |
| `uc003-notcancellable` | GRADED | **FIX-ASSERT** | GRADED — and on our conformance path — but the scenario asserts the wrong code, and it is DORMANT so it grades nothing today. |
| `uc003-pkgnotfound` | GRADED | **REPIN** | GRADED — and doubly so. PACKAGE_NOT_FOUND is graded by exactly one storyboard at 3.1.1, |
| `uc004-delivery` | GRADED | **REPIN** | GRADED — and the tag @storyboard-v3.1 stays. |
| `uc004-reqmetrics` | GRADED | **FIX-ASSERT** | GRADED — but the scenario asserts the one branch that is NOT graded, and it currently grades nothing at all (dormant). |
| `uc004-vendormetric` | GRADED | **PARTIAL** | GRADED — but only one of its three phases can be green today. |
| `uc005-baseline` | GRADED | **REPIN** | GRADED — storyboard grades formats[0] presence only; core/format-id.json is strictly stronger (every entry, type object, required pair, value patterns). Schema wins. |
| `uc005-roundtrip` | GRADED | **REPIN** | GRADED — list_formats_integrity lives in protocols/media-buy/index.yaml, not the cited protocols/creative/index.yaml; schema mandates canonicalized agent_url comparison where the storyboard grades byte equality. |
| `uc005-thirdparty` | GRADED | **FIX-ASSERT** | GRADED — but the scenario asserts the compliance runner's on_out_of_scope grading policy, which no seller behaviour can falsify; the gradeable obligation is do-not-fabricate. Cited path also wrong. |
| `uc006-fmtroundtrip` | GRADED | **FIX-ASSERT** | GRADED — but the specific MUST the scenario names is prose, not a graded check. |
| `uc006-multiformat` | GRADED | **REPIN** | GRADED — but the cited binding is wrong, and the scenario as written cannot be graded at 3.1.1. |
| `uc006-prov-corrected` | GRADED | **REPIN** | GRADED — and the footer's cited path is wrong. |
| `uc006-prov-disclosure` | GRADED | **REPIN** | GRADED — and correctly bound. But zero production coverage, and the scenario is DORMANT today. |
| `uc006-prov-dst` | GRADED | **TICKET** | GRADED — and unimplemented. The scenario is currently DORMANT (auto-xfail), and the graded assertion cannot be made green. |
| `uc006-prov-required` | GRADED | **TICKET** | GRADED — and production is non-conformant. The scenario CANNOT be made green as a storyboard assertion. |
| `uc019-statuspoll` | GRADED | **REPIN** | GRADED — and the scenario's own prose named the right storyboard all along; it just never |
| `uc001-finalize` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. (And, independently, NOT GRADED — prose only at the cited step.) |
| `uc001-refine` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. And, independently, NOT GRADED — prose only. Both hold; either alone |
| `uc002-async` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. |
| `uc002-gov-approved` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. |
| `uc002-gov-conditions` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. |
| `uc002-gov-denied` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. |
| `uc002-gov-recovery` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. The @storyboard-v3.1 tag is unjustified and must become @schema-v3.1. |
| `uc002-inv-nomatch` | NOT GRADED | **PARTIAL** | NOT GRADED — prose only (for the behaviour the scenario currently asserts). |
| `uc002-pending` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. |
| `uc006-prov-contradicted` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate (and orphan storyboard). |
| `uc006-reception` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. Two independent reasons, either one sufficient: |
| `uc008-agentdest` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. Three independent reasons, each sufficient on its own: |
| `uc008-baseline` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. Two independent reasons, either one sufficient: |
| `uc008-platformdest` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. Triple-gated, and every gate is closed for us. |
| `uc014-session` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. Two independent reasons, either one sufficient: |
| `uc018-conceptid` | NOT GRADED | **RETAG** | NOT GRADED — concept_id appears only in specialisms/creative-ad-server ungraded expected: prose, and we do not declare that specialism. |
| `uc018-fmtfilter` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. |
| `uc018-listall` | NOT GRADED | **PARTIAL** | NOT GRADED — undeclared gate. The behaviour *is* graded at 3.1.1, but only inside the |
| `uc020-vast` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. |
| `uc021-preview` | NOT GRADED | **RETAG** | NOT GRADED — undeclared gate. Three independent reasons, any one of which is sufficient: |
| `uc030-govbinding` | NOT GRADED | **RETAG** | NOT GRADED — twice over. |

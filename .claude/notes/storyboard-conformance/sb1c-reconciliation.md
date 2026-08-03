# SB-1c — reconciling the derived coverage map against SB-1b's real-runner baseline

Beads task **salesagent-0w5t**. Compares `docs/test-obligations/storyboard-coverage-map.md`'s
derivation (`scripts/audit/storyboard_coverage_map.py`) against what the real
AdCP storyboard runner actually selected/graded in SB-1b
(`.claude/notes/storyboard-conformance/sb1b-runner/results/sb1b-full.json`,
`sb1b-baseline-report.md`).

## What disagreed, and which side was wrong

### 1. `universal/` tier ignored `required_tools` — classifier bug, fixed

The old `classify()` returned `("ON-PATH", ...)` for every `universal/*`
file the instant it matched the path prefix, before the `tool_gate()`
closure even existed in scope. The module docstring claimed
`required_tools` was a lenient any-of gate that applied everywhere, but the
code never actually called it for `universal/`.

Real-runner evidence (`sb1b-full.json` `storyboards_missing_tools`, 10
entries) shows all 10 are `universal/*` storyboards graded fully
`not_applicable`/skipped purely because our agent's tool surface didn't
intersect their `required_tools` (`comply_test_controller`, `validate_input`,
`list_collection_lists`, `list_content_standards`, `list_property_lists`,
`get_signals`, `activate_signal` — verified per-file against
`~/projects/adcp/dist/compliance/3.1.1/universal/*.yaml`). The 25 executed
storyboards all have `required_tools` that DO intersect our tool surface.
100% consistent — the classifier was wrong, not the storyboards.

**Fix:** `classify()` now runs `universal/*` through the same `tool_gate()`
every other tier uses (`scripts/audit/storyboard_coverage_map.py`).

Net effect after the fix: of the 10 real `storyboards_missing_tools`, 6 now
correctly classify OFF-PATH (`canonical_format_validate_input`,
`comply_controller_mode_gate`, `deterministic_testing`,
`pagination_integrity_collection_lists`, `pagination_integrity_content_standards`,
`pagination_integrity_property_lists` — none of their `required_tools` are in
`ADVERTISED_TOOLS`). The other 4
(`error_compliance_signals`, `get_signals_pagination_integrity`,
`schema_validation_signals`, `wholesale_feed_signals`) still classify
ON-PATH under the fixed classifier, because their only `required_tools` are
`get_signals`/`activate_signal` — real, production-registered MCP tools
(`src/core/tools/signals.py::get_signals`, `::activate_signal`), genuinely in
`ADVERTISED_TOOLS`. This is expected divergence, not a re-introduced bug: the
SB-1b run used `tests/harness`'s "E2E Test Client" dispatcher, whose
`agent_profile.tools` list (`.claude/notes/storyboard-conformance/sb1b-runner/results/sb1b-full.json`
→ `agent_profile.tools`) does not include `get_signals`/`activate_signal` even
though the real MCP server implements them — a harness/dispatcher gap, not a
classifier gap. Owned by the sibling harness tasks (salesagent-uz00/wu78/tisr,
`tests/harness/dispatchers.py` / `tests/harness/client.py`), explicitly out of
this task's file scope. Do not "fix" the classifier by shrinking
`ADVERTISED_TOOLS` to match the harness's current dispatch surface — that
would make the classifier wrong about the real server to satisfy an
incomplete test double.

### 2. Two `universal/` files are not gradable storyboards at all — classifier bug, fixed

`universal/fictional-entities.yaml` (a shared fixture/data catalog: brands,
agencies, collections — no `id`/`phases`/`track`) and
`universal/runner-output-contract.yaml` (a contract describing REQUIRED
runner *output* shape, not something dispatched against an agent; it isn't
even valid plain YAML — parsing it throws on an embedded code block) were
both counted as ON-PATH storyboards by the old classifier purely because they
live under `universal/`. Neither ever appears anywhere in the SB-1b run's
`storyboards_executed`, `storyboards_missing_tools`, or `observations` —
every one of the 35 *other* files in `universal/` does appear in one of those
two lists. Confirmed the discriminator: every real storyboard (across all
three tiers, 121 of 123 files) declares a top-level `track:`; these two
don't (the third file without `track:` is `universal/storyboard-schema.yaml`,
already excluded by the pre-existing `stem == "storyboard-schema"` check).

**Fix:** `build()` now skips any `universal/*` file lacking a top-level
`track:` field, with a comment citing this evidence. Scoped to `universal/`
only — did not extend the same filter to `specialisms/creative-generative/index.yaml`
and `specialisms/creative-transformers/index.yaml`, which also lack `track:`
but are real, populated specialism definitions (have `id`, `required_tools`,
`protocol`) that just happen to omit that one field upstream; they're
already OFF-PATH (protocol `creative` not declared) and uncleared by any
current scenario claim, so leaving them in the row set is a no-op on today's
output and doesn't risk misclassifying something I have no runner evidence
for.

### 3. `protocols/`, `domains/`, `specialisms/` tiers (33 items) — UNRESOLVED, not a classifier defect this run can prove or disprove

SB-1b's capability probe (`get_adcp_capabilities`) was itself rejected by our
agent (`VALIDATION_ERROR: Unexpected keyword argument` on
`adcp_major_version`/`adcp_version`/`context` — `agent_profile.capabilities_probe_error`
in `sb1b-full.json`). The SDK's `resolveStoryboardsForCapabilities` depends on
that call succeeding to resolve our declared `supported_protocols`/
`specialisms`. Because it failed, the runner never attempted to select
anything under `protocols/` or `specialisms/` — confirmed by exact set
arithmetic: `storyboards_executed ∪ storyboards_missing_tools` (35 items) is
byte-identical to "every real, gradable file under `universal/`" (35 items,
`~/projects/adcp/dist/compliance/3.1.1/universal/*.yaml` minus the two
excluded above and the schema file). Nothing from `protocols/media-buy/`,
`specialisms/sales-non-guaranteed/`, or any other tier appears anywhere in
the run's output.

This means the module docstring's UNRESOLVED question — whether a scenario
outside every `requires_scenarios` list (the case `provenance_enforcement`
was named as deciding) is reachable standalone on its own `required_tools`,
or orphaned — is **still unresolved**. `provenance_enforcement` never
appears anywhere in `sb1b-full.json` (grepped for `provenance`: zero hits).
This run is not evidence either way for the ~33 protocol/specialism-gated
storyboards; I did not touch that part of `classify()`/`requiring_indexes()`,
and the docstring now says so explicitly instead of implying SB-1b settled
it. Re-running the real SDK against a working `get_adcp_capabilities` (the
capabilities-probe bug is tracked as a follow-up in `sb1b-baseline-report.md`,
not this task) is what would actually produce evidence here.

## Regenerated artifact

`docs/test-obligations/storyboard-coverage-map.md` regenerated via
`python3 scripts/audit/storyboard_coverage_map.py --markdown`:

- storyboards examined: 123 → 121 (2 non-storyboard `universal/` files excluded)
- on our conformance path: 70 → 62 (6 universal storyboards reclassified
  OFF-PATH on the `required_tools` fix; 2 removed entirely as non-storyboards)
- off-path/gated but claimed by a scenario: 10 → 2

That last number's drop is **not** an effect of this task's classifier fix —
reran the *unmodified* classifier against the current `tests/bdd/features/`
tree first and got the same "2", not "10" — the checked-in doc was stale
relative to feature-file changes made since it was last generated (commit
`9adb5971b`, several commits before `HEAD`). Regenerating picked that drift
up as a side effect, which is expected: the artifact is supposed to reflect
current `tests/bdd/features/` state, and staleness on the "claimed by"
column isn't something this task's classifier fix caused or should try to
suppress.

## `error_compliance` overlap with salesagent-44c8

SB-1b's `error_compliance` failures (`nonexistent_product`,
`reversed_dates_error`, `unsupported_major_version`,
`unsupported_release_version` — see "Failure classes" #4 in
`sb1b-baseline-report.md`) are the *real runner* grading the same underlying
gap that **salesagent-44c8** (epic: reconcile BDD error-code assertions
against AdCP 3.1.1) already tracks from the BDD-assertion angle: production's
error-code vocabulary/emission doesn't cover the pinned spec's enum for
several paths. Both point at the same root cause (production error-code
emission drift vs. the v3.1.1 enum), graded by two different harnesses (real
compliance runner vs. our BDD suite). Not filing a new gap for this — noting
it here so nobody double-counts `error_compliance`'s "ON-PATH, NOT COVERED"
row in the coverage map as a fresh, unrelated finding. Fixing it is
salesagent-44c8's scope, not this task's.

## Follow-ups (not filed by this task)

- Re-run SB-1b's real SDK runner once `get_adcp_capabilities` accepts
  `adcp_major_version`/`adcp_version`/`context` (tracked in
  `sb1b-baseline-report.md`'s own follow-ups) — that's what would finally
  produce real evidence for the `protocols/`/`specialisms/` tiers and settle
  the `provenance_enforcement` reachability question.
- `tests/harness`'s "E2E Test Client" dispatcher under-advertises tools
  relative to the real MCP server (missing `get_signals`/`activate_signal`;
  also exposes `update_performance_index`/`list_tasks`/`get_task`/
  `complete_task` that `ADVERTISED_TOOLS` in the classifier doesn't list,
  though nothing in the `universal/` tier currently gates on those four) —
  for the sibling harness tasks (salesagent-uz00/wu78/tisr), not this one.

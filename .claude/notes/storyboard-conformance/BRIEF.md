# Shared brief — re-ground ONE BDD scenario against AdCP 3.1.1

You own exactly one scenario. Read this brief, do the work, write your proposal file. **Propose only — do NOT edit any file under `/Users/konst/projects/salesagent-sbsweep`.**

Repo under audit: `/Users/konst/projects/salesagent-sbsweep` (branch `test/storyboard-binding-baseline`, off `origin/main` @ `8cb8d0ed6`).
Spec repo: `/Users/konst/projects/adcp`.

## Authority order — strict

1. **AdCP 3.1.1 JSON schemas** — HIGHEST. Read via `cd /Users/konst/projects/adcp && git show v3.1.1:static/schemas/source/<path>`
2. **AdCP 3.1.1 storyboards** — `/Users/konst/projects/adcp/dist/compliance/3.1.1/...` (checked out on disk)
3. SDK (`adcp==6.6.0`) and our production code — **cross-check only, never authority**

Where schema and storyboard disagree, **the 3.1.1 schema wins** — say so explicitly in your writeup.

We are pinned to **3.1.1** and are NOT moving the pin. Do not treat 3.1.8 or HEAD as authority. (You may note drift in Risks, nothing more.)

## Two defects already proven across the scenario set — assume yours has them

**1. The `@source` ref is stale.** Nearly every scenario pins `ref=v3.1-04f59d2d5 commit=04f59d2d5`. That commit is an **ancestor of beta.3**, i.e. OLDER than our own 3.1.1 pin. Re-pin forward to `ref=v3.1.1`.

**2. The `@source` path is probably WRONG.** 16 of 40 scenarios were mechanically proven to cite the **next scenario's** storyboard — a systematic off-by-one (`create_media_buy_async` → cites `governance_approved` → cites `governance_conditions` → cites `governance_denied` → …).

**Do not trust the cited path.** Find the real one. The scenario's own prose usually names its true storyboard in a summary line just above the footer, e.g. `# governance_approved: APPROVED decision flows through to the persisted buy`. Take that name, locate the actual file under `dist/compliance/3.1.1/`, and verify the phase/step is really there. If your scenario has **no** `@source` footer at all (11 do not), derive the correct binding from the scenario's subject and add one.

## The questions you must answer

1. **Where is this behaviour actually graded at 3.1.1?** Give the real file + line, and quote the graded `validations:` block verbatim.
2. **Is it graded at all?** A mention under `expected:` is *narrative prose*, NOT graded. Only entries under `validations:` (`- check: …`) are graded. If the behaviour appears only in prose, the `@storyboard-v3.1` tag is **unjustified**.
3. **Which tier owns it** — `universal/` (always applies), `protocols/`, `domains/`, or `specialisms/` (capability-gated)?
4. **Do we declare the gate?** `src/core/tools/capabilities.py` declares `specialisms=[sales_non_guaranteed]` and `supported_protocols=[media_buy]` — nothing else. A scenario gated by a specialism or protocol we do not declare is **not on our conformance path**, and its tag should become `@schema-v3.1` (that tag already exists in the vocabulary; UC-010 uses it). Keep the opaque `@T-UC-…` identifier tag unchanged — it is referenced from `docs/test-obligations/bdd-traceability.yaml`.
5. **What do the 3.1.1 JSON schemas mandate** for this behaviour — required fields, enums, patterns, envelope refs (`core/protocol-envelope.json` requires `status`), pagination rules? Quote them.
6. **What is the scenario missing or asserting wrongly?**

## Rewriting the scenario — rules

- **GREEN ONLY.** Include an assertion **only if it passes against current production.** Verify by reading `src/`. If an assertion would require a production change, **do not include it** — put it in your `TICKET MATERIAL` section instead. This is a baseline PR; nothing may go red.
- **Transport-independent.** Identical logic across MCP / A2A / REST / e2e_rest. No transport branching anywhere in the Gherkin.
- **Use `Scenario Outline` + `Examples:` tables** to express specificity — that is the point of this exercise. Prefer parametrized rows over vague prose Thens.
- **Every Then must compare concrete values.** Never truthiness or mere existence — structural guards (`test_architecture_bdd_no_trivial_assertions.py`, `..._no_pass_steps.py`) reject those.
- **Reuse existing steps.** Search `tests/bdd/steps/` (`ast-grep --pattern '@then($_)' tests/bdd/steps/`) before inventing phrasing. Report existing vs new.
- Keep the tag vocabulary; update `@source` to cite **3.1.1** with the real path and phase.
- Comments cite **GitHub issue numbers** (`#1234`), NEVER beads ids (`salesagent-abcd`).

## Known production gaps — already found, do NOT re-file

If your scenario touches these, cite them; don't rediscover them:

- `list_creatives` never emits `pagination.cursor` while `has_more` can be true (`src/core/tools/creatives/listing.py:349,416-419`) — violates `universal/pagination-integrity.yaml`
- No top-level `status` on responses; 3.1.1 adds `core/protocol-envelope.json` (`required: ["status"]`) to response schemas
- REST drops `context` and `pagination`; MCP drops `pagination` (`src/routes/api_v1.py`, Pattern #5 violation)
- REST emits `cursor: null` on terminal pages (`api_v1.py:211` `model_dump` without `exclude_none`)
- `tests/fixtures/adcp_schemas_pinned/` is vendored at `04f59d2d5`, not 3.1.1
- `then_response_schema_valid` runs no validator despite `tests/helpers/pinned_schema.py::validate_against_pinned_schema` existing

## Output file structure

1. **VERDICT** — is this scenario storyboard-graded for us? (`GRADED` / `NOT GRADED — prose only` / `NOT GRADED — undeclared gate`). State it first, plainly.
2. **Real binding at 3.1.1** — correct file + line, graded `validations:` quoted verbatim; and what the current footer wrongly points at.
3. **Schema constraints at 3.1.1** — verbatim quotes + file.
4. **Conflicts** — where schema overrode storyboard; what the scenario gets wrong, misses, or asserts vacuously.
5. **Proposed Gherkin** — complete replacement, fenced, ready to paste. GREEN ONLY.
6. **Step inventory** — existing vs new step phrasings.
7. **TICKET MATERIAL** — every follow-up that cannot land green, one bullet each, each with: what is broken, the file:line evidence, and which 3.1.1 schema/storyboard clause mandates the fix. This section becomes GitHub issues, so make it specific enough to file verbatim.
8. **Risks** — anything you are unsure about, and anything you could not verify by execution.

End your final message with a 10-line summary. The file is the deliverable.

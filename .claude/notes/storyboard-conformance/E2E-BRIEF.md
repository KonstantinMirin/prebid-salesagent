# Brief — e2e-wireability pass over the proposed scenarios

You are auditing proposed BDD Gherkin for whether it can actually **run on every transport it will be parametrized across**. Read-only: do NOT edit anything in `/Users/konst/projects/salesagent-sbsweep`.

Repo: `/Users/konst/projects/salesagent-sbsweep` (branch `test/storyboard-binding-baseline`).
Proposals: `/private/tmp/claude-501/-Users-konst-projects-salesagent/febefa2f-073c-4553-a1b1-3f61a47b9e32/scratchpad/` — each `sb-*.md` / `repin-*.md` has a **Proposed Gherkin** fenced block and a **Step inventory** section.

> **This brief was rewritten after its first version stated the criterion wrongly.** The earlier
> version said in-process mock injection is categorically e2e-unsafe and named
> `set_adapter_response` / `set_registry_formats` as unsafe. **Both are e2e-realized.** Judging by
> "does it look like mocking" produces confidently wrong answers. Use the mechanism below.

## The criterion — `realize_e2e`

`tests/harness/_realize.py` defines a decorator that every setup method carrying in-process state
must use. A method is either:

- `@realize_e2e(<realizer_fn>)` → **e2e-safe.** In-process it does the mock thing; over e2e the
  realizer performs the equivalent through a real server surface (usually a DB write the server
  reads).
- `@realize_e2e(e2e_unsupported("<reason>"))` → **not e2e-safe**, declared, with a reason.

Verified inventory at this commit — do not re-derive, but do verify anything you depend on:

| Method | Status |
|---|---|
| `set_adapter_response` → `_realize_adapter_response` (`tests/harness/_mixins.py:202`) | **REALIZED** — persists a `DeliverySimulationConfig` row (`_mixins.py:37`) that the live server's Mock adapter reads (`src/adapters/mock_ad_server.py:1155`, `:1208`) |
| `set_registry_formats` (`tests/harness/creative_formats.py:114`) | **REALIZED** |
| `set_adapter_error` (`tests/harness/_mixins.py:211`) | **UNSUPPORTED** — *"adapter fault-injection has no server surface; needs an ADCP_TESTING fault-injection control (#1418)"*. One caller: `tests/bdd/steps/domain/uc004_delivery.py:308` |

So today exactly **one** setup capability is genuinely unrealizable over e2e: adapter fault injection.

## The other things that decide wireability

- **DB-seeded state is safe.** Factory/ORM writes reach the server: `tests/bdd/conftest.py:3136`
  `_production_db_pointed_at` repoints `DATABASE_URL` at the live server's database for the
  scenario. A Given that sets state no request could produce (e.g. `given_media_buy_status`,
  `tests/bdd/steps/domain/uc003_update_media_buy.py:162`, which sets `mb.status = "canceled"` and
  commits) is legitimate — it is a fixture, not a lie.
- **IMPL is sunsetted.** `tests/bdd/conftest.py:2871` — the parametrized set is `[A2A, MCP, REST]`
  plus `E2E_REST` when enabled. Any proposal reasoning about an IMPL path, an IMPL fallback, or
  `_serialized_*` degrading to "the production-serialized payload on IMPL" is reasoning about
  something that does not execute. Flag every instance.
- **UC-019 is e2e-exempt by design.** `tests/bdd/conftest.py:2832`
  `_NO_REST_UC_TAG_PREFIXES = ("T-UC-019-",)`: no REST route, so it runs `[A2A, MCP]` only and skips
  e2e. Record E2E-EXEMPT; do not invent a remediation.
- **e2e is REST-only today.** `E2E_REST` dispatches real HTTP REST to a separate server process. No
  e2e_mcp driver exists yet. A tool with no REST route 404s there.

## Your task, per assigned scenario

1. List every `Given` / setup step in the **Proposed Gherkin**.
2. Find each step's definition (`tests/bdd/steps/`, plus the scenario's own binding module — UC-018's
   steps live inline in `tests/bdd/test_uc018_list_creatives.py`). If the proposal marks a step NEW,
   judge from its described implementation.
3. For each, determine what it ultimately does: DB write · a `realize_e2e`-REALIZED harness method ·
   a `realize_e2e`-UNSUPPORTED harness method · in-process state with **no** `realize_e2e`
   declaration at all (this last one is the dangerous case — it silently breaks e2e).
4. Verdict: **E2E-WIREABLE** / **NOT-E2E-WIREABLE** / **E2E-EXEMPT (UC-019)**.
5. If not wireable: name the exact breaking step, and give the remediation — add the realizer, or
   re-express the Then so it grades an e2e-observable signal. A new `e2e_rest_known_failures.txt`
   entry is NOT a remediation: the ledger is a ratchet that may only SHRINK, so adding a row to it
   is how a gap becomes permanent. Never a silent new failure either.
6. Flag every dead IMPL assumption, and any Then reading state REST would not expose.

## Rules

- **Read the step body and follow it to the harness method.** Never classify from wording.
- Do not invent realizers that do not exist. "No realizer today" is a valid, useful answer.
- Quote `file:line` for every classification.
- GitHub issue numbers, never beads ids.

## Output

Write to the file named in your task prompt:

1. **Summary table** — scenario · verdict · breaking step (if any) · remediation
2. **Per scenario** — classified step list with `file:line`, plus remediation detail
3. **Dead IMPL assumptions** — each, with proposal and line
4. **Steps with in-process state and no `realize_e2e` declaration** — the silent-breakage class
5. **Ledger entries to REMOVE** — exact nodeid-shaped entries, if any
6. **Uncertainties**

Final message: 12-line summary. The file is the deliverable.

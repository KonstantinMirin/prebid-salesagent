# SB-1b — measured storyboard-runner baseline

Beads task **salesagent-exbf**. First GROUND-TRUTH run of the real AdCP
conformance runner (`@adcp/sdk`'s `adcp storyboard run`, which wraps
`runStoryboard`/`resolveStoryboardsForCapabilities` from `@adcp/sdk/testing`)
against a live, seeded copy of this repo's MCP endpoint. Everything below is
measured output from that run, not inference from reading YAML.

Run date: 2026-08-03. Branch: `test/storyboard-binding-baseline`.

## TL;DR

- **0 of 25** selected storyboards passed cleanly.
- **16** storyboards produced at least one failing check (**72** failing
  checks total across them, `d.failures[]`; the SDK's own step-level tally
  reports **69** failed steps — the 3-item gap is the SDK counting some
  probe-class steps as one failed *step* with multiple flattened
  *failures*, not a measurement error on our side).
- **9** storyboards produced **zero graded steps** — 100% skipped, mostly
  because our agent doesn't expose `comply_test_controller` (an
  admin-seeding tool the runner uses to force deterministic account/creative
  states) or because this run didn't pass `--webhook-receiver` (needed for
  `webhook_emission`/`idempotency`'s controller-seeded steps). These are
  **coverage-blocked, not verified-clean** — do not read "0 failures" here as
  "passing."
- **10** more storyboards were capability-selected but couldn't run at all —
  our agent doesn't expose the MCP tool(s) they need (`storyboards_missing_tools`).
- **1** track (`creative`) produced no results at all.
- Two dominant, cross-cutting failure classes account for the bulk of the 72
  failing checks (see "Failure classes" below): a `get_adcp_capabilities`
  request-shape rejection (17 checks) and an `sync_accounts` auth rejection
  on a token that authenticates fine everywhere else (8 checks). The
  remaining 47 are almost all the `signed_requests` storyboard (40 checks) —
  expected, since this repo does not implement RFC 9421 request signing.

## Method

1. **SDK / spec pin.** `@adcp/sdk@9.3.0` (matches spec 3.1.1 per
   `.claude/research/salesagent-7voe.md`, SB-1a). Sidecar at
   `.claude/notes/storyboard-conformance/sb1b-runner/` (`package.json` +
   `package-lock.json`, committed; `node_modules/` is not).
2. **Exact-3.1.1 schema/compliance bundle.** Downloaded the `v3.1.1` GitHub
   release asset `3.1.1.tgz` from `adcontextprotocol/adcp` (sha256
   `e1894a8222529bafc34a8e5d45b395e1b4079de82238416cc753fa71940dfc5d`,
   verified against the published `.sha256`), unpacked to get `schemas/` and
   `compliance/` (contains `index.json` declaring `adcp_version: 3.1.1`).
   Not committed (84 MB of generated spec artifacts) — re-download to
   reproduce (command below).
3. **Stack.** Per the ticket's explicit instruction, brought up
   `docker-compose.e2e.yml` (+ `docker-compose.e2e.ports.yml` for host-port
   publishing, since the base file publishes none by design) on the remote
   CI box (hetzner2) via `saci sync` + manual `docker compose`, **not**
   `run_all_tests.sh`/`saci run` — that script tears the stack down via a
   `trap cleanup EXIT` the instant its own test suites finish, which doesn't
   leave a window for an external sidecar to run against it. Project name
   `sb1b`, ports `18092`/`15435` (non-default, to avoid collision with other
   concurrent box activity). Seeded CI data
   (`scripts/setup/init_database_ci.py` via `docker compose exec
   adcp-server`) exactly as `tests/e2e/conftest.py`'s in-network branch does,
   producing `ci-test-token` / tenant `default` / 2 products.
4. **Smoke test first**, per the ticket: single storyboard
   (`capability_discovery`) before the full set, confirmed it reached the
   real endpoint and returned a real (non-connection-error) result.
5. **Full run**, capability-driven (`adcp storyboard run <url>` with no
   storyboard id → the CLI calls `get_adcp_capabilities` on the agent and
   runs `resolveStoryboardsForCapabilities` — the exact "which storyboards
   the runner SELECTS for us" mechanism the ticket asks about — against our
   `supported_protocols`/`specialisms`). Re-ran once with `--compliance-version
   3.1.1` added explicitly after noticing the first pass's `schemas_used`
   summary field showed `/schemas/3.1.0/...` labels; the two runs produced
   byte-identical results (`diff` clean) and the corrected run's top-level
   `adcp_version` field correctly reports `3.1.1`, so the `/3.1.0/` string in
   `schemas_used` looks like a cosmetic/internal labeling artifact in the SDK
   (not confirmed root-caused — noted, not chased further; out of scope for
   a measurement task).
6. Pulled results back, teardown (`docker compose -p sb1b down -v`) after
   capture.

### Reproduce

```bash
# 1. sidecar deps
cd .claude/notes/storyboard-conformance/sb1b-runner && npm ci

# 2. exact-3.1.1 compliance/schema bundle (not committed)
gh release download v3.1.1 --repo adcontextprotocol/adcp -p "3.1.1.tgz" -p "3.1.1.tgz.sha256"
shasum -a 256 -c 3.1.1.tgz.sha256   # verify before trusting it
tar -xzf 3.1.1.tgz                   # -> adcp-3.1.1/{schemas,compliance}

# 3. bring up the e2e stack with host ports (NOT run_all_tests.sh/saci run —
#    those tear down the instant their own suites finish)
export COMPOSE_PROJECT_NAME=sb1b ADCP_SALES_PORT=18092 POSTGRES_PORT=15435
docker compose -f docker-compose.e2e.yml -f docker-compose.e2e.ports.yml \
  up -d postgres adcp-server proxy creative-pg creative-agent
docker compose -p sb1b -f docker-compose.e2e.yml -f docker-compose.e2e.ports.yml \
  exec -T adcp-server python scripts/setup/init_database_ci.py

# 4. smoke test (single storyboard)
node_modules/.bin/adcp storyboard run http://127.0.0.1:18092/mcp/ capability_discovery \
  --auth ci-test-token --allow-http --compliance-version 3.1.1 \
  --compliance-dir ./adcp-3.1.1/compliance --schema-root ./adcp-3.1.1/schemas --json

# 5. full capability-driven assessment
node_modules/.bin/adcp storyboard run http://127.0.0.1:18092/mcp/ \
  --auth ci-test-token --allow-http --compliance-version 3.1.1 \
  --compliance-dir ./adcp-3.1.1/compliance --schema-root ./adcp-3.1.1/schemas \
  --timeout 600 --json --summary-output summary.json > full.json

# 6. teardown
docker compose -p sb1b -f docker-compose.e2e.yml -f docker-compose.e2e.ports.yml down -v
```

Each failing check's `fix_command` in `results/sb1b-full.json`'s
`failures[]` array is a ready-to-run
`adcp storyboard step <url> <storyboard_id> <step_id> --json ...` for
drilling into that one check in isolation.

## Selection — what the runner picked for us

`storyboards_executed` (25) — capability-resolved AND our agent exposes the
tool(s) they need, so they actually ran:

```
billing_gate_dispatch, capability_discovery, error_compliance,
get_media_buys_pagination_integrity, get_products_pagination_integrity,
idempotency, notification_config_event_scope, notification_config_lifecycle,
notification_config_rejections, pagination_integrity,
pagination_integrity_creative_formats, pagination_integrity_list_accounts,
read_tool_idempotency, schema_validation, security_baseline, signed_requests,
stale_response_advisory, v3_envelope_integrity, version_negotiation,
webhook_emission, webhook_receiver_envelope, wholesale_feed_bulk_webhooks,
wholesale_feed_product_webhooks, wholesale_feed_products,
wholesale_feed_signal_webhooks
```

`storyboards_missing_tools` (10) — capability-resolved but our agent doesn't
expose the MCP tool the storyboard needs, so it graded as fully skipped
(`missing_test_controller` / not applicable), not run:

```
canonical_format_validate_input, pagination_integrity_collection_lists,
comply_controller_mode_gate, pagination_integrity_content_standards,
deterministic_testing, error_compliance_signals,
get_signals_pagination_integrity, pagination_integrity_property_lists,
schema_validation_signals, wholesale_feed_signals
```

Track `creative` produced no results at all (`skipped_tracks`: "No
storyboards produced results for this track" — its one candidate storyboard,
`canonical_format_validate_input`, is in the missing-tools list above).

This 25+10 selection is itself a measured fact worth comparing against the
derived "70 storyboards apply to us" estimate in `README.md` (SB-1c's job,
not this task's) — the capability-driven mechanism here only resolves
against what `get_adcp_capabilities` + tool discovery report, so it is
narrower in scope than a hand-audited "would apply to a seller like us"
sweep.

## Per-storyboard results (25 executed)

Format: storyboard — verdict (passed/failed/skipped steps), failing check
ids with the AdCP error code from the agent's actual wire response
(`(none)` = the check compared HTTP status/error-field directly rather than
via a typed `AdCPError`, e.g. the `signed_requests` HTTP probes).

### Failing (16)

| Storyboard | P/F/S | Failing check ids |
|---|---|---|
| `billing_gate_dispatch` | 0/2/1 | `get_capabilities` (VALIDATION_ERROR), `sync_accounts_passthrough_rejects_agent` (mcp_error) |
| `capability_discovery` | 0/2/0 | `get_capabilities` (VALIDATION_ERROR), `get_capabilities_filtered` (VALIDATION_ERROR) |
| `error_compliance` | 3/7/0 | `get_capabilities` (VALIDATION_ERROR), `nonexistent_product`, `missing_fields` (VALIDATION_ERROR), `reversed_dates_error`, `unsupported_major_version`, `unsupported_release_version`, `supported_major_version` (VALIDATION_ERROR) |
| `notification_config_event_scope` | 0/1/0 | `sync_accounts_rejects_scheduled_account_notification` (mcp_error) |
| `notification_config_lifecycle` | 0/1/5 | `sync_accounts_create_paused_notification_config` (mcp_error) |
| `notification_config_rejections` | 0/1/0 | `sync_accounts_rejects_duplicate_subscriber_id` (mcp_error) |
| `read_tool_idempotency` | 0/8/0 | `get_capabilities_with_idempotency_key`, `get_products_with_idempotency_key`, `list_accounts_with_idempotency_key`, `list_creative_formats_with_idempotency_key` (all VALIDATION_ERROR), `list_creatives_with_idempotency_key` (mcp_error), `get_capabilities_without_idempotency_key_3_1_accept` (VALIDATION_ERROR), `get_capabilities_without_idempotency_key_3_1_reject`, `assert_omitted_key_grace_handled` |
| `security_baseline` | 0/2/0 | `probe_unauth`, `assert_mechanism` — **see "Possible security gap" below** |
| `signed_requests` | 0/40/0 | `get_capabilities` (VALIDATION_ERROR) + 39 request-signing vectors, all `expected 2xx/401, got 404` — RFC 9421 signing routes (`/mcp-strict*`) don't exist on this server (expected; tracked separately, #1291) |
| `stale_response_advisory` | 0/2/2 | `get_capabilities` (VALIDATION_ERROR), `no_stale_on_healthy_upstream` (VALIDATION_ERROR) |
| `v3_envelope_integrity` | 0/1/0 | `no_legacy_status_fields` (VALIDATION_ERROR) |
| `version_negotiation` | 0/1/0 | `get_capabilities_with_version` (VALIDATION_ERROR) |
| `wholesale_feed_bulk_webhooks` | 0/1/0 | `register_bulk_change_webhook` (mcp_error) |
| `wholesale_feed_product_webhooks` | 0/1/0 | `register_product_pricing_webhook` (mcp_error) |
| `wholesale_feed_products` | 0/1/2 | `bootstrap_products` (VALIDATION_ERROR) |
| `wholesale_feed_signal_webhooks` | 0/1/0 | `register_signal_pricing_webhook` (mcp_error) |

### Zero graded steps — coverage-blocked, not verified (9)

`get_media_buys_pagination_integrity`, `get_products_pagination_integrity`,
`idempotency`, `pagination_integrity`, `pagination_integrity_creative_formats`,
`pagination_integrity_list_accounts`, `schema_validation`, `webhook_emission`,
`webhook_receiver_envelope` — all `0P/0F`, entirely `skipped`
(`missing_test_controller` and/or `requirement_unmet: webhook_receiver`,
since this run didn't pass `--webhook-receiver`). None of these represent
verified passing behavior.

## Failure classes (why 72 checks fail, grouped)

1. **`VALIDATION_ERROR: Unexpected keyword argument` on `get_adcp_capabilities`
   (and every read-tool step in `read_tool_idempotency` that also calls it)
   — 17 checks, the single biggest identifiable class.** The wire response
   (`observation_data.adcp_error`) shows our server rejects the request with
   `field: adcp_major_version`, `validation_errors: [adcp_major_version,
   adcp_version, context]` all `"Unexpected keyword argument"`. The runner
   sends `adcp_major_version`/`adcp_version`/`context` on every
   `get_adcp_capabilities` call (an AdCP 3.1.1 request-envelope field set);
   our tool's request model doesn't declare them, so FastMCP/Pydantic
   rejects the call outright before any capability data is ever returned —
   every storyboard whose first step is capability discovery inherits this
   failure. Confirmed reproducible: identical error on both runs (with and
   without the explicit `--compliance-version 3.1.1` flag), and on the
   isolated single-storyboard smoke test.
2. **`mcp_error: Authentication token is invalid for tenant 'default'` on
   `sync_accounts` — 8 checks.** The same `ci-test-token` authenticates
   fine on every `get_products`/`list_*` call in this same run (those get
   past auth and hit the `VALIDATION_ERROR` class above instead), so this
   looks like an auth-resolution path specific to `sync_accounts` rather
   than a broken token. Not root-caused further here (measurement task,
   not a fix task) — worth a focused look.
3. **`signed_requests` — 40 checks, all HTTP-level (`got 404`).** This repo
   does not implement RFC 9421 request signing or the `/mcp-strict*` routes
   the storyboard probes. Expected, already tracked (RFC 9421 work, #1291).
4. **`error_compliance`/`version_negotiation` variants (4 checks, no
   `adcp_error` — direct HTTP/error-code assertions) — server error-code
   emission for reversed dates / nonexistent product / unsupported version
   pins doesn't match what this storyboard expects.** Consistent with the
   BDD error-code reconciliation gap already tracked in this repo
   (`salesagent-44c8`) — not a new finding, but this is the first time it's
   graded by the *real* upstream runner rather than our own BDD harness.
5. **`security_baseline/probe_unauth` — possible real gap, flagged for
   priority triage (not diagnosed further here):** "Agent returned 200 or
   5xx on an unauthenticated protected call — it MUST reject with 401 (and
   send `WWW-Authenticate`) or 403." Worth checking with priority given the
   security implication, independent of the broader baseline sweep.

## Artifacts

- `sb1b-runner/package.json`, `sb1b-runner/package-lock.json` — the sidecar
  (pins `@adcp/sdk@9.3.0`; `node_modules/` not committed, restore with
  `npm ci`).
- `results/sb1b-full.json` — full `ComplianceResult` from the corrected
  (`--compliance-version 3.1.1`-explicit) run: `tracks[]`, flattened
  `failures[]` (each with `fix_command`, `expected`, and the raw
  `validation`/`adcp_error` payload), `storyboards_executed`,
  `storyboards_missing_tools`, `summary`.
- `results/sb1b-summary.json` — the narrow, schema-stable
  `{schema_version, passed, failed, failures}` artifact (`--summary-output`).
- `results/smoke.json` — the single-storyboard (`capability_discovery`)
  smoke-test result from step 4.

## Follow-ups (not filed by this task — for the team-lead / SB-1c)

- Root-cause the `get_adcp_capabilities` "Unexpected keyword argument"
  rejection (`adcp_major_version`/`adcp_version`/`context`) — it single-handedly
  blocks capability discovery for every storyboard that starts with it,
  which is most of them. **DONE — see SB-1d addendum below (salesagent-xg5w.1).**
- Root-cause the `sync_accounts`-specific "Authentication token is invalid
  for tenant 'default'" — same token works everywhere else in the same run.
  **Partially done — see SB-1d addendum (salesagent-xg5w.2, salesagent-xg5w.11).**
- Triage `security_baseline/probe_unauth` (unauthenticated protected call
  not rejecting with 401/403) as a possible real security gap. **Confirmed
  real (salesagent-xg5w.3); fix designed, blocked on human sign-off (new
  ASGI auth-enforcement middleware, out of scope for autonomous
  implementation given the blast radius).**
- Re-run with `--webhook-receiver loopback` to unlock the 9 currently
  coverage-blocked storyboards (`webhook_emission`, `idempotency`, the
  pagination-integrity family, `schema_validation`) — none of those are
  actually verified yet. **DONE — see SB-1d addendum below (salesagent-xg5w.4).**
- SB-1c: reconcile this measured 25-executed/10-missing-tools/1-track-empty
  selection against the derived "70 storyboards apply to us" estimate in
  `README.md`, and reconcile the 4 `error_compliance` gaps against
  `salesagent-44c8`. **Done (salesagent-0w5t, closed 2026-08-03).**

## SB-1d addendum — re-run with `--webhook-receiver loopback` (salesagent-xg5w.4)

Run date: 2026-08-03. Same branch, same method as SB-1b (`docker-compose.e2e.yml`
+ `.ports.yml`, project name `sb1d`, ports `18093`/`15436`, local Docker instead
of the remote CI box — the local machine had Docker available this session),
run **after** `salesagent-xg5w.1` and `salesagent-xg5w.2`'s fixes were committed
to this branch. One change from the SB-1b command: `--webhook-receiver loopback`
added to the full run. Raw data: `sb1b-runner/results/sb1d-full.json`,
`sb1d-summary.json`, `smoke-webhook.json`.

### Primary result: webhook receiver unlocks 3 of 9 previously coverage-blocked storyboards cleanly

| Storyboard | Before (SB-1b) | After (SB-1d) |
|---|---|---|
| `idempotency` | 0 graded steps (skipped, no receiver) | **All steps passed** (7 scenarios) |
| `schema_validation` | 0 graded steps (skipped, no receiver) | **All steps passed** (5 scenarios) |
| `webhook_receiver_envelope` | 0 graded steps | **All steps passed** (2 scenarios) |
| `webhook_emission` | 0 graded steps | Mostly passing — 5 of 9 checks fail: `idempotency_key_presence`, `operation_id_echo`, `idempotency_replay_side_effects`, `idempotency_key_stability` (all `sync_accounts`-token-invalid, see below), and `signing_keys_published`/`signature_validity` (RFC 9421 signing, expected — tracked separately, #1291) |
| `get_media_buys_pagination_integrity` | 0 graded steps | Still `requirement_unmet: controller` — needs `comply_test_controller`, unaffected by `--webhook-receiver` |
| `get_products_pagination_integrity` | 0 graded steps | Same — still controller-gated |
| `pagination_integrity` | 0 graded steps | Same — still controller-gated |
| `pagination_integrity_creative_formats` | 0 graded steps | Same — still controller-gated |
| `pagination_integrity_list_accounts` | 0 graded steps | Same — still controller-gated |

The pagination-integrity family's blocker is `comply_test_controller` (an
admin-seeding tool this agent doesn't expose), not the webhook receiver — a
distinct, still-open gap.

### `get_adcp_capabilities` fix confirmed, uncovered a second bug

The smoke test (`capability_discovery` alone) confirms the "Unexpected keyword
argument" rejection is gone. But the response now fails schema validation
instead: `extensions_supported`/`experimental_features`/`errors` are `null`
where the schema wants an array, `wholesale_feed_versioning`/`ext`/
`wholesale_feed_webhooks` are `null` where it wants an object, and the
`context`/`context_id` echo checks fail (not in the response). This blocks the
same wide set of storyboards `get_adcp_capabilities` gates, for a different
reason. Filed as `salesagent-xg5w.12`.

### `sync_accounts`-class token-invalid errors: confirmed NOT a masked infra error

`salesagent-xg5w.2` changed `get_principal_from_token()` to *raise*
`AdCPServiceUnavailableError` (a different message) instead of silently
returning `(None, None)` on a DB/infra exception. This re-run — with that fix
already committed — still shows the **original** "Authentication token is
invalid for tenant 'default'" message, unchanged, for 12 checks across
`billing_gate_dispatch`, `notification_config_event_scope/lifecycle/rejections`,
`read_tool_idempotency` (`list_creatives_with_idempotency_key`),
`webhook_emission` (4 checks), and two `media_buy_seller` checks
(`sync_creatives`, `sync_accounts`). Since the masking fix did NOT change the
observed message, this proves the failure is a genuine, deterministic
`(None, None)` result — no exception is being raised at all; the token+tenant
combination truly doesn't resolve for these specific calls, while the
identical `ci-test-token` resolves fine for `get_products`/`create_media_buy`
in the same run. Checked whether `webhook_emission`/`read_tool_idempotency`
declare a test-kit auth override the way `billing_gate_dispatch` does (which
would explain that one storyboard) — they don't, so that explanation doesn't
generalize. Needs live wire-level tracing (curl/tcpdump) to find the actual
divergence; filed as `salesagent-xg5w.11`.

### New failure surface: `AUTH_REQUIRED` on `get_products` in several storyboards

Because `get_adcp_capabilities` now returns (schema-invalid but) real data
instead of rejecting outright, the capability-driven selection now resolves
**44 storyboards** (vs 25 in SB-1b) — including the entire `media_buy_seller`
family, previously never reached. Several of these hit a new failure class:
`get_products` (a discovery/`AUTH_OPTIONAL_TOOLS` tool) rejects with
"`AUTH_REQUIRED`: Authentication required by tenant policy" for specific
storyboard steps (`error_compliance/missing_fields`,
`stale_response_advisory/no_stale_on_healthy_upstream`, most of
`media_buy_seller`'s `get_products_brief`/`get_products_canonical_format`
steps). Not root-caused here — noted for SB-1c/next-baseline triage, since the
much larger selection surface this run reveals means the "25 executed / 10
missing-tools" numbers in this report's main body are now stale and need a
fresh SB-1c-style reconciliation pass.

### Summary counts (schema_version 2, `sb1d-summary.json`)

`overall_status: partial` — 204 total steps: 7 passed, 47 failed, 150 skipped
(33 `prerequisite_failed`, 53 `missing_test_controller`, 48 `not_applicable`, 4
`missing_tool`, 1 `peer_branch_taken`, 11 `unsatisfied_contract`). Not directly
comparable to SB-1b's 72-failing-checks/25-storyboards figure — the storyboard
selection surface itself changed (44 vs 25 executed) because fixing capability
discovery unlocked a much larger set of storyboards to attempt, most of which
immediately hit the new findings above rather than passing cleanly. A clean
apples-to-apples before/after comparison needs the `get_adcp_capabilities`
schema bug (`salesagent-xg5w.12`) fixed first.

### Artifacts (this addendum)

- `sb1b-runner/results/sb1d-full.json` — full `ComplianceResult`, same shape as `sb1b-full.json`.
- `sb1b-runner/results/sb1d-summary.json` — narrow summary artifact.
- `sb1b-runner/results/smoke-webhook.json` — single-storyboard smoke test (post-fix).
- `sb1b-runner/results/sb1d-stderr.log` — the run's `STORYBOARD-FAIL` stderr summary.

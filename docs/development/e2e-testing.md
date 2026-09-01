# End-to-end testing

This guide explains how this repository tests against a live, containerized
server: what the stack is, which suites drive it, how they share (and protect)
its database, and how to debug a run that misbehaves. Read the first section
before anything else — the single most common e2e mistake here is running the
wrong suite and drawing a conclusion from the wrong green result.

## Two suites share the name "e2e"

"E2E" names two different things in this repository. They share the Docker
stack but grade different contracts, run under different tox environments, and
fail for different reasons.

**`tests/e2e/` — the protocol pytest suite.**
The `test_*.py` modules under `tests/e2e/` are ordinary pytest that exercises
the live server over real HTTP through nginx: full AdCP lifecycle flows, A2A
protocol compliance, delivery webhooks, tenant isolation, schema compliance.
Runs as `tox -e e2e`.

**`e2e_rest` — a BDD wire transport.**
The BDD suite (`tests/bdd/`) runs every generated scenario across the wire
transports `a2a`, `mcp`, and `rest` in-process. When `BDD_E2E_ENABLED=true`,
`pytest_generate_tests` in `tests/bdd/conftest.py` appends a fourth
parametrization, `e2e_rest`, which replays the same scenario as real HTTP
against the live server. Runs as `tox -e bdd_e2e` (which executes
`pytest tests/bdd/ -k e2e_rest`); the in-process bulk runs as
`tox -e bdd_inprocess`.

The distinction matters because a green result only certifies what actually
ran. `tox -e e2e` passing says nothing about BDD scenario conformance over the
wire, and `tox -e bdd_inprocess` passing says nothing about the live server —
that environment pins `BDD_E2E_ENABLED=false`. If you changed server behavior
that a BDD scenario grades, the suite that must pass is `bdd_e2e`.


## The stack

Both suites talk to the same compose stack, defined in
`docker-compose.e2e.yml`:

| Service | Role | Why it exists |
|---------|------|---------------|
| `postgres` | One Postgres instance holding every database the run uses | Single DB service; isolation comes from database names, not containers |
| `adcp-server` | The application under test (FastAPI, all protocols on one port) | The thing being graded |
| `proxy` | nginx in front of `adcp-server`, plaintext `:8000` | Tests go through the same reverse proxy production does |
| `tls-proxy` | A second nginx listener terminating TLS on `:8443` for the `*.adcp.test` origins | Serves real HTTPS from a generated private CA so https behavior is true, not asserted |
| `webhook-capture` | Long-lived webhook receiver (`tests/e2e/webhook_capture_service.py`) | Captures the server's outbound webhook deliveries; delivery arrives over TLS, readback is a plain-HTTP test control plane |
| `creative-agent` + `creative-pg` | A pinned in-network creative agent with its own registry DB | The live public agent drifts and rate-limits; it is blackholed in `adcp-server`'s `extra_hosts` so a regression fails instantly |
| `tests` | The in-network test runner (profile `runner`) | Runs tox inside the compose network so suites reach services by name |

Three properties of this stack shape everything else in this guide.

**The base compose file publishes no host ports.** Every service is reached by
service name (`postgres:5432`, `proxy:8000`) on the stack's own bridge
network. Each `docker compose -p <project>` gets an isolated network, so any
number of stacks can run concurrently with zero port coordination. The paths
that run pytest on the host instead overlay `docker-compose.e2e.ports.yml`,
which publishes loopback ports (`POSTGRES_PORT`, `ADCP_SALES_PORT`,
`ADCP_TLS_PORT`, `WEBHOOK_CAPTURE_PORT`). Never add that overlay to the
in-network runner — it would reintroduce the cross-stack collision surface the
in-network design removes.

**TLS is served for real.** `scripts/dev/ensure-test-tls.sh` generates a
private CA and a leaf covering `*.adcp.test` into `.test-tls/` before any
`up`; `tls-proxy` fronts every HTTPS origin the stack dials
(`proxy.adcp.test`, `creative-agent.adcp.test`, `webhooks.adcp.test`) through
dotted network aliases on one service. Startup performs a verified handshake
against the CA — a listener that half-starts is a hard failure, not a silent
fallback to plaintext. The egress reasoning behind this design — why every
outbound origin is TLS-fronted and what the seam refuses — lives in
[Outbound egress](../security/outbound-egress.md); don't re-derive it here.

**The stack opens the private-address hatch.** Every origin on a compose
network resolves to a private bridge address, so `adcp-server` runs with
`ADCP_OUTBOUND_ALLOW_PRIVATE=true`. The consequence: no e2e or `bdd_e2e`
scenario in this stack can grade a private-range egress refusal — that grading
stays in-process, in `tests/integration/test_outbound_http.py` and the BDD
refusal scenarios, which pin the flag closed per case. Scheme refusal and the
supplement-range refusals remain gradeable live. Again, see
[Outbound egress](../security/outbound-egress.md) for the full posture.

## Two databases, one Postgres

The `postgres` service holds two databases with different owners:

- `/adcp` — the **server's** database. `adcp-server` reads and writes it; it
  is the state behind every HTTP response an e2e test sees.
- `/adcp_test` — the **suite** database. Integration, in-process BDD, and
  admin tests provision and query it directly.

The suites that drive the live server must look at the server's database, not
the suite one. The `[testenv:e2e]` block in `tox.ini` does this with a
per-suite override:

```ini
DATABASE_URL = {env:E2E_DATABASE_URL:{env:DATABASE_URL:}}
```

In the in-network runner, `docker-compose.e2e.yml` exports
`E2E_DATABASE_URL=postgresql://...@postgres:5432/adcp`, so the e2e and ui
environments see `/adcp` while integration/bdd/admin — which share the same
runner container — keep the runner's `DATABASE_URL` of `/adcp_test`. On the
host path `E2E_DATABASE_URL` starts unset; `tests/e2e/conftest.py` then
derives it from the stack's published Postgres port
(`localhost:<POSTGRES_PORT>/adcp`) with `setdefault`, so a stale
`DATABASE_URL` inherited from some other harness cannot silently point the
direct-DB helpers at a database the server never reads.

Three suites mutate the server database, and they must not overlap:

- `e2e` seeds the `ci-test`/`iso-test` tenants
  (`scripts/setup/init_database_ci.py`).
- `ui` seeds the default tenant.
- `bdd_e2e` **truncates every table** before each `e2e_rest` scenario
  (`_reset_e2e_db` in `tests/bdd/conftest.py`).

`tox.ini` therefore chains them: the `ui` environment declares
`depends = e2e`, and the `bdd` and `bdd_e2e` environments declare
`depends = e2e, ui`. That serializes the server-DB group under `tox -p` while
unit/integration/admin still run fully parallel. This is not
housekeeping: run the group in parallel and bdd's truncations land inside
e2e's window, deleting the tenants e2e just seeded — presenting as
`Tenant with subdomain 'ci-test' not found`, invisible to any targeted rerun
because the same tests pass alone. The banner above `[testenv:ui]` in
`tox.ini` carries the same warning.

## The e2e_rest transport and its ledger

`e2e_rest` exists so the exact scenarios that grade the in-process wire
transports also grade the deployed server — same Gherkin, same step
definitions, same assertions, dispatched as real HTTP. The
`e2e_stack` fixture in `tests/bdd/conftest.py` reads `E2E_BASE_URL` /
`E2E_POSTGRES_URL` and health-checks the server; for an `e2e_rest` test a
missing stack is a hard error, never a skip, because the transport is only
parametrized when `BDD_E2E_ENABLED=true` — you asked for it, so it must run.

Not every scenario passes over real HTTP yet.
`tests/bdd/e2e_rest_known_failures.txt` is a ledger of node IDs that
`tests/bdd/conftest.py` marks `xfail(strict=False)`: genuine production gaps,
unseeded server-side state, or harness observability gaps, each annotated with
the gap it represents. `tests/unit/test_e2e_rest_ledger_state.py` locks the
file's shape.

**The only job that grades the ledger is a bdd-in-network run** — the
"BDD In-Network (e2e_rest)" job in `.github/workflows/ci.yml`, which runs
`./run_all_tests.sh bdd_e2e`. In-process runs never execute the `e2e_rest`
parametrizations, so they can neither confirm a graduation nor catch a
regression there. If your change touches behavior a ledgered scenario covers:

1. Run `./run_all_tests.sh bdd_e2e` (or let the CI job run).
2. If a ledgered scenario now passes, graduate it — remove its line **in the
   same change**, following the
   [xpass graduation workflow](../../.claude/rules/workflows/xpass-graduation.md).
   One scenario at a time, with the inspection evidence the workflow demands.
3. If a previously passing scenario now fails, that is a regression; the
   ledger only ever shrinks.

### A green run that proves nothing: the xdist silent drop

This hazard earns its own section because its failure mode is a **passing**
suite.

`BDD_E2E_ENABLED=true` is incompatible with xdist. Under `-n>0`, the xdist
worker's collection never reaches the `pytest_generate_tests` state that
appends the `e2e_rest` transport, so every scenario silently collects with
only its in-process parametrizations. Nothing fails. Nothing skips. The suite
goes green having never once dispatched HTTP at the live server — and a reader
of that green run concludes the deployed server conforms when it was never
asked.

`pytest_configure` in `tests/bdd/conftest.py` turns this into a hard
`pytest.UsageError`: `BDD_E2E_ENABLED=true` together with `-n>0` refuses to
start. Two configurations are exempt, each because the drop cannot go
unnoticed there:

- `E2E_PER_WORKER=1`: each xdist worker targets its **own** server container
  and database (see the next section), so parallel `e2e_rest` is legal — and
  the `bdd_e2e` environment's `-k e2e_rest` makes pytest exit 5 ("no tests
  collected") if the transport were ever dropped, so a silent drop cannot
  present as green.
- `-n 0`: collection runs in-process, so the transport is parametrized
  normally. The in-network compose default pins `BDD_XDIST_N=0` for exactly
  this reason.

If you hit the `UsageError`, the fix is one of those two shapes — never
exporting the flag away.

## Worker counts are computed, not chosen

`run_all_tests.sh` sizes every xdist worker count from the **Docker VM's**
memory (`docker info --format '{{.MemTotal}}'`) and the core count — not from
host RAM, because on a Mac those differ wildly and every worker imports the
whole application. Three tiers (the script is the authority):

| Docker VM memory | `UNIT_XDIST_N` | `INTEGRATION_XDIST_N` | `E2E_WORKERS` |
|------------------|----------------|------------------------|---------------|
| ≥ 64 GB | min(cores, 16) | 8 | 8 |
| ≥ 32 GB | min(cores, 8) | 4 | 2 |
| below (default Docker Desktop) | cores / 2, floor 2 | 4 | 0 |

Every export uses the `${VAR:-computed}` pattern, which means **any value you
have exported silently wins, with no warning** — and on a laptop-tier VM an
exported worker count produces `-9` (SIGKILL) suite deaths from the VM's
out-of-memory killer, reading as mysterious test failures. If a full run dies
with exit code -9 or reports
`collected N but reported 0`, check your environment for stale
`*_XDIST_N`/`E2E_WORKERS` exports before suspecting the tests. The safe
default is to never export these variables.

Two related pins, both load-bearing:

- `PYTEST_XDIST_AUTO_NUM_WORKERS` is set to 1 by `docker-compose.e2e.yml`, so
  any `-n auto` inside the runner resolves to one worker instead of one
  app-loading process per CPU — which is an in-container OOM.
- `BDD_XDIST_N` must **derive from** `E2E_WORKERS`, never be set directly.
  When `E2E_WORKERS > 0`, `run_all_tests.sh` swaps the serial `bdd` env for
  the `bdd_inprocess,bdd_e2e` split, exports
  `BDD_XDIST_N=${BDD_XDIST_N:-$E2E_WORKERS}` for the in-process half, and
  provisions `E2E_WORKERS` isolated per-worker stacks — one `adcp-server`
  container plus one TLS sidecar per xdist worker, each on its own database
  (`adcp_gwN`, cloned from a migrated template) — then runs `bdd_e2e` with
  `E2E_PER_WORKER=1` and `BDD_E2E_XDIST_N=$E2E_WORKERS`. That provisioning is
  what makes parallel `e2e_rest` legal under the guard above.

## Choose a command

This table extends the decision tree in the root `CLAUDE.md` with the e2e
distinctions this page teaches.

| You want to grade | Command | What it starts |
|-------------------|---------|----------------|
| Everything (the default full gate) | `./run_all_tests.sh` | Full stack in-network, all six suites via `tox -p`, auto-teardown |
| The protocol pytest suite only | `./run_all_tests.sh e2e` | Full stack in-network, `tox -e e2e` |
| BDD scenarios over real HTTP (the ledger) | `./run_all_tests.sh bdd_e2e` | Full stack in-network, `tox -e bdd_e2e` |
| BDD scenarios in-process only | `tox -e bdd_inprocess` | Nothing (needs a suite `DATABASE_URL`) |
| One e2e test, iterating | `make test-stack-up`, then `source .test-stack.env && tox -e e2e -- -k <name>` | Host-side stack with published ports; stays up between runs |
| One e2e test, no manual lifecycle | `scripts/run-test.sh tests/e2e/test_foo.py -x` | Auto-detects and starts the full stack |
| A targeted non-suite run | `./run_all_tests.sh ci <pytest-target> [args]` | Host-side stack (delegates to `run_all_tests_host.sh`) |

`run_all_tests.sh` with no arguments (or `ci`) is the in-network path: the
runner executes inside the compose network, no host ports exist, and
concurrent invocations cannot collide. `quick` and `ci <target>` delegate to
`run_all_tests_host.sh`, which runs pytest on the host against a
`scripts/test-stack.sh` stack with published loopback ports.

## Iterate on one failing e2e test

Paying a full stack build-up-teardown cycle per attempt is the slow way. The
fast loop:

1. Start a host-side stack once: `make test-stack-up`. This builds the images,
   overlays the ports file, waits for Postgres, the server, and a **verified**
   TLS handshake, then writes the allocated ports and `DATABASE_URL` to
   `.test-stack.env`.
2. In every shell you test from: `source .test-stack.env`.
3. Iterate: `tox -e e2e -- -k <test_name> -x`, or
   `uv run pytest tests/e2e/test_foo.py::test_bar -x -v`. Because
   `.test-stack.env` exports `ADCP_TESTING=true`, the session-scoped
   `docker_services_e2e` fixture reuses the running stack instead of starting
   its own.
4. Inspect the server while the test runs:
   `docker compose -f docker-compose.e2e.yml -f docker-compose.e2e.ports.yml -p <project> logs -f adcp-server`
   (the project name is in `.test-stack.env`), and the server database at
   `psql "postgresql://adcp_user:...@127.0.0.1:${POSTGRES_PORT}/adcp"`.
5. Tear down when done: `make test-stack-down`.

Without `ADCP_TESTING=true` (and without `--skip-docker`), running
`pytest tests/e2e/...` takes the standalone branch of `docker_services_e2e`:
it builds and starts its own stack on dynamically allocated ports (server
20000–25000, Postgres 25000–30000, TLS 15000–20000, webhook capture
30000–32000) and tears it down at session end. That is the branch GitHub CI's
host-side `pytest tests/e2e` path uses; for local iteration it pays the full
cycle every session, so prefer the loop above.

For an `e2e_rest` BDD scenario, the supported iteration path is the
in-network runner: `./run_all_tests.sh bdd_e2e`. It is slower per cycle than
the pytest loop, but it is the configuration the ledger and CI job are
defined against; a scenario's pass/fail state on any other configuration is
not evidence about the ledger.

## Read the results, not the scrollback

Every suite writes a pytest JSON report, and the runners copy the reports of
exactly the suites that ran:

- In-network runs: `test-results/innet_<ddmmyy_HHMM>/` (UTC timestamp), plus a
  `.suites` manifest naming which suites this invocation ran.
- Host runs: `test-results/<ddmmyy_HHmm>/` (local time); the last 10
  directories are kept.

The JSON is the authoritative record:

- A long run's terminal output can vanish — background processes die, CLI
  connections drop. The reports persist.
- A suite that is stopped mid-run can truncate its report;
  `scripts/check_truncated_reports.py` fails the run when a report's
  collected/reported counts disagree, so a half-run cannot read as green.
- A suite that ran but produced no report is an **error**, not an omission —
  it died before writing one, and the runner exits nonzero for it.
- `.tox/` persists between runs, so both runners purge old reports before
  running; a report exists only if the current run produced it. Trust the
  directory plus its `.suites` manifest, never a lone JSON file's timestamp.

A useful corollary: when the process exit code is nonzero but every report in
the directory shows zero failures, the failure is outside the suites. The
runner prints a diagnosis for the common case — Docker's own 125/126/127
"could not run the container" range after all suites already finished.

## Failure modes and what they actually mean

| Symptom | What it usually means | Where to look |
|---------|----------------------|---------------|
| `Tenant with subdomain 'ci-test' not found` in e2e, though the seed ran | Another suite truncated the server DB mid-window — the serialization in `tox.ini` was bypassed (for example, by running server-DB envs in parallel manually) | The `depends` banner above `[testenv:ui]` in `tox.ini` |
| `Server not ready after 60s (port N)` across all of e2e, or `the live E2E stack is unreachable` across all of `bdd_e2e` | The stack never came up; the tests are casualties, not causes. One infrastructure fault, thousands of downstream errors | `docker compose ... logs adcp-server`; the runner's own health-wait output |
| `PermissionError: /app/logs/audit.log` at collection, or the server dying at import | Bind-mount file-ownership race between `adcp-server` (uid 1001) and the runner. The runners pre-create world-writable log files to prevent it | The `logs/` block in `run_all_tests.sh` |
| Suite dies with exit code -9, or a report says `collected N but reported 0` | The Docker VM's out-of-memory killer. Almost always an exported worker-count override defeating the computed tiers | Your shell environment: `UNIT_XDIST_N`, `INTEGRATION_XDIST_N`, `E2E_WORKERS`, `BDD_XDIST_N` |
| `pytest.UsageError: BDD_E2E_ENABLED=true is incompatible with xdist` | The guard against the silent transport drop fired | The silent-drop section in this guide |
| nginx 502, or connection refused on a host-path port | Cross-stack host-port collision (the TOCTOU window in port allocation), or an abandoned stack squatting the port | `scripts/test-stack.sh` retries with fresh ports and reaps stacks older than 90 minutes; `docker ps --filter name=adcp-test-` |
| An https e2e test fails with a certificate error | Stale or missing `.test-tls/` material, or the process doesn't trust the generated CA | `scripts/dev/ensure-test-tls.sh`; `E2E_CA_BUNDLE`; note `SSL_CERT_FILE` must point at the **combined** bundle, never the private CA alone |
| A report in `test-results/` shows failures for code that no longer exists | You are reading a stale report from a previous run | The directory's `.suites` manifest; rerun and read the fresh directory |
| Exit code 125/126/127 with all-green reports | Docker's runner-level failure after the suites finished | The runner's closing diagnostic; the Docker daemon, not the tests |

## Related reading

- [Outbound egress](../security/outbound-egress.md) — the TLS front, the
  egress seam, and why the stack's SSRF posture is what it is.
- [Xpass graduation workflow](../../.claude/rules/workflows/xpass-graduation.md)
  — the per-scenario protocol for retiring ledger entries.
- [CI pipeline](ci-pipeline.md) — where these suites run in GitHub Actions.
- `tests/e2e/README.md` — directory-local notes for the protocol pytest
  suite.

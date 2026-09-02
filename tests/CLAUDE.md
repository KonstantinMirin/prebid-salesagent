# Test Architecture

This file is the authoritative guide to writing tests in this project.
**Agents must read this before writing any test code.**

## The Harness System (Use This)

The test harness (`tests/harness/`) is the central testing abstraction. It manages mocks,
identity, database sessions, and multi-transport dispatch. **All new tests must use it.**

### How it works

```python
from tests.harness import DeliveryPollEnv

with DeliveryPollEnv(tenant_id="t1", principal_id="p1") as env:
    # env auto-patches external dependencies, creates identity, binds DB session to factories
    tenant = TenantFactory(tenant_id="t1")
    principal = PrincipalFactory(tenant=tenant, principal_id="p1")
    buy = MediaBuyFactory(tenant=tenant, principal=principal)

    env.set_adapter_response(buy.media_buy_id, impressions=5000)
    result = env.call_impl(media_buy_ids=[buy.media_buy_id])

    assert result.deliveries[0].impressions == 5000
```

### Environment hierarchy

| Class | Mode | Domain | File |
|-------|------|--------|------|
| `BaseTestEnv` | Unit (mocked DB) | Base class | `tests/harness/_base.py` |
| `IntegrationEnv` | Integration (real DB) | Base class | `tests/harness/_base.py` |
| `DeliveryPollEnv` | Integration | Delivery metrics | `tests/harness/delivery_poll.py` |
| `DeliveryPollEnvUnit` | Unit | Delivery metrics | `tests/harness/delivery_poll_unit.py` |
| `WebhookEnv` | Integration | Webhook delivery | `tests/harness/delivery_webhook.py` |
| `CircuitBreakerEnv` | Integration | Circuit breaker | `tests/harness/delivery_circuit_breaker.py` |
| `CreativeSyncEnv` | Integration | Creative sync | `tests/harness/creative_sync.py` |
| `CreativeFormatsEnv` | Integration | Format discovery | `tests/harness/creative_formats.py` |
| `CreativeListEnv` | Integration | Creative listing | `tests/harness/creative_list.py` |
| `ProductEnv` | Integration | Product catalog | `tests/harness/product.py` |
| `ProductEnvUnit` | Unit | Product catalog | `tests/harness/product_unit.py` |
| `MediaBuyUpdateEnv` | Unit | Media buy updates | `tests/harness/media_buy_update.py` |

### Key capabilities

- **`EXTERNAL_PATCHES`**: Dict of `{name: patch_target}` — auto-started as `unittest.mock.patch` on `__enter__`
- **`ASYNC_PATCHES`**: Set of names that need `AsyncMock` instead of `MagicMock`
- **`env.mock[name]`**: Access active mocks by name
- **`env.call_impl()`**: Call the `_impl` function directly
- **`env.call_a2a()`**: Call through A2A transport wrapper
- **`env.call_mcp()`**: Call through MCP transport wrapper
- **`env.get_rest_client()`**: Get a Starlette `TestClient` for REST calls
- **`env.call_via(transport, **kwargs)`**: Dispatch through any transport

### Transport dispatching

There are three transports: **A2A, MCP and REST**. Every `_impl` function is
wrapped by all three, each dispatches in-process, and each has an `E2E_*`
variant that dispatches the same call over real HTTP
(`tests/harness/transport.py`). Tests verify behavior across the transports
that grade them:

```python
from tests.harness.transport import Transport

for transport in [Transport.A2A, Transport.MCP, Transport.REST]:
    result = env.call_via(transport, media_buy_ids=[buy.media_buy_id])
    assert result.is_success
```

BDD parametrizes exactly these three, plus `e2e_rest` when the in-network
stack enables it — a scenario grades AdCP wire conformance, so it must run
where there is a wire.

A direct call to `_impl` is not a transport and grades no wire; `Transport.IMPL`
is legacy and is removed by #1721 — do not write new tests against it.

### Symbol index

Check `.agent-index/harness/` for quick lookup of all harness classes and methods:
- `base.pyi` — BaseTestEnv, IntegrationEnv interfaces
- `transport.pyi` — Transport enum, TransportResult, dispatchers
- `envs.pyi` — Domain-specific env classes with methods

## Test Types

### Unit Tests (`tests/unit/`)

Fast, isolated. No database. External deps mocked via harness `BaseTestEnv` or direct `unittest.mock`.

```bash
make quality          # Runs unit tests as part of quality gates
tox -e unit           # Unit tests only
```

### Integration Tests (`tests/integration/`)

Real PostgreSQL. Use `IntegrationEnv` subclasses or the `integration_db` fixture.
Factory-boy factories create test data — the harness binds sessions automatically.

```bash
tox -e integration
scripts/run-test.sh tests/integration/test_foo.py -x   # Single test with auto-DB
```

### BDD Tests (`tests/bdd/`)

Behavioral tests from AdCP requirements. Feature files are auto-generated from spec.
Step definitions are organized in two layers:

- **`tests/bdd/steps/generic/`** — Reusable steps (auth, entity setup, assertions)
- **`tests/bdd/steps/domain/`** — Use-case-specific steps (delivery, creative formats)

Every BDD scenario is automatically parametrized across the wire transports (A2A, MCP, REST —
plus `e2e_rest` in-network) unless tagged with a specific transport. The `ctx`
fixture is a mutable dict shared across steps, with `ctx["env"]` holding the
harness environment.

```bash
tox -e bdd
```

### E2E Tests (`tests/e2e/`)

Full Docker stack (app + nginx + Postgres). No mocking.

```bash
./run_all_tests.sh    # Full suite including e2e
```

### Admin Tests (`tests/admin/`)

Admin UI tests against the Docker stack.

## Factory System (Use This)

**All test data must be created via factory-boy factories in `tests/factories/`.**

### ORM Factories (for database entities)

```python
from tests.factories import TenantFactory, PrincipalFactory, MediaBuyFactory

tenant = TenantFactory(tenant_id="t1")                    # Creates Tenant ORM model in DB
principal = PrincipalFactory(tenant=tenant)                # Auto-links to tenant
buy = MediaBuyFactory(tenant=tenant, principal=principal)  # Full media buy with defaults
```

### Pydantic Factories (for non-ORM models)

```python
from tests.factories import FormatFactory, FormatIdFactory

fmt = FormatFactory(format_id="display_300x250_image")     # Format Pydantic model
fid = FormatIdFactory(id="display_300x250_image")          # FormatId model
```

### Identity helper

```python
identity = PrincipalFactory.make_identity(tenant_id="t1", principal_id="p1")
```

Single source of truth for `ResolvedIdentity` in tests — never construct it manually.

### Session binding

You do NOT manage sessions. `IntegrationEnv.__enter__()` creates a session and binds it
to all factories automatically. Just use factories inside a `with env:` block.

## Obligation Tests

Tests tagged with `Covers: <obligation-id>` verify behavioral contracts.
`docs/test-obligations/` holds curated inputs only
(`storyboard-issue-map.yaml`, `storyboard-wireability.yaml`,
`bdd-traceability.yaml`); there is no committed obligation document to tag
against, so do not add new `Covers:` tags. The rules below bind any test that
carries one.

### Five hard rules

1. MUST import from `src.*`
2. MUST call a production function (not just import it)
3. MUST assert on production output
4. MUST use factory-boy factories for data setup
5. MUST NOT be mock-echo only (asserting mock return values)

## HOWTO: The Three Moves of a Test

Every behavioral test makes the same three moves: put the world in a starting
state (Given), run production through a transport (When), and check what the
run produced (Then). Each move has exactly one recipe.

### How to set state in a Given step

**Goal:** starting state lives in two places — database entities, and the
collaborators the env manages (adapter, format registry, HTTP origins).
Program both through the env.

**The call:** open the domain env, create entities with the factory-boy
factories from `tests/factories`, and program collaborators with the env's
`set_*` methods:

```python
from tests.factories import TenantFactory, PrincipalFactory, MediaBuyFactory
from tests.harness import DeliveryPollEnv

with DeliveryPollEnv(tenant_id="t1", principal_id="p1") as env:
    tenant = TenantFactory(tenant_id="t1")
    principal = PrincipalFactory(tenant=tenant, principal_id="p1")
    buy = MediaBuyFactory(tenant=tenant, principal=principal)
    env.set_adapter_response(buy.media_buy_id, impressions=5000)
```

`IntegrationEnv.__enter__()` opens the session and binds it to every factory,
so the test manages no session at all — no `get_db_session()`, no
`session.add()`. Each domain env exposes typed state-programming methods:
`set_adapter_response(...)` / `set_adapter_error(exc)` (delivery),
`set_registry_formats([...])` (`CreativeFormatsEnv`), `set_http_status(...)` /
`set_http_sequence([...])` (webhook local origin), `set_policy_blocked(...)` /
`set_policy_approved()` (`ProductEnv`). `.agent-index/harness/envs.pyi` lists
the full set per env; anything else the env patches is reachable as
`env.mock[name]` — never hand-roll a `mock.patch` stack for a dependency the
env already manages. Identity comes from
`PrincipalFactory.make_identity(tenant_id=..., principal_id=...)`, the single
source of truth for `ResolvedIdentity`.

**The trap:** import factories from `tests/factories`, never `tests/fixtures`
— the dict-based namesakes there return plain dicts, not ORM models. The
structural guard `tests/unit/test_architecture_repository_pattern.py` fails
new `get_db_session()` / `session.add()` calls in test bodies at
`make quality`, and its allowlist only shrinks; tests that predate the
harness are legacy — do not copy their setup.

### How to check a field in the response

**Goal:** assert the *value* of a field on the response the `When` step
produced, through the transport-independent readers on `TransportResult`.

**The call:**

```python
result = env.call_via(transport, media_buy_ids=[buy.media_buy_id])
assert result.is_success
assert result.payload.deliveries[0].impressions == 5000
```

Two readers, two jobs. `result.payload` is the typed response model — the
default for checking values. `result.require_wire()` is the serialized body
the buyer actually received — required when the assertion is about
serialization itself (field names, key presence/absence, wire types), because
`payload` fields are already coerced to their declared types and cannot catch
a serialization regression; it raises loudly on a success with no stashed
body instead of falling back to re-serializing the payload. In BDD steps the
same pair is `require_payload(ctx)` and `wire_field(ctx, "field")` /
`wire_dict(ctx)` from `tests/bdd/steps/_outcome_helpers.py`.

**The trap — a Then that grades the Given.** The value you check must be one
the `When` produced, having made the full trip Given → production → response.
Three reads that look like assertions but re-read the setup instead:

- reading the factory object or DB row the Given wrote
  (`assert buy.status == "active"`) — passes even when the When does nothing;
- reading the mock the Given programmed
  (`env.mock["adapter"].return_value...`) — mock-echo, hard rule 5: the
  assertion and the setup are the same object;
- recomputing the expected value from `ctx` / env state the Given stashed,
  rather than reading `ctx["result"]` — the same circle, one hop longer.

The test for vacuity: if the When step were deleted, could the Then still
compute its actual value? Only the `TransportResult` returned by `call_via`
(stashed as `ctx["result"]` in BDD) came out of the run. Plant a distinctive
value in the Given (`impressions=5000`, not a factory default) and read it
back off the result — then the assertion can only pass if production carried
the value through.

### How to validate an error response

**Goal:** assert on the real JSON error envelope the buyer receives — code,
recovery, message.

**The call:** `assert_envelope_shape()` from
`tests/helpers/envelope_assertions.py`, on `result.wire_error_envelope`:

```python
from tests.helpers import assert_envelope_shape

result = env.call_via(transport, **bad_request)
assert result.is_error
assert_envelope_shape(
    result.wire_error_envelope,
    "VALIDATION_ERROR",
    recovery="correctable",
    message_substr="budget must be positive",
)
```

`recovery` is required — it pins the buyer-facing retry semantics. BDD steps
asserting a rejection that names a request field use
`assert_wire_rejection(ctx, code, recovery=..., field=...)` from
`tests/bdd/steps/_outcome_helpers.py`; step definitions never hand-roll
envelope parsing.

**The trap:** the harness also reconstructs a typed `AdCPError` from the wire
(`result.error`). Asserting on that object — `isinstance(...)`,
`.error_code` — grades the reconstruction rather than the real JSON response,
and the reconstruction is lossy. Full policy: § Error Verification Policy
below.

## Quick Reference: Writing a New Test

### Integration test with harness

```python
import pytest
from tests.factories import TenantFactory, PrincipalFactory, MediaBuyFactory

@pytest.mark.requires_db
class TestDeliveryReturnsMetrics:
    """Delivery poll returns adapter metrics for active media buys."""

    def test_returns_impressions(self, integration_db):
        from tests.harness import DeliveryPollEnv

        with DeliveryPollEnv(tenant_id="t1", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="p1")
            buy = MediaBuyFactory(tenant=tenant, principal=principal)

            env.set_adapter_response(buy.media_buy_id, impressions=5000)
            result = env.call_impl(media_buy_ids=[buy.media_buy_id])

            assert result.deliveries[0].impressions == 5000
```

### Unit test (no DB)

```python
class TestFormatResolution:
    def test_unknown_format_raises_not_found(self):
        from tests.harness import CreativeFormatsEnv
        from src.core.exceptions import AdCPNotFoundError

        with CreativeFormatsEnv() as env:
            env.mock["registry"].get_format.return_value = None
            with pytest.raises(AdCPNotFoundError):
                get_format("nonexistent_format")
```

### BDD step definition

```python
from tests.bdd.steps._outcome_helpers import wire_field

@then(parsers.parse('the response contains {count:d} formats'))
def then_response_has_formats(ctx, count):
    assert len(wire_field(ctx, "formats")) == count
```

## Error Verification Policy

### Principle: Assert on the Wire Envelope, Not Reconstructed Exceptions

The test harness reconstructs `AdCPError` subclasses from wire responses so tests can
use `isinstance()` and `.error_code`. This reconstruction is **lossy** — e.g.,
`AdCPAuthenticationError` and `AdCPAuthorizationError` both map to `AUTH_REQUIRED` on
the wire, so reconstruction always produces `AdCPAuthenticationError`. Tests that assert
on reconstructed exceptions verify the reconstruction layer, not the actual wire shape.

**New error-path tests MUST assert on the wire error envelope** as the primary authority.
The wire envelope is the buyer-facing contract — it is what the AdCP spec defines and
what storyboard runners parse.

### How to assert on the wire envelope

Use `assert_envelope_shape()` from `tests/helpers/envelope_assertions.py` on
`result.wire_error_envelope` — the recipe, with a worked example, is
§ "How to validate an error response" above.

### What to assert

`recovery` is a **required** keyword argument — every call pins the buyer-facing
retry semantics (`correctable` / `transient` / `terminal`). Omitting it is a
`TypeError`, not a soft default: silent drift between a typed exception's recovery
and the wire is exactly the regression this helper exists to catch.

| Layer | What to check | How |
|-------|--------------|-----|
| Wire shape | Two-layer envelope structure | `assert_envelope_shape(envelope, code, recovery="correctable")` |
| HTTP status | REST status code | `assert result.envelope["status_code"] == 400` |
| Error code | Machine-readable wire code | `assert_envelope_shape(envelope, "VALIDATION_ERROR", recovery="correctable")` |
| Message | Human-readable content | `assert_envelope_shape(envelope, code, recovery=..., message_substr="...")` |
| Recovery | Buyer retry semantics | `assert_envelope_shape(envelope, code, recovery="correctable")` |

Assertions on the reconstructed exception — `isinstance(error, ...)`,
`error.error_code == ...`, `error.recovery == ...` — verify the
reconstruction layer, not the wire. Never write one. Tests that predate this
policy still assert on reconstructed exceptions; migrate them to the envelope
when touched.

### TransportResult.wire_error_envelope

`TransportResult` exposes `wire_error_envelope: dict | None` — the two-layer
error envelope captured at the transport boundary, from the transport's real
wire bytes. Populated on error; `None` on success. This is the canonical
field for error verification.

**Authenticity per transport (matters for what regressions the field catches):**

| Transport | `wire_error_envelope` source                                          | Catches a regression in...                                |
|-----------|-----------------------------------------------------------------------|-----------------------------------------------------------|
| REST      | HTTP response body (real wire)                                        | exception handler + envelope serialization + HTTP framing |
| MCP       | JSON string in `ToolError`, else the real envelope stashed on the reconstructed error by `_envelope_to_adcp_error` — never synthesized | `_handle_tool_exception` + `build_two_layer_error_envelope` |
| A2A       | Failed Task's artifact DataPart, stashed by `_envelope_to_adcp_error` | `on_message_send` + `_serialize_for_a2a` + envelope build |

Every transport captures the envelope that actually came back; none
synthesizes one. A synthesized value would be either redundant or a mask over
a lost capture — an assertion on it would grade the harness rebuilding an
envelope from the exception it had just caught, which passes whether or not
production emitted anything. The invariant that MCP stashes its real envelope
rather than synthesizing is pinned by
`tests/unit/test_harness_mcp_never_synthesizes.py`.

`result.error` (reconstructed exception) exists for tests that predate this
policy. Reconstruction is lossy — assert on `result.error_envelope()`, which
returns the captured wire envelope and RAISES when there is none, rather than
letting a dead wire path pass on a rebuilt shape; `error_envelope_or_none()`
is the sibling for callers that branch on envelope-presence as control flow
(an MCP dispatch can fail with a `ToolError` that is genuinely not an AdCP
envelope).

### TransportResult.has_wire — declared, never defaulted

`has_wire` is **required and keyword-only**. A default turns omission into a
silent claim — "this transport has no wire" — and omission is the one thing
that must not be silent, so leaving it out is a `TypeError`.

It is declared **per construction site, not per dispatcher class**. A wire
dispatcher legitimately builds results for requests that never left: a
missing-config guard, or a catch-all firing before anything was sent. Those are
`False` even on REST. The arm where a 2xx arrived and parsing then threw is
`True`, because the bytes did cross.

**`has_wire` governs the success path only — do not branch on it to decide
whether an error envelope exists.** It is `False` on every A2A and MCP error
(a catch-all arm may fire before anything was sent, and cannot tell which),
yet those dispatchers still capture a real envelope when one came back —
keying on `has_wire` would discard it. Read errors through
`error_envelope()` / `error_envelope_or_none()` instead.

### TransportResult.wire_response (success-path wire)

`TransportResult` also exposes `wire_response: dict | None` — the **serialized
success-path response body**, the success-path analogue of `wire_error_envelope`.
Populated on success by the REST dispatcher (HTTP body) and by the A2A/MCP
dispatchers **only when the env routes through `_run_a2a_handler` /
`_run_mcp_client`** (which stash the wire); `None` on error. Legacy
`_run_mcp_wrapper` and the direct `*_raw` wrappers do not stash, so
`wire_response` is `None` there too. `CreativeFormatsEnv` and
`CreativeListEnv` read it. Read it through `result.require_wire()`, which
raises on a success with no stashed body instead of falling through to a
harness-side reconstruction. Use it to assert the **actual serialized shape**
a buyer receives (e.g. the v3.1 `format_id` `{agent_url, id}` federation
contract on `list_creative_formats`) rather than the typed `payload`, whose
fields are already coerced to their declared types and so cannot catch a
serialization regression.

**Authenticity per transport:**

| Transport | `wire_response` source | Notes |
|-----------|------------------------|-------|
| REST | HTTP JSON body (`response.json()`) | Real wire; equals `raw_response.json()`. |
| MCP  | `ToolResult.structured_content` (real wire) | Stashed by `_run_mcp_client`. |
| A2A  | Full artifact DataPart (real wire) | Stashed by `_run_a2a_handler` BEFORE the `message`/`success` strip, so top-level envelope fields are present. |

See
`tests/integration/test_harness_wire_response.py` (pins that the field is real
wire, not a payload reconstruction) and
`tests/bdd/steps/domain/uc005_format_id_shape.py` (uses it for the format_id
federation contract; reusable by the `roundtrip-from-products` /
`third-party-agent` siblings).

## Infrastructure

| What you need | Command |
|---|---|
| Unit tests only | `make quality` |
| One integration test | `scripts/run-test.sh tests/integration/test_foo.py -x` |
| Full suite (all 5 envs) | `./run_all_tests.sh` |
| BDD only | `tox -e bdd` |
| Entity-scoped | `make test-entity ENTITY=delivery` |

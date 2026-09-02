# Architecture Principles

The rules that decide where code belongs in this codebase — and why. The
mechanics of how a request reaches business logic are in
[request-lifecycle.md](request-lifecycle.md); the boundary contract with
canonical examples is Critical Pattern #5 in [CLAUDE.md](../../CLAUDE.md) and
[patterns-reference.md](patterns-reference.md). This document is the layer
above both: six principles, each short enough to apply on sight.

The whole architecture is one symmetry:

```
wire ──► boundary: construct models, resolve identity ──► _impl(models → models) ──► boundary: serialize models ──► wire / DB / egress
```

Models are constructed on the way in, serialized on the way out, and the code
in the middle never touches anything else.

## 1. Logic lives in `_impl` — everything else is plumbing

**Rule.** Business logic lives in exactly one place: the `_impl` functions
under `src/core/tools/`. Everything before and after them — transports,
identity resolution, error translation, envelope parsing and creation — is
plumbing. If logic appears outside `_impl`, that placement is the defect,
regardless of whether the logic is correct.

**Illustration.** A budget rule added to the REST handler in
`src/routes/api_v1.py` would be logic the MCP and A2A callers never run. The
same rule inside `_create_media_buy_impl` runs identically for all transports,
because every wrapper calls the same function with the same
`ResolvedIdentity`.

**Consequence.** Adding a transport, or fixing a transport bug, never changes
behavior; changing behavior never touches a transport. The seam is enforced:
`_impl` may not import transport machinery
(`tests/unit/test_transport_agnostic_impl.py`), must accept `ResolvedIdentity`
rather than a transport context (`tests/unit/test_impl_resolved_identity.py`),
and every wrapper must forward every `_impl` parameter
(`tests/unit/test_architecture_boundary_completeness.py`). When unsure where a
change goes, use the [placement
table](request-lifecycle.md#where-does-my-change-go) in the request lifecycle.

## 2. Trust the database — never validate on read

**Rule.** We wrote what is in the database, and the stored shapes are designed
so that nothing we store can crash the application. Therefore **reads do not
validate**: read into Pydantic models and proceed. No `try/except` around
parsing our own rows, no fallback branches for shapes we would never have
written, no re-checking invariants the write path already guaranteed.

**Illustration.** JSON columns are declared with a model —
`JSONType(model=BrandReference)` in `src/core/database/json_type.py` — so the
column type itself materializes a typed model on read and serializes the model
on write. A repository method returns those models directly; the caller does
not inspect them for well-formedness first.

**Consequence.** Defensive re-validation is the instinct most newcomers arrive
with, and here it is the anti-pattern: it duplicates the write path's
guarantee, buries real bugs under fallbacks, and makes every read site a
policy decision. If a read *does* blow up, the defect is on the write path (or
in a migration) — fix it there once, not at N read sites. This principle is
carried by the typed column/repository seam and code review rather than a
single guard; its defensive-branch edge is pinned by
`tests/unit/test_architecture_no_defensive_rootmodel.py` (no
`hasattr(x, "root")` unwrapping). Bare `JSONType` columns with no model are
legacy; new columns always declare one.

## 3. Pydantic models everywhere inside business logic

**Rule.** `_impl` receives models, works with models, and returns models —
never dicts. A dict has no schema, so every consumer re-derives the shape and
none of them can be checked.

**Illustration.** `_create_media_buy_impl` takes a `CreateMediaBuyRequest` and
returns a result model; it never sees the JSON-RPC params, the HTTP body, or a
`kwargs` dict of loose fields.

**Consequence.** The type checker and the schema guards see every field
access. Wrapper signatures must use SDK types rather than `Any`/`dict`
(`tests/unit/test_architecture_wrapper_typed_params.py`), so the models arrive
typed at the door and stay typed until the boundary serializes them.

## 4. Construction and serialization happen at the boundary — never in `_impl`

**Rule.** The symmetry at the heart of the design:

- **Inbound**: the boundary constructs the Pydantic request model — the compat
  middlewares normalise the wire dialect and the route/tool wrapper parses it
  ([request-lifecycle.md](request-lifecycle.md#the-backwards-compatibility-edge)).
- **Outbound, response**: `_impl` returns a response model and stops. It does
  not build the response — the transport converts the model automatically, and
  wire shaping lives in the single serializer seat (`WireSerializerMixin` in
  `src/core/schemas/_base.py`, pinned by
  `tests/unit/test_architecture_one_wire_serializer_seat.py`).
- **Outbound, database**: `_impl` hands models to repositories; it does not
  build dicts to store. `MediaBuyRepository.create_from_request`
  (`src/core/database/repositories/media_buy.py`) serializes the request at
  the DB boundary for exactly this reason, and `JSONType` serializes model
  values on write.
- **Outbound, external calls**: egress goes through the outbound seam
  (`src/core/security/outbound_http.py`), which owns the wire concerns.

**Illustration.** A `model_dump()` inside `_impl` is the tell: it means
business logic is deciding a wire or storage shape. The guard
`tests/unit/test_architecture_no_model_dump_in_impl.py` bans the call outright
— its allowlist is empty.

**Consequence.** Serialization decisions (aliases, exclusions, spec-pinned
nullable fields) are made once, at seams that every transport shares, instead
of being re-decided per call site. Repositories are the only DB writers
(`tests/unit/test_architecture_repository_pattern.py`).

## 5. Errors: typed raises inside, envelopes at the boundary

**Rule.** `_impl` signals failure by raising a typed `AdCPError` subclass
(`src/core/exceptions.py`) — and nothing else. The buyer-facing envelope is
built by the boundary translator, never authored at the raise site.

**Illustration.** A validation failure raises `AdCPValidationError`; the
boundary runs `build_two_layer_error_envelope()` (`src/core/exceptions.py`)
and emits the transport's shape — REST envelope + HTTP status, MCP `isError`
tool error, A2A failed Task — all through `record_boundary_error`.

**Consequence.** The error class *is* the wire code's identity, so a new error
condition is a new subclass, not a string. Guards hold the line on both sides
of the seam: no `ToolError` in `_impl`
(`tests/unit/test_no_toolerror_in_impl.py`), no `Error(code=...)` construction
in business logic
(`tests/unit/test_architecture_no_error_construction_in_impl.py`), no
`error_code=` kwarg bypassing the hierarchy
(`tests/unit/test_architecture_no_error_code_kwarg_in_impl.py`), and every
boundary must call the two-layer envelope builder
(`tests/unit/test_architecture_error_envelope_two_layer.py`).

## 6. The consequence for tests — derived, not decreed

Because of principle 1, logic exists in exactly one transport-agnostic place.
So BDD grades **logic**, and Given/When/Then are transport-independent by
construction: the same scenario text runs against every transport. It follows
that response and error assertions must go through **transport-independent
helpers** — `assert_envelope_shape()` (`tests/helpers/envelope_assertions.py`)
against `result.wire_error_envelope` for error paths, `wire_response` / the
typed payload for success paths (policy: [tests/CLAUDE.md](../../tests/CLAUDE.md)
§ "Error Verification Policy").

A test that reaches for a transport's own shape — parsing an HTTP body by
hand, unpacking a Task artifact inline — has stepped outside what the scenario
is grading: it now tests one transport's framing, which the scenario never
claimed to specify. Guards enforce the discipline
(`tests/unit/test_architecture_bdd_wire_discipline.py`,
`tests/unit/test_architecture_bdd_no_direct_call_impl.py`).

BDD assertions that reconstruct the error class (`isinstance`, `.error_code`)
are legacy — an architectural mistake being removed; new assertions use the
transport-independent wire helpers.

## Direction of travel: one request DTO, one code table (PR #1721)

PR #1721 is **in flight, not merged**. It refines the details below; the six
principles above are already the rule. Do not write new code against the
shapes it removes:

- **`CODE_TABLE` becomes the sole authority** for a buyer-facing `message`,
  `suggestion`, and `recovery`. `AdCPError` has no `message` parameter, so no
  raise site can author buyer-facing text; provenance-bearing text goes to
  `internal_detail`, which is server-log only.
- **An error's `details` is a declared class**, not a free-form dict —
  `AdCPError` is generic in its detail shape.
- **Error verification converges on exactly one shape.** The `IMPL`
  pseudo-transport, `synthesized_error_envelope`, and the `ImplDispatcher` go
  away: all three computed an envelope from the same in-memory exception the
  assertion then read, so a regression in the production boundary translator
  could not change the result. Error-path tests run on a wire transport.
- Request parsing converges on **a single request DTO**, with errors raised
  and conversions performed at the boundary.

If you are choosing between "raise with a hand-written message" and "pick the
right typed error and let the table speak", choose the latter — it is correct
today and remains correct after #1721 lands.

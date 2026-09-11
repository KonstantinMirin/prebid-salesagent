# Context echo from the boundary

Frozen scope authority for salesagent-3cs7o.1. The epic salesagent-3cs7o holds the
same design; this file is the copy `plan-lane-execute` hashes, so a later edit is
visible in history. Lanes .2 and .3 are structural steps and take the epic as their
plan instead.

## The rule

`src/core/tools/_boundary.py` is the only place in `src/` that reads or writes the buyer's
`context` object. It reads the value once from the raw request and writes it once onto
whatever leaves. Business logic may READ `req.context`, because the field is declared on the
request envelope. Nothing may pass it, forward it, or assign it.

## Spec grounding (AdCP 3.1.1, the pinned version)

- `schemas/core/protocol-envelope.json` declares `context` on every response envelope. Still
  declared at 3.1.21 and 3.2.0-rc.1, so no version bump changes this.
- `ContextObject` declares zero properties with `extra="allow"`: a free-form bag.
  `deep_strip_to_schema` passes it through whole (`src/core/schemas/_accepted_shape.py:171`
  names `context` and `ext` as the shapes AdCP uses for arbitrary data). Echo what arrived;
  never normalize or re-validate it.
- `compliance/universal/error-compliance.yaml:24`: "Context echo is required on error
  responses - the correlation ID is even more important for error diagnosis than for success
  cases. Every error response must include the caller's context object unchanged."
- Graded by 395 `field_present path:"context"` checks and 496
  `field_value path:"context.correlation_id"` checks across 119 storyboard files.
- Webhook delivery is out of scope. `schemas/core/mcp-webhook-payload.json` declares
  `context_id`, not `context`. Asynchronous work needs no second stamp: the synchronous
  `submitted` response is a protocol envelope and carries the echo, the webhook carries
  `context_id`, and a `tasks/get` poll is a new request with its own context.

## 1. One entry, which owns validation

`invoke_tool` accepts the raw payload and validates it, so the read precedes validation and a
schema rejection carries the echo like every other outcome. Validate first, then resolve
identity: a malformed payload answers `INVALID_REQUEST`.

- `src/core/main.py:443` - remove `spec.dto.model_validate(arguments)`; hand over `arguments`.
- `src/a2a_server/adcp_a2a_server.py:845` - remove the `model_validate` and its
  `except ValueError`; hand over `parameters`.
- `src/routes/api_v1.py` - the route declares `body: body_model`, which is what makes FastAPI
  validate ahead of the handler. Read the raw body off the `Request` and carry
  `DTO.model_json_schema()` in the route's `openapi_extra`. That schema is DOCUMENTATION
  only: it is what `/openapi.json` publishes for a client to read, and nothing in the request
  path consults it. Validation stays `DTO.model_validate(raw)` in the boundary. The published
  schema advertises the DTO's full property set, inlined rather than as a `$ref` into
  `components/schemas`, and it is derived from the same model that validates, so the two
  cannot diverge. The path-field merge becomes `{**body, **path_values}`.
- `src/app.py:278`'s `RequestValidationError` handler no longer serves tool routes. Confirm
  no non-tool route needs it before removing it.

## 2. One write, for every outcome

`_echo(value, artifact)` in `src/core/tools/_boundary.py` is the sole writer and assigns
through `object.__setattr__`. A response carries the attribute through `ProtocolEnvelope` and
a typed error through `AdCPSalesAgentError`, so one function serves both.

- Success: where `_served` (`_boundary.py:308`) stamps `adcp_version`. That function receives
  fresh and replayed answers alike.
- Error: in the `except` block at `_boundary.py:246`, after `typed = adcp_error_for(exc)`.
  This also covers the version rejection, because `negotiate_adcp_version` raises inside that
  same try and `unsupported_major_version` is a graded context-echo step.

Echo on every outcome, including the transport errors the spec excuses.

`_deserializer_for` (`_boundary.py:123`) strips `context` from the stored body before
`model.revive(...)` runs. A cached body holds the context of the request that filled the
cache, and `_echo` stamps the context of the caller being served.

## 3. Deletions

| Trace | Count |
|-------|-------|
| Call sites passing `context=req.context` | 103 |
| Call sites forwarding `context=context` | 26 |
| Signatures declaring `context: ContextObject` | 16 |
| Modules importing `ContextObject` | 15 |
| Direct dict writes of the key | 3 |

- The `context` parameter of `AdCPSalesAgentError.__init__` (`src/core/exceptions.py:337`)
  and its `self.context = context` (`:369`). Removing the parameter is what forces the rest
  out: the class accepts no undeclared argument, so the 129 passing and forwarding sites stop
  working and `_echo` becomes the only writer.
- The 16 `context: ContextObject` signatures, including both repository methods
  (`src/core/database/repositories/media_buy.py:81` and `:209`).
- `_serialize_context` (`src/core/exceptions.py:105`), once the boundary's opaque
  pass-through leaves it with no caller.
- The per-`_impl` `context=req.context` in every response constructor, among them
  `src/core/tools/products.py:812` and `src/core/tools/media_buy_list.py:409`.
- `ContextObject` imports from all 15 modules except `src/core/schemas/`, which declares the
  field, and `src/core/tools/_boundary.py`.
- The two non-envelope dict writes, at `src/core/tools/creatives/_assets.py:183` and
  `src/core/tools/creatives/_workflow.py:96`.

`context_id` is a different field and stays. It is declared beside `context` on
`protocol-envelope.json` at 3.1.1, 3.1.21 and 3.2.0-rc.1, and it is what webhook payloads
carry.

## 4. Bans

- **ruff, `ruff-boundary.toml`, TID251**: ban importing `ContextObject`, with
  `per-file-ignores` for `src/core/schemas/*` and `src/core/tools/_boundary.py`. Same shape
  as that file's existing `_impl` bans.
- **ast-grep, `.ast-grep/rules/`**: ban a `context` keyword argument in any call outside
  `src/core/tools/_boundary.py`. Ruff cannot express a keyword-argument ban; the rule
  directory already runs under `make quality-ci`.
- **The response base class, two refusals.** A `model_validator(mode="after")` raises when
  `context` arrives non-None, which blocks the constructor form. A `__setattr__` override
  raises for `context`, which blocks assignment afterwards. Both are required: pydantic's
  `__init__` populates a model without routing through `__setattr__`, so the override alone
  does not see a constructor argument. `_echo`'s `object.__setattr__` bypasses both.
- `AdCPSalesAgentError` needs no runtime guard. Removing the constructor parameter is the ban.

## Verification

1. Break each ban deliberately and watch it fail. A passing guard is not a grading guard.
2. BDD across a2a, mcp, rest and e2e_rest, asserting the echo on the wire for a success, a
   validation rejection and a business error. `TransportResult.wire_response` and
   `wire_error_envelope` are the oracles.
3. Storyboard `error_compliance` and `error-compliance-signals` pass their
   `field_present path:"context"` checks on both protocols.
4. `./run_all_tests.sh`, plus `tox -e integration` because this moves imports and signatures.

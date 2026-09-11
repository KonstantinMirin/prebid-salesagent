# Context echo from the boundary

Frozen scope authority for salesagent-3cs7o.1. The epic salesagent-3cs7o holds the
same design; this file is the copy `plan-lane-execute` hashes, so a later edit is
visible in history. Lanes .2 and .3 are structural steps and take the epic as their
plan instead; .4 is the conformance-grading gap this work uncovered.

## Core Invariant

Every outcome of a tool call is an `AdcpResponse` instance. `context` is one field on one
class, assigned in one place; nothing else reads, passes, or writes it.

## Why the rebuild, grounded in the pin (AdCP 3.1.1)

`core/protocol-envelope.json` declares `adcp_error`, `context` AND `status` on every response
envelope, with `status` in its `required` list. So the spec's model of an error is a response
envelope carrying an error, not a separate document.

Our implementation instead raises out of `invoke_tool` and has each transport call
`build_two_layer_error_envelope(exc)`, which hand-assembles a detached
`{"adcp_error": ..., "errors": [...]}` dict. Three consequences, all measured:

- That dict omits `status`, so every error body this seller emits is invalid against every
  pinned RESPONSE schema. The error OBJECTS are graded and do comply --
  `TransportResult.assert_wire_error_is_schema_conformant` validates every `errors[]` entry
  against pinned `core/error.json`, and BDD validates against exactly three pinned schemas
  (`core/error.json`, `core/mcp-webhook-payload.json`,
  `media-buy/media-buy-delivery-webhook-result.json`). What is ungraded is the ENVELOPE half:
  no check validates an error body against the tool's `*-response.json`, where `status` is
  required. The storyboard's error steps grade `check: error_code`, never
  `check: response_schema` (all ten steps of `universal/error-compliance.yaml`), and the
  envelope-level BDD steps run `Model.model_validate(wire_dict(ctx))` on success bodies.
  Setting `status` is therefore a free conformance gain: nothing depends on its absence, and
  the error-object compliance that IS graded is preserved because the same
  `adcp_error(...)` SDK call still produces those entries.
- Because no response object exists on the error path, `context` has to ride the exception --
  which is why `AdCPSalesAgentError.__init__` takes a `context`, why 103 call sites thread
  `context=req.context` to reach a raise, and why an echo helper needs two artifact types.
- 4 of our 14 tools' response schemas accept a pure error response once `status` is present
  (`get_products`, `create_media_buy`, `update_media_buy`, `sync_creatives`); the other 10
  require their success fields. Emitting a response instance therefore omits the same fields
  the current dict already omits, while ADDING the required `status`. The rebuild is a strict
  conformance improvement, not a regression.

## The shape

One error response type, declared once:

```python
class AdcpErrorResponse(AdcpResponse):
    """What a failed tool call IS: the response envelope, carrying the error."""
    errors: list[Error] = Field(default_factory=list)
```

`adcp_error`, `context` and `status` come from the envelope base; `errors` is declared here
because the pin puts it on each tool's own schema rather than on the envelope, and one
subclass is the one place it can live without a per-tool copy.

One exception at the edge, whose payload is that response:

```python
class AdcpFailure(Exception):
    def __init__(self, response: AdcpErrorResponse) -> None: ...
```

- Business logic keeps raising `AdCPSalesAgentError` subclasses and never sees either class.
- The boundary converts ONCE: `AdcpErrorResponse.of(exc, context=...)` builds the response --
  `status=failed`, the error mirrored to `adcp_error` and `errors[0]`, `context`, and
  `adcp_version` stamped by `of` itself so no path can miss it -- and raises
  `AdcpFailure(response)`. Raising, not returning: a return value can be ignored and a raise
  cannot, and business logic across fourteen tools calls services that call services. What
  changes is WHAT is raised, not whether.
- `serve(tool_name, raw, credential, protocol)` is the transport entry. It parses the payload
  and runs the tool, and both failures leave as `AdcpFailure`, so a transport wraps one call in
  one `try` and cannot leave a schema rejection uncaught. `invoke_tool` keeps its typed
  signature for callers that already hold a validated request.
- Each transport catches `AdcpFailure`, serializes `failure.response` with the same `to_wire`
  the success path uses, and adds only its own wire failure marker: an HTTP status for REST
  (`wire_status`, read from `CODE_TABLE`), an `AdCPToolError` for MCP, a Task state for A2A.
  That marker is the only part of a refusal that is genuinely per-transport.
- A2A's Task state is the response's own `status`, translated through one total enum-to-enum
  mapping (`_TASK_STATE_BY_ADCP_STATUS`, nine rows, exact counterparts). Derived once. The
  per-creative `pending_review -> submitted` rule is deleted: pinned
  `creative/sync-creatives-response.json` puts that state inside the synchronous branch as
  per-item information, and its submitted branch cannot carry creatives at all.
- `TransportProtocol` is a `StrEnum` in `src/core/resolved_identity.py`, the same three string
  values the `Literal` had; the harness `Transport` derives its protocol members from it.

## Deletes

| Thing | Why it existed |
|---|---|
| `build_two_layer_error_envelope` | assembled the envelope by hand |
| `_echo` and its two artifact types | one outcome had no response object |
| `AdCPSalesAgentError.context` + its constructor parameter | to carry the echo to a detached dict |
| the 103 `context=req.context` call sites and 16 forwarding signatures | to reach a raise site |
| `_serialize_context` | serialized a context off an exception |
| per-transport `build_two_layer_error_envelope(exc)` calls in `app.py`, `tool_error_logging.py`, `adcp_a2a_server.py` | each transport assembled its own error body |

## Kept from the superseded lane

`validated_request(tool_name, raw)` stays: a schema rejection has no `req`, so the buyer's
context can only come from the raw payload. It now returns an `AdcpErrorResponse` rather than
raising an echoed exception. The transport moves stay too -- MCP and A2A already had no native
validation, and REST's raw body is what lets a rejection be answered at all.

## Graded by

`tests/bdd/test_local_context_echo.py` unchanged -- 6 scenarios x (a2a, mcp, rest, e2e_rest),
already green at 18/18 on the superseded lane and agnostic to how the echo arrives. Plus a new
obligation this rebuild creates: every error body validates `status`.

## Filed separately, not fixed here

10 of 14 pinned response schemas require their success fields, so a pin-valid error response is
impossible for them; `create-media-buy-response.json` and `update-media-buy-response.json` solve
it with a `oneOf` error branch (`required: ['errors']`) and the others should too. Upstream.

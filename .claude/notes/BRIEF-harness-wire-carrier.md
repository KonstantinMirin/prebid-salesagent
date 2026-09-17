# BRIEF: the signed HTTP legs must CARRY the wire response, not raise past it

**Status:** root-caused, not started. 13 failing scenarios, one cause.
**Production is already correct — no `src/` change should be needed.** If you find yourself
editing `src/`, stop and re-read "Why production is exonerated" below.

## The defect in one sentence

`_run_mcp_over_http` (and its A2A/REST siblings) turn a wire refusal into a RAISED,
reconstructed exception and discard the `httpx` response — so the
`WWW-Authenticate: Signature error="<code>"` header the seller really sent never reaches the
assertion that exists to grade it.

## Exact sites

| file:line | what it does |
|---|---|
| `tests/harness/_base.py:2216` | `raise _mcp_wire_error(_mcp_error_to_exception(envelope["error"]))` — the JSON-RPC `error` frame branch |
| `tests/harness/_base.py:2219` | `raise _mcp_wire_error(_mcp_error_to_exception(result))` — the `isError` result branch |
| `tests/harness/_base.py` `_run_a2a_over_http` | same shape on the A2A leg (`_a2a_jsonrpc_result` → raise) |
| `tests/harness/_base.py` the signed REST leg (`~:2428`, `wire_request(...)` then `client.post`) | returns the response; confirm it survives all the way onto the `TransportResult` |

The consumer side, for reference (do not weaken these):

* `tests/harness/transport.py:313` — `TransportResult.raw_response` exists and is the carrier.
* `tests/harness/transport.py:685` — `assert_signature_challenge` reads `self.raw_response` and
  REFUSES TO GRADE when it is `None`. That refusal is correct behaviour and must stay; the
  fix is to give it something to read, never to relax it.

## The prescribed shape, and it is written down

`tests/CLAUDE.md:659`:

> Assert on the wire envelope, not reconstructed exceptions… that reconstruction was lossy.

So this is a conformance job, not a judgement call. Return a `TransportResult` carrying
`raw_response` (and the parsed `wire_error_envelope`) instead of raising. The raised,
reconstructed `AdCPSalesAgentError` is exactly the "lossy reconstruction" that line names —
it survives the transit and the HTTP response does not.

## The 13 failing node ids

```
tests/bdd/test_request_signing_enforcement.py::test_an_unsigned_request_to_a_required_for_operation_is_refused[a2a]
tests/bdd/test_request_signing_enforcement.py::test_a_request_signed_by_a_counterparty_the_seller_can_resolve_is_accepted[a2a]
tests/bdd/test_request_signing_enforcement.py::test_a_registration_carrying_webhook_authentication_is_refused_unless_signed[a2a]
tests/bdd/test_request_signing_enforcement.py::test_a_registration_carrying_webhook_authentication_is_refused_unless_signed[mcp]
tests/bdd/test_request_signing_enforcement.py::test_a_registration_carrying_webhook_authentication_is_refused_unless_signed[rest]
tests/bdd/test_request_signing_enforcement.py::test_a_presentbutmalformed_signature_is_refused_in_every_bucket_the_seller_declares[a2a-required]
tests/bdd/test_request_signing_enforcement.py::test_a_presentbutmalformed_signature_is_refused_in_every_bucket_the_seller_declares[a2a-warn]
tests/bdd/test_request_signing_enforcement.py::test_a_presentbutmalformed_signature_is_refused_in_every_bucket_the_seller_declares[a2a-supported]
tests/bdd/test_request_signing_enforcement.py::test_a_signedbutinvalid_request_completes_under_warn[a2a]
tests/bdd/test_request_signing_enforcement.py::test_the_same_signedbutinvalid_request_is_refused_under_supported[a2a]
tests/bdd/test_request_signing_enforcement.py::test_a_signedbutinvalid_registration_carrying_credentials_is_refused_under_warn[a2a]
tests/bdd/test_request_signing_enforcement.py::test_a_signedbutinvalid_registration_carrying_credentials_is_refused_under_warn[mcp]
tests/bdd/test_request_signing_enforcement.py::test_a_signedbutinvalid_registration_carrying_credentials_is_refused_under_warn[rest]
```

All 13 fail with the identical diagnosis, which is the tell that it is ONE cause:

```
Expected the '<code>' signature challenge, and this result IS an error
(error=AdCPSalesAgentError()) — but it carries no raw HTTP response to read
WWW-Authenticate from (raw_response=None).
```

Run them with: `scripts/run-test.sh tests/bdd/test_request_signing_enforcement.py -q -p no:randomly`
Baseline as of this brief: **13 failed, 14 passed.**

## Why production is exonerated — do not "fix" `src/`

Driven directly, with the scenario's OWN factory payload
(`CreativeAssetRequestFactory.payload(...)` plus `_format_payload`'s `format_id`/`assets`),
against a tenant declaring `required_for: ["sync_creatives"]`, with `credential={}`:

```
STATUS:   401
WWW-AUTH: Signature error="request_signature_required"
CODE:     request_signature_required
MESSAGE:  The request signature was missing or malformed
```

That is the design doc's CRITICAL requirement already met: the specific code survives
byte-for-byte into the envelope and reaches `_challenge_for_code`. The resolver raises it,
the boundary writes it, `AuthChallengeResponder` lifts it into the header. Everything
`src/` owns works.

**Do not confuse this with the PARKED malformed-body ordering question.** An earlier probe
here used a hand-built creative that was genuinely invalid (`creative_id` and `assets`
missing) and got `INVALID_REQUEST` at HTTP 400 — that is the parked ordering artefact
(`serve()` evaluates `validated_request(...)` as an argument to `invoke_tool`, so body
validation precedes `_resolve_identity`), and the owner has ruled it parked as a
conformance-runner concern. It is NOT this bug. These 13 scenarios all send a VALID
factory-built `sync_creatives` request.

## Blast radius — read this before you start

This changes **how every signed HTTP leg returns**, not just these 13. Any
transport-parametrized ERROR-PATH scenario that currently relies on the leg RAISING will see
a returned `TransportResult` instead. Expect to touch, or at least to re-run:

* every `tests/bdd/` scenario parametrized over `[mcp]`/`[a2a]`/`[rest]` that asserts an error;
* `tests/harness/dispatchers.py`, which reads what these legs return;
* `tests/integration/test_harness_signed_dispatch.py` (3 failures in the same family — check
  whether they clear for free once the carrier survives);
* `tests/integration/test_harness_wire_response.py`, which pins where wire responses come from.

Budget for the whole behaviour suite, not a targeted run. `./run_all_tests.sh` or a cassini
run is the gate, not `-k request_signing`.

## Two things already fixed — do not redo them

1. `credentialed=bool(credential)` → `_presents_a_credential(credential)` (commit `406e6a8df`).
   `env.credential(token=None)` returns `{"x-adcp-tenant": "..."}`, a non-empty mapping
   presenting no credential; truthiness read it as credentialed and the legs attached the
   capability's bearer to a call the scenario asked to make anonymous. Took the module from
   15 failed / 12 passed to 13 / 14.
2. `tests/harness/_base.py:451`'s function-local `from src.core.exceptions import AdCPError`
   (renamed to `AdCPSalesAgentError`). It raised ImportError only when an `/a2a` call FAILED,
   and the harness reported that as "no envelope to grade" — the same masking shape as the
   defect above, which is worth knowing while you work here.

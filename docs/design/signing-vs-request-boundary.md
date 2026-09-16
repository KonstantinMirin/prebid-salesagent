# Reconciling the RFC 9421 verifier with PR #1721's request boundary

Written BEFORE the merge, because this one decision drives how ~30 of the 55 conflicting
`src/` files resolve. Everything below is grounded in the two branches' code as it stands,
not in intent.

## The collision, stated plainly

PR #1721 rebuilds the request path around a single boundary and states a principle in
`docs/development/request-lifecycle.md`:

> `src/app.py` registers three HTTP middlewares, and **none of them reads a credential or
> resolves an identity.** … **No middleware decides auth.** Each transport hands the request
> headers to the boundary, where the tool name is known, and the resolver behind it is the
> one reader of a credential.

Our branch adds a fourth ASGI middleware, `RequestSignatureMiddleware`, which reads a
credential (the `Signature`/`Signature-Input` headers) and decides auth (it can end the
exchange with 401 before the app runs).

Taken at face value these cannot both stand. They can, and the reason is a distinction the
principle does not draw.

## Decision 1 — signature verification MOVES INTO `_resolve_identity` (owner's call)

The earlier draft of this document argued the verifier should stay an ASGI middleware. That
was wrong, and the owner's correction is better: **`_resolve_identity` expands to resolve the
signature as well as the credential.** One function answers "who is this caller", by every
means the request offers.

Why it is better than what I proposed:

* It satisfies #1721's principle literally rather than by carving an exception into it. The
  resolver becomes the one reader of a credential, signature included; no middleware decides
  auth.
* The duplicated tenant lookup disappears. `_resolve_identity` already calls `_detect_tenant`,
  so the verifier stops doing its own — deleting the failure mode that cost a full session to
  diagnose (`salesagent-x5t4y`).
* **It collapses the two-renderer problem** that the rest of this document was contorting to
  justify. A signature failure becomes an identity failure, raised inside the resolver, caught
  by `invoke_tool`'s `except`, and turned into a response by `failure_response`. It is then an
  AdCP envelope like any other, and `AuthChallengeResponder` — the ONE renderer — lifts it to
  401 and writes the challenge. The open question at the bottom of the earlier draft is simply
  answered: there is one renderer, as their design intends.
* The constraint that forced the old shape dissolves. The verifier's docstring says rejections
  are "SENT rather than raised … a raise here becomes a 500 in ServerErrorMiddleware". That is
  true at the ASGI layer and false inside the resolver, where the boundary's cascade exists.

### The one real obstacle: the resolver cannot see the body

```python
def _resolve_identity(headers: Mapping[str, str], *, require_valid_token, account_ref,
                      credential_required_for) -> ResolvedIdentity | PublicIdentity
```

Headers only. RFC 9421's `content-digest` covers the EXACT bytes received, and the boundary's
`raw` is already decoded (`model_validate(raw)`, `raw["context"]`) — re-serializing it is not
byte-identical, so a digest computed from it would verify a different message than the buyer
signed.

So the bytes have to reach the resolver. Headers already do, from every transport; the bytes
travel the same road:

1. `_resolve_identity` gains `signed_body: bytes | None` beside `headers`, and verifies iff the
   signature headers are present.
2. The boundary passes it through, exactly as it passes `headers` — sourced from the transport,
   not re-derived.
3. Each transport supplies it from where the bytes still exist: REST from `await request.body()`;
   A2A from the ASGI `scope` (their doc notes A2A routes are appended directly to the route
   table "so the app's middleware and `scope['state']` are visible to A2A handlers"); MCP needs
   checking — if FastMCP does not expose the raw body, a minimal body-capturing middleware
   stashes it on `scope["state"]` and the transport reads it there.

That residual middleware, if MCP needs one, CAPTURES bytes and decides nothing — which keeps
the principle intact.

### CORRECTION from implementation — `signed_body` alone was wrong

The plumbing above says `signed_body: bytes | None`, sourced per transport. Implementation
found that insufficient, and the correction is better. Recorded here so the doc does not stay
wrong:

* **Bytes alone do not cover the signature base.** `@target-uri` covers the URL AS SENT with
  percent-encoding intact, and `scope["path"]` is percent-DECODED by every real server
  (uvicorn sets `path = unquote(raw_path)`), so only `raw_path` — bytes on the scope — can
  rebuild it. `@method` is simply absent from what a transport hands the boundary. A digest is
  not the only covered component the boundary cannot reconstruct.
* **Per-transport sourcing would fork the one derivation that must not fork.** Three transports
  sourcing it separately means three copies of the `@target-uri` derivation — and unlike most
  duplication, divergence there fails EVERY signed request rather than an edge case.

So: ONE capture, one derivation, three readers. The middleware records an `HttpExchange`
(`method`, `url`, body) on `scope["state"]`; the resolver reads it. It still decides nothing —
verified by there being no `raise`, no `401`, no `status_code` and no early `send` in it.

Two further implementation findings worth keeping:

* The capture is scoped by an **allowlist of AdCP surfaces, not a denylist**. That permanently
  exempts the trust-root documents: buffering in front of `/.well-known/jwks.json` costs
  nothing, but a VERIFIER in front of it would be a bootstrap deadlock — and an allowlist
  cannot forget to exclude it.
* The buffer must be **lossless on every exit**. The downstream app builds its `Request` from
  the same scope and reads the SAME receive channel, so a buffer that consumed and discarded
  would hand the handler a destroyed body. Over-cap refuses only the HASHING, and the
  disconnect still reaches the app.

### The consequence to design deliberately

The refusal stops being bodyless and becomes an AdCP envelope, so `_challenge_for_code` must
emit `WWW-Authenticate: Signature error="<code>"` — and the SPECIFIC signature error code must
survive into the envelope, because the pinned compliance vectors grade that string
byte-for-byte. A generic AUTH_INVALID that loses `request_signature_required` would pass our
tests and fail conformance. This is the sharp edge of the new shape and needs a test that
asserts the exact challenge string end-to-end.

## Decision 2 — what this retires

Two hazards in the earlier draft disappear with the middleware:

* The accidental-safety analysis (our 401 survived `_flush` only because it was bodyless, and
  any future JSON body would silently strip the challenge) is moot — there is no second
  renderer to strip.
* `_detect_tenant_for_posture` goes away as a separate lookup. Posture is read once the
  resolver holds the tenant.

`posture_for_tenant(None).supported` falling back to `SigningConfig.verifier_enabled` still
stands and stays documented (`salesagent-t1z7l` records why flipping it would be wrong) — but
the `None` case should become unreachable, since the resolver always has a tenant by then.

## Why the straddle is the SPEC's, not ours

A reviewer will challenge `signed_body` first, as a layering violation. It is not, and the
argument is the spec's own. `security.mdx` @ 3.1.1, the `protocol_methods_*` section:

> The matched value is the JSON-RPC envelope's `method` field … **not** the MCP `tools/call`
> `params.name`. … Verifiers MUST NOT cross-namespace match … The two buckets are matched
> against **disjoint envelope fields**.

> The signature-base construction is identical for both namespaces: the same RFC 9421 covered
> components apply (`@target-uri`, `@method`, `content-digest` …), with **`@target-uri` and
> `@method` reflecting the actual HTTP request — not the JSON-RPC method string**.

Read together they fix the verifier's shape:

* **What is signed** is the HTTP message — `@method`, `@target-uri`, and `content-digest` over
  the raw body. RFC 9421 is an HTTP *message* signature standard; there is no other layer it
  could sign at.
* **Which policy applies** is decided by reading INSIDE that body — the JSON-RPC `method`, and
  for `tools/call`, one level deeper.

So a conforming verifier cannot be purely HTTP-layer (it must parse the envelope to choose a
bucket) and cannot be purely protocol-layer (it must digest bytes the protocol layer has
already destroyed). The spec REQUIRES something that spans both. AdCP layers one protocol over
three transports while adopting a signature standard defined one layer beneath all of them;
that is the source of the tension, not a mistake in #1721's layering or in ours.

**And #1721 already made this seam deliberately.** `_resolve_identity(headers, ...)` takes
`headers` — an HTTP-layer artifact — because identity needs it. Raw bytes are the same category
of thing, needed by the same function, for the same reason. `signed_body` completes an existing
seam rather than opening a new one, and `_resolve_identity` is the only place in the
architecture holding both halves: headers from HTTP, and a position downstream of transport
unwrapping.

Contrast idempotency, where the same instinct was right to resist: the idempotency key is a
DECLARED DTO FIELD, already inside the validated request, so it never needed bytes. A signature
is computed OVER the bytes. The two are not the same problem.

## The namespace split has ONE home: the registry is the authority

`security.mdx` :1198 requires more than correct matching — it requires REFUSAL at config time:

> AdCP tool names (no `/`) MUST NOT appear in any `protocol_methods_*` array, and JSON-RPC
> method names (containing `/`) MUST NOT appear in `supported_for` / `warn_for` /
> `required_for`. Verifiers MUST reject capability blocks that violate the namespace split
> with a **configuration-time error** rather than silently coercing strings between the two.

Two obligations, and they belong in different places — but the RULE is stated once:

1. **The predicate belongs to the registry.** `src/core/tools/registry.py` is the authority on
   what an AdCP tool name is; nothing else should decide it by looking for a `/`. It exposes
   the question ("is this a registered AdCP operation?") and owns the answer.
2. **The enforcement hangs off the existing declaration validator.** #1721 already validates
   `tenants.capability_declarations` at config load — its own description calls it "a
   config-time-validated STRICT declaration store — a declaration whose `required_tools` aren't
   implemented is rejected at config load, not discovered on the wire". The namespace split is
   the same KIND of check at the same moment, so it goes there and calls the registry predicate
   rather than re-deriving membership.

That keeps one rule in one place while letting both sides read it, and it means a mixed-up
declaration fails at config load rather than at verification time on a buyer's request.

**The matching-side trap to pin with a test.** `Verifiers MUST NOT cross-namespace match`: a
`protocol_methods_required_for` membership must NOT be satisfied by a `tools/call` body even
when `params.name` equals the listed string. This is why the verifier must match on the
ENVELOPE's `method`, not on the resolved tool name — the resolved-tool-name shortcut looks
correct, is simpler, and is a conformance failure.

## Decision 3 — every one of our raise sites loses its message

#1721 removes `message` from `AdCPError.__init__`; `CODE_TABLE` (100 entries) becomes the sole
authority for `message`/`suggestion`/`recovery`, and the class becomes generic in its details
shape (`class AdCPError[DetailsT: ErrorDetails]`). Provenance text moves to `internal_detail`,
which is server-log only.

Our branch authors buyer-facing text at many raise sites. Each needs re-expressing as
`code + typed details`, with the prose moved to `internal_detail`. Known families:

| Site | Current | Becomes |
|---|---|---|
| egress refusals (`AdCPBlockedUrlError`) | authored sentence | code + `{url}`-shaped details |
| `raise_injected_adapter_failure` | `f"test_behavior recovery={requested!r} ..."` | code + `internal_detail` |
| signing/trust-root config errors | authored sentences | `AdCPConfigurationError` + details |

This is mechanical per site but large, and it is where a careless merge silently re-introduces
authored text. The guard that enforces it ships in #1721, so the merge is self-checking here:
if we get it wrong, their guard fails rather than our tests passing quietly.

## Decision 4 — what we GAIN, and must not re-add

#1721 deletes `Transport.IMPL`, `synthesized_error_envelope` and `ImplDispatcher`, with the
reason that all three "computed an envelope from the same in-memory exception the assertion
then read, so a regression in the production boundary translator could not have changed the
result."

Our branch still has all three, and two outstanding guard failures are exactly about them
(`_outcome_helpers.py:105/137/139` keying on `Transport.IMPL`). **Take theirs wholesale.** Any
conflict in `tests/harness/transport.py`, `dispatchers.py` or `_outcome_helpers.py` where we
kept an IMPL branch resolves to deletion, not union. This retires our two failures rather than
merging them forward.

## Staging plan

The 174-file surface splits along these decisions. Merge in this order, one commit per stage,
with the coherence gate between stages:

| Stage | Content | Conflicts | Why first |
|---|---|---|---|
| 1 | baselines + config (6 dotfiles, `mypy.ini`, `tox.ini`, `run_all_tests.sh`, `docker-compose.e2e.yml`) | ~11 | Mechanical, by rule. Regenerate ratchets AFTER the code stages, never content-merge. |
| 2 | `src/core/exceptions.py` + the raise sites (Decision 3) | ~20 | Everything else depends on the error type's shape. |
| 3 | the boundary + transports + auth (`_boundary.py`, `main.py`, `app.py`, `auth_*.py`, `schemas/_base.py`, `agent_identity.py`) — Decisions 1–2 | ~20 | The architectural core; the design above is its spec. |
| 4 | BDD harness — take theirs for IMPL deletion (Decision 4) | ~30 | Depends on 3's transport shape. |
| 5 | the remaining `tests/` | ~73 | Mostly follows once 2–4 are settled. |
| 6 | docs — union, plus the principle amendment from Decision 1 | ~2 | Last, so it describes what actually landed. |

Phase 7's layer 5 (bare node-id pass-count comparison against both parents) is mandatory at the
end: the IMPL deletion legitimately removes tests, and only a node-id diff can separate "deleted
on purpose" from "silently stopped running".

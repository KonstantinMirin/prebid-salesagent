# RFC 001: The sales agent does not implement idempotency on read operations

**Status:** Request for comment
**Scope:** AdCP 3.1.1 (pinned) and the 3.2 beta line
**Decision:** Implement idempotency for mutating tasks only. Take no action on the read-path requirement.

## Summary

AdCP 3.1.1 requires an `idempotency_key` on every task request, reads included, and requires
the seller to store each response durably and replay it byte-for-byte for a declared window of
up to seven days. The 3.2 beta line withdraws that requirement for reads.

The sales agent implements idempotency for mutating tasks. It takes no action on the read path:
no durable read cache, no replay of a supplied key on a read, and no rejection of a read that
omits the key.

Three findings support the decision. No other protocol surveyed applies an idempotency key to a
read. The stated justification for extending the requirement to reads rests on a premise the
reference SDKs contradict. A conformant client writes to the mandated store on every read and
reads from it on almost none.

This document also proposes that AdCP drop idempotency from every non-mutating route.

## What the specification requires

The idempotency rules live in `building/by-layer/L1/security.mdx` in the
[AdCP repository](https://github.com/adcontextprotocol/adcp).

| Requirement | [3.1.1](https://github.com/adcontextprotocol/adcp/blob/v3.1.1/docs/building/by-layer/L1/security.mdx) | [3.2.0-beta.5](https://github.com/adcontextprotocol/adcp/blob/v3.2.0-beta.5/docs/building/by-layer/L1/security.mdx) |
|---|---|---|
| Key on mutating requests | Required | Required |
| Key on read requests | Required; sellers SHOULD reject omission | Optional |
| Replay when a key is supplied | Required, byte-for-byte | Required, byte-for-byte |
| Response store durability | Normative: survives restarts, pod replacement, and region failover. In-memory stores are non-conformant. | Unchanged |
| Retention window | Declared by the seller: 3600s floor, 86400s recommended, 604800s maximum | Unchanged |
| Row cap on the store | None | None |

3.1.1 states the read requirement and its enforcement schedule:

> `idempotency_key` is **required on every AdCP task request** — read and mutating alike.

> **3.2.0** — sellers MUST reject reads that omit `idempotency_key` with `INVALID_REQUEST`.

3.2.0-beta.5 replaces the first sentence and cancels the second:

> `idempotency_key` is **required on every state-mutating AdCP task request**. Guaranteed
> pure-read tasks may leave it optional, but they MUST accept and apply the replay contract
> when a caller supplies one.

The withdrawal rides inside
[PR #6212](https://github.com/adcontextprotocol/adcp/pull/6212), whose subject covers
resource-scoped indicators. No dedicated design discussion accompanies it.

## What the sales agent does

| Behavior | Decision |
|---|---|
| `idempotency_key` on a mutating task | Honored: at-most-once execution, conflict detection, replay |
| `idempotency_key` supplied on a read | Accepted and ignored. No storage, no replay. |
| Read that omits `idempotency_key` | Processed normally. Never rejected. |
| Durable read-response cache | Not built |

The first row is deliberate and stays. A client-supplied key is the only signal that
distinguishes "retry the media buy I already sent" from "create a second, identical media buy".
Nothing else in the request carries that distinction, because a buyer may legitimately want two
identical buys. Idempotency on mutations is correct, and the sales agent implements it.

## Why the read path gets no action

### No protocol applies idempotency keys to reads

A survey of 20 protocols, vendors, and standards found no case that applies a client-supplied
idempotency key to a safe operation, and no case that mandates durable response replay for one.
Two vendors forbid the practice in their reference documentation.

| Source | Scope of the key | Response storage |
|---|---|---|
| [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests) | `POST` only | Permitted to prune after 24 hours |
| [Adyen idempotency](https://docs.adyen.com/development-resources/api-idempotency/) | `POST` only | Not mandated |
| [IETF Idempotency-Key header draft](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) | Non-idempotent methods | Strategy left to the implementer; expiry is a MAY |
| [OASIS Repeatable Requests 1.0](https://docs.oasis-open.org/odata/repeatable-requests/v1.0/repeatable-requests-v1.0.html) | Unsafe methods | Tracking window only |
| [Google AIP-155: Request identification](https://google.aip.dev/155) | Create and mutate | Returning current state instead is permitted |
| [AWS EC2 idempotency](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/Run_Instance_Idempotency.html) | Create operations | Not mandated |
| [Protocol Buffers `IdempotencyLevel`](https://github.com/protocolbuffers/protobuf/blob/main/src/google/protobuf/descriptor.proto) | `NO_SIDE_EFFECTS` marks a method safe, so retries need no key | None |

Stripe states the position directly:

> All `POST` requests accept idempotency keys. Don't send idempotency keys in `GET` and
> `DELETE` requests because it has no effect. These requests are idempotent by definition.

The search found no argument for the opposite position in standards discussions, vendor
documentation, or the API-design literature.

### HTTP already solves read caching, with the opposite control model

[RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111) governs response reuse for
reads. Its control model inverts AdCP's on every axis.

| Axis | RFC 9111 | AdCP 3.1.1 reads |
|---|---|---|
| Is caching required | Optional for every participant | Required of the seller |
| Cache key | Derived from the URI, so entries are shareable | A per-request client token, so entries are unshareable |
| Freshness | The origin declares it and can revalidate | No freshness model; the entry is immutable for the TTL |
| Client bypass | `no-cache` forces a fresh response | None. A fresh result requires a different key. |

A protocol that wanted cacheable reads had a specified mechanism available and did not use it.

### The mandated store has almost no consumer

3.1.1 requires the buyer to mint a fresh key for each logical read:

> Buyers MUST mint a fresh `idempotency_key` per call. Reusing the prior poll's key would
> replay the cached snapshot (up to `replay_ttl_seconds`), silently returning stale data.

A conformant buyer therefore never reuses a read key except when retrying a request whose
response it never received. The seller writes an entry on every read and serves one only on
that rare retry. The store is written on every request and read on almost none.

The specification also assesses the same mechanism two ways. It calls read replay "harmless"
where it justifies the requirement, and "exactly the failure mode the cache exists to prevent
on mutations" where it states the buyer's obligation. Both sentences describe a replayed read.

### The justification rests on a premise the SDKs contradict

3.1.1 defends the enforcement schedule by asserting that the reference clients already send the
field on every call:

> Buyer SDKs (`@adcp/client`, `adcp-py`) already send `idempotency_key` uniformly today, so
> SDK-using integrators are unaffected by the cut date.

The Python SDK's `resolve_key` documents the opposite:

> 3. Freshly generated UUID v4 when the tool is mutating.
> 4. `None` for non-mutating tools — caller should not include the field.

The [TypeScript SDK](https://github.com/adcontextprotocol/adcp-client) derives its mutating set
from the schemas that require the field, and classifies `get_products` per call — the
read-versus-mutating classification that 3.1.1 calls "not feasible" in the same paragraph.

Neither SDK server module wires read caching. The Python server middleware describes itself as
middleware "for AdCP mutating tool handlers", and its Postgres backend documents that it has
"no row cap; only TTL bounds the table size".

The uniform sender was the conformance runner, not a buyer SDK.
[Issue #4399](https://github.com/adcontextprotocol/adcp/issues/4399) reports that a wrapper
rejected the runner's `idempotency_key` on `get_products`, and asks for tolerance of the field.
[PR #2315](https://github.com/adcontextprotocol/adcp/pull/2315) had scoped the key to mutating
requests. The follow-up commit turned a tolerance request into a requirement on every task.

## Proposal for AdCP

1. Drop `idempotency_key` from every non-mutating route and tool. Reads are idempotent by
   definition, which is the reasoning Stripe, Adyen, and the IETF draft already apply.
2. Keep the replay contract for mutating tasks, where a client-supplied key resolves an
   ambiguity nothing else in the request resolves.
3. Solve long-running operations with the mechanisms built for them. AdCP already specifies
   push notification configuration, and 3.1.1 already directs buyers away from replay for this
   purpose: a replayed response is "a historical snapshot, not a current-state read", and
   buyers "requiring current state MUST consult the resource's read endpoint". Replay never was
   the polling mechanism. Webhook callbacks and a status read endpoint are the precedent, in
   AdCP and outside it.
4. Handle a polymorphic task by classifying the call, not by keying every call. The 3.2 line
   demonstrates this: splitting product discovery restored static classification, and the read
   requirement became unnecessary in the same change.

## Open questions for reviewers

- Does a use case for read-path replay exist that this document misses? The only benefit the
  specification names is byte-stable replay on a retried read.
- The 3.2 withdrawal commit subject reads "move `get_products` idempotency to 4.0". Does that
  signal a return of the requirement, and on what terms?
- Replay of a supplied key on a read is a prose requirement in both version lines, and no
  storyboard grades it. Should conformance grade it, or should the requirement go?

## References

- [AdCP security specification, v3.1.1](https://github.com/adcontextprotocol/adcp/blob/v3.1.1/docs/building/by-layer/L1/security.mdx)
- [AdCP security specification, v3.2.0-beta.5](https://github.com/adcontextprotocol/adcp/blob/v3.2.0-beta.5/docs/building/by-layer/L1/security.mdx)
- [Issue #4399: get_products MCP envelope idempotency_key rejected by wrapper layer](https://github.com/adcontextprotocol/adcp/issues/4399)
- [PR #2315: require idempotency_key on all mutating requests](https://github.com/adcontextprotocol/adcp/pull/2315)
- [PR #6212: add resource-scoped indicators and warnings](https://github.com/adcontextprotocol/adcp/pull/6212)
- [Stripe: Idempotent requests](https://docs.stripe.com/api/idempotent_requests)
- [IETF: The Idempotency-Key HTTP header field](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111)
- [Google AIP-155: Request identification](https://google.aip.dev/155)
- [OASIS: Repeatable Requests Version 1.0](https://docs.oasis-open.org/odata/repeatable-requests/v1.0/repeatable-requests-v1.0.html)
- [Protocol Buffers: `descriptor.proto` IdempotencyLevel](https://github.com/protocolbuffers/protobuf/blob/main/src/google/protobuf/descriptor.proto)
- [AdCP TypeScript SDK](https://github.com/adcontextprotocol/adcp-client)

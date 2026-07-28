# RFC 9421 message signing — spec grounding and configuration surface design

Issue **#1291**. Branch `feat/rfc9421-request-signing`, stacked on `feature/spec-gaps-1210`.
Produced by A1 (`salesagent-z6nr.7`). **Design only — this note changes no production behavior.**

This is the artifact CLAUDE.md's spec-grounding gate requires *before code is written*. Every
child issue of #1291 cites this note instead of re-deriving citations; §13 is the block to paste
into each child PR.

---

## 1. Authority, and how to read every citation here

**Pinned version: AdCP 3.1.1**, via `adcp==6.6.0`. The pin is guarded by
`tests/unit/test_adcp_spec_version.py`.

Spec source is the `adcontextprotocol/adcp` repo at **tag `v3.1.1`**. Every path below is read as:

```bash
git -C ~/projects/adcp show v3.1.1:<path>
```

Read it that way and nothing else. The `~/projects/adcp` working tree is checked out at a
different version, so reading files from disk gives you the wrong text — a mistake that has
already produced wrong conclusions on this codebase.

### Authority hierarchy

1. **The 3.1.1 JSON schemas** — `dist/schemas/3.1.1/bundled/protocol/*.json`. The contract.
2. **The compliance artifacts** — `dist/compliance/3.1.1/{universal,test-kits,test-vectors}/`.
   What is actually graded, and the enumerated bodies (the vector directory, the checklist
   listing) beat any summary sentence that counts them.
3. **The prose** — `dist/docs/3.1.0/building/by-layer/L1/security.mdx`, read at tag `v3.1.1`.
4. **The `adcp` SDK** (`.venv/lib/python3.12/site-packages/adcp/signing/`) — a **cross-check, not
   the authority**. Where the SDK and the schema/prose disagree, the schema wins, we implement the
   schema, and the divergence is filed upstream.

### Path corrections this note makes to the epic's own citations

- **There is no `dist/docs/3.1.1/`.** `dist/docs/` at tag `v3.1.1` tops out at `3.1.0/`.
  `dist/docs/<version>/building/implementation/*.mdx` — cited by the epic body — does not resolve
  either at any version present (checked: `dist/docs/3.1.0/building/implementation/security.mdx`).
  The prose path that resolves is
  `dist/docs/3.1.0/building/by-layer/L1/security.mdx`. The schemas' own
  `x-adcp-validation.spec` pointers (`docs/building/implementation/security.mdx`) are stale
  in-schema pointers; do not copy them.
- **The vector count is 40, not 28** — see §6.
- **The verifier checklist is 15 checks, not 14** — see §8.

### The seven SDK divergences already found

Concrete instances, not a boilerplate disclaimer. All get filed upstream; all get implemented per
the schema on our side. (#4 and #5 were found by A3, `salesagent-z6nr.9`; #6 and #7 by B3,
`salesagent-z6nr.14`, by RUNNING the shipped conformance data against `adcp==6.6.0`.)

| # | Divergence | Consequence |
|---|---|---|
| 1 | `adcp.signing.verifier.VerifierCapability` (verifier.py:88) carries **4 of `request_signing`'s 8 properties** — i.e. **2 of its 6 operation buckets** (`supported_for`, `required_for`). Missing: `warn_for`, `protocol_methods_supported_for`, `protocol_methods_warn_for`, `protocol_methods_required_for`. | Shadow mode (§10) and the JSON-RPC method namespace are **ours to implement**. Passing `warn_for` into `VerifierCapability` silently drops it. |
| 2 | `request_target_uri_malformed` (security.mdx step 10) and `request_body_malformed` (step 14) exist in the prose and in **no** SDK constant and **no** vector. | We emit both from our own layer. Do not "resolve" the divergence by dropping the codes. |
| 3 | `verify_starlette_request`'s docstring (middleware.py:38-44) claims Starlette caches the body so downstream handlers re-reading it get the same bytes. The cache lives on the `Request` **instance** the middleware constructs, not on the one the downstream app builds from the same scope — the receive channel **is** drained. | The `_receive` replay shim already in `src/app.py:455-462` is required. The docstring is wrong. |
| 4 | `adcp.signing.agent_resolver._fetch_capabilities` (agent_resolver.py:179-305) performs a raw `GET <agent_url>` and requires a JSON **object** body. security.mdx:1142 says the opposite verbatim: "This is a **protocol-level** call — invoke `get_adcp_capabilities` via the agent's declared transport (MCP `tools/call` or A2A skill invocation), **not a raw HTTP `GET`** against `A`. The agent URL is the protocol endpoint, not a JSON capabilities document." | `resolve_agent(<our agent url>)` cannot reach hop 2 against us no matter what we publish: `/mcp` answers GET with a redirect to an SSE stream and `/a2a` is JSON-RPC POST. Any test driving the resolver must seed hop 1 through `_capabilities_client_factory` (`tests/e2e/test_trust_root_e2e.py` does, and leaves hops 2 and 3 live). |
| 5 | `adcp.signing.brand_jwks._pick_agent` (brand_jwks.py:824-869) selects the `agents[]` entry by `type` plus an optional `agent_id` and **never compares `url` to the agent URL `A`** — so it raises `agent_ambiguous` for the shape the schema explicitly blesses (`#/definitions/agents`: "Multiple entries with the same type are permitted when they have distinct url values, such as one endpoint URL per tenant or property scope"), while security.mdx:1104 step 5 defines the match as byte-equality on `url`. | We publish one `agents[]` entry PER ENDPOINT we serve (`/mcp/`, `/a2a`) with distinct `id`s, per the schema — an origin-only `url` would byte-equal nothing any counterparty ever invoked. Our own resolver calls must pass `agent_id`. Do not "resolve" this by collapsing to one entry. |
| 6 | **Canonicalization.** `adcp.signing.canonical._canon_authority` (canonical.py:128-150) never calls the SDK's OWN `adcp.signing._idna_canonicalize.canonicalize_host` (four sibling SDK modules do), performs **no** malformed-authority rejection, and `canonicalize_target_uri` drops a trailing empty query. MEASURED: **8 of the 31 shipped `canonicalization.json` cases fail** against `adcp==6.6.0` — the 2 IDN cases, `trailing-empty-query-preserved`, and all 6 `reject: true` cases (5 accepted outright, `malformed-ipv6-missing-closing-bracket` refused with a bare `ValueError` carrying no code). The same root cause makes the SDK answer request vector `negative/026` with `request_signature_invalid` instead of `request_signature_header_malformed`. | `src/core/signing/canonical.py` is the thin seam: it DELEGATES every canonical form to the SDK and adds ONLY the spec's rejection set (url-canonicalization.mdx steps 2-3), so we never carry a second canonicalizer. 28 of 31 cases run as conformance through it; the 2 IDN mapping cases and `trailing-empty-query-preserved` are **not implementable at a verifier boundary** (the first are signer-side — a comparer MUST reject, not re-normalize; the third is destroyed by ASGI, which hands `query_string=b""` for both `/p` and `/p?`) and run as named our-obligation tests. **0 skipped, 0 xfailed.** |
| 7 | **`request_target_uri_malformed` is now GRADED, and the constant still does not exist.** Cross-reference #2, which flagged the constant's absence but recorded that no vector graded it. That is no longer true: `canonicalization.json`'s 6 `reject: true` cases expect exactly this string, grounded at url-canonicalization.mdx ("Malformed authorities are rejected with `request_target_uri_malformed` on the signing path"). NOTE the vector README's worked example is **stale** and shows `request_signature_header_malformed`; the shipped DATA wins. | Defined in our layer as `src.core.signing.canonical.REQUEST_TARGET_URI_MALFORMED`, per #2's own instruction. **Keep it apart from `request_signature_header_malformed`**: request vector `negative/026` legitimately expects the latter (a checklist step-1 wire rejection), the canonicalization reject set expects the former. Collapsing the two loses a graded artifact in each direction. |

**Upstream filing status (B3, `salesagent-z6nr.14`).** #6 and #7 are ONE upstream issue against
`adcontextprotocol/adcp` — they share a root cause (`_canon_authority` implements steps 4-6 of
url-canonicalization.mdx and none of steps 2-3's MUST-rejects) and one of them is the missing
constant that rejection needs. The issue body is the divergence rows above plus the three cases
that are not implementable at a verifier boundary. **Not yet filed — opening an issue on the
upstream public repo is the owner's call, not an agent's.** Nothing in this repo waits on it: the
seam implements the spec locally and 31 of 31 cases are accounted for.

---

## 2. What the schema says — `request_signing`

`dist/schemas/3.1.1/bundled/protocol/get-adcp-capabilities-response.json`
`#/properties/request_signing`.

> RFC 9421 HTTP Signatures support for incoming requests. Optional in 3.0 — capability-advertised
> so counterparties can opt into signing selectively. Required for spend-committing operations in
> 4.0 (the next breaking-changes accumulation window).

Eight properties: `supported`, `covers_content_digest`, `required_for`, `warn_for`,
`supported_for`, `protocol_methods_supported_for`, `protocol_methods_warn_for`,
`protocol_methods_required_for`.

### `x-adcp-validation` rules, verbatim

| Property | Rule |
|---|---|
| `required_for` | `subset_of: request_signing.supported_for` |
| `warn_for` | `disjoint_with: request_signing.required_for`, `subset_of: request_signing.supported_for` |
| `protocol_methods_required_for` | `subset_of: request_signing.protocol_methods_supported_for` |
| `protocol_methods_warn_for` | `disjoint_with: request_signing.protocol_methods_required_for`, `subset_of: request_signing.protocol_methods_supported_for` |

Operation names in the three non-`protocol_methods_` buckets MUST be **AdCP protocol operation
names** — never MCP tool names, never A2A skill renames. JSON-RPC methods such as `tasks/cancel`
belong in the `protocol_methods_*` buckets.

`covers_content_digest` — enum `required | forbidden | either` (default `either`):

> 'required': signers MUST cover content-digest (body is bound to the signature); body-unbound
> signatures rejected with `request_signature_components_incomplete`. 'forbidden': signers MUST NOT
> cover content-digest; body-bound signatures rejected with `request_signature_components_unexpected`.

---

## 3. What the schema says — `webhook_signing`

`#/properties/webhook_signing`. Four properties:

| Property | Values | Note |
|---|---|---|
| `supported` | boolean | Forced `true` by `must_equal_when` — see below |
| `profile` | enum `["adcp/webhook-signing/v1"]` | MUST match the `tag=` parameter we emit in `Signature-Input` |
| `algorithms` | enum `["ed25519", "ecdsa-p256-sha256"]` | Closed. **No RSA.** |
| `legacy_hmac_fallback` | boolean (default false) | HMAC-SHA256 fallback on the legacy `push_notification_config.authentication`; removed in 4.0 |

`#/properties/webhook_signing/properties/supported`
`x-adcp-validation.verifier_constraints.must_equal_when` — `value: true`, `any_of`:

1. `media_buy.reporting_delivery_methods` **contains** `"webhook"`
2. `media_buy.content_standards.supports_webhook_delivery` **equals** `true`
3. `wholesale_feed_webhooks.supported` **equals** `true`

Exactly three triggers. `media_buy.offline_delivery_protocols` is **not** one of them — the
`_UNBACKED_BLOCKS` comment that said otherwise was corrected under #1729 (D3).

Rationale, from the schema itself: *"emitting state-changing webhooks unsigned is a downgrade
vector that lets an on-path attacker forge delivery callbacks."*

---

## 4. What the schema says — `identity`

`#/properties/identity`. Four properties: `brand_json_url`, `per_principal_key_isolation`,
`key_origins`, `compromise_notification`. The last three are advisory posture.

`brand_json_url` is the load-bearing one:

> `brand_json_url` is **load-bearing** for signature verification: when the agent declares any
> signing posture (`request_signing.supported_for`/`required_for` non-empty,
> `webhook_signing.supported === true`, or any `key_origins` subfield), `brand_json_url` MUST be
> present (storyboard-enforced in 3.x; schema-required in 4.0).

`x-adcp-validation` on `brand_json_url`:

- `trust_root: true`
- `required_when.any_of`: `request_signing.supported_for` non-empty · `request_signing.required_for`
  non-empty · `request_signing.protocol_methods_supported_for` non-empty ·
  `request_signing.protocol_methods_required_for` non-empty · `webhook_signing.supported == true` ·
  `identity.key_origins` any subfield present
- `schema_required_when`: `adcp.supported_versions` matches `^4\.`
- `verifier_constraints`: `agent_url_match: byte_equal` · `origin_binding:
  etld1_or_authorized_operators` · `key_origins_consistency: mandatory_when_signing`
- `distinct_from: sponsored_intelligence.brand_url`

**Consequence for us: even an inbound-only posture forces us to publish a trust root** — brand.json,
`adagents.json` `signing_keys`, and a JWKS. That is A3, and it is not optional.

`agent_url_match: byte_equal` is why §12 pins one canonical agent URL per tenant.

---

## 5. What is graded — the `signed_requests` storyboard

`dist/compliance/3.1.1/universal/signed-requests.yaml`.

**Gating** (verbatim):

> This storyboard runs for any agent advertising `request_signing.supported: true` in
> `get_adcp_capabilities`. Agents that do not advertise support are not tested against this
> storyboard — absence of advertisement is not a failure, it is a declaration that the agent does
> not offer verified signed requests.

Not advertising is conformant. Advertising is what buys us the grading.

**Grading** (verbatim):

> Observable-behavior only. The runner constructs signed HTTP requests exactly as documented in the
> conformance vectors at `/compliance/{version}/test-vectors/request-signing/` and sends them to
> the agent. The agent's responses are compared against the vectors' `expected_outcome`:
>
> - Positive vectors MUST produce a non-4xx response — the agent accepted the signed request.
> - Negative vectors MUST produce `401` with `WWW-Authenticate: Signature error="<code>"`, where the
>   `<code>` matches the vector's `expected_outcome.error_code` byte-for-byte. The checklist step
>   number is informational; grading is on the stable error code only.

Two things follow. The error code is the graded artifact, so it must be produced byte-for-byte —
`adcp.signing.middleware.unauthorized_response_headers(exc)` (middleware.py:20) already returns
exactly `{"WWW-Authenticate": 'Signature error="<code>"'}`, so B1 writes no header formatting. And
the checklist step numbers are *informational*: never grade on them, never let a test assert them.

Also from the storyboard: a seller advertising both `request_signing.supported: true` and a
specialism is graded on both, independently. The deprecated `signed-requests` specialism enum
still exists for back-compat but SHOULD NOT be claimed — `request_signing.supported: true` is the
declaration.

---

## 6. The 40 conformance vectors

`dist/compliance/3.1.1/test-vectors/request-signing/`.

**The count is 40 — 12 positive + 28 negative** — plus `canonicalization.json` (a separate flat,
crypto-free case set) and `keys.json`. Verified twice by directory listing at tag `v3.1.1`.

The epic body, its DoD checkbox, its child-index tree line, and `salesagent-z6nr.14`'s title all
said **28**. 28 is the *negative* count, propagated from the test-kit's own header comment
(`signed-requests-runner.yaml` says "28 conformance vectors") and from the storyboard's stale
narrative — whose positive-phase enumeration stops at `008` (the directory has 009-012) and whose
negative list jumps 020 → 028 with "Vectors 021-027 … cover later additions". **The vectors are the
graded artifact; the narrative is not.** B3 must run 40 or it can pass its own acceptance while
skipping 12 cases. A1 corrects all four ticket sites.

### Positive (12) — all MUST produce a non-4xx

| Vector | What it exercises | Our owning component |
|---|---|---|
| `001-basic-post` | Ed25519, no content-digest coverage | B1 middleware → SDK verifier |
| `002-post-with-content-digest` | content-digest covered | SDK verifier (step 11) |
| `003-es256-post` | ES256 (edge-runtime profile) | SDK verifier |
| `004-multiple-signature-labels` | multiple `Signature-Input` labels — verifier MUST process exactly one | SDK verifier |
| `005-default-port-stripped` | explicit `:443` stripped in canonicalization | SDK canonicalization |
| `006-dot-segment-path` | `/./` collapsed | SDK canonicalization |
| `007-query-byte-preserved` | query byte order preserved, not alphabetized | SDK canonicalization |
| `008-percent-encoded-path` | percent-encoded bytes normalized to uppercase hex | SDK canonicalization |
| `009-percent-encoded-unreserved-decoded` | unreserved bytes decoded per RFC 3986 §6.2.2 | SDK canonicalization |
| `010-percent-encoded-slash-preserved` | `%2F` preserved literally through dot-segment removal | SDK canonicalization |
| `011-ipv6-authority` | IPv6 literal, brackets preserved in `@target-uri`/`@authority` | SDK canonicalization + B1 `@authority` derivation |
| `012-ipv6-authority-default-port-stripped` | IPv6 + explicit `:443` | same |

The eight canonicalization vectors are the strongest argument for adopting the SDK wholesale: each
is a distinct way a hand-rolled canonicalizer silently diverges.

### Negative (28) — all MUST produce `401` + `WWW-Authenticate: Signature error="<code>"`

| Vector | `expected_outcome.error_code` | Our owning component |
|---|---|---|
| `001-no-signature-header` | `request_signature_required` | **B2** operation resolution (op ∈ `required_for`) |
| `002-wrong-tag` | `request_signature_tag_invalid` | SDK verifier (step 3) |
| `003-expired-signature` | `request_signature_window_invalid` | SDK verifier (step 5) |
| `004-window-too-long` | `request_signature_window_invalid` | SDK verifier (step 5) |
| `005-alg-not-allowed` | `request_signature_alg_not_allowed` | SDK verifier (step 4) |
| `006-missing-covered-component` | `request_signature_components_incomplete` | SDK verifier (step 6) |
| `007-missing-content-digest` | `request_signature_components_incomplete` | SDK verifier (step 6) — needs `covers_content_digest: required` |
| `008-unknown-keyid` | `request_signature_key_unknown` | **A5/B1** kid→JWK resolution (step 7) |
| `009-key-ops-missing-verify` | `request_signature_key_purpose_invalid` | SDK verifier (step 8) |
| `010-content-digest-mismatch` | `request_signature_digest_mismatch` | SDK verifier (step 11) |
| `011-malformed-header` | `request_signature_header_malformed` | SDK verifier (step 1) |
| `012-missing-expires-param` | `request_signature_params_incomplete` | SDK verifier (step 2) |
| `013-expires-le-created` | `request_signature_window_invalid` | SDK verifier (step 5) |
| `014-missing-nonce-param` | `request_signature_params_incomplete` | SDK verifier (step 2) |
| `015-signature-invalid` | `request_signature_invalid` | SDK verifier (step 10) |
| `016-replayed-nonce` | `request_signature_replayed` | **A4** replay store (step 12) — stateful, see §7 |
| `017-key-revoked` | `request_signature_key_revoked` | **A5** revocation (step 9) — stateful, see §7 |
| `018-digest-covered-when-forbidden` | `request_signature_components_unexpected` | SDK verifier (step 6) — needs `covers_content_digest: forbidden` |
| `019-signature-without-signature-input` | `request_signature_header_malformed` | SDK verifier (step 1) |
| `020-rate-abuse` | `request_signature_rate_abuse` | **A4** `at_capacity` (step 9a) — stateful, see §7 |
| `021-duplicate-signature-input-label` | `request_signature_header_malformed` | SDK verifier (step 1) |
| `022-multi-valued-content-type` | `request_signature_header_malformed` | SDK verifier (step 1) |
| `023-multi-valued-content-digest` | `request_signature_header_malformed` | SDK verifier (step 1) |
| `024-unquoted-string-param` | `request_signature_header_malformed` | SDK verifier (step 1) |
| `025-jwk-alg-crv-mismatch` | `request_signature_key_purpose_invalid` | SDK verifier (step 8) |
| `026-non-ascii-host` | `request_signature_header_malformed` | SDK verifier (step 1) / B1 `@authority` |
| `027-webhook-registration-authentication-unsigned` | `request_signature_required` | **B2** — webhook registration carrying `push_notification_config.authentication` |
| `028-unsigned-protocol-method-required` | `request_signature_required` | **B2** — JSON-RPC `tasks/cancel`, bound off `protocol_methods_required_for` |

Three vectors are ours end to end because the SDK cannot express their inputs: 001, 027 and 028 all
turn on **which operation this request is**, and `VerifierCapability` has nowhere to put a
`protocol_methods_*` list (divergence #1). B2 binds `tasks/cancel` off the JSON-RPC **`method`**
field, not `params.name`.

---

## 7. The stateful-vector contract

`dist/compliance/3.1.1/test-kits/signed-requests-runner.yaml`. Values verbatim.

- `endpoint_scope: sandbox` — *"The replay-window contract sends a live, validly-signed mutating
  request as its first step… Running this against a production endpoint would create a real media
  buy. Graders MUST target a sandbox/staging endpoint… Agents advertising `request_signing.supported:
  true` SHOULD expose a dedicated grading endpoint rather than grading in prod."* This is why B4
  exists and is not polish.
- `harness_mode: black_box` — *"AdCP Verified grading runs in black_box mode only."* White-box state
  injection via a vector's `test_harness_state` block does not count.
- `runner_signing_keys` — `test-ed25519-2026` (`ed25519`) and `test-es256-2026`
  (`ecdsa-p256-sha256`), JWKS at the vectors' `keys.json`. *"The agent's verifier MUST treat these
  keyids as a registered test counterparty whose JWKS contains the corresponding public keys with
  `adcp_use: "request-signing"`."*

| Vector | Contract field | Value |
|---|---|---|
| `016-replayed-nonce` | `black_box_behavior` | `repeat_request` |
| | `max_interval_seconds` | `5` |
| | `min_replay_ttl_seconds` | `10` |
| `017-key-revoked` | `pre_revoked_keyid` | `test-revoked-2026` |
| `020-rate-abuse` | `grading_target_per_keyid_cap_requests` | `100` |
| | `production_min_per_keyid_cap_requests` | `1000000` |
| | `window_seconds` | `60` |

On 016 the contract warns of a **silent false green**: *"Otherwise the cache entry for the first
request may evict before the second arrives and the vector will pass spuriously (i.e., both requests
accepted = no replay rejection)."* A TTL under 10s makes the vector pass while replay protection is
broken.

On 020, the sentence that makes the two-tier cap legitimate rather than a backdoor smuggled past
`harness_mode: black_box`:

> `grading_target_per_keyid_cap_requests` is the cap the runner will target during grading — NOT a
> production recommendation. Agents MAY configure a lower cap for the test-kit counterparty only so
> grading finishes in a reasonable time. Production caps MUST follow the spec recommendation at
> …§per-keyid cap (at least 1,000,000 entries per keyid). Implementers copying a value from this
> file into production code SHOULD use `production_min_per_keyid_cap_requests` below as the floor.

and its `scope.in_scope` line naming it in-contract:

> Grading-time cap the runner will target for rate-abuse grading (NOT a production recommendation;
> see rate_abuse block).

**Explicitly out of contract** (`scope.out_of_scope`): error-code strings (they live in the
vectors, graded byte-for-byte), checklist step numbers ("informational only"), our internal TTL/cap
storage mechanism, and production verifier configuration. So the cap must be resolvable
**per counterparty keyid** — one global constant cannot be both 100 and 1,000,000.

---

## 8. The verifier checklist — 15 checks, and two ordering invariants

`security.mdx` §"Verifier checklist (requests)", read at tag `v3.1.1`:

> Otherwise, verifiers MUST apply these **15 checks (14 numbered steps plus sub-step 9a)** in order,
> short-circuiting on the first failure.

The same release contradicts itself twice — the quickstart at :932 says *"all 14 checks (13
numbered steps plus sub-step 9a)"*, and `signed-requests.yaml` says the same. **The enumerated body
is the authority**: steps 1-14 plus 9a. Step 14 decomposes into 14a (strict-parse) and 14b (logging
discipline), which the spec says are *"elaborations of one check, not separate checks in the count"*.

Steps, abridged to code-emitting decisions:

| Step | Check | Code on failure |
|---|---|---|
| 1 | Parse `Signature-Input`/`Signature` per RFC 9421 §4 | `header_malformed` |
| 2 | `created`,`expires`,`nonce`,`keyid`,`alg`,`tag` all present | `params_incomplete` |
| 3 | `tag` is exactly `adcp/request-signing/v1` | `tag_invalid` |
| 4 | `alg` ∈ {`ed25519`,`ecdsa-p256-sha256`} — *"Library defaults MUST NOT be relied upon"* | `alg_not_allowed` |
| 5 | `expires > created`, `created ≤ now+60s`, `expires ≥ now−60s`, `expires−created ≤ 300s` | `window_invalid` |
| 6 | covered components ⊇ `@method`,`@target-uri`,`@authority`; `content-type` when a body exists; `content-digest` per `covers_content_digest` | `components_incomplete` / `components_unexpected` |
| 7 | resolve `keyid` → JWK; run the brand_json_url discovery preamble on cache miss; on `kid` miss **refetch once, subject to the 30-second cooldown** | `key_unknown`, `brand_*`, `key_origin_*` |
| 8 | JWK `use == "sig"`, `key_ops` ∋ `"verify"`, `adcp_use == "request-signing"` — *absent `adcp_use` MUST be treated as non-conforming* | `key_purpose_invalid` |
| 9 | revocation list; staleness beyond grace also rejects | `key_revoked` / `revocation_stale` |
| **9a** | per-keyid replay-cache cap | `rate_abuse` |
| 10 | canonical signature base + `@authority` derivation, then crypto verify | `invalid` / `request_target_uri_malformed` |
| 11 | recompute content-digest when covered | `digest_mismatch` |
| 12 | `(keyid, nonce)` against the replay cache | `replayed` |
| 13 | **insert** `(keyid, nonce)` with TTL `(expires − now) + 60s` | — |
| 14 | body well-formedness — reject duplicate object keys | `request_body_malformed` |

### Two ordering invariants the spec calls out as future-edit hazards — preserve both

1. **Steps 9 and 9a run BEFORE crypto verify (step 10).** *"a compromised or misconfigured signer
   exhausting its cap MUST NOT force amplified Ed25519/ECDSA work on the verifier."* And 9a runs
   *after* keyid resolution (step 7) *"so the cap-state oracle only responds for keys the verifier
   has already committed to recognizing — running 9a earlier would let an attacker probe
   verifier-internal rate-limit state across the full keyid space."*
2. **The replay insert is step 13 — after 10-12, before 14.** *"so that a captured frame carrying a
   valid signature over a malformed body cannot be replayed to burn crypto-verify CPU on each
   retry — the nonce is burned on first sighting of a cryptographically-valid frame."*

B1 is reviewed against both.

### The `@authority` rule (step 10) is load-bearing for us specifically

> verifiers MUST derive `@authority` from the HTTP/2+ `:authority` pseudo-header when present,
> otherwise from the as-received HTTP/1.1 `Host` header — **NOT from reverse-proxy routing state,
> load-balancer metadata, or any `Host` value a forward proxy may have rewritten in transit.**

Skipping it *"silently accepts a cross-vhost replay vector"*. We run behind nginx and route tenants
by `Host`/`Apx-Incoming-Host` — see §12, where the same sentence forces a decision about our agent
card.

Step 14 has **no conformance vector** and **no SDK constant** (divergence #2). It is a MUST the
storyboard does not grade, so it is graded by our own BDD or it is not graded at all.

---

## 9. The configuration surface

### 9.1 The split is settled by the graded feature file, not by taste

`tests/bdd/features/BR-UC-010-discover-seller-capabilities.feature` (generated, authoritative)
drives every signing scenario through **the tenant declaration**:

- `:1043` `Given the tenant declares request_signing posture <posture>` → asserts `supported`,
  `covers_content_digest`
- `:1064` `… supported_for=[…] required_for=[…] protocol_methods_supported_for=["tasks/cancel"]
  protocol_methods_required_for=["tasks/cancel"]`
- `:1081` `… supported_for=[…] required_for=[…] warn_for=[…]` → subset + disjoint assertions
- `:1094` `Given the tenant declares webhook_signing posture <posture>` → `supported`, `profile`,
  `algorithms`, `legacy_hmac_fallback`
- `:1521` `the tenant identity and signing posture are configured for <boundary_point>` → the
  `required_when` rejection, `CONFIGURATION_ERROR`, recovery `terminal`, naming `brand_json_url`

Every "invalid" row grades a `CONFIGURATION_ERROR` raised from the **declaration** path. So the
declarable posture is tenant-scoped by construction, and the relation validators belong next to the
existing `_UNBACKED_BLOCKS` loop in
`src/core/schemas/capability_declarations.py` (`:194-205`, `validate_backing()` at `:218`).

**Do not invent a third store.** Two stores exist and both are extended:
`CapabilityDeclarations` (tenant) and `src/core/config.py` (agent).

### 9.2 Tenant-level — typed fields on `CapabilityDeclarations`

Stored inside the existing `tenants.capability_declarations` `JSONType` column
(`src/core/database/models.py:112`). **No migration.**

| Field | Why it varies per tenant |
|---|---|
| `request_signing.supported` | a seller may run the verifier but not offer it to this counterparty |
| `request_signing.covers_content_digest` | per-counterparty digest policy; graded at `:1043` |
| `request_signing.supported_for` / `warn_for` / `required_for` | **the rollout dial**; graded at `:1064`, `:1081` |
| `request_signing.protocol_methods_{supported,warn,required}_for` | same dial, JSON-RPC namespace; graded at `:1064` |
| `webhook_signing.{supported,profile,algorithms,legacy_hmac_fallback}` | per-receiver RFC 9421 vs legacy HMAC; graded at `:1094` |
| `identity.brand_json_url` | per-tenant `virtual_host` ⇒ per-tenant trust root; graded at `:1521` |
| `identity.{per_principal_key_isolation,key_origins,compromise_notification}` | advisory posture, per operator |
| `media_buy.content_standards.supports_webhook_delivery` | declarable **only once C1 signs** — declaring it fires `must_equal_when` |
| `media_buy.reporting_delivery_methods` | `[webhook]` declarable after C1; `[offline]` stays unbacked under **#1729**, not this epic |

`media_buy.offline_delivery_protocols` is **#1729 only** and does not become declarable here. The
`T-UC-010-v31-reporting-delivery-methods` `offline_only` row does not graduate under #1291.

### 9.3 Agent-level — one `SigningConfig(BaseSettings)` on `AppConfig`

Composed in `src/core/config.py` following the existing `BaseSettings` sub-config precedent
(`:93-116`, `get_config()` at `:118`). Never hand-rolled `os.getenv`.

**Group A — verifier enforcement facts**

| Field | Why it cannot vary per tenant |
|---|---|
| verifier mounted (on/off) | one ASGI middleware instance serves every tenant |
| allowed algorithms | a profile constant; narrowing per tenant is not a schema-expressible posture |
| `max_skew_seconds` (60) / `max_window_seconds` (300) | RFC profile constants; a tenant override would be non-conformant |
| replay TTL floor, per-keyid cap default | properties of the shared replay store |

**Group B — our own key material and publication**

| Field | Why it cannot vary per tenant |
|---|---|
| `SigningProvider` selection + key **store kind** | one process, one key store |
| revocation list issuer origin + poll interval | one fetcher per process |
| brand.json / `adagents.json` / JWKS publication origin | one deployment origin |

**Amendment (A2, salesagent-z6nr.8).** This row originally read "`SigningProvider` selection + key
material LOCATION". Taken literally that is unimplementable: each tenant is a distinct seller
identity with its own brand domain and therefore its own key material, so there is no single
agent-level key location. A2 splits it — the **store kind** is agent-level
(`SigningConfig.provider`, plus `allowed_key_ref_schemes`, which is what lets a deployment forbid
`file:` in production), while each key's **location** is per-tenant and lives on the `signing_keys`
row's scheme-prefixed `private_key_ref` (`env:NAME` / `file:/abs/path`). A3 and C1 inherit that
split; do not re-derive it.

**Group C — counterparty key resolution** (the inbound discovery chain: checklist step 7,
`get_adcp_capabilities → identity.brand_json_url → brand.json → agents[] → jwks_uri`). This group
owns **12 of the 27 error codes** and had no config home until this note; without it A5 and B1 each
invent one ad hoc.

| Field | Why it cannot vary per tenant |
|---|---|
| counterparty JWKS cache TTL | one fetcher, one cache, shared across tenants |
| refetch cooldown (spec: 30s) | a profile constant, not a posture |
| brand.json snapshot lifetime / `max_age` | property of the shared cache |
| `allow_private_destinations` | deployment-scoped SSRF policy — **MUST be false in prod**, true only for the B4 sandbox grading endpoint |
| counterparty capabilities fetch timeout/retry | one HTTP client per process |

Note the asymmetry that makes this its own group: `identity.brand_json_url` in §9.2 is what **we
publish** (A3); Group C is about **the counterparty's**, which we fetch.

**Neither tenant nor agent: the per-keyid cap override.** §7 requires 100 for the test counterparty
and ≥1,000,000 in production. Model it as an agent-level default plus a **per-keyid counterparty
override**, never a tenant field and never a global lowering.

### 9.4 The bridge — `_UNBACKED_BLOCKS` generalizes

Today `_UNBACKED_BLOCKS` means *"this block has no field at all"*. It becomes *"this block's field
exists but the running process does not back it"*. A tenant declaring
`request_signing.supported=true` while the verifier is unmounted is refused **by name**, exactly as
today. Same for `webhook_signing.supported=true` without a provisioned webhook key, and for a
`brand_json_url` whose origin this deployment does not serve.

### 9.5 The failure mode this creates, and the decision about it

`from_tenant()` → `validate_backing()` runs on the **read** path, per request
(`src/core/tools/capabilities.py:433`). Today it is checked against a **static table**, so it can
only fail for a declaration an operator wrote. Checked against **mutable process config**,
unmounting the verifier — or rolling back the B1 middleware — would turn `get_adcp_capabilities`
into `CONFIGURATION_ERROR` for every tenant that declared `supported=true`. **Discovery would break
on rollback, for tenants who changed nothing.**

**Decision: the read path degrades; only the write path raises.**

- **Read path:** when agent-level backing is absent, the emitted posture degrades to
  `supported=false` — the honest wire fact, since the verifier really is not running — and the
  response succeeds. Log at WARNING with the tenant and the missing backing.
- **Write/config path:** keeps raising `AdCPConfigurationError` → `CONFIGURATION_ERROR`. That is
  where STRICT matters: an operator still cannot *declare* an unbacked posture.
- **Unchanged:** a **schema-relation** violation (`required_for ⊄ supported_for`, `warn_for ∩
  required_for ≠ ∅`) is a bad declaration and raises on **both** paths. The graded "invalid" rows at
  `:1064`/`:1081` depend on that. Only the **agent-backing** check degrades.

D1 must not pick one of these silently.

---

## 10. The shadow-mode ladder

The schema defines `warn_for` as the bridge: *"verifies signatures when present and logs failures
but does NOT reject… a shadow-mode bridge between `supported_for` and `required_for`."*

**Operator progression, one operation at a time:**

```
supported_for   verify when present, never reject          ← counterparties may start signing
      ↓
warn_for        verify when present, log + emit metric,    ← we learn whether they actually do,
                still never reject                            and whether they do it right
      ↓
required_for    reject unsigned with request_signature_required
```

Precedence is `required_for > warn_for > supported_for`. Relations: `required_for ⊆ supported_for`,
`warn_for ⊆ supported_for`, `warn_for ∩ required_for = ∅`.

**The metric an operator watches before promoting.** Per `(operation, keyid)` counters emitted from
the B1 middleware — the only layer that sees the outcome before it is either swallowed (warn) or
turned into a 401:

- `signed_ok`
- `signed_failed{code}`
- `unsigned`

**Promotion criterion:** over a full traffic cycle, `unsigned == 0` **and** `signed_failed == 0` for
that operation across every active counterparty. The breakdown by code is what distinguishes
*"counterparty is not signing yet"* (promote later) from *"counterparty is signing wrong"* (fix
before promoting) — a single aggregate number cannot tell those apart, and promoting on the wrong
one 401s live traffic.

**Implementation consequence — the trap.** The SDK verifier cannot be told about `warn_for`
(divergence #1). B1 implements warn by calling the verifier, catching `SignatureVerificationError`,
emitting the metric, and continuing. Passing `warn_for` into `VerifierCapability` would be silently
dropped, degrading the operation to plain `supported_for` semantics — **which produces the identical
non-rejecting response**, so the bug is invisible at the wire level and shows up only as a missing
metric. **B1 owes a test that fails if warn degrades to `supported_for`.**

---

## 11. `SigningProvider` selection and the replay-store backend

### `SigningProvider`

`adcp.signing.provider.SigningProvider` (provider.py:85) is a 3-method Protocol: `async
sign(signature_base) -> bytes`, `key_id()`, `algorithm()`. `InMemorySigningProvider` (:163) ships.

**Config key `signing.provider` on the agent-level `SigningConfig`, enum `in_memory` (default) |
`kms`.** `in_memory` constructs `InMemorySigningProvider` from a PEM loaded via
`adcp.signing.load_private_key_pem`.

**A KMS/HSM provider is OUT of scope for this epic.** It is a 3-method Protocol, so a follow-up adds
one without touching a single caller. Two things the follow-up inherits, recorded here so they are
not rediscovered: the ECDSA `DigestSign`-not-double-hash requirement (provider.py:85-108) is a
KMS-integration concern with no in-memory analogue, and **selecting `kms` before that lands must
fail at config validation, not at first signature.**

### Replay-store backend (feeds A4)

**Decision: implement `adcp.signing.replay.ReplayStore` ourselves** — three methods (`seen`,
`remember`, `at_capacity`) over the existing SQLAlchemy session in a repository, with
`adcp/signing/pg/replay_store.sql` translated into an Alembic migration so the table is versioned
like every other.

**Not `adcp.signing.pg.PgReplayStore`**, which hard-requires `psycopg` + `psycopg_pool`
(`pg/replay_store.py:85-91`) while we pin `psycopg2-binary` (`pyproject.toml:20`, with
`types-psycopg2`) — `import psycopg` raises `ModuleNotFoundError` in this venv — **and** opens its
own `ConnectionPool`, which `test_architecture_repository_pattern.py` forbids and whose allowlist
may only shrink. Adding a second driver and a second pool to satisfy a three-method Protocol is not
a close call. A4's own ticket text reaches option (b) independently.

**The mitigation A4 must carry.** `seen`/`remember`/`at_capacity` (replay.py:21-28) are **sync**
`def`, and the verifier calls them **inline** at verifier.py:304 (step 9a), :348 (step 12), :358
(step 13) — from a sync function that `verify_starlette_request` invokes inside an async request.
A session-backed store therefore does 2-3 **blocking** Postgres round-trips on the event loop per
signed request. `PgReplayStore` would be no better (psycopg3 sync pool), so this is not an argument
between the options — it is a property of the SDK's Protocol. It is also the same class as the
owner-confirmed *"adapters must not run in the HTTP request cycle"* direction. Wrap the store calls
— or the whole `verify_request_signature` call — in `anyio.to_thread.run_sync`, with a dedicated
short-lived session per call, **never** the request-scoped UoW session (not thread-safe to share).

### The one place two named reuse targets do not compose

`verify_request_signature` (verifier.py:170) is **sync**, and `VerifyOptions.jwks_resolver`
(verifier.py:138) types the **sync** `JwksResolver` (jwks.py:91). But `BrandJsonJwksResolver`
(brand_jwks.py:320) — which implements the entire step-7 discovery chain with SSRF validation and
IP pinning — implements `AsyncJwksResolver` **only** (`async def resolve`, :405), and
`as_async_resolver` (jwks.py:508) converts sync→async, the wrong direction. `jwks.py` ships no sync
brand.json resolver: `CachingJwksResolver` and `StaticJwksResolver` take a bare `jwks_uri` and skip
discovery entirely.

**Decision:** the ASGI middleware **awaits** `BrandJsonJwksResolver.resolve(kid)` first, then passes
a `StaticJwksResolver` seeded with that key into the sync verify. Discovery I/O stays off the sync
path and the SDK's SSRF/IP-pinning chain stays intact.

**Rejected:** writing our own sync brand.json resolver — ~600 lines of SSRF and IP-pinning logic
duplicated, and ours to keep correct forever.

**Consequence:** A5 is *"wire + own the kid→JWK resolution step"*, not *"wire"*. B1 owns the
await-then-seed ordering.

---

## 12. The canonical per-tenant agent URL — FYI to the owner

`identity.brand_json_url`'s `verifier_constraints` demand `agent_url_match: byte_equal` against the
`agents[].agent_url` **we publish**. So what must be pinned is one published string, not a
per-request derivation.

Today `_create_dynamic_agent_card` (`src/app.py:346-388`) derives the agent card URL per request
from `Apx-Incoming-Host`, then `Host`, then `X-Forwarded-Proto` — **exactly the reverse-proxy
routing state security.mdx step 10 forbids relying on.** The same tenant can therefore publish
several different `agent_url` strings depending on which hostname the caller used, so a byte-equal
compare is a coin flip.

**Decision:** one canonical stored agent URL per tenant — `Tenant.virtual_host` when set, else
`https://{subdomain}.{base_domain}` — computed by a single function and emitted **byte-identically**
by the agent card, brand.json `agents[].agent_url`, and the JWKS pointer. `ADCP_AGENT_URL`
(`src/admin/blueprints/authorized_properties.py:224`) becomes the deployment-level base, not a
second source of truth.

**A3's acceptance becomes:** *the agent card and brand.json emit a byte-identical `agent_url` for
the same tenant.*

Flagged for the owner because it changes existing agent-card behavior. It does not block A1.

### Corrections from A3 (`salesagent-z6nr.9`), which implemented this

1. **The field is `agents[].url`, not `agents[].agent_url`.** `dist/schemas/3.1.1/brand.json`
   `#/definitions/brand_agent_entry` has `required: [type, url, id]` and no `agent_url` anywhere.
   Grep for the wrong name and you find nothing to match against.
2. **It is one entry PER ENDPOINT, not one origin.** security.mdx:1104 step 5 byte-equals the URL
   whose `get_adcp_capabilities` the counterparty invoked, and that is an endpoint — the schema
   calls `url` "Agent endpoint URL (MCP or A2A)" and :1104's own worked failure example is
   `https://x.com/mcp` vs `https://x.com/mcp/`. A bare origin byte-equals nothing anybody ever
   called. We publish `{origin}/mcp/` and `{origin}/a2a` (paths verified against the running app:
   `GET /mcp` 307s to `/mcp/`; `GET /a2a` does not redirect), each with a distinct `id`. The
   schema blesses this explicitly under `#/definitions/agents`. See SDK divergence #5 for why
   the SDK's `_pick_agent` is not evidence against it.
3. **The origin binding is eTLD+1 EQUALITY** (security.mdx:1102 step 3), not same-host. We serve
   brand.json on the tenant's own host, which is sufficient and strictly stricter — but nobody
   should later read "same host" as the normative rule.
4. **`ADCP_AGENT_URL` is ranked BELOW the tenant's own host**, not above it. As a top-priority
   override it would collapse every tenant onto one URL, which is the defect this section exists
   to remove. It is the base for deployments that have no per-tenant host at all.
5. Implemented in `src/core/agent_identity.py`. Two call sites migrated
   (`_create_dynamic_agent_card`, `_construct_agent_url`); `create_agent_card`
   (`adcp_a2a_server.py:2214`) is a static default that is always overridden per request and was
   deliberately left alone.

---

## 13. PR-body citation block

Every child PR of #1291 pastes this, filled in. It discharges CLAUDE.md's spec-grounding gate
per-PR without re-deriving anything.

```markdown
### Spec grounding

- **Pinned version:** AdCP 3.1.1 (`adcp==6.6.0`), guarded by `tests/unit/test_adcp_spec_version.py`
- **Spec source:** `adcontextprotocol/adcp` @ tag `v3.1.1` — read via `git show v3.1.1:<path>`
- **Mandating section:** `<dist/schemas/3.1.1/... #/pointer>` or
  `<dist/docs/3.1.0/building/by-layer/L1/security.mdx §section>` (read at tag v3.1.1)
- **Graded by:** `dist/compliance/3.1.1/universal/signed-requests.yaml` — vectors `<ids>` /
  BR-UC-010 tags `<tags>`   ·   or the literal word **ungraded**, with the reason
- **Design note:** `.claude/notes/rfc9421-signing-adoption.md` §`<n>`
- **SDK divergence touched:** none | #1 warn_for/protocol_methods | #2 spec-only codes | #3 body cache
```

Filled example, from B3:

```markdown
### Spec grounding

- **Pinned version:** AdCP 3.1.1 (`adcp==6.6.0`), guarded by `tests/unit/test_adcp_spec_version.py`
- **Spec source:** `adcontextprotocol/adcp` @ tag `v3.1.1` — read via `git show v3.1.1:<path>`
- **Mandating section:** `dist/docs/3.1.0/building/by-layer/L1/security.mdx` §"Verifier checklist
  (requests)" — the 15 checks, applied in order, short-circuiting on first failure
- **Graded by:** `dist/compliance/3.1.1/universal/signed-requests.yaml` against all 40 vectors at
  `dist/compliance/3.1.1/test-vectors/request-signing/{positive,negative}/` plus
  `canonicalization.json`; stateful vectors 016/017/020 additionally gated on
  `dist/compliance/3.1.1/test-kits/signed-requests-runner.yaml`
- **Design note:** `.claude/notes/rfc9421-signing-adoption.md` §6, §7, §8
- **SDK divergence touched:** #1 (vectors 001/027/028 need operation and protocol-method binding
  that `VerifierCapability` cannot express)
```

---

## 14. Corrections this note makes to #1291's own tickets

Recorded so the next reader knows the epic text was wrong before it was right.

| Where | Was | Is |
|---|---|---|
| Epic body, DoD checkbox, child-index tree line, `salesagent-z6nr.14` title + description | "28 conformance vectors" | **40** (12 positive + 28 negative) + `canonicalization.json` |
| Epic body, this note's own brief | `dist/docs/<version>/building/implementation/*.mdx` | `dist/docs/3.1.0/building/by-layer/L1/security.mdx`, read at tag `v3.1.1` |
| Epic body | "27 codes … mapped to the verifier checklist step" | 27 confirmed; **15 graded** by the negative vectors, **12 integration-only** by the vectors' own README, **2 in prose with no SDK constant** |
| Everywhere | "the 14-check verifier checklist" | **15 checks** (14 numbered + 9a); the "14" in the quickstart and in `signed-requests.yaml` contradicts the enumerated body |
| `_UNBACKED_BLOCKS`, conftest park (fixed by D3 / #1729) | `offline_delivery_protocols` gated on #1291 | gated on **#1729**; `must_equal_when` has exactly three triggers and offline delivery is not one |
| A5 (`salesagent-z6nr.11`) scope | "wire `CachingRevocationChecker`" | wire **+ own the kid→JWK resolution step** (§11, sync/async) |

### The 27 `request_signature_*` codes

**15 graded** by the negative vectors: `alg_not_allowed`, `components_incomplete`,
`components_unexpected`, `digest_mismatch`, `header_malformed`, `invalid`, `key_purpose_invalid`,
`key_revoked`, `key_unknown`, `params_incomplete`, `rate_abuse`, `replayed`, `required`,
`tag_invalid`, `window_invalid`.

**12 integration-only** — the vectors' README: they *"do not exercise live JWKS fetch, brand.json
discovery, or revocation-list polling … those require live endpoints and belong in integration
suites"*: `revocation_stale`, `jwks_unavailable`, `jwks_untrusted`, `brand_json_url_missing`,
`capabilities_unreachable`, `brand_json_unreachable`, `brand_json_malformed`,
`brand_origin_mismatch`, `agent_not_in_brand_json`, `brand_json_ambiguous`, `key_origin_mismatch`,
`key_origin_missing`. All twelve are emitted by the §9.3 Group C subsystem.

**2 in the prose, in no SDK constant and no vector**: `request_target_uri_malformed` (step 10),
`request_body_malformed` (step 14). We emit both from our own layer and file the gap upstream.

# The egress seam and the SDK boundary

Where the seam is, what the `adcp` SDK owns, what this repo implements on top,
and which parts of that are temporary.

Companion to [security/outbound-egress.md](../security/outbound-egress.md),
which states the rule for people who just need to make a request. This document
is for people changing the seam, or deciding whether a new concern belongs here
or upstream.

## The module map

```
src/core/security/
  outbound_http.py          the seam. send / asend. the only public entry point
  egress/
    policy.py               the address + scheme verdicts, and the one predicate they share
    attempts.py             the retry SCHEDULE as pure steppable values — no I/O, no httpx
    response.py             OutboundResult — the closed response shape consumers read
    destination.py          the typed notion of WHERE a URL came from, at construction time
```

Each module owns exactly one decision, and the split is deliberate:

- **`attempts.py` has no `httpx` import and does no sleeping.** It is a state
  machine returning retry / success / terminal, which `send` and `asend` drive
  *identically*. Before it existed the value-level decisions were already shared
  but the two loops that consumed them were not, which is where sync and async
  drifted.
- **`response.py` closes the response shape.** `OutboundResult` used to carry a
  live `httpx.Response`, so four call sites programmed against httpx directly
  while the import ban was still satisfied — the ban was true and useless at the
  same time. The closed shape is what makes "no raw egress" mean something.
- **`destination.py` is not `UrlProvenance`.** They answer different questions
  at different moments: `UrlProvenance` answers *"who do I blame in this
  refusal"* when a dial fails, and deliberately never carries the URL;
  `VendorConstant` answers *"where in source did this constant come from"* when
  a call site builds a URL, and does carry it. A call site may legitimately use
  both.

## What comes from the SDK

The `adcp` SDK owns address validation and connection pinning. We import, we do
not reimplement:

| from `adcp` | what it owns |
|---|---|
| `signing.resolve_and_validate_host` | resolve once, classify the resolved address |
| `signing.SSRFValidationError` | the SDK's refusal, which we translate and never leak |
| `signing.IpPinnedTransport` / `AsyncIpPinnedTransport` | connecting to the address that was validated |
| `types.*`, `types.generated_poc.*` | the wire schema |
| `canonical_formats` | format identity |
| `webhook_receiver.verify_webhook_hmac` | the AdCP 3.x HMAC fallback verification |
| `types.AuthenticationScheme` | the ONE webhook auth vocabulary — see the reversal below |

**The single most important consequence:** because the SDK resolves once and
pins that IP into the transport, the address that was validated is the address
that gets connected. Any code that validates a hostname and then hands the
*hostname* to a client has reintroduced the DNS-rebinding TOCTOU, however
thorough its checks are. This is why "just add a check here" is not a smaller
version of the right fix — it is a different, broken shape.

### One SDK symbol is banned outright

`adcp.webhooks.get_adcp_signed_headers_for_webhook` is on the TID251 ban list.
It discards the body bytes it signs, so its own documented usage — sign, then
send `json=payload` separately — reintroduces the signed-bytes-vs-wire-bytes
divergence. Sign and send through the seam with the signed byte string instead.

That an SDK ships a footgun is not a contradiction of "the SDK owns this": it
owns address validation and pinning, which is not the same as every helper in
it being safe. Treat the SDK as authoritative where it is the mechanism, and as
a cross-check elsewhere.

## What is carried here only until upstream catches up

Two overloads, both marked in the source. Neither is a design position — each is
a dated workaround with a named retirement.

### 1. Five of the six supplement ranges

```python
# FIXME(adcontextprotocol/adcp-client-python#974): drop this whole
# frozenset (except the CGNAT entry above) once we adopt a release
# that carries these ranges upstream.
```

6to4 relay, AS112-v4, AMT, AS112 direct and ORCHIDv2 are held here only until
the SDK classifies them. **CGNAT `100.64.0.0/10` stays**, because AdCP 3.1.1
names it explicitly as a range a fetcher MUST reject.

Retirement: adopt the release, delete the five, keep CGNAT, and confirm the
oracle table in `tests/integration/test_outbound_http.py` still covers the
production set exactly — a completeness test grades that both ways, so removing
a range without removing its row fails, and adding one without a row fails too.

The bump has been deliberately deferred: it is a major version jump, and the
owner's call was that it is not worth the risk for this alone.

### 2. Operator agent dials do not use the SDK client

`creative_agent_registry` and `signals_agent_registry` dial through
`src/core/utils/operator_mcp.py::call_operator_mcp_tool` — a real MCP handshake
that is IP-pinned and redirect-refusing — rather than `adcp.ADCPMultiAgentClient`.

The reason is concrete rather than stylistic: adcp 6.6.0 exposes no transport
injection point, so the SDK client builds its own connection and the dial
reaches **none** of this application's egress policy. That was measured, not
assumed — a 302 to a metadata stand-in was followed.

Retirement: **adcp-client-python#1004**, which adds the injection point. The
citation is at `creative_agent_registry.py` and `signals_agent_registry.py`
where the choice is made, not only here.

## The validation split: two verdicts, one predicate

The seam is asked two different questions at two different times, so there are
two verdicts:

| | `check_registration` | `resolve_for_dial` |
|---|---|---|
| when | a URL is **stored** (webhook registration) | something is **about to dial** |
| DNS | none — never resolves | resolves once, pins the result |
| catches | a literal `10.0.0.1`, a bad scheme, a blocked hostname | what a name actually points at |
| cannot catch | what `evil.example.com` resolves to | nothing it was given a chance to see |
| `allow_private` | **no such parameter** | test-only hatch, and see below |

They read the **same** `_blocked_address` predicate, the same hostname
blocklist and the same scheme rule. That is the point: two independently
maintained copies of "what is a bad address" is the disease this module exists
to prevent, and the reason registration and dial cannot drift into disagreeing.

Registration is DNS-free **on purpose**, and this is a decision that has already
been made and reversed once, so it is worth stating why.

It runs when a buyer hands you a URL and there is no request to attach a refusal
to yet. A registration-time resolution was never binding: DNS moves between
registration and the first dial, so an unresolvable-but-public hostname must be
*accepted* now and re-checked when the callback is actually dialled. Resolving
at storage time is a side effect of storing data that proves nothing.

The admin route's registration-time resolution was removed for exactly this
reason — and the test that pinned it was **inverted rather than deleted**. It
now asserts the resolver is called **zero** times, so reinstating resolution has
to be a deliberate act with a failing test in front of it, not an innocent-looking
"we should validate earlier" change.

That technique generalises: when you remove a behaviour on purpose, invert its
test instead of deleting it. A deleted test leaves no trace of the decision; an
inverted one makes the reversal argue for itself.

### Stored rows are not re-validated

A related split, same reasoning about who is present to fix a problem: **ingest
validates, rehydration does not.** Reading a stored registration carries the
document through the library type with `model_construct`, nested models included.

At ingest a buyer is present to correct a rejection. A stored row has no buyer,
is delivering *today*, and the delivery path fails closed on its own. Routing
rehydration through the validating model stopped five measured shapes from
delivering — short credential, lowercase scheme, unrecognised scheme, short
token, empty `schemes` — every one of them writable by the untyped path that has
since been closed.

The one exception is principled: an HMAC registration with no secret still
refuses, because that row never delivered, and delivering it would mean sending
unsigned to a receiver obliged to reject unsigned.

### What no posture opens

`ADCP_OUTBOUND_ALLOW_PRIVATE=true` relaxes the SDK's flag classes so tests can
reach their own loopback origin or the compose bridge. It does **not** relax the
supplement set, which is checked unconditionally ahead of it. Those ranges are
carried here precisely because the SDK does not classify them, so they have no
second line of defence — a posture that skipped them would leave them undefended
rather than merely relaxed.

### Refusals say nothing

AdCP 3.1.1 `building/by-layer/L1/security.mdx` point 6: a fetcher MUST never
echo the refusal cause back to the party that supplied the URL. A per-cause
message at the buyer surface is a port-scanning oracle.

This is structural, not conventional: `AdCPBlockedUrlError.__init__` is
keyword-only and takes **no `message` parameter**, so a second spelling of the
refusal is unrepresentable. The cause is not lost — it goes to the operator's
log. **Do not assert on refusal message text in tests**; assert on the code, and
at most on the presence or value of structured details carried with the error.

## What is temporary

One thing in this package is an explicit overload pending upstream, and it is
marked in the source:

```python
# FIXME(adcontextprotocol/adcp-client-python#974): drop this whole
# frozenset (except the CGNAT entry above) once we adopt a release
# that carries these ranges upstream.
```

Five of the six `_SUPPLEMENT_NETWORKS` entries — 6to4 relay, AS112-v4, AMT,
AS112 direct, ORCHIDv2 — are held here only until the SDK classifies them.
**CGNAT `100.64.0.0/10` stays**, because AdCP 3.1.1 names it explicitly as a
range a fetcher MUST reject.

When that release is adopted: delete the five, keep CGNAT, and check the
oracle table in `tests/integration/test_outbound_http.py` still covers the
production set exactly — a completeness test grades that both ways, so removing
a range without removing its row fails, and vice versa.

## One vocabulary for webhook auth — a recorded reversal

The scheme a webhook is signed with comes from `adcp.types.AuthenticationScheme`
— a **spec vocabulary, not a local choice**. Its two members are what AdCP 3.1.1
defines, generated into the pinned `adcp==6.6.0` package rather than written
here. This repo does not get to add to it.

What #1802 decided was narrower and is the part worth recording: adopt that
vocabulary as the **only** one, exhaustively, and stop carrying seller-local
additions beside it.

| scheme | |
|---|---|
| `Bearer` | supported |
| `HMAC-SHA256` | supported |
| ~~`Basic`~~ | **dropped** — AdCP 3.1.1 does not define it |
| ~~`x-adcp-token`~~ | **dropped** — a seller-local invention that was never in the spec |

Case-sensitive, matched **exhaustively** at the sender with `match`/`case`. That
is the mechanism that keeps the vocabularies aligned: when the spec adds a member
and the pin moves, the sender stops type-checking until someone handles it —
rather than silently falling through to a default and sending nothing. A
seller-local `webhook_authentication` module with its own `Authentication` and
`PushNotificationConfig` subclasses existed and was **deleted**.

What happens to rows that used the dropped schemes is deliberate and worth being
explicit about, because it is a delivery-affecting outcome:

- Rows that **meant** a supported scheme and merely spelled it differently
  (`bearer`, `hmac_sha256`) were migrated case-insensitively onto the pinned
  spelling, and keep delivering.
- Rows naming a scheme AdCP 3.1.1 does not define — `Basic`, `x-adcp-token` —
  **stop delivering** and are refused as `scheme_not_in_spec` until their
  operator re-registers. That is the intended outcome, not collateral: a row
  that cannot be signed correctly must not be signed incorrectly.

This is written down because it reverses an earlier decision *within the same
epic*, and the reversed reasoning is the more tempting one. The tolerant reading
— A2A stores a free-form protobuf scheme, so lowercase rows genuinely exist, so
accept them — is self-perpetuating: rows always exist. It bought one extra
enum member plus one case fold, and produced three spellings of one fact across
three senders that then disagreed about what the column held.

Non-conforming rows were **migrated**. Anything still non-conforming stops
delivering and is refused as `scheme_not_in_spec` — a row that cannot be signed
correctly must not be signed incorrectly.

Three sub-rules came out of it, and the third is a trap worth knowing:

- **Decide on the enum member, never on its text.** `mypy.ini` sets
  `strict_equality`, and a guard catches what mypy structurally cannot — StrEnum
  comparisons are legal, because the members *are* strings.
- **A migration writes values read from the enum, not literals.** Hand-typing is
  how `hmac_sha256` — which nothing in `src/` compares against — became a
  persisted value.
- **Never add an import-time assertion restating enum values.** It puts one fact
  in two places, which is the defect being removed, and it is actively
  dangerous: alembic imports every module under `versions/`, so an import-scope
  `assert` fails `alembic heads` and `alembic upgrade` on any member rename.
  That bricks the migration system to guard a rename that has not happened.

## Deciding where a new concern belongs

Ask in this order:

1. **Does the SDK already own it?** Address classification, resolution, pinning
   and signing do. Import it. If the SDK is wrong, fix it upstream — a local
   copy is how the two got out of step in the first place.
2. **Is it a policy the seam should decide once?** Then it belongs in
   `egress/`, in the module that owns that decision, expressed as a value rather
   than an effect where possible (`attempts.py` is the model: no I/O, fully
   steppable).
3. **Is it a call-site concern?** Then it is probably not a policy — pass it in.
   If you are about to write address logic at a call site, that is the shape
   this package exists to remove.

## Related

- [security/outbound-egress.md](../security/outbound-egress.md) — the rule, and the three enforcement layers
- `CLAUDE.md` Pattern #9 — the same, for agents
- GH #1589 — the consolidation
- GH #1802 — the round that closed the seam's own bypasses

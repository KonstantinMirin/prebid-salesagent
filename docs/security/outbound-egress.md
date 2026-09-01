# Outbound egress: one seam, and why nothing else validates a URL

Outbound HTTP goes through one module, `src/core/security/outbound_http.py`, via
`send` (sync) or `asend` (async). Anything you write goes through the seam.

There are exactly **three sanctioned dialers that do not**, and they are listed
in the seam's own module docstring rather than only here. Read that list before
"fixing" an apparent bypass — one of them is deliberately *stronger* than the
seam, and routing it through us would weaken it. See
[Sanctioned dialers](#sanctioned-dialers-and-why-they-are-not-bypasses) below.

The rest of this document explains what the seam decides on your behalf, why
adding your own check is a defect rather than an improvement, and how the
codebase makes the alternatives hard to write.

## The rule

```python
from src.core.security.outbound_http import asend

result = await asend(url, json=payload)
```

Do not add URL validation, private-IP checks, metadata blocklists,
resolve-then-check, or redirect re-validation at the call site. If you find
yourself importing `ipaddress`, reaching for `socket.gethostbyname`, or writing a
hostname blocklist anywhere under `src/`, stop — that logic already exists and
yours will disagree with it.

## Why a seam rather than a helper everyone calls

An outbound request has at least four policy decisions attached to it:

| decision | who owns it |
|---|---|
| Is this address allowed? | `adcp.signing` — validates and **pins** the resolved IP |
| What TLS? | the seam, one configuration |
| Follow redirects? | **No.** httpx's `follow_redirects=False`, never overridden |
| Retry, and how long? | the seam — BR-RULE-029 backoff, bounded `Retry-After` |

Spread those across call sites and each site gets three of four right. The
failure is never "nobody thought about SSRF" — it is that *this* call site
forgot redirects while *that* one forgot the retry bound. Consolidating them is
what GH #1589 was, and the recurrence it fixed.

The address decision is the sharpest example. Checking an address and then
connecting is a TOCTOU: DNS can answer differently the second time, which is
DNS rebinding. `adcp.signing.resolve_and_validate_host` resolves **once** and
pins that IP into the transport, so the address that was validated is the
address that gets connected. A call site that validates and then hands the
hostname to its own client has re-opened the hole no matter how good its
blocklist is.

## What the seam refuses, and what it never refuses

Two verdicts, deliberately kept identical in what they consider:

- **`check_registration`** — DNS-free. Grades a URL a buyer supplied, before it
  is stored. Never resolves, so it can refuse a literal `10.0.0.1` but cannot
  know what `evil.example.com` points at.
- **`resolve_for_dial`** — DNS-full. Resolves once, pins, and refuses on the
  resolved address.

Both consult the same address predicate, so "registration said yes, dial said
no" cannot drift into a surprise.

### The supplement ranges, and the one thing no posture opens

`adcp.signing` classifies the usual reserved space (private, loopback,
link-local, multicast, reserved, unspecified). Six ranges it does **not**
classify are carried here, in `_SUPPLEMENT_NETWORKS`:

| range | what |
|---|---|
| `100.64.0.0/10` | CGNAT (RFC 6598) |
| `192.88.99.0/24` | 6to4 relay anycast (RFC 7526) |
| `192.31.196.0/24` | AS112-v4 (RFC 7535) |
| `192.52.193.0/24` | AMT (RFC 7450) |
| `192.175.48.0/24` | AS112 direct (RFC 7534) |
| `2001:20::/28` | ORCHIDv2 (RFC 7343) |

`ADCP_OUTBOUND_ALLOW_PRIVATE=true` is a **test-only** hatch that relaxes the
SDK's flag classes, so an in-process suite can dial its own loopback origin and
the e2e stack can dial its compose bridge. It does **not** open the supplement
set: that check runs unconditionally, ahead of the hatch. The reason is that
those six have no second line of defence — they are carried here precisely
because the SDK does not know them, so a posture that skipped them would leave
them undefended rather than merely relaxed.

## Sanctioned dialers, and why they are not bypasses

Three classes of outbound call deliberately sit outside `send`/`asend`. The
taxonomy lives in the seam's module docstring, with a one-line pointer at each
call site — deliberately, so a reader can tell a sanctioned dialer from an
unnoticed bypass without archaeology through a PR description.

**1. `adcp.adagents.fetch_adagents`** — dials a tenant-admin-configured
`publisher_domain`. It self-pins: builds an `AsyncIpPinnedTransport` on the
validated IP with `trust_env=False`, and mints a **fresh pinned client per
redirect hop**. That is *stronger* than this seam for a multi-host redirect
chain — our client resolves once and pins once, which across `fetch_adagents`'
own hops would collapse into a TOCTOU pre-check. **Do not "fix" this one.**

**2. authlib** (OIDC discovery and token exchange, `requests`-backed). Not
expressible as a TID251 ban, and it dereferences `server_metadata_url=` itself,
outside any seam. It is handled where it can be: the `discovery_url` and
`logout_url` are validated at **ingest**, so the URL authlib later dereferences
has already passed the registration gate.

**3. Fixed-destination vendor SDKs** — no attacker-controlled URL ever reaches
them, so there is no SSRF surface to guard.

If you are adding a fourth, it belongs in that docstring with its reason before
it belongs in the code. An unlisted dialer is indistinguishable from a mistake.

## How the codebase stops you writing the wrong thing

Three layers, in descending order of strength. Prefer the strongest available.

### 1. Unrepresentable — the name does not exist

The seam imports what it wraps, and binds it **privately**:

```python
import httpx as _httpx          # not `import httpx`
```

A plain import would publish `outbound_http.httpx`, and
`from src.core.security.outbound_http import httpx` would then resolve to the
real module straight past every gate. The underscore makes that an
`ImportError`. Four paths are closed this way:

```
src.core.security.outbound_http.httpx
src.core.security.egress.policy.ipaddress
src.core.utils.mcp_client.Client
src.core.utils.mcp_client.StreamableHttpTransport
```

Nothing bans these, because there is nothing to ban. No config row, no test, no
table to keep in sync — and the failure arrives at import rather than at lint.

**If you are adding a seam that wraps a dangerous dependency, bind it privately.**
That is the pattern.

### 2. Banned — a lint rule, because the name is not ours

You cannot make `import httpx` impossible in an arbitrary file from inside this
repo, so `ruff-egress.toml` bans the modules outright: `httpx`, `requests`,
`aiohttp`, `urllib.request`, `httpcore`, `urllib3`, `http.client`, plus `httpx2`
and `httpcore2` (installed transitively, and one character from the real thing).

The same table bans `fastmcp.Client` and the MCP transports. `Client(url)`
infers an un-pinned transport from a bare URL, and fastmcp is a third-party API
we cannot rebind — so a ban list is the only mechanism available for that half.

### 3. Exempted — one file, reviewed

The gate runs with `--ignore-noqa`:

```
uv run ruff check --config ruff-egress.toml --ignore-noqa --no-respect-gitignore src/ scripts/
```

That makes `# noqa` **inert** for this config, in every spelling — `# noqa: TID251`,
file-scope `# ruff: noqa`, bare `# noqa`, `# flake8: noqa`. A file cannot exempt
itself. The only way to be exempt is a row in `[lint.per-file-ignores]`, which
lands in a diff someone reviews.

Rows come in three kinds, and the difference matters:

- **the seam importers** (`outbound_http.py`, `egress/policy.py`,
  `mcp_client.py`) — a *floor*. A seam architecture must have sanctioned
  importers of what it wraps; this set never empties.
- **`scripts/` rows** — *debt*. Retire them; do not add to them.
- **pre-ban `Any`** (ANN401) — *debt*. Shrinks as those signatures get typed.

The trade, stated plainly: these rows are **file**-granular where a `# noqa` was
line-granular. That precision bought the deletion of ~150 lines of machinery
whose whole job was auditing whether every scattered marker was recorded and
still live. Once self-exemption is impossible rather than merely detectable, the
audit has nothing to do.

`--no-respect-gitignore` is also load-bearing rather than decoration: ruff's
directory walk honours `.gitignore`, which once hid a git-tracked file under
`scripts/` from the scan entirely.

## What is still tested, and why

`tests/unit/test_ruff_egress_bans.py` is deliberately small. It keeps two claims:

- **every ban fires**, on every resolving import spelling. Ruff does not
  validate `banned-api` keys, so a typo'd row like `"httpx3"` is silently inert
  forever. Only a test catches that.
- **a clean snippet passes**, and the config parses — so a broken
  `ruff-egress.toml` fails loudly instead of passing vacuously on empty output.

Everything else it used to assert was auditing exemptions, and went when
exemptions stopped being writable in code.

## Adding a new outbound call

1. Call `send` / `asend`. You are done.
2. If you think you need a raw client, you are adding a second policy owner —
   say why in review before writing it.
3. If you are wrapping a new dangerous dependency in a seam of your own, bind
   its import privately so your seam cannot re-export it.
4. Never add a `# noqa` for the egress rules. It does nothing.

## Related

- [../design/egress-sdk-boundary.md](../design/egress-sdk-boundary.md) — the module map,
  what the `adcp` SDK owns, the two-verdict split, and what is carried here only
  until an upstream release
- `docs/security.md` — authentication, tenancy, audit
- `CLAUDE.md` Pattern #9 — the same rule, stated for agents
- GH #1589 — the consolidation this replaced
- GH #1802 — the round that made the bypasses unrepresentable

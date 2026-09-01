# Outbound egress: one seam, and why nothing else validates a URL

Outbound HTTP goes through one module, `src/core/security/outbound_http.py`, via
`send` (sync) or `asend` (async). Anything you write goes through the seam.

Exactly **three classes of sanctioned dialers do not**, and they are listed
in the seam's own module docstring rather than only here. Read that list before
"fixing" an apparent bypass — one of them is deliberately *stronger* than the
seam, and routing it through the seam weakens it. See
[Sanctioned dialers](#sanctioned-dialers-and-why-they-are-not-bypasses).

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

| Decision | Who owns it |
|---|---|
| Is this address allowed? | `adcp.signing` — validates and **pins** the resolved IP — plus the seam's own supplement set |
| What TLS? | The seam, one configuration |
| Follow redirects? | **No.** httpx's `follow_redirects=False`, never overridden |
| Retry, and how long? | The seam — BR-RULE-029 backoff, bounded `Retry-After` |

Spread those across call sites and each site gets three of four right. The
failure is never "nobody thought about SSRF" — it is that *this* call site
forgot redirects while *that* one forgot the retry bound. The seam holds all
four decisions in one place.

The address decision is the sharpest example. Checking an address and then
connecting is a TOCTOU (time-of-check to time-of-use) hole: DNS can answer
differently the second time, which is DNS rebinding. `adcp.signing.resolve_and_validate_host` resolves **once** and
pins that IP into the transport, so the address that was validated is the
address that gets connected. A call site that validates and then hands the
hostname to its own client has re-opened the hole no matter how good its
blocklist is.

## What the seam refuses, and what it never refuses

The seam answers two questions, through two verdicts deliberately kept
identical in what they consider:

- **`check_registration`** — DNS-free. Grades a URL a buyer supplied, before it
  is stored. Never resolves, so it can refuse a literal `10.0.0.1` but cannot
  know what `evil.example.com` points at.
- **`resolve_for_dial`** — DNS-full. Resolves once, pins, and refuses on the
  resolved address.

Both consult the same address predicate, so the two verdicts cannot drift
apart on what counts as a bad address. A dial can still refuse what
registration accepted — that is DNS answering, not drift.

### Validate a stored URL at ingest: `validate_url`

`validate_url(url, *, provenance=None)` applies the seam's full dial-time
policy to a URL **without sending anything**
(`src/core/security/outbound_http.py`). Use it when a URL is stored at ingest
and fetched later by a background worker: at fetch time no request exists to
carry a refusal, so without ingest validation the caller gets a success
followed by a silent delivery failure. The alternative call sites reach for
otherwise — a hand-written pre-flight at the eventual dial site — is a second
copy of address policy, which is exactly the duplication this module exists to prevent.

It refuses exactly what `send` and `asend` refuse, because all three go
through `EgressPolicy.resolve_for_dial` and differ only in what they do with
the resolved address. Here it is **discarded**: no transport is built, no
socket is opened, and a later fetch must resolve again through its own `send`
call — a resolution cached across the ingest-to-fetch gap is precisely the
DNS-rebinding window that resolve-once-then-pin closes within a single
request. Handing the resolved address back also leaks it into whatever logs
the result, which is the same disclosure concern as the opaque refusal
message.

Two live consumers: the admin ingest funnel (`src/admin/utils/url_policy.py`,
two helpers over one refusal decision) and the MCP seam, which validates the
agent URL before the handshake. Admin handlers omit `provenance` — they build no AdCP envelope, so
there is no request path to name.

One deliberate non-consumer: buyer-supplied webhook URLs at protocol ingest go
through the DNS-free `check_registration` funnel instead, **not**
`validate_url` — it always resolves, so at registration it refuses a buyer
whose hostname has not yet propagated, and answers the same input differently
across surfaces. Operator-entered URLs get `validate_url` because the operator
is present and a wrong hostname should fail loudly at once; buyer-supplied
URLs get the DNS-free verdict now and the full one at dial.

### The supplement ranges, and the one thing no posture opens

`adcp.signing` classifies the usual reserved space (private, loopback,
link-local, multicast, reserved, unspecified). Six ranges it does **not**
classify are carried here, in `_SUPPLEMENT_NETWORKS`:

| Range | What it is |
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
because the SDK does not know them, so a posture that skips them leaves them
undefended rather than merely relaxed.

## Grade egress in-network: the TLS front

The seam requires `https` unconditionally — no scheme hatch exists, so no
flag lets a test dial `http://`. The in-network stack therefore serves its
origins over real TLS through a shared front, rather than relaxing the seam.

`docker-compose.e2e.yml` runs one shared TLS terminator, the `tls-proxy`
service, fronting every `*.adcp.test` origin the stack dials outbound —
`proxy.adcp.test`, `creative-agent.adcp.test`, and `webhooks.adcp.test`, as
network aliases on that one service. `scripts/dev/gen_test_tls.py` generates
the private CA and the leaf certificates.

The CA bundle is **combined, and that is load-bearing**. `SSL_CERT_FILE`
replaces the process's entire default cafile, so a private-CA-only bundle
breaks every real HTTPS dial the same process makes (`uv sync` against
pypi.org included). `gen_test_tls.py` produces `COMBINED_CERT`: the system
bundle (or `certifi`'s, on a developer laptop) plus the private CA, one file
serving both trust anchors. The `--cacert`-style flags and
`E2E_CA_BUNDLE` use the private CA alone on purpose — a caller checking one of
the stack's own fronts should trust only this stack's leaf, not the whole
public web.

### The hatch is scoped, and the scoping is the mechanism

Every compose origin resolves to a bridge address, so the stack sets
`ADCP_OUTBOUND_ALLOW_PRIVATE: "true"` — in exactly two places, both in
`docker-compose.e2e.yml`. The developer stack, `docker-compose.yml`, names it
zero times: opening it there turns off egress policy for every developer, and
nothing in the test path reads that file. `tox.ini` lists the variable under
`pass_env`, not `setenv` — `setenv` forces the hatch open for every tox env,
including the in-process suites that must see it closed.

One guard (`tests/unit/test_architecture_no_outbound_insecure_hatch.py`)
covers both hatches, asymmetrically and deliberately:
`ADCP_OUTBOUND_ALLOW_INSECURE` has no legitimate use, so the guard keeps it
out of the tree entirely; `ADCP_OUTBOUND_ALLOW_PRIVATE` has legitimate uses,
so the guard instead pins **which files may name it** — by set identity, so
adding one surface while dropping another fails. Anyone adding an env surface
that names the hatch — a compose file, a Dockerfile `ENV`, a CI matrix group —
adds a pin entry with a reason, or the build fails.

### What is gradeable where

Two immunities survive the open hatch, so most refusals stay gradeable live:

| Refusal | In-network? | Why |
|---|---|---|
| Cloud metadata (`169.254.169.254`) | Yes | The SDK checks its metadata set before it reads `allow_private` |
| The six supplement ranges | Yes | This repo's predicate runs unconditionally, ahead of the hatch |
| Non-`https` scheme | Yes | No scheme hatch exists; the TLS front provides a real `https` origin to refuse against |
| General private-range | No — in-process only | Every compose origin is a bridge address, so the hatch stays open there; `set_flags()` in `tests/integration/test_outbound_http.py` closes it per case |

When a new egress case "cannot be tested in-network", the knob is one of
these: give the origin a real `https` front behind `tls-proxy` (an alias and a
leaf), or accept that the case grades a refusal the open hatch masks, and
write it in-process.

The stack's service inventory, tox envs, port publishing, and how to run the
suites live in [End-to-end testing](../development/e2e-testing.md).

## Sanctioned dialers, and why they are not bypasses

Three classes of outbound call deliberately sit outside `send`/`asend`. The
taxonomy lives in the seam's module docstring, with a one-line pointer at each
call site — deliberately, so a reader can tell a sanctioned dialer from an
unnoticed bypass.

**1. `adcp.adagents.fetch_adagents`** — dials a tenant-admin-configured
`publisher_domain`. It self-pins: builds an `AsyncIpPinnedTransport` on the
validated IP with `trust_env=False`, and mints a **fresh pinned client per
redirect hop**. That is *stronger* than this seam for a multi-host redirect
chain — this seam's client resolves once and pins once, which across
`fetch_adagents`' own hops collapses into a TOCTOU pre-check.
**Do not "fix" this one.**

**2. authlib** (OIDC discovery and token exchange, `requests`-backed). Not
expressible as a TID251 ban, and it dereferences `server_metadata_url=` itself,
outside any seam. It is handled where it can be: the `discovery_url` and
`logout_url` are validated at **ingest** (`src/admin/blueprints/oidc.py`), so
the URL authlib later dereferences has already passed the registration gate.
The second-order `token_endpoint`/`jwks_uri` read out of the discovery
document is a known open item, tracked by GH #1872.

**3. Fixed-destination vendor SDKs** — no attacker-controlled URL ever reaches
them, so there is no SSRF surface to guard.

If you are adding a fourth, it belongs in that docstring with its reason before
it belongs in the code. An unlisted dialer is indistinguishable from a mistake.

## How the codebase stops you writing the wrong thing

The codebase stops the wrong call at three layers, in descending order of
strength. Prefer the strongest available.

### Unrepresentable — the name does not exist

The seam imports what it wraps, and binds it **privately**:

```python
import httpx as _httpx          # not `import httpx`
```

A plain import publishes `outbound_http.httpx`, and
`from src.core.security.outbound_http import httpx` then resolves to the
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

### Banned — a lint rule, because the name is third-party

You cannot make `import httpx` impossible in an arbitrary file from inside this
repo, so `ruff-egress.toml` bans the modules outright: `httpx`, `requests`,
`aiohttp`, `urllib.request`, `httpcore`, `urllib3`, `http.client`, plus `httpx2`
and `httpcore2` (installed transitively, and one character from the real thing).

The same table bans `fastmcp.Client` and the MCP transports. `Client(url)`
infers an un-pinned transport from a bare URL, and fastmcp is a third-party
API this repo cannot rebind — so a ban list is the only mechanism available
for that half. The un-pinnable `adcp` clients, the SDK's signed-headers
footgun, `ipaddress`, and `socket.gethostbyname` are banned in the same table,
each row carrying its reason.

### Exempted — one file, reviewed

The gate runs with `--ignore-noqa`:

```
uv run ruff check --config ruff-egress.toml --ignore-noqa --no-respect-gitignore src/ scripts/
```

That makes `# noqa` **inert** for this config, in every spelling — `# noqa: TID251`,
file-scope `# ruff: noqa`, bare `# noqa`, `# flake8: noqa`. A file cannot exempt
itself. The only way to be exempt is a row in `[lint.per-file-ignores]`, which
lands in a diff someone reviews.

Rows come in three kinds, and the difference matters:

- **The seam importers** (`outbound_http.py`, `egress/policy.py`,
  `mcp_client.py`) — a *floor*. A seam architecture must have sanctioned
  importers of what it wraps; this set never empties.
- **`scripts/` rows** — *debt*. Retire them; do not add to them.
- **Pre-ban `Any`** (ANN401) — *debt*. Shrinks as those signatures get typed.

These rows are **file**-granular. Because self-exemption is impossible rather
than merely detectable, no machinery is needed to audit whether scattered
markers are recorded and still live.

`--no-respect-gitignore` is also load-bearing rather than decoration: ruff's
directory walk honours `.gitignore`, which can hide a git-tracked file from
the scan entirely.

## What the ban test keeps true

`tests/unit/test_ruff_egress_bans.py` is deliberately small. It keeps two claims:

- **Every ban fires**, on every resolving import spelling, and under
  `scripts/` as well as `src/`. Ruff does not validate `banned-api` keys, so a
  typo'd row like `"httpx3"` is silently inert forever. Only a test catches
  that.
- **A clean snippet passes**, and the config parses — so a broken
  `ruff-egress.toml` fails loudly instead of passing vacuously on empty output.


## Add a new outbound call

1. Call `send` / `asend`. You are done.
2. If you think you need a raw client, you are adding a second policy owner —
   say why in review before writing it.
3. If you are wrapping a new dangerous dependency in a seam of your own, bind
   its import privately so your seam cannot re-export it.
4. Never add a `# noqa` for the egress rules. It does nothing.

## Related

- [The egress seam and the SDK boundary](../design/egress-sdk-boundary.md) — the module map,
  what the `adcp` SDK owns, the two-verdict split, and what is carried here only
  until an upstream release
- [Security overview](../security.md) — authentication, tenancy, audit
- `CLAUDE.md` Pattern #9 — the same rule, stated for agents

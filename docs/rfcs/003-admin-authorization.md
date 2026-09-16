# RFC 003: The admin plane's own track under the AuthZ design

**Status:** Request for comment
**Parent:** [#2232, "RFC: AuthZ design"](https://github.com/prebid/salesagent/issues/2232). This
document is subordinate to it and proposes no parallel architecture. It adopts four things from
#2232 by reference. The component decomposition of §5.1 — policy enforcement point (PEP), policy
decision point (PDP), policy information point (PIP), and policy administration point (PAP),
after NIST SP 800-162 and XACML. The `Decision` vocabulary of §5.2. The two decision points of
§5.3. And the reason-to-wire mapping of §5.4.
**Scope:** `src/admin/`, plus the route handlers registered onto the admin app from
`src/adapters/` and `src/services/`. Not the buyer plane.
**Decision proposed:** Consolidate the admin plane's ten authorization mechanisms onto the one
PEP seat #2232 already names for it, its decorators. Make that seat unforgettable with the
`url_map` guard #2203 already specifies. Remove the `ruff-ownership.toml:51` exemption that let
the sprawl accumulate. Adopt #2232's `Decision` type at that seat rather than inventing a second
vocabulary.

## Summary

#2232 §6 is this document's charter:

> The admin plane otherwise proceeds on its own track. Issues #2203, #2204, #2205, and #2206
> track admin-side authorization and credential-binding fixes, and PR #2075 adds missing
> authentication decorators. None of them wait on this RFC. What this RFC asks of the admin
> plane is that its decisions reach the same `Decision` type with the same reason vocabulary, so
> audit records and error classification have one implementation across both planes while the
> planes keep separate trust roots.

That track has five issues and one open PR. What it does not have is an inventory of the seat
those fixes land on, and a reason the seat drifted. This document supplies both, and nothing else:
the design is #2232's.

The seat is not one decorator. There are **ten** distinct places an admin authorization outcome
is decided, and only two are decorators. #2232's PEP row lists "the admin plane's decorators" as
one seat, which understates it by eight.

The reason the sprawl accumulated is one line of configuration. `ruff-ownership.toml:51` exempts
`src/admin/**` from the import bans that hold the buyer plane's ownership boundaries in place.
CLAUDE.md § Structural guards requires that allowlists only shrink and that every entry carry a
`# FIXME(#<issue>)` at the source location. A glob has no source locations to annotate and no
count to shrink. Ten mechanisms accumulated with nothing going red.

Two findings in this document are genuinely new and neither is a design question. Four live,
unauthenticated, tenant-parameterized routes are registered onto the admin app from
`src/services/gam_inventory_service.py`. They sit outside `src/admin/` entirely, which is why no
admin-scoped review has named them. The second is that the admin OIDC path accepts an identity
from an unsigned `id_token`. That is the concrete instance of #2232 §6's first identity-integrity
item. §6 states that item at the level of mechanism, and it is the only bullet there with no
issue number.

## Part 1: The measured asymmetry

|                                    | buyer plane                           | admin plane                                                          |
|------------------------------------|---------------------------------------|----------------------------------------------------------------------|
| authorization seams                | 1                                     | 10                                                                   |
| tenant scoping                     | in the type                           | `@require_tenant_access` × 148 across 20 files                       |
| handlers with no authorization     | 0 (structurally impossible)           | 37 of 221 under `src/admin/`; 33 of 179 tenant-scoped URL rules (#2203) |
| business rules                     | in the repository / service           | in the blueprint                                                     |
| enforcement                        | ruff + ast-grep guards                | `ruff-ownership.toml:51` blanket-exempts `src/admin/**`              |
| what grades it                     | 2628 scenarios × 5 transports         | 13 scenarios × 1 transport, over 1 of 27 blueprints (#2235)          |

### How the buyer plane gets to one

This is the shape #2232 §3 calls derivation, and §5.3 calls construction. `serve(tool_name,
payload, headers, protocol)` is the whole transport surface (`src/core/tools/_boundary.py:237`).
Its docstring states the property: "IT TAKES HEADERS, NOT AN IDENTITY. Nothing here reads them:
the resolver is their one reader" (`:265`). `_resolve_identity` is imported inside `serve`
(`:270`) and called once (`:317`). It returns one of three types: `PublicIdentity`
(`src/core/resolved_identity.py:44`), `ResolvedIdentity` (`:105`), or `AccountIdentity` (`:140`).
Their `principal_id` (`:129`) and `tenant_id` (`:133`) are properties over non-optional fields.
The implementation is called `(req, identity)` and nothing else (`:337`).

Absence is a type error rather than silence.
`.ast-grep/rules/impl-signature-is-request-and-identity.yml` refuses any other signature, and
`ToolSpec.requires_credential` is derived from the annotation. So there is no `auth=` literal to
forget. The identity has one constructor
(`.ast-grep/rules/resolved-identity-constructed-only-by-its-owners.yml`).

The admin plane has none of those three properties. #2232 §5.3 explains why a seat without them
cannot acquire them by discipline. "The implementation remembers to check" is the failure mode in
every issue in its §1.

### The ten mechanisms

| # | Mechanism | Where | Owner |
|---|---|---|---|
| 1 | `@require_auth(admin_only=)` | `src/admin/utils/helpers.py:265`, 25 applications | — |
| 2 | `@require_tenant_access(api_mode=)` | `helpers.py:304`, 148 applications across 20 files, ending in a `select(User)` at `:363` | — |
| 3 | `require_api_key_auth(...)` factory | `src/admin/auth_helpers.py:94`, instantiated twice (`sync_api.py:35`, `tenant_management_api.py:34`) | — |
| 4 | A private third `require_auth` + a private `get_tenant_access` | `src/adapters/gam_reporting_api.py:60`, `:89`, guarding six routes | **#2204** |
| 5 | `is_super_admin(email)` reading a session cache it wrote itself | `helpers.py:151`, read `:164`, written `:217`–`:220` | — |
| 6 | Inline `session.get("role")` in route bodies | 20 sites under `src/admin/` | **#2203 Notes** (asks for its own issue; not yet filed) |
| 7 | Inline `"user" not in session` in undecorated routes | 7 sites, e.g. `src/admin/blueprints/public.py:106` | — |
| 8 | Template gates on `session.role` | `templates/base.html:155`, `:165`–`:179` | **#2206** (the predicate behind them) |
| 9 | A composed-path test-session bypass inside both decorators | `helpers.py:272`, `:320` | **#2235** (its test-side consequence) |
| 10 | Nothing at all | 37 of 221 route handlers under `src/admin/` | **#2203** AC 6 (the guard) |

Mechanism 5 self-perpetuates: `is_super_admin` reads `session["is_super_admin"]` against
`session["admin_email"]` (`helpers.py:164`), both written by `_cache_admin_status`
(`:217`–`:220`). The grant is a domain match — on `super_admin_domain_list` from settings
(`:178`–`:182`), falling back to a `TenantManagementConfig` row (`:197`–`:205`).

Mechanism 9 is narrower than it looks in production and wider than it looks in tests.
`test_login_composed()` (`helpers.py:41`–`:47`) asks whether `create_app` registered the
test-login blueprint, and `src/admin/app.py:350` registers it only when
`settings.testing.adcp_auth_test_mode and not is_production`. The bypass does not exist in
production. It exists in every admin test, because the canonical `admin_client` fixture sets
`ADCP_AUTH_TEST_MODE=true` (`tests/admin/conftest.py:26`). An undecorated handler and a decorated
one are therefore indistinguishable to the suite. #2203's traps name the same hazard from the
test-authoring side: "Do not enable `ADCP_AUTH_TEST_MODE` or forge a super-admin session in a
test meant to prove authorization works."

Mechanism 8 gates on values the schema cannot hold. `User.role` carries
`CheckConstraint("role IN ('admin', 'manager', 'viewer')")`
(`src/core/database/models.py:742`). `templates/base.html` gates on `super_admin` and
`tenant_admin`, which that constraint forbids. #2203's Notes establish that no production login
path assigns them. `session["role"]` is written at exactly three sites: `auth.py` super-admin
login, `auth.py` test login, and `public.py:279` (`"admin"`). So mechanisms 6 and 8 are largely
dead branches that read as coverage. #2206 is the same disease one level down. `helpers.py:249`
filters on `is_admin=True`, a column `User` does not have, and the resulting
`InvalidRequestError` is swallowed into an unconditional `False`.

### Reconciling the three counts

Three different numbers describe "handlers with no authorization", and they are not in conflict.
Stating the denominators keeps them from being quoted against each other:

| Count | Question | Method |
|---|---|---|
| **33 of 179** (#2203) | Which tenant-scoped URL *rules* do not reach `require_tenant_access`? | Walking the live `app.url_map` |
| **37 of 221** | Which route *handlers* under `src/admin/` carry no authorization decorator at all? | AST walk of `@*_bp.route` decorators |
| **46 of 96** | Which handlers whose own `route()` decorator spells `<tenant_id>` do not reach `require_tenant_access`? | AST walk over all of `src/` |

**#2203's is the authoritative one, and its method is why.** A decorator-source scan cannot see a
`<tenant_id>` supplied by a blueprint's `url_prefix`. `policy.rules`
(`src/admin/blueprints/policy.py:209`–`:211`) is one of #2203's four named routes, and it does not
appear in the 46 because its route string is `/rules`. Only the live `url_map` sees the composed
path. The two AST counts are useful for distribution, not for ratcheting. That is the right
division, since #2203 AC 6 specifies the guard as a `url_map` walk.

The 37 also needs its intent split stated, because the count is not the finding:

| Blueprint | Count | Reading |
|---|---|---|
| `auth.py` | 9 | Login and OAuth flow endpoints, public by construction — except `gam_authorize` (`:762`), which is **#2205** |
| `core.py` | 7 | `index`, `admin_index`, `send_static`, plus `health` (`:367`), `health_config` (`:379`), `metrics` (`:412`), `debug_headers` (`:330`) — four unauthenticated information surfaces that want their own read |
| `public.py` | 5 | Signup flow, self-checking inline (`:102`, `:106`) |
| `publisher_partners.py` | 5 | **PR #2075**, in review |
| `schemas.py` | 5 | Static schema serving, public by design |
| `oidc.py` | 3 | `callback` (`:221`) and `login` (`:408`) are flow endpoints; `test_initiate` (`:178`) is new (Part 3) |
| `test_auth.py` | 2 | Composed only under `adcp_auth_test_mode and not is_production` (`app.py:350`) |
| `api.py` | 1 | `api_health` |

Six of the 37 are defects and thirty-one are intentional, and **nothing in the tree distinguishes
them**. That is the argument for #2203 AC 6's exempt set. The split has to be written down
somewhere a build can read, and today it exists only in tables like this one.

**#2203's four named routes are not among the 37.** They carry `@require_auth()`, so a scan
asking "is there an authorization decorator" passes them. #2203 asks the sharper question, "does
it prove membership", and they fail it. The two sets are disjoint, and #2203's 33 contains all
six of the 37's defects. Three more routes share #2203's exact shape and are not in its four:
`src/admin/blueprints/inventory.py:344`, `:516`, `:558` — `@require_auth()` plus `<tenant_id>`,
no membership proof. `inventory.py:558` appears in #2203's Notes for its dead inline role check.
The missing membership proof is a separate gap at the same site.

## Part 2: Why the seat drifted

`ruff-ownership.toml:51` is:

```toml
"src/admin/**" = ["TID251"]
```

The comment above it explains the intent, and that intent is legitimate: the admin UI handles
principals and accounts "as DATA rather than act as a caller". The consequence is not legitimate.
It is a glob, so it also exempts every future file under `src/admin/` from every current and
future TID251 ban in that config. The same comment says the four single files outside `src/admin`
and `scripts` are "listed by name so nothing else in `src/` inherits the exemption". The admin app
is the one surface where that discipline was not applied.

This is the local instance of #2232's own diagnosis. Its §3 states the principle: "a graded
surface is a function of one declaration, never authored at the site that uses it". Its §11
rejects the alternative this exemption created: "Fix the issues individually. This is the current
approach. Each fix is correct, and none of them prevents the next instance." Five independently
found admin authorization bugs (#2203–#2206, PR #2075) sit at a surface exempted from the guards.
That is the recurrence rate with a mechanical explanation.

## Part 3: Findings and their owners

Every finding, with the GitHub issue that owns it or a statement that it is new. Verified on
`feature/spec-gaps-1210`, which runs 1–2 lines ahead of `main @ fd90b69a8`. That offset explains
every line-number difference from #2203–#2206.

| Finding | Owner | Status |
|---|---|---|
| `publisher_partners.py` five routes unauthenticated (`:31`, `:91`, `:182`, `:203`, `:510`), registered under `/tenant` (`app.py:372`) | **PR #2075** | In review. Not new work |
| Four tenant-scoped routes with `require_auth()` and no tenant check | **#2203** | PR #2231 open, closes it |
| The 33 unguarded tenant-scoped rules, and the `url_map` guard | **#2203** AC 6 | Specified, unlanded |
| Dead inline `session.get("role")` branches | **#2203 Notes** | Notes asks for its own issue; **not filed** |
| `gam_reporting_api` third `require_auth`, OIDC 500s, super-admins unscoped | **#2204** | Open |
| GAM OAuth callback takes the tenant from attacker-supplied `state` | **#2205** | Open. Subsumes our `gam_authorize` finding |
| `is_tenant_admin()` queries a phantom `User.is_admin` | **#2206** | Open. Blocks #1861 |
| OIDC discovery document's `token_endpoint`/`jwks_uri` dialled unvalidated | **#1872** | Open. Sibling of the unsigned-token finding |
| Admin harness has no transport axis; every admin feature copies the last | **#2235** | Open, assigned |
| `src/admin` still reaching past repository/UoW | **#1853** | Open epic |
| Admin handlers auditing their own refusals as successes | **#2166** | Open |
| Approval query with no tenant filter | **#2126**, **#2127** | Open; #2232 §9 claims both |
| Per-account scope model and authoring surface | **#1615**, **#1856** | #2232 phase 2 homes |
| Unsigned `id_token`, `email_verified` absent | **new** | = #2232 §6 item 1, which carries no issue number |
| `/auth/oidc/test/<tenant_id>` undecorated, callback sets `oidc_enabled` | **new** | In #2203's 33 by construction; named nowhere |
| Four live unauthenticated tenant routes registered from `src/services/` | **new** | In #2203's 33 by construction; named nowhere |
| No CSRF protection while appearing to have it | **new** | No GitHub issue matches |
| A minted buyer token flashed into the session cookie | **new** | No GitHub issue matches |
| Tenant-management API key mint/verify mismatch | **new** | Closed #1098 is a different defect |
| Admin-created account unusable by any buyer | **new** | #1615/#1856 own the model, not this defect |
| Admin account path bypasses every `sync_accounts` gate | **new** | Same |
| No credential in the system has an expiry | **new** | No GitHub issue matches |

### The two new findings that are not already a ticket shape

**Four live, unauthenticated, tenant-parameterized routes are registered onto the admin app from
outside `src/admin/`.** `create_inventory_endpoints(app)` is called at `src/admin/app.py:409`. It
registers four routes directly with `@app.route("/api/tenant/<tenant_id>/inventory/...")` and no
decorator of any kind: `src/services/gam_inventory_service.py:1489`, `:1566`, `:1586`, `:1611`.
`register_adapter_routes` (`app.py:417`) registers two more the same way
(`src/adapters/google_ad_manager.py:1506`, `src/adapters/mock_ad_server.py:1429`). Those two sit
inside a broad `except Exception` that logs at DEBUG, so their reachability needs confirming
rather than asserting. Read from source; not exercised against a running app.

These are in #2203's 33 by construction, because #2203 walked the live `url_map` rather than
`src/admin/`. They are named in no issue, and no admin-scoped review would find them. That is the
strongest available argument for AC 6's guard being a `url_map` walk rather than a directory
scan. Three route-registering factories are *not* reachable and are dead code rather than
exposure. `src/adapters/gam_inventory_discovery.py:1029`, `:1049`, `:1071` and
`src/adapters/gam/utils/health_check.py:457` have no caller in `app.py` or `src/core/main.py`.

**The admin OIDC path accepts an identity from an unsigned token, and this is evidence for
#2232 §6's sequencing rather than a new requirement.** §6's first bullet states the mechanism:

> An identity assertion can cross planes. A tenant-configured identity provider can assert an
> identity that is then matched against operator-level administrator configuration, with no check
> on which issuer made the assertion.

The instance: `src/admin/auth_utils.py` reads `token["userinfo"]`. When it is absent, the module
decodes the id_token with `jwt.decode(id_token, options={"verify_signature": False})` (`:38`) and
trusts the result. `email_verified` appears **nowhere** in `src/` — zero occurrences. The email is
then taken from `email`, or `preferred_username`, or `upn`, or `sub` (`:46`–`:52`). That value
becomes the authorization subject and reaches `is_super_admin()` through `require_tenant_access`
(`helpers.py:357`), where a domain match grants super-admin (`helpers.py:178`–`:182`).

The path is reachable by a tenant-scoped actor. Per-tenant OIDC scopes are written by
`save_config` (`src/admin/blueprints/oidc.py:73`, scopes at `:92`), gated only by
`@require_tenant_access(api_mode=True)`. That decorator admits any active `User` row of the
tenant: `helpers.py:363` filters on `email`, `tenant_id`, `is_active=True` and nothing else.
Dropping `openid` from a tenant's scopes moves it onto the no-`userinfo`, unsigned-decode path.

§6's warning applies literally: "Enforcing policy against forgeable inputs converts an inert
misconfiguration into an active grant." This is that forgeable input, and it is the reason the
admin plane's enforcement work cannot lead. #1872 is its sibling. The same
tenant-admin-writable OIDC configuration reaches outbound dialing there, rather than the identity
subject. One writable surface, two consequences.

### The remaining new findings

**`/auth/oidc/test/<tenant_id>` is undecorated and its callback enables SSO.** The route
(`src/admin/blueprints/oidc.py:177`–`:178`) has no decorator. Its callback, on the `is_test`
branch, writes `oidc_verified_at`, `oidc_verified_redirect_uri` and `oidc_enabled = True` in one
transaction (`:302`–`:305`). The supported path refuses exactly this: `enable_oidc`
(`src/services/auth_config_service.py:164`) returns `False` unless `is_oidc_config_valid`
passes (`:182`). `oidc_enabled` decides which IdP a tenant authenticates against
(`src/admin/blueprints/auth.py:256`, `:259`, `:274`, `:276`).

**No CSRF protection, while the app appears to have it.** `CSRFProtect`, `flask_wtf` and
`flask-wtf` have zero occurrences in `src/` and zero in `pyproject.toml`. Meanwhile
`templates/base.html:6` renders `{{ csrf_token() if csrf_token else '' }}` against an undefined
name, and so silently emits an empty token. The admin fixture sets
`app.config["WTF_CSRF_ENABLED"] = False` (`tests/admin/conftest.py:33`) for a library that is not
installed. A deliberate production posture compounds it:
`SESSION_COOKIE_SAMESITE = "None"` and `SESSION_COOKIE_HTTPONLY = False`
(`src/admin/app.py:124`–`:136`), both for EventSource compatibility.

**A minted buyer token is flashed into the session cookie.**
`src/admin/blueprints/principals.py:205` flashes the plaintext token. That puts a live credential
in the signed session cookie and therefore in a `Set-Cookie` header, script-readable and
cross-site under that posture. The codebase already knows this.
`src/admin/blueprints/public.py:283`–`:290` documents the hazard by line number and deliberately
renders its token into the response body instead, with "no flash, no session stash and no
redirect". An AST scan of all of `src/admin/` finds exactly one site on the wrong side of that
reasoning.

**The documented bootstrap mints the wrong key and rotates a second one.**
`mint_tenant_management_api_key()` (`src/admin/sync_api.py:673`) mints under
`SYNC_API_CONFIG_KEY = "api_key"` (`:33`), while the tenant-management decorator verifies
`config_key="tenant_management_api_key"` (`src/admin/tenant_management_api.py:34`–`:38`). Its own
docstring reads "Mint the sync API key". `scripts/initialize_tenant_mgmt_api_key.py:35` calls it.
So the documented bootstrap hands an operator a key that cannot authenticate the tenant-management
API, and silently rotates the sync key out from under whoever holds it.
`tenant_management_api_key_prefix()` (`sync_api.py:684`) reads the same wrong row, so the
"existing key" the script reports is the sync key's prefix too. The API is reachable. All six
routes authenticate against `TENANT_MANAGEMENT_API_KEY` in the environment via
`hmac.compare_digest` (`src/admin/auth_helpers.py:115`, `:63`). That variable is absent from
`docs/deployment/environment-variables.md`, as is `SYNC_API_KEY`.

**An account created in the admin UI can never be used by any buyer.**
`AccountRepository.grant_access` (`src/core/database/repositories/account.py:541`) has exactly one
caller in the tree: `src/core/tools/accounts.py:1554`, inside `sync_accounts`' create branch. The
admin create path passes `principal_id=None` (`src/admin/blueprints/accounts.py:92`) and grants
nothing, so every later resolution fails. `_require_access`
(`src/core/database/repositories/account_lookup.py:105`) raises `AdCPAuthorizationError` when
`has_access` is false, and both resolution paths call it (`:62`, `:101`). The tool's update branch
does not grant either (`accounts.py:1293`). A buyer who syncs that natural key therefore receives
`action="updated"` plus an `account_id` that fails on every subsequent call.

**The admin account path bypasses every gate `sync_accounts` enforces.** The row shape is shared,
because `src/admin/blueprints/accounts.py:84` calls `AccountRepository.build_row`. The gates are
not:

| Gate | `sync_accounts` | admin create |
|---|---|---|
| Approval mode | `initial_status = "pending_approval" if setup else "active"` (`src/core/tools/accounts.py:1518`) | `status="active"` hardcoded (`accounts.py:88`). `account_approval_mode` has no CHECK constraint (`src/core/database/models.py:97`) and no template writes it |
| Billing policy | `_check_billing_policy` (`accounts.py:798`) | full-enum dropdown, unchecked (`accounts.py:61`) |
| Sandbox capability | `_check_sandbox_capability` (`accounts.py:864`) | unchecked (`accounts.py:70`) — and `sandbox` is an immutable natural-key component (`src/core/database/repositories/account.py:116`–`:118`) |
| Field disposition | `_FIELD_POLICY` (`accounts.py:522`) | no equivalent |
| Occupied natural key | upserts | refuses with a form error (`accounts.py:99`–`:111`) |

The last row is the only one the code documents as deliberate. This is #2232 §5.3's argument in
the admin plane. There are two implementations of one decision, and the one in the blueprint has
no constructor to bind a subject to.

**No credential in the system has an expiry.** Not the buyer tokens, not the two API keys, not
the admin session. Rotation is the only revocation mechanism. That makes the mint/verify mismatch
above a revocation defect as well as a bootstrap one.

## Part 4: What grades the admin plane

#2235 owns this gap. The measurement below counts behaviour-driven development (BDD) scenarios
and plain test functions separately. It was taken on this branch, and therefore predates PR
#2231, which adds `AdminTenantScopingEnv` and an e2e mirror.

| | buyer plane | admin plane |
|---|---|---|
| BDD features | 52 | 1 (`tests/bdd/features/BR-ADMIN-ACCOUNTS.feature`) |
| BDD scenarios | 2628 | 13 |
| Transports per scenario | impl, mcp, a2a, rest in process, plus `e2e_rest` | 1 (Flask test client, in process) |
| Blueprints covered | n/a | 1 of 27 |
| Scenarios asserting an authorization refusal | — | 1 (feature `:165`) |

There is also a non-BDD admin suite: 147 test functions in `tests/admin/` and 43 in
`src/admin/tests/`, 190 in total. Seven sites in all of it assert an authorization refusal
(`tests/admin/test_settings_blueprint.py:344`, `test_users_blueprint.py:267`,
`test_oidc_blueprint.py:90`, `src/admin/tests/unit/test_utils.py:126` and `:193`,
`src/admin/tests/integration/test_admin_app.py:137`, `src/admin/tests/unit/test_auth.py:289`).

The blueprint with the worst finding has four tests and none of them mentions authorization.
`tests/admin/test_publisher_partners_blueprint.py:51`, `:67`, `:89`, `:128` all cover duplicate
handling and error text. PR #2075 adds `tests/admin/test_publisher_partners_auth.py`, which is the
gap closing, subject to the caveat #2203's traps raise about that PR's sync tests.

#2235's conclusion binds this document's sequencing: "Until this lands, new admin features should
not be converted onto the current harness — anything built on it now is another override on top
of overrides." So step 0 below is #2235, not a new proposal.

## Part 5: What this proposes

Three things, none of them an architecture. #2232 supplies the architecture.

**1. The admin PEP seat is `require_tenant_access`, and the other nine mechanisms are retired
onto it.** #2232's PEP row already names the decorators as the admin seat. Mechanisms 4 through 9
are not additional seats; they are the seat not being used. Retiring them is mechanical per
mechanism. #2204 deletes mechanism 4. #2206 resolves the predicate behind mechanism 8. The issue
#2203's Notes asks for retires mechanism 6. Mechanism 5's session cache has nothing left to save
once the decorator resolves once per request.

**2. That seat produces a `Decision`, per #2232 §6's ask.** The decorator today returns a
rendered redirect or a `jsonify` pair, so the reason a request was refused exists nowhere. Under
#2232 §5.4 the reason is what the wire code, the disclosure posture and the audit obligation all
derive from. The change at this seat is that `require_tenant_access` computes a `Decision`, and
the error shape derives from its reason. That is the whole of what the parent asks of this plane,
and it is what gives #2166 (admin handlers auditing refusals as successes) something to attach
to. Two of #2232's nine phase 1 rules bear on this seat. Its §5.1 already marks one of them
dormant: "the admin-role rule stays inert until the identity-integrity work in section 6 lands."

**3. The exemption is replaced and the seat gets the guard #2203 specifies.**
`ruff-ownership.toml:51`'s glob becomes per-file rows for the admin modules that genuinely handle
principals and accounts as data. That is the treatment the four single files outside `src/admin`
already get by name, and each row carries a `# FIXME(#<issue>)` at the source location.
Separately, #2203 AC 6's `url_map` guard lands with its exempt set seeded at today's 33 and a
one-line reason per entry. The guard is the piece whose absence Part 2 diagnoses. Per this repo's
practice it should be broken on purpose first: re-remove a decorator from one route and watch it
go red.

## Part 6: Sequencing

Each step lands on its own and leaves the tree green. Nothing here supersedes #2232's ordering
constraint 1, "identity integrity before admin-plane enforcement", or its constraint 4, "direct
fixes never wait".

**Step 0 — the net (#2235).** Split `AdminTransportEnv` out of `AdminAccountEnv`, give the admin
family a real transport axis at the conftest hook, and publish the shared helpers. #2235 says not
to build new admin features before this lands. The fixture problem is inside it: a request that
must be unauthenticated cannot go through a client that arms mechanism 9.

**Step 1 — identity integrity (#2232 §6).** The unsigned-`id_token` path, plus #1872's sibling
hop. This is #2232's constraint 1 and it precedes every enforcement step below. It wants the issue
number §6's first bullet does not have.

**Step 2 — the in-flight fixes, unchanged.** PR #2075 (five publisher-partner routes), PR #2231
(#2203's four), then #2204, #2205, #2206. None waits on this document. #2232 §6 says so, and this
document does not propose otherwise. The 5-routes correction and the vacuous-test caveat belong as
review comments on #2075, not as new tickets.

**Step 3 — the three unowned route findings.** The four `src/services/gam_inventory_service.py`
routes, `oidc.py:178`, and `inventory.py:344`/`:516`/`:558`. All three are the shape #2203 and
#2075 already fix. They need issues, not design.

**Step 4 — CSRF.** Add the dependency, register `CSRFProtect` in `create_app`, make
`base.html:6` emit a real token. The empty-token tag is already the insertion point.

**Step 5 — the guard and the exemption.** #2203 AC 6's `url_map` guard, then per-file rows
replacing `ruff-ownership.toml:51`. After this, a regression at this seat fails a build.

**Step 6 — `Decision` at the seat.** Proposal 2 above, once #2232's vocabulary module exists.
Phase 1 of #2232's table lists "the admin plane adopts the same decision vocabulary". So this step
is inside that phase rather than after it.

**Step 7 — the account path onto the shared service.** After #1853. It retires both account
findings together rather than patching five gates into a Flask view.

**Step 8 — credential lifetime.** Expiry on the two API keys, the buyer tokens, the admin session.

Two point defects are not in this sequence, because they do not need it. The tenant-management key
mismatch is a wrong constant in two functions. The flashed buyer token is one call, with the
correct pattern already written out at `public.py:283`–`:290`.

## Part 7: Open questions

- **Does the admin seat want `Decision` or the repository seam?** #2232 §5.3 puts row-level
  decisions at the repository, and #1853 is migrating `src/admin` onto repository/UoW. If that
  migration completes first, most admin row-level scoping arrives through §5.3's construction and
  the decorator seat shrinks to the caller-level question. The two tracks should agree on which
  seat owns tenant scoping before step 6, not after.
- **What is the one admin authority vocabulary?** `User.role` permits `admin|manager|viewer`;
  templates gate on `super_admin|tenant_admin`; `require_auth(admin_only=True)` asks
  `is_super_admin` instead of reading a role; #2206 asks delete-or-fix on `is_tenant_admin`.
  #2206 scopes "making `User.role` authoritative" out as "a separate, sequenced piece of work with
  its own activation hazard" — and #2232 §6's second bullet is that hazard. It needs an owner.
- **Are `health_config`, `metrics` and `debug_headers` intended to be unauthenticated?** Three of
  `core.py`'s seven undecorated handlers are information surfaces. They belong in step 5's exempt
  set either way; the question is whether permanently.
- **How does first-run admin setup happen?** The test-credential login path is a bootstrap
  capability wearing a test flag (`app.py:350`), which #2232 §6's framing makes a sequencing
  hazard rather than a convenience. Ancestor: closed #1127.
- **Do the two `register_adapter_routes` routes register?** `google_ad_manager.py:1506` and
  `mock_ad_server.py:1429` register inside a broad `except Exception` logging at DEBUG
  (`app.py:430`–`:442`). Read from source; needs confirming against a running app.

## Part 8: Non-goals

- **Not a parallel architecture.** The PEP/PDP/PIP/PAP decomposition, the `Decision` type, the
  reason-to-wire mapping and the two decision points are #2232's, adopted by reference. This
  document contributes an inventory, an ownership table, and a sequencing.
- **Not a rewrite.** Ten mechanisms retire one at a time behind a guard. Steps 1 through 5 change
  no handler signature.
- **Not the buyer plane's ACL question.** #2232 §1 and #1849 own product entitlement on the write
  path; #1615 and #1856 own the phase 2 scope model.
- **Not a new authentication provider.** #1844 (OAuth 2.1) and #1291 (RFC 9421) each become one
  `Authenticator` behind #2232 §5.5's seam.
- **Not the error-disclosure sweep.** #2166 and its beads siblings are a disclosure surface, not
  an authorization one.

## Sources

- [#2232 RFC: AuthZ design](https://github.com/prebid/salesagent/issues/2232) — the parent; §1,
  §3, §5.1–§5.4, §6, §8, §11 cited above
- [#2203](https://github.com/prebid/salesagent/issues/2203),
  [#2204](https://github.com/prebid/salesagent/issues/2204),
  [#2205](https://github.com/prebid/salesagent/issues/2205),
  [#2206](https://github.com/prebid/salesagent/issues/2206),
  [#1872](https://github.com/prebid/salesagent/issues/1872),
  [#2235](https://github.com/prebid/salesagent/issues/2235),
  [#1853](https://github.com/prebid/salesagent/issues/1853),
  [#2166](https://github.com/prebid/salesagent/issues/2166),
  [#2126](https://github.com/prebid/salesagent/issues/2126) — the admin plane's own track
- [PR #2075](https://github.com/prebid/salesagent/pull/2075),
  [PR #2231](https://github.com/prebid/salesagent/pull/2231) — in flight
- `src/core/tools/_boundary.py`, `src/core/resolved_identity.py` — the buyer-plane seam
- `src/admin/utils/helpers.py`, `src/admin/auth_helpers.py`, `src/admin/auth_utils.py`,
  `src/adapters/gam_reporting_api.py` — the admin mechanisms
- `ruff-ownership.toml:51` — the exemption
- CLAUDE.md patterns 3, 5, 11; § Structural guards. `tests/CLAUDE.md` § Which kind of test

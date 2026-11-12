# Deploying noetis

`noetis` is upstream [prebid/salesagent](https://github.com/prebid/salesagent) `main` with the
open PRs below merged in. It runs AdCP 3.2.7 (adcp 9.3.0). This note lists what you have to set up
or know when you deploy it in your own environment. Everything `noetis` already fixes is left out.

## What noetis adds to main

- [#2313](https://github.com/prebid/salesagent/pull/2313): `GET /tls/ask`, so a reverse proxy can
  gate on-demand TLS by tenant host. Off by default; set `TLS_ASK_ENABLED=true` to use it.
- [#2327](https://github.com/prebid/salesagent/pull/2327): the capabilities portfolio names
  verified publishers, and a host that owns no property answers 404 for `adagents.json`.
- [#2330](https://github.com/prebid/salesagent/pull/2330) (since merged upstream): products derive
  their publishers and format options from each publisher's stored `adagents.json`.
- [#2411](https://github.com/prebid/salesagent/pull/2411): MCP tool schemas keep their `$ref`s, so
  `tools/list` stays small enough for an LLM client.
- [#2412](https://github.com/prebid/salesagent/pull/2412): a signed request's keyid resolves
  against the addressed tenant's onboarding records (keys pinned per principal).
- [#2498](https://github.com/prebid/salesagent/pull/2498): Google Ad Manager booking, creative
  trafficking, geo targeting and delivery reporting fixes.
- [#2189](https://github.com/prebid/salesagent/pull/2189): test-run reporting (CI only).
- An empty alembic revision that joins the migration heads of
  [#2330](https://github.com/prebid/salesagent/pull/2330) and
  [#2412](https://github.com/prebid/salesagent/pull/2412).

## Set up before the first deploy

### Container health check

The image's health check gives the app a 5-second start period, but the first start after a
release runs the migrations and takes about 2 minutes. The container shows `unhealthy` first, and
an automatic rollback reads that as a failed deploy. Give the app a longer start period, for
example in compose:

```yaml
  app:
    healthcheck:
      start_period: 300s
```

### Creative agent settings

- `CREATIVE_AGENT_URL` is the agent's MCP endpoint, ending in `/mcp`, not its base URL.
- `CREATIVE_AGENT_ORIGIN` is the format identity. Unset, it is the public reference agent,
  `https://creative.adcontextprotocol.org`.
- **If you self-host the reference creative agent**, set `CREATIVE_AGENT_ORIGIN` to its origin
  (for example `https://creative.example.com`), and make every product's format references name
  the address it lists formats under, `<origin>/api/creative-agent`. Without this,
  `sync_creatives` refuses every format except static display images as `UNSUPPORTED_FEATURE`
  ([#2546](https://github.com/prebid/salesagent/issues/2546)). Buyers then use the format ids
  your products list.
- **HTML banners:** a self-hosted 3.2.x reference agent resolves `display_*_html` as canonical
  `html5`, so products offer an `html5` option for them, and the buyer's inline HTML reaches Google
  Ad Manager as a third-party creative. The public agent already serves 3.3 beta, which resolves
  them as `display_tag`; the seller cannot traffic that yet
  ([#2547](https://github.com/prebid/salesagent/issues/2547)). Use a self-hosted 3.2.x agent if
  you sell HTML banners.

### Publishers

- A product is offered only for publishers whose `/.well-known/adagents.json` authorizes the
  tenant's URL and was fetched in the last 24 hours. Each site's file lists one entry per seller
  that sells it.
- The image's crontab re-fetches every publisher every 6 hours
  (`scripts/ops/refresh_publishers.py`). If you replace that crontab, keep the job, or products
  disappear a day after the last fetch. Run the script by hand after publishing a site's file.
- A fetch never follows a redirect to another registrable domain, so a tenant's publisher must be
  the domain that serves the file, not a host that redirects to it.

### Testing a deployment

On a deployment with `ADCP_TESTING` set, formats resolve from a committed catalogue that names the
public agent, and no creative agent is asked. A buy that works there does not prove the creative
path of a production deployment that uses a real (for example self-hosted) agent. Check that on
production with a dry-run `sync_creatives`.

### A conformance (storyboard) tenant

Only if you host one for AdCP grading:

- The storyboard seeders refuse to run when `PRODUCTION`, `ENVIRONMENT=production` or
  `FLY_APP_NAME` is set, because they write test-kit credentials. On a deployment that keeps
  `ENVIRONMENT=production`, run only the seeding process with `ENVIRONMENT=conformance`.
- The request-signing seeder needs the compliance bundle on disk. In a one-off container, call
  `tests.storyboard.bundle.materialize_bundle()` before `scripts.setup.storyboard_signing.seed()`.
- The test kit's publishers (`*.example`) never resolve, so they never sell. Keep them (the
  `inventory_list_targeting` storyboard checks the seller carries them), and add a real site whose
  `adagents.json` authorizes the conformance tenant, attached to the tenant's products.

### Upgrading an existing database

Migration `b4f1a9c27d53` (from [#2474](https://github.com/prebid/salesagent/pull/2474)) stops the
upgrade if any creative names a format agent other than the deployment's `CREATIVE_AGENT_ORIGIN`
identity. Point those references at the right agent before you switch, and rehearse the upgrade
on a copy of the production database.

## Known limitations

These still happen on `noetis`, which includes all the PRs above:

- A buy can be booked in the ad server and then reported as failed when the creative upload fails,
  and a retry books a second order
  ([#2393](https://github.com/prebid/salesagent/issues/2393)).
- An HTML-only creative passes the pre-booking check only if `sync_creatives` stored a preview URL
  and size on it ([#2390](https://github.com/prebid/salesagent/issues/2390)).
- A canonical `html5` zip creative never reaches Google Ad Manager as an `Html5Creative`
  ([#2545](https://github.com/prebid/salesagent/issues/2545)), and a `display_tag` creative is
  refused or sent as an image ([#2547](https://github.com/prebid/salesagent/issues/2547)).
- `get_media_buys` never reports `formats_pending`, so buyers cannot tell when a package's formats
  are covered ([#2544](https://github.com/prebid/salesagent/issues/2544)).
- Only Google Ad Manager receives creatives. Kevel and Triton fail
  ([#2416](https://github.com/prebid/salesagent/issues/2416); Triton already fails in its
  constructor, [#2539](https://github.com/prebid/salesagent/issues/2539)), and Broadstreet tenants
  run on the mock adapter ([#2024](https://github.com/prebid/salesagent/issues/2024)).

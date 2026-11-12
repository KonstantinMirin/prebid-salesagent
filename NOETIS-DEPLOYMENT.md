# noetis deployment: handoff notes

The `noetis` branch of this fork is what the noetis deployments run: upstream `main` plus the
owner's open PR branches, each merged in, plus a few `carry/*` branches (this note is one). This
file records what running it in production taught us, so the next person does not relearn it.

Hosts, addresses, secrets, the deploy and seed scripts, and the per-upgrade records live in the
private `noetis-deploy` repository (ask the owner for access). Its `README.md` is the operating
manual; `upgrades/2026-11-11-adcp-3.2/README.md` is the most recent upgrade, step by step.

State as of 2026-11-12: tag `noetis-2026.11.11-1`, AdCP 3.2.7 (adcp 9.3.0), upstream `main`
`48e8d9b0c` plus #2313, #2327, #2330, #2411, #2412, #2498, #2189 and
`carry/alembic-merge-2412-2330`. #2330 has since merged upstream.

## Branch model

- `noetis` only ever receives merges: upstream `main`, a PR branch, or a `carry/*` branch. Nothing
  is committed on it directly. A fix that the integration needs (for example the empty migration
  that joins two PRs' alembic heads) goes on its own `carry/*` branch and is merged like a PR.
- A re-cut rebuilds `noetis` from `main` by merging only what should stay. To keep the push a
  fast-forward, merge the old tip with `git merge -s ours fork/noetis` after the re-cut, and check
  that the tree is the one you meant (`git rev-parse HEAD^{tree}`).
- Deploys are tagged `noetis-YYYY.MM.DD-N` on `noetis`.

## Gotchas

### Upgrades and migrations

1. **A re-cut can orphan a migration.** If the old `noetis` carried a migration that the new one
   does not (a PR changed or dropped it), the new image crash-loops with "Can't locate revision".
   Downgrade that revision with the **old** image before switching
   (`alembic downgrade <its down_revision>`), then start the new image.
2. **Two carried PRs can each add an alembic head.** The single-head guard then fails. Join them
   with an empty merge revision on a `carry/*` branch; upstream needs none, because the second PR
   to land re-points its `down_revision`.
3. **The first start after an upgrade takes about 2 minutes** (migrations run on start). The image's
   own healthcheck has a 5-second start period, so the container reports `unhealthy` before it
   turns `healthy`, and an automatic rollback reads that as a failure. Give the `app` service a
   `healthcheck: start_period: 300s` in compose.
4. **Rehearse data migrations on a copy of the production dump** before the live switch. Migration
   `b4f1a9c27d53` (#2474) aborts if any creative names a format agent other than the operator's
   identity; the first production switch crash-looped on it.

### Creative agent: identity and transport (#2474)

5. **`CREATIVE_AGENT_URL` is the MCP endpoint itself** (ending in `/mcp`), not the agent's base URL.
   `CREATIVE_AGENT_ORIGIN` is the format **identity**; unset, it is the public reference agent,
   `https://creative.adcontextprotocol.org`.
6. **A self-hosted reference agent needs `CREATIVE_AGENT_ORIGIN` set to its own origin**, and every
   stored format reference (products' `format_options[].v1_format_ref`, creatives, packages) must
   name the address it lists formats under, `<origin>/api/creative-agent`. With `ORIGIN` unset,
   `sync_creatives` finds no format declaration for any operator reference and refuses every format
   except static display images as `UNSUPPORTED_FEATURE` (#2546). Buyers then copy the
   self-hosted agent's format ids from `get_products`, not the public ones.
7. **Test mode hides creative-path problems.** Under `ADCP_TESTING`, formats resolve from a
   committed capture that names the public agent, and no creative agent is dialled for resolution.
   A dry run on a test deployment does not validate the creative path of a production deployment
   that dials a real agent.
8. **Inline HTML banners.** The 3.2.x reference catalogue labels `display_*_html` as canonical
   `html5`, while the 3.2.7 spec text says inline markup is `display_tag`
   (`docs/creative/channels/display.mdx`: "Inline third-party markup is never an `html5` bundle";
   fixed upstream only in adcontextprotocol/adcp#8357, 3.3 beta). A self-hosted 3.2.x agent therefore
   resolves them as `html5`, and products should offer `html5` options for them. The public agent
   (3.3 beta) says `display_tag`, which today's products and GAM path do not handle (#2547).
   With #2498, an `html` asset reaches GAM as a `ThirdPartyCreative` snippet.

### Publishers and products (#2330)

9. **A product is offered only for publishers whose `adagents.json`, fetched within the last 24
   hours, authorizes the tenant's URL.** The image's crontab refreshes every 6 hours
   (`scripts/ops/refresh_publishers.py`); a deployment that mounts its own crontab must keep that
   job. If products disappear a day after a deploy, check the publisher's `fetch_status`.
10. **A fetch never follows a redirect off the registrable domain.** Name the domain that serves the
    file (for example `briefgateway.com`, not a host that 301s to it).
11. **The file is the publisher's, not the agent's.** It lists one `authorized_agents` entry per
    seller; one site can authorize several sellers (production and test). Publish the site, then
    fetch (`refresh_publishers.py`) and check the tenant's products appear.
12. **The conformance tenant needs a real publisher.** The storyboard test kit's publishers
    (`*.example`) must stay, because `media_buy_seller/inventory_list_targeting` grades that the
    seller carries them, but they never resolve, so they never sell. Add a fetchable site that
    authorizes the conformance tenant and attach it to the tenant's products.

### Seeding

13. **The storyboard seeders refuse a production deployment** (`scripts/setup/production_guard.py`:
    `PRODUCTION`, `ENVIRONMENT=production` or `FLY_APP_NAME`), because they write test-kit
    credentials. A deployment that keeps `ENVIRONMENT=production` and hosts a conformance tenant on
    purpose runs only the seeding process with `ENVIRONMENT=conformance`.
14. **The signing seeder needs the compliance bundle on disk.** In a one-off container, call
    `tests.storyboard.bundle.materialize_bundle()` before `storyboard_signing.seed()`.
15. **Since AdCP 3.2 a test kit declares the AAO hosted grader's brand**, so
    `seed_storyboard_tenant` derives its accounts itself. Accounts created for it by hand before 3.2
    collide on the natural key; delete them and re-seed.

### Booking

16. **A buy can be booked and then reported as failed.** If the creative step fails after the
    adapter booked, the buyer gets a transient error and a retry books a second ad-server order
    (#2393). On Kevel this happens on every auto-approved buy with a creative (#2416).
17. **An HTML-only creative passes the pre-adapter check only if `sync_creatives` stored a preview
    URL and size on it** (#2390). Canonical `html5` zip creatives never become an `Html5Creative`
    (#2545).
18. **Readiness is never reported.** `formats_to_provide` stays on a package after its creatives are
    attached, as the spec requires, but `formats_pending` is never emitted (#2544).
19. **Only GAM traffics creatives.** Kevel, Triton and Broadstreet do not receive them (#2416);
    Triton fails in its constructor (#2539), and Broadstreet tenants run on the mock adapter
    (#2024).

### Buyer clients

20. **MCP headers are fixed when a client connects.** A Claude Code session started without its
    seller token cannot recover by exporting it later. Use a `headersHelper` on the HTTP MCP server
    that prints the `Authorization` header, so the token is fetched at connect time.

## Open upstream issues to watch

#2544 (`formats_pending`), #2545 (`html5` zip), #2546 (format lookup with a self-hosted agent),
#2547 (`display_tag`), #2390, #2393, #2416, #2024, #2539, #2093, #2236 (canonical format RFC).

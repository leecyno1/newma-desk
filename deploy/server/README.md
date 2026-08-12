# Newma-Desk server deployment

## Core stack

Run the production core with static frontends and the slim Python API runtime:

```bash
docker compose \
  --env-file deploy/server/.env.server \
  -f deploy/server/docker-compose.yml \
  --profile core \
  up -d --build
```

The production core publishes:

- `5888` Desk shell
- `8911` Newma-Desk API
- `80` public gateway

Market workspaces are bundled into the Desk build and loaded on demand through
`5888`. Port `5891` is reserved for optional standalone development only and
is not part of the production core profile.

## Newma WebUI co-located deployment

When NewmaDesk, Newma WebUI, and Hermes run on one remote server, "same
server" must not become "browser loopback". The browser-facing layout uses
three distinct HTTPS Origins, all reverse-proxied to services on that server:

- `https://desk.example` → Desk shell (`127.0.0.1:5888`) and Desk `/api/`
  (`127.0.0.1:8911`)
- `https://mods.example` → integrated Mod/API runtime (`127.0.0.1:8911`)
- the existing authenticated Newma WebUI Origin

Configure WebUI with the exact Desk Origin in both
`NEWMA_DESK_EMBED_ORIGIN` and `NEWMA_NUMA_DESK_ALLOWED_ORIGINS`, and add it to
`HERMES_WEBUI_CSP_FRAME_EXTRA`. Configure
Desk's `PUBLIC_DESK_ORIGIN` to the Desk Origin and its integrated Research /
Trading browser URLs to the Mod Origin. Do not publish `127.0.0.1` in a Mod
manifest: in a remote browser it means the user's computer, not the server.

The reverse direction is separate: Desk API must reach the internal Newma /
Hermes WebUI API through `NEWMA_DESK_HERMES_WEBUI_BASE_URL`. The Compose file
provides `host.docker.internal` through Docker's host gateway; point the
variable at the actual reachable listener or a private host proxy. Standard
managed nodes normally use port `8788`; c10375 uses `8787`. Do not assume the
port or systemd unit name across servers. If WebUI authentication is enabled,
also configure the service-only cookie and CSRF token. `/api/capabilities`
must report the `hermes-webui` adapter as available before deployment passes.

Desk and its Mod runtime remain cross-origin from WebUI so sandboxed frames can
retain their own origin without gaining authenticated same-origin access to the
WebUI parent. A production Desk shell must be a static build; `/@vite/client`
or `/src/main.tsx` is a failed deployment.

After deployment, run the fail-closed preflight with the actual health URLs:

```bash
python3 deploy/server/check-newma-stack.py \
  --desk-origin https://desk.example \
  --mod-origin https://mods.example \
  --webui-origin https://newma.example \
  --webui-health-url http://127.0.0.1:8788/health \
  --hermes-health-url http://127.0.0.1:PORT/health
```

It verifies the production Desk shell, Desk API, Mod runtime, WebUI and Hermes
health, plus the Desk → WebUI adapter. Any unavailable adapter, leaked loopback
URL, development shell, shared browser Origin or unhealthy service fails the
deployment.

`register-mods` is now an explicit one-shot ops profile instead of a permanent
Node runtime:

```bash
docker compose \
  --env-file deploy/server/.env.server \
  -f deploy/server/docker-compose.yml \
  --profile ops \
  run --rm register-mods
```

## Optional integrations

Deepsee, Seven Cycle, InStock, and Orchestra remain opt-in so most servers only
carry the core footprint. Use the profile wrapper when you want to compose them
with the core stack:

Typical pattern:

```bash
docker compose \
  --env-file deploy/server/.env.server \
  -f deploy/server/docker-compose.yml \
  --profile core \
  up -d --build

docker compose \
  --env-file deploy/server/.env.external \
  -f deploy/server/docker-compose.integrations.yml \
  --profile optional-integrations \
  up -d --build
```

You can also target only one integration profile, for example `--profile
instock` or `--profile orchestra`.

`docker-compose.external.yml` is the shared service definition used by the
profile wrapper. For normal deployment, invoke `docker-compose.integrations.yml`
so a host cannot start every heavy integration by accident.

Default container guardrails:

| Runtime | Profile | Memory | PIDs |
| --- | --- | ---: | ---: |
| Desk / Gateway | `core` | `96m` each | `64` each |
| Integrated API | `core` | `768m` | `256` |
| Mod registration job | `ops` | `128m` | `64` |
| Deepsee | `deepsee` | `768m` | `256` |
| Seven Cycle | `seven-cycle` | `1536m` | `256` |
| InStock | `instock` | `768m` | `256` |
| Orchestra API / Web | `orchestra` | `1024m` / `128m` | `256` / `64` |
| Orchestra Postgres / Redis | `orchestra` | `512m` / `256m` | `128` each |

Every listed service also enables `no-new-privileges`; application services
that may spawn child processes use Compose `init`. The values are hard limits,
not reservations, and can be overridden in `.env.server` or `.env.external`.

## Runtime layout

- `api` now runs from the `api-runtime` target and no longer carries Node,
  `git`, or build toolchains.
- `desk` serves the shell and the lazily loaded market workspaces from one
  static build. First-party market pages no longer use an iframe or a second
  nginx container.
- The Docker build still compiles integrated Research/Trading frontends, but
  only their built assets and runtime Python sources are copied into the final
  API image.
- Research and Trading share one controlled Python dependency set. Production
  never loads either upstream workspace `.venv`; that compatibility mode is
  reserved for local development.
- `requirements-domain-runtime.txt` is the single Research/Trading production
  dependency entry. The Desk API is installed into the same environment under
  `constraints-domain-runtime.txt`; every image build runs `pip check` before
  accepting the environment.
- The legacy `mootdx` fallback is not installed in the unified API image:
  upstream `mootdx==0.11.7` requires `httpx<0.26`, while Desk and Trading
  require `httpx>=0.28`. Research loads it lazily, so Tencent/AKShare paths
  remain available; the mootdx-only finance fallback stays unavailable until
  it can move behind an isolated Adapter or upstream relaxes that constraint.
- Research native chat/model settings and Trading native Agent, channels,
  scheduler and upload routes are absent in integrated mode. Both suites use
  the Desk Agent selected in the global or per-Mod Agent settings.
- Builders use Node 22 and Python 3.12. Frontends install from their committed
  npm lockfiles with `npm ci`; Python direct dependencies are constrained by
  `constraints-domain-runtime.txt`, and every image build runs `pip check`.
- Heavy external Mods keep their own images and dependency environments. This
  prevents one Mod's Python, Node, database or system packages from mutating the
  Desk runtime or another Mod.

Reference measurement on 2026-08-09:

- clean unified Python environment: `260.6 MiB` of file content (`289 MiB`
  allocated on disk), `69` installed distributions
- idle Research + Trading import RSS: `64.8 MiB`, with `47` Research routes,
  `33` Trading routes and no forbidden heavyweight imports
- Desk (including lazy market workspaces) / Portfolio frontends: `790.4 KiB` /
  `368.3 KiB`; no Desk chunk exceeds `420 KiB`
- integrated Research / Trading frontends: `697.1 KiB` / `1.72 MiB`
- filtered Docker build context: approximately `11.82 MiB`, down from
  `20.16 MiB` after excluding reproducible build outputs

The API container defaults to a `768m` limit because pandas factor jobs can use
substantially more memory than idle import. Static nginx containers default to
`96m`. Override these with `NEWMA_DESK_API_MEMORY_LIMIT` and
`NEWMA_DESK_STATIC_MEMORY_LIMIT` when a server profile needs different limits.

Run `npm run footprint:check` after production builds. It enforces frontend
budgets, Docker context exclusions and the integrated dependency blacklist.
The Docker builder also imports both Domain Suites and fails when idle import
RSS exceeds `192 MiB` or a removed heavyweight Agent dependency reappears.

Validate Compose expansion, profiles, memory limits, PID limits and
`no-new-privileges` without starting containers:

```bash
python3 deploy/server/check-compose.py
```

This static check only needs the Docker CLI with the Compose plugin. A real
multi-stage image build and health check still require a running Docker daemon.

## Reproducibility boundary

The core dependency environment and build inputs are controlled, but a clean
Newma-Desk clone still cannot recreate the current integrated Research and
Trading source trees while those ignored nested repositories contain unreviewed
working-tree changes. See [`docs/mod-project-source-lock.md`](../../docs/mod-project-source-lock.md)
and run `npm run mods:sources:check`. Publish reviewed forks at pinned commits
or create reviewed overlays before calling the full deployment reproducible.

Optional integrations are also built from pre-provisioned
`/opt/newma-projects/*` workspaces; Compose isolates them but does not clone or
pin those sources. Record reviewed commits for those workspaces before rolling
the same stack to multiple servers. For bit-for-bit image reproduction, also
pin base-image digests and generate a hashed Linux Python lock; the current
constraints intentionally pin direct dependencies only.

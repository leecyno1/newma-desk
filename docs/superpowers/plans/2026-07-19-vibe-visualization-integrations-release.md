# vibe-visualization Upstream Integrations and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap selected Vibe-Research and Vibe-Trading routes as independent HTML modules, preserve upstream isolation, add production deployment and CI, then publish synchronized private repositories to GitHub and Gitee.

**Architecture:** Build a reusable URL Adapter that is itself a standalone HTML page and contains the upstream route in a nested iframe. This preserves upstream updateability while giving every module a stable URL, health state, Module Bridge, and Agent Gateway access; later each adapter can be replaced by an extracted native module without changing its module ID.

**Tech Stack:** React 19, TypeScript, Vite, Module SDK, FastAPI health proxy, Nginx, Docker Compose, GitHub Actions, GitHub CLI, Gitee REST API

---

## File Structure

```text
packages/url-adapter/                         # reusable standalone wrapper page
integrations/vibe-research/modules/           # Research wrapper configurations
integrations/vibe-trading/modules/            # Trading wrapper configurations
services/api/vibe_visualization_api/integrations/
deploy/nginx.conf
deploy/docker-compose.yml
deploy/Dockerfile.web
deploy/Dockerfile.api
scripts/dev.sh
scripts/verify.sh
scripts/push-remotes.sh
.github/workflows/ci.yml
```

### Task 1: Build the reusable standalone URL Adapter

**Files:**
- Create: `packages/url-adapter/package.json`
- Create: `packages/url-adapter/src/UrlAdapter.tsx`
- Create: `packages/url-adapter/src/config.ts`
- Create: `packages/url-adapter/src/styles.css`
- Create: `packages/url-adapter/src/index.ts`
- Test: `packages/url-adapter/src/UrlAdapter.test.tsx`

- [ ] **Step 1: Write failing adapter tests**

Create the package manifest:

```json
{
  "name": "@vibe-visualization/url-adapter",
  "version": "0.1.0",
  "type": "module",
  "exports": "./src/index.ts",
  "scripts": {
    "build": "tsc --noEmit",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@vibe-visualization/module-sdk": "0.1.0",
    "react": "^19.0.0"
  },
  "devDependencies": {
    "@testing-library/react": "^16.3.0",
    "jsdom": "^27.0.0",
    "typescript": "^5.7.3",
    "vitest": "^4.0.0"
  },
  "peerDependencies": {"react-dom": "^19.0.0"}
}
```

```tsx
it("loads an allowed upstream URL in a nested iframe", async () => {
  render(<UrlAdapter config={{
    moduleId: "research-daily-review",
    title: "每日复盘",
    upstreamUrl: "http://127.0.0.1:5899/daily-review",
    healthUrl: "/api/integrations/research/health",
    allowedOrigin: "http://127.0.0.1:5899",
  }} />);
  expect(screen.getByTitle("每日复盘")).toHaveAttribute("src", "http://127.0.0.1:5899/daily-review");
});

it("rejects an upstream URL outside the declared origin", () => {
  expect(() => validateAdapterConfig({ ...config, upstreamUrl: "https://evil.example/" })).toThrow();
});
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `npm run test:run -w @vibe-visualization/url-adapter`

Expected: FAIL because the package does not exist.

- [ ] **Step 3: Implement config validation**

```ts
export type UrlAdapterConfig = {
  moduleId: string;
  title: string;
  upstreamUrl: string;
  healthUrl: string;
  allowedOrigin: string;
};

export function validateAdapterConfig(config: UrlAdapterConfig): UrlAdapterConfig {
  const upstream = new URL(config.upstreamUrl);
  if (upstream.origin !== config.allowedOrigin) throw new Error("upstream origin is not allowed");
  if (!["http:", "https:"].includes(upstream.protocol)) throw new Error("unsupported upstream protocol");
  return config;
}
```

- [ ] **Step 4: Implement the wrapper UI**

Requirements:

- Health check every 30 seconds and on browser focus.
- Show an offline card with last successful health timestamp and a retry button.
- Full-size nested iframe with `sandbox="allow-scripts allow-forms allow-downloads allow-popups allow-same-origin"` because the upstream application requires its own storage; isolation is maintained by its distinct origin.
- Provide an “打开原页面” link.
- Use Module SDK for Agent tasks and Shell events.
- Forward only whitelisted upstream `postMessage` events after validating `MessageEvent.origin` and `MessageEvent.source`.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
npm run test:run -w @vibe-visualization/url-adapter
npm run typecheck -w @vibe-visualization/url-adapter
```

Expected: PASS.

```bash
git add packages/url-adapter package-lock.json
git commit -m "feat: add standalone upstream URL adapter"
```

### Task 2: Register Vibe-Research wrapper modules

**Files:**
- Create: `integrations/vibe-research/package.json`
- Create: `integrations/vibe-research/integration.json`
- Create: `integrations/vibe-research/modules/daily-review/module.json`
- Create: `integrations/vibe-research/modules/market/module.json`
- Create: `integrations/vibe-research/modules/stock-analysis/module.json`
- Create: `integrations/vibe-research/modules/industry-chain/module.json`
- Create: `integrations/vibe-research/build-modules.mjs`
- Test: `integrations/vibe-research/build-modules.test.ts`

- [ ] **Step 1: Write the failing integration build test**

```ts
it("builds one independent HTML entry for every Research module", async () => {
  await buildResearchModules({ publicBaseUrl: "http://localhost:5888", upstreamBaseUrl: "http://127.0.0.1:5899" });
  for (const id of ["daily-review", "market", "stock-analysis", "industry-chain"]) {
    expect(existsSync(`integrations/vibe-research/dist/${id}/index.html`)).toBe(true);
  }
});
```

- [ ] **Step 2: Define exact route mappings**

Create the workspace package:

```json
{
  "name": "@vibe-visualization/vibe-research-integration",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "node build-modules.mjs",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {"@vibe-visualization/url-adapter": "0.1.0"},
  "devDependencies": {"typescript": "^5.7.3", "vite": "^6.4.0", "vitest": "^4.0.0"}
}
```

```json
{
  "id": "vibe-research",
  "healthUrl": "http://127.0.0.1:8900/api/health",
  "modules": [
    {"id": "research-daily-review", "name": "每日复盘", "path": "/daily-review", "category": "research"},
    {"id": "research-market", "name": "股票行情", "path": "/watchlist", "category": "market"},
    {"id": "research-stock-analysis", "name": "个股分析", "path": "/stock-data", "category": "research"},
    {"id": "research-industry-chain", "name": "产业链研究", "path": "/sectors", "category": "research"}
  ]
}
```

Keep IDs stable when the upstream implementation changes.

- [ ] **Step 3: Generate one static wrapper per module**

`build-modules.mjs` must create an isolated Vite build input for each route, write a resolved adapter config, build into `dist/{short-id}/`, and copy its Manifest beside `index.html`. All generated Manifests use `entry.type="static"` and local URLs under `/modules/integrations/vibe-research/`.

- [ ] **Step 4: Run build tests and commit**

Run:

```bash
npm run test:run -w @vibe-visualization/vibe-research-integration
npm run build -w @vibe-visualization/vibe-research-integration
```

Expected: four independent `index.html` files exist.

```bash
git add integrations/vibe-research package-lock.json
git commit -m "feat: wrap Vibe Research routes as modules"
```

### Task 3: Register Vibe-Trading wrapper modules

**Files:**
- Create: `integrations/vibe-trading/package.json`
- Create: `integrations/vibe-trading/integration.json`
- Create: `integrations/vibe-trading/modules/alpha-zoo/module.json`
- Create: `integrations/vibe-trading/modules/backtest-reports/module.json`
- Create: `integrations/vibe-trading/modules/trade-console/module.json`
- Create: `integrations/vibe-trading/build-modules.mjs`
- Test: `integrations/vibe-trading/build-modules.test.ts`

- [ ] **Step 1: Write the failing integration build test**

Assert that builds produce:

```text
integrations/vibe-trading/dist/alpha-zoo/index.html
integrations/vibe-trading/dist/backtest-reports/index.html
integrations/vibe-trading/dist/trade-console/index.html
```

- [ ] **Step 2: Define exact route mappings**

Create the workspace package:

```json
{
  "name": "@vibe-visualization/vibe-trading-integration",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "node build-modules.mjs",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {"@vibe-visualization/url-adapter": "0.1.0"},
  "devDependencies": {"typescript": "^5.7.3", "vite": "^6.4.0", "vitest": "^4.0.0"}
}
```

```json
{
  "id": "vibe-trading",
  "healthUrl": "http://127.0.0.1:8899/health",
  "modules": [
    {"id": "trading-alpha-zoo", "name": "Alpha Zoo", "path": "/alpha-zoo", "category": "quant"},
    {"id": "trading-backtest-reports", "name": "回测报告", "path": "/reports", "category": "quant"},
    {"id": "trading-trade-console", "name": "交易控制台", "path": "/runtime", "category": "trading"}
  ]
}
```

The trade-console Manifest declares `trade.read` only. It must not declare `trade.execute` until a separately reviewed trading plan adds confirmation tokens and broker integration.

- [ ] **Step 3: Generate and build the wrappers**

Use the same URL Adapter package and build contract as Vibe-Research. Do not import Vibe-Trading source code into this repository.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
npm run test:run -w @vibe-visualization/vibe-trading-integration
npm run build -w @vibe-visualization/vibe-trading-integration
```

Expected: three independent HTML files exist.

```bash
git add integrations/vibe-trading package-lock.json
git commit -m "feat: wrap Vibe Trading routes as modules"
```

### Task 4: Add integration health and installation APIs

**Files:**
- Create: `services/api/vibe_visualization_api/integrations/models.py`
- Create: `services/api/vibe_visualization_api/integrations/service.py`
- Create: `services/api/vibe_visualization_api/integrations/routes.py`
- Modify: `services/api/vibe_visualization_api/main.py`
- Test: `services/api/tests/integrations/test_service.py`
- Test: `services/api/tests/integrations/test_routes.py`

- [ ] **Step 1: Write failing health isolation tests**

```py
async def test_trading_failure_does_not_mark_research_offline() -> None:
    service = IntegrationHealthService(client=mock_client)
    statuses = await service.check_all([research, trading])
    assert statuses["vibe-research"].online is True
    assert statuses["vibe-trading"].online is False
```

- [ ] **Step 2: Implement health checks**

Run checks concurrently with per-service timeout 5 seconds. Cache a successful status for 15 seconds. Return:

```json
{
  "id": "vibe-research",
  "online": true,
  "checkedAt": "ISO-8601",
  "latencyMs": 12,
  "detail": null
}
```

Never return upstream stack traces.

- [ ] **Step 3: Implement installation from built manifests**

`POST /api/integrations/{integration_id}/install` reads only manifests from the repository's configured integration directory, creates drafts, and returns their revisions. `POST /api/integrations/{integration_id}/publish` publishes those revisions as one transaction-like operation: if validation fails for one manifest, publish none.

- [ ] **Step 4: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/integrations -v`

Expected: PASS.

```bash
git add services/api/vibe_visualization_api/integrations services/api/tests/integrations services/api/vibe_visualization_api/main.py
git commit -m "feat: install and monitor upstream integrations"
```

### Task 5: Add development and production deployment

**Files:**
- Create: `scripts/dev.sh`
- Create: `scripts/verify.sh`
- Create: `deploy/Dockerfile.api`
- Create: `deploy/Dockerfile.web`
- Create: `deploy/nginx.conf`
- Create: `deploy/docker-compose.yml`
- Create: `deploy/env.example`
- Create: `README.md`

- [ ] **Step 1: Implement a supervised local startup script**

`scripts/dev.sh` must start:

```text
Shell/API reverse-proxy entry: http://127.0.0.1:5888
Standalone module origin:      http://127.0.0.1:5891
Base API:                    http://127.0.0.1:8901
Research web/API:           configurable, defaults 5899/8900
Trading web/API:            configurable, defaults 5900/8899
```

Use PID files under `runtime/pids`, logs under `runtime/logs`, trap EXIT/INT/TERM, and exit if any child stops. Do not start or stop upstream services unless `VIBE_VIS_MANAGE_UPSTREAMS=true`.

- [ ] **Step 2: Implement the web image**

Multi-stage Dockerfile:

1. Node stage installs workspaces and builds Shell, market module, and both integrations.
2. Nginx stage copies Shell to `/usr/share/nginx/shell`, modules to `/usr/share/nginx/modules`, and `deploy/nginx.conf` to `/etc/nginx/conf.d/default.conf`.

Build the Shell with `VITE_MODULE_ORIGIN` set to the dedicated module origin. For local Compose this is `http://localhost:5891`; production may use a separate module subdomain.

- [ ] **Step 3: Implement the API image**

Use `python:3.12-slim`, install `services/api`, run as a non-root user, mount `/data` for SQLite and snapshots, and start:

```text
uvicorn vibe_visualization_api.main:app --host 0.0.0.0 --port 8901
```

- [ ] **Step 4: Configure Nginx routing**

```nginx
server {
  listen 5888;
  root /usr/share/nginx/shell;

  location /api/ {
    proxy_pass http://api:8901;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 180s;
  }

  location / { try_files $uri $uri/ /index.html; }
}

server {
  listen 5891;
  root /usr/share/nginx/modules;

  location /api/ {
    proxy_pass http://api:8901;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 180s;
  }

  location / { try_files $uri $uri/ =404; }
}
```

SSE path `/api/agent/tasks/` must disable proxy buffering with `proxy_buffering off`.

- [ ] **Step 5: Define Docker Compose limits**

Create `web` and `api` services only, but expose two web origins from the Nginx container: Shell on 5888 and modules on 5891. External upstream URLs are environment variables. Set API memory reservation 512 MiB and web 128 MiB; do not start Research or Trading in the same 2-core/2-GB deployment by default.

- [ ] **Step 6: Implement verification script**

`scripts/verify.sh` runs:

```bash
npm test
npm run typecheck
npm run build
services/api/.venv/bin/pytest services/api/tests -q
npm run test:e2e
docker compose -f deploy/docker-compose.yml config
```

- [ ] **Step 7: Document setup and commit deployment**

README must cover architecture, local ports, module package format, Agent/Data Gateway configuration, current upstream adapter strategy, and the statement that real trading is disabled in MVP.

```bash
git add scripts deploy README.md
git commit -m "chore: add deployment and operator workflow"
```

### Task 6: Add CI and upstream compatibility smoke checks

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `scripts/check-upstreams.mjs`
- Test: `scripts/check-upstreams.test.ts`

- [ ] **Step 1: Write a compatibility checker test**

Feed route results where `/daily-review` returns 200, `/stock-data` returns 404, and `/alpha-zoo` returns 200. Assert the report names only `research-stock-analysis` as broken and exits 1.

- [ ] **Step 2: Implement the checker**

The script reads both integration JSON files, issues HEAD then GET fallback with 5-second timeouts, and prints machine-readable JSON plus a concise human summary. It never modifies the upstream repositories.

- [ ] **Step 3: Add GitHub Actions**

CI jobs:

1. `frontend`: Node 22, `npm ci`, test, typecheck, build.
2. `backend`: Python 3.12, install editable test extras, pytest.
3. `e2e`: install Playwright Chromium and run deterministic fake-upstream tests.
4. `docker`: build both images and validate Compose.

Do not call live Vibe upstreams in required CI; live compatibility checks are a manual workflow dispatch.

- [ ] **Step 4: Run CI commands locally and commit**

Run: `scripts/verify.sh`

Expected: exit 0.

```bash
git add .github scripts/check-upstreams.mjs scripts/check-upstreams.test.ts
git commit -m "ci: verify modules and upstream adapters"
```

### Task 7: Perform final security and failure-isolation verification

**Files:**
- Create: `tests/e2e/failure-isolation.spec.ts`
- Create: `tests/e2e/module-security.spec.ts`
- Modify: `docs/security.md`

- [ ] **Step 1: Test failure isolation**

Stop the fake Trading service while Research and market-daily remain online. Verify:

- Shell loads.
- Research wrapper loads.
- Market snapshot loads.
- Trading sidebar item shows offline.
- Agent Gateway remains usable.

- [ ] **Step 2: Test iframe and message security**

Verify:

- A module cannot read `window.parent.document`.
- An event with the wrong source module is rejected.
- An event from the wrong origin is rejected.
- A module cannot invoke undeclared data or Agent capabilities.
- A JavaScript URL Manifest is rejected.

- [ ] **Step 3: Document the security model**

`docs/security.md` must describe trust levels, iframe flags, origin validation, server-only secrets, permission declarations, audit records, disabled real trading, and the reporting process.

- [ ] **Step 4: Run the full verification and commit**

Run: `scripts/verify.sh`

Expected: exit 0.

```bash
git add tests/e2e docs/security.md
git commit -m "test: verify module isolation and security"
```

### Task 8: Create and push GitHub and Gitee repositories

**Files:**
- Create: `scripts/push-remotes.sh`
- Modify: `README.md`

- [ ] **Step 1: Add a deterministic remote-publish script**

```bash
#!/usr/bin/env bash
set -euo pipefail

repo="vibe-visualization"
github_owner="leecyno1"

scripts/verify.sh
git diff --quiet
git diff --cached --quiet

if ! gh repo view "$github_owner/$repo" >/dev/null 2>&1; then
  gh repo create "$github_owner/$repo" --private --description "Persistent HTML module base for humans and agents"
fi

if ! git remote get-url github >/dev/null 2>&1; then
  git remote add github "git@github.com:$github_owner/$repo.git"
fi

: "${GITEE_TOKEN:?Set GITEE_TOKEN to a Gitee personal access token with repository permission}"
gitee_login="$(curl -fsS -H "Authorization: token $GITEE_TOKEN" https://gitee.com/api/v5/user | python3 -c 'import json,sys; print(json.load(sys.stdin)["login"])')"

if ! curl -fsS -H "Authorization: token $GITEE_TOKEN" "https://gitee.com/api/v5/repos/$gitee_login/$repo" >/dev/null 2>&1; then
  curl -fsS -X POST https://gitee.com/api/v5/user/repos \
    -H "Authorization: token $GITEE_TOKEN" \
    --data-urlencode "name=$repo" \
    --data-urlencode "private=true" \
    --data-urlencode "description=Persistent HTML module base for humans and agents" >/dev/null
fi

if ! git remote get-url gitee >/dev/null 2>&1; then
  git remote add gitee "git@gitee.com:$gitee_login/$repo.git"
fi

git push --follow-tags github main
git push --follow-tags gitee main
```

- [ ] **Step 2: Validate credentials without changing repositories**

Run:

```bash
gh auth status
test -n "${GITEE_TOKEN:-}" && curl -fsS -H "Authorization: token $GITEE_TOKEN" https://gitee.com/api/v5/user >/dev/null
ssh -T git@github.com || test $? -eq 1
ssh -T git@gitee.com || test $? -eq 1
```

Expected: GitHub authentication succeeds; Gitee user lookup and SSH authentication succeed. If Gitee credentials are absent, stop here and request only the Gitee token from the user.

- [ ] **Step 3: Commit the publish workflow**

```bash
chmod +x scripts/push-remotes.sh
git add scripts/push-remotes.sh README.md
git commit -m "chore: add dual-remote publish workflow"
```

- [ ] **Step 4: Run final verification**

Run: `scripts/verify.sh`

Expected: exit 0 with a clean worktree.

- [ ] **Step 5: Create private remotes and push**

Run: `scripts/push-remotes.sh`

Expected:

- `git remote -v` lists `github` and `gitee`.
- `gh repo view leecyno1/vibe-visualization` succeeds.
- Gitee repository lookup returns HTTP 200.
- Both remote `main` branches point to the same commit.

- [ ] **Step 6: Record repository links**

Add the resolved GitHub and Gitee links to README, commit, and push both remotes again:

```bash
git add README.md
git commit -m "docs: link GitHub and Gitee mirrors"
git push github main
git push gitee main
```

## Release Completion Gate

The MVP is complete only when:

- Market, four Research wrappers, and three Trading wrappers each have a standalone HTML URL.
- All appear from the dynamic registry and work embedded.
- Upstream failures remain isolated.
- Deterministic events and Agent tasks use separate validated channels.
- Real trade execution remains disabled.
- `scripts/verify.sh` passes.
- GitHub and Gitee private repositories exist and point to the same final commit.

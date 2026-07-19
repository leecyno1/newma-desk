# vibe-visualization Structured Renderer and Market Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the schema-driven HTML renderer, versioned data snapshots, scheduled refresh, and a real daily market module that works standalone and embedded.

**Architecture:** Define a deliberately small View Schema for metrics, tables, ECharts, Markdown, filters, and actions. The market module is an independent Vite HTML application that consumes a published View Schema and the last successful market snapshot through the Module SDK.

**Tech Stack:** React 19, TypeScript, Zod, ECharts 6, FastAPI, SQLite/file snapshots, Vitest, Pytest, Playwright

---

## File Structure

```text
packages/contracts/src/view.ts                 # schema-driven page contract
packages/structured-renderer/src/              # renderer components
services/api/vibe_visualization_api/snapshots/ # atomic snapshot persistence
services/api/vibe_visualization_api/scheduler/ # persisted refresh jobs
services/api/vibe_visualization_api/data_services/market.py
modules/market-daily/                           # standalone HTML module
```

### Task 1: Define the MVP View Schema

**Files:**
- Create: `packages/contracts/src/view.ts`
- Modify: `packages/contracts/src/index.ts`
- Test: `packages/contracts/src/view.test.ts`

- [ ] **Step 1: Write failing schema tests**

```ts
import { describe, expect, it } from "vitest";
import { viewSchema } from "./view";

describe("viewSchema", () => {
  it("accepts metrics, a table, and a chart", () => {
    expect(viewSchema.parse({
      version: "1.0",
      title: "每日股票行情",
      blocks: [
        { id: "breadth", type: "metrics", items: [{ label: "上涨", valuePath: "breadth.up" }] },
        { id: "leaders", type: "table", rowsPath: "leaders", columns: [{ key: "symbol", label: "代码" }] },
        { id: "trend", type: "chart", optionPath: "charts.indexTrend" },
      ],
    }).blocks).toHaveLength(3);
  });

  it("rejects arbitrary HTML and script blocks", () => {
    expect(() => viewSchema.parse({ version: "1.0", title: "x", blocks: [{ id: "x", type: "html", html: "<script/>" }] })).toThrow();
  });
});
```

- [ ] **Step 2: Run the test to verify failure**

Run: `npm run test:run -w @vibe-visualization/contracts`

Expected: FAIL because `view.ts` does not exist.

- [ ] **Step 3: Implement the View Schema**

Define a discriminated union for:

```ts
type ViewBlock =
  | MetricsBlock
  | TableBlock
  | ChartBlock
  | MarkdownBlock
  | FiltersBlock
  | ActionsBlock;
```

Use these exact fields:

```ts
metrics: { id, type: "metrics", title?, items: [{ label, valuePath, format? }] }
table: { id, type: "table", title?, rowsPath, columns: [{ key, label, format?, sortable? }], emptyText? }
chart: { id, type: "chart", title?, optionPath, height? }
markdown: { id, type: "markdown", title?, contentPath }
filters: { id, type: "filters", fields: [{ key, label, input: "text" | "select" | "date", options? }] }
actions: { id, type: "actions", items: [{ id, label, capability, confirmation? }] }
```

Reject unknown block types and limit a page to 100 blocks, a table to 50 columns, and select options to 500 entries.

- [ ] **Step 4: Run contract tests and commit**

Run: `npm run test:run -w @vibe-visualization/contracts && npm run typecheck -w @vibe-visualization/contracts`

Expected: PASS.

```bash
git add packages/contracts
git commit -m "feat: define structured view schema"
```

### Task 2: Build the structured renderer package

**Files:**
- Create: `packages/structured-renderer/package.json`
- Create: `packages/structured-renderer/src/index.ts`
- Create: `packages/structured-renderer/src/StructuredView.tsx`
- Create: `packages/structured-renderer/src/resolvePath.ts`
- Create: `packages/structured-renderer/src/blocks/MetricsBlock.tsx`
- Create: `packages/structured-renderer/src/blocks/TableBlock.tsx`
- Create: `packages/structured-renderer/src/blocks/ChartBlock.tsx`
- Create: `packages/structured-renderer/src/blocks/MarkdownBlock.tsx`
- Create: `packages/structured-renderer/src/blocks/FiltersBlock.tsx`
- Create: `packages/structured-renderer/src/blocks/ActionsBlock.tsx`
- Test: `packages/structured-renderer/src/StructuredView.test.tsx`

- [ ] **Step 1: Write the failing rendering test**

Create the package manifest before running the test:

```json
{
  "name": "@vibe-visualization/structured-renderer",
  "version": "0.1.0",
  "type": "module",
  "exports": "./src/index.ts",
  "scripts": {
    "build": "tsc --noEmit",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@vibe-visualization/contracts": "0.1.0",
    "echarts": "^6.0.0",
    "echarts-for-react": "^3.0.2",
    "react": "^19.0.0",
    "react-markdown": "^9.0.0"
  },
  "devDependencies": {
    "@testing-library/react": "^16.3.0",
    "@testing-library/user-event": "^14.6.0",
    "jsdom": "^27.0.0",
    "typescript": "^5.7.3",
    "vitest": "^4.0.0"
  },
  "peerDependencies": {"react-dom": "^19.0.0"}
}
```

```tsx
it("renders values from data paths and emits a declared action", async () => {
  const onAction = vi.fn();
  render(<StructuredView schema={schema} data={{ breadth: { up: 3210 } }} onAction={onAction} />);
  expect(screen.getByText("3,210")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "解释行情" }));
  expect(onAction).toHaveBeenCalledWith("market.explain", {});
});
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `npm run test:run -w @vibe-visualization/structured-renderer`

Expected: FAIL because the package does not exist.

- [ ] **Step 3: Implement safe path resolution**

```ts
export function resolvePath(root: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((value, key) => {
    if (value === null || typeof value !== "object" || !(key in value)) return undefined;
    return (value as Record<string, unknown>)[key];
  }, root);
}
```

Reject path keys `__proto__`, `prototype`, and `constructor` before resolution.

- [ ] **Step 4: Implement block components**

Requirements:

- Metrics formatting: `number`, `percent`, `currency`, `text`.
- Table sorting remains client-side and never mutates source rows.
- ChartBlock passes only the resolved ECharts option object to `echarts-for-react`.
- MarkdownBlock uses `react-markdown` with raw HTML disabled.
- FiltersBlock sends one complete filter object through `onFiltersChange`.
- ActionsBlock calls only capabilities declared in the schema.
- Unknown or missing paths render `—` or the block's `emptyText`, never throw.

- [ ] **Step 5: Run tests, type checking, and build**

Run:

```bash
npm run test:run -w @vibe-visualization/structured-renderer
npm run typecheck -w @vibe-visualization/structured-renderer
npm run build -w @vibe-visualization/structured-renderer
```

Expected: PASS.

- [ ] **Step 6: Commit the renderer**

```bash
git add packages/structured-renderer package-lock.json
git commit -m "feat: add structured page renderer"
```

### Task 3: Add atomic versioned snapshot storage

**Files:**
- Create: `services/api/vibe_visualization_api/snapshots/models.py`
- Create: `services/api/vibe_visualization_api/snapshots/store.py`
- Create: `services/api/vibe_visualization_api/snapshots/routes.py`
- Modify: `services/api/vibe_visualization_api/main.py`
- Test: `services/api/tests/snapshots/test_store.py`
- Test: `services/api/tests/snapshots/test_routes.py`

- [ ] **Step 1: Write the failing snapshot test**

```py
def test_failed_refresh_does_not_replace_last_success(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    first = store.write_success("market-daily", {"asOf": "2026-07-18", "breadth": {"up": 3000}})
    store.write_failure("market-daily", "upstream timeout")
    latest = store.latest_success("market-daily")
    assert latest.id == first.id
    assert latest.data["asOf"] == "2026-07-18"
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `services/api/.venv/bin/pytest services/api/tests/snapshots/test_store.py -v`

Expected: FAIL because `SnapshotStore` does not exist.

- [ ] **Step 3: Implement atomic file snapshots**

Store each successful snapshot as:

```text
runtime/snapshots/{module_id}/{timestamp}-{uuid}.json
runtime/snapshots/{module_id}/latest.json
```

Write to `.tmp`, `fsync`, then `os.replace`. `latest.json` contains metadata and the relative immutable snapshot filename. Failure records go to SQLite audit state and never replace `latest.json`.

- [ ] **Step 4: Expose snapshot APIs**

```text
GET /api/modules/{module_id}/snapshot
GET /api/modules/{module_id}/snapshots
```

Return HTTP 404 when no successful snapshot exists. Add `Cache-Control: no-store` for `latest`; immutable snapshot URLs may use one-year caching.

- [ ] **Step 5: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/snapshots -v`

Expected: PASS.

```bash
git add services/api/vibe_visualization_api/snapshots services/api/tests/snapshots services/api/vibe_visualization_api/main.py
git commit -m "feat: persist versioned module snapshots"
```

### Task 4: Implement the market data service adapter

**Files:**
- Create: `services/api/vibe_visualization_api/data_services/market.py`
- Create: `services/api/vibe_visualization_api/data_services/normalizers.py`
- Test: `services/api/tests/data_services/test_market.py`
- Create: `integrations/vibe-research/data-service.json`

- [ ] **Step 1: Write failing normalization tests**

```py
def test_market_snapshot_has_stable_shape() -> None:
    snapshot = normalize_market_snapshot(
        overview={"rise": 3120, "fall": 1800, "flat": 120},
        indices=[{"code": "000001", "name": "上证指数", "price": 3520.1, "pct": 0.8}],
        leaders=[{"code": "600519", "name": "贵州茅台", "pct": 3.2}],
        as_of="2026-07-18T15:00:00+08:00",
    )
    assert snapshot["breadth"] == {"up": 3120, "down": 1800, "flat": 120}
    assert snapshot["indices"][0]["symbol"] == "000001"
```

- [ ] **Step 2: Implement a Vibe-Research market client**

Call only these registered endpoints:

```text
GET /api/market/overview
GET /api/indices
GET /api/global/indices
GET /api/market/turnover-top
```

Use concurrent requests with a shared 15-second timeout. Treat the local Research base URL as configuration `VIBE_VIS_RESEARCH_BASE_URL=http://127.0.0.1:8900`.

- [ ] **Step 3: Normalize into the stable snapshot contract**

Return:

```json
{
  "asOf": "ISO-8601",
  "breadth": {"up": 0, "down": 0, "flat": 0},
  "indices": [{"symbol": "", "name": "", "price": 0, "changePct": 0}],
  "globalIndices": [],
  "leaders": [],
  "charts": {"indexTrend": {"xAxis": {}, "yAxis": {}, "series": []}}
}
```

Never expose raw upstream response objects to the module.

- [ ] **Step 4: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/data_services/test_market.py -v`

Expected: PASS with `httpx.MockTransport` and no network access.

```bash
git add services/api/vibe_visualization_api/data_services services/api/tests/data_services integrations/vibe-research
git commit -m "feat: normalize Vibe Research market data"
```

### Task 5: Add persisted scheduled refresh

**Files:**
- Create: `services/api/vibe_visualization_api/scheduler/models.py`
- Create: `services/api/vibe_visualization_api/scheduler/store.py`
- Create: `services/api/vibe_visualization_api/scheduler/service.py`
- Modify: `services/api/vibe_visualization_api/main.py`
- Test: `services/api/tests/scheduler/test_service.py`

- [ ] **Step 1: Write failing scheduler tests**

Test:

- Published scheduled module is due at the expected Asia/Shanghai time.
- Disabled module is skipped.
- Two scheduler ticks cannot run the same module concurrently.
- Failed refresh preserves the previous snapshot and records `next_run_at`.
- Startup recovers jobs left in `running` state for more than 30 minutes.

- [ ] **Step 2: Define job state**

```py
class RefreshJob(BaseModel):
    module_id: str
    cron: str
    timezone: str = "Asia/Shanghai"
    status: Literal["idle", "running", "failed"]
    next_run_at: datetime
    last_success_at: datetime | None = None
    last_error: str | None = None
```

- [ ] **Step 3: Implement the scheduler service**

Poll every 30 seconds. Acquire a SQLite compare-and-swap lease before running. Route `market-daily` refresh to the declared `market.refresh` capability, write a success snapshot, advance the next run, and always release the lease.

Start and stop the scheduler from FastAPI lifespan only when `VIBE_VIS_ENABLE_SCHEDULER=true`.

- [ ] **Step 4: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/scheduler -v`

Expected: PASS.

```bash
git add services/api/vibe_visualization_api/scheduler services/api/tests/scheduler services/api/vibe_visualization_api/main.py
git commit -m "feat: schedule durable module refreshes"
```

### Task 6: Create the standalone daily market HTML module

**Files:**
- Create: `modules/market-daily/package.json`
- Create: `modules/market-daily/module.json`
- Create: `modules/market-daily/index.html`
- Create: `modules/market-daily/src/main.tsx`
- Create: `modules/market-daily/src/view.json`
- Create: `modules/market-daily/src/styles.css`
- Test: `modules/market-daily/src/App.test.tsx`

- [ ] **Step 1: Write the failing module test**

```tsx
it("shows the last snapshot timestamp and refresh action", async () => {
  server.use(http.get("/api/modules/market-daily/snapshot", () => HttpResponse.json(snapshot)));
  render(<MarketDailyApp />);
  expect(await screen.findByText("2026-07-18 15:00")).toBeVisible();
  expect(screen.getByRole("button", { name: "刷新行情" })).toBeVisible();
});
```

- [ ] **Step 2: Create a standalone Vite module package**

Use dependencies:

```json
{
  "@vibe-visualization/contracts": "0.1.0",
  "@vibe-visualization/module-sdk": "0.1.0",
  "@vibe-visualization/structured-renderer": "0.1.0",
  "react": "^19.0.0",
  "react-dom": "^19.0.0"
}
```

Set Vite `base` to `/modules/market-daily/`. The built `dist/index.html` must work without the Web Shell.

- [ ] **Step 3: Add the approved Manifest**

Use the Manifest from the design spec, plus:

```json
"agentCapabilities": ["market.refresh", "market.explain"],
"events": {"emits": ["security.selected"], "accepts": ["date.changed", "security.selected"]}
```

- [ ] **Step 4: Implement snapshot loading and structured rendering**

Load `/api/modules/market-daily/snapshot`. Show a stale-data banner when the snapshot is older than 24 hours. The refresh button invokes `market.refresh`; the explanation button invokes `market.explain` and renders task progress and the final answer below the dashboard.

When a table row is selected, emit:

```ts
bridge.emit("security.selected", { symbol: row.symbol, market: row.market ?? "CN" });
```

- [ ] **Step 5: Run tests and build**

Run:

```bash
npm run test:run -w @vibe-visualization/market-daily
npm run typecheck -w @vibe-visualization/market-daily
npm run build -w @vibe-visualization/market-daily
test -f modules/market-daily/dist/index.html
```

Expected: PASS and the HTML file exists.

- [ ] **Step 6: Publish the module through the API in a local smoke test**

Run the API, POST `modules/market-daily/module.json` to `/api/modules/drafts`, publish the returned revision, and verify `GET /api/modules` contains `market-daily`.

- [ ] **Step 7: Commit the market module**

```bash
git add modules/market-daily package-lock.json
git commit -m "feat: add standalone daily market module"
```

### Task 7: Add the market explanation capability

**Files:**
- Create: `services/api/vibe_visualization_api/agent_gateway/prompts/market_explain.py`
- Modify: `services/api/vibe_visualization_api/agent_gateway/service.py`
- Test: `services/api/tests/agent_gateway/test_market_explain.py`

- [ ] **Step 1: Write the failing prompt-contract test**

```py
def test_market_explain_uses_snapshot_not_raw_upstream_data() -> None:
    prompt = build_market_explain_prompt(snapshot=stable_snapshot, user_prompt="解释上涨原因")
    assert "breadth" in prompt
    assert "rawResponse" not in prompt
    assert len(prompt) < 20000
```

- [ ] **Step 2: Implement a deterministic prompt builder**

Serialize only the normalized snapshot fields, include snapshot `asOf`, state that missing evidence must be acknowledged, and request concise Markdown with observations, possible drivers, and risks. Cap serialized context at 16,000 characters.

- [ ] **Step 3: Route `market.explain`**

Load the latest successful snapshot server-side, build the prompt, and dispatch through the requested/default Agent Adapter. Return HTTP 404 when no snapshot exists.

- [ ] **Step 4: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway/test_market_explain.py -v`

Expected: PASS.

```bash
git add services/api/vibe_visualization_api/agent_gateway services/api/tests/agent_gateway
git commit -m "feat: explain market snapshots through gateway"
```

### Task 8: Verify the complete market workflow end to end

**Files:**
- Create: `tests/e2e/market-daily.spec.ts`
- Modify: `playwright.config.ts`

- [ ] **Step 1: Write the E2E workflow**

The test must:

1. Start a deterministic fake Vibe-Research server.
2. Start the API, Shell, and module static host.
3. Install and publish `market-daily` through the API.
4. Trigger `market.refresh` and wait for a successful snapshot.
5. Open the module directly and verify metrics, table, and chart container.
6. Open it in the Shell and verify the same content.
7. Select a stock and verify `security.selected` reaches the Shell event log.
8. Invoke `market.explain` through the fake Agent Adapter and verify the answer.

- [ ] **Step 2: Run the full market validation**

Run:

```bash
npm test
services/api/.venv/bin/pytest services/api/tests -v
npm run build
npm run test:e2e -- market-daily.spec.ts
```

Expected: all commands exit 0.

- [ ] **Step 3: Commit the market workflow**

```bash
git add tests/e2e playwright.config.ts
git commit -m "test: verify persistent market module workflow"
```

## Market Module Completion Gate

Do not begin upstream integration until:

- View Schema rejects arbitrary HTML and unknown blocks.
- Renderer handles missing/empty data without crashing.
- Snapshot writes are atomic and failed refreshes retain the last success.
- Scheduler recovery and concurrency tests pass.
- Market module builds to standalone HTML and works inside the Shell.
- Market selection emits a validated deterministic event.
- Market explanation goes through the Agent Gateway using normalized snapshot data.

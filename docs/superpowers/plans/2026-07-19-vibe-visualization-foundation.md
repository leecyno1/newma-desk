# vibe-visualization Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the independent repository foundation, versioned Module Contract, SQLite-backed registry lifecycle, dynamic Web Shell, and sandboxed HTML module bridge.

**Architecture:** Use npm workspaces for the React/TypeScript frontend packages and one FastAPI service for registry APIs. Modules remain standalone HTML applications loaded through a sandboxed iframe; the Shell discovers them from the registry instead of hard-coded navigation.

**Tech Stack:** React 19, TypeScript 5.7+, Vite 6+, Zod 3, FastAPI, Pydantic 2, SQLite, Vitest, Pytest, Playwright

---

## File Structure

Create these units with one responsibility each:

```text
package.json                              # workspace scripts
tsconfig.base.json                        # shared TypeScript settings
.gitignore                                # generated and secret files
packages/contracts/                       # versioned Manifest and Event schemas
packages/module-sdk/                      # browser bridge used by standalone modules
apps/shell/                               # dynamic sidebar and iframe host
services/api/pyproject.toml               # Python package and test dependencies
services/api/vibe_visualization_api/      # FastAPI application
services/api/vibe_visualization_api/control_plane/
tests/e2e/                                # direct and embedded browser tests
```

### Task 1: Initialize the workspace toolchain

**Files:**
- Create: `.gitignore`
- Create: `package.json`
- Create: `tsconfig.base.json`
- Create: `services/api/pyproject.toml`
- Create: `services/api/vibe_visualization_api/__init__.py`

- [ ] **Step 1: Add the repository ignore rules**

```gitignore
node_modules/
dist/
coverage/
.vite/
.venv/
__pycache__/
.pytest_cache/
*.pyc
*.db
*.db-shm
*.db-wal
.env
.env.*
!.env.example
runtime/
playwright-report/
test-results/
```

- [ ] **Step 2: Add the npm workspace manifest**

```json
{
  "name": "vibe-visualization",
  "private": true,
  "version": "0.1.0",
  "workspaces": ["apps/*", "packages/*", "modules/*", "integrations/*"],
  "scripts": {
    "build": "npm run build --workspaces --if-present",
    "test": "npm run test:run --workspaces --if-present",
    "typecheck": "npm run typecheck --workspaces --if-present",
    "dev:shell": "npm run dev -w @vibe-visualization/shell"
  },
  "engines": {
    "node": ">=22",
    "npm": ">=10"
  }
}
```

- [ ] **Step 3: Add shared TypeScript settings**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  }
}
```

- [ ] **Step 4: Add the Python project manifest**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vibe-visualization-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "croniter>=6,<7",
  "fastapi>=0.116,<1",
  "httpx>=0.28,<1",
  "pydantic>=2.11,<3",
  "pydantic-settings>=2.10,<3",
  "python-multipart>=0.0.20,<1",
  "uvicorn[standard]>=0.35,<1"
]

[project.optional-dependencies]
test = ["pytest>=8.4,<9", "pytest-asyncio>=1.1,<2"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 5: Install dependencies and verify both toolchains**

Run:

```bash
npm install
python3 -m venv services/api/.venv
services/api/.venv/bin/pip install -e 'services/api[test]'
npm --version
services/api/.venv/bin/python -c 'import fastapi, pydantic; print("python-ready")'
```

Expected: npm prints version 10 or newer and Python prints `python-ready`.

- [ ] **Step 6: Commit the workspace foundation**

```bash
git add .gitignore package.json package-lock.json tsconfig.base.json services/api
git commit -m "chore: initialize vibe-visualization workspace"
```

### Task 2: Define and validate the Module Manifest contract

**Files:**
- Create: `packages/contracts/package.json`
- Create: `packages/contracts/tsconfig.json`
- Create: `packages/contracts/src/module.ts`
- Create: `packages/contracts/src/event.ts`
- Create: `packages/contracts/src/index.ts`
- Test: `packages/contracts/src/module.test.ts`
- Test: `packages/contracts/src/event.test.ts`

- [ ] **Step 1: Create the contracts package manifest**

```json
{
  "name": "@vibe-visualization/contracts",
  "version": "0.1.0",
  "type": "module",
  "exports": "./src/index.ts",
  "scripts": {
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {"zod": "^3.25.76"},
  "devDependencies": {"typescript": "^5.7.3", "vitest": "^4.0.0"}
}
```

- [ ] **Step 2: Write failing Manifest tests**

```ts
import { describe, expect, it } from "vitest";
import { moduleManifestSchema } from "./module";

const valid = {
  schemaVersion: "1.0",
  id: "market-daily",
  name: "每日股票行情",
  version: "0.1.0",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
  permissions: ["market.read"],
  dataServices: ["market-data"],
  agentCapabilities: ["market.refresh"],
  events: { emits: ["security.selected"], accepts: ["date.changed"] }
};

describe("moduleManifestSchema", () => {
  it("accepts a stable standalone module", () => {
    expect(moduleManifestSchema.parse(valid).id).toBe("market-daily");
  });

  it("rejects traversal and javascript URLs", () => {
    expect(() => moduleManifestSchema.parse({ ...valid, entry: { type: "static", url: "../secret" } })).toThrow();
    expect(() => moduleManifestSchema.parse({ ...valid, entry: { type: "external", url: "javascript:alert(1)" } })).toThrow();
  });
});
```

- [ ] **Step 3: Run the test and confirm failure**

Run: `npm install && npm run test:run -w @vibe-visualization/contracts`

Expected: FAIL because `src/module.ts` does not exist.

- [ ] **Step 4: Implement the Manifest schema**

```ts
import { z } from "zod";

const safeRelativeUrl = z.string().refine(
  (value) => value.startsWith("/") && !value.includes(".."),
  "local module URL must be an absolute safe path",
);
const safeExternalUrl = z.string().url().refine(
  (value) => ["http:", "https:"].includes(new URL(value).protocol),
  "external URL must use http or https",
);

export const moduleEntrySchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("structured"), url: safeRelativeUrl }),
  z.object({ type: z.literal("static"), url: safeRelativeUrl }),
  z.object({ type: z.literal("external"), url: safeExternalUrl }),
]);

export const moduleManifestSchema = z.object({
  schemaVersion: z.literal("1.0"),
  id: z.string().regex(/^[a-z][a-z0-9-]{2,63}$/),
  name: z.string().min(1).max(80),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  category: z.string().regex(/^[a-z][a-z0-9-]{1,31}$/),
  entry: moduleEntrySchema,
  icon: z.string().optional(),
  permissions: z.array(z.string()).default([]),
  dataServices: z.array(z.string()).default([]),
  agentCapabilities: z.array(z.string()).default([]),
  events: z.object({
    emits: z.array(z.string()).default([]),
    accepts: z.array(z.string()).default([]),
  }).default({ emits: [], accepts: [] }),
  refresh: z.object({
    mode: z.enum(["manual", "schedule"]),
    cron: z.string().optional(),
  }).optional(),
});

export type ModuleManifest = z.infer<typeof moduleManifestSchema>;
```

- [ ] **Step 5: Write failing Event Envelope tests**

```ts
import { describe, expect, it } from "vitest";
import { moduleEventSchema } from "./event";

describe("moduleEventSchema", () => {
  it("accepts a namespaced event", () => {
    const result = moduleEventSchema.parse({
      version: "1.0",
      event: "security.selected",
      source: "market-daily",
      target: "stock-analysis",
      traceId: "trace-1",
      payload: { symbol: "600519", market: "CN" },
    });
    expect(result.event).toBe("security.selected");
  });

  it("rejects unversioned messages", () => {
    expect(() => moduleEventSchema.parse({ event: "security.selected" })).toThrow();
  });
});
```

- [ ] **Step 6: Implement Event Envelope and exports**

```ts
// packages/contracts/src/event.ts
import { z } from "zod";

export const moduleEventSchema = z.object({
  version: z.literal("1.0"),
  event: z.string().regex(/^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/),
  source: z.string().min(1),
  target: z.string().min(1).optional(),
  traceId: z.string().min(1),
  payload: z.record(z.unknown()),
});

export type ModuleEvent = z.infer<typeof moduleEventSchema>;

// packages/contracts/src/index.ts
export * from "./event";
export * from "./module";
```

- [ ] **Step 7: Run tests and type checking**

Run:

```bash
npm run test:run -w @vibe-visualization/contracts
npm run typecheck -w @vibe-visualization/contracts
```

Expected: all tests PASS and TypeScript exits 0.

- [ ] **Step 8: Commit the contracts**

```bash
git add packages/contracts package-lock.json
git commit -m "feat: define module and event contracts"
```

### Task 3: Create the FastAPI application and health boundary

**Files:**
- Create: `services/api/vibe_visualization_api/config.py`
- Create: `services/api/vibe_visualization_api/main.py`
- Create: `services/api/tests/conftest.py`
- Test: `services/api/tests/test_health.py`

- [ ] **Step 1: Write the failing health test**

```py
from fastapi.testclient import TestClient

from vibe_visualization_api.main import app


def test_health_reports_service_identity() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "vibe-visualization-api", "version": "0.1.0"}
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `services/api/.venv/bin/pytest services/api/tests/test_health.py -v`

Expected: FAIL because `vibe_visualization_api.main` does not exist.

- [ ] **Step 3: Implement settings and the health endpoint**

```py
# services/api/vibe_visualization_api/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIBE_VIS_", env_file=".env")
    runtime_dir: Path = Path("runtime")
    database_path: Path = Path("runtime/vibe-visualization.db")
    allowed_origins: str = "http://127.0.0.1:5888,http://127.0.0.1:5891"

    def origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()


# services/api/vibe_visualization_api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

app = FastAPI(title="vibe-visualization API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origin_list(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "vibe-visualization-api", "version": "0.1.0"}
```

Add a shared test client fixture:

```py
# services/api/tests/conftest.py
import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 4: Run the test**

Run: `services/api/.venv/bin/pytest services/api/tests/test_health.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the API boundary**

```bash
git add services/api
git commit -m "feat: add base API health boundary"
```

### Task 4: Implement the SQLite module registry

**Files:**
- Create: `services/api/vibe_visualization_api/control_plane/models.py`
- Create: `services/api/vibe_visualization_api/control_plane/database.py`
- Create: `services/api/vibe_visualization_api/control_plane/repository.py`
- Test: `services/api/tests/control_plane/test_repository.py`

- [ ] **Step 1: Write the failing registry lifecycle test**

```py
from vibe_visualization_api.control_plane.repository import ModuleRepository


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "structured", "url": "/modules/market-daily/"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": [],
    "events": {"emits": [], "accepts": []},
}


def test_draft_publish_and_rollback(tmp_path) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")
    draft = repo.create_draft(MANIFEST)
    assert draft.status == "draft"

    published = repo.publish("market-daily", draft.revision)
    assert published.status == "published"

    second = repo.create_draft({**MANIFEST, "version": "0.2.0"})
    repo.publish("market-daily", second.revision)
    rolled_back = repo.rollback("market-daily", draft.revision)
    assert rolled_back.manifest["version"] == "0.1.0"
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `services/api/.venv/bin/pytest services/api/tests/control_plane/test_repository.py -v`

Expected: FAIL because `ModuleRepository` does not exist.

- [ ] **Step 3: Define the stored module model**

```py
from dataclasses import dataclass
from typing import Any, Literal

ModuleStatus = Literal["draft", "published", "disabled"]


@dataclass(frozen=True)
class StoredModule:
    module_id: str
    revision: int
    status: ModuleStatus
    manifest: dict[str, Any]
    created_at: str
```

- [ ] **Step 4: Implement database initialization**

```py
import sqlite3
from pathlib import Path


DDL = """
CREATE TABLE IF NOT EXISTS module_revisions (
  module_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('draft','published','disabled')),
  manifest_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (module_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_module_status ON module_revisions(module_id, status);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  module_id TEXT,
  revision INTEGER,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(DDL)
    return connection
```

- [ ] **Step 5: Implement draft, publish, list, disable, and rollback**

Implement `ModuleRepository` with these exact public methods:

```py
class ModuleRepository:
    def __init__(self, database_path: Path): ...
    def create_draft(self, manifest: dict[str, object]) -> StoredModule: ...
    def publish(self, module_id: str, revision: int) -> StoredModule: ...
    def list_published(self) -> list[StoredModule]: ...
    def disable(self, module_id: str) -> StoredModule: ...
    def rollback(self, module_id: str, revision: int) -> StoredModule: ...
```

Use `json.dumps(..., ensure_ascii=False, sort_keys=True)`, UTC ISO timestamps, and `BEGIN IMMEDIATE` for revision allocation. Publishing must change every prior `published` row for the same module to `disabled` in the same transaction.
Every draft, publish, disable, rollback, import, and export operation must append an `audit_events` row in the same transaction as its state change.

- [ ] **Step 6: Run the repository test**

Run: `services/api/.venv/bin/pytest services/api/tests/control_plane/test_repository.py -v`

Expected: PASS.

- [ ] **Step 7: Commit the registry storage**

```bash
git add services/api/vibe_visualization_api/control_plane services/api/tests/control_plane
git commit -m "feat: add versioned module registry"
```

### Task 5: Expose the module lifecycle API

**Files:**
- Create: `services/api/vibe_visualization_api/control_plane/schemas.py`
- Create: `services/api/vibe_visualization_api/control_plane/routes.py`
- Modify: `services/api/vibe_visualization_api/main.py`
- Create: `services/api/tests/control_plane/conftest.py`
- Test: `services/api/tests/control_plane/test_routes.py`

- [ ] **Step 1: Write the failing route test**

```py
MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "structured", "url": "/modules/market-daily/"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": [],
    "events": {"emits": [], "accepts": []},
}


def test_module_must_be_published_before_sidebar_listing(client) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    assert client.get("/api/modules").json() == []

    response = client.post(f"/api/modules/market-daily/revisions/{draft['revision']}/publish")
    assert response.status_code == 200
    assert client.get("/api/modules").json()[0]["manifest"]["id"] == "market-daily"
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `services/api/.venv/bin/pytest services/api/tests/control_plane/test_routes.py -v`

Expected: FAIL with 404 for `/api/modules/drafts`.

- [ ] **Step 3: Implement request and response schemas**

Create Pydantic models matching the TypeScript Manifest fields exactly. Add validators that reject `..`, non-HTTP external URLs, invalid semantic versions, and scheduled refresh without a cron expression.

- [ ] **Step 4: Implement lifecycle routes**

```py
router = APIRouter(prefix="/api/modules", tags=["modules"])

@router.get("")
def list_modules(repository: ModuleRepository = Depends(get_repository)): ...

@router.post("/drafts", status_code=201)
def create_draft(manifest: ModuleManifestIn, repository: ModuleRepository = Depends(get_repository)): ...

@router.post("/{module_id}/revisions/{revision}/publish")
def publish(module_id: str, revision: int, repository: ModuleRepository = Depends(get_repository)): ...

@router.post("/{module_id}/disable")
def disable(module_id: str, repository: ModuleRepository = Depends(get_repository)): ...

@router.post("/{module_id}/revisions/{revision}/rollback")
def rollback(module_id: str, revision: int, repository: ModuleRepository = Depends(get_repository)): ...

@router.get("/{module_id}/revisions/{revision}")
def get_revision(module_id: str, revision: int, repository: ModuleRepository = Depends(get_repository)): ...
```

Map missing revisions to HTTP 404 and invalid state transitions to HTTP 409.

In `services/api/tests/control_plane/conftest.py`, override `get_repository` with a `ModuleRepository(tmp_path / "registry.db")` for each test and clear the dependency override after yielding the client. This prevents tests from touching `runtime/vibe-visualization.db`.

- [ ] **Step 5: Mount the router and run tests**

Run:

```bash
services/api/.venv/bin/pytest services/api/tests/control_plane -v
```

Expected: all control-plane tests PASS.

- [ ] **Step 6: Commit the lifecycle API**

```bash
git add services/api/vibe_visualization_api services/api/tests/control_plane
git commit -m "feat: expose module lifecycle API"
```

### Task 6: Build the dynamic Web Shell

**Files:**
- Create: `apps/shell/package.json`
- Create: `apps/shell/index.html`
- Create: `apps/shell/tsconfig.json`
- Create: `apps/shell/vite.config.ts`
- Create: `apps/shell/src/main.tsx`
- Create: `apps/shell/src/App.tsx`
- Create: `apps/shell/src/api/modules.ts`
- Create: `apps/shell/src/components/Sidebar.tsx`
- Create: `apps/shell/src/components/ModuleFrame.tsx`
- Create: `apps/shell/src/styles.css`
- Create: `apps/shell/src/test/setup.ts`
- Test: `apps/shell/src/App.test.tsx`

- [ ] **Step 1: Create the shell package**

Use dependencies `@vibe-visualization/contracts`, `lucide-react`, `react`, `react-dom`, and dev dependencies `@testing-library/jest-dom`, `@testing-library/react`, `@testing-library/user-event`, `@vitejs/plugin-react`, `jsdom`, `msw`, `typescript`, `vite`, `vitest`.

Set scripts:

```json
{
  "dev": "vite",
  "build": "tsc -b && vite build",
  "test:run": "vitest run",
  "typecheck": "tsc --noEmit"
}
```

Configure Vite so the browser has one local entry URL while services remain separate:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8901",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

- [ ] **Step 2: Write the failing sidebar test**

```tsx
it("renders registry modules and opens the selected URL", async () => {
  server.use(http.get("/api/modules", () => HttpResponse.json([publishedMarketModule])));
  render(<App />);
  expect(await screen.findByRole("button", { name: "每日股票行情" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "每日股票行情" }));
  expect(screen.getByTitle("每日股票行情")).toHaveAttribute("src", "http://127.0.0.1:5891/modules/market-daily/");
});
```

- [ ] **Step 3: Run the shell test to confirm failure**

Run: `npm run test:run -w @vibe-visualization/shell`

Expected: FAIL because `App` does not exist.

- [ ] **Step 4: Implement registry fetching**

```ts
import { moduleManifestSchema, type ModuleManifest } from "@vibe-visualization/contracts";

export async function listModules(): Promise<ModuleManifest[]> {
  const response = await fetch("/api/modules");
  if (!response.ok) throw new Error(`module registry returned ${response.status}`);
  const rows = await response.json();
  return rows.map((row: { manifest: unknown }) => moduleManifestSchema.parse(row.manifest));
}
```

- [ ] **Step 5: Implement App, Sidebar, and ModuleFrame**

The Shell must:

- Load modules once on startup and expose retry after failure.
- Group buttons by `category`.
- Store the selected module ID in the `module` query parameter and localStorage.
- Render an offline/error card without removing other modules.
- Provide an “独立打开” link using the same manifest URL.
- Support `?preview={module_id}@{revision}` by loading the exact draft revision from the revision API, showing a persistent “预览，尚未发布” banner, and never adding that draft to the normal sidebar.
- Resolve `structured` and `static` entry paths against `VITE_MODULE_ORIGIN` (default `http://127.0.0.1:5891`). External entries keep their absolute URL. Reject a local module origin equal to `window.location.origin` so `allow-same-origin` never gives a module access to the Shell origin.

`ModuleFrame` must render:

```tsx
<iframe
  title={manifest.name}
  src={resolveModuleUrl(manifest.entry, import.meta.env.VITE_MODULE_ORIGIN)}
  sandbox="allow-scripts allow-forms allow-downloads allow-popups allow-same-origin"
  referrerPolicy="no-referrer"
  allow="clipboard-read; clipboard-write; fullscreen"
/>
```

`allow-same-origin` is permitted only because static/structured modules are served from the dedicated module origin. Add a unit test that rejects a module origin matching the Shell origin.

- [ ] **Step 6: Run shell tests, type checking, and build**

Run:

```bash
npm run test:run -w @vibe-visualization/shell
npm run typecheck -w @vibe-visualization/shell
npm run build -w @vibe-visualization/shell
```

Expected: tests PASS and `apps/shell/dist/index.html` exists.

- [ ] **Step 7: Commit the dynamic shell**

```bash
git add apps/shell package-lock.json
git commit -m "feat: add registry-driven web shell"
```

### Task 7: Implement the browser Module SDK and secure bridge

**Files:**
- Create: `packages/module-sdk/package.json`
- Create: `packages/module-sdk/src/index.ts`
- Create: `packages/module-sdk/src/bridge.ts`
- Test: `packages/module-sdk/src/bridge.test.ts`
- Modify: `apps/shell/src/components/ModuleFrame.tsx`
- Test: `apps/shell/src/components/ModuleFrame.test.tsx`
- Create: `apps/shell/src/events/ShellEventBus.ts`
- Test: `apps/shell/src/events/ShellEventBus.test.ts`

- [ ] **Step 1: Write failing bridge tests**

```ts
it("emits a versioned event to the parent", () => {
  const postMessage = vi.spyOn(window.parent, "postMessage");
  const bridge = createModuleBridge({ moduleId: "market-daily", parentOrigin: "http://localhost:5888" });
  bridge.emit("security.selected", { symbol: "600519" });
  expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({
    version: "1.0",
    event: "security.selected",
    source: "market-daily",
  }), "http://localhost:5888");
});
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `npm run test:run -w @vibe-visualization/module-sdk`

Expected: FAIL because the bridge package does not exist.

- [ ] **Step 3: Implement the bridge**

```ts
export function createModuleBridge(config: { moduleId: string; parentOrigin: string }) {
  const channel = window.parent === window ? new BroadcastChannel("vibe-visualization-events") : null;
  return {
    emit(event: string, payload: Record<string, unknown>, target?: string) {
      const envelope = moduleEventSchema.parse({
        version: "1.0",
        event,
        source: config.moduleId,
        target,
        traceId: crypto.randomUUID(),
        payload,
      });
      if (channel) channel.postMessage(envelope);
      else window.parent.postMessage(envelope, config.parentOrigin);
    },
    subscribe(handler: (event: ModuleEvent) => void) {
      const listener = (message: MessageEvent) => {
        if (message.origin !== config.parentOrigin) return;
        const parsed = moduleEventSchema.safeParse(message.data);
        if (parsed.success && (!parsed.data.target || parsed.data.target === config.moduleId)) handler(parsed.data);
      };
      window.addEventListener("message", listener);
      const channelListener = (message: MessageEvent) => {
        const parsed = moduleEventSchema.safeParse(message.data);
        if (parsed.success && (!parsed.data.target || parsed.data.target === config.moduleId)) handler(parsed.data);
      };
      channel?.addEventListener("message", channelListener);
      return () => {
        window.removeEventListener("message", listener);
        channel?.removeEventListener("message", channelListener);
        channel?.close();
      };
    },
  };
}
```

- [ ] **Step 4: Add Shell-side message validation**

`ModuleFrame` must accept messages only when:

- `event.source` equals the currently loaded manifest ID.
- `event.event` appears in `manifest.events.emits`.
- `MessageEvent.source` equals the iframe content window.
- External origins match the manifest URL origin.

Valid messages are forwarded to a Shell event dispatcher; invalid messages are ignored and recorded with `console.warn` in development.

Implement `ShellEventBus` as a registry of mounted module windows. When an event has `target`, forward it only to that module after verifying the target Manifest declares the event in `events.accepts`; broadcast events go only to modules that declare the event. Also publish validated events to `BroadcastChannel("vibe-visualization-events")` so separately opened same-origin module pages can participate without an Agent call.

- [ ] **Step 5: Run SDK and Shell tests**

Run:

```bash
npm run test:run -w @vibe-visualization/module-sdk
npm run test:run -w @vibe-visualization/shell
npm run typecheck
```

Expected: all tests PASS.

- [ ] **Step 6: Commit the module bridge**

```bash
git add packages/module-sdk apps/shell package-lock.json
git commit -m "feat: add secure module bridge"
```

### Task 8: Add direct-versus-embedded end-to-end coverage

**Files:**
- Create: `playwright.config.ts`
- Create: `tests/e2e/fixtures/modules/demo/index.html`
- Create: `tests/e2e/module-host.spec.ts`
- Modify: `package.json`

- [ ] **Step 1: Add Playwright and the root test script**

Install: `npm install -D @playwright/test`

Add root script:

```json
"test:e2e": "playwright test"
```

- [ ] **Step 2: Write the failing E2E test**

```ts
test("the same module works directly and inside the shell", async ({ page }) => {
  await page.goto("http://127.0.0.1:5891/modules/demo/");
  await expect(page.getByRole("heading", { name: "Demo Module" })).toBeVisible();

  await page.goto("http://127.0.0.1:5888/?module=demo");
  const frame = page.frameLocator('iframe[title="Demo Module"]');
  await expect(frame.getByRole("heading", { name: "Demo Module" })).toBeVisible();
});
```

- [ ] **Step 3: Configure Playwright web servers**

Configure three commands in `playwright.config.ts`:

- API: `services/api/.venv/bin/uvicorn vibe_visualization_api.main:app --app-dir services/api --port 8901`
- Shell: `npm run dev -w @vibe-visualization/shell -- --host 127.0.0.1 --port 5888`
- Demo static host: `python3 -m http.server 5891 --bind 127.0.0.1 --directory tests/e2e/fixtures`

Set `VITE_MODULE_ORIGIN=http://127.0.0.1:5891` for the Shell web server and `VIBE_VIS_ALLOWED_ORIGINS=http://127.0.0.1:5888,http://127.0.0.1:5891` for the API web server.

- [ ] **Step 4: Seed the demo module before the test**

Use Playwright `globalSetup` to POST the demo Manifest and publish its returned revision. Do not write directly to SQLite from the browser test.

- [ ] **Step 5: Run all foundation checks**

Run:

```bash
npm test
services/api/.venv/bin/pytest services/api/tests -v
npm run build
npm run test:e2e
```

Expected: all commands exit 0 and the E2E test passes in direct and embedded modes.

- [ ] **Step 6: Commit foundation E2E coverage**

```bash
git add package.json package-lock.json playwright.config.ts tests/e2e
git commit -m "test: cover direct and embedded modules"
```

### Task 9: Add safe module package import and export

**Files:**
- Create: `services/api/vibe_visualization_api/control_plane/packages.py`
- Modify: `services/api/vibe_visualization_api/control_plane/routes.py`
- Test: `services/api/tests/control_plane/test_packages.py`

- [ ] **Step 1: Write failing package security tests**

```py
def test_import_creates_a_draft_and_never_auto_publishes(client, valid_module_zip) -> None:
    response = client.post("/api/modules/import", files={"package": ("market.zip", valid_module_zip, "application/zip")})
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert client.get("/api/modules").json() == []


def test_import_rejects_path_traversal(client, traversal_zip) -> None:
    response = client.post("/api/modules/import", files={"package": ("bad.zip", traversal_zip, "application/zip")})
    assert response.status_code == 400
    assert response.json()["detail"] == "module package contains an unsafe path"
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `services/api/.venv/bin/pytest services/api/tests/control_plane/test_packages.py -v`

Expected: FAIL because `/api/modules/import` does not exist.

- [ ] **Step 3: Implement safe package extraction**

```py
MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_FILES = 2000
ALLOWED_ROOT_FILES = {"module.json"}


def safe_member_path(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name
```

Reject archives over the byte/file limits, symlinks, traversal, missing `module.json`, missing `dist/index.html` for non-external modules, and files outside `module.json` or `dist/`. Validate the Manifest before extraction, extract into a temporary directory, then atomically move to `runtime/module-packages/{module_id}/{revision}/`.

- [ ] **Step 4: Implement import and export routes**

```text
POST /api/modules/import
GET  /api/modules/{module_id}/revisions/{revision}/export
```

Import always creates a draft. Export returns a deterministic ZIP containing `module.json` and the selected revision's `dist/`, with `Content-Disposition: attachment` and no Secret values.

- [ ] **Step 5: Run package and lifecycle tests**

Run:

```bash
services/api/.venv/bin/pytest services/api/tests/control_plane -v
```

Expected: PASS.

- [ ] **Step 6: Commit module portability**

```bash
git add services/api/vibe_visualization_api/control_plane services/api/tests/control_plane
git commit -m "feat: import and export module packages"
```

## Foundation Completion Gate

Do not start the Gateway plan until all of the following are true:

- `npm test`, `npm run typecheck`, and `npm run build` pass.
- API unit tests pass.
- A module can move from draft to published and appears in the sidebar.
- The same HTML page works directly and inside the sandboxed Shell.
- An invalid iframe event is rejected.
- A draft can be previewed without appearing in the published sidebar.
- Module packages import as drafts, export deterministically, and reject traversal archives.

import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  loadModStore,
  manifestsEqual,
  registerStoreMods,
  standardizeStoreMods,
} from "../../scripts/lib/mod-store.mjs";

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const HTTP_SUITE_DESCRIPTOR = {
  schemaVersion: "1.0",
  id: "example-suite",
  name: "示例项目",
  description: "通过 HTTP 自动发现的示例 Mod Suite。",
  version: "0.1.0",
  publisher: "Example",
  upstream: "https://github.com/example/project",
  tags: ["Suite"],
  runtime: {
    type: "external",
    baseUrlEnv: "NEWMA_DOCK_EXAMPLE_WEB_URL",
    defaultBaseUrl: "http://127.0.0.1:4312",
  },
  manifest: {
    category: "research",
    navigation: {
      groupLabel: "研究",
      groupOrder: 10,
      itemOrder: 100,
      directory: { id: "example-suite", label: "示例项目", order: 10 },
      icon: "research",
    },
    permissions: [],
    dataServices: [],
    agentCapabilities: [],
    events: { emits: [], accepts: [] },
  },
  pages: [{
    id: "example-overview",
    name: "项目总览",
    description: "自动发现的项目总览页面。",
    route: "/overview",
    navigation: { itemOrder: 10, label: "总览" },
    defaultInstall: true,
  }],
};

async function temporaryStore(catalog, callback) {
  const directory = await mkdtemp(join(tmpdir(), "newma-dock-store-"));
  const storePath = join(directory, "store.json");
  try {
    await writeFile(storePath, JSON.stringify(catalog), "utf8");
    return await callback(pathToFileURL(storePath));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test("validates the project Mod store and includes Research and Trading by default", async () => {
  const store = await loadModStore({
    env: {
      NEWMA_DOCK_INVESTMENT_WEB_URL: "https://investment.example",
      NEWMA_DOCK_TRADING_WEB_URL: "https://trading.example",
      NEWMA_DOCK_DEEPSEE_WEB_URL: "https://deepsee.example",
      NEWMA_DOCK_SEVEN_CYCLE_WEB_URL: "https://cycle.example",
      NEWMA_DOCK_INSTOCK_WEB_URL: "https://instock.example",
      NEWMA_DOCK_ORCHESTRA_WEB_URL: "https://orchestra.example",
    },
  });
  const defaults = store.mods.filter((mod) => mod.defaultInstall);

  assert.equal(store.mods.length, 42);
  assert.deepEqual(store.suites.map((suite) => suite.id), [
    "deepsee-suite",
    "orchestra-suite",
  ]);
  assert.deepEqual(store.retiredMods, ["investment-settings", "quant-agent"]);
  assert.deepEqual(defaults.map((mod) => mod.id), [
    "daily-review",
    "alpha-lab",
    "news-radar",
    "watchlist",
    "portfolio-brief",
    "stock-research",
    "industry-map",
    "research-library",
    "research-notes",
    "quant-overview",
    "backtest-lab",
    "factor-correlation",
    "instock-czsc",
    "instock-rotation",
    "trade-desk",
    "trading-settings",
    "orchestra-committee",
    "orchestra-history",
    "orchestra-reports",
    "orchestra-agents",
    "orchestra-skills",
    "orchestra-data",
    "orchestra-workspace",
    "orchestra-settings",
  ]);
  assert.equal(
    store.mods.find((mod) => mod.id === "daily-review").manifest.entry.url,
    "https://investment.example/mod-runtime/research/daily-review",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "alpha-lab").manifest.entry.url,
    "https://trading.example/mod-runtime/trading/alpha-zoo",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "market-daily").manifest.entry.url,
    "/mods/market-daily/",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "multi-timeframe").manifest.entry.url,
    "/mods/market-daily/?workspace=multi-timeframe",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "deepsee-wechat").manifest.entry.url,
    "https://deepsee.example/embed/message-list",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "seven-cycle-research").manifest.entry.url,
    "https://cycle.example/",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "instock-czsc").manifest.entry.url,
    "https://instock.example/mods/czsc",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "instock-czsc").manifest.actions["analysis.czsc"].binding.capability,
    "analysis.czsc",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "instock-rotation").manifest.actions["analysis.rotation"].binding.capability,
    "analysis.rotation",
  );
  const orchestraRoutes = {
    "orchestra-committee": "committee",
    "orchestra-history": "history",
    "orchestra-reports": "reports",
    "orchestra-agents": "agents",
    "orchestra-skills": "skills",
    "orchestra-data": "data",
    "orchestra-workspace": "workspace",
    "orchestra-settings": "settings",
  };
  for (const [modId, workspace] of Object.entries(orchestraRoutes)) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(
      mod.manifest.entry.url,
      `https://orchestra.example/?workspace=${workspace}`,
    );
    assert.equal(mod.manifest.navigation.directory.id, "orchestra-suite");
    assert.equal(mod.suiteId, "orchestra-suite");
  }
  assert.equal(
    store.mods.filter((mod) => mod.id.startsWith("deepsee-")).length,
    11,
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "deepsee-overview").suiteId,
    "deepsee-suite",
  );
  assert.deepEqual(
    store.mods.find((mod) => mod.id === "deepsee-ai-insights").manifest.permissions,
    ["deepsee.read", "deepsee.ai"],
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "deepsee-settings").manifest.navigation.icon,
    "settings",
  );
});

test("rejects unsafe configured external Mod origins", async () => {
  await assert.rejects(
    loadModStore({
      env: { NEWMA_DOCK_INVESTMENT_WEB_URL: "https://user:pass@example.com" },
    }),
    /must be an HTTP\(S\) origin/,
  );
});

test("discovers a Mod Suite from the standard HTTP well-known endpoint", async () => {
  const catalog = {
    schemaVersion: "1.0",
    id: "http-discovery-store",
    name: "HTTP Discovery Store",
    git: {},
    mods: [],
    suites: [{
      id: "example-suite",
      defaultInstall: false,
      discovery: {
        type: "http",
        baseUrlEnv: "NEWMA_DOCK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
      },
    }],
  };
  const calls = [];

  await temporaryStore(catalog, async (storeUrl) => {
    const store = await loadModStore({
      storeUrl,
      env: { NEWMA_DOCK_EXAMPLE_WEB_URL: "https://suite.example" },
      fetchImpl: async (url, init) => {
        calls.push({ url: String(url), init });
        return response(HTTP_SUITE_DESCRIPTOR);
      },
    });

    assert.equal(store.suites[0].discoveryUrl, "https://suite.example/.well-known/newma-dock-suite.json");
    assert.equal(store.mods[0].id, "example-overview");
    assert.equal(store.mods[0].suiteId, "example-suite");
    assert.equal(store.mods[0].defaultInstall, true);
    assert.equal(store.mods[0].manifest.entry.url, "https://suite.example/overview");
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.redirect, "error");
  assert.equal(calls[0].init.headers.Accept, "application/json");
});

test("falls back to the legacy Suite endpoint and environment prefix", async () => {
  const catalog = {
    schemaVersion: "1.0",
    id: "legacy-http-discovery-store",
    name: "Legacy HTTP Discovery Store",
    git: {},
    mods: [],
    suites: [{
      id: "example-suite",
      discovery: {
        type: "http",
        baseUrlEnv: "VIBEDESK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
      },
    }],
  };
  const calls = [];

  await temporaryStore(catalog, async (storeUrl) => {
    const store = await loadModStore({
      storeUrl,
      env: { NEWMA_DOCK_EXAMPLE_WEB_URL: "https://suite.example" },
      fetchImpl: async (url) => {
        calls.push(String(url));
        return String(url).endsWith("/newma-dock-suite.json")
          ? response({}, 404)
          : response(HTTP_SUITE_DESCRIPTOR);
      },
    });

    assert.equal(store.suites[0].discoveryUrl, "https://suite.example/.well-known/vibedesk-suite.json");
    assert.equal(store.mods[0].manifest.entry.url, "https://suite.example/overview");
  });

  assert.deepEqual(calls, [
    "https://suite.example/.well-known/newma-dock-suite.json",
    "https://suite.example/.well-known/vibedesk-suite.json",
  ]);
});

test("rejects non-standard HTTP Suite Discovery paths", async () => {
  await temporaryStore({
    schemaVersion: "1.0",
    id: "invalid-http-discovery-store",
    name: "Invalid HTTP Discovery Store",
    git: {},
    mods: [],
    suites: [{
      id: "example-suite",
      discovery: {
        type: "http",
        baseUrlEnv: "NEWMA_DOCK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
        path: "/suite.json",
      },
    }],
  }, async (storeUrl) => {
    await assert.rejects(
      loadModStore({ storeUrl, fetchImpl: async () => response({}) }),
      /path must be \/\.well-known\/newma-dock-suite\.json or \/\.well-known\/vibedesk-suite\.json/,
    );
  });
});

test("registers every store Mod and skips identical published Mods", async () => {
  const store = await loadModStore();
  const desired = store.mods.map((mod) => mod.manifest);
  const existing = {
    moduleId: desired[0].id,
    revision: 1,
    status: "published",
    manifest: desired[0],
    createdAt: "2026-07-21T00:00:00Z",
  };
  const calls = [];
  let revision = 1;
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (!init.method) return response([existing]);
    if (String(url).endsWith("/drafts")) return response({ revision: ++revision }, 201);
    return response({ status: "published" });
  };

  const result = await registerStoreMods({ fetchImpl });

  assert.equal(result.skipped.length, 1);
  assert.equal(result.created.length, 41);
  assert.equal(result.disabled.length, 0);
  assert.equal(calls.filter((call) => call.init.method === "POST").length, 82);
  assert.equal(manifestsEqual(existing.manifest, desired[0]), true);
});

test("standardizes the full store without disabling official or third-party Mods", async () => {
  const store = await loadModStore();
  const current = [
    ...store.mods.map(({ manifest }, index) => ({
      moduleId: manifest.id,
      revision: index + 1,
      status: "published",
      manifest,
      createdAt: "2026-07-21T00:00:00Z",
    })),
    ...store.retiredMods.map((moduleId, index) => ({
      moduleId,
      revision: store.mods.length + index + 1,
      status: "published",
      manifest: { id: moduleId },
      createdAt: "2026-07-21T00:00:00Z",
    })),
    {
      moduleId: "third-party",
      revision: 1,
      status: "published",
      manifest: { id: "third-party" },
      createdAt: "2026-07-21T00:00:00Z",
    },
  ];
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (!init.method) return response(current);
    return response({ status: "published" });
  };

  const result = await standardizeStoreMods({ fetchImpl });

  assert.equal(result.created.length, 0);
  assert.equal(result.skipped.length, 42);
  assert.deepEqual(
    result.disabled.map((mod) => mod.moduleId),
    ["investment-settings", "quant-agent"],
  );
  assert.equal(
    calls.filter((call) => call.init.method === "POST").length,
    2,
  );
});

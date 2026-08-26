import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  loadModStore,
  manifestsEqual,
  registerDefaultMods,
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
    baseUrlEnv: "NEWMA_DESK_EXAMPLE_WEB_URL",
    defaultBaseUrl: "http://127.0.0.1:4312",
  },
  manifest: {
    category: "research",
    navigation: {
      groupLabel: "研究",
      groupOrder: 10,
      itemOrder: 100,
      directory: { id: "example-suite", label: "示例项目", order: 10 },
      project: {
        id: "fundamentals",
        name: "宏观面",
        order: 20,
        description: "经济数据、宏观指标、行业、产业链与宏观事件。",
        logo: {
          type: "image",
          src: "https://assets.example/example-project.png",
          alt: "Example Research",
        },
      },
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
  const directory = await mkdtemp(join(tmpdir(), "newma-desk-store-"));
  const storePath = join(directory, "store.json");
  try {
    await writeFile(storePath, JSON.stringify(catalog), "utf8");
    return await callback(pathToFileURL(storePath));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test("validates the project Mod store and installs the core Desk projects", async () => {
  const store = await loadModStore({
    env: {
      NEWMA_DESK_INVESTMENT_WEB_URL: "https://investment.example",
      NEWMA_DESK_TRADING_WEB_URL: "https://trading.example",
      NEWMA_DESK_DEEPSEE_WEB_URL: "https://deepsee.example",
      NEWMA_DESK_SEVEN_CYCLE_WEB_URL: "https://cycle.example",
      NEWMA_DESK_INSTOCK_WEB_URL: "https://instock.example",
      NEWMA_DESK_ORCHESTRA_WEB_URL: "https://orchestra.example",
      NEWMA_DESK_FUND_RESEARCH_WEB_URL: "https://fund.example",
    },
  });
  const defaults = store.mods.filter((mod) => mod.defaultInstall);

  assert.equal(store.mods.length, new Set(store.mods.map((mod) => mod.id)).size);
  assert.ok(store.mods.length >= 93);
  assert.deepEqual(store.suites.map((suite) => suite.id), [
    "research-suite",
    "research-strategy-suite",
    "research-fund-suite",
    "professional-fund-research-suite",
    "research-industry-suite",
    "instock-market-suite",
    "instock-market-analysis-suite",
    "instock-industry-suite",
    "instock-equity-suite",
    "instock-company-suite",
    "trading-suite",
    "trading-execution-suite",
    "portfolio-suite",
    "portfolio-trading-suite",
    "portfolio-risk-suite",
    "deepsee-suite",
    "orchestra-suite",
    "creator-studio-suite",
    "workflow-center-suite",
  ]);
  assert.deepEqual(store.retiredMods, [
    "investment-settings", "quant-agent", "event-intelligence",
    "daily-review", "market-scanner", "stock-research",
    "calendar-effect-overview", "calendar-effect-history",
  ]);
  assert.deepEqual(defaults.map((mod) => mod.id), [
    "global-situation",
    "fed-rates",
    "hormuz-conflict",
    "us-china-trade",
    "policy-analysis",
    "policy-calendar",
    "policy-flow",
    "policy-interpretation",
    "capital-flow",
    "capital-overview",
    "capital-sectors",
    "capital-cross-border",
    "capital-liquidity",
    "capital-etf",
    "capital-emotion",
    "fund-discover",
    "fund-research-library",
    "fund-ai-analysis",
    "fund-recommendations",
    "fund-attribution",
    "fund-portfolio",
    "workflow-overview",
    "workflow-designer",
    "workflow-runs",
    "workflow-delegations",
    "workflow-artifacts",
    "workflow-audit",
    "workflow-settings",
  ]);
  assert.deepEqual(
    [...new Set(defaults.map((mod) => mod.manifest.navigation.project.id))].sort(),
    [
      "capital-flow",
      "fund-research",
      "global-intelligence",
      "industry-research",
      "policy-intelligence",
      "workflow-center-suite",
    ],
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
    assert.equal(mod.manifest.navigation.project.id, "investment-committee");
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
  assert.equal(
    store.mods.find((mod) => mod.id === "deepsee-overview").manifest.navigation.project.id,
    "deepsee",
  );
  for (const mod of store.mods.filter((item) => item.id.startsWith("deepsee-"))) {
    assert.equal(mod.manifest.navigation.project.id, "deepsee");
    assert.equal(mod.manifest.navigation.directory.id, "deepsee-suite");
    assert.equal(mod.manifest.navigation.directory.label, "DeepSee");
  }
  assert.deepEqual(
    store.mods.find((mod) => mod.id === "deepsee-ai-insights").manifest.permissions,
    ["deepsee.read", "deepsee.ai"],
  );
  assert.deepEqual(
    store.mods.find((mod) => mod.id === "deepsee-ai-insights").manifest.actions["deepsee.insights.analyze"].binding,
    {
      type: "agent",
      capability: "deepsee.insights.analyze",
      profile: "deep",
      memoryScope: "user-agent-mod",
    },
  );
  assert.deepEqual(
    store.mods.find((mod) => mod.id === "deepsee-news").manifest.actions["deepsee.news.batch-analyze"].binding,
    {
      type: "agent",
      capability: "deepsee.news.batch-analyze",
      profile: "batch",
      memoryScope: "task",
    },
  );
  const deepseeBatchActions = [
    ["deepsee-wechat", "deepsee.wechat.batch-summarize", 100],
    ["deepsee-email", "deepsee.email.batch-summarize", 50],
    ["deepsee-minutes", "deepsee.minutes.batch-summarize", 50],
    ["deepsee-minutes", "deepsee.minutes.batch-refine", 50],
    ["deepsee-media", "deepsee.media.batch-summarize", 10],
    ["deepsee-official-accounts", "deepsee.official-accounts.batch-summarize", 10],
  ];
  for (const [modId, actionId, maxItems] of deepseeBatchActions) {
    const action = store.mods.find((mod) => mod.id === modId).manifest.actions[actionId];
    assert.deepEqual(action.binding, {
      type: "agent",
      capability: actionId,
      profile: "batch",
      memoryScope: "task",
    });
    assert.equal(action.inputSchema.properties.itemIds.maxItems, maxItems);
  }
  const creatorAgentActions = [
    ["creator-workbench", "creator.intake.batch-extract", "batch", "task"],
    ["creator-brief", "creator.brief.generate", "deep", "user-agent-mod"],
    ["creator-draft", "creator.draft.generate", "deep", "user-agent-mod"],
    ["creator-transwrite", "creator.transwrite.batch-generate", "batch", "task"],
    ["creator-publish", "creator.publish.package", "batch", "task"],
    ["creator-postmortem", "creator.postmortem.analyze", "deep", "user-agent-mod"],
  ];
  for (const [modId, actionId, profile, memoryScope] of creatorAgentActions) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.deepEqual(mod.manifest.actions[actionId].binding, {
      type: "agent",
      capability: actionId,
      profile,
      memoryScope,
    });
    assert.equal(mod.manifest.actions["creator.node.run"].binding.type, "local");
  }
  assert.equal(
    store.mods.find((mod) => mod.id === "deepsee-settings").manifest.navigation.icon,
    "settings",
  );
  for (const modId of ["portfolio-brief", "portfolio-allocation", "portfolio-scenarios", "portfolio-performance", "portfolio-settings"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.manifest.navigation.project.id, "asset-allocation");
    assert.equal(mod.manifest.navigation.directory.id, "portfolio-suite");
  }
  assert.equal(store.mods.find((item) => item.id === "portfolio-activities").manifest.navigation.project.id, "trading");
  assert.equal(store.mods.find((item) => item.id === "portfolio-activities").suiteId, "portfolio-trading-suite");
  assert.equal(store.mods.find((item) => item.id === "portfolio-risk").manifest.navigation.project.id, "risk-management");
  assert.equal(store.mods.find((item) => item.id === "portfolio-risk").suiteId, "portfolio-risk-suite");
  for (const modId of [
    "earnings-workbench", "peer-comparison", "valuation-workbench",
    "research-memo", "thesis-tracker", "research-library", "research-notes",
  ]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.suiteId, "research-suite");
    assert.equal(mod.manifest.navigation.project.id, "equity-research");
    assert.equal(mod.manifest.navigation.directory.id, "research-suite");
  }
  assert.equal(store.mods.find((item) => item.id === "idea-funnel").suiteId, "research-strategy-suite");
  assert.equal(store.mods.find((item) => item.id === "idea-funnel").manifest.navigation.project.id, "strategy-research");
  assert.equal(store.mods.find((item) => item.id === "etf-research").suiteId, "research-fund-suite");
  assert.equal(store.mods.find((item) => item.id === "etf-research").manifest.navigation.project.id, "fund-research");
  for (const modId of ["industry-map"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.suiteId, "research-industry-suite");
    assert.equal(mod.manifest.navigation.project.id, "industry-research");
    assert.equal(mod.manifest.navigation.directory.id, "research-industry-suite");
  }
  const marketWorkbench = store.mods.find((item) => item.id === "instock-market-workbench");
  assert.equal(marketWorkbench.suiteId, "instock-market-suite");
  assert.equal(marketWorkbench.manifest.navigation.label, "市场复盘");
  assert.equal(marketWorkbench.manifest.navigation.project.id, "market-surface");
  assert.equal(marketWorkbench.manifest.navigation.directory.id, "instock-market-suite");

  const marketMap = store.mods.find((item) => item.id === "instock-market-map");
  assert.equal(marketMap.suiteId, undefined);
  assert.equal(marketMap.manifest.navigation.project.id, "market-surface");
  assert.equal(marketMap.manifest.navigation.directory.id, "market-suite");
  for (const modId of ["instock-rotation", "instock-industry-chain"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.suiteId, "instock-industry-suite");
    assert.equal(mod.manifest.navigation.project.id, "industry-research");
    assert.equal(mod.manifest.navigation.directory.id, "instock-industry-suite");
  }
  for (const modId of ["instock-stock-candidates", "instock-technical-signals", "instock-strategy-validation", "instock-research-book"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.suiteId, "instock-equity-suite");
    assert.equal(mod.manifest.navigation.project.id, "strategy-research");
    assert.equal(mod.manifest.navigation.directory.id, "instock-equity-suite");
  }
  for (const modId of ["instock-stock-research", "instock-event-flow"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.suiteId, "instock-company-suite");
    assert.equal(mod.manifest.navigation.project.id, "equity-research");
  }
  assert.equal(store.mods.find((item) => item.id === "instock-czsc").suiteId, "instock-market-analysis-suite");
  assert.equal(store.mods.find((item) => item.id === "instock-czsc").manifest.navigation.project.id, "market-surface");
  for (const modId of ["watchlist"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.manifest.navigation.project.id, "strategy-research");
    assert.equal(mod.manifest.navigation.directory.id, "strategy-watchlist-suite");
  }
  for (const modId of ["seven-cycle-research", "macro-monitor"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.manifest.navigation.project.id, "fundamentals");
    assert.equal(mod.manifest.navigation.directory.id, "macro-suite");
  }
  for (const modId of [
    "global-situation", "news-radar", "catalyst-calendar",
  ]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.manifest.navigation.project.id, "global-intelligence");
    assert.equal(mod.manifest.navigation.directory.id, "global-suite");
  }
  assert.equal(store.mods.find((mod) => mod.id === "event-timeline").manifest.navigation.project.id, "market-surface");
  assert.equal(store.mods.find((mod) => mod.id === "policy-analysis").manifest.navigation.project.id, "policy-intelligence");
  assert.equal(store.mods.find((mod) => mod.id === "policy-analysis").manifest.navigation.directory.id, "policy-suite");
  assert.equal(store.mods.find((mod) => mod.id === "capital-flow").manifest.navigation.project.id, "capital-flow");
  assert.equal(store.mods.find((mod) => mod.id === "capital-flow").manifest.navigation.directory.id, "capital-flow-suite");
  for (const modId of [
    "quant-overview", "alpha-lab", "backtest-lab", "factor-correlation",
    "trading-settings",
  ]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.suiteId, "trading-suite");
    assert.equal(mod.manifest.navigation.project.id, "quant-research");
    assert.equal(mod.manifest.navigation.directory.id, "trading-suite");
  }
  assert.equal(store.mods.find((mod) => mod.id === "trade-desk").suiteId, "trading-execution-suite");
  assert.equal(store.mods.find((mod) => mod.id === "trade-desk").manifest.navigation.project.id, "trading");
  for (const modId of ["fund-discover", "fund-research-library", "fund-ai-analysis", "fund-recommendations", "fund-attribution", "fund-portfolio"]) {
    const mod = store.mods.find((item) => item.id === modId);
    assert.equal(mod.suiteId, "professional-fund-research-suite");
    assert.equal(mod.manifest.navigation.project.id, "fund-research");
    assert.match(mod.manifest.entry.url, /^https:\/\/fund\.example\/mod\/fund-research\//);
  }
  assert.equal(
    store.mods.find((mod) => mod.id === "watchlist").manifest.schemaVersion,
    "1.1",
  );
  const stockResearch = store.mods.find((mod) => mod.id === "instock-stock-research");
  assert.deepEqual(stockResearch.manifest.wiki.subjectTypes, ["security"]);
  assert.equal(stockResearch.manifest.wiki.entrypoints[0].intent, "equity.research");
  const industryMap = store.mods.find((mod) => mod.id === "industry-map");
  assert.deepEqual(industryMap.manifest.wiki.subjectTypes, [
    "security",
    "industry",
    "concept",
  ]);
  assert.equal(industryMap.manifest.wiki.entrypoints[0].intent, "industry.chain");
  for (const modId of [
    "quant-overview",
    "alpha-lab",
    "backtest-lab",
    "factor-correlation",
    "trading-settings",
  ]) {
    assert.equal(store.mods.find((mod) => mod.id === modId).manifest.schemaVersion, "1.1");
  }
  assert.equal(
    store.mods.find((mod) => mod.id === "watchlist").manifest.navigation.groupLabel,
    "策略",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "instock-stock-research").manifest.navigation.groupLabel,
    "公司",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "trade-desk").manifest.navigation.groupLabel,
    "交易",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "trading-settings").manifest.category,
    "system",
  );
});

test("rejects unsafe configured external Mod origins", async () => {
  await assert.rejects(
    loadModStore({
      env: { NEWMA_DESK_INVESTMENT_WEB_URL: "https://user:pass@example.com" },
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
        baseUrlEnv: "NEWMA_DESK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
      },
    }],
  };
  const calls = [];

  await temporaryStore(catalog, async (storeUrl) => {
    const store = await loadModStore({
      storeUrl,
      env: { NEWMA_DESK_EXAMPLE_WEB_URL: "https://suite.example" },
      fetchImpl: async (url, init) => {
        calls.push({ url: String(url), init });
        return response(HTTP_SUITE_DESCRIPTOR);
      },
    });

    assert.equal(store.suites[0].discoveryUrl, "https://suite.example/.well-known/newma-desk-suite.json");
    assert.equal(store.mods[0].id, "example-overview");
    assert.equal(store.mods[0].suiteId, "example-suite");
    assert.equal(store.mods[0].defaultInstall, false);
    assert.equal(store.mods[0].manifest.entry.url, "https://suite.example/overview");
    assert.deepEqual(store.mods[0].manifest.navigation.project, {
      id: "fundamentals",
      name: "宏观面",
      order: 20,
      description: "经济数据、宏观指标、行业、产业链与宏观事件。",
      logo: {
        type: "image",
        src: "https://assets.example/example-project.png",
        alt: "Example Research",
      },
    });
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.redirect, "error");
  assert.equal(calls[0].init.headers.Accept, "application/json");
});

test("promotes a legacy HTTP Mod Suite to its own project", async () => {
  const descriptor = structuredClone(HTTP_SUITE_DESCRIPTOR);
  delete descriptor.manifest.navigation.project;
  const catalog = {
    schemaVersion: "1.0",
    id: "legacy-project-store",
    name: "Legacy Project Store",
    git: {},
    mods: [],
    suites: [{
      id: "example-suite",
      discovery: {
        type: "http",
        baseUrlEnv: "NEWMA_DESK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
      },
    }],
  };

  await temporaryStore(catalog, async (storeUrl) => {
    const store = await loadModStore({
      storeUrl,
      fetchImpl: async () => response(descriptor),
    });

    assert.deepEqual(store.mods[0].manifest.navigation.project, {
      id: "example-suite",
      name: "示例项目",
      order: 10,
      description: "通过 HTTP 自动发现的示例 Mod Suite。",
    });
  });
});

test("rejects a Suite that splits one project across domains", async () => {
  const descriptor = structuredClone(HTTP_SUITE_DESCRIPTOR);
  descriptor.pages.push({
    id: "example-policy",
    name: "政策页面",
    description: "不允许跨栏目拆分的页面。",
    route: "/policy",
    navigation: {
      itemOrder: 20,
      project: { id: "policy-intelligence", name: "政策面", order: 50 },
    },
  });
  const catalog = {
    schemaVersion: "1.0",
    id: "split-suite-store",
    name: "Split Suite Store",
    git: {},
    mods: [],
    suites: [{
      id: "example-suite",
      discovery: {
        type: "http",
        baseUrlEnv: "NEWMA_DESK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
      },
    }],
  };
  await temporaryStore(catalog, async (storeUrl) => {
    await assert.rejects(
      loadModStore({ storeUrl, fetchImpl: async () => response(descriptor) }),
      /cannot split pages across investment domains/,
    );
  });
});

test("rejects a Suite page that moves into another complete project", async () => {
  const descriptor = structuredClone(HTTP_SUITE_DESCRIPTOR);
  descriptor.pages.push({
    id: "example-detached",
    name: "拆分页面",
    description: "不允许脱离来源项目的页面。",
    route: "/detached",
    navigation: {
      itemOrder: 20,
      directory: { id: "detached-suite", label: "另一个项目", order: 20 },
    },
  });
  const catalog = {
    schemaVersion: "1.0",
    id: "detached-suite-store",
    name: "Detached Suite Store",
    git: {},
    mods: [],
    suites: [{
      id: "example-suite",
      discovery: {
        type: "http",
        baseUrlEnv: "NEWMA_DESK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
      },
    }],
  };
  await temporaryStore(catalog, async (storeUrl) => {
    await assert.rejects(
      loadModStore({ storeUrl, fetchImpl: async () => response(descriptor) }),
      /cannot split pages into another project group/,
    );
  });
});

test("rejects unsafe project logo declarations from HTTP Mod Suites", async (t) => {
  const catalog = {
    schemaVersion: "1.0",
    id: "unsafe-project-logo-store",
    name: "Unsafe Project Logo Store",
    git: {},
    mods: [],
    suites: [{
      id: "example-suite",
      discovery: {
        type: "http",
        baseUrlEnv: "NEWMA_DESK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
      },
    }],
  };
  const cases = [
    ["blank letter", { type: "letter", text: " " }],
    ["long letter", { type: "letter", text: "LONG" }],
    ["script URL", { type: "image", src: "javascript:alert(1)" }],
    ["encoded traversal", { type: "image", src: "/%2e%2e/secret.png" }],
    ["unknown icon", { type: "icon", name: "unregistered" }],
    ["unknown field", { type: "letter", text: "ER", html: "<script>" }],
  ];

  for (const [name, logo] of cases) {
    await t.test(name, async () => {
      const descriptor = structuredClone(HTTP_SUITE_DESCRIPTOR);
      descriptor.manifest.navigation.project.logo = logo;
      await temporaryStore(catalog, async (storeUrl) => {
        await assert.rejects(
          loadModStore({
            storeUrl,
            fetchImpl: async () => response(descriptor),
          }),
          /project|logo|relative or HTTP\(S\) URL/,
        );
      });
    });
  }
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
      env: { NEWMA_DESK_EXAMPLE_WEB_URL: "https://suite.example" },
      fetchImpl: async (url) => {
        calls.push(String(url));
        return String(url).endsWith("/vibedesk-suite.json")
          ? response(HTTP_SUITE_DESCRIPTOR)
          : response({}, 404);
      },
    });

    assert.equal(store.suites[0].discoveryUrl, "https://suite.example/.well-known/vibedesk-suite.json");
    assert.equal(store.mods[0].manifest.entry.url, "https://suite.example/overview");
  });

  assert.deepEqual(calls, [
    "https://suite.example/.well-known/newma-desk-suite.json",
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
        baseUrlEnv: "NEWMA_DESK_EXAMPLE_WEB_URL",
        defaultBaseUrl: "http://127.0.0.1:4312",
        path: "/suite.json",
      },
    }],
  }, async (storeUrl) => {
    await assert.rejects(
      loadModStore({ storeUrl, fetchImpl: async () => response({}) }),
      /path must be \/\.well-known\/newma-desk-suite\.json, \/\.well-known\/newma-dock-suite\.json or \/\.well-known\/vibedesk-suite\.json/,
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
  assert.equal(result.created.length, desired.length - 1);
  assert.equal(result.disabled.length, 0);
  assert.equal(
    calls.filter((call) => call.init.method === "POST").length,
    (desired.length - 1) * 2,
  );
  assert.ok(result.created.some((manifest) => manifest.id === "deepsee-overview"));
  assert.ok(result.created.some((manifest) => manifest.id === "seven-cycle-research"));
  assert.equal(manifestsEqual(existing.manifest, desired[0]), true);
});

test("registers only Mods marked for default installation", async () => {
  const store = await loadModStore();
  const defaults = store.mods.filter((mod) => mod.defaultInstall);
  const calls = [];
  let revision = 0;
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (!init.method) return response([]);
    if (String(url).endsWith("/drafts")) return response({ revision: ++revision }, 201);
    return response({ status: "published" });
  };

  const result = await registerDefaultMods({ fetchImpl });
  const createdIds = result.created.map((manifest) => manifest.id);
  const submittedIds = calls
    .filter((call) => String(call.url).endsWith("/drafts"))
    .map((call) => JSON.parse(call.init.body).id);

  assert.deepEqual(createdIds, defaults.map((mod) => mod.id));
  assert.deepEqual(submittedIds, createdIds);
  assert.equal(createdIds.some((id) => id.startsWith("deepsee-")), false);
  assert.equal(createdIds.includes("seven-cycle-research"), false);
  assert.equal(
    calls.filter((call) => call.init.method === "POST").length,
    defaults.length * 2,
  );
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
  assert.equal(result.skipped.length, store.mods.length);
  assert.deepEqual(
    result.disabled.map((mod) => mod.moduleId),
    [
      "investment-settings", "quant-agent", "event-intelligence",
      "daily-review", "market-scanner", "stock-research",
      "calendar-effect-overview", "calendar-effect-history",
    ],
  );
  assert.equal(
    calls.filter((call) => call.init.method === "POST").length,
    8,
  );
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  checkModManifest,
  runCompatibilityCheck,
} from "../../scripts/check-mod-compatibility.mjs";

const manifestParity = JSON.parse(
  readFileSync(resolve("tests/fixtures/mod-manifest-parity.json"), "utf8"),
);

const connected = {
  schemaVersion: "1.1",
  id: "factor-lab",
  name: "因子实验室",
  version: "1.0.0",
  category: "quant",
  entry: { type: "external", url: "https://quant.example/mod" },
  compatibility: { level: 2, bridgeProtocol: "1.0" },
  permissions: ["quant.execute", "research.read"],
  dataServices: ["vibe-trading"],
  actions: {
    "factor.backtest": {
      binding: { type: "data", service: "vibe-trading" },
      execution: "task",
      permission: "quant.execute",
      inputSchema: { type: "object" },
      outputSchema: { type: "object" },
      confirmation: "user",
    },
    "research.explain": {
      binding: { type: "agent", memoryScope: "user-agent-mod" },
      execution: "task",
      permission: "research.read",
      inputSchema: { type: "object" },
      outputSchema: { type: "object" },
      confirmation: "none",
    },
  },
  events: { emits: [], accepts: [] },
};

for (const fixture of manifestParity.cases) {
  test(`keeps the shared manifest contract aligned for ${fixture.id}`, () => {
    const result = checkModManifest(fixture.manifest);
    assert.equal(result.contractStatus === "passed", fixture.expectedValid);
  });
}

test("validates a connected Mod contract and derives capability badges", () => {
  const result = checkModManifest(connected);

  assert.equal(result.level, 2);
  assert.equal(result.declaredLevel, 2);
  assert.equal(result.certifiedLevel, null);
  assert.equal(result.contractStatus, "passed");
  assert.equal(result.certificationStatus, "pending");
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.badges, ["Agent", "Data", "Schema"]);
});

test("rejects undeclared permissions and data services", () => {
  const result = checkModManifest({
    ...connected,
    permissions: [],
    dataServices: [],
  });

  assert.ok(result.errors.some((error) => error.includes("permission")));
  assert.ok(result.errors.some((error) => error.includes("data service")));
});

test("rejects confirmation values that the runtime contract cannot parse", () => {
  const result = checkModManifest({
    ...connected,
    actions: {
      ...connected.actions,
      "factor.backtest": {
        ...connected.actions["factor.backtest"],
        confirmation: "required",
      },
    },
  });

  assert.ok(result.errors.some((error) => error.includes("confirmation must be")));
});

test("embedded market workspaces declare every data action used by their runtime", () => {
  const requiredActions = {
    "market-daily": [
      "market.symbol-search",
      "market.quotes",
      "market.quote",
      "market.ohlcv",
      "market.intraday",
      "market.overview",
      "market.indices",
      "market.global-indices",
      "market.turnover-top",
    ],
    "market-scanner": [
      "market.symbol-search",
      "market.quote",
      "market.scan",
    ],
    "multi-timeframe": [
      "market.symbol-search",
      "market.quote",
      "market.ohlcv",
      "market.intraday",
    ],
    "relative-strength": [
      "market.symbol-search",
      "market.quote",
      "market.ohlcv",
    ],
    "event-timeline": [
      "market.symbol-search",
      "market.quote",
      "market.ohlcv",
      "market.announcements",
      "market.reports",
      "market.news",
    ],
    "trading-replay": [
      "market.symbol-search",
      "market.quote",
      "market.ohlcv",
      "market.intraday",
    ],
  };

  for (const [modId, actions] of Object.entries(requiredActions)) {
    const source = JSON.parse(
      readFileSync(resolve(`mods/${modId}/mod.json`), "utf8"),
    );
    const declared = new Set(Object.keys(source.manifest.actions));
    assert.deepEqual(
      actions.filter((actionId) => !declared.has(actionId)),
      [],
      `${modId} is missing embedded data actions`,
    );
  }
});

test("the current store keeps legacy Mods compatible and validates declared levels", async () => {
  const results = await runCompatibilityCheck();

  assert.equal(results.length, new Set(results.map((result) => result.id)).size);
  assert.ok(results.length >= 42);
  assert.ok(results.every((result) => result.errors.length === 0));
  assert.ok(
    results
      .filter((result) => result.level !== 0)
      .every((result) => result.certificationStatus === "pending"),
  );
  assert.ok(
    results
      .filter((result) => result.level === 0)
      .every((result) => result.certificationStatus === "not-applicable"),
  );
  assert.equal(results.find((result) => result.id === "market-daily").level, 3);
  assert.equal(results.find((result) => result.id === "watchlist").level, 3);
  assert.equal(results.find((result) => result.id === "idea-funnel").level, 3);
  assert.equal(results.find((result) => result.id === "research-library").level, 3);
  assert.equal(results.find((result) => result.id === "research-notes").level, 3);
  assert.equal(results.find((result) => result.id === "industry-map").level, 3);
  assert.equal(results.find((result) => result.id === "news-radar").level, 3);
  assert.equal(results.find((result) => result.id === "capital-flow").level, 3);
  assert.equal(results.find((result) => result.id === "etf-research").level, 3);
  assert.equal(results.find((result) => result.id === "catalyst-calendar").level, 3);
  assert.equal(results.find((result) => result.id === "earnings-workbench").level, 3);
  assert.equal(results.find((result) => result.id === "peer-comparison").level, 3);
  assert.equal(results.find((result) => result.id === "valuation-workbench").level, 3);
  assert.equal(results.find((result) => result.id === "research-memo").level, 3);
  assert.equal(results.find((result) => result.id === "macro-monitor").level, 3);
  assert.equal(results.find((result) => result.id === "thesis-tracker").level, 3);
  const portfolioIds = [
    "portfolio-brief",
    "portfolio-activities",
    "portfolio-risk",
    "portfolio-allocation",
    "portfolio-scenarios",
    "portfolio-performance",
    "portfolio-settings",
  ];
  assert.ok(portfolioIds.every((id) => results.find((result) => result.id === id)?.level === 3));
  const chartWorkspaceIds = [
    "global-situation",
    "fed-rates",
    "hormuz-conflict",
    "us-china-trade",
    "policy-calendar",
    "policy-flow",
    "policy-interpretation",
    "capital-overview",
    "capital-sectors",
    "capital-cross-border",
    "capital-liquidity",
    "capital-etf",
    "capital-emotion",
    "market-sentiment",
    "market-technical",
    "multi-timeframe",
    "relative-strength",
    "event-timeline",
    "trading-replay",
  ];
  assert.ok(chartWorkspaceIds.every((id) => results.find((result) => result.id === id)?.level === 3));
  const instockSuiteIds = [
    "instock-market-workbench",
    "instock-market-map",
    "instock-rotation",
    "instock-stock-candidates",
    "instock-technical-signals",
    "instock-stock-research",
    "instock-czsc",
    "instock-event-flow",
    "instock-industry-chain",
    "instock-strategy-validation",
    "instock-research-book",
  ];
  assert.ok(instockSuiteIds.every((id) => results.find((result) => result.id === id)?.level === 2));
  const deepseeIds = [
    "deepsee-overview",
    "deepsee-ai-insights",
    "deepsee-news",
    "deepsee-wechat",
    "deepsee-email",
    "deepsee-minutes",
    "deepsee-media",
    "deepsee-official-accounts",
    "deepsee-campaigns",
    "deepsee-contacts",
    "deepsee-settings",
  ];
  assert.ok(deepseeIds.every((id) => results.find((result) => result.id === id)?.level === 2));
  const orchestraIds = [
    "orchestra-committee",
    "orchestra-history",
    "orchestra-reports",
    "orchestra-agents",
    "orchestra-skills",
    "orchestra-data",
    "orchestra-workspace",
    "orchestra-settings",
  ];
  assert.ok(orchestraIds.every((id) => results.find((result) => result.id === id)?.level === 1));
  const tradingSuiteIds = [
    "quant-overview",
    "alpha-lab",
    "backtest-lab",
    "factor-correlation",
    "trade-desk",
    "trading-settings",
  ];
  assert.ok(tradingSuiteIds.every((id) => results.find((result) => result.id === id)?.level === 1));
  const creatorStudioIds = [
    "creator-dashboard",
    "creator-workbench",
    "creator-brief",
    "creator-draft",
    "creator-transwrite",
    "creator-publish",
    "creator-postmortem",
    "creator-marketplace",
    "creator-settings",
  ];
  assert.ok(creatorStudioIds.every((id) => results.find((result) => result.id === id)?.level === 3));
  const fundResearchIds = [
    "fund-discover",
    "fund-research-library",
    "fund-ai-analysis",
    "fund-recommendations",
    "fund-attribution",
    "fund-portfolio",
  ];
  assert.ok(fundResearchIds.every((id) => results.find((result) => result.id === id)?.level === 3));
  const workflowCenterIds = [
    "workflow-overview",
    "workflow-designer",
    "workflow-runs",
    "workflow-delegations",
    "workflow-artifacts",
    "workflow-audit",
    "workflow-settings",
  ];
  assert.ok(workflowCenterIds.every((id) => results.find((result) => result.id === id)?.level === 3));
  assert.ok(
    results
      .filter((result) => ![
        "market-daily",
        "news-radar",
        "policy-analysis",
        "capital-flow",
        "watchlist",
        "idea-funnel",
        "research-library",
        "research-notes",
        "etf-research",
        "catalyst-calendar",
        "earnings-workbench",
        "peer-comparison",
        "valuation-workbench",
        "research-memo",
        "macro-monitor",
        "thesis-tracker",
        "industry-map",
        ...portfolioIds,
        ...chartWorkspaceIds,
        ...instockSuiteIds,
        ...deepseeIds,
        ...orchestraIds,
        ...tradingSuiteIds,
        ...creatorStudioIds,
        ...fundResearchIds,
        ...workflowCenterIds,
      ].includes(result.id))
      .every((result) => result.level === 0),
  );
});

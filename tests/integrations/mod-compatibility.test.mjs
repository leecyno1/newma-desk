import assert from "node:assert/strict";
import test from "node:test";

import {
  checkModManifest,
  runCompatibilityCheck,
} from "../../scripts/check-mod-compatibility.mjs";

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
  const portfolioIds = [
    "portfolio-brief",
    "portfolio-activities",
    "portfolio-risk",
    "portfolio-performance",
    "portfolio-settings",
  ];
  assert.ok(portfolioIds.every((id) => results.find((result) => result.id === id)?.level === 3));
  const chartWorkspaceIds = [
    "market-scanner",
    "multi-timeframe",
    "relative-strength",
    "event-timeline",
    "trading-replay",
  ];
  assert.ok(chartWorkspaceIds.every((id) => results.find((result) => result.id === id)?.level === 3));
  assert.equal(results.find((result) => result.id === "instock-czsc").level, 2);
  assert.equal(results.find((result) => result.id === "instock-rotation").level, 2);
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
  assert.ok(
    results
      .filter((result) => ![
        "market-daily",
        "watchlist",
        ...portfolioIds,
        ...chartWorkspaceIds,
        "instock-czsc",
        "instock-rotation",
        ...orchestraIds,
      ].includes(result.id))
      .every((result) => result.level === 0),
  );
});

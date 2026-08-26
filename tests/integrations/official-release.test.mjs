import assert from "node:assert/strict";
import test from "node:test";

import {
  checkReleaseModDataContracts,
  loadReleaseDataServices,
  selectReleaseCertificationMods,
} from "../../scripts/lib/official-release.mjs";
import { loadModStore } from "../../scripts/lib/mod-store.mjs";


test("runtime certification candidates come from default Manifest 1.1 Store entries", () => {
  const selected = selectReleaseCertificationMods({
    mods: [
      { id: "default-v1", defaultInstall: true, manifest: { schemaVersion: "1.1" } },
      { id: "optional-v1", defaultInstall: false, manifest: { schemaVersion: "1.1" } },
      { id: "default-legacy", defaultInstall: true, manifest: { schemaVersion: "1.0" } },
    ],
  });

  assert.deepEqual(selected.map((mod) => mod.id), ["default-v1"]);
});

test("current official Mods only use registered data capabilities", async () => {
  const store = await loadModStore();
  const mods = selectReleaseCertificationMods(store);
  const services = await loadReleaseDataServices();

  assert.deepEqual(mods.map((mod) => mod.id), [
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
  assert.deepEqual(checkReleaseModDataContracts(mods, services), []);
});

test("release data check rejects a missing unified provider", () => {
  const errors = checkReleaseModDataContracts([
    {
      id: "broken-monitor",
      manifest: {
        dataServices: [],
        actions: {
          "missing.snapshot": {
            binding: { type: "data" },
            permission: "market.read",
          },
        },
      },
    },
  ], new Map());

  assert.deepEqual(errors, [
    "broken-monitor/missing.snapshot: no data service provides missing.snapshot",
  ]);
});

import { defineConfig } from "@playwright/test";

import { chromiumProject } from "./tests/e2e/browser-project";

process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN ??= "http://127.0.0.1:5888";
process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN ??= "http://127.0.0.1:8911";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: ["domain-suites.spec.ts", "policy-research.spec.ts", "market-structure.spec.ts", "market-sentiment.spec.ts", "capital-evidence.spec.ts", "capital-liquidity.spec.ts", "capital-appetite.spec.ts", "news-radar.spec.ts", "macro-monitor.spec.ts", "seven-cycle-context.spec.ts", "global-intelligence.spec.ts", "portfolio-risk.spec.ts", "earnings-evidence.spec.ts", "earnings-upload.spec.ts", "copilot-markdown.spec.ts", "valuation-inputs.spec.ts", "fund-context.spec.ts"],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: {
    timeout: 20_000,
  },
  reporter: [["list"]],
  use: {
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [chromiumProject()],
});

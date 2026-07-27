import { defineConfig } from "@playwright/test";

import { chromiumProject } from "./tests/e2e/browser-project";

process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN ??= "http://127.0.0.1:5888";
process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN ??= "http://127.0.0.1:8911";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "domain-suites.spec.ts",
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

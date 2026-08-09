import { defineConfig } from "@playwright/test";

import { chromiumProject } from "./tests/e2e/browser-project";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "equity-research.live.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
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

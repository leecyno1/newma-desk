import { defineConfig } from "@playwright/test";

import {
  apiHealthUrl,
  apiOrigin,
  apiPort,
  databasePath,
  demoModuleUrl,
  moduleOrigin,
  modulePort,
  shellOrigin,
  shellPort,
} from "./tests/e2e/runtime-config";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",
  use: {
    actionTimeout: 5_000,
    navigationTimeout: 10_000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
  webServer: [
    {
      command:
        "services/api/.venv/bin/uvicorn vibe_visualization_api.main:app " +
        `--app-dir services/api --host 127.0.0.1 --port ${apiPort}`,
      url: apiHealthUrl,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VIBE_VIS_DATABASE_PATH: databasePath,
        VIBE_VIS_ALLOWED_ORIGINS: `${shellOrigin},${moduleOrigin}`,
      },
    },
    {
      command:
        "npm run dev -w @vibe-visualization/shell -- " +
        `--host 127.0.0.1 --port ${shellPort}`,
      url: `${shellOrigin}/`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VITE_MODULE_ORIGIN: moduleOrigin,
        VITE_API_PROXY_TARGET: apiOrigin,
      },
    },
    {
      command:
        `python3 -m http.server ${modulePort} --bind 127.0.0.1 ` +
        "--directory tests/e2e/fixtures",
      url: demoModuleUrl,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});

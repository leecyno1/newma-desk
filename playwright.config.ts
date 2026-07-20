import { defineConfig } from "@playwright/test";

import {
  apiHealthUrl,
  apiOrigin,
  apiPort,
  databasePath,
  demoModuleUrl,
  fakeHealthUrl,
  fakeOrigin,
  fakePort,
  moduleOrigin,
  modulePort,
  runtimeDir,
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
        `services/api/.venv/bin/python tests/e2e/fake-upstream.py --port ${fakePort}`,
      url: fakeHealthUrl,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command:
        "services/api/.venv/bin/uvicorn vibe_visualization_api.main:app " +
        `--app-dir services/api --host 127.0.0.1 --port ${apiPort}`,
      url: apiHealthUrl,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VIBE_VIS_DATABASE_PATH: databasePath,
        VIBE_VIS_RUNTIME_DIR: runtimeDir,
        VIBE_VIS_ALLOWED_ORIGINS: `${shellOrigin},${moduleOrigin}`,
        VIBE_VIS_RESEARCH_BASE_URL: fakeOrigin,
        VIBE_VIS_OPENAI_BASE_URL: `${fakeOrigin}/v1`,
        VIBE_VIS_OPENAI_API_KEY: "e2e-api-key",
        VIBE_VIS_OPENAI_MODEL: "e2e-model",
        VIBE_VIS_MODEL_TIMEOUT_SECONDS: "5",
        VIBE_VIS_HERMES_WEBUI_BASE_URL: fakeOrigin,
        VIBE_VIS_AGENT_TIMEOUT_SECONDS: "5",
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
        "npm run build -w @vibe-visualization/market-daily && " +
        `python3 tests/e2e/module-server.py --port ${modulePort}`,
      url: demoModuleUrl,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VITE_GATEWAY_BASE_URL: apiOrigin,
        VITE_PARENT_ORIGIN: shellOrigin,
      },
    },
  ],
});

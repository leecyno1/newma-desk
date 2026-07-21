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
        "services/api/.venv/bin/python -m uvicorn vibe_visualization_api.main:app " +
        `--app-dir services/api --host 127.0.0.1 --port ${apiPort}`,
      url: apiHealthUrl,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VIBEDESK_DATABASE_PATH: databasePath,
        VIBEDESK_RUNTIME_DIR: runtimeDir,
        VIBEDESK_ALLOWED_ORIGINS: `${shellOrigin},${moduleOrigin}`,
        VIBEDESK_RESEARCH_BASE_URL: fakeOrigin,
        VIBEDESK_OPENAI_BASE_URL: `${fakeOrigin}/v1`,
        VIBEDESK_OPENAI_API_KEY: "e2e-api-key",
        VIBEDESK_OPENAI_MODEL: "e2e-model",
        VIBEDESK_MODEL_TIMEOUT_SECONDS: "5",
        VIBEDESK_HERMES_WEBUI_BASE_URL: fakeOrigin,
        VIBEDESK_AGENT_TIMEOUT_SECONDS: "5",
      },
    },
    {
      command:
        "npm run dev -w @vibedesk/desk -- " +
        `--host 127.0.0.1 --port ${shellPort}`,
      url: `${shellOrigin}/`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VITE_MOD_ORIGIN: moduleOrigin,
        VITE_API_PROXY_TARGET: apiOrigin,
      },
    },
    {
      command:
        "npm run build -w @vibedesk/market-pulse && " +
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

import { defineConfig } from "@playwright/test";

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
        "services/api/.venv/bin/uvicorn vibe_visualization_api.main:app --app-dir services/api --host 127.0.0.1 --port 8901",
      url: "http://127.0.0.1:8901/api/health",
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VIBE_VIS_DATABASE_PATH: "runtime/e2e-foundation.db",
        VIBE_VIS_ALLOWED_ORIGINS:
          "http://127.0.0.1:15888,http://127.0.0.1:5891",
      },
    },
    {
      command:
        "npm run dev -w @vibe-visualization/shell -- --host 127.0.0.1 --port 15888",
      url: "http://127.0.0.1:15888/",
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VITE_MODULE_ORIGIN: "http://127.0.0.1:5891",
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8901",
      },
    },
    {
      command:
        "python3 -m http.server 5891 --bind 127.0.0.1 --directory tests/e2e/fixtures",
      url: "http://127.0.0.1:5891/modules/demo/",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});

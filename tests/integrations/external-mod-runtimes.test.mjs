import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveExternalModRuntimes,
  runtimeEnvironment,
} from "../../scripts/lib/external-mod-runtimes.mjs";

const descriptor = {
  schemaVersion: "1.0",
  roots: [
    {
      id: "projects",
      env: "NEWMA_DOCK_PROJECTS_ROOT",
      fallback: { type: "repo-relative", path: ".." },
    },
  ],
  runtimes: [
    {
      id: "example-runtime",
      label: "Example Runtime",
      adapter: "example",
      workspaces: {
        source: {
          env: "NEWMA_DOCK_EXAMPLE_WORKSPACE",
          candidates: [{ root: "projects", path: "example" }],
        },
      },
      endpoints: {
        web: {
          env: "NEWMA_DOCK_EXAMPLE_WEB_URL",
          defaultOrigin: "http://127.0.0.1:4321",
          healthPath: "/health",
        },
      },
    },
  ],
};

test("discovers a sibling workspace and derives endpoint lifecycle data", () => {
  const existing = new Set(["/workspace/example"]);
  const catalog = resolveExternalModRuntimes(descriptor, {
    repoRoot: "/workspace/newma-dock",
    homeDir: "/home/user",
    env: {},
    exists: (candidate) => existing.has(candidate),
  });
  const runtime = catalog.byId["example-runtime"];

  assert.equal(runtime.workspaces.source.path, "/workspace/example");
  assert.equal(runtime.workspaces.source.source, "discovered");
  assert.deepEqual(runtime.endpoints.web, {
    env: "NEWMA_DOCK_EXAMPLE_WEB_URL",
    origin: "http://127.0.0.1:4321",
    port: 4321,
    local: true,
    healthPath: "/health",
    healthUrl: "http://127.0.0.1:4321/health",
  });
});

test("treats an explicitly missing workspace as configuration evidence", () => {
  const catalog = resolveExternalModRuntimes(descriptor, {
    repoRoot: "/workspace/newma-dock",
    homeDir: "/home/user",
    env: { NEWMA_DOCK_EXAMPLE_WORKSPACE: "/missing/example" },
    exists: () => false,
  });

  assert.equal(catalog.byId["example-runtime"].workspaces.source.path, null);
  assert.equal(
    catalog.byId["example-runtime"].workspaces.source.source,
    "missing-environment",
  );
  assert.deepEqual(
    catalog.byId["example-runtime"].workspaces.source.attempts,
    ["/missing/example"],
  );
});

test("exports resolved workspace and endpoint values for child processes", () => {
  const catalog = resolveExternalModRuntimes(descriptor, {
    repoRoot: "/workspace/newma-dock",
    homeDir: "/home/user",
    env: {
      NEWMA_DOCK_PROJECTS_ROOT: "/projects",
      NEWMA_DOCK_EXAMPLE_WEB_URL: "https://example.test",
    },
    exists: (candidate) => candidate === "/projects/example",
  });

  assert.deepEqual(runtimeEnvironment(catalog), {
    NEWMA_DOCK_EXAMPLE_WORKSPACE: "/projects/example",
    NEWMA_DOCK_EXAMPLE_WEB_URL: "https://example.test",
  });
  assert.equal(catalog.byId["example-runtime"].endpoints.web.local, false);
});

test("accepts previous VIBEDESK environment names for compatibility", () => {
  const catalog = resolveExternalModRuntimes(descriptor, {
    repoRoot: "/workspace/newma-dock",
    homeDir: "/home/user",
    env: { VIBEDESK_EXAMPLE_WEB_URL: "https://legacy.example" },
    exists: () => false,
  });

  assert.equal(
    catalog.byId["example-runtime"].endpoints.web.origin,
    "https://legacy.example",
  );
});

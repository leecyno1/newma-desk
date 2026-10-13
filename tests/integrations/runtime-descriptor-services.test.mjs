import assert from "node:assert/strict";
import test from "node:test";

import { resolveExternalModRuntimes } from "../../scripts/lib/external-mod-runtimes.mjs";
import {
  createRuntimeServiceGroups,
  interpolateRuntimeTemplate,
} from "../../scripts/lib/runtime-descriptor-services.mjs";

function descriptor(launch = {
  command: "node",
  args: ["server.mjs", "--port", "{{endpoint.port}}"],
  requiredPaths: ["server.mjs"],
  prepare: "example-prepare",
  env: { PUBLIC_URL: "{{endpoint.origin}}" },
}) {
  return {
    schemaVersion: "2.0",
    roots: [],
    profiles: {
      core: { preCore: ["example-runtime"], optional: [] },
      local: { preCore: ["example-runtime"], optional: [] },
      all: { preCore: ["example-runtime"], optional: [] },
    },
    runtimes: [
      {
        id: "example-runtime",
        label: "Example Runtime",
        adapter: "example",
        workspaces: {
          source: {
            env: "NEWMA_DESK_EXAMPLE_WORKSPACE",
            candidates: [{ root: "repo", path: "runtime" }],
          },
        },
        endpoints: {
          web: {
            env: "NEWMA_DESK_EXAMPLE_WEB_URL",
            defaultOrigin: "http://127.0.0.1:4321",
            healthPath: "/healthz",
          },
        },
        services: [
          {
            id: "example-service",
            label: "Example Service",
            workspace: "source",
            endpoint: "web",
            criticality: { local: "optional", remote: "external" },
            launch,
            readiness: { mode: "json", expectedService: "example-service" },
          },
        ],
      },
    ],
  };
}

test("builds a supervised service from Runtime Descriptor 2.0", async () => {
  const existing = new Set([
    "/workspace/newma-desk/runtime",
    "/workspace/newma-desk/runtime/server.mjs",
  ]);
  const catalog = resolveExternalModRuntimes(descriptor(), {
    repoRoot: "/workspace/newma-desk",
    homeDir: "/home/user",
    env: {},
    exists: (candidate) => existing.has(candidate),
  });
  let prepared = false;
  const groups = createRuntimeServiceGroups(catalog, {
    exists: (candidate) => existing.has(candidate),
    prepareAdapters: {
      "example-prepare": async ({ runtime, service }) => {
        assert.equal(runtime.id, "example-runtime");
        assert.equal(service.id, "example-service");
        prepared = true;
      },
    },
  });
  const [service] = groups["example-runtime"];

  assert.equal(service.command, "node");
  assert.deepEqual(service.commandArgs, ["server.mjs", "--port", "4321"]);
  assert.deepEqual(service.env, { PUBLIC_URL: "http://127.0.0.1:4321" });
  assert.equal(service.cwd, "/workspace/newma-desk/runtime");
  assert.equal(service.url, "http://127.0.0.1:4321/healthz");
  assert.equal(service.criticality, "optional");
  await service.prepare();
  assert.equal(prepared, true);
});

test("preserves service-specific cold-start budget without changing the request timeout", () => {
  const input = descriptor();
  delete input.runtimes[0].services[0].launch.prepare;
  input.runtimes[0].services[0].readiness.startupTimeoutMs = 120_000;
  const resolve = () => resolveExternalModRuntimes(input, {
    repoRoot: "/workspace/newma-desk", homeDir: "/home/user", env: {}, exists: () => true,
  });
  const catalog = resolve();
  const service = createRuntimeServiceGroups(catalog, { exists: () => true })["example-runtime"][0];
  assert.equal(service.startupTimeoutMs, 120_000);
  assert.equal(catalog.runtimes[0].services[0].readiness.timeoutMs, undefined);
  input.runtimes[0].services[0].readiness.startupTimeoutMs = -1;
  assert.throws(resolve, /startupTimeoutMs must be a positive number/);
});

test("uses a launch Adapter only for a runtime that needs special command selection", () => {
  const existing = new Set(["/workspace/newma-desk/runtime"]);
  const catalog = resolveExternalModRuntimes(descriptor({ adapter: "special" }), {
    repoRoot: "/workspace/newma-desk",
    homeDir: "/home/user",
    env: {},
    exists: (candidate) => existing.has(candidate),
  });
  const groups = createRuntimeServiceGroups(catalog, {
    exists: (candidate) => existing.has(candidate),
    launchAdapters: {
      special: ({ endpoint }) => ({
        command: "special-runtime",
        commandArgs: ["--listen", String(endpoint.port)],
      }),
    },
  });

  assert.equal(groups["example-runtime"][0].command, "special-runtime");
  assert.deepEqual(groups["example-runtime"][0].commandArgs, ["--listen", "4321"]);
});

test("omits an optional local service whose declared launch files are absent", () => {
  const catalog = resolveExternalModRuntimes(descriptor(), {
    repoRoot: "/workspace/newma-desk",
    homeDir: "/home/user",
    env: {},
    exists: (candidate) => candidate === "/workspace/newma-desk/runtime",
  });
  const groups = createRuntimeServiceGroups(catalog, {
    exists: (candidate) => candidate === "/workspace/newma-desk/runtime",
  });

  assert.deepEqual(groups["example-runtime"], []);
});

test("does not attach a local command to an explicitly remote endpoint", () => {
  const catalog = resolveExternalModRuntimes(descriptor(), {
    repoRoot: "/workspace/newma-desk",
    homeDir: "/home/user",
    env: { NEWMA_DESK_EXAMPLE_WEB_URL: "https://runtime.example" },
    exists: () => true,
  });
  const [service] = createRuntimeServiceGroups(catalog)["example-runtime"];

  assert.equal(service.command, undefined);
  assert.equal(service.criticality, "external");
  assert.equal(service.url, "https://runtime.example/healthz");
});

test("rejects unknown template variables instead of silently spawning a broken command", () => {
  assert.throws(
    () => interpolateRuntimeTemplate("{{endpoint.missing}}", { endpoint: {} }),
    /未知 Runtime Descriptor 模板变量/,
  );
});
